"""Application configuration via Pydantic BaseSettings — Section 2.3 & Appendix B."""

from __future__ import annotations

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ── Application ──────────────────────────────────────────────────────
    app_name: str = "hr-rag-chatbot"
    environment: str = "development"
    api_port: int = 8000
    debug: bool = False

    # ── Authentication (Section 17.1) ────────────────────────────────────
    jwt_secret_key: str = Field(default="change-me-in-production-256-bit-min")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60  # 1-hour tokens (PHASE 9)

    # ── LLM Gateway (Section 10) ─────────────────────────────────────────
    llm_provider: str = "ollama"  # "ollama" | "vllm"
    llm_model: str = "llama3:8b"
    vllm_base_url: str = "http://localhost:8001/v1"
    ollama_base_url: str = "http://localhost:11434"

    # ── Embedding Service (Section 3.2) ──────────────────────────────────
    embedding_model: str = "nomic-embed-text"
    embedding_provider: str = "ollama"  # "ollama" | "sentence-transformers"
    embedding_dimension: int = 768

    # ── Vector Store (Section 7) ─────────────────────────────────────────
    vector_store_backend: str = "faiss"  # "faiss" | "qdrant"
    qdrant_url: str = "http://localhost:6333"
    faiss_index_dir: str = "./data/faiss_index"

    # ── Database ─────────────────────────────────────────────────────────
    database_url: str = "sqlite:///./data/hr_chatbot.db"
    db_path: str = "./data/hr_chatbot.db"

    # ── Redis ────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379"

    # ── RAG Pipeline (Section 4.2) ───────────────────────────────────────
    dense_top_k: int = 20
    bm25_top_k: int = 20
    rerank_top_n: int = 8
    final_context_chunks: int = 5
    max_context_tokens: int = 3000
    llm_temperature: float = 0.1
    max_response_tokens: int = 1024
    verify_grounding: bool = True
    min_faithfulness_score: float = 0.7
    session_context_turns: int = 5
    dense_weight: float = 0.6
    bm25_weight: float = 0.4

    # ── Company Info ─────────────────────────────────────────────────────
    company_name: str = "Acme Corp"
    hr_contact_email: str = "your HR department"  # PHASE 7: no hardcoded email

    # ── File Storage ─────────────────────────────────────────────────────
    upload_dir: str = "./data/uploads"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
