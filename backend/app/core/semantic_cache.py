"""Semantic query cache — Phase 4 upgrade: Redis-backed, multi-instance safe (F-39).

Phase 2 used an in-memory dict — died on restart, not shared across API instances.
Phase 4: Redis-backed. Safe for horizontal scaling (multiple API pods all share cache).

Cache strategy:
  1. Exact hash match in Redis (O(1)) → cache hit
  2. Embedding similarity check against recent query keys (cosine ≥ 0.92) → cache hit
  3. Miss → run full RAG pipeline → store result in Redis with TTL

Key schema:
  sc:hash:{hash16}         → JSON blob (answer, citations, confidence, suggested_questions)
  sc:emb:{hash16}          → JSON array (embedding vector)
  sc:keys:{tenant_id}      → Redis SET of all hash keys for this tenant (for similarity scan)

All keys scoped per tenant_id to avoid cross-tenant cache pollution.

Fallback: if Redis is unavailable, falls back to in-memory dict (dev/CI mode).
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Optional

import structlog

logger = structlog.get_logger()

# Cache config
CACHE_TTL_SECONDS = 3600         # 1 hour
SIMILARITY_THRESHOLD = 0.92      # Cosine similarity for semantic hit
MAX_SIMILARITY_CANDIDATES = 100  # Max embeddings to scan for similarity (perf guard)

# Fallback in-memory cache (used when Redis unavailable)
_memory_cache: dict[str, dict] = {}
_memory_embeddings: dict[str, list] = {}
_memory_stats = {"hits": 0, "misses": 0}

# ── Redis client (lazy init) ──────────────────────────────────────────────────

_redis_client = None


def _get_redis():
    """Return Redis client, or None if unavailable."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis as redis_lib
        import os
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        client = redis_lib.from_url(redis_url, decode_responses=True, socket_timeout=1.0)
        client.ping()
        _redis_client = client
        logger.info("semantic_cache_redis_connected", url=redis_url)
        return _redis_client
    except Exception as e:
        logger.warning("semantic_cache_redis_unavailable", error=str(e),
                       fallback="in-memory")
        return None


def reset_redis_client() -> None:
    """Force reconnect on next use — call after Redis config change."""
    global _redis_client
    _redis_client = None


# ── Internal helpers ──────────────────────────────────────────────────────────

def _query_hash(query: str) -> str:
    """Deterministic 16-char hash for exact match lookup."""
    return hashlib.sha256(query.lower().strip().encode()).hexdigest()[:16]


def _cosine_similarity(a: list, b: list) -> float:
    """Compute cosine similarity between two float vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _redis_key_entry(tenant_id: str, qhash: str) -> str:
    return f"sc:hash:{tenant_id}:{qhash}"


def _redis_key_emb(tenant_id: str, qhash: str) -> str:
    return f"sc:emb:{tenant_id}:{qhash}"


def _redis_key_set(tenant_id: str) -> str:
    return f"sc:keys:{tenant_id}"


# ── Public API ────────────────────────────────────────────────────────────────

def get_cached(
    query: str,
    query_embedding: Optional[list] = None,
    tenant_id: str = "default",
) -> Optional[dict]:
    """Look up cache for an exact or semantically similar query.

    Returns cached response dict (with cached=True) or None.
    Tenant-scoped: queries from different tenants never collide.
    """
    r = _get_redis()
    qhash = _query_hash(query)

    if r:
        return _get_cached_redis(r, qhash, query_embedding, tenant_id)
    else:
        return _get_cached_memory(qhash, query_embedding)


def put_cache(
    query: str,
    query_embedding: Optional[list],
    answer: str,
    citations: list,
    confidence: float,
    suggested_questions: list,
    tenant_id: str = "default",
) -> None:
    """Store a query result in the cache."""
    r = _get_redis()
    qhash = _query_hash(query)

    entry = {
        "answer": answer,
        "citations": citations,
        "confidence": confidence,
        "suggested_questions": suggested_questions,
        "cached_at": time.time(),
    }

    if r:
        _put_cache_redis(r, qhash, entry, query_embedding, tenant_id)
    else:
        _put_cache_memory(qhash, entry, query_embedding)


def get_cache_stats(tenant_id: str = "default") -> dict:
    """Return cache statistics for monitoring."""
    r = _get_redis()
    if r:
        try:
            key_count = r.scard(_redis_key_set(tenant_id))
            info = r.info("stats")
            return {
                "backend": "redis",
                "tenant_id": tenant_id,
                "size": key_count,
                "ttl_seconds": CACHE_TTL_SECONDS,
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
            }
        except Exception:
            pass
    total = _memory_stats["hits"] + _memory_stats["misses"]
    return {
        "backend": "memory",
        "size": len(_memory_cache),
        "hits": _memory_stats["hits"],
        "misses": _memory_stats["misses"],
        "hit_rate": round(_memory_stats["hits"] / max(total, 1), 3),
        "ttl_seconds": CACHE_TTL_SECONDS,
    }


def clear_cache(tenant_id: str = "default") -> None:
    """Clear all cache entries for this tenant."""
    r = _get_redis()
    if r:
        try:
            # Get all keys for this tenant and delete them
            keys_set = _redis_key_set(tenant_id)
            members = r.smembers(keys_set)
            pipe = r.pipeline()
            for qhash in members:
                pipe.delete(_redis_key_entry(tenant_id, qhash))
                pipe.delete(_redis_key_emb(tenant_id, qhash))
            pipe.delete(keys_set)
            pipe.execute()
            logger.info("semantic_cache_cleared", backend="redis", tenant_id=tenant_id)
            return
        except Exception as e:
            logger.warning("cache_clear_redis_failed", error=str(e))
    _memory_cache.clear()
    _memory_embeddings.clear()
    logger.info("semantic_cache_cleared", backend="memory")


def warm_cache(top_queries: list[dict], tenant_id: str = "default") -> int:
    """Pre-populate cache with pre-computed answers for top queries.

    Used by Celery Beat cache warming job (daily at 6am).
    top_queries: list of {"query", "embedding", "answer", "citations",
                           "confidence", "suggested_questions"}
    Returns number of entries written.
    """
    count = 0
    for item in top_queries:
        put_cache(
            query=item["query"],
            query_embedding=item.get("embedding"),
            answer=item["answer"],
            citations=item.get("citations", []),
            confidence=item.get("confidence", 1.0),
            suggested_questions=item.get("suggested_questions", []),
            tenant_id=tenant_id,
        )
        count += 1
    logger.info("cache_warmed", entries=count, tenant_id=tenant_id)
    return count


# ── Redis backend ─────────────────────────────────────────────────────────────

def _get_cached_redis(r, qhash: str, query_embedding: Optional[list], tenant_id: str) -> Optional[dict]:
    # 1. Exact hash match (O(1))
    entry_key = _redis_key_entry(tenant_id, qhash)
    raw = r.get(entry_key)
    if raw:
        _memory_stats["hits"] += 1
        entry = json.loads(raw)
        entry["cached"] = True
        logger.info("cache_hit", type="exact", backend="redis", tenant_id=tenant_id)
        return entry

    # 2. Semantic similarity scan
    if query_embedding:
        keys_set = _redis_key_set(tenant_id)
        all_hashes = list(r.smembers(keys_set))[:MAX_SIMILARITY_CANDIDATES]

        best_score = 0.0
        best_entry: Optional[dict] = None

        pipe = r.pipeline()
        for h in all_hashes:
            pipe.get(_redis_key_emb(tenant_id, h))
        emb_raws = pipe.execute()

        for h, emb_raw in zip(all_hashes, emb_raws):
            if not emb_raw:
                continue
            try:
                stored_emb = json.loads(emb_raw)
                sim = _cosine_similarity(query_embedding, stored_emb)
                if sim > best_score:
                    best_score = sim
                    best_hash = h
                    if sim >= SIMILARITY_THRESHOLD:
                        # Early exit — good enough match found
                        break
            except (json.JSONDecodeError, TypeError):
                continue

        if best_score >= SIMILARITY_THRESHOLD:
            raw_best = r.get(_redis_key_entry(tenant_id, best_hash))
            if raw_best:
                # Refresh TTL on hit
                r.expire(entry_key, CACHE_TTL_SECONDS)
                entry = json.loads(raw_best)
                entry["cached"] = True
                _memory_stats["hits"] += 1
                logger.info(
                    "cache_hit", type="semantic", backend="redis",
                    similarity=round(best_score, 3), tenant_id=tenant_id,
                )
                return entry

    _memory_stats["misses"] += 1
    return None


def _put_cache_redis(r, qhash: str, entry: dict, query_embedding: Optional[list], tenant_id: str) -> None:
    try:
        pipe = r.pipeline()
        # Store entry
        pipe.set(
            _redis_key_entry(tenant_id, qhash),
            json.dumps(entry),
            ex=CACHE_TTL_SECONDS,
        )
        # Store embedding for semantic search
        if query_embedding:
            pipe.set(
                _redis_key_emb(tenant_id, qhash),
                json.dumps(query_embedding),
                ex=CACHE_TTL_SECONDS,
            )
        # Register hash in tenant key set (for similarity scan)
        pipe.sadd(_redis_key_set(tenant_id), qhash)
        pipe.expire(_redis_key_set(tenant_id), CACHE_TTL_SECONDS * 2)
        pipe.execute()
    except Exception as e:
        logger.warning("cache_put_redis_failed", error=str(e))
        # Fallback to memory
        _put_cache_memory(qhash, entry, query_embedding)


# ── Memory fallback backend ───────────────────────────────────────────────────

def _get_cached_memory(qhash: str, query_embedding: Optional[list]) -> Optional[dict]:
    now = time.time()

    # Exact match
    if qhash in _memory_cache:
        entry = _memory_cache[qhash]
        if now - entry.get("cached_at", 0) < CACHE_TTL_SECONDS:
            _memory_stats["hits"] += 1
            result = dict(entry)
            result["cached"] = True
            return result
        del _memory_cache[qhash]

    # Semantic similarity
    if query_embedding:
        best_score = 0.0
        best_hash: Optional[str] = None
        expired = []
        for h, entry in _memory_cache.items():
            if now - entry.get("cached_at", 0) >= CACHE_TTL_SECONDS:
                expired.append(h)
                continue
            stored_emb = _memory_embeddings.get(h)
            if stored_emb:
                sim = _cosine_similarity(query_embedding, stored_emb)
                if sim > best_score:
                    best_score = sim
                    best_hash = h
        for h in expired:
            _memory_cache.pop(h, None)
            _memory_embeddings.pop(h, None)

        if best_hash and best_score >= SIMILARITY_THRESHOLD:
            _memory_stats["hits"] += 1
            result = dict(_memory_cache[best_hash])
            result["cached"] = True
            logger.info("cache_hit", type="semantic", backend="memory",
                        similarity=round(best_score, 3))
            return result

    _memory_stats["misses"] += 1
    return None


def _put_cache_memory(qhash: str, entry: dict, query_embedding: Optional[list]) -> None:
    # Evict oldest if over 500 entries
    if len(_memory_cache) >= 500:
        oldest = min(_memory_cache, key=lambda k: _memory_cache[k].get("cached_at", 0))
        _memory_cache.pop(oldest, None)
        _memory_embeddings.pop(oldest, None)

    _memory_cache[qhash] = entry
    if query_embedding:
        _memory_embeddings[qhash] = query_embedding


# ── Cache invalidation on document changes ───────────────────────────────────

# Track which source documents contributed to cached answers
_source_to_cache_keys: dict[str, set[str]] = {}


def invalidate_on_document_change(
    document_source: str,
    tenant_id: str = "default",
) -> int:
    """Invalidate all cache entries that cite the changed document.

    Called after:
      - Document upload (new content may change answers)
      - Document delete (cited document no longer exists)
      - Document reindex (content may have changed)

    Returns number of cache entries invalidated.
    """
    r = _get_redis()
    invalidated = 0

    if r:
        try:
            # Scan all cached entries for this tenant and check citations
            keys_set = _redis_key_set(tenant_id)
            all_hashes = list(r.smembers(keys_set))

            pipe = r.pipeline()
            for h in all_hashes:
                pipe.get(_redis_key_entry(tenant_id, h))
            entries = pipe.execute()

            to_delete = []
            for h, raw in zip(all_hashes, entries):
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                    citations = entry.get("citations", [])
                    # Check if any citation references the changed document
                    for cit in citations:
                        src = cit.get("source", "") if isinstance(cit, dict) else ""
                        if document_source.lower() in src.lower():
                            to_delete.append(h)
                            break
                except (json.JSONDecodeError, TypeError):
                    continue

            if to_delete:
                del_pipe = r.pipeline()
                for h in to_delete:
                    del_pipe.delete(_redis_key_entry(tenant_id, h))
                    del_pipe.delete(_redis_key_emb(tenant_id, h))
                    del_pipe.srem(keys_set, h)
                del_pipe.execute()
                invalidated = len(to_delete)
        except Exception as e:
            logger.warning("cache_invalidation_redis_failed", error=str(e))
    else:
        # Memory fallback: scan and remove matching entries
        to_remove = []
        for qhash, entry in _memory_cache.items():
            citations = entry.get("citations", [])
            for cit in citations:
                src = cit.get("source", "") if isinstance(cit, dict) else ""
                if document_source.lower() in src.lower():
                    to_remove.append(qhash)
                    break
        for qhash in to_remove:
            _memory_cache.pop(qhash, None)
            _memory_embeddings.pop(qhash, None)
        invalidated = len(to_remove)

    if invalidated > 0:
        logger.info(
            "cache_invalidated_on_doc_change",
            document_source=document_source,
            entries_invalidated=invalidated,
            tenant_id=tenant_id,
        )
    return invalidated


def get_detailed_stats(tenant_id: str = "default") -> dict:
    """Extended cache statistics with per-type breakdowns."""
    base = get_cache_stats(tenant_id)

    # Add memory usage estimate
    cache_size = len(_memory_cache)
    approx_memory_bytes = sum(
        len(json.dumps(v)) for v in _memory_cache.values()
    ) if _memory_cache else 0
    emb_memory_bytes = sum(
        len(json.dumps(v)) for v in _memory_embeddings.values()
    ) if _memory_embeddings else 0

    base["detailed"] = {
        "memory_cache_entries": cache_size,
        "memory_embedding_entries": len(_memory_embeddings),
        "approx_cache_bytes": approx_memory_bytes,
        "approx_embedding_bytes": emb_memory_bytes,
        "similarity_threshold": SIMILARITY_THRESHOLD,
        "max_similarity_candidates": MAX_SIMILARITY_CANDIDATES,
    }
    return base
