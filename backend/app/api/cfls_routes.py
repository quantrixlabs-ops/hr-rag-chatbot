"""Controlled Feedback Learning System (CFLS) — API Routes.

Human-in-the-loop learning: employees report issues, HR Head reviews
and creates approved corrections that the chatbot prioritizes.

Tables used:
- feedback_logs: detailed negative feedback with issue categories
- knowledge_corrections: HR-approved response overrides
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

import structlog

from backend.app.core.config import get_settings
from backend.app.core.security import get_current_user, require_role
from backend.app.models.chat_models import User

logger = structlog.get_logger()
router = APIRouter(prefix="/cfls", tags=["cfls"])


# ── Request / Response models ─────────────────────────────────────────────────

class DetailedFeedbackRequest(BaseModel):
    session_id: str
    query: str
    response: str
    feedback_type: str = "negative"
    issue_category: str = ""        # incorrect, incomplete, not_relevant, other
    custom_comment: str = ""


class CorrectionCreate(BaseModel):
    query_pattern: str
    corrected_response: str
    keywords: str = ""
    source_feedback_id: Optional[int] = None


class CorrectionUpdate(BaseModel):
    corrected_response: Optional[str] = None
    keywords: Optional[str] = None
    is_active: Optional[bool] = None


class FeedbackReview(BaseModel):
    status: str                     # reviewed, approved, rejected
    review_notes: str = ""


# ── Feedback endpoints ────────────────────────────────────────────────────────

@router.post("/feedback")
async def submit_detailed_feedback(
    req: DetailedFeedbackRequest,
    user: User = Depends(get_current_user),
):
    """Employee submits detailed feedback on a chatbot response."""
    s = get_settings()
    from backend.app.core.tenant import get_current_tenant
    tenant_id = get_current_tenant()

    with sqlite3.connect(s.db_path) as con:
        con.execute(
            "INSERT INTO feedback_logs "
            "(user_id, user_role, department, session_id, query, response, "
            "feedback_type, issue_category, custom_comment, status, created_at, tenant_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (user.user_id, user.role, user.department or "", req.session_id,
             req.query, req.response, req.feedback_type,
             req.issue_category, req.custom_comment, "pending",
             time.time(), tenant_id),
        )

    logger.info("cfls_feedback_submitted",
                user_id=user.user_id, feedback_type=req.feedback_type,
                issue_category=req.issue_category)

    # Notify HR Head about new negative feedback
    if req.feedback_type == "negative":
        try:
            from backend.app.api.notification_routes import notify_role
            notify_role("hr_head",
                        "New chatbot feedback requires review",
                        f"An employee reported an issue: {req.issue_category or 'general'}",
                        "action", "/admin?tab=feedback", s.db_path)
        except Exception:
            pass

    return {"status": "recorded", "message": "Thank you for your feedback. HR will review it."}


@router.get("/feedback")
async def list_feedback(
    user: User = Depends(get_current_user),
    status: str = "",
    issue_category: str = "",
    department: str = "",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List feedback entries. HR Head+ sees all; employees see only their own."""
    s = get_settings()
    from backend.app.core.tenant import get_current_tenant
    tenant_id = get_current_tenant()

    _HR_ROLES = {"hr_head", "hr_admin", "admin", "super_admin"}
    is_hr = user.role in _HR_ROLES

    conditions = ["tenant_id = ?"]
    params: list = [tenant_id]

    if not is_hr:
        conditions.append("user_id = ?")
        params.append(user.user_id)

    if status:
        conditions.append("status = ?")
        params.append(status)
    if issue_category:
        conditions.append("issue_category = ?")
        params.append(issue_category)
    if department and is_hr:
        conditions.append("department = ?")
        params.append(department)

    where = " AND ".join(conditions)
    params.extend([limit, offset])

    with sqlite3.connect(s.db_path) as con:
        rows = con.execute(
            f"SELECT id, user_id, user_role, department, session_id, query, response, "
            f"feedback_type, issue_category, custom_comment, status, "
            f"reviewed_by, reviewed_at, review_notes, created_at "
            f"FROM feedback_logs WHERE {where} "
            f"ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()

        total = con.execute(
            f"SELECT COUNT(*) FROM feedback_logs WHERE {where}",
            params[:-2],
        ).fetchone()[0]

    items = []
    for r in rows:
        item = {
            "id": r[0], "user_id": r[1] if is_hr else "(you)",
            "user_role": r[2], "department": r[3], "session_id": r[4],
            "query": r[5], "response": r[6][:500],
            "feedback_type": r[7], "issue_category": r[8],
            "custom_comment": r[9], "status": r[10],
            "reviewed_by": r[11], "reviewed_at": r[12],
            "review_notes": r[13], "created_at": r[14],
        }
        items.append(item)

    return {"feedback": items, "total": total}


@router.patch("/feedback/{feedback_id}")
async def review_feedback(
    feedback_id: int,
    req: FeedbackReview,
    user: User = Depends(get_current_user),
):
    """HR Head reviews a feedback entry."""
    require_role(user, "hr_head")
    s = get_settings()

    if req.status not in ("reviewed", "approved", "rejected"):
        raise HTTPException(400, "Status must be: reviewed, approved, or rejected")

    with sqlite3.connect(s.db_path) as con:
        existing = con.execute(
            "SELECT id FROM feedback_logs WHERE id = ?", (feedback_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(404, "Feedback not found")

        con.execute(
            "UPDATE feedback_logs SET status=?, reviewed_by=?, reviewed_at=?, review_notes=? "
            "WHERE id=?",
            (req.status, user.user_id, time.time(), req.review_notes, feedback_id),
        )

    logger.info("cfls_feedback_reviewed", feedback_id=feedback_id,
                status=req.status, reviewer=user.user_id)
    return {"status": "updated", "feedback_id": feedback_id}


# ── Knowledge Corrections endpoints ──────────────────────────────────────────

@router.post("/corrections")
async def create_correction(
    req: CorrectionCreate,
    user: User = Depends(get_current_user),
):
    """HR Head creates an approved knowledge correction."""
    require_role(user, "hr_head")
    s = get_settings()
    from backend.app.core.tenant import get_current_tenant
    tenant_id = get_current_tenant()

    if not req.query_pattern.strip() or not req.corrected_response.strip():
        raise HTTPException(400, "Both query_pattern and corrected_response are required")

    now = time.time()
    with sqlite3.connect(s.db_path) as con:
        con.execute(
            "INSERT INTO knowledge_corrections "
            "(query_pattern, corrected_response, keywords, source_feedback_id, "
            "approved_by, is_active, created_at, updated_at, tenant_id) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (req.query_pattern.strip(), req.corrected_response.strip(),
             req.keywords.strip(), req.source_feedback_id,
             user.user_id, 1, now, now, tenant_id),
        )

        # If linked to a feedback entry, mark it approved
        if req.source_feedback_id:
            con.execute(
                "UPDATE feedback_logs SET status='approved', reviewed_by=?, reviewed_at=? "
                "WHERE id=?",
                (user.user_id, now, req.source_feedback_id),
            )

    logger.info("cfls_correction_created", query_pattern=req.query_pattern[:80],
                approved_by=user.user_id)
    return {"status": "created", "message": "Correction is now active in the chatbot."}


@router.get("/corrections")
async def list_corrections(
    user: User = Depends(get_current_user),
    active_only: bool = True,
    limit: int = Query(50, ge=1, le=200),
):
    """List knowledge corrections. HR Head+ only."""
    require_role(user, "hr_head")
    s = get_settings()
    from backend.app.core.tenant import get_current_tenant
    tenant_id = get_current_tenant()

    condition = "tenant_id = ?"
    params: list = [tenant_id]
    if active_only:
        condition += " AND is_active = 1"

    with sqlite3.connect(s.db_path) as con:
        rows = con.execute(
            f"SELECT id, query_pattern, corrected_response, keywords, "
            f"source_feedback_id, approved_by, is_active, use_count, "
            f"created_at, updated_at "
            f"FROM knowledge_corrections WHERE {condition} "
            f"ORDER BY created_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()

    items = [{
        "id": r[0], "query_pattern": r[1], "corrected_response": r[2],
        "keywords": r[3], "source_feedback_id": r[4],
        "approved_by": r[5], "is_active": bool(r[6]),
        "use_count": r[7], "created_at": r[8], "updated_at": r[9],
    } for r in rows]

    return {"corrections": items, "total": len(items)}


@router.put("/corrections/{correction_id}")
async def update_correction(
    correction_id: int,
    req: CorrectionUpdate,
    user: User = Depends(get_current_user),
):
    """Update or deactivate a correction. Saves a version snapshot before updating."""
    require_role(user, "hr_head")
    s = get_settings()

    with sqlite3.connect(s.db_path) as con:
        existing = con.execute(
            "SELECT id FROM knowledge_corrections WHERE id = ?", (correction_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(404, "Correction not found")

    # CLS: Save version before modifying
    from backend.app.services.cls_service import save_version
    changes = []
    if req.corrected_response is not None:
        changes.append("response updated")
    if req.keywords is not None:
        changes.append("keywords updated")
    if req.is_active is not None:
        changes.append("active" if req.is_active else "deactivated")
    save_version(s.db_path, correction_id, user.user_id, "; ".join(changes) or "updated")

    with sqlite3.connect(s.db_path) as con:
        updates = ["updated_at = ?"]
        params: list = [time.time()]

        if req.corrected_response is not None:
            updates.append("corrected_response = ?")
            params.append(req.corrected_response.strip())
        if req.keywords is not None:
            updates.append("keywords = ?")
            params.append(req.keywords.strip())
        if req.is_active is not None:
            updates.append("is_active = ?")
            params.append(1 if req.is_active else 0)

        params.append(correction_id)
        con.execute(
            f"UPDATE knowledge_corrections SET {', '.join(updates)} WHERE id = ?",
            params,
        )

    return {"status": "updated", "correction_id": correction_id}


@router.delete("/corrections/{correction_id}")
async def delete_correction(
    correction_id: int,
    user: User = Depends(get_current_user),
):
    """Delete a correction (hard delete)."""
    require_role(user, "hr_head")
    s = get_settings()

    with sqlite3.connect(s.db_path) as con:
        existing = con.execute(
            "SELECT id FROM knowledge_corrections WHERE id = ?", (correction_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(404, "Correction not found")
        con.execute("DELETE FROM knowledge_corrections WHERE id = ?", (correction_id,))

    return {"status": "deleted", "correction_id": correction_id}


# ── Analytics endpoints ───────────────────────────────────────────────────────

@router.get("/analytics")
async def feedback_analytics(user: User = Depends(get_current_user)):
    """CFLS dashboard metrics. HR Head+ only."""
    require_role(user, "hr_head")
    s = get_settings()
    from backend.app.core.tenant import get_current_tenant
    tenant_id = get_current_tenant()
    now = time.time()
    week_ago = now - 604800
    month_ago = now - 2592000

    with sqlite3.connect(s.db_path) as con:
        # Overall feedback counts
        total_feedback = con.execute(
            "SELECT COUNT(*) FROM feedback_logs WHERE tenant_id=?", (tenant_id,)
        ).fetchone()[0]
        negative_count = con.execute(
            "SELECT COUNT(*) FROM feedback_logs WHERE feedback_type='negative' AND tenant_id=?",
            (tenant_id,)
        ).fetchone()[0]
        pending_count = con.execute(
            "SELECT COUNT(*) FROM feedback_logs WHERE status='pending' AND tenant_id=?",
            (tenant_id,)
        ).fetchone()[0]

        # This week's feedback
        week_negative = con.execute(
            "SELECT COUNT(*) FROM feedback_logs WHERE feedback_type='negative' AND created_at>? AND tenant_id=?",
            (week_ago, tenant_id)
        ).fetchone()[0]
        week_positive = con.execute(
            "SELECT COUNT(*) FROM feedback_logs WHERE feedback_type='positive' AND created_at>? AND tenant_id=?",
            (week_ago, tenant_id)
        ).fetchone()[0]

        # Issue category breakdown
        category_rows = con.execute(
            "SELECT issue_category, COUNT(*) FROM feedback_logs "
            "WHERE feedback_type='negative' AND tenant_id=? "
            "GROUP BY issue_category ORDER BY COUNT(*) DESC",
            (tenant_id,)
        ).fetchall()

        # Top failed queries (most repeated negative feedback)
        top_failed = con.execute(
            "SELECT query, COUNT(*) as cnt FROM feedback_logs "
            "WHERE feedback_type='negative' AND tenant_id=? "
            "GROUP BY query ORDER BY cnt DESC LIMIT 10",
            (tenant_id,)
        ).fetchall()

        # Department breakdown
        dept_rows = con.execute(
            "SELECT department, COUNT(*) FROM feedback_logs "
            "WHERE feedback_type='negative' AND department != '' AND tenant_id=? "
            "GROUP BY department ORDER BY COUNT(*) DESC LIMIT 10",
            (tenant_id,)
        ).fetchall()

        # Corrections stats
        total_corrections = con.execute(
            "SELECT COUNT(*) FROM knowledge_corrections WHERE is_active=1 AND tenant_id=?",
            (tenant_id,)
        ).fetchone()[0]
        total_correction_uses = con.execute(
            "SELECT COALESCE(SUM(use_count), 0) FROM knowledge_corrections WHERE tenant_id=?",
            (tenant_id,)
        ).fetchone()[0]

        # Improvement over time: negative feedback per week (last 4 weeks)
        weekly_trend = []
        for i in range(4):
            end = now - (i * 604800)
            start = end - 604800
            cnt = con.execute(
                "SELECT COUNT(*) FROM feedback_logs "
                "WHERE feedback_type='negative' AND created_at BETWEEN ? AND ? AND tenant_id=?",
                (start, end, tenant_id)
            ).fetchone()[0]
            weekly_trend.append({"week_offset": i, "negative_count": cnt})

    neg_rate = round(negative_count / total_feedback * 100, 1) if total_feedback > 0 else 0
    week_total = week_negative + week_positive
    week_neg_rate = round(week_negative / week_total * 100, 1) if week_total > 0 else 0

    return {
        "overview": {
            "total_feedback": total_feedback,
            "negative_count": negative_count,
            "negative_rate_percent": neg_rate,
            "pending_review": pending_count,
            "active_corrections": total_corrections,
            "correction_uses": total_correction_uses,
        },
        "this_week": {
            "positive": week_positive,
            "negative": week_negative,
            "negative_rate_percent": week_neg_rate,
        },
        "issue_categories": [
            {"category": r[0] or "unspecified", "count": r[1]} for r in category_rows
        ],
        "top_failed_queries": [
            {"query": r[0][:100], "count": r[1]} for r in top_failed
        ],
        "department_breakdown": [
            {"department": r[0], "count": r[1]} for r in dept_rows
        ],
        "weekly_trend": weekly_trend,
    }


# ── CLS: Version Control & Rollback ──────────────────────────────────────────

@router.get("/corrections/{correction_id}/versions")
async def list_correction_versions(
    correction_id: int,
    user: User = Depends(get_current_user),
):
    """Get version history of a correction for audit trail and rollback."""
    require_role(user, "hr_head")
    from backend.app.services.cls_service import get_versions
    s = get_settings()
    versions = get_versions(s.db_path, correction_id)
    return {"versions": versions, "correction_id": correction_id}


class RollbackRequest(BaseModel):
    version_number: int


@router.post("/corrections/{correction_id}/rollback")
async def rollback_correction_endpoint(
    correction_id: int,
    req: RollbackRequest,
    user: User = Depends(get_current_user),
):
    """Rollback a correction to a previous version."""
    require_role(user, "hr_head")
    from backend.app.services.cls_service import rollback_correction
    s = get_settings()

    success = rollback_correction(s.db_path, correction_id, req.version_number, user.user_id)
    if not success:
        raise HTTPException(404, f"Version {req.version_number} not found for correction {correction_id}")

    logger.info("correction_rolled_back", correction_id=correction_id,
                version=req.version_number, by=user.user_id)
    return {"status": "rolled_back", "correction_id": correction_id, "to_version": req.version_number}


# ── CLS: Learning Queue ──────────────────────────────────────────────────────

@router.get("/learning-queue")
async def get_learning_queue_endpoint(
    user: User = Depends(get_current_user),
    status: str = "",
):
    """Get the learning queue — auto-detected failure patterns needing correction."""
    require_role(user, "hr_head")
    from backend.app.services.cls_service import get_learning_queue
    s = get_settings()
    items = get_learning_queue(s.db_path, status)
    return {"queue": items, "total": len(items)}


@router.post("/learning-queue/refresh")
async def refresh_learning_queue_endpoint(
    user: User = Depends(get_current_user),
):
    """Scan feedback logs and populate learning queue with new failure patterns."""
    require_role(user, "hr_head")
    from backend.app.services.cls_service import refresh_learning_queue
    s = get_settings()
    new_entries = refresh_learning_queue(s.db_path)
    return {"status": "refreshed", "new_entries": new_entries}


class ConvertQueueRequest(BaseModel):
    corrected_response: str
    keywords: str = ""


@router.post("/learning-queue/{item_id}/convert")
async def convert_queue_to_correction(
    item_id: int,
    req: ConvertQueueRequest,
    user: User = Depends(get_current_user),
):
    """Convert a learning queue item into a knowledge correction."""
    require_role(user, "hr_head")
    from backend.app.services.cls_service import update_queue_item
    s = get_settings()
    from backend.app.core.tenant import get_current_tenant
    tenant_id = get_current_tenant()

    if not req.corrected_response.strip():
        raise HTTPException(400, "Corrected response is required")

    # Get the queue item
    with sqlite3.connect(s.db_path) as con:
        item = con.execute(
            "SELECT query_pattern, sample_query FROM learning_queue WHERE id=?", (item_id,)
        ).fetchone()
    if not item:
        raise HTTPException(404, "Queue item not found")

    # Create correction
    now = time.time()
    with sqlite3.connect(s.db_path) as con:
        con.execute(
            "INSERT INTO knowledge_corrections "
            "(query_pattern, corrected_response, keywords, approved_by, is_active, created_at, updated_at, tenant_id) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (item[0], req.corrected_response.strip(), req.keywords.strip(),
             user.user_id, 1, now, now, tenant_id),
        )

    # Mark queue item as converted
    update_queue_item(s.db_path, item_id, "converted", user.user_id)

    logger.info("learning_queue_converted", item_id=item_id, pattern=item[0][:80])
    return {"status": "converted", "message": "Queue item converted to active correction."}


@router.post("/learning-queue/{item_id}/dismiss")
async def dismiss_queue_item(
    item_id: int,
    user: User = Depends(get_current_user),
):
    """Dismiss a learning queue item (not a real pattern)."""
    require_role(user, "hr_head")
    from backend.app.services.cls_service import update_queue_item
    s = get_settings()
    update_queue_item(s.db_path, item_id, "dismissed", user.user_id)
    return {"status": "dismissed"}


# ── CLS: Effectiveness Metrics ────────────────────────────────────────────────

@router.get("/effectiveness")
async def get_effectiveness_metrics_endpoint(
    user: User = Depends(get_current_user),
):
    """Get learning system effectiveness — are corrections actually improving responses?"""
    require_role(user, "hr_head")
    from backend.app.services.cls_service import get_effectiveness_metrics
    s = get_settings()
    return get_effectiveness_metrics(s.db_path)
