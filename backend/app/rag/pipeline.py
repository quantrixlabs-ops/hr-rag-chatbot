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
from backend.app.services.retrieval_service import RetrievalOrchestrator
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
    turns: list[ConversationTurn] | None = None,
    company: str = "Acme Corp",
    hr_contact: str = "your HR department",
) -> str:
    history = ""
    if turns:
        # Limit to last 3 turns and truncate each to prevent context flooding
        for t in turns[-3:]:
            label = "Employee" if t.role == "user" else "HR Assistant"
            # Truncate long turn content to prevent old answers dominating the prompt
            content = t.content[:300] if t.role == "assistant" else t.content[:200]
            history += f"{label}: {content}\n"
    prompt = SYSTEM_PROMPT.format(
        company_name=company,
        hr_contact=hr_contact,
        context=context,
        conversation_history=history or "(Start of conversation)",
    )
    return prompt + f"\nEmployee: {query}\nHR Assistant:"


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

    def query(
        self,
        query: str,
        user_role: str,
        session_turns: list[ConversationTurn] | None = None,
    ) -> ChatResult:
        t0 = time.time()
        analysis = self.qa.analyze(query)

        # ── Stage 0: Ambiguity Detection ─────────────────────────────────
        if analysis.is_ambiguous and analysis.clarification_prompt:
            ms = (time.time() - t0) * 1000
            logger.info("ambiguous_query_detected", query=query[:80], topics=analysis.detected_topics)
            return ChatResult(
                answer=analysis.clarification_prompt,
                session_id="", citations=[], confidence=1.0,
                faithfulness_score=1.0, query_type="clarification", latency_ms=ms,
            )

        # ── Stage 1: Query Expansion + Retrieval ─────────────────────────
        try:
            enriched = _inject_context(query, session_turns) if session_turns else query
            # Expand short/simple queries for better retrieval coverage
            if analysis.complexity == "simple" and len(query.split()) <= 12:
                enriched = self._expand_query(enriched, analysis)
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

        # ── Stage 2: Context + Prompt ────────────────────────────────────
        context = self.ctx.build(chunks)
        prompt = _build_prompt(
            query, context, session_turns,
            self.s.company_name, self.s.hr_contact_email,
        )

        # ── Stage 3: LLM Generation ─────────────────────────────────────
        try:
            llm_resp = self.llm.generate(
                prompt, self.s.llm_model,
                self.s.llm_temperature, self.s.max_response_tokens,
            )
            answer_text = filter_prompt_leakage(llm_resp.text)
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
        verification = self.verifier.verify(answer_text, chunks, query)
        answer = handle_ungrounded(verification, answer_text)

        ms = (time.time() - t0) * 1000
        self._log(query, analysis.query_type, user_role, verification, ms, chunks)

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
        )

        return ChatResult(
            answer=answer,
            session_id="",
            citations=verification.citations,
            confidence=verification.faithfulness_score,
            faithfulness_score=verification.faithfulness_score,
            query_type=analysis.query_type,
            latency_ms=ms,
            chunks=chunks,
            verification=verification,
        )

    def _log(self, query, qtype, role, v, ms, chunks):
        try:
            import hashlib
            import json as _json
            # SECTION 3: Store only query hash — never store raw queries
            query_hash = hashlib.sha256(mask_pii(query).encode()).hexdigest()[:16]
            sources = list({c.source for c in chunks}) if chunks else []
            with sqlite3.connect(self.s.db_path) as con:
                con.execute(
                    "INSERT INTO query_logs (query,query_type,user_role,faithfulness_score,"
                    "hallucination_risk,latency_ms,top_chunk_score,sources_used,timestamp) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (query_hash, qtype, role, v.faithfulness_score, v.hallucination_risk,
                     ms, chunks[0].score if chunks else 0, _json.dumps(sources), time.time()),
                )
        except Exception as e:
            logger.warning("query_log_failed", error=str(e))
