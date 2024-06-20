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
from pathlib import Path
from lxml import etree  # type: ignore
from typing import List, Optional, Dict, Any, NamedTuple, cast, Callable, Union, Tuple
import json
import jq # type: ignore
from .cache_handler import get_keys, read_from_cache

ANALYZER = 'ANALYZER:'

logger = logging.getLogger(__name__)

class OrcidProfile(NamedTuple):
    """
    Represents information about an ORCID profile.
    """

    id: str # 0
    given_name: str # 1
    family_name: str # 2


class AuthorInfo(NamedTuple):
    """
    Represents information about an author.
    """

    given_name: str  # 0
    family_name: str  # 1
    orcid: Optional[str]  # 2
    origin_orcid: Optional[str] # 3


class PublicationInfo(NamedTuple):
    """
    Represents a resolved DOI.

    # https://realpython.com/python-namedtuple/#namedtuple-vs-typingnamedtuple
    # requires Python 3.5
    """
    doi: str  # 0
    title: Optional[str]  # 1
    authors: List[AuthorInfo]  # 2


def _get_orcid_id_from_url(orcid_url: str) -> str:
    return orcid_url.replace('http://orcid.org/http', 'http').replace('http://',
                                                      'https://').strip()[len('https://orcid.org/'):]  # fix invalid ORCIDs, use https scheme for ORCID


def _match_name_with_orcid_profile(orcid_info: List[OrcidProfile], given_name: str, family_name: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Given a list of ORCID profiles for a DOI, filters them by name.

    @param orcid_info: Information extracted from the ORCID profiles.
    @param given_name: The author's first name.
    @param family_name: The author's last name.
    """

    # match ORCID profiles by name
    author_orcid = list(
        filter(lambda orcid: orcid.family_name == family_name and orcid.given_name == given_name, orcid_info))

    if len(author_orcid) == 1:
        # get ORCID ID from URL
        orcid = author_orcid[0].id.rsplit('/', 1)[-1]
        origin_orcid = 'orcid'
    else:
        orcid = None
        origin_orcid = None

    return orcid, origin_orcid


def analyze_author_info_datacite(author_info: Dict, orcid_info: List[OrcidProfile]) -> AuthorInfo:
    """
    Transforms a JSON-LD item representing author information.

    @param author_info: Information about a publication's author.
    @param orcid_info: ORCID profiles associated with the current DOI/publication.
    """

    given_name = author_info['givenName']
    family_name = author_info['familyName']

    orcid: Optional[str]
    origin_orcid: Optional[str]
    # check for valid ORCID
    if '@id' in author_info and (
            'http://orcid.org/' in author_info['@id'] or 'https://orcid.org/' in author_info['@id']):
        orcid = _get_orcid_id_from_url(author_info['@id'])
        origin_orcid = 'doi'
    else:
        orcid, origin_orcid = _match_name_with_orcid_profile(orcid_info, given_name, family_name)

    return AuthorInfo(given_name=given_name, family_name=family_name, orcid=orcid, origin_orcid=origin_orcid)


def analyze_doi_record_datacite(cache_dir: Path, doi: str, orcid_info: Dict[str, List[OrcidProfile]]) -> Optional[PublicationInfo]:
    """
    Reads a DOI record (JSON-LD/schema.org) and transforms it to an item containing author information about a publication.

    @type cache_dir: Directory resolved DOIs have been written to.
    @param doi: Path to read record from.
    @param orcid_info: ORCID profiles organized by DOI.
    """

    try:
        record = json.loads(read_from_cache(doi, cache_dir))

        title: Optional[str] = record['name']
        author_info: Union[List[Dict], Dict] = record['author']

        if doi in orcid_info:
            orcid_author_info = orcid_info[doi]
        else:
            orcid_author_info = []

        if isinstance(author_info, List):
            authors_list: List[AuthorInfo] = list(map(lambda author: analyze_author_info_datacite(author, orcid_author_info), author_info))
            return PublicationInfo(doi=doi, title=title, authors=authors_list)
        else:
            author_single: List[AuthorInfo] = [analyze_author_info_datacite(author_info, orcid_author_info)]
            return PublicationInfo(doi=doi, title=title, authors=author_single)

    except Exception as e:
        logging.error(f'{ANALYZER} An error occurred in {doi}: {e}')
        return None


def analyze_author_info_crossref(creator: etree.Element, namespace_map: Any, orcid_info: List[OrcidProfile]) -> Optional[AuthorInfo]:
    """
    Transforms an RDF/XML item representing creator information to author information.

    @param creator: DOI information about a creator.
    @param namespace_map: XML namespace information for the XML element.
    @param orcid_info: ORCID profiles associated with the current DOI/publication.
    """

    given_name_ele: Optional[etree.Element] = creator.find('.//j.3:givenName', namespaces=namespace_map)
    family_name_ele: Optional[etree.Element] = creator.find('.//j.3:familyName', namespaces=namespace_map)
    orcid_ele: Optional[etree.Element] = creator.find('.//owl:sameAs', namespaces=namespace_map)

    orcid: Optional[str]
    origin_orcid: Optional[str]

    if given_name_ele is not None and family_name_ele is not None:
        given_name = given_name_ele.text
        family_name = family_name_ele.text
        if orcid_ele is not None:
            orcid = _get_orcid_id_from_url(orcid_ele.attrib.get('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource'))
            return AuthorInfo(given_name=given_name, family_name=family_name, orcid=orcid, origin_orcid='doi')
        else:
            orcid, origin_orcid = _match_name_with_orcid_profile(orcid_info, given_name, family_name)

            return AuthorInfo(given_name=given_name, family_name=family_name, orcid=orcid, origin_orcid=origin_orcid)

    # return None if insufficient information is provided.
    return None


def analyze_doi_record_crossref(cache_dir: Path, doi: str, orcid_info: Dict[str, List[OrcidProfile]]) -> Optional[PublicationInfo]:
    """
    Reads a DOI record (RDF/XML) and transforms it to an item containing author information about a publication.

    @type cache_dir: Directory resolved DOIs have been written to.
    @param doi: Path to read record from.
    @param orcid_info: ORCID profiles organized by DOI.
    """

    try:
        rec_str = read_from_cache(doi, cache_dir)

        root = etree.fromstring(rec_str)

        title_ele: Optional[etree.Element] = root.find('.//rdf:Description/j.0:title', namespaces=root.nsmap)
        creators: List[etree.Element] = root.findall('.//j.0:creator/j.3:Person', namespaces=root.nsmap)

        if title_ele is not None:
            title = title_ele.text
        else:
            title = None

        if doi in orcid_info:
            orcid_author_info: List[OrcidProfile] = orcid_info[doi]
        else:
            orcid_author_info = []

        authors: List[Optional[AuthorInfo]] = list(
            map(lambda creator: analyze_author_info_crossref(creator, root.nsmap, orcid_author_info), creators))

        # filter out None values
        authors_filtered = list(filter(lambda auth: auth is not None, authors))

        # https://stackoverflow.com/questions/67274469/mypy-types-and-optional-filtering
        return PublicationInfo(doi=doi, title=title, authors=cast(List[AuthorInfo], authors_filtered))
    except Exception as e:
        logging.error(f'{ANALYZER} An error occurred in {doi}: {e}')
        return None


def analyze_author_info_medra(creator: etree.Element, namespace_map: Any, orcid_info: List[OrcidProfile]) -> Optional[AuthorInfo]:
    given_name_ele: Optional[etree.Element] = creator.find('.//NamesBeforeKey', namespaces=namespace_map)
    family_name_ele: Optional[etree.Element] = creator.find('.//KeyNames', namespaces=namespace_map)
    orcid_ele: Optional[etree.Element] = creator.find('.//NameIdentifier/IDValue', namespaces=namespace_map)

    orcid: Optional[str]
    origin_orcid: Optional[str]

    if given_name_ele is not None and family_name_ele is not None:
        given_name = given_name_ele.text.strip()
        family_name = family_name_ele.text.strip()

        if orcid_ele is not None:
            orcid = _get_orcid_id_from_url(orcid_ele.text)
            return AuthorInfo(given_name=given_name, family_name=family_name, orcid=orcid, origin_orcid='doi')
        else:
            orcid, origin_orcid = _match_name_with_orcid_profile(orcid_info, given_name, family_name)
            return AuthorInfo(given_name=given_name, family_name=family_name, orcid=orcid, origin_orcid=origin_orcid)

    # return None if insufficient information is provided.
    return None


def analyze_doi_record_medra(cache_dir: Path, doi: str, orcid_info: Dict[str, List[OrcidProfile]]) -> Optional[PublicationInfo]:
    try:
        rec_str = read_from_cache(doi, cache_dir)

        # encode to bytes because of Unicode strings with encoding declaration
        root = etree.fromstring(rec_str.encode())

        title_ele: Optional[etree.Element] = root.find('.//ContentItem/Title/TitleText', namespaces=root.nsmap)

        if title_ele is not None:
            title = title_ele.text.strip()
        else:
            title = None

        if doi in orcid_info:
            orcid_author_info: List[OrcidProfile] = orcid_info[doi]
        else:
            orcid_author_info = []

        creators: List[etree.Element] = root.findall('.//ContentItem/Contributor', namespaces=root.nsmap)

        authors: List[Optional[AuthorInfo]] = list(
            map(lambda creator: analyze_author_info_medra(creator, root.nsmap, orcid_author_info), creators))

        # filter out None values
        authors_filtered = list(filter(lambda auth: auth is not None, authors))

        # https://stackoverflow.com/questions/67274469/mypy-types-and-optional-filtering
        return PublicationInfo(doi=doi, title=title, authors=cast(List[AuthorInfo], authors_filtered))

    except Exception as e:
        logging.error(f'{ANALYZER} An error occurred in {doi}: {e}')

    return None



def analyze_dois(cache_dir: Path, analyzer: Callable[[Path, str, Dict], Optional[PublicationInfo]]) -> Dict[
    str, PublicationInfo]:
    """
    Reads resolved DOIs from the cache and returns a dict indexed by DOI (without base URL).

    @param cache_dir: Directory resolved DOIs have been written to.
    @param analyzer: Function that parses the metadata resolved for a DOI and transforms it to a PublicationInfo.
    """

    '''
    records_cache_file = Path('resolved_dois.json')

    # check if cache_file exists
    if os.path.isfile(records_cache_file):
        cached_records = parse_resolved_dois_from_json(records_cache_file)
        # move current cache file (backup)
        os.rename(records_cache_file, f'{records_cache_file}.bkp')
    else:
        cached_records = {}
    '''


    '''
    files: List[Path] = list(Path(cache_dir).rglob('*/*'))
    sorted_files: List[Path] = sorted(files)
    '''

    # only analyze those DOIs from cache dir that were not contained in cache file
    # quote cached DOIs since paths are quoted

    # dois_to_analyze = set(sorted_files) - set(map(lambda doi: cache_dir / Path(doi), cached_records.keys()))


    # dois_to_analyze = list(set(cache_ref.iterkeys() - cached_records.keys()))
    dois_to_analyze = list(get_keys(cache_dir))

    #print('dois to analyze ', len(dois_to_analyze), dois_to_analyze)

    # check if additional ORCIDs could be added from cached ORCID profiles
    dois_per_orcid: List[Dict] = get_dois_per_orcid(Path('orcid'))
    orcids_grouped_by_doi: Dict[str, List[OrcidProfile]] = group_orcids_per_doi(dois_per_orcid)

    # print(grouped)

    records: List[Optional[PublicationInfo]] = list(map(lambda file: analyzer(cache_dir, file, orcids_grouped_by_doi), dois_to_analyze))

    # filter out None values
    records_non_empty: List[PublicationInfo] = cast(List[PublicationInfo],
                                                    list(filter(lambda rec: rec is not None, records)))

    # https://stackoverflow.com/questions/1993840/map-list-onto-dictionary
    # return dict indexed by DOI
    records_as_dict = dict(map(lambda x: (x[0], x), records_non_empty))

    # https://www.geeksforgeeks.org/python-merging-two-dictionaries/
    #combined_records = {**cached_records, **records_as_dict}

    # write dois to new cache file
    '''
    with open(records_cache_file, 'w') as f:
        f.write(json.dumps(combined_records))
    '''

    #return combined_records
    return records_as_dict


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
        map(lambda auth: AuthorInfo(given_name=auth[0], family_name=auth[1], orcid=auth[2], origin_orcid=auth[3]), doi[1][2])))],
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


def _parse_orcid_json(orcid_json: str, orcid: str)-> Optional[Dict]:
    try:
        return json.loads(orcid_json)
    except Exception as e:
        logging.error(f'{ANALYZER} An error occurred when parsing ORCID JSON for {orcid}: {e}')
        return None


def get_dois_per_orcid(cache_dir: Path) -> List[Dict]:
    """
    Collects cached ORCID profiles and organizes them as a list of objects with id and DOIs.

    @param cache_dir: The ORCID cache directory.
    """

    orcids = list(get_keys(cache_dir))

    orcid_profiles_maybe: List[Optional[Dict]] = list(map(lambda orcid: _parse_orcid_json(read_from_cache(orcid, cache_dir), orcid), orcids))

    orcid_profiles = list(filter(lambda orcid_profile: orcid_profile is not None, orcid_profiles_maybe))

    # structure [{id, givenName, familyName, dois}]
    dois_per_orcid: List[Dict] = jq.compile(
        '. | map({"id": ."@id", "givenName": .givenName, "familyName": .familyName, "dois": [[."@reverse".creator] | flatten[] | select(."@type" == "CreativeWork")] | [[map(.identifier)] | flatten[] | [select(.propertyID == "doi")] | map(.value)] | flatten})').input_value(
        orcid_profiles).first()

    #logging.info(f'{ANALYZER} {dois_per_orcid}')

    return dois_per_orcid


def _make_entry(ele: Dict) -> OrcidProfile:
    # TODO: error handling for missing info (None)
    return OrcidProfile(ele['id'], ele['givenName'], ele['familyName'])


def group_orcids_per_doi(dois_per_orcid: List[Dict]) -> Dict[str, List[OrcidProfile]]:
    """
    Groups ORCID profile contents by DOI (key) and associates the ORCIDs with them (values).

    @param dois_per_orcid: A list of ORCIDs with their associated DOIs.
    """

    orcids_by_doi = {}

    for ele in dois_per_orcid:
        for doi in ele['dois']:
            if doi not in orcids_by_doi:
                orcids_by_doi[doi] = [_make_entry(ele)]
            else:
                orcids_by_doi[doi].append(_make_entry(ele))

    return orcids_by_doi


__all__ = ['PublicationInfo', 'analyze_dois', 'analyze_doi_record_crossref', 'analyze_doi_record_datacite', 'analyze_doi_record_medra', 'get_orcids_from_resolved_dois',
           'get_dois_per_orcid', 'group_orcids_per_doi']