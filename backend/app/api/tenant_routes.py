"""Tenant provisioning and management API — Phase 3.

Endpoints:
  POST   /tenants                    → Provision new tenant (super_admin)
  GET    /tenants                    → List all tenants (super_admin)
  GET    /tenants/{slug}             → Get tenant details
  PATCH  /tenants/{slug}/config      → Update tenant config
  POST   /tenants/{slug}/deactivate  → Deactivate tenant
  POST   /tenants/register           → Self-service onboarding (public)
  GET    /tenants/me/config          → Current tenant config (any admin)
  GET    /tenants/me/branding        → Public branding info (no auth)
"""

from __future__ import annotations

import re
import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.app.core.config import get_settings
from backend.app.core.security import get_current_user, require_role
from backend.app.core.permissions import require_permission
from backend.app.core.tenant import (
    DEFAULT_CONFIG,
    invalidate_tenant_cache,
    get_current_tenant,
)
from backend.app.models.chat_models import User

logger = structlog.get_logger()
router = APIRouter(prefix="/tenants", tags=["tenants"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class TenantCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=50, pattern=r'^[a-z0-9-]+$')
    plan: str = Field(default="trial")  # trial | basic | pro | enterprise
    config: dict = Field(default_factory=dict)


class TenantConfigUpdateRequest(BaseModel):
    config: dict


class TenantRegisterRequest(BaseModel):
    """Self-service tenant registration (public endpoint)."""
    organization_name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=50, pattern=r'^[a-z0-9-]+$')
    admin_email: str
    admin_name: str
    admin_password: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_postgres():
    s = get_settings()
    if not s.database_url.startswith("postgresql"):
        raise HTTPException(503, "Tenant management requires PostgreSQL. Configure DATABASE_URL.")


def _get_tenant_by_slug(slug: str) -> Optional[dict]:
    from backend.app.database.postgres import get_connection
    from sqlalchemy import text
    with get_connection() as conn:
        row = conn.execute(
            text("SELECT id, name, slug, is_active, config, created_at FROM tenants WHERE slug = :slug"),
            {"slug": slug},
        ).fetchone()
    if not row:
        return None
    return {
        "id": str(row[0]),
        "name": row[1],
        "slug": row[2],
        "is_active": row[3],
        "config": row[4] or {},
        "created_at": str(row[5]),
    }


# ── Provision new tenant (super_admin only) ───────────────────────────────────

@router.post("", status_code=201)
async def provision_tenant(
    req: TenantCreateRequest,
    admin: User = Depends(get_current_user),
):
    """Provision a new tenant organization. super_admin only."""
    require_role(admin, "super_admin")
    if not require_permission(admin.role, "tenant.provision"):
        raise HTTPException(403, "Only super_admin can provision tenants")

    _require_postgres()

    slug = req.slug.lower().strip()
    if slug in ("default", "api", "admin", "health", "metrics", "static"):
        raise HTTPException(400, f"Slug '{slug}' is reserved")

    from backend.app.database.postgres import get_connection, tenants, DEFAULT_TENANT_CONFIG
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    tenant_id = uuid.uuid4()
    merged_config = {**DEFAULT_TENANT_CONFIG, **req.config}
    if "features" in req.config:
        merged_config["features"] = {**DEFAULT_TENANT_CONFIG.get("features", {}), **req.config["features"]}

    try:
        with get_connection() as conn:
            # Check duplicate slug
            exists = conn.execute(
                text("SELECT 1 FROM tenants WHERE slug = :slug"),
                {"slug": slug},
            ).fetchone()
            if exists:
                raise HTTPException(409, f"Tenant slug '{slug}' already exists")

            conn.execute(
                tenants.insert().values(
                    id=tenant_id,
                    name=req.name.strip(),
                    slug=slug,
                    is_active=True,
                    config=merged_config,
                )
            )
    except HTTPException:
        raise
    except IntegrityError:
        raise HTTPException(409, f"Tenant slug '{slug}' already exists")
    except Exception as e:
        logger.error("tenant_provision_failed", slug=slug, error=str(e))
        raise HTTPException(500, "Failed to provision tenant")

    from backend.app.database.postgres import write_audit_log
    write_audit_log(
        action="tenant.provisioned",
        target_type="tenant",
        target_id=str(tenant_id),
        extra={"slug": slug, "name": req.name, "provisioned_by": admin.user_id},
    )

    logger.info("tenant_provisioned", tenant_id=str(tenant_id), slug=slug, by=admin.user_id)
    return {
        "tenant_id": str(tenant_id),
        "name": req.name,
        "slug": slug,
        "is_active": True,
        "config": merged_config,
    }


# ── List tenants (super_admin) ────────────────────────────────────────────────

@router.get("")
async def list_tenants(admin: User = Depends(get_current_user)):
    """List all tenants. super_admin only."""
    require_role(admin, "super_admin")
    _require_postgres()

    from backend.app.database.postgres import get_connection
    from sqlalchemy import text
    with get_connection() as conn:
        rows = conn.execute(
            text("SELECT id, name, slug, is_active, created_at FROM tenants ORDER BY created_at DESC")
        ).fetchall()

    return {
        "tenants": [
            {
                "id": str(r[0]),
                "name": r[1],
                "slug": r[2],
                "is_active": r[3],
                "created_at": str(r[4]),
            }
            for r in rows
        ],
        "total": len(rows),
    }


# ── Get single tenant ─────────────────────────────────────────────────────────

@router.get("/{slug}")
async def get_tenant(slug: str, admin: User = Depends(get_current_user)):
    """Get tenant details. super_admin sees all; hr_admin sees own tenant only."""
    _require_postgres()

    # hr_admin can only view their own tenant
    if admin.role != "super_admin":
        current = get_current_tenant()
        tenant = _get_tenant_by_slug(slug)
        if not tenant or tenant["id"] != current:
            raise HTTPException(403, "You can only view your own tenant")

    tenant = _get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(404, f"Tenant '{slug}' not found")

    # Strip sensitive SSO credentials from non-super-admin response
    if admin.role != "super_admin" and "sso" in tenant.get("config", {}):
        sso = tenant["config"]["sso"].copy()
        sso.pop("client_secret", None)
        tenant["config"]["sso"] = sso

    return tenant


# ── Update tenant config ──────────────────────────────────────────────────────

@router.patch("/{slug}/config")
async def update_tenant_config(
    slug: str,
    req: TenantConfigUpdateRequest,
    admin: User = Depends(get_current_user),
):
    """Update tenant configuration. super_admin or own tenant's hr_admin."""
    _require_postgres()

    tenant = _get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(404, f"Tenant '{slug}' not found")

    # hr_admin can only update their own tenant config (not super_admin privileges)
    if admin.role != "super_admin":
        require_role(admin, "hr_admin")
        if tenant["id"] != get_current_tenant():
            raise HTTPException(403, "You can only configure your own tenant")
        # hr_admin cannot change billing/plan fields
        req.config.pop("plan", None)
        req.config.pop("max_users", None)

    # Merge new config over existing
    current_config = tenant["config"]
    merged = {**current_config, **req.config}
    if "features" in req.config:
        merged["features"] = {**current_config.get("features", {}), **req.config["features"]}

    from backend.app.database.postgres import get_connection
    from sqlalchemy import text
    with get_connection() as conn:
        conn.execute(
            text("UPDATE tenants SET config = :cfg WHERE slug = :slug"),
            {"cfg": merged, "slug": slug},
        )

    # Invalidate Redis cache for this tenant
    invalidate_tenant_cache(tenant["id"])

    from backend.app.database.postgres import write_audit_log
    write_audit_log(
        action="tenant.config_updated",
        target_type="tenant",
        target_id=tenant["id"],
        extra={"slug": slug, "updated_by": admin.user_id, "fields": list(req.config.keys())},
    )

    logger.info("tenant_config_updated", slug=slug, by=admin.user_id)
    return {"slug": slug, "config": merged, "message": "Config updated"}


# ── Deactivate tenant ─────────────────────────────────────────────────────────

@router.post("/{slug}/deactivate")
async def deactivate_tenant(slug: str, admin: User = Depends(get_current_user)):
    """Deactivate a tenant (soft-delete). super_admin only."""
    require_role(admin, "super_admin")
    _require_postgres()

    if slug == "default":
        raise HTTPException(400, "Cannot deactivate the default tenant")

    tenant = _get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(404, f"Tenant '{slug}' not found")

    from backend.app.database.postgres import get_connection
    from sqlalchemy import text
    with get_connection() as conn:
        conn.execute(
            text("UPDATE tenants SET is_active = FALSE WHERE slug = :slug"),
            {"slug": slug},
        )

    invalidate_tenant_cache(tenant["id"])

    from backend.app.database.postgres import write_audit_log
    write_audit_log(
        action="tenant.deactivated",
        target_type="tenant",
        target_id=tenant["id"],
        extra={"slug": slug, "deactivated_by": admin.user_id},
    )

    logger.info("tenant_deactivated", slug=slug, by=admin.user_id)
    return {"slug": slug, "is_active": False, "message": "Tenant deactivated"}


# ── Self-service tenant registration (PUBLIC) ─────────────────────────────────

@router.post("/register", status_code=201)
async def register_tenant(req: TenantRegisterRequest):
    """Self-service tenant onboarding. Creates tenant + first admin user.

    This is a public endpoint — no auth required.
    New tenant starts in 'trial' plan with limited features.
    """
    _require_postgres()

    slug = req.slug.lower().strip()

    from backend.app.database.postgres import get_connection, tenants, users, DEFAULT_TENANT_CONFIG
    from sqlalchemy import text
    from passlib.context import CryptContext

    _pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

    # Validate password
    if len(req.admin_password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")

    # Validate email format (basic)
    if "@" not in req.admin_email or "." not in req.admin_email:
        raise HTTPException(400, "Invalid email address")

    tenant_id = uuid.uuid4()
    admin_user_id = uuid.uuid4()
    trial_config = {
        **DEFAULT_TENANT_CONFIG,
        "plan": "trial",
        "features": {
            **DEFAULT_TENANT_CONFIG.get("features", {}),
            "sso": False,
        },
        "branding": {
            "company_name": req.organization_name,
            "primary_color": "#2563EB",
        },
    }

    try:
        with get_connection() as conn:
            # Check duplicate slug
            if conn.execute(text("SELECT 1 FROM tenants WHERE slug = :s"), {"s": slug}).fetchone():
                raise HTTPException(409, f"Organization slug '{slug}' is already taken. Choose another.")

            # Check duplicate email
            if conn.execute(text("SELECT 1 FROM users WHERE email = :e"), {"e": req.admin_email}).fetchone():
                raise HTTPException(409, "An account with this email already exists.")

            # Create tenant
            conn.execute(
                tenants.insert().values(
                    id=tenant_id,
                    name=req.organization_name.strip(),
                    slug=slug,
                    is_active=True,
                    config=trial_config,
                )
            )

            # Create first admin user (immediately active)
            conn.execute(
                users.insert().values(
                    id=admin_user_id,
                    tenant_id=tenant_id,
                    username=req.admin_email.split("@")[0],
                    email=req.admin_email,
                    hashed_password=_pwd_ctx.hash(req.admin_password),
                    role="hr_admin",
                    full_name=req.admin_name,
                    is_active=True,
                    status="active",
                    email_verified=False,
                )
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("tenant_register_failed", slug=slug, error=str(e))
        raise HTTPException(500, "Registration failed. Please try again.")

    logger.info("tenant_registered", tenant_id=str(tenant_id), slug=slug, admin=req.admin_email)
    return {
        "tenant_id": str(tenant_id),
        "slug": slug,
        "organization_name": req.organization_name,
        "admin_user_id": str(admin_user_id),
        "plan": "trial",
        "message": (
            f"Organization '{req.organization_name}' registered. "
            f"Log in at /api/v1/auth/login with your email."
        ),
    }


# ── Current tenant config (authenticated) ────────────────────────────────────

@router.get("/me/config")
async def get_my_tenant_config(admin: User = Depends(get_current_user)):
    """Get configuration for the current user's tenant. hr_admin only."""
    require_role(admin, "hr_admin")
    from backend.app.core.tenant import get_current_tenant_config
    config = get_current_tenant_config()

    # Strip SSO secret from response
    safe_config = {k: v for k, v in config.items() if k != "sso"}
    if "sso" in config:
        sso_safe = {k: v for k, v in config["sso"].items() if k != "client_secret"}
        safe_config["sso"] = sso_safe

    return {"tenant_id": get_current_tenant(), "config": safe_config}


# ── Public branding endpoint (no auth required) ───────────────────────────────

@router.get("/me/branding")
async def get_branding(slug: Optional[str] = None):
    """Get branding for a tenant by slug. Used by frontend before login."""
    if not slug:
        return {
            "company_name": "HR Chatbot",
            "primary_color": "#2563EB",
            "logo_url": None,
        }

    _require_postgres()
    tenant = _get_tenant_by_slug(slug)
    if not tenant or not tenant["is_active"]:
        raise HTTPException(404, "Organization not found")

    branding = tenant["config"].get("branding", {})
    return {
        "company_name": branding.get("company_name", tenant["name"]),
        "primary_color": branding.get("primary_color", "#2563EB"),
        "logo_url": branding.get("logo_url"),
        "slug": slug,
    }
