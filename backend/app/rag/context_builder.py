"""Context construction with token budgeting — Section 9.

Improvements:
- Numbered document excerpts for clearer LLM reference
- Minimum relevance floor (0.20) to exclude noise chunks
- Dedup by text similarity
- Token budget enforcement
"""

from __future__ import annotations

from backend.app.models.document_models import SearchResult
from backend.app.models.session_models import ConversationTurn

# Chunks below this score are likely irrelevant noise
MIN_RELEVANCE_SCORE = 0.20


class ContextBuilder:
    def __init__(self, max_tokens: int = 3000):
        self.max_tokens = max_tokens

    def build(
        self,
        chunks: list[SearchResult],
        session_context: Optional[list[ConversationTurn]] = None,
    ) -> str:
        parts: list[str] = []
        tokens = 0
        seen: set[int] = set()
        doc_num = 0

        for c in chunks:
            # Skip low-relevance chunks that would dilute context quality
            if c.score < MIN_RELEVANCE_SCORE:
                continue

            # Dedup by first 150 chars
            h = hash(c.text[:150].lower().strip())
            if h in seen:
                continue
            seen.add(h)

            # Token budget
            ct = int(len(c.text.split()) * 1.3)
            if tokens + ct > self.max_tokens:
                break

            # Numbered format with clear source attribution for LLM grounding
            doc_num += 1
            header = f"[Document {doc_num} | Source: {c.source}"
            if c.page:
                header += f", Page {c.page}"
            header += f" | Relevance: {c.score:.0%}]"
            parts.append(f"{header}\n{c.text.strip()}")
            tokens += ct

        if not parts:
            return "(No relevant documents found)"

        preamble = f"The following {len(parts)} document excerpt(s) are provided for reference:\n"
        return preamble + "\n\n---\n\n".join(parts)
