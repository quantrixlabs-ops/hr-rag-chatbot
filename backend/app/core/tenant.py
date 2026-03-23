"""Multi-tenancy enforcement — Phase 3.

Tenant resolution priority (per request):
  1. JWT claim `tenant_id` (authenticated requests — most trusted, signed)
  2. X-Tenant-Slug header (API clients, SSO login flow)
  3. Default tenant (single-tenant fallback / dev mode)

Tenant config is Redis-cached (5-min TTL) to avoid DB hit per request.

Phase 5 hook: PostgreSQL Row-Level Security can enforce tenant_id at DB level
as a second enforcement layer on top of this middleware filter.
"""

from __future__ import annotations

import contextvars
import json
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional, Tuple

import structlog

logger = structlog.get_logger()

# ── Request-scoped context vars ───────────────────────────────────────────────
_current_tenant_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_tenant_id", default="default"
)
_current_tenant_config: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "current_tenant_config", default={}
)

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_TENANT_SLUG = "default"

# ── Default config (used when no tenant config exists or for default tenant) ──
DEFAULT_CONFIG: dict = {
    "llm_model": "llama3:8b",
    "chunk_size": 400,
    "max_context_turns": 10,
    "rate_limits": {
        "queries_per_hour": 500,
        "uploads_per_day": 50,
    },
    "features": {
        "sso": False,
        "memory_summarization": True,
        "document_versioning": True,
        "async_ingestion": True,
        "audit_logging": True,
    },
    "sso": {},
    "branding": {
        "company_name": "Your Company",
        "primary_color": "#2563EB",
    },
}


# ── Public accessors ──────────────────────────────────────────────────────────

def get_current_tenant() -> str:
    """Current tenant_id for this request (ContextVar — async-safe)."""
    return _current_tenant_id.get()


def get_current_tenant_config() -> dict:
    """Current tenant config dict for this request."""
    return _current_tenant_config.get()


def set_current_tenant(tenant_id: str, config: Optional[dict] = None) -> None:
    """Set tenant context for this request. Called by TenantMiddleware."""
    _current_tenant_id.set(tenant_id)
    _current_tenant_config.set(config or DEFAULT_CONFIG)


def tenant_filter(base_query: str, params: tuple, tenant_id: Optional[str] = None) -> tuple:
    """Append tenant_id filter to a raw SQL query.

    Usage:
        q, p = tenant_filter("SELECT * FROM documents WHERE category=?", ("policy",))
        # → "SELECT * FROM documents WHERE category=? AND tenant_id=?", ("policy", "default")
    """
    tid = tenant_id or get_current_tenant()
    if "WHERE" in base_query.upper():
        return base_query + " AND tenant_id=?", params + (tid,)
    return base_query + " WHERE tenant_id=?", params + (tid,)


def feature_enabled(feature_name: str) -> bool:
    """Check if a feature is enabled for the current tenant."""
    config = get_current_tenant_config()
    return config.get("features", {}).get(feature_name, False)


# ── Tenant DB lookup ──────────────────────────────────────────────────────────

def _lookup_tenant_by_slug(slug: str) -> Optional[Tuple[str, dict]]:
    """Look up tenant_id and config from PostgreSQL by slug. Returns (tenant_id, config) or None."""
    try:
        from backend.app.core.config import get_settings
        s = get_settings()
        if not s.database_url.startswith("postgresql"):
            return DEFAULT_TENANT_ID, DEFAULT_CONFIG

        from backend.app.database.postgres import get_connection
        from sqlalchemy import text
        with get_connection() as conn:
            row = conn.execute(
                text("SELECT id, config, is_active FROM tenants WHERE slug = :slug"),
                {"slug": slug},
            ).fetchone()
        if not row:
            return None
        tenant_id, config_raw, is_active = str(row[0]), row[1] or {}, row[2]
        if not is_active:
            return None
        # Merge with defaults (new config fields get defaults automatically)
        config = {**DEFAULT_CONFIG, **config_raw}
        if "features" in config_raw:
            config["features"] = {**DEFAULT_CONFIG["features"], **config_raw["features"]}
        return tenant_id, config
    except Exception as e:
        logger.warning("tenant_lookup_failed", slug=slug, error=str(e))
        return None


def _lookup_tenant_by_id(tenant_id: str) -> Optional[dict]:
    """Look up tenant config from PostgreSQL by id. Returns config dict or None."""
    try:
        from backend.app.core.config import get_settings
        s = get_settings()
        if not s.database_url.startswith("postgresql"):
            return DEFAULT_CONFIG

        from backend.app.database.postgres import get_connection
        from sqlalchemy import text
        with get_connection() as conn:
            row = conn.execute(
                text("SELECT config, is_active FROM tenants WHERE id = :tid"),
                {"tid": tenant_id},
            ).fetchone()
        if not row or not row[1]:
            return None
        config_raw = row[0] or {}
        config = {**DEFAULT_CONFIG, **config_raw}
        if "features" in config_raw:
            config["features"] = {**DEFAULT_CONFIG["features"], **config_raw["features"]}
        return config
    except Exception as e:
        logger.warning("tenant_config_lookup_failed", tenant_id=tenant_id, error=str(e))
        return None


# ── Redis-backed tenant config cache ─────────────────────────────────────────
_CACHE_TTL = 300  # 5 minutes

def _get_redis():
    try:
        import redis as _redis
        from backend.app.core.config import get_settings
        return _redis.from_url(get_settings().redis_url, decode_responses=True)
    except Exception:
        return None


def get_tenant_config_cached(tenant_id: str) -> dict:
    """Get tenant config from Redis cache, falling back to DB lookup."""
    cache_key = f"tenant_config:{tenant_id}"
    r = _get_redis()
    if r:
        try:
            cached = r.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    config = _lookup_tenant_by_id(tenant_id) or DEFAULT_CONFIG

    if r:
        try:
            r.setex(cache_key, _CACHE_TTL, json.dumps(config))
        except Exception:
            pass

    return config


def invalidate_tenant_cache(tenant_id: str) -> None:
    """Invalidate cached config for a tenant (call after config update)."""
    r = _get_redis()
    if r:
        try:
            r.delete(f"tenant_config:{tenant_id}")
            logger.info("tenant_cache_invalidated", tenant_id=tenant_id)
        except Exception:
            pass


# ── Tenant resolution from request ───────────────────────────────────────────

def resolve_tenant_from_request(jwt_payload: Optional[dict], slug_header: Optional[str]) -> Tuple[str, dict]:
    """
    Resolve tenant from request context. Returns (tenant_id, config).

    Priority:
      1. JWT claim tenant_id (signed — cannot be forged)
      2. X-Tenant-Slug header → DB lookup
      3. Default tenant
    """
    # Priority 1: JWT claim
    if jwt_payload and jwt_payload.get("tenant_id"):
        tenant_id = jwt_payload["tenant_id"]
        config = get_tenant_config_cached(tenant_id)
        return tenant_id, config

    # Priority 2: Slug header
    if slug_header:
        result = _lookup_tenant_by_slug(slug_header.strip().lower())
        if result:
            tenant_id, config = result
            return tenant_id, config
        logger.warning("unknown_tenant_slug", slug=slug_header)

    # Priority 3: Default (single-tenant fallback)
    return DEFAULT_TENANT_ID, DEFAULT_CONFIG


# ── Tenant usage quotas ────────────────────────────────────────────────────

class TenantQuotaEnforcer:
    """Enforce per-tenant usage quotas (queries, uploads, storage).

    Quota config comes from tenant config's `rate_limits` key:
      - queries_per_hour: max queries across all users in the tenant
      - uploads_per_day: max document uploads per day
      - max_documents: max total documents stored
      - max_storage_mb: max total storage in MB
    """

    # In-memory counters (replace with Redis for multi-instance)
    _query_counts: dict[str, list[float]] = {}
    _upload_counts: dict[str, list[float]] = {}

    @classmethod
    def check_query_quota(cls, tenant_id: Optional[str] = None) -> None:
        """Raise HTTPException(429) if tenant exceeded hourly query quota."""
        tid = tenant_id or get_current_tenant()
        config = get_current_tenant_config()
        limit = config.get("rate_limits", {}).get("queries_per_hour", 500)

        now = time.time()
        window = 3600  # 1 hour
        if tid not in cls._query_counts:
            cls._query_counts[tid] = []
        cls._query_counts[tid] = [t for t in cls._query_counts[tid] if now - t < window]

        if len(cls._query_counts[tid]) >= limit:
            logger.warning("tenant_query_quota_exceeded", tenant_id=tid, limit=limit)
            from fastapi import HTTPException
            raise HTTPException(
                429,
                f"Organization query limit reached ({limit}/hour). Please try again later."
            )
        cls._query_counts[tid].append(now)

    @classmethod
    def check_upload_quota(cls, tenant_id: Optional[str] = None) -> None:
        """Raise HTTPException(429) if tenant exceeded daily upload quota."""
        tid = tenant_id or get_current_tenant()
        config = get_current_tenant_config()
        limit = config.get("rate_limits", {}).get("uploads_per_day", 50)

        now = time.time()
        window = 86400  # 24 hours
        if tid not in cls._upload_counts:
            cls._upload_counts[tid] = []
        cls._upload_counts[tid] = [t for t in cls._upload_counts[tid] if now - t < window]

        if len(cls._upload_counts[tid]) >= limit:
            logger.warning("tenant_upload_quota_exceeded", tenant_id=tid, limit=limit)
            from fastapi import HTTPException
            raise HTTPException(
                429,
                f"Organization upload limit reached ({limit}/day). Please try again tomorrow."
            )
        cls._upload_counts[tid].append(now)

    @classmethod
    def check_document_count_quota(cls, tenant_id: Optional[str] = None) -> None:
        """Raise HTTPException(429) if tenant has too many documents."""
        tid = tenant_id or get_current_tenant()
        config = get_current_tenant_config()
        limit = config.get("rate_limits", {}).get("max_documents", 1000)

        try:
            import sqlite3
            from backend.app.core.config import get_settings
            s = get_settings()
            with sqlite3.connect(s.db_path) as con:
                count = con.execute(
                    "SELECT COUNT(*) FROM documents WHERE tenant_id=?", (tid,)
                ).fetchone()[0]
            if count >= limit:
                logger.warning("tenant_document_quota_exceeded", tenant_id=tid,
                               count=count, limit=limit)
                from fastapi import HTTPException
                raise HTTPException(
                    429,
                    f"Organization document limit reached ({limit}). Delete old documents to upload new ones."
                )
        except ImportError:
            pass
        except Exception as e:
            if "HTTPException" not in str(type(e)):
                logger.warning("quota_check_failed", error=str(e))
            else:
                raise

    @classmethod
    def get_usage_stats(cls, tenant_id: Optional[str] = None) -> dict:
        """Get current usage stats for a tenant."""
        tid = tenant_id or get_current_tenant()
        config = get_current_tenant_config()
        now = time.time()

        query_count = len([t for t in cls._query_counts.get(tid, []) if now - t < 3600])
        upload_count = len([t for t in cls._upload_counts.get(tid, []) if now - t < 86400])

        limits = config.get("rate_limits", {})
        return {
            "tenant_id": tid,
            "queries_this_hour": query_count,
            "query_limit_per_hour": limits.get("queries_per_hour", 500),
            "uploads_today": upload_count,
            "upload_limit_per_day": limits.get("uploads_per_day", 50),
        }


# ── Tenant data isolation assertion ──────────────────────────────────────────

def assert_tenant_access(resource_tenant_id: str, requesting_tenant_id: Optional[str] = None) -> None:
    """Verify the requesting tenant matches the resource's tenant.

    Raises HTTPException(403) on cross-tenant access attempt.
    Logs a security event for audit trail.
    """
    tid = requesting_tenant_id or get_current_tenant()
    if resource_tenant_id != tid and resource_tenant_id != DEFAULT_TENANT_ID:
        from backend.app.core.security import log_security_event
        log_security_event(
            "cross_tenant_access_blocked",
            {"requesting_tenant": tid, "resource_tenant": resource_tenant_id},
        )
        logger.error(
            "cross_tenant_access_attempt",
            requesting_tenant=tid,
            resource_tenant=resource_tenant_id,
        )
        from fastapi import HTTPException
        raise HTTPException(403, "Access denied")
