"""Feedback-driven source scoring — adjusts retrieval based on user feedback (Phase C9).

Tracks negative feedback per source document. Sources with high negative
feedback ratios get a penalty applied during retrieval scoring.
"""

from __future__ import annotations

import sqlite3
import time

import structlog

from backend.app.core.config import get_settings

logger = structlog.get_logger()

# Cache — refreshed every 5 minutes
_source_scores: dict[str, float] = {}
_last_refresh: float = 0
REFRESH_INTERVAL = 300  # 5 minutes


def get_source_penalty(source: str) -> float:
    """Return a penalty multiplier for a source (0.5 to 1.0).

    Sources with many negative feedback get penalized (lower score multiplier).
    Sources with no feedback or positive feedback get 1.0 (no penalty).
    """
    _maybe_refresh()
    return _source_scores.get(source, 1.0)


def apply_feedback_scoring(chunks: list) -> list:
    """Apply feedback-based score adjustments to retrieved chunks."""
    _maybe_refresh()
    if not _source_scores:
        return chunks  # No feedback data — no adjustment

    for chunk in chunks:
        penalty = _source_scores.get(chunk.source, 1.0)
        if penalty < 1.0:
            chunk.score = chunk.score * penalty
            logger.debug("feedback_penalty_applied", source=chunk.source, penalty=penalty)

    # Re-sort by adjusted score
    chunks.sort(key=lambda c: c.score, reverse=True)
    return chunks


def _maybe_refresh():
    """Refresh source scores from feedback data if stale."""
    global _source_scores, _last_refresh
    now = time.time()
    if now - _last_refresh < REFRESH_INTERVAL:
        return

    try:
        s = get_settings()
        with sqlite3.connect(s.db_path) as con:
            # Count positive and negative feedback per query
            rows = con.execute(
                "SELECT f.rating, ql.sources_used "
                "FROM feedback f "
                "JOIN query_logs ql ON f.query = ql.query "
                "WHERE f.timestamp > ? AND ql.sources_used != ''",
                (now - 604800,),  # Last 7 days
            ).fetchall()

        if not rows:
            _source_scores = {}
            _last_refresh = now
            return

        import json
        pos_count: dict[str, int] = {}
        neg_count: dict[str, int] = {}
        for rating, sources_json in rows:
            try:
                sources = json.loads(sources_json)
            except Exception:
                continue
            for src in sources:
                if rating == "negative":
                    neg_count[src] = neg_count.get(src, 0) + 1
                else:
                    pos_count[src] = pos_count.get(src, 0) + 1

        # Calculate penalty: high negative ratio → lower score
        scores = {}
        all_sources = set(pos_count) | set(neg_count)
        for src in all_sources:
            total = pos_count.get(src, 0) + neg_count.get(src, 0)
            if total >= 3:  # Need at least 3 feedbacks to apply penalty
                neg_ratio = neg_count.get(src, 0) / total
                # Penalty: 1.0 (no negatives) → 0.5 (all negatives)
                scores[src] = max(0.5, 1.0 - (neg_ratio * 0.5))

        _source_scores = scores
        _last_refresh = now
        if scores:
            logger.info("feedback_scores_updated", sources=len(scores))
    except Exception as e:
        logger.warning("feedback_score_refresh_failed", error=str(e))
        _last_refresh = now
