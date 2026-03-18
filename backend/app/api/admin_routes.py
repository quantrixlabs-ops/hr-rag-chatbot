"""Admin endpoints — Section 20.3."""


import csv
import hashlib
import io
import json
import sqlite3
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.app.core.config import get_settings
from backend.app.core.security import get_current_user, require_role, log_security_event
from backend.app.models.chat_models import User

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/metrics")
async def metrics(user: User = Depends(get_current_user)):
    require_role(user, "hr_admin")
    s = get_settings()
    now = time.time()
    with sqlite3.connect(s.db_path) as con:
        qt = con.execute("SELECT COUNT(*) FROM query_logs WHERE timestamp>?", (now - 86400,)).fetchone()[0]
        qw = con.execute("SELECT COUNT(*) FROM query_logs WHERE timestamp>?", (now - 604800,)).fetchone()[0]
        avg = con.execute("SELECT AVG(latency_ms),AVG(faithfulness_score),AVG(hallucination_risk) FROM query_logs WHERE timestamp>?", (now - 604800,)).fetchone()
        active = con.execute("SELECT COUNT(*) FROM sessions WHERE last_active>?", (now - 86400,)).fetchone()[0]
        docs = con.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        chunks = con.execute("SELECT COALESCE(SUM(chunk_count),0) FROM documents").fetchone()[0]
        # PHASE 6: Real query success/failure metrics from logs
        grounded = con.execute("SELECT COUNT(*) FROM query_logs WHERE faithfulness_score>=0.6 AND timestamp>?", (now - 604800,)).fetchone()[0]
        failed = con.execute("SELECT COUNT(*) FROM query_logs WHERE faithfulness_score<0.6 AND timestamp>?", (now - 604800,)).fetchone()[0]
        negative_fb = con.execute("SELECT COUNT(*) FROM feedback WHERE rating='negative' AND timestamp>?", (now - 604800,)).fetchone()[0]
        # Top documents accessed — parse sources_used JSON from query_logs
        source_rows = con.execute(
            "SELECT sources_used FROM query_logs WHERE sources_used != '' AND timestamp>?",
            (now - 604800,)
        ).fetchall()
        # Query type distribution
        qtype_rows = con.execute(
            "SELECT query_type, COUNT(*) FROM query_logs WHERE timestamp>? GROUP BY query_type",
            (now - 604800,)
        ).fetchall()
    # Aggregate top documents
    import json as _json
    doc_counts: dict[str, int] = {}
    for (src_json,) in source_rows:
        try:
            for src in _json.loads(src_json):
                doc_counts[src] = doc_counts.get(src, 0) + 1
        except Exception:
            pass
    top_docs = sorted(doc_counts.items(), key=lambda x: -x[1])[:10]
    query_types = {r[0]: r[1] for r in qtype_rows if r[0]}
    success_rate = round(grounded / max(qw, 1), 3)
    return {
        "queries_today": qt, "queries_this_week": qw,
        "avg_latency_ms": round(avg[0] or 0, 1), "avg_faithfulness": round(avg[1] or 0, 3),
        "hallucination_rate": round(avg[2] or 0, 3), "active_sessions": active,
        "total_documents": docs, "total_chunks": chunks,
        "query_success_rate": success_rate, "failed_queries": failed,
        "negative_feedback_count": negative_fb,
        "top_documents": [{"source": s, "query_count": c} for s, c in top_docs],
        "query_type_distribution": query_types,
    }


@router.get("/failed-queries")
async def failed_queries(user: User = Depends(get_current_user)):
    require_role(user, "hr_admin")
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        rows = con.execute(
            "SELECT q.query, q.query_type, q.faithfulness_score, q.hallucination_risk, q.latency_ms, q.timestamp "
            "FROM query_logs q WHERE q.faithfulness_score < 0.7 "
            "OR q.id IN (SELECT ql.id FROM query_logs ql JOIN feedback f ON f.query = ql.query WHERE f.rating = 'negative') "
            "ORDER BY q.timestamp DESC LIMIT 50"
        ).fetchall()
    # PHASE 3: Return query_hash instead of raw query text to avoid PII exposure
    return {
        "failed_queries": [
            {
                "query_hash": hashlib.sha256(r[0].encode()).hexdigest()[:16],
                "query_type": r[1],
                "faithfulness_score": r[2],
                "hallucination_risk": r[3],
                "failure_reason": "low_faithfulness" if (r[2] or 0) < 0.7 else "negative_feedback",
                "latency_ms": r[4],
                "timestamp": r[5],
            }
            for r in rows
        ],
        "count": len(rows),
    }


@router.get("/security-events")
async def security_events(user: User = Depends(get_current_user)):
    """Audit trail of security events — admin only."""
    require_role(user, "hr_admin")
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        rows = con.execute(
            "SELECT event_type, user_id, ip_address, details, timestamp "
            "FROM security_events ORDER BY timestamp DESC LIMIT 100"
        ).fetchall()
    return {"events": [{"event_type": r[0], "user_id": r[1], "ip_address": r[2],
                         "details": json.loads(r[3]) if r[3] else {}, "timestamp": r[4]} for r in rows],
            "count": len(rows)}


@router.get("/security-events/export")
async def export_security_events(
    format: str = Query("csv", pattern="^(csv|json)$"),
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(get_current_user),
):
    """Export audit trail as CSV or JSON for compliance reporting."""
    require_role(user, "hr_admin")
    s = get_settings()
    since = time.time() - (days * 86400)
    with sqlite3.connect(s.db_path) as con:
        rows = con.execute(
            "SELECT event_type, user_id, ip_address, details, timestamp "
            "FROM security_events WHERE timestamp>? ORDER BY timestamp DESC",
            (since,),
        ).fetchall()

    if format == "json":
        events = [{"event_type": r[0], "user_id": r[1], "ip_address": r[2],
                    "details": json.loads(r[3]) if r[3] else {}, "timestamp": r[4]} for r in rows]
        content = json.dumps({"exported_at": time.time(), "days": days, "events": events}, indent=2)
        return StreamingResponse(
            io.BytesIO(content.encode()),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=audit_log_{days}d.json"},
        )
    else:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["event_type", "user_id", "ip_address", "details", "timestamp"])
        for r in rows:
            writer.writerow([r[0], r[1], r[2], r[3], r[4]])
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode()),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=audit_log_{days}d.csv"},
        )


@router.get("/users")
async def list_users(user: User = Depends(get_current_user)):
    """List all users with status info — admin only."""
    require_role(user, "hr_admin")
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        rows = con.execute(
            "SELECT user_id, username, role, department, full_name, email, created_at, "
            "COALESCE(status,'active'), COALESCE(suspended,0) "
            "FROM users WHERE username NOT LIKE 'deleted_%' ORDER BY created_at DESC"
        ).fetchall()
    return {
        "users": [
            {"user_id": r[0], "username": r[1], "role": r[2], "department": r[3],
             "full_name": r[4], "email": r[5], "created_at": r[6],
             "status": r[7], "suspended": bool(r[8])}
            for r in rows
        ],
        "count": len(rows),
    }


@router.get("/users/pending")
async def list_pending_users(user: User = Depends(get_current_user)):
    """List users awaiting approval — admin only."""
    require_role(user, "hr_admin")
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        rows = con.execute(
            "SELECT user_id, username, full_name, email, department, created_at "
            "FROM users WHERE status='pending_approval' ORDER BY created_at ASC"
        ).fetchall()
    return {
        "pending": [
            {"user_id": r[0], "username": r[1], "full_name": r[2],
             "email": r[3], "department": r[4], "created_at": r[5]}
            for r in rows
        ],
        "count": len(rows),
    }


class ApprovalAction(BaseModel):
    action: str  # "approve" or "reject"
    role: str = "employee"


@router.post("/users/{user_id}/approve")
async def approve_or_reject_user(user_id: str, req: ApprovalAction, admin: User = Depends(get_current_user)):
    """Approve or reject a pending user registration."""
    require_role(admin, "hr_admin")
    if req.action not in ("approve", "reject"):
        raise HTTPException(400, "Action must be 'approve' or 'reject'")
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute("SELECT username, status FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(404, "User not found")
        if row[1] != "pending_approval":
            raise HTTPException(409, f"User is already {row[1]}")
        if req.action == "approve":
            valid_roles = {"employee", "manager", "hr_admin"}
            role = req.role if req.role in valid_roles else "employee"
            con.execute("UPDATE users SET status='active', role=? WHERE user_id=?", (role, user_id))
        else:
            con.execute("UPDATE users SET status='rejected' WHERE user_id=?", (user_id,))
    log_security_event(
        f"user_{req.action}d",
        {"target_user": row[0], "target_id": user_id, "assigned_role": req.role if req.action == "approve" else ""},
        user_id=admin.user_id,
    )
    return {"status": f"user_{req.action}d", "user_id": user_id, "username": row[0]}


@router.post("/users/{user_id}/suspend")
async def suspend_user(user_id: str, admin: User = Depends(get_current_user)):
    """Suspend a user account — blocks login."""
    require_role(admin, "hr_admin")
    if user_id == admin.user_id:
        raise HTTPException(403, "Cannot suspend yourself")
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute("SELECT username, suspended FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(404, "User not found")
        new_state = 0 if row[1] else 1
        con.execute("UPDATE users SET suspended=? WHERE user_id=?", (new_state, user_id))
    action = "suspended" if new_state else "unsuspended"
    log_security_event(f"user_{action}", {"target_user": row[0], "target_id": user_id}, user_id=admin.user_id)
    return {"status": action, "user_id": user_id, "username": row[0]}


# ── Escalations (Phase 1) ────────────────────────────────────────────────────

@router.get("/escalations")
async def list_escalations(user: User = Depends(get_current_user)):
    """List all HR escalation tickets — admin only."""
    require_role(user, "hr_admin")
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        rows = con.execute(
            "SELECT e.id, e.user_id, u.username, e.query, e.answer, e.reason, e.status, e.created_at "
            "FROM escalations e LEFT JOIN users u ON e.user_id = u.user_id "
            "ORDER BY e.created_at DESC LIMIT 100"
        ).fetchall()
    return {
        "escalations": [
            {"id": r[0], "user_id": r[1], "username": r[2] or "unknown",
             "query": r[3], "answer": r[4], "reason": r[5],
             "status": r[6], "created_at": r[7]}
            for r in rows
        ],
        "count": len(rows),
    }


class ResolveEscalation(BaseModel):
    resolution: str


@router.post("/escalations/{escalation_id}/resolve")
async def resolve_escalation(escalation_id: int, req: ResolveEscalation, admin: User = Depends(get_current_user)):
    """Resolve an escalation ticket."""
    require_role(admin, "hr_admin")
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute("SELECT status FROM escalations WHERE id=?", (escalation_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Escalation not found")
        con.execute(
            "UPDATE escalations SET status='resolved', assigned_to=?, answer=? WHERE id=?",
            (admin.user_id, req.resolution, escalation_id)
        )
    return {"status": "resolved", "escalation_id": escalation_id}


# ── Phase 2: Background tasks + Cache stats ──────────────────────────────────

@router.get("/tasks")
async def list_background_tasks(user: User = Depends(get_current_user)):
    """List recent background tasks — admin only."""
    require_role(user, "hr_admin")
    from backend.app.core.background_tasks import list_tasks
    return {"tasks": list_tasks(limit=30)}


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str, user: User = Depends(get_current_user)):
    """Get status of a specific background task."""
    require_role(user, "hr_admin")
    from backend.app.core.background_tasks import get_task
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return {
        "task_id": task.task_id, "task_type": task.task_type,
        "status": task.status, "progress": task.progress,
        "created_at": task.created_at, "completed_at": task.completed_at,
        "result": task.result, "error": task.error,
    }


@router.get("/cache/stats")
async def cache_statistics(user: User = Depends(get_current_user)):
    """View semantic cache statistics — admin only."""
    require_role(user, "hr_admin")
    from backend.app.core.semantic_cache import get_cache_stats
    return get_cache_stats()


@router.post("/cache/clear")
async def clear_semantic_cache(user: User = Depends(get_current_user)):
    """Clear the semantic query cache — use after document reindex."""
    require_role(user, "hr_admin")
    from backend.app.core.semantic_cache import clear_cache
    clear_cache()
    log_security_event("cache_cleared", {}, user_id=user.user_id)
    return {"status": "cache_cleared"}


@router.get("/ai-responses")
async def list_ai_responses(
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
):
    """View AI response history with safety metadata — admin audit trail."""
    require_role(user, "hr_admin")
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        rows = con.execute(
            "SELECT query_hash, answer, confidence, faithfulness, verdict, "
            "sources_used, safety_issues, model, created_at "
            "FROM response_versions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return {
        "responses": [
            {
                "query_hash": r[0], "answer_preview": r[1][:200],
                "confidence": r[2], "faithfulness": r[3], "verdict": r[4],
                "sources": json.loads(r[5]) if r[5] else [],
                "safety_issues": json.loads(r[6]) if r[6] else [],
                "model": r[7], "created_at": r[8],
            }
            for r in rows
        ],
        "count": len(rows),
    }


# ── PHASE 1: Role assignment endpoint ────────────────────────────────────────
_VALID_ROLES = {"employee", "manager", "hr_admin"}


class RoleUpdateRequest(BaseModel):
    role: str


@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    req: RoleUpdateRequest,
    admin: User = Depends(get_current_user),
):
    """Assign a role to a user — hr_admin only. Cannot demote yourself."""
    require_role(admin, "hr_admin")
    if req.role not in _VALID_ROLES:
        raise HTTPException(400, f"Invalid role. Must be one of: {', '.join(sorted(_VALID_ROLES))}")
    if user_id == admin.user_id:
        raise HTTPException(403, "Cannot change your own role")
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute("SELECT username, role FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(404, "User not found")
        old_role = row[1]
        con.execute("UPDATE users SET role=? WHERE user_id=?", (req.role, user_id))
    log_security_event(
        "role_change",
        {"target_user_id": user_id, "username": row[0], "old_role": old_role, "new_role": req.role},
        user_id=admin.user_id,
    )
    return {"user_id": user_id, "username": row[0], "old_role": old_role, "new_role": req.role}


# ── SECTION 7: Vector store cleanup ──────────────────────────────────────────

@router.post("/cleanup-vector-store")
async def cleanup_vector_store(admin: User = Depends(get_current_user)):
    """Remove test/QA/duplicate documents from the vector store. Admin only."""
    require_role(admin, "hr_admin")
    from backend.app.core.dependencies import get_registry
    from backend.app.services.ingestion_service import _TEST_DOC_PATTERNS

    s = get_settings()
    reg = get_registry()
    vs = reg["vector_store"]
    bm25 = reg["bm25"]

    # Find contaminated documents in DB
    contaminated_ids: set[str] = set()
    with sqlite3.connect(s.db_path) as con:
        rows = con.execute("SELECT document_id, title, source_filename FROM documents").fetchall()

    for doc_id, title, filename in rows:
        if _TEST_DOC_PATTERNS.search(title) or _TEST_DOC_PATTERNS.search(filename):
            contaminated_ids.add(doc_id)

    if not contaminated_ids:
        return {"status": "clean", "removed_documents": 0, "removed_chunks": 0}

    # Rebuild FAISS excluding contaminated documents
    keep_indices = []
    keep_metadata = []
    removed_chunks = 0
    for i, meta in enumerate(vs.metadata):
        if meta.document_id not in contaminated_ids:
            keep_indices.append(i)
            keep_metadata.append(meta)
        else:
            removed_chunks += 1

    if removed_chunks > 0:
        import faiss
        if keep_indices:
            old_index = vs.index
            new_index = faiss.IndexFlatIP(vs.dimension)
            for idx in keep_indices:
                vec = old_index.reconstruct(idx).reshape(1, -1)
                new_index.add(vec)
            vs.index = new_index
            vs.metadata = keep_metadata
        else:
            vs.index = faiss.IndexFlatIP(vs.dimension)
            vs.metadata = []
        bm25.build_index(vs.metadata)
        vs.save()

    # Remove from DB
    with sqlite3.connect(s.db_path) as con:
        for doc_id in contaminated_ids:
            con.execute("DELETE FROM documents WHERE document_id=?", (doc_id,))

    import structlog
    structlog.get_logger().info(
        "vector_store_cleanup", admin=admin.user_id,
        removed_docs=len(contaminated_ids), removed_chunks=removed_chunks,
    )
    log_security_event("vector_store_cleanup", {
        "removed_documents": len(contaminated_ids),
        "removed_chunks": removed_chunks,
        "document_ids": list(contaminated_ids),
    }, user_id=admin.user_id)

    return {
        "status": "cleaned",
        "removed_documents": len(contaminated_ids),
        "removed_chunks": removed_chunks,
        "remaining_chunks": vs.total_chunks,
    }
