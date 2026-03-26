"""Knowledge Correction Matching Service — CFLS Core.

Checks incoming queries against HR-approved corrections BEFORE the RAG
pipeline runs. This is the highest-priority response source.

Priority order:
1. KnowledgeCorrections (this service) — HR-approved overrides
2. FAQ entries — curated Q&A pairs
3. RAG pipeline — document retrieval + LLM generation

Matching uses the same fuzzy logic as FAQ service: sequence similarity +
keyword overlap, but with a HIGHER threshold to avoid false positives
(corrections must be highly confident since they bypass document retrieval).
"""

from __future__ import annotations

import re
import sqlite3
import time
from difflib import SequenceMatcher

import structlog

from backend.app.core.config import get_settings

logger = structlog.get_logger()

# Higher threshold than FAQ (0.45) — corrections must be very confident
CORRECTION_MATCH_THRESHOLD = 0.72


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, normalize common variations."""
    text = text.lower().strip()
    text = re.sub(r"\bwhats\b", "what is", text)
    text = re.sub(r"\bhows\b", "how is", text)
    text = re.sub(r"\bwhos\b", "who is", text)
    text = re.sub(r"\bmy\b", "the", text)
    text = re.sub(r"\bour\b", "the", text)
    return re.sub(r"[^\w\s]", "", text).strip()


def _word_overlap(a_words: set, b_words: set) -> float:
    if not a_words or not b_words:
        return 0.0
    intersection = a_words & b_words
    union = a_words | b_words
    return len(intersection) / len(union)


class CorrectionService:
    """Matches user queries against HR-approved knowledge corrections."""

    def __init__(self, db_path: str = ""):
        self.db_path = db_path or get_settings().db_path

    def match(self, query: str) -> dict | None:
        """Find the best matching correction for a query.

        Returns {"id", "corrected_response", "query_pattern", "score"}
        or None if no correction matches above threshold.
        """
        norm_query = _normalize(query)
        query_words = set(norm_query.split())

        stop_words = {"a", "an", "the", "is", "are", "was", "were", "do", "does",
                      "how", "what", "when", "where", "who", "which", "can", "i",
                      "my", "me", "our", "we", "to", "of", "in", "for", "and", "or"}
        query_content_words = query_words - stop_words

        try:
            with sqlite3.connect(self.db_path) as con:
                rows = con.execute(
                    "SELECT id, query_pattern, corrected_response, keywords "
                    "FROM knowledge_corrections WHERE is_active = 1"
                ).fetchall()
        except Exception:
            return None

        if not rows:
            return None

        best_score = 0.0
        best_match = None

        for corr_id, pattern, response, keywords in rows:
            # Score 1: Sequence similarity
            seq_score = SequenceMatcher(None, norm_query, _normalize(pattern)).ratio()

            # Score 2: Keyword overlap (pattern words + explicit keywords)
            kw_set = set(_normalize(keywords).split()) if keywords else set()
            pattern_words = set(_normalize(pattern).split()) - stop_words
            all_corr_words = kw_set | pattern_words
            overlap_score = _word_overlap(query_content_words, all_corr_words)

            # Combined: heavier weight on sequence similarity for precision
            combined = seq_score * 0.65 + overlap_score * 0.35

            if combined > best_score:
                best_score = combined
                best_match = {
                    "id": corr_id,
                    "query_pattern": pattern,
                    "corrected_response": response,
                    "score": combined,
                }

        if best_match and best_score >= CORRECTION_MATCH_THRESHOLD:
            # Increment use counter
            try:
                with sqlite3.connect(self.db_path) as con:
                    con.execute(
                        "UPDATE knowledge_corrections SET use_count = use_count + 1 WHERE id = ?",
                        (best_match["id"],)
                    )
            except Exception:
                pass

            logger.info("cfls_correction_hit",
                        query=query[:80],
                        pattern=best_match["query_pattern"][:80],
                        score=round(best_score, 3))
            return best_match

        return None
