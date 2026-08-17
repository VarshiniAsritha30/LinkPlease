"""Sliding-window Rate Limiter for Pseudogram API requests."""

import asyncio
import time
import logging
from collections import deque
from typing import Optional

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Sliding window rate limiter that enforces max 10 POST /v1/dm/send requests 
    per rolling 60 seconds as required by Pseudogram API specs.
    Also handles dynamic 429 Retry-After pauses.
    """

    def __init__(self, max_requests: int = 10, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: deque = deque()
        self._lock = asyncio.Lock()
        self._pause_until: float = 0.0

    async def acquire(self):
        """
        Wait if necessary until a request slot is available in the rolling window
        and any active Retry-After pause has expired.
        """
        while True:
            async with self._lock:
                now = time.monotonic()

                # Check if we are paused due to external 429 Retry-After
                if now < self._pause_until:
                    wait_seconds = self._pause_until - now
                    logger.info(f"Rate limiter paused due to Retry-After. Waiting {wait_seconds:.2f}s")
                else:
                    # Remove timestamps outside the rolling window
                    while self._timestamps and self._timestamps[0] <= now - self.window_seconds:
                        self._timestamps.popleft()

                    # If slot available, record timestamp and proceed
                    if len(self._timestamps) < self.max_requests:
                        self._timestamps.append(now)
                        return

                    # Calculate wait time until oldest timestamp falls out of the window
                    wait_seconds = self._timestamps[0] + self.window_seconds - now

            # Sleep outside the lock so other tasks aren't blocked from checking status
            if wait_seconds > 0:
                logger.info(f"Rate limit threshold reached (10/60s). Waiting {wait_seconds:.2f}s before sending DM")
                await asyncio.sleep(wait_seconds + 0.05)

    async def report_rate_limit(self, retry_after_seconds: Optional[float] = None):
        """
        Call when an external 429 response is received to pause all future send requests.
        """
        async with self._lock:
            now = time.monotonic()
            pause_duration = retry_after_seconds if (retry_after_seconds is not None and retry_after_seconds > 0) else 5.0
            self._pause_until = max(self._pause_until, now + pause_duration)
            logger.warning(f"External 429 received. Pausing rate limiter for {pause_duration:.2f} seconds.")


# Global singleton instance for application DM sending
dm_rate_limiter = RateLimiter(max_requests=10, window_seconds=60.0)
