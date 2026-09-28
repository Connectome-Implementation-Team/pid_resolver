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

import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import AsyncMock

from aioresponses import aioresponses
import aiohttp
from pid_resolver_lib import pid_resolver, cache_handler
from pid_resolver_lib.rate_limit import RetryConfig, AsyncRateLimiter


def _fast_limiter() -> AsyncRateLimiter:
    # a high rate so tests don't actually wait on the limiter
    return AsyncRateLimiter(rate=1000)


def _quick_retry_config(max_retries: int = 3) -> RetryConfig:
    # tiny delays so retry tests run fast
    return RetryConfig(max_retries=max_retries, base_delay=0.001, max_delay=0.01)


class TestPidResolver(unittest.IsolatedAsyncioTestCase):

    async def test__make_record_request_success(self):
        with aioresponses() as mocked:
            mocked.get('http://example.com/one', status=200, body='data')
            session = aiohttp.ClientSession()

            resp = await pid_resolver._make_record_request(
                session, 'one', 'http://example.com', 'application/ld+json',
                _fast_limiter(), _quick_retry_config())

            await session.close()

            assert resp is not None
            assert resp.rec_id == 'one'
            assert resp.content == 'data'

    async def test__make_record_request_retries_then_succeeds(self):
        with aioresponses() as mocked:
            # first attempt is rate-limited, second attempt succeeds
            mocked.get('http://example.com/one', status=429)
            mocked.get('http://example.com/one', status=200, body='data')
            session = aiohttp.ClientSession()

            resp = await pid_resolver._make_record_request(
                session, 'one', 'http://example.com', 'application/ld+json',
                _fast_limiter(), _quick_retry_config())

            await session.close()

            assert resp is not None
            assert resp.rec_id == 'one'
            assert resp.content == 'data'

    async def test__make_record_request_gives_up_after_max_retries(self):
        retry_config = _quick_retry_config(max_retries=2)

        with aioresponses() as mocked:
            # always fails with a retryable status
            for _ in range(retry_config.max_retries + 1):
                mocked.get('http://example.com/one', status=503)
            session = aiohttp.ClientSession()

            resp = await pid_resolver._make_record_request(
                session, 'one', 'http://example.com', 'application/ld+json',
                _fast_limiter(), retry_config)

            await session.close()

            assert resp is None

    async def test__make_record_request_does_not_retry_definitive_error(self):
        with aioresponses() as mocked:
            # only register the response once: if the code retried, aioresponses would raise
            # because there is no second mock registered for this URL.
            mocked.get('http://example.com/one', status=404)
            session = aiohttp.ClientSession()

            resp = await pid_resolver._make_record_request(
                session, 'one', 'http://example.com', 'application/ld+json',
                _fast_limiter(), _quick_retry_config())

            await session.close()

            assert resp is None

    def test_records_not_in_cache(self):
        with mock.patch('pid_resolver_lib.pid_resolver.get_keys') as mock_get_keys:
            mock_get_keys.return_value = ['1', '3', '5']

            not_cached = pid_resolver.records_not_in_cache(['1', '2', '3', '4'], Path('.'))

            assert set(not_cached) == set(['2', '4'])

            args = mock_get_keys.mock_calls[0].args

            assert Path('.') == args[0]

    async def test_fetch_records(self):

        # https://medium.com/@durgaswaroop/writing-better-tests-in-python-with-pytest-mock-part-2-92b828e1453c
        with mock.patch('pid_resolver_lib.pid_resolver.get_keys') as mock_get_keys:
            mock_get_keys.return_value = ['1']

            pid_resolver._fetch_all = AsyncMock(name='_fetch_all', return_value=[])
            res = await pid_resolver.fetch_records(['1', '2'], Path(), 'http://example.com/one', '')

            assert res == []

            args = pid_resolver._fetch_all.mock_calls[0].args

            # rec ids are converted to a set, hence order is not preserved
            assert set(args[0]) == {'2'}
            assert args[1] == Path()
            assert args[2] == 'http://example.com/one'
            assert args[3] == ''

    async def test_fetch_records_returns_empty_list_when_nothing_to_fetch(self):
        with mock.patch('pid_resolver_lib.pid_resolver.get_keys') as mock_get_keys:
            mock_get_keys.return_value = ['1', '2']

            pid_resolver._fetch_all = AsyncMock(name='_fetch_all')
            res = await pid_resolver.fetch_records(['1', '2'], Path(), 'http://example.com/one', '')

            assert res == []
            pid_resolver._fetch_all.assert_not_called()
