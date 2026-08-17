"""Services package initialization exposing the public API."""

from app.services.dm_service import create_dm_job_for_rule
from app.services.pseudogram_client import pseudogram_client, PseudogramClient
from app.services.rate_limiter import dm_rate_limiter, RateLimiter
from app.services.retry_service import calculate_next_attempt, should_retry
from app.services.rule_service import (
    create_rule,
    get_active_rules,
    matches_keyword,
    find_matching_rules,
)
from app.services.webhook_service import verify_signature, process_incoming_webhook

__all__ = [
    "create_dm_job_for_rule",
    "pseudogram_client",
    "PseudogramClient",
    "dm_rate_limiter",
    "RateLimiter",
    "calculate_next_attempt",
    "should_retry",
    "create_rule",
    "get_active_rules",
    "matches_keyword",
    "find_matching_rules",
    "verify_signature",
    "process_incoming_webhook",
]
