"""Phase 2: Contradiction detection between document sources.

Detects when retrieved chunks from different documents contain
potentially conflicting information (e.g., different leave entitlements,
conflicting deadlines, or policy version mismatches).

This is a lightweight keyword + numeric comparison approach that
works without an LLM call — designed to be fast and additive.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from backend.app.models.document_models import SearchResult


@dataclass
class Contradiction:
    """A detected contradiction between two document chunks."""
    source_a: str
    source_b: str
    excerpt_a: str
    excerpt_b: str
    conflict_type: str  # "numeric", "date", "policy_version", "keyword"
    description: str


@dataclass
class ContradictionResult:
    """Result of contradiction analysis."""
    has_contradictions: bool = False
    contradictions: List[Contradiction] = field(default_factory=list)
    warning_message: str = ""


# Patterns to extract numeric values with context
_NUMBER_PATTERN = re.compile(
    r'(\d+(?:\.\d+)?)\s*'
    r'(days?|hours?|weeks?|months?|years?|percent|%|\$|dollars?|business days?)',
    re.IGNORECASE,
)

# Patterns to extract dates
_DATE_PATTERN = re.compile(
    r'(?:effective|starting|from|until|by|before|after)\s+'
    r'(\w+\s+\d{1,2}(?:,?\s+\d{4})?|\d{1,2}/\d{1,2}/\d{2,4})',
    re.IGNORECASE,
)

# Policy keywords that should be consistent across documents
_POLICY_TERMS = {
    "leave": ["annual leave", "vacation", "sick leave", "pto", "paid time off"],
    "notice": ["notice period", "resignation notice", "termination notice"],
    "probation": ["probation", "probationary period", "trial period"],
    "benefits": ["enrollment", "waiting period", "eligibility"],
}


class ContradictionDetector:
    """Detect contradictions between retrieved document chunks."""

    def detect(self, chunks: list, query: str = "") -> ContradictionResult:
        """Analyze chunks for potential contradictions.

        Only compares chunks from DIFFERENT sources — contradictions
        within the same document are not flagged (likely section context).
        """
        if len(chunks) < 2:
            return ContradictionResult()

        # Group chunks by source
        by_source = {}
        for c in chunks:
            source = c.source if hasattr(c, 'source') else str(c)
            if source not in by_source:
                by_source[source] = []
            by_source[source].append(c)

        if len(by_source) < 2:
            return ContradictionResult()

        contradictions = []
        sources = list(by_source.keys())

        for i in range(len(sources)):
            for j in range(i + 1, len(sources)):
                src_a, src_b = sources[i], sources[j]
                for chunk_a in by_source[src_a]:
                    for chunk_b in by_source[src_b]:
                        found = self._compare_chunks(chunk_a, chunk_b, src_a, src_b)
                        contradictions.extend(found)

        if not contradictions:
            return ContradictionResult()

        # Deduplicate and limit
        unique = self._deduplicate(contradictions)[:3]

        warning = self._build_warning(unique)

        return ContradictionResult(
            has_contradictions=True,
            contradictions=unique,
            warning_message=warning,
        )

    def _compare_chunks(
        self, chunk_a, chunk_b, src_a: str, src_b: str
    ) -> list:
        """Compare two chunks from different sources for contradictions."""
        text_a = chunk_a.text if hasattr(chunk_a, 'text') else str(chunk_a)
        text_b = chunk_b.text if hasattr(chunk_b, 'text') else str(chunk_b)

        contradictions = []

        # ── Check 1: Numeric contradictions ──────────────────────────────
        nums_a = self._extract_numbers(text_a)
        nums_b = self._extract_numbers(text_b)

        for unit, values_a in nums_a.items():
            if unit in nums_b:
                values_b = nums_b[unit]
                # Check if same unit has different values AND they're about similar topics
                for va in values_a:
                    for vb in values_b:
                        if va["value"] != vb["value"] and self._same_topic(
                            va["context"], vb["context"]
                        ):
                            contradictions.append(Contradiction(
                                source_a=src_a,
                                source_b=src_b,
                                excerpt_a=va["context"][:150],
                                excerpt_b=vb["context"][:150],
                                conflict_type="numeric",
                                description=(
                                    f"Different values found: {va['value']} {unit} "
                                    f"vs {vb['value']} {unit}"
                                ),
                            ))

        # ── Check 2: Contradictory policy terms ──────────────────────────
        for topic, terms in _POLICY_TERMS.items():
            a_mentions = any(t in text_a.lower() for t in terms)
            b_mentions = any(t in text_b.lower() for t in terms)
            if a_mentions and b_mentions:
                # Both discuss the same policy topic — check for opposing statements
                if self._has_opposing_language(text_a, text_b):
                    contradictions.append(Contradiction(
                        source_a=src_a,
                        source_b=src_b,
                        excerpt_a=text_a[:150],
                        excerpt_b=text_b[:150],
                        conflict_type="policy_version",
                        description=f"Potentially conflicting {topic} policy statements found across documents.",
                    ))

        return contradictions

    def _extract_numbers(self, text: str) -> dict:
        """Extract numbers with their units and surrounding context."""
        results = {}
        for match in _NUMBER_PATTERN.finditer(text):
            value = float(match.group(1))
            unit = match.group(2).lower().rstrip('s')
            if unit == '%':
                unit = 'percent'
            if unit == '$' or unit == 'dollar':
                unit = 'dollars'

            # Get surrounding context (40 chars each side)
            start = max(0, match.start() - 40)
            end = min(len(text), match.end() + 40)
            context = text[start:end].strip()

            if unit not in results:
                results[unit] = []
            results[unit].append({"value": value, "context": context})
        return results

    def _same_topic(self, context_a: str, context_b: str) -> bool:
        """Check if two numeric contexts are discussing the same topic."""
        words_a = set(re.findall(r'\b\w{4,}\b', context_a.lower()))
        words_b = set(re.findall(r'\b\w{4,}\b', context_b.lower()))
        overlap = words_a & words_b
        # If they share 2+ meaningful words, they're likely about the same topic
        return len(overlap) >= 2

    def _has_opposing_language(self, text_a: str, text_b: str) -> bool:
        """Detect opposing statements (e.g., 'required' vs 'not required')."""
        opposing_pairs = [
            ("required", "not required"),
            ("mandatory", "optional"),
            ("eligible", "not eligible"),
            ("allowed", "not allowed"),
            ("permitted", "not permitted"),
            ("approved", "not approved"),
            ("included", "excluded"),
            ("covered", "not covered"),
        ]
        a_lower = text_a.lower()
        b_lower = text_b.lower()

        for pos, neg in opposing_pairs:
            if (pos in a_lower and neg in b_lower) or (neg in a_lower and pos in b_lower):
                return True
        return False

    def _deduplicate(self, contradictions: list) -> list:
        """Remove duplicate contradictions (same sources + same type)."""
        seen = set()
        unique = []
        for c in contradictions:
            key = (c.source_a, c.source_b, c.conflict_type, c.description[:50])
            if key not in seen:
                seen.add(key)
                unique.append(c)
        return unique

    def _build_warning(self, contradictions: list) -> str:
        """Build a user-facing warning message about contradictions."""
        if not contradictions:
            return ""

        if len(contradictions) == 1:
            c = contradictions[0]
            return (
                f"\n\n**Note:** I found potentially conflicting information between "
                f"*{c.source_a}* and *{c.source_b}*. {c.description} "
                "Please verify with HR which document is current."
            )

        sources = set()
        for c in contradictions:
            sources.add(c.source_a)
            sources.add(c.source_b)
        source_list = ", ".join(f"*{s}*" for s in sorted(sources))

        return (
            f"\n\n**Note:** I found potentially conflicting information across "
            f"these documents: {source_list}. "
            "Some policies may have been updated. Please verify with HR "
            "which version applies to your situation."
        )
