"""Shared time utilities for consistent UTC datetime generation across the application."""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return the current UTC datetime as a timezone-aware object."""
    return datetime.now(timezone.utc)
