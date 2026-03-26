# Enterprise HR RAG Chatbot — Complete Technical Documentation

**Version:** 2.0.0
**Date:** 2026-03-26
**Classification:** Technical — Engineering & Architecture
**Audience:** Senior Engineers, Architects, DevOps, Security Auditors

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Detailed Component Design](#3-detailed-component-design)
4. [Features & Functionalities](#4-features--functionalities)
5. [Conversation Engine](#5-conversation-engine)
6. [Algorithms & Logic](#6-algorithms--logic)
7. [Data Management](#7-data-management)
8. [Integrations](#8-integrations)
9. [Performance & Scalability](#9-performance--scalability)
10. [Security & Privacy](#10-security--privacy)
11. [Deployment Architecture](#11-deployment-architecture)
12. [Limitations & Trade-offs](#12-limitations--trade-offs)
13. [Future Improvements](#13-future-improvements)

---

## 1. System Overview

### 1.1 Purpose & Goals

The HR RAG Chatbot is an enterprise-grade, AI-powered HR assistant that answers employee questions using **Retrieval-Augmented Generation (RAG)** grounded in the organization's actual HR policy documents. Every answer is verifiable, cited, and confidence-scored.

**Core Design Principles:**
- **Zero cloud LLM cost** — All inference runs locally via Ollama (llama3:8b + nomic-embed-text)
- **Full data sovereignty** — No data leaves the organization's network
- **Document-grounded answers** — Every response is traced to source documents with page numbers
- **Anti-hallucination by design** — Multi-stage verification pipeline ensures factual accuracy
- **Multi-tenant ready** — `tenant_id` on every table from Day 1 (Phase 3 SaaS activation)
- **Additive architecture** — Each phase builds on the previous without breaking changes

### 1.2 Key Capabilities

| Capability | Description |
|-----------|-------------|
| **RAG Chat** | Natural language Q&A grounded in HR documents with citations |
| **Hybrid Retrieval** | Dense (FAISS/Qdrant) + BM25 keyword search + cross-encoder reranking |
| **Multi-Role RBAC** | 6-level role hierarchy controlling document and feature access |
| **Document Management** | Upload, version, auto-classify, chunk, embed, and index HR documents |
| **Streaming Responses** | Server-Sent Events (SSE) for token-by-token response delivery |
| **Answer Verification** | Faithfulness scoring, citation extraction, hallucination detection |
| **Content Safety** | Profanity filtering, bias detection, PII redaction, prompt injection blocking |
| **Ticket System** | HR support tickets with assignment, comments, escalation, and resolution workflow |
| **Anonymous Complaints** | Confidential complaint filing with HR review workflow |
| **FAQ Fast-Path** | Curated Q&A bypasses RAG for instant, high-confidence answers |
| **Semantic Cache** | Redis-backed similarity cache reduces redundant LLM calls by 30-40% |
| **Multi-LLM Routing** | Query complexity-based model selection + external provider fallback |
| **GDPR Compliance** | Data export, right-to-erasure, configurable retention policies |
| **MFA** | TOTP-based multi-factor authentication for admin accounts |
| **OpenTelemetry** | Distributed tracing across the entire query pipeline |
| **Notification System** | In-app notifications for approvals, tickets, document uploads |

### 1.3 Target Users

| Role | Access Level | Primary Use |
|------|-------------|-------------|
| **Employee** | Chat, own tickets, profile settings | Ask HR questions, file tickets |
| **Manager** | Employee access + team views | Team query summaries, escalations |
| **HR Team** | Upload docs (pending approval), manage tickets | Document management, ticket handling |
| **HR Head** | Approve documents, review complaints, manage HR contacts | Governance and oversight |
| **HR Admin** | Full document + user + analytics access | System administration |
| **Super Admin** | Everything + tenant management, AI config | Platform administration |

---

## 2. High-Level Architecture

### 2.1 System Components

```
                                    HR RAG CHATBOT ARCHITECTURE

    +-----------------------------------------------------------------------------------+
    |                              FRONTEND (React 18 + TypeScript)                      |
    |  +----------+ +----------+ +----------+ +----------+ +----------+ +-----------+   |
    |  | LoginPage| | ChatPage | |AdminDash | |UploadDocs| | Tickets  | | Settings  |   |
    |  +----------+ +----------+ +----------+ +----------+ +----------+ +-----------+   |
    |  | Sidebar  | |ChatWindow| |MessageBub| |DocViewer | |Complaints| |BranchMgmt |   |
    |  +----------+ +----------+ +----------+ +----------+ +----------+ +-----------+   |
    |                         Vite 5.1 | Tailwind CSS 3.4                               |
    +-------------------------------------|---------------------------------------------+
                                          | HTTP/SSE (port 3000 → proxy → 8000)
    +-------------------------------------|---------------------------------------------+
    |                              BACKEND (FastAPI + Python 3.11)                       |
    |                                                                                   |
    |  +--MIDDLEWARE STACK-------------------------------------------------------+      |
    |  | RequestId → SecurityHeaders → AdminIPAllowlist → GlobalRateLimit → Tenant|      |
    |  +------------------------------------------------------------------------+      |
    |                                                                                   |
    |  +--API LAYER (18 route modules)----------------------------------------------+   |
    |  | /auth  /chat  /documents  /admin  /tickets  /complaints  /notifications    |   |
    |  | /tenants  /users  /branches  /hr-contacts  /faq  /cfls  /ai-config        |   |
    |  | /gdpr  /compliance  /integrations                                          |   |
    |  +------------------------------------------------------------------------+   |
    |                                                                                   |
    |  +--SERVICE LAYER------------------------------------------------------------+   |
    |  | ChatService → RAGPipeline → RetrievalOrchestrator → ContextBuilder        |   |
    |  | IngestionPipeline → EmbeddingService → FAQService → VerificationService   |   |
    |  | AIRouter → ModelGateway → ReasoningEngine → QueryAnalyzer                 |   |
    |  | ContentSafety → SemanticCache → CorrectionService                         |   |
    |  +------------------------------------------------------------------------+   |
    |                                                                                   |
    |  +--DATA LAYER--------------------------------------------------------------+   |
    |  | SQLite (dev) / PostgreSQL (prod) | FAISS / Qdrant | Redis | MinIO        |   |
    |  +------------------------------------------------------------------------+   |
    +-----------------------------------------------------------------------------------+
                                          |
    +-------------------------------------|---------------------------------------------+
    |                              INFRASTRUCTURE                                       |
    |  +--------+ +--------+ +--------+ +--------+ +--------+ +--------+               |
    |  | Ollama | | Qdrant | |Postgres| | Redis  | | MinIO  | |PgBounc |               |
    |  |llama3:8b| |v1.9.0 | |  16    | |   7    | |        | |  1.22  |               |
    |  |nomic-  | |        | |        | |        | |        | |        |               |
    |  |embed   | |        | |        | |        | |        | |        |               |
    |  +--------+ +--------+ +--------+ +--------+ +--------+ +--------+               |
    +-----------------------------------------------------------------------------------+
```

### 2.2 Data Flow — Chat Query

```
User types question in ChatWindow
         |
         v
    [ChatInput] ──POST──> /chat/query/stream (SSE)
         |
         v
    [ChatService.handle_query]
         |
    +----|----+
    |         |
    v         v
 Sanitize   Session
 + Inject   Mgmt
 Check      (get/create)
    |         |
    +----+----+
         |
         v
    Semantic Cache ──hit──> Return cached response
         |miss
         v
    [RAGPipeline.query]
         |
    +----+----+----+----+
    |    |    |    |    |
    v    v    v    v    v
  Query  FAQ  CFLS Lang  Domain
  Analyze Match Corr Det  Route
    |    |    |    |    |
    +-+--+----+----+----+
      |
      v  (if standard HR query)
    [RetrievalOrchestrator.retrieve]
      |
      +-----+-----+
      |           |
      v           v
    Dense       BM25
    (FAISS/     (keyword)
    Qdrant)
      |           |
      +-----+-----+
            |
            v
    Reciprocal Rank Fusion (k=60, dense=0.6, bm25=0.4)
            |
            v
    Cross-Encoder Reranking (ms-marco-MiniLM-L-6-v2)
            |
            v
    [ContextBuilder.build] (token budget: 3000)
            |
            v
    [ReasoningEngine] (optional: complex/sensitive queries)
            |
            v
    [ModelGateway.generate] (Ollama llama3:8b)
            |
            v
    +-------+-------+-------+-------+
    |       |       |       |       |
    v       v       v       v       v
  Verify  Content  PII    Guard   Suggest
  Ground  Safety   Scrub  Rails   Follow-up
    |       |       |       |       |
    +---+---+---+---+---+---+---+---+
        |
        v
    [ChatResult] → SSE tokens → ChatWindow → MessageBubble
        |
        v
    Persist turns + Audit log + Cache result
```

### 2.3 Data Flow — Document Ingestion

```
HR Admin uploads PDF via UploadDocs page
         |
         v
    POST /documents/upload (multipart/form-data)
         |
         v
    Validation (ext, size, filename sanitization, path traversal check)
         |
         v
    Duplicate Detection (content_hash or source_filename match)
         |yes
         v
    Remove old chunks from FAISS/Qdrant + BM25 + DB
         |
         v
    Auto-Classify Category (leave, benefits, handbook, etc.)
         |
         v
    [IngestionPipeline.ingest]
         |
    +----+----+----+----+----+----+----+----+
    |    |    |    |    |    |    |    |    |
    v    v    v    v    v    v    v    v    v
   Save  Load  Clean Chunk  Embed Index BM25 Register Persist
   File  PDF   Text  (head  (nomic (FAISS/ Update  (SQLite) FAISS
         plumb       +fix)  -embed Qdrant)              to disk
         er                 text)
    |    |    |    |    |    |    |    |    |
    +----+----+----+----+----+----+----+----+
         |
         v
    Approval Workflow (HR Head auto-approve; HR Team → pending)
         |
         v
    Invalidate Semantic Cache for affected queries
         |
         v
    Notify HR Head (if pending approval)
```

---

## 3. Detailed Component Design

### 3.1 Backend — FastAPI Application

**Entry Point:** `backend/app/main.py`

**Startup Sequence:**
1. Set OpenMP environment variables (prevent duplicate libomp crash on macOS)
2. Configure structured logging (structlog)
3. Initialize OpenTelemetry distributed tracing
4. Create data directories (FAISS index, uploads, DB)
5. Validate Ollama connectivity and model availability
6. Initialize SQLite database (30+ tables)
7. Wire all services via `_wire_services()`:
   - EmbeddingService → warmup model
   - Vector Store (Qdrant primary, FAISS fallback) → load index
   - BM25 Retriever → build keyword index from metadata
   - Dense Retriever → wire embedding + vector store
   - Reranker → warmup cross-encoder model
   - RetrievalOrchestrator → combine dense + BM25 + reranker
   - ModelGateway → configure Ollama/vLLM endpoint
   - AIRouter → wrap with external provider fallback
   - ContextBuilder → set token budget (3000)
   - AnswerVerifier → grounding checks
   - SessionStore → SQLite connection
   - IngestionPipeline → wire embedding + vector store + BM25
   - RAGPipeline → assemble full pipeline
   - ChatService → wire session store + RAG pipeline
8. Register all 18 API route modules
9. Apply middleware stack (5 layers)
10. Start uvicorn server on port 8000

**Middleware Stack (execution order):**

| Order | Middleware | Purpose |
|-------|-----------|---------|
| 1 | `RequestIdMiddleware` | Generates unique X-Request-ID for every request |
| 2 | `SecurityHeadersMiddleware` | Adds X-Frame-Options, CSP, HSTS, X-Content-Type-Options |
| 3 | `AdminIPAllowlistMiddleware` | Restricts /admin routes to configured IPs |
| 4 | `GlobalRateLimitMiddleware` | 600 requests/min per IP (sliding window) |
| 5 | `TenantMiddleware` | Resolves tenant from JWT → X-Tenant-Slug header → default |

**Health Endpoints:**

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /health` | Public | Quick status (vector store + database) |
| `GET /health/detailed` | Admin | Deep diagnostics (all services) |
| `GET /health/ready` | Public | Kubernetes readiness probe (503 if not ready) |
| `GET /metrics` | Admin | Prometheus metrics export |

### 3.2 Frontend — React SPA

**Technology:** React 18.3.1 + TypeScript 5.4.2 + Vite 5.1.4 + Tailwind CSS 3.4.1

**Architecture:** Single-page application with custom page state machine (no React Router).

**Page Navigation:**
```typescript
const [page, setPage] = useState<string>('chat')
// Controlled by Sidebar onNavigate callback
// Role-based default home:
//   admin/hr_admin/super_admin → 'admin' (Analytics)
//   hr_team/hr_head → 'hr-dashboard'
//   employee → 'home' (EmployeeDashboard)
```

**Component Hierarchy:**
```
App
├── LoginPage (unauthenticated)
└── (authenticated)
    ├── Sidebar (navigation + session list)
    ├── NotificationBell (header)
    └── Page Content (conditional)
        ├── EmployeeDashboard (home)
        ├── HRDashboard (hr-dashboard)
        ├── ChatPage
        │   └── ChatWindow
        │       ├── MessageBubble[]
        │       ├── ChatInput
        │       └── DocumentViewer (modal)
        ├── AdminDashboard (admin)
        ├── UploadDocs (upload)
        ├── TicketsPage (tickets)
        ├── ComplaintsPage (complaints)
        ├── ContactHR (contact-hr)
        ├── BranchManagement (branches)
        └── UserSettingsPage (settings)
```

**State Management:** React hooks only (useState, useCallback, useEffect, useRef, useContext). No external state library. Toast notifications via React Context API.

**Auth Flow:**
- JWT stored in localStorage with proactive refresh (5 min before expiry)
- 30-minute inactivity timeout (mouse/keyboard/scroll tracking)
- 401 responses trigger token refresh → logout fallback
- Session list auto-refreshes every 10 seconds

**Chat Streaming:**
```typescript
// useChat hook: SSE streaming with non-streaming fallback
async function send(query: string) {
    try {
        await sendMessageStream(token, query, sessionId, onToken, onDone, onError)
    } catch {
        const response = await sendMessage(token, query, sessionId)  // fallback
    }
}
```

### 3.3 Vector Store — FAISS + Qdrant

**Primary: Qdrant** (self-hosted, Docker)
- Collection: `hr_chunks` (shared across tenants)
- Tenant isolation via `tenant_id` payload filter on every search
- RBAC via `access_roles` payload filter
- Supports incremental add/delete per document

**Fallback: FAISS** (in-process, no Docker dependency)
- `IndexFlatIP` (inner product with L2-normalized vectors = cosine similarity)
- Pickle metadata sidecar for chunk information
- Atomic save (write-to-temp + rename) prevents corruption
- Automatic dimension validation on add()
- Corrupt-file handling on load() (resets to empty)

**Selection Logic:**
```python
if settings.vector_store_backend == "qdrant":
    try:
        return QdrantStore(url, collection, dimension)
    except:
        pass  # Fall through to FAISS
return FAISSIndex(dimension, index_dir)
```

### 3.4 Embedding Service

**Provider:** Ollama (default) or sentence-transformers (fallback)

| Setting | Value |
|---------|-------|
| Model | `nomic-embed-text` |
| Dimension | 768 |
| Max input | 7500 characters (~8192 tokens) |
| Batch size | 32 texts per batch |
| Endpoint | `POST /api/embeddings` (Ollama) |
| Timeout | 60 seconds |
| Retries | 3 with exponential backoff |

**Warmup:** Model is pre-loaded at startup to eliminate cold-start latency on the first query.

### 3.5 LLM Gateway

**Primary: Ollama** (local)
- Endpoint: `POST /api/generate`
- Model: `llama3:8b`
- Timeout: 120 seconds
- Retries: 2 with 1-second backoff
- Streaming support via chunked response

**Secondary: vLLM** (OpenAI-compatible)
- Endpoint: `POST /v1/chat/completions`
- Configurable base URL

**Tertiary: External Providers** (via AIRouter)
- OpenAI (GPT-4o-mini), Claude (Sonnet 4), Gemini (2.0 Flash)
- Groq (Llama 3.1 8B), Perplexity (Sonar), Grok (3 Mini)
- Priority-based fallback chain
- Encrypted API key storage (Fernet)
- Per-provider usage tracking and limits

---

## 4. Features & Functionalities

### 4.1 RAG Chat (Core)

**Input:** Natural language HR question + user role + session context
**Output:** Cited answer with confidence score, sources, follow-up suggestions

**Edge Cases Handled:**
- Empty/whitespace queries → "Please enter a question"
- Prompt injection attempts → Blocked with security event logged
- Non-English queries → Language detection + polite redirect
- Non-HR queries (IT, personal) → Domain redirect with helpful message
- Greetings → Friendly response without RAG
- Ambiguous queries → Clarification prompt with suggested refinements
- Compound queries → Split, retrieve independently, merge answers
- No matching documents → Clear "not found" message with HR contact
- LLM timeout/error → Graceful error message
- Low-confidence answers → Disclaimer banner
- Contradictory sources → Both versions shown with HR escalation suggestion

### 4.2 Document Management

**Upload:**
- Formats: PDF, DOCX, MD, TXT (max 100 MB)
- Auto-classification by content analysis
- Duplicate detection (content hash + filename)
- Approval workflow (HR Team → pending; HR Head+ → auto-approved)
- Path traversal prevention (filename sanitization + realpath check)

**Ingestion Pipeline (10 steps):**
1. Save file to upload directory
2. Extract text per page (pdfplumber for PDF, python-docx for DOCX)
3. Clean text (normalize unicode, remove artifacts, collapse whitespace)
4. Build document metadata
5. Chunk by headings first, then fixed-size with sentence-boundary awareness
6. Embed in batches of 32 via nomic-embed-text
7. Index into FAISS/Qdrant vector store
8. Update BM25 keyword index
9. Register in SQLite database
10. Persist FAISS index to disk (atomic write)

**Chunking Parameters:**
```python
HR_CHUNK_RULES = {
    "policy":     {"size": 400, "overlap": 60},
    "handbook":   {"size": 400, "overlap": 60},
    "benefits":   {"size": 350, "overlap": 50},
    "leave":      {"size": 350, "overlap": 50},
    "onboarding": {"size": 400, "overlap": 60},
    "legal":      {"size": 500, "overlap": 80},
}
MIN_CHUNK_WORDS = 15
MAX_CHUNK_WORDS = 800
MAX_CHUNKS_PER_DOCUMENT = 2000
```

### 4.3 Ticket System

**Workflow:**
```
Employee creates ticket
    → Status: raised
    → HR assigns
    → Status: assigned → in_progress
    → HR resolves
    → Status: resolved
    → Employee provides feedback (rating + comment) within 7 days
    → Status: closed
    → (or auto-closed after 7 days without response)
```

**Features:** Priority levels (low/medium/high/urgent), comment threads, escalation from chat, assignment to specific HR staff, full audit trail.

### 4.4 Anonymous Complaints

**Workflow:**
```
Employee submits anonymous complaint
    → Status: submitted
    → HR Head reviews
    → Status: under_review → investigating
    → HR Head resolves
    → Status: resolved (or dismissed)
```

**Categories:** harassment, discrimination, fraud, safety, ethics, retaliation, misconduct, policy_violation.

### 4.5 FAQ Fast-Path

**Matching Algorithm:** Weighted combination of sequence similarity (0.6) + keyword Jaccard overlap (0.4). Threshold: 0.55 combined score.

**Priority:** FAQ check runs before RAG retrieval. If match found, returns curated answer instantly with high confidence.

### 4.6 CFLS (Controlled Feedback Learning System)

**Purpose:** HR-approved answer corrections that override RAG responses.

**Flow:**
1. Employee reports incorrect answer (detailed feedback)
2. HR reviews feedback
3. HR creates a "knowledge correction" (query pattern → corrected response)
4. On future matching queries, correction is returned instead of RAG answer
5. Corrections are tracked with use_count for analytics

### 4.7 Notification System

**Types:** Ticket updates, document approval requests, complaint status changes, system alerts.

**Delivery:** In-app notifications with unread count badge, polled every 30 seconds.

### 4.8 Branch & HR Contact Management

**Branches:** Organization locations with CRUD operations, user assignment, statistics.

**HR Contacts:** Directory of HR staff per branch with contact details and availability status.

---

## 5. Conversation Engine

### 5.1 Prompt Design Strategy

**System Prompt Template:**
```
You are an HR assistant for {company_name}.

STRICT RULES:
1. Answer ONLY using the document excerpts provided below
2. CITE every claim with [Source: document name, Page X]
3. Use relevant excerpts even if not perfectly matched
4. Only say "I don't have information" if NO excerpts relate at all
5. NEVER invent policies, numbers, or dates
6. Redirect personal data questions (salary, reviews) to HR
7. Be concise and use bullet points

DOCUMENT EXCERPTS:
{context}

CONVERSATION HISTORY:
{conversation_history}
```

**Prompt Leakage Detection:** If the LLM response contains 2+ internal instruction phrases (e.g., "STRICT RULES", "CITE EVERY CLAIM"), the response is replaced with a generic message. This prevents the LLM from echoing system instructions.

### 5.2 Context Handling

**Session History:**
- Last 5 turns loaded per query (configurable)
- If conversation exceeds 6 turns, older turns are summarized by LLM into a brief context blob
- Maximum 200 turns per session (hard cap; auto-trims oldest 20% when exceeded)

**Anaphoric Reference Resolution:**
- Previous turn is injected into context to resolve pronouns ("What about that policy?" → context from previous answer)

**Token Management:**
- Max context tokens: 3000 (configurable)
- Token estimation: `word_count * 1.3`
- Chunks are added greedily until budget exhausted
- Minimum relevance floor: 0.05 (sigmoid-normalized cross-encoder score)
- Deduplication by text hash (first 150 characters)

### 5.3 Response Generation Flow

**11-Stage Pipeline:**

| Stage | Name | Purpose |
|-------|------|---------|
| -1 | Smart Routing | Redirect non-HR queries (IT, personal, greetings) |
| 0a | CFLS Check | Return HR-approved corrections if pattern matches |
| 0b | FAQ Fast-Path | Return curated answers for known questions |
| 0c | Language Detection | Block non-English queries with polite message |
| 1 | Query Analysis | Classify intent, complexity, sensitivity, emotion, domain |
| 1b | Retrieval | Dense + BM25 + RRF + cross-encoder reranking |
| 1c | Contradiction Detection | Flag conflicting info across chunks |
| 1d | Sensitivity Guidance | Append warnings for sensitive topics |
| 2 | Context Building | Token-budget-aware context with source attribution |
| 2b | Reasoning Engine | Chain-of-thought prompting for complex queries |
| 2c | Model Routing | Select optimal model tier (fast/standard/advanced) |
| 3 | LLM Generation | Call Ollama with constructed prompt |
| 4 | Verification | Faithfulness scoring + citation extraction |
| 4a | Enrichment | Emotional acknowledgments for stressed/worried users |
| 4b | Content Safety | Profanity, harmful content, bias detection |
| 4c | PII Scrubbing | Redact emails, SSNs, phone numbers, credit cards |
| 4d | Guardrails | Post-guard policy validation |
| 5 | Follow-up Suggestions | Generate 2-3 contextual follow-up questions |

---

## 6. Algorithms & Logic

### 6.1 Hybrid Retrieval

```
Query Embedding (nomic-embed-text, 768-dim)
         |
    +----+----+
    |         |
    v         v
  Dense     BM25
  Search    Search
  (top-20)  (top-20)
    |         |
    +----+----+
         |
         v
  Reciprocal Rank Fusion
    For each result:
      rrf_score = 0.6/(60 + dense_rank) + 0.4/(60 + bm25_rank)
    Sort by rrf_score descending
         |
         v
  Cross-Encoder Reranking (top-8)
    Model: ms-marco-MiniLM-L-6-v2
    Score: sigmoid(raw_logit) = 1/(1 + e^(-x))
    Sort by reranked score descending
         |
         v
  Final Results (with RBAC filtering applied at each stage)
```

**Why Hybrid?** Dense retrieval excels at semantic similarity ("What are my PTO options?" matches "vacation leave entitlement"). BM25 catches exact keyword matches that dense retrieval may miss ("FMLA" as an exact term). Reciprocal Rank Fusion combines both without requiring score normalization.

### 6.2 Query Analysis (18-Dimensional Classification)

```python
QueryAnalysis:
  original_query      # Raw input
  query_type          # comparative | procedural | factual | policy_lookup
  complexity          # simple | moderate | complex
  detected_topics     # [leave, benefits, policy, compensation, ...]
  sub_queries         # Split compound queries
  requires_session    # Needs conversation context?
  is_ambiguous        # Needs clarification?
  clarification       # Suggested clarification prompt
  domain              # hr | it | personal | greeting
  language            # en | es | fr | de | zh | ja | ko | ar | hi | ta
  redirect_message    # For non-HR domains
  intent              # policy_lookup | calculation | procedural | sensitive | emotional
  analysis_confidence # 0.0-1.0
  is_sensitive        # termination | harassment | disciplinary | salary | whistleblower
  sensitive_category  # Specific sensitivity type
  is_calculation      # Requires numeric reasoning?
  emotional_tone      # stressed | worried | frustrated | upset
  requires_multi      # Needs multiple retrieval passes?
```

**Topic Detection:** 7 HR domains with keyword ontology (leave, benefits, onboarding, policy, compensation, performance, termination).

**Complexity Estimation:**
- Complex: comparative query OR (conjunction + >20 words)
- Moderate: conjunction OR >15 words
- Simple: everything else

### 6.3 Query Normalization (Synonym Expansion)

**Purpose:** Bridge vocabulary gaps between how employees ask questions and how policies are written.

**Example:**
```
Input:  "how many leaves do I get?"
Output: "how many leaves do I get? leave entitlement annual leave"
```

**70+ synonym groups** mapping informal terms to formal HR terminology:
- "wfh" → "work from home remote work telecommute"
- "pay raise" → "salary increase increment compensation adjustment"
- "fired" → "termination separation involuntary separation"

### 6.4 Confidence Scoring

```python
# Base confidence from retrieval quality
avg_chunk_score = mean(chunk.score for chunk in retrieved_chunks)
citation_ratio = min(1.0, citation_count / max(1, claim_count))
confidence = min(1.0, avg_chunk_score * citation_ratio)

# Faithfulness floor
confidence = max(confidence, faithfulness_score * avg_chunk_score)

# Strong evidence boost
if chunks[0].score > 0.5 and faithfulness > 0.5:
    confidence = max(confidence, 0.5)

# Intent-aware adjustments
if intent == "sensitive":
    confidence = min(confidence, 0.85)    # Cap for sensitive topics
elif intent == "calculation":
    confidence *= 0.95                     # Penalty for numeric queries

# Analyzer confidence factor
confidence *= (0.7 + 0.3 * analysis_confidence)
```

**Verdict Assignment:**
- `grounded` (confidence >= 0.25): Answer well-supported by documents
- `partially_grounded` (confidence >= 0.05): Some support, may need verification
- `ungrounded` (confidence < 0.05): Answer blocked, replaced with disclaimer

### 6.5 Faithfulness Verification

```
1. Split answer into sentence-level claims (>15 chars each)
2. For each claim:
   a. Extract significant words (4+ chars, excluding stop words)
   b. Search retrieved chunks for 2+ word overlap
   c. Record supporting chunk IDs
   d. Per-claim confidence = min(1.0, overlap_count * 0.3 + 0.4)
3. Faithfulness = claims_with_evidence / total_claims
4. Hallucination risk = 1.0 - confidence_score
```

### 6.6 Reasoning Engine (Chain-of-Thought)

**Triggers:** Complex, sensitive, calculation, or contradiction queries.

**Prompt Pattern:**
```
REASONING:
[1-3 sentences: which documents address this, is information sufficient?]

ANSWER:
[Full answer with [Source: doc, Page X] citations]

CONFIDENCE:
[High / Medium / Low]
```

**Role-specific depth:**
- Employee: Simple, clear, bullet points, no jargon
- Manager: Operational details, policy sections, team implications
- HR Admin: Full references, edge cases, cross-references
- HR Head: Comprehensive analysis, compliance implications

### 6.7 Semantic Cache

**Three-layer lookup:**
1. **Exact hash match** — O(1) Redis key lookup
2. **Embedding similarity** — Cosine similarity >= 0.92 against cached embeddings
3. **Miss** — Full RAG pipeline, result cached with 1-hour TTL

**Per-tenant scoping:** Cache keys prefixed with `tenant_id` to prevent cross-tenant leakage.

**Skip conditions:** Cache is bypassed for queries with session context (follow-up questions need conversation history).

---

## 7. Data Management

### 7.1 Database Schema (30+ Tables)

**Core Tables:**

| Table | Purpose | Key Fields |
|-------|---------|-----------|
| `tenants` | Multi-tenancy | tenant_id, name, slug, plan, settings (JSONB) |
| `users` | User accounts | user_id, username, hashed_password, role, department, status, totp_enabled |
| `sessions` | Chat sessions | session_id, user_id, user_role, created_at, last_active |
| `turns` | Conversation history | session_id, role (user/assistant), content, timestamp, metadata (JSON) |
| `documents` | Ingested documents | document_id, title, category, access_roles, chunk_count, content_hash, approval_status |
| `faqs` | Curated Q&A | faq_id, question, answer, keywords, category, is_active |
| `feedback` | User ratings | session_id, query, answer, rating (1-5), timestamp |
| `query_logs` | Analytics | query_hash, query_type, user_role, faithfulness_score, latency_ms |

**Security Tables:**

| Table | Purpose |
|-------|---------|
| `security_events` | Audit trail (event_type, user_id, ip_address, details) |
| `response_versions` | Response versioning (query_hash, answer, confidence, verdict) |
| `refresh_tokens` | Token revocation (token, user_id, expires_at, revoked) |
| `audit_logs` | PostgreSQL audit trail |

**HR Operations Tables:**

| Table | Purpose |
|-------|---------|
| `tickets` | Support tickets (title, status, priority, raised_by, assigned_to) |
| `complaints` | Anonymous complaints (category, status, submitted_at) |
| `notifications` | In-app notifications (title, message, type, is_read) |
| `branches` | Organization locations |
| `hr_contacts` | HR staff directory |
| `knowledge_corrections` | CFLS overrides (query_pattern → corrected_response) |
| `feedback_logs` | Detailed feedback with issue categories |

**AI Configuration Tables:**

| Table | Purpose |
|-------|---------|
| `ai_providers` | External LLM config (provider_name, api_key_encrypted, model_name) |
| `ai_settings` | Active AI mode (internal vs external) |

### 7.2 Storage Strategy

| Data Type | Storage | Retention |
|-----------|---------|-----------|
| Chat messages | SQLite/PostgreSQL `turns` table | Configurable (default 365 days) |
| Document files | Local filesystem / MinIO (S3-compatible) | Until deleted by admin |
| Vector embeddings | FAISS index (disk) / Qdrant (Docker) | Linked to document lifecycle |
| Chunk metadata | FAISS pickle sidecar / Qdrant payload | Linked to document lifecycle |
| Semantic cache | Redis (in-memory) | 1-hour TTL |
| Session state | SQLite/PostgreSQL `sessions` table | 90-day stale cleanup |
| Audit logs | SQLite/PostgreSQL `security_events` | Configurable retention |
| User files | MinIO buckets (per-tenant path) | Until GDPR erasure |

### 7.3 Caching Mechanisms

| Cache | Backend | TTL | Scope |
|-------|---------|-----|-------|
| Semantic query cache | Redis | 1 hour | Per-tenant |
| Tenant config cache | Redis | 5 minutes | Per-tenant |
| BM25 index | In-memory | Rebuilt on document change | Global |
| Cross-encoder model | In-memory | Application lifetime | Global |
| Embedding model | In-memory | Application lifetime | Global |
| Token revocation list | In-memory dict | Auto-pruned on expiry | Global |

---

## 8. Integrations

### 8.1 LLM Providers

| Provider | Model | Use Case | Auth |
|----------|-------|----------|------|
| **Ollama** (primary) | llama3:8b | All queries (local inference) | None (localhost) |
| **Ollama** | nomic-embed-text | Document + query embeddings | None (localhost) |
| **vLLM** (optional) | Configurable | High-throughput inference | None (localhost) |
| **OpenAI** (fallback) | GPT-4o-mini | External fallback | API key (encrypted) |
| **Anthropic** (fallback) | Claude Sonnet 4 | External fallback | API key (encrypted) |
| **Google** (fallback) | Gemini 2.0 Flash | External fallback | API key (encrypted) |
| **Groq** (fallback) | Llama 3.1 8B | Fast external fallback | API key (encrypted) |
| **Perplexity** (fallback) | Llama 3.1 Sonar | External fallback | API key (encrypted) |
| **xAI** (fallback) | Grok 3 Mini | External fallback | API key (encrypted) |

### 8.2 ML Models

| Model | Purpose | Size | Runtime |
|-------|---------|------|---------|
| `llama3:8b` | Response generation | ~4.7GB | Ollama |
| `nomic-embed-text` | Text embeddings (768-dim) | ~275MB | Ollama |
| `ms-marco-MiniLM-L-6-v2` | Cross-encoder reranking | ~23MB | sentence-transformers |

### 8.3 Infrastructure Services

| Service | Version | Purpose | Port |
|---------|---------|---------|------|
| PostgreSQL | 16-alpine | Primary database (production) | 5432 |
| Qdrant | v1.9.0 | Vector store | 6333 |
| Redis | 7-alpine | Cache + task broker | 6379 |
| MinIO | latest | S3-compatible object storage | 9000/9001 |
| PgBouncer | 1.22.0 | Connection pooling | 6432 |
| Ollama | latest | Local LLM inference | 11434 |

---

## 9. Performance & Scalability

### 9.1 Latency Benchmarks

| Operation | Typical Latency | Bottleneck |
|-----------|----------------|------------|
| Query embedding | 50-100ms | Ollama HTTP call |
| Dense retrieval (FAISS, 1K chunks) | 1-5ms | In-memory search |
| BM25 retrieval | 5-15ms | In-memory search |
| Cross-encoder reranking (8 candidates) | 100-200ms | CPU inference |
| LLM generation (llama3:8b) | 2-8 seconds | GPU/CPU inference |
| Full RAG pipeline | 3-10 seconds | LLM generation dominates |
| Semantic cache hit | 5-20ms | Redis lookup + embedding comparison |
| Document viewer (paginated) | 500-900ms | pdfplumber page extraction |

### 9.2 Bottlenecks

1. **LLM Inference (70-80% of latency):** Local Ollama on CPU can take 5-10s per response. GPU acceleration reduces this to 1-3s.
2. **Cross-encoder reranking (10-15%):** Loading and running the sentence-transformer model. Mitigated by warmup at startup.
3. **PDF extraction:** pdfplumber is CPU-bound. Paginated endpoint (11-page window) reduces 31s full extraction to <1s.

### 9.3 Optimization Strategies

| Strategy | Impact | Implementation |
|----------|--------|---------------|
| Semantic cache | 30-40% LLM call reduction | Redis-backed, 0.92 cosine threshold |
| FAQ fast-path | Instant answers for top questions | Curated Q&A database |
| CFLS corrections | Instant answers for known corrections | Pattern-matched overrides |
| Model routing | Right-size LLM per query complexity | Fast/standard/advanced tiers |
| Eager model warmup | Eliminate cold-start latency | Cross-encoder + embedding at startup |
| Batch embedding | Efficient ingestion | 32 texts per batch |
| Paginated document viewer | 35x faster document loading | 11-page window vs full PDF |
| BM25 in-memory index | Sub-millisecond keyword search | Built from metadata at startup |
| PgBouncer connection pooling | 5000 clients → 25 DB connections | Transaction-mode pooling |
| Atomic FAISS saves | No corruption on crash | Write-to-temp + rename |

### 9.4 Scaling Path

| Scale | Architecture | Users |
|-------|-------------|-------|
| **Dev/Demo** | Single server, Docker Compose, FAISS | 1-50 users |
| **Small Org** | Single server, Qdrant, Ollama GPU | 50-500 users |
| **Enterprise** | Kubernetes, HPA, Qdrant cluster, GPU pool | 500-5000 users |
| **Multi-tenant SaaS** | K8s + per-tenant isolation, PgBouncer, Redis cluster | 5000+ users |

---

## 10. Security & Privacy

### 10.1 Authentication

| Mechanism | Details |
|-----------|---------|
| **JWT Access Token** | HS256, 1-hour expiry, claims: {sub, role, department, tenant_id, jti} |
| **Refresh Token** | Opaque, 7-day expiry, server-side stored, revocable |
| **MFA (TOTP)** | RFC 6238, Google Authenticator compatible, recovery codes |
| **Password Policy** | >= 12 chars, letter + number + symbol required |
| **Account Lockout** | 10 failed attempts = 15 min lockout |
| **Login Rate Limit** | 5 attempts/min per IP |
| **Registration Rate Limit** | 3 registrations/hour per IP |

### 10.2 Authorization (RBAC)

```python
ROLE_HIERARCHY = {
    "employee":    ["employee"],
    "manager":     ["employee", "manager"],
    "hr_team":     ["employee", "hr_team"],
    "hr_head":     ["employee", "manager", "hr_team", "hr_head"],
    "hr_admin":    ["employee", "manager", "hr_team", "hr_admin"],
    "super_admin": ["employee", "manager", "hr_team", "hr_admin", "hr_head", "super_admin"],
}
```

Document access: `can_access_document(user_role, doc.access_roles)` checks if any of the user's effective roles match the document's allowed roles.

### 10.3 Input Protection

| Threat | Defense |
|--------|---------|
| **Prompt injection** | 15+ regex patterns detecting jailbreak phrases ("ignore instructions", "you are now", "DAN mode") |
| **Query sanitization** | Unicode NFKC normalization, zero-width char removal, homoglyph normalization (Cyrillic→Latin), HTML tag removal |
| **Path traversal** | Filename sanitization + realpath validation on document upload |
| **XSS** | HTML entity escaping on document titles |
| **Repeated query abuse** | Flags >3 identical queries in 30 seconds |

### 10.4 Output Protection

| Threat | Defense |
|--------|---------|
| **Hallucination** | Multi-stage verification (faithfulness scoring, citation grounding, confidence thresholds) |
| **PII leakage** | Regex-based redaction of emails, SSNs, phone numbers, credit card numbers |
| **Profanity** | Pattern matching against 15+ profanity terms, compound word detection |
| **Harmful content** | Detection of violence, self-harm, discrimination, document forgery phrases |
| **Bias** | Detection of gender/race/age superiority claims |
| **Prompt leakage** | Detection of system instruction phrases echoed in response |

### 10.5 Data Privacy

| Capability | Implementation |
|-----------|---------------|
| **GDPR data export** | `GET /user/{id}/export` — all messages, sessions, profile |
| **Right to erasure** | `DELETE /user/{id}/erase` — hard delete including vector store entries |
| **Data retention** | Configurable; default 365 days; stale session cleanup at 90 days |
| **Audit logging** | Query hashes (not raw queries) for privacy; document access trails |
| **Encryption at rest** | Fernet encryption for API keys and secrets |
| **Tenant isolation** | Per-tenant data filtering at DB, vector store, and cache layers |

### 10.6 Security Headers

```
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'self'
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

---

## 11. Deployment Architecture

### 11.1 Development Environment

```bash
# Backend
cd backend && pip install -r requirements.txt
ollama pull llama3:8b && ollama pull nomic-embed-text
uvicorn backend.app.main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev  # port 3000, proxies /api → :8000
```

**Requirements:** Python 3.11+, Node 20+, Ollama running locally.

### 11.2 Docker Compose (Demo/Small Org)

```yaml
services:
  postgres:    # PostgreSQL 16-alpine, port 5432
  qdrant:      # Qdrant v1.9.0, port 6333
  redis:       # Redis 7-alpine, port 6379
  minio:       # MinIO, ports 9000/9001
  ollama:      # Ollama with llama3:8b + nomic-embed-text, port 11434
  pgbouncer:   # PgBouncer 1.22.0, port 6432
  api:         # FastAPI backend, port 8000
```

**Resource Allocation:** Ollama: 4 CPUs, 16GB RAM. Total: 8 CPUs, 32GB RAM recommended.

### 11.3 CI/CD Pipeline (GitHub Actions)

```
Push/PR to main
    → Lint (ruff + eslint)
    → Unit Tests (SQLite + FAISS)
    → Integration Tests (PostgreSQL 16 + Redis 7)
    → Docker Build + Push to GHCR
    → Deploy to Staging (if: push to main)
    → Smoke Tests (health check)
    → Deploy to Production (if: semver tag v*.*.*)
```

### 11.4 Production (Kubernetes)

**Helm Charts:** API, worker, Qdrant, PostgreSQL, Redis, MinIO, Ollama, Grafana.

**Scaling:**
- API: HPA 2→10 pods based on CPU/request latency
- Ollama: Dedicated GPU nodes (4 CPUs, 16GB RAM per instance)
- PgBouncer: 5000 client connections → 25 DB connections
- Qdrant: Horizontal scaling with sharding

### 11.5 Observability

| Tool | Purpose |
|------|---------|
| **Prometheus** | Metrics collection (query latency, error rates, cache hits) |
| **Grafana** | Dashboards (p50/p95/p99 latency, active users, queue depth) |
| **OpenTelemetry** | Distributed tracing across RAG pipeline spans |
| **Jaeger/Tempo** | Trace visualization and analysis |
| **Structured Logging** | JSON logs with correlation IDs via structlog |

---

## 12. Limitations & Trade-offs

### 12.1 Known Limitations

| Limitation | Impact | Mitigation |
|-----------|--------|------------|
| **Local LLM quality** | llama3:8b may produce less nuanced answers than GPT-4 | AIRouter fallback to external providers; model routing for complex queries |
| **No OCR support** | Scanned PDFs produce zero chunks | Logged with hint; HR must upload text-extractable PDFs |
| **English-only** | Non-English queries redirected | Language detection with polite message |
| **No real-time HRMS data** | Can't answer "What's my leave balance?" from live systems | Redirect to HR; HRMS adapter framework planned (Phase 4) |
| **SQLite in dev** | Single-writer, no concurrent writes | PostgreSQL for production; SQLite fine for demo/dev |
| **In-memory BM25** | Rebuilt on every startup; lost if process crashes | Fast rebuild from FAISS metadata; <1s for 1000 chunks |
| **No voice interface** | Text-only interaction | Planned for future (G-14 in roadmap) |

### 12.2 Design Compromises

| Decision | Trade-off | Rationale |
|----------|-----------|-----------|
| FAISS over pgvector | No SQL joins on vectors | Simpler deployment; Qdrant as primary handles complex queries |
| Pickle metadata | Not human-readable | Fast serialization; atomic save prevents corruption |
| In-memory token revocation | Lost on restart | JWT expiry is 1 hour; acceptable risk for dev; Redis in production |
| Synchronous ingestion (dev) | Blocks upload request | Celery + Redis available for async in production |
| Heading-based chunking first | May miss content if headings poorly formatted | Fallback to fixed-size chunking if coverage <50% |
| 15+ regex prompt injection | Not ML-based | Fast, predictable, no false positives on normal HR queries |

---

## 13. Future Improvements

### 13.1 High Priority (from Roadmap)

| Feature | Description | Effort |
|---------|-------------|--------|
| G-01: Load Testing | Locust tests for 100/500/1000 concurrent users | Medium |
| G-02: Pen Testing | OWASP ZAP automated scans in CI | Medium |
| G-04: Retrieval Benchmarks | MRR, NDCG, Recall@k ground-truth evaluation | Medium |
| G-11: Semantic Chunking | Parent-child chunk hierarchy for long documents | Medium |
| G-12: Feedback-Driven Tuning | Negative feedback deprioritizes sources | Medium |

### 13.2 Medium Priority

| Feature | Description | Effort |
|---------|-------------|--------|
| G-06: Slack Bot | Slash commands + conversational threads | Medium |
| G-07: Teams Bot | Activity handler + adaptive cards | Medium |
| G-08: Multi-Language | Translation layer + multilingual embeddings | Large |
| G-09: WCAG 2.1 AA | Keyboard nav, screen reader, contrast | Medium |
| G-10: A/B Testing | Compare RAG parameters (chunk sizes, models) | Medium |

### 13.3 Long-Term Vision

| Feature | Description | Effort |
|---------|-------------|--------|
| G-14: Voice Interface | STT → RAG → TTS via WebRTC | Large |
| G-15: Fine-Tuning Pipeline | LoRA/QLoRA domain adaptation | Large |
| G-16: Knowledge Graph | Entity relationships across policies | Large |
| G-17: Agentic Workflows | "Help me request leave" → multi-step form filling | Large |

### 13.4 SaaS Evolution

| Step | Status | Description |
|------|--------|-------------|
| tenant_id on all tables | DONE | Row-level isolation |
| Tenant middleware | DONE | JWT-based tenant resolution |
| All queries filter by tenant | DONE | DB, vector store, cache |
| Tenant management API | DONE | CRUD with config JSONB |
| Per-tenant feature flags | DONE | SSO, MFA, model routing |
| Tenant onboarding flow | TODO | Self-serve signup + provisioning |
| Billing integration (Stripe) | TODO | Usage-based or per-seat |
| Physical isolation option | TODO | Dedicated schema/DB for enterprise |

---

## Appendix A — API Endpoint Reference

### Authentication (`/auth`)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/auth/login` | Public | Login with username/password |
| POST | `/auth/register` | Public | Self-registration (requires approval) |
| POST | `/auth/logout` | Bearer | Revoke tokens |
| POST | `/auth/refresh` | Refresh token | Get new access token |
| POST | `/auth/forgot-password` | Public | Initiate password reset |
| POST | `/auth/reset-password` | Public | Complete password reset |
| GET | `/auth/me` | Bearer | Current user profile |
| PATCH | `/auth/me` | Bearer | Update profile |

### Chat (`/chat`)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/chat/query` | Bearer | Send query (non-streaming) |
| POST | `/chat/query/stream` | Bearer | Send query (SSE streaming) |
| GET | `/chat/sessions` | Bearer | List user's sessions |
| GET | `/chat/sessions/{id}/history` | Bearer | Get session conversation |
| DELETE | `/chat/sessions/{id}` | Bearer | Delete session |
| POST | `/chat/feedback` | Bearer | Submit feedback |
| POST | `/chat/escalate` | Bearer | Escalate to HR ticket |

### Documents (`/documents`)
| Method | Path | Auth | Role |Purpose |
|--------|------|------|------|--------|
| POST | `/documents/upload` | Bearer | HR+ | Upload document |
| GET | `/documents` | Bearer | Any | List documents |
| GET | `/documents/{id}/content` | Bearer | Any | Get document content (paginated) |
| DELETE | `/documents/{id}` | Bearer | HR+ | Delete document |
| POST | `/documents/{id}/reindex` | Bearer | HR+ | Reindex document |

### Admin (`/admin`)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/admin/metrics` | Admin | Dashboard analytics |
| GET | `/admin/failed-queries` | Admin | Failed query analysis |
| GET | `/admin/security-events` | Admin | Audit trail |
| GET | `/admin/users` | Admin | User management |
| POST | `/admin/users/{id}/approve` | Admin | Approve/reject user |
| POST | `/admin/cache/clear` | Admin | Clear semantic cache |
| POST | `/admin/gdpr/cleanup` | Admin | GDPR data retention cleanup |

### Tickets (`/tickets`)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/tickets` | Bearer | Create ticket |
| GET | `/tickets` | Bearer | List tickets (filtered) |
| GET | `/tickets/{id}` | Bearer | Get ticket detail |
| PATCH | `/tickets/{id}` | HR+ | Update ticket status |
| POST | `/tickets/{id}/comments` | Bearer | Add comment |
| GET | `/tickets/stats` | Bearer | Ticket statistics |

### AI Configuration (`/ai-config`)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/ai-config/mode` | Admin | Current AI mode |
| POST | `/ai-config/mode` | Admin | Switch internal/external |
| POST | `/ai-config/providers` | Admin | Add external provider |
| POST | `/ai-config/providers/{name}/test` | Admin | Test provider |
| GET | `/ai-config/usage` | Admin | Usage analytics |
| GET | `/ai-config/routing` | Admin | Model routing config |
| POST | `/ai-config/routing` | Admin | Set model routing |

---

## Appendix B — Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | dev | Runtime environment |
| `API_PORT` | 8000 | Backend port |
| `JWT_SECRET_KEY` | change-me... | JWT signing key |
| `JWT_ALGORITHM` | HS256 | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 60 | Access token TTL |
| `LLM_PROVIDER` | ollama | LLM backend (ollama/vllm) |
| `LLM_MODEL` | llama3:8b | Default LLM model |
| `OLLAMA_BASE_URL` | http://localhost:11434 | Ollama endpoint |
| `EMBEDDING_MODEL` | nomic-embed-text | Embedding model name |
| `EMBEDDING_DIMENSION` | 768 | Embedding vector size |
| `VECTOR_STORE_BACKEND` | qdrant | Vector store (qdrant/faiss) |
| `QDRANT_URL` | http://localhost:6333 | Qdrant endpoint |
| `FAISS_INDEX_DIR` | ./data/faiss_index | FAISS storage path |
| `DB_PATH` | ./data/hr_chatbot.db | SQLite database path |
| `REDIS_URL` | redis://localhost:6379/0 | Redis connection |
| `DENSE_TOP_K` | 20 | Dense retrieval candidates |
| `BM25_TOP_K` | 20 | BM25 retrieval candidates |
| `RERANK_TOP_N` | 8 | Final reranked results |
| `MAX_CONTEXT_TOKENS` | 3000 | Context window budget |
| `DENSE_WEIGHT` | 0.6 | RRF dense score weight |
| `BM25_WEIGHT` | 0.4 | RRF BM25 score weight |
| `VERIFY_GROUNDING` | true | Enable answer verification |
| `MIN_FAITHFULNESS_SCORE` | 0.7 | Minimum faithfulness threshold |
| `UPLOAD_DIR` | ./data/uploads | Document storage path |
| `COMPANY_NAME` | Acme Corp | Display name in prompts |

---

*Document: TECHNICAL_DOCUMENTATION.md*
*Version: 2.0.0 | Created: 2026-03-26*
*Lines of Code: Backend ~6000+ Python, Frontend ~8000+ TypeScript*
*Total Features: 74 (61 core + 13 UX/UI)*
*Total API Endpoints: 60+*
*Total Database Tables: 30+*
