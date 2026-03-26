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
os.environ.setdefault("HF_HUB_OFFLINE", "1")          # Skip HuggingFace online checks
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")     # Use locally cached models only
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
def _check_ollama(base_url: str) -> dict:
    """Validate Ollama is reachable and required models are pulled."""
    status = {}  # type: dict
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
def _build_vector_store(s):
    """Select and initialize vector store based on VECTOR_STORE_BACKEND config.

    qdrant (default): self-hosted Qdrant — supports tenant_id filtering (Phase 3 ready)
    faiss (fallback):  in-process FAISS — for local dev without Docker
    """
    if s.vector_store_backend == "qdrant":
        try:
            from backend.app.vectorstore.qdrant_store import QdrantStore
            vs = QdrantStore(url=s.qdrant_url, collection=s.qdrant_collection, dimension=s.embedding_dimension)
            vs.ensure_collection()
            logger.info("vector_store_selected", backend="qdrant", url=s.qdrant_url)
            return vs
        except Exception as exc:
            logger.warning("qdrant_init_failed", error=str(exc), fallback="faiss")
            # Fall through to FAISS

    from backend.app.vectorstore.faiss_store import FAISSIndex
    vs = FAISSIndex(s.embedding_dimension, s.faiss_index_dir)
    vs.load()
    logger.info("vector_store_selected", backend="faiss", dir=s.faiss_index_dir)
    return vs


def _wire_services() -> dict:
    """Instantiate and wire all services — called once at startup."""
    s = get_settings()

    from backend.app.services.embedding_service import EmbeddingService
    emb = EmbeddingService(s.embedding_model, s.embedding_provider, s.ollama_base_url, s.embedding_dimension)
    emb.warmup()  # Pre-load embedding model at startup

    # Vector store — Qdrant (primary) or FAISS (fallback)
    vs = _build_vector_store(s)

    from backend.app.services.retrieval_service import BM25Retriever, DenseRetriever, Reranker, RetrievalOrchestrator
    bm25 = BM25Retriever()
    # FAISS exposes .metadata; Qdrant does not pre-load all metadata in memory
    if hasattr(vs, "metadata") and vs.metadata:
        bm25.build_index(vs.metadata)
    dense = DenseRetriever(emb, vs)
    reranker = Reranker()
    reranker.warmup()  # Eagerly load cross-encoder to avoid cold-start latency
    retrieval = RetrievalOrchestrator(
        dense, bm25, reranker, s.dense_top_k, s.bm25_top_k,
        s.rerank_top_n, s.dense_weight, s.bm25_weight,
    )

    from backend.app.rag.orchestrator import ModelGateway
    internal_llm = ModelGateway(s.llm_provider)
    internal_llm.configure(s.llm_provider, s.vllm_base_url if s.llm_provider == "vllm" else s.ollama_base_url)

    # Wrap internal LLM with AI Router for external provider fallback
    from backend.app.services.ai_router import AIRouter
    llm = AIRouter(internal_llm, s)

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
        "reranker": reranker, "retrieval": retrieval,
        "llm": llm, "model_gateway": internal_llm,  # llm=AIRouter, model_gateway=internal
        "ctx": ctx, "verifier": verifier, "session_store": ss,
        "ingestion": ingestion, "rag": rag, "chat_service": chat,
    }


# ── Application lifespan ────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    s = get_settings()
    logger.info("starting", env=s.environment)

    # Phase 5: Initialize OpenTelemetry distributed tracing
    from backend.app.core.tracing import init_tracing
    init_tracing()

    # 1. Guarantee data dirs
    _ensure_dirs(s)

    # 2. Validate Ollama
    ollama_status = _check_ollama(s.ollama_base_url)
    for k, v in ollama_status.items():
        logger.info(k, status=v)
    if "UNREACHABLE" in ollama_status.get("ollama_connection", ""):
        logger.warning("ollama_offline", msg="LLM and embedding calls will fail until Ollama is started")

    # 3. Init DB + services
    # Initialize SQLite (session store — always needed for session/user management)
    init_database(s.db_path)

    # Seed default FAQ entries if table is empty
    try:
        from backend.app.services.faq_service import FAQService
        seeded = FAQService(s.db_path).seed_defaults()
        if seeded:
            logger.info("faq_seeded", count=seeded)
    except Exception as e:
        logger.warning("faq_seed_failed", error=str(e))

    # Initialize PostgreSQL schema if DATABASE_URL points to PostgreSQL
    if s.database_url.startswith("postgresql"):
        try:
            from backend.app.database.postgres import init_postgres_schema
            init_postgres_schema()
            logger.info("postgres_initialized")
        except Exception as e:
            logger.warning("postgres_init_failed", error=str(e), fallback="sqlite_only")

    reg = _wire_services()
    set_registry(reg)

    chunks = reg["vector_store"].total_chunks
    logger.info("ready", indexed_chunks=chunks)
    if s.environment != "production":
        print("\n" + "=" * 60)
        print("  HR RAG Chatbot — Ready")
        print("=" * 60)
        print(f"  API:      http://localhost:{s.api_port}")
        print(f"  Docs:     http://localhost:{s.api_port}/docs")
        print(f"  Chunks:   {chunks} indexed")
        print(f"  LLM:      {s.llm_model} via {s.llm_provider}")
        print("-" * 60)
        print("  Demo Credentials:")
        print("    admin      / Admin@12345!!     (hr_admin)")
        print("    manager1   / Manager@12345!!   (manager)")
        print("    employee1  / Employee@12345!!  (employee)")
        print("=" * 60 + "\n")
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

    # Global exception handler — ensures CORS headers on 500 errors
    from fastapi.responses import JSONResponse as _JSONResponse
    from fastapi import Request as _Request

    @app.exception_handler(Exception)
    async def global_exception_handler(request: _Request, exc: Exception):
        logger.error("unhandled_exception", error=str(exc)[:200], path=str(request.url.path))
        origin = request.headers.get("origin", "")
        resp = _JSONResponse(status_code=500, content={"detail": str(exc)[:200]})
        if origin:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Credentials"] = "true"
        return resp

    # CORS for frontend dev servers
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:3002",
            "http://localhost:3003",
            "http://localhost:5173",
            "http://localhost:5174",
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
            # CSP only for production HTML pages — skip for API responses
            # to avoid blocking frontend dev servers on different ports
            if s.environment == "production":
                response.headers["Content-Security-Policy"] = (
                    "default-src 'self'; "
                    "script-src 'self'; "
                    "style-src 'self' 'unsafe-inline'; "
                    "img-src 'self' data:; "
                    "connect-src 'self'; "
                    "frame-ancestors 'none'"
                )
                response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            response.headers["server"] = "hr-chatbot"
            return response

    # Global API rate limiting middleware — 300 requests/min per IP
    # Frontend polls sessions + notifications every 10s = ~12 req/min baseline;
    # plus normal clicks, uploads, chat — 300/min gives ample headroom.
    _global_rate: defaultdict = defaultdict(list)
    GLOBAL_RATE_LIMIT = 600
    GLOBAL_RATE_WINDOW = 60  # seconds

    class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            # Skip rate limiting for health checks and CORS preflight
            if request.url.path == "/health" or request.method == "OPTIONS":
                return await call_next(request)
            client_ip = request.client.host if request.client else "unknown"
            now = _time.time()
            _global_rate[client_ip] = [t for t in _global_rate[client_ip]
                                        if now - t < GLOBAL_RATE_WINDOW]
            if len(_global_rate[client_ip]) >= GLOBAL_RATE_LIMIT:
                from starlette.responses import JSONResponse
                origin = request.headers.get("origin", "")
                resp = JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please slow down."},
                )
                # Ensure CORS headers are present so browsers don't mask the error
                if origin:
                    resp.headers["Access-Control-Allow-Origin"] = origin
                    resp.headers["Access-Control-Allow-Credentials"] = "true"
                return resp
            _global_rate[client_ip].append(now)
            return await call_next(request)

    # IP allowlisting for admin endpoints (Phase B)
    _admin_allowed_ips = set(
        ip.strip() for ip in s.admin_allowed_ips.split(",") if ip.strip()
    ) if s.admin_allowed_ips else set()

    class AdminIPAllowlistMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if _admin_allowed_ips and request.url.path.startswith("/admin"):
                client_ip = request.client.host if request.client else "unknown"
                if client_ip not in _admin_allowed_ips and client_ip != "127.0.0.1":
                    from starlette.responses import JSONResponse
                    origin = request.headers.get("origin", "")
                    resp = JSONResponse(status_code=403, content={"detail": "IP not allowed"})
                    if origin:
                        resp.headers["Access-Control-Allow-Origin"] = origin
                        resp.headers["Access-Control-Allow-Credentials"] = "true"
                    return resp
            return await call_next(request)

    # Phase 3: Tenant resolution middleware
    # Runs after auth to resolve tenant_id from JWT claim or X-Tenant-Slug header.
    # Sets ContextVar so all downstream services read the correct tenant automatically.
    class TenantMiddleware(BaseHTTPMiddleware):
        _SKIP_PATHS = {"/health", "/health/detailed", "/info", "/metrics",
                       "/api/v1/tenants/me/branding", "/api/v1/tenants/register"}

        async def dispatch(self, request, call_next):
            if request.url.path in self._SKIP_PATHS:
                return await call_next(request)

            from backend.app.core.tenant import set_current_tenant, resolve_tenant_from_request
            slug_header = request.headers.get("X-Tenant-Slug")
            jwt_payload = None

            # Try to peek at JWT without raising (auth middleware runs inside routes)
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                try:
                    from backend.app.core.security import decode_token
                    jwt_payload = decode_token(auth_header[7:])
                except Exception:
                    pass

            tenant_id, config = resolve_tenant_from_request(jwt_payload, slug_header)
            set_current_tenant(tenant_id, config)
            return await call_next(request)

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(GlobalRateLimitMiddleware)
    app.add_middleware(TenantMiddleware)
    app.add_middleware(RequestIdMiddleware)
    if _admin_allowed_ips:
        app.add_middleware(AdminIPAllowlistMiddleware)

    # Phase 3: All routes under /api/v1/ prefix
    # Legacy paths (no prefix) kept for backward compatibility during migration.
    from backend.app.api import auth_routes, chat_routes, document_routes, admin_routes, user_routes, integration_routes
    from backend.app.api import tenant_routes
    # Phase 5: GDPR + compliance routes
    from backend.app.api import gdpr_routes, compliance_routes
    # Phase B: Ticket system
    from backend.app.api import ticket_routes
    # Phase D: Notifications + Complaints
    from backend.app.api import notification_routes, complaint_routes
    # Phase F: Branches + HR Contacts
    from backend.app.api import branch_routes, hr_contact_routes
    # FAQ management
    from backend.app.api import faq_routes
    # CFLS: Controlled Feedback Learning System
    from backend.app.api import cfls_routes
    # AI Configuration: External provider management (Admin only)
    from backend.app.api import ai_config_routes

    API_V1 = "/api/v1"
    app.include_router(auth_routes.router, prefix=API_V1)
    app.include_router(chat_routes.router, prefix=API_V1)
    app.include_router(document_routes.router, prefix=API_V1)
    app.include_router(admin_routes.router, prefix=API_V1)
    app.include_router(user_routes.router, prefix=API_V1)
    app.include_router(integration_routes.router, prefix=API_V1)
    app.include_router(tenant_routes.router, prefix=API_V1)
    app.include_router(gdpr_routes.router, prefix=API_V1)
    app.include_router(compliance_routes.router, prefix=API_V1)
    app.include_router(ticket_routes.router, prefix=API_V1)
    app.include_router(notification_routes.router, prefix=API_V1)
    app.include_router(complaint_routes.router, prefix=API_V1)
    app.include_router(branch_routes.router, prefix=API_V1)
    app.include_router(hr_contact_routes.router, prefix=API_V1)
    app.include_router(faq_routes.router, prefix=API_V1)
    app.include_router(cfls_routes.router, prefix=API_V1)
    app.include_router(ai_config_routes.router, prefix=API_V1)

    # Backward-compat: legacy routes (no /api/v1 prefix) — redirect to v1
    app.include_router(auth_routes.router)
    app.include_router(chat_routes.router)
    app.include_router(document_routes.router)
    app.include_router(admin_routes.router)
    app.include_router(user_routes.router)
    app.include_router(integration_routes.router)
    app.include_router(ticket_routes.router)
    app.include_router(notification_routes.router)
    app.include_router(complaint_routes.router)
    app.include_router(branch_routes.router)
    app.include_router(hr_contact_routes.router)
    app.include_router(faq_routes.router)
    app.include_router(cfls_routes.router)
    app.include_router(ai_config_routes.router)

    # Prometheus metrics — secured behind admin auth
    from backend.app.core.security import get_current_user, require_role
    from backend.app.models.chat_models import User

    @app.get("/metrics")
    async def prometheus_metrics(user: User = Depends(get_current_user)):
        require_role(user, "hr_admin")
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # Public app info (non-sensitive, used by frontend for branding)
    @app.get("/info")
    def app_info():
        return {"company_name": s.company_name, "version": "1.0.0"}

    # VULN-003: Public health returns ONLY status — no infrastructure details
    @app.get("/health")
    def health():
        s = get_settings()
        reg = get_registry()
        ok_vs, ok_db = False, False
        try:
            vs = reg.get("vector_store")
            ok_vs = vs is not None and vs.total_chunks >= 0
        except Exception:
            ok_vs = False
        try:
            if s.database_url.startswith("postgresql"):
                from backend.app.database.postgres import check_postgres_health
                ok_db = check_postgres_health().get("status") == "ok"
            else:
                with sqlite3.connect(s.db_path) as con:
                    con.execute("SELECT 1")
                ok_db = True
        except Exception:
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

        # Vector store
        vs = reg.get("vector_store")
        if vs:
            if hasattr(vs, "health"):
                vh = vs.health()
                checks["vector_store"] = f"ok ({vs.total_chunks} chunks)" if vh.get("status") == "ok" else f"error: {vh.get('detail')}"
            else:
                checks["vector_store"] = f"ok ({vs.total_chunks} chunks)"
        else:
            checks["vector_store"] = "not_initialized"

        # LLM
        checks["llm_gateway"] = "configured" if reg.get("llm") else "not_initialized"

        # Ollama
        ollama = _check_ollama(s.ollama_base_url)
        checks["ollama"] = ollama.get("ollama_connection", "unknown")

        # Database
        try:
            if s.database_url.startswith("postgresql"):
                from backend.app.database.postgres import check_postgres_health
                pg = check_postgres_health()
                checks["database"] = f"postgresql:{pg['status']}"
            else:
                with sqlite3.connect(s.db_path) as con:
                    con.execute("SELECT 1")
                checks["database"] = "sqlite:ok"
        except Exception as e:
            checks["database"] = f"error: {e}"

        overall = "operational" if all(
            "ok" in v or v == "configured" for v in checks.values()
        ) else "degraded"

        metrics: dict = {}
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

        return {
            "status": overall,
            "checks": checks,
            "metrics": metrics,
            "version": "1.0.0",
            "vector_store_backend": s.vector_store_backend,
            "database_backend": "postgresql" if s.database_url.startswith("postgresql") else "sqlite",
        }

    # Phase 5: Wire OpenTelemetry FastAPI auto-instrumentation
    from backend.app.core.tracing import instrument_fastapi
    instrument_fastapi(app)

    # Phase 5: /health/ready — K8s readiness probe
    # Returns 503 if key dependencies (DB, vector store) are not ready
    @app.get("/health/ready")
    def health_ready():
        """Kubernetes readiness probe — returns 200 only when fully ready."""
        reg = get_registry()
        vs = reg.get("vector_store")
        if vs is None:
            from starlette.responses import JSONResponse
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "reason": "vector_store_not_initialized"},
            )
        return {"status": "ready"}

    return app


app = create_app()
