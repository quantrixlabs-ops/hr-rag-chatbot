"""Prometheus application metrics — Phase 5 (F-56).

All custom metrics are defined here. Import and instrument from services.

Metrics exposed at GET /metrics (Prometheus scrape endpoint).
Default process/Python metrics are also included by prometheus_client.

Usage:
    from backend.app.core.metrics import (
        record_query, record_llm_inference, record_rag_retrieval,
        record_cache_hit, record_ingestion, ACTIVE_SESSIONS,
    )

    # In chat pipeline:
    with record_llm_inference(model="llama3:8b"):
        response = llm.generate(prompt)

    record_query(tenant_id, status="ok", latency_ms=342)
    record_cache_hit(tenant_id, hit=True, cache_type="semantic")
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Generator

from prometheus_client import Counter, Gauge, Histogram, Summary

# ── Query metrics ─────────────────────────────────────────────────────────────

QUERY_TOTAL = Counter(
    "hr_chatbot_query_total",
    "Total chat queries processed",
    labelnames=["tenant_id", "status"],  # status: ok | error | cached
)

QUERY_LATENCY = Histogram(
    "hr_chatbot_query_latency_seconds",
    "End-to-end chat query latency",
    labelnames=["tenant_id"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# ── LLM metrics ───────────────────────────────────────────────────────────────

LLM_INFERENCE_SECONDS = Histogram(
    "hr_chatbot_llm_inference_seconds",
    "LLM inference time per request",
    labelnames=["model", "tier"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

LLM_NODE_IN_FLIGHT = Gauge(
    "hr_chatbot_llm_node_in_flight",
    "In-flight LLM requests per Ollama node",
    labelnames=["node_url"],
)

LLM_ERRORS_TOTAL = Counter(
    "hr_chatbot_llm_errors_total",
    "LLM inference errors",
    labelnames=["model", "error_type"],
)

# ── RAG pipeline metrics ──────────────────────────────────────────────────────

RAG_RETRIEVAL_SECONDS = Histogram(
    "hr_chatbot_rag_retrieval_seconds",
    "RAG retrieval time (embed + Qdrant search + BM25 + rerank)",
    labelnames=["tenant_id"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

RAG_CHUNKS_RETRIEVED = Histogram(
    "hr_chatbot_rag_chunks_retrieved",
    "Number of chunks retrieved per query",
    buckets=[1, 3, 5, 8, 10, 15, 20, 30],
)

RAG_CONFIDENCE = Histogram(
    "hr_chatbot_rag_confidence",
    "Answer confidence score distribution",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

# ── Cache metrics ─────────────────────────────────────────────────────────────

CACHE_HITS_TOTAL = Counter(
    "hr_chatbot_cache_hits_total",
    "Semantic cache hits",
    labelnames=["tenant_id", "type"],  # type: exact | semantic
)

CACHE_MISSES_TOTAL = Counter(
    "hr_chatbot_cache_misses_total",
    "Semantic cache misses",
    labelnames=["tenant_id"],
)

# ── Session / user metrics ────────────────────────────────────────────────────

ACTIVE_SESSIONS = Gauge(
    "hr_chatbot_active_sessions",
    "Currently active chat sessions",
    labelnames=["tenant_id"],
)

AUTH_ATTEMPTS_TOTAL = Counter(
    "hr_chatbot_auth_attempts_total",
    "Authentication attempts",
    labelnames=["tenant_id", "status"],  # status: ok | failed | mfa_required
)

# ── Ingestion metrics ─────────────────────────────────────────────────────────

INGESTION_TOTAL = Counter(
    "hr_chatbot_ingestion_total",
    "Document ingestion outcomes",
    labelnames=["tenant_id", "status"],  # status: ok | failed | retry
)

INGESTION_DURATION_SECONDS = Histogram(
    "hr_chatbot_ingestion_duration_seconds",
    "Document ingestion pipeline duration",
    labelnames=["file_type"],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

INGESTION_CHUNKS_CREATED = Histogram(
    "hr_chatbot_ingestion_chunks_created",
    "Chunks created per document ingestion",
    buckets=[10, 25, 50, 100, 250, 500, 1000],
)

# ── HRMS metrics ──────────────────────────────────────────────────────────────

HRMS_CALLS_TOTAL = Counter(
    "hr_chatbot_hrms_calls_total",
    "Live HRMS API calls",
    labelnames=["tenant_id", "provider", "operation", "status"],
)

HRMS_CALL_SECONDS = Histogram(
    "hr_chatbot_hrms_call_seconds",
    "HRMS API call latency",
    labelnames=["provider", "operation"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

# ── Webhook metrics ───────────────────────────────────────────────────────────

WEBHOOK_DELIVERIES_TOTAL = Counter(
    "hr_chatbot_webhook_deliveries_total",
    "Webhook delivery outcomes",
    labelnames=["tenant_id", "event", "status"],
)

# ── Infrastructure metrics ────────────────────────────────────────────────────

DB_POOL_SIZE = Gauge(
    "hr_chatbot_db_pool_size",
    "Database connection pool current size",
    labelnames=["role"],  # role: primary | replica
)

ERRORS_TOTAL = Counter(
    "hr_chatbot_errors_total",
    "Unhandled application errors",
    labelnames=["endpoint", "error_type"],
)


# ── Instrumentation helpers ───────────────────────────────────────────────────

def record_query(
    tenant_id: str,
    status: str,
    latency_ms: float,
) -> None:
    """Record a completed chat query."""
    QUERY_TOTAL.labels(tenant_id=tenant_id, status=status).inc()
    QUERY_LATENCY.labels(tenant_id=tenant_id).observe(latency_ms / 1000.0)


def record_cache_hit(tenant_id: str, hit: bool, cache_type: str = "exact") -> None:
    """Record a cache hit or miss."""
    if hit:
        CACHE_HITS_TOTAL.labels(tenant_id=tenant_id, type=cache_type).inc()
    else:
        CACHE_MISSES_TOTAL.labels(tenant_id=tenant_id).inc()


def record_ingestion(
    tenant_id: str,
    status: str,
    file_type: str = "unknown",
    duration_s: float = 0,
    chunks: int = 0,
) -> None:
    """Record a document ingestion outcome."""
    INGESTION_TOTAL.labels(tenant_id=tenant_id, status=status).inc()
    if duration_s > 0:
        INGESTION_DURATION_SECONDS.labels(file_type=file_type).observe(duration_s)
    if chunks > 0:
        INGESTION_CHUNKS_CREATED.observe(chunks)


@contextmanager
def record_llm_inference(model: str, tier: str = "standard") -> Generator:
    """Context manager to time LLM inference."""
    start = time.perf_counter()
    try:
        yield
    except Exception:
        LLM_ERRORS_TOTAL.labels(model=model, error_type="inference_error").inc()
        raise
    finally:
        elapsed = time.perf_counter() - start
        LLM_INFERENCE_SECONDS.labels(model=model, tier=tier).observe(elapsed)


@contextmanager
def record_rag_retrieval(tenant_id: str) -> Generator:
    """Context manager to time RAG retrieval pipeline."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        RAG_RETRIEVAL_SECONDS.labels(tenant_id=tenant_id).observe(elapsed)
