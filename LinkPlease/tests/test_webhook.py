import pytest
from sqlalchemy import select
from app.models.dm_job import DMJob


@pytest.mark.asyncio
async def test_webhook_creates_dm_job(client, db_session):
    # 1. Create a rule
    rule_res = await client.post("/rules", json={
        "keyword": "PRICE",
        "dm_message": "Price list link: https://example.com"
    })
    assert rule_res.status_code == 201

    # 2. Send matching webhook event
    payload = {
        "event_id": "evt_001",
        "event_type": "comment.created",
        "sent_at": "2026-08-10T09:14:22.481Z",
        "data": {
            "comment_id": "cmt_100",
            "post_id": "post_1",
            "text": "Can you send the PRICE please?",
            "created_at": "2026-08-10T09:14:21.900Z",
            "from": {
                "user_id": "usr_alpha",
                "username": "alpha_user"
            }
        }
    }

    res = await client.post("/webhook", json=payload)
    assert res.status_code == 200
    assert res.json()["status"] == "success"

    # 3. Verify DM job created in DB
    stmt = select(DMJob).where(DMJob.user_id == "usr_alpha")
    result = await db_session.execute(stmt)
    jobs = result.scalars().all()
    assert len(jobs) == 1
    assert jobs[0].comment_id == "cmt_100"
    assert jobs[0].status == "queued"


@pytest.mark.asyncio
async def test_webhook_non_matching_comment(client, db_session):
    # Send non-matching comment
    payload = {
        "event_id": "evt_002",
        "event_type": "comment.created",
        "data": {
            "comment_id": "cmt_101",
            "text": "Lovely picture!",
            "from": {"user_id": "usr_beta", "username": "beta_user"}
        }
    }

    res = await client.post("/webhook", json=payload)
    assert res.status_code == 200

    stmt = select(DMJob).where(DMJob.user_id == "usr_beta")
    result = await db_session.execute(stmt)
    jobs = result.scalars().all()
    assert len(jobs) == 0
