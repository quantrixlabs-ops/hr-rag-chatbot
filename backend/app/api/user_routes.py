"""User self-service endpoints — GDPR compliance (Phase B)."""

import json
import sqlite3
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from backend.app.core.config import get_settings
from backend.app.core.security import (
    get_current_user, hash_password, log_security_event, revoke_all_user_refresh_tokens,
)
from backend.app.models.chat_models import User

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/profile")
async def get_profile(user: User = Depends(get_current_user)):
    """Return the current user's profile information."""
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT username, role, department, full_name, email, phone, created_at, tenant_id "
            "FROM users WHERE user_id=?",
            (user.user_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "User not found")
    return {
        "user_id": user.user_id,
        "username": row[0],
        "role": row[1],
        "department": row[2],
        "full_name": row[3],
        "email": row[4],
        "phone": row[5],
        "created_at": row[6],
        "tenant_id": row[7],
    }


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
