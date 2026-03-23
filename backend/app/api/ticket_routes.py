"""Ticket system endpoints — Phase B.

Full lifecycle: raised → assigned → in_progress → resolved → closed → rejected.

Access rules:
- Employee: create tickets, view own tickets
- HR Team: view all tickets, assign, update status, resolve
- HR Head: all of the above + close/reject
- Admin: full access
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

router = APIRouter(prefix="/tickets", tags=["tickets"])

# ── Constants ────────────────────────────────────────────────────────────────

VALID_STATUSES = {"raised", "assigned", "in_progress", "resolved", "closed", "rejected"}
VALID_PRIORITIES = {"low", "medium", "high", "urgent"}
VALID_CATEGORIES = {
    "general", "leave", "payroll", "benefits", "onboarding", "offboarding",
    "policy", "complaint", "technical", "other",
}

# Status transitions: current_status → set of allowed next statuses
STATUS_TRANSITIONS: dict[str, set[str]] = {
    "raised": {"assigned", "in_progress", "rejected"},
    "assigned": {"in_progress", "resolved", "rejected"},
    "in_progress": {"resolved", "rejected"},
    "resolved": {"closed", "in_progress"},  # Can reopen or close
    "closed": set(),  # Terminal
    "rejected": set(),  # Terminal
}

AUTO_CLOSE_WORKING_DAYS = 2  # Auto-accept after 2 working days of no employee action


def _add_working_days(start: float, days: int) -> float:
    """Add N working days (Mon-Fri) to a Unix timestamp."""
    from datetime import datetime, timedelta
    dt = datetime.fromtimestamp(start)
    added = 0
    while added < days:
        dt += timedelta(days=1)
        if dt.weekday() < 5:  # Mon=0 … Fri=4
            added += 1
    return dt.timestamp()


def _auto_close_resolved(db_path: str) -> None:
    """Auto-close resolved tickets past their auto_close_at deadline."""
    now = time.time()
    with sqlite3.connect(db_path) as con:
        expired = con.execute(
            "SELECT ticket_id, raised_by, title FROM tickets "
            "WHERE status='resolved' AND auto_close_at IS NOT NULL AND auto_close_at <= ?",
            (now,),
        ).fetchall()
        for tid, raiser, title in expired:
            con.execute(
                "UPDATE tickets SET status='closed', feedback='Auto-accepted (no response within 2 working days)', "
                "updated_at=? WHERE ticket_id=?",
                (now, tid),
            )
            con.execute(
                "INSERT INTO ticket_history (ticket_id, action, performed_by, old_value, new_value, comment, timestamp) "
                "VALUES (?,?,?,?,?,?,?)",
                (tid, "status_change", "system", "resolved", "closed",
                 "Auto-accepted: no employee response within 2 working days", now),
            )
            # Notify employee
            try:
                from backend.app.api.notification_routes import create_notification
                create_notification(
                    raiser, f"Ticket auto-closed: {title[:80]}",
                    "No response within 2 working days — ticket accepted automatically.",
                    "info", f"/tickets/{tid}", db_path,
                )
            except Exception:
                pass


# Minimum role level to perform certain actions
# hr_team can assign/resolve; hr_head can close/reject
_HR_ROLES = {"hr_team", "hr_head", "hr_admin", "admin", "super_admin"}
_HR_HEAD_ROLES = {"hr_head", "hr_admin", "admin", "super_admin"}


# ── Request/Response Models ──────────────────────────────────────────────────

class CreateTicketRequest(BaseModel):
    title: str
    description: str = ""
    category: str = "general"
    priority: str = "medium"


class UpdateTicketRequest(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_to: Optional[str] = None
    comment: str = ""


class TicketCommentRequest(BaseModel):
    comment: str


class TicketRespondRequest(BaseModel):
    action: str  # "accept" or "reject"
    feedback: str = ""
    rating: int = 0  # 1-5 stars


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_ticket(req: CreateTicketRequest, user: User = Depends(get_current_user)):
    """Create a new ticket. Any authenticated user can create tickets."""
    title = req.title.strip()
    if not title or len(title) < 3:
        raise HTTPException(400, "Title must be at least 3 characters")
    if len(title) > 200:
        raise HTTPException(400, "Title must be 200 characters or fewer")

    category = req.category.lower() if req.category.lower() in VALID_CATEGORIES else "general"
    priority = req.priority.lower() if req.priority.lower() in VALID_PRIORITIES else "medium"

    import html
    title = html.escape(title, quote=True)
    description = html.escape(req.description.strip()[:2000], quote=True)

    ticket_id = str(uuid.uuid4())
    now = time.time()
    s = get_settings()

    with sqlite3.connect(s.db_path) as con:
        con.execute(
            "INSERT INTO tickets (ticket_id, title, description, category, priority, "
            "status, raised_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (ticket_id, title, description, category, priority, "raised", user.user_id, now, now),
        )
        # Record creation in history
        con.execute(
            "INSERT INTO ticket_history (ticket_id, action, performed_by, new_value, timestamp) "
            "VALUES (?,?,?,?,?)",
            (ticket_id, "created", user.user_id, "raised", now),
        )

    log_security_event("ticket_created", {
        "ticket_id": ticket_id, "category": category, "priority": priority,
    }, user_id=user.user_id)

    # Phase D: Notify HR team about new ticket
    try:
        from backend.app.api.notification_routes import notify_role
        notify_role("hr_team", f"New ticket: {title[:80]}",
                    f"Priority: {priority} | Category: {category}",
                    "action", f"/tickets/{ticket_id}", s.db_path)
        notify_role("hr_head", f"New ticket: {title[:80]}",
                    f"Priority: {priority} | Category: {category}",
                    "action", f"/tickets/{ticket_id}", s.db_path)
    except Exception:
        pass  # Non-critical — don't fail ticket creation

    return {
        "ticket_id": ticket_id, "title": title, "status": "raised",
        "category": category, "priority": priority, "created_at": now,
    }


@router.get("")
async def list_tickets(
    status: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
):
    """List tickets. Employees see own tickets only; HR roles see all."""
    s = get_settings()
    # Auto-close expired resolved tickets on each list fetch
    _auto_close_resolved(s.db_path)
    offset = (page - 1) * limit

    # Build query based on role
    conditions = []
    params: list = []

    if user.role in _HR_ROLES:
        pass  # HR roles see all tickets
    else:
        # Employees/managers see only their own tickets
        conditions.append("t.raised_by = ?")
        params.append(user.user_id)

    if status and status in VALID_STATUSES:
        conditions.append("t.status = ?")
        params.append(status)
    if category and category in VALID_CATEGORIES:
        conditions.append("t.category = ?")
        params.append(category)
    if priority and priority in VALID_PRIORITIES:
        conditions.append("t.priority = ?")
        params.append(priority)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with sqlite3.connect(s.db_path) as con:
        total = con.execute(
            f"SELECT COUNT(*) FROM tickets t {where}", params
        ).fetchone()[0]

        rows = con.execute(
            f"SELECT t.ticket_id, t.title, t.description, t.category, t.priority, "
            f"t.status, t.raised_by, t.assigned_to, t.created_at, t.updated_at, t.resolved_at, "
            f"COALESCE(u.full_name, u.username, t.raised_by), "
            f"COALESCE(a.full_name, a.username, ''), "
            f"t.auto_close_at, COALESCE(t.feedback,''), COALESCE(t.rating,0) "
            f"FROM tickets t "
            f"LEFT JOIN users u ON t.raised_by = u.user_id "
            f"LEFT JOIN users a ON t.assigned_to = a.user_id "
            f"{where} ORDER BY t.updated_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()

    return {
        "tickets": [
            {
                "ticket_id": r[0], "title": r[1], "description": r[2][:200],
                "category": r[3], "priority": r[4], "status": r[5],
                "raised_by": r[6], "assigned_to": r[7] or "",
                "created_at": r[8], "updated_at": r[9], "resolved_at": r[10],
                "raised_by_name": r[11], "assigned_to_name": r[12],
                "auto_close_at": r[13], "feedback": r[14], "rating": r[15],
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/{ticket_id}")
async def get_ticket(ticket_id: str, user: User = Depends(get_current_user)):
    """Get ticket details with full history."""
    s = get_settings()
    # Auto-close check
    _auto_close_resolved(s.db_path)
    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT t.ticket_id, t.title, t.description, t.category, t.priority, "
            "t.status, t.raised_by, t.assigned_to, t.created_at, t.updated_at, t.resolved_at, "
            "COALESCE(u.full_name, u.username, t.raised_by), "
            "COALESCE(a.full_name, a.username, ''), "
            "t.auto_close_at, COALESCE(t.feedback,''), COALESCE(t.rating,0) "
            "FROM tickets t "
            "LEFT JOIN users u ON t.raised_by = u.user_id "
            "LEFT JOIN users a ON t.assigned_to = a.user_id "
            "WHERE t.ticket_id = ?",
            (ticket_id,),
        ).fetchone()

        if not row:
            raise HTTPException(404, "Ticket not found")

        # Access check: employees can only view their own tickets
        if user.role not in _HR_ROLES and row[6] != user.user_id:
            raise HTTPException(403, "You can only view your own tickets")

        # Get history
        history = con.execute(
            "SELECT h.action, h.performed_by, h.old_value, h.new_value, h.comment, h.timestamp, "
            "COALESCE(u.full_name, u.username, h.performed_by) "
            "FROM ticket_history h "
            "LEFT JOIN users u ON h.performed_by = u.user_id "
            "WHERE h.ticket_id = ? ORDER BY h.timestamp ASC",
            (ticket_id,),
        ).fetchall()

    return {
        "ticket_id": row[0], "title": row[1], "description": row[2],
        "category": row[3], "priority": row[4], "status": row[5],
        "raised_by": row[6], "assigned_to": row[7] or "",
        "created_at": row[8], "updated_at": row[9], "resolved_at": row[10],
        "raised_by_name": row[11], "assigned_to_name": row[12],
        "auto_close_at": row[13], "feedback": row[14], "rating": row[15],
        "history": [
            {
                "action": h[0], "performed_by": h[1], "old_value": h[2],
                "new_value": h[3], "comment": h[4], "timestamp": h[5],
                "performed_by_name": h[6],
            }
            for h in history
        ],
    }


@router.patch("/{ticket_id}")
async def update_ticket(
    ticket_id: str, req: UpdateTicketRequest, user: User = Depends(get_current_user),
):
    """Update ticket status, priority, or assignment. HR roles only."""
    if user.role not in _HR_ROLES:
        raise HTTPException(403, "Only HR team members can update tickets")

    s = get_settings()
    now = time.time()

    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT status, priority, assigned_to FROM tickets WHERE ticket_id=?",
            (ticket_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Ticket not found")

        current_status, current_priority, current_assigned = row

        # Status change
        if req.status and req.status != current_status:
            if req.status not in VALID_STATUSES:
                raise HTTPException(400, f"Invalid status. Must be one of: {', '.join(sorted(VALID_STATUSES))}")

            allowed = STATUS_TRANSITIONS.get(current_status, set())
            if req.status not in allowed:
                raise HTTPException(
                    400,
                    f"Cannot transition from '{current_status}' to '{req.status}'. "
                    f"Allowed: {', '.join(sorted(allowed)) if allowed else 'none (terminal state)'}",
                )

            # Close/reject require hr_head+
            if req.status in ("closed", "rejected") and user.role not in _HR_HEAD_ROLES:
                raise HTTPException(403, "Only HR Head or Admin can close/reject tickets")

            con.execute(
                "UPDATE tickets SET status=?, updated_at=? WHERE ticket_id=?",
                (req.status, now, ticket_id),
            )
            if req.status == "resolved":
                auto_close = _add_working_days(now, AUTO_CLOSE_WORKING_DAYS)
                con.execute(
                    "UPDATE tickets SET resolved_at=?, auto_close_at=? WHERE ticket_id=?",
                    (now, auto_close, ticket_id),
                )
            # Clear auto_close_at if reopened
            if req.status == "in_progress":
                con.execute(
                    "UPDATE tickets SET auto_close_at=NULL WHERE ticket_id=?", (ticket_id,),
                )
            con.execute(
                "INSERT INTO ticket_history (ticket_id, action, performed_by, old_value, new_value, comment, timestamp) "
                "VALUES (?,?,?,?,?,?,?)",
                (ticket_id, "status_change", user.user_id, current_status, req.status, req.comment, now),
            )

        # Priority change
        if req.priority and req.priority != current_priority:
            if req.priority not in VALID_PRIORITIES:
                raise HTTPException(400, f"Invalid priority. Must be one of: {', '.join(sorted(VALID_PRIORITIES))}")
            con.execute(
                "UPDATE tickets SET priority=?, updated_at=? WHERE ticket_id=?",
                (req.priority, now, ticket_id),
            )
            con.execute(
                "INSERT INTO ticket_history (ticket_id, action, performed_by, old_value, new_value, comment, timestamp) "
                "VALUES (?,?,?,?,?,?,?)",
                (ticket_id, "priority_change", user.user_id, current_priority, req.priority, req.comment, now),
            )

        # Assignment change
        if req.assigned_to is not None and req.assigned_to != current_assigned:
            # Verify assignee exists and is HR
            if req.assigned_to:
                assignee = con.execute(
                    "SELECT role FROM users WHERE user_id=?", (req.assigned_to,)
                ).fetchone()
                if not assignee:
                    raise HTTPException(404, "Assignee user not found")

            new_status = "assigned" if req.assigned_to and current_status == "raised" else None
            if new_status:
                con.execute(
                    "UPDATE tickets SET assigned_to=?, status=?, updated_at=? WHERE ticket_id=?",
                    (req.assigned_to, new_status, now, ticket_id),
                )
                con.execute(
                    "INSERT INTO ticket_history (ticket_id, action, performed_by, old_value, new_value, comment, timestamp) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (ticket_id, "status_change", user.user_id, current_status, new_status, "Auto-assigned", now),
                )
            else:
                con.execute(
                    "UPDATE tickets SET assigned_to=?, updated_at=? WHERE ticket_id=?",
                    (req.assigned_to, now, ticket_id),
                )

            con.execute(
                "INSERT INTO ticket_history (ticket_id, action, performed_by, old_value, new_value, comment, timestamp) "
                "VALUES (?,?,?,?,?,?,?)",
                (ticket_id, "assigned", user.user_id, current_assigned or "", req.assigned_to, req.comment, now),
            )

        # Comment-only update (no field changes)
        if req.comment and not req.status and not req.priority and req.assigned_to is None:
            con.execute(
                "UPDATE tickets SET updated_at=? WHERE ticket_id=?", (now, ticket_id),
            )
            con.execute(
                "INSERT INTO ticket_history (ticket_id, action, performed_by, old_value, new_value, comment, timestamp) "
                "VALUES (?,?,?,?,?,?,?)",
                (ticket_id, "comment", user.user_id, "", "", req.comment, now),
            )

    # Phase D: Notify ticket raiser about updates
    try:
        with sqlite3.connect(s.db_path) as con2:
            tb = con2.execute(
                "SELECT raised_by, title FROM tickets WHERE ticket_id=?", (ticket_id,)
            ).fetchone()
        if tb and tb[0] != user.user_id:
            from backend.app.api.notification_routes import create_notification
            msg_parts = []
            if req.status:
                msg_parts.append(f"Status: {req.status}")
            if req.priority:
                msg_parts.append(f"Priority: {req.priority}")
            if req.assigned_to:
                msg_parts.append("Assigned to HR")
            create_notification(
                tb[0], f"Ticket updated: {tb[1][:80]}",
                " | ".join(msg_parts) if msg_parts else "Your ticket was updated",
                "info", f"/tickets/{ticket_id}", s.db_path,
            )
    except Exception:
        pass  # Non-critical

    return {"status": "updated", "ticket_id": ticket_id}


@router.post("/{ticket_id}/comment")
async def add_comment(
    ticket_id: str, req: TicketCommentRequest, user: User = Depends(get_current_user),
):
    """Add a comment to a ticket. Ticket owner or HR can comment."""
    if not req.comment.strip():
        raise HTTPException(400, "Comment cannot be empty")

    s = get_settings()
    now = time.time()

    import html
    comment = html.escape(req.comment.strip()[:2000], quote=True)

    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT raised_by, status FROM tickets WHERE ticket_id=?", (ticket_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Ticket not found")

        # Access: ticket owner or HR
        if user.role not in _HR_ROLES and row[0] != user.user_id:
            raise HTTPException(403, "You can only comment on your own tickets")

        if row[1] in ("closed", "rejected"):
            raise HTTPException(400, "Cannot comment on closed/rejected tickets")

        con.execute(
            "UPDATE tickets SET updated_at=? WHERE ticket_id=?", (now, ticket_id),
        )
        con.execute(
            "INSERT INTO ticket_history (ticket_id, action, performed_by, comment, timestamp) "
            "VALUES (?,?,?,?,?)",
            (ticket_id, "comment", user.user_id, comment, now),
        )

    return {"status": "comment_added", "ticket_id": ticket_id}


@router.post("/{ticket_id}/respond")
async def respond_to_ticket(
    ticket_id: str, req: TicketRespondRequest, user: User = Depends(get_current_user),
):
    """Employee responds to a resolved ticket: accept (close) or reject (reopen).

    - accept: ticket closes, employee can leave feedback + rating (1-5)
    - reject: ticket reopens to in_progress, employee should add comment explaining why
    """
    if req.action not in ("accept", "reject"):
        raise HTTPException(400, "Action must be 'accept' or 'reject'")

    if req.rating and (req.rating < 1 or req.rating > 5):
        raise HTTPException(400, "Rating must be between 1 and 5")

    s = get_settings()
    now = time.time()

    import html as _html
    feedback = _html.escape(req.feedback.strip()[:1000], quote=True) if req.feedback else ""

    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT status, raised_by, title FROM tickets WHERE ticket_id=?", (ticket_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Ticket not found")

        if row[0] != "resolved":
            raise HTTPException(400, "Can only respond to resolved tickets")

        if row[1] != user.user_id:
            raise HTTPException(403, "Only the ticket raiser can accept or reject")

        if req.action == "accept":
            con.execute(
                "UPDATE tickets SET status='closed', feedback=?, rating=?, "
                "auto_close_at=NULL, updated_at=? WHERE ticket_id=?",
                (feedback, req.rating or 0, now, ticket_id),
            )
            con.execute(
                "INSERT INTO ticket_history (ticket_id, action, performed_by, old_value, new_value, comment, timestamp) "
                "VALUES (?,?,?,?,?,?,?)",
                (ticket_id, "status_change", user.user_id, "resolved", "closed",
                 f"Employee accepted resolution.{(' Feedback: ' + feedback) if feedback else ''}"
                 f"{(' Rating: ' + str(req.rating) + '/5') if req.rating else ''}",
                 now),
            )
        else:  # reject — need more details
            con.execute(
                "UPDATE tickets SET status='in_progress', auto_close_at=NULL, updated_at=? WHERE ticket_id=?",
                (now, ticket_id),
            )
            con.execute(
                "INSERT INTO ticket_history (ticket_id, action, performed_by, old_value, new_value, comment, timestamp) "
                "VALUES (?,?,?,?,?,?,?)",
                (ticket_id, "status_change", user.user_id, "resolved", "in_progress",
                 f"Employee requested more details.{(' Reason: ' + feedback) if feedback else ''}",
                 now),
            )

    # Notify HR about the response
    try:
        from backend.app.api.notification_routes import notify_role
        if req.action == "accept":
            notify_role("hr_team", f"Ticket accepted: {row[2][:80]}",
                        f"Employee accepted the resolution.{(' Rating: ' + str(req.rating) + '/5') if req.rating else ''}",
                        "info", f"/tickets/{ticket_id}", s.db_path)
        else:
            notify_role("hr_team", f"Ticket reopened: {row[2][:80]}",
                        "Employee needs more details — ticket moved back to in-progress.",
                        "action", f"/tickets/{ticket_id}", s.db_path)
    except Exception:
        pass

    return {"status": req.action + "ed", "ticket_id": ticket_id}


@router.get("/stats/summary")
async def ticket_stats(user: User = Depends(get_current_user)):
    """Get ticket statistics. HR roles see all; employees see own."""
    s = get_settings()

    with sqlite3.connect(s.db_path) as con:
        if user.role in _HR_ROLES:
            where = ""
            params: list = []
        else:
            where = "WHERE raised_by = ?"
            params = [user.user_id]

        rows = con.execute(
            f"SELECT status, COUNT(*) FROM tickets {where} GROUP BY status", params,
        ).fetchall()

        # Priority breakdown for open tickets
        open_statuses = "('raised','assigned','in_progress')"
        if user.role in _HR_ROLES:
            priority_rows = con.execute(
                f"SELECT priority, COUNT(*) FROM tickets WHERE status IN {open_statuses} GROUP BY priority",
            ).fetchall()
        else:
            priority_rows = con.execute(
                f"SELECT priority, COUNT(*) FROM tickets WHERE status IN {open_statuses} AND raised_by = ? GROUP BY priority",
                (user.user_id,),
            ).fetchall()

    status_counts = {r[0]: r[1] for r in rows}
    priority_counts = {r[0]: r[1] for r in priority_rows}
    total = sum(status_counts.values())
    open_count = sum(status_counts.get(s, 0) for s in ("raised", "assigned", "in_progress"))

    return {
        "total": total,
        "open": open_count,
        "by_status": status_counts,
        "by_priority": priority_counts,
    }
