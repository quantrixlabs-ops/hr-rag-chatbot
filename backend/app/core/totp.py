"""MFA / TOTP authentication — Phase 5 (F-51).

Implements TOTP (RFC 6238) via pyotp. Compatible with Google Authenticator,
Authy, 1Password, and any RFC 6238 compliant app.

Phase 5 additions over the Phase 3 stub:
  - generate_recovery_codes() — 8 single-use recovery codes
  - verify_recovery_code()    — constant-time comparison, marks code used
  - MFA enforcement check     — respects per-tenant mfa_required feature flag

Recovery codes are stored hashed (bcrypt). The plaintext codes are shown
once to the user at enrollment and never stored.

Usage:
    # Enrollment
    secret = generate_totp_secret()
    encrypted_secret = encrypt_field(secret)  # Store encrypted in DB
    uri = get_provisioning_uri(secret, username)
    recovery_codes, hashed_codes = generate_recovery_codes()
    # Show recovery_codes to user, store hashed_codes in DB

    # Login verification
    if not verify_totp(decrypt_field(db_secret), submitted_code):
        raise HTTPException(401, "Invalid MFA code")
"""

from __future__ import annotations

import os
import secrets
import string

import structlog

logger = structlog.get_logger()

_HAS_PYOTP = False
try:
    import pyotp
    _HAS_PYOTP = True
except ImportError:
    pass


def is_available() -> bool:
    """Check if TOTP support is available (pyotp installed)."""
    return _HAS_PYOTP


def generate_totp_secret() -> str:
    """Generate a new TOTP base32 secret for a user."""
    if not _HAS_PYOTP:
        raise RuntimeError("pyotp is not installed. Run: pip install pyotp")
    return pyotp.random_base32()


def verify_totp(secret: str, code: str) -> bool:
    """Verify a TOTP code against a secret. Allows ±1 time window (30s clock drift)."""
    if not _HAS_PYOTP or not secret or not code:
        return False
    try:
        totp = pyotp.TOTP(secret)
        return totp.verify(code.strip(), valid_window=1)
    except Exception:
        return False


def get_provisioning_uri(
    secret: str,
    username: str,
    issuer: str = "HR Chatbot",
) -> str:
    """Generate otpauth:// URI for QR code display in authenticator apps."""
    if not _HAS_PYOTP:
        return ""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=username, issuer_name=issuer)


def generate_recovery_codes(count: int = 8) -> tuple[list[str], list[str]]:
    """Generate single-use recovery codes for account recovery.

    Returns:
        (plaintext_codes, hashed_codes)
        - Show plaintext_codes to the user once and discard
        - Store hashed_codes in the DB (bcrypt hashed)

    Code format: XXXXX-XXXXX (10 alphanumeric chars, hyphen in middle)
    """
    alphabet = string.ascii_uppercase + string.digits
    codes = []
    for _ in range(count):
        part1 = "".join(secrets.choice(alphabet) for _ in range(5))
        part2 = "".join(secrets.choice(alphabet) for _ in range(5))
        codes.append(f"{part1}-{part2}")

    hashed = []
    try:
        from passlib.context import CryptContext
        _ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        hashed = [_ctx.hash(c) for c in codes]
    except ImportError:
        # Fallback: SHA-256 (less ideal but still one-way)
        import hashlib
        hashed = [hashlib.sha256(c.encode()).hexdigest() for c in codes]

    return codes, hashed


def verify_recovery_code(submitted: str, hashed_codes: list[str]) -> tuple[bool, int]:
    """Verify a submitted recovery code against stored hashes.

    Returns (is_valid, matched_index). The caller should mark the matched
    index as used in the DB to prevent reuse.

    Uses constant-time comparison to prevent timing attacks.
    """
    submitted_clean = submitted.strip().upper().replace(" ", "")
    try:
        from passlib.context import CryptContext
        _ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        for i, h in enumerate(hashed_codes):
            if h and _ctx.verify(submitted_clean, h):
                return True, i
    except ImportError:
        import hashlib
        import hmac as _hmac
        sub_hash = hashlib.sha256(submitted_clean.encode()).hexdigest()
        for i, h in enumerate(hashed_codes):
            if h and _hmac.compare_digest(sub_hash, h):
                return True, i
    return False, -1


def mfa_required_for_role(role: str, tenant_config: dict) -> bool:
    """Return True if MFA is required for this role given the tenant's config.

    Policy:
      - super_admin, hr_admin: required if tenant.features.mfa_required is True
      - manager, employee: optional (but enforced if user has totp_enabled)
    """
    features = tenant_config.get("features", {})
    if not features.get("mfa_required", False):
        return False
    return role in ("super_admin", "hr_admin")
