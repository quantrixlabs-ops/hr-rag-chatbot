"""Async document ingestion task — Phase 2.

Moves document processing off the HTTP request thread.
The API enqueues this task and returns immediately with job_id.

Retry strategy: exponential backoff — 30s, 60s, 120s — max 3 attempts.
Status tracking: SQLite documents table (ingestion_status field).

Phase 4 hook: add hrms_sync_task, report_generation_task here.
"""

from __future__ import annotations

import os
import time
from typing import Optional

import structlog

from backend.app.workers.celery_app import app
from backend.app.core.config import get_settings

logger = structlog.get_logger()

# ── OpenMP env vars — must be set before any ML import ───────────────────────
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def _get_services():
    """Build services needed for ingestion — called inside task, not at import."""
    s = get_settings()

    from backend.app.services.embedding_service import EmbeddingService
    emb = EmbeddingService(
        s.embedding_model, s.embedding_provider,
        s.ollama_base_url, s.embedding_dimension
    )

    # Vector store — Qdrant or FAISS based on config
    if s.vector_store_backend == "qdrant":
        from backend.app.vectorstore.qdrant_store import QdrantStore
        vs = QdrantStore(url=s.qdrant_url, collection=s.qdrant_collection, dimension=s.embedding_dimension)
        vs.ensure_collection()
    else:
        from backend.app.vectorstore.faiss_store import FAISSIndex
        vs = FAISSIndex(s.embedding_dimension, s.faiss_index_dir)
        vs.load()

    from backend.app.services.retrieval_service import BM25Retriever
    bm25 = BM25Retriever()

    from backend.app.services.ingestion_service import IngestionPipeline
    pipeline = IngestionPipeline(emb, vs, bm25)

    return pipeline


def _update_status(document_id: str, status: str, chunk_count: int = 0, error: Optional[str] = None):
    """Update document ingestion status in both SQLite and PostgreSQL."""
    s = get_settings()

    # SQLite update
    try:
        import sqlite3
        with sqlite3.connect(s.db_path) as con:
            con.execute(
                "UPDATE documents SET ingestion_status=? WHERE document_id=?",
                (status, document_id),
            )
    except Exception as e:
        logger.warning("sqlite_status_update_failed", doc_id=document_id, error=str(e))

    # PostgreSQL update
    try:
        if s.database_url.startswith("postgresql"):
            import uuid as _uuid
            from backend.app.database.postgres import update_document_status
            update_document_status(
                _uuid.UUID(document_id),
                status=status,
                chunk_count=chunk_count,
                error=error,
            )
    except Exception as e:
        logger.warning("postgres_status_update_failed", doc_id=document_id, error=str(e))


@app.task(
    bind=True,
    name="backend.app.workers.ingestion_tasks.ingest_document",
    max_retries=3,
    default_retry_delay=30,    # 30s first retry; Celery doubles each time with autoretry_for
    queue="ingestion",
    acks_late=True,
)
def ingest_document(
    self,
    document_id: str,
    file_path: str,
    filename: str,
    category: str,
    access_roles: list[str],
    tenant_id: str,
) -> dict:
    """
    Async document ingestion task.

    Args:
        document_id: UUID of the document record in DB
        file_path:   Absolute path to the uploaded file on disk
        filename:    Original filename (for logging and metadata)
        category:    HR document category (leave, benefits, onboarding, ...)
        access_roles: Roles allowed to see chunks from this document
        tenant_id:   Tenant UUID — written to every Qdrant chunk payload

    Returns:
        dict with chunk_count, latency_ms, status
    """
    logger.info("ingestion_task_started", doc_id=document_id, filename=filename, attempt=self.request.retries + 1)
    _update_status(document_id, "processing")

    t_start = time.time()

    try:
        pipeline = _get_services()
        result = pipeline.ingest(
            file_path=file_path,
            filename=filename,
            category=category,
            access_roles=access_roles,
            document_id=document_id,
        )

        chunk_count = result.get("chunk_count", 0)
        latency_ms = round((time.time() - t_start) * 1000)

        _update_status(document_id, "done", chunk_count=chunk_count)

        logger.info(
            "ingestion_task_completed",
            doc_id=document_id,
            filename=filename,
            chunk_count=chunk_count,
            latency_ms=latency_ms,
        )

        return {"status": "done", "chunk_count": chunk_count, "latency_ms": latency_ms}

    except Exception as exc:
        error_msg = str(exc)
        attempt = self.request.retries + 1
        max_retries = self.max_retries

        logger.error(
            "ingestion_task_failed",
            doc_id=document_id,
            filename=filename,
            error=error_msg,
            attempt=attempt,
            max_retries=max_retries,
        )

        if attempt <= max_retries:
            # Exponential backoff: 30s → 60s → 120s
            countdown = 30 * (2 ** self.request.retries)
            _update_status(document_id, "pending", error=f"Retrying ({attempt}/{max_retries}): {error_msg}")
            raise self.retry(exc=exc, countdown=countdown)
        else:
            _update_status(document_id, "failed", error=error_msg)
            return {"status": "failed", "error": error_msg}
