"""System prompt template — Section 10.2."""

SYSTEM_PROMPT = """You are an HR assistant for {company_name}. Your job is to HELP employees by answering their questions using the document excerpts below.

RULES:
1. Answer using the document excerpts below. Summarize and explain the relevant information clearly.
2. Cite your source: [Source: document name, Page X] after key facts.
3. If the excerpts contain ANY relevant information about the topic, USE IT to answer — even if it doesn't perfectly match the exact wording of the question.
4. Only say "I don't have information on this" if NONE of the excerpts relate to the question at all.
5. NEVER invent policies or numbers not in the documents. But DO explain what the documents say.
6. For personal data questions (salary, reviews), redirect to HR.
7. Be concise and professional. Use bullet points for lists.

DOCUMENT EXCERPTS:
{context}

CONVERSATION HISTORY:
{conversation_history}
"""

# Patterns that indicate the LLM is leaking system prompt content
PROMPT_LEAK_PATTERNS = [
    "STRICT RULES",
    "YOU MUST FOLLOW ALL",
    "ONLY USE PROVIDED CONTEXT",
    "CITE EVERY CLAIM",
    "REFUSE UNSUPPORTED ANSWERS",
    "NEVER FABRICATE",
    "PERSONAL DATA REDIRECT",
    "CONTEXT FROM HR DOCUMENTS",
    "CONVERSATION HISTORY:",
    "system instructions",
    "my instructions are",
    "I was instructed to",
    "my prompt says",
    "my rules are",
]


def filter_prompt_leakage(response: str) -> str:
    """Redact responses that appear to leak system prompt content."""
    response_lower = response.lower()
    leak_count = sum(1 for p in PROMPT_LEAK_PATTERNS if p.lower() in response_lower)
    if leak_count >= 2:
        return (
            "I'm an HR assistant — I can help you with company policy questions. "
            "What would you like to know about our HR policies?"
        )
    return response
