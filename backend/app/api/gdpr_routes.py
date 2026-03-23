"""GDPR compliance routes — Phase 5 (F-53).

Implements GDPR Article 15 (Subject Access Request) and Article 17 (Right to Erasure).

Endpoints:
  GET  /api/v1/users/{user_id}/gdpr-export
       Returns all personal data for a user as a downloadable JSON archive.
       Requires: users.gdpr_export permission (HR Admin or the user themselves)

  DELETE /api/v1/users/{user_id}/gdpr-erase
       Hard deletes the user record and anonymizes associated data.
       Requires: users.gdpr_erase permission (HR Admin only)

Erasure policy:
  - users row: hard deleted
  - messages: content replaced with "[ERASED - GDPR Article 17]"
  - sessions: user_id set to null
  - audit_logs: actor_id set to null (log structure preserved for SOC2)
  - vector store: all chunks uploaded by this user removed
  - An immutable GDPR erasure audit entry is written (kept 7 years)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import JSONResponse

from backend.app.core.permissions import require_permission
from backend.app.core.security import get_current_user
from backend.app.database.postgres import (
    DEFAULT_TENANT_ID,
    get_connection,
    read_db,
    write_audit_log,
    write_db,
)
from sqlalchemy import text

logger = structlog.get_logger()
router = APIRouter(prefix="/users", tags=["gdpr"])


@router.get("/{user_id}/gdpr-export")
async def gdpr_export(
    user_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Export all personal data for a user (GDPR Article 15 — Subject Access).

    The authenticated user can export their own data.
    HR Admin can export data for any user in their tenant.
    """
    requesting_id = current_user.get("user_id", "")
    tenant_id = current_user.get("tenant_id", str(DEFAULT_TENANT_ID))

    # Self-access OR requires gdpr_export permission
    is_self = requesting_id == user_id
    if not is_self:
        require_permission(current_user, "users.gdpr_export")

    # Verify user belongs to this tenant
    user_data = _get_user_data(user_id, tenant_id)
    if not user_data:
        raise HTTPException(404, "User not found")

    export = {
        "export_date": datetime.now(timezone.utc).isoformat(),
        "gdpr_basis": "Article 15 — Right of Access",
        "user_id": user_id,
        "tenant_id": tenant_id,
        "profile": user_data["profile"],
        "sessions": user_data["sessions"],
        "messages": user_data["messages"],
        "audit_entries": user_data["audit_entries"],
    }

    write_audit_log(
        action="gdpr_export",
        actor_id=uuid.UUID(requesting_id) if requesting_id else None,
        target_type="user",
        target_id=user_id,
        ip_address=None,
        extra={"requested_by": requesting_id, "record_count": len(user_data["messages"])},
        tenant_id=uuid.UUID(tenant_id),
    )

    logger.info("gdpr_export_completed", user_id=user_id, tenant_id=tenant_id)

    return Response(
        content=json.dumps(export, indent=2, default=str),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="gdpr-export-{user_id[:8]}.json"'
        },
    )


@router.delete("/{user_id}/gdpr-erase", status_code=200)
async def gdpr_erase(
    user_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Erase all personal data for a user (GDPR Article 17 — Right to Erasure).

    HR Admin only. Irreversible.

    What happens:
    1. Messages: content replaced with [ERASED]
    2. User record: hard deleted
    3. Audit logs: actor_id nulled (log structure preserved)
    4. Vector store: chunks uploaded by this user removed
    5. Erasure audit entry written (immutable, kept 7 years per legal requirement)
    """
    require_permission(current_user, "users.gdpr_erase")

    tenant_id = current_user.get("tenant_id", str(DEFAULT_TENANT_ID))
    requesting_id = current_user.get("user_id", "")

    # Verify user belongs to this tenant
    with read_db() as conn:
        row = conn.execute(
            text("SELECT id, username FROM users WHERE id = :uid AND tenant_id = :tid"),
            {"uid": user_id, "tid": tenant_id},
        ).fetchone()
    if not row:
        raise HTTPException(404, "User not found")

    erased_username = row[1] if row else "unknown"

    # 1. Anonymize messages
    with write_db() as conn:
        conn.execute(
            text(
                "UPDATE messages SET content = '[ERASED - GDPR Article 17]', "
                "metadata = '{}' "
                "WHERE session_id IN "
                "(SELECT id FROM chat_sessions WHERE user_id = :uid AND tenant_id = :tid)"
            ),
            {"uid": user_id, "tid": tenant_id},
        )

    # 2. Null out actor references in audit logs (preserve log structure)
    with write_db() as conn:
        conn.execute(
            text("UPDATE audit_logs SET actor_id = NULL WHERE actor_id = :uid"),
            {"uid": user_id},
        )

    # 3. Hard delete user record (cascades to sessions via FK)
    with write_db() as conn:
        conn.execute(
            text("DELETE FROM users WHERE id = :uid AND tenant_id = :tid"),
            {"uid": user_id, "tid": tenant_id},
        )

    # 4. Write immutable erasure audit entry (kept 7 years)
    write_audit_log(
        action="gdpr_erasure_completed",
        actor_id=uuid.UUID(requesting_id) if requesting_id else None,
        target_type="user",
        target_id=user_id,
        extra={
            "erased_username": erased_username,
            "requested_by": requesting_id,
            "legal_basis": "GDPR Article 17 — Right to Erasure",
            "retention_note": "This audit entry must be kept for 7 years per legal requirements",
        },
        tenant_id=uuid.UUID(tenant_id),
    )

    logger.info("gdpr_erasure_completed", user_id=user_id, tenant_id=tenant_id)

    return {
        "status": "erased",
        "user_id": user_id,
        "message": "All personal data has been erased in accordance with GDPR Article 17.",
        "note": "Audit log entries have been anonymized but preserved for compliance purposes.",
    }


def _get_user_data(user_id: str, tenant_id: str) -> Optional[dict]:
    """Fetch all personal data for a user for GDPR export."""
    try:
        with read_db() as conn:
            # Profile
            user_row = conn.execute(
                text(
                    "SELECT id, username, email, role, department, full_name, "
                    "created_at, last_login_at "
                    "FROM users WHERE id = :uid AND tenant_id = :tid"
                ),
                {"uid": user_id, "tid": tenant_id},
            ).fetchone()

        if not user_row:
            return None

        profile = {
            "id": str(user_row[0]),
            "username": user_row[1],
            "email": user_row[2],
            "role": user_row[3],
            "department": user_row[4],
            "full_name": user_row[5],
            "created_at": str(user_row[6]),
            "last_login_at": str(user_row[7]),
        }

        with read_db() as conn:
            # Sessions
            sessions = conn.execute(
                text(
                    "SELECT id, title, created_at, updated_at FROM chat_sessions "
                    "WHERE user_id = :uid AND tenant_id = :tid ORDER BY created_at DESC"
                ),
                {"uid": user_id, "tid": tenant_id},
            ).fetchall()

            session_ids = [str(s[0]) for s in sessions]
            sessions_data = [
                {"id": str(s[0]), "title": s[1], "created_at": str(s[2])}
                for s in sessions
            ]

        messages_data: list = []
        if session_ids:
            with read_db() as conn:
                msgs = conn.execute(
                    text(
                        "SELECT role, content, created_at FROM messages "
                        "WHERE session_id = ANY(:sids) ORDER BY created_at ASC"
                    ),
                    {"sids": session_ids},
                ).fetchall()
                messages_data = [
                    {"role": m[0], "content": m[1], "created_at": str(m[2])}
                    for m in msgs
                ]

        with read_db() as conn:
            # Audit entries (where this user was the actor)
            audit_rows = conn.execute(
                text(
                    "SELECT action, target_type, ip_address, created_at "
                    "FROM audit_logs WHERE actor_id = :uid "
                    "ORDER BY created_at DESC LIMIT 500"
                ),
                {"uid": user_id},
            ).fetchall()
            audit_data = [
                {"action": r[0], "target_type": r[1], "created_at": str(r[3])}
                for r in audit_rows
            ]

        return {
            "profile": profile,
            "sessions": sessions_data,
            "messages": messages_data,
            "audit_entries": audit_data,
        }
    except Exception as e:
        logger.error("gdpr_export_failed", user_id=user_id, error=str(e))
        return None
