#!/usr/bin/env python3
"""Batch ingest HR documents — rebuilds the FAISS index from scratch.

Usage:
    python scripts/ingest_documents.py ./docs/

This script:
1. Deletes the existing FAISS index (clean rebuild)
2. Discovers all PDF/DOCX/MD/TXT files in the given directory
3. Ingests each document through the full pipeline
4. Validates that total chunks > 20 (fails otherwise)
5. Saves the FAISS index to disk
"""

from __future__ import annotations

import os
import sys
import shutil
import time
from pathlib import Path

# ── OpenMP fix must come before any C-extension import ──────────────────────
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.core.config import get_settings
from backend.app.core.logging import configure_logging
from backend.app.database.session_store import init_database
from backend.app.services.embedding_service import EmbeddingService
from backend.app.services.ingestion_service import IngestionPipeline
from backend.app.services.retrieval_service import BM25Retriever
from backend.app.vectorstore.faiss_store import FAISSIndex

CATEGORY_MAP = {
    "handbook": "handbook",
    "employee": "handbook",
    "policy": "policy",
    "benefit": "benefits",
    "leave": "leave",
    "onboard": "onboarding",
    "legal": "legal",
}

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".md", ".txt"}
MIN_TOTAL_CHUNKS = 20


def guess_category(filename: str) -> str:
    fl = filename.lower()
    for keyword, cat in CATEGORY_MAP.items():
        if keyword in fl:
            return cat
    return "policy"


def main(docs_dir: str) -> None:
    configure_logging()
    t_start = time.time()
    s = get_settings()

    # ── Step 1: Clean up stale state ─────────────────────────────────────
    print("=" * 60)
    print("HR RAG Chatbot — Document Ingestion")
    print("=" * 60)

    # Ensure data dirs exist
    os.makedirs(s.faiss_index_dir, exist_ok=True)
    os.makedirs(s.upload_dir, exist_ok=True)
    os.makedirs(os.path.dirname(s.db_path), exist_ok=True)

    # Delete existing FAISS index for clean rebuild
    for f in ["index.faiss", "metadata.pkl", "index.faiss.tmp", "metadata.pkl.tmp"]:
        fp = os.path.join(s.faiss_index_dir, f)
        if os.path.exists(fp):
            os.remove(fp)
            print(f"  Deleted stale: {fp}")

    init_database(s.db_path)

    # ── Step 2: Initialize services ──────────────────────────────────────
    print(f"\nEmbedding model: {s.embedding_model} via {s.embedding_provider}")
    print(f"Ollama URL: {s.ollama_base_url}")
    print(f"FAISS dimension: {s.embedding_dimension}")
    print()

    emb = EmbeddingService(s.embedding_model, s.embedding_provider, s.ollama_base_url, s.embedding_dimension)
    vs = FAISSIndex(s.embedding_dimension, s.faiss_index_dir)
    bm25 = BM25Retriever()
    pipeline = IngestionPipeline(emb, vs, bm25)

    # ── Step 3: Discover documents ───────────────────────────────────────
    docs_path = Path(docs_dir)
    if not docs_path.is_dir():
        print(f"ERROR: {docs_dir} is not a directory")
        sys.exit(1)

    files = sorted(f for f in docs_path.iterdir() if f.suffix.lower() in SUPPORTED_EXTENSIONS)
    if not files:
        print(f"ERROR: No supported files found in {docs_dir}")
        print(f"  Supported: {', '.join(SUPPORTED_EXTENSIONS)}")
        sys.exit(1)

    print(f"Found {len(files)} documents to ingest:")
    for f in files:
        size_kb = f.stat().st_size / 1024
        print(f"  {f.name} ({size_kb:.0f} KB)")
    print()

    # ── Step 4: Ingest each document ─────────────────────────────────────
    results = []
    total_chunks = 0

    for i, fp in enumerate(files, 1):
        title = fp.stem.replace("_", " ").replace("-", " ").title()
        category = guess_category(fp.name)

        print(f"[{i}/{len(files)}] Ingesting: {fp.name}")
        print(f"         Title: {title}")
        print(f"         Category: {category}")

        with open(fp, "rb") as f:
            content = f.read()

        t0 = time.time()
        result = pipeline.ingest(
            file_content=content,
            filename=fp.name,
            title=title,
            category=category,
            access_roles=["employee", "manager", "hr_admin"],
        )
        elapsed = time.time() - t0

        status = "OK" if result.status == "indexed" else "FAIL"
        print(f"         Result: {status} — {result.chunk_count} chunks in {elapsed:.1f}s")
        print(f"         FAISS total: {vs.total_chunks} vectors")
        print()

        results.append(result)
        total_chunks += result.chunk_count

    # ── Step 5: Save and validate ────────────────────────────────────────
    vs.save()

    print("=" * 60)
    print("INGESTION SUMMARY")
    print("=" * 60)
    print(f"Documents processed: {len(files)}")
    print(f"Successfully indexed: {sum(1 for r in results if r.status == 'indexed')}")
    print(f"Failed: {sum(1 for r in results if r.status != 'indexed')}")
    print(f"Total chunks: {total_chunks}")
    print(f"FAISS vectors: {vs.total_chunks}")
    print(f"BM25 index: {bm25.total_chunks} chunks")
    print(f"Total time: {time.time() - t_start:.1f}s")
    print()

    for r in results:
        marker = "OK" if r.status == "indexed" else "FAIL"
        print(f"  [{marker}] {r.document_id[:8]}... — {r.chunk_count} chunks ({r.processing_time_ms:.0f}ms)")

    # ── Validation ───────────────────────────────────────────────────────
    if total_chunks < MIN_TOTAL_CHUNKS:
        print(f"\nERROR: Only {total_chunks} total chunks indexed (minimum: {MIN_TOTAL_CHUNKS})")
        print("This usually means PDF text extraction failed. Check logs above.")
        sys.exit(1)

    print(f"\nSUCCESS: {total_chunks} chunks indexed across {len(files)} documents")
    print(f"Index saved to: {s.faiss_index_dir}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/ingest_documents.py <docs_directory>")
        print()
        print("Example:")
        print("  python scripts/ingest_documents.py ./docs/")
        sys.exit(1)
    main(sys.argv[1])
