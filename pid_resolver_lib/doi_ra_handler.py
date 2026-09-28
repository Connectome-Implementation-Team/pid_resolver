#  Copyright 2024 Switch
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
from pathlib import Path
from typing import List, Dict, Union, cast, Any, Optional
from functools import reduce
import asyncio
from aiohttp import ClientSession, ClientResponse, TCPConnector, ClientTimeout # type: ignore
import jq # type: ignore
from .cache_handler import get_keys
from .rate_limit import RetryConfig, AsyncRateLimiter, request_with_retry
from .pid_resolver import DEFAULT_USER_AGENT
import logging

# 'requests_per_second' is the sustained rate used when fetching each RA's records via doi.org
# content negotiation in fetch_records (see pid_resolver.py); adjust to whatever the target API
# currently documents, e.g. https://support.datacite.org/docs/rate-limit for DataCite/Crossref.
RAs: Dict[str, Dict[str, Union[str, float]]] = {
    'DataCite': {'mime': 'application/ld+json', 'requests_per_second': 3.0},
    'Crossref': {'mime': 'application/rdf+xml', 'requests_per_second': 3.0},
    'mEDRA': {'mime': 'application/rdf+xml', 'requests_per_second': 5.0}
}

REGISTRATION_AGENCY = 'RA:'
DOI_RA_BASE_URL = 'https://doi.org/ra'

logger = logging.getLogger(__name__)

def get_registration_agency_prefixes(dois: List[str]) -> List[str]:
    """
    Given a list of DOIS, returns their agency prefixes (no duplicates).

    :param dois: A list of DOIs without base URL, e.g., 10.1016/j.jtherbio.2015.06.009.
    """
    agencies: List[str] = jq.compile('[.[] | .[0:index("/")]] | unique').input_value(dois).first()

    return agencies


async def _make_registration_agency_prefix_request(
        session: ClientSession,
        doi_prefix: str,
        limiter: AsyncRateLimiter,
        retry_config: RetryConfig,
) -> Union[Dict[str, str], None]:
    """
    Given a DOI prefix, fetches information about the RA. Rate limiting and retries of transient
    failures are handled by `request_with_retry`.

    @param session: The aiohttp session to be used.
    @param doi_prefix: The DOI prefix to be fetched.
    @param limiter: Rate limiter shared across all requests in this batch.
    @param retry_config: Retry/backoff behavior for transient failures.
    """

    async def parse(request: ClientResponse) -> Optional[Dict[str, str]]:
        res = await request.json()
        if isinstance(res, list) and len(res) == 1:
            return cast(Dict[str, str], res[0])
        logging.error(f'{REGISTRATION_AGENCY} {doi_prefix}: DOI RA result is not a list: {res}')
        return None

    return await request_with_retry(
        session, f'{DOI_RA_BASE_URL}/{doi_prefix}', limiter, retry_config, parse,
        REGISTRATION_AGENCY, doi_prefix)


async def resolve_registration_agency_prefixes(
        doi_prefixes: List[str],
        requests_per_second: float = 5.0,
        max_concurrency: int = 10,
        retry_config: Optional[RetryConfig] = None,
        user_agent: str = DEFAULT_USER_AGENT,
) -> List[Dict[str, str]]:
    """
    Given a list of DOI prefixes, resolves them to get the registration agencies.

    @param doi_prefixes: DOI prefixes to be resolved.
    @param requests_per_second: Sustained request rate against https://doi.org/ra.
    @param max_concurrency: Maximum number of requests in flight at once.
    @param retry_config: Retry/backoff behavior for transient failures. Defaults to RetryConfig().
    @param user_agent: Value of the User-Agent header sent with every request.
    """

    retry_config = retry_config or RetryConfig()
    limiter = AsyncRateLimiter(rate=requests_per_second)

    conn = TCPConnector(limit=max_concurrency)
    time_out = ClientTimeout(total=None, sock_connect=30, sock_read=60)
    headers = {'User-Agent': user_agent}

    async with ClientSession(connector=conn, timeout=time_out, headers=headers) as session:

        requests = [_make_registration_agency_prefix_request(session, doi_prefix, limiter, retry_config)
                    for doi_prefix in doi_prefixes]

        results = await asyncio.gather(*requests)

        filtered: List[Dict[str, str]] = list(filter(lambda res: res is not None, cast(List[Union[Dict[str, str]]], results)))

        return filtered


def filter_prefixes_by_registration_agency(resolved_doi_registration_agencies:  List[Dict[str, str]], registration_agency: str) -> List[str]:
    """
    Given a list of DOI prefix responses, filters them by a specific registration agency.

    @param resolved_doi_registration_agencies: Resolved DOI prefixes.
    @param registration_agency: The registration agency to filter for, e.g., "Crossref"
    """

    return jq.compile(f'[.[] | select(.RA == "{registration_agency}") | .DOI ]').input_value(
        resolved_doi_registration_agencies).first()


def filter_dois_by_prefixes(dois: List[str], prefixes: List[str]) -> List[str]:
    """
    Given a list of DOIs, filters them by their prefix.

    @param dois: Dois to be filtered.
    @param prefixes: Prefixes to filter for.
    """

    filtered_dois = list(filter(lambda doi: doi[0:(doi.find('/'))] in prefixes, dois))
    return list(set(filtered_dois))


async def group_dois_by_ra(dois: List[str]) -> Dict[str, List[str]]:
    """
    Given a list of DOIs, groups them by RA.

    @param dois: DOIs to be grouped.
    """

    existing_dois = list(map(lambda ra: get_keys(Path(ra)), RAs))

    dois_to_harvest = list(set(dois) - set([item for sublist in existing_dois for item in sublist]))

    # return if list is empty
    if len(dois_to_harvest) == 0:
        return {}

    # get prefixes from DOIs
    doi_prefixes: List[str] = get_registration_agency_prefixes(dois_to_harvest)

    # For each prefix, resolve its RA.
    resolved_ras_for_doi_prefixes: List[Dict[str, str]] = await resolve_registration_agency_prefixes(doi_prefixes)

    # Make a list of available RAs
    ras = set(map(lambda ra: ra['RA'], filter(lambda doi_info: 'RA' in doi_info, resolved_ras_for_doi_prefixes)))

    # For each RA, get the associated prefixes and filter the DOIs by them
    # For each RA, a dict with a list of associated DOIs is created
    ra_list: List[Dict[str, List[str]]] = list(map(lambda reg_ag: {reg_ag: filter_dois_by_prefixes(dois,
                                                                                                   filter_prefixes_by_registration_agency(
                                                                                                       resolved_ras_for_doi_prefixes,
                                                                                                       reg_ag))}, ras))

    # Combine all dicts into one structure
    return reduce(lambda a, b: {**a, **b}, ra_list)


__all__ = ['RAs', 'group_dois_by_ra']
