"""HRMS background tasks — Phase 4 (F-43/F-47).

Tasks:
  sync_tenant_hrms_data   — Pull HRMS data for one tenant, cache in Redis
  sync_all_tenants_hrms   — Celery Beat entry: fan out to per-tenant sync tasks
  warm_tenant_cache       — Pre-populate semantic cache for a tenant's top queries
  warm_all_tenants_cache  — Celery Beat entry: fan out to per-tenant warming tasks
  cleanup_stale_sessions  — Delete expired JWT sessions from DB

All tasks are idempotent: running twice produces the same result.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import structlog

from backend.app.workers.celery_app import app

logger = structlog.get_logger()

# How long to cache synced HRMS data (seconds) — same as sync interval
HRMS_CACHE_TTL = int(os.getenv("HRMS_CACHE_TTL_SECONDS", str(4 * 3600)))

# Redis key prefix for cached HRMS data
HRMS_CACHE_PREFIX = "hrms:snapshot"


@app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=120,
    queue="hrms_sync",
    acks_late=True,
    name="backend.app.workers.hrms_tasks.sync_tenant_hrms_data",
)
def sync_tenant_hrms_data(self, tenant_id: str, tenant_config: dict) -> dict:
    """Pull HRMS data for one tenant and cache it in Redis.

    Stores employee count and org snapshot for fast lookup.
    The chat pipeline reads from this cache instead of calling HRMS
    on every query (reduces HRMS API load, survives HRMS downtime).

    Cache key: hrms:snapshot:{tenant_id}
    """
    from backend.app.integrations.hrms_router import get_adapter
    import redis as redis_lib

    logger.info("hrms_sync_start", tenant_id=tenant_id)
    start = time.time()

    try:
        adapter = get_adapter(tenant_id, tenant_config)
        if not adapter:
            logger.info("hrms_sync_skipped_no_adapter", tenant_id=tenant_id)
            return {"status": "skipped", "reason": "no_adapter_configured"}

        health = adapter.health()
        if health.get("status") == "down":
            raise RuntimeError(f"HRMS adapter unhealthy: {health.get('error')}")

        # Build snapshot: just health + metadata for now
        # Full employee sync would be too large for Redis — use DB in Phase 5
        snapshot = {
            "tenant_id": tenant_id,
            "synced_at": time.time(),
            "adapter_health": health,
            "provider": tenant_config.get("hrms", {}).get("provider", "unknown"),
        }

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis_lib.from_url(redis_url, decode_responses=True)
        cache_key = f"{HRMS_CACHE_PREFIX}:{tenant_id}"
        r.set(cache_key, json.dumps(snapshot), ex=HRMS_CACHE_TTL)

        elapsed = round(time.time() - start, 2)
        logger.info("hrms_sync_done", tenant_id=tenant_id, elapsed=elapsed)
        return {"status": "ok", "elapsed": elapsed, "snapshot_key": cache_key}

    except Exception as exc:
        logger.error("hrms_sync_failed", tenant_id=tenant_id, error=str(exc))
        countdown = 120 * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)


@app.task(
    queue="hrms_sync",
    name="backend.app.workers.hrms_tasks.sync_all_tenants_hrms",
)
def sync_all_tenants_hrms() -> dict:
    """Fan out HRMS sync to all active tenants with HRMS configured.

    Celery Beat calls this every 4 hours. It reads the tenant list
    from PostgreSQL and dispatches per-tenant sync tasks.
    """
    tenants = _get_active_tenants_with_hrms()
    dispatched = 0
    for tenant in tenants:
        sync_tenant_hrms_data.apply_async(
            args=[tenant["id"], tenant["config"]],
            queue="hrms_sync",
        )
        dispatched += 1

    logger.info("hrms_sync_dispatched", count=dispatched)
    return {"dispatched": dispatched}


@app.task(
    queue="cache_warm",
    name="backend.app.workers.hrms_tasks.warm_tenant_cache",
)
def warm_tenant_cache(tenant_id: str) -> dict:
    """Pre-populate semantic cache with top-50 HR queries for a tenant.

    Reads the 50 most-asked queries from the messages table (last 30 days),
    runs them through the RAG pipeline at low priority, and stores results
    in the Redis semantic cache. Morning employees hit cache, not LLM.
    """
    from backend.app.core.semantic_cache import warm_cache
    from backend.app.database.postgres import get_top_queries_for_tenant

    logger.info("cache_warm_start", tenant_id=tenant_id)

    top_queries = get_top_queries_for_tenant(tenant_id, limit=50)
    if not top_queries:
        return {"status": "skipped", "reason": "no_query_history"}

    # For each top query, we'd normally run RAG here.
    # In Phase 4 we warm with the last known answers from DB.
    warm_entries = []
    for q in top_queries:
        if q.get("answer") and q.get("query"):
            warm_entries.append({
                "query": q["query"],
                "embedding": q.get("embedding"),
                "answer": q["answer"],
                "citations": q.get("citations", []),
                "confidence": q.get("confidence", 1.0),
                "suggested_questions": q.get("suggested_questions", []),
            })

    count = warm_cache(warm_entries, tenant_id=tenant_id)
    logger.info("cache_warm_done", tenant_id=tenant_id, entries=count)
    return {"status": "ok", "entries_warmed": count}


@app.task(
    queue="cache_warm",
    name="backend.app.workers.hrms_tasks.warm_all_tenants_cache",
)
def warm_all_tenants_cache() -> dict:
    """Fan out cache warming to all active tenants.

    Celery Beat calls this daily at 6am UTC.
    """
    tenants = _get_active_tenants()
    dispatched = 0
    for tenant in tenants:
        warm_tenant_cache.apply_async(
            args=[tenant["id"]],
            queue="cache_warm",
        )
        dispatched += 1

    logger.info("cache_warm_dispatched", count=dispatched)
    return {"dispatched": dispatched}


@app.task(
    queue="default",
    name="backend.app.workers.hrms_tasks.cleanup_stale_sessions",
)
def cleanup_stale_sessions() -> dict:
    """Delete expired refresh tokens and inactive sessions from the database.

    Celery Beat calls this daily at 2am UTC.
    """
    from backend.app.database.postgres import cleanup_expired_sessions

    count = cleanup_expired_sessions()
    logger.info("session_cleanup_done", deleted=count)
    return {"deleted": count}


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_active_tenants() -> list[dict]:
    """Return list of active tenant dicts from PostgreSQL."""
    try:
        from backend.app.database.postgres import get_engine
        from sqlalchemy import text
        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT id::text, config FROM tenants WHERE is_active = true")
            ).fetchall()
            return [{"id": str(r[0]), "config": r[1] or {}} for r in rows]
    except Exception as e:
        logger.error("get_active_tenants_failed", error=str(e))
        return []


def _get_active_tenants_with_hrms() -> list[dict]:
    """Return active tenants that have HRMS configured."""
    all_tenants = _get_active_tenants()
    return [
        t for t in all_tenants
        if t.get("config", {}).get("hrms", {}).get("provider")
    ]
