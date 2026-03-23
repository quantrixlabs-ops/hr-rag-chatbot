"""Phase 1 tests — Intent detection, sensitive queries, emotional tone,
calculation detection, multi-retrieval, verification scoring.

Tests the enterprise intelligence features added in Phase 1.
"""

from __future__ import annotations

import pytest

from backend.app.rag.query_analyzer import QueryAnalyzer


# ── Intent Classification ────────────────────────────────────────────────────

class TestIntentDetection:
    """Verify the query analyzer correctly classifies intents."""

    def setup_method(self):
        self.qa = QueryAnalyzer()

    def test_policy_lookup_intent(self):
        r = self.qa.analyze("What is the remote work policy?")
        assert r.intent in ("factual", "policy_lookup")

    def test_calculation_intent(self):
        r = self.qa.analyze("How many days of leave have I accrued this year?")
        assert r.intent == "calculation"
        assert r.is_calculation is True

    def test_calculation_keywords(self):
        for kw in ["how many days", "how much", "calculate", "accrued", "remaining balance"]:
            r = self.qa.analyze(f"{kw} of leave do I get?")
            assert r.is_calculation is True, f"Failed for keyword: {kw}"

    def test_procedural_intent(self):
        r = self.qa.analyze("How do I request a leave of absence?")
        assert r.intent == "procedural"

    def test_comparative_intent(self):
        r = self.qa.analyze("Compare the Basic and Premium health plans")
        assert r.intent == "comparative"
        assert r.query_type == "comparative"

    def test_sensitive_intent_termination(self):
        r = self.qa.analyze("Am I getting fired?")
        assert r.intent == "sensitive"
        assert r.is_sensitive is True
        assert r.sensitive_category == "termination"

    def test_sensitive_intent_harassment(self):
        r = self.qa.analyze("I want to report harassment in my department")
        assert r.intent == "sensitive"
        assert r.is_sensitive is True
        assert r.sensitive_category == "harassment"

    def test_sensitive_intent_whistleblower(self):
        r = self.qa.analyze("How do I report fraud as a whistleblower?")
        assert r.is_sensitive is True
        assert r.sensitive_category == "whistleblower"

    def test_sensitive_intent_disciplinary(self):
        r = self.qa.analyze("I received a written warning, what are my options?")
        assert r.is_sensitive is True
        assert r.sensitive_category == "disciplinary"

    def test_sensitive_intent_salary(self):
        r = self.qa.analyze("I think I'm underpaid compared to my peers")
        assert r.is_sensitive is True
        assert r.sensitive_category == "salary_negotiation"

    def test_non_sensitive_query(self):
        r = self.qa.analyze("What health insurance plans are available?")
        assert r.is_sensitive is False
        assert r.sensitive_category == ""


# ── Emotional Tone Detection ────────────────────────────────────────────────

class TestEmotionalTone:
    def setup_method(self):
        self.qa = QueryAnalyzer()

    def test_stressed_tone(self):
        r = self.qa.analyze("I'm so stressed about the performance review")
        assert r.emotional_tone == "stressed"

    def test_worried_tone(self):
        r = self.qa.analyze("I'm worried about losing my benefits during leave")
        assert r.emotional_tone == "worried"

    def test_frustrated_tone(self):
        r = self.qa.analyze("This policy is unfair and ridiculous")
        assert r.emotional_tone == "frustrated"

    def test_upset_tone(self):
        r = self.qa.analyze("I'm upset about how this was handled")
        assert r.emotional_tone == "upset"

    def test_neutral_tone(self):
        r = self.qa.analyze("What are the office hours?")
        assert r.emotional_tone == ""


# ── Analysis Confidence ─────────────────────────────────────────────────────

class TestAnalysisConfidence:
    def setup_method(self):
        self.qa = QueryAnalyzer()

    def test_confidence_is_numeric(self):
        r = self.qa.analyze("What is the leave policy?")
        assert isinstance(r.analysis_confidence, float)
        assert 0.0 <= r.analysis_confidence <= 1.0

    def test_sensitive_has_high_confidence(self):
        r = self.qa.analyze("I want to report harassment")
        assert r.analysis_confidence >= 0.8

    def test_ambiguous_lowers_confidence(self):
        r = self.qa.analyze("About leave")
        assert r.is_ambiguous is True
        assert r.analysis_confidence < 0.7  # ambiguity multiplier applied

    def test_specific_query_default_confidence(self):
        r = self.qa.analyze("How many vacation days do new employees get?")
        assert r.analysis_confidence >= 0.7


# ── Multi-Retrieval Flag ────────────────────────────────────────────────────

class TestMultiRetrieval:
    def setup_method(self):
        self.qa = QueryAnalyzer()

    def test_compound_query_flags_multi_retrieval(self):
        r = self.qa.analyze("What is the vacation policy and also the sick leave rules?")
        assert len(r.sub_queries) >= 2
        assert r.requires_multi_retrieval is True

    def test_single_query_no_multi_retrieval(self):
        r = self.qa.analyze("How many vacation days do I get?")
        assert r.requires_multi_retrieval is False

    def test_sub_queries_are_meaningful(self):
        r = self.qa.analyze("What is the vacation policy and also the sick leave rules?")
        combined = " ".join(r.sub_queries).lower()
        assert "vacation" in combined
        assert "sick" in combined


# ── Domain Routing ──────────────────────────────────────────────────────────

class TestDomainRouting:
    def setup_method(self):
        self.qa = QueryAnalyzer()

    def test_it_domain_routing(self):
        r = self.qa.analyze("How do I reset my vpn password?")
        assert r.domain == "it"
        assert r.redirect_message != ""

    def test_personal_domain_routing(self):
        r = self.qa.analyze("What is my salary?")
        assert r.domain == "personal"

    def test_greeting_routing(self):
        r = self.qa.analyze("Hello")
        assert r.domain == "greeting"

    def test_hr_domain_default(self):
        r = self.qa.analyze("What is the maternity leave policy?")
        assert r.domain == "hr"


# ── Language Detection ──────────────────────────────────────────────────────

class TestLanguageDetection:
    def setup_method(self):
        self.qa = QueryAnalyzer()

    def test_english_detected(self):
        r = self.qa.analyze("What is the vacation policy?")
        assert r.language == "en"

    def test_chinese_detected(self):
        r = self.qa.analyze("你好，请问假期政策是什么？")
        assert r.language == "zh"

    def test_japanese_detected(self):
        # Use Hiragana/Katakana-only query (no Kanji, which overlaps with Chinese range)
        r = self.qa.analyze("おやすみのポリシーはなんですか？")
        assert r.language == "ja"

    def test_korean_detected(self):
        r = self.qa.analyze("휴가 정책은 무엇입니까?")
        assert r.language == "ko"

    def test_arabic_detected(self):
        r = self.qa.analyze("ما هي سياسة الإجازات؟")
        assert r.language == "ar"


# ── Verification Service: Intent-Aware Scoring ─────────────────────────────

class TestVerificationIntentAware:
    """Test that the verifier adjusts confidence based on intent and analysis_confidence."""

    def test_sensitive_caps_confidence(self, sample_results):
        from backend.app.services.verification_service import AnswerVerifier
        v = AnswerVerifier()
        r = v.verify(
            "Employees receive 15 vacation days per year.",
            sample_results, "vacation?",
            intent="sensitive", analysis_confidence=0.9,
        )
        assert r.faithfulness_score <= 0.85  # sensitive cap

    def test_calculation_multiplier(self, sample_results):
        from backend.app.services.verification_service import AnswerVerifier
        v = AnswerVerifier()
        r_normal = v.verify(
            "Employees receive 15 vacation days per year.",
            sample_results, "vacation?",
            intent="factual", analysis_confidence=0.8,
        )
        r_calc = v.verify(
            "Employees receive 15 vacation days per year.",
            sample_results, "vacation?",
            intent="calculation", analysis_confidence=0.8,
        )
        # Calculation intent applies 0.95x multiplier — so calc <= normal
        assert r_calc.faithfulness_score <= r_normal.faithfulness_score

    def test_analysis_confidence_blending(self, sample_results):
        from backend.app.services.verification_service import AnswerVerifier
        v = AnswerVerifier()
        r_high = v.verify(
            "Employees receive 15 vacation days per year.",
            sample_results, "vacation?",
            intent="factual", analysis_confidence=1.0,
        )
        r_low = v.verify(
            "Employees receive 15 vacation days per year.",
            sample_results, "vacation?",
            intent="factual", analysis_confidence=0.3,
        )
        # Higher analysis confidence should yield higher or equal score
        assert r_high.faithfulness_score >= r_low.faithfulness_score

    def test_backward_compatible_defaults(self, sample_results):
        """Verify that verify() works with default parameters (backward compatible)."""
        from backend.app.services.verification_service import AnswerVerifier
        v = AnswerVerifier()
        r = v.verify("Employees receive 15 vacation days.", sample_results, "vacation?")
        assert r.faithfulness_score > 0
        assert r.verdict in ("grounded", "partially_grounded", "ungrounded")
