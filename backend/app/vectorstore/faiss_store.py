"""FAISS vector index with RBAC-aware filtering — Section 7.2.

Hardened with:
- Automatic directory creation
- Safe load (corrupt-file handling)
- Atomic save (write-then-rename)
- Dimension validation on add()
"""

from __future__ import annotations

import os
import pickle
import tempfile
import shutil

import faiss
import numpy as np
import structlog

from backend.app.models.document_models import ChunkMetadata, SearchResult

logger = structlog.get_logger()


class FAISSIndex:
    def __init__(self, dimension: int = 768, index_dir: str = "./data/faiss_index"):
        self.dimension = dimension
        self.index_dir = index_dir
        self.index = faiss.IndexFlatIP(dimension)
        self.metadata: list[ChunkMetadata] = []
        # Ensure the directory exists immediately
        os.makedirs(self.index_dir, exist_ok=True)

    # ── Write ────────────────────────────────────────────────────────────
    def add(self, embeddings: np.ndarray, metadata: list[ChunkMetadata]) -> None:
        if embeddings.ndim == 1:
            embeddings = embeddings.reshape(1, -1)
        if embeddings.shape[1] != self.dimension:
            raise ValueError(
                f"Embedding dimension mismatch: got {embeddings.shape[1]}, "
                f"expected {self.dimension}"
            )
        if embeddings.shape[0] != len(metadata):
            raise ValueError(
                f"Count mismatch: {embeddings.shape[0]} embeddings vs "
                f"{len(metadata)} metadata entries"
            )

        embeddings = embeddings.astype(np.float32).copy()
        faiss.normalize_L2(embeddings)
        self.index.add(embeddings)
        self.metadata.extend(metadata)
        logger.info("faiss_add", new_vectors=len(metadata), total=self.index.ntotal)

    # ── Read ─────────────────────────────────────────────────────────────
    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 20,
        role_filter: list[str] | None = None,
    ) -> list[SearchResult]:
        if self.index.ntotal == 0:
            return []

        try:
            qe = query_embedding.astype(np.float32).copy()
            if qe.ndim == 1:
                qe = qe.reshape(1, -1)
            if qe.shape[1] != self.dimension:
                logger.error("search_dim_mismatch", got=qe.shape[1], expected=self.dimension)
                return []

            faiss.normalize_L2(qe)
            fetch_k = min(top_k * 3, self.index.ntotal)
            scores, indices = self.index.search(qe, fetch_k)

            results: list[SearchResult] = []
            for score, idx in zip(scores[0], indices[0]):
                if idx == -1:
                    continue
                if idx >= len(self.metadata):
                    logger.warning("faiss_index_metadata_drift", idx=int(idx), metadata_len=len(self.metadata))
                    continue
                meta = self.metadata[idx]
                if role_filter and not any(r in meta.access_roles for r in role_filter):
                    continue
                results.append(SearchResult(
                    chunk_id=meta.chunk_id,
                    text=meta.text,
                    score=float(score),
                    source=meta.source,
                    page=meta.page,
                    metadata={
                        "document_id": meta.document_id,
                        "section_heading": meta.section_heading,
                        "category": meta.category,
                        "chunk_index": meta.chunk_index,
                    },
                ))
                if len(results) >= top_k:
                    break
            return results

        except Exception as e:
            logger.error("faiss_search_failed", error=str(e),
                         index_size=self.index.ntotal, metadata_len=len(self.metadata))
            # If the index is corrupted, reset it
            if "index" in str(e).lower() or "dimension" in str(e).lower():
                logger.warning("faiss_index_corruption_detected", action="resetting index")
                self.index = faiss.IndexFlatIP(self.dimension)
                self.metadata = []
            return []

    # ── Persistence ──────────────────────────────────────────────────────
    def save(self) -> None:
        """Save index to disk. Uses write-to-temp + rename for atomicity."""
        os.makedirs(self.index_dir, exist_ok=True)

        idx_path = os.path.join(self.index_dir, "index.faiss")
        meta_path = os.path.join(self.index_dir, "metadata.pkl")

        try:
            # Write to temp files first, then move — prevents corruption
            # on crash mid-write
            tmp_idx = idx_path + ".tmp"
            tmp_meta = meta_path + ".tmp"

            faiss.write_index(self.index, tmp_idx)
            with open(tmp_meta, "wb") as f:
                pickle.dump(self.metadata, f)

            # Atomic rename
            shutil.move(tmp_idx, idx_path)
            shutil.move(tmp_meta, meta_path)

            logger.info("faiss_saved", index_dir=self.index_dir, total=self.index.ntotal)
        except Exception as e:
            logger.error("faiss_save_failed", error=str(e))
            # Clean up temp files
            for tmp in [idx_path + ".tmp", meta_path + ".tmp"]:
                if os.path.exists(tmp):
                    os.remove(tmp)
            raise

    def load(self) -> bool:
        """Load index from disk. Returns False if files don't exist.
        Logs a warning and starts fresh if files are corrupt."""
        idx_path = os.path.join(self.index_dir, "index.faiss")
        meta_path = os.path.join(self.index_dir, "metadata.pkl")

        if not os.path.exists(idx_path) or not os.path.exists(meta_path):
            logger.info("faiss_no_index_on_disk", index_dir=self.index_dir, hint="Will start with empty index")
            return False

        try:
            loaded_index = faiss.read_index(idx_path)
            with open(meta_path, "rb") as f:
                loaded_meta = pickle.load(f)

            # Validate consistency
            if loaded_index.ntotal != len(loaded_meta):
                logger.warning(
                    "faiss_metadata_mismatch",
                    index_vectors=loaded_index.ntotal,
                    metadata_count=len(loaded_meta),
                    action="starting fresh",
                )
                return False

            self.index = loaded_index
            self.metadata = loaded_meta
            logger.info("faiss_loaded", total=self.index.ntotal)
            return True

        except Exception as e:
            logger.error(
                "faiss_load_failed",
                error=str(e),
                action="starting with empty index",
            )
            # Reset to empty — don't crash
            self.index = faiss.IndexFlatIP(self.dimension)
            self.metadata = []
            return False

    @property
    def total_chunks(self) -> int:
        return self.index.ntotal
