"""Application configuration via Pydantic BaseSettings — Section 2.3 & Appendix B."""

from __future__ import annotations

from typing import Optional

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
    # Primary: qdrant (self-hosted, supports tenant_id filtering for Phase 3)
    # Fallback: faiss (in-process, for local dev without Docker)
    vector_store_backend: str = "qdrant"  # "qdrant" | "faiss"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "hr_chunks"
    faiss_index_dir: str = "./data/faiss_index"

    # ── Database ─────────────────────────────────────────────────────────
    # Primary: PostgreSQL (concurrent writes, row-level security in Phase 3)
    # Fallback: SQLite (local dev without Docker)
    database_url: str = "postgresql://hr_user:hr_dev_password_change_in_prod@localhost:5432/hr_chatbot"
    db_path: str = "./data/hr_chatbot.db"  # SQLite fallback

    # ── Redis ────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── RAG Pipeline (Section 4.2) ───────────────────────────────────────
    dense_top_k: int = 20
    bm25_top_k: int = 20
    rerank_top_n: int = 8
    final_context_chunks: int = 5
    max_context_tokens: int = 3000
    llm_temperature: float = 0.0
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
    # ── File Storage — Phase 3: MinIO (primary), local (fallback) ────────────
    storage_backend: str = "minio"
    upload_dir: str = "./data/uploads"       # local fallback path
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin123"
    minio_bucket: str = "hr-documents"

    # ── SSO (per-tenant config, not global) ──────────────────────────────────
    sso_enabled: bool = False                # global switch; per-tenant via config.features.sso

    # ── Phase 4: Multi-model routing ────────────────────────────────────
    model_fast: str = ""      # e.g. "llama3.2:3b"
    model_standard: str = ""  # e.g. "llama3.1:8b"
    model_advanced: str = ""  # e.g. "llama3.1:70b"

    # ── Phase 4: Multi-Ollama load balancing ─────────────────────────────
    ollama_nodes: str = ""    # Comma-separated URLs; empty → use ollama_base_url

    # ── Phase 4: Read replica ─────────────────────────────────────────────
    read_replica_url: str = ""  # Empty → use primary for all reads

    # ── Phase 4: HRMS ─────────────────────────────────────────────────────
    hrms_cache_ttl_seconds: int = 14400  # 4 hours

    # ── Enterprise Security (Phase B) ─────────────────────────────────
    admin_allowed_ips: str = ""  # Comma-separated IPs, empty = allow all
    api_keys: str = ""  # Comma-separated API keys for service-to-service auth
    session_inactivity_minutes: int = 30  # Frontend idle timeout
    data_retention_days: int = 365  # How long to keep logs/audit trails
    encryption_key: str = ""  # Fernet key for data-at-rest encryption (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

    # ── Email / SMTP (Phase 2: OTP password reset) ────────────────────────
    smtp_host: str = ""           # e.g. "smtp.gmail.com" — empty = email OTP disabled
    smtp_port: int = 587
    smtp_user: str = ""           # e.g. "noreply@company.com"
    smtp_password: str = ""
    smtp_from_name: str = "HR Chatbot"
    smtp_use_tls: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
