"""Stats API endpoint calculating metrics from database state."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.dm_job import DMJob
from app.schemas.stats import StatsResponse
from app.repositories.stats_repository import StatsRepository

router = APIRouter(tags=["Stats"])


@router.get("/stats", response_model=StatsResponse)
async def api_get_stats(
    db: AsyncSession = Depends(get_db)
):
    """
    Returns aggregated DM stats calculated directly from persistent database state.
    - sent: DMs confirmed as delivered by external API
    - failed: DM jobs permanently failed after retries
    - queued: DM jobs currently waiting to send or waiting for retry/status verification
    - duplicates_blocked: DM attempts prevented because user already received/was scheduled to receive a DM for the rule
    """
    stats_repo = StatsRepository(db)
    return await stats_repo.get_aggregated_stats()


@router.get("/api/jobs")
async def api_get_recent_jobs(
    db: AsyncSession = Depends(get_db)
):
    """Retrieve recent DM jobs for dashboard activity monitoring."""
    stmt = select(DMJob).order_by(DMJob.created_at.desc()).limit(20)
    res = await db.execute(stmt)
    jobs = res.scalars().all()
    return [
        {
            "id": j.id,
            "rule_id": j.rule_id,
            "user_id": j.user_id,
            "comment_id": j.comment_id,
            "status": j.status,
            "attempts": j.attempts,
            "dm_id": j.dm_id,
            "last_error": j.last_error,
            "created_at": j.created_at
        }
        for j in jobs
    ]
