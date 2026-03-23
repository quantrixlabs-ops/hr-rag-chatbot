# HR RAG Chatbot

An enterprise-grade HR assistant powered by **Retrieval-Augmented Generation (RAG)**.
Employees ask natural-language questions about company policies, benefits, and procedures
and receive accurate, citation-backed answers sourced from your own HR documents —
with optional live data from BambooHR or SAP SuccessFactors.

---

## Features

- **Hybrid RAG Pipeline** — Dense (Qdrant) + BM25 + cross-encoder reranking + faithfulness verification
- **Streaming Responses** — Token-by-token SSE delivery with source citations
- **Multi-Tenancy** — Tenant isolation at DB, vector store, and cache layers with per-tenant feature flags
- **RBAC (4 Roles)** — employee, manager, hr_admin, super_admin with permissions matrix
- **HRMS Integration** — BambooHR + SAP SuccessFactors adapters for live leave/payroll/org data
- **MFA / TOTP** — Two-factor authentication with QR enrollment and recovery codes
- **GDPR Compliance** — Article 15 data export + Article 17 account erasure
- **Async Ingestion** — Celery workers process PDF, DOCX, TXT, MD documents in background
- **Semantic Cache** — Redis-backed, tenant-scoped query caching with daily cache warming
- **Multi-Model Routing** — Fast/Standard/Advanced tiers with automatic complexity classification
- **Observability** — Prometheus metrics, OpenTelemetry tracing (Jaeger), Grafana dashboards, alerting
- **Kubernetes Ready** — Helm charts with HPA, PDB, health probes, CI/CD via GitHub Actions
- **Fully Local LLM** — Ollama (Llama 3 8B) — no data leaves your network

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 18, TypeScript, Tailwind CSS, Vite |
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy, Alembic |
| **LLM** | Ollama (llama3:8b) |
| **Embeddings** | nomic-embed-text (768-dim) |
| **Vector Store** | Qdrant (primary), FAISS (fallback) |
| **Database** | PostgreSQL 16 (via PgBouncer) |
| **Object Storage** | MinIO (S3-compatible) |
| **Task Queue** | Celery 5 + Redis |
| **Auth** | JWT + bcrypt + TOTP (pyotp) + OIDC SSO |
| **Monitoring** | Prometheus, Grafana, Jaeger, OpenTelemetry |
| **Deployment** | Docker Compose (dev), Helm/K8s (prod) |

---

## Quick Start

### Prerequisites

| Requirement | Version |
|---|---|
| Docker + Compose | v2+ |
| Ollama | latest |

### Run with Docker Compose

```bash
# 1. Clone
git clone <repo-url>
cd hr-rag-chatbot

# 2. Configure
cp .env.example .env
# Edit .env — set JWT_SECRET_KEY for production

# 3. Start all services
docker compose up -d

# 4. Pull LLM models (first time only)
docker compose exec ollama ollama pull llama3:8b
docker compose exec ollama ollama pull nomic-embed-text

# 5. (Optional) Enable monitoring stack
docker compose --profile monitoring up -d
```

**Frontend**: http://localhost:3000 | **API**: http://localhost:8000 | **Swagger**: http://localhost:8000/docs

### Run Locally (without Docker)

```bash
# Python backend
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000

# React frontend
cd frontend && npm install && npm run dev
```

Requires PostgreSQL, Redis, Qdrant, and Ollama running locally (see `.env` for connection settings).

---

## Demo Credentials

| Role | Username | Password |
|---|---|---|
| Admin | admin | Admin@12345!! |
| Manager | manager1 | Manager@12345!! |
| Employee | employee1 | Employee@12345!! |

---

## Project Structure

```
hr-rag-chatbot/
├── backend/
│   ├── app/
│   │   ├── api/                 # Route handlers (auth, chat, docs, admin, gdpr, compliance)
│   │   ├── core/                # Config, security, metrics, tracing, encryption, caching
│   │   ├── database/            # PostgreSQL module, session store
│   │   ├── integrations/        # HRMS adapters (BambooHR, SAP, router)
│   │   ├── models/              # Pydantic schemas
│   │   ├── prompts/             # System prompt templates
│   │   ├── rag/                 # RAG pipeline, reranker, orchestrator
│   │   ├── services/            # Business logic (chat, embedding, ingestion, retrieval)
│   │   ├── vectorstore/         # Qdrant and FAISS adapters
│   │   ├── workers/             # Celery tasks (ingestion, HRMS sync, webhooks)
│   │   └── main.py              # FastAPI entry point
│   ├── alembic/                 # Database migrations (001–005)
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/          # ChatInput, ChatWindow, MessageBubble, Sidebar, NotificationToast
│   │   ├── hooks/               # useChat
│   │   ├── pages/               # ChatPage, LoginPage, AdminDashboard, UploadDocs, UserSettingsPage
│   │   ├── services/            # API client
│   │   ├── types/               # TypeScript interfaces
│   │   └── App.tsx              # Root (auth, routing, toast, branding)
│   ├── Dockerfile
│   └── package.json
├── docs/                        # Documentation
│   ├── ARCHITECTURE.md          # Full system architecture (all 5 phases)
│   ├── UXUI_DESIGN.md           # Frontend component architecture
│   ├── SYSTEM_DOCUMENTATION.md  # Original system reference
│   ├── ROADMAP.md               # Remaining gaps + SaaS evolution
│   └── QA_TEST_REPORT.md        # Adversarial QA test results
├── helm/hr-chatbot/             # Kubernetes Helm chart
├── monitoring/                  # Prometheus, Grafana, Alertmanager configs
├── scripts/                     # Seed data, ingestion, backup
├── tests/                       # pytest test suite
├── .github/workflows/ci.yml     # CI/CD pipeline
├── docker-compose.yml           # 12-service development stack
├── .env.example                 # Environment template
└── pyproject.toml               # Python project config
```

---

## Documentation

| Document | Description |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Unified architecture reference — RAG pipeline, security, multi-tenancy, HRMS, caching, observability, deployment, full API reference |
| [docs/UXUI_DESIGN.md](docs/UXUI_DESIGN.md) | Frontend component map, feature inventory, data flow |
| [docs/SYSTEM_DOCUMENTATION.md](docs/SYSTEM_DOCUMENTATION.md) | Original system documentation — base RAG pipeline details, data models, thresholds |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Remaining gaps, SaaS evolution path, best practices checklist |
| [docs/QA_TEST_REPORT.md](docs/QA_TEST_REPORT.md) | Adversarial QA test report (83 test cases, 10 categories) |

---

## API Overview

| Group | Endpoints |
|---|---|
| **Auth** | `/auth/login`, `/auth/register`, `/auth/refresh`, `/auth/mfa/verify-login` |
| **Chat** | `/chat/query`, `/chat/query/stream`, `/chat/sessions`, `/chat/feedback` |
| **Documents** | `/documents/upload`, `/documents`, `/documents/batch-delete`, `/documents/reindex` |
| **Admin** | `/admin/metrics`, `/admin/users/pending`, `/admin/users/{id}/approve` |
| **GDPR** | `/api/v1/users/{id}/gdpr-export`, `/api/v1/users/{id}/gdpr-erase` |
| **MFA** | `/api/v1/compliance/mfa/enroll`, `/api/v1/compliance/mfa/verify` |
| **Health** | `/health`, `/health/ready`, `/metrics` |

Full interactive docs at `http://localhost:8000/docs` (Swagger UI, development mode only).

---

## License

This project is licensed under the [MIT License](LICENSE).
