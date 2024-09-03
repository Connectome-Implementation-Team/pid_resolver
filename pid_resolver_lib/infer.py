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
from typing import NamedTuple, List, Dict
import json
from .pid_analyzer import parse_resolved_dois_from_json, PublicationInfo, AuthorInfo

logging.basicConfig(filename='pid_infer.log',
                    filemode='a',
                    format='%(module)s %(levelname)s: %(asctime)s %(message)s',
                    datefmt='%H:%M:%S',
                    encoding='utf-8',
                    level=logging.DEBUG)

logger = logging.getLogger(__name__)

class ContextInfo(NamedTuple):
    author: AuthorInfo
    co_authors: List[AuthorInfo]
    doi: str
    idx: int


def make_context(pub: PublicationInfo) -> List[ContextInfo]:
    length = len(pub.authors)
    idx_range = list(range(length))

    # structure:

    # for each author of a publication, return an entry with the author's profile and his co-authors
    return list(map(lambda idx: ContextInfo(pub.authors[idx], (pub.authors[:idx] + pub.authors[idx+1:]), pub.doi, idx), idx_range))


def search_author(given_name: str, family_name: str, with_ctx: List[ContextInfo]):
    return list(filter(lambda ctx: ctx.author.given_name == given_name and ctx.author.family_name == family_name and ctx.author.orcid is not None, with_ctx))



def main():
    results: Dict[str, PublicationInfo] = parse_resolved_dois_from_json(Path('results.json'))

    pubs: List[PublicationInfo] = list(results.values())

    # print(pubs)

    # preserve their context, i.e. their co-authors
    with_context: List[List[ContextInfo]] = list(map(make_context, pubs))

    flattened_context: List[ContextInfo] = [item for sublist in with_context for item in sublist]

    # print(flattened_context)

    for auth_ctx in flattened_context:

        if auth_ctx.author.orcid is None:
            match = search_author(auth_ctx.author.given_name, auth_ctx.author.family_name, flattened_context)

            if len(match) > 0:
                # compare co-authors (ignore co-authors without ORCID)
                co_author_orcid = set(map(lambda co_author: co_author.orcid, auth_ctx.co_authors)) - {None}

                common_co_authors = co_author_orcid.intersection(
                    set(map(lambda co_author: co_author.orcid, match[0].co_authors)) - {None})
                # print(common_co_authors)

                if len(common_co_authors) > 0:
                    # infer author's ORCID

                    # inferred ORCID must stem from a different publication: this assertion should always be met
                    assert auth_ctx.doi != match[0].doi

                    if {match[0].author.orcid}.issubset(common_co_authors):
                        # author cannot be her or his own co-author: these mistakes stem from wrong ORCID assignments from the publisher:
                        # An ORCID was assigned to the wrong person, then the ORCID was assigned to the correct person from the information in the ORCID profile itself -> two distinct persons have the same ORCID
                        logging.error(f'{set(match[0].author.orcid).issubset(common_co_authors)}, {match[0].author.orcid}, {common_co_authors}, {auth_ctx}, {match[0]}')
                        continue

                    logging.debug(
                        f'{auth_ctx.author.given_name}, {auth_ctx.author.family_name}, {auth_ctx.author.orcid}, {auth_ctx.doi}, {auth_ctx.idx}, {match[0].author.orcid}, {match[0].author.given_name}, {match[0].author.family_name}, {match[0].doi}, {common_co_authors}')
                    # add missing ORCID
                    results[auth_ctx.doi] = PublicationInfo(
                        doi=results[auth_ctx.doi].doi,
                        title=results[auth_ctx.doi].title,
                        authors=results[auth_ctx.doi].authors[:auth_ctx.idx] + [
                            AuthorInfo(given_name=auth_ctx.author.given_name, family_name=auth_ctx.author.family_name,
                                       orcid=match[0].author.orcid, origin_orcid='inferred', ror=None)] + results[
                                                                                                              auth_ctx.doi].authors[
                                                                                                          auth_ctx.idx + 1:]
                    )

    with open('updated.json', 'w') as f:
        f.write(json.dumps(results))
