"""End-to-end RAG pipeline — Section 4.

Query → Analysis → Retrieval → Context → Prompt → LLM → Verification → Response

Fixes applied:
- Confidence score properly passed through (was always 0 before)
- Retrieval metadata logged for debugging
- LLM and retrieval errors produce user-friendly messages
"""

from __future__ import annotations

import sqlite3
import time
import traceback

import structlog

from backend.app.core.config import get_settings
from backend.app.core.security import get_allowed_roles, mask_pii
from backend.app.models.session_models import ChatResult, ConversationTurn
from backend.app.prompts.system_prompt import SYSTEM_PROMPT, filter_prompt_leakage
from backend.app.rag.context_builder import ContextBuilder
from backend.app.rag.orchestrator import ModelGateway
from backend.app.rag.query_analyzer import QueryAnalyzer
from backend.app.services.correction_service import CorrectionService
from backend.app.services.faq_service import FAQService
from backend.app.rag.query_normalizer import normalize_query
from backend.app.rag.reasoning_engine import build_reasoning_prompt, parse_reasoning_response, clean_answer_for_user
from backend.app.services.retrieval_service import RetrievalOrchestrator
from backend.app.services.contradiction_detector import ContradictionDetector
from backend.app.services.verification_service import AnswerVerifier, handle_ungrounded

logger = structlog.get_logger()

_NO_DOCS_ANSWER = (
    "I don't have any HR documents indexed yet. "
    "Please ask your HR administrator to upload documents first, "
    "or contact {hr_contact} directly."
)

_LLM_ERROR_ANSWER = (
    "I'm having trouble connecting to the language model right now. "
    "Please try again in a moment, or contact {hr_contact} directly."
)


def _build_prompt(
    query: str,
    context: str,
    turns: Optional[list[ConversationTurn]] = None,
    company: str = "Acme Corp",
    hr_contact: str = "your HR department",
    user_role: str = "employee",
    department: Optional[str] = None,
) -> str:
    history = ""
    if turns:
        # Summarize if too many turns; otherwise include last 3
        if len(turns) > 6:
            history = _summarize_history(turns)
        else:
            for t in turns[-3:]:
                label = "Employee" if t.role == "user" else "HR Assistant"
                content = t.content[:300] if t.role == "assistant" else t.content[:200]
                history += f"{label}: {content}\n"

    # Personalization context based on role and department
    personalization = ""
    if department:
        personalization += f"\nThe employee asking is from the {department} department."
    if user_role == "manager":
        personalization += "\nThis is a manager — they may need team-level policy details."
    elif user_role == "hr_admin":
        personalization += "\nThis is an HR administrator — provide detailed policy references."

    prompt = SYSTEM_PROMPT.format(
        company_name=company,
        hr_contact=hr_contact,
        context=context,
        conversation_history=history or "(Start of conversation)",
    )
    # Note: Guardrails rules are enforced via pre-guard/post-guard middleware
    # (guardrails.py), NOT injected into the LLM prompt. Injecting 1300+ tokens
    # of rules overwhelms small models (llama3:8b) and causes refusals.
    if personalization:
        prompt += personalization
    return prompt + f"\nEmployee: {query}\nHR Assistant:"


def _summarize_history(turns: list[ConversationTurn]) -> str:
    """Compress long conversation history into a brief summary."""
    user_topics = []
    for t in turns:
        if t.role == "user":
            user_topics.append(t.content[:80])
    if not user_topics:
        return "(Start of conversation)"
    recent = turns[-2:]
    summary = f"(Previous topics discussed: {'; '.join(user_topics[:-2])})\n"
    for t in recent:
        label = "Employee" if t.role == "user" else "HR Assistant"
        content = t.content[:300] if t.role == "assistant" else t.content[:200]
        summary += f"{label}: {content}\n"
    return summary


def _inject_context(query: str, turns: list[ConversationTurn]) -> str:
    """Inject conversation context when query contains anaphoric references.

    Only triggers when the query is SHORT and starts with or prominently features
    a pronoun — avoids false positives on normal sentences like "What is this policy?"

    To prevent cross-turn context bleeding:
    - Only inject the previous USER query (not the full assistant response)
    - Keep the injection minimal — just enough for retrieval disambiguation
    - Never inject raw LLM output into the retrieval pipeline
    """
    words = query.lower().split()
    pronouns = {"it", "that", "this", "those", "these"}
    # Only inject if the query is short (likely a follow-up) AND starts with a pronoun
    # or the pronoun is within the first 3 words
    if len(words) <= 10 and any(w in pronouns for w in words[:3]):
        # Use the previous USER query for context, not the assistant response
        # This prevents LLM-generated content from contaminating retrieval
        last_user = next((t for t in reversed(turns) if t.role == "user"), None)
        if last_user:
            # Only inject the topic (first 100 chars of previous user query)
            prev_topic = last_user.content[:100].strip()
            return f"(Previous question was about: {prev_topic})\n{query}"
    return query


class RAGPipeline:
    def __init__(
        self,
        retrieval: RetrievalOrchestrator,
        context_builder: ContextBuilder,
        model_gateway: ModelGateway,
        verifier: AnswerVerifier,
        settings=None,
    ):
        self.retrieval = retrieval
        self.ctx = context_builder
        self.llm = model_gateway
        self.verifier = verifier
        self.s = settings or get_settings()
        self.qa = QueryAnalyzer()
        self.contradiction_detector = ContradictionDetector()
        self.corrections = CorrectionService()
        self.faq = FAQService()

    def _multi_retrieve(self, sub_queries, role_filter, fallback_query):
        """Phase 1: Execute each sub-query separately and merge results (deduplicated)."""
        seen_ids = set()
        merged_chunks = []
        merged_meta = {}

        for sq in sub_queries[:3]:  # Cap at 3 sub-queries to limit latency
            try:
                sq_normalized = normalize_query(sq.strip())
                sq_chunks, sq_meta = self.retrieval.retrieve(sq_normalized, role_filter=role_filter)
                for c in sq_chunks:
                    if c.chunk_id not in seen_ids:
                        seen_ids.add(c.chunk_id)
                        merged_chunks.append(c)
            except Exception as e:
                logger.warning("sub_query_retrieval_failed", sub_query=sq[:60], error=str(e))

        if not merged_chunks:
            # Fallback to single retrieval with the enriched query
            return self.retrieval.retrieve(fallback_query, role_filter=role_filter)

        # Sort merged chunks by score descending, keep top N
        merged_chunks.sort(key=lambda c: c.score, reverse=True)
        max_chunks = 8  # reasonable upper limit
        merged_chunks = merged_chunks[:max_chunks]

        logger.info(
            "multi_retrieval_complete",
            sub_query_count=len(sub_queries),
            total_chunks=len(merged_chunks),
            unique_sources=len({c.source for c in merged_chunks}),
        )
        return merged_chunks, merged_meta

    def _expand_query(self, query: str, analysis) -> str:
        """Use LLM to expand a query for better retrieval coverage."""
        try:
            expand_prompt = (
                "Rewrite this HR question to be more specific and detailed for document search. "
                "Keep it as a single question. Only output the rewritten question, nothing else.\n\n"
                f"Original: {query}\n"
                "Rewritten:"
            )
            resp = self.llm.generate(expand_prompt, self.s.llm_model, 0.0, 100)
            expanded = resp.text.strip().strip('"')
            if expanded and len(expanded) > len(query) * 0.5 and len(expanded) < 500:
                logger.info("query_expanded", original=query[:80], expanded=expanded[:80])
                return expanded
        except Exception:
            pass  # Fall back to original query
        return query

    def _generate_suggestions(self, query: str, answer: str, chunks: list) -> list:
        """Generate 2-3 follow-up question suggestions based on ACTUAL document sources.

        Only suggests questions about topics that exist in the uploaded documents.
        Never suggests questions the system can't answer.
        """
        # Get the actual document titles from the retrieved chunks
        sources = list({c.source for c in chunks})
        query_lower = query.lower()
        suggestions = []

        # Map real document titles to relevant follow-up questions
        for source in sources:
            src = source.lower()
            if "leave" in src and "leave" not in query_lower:
                suggestions.append("What are the types of leave available?")
            elif "harassment" in src and "harassment" not in query_lower:
                suggestions.append("What is the anti-harassment policy?")
            elif "conduct" in src and "conduct" not in query_lower:
                suggestions.append("What does the code of conduct cover?")
            elif "disciplin" in src and "disciplin" not in query_lower:
                suggestions.append("What is the disciplinary process?")
            elif "exit" in src or "separation" in src:
                suggestions.append("What is the exit process?")
            elif "attendance" in src and "attendance" not in query_lower:
                suggestions.append("What is the attendance policy?")
            elif "payroll" in src and "payroll" not in query_lower:
                suggestions.append("How does payroll work?")
            elif "medical" in src and "medical" not in query_lower:
                suggestions.append("What does the medical policy cover?")
            elif "conflict" in src and "conflict" not in query_lower:
                suggestions.append("What is the conflict of interest policy?")
            elif "safety" in src or "emergency" in src:
                suggestions.append("What are the safety guidelines?")
            elif "training" in src or "education" in src:
                suggestions.append("What training programs are available?")
            elif "transfer" in src or "relocation" in src:
                suggestions.append("What is the transfer policy?")

        # Deduplicate and filter out the current question
        seen = set()
        unique = []
        for s in suggestions:
            if s.lower() not in seen and s.lower() != query_lower:
                seen.add(s.lower())
                unique.append(s)

        return unique[:3]

    # ── Phase 2: Multi-question decomposition ──────────────────────────────

    def _answer_compound_query(
        self,
        analysis,
        user_role: str,
        session_turns,
        department,
        role_filter,
        t0: float,
    ) -> ChatResult:
        """Answer each sub-query independently, then merge into a structured response.

        This avoids the problem where a single LLM call with merged context
        ignores one of the questions or conflates topics.
        """
        sub_answers = []
        all_chunks = []
        all_citations = []
        min_confidence = 1.0
        seen_chunk_ids = set()

        for i, sq in enumerate(analysis.sub_queries[:3]):
            try:
                sq_normalized = normalize_query(sq.strip())
                sq_chunks, _ = self.retrieval.retrieve(sq_normalized, role_filter=role_filter)
            except Exception as e:
                logger.warning("sub_query_retrieval_failed", sub_query=sq[:60], error=str(e))
                sq_chunks = []

            if not sq_chunks:
                sub_answers.append({
                    "question": sq.strip(),
                    "answer": "I don't have enough information in our HR documents to answer this part.",
                    "confidence": 0.0,
                    "citations": [],
                })
                continue

            # Deduplicate chunks across sub-queries
            unique_chunks = []
            for c in sq_chunks:
                if c.chunk_id not in seen_chunk_ids:
                    seen_chunk_ids.add(c.chunk_id)
                    unique_chunks.append(c)
                    all_chunks.append(c)

            context = self.ctx.build(unique_chunks if unique_chunks else sq_chunks)
            prompt = _build_prompt(
                sq.strip(), context, session_turns,
                self.s.company_name, self.s.hr_contact_email,
                user_role, department,
            )

            try:
                llm_resp = self.llm.generate(
                    prompt, self.s.llm_model,
                    self.s.llm_temperature, self.s.max_response_tokens,
                )
                answer_text = filter_prompt_leakage(llm_resp.text)
            except Exception as e:
                logger.error("sub_query_llm_failed", sub_query=sq[:60], error=str(e))
                sub_answers.append({
                    "question": sq.strip(),
                    "answer": "I encountered an error answering this part. Please try again.",
                    "confidence": 0.0,
                    "citations": [],
                })
                continue

            verification = self.verifier.verify(
                answer_text, sq_chunks, sq.strip(),
                intent=analysis.intent,
                analysis_confidence=analysis.analysis_confidence,
            )
            answer_text = handle_ungrounded(verification, answer_text)
            min_confidence = min(min_confidence, verification.faithfulness_score)
            all_citations.extend(verification.citations)

            sub_answers.append({
                "question": sq.strip(),
                "answer": answer_text,
                "confidence": verification.faithfulness_score,
                "citations": verification.citations,
            })

        # ── Merge into structured response ────────────────────────────────
        merged = self._merge_sub_answers(sub_answers)

        # Deduplicate citations by source name
        seen_sources = set()
        unique_citations = []
        for c in all_citations:
            if c.source not in seen_sources:
                seen_sources.add(c.source)
                unique_citations.append(c)

        # Content safety + PII on merged answer
        from backend.app.core.content_safety import check_content_safety, sanitize_response
        safety = check_content_safety(merged)
        merged = sanitize_response(merged)
        merged = mask_pii(merged)

        ms = (time.time() - t0) * 1000
        suggestions = self._generate_suggestions(
            analysis.original_query, merged, all_chunks
        )

        return ChatResult(
            answer=merged,
            session_id="",
            citations=unique_citations,
            confidence=min_confidence,
            faithfulness_score=min_confidence,
            query_type="compound",
            latency_ms=ms,
            flagged=not safety["safe"],
            chunks=all_chunks,
            suggested_questions=suggestions,
            intent=analysis.intent,
            analysis_confidence=analysis.analysis_confidence,
            is_sensitive=analysis.is_sensitive,
            emotional_tone=analysis.emotional_tone,
        )

    def _merge_sub_answers(self, sub_answers: list) -> str:
        """Merge multiple sub-answers into a well-structured combined response."""
        if len(sub_answers) == 1:
            return sub_answers[0]["answer"]

        parts = []
        for i, sa in enumerate(sub_answers, 1):
            q = sa["question"]
            a = sa["answer"]
            # Strip existing disclaimers from sub-answers to avoid repetition
            a = a.replace(
                "I don't have enough information in our HR documents to answer this question accurately. "
                "Please contact your HR department directly for assistance.", ""
            ).replace(
                "**Note:** Some details below may not be fully covered in our HR documents. "
                "Please verify with HR for anything not explicitly cited.\n\n", ""
            ).strip()
            parts.append(f"**{i}. {q}**\n\n{a}")

        return "\n\n---\n\n".join(parts)

    # ── Phase 1: Sensitive & emotional handling helpers ───────────────────

    def _get_sensitive_guidance(self, analysis) -> str:
        """Return a tailored guidance suffix for sensitive topics."""
        guidance = {
            "termination": (
                "\n\n**Important:** Questions about termination are sensitive. "
                "For your specific situation, please contact HR directly at {hr_contact}. "
                "All conversations regarding employment status are confidential."
            ),
            "harassment": (
                "\n\n**Important:** If you are experiencing harassment, please report it immediately. "
                "You can contact HR at {hr_contact}, your manager, or use the anonymous ethics hotline. "
                "All reports are treated confidentially and retaliation is strictly prohibited."
            ),
            "disciplinary": (
                "\n\n**Note:** For questions about your specific disciplinary situation, "
                "please speak with your manager or HR at {hr_contact} directly."
            ),
            "salary_negotiation": (
                "\n\n**Note:** For specific compensation discussions, please schedule a meeting "
                "with your manager or HR at {hr_contact}."
            ),
            "whistleblower": (
                "\n\n**Important:** Whistleblower protections are taken very seriously. "
                "If you need to report a concern, you can do so anonymously through the ethics hotline "
                "or contact HR at {hr_contact}. Retaliation against whistleblowers is prohibited."
            ),
        }
        template = guidance.get(analysis.sensitive_category, "")
        return template.format(hr_contact=self.s.hr_contact_email) if template else ""

    def _get_emotional_acknowledgment(self, tone: str) -> str:
        """Return an empathetic opening for emotionally charged queries."""
        acknowledgments = {
            "stressed": "I understand this can be a stressful situation. ",
            "worried": "I understand you may be concerned. Let me help clarify. ",
            "frustrated": "I hear your frustration. Let me provide the relevant information. ",
            "upset": "I'm sorry you're going through this. Here's what I can share. ",
        }
        return acknowledgments.get(tone, "")

    def query(
        self,
        query: str,
        user_role: str,
        session_turns: Optional[list[ConversationTurn]] = None,
        department: Optional[str] = None,
    ) -> ChatResult:
        t0 = time.time()
        analysis = self.qa.analyze(query)

        # ── Stage -1: Smart routing — redirect non-HR queries ────────────
        if analysis.domain in ("it", "personal") and analysis.redirect_message:
            ms = (time.time() - t0) * 1000
            logger.info("query_routed", domain=analysis.domain, query=query[:80])
            return ChatResult(
                answer=analysis.redirect_message,
                session_id="", citations=[], confidence=1.0,
                faithfulness_score=1.0, query_type="redirect", latency_ms=ms,
            )
        if analysis.domain == "greeting":
            ms = (time.time() - t0) * 1000
            return ChatResult(
                answer="Hello! I'm your HR assistant. I can help with questions about company policies, "
                       "benefits, leave, onboarding, and more. What would you like to know?",
                session_id="", citations=[], confidence=1.0,
                faithfulness_score=1.0, query_type="greeting", latency_ms=ms,
            )

        # ── Stage 0: CFLS correction check — HR-approved overrides (HIGHEST PRIORITY)
        try:
            correction = self.corrections.match(query)
            if correction:
                ms = (time.time() - t0) * 1000
                return ChatResult(
                    answer=correction["corrected_response"],
                    session_id="", citations=[], confidence=1.0,
                    faithfulness_score=1.0, query_type="correction", latency_ms=ms,
                )
        except Exception as e:
            logger.warning("cfls_correction_lookup_failed", error=str(e))

        # ── Stage 0a: FAQ fast-path — curated answers bypass RAG ─────────
        try:
            faq_match = self.faq.match(query)
            if faq_match:
                ms = (time.time() - t0) * 1000
                logger.info("faq_hit", query=query[:80], faq_id=faq_match["faq_id"],
                            score=faq_match["score"])
                return ChatResult(
                    answer=faq_match["answer"],
                    session_id="", citations=[], confidence=1.0,
                    faithfulness_score=1.0, query_type="faq", latency_ms=ms,
                )
        except Exception as e:
            logger.warning("faq_lookup_failed", error=str(e))

        # ── Stage 0: Language check ──────────────────────────────────────
        if analysis.language != "en":
            ms = (time.time() - t0) * 1000
            lang_names = {"es": "Spanish", "fr": "French", "de": "German", "zh": "Chinese",
                          "ja": "Japanese", "ko": "Korean", "ar": "Arabic", "hi": "Hindi", "ta": "Tamil"}
            lang_name = lang_names.get(analysis.language, analysis.language)
            return ChatResult(
                answer=f"I detected your query may be in {lang_name}. Currently I support English only. "
                       "Please rephrase your question in English and I'll be happy to help.",
                session_id="", citations=[], confidence=1.0,
                faithfulness_score=1.0, query_type="language_unsupported", latency_ms=ms,
            )

        # ── Stage 1: Ambiguity Detection ─────────────────────────────────
        if analysis.is_ambiguous and analysis.clarification_prompt:
            ms = (time.time() - t0) * 1000
            logger.info("ambiguous_query_detected", query=query[:80], topics=analysis.detected_topics)
            return ChatResult(
                answer=analysis.clarification_prompt,
                session_id="", citations=[], confidence=1.0,
                faithfulness_score=1.0, query_type="clarification", latency_ms=ms,
            )

        # ── Phase 2: Compound query decomposition (Phase 4: safe fallback) ──
        if analysis.requires_multi_retrieval and len(analysis.sub_queries) > 1:
            role_filter = get_allowed_roles(user_role)
            try:
                return self._answer_compound_query(
                    analysis, user_role, session_turns, department, role_filter, t0,
                )
            except Exception as e:
                logger.error("compound_query_failed_fallback_to_single", error=str(e))
                # Fall through to single-query path instead of crashing

        # ── Stage 1: Query Expansion + Retrieval ─────────────────────────
        try:
            enriched = _inject_context(query, session_turns) if session_turns else query
            # Normalize informal phrasing → formal HR terms for better retrieval
            enriched = normalize_query(enriched)
            role_filter = get_allowed_roles(user_role)
            chunks, retrieval_meta = self.retrieval.retrieve(enriched, role_filter=role_filter)
        except Exception as e:
            logger.error("retrieval_failed", error=str(e))
            chunks, retrieval_meta = [], {}

        if not chunks:
            ms = (time.time() - t0) * 1000
            return ChatResult(
                answer=_NO_DOCS_ANSWER.format(hr_contact=self.s.hr_contact_email),
                session_id="", citations=[], confidence=0.0,
                faithfulness_score=0.0, query_type=analysis.query_type, latency_ms=ms,
            )

        # ── Stage 1b: Contradiction detection (Phase 2, Phase 4: safe fallback) ─
        try:
            contradiction_result = self.contradiction_detector.detect(chunks, query)
            contradiction_warning = contradiction_result.warning_message if contradiction_result.has_contradictions else ""
        except Exception as e:
            logger.warning("contradiction_detection_failed", error=str(e))
            from backend.app.services.contradiction_detector import ContradictionResult
            contradiction_result = ContradictionResult(has_contradictions=False, contradictions=[], warning_message="")
            contradiction_warning = ""

        # ── Stage 1c: Sensitive query guidance (Phase 1) ──────────────────
        sensitive_prefix = ""
        if analysis.is_sensitive:
            sensitive_prefix = self._get_sensitive_guidance(analysis)
        emotional_prefix = ""
        if analysis.emotional_tone and analysis.emotional_tone != "neutral":
            emotional_prefix = self._get_emotional_acknowledgment(analysis.emotional_tone)

        # ── Stage 2: Context + Prompt (with personalization) ─────────────
        context = self.ctx.build(chunks)
        prompt = _build_prompt(
            query, context, session_turns,
            self.s.company_name, self.s.hr_contact_email,
            user_role, department,
        )

        # ── Stage 2b: Reasoning Engine — only for complex queries ──────────
        # Simple queries work better without extra reasoning instructions
        # (llama3:8b gets confused by structured output formatting on easy questions)
        needs_reasoning = (
            analysis.complexity == "complex"
            or analysis.is_sensitive
            or analysis.is_calculation
            or contradiction_result.has_contradictions
        )
        if needs_reasoning:
            prompt = build_reasoning_prompt(
                prompt, query,
                analysis_intent=analysis.intent,
                is_calculation=analysis.is_calculation,
                is_sensitive=analysis.is_sensitive,
                has_contradictions=contradiction_result.has_contradictions,
                user_role=user_role,
                complexity=analysis.complexity,
            )

        # ── Stage 2c: Model routing — select optimal model for query type ──
        from backend.app.rag.model_router import select_model
        selected_model, model_tier = select_model(
            complexity=analysis.complexity,
            intent=analysis.intent,
            is_sensitive=analysis.is_sensitive,
            is_calculation=analysis.is_calculation,
            requires_multi_retrieval=analysis.requires_multi_retrieval,
            query_type=analysis.query_type,
        )

        # ── Stage 3: LLM Generation ─────────────────────────────────────
        try:
            llm_resp = self.llm.generate(
                prompt, selected_model,
                self.s.llm_temperature, self.s.max_response_tokens,
            )
            # Parse output: structured if reasoning was injected, plain otherwise
            if needs_reasoning:
                reasoning = parse_reasoning_response(llm_resp.text)
                answer_text = filter_prompt_leakage(
                    clean_answer_for_user(reasoning, user_role)
                )
            else:
                answer_text = filter_prompt_leakage(llm_resp.text.strip())
            logger.info("llm_generation_complete",
                        model_used=selected_model, model_tier=model_tier,
                        reasoning_used=needs_reasoning,
                        answer_len=len(answer_text))
        except Exception as e:
            logger.error("llm_generation_failed", error=str(e), traceback=traceback.format_exc())
            ms = (time.time() - t0) * 1000
            return ChatResult(
                answer=_LLM_ERROR_ANSWER.format(hr_contact=self.s.hr_contact_email),
                session_id="", citations=[], confidence=0.0,
                faithfulness_score=0.0, query_type=analysis.query_type,
                latency_ms=ms, chunks=chunks,
            )

        # ── Stage 4: Verification ────────────────────────────────────────
        verification = self.verifier.verify(
            answer_text, chunks, query,
            intent=analysis.intent,
            analysis_confidence=analysis.analysis_confidence,
        )
        answer = handle_ungrounded(verification, answer_text)

        # ── Stage 4a-ii: Prepend sensitive/emotional context (Phase 1) ────
        if emotional_prefix and not answer.startswith("I don't have enough") and not answer.startswith("**Note:**"):
            answer = emotional_prefix + answer
        if sensitive_prefix and not answer.startswith("I don't have enough"):
            answer = answer + sensitive_prefix

        # ── Stage 4a-iii: Append contradiction warning (Phase 2) ──────────
        if contradiction_warning:
            answer = answer + contradiction_warning

        # ── Stage 4b: Content safety filter ──────────────────────────────
        from backend.app.core.content_safety import check_content_safety, sanitize_response
        safety = check_content_safety(answer)
        answer = sanitize_response(answer)
        flagged = not safety["safe"]

        # ── Stage 4c: PII scrubbing on outbound response ────────────────
        answer = mask_pii(answer)

        # ── Stage 4d: Guardrails post-guard — validate output ──────────
        from backend.app.core.guardrails import post_guard
        guard_check = post_guard(answer, query)
        if not guard_check.passed:
            answer = guard_check.message
            flagged = True

        ms = (time.time() - t0) * 1000
        self._log(query, analysis.query_type, user_role, verification, ms, chunks)

        # ── Stage 4d: Response versioning (audit trail) ──────────────────
        self._store_version(query, answer, verification, safety, chunks)

        # Log source documents used — verify correct docs are retrieved
        sources_used = list({c.source for c in chunks})
        logger.info(
            "rag_pipeline_complete",
            query_type=analysis.query_type,
            chunks_used=len(chunks),
            sources_used=sources_used,
            top_chunk_score=chunks[0].score if chunks else 0,
            bottom_chunk_score=chunks[-1].score if chunks else 0,
            confidence=verification.faithfulness_score,
            citation_count=len(verification.citations),
            verdict=verification.verdict,
            latency_ms=round(ms),
            # Phase 4: Extended audit fields
            intent=analysis.intent,
            is_sensitive=analysis.is_sensitive,
            has_contradictions=contradiction_result.has_contradictions,
        )

        # ── Phase 4: Audit trail for sensitive/flagged queries ────────────
        if analysis.is_sensitive or flagged or contradiction_result.has_contradictions:
            from backend.app.core.security import log_security_event
            log_security_event("query_audit_trail", {
                "intent": analysis.intent,
                "is_sensitive": analysis.is_sensitive,
                "sensitive_category": analysis.sensitive_category,
                "has_contradictions": contradiction_result.has_contradictions,
                "flagged": flagged,
                "confidence": round(verification.faithfulness_score, 3),
                "query_type": analysis.query_type,
            })

        # ── Stage 5: Generate follow-up suggestions ─────────────────────
        suggestions = self._generate_suggestions(query, answer, chunks)

        return ChatResult(
            answer=answer,
            session_id="",
            citations=verification.citations,
            confidence=verification.faithfulness_score,
            faithfulness_score=verification.faithfulness_score,
            query_type=analysis.query_type,
            latency_ms=ms,
            flagged=flagged,
            chunks=chunks,
            verification=verification,
            suggested_questions=suggestions,
            intent=analysis.intent,
            analysis_confidence=analysis.analysis_confidence,
            is_sensitive=analysis.is_sensitive,
            emotional_tone=analysis.emotional_tone,
            has_contradictions=contradiction_result.has_contradictions,
        )

    def _store_version(self, query, answer, verification, safety, chunks):
        """Store response version for audit trail (Phase 3)."""
        try:
            import hashlib
            import json as _json
            query_hash = hashlib.sha256(mask_pii(query).encode()).hexdigest()[:16]
            sources = list({c.source for c in chunks}) if chunks else []
            with sqlite3.connect(self.s.db_path) as con:
                con.execute(
                    "INSERT INTO response_versions "
                    "(session_id, query_hash, answer, confidence, faithfulness, verdict, "
                    "sources_used, safety_issues, model, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    ("", query_hash, answer[:2000], verification.faithfulness_score,
                     verification.faithfulness_score, verification.verdict,
                     _json.dumps(sources), _json.dumps(safety.get("issues", [])),
                     self.s.llm_model, time.time()),
                )
        except Exception as e:
            logger.warning("response_version_failed", error=str(e))

    def _log(self, query, qtype, role, v, ms, chunks):
        try:
            import hashlib
            import json as _json
            from backend.app.core.tenant import get_current_tenant
            # SECTION 3: Store only query hash — never store raw queries
            query_hash = hashlib.sha256(mask_pii(query).encode()).hexdigest()[:16]
            sources = list({c.source for c in chunks}) if chunks else []
            tenant_id = get_current_tenant()
            with sqlite3.connect(self.s.db_path) as con:
                con.execute(
                    "INSERT INTO query_logs (query,query_type,user_role,faithfulness_score,"
                    "hallucination_risk,latency_ms,top_chunk_score,sources_used,timestamp,tenant_id) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (query_hash, qtype, role, v.faithfulness_score, v.hallucination_risk,
                     ms, chunks[0].score if chunks else 0, _json.dumps(sources), time.time(), tenant_id),
                )
        except Exception as e:
            logger.warning("query_log_failed", error=str(e))
