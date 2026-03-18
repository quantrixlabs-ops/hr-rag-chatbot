"""Data-at-rest encryption using Fernet symmetric encryption (Phase B2).

Usage:
    from backend.app.core.encryption import encrypt_field, decrypt_field

    # Encrypt before storing in DB
    encrypted = encrypt_field("sensitive data")

    # Decrypt when reading from DB
    plaintext = decrypt_field(encrypted)

    # If no encryption key is configured, data passes through unchanged.

Generate a key:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from __future__ import annotations

import base64
import hashlib

import structlog

logger = structlog.get_logger()

_fernet = None
_initialized = False


def _get_fernet():
    """Lazy-init the Fernet cipher from config."""
    global _fernet, _initialized
    if _initialized:
        return _fernet
    _initialized = True
    try:
        from backend.app.core.config import get_settings
        key = get_settings().encryption_key
        if key:
            from cryptography.fernet import Fernet
            _fernet = Fernet(key.encode() if isinstance(key, str) else key)
            logger.info("encryption_enabled")
        else:
            logger.info("encryption_disabled", reason="no ENCRYPTION_KEY configured")
    except ImportError:
        logger.warning("encryption_disabled", reason="cryptography package not installed")
    except Exception as e:
        logger.warning("encryption_disabled", reason=str(e))
    return _fernet


def encrypt_field(plaintext: str) -> str:
    """Encrypt a string field. Returns the encrypted value or original if encryption is disabled."""
    if not plaintext:
        return plaintext
    f = _get_fernet()
    if f is None:
        return plaintext
    try:
        return "ENC:" + f.encrypt(plaintext.encode("utf-8")).decode("utf-8")
    except Exception:
        return plaintext


def decrypt_field(ciphertext: str) -> str:
    """Decrypt a string field. Returns the decrypted value or original if not encrypted."""
    if not ciphertext or not ciphertext.startswith("ENC:"):
        return ciphertext
    f = _get_fernet()
    if f is None:
        return ciphertext  # Can't decrypt without key — return as-is
    try:
        return f.decrypt(ciphertext[4:].encode("utf-8")).decode("utf-8")
    except Exception:
        return ciphertext


def hash_for_lookup(value: str) -> str:
    """Create a deterministic hash for indexed lookups on encrypted fields."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
