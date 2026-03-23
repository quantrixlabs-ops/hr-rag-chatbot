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
    from backend.app.core.tenant import get_current_tenant
    tenant_id = get_current_tenant()
    with sqlite3.connect(s.db_path) as con:
        qt = con.execute("SELECT COUNT(*) FROM query_logs WHERE timestamp>? AND tenant_id=?", (now - 86400, tenant_id)).fetchone()[0]
        qw = con.execute("SELECT COUNT(*) FROM query_logs WHERE timestamp>? AND tenant_id=?", (now - 604800, tenant_id)).fetchone()[0]
        avg = con.execute("SELECT AVG(latency_ms),AVG(faithfulness_score),AVG(hallucination_risk) FROM query_logs WHERE timestamp>? AND tenant_id=?", (now - 604800, tenant_id)).fetchone()
        active = con.execute("SELECT COUNT(*) FROM sessions WHERE last_active>? AND tenant_id=?", (now - 86400, tenant_id)).fetchone()[0]
        docs = con.execute("SELECT COUNT(*) FROM documents WHERE tenant_id=?", (tenant_id,)).fetchone()[0]
        chunks = con.execute("SELECT COALESCE(SUM(chunk_count),0) FROM documents WHERE tenant_id=?", (tenant_id,)).fetchone()[0]
        # PHASE 6: Real query success/failure metrics from logs
        grounded = con.execute("SELECT COUNT(*) FROM query_logs WHERE faithfulness_score>=0.6 AND timestamp>? AND tenant_id=?", (now - 604800, tenant_id)).fetchone()[0]
        failed = con.execute("SELECT COUNT(*) FROM query_logs WHERE faithfulness_score<0.6 AND timestamp>? AND tenant_id=?", (now - 604800, tenant_id)).fetchone()[0]
        negative_fb = con.execute("SELECT COUNT(*) FROM feedback WHERE rating='negative' AND timestamp>? AND tenant_id=?", (now - 604800, tenant_id)).fetchone()[0]
        # Top documents accessed — parse sources_used JSON from query_logs
        source_rows = con.execute(
            "SELECT sources_used FROM query_logs WHERE sources_used != '' AND timestamp>? AND tenant_id=?",
            (now - 604800, tenant_id)
        ).fetchall()
        # Query type distribution
        qtype_rows = con.execute(
            "SELECT query_type, COUNT(*) FROM query_logs WHERE timestamp>? AND tenant_id=? GROUP BY query_type",
            (now - 604800, tenant_id)
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
    """List all users with status info — hr_head+ only."""
    require_role(user, "hr_admin")
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        rows = con.execute(
            "SELECT user_id, username, role, department, full_name, email, created_at, "
            "COALESCE(status,'active'), COALESCE(suspended,0), "
            "COALESCE(employee_id,''), COALESCE(branch_id,''), COALESCE(team,'') "
            "FROM users WHERE username NOT LIKE 'deleted_%' ORDER BY created_at DESC"
        ).fetchall()
    return {
        "users": [
            {"user_id": r[0], "username": r[1], "role": r[2], "department": r[3],
             "full_name": r[4], "email": r[5], "created_at": r[6],
             "status": r[7], "suspended": bool(r[8]),
             "employee_id": r[9], "branch_id": r[10], "team": r[11]}
            for r in rows
        ],
        "count": len(rows),
    }


@router.get("/users/pending")
async def list_pending_users(user: User = Depends(get_current_user)):
    """List users awaiting approval — hr_head+ only.

    Phase A: Shows requested_role so approver knows what role was requested.
    HR Head sees employee/hr_team requests. Admin sees hr_head requests too.
    """
    require_role(user, "hr_admin")
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        rows = con.execute(
            "SELECT user_id, username, full_name, email, department, created_at, "
            "COALESCE(requested_role, 'employee') "
            "FROM users WHERE status='pending_approval' ORDER BY created_at ASC"
        ).fetchall()

    # Phase A: Filter based on approval chain — show only users this approver can approve
    from backend.app.core.permissions import APPROVAL_CHAIN
    approver_role = user.role
    visible = []
    for r in rows:
        requested = r[6]
        allowed_approvers = APPROVAL_CHAIN.get(requested, set())
        if approver_role in allowed_approvers:
            visible.append(r)

    return {
        "pending": [
            {"user_id": r[0], "username": r[1], "full_name": r[2],
             "email": r[3], "department": r[4], "created_at": r[5],
             "requested_role": r[6]}
            for r in visible
        ],
        "count": len(visible),
    }


class ApprovalAction(BaseModel):
    action: str  # "approve" or "reject"
    role: str = "employee"


@router.post("/users/{user_id}/approve")
async def approve_or_reject_user(user_id: str, req: ApprovalAction, admin: User = Depends(get_current_user)):
    """Approve or reject a pending user registration.

    Phase A: Enforces approval chain —
    - Employee/HR Team registrations → HR Head (or Admin) approves
    - HR Head registrations → Admin only approves
    """
    require_role(admin, "hr_admin")
    if req.action not in ("approve", "reject"):
        raise HTTPException(400, "Action must be 'approve' or 'reject'")
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT username, status, COALESCE(requested_role, 'employee') FROM users WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "User not found")
        if row[1] != "pending_approval":
            raise HTTPException(409, f"User is already {row[1]}")

        # Phase A: Validate approval chain
        from backend.app.core.permissions import APPROVAL_CHAIN, VALID_ROLES
        requested_role = row[2]
        allowed_approvers = APPROVAL_CHAIN.get(requested_role, set())
        if admin.role not in allowed_approvers:
            raise HTTPException(
                403,
                f"Your role ({admin.role}) cannot approve {requested_role} registrations. "
                f"Required: {', '.join(sorted(allowed_approvers))}",
            )

        if req.action == "approve":
            # Use requested_role by default, allow override if approver specifies a valid role
            role = req.role if req.role in VALID_ROLES else requested_role
            # Prevent approver from assigning a role higher than they can approve
            if role not in APPROVAL_CHAIN or admin.role not in APPROVAL_CHAIN.get(role, set()):
                role = requested_role  # Fall back to requested role
            con.execute("UPDATE users SET status='active', role=? WHERE user_id=?", (role, user_id))
        else:
            con.execute("UPDATE users SET status='rejected' WHERE user_id=?", (user_id,))
    log_security_event(
        f"user_{req.action}d",
        {
            "target_user": row[0], "target_id": user_id,
            "requested_role": requested_role,
            "assigned_role": req.role if req.action == "approve" else "",
            "approved_by_role": admin.role,
        },
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


@router.post("/tasks/{task_id}/cancel")
async def cancel_background_task(task_id: str, user: User = Depends(get_current_user)):
    """Cancel a running or pending background task."""
    require_role(user, "hr_admin")
    from backend.app.core.background_tasks import cancel_task
    cancelled = cancel_task(task_id)
    if not cancelled:
        raise HTTPException(409, "Task cannot be cancelled (already completed, failed, or not found)")
    log_security_event("task_cancelled", {"task_id": task_id}, user_id=user.user_id)
    return {"status": "cancelled", "task_id": task_id}


@router.post("/tasks/cleanup-stale")
async def cleanup_stale_tasks_endpoint(user: User = Depends(get_current_user)):
    """Mark stale running tasks (>30 min) as failed."""
    require_role(user, "hr_admin")
    from backend.app.core.background_tasks import cleanup_stale_tasks
    count = cleanup_stale_tasks()
    return {"status": "cleaned", "stale_tasks_failed": count}


@router.get("/cache/stats")
async def cache_statistics(user: User = Depends(get_current_user)):
    """View semantic cache statistics — admin only."""
    require_role(user, "hr_admin")
    from backend.app.core.semantic_cache import get_detailed_stats
    return get_detailed_stats()


@router.get("/tenant/usage")
async def tenant_usage(user: User = Depends(get_current_user)):
    """View current tenant usage stats and quota utilization — admin only."""
    require_role(user, "hr_admin")
    from backend.app.core.tenant import TenantQuotaEnforcer
    return TenantQuotaEnforcer.get_usage_stats()


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


# ── PHASE 2: Direct user creation (admin-initiated, no approval flow) ────────

class CreateUserRequest(BaseModel):
    username: str
    email: str
    password: str
    role: str = "employee"
    department: str = ""
    full_name: str = ""


@router.post("/users", status_code=201)
async def create_user(
    req: CreateUserRequest,
    admin: User = Depends(get_current_user),
):
    """Create a user directly without the self-registration approval flow.

    Only hr_admin and super_admin can use this. User is immediately active.
    For bulk onboarding without requiring employees to self-register.
    """
    require_role(admin, "hr_admin")
    from backend.app.core.permissions import require_permission, VALID_ROLES
    if not require_permission(admin.role, "users.create"):
        raise HTTPException(403, "Insufficient permissions to create users")
    if req.role not in VALID_ROLES:
        raise HTTPException(400, f"Invalid role '{req.role}'. Valid roles: {', '.join(sorted(VALID_ROLES))}")

    s = get_settings()

    # Validate username
    import re, html as html_mod
    username = html_mod.escape(req.username.strip())
    if not re.match(r'^[a-zA-Z0-9._-]{3,50}$', username):
        raise HTTPException(400, "Username must be 3-50 chars: letters, numbers, dots, hyphens, underscores only")

    # Validate password strength
    pwd = req.password
    if len(pwd) < 8 or not any(c.isdigit() for c in pwd) or not any(c.isalpha() for c in pwd):
        raise HTTPException(400, "Password must be ≥8 chars with at least one letter and one number")

    from passlib.context import CryptContext
    _pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed = _pwd_ctx.hash(pwd)

    import uuid as _uuid, time as _time
    user_id = str(_uuid.uuid4())
    now = _time.time()

    with sqlite3.connect(s.db_path) as con:
        # Check for duplicate username/email
        if con.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise HTTPException(409, f"Username '{username}' already exists")
        if req.email and con.execute("SELECT 1 FROM users WHERE email=?", (req.email,)).fetchone():
            raise HTTPException(409, f"Email '{req.email}' already registered")

        from backend.app.core.tenant import get_current_tenant
        con.execute(
            "INSERT INTO users (user_id,username,hashed_password,role,department,full_name,"
            "email,created_at,status,email_verified,tenant_id) VALUES (?,?,?,?,?,?,?,?,'active',1,?)",
            (user_id, username, hashed, req.role, req.department, req.full_name, req.email, now, get_current_tenant()),
        )

    # Write audit log to PostgreSQL
    from backend.app.database.postgres import write_audit_log
    write_audit_log(
        action="user.created",
        target_type="user",
        target_id=user_id,
        extra={"username": username, "role": req.role, "created_by": admin.user_id},
    )
    log_security_event("user_created_by_admin", {"username": username, "role": req.role}, user_id=admin.user_id)

    logger.info("admin_user_created", user_id=user_id, username=username, role=req.role, by=admin.user_id)
    return {"user_id": user_id, "username": username, "role": req.role, "status": "active"}


# ── PHASE 2: Audit log viewer ─────────────────────────────────────────────────

@router.get("/audit-logs")
async def get_audit_logs(
    limit: int = 50,
    offset: int = 0,
    admin: User = Depends(get_current_user),
):
    """View the PostgreSQL audit trail. hr_admin only."""
    require_role(admin, "hr_admin")
    from backend.app.core.permissions import require_permission
    if not require_permission(admin.role, "admin.view_audit_logs"):
        raise HTTPException(403, "Insufficient permissions")

    s = get_settings()
    if not s.database_url.startswith("postgresql"):
        return {"logs": [], "total": 0, "note": "Audit logs require PostgreSQL"}

    try:
        from backend.app.database.postgres import get_connection
        from sqlalchemy import text
        with get_connection() as conn:
            total = conn.execute(text("SELECT COUNT(*) FROM audit_logs")).fetchone()[0]
            rows = conn.execute(
                text(
                    "SELECT id, actor_id, action, target_type, target_id, ip_address, metadata, created_at "
                    "FROM audit_logs ORDER BY created_at DESC LIMIT :lim OFFSET :off"
                ),
                {"lim": min(limit, 200), "off": offset},
            ).fetchall()

        logs = [
            {
                "id": str(r[0]),
                "actor_id": str(r[1]) if r[1] else None,
                "action": r[2],
                "target_type": r[3],
                "target_id": r[4],
                "ip_address": r[5],
                "metadata": r[6],
                "created_at": str(r[7]),
            }
            for r in rows
        ]
        return {"logs": logs, "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        logger.error("audit_log_fetch_failed", error=str(e))
        raise HTTPException(500, "Failed to fetch audit logs")


# ── PHASE 1: Role assignment endpoint ────────────────────────────────────────
# Phase A: Extended with hr_team, hr_head, admin aliases
_VALID_ROLES = {"employee", "manager", "hr_team", "hr_head", "hr_admin", "admin", "super_admin"}


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
    from backend.app.core.permissions import require_permission
    if not require_permission(admin.role, "users.change_role"):
        raise HTTPException(403, "Insufficient permissions to change roles")
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


# ── Phase 4: GDPR Compliance & Session Maintenance ───────────────────────────

@router.post("/gdpr/cleanup")
async def gdpr_data_cleanup(
    retention_days: int = Query(365, ge=30, le=3650),
    user: User = Depends(get_current_user),
):
    """GDPR data retention cleanup — deletes user data older than retention_days.

    Cleans: sessions, turns, feedback, query_logs, old security events (2yr).
    Admin only. Logs the action for audit trail.
    """
    require_role(user, "hr_admin")
    from backend.app.core.dependencies import get_registry
    reg = get_registry()
    ss = reg["session_store"]
    result = ss.gdpr_cleanup(retention_days=retention_days)
    log_security_event("gdpr_cleanup", {
        "retention_days": retention_days,
        "deleted": result,
    }, user_id=user.user_id)
    return {"status": "completed", "retention_days": retention_days, "deleted": result}


@router.post("/sessions/cleanup-stale")
async def cleanup_stale_sessions(
    max_age_days: int = Query(90, ge=7, le=365),
    user: User = Depends(get_current_user),
):
    """Remove stale sessions that have been inactive for max_age_days.

    Admin only. Useful for periodic maintenance.
    """
    require_role(user, "hr_admin")
    from backend.app.core.dependencies import get_registry
    reg = get_registry()
    ss = reg["session_store"]
    count = ss.cleanup_stale_sessions(max_age_days=max_age_days)
    log_security_event("stale_sessions_cleanup", {
        "max_age_days": max_age_days,
        "sessions_deleted": count,
    }, user_id=user.user_id)
    return {"status": "completed", "sessions_deleted": count, "max_age_days": max_age_days}
