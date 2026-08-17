import pytest
from app.models.dm_job import DMJob, DMJobStatus
from app.models.duplicate_block import DuplicateBlock


@pytest.mark.asyncio
async def test_stats_endpoint_derived_from_db(client, db_session):
    # Add dummy jobs in different states
    job_delivered = DMJob(id="j1", rule_id="r1", user_id="u1", comment_id="c1", message="m", status=DMJobStatus.DELIVERED.value)
    job_failed = DMJob(id="j2", rule_id="r1", user_id="u2", comment_id="c2", message="m", status=DMJobStatus.FAILED.value)
    job_queued = DMJob(id="j3", rule_id="r1", user_id="u3", comment_id="c3", message="m", status=DMJobStatus.QUEUED.value)
    job_accepted = DMJob(id="j4", rule_id="r1", user_id="u4", comment_id="c4", message="m", status=DMJobStatus.ACCEPTED.value)

    block1 = DuplicateBlock(id="b1", rule_id="r1", user_id="u5", event_id="e1", comment_id="c5", reason="user_rule_exists")
    block2 = DuplicateBlock(id="b2", rule_id="r1", user_id="u6", event_id="e2", comment_id="c6", reason="user_rule_exists")

    db_session.add_all([job_delivered, job_failed, job_queued, job_accepted, block1, block2])
    await db_session.commit()

    res = await client.get("/stats")
    assert res.status_code == 200
    data = res.json()

    assert data["sent"] == 1
    assert data["failed"] == 1
    assert data["queued"] == 2  # job_queued + job_accepted
    assert data["duplicates_blocked"] == 2
