"""Background task processing — async job queue for heavy operations (Phase 2).

Enhanced with:
  - Task cancellation support (cooperative cancellation via flag)
  - Persistent task storage in SQLite (survives restarts)
  - Progress callbacks for real-time monitoring
  - Task type filtering and pagination
  - Automatic stale task cleanup (tasks stuck running > 30 min)
"""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

import structlog

from backend.app.core.config import get_settings

logger = structlog.get_logger()

MAX_TASK_HISTORY = 200
STALE_TASK_TIMEOUT = 1800  # 30 minutes — mark stuck tasks as failed

# In-memory cancellation flags (thread-safe)
_cancel_flags: dict[str, threading.Event] = {}
_progress_callbacks: dict[str, list[Callable]] = {}


@dataclass
class TaskStatus:
    task_id: str
    task_type: str
    status: str  # "pending", "running", "completed", "failed", "cancelled"
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    progress: int = 0  # 0-100
    user_id: str = ""


def _get_db() -> str:
    """Return the SQLite database path."""
    return get_settings().db_path


def _ensure_tasks_table() -> None:
    """Create background_tasks table if it doesn't exist."""
    try:
        with sqlite3.connect(_get_db()) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS background_tasks (
                    task_id TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    progress INTEGER DEFAULT 0,
                    created_at REAL NOT NULL,
                    started_at REAL,
                    completed_at REAL,
                    result TEXT,
                    error TEXT,
                    user_id TEXT DEFAULT ''
                )
            """)
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_bg_tasks_status ON background_tasks(status)"
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_bg_tasks_created ON background_tasks(created_at)"
            )
    except Exception as e:
        logger.warning("bg_tasks_table_init_failed", error=str(e))


# Initialize table on import
_ensure_tasks_table()


def create_task(task_type: str, user_id: str = "") -> TaskStatus:
    """Register a new background task."""
    task_id = str(uuid.uuid4())[:8]
    now = time.time()
    task = TaskStatus(
        task_id=task_id,
        task_type=task_type,
        status="pending",
        created_at=now,
        user_id=user_id,
    )

    # Store in SQLite for persistence
    try:
        with sqlite3.connect(_get_db()) as con:
            con.execute(
                "INSERT INTO background_tasks "
                "(task_id, task_type, status, progress, created_at, user_id) "
                "VALUES (?,?,?,?,?,?)",
                (task_id, task_type, "pending", 0, now, user_id),
            )
    except Exception as e:
        logger.warning("task_persist_failed", task_id=task_id, error=str(e))

    # Set up cancellation flag
    _cancel_flags[task_id] = threading.Event()

    logger.info("task_created", task_id=task_id, task_type=task_type, user_id=user_id)
    _prune_old_tasks()
    return task


def update_task(
    task_id: str,
    status: str,
    progress: int = 0,
    result: Optional[dict] = None,
    error: Optional[str] = None,
) -> None:
    """Update task status in persistent store."""
    import json

    now = time.time()
    started_at = now if status == "running" else None
    completed_at = now if status in ("completed", "failed", "cancelled") else None

    try:
        with sqlite3.connect(_get_db()) as con:
            if started_at:
                con.execute(
                    "UPDATE background_tasks SET status=?, progress=?, started_at=COALESCE(started_at,?) "
                    "WHERE task_id=?",
                    (status, progress, started_at, task_id),
                )
            elif completed_at:
                con.execute(
                    "UPDATE background_tasks SET status=?, progress=?, completed_at=?, result=?, error=? "
                    "WHERE task_id=?",
                    (status, progress, completed_at,
                     json.dumps(result) if result else None,
                     error, task_id),
                )
            else:
                con.execute(
                    "UPDATE background_tasks SET status=?, progress=? WHERE task_id=?",
                    (status, progress, task_id),
                )
    except Exception as e:
        logger.warning("task_update_failed", task_id=task_id, error=str(e))

    # Fire progress callbacks
    for cb in _progress_callbacks.get(task_id, []):
        try:
            cb(task_id, status, progress)
        except Exception:
            pass

    # Clean up cancellation flag on terminal states
    if status in ("completed", "failed", "cancelled"):
        _cancel_flags.pop(task_id, None)
        _progress_callbacks.pop(task_id, None)


def get_task(task_id: str) -> Optional[TaskStatus]:
    """Get task status by ID from persistent store."""
    import json

    try:
        with sqlite3.connect(_get_db()) as con:
            row = con.execute(
                "SELECT task_id, task_type, status, progress, created_at, "
                "started_at, completed_at, result, error, user_id "
                "FROM background_tasks WHERE task_id=?",
                (task_id,),
            ).fetchone()
        if not row:
            return None
        return TaskStatus(
            task_id=row[0],
            task_type=row[1],
            status=row[2],
            progress=row[3],
            created_at=row[4],
            started_at=row[5],
            completed_at=row[6],
            result=json.loads(row[7]) if row[7] else None,
            error=row[8],
            user_id=row[9] or "",
        )
    except Exception as e:
        logger.warning("task_get_failed", task_id=task_id, error=str(e))
        return None


def list_tasks(
    limit: int = 20,
    task_type: Optional[str] = None,
    status: Optional[str] = None,
    offset: int = 0,
) -> list[dict]:
    """List recent tasks with optional filtering."""
    import json

    try:
        query = "SELECT task_id, task_type, status, progress, created_at, completed_at, error, result, user_id FROM background_tasks"
        params: list = []
        conditions: list[str] = []

        if task_type:
            conditions.append("task_type=?")
            params.append(task_type)
        if status:
            conditions.append("status=?")
            params.append(status)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with sqlite3.connect(_get_db()) as con:
            rows = con.execute(query, params).fetchall()

        return [
            {
                "task_id": r[0],
                "task_type": r[1],
                "status": r[2],
                "progress": r[3],
                "created_at": r[4],
                "completed_at": r[5],
                "error": r[6],
                "result": json.loads(r[7]) if r[7] else None,
                "user_id": r[8] or "",
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("task_list_failed", error=str(e))
        return []


def cancel_task(task_id: str) -> bool:
    """Request cooperative cancellation of a running task.

    Returns True if the cancellation signal was sent, False if the task
    is not in a cancellable state.
    """
    task = get_task(task_id)
    if not task:
        return False
    if task.status not in ("pending", "running"):
        return False

    # Set the cancellation flag — running tasks should check is_cancelled()
    flag = _cancel_flags.get(task_id)
    if flag:
        flag.set()

    update_task(task_id, "cancelled")
    logger.info("task_cancelled", task_id=task_id)
    return True


def is_cancelled(task_id: str) -> bool:
    """Check if a task has been cancelled. Call this in long-running loops."""
    flag = _cancel_flags.get(task_id)
    return flag.is_set() if flag else False


def register_progress_callback(task_id: str, callback: Callable) -> None:
    """Register a callback to be called on task progress updates."""
    _progress_callbacks.setdefault(task_id, []).append(callback)


def cleanup_stale_tasks() -> int:
    """Mark tasks stuck in 'running' for > 30 min as failed."""
    cutoff = time.time() - STALE_TASK_TIMEOUT
    try:
        with sqlite3.connect(_get_db()) as con:
            result = con.execute(
                "UPDATE background_tasks SET status='failed', "
                "error='Task timed out (exceeded 30 min)', completed_at=? "
                "WHERE status='running' AND started_at < ?",
                (time.time(), cutoff),
            )
            count = result.rowcount
            if count > 0:
                logger.info("stale_tasks_cleaned", count=count)
            return count
    except Exception:
        return 0


def _prune_old_tasks() -> None:
    """Remove oldest tasks when exceeding MAX_TASK_HISTORY."""
    try:
        with sqlite3.connect(_get_db()) as con:
            count = con.execute("SELECT COUNT(*) FROM background_tasks").fetchone()[0]
            if count > MAX_TASK_HISTORY:
                con.execute(
                    "DELETE FROM background_tasks WHERE task_id IN "
                    "(SELECT task_id FROM background_tasks ORDER BY created_at ASC LIMIT ?)",
                    (count - MAX_TASK_HISTORY,),
                )
    except Exception:
        pass


# ── Background job functions (called via FastAPI BackgroundTasks) ─────────────

def bg_index_document(task_id: str, content: bytes, filename: str, title: str,
                      category: str, roles: list, version: str, user_id: str) -> None:
    """Background: index a document after upload."""
    try:
        update_task(task_id, "running", 10)

        if is_cancelled(task_id):
            update_task(task_id, "cancelled")
            return

        from backend.app.core.dependencies import get_registry
        reg = get_registry()
        update_task(task_id, "running", 30)

        if is_cancelled(task_id):
            update_task(task_id, "cancelled")
            return

        result = reg["ingestion"].ingest(content, filename, title, category, roles, "", version, user_id)
        update_task(task_id, "completed", 100, result={
            "document_id": result.document_id,
            "chunk_count": result.chunk_count,
            "status": result.status,
        })

        # Invalidate cache after new document indexed
        from backend.app.core.semantic_cache import invalidate_on_document_change
        invalidate_on_document_change(filename)

    except Exception as e:
        update_task(task_id, "failed", error=str(e))
        logger.error("bg_index_failed", task_id=task_id, error=str(e))


def bg_generate_report(task_id: str, report_type: str, db_path: str, days: int) -> None:
    """Background: generate an audit/analytics report."""
    try:
        update_task(task_id, "running", 10)

        if is_cancelled(task_id):
            update_task(task_id, "cancelled")
            return

        import json

        with sqlite3.connect(db_path) as con:
            since = time.time() - (days * 86400)
            if report_type == "audit":
                rows = con.execute(
                    "SELECT event_type, user_id, ip_address, details, timestamp "
                    "FROM security_events WHERE timestamp>? ORDER BY timestamp DESC",
                    (since,)
                ).fetchall()
                update_task(task_id, "running", 50)
                data = [{"event_type": r[0], "user_id": r[1], "ip": r[2],
                         "details": json.loads(r[3]) if r[3] else {}, "timestamp": r[4]} for r in rows]
                update_task(task_id, "completed", 100, result={"rows": len(data), "report_type": report_type})
            elif report_type == "analytics":
                qt = con.execute("SELECT COUNT(*) FROM query_logs WHERE timestamp>?", (since,)).fetchone()[0]
                avg = con.execute("SELECT AVG(faithfulness_score), AVG(latency_ms) FROM query_logs WHERE timestamp>?", (since,)).fetchone()
                update_task(task_id, "completed", 100, result={
                    "queries": qt, "avg_faithfulness": round(avg[0] or 0, 3),
                    "avg_latency_ms": round(avg[1] or 0, 1),
                })
    except Exception as e:
        update_task(task_id, "failed", error=str(e))
