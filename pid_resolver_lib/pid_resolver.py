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
from typing import List, NamedTuple, Optional
import aiohttp # type: ignore
from aiohttp import ClientSession, TCPConnector, ClientTimeout
import asyncio
import logging
from .cache_handler import get_keys, write_records_to_cache
from .rate_limit import RetryConfig, AsyncRateLimiter, compute_backoff_delay

logger = logging.getLogger(__name__)

RESOLVER = 'RESOLVER:'

# Sent on every request so upstream services (DataCite, Crossref, ORCID, mEDRA) can identify and, if
# needed, contact the operator of this script instead of just blocking it. Best practice, e.g., per
# https://support.datacite.org/docs/best-practices-for-integrators -- callers are encouraged to pass
# their own value (ideally including a mailto:) via the `user_agent` parameter of `fetch_records`.
DEFAULT_USER_AGENT = 'pid_resolver_lib (https://github.com/Connectome-Implementation-Team/pid_resolver)'


class ResolvedRecord(NamedTuple):
    """
    Represents a resolved record (DOI, ORCID).

    # https://realpython.com/python-namedtuple/#namedtuple-vs-typingnamedtuple
    # requires Python 3.5
    """
    rec_id: str # 0
    content: str # 1


async def _make_record_request(
        session: ClientSession,
        record_id: str,
        base_url: str,
        accept_header: str,
        limiter: AsyncRateLimiter,
        retry_config: RetryConfig,
) -> Optional[ResolvedRecord]:
    """
    Given a record id, resolves it using content negotiation. Retries transient failures
    (429, 5xx, timeouts, connection errors) with exponential backoff + jitter, honoring a numeric
    `Retry-After` header when the server sends one. Definitive failures (e.g. 404) are not retried.

    @param session: The aiohttp session to be used.
    @param record_id: The id of the record to be resolved.
    @param base_url: Base URL of the item to be fetched, e.g., https://doi.org.
    @param accept_header: HTTP accept header for content negotiation.
    @param limiter: Rate limiter shared across all requests in this batch.
    @param retry_config: Retry/backoff behavior for transient failures.
    """

    headers = {
        'Accept': accept_header
    }

    url = f'{base_url}/{record_id}'

    for attempt in range(retry_config.max_retries + 1):

        await limiter.acquire()

        try:
            async with session.get(url, headers=headers) as request:

                if request.status in retry_config.retryable_statuses:
                    if attempt == retry_config.max_retries:
                        logging.error(
                            f'{RESOLVER} {record_id}: giving up after {attempt + 1} attempt(s), last status {request.status}')
                        return None

                    delay = compute_backoff_delay(attempt, retry_config, request.headers.get('Retry-After'))
                    logging.warning(
                        f'{RESOLVER} {record_id}: status {request.status}, retrying in {delay:.1f}s '
                        f'(attempt {attempt + 1}/{retry_config.max_retries})')
                    await asyncio.sleep(delay)
                    continue

                # raises for any remaining 4xx/5xx not in retryable_statuses, e.g. 404
                request.raise_for_status()
                return ResolvedRecord(record_id, await request.text())

        except aiohttp.ClientResponseError as e:
            # a definitive client/server error that we've decided not to retry (see retryable_statuses)
            logging.error(f'{RESOLVER} {record_id}: non-retryable error {e.status} {e.message}')
            return None

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt == retry_config.max_retries:
                logging.error(f'{RESOLVER} {record_id}: giving up after {attempt + 1} attempt(s): {e}')
                return None

            delay = compute_backoff_delay(attempt, retry_config)
            logging.warning(
                f'{RESOLVER} {record_id}: {e}, retrying in {delay:.1f}s '
                f'(attempt {attempt + 1}/{retry_config.max_retries})')
            await asyncio.sleep(delay)

    return None


def records_not_in_cache(record_ids: List[str], cache_dir: Path) -> List[str]:
    return list(set(record_ids) - set(get_keys(cache_dir)))


async def _fetch_all(
        record_ids: List[str],
        cache_dir: Path,
        base_url: str,
        accept_header: str,
        requests_per_second: float,
        max_concurrency: int,
        retry_config: RetryConfig,
        user_agent: str,
) -> List[str]:
    """
    Fetches all given records, paced by a rate limiter and bounded by a concurrency limit, retrying
    transient failures. Writes successfully resolved records to the cache. Returns the ids of records
    that permanently failed after retries (not written to cache).
    """

    limiter = AsyncRateLimiter(rate=requests_per_second)
    conn = TCPConnector(limit=max_concurrency)
    # bound individual connect/read phases; overall duration is governed by the retry policy instead
    # of one very long-lived timeout.
    time_out = ClientTimeout(total=None, sock_connect=30, sock_read=60)
    headers = {'User-Agent': user_agent}

    async with aiohttp.ClientSession(connector=conn, timeout=time_out, headers=headers) as session:

        requests = [_make_record_request(session, rec_id, base_url, accept_header, limiter, retry_config)
                    for rec_id in record_ids]

        results: List[Optional[ResolvedRecord]] = await asyncio.gather(*requests)

    succeeded: List[ResolvedRecord] = [res for res in results if res is not None]
    failed_ids: List[str] = [rec_id for rec_id, res in zip(record_ids, results) if res is None]

    logging.info(f'{RESOLVER} results {len(succeeded)}, failed {len(failed_ids)}')

    try:
        write_records_to_cache(succeeded, 0, 1, cache_dir)
    except Exception as e:
        logging.error(f'{RESOLVER} An error occurred when writing results: {e}')

    if failed_ids:
        preview = failed_ids[:20]
        suffix = ', ...' if len(failed_ids) > 20 else ''
        logging.error(f'{RESOLVER} {len(failed_ids)} record(s) permanently failed for {cache_dir}: {preview}{suffix}')

    return failed_ids


async def fetch_records(
        record_ids: List[str],
        cache_dir: Path,
        base_url: str,
        accept_header: str,
        requests_per_second: float = 3.0,
        max_concurrency: int = 5,
        retry_config: Optional[RetryConfig] = None,
        user_agent: str = DEFAULT_USER_AGENT,
) -> List[str]:
    """
    Fetches a list of records (DOIs, ORCIDs) and writes them to the cache directory.

    Requests are paced to `requests_per_second` (smoothed over time rather than fired in one big
    burst per batch) and bounded to `max_concurrency` requests in flight at once. Transient failures
    (HTTP 429/5xx, timeouts, connection errors) are retried with exponential backoff and jitter,
    honoring a `Retry-After` response header when present; definitive failures (e.g. 404) are not
    retried.

    @param record_ids: Records to be fetched.
    @param cache_dir: Directory the results are written to.
    @param base_url: Base URL of the items to be fetched, e.g., https://doi.org.
    @param accept_header: HTTP accept header for content negotiation.
    @param requests_per_second: Sustained request rate to stay within the upstream API's rate limit.
        E.g., DOI content negotiation via doi.org allows 1000 requests / 5 minutes per IP address
        (~3.3/sec) as of 2026, see https://support.datacite.org/docs/rate-limit -- adjust to match
        whatever the target API currently documents.
    @param max_concurrency: Maximum number of requests in flight at once.
    @param retry_config: Retry/backoff behavior for transient failures. Defaults to
        RetryConfig() (5 retries, exponential backoff with jitter, capped at 60s).
    @param user_agent: Value of the User-Agent header sent with every request. Upstream services
        (DataCite, Crossref, ORCID) ask for an identifiable value that includes contact info
        (e.g. "my_script/1.0 (https://example.org; mailto:me@example.org)") so they can reach you
        instead of just blocking you if something goes wrong.
    @return: Ids of records that permanently failed after retries (these are not written to cache).
    """

    retry_config = retry_config or RetryConfig()

    records_not_cached = records_not_in_cache(record_ids, cache_dir)

    logging.info(f'{RESOLVER} fetching number of records for {cache_dir}: {len(records_not_cached)}')

    if not records_not_cached:
        return []

    return await _fetch_all(records_not_cached, cache_dir, base_url, accept_header, requests_per_second,
                             max_concurrency, retry_config, user_agent)


__all__ = ['fetch_records', 'records_not_in_cache', 'ResolvedRecord', 'DEFAULT_USER_AGENT']
