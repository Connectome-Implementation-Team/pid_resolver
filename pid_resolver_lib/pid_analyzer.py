from pathlib import Path
from lxml import etree  # type: ignore
from typing import List, Optional, Dict, Any, NamedTuple, cast, Callable, Union
import sys
from urllib.parse import unquote, quote
import os
import json


class AuthorInfo(NamedTuple):
    """
    Represents information about an author.
    """

    given_name: str  # 0
    family_name: str  # 1
    orcid: Optional[str]  # 2


class PublicationInfo(NamedTuple):
    """
    Represents a resolved DOI.

    # https://realpython.com/python-namedtuple/#namedtuple-vs-typingnamedtuple
    # requires Python 3.5
    """
    doi: str  # 0
    title: Optional[str]  # 1
    authors: List[AuthorInfo]  # 2


def analyze_author_info_datacite(author_info: Dict) -> AuthorInfo:
    """
    Transforms a JSON-LD item representing author information.

    @param author_info: Information about a publication's author.
    """

    given_name = author_info['givenName']
    family_name = author_info['familyName']

    # check for valid ORCID
    if '@id' in author_info and (
            'http://orcid.org/' in author_info['@id'] or 'https://orcid.org/' in author_info['@id']):
        orcid = author_info['@id'].replace('http://orcid.org/http', 'http').replace('http://',
                                                                                    'https://').strip()  # fix invalid ORCIDs, use https scheme for ORCID
    else:
        orcid = None

    return AuthorInfo(given_name=given_name, family_name=family_name, orcid=orcid)


def analyze_doi_record_datacite(cache_dir: Path, path: Path) -> Optional[PublicationInfo]:
    """
    Reads a DOI record (JSON-LD/schema.org) and transforms it to an item containing author information about a publication.

    @type cache_dir: Directory resolved DOIs have been written to.
    @param path: Path to read record from.
    """

    try:
        with open(path) as f:
            record = json.load(f)

        title: Optional[str] = record['name']
        author_info: Union[List[Dict], Dict] = record['author']

        if isinstance(author_info, List):
            authors_list: List[AuthorInfo] = list(map(analyze_author_info_datacite, author_info))
            return PublicationInfo(doi=unquote(str(Path(*path.parts[-2:]))), title=title, authors=authors_list)
        else:
            author_single: List[AuthorInfo] = [analyze_author_info_datacite(author_info)]
            return PublicationInfo(doi=unquote(str(Path(*path.parts[-2:]))), title=title, authors=author_single)

    except Exception as e:
        print(f'An error occurred in {path}: {e}', file=sys.stderr)
        return None


def analyze_author_info_crossref(creator: etree.Element, namespace_map: Any) -> Optional[AuthorInfo]:
    """
    Transforms an RDF/XML item representing creator information to author information.

    @param creator: DOI information about a creator.
    @param namespace_map: XML namespace information for the XML element.
    """

    given_name_ele: Optional[etree.Element] = creator.find('.//j.3:givenName', namespaces=namespace_map)
    family_name_ele: Optional[etree.Element] = creator.find('.//j.3:familyName', namespaces=namespace_map)
    orcid_ele: Optional[etree.Element] = creator.find('.//owl:sameAs', namespaces=namespace_map)

    if given_name_ele is not None and family_name_ele is not None:
        given_name = given_name_ele.text
        family_name = family_name_ele.text
        if orcid_ele is not None:
            orcid = orcid_ele.attrib.get('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource').replace('http://',
                                                                                                          'https://')  # use https scheme for ORCID
            return AuthorInfo(given_name=given_name, family_name=family_name, orcid=orcid)
        else:
            return AuthorInfo(given_name=given_name, family_name=family_name, orcid=None)

    # return None if insufficient information is provided.
    return None


def analyze_doi_record_crossref(cache_dir: Path, path: Path) -> Optional[PublicationInfo]:
    """
    Reads a DOI record (RDF/XML) and transforms it to an item containing author information about a publication.

    @type cache_dir: Directory resolved DOIs have been written to.
    @param path: Path to read record from.
    """

    try:
        tree = etree.parse(path)
        root = tree.getroot()

        title_ele: Optional[etree.Element] = root.find('.//rdf:Description/j.0:title', namespaces=root.nsmap)
        creators: List[etree.Element] = root.findall('.//j.0:creator/j.3:Person', namespaces=root.nsmap)

        if title_ele is not None:
            title = title_ele.text
        else:
            title = None

        authors: List[Optional[AuthorInfo]] = list(
            map(lambda creator: analyze_author_info_crossref(creator, root.nsmap), creators))

        # filter out None values
        authors_filtered = list(filter(lambda auth: auth is not None, authors))

        # https://stackoverflow.com/questions/67274469/mypy-types-and-optional-filtering
        return PublicationInfo(doi=unquote(str(Path(*path.parts[-2:]))), title=title, authors=cast(List[AuthorInfo], authors_filtered))
    except Exception as e:
        print(f'An error occurred in {path}: {e}', file=sys.stderr)
        return None


def analyze_dois(cache_dir: Path, analyzer: Callable[[Path, Path], Optional[PublicationInfo]]) -> Dict[
    str, PublicationInfo]:
    """
    Reads resolved DOIs from the cache and returns a dict indexed by DOI (without base URL).

    @param cache_dir: Directory resolved DOIs have been written to.
    @param analyzer: Function that parses the metadata resolved for a DOI and transforms it to a PublicationInfo.
    """

    records_cache_file = Path('resolved_dois.json')

    # check if cache_file exists
    if os.path.isfile(records_cache_file):
        cached_records = parse_resolved_dois_from_json(records_cache_file)
        # move current cache file (backup)
        os.rename(records_cache_file, f'{records_cache_file}.bkp')
    else:
        cached_records = {}

    files: List[Path] = list(Path(cache_dir).rglob('*/*'))
    sorted_files: List[Path] = sorted(files)

    # only analyze those DOIs from cache dir that were not contained in cache file
    # quote cached DOIs since paths are quoted
    dois_to_analyze = set(sorted_files) - set(map(lambda doi: cache_dir / Path(doi), cached_records.keys()))

    print('dois to analyze ', len(dois_to_analyze))

    records: List[Optional[PublicationInfo]] = list(map(lambda file: analyzer(cache_dir, file), dois_to_analyze))

    # filter out None values
    records_non_empty: List[PublicationInfo] = cast(List[PublicationInfo],
                                                    list(filter(lambda rec: rec is not None, records)))

    # https://stackoverflow.com/questions/1993840/map-list-onto-dictionary
    # return dict indexed by DOI
    records_as_dict = dict(map(lambda x: (x[0], x), records_non_empty))

    # https://www.geeksforgeeks.org/python-merging-two-dictionaries/
    combined_records = {**cached_records, **records_as_dict}

    # write dois to new cache file
    with open(records_cache_file, 'w') as f:
        f.write(json.dumps(combined_records))

    return combined_records


def parse_resolved_dois_from_json(resolved_dois_json: Path) -> Dict[str, PublicationInfo]:
    """
    Transform a JSON representation to a Dict of PublicationInfo.

    @param resolved_dois_json: Path to JSON representing resolved DOIs.
    """

    with open(resolved_dois_json) as f:
        resolved_dois = json.load(f)

    doi_items = resolved_dois.items()

    '''
    dois_items is an iterable of pairs: (doi, pub and author info), e.g.,

    "10.3390/math8040648": [
    "10.3390/math8040648",
    "Supported Evacuation for Disaster Relief through Lexicographic Goal Programming", # [1][1]
    [ # [1][2]
      [ 
        "Begoña",
        "Vitoriano",
        "https://orcid.org/0000-0002-3356-6049"
      ],
      [
        "Gregorio",
        "Tirado",
        "https://orcid.org/0000-0002-1871-7822"
      ],
      [
        "M. Teresa",
        "Ortuño",
        "https://orcid.org/0000-0002-5568-9496"
      ],
      [
        "Inmaculada",
        "Flores",
        "https://orcid.org/0000-0002-8582-3633"
      ]
    ]
  ] 
    '''
    mapped_items = map(lambda doi: [doi[0], PublicationInfo(doi=doi[0], title=doi[1][1], authors=list(
        map(lambda auth: AuthorInfo(given_name=auth[0], family_name=auth[1], orcid=auth[2]), doi[1][2])))],
                       doi_items)

    # recreate Dict[str, PublicationInfo] from JSON
    return dict(mapped_items)


def get_orcids_from_resolved_dois(dois: Dict[str, PublicationInfo]) -> List[str]:
    """
    Extracts ORCIDs from resolved DOIs and returns ORCIDs that are contained in the author information.

    @param dois: Resolved DOIs.
    """

    auth_info: List[List[AuthorInfo]] = list(map(lambda doi: doi.authors, list(dois.values())))

    auth_info_flattened: List[AuthorInfo] = [item for sublist in auth_info for item in sublist]

    orcids = list(map(lambda auth: auth.orcid, auth_info_flattened))

    # remove duplicates
    return cast(List[str], list(set(filter(lambda auth: auth is not None, orcids))))


def analyze_orcid_record(orcid: str) -> Optional[Dict]:
    """
    Transform a resolved ORCID into a dict.

    @param orcid: Path to the resolved ORCID.
    """

    try:
        with open(orcid) as f:
            rec = json.load(f)

        return {
            '@id': f'https://data.connectome.ch/orcid/person/{rec["@id"][18:]}',
            '@type': 'Person',
            'givenName': rec['givenName'],
            'familyName': rec['familyName'],
            'name': f'{rec["givenName"]} {rec["familyName"]}',
            'sameAs': {'@id': rec['@id'].replace('http://', 'https://')},  # normalize URL
        }
    except Exception as e:
        print(f'An error occurred in ORCID {orcid}: {e}', file=sys.stderr)
        return None


def analyze_orcids(cache_dir: Path) -> Dict:
    """
    Analyze resolved ORCIDs.

    @param cache_dir: Directory resolved ORCIDs have been written.
    """

    files: List[str] = os.listdir(cache_dir)
    sorted_files: List[str] = sorted(files)

    print(len(sorted_files))

    records = list(map(lambda file: analyze_orcid_record(f'{cache_dir}/{file}'), sorted_files))

    graph = {
        '@context': {'@vocab': 'http://schema.org/'},
        '@graph': list(filter(lambda rec: rec is not None, records))
    }

    return graph


__all__ = ['PublicationInfo', 'analyze_dois', 'analyze_doi_record_crossref', 'analyze_doi_record_datacite', 'get_orcids_from_resolved_dois', 'analyze_orcids']