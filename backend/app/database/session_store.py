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
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, user_role TEXT NOT NULL,
    created_at REAL NOT NULL, last_active REAL NOT NULL, metadata TEXT DEFAULT '{}'
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
    content_hash TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
    query TEXT NOT NULL, answer TEXT NOT NULL, rating TEXT NOT NULL,
    timestamp REAL NOT NULL, user_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS query_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT NOT NULL,
    query_type TEXT, user_role TEXT NOT NULL, faithfulness_score REAL,
    hallucination_risk REAL, latency_ms REAL, top_chunk_score REAL,
    user_feedback TEXT, timestamp REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'employee',
    department TEXT, created_at REAL NOT NULL,
    full_name TEXT DEFAULT '', email TEXT DEFAULT '', phone TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS security_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    user_id TEXT,
    ip_address TEXT,
    details TEXT DEFAULT '{}',
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_security_events_ts ON security_events(timestamp);
CREATE TABLE IF NOT EXISTS refresh_tokens (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    expires_at REAL NOT NULL,
    revoked INTEGER DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);
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
