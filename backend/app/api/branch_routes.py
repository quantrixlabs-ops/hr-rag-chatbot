"""Branch management endpoints — Phase F.

CRUD for organizational branches. Admin only for write ops.
All authenticated users can list branches.
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

router = APIRouter(prefix="/branches", tags=["branches"])

_ADMIN_ROLES = {"hr_admin", "admin", "super_admin"}


# ── Request Models ───────────────────────────────────────────────────────────

class CreateBranchRequest(BaseModel):
    name: str
    location: str = ""
    address: str = ""


class UpdateBranchRequest(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    address: Optional[str] = None
    is_active: Optional[bool] = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("")
async def list_branches(
    active_only: bool = True,
    user: User = Depends(get_current_user),
):
    """List all branches. Any authenticated user can view."""
    s = get_settings()
    where = "WHERE is_active=1" if active_only else ""
    with sqlite3.connect(s.db_path) as con:
        rows = con.execute(
            f"SELECT branch_id, name, location, address, is_active, created_at "
            f"FROM branches {where} ORDER BY name",
        ).fetchall()
        # Count users per branch
        user_counts = dict(con.execute(
            "SELECT branch_id, COUNT(*) FROM users WHERE branch_id != '' GROUP BY branch_id"
        ).fetchall())
    return {
        "branches": [
            {
                "branch_id": r[0], "name": r[1], "location": r[2],
                "address": r[3], "is_active": bool(r[4]),
                "created_at": r[5], "user_count": user_counts.get(r[0], 0),
            }
            for r in rows
        ],
    }


@router.get("/{branch_id}")
async def get_branch(branch_id: str, user: User = Depends(get_current_user)):
    """Get branch details."""
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT branch_id, name, location, address, is_active, created_at "
            "FROM branches WHERE branch_id=?",
            (branch_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Branch not found")
    return {
        "branch_id": row[0], "name": row[1], "location": row[2],
        "address": row[3], "is_active": bool(row[4]), "created_at": row[5],
    }


@router.post("", status_code=201)
async def create_branch(req: CreateBranchRequest, user: User = Depends(get_current_user)):
    """Create a new branch — Admin only."""
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(403, "Only admins can manage branches")

    import html
    name = html.escape(req.name.strip(), quote=True)
    if not name or len(name) < 2:
        raise HTTPException(400, "Branch name must be at least 2 characters")

    branch_id = str(uuid.uuid4())
    now = time.time()
    s = get_settings()

    with sqlite3.connect(s.db_path) as con:
        con.execute(
            "INSERT INTO branches (branch_id, name, location, address, is_active, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (branch_id, name, req.location.strip(), req.address.strip(), 1, now),
        )

    return {"branch_id": branch_id, "name": name, "status": "created"}


@router.patch("/{branch_id}")
async def update_branch(
    branch_id: str, req: UpdateBranchRequest, user: User = Depends(get_current_user),
):
    """Update branch details — Admin only."""
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(403, "Only admins can manage branches")

    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute("SELECT 1 FROM branches WHERE branch_id=?", (branch_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Branch not found")

        import html
        updates: list[str] = []
        params: list = []
        if req.name is not None:
            updates.append("name=?")
            params.append(html.escape(req.name.strip(), quote=True))
        if req.location is not None:
            updates.append("location=?")
            params.append(req.location.strip())
        if req.address is not None:
            updates.append("address=?")
            params.append(req.address.strip())
        if req.is_active is not None:
            updates.append("is_active=?")
            params.append(1 if req.is_active else 0)

        if not updates:
            raise HTTPException(400, "No fields to update")

        params.append(branch_id)
        con.execute(f"UPDATE branches SET {', '.join(updates)} WHERE branch_id=?", params)

    return {"status": "updated", "branch_id": branch_id}


@router.delete("/{branch_id}")
async def delete_branch(branch_id: str, user: User = Depends(get_current_user)):
    """Soft-delete a branch (deactivate) — Admin only."""
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(403, "Only admins can manage branches")

    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute("SELECT 1 FROM branches WHERE branch_id=?", (branch_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Branch not found")
        con.execute("UPDATE branches SET is_active=0 WHERE branch_id=?", (branch_id,))

    return {"status": "deactivated", "branch_id": branch_id}


@router.get("/{branch_id}/stats")
async def branch_stats(branch_id: str, user: User = Depends(get_current_user)):
    """Get stats for a specific branch — HR roles only."""
    _HR_ROLES = {"hr_team", "hr_head", "hr_admin", "admin", "super_admin"}
    if user.role not in _HR_ROLES:
        raise HTTPException(403, "Only HR team can view branch stats")

    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        user_count = con.execute(
            "SELECT COUNT(*) FROM users WHERE branch_id=?", (branch_id,)
        ).fetchone()[0]
        ticket_count = con.execute(
            "SELECT COUNT(*) FROM tickets t JOIN users u ON t.raised_by=u.user_id WHERE u.branch_id=?",
            (branch_id,),
        ).fetchone()[0]
        open_tickets = con.execute(
            "SELECT COUNT(*) FROM tickets t JOIN users u ON t.raised_by=u.user_id "
            "WHERE u.branch_id=? AND t.status NOT IN ('resolved','closed','rejected')",
            (branch_id,),
        ).fetchone()[0]
        contact_count = con.execute(
            "SELECT COUNT(*) FROM hr_contacts WHERE branch_id=? AND is_available=1",
            (branch_id,),
        ).fetchone()[0]

    return {
        "branch_id": branch_id,
        "user_count": user_count,
        "ticket_count": ticket_count,
        "open_tickets": open_tickets,
        "hr_contact_count": contact_count,
    }
