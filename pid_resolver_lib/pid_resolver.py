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

from pathlib import Path
import jq  # type: ignore
from typing import List, NamedTuple, Optional, cast, Tuple
import aiohttp # type: ignore
from aiohttp import ClientSession, TCPConnector, ClientTimeout
import asyncio
import logging
from .cache_handler import get_keys, write_records_to_cache

logger = logging.getLogger(__name__)

RESOLVER = 'RESOLVER:'

class ResolvedRecord(NamedTuple):
    """
    Represents a resolved record (DOI, ORCID).

    # https://realpython.com/python-namedtuple/#namedtuple-vs-typingnamedtuple
    # requires Python 3.5
    """
    rec_id: str # 0
    content: str # 1


async def _make_record_request(session: ClientSession, record_id: str, base_url: str, accept_header: str) -> Optional[ResolvedRecord]:
    """
    Given a record id, resolves it using content negotiation.

    @param session:  The aiohttp session to be used.
    @param record_id: The id of the record to be resolved.
    """

    headers = {
        'Accept': accept_header
    }

    try:
        async with session.get(f'{base_url}/{record_id}', headers=headers) as request:
            return ResolvedRecord(record_id, await request.text())

    except Exception as e:
        logging.error(f'{RESOLVER} Error when resolving record {e}')
        return None


async def _fetch_record_batch(record_ids: List[str], base_url: str, accept_header) -> List[ResolvedRecord]:
    """
    Given a batch of record ids, fetches them.

    @param record_ids: List of record ids.
    """

    conn = TCPConnector(limit=5)
    # set raise_for_status
    time_out = ClientTimeout(total=60 * 60 * 24)
    async with aiohttp.ClientSession(connector=conn, raise_for_status=True, timeout=time_out) as session:

        requests = [_make_record_request(session, rec_id, base_url, accept_header) for rec_id in record_ids]

        results = await asyncio.gather(*requests)

        # filter out None values (failed requests)
        return cast(List[ResolvedRecord], list(filter(lambda res: res is not None, results)))


def records_not_in_cache(record_ids: List[str], cache_dir: Path) -> List[str]:
    return list(set(record_ids) - set(get_keys(cache_dir)))


async def fetch_records(record_ids: List[str], cache_dir: Path, base_url: str, accept_header: str, sleep_per_batch: int = 0) -> None:
    """
    Fetches a list of records (DOIs, ORCIDs) and writes them to the cache directory.
    Performs fetching in batches of size 500 requests each.

    @param record_ids: Records to be fetched.
    @param cache_dir: Directory the results are written to
    @param base_url: Base URL of the items to be fetched, e.g., https://doi.org.
    @param accept_header: HTTP accept header for content negotiation.
    @param sleep_per_batch: Sleep in seconds after each batch to respect rate limits, if any. See https://support.datacite.org/docs/is-there-a-rate-limit-for-making-requests-against-the-datacite-apis.
    """

    records_not_cached = records_not_in_cache(record_ids, cache_dir)

    logging.info(f'{RESOLVER} fetching number of records for {cache_dir}: {len(records_not_cached)}')

    offset = 0
    batch_size = 500
    last_run = False

    while not last_run:

        limit = offset + batch_size

        if limit > len(records_not_cached):
            limit = len(records_not_cached)
            last_run = True

        logging.info(f'{RESOLVER} fetching batch: {offset}, {limit}')

        results: List[ResolvedRecord] = await _fetch_record_batch(records_not_cached[offset:limit], base_url, accept_header)

        # store records in cache
        try:
            # TODO: try to use member names of named tuple, i.e rec_id and content
            logging.info(f'{RESOLVER} results {len(results)}')
            write_records_to_cache(results, 0, 1, cache_dir)

        except Exception as e:
            logging.error(f'{RESOLVER} An error occurred when writing results: {e}')

        # sleep because of rate limits
        logging.info(f'{RESOLVER} pausing')
        await asyncio.sleep(sleep_per_batch)
        logging.info(f'{RESOLVER} working')

        offset = offset + batch_size

__all__ = ['fetch_records', 'records_not_in_cache']