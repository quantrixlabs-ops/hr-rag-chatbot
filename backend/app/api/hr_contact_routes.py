"""HR Contact directory endpoints — Phase F.

Manages HR contact information per branch. Employees can view contacts;
HR Admin can manage them.
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

router = APIRouter(prefix="/hr-contacts", tags=["hr-contacts"])

_ADMIN_ROLES = {"hr_admin", "hr_head", "admin", "super_admin"}


# ── Request Models ───────────────────────────────────────────────────────────

class CreateContactRequest(BaseModel):
    name: str
    role: str = "hr_team"
    email: str = ""
    phone: str = ""
    branch_id: str = ""


class UpdateContactRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    branch_id: Optional[str] = None
    is_available: Optional[bool] = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("")
async def list_contacts(
    branch_id: Optional[str] = None,
    available_only: bool = True,
    user: User = Depends(get_current_user),
):
    """List HR contacts. Any authenticated user can view.
    Optionally filter by branch_id.
    """
    s = get_settings()
    conditions: list[str] = []
    params: list = []

    if available_only:
        conditions.append("c.is_available=1")
    if branch_id:
        conditions.append("(c.branch_id=? OR c.branch_id='')")
        params.append(branch_id)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with sqlite3.connect(s.db_path) as con:
        rows = con.execute(
            f"SELECT c.contact_id, c.name, c.role, c.email, c.phone, "
            f"c.branch_id, c.is_available, COALESCE(b.name, '') "
            f"FROM hr_contacts c LEFT JOIN branches b ON c.branch_id=b.branch_id "
            f"{where} ORDER BY c.name",
            params,
        ).fetchall()

    return {
        "contacts": [
            {
                "contact_id": r[0], "name": r[1], "role": r[2],
                "email": r[3], "phone": r[4], "branch_id": r[5],
                "is_available": bool(r[6]), "branch_name": r[7],
            }
            for r in rows
        ],
    }


@router.get("/{contact_id}")
async def get_contact(contact_id: str, user: User = Depends(get_current_user)):
    """Get a single HR contact."""
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT c.contact_id, c.name, c.role, c.email, c.phone, "
            "c.branch_id, c.is_available, COALESCE(b.name, '') "
            "FROM hr_contacts c LEFT JOIN branches b ON c.branch_id=b.branch_id "
            "WHERE c.contact_id=?",
            (contact_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Contact not found")
    return {
        "contact_id": row[0], "name": row[1], "role": row[2],
        "email": row[3], "phone": row[4], "branch_id": row[5],
        "is_available": bool(row[6]), "branch_name": row[7],
    }


@router.post("", status_code=201)
async def create_contact(req: CreateContactRequest, user: User = Depends(get_current_user)):
    """Create an HR contact — HR Admin+ only."""
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(403, "Only HR Admin can manage contacts")

    import html
    name = html.escape(req.name.strip(), quote=True)
    if not name or len(name) < 2:
        raise HTTPException(400, "Name must be at least 2 characters")

    contact_id = str(uuid.uuid4())
    s = get_settings()

    with sqlite3.connect(s.db_path) as con:
        con.execute(
            "INSERT INTO hr_contacts (contact_id, name, role, email, phone, branch_id, is_available) "
            "VALUES (?,?,?,?,?,?,?)",
            (contact_id, name, req.role, req.email.strip(), req.phone.strip(),
             req.branch_id, 1),
        )

    return {"contact_id": contact_id, "name": name, "status": "created"}


@router.patch("/{contact_id}")
async def update_contact(
    contact_id: str, req: UpdateContactRequest, user: User = Depends(get_current_user),
):
    """Update an HR contact — HR Admin+ only."""
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(403, "Only HR Admin can manage contacts")

    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute("SELECT 1 FROM hr_contacts WHERE contact_id=?", (contact_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Contact not found")

        import html
        updates: list[str] = []
        params: list = []
        if req.name is not None:
            updates.append("name=?")
            params.append(html.escape(req.name.strip(), quote=True))
        if req.role is not None:
            updates.append("role=?")
            params.append(req.role)
        if req.email is not None:
            updates.append("email=?")
            params.append(req.email.strip())
        if req.phone is not None:
            updates.append("phone=?")
            params.append(req.phone.strip())
        if req.branch_id is not None:
            updates.append("branch_id=?")
            params.append(req.branch_id)
        if req.is_available is not None:
            updates.append("is_available=?")
            params.append(1 if req.is_available else 0)

        if not updates:
            raise HTTPException(400, "No fields to update")

        params.append(contact_id)
        con.execute(f"UPDATE hr_contacts SET {', '.join(updates)} WHERE contact_id=?", params)

    return {"status": "updated", "contact_id": contact_id}


@router.delete("/{contact_id}")
async def delete_contact(contact_id: str, user: User = Depends(get_current_user)):
    """Delete an HR contact — HR Admin+ only."""
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(403, "Only HR Admin can manage contacts")

    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute("SELECT 1 FROM hr_contacts WHERE contact_id=?", (contact_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Contact not found")
        con.execute("DELETE FROM hr_contacts WHERE contact_id=?", (contact_id,))

    return {"status": "deleted", "contact_id": contact_id}
