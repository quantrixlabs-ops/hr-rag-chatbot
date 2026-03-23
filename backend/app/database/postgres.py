"""PostgreSQL database module — Phase 4 extended with read replica routing (F-45).

Phase 1: single engine (primary)
Phase 4 adds:
  - READ_REPLICA_URL env var → second engine for read-only queries
  - write_db() context manager → always hits primary
  - read_db()  context manager → hits replica if configured, primary otherwise
  - get_top_queries_for_tenant() → for cache warming job
  - cleanup_expired_sessions()  → for daily session cleanup job

Uses SQLAlchemy Core (not ORM) for explicit query control.
All queries are scoped to tenant_id — the Phase 3 multi-tenancy hook.

Connection strategy:
- Production (Docker): DATABASE_URL=postgresql://...  → psycopg2
- Read replica:        READ_REPLICA_URL=postgresql://... → replica (optional)
- Tests / CI:          DATABASE_URL=sqlite:///...      → falls back to session_store.py
"""

from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator, Optional, Union

import structlog
from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer,
    MetaData, String, Table, Text, create_engine, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.pool import NullPool

from backend.app.core.config import get_settings

logger = structlog.get_logger()

# ── SQLAlchemy metadata ───────────────────────────────────────────────────────
metadata = MetaData()

# ── Table definitions (mirrors HR_CHATBOT_PHASE1_ARCHITECTURE.md schema) ─────

tenants = Table(
    "tenants", metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("name", String(255), nullable=False),
    Column("slug", String(100), unique=True, nullable=False),
    Column("is_active", Boolean, default=True),
    Column("config", JSONB, default=dict),
    Column("created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
)

users = Table(
    "users", metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False),
    Column("username", String(100), unique=True, nullable=False),
    Column("email", String(255), unique=True),
    Column("hashed_password", String(255), nullable=False),
    Column("role", String(50), nullable=False, default="employee"),
    Column("department", String(100)),
    Column("full_name", String(255), default=""),
    Column("phone", String(50), default=""),
    Column("is_active", Boolean, default=True),
    Column("status", String(50), default="pending_approval"),
    Column("email_verified", Boolean, default=False),
    Column("totp_enabled", Boolean, default=False),
    Column("totp_secret", String(255)),
    Column("created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
    Column("last_login_at", DateTime(timezone=True)),
)

documents = Table(
    "documents", metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False),
    Column("filename", String(500), nullable=False),
    Column("title", String(500)),
    Column("file_type", String(20), nullable=False),
    Column("storage_path", String(1000), nullable=False),
    Column("category", String(100)),
    Column("access_roles", JSONB, default=lambda: ["employee"]),
    Column("ingestion_status", String(20), default="pending"),
    Column("ingestion_error", Text),
    Column("chunk_count", Integer, default=0),
    Column("content_hash", String(64)),
    Column("metadata", JSONB, default=dict),
    Column("uploaded_by", UUID(as_uuid=True), ForeignKey("users.id")),
    Column("created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
    Column("updated_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
)

document_versions = Table(
    "document_versions", metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("document_id", UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False),
    Column("version_number", Integer, nullable=False, default=1),
    Column("storage_path", String(1000)),
    Column("is_current", Boolean, default=False),
    Column("archived_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
)

chat_sessions = Table(
    "chat_sessions", metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id"), nullable=False),
    Column("title", String(500)),
    Column("is_active", Boolean, default=True),
    Column("message_count", Integer, default=0),
    Column("created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
    Column("updated_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
)

messages = Table(
    "messages", metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("session_id", UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=False),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False),
    Column("role", String(20), nullable=False),
    Column("content", Text, nullable=False),
    Column("sources", JSONB, default=list),
    Column("confidence", Float),
    Column("latency_ms", Integer),
    Column("metadata", JSONB, default=dict),
    Column("created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
)

audit_logs = Table(
    "audit_logs", metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenants.id")),
    Column("actor_id", UUID(as_uuid=True), ForeignKey("users.id")),
    Column("action", String(100), nullable=False),
    Column("target_type", String(50)),
    Column("target_id", String(255)),
    Column("ip_address", String(45)),
    Column("metadata", JSONB, default=dict),
    Column("created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
)

feedback = Table(
    "feedback", metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False),
    Column("session_id", UUID(as_uuid=True), ForeignKey("chat_sessions.id")),
    Column("message_id", UUID(as_uuid=True), ForeignKey("messages.id")),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id")),
    Column("rating", String(20), nullable=False),
    Column("comment", Text),
    Column("created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
)

security_events = Table(
    "security_events", metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenants.id")),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id")),
    Column("event_type", String(100), nullable=False),
    Column("ip_address", String(45)),
    Column("details", JSONB, default=dict),
    Column("created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
)

refresh_tokens = Table(
    "refresh_tokens", metadata,
    Column("token", String(512), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenants.id")),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id"), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked", Boolean, default=False),
    Column("created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
)

# ── Default tenant constants ──────────────────────────────────────────────────
DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEFAULT_TENANT_CONFIG = {
    "llm_model": "llama3:8b",
    "chunk_size": 400,
    "max_context_turns": 10,
    "features": {
        "memory_summarization": False,
        "sso": False,
        "document_versioning": False,
        "audit_logging": True,
    },
    "branding": {
        "company_name": "Your Company",
        "primary_color": "#2563EB",
    },
}

# ── Engine management — Phase 4: primary + optional read replica ──────────────
_engine = None           # Primary (writes + reads when no replica)
_read_engine = None      # Read replica (optional, Phase 4)


def _build_engine(db_url: str):
    """Create a SQLAlchemy engine with appropriate pool settings."""
    kwargs: dict = {"echo": False}
    if db_url.startswith("postgresql"):
        kwargs["pool_pre_ping"] = True
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
    else:
        kwargs["poolclass"] = NullPool
    return create_engine(db_url, **kwargs)


def get_engine():
    """Return the primary (write) engine."""
    global _engine
    if _engine is None:
        _engine = _build_engine(get_settings().database_url)
    return _engine


def get_read_engine():
    """Return the read replica engine, or primary if no replica configured.

    Configured via READ_REPLICA_URL env var. Falls back to primary silently
    so Phase 1-3 deployments work unchanged.
    """
    global _read_engine
    if _read_engine is None:
        replica_url = os.getenv("READ_REPLICA_URL", "").strip()
        if replica_url:
            _read_engine = _build_engine(replica_url)
            logger.info("postgres_read_replica_connected")
        else:
            _read_engine = get_engine()  # Fallback to primary
    return _read_engine


@contextmanager
def get_connection() -> Generator:
    """Write connection to primary database."""
    engine = get_engine()
    with engine.connect() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


@contextmanager
def write_db() -> Generator:
    """Explicit write connection — always hits the primary.

    Alias for get_connection() with intent-signalling name.
    Use this for INSERT/UPDATE/DELETE operations.
    """
    with get_connection() as conn:
        yield conn


@contextmanager
def read_db() -> Generator:
    """Read-only connection — hits replica if configured, primary otherwise.

    Use this for SELECT operations. Does NOT commit (read-only).
    At 5000 users, routing reads to replica reduces primary load ~40%.
    """
    engine = get_read_engine()
    with engine.connect() as conn:
        yield conn


# ── Schema initialization ─────────────────────────────────────────────────────

def init_postgres_schema() -> None:
    """Create all tables and seed the default tenant. Idempotent."""
    engine = get_engine()
    metadata.create_all(engine)
    _seed_default_tenant()
    logger.info("postgres_schema_initialized")


def _seed_default_tenant() -> None:
    """Insert the default tenant if it doesn't exist yet."""
    with get_connection() as conn:
        existing = conn.execute(
            text("SELECT id FROM tenants WHERE id = :id"),
            {"id": str(DEFAULT_TENANT_ID)},
        ).fetchone()
        if not existing:
            conn.execute(
                tenants.insert().values(
                    id=DEFAULT_TENANT_ID,
                    name="Default Organization",
                    slug="default",
                    is_active=True,
                    config=DEFAULT_TENANT_CONFIG,
                )
            )
            logger.info("default_tenant_seeded", tenant_id=str(DEFAULT_TENANT_ID))


# ── Health check ─────────────────────────────────────────────────────────────

def check_postgres_health() -> dict:
    try:
        with get_connection() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


# ── Document helpers ──────────────────────────────────────────────────────────

def get_document_count(tenant_id: uuid.UUID = DEFAULT_TENANT_ID) -> int:
    with get_connection() as conn:
        row = conn.execute(
            text("SELECT COUNT(*) FROM documents WHERE tenant_id = :tid"),
            {"tid": str(tenant_id)},
        ).fetchone()
        return row[0] if row else 0


def get_all_documents(tenant_id: uuid.UUID = DEFAULT_TENANT_ID) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            text(
                "SELECT id, filename, title, category, ingestion_status, "
                "chunk_count, created_at, uploaded_by "
                "FROM documents WHERE tenant_id = :tid ORDER BY created_at DESC"
            ),
            {"tid": str(tenant_id)},
        ).fetchall()
    return [
        {
            "id": str(r[0]), "filename": r[1], "title": r[2],
            "category": r[3], "ingestion_status": r[4],
            "chunk_count": r[5], "created_at": str(r[6]),
            "uploaded_by": str(r[7]) if r[7] else None,
        }
        for r in rows
    ]


def upsert_document(
    filename: str,
    title: str,
    file_type: str,
    storage_path: str,
    category: str,
    access_roles: list[str],
    content_hash: str,
    uploaded_by_id: Optional[uuid.UUID],
    tenant_id: uuid.UUID = DEFAULT_TENANT_ID,
) -> uuid.UUID:
    doc_id = uuid.uuid4()
    with get_connection() as conn:
        conn.execute(
            documents.insert().values(
                id=doc_id,
                tenant_id=tenant_id,
                filename=filename,
                title=title,
                file_type=file_type,
                storage_path=storage_path,
                category=category,
                access_roles=access_roles,
                content_hash=content_hash,
                ingestion_status="pending",
                uploaded_by=uploaded_by_id,
            )
        )
    return doc_id


def update_document_status(
    document_id: uuid.UUID,
    status: str,
    chunk_count: int = 0,
    error: Optional[str] = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            text(
                "UPDATE documents SET ingestion_status = :status, "
                "chunk_count = :count, ingestion_error = :err, "
                "updated_at = NOW() WHERE id = :id"
            ),
            {"status": status, "count": chunk_count, "err": error, "id": str(document_id)},
        )


def delete_document(document_id: uuid.UUID, tenant_id: uuid.UUID = DEFAULT_TENANT_ID) -> bool:
    with get_connection() as conn:
        result = conn.execute(
            text(
                "DELETE FROM documents WHERE id = :id AND tenant_id = :tid"
            ),
            {"id": str(document_id), "tid": str(tenant_id)},
        )
        return result.rowcount > 0


# ── User helpers ──────────────────────────────────────────────────────────────

def get_user_by_username(username: str, tenant_id: uuid.UUID = DEFAULT_TENANT_ID) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            text(
                "SELECT id, tenant_id, username, email, hashed_password, role, "
                "department, full_name, is_active, status, totp_enabled, totp_secret "
                "FROM users WHERE username = :u AND tenant_id = :tid"
            ),
            {"u": username, "tid": str(tenant_id)},
        ).fetchone()
    if not row:
        return None
    return {
        "id": str(row[0]), "tenant_id": str(row[1]), "username": row[2],
        "email": row[3], "hashed_password": row[4], "role": row[5],
        "department": row[6], "full_name": row[7], "is_active": row[8],
        "status": row[9], "totp_enabled": row[10], "totp_secret": row[11],
    }


def create_user(
    username: str,
    hashed_password: str,
    role: str,
    email: Optional[str],
    department: Optional[str],
    full_name: str = "",
    phone: str = "",
    tenant_id: uuid.UUID = DEFAULT_TENANT_ID,
) -> uuid.UUID:
    user_id = uuid.uuid4()
    with get_connection() as conn:
        conn.execute(
            users.insert().values(
                id=user_id,
                tenant_id=tenant_id,
                username=username,
                email=email,
                hashed_password=hashed_password,
                role=role,
                department=department,
                full_name=full_name,
                phone=phone,
                is_active=True,
                status="pending_approval",
            )
        )
    return user_id


def get_all_users(tenant_id: uuid.UUID = DEFAULT_TENANT_ID) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            text(
                "SELECT id, username, email, role, department, is_active, status, created_at "
                "FROM users WHERE tenant_id = :tid ORDER BY created_at DESC"
            ),
            {"tid": str(tenant_id)},
        ).fetchall()
    return [
        {
            "id": str(r[0]), "username": r[1], "email": r[2],
            "role": r[3], "department": r[4], "is_active": r[5],
            "status": r[6], "created_at": str(r[7]),
        }
        for r in rows
    ]


# ── Audit log helpers ─────────────────────────────────────────────────────────

def write_audit_log(
    action: str,
    actor_id: Optional[uuid.UUID] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    extra: Optional[dict] = None,
    tenant_id: uuid.UUID = DEFAULT_TENANT_ID,
) -> None:
    try:
        with get_connection() as conn:
            conn.execute(
                audit_logs.insert().values(
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    action=action,
                    target_type=target_type,
                    target_id=target_id,
                    ip_address=ip_address,
                    metadata=extra or {},
                )
            )
    except Exception as e:
        # Audit logging must never crash the main request
        logger.error("audit_log_write_failed", error=str(e), action=action)


# ── Phase 4: Cache warming + Session cleanup helpers ──────────────────────────

def get_top_queries_for_tenant(
    tenant_id: Union[str, uuid.UUID],
    limit: int = 50,
    days: int = 30,
) -> list[dict]:
    """Return the most frequently asked queries for a tenant (last N days).

    Used by the cache warming Celery task to pre-populate the semantic cache.
    Returns queries that have answers — grounding the cache with real responses.
    """
    try:
        with read_db() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        m.content AS query,
                        r.content AS answer,
                        r.sources AS citations,
                        r.confidence,
                        COUNT(*) OVER (PARTITION BY m.content) AS frequency
                    FROM messages m
                    JOIN messages r ON r.session_id = m.session_id
                        AND r.role = 'assistant'
                        AND r.created_at > m.created_at
                    WHERE m.tenant_id = :tid
                      AND m.role = 'user'
                      AND m.created_at > NOW() - INTERVAL ':days days'
                    ORDER BY frequency DESC, m.created_at DESC
                    LIMIT :limit
                    """
                ),
                {"tid": str(tenant_id), "days": days, "limit": limit},
            ).fetchall()
        return [
            {
                "query": r[0],
                "answer": r[1],
                "citations": r[2] or [],
                "confidence": r[3] or 1.0,
                "suggested_questions": [],
            }
            for r in rows
        ]
    except Exception as e:
        logger.error("get_top_queries_failed", tenant_id=str(tenant_id), error=str(e))
        return []


def cleanup_expired_sessions(days_old: int = 7) -> int:
    """Delete expired refresh tokens from the database.

    Called by Celery Beat daily at 2am UTC.
    Returns number of rows deleted.
    """
    try:
        with write_db() as conn:
            result = conn.execute(
                text(
                    "DELETE FROM refresh_tokens WHERE expires_at < NOW() OR revoked = true"
                )
            )
            deleted = result.rowcount
            logger.info("session_cleanup_done", deleted=deleted)
            return deleted
    except Exception as e:
        logger.error("session_cleanup_failed", error=str(e))
        return 0
