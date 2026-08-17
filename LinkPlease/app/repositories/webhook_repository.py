"""Repository layer for webhook event and DM job database operations.

Separates all database access patterns from business logic in webhook_service.py.
All methods are typed, logged, and raise only SQLAlchemy exceptions — never HTTP exceptions.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dm_job import DMJob, DMJobStatus
from app.models.webhook_event import WebhookEvent

logger = logging.getLogger(__name__)


class WebhookRepository:
    """Data access object for WebhookEvent and related DMJob cancellation operations."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_event_by_id(self, event_id: str) -> Optional[WebhookEvent]:
        """Retrieve a WebhookEvent by its primary key. Returns None if not found."""
        return await self._db.get(WebhookEvent, event_id)

    async def persist_event(self, event: WebhookEvent) -> bool:
        """
        Attempt to persist a new WebhookEvent to the database.

        Returns True on success, False if an IntegrityError indicates a duplicate
        event_id was inserted concurrently (race condition guard).
        """
        try:
            async with self._db.begin_nested():
                self._db.add(event)
                await self._db.flush()
            logger.info(
                "WebhookEvent persisted",
                extra={"event_id": event.event_id, "event_type": event.event_type},
            )
            return True
        except IntegrityError:
            await self._db.rollback()
            logger.info(
                "Race condition: duplicate event_id caught by DB constraint",
                extra={"event_id": event.event_id},
            )
            return False

    async def mark_event_processed(self, event: WebhookEvent, status: str = "processed") -> None:
        """Update event status and processed_at timestamp."""
        event.status = status
        event.processed_at = datetime.now(timezone.utc)


    async def cancel_pending_jobs_for_comment(self, comment_id: str) -> int:
        """
        Cancel all QUEUED or RETRY_WAIT jobs associated with a deleted comment.

        Returns the count of jobs cancelled.
        """
        stmt = select(DMJob).where(
            DMJob.comment_id == comment_id,
            DMJob.status.in_([DMJobStatus.QUEUED.value, DMJobStatus.RETRY_WAIT.value]),
        )
        result = await self._db.execute(stmt)
        jobs_to_cancel = result.scalars().all()

        now = datetime.now(timezone.utc)
        for job in jobs_to_cancel:
            job.status = DMJobStatus.FAILED.value
            job.last_error = "Comment deleted before DM sent"
            job.updated_at = now
            logger.info(
                "DMJob cancelled due to comment deletion",
                extra={"job_id": job.id, "comment_id": comment_id},
            )

        return len(jobs_to_cancel)
