"""Dependency injection — lazy service singletons wired at startup."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.services.embedding_service import EmbeddingService
    from backend.app.services.ingestion_service import IngestionPipeline
    from backend.app.services.retrieval_service import RetrievalOrchestrator
    from backend.app.services.session_service import SessionStore
    from backend.app.services.chat_service import ChatService
    from backend.app.services.verification_service import AnswerVerifier
    from backend.app.vectorstore.faiss_store import FAISSIndex
    from backend.app.rag.pipeline import RAGPipeline

# Singleton registry — populated during app lifespan startup
_registry: dict = {}


def get_registry() -> dict:
    return _registry


def set_registry(reg: dict) -> None:
    global _registry
    _registry = reg
