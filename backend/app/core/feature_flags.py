"""Feature flag enforcement — Phase 3.

Feature flags are stored per-tenant in tenants.config.features.
Checked at route level before business logic executes.

Usage:
    from backend.app.core.feature_flags import require_feature, feature_enabled

    # In a route:
    @router.post("/chat/query")
    async def chat(req, user=Depends(get_current_user)):
        require_feature("memory_summarization")  # raises 403 if disabled for tenant
        ...

    # Conditional:
    if feature_enabled("async_ingestion"):
        enqueue_task(...)
    else:
        sync_ingest(...)

Phase 3 hook: Feature flags enable tiered SaaS pricing (Basic / Pro / Enterprise).
"""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from backend.app.core.tenant import get_current_tenant_config, get_current_tenant


def feature_enabled(feature_name: str) -> bool:
    """True if the feature is enabled for the current tenant."""
    config = get_current_tenant_config()
    return bool(config.get("features", {}).get(feature_name, False))


def require_feature(feature_name: str, error_msg: Optional[str] = None) -> None:
    """Raise HTTP 403 if feature is disabled for the current tenant.

    Use at the top of route handlers that depend on optional features.
    """
    if not feature_enabled(feature_name):
        tenant = get_current_tenant()
        raise HTTPException(
            status_code=403,
            detail=error_msg or f"Feature '{feature_name}' is not enabled for your organization. Contact your administrator.",
        )


def get_tenant_rate_limits() -> dict:
    """Get rate limit config for the current tenant."""
    config = get_current_tenant_config()
    defaults = {"queries_per_hour": 500, "uploads_per_day": 50}
    return {**defaults, **config.get("rate_limits", {})}


def get_tenant_llm_model() -> str:
    """Get the LLM model configured for the current tenant."""
    config = get_current_tenant_config()
    return config.get("llm_model", "llama3:8b")


def get_tenant_branding() -> dict:
    """Get branding config for the current tenant."""
    config = get_current_tenant_config()
    return config.get("branding", {"company_name": "Your Company", "primary_color": "#2563EB"})
