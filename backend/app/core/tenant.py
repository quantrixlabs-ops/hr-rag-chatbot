"""Multi-tenancy enforcement — tenant context management (Phase 2).

Every authenticated request carries a tenant_id. All database queries
MUST filter by tenant_id to prevent cross-tenant data leakage.

For single-tenant demo mode, tenant_id is always 'default'.
For SaaS mode, tenant_id is extracted from the JWT or subdomain.
"""

from __future__ import annotations

import contextvars
from typing import Optional

# Context variable holding the current tenant_id for this request
_current_tenant: contextvars.ContextVar[str] = contextvars.ContextVar("current_tenant", default="default")


def get_current_tenant() -> str:
    """Get the tenant_id for the current request."""
    return _current_tenant.get()


def set_current_tenant(tenant_id: str) -> None:
    """Set the tenant_id for the current request (called by middleware)."""
    _current_tenant.set(tenant_id)


def tenant_filter(base_query: str, params: tuple, tenant_id: Optional[str] = None) -> tuple:
    """Add tenant_id filter to a SQL query.

    Usage:
        query, params = tenant_filter(
            "SELECT * FROM documents WHERE category=?",
            ("policy",)
        )
        # Returns: "SELECT * FROM documents WHERE category=? AND tenant_id=?", ("policy", "default")
    """
    tid = tenant_id or get_current_tenant()
    if "WHERE" in base_query.upper():
        return base_query + " AND tenant_id=?", params + (tid,)
    else:
        return base_query + " WHERE tenant_id=?", params + (tid,)
