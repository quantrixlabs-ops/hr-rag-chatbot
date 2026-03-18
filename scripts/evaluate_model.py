"""Model evaluation pipeline — automated quality regression tests.

Run: python -m scripts.evaluate_model

Tests the full RAG pipeline (retrieval + LLM + verification) against
a set of questions with expected answers. Returns pass/fail for CI.
"""
import os
import sys
import time

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

EVAL_CASES = [
    {
        "query": "How many vacation days do new employees get?",
        "must_contain": ["15"],
        "must_cite": True,
        "min_confidence": 0.4,
    },
    {
        "query": "What health insurance plans does the company offer?",
        "must_contain": ["Basic", "Standard", "Premium"],
        "must_cite": True,
        "min_confidence": 0.4,
    },
    {
        "query": "How does the 401k matching work?",
        "must_contain": ["6%"],
        "must_cite": True,
        "min_confidence": 0.3,
    },
    {
        "query": "What is the parental leave policy?",
        "must_contain": ["16 weeks"],
        "must_cite": True,
        "min_confidence": 0.3,
    },
    {
        "query": "When are performance reviews conducted?",
        "must_contain": ["Q4"],
        "must_cite": True,
        "min_confidence": 0.3,
    },
    {
        "query": "Fix my VPN connection",
        "expect_redirect": True,
        "redirect_contains": "IT",
    },
    {
        "query": "Tell me about leave",
        "expect_clarification": True,
    },
]


def run_evaluation():
    from backend.app.core.config import get_settings
    from backend.app.core.logging import configure_logging
    from backend.app.database.session_store import init_database

    configure_logging()
    s = get_settings()
    init_database(s.db_path)

    # Wire up the full pipeline
    from backend.app.services.embedding_service import EmbeddingService
    from backend.app.vectorstore.faiss_store import FAISSIndex
    from backend.app.services.retrieval_service import BM25Retriever, DenseRetriever, Reranker, RetrievalOrchestrator
    from backend.app.rag.orchestrator import ModelGateway
    from backend.app.rag.context_builder import ContextBuilder
    from backend.app.services.verification_service import AnswerVerifier
    from backend.app.rag.pipeline import RAGPipeline

    emb = EmbeddingService(s.embedding_model, s.embedding_provider, s.ollama_base_url, s.embedding_dimension)
    vs = FAISSIndex(s.embedding_dimension, s.faiss_index_dir)
    vs.load()
    if vs.total_chunks == 0:
        print("ERROR: No chunks indexed. Run ingestion first.")
        sys.exit(1)

    bm25 = BM25Retriever()
    bm25.build_index(vs.metadata)
    dense = DenseRetriever(emb, vs)
    reranker = Reranker()
    retrieval = RetrievalOrchestrator(dense, bm25, reranker, s.dense_top_k, s.bm25_top_k, s.rerank_top_n, s.dense_weight, s.bm25_weight)
    llm = ModelGateway(s.llm_provider)
    llm.configure(s.llm_provider, s.vllm_base_url if s.llm_provider == "vllm" else s.ollama_base_url)
    ctx = ContextBuilder(s.max_context_tokens)
    verifier = AnswerVerifier()
    rag = RAGPipeline(retrieval, ctx, llm, verifier, s)

    print("=" * 70)
    print("  HR RAG Chatbot — Model Evaluation Pipeline")
    print("=" * 70)
    print(f"  Chunks: {vs.total_chunks}  |  Model: {s.llm_model}  |  Cases: {len(EVAL_CASES)}")
    print("=" * 70 + "\n")

    passed = 0
    failed = 0
    total_latency = 0

    for i, case in enumerate(EVAL_CASES, 1):
        t0 = time.time()
        result = rag.query(case["query"], "employee")
        latency = (time.time() - t0) * 1000
        total_latency += latency

        answer = result.answer.lower()
        errors = []

        # Check redirect
        if case.get("expect_redirect"):
            if "redirect_contains" in case:
                if case["redirect_contains"].lower() not in answer:
                    errors.append(f"Expected redirect containing '{case['redirect_contains']}'")
        # Check clarification
        elif case.get("expect_clarification"):
            if result.query_type != "clarification":
                errors.append(f"Expected clarification, got query_type={result.query_type}")
        else:
            # Check must_contain
            for term in case.get("must_contain", []):
                if term.lower() not in answer:
                    errors.append(f"Missing: '{term}'")
            # Check citations
            if case.get("must_cite") and not result.citations:
                errors.append("No citations provided")
            # Check confidence
            min_conf = case.get("min_confidence", 0.0)
            if result.confidence < min_conf:
                errors.append(f"Confidence {result.confidence:.2f} < {min_conf}")

        status = "PASS" if not errors else "FAIL"
        if errors:
            failed += 1
        else:
            passed += 1

        print(f"  [{status}] Q{i}: {case['query'][:55]}...")
        print(f"       Type: {result.query_type}  Confidence: {result.confidence:.2f}  Latency: {latency:.0f}ms")
        if errors:
            for e in errors:
                print(f"       ERROR: {e}")
        print()

    print("=" * 70)
    print(f"  RESULTS: {passed} passed, {failed} failed out of {len(EVAL_CASES)}")
    print(f"  Avg Latency: {total_latency / len(EVAL_CASES):.0f}ms")
    print(f"  Pass Rate: {passed / len(EVAL_CASES) * 100:.0f}%")
    print("=" * 70)

    if failed > 0:
        print(f"\n  QUALITY GATE: FAILED ({failed} failures)")
        sys.exit(1)
    else:
        print(f"\n  QUALITY GATE: PASSED (all {passed} cases)")


if __name__ == "__main__":
    run_evaluation()
