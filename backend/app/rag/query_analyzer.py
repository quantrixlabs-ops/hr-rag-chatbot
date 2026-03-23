"""Query analysis agent — Section 4.1 / 14.2.

Classifies query type, estimates complexity, generates sub-queries.
Detects ambiguous queries, routes by domain, and detects language.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

HR_TOPICS: dict[str, list[str]] = {
    "leave": ["leave", "vacation", "pto", "time off", "sick", "fmla", "maternity", "paternity"],
    "benefits": ["benefit", "insurance", "health", "dental", "vision", "401k", "retirement", "hsa"],
    "onboarding": ["onboarding", "new hire", "orientation", "first day", "training"],
    "policy": ["policy", "procedure", "guideline", "rule", "compliance", "code of conduct"],
    "compensation": ["salary", "pay", "compensation", "bonus", "raise", "promotion", "equity"],
    "performance": ["performance", "review", "pip", "improvement plan", "feedback", "evaluation"],
    "termination": ["termination", "resign", "separation", "layoff", "severance", "exit"],
}

# Non-HR domain keywords for smart routing
IT_KEYWORDS = ["vpn", "wifi", "password reset", "laptop", "software install", "email setup",
               "printer", "jira", "github", "deploy", "server", "database", "network", "firewall"]
PERSONAL_KEYWORDS = ["my salary", "my bonus", "my performance", "my review score", "my rating",
                     "my disciplinary", "my warning", "am i getting fired", "my termination"]
GREETING_KEYWORDS = ["hello", "hi", "hey", "good morning", "good afternoon", "thanks", "thank you", "bye"]

# ── Phase 1: Intent detection patterns ───────────────────────────────────────
SENSITIVE_PATTERNS = {
    "termination": ["fired", "terminate", "let go", "laid off", "layoff", "severance",
                     "getting fired", "lose my job", "dismissal", "wrongful termination"],
    "harassment": ["harassment", "harassed", "bullying", "hostile work", "discrimination",
                   "sexual harassment", "reporting harassment", "complaint against"],
    "disciplinary": ["disciplinary", "written warning", "pip", "improvement plan",
                     "final warning", "suspension", "reprimand", "misconduct"],
    "salary_negotiation": ["salary negotiation", "pay raise", "underpaid", "pay gap",
                           "salary review", "asking for a raise", "counter offer"],
    "whistleblower": ["whistleblower", "retaliation", "report fraud", "ethics violation",
                      "anonymous report", "compliance violation"],
}

CALCULATION_KEYWORDS = [
    "how many days", "how many hours", "calculate", "how much",
    "accrued", "remaining", "balance", "total days", "pro-rata",
    "prorate", "prorated", "percentage", "number of",
]

EMOTIONAL_PATTERNS = {
    "stressed": ["stressed", "overwhelmed", "burnt out", "burnout", "too much work", "overworked"],
    "worried": ["worried", "anxious", "concerned", "afraid", "scared", "nervous"],
    "frustrated": ["frustrated", "unfair", "not fair", "angry", "furious", "ridiculous", "unacceptable"],
    "upset": ["upset", "disappointed", "hurt", "feel bad", "feel terrible"],
}

# Clarification options for broad topic mentions
TOPIC_CLARIFICATIONS: dict[str, list[str]] = {
    "leave": ["annual/vacation leave", "sick leave", "parental/maternity leave", "FMLA leave", "leave request process"],
    "benefits": ["health insurance plans", "dental/vision coverage", "401k/retirement", "HSA", "benefits enrollment"],
    "policy": ["code of conduct", "remote work policy", "dress code", "attendance policy", "expense policy"],
    "compensation": ["salary structure", "bonus eligibility", "pay schedule", "equity/stock options", "promotion process"],
    "performance": ["performance review process", "improvement plans (PIP)", "goal setting", "feedback process"],
    "termination": ["resignation process", "severance policy", "exit interviews", "final pay"],
}

# Auto-classification keywords for document uploads
DOCUMENT_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "leave": ["leave", "vacation", "pto", "time off", "sick leave", "fmla", "maternity", "parental"],
    "benefits": ["benefit", "insurance", "health plan", "dental", "vision", "401k", "retirement", "hsa"],
    "handbook": ["handbook", "employee guide", "company policies", "code of conduct"],
    "onboarding": ["onboarding", "new hire", "orientation", "first day", "welcome"],
    "policy": ["policy", "procedure", "guideline", "compliance", "remote work", "dress code"],
    "legal": ["legal", "contract", "nda", "non-compete", "confidentiality", "agreement"],
    "compensation": ["salary", "compensation", "pay scale", "bonus", "equity", "stock"],
    "performance": ["performance", "review", "evaluation", "rating", "promotion criteria"],
}


@dataclass
class QueryAnalysis:
    original_query: str
    query_type: str
    complexity: str
    detected_topics: list[str]
    sub_queries: list[str]
    requires_session_context: bool
    is_ambiguous: bool = False
    clarification_prompt: str = ""
    domain: str = "hr"  # hr, it, personal, greeting, off_topic
    language: str = "en"
    redirect_message: str = ""
    # ── Phase 1: Enterprise Intelligence fields (additive only) ──────────
    intent: str = "policy_lookup"  # policy_lookup, calculation, procedural, sensitive, emotional, comparative, factual
    analysis_confidence: float = 0.8  # how confident the analyzer is in its classification
    is_sensitive: bool = False  # termination, harassment, disciplinary, salary negotiation
    sensitive_category: str = ""  # specific sensitive category if detected
    is_calculation: bool = False  # requires numerical reasoning (days, amounts, etc.)
    emotional_tone: str = ""  # stressed, worried, frustrated, neutral
    requires_multi_retrieval: bool = False  # True when sub_queries > 1 and should be executed separately


def detect_language(text: str) -> str:
    """Lightweight language detection based on character patterns."""
    # Check for non-Latin scripts
    if re.search(r'[\u4e00-\u9fff]', text):
        return "zh"
    if re.search(r'[\u3040-\u309f\u30a0-\u30ff]', text):
        return "ja"
    if re.search(r'[\uac00-\ud7af]', text):
        return "ko"
    if re.search(r'[\u0600-\u06ff]', text):
        return "ar"
    if re.search(r'[\u0900-\u097f]', text):
        return "hi"
    if re.search(r'[\u0b80-\u0bff]', text):
        return "ta"
    # Spanish/French/German common patterns
    if re.search(r'\b(el|la|los|las|es|por|que|como|para)\b', text.lower()) and len(re.findall(r'[áéíóúñ]', text)) > 0:
        return "es"
    if re.search(r'\b(le|la|les|des|est|sont|avec|pour|dans)\b', text.lower()) and len(re.findall(r'[àâéèêëîïôùûç]', text)) > 0:
        return "fr"
    return "en"


def auto_classify_document(title: str, content_preview: str) -> str:
    """Auto-classify a document's category based on title and content."""
    combined = (title + " " + content_preview[:500]).lower()
    scores: dict[str, int] = {}
    for category, keywords in DOCUMENT_CATEGORY_KEYWORDS.items():
        scores[category] = sum(1 for kw in keywords if kw in combined)
    if not scores or max(scores.values()) == 0:
        return "policy"  # default
    return max(scores, key=lambda k: scores[k])


# ── Phase 2: Clarification patterns for vague queries ─────────────────────────
VAGUE_QUERY_PATTERNS = [
    # Single-word topic mentions
    re.compile(r"^(leave|benefits?|policy|compensation|salary|onboarding|termination|performance)\.?$", re.I),
    # "Tell me about X" without specifics
    re.compile(r"^tell me about\s+\w+\.?$", re.I),
    # "What about X?"
    re.compile(r"^what about\s+\w+\??$", re.I),
    # "I need help with X"
    re.compile(r"^i need help with\s+\w+\.?$", re.I),
]

# Phrases that indicate the user is providing clarification (follow-up to our question)
CLARIFICATION_INDICATORS = [
    "i mean", "i meant", "i'm asking about", "specifically", "i want to know about",
    "the first one", "the second one", "option", "yes", "no", "that one",
]


class QueryAnalyzer:
    def analyze(self, query: str, has_context: bool = False) -> QueryAnalysis:
        ql = query.lower()
        topics = [t for t, kws in HR_TOPICS.items() if any(k in ql for k in kws)] or ["general"]
        qtype = (
            "comparative" if any(w in ql for w in ["compare", "difference", "versus", "vs"]) else
            "procedural" if any(w in ql for w in ["how do i", "how to", "steps", "process"]) else
            "factual" if any(w in ql for w in ["what is", "what are", "how many", "how much", "when"]) else
            "policy_lookup"
        )
        wc = len(query.split())
        conj = any(w in ql for w in [" and ", " also ", " additionally "])
        comp = any(w in ql for w in ["compare", "difference", "versus"])
        complexity = "complex" if comp or (conj and wc > 20) else "moderate" if conj or wc > 15 else "simple"
        subs = [p.strip() for p in re.split(r"\s+(?:and|also|additionally)\s+", query, flags=re.I) if p.strip()]
        needs_ctx = any(w in ql.split() for w in ["it", "that", "this", "those", "these"])

        # ── Smart routing: detect domain ─────────────────────────────────
        domain = "hr"
        redirect_message = ""

        if any(kw in ql for kw in GREETING_KEYWORDS) and wc <= 5:
            domain = "greeting"
            redirect_message = ""
        elif any(kw in ql for kw in IT_KEYWORDS):
            domain = "it"
            redirect_message = (
                "That looks like an IT question. I specialize in HR topics like leave, benefits, "
                "and company policies. For IT support, please contact your IT help desk."
            )
        elif any(kw in ql for kw in PERSONAL_KEYWORDS):
            domain = "personal"
            redirect_message = (
                "For questions about your personal records (salary, performance ratings, "
                "disciplinary matters), please contact your HR department directly. "
                "I can help with general policy questions."
            )

        # ── Language detection ───────────────────────────────────────────
        language = detect_language(query)

        # ── Ambiguity detection (enhanced in Phase 2) ────────────────────
        is_ambiguous = False
        clarification = ""
        specific_words = {"how", "what", "when", "where", "who", "which", "can", "do", "does",
                          "is", "are", "get", "request", "apply", "enroll", "submit", "file"}
        has_specific = any(w in ql.split() for w in specific_words)

        # Phase 2: If user is providing clarification to our previous question,
        # skip ambiguity detection — let it flow through to retrieval
        is_user_clarifying = has_context and any(ind in ql for ind in CLARIFICATION_INDICATORS)

        if not is_user_clarifying and domain == "hr" and topics != ["general"]:
            # Original rule: short + no specifics
            if wc <= 5 and not has_specific:
                is_ambiguous = True
            # Phase 2: Also catch vague patterns like "tell me about leave"
            elif any(p.match(query.strip()) for p in VAGUE_QUERY_PATTERNS):
                is_ambiguous = True

            if is_ambiguous:
                topic = topics[0]
                options = TOPIC_CLARIFICATIONS.get(topic, [])
                if options:
                    bullet_list = "\n".join(f"  - {opt}" for opt in options)
                    clarification = (
                        f"I'd be happy to help with {topic}! Could you be more specific? "
                        f"For example, are you asking about:\n{bullet_list}\n\n"
                        "Please provide more details so I can give you the most accurate answer."
                    )
                else:
                    clarification = (
                        "Could you provide more details about what you'd like to know? "
                        "A more specific question will help me find the right information."
                    )

        # ── Phase 1: Intent classification (additive — does not change qtype) ─
        intent = qtype  # start with existing query_type as default
        is_sensitive = False
        sensitive_category = ""
        is_calculation = False
        emotional_tone = ""
        analysis_confidence = 0.8  # default confidence

        # Sensitive query detection
        for cat, patterns in SENSITIVE_PATTERNS.items():
            if any(p in ql for p in patterns):
                is_sensitive = True
                sensitive_category = cat
                intent = "sensitive"
                analysis_confidence = 0.9  # high confidence on keyword match
                break

        # Calculation detection
        if not is_sensitive and any(kw in ql for kw in CALCULATION_KEYWORDS):
            is_calculation = True
            intent = "calculation"
            analysis_confidence = 0.85

        # Emotional tone detection
        for tone, patterns in EMOTIONAL_PATTERNS.items():
            if any(p in ql for p in patterns):
                emotional_tone = tone
                break

        # Refine intent from existing qtype if not overridden
        if intent == qtype:
            if qtype == "comparative":
                intent = "comparative"
                analysis_confidence = 0.85
            elif qtype == "procedural":
                intent = "procedural"
                analysis_confidence = 0.85
            elif qtype == "factual":
                intent = "factual"
                analysis_confidence = 0.8

        # Multi-retrieval: needed when there are real sub-queries
        requires_multi = len(subs) > 1 and complexity in ("moderate", "complex")

        # Adjust confidence based on ambiguity and complexity
        if is_ambiguous:
            analysis_confidence *= 0.6
        if complexity == "complex":
            analysis_confidence *= 0.9

        return QueryAnalysis(
            query, qtype, complexity, topics, subs if len(subs) > 1 else [query],
            needs_ctx or has_context, is_ambiguous, clarification,
            domain, language, redirect_message,
            intent=intent,
            analysis_confidence=round(analysis_confidence, 3),
            is_sensitive=is_sensitive,
            sensitive_category=sensitive_category,
            is_calculation=is_calculation,
            emotional_tone=emotional_tone,
            requires_multi_retrieval=requires_multi,
        )
