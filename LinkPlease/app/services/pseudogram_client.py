"""HTTP Client for interacting with the external Pseudogram API.

Now supports a persistent httpx.AsyncClient connection pool to prevent socket exhaustion.
"""

import logging
from typing import Dict, Any, Tuple, Optional
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


class PseudogramClient:
    """Persistent HTTP client interacting with the external Pseudogram API."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.base_url = (base_url or settings.PSEUDOGRAM_API_BASE_URL).rstrip("/")
        self.api_key = api_key or settings.PSEUDOGRAM_API_KEY
        self.client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        """Initialize the persistent async HTTP client session."""
        if not self.client:
            self.client = httpx.AsyncClient(timeout=10.0)
            logger.info("Persistent httpx.AsyncClient session started.")

    async def stop(self) -> None:
        """Close the persistent async HTTP client session."""
        if self.client:
            await self.client.aclose()
            self.client = None
            logger.info("Persistent httpx.AsyncClient session closed.")

    def _get_headers(self, idempotency_key: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    async def send_dm(
        self,
        recipient_user_id: str,
        message: str,
        comment_id: str,
        idempotency_key: str
    ) -> Tuple[int, Dict[str, Any], Dict[str, str]]:
        """
        Send a DM via POST /v1/dm/send.
        Returns tuple of (status_code, response_json, response_headers).
        """
        url = f"{self.base_url}/v1/dm/send"
        payload = {
            "recipient_user_id": recipient_user_id,
            "message": message,
            "comment_id": comment_id
        }
        headers = self._get_headers(idempotency_key=idempotency_key)

        # Fallback to local client if start() was not called (e.g. in tests)
        active_client = self.client or httpx.AsyncClient(timeout=10.0)
        try:
            response = await active_client.post(url, json=payload, headers=headers)
            try:
                data = response.json()
            except Exception:
                data = {"raw_content": response.text}
            return response.status_code, data, dict(response.headers)
        except httpx.RequestError as exc:
            logger.error(
                "HTTP request error calling send_dm",
                extra={"error": str(exc), "recipient": recipient_user_id}
            )
            raise
        finally:
            if not self.client:
                await active_client.aclose()

    async def get_dm_status(self, dm_id: str) -> Tuple[int, Dict[str, Any]]:
        """
        Check status of a sent DM via GET /v1/dm/{dm_id}.
        Returns tuple of (status_code, response_json).
        """
        url = f"{self.base_url}/v1/dm/{dm_id}"
        headers = self._get_headers()

        active_client = self.client or httpx.AsyncClient(timeout=10.0)
        try:
            response = await active_client.get(url, headers=headers)
            try:
                data = response.json()
            except Exception:
                data = {"raw_content": response.text}
            return response.status_code, data
        except httpx.RequestError as exc:
            logger.error(
                "HTTP request error calling get_dm_status",
                extra={"error": str(exc), "dm_id": dm_id}
            )
            raise
        finally:
            if not self.client:
                await active_client.aclose()


pseudogram_client = PseudogramClient()
