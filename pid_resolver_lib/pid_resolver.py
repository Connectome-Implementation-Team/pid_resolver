from pathlib import Path
import jq  # type: ignore
import sys
from typing import List, Union, Dict, NamedTuple, Optional, cast
import aiohttp
from aiohttp import ClientSession, TCPConnector, ClientTimeout
import asyncio
import urllib.parse
import os

contact = ''

class ResolvedRecord(NamedTuple):
    """
    Represents a resolved record (DOI, ORCID).

    # https://realpython.com/python-namedtuple/#namedtuple-vs-typingnamedtuple
    # requires Python 3.5
    """
    rec_id: str # 0
    content: str # 1


def get_registration_agency_prefixes(dois: List[str]) -> List[str]:
    """
    Given a list of DOIS, returns their agency prefixes (no duplicates).

    :param dois: A list of DOIs without base URL, e.g., 10.1016/j.jtherbio.2015.06.009.
    """
    agencies: List[str] = jq.compile('[.[] | .[0:index("/")]] | unique').input_value(dois).first()

    return agencies


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


async def _make_registration_agency_prefix_request(session: ClientSession, doi_prefix: str) -> Union[Dict, None]:
    """
    Given a DOI prefix, fetches information about the RA.

    @param session: The aiohttp session to be used.
    @param doi_prefix: The DOI prefix to be fetched.
    """

    base_url = 'https://doi.org/ra/'

    try:
        async with session.get(f'{base_url}/{doi_prefix}') as request:
            return await request.json()

    except Exception as e:
        print('DOI Error ' + str(e), file=sys.stderr)
        return None


async def resolve_registration_agency_prefixes(doi_prefixes: List[str]) -> List[Dict[str, str]]:
    """
    Given a list of DOI prefixes, resolves them to get the registration agencies.

    @param doi_prefixes: DOI prefixes to be resolved.
    """

    conn = TCPConnector(limit=10)
    # set raise_for_status
    time_out = ClientTimeout(total=60 * 60 * 24)
    async with aiohttp.ClientSession(connector=conn, raise_for_status=True, timeout=time_out) as session:

        requests = [_make_registration_agency_prefix_request(session, doi_prefix) for doi_prefix in doi_prefixes]

        results = await asyncio.gather(*requests)

        # https://stackoverflow.com/questions/952914/how-do-i-make-a-flat-list-out-of-a-list-of-lists
        # TODO: handle error cases (None is returned)
        return [item for sublist in cast(List[List[Dict]], results) for item in sublist]


async def _make_doi_request(session: ClientSession, doi: str, base_url: str, accept_header: str) -> Optional[ResolvedRecord]:
    """
    Given a DOI, resolves it using content negotiation.

    @param session:  The aiohttp session to be used.
    @param doi: The DOI to be resolved.
    """

    headers = {
        'Accept': accept_header,
        'User-Agent': f'Connectome (https://connectome.ch; mailto:{contact})'
    }

    try:
        async with session.get(f'{base_url}/{doi}', headers=headers) as request:
            return ResolvedRecord(doi, await request.text())

    except Exception as e:
        print('DOI Error ' + str(e), file=sys.stderr)
        return None


async def _fetch_doi_batch(dois: List[str], base_url: str, accept_header) -> List[ResolvedRecord]:
    """
    Given a batch of DOIs, fetches them.

    @param dois: List of DOIs.
    """

    conn = TCPConnector(limit=5)
    # set raise_for_status
    time_out = ClientTimeout(total=60 * 60 * 24)
    async with aiohttp.ClientSession(connector=conn, raise_for_status=True, timeout=time_out) as session:

        requests = [_make_doi_request(session, doi, base_url, accept_header) for doi in dois]

        results = await asyncio.gather(*requests)

        # filter out None values (failed requests)
        return cast(List[ResolvedRecord], list(filter(lambda res: res is not None, results)))


async def fetch_records(records: List[str], cache_dir: Path, base_url: str, accept_header: str, sleep_per_batch: int = 0) -> None:
    """
    Fetches a list of records (DOIs, ORCIDs) and writes them to the cache directory.
    Performs fetching in batches of size 500 requests each.

    @param records: Records to be fetched.
    @param cache_dir: Directory the results are written to
    @param base_url: Base URL of the items to be fetched, e.g., https://doi.org.
    @param accept_header: HTTP accept header for content negotiation.
    @param sleep_per_batch: Sleep in seconds after each batch to respect rate limits, if any. See https://support.datacite.org/docs/is-there-a-rate-limit-for-making-requests-against-the-datacite-apis.
    """

    dois_deduplicated = list(set(records))

    # check if a DOI is already in the cache
    dois_not_cached = list(
        filter(lambda doi: not os.path.isfile(f'{cache_dir}/{urllib.parse.quote(doi, safe="")}'),
               dois_deduplicated))

    print('fetching number of records: ', len(dois_not_cached))

    offset = 0
    batch_size = 500
    last_run = False

    while not last_run:

        limit = offset + batch_size

        if limit > len(dois_not_cached):
            limit = len(dois_not_cached)
            last_run = True

        print('fetching batch: ',  offset, limit)

        results = await _fetch_doi_batch(dois_not_cached[offset:limit], base_url, accept_header)

        # store DOIs as files
        for res in results:
            try:
                with open(f'{cache_dir}/{urllib.parse.quote(res.rec_id, safe="")}', 'w') as f:
                    f.write(res.content)
            except Exception as e:
                print(f'An error occurred when writing record {res}: {e}')


        # sleep because of rate limits
        print('pausing')
        await asyncio.sleep(sleep_per_batch)
        print('working')

        offset = offset + batch_size

__all__ = ['get_registration_agency_prefixes', 'filter_prefixes_by_registration_agency', 'filter_dois_by_prefixes', 'resolve_registration_agency_prefixes', 'fetch_records']