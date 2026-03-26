"""AI Configuration — Admin-only API for managing external AI providers.

Endpoints for CRUD operations on AI providers (API keys encrypted at rest)
and usage analytics. ONLY accessible to admin/super_admin roles.
"""

from __future__ import annotations

import sqlite3
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

import structlog

from backend.app.core.config import get_settings
from backend.app.core.encryption import encrypt_field, decrypt_field
from backend.app.core.security import get_current_user, require_role, log_security_event
from backend.app.models.chat_models import User
from backend.app.services.ai_router import SUPPORTED_PROVIDERS

logger = structlog.get_logger()
router = APIRouter(prefix="/ai-config", tags=["ai-config"])

_ADMIN_ROLES = {"admin", "super_admin"}


def _require_admin(user: User):
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(403, "Only system administrators can access AI configuration")


# ── Models ────────────────────────────────────────────────────────────────────

class CreateProviderRequest(BaseModel):
    provider_name: str       # openai, claude, gemini, groq, perplexity, grok
    api_key: str
    model_name: str = ""
    base_url: str = ""
    priority: int = 10
    max_tokens: int = 1024
    temperature: float = 0.0
    status: str = "active"   # active / inactive
    usage_limit: int = 0     # 0 = unlimited


class UpdateProviderRequest(BaseModel):
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    base_url: Optional[str] = None
    priority: Optional[int] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    status: Optional[str] = None
    usage_limit: Optional[int] = None


# ── AI Mode: internal (Ollama) vs external (API) ─────────────────────────────

class SetAiModeRequest(BaseModel):
    ai_mode: str           # "internal" or "external"
    active_provider: str = ""  # required when mode is "external"


@router.get("/mode")
async def get_ai_mode(user: User = Depends(get_current_user)):
    """Get current AI mode (internal Ollama vs external API)."""
    _require_admin(user)
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT ai_mode, active_provider, updated_by, updated_at FROM ai_settings WHERE id = 1"
        ).fetchone()

    if not row:
        return {"ai_mode": "internal", "active_provider": "", "updated_by": "", "updated_at": None}

    # Get provider display name if external
    provider_display = ""
    provider_model = ""
    if row[0] == "external" and row[1]:
        with sqlite3.connect(s.db_path) as con:
            p = con.execute(
                "SELECT display_name, model_name FROM ai_providers WHERE provider_name = ? AND status = 'active'",
                (row[1],)
            ).fetchone()
            if p:
                provider_display = p[0]
                provider_model = p[1]

    return {
        "ai_mode": row[0],
        "active_provider": row[1],
        "provider_display_name": provider_display,
        "provider_model": provider_model,
        "updated_by": row[2] or "",
        "updated_at": row[3],
    }


@router.post("/mode")
async def set_ai_mode(req: SetAiModeRequest, user: User = Depends(get_current_user)):
    """Switch between internal AI (Ollama) and external API provider."""
    _require_admin(user)

    if req.ai_mode not in ("internal", "external"):
        raise HTTPException(400, "ai_mode must be 'internal' or 'external'")

    s = get_settings()

    if req.ai_mode == "external":
        if not req.active_provider:
            raise HTTPException(400, "active_provider is required when switching to external mode")
        # Verify provider exists and is active
        with sqlite3.connect(s.db_path) as con:
            p = con.execute(
                "SELECT provider_name, display_name, model_name FROM ai_providers "
                "WHERE provider_name = ? AND status = 'active'",
                (req.active_provider.lower(),)
            ).fetchone()
        if not p:
            raise HTTPException(400, f"Provider '{req.active_provider}' not found or not active. Add and activate it first.")

    now = time.time()
    with sqlite3.connect(s.db_path) as con:
        con.execute(
            "INSERT OR REPLACE INTO ai_settings (id, ai_mode, active_provider, updated_by, updated_at) "
            "VALUES (1, ?, ?, ?, ?)",
            (req.ai_mode, req.active_provider.lower() if req.ai_mode == "external" else "",
             user.user_id, now),
        )

    log_security_event("ai_mode_changed", {
        "mode": req.ai_mode,
        "provider": req.active_provider if req.ai_mode == "external" else "ollama",
    }, user_id=user.user_id)

    mode_label = f"External API ({req.active_provider})" if req.ai_mode == "external" else "Internal AI (Ollama)"
    logger.info("ai_mode_switched", mode=req.ai_mode,
                provider=req.active_provider if req.ai_mode == "external" else "ollama")

    return {
        "status": "updated",
        "ai_mode": req.ai_mode,
        "active_provider": req.active_provider if req.ai_mode == "external" else "",
        "message": f"AI mode switched to: {mode_label}",
    }


# ── Provider Management ───────────────────────────────────────────────────────

@router.get("/providers/supported")
async def list_supported_providers(user: User = Depends(get_current_user)):
    """List all supported external AI providers."""
    _require_admin(user)
    return {
        "providers": [
            {"name": k, "display_name": v["display_name"],
             "default_model": v["default_model"], "default_url": v["default_url"]}
            for k, v in SUPPORTED_PROVIDERS.items()
        ]
    }


@router.post("/providers")
async def create_provider(req: CreateProviderRequest, user: User = Depends(get_current_user)):
    """Add a new external AI provider. API key is encrypted before storage."""
    _require_admin(user)

    name = req.provider_name.lower().strip()
    if name not in SUPPORTED_PROVIDERS:
        raise HTTPException(400, f"Unsupported provider '{name}'. Supported: {', '.join(SUPPORTED_PROVIDERS.keys())}")
    if not req.api_key.strip():
        raise HTTPException(400, "API key is required")
    if req.status not in ("active", "inactive"):
        raise HTTPException(400, "Status must be 'active' or 'inactive'")

    s = get_settings()
    defaults = SUPPORTED_PROVIDERS[name]
    model = req.model_name.strip() or defaults["default_model"]
    url = req.base_url.strip() or defaults["default_url"]
    now = time.time()

    # Encrypt API key before storage
    encrypted_key = encrypt_field(req.api_key.strip())

    with sqlite3.connect(s.db_path) as con:
        # Check for duplicate provider
        existing = con.execute(
            "SELECT id FROM ai_providers WHERE provider_name = ?", (name,)
        ).fetchone()
        if existing:
            raise HTTPException(409, f"Provider '{name}' already exists. Use PUT to update.")

        con.execute(
            "INSERT INTO ai_providers "
            "(provider_name, display_name, api_key_encrypted, model_name, base_url, "
            "status, priority, max_tokens, temperature, usage_limit, "
            "created_by, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (name, defaults["display_name"], encrypted_key, model, url,
             req.status, req.priority, req.max_tokens, req.temperature,
             req.usage_limit, user.user_id, now, now),
        )

    log_security_event("ai_provider_created", {
        "provider": name, "model": model, "status": req.status,
    }, user_id=user.user_id)

    return {"status": "created", "provider": name, "model": model}


@router.get("/providers")
async def list_providers(user: User = Depends(get_current_user)):
    """List all configured AI providers. API keys are masked."""
    _require_admin(user)
    s = get_settings()

    with sqlite3.connect(s.db_path) as con:
        rows = con.execute(
            "SELECT id, provider_name, display_name, model_name, base_url, "
            "status, priority, max_tokens, temperature, usage_count, usage_limit, "
            "created_by, created_at, updated_at "
            "FROM ai_providers ORDER BY priority ASC"
        ).fetchall()

    return {
        "providers": [{
            "id": r[0], "provider_name": r[1], "display_name": r[2],
            "model_name": r[3], "base_url": r[4],
            "status": r[5], "priority": r[6],
            "max_tokens": r[7], "temperature": r[8],
            "usage_count": r[9], "usage_limit": r[10],
            "api_key_configured": True,  # Never expose actual key
            "created_by": r[11], "created_at": r[12], "updated_at": r[13],
        } for r in rows],
    }


@router.put("/providers/{provider_name}")
async def update_provider(
    provider_name: str, req: UpdateProviderRequest,
    user: User = Depends(get_current_user),
):
    """Update an existing provider's settings."""
    _require_admin(user)
    s = get_settings()
    now = time.time()

    with sqlite3.connect(s.db_path) as con:
        existing = con.execute(
            "SELECT id FROM ai_providers WHERE provider_name = ?",
            (provider_name.lower(),)
        ).fetchone()
        if not existing:
            raise HTTPException(404, f"Provider '{provider_name}' not found")

        updates = ["updated_at = ?"]
        params: list = [now]

        if req.api_key is not None and req.api_key.strip():
            updates.append("api_key_encrypted = ?")
            params.append(encrypt_field(req.api_key.strip()))
        if req.model_name is not None:
            updates.append("model_name = ?")
            params.append(req.model_name.strip())
        if req.base_url is not None:
            updates.append("base_url = ?")
            params.append(req.base_url.strip())
        if req.priority is not None:
            updates.append("priority = ?")
            params.append(req.priority)
        if req.max_tokens is not None:
            updates.append("max_tokens = ?")
            params.append(req.max_tokens)
        if req.temperature is not None:
            updates.append("temperature = ?")
            params.append(req.temperature)
        if req.status is not None:
            if req.status not in ("active", "inactive"):
                raise HTTPException(400, "Status must be 'active' or 'inactive'")
            updates.append("status = ?")
            params.append(req.status)
        if req.usage_limit is not None:
            updates.append("usage_limit = ?")
            params.append(req.usage_limit)

        params.append(provider_name.lower())
        con.execute(
            f"UPDATE ai_providers SET {', '.join(updates)} WHERE provider_name = ?",
            params,
        )

    log_security_event("ai_provider_updated", {
        "provider": provider_name, "fields_changed": len(updates) - 1,
    }, user_id=user.user_id)

    return {"status": "updated", "provider": provider_name}


@router.delete("/providers/{provider_name}")
async def delete_provider(provider_name: str, user: User = Depends(get_current_user)):
    """Remove an external AI provider."""
    _require_admin(user)
    s = get_settings()

    with sqlite3.connect(s.db_path) as con:
        existing = con.execute(
            "SELECT id FROM ai_providers WHERE provider_name = ?",
            (provider_name.lower(),)
        ).fetchone()
        if not existing:
            raise HTTPException(404, f"Provider '{provider_name}' not found")
        con.execute("DELETE FROM ai_providers WHERE provider_name = ?", (provider_name.lower(),))

    log_security_event("ai_provider_deleted", {"provider": provider_name}, user_id=user.user_id)
    return {"status": "deleted", "provider": provider_name}


@router.post("/providers/{provider_name}/test")
async def test_provider(provider_name: str, user: User = Depends(get_current_user)):
    """Test connectivity to an external AI provider."""
    _require_admin(user)
    s = get_settings()

    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT api_key_encrypted, model_name, base_url, max_tokens, temperature "
            "FROM ai_providers WHERE provider_name = ?",
            (provider_name.lower(),)
        ).fetchone()
    if not row:
        raise HTTPException(404, f"Provider '{provider_name}' not found")

    from backend.app.services.ai_router import call_external_provider, ProviderConfig
    provider = ProviderConfig(
        id=0, provider_name=provider_name.lower(),
        api_key=decrypt_field(row[0]),
        model_name=row[1], base_url=row[2],
        priority=0, max_tokens=row[3] or 50,
        temperature=row[4] if row[4] is not None else 0.0,
    )
    # Override max_tokens for test (keep it cheap)
    provider.max_tokens = 50

    t0 = time.time()
    try:
        result = call_external_provider(provider, "Reply with exactly: OK")
        ms = (time.time() - t0) * 1000
        return {
            "status": "success", "provider": provider_name,
            "model": provider.model_name,
            "response_preview": result.text[:100],
            "latency_ms": round(ms),
        }
    except Exception as e:
        ms = (time.time() - t0) * 1000
        return {
            "status": "error", "provider": provider_name,
            "error": str(e)[:200],
            "latency_ms": round(ms),
        }


# ── Usage Analytics ───────────────────────────────────────────────────────────

@router.get("/usage")
async def get_usage_analytics(
    user: User = Depends(get_current_user),
    days: int = Query(7, ge=1, le=90),
):
    """Get AI provider usage analytics."""
    _require_admin(user)
    s = get_settings()
    cutoff = time.time() - (days * 86400)

    with sqlite3.connect(s.db_path) as con:
        # Per-provider summary
        provider_stats = con.execute(
            "SELECT provider_name, COUNT(*) as calls, "
            "SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) as successes, "
            "AVG(response_time_ms) as avg_latency, "
            "SUM(prompt_tokens) as total_prompt_tokens, "
            "SUM(completion_tokens) as total_completion_tokens "
            "FROM ai_usage_logs WHERE timestamp > ? "
            "GROUP BY provider_name ORDER BY calls DESC",
            (cutoff,),
        ).fetchall()

        # Fallback events
        fallbacks = con.execute(
            "SELECT fallback_from, provider_name, COUNT(*) "
            "FROM ai_usage_logs WHERE fallback_from != '' AND timestamp > ? "
            "GROUP BY fallback_from, provider_name",
            (cutoff,),
        ).fetchall()

        # Recent errors
        errors = con.execute(
            "SELECT provider_name, error_message, timestamp "
            "FROM ai_usage_logs WHERE success = 0 AND timestamp > ? "
            "ORDER BY timestamp DESC LIMIT 20",
            (cutoff,),
        ).fetchall()

    return {
        "period_days": days,
        "providers": [{
            "provider": r[0], "total_calls": r[1], "successes": r[2],
            "success_rate": round(r[2] / r[1] * 100, 1) if r[1] > 0 else 0,
            "avg_latency_ms": round(r[3] or 0), "total_prompt_tokens": r[4] or 0,
            "total_completion_tokens": r[5] or 0,
        } for r in provider_stats],
        "fallback_events": [{
            "from": r[0], "to": r[1], "count": r[2],
        } for r in fallbacks],
        "recent_errors": [{
            "provider": r[0], "error": r[1][:100], "timestamp": r[2],
        } for r in errors],
    }


# ── Model Routing Configuration ───────────────────────────────────────────────

class SetRoutingModelRequest(BaseModel):
    tier: str           # "fast", "standard", "advanced"
    model_name: str     # e.g., "gemma3:4b", "llama3:8b"
    is_enabled: bool = True


@router.get("/routing")
async def get_model_routing(user: User = Depends(get_current_user)):
    """Get current model routing configuration (which model handles which query tier)."""
    _require_admin(user)
    from backend.app.rag.model_router import get_routing_config, TIER_FAST, TIER_STANDARD, TIER_ADVANCED
    s = get_settings()

    config = get_routing_config(s.db_path)

    # Show defaults for any unconfigured tiers
    tier_defaults = {
        TIER_FAST: s.model_fast or s.llm_model,
        TIER_STANDARD: s.model_standard or s.llm_model,
        TIER_ADVANCED: s.model_advanced or s.llm_model,
    }
    tier_descriptions = {
        TIER_FAST: "Simple queries — FAQ, basic lookups, greetings",
        TIER_STANDARD: "Moderate queries — most HR policy questions",
        TIER_ADVANCED: "Complex queries — calculations, sensitive topics, multi-step reasoning",
    }
    configured_tiers = {c["tier"] for c in config}
    for tier in (TIER_FAST, TIER_STANDARD, TIER_ADVANCED):
        if tier not in configured_tiers:
            config.append({
                "tier": tier, "model_name": tier_defaults[tier],
                "is_enabled": True, "description": tier_descriptions[tier],
                "updated_at": None, "is_default": True,
            })

    config.sort(key=lambda x: [TIER_FAST, TIER_STANDARD, TIER_ADVANCED].index(x["tier"]))

    return {
        "routing": config,
        "default_model": s.llm_model,
        "available_tiers": [
            {"tier": TIER_FAST, "label": "Fast (Simple)", "description": tier_descriptions[TIER_FAST]},
            {"tier": TIER_STANDARD, "label": "Standard", "description": tier_descriptions[TIER_STANDARD]},
            {"tier": TIER_ADVANCED, "label": "Advanced (Complex)", "description": tier_descriptions[TIER_ADVANCED]},
        ],
    }


@router.post("/routing")
async def set_model_routing(req: SetRoutingModelRequest, user: User = Depends(get_current_user)):
    """Set which Ollama model handles a specific query tier."""
    _require_admin(user)
    from backend.app.rag.model_router import set_routing_model, TIER_FAST, TIER_STANDARD, TIER_ADVANCED

    if req.tier not in (TIER_FAST, TIER_STANDARD, TIER_ADVANCED):
        raise HTTPException(400, f"Tier must be: {TIER_FAST}, {TIER_STANDARD}, or {TIER_ADVANCED}")
    if not req.model_name.strip():
        raise HTTPException(400, "Model name is required")

    s = get_settings()
    set_routing_model(s.db_path, req.tier, req.model_name.strip(), req.is_enabled)

    log_security_event("model_routing_changed", {
        "tier": req.tier, "model": req.model_name, "enabled": req.is_enabled,
    }, user_id=user.user_id)

    return {
        "status": "updated",
        "tier": req.tier,
        "model_name": req.model_name,
        "message": f"Tier '{req.tier}' now uses model '{req.model_name}'",
    }
