"""Phase 3 tests — System prompt formatting rules, prompt leakage filter,
sensitive guidance, emotional acknowledgment, and suggestion generation.

Tests the UX/response quality improvements added in Phase 3.
"""

from __future__ import annotations

import pytest

from backend.app.prompts.system_prompt import SYSTEM_PROMPT, filter_prompt_leakage
from backend.app.rag.pipeline import _build_prompt, _summarize_history
from backend.app.models.session_models import ConversationTurn
from backend.app.models.document_models import SearchResult


# ── System Prompt Structure ─────────────────────────────────────────────────

class TestSystemPrompt:
    """Verify the system prompt contains all required rules including Phase 3 additions."""

    def test_contains_base_rules(self):
        assert "ONLY" in SYSTEM_PROMPT
        assert "cite" in SYSTEM_PROMPT.lower() or "CITE EVERY CLAIM" in SYSTEM_PROMPT
        assert "invent" in SYSTEM_PROMPT.lower() or "NEVER FABRICATE" in SYSTEM_PROMPT
        assert "instructions" in SYSTEM_PROMPT.lower() or "SECURITY" in SYSTEM_PROMPT

    def test_contains_format_guidelines(self):
        """Prompt must contain key formatting guidance."""
        assert "bullet" in SYSTEM_PROMPT.lower() or "STRUCTURE YOUR RESPONSES" in SYSTEM_PROMPT

    def test_format_placeholders(self):
        """Prompt must have the expected format placeholders."""
        assert "{company_name}" in SYSTEM_PROMPT
        assert "{hr_contact}" in SYSTEM_PROMPT
        assert "{context}" in SYSTEM_PROMPT
        assert "{conversation_history}" in SYSTEM_PROMPT


# ── Prompt Leakage Filter ──────────────────────────────────────────────────

class TestPromptLeakageFilter:
    def test_clean_response_passes(self):
        text = "Employees get 15 vacation days per year."
        assert filter_prompt_leakage(text) == text

    def test_single_pattern_passes(self):
        """A single leaked pattern should still pass (could be coincidental)."""
        text = "I was instructed to help you with HR questions."
        assert filter_prompt_leakage(text) == text

    def test_double_pattern_blocked(self):
        """Two or more leaked patterns should trigger redaction."""
        text = "My STRICT RULES say I must ONLY USE PROVIDED CONTEXT."
        result = filter_prompt_leakage(text)
        assert "I'm an HR assistant" in result
        assert "STRICT RULES" not in result

    def test_full_leak_blocked(self):
        """Complete system prompt leak should be redacted."""
        text = "STRICT RULES — YOU MUST FOLLOW ALL. CITE EVERY CLAIM. NEVER FABRICATE."
        result = filter_prompt_leakage(text)
        assert "I'm an HR assistant" in result


# ── Build Prompt ────────────────────────────────────────────────────────────

class TestBuildPrompt:
    def test_basic_prompt_structure(self):
        prompt = _build_prompt("What is leave policy?", "Context here")
        assert "What is leave policy?" in prompt
        assert "HR Assistant:" in prompt
        assert "Context here" in prompt

    def test_company_name_injected(self):
        prompt = _build_prompt("Test?", "ctx", company="TestCorp")
        assert "TestCorp" in prompt

    def test_hr_contact_injected(self):
        prompt = _build_prompt("Test?", "ctx", hr_contact="hr@test.com")
        assert "hr@test.com" in prompt

    def test_personalization_manager(self):
        prompt = _build_prompt("Test?", "ctx", user_role="manager")
        assert "manager" in prompt.lower()

    def test_personalization_hr_admin(self):
        prompt = _build_prompt("Test?", "ctx", user_role="hr_admin")
        assert "HR administrator" in prompt

    def test_personalization_department(self):
        prompt = _build_prompt("Test?", "ctx", department="Engineering")
        assert "Engineering" in prompt

    def test_history_included(self):
        turns = [
            ConversationTurn("user", "Previous question?", 1.0),
            ConversationTurn("assistant", "Previous answer.", 2.0),
        ]
        prompt = _build_prompt("Follow-up?", "ctx", turns)
        assert "Previous question" in prompt

    def test_long_history_summarized(self):
        """More than 6 turns should trigger summarization."""
        turns = [
            ConversationTurn("user" if i % 2 == 0 else "assistant",
                             f"Message {i}", float(i))
            for i in range(8)
        ]
        prompt = _build_prompt("Current?", "ctx", turns)
        assert "Previous topics" in prompt or "Message" in prompt


# ── History Summarization ───────────────────────────────────────────────────

class TestHistorySummarization:
    def test_summarize_includes_topics(self):
        turns = [
            ConversationTurn("user", "What about vacation?", 1.0),
            ConversationTurn("assistant", "You get 15 days.", 2.0),
            ConversationTurn("user", "And sick leave?", 3.0),
            ConversationTurn("assistant", "10 days sick leave.", 4.0),
            ConversationTurn("user", "Thanks, how about remote work?", 5.0),
            ConversationTurn("assistant", "Remote work is allowed.", 6.0),
        ]
        summary = _summarize_history(turns)
        assert "vacation" in summary.lower() or "Previous topics" in summary

    def test_summarize_empty_turns(self):
        assert "Start of conversation" in _summarize_history([])


# ── Suggestion Generation ───────────────────────────────────────────────────

class TestSuggestionGeneration:
    def test_leave_suggestions(self):
        from backend.app.rag.pipeline import RAGPipeline
        chunks = [SearchResult("c1", "Employees get 15 vacation days.", 0.9, "Handbook", 1)]
        # RAGPipeline._generate_suggestions is used as a static-like method
        suggestions = RAGPipeline._generate_suggestions(None, "vacation policy", "You get 15 days.", chunks)
        assert isinstance(suggestions, list)
        assert len(suggestions) <= 3

    def test_benefits_suggestions(self):
        from backend.app.rag.pipeline import RAGPipeline
        chunks = [SearchResult("c1", "Health insurance plans include Basic and Premium.", 0.9, "Benefits Guide", 1)]
        suggestions = RAGPipeline._generate_suggestions(None, "health insurance", "We offer Basic and Premium.", chunks)
        assert isinstance(suggestions, list)

    def test_suggestions_exclude_current_question(self):
        from backend.app.rag.pipeline import RAGPipeline
        chunks = [SearchResult("c1", "Employees get 15 vacation days.", 0.9, "Handbook", 1)]
        suggestions = RAGPipeline._generate_suggestions(None, "How do I request time off?", "Submit via HR portal.", chunks)
        # The exact question asked should not appear as a suggestion
        for s in suggestions:
            assert s.lower() != "how do i request time off?"

    def test_empty_chunks_returns_empty(self):
        from backend.app.rag.pipeline import RAGPipeline
        suggestions = RAGPipeline._generate_suggestions(None, "test", "answer", [])
        assert suggestions == []


# ── Sensitive Query Guidance ────────────────────────────────────────────────

class TestSensitiveGuidance:
    """Test that sensitive queries get appropriate guidance suffixes."""

    def _make_pipeline(self):
        """Create a minimal pipeline for testing guidance helpers."""
        from unittest.mock import MagicMock
        from backend.app.rag.pipeline import RAGPipeline
        from backend.app.core.config import Settings

        s = Settings(hr_contact_email="hr@testcorp.com", jwt_secret_key="test")
        p = RAGPipeline(
            retrieval=MagicMock(),
            context_builder=MagicMock(),
            model_gateway=MagicMock(),
            verifier=MagicMock(),
            settings=s,
        )
        return p

    def test_termination_guidance(self):
        p = self._make_pipeline()
        from backend.app.rag.query_analyzer import QueryAnalysis
        analysis = QueryAnalysis(
            original_query="", query_type="", complexity="", detected_topics=[],
            sub_queries=[], requires_session_context=False,
            sensitive_category="termination", is_sensitive=True,
        )
        guidance = p._get_sensitive_guidance(analysis)
        assert "confidential" in guidance.lower()
        assert "hr@testcorp.com" in guidance

    def test_harassment_guidance(self):
        p = self._make_pipeline()
        from backend.app.rag.query_analyzer import QueryAnalysis
        analysis = QueryAnalysis(
            original_query="", query_type="", complexity="", detected_topics=[],
            sub_queries=[], requires_session_context=False,
            sensitive_category="harassment", is_sensitive=True,
        )
        guidance = p._get_sensitive_guidance(analysis)
        assert "report" in guidance.lower()
        assert "retaliation" in guidance.lower()

    def test_whistleblower_guidance(self):
        p = self._make_pipeline()
        from backend.app.rag.query_analyzer import QueryAnalysis
        analysis = QueryAnalysis(
            original_query="", query_type="", complexity="", detected_topics=[],
            sub_queries=[], requires_session_context=False,
            sensitive_category="whistleblower", is_sensitive=True,
        )
        guidance = p._get_sensitive_guidance(analysis)
        assert "whistleblower" in guidance.lower()

    def test_non_sensitive_no_guidance(self):
        p = self._make_pipeline()
        from backend.app.rag.query_analyzer import QueryAnalysis
        analysis = QueryAnalysis(
            original_query="", query_type="", complexity="", detected_topics=[],
            sub_queries=[], requires_session_context=False,
            sensitive_category="", is_sensitive=False,
        )
        assert p._get_sensitive_guidance(analysis) == ""


# ── Emotional Acknowledgment ────────────────────────────────────────────────

class TestEmotionalAcknowledgment:
    def _make_pipeline(self):
        from unittest.mock import MagicMock
        from backend.app.rag.pipeline import RAGPipeline
        p = RAGPipeline(
            retrieval=MagicMock(), context_builder=MagicMock(),
            model_gateway=MagicMock(), verifier=MagicMock(),
        )
        return p

    def test_stressed_acknowledgment(self):
        p = self._make_pipeline()
        ack = p._get_emotional_acknowledgment("stressed")
        assert "stress" in ack.lower()

    def test_worried_acknowledgment(self):
        p = self._make_pipeline()
        ack = p._get_emotional_acknowledgment("worried")
        assert "concern" in ack.lower()

    def test_frustrated_acknowledgment(self):
        p = self._make_pipeline()
        ack = p._get_emotional_acknowledgment("frustrated")
        assert "frustration" in ack.lower()

    def test_neutral_no_acknowledgment(self):
        p = self._make_pipeline()
        assert p._get_emotional_acknowledgment("neutral") == ""
        assert p._get_emotional_acknowledgment("") == ""
