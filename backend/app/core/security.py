"""JWT authentication and RBAC — Sections 13 & 17."""

from __future__ import annotations

import hashlib
import re
import sqlite3
import time
import uuid

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
import bcrypt as _bcrypt

from backend.app.core.config import get_settings
from backend.app.models.chat_models import User

logger = structlog.get_logger("audit")
security_scheme = HTTPBearer()

# ── Role hierarchy (Section 13.1) ────────────────────────────────────────────
ROLE_HIERARCHY: dict[str, list[str]] = {
    "employee": ["employee"],
    "manager": ["employee", "manager"],
    "hr_admin": ["employee", "manager", "hr_admin"],
}

# ── Prompt injection patterns (Section 17.2) ────────────────────────────────
INJECTION_PATTERNS = [
    r"ignore\s+(previous|above|all)\s+(instructions|rules|prompts)",
    r"you\s+are\s+now\s+a",
    r"pretend\s+(to\s+be|you\s+are)",
    r"system\s*prompt",
    r"<\s*/?\s*system\s*>",
    r"\\n\\nHuman:",
    r"forget\s+(everything|all|your\s+instructions)",
    r"jailbreak",
    r"DAN\s+mode",
    r"override\s+(instructions|rules|safety)",
    r"act\s+as\s+(if|though)",
    r"new\s+instructions",
    r"disregard\s+(all|previous|above)",
    r"reveal\s+(your|the)\s+(prompt|instructions|system)",
    r"output\s+(the|your)\s+(system|initial)\s+prompt",
    r"\{.*system.*\}",  # JSON-style injection attempts
    r"<\|.*\|>",  # special token injection
    # BUG-002: prompt leakage attempts
    r"what\s+are\s+your\s+(instructions|rules|guidelines|directives)",
    r"repeat\s+(your|the)\s+(system|initial|original)\s*(prompt|instructions|message)",
    r"show\s+me\s+your\s+(prompt|instructions|rules)",
    r"print\s+your\s+(system|initial)\s*(prompt|message)",
]


# ── JWT helpers ──────────────────────────────────────────────────────────────
_JWT_ISSUER = "hr-rag-chatbot"
_JWT_AUDIENCE = "hr-rag-chatbot-api"


# ── Token revocation blocklist (in-memory; use Redis in production) ──────────
# Maps jti -> expiry_timestamp so we can prune naturally-expired entries
_revoked_tokens: dict[str, float] = {}


def revoke_token(jti: str, expiry: float) -> None:
    """Add a token's jti to the revocation blocklist."""
    _revoked_tokens[jti] = expiry


def is_token_revoked(jti: str) -> bool:
    """Return True if jti is in blocklist and the token hasn't naturally expired."""
    if jti not in _revoked_tokens:
        return False
    if time.time() > _revoked_tokens[jti]:
        # Token expired anyway — clean up and treat as not revoked (expired wins)
        del _revoked_tokens[jti]
        return False
    return True


def create_access_token(user_id: str, role: str, department: Optional[str] = None) -> str:
    s = get_settings()
    now = int(time.time())
    payload = {
        "sub": user_id,
        "role": role,
        "department": department,
        "exp": now + s.access_token_expire_minutes * 60,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "iss": _JWT_ISSUER,
        "aud": _JWT_AUDIENCE,
    }
    return jwt.encode(payload, s.jwt_secret_key, algorithm=s.jwt_algorithm)


# ── Refresh tokens (SECTION 11) ─────────────────────────────────────────────
REFRESH_TOKEN_EXPIRY_HOURS = 168  # 7 days


def create_refresh_token(user_id: str) -> str:
    """Create an opaque refresh token, stored server-side in the database."""
    s = get_settings()
    token = str(uuid.uuid4())
    now = time.time()
    expires_at = now + REFRESH_TOKEN_EXPIRY_HOURS * 3600
    with sqlite3.connect(s.db_path) as con:
        con.execute(
            "INSERT INTO refresh_tokens (token, user_id, expires_at, revoked, created_at) "
            "VALUES (?,?,?,0,?)",
            (token, user_id, expires_at, now),
        )
    return token


def validate_refresh_token(token: str) -> Optional[str]:
    """Validate a refresh token. Returns user_id if valid, None otherwise."""
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT user_id, expires_at, revoked FROM refresh_tokens WHERE token=?",
            (token,),
        ).fetchone()
    if not row:
        return None
    user_id, expires_at, revoked = row
    if revoked or time.time() > expires_at:
        return None
    return user_id


def revoke_refresh_token(token: str) -> None:
    """Mark a refresh token as revoked."""
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        con.execute("UPDATE refresh_tokens SET revoked=1 WHERE token=?", (token,))


def revoke_all_user_refresh_tokens(user_id: str) -> None:
    """Revoke all refresh tokens for a user (e.g., on password change)."""
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        con.execute("UPDATE refresh_tokens SET revoked=1 WHERE user_id=?", (user_id,))


def decode_token(token: str) -> dict:
    s = get_settings()
    try:
        return jwt.decode(token, s.jwt_secret_key, algorithms=[s.jwt_algorithm],
                          issuer=_JWT_ISSUER, audience=_JWT_AUDIENCE)
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}") from exc


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> User:
    s = get_settings()
    try:
        payload = jwt.decode(creds.credentials, s.jwt_secret_key, algorithms=[s.jwt_algorithm],
                             issuer=_JWT_ISSUER, audience=_JWT_AUDIENCE)
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except JWTError:
        raise HTTPException(401, "Invalid token")

    # PHASE 9: Check revocation blocklist
    jti = payload.get("jti", "")
    if jti and is_token_revoked(jti):
        raise HTTPException(401, "Token has been revoked")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(401, "Invalid token: missing subject")

    # PHASE 2: Load role from database — never trust JWT role claim
    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT role, department FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
    if not row:
        raise HTTPException(401, "User not found")

    return User(user_id=user_id, role=row[0], department=row[1])


# ── API Key authentication (service-to-service) ─────────────────────────────
def verify_api_key(api_key: str) -> bool:
    """Validate an API key for service-to-service calls."""
    s = get_settings()
    if not s.api_keys:
        return False
    valid_keys = {k.strip() for k in s.api_keys.split(",") if k.strip()}
    return api_key in valid_keys


# ── RBAC helpers ─────────────────────────────────────────────────────────────
def get_allowed_roles(user_role: str) -> list[str]:
    return ROLE_HIERARCHY.get(user_role, ["employee"])


def can_access_document(user_role: str, doc_roles: list[str]) -> bool:
    return bool(set(get_allowed_roles(user_role)) & set(doc_roles))


def require_role(user: User, minimum_role: str) -> None:
    order = {"employee": 0, "manager": 1, "hr_admin": 2}
    if order.get(user.role, 0) < order.get(minimum_role, 0):
        raise HTTPException(403, "Insufficient permissions")


# ── Password helpers ─────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ── Query sanitization ───────────────────────────────────────────────────────
def sanitize_query(query: str) -> str:
    """Strip potentially dangerous content from user queries."""
    # Remove HTML/script tags
    query = re.sub(r"<[^>]+>", "", query)
    # Remove null bytes
    query = query.replace("\x00", "")
    # Remove control characters (except newlines)
    query = re.sub(r"[\x01-\x09\x0b\x0c\x0e-\x1f\x7f]", "", query)
    # Collapse excessive whitespace
    query = re.sub(r"\s{3,}", " ", query)
    return query.strip()


# ── Prompt injection ─────────────────────────────────────────────────────────
def check_prompt_injection(query: str) -> bool:
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            logger.warning("prompt_injection_detected", pattern=pattern,
                           query_preview=query[:100])
            return True
    return False


# ── Audit logging ────────────────────────────────────────────────────────────
def log_access(user: User, query: str, chunks_accessed: list[str]) -> None:
    logger.info(
        "document_access",
        user_id=user.user_id,
        role=user.role,
        query_hash=hashlib.sha256(query.encode()).hexdigest()[:16],
        chunks_accessed=chunks_accessed,
        timestamp=time.time(),
    )


def log_document_upload(user: User, doc_id: str, category: str, filename: str) -> None:
    logger.info("document_upload", user_id=user.user_id, document_id=doc_id, category=category, filename=filename)


def log_admin_action(user: User, action: str, details: Optional[dict] = None) -> None:
    logger.info("admin_action", user_id=user.user_id, role=user.role, action=action,
                details=details or {}, timestamp=time.time())


def mask_pii(text: str) -> str:
    """Redact common PII patterns from text before logging/storage.

    Masks: email addresses, SSNs, phone numbers, credit card numbers.
    """
    # Email addresses
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL_REDACTED]", text)
    # SSN patterns (XXX-XX-XXXX)
    text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[SSN_REDACTED]", text)
    # Phone numbers (various formats)
    text = re.sub(r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "[PHONE_REDACTED]", text)
    # Credit card numbers (13-19 digits with optional separators)
    text = re.sub(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{1,7}\b", "[CC_REDACTED]", text)
    return text


def log_security_event(event_type: str, details: Optional[dict] = None, user_id: str = "",
                       ip_address: str = "") -> None:
    """Log security event to structured log AND database for audit trail."""
    import json as _json
    import sqlite3 as _sqlite3
    logger.warning("security_event", event_type=event_type, details=details or {},
                   user_id=user_id, ip=ip_address, timestamp=time.time())
    try:
        from backend.app.core.config import get_settings
        with _sqlite3.connect(get_settings().db_path) as con:
            con.execute(
                "INSERT INTO security_events (event_type,user_id,ip_address,details,timestamp) "
                "VALUES (?,?,?,?,?)",
                (event_type, user_id, ip_address, _json.dumps(details or {}), time.time()),
            )
    except Exception:
        pass  # Don't fail the request if audit logging fails
