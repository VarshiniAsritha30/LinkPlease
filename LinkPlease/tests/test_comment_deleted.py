import pytest
from sqlalchemy import select
from app.models.dm_job import DMJob, DMJobStatus


@pytest.mark.asyncio
async def test_comment_deleted_before_send(client, db_session):
    # Rule
    await client.post("/rules", json={"keyword": "INFO", "dm_message": "Info DM"})

    # 1. Comment created
    await client.post("/webhook", json={
        "event_id": "evt_c1",
        "event_type": "comment.created",
        "data": {
            "comment_id": "cmt_to_delete",
            "text": "INFO please",
            "from": {"user_id": "usr_del_1"}
        }
    })

    # Verify job is queued
    stmt = select(DMJob).where(DMJob.comment_id == "cmt_to_delete")
    res = await db_session.execute(stmt)
    job = res.scalar_one()
    assert job.status == DMJobStatus.QUEUED.value

    # 2. Comment deleted webhook arrives BEFORE DM worker sends it
    await client.post("/webhook", json={
        "event_id": "evt_del_1",
        "event_type": "comment.deleted",
        "data": {
            "comment_id": "cmt_to_delete"
        }
    })

    # Verify job status updated to failed
    await db_session.rollback()
    await db_session.refresh(job)
    assert job.status == DMJobStatus.FAILED.value

    assert "Comment deleted before DM sent" in job.last_error

