"""Exponential backoff and retry management service."""

import random
from datetime import datetime, timedelta, timezone
from app.config import settings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def calculate_next_attempt(attempt: int, base_delay: float = 2.0, max_delay: float = 300.0) -> datetime:
    """
    Calculate the next attempt timestamp using exponential backoff with jitter.
    Attempt is 1-indexed.
    """
    delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
    # Add random jitter up to 50% of delay
    jitter = random.uniform(0, 0.5 * delay)
    total_delay = delay + jitter
    return utc_now() + timedelta(seconds=total_delay)


def should_retry(attempts: int) -> bool:
    """Determine if a failed job can be retried based on max attempt limit."""
    return attempts < settings.MAX_DM_ATTEMPTS
