"""Phase 3: Tenant config enhancements for SaaS readiness.

Adds a plan field to tenants table and a unique index on slug.
All multi-tenancy logic is application-level (not DB-level RLS yet).

Revision ID: 003_phase3_tenant_config
Revises: 002_phase2_rbac
Create Date: 2026-03-20
"""

from __future__ import annotations
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_phase3_tenant_config"
down_revision: Union[str, None] = "002_phase2_rbac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add plan field to tenants (trial | basic | pro | enterprise)
    op.add_column(
        "tenants",
        sa.Column("plan", sa.String(50), server_default="trial"),
    )

    # Add updated_at to tenants for cache invalidation triggers
    op.add_column(
        "tenants",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Add unique index on slug (should already be unique constraint but explicit index helps query perf)
    op.create_index("idx_tenants_slug", "tenants", ["slug"], unique=True)

    # Add tenant_id to audit_logs index for per-tenant compliance export (Phase 5)
    # (Table already exists from 001, just adding composite index)
    try:
        op.create_index(
            "idx_audit_logs_tenant_created",
            "audit_logs",
            ["tenant_id", "created_at"],
        )
    except Exception:
        pass  # Index may already exist


def downgrade() -> None:
    op.drop_index("idx_tenants_slug", "tenants")
    op.drop_column("tenants", "plan")
    op.drop_column("tenants", "updated_at")
    try:
        op.drop_index("idx_audit_logs_tenant_created", "audit_logs")
    except Exception:
        pass
