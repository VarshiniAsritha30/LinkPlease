import pytest
from sqlalchemy import select
from app.models.dm_job import DMJob, DMJobStatus
from app.workers.dm_worker import DMWorker


@pytest.mark.asyncio
async def test_process_restart_recovery(db_session, test_session_factory):
    # Simulate job stuck in 'sending' due to sudden restart
    job = DMJob(
        id="job_stuck",
        rule_id="r1",
        user_id="usr_stuck",
        comment_id="cmt_stuck",
        message="Message",
        status=DMJobStatus.SENDING.value
    )
    db_session.add(job)
    await db_session.commit()

    # Simulate worker restart recovery
    worker = DMWorker(session_factory=test_session_factory)
    await worker._recover_stale_jobs()

    await db_session.refresh(job)
    assert job.status == DMJobStatus.RETRY_WAIT.value
