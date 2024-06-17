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
import logging
import sys
import getopt
import os
from pathlib import Path
from typing import Dict, List
import asyncio
import json
from .doi_ra_handler import group_dois_by_ra, RAs
from .pid_resolver import fetch_records
from .pid_analyzer import analyze_dois, analyze_doi_record_crossref, analyze_doi_record_datacite, get_orcids_from_resolved_dois, get_dois_per_orcid

logging.basicConfig(filename='pid_resolver.log',
                    filemode='a',
                    format='%(module)s %(levelname)s: %(asctime)s %(message)s',
                    datefmt='%H:%M:%S',
                    encoding='utf-8',
                    level=logging.DEBUG)

logger = logging.getLogger(__name__)


def normalize_doi(doi: str) -> str:
    # remove backslashes
    return doi.replace('\\', '')


async def fetch_dois(dois: List[str], ) -> List[str]:
    if len(dois) == 0:
        return []

    # group the DOIs by registration agency
    org_dois: Dict = await group_dois_by_ra(dois)

    # for each RA, create a cache dir if not already existent
    for ra in org_dois.keys():

        # for each RA, resolve the DOIs
        if ra in RAs:
            mime: str = str(RAs[ra]['mime'])
            sleep: int = int(RAs[ra]['sleep'])
            await fetch_records(org_dois[ra], Path(ra), 'https://doi.org', mime, sleep)

    resolved_dois_crossref = analyze_dois(Path('Crossref'),
                                                           analyze_doi_record_crossref)

    resolved_dois_datacite = analyze_dois(Path('DataCite'),
                                                           analyze_doi_record_datacite)

    # combined resolved DOIs
    resolved_dois = {**resolved_dois_crossref, **resolved_dois_datacite}

    with open('results.json', 'w') as f:
        f.write(json.dumps(resolved_dois))

    orcids = get_orcids_from_resolved_dois(resolved_dois)

    await fetch_records(orcids, Path('orcid'), 'https://orcid.org', 'application/ld+json')

    dois_for_orcid = get_dois_per_orcid(Path('orcid'))

    new_dois = list(map(lambda doi: doi['dois'], dois_for_orcid))

    dois_to_harvest = [item for sublist in new_dois for item in sublist]

    return list(map(normalize_doi, dois_to_harvest))


async def start(dois_to_harvest: List[str], number_of_iterations: int):

    # range's end is exclusive
    for idx in range(1, number_of_iterations+1):
        print(f'iteration {idx}')

        dois_to_harvest = await fetch_dois(dois_to_harvest)


def usage() -> None:
    print('Usage: ' + sys.argv[0] + ' -i <number_of_iterations> -d <doi_input_file>')
    print('Resolves DOIs and related ORCIDs.')
    print('-i <number_of_iterations>: positive integer')
    print('-d <doi_input_file>: path to JSON file containing an array of DOIs, e.g. ["10.1007/978-3-031-47243-5_6"]')
    exit(1)


def main():

    iterations = 0
    dois = []

    argv = sys.argv[1:]

    # no args given
    if len(argv) == 0:
        usage()

    try:
        opts, args = getopt.getopt(argv, "i:d:")

        for opt, arg in opts:
            if opt in ['-i']:
                if arg.isnumeric():
                    iterations = int(arg)
                else:
                    print('-i is expected to be a positive integer', file=sys.stderr)
                    usage()
            elif opt in ['-d']:
                doi_file = arg
                if os.path.isfile(doi_file):
                    with open(doi_file) as f:
                        dois = json.load(f)
                else:
                    print('-d is expected to be a JSON file name', file=sys.stderr)
                    usage()


    except Exception as err:
        print(err, file=sys.stderr)
        usage()

    # check for empty values (still initialised to empty strings)
    if not iterations or not dois:
        usage()

    asyncio.run(start(dois, iterations))
