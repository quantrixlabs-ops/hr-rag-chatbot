"""Tests for RAG pipeline components — query analysis, context building, prompt assembly."""

from backend.app.rag.query_analyzer import QueryAnalyzer
from backend.app.rag.context_builder import ContextBuilder
from backend.app.rag.pipeline import _build_prompt, _inject_context
from backend.app.models.document_models import SearchResult
from backend.app.models.session_models import ConversationTurn


def test_query_analyzer_factual():
    qa = QueryAnalyzer()
    r = qa.analyze("How many vacation days do new employees get?")
    assert r.query_type == "factual"
    assert "leave" in r.detected_topics
    assert r.complexity == "simple"


def test_query_analyzer_comparative():
    qa = QueryAnalyzer()
    r = qa.analyze("Compare our maternity leave policy versus FMLA provisions")
    assert r.query_type == "comparative"
    assert r.complexity == "complex"


def test_query_analyzer_procedural():
    qa = QueryAnalyzer()
    r = qa.analyze("How do I request time off?")
    assert r.query_type == "procedural"


def test_query_analyzer_decomposition():
    qa = QueryAnalyzer()
    r = qa.analyze("What is the vacation policy and also the sick leave rules?")
    assert len(r.sub_queries) == 2


def test_context_builder_basic(sample_results):
    cb = ContextBuilder(max_tokens=3000)
    ctx = cb.build(sample_results)
    assert "Source:" in ctx
    assert "---" in ctx
    assert "Document 1" in ctx


def test_context_builder_token_budget():
    chunks = [SearchResult(f"c{i}", " ".join(["word"]*500), 0.9, "doc", 1) for i in range(10)]
    cb = ContextBuilder(max_tokens=500)
    ctx = cb.build(chunks)
    assert ctx.count("Source:") < 10


def test_context_builder_dedup():
    chunks = [
        SearchResult("c1", "Same text here blah", 0.9, "doc", 1),
        SearchResult("c2", "Same text here blah", 0.8, "doc", 1),
    ]
    cb = ContextBuilder(max_tokens=3000)
    assert cb.build(chunks).count("Source:") == 1


def test_context_builder_empty():
    assert "No relevant documents" in ContextBuilder().build([])


def test_build_prompt():
    prompt = _build_prompt("How many vacation days?", "Employees get 15 days.")
    assert "How many vacation days" in prompt
    assert "HR Assistant:" in prompt
    assert "Acme Corp" in prompt


def test_build_prompt_with_history():
    turns = [
        ConversationTurn("user", "What is leave?", 1.0),
        ConversationTurn("assistant", "Leave policy grants 15 days.", 2.0),
    ]
    prompt = _build_prompt("What about sick leave?", "Sick = 10 days.", turns)
    assert "Employee: What is leave?" in prompt


def test_inject_context_with_pronoun():
    turns = [
        ConversationTurn("user", "What is the vacation policy?", 1.0),
        ConversationTurn("assistant", "The vacation policy allows 15 days.", 2.0),
    ]
    result = _inject_context("Does it carry over?", turns)
    assert "Previous question" in result
    assert "vacation policy" in result.lower()


def test_inject_context_no_pronoun():
    turns = [ConversationTurn("user", "Some question", 1.0)]
    assert _inject_context("How many days?", turns) == "How many days?"


# ── Phase 5: Ambiguity detection ─────────────────────────────────────────────

def test_ambiguity_detection_vague_leave():
    """Short vague queries about broad topics trigger clarification."""
    qa = QueryAnalyzer()
    r = qa.analyze("Tell me about leave")
    assert r.is_ambiguous is True
    assert r.clarification_prompt != ""
    assert "annual" in r.clarification_prompt.lower() or "sick" in r.clarification_prompt.lower()


def test_ambiguity_detection_specific_not_ambiguous():
    """Specific queries should NOT be flagged as ambiguous."""
    qa = QueryAnalyzer()
    r = qa.analyze("How many vacation days do new employees get?")
    assert r.is_ambiguous is False


def test_ambiguity_detection_short_general():
    """Very short queries with no topic detected should not be ambiguous."""
    qa = QueryAnalyzer()
    r = qa.analyze("Hello there")
    assert r.is_ambiguous is False  # "general" topic, not in clarification map


def test_ambiguity_detection_benefits_vague():
    """Vague benefits query should trigger clarification."""
    qa = QueryAnalyzer()
    r = qa.analyze("About benefits")
    assert r.is_ambiguous is True
    assert "health insurance" in r.clarification_prompt.lower() or "401k" in r.clarification_prompt.lower()
