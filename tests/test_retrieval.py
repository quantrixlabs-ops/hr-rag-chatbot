"""Tests for retrieval — FAISS, BM25, RRF, reranking."""

import numpy as np
import pytest

from backend.app.vectorstore.faiss_store import FAISSIndex
from backend.app.services.retrieval_service import BM25Retriever, reciprocal_rank_fusion
from backend.app.models.document_models import SearchResult


def test_faiss_add_search(sample_chunks):
    idx = FAISSIndex(dimension=8)
    embs = np.random.randn(len(sample_chunks), 8).astype(np.float32)
    idx.add(embs, sample_chunks)
    assert idx.total_chunks == len(sample_chunks)
    results = idx.search(np.random.randn(8).astype(np.float32), top_k=3)
    assert len(results) <= 3


def test_faiss_rbac(sample_chunks):
    sample_chunks[0].access_roles = ["hr_admin"]
    idx = FAISSIndex(dimension=8)
    idx.add(np.random.randn(len(sample_chunks), 8).astype(np.float32), sample_chunks)
    results = idx.search(np.random.randn(8).astype(np.float32), top_k=10, role_filter=["employee"])
    assert all(r.chunk_id != sample_chunks[0].chunk_id for r in results)


def test_faiss_persistence(sample_chunks, tmp_path):
    d = str(tmp_path / "faiss_test")
    idx = FAISSIndex(8, d)
    idx.add(np.random.randn(len(sample_chunks), 8).astype(np.float32), sample_chunks)
    idx.save()
    idx2 = FAISSIndex(8, d)
    assert idx2.load()
    assert idx2.total_chunks == len(sample_chunks)


def test_bm25_retrieval(sample_chunks):
    r = BM25Retriever()
    r.build_index(sample_chunks)
    results = r.retrieve("vacation days paid leave", top_k=3)
    assert len(results) > 0
    assert any("vacation" in x.text.lower() for x in results)


def test_bm25_rbac(sample_chunks):
    sample_chunks[0].access_roles = ["hr_admin"]
    r = BM25Retriever()
    r.build_index(sample_chunks)
    results = r.retrieve("vacation", top_k=10, role_filter=["employee"])
    assert all(x.chunk_id != sample_chunks[0].chunk_id for x in results)


def test_rrf():
    dense = [SearchResult("a","ta",0.9,"d",1), SearchResult("b","tb",0.8,"d",2), SearchResult("c","tc",0.7,"d",3)]
    bm25 = [SearchResult("b","tb",5.0,"d",2), SearchResult("d","td",4.0,"d",4), SearchResult("a","ta",3.0,"d",1)]
    fused = reciprocal_rank_fusion(dense, bm25)
    assert len(fused) == 4
    assert "b" in [r.chunk_id for r in fused[:2]]


def test_rrf_empty():
    assert reciprocal_rank_fusion([], []) == []
