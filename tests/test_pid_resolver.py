import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import AsyncMock, call

from aioresponses import aioresponses
import aiohttp
from pid_resolver_lib import pid_resolver, cache_handler


class TestPidResolver(unittest.IsolatedAsyncioTestCase):

    async def test__make_record_request(self):
        with aioresponses() as mocked:
            mocked.get('http://example.com/one', status=200, body='data')
            session = aiohttp.ClientSession()

            resp = await pid_resolver._make_record_request(session, 'one', 'http://example.com', 'application/ld+json')

            await session.close()

            assert resp.rec_id == 'one'
            assert resp.content == 'data'

    async def test_fetch_records(self):

        # https://medium.com/@durgaswaroop/writing-better-tests-in-python-with-pytest-mock-part-2-92b828e1453c
        with mock.patch('pid_resolver_lib.pid_resolver.get_keys') as mock_get_keys:
            mock_get_keys.return_value = ['1']

            pid_resolver._fetch_record_batch = AsyncMock(name='_fetch_record_batch')
            res = await pid_resolver.fetch_records(['1', '2'], Path(), 'http://example.com/one', '')

            assert res is None

            #print(pid_resolver._fetch_record_batch.mock_calls[0].args)

            args = pid_resolver._fetch_record_batch.mock_calls[0].args
            expected_args = (['2'], 'http://example.com/one', '')

            assert len(args) == len(expected_args)

            # rec ids are converted to a set, hence order is not preserved
            assert set(args[0]) == set(expected_args[0])
            assert args[1] == expected_args[1]
            assert args[2] == expected_args[2]

