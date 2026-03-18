"""Chat service — orchestrates session, RAG, and response formatting — Section 2.2."""

from __future__ import annotations

import time

import structlog

from backend.app.core.security import check_prompt_injection, get_allowed_roles, log_access, sanitize_query
from backend.app.models.chat_models import User
from backend.app.models.session_models import ChatResult
from backend.app.database.session_store import SessionStore
from backend.app.rag.pipeline import RAGPipeline

logger = structlog.get_logger()


class ChatService:
    def __init__(self, session_store: SessionStore, rag_pipeline: RAGPipeline):
        self.sessions = session_store
        self.rag = rag_pipeline

    def handle_query(self, query: str, user: User, session_id: Optional[str] = None) -> ChatResult:
        t0 = time.time()

        # Sanitize input
        query = sanitize_query(query)

        # Validate non-empty after sanitization
        if not query:
            return ChatResult(
                answer="Please enter a question and I'll do my best to help.",
                session_id=session_id or "", citations=[], confidence=0.0,
                faithfulness_score=0.0, query_type="invalid", latency_ms=(time.time() - t0) * 1000,
            )

        # Prompt injection check
        if check_prompt_injection(query):
            logger.warning("prompt_injection_blocked", user_id=user.user_id, query_preview=query[:50])
            return ChatResult(
                answer="I can only answer HR-related questions. Please rephrase your question.",
                session_id=session_id or "", citations=[], confidence=0.0,
                faithfulness_score=0.0, query_type="blocked", latency_ms=(time.time() - t0) * 1000, flagged=True,
            )

        # Session management
        try:
            if session_id:
                session = self.sessions.get_session(session_id)
                if not session:
                    session = self.sessions.create_session(user.user_id, user.role)
            else:
                session = self.sessions.create_session(user.user_id, user.role)
        except Exception as e:
            logger.error("session_management_failed", error=str(e), user_id=user.user_id)
            session = self.sessions.create_session(user.user_id, user.role)

        recent = self.sessions.get_recent_turns(session.session_id, limit=5)

        # RAG pipeline with error boundary
        try:
            result = self.rag.query(query=query, user_role=user.role, session_turns=recent, department=user.department)
        except Exception as e:
            logger.error("rag_pipeline_error", error=str(e), user_id=user.user_id)
            ms = (time.time() - t0) * 1000
            return ChatResult(
                answer="I encountered an error processing your question. Please try again or contact HR directly.",
                session_id=session.session_id, citations=[], confidence=0.0,
                faithfulness_score=0.0, query_type="error", latency_ms=ms,
            )

        # Persist turns
        try:
            self.sessions.add_turn(session.session_id, "user", query)
            self.sessions.add_turn(session.session_id, "assistant", result.answer)
        except Exception as e:
            logger.error("turn_persistence_failed", error=str(e), session_id=session.session_id)

        # Audit
        log_access(user, query, [c.chunk_id for c in result.chunks])

        result.session_id = session.session_id
        result.latency_ms = (time.time() - t0) * 1000
        return result
