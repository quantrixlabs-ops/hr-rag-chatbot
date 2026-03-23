"""Phase 4: HRMS integration support + webhook delivery tracking.

Adds:
  - hrms_sync_log:  records each HRMS sync run per tenant (audit + debug)
  - webhook_events: tracks outbound webhook delivery attempts

Revision ID: 004_phase4_hrms_webhooks
Revises: 003_phase3_tenant_config
Create Date: 2026-03-20
"""

from __future__ import annotations
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from alembic import op

revision: str = "004_phase4_hrms_webhooks"
down_revision: Union[str, None] = "003_phase3_tenant_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── HRMS sync log — audit trail for each sync run ────────────────────────
    op.create_table(
        "hrms_sync_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("provider", sa.String(50)),        # bamboohr | sap | ...
        sa.Column("status", sa.String(20)),          # ok | failed | skipped
        sa.Column("records_synced", sa.Integer, server_default="0"),
        sa.Column("error_message", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", JSONB, server_default="{}"),
    )
    op.create_index("idx_hrms_sync_tenant_started", "hrms_sync_log",
                    ["tenant_id", "started_at"])

    # ── Webhook events — delivery tracking ───────────────────────────────────
    op.create_table(
        "webhook_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("event", sa.String(100), nullable=False),  # document.ingested etc
        sa.Column("webhook_url", sa.String(2000), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending"),
        # pending | delivered | failed | permanent_failure
        sa.Column("http_status", sa.Integer),
        sa.Column("attempts", sa.Integer, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("celery_task_id", sa.String(255)),
        sa.Column("payload", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index("idx_webhook_events_tenant_event", "webhook_events",
                    ["tenant_id", "event"])
    op.create_index("idx_webhook_events_status", "webhook_events", ["status"])

    # ── Add hrms config index to tenants for fast adapter lookup ─────────────
    # The HRMS provider is in tenants.config->>'hrms'->'provider' (JSONB)
    # GIN index speeds up queries that check feature flags / HRMS config
    try:
        op.execute("CREATE INDEX idx_tenants_config_gin ON tenants USING gin(config)")
    except Exception:
        pass  # May already exist


def downgrade() -> None:
    op.drop_table("webhook_events")
    op.drop_table("hrms_sync_log")
    try:
        op.drop_index("idx_tenants_config_gin", "tenants")
    except Exception:
        pass
