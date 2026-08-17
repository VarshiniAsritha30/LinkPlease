import pytest
from sqlalchemy import select
from app.models.dm_job import DMJob
from app.models.duplicate_block import DuplicateBlock


@pytest.mark.asyncio
async def test_duplicate_event_id(client, db_session):
    await client.post("/rules", json={"keyword": "PRICE", "dm_message": "Price list"})

    payload = {
        "event_id": "evt_dup_1",
        "event_type": "comment.created",
        "data": {
            "comment_id": "cmt_dup_1",
            "text": "PRICE please",
            "from": {"user_id": "usr_dup_1", "username": "user1"}
        }
    }

    # First attempt
    res1 = await client.post("/webhook", json=payload)
    assert res1.status_code == 200
    assert res1.json()["status"] == "success"

    # Second attempt with exact same event_id
    res2 = await client.post("/webhook", json=payload)
    assert res2.status_code == 200
    assert res2.json()["status"] == "success"
    assert "already processed" in res2.json()["message"]

    # Verify only ONE DMJob exists
    stmt = select(DMJob).where(DMJob.user_id == "usr_dup_1")
    res = await db_session.execute(stmt)
    assert len(res.scalars().all()) == 1


@pytest.mark.asyncio
async def test_same_user_different_comments_deduplication(client, db_session):
    # Rule
    rule_res = await client.post("/rules", json={"keyword": "INFO", "dm_message": "Info payload"})
    rule_id = rule_res.json()["rule_id"]

    # First comment from user_xyz
    payload1 = {
        "event_id": "evt_user_1",
        "event_type": "comment.created",
        "data": {
            "comment_id": "cmt_1",
            "text": "Need INFO",
            "from": {"user_id": "usr_xyz", "username": "user_xyz"}
        }
    }
    await client.post("/webhook", json=payload1)

    # Second comment from SAME user_xyz with different event_id and comment_id
    payload2 = {
        "event_id": "evt_user_2",
        "event_type": "comment.created",
        "data": {
            "comment_id": "cmt_2",
            "text": "INFO please again!",
            "from": {"user_id": "usr_xyz", "username": "user_xyz"}
        }
    }
    await client.post("/webhook", json=payload2)

    # Verify only ONE DMJob was created for usr_xyz
    stmt_jobs = select(DMJob).where(DMJob.user_id == "usr_xyz")
    res_jobs = await db_session.execute(stmt_jobs)
    jobs = res_jobs.scalars().all()
    assert len(jobs) == 1

    # Verify DuplicateBlock recorded for the second attempt
    stmt_blocks = select(DuplicateBlock).where(DuplicateBlock.user_id == "usr_xyz")
    res_blocks = await db_session.execute(stmt_blocks)
    blocks = res_blocks.scalars().all()
    assert len(blocks) == 1
    assert blocks[0].rule_id == rule_id


@pytest.mark.asyncio
async def test_different_users_same_rule(client, db_session):
    await client.post("/rules", json={"keyword": "DISCOUNT", "dm_message": "10% off code"})

    # User 1
    await client.post("/webhook", json={
        "event_id": "evt_u1",
        "event_type": "comment.created",
        "data": {"comment_id": "c1", "text": "DISCOUNT", "from": {"user_id": "usr_1"}}
    })

    # User 2
    await client.post("/webhook", json={
        "event_id": "evt_u2",
        "event_type": "comment.created",
        "data": {"comment_id": "c2", "text": "DISCOUNT", "from": {"user_id": "usr_2"}}
    })

    stmt = select(DMJob)
    res = await db_session.execute(stmt)
    jobs = res.scalars().all()
    assert len(jobs) == 2


@pytest.mark.asyncio
async def test_different_rules_same_user(client, db_session):
    # Rule 1
    await client.post("/rules", json={"keyword": "PRICE", "dm_message": "Price list"})
    # Rule 2
    await client.post("/rules", json={"keyword": "CATALOG", "dm_message": "Catalog pdf"})

    # Comment containing both keywords
    await client.post("/webhook", json={
        "event_id": "evt_both",
        "event_type": "comment.created",
        "data": {"comment_id": "c_both", "text": "Send me the PRICE and CATALOG", "from": {"user_id": "usr_multi"}}
    })

    stmt = select(DMJob).where(DMJob.user_id == "usr_multi")
    res = await db_session.execute(stmt)
    jobs = res.scalars().all()
    assert len(jobs) == 2
