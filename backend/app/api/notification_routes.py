"""Notification system endpoints — Phase D.

Provides CRUD for user notifications and a helper to create
notifications from other modules (ticket updates, doc approvals, etc.).
"""

from __future__ import annotations

import sqlite3
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from backend.app.core.config import get_settings
from backend.app.core.security import get_current_user, require_role
from backend.app.models.chat_models import User

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ── Helper: create a notification (called from other modules) ────────────────

def create_notification(
    user_id: str,
    title: str,
    message: str = "",
    notification_type: str = "info",
    link: str = "",
    db_path: str | None = None,
) -> str:
    """Insert a notification for a user. Returns notification_id.

    notification_type: info | success | warning | action
    link: optional deep-link (e.g., "/tickets/<id>")
    """
    nid = str(uuid.uuid4())
    now = time.time()
    path = db_path or get_settings().db_path
    with sqlite3.connect(path) as con:
        con.execute(
            "INSERT INTO notifications (notification_id, user_id, title, message, "
            "notification_type, link, created_at) VALUES (?,?,?,?,?,?,?)",
            (nid, user_id, title[:200], message[:1000], notification_type, link, now),
        )
    return nid


def notify_role(
    role: str,
    title: str,
    message: str = "",
    notification_type: str = "info",
    link: str = "",
    db_path: str | None = None,
) -> int:
    """Send a notification to all users with a given role. Returns count sent."""
    path = db_path or get_settings().db_path
    with sqlite3.connect(path) as con:
        rows = con.execute("SELECT user_id FROM users WHERE role=? AND status='active'", (role,)).fetchall()
    count = 0
    for (uid,) in rows:
        create_notification(uid, title, message, notification_type, link, path)
        count += 1
    return count


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("")
async def list_notifications(
    unread_only: bool = False,
    limit: int = Query(30, ge=1, le=100),
    user: User = Depends(get_current_user),
):
    """List notifications for the current user."""
    s = get_settings()
    if unread_only:
        where = "WHERE n.user_id=? AND n.is_read=0"
    else:
        where = "WHERE n.user_id=?"
    with sqlite3.connect(s.db_path) as con:
        rows = con.execute(
            f"SELECT n.notification_id, n.title, n.message, n.notification_type, "
            f"n.is_read, n.link, n.created_at "
            f"FROM notifications n {where} ORDER BY n.created_at DESC LIMIT ?",
            (user.user_id, limit),
        ).fetchall()
        unread_count = con.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0",
            (user.user_id,),
        ).fetchone()[0]
    return {
        "notifications": [
            {
                "notification_id": r[0], "title": r[1], "message": r[2],
                "type": r[3], "is_read": bool(r[4]), "link": r[5],
                "created_at": r[6],
            }
            for r in rows
        ],
        "unread_count": unread_count,
    }


@router.get("/unread-count")
async def unread_count(user: User = Depends(get_current_user)):
    """Quick endpoint to get just the unread notification count (for badge)."""
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        count = con.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0",
            (user.user_id,),
        ).fetchone()[0]
    return {"unread_count": count}


@router.post("/{notification_id}/read")
async def mark_read(notification_id: str, user: User = Depends(get_current_user)):
    """Mark a single notification as read."""
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT user_id FROM notifications WHERE notification_id=?",
            (notification_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Notification not found")
        if row[0] != user.user_id:
            raise HTTPException(403, "Not your notification")
        con.execute(
            "UPDATE notifications SET is_read=1 WHERE notification_id=?",
            (notification_id,),
        )
    return {"status": "read"}


@router.post("/read-all")
async def mark_all_read(user: User = Depends(get_current_user)):
    """Mark all notifications as read for the current user."""
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        cur = con.execute(
            "UPDATE notifications SET is_read=1 WHERE user_id=? AND is_read=0",
            (user.user_id,),
        )
    return {"status": "all_read", "marked": cur.rowcount}


class SendNotificationRequest(BaseModel):
    user_id: str
    title: str
    message: str = ""
    notification_type: str = "info"
    link: str = ""


@router.post("/send")
async def send_notification(req: SendNotificationRequest, user: User = Depends(get_current_user)):
    """Send a notification to a specific user — HR roles only."""
    _HR_ROLES = {"hr_team", "hr_head", "hr_admin", "admin", "super_admin"}
    if user.role not in _HR_ROLES:
        raise HTTPException(403, "Only HR team members can send notifications")

    import html
    title = html.escape(req.title.strip(), quote=True)[:200]
    message = html.escape(req.message.strip(), quote=True)[:1000]
    if not title:
        raise HTTPException(400, "Title is required")

    nid = create_notification(req.user_id, title, message, req.notification_type, req.link)
    return {"status": "sent", "notification_id": nid}
