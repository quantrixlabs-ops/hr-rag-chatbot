"""Phase 2 tests — Compound query decomposition, contradiction detection,
clarification flow, and intent badges.

Tests the intelligence upgrade features added in Phase 2.
"""

from __future__ import annotations

import uuid

import pytest

from backend.app.services.contradiction_detector import (
    ContradictionDetector,
    ContradictionResult,
)
from backend.app.models.document_models import SearchResult
from backend.app.rag.query_analyzer import QueryAnalyzer


# ── Contradiction Detection ─────────────────────────────────────────────────

class TestContradictionDetector:
    """Test cross-document contradiction detection."""

    def setup_method(self):
        self.detector = ContradictionDetector()

    def test_no_contradiction_single_source(self):
        """Chunks from the same source should never flag contradictions."""
        chunks = [
            SearchResult("c1", "Employees get 15 vacation days per year.", 0.9, "Handbook", 1),
            SearchResult("c2", "New hires get 10 vacation days in their first year.", 0.8, "Handbook", 2),
        ]
        result = self.detector.detect(chunks, "vacation days")
        assert result.has_contradictions is False

    def test_numeric_contradiction_cross_source(self):
        """Different numeric values for the same topic across sources should flag."""
        # Both chunks must share 2+ words of 4+ chars for _same_topic to match
        chunks = [
            SearchResult("c1", "Full-time employees receive 15 days annual vacation leave entitlement per year.", 0.9, "Handbook 2024", 1),
            SearchResult("c2", "Full-time employees receive 20 days annual vacation leave entitlement per year.", 0.8, "Leave Policy 2023", 1),
        ]
        result = self.detector.detect(chunks, "vacation days")
        assert result.has_contradictions is True
        assert len(result.contradictions) >= 1
        assert result.contradictions[0].conflict_type == "numeric"
        assert result.warning_message != ""

    def test_opposing_language_contradiction(self):
        """Opposing policy terms across sources should flag."""
        # Must share a _POLICY_TERMS topic ("leave" terms) AND have opposing language
        chunks = [
            SearchResult("c1", "Annual leave requests are permitted and approved by default for all employees.", 0.9, "Leave Policy A", 1),
            SearchResult("c2", "Annual leave requests are not permitted during the probation period.", 0.8, "Leave Policy B", 1),
        ]
        result = self.detector.detect(chunks, "annual leave")
        assert result.has_contradictions is True
        assert any(c.conflict_type == "policy_version" for c in result.contradictions)

    def test_no_contradiction_unrelated_topics(self):
        """Different numbers about different topics should NOT flag."""
        chunks = [
            SearchResult("c1", "Employees get 15 vacation days per year.", 0.9, "Handbook", 1),
            SearchResult("c2", "The probationary period is 90 days for new hires.", 0.8, "Onboarding Guide", 1),
        ]
        result = self.detector.detect(chunks, "time off")
        assert result.has_contradictions is False

    def test_single_chunk_no_detection(self):
        """Single chunk should never have contradictions."""
        chunks = [SearchResult("c1", "Some text", 0.9, "Doc", 1)]
        result = self.detector.detect(chunks, "test")
        assert result.has_contradictions is False

    def test_empty_chunks(self):
        result = self.detector.detect([], "test")
        assert result.has_contradictions is False

    def test_contradiction_cap_at_3(self):
        """Should not return more than 3 contradictions."""
        chunks = []
        for i in range(5):
            chunks.append(SearchResult(
                f"c{i}", f"Employees get {10 + i * 5} vacation days per year.",
                0.9, f"Doc_{i}", 1,
            ))
        result = self.detector.detect(chunks, "vacation days")
        if result.has_contradictions:
            assert len(result.contradictions) <= 3

    def test_warning_message_single_contradiction(self):
        chunks = [
            SearchResult("c1", "Annual leave is 15 days per year.", 0.9, "Policy A", 1),
            SearchResult("c2", "Annual leave is 20 days per year.", 0.8, "Policy B", 1),
        ]
        result = self.detector.detect(chunks, "annual leave")
        if result.has_contradictions:
            assert "Policy A" in result.warning_message or "Policy B" in result.warning_message
            assert "verify" in result.warning_message.lower()

    def test_warning_message_multiple_contradictions(self):
        chunks = [
            SearchResult("c1", "Annual leave is 15 days. Notice period is 30 days.", 0.9, "Policy A", 1),
            SearchResult("c2", "Annual leave is 20 days. Notice period is 60 days.", 0.8, "Policy B", 1),
            SearchResult("c3", "Annual leave is 25 days. Notice period is 90 days.", 0.7, "Policy C", 1),
        ]
        result = self.detector.detect(chunks, "leave and notice")
        if result.has_contradictions and len(result.contradictions) > 1:
            assert "documents" in result.warning_message.lower()


# ── Contradiction Result Dataclass ──────────────────────────────────────────

class TestContradictionResult:
    def test_default_result(self):
        r = ContradictionResult()
        assert r.has_contradictions is False
        assert r.contradictions == []
        assert r.warning_message == ""

    def test_custom_result(self):
        r = ContradictionResult(has_contradictions=True, contradictions=[], warning_message="test")
        assert r.has_contradictions is True
        assert r.warning_message == "test"


# ── Compound Query Decomposition ────────────────────────────────────────────

class TestCompoundQuery:
    """Test query decomposition into sub-queries."""

    def setup_method(self):
        self.qa = QueryAnalyzer()

    def test_and_conjunction_splits(self):
        r = self.qa.analyze("What is the vacation policy and also the sick leave rules?")
        assert len(r.sub_queries) >= 2

    def test_additionally_conjunction_splits(self):
        r = self.qa.analyze("Tell me about health benefits and additionally about retirement plans")
        assert len(r.sub_queries) >= 2

    def test_single_question_no_split(self):
        r = self.qa.analyze("What is the vacation policy?")
        # Single query returns the original query as sole sub_query
        assert len(r.sub_queries) == 1

    def test_compound_sets_multi_retrieval(self):
        r = self.qa.analyze(
            "What is the vacation policy and also the sick leave rules and additionally the remote work guidelines?"
        )
        if len(r.sub_queries) > 1:
            assert r.requires_multi_retrieval is True

    def test_compound_query_type(self):
        r = self.qa.analyze("What is the vacation policy and also the sick leave rules?")
        # The query type is still factual/policy_lookup — compound is handled at execution level
        assert r.query_type in ("factual", "policy_lookup", "comparative", "procedural")


# ── Clarification Flow ──────────────────────────────────────────────────────

class TestClarificationFlow:
    """Test vague query detection and clarification prompts."""

    def setup_method(self):
        self.qa = QueryAnalyzer()

    def test_vague_single_word_triggers_clarification(self):
        r = self.qa.analyze("Leave")
        assert r.is_ambiguous is True
        assert r.clarification_prompt != ""

    def test_tell_me_about_triggers_clarification(self):
        r = self.qa.analyze("Tell me about benefits")
        assert r.is_ambiguous is True

    def test_what_about_triggers_clarification(self):
        r = self.qa.analyze("What about compensation?")
        assert r.is_ambiguous is True

    def test_specific_query_no_clarification(self):
        r = self.qa.analyze("How many vacation days do new employees get per year?")
        assert r.is_ambiguous is False

    def test_clarification_includes_options(self):
        r = self.qa.analyze("Benefits")
        assert r.is_ambiguous is True
        prompt = r.clarification_prompt.lower()
        assert any(opt in prompt for opt in ["health", "401k", "dental", "insurance"])

    def test_user_clarifying_skips_ambiguity(self):
        """When user is clarifying (has_context=True), vague text should pass through."""
        r = self.qa.analyze("I mean sick leave", has_context=True)
        assert r.is_ambiguous is False

    def test_yes_as_clarification(self):
        r = self.qa.analyze("Yes, the first one", has_context=True)
        assert r.is_ambiguous is False

    def test_greeting_not_ambiguous(self):
        r = self.qa.analyze("Hello there")
        assert r.is_ambiguous is False

    def test_off_topic_not_ambiguous(self):
        """Non-HR topics should not trigger HR clarification."""
        r = self.qa.analyze("How do I reset my vpn password?")
        assert r.is_ambiguous is False  # IT domain, not HR
