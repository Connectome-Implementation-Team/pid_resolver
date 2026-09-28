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
import time
import unittest

from pid_resolver_lib.rate_limit import RetryConfig, AsyncRateLimiter, compute_backoff_delay


class TestRateLimit(unittest.TestCase):

    def test_compute_backoff_delay_honors_retry_after(self):
        cfg = RetryConfig(base_delay=1.0, max_delay=60.0)
        delay = compute_backoff_delay(attempt=0, retry_config=cfg, retry_after_header='7')
        assert delay == 7.0

    def test_compute_backoff_delay_falls_back_on_invalid_retry_after(self):
        cfg = RetryConfig(base_delay=1.0, max_delay=60.0)
        delay = compute_backoff_delay(attempt=0, retry_config=cfg, retry_after_header='not-a-number')
        # falls back to exponential backoff with jitter: base_delay * 2**0 * [0.5, 1.5]
        assert 0.5 <= delay <= 1.5

    def test_compute_backoff_delay_grows_exponentially_and_is_capped(self):
        cfg = RetryConfig(base_delay=1.0, max_delay=5.0)
        # attempt 10 would be 1024 uncapped; must be capped at max_delay (before jitter)
        delay = compute_backoff_delay(attempt=10, retry_config=cfg)
        assert delay <= cfg.max_delay * 1.5

    def test_rate_limiter_rejects_invalid_params(self):
        with self.assertRaises(ValueError):
            AsyncRateLimiter(rate=0)
        with self.assertRaises(ValueError):
            AsyncRateLimiter(rate=1, period=0)


class TestAsyncRateLimiterTiming(unittest.IsolatedAsyncioTestCase):

    async def test_rate_limiter_allows_burst_up_to_rate(self):
        limiter = AsyncRateLimiter(rate=5, period=1.0)

        start = time.monotonic()
        for _ in range(5):
            await limiter.acquire()
        elapsed = time.monotonic() - start

        # first `rate` acquisitions should not need to wait (bucket starts full)
        assert elapsed < 0.2

    async def test_rate_limiter_throttles_beyond_rate(self):
        limiter = AsyncRateLimiter(rate=5, period=0.5)  # 10/sec

        start = time.monotonic()
        for _ in range(10):
            await limiter.acquire()
        elapsed = time.monotonic() - start

        # 10 acquisitions at 10/sec sustained (after the initial full bucket of 5) should take
        # meaningfully longer than an unthrottled burst.
        assert elapsed >= 0.3
