"""Health check API endpoint.

Returns application liveness and database reachability in a format suitable
for Render healthCheckPath, Docker HEALTHCHECK, and load balancer probes.
This endpoint must NEVER raise an HTTP 5xx — it always returns 200 with a status field.
"""

import logging
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    """Structured health check response."""

    status: Literal["ok", "degraded"]
    worker_running: bool
    db_reachable: bool


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Application health check",
    description=(
        "Returns liveness status of the application, background DM worker, "
        "and database connectivity. Always returns HTTP 200 — check the "
        "`status` field to distinguish 'ok' from 'degraded'."
    ),
)
async def health_check(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    """
    Probe application health without raising exceptions.

    Checks:
    - Database reachability via a lightweight SELECT 1 query.
    - DM worker liveness via the module-level singleton's _running flag.
    """
    # Import here to avoid circular imports at module load time
    from app.workers.dm_worker import dm_worker

    db_reachable: bool
    try:
        await db.execute(text("SELECT 1"))
        db_reachable = True
    except Exception as exc:
        logger.warning("Health check: database unreachable", extra={"error": str(exc)})
        db_reachable = False

    worker_running: bool = dm_worker._running

    overall_status: Literal["ok", "degraded"] = (
        "ok" if (db_reachable and worker_running) else "degraded"
    )

    if overall_status == "degraded":
        logger.warning(
            "Health check degraded",
            extra={"db_reachable": db_reachable, "worker_running": worker_running},
        )

    return HealthResponse(
        status=overall_status,
        worker_running=worker_running,
        db_reachable=db_reachable,
    )
