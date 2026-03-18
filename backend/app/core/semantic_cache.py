"""Semantic query cache — caches RAG responses for similar queries (Phase 2).

Uses embedding similarity to detect repeated/similar queries and return
cached responses instead of running the full RAG pipeline.

Cache hit rate: typically 30-60% for enterprise HR chatbots
(employees frequently ask the same questions).

TTL: 1 hour (configurable). Evicts oldest entries when full.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Optional

import structlog

logger = structlog.get_logger()

# Cache config
MAX_CACHE_SIZE = 200
CACHE_TTL_SECONDS = 3600  # 1 hour
SIMILARITY_THRESHOLD = 0.92  # Cosine similarity for cache hit


@dataclass
class CacheEntry:
    query_hash: str
    query_text: str
    embedding: list  # Query embedding vector
    answer: str
    citations: list
    confidence: float
    suggested_questions: list
    created_at: float
    hits: int = 0


# In-memory cache (replace with Redis for multi-worker setups)
_cache: dict[str, CacheEntry] = {}
_cache_stats = {"hits": 0, "misses": 0, "evictions": 0}


def _cosine_similarity(a: list, b: list) -> float:
    """Compute cosine similarity between two vectors."""
    import math
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _query_hash(query: str) -> str:
    """Deterministic hash for exact match lookup."""
    return hashlib.sha256(query.lower().strip().encode()).hexdigest()[:16]


def get_cached(query: str, query_embedding: Optional[list] = None) -> Optional[dict]:
    """Look up cache for an exact or semantically similar query.

    Returns cached response dict or None.
    """
    now = time.time()
    qh = _query_hash(query)

    # 1. Exact match (fast path)
    if qh in _cache:
        entry = _cache[qh]
        if now - entry.created_at < CACHE_TTL_SECONDS:
            entry.hits += 1
            _cache_stats["hits"] += 1
            logger.info("cache_hit", type="exact", query=query[:50], hits=entry.hits)
            return _entry_to_dict(entry)
        else:
            del _cache[qh]  # Expired

    # 2. Semantic similarity search (slower, but catches paraphrases)
    if query_embedding:
        best_score = 0.0
        best_entry: Optional[CacheEntry] = None
        expired = []
        for key, entry in _cache.items():
            if now - entry.created_at >= CACHE_TTL_SECONDS:
                expired.append(key)
                continue
            if entry.embedding:
                sim = _cosine_similarity(query_embedding, entry.embedding)
                if sim > best_score:
                    best_score = sim
                    best_entry = entry
        # Clean expired
        for key in expired:
            del _cache[key]
        # Return if similarity exceeds threshold
        if best_entry and best_score >= SIMILARITY_THRESHOLD:
            best_entry.hits += 1
            _cache_stats["hits"] += 1
            logger.info("cache_hit", type="semantic", query=query[:50],
                        similarity=round(best_score, 3), hits=best_entry.hits)
            return _entry_to_dict(best_entry)

    _cache_stats["misses"] += 1
    return None


def put_cache(query: str, query_embedding: Optional[list], answer: str,
              citations: list, confidence: float, suggested_questions: list) -> None:
    """Store a query result in the cache."""
    qh = _query_hash(query)

    # Evict oldest if full
    if len(_cache) >= MAX_CACHE_SIZE:
        oldest_key = min(_cache, key=lambda k: _cache[k].created_at)
        del _cache[oldest_key]
        _cache_stats["evictions"] += 1

    _cache[qh] = CacheEntry(
        query_hash=qh,
        query_text=query,
        embedding=query_embedding or [],
        answer=answer,
        citations=citations,
        confidence=confidence,
        suggested_questions=suggested_questions,
        created_at=time.time(),
    )


def get_cache_stats() -> dict:
    """Return cache statistics for monitoring."""
    total = _cache_stats["hits"] + _cache_stats["misses"]
    hit_rate = _cache_stats["hits"] / max(total, 1)
    return {
        "size": len(_cache),
        "max_size": MAX_CACHE_SIZE,
        "hits": _cache_stats["hits"],
        "misses": _cache_stats["misses"],
        "hit_rate": round(hit_rate, 3),
        "evictions": _cache_stats["evictions"],
        "ttl_seconds": CACHE_TTL_SECONDS,
    }


def clear_cache() -> None:
    """Clear the entire cache (e.g., after document reindex)."""
    _cache.clear()
    logger.info("cache_cleared")


def _entry_to_dict(entry: CacheEntry) -> dict:
    return {
        "answer": entry.answer,
        "citations": entry.citations,
        "confidence": entry.confidence,
        "suggested_questions": entry.suggested_questions,
        "cached": True,
    }
