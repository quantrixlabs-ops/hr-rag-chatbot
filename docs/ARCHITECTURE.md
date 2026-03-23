# HR RAG Chatbot — System Architecture

> Unified architecture reference covering all 5 phases of the enterprise HR chatbot platform.
> For UX/UI specifics see [UXUI_DESIGN.md](UXUI_DESIGN.md).
> For the QA test report see [QA_TEST_REPORT.md](QA_TEST_REPORT.md).

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture Diagram](#2-architecture-diagram)
3. [Tech Stack](#3-tech-stack)
4. [Phase Summary](#4-phase-summary)
5. [RAG Pipeline](#5-rag-pipeline)
6. [Database & Storage](#6-database--storage)
7. [Authentication & Security](#7-authentication--security)
8. [Multi-Tenancy](#8-multi-tenancy)
9. [HRMS Integrations](#9-hrms-integrations)
10. [Async Processing](#10-async-processing)
11. [Caching & Performance](#11-caching--performance)
12. [Observability](#12-observability)
13. [Deployment](#13-deployment)
14. [API Reference](#14-api-reference)
15. [Configuration Reference](#15-configuration-reference)
16. [Key Thresholds](#16-key-thresholds)

---

## 1. System Overview

An enterprise-grade HR chatbot that answers employee questions using **Retrieval-Augmented Generation (RAG)**. The system retrieves relevant HR policy documents, grounds LLM responses in factual content, verifies answer faithfulness, and integrates with HRMS systems for live data — reducing hallucination to enterprise-acceptable levels.

### Key Capabilities

| Capability | Description |
|---|---|
| **Grounded Q&A** | Answers backed by retrieved HR documents with source citations |
| **Hybrid Retrieval** | Dense (Qdrant/FAISS) + BM25 keyword + cross-encoder reranking |
| **Hallucination Detection** | Claim-level verification with faithfulness scoring |
| **Multi-Turn Conversations** | Session memory with context-aware follow-up |
| **RBAC (4 Roles)** | employee / manager / hr_admin / super_admin |
| **Multi-Tenancy** | Tenant isolation at DB, vector store, and cache layers |
| **Live HRMS Data** | BambooHR + SAP SuccessFactors adapters for leave/payroll/org data |
| **MFA / TOTP** | Two-factor authentication with recovery codes |
| **GDPR Compliance** | Art. 15 data export + Art. 17 erasure |
| **Streaming Responses** | SSE token-by-token delivery |
| **Async Ingestion** | Celery + Redis background document processing |
| **Semantic Cache** | Redis-backed tenant-scoped query cache |
| **Multi-Model Routing** | Fast/Standard/Advanced tiers with complexity classification |
| **Observability** | Prometheus metrics, OpenTelemetry tracing, Grafana dashboards |
| **Kubernetes Ready** | Helm charts with HPA, PDB, health probes |

---

## 2. Architecture Diagram

```
                            ┌────────────────────────────┐
                            │       LOAD BALANCER         │
                            │   (nginx / K8s Ingress)     │
                            └─────────┬──────────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              │                       │                       │
     ┌────────┴────────┐    ┌────────┴────────┐    ┌────────┴────────┐
     │   FRONTEND       │    │   API (FastAPI)   │    │  INTEGRATION    │
     │   React 18 +     │    │   Port 8000       │    │  Slack / Teams  │
     │   TypeScript +   │◄──►│                   │◄──►│  Webhooks       │
     │   Tailwind CSS   │    │  Auth │ Chat      │    │  HRMS Adapters  │
     │   Port 3000      │    │  Docs │ Admin     │    │                 │
     └─────────────────┘    │  GDPR │ Compliance│    └─────────────────┘
                             │  Tenant│ SSO      │
                             └───┬────┬────┬────┘
                                 │    │    │
                    ┌────────────┘    │    └────────────┐
                    │                 │                  │
           ┌────────┴───────┐ ┌──────┴──────┐  ┌───────┴───────┐
           │  PostgreSQL     │ │   Qdrant     │  │    Redis       │
           │  (via PgBouncer)│ │   Vector DB   │  │  Broker +      │
           │  Primary +      │ │  tenant_id    │  │  Cache +       │
           │  Read Replica   │ │  on payloads  │  │  Rate Limits   │
           └────────────────┘ └──────────────┘  └───────────────┘
                    │                                    │
           ┌────────┴───────┐                   ┌───────┴───────┐
           │  MinIO (S3)     │                   │  Celery        │
           │  Document       │                   │  Worker + Beat │
           │  Storage        │                   │  Async Jobs    │
           └────────────────┘                   └───────────────┘
                                                        │
                                                ┌───────┴───────┐
                                                │  Ollama        │
                                                │  LLM + Embed   │
                                                │  (multi-node)  │
                                                └───────────────┘

  ── Observability (optional profile) ──────────────────────────────
  │  Prometheus → Grafana → Alertmanager                           │
  │  Jaeger (OTLP gRPC) ← OpenTelemetry SDK                       │
  ──────────────────────────────────────────────────────────────────
```

---

## 3. Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Frontend** | React 18 + TypeScript + Vite + Tailwind CSS | SPA with streaming chat |
| **Backend** | FastAPI (Python 3.11+) | Async REST API + SSE |
| **LLM** | Ollama (llama3:8b default) | Answer generation, query expansion |
| **Embeddings** | nomic-embed-text (768-dim) via Ollama | Document and query embedding |
| **Vector Store** | Qdrant (primary), FAISS (fallback) | Dense vector search with tenant filtering |
| **Keyword Search** | BM25Okapi (rank-bm25) | Sparse keyword retrieval |
| **Reranker** | cross-encoder/ms-marco-MiniLM-L-6-v2 | Cross-encoder reranking |
| **Database** | PostgreSQL 16 (via PgBouncer) | Primary data store, Alembic migrations |
| **Object Storage** | MinIO (S3-compatible) | Document file storage |
| **Task Queue** | Celery 5 + Redis | Async ingestion, HRMS sync, webhooks |
| **Cache** | Redis 7 | Semantic cache, rate limiting, sessions |
| **Auth** | JWT (python-jose) + bcrypt + TOTP (pyotp) | Stateless auth with MFA |
| **SSO** | Authlib (OIDC) | Enterprise identity providers |
| **Encryption** | Fernet (cryptography) | PII encryption at rest |
| **Metrics** | prometheus-client | Custom counters and histograms |
| **Tracing** | OpenTelemetry SDK + OTLP gRPC | Distributed tracing to Jaeger |
| **Logging** | structlog (JSON) | Structured logs with request trace IDs |
| **CI/CD** | GitHub Actions | Lint → test → build → deploy pipeline |
| **Orchestration** | Docker Compose (dev), Helm/K8s (prod) | Container orchestration |

---

## 4. Phase Summary

### Phase 1 — Foundation

PostgreSQL + Qdrant as primary stores, SQLAlchemy Core, Alembic migrations, `tenant_id` on every table and every Qdrant chunk payload, JWT auth with RBAC, hybrid RAG pipeline, Docker Compose with 5 services (postgres, qdrant, ollama, api, frontend).

### Phase 2 — RBAC & Async Processing

Expanded to 4 roles (employee, manager, hr_admin, super_admin), Celery + Redis async document ingestion, permissions matrix, audit logging, user creation API with admin approval, document versioning, retry endpoint for failed ingestion.

### Phase 3 — Multi-Tenancy & SSO

Tenant middleware extracting `tenant_id` from JWT, tenant CRUD API, MinIO object storage, OIDC SSO via Authlib, feature flags in `tenants.config` JSONB, API versioning under `/api/v1/`, tenant config caching in Redis.

### Phase 4 — HRMS & Performance

HRMS adapter framework (BambooHR + SAP SuccessFactors), live HR data injected into RAG context, Redis-backed semantic cache (tenant-scoped), multi-model routing (fast/standard/advanced), LLM load balancer across Ollama nodes, Celery Beat scheduler (HRMS sync 4h, cache warm 6am, session cleanup 2am), webhook delivery with HMAC-SHA256 signing, PgBouncer (5000→25 connections), read replica routing.

### Phase 5 — Enterprise Hardening

Fernet encryption for PII at rest, TOTP MFA with recovery codes, GDPR Article 15 export + Article 17 erasure, compliance audit export with HMAC signatures, Prometheus metrics (15+ custom metrics), OpenTelemetry tracing to Jaeger, alerting rules (9 alerts), Grafana dashboard (10 panels), Kubernetes Helm charts with HPA/PDB, GitHub Actions CI/CD (6 stages), backup script.

### UX/UI Layer

Toast notifications, MFA step-up login flow, user settings page (profile/security/privacy), role-aware quick chips, date-grouped session sidebar with search and collapse, mobile responsive layout, tenant branding.

---

## 5. RAG Pipeline

### Stage 0 — Ambiguity Detection
- `QueryAnalyzer` classifies query type (factual / procedural / comparative / policy_lookup)
- Vague queries (short + broad topic + no specifics) → clarification prompt with topic-specific options
- HRMS data intent detection: keywords for leave balance, org chart, payroll → triggers live data fetch

### Stage 1 — Retrieval
- **Context injection**: Follow-up queries with pronouns get previous topic prepended
- **Query expansion**: Simple queries (≤12 words) rewritten by LLM for better coverage
- **Dense retrieval**: Qdrant (top 20) with `tenant_id` payload filtering
- **BM25 retrieval**: Keyword-based (top 20) with role filtering
- **Reciprocal Rank Fusion**: k=60, dense weight 0.6, BM25 weight 0.4
- **Cross-encoder reranking**: ms-marco-MiniLM-L-6-v2 → top 8 results

### Stage 2 — Context Building
- Token budget: 3,000 tokens
- Min relevance score: 0.20
- Deduplication by first 150 characters
- HRMS live data injected with `[LIVE HRMS DATA — ...]` prefix if detected

### Stage 3 — LLM Generation
- System prompt with 9 strict grounding rules
- Conversation history: last 3 turns
- Multi-model routing: complexity classifier selects fast/standard/advanced model
- Load balancer distributes across Ollama nodes (least-busy strategy)
- Temperature: 0.1, max tokens: 1,024

### Stage 4 — Verification
- Claim extraction (sentence-level, min 15 chars)
- Evidence matching (2+ shared 4-char words between claim and chunk)
- Faithfulness scoring: verified claims / total claims
- Verdict: grounded (≥0.6), partially_grounded (0.35–0.6), ungrounded (<0.35)
- Ungrounded answers get disclaimer prepended
- Citations extracted from `[Source: ...]` patterns or auto-generated from top 3 chunks

### Semantic Cache
- Redis-backed, tenant-scoped keys: `sc:hash:{tenant_id}:{hash}`
- Exact match (O(1)) then cosine similarity scan
- TTL-based expiry, `warm_cache()` for Celery Beat pre-population
- Falls back to in-memory dict if Redis unavailable

---

## 6. Database & Storage

### PostgreSQL (Primary)

All tables include `tenant_id` column. Managed via Alembic migrations (001–005).

**Core tables**: `users`, `sessions`, `messages`, `documents`, `document_versions`, `document_chunks`
**Auth tables**: `refresh_tokens`, `mfa_recovery_codes`
**Operations**: `ingestion_jobs`, `audit_logs`, `hrms_sync_log`, `webhook_events`
**Compliance**: `gdpr_consent_log`
**Multi-tenancy**: `tenants` (with `config` JSONB for feature flags, branding, HRMS settings)

### PgBouncer

Transaction-mode pooling. 5,000 max client connections → 25 server connections. API and workers connect via PgBouncer, not directly to PostgreSQL.

### Read Replica Routing

`write_db()` → always hits primary. `read_db()` → hits `READ_REPLICA_URL` if configured, primary fallback.

### Qdrant (Vector Store)

Collection `hr_chunks`, 768-dim vectors. Every point payload includes `tenant_id`, `access_roles`, `category`, `source`, `page`. Filtering via Qdrant's payload filter on search.

### MinIO (Object Storage)

S3-compatible. Bucket `hr-documents`. Original files stored with tenant-prefixed keys. Console UI on port 9001.

---

## 7. Authentication & Security

### Auth Flow

```
Register → Admin Approval → Login → [MFA if enabled] → Access Token (1h) + Refresh Token (7d)
         ↓                                                         ↓
    Every request:                                          Proactive refresh
    JWT validate → check revocation → load role from DB     5 min before expiry
```

### JWT Structure
- Algorithm: HS256
- Claims: sub (user_id), role, department, tenant_id, exp, iat, jti, iss, aud
- Role loaded from DB on every request (JWT role ignored)

### MFA / TOTP
- pyotp (RFC 6238) with QR code enrollment
- 8 bcrypt-hashed recovery codes (shown once)
- `mfa_required_for_role()` check per tenant config (hr_admin, super_admin)
- Step-up flow: password login returns `mfa_token`, then verify TOTP to get access tokens

### Encryption at Rest
- Fernet (AES-128-CBC) for PII fields (email, phone, etc.)
- `ENC:` prefix on ciphertext in DB columns
- `hash_for_lookup()` for indexed WHERE-clause queries on encrypted fields

### RBAC

| Role | Scope |
|---|---|
| `employee` | Own sessions, employee-level documents |
| `manager` | Employee access + manager-level documents + team analytics |
| `hr_admin` | Full access + admin APIs + document management |
| `super_admin` | Platform-wide: manage tenants, all hr_admin permissions |

### Rate Limiting

| Endpoint | Limit | Window |
|---|---|---|
| Login | 5 / minute / IP | Account lockout after 10 failures (15 min) |
| Registration | 3 / hour / IP | |
| Chat queries | 10 / minute / user | |
| Document upload | 5 / minute / user | |
| Global API | 60 / minute / IP | |

### Security Headers
X-Content-Type-Options: nosniff, X-Frame-Options: DENY, CSP: default-src 'self', HSTS: max-age=31536000 (production), Server: hr-chatbot.

### Input Protection
- 19 regex patterns for prompt injection (jailbreak, DAN, system prompt extraction)
- PII masking: emails, SSNs, phones, credit cards redacted before logging
- File upload: extension whitelist, 50MB limit, path traversal prevention, SHA-256 dedup

### GDPR Compliance
- **Article 15 (Export)**: `GET /api/v1/users/{id}/gdpr-export` — full JSON bundle
- **Article 17 (Erasure)**: `DELETE /api/v1/users/{id}/gdpr-erase` — anonymize messages, NULL audit log actor_id, hard-delete user record, immutable erasure audit entry with 7-year retention note
- **Audit signing**: HMAC-SHA256 integrity signatures on compliance export records

---

## 8. Multi-Tenancy

### Strategy
- **Logical isolation**: Single PostgreSQL database, `tenant_id` on every table
- **Vector isolation**: `tenant_id` in every Qdrant point payload, filtered on search
- **Cache isolation**: Redis keys prefixed with `tenant_id`
- **Feature flags**: `tenants.config` JSONB stores per-tenant feature toggles, HRMS provider, SSO config, branding

### Tenant Middleware
Extracts `tenant_id` from JWT on every request. Injected into request state for downstream use.

### SSO (OIDC)
Per-tenant SSO via `tenants.config.features.sso`. Uses Authlib for OIDC discovery + code exchange. Configurable per tenant (some use SSO, others use password auth).

---

## 9. HRMS Integrations

### Adapter Pattern

```python
class HRMSAdapter(ABC):
    async def get_employee(employee_id) -> dict
    async def get_leave_balance(employee_id) -> dict
    async def get_org_chart(department) -> dict
    async def get_payroll_info(employee_id) -> dict
    async def health() -> bool
```

### Implementations
- **BambooHR**: REST API, HTTP Basic Auth, maps leave policy names to annual/sick/carry_forward
- **SAP SuccessFactors**: OData v2, OAuth2 token caching with expiry buffer, `/Date(ms)/` parsing

### Live Data Flow
1. `HRMSDataIntent.detect()` classifies query for live data needs
2. `HRMSRouter.get_adapter(tenant_id)` reads `config.hrms.provider`
3. Adapter fetches data, formatted as `[LIVE HRMS DATA — ...]` context block
4. Injected into RAG context alongside document chunks
5. Graceful fallback: returns None on any HRMS failure

### Periodic Sync (Celery Beat)
Every 4 hours: fan-out per-tenant HRMS health check + data snapshot stored in Redis at `hrms:snapshot:{tenant_id}`.

---

## 10. Async Processing

### Celery Workers

| Queue | Tasks |
|---|---|
| `ingestion` | Document processing (extract → chunk → embed → index) |
| `hrms_sync` | Per-tenant HRMS data synchronization |
| `cache_warm` | Pre-populate semantic cache with top queries |
| `webhooks` | HMAC-signed webhook delivery with exponential backoff |
| `default` | Miscellaneous background tasks |

### Celery Beat Schedule

| Job | Schedule | Description |
|---|---|---|
| HRMS sync | Every 4 hours | Fan-out per-tenant adapter health + data snapshot |
| Cache warming | Daily 6:00 UTC | Top-50 queries per tenant → warm semantic cache |
| Session cleanup | Daily 2:00 UTC | Delete expired refresh tokens (>7 days or revoked) |

### Webhook Delivery
- HMAC-SHA256 signed payloads
- Exponential backoff: 30s → 60s → 120s (max 3 retries)
- 4xx = permanent failure (no retry), 5xx = transient (retry)

---

## 11. Caching & Performance

### Semantic Cache (Redis)
- Tenant-scoped keys: `sc:hash:{tenant_id}:{hash}`, `sc:emb:{tenant_id}:{hash}`, `sc:keys:{tenant_id}`
- Exact hash lookup (O(1)), then cosine similarity scan across tenant's key set
- Redis pipeline for atomic writes
- Warm via Celery Beat pre-population of top-50 queries

### PgBouncer
Transaction-mode pooling. 5,000 client connections → 25 PostgreSQL connections. Prevents connection exhaustion under load.

### Multi-Model Routing

| Tier | Default Model | Query Types |
|---|---|---|
| `fast` | `MODEL_FAST` env | Simple factual, greetings, single-lookup |
| `standard` | `MODEL_STANDARD` env | Procedural, multi-step, policy interpretation |
| `advanced` | `MODEL_ADVANCED` env | Comparative, multi-document synthesis, complex analysis |

If env vars are unset, all tiers fall back to `LLM_MODEL` (single-model dev mode).

### LLM Load Balancer
- `OLLAMA_NODES` env: comma-separated URLs for multiple Ollama instances
- Least-busy strategy: `min(healthy_nodes, key=lambda n: n.in_flight)`
- Background health checks every 30 seconds
- Single node = no balancing

---

## 12. Observability

### Prometheus Metrics

| Metric | Type | Labels |
|---|---|---|
| `hr_chatbot_query_total` | Counter | tenant_id, status |
| `hr_chatbot_query_latency_seconds` | Histogram | tenant_id |
| `hr_chatbot_llm_inference_seconds` | Histogram | model, tier |
| `hr_chatbot_rag_retrieval_seconds` | Histogram | tenant_id |
| `hr_chatbot_cache_hits_total` | Counter | tenant_id, type (hit/miss) |
| `hr_chatbot_active_sessions` | Gauge | tenant_id |
| `hr_chatbot_auth_attempts_total` | Counter | tenant_id, status |
| `hr_chatbot_ingestion_total` | Counter | tenant_id, status |
| `hr_chatbot_hrms_calls_total` | Counter | tenant_id, provider, operation, status |
| `hr_chatbot_webhook_deliveries_total` | Counter | tenant_id, event, status |
| `hr_chatbot_errors_total` | Counter | tenant_id, error_type |

### OpenTelemetry Tracing
- OTLP gRPC export to Jaeger (`OTEL_EXPORTER_OTLP_ENDPOINT`)
- FastAPI auto-instrumentation via `opentelemetry-instrumentation-fastapi`
- `span()` context manager for custom spans
- `get_trace_id()` for log correlation
- Disabled by default (`OTEL_TRACES_ENABLED=false`); enable when Jaeger is running

### Alerting Rules (Prometheus)

| Alert | Condition |
|---|---|
| LLMHighErrorRate | Error rate > 10% for 5 min |
| HighQueryLatency | p95 > 10s for 5 min |
| AllLLMNodesDown | All Ollama nodes unhealthy |
| HighIngestionFailureRate | Failure rate > 20% for 15 min |
| LowCacheHitRate | Hit rate < 20% for 30 min |
| BruteForceDetected | > 50 failed logins in 5 min |
| HighApplicationErrorRate | Error rate > 5% for 5 min |
| RedisDown | Redis unreachable for 2 min |
| DBPoolExhaustion | > 80% pool usage for 5 min |

### Grafana Dashboard (10 panels)
Query rate, latency P50/P95/P99, LLM inference P95, cache hit rate, active sessions, LLM node load, ingestion outcomes, RAG retrieval time, auth attempts, application errors.

---

## 13. Deployment

### Docker Compose (Development)

12 services total:

| Service | Image | Port | Purpose |
|---|---|---|---|
| `postgres` | postgres:16-alpine | 5432 | Primary database |
| `qdrant` | qdrant/qdrant:v1.9.0 | 6333/6334 | Vector store |
| `redis` | redis:7-alpine | 6379 | Broker + cache |
| `minio` | minio/minio:latest | 9000/9001 | Object storage |
| `ollama` | ollama/ollama:latest | 11434 | LLM + embeddings |
| `pgbouncer` | edoburu/pgbouncer:1.22.0 | 5433 | Connection pooler |
| `api` | ./backend | 8000 | FastAPI backend |
| `worker` | ./backend | — | Celery worker (4 queues) |
| `beat` | ./backend | — | Celery Beat scheduler |
| `frontend` | ./frontend | 3000 | React SPA |
| `prometheus` | prom/prometheus:v2.51.0 | 9090 | Metrics (monitoring profile) |
| `grafana` | grafana/grafana:10.4.0 | 3001 | Dashboards (monitoring profile) |
| `jaeger` | jaegertracing/all-in-one:1.56 | 16686 | Tracing (monitoring profile) |

```bash
# Core services
docker compose up -d

# With monitoring stack
docker compose --profile monitoring up -d
```

### Kubernetes (Helm)

Chart: `helm/hr-chatbot/`

- **API**: Deployment + Service + HPA (min=2, max=10, CPU target 70%) + PDB (minAvailable=1)
- **Worker**: Deployment (concurrency=4, all queues)
- **Beat**: Deployment (replicas=1 enforced — singleton)
- **Secrets**: `helm.sh/resource-policy: keep` annotation
- **Dependencies**: Bitnami PostgreSQL + Redis sub-charts
- **Health probes**: liveness → `/health`, readiness → `/health/ready`

### CI/CD (GitHub Actions)

6-stage pipeline:
1. **Lint** — ruff (Python) + eslint (TypeScript)
2. **Unit Tests** — SQLite + FAISS (no external services)
3. **Integration Tests** — Real PostgreSQL + Redis via GitHub Actions services
4. **Build** — Docker image → GitHub Container Registry
5. **Deploy Staging** — On `main` branch push
6. **Smoke Tests → Deploy Production** — On version tags only

### Backup

`scripts/backup.sh`: `pg_dump` (compressed custom format), Qdrant snapshots via API, MinIO upload via `mc`, 30-day retention cleanup.

---

## 14. API Reference

### Authentication

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | None | Create account (pending approval) |
| POST | `/auth/login` | None | Password auth → tokens (or `mfa_required`) |
| POST | `/auth/mfa/verify-login` | None | TOTP verification → tokens |
| POST | `/auth/logout` | Bearer | Revoke tokens |
| POST | `/auth/refresh` | None | Rotate token pair |

### Chat

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/chat/query` | Bearer | Query → answer with citations |
| POST | `/chat/query/stream` | Bearer | SSE streaming version |
| GET | `/chat/sessions` | Bearer | List user sessions |
| GET | `/chat/sessions/{id}/history` | Bearer | Session conversation turns |
| POST | `/chat/feedback` | Bearer | Record thumbs up/down |
| POST | `/chat/escalate` | Bearer | Escalate to HR representative |
| GET | `/chat/saved-prompts` | Bearer | List saved prompts |
| POST | `/chat/saved-prompts` | Bearer | Save a prompt |

### Documents

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/documents/upload` | hr_admin | Upload + ingest document |
| GET | `/documents` | Bearer | List documents (role-filtered) |
| DELETE | `/documents/{id}` | hr_admin | Delete document + chunks |
| POST | `/documents/batch-delete` | hr_admin | Batch delete (up to 50) |
| POST | `/documents/reindex` | hr_admin | Reindex one or all |
| GET | `/documents/{id}/content` | Bearer | View document content |

### Admin

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/admin/metrics` | hr_admin | Dashboard KPIs |
| GET | `/admin/failed-queries` | hr_admin | Low-confidence queries |
| GET | `/admin/security-events` | hr_admin | Security audit trail |
| GET | `/admin/users/pending` | hr_admin | Pending registrations |
| POST | `/admin/users/{id}/approve` | hr_admin | Approve/reject user |
| POST | `/admin/users/{id}/suspend` | hr_admin | Suspend user |

### GDPR & Compliance (under `/api/v1/`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/users/{id}/gdpr-export` | Bearer | Article 15 data export (JSON) |
| DELETE | `/users/{id}/gdpr-erase` | Bearer | Article 17 erasure |
| GET | `/compliance/audit-export` | hr_admin | Signed audit log export |
| GET | `/compliance/audit-export/verify` | hr_admin | Verify signature |
| POST | `/compliance/mfa/enroll` | Bearer | Start TOTP enrollment |
| POST | `/compliance/mfa/verify` | Bearer | Confirm enrollment + get recovery codes |
| DELETE | `/compliance/mfa/disable` | Bearer | Disable MFA |

### User Profile (under `/api/v1/`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/users/me` | Bearer | Get own profile |
| PATCH | `/users/me` | Bearer | Update profile fields |

### Tenants (under `/api/v1/`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/tenants/me/branding` | Bearer | Tenant branding (name, color, logo) |
| POST | `/tenants` | super_admin | Create tenant |
| PATCH | `/tenants/{id}` | super_admin | Update tenant config |

### Health

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | None | Liveness probe |
| GET | `/health/ready` | None | Readiness probe (vector store check) |
| GET | `/health/detailed` | hr_admin | Full system diagnostics |
| GET | `/metrics` | None | Prometheus metrics |

---

## 15. Configuration Reference

All settings via environment variables or `.env` file:

| Setting | Default | Description |
|---|---|---|
| `ENVIRONMENT` | development | development / production |
| `JWT_SECRET_KEY` | dev-secret... | JWT signing key (change in prod!) |
| `LLM_PROVIDER` | ollama | ollama / vllm |
| `LLM_MODEL` | llama3:8b | Default LLM model |
| `OLLAMA_BASE_URL` | http://localhost:11434 | Ollama server |
| `EMBEDDING_MODEL` | nomic-embed-text | Embedding model |
| `EMBEDDING_DIMENSION` | 768 | Vector dimensions |
| `VECTOR_STORE_BACKEND` | qdrant | qdrant / faiss |
| `QDRANT_URL` | http://localhost:6333 | Qdrant server |
| `DATABASE_URL` | postgresql://... | PostgreSQL connection |
| `REDIS_URL` | redis://localhost:6379/0 | Redis connection |
| `STORAGE_BACKEND` | minio | minio / local |
| `MINIO_ENDPOINT` | localhost:9000 | MinIO server |
| `DENSE_TOP_K` | 20 | Dense retrieval count |
| `BM25_TOP_K` | 20 | BM25 retrieval count |
| `RERANK_TOP_N` | 8 | Reranked results |
| `MAX_CONTEXT_TOKENS` | 3000 | Context budget |
| `LLM_TEMPERATURE` | 0.1 | LLM temperature |
| `MAX_RESPONSE_TOKENS` | 1024 | Max output tokens |
| `MODEL_FAST` | (LLM_MODEL) | Fast tier model |
| `MODEL_STANDARD` | (LLM_MODEL) | Standard tier model |
| `MODEL_ADVANCED` | (LLM_MODEL) | Advanced tier model |
| `OLLAMA_NODES` | (single) | Comma-separated Ollama URLs |
| `READ_REPLICA_URL` | (none) | PostgreSQL read replica |
| `HRMS_CACHE_TTL_SECONDS` | 14400 | HRMS data cache TTL |
| `ENCRYPTION_KEY` | (none) | Fernet key for PII encryption |
| `AUDIT_SIGN_SECRET` | (none) | HMAC key for audit signatures |
| `OTEL_TRACES_ENABLED` | false | Enable OpenTelemetry tracing |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | (none) | Jaeger/collector endpoint |

---

## 16. Key Thresholds

| Parameter | Value | Location |
|---|---|---|
| Chunk size | 400 words | ingestion_service.py |
| Chunk overlap | 60 words | ingestion_service.py |
| Max chunks/document | 500 | ingestion_service.py |
| Max file size | 50 MB | document_routes.py |
| Max query length | 1,000 chars | chat_routes.py |
| Min relevance score | 0.20 | context_builder.py |
| RRF dense weight | 0.6 | config.py |
| RRF BM25 weight | 0.4 | config.py |
| Access token expiry | 60 min | config.py |
| Refresh token expiry | 7 days | security.py |
| Grounded threshold | ≥ 0.6 | verification_service.py |
| Partial threshold | 0.35–0.6 | verification_service.py |
| Ungrounded threshold | < 0.35 | verification_service.py |
| PgBouncer max clients | 5,000 | docker-compose.yml |
| PgBouncer pool size | 25 | docker-compose.yml |
| Inactivity timeout | 30 min | App.tsx |
| Password min length | 12 chars | auth_routes.py |
| MFA recovery codes | 8 codes | totp.py |
| Webhook max retries | 3 | webhook_tasks.py |
| Webhook backoff base | 30s | webhook_tasks.py |
| HRMS sync interval | 4 hours | celery_app.py |
| Cache warm schedule | Daily 6am UTC | celery_app.py |
| Session cleanup | Daily 2am UTC | celery_app.py |
