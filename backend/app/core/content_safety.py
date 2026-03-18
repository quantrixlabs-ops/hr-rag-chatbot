"""Content safety filter — detects toxic/harmful/inappropriate LLM output (Phase 3).

Runs on every LLM response BEFORE sending to the user.
Uses pattern-based detection (no external dependencies needed).
"""

from __future__ import annotations

import re
from typing import Optional

import structlog

logger = structlog.get_logger()

# Profanity/slur patterns (common patterns, not exhaustive)
_PROFANITY_PATTERNS = [
    r"\b(?:fuck|shit|damn|ass|bitch|bastard|crap|dick|piss)\w*\b",
    r"\b(?:nigger|faggot|retard|slut|whore)\w*\b",
]

# Harmful advice patterns (should never appear in HR responses)
_HARMFUL_PATTERNS = [
    r"(?:kill|harm|hurt|injure)\s+(?:yourself|themselves|himself|herself)",
    r"(?:suicide|self.harm|end\s+your\s+life)",
    r"(?:discriminat|harass|bully|stalk)\s+(?:them|him|her|the\s+employee)",
    r"(?:ignore\s+(?:the\s+)?(?:law|regulation|compliance|policy))",
    r"(?:falsify|forge|fabricate)\s+(?:documents?|records?|data)",
    r"(?:fire|terminate)\s+(?:them|him|her)\s+(?:because\s+of\s+(?:race|gender|religion|age|disability))",
]

# PII that shouldn't appear in responses (different from user input PII)
_RESPONSE_PII_PATTERNS = [
    (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN_REMOVED]"),  # SSN
    (r"\b(?:\d{4}[-\s]?){3}\d{1,4}\b", "[CARD_REMOVED]"),  # Credit card
]

# Bias/discrimination patterns
_BIAS_PATTERNS = [
    r"(?:men|women|males?|females?)\s+(?:are\s+)?(?:better|worse|superior|inferior)\s+at",
    r"(?:people\s+of\s+(?:that|this)\s+(?:race|religion|ethnicity))",
    r"(?:too\s+old|too\s+young)\s+(?:to|for)\s+(?:the\s+)?(?:job|role|position)",
]


def check_content_safety(text: str) -> dict:
    """Check LLM output for safety issues.

    Returns:
        {
            "safe": bool,
            "issues": list of issue descriptions,
            "cleaned_text": text with PII removed (if any),
            "severity": "none" | "low" | "high"
        }
    """
    issues = []
    severity = "none"
    cleaned = text

    text_lower = text.lower()

    # Check profanity
    for pattern in _PROFANITY_PATTERNS:
        if re.search(pattern, text_lower):
            issues.append("profanity_detected")
            severity = "high"

    # Check harmful advice
    for pattern in _HARMFUL_PATTERNS:
        if re.search(pattern, text_lower):
            issues.append("harmful_content_detected")
            severity = "high"

    # Check bias
    for pattern in _BIAS_PATTERNS:
        if re.search(pattern, text_lower):
            issues.append("potential_bias_detected")
            if severity != "high":
                severity = "low"

    # Remove PII from response
    for pattern, replacement in _RESPONSE_PII_PATTERNS:
        cleaned = re.sub(pattern, replacement, cleaned)
        if cleaned != text:
            issues.append("pii_in_response_removed")

    safe = severity != "high"

    if issues:
        logger.warning("content_safety_issue", issues=issues, severity=severity, text_preview=text[:80])

    return {
        "safe": safe,
        "issues": issues,
        "cleaned_text": cleaned,
        "severity": severity,
    }


def sanitize_response(text: str) -> str:
    """Run safety check and return clean text. Replaces unsafe responses."""
    result = check_content_safety(text)

    if not result["safe"]:
        logger.error("unsafe_response_blocked", issues=result["issues"])
        return (
            "I apologize, but I'm unable to provide an appropriate response to this query. "
            "Please contact your HR department directly for assistance."
        )

    return result["cleaned_text"]
