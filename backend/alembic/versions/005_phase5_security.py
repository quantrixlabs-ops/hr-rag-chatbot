"""Phase 5: Security hardening — MFA recovery codes, GDPR consent, audit signing.

Adds:
  - mfa_recovery_codes table: single-use backup codes for MFA account recovery
  - gdpr_consent_log: tracks user consent events (for GDPR Article 7 compliance)
  - users.email_hash: SHA-256 lookup index for encrypted email field
  - audit_logs.signature: HMAC integrity column (populated on export, stored for verification)

Revision ID: 005_phase5_security
Revises: 004_phase4_hrms_webhooks
Create Date: 2026-03-20
"""

from __future__ import annotations
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from alembic import op

revision: str = "005_phase5_security"
down_revision: Union[str, None] = "004_phase4_hrms_webhooks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── MFA recovery codes ───────────────────────────────────────────────────
    op.create_table(
        "mfa_recovery_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("code_hash", sa.String(255), nullable=False),  # bcrypt hash
        sa.Column("used", sa.Boolean, server_default="false"),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index("idx_mfa_recovery_user", "mfa_recovery_codes",
                    ["user_id", "used"])

    # ── GDPR consent log ─────────────────────────────────────────────────────
    op.create_table(
        "gdpr_consent_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("consent_type", sa.String(100), nullable=False),  # data_processing | marketing
        sa.Column("granted", sa.Boolean, nullable=False),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_gdpr_consent_user", "gdpr_consent_log", ["user_id", "consent_type"])

    # ── Add email_hash to users for encrypted email lookup ───────────────────
    # email stored as ENC:... (Fernet encrypted), email_hash used for WHERE queries
    try:
        op.add_column(
            "users",
            sa.Column("email_hash", sa.String(64)),
        )
        op.create_index("idx_users_email_hash", "users", ["email_hash"])
    except Exception:
        pass  # Column may already exist

    # ── Add integrity signature column to audit_logs ─────────────────────────
    try:
        op.add_column(
            "audit_logs",
            sa.Column("signature", sa.String(64)),  # HMAC-SHA256 hex (64 chars)
        )
    except Exception:
        pass


def downgrade() -> None:
    op.drop_table("mfa_recovery_codes")
    op.drop_table("gdpr_consent_log")
    try:
        op.drop_index("idx_users_email_hash", "users")
        op.drop_column("users", "email_hash")
    except Exception:
        pass
    try:
        op.drop_column("audit_logs", "signature")
    except Exception:
        pass
