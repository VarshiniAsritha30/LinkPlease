"""Durable background worker for sending DMs and reconciling delivery status."""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.dm_job import DMJob, DMJobStatus
from app.services.rate_limiter import dm_rate_limiter, RateLimiter
from app.services.retry_service import calculate_next_attempt, should_retry
from app.services.pseudogram_client import pseudogram_client, PseudogramClient
from app.utils.time import utc_now

logger = logging.getLogger(__name__)


class DMWorker:
    """Durable background worker managing rate limits, sending, and reconciliation."""

    def __init__(
        self,
        poll_interval: float = 1.0,
        session_factory=None,
        rate_limiter: Optional[RateLimiter] = None,
        api_client: Optional[PseudogramClient] = None,
    ):
        self.poll_interval = poll_interval
        self._session_factory = session_factory or AsyncSessionLocal
        self.rate_limiter = rate_limiter or dm_rate_limiter
        self.api_client = api_client or pseudogram_client
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def get_session(self):
        return self._session_factory()

    async def start(self):
        """Start the background worker loop."""
        self._running = True
        await self._recover_stale_jobs()
        self._task = asyncio.create_task(self._worker_loop())
        logger.info("DM Worker started successfully.")

    async def stop(self):
        """Stop the background worker loop gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("DM Worker stopped.")

    async def _recover_stale_jobs(self):
        """
        On application startup, recover any jobs that were left in 'sending' state
        due to a sudden server crash or restart.
        """
        async with self.get_session() as db:
            stmt = select(DMJob).where(DMJob.status == DMJobStatus.SENDING.value)
            result = await db.execute(stmt)
            stale_jobs = result.scalars().all()
            if stale_jobs:
                logger.warning(
                    "Process restart recovery: found stale jobs stuck in 'sending' state. Resetting to retry_wait.",
                    extra={"stale_jobs_count": len(stale_jobs)}
                )
                for job in stale_jobs:
                    job.status = DMJobStatus.RETRY_WAIT.value
                    job.next_attempt_at = utc_now()
                await db.commit()

    async def _worker_loop(self):
        """Main worker loop executing DM send and status reconciliation."""
        while self._running:
            try:
                await self._process_pending_jobs()
                await self._reconcile_accepted_jobs()
            except Exception as e:
                logger.error(
                    "Error in DM worker loop",
                    extra={"error": str(e)},
                    exc_info=True
                )
            
            await asyncio.sleep(self.poll_interval)

    async def _process_pending_jobs(self):
        """Fetch and execute pending or retryable DM jobs."""
        async with self.get_session() as db:
            now = utc_now()
            stmt = select(DMJob).where(
                DMJob.status.in_([DMJobStatus.QUEUED.value, DMJobStatus.RETRY_WAIT.value]),
                DMJob.next_attempt_at <= now
            ).order_by(DMJob.created_at.asc()).limit(5)

            result = await db.execute(stmt)
            jobs = result.scalars().all()

            for job in jobs:
                # Atomically claim job
                job.status = DMJobStatus.SENDING.value
                job.updated_at = utc_now()
                await db.commit()

                # Process job
                await self._send_job(job.id)

    async def _send_job(self, job_id: str):
        """Send DM for a specific job using rate limiter and external API client."""
        async with self.get_session() as db:
            job = await db.get(DMJob, job_id)
            if not job or job.status != DMJobStatus.SENDING.value:
                return

            # Wait for rate limit slot
            await self.rate_limiter.acquire()

            idempotency_key = f"dm-job-{job.id}"
            try:
                status_code, data, headers = await self.api_client.send_dm(
                    recipient_user_id=job.user_id,
                    message=job.message,
                    comment_id=job.comment_id,
                    idempotency_key=idempotency_key
                )

                if status_code in (200, 202):
                    dm_id = data.get("dm_id")
                    job.dm_id = dm_id
                    job.status = DMJobStatus.ACCEPTED.value
                    job.last_error = None
                    job.updated_at = utc_now()
                    logger.info(
                        "DMJob accepted by API",
                        extra={"job_id": job.id, "dm_id": dm_id, "status_code": status_code}
                    )

                elif status_code == 429:
                    retry_after_str = headers.get("Retry-After") or headers.get("retry-after")
                    retry_after = float(retry_after_str) if retry_after_str else 5.0
                    await self.rate_limiter.report_rate_limit(retry_after)

                    job.attempts += 1
                    error_msg = f"HTTP 429 Rate Limited (Retry-After: {retry_after}s)"
                    job.last_error = error_msg

                    if should_retry(job.attempts):
                        job.status = DMJobStatus.RETRY_WAIT.value
                        job.next_attempt_at = calculate_next_attempt(job.attempts, base_delay=retry_after)
                        logger.warning(
                            "DMJob rate limited. Retry scheduled",
                            extra={"job_id": job.id, "attempt": job.attempts, "next_attempt_at": str(job.next_attempt_at)}
                        )
                    else:
                        job.status = DMJobStatus.FAILED.value
                        logger.error(
                            "DMJob failed permanently after max attempts (429)",
                            extra={"job_id": job.id, "attempts": job.attempts}
                        )

                elif status_code == 400:
                    job.attempts += 1
                    job.status = DMJobStatus.FAILED.value
                    job.last_error = f"HTTP 400 Bad Request: {data.get('message', 'Invalid request')}"
                    job.updated_at = utc_now()
                    logger.error(
                        "DMJob permanently failed with HTTP 400",
                        extra={"job_id": job.id, "error": job.last_error}
                    )

                else:
                    job.attempts += 1
                    error_msg = f"HTTP {status_code}: {data}"
                    job.last_error = error_msg

                    if should_retry(job.attempts):
                        job.status = DMJobStatus.RETRY_WAIT.value
                        job.next_attempt_at = calculate_next_attempt(job.attempts)
                        logger.warning(
                            "DMJob failed with server error. Retry scheduled",
                            extra={"job_id": job.id, "status_code": status_code, "attempt": job.attempts}
                        )
                    else:
                        job.status = DMJobStatus.FAILED.value
                        logger.error(
                            "DMJob failed permanently after max attempts",
                            extra={"job_id": job.id, "attempts": job.attempts}
                        )

            except Exception as exc:
                job.attempts += 1
                job.last_error = f"Network Exception: {str(exc)}"
                if should_retry(job.attempts):
                    job.status = DMJobStatus.RETRY_WAIT.value
                    job.next_attempt_at = calculate_next_attempt(job.attempts)
                    logger.warning(
                        "DMJob network error. Retry scheduled",
                        extra={"job_id": job.id, "error": str(exc), "attempt": job.attempts}
                    )
                else:
                    job.status = DMJobStatus.FAILED.value
                    logger.error(
                        "DMJob failed permanently after network errors",
                        extra={"job_id": job.id, "error": str(exc), "attempts": job.attempts}
                    )

            job.updated_at = utc_now()
            await db.commit()

    async def _reconcile_accepted_jobs(self):
        """Periodically poll GET /v1/dm/{dm_id} for accepted DM jobs to verify delivery status."""
        async with self.get_session() as db:
            stmt = select(DMJob).where(
                DMJob.status == DMJobStatus.ACCEPTED.value,
                DMJob.dm_id.isnot(None)
            ).limit(10)

            result = await db.execute(stmt)
            jobs = result.scalars().all()

            for job in jobs:
                try:
                    status_code, data = await self.api_client.get_dm_status(job.dm_id)
                    if status_code == 200:
                        dm_status = data.get("status")
                        if dm_status == "delivered":
                            # Merge job into active session to avoid detached instance issues
                            db_job = await db.get(DMJob, job.id)
                            if db_job:
                                db_job.status = DMJobStatus.DELIVERED.value
                                db_job.updated_at = utc_now()
                                logger.info(
                                    "DMJob delivery confirmed",
                                    extra={"job_id": db_job.id, "dm_id": db_job.dm_id}
                                )

                        elif dm_status == "failed":
                            db_job = await db.get(DMJob, job.id)
                            if db_job:
                                db_job.attempts += 1
                                error_msg = f"Delivery failed according to external status check (dm_id={db_job.dm_id})"
                                db_job.last_error = error_msg
                                db_job.dm_id = None  # Clear dm_id for re-attempt

                                if should_retry(db_job.attempts):
                                    db_job.status = DMJobStatus.RETRY_WAIT.value
                                    db_job.next_attempt_at = calculate_next_attempt(db_job.attempts)
                                    logger.warning(
                                        "DMJob failed external delivery. Retry scheduled",
                                        extra={"job_id": db_job.id, "attempt": db_job.attempts}
                                    )
                                else:
                                    db_job.status = DMJobStatus.FAILED.value
                                    logger.error(
                                        "DMJob failed external delivery permanently",
                                        extra={"job_id": db_job.id}
                                    )

                        elif dm_status == "queued":
                            # Still queued remotely, keep waiting
                            pass

                except Exception as exc:
                    logger.warning(
                        "Error checking delivery status",
                        extra={"dm_id": job.dm_id, "error": str(exc)}
                    )

            await db.commit()


dm_worker = DMWorker(poll_interval=1.0)
