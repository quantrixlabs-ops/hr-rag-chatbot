"""FAQ service — curated Q&A pairs that bypass RAG for common HR questions.

Matches user queries against FAQ entries using keyword overlap + fuzzy matching.
Returns a direct answer when confidence is high, avoiding unnecessary LLM calls.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from difflib import SequenceMatcher

import structlog

from backend.app.core.config import get_settings

logger = structlog.get_logger()

# Minimum similarity score to consider an FAQ match
FAQ_MATCH_THRESHOLD = 0.45


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, normalize common variations."""
    import re
    text = text.lower().strip()
    # Normalize informal spellings
    text = re.sub(r"\bwhats\b", "what is", text)
    text = re.sub(r"\bhows\b", "how is", text)
    text = re.sub(r"\bwhos\b", "who is", text)
    # Normalize possessives that don't change meaning
    text = re.sub(r"\bmy\b", "the", text)
    text = re.sub(r"\bour\b", "the", text)
    return re.sub(r"[^\w\s]", "", text).strip()


def _word_overlap_score(query_words: set[str], faq_words: set[str]) -> float:
    """Jaccard-like overlap between query and FAQ keywords."""
    if not query_words or not faq_words:
        return 0.0
    intersection = query_words & faq_words
    union = query_words | faq_words
    return len(intersection) / len(union)


class FAQService:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or get_settings().db_path

    def match(self, query: str) -> dict | None:
        """Try to match a query against curated FAQs.

        Returns {"answer": str, "faq_id": str, "question": str} if matched,
        or None if no FAQ is relevant enough.
        """
        norm_query = _normalize(query)
        query_words = set(norm_query.split())

        # Remove common stop words for better matching
        stop_words = {"a", "an", "the", "is", "are", "was", "were", "do", "does",
                      "how", "what", "when", "where", "who", "which", "can", "i",
                      "my", "me", "our", "we", "to", "of", "in", "for", "and", "or"}
        query_content_words = query_words - stop_words

        try:
            with sqlite3.connect(self.db_path) as con:
                rows = con.execute(
                    "SELECT faq_id, question, answer, keywords FROM faqs WHERE is_active = 1"
                ).fetchall()
        except Exception:
            return None

        if not rows:
            return None

        best_score = 0.0
        best_match = None

        for faq_id, faq_question, faq_answer, keywords in rows:
            # Score 1: Sequence similarity between query and FAQ question
            seq_score = SequenceMatcher(None, norm_query, _normalize(faq_question)).ratio()

            # Score 2: Keyword overlap
            kw_set = set(_normalize(keywords).split()) if keywords else set()
            faq_q_words = set(_normalize(faq_question).split()) - stop_words
            all_faq_words = kw_set | faq_q_words
            overlap_score = _word_overlap_score(query_content_words, all_faq_words)

            # Combined score — sequence similarity weighted higher
            combined = seq_score * 0.6 + overlap_score * 0.4

            if combined > best_score:
                best_score = combined
                best_match = {
                    "faq_id": faq_id,
                    "question": faq_question,
                    "answer": faq_answer,
                    "score": combined,
                }

        if best_match and best_score >= FAQ_MATCH_THRESHOLD:
            logger.info("faq_matched", query=query[:80], faq_q=best_match["question"][:80],
                        score=round(best_score, 3))
            return best_match

        return None

    # ── CRUD for admin management ─────────────────────────────────────────

    def list_faqs(self) -> list[dict]:
        with sqlite3.connect(self.db_path) as con:
            rows = con.execute(
                "SELECT faq_id, question, answer, keywords, category, is_active, created_at "
                "FROM faqs ORDER BY created_at DESC"
            ).fetchall()
        return [
            {"faq_id": r[0], "question": r[1], "answer": r[2], "keywords": r[3],
             "category": r[4], "is_active": bool(r[5]), "created_at": r[6]}
            for r in rows
        ]

    def create_faq(self, question: str, answer: str, keywords: str = "",
                   category: str = "general", created_by: str = "") -> str:
        faq_id = str(uuid.uuid4())
        now = time.time()
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT INTO faqs (faq_id, question, answer, keywords, category, "
                "is_active, created_by, created_at) VALUES (?,?,?,?,?,1,?,?)",
                (faq_id, question, answer, keywords, category, created_by, now),
            )
        return faq_id

    def update_faq(self, faq_id: str, **fields) -> bool:
        allowed = {"question", "answer", "keywords", "category", "is_active"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return False
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [faq_id]
        with sqlite3.connect(self.db_path) as con:
            cur = con.execute(f"UPDATE faqs SET {set_clause} WHERE faq_id = ?", values)
        return cur.rowcount > 0

    def delete_faq(self, faq_id: str) -> bool:
        with sqlite3.connect(self.db_path) as con:
            cur = con.execute("DELETE FROM faqs WHERE faq_id = ?", (faq_id,))
        return cur.rowcount > 0

    def seed_defaults(self) -> int:
        """Seed common HR FAQ entries if the table is empty."""
        with sqlite3.connect(self.db_path) as con:
            count = con.execute("SELECT COUNT(*) FROM faqs").fetchone()[0]
            if count > 0:
                return 0

        defaults = [
            {
                "question": "How do I request time off?",
                "answer": "To request time off, submit a leave request through the HR portal or contact your manager. Most companies require at least 2 weeks advance notice for planned leave. Check your company's leave policy for specific procedures and approval workflows.",
                "keywords": "leave time off vacation pto request holiday absence",
                "category": "leave",
            },
            {
                "question": "What health insurance plans are available?",
                "answer": "Please check your company's benefits documentation for available health insurance plans. Typically, options include medical, dental, and vision coverage. For specific plan details, deductibles, and enrollment periods, contact your HR department.",
                "keywords": "health insurance medical dental vision benefits coverage plan",
                "category": "benefits",
            },
            {
                "question": "What is the remote work policy?",
                "answer": "Remote work policies vary by company and role. Check your company's remote work or flexible work arrangement policy for eligibility, requirements, and approval processes. Contact your manager or HR for your specific situation.",
                "keywords": "remote work from home wfh hybrid flexible telecommute",
                "category": "policies",
            },
            {
                "question": "How do I submit an expense report?",
                "answer": "Expense reports are typically submitted through your company's expense management system. Save all receipts, categorize expenses properly, and submit within the required timeframe (usually 30 days). Check your company's expense policy for spending limits and approval requirements.",
                "keywords": "expense report reimbursement receipt claim spending",
                "category": "procedures",
            },
            {
                "question": "What should I know for my first day?",
                "answer": "For your first day, typically you'll need a valid ID for verification, complete onboarding paperwork, set up your IT accounts, and meet your team. Check any welcome email from HR for specific instructions, arrival time, and dress code. Your manager or HR buddy will guide you through orientation.",
                "keywords": "first day onboarding new hire orientation start joining induction",
                "category": "onboarding",
            },
            {
                "question": "How does the performance review process work?",
                "answer": "Performance reviews are typically conducted annually or semi-annually. The process usually involves self-assessment, manager evaluation, goal setting, and a feedback discussion. Check your company's performance management policy for specific timelines and criteria.",
                "keywords": "performance review evaluation appraisal assessment rating feedback goals",
                "category": "performance",
            },
            {
                "question": "What is the company's leave policy?",
                "answer": "Leave policies cover annual leave, sick leave, personal leave, and other types of absence. Entitlements vary by role, tenure, and location. Check your company's leave policy document for specific details on accrual rates, carry-over rules, and approval processes.",
                "keywords": "leave policy annual sick personal casual maternity paternity holiday",
                "category": "leave",
            },
            {
                "question": "How do I update my personal information?",
                "answer": "You can update your personal information (address, phone, emergency contacts, bank details) through the HR portal or by contacting HR directly. Some changes may require supporting documentation. For name or tax-related changes, contact HR for the required forms.",
                "keywords": "update personal information details address phone bank emergency contact",
                "category": "procedures",
            },
        ]

        count = 0
        for faq in defaults:
            self.create_faq(**faq)
            count += 1

        logger.info("faq_defaults_seeded", count=count)
        return count
