"""Webhook API endpoint receiving comment events."""

import json
import logging
from fastapi import APIRouter, Request, HTTPException, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.schemas.webhook import WebhookPayload, WebhookResponse
from app.services.webhook_service import verify_signature, process_incoming_webhook

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Webhook"])


@router.post("/webhook", response_model=WebhookResponse, status_code=status.HTTP_200_OK)
async def api_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_pseudogram_signature: str = Header(None, alias="X-PseudoGram-Signature")
):
    """
    Public webhook receiver endpoint.
    Processes comment events, validates optional HMAC signature, and returns HTTP 200 OK fast.
    """
    raw_body = await request.body()

    # Step 1: Signature Verification if required
    if settings.WEBHOOK_SIGNATURE_REQUIRED:
        if not x_pseudogram_signature or not verify_signature(raw_body, x_pseudogram_signature, settings.PSEUDOGRAM_API_KEY):
            logger.warning("Webhook request rejected: invalid or missing HMAC signature.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing X-PseudoGram-Signature header"
            )

    # Step 2: Parse payload JSON
    try:
        data = json.loads(raw_body.decode("utf-8"))
        payload = WebhookPayload(**data)
    except Exception as exc:
        logger.error(f"Malformed webhook payload: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid webhook JSON payload: {str(exc)}"
        )

    # Step 3: Process event in DB
    status_code_name, message = await process_incoming_webhook(db, payload)

    return WebhookResponse(
        status="success" if status_code_name in ("processed", "duplicate") else "ignored",
        message=message,
        event_id=payload.event_id
    )
