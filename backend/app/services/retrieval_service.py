"""Hybrid retrieval orchestrator — Sections 8.1-8.5.

Dense + BM25 → RRF fusion → cross-encoder reranking.

Fixes applied:
- Cross-encoder scores normalized to 0-1 via sigmoid (ms-marco outputs logits)
- Reranker logs model load time
- Retrieval orchestrator logs per-stage metrics
"""

from __future__ import annotations

import math
import re
import time

import numpy as np
import structlog
from rank_bm25 import BM25Okapi

from backend.app.models.document_models import ChunkMetadata, SearchResult

logger = structlog.get_logger()


# ── BM25 keyword retriever (Section 8.3) ────────────────────────────────────
def _tokenize(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text.lower())


class BM25Retriever:
    def __init__(self):
        self.index: Optional[BM25Okapi] = None
        self.chunks: list[ChunkMetadata] = []

    def build_index(self, chunks: list[ChunkMetadata]) -> None:
        self.chunks = list(chunks)
        if self.chunks:
            self.index = BM25Okapi([_tokenize(c.text) for c in self.chunks])
        else:
            self.index = None
        logger.info("bm25_index_built", chunk_count=len(self.chunks))

    def add_chunks(self, new: list[ChunkMetadata]) -> None:
        self.chunks.extend(new)
        self.index = BM25Okapi([_tokenize(c.text) for c in self.chunks])

    def retrieve(self, query: str, top_k: int = 20, role_filter: Optional[list[str]] = None) -> list[SearchResult]:
        if not self.index or not self.chunks:
            return []
        scores = self.index.get_scores(_tokenize(query))
        results: list[SearchResult] = []
        for idx, sc in sorted(enumerate(scores), key=lambda x: x[1], reverse=True):
            if sc <= 0:
                continue
            c = self.chunks[idx]
            if role_filter and not any(r in c.access_roles for r in role_filter):
                continue
            results.append(SearchResult(
                c.chunk_id, c.text, float(sc), c.source, c.page,
                {"document_id": c.document_id, "section_heading": c.section_heading, "category": c.category},
            ))
            if len(results) >= top_k:
                break
        return results

    @property
    def total_chunks(self) -> int:
        return len(self.chunks)


# ── Reciprocal Rank Fusion (Section 8.4) ─────────────────────────────────────
def reciprocal_rank_fusion(
    dense: list[SearchResult],
    bm25: list[SearchResult],
    k: int = 60,
    dw: float = 0.6,
    bw: float = 0.4,
) -> list[SearchResult]:
    scores: dict[str, float] = {}
    cmap: dict[str, SearchResult] = {}
    for rank, r in enumerate(dense, 1):
        scores[r.chunk_id] = scores.get(r.chunk_id, 0) + dw / (k + rank)
        cmap[r.chunk_id] = r
    for rank, r in enumerate(bm25, 1):
        scores[r.chunk_id] = scores.get(r.chunk_id, 0) + bw / (k + rank)
        cmap.setdefault(r.chunk_id, r)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [
        SearchResult(cid, cmap[cid].text, sc, cmap[cid].source, cmap[cid].page, cmap[cid].metadata)
        for cid, sc in ranked
    ]


# ── Cross-encoder reranker (Section 8.5) ─────────────────────────────────────
def _sigmoid(x: float) -> float:
    """Convert cross-encoder logit to 0-1 probability."""
    return 1.0 / (1.0 + math.exp(-x))


class Reranker:
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self._model = None

    def warmup(self) -> None:
        """Eagerly load the cross-encoder model at startup to avoid cold-start latency."""
        self._load()

    def _load(self):
        if self._model is None:
            try:
                t0 = time.time()
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(self.model_name)
                logger.info("reranker_loaded", model=self.model_name, load_ms=round((time.time() - t0) * 1000))
            except Exception as e:
                logger.warning("reranker_load_failed", error=str(e), fallback="score-based ordering")
        return self._model

    def rerank(self, query: str, candidates: list[SearchResult], top_n: int = 8) -> list[SearchResult]:
        if not candidates:
            return []
        model = self._load()
        if model is None:
            # Fallback: return top-N by existing RRF score
            return candidates[:top_n]

        pairs = [(query, c.text) for c in candidates]
        raw_scores = model.predict(pairs)

        # ms-marco outputs raw logits (often negative). Normalize to 0-1 via sigmoid.
        normalized = [_sigmoid(float(s)) for s in raw_scores]

        scored = sorted(zip(candidates, normalized), key=lambda x: x[1], reverse=True)
        results = [
            SearchResult(r.chunk_id, r.text, round(s, 4), r.source, r.page, r.metadata)
            for r, s in scored[:top_n]
        ]

        logger.info(
            "reranker_scores",
            top_score=results[0].score if results else 0,
            bottom_score=results[-1].score if results else 0,
            candidates_in=len(candidates),
            results_out=len(results),
        )
        return results


# ── Dense retriever (Section 8.2) ────────────────────────────────────────────
class DenseRetriever:
    def __init__(self, embedding_service, vector_store):
        self.emb = embedding_service
        self.vs = vector_store

    def retrieve(self, query: str, top_k: int = 20, role_filter: Optional[list[str]] = None) -> list[SearchResult]:
        qe = self.emb.embed(query)
        return self.vs.search(qe, top_k=top_k, role_filter=role_filter)


# ── Orchestrator (Section 3.5) ───────────────────────────────────────────────
class RetrievalOrchestrator:
    def __init__(
        self,
        dense: DenseRetriever,
        bm25: BM25Retriever,
        reranker: Reranker,
        dense_top_k: int = 20,
        bm25_top_k: int = 20,
        rerank_top_n: int = 8,
        dense_weight: float = 0.6,
        bm25_weight: float = 0.4,
    ):
        self.dense = dense
        self.bm25 = bm25
        self.reranker = reranker
        self.dense_top_k = dense_top_k
        self.bm25_top_k = bm25_top_k
        self.rerank_top_n = rerank_top_n
        self.dw = dense_weight
        self.bw = bm25_weight

    def retrieve(self, query: str, role_filter: Optional[list[str]] = None) -> tuple[list[SearchResult], dict]:
        t0 = time.time()

        # Stage 1: Dense
        t_dense = time.time()
        dr = self.dense.retrieve(query, self.dense_top_k, role_filter)
        dense_ms = (time.time() - t_dense) * 1000

        # Stage 2: BM25
        t_bm25 = time.time()
        br = self.bm25.retrieve(query, self.bm25_top_k, role_filter)
        bm25_ms = (time.time() - t_bm25) * 1000

        # Stage 3: RRF fusion
        fused = reciprocal_rank_fusion(dr, br, dw=self.dw, bw=self.bw)

        # Stage 4: Rerank
        t_rerank = time.time()
        reranked = self.reranker.rerank(query, fused, self.rerank_top_n)
        rerank_ms = (time.time() - t_rerank) * 1000

        total_ms = (time.time() - t0) * 1000
        meta = {
            "dense_count": len(dr),
            "bm25_count": len(br),
            "fused_count": len(fused),
            "reranked_count": len(reranked),
            "dense_ms": round(dense_ms),
            "bm25_ms": round(bm25_ms),
            "rerank_ms": round(rerank_ms),
            "retrieval_latency_ms": round(total_ms),
        }
        logger.info(
            "retrieval_complete", **meta,
            top_score=reranked[0].score if reranked else 0,
        )
        return reranked, meta
