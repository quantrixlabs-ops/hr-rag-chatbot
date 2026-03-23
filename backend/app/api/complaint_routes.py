"""Anonymous complaint / whistleblower system — Phase D.

Complaints are fully anonymous — no user_id is stored.
Only HR Head (and Admin) can view complaints.
"""

from __future__ import annotations

import sqlite3
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from backend.app.core.config import get_settings
from backend.app.core.security import get_current_user, require_role, log_security_event
from backend.app.models.chat_models import User

router = APIRouter(prefix="/complaints", tags=["complaints"])

VALID_CATEGORIES = {
    "harassment", "discrimination", "fraud", "safety", "ethics",
    "retaliation", "misconduct", "policy_violation", "other",
}

_HR_HEAD_ROLES = {"hr_head", "hr_admin", "admin", "super_admin"}


# ── Request Models ───────────────────────────────────────────────────────────

class SubmitComplaintRequest(BaseModel):
    category: str = "other"
    description: str


class ReviewComplaintRequest(BaseModel):
    status: str  # "under_review", "investigating", "resolved", "dismissed"
    resolution: str = ""


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def submit_complaint(req: SubmitComplaintRequest, user: User = Depends(get_current_user)):
    """Submit an anonymous complaint. No user identity is stored.

    Any authenticated user can submit. The complaint is visible only to HR Head.
    """
    description = req.description.strip()
    if not description or len(description) < 10:
        raise HTTPException(400, "Description must be at least 10 characters")
    if len(description) > 5000:
        raise HTTPException(400, "Description must be 5000 characters or fewer")

    import html
    description = html.escape(description, quote=True)
    category = req.category.lower() if req.category.lower() in VALID_CATEGORIES else "other"

    complaint_id = str(uuid.uuid4())
    now = time.time()
    s = get_settings()

    with sqlite3.connect(s.db_path) as con:
        con.execute(
            "INSERT INTO complaints (complaint_id, category, description, status, submitted_at) "
            "VALUES (?,?,?,?,?)",
            (complaint_id, category, description, "submitted", now),
        )

    # Log event WITHOUT user_id to maintain anonymity
    log_security_event("anonymous_complaint_submitted", {
        "complaint_id": complaint_id, "category": category,
    })

    return {
        "complaint_id": complaint_id,
        "status": "submitted",
        "message": "Your complaint has been submitted anonymously. It will be reviewed by HR leadership.",
    }


@router.get("")
async def list_complaints(
    status: Optional[str] = None,
    category: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
):
    """List complaints — HR Head+ only."""
    if user.role not in _HR_HEAD_ROLES:
        raise HTTPException(403, "Only HR Head or Admin can view complaints")

    s = get_settings()
    offset = (page - 1) * limit

    conditions: list[str] = []
    params: list = []

    if status:
        conditions.append("c.status = ?")
        params.append(status)
    if category and category in VALID_CATEGORIES:
        conditions.append("c.category = ?")
        params.append(category)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with sqlite3.connect(s.db_path) as con:
        total = con.execute(f"SELECT COUNT(*) FROM complaints c {where}", params).fetchone()[0]
        rows = con.execute(
            f"SELECT c.complaint_id, c.category, c.description, c.status, "
            f"c.submitted_at, c.reviewed_by, c.reviewed_at, c.resolution, "
            f"COALESCE(u.full_name, u.username, '') "
            f"FROM complaints c LEFT JOIN users u ON c.reviewed_by = u.user_id "
            f"{where} ORDER BY c.submitted_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()

    return {
        "complaints": [
            {
                "complaint_id": r[0], "category": r[1],
                "description": r[2][:500], "status": r[3],
                "submitted_at": r[4], "reviewed_by": r[5] or "",
                "reviewed_at": r[6], "resolution": r[7],
                "reviewed_by_name": r[8],
            }
            for r in rows
        ],
        "total": total,
        "page": page,
    }


@router.get("/{complaint_id}")
async def get_complaint(complaint_id: str, user: User = Depends(get_current_user)):
    """Get full complaint details — HR Head+ only."""
    if user.role not in _HR_HEAD_ROLES:
        raise HTTPException(403, "Only HR Head or Admin can view complaints")

    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT c.complaint_id, c.category, c.description, c.status, "
            "c.submitted_at, c.reviewed_by, c.reviewed_at, c.resolution, "
            "COALESCE(u.full_name, u.username, '') "
            "FROM complaints c LEFT JOIN users u ON c.reviewed_by = u.user_id "
            "WHERE c.complaint_id = ?",
            (complaint_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Complaint not found")

    return {
        "complaint_id": row[0], "category": row[1],
        "description": row[2], "status": row[3],
        "submitted_at": row[4], "reviewed_by": row[5] or "",
        "reviewed_at": row[6], "resolution": row[7],
        "reviewed_by_name": row[8],
    }


@router.patch("/{complaint_id}")
async def review_complaint(
    complaint_id: str, req: ReviewComplaintRequest, user: User = Depends(get_current_user),
):
    """Update complaint status — HR Head+ only."""
    if user.role not in _HR_HEAD_ROLES:
        raise HTTPException(403, "Only HR Head or Admin can review complaints")

    valid_statuses = {"under_review", "investigating", "resolved", "dismissed"}
    if req.status not in valid_statuses:
        raise HTTPException(400, f"Status must be one of: {', '.join(sorted(valid_statuses))}")

    import html
    resolution = html.escape(req.resolution.strip()[:2000], quote=True) if req.resolution else ""

    s = get_settings()
    now = time.time()

    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT status FROM complaints WHERE complaint_id=?", (complaint_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Complaint not found")

        con.execute(
            "UPDATE complaints SET status=?, reviewed_by=?, reviewed_at=?, resolution=? "
            "WHERE complaint_id=?",
            (req.status, user.user_id, now, resolution, complaint_id),
        )

    log_security_event("complaint_reviewed", {
        "complaint_id": complaint_id, "new_status": req.status,
    }, user_id=user.user_id)

    return {"status": "updated", "complaint_id": complaint_id, "new_status": req.status}


@router.get("/stats/summary")
async def complaint_stats(user: User = Depends(get_current_user)):
    """Complaint statistics — HR Head+ only."""
    if user.role not in _HR_HEAD_ROLES:
        raise HTTPException(403, "Only HR Head or Admin can view complaint stats")

    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        status_rows = con.execute(
            "SELECT status, COUNT(*) FROM complaints GROUP BY status"
        ).fetchall()
        category_rows = con.execute(
            "SELECT category, COUNT(*) FROM complaints GROUP BY category"
        ).fetchall()
        total = con.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]

    return {
        "total": total,
        "by_status": {r[0]: r[1] for r in status_rows},
        "by_category": {r[0]: r[1] for r in category_rows},
    }
