"""Email service — sends OTP codes for password reset (Phase 2).

Uses Python's built-in smtplib — no external dependencies.
Only active when SMTP_HOST is configured in .env.
"""

from __future__ import annotations

import random
import smtplib
import sqlite3
import string
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import structlog

from backend.app.core.config import get_settings
from backend.app.core.security import hash_password, verify_password

logger = structlog.get_logger()

OTP_LENGTH = 6
OTP_EXPIRY_SECONDS = 600  # 10 minutes
OTP_MAX_ATTEMPTS = 3


def is_email_configured() -> bool:
    """Check if SMTP is configured (non-empty host)."""
    s = get_settings()
    return bool(s.smtp_host and s.smtp_user)


def generate_otp() -> str:
    """Generate a cryptographically random 6-digit OTP."""
    return "".join(random.SystemRandom().choices(string.digits, k=OTP_LENGTH))


def send_otp_email(to_email: str, otp_code: str, username: str) -> bool:
    """Send OTP code via email. Returns True on success."""
    s = get_settings()
    if not is_email_configured():
        logger.warning("email_not_configured", reason="SMTP_HOST not set")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Password Reset Code — {s.smtp_from_name}"
        msg["From"] = f"{s.smtp_from_name} <{s.smtp_user}>"
        msg["To"] = to_email

        text_body = (
            f"Hello {username},\n\n"
            f"Your password reset code is: {otp_code}\n\n"
            f"This code expires in {OTP_EXPIRY_SECONDS // 60} minutes.\n"
            f"If you did not request this, please ignore this email.\n\n"
            f"— {s.company_name} HR Team"
        )

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto; padding: 24px;">
            <div style="background: #f0fdf4; border: 1px solid #86efac; border-radius: 12px; padding: 24px; text-align: center;">
                <h2 style="color: #166534; margin: 0 0 8px;">Password Reset</h2>
                <p style="color: #4b5563; font-size: 14px; margin: 0 0 20px;">
                    Hello {username}, use this code to reset your password:
                </p>
                <div style="background: white; border: 2px solid #16a34a; border-radius: 8px;
                            padding: 16px; font-size: 32px; font-weight: bold; letter-spacing: 8px;
                            color: #166534; font-family: monospace;">
                    {otp_code}
                </div>
                <p style="color: #9ca3af; font-size: 12px; margin: 16px 0 0;">
                    Expires in {OTP_EXPIRY_SECONDS // 60} minutes. If you didn't request this, ignore this email.
                </p>
            </div>
            <p style="color: #9ca3af; font-size: 11px; text-align: center; margin-top: 16px;">
                {s.company_name} HR Team
            </p>
        </div>
        """

        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        if s.smtp_use_tls:
            server = smtplib.SMTP(s.smtp_host, s.smtp_port)
            server.starttls()
        else:
            server = smtplib.SMTP(s.smtp_host, s.smtp_port)

        if s.smtp_user and s.smtp_password:
            server.login(s.smtp_user, s.smtp_password)

        server.sendmail(s.smtp_user, to_email, msg.as_string())
        server.quit()

        logger.info("otp_email_sent", to=to_email[:20] + "...", username=username)
        return True

    except Exception as e:
        logger.error("otp_email_failed", error=str(e)[:200], to=to_email[:20] + "...")
        return False


def store_otp(db_path: str, username: str, otp_code: str) -> None:
    """Store hashed OTP in the user's verification_token field with expiry."""
    otp_hash = hash_password(otp_code)
    expiry = time.time() + OTP_EXPIRY_SECONDS
    token_value = f"OTP:{expiry}:{otp_hash}"

    with sqlite3.connect(db_path) as con:
        con.execute(
            "UPDATE users SET verification_token = ? WHERE username = ?",
            (token_value, username),
        )


def verify_otp(db_path: str, username: str, otp_code: str) -> bool:
    """Verify an OTP code against the stored hash. Returns True if valid."""
    with sqlite3.connect(db_path) as con:
        row = con.execute(
            "SELECT verification_token FROM users WHERE username = ?", (username,)
        ).fetchone()

    if not row or not row[0] or not row[0].startswith("OTP:"):
        return False

    parts = row[0].split(":", 2)
    if len(parts) != 3:
        return False

    try:
        expiry = float(parts[1])
    except ValueError:
        return False

    # Check expiry
    if time.time() > expiry:
        return False

    # Verify hash
    return verify_password(otp_code, parts[2])


def clear_otp(db_path: str, username: str) -> None:
    """Clear the OTP after successful verification."""
    with sqlite3.connect(db_path) as con:
        con.execute(
            "UPDATE users SET verification_token = '' WHERE username = ?",
            (username,),
        )
