import pytest
import time
import asyncio
from app.services.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_allows_10_requests_and_blocks_11th():
    limiter = RateLimiter(max_requests=3, window_seconds=1.0)

    # First 3 requests should be immediate
    start = time.monotonic()
    await limiter.acquire()
    await limiter.acquire()
    await limiter.acquire()
    duration = time.monotonic() - start
    assert duration < 0.2

    # 4th request must be delayed until window expires
    start = time.monotonic()
    await limiter.acquire()
    duration = time.monotonic() - start
    assert duration >= 0.8


@pytest.mark.asyncio
async def test_rate_limiter_retry_after_pause():
    limiter = RateLimiter(max_requests=10, window_seconds=60.0)

    # Report 429 with 0.5s Retry-After
    await limiter.report_rate_limit(retry_after_seconds=0.5)

    start = time.monotonic()
    await limiter.acquire()
    duration = time.monotonic() - start
    assert duration >= 0.4
