"""DM Job processing and deduplication service."""

import logging
from typing import Optional
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dm_job import DMJob, DMJobStatus
from app.models.duplicate_block import DuplicateBlock

logger = logging.getLogger(__name__)


async def create_dm_job_for_rule(
    db: AsyncSession,
    rule_id: str,
    dm_message: str,
    user_id: str,
    comment_id: str,
    event_id: str
) -> Optional[DMJob]:
    """
    Attempts to create a DM job for a user and rule.
    Enforces uniqueness of (rule_id, user_id) at the database level.
    If the database unique constraint fails (IntegrityError), records a DuplicateBlock
    and returns None, preventing any duplicate DM.

    Does NOT commit. Each attempt is wrapped in its own SAVEPOINT (begin_nested) so a
    duplicate on one rule doesn't roll back other work already staged on this session
    (e.g. the parent WebhookEvent, or DMJobs already created for other matching rules
    in the same webhook). The caller is responsible for the outer commit, so that the
    WebhookEvent and all of its resulting DMJobs/DuplicateBlocks land atomically -
    either all of it is durable, or none of it is, so a redelivered webhook can never
    see "already processed" for an event whose jobs never actually got created.
    """

    job = DMJob(
        rule_id=rule_id,
        user_id=user_id,
        comment_id=comment_id,
        message=dm_message,
        status=DMJobStatus.QUEUED.value,
        attempts=0
    )

    try:
        async with db.begin_nested():
            db.add(job)
            await db.flush()
        logger.info(f"DMJob created: id={job.id}, rule_id={rule_id}, user_id={user_id}")
        return job
    except IntegrityError:
        logger.info(f"Duplicate DM attempt blocked by DB constraint: rule_id={rule_id}, user_id={user_id}, comment_id={comment_id}")

        # Record persistent duplicate block event for accurate /stats calculation
        block = DuplicateBlock(
            rule_id=rule_id,
            user_id=user_id,
            event_id=event_id,
            comment_id=comment_id,
            reason="user_rule_exists"
        )
        async with db.begin_nested():
            db.add(block)
            await db.flush()
        return None
