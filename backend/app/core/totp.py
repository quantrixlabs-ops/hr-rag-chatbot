"""TOTP-based two-factor authentication (Phase B8).

Uses pyotp for TOTP generation and verification.
Falls back gracefully if pyotp is not installed.

Usage:
    from backend.app.core.totp import generate_totp_secret, verify_totp, get_provisioning_uri

    # Generate secret for a new user
    secret = generate_totp_secret()  # Store in user record

    # Get QR code URI for authenticator app
    uri = get_provisioning_uri(secret, "username", "HR Chatbot")

    # Verify a code from the user's authenticator
    is_valid = verify_totp(secret, "123456")
"""

from __future__ import annotations

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
    """Generate a new TOTP secret for a user."""
    if not _HAS_PYOTP:
        raise RuntimeError("pyotp is not installed. Run: pip install pyotp")
    return pyotp.random_base32()


def verify_totp(secret: str, code: str) -> bool:
    """Verify a TOTP code against a secret. Allows 1 step of clock drift."""
    if not _HAS_PYOTP:
        return False
    try:
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)
    except Exception:
        return False


def get_provisioning_uri(secret: str, username: str, issuer: str = "HR Chatbot") -> str:
    """Generate a provisioning URI for QR code display in authenticator apps."""
    if not _HAS_PYOTP:
        return ""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=username, issuer_name=issuer)
