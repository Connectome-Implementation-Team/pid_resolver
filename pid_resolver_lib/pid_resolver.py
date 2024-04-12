from pathlib import Path
import jq  # type: ignore
import sys
from typing import List, NamedTuple, Optional, cast, Tuple
import aiohttp # type: ignore
from aiohttp import ClientSession, TCPConnector, ClientTimeout
import asyncio
from urllib.parse import quote
import os


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
        print(f'Error when resolving record {e}', file=sys.stderr)
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


def _record_to_path(record_id: str) -> Tuple[Path, Path]:
    parts = record_id.split('/', 1) # split on first occurrence of slash as DOI suffixes may contain slashes
    if len(parts) == 2: # it is a DOI
        return Path(parts[0]), Path(parts[1])
    else: # it is an ORCID
        return Path(parts[0]), Path() # second part won't have any effect


def _quote_path(record_path: Tuple[Path, Path]):
    return record_path[0] / quote(str(record_path[1]), safe="")


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

    record_ids_deduplicated = list(set(record_ids))

    # check if a record is already in the cache
    records_not_cached = list(
        filter(lambda rec_id: not os.path.isfile(f'{cache_dir / _quote_path(_record_to_path(rec_id))}'),  # https://stackoverflow.com/questions/14826888/python-os-path-join-on-a-list
               record_ids_deduplicated))

    print(f'fetching number of records for {cache_dir}: ', len(records_not_cached))

    offset = 0
    batch_size = 500
    last_run = False

    while not last_run:

        limit = offset + batch_size

        if limit > len(records_not_cached):
            limit = len(records_not_cached)
            last_run = True

        print('fetching batch: ',  offset, limit)

        results = await _fetch_record_batch(records_not_cached[offset:limit], base_url, accept_header)

        # store records as files
        for res in results:
            try:
                if 'doi.org' in base_url:
                    # DOI
                    prefix, suffix = _record_to_path(res.rec_id)
                    # organize DOIs by prefixes
                    if not os.path.isdir(cache_dir / prefix):
                        os.makedirs(cache_dir / Path(prefix))
                    with open(f'{cache_dir / _quote_path((prefix, suffix)) }', 'w') as f:
                        f.write(res.content)
                else:
                    # ORCID
                    with open(f'{cache_dir / Path(res.rec_id) }', 'w') as f:
                        f.write(res.content)

            except Exception as e:
                print(f'An error occurred when writing record {res}: {e}')


        # sleep because of rate limits
        print('pausing')
        await asyncio.sleep(sleep_per_batch)
        print('working')

        offset = offset + batch_size


__all__ = ['fetch_records']