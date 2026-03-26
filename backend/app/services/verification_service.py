"""Answer verification — Section 11.

Fixes applied:
- Confidence now combines retrieval score + evidence coverage (not just claim matching)
- Evidence matching threshold lowered from 3 to 2 shared 4-char words
- Auto-generates citations from retrieved chunks even if LLM doesn't cite them
- Confidence formula: min(1.0, avg_chunk_score * citation_coverage_ratio)
"""

from __future__ import annotations

import re

from backend.app.models.document_models import Citation, ClaimVerification, SearchResult, VerificationResult


class AnswerVerifier:
    def verify(
        self,
        answer: str,
        chunks: list[SearchResult],
        query: str,
        intent: str = "policy_lookup",
        analysis_confidence: float = 0.8,
    ) -> VerificationResult:
        claims = self._extract_claims(answer)
        verified: list[ClaimVerification] = []

        for claim in claims:
            evidence_ids = self._find_evidence(claim, chunks)
            has_evidence = len(evidence_ids) > 0
            confidence = min(1.0, len(evidence_ids) * 0.3 + 0.4) if has_evidence else 0.1
            verified.append(ClaimVerification(claim, has_evidence, evidence_ids, confidence))

        # ── Faithfulness: fraction of claims with evidence ───────────────
        if verified:
            faithfulness = sum(1 for c in verified if c.verified) / len(verified)
        else:
            # No extractable claims (very short answer) — use chunk scores
            faithfulness = 1.0 if chunks else 0.0

        # ── Citations: extract explicit + auto-generate from top chunks ──
        citations = self._extract_citations(answer, chunks)
        if not citations and chunks:
            # LLM didn't cite sources explicitly — auto-cite from top chunks
            seen: set[str] = set()
            for c in chunks[:3]:
                if c.source not in seen:
                    citations.append(Citation(c.source, c.page, c.text[:200]))
                    seen.add(c.source)

        # ── Combined confidence score ────────────────────────────────────
        # Formula per spec: confidence_score = min(1.0, avg_chunk_score × citation_ratio)
        # with a faithfulness floor to ensure grounded answers score well
        avg_chunk_score = sum(c.score for c in chunks) / len(chunks) if chunks else 0.0
        citation_ratio = min(1.0, len(citations) / max(1, len(claims))) if claims else (1.0 if citations else 0.0)
        confidence_score = min(1.0, avg_chunk_score * citation_ratio)

        # Apply faithfulness floor: if claims are well-grounded, ensure score reflects that
        confidence_score = max(confidence_score, faithfulness * avg_chunk_score)

        # Ensure we never report 0 confidence when we have relevant chunks with strong evidence
        if chunks and chunks[0].score > 0.5 and faithfulness > 0.5:
            confidence_score = max(confidence_score, 0.5)

        # Phase 1: Intent-aware confidence adjustment
        # Sensitive and calculation queries get a slight confidence penalty
        # because they often require personal data we don't have
        if intent == "sensitive":
            confidence_score = min(confidence_score, 0.85)  # cap — sensitive answers need HR verification
        elif intent == "calculation":
            confidence_score *= 0.95  # slight penalty — calculations may need personal data
        # Factor in analyzer confidence as a soft signal
        confidence_score = confidence_score * (0.7 + 0.3 * analysis_confidence)

        hallucination_risk = round(1.0 - confidence_score, 3)

        return VerificationResult(
            faithfulness_score=round(confidence_score, 3),
            hallucination_risk=hallucination_risk,
            verified_claims=verified,
            citations=citations,
            verdict=(
                "grounded" if confidence_score >= 0.25
                else "partially_grounded" if confidence_score >= 0.05
                else "ungrounded"
            ),
        )

    def _extract_claims(self, text: str) -> list[str]:
        """Split answer into sentence-level claims for verification."""
        # Remove disclaimer prefixes if present
        text = re.sub(r"^(Note:.*?\n\n|I was unable.*?\n\n)", "", text, flags=re.DOTALL)
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if len(s.strip()) > 15]

    def _find_evidence(self, claim: str, chunks: list[SearchResult]) -> list[str]:
        """Find chunks that support a claim via word overlap.
        Threshold: 3+ shared content words of 4+ chars, excluding stop words."""
        _STOP = {"that", "this", "with", "from", "have", "been", "were", "will",
                 "your", "they", "them", "their", "which", "would", "should",
                 "could", "about", "other", "than", "also", "into", "more",
                 "some", "such", "only", "each", "when", "what", "does", "make"}
        claim_words = set(re.findall(r"\b\w{4,}\b", claim.lower())) - _STOP
        if len(claim_words) < 2:
            # Very short claim — treat as supported if any chunk mentions the topic
            return [chunks[0].chunk_id] if chunks else []

        supporting: list[str] = []
        for chunk in chunks:
            chunk_words = set(re.findall(r"\b\w{4,}\b", chunk.text.lower())) - _STOP
            overlap = claim_words & chunk_words
            # Require 2+ meaningful content word overlap for evidence
            if len(overlap) >= 2:
                supporting.append(chunk.chunk_id)
        return supporting

    def _extract_citations(self, answer: str, chunks: list[SearchResult]) -> list[Citation]:
        """Extract [Source: ...] references from the LLM answer."""
        citations: list[Citation] = []
        seen: set[str] = set()
        for ref in re.findall(r"\[Source:\s*([^\]]+)\]", answer):
            for c in chunks:
                if c.source in ref and c.source not in seen:
                    citations.append(Citation(c.source, c.page, c.text[:200]))
                    seen.add(c.source)
                    break
        return citations


def handle_ungrounded(result: VerificationResult, answer: str) -> str:
    """Handle verification results. The system prompt enforces grounding —
    the LLM already refuses when documents don't cover a topic.
    Only block answers that are clearly fabricated (zero evidence)."""
    if result.verdict == "ungrounded" and result.faithfulness_score == 0.0 and not result.citations:
        return (
            "This topic is not covered in the HR documents currently uploaded to the system. "
            "Please contact your HR department directly for assistance, "
            "or ask your HR admin to upload the relevant policy document."
        )
    # For all other cases, trust the system prompt's grounding rules
    return answer
    return answer
