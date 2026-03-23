"""Webhook delivery system — Phase 4 (F-44).

Delivers async webhook notifications to tenant-configured endpoints.

Events that trigger webhooks:
  document.ingested   — document processed successfully
  document.failed     — document ingestion failed
  query.answered      — chat query answered (if tenant has webhook configured)
  user.created        — new user provisioned
  hrms.sync_done      — HRMS sync completed

Delivery:
  - POST to tenant webhook URL with signed payload (HMAC-SHA256)
  - Retry on failure: max 3 attempts with exponential backoff (30s→60s→120s)
  - After max retries: mark as failed (Phase 5: dead letter queue)

Payload format:
  {
    "event": "document.ingested",
    "tenant_id": "...",
    "timestamp": 1234567890.0,
    "data": { ... },
    "signature": "sha256=..."
  }

Signature verification (by webhook consumer):
  HMAC-SHA256(secret, payload_bytes)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Optional

import structlog

from backend.app.workers.celery_app import app

logger = structlog.get_logger()

# Delivery config
MAX_PAYLOAD_SIZE = 64 * 1024  # 64KB
WEBHOOK_TIMEOUT_SECONDS = 10


@app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="webhooks",
    acks_late=True,
    name="backend.app.workers.webhook_tasks.deliver_webhook",
)
def deliver_webhook(
    self,
    event: str,
    tenant_id: str,
    webhook_url: str,
    webhook_secret: str,
    data: dict,
) -> dict:
    """Deliver a webhook notification to the tenant's endpoint.

    Args:
        event:          Event type string (e.g. "document.ingested")
        tenant_id:      Tenant identifier
        webhook_url:    Target URL to POST to
        webhook_secret: HMAC signing secret (from tenant config)
        data:           Event-specific payload dict

    Returns delivery result dict.
    Retries on HTTP errors or timeouts with exponential backoff.
    """
    payload = {
        "event": event,
        "tenant_id": tenant_id,
        "timestamp": time.time(),
        "attempt": self.request.retries + 1,
        "data": data,
    }

    payload_bytes = json.dumps(payload, sort_keys=True).encode()

    # Enforce max payload size
    if len(payload_bytes) > MAX_PAYLOAD_SIZE:
        logger.warning("webhook_payload_too_large", event=event, size=len(payload_bytes))
        payload["data"] = {"truncated": True, "original_size": len(payload_bytes)}
        payload_bytes = json.dumps(payload, sort_keys=True).encode()

    signature = _sign_payload(payload_bytes, webhook_secret)
    payload["signature"] = f"sha256={signature}"
    payload_bytes = json.dumps(payload, sort_keys=True).encode()

    try:
        import httpx
    except ImportError:
        raise RuntimeError("httpx not installed — add to requirements.txt")

    try:
        with httpx.Client(timeout=WEBHOOK_TIMEOUT_SECONDS) as client:
            resp = client.post(
                webhook_url,
                content=payload_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-HR-Chatbot-Event": event,
                    "X-HR-Chatbot-Signature": f"sha256={signature}",
                    "X-HR-Chatbot-Timestamp": str(int(time.time())),
                },
            )

        if 200 <= resp.status_code < 300:
            logger.info(
                "webhook_delivered",
                event=event,
                tenant_id=tenant_id,
                url=webhook_url,
                status=resp.status_code,
            )
            return {
                "status": "delivered",
                "event": event,
                "http_status": resp.status_code,
                "attempts": self.request.retries + 1,
            }

        # 4xx = permanent failure (bad URL, auth, etc.) — don't retry
        if 400 <= resp.status_code < 500:
            logger.error(
                "webhook_client_error",
                event=event,
                tenant_id=tenant_id,
                status=resp.status_code,
                body=resp.text[:200],
            )
            return {
                "status": "failed",
                "reason": f"Client error {resp.status_code}",
                "permanent": True,
            }

        # 5xx = server error — retry
        raise httpx.HTTPStatusError(
            f"Server error {resp.status_code}",
            request=resp.request,
            response=resp,
        )

    except httpx.TimeoutException as exc:
        logger.warning(
            "webhook_timeout",
            event=event,
            tenant_id=tenant_id,
            attempt=self.request.retries + 1,
        )
        countdown = 30 * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)

    except httpx.HTTPStatusError as exc:
        countdown = 30 * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)

    except Exception as exc:
        logger.error("webhook_unexpected_error", event=event, error=str(exc))
        countdown = 30 * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)


def dispatch_webhook_if_configured(
    event: str,
    tenant_id: str,
    tenant_config: dict,
    data: dict,
) -> Optional[str]:
    """Convenience function: dispatch webhook if tenant has it configured.

    Returns the Celery task ID if dispatched, None if not configured.
    Call this from any part of the application that triggers events.

    Usage:
        dispatch_webhook_if_configured(
            event="document.ingested",
            tenant_id=tenant_id,
            tenant_config=current_tenant_config(),
            data={"document_id": doc_id, "filename": name},
        )
    """
    webhook_config = tenant_config.get("webhooks", {})
    webhook_url = webhook_config.get("url")
    webhook_secret = webhook_config.get("secret", "")

    if not webhook_url:
        return None

    # Only dispatch events the tenant has subscribed to
    subscribed_events = webhook_config.get("events", [])
    if subscribed_events and event not in subscribed_events:
        return None

    task = deliver_webhook.apply_async(
        kwargs={
            "event": event,
            "tenant_id": tenant_id,
            "webhook_url": webhook_url,
            "webhook_secret": webhook_secret,
            "data": data,
        },
        queue="webhooks",
    )

    logger.info(
        "webhook_dispatched",
        event=event,
        tenant_id=tenant_id,
        task_id=task.id,
    )
    return task.id


# ── Signature helper ──────────────────────────────────────────────────────────

def _sign_payload(payload_bytes: bytes, secret: str) -> str:
    """Create HMAC-SHA256 signature of the payload."""
    return hmac.new(
        secret.encode(),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()


def verify_webhook_signature(
    payload_bytes: bytes,
    signature_header: str,
    secret: str,
) -> bool:
    """Verify a webhook signature (for use by webhook consumers).

    signature_header: value of X-HR-Chatbot-Signature header (e.g. "sha256=abc...")
    Returns True if valid, False if tampered.
    """
    if not signature_header.startswith("sha256="):
        return False
    expected = _sign_payload(payload_bytes, secret)
    provided = signature_header[7:]  # Strip "sha256="
    return hmac.compare_digest(expected, provided)
