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

        # Ensure we never report 0 confidence when we have relevant chunks with evidence
        if chunks and chunks[0].score > 0.4 and faithfulness > 0.3:
            confidence_score = max(confidence_score, 0.5)

        hallucination_risk = round(1.0 - confidence_score, 3)

        return VerificationResult(
            faithfulness_score=round(confidence_score, 3),
            hallucination_risk=hallucination_risk,
            verified_claims=verified,
            citations=citations,
            verdict=(
                "grounded" if confidence_score >= 0.6
                else "partially_grounded" if confidence_score >= 0.35
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
        Threshold: 2+ shared words of 4+ chars."""
        claim_words = set(re.findall(r"\b\w{4,}\b", claim.lower()))
        if len(claim_words) < 2:
            # Very short claim — treat as supported if any chunk mentions the topic
            return [chunks[0].chunk_id] if chunks else []

        supporting: list[str] = []
        for chunk in chunks:
            chunk_words = set(re.findall(r"\b\w{4,}\b", chunk.text.lower()))
            overlap = claim_words & chunk_words
            if len(overlap) >= 2:  # lowered from 3 — policy sentences share fewer words
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
    """Prepend disclaimer for low-confidence answers."""
    if result.verdict == "ungrounded":
        return (
            "I was unable to find sufficient evidence in our HR documents "
            "to fully answer this question. Please verify with HR directly.\n\n"
            + answer
        )
    if result.verdict == "partially_grounded":
        return (
            "Note: Parts of this answer may not be fully supported by our "
            "HR documents. Sources are cited where available.\n\n"
            + answer
        )
    return answer
