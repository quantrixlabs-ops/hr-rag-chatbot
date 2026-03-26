"""User self-service endpoints — GDPR compliance (Phase B)."""

import html as _html
import json
import sqlite3
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.app.core.config import get_settings
from backend.app.core.security import (
    get_current_user, hash_password, log_security_event, revoke_all_user_refresh_tokens,
)
from backend.app.models.chat_models import User


class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    department: Optional[str] = None
    team: Optional[str] = None

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/profile")
async def get_profile(user: User = Depends(get_current_user)):
    """Return the current user's profile information."""
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT username, role, department, full_name, email, phone, created_at, tenant_id, "
            "COALESCE(employee_id,''), COALESCE(branch_id,''), COALESCE(team,''), "
            "COALESCE(totp_enabled,0) "
            "FROM users WHERE user_id=?",
            (user.user_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "User not found")

    # Resolve branch name if branch_id exists
    branch_name = ""
    if row[9]:
        with sqlite3.connect(s.db_path) as con:
            br = con.execute("SELECT name FROM branches WHERE branch_id=?", (row[9],)).fetchone()
            if br:
                branch_name = br[0]

    return {
        "user_id": user.user_id,
        "username": row[0],
        "role": row[1],
        "department": row[2] or "",
        "full_name": row[3] or "",
        "email": row[4] or "",
        "phone": row[5] or "",
        "created_at": row[6],
        "tenant_id": row[7],
        "employee_id": row[8],
        "branch_id": row[9],
        "branch_name": branch_name,
        "team": row[10],
        "totp_enabled": bool(row[11]),
    }


@router.patch("/profile")
async def update_profile(req: UpdateProfileRequest, user: User = Depends(get_current_user)):
    """Update editable profile fields. Role, employee_id, and username are read-only."""
    s = get_settings()
    now = time.time()

    updates = []
    params: list = []

    if req.full_name is not None:
        updates.append("full_name = ?")
        params.append(_html.escape(req.full_name.strip(), quote=True)[:100])
    if req.email is not None:
        updates.append("email = ?")
        params.append(req.email.strip()[:254])
    if req.phone is not None:
        updates.append("phone = ?")
        params.append(req.phone.strip()[:20])
    if req.department is not None:
        updates.append("department = ?")
        params.append(_html.escape(req.department.strip(), quote=True)[:100])
    if req.team is not None:
        updates.append("team = ?")
        params.append(_html.escape(req.team.strip(), quote=True)[:100])

    if not updates:
        raise HTTPException(400, "No fields to update")

    params.append(user.user_id)
    with sqlite3.connect(s.db_path) as con:
        con.execute(f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?", params)

    log_security_event("profile_updated", {"fields": len(updates)}, user_id=user.user_id)
    return {"status": "updated", "message": "Profile updated successfully."}


# Aliases: /users/me → /user/profile (frontend compatibility)
@router.get("/me", include_in_schema=False)
async def get_profile_alias(user: User = Depends(get_current_user)):
    return await get_profile(user)


@router.patch("/me", include_in_schema=False)
async def update_profile_alias(req: UpdateProfileRequest, user: User = Depends(get_current_user)):
    return await update_profile(req, user)


@router.get("/data/export")
async def export_user_data(user: User = Depends(get_current_user)):
    """GDPR Article 20 — Data portability. Export all user data as JSON."""
    s = get_settings()
    export = {"exported_at": time.time(), "user": {}, "sessions": [], "feedback": []}

    with sqlite3.connect(s.db_path) as con:
        # User profile
        row = con.execute(
            "SELECT username, role, department, full_name, email, phone, created_at "
            "FROM users WHERE user_id=?",
            (user.user_id,),
        ).fetchone()
        if row:
            export["user"] = {
                "user_id": user.user_id,
                "username": row[0], "role": row[1], "department": row[2],
                "full_name": row[3], "email": row[4], "phone": row[5],
                "created_at": row[6],
            }

        # Conversation history
        sessions = con.execute(
            "SELECT session_id, created_at, last_active FROM sessions WHERE user_id=?",
            (user.user_id,),
        ).fetchall()
        for sess in sessions:
            turns = con.execute(
                "SELECT role, content, timestamp FROM turns WHERE session_id=? ORDER BY timestamp",
                (sess[0],),
            ).fetchall()
            export["sessions"].append({
                "session_id": sess[0],
                "created_at": sess[1],
                "last_active": sess[2],
                "messages": [{"role": t[0], "content": t[1], "timestamp": t[2]} for t in turns],
            })

        # Feedback given
        feedback = con.execute(
            "SELECT session_id, rating, timestamp FROM feedback WHERE user_id=?",
            (user.user_id,),
        ).fetchall()
        export["feedback"] = [
            {"session_id": f[0], "rating": f[1], "timestamp": f[2]} for f in feedback
        ]

    log_security_event("gdpr_data_export", {"user_id": user.user_id}, user_id=user.user_id)

    return JSONResponse(
        content=export,
        headers={"Content-Disposition": f"attachment; filename=user_data_{user.user_id[:8]}.json"},
    )


@router.delete("/data")
async def delete_user_data(user: User = Depends(get_current_user)):
    """GDPR Article 17 — Right to erasure. Delete all user data.

    This removes: profile, sessions, turns, feedback, refresh tokens.
    Query logs are already anonymized (hash only) so they are retained.
    """
    s = get_settings()

    with sqlite3.connect(s.db_path) as con:
        # Get all session IDs for this user
        session_ids = [r[0] for r in con.execute(
            "SELECT session_id FROM sessions WHERE user_id=?", (user.user_id,)
        ).fetchall()]

        # Delete turns for all sessions
        for sid in session_ids:
            con.execute("DELETE FROM turns WHERE session_id=?", (sid,))

        # Delete sessions
        con.execute("DELETE FROM sessions WHERE user_id=?", (user.user_id,))

        # Delete feedback
        con.execute("DELETE FROM feedback WHERE user_id=?", (user.user_id,))

        # Delete refresh tokens
        con.execute("DELETE FROM refresh_tokens WHERE user_id=?", (user.user_id,))

        # Anonymize the user record (keep for referential integrity but strip PII)
        con.execute(
            "UPDATE users SET username=?, full_name='[deleted]', email='', phone='', "
            "hashed_password='[deleted]', department=NULL WHERE user_id=?",
            (f"deleted_{user.user_id[:8]}", user.user_id),
        )

    # Revoke all tokens
    revoke_all_user_refresh_tokens(user.user_id)

    log_security_event(
        "gdpr_data_deletion",
        {"user_id": user.user_id, "sessions_deleted": len(session_ids)},
        user_id=user.user_id,
    )

    return {
        "status": "deleted",
        "sessions_removed": len(session_ids),
        "message": "All personal data has been erased. Your account has been anonymized.",
    }
