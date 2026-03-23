"""Phase 2: RBAC expansion + super_admin role.

No new tables needed (all tables created in 001).
This migration documents the role expansion and adds
a check constraint to validate roles at DB level.

Revision ID: 002_phase2_rbac
Revises: 001_initial
Create Date: 2026-03-20
"""

from __future__ import annotations
from typing import Sequence, Union

from alembic import op

revision: str = "002_phase2_rbac"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add DB-level role constraint (catches invalid roles at insert time)
    op.execute("""
        ALTER TABLE users
        ADD CONSTRAINT chk_users_role
        CHECK (role IN ('employee', 'manager', 'hr_admin', 'super_admin'))
    """)

    # Add ingestion_status constraint on documents
    op.execute("""
        ALTER TABLE documents
        ADD CONSTRAINT chk_documents_ingestion_status
        CHECK (ingestion_status IN ('pending', 'processing', 'done', 'failed'))
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_users_role")
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS chk_documents_ingestion_status")
