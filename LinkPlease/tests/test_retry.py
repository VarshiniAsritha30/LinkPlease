import pytest
import respx
import httpx
from sqlalchemy import select
from app.config import settings
from app.workers.dm_worker import DMWorker
from app.models.dm_job import DMJob, DMJobStatus


@pytest.mark.asyncio
async def test_retry_on_500_error(db_session, test_session_factory):
    # Setup DM Job
    job = DMJob(
        id="job_500",
        rule_id="r1",
        user_id="usr_500",
        comment_id="cmt_500",
        message="Test DM",
        status=DMJobStatus.SENDING.value,
        attempts=0
    )
    db_session.add(job)
    await db_session.commit()

    # Mock external API returning 500
    with respx.mock(base_url=settings.PSEUDOGRAM_API_BASE_URL) as respx_mock:
        respx_mock.post("/v1/dm/send").mock(return_value=httpx.Response(500, json={"error": "Internal Server Error"}))

        worker = DMWorker(session_factory=test_session_factory)
        await worker._send_job("job_500")

    await db_session.refresh(job)
    assert job.status == DMJobStatus.RETRY_WAIT.value
    assert job.attempts == 1
    assert "HTTP 500" in job.last_error


@pytest.mark.asyncio
async def test_400_permanent_failure(db_session, test_session_factory):
    job = DMJob(
        id="job_400",
        rule_id="r1",
        user_id="usr_400",
        comment_id="cmt_400",
        message="Test DM",
        status=DMJobStatus.SENDING.value,
        attempts=0
    )
    db_session.add(job)
    await db_session.commit()

    with respx.mock(base_url=settings.PSEUDOGRAM_API_BASE_URL) as respx_mock:
        respx_mock.post("/v1/dm/send").mock(return_value=httpx.Response(400, json={"message": "Invalid recipient"}))

        worker = DMWorker(session_factory=test_session_factory)
        await worker._send_job("job_400")

    await db_session.refresh(job)
    assert job.status == DMJobStatus.FAILED.value
    assert job.attempts == 1
    assert "HTTP 400 Bad Request" in job.last_error


@pytest.mark.asyncio
async def test_202_accepted_and_reconciliation_to_delivered(db_session, test_session_factory):
    job = DMJob(
        id="job_202",
        rule_id="r1",
        user_id="usr_202",
        comment_id="cmt_202",
        message="Test DM",
        status=DMJobStatus.SENDING.value,
        attempts=0
    )
    db_session.add(job)
    await db_session.commit()

    # 1. Mock 202 response
    with respx.mock(base_url=settings.PSEUDOGRAM_API_BASE_URL) as respx_mock:
        respx_mock.post("/v1/dm/send").mock(return_value=httpx.Response(202, json={"dm_id": "dm_xyz", "status": "queued"}))

        worker = DMWorker(session_factory=test_session_factory)
        await worker._send_job("job_202")

    await db_session.refresh(job)
    assert job.status == DMJobStatus.ACCEPTED.value
    assert job.dm_id == "dm_xyz"

    # 2. Reconcile delivery status via GET /v1/dm/dm_xyz returning 'delivered'
    with respx.mock(base_url=settings.PSEUDOGRAM_API_BASE_URL) as respx_mock:
        respx_mock.get("/v1/dm/dm_xyz").mock(return_value=httpx.Response(200, json={"dm_id": "dm_xyz", "status": "delivered"}))

        await worker._reconcile_accepted_jobs()

    await db_session.rollback()
    await db_session.refresh(job)
    assert job.status == DMJobStatus.DELIVERED.value



