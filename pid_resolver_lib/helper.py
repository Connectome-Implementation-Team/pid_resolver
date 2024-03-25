from typing import List, Dict
from .pid_resolver import get_registration_agency_prefixes, resolve_registration_agency_prefixes, \
    filter_prefixes_by_registration_agency, filter_dois_by_prefixes
from functools import reduce

RA_MIME = {
    'DataCite': 'application/ld+json',
    'Crossref': 'application/rdf+xml',
    'mEDRA': ' application/rdf+xml'
}


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
