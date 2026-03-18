"""FastAPI application entry point — wires all services at startup.

CRITICAL: OpenMP env vars MUST be set before any C-extension import.
torch, faiss-cpu, and scikit-learn each bundle their own libomp.dylib
on macOS. When Python loads more than one, the OpenMP runtime aborts:

    OMP: Error #15: Initializing libomp.dylib, but found libomp.dylib
         already initialized.

Setting KMP_DUPLICATE_LIB_OK=TRUE tells the Intel OpenMP runtime to
tolerate the duplicate.  OMP_NUM_THREADS=1 avoids contention in a
web-server process where concurrency is managed by uvicorn workers.
"""

from __future__ import annotations

# ── MUST be the very first executable lines in the module ────────────────────
import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# ─────────────────────────────────────────────────────────────────────────────

import sqlite3
import time as import_time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import structlog
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from backend.app.core.config import get_settings
from backend.app.core.dependencies import set_registry, get_registry
from backend.app.core.logging import configure_logging
from backend.app.database.session_store import SessionStore, init_database

logger = structlog.get_logger()


# ── Ollama connectivity check ────────────────────────────────────────────────
def _check_ollama(base_url: str) -> dict[str, str]:
    """Validate Ollama is reachable and required models are pulled."""
    status: dict[str, str] = {}
    try:
        resp = httpx.get(f"{base_url}/api/tags", timeout=5.0)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        status["ollama_connection"] = "ok"
        status["ollama_models"] = ", ".join(models) if models else "none"
    except httpx.ConnectError:
        status["ollama_connection"] = f"UNREACHABLE at {base_url} — start Ollama first"
    except Exception as e:
        status["ollama_connection"] = f"error: {e}"
    return status


# ── Directory bootstrapping ──────────────────────────────────────────────────
def _ensure_dirs(s) -> None:
    """Create data directories if they don't exist."""
    for d in [s.faiss_index_dir, s.upload_dir, str(Path(s.db_path).parent)]:
        os.makedirs(d, exist_ok=True)
        logger.info("dir_ensured", path=d)


# ── Service wiring ───────────────────────────────────────────────────────────
def _wire_services() -> dict:
    """Instantiate and wire all services — called once at startup."""
    s = get_settings()

    from backend.app.services.embedding_service import EmbeddingService
    emb = EmbeddingService(s.embedding_model, s.embedding_provider, s.ollama_base_url, s.embedding_dimension)
    emb.warmup()  # Pre-load embedding model at startup

    from backend.app.vectorstore.faiss_store import FAISSIndex
    vs = FAISSIndex(s.embedding_dimension, s.faiss_index_dir)
    vs.load()  # safe — returns False if no index on disk

    from backend.app.services.retrieval_service import BM25Retriever, DenseRetriever, Reranker, RetrievalOrchestrator
    bm25 = BM25Retriever()
    if vs.metadata:
        bm25.build_index(vs.metadata)
    dense = DenseRetriever(emb, vs)
    reranker = Reranker()
    reranker.warmup()  # Eagerly load cross-encoder to avoid cold-start latency
    retrieval = RetrievalOrchestrator(
        dense, bm25, reranker, s.dense_top_k, s.bm25_top_k,
        s.rerank_top_n, s.dense_weight, s.bm25_weight,
    )

    from backend.app.rag.orchestrator import ModelGateway
    llm = ModelGateway(s.llm_provider)
    llm.configure(s.llm_provider, s.vllm_base_url if s.llm_provider == "vllm" else s.ollama_base_url)

    from backend.app.rag.context_builder import ContextBuilder
    ctx = ContextBuilder(s.max_context_tokens)

    from backend.app.services.verification_service import AnswerVerifier
    verifier = AnswerVerifier()

    ss = SessionStore(s.db_path)

    from backend.app.services.ingestion_service import IngestionPipeline
    ingestion = IngestionPipeline(emb, vs, bm25)

    from backend.app.rag.pipeline import RAGPipeline
    rag = RAGPipeline(retrieval, ctx, llm, verifier, s)

    from backend.app.services.chat_service import ChatService
    chat = ChatService(ss, rag)

    return {
        "embedding": emb, "vector_store": vs, "bm25": bm25, "dense": dense,
        "reranker": reranker, "retrieval": retrieval, "llm": llm, "ctx": ctx,
        "verifier": verifier, "session_store": ss, "ingestion": ingestion,
        "rag": rag, "chat_service": chat,
    }


# ── Application lifespan ────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    s = get_settings()
    logger.info("starting", env=s.environment)

    # 1. Guarantee data dirs
    _ensure_dirs(s)

    # 2. Validate Ollama
    ollama_status = _check_ollama(s.ollama_base_url)
    for k, v in ollama_status.items():
        logger.info(k, status=v)
    if "UNREACHABLE" in ollama_status.get("ollama_connection", ""):
        logger.warning("ollama_offline", msg="LLM and embedding calls will fail until Ollama is started")

    # 3. Init DB + services
    init_database(s.db_path)
    reg = _wire_services()
    set_registry(reg)

    logger.info("ready", indexed_chunks=reg["vector_store"].total_chunks)
    yield

    # Shutdown
    logger.info("shutting_down")
    try:
        reg["vector_store"].save()
    except Exception as e:
        logger.error("faiss_save_failed", error=str(e))


# ── App factory ──────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    s = get_settings()
    # BUG-003: Disable Swagger/OpenAPI in production
    is_prod = s.environment == "production"
    app = FastAPI(
        title="HR RAG Chatbot API",
        description="Enterprise HR chatbot with RAG-grounded answers, RBAC, and multi-agent reasoning",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
    )

    # CORS for frontend dev servers
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Security headers for HTTPS readiness
    from starlette.middleware.base import BaseHTTPMiddleware
    from collections import defaultdict
    import time as _time
    import uuid as _uuid

    # Request trace ID middleware — adds X-Request-ID to every response and binds to structlog
    class RequestIdMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request_id = request.headers.get("X-Request-ID") or str(_uuid.uuid4())[:8]
            structlog.contextvars.clear_contextvars()
            structlog.contextvars.bind_contextvars(request_id=request_id)
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response

    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "connect-src 'self' http://localhost:8000; "
                "frame-ancestors 'none'"
            )
            response.headers["server"] = "hr-chatbot"
            if s.environment == "production":
                response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            return response

    # Global API rate limiting middleware — 60 requests/min per IP
    _global_rate: dict[str, list[float]] = defaultdict(list)
    GLOBAL_RATE_LIMIT = 60
    GLOBAL_RATE_WINDOW = 60  # seconds

    class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            # Skip rate limiting for health checks
            if request.url.path == "/health":
                return await call_next(request)
            client_ip = request.client.host if request.client else "unknown"
            now = _time.time()
            _global_rate[client_ip] = [t for t in _global_rate[client_ip]
                                        if now - t < GLOBAL_RATE_WINDOW]
            if len(_global_rate[client_ip]) >= GLOBAL_RATE_LIMIT:
                from starlette.responses import JSONResponse
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please slow down."},
                )
            _global_rate[client_ip].append(now)
            return await call_next(request)

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(GlobalRateLimitMiddleware)
    app.add_middleware(RequestIdMiddleware)

    # Routers
    from backend.app.api import auth_routes, chat_routes, document_routes, admin_routes
    app.include_router(auth_routes.router)
    app.include_router(chat_routes.router)
    app.include_router(document_routes.router)
    app.include_router(admin_routes.router)

    # Prometheus metrics — secured behind admin auth
    from backend.app.core.security import get_current_user, require_role
    from backend.app.models.chat_models import User

    @app.get("/metrics")
    async def prometheus_metrics(user: User = Depends(get_current_user)):
        require_role(user, "hr_admin")
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # VULN-003: Public health returns ONLY status — no infrastructure details
    @app.get("/health")
    def health():
        s = get_settings()
        reg = get_registry()
        try:
            vs = reg.get("vector_store")
            ok_vs = vs and vs.total_chunks >= 0
            with sqlite3.connect(s.db_path) as con:
                con.execute("SELECT 1")
            ok_db = True
        except Exception:
            ok_vs = False
            ok_db = False
        overall = "ok" if ok_vs and ok_db else "degraded"
        return {"status": overall}

    # Detailed health — admin only
    @app.get("/health/detailed")
    async def health_detailed(user: User = Depends(get_current_user)):
        require_role(user, "hr_admin")
        s = get_settings()
        reg = get_registry()
        checks: dict[str, str] = {}
        vs = reg.get("vector_store")
        checks["vector_store"] = f"ok ({vs.total_chunks} chunks)" if vs else "not_initialized"
        checks["llm_gateway"] = "configured" if reg.get("llm") else "not_initialized"
        ollama = _check_ollama(s.ollama_base_url)
        checks["ollama"] = ollama.get("ollama_connection", "unknown")
        try:
            with sqlite3.connect(s.db_path) as con:
                con.execute("SELECT 1")
            checks["database"] = "ok"
        except Exception as e:
            checks["database"] = f"error: {e}"
        overall = "operational" if all(
            "ok" in v or v == "configured" for v in checks.values()
        ) else "degraded"
        metrics = {}
        try:
            metrics["vector_index_size"] = vs.total_chunks if vs else 0
            with sqlite3.connect(s.db_path) as con:
                metrics["document_count"] = con.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
                metrics["chunk_count"] = con.execute("SELECT COALESCE(SUM(chunk_count),0) FROM documents").fetchone()[0]
                avg_latency = con.execute(
                    "SELECT AVG(latency_ms) FROM query_logs WHERE timestamp > ?",
                    (import_time.time() - 3600,)
                ).fetchone()[0]
                metrics["avg_query_latency_ms"] = round(avg_latency, 1) if avg_latency else 0
        except Exception:
            pass
        return {"status": overall, "checks": checks, "metrics": metrics, "version": "1.0.0"}

    return app


app = create_app()
