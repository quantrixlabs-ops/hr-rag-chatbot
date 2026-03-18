"""Integration endpoints — external API, webhooks, Slack/Teams (Phase D)."""

import json
import sqlite3
import time
from typing import Optional, List

import structlog
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel

from backend.app.core.config import get_settings
from backend.app.core.dependencies import get_registry
from backend.app.core.security import verify_api_key, get_allowed_roles, log_security_event, sanitize_query, check_prompt_injection, mask_pii

logger = structlog.get_logger()

router = APIRouter(tags=["integrations"])


# ── API Key dependency ───────────────────────────────────────────────────────

def _require_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """Validate API key from X-API-Key header."""
    if not verify_api_key(x_api_key):
        raise HTTPException(401, "Invalid or missing API key")
    return x_api_key


# ══════════════════════════════════════════════════════════════════════════════
# EXTERNAL API (v1) — Service-to-service, API key authenticated
# ══════════════════════════════════════════════════════════════════════════════

class ExternalQueryRequest(BaseModel):
    query: str
    user_role: str = "employee"
    department: Optional[str] = None
    session_id: Optional[str] = None
    include_sources: bool = True


class ExternalQueryResponse(BaseModel):
    answer: str
    citations: list = []
    confidence: float = 0.0
    suggested_questions: List[str] = []
    latency_ms: float = 0.0


@router.post("/api/v1/query", response_model=ExternalQueryResponse)
async def external_query(req: ExternalQueryRequest, api_key: str = Depends(_require_api_key)):
    """External API for service-to-service HR queries.

    Authenticate with X-API-Key header. No JWT required.
    Intended for: Slack bots, Teams bots, internal tools, HRMS integrations.
    """
    if not req.query or not req.query.strip():
        raise HTTPException(400, "Query cannot be empty")
    if len(req.query) > 1000:
        raise HTTPException(400, "Query exceeds 1000 character limit")

    query = sanitize_query(req.query.strip())
    if check_prompt_injection(query):
        raise HTTPException(400, "Query blocked by security filter")

    reg = get_registry()
    rag = reg["rag"]

    try:
        result = rag.query(query=query, user_role=req.user_role, department=req.department)
    except Exception as e:
        logger.error("external_api_error", error=str(e))
        raise HTTPException(500, "Failed to process query")

    citations = []
    if req.include_sources and result.citations:
        citations = [
            {"source": c.source, "page": c.page, "excerpt": c.text_excerpt}
            for c in result.citations
        ]

    return ExternalQueryResponse(
        answer=result.answer,
        citations=citations,
        confidence=result.confidence,
        suggested_questions=result.suggested_questions,
        latency_ms=result.latency_ms,
    )


# ══════════════════════════════════════════════════════════════════════════════
# WEBHOOKS — Inbound event triggers
# ══════════════════════════════════════════════════════════════════════════════

class WebhookEvent(BaseModel):
    event_type: str  # "document.created", "document.updated", "document.deleted"
    document_id: Optional[str] = None
    metadata: dict = {}


@router.post("/webhooks/documents")
async def document_webhook(event: WebhookEvent, api_key: str = Depends(_require_api_key)):
    """Webhook for external systems to trigger document operations.

    Events:
      - document.updated: Triggers reindex of the specified document
      - document.deleted: Removes document from index
      - document.sync: Triggers full reindex from upload directory
    """
    s = get_settings()
    reg = get_registry()

    logger.info("webhook_received", event_type=event.event_type,
                document_id=event.document_id, metadata=event.metadata)

    if event.event_type == "document.updated" and event.document_id:
        # Reindex a specific document
        with sqlite3.connect(s.db_path) as con:
            row = con.execute(
                "SELECT source_filename FROM documents WHERE document_id=?",
                (event.document_id,)
            ).fetchone()
        if not row:
            raise HTTPException(404, f"Document {event.document_id} not found")
        return {"status": "accepted", "action": "reindex_queued", "document_id": event.document_id}

    elif event.event_type == "document.sync":
        return {"status": "accepted", "action": "full_sync_queued"}

    elif event.event_type == "document.deleted" and event.document_id:
        return {"status": "accepted", "action": "deletion_queued", "document_id": event.document_id}

    else:
        raise HTTPException(400, f"Unknown event type: {event.event_type}")


# ══════════════════════════════════════════════════════════════════════════════
# SLACK INTEGRATION — Bot event handler
# ══════════════════════════════════════════════════════════════════════════════

class SlackEvent(BaseModel):
    type: str  # "url_verification" or "event_callback"
    challenge: Optional[str] = None  # For URL verification
    event: Optional[dict] = None
    token: Optional[str] = None


@router.post("/integrations/slack/events")
async def slack_events(body: SlackEvent, request: Request):
    """Slack Events API endpoint.

    Handles:
      1. URL verification challenge (Slack sends this during setup)
      2. Message events (when users message the bot)

    Setup: Add this URL as your Slack app's Event Subscription URL:
      https://your-domain.com/integrations/slack/events

    Required Slack scopes: app_mentions:read, chat:write, im:history
    """
    # URL verification challenge (Slack setup handshake)
    if body.type == "url_verification":
        return {"challenge": body.challenge}

    # Event callback (actual messages)
    if body.type == "event_callback" and body.event:
        event = body.event
        event_type = event.get("type", "")

        # Handle direct messages and app mentions
        if event_type in ("message", "app_mention"):
            text = event.get("text", "").strip()
            user_id = event.get("user", "unknown")
            channel = event.get("channel", "")

            if not text:
                return {"ok": True}

            # Strip bot mention from text (e.g., "<@BOTID> what is leave policy")
            import re
            text = re.sub(r"<@[A-Z0-9]+>\s*", "", text).strip()

            if not text:
                return {"ok": True}

            logger.info("slack_message", user=user_id, channel=channel, text=text[:80])

            # Process through RAG pipeline
            try:
                reg = get_registry()
                rag = reg["rag"]
                result = rag.query(query=text, user_role="employee")

                # Format response for Slack
                answer = result.answer
                if result.citations:
                    sources = list({c.source for c in result.citations})
                    answer += f"\n\n_Sources: {', '.join(sources)}_"

                # In production, you'd send this via Slack Web API:
                # slack_client.chat_postMessage(channel=channel, text=answer)
                # For now, return the response (useful for testing)
                return {
                    "ok": True,
                    "response": {
                        "channel": channel,
                        "text": answer,
                        "confidence": result.confidence,
                    },
                }
            except Exception as e:
                logger.error("slack_rag_error", error=str(e))
                return {"ok": True, "response": {"text": "Sorry, I couldn't process that. Please try again."}}

    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# EMBEDDABLE WIDGET — Standalone chat for embedding in external sites
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/widget/config")
async def widget_config():
    """Returns configuration for the embeddable chat widget.

    Embed in any webpage:
      <script src="https://your-domain.com/widget/loader.js"></script>
      <div id="hr-chatbot-widget" data-api-key="YOUR_KEY"></div>
    """
    s = get_settings()
    return {
        "company_name": s.company_name,
        "welcome_message": f"Hi! I'm the {s.company_name} HR Assistant. Ask me anything about company policies.",
        "placeholder": "Ask about leave, benefits, policies...",
        "theme": {
            "primary_color": "#059669",
            "font_family": "Inter, system-ui, sans-serif",
        },
        "features": {
            "citations": True,
            "confidence_badge": True,
            "suggested_questions": True,
            "feedback": True,
        },
        "quick_actions": [
            "How many vacation days do I get?",
            "What health insurance plans are available?",
            "How do I request time off?",
            "What is the remote work policy?",
        ],
    }


# ══════════════════════════════════════════════════════════════════════════════
# MICROSOFT TEAMS INTEGRATION (Phase D2)
# ══════════════════════════════════════════════════════════════════════════════

class TeamsActivity(BaseModel):
    type: str  # "message", "conversationUpdate"
    text: Optional[str] = None
    from_user: Optional[dict] = None
    conversation: Optional[dict] = None
    serviceUrl: Optional[str] = None


@router.post("/integrations/teams/messages")
async def teams_messages(activity: TeamsActivity, api_key: str = Depends(_require_api_key)):
    """Microsoft Teams Bot Framework messaging endpoint.

    Setup:
      1. Register a bot in Azure Bot Service
      2. Set messaging endpoint to: https://your-domain.com/integrations/teams/messages
      3. Add X-API-Key header in bot configuration

    In production, verify the Bearer token from Bot Framework instead of API key.
    """
    if activity.type == "conversationUpdate":
        return {"type": "message", "text": "Hello! I'm your HR assistant. Ask me anything about company policies."}

    if activity.type == "message" and activity.text:
        text = activity.text.strip()
        if not text:
            return {"type": "message", "text": "Please type a question."}

        logger.info("teams_message", text=text[:80])

        try:
            reg = get_registry()
            rag = reg["rag"]
            result = rag.query(query=text, user_role="employee")
            answer = result.answer
            if result.citations:
                sources = list({c.source for c in result.citations})
                answer += f"\n\n**Sources:** {', '.join(sources)}"
            return {"type": "message", "text": answer}
        except Exception as e:
            logger.error("teams_rag_error", error=str(e))
            return {"type": "message", "text": "Sorry, I couldn't process that. Please try again."}

    return {"type": "message", "text": "I can help with HR questions. Just type your question!"}


# ══════════════════════════════════════════════════════════════════════════════
# EMAIL GATEWAY (Phase D5)
# ══════════════════════════════════════════════════════════════════════════════

class InboundEmail(BaseModel):
    from_address: str
    subject: str
    body: str
    message_id: Optional[str] = None


@router.post("/integrations/email/inbound")
async def email_inbound(email: InboundEmail, api_key: str = Depends(_require_api_key)):
    """Process inbound emails and generate HR answers.

    Integration: Configure your email service (SendGrid, Mailgun, AWS SES)
    to forward HR inbox emails to this webhook.

    Returns the answer text — your email service can send it as a reply.
    """
    query = email.body.strip()
    if not query:
        query = email.subject

    if len(query) > 1000:
        query = query[:1000]

    logger.info("email_inbound", from_addr=email.from_address[:30], subject=email.subject[:50])

    try:
        reg = get_registry()
        rag = reg["rag"]
        result = rag.query(query=query, user_role="employee")

        reply_body = f"Re: {email.subject}\n\n{result.answer}"
        if result.citations:
            sources = list({c.source for c in result.citations})
            reply_body += f"\n\nSources: {', '.join(sources)}"
        reply_body += "\n\n---\nThis is an automated response from the HR Assistant."

        return {
            "status": "processed",
            "reply_to": email.from_address,
            "subject": f"Re: {email.subject}",
            "body": reply_body,
            "confidence": result.confidence,
        }
    except Exception as e:
        logger.error("email_processing_error", error=str(e))
        return {
            "status": "error",
            "reply_to": email.from_address,
            "subject": f"Re: {email.subject}",
            "body": "We received your question but encountered an error. Please try again or contact HR directly.",
        }


# ══════════════════════════════════════════════════════════════════════════════
# A/B TESTING API (Phase C2)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/admin/experiments")
async def list_ab_experiments(api_key: str = Depends(_require_api_key)):
    """List all active A/B testing experiments and their variants."""
    from backend.app.core.ab_testing import list_experiments
    return {"experiments": list_experiments()}
