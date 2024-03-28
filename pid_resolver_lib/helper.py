from typing import List, Dict, Union, cast
from functools import reduce
import asyncio
from aiohttp import ClientSession, TCPConnector, ClientTimeout
import sys
import jq # type: ignore


RA_MIME = {
    'DataCite': 'application/ld+json',
    'Crossref': 'application/rdf+xml',
    'mEDRA': ' application/rdf+xml'
}


def get_registration_agency_prefixes(dois: List[str]) -> List[str]:
    """
    Given a list of DOIS, returns their agency prefixes (no duplicates).

    :param dois: A list of DOIs without base URL, e.g., 10.1016/j.jtherbio.2015.06.009.
    """
    agencies: List[str] = jq.compile('[.[] | .[0:index("/")]] | unique').input_value(dois).first()

    return agencies


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
    async with ClientSession(connector=conn, raise_for_status=True, timeout=time_out) as session:

        requests = [_make_registration_agency_prefix_request(session, doi_prefix) for doi_prefix in doi_prefixes]

        results = await asyncio.gather(*requests)

        # https://stackoverflow.com/questions/952914/how-do-i-make-a-flat-list-out-of-a-list-of-lists
        # TODO: handle error cases (None is returned)
        return [item for sublist in cast(List[List[Dict]], results) for item in sublist]


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

    # get prefixes from DOIs
    doi_prefixes: List[str] = get_registration_agency_prefixes(dois)

    # For each prefix, resolve its RA.
    resolved_ras_for_doi_prefixes: List[Dict[str, str]] = await resolve_registration_agency_prefixes(doi_prefixes)

    # Make a list of available RAs
    ras = set(map(lambda ra: ra['RA'], resolved_ras_for_doi_prefixes))

    # For each RA, get the associated prefixes and filter the DOIs by them
    # For each RA, a dict with a list of associated DOIs is created
    ra_list: List[Dict[str, List[str]]] = list(map(lambda reg_ag: {reg_ag: filter_dois_by_prefixes(dois,
                                                                                                   filter_prefixes_by_registration_agency(
                                                                                                       resolved_ras_for_doi_prefixes,
                                                                                                       reg_ag))}, ras))

    # Combine all dicts into one structure
    return reduce(lambda a, b: {**a, **b}, ra_list)


__all__ = ['RA_MIME', 'group_dois_by_ra']
