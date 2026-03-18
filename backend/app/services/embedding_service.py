"""Embedding service — Section 3.2.

Supports Ollama and sentence-transformers with:
- Lazy model loading (loads once, reuses)
- Connection-error retries for Ollama
- Meaningful error messages
"""

from __future__ import annotations

import time

import numpy as np
import httpx
import structlog

logger = structlog.get_logger()

_MAX_RETRIES = 3
_RETRY_DELAY = 1.0  # seconds
_MAX_EMBED_CHARS = 7500  # nomic-embed-text has 8192 token context; ~4 chars/token


def _truncate(text: str, max_chars: int = _MAX_EMBED_CHARS) -> str:
    """Truncate text to stay within embedding model's context window."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


class EmbeddingService:
    def __init__(
        self,
        model: str = "nomic-embed-text",
        provider: str = "ollama",
        base_url: str = "http://localhost:11434",
        dimension: int = 768,
    ):
        self.model = model
        self.provider = provider
        self.base_url = base_url
        self.dimension = dimension
        self._st_model = None  # lazy-loaded sentence-transformers model
        self._warm = False

    def warmup(self) -> None:
        """Pre-load the embedding model by running a dummy embedding.
        Call once at startup to avoid cold-start latency on first query."""
        try:
            t0 = time.time()
            self.embed("warmup")
            logger.info("embedding_warmup_complete", model=self.model,
                        provider=self.provider, warmup_ms=round((time.time() - t0) * 1000))
        except Exception as e:
            logger.warning("embedding_warmup_failed", error=str(e),
                           hint="Embedding will be loaded on first use")

    # ── Public API ───────────────────────────────────────────────────────
    def embed(self, text: str) -> np.ndarray:
        text = _truncate(text)
        if self.provider == "ollama":
            return self._ollama_embed(text)
        return self._st_embed([text])[0]

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        texts = [_truncate(t) for t in texts]
        if self.provider == "ollama":
            return self._ollama_embed_batch(texts)
        return self._st_embed(texts)

    def _ollama_embed_batch(self, texts: list[str]) -> np.ndarray:
        """Batch embed via Ollama — processes in batches of BATCH_SIZE for efficiency."""
        BATCH_SIZE = 32
        all_embeddings: list[np.ndarray] = []
        for batch_start in range(0, len(texts), BATCH_SIZE):
            batch = texts[batch_start:batch_start + BATCH_SIZE]
            batch_embeddings: list[np.ndarray] = []
            for t in batch:
                batch_embeddings.append(self._ollama_embed(t))
            all_embeddings.extend(batch_embeddings)
            if batch_start + BATCH_SIZE < len(texts):
                logger.info("embedding_progress", done=batch_start + len(batch), total=len(texts))
        return np.stack(all_embeddings)

    # ── Ollama provider ──────────────────────────────────────────────────
    def _ollama_embed(self, text: str) -> np.ndarray:
        last_err: Optional[Exception] = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = httpx.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                    timeout=60.0,
                )
                resp.raise_for_status()
                data = resp.json()
                vec = np.array(data["embedding"], dtype=np.float32)
                if not self._warm:
                    logger.info("embedding_model_ready", model=self.model, provider="ollama", dim=len(vec))
                    self._warm = True
                return vec
            except httpx.ConnectError as e:
                last_err = e
                logger.warning(
                    "ollama_connect_failed",
                    attempt=attempt,
                    url=self.base_url,
                    hint="Is Ollama running? → ollama serve",
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAY * attempt)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    raise RuntimeError(
                        f"Ollama model '{self.model}' not found. "
                        f"Pull it first: ollama pull {self.model}"
                    ) from e
                last_err = e
                logger.error("ollama_http_error", status=e.response.status_code, body=e.response.text[:200])
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAY)
            except Exception as e:
                last_err = e
                logger.error("ollama_embed_error", error=str(e))
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAY)

        raise RuntimeError(
            f"Ollama embedding failed after {_MAX_RETRIES} attempts: {last_err}"
        ) from last_err

    # ── sentence-transformers provider ───────────────────────────────────
    def _st_embed(self, texts: list[str]) -> np.ndarray:
        if self._st_model is None:
            logger.info("loading_sentence_transformer", model=self.model)
            try:
                from sentence_transformers import SentenceTransformer
                self._st_model = SentenceTransformer(self.model)
                logger.info("sentence_transformer_ready", model=self.model)
            except Exception as e:
                raise RuntimeError(
                    f"Failed to load sentence-transformers model '{self.model}': {e}"
                ) from e
        embeddings = self._st_model.encode(texts, normalize_embeddings=True)
        return np.array(embeddings, dtype=np.float32)
