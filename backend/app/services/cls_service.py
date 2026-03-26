"""Controlled Learning System (CLS) — continuous improvement engine.

Adds on top of the existing CFLS (correction_service.py + cfls_routes.py):
1. Version control: every correction edit creates a version snapshot
2. Rollback: restore any previous version of a correction
3. Learning queue: auto-detect repeated failure patterns from feedback_logs
4. Effectiveness tracking: measure whether corrections reduce future complaints

This module does NOT modify any existing CFLS logic.
"""

from __future__ import annotations

import sqlite3
import time
from difflib import SequenceMatcher

import structlog

from backend.app.core.config import get_settings

logger = structlog.get_logger()


# ── Version Control ───────────────────────────────────────────────────────────

def save_version(db_path: str, correction_id: int, changed_by: str, change_summary: str = "") -> int:
    """Snapshot the current state of a correction before it's modified."""
    with sqlite3.connect(db_path) as con:
        # Get current correction data
        row = con.execute(
            "SELECT query_pattern, corrected_response, keywords FROM knowledge_corrections WHERE id=?",
            (correction_id,),
        ).fetchone()
        if not row:
            return 0

        # Get next version number
        max_ver = con.execute(
            "SELECT COALESCE(MAX(version_number), 0) FROM knowledge_correction_versions WHERE correction_id=?",
            (correction_id,),
        ).fetchone()[0]

        ver = max_ver + 1
        con.execute(
            "INSERT INTO knowledge_correction_versions "
            "(correction_id, version_number, query_pattern, corrected_response, keywords, "
            "change_summary, changed_by, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (correction_id, ver, row[0], row[1], row[2], change_summary, changed_by, time.time()),
        )
        logger.info("correction_version_saved", correction_id=correction_id, version=ver)
        return ver


def get_versions(db_path: str, correction_id: int) -> list[dict]:
    """Get all versions of a correction."""
    with sqlite3.connect(db_path) as con:
        rows = con.execute(
            "SELECT id, version_number, query_pattern, corrected_response, keywords, "
            "change_summary, changed_by, created_at "
            "FROM knowledge_correction_versions WHERE correction_id=? ORDER BY version_number DESC",
            (correction_id,),
        ).fetchall()
    return [{
        "id": r[0], "version_number": r[1], "query_pattern": r[2],
        "corrected_response": r[3], "keywords": r[4],
        "change_summary": r[5], "changed_by": r[6], "created_at": r[7],
    } for r in rows]


def rollback_correction(db_path: str, correction_id: int, version_number: int, rolled_back_by: str) -> bool:
    """Restore a correction to a previous version."""
    with sqlite3.connect(db_path) as con:
        ver = con.execute(
            "SELECT query_pattern, corrected_response, keywords FROM knowledge_correction_versions "
            "WHERE correction_id=? AND version_number=?",
            (correction_id, version_number),
        ).fetchone()
        if not ver:
            return False

        # Save current as a version before rollback
        save_version(db_path, correction_id, rolled_back_by, f"Before rollback to v{version_number}")

        # Apply the old version
        con.execute(
            "UPDATE knowledge_corrections SET query_pattern=?, corrected_response=?, keywords=?, updated_at=? "
            "WHERE id=?",
            (ver[0], ver[1], ver[2], time.time(), correction_id),
        )
        logger.info("correction_rolled_back", correction_id=correction_id,
                     to_version=version_number, by=rolled_back_by)
        return True


# ── Learning Queue — auto-detect patterns ─────────────────────────────────────

def refresh_learning_queue(db_path: str, min_feedback_count: int = 2) -> int:
    """Scan feedback_logs for repeated failure patterns and populate learning_queue.

    Groups negative feedback by similar queries. If a query pattern appears
    in 2+ negative feedbacks and has no existing correction, it enters the queue.

    Returns number of new queue entries created.
    """
    with sqlite3.connect(db_path) as con:
        # Get all pending/negative feedback that hasn't been addressed
        rows = con.execute(
            "SELECT id, query, response, issue_category FROM feedback_logs "
            "WHERE feedback_type='negative' AND status IN ('pending','reviewed') "
            "ORDER BY created_at DESC LIMIT 200"
        ).fetchall()

        if not rows:
            return 0

        # Get existing corrections + queue entries to avoid duplicates
        existing_corrections = {r[0].lower() for r in con.execute(
            "SELECT query_pattern FROM knowledge_corrections WHERE is_active=1"
        ).fetchall()}
        existing_queue = {r[0].lower() for r in con.execute(
            "SELECT query_pattern FROM learning_queue WHERE status IN ('pending','reviewing')"
        ).fetchall()}

    # Group similar queries
    clusters: dict[str, list] = {}
    for fb_id, query, response, category in rows:
        query_norm = _normalize_for_clustering(query)

        # Check if this matches an existing cluster
        matched = False
        for pattern in clusters:
            if _similarity(query_norm, pattern) > 0.6:
                clusters[pattern].append((fb_id, query, response, category))
                matched = True
                break

        if not matched:
            clusters[query_norm] = [(fb_id, query, response, category)]

    # Create queue entries for patterns with enough feedback
    new_entries = 0
    now = time.time()
    with sqlite3.connect(db_path) as con:
        for pattern, feedbacks in clusters.items():
            if len(feedbacks) < min_feedback_count:
                continue
            # Skip if correction or queue entry already exists
            if pattern in existing_corrections or pattern in existing_queue:
                continue

            # Use the most recent feedback as the sample
            sample = feedbacks[0]
            top_category = max(set(f[3] for f in feedbacks), key=lambda c: sum(1 for f in feedbacks if f[3] == c))

            con.execute(
                "INSERT INTO learning_queue "
                "(query_pattern, sample_query, sample_response, feedback_count, "
                "issue_category, status, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (pattern, sample[1], sample[2], len(feedbacks),
                 top_category, "pending", now, now),
            )
            new_entries += 1

    if new_entries:
        logger.info("learning_queue_refreshed", new_entries=new_entries, clusters=len(clusters))
    return new_entries


def get_learning_queue(db_path: str, status: str = "") -> list[dict]:
    """Get learning queue entries."""
    condition = "WHERE status = ?" if status else ""
    params = [status] if status else []
    with sqlite3.connect(db_path) as con:
        rows = con.execute(
            f"SELECT id, query_pattern, sample_query, sample_response, feedback_count, "
            f"issue_category, ai_suggested_response, status, reviewed_by, reviewed_at, "
            f"created_at, updated_at "
            f"FROM learning_queue {condition} ORDER BY feedback_count DESC, created_at DESC",
            params,
        ).fetchall()
    return [{
        "id": r[0], "query_pattern": r[1], "sample_query": r[2],
        "sample_response": r[3], "feedback_count": r[4],
        "issue_category": r[5], "ai_suggested_response": r[6],
        "status": r[7], "reviewed_by": r[8], "reviewed_at": r[9],
        "created_at": r[10], "updated_at": r[11],
    } for r in rows]


def update_queue_item(db_path: str, item_id: int, status: str, reviewed_by: str) -> None:
    """Update a learning queue item status."""
    with sqlite3.connect(db_path) as con:
        con.execute(
            "UPDATE learning_queue SET status=?, reviewed_by=?, reviewed_at=?, updated_at=? WHERE id=?",
            (status, reviewed_by, time.time(), time.time(), item_id),
        )


# ── Effectiveness Tracking ────────────────────────────────────────────────────

def get_effectiveness_metrics(db_path: str) -> dict:
    """Measure how well the learning system is improving responses."""
    now = time.time()
    week = 604800
    month = 2592000

    with sqlite3.connect(db_path) as con:
        # Total corrections and their usage
        total_corrections = con.execute(
            "SELECT COUNT(*) FROM knowledge_corrections WHERE is_active=1"
        ).fetchone()[0]
        total_uses = con.execute(
            "SELECT COALESCE(SUM(use_count), 0) FROM knowledge_corrections WHERE is_active=1"
        ).fetchone()[0]

        # Most effective corrections (highest use count)
        top_corrections = con.execute(
            "SELECT id, query_pattern, use_count, created_at FROM knowledge_corrections "
            "WHERE is_active=1 ORDER BY use_count DESC LIMIT 5"
        ).fetchall()

        # Feedback trend — compare this month vs last month
        this_month_neg = con.execute(
            "SELECT COUNT(*) FROM feedback_logs WHERE feedback_type='negative' AND created_at > ?",
            (now - month,)
        ).fetchone()[0]
        last_month_neg = con.execute(
            "SELECT COUNT(*) FROM feedback_logs WHERE feedback_type='negative' AND created_at BETWEEN ? AND ?",
            (now - 2 * month, now - month)
        ).fetchone()[0]

        # This week vs last week
        this_week_neg = con.execute(
            "SELECT COUNT(*) FROM feedback_logs WHERE feedback_type='negative' AND created_at > ?",
            (now - week,)
        ).fetchone()[0]
        last_week_neg = con.execute(
            "SELECT COUNT(*) FROM feedback_logs WHERE feedback_type='negative' AND created_at BETWEEN ? AND ?",
            (now - 2 * week, now - week)
        ).fetchone()[0]

        # Correction hit rate (corrections used vs total queries this week)
        correction_queries = con.execute(
            "SELECT COUNT(*) FROM query_logs WHERE query_type='correction' AND timestamp > ?",
            (now - week,)
        ).fetchone()[0]
        total_queries = con.execute(
            "SELECT COUNT(*) FROM query_logs WHERE timestamp > ?",
            (now - week,)
        ).fetchone()[0]

        # Learning queue stats
        queue_pending = con.execute(
            "SELECT COUNT(*) FROM learning_queue WHERE status='pending'"
        ).fetchone()[0]
        queue_converted = con.execute(
            "SELECT COUNT(*) FROM learning_queue WHERE status='converted'"
        ).fetchone()[0]

        # Version count
        total_versions = con.execute(
            "SELECT COUNT(*) FROM knowledge_correction_versions"
        ).fetchone()[0]

    # Calculate improvement trends
    month_improvement = 0.0
    if last_month_neg > 0:
        month_improvement = round((last_month_neg - this_month_neg) / last_month_neg * 100, 1)
    week_improvement = 0.0
    if last_week_neg > 0:
        week_improvement = round((last_week_neg - this_week_neg) / last_week_neg * 100, 1)

    hit_rate = round(correction_queries / total_queries * 100, 1) if total_queries > 0 else 0

    return {
        "corrections": {
            "total_active": total_corrections,
            "total_uses": total_uses,
            "total_versions": total_versions,
            "hit_rate_percent": hit_rate,
            "top_corrections": [
                {"id": r[0], "pattern": r[1][:80], "uses": r[2],
                 "age_days": round((now - r[3]) / 86400)}
                for r in top_corrections
            ],
        },
        "improvement": {
            "weekly_negative_feedback": this_week_neg,
            "weekly_change_percent": week_improvement,
            "monthly_negative_feedback": this_month_neg,
            "monthly_change_percent": month_improvement,
            "trend": "improving" if month_improvement > 0 else "stable" if month_improvement == 0 else "declining",
        },
        "learning_queue": {
            "pending": queue_pending,
            "converted_to_corrections": queue_converted,
        },
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_for_clustering(text: str) -> str:
    """Normalize a query for pattern clustering."""
    import re
    text = text.lower().strip()
    text = re.sub(r"\bwhats\b", "what is", text)
    text = re.sub(r"\bhows\b", "how is", text)
    text = re.sub(r"\bmy\b", "the", text)
    text = re.sub(r"[^\w\s]", "", text).strip()
    return text


def _similarity(a: str, b: str) -> float:
    """Simple sequence similarity for clustering."""
    return SequenceMatcher(None, a, b).ratio()
