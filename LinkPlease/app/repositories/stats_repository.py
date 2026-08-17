"""Repository layer for aggregated statistics queries.

Separates all stats-related database queries from the API route handler,
making the query logic independently testable and reusable.
"""

import logging

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dm_job import DMJob, DMJobStatus
from app.models.duplicate_block import DuplicateBlock
from app.schemas.stats import StatsResponse

logger = logging.getLogger(__name__)


class StatsRepository:
    """Data access object for aggregated DM statistics."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_aggregated_stats(self) -> StatsResponse:
        """
        Execute four count queries to build the current system-wide stats snapshot.

        All counts are derived directly from persistent database state — never from
        in-memory counters — ensuring accuracy after restarts.
        """
        # 1. Confirmed delivered DMs
        sent_res = await self._db.execute(
            select(func.count(DMJob.id)).where(DMJob.status == DMJobStatus.DELIVERED.value)
        )
        sent_count: int = sent_res.scalar_one_or_none() or 0

        # 2. Permanently failed DM jobs
        failed_res = await self._db.execute(
            select(func.count(DMJob.id)).where(DMJob.status == DMJobStatus.FAILED.value)
        )
        failed_count: int = failed_res.scalar_one_or_none() or 0

        # 3. In-flight jobs (queued, sending, accepted, retry_wait)
        queued_statuses = [
            DMJobStatus.QUEUED.value,
            DMJobStatus.SENDING.value,
            DMJobStatus.ACCEPTED.value,
            DMJobStatus.RETRY_WAIT.value,
        ]
        queued_res = await self._db.execute(
            select(func.count(DMJob.id)).where(DMJob.status.in_(queued_statuses))
        )
        queued_count: int = queued_res.scalar_one_or_none() or 0

        # 4. Duplicate DM attempts blocked by uniqueness constraint
        blocked_res = await self._db.execute(select(func.count(DuplicateBlock.id)))
        blocked_count: int = blocked_res.scalar_one_or_none() or 0

        logger.debug(
            "Stats aggregated",
            extra={
                "sent": sent_count,
                "failed": failed_count,
                "queued": queued_count,
                "duplicates_blocked": blocked_count,
            },
        )

        return StatsResponse(
            sent=sent_count,
            failed=failed_count,
            queued=queued_count,
            duplicates_blocked=blocked_count,
        )
