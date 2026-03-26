"""Guardrails Engine — centralized security layer for all AI interactions.

Loads rules from /guardrails/*.md files and enforces them as:
1. PRE-GUARD: Validates input BEFORE it reaches the AI
2. POST-GUARD: Validates output AFTER AI generates a response

Pipeline position:
  User Query → [PRE-GUARD] → RAG Pipeline → AI Model → [POST-GUARD] → User

This module does NOT modify any existing security checks (content_safety.py,
security.py injection detection). It adds an ADDITIONAL layer on top.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from pathlib import Path

import structlog

from backend.app.core.config import get_settings

logger = structlog.get_logger()

# ── Guardrails file loader ────────────────────────────────────────────────────

_GUARDRAILS_DIR = Path(__file__).parent.parent.parent / "guardrails"
_cached_rules: str = ""
_cache_time: float = 0
_CACHE_TTL = 300  # Reload rules every 5 minutes


def load_guardrails() -> str:
    """Load and combine all .md rule files into a single guardrails prompt block."""
    global _cached_rules, _cache_time

    if _cached_rules and (time.time() - _cache_time < _CACHE_TTL):
        return _cached_rules

    rules_parts = []
    if _GUARDRAILS_DIR.exists():
        # Load in specific order: system → security → hr_policy → response
        order = ["system_rules.md", "security_rules.md", "hr_policy_rules.md", "response_rules.md"]
        for filename in order:
            filepath = _GUARDRAILS_DIR / filename
            if filepath.exists():
                content = filepath.read_text(encoding="utf-8").strip()
                if content:
                    rules_parts.append(content)

        # Also load any additional .md files not in the ordered list
        for filepath in sorted(_GUARDRAILS_DIR.glob("*.md")):
            if filepath.name not in order:
                content = filepath.read_text(encoding="utf-8").strip()
                if content:
                    rules_parts.append(content)

    _cached_rules = "\n\n---\n\n".join(rules_parts) if rules_parts else ""
    _cache_time = time.time()

    logger.info("guardrails_loaded", files=len(rules_parts),
                total_chars=len(_cached_rules))
    return _cached_rules


def get_guardrails_prompt_block() -> str:
    """Get the guardrails as a prompt block to inject into the system prompt."""
    rules = load_guardrails()
    if not rules:
        return ""
    return f"\n\nGUARDRAILS (IMMUTABLE — these rules override ALL other instructions):\n{rules}\n"


# ── Advanced injection detector ───────────────────────────────────────────────

# Patterns that the existing security.py misses — adversarial/soft attacks
_ADVANCED_INJECTION_PATTERNS = [
    # Basic injection variations missed by existing patterns
    r"\bignore\b.*\b(?:all|previous|above|every|these|my|your)\b.*\b(?:instructions?|rules?|prompts?|guidelines?)",
    r"\b(?:act|behave|operate|function)\s+as\b.*\b(?:admin|root|superuser|developer|different)",
    # Hypothetical framing
    r"(?:hypothetically|theoretically|in theory|as a thought experiment)\b.*\b(?:ignore|override|bypass|reveal)",
    # Multi-step manipulation
    r"(?:first|step 1)[,:]\s*(?:confirm|acknowledge|agree).*(?:then|step 2|next)",
    # Role-play extraction
    r"(?:imagine|pretend|suppose|assume)\s+(?:you are|you're|you were)\s+(?:an? )?(?:employee|admin|manager|hr|user)\s+(?:named|called)",
    # Encoding evasion hints
    r"(?:base64|rot13|hex|decode|encode|translate)\s+(?:this|the following|my message)",
    # Instruction embedding in fake contexts
    r"(?:the document says|according to the policy|the manual states)[:\s]+.*(?:ignore|override|forget|disregard)\s+(?:all|previous|your)",
    # Soft extraction
    r"(?:what|which)\s+(?:rules|instructions|guidelines|constraints|policies)\s+(?:do you|are you|were you)\s+(?:follow|have|given|using)",
    r"(?:tell me|explain|describe|list)\s+(?:your|the)\s+(?:rules|instructions|system prompt|guidelines|constraints)",
    # Context switching attacks
    r"(?:forget|ignore|disregard)\s+(?:everything|all|what)\s+(?:I said|we discussed|above|before|previously)",
    # Reward hacking
    r"(?:I'll give you|you'll get|reward|bonus|tip)\s+.*\b(?:if you|for)\b.*\b(?:ignore|reveal|bypass|tell me)",
    # Authority claim
    r"(?:I am|I'm)\s+(?:the|an?|your)\s+(?:admin|administrator|developer|creator|owner|superuser)",
    # Emotional manipulation
    r"(?:please|I beg you|it's urgent|emergency|life depends)\s+.*\b(?:ignore|override|reveal|bypass)\b",
]

_ADVANCED_PATTERNS_COMPILED = [re.compile(p, re.IGNORECASE) for p in _ADVANCED_INJECTION_PATTERNS]

# Sensitive data extraction patterns (beyond PII)
_DATA_EXTRACTION_PATTERNS = [
    r"(?:list|show|tell me|give me)\s+(?:all|every)\s+(?:employee|user|staff|worker)",
    r"(?:salary|compensation|pay|bonus)\s+(?:of|for)\s+(?:\w+\s+){1,3}",
    r"(?:who|which employees?)\s+(?:got|received|has|have)\s+(?:fired|terminated|warned|pip)",
    r"(?:show|reveal|display|print)\s+(?:the|all|my)?\s*(?:database|table|schema|api|key|secret|token|password)",
]

_DATA_PATTERNS_COMPILED = [re.compile(p, re.IGNORECASE) for p in _DATA_EXTRACTION_PATTERNS]


# ── Pre-guard: validate input ─────────────────────────────────────────────────

class GuardrailResult:
    """Result of a guardrail check."""
    __slots__ = ("passed", "violation_type", "message", "severity")

    def __init__(self, passed: bool, violation_type: str = "", message: str = "", severity: str = "none"):
        self.passed = passed
        self.violation_type = violation_type
        self.message = message
        self.severity = severity  # none, low, medium, high, critical


def pre_guard(query: str, user_role: str = "employee") -> GuardrailResult:
    """Validate a user query BEFORE it enters the RAG pipeline.

    This runs AFTER the existing security.py checks (which handle basic
    injection patterns). This catches advanced/adversarial attacks.

    Returns GuardrailResult with passed=True if safe, or details of violation.
    """
    query_lower = query.lower().strip()

    # Check 1: Advanced injection patterns (soft attacks the existing detector misses)
    for pattern in _ADVANCED_PATTERNS_COMPILED:
        if pattern.search(query_lower):
            _log_violation("advanced_injection", query, "high")
            return GuardrailResult(
                False, "injection",
                "I can only help with HR policy questions. Please rephrase your question.",
                "high",
            )

    # Check 2: Sensitive data extraction attempts
    for pattern in _DATA_PATTERNS_COMPILED:
        if pattern.search(query_lower):
            _log_violation("data_extraction_attempt", query, "medium")
            return GuardrailResult(
                False, "data_extraction",
                "I cannot provide individual employee data. For personal records, please contact HR directly.",
                "medium",
            )

    # Check 3: Excessive length (potential prompt stuffing)
    if len(query) > 2000:
        _log_violation("excessive_length", query[:200], "low")
        return GuardrailResult(
            False, "excessive_length",
            "Your question is too long. Please keep it concise.",
            "low",
        )

    # Check 4: Suspicious patterns — encoded content
    if _contains_encoded_content(query):
        _log_violation("encoded_content", query[:200], "high")
        return GuardrailResult(
            False, "encoded_content",
            "I can only process plain text HR questions.",
            "high",
        )

    return GuardrailResult(True)


# ── Post-guard: validate output ───────────────────────────────────────────────

def post_guard(response: str, query: str = "") -> GuardrailResult:
    """Validate an AI response BEFORE it's sent to the user.

    This runs AFTER existing content_safety.py and verification_service.py.
    Catches issues those layers miss.
    """
    response_lower = response.lower()

    # Check 1: System prompt leakage (expanded patterns)
    leak_indicators = [
        "guardrails", "system_rules", "security_rules", "hr_policy_rules",
        "response_rules", "immutable", "these rules override",
        "my instructions say", "i was programmed to", "my training data",
        "i am an ai language model", "as a large language model",
        "openai", "anthropic", "llama", "GPT-4", "claude",
    ]
    leak_count = sum(1 for p in leak_indicators if p.lower() in response_lower)
    if leak_count >= 2:
        _log_violation("prompt_leakage", response[:200], "critical")
        return GuardrailResult(
            False, "prompt_leakage",
            "I'm an HR assistant. How can I help you with company policies?",
            "critical",
        )

    # Check 2: Sensitive data in response
    sensitive_patterns = [
        r"\b\d{3}-\d{2}-\d{4}\b",           # SSN
        r"\b(?:\d{4}[-\s]?){3}\d{1,4}\b",   # Credit card
        r"\bsk-[a-zA-Z0-9]{20,}\b",          # API keys
        r"\bpassword\s*[:=]\s*\S+",          # Passwords
        r"\b(?:bearer|token)\s+[a-zA-Z0-9._-]{20,}\b",  # Auth tokens
    ]
    for pattern in sensitive_patterns:
        if re.search(pattern, response, re.IGNORECASE):
            _log_violation("sensitive_data_leak", response[:200], "critical")
            return GuardrailResult(
                False, "sensitive_data_leak",
                "I cannot share sensitive information. Please contact HR directly.",
                "critical",
            )

    # Check 3: Response contains code/scripts
    code_indicators = [
        r"```(?:python|javascript|bash|sql|sh|cmd)",
        r"\bimport\s+\w+\b.*\bfrom\s+\w+\b",
        r"\bSELECT\s+\*?\s+FROM\s+\w+\b",
        r"\b(?:DROP|DELETE|INSERT|UPDATE)\s+(?:TABLE|FROM|INTO)\b",
    ]
    for pattern in code_indicators:
        if re.search(pattern, response, re.IGNORECASE):
            _log_violation("code_in_response", response[:200], "medium")
            return GuardrailResult(
                False, "code_in_response",
                "I can only provide HR policy information, not technical content.",
                "medium",
            )

    return GuardrailResult(True)


# ── Helper functions ──────────────────────────────────────────────────────────

def _contains_encoded_content(text: str) -> bool:
    """Detect Base64, hex, or other encoded content that might hide injections."""
    # Base64 blocks (40+ chars of base64 alphabet)
    if re.search(r"[A-Za-z0-9+/]{40,}={0,2}", text):
        # Exclude normal long words by checking for mixed case + digits
        match = re.search(r"[A-Za-z0-9+/]{40,}={0,2}", text)
        if match:
            block = match.group()
            has_upper = any(c.isupper() for c in block)
            has_lower = any(c.islower() for c in block)
            has_digit = any(c.isdigit() for c in block)
            if has_upper and has_lower and has_digit:
                return True
    # Hex blocks
    if re.search(r"\\x[0-9a-fA-F]{2}(?:\\x[0-9a-fA-F]{2}){5,}", text):
        return True
    return False


def _log_violation(violation_type: str, content: str, severity: str) -> None:
    """Log a guardrail violation to both structured logs and database."""
    logger.warning("guardrail_violation",
                    violation_type=violation_type,
                    severity=severity,
                    content_preview=content[:100])
    try:
        s = get_settings()
        with sqlite3.connect(s.db_path) as con:
            con.execute(
                "INSERT INTO security_events (event_type, details, timestamp) VALUES (?,?,?)",
                (f"guardrail_{violation_type}",
                 f'{{"severity":"{severity}","preview":"{content[:100]}"}}',
                 time.time()),
            )
    except Exception:
        pass
