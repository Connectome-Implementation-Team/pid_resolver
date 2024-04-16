## README

### Scope

This library facilitates the retrieval of structured metadata based on a collection of given DOIs.
It resolves DOIs to structured metadata using content negotiation taking into account different standards used by registration agencies.
It provides method to analyse this metadata and extract ORCIDs from it which can then also be resolved.

### Structure

The library consists of three modules:
1. `doi_ra_handler`: Given a collection of DOIs, groups them by registration agency based on the DOI prefix. 
2. `pid_resolver`: Given a collection of DOIs for a known registration agency, resolves them to structured metadata. 
   The serialisation format and data model depends on the registration agency.
   Resolved DOI metadata will be cached in the corresponding directory.
3. `pid_analyzer`: Given DOI metadata, provides methods to analyse this data and build a general structure called `PublicationInfo` 
   representing basic information such as title and author information including ORCID for a given DOI.   

### Usage

Here is some sample code how to use the library. You can install it from the local repo using `pip install -e <path/to/repo>`

```python
from pathlib import Path
from typing import Dict, List
import pid_resolver_lib
import asyncio


async def fetch_dois(dois: List[str]):
    # group the DOIs by registration agency
    org_dois: Dict = await pid_resolver_lib.group_dois_by_ra(dois)

    # for each RA, create a cache dir if not already existent
    for ra in org_dois.keys():

        # for each RA, resolve the DOIs
        if ra in pid_resolver_lib.RA_MIME:
            mime = pid_resolver_lib.RA_MIME[ra]
            await pid_resolver_lib.fetch_records(org_dois[ra], Path(ra), 'https://doi.org/', mime, 0)

    resolved_dois_crossref = pid_resolver_lib.analyze_dois(Path('Crossref'),
                                                           pid_resolver_lib.analyze_doi_record_crossref)

    resolved_dois_datacite = pid_resolver_lib.analyze_dois(Path('DataCite'),
                                                           pid_resolver_lib.analyze_doi_record_datacite)

    # combined resolved DOIs
    resolved_dois = {**resolved_dois_crossref, **resolved_dois_datacite}

    orcids = pid_resolver_lib.get_orcids_from_resolved_dois(resolved_dois)

    await pid_resolver_lib.fetch_records(orcids, Path('orcid'), 'https://orcid.org/', 'application/ld+json')

    dois_for_orcid = pid_resolver_lib.get_dois_per_orcid(Path('orcid'))

    new_dois = list(map(lambda doi: doi['dois'], dois_for_orcid))

    dois_to_harvest = [item for sublist in new_dois for item in sublist]

    return dois_to_harvest

async def main():
    dois = [
        "10.1371/journal.pone.0266659",
        "10.5061/dryad.cv86385c"
    ]

    dois_to_harvest = await fetch_dois(dois)

    for idx in range(1, 2):

        print(f'iteration {idx}')

        dois_to_harvest = await fetch_dois(dois_to_harvest)


asyncio.run(main())

```
