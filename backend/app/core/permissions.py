"""Config-driven permission matrix — Phase 2 + Phase A (HR-OS roles).

Every API action maps to a named permission string.
Roles are granted sets of permissions.

Design hooks:
- Phase 3: Per-tenant permission overrides stored in tenants.config
- Adding a new permission = one dict entry, no code search required
- Audit log records permission name checked, not just role

Phase A adds hr_team and hr_head roles (additive — existing roles preserved):
- admin (alias: super_admin) — full system control
- hr_head (alias: hr_admin) — HR department head, approves hr_team & documents
- hr_team — HR staff, uploads documents, manages employees
- employee — self-service only
"""

from __future__ import annotations

# ── Permission strings ────────────────────────────────────────────────────────
# Format: "<resource>.<action>"

PERMISSIONS = {
    # Chat
    "chat.query": "Send a chat message",
    "chat.view_own_sessions": "View own session history",
    "chat.view_team_sessions": "View team session summaries (manager/hr_team)",

    # Documents
    "documents.read": "Read/search documents",
    "documents.upload": "Upload new documents",
    "documents.delete": "Delete documents",
    "documents.reindex": "Reindex document chunks",
    "documents.view_versions": "View document version history",
    "documents.approve": "Approve/reject uploaded documents",

    # Users
    "users.view_self": "View own profile",
    "users.view_all": "View all users in org",
    "users.create": "Create a user directly (no approval flow)",
    "users.approve": "Approve/reject pending registrations",
    "users.suspend": "Suspend/unsuspend users",
    "users.change_role": "Change user role",
    "users.delete": "Permanently delete a user",
    "users.gdpr_export": "Export user data (GDPR Article 20)",
    "users.gdpr_erase": "Erase user data (GDPR Article 17)",

    # Tickets (Phase A — defined now, enforced in Phase B)
    "tickets.create": "Create a new ticket",
    "tickets.view_own": "View own tickets",
    "tickets.view_all": "View all tickets",
    "tickets.assign": "Assign tickets to HR team members",
    "tickets.resolve": "Resolve/close tickets",

    # Complaints (Phase A — defined now, enforced in Phase D)
    "complaints.submit": "Submit anonymous complaint",
    "complaints.view": "View complaints (HR Head only)",

    # Notifications
    "notifications.view_own": "View own notifications",
    "notifications.send": "Send notifications to users",

    # Admin
    "admin.view_metrics": "View system analytics",
    "admin.view_audit_logs": "View audit trail",
    "admin.view_failed_queries": "View failed/low-confidence queries",
    "admin.clear_cache": "Clear semantic response cache",
    "admin.manage_jobs": "View and retry background jobs",
    "admin.manage_branches": "Manage organization branches",

    # Tenant (Phase 3 — defined now, enforced later)
    "tenant.provision": "Create new tenant organizations",
    "tenant.configure": "Update tenant configuration",
    "tenant.deactivate": "Deactivate a tenant",
}

# ── Role → Permission grants ──────────────────────────────────────────────────

ROLE_PERMISSIONS: dict[str, set[str]] = {
    # admin (formerly super_admin) — all permissions
    "super_admin": set(PERMISSIONS.keys()),
    "admin": set(PERMISSIONS.keys()),

    # hr_head (formerly hr_admin) — HR department head
    "hr_head": {
        "chat.query",
        "chat.view_own_sessions",
        "chat.view_team_sessions",
        "documents.read",
        "documents.upload",
        "documents.delete",
        "documents.reindex",
        "documents.view_versions",
        "documents.approve",
        "users.view_self",
        "users.view_all",
        "users.create",
        "users.approve",
        "users.suspend",
        "users.change_role",
        "users.gdpr_export",
        "users.gdpr_erase",
        "tickets.view_all",
        "tickets.assign",
        "tickets.resolve",
        "complaints.view",
        "notifications.view_own",
        "notifications.send",
        "admin.view_metrics",
        "admin.view_audit_logs",
        "admin.view_failed_queries",
        "admin.clear_cache",
        "admin.manage_jobs",
    },
    "hr_admin": {  # Backward-compatible alias for hr_head
        "chat.query",
        "chat.view_own_sessions",
        "chat.view_team_sessions",
        "documents.read",
        "documents.upload",
        "documents.delete",
        "documents.reindex",
        "documents.view_versions",
        "documents.approve",
        "users.view_self",
        "users.view_all",
        "users.create",
        "users.approve",
        "users.suspend",
        "users.change_role",
        "users.gdpr_export",
        "users.gdpr_erase",
        "tickets.view_all",
        "tickets.assign",
        "tickets.resolve",
        "complaints.view",
        "notifications.view_own",
        "notifications.send",
        "admin.view_metrics",
        "admin.view_audit_logs",
        "admin.view_failed_queries",
        "admin.clear_cache",
        "admin.manage_jobs",
    },

    # hr_team — HR staff (new in Phase A)
    "hr_team": {
        "chat.query",
        "chat.view_own_sessions",
        "chat.view_team_sessions",
        "documents.read",
        "documents.upload",
        "documents.view_versions",
        "users.view_self",
        "users.view_all",
        "tickets.create",
        "tickets.view_all",
        "tickets.resolve",
        "notifications.view_own",
        "notifications.send",
    },

    # manager (preserved for backward compatibility)
    "manager": {
        "chat.query",
        "chat.view_own_sessions",
        "chat.view_team_sessions",
        "documents.read",
        "users.view_self",
        "tickets.create",
        "tickets.view_own",
        "notifications.view_own",
    },

    "employee": {
        "chat.query",
        "chat.view_own_sessions",
        "documents.read",
        "users.view_self",
        "users.gdpr_export",
        "users.gdpr_erase",
        "tickets.create",
        "tickets.view_own",
        "complaints.submit",
        "notifications.view_own",
    },
}

# ── Role hierarchy (for require_role checks) ──────────────────────────────────
# A role inherits all permissions of roles below it in the hierarchy.
# Phase A: additive — new roles coexist with legacy roles.
ROLE_HIERARCHY: dict[str, int] = {
    "super_admin": 100,
    "admin": 100,       # Alias for super_admin
    "hr_admin": 50,     # Backward-compatible alias for hr_head
    "hr_head": 50,
    "hr_team": 30,
    "manager": 20,
    "employee": 10,
}

ALL_ROLES = list(ROLE_HIERARCHY.keys())
VALID_ROLES = set(ALL_ROLES)

# Roles available for self-registration (subset — admin/hr_head assigned by approvers)
SELF_REGISTER_ROLES = {"employee", "hr_team"}

# Mapping from new role names to legacy names (for backward compatibility)
ROLE_ALIASES: dict[str, str] = {
    "admin": "super_admin",
    "hr_head": "hr_admin",
}

# Approval chain: who can approve whom
# employee/hr_team registrations → hr_head (or admin) approves
# hr_head registrations → admin approves
APPROVAL_CHAIN: dict[str, set[str]] = {
    "employee": {"hr_head", "hr_admin", "admin", "super_admin"},
    "hr_team": {"hr_head", "hr_admin", "admin", "super_admin"},
    "hr_head": {"admin", "super_admin"},
    "manager": {"hr_head", "hr_admin", "admin", "super_admin"},
}


# ── Public API ────────────────────────────────────────────────────────────────

def has_permission(role: str, permission: str) -> bool:
    """Check if a role has a specific named permission."""
    if role not in ROLE_PERMISSIONS:
        return False
    return permission in ROLE_PERMISSIONS[role]


def get_role_level(role: str) -> int:
    """Numeric level of a role — higher = more powerful."""
    return ROLE_HIERARCHY.get(role, 0)


def role_at_least(user_role: str, required_role: str) -> bool:
    """True if user_role is equal to or more powerful than required_role."""
    return get_role_level(user_role) >= get_role_level(required_role)


def get_permissions_for_role(role: str) -> set[str]:
    """All permissions granted to a role."""
    return ROLE_PERMISSIONS.get(role, set()).copy()


def require_permission(user_role: str, permission: str) -> bool:
    """
    Returns True if allowed.
    Raises ValueError if permission string is unknown (catches typos early).
    """
    if permission not in PERMISSIONS:
        raise ValueError(f"Unknown permission: '{permission}'. Add it to PERMISSIONS dict first.")
    return has_permission(user_role, permission)
