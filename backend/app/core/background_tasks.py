"""Background task processing — async job queue for heavy operations (Phase 2).

Uses FastAPI BackgroundTasks for fire-and-forget jobs plus an in-memory
task tracker for status monitoring.

Handles:
  - Document indexing (after upload)
  - Report generation (audit exports)
  - Vector store maintenance (cleanup, reindex)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import structlog

logger = structlog.get_logger()

# In-memory task registry (replace with Redis/DB for multi-worker setups)
_tasks: dict[str, "TaskStatus"] = {}
MAX_TASK_HISTORY = 100


@dataclass
class TaskStatus:
    task_id: str
    task_type: str
    status: str  # "pending", "running", "completed", "failed"
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    progress: int = 0  # 0-100


def create_task(task_type: str) -> TaskStatus:
    """Register a new background task."""
    task_id = str(uuid.uuid4())[:8]
    task = TaskStatus(
        task_id=task_id,
        task_type=task_type,
        status="pending",
        created_at=time.time(),
    )
    _tasks[task_id] = task
    # Prune old tasks
    if len(_tasks) > MAX_TASK_HISTORY:
        oldest = sorted(_tasks.values(), key=lambda t: t.created_at)[:len(_tasks) - MAX_TASK_HISTORY]
        for t in oldest:
            del _tasks[t.task_id]
    logger.info("task_created", task_id=task_id, task_type=task_type)
    return task


def update_task(task_id: str, status: str, progress: int = 0,
                result: Optional[dict] = None, error: Optional[str] = None) -> None:
    """Update task status."""
    task = _tasks.get(task_id)
    if not task:
        return
    task.status = status
    task.progress = progress
    if status == "running" and not task.started_at:
        task.started_at = time.time()
    if status in ("completed", "failed"):
        task.completed_at = time.time()
    if result:
        task.result = result
    if error:
        task.error = error


def get_task(task_id: str) -> Optional[TaskStatus]:
    """Get task status by ID."""
    return _tasks.get(task_id)


def list_tasks(limit: int = 20) -> list[dict]:
    """List recent tasks."""
    tasks = sorted(_tasks.values(), key=lambda t: t.created_at, reverse=True)[:limit]
    return [
        {
            "task_id": t.task_id,
            "task_type": t.task_type,
            "status": t.status,
            "progress": t.progress,
            "created_at": t.created_at,
            "completed_at": t.completed_at,
            "error": t.error,
            "result": t.result,
        }
        for t in tasks
    ]


# ── Background job functions (called via FastAPI BackgroundTasks) ─────────────

def bg_index_document(task_id: str, content: bytes, filename: str, title: str,
                      category: str, roles: list, version: str, user_id: str) -> None:
    """Background: index a document after upload."""
    try:
        update_task(task_id, "running", 10)
        from backend.app.core.dependencies import get_registry
        reg = get_registry()
        update_task(task_id, "running", 30)
        result = reg["ingestion"].ingest(content, filename, title, category, roles, "", version, user_id)
        update_task(task_id, "completed", 100, result={
            "document_id": result.document_id,
            "chunk_count": result.chunk_count,
            "status": result.status,
        })
    except Exception as e:
        update_task(task_id, "failed", error=str(e))
        logger.error("bg_index_failed", task_id=task_id, error=str(e))


def bg_generate_report(task_id: str, report_type: str, db_path: str, days: int) -> None:
    """Background: generate an audit/analytics report."""
    try:
        update_task(task_id, "running", 10)
        import sqlite3
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
