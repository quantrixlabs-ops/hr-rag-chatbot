"""SQLite-backed session & metadata storage — Section 12.2."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid

import structlog

from backend.app.core.config import get_settings
from backend.app.models.session_models import ConversationTurn, Session

logger = structlog.get_logger()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    plan TEXT DEFAULT 'trial',
    settings TEXT DEFAULT '{}',
    created_at REAL NOT NULL,
    is_active INTEGER DEFAULT 1
);
INSERT OR IGNORE INTO tenants (tenant_id, name, slug, plan, created_at, is_active)
    VALUES ('00000000-0000-0000-0000-000000000001', 'Default Organization', 'default', 'enterprise', 0, 1);
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, user_role TEXT NOT NULL,
    created_at REAL NOT NULL, last_active REAL NOT NULL, metadata TEXT DEFAULT '{}',
    tenant_id TEXT DEFAULT '00000000-0000-0000-0000-000000000001'
);
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
    role TEXT NOT NULL, content TEXT NOT NULL, timestamp REAL NOT NULL,
    metadata TEXT DEFAULT '{}', FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);
CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id);
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL,
    access_roles TEXT NOT NULL, effective_date TEXT, version TEXT,
    source_filename TEXT NOT NULL, uploaded_by TEXT NOT NULL,
    uploaded_at REAL NOT NULL, page_count INTEGER DEFAULT 0, chunk_count INTEGER DEFAULT 0,
    content_hash TEXT DEFAULT '', tenant_id TEXT DEFAULT '00000000-0000-0000-0000-000000000001',
    ingestion_status TEXT DEFAULT 'done'
);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
    query TEXT NOT NULL, answer TEXT NOT NULL, rating TEXT NOT NULL,
    timestamp REAL NOT NULL, user_id TEXT NOT NULL, tenant_id TEXT DEFAULT '00000000-0000-0000-0000-000000000001'
);
CREATE TABLE IF NOT EXISTS query_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT NOT NULL,
    query_type TEXT, user_role TEXT NOT NULL, faithfulness_score REAL,
    hallucination_risk REAL, latency_ms REAL, top_chunk_score REAL,
    user_feedback TEXT, timestamp REAL NOT NULL, sources_used TEXT DEFAULT '',
    tenant_id TEXT DEFAULT '00000000-0000-0000-0000-000000000001'
);
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'employee',
    department TEXT, created_at REAL NOT NULL,
    full_name TEXT DEFAULT '', email TEXT DEFAULT '', phone TEXT DEFAULT '',
    tenant_id TEXT DEFAULT '00000000-0000-0000-0000-000000000001',
    status TEXT DEFAULT 'pending_approval',
    email_verified INTEGER DEFAULT 0,
    verification_token TEXT DEFAULT '',
    suspended INTEGER DEFAULT 0,
    totp_secret TEXT DEFAULT '',
    totp_enabled INTEGER DEFAULT 0,
    secret_question TEXT DEFAULT '',
    secret_answer_hash TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS saved_prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    prompt_text TEXT NOT NULL,
    created_at REAL NOT NULL,
    tenant_id TEXT DEFAULT '00000000-0000-0000-0000-000000000001'
);
CREATE TABLE IF NOT EXISTS escalations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    session_id TEXT,
    query TEXT NOT NULL,
    answer TEXT DEFAULT '',
    reason TEXT DEFAULT '',
    status TEXT DEFAULT 'open',
    assigned_to TEXT DEFAULT '',
    created_at REAL NOT NULL,
    resolved_at REAL,
    tenant_id TEXT DEFAULT '00000000-0000-0000-0000-000000000001'
);
CREATE TABLE IF NOT EXISTS security_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    user_id TEXT,
    ip_address TEXT,
    details TEXT DEFAULT '{}',
    timestamp REAL NOT NULL,
    tenant_id TEXT DEFAULT '00000000-0000-0000-0000-000000000001'
);
CREATE INDEX IF NOT EXISTS idx_security_events_ts ON security_events(timestamp);
CREATE TABLE IF NOT EXISTS response_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    query_hash TEXT NOT NULL,
    answer TEXT NOT NULL,
    confidence REAL DEFAULT 0.0,
    faithfulness REAL DEFAULT 0.0,
    verdict TEXT DEFAULT '',
    sources_used TEXT DEFAULT '[]',
    safety_issues TEXT DEFAULT '[]',
    model TEXT DEFAULT '',
    version INTEGER DEFAULT 1,
    created_at REAL NOT NULL,
    tenant_id TEXT DEFAULT '00000000-0000-0000-0000-000000000001'
);
CREATE INDEX IF NOT EXISTS idx_resp_versions_session ON response_versions(session_id);
CREATE TABLE IF NOT EXISTS refresh_tokens (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    expires_at REAL NOT NULL,
    revoked INTEGER DEFAULT 0,
    created_at REAL NOT NULL,
    tenant_id TEXT DEFAULT '00000000-0000-0000-0000-000000000001'
);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);

-- Phase A: Tickets (lifecycle: raised→assigned→in_progress→resolved→closed→rejected)
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general',
    priority TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'raised',
    raised_by TEXT NOT NULL,
    assigned_to TEXT DEFAULT '',
    branch_id TEXT DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    resolved_at REAL,
    auto_close_at REAL,
    feedback TEXT DEFAULT '',
    rating INTEGER DEFAULT 0,
    -- Escalation fields (empty for normal tickets)
    is_escalation INTEGER DEFAULT 0,
    escalation_reason TEXT DEFAULT '',
    chat_history TEXT DEFAULT '',
    ai_suggestion TEXT DEFAULT '',
    hr_response TEXT DEFAULT '',
    tenant_id TEXT DEFAULT '00000000-0000-0000-0000-000000000001',
    FOREIGN KEY (raised_by) REFERENCES users(user_id)
);
CREATE INDEX IF NOT EXISTS idx_tickets_raised_by ON tickets(raised_by);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_assigned ON tickets(assigned_to);

CREATE TABLE IF NOT EXISTS ticket_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL,
    action TEXT NOT NULL,
    performed_by TEXT NOT NULL,
    old_value TEXT DEFAULT '',
    new_value TEXT DEFAULT '',
    comment TEXT DEFAULT '',
    timestamp REAL NOT NULL,
    FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id)
);
CREATE INDEX IF NOT EXISTS idx_ticket_history_ticket ON ticket_history(ticket_id);

-- Phase A: Anonymous complaints / whistleblower (visible only to HR Head)
CREATE TABLE IF NOT EXISTS complaints (
    complaint_id TEXT PRIMARY KEY,
    category TEXT NOT NULL DEFAULT 'general',
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'submitted',
    submitted_at REAL NOT NULL,
    reviewed_by TEXT DEFAULT '',
    reviewed_at REAL,
    resolution TEXT DEFAULT '',
    tenant_id TEXT DEFAULT '00000000-0000-0000-0000-000000000001'
);
CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status);

-- Phase A: Notifications
CREATE TABLE IF NOT EXISTS notifications (
    notification_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    notification_type TEXT NOT NULL DEFAULT 'info',
    is_read INTEGER DEFAULT 0,
    link TEXT DEFAULT '',
    created_at REAL NOT NULL,
    tenant_id TEXT DEFAULT '00000000-0000-0000-0000-000000000001',
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(user_id, is_read);

-- Phase A: HR Contacts
CREATE TABLE IF NOT EXISTS hr_contacts (
    contact_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'hr_team',
    email TEXT NOT NULL DEFAULT '',
    phone TEXT DEFAULT '',
    branch_id TEXT DEFAULT '',
    is_available INTEGER DEFAULT 1,
    tenant_id TEXT DEFAULT '00000000-0000-0000-0000-000000000001'
);

-- Phase A: Organization branches/locations
CREATE TABLE IF NOT EXISTS branches (
    branch_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    location TEXT NOT NULL DEFAULT '',
    address TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    created_at REAL NOT NULL,
    tenant_id TEXT DEFAULT '00000000-0000-0000-0000-000000000001'
);

-- FAQ: Curated Q&A pairs that bypass RAG for common questions
CREATE TABLE IF NOT EXISTS faqs (
    faq_id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    keywords TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general',
    is_active INTEGER DEFAULT 1,
    created_by TEXT DEFAULT '',
    created_at REAL NOT NULL,
    tenant_id TEXT DEFAULT '00000000-0000-0000-0000-000000000001'
);
CREATE INDEX IF NOT EXISTS idx_faqs_active ON faqs(is_active);

-- CFLS: Enhanced feedback with issue categories and detailed tracking
CREATE TABLE IF NOT EXISTS feedback_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    user_role TEXT NOT NULL DEFAULT 'employee',
    department TEXT DEFAULT '',
    session_id TEXT DEFAULT '',
    query TEXT NOT NULL,
    response TEXT NOT NULL,
    feedback_type TEXT NOT NULL DEFAULT 'negative',
    issue_category TEXT DEFAULT '',
    custom_comment TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    reviewed_by TEXT DEFAULT '',
    reviewed_at REAL,
    review_notes TEXT DEFAULT '',
    created_at REAL NOT NULL,
    tenant_id TEXT DEFAULT '00000000-0000-0000-0000-000000000001'
);
CREATE INDEX IF NOT EXISTS idx_feedback_logs_status ON feedback_logs(status);
CREATE INDEX IF NOT EXISTS idx_feedback_logs_created ON feedback_logs(created_at);

-- CFLS: HR-approved knowledge corrections (highest priority in response pipeline)
CREATE TABLE IF NOT EXISTS knowledge_corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_pattern TEXT NOT NULL,
    corrected_response TEXT NOT NULL,
    keywords TEXT NOT NULL DEFAULT '',
    source_feedback_id INTEGER,
    approved_by TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    use_count INTEGER DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL,
    tenant_id TEXT DEFAULT '00000000-0000-0000-0000-000000000001',
    FOREIGN KEY (source_feedback_id) REFERENCES feedback_logs(id)
);
CREATE INDEX IF NOT EXISTS idx_corrections_active ON knowledge_corrections(is_active);

-- CLS: Version history for knowledge corrections (audit trail + rollback)
CREATE TABLE IF NOT EXISTS knowledge_correction_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    correction_id INTEGER NOT NULL,
    version_number INTEGER NOT NULL DEFAULT 1,
    query_pattern TEXT NOT NULL,
    corrected_response TEXT NOT NULL,
    keywords TEXT DEFAULT '',
    change_summary TEXT DEFAULT '',
    changed_by TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (correction_id) REFERENCES knowledge_corrections(id)
);
CREATE INDEX IF NOT EXISTS idx_correction_versions_cid ON knowledge_correction_versions(correction_id);

-- CLS: Learning queue — auto-populated from repeated negative feedback patterns
CREATE TABLE IF NOT EXISTS learning_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_pattern TEXT NOT NULL,
    sample_query TEXT NOT NULL DEFAULT '',
    sample_response TEXT NOT NULL DEFAULT '',
    feedback_count INTEGER DEFAULT 1,
    issue_category TEXT DEFAULT '',
    ai_suggested_response TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    reviewed_by TEXT DEFAULT '',
    reviewed_at REAL,
    created_at REAL NOT NULL,
    updated_at REAL,
    tenant_id TEXT DEFAULT '00000000-0000-0000-0000-000000000001'
);
CREATE INDEX IF NOT EXISTS idx_learning_queue_status ON learning_queue(status);

-- External AI Providers (Admin-only configuration)
CREATE TABLE IF NOT EXISTS ai_providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_name TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    api_key_encrypted TEXT NOT NULL DEFAULT '',
    model_name TEXT NOT NULL DEFAULT '',
    base_url TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'inactive',
    priority INTEGER NOT NULL DEFAULT 99,
    max_tokens INTEGER DEFAULT 1024,
    temperature REAL DEFAULT 0.0,
    usage_count INTEGER DEFAULT 0,
    usage_limit INTEGER DEFAULT 0,
    created_by TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL,
    tenant_id TEXT DEFAULT '00000000-0000-0000-0000-000000000001'
);
CREATE INDEX IF NOT EXISTS idx_ai_providers_status ON ai_providers(status);

-- AI usage logs (audit trail for external API calls)
CREATE TABLE IF NOT EXISTS ai_usage_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_name TEXT NOT NULL,
    model_name TEXT NOT NULL DEFAULT '',
    query_hash TEXT NOT NULL DEFAULT '',
    response_time_ms REAL DEFAULT 0,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    success INTEGER DEFAULT 1,
    error_message TEXT DEFAULT '',
    fallback_from TEXT DEFAULT '',
    timestamp REAL NOT NULL,
    tenant_id TEXT DEFAULT '00000000-0000-0000-0000-000000000001'
);
CREATE INDEX IF NOT EXISTS idx_ai_usage_ts ON ai_usage_logs(timestamp);

-- AI Mode: admin chooses between internal (Ollama) or external API
CREATE TABLE IF NOT EXISTS ai_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    ai_mode TEXT NOT NULL DEFAULT 'internal',
    active_provider TEXT NOT NULL DEFAULT '',
    updated_by TEXT DEFAULT '',
    updated_at REAL DEFAULT 0,
    tenant_id TEXT DEFAULT '00000000-0000-0000-0000-000000000001'
);
INSERT OR IGNORE INTO ai_settings (id, ai_mode, active_provider) VALUES (1, 'internal', '');
"""


def init_database(db_path: Optional[str] = None) -> None:
    path = db_path or get_settings().db_path
    with sqlite3.connect(path) as con:
        con.executescript(_SCHEMA)
        # Migrations: add columns/tables that may be missing from older databases
        _run_migrations(con)


def _run_migrations(con: sqlite3.Connection) -> None:
    """Apply schema migrations for columns/tables added after initial release."""
    # Get existing columns for each table
    def _has_column(table: str, column: str) -> bool:
        cols = {row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
        return column in cols

    # Migration: documents.content_hash (added for SHA-256 deduplication)
    if not _has_column("documents", "content_hash"):
        con.execute("ALTER TABLE documents ADD COLUMN content_hash TEXT DEFAULT ''")

    # Migration: documents.source_filename may be missing in very old schemas
    if not _has_column("documents", "source_filename"):
        con.execute("ALTER TABLE documents ADD COLUMN source_filename TEXT DEFAULT ''")

    # Migration: query_logs.sources_used — tracks which documents answered each query
    if not _has_column("query_logs", "sources_used"):
        con.execute("ALTER TABLE query_logs ADD COLUMN sources_used TEXT DEFAULT ''")

    # Migration: users profile fields
    for col in ("full_name", "email", "phone"):
        if not _has_column("users", col):
            con.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT DEFAULT ''")

    # Migration: 2FA TOTP fields
    if not _has_column("users", "totp_secret"):
        con.execute("ALTER TABLE users ADD COLUMN totp_secret TEXT DEFAULT ''")
    if not _has_column("users", "totp_enabled"):
        con.execute("ALTER TABLE users ADD COLUMN totp_enabled INTEGER DEFAULT 0")

    # Migration: SaaS-ready tenant_id on all tables
    _tenant_tables = ["users", "sessions", "documents", "feedback",
                      "query_logs", "security_events", "refresh_tokens"]
    for table in _tenant_tables:
        if not _has_column(table, "tenant_id"):
            con.execute(f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT DEFAULT '00000000-0000-0000-0000-000000000001'")

    # Migration: User status/approval workflow (Phase 0)
    for col, default in [("status", "'active'"), ("email_verified", "0"),
                         ("verification_token", "''"), ("suspended", "0")]:
        if not _has_column("users", col):
            con.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT DEFAULT {default}" if col in ("status", "verification_token")
                        else f"ALTER TABLE users ADD COLUMN {col} INTEGER DEFAULT {default}")

    # Migration: Document sensitivity classification
    if not _has_column("documents", "sensitivity"):
        con.execute("ALTER TABLE documents ADD COLUMN sensitivity TEXT DEFAULT 'internal'")

    # Phase A: User profile extensions
    if not _has_column("users", "employee_id"):
        con.execute("ALTER TABLE users ADD COLUMN employee_id TEXT DEFAULT ''")
    if not _has_column("users", "branch_id"):
        con.execute("ALTER TABLE users ADD COLUMN branch_id TEXT DEFAULT ''")
    if not _has_column("users", "team"):
        con.execute("ALTER TABLE users ADD COLUMN team TEXT DEFAULT ''")
    if not _has_column("users", "requested_role"):
        con.execute("ALTER TABLE users ADD COLUMN requested_role TEXT DEFAULT 'employee'")

    # Ticket employee response: feedback, rating, auto-close
    if not _has_column("tickets", "auto_close_at"):
        con.execute("ALTER TABLE tickets ADD COLUMN auto_close_at REAL")
    if not _has_column("tickets", "feedback"):
        con.execute("ALTER TABLE tickets ADD COLUMN feedback TEXT DEFAULT ''")
    if not _has_column("tickets", "rating"):
        con.execute("ALTER TABLE tickets ADD COLUMN rating INTEGER DEFAULT 0")

    # Phase A: Document approval workflow columns
    if not _has_column("documents", "approval_status"):
        con.execute("ALTER TABLE documents ADD COLUMN approval_status TEXT DEFAULT 'approved'")
    if not _has_column("documents", "approved_by"):
        con.execute("ALTER TABLE documents ADD COLUMN approved_by TEXT DEFAULT ''")
    if not _has_column("documents", "approved_at"):
        con.execute("ALTER TABLE documents ADD COLUMN approved_at REAL")

    # Escalation fields on tickets table
    for col, default in [("is_escalation", "0"), ("escalation_reason", "''"),
                         ("chat_history", "''"), ("ai_suggestion", "''"), ("hr_response", "''")]:
        if not _has_column("tickets", col):
            dtype = "INTEGER" if col == "is_escalation" else "TEXT"
            con.execute(f"ALTER TABLE tickets ADD COLUMN {col} {dtype} DEFAULT {default}")

    # Forgot password: secret question fields
    if not _has_column("users", "secret_question"):
        con.execute("ALTER TABLE users ADD COLUMN secret_question TEXT DEFAULT ''")
    if not _has_column("users", "secret_answer_hash"):
        con.execute("ALTER TABLE users ADD COLUMN secret_answer_hash TEXT DEFAULT ''")


# Phase 4: Session limits
MAX_TURNS_PER_SESSION = 200  # Hard cap — prevents runaway sessions
STALE_SESSION_DAYS = 90  # Sessions older than this are eligible for cleanup


class SessionStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_settings().db_path

    # ── Session CRUD ─────────────────────────────────────────────────────
    def create_session(self, user_id: str, user_role: str) -> Session:
        sid = str(uuid.uuid4())
        now = time.time()
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT INTO sessions (session_id,user_id,user_role,created_at,last_active) VALUES (?,?,?,?,?)",
                (sid, user_id, user_role, now, now),
            )
        return Session(session_id=sid, user_id=user_id, user_role=user_role, turns=[], created_at=now, last_active=now)

    def get_session(self, session_id: str) -> Optional[Session]:
        with sqlite3.connect(self.db_path) as con:
            row = con.execute(
                "SELECT session_id,user_id,user_role,created_at,last_active,metadata FROM sessions WHERE session_id=?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        turns = self.get_recent_turns(session_id, limit=100)
        return Session(
            session_id=row[0], user_id=row[1], user_role=row[2],
            turns=turns, created_at=row[3], last_active=row[4],
            metadata=json.loads(row[5]) if row[5] else {},
        )

    def add_turn(self, session_id: str, role: str, content: str, metadata: Optional[dict] = None) -> None:
        now = time.time()
        with sqlite3.connect(self.db_path) as con:
            # Phase 4: Enforce max turns per session
            turn_count = con.execute(
                "SELECT COUNT(*) FROM turns WHERE session_id=?", (session_id,)
            ).fetchone()[0]
            if turn_count >= MAX_TURNS_PER_SESSION:
                logger.warning("session_turn_limit_reached", session_id=session_id, turns=turn_count)
                # Trim oldest turns to make room (keep last 80% of max)
                keep = int(MAX_TURNS_PER_SESSION * 0.8)
                trim_count = turn_count - keep
                con.execute(
                    "DELETE FROM turns WHERE id IN "
                    "(SELECT id FROM turns WHERE session_id=? ORDER BY timestamp ASC LIMIT ?)",
                    (session_id, trim_count),
                )

            con.execute(
                "INSERT INTO turns (session_id,role,content,timestamp,metadata) VALUES (?,?,?,?,?)",
                (session_id, role, content, now, json.dumps(metadata or {})),
            )
            con.execute("UPDATE sessions SET last_active=? WHERE session_id=?", (now, session_id))

    def get_recent_turns(self, session_id: str, limit: int = 5) -> list[ConversationTurn]:
        with sqlite3.connect(self.db_path) as con:
            rows = con.execute(
                "SELECT role,content,timestamp,metadata FROM turns WHERE session_id=? ORDER BY timestamp DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [ConversationTurn(role=r[0], content=r[1], timestamp=r[2], metadata=json.loads(r[3]) if r[3] else None) for r in reversed(rows)]

    def get_user_sessions(self, user_id: str) -> list[dict]:
        with sqlite3.connect(self.db_path) as con:
            rows = con.execute(
                "SELECT s.session_id,s.created_at,s.last_active,"
                "(SELECT COUNT(*) FROM turns t WHERE t.session_id=s.session_id) AS turn_count,"
                "(SELECT content FROM turns t WHERE t.session_id=s.session_id AND t.role='user' ORDER BY t.timestamp ASC LIMIT 1) AS preview "
                "FROM sessions s WHERE s.user_id=? ORDER BY s.last_active DESC",
                (user_id,),
            ).fetchall()
        return [{"session_id": r[0], "created_at": r[1], "last_active": r[2], "turn_count": r[3], "preview": (r[4] or "")[:100]} for r in rows]

    def delete_session(self, session_id: str) -> None:
        with sqlite3.connect(self.db_path) as con:
            con.execute("DELETE FROM turns WHERE session_id=?", (session_id,))
            con.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))

    # ── Phase 4: Stale session cleanup ───────────────────────────────

    def cleanup_stale_sessions(self, max_age_days: int = STALE_SESSION_DAYS) -> int:
        """Delete sessions (and their turns) that have been inactive for max_age_days.

        Returns the number of sessions deleted. Safe to call periodically
        (e.g., from a background task or admin endpoint).
        """
        cutoff = time.time() - (max_age_days * 86400)
        with sqlite3.connect(self.db_path) as con:
            stale = con.execute(
                "SELECT session_id FROM sessions WHERE last_active < ?", (cutoff,)
            ).fetchall()
            if not stale:
                return 0
            stale_ids = [r[0] for r in stale]
            placeholders = ",".join("?" * len(stale_ids))
            con.execute(f"DELETE FROM turns WHERE session_id IN ({placeholders})", stale_ids)
            con.execute(f"DELETE FROM sessions WHERE session_id IN ({placeholders})", stale_ids)
        logger.info("stale_sessions_cleaned", count=len(stale_ids), cutoff_days=max_age_days)
        return len(stale_ids)

    def get_session_turn_count(self, session_id: str) -> int:
        """Return the number of turns in a session."""
        with sqlite3.connect(self.db_path) as con:
            row = con.execute(
                "SELECT COUNT(*) FROM turns WHERE session_id=?", (session_id,)
            ).fetchone()
        return row[0] if row else 0

    # ── Phase 4: GDPR data retention cleanup ─────────────────────────

    def gdpr_cleanup(self, retention_days: int = 365) -> dict:
        """Delete user data older than retention_days for GDPR compliance.

        Cleans: sessions, turns, feedback, query_logs.
        Returns counts of deleted records per table.
        """
        cutoff = time.time() - (retention_days * 86400)
        result: dict[str, int] = {}
        with sqlite3.connect(self.db_path) as con:
            # Old sessions + turns
            old_sessions = con.execute(
                "SELECT session_id FROM sessions WHERE last_active < ?", (cutoff,)
            ).fetchall()
            if old_sessions:
                sids = [r[0] for r in old_sessions]
                ph = ",".join("?" * len(sids))
                cur = con.execute(f"DELETE FROM turns WHERE session_id IN ({ph})", sids)
                result["turns"] = cur.rowcount
                cur = con.execute(f"DELETE FROM sessions WHERE session_id IN ({ph})", sids)
                result["sessions"] = cur.rowcount
            else:
                result["turns"] = 0
                result["sessions"] = 0

            # Old feedback
            cur = con.execute("DELETE FROM feedback WHERE timestamp < ?", (cutoff,))
            result["feedback"] = cur.rowcount

            # Old query logs
            cur = con.execute("DELETE FROM query_logs WHERE timestamp < ?", (cutoff,))
            result["query_logs"] = cur.rowcount

            # Old security events (keep 2 years for compliance, not retention_days)
            sec_cutoff = time.time() - (730 * 86400)
            cur = con.execute("DELETE FROM security_events WHERE timestamp < ?", (sec_cutoff,))
            result["security_events"] = cur.rowcount

        logger.info("gdpr_cleanup_complete", retention_days=retention_days, deleted=result)
        return result
