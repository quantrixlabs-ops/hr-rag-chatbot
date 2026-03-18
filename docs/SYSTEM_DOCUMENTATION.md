# HR RAG Chatbot — Complete System Documentation

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture](#2-architecture)
3. [Tech Stack](#3-tech-stack)
4. [RAG Pipeline](#4-rag-pipeline)
5. [API Reference](#5-api-reference)
6. [Database Schema](#6-database-schema)
7. [Security Architecture](#7-security-architecture)
8. [Document Ingestion](#8-document-ingestion)
9. [Retrieval Architecture](#9-retrieval-architecture)
10. [Answer Verification](#10-answer-verification)
11. [Frontend Architecture](#11-frontend-architecture)
12. [Observability & Analytics](#12-observability--analytics)
13. [Configuration Reference](#13-configuration-reference)
14. [Data Models](#14-data-models)
15. [Testing](#15-testing)
16. [Deployment](#16-deployment)
17. [Key Thresholds & Parameters](#17-key-thresholds--parameters)

---

## 1. System Overview

An enterprise-grade HR chatbot that answers employee questions using **Retrieval-Augmented Generation (RAG)**. The system retrieves relevant HR policy documents, grounds LLM responses in factual content, and verifies answer faithfulness — reducing hallucination to enterprise-acceptable levels.

### Key Capabilities

- **Grounded Q&A** — Answers backed by retrieved HR documents with source citations
- **Hybrid Retrieval** — FAISS vector search + BM25 keyword matching + cross-encoder reranking
- **Hallucination Detection** — Claim-level verification with faithfulness scoring and confidence badges
- **Multi-Turn Conversations** — Session memory with context-aware follow-up handling
- **Role-Based Access Control** — Employee/Manager/HR Admin with document-level permissions
- **Real-Time Streaming** — Server-Sent Events for token-by-token response delivery
- **Admin Dashboard** — Metrics, failed query tracking, security audit trail, document management
- **Ambiguity Detection** — Identifies vague queries and prompts users for clarification
- **Query Expansion** — LLM-powered query rewriting for improved retrieval coverage
- **Feedback System** — Thumbs up/down on every response for quality tracking

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React)                         │
│  LoginPage │ ChatPage │ AdminDashboard │ Sidebar │ MessageBubble│
│                    ↕ REST + SSE                                 │
├─────────────────────────────────────────────────────────────────┤
│                     FASTAPI BACKEND                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │   Auth   │ │   Chat   │ │Documents │ │     Admin        │   │
│  │ Routes   │ │ Routes   │ │ Routes   │ │     Routes       │   │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────────┬─────────┘   │
│       │            │            │                 │             │
│  ┌────┴────────────┴────────────┴─────────────────┴──────────┐  │
│  │                    MIDDLEWARE STACK                        │  │
│  │  RequestId → Security Headers → Rate Limiting → CORS      │  │
│  └───────────────────────────────────────────────────────────┘  │
│                            │                                    │
│  ┌─────────────────────────┴─────────────────────────────────┐  │
│  │                     RAG PIPELINE                          │  │
│  │                                                           │  │
│  │  Query → Ambiguity Check → Expansion → Retrieval          │  │
│  │    → Context Building → Prompt Assembly → LLM             │  │
│  │    → Verification → Response                              │  │
│  └───────────────────────────────────────────────────────────┘  │
│       │              │              │              │             │
│  ┌────┴────┐   ┌─────┴─────┐  ┌────┴────┐  ┌─────┴──────┐     │
│  │ SQLite  │   │   FAISS   │  │  BM25   │  │  Ollama    │     │
│  │   DB    │   │  Vector   │  │  Index  │  │ (Llama3)   │     │
│  └─────────┘   └───────────┘  └─────────┘  └────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | React 18 + TypeScript + Vite | Single-page application |
| **Styling** | Tailwind CSS | Utility-first CSS |
| **Icons** | Lucide React | UI icons |
| **Backend** | FastAPI (Python) | Async REST API + SSE |
| **LLM** | Llama3:8b via Ollama | Answer generation |
| **Embeddings** | nomic-embed-text via Ollama | Document/query embedding (768-dim) |
| **Vector Store** | FAISS (IndexFlatIP) | Dense vector search |
| **Keyword Search** | rank-bm25 (BM25Okapi) | Sparse keyword retrieval |
| **Reranker** | cross-encoder/ms-marco-MiniLM-L-6-v2 | Cross-encoder reranking |
| **Database** | SQLite | Sessions, users, documents, logs |
| **Auth** | JWT (python-jose) + bcrypt | Token-based authentication |
| **Logging** | structlog (JSON) | Structured logging with request trace IDs |
| **Metrics** | prometheus_client | Prometheus-format metrics |
| **Containerization** | Docker + docker-compose | Multi-service deployment |

---

## 4. RAG Pipeline

The complete pipeline from user query to verified response:

### Stage 0 — Ambiguity Detection
- **QueryAnalyzer** classifies the query (factual/procedural/comparative/policy_lookup)
- Detects vague queries: short (≤5 words) + broad topic + no specific question words
- Returns clarification prompt with topic-specific options (e.g., "Are you asking about annual leave, sick leave, or parental leave?")
- Clarification topics: leave, benefits, policy, compensation, performance, termination

### Stage 1 — Query Expansion & Retrieval
- **Context Injection**: For follow-up queries with pronouns (it/that/this), injects previous user query topic (max 100 chars)
- **Query Expansion**: For simple queries (≤12 words), LLM rewrites for better retrieval coverage
- **Hybrid Retrieval**:
  - Dense retrieval via FAISS (top 20)
  - BM25 keyword retrieval (top 20)
  - Reciprocal Rank Fusion (k=60, dense weight 0.6, BM25 weight 0.4)
  - Cross-encoder reranking → top 8 results

### Stage 2 — Context Building
- Token budget: 3,000 tokens
- Minimum relevance score: 0.20 (filters noise)
- Deduplication by first 150 characters
- Output format: `[Document N | Source: filename, Page X | Relevance: Y%]`

### Stage 3 — Prompt Assembly
- System prompt with 9 strict rules (cite sources, refuse unsupported answers, no fabrication, etc.)
- Conversation history: last 3 turns (user: 200 chars, assistant: 300 chars)
- Temperature: 0.1 (near-deterministic)
- Max response tokens: 1,024

### Stage 4 — Answer Verification
- Claim extraction: sentence-level splitting (min 15 chars)
- Evidence matching: 2+ shared 4-character words between claim and chunk
- Faithfulness scoring: fraction of claims with evidence
- Verdict: grounded (≥0.6), partially_grounded (0.35-0.6), ungrounded (<0.35)
- Ungrounded answers get disclaimer prepended
- Citations: extracted from `[Source: ...]` patterns or auto-generated from top 3 chunks

### Stage 5 — Logging
- Query hash (SHA-256, 16 chars) stored — never raw text
- Sources used stored as JSON array
- Metrics: latency_ms, faithfulness_score, hallucination_risk, top_chunk_score

---

## 5. API Reference

### Authentication

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/auth/register` | None | Create account (name, email, phone, role, username, password) |
| `POST` | `/auth/login` | None | Authenticate → access_token + refresh_token |
| `POST` | `/auth/logout` | Bearer | Revoke access token + all refresh tokens |
| `POST` | `/auth/refresh` | None | Exchange refresh token for new token pair (rotation) |

### Chat

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/chat/query` | Bearer | Send query → answer with citations + confidence |
| `POST` | `/chat/query/stream` | Bearer | SSE streaming version with token-by-token delivery |
| `GET` | `/chat/sessions` | Bearer | List user's conversation sessions |
| `GET` | `/chat/sessions/{id}/history` | Bearer | Get conversation turns (max 100) |
| `POST` | `/chat/feedback` | Bearer | Record thumbs up/down on a response |

### Documents

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/documents/upload` | hr_admin | Upload + index HR document (PDF/DOCX/MD/TXT) |
| `GET` | `/documents` | Bearer | List accessible documents (role-filtered) |
| `DELETE` | `/documents/{id}` | hr_admin | Delete document + chunks from index |
| `POST` | `/documents/batch-delete` | hr_admin | Delete up to 50 documents at once |
| `POST` | `/documents/reindex` | hr_admin | Reindex one or all documents from source files |

### Admin

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/admin/metrics` | hr_admin | Dashboard KPIs (12 metrics + top docs + query types) |
| `GET` | `/admin/failed-queries` | hr_admin | Queries with faithfulness < 0.7 (hash only, no raw text) |
| `GET` | `/admin/security-events` | hr_admin | Security audit trail (100 most recent) |
| `PATCH` | `/admin/users/{id}/role` | hr_admin | Change user role (cannot self-demote) |
| `POST` | `/admin/cleanup-vector-store` | hr_admin | Remove test/QA documents from index |

### Health & Metrics

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | None | Public health check (status only) |
| `GET` | `/health/detailed` | hr_admin | Full system diagnostics |
| `GET` | `/metrics` | hr_admin | Prometheus-format metrics |

---

## 6. Database Schema

### Tables

**users**
| Column | Type | Description |
|--------|------|-------------|
| user_id | TEXT PK | UUID |
| username | TEXT UNIQUE | Login name |
| hashed_password | TEXT | bcrypt hash |
| role | TEXT | employee / manager / hr_admin |
| department | TEXT | Optional department |
| created_at | REAL | Unix timestamp |
| full_name | TEXT | Display name |
| email | TEXT | Email address |
| phone | TEXT | Phone number |

**sessions**
| Column | Type | Description |
|--------|------|-------------|
| session_id | TEXT PK | UUID |
| user_id | TEXT | Owner |
| user_role | TEXT | Role at creation |
| created_at | REAL | Unix timestamp |
| last_active | REAL | Last activity |
| metadata | TEXT | JSON metadata |

**turns**
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| session_id | TEXT FK | Parent session |
| role | TEXT | "user" or "assistant" |
| content | TEXT | Message content |
| timestamp | REAL | Unix timestamp |
| metadata | TEXT | JSON metadata |

**documents**
| Column | Type | Description |
|--------|------|-------------|
| document_id | TEXT PK | UUID |
| title | TEXT | Document title |
| category | TEXT | policy/handbook/benefits/leave/onboarding/legal |
| access_roles | TEXT | JSON array of allowed roles |
| effective_date | TEXT | Policy effective date |
| version | TEXT | Version string (e.g., "1.0", "2.0") |
| source_filename | TEXT | Original filename |
| uploaded_by | TEXT | Uploader user_id |
| uploaded_at | REAL | Unix timestamp |
| page_count | INTEGER | Total pages |
| chunk_count | INTEGER | Indexed chunks |
| content_hash | TEXT | SHA-256 hash for deduplication |

**query_logs**
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| query | TEXT | SHA-256 hash (16 chars), never raw text |
| query_type | TEXT | factual/procedural/comparative/policy_lookup |
| user_role | TEXT | Querying user's role |
| faithfulness_score | REAL | 0.0 - 1.0 |
| hallucination_risk | REAL | 0.0 - 1.0 |
| latency_ms | REAL | Full pipeline latency |
| top_chunk_score | REAL | Best retrieval score |
| sources_used | TEXT | JSON array of source document names |
| timestamp | REAL | Unix timestamp |

**feedback**
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| session_id | TEXT | Session context |
| query | TEXT | Query hash |
| answer | TEXT | Answer text |
| rating | TEXT | "positive" or "negative" |
| timestamp | REAL | Unix timestamp |
| user_id | TEXT | Who gave feedback |

**security_events**
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| event_type | TEXT | login_failed, account_lockout, role_change, etc. |
| user_id | TEXT | Related user |
| ip_address | TEXT | Client IP |
| details | TEXT | JSON details |
| timestamp | REAL | Unix timestamp |

**refresh_tokens**
| Column | Type | Description |
|--------|------|-------------|
| token | TEXT PK | Opaque UUID token |
| user_id | TEXT | Owner |
| expires_at | REAL | Expiry timestamp |
| revoked | INTEGER | 0 = active, 1 = revoked |
| created_at | REAL | Creation timestamp |

---

## 7. Security Architecture

### Authentication Flow

```
Register → Login → Access Token (1h) + Refresh Token (7d)
    │
    ├── Every request: validate JWT → check revocation → load role from DB
    │
    ├── Token refresh: POST /auth/refresh → rotate both tokens
    │
    └── Logout: revoke access token (jti blocklist) + all refresh tokens (DB)
```

### JWT Structure
- **Algorithm**: HS256
- **Claims**: sub (user_id), role, department, exp, iat, jti (unique ID), iss, aud
- **Issuer**: `hr-rag-chatbot`
- **Audience**: `hr-rag-chatbot-api`
- **Key security**: Role loaded from database on every request — JWT role claim ignored

### Role-Based Access Control

| Role | Access Level |
|------|-------------|
| employee | Own sessions, employee-level documents |
| manager | Employee access + manager-level documents |
| hr_admin | Full access + admin APIs + document management |

### Rate Limiting

| Endpoint | Limit | Window |
|----------|-------|--------|
| Login | 5 attempts | 60 seconds per IP |
| Account lockout | 10 failures | 15-minute lockout |
| Registration | 3 attempts | 1 hour per IP |
| Chat queries | 10 queries | 60 seconds per user |
| Document upload | 5 uploads | 60 seconds per user |
| Global API | 60 requests | 60 seconds per IP |

### Input Protection
- **Prompt injection**: 19 regex patterns (jailbreak, DAN mode, system prompt extraction, etc.)
- **Query sanitization**: Strip HTML tags, null bytes, control characters, collapse whitespace
- **Prompt leakage filter**: Detects if LLM output contains ≥2 system prompt patterns → redacts
- **PII masking**: Emails, SSNs, phone numbers, credit cards redacted before logging
- **File upload**: Extension whitelist, 50MB limit, path traversal prevention, SHA-256 dedup

### Security Headers
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- X-XSS-Protection: 1; mode=block
- Content-Security-Policy: default-src 'self'; script-src 'self'; frame-ancestors 'none'
- Referrer-Policy: strict-origin-when-cross-origin
- Strict-Transport-Security: max-age=31536000 (production)
- Server: hr-chatbot (hides uvicorn identity)

### Password Policy
- Minimum 12 characters
- Must contain: letter + number + special character
- Hashed with bcrypt + random salt

---

## 8. Document Ingestion

### Supported Formats
- PDF (.pdf) — per-page text extraction with page numbers preserved
- Word (.docx) — paragraph extraction
- Markdown (.md) — direct text
- Plain text (.txt) — direct text

### Ingestion Pipeline

```
Upload → Validate → Save → Extract Text → Clean → Chunk → Embed → Index → Register
```

1. **Validate**: extension, size (≤50MB), empty check, path traversal, test-doc rejection
2. **Duplicate Detection**: SHA-256 content hash + filename check; supports version upgrades
3. **Text Extraction**: Per-page PDF extraction preserving page numbers
4. **Cleaning**: Unicode normalization, control char removal, whitespace collapse
5. **Chunking**: 400 words, 60-word overlap, heading-aware splitting, page metadata
6. **Embedding**: Batch processing (32 texts/batch) via nomic-embed-text
7. **Indexing**: Add to FAISS + rebuild BM25 index
8. **Registration**: Store metadata in SQLite with content_hash
9. **Persistence**: Atomic FAISS save to disk

### Guardrails
- Max chunks per document: 500
- Min chunks per document: 5
- Test document rejection: regex patterns for test/QA/dummy/sample/fake files
- Version-aware uploads: higher version number replaces previous version

---

## 9. Retrieval Architecture

### Pipeline

```
Query → Dense Retrieval (top 20) ──┐
                                    ├── RRF Fusion → Cross-Encoder Reranking → Top 8
Query → BM25 Retrieval (top 20) ───┘
```

### Dense Retrieval (FAISS)
- Model: nomic-embed-text (768 dimensions)
- Index: FAISS IndexFlatIP (inner product with L2-normalized vectors)
- Role filtering applied post-retrieval

### BM25 Keyword Retrieval
- Algorithm: BM25Okapi (rank-bm25)
- Tokenization: Regex word extraction
- Role filtering applied

### Reciprocal Rank Fusion
- Constant k = 60
- Dense weight: 0.6, BM25 weight: 0.4
- Formula: `score[chunk] += weight / (k + rank)`

### Cross-Encoder Reranking
- Model: cross-encoder/ms-marco-MiniLM-L-6-v2
- Score normalization: Sigmoid (converts logits to 0-1 probability)
- Output: Top 8 reranked results with calibrated scores

---

## 10. Answer Verification

### Faithfulness Scoring
1. Extract claims from answer (sentence-level, min 15 chars)
2. For each claim, search chunks for evidence (2+ shared 4-character words)
3. Faithfulness = verified claims / total claims

### Confidence Score
- `min(1.0, avg_chunk_score × citation_ratio)`
- Floor: 0.5 if chunks score > 0.4 AND faithfulness > 0.3

### Verdicts
| Verdict | Score Range | Action |
|---------|------------|--------|
| grounded | ≥ 0.6 | No disclaimer |
| partially_grounded | 0.35 — 0.6 | Prepend "Note: Parts may not be fully supported..." |
| ungrounded | < 0.35 | Prepend "I was unable to find sufficient evidence..." |

### Citations
- Extracted from `[Source: document, Page X]` patterns in LLM output
- Auto-generated from top 3 chunks if LLM doesn't cite
- Each citation includes: source name, page number, text excerpt (200 chars)

---

## 11. Frontend Architecture

### Pages

| Page | Purpose |
|------|---------|
| **LoginPage** | Separate login/register forms with show/hide password, role selection, confirm password |
| **ChatPage** | Conversation interface with streaming, citations, confidence badges, feedback buttons |
| **AdminDashboard** | 8 metric cards, top documents chart, tabbed views (Documents / Failed Queries / Security Events), upload/delete/reindex |

### Components

| Component | Purpose |
|-----------|---------|
| **Sidebar** | Session list, navigation, user info, logout |
| **ChatWindow** | Message list, typing indicator, streaming display |
| **MessageBubble** | Individual message with citations, confidence badge, latency, thumbs up/down |
| **ChatInput** | Query input with send button |

### Key Features
- **Proactive token refresh**: Schedules refresh 5 minutes before access token expiry
- **Reactive 401 handling**: Attempts refresh before logging out
- **SSE streaming**: Token-by-token display with cursor animation, citations in final event
- **Bulk operations**: Multi-select checkboxes for batch document deletion
- **Per-document reindex**: Individual or full reindex from admin dashboard

---

## 12. Observability & Analytics

### Structured Logging
- Library: structlog with JSON rendering
- Every log entry includes: `request_id`, `timestamp` (ISO), `level`
- Request trace IDs via `RequestIdMiddleware` (propagated via `X-Request-ID` header)
- Security events logged to both structlog AND `security_events` table

### Admin Metrics Dashboard (`GET /admin/metrics`)

| Metric | Description |
|--------|-------------|
| queries_today | Query count in last 24 hours |
| queries_this_week | Query count in last 7 days |
| avg_latency_ms | Average pipeline latency |
| avg_faithfulness | Average confidence score |
| hallucination_rate | Average hallucination risk |
| active_sessions | Sessions active in last 24h |
| total_documents | Indexed document count |
| total_chunks | Total chunks in vector store |
| query_success_rate | Grounded queries / total |
| failed_queries | Low-confidence query count |
| negative_feedback_count | Negative ratings this week |
| top_documents | Top 10 most-accessed documents |
| query_type_distribution | Breakdown by query type |

### Failed Query Tracking
- Threshold: faithfulness_score < 0.7 or negative feedback
- Returns: query_hash, query_type, faithfulness, hallucination_risk, failure_reason, latency, timestamp
- Never returns raw query text

### Security Audit Trail
- Events: login_failed, account_lockout, role_change, vector_store_cleanup, registration_rate_limited
- Each event: type, user_id, IP, details (JSON), timestamp
- Indexed by timestamp for fast retrieval

---

## 13. Configuration Reference

All settings configurable via environment variables or `.env` file:

| Setting | Default | Description |
|---------|---------|-------------|
| `APP_NAME` | hr-rag-chatbot | Application name |
| `ENVIRONMENT` | development | development / production |
| `API_PORT` | 8000 | Backend server port |
| `JWT_SECRET_KEY` | change-me-... | JWT signing secret |
| `JWT_ALGORITHM` | HS256 | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 60 | Access token lifetime |
| `LLM_PROVIDER` | ollama | ollama / vllm |
| `LLM_MODEL` | llama3:8b | LLM model name |
| `OLLAMA_BASE_URL` | http://localhost:11434 | Ollama server |
| `EMBEDDING_MODEL` | nomic-embed-text | Embedding model |
| `EMBEDDING_PROVIDER` | ollama | ollama / sentence-transformers |
| `EMBEDDING_DIMENSION` | 768 | Vector dimensions |
| `VECTOR_STORE_BACKEND` | faiss | faiss / qdrant |
| `FAISS_INDEX_DIR` | ./data/faiss_index | FAISS index directory |
| `DB_PATH` | ./data/hr_chatbot.db | SQLite database path |
| `DENSE_TOP_K` | 20 | Dense retrieval results |
| `BM25_TOP_K` | 20 | BM25 retrieval results |
| `RERANK_TOP_N` | 8 | Reranked final results |
| `DENSE_WEIGHT` | 0.6 | RRF dense weight |
| `BM25_WEIGHT` | 0.4 | RRF BM25 weight |
| `MAX_CONTEXT_TOKENS` | 3000 | Context token budget |
| `LLM_TEMPERATURE` | 0.1 | LLM temperature |
| `MAX_RESPONSE_TOKENS` | 1024 | Max LLM output tokens |
| `MIN_FAITHFULNESS_SCORE` | 0.7 | Grounding threshold |
| `SESSION_CONTEXT_TURNS` | 5 | History turns stored |
| `COMPANY_NAME` | Acme Corp | Company name in prompts |
| `HR_CONTACT_EMAIL` | your HR department | HR fallback contact |
| `UPLOAD_DIR` | ./data/uploads | Document storage |

---

## 14. Data Models

### Request/Response Models (Pydantic)

**ChatQueryRequest**: query, session_id?, include_sources, include_trace

**ChatQueryResponse**: answer, session_id, citations[], confidence, faithfulness_score, query_type, latency_ms, flagged

**RegisterRequest**: username, password, full_name, email, phone, role, department?

**FeedbackRequest**: session_id, query, answer, rating (positive/negative)

### Internal Models (Dataclass)

**ChunkMetadata**: chunk_id, document_id, text, page, section_heading, chunk_index, access_roles[], category, token_count, source

**SearchResult**: chunk_id, text, score, source, page, metadata{}

**VerificationResult**: faithfulness_score, hallucination_risk, verified_claims[], citations[], verdict

**ChatResult**: answer, session_id, citations[], confidence, faithfulness_score, query_type, latency_ms, flagged, chunks[], verification

**QueryAnalysis**: original_query, query_type, complexity, detected_topics[], sub_queries[], requires_session_context, is_ambiguous, clarification_prompt

---

## 15. Testing

### Test Suite: 81 tests

**test_api.py** (~58 tests):
- Auth: register, login, logout, refresh tokens, token revocation, role assignment
- Security: rate limiting, account lockout, injection detection, PII masking, XSS prevention
- Chat: query validation, session ownership, feedback
- Documents: upload validation, batch delete
- Admin: metrics, failed queries (hash not raw), security events
- Headers: CSP, X-Frame-Options, server identity

**test_rag_pipeline.py** (~17 tests):
- Query analyzer: factual, comparative, procedural, decomposition
- Context builder: basic, dedup, token budget, empty
- Prompt building: with/without history
- Context injection: pronoun detection, no-pronoun skip
- Ambiguity detection: vague leave, specific not ambiguous, vague benefits

**test_retrieval.py** (~6 tests):
- FAISS: add, search, RBAC filtering, persistence
- BM25: index, search
- RRF: fusion correctness

---

## 16. Deployment

### Docker Compose (3 services)

```yaml
services:
  api:        # Python 3.11 + FastAPI + uvicorn (port 8000)
  frontend:   # Node 20 + nginx (port 3000)
  ollama:     # Ollama LLM server (port 11434, 4 CPUs, 16GB RAM)
```

### Quick Start

```bash
# 1. Clone
git clone https://github.com/quantrixlabs-ops/hr-rag-chatbot.git
cd hr-rag-chatbot

# 2. Copy environment
cp .env.example .env
# Edit .env with your JWT_SECRET_KEY

# 3. Install backend
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

# 4. Install frontend
cd frontend && npm install && cd ..

# 5. Start Ollama + pull models
ollama serve &
ollama pull llama3:8b
ollama pull nomic-embed-text

# 6. Ingest documents
python scripts/ingest_documents.py

# 7. Start backend
uvicorn backend.app.main:app --reload --port 8000

# 8. Start frontend (new terminal)
cd frontend && npm run dev
```

### Production Notes
- Set `ENVIRONMENT=production` to disable Swagger UI and enable HSTS
- Change `JWT_SECRET_KEY` to a 256-bit random secret
- Use `--workers 2` for uvicorn in production
- Token revocation is in-memory — use Redis for multi-worker deployments
- FAISS index saved atomically to prevent corruption on crash

---

## 17. Key Thresholds & Parameters

| Parameter | Value | Location |
|-----------|-------|----------|
| Chunk size | 400 words | ingestion_service.py |
| Chunk overlap | 60 words | ingestion_service.py |
| Max chunks/document | 500 | ingestion_service.py |
| Max file size | 50 MB | document_routes.py |
| Max query length | 1,000 chars | chat_routes.py |
| Context token budget | 3,000 | config.py |
| Min relevance score | 0.20 | context_builder.py |
| Dense top-k | 20 | config.py |
| BM25 top-k | 20 | config.py |
| Rerank top-n | 8 | config.py |
| RRF dense weight | 0.6 | config.py |
| RRF BM25 weight | 0.4 | config.py |
| Access token expiry | 60 minutes | config.py |
| Refresh token expiry | 7 days | security.py |
| Login rate limit | 5/minute per IP | auth_routes.py |
| Account lockout | 10 failures → 15 min | auth_routes.py |
| Registration rate limit | 3/hour per IP | auth_routes.py |
| Chat rate limit | 10/minute per user | chat_routes.py |
| Upload rate limit | 5/minute per user | document_routes.py |
| Global API rate limit | 60/minute per IP | main.py |
| LLM temperature | 0.1 | config.py |
| LLM max tokens | 1,024 | config.py |
| Embedding dimension | 768 | config.py |
| Grounded threshold | ≥ 0.6 | verification_service.py |
| Partial threshold | 0.35 — 0.6 | verification_service.py |
| Ungrounded threshold | < 0.35 | verification_service.py |
| Injection patterns | 19 | security.py |
| Prompt leak patterns | 14 | system_prompt.py |
| Password min length | 12 chars | auth_routes.py |
| Cross-encoder model | ms-marco-MiniLM-L-6-v2 | retrieval_service.py |
| Embedding model | nomic-embed-text | config.py |
| LLM model | llama3:8b | config.py |
