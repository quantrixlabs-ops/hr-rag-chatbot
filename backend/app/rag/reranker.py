"""Re-export of the cross-encoder reranker from retrieval_service."""

from backend.app.services.retrieval_service import Reranker

__all__ = ["Reranker"]
