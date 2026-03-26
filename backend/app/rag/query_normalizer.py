"""Query normalizer — expands informal user phrasing into document-friendly terms.

Solves the problem where users ask "how many leaves do I get?" but the document
says "annual leave entitlement" — without this, retrieval misses the right chunks.

Two layers:
1. Synonym expansion: maps informal → formal HR terms
2. Phrase normalization: rewrites common informal patterns
"""

from __future__ import annotations

import re

# ── HR synonym groups: first term is the canonical form ───────────────────────
# When any term in the group appears, the canonical form is appended to the query
# so that both the original and formal phrasing are searched.
SYNONYM_GROUPS: list[list[str]] = [
    # Leave / PTO
    ["leave entitlement", "leave", "leaves", "pto", "paid time off", "time off",
     "days off", "vacation", "vacation days", "annual leave", "casual leave"],
    ["sick leave", "sick days", "medical leave", "illness leave", "health leave"],
    ["maternity leave", "maternity", "pregnancy leave", "prenatal"],
    ["paternity leave", "paternity", "parental leave"],
    ["work from home", "wfh", "remote work", "remote working", "hybrid work",
     "telecommute", "telecommuting", "work remotely"],
    # Benefits
    ["health insurance", "medical insurance", "health plan", "medical plan",
     "health coverage", "medical coverage", "healthcare"],
    ["dental insurance", "dental plan", "dental coverage", "dental"],
    ["vision insurance", "vision plan", "vision coverage"],
    ["retirement plan", "401k", "401(k)", "pension", "retirement savings",
     "retirement benefits"],
    ["life insurance", "life cover", "death benefit"],
    # Compensation
    ["salary", "pay", "compensation", "wages", "remuneration", "ctc",
     "cost to company", "take home", "gross pay", "net pay"],
    ["bonus", "incentive", "variable pay", "performance bonus", "annual bonus"],
    ["pay raise", "salary increase", "salary revision", "increment",
     "salary hike", "raise", "pay hike"],
    ["promotion", "career advancement", "career growth", "career progression"],
    # Policies
    ["code of conduct", "workplace behavior", "employee conduct",
     "professional conduct", "workplace rules"],
    ["dress code", "attire policy", "dress policy", "clothing policy"],
    ["attendance", "attendance policy", "punctuality", "working hours",
     "office hours", "office timings", "work hours", "shift"],
    ["expense", "reimbursement", "expense claim", "expense report",
     "travel expense", "travel reimbursement"],
    ["probation", "probation period", "probationary", "trial period",
     "confirmation", "employment confirmation"],
    # Processes
    ["resignation", "resign", "quit", "leaving the company", "notice period",
     "two weeks notice", "exit process", "separation"],
    ["onboarding", "joining", "new hire", "new joiner", "first day",
     "induction", "orientation"],
    ["performance review", "appraisal", "evaluation", "annual review",
     "performance appraisal", "performance evaluation", "review cycle"],
    ["grievance", "complaint", "raise a concern", "file a complaint",
     "lodge a complaint", "workplace complaint"],
    ["transfer", "relocation", "internal transfer", "department transfer",
     "job transfer", "internal mobility"],
    # Common informal → formal
    ["eligibility", "eligible", "qualify", "am i eligible", "do i qualify",
     "who is eligible", "who can"],
    ["policy document", "handbook", "employee handbook", "hr manual",
     "policy manual", "hr handbook", "company handbook"],
]

# Build reverse lookup: informal_term → canonical_term
_SYNONYM_MAP: dict[str, str] = {}
for group in SYNONYM_GROUPS:
    canonical = group[0]
    for term in group[1:]:
        _SYNONYM_MAP[term.lower()] = canonical.lower()

# ── Informal phrase patterns → normalized forms ───────────────────────────────
PHRASE_REWRITES: list[tuple[re.Pattern, str]] = [
    # "how many leaves/days do I get" → "leave entitlement"
    (re.compile(r"\bhow many (leaves?|days off|vacation days?|pto days?)\b.*\b(get|have|entitled|allowed)\b", re.I),
     " leave entitlement"),
    # "can I work from home" → "work from home policy"
    (re.compile(r"\bcan i (work from home|wfh|work remotely)\b", re.I),
     " work from home policy"),
    # "when do I get paid" → "pay schedule"
    (re.compile(r"\bwhen\b.*\b(get paid|salary credited|pay day|payday)\b", re.I),
     " pay schedule salary disbursement"),
    # "how do I apply for leave" → "leave request process"
    (re.compile(r"\bhow\b.*\b(apply|request|take)\b.*\b(leave|pto|vacation|time off)\b", re.I),
     " leave request process apply"),
    # "what happens if I" + policy violation
    (re.compile(r"\bwhat happens if\b.*\b(late|absent|miss|violat|breach)\b", re.I),
     " disciplinary policy consequences"),
    # "who do I contact" / "who should I talk to"
    (re.compile(r"\bwho\b.*\b(contact|talk|speak|reach|report|escalat)\b", re.I),
     " contact escalation reporting"),
    # "am I eligible for" → "eligibility criteria"
    (re.compile(r"\b(am i|do i|can i)\b.*\beligibl\b", re.I),
     " eligibility criteria"),
    # "how to resign" / "I want to quit"
    (re.compile(r"\b(resign|quit|leave the company|put in.*(notice|papers))\b", re.I),
     " resignation process notice period"),
]


def normalize_query(query: str) -> str:
    """Expand a user query with formal HR synonyms for better retrieval.

    Does NOT replace the original query — appends canonical terms so both
    the user's phrasing and the document language are searched.

    Returns the enriched query string.
    """
    ql = query.lower().strip()
    additions: list[str] = []

    # 1. Phrase-level rewrites (check patterns first — more specific)
    for pattern, expansion in PHRASE_REWRITES:
        if pattern.search(ql):
            additions.append(expansion.strip())

    # 2. Term-level synonym expansion
    # Sort by length descending so multi-word terms match before single words
    for term, canonical in sorted(_SYNONYM_MAP.items(), key=lambda x: -len(x[0])):
        if term in ql and canonical not in ql:
            # Only add if the canonical form isn't already in the query
            if canonical not in " ".join(additions).lower():
                additions.append(canonical)

    if not additions:
        return query  # No expansion needed

    # Append expansions to the original query
    expanded = query + " " + " ".join(additions)
    return expanded
