"""Qdrant vector store — Phase 1 primary vector backend.

Design decisions:
- Single collection `hr_chunks` for all tenants in Phase 1-3
- tenant_id stored in every chunk payload (Phase 3 hook: filter by tenant)
- access_roles stored in payload for RBAC filtering
- All searches filtered by tenant_id to prevent cross-tenant data leakage
"""

from __future__ import annotations

import uuid

import structlog

from backend.app.models.document_models import ChunkMetadata, SearchResult

logger = structlog.get_logger()

# Default tenant UUID — single tenant in Phase 1
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"


class QdrantStore:
    """Qdrant-backed vector store with tenant isolation and RBAC filtering."""

    def __init__(
        self,
        url: str = "http://localhost:6333",
        collection: str = "hr_chunks",
        dimension: int = 768,
    ):
        self.url = url
        self.collection = collection
        self.dimension = dimension
        self._client = None

    # ── Client ───────────────────────────────────────────────────────────────

    def _get_client(self):
        if self._client is None:
            try:
                from qdrant_client import QdrantClient
                self._client = QdrantClient(url=self.url, timeout=30)
            except ImportError:
                raise RuntimeError(
                    "qdrant-client not installed — run: pip install qdrant-client"
                )
        return self._client

    # ── Collection management ─────────────────────────────────────────────────

    def ensure_collection(self) -> None:
        """Create the collection if it doesn't exist. Idempotent."""
        from qdrant_client.models import Distance, VectorParams
        client = self._get_client()
        existing = [c.name for c in client.get_collections().collections]
        if self.collection not in existing:
            client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=self.dimension, distance=Distance.COSINE),
            )
            logger.info("qdrant_collection_created", collection=self.collection, dim=self.dimension)
        else:
            logger.debug("qdrant_collection_exists", collection=self.collection)

    # ── Write ─────────────────────────────────────────────────────────────────

    def add(
        self,
        embeddings,
        metadata: list[ChunkMetadata],
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        """Store embeddings with metadata payload. tenant_id is written on every chunk."""
        from qdrant_client.models import PointStruct
        client = self._get_client()

        points = []
        for i, m in enumerate(metadata):
            # Ensure chunk_id is a valid UUID string for Qdrant point ID
            chunk_id = m.chunk_id if m.chunk_id else str(uuid.uuid4())

            points.append(
                PointStruct(
                    id=chunk_id,
                    vector=embeddings[i].tolist(),
                    payload={
                        # Phase 3 scalability hook: tenant_id on every chunk
                        "tenant_id": tenant_id,
                        # Content
                        "text": m.text,
                        "source": m.source,
                        "document_id": m.document_id,
                        "chunk_index": m.chunk_index,
                        "page": m.page,
                        "section_heading": m.section_heading,
                        # Access control
                        "access_roles": m.access_roles,
                        # Classification
                        "category": m.category,
                    },
                )
            )

        if points:
            client.upsert(collection_name=self.collection, points=points)
            logger.info(
                "qdrant_chunks_stored",
                count=len(points),
                tenant_id=tenant_id,
                collection=self.collection,
            )

    # ── Read ──────────────────────────────────────────────────────────────────

    def search(
        self,
        query_embedding,
        top_k: int = 20,
        role_filter: list[str] | None = None,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> list[SearchResult]:
        """Retrieve top-K chunks. Always filtered by tenant_id. Optionally filtered by role."""
        from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

        client = self._get_client()

        # Build filter conditions — tenant_id is ALWAYS applied
        must_conditions = [
            FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))
        ]

        # RBAC filter: if role_filter provided, chunk must have at least one matching role
        if role_filter:
            must_conditions.append(
                FieldCondition(key="access_roles", match=MatchAny(any=role_filter))
            )

        query_filter = Filter(must=must_conditions)

        hits = client.search(
            collection_name=self.collection,
            query_vector=query_embedding.tolist(),
            query_filter=query_filter,
            limit=top_k,
        )

        return [
            SearchResult(
                chunk_id=str(h.id),
                text=h.payload.get("text", ""),
                score=h.score,
                source=h.payload.get("source", ""),
                page=h.payload.get("page"),
                metadata=h.payload,
            )
            for h in hits
        ]

    # ── Delete ────────────────────────────────────────────────────────────────

    def delete_by_document(
        self,
        document_id: str,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> int:
        """Delete all chunks for a document. Returns count deleted."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        client = self._get_client()

        delete_filter = Filter(
            must=[
                FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)),
                FieldCondition(key="document_id", match=MatchValue(value=document_id)),
            ]
        )

        result = client.delete(
            collection_name=self.collection,
            points_selector=delete_filter,
        )

        deleted_count = getattr(result, "operation_id", 0)
        logger.info(
            "qdrant_chunks_deleted",
            document_id=document_id,
            tenant_id=tenant_id,
        )
        return deleted_count

    # ── Stats ─────────────────────────────────────────────────────────────────

    @property
    def total_chunks(self) -> int:
        try:
            client = self._get_client()
            info = client.get_collection(self.collection)
            return info.points_count or 0
        except Exception:
            return 0

    def chunk_count_for_tenant(self, tenant_id: str = DEFAULT_TENANT_ID) -> int:
        """Count chunks for a specific tenant (Phase 3: per-tenant usage metrics)."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        try:
            client = self._get_client()
            result = client.count(
                collection_name=self.collection,
                count_filter=Filter(
                    must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
                ),
            )
            return result.count
        except Exception:
            return 0

    # ── Health ────────────────────────────────────────────────────────────────

    def health(self) -> dict:
        try:
            client = self._get_client()
            info = client.get_collection(self.collection)
            return {"status": "ok", "points_count": info.points_count}
        except Exception as e:
            return {"status": "error", "detail": str(e)}
