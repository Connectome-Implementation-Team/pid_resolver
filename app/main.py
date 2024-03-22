#!/usr/bin/env python3
from pathlib import Path
from typing import List, Dict
import getopt
import sys
import os
import asyncio
import json
from utlis.pid_analyzer import analyze_dois, analyze_doi_record_crossref, analyze_doi_record_datacite
from utlis.pid_resolver import get_registration_agency_prefixes, resolve_registration_agency_prefixes, \
    filter_prefixes_by_registration_agency, filter_dois_by_prefixes, fetch_records


BASE_PATH = os.environ['BASE_PATH']
path = Path(BASE_PATH)


''''
print('hello')
print(sys.argv)

with open('/data/test.txt') as f:
    print(f.read())
'''

def usage() -> None:
    print(f'Usage: {sys.argv[0]} -d <dois.json> [-o orcids.json]')
    print('Resolves DOIs provided in <dois.json> (JSON array of DOIs without base URL).')
    print('Resolves ORCIDs provided in <orcids.json> (JSON array of ORCIDs without base URL).')
    exit(1)

async def main():
    dois_file = ''
    orcids_file = ''

    argv = sys.argv[1:]

    # no args given
    if len(argv) == 0:
        usage()

    try:
        opts, args = getopt.getopt(argv, "d:o:")
    except getopt.GetoptError as err:
        print(err)
        usage()

    for opt, arg in opts:
        if opt in ['-d']:
            dois_file = arg
        elif opt in ['-o']:
            orcids_file = arg

    # check for empty values (still initialised to empty strings)
    if not dois_file:
        usage()

    with open(Path(BASE_PATH) / dois_file) as f:
        dois = json.load(f)

    doi_prefixes: List[str] = get_registration_agency_prefixes(dois)

    resolved_ras_for_doi_prefixes: List[Dict[str, str]] = await resolve_registration_agency_prefixes(doi_prefixes)

    # Crossref

    crossref_doi_prefixes = filter_prefixes_by_registration_agency(resolved_ras_for_doi_prefixes, 'Crossref')

    crossref_dois = filter_dois_by_prefixes(dois, crossref_doi_prefixes)

    await fetch_records(crossref_dois, path / 'crossref_dois', 'https://doi.org/', 'application/rdf+xml')

    resolved_dois_crossref = analyze_dois(path, path / 'crossref_dois', analyze_doi_record_crossref)

    # DataCite

    datacite_doi_prefixes = filter_prefixes_by_registration_agency(resolved_ras_for_doi_prefixes, 'DataCite')

    datacite_dois = filter_dois_by_prefixes(dois, datacite_doi_prefixes)

    await fetch_records(datacite_dois, path / 'datacite_dois', 'https://doi.org/', 'application/ld+json', 120)

    resolved_dois_datacite = analyze_dois(path, path /'datacite_dois', analyze_doi_record_datacite)

asyncio.run(main())
