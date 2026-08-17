"""Webhook processing and signature verification service."""

import hmac
import hashlib
import logging
from typing import Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.webhook_event import WebhookEvent
from app.schemas.webhook import WebhookPayload
from app.services.rule_service import find_matching_rules
from app.services.dm_service import create_dm_job_for_rule
from app.repositories.webhook_repository import WebhookRepository
from app.utils.time import utc_now

logger = logging.getLogger(__name__)


def verify_signature(raw_body: bytes, signature_header: str, secret: str) -> bool:
    """
    Verify HMAC-SHA256 signature using constant-time comparison.
    Header format: 'sha256=<hex_hash>'
    """
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    
    expected_hash = signature_header.split("sha256=")[1]
    computed_hash = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed_hash, expected_hash)


async def process_incoming_webhook(db: AsyncSession, payload: WebhookPayload) -> Tuple[str, str]:
    """
    Persists the incoming webhook event and enqueues DM jobs if rules match.
    Returns tuple: (status, message).
    Fast execution (< 50ms) without waiting for external API calls.
    """
    event_id = payload.event_id
    event_type = payload.event_type
    comment_data = payload.data

    comment_id = comment_data.comment_id
    post_id = comment_data.post_id
    text = comment_data.text
    user_id = comment_data.from_user.user_id if comment_data.from_user else None
    username = comment_data.from_user.username if comment_data.from_user else None

    repo = WebhookRepository(db)

    # Step 1: Check for event-level duplicate in DB using WebhookRepository
    existing_event = await repo.get_event_by_id(event_id)
    if existing_event:
        logger.info(
            "Duplicate webhook event_id received. Returning 200 OK without reprocessing.",
            extra={"event_id": event_id}
        )
        return "duplicate", f"Event {event_id} already processed"

    # Step 2: Build new WebhookEvent
    event = WebhookEvent(
        event_id=event_id,
        event_type=event_type,
        comment_id=comment_id,
        user_id=user_id,
        username=username,
        post_id=post_id,
        text=text,
        received_at=utc_now(),
        status="received"
    )

    # Step 3: Persist via repository
    persisted = await repo.persist_event(event)
    if not persisted:
        return "duplicate", f"Event {event_id} already processed"

    # Step 4: Process event payload according to event_type
    if event_type == "comment.created":
        if text and user_id:
            matching_rules = await find_matching_rules(db, text)
            logger.info(
                "Matching rules found for webhook event",
                extra={"event_id": event_id, "rules_count": len(matching_rules)}
            )
            # Snapshot rule fields into plain values NOW, before any commit expires ORM objects
            rule_snapshots = [
                {"id": rule.id, "dm_message": rule.dm_message}
                for rule in matching_rules
            ]
            # Commit persisting the event before creating jobs
            await repo.mark_event_processed(event, status="processed")
            
            for snap in rule_snapshots:
                await create_dm_job_for_rule(
                    db=db,
                    rule_id=snap["id"],
                    dm_message=snap["dm_message"],
                    user_id=user_id,
                    comment_id=comment_id,
                    event_id=event_id
                )
            await db.commit()
        else:
            await repo.mark_event_processed(event, status="processed")
            await db.commit()
        return "processed", "Webhook received and jobs queued"

    elif event_type == "comment.deleted":
        logger.info(
            "Comment deletion webhook received",
            extra={"event_id": event_id, "comment_id": comment_id}
        )
        # Cancel any pending/retry_wait jobs for this comment_id using WebhookRepository
        cancelled_count = await repo.cancel_pending_jobs_for_comment(comment_id)
            
        await repo.mark_event_processed(event, status="processed")
        await db.commit()
        return "processed", f"Comment deletion processed, {cancelled_count} unsent jobs cancelled"

    else:
        await repo.mark_event_processed(event, status="ignored")
        await db.commit()
        return "ignored", f"Unhandled event_type '{event_type}'"
