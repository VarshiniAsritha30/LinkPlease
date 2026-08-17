import hmac
import hashlib
import json
import pytest
from app.config import settings
from app.services.webhook_service import verify_signature


def test_hmac_signature_verification():
    secret = "secret_key_123"
    raw_body = b'{"event_id": "evt_test", "event_type": "comment.created"}'

    # Compute correct signature
    computed_hash = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    valid_header = f"sha256={computed_hash}"

    assert verify_signature(raw_body, valid_header, secret) is True
    assert verify_signature(raw_body, "sha256=invalid_hash", secret) is False
    assert verify_signature(raw_body, "", secret) is False


@pytest.mark.asyncio
async def test_webhook_signature_enforcement(client, monkeypatch):
    monkeypatch.setattr(settings, "WEBHOOK_SIGNATURE_REQUIRED", True)
    monkeypatch.setattr(settings, "PSEUDOGRAM_API_KEY", "test_key_abc")

    payload = {
        "event_id": "evt_sig_1",
        "event_type": "comment.created",
        "data": {"comment_id": "c1", "text": "hello"}
    }
    body_bytes = json.dumps(payload).encode("utf-8")

    # 1. Missing signature -> 401
    res = await client.post("/webhook", content=body_bytes, headers={"Content-Type": "application/json"})
    assert res.status_code == 401

    # 2. Invalid signature -> 401
    res = await client.post("/webhook", content=body_bytes, headers={
        "Content-Type": "application/json",
        "X-PseudoGram-Signature": "sha256=wrong"
    })
    assert res.status_code == 401

    # 3. Valid signature -> 200
    valid_sig = "sha256=" + hmac.new(b"test_key_abc", body_bytes, hashlib.sha256).hexdigest()
    res = await client.post("/webhook", content=body_bytes, headers={
        "Content-Type": "application/json",
        "X-PseudoGram-Signature": valid_sig
    })
    assert res.status_code == 200
