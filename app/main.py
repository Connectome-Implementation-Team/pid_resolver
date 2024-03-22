#!/usr/bin/env python3
from pathlib import Path
from typing import List

import jq
import getopt
import sys
import os
import asyncio
import json
from utlis.pid_resolver import get_registration_agency_prefixes
BASE_PATH = os.environ['BASE_PATH']


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

    print(len(dois))

    doi_prefixes: List[str] = get_registration_agency_prefixes(dois)

    print(doi_prefixes, len(doi_prefixes))
    print('doniiii')

asyncio.run(main())
