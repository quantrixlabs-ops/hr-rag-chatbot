"""Retrieval quality benchmarks — measures MRR, Recall@k, and faithfulness.

Run: python -m scripts.benchmark_retrieval

Requires: Ollama running with nomic-embed-text model pulled.
"""
import os
import sys
import time

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.core.config import get_settings
from backend.app.core.logging import configure_logging
from backend.app.database.session_store import init_database
from backend.app.services.embedding_service import EmbeddingService
from backend.app.services.retrieval_service import BM25Retriever, DenseRetriever, Reranker, RetrievalOrchestrator
from backend.app.vectorstore.faiss_store import FAISSIndex

# Benchmark queries with expected source documents
BENCHMARK_QUERIES = [
    {
        "query": "How many vacation days do employees get?",
        "expected_sources": ["Leave Policy"],
        "expected_answer_contains": ["15 days"],
    },
    {
        "query": "What health insurance plans are available?",
        "expected_sources": ["Benefits Guide"],
        "expected_answer_contains": ["Basic", "Standard", "Premium"],
    },
    {
        "query": "How does the 401k matching work?",
        "expected_sources": ["Benefits Guide"],
        "expected_answer_contains": ["6%", "match"],
    },
    {
        "query": "What is the remote work policy?",
        "expected_sources": ["Remote Work Policy"],
        "expected_answer_contains": ["hybrid", "remote"],
    },
    {
        "query": "When are performance reviews conducted?",
        "expected_sources": ["Performance Review"],
        "expected_answer_contains": ["Q4", "October"],
    },
    {
        "query": "What happens on the first day at work?",
        "expected_sources": ["Onboarding Guide"],
        "expected_answer_contains": ["Welcome", "HR"],
    },
    {
        "query": "How much parental leave do I get?",
        "expected_sources": ["Leave Policy"],
        "expected_answer_contains": ["16 weeks"],
    },
    {
        "query": "What is the dress code?",
        "expected_sources": ["Employee Handbook"],
        "expected_answer_contains": ["business casual"],
    },
    {
        "query": "How do I request time off?",
        "expected_sources": ["Leave Policy"],
        "expected_answer_contains": ["2 weeks", "manager"],
    },
    {
        "query": "What is the promotion criteria?",
        "expected_sources": ["Performance Review"],
        "expected_answer_contains": ["1 year", "rating"],
    },
]


def run_benchmark():
    configure_logging()
    s = get_settings()
    init_database(s.db_path)

    print("=" * 70)
    print("  HR RAG Chatbot — Retrieval Quality Benchmark")
    print("=" * 70)

    # Initialize services
    emb = EmbeddingService(s.embedding_model, s.embedding_provider, s.ollama_base_url, s.embedding_dimension)
    vs = FAISSIndex(s.embedding_dimension, s.faiss_index_dir)
    vs.load()

    if vs.total_chunks == 0:
        print("\nERROR: No chunks indexed. Run: python -m scripts.ingest_documents ./data/uploads")
        sys.exit(1)

    print(f"\nIndex: {vs.total_chunks} chunks loaded")

    bm25 = BM25Retriever()
    bm25.build_index(vs.metadata)
    dense = DenseRetriever(emb, vs)
    reranker = Reranker()
    orchestrator = RetrievalOrchestrator(
        dense, bm25, reranker,
        s.dense_top_k, s.bm25_top_k, s.rerank_top_n,
        s.dense_weight, s.bm25_weight,
    )

    # Run benchmarks
    results = []
    total_mrr = 0.0
    total_recall_3 = 0.0
    total_recall_5 = 0.0
    total_latency = 0.0

    print(f"\nRunning {len(BENCHMARK_QUERIES)} benchmark queries...\n")

    for i, bq in enumerate(BENCHMARK_QUERIES, 1):
        t0 = time.time()
        chunks, meta = orchestrator.retrieve(bq["query"])
        latency = (time.time() - t0) * 1000

        # Check if expected source is in top results
        retrieved_sources = [c.source for c in chunks]
        expected = bq["expected_sources"]

        # MRR: reciprocal rank of first relevant result
        rr = 0.0
        for rank, source in enumerate(retrieved_sources, 1):
            if any(exp.lower() in source.lower() for exp in expected):
                rr = 1.0 / rank
                break

        # Recall@k: is the expected source in top-k?
        def recall_at_k(k):
            top_k_sources = retrieved_sources[:k]
            return 1.0 if any(
                any(exp.lower() in s.lower() for exp in expected)
                for s in top_k_sources
            ) else 0.0

        r3 = recall_at_k(3)
        r5 = recall_at_k(5)

        total_mrr += rr
        total_recall_3 += r3
        total_recall_5 += r5
        total_latency += latency

        status = "PASS" if rr > 0 else "MISS"
        print(f"  [{status}] Q{i}: {bq['query'][:50]}...")
        print(f"       MRR={rr:.2f}  Recall@3={r3:.0f}  Recall@5={r5:.0f}  Latency={latency:.0f}ms")
        if rr == 0:
            print(f"       Expected: {expected}")
            print(f"       Got: {retrieved_sources[:3]}")

        results.append({
            "query": bq["query"],
            "mrr": rr, "recall_3": r3, "recall_5": r5,
            "latency_ms": latency, "status": status,
        })

    n = len(BENCHMARK_QUERIES)
    print(f"\n{'=' * 70}")
    print(f"  RESULTS SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Queries:        {n}")
    print(f"  MRR:            {total_mrr / n:.3f}  (target: > 0.85)")
    print(f"  Recall@3:       {total_recall_3 / n:.3f}  (target: > 0.80)")
    print(f"  Recall@5:       {total_recall_5 / n:.3f}  (target: > 0.90)")
    print(f"  Avg Latency:    {total_latency / n:.0f}ms  (target: < 500ms)")
    print(f"  Pass Rate:      {sum(1 for r in results if r['status'] == 'PASS')}/{n}")
    print(f"{'=' * 70}")

    # Quality gate
    mrr = total_mrr / n
    if mrr >= 0.85:
        print(f"\n  QUALITY GATE: PASSED (MRR {mrr:.3f} >= 0.85)")
    else:
        print(f"\n  QUALITY GATE: FAILED (MRR {mrr:.3f} < 0.85)")
        print(f"  Action: Review chunking strategy, embedding model, or document quality")


if __name__ == "__main__":
    run_benchmark()
