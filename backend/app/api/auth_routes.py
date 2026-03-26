"""Authentication endpoints — Section 20.4."""


import html
import re
import sqlite3
import time
import uuid
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Depends
from pydantic import BaseModel

from backend.app.core.config import get_settings
from backend.app.core.security import (
    create_access_token, create_refresh_token, decode_token, hash_password,
    log_security_event, revoke_all_user_refresh_tokens, revoke_refresh_token,
    revoke_token, validate_refresh_token, verify_password,
)

import structlog

logger = structlog.get_logger("audit")
router = APIRouter(prefix="/auth", tags=["auth"])

MIN_USERNAME_LENGTH = 3
MIN_PASSWORD_LENGTH = 12

# ── Login rate limiting + account lockout ────────────────────────────────────
_login_attempts: dict[str, list[float]] = defaultdict(list)
_account_lockouts: dict[str, float] = {}  # username -> lockout_until timestamp
MAX_LOGIN_ATTEMPTS_PER_IP = 5
LOGIN_WINDOW_SECONDS = 60
MAX_FAILED_PER_ACCOUNT = 10
ACCOUNT_LOCKOUT_SECONDS = 900  # 15 minutes

# Registration rate limiting: 3 registrations per IP per hour
_registration_attempts: dict[str, list[float]] = defaultdict(list)
MAX_REGISTRATIONS_PER_IP = 3
REGISTRATION_WINDOW_SECONDS = 3600


def _check_rate_limit(client_ip: str, username: str) -> None:
    """Enforce IP rate limiting + account lockout after repeated failures."""
    now = time.time()

    # Account lockout check
    lockout_until = _account_lockouts.get(username, 0)
    if now < lockout_until:
        remaining = int(lockout_until - now)
        logger.warning("account_locked", username=username, remaining_seconds=remaining)
        raise HTTPException(423, f"Account temporarily locked. Try again in {remaining} seconds.")

    # IP rate limiting
    attempts = _login_attempts[client_ip]
    _login_attempts[client_ip] = [t for t in attempts if now - t < LOGIN_WINDOW_SECONDS]
    if len(_login_attempts[client_ip]) >= MAX_LOGIN_ATTEMPTS_PER_IP:
        logger.warning("login_rate_limited", ip=client_ip, attempts=len(_login_attempts[client_ip]))
        raise HTTPException(429, "Too many login attempts. Please wait before trying again.")
    _login_attempts[client_ip].append(now)


def _record_failed_login(username: str) -> None:
    """Track failed logins per account; lock after MAX_FAILED_PER_ACCOUNT."""
    key = f"__account__{username}"
    now = time.time()
    _login_attempts[key] = [t for t in _login_attempts.get(key, []) if now - t < 3600]
    _login_attempts[key].append(now)
    if len(_login_attempts[key]) >= MAX_FAILED_PER_ACCOUNT:
        _account_lockouts[username] = now + ACCOUNT_LOCKOUT_SECONDS
        logger.warning("account_lockout_triggered", username=username, duration_s=ACCOUNT_LOCKOUT_SECONDS)
        log_security_event("account_lockout", {"username": username, "failed_attempts": len(_login_attempts[key])})


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    full_name: str = ""
    email: str = ""
    phone: str = ""
    role: str = "employee"  # Requested role — validated against SELF_REGISTER_ROLES
    department: Optional[str] = None
    secret_question: str = ""
    secret_answer: str = ""


def _validate_username(username: str) -> str:
    """Validate, sanitize, and normalize username."""
    username = username.strip()
    if not username or len(username) < MIN_USERNAME_LENGTH:
        raise HTTPException(400, f"Username must be at least {MIN_USERNAME_LENGTH} characters")
    # BUG-003/XSS: Escape HTML entities to prevent stored XSS
    username = html.escape(username, quote=True)
    # Only allow alphanumeric, underscores, hyphens, dots
    if not re.match(r"^[a-zA-Z0-9._-]+$", username):
        raise HTTPException(400, "Username may only contain letters, numbers, dots, hyphens, and underscores")
    return username


def _validate_password(password: str) -> None:
    """Validate password strength — enterprise policy."""
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(400, f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if not re.search(r"[a-zA-Z]", password):
        raise HTTPException(400, "Password must contain at least one letter")
    if not re.search(r"[0-9]", password):
        raise HTTPException(400, "Password must contain at least one number")
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?~`]", password):
        raise HTTPException(400, "Password must contain at least one special character")


@router.post("/login")
async def login(req: LoginRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    username = req.username.strip()
    if not username:
        raise HTTPException(400, "Username cannot be empty")
    if not req.password:
        raise HTTPException(400, "Password cannot be empty")

    # Rate limiting + account lockout
    _check_rate_limit(client_ip, username)

    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT user_id,hashed_password,role,department,status,suspended,"
            "COALESCE(full_name,''),username FROM users WHERE username=?",
            (username,)
        ).fetchone()
    if not row or not verify_password(req.password, row[1]):
        _record_failed_login(username)
        logger.warning("login_failed", username=username, ip=client_ip)
        raise HTTPException(401, "Invalid credentials")

    # Check account status
    user_status = row[4] if len(row) > 4 else "active"
    is_suspended = row[5] if len(row) > 5 else 0
    if is_suspended:
        raise HTTPException(403, "Your account has been suspended. Please contact HR.")
    if user_status == "pending_approval":
        raise HTTPException(403, "Your account is pending admin approval. Please wait for an administrator to approve your registration.")

    logger.info("login_success", user_id=row[0], role=row[2], ip=client_ip)
    token = create_access_token(row[0], row[2], row[3])
    refresh = create_refresh_token(row[0])
    return {"access_token": token, "refresh_token": refresh, "token_type": "bearer",
            "expires_in": s.access_token_expire_minutes * 60,
            "user": {"user_id": row[0], "role": row[2], "department": row[3],
                     "full_name": row[6], "username": row[7]}}


@router.get("/setup-status")
async def setup_status():
    """Check if any users exist — used by frontend to show bootstrap role options."""
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        count = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        has_admin = con.execute(
            "SELECT COUNT(*) FROM users WHERE role IN ('admin','super_admin')"
        ).fetchone()[0]
        has_hr_head = con.execute(
            "SELECT COUNT(*) FROM users WHERE role IN ('hr_head','hr_admin')"
        ).fetchone()[0]
    return {
        "has_users": count > 0,
        "has_admin": has_admin > 0,
        "has_hr_head": has_hr_head > 0,
    }


@router.post("/register", status_code=201)
async def register(req: RegisterRequest, request: Request):
    # Validate inputs first — don't count invalid attempts against rate limit
    username = _validate_username(req.username)
    _validate_password(req.password)

    # Registration rate limiting — prevent automated account creation
    # Only counted AFTER validation passes (invalid attempts don't create accounts)
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    _registration_attempts[client_ip] = [
        t for t in _registration_attempts[client_ip]
        if now - t < REGISTRATION_WINDOW_SECONDS
    ]
    if len(_registration_attempts[client_ip]) >= MAX_REGISTRATIONS_PER_IP:
        log_security_event("registration_rate_limited", {"ip": client_ip}, ip_address=client_ip)
        raise HTTPException(429, "Too many registration attempts. Please try again later.")
    _registration_attempts[client_ip].append(now)

    s = get_settings()
    uid = str(uuid.uuid4())

    # Bootstrap mode: when no users exist, allow admin/hr_head self-registration
    with sqlite3.connect(s.db_path) as con:
        user_count = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        admin_count = con.execute(
            "SELECT COUNT(*) FROM users WHERE role IN ('admin','super_admin')"
        ).fetchone()[0]
        hr_head_count = con.execute(
            "SELECT COUNT(*) FROM users WHERE role IN ('hr_head','hr_admin')"
        ).fetchone()[0]

    from backend.app.core.permissions import SELF_REGISTER_ROLES
    requested_role = req.role.strip().lower() if req.role else "employee"

    # Bootstrap roles allowed only when those roles don't exist yet
    bootstrap_roles = set()
    if admin_count == 0:
        bootstrap_roles.add("admin")
    if hr_head_count == 0:
        bootstrap_roles.add("hr_head")

    allowed_roles = SELF_REGISTER_ROLES | bootstrap_roles
    if requested_role not in allowed_roles:
        requested_role = "employee"  # Fallback

    # Bootstrap users get auto-approved with their requested role
    is_bootstrap = requested_role in bootstrap_roles
    role = requested_role if is_bootstrap else "employee"
    status = "active" if is_bootstrap else "pending_approval"
    verification_token = str(uuid.uuid4())
    # Sanitize profile fields
    import html as _html
    full_name = _html.escape(req.full_name.strip(), quote=True)[:100]
    email = req.email.strip()[:254]
    phone = req.phone.strip()[:20]
    # Hash secret answer (like password — never store plain text)
    secret_q = _html.escape(req.secret_question.strip(), quote=True)[:200] if req.secret_question else ""
    secret_a_hash = hash_password(req.secret_answer.strip().lower()) if req.secret_answer.strip() else ""

    try:
        with sqlite3.connect(s.db_path) as con:
            con.execute(
                "INSERT INTO users (user_id,username,hashed_password,role,department,created_at,"
                "full_name,email,phone,status,verification_token,requested_role,"
                "secret_question,secret_answer_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (uid, username, hash_password(req.password), role, req.department, time.time(),
                 full_name, email, phone, status, verification_token, requested_role,
                 secret_q, secret_a_hash))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Username already exists")
    log_security_event("user_registered", {
        "username": username, "status": status, "requested_role": requested_role,
        "bootstrap": is_bootstrap,
    }, user_id=uid)
    msg = (
        f"Registration successful. You are now the {requested_role.replace('_', ' ')}. You can log in immediately."
        if is_bootstrap
        else "Registration successful. Your account is pending approval."
    )
    return {
        "user_id": uid, "username": username, "role": role,
        "requested_role": requested_role, "status": status,
        "message": msg,
    }


_logout_bearer = HTTPBearer(auto_error=False)


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None


@router.post("/logout")
async def logout(
    body: Optional[LogoutRequest] = None,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_logout_bearer),
):
    """Revoke the access token AND optional refresh token."""
    if not creds:
        raise HTTPException(400, "No token provided")
    try:
        payload = decode_token(creds.credentials)
    except HTTPException:
        # Token already invalid — treat as successful logout
        return {"status": "logged_out"}
    jti = payload.get("jti")
    exp = payload.get("exp", 0)
    user_id = payload.get("sub", "unknown")
    if jti:
        revoke_token(jti, float(exp))
    # Revoke refresh token if provided, otherwise revoke all for this user
    if body and body.refresh_token:
        revoke_refresh_token(body.refresh_token)
    else:
        revoke_all_user_refresh_tokens(user_id)
    logger.info("logout", user_id=user_id)
    return {"status": "logged_out"}


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh")
async def refresh(req: RefreshRequest):
    """Exchange a valid refresh token for a new access token."""
    user_id = validate_refresh_token(req.refresh_token)
    if not user_id:
        raise HTTPException(401, "Invalid or expired refresh token")
    # Load current role from DB (never cache stale role)
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute("SELECT role, department FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(401, "User not found")
    # Rotate: revoke old refresh token, issue new pair
    revoke_refresh_token(req.refresh_token)
    new_access = create_access_token(user_id, row[0], row[1])
    new_refresh = create_refresh_token(user_id)
    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "expires_in": s.access_token_expire_minutes * 60,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2FA / TOTP (Phase B8)
# ══════════════════════════════════════════════════════════════════════════════

from backend.app.core.security import get_current_user
from backend.app.models.chat_models import User


class TOTPSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str


class TOTPVerifyRequest(BaseModel):
    code: str


@router.post("/2fa/setup", response_model=TOTPSetupResponse)
async def setup_2fa(user: User = Depends(get_current_user)):
    """Generate a TOTP secret and provisioning URI for authenticator app setup."""
    from backend.app.core.totp import is_available, generate_totp_secret, get_provisioning_uri
    if not is_available():
        raise HTTPException(501, "2FA not available — install pyotp: pip install pyotp")
    s = get_settings()
    # Check if already enabled
    with sqlite3.connect(s.db_path) as con:
        row = con.execute("SELECT totp_enabled, username FROM users WHERE user_id=?", (user.user_id,)).fetchone()
    if not row:
        raise HTTPException(404, "User not found")
    if row[0]:
        raise HTTPException(409, "2FA is already enabled for this account")
    secret = generate_totp_secret()
    uri = get_provisioning_uri(secret, row[1], s.company_name)
    # Store secret (not yet enabled until verified)
    with sqlite3.connect(s.db_path) as con:
        con.execute("UPDATE users SET totp_secret=? WHERE user_id=?", (secret, user.user_id))
    return TOTPSetupResponse(secret=secret, provisioning_uri=uri)


@router.post("/2fa/verify")
async def verify_and_enable_2fa(req: TOTPVerifyRequest, user: User = Depends(get_current_user)):
    """Verify a TOTP code to confirm setup and enable 2FA."""
    from backend.app.core.totp import verify_totp
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute("SELECT totp_secret FROM users WHERE user_id=?", (user.user_id,)).fetchone()
    if not row or not row[0]:
        raise HTTPException(400, "2FA setup not initiated — call /auth/2fa/setup first")
    if not verify_totp(row[0], req.code):
        raise HTTPException(401, "Invalid TOTP code")
    with sqlite3.connect(s.db_path) as con:
        con.execute("UPDATE users SET totp_enabled=1 WHERE user_id=?", (user.user_id,))
    log_security_event("2fa_enabled", {"user_id": user.user_id}, user_id=user.user_id)
    return {"status": "2fa_enabled"}


@router.delete("/2fa")
async def disable_2fa(req: TOTPVerifyRequest, user: User = Depends(get_current_user)):
    """Disable 2FA (requires valid TOTP code to confirm)."""
    from backend.app.core.totp import verify_totp
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute("SELECT totp_secret, totp_enabled FROM users WHERE user_id=?", (user.user_id,)).fetchone()
    if not row or not row[1]:
        raise HTTPException(400, "2FA is not enabled")
    if not verify_totp(row[0], req.code):
        raise HTTPException(401, "Invalid TOTP code")
    with sqlite3.connect(s.db_path) as con:
        con.execute("UPDATE users SET totp_enabled=0, totp_secret='' WHERE user_id=?", (user.user_id,))
    log_security_event("2fa_disabled", {"user_id": user.user_id}, user_id=user.user_id)
    return {"status": "2fa_disabled"}


# ── Phase 3: SSO / OIDC Login Flow ───────────────────────────────────────────

@router.get("/sso/login")
async def sso_login(request: Request, tenant: str = "default"):
    """Redirect to the tenant's configured IdP for SSO login.

    Query param `tenant` is the tenant slug (e.g., ?tenant=acme).
    The IdP will redirect back to /auth/sso/callback after authentication.
    """
    from backend.app.core.tenant import _lookup_tenant_by_slug
    result = _lookup_tenant_by_slug(tenant)
    if not result:
        raise HTTPException(404, f"Tenant '{tenant}' not found")

    tenant_id, config = result
    sso_config = config.get("sso", {})

    if not config.get("features", {}).get("sso", False):
        raise HTTPException(403, "SSO is not enabled for this organization. Contact your administrator.")
    if not sso_config.get("client_id"):
        raise HTTPException(503, "SSO is not configured for this organization. Contact your administrator.")

    from backend.app.core.sso import configure_sso, get_sso_client
    s = get_settings()
    configured = configure_sso(
        client_id=sso_config["client_id"],
        client_secret=sso_config.get("client_secret", ""),
        issuer_url=sso_config.get("issuer_url", ""),
        redirect_uri=sso_config.get("redirect_uri", f"{s.ollama_base_url.replace('11434', '8000')}/api/v1/auth/sso/callback"),
    )
    if not configured:
        raise HTTPException(503, "SSO client could not be initialized. Install authlib: pip install authlib")

    # Store tenant slug in session state for callback
    client = get_sso_client()
    redirect_uri = str(request.url_for("sso_callback"))
    # Pass tenant slug as state parameter (signed by OIDC flow)
    return await client.hr_sso.authorize_redirect(request, redirect_uri, state=tenant)


@router.get("/sso/callback", name="sso_callback")
async def sso_callback(request: Request):
    """Handle OIDC callback. Exchange code for tokens, provision user, issue JWT."""
    from backend.app.core.sso import get_sso_client
    import sqlite3 as _sqlite3, time as _time, uuid as _uuid

    client = get_sso_client()
    if not client:
        raise HTTPException(503, "SSO not configured")

    try:
        token = await client.hr_sso.authorize_access_token(request)
    except Exception as e:
        logger.error("sso_callback_failed", error=str(e))
        raise HTTPException(401, "SSO authentication failed. Please try again.")

    userinfo = token.get("userinfo", {})
    email = userinfo.get("email", "")
    name = userinfo.get("name", email.split("@")[0])
    tenant_slug = request.query_params.get("state", "default")

    if not email:
        raise HTTPException(401, "SSO provider did not return an email address")

    # Resolve tenant
    from backend.app.core.tenant import _lookup_tenant_by_slug
    result = _lookup_tenant_by_slug(tenant_slug)
    if not result:
        raise HTTPException(404, "Tenant not found")
    tenant_id, _ = result

    s = get_settings()

    # Auto-provision or match user by email
    with _sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT user_id, role, status FROM users WHERE email=? AND tenant_id=?",
            (email, tenant_slug),
        ).fetchone()

        if row:
            user_id, role, status = row
            if status == "suspended":
                raise HTTPException(403, "Your account has been suspended")
        else:
            # Auto-provision new SSO user as employee
            user_id = str(_uuid.uuid4())
            role = "employee"
            username = email.split("@")[0] + "_" + user_id[:6]
            con.execute(
                "INSERT INTO users (user_id,username,hashed_password,role,email,full_name,"
                "created_at,status,email_verified,tenant_id) VALUES (?,?,?,?,?,?,?,'active',1,?)",
                (user_id, username, "sso-auth", role, email, name, _time.time(), tenant_slug),
            )
            logger.info("sso_user_provisioned", user_id=user_id, email=email, tenant=tenant_slug)

    from backend.app.core.security import create_access_token, create_refresh_token
    access_token = create_access_token({"sub": user_id, "role": role, "tenant_id": tenant_id})
    refresh_token = create_refresh_token(user_id)

    log_security_event("sso_login", {"email": email, "tenant": tenant_slug}, user_id=user_id)

    # Redirect to frontend with tokens in query params
    # Frontend reads tokens from URL and stores in localStorage
    frontend_url = f"http://localhost:3000/auth/sso/complete?access_token={access_token}&refresh_token={refresh_token}&tenant={tenant_slug}"
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=frontend_url)


# ── Forgot Password (Secret Question) ────────────────────────────────────────

# Rate limiting for forgot password attempts
_forgot_attempts: dict[str, list[float]] = defaultdict(list)
FORGOT_MAX_ATTEMPTS = 3
FORGOT_COOLDOWN_SECONDS = 300  # 5-minute cooldown after 3 failures


class ForgotPasswordRequest(BaseModel):
    username: str


class VerifySecretRequest(BaseModel):
    username: str
    secret_answer: str


class ResetPasswordRequest(BaseModel):
    username: str
    secret_answer: str
    new_password: str


@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, request: Request):
    """Step 1: Get the secret question for a username."""
    username = req.username.strip()
    if not username:
        raise HTTPException(400, "Username is required")

    client_ip = request.client.host if request.client else "unknown"
    key = f"forgot:{client_ip}"
    now = time.time()

    # Rate limiting
    _forgot_attempts[key] = [t for t in _forgot_attempts[key] if now - t < FORGOT_COOLDOWN_SECONDS]
    if len(_forgot_attempts[key]) >= FORGOT_MAX_ATTEMPTS:
        raise HTTPException(429, "Too many attempts. Please try again in 5 minutes.")

    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT secret_question FROM users WHERE username = ?", (username,)
        ).fetchone()

    if not row or not row[0]:
        # Don't reveal whether username exists — return generic message
        return {"has_question": False, "message": "No security question found. Please contact HR to reset your password."}

    return {"has_question": True, "secret_question": row[0]}


@router.post("/verify-secret")
async def verify_secret_answer(req: VerifySecretRequest, request: Request):
    """Step 2: Verify the secret answer."""
    username = req.username.strip()
    answer = req.secret_answer.strip().lower()

    if not username or not answer:
        raise HTTPException(400, "Username and answer are required")

    client_ip = request.client.host if request.client else "unknown"
    key = f"forgot:{client_ip}"
    now = time.time()

    # Rate limiting
    _forgot_attempts[key] = [t for t in _forgot_attempts[key] if now - t < FORGOT_COOLDOWN_SECONDS]
    if len(_forgot_attempts[key]) >= FORGOT_MAX_ATTEMPTS:
        raise HTTPException(429, "Too many attempts. Please try again in 5 minutes.")

    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT secret_answer_hash FROM users WHERE username = ?", (username,)
        ).fetchone()

    if not row or not row[0]:
        _forgot_attempts[key].append(now)
        raise HTTPException(400, "Verification failed. Please try again or contact HR.")

    if not verify_password(answer, row[0]):
        _forgot_attempts[key].append(now)
        remaining = FORGOT_MAX_ATTEMPTS - len(_forgot_attempts[key])
        log_security_event("forgot_password_failed", {"username": username, "remaining": remaining},
                           ip_address=client_ip)
        if remaining <= 0:
            raise HTTPException(429, "Too many failed attempts. Please try again in 5 minutes.")
        raise HTTPException(400, f"Incorrect answer. {remaining} attempt(s) remaining.")

    # Generate a short-lived reset token
    reset_token = str(uuid.uuid4())
    with sqlite3.connect(s.db_path) as con:
        con.execute(
            "UPDATE users SET verification_token = ? WHERE username = ?",
            (f"RESET:{reset_token}", username),
        )

    log_security_event("forgot_password_verified", {"username": username}, ip_address=client_ip)
    return {"verified": True, "reset_token": reset_token}


@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest, request: Request):
    """Step 3: Reset password after secret answer verification."""
    username = req.username.strip()
    answer = req.secret_answer.strip().lower()

    if not username or not answer or not req.new_password:
        raise HTTPException(400, "All fields are required")

    _validate_password(req.new_password)

    client_ip = request.client.host if request.client else "unknown"
    s = get_settings()

    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT user_id, secret_answer_hash FROM users WHERE username = ?", (username,)
        ).fetchone()

    if not row or not row[1]:
        raise HTTPException(400, "Password reset failed. Please try again.")

    # Re-verify the secret answer (defense in depth)
    if not verify_password(answer, row[1]):
        raise HTTPException(400, "Verification failed.")

    # Update password
    new_hash = hash_password(req.new_password)
    with sqlite3.connect(s.db_path) as con:
        con.execute(
            "UPDATE users SET hashed_password = ?, verification_token = '' WHERE username = ?",
            (new_hash, username),
        )

    # Revoke all existing tokens for security
    revoke_all_user_refresh_tokens(row[0])

    log_security_event("password_reset_success", {"username": username}, user_id=row[0], ip_address=client_ip)
    return {"status": "success", "message": "Password has been reset successfully. Please log in with your new password."}


@router.post("/change-password")
async def change_password_authenticated(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    """Change password for authenticated user (from Settings page)."""
    import json as _json
    body = _json.loads(await request.body())
    current_password = body.get("current_password", "")
    new_password = body.get("new_password", "")

    if not current_password or not new_password:
        raise HTTPException(400, "Current and new passwords are required")

    _validate_password(new_password)

    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        raise HTTPException(401, "Invalid token")

    user_id = payload.get("sub")
    s = get_settings()

    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT hashed_password FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()

    if not row or not verify_password(current_password, row[0]):
        raise HTTPException(400, "Current password is incorrect")

    new_hash = hash_password(new_password)
    with sqlite3.connect(s.db_path) as con:
        con.execute(
            "UPDATE users SET hashed_password = ? WHERE user_id = ?",
            (new_hash, user_id),
        )

    log_security_event("password_changed", {}, user_id=user_id)
    return {"status": "success", "message": "Password changed successfully."}


# ── Phase 2: Email OTP Password Reset ─────────────────────────────────────────

_otp_attempts: dict[str, list[float]] = defaultdict(list)
OTP_MAX_ATTEMPTS = 3
OTP_COOLDOWN_SECONDS = 300


class RequestOtpRequest(BaseModel):
    username: str


class VerifyOtpRequest(BaseModel):
    username: str
    otp_code: str


class ResetWithOtpRequest(BaseModel):
    username: str
    otp_code: str
    new_password: str


@router.get("/email-reset-available")
async def check_email_reset_available():
    """Check if email OTP reset is configured on this server."""
    from backend.app.services.email_service import is_email_configured
    return {"available": is_email_configured()}


@router.post("/request-otp")
async def request_email_otp(req: RequestOtpRequest, request: Request):
    """Send a 6-digit OTP to the user's registered email for password reset."""
    from backend.app.services.email_service import (
        is_email_configured, generate_otp, send_otp_email, store_otp,
    )

    if not is_email_configured():
        raise HTTPException(503, "Email reset is not configured on this server.")

    username = req.username.strip()
    if not username:
        raise HTTPException(400, "Username is required")

    client_ip = request.client.host if request.client else "unknown"
    key = f"otp:{client_ip}"
    now = time.time()

    # Rate limiting
    _otp_attempts[key] = [t for t in _otp_attempts[key] if now - t < OTP_COOLDOWN_SECONDS]
    if len(_otp_attempts[key]) >= OTP_MAX_ATTEMPTS:
        raise HTTPException(429, "Too many OTP requests. Please wait 5 minutes.")
    _otp_attempts[key].append(now)

    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT email FROM users WHERE username = ?", (username,)
        ).fetchone()

    # Always return success-like message to avoid revealing if username exists
    if not row or not row[0] or "@" not in row[0]:
        return {
            "sent": False,
            "message": "If an account with that username exists and has a verified email, a reset code has been sent.",
        }

    email = row[0]
    otp_code = generate_otp()

    # Store hashed OTP with expiry
    store_otp(s.db_path, username, otp_code)

    # Send email
    success = send_otp_email(email, otp_code, username)

    if not success:
        log_security_event("otp_email_send_failed", {"username": username}, ip_address=client_ip)
        raise HTTPException(500, "Failed to send email. Please try the security question method instead.")

    # Mask email for display: j***@company.com
    parts = email.split("@")
    masked = parts[0][0] + "***@" + parts[1] if len(parts) == 2 else "***"

    log_security_event("otp_requested", {"username": username, "email_masked": masked}, ip_address=client_ip)

    return {
        "sent": True,
        "email_masked": masked,
        "message": f"A 6-digit code has been sent to {masked}. It expires in 10 minutes.",
    }


@router.post("/verify-otp")
async def verify_email_otp(req: VerifyOtpRequest, request: Request):
    """Verify the OTP code sent via email."""
    from backend.app.services.email_service import verify_otp

    username = req.username.strip()
    otp = req.otp_code.strip()

    if not username or not otp:
        raise HTTPException(400, "Username and OTP code are required")

    if len(otp) != 6 or not otp.isdigit():
        raise HTTPException(400, "OTP must be a 6-digit number")

    client_ip = request.client.host if request.client else "unknown"
    key = f"otp_verify:{client_ip}"
    now = time.time()

    # Rate limiting on verification
    _otp_attempts[key] = [t for t in _otp_attempts[key] if now - t < OTP_COOLDOWN_SECONDS]
    if len(_otp_attempts[key]) >= OTP_MAX_ATTEMPTS:
        raise HTTPException(429, "Too many attempts. Please request a new code.")
    _otp_attempts[key].append(now)

    s = get_settings()
    if not verify_otp(s.db_path, username, otp):
        remaining = OTP_MAX_ATTEMPTS - len(_otp_attempts[key])
        log_security_event("otp_verify_failed", {"username": username, "remaining": remaining},
                           ip_address=client_ip)
        raise HTTPException(400, f"Invalid or expired code. {remaining} attempt(s) remaining.")

    log_security_event("otp_verified", {"username": username}, ip_address=client_ip)
    return {"verified": True}


@router.post("/reset-with-otp")
async def reset_password_with_otp(req: ResetWithOtpRequest, request: Request):
    """Reset password after OTP verification."""
    from backend.app.services.email_service import verify_otp, clear_otp

    username = req.username.strip()
    otp = req.otp_code.strip()

    if not username or not otp or not req.new_password:
        raise HTTPException(400, "All fields are required")

    _validate_password(req.new_password)

    client_ip = request.client.host if request.client else "unknown"
    s = get_settings()

    # Re-verify OTP (defense in depth)
    if not verify_otp(s.db_path, username, otp):
        raise HTTPException(400, "Invalid or expired OTP. Please request a new code.")

    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT user_id FROM users WHERE username = ?", (username,)
        ).fetchone()

    if not row:
        raise HTTPException(400, "Password reset failed.")

    # Update password and clear OTP
    new_hash = hash_password(req.new_password)
    with sqlite3.connect(s.db_path) as con:
        con.execute(
            "UPDATE users SET hashed_password = ? WHERE username = ?",
            (new_hash, username),
        )
    clear_otp(s.db_path, username)

    # Revoke all existing tokens
    revoke_all_user_refresh_tokens(row[0])

    log_security_event("password_reset_via_otp", {"username": username}, user_id=row[0], ip_address=client_ip)
    return {"status": "success", "message": "Password has been reset successfully. Please log in with your new password."}
