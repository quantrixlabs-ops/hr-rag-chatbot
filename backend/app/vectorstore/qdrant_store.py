"""Qdrant vector store integration — Section 7 (production path).

This module provides the Qdrant client wrapper for production deployments
that need horizontal scaling beyond what FAISS supports.
"""

from __future__ import annotations

import structlog

from backend.app.models.document_models import ChunkMetadata, SearchResult

logger = structlog.get_logger()


class QdrantStore:
    """Qdrant vector store — requires `qdrant-client` package."""

    def __init__(self, url: str = "http://localhost:6333", collection: str = "hr_chunks", dimension: int = 768):
        self.url = url
        self.collection = collection
        self.dimension = dimension
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from qdrant_client import QdrantClient
                self._client = QdrantClient(url=self.url)
            except ImportError:
                raise RuntimeError("qdrant-client not installed — pip install qdrant-client")
        return self._client

    def ensure_collection(self) -> None:
        from qdrant_client.models import Distance, VectorParams
        client = self._get_client()
        collections = [c.name for c in client.get_collections().collections]
        if self.collection not in collections:
            client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=self.dimension, distance=Distance.COSINE),
            )
            logger.info("qdrant_collection_created", collection=self.collection)

    def add(self, embeddings, metadata: list[ChunkMetadata]) -> None:
        from qdrant_client.models import PointStruct
        client = self._get_client()
        points = [
            PointStruct(
                id=m.chunk_id, vector=embeddings[i].tolist(),
                payload={"text": m.text, "source": m.source, "page": m.page,
                         "document_id": m.document_id, "access_roles": m.access_roles,
                         "category": m.category, "chunk_index": m.chunk_index,
                         "section_heading": m.section_heading},
            )
            for i, m in enumerate(metadata)
        ]
        client.upsert(collection_name=self.collection, points=points)

    def search(self, query_embedding, top_k: int = 20, role_filter: list[str] | None = None) -> list[SearchResult]:
        from qdrant_client.models import FieldCondition, Filter, MatchAny
        client = self._get_client()
        qf = None
        if role_filter:
            qf = Filter(must=[FieldCondition(key="access_roles", match=MatchAny(any=role_filter))])
        hits = client.search(collection_name=self.collection, query_vector=query_embedding.tolist(), query_filter=qf, limit=top_k)
        return [
            SearchResult(chunk_id=h.id, text=h.payload["text"], score=h.score,
                         source=h.payload.get("source", ""), page=h.payload.get("page"),
                         metadata=h.payload)
            for h in hits
        ]
