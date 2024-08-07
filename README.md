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

The library offers a [CLI version](pid_resolver_lib/cli.py) that can be used as follows:
- Create a virtual environment, see https://docs.python.org/3/tutorial/venv.html#creating-virtual-environments
- Install the library `pip install -e <path/to/local/repo>` (from locally checked out repo).
- Create a JSON file containing one or several DOIs, e.g., a file `dois.json` with the contents `["10.1007/978-3-031-47243-5_6"]`. Note that DOIs are **without** base path `https://doi.org/`.
- Use the script as follows: `pid_resolver -i 2 -d dois.json`
- Run `pid_resolver` for usage instructions.

The process will start with the given DOIs and perform as many iterations as configured.
The results of the analysis will be written to `results.json` (working directory). 
The cache directories will be created in the working directory.  

