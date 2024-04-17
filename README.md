## README

### Scope

This library facilitates the retrieval of structured metadata based on a collection of given DOIs.
It resolves DOIs to structured metadata using content negotiation taking into account different standards used by registration agencies.
It provides method to analyse this metadata and extract ORCIDs from it which can then also be resolved.

### Use Cases

The use cases range from very simple to more complex ones.
Initially, this library was designed to resolve DOIs to structured metadata to obtain ORCIDs for a given publication.
Then more functionality was added to extract DOIs from ORCID profiles to continue the process.
This means that given some DOIs as a starting point, this library can be used like a crawler following the connection between DOIs and ORCIDs.
From a few DOIs, the co-author network can be constructed by combining DOI and ORCID metadata, using DOIs and ORCIDs as identifiers. 

### Structure

The library consists of three modules:
1. `doi_ra_handler`: Given a collection of DOIs, groups them by registration agency based on the DOI prefix. 
2. `pid_resolver`: Given a collection of DOIs for a known registration agency, resolves them to structured metadata. 
   The serialisation format and data model depends on the registration agency.
   Resolved DOI metadata will be cached in the corresponding directory.
3. `pid_analyzer`: Given DOI metadata, provides methods to analyse this data and build a general structure called `PublicationInfo` 
   representing basic information such as title and author information including ORCID for a given DOI.

### Caching

All resolved DOIs and ORCIDs are cached. For each registration agency (RA), a separate cache is used.

### Licensing

This library is licensed under the terms defined in [LICENSE](LICENSE).
Software dependencies are explicitly mentioned in the [dependencies document](DEPENDENCIES.md).


### Usage

Here is some sample code how to use the library. You can install it from the local repo using `pip install -e <path/to/repo>`

The code sample defines two methods:
- `fetch_dois(dois: List[str])`: fetches structured metadata for the given DOIs. Then, ORCIDs are extracted from this metadata, if any are given. These ORCIDs are then resolved. From these ORCIDs, the linked DOIs are extracted for the next iteration. 
- `main()`: inits the process and defines the number of iterations. 

The process in `main` starts with two given DOIs: one from Crossref and one from DataCite to illustrate the process for both registration agencies (RAs).
It calls `fetch_dois` with the two given DOIs. The method returns the DOIs it obtained from the linked ORCID profiles which are used for the next iteration and so on.

```python
from pathlib import Path
from typing import Dict, List
import pid_resolver_lib
import asyncio
import json

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

    with open('results.json', 'w') as f:
       f.write(json.dumps(resolved_dois))
    
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
