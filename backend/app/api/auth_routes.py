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
    role: str = "employee"
    department: Optional[str] = None


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
            "SELECT user_id,hashed_password,role,department,status,suspended FROM users WHERE username=?",
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
            "user": {"user_id": row[0], "role": row[2], "department": row[3]}}


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
    # All new registrations are pending_approval — admin must approve
    role = "employee"
    status = "pending_approval"
    verification_token = str(uuid.uuid4())
    # Sanitize profile fields
    import html as _html
    full_name = _html.escape(req.full_name.strip(), quote=True)[:100]
    email = req.email.strip()[:254]
    phone = req.phone.strip()[:20]
    try:
        with sqlite3.connect(s.db_path) as con:
            con.execute(
                "INSERT INTO users (user_id,username,hashed_password,role,department,created_at,"
                "full_name,email,phone,status,verification_token) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (uid, username, hash_password(req.password), role, req.department, time.time(),
                 full_name, email, phone, status, verification_token))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Username already exists")
    log_security_event("user_registered", {"username": username, "status": status}, user_id=uid)
    return {
        "user_id": uid, "username": username, "role": role, "status": status,
        "message": "Registration successful. Your account is pending admin approval.",
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
