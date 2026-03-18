"""Query analysis agent — Section 4.1 / 14.2.

Classifies query type, estimates complexity, generates sub-queries.
Detects ambiguous queries and suggests clarifications.
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

# Clarification options for broad topic mentions
TOPIC_CLARIFICATIONS: dict[str, list[str]] = {
    "leave": ["annual/vacation leave", "sick leave", "parental/maternity leave", "FMLA leave", "leave request process"],
    "benefits": ["health insurance plans", "dental/vision coverage", "401k/retirement", "HSA", "benefits enrollment"],
    "policy": ["code of conduct", "remote work policy", "dress code", "attendance policy", "expense policy"],
    "compensation": ["salary structure", "bonus eligibility", "pay schedule", "equity/stock options", "promotion process"],
    "performance": ["performance review process", "improvement plans (PIP)", "goal setting", "feedback process"],
    "termination": ["resignation process", "severance policy", "exit interviews", "final pay"],
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

        # Ambiguity detection: short + broad topic + no specific action/question word
        is_ambiguous = False
        clarification = ""
        specific_words = {"how", "what", "when", "where", "who", "which", "can", "do", "does",
                          "is", "are", "get", "request", "apply", "enroll", "submit", "file"}
        has_specific = any(w in ql.split() for w in specific_words)

        if wc <= 5 and not has_specific and topics != ["general"]:
            # Short vague query about a broad topic — ask for clarification
            is_ambiguous = True
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

        return QueryAnalysis(
            query, qtype, complexity, topics, subs if len(subs) > 1 else [query],
            needs_ctx or has_context, is_ambiguous, clarification,
        )
