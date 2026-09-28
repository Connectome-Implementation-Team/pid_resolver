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

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, FrozenSet, Optional, TypeVar
import aiohttp # type: ignore
from aiohttp import ClientResponse, ClientSession # type: ignore

T = TypeVar('T')


@dataclass
class RetryConfig:
    """
    Configuration for retrying transient failures of HTTP requests.

    @param max_retries: Maximum number of retry attempts after the initial try.
    @param base_delay: Base delay in seconds used for exponential backoff (attempt 0 -> ~base_delay).
    @param max_delay: Upper bound for the computed backoff delay, in seconds.
    @param retryable_statuses: HTTP status codes that should trigger a retry. Anything else (e.g. 404)
        is treated as a definitive result and is not retried.
    """
    max_retries: int = 5
    base_delay: float = 1.0
    max_delay: float = 60.0
    retryable_statuses: FrozenSet[int] = field(default_factory=lambda: frozenset({429, 500, 502, 503, 504}))


def compute_backoff_delay(attempt: int, retry_config: RetryConfig, retry_after_header: Optional[str] = None) -> float:
    """
    Computes how long to wait before the next retry attempt.

    If the server sent a numeric `Retry-After` header (seconds form), that value is honored directly,
    since it reflects the server's own view of when it will accept requests again.
    Otherwise, falls back to exponential backoff with full jitter (delay is randomized between 50% and
    150% of the computed value) so that concurrent workers retrying after the same failure don't all
    hammer the API again at the exact same moment.

    @param attempt: Zero-based index of the attempt that just failed (0 = first try failed).
    @param retry_config: Backoff parameters (base_delay, max_delay).
    @param retry_after_header: Value of a `Retry-After` response header, if present.
    """

    if retry_after_header is not None:
        try:
            return max(0.0, float(retry_after_header))
        except ValueError:
            # Retry-After can also be an HTTP-date; that form is rare for the APIs this
            # library talks to, so we fall back to exponential backoff rather than parsing it.
            pass

    delay = min(retry_config.max_delay, retry_config.base_delay * (2 ** attempt))
    return delay * (0.5 + random.random())


class AsyncRateLimiter:
    """
    A small async token-bucket rate limiter: allows up to `rate` acquisitions per `period` seconds.

    This smooths requests out over time instead of the "fire a burst of requests, then sleep for a
    fixed duration" pattern, which tends to spike well above the allowed rate during the burst and
    then sit idle unnecessarily during the sleep.

    Usage:
        limiter = AsyncRateLimiter(rate=3, period=1.0)  # ~3 requests/second, sustained
        async with limiter:
            ...  # make one request
    """

    def __init__(self, rate: float, period: float = 1.0):
        if rate <= 0:
            raise ValueError('rate must be > 0')
        if period <= 0:
            raise ValueError('period must be > 0')

        self._rate = rate
        self._period = period
        self._tokens = rate
        self._updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._updated_at
                self._updated_at = now
                self._tokens = min(self._rate, self._tokens + elapsed * (self._rate / self._period))

                if self._tokens >= 1:
                    self._tokens -= 1
                    return

                wait_time = (1 - self._tokens) * (self._period / self._rate)
                await asyncio.sleep(wait_time)

    async def __aenter__(self) -> 'AsyncRateLimiter':
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


async def request_with_retry(
        session: ClientSession,
        url: str,
        limiter: AsyncRateLimiter,
        retry_config: RetryConfig,
        parse_response: Callable[[ClientResponse], Awaitable[T]],
        log_prefix: str,
        log_id: str,
        headers: Optional[Dict[str, str]] = None,
) -> Optional[T]:
    """
    Performs a GET request with rate limiting and retry/backoff for transient failures
    (retryable HTTP statuses, timeouts, connection errors). A numeric `Retry-After` header is honored.

    On a successful response, `parse_response` is awaited with the response and its result returned.
    Definitive failures (e.g. 404) and exhausted retries return None; nothing is raised for those.

    @param session: The aiohttp session to be used.
    @param url: The URL to GET.
    @param limiter: Rate limiter shared across all requests of a batch.
    @param retry_config: Retry/backoff behavior.
    @param parse_response: Extracts the result from a successful response.
    @param log_prefix: Prefix for log messages, e.g. 'RESOLVER:'.
    @param log_id: Identifier of the thing being requested, used in log messages.
    @param headers: Optional request headers.
    """

    for attempt in range(retry_config.max_retries + 1):

        await limiter.acquire()

        try:
            async with session.get(url, headers=headers) as request:

                if request.status in retry_config.retryable_statuses:
                    if attempt == retry_config.max_retries:
                        logging.error(
                            f'{log_prefix} {log_id}: giving up after {attempt + 1} attempt(s), '
                            f'last status {request.status}')
                        return None

                    delay = compute_backoff_delay(attempt, retry_config, request.headers.get('Retry-After'))
                    logging.warning(
                        f'{log_prefix} {log_id}: status {request.status}, retrying in {delay:.1f}s '
                        f'(attempt {attempt + 1}/{retry_config.max_retries})')
                    await asyncio.sleep(delay)
                    continue

                # raises for any remaining 4xx/5xx not in retryable_statuses, e.g. 404
                request.raise_for_status()
                return await parse_response(request)

        except aiohttp.ClientResponseError as e:
            logging.error(f'{log_prefix} {log_id}: non-retryable error {e.status} {e.message}')
            return None

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt == retry_config.max_retries:
                logging.error(f'{log_prefix} {log_id}: giving up after {attempt + 1} attempt(s): {e}')
                return None

            delay = compute_backoff_delay(attempt, retry_config)
            logging.warning(
                f'{log_prefix} {log_id}: {e}, retrying in {delay:.1f}s '
                f'(attempt {attempt + 1}/{retry_config.max_retries})')
            await asyncio.sleep(delay)

    return None


__all__ = ['RetryConfig', 'AsyncRateLimiter', 'compute_backoff_delay', 'request_with_retry']
