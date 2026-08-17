import asyncio
import pytest
from sqlalchemy import select
from app.models.dm_job import DMJob
from app.models.duplicate_block import DuplicateBlock


@pytest.mark.asyncio
async def test_concurrent_webhooks_same_user(client, session_factory):
    # Create rule
    await client.post("/rules", json={"keyword": "PRICE", "dm_message": "Price details"})

    # Two webhook payloads from the SAME user arriving simultaneously
    payload1 = {
        "event_id": "evt_conc_1",
        "event_type": "comment.created",
        "data": {
            "comment_id": "cmt_conc_1",
            "text": "PRICE please!",
            "from": {"user_id": "usr_concurrent", "username": "user_conc"}
        }
    }

    payload2 = {
        "event_id": "evt_conc_2",
        "event_type": "comment.created",
        "data": {
            "comment_id": "cmt_conc_2",
            "text": "What is the PRICE?",
            "from": {"user_id": "usr_concurrent", "username": "user_conc"}
        }
    }

    # Execute both webhook POST requests concurrently using asyncio.gather
    res1, res2 = await asyncio.gather(
        client.post("/webhook", json=payload1),
        client.post("/webhook", json=payload2)
    )

    assert res1.status_code == 200
    assert res2.status_code == 200

    # Query fresh session to verify database state
    async with session_factory() as session:
        stmt_jobs = select(DMJob).where(DMJob.user_id == "usr_concurrent")
        res_jobs = await session.execute(stmt_jobs)
        jobs = res_jobs.scalars().all()
        assert len(jobs) == 1

        stmt_blocks = select(DuplicateBlock).where(DuplicateBlock.user_id == "usr_concurrent")
        res_blocks = await session.execute(stmt_blocks)
        blocks = res_blocks.scalars().all()
        assert len(blocks) == 1
