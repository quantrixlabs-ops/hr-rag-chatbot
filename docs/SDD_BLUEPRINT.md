# Enterprise HR RAG Chatbot — Spec-Driven Development Blueprint

**Version:** 1.0.0
**Classification:** Engineering Playbook — Implementation-Ready
**Target:** ~5,000 employees, scalable to 50k+
**Deployment:** Hybrid (cloud + on-prem) | Local models only | RBAC-enforced

---

## Table of Contents

| # | Section | Purpose |
|---|---------|---------|
| 1 | Product Requirements Specification | Goals, personas, features, NFRs |
| 2 | System Architecture Specification | Service topology, request flow |
| 3 | Modular Service Architecture | Per-module specs with I/O contracts |
| 4 | RAG Pipeline Specification | End-to-end retrieval-augmented generation |
| 5 | Document Ingestion Spec | Loaders, extraction, metadata |
| 6 | Chunking Strategy Specification | Semantic + heading-aware chunking |
| 7 | Vector Database Specification | Schema, index, query structure |
| 8 | Retrieval Strategy Specification | Hybrid retrieval + reranking |
| 9 | Context Construction Spec | Token budgeting, dedup, filtering |
| 10 | LLM Inference Specification | Local model gateway, prompts |
| 11 | Answer Verification Spec | Grounding, citation, confidence |
| 12 | Session Management Spec | Conversation memory, retention |
| 13 | Role-Based Access Control Spec | RBAC enforcement at retrieval |
| 14 | Multi-Agent Reasoning Architecture | 5-agent advanced reasoning |
| 15 | Evaluation Framework | Metrics, datasets, benchmarking |
| 16 | Autotuning & Continuous Improvement | Self-optimizing RAG |
| 17 | Security Specification | Auth, injection defense, audit |
| 18 | Observability Spec | Logs, metrics, health |
| 19 | Deployment Architecture | Infrastructure, scaling |
| 20 | API Contract Specification | Endpoints, schemas |
| 21 | Development Roadmap | 5-phase implementation plan |
| 22 | Best Practices | Engineering cheat codes |

---

# SECTION 1 — PRODUCT REQUIREMENTS SPECIFICATION (PRS)

## 1.1 System Goals

| Goal | Target | Measurement |
|------|--------|-------------|
| Answer HR questions accurately from company documents | >93% faithfulness | Automated eval suite |
| Prevent hallucinated or ungrounded answers | <5% hallucination rate | Claim-vs-evidence verification |
| Enforce document-level access control | Zero unauthorized document leakage | RBAC audit log |
| Respond within acceptable latency | P95 < 3 seconds | Observability metrics |
| Scale to 50k+ employees without re-architecture | Horizontal scaling | Load testing |
| Operate with local models only (no external API calls) | 100% on-prem inference | Network audit |

## 1.2 User Personas

### Employee (VIEWER role)

- Access: General HR policies, employee handbook, benefits docs, leave policies, onboarding materials
- Actions: Ask questions, view chat history, provide feedback
- Restrictions: Cannot see manager-only or HR-admin documents

### Manager (ANALYST role)

- Access: Everything employees can see + manager-specific policies (performance review guidelines, termination procedures, compensation bands)
- Actions: Ask questions, view team-related HR policies, export conversation summaries
- Restrictions: Cannot see HR-admin-only documents (audit reports, legal hold docs)

### HR Admin (ADMIN role)

- Access: All documents including internal HR procedures, audit trails, legal compliance docs
- Actions: Upload/manage documents, configure system, view analytics, manage user roles
- Restrictions: None (full access)

## 1.3 Core Features

| ID | Feature | Priority |
|----|---------|----------|
| F-001 | Session-based conversational HR assistant | P0 |
| F-002 | RAG-grounded answers with source citations | P0 |
| F-003 | RBAC-filtered document retrieval | P0 |
| F-004 | Document ingestion pipeline (PDF, DOCX, MD, TXT) | P0 |
| F-005 | Hybrid retrieval (dense + keyword) | P0 |
| F-006 | Answer verification / anti-hallucination | P0 |
| F-007 | Conversation history & context retention | P1 |
| F-008 | Admin dashboard with analytics | P1 |
| F-009 | Feedback loop (thumbs up/down) | P1 |
| F-010 | Multi-agent reasoning for complex queries | P2 |
| F-011 | Autonomous RAG optimization | P2 |
| F-012 | Evaluation & benchmarking framework | P1 |

## 1.4 Non-Functional Requirements

| Requirement | Specification |
|-------------|---------------|
| Availability | 99.5% uptime during business hours |
| Latency | P50 < 1.5s, P95 < 3s, P99 < 5s |
| Throughput | 100 concurrent sessions minimum |
| Data residency | All data on-prem or approved cloud region |
| Model hosting | Local only — vLLM / Ollama / equivalent |
| Security | JWT auth, RBAC, prompt injection defense, audit logging |
| Scalability | Horizontal scaling to 50k+ users |
| Recoverability | RPO < 1 hour, RTO < 15 minutes |

---

# SECTION 2 — SYSTEM ARCHITECTURE SPECIFICATION

## 2.1 Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────────┐
│                           CLIENT LAYER                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                     │
│  │  Web Chat UI │  │  Teams Bot   │  │  Mobile App  │                     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                     │
│         └──────────────────┼──────────────────┘                            │
│                            ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      API GATEWAY (FastAPI)                          │   │
│  │  /chat/* │ /documents/* │ /admin/* │ /auth/* │ /health             │   │
│  └────────────────────────┬────────────────────────────────────────────┘   │
│                           ▼                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    AUTHENTICATION & RBAC                            │   │
│  │  JWT Validator → Role Resolver → Permission Filter                 │   │
│  └────────────────────────┬────────────────────────────────────────────┘   │
│                           ▼                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     CHAT SERVICE                                    │   │
│  │  Session Manager ← → RAG Pipeline ← → Response Formatter          │   │
│  └────────────────────────┬────────────────────────────────────────────┘   │
│                           ▼                                                │
│  ┌──────────────────── RAG PIPELINE ───────────────────────────────────┐   │
│  │                                                                     │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │   │
│  │  │  Query   │→ │ Retrieval│→ │ Reranker │→ │ Context  │          │   │
│  │  │ Analyzer │  │  Engine  │  │          │  │ Builder  │          │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘          │   │
│  │        │              │                           │                │   │
│  │        ▼              ▼                           ▼                │   │
│  │  ┌──────────┐  ┌──────────┐                ┌──────────┐          │   │
│  │  │  Query   │  │  Vector  │                │   LLM    │          │   │
│  │  │Decomposer│  │  Store   │                │ Gateway  │          │   │
│  │  └──────────┘  │+ BM25   │                └──────────┘          │   │
│  │                └──────────┘                      │                │   │
│  │                                                  ▼                │   │
│  │                                            ┌──────────┐          │   │
│  │                                            │ Answer   │          │   │
│  │                                            │ Verifier │          │   │
│  │                                            └──────────┘          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│  ┌──────────────────── SUPPORTING SERVICES ────────────────────────────┐   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐   │   │
│  │  │ Document   │  │ Embedding  │  │ Evaluation │  │Observability│   │   │
│  │  │ Ingestion  │  │  Service   │  │  Service   │  │  Service    │   │   │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│  ┌──────────────────── DATA LAYER ─────────────────────────────────────┐   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │   │
│  │  │ Vector   │  │ SQLite/  │  │  Redis   │  │  File    │          │   │
│  │  │  Store   │  │ Postgres │  │  Cache   │  │  Store   │          │   │
│  │  │(FAISS/   │  │          │  │          │  │          │          │   │
│  │  │ Qdrant)  │  │          │  │          │  │          │          │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────────┘
```

## 2.2 Request Flow

```
1. User sends message via chat UI
2. API Gateway authenticates JWT → resolves user role
3. Chat Service creates/resumes session
4. RAG Pipeline executes:
   a. Query Analysis — classify, decompose, detect intent
   b. Retrieval — hybrid search (dense + BM25) with RBAC filter
   c. Reranking — cross-encoder scores top candidates
   d. Context Construction — token budget, dedup, format
   e. LLM Inference — local model generates answer
   f. Answer Verification — grounding check, citation extraction
5. Response returned with citations + confidence score
6. Session updated with conversation turn
7. Telemetry emitted (latency, retrieval stats, confidence)
```

## 2.3 Service Registry

| Service | Port | Protocol | Scaling |
|---------|------|----------|---------|
| API Gateway | 8000 | HTTP/REST | Horizontal (load balanced) |
| Chat Service | Internal | In-process | Scales with API Gateway |
| Vector Store (FAISS) | In-process | Library call | Per-instance index |
| Vector Store (Qdrant) | 6333 | gRPC/HTTP | Cluster mode |
| LLM Gateway (vLLM) | 8001 | HTTP/OpenAI-compat | GPU-per-instance |
| LLM Gateway (Ollama) | 11434 | HTTP | CPU/GPU instance |
| Redis | 6379 | Redis protocol | Sentinel/Cluster |
| PostgreSQL | 5432 | PostgreSQL wire | Primary-replica |
| Observability (Prometheus) | 9090 | HTTP | Single/HA pair |

---

# SECTION 3 — MODULAR SERVICE ARCHITECTURE

## 3.1 Document Ingestion Service

```yaml
module: document_ingestion
purpose: Extract text from HR documents, chunk, embed, and index into vector store
inputs:
  - file: binary (PDF, DOCX, MD, TXT)
  - metadata:
      title: string
      category: enum[policy, handbook, benefits, leave, onboarding, legal]
      access_roles: list[string]  # ["employee", "manager", "hr_admin"]
      effective_date: ISO-8601
      version: string
outputs:
  - document_id: UUID
  - chunk_count: int
  - index_status: enum[indexed, failed, pending]
dependencies:
  - embedding_service
  - vector_store
  - file_store
```

## 3.2 Embedding Service

```yaml
module: embedding_service
purpose: Generate dense vector embeddings from text using local models
inputs:
  - texts: list[string]
  - model_id: string (default: "nomic-embed-text" or "bge-base-en-v1.5")
outputs:
  - embeddings: list[float[768]]  # dimension depends on model
  - model_used: string
  - latency_ms: float
dependencies:
  - model_gateway (Ollama or sentence-transformers)
config:
  batch_size: 64
  max_tokens_per_text: 512
  normalize: true
```

## 3.3 Vector Search Service

```yaml
module: vector_search
purpose: Execute similarity search with RBAC filtering
inputs:
  - query_embedding: float[768]
  - top_k: int (default: 20)
  - role_filter: list[string]  # user's allowed roles
  - category_filter: optional[list[string]]
outputs:
  - results: list[SearchResult]
    # SearchResult: {chunk_id, text, score, source, page, metadata}
  - search_latency_ms: float
dependencies:
  - vector_store (FAISS/Qdrant/pgvector)
  - metadata_store
```

## 3.4 BM25 Keyword Search Service

```yaml
module: bm25_search
purpose: Lexical keyword retrieval for exact-match and acronym queries
inputs:
  - query: string
  - top_k: int (default: 20)
  - role_filter: list[string]
outputs:
  - results: list[SearchResult]
dependencies:
  - inverted_index (rank_bm25 or Elasticsearch)
```

## 3.5 Retrieval Orchestration Service

```yaml
module: retrieval_orchestrator
purpose: Combine dense + BM25 results, deduplicate, rerank
inputs:
  - query: string
  - user_role: string
  - session_context: optional[list[ConversationTurn]]
  - strategy: enum[fast, standard, thorough]
outputs:
  - ranked_chunks: list[RankedChunk]  # top 5-10 after reranking
  - retrieval_metadata:
      dense_count: int
      bm25_count: int
      reranked_count: int
      coverage_score: float
dependencies:
  - embedding_service
  - vector_search
  - bm25_search
  - reranker
```

## 3.6 LLM Inference Service

```yaml
module: llm_inference
purpose: Generate answers using local LLM with injected context
inputs:
  - prompt: string (system + context + conversation + user query)
  - model_id: string
  - temperature: float (default: 0.1)
  - max_tokens: int (default: 1024)
outputs:
  - response_text: string
  - token_usage: {prompt_tokens, completion_tokens}
  - latency_ms: float
  - model_used: string
dependencies:
  - model_gateway (vLLM / Ollama)
config:
  providers:
    vllm:
      base_url: "http://localhost:8001/v1"
      api_format: openai_compatible
    ollama:
      base_url: "http://localhost:11434"
      api_format: ollama_native
```

## 3.7 Answer Verification Service

```yaml
module: answer_verification
purpose: Verify generated answer is grounded in retrieved evidence
inputs:
  - answer: string
  - source_chunks: list[RankedChunk]
  - query: string
outputs:
  - faithfulness_score: float (0.0–1.0)
  - hallucination_risk: float (0.0–1.0)
  - grounded_claims: list[{claim, evidence_chunk_id, verified}]
  - citations: list[{source, page, excerpt}]
  - verdict: enum[grounded, partially_grounded, ungrounded]
dependencies:
  - (optional) secondary LLM call for NLI-based verification
  - or: heuristic TF-IDF claim↔chunk overlap verifier
```

## 3.8 Session Memory Service

```yaml
module: session_memory
purpose: Store and retrieve conversation history per session
inputs:
  - session_id: UUID
  - turn: {role: "user"|"assistant", content: string, timestamp: float}
outputs:
  - session: {id, turns, created_at, last_active}
dependencies:
  - sqlite or redis
config:
  max_turns: 20
  retention_days: 30
  context_window_turns: 5  # last N turns injected into prompt
```

## 3.9 Evaluation Service

```yaml
module: evaluation
purpose: Measure RAG quality across retrieval and generation metrics
inputs:
  - eval_dataset: list[{query, expected_keywords, expected_sources}]
  - pipeline_config: current RAG configuration
outputs:
  - metrics:
      retrieval_precision: float
      answer_faithfulness: float
      hallucination_rate: float
      latency_p50_ms: float
      latency_p95_ms: float
  - per_query_breakdown: list[EvalResult]
dependencies:
  - rag_pipeline
  - answer_verification
```

## 3.10 Observability Service

```yaml
module: observability
purpose: Structured logging, metrics collection, health monitoring
outputs:
  - structured_logs → stdout (JSON) → log aggregator
  - prometheus_metrics → /metrics endpoint
  - health_status → /health endpoint
dependencies:
  - structlog
  - prometheus_client
  - (optional) Grafana dashboards
```

---

# SECTION 4 — RAG PIPELINE SPECIFICATION

## 4.1 Pipeline Stages

```
Query → [1] Query Analysis → [2] Retrieval → [3] Reranking →
  [4] Context Construction → [5] LLM Generation → [6] Verification → Response
```

### Stage 1: Query Analysis

```python
@dataclass
class QueryAnalysis:
    original_query: str
    query_type: str         # factual | policy_lookup | comparative | procedural
    complexity: str         # simple | moderate | complex
    detected_topics: list[str]  # ["leave", "benefits", "onboarding"]
    sub_queries: list[str]  # decomposed queries for multi-hop
    requires_session_context: bool
```

**Implementation:**
- Regex + keyword matching for HR topic detection
- Word count + conjunction detection for complexity classification
- Sub-query generation: split on "and"/"also"/"additionally" for multi-part questions

### Stage 2: Retrieval

Execute in parallel:
- **Dense retrieval**: Embed query → top-K nearest neighbors from vector store
- **BM25 retrieval**: Keyword search over inverted index
- Merge results with Reciprocal Rank Fusion (RRF):

```python
def rrf_score(dense_rank: int, bm25_rank: int, k: int = 60) -> float:
    dense_contrib = 1.0 / (k + dense_rank) if dense_rank else 0
    bm25_contrib = 1.0 / (k + bm25_rank) if bm25_rank else 0
    return dense_contrib + bm25_contrib
```

- Apply RBAC filter: remove chunks where `chunk.access_roles` does not include user's role

### Stage 3: Reranking

```python
# Cross-encoder reranking
from sentence_transformers import CrossEncoder
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

pairs = [(query, chunk.text) for chunk in candidates]
scores = reranker.predict(pairs)
ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
final_chunks = [chunk for chunk, score in ranked[:TOP_N]]
```

- Input: top 20–30 candidates from Stage 2
- Output: top 5–8 reranked chunks
- Fallback: if cross-encoder unavailable, use embedding cosine similarity

### Stage 4: Context Construction

```python
def build_context(chunks: list[Chunk], max_tokens: int = 3000) -> str:
    context_parts = []
    token_count = 0
    seen_texts = set()

    for chunk in chunks:
        # Deduplicate near-identical chunks
        text_hash = hash(chunk.text[:100])
        if text_hash in seen_texts:
            continue
        seen_texts.add(text_hash)

        chunk_tokens = len(chunk.text.split()) * 1.3  # approximate
        if token_count + chunk_tokens > max_tokens:
            break

        context_parts.append(
            f"[Source: {chunk.source}, Page {chunk.page}]\n{chunk.text}"
        )
        token_count += chunk_tokens

    return "\n\n---\n\n".join(context_parts)
```

### Stage 5: LLM Generation

See Section 10 for prompt templates and model configuration.

### Stage 6: Answer Verification

See Section 11 for grounding check and citation extraction.

## 4.2 Pipeline Configuration

```python
@dataclass
class PipelineConfig:
    # Retrieval
    dense_top_k: int = 20
    bm25_top_k: int = 20
    rerank_top_n: int = 8
    final_context_chunks: int = 5

    # Context
    max_context_tokens: int = 3000
    include_source_metadata: bool = True

    # Generation
    llm_model: str = "llama3:8b"
    temperature: float = 0.1
    max_response_tokens: int = 1024

    # Verification
    verify_grounding: bool = True
    min_faithfulness_score: float = 0.7

    # Session
    session_context_turns: int = 5
```

---

# SECTION 5 — DOCUMENT INGESTION SPEC

## 5.1 Supported Formats & Loaders

| Format | Loader | Library |
|--------|--------|---------|
| PDF | `PyPDFLoader` or `pdfplumber` | `langchain_community` / `pdfplumber` |
| DOCX | `Docx2txtLoader` or `python-docx` | `langchain_community` / `python-docx` |
| Markdown | `UnstructuredMarkdownLoader` | `langchain_community` |
| TXT | `TextLoader` | `langchain_community` |

## 5.2 Ingestion Pipeline

```python
class IngestionPipeline:
    """
    file → extract_text → clean → chunk → embed → index → register_metadata
    """

    def ingest(self, file: UploadFile, metadata: DocumentMetadata) -> IngestionResult:
        # 1. Extract raw text
        raw_text = self._extract(file)

        # 2. Clean and normalize
        cleaned = self._clean(raw_text)

        # 3. Chunk with metadata
        chunks = self._chunk(cleaned, metadata)

        # 4. Generate embeddings
        embeddings = self._embed([c.text for c in chunks])

        # 5. Index into vector store
        ids = self._index(chunks, embeddings)

        # 6. Register in metadata store
        doc_id = self._register(metadata, chunk_ids=ids)

        return IngestionResult(
            document_id=doc_id,
            chunk_count=len(chunks),
            status="indexed",
        )
```

## 5.3 Text Extraction Rules

```python
def _clean(self, text: str) -> str:
    # Remove excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove page numbers / headers / footers (common in PDFs)
    text = re.sub(r"Page \d+ of \d+", "", text)
    # Normalize unicode
    text = unicodedata.normalize("NFKC", text)
    # Strip control characters
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text.strip()
```

## 5.4 Metadata Schema

```python
@dataclass
class DocumentMetadata:
    document_id: str          # UUID
    title: str
    category: str             # policy | handbook | benefits | leave | onboarding | legal
    access_roles: list[str]   # ["employee", "manager", "hr_admin"]
    effective_date: str        # ISO-8601
    version: str
    source_filename: str
    uploaded_by: str
    uploaded_at: float         # Unix timestamp
    page_count: int
    chunk_count: int           # set after chunking
```

## 5.5 Chunk Metadata

```python
@dataclass
class ChunkMetadata:
    chunk_id: str             # UUID
    document_id: str          # parent document
    text: str
    page: int | None
    section_heading: str | None
    chunk_index: int          # position in document
    access_roles: list[str]   # inherited from document
    category: str             # inherited from document
    token_count: int
```

---

# SECTION 6 — CHUNKING STRATEGY SPECIFICATION

## 6.1 Chunking Methods

### Method 1: Heading-Aware Semantic Chunking (Primary)

```python
import re

HEADING_PATTERN = re.compile(
    r"^(#{1,4}\s.+|"                     # Markdown headings
    r"[A-Z][A-Za-z\s]{2,60}\n[=-]+|"     # Underline headings
    r"\d+\.\d*\s+[A-Z].{5,80}|"          # Numbered sections (3.1 Policy Name)
    r"[A-Z][A-Z\s]{5,60}$)",             # ALL-CAPS headings
    re.MULTILINE,
)

def heading_aware_chunk(text: str, max_chunk_size: int = 512, overlap: int = 50) -> list[Chunk]:
    """
    Split on headings first, then subdivide oversized sections.
    Preserves section context — critical for policy documents.
    """
    sections = re.split(HEADING_PATTERN, text)
    chunks = []
    current_heading = ""

    for section in sections:
        if HEADING_PATTERN.match(section.strip()):
            current_heading = section.strip()
            continue

        if len(section.split()) <= max_chunk_size:
            chunks.append(Chunk(
                text=f"{current_heading}\n\n{section.strip()}",
                section_heading=current_heading,
            ))
        else:
            # Subdivide oversized sections with overlap
            sub_chunks = fixed_size_chunk(section, max_chunk_size, overlap)
            for sc in sub_chunks:
                chunks.append(Chunk(
                    text=f"{current_heading}\n\n{sc}",
                    section_heading=current_heading,
                ))

    return chunks
```

### Method 2: Fixed-Size with Overlap (Fallback)

```python
def fixed_size_chunk(text: str, chunk_size: int = 512, overlap: int = 50) -> list[str]:
    """Token-based chunking with overlap for documents without clear headings."""
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start = end - overlap
    return chunks
```

## 6.2 Optimal Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `chunk_size` | 400–512 tokens | Balances context richness vs retrieval precision |
| `overlap` | 50–75 tokens | Prevents splitting mid-sentence at chunk boundaries |
| `min_chunk_size` | 50 tokens | Discard fragments that add noise without information |
| `max_chunk_size` | 800 tokens | Hard cap — oversized chunks hurt retrieval specificity |

## 6.3 HR Document-Specific Chunking Rules

```python
HR_CHUNK_RULES = {
    "policy": {
        "split_on": ["headings", "numbered_sections"],
        "preserve": ["definitions", "effective_date", "scope"],
        "chunk_size": 450,
        "overlap": 60,
    },
    "handbook": {
        "split_on": ["chapters", "headings"],
        "preserve": ["chapter_title"],
        "chunk_size": 500,
        "overlap": 75,
    },
    "benefits": {
        "split_on": ["plan_type", "headings"],
        "preserve": ["plan_name", "eligibility"],
        "chunk_size": 400,
        "overlap": 50,
    },
    "leave": {
        "split_on": ["leave_type", "headings"],
        "preserve": ["leave_type_name", "accrual_rules"],
        "chunk_size": 400,
        "overlap": 50,
    },
}
```

## 6.4 Impact on Retrieval

| Chunk Quality Factor | Impact |
|---------------------|--------|
| Too small (< 100 tokens) | High retrieval recall, low context → LLM can't generate useful answer |
| Too large (> 800 tokens) | Low retrieval precision → irrelevant content dilutes signal |
| No overlap | Misses answers that span chunk boundaries |
| No heading preservation | Loses section context → LLM can't interpret chunk meaning |
| Good heading-aware chunking | Best retrieval precision + LLM has section context for generation |

---

# SECTION 7 — VECTOR DATABASE SPECIFICATION

## 7.1 Supported Backends

| Backend | Best For | Deployment | RBAC Filtering |
|---------|----------|------------|----------------|
| FAISS | Development, single-node production | In-process | Post-retrieval filter |
| Qdrant | Production, horizontal scaling | Docker/K8s cluster | Native payload filter |
| pgvector | PostgreSQL-native teams | Existing PG infra | SQL WHERE clause |

## 7.2 Vector Index Schema

```sql
-- pgvector schema
CREATE TABLE hr_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES hr_documents(id),
    text            TEXT NOT NULL,
    embedding       vector(768) NOT NULL,
    section_heading TEXT,
    page            INTEGER,
    chunk_index     INTEGER NOT NULL,
    access_roles    TEXT[] NOT NULL,      -- {"employee", "manager", "hr_admin"}
    category        TEXT NOT NULL,
    token_count     INTEGER NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_chunks_embedding ON hr_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_chunks_roles ON hr_chunks USING GIN (access_roles);
CREATE INDEX idx_chunks_category ON hr_chunks (category);
CREATE INDEX idx_chunks_document ON hr_chunks (document_id);
```

```python
# Qdrant collection schema
from qdrant_client.models import VectorParams, Distance

client.create_collection(
    collection_name="hr_chunks",
    vectors_config=VectorParams(size=768, distance=Distance.COSINE),
)
# Payload schema:
# {
#     "document_id": str,
#     "text": str,
#     "section_heading": str | None,
#     "page": int | None,
#     "access_roles": ["employee", "manager", "hr_admin"],
#     "category": "policy",
#     "chunk_index": int,
# }
```

```python
# FAISS index wrapper
import faiss
import numpy as np

class FAISSIndex:
    def __init__(self, dimension: int = 768):
        self.index = faiss.IndexFlatIP(dimension)  # Inner product (cosine on normalized vecs)
        self.metadata: list[ChunkMetadata] = []

    def add(self, embeddings: np.ndarray, metadata: list[ChunkMetadata]):
        faiss.normalize_L2(embeddings)
        self.index.add(embeddings)
        self.metadata.extend(metadata)

    def search(self, query_embedding: np.ndarray, top_k: int = 20,
               role_filter: list[str] | None = None) -> list[SearchResult]:
        faiss.normalize_L2(query_embedding)
        scores, indices = self.index.search(query_embedding, top_k * 3)  # over-fetch for filtering

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            meta = self.metadata[idx]
            # RBAC filter
            if role_filter and not any(r in meta.access_roles for r in role_filter):
                continue
            results.append(SearchResult(
                chunk_id=meta.chunk_id,
                text=meta.text,
                score=float(score),
                source=meta.source,
                page=meta.page,
                metadata=meta,
            ))
            if len(results) >= top_k:
                break
        return results
```

## 7.3 Retrieval Query Structure

```python
# Qdrant query with RBAC filter
results = client.search(
    collection_name="hr_chunks",
    query_vector=query_embedding,
    query_filter=models.Filter(
        must=[
            models.FieldCondition(
                key="access_roles",
                match=models.MatchAny(any=user_roles),
            ),
        ],
    ),
    limit=20,
)
```

```sql
-- pgvector query with RBAC filter
SELECT id, text, section_heading, page,
       1 - (embedding <=> $1::vector) AS score
FROM hr_chunks
WHERE access_roles && $2::text[]   -- array overlap = role match
ORDER BY embedding <=> $1::vector
LIMIT 20;
```

---

# SECTION 8 — RETRIEVAL STRATEGY SPECIFICATION

## 8.1 Hybrid Retrieval Architecture

```
User Query
    │
    ├──→ [Embedding Model] ──→ Dense Retrieval (FAISS/Qdrant) ──→ Top 20
    │
    └──→ [BM25 Tokenizer]  ──→ Keyword Retrieval (BM25)       ──→ Top 20
                                                                      │
                                               ┌──────────────────────┘
                                               ▼
                                    Reciprocal Rank Fusion
                                               │
                                               ▼
                                    Deduplicated Candidates (20-30)
                                               │
                                               ▼
                                    Cross-Encoder Reranking
                                               │
                                               ▼
                                    Final Top 5-8 Chunks
```

## 8.2 Dense Retrieval

```python
class DenseRetriever:
    def __init__(self, embedding_model: str = "nomic-embed-text"):
        self.embedder = OllamaEmbedder(model=embedding_model)
        self.index = get_vector_store()  # FAISS or Qdrant

    def retrieve(self, query: str, top_k: int = 20,
                 role_filter: list[str] | None = None) -> list[SearchResult]:
        query_embedding = self.embedder.embed(query)
        return self.index.search(query_embedding, top_k=top_k, role_filter=role_filter)
```

## 8.3 BM25 Keyword Retrieval

```python
from rank_bm25 import BM25Okapi
import nltk

class BM25Retriever:
    def __init__(self):
        self.tokenizer = nltk.word_tokenize
        self.index: BM25Okapi | None = None
        self.chunks: list[ChunkMetadata] = []

    def build_index(self, chunks: list[ChunkMetadata]):
        tokenized = [self.tokenizer(c.text.lower()) for c in chunks]
        self.index = BM25Okapi(tokenized)
        self.chunks = chunks

    def retrieve(self, query: str, top_k: int = 20,
                 role_filter: list[str] | None = None) -> list[SearchResult]:
        tokenized_query = self.tokenizer(query.lower())
        scores = self.index.get_scores(tokenized_query)

        # Sort by score, apply RBAC filter
        scored = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        results = []
        for idx, score in scored:
            chunk = self.chunks[idx]
            if role_filter and not any(r in chunk.access_roles for r in role_filter):
                continue
            results.append(SearchResult(
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                score=score,
                source=chunk.source,
                page=chunk.page,
            ))
            if len(results) >= top_k:
                break
        return results
```

## 8.4 Reciprocal Rank Fusion

```python
def reciprocal_rank_fusion(
    dense_results: list[SearchResult],
    bm25_results: list[SearchResult],
    k: int = 60,
    dense_weight: float = 0.6,
    bm25_weight: float = 0.4,
) -> list[SearchResult]:
    """Merge dense + BM25 results using weighted RRF."""
    scores: dict[str, float] = {}
    chunk_map: dict[str, SearchResult] = {}

    for rank, result in enumerate(dense_results, 1):
        scores[result.chunk_id] = scores.get(result.chunk_id, 0) + dense_weight / (k + rank)
        chunk_map[result.chunk_id] = result

    for rank, result in enumerate(bm25_results, 1):
        scores[result.chunk_id] = scores.get(result.chunk_id, 0) + bm25_weight / (k + rank)
        if result.chunk_id not in chunk_map:
            chunk_map[result.chunk_id] = result

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [chunk_map[chunk_id] for chunk_id, _ in ranked]
```

## 8.5 Cross-Encoder Reranking

```python
from sentence_transformers import CrossEncoder

class Reranker:
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, candidates: list[SearchResult],
               top_n: int = 8) -> list[SearchResult]:
        if not candidates:
            return []
        pairs = [(query, c.text) for c in candidates]
        scores = self.model.predict(pairs)
        scored = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
        return [result for result, _ in scored[:top_n]]
```

---

# SECTION 9 — CONTEXT CONSTRUCTION SPEC

## 9.1 Context Builder

```python
class ContextBuilder:
    def __init__(self, max_tokens: int = 3000):
        self.max_tokens = max_tokens

    def build(self, chunks: list[SearchResult],
              session_context: list[ConversationTurn] | None = None) -> str:
        parts = []
        token_count = 0
        seen_hashes: set[int] = set()

        for chunk in chunks:
            # Deduplication: skip near-identical chunks
            text_hash = hash(chunk.text[:150].lower().strip())
            if text_hash in seen_hashes:
                continue
            seen_hashes.add(text_hash)

            # Relevance floor: skip very low-score chunks
            if chunk.score < 0.15:
                continue

            chunk_tokens = self._estimate_tokens(chunk.text)
            if token_count + chunk_tokens > self.max_tokens:
                break

            parts.append(self._format_chunk(chunk))
            token_count += chunk_tokens

        return "\n\n---\n\n".join(parts)

    def _format_chunk(self, chunk: SearchResult) -> str:
        header = f"[Source: {chunk.source}"
        if chunk.page:
            header += f", Page {chunk.page}"
        header += "]"
        return f"{header}\n{chunk.text.strip()}"

    def _estimate_tokens(self, text: str) -> int:
        return int(len(text.split()) * 1.3)
```

## 9.2 Token Budget Allocation

| Component | Token Budget | Notes |
|-----------|-------------|-------|
| System prompt | 200–300 | Static instructions + guardrails |
| Retrieved context | 2500–3500 | Primary evidence for answer generation |
| Conversation history | 500–800 | Last 3–5 turns for continuity |
| User query | 50–200 | Current question |
| **Total prompt** | **~4000** | Fits 8K context window models |
| Response budget | 1024 | Max generation tokens |

## 9.3 Duplicate Handling

```python
def _is_near_duplicate(text_a: str, text_b: str, threshold: float = 0.85) -> bool:
    """Quick Jaccard similarity check for near-duplicates."""
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a or not words_b:
        return False
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union) > threshold
```

---

# SECTION 10 — LLM INFERENCE SPECIFICATION

## 10.1 Model Gateway

```python
class ModelGateway:
    """Unified interface for local LLM providers."""

    def __init__(self, provider: str = "ollama"):
        self.provider = provider
        self.config = {
            "ollama": {"base_url": "http://localhost:11434", "format": "ollama"},
            "vllm": {"base_url": "http://localhost:8001/v1", "format": "openai"},
        }

    def generate(self, prompt: str, model: str = "llama3:8b",
                 temperature: float = 0.1, max_tokens: int = 1024) -> LLMResponse:
        if self.provider == "ollama":
            return self._ollama_generate(prompt, model, temperature, max_tokens)
        elif self.provider == "vllm":
            return self._vllm_generate(prompt, model, temperature, max_tokens)

    def _ollama_generate(self, prompt, model, temperature, max_tokens) -> LLMResponse:
        import httpx
        resp = httpx.post(
            f"{self.config['ollama']['base_url']}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            },
            timeout=60.0,
        )
        data = resp.json()
        return LLMResponse(
            text=data["response"],
            model=model,
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
        )

    def _vllm_generate(self, prompt, model, temperature, max_tokens) -> LLMResponse:
        import httpx
        resp = httpx.post(
            f"{self.config['vllm']['base_url']}/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=60.0,
        )
        data = resp.json()
        choice = data["choices"][0]
        return LLMResponse(
            text=choice["message"]["content"],
            model=model,
            prompt_tokens=data["usage"]["prompt_tokens"],
            completion_tokens=data["usage"]["completion_tokens"],
        )
```

## 10.2 System Prompt Template

```python
SYSTEM_PROMPT = """You are an HR assistant for {company_name}. Your role is to answer
employee questions accurately using ONLY the provided HR documents.

RULES:
1. Answer ONLY from the provided context. If the context does not contain the answer,
   say "I don't have enough information in our HR documents to answer this question.
   Please contact HR directly at {hr_contact}."
2. Cite your sources using [Source: document name, Page X] format.
3. Be concise, professional, and helpful.
4. Never fabricate policies, dates, numbers, or procedures.
5. If the question involves personal employee data (salary, performance),
   redirect to HR: "For questions about your personal records, please contact HR."
6. For ambiguous questions, ask for clarification before answering.

CONTEXT FROM HR DOCUMENTS:
{context}

CONVERSATION HISTORY:
{conversation_history}
"""
```

## 10.3 Full Prompt Assembly

```python
def assemble_prompt(
    query: str,
    context: str,
    session_turns: list[ConversationTurn],
    company_name: str = "Acme Corp",
    hr_contact: str = "hr@acmecorp.com",
) -> str:
    history = ""
    for turn in session_turns[-5:]:  # Last 5 turns
        role_label = "Employee" if turn.role == "user" else "HR Assistant"
        history += f"{role_label}: {turn.content}\n"

    prompt = SYSTEM_PROMPT.format(
        company_name=company_name,
        hr_contact=hr_contact,
        context=context,
        conversation_history=history or "(Start of conversation)",
    )
    prompt += f"\nEmployee: {query}\nHR Assistant:"
    return prompt
```

## 10.4 Recommended Models

| Model | Size | Context | Use Case | Provider |
|-------|------|---------|----------|----------|
| Llama 3 8B Instruct | 8B | 8K | Primary chat model | Ollama / vLLM |
| Mistral 7B Instruct | 7B | 32K | Long-context queries | Ollama / vLLM |
| Phi-3 Mini | 3.8B | 4K | Fast/simple queries | Ollama |
| Llama 3 70B | 70B | 8K | Complex reasoning | vLLM (multi-GPU) |
| nomic-embed-text | 137M | 8K | Embeddings | Ollama |
| BGE-base-en-v1.5 | 109M | 512 | Embeddings | sentence-transformers |

---

# SECTION 11 — ANSWER VERIFICATION SPEC

## 11.1 Grounding Verification

```python
import re

class AnswerVerifier:
    """Verify that LLM-generated answer is grounded in retrieved evidence."""

    def verify(self, answer: str, chunks: list[SearchResult],
               query: str) -> VerificationResult:
        claims = self._extract_claims(answer)
        verified_claims = []

        for claim in claims:
            evidence = self._find_evidence(claim, chunks)
            verified_claims.append(ClaimVerification(
                claim=claim,
                verified=len(evidence) > 0,
                evidence_chunks=evidence,
                confidence=self._compute_confidence(claim, evidence),
            ))

        faithfulness = (
            sum(1 for c in verified_claims if c.verified) / len(verified_claims)
            if verified_claims else 1.0
        )
        hallucination_risk = 1.0 - faithfulness

        citations = self._extract_citations(answer, chunks)

        return VerificationResult(
            faithfulness_score=round(faithfulness, 3),
            hallucination_risk=round(hallucination_risk, 3),
            verified_claims=verified_claims,
            citations=citations,
            verdict=(
                "grounded" if faithfulness >= 0.8
                else "partially_grounded" if faithfulness >= 0.5
                else "ungrounded"
            ),
        )

    def _extract_claims(self, answer: str) -> list[str]:
        """Split answer into verifiable atomic claims (sentence-level)."""
        sentences = re.split(r"(?<=[.!?])\s+", answer)
        return [s.strip() for s in sentences if len(s.strip()) > 20]

    def _find_evidence(self, claim: str, chunks: list[SearchResult]) -> list[str]:
        """Find chunks that support the claim via word overlap."""
        claim_words = set(re.findall(r"\b\w{4,}\b", claim.lower()))
        supporting = []
        for chunk in chunks:
            chunk_words = set(re.findall(r"\b\w{4,}\b", chunk.text.lower()))
            overlap = claim_words & chunk_words
            if len(overlap) >= 3:
                supporting.append(chunk.chunk_id)
        return supporting

    def _compute_confidence(self, claim: str, evidence: list[str]) -> float:
        if not evidence:
            return 0.0
        return min(1.0, len(evidence) * 0.3 + 0.4)

    def _extract_citations(self, answer: str,
                           chunks: list[SearchResult]) -> list[Citation]:
        """Extract [Source: ...] references from the answer."""
        citations = []
        source_refs = re.findall(r"\[Source:\s*([^\]]+)\]", answer)
        for ref in source_refs:
            for chunk in chunks:
                if chunk.source in ref:
                    citations.append(Citation(
                        source=chunk.source,
                        page=chunk.page,
                        text_excerpt=chunk.text[:200],
                    ))
                    break
        return citations
```

## 11.2 Ungrounded Answer Handling

```python
def handle_ungrounded_answer(result: VerificationResult, answer: str) -> str:
    """Prepend a disclaimer if answer is not fully grounded."""
    if result.verdict == "ungrounded":
        return (
            "⚠️ I was unable to find sufficient evidence in our HR documents "
            "to fully answer this question. Please verify with HR directly.\n\n"
            + answer
        )
    if result.verdict == "partially_grounded":
        return (
            "ℹ️ Note: Parts of this answer may not be fully supported by our "
            "HR documents. Sources are cited where available.\n\n"
            + answer
        )
    return answer
```

---

# SECTION 12 — SESSION MANAGEMENT SPEC

## 12.1 Session Data Model

```python
@dataclass
class ConversationTurn:
    role: str           # "user" | "assistant"
    content: str
    timestamp: float
    metadata: dict | None = None  # retrieval stats, confidence, etc.

@dataclass
class Session:
    session_id: str     # UUID
    user_id: str
    user_role: str      # "employee" | "manager" | "hr_admin"
    turns: list[ConversationTurn]
    created_at: float
    last_active: float
    metadata: dict      # custom session-level data
```

## 12.2 Session Storage

```python
class SessionStore:
    """SQLite-backed session storage."""

    def __init__(self, db_path: str = "./sessions.db"):
        self.db_path = db_path
        self._init_tables()

    def _init_tables(self):
        with sqlite3.connect(self.db_path) as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id   TEXT PRIMARY KEY,
                    user_id      TEXT NOT NULL,
                    user_role    TEXT NOT NULL,
                    created_at   REAL NOT NULL,
                    last_active  REAL NOT NULL,
                    metadata     TEXT DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS turns (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id   TEXT NOT NULL REFERENCES sessions(session_id),
                    role         TEXT NOT NULL,
                    content      TEXT NOT NULL,
                    timestamp    REAL NOT NULL,
                    metadata     TEXT DEFAULT '{}',
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                );
                CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id);
            """)

    def create_session(self, user_id: str, user_role: str) -> Session:
        session_id = str(uuid.uuid4())
        now = time.time()
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT INTO sessions (session_id, user_id, user_role, created_at, last_active) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, user_id, user_role, now, now),
            )
        return Session(session_id=session_id, user_id=user_id, user_role=user_role,
                       turns=[], created_at=now, last_active=now, metadata={})

    def add_turn(self, session_id: str, role: str, content: str):
        now = time.time()
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT INTO turns (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                (session_id, role, content, now),
            )
            con.execute(
                "UPDATE sessions SET last_active = ? WHERE session_id = ?",
                (now, session_id),
            )

    def get_recent_turns(self, session_id: str, limit: int = 5) -> list[ConversationTurn]:
        with sqlite3.connect(self.db_path) as con:
            rows = con.execute(
                "SELECT role, content, timestamp FROM turns "
                "WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [ConversationTurn(role=r[0], content=r[1], timestamp=r[2]) for r in reversed(rows)]
```

## 12.3 Context Retention Strategy

| Turn Window | Use Case |
|------------|----------|
| Last 3 turns | Injected into LLM prompt as conversation context |
| Last 5 turns | Available for query reformulation / anaphora resolution |
| Full session | Stored in DB for analytics, not injected into prompt |

```python
def inject_session_context(query: str, recent_turns: list[ConversationTurn]) -> str:
    """Rewrite query using session context to resolve references."""
    # If query contains pronouns like "it", "that", "this policy"
    # and recent turns mention a specific topic, prepend context
    if any(word in query.lower() for word in ["it", "that", "this", "those", "these"]):
        last_assistant = next(
            (t for t in reversed(recent_turns) if t.role == "assistant"), None
        )
        if last_assistant:
            return f"(Context: previous answer discussed: {last_assistant.content[:200]})\n{query}"
    return query
```

---

# SECTION 13 — ROLE-BASED ACCESS CONTROL SPEC

## 13.1 Role Hierarchy

```
hr_admin (full access)
    └── manager (employee + manager docs)
        └── employee (general docs only)
```

## 13.2 Document Access Matrix

| Document Category | Employee | Manager | HR Admin |
|-------------------|----------|---------|----------|
| Employee Handbook | ✅ | ✅ | ✅ |
| General HR Policies | ✅ | ✅ | ✅ |
| Benefits Documentation | ✅ | ✅ | ✅ |
| Leave Policies | ✅ | ✅ | ✅ |
| Onboarding Materials | ✅ | ✅ | ✅ |
| Manager Guidelines | ❌ | ✅ | ✅ |
| Performance Review Procedures | ❌ | ✅ | ✅ |
| Compensation Band Data | ❌ | ✅ | ✅ |
| Termination Procedures | ❌ | ✅ | ✅ |
| Internal HR Audit Reports | ❌ | ❌ | ✅ |
| Legal Compliance Documents | ❌ | ❌ | ✅ |
| HR System Configuration | ❌ | ❌ | ✅ |

## 13.3 RBAC Enforcement Points

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  API Layer   │ ──→ │  Retrieval   │ ──→ │  Response    │
│  JWT → Role  │     │  RBAC Filter │     │  Audit Log   │
└──────────────┘     └──────────────┘     └──────────────┘
```

**Point 1 — API Authentication:**
```python
def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    return User(
        user_id=payload["sub"],
        role=payload["role"],     # "employee" | "manager" | "hr_admin"
        department=payload.get("department"),
    )
```

**Point 2 — Retrieval Filter:**
```python
ROLE_HIERARCHY = {
    "employee": ["employee"],
    "manager": ["employee", "manager"],
    "hr_admin": ["employee", "manager", "hr_admin"],
}

def get_allowed_roles(user_role: str) -> list[str]:
    return ROLE_HIERARCHY.get(user_role, ["employee"])

# Applied in every vector search:
results = vector_store.search(
    query_embedding=embedding,
    top_k=20,
    role_filter=get_allowed_roles(user.role),
)
```

**Point 3 — Audit Logging:**
```python
def log_access(user: User, query: str, chunks_accessed: list[str]):
    audit_logger.info(
        "document_access",
        user_id=user.user_id,
        role=user.role,
        query=query,
        chunks_accessed=chunks_accessed,
        timestamp=time.time(),
    )
```

## 13.4 Role Assignment

```python
# JWT payload structure
{
    "sub": "user-12345",
    "role": "manager",
    "department": "Engineering",
    "exp": 1710000000,
    "iat": 1709913600,
}
```

Roles are assigned via the company's identity provider (LDAP / SSO / Azure AD) and embedded in the JWT at login time.

---

# SECTION 14 — MULTI-AGENT REASONING ARCHITECTURE (ADVANCED)

## 14.1 Agent Architecture

```
User Query
    │
    ▼
┌──────────────────────────────────────────────────┐
│               ORCHESTRATOR                        │
│  Routes query through agents based on complexity  │
└──┬────────┬────────┬────────┬────────┬───────────┘
   │        │        │        │        │
   ▼        ▼        ▼        ▼        ▼
┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐
│Query ││Research││Reason││Verify││Critic│
│Agent ││Agent  ││Agent ││Agent ││Agent │
└──────┘└──────┘└──────┘└──────┘└──────┘
```

## 14.2 Agent Specifications

### Agent 1: Query Analysis Agent

```yaml
purpose: Classify query, estimate complexity, generate sub-queries
input: raw user query + session context
output: ReasoningPlan
  - query_type: factual | policy_lookup | comparative | procedural | multi_hop
  - complexity: simple | moderate | complex
  - sub_queries: list[string]
  - required_domains: list[string]
  - strategy: fast | standard | deep
logic: Heuristic classification via regex + keyword matching (no LLM required)
```

### Agent 2: Research Agent

```yaml
purpose: Execute retrieval for each sub-query, assemble evidence
input: ReasoningPlan
output: EvidenceBundle
  - items: list[EvidenceItem]
  - gaps: list[string]  # sub-queries with insufficient results
  - coverage_score: float
logic: Run hybrid retrieval per sub-query, deduplicate, detect gaps
```

### Agent 3: Reasoning Agent

```yaml
purpose: Interpret evidence, apply HR rules, draft conclusion
input: ReasoningPlan + EvidenceBundle
output: ReasoningTrace
  - conclusion: string
  - reasoning_steps: list[string]
  - applicable_rules: list[string]
  - confidence: float
  - uncertainty_flags: list[string]
logic: Pattern-match HR rules against evidence, build step-by-step reasoning
```

### Agent 4: Verification Agent

```yaml
purpose: Verify claims against evidence, detect contradictions
input: ReasoningTrace + EvidenceBundle
output: ValidationReport
  - faithfulness_score: float
  - hallucination_risk: float
  - contradictions: list[string]
  - unsupported_claims: list[string]
logic: Word-overlap claim verification + contradiction pair detection
```

### Agent 5: Critic Agent

```yaml
purpose: Adversarial review — find logical gaps, overconfident language, missing nuance
input: ReasoningTrace + ValidationReport
output: CritiqueReport
  - findings: list[CritiqueFinding]
  - overall_quality: float
  - confidence_adjustment: float
  - requires_revision: bool
logic: Check for definitive language with low faithfulness, missing caveats, scope issues
```

## 14.3 Orchestration Flow

```python
class MultiAgentOrchestrator:
    def run(self, query: str, user_role: str) -> MultiAgentResult:
        # Agent 1: Classify and plan
        plan = QueryAnalysisAgent().analyze(query)

        # Fast path: simple factual queries skip multi-agent
        if plan.complexity == "simple" and plan.strategy == "fast":
            return self._fast_path(query, user_role, plan)

        # Agent 2: Research
        bundle = ResearchAgent().research(plan, role_filter=get_allowed_roles(user_role))

        # Agent 3: Reason
        trace = ReasoningAgent().reason(plan, bundle)

        # Agent 4: Verify
        validation = VerificationAgent().validate(trace, bundle)

        # Agent 5: Critique (only for complex queries)
        if plan.complexity == "complex":
            critique = CriticAgent().critique(trace, validation)
        else:
            critique = CritiqueReport(overall_quality=0.8)

        # Synthesize final answer
        return self._synthesize(plan, bundle, trace, validation, critique)
```

## 14.4 When to Use Multi-Agent

| Query Type | Strategy | Agents Used |
|-----------|----------|-------------|
| "What is our vacation policy?" | fast | Agent 1 → standard RAG pipeline |
| "How do I apply for FMLA leave?" | standard | Agent 1 → 2 → 3 → 4 |
| "Compare our maternity leave vs FMLA" | deep | All 5 agents |
| "What happens if I exhaust PTO and need more time off?" | deep | All 5 agents |

---

# SECTION 15 — EVALUATION FRAMEWORK

## 15.1 Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Retrieval Precision@5 | > 0.80 | Fraction of top-5 chunks that are relevant |
| Answer Faithfulness | > 0.93 | Claim-vs-evidence grounding verification |
| Hallucination Rate | < 0.05 | Fraction of claims without evidence support |
| Latency P50 | < 1.5s | End-to-end response time |
| Latency P95 | < 3.0s | End-to-end response time |
| User Satisfaction | > 4.0/5 | Feedback thumbs up/down + periodic surveys |

## 15.2 Evaluation Dataset

```python
@dataclass
class EvalQuery:
    query: str
    expected_keywords: list[str]       # keywords that MUST appear in answer
    expected_sources: list[str]        # document names that should be retrieved
    query_type: str                    # factual | policy | comparative | procedural
    difficulty: str                    # easy | medium | hard
    role: str                          # which role should be used for testing

# Example dataset
EVAL_DATASET = [
    EvalQuery(
        query="How many vacation days do new employees get?",
        expected_keywords=["vacation", "days", "new", "employee"],
        expected_sources=["Employee Handbook", "Leave Policy"],
        query_type="factual",
        difficulty="easy",
        role="employee",
    ),
    EvalQuery(
        query="Compare our short-term and long-term disability benefits",
        expected_keywords=["short-term", "long-term", "disability", "coverage"],
        expected_sources=["Benefits Guide"],
        query_type="comparative",
        difficulty="medium",
        role="employee",
    ),
    EvalQuery(
        query="What is the process for placing an employee on a performance improvement plan?",
        expected_keywords=["PIP", "performance", "improvement", "plan"],
        expected_sources=["Manager Guidelines", "Performance Review Policy"],
        query_type="procedural",
        difficulty="medium",
        role="manager",
    ),
]
```

## 15.3 Automated Evaluation Runner

```python
class EvalRunner:
    def __init__(self, pipeline: RAGPipeline, dataset: list[EvalQuery]):
        self.pipeline = pipeline
        self.dataset = dataset

    def run(self) -> EvalReport:
        results = []
        for eq in self.dataset:
            t0 = time.time()
            response = self.pipeline.query(
                query=eq.query,
                user_role=eq.role,
            )
            latency_ms = (time.time() - t0) * 1000

            # Check retrieval precision
            retrieved_sources = {c.source for c in response.chunks}
            expected_sources = set(eq.expected_sources)
            retrieval_hit = len(retrieved_sources & expected_sources) / max(1, len(expected_sources))

            # Check keyword presence
            answer_lower = response.answer.lower()
            keyword_hits = sum(1 for kw in eq.expected_keywords if kw.lower() in answer_lower)
            keyword_score = keyword_hits / max(1, len(eq.expected_keywords))

            results.append(EvalResult(
                query=eq.query,
                retrieval_precision=retrieval_hit,
                keyword_score=keyword_score,
                faithfulness=response.verification.faithfulness_score,
                hallucination_risk=response.verification.hallucination_risk,
                latency_ms=latency_ms,
            ))

        return self._aggregate(results)
```

## 15.4 Evaluation Schedule

| Frequency | Trigger | Scope |
|-----------|---------|-------|
| On every deploy | CI/CD pipeline | Full eval dataset (~50 queries) |
| Daily (automated) | Cron job | Random sample of 20 queries |
| Weekly | Manual review | Full dataset + new edge cases |
| On document upload | Ingestion hook | Affected document queries only |

---

# SECTION 16 — AUTOTUNING AND CONTINUOUS IMPROVEMENT

## 16.1 Feedback Loop Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Query Logs  │ ──→ │  Diagnostic  │ ──→ │  Parameter   │
│  + Feedback  │     │  Analyzer    │     │  Optimizer   │
└──────────────┘     └──────────────┘     └──────────────┘
       │                    │                     │
       ▼                    ▼                     ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Failed      │     │  Retrieval   │     │  A/B Test    │
│  Queries     │     │  Gap Report  │     │  New Config  │
│  Dashboard   │     │              │     │              │
└──────────────┘     └──────────────┘     └──────────────┘
```

## 16.2 What Gets Tuned

| Parameter | Range | Default | Impact |
|-----------|-------|---------|--------|
| `dense_top_k` | 10–50 | 20 | Recall vs. noise trade-off |
| `bm25_top_k` | 10–50 | 20 | Keyword match coverage |
| `rerank_top_n` | 3–15 | 8 | Context quality vs. diversity |
| `chunk_size` | 300–800 | 450 | Retrieval granularity |
| `chunk_overlap` | 25–100 | 60 | Boundary coverage |
| `dense_weight` (RRF) | 0.3–0.8 | 0.6 | Dense vs. keyword balance |
| `temperature` | 0.0–0.3 | 0.1 | Answer creativity vs. safety |
| `max_context_tokens` | 2000–4000 | 3000 | Evidence quantity |

## 16.3 Diagnostic Queries

```python
class QueryDiagnostics:
    """Analyze failed queries to identify improvement opportunities."""

    def analyze_failures(self, failed_queries: list[FailedQuery]) -> DiagnosticReport:
        categories = {
            "no_relevant_chunks": [],     # retrieval found nothing useful
            "low_faithfulness": [],        # answer not grounded
            "high_latency": [],            # exceeded P95 target
            "user_negative_feedback": [],  # thumbs down
        }

        for fq in failed_queries:
            if fq.top_chunk_score < 0.3:
                categories["no_relevant_chunks"].append(fq)
            if fq.faithfulness_score < 0.7:
                categories["low_faithfulness"].append(fq)
            if fq.latency_ms > 3000:
                categories["high_latency"].append(fq)
            if fq.user_feedback == "negative":
                categories["user_negative_feedback"].append(fq)

        return DiagnosticReport(
            total_failures=len(failed_queries),
            by_category=categories,
            recommendations=self._generate_recommendations(categories),
        )

    def _generate_recommendations(self, categories) -> list[str]:
        recs = []
        if len(categories["no_relevant_chunks"]) > 5:
            recs.append("Consider reducing chunk_size for finer-grained retrieval")
            recs.append("Check if missing documents need to be ingested")
        if len(categories["low_faithfulness"]) > 5:
            recs.append("Increase rerank_top_n to provide more evidence to LLM")
            recs.append("Lower temperature to reduce creative generation")
        if len(categories["high_latency"]) > 5:
            recs.append("Reduce dense_top_k and bm25_top_k to lower retrieval time")
            recs.append("Consider using a smaller/faster LLM for simple queries")
        return recs
```

## 16.4 Continuous Improvement Cycle

```
1. Collect query logs + user feedback (daily)
2. Run diagnostic analysis (weekly automated)
3. Identify parameter adjustment candidates
4. Run evaluation suite with candidate config
5. Compare against baseline metrics
6. If improvement confirmed → deploy new config
7. Monitor for regression for 48 hours
8. Promote to permanent config or rollback
```

---

# SECTION 17 — SECURITY SPECIFICATION

## 17.1 Authentication

```python
# JWT configuration
JWT_CONFIG = {
    "secret_key": os.environ["JWT_SECRET_KEY"],   # 256-bit minimum
    "algorithm": "HS256",
    "access_token_expire_minutes": 480,            # 8 hours (business day)
    "refresh_token_expire_days": 30,
}

# Token validation middleware
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def validate_token(credentials = Depends(security)) -> User:
    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_CONFIG["secret_key"],
            algorithms=[JWT_CONFIG["algorithm"]],
        )
        return User(
            user_id=payload["sub"],
            role=payload["role"],
            department=payload.get("department"),
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

## 17.2 Prompt Injection Defense

```python
INJECTION_PATTERNS = [
    r"ignore\s+(previous|above|all)\s+(instructions|rules|prompts)",
    r"you\s+are\s+now\s+a",
    r"pretend\s+(to\s+be|you\s+are)",
    r"system\s*prompt",
    r"<\s*/?\s*system\s*>",
    r"\\n\\nHuman:",
    r"forget\s+(everything|all|your\s+instructions)",
    r"jailbreak",
    r"DAN\s+mode",
]

def check_prompt_injection(query: str) -> bool:
    """Return True if injection attempt detected."""
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            return True
    return False

# In the chat endpoint:
if check_prompt_injection(query):
    return ChatResponse(
        answer="I can only answer HR-related questions. Please rephrase your question.",
        confidence=0.0,
        flagged=True,
    )
```

## 17.3 Data Privacy

| Control | Implementation |
|---------|---------------|
| PII in queries | Log queries with hashed user IDs only |
| Document access | RBAC filter at retrieval + audit log |
| Data at rest | SQLite/Postgres encryption at filesystem level |
| Data in transit | TLS 1.2+ for all API communications |
| Model isolation | Local models only — no external API calls |
| Session data | Auto-expire after 30 days, user can delete |

## 17.4 Audit Logging

```python
import structlog

audit_logger = structlog.get_logger("audit")

def log_chat_interaction(user: User, query: str, response: ChatResponse):
    audit_logger.info(
        "chat_interaction",
        user_id=user.user_id,
        role=user.role,
        query_hash=hashlib.sha256(query.encode()).hexdigest()[:16],
        chunks_accessed=[c.chunk_id for c in response.chunks],
        faithfulness=response.verification.faithfulness_score,
        latency_ms=response.latency_ms,
        flagged=response.flagged,
    )

def log_document_upload(user: User, doc: DocumentMetadata):
    audit_logger.info(
        "document_upload",
        user_id=user.user_id,
        document_id=doc.document_id,
        category=doc.category,
        access_roles=doc.access_roles,
        filename=doc.source_filename,
    )
```

---

# SECTION 18 — OBSERVABILITY SPEC

## 18.1 Structured Logging

```python
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()

# Usage in RAG pipeline:
logger.info("retrieval_complete",
    query_id=query_id,
    dense_results=len(dense_results),
    bm25_results=len(bm25_results),
    reranked_count=len(reranked),
    top_score=reranked[0].score if reranked else 0,
    latency_ms=retrieval_latency_ms,
)
```

## 18.2 Prometheus Metrics

```python
from prometheus_client import Counter, Histogram, Gauge

# Counters
chat_queries_total = Counter("hr_chat_queries_total", "Total chat queries", ["role", "query_type"])
hallucination_flags_total = Counter("hr_hallucination_flags_total", "Hallucination flags")
auth_failures_total = Counter("hr_auth_failures_total", "Authentication failures")

# Histograms
query_latency = Histogram("hr_query_latency_seconds", "Query latency",
                          buckets=[0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0])
retrieval_latency = Histogram("hr_retrieval_latency_seconds", "Retrieval latency")
faithfulness_score = Histogram("hr_faithfulness_score", "Faithfulness distribution",
                               buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])

# Gauges
active_sessions = Gauge("hr_active_sessions", "Currently active sessions")
indexed_chunks = Gauge("hr_indexed_chunks_total", "Total indexed chunks")
```

## 18.3 Health Endpoint

```python
@app.get("/health")
def health_check():
    checks = {}

    # Vector store
    try:
        vector_store.search(np.zeros(768), top_k=1)
        checks["vector_store"] = "ok"
    except Exception as e:
        checks["vector_store"] = f"error: {e}"

    # LLM gateway
    try:
        model_gateway.generate("test", max_tokens=1)
        checks["llm_gateway"] = "ok"
    except Exception as e:
        checks["llm_gateway"] = f"error: {e}"

    # Database
    try:
        with sqlite3.connect(DB_PATH) as con:
            con.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    overall = "operational" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}
```

## 18.4 Dashboard Metrics

| Panel | Metric | Alert Threshold |
|-------|--------|----------------|
| Query Volume | queries/minute by role | > 200 qpm |
| Latency P50/P95 | seconds | P95 > 3s |
| Faithfulness | avg score over 1hr | < 0.85 |
| Hallucination Rate | flagged / total | > 0.08 |
| Error Rate | 5xx / total | > 0.02 |
| Active Sessions | gauge | > 500 concurrent |
| Vector Index Size | chunk count | operational metric |
| LLM Token Usage | tokens/hour | cost tracking |

---

# SECTION 19 — DEPLOYMENT ARCHITECTURE

## 19.1 Infrastructure Topology

```
                    ┌─────────────────────────────────────────┐
                    │            LOAD BALANCER                 │
                    │         (nginx / HAProxy)                │
                    └──────────┬──────────┬───────────────────┘
                               │          │
                    ┌──────────▼──┐ ┌─────▼──────────┐
                    │  API Server │ │  API Server    │
                    │  (FastAPI)  │ │  (FastAPI)     │
                    │  Port 8000  │ │  Port 8000     │
                    └──────┬──────┘ └─────┬──────────┘
                           │              │
              ┌────────────┼──────────────┼────────────┐
              │            │              │            │
    ┌─────────▼──┐  ┌──────▼─────┐  ┌────▼────┐  ┌───▼──────┐
    │  Vector    │  │  LLM       │  │  Redis  │  │ Postgres │
    │  Store     │  │  Gateway   │  │  Cache  │  │  (Meta)  │
    │  (Qdrant)  │  │  (vLLM)   │  │         │  │          │
    │  Port 6333 │  │  Port 8001 │  │  :6379  │  │  :5432   │
    └────────────┘  └────────────┘  └─────────┘  └──────────┘
```

## 19.2 Container Definitions

```yaml
# docker-compose.yml
version: "3.9"

services:
  api:
    build: .
    ports: ["8000:8000"]
    environment:
      - LLM_PROVIDER=vllm
      - VLLM_BASE_URL=http://llm:8001/v1
      - VECTOR_STORE_BACKEND=qdrant
      - QDRANT_URL=http://qdrant:6333
      - REDIS_URL=redis://redis:6379
      - DB_URL=postgresql://hr:pass@postgres:5432/hrchat
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
    depends_on: [qdrant, llm, redis, postgres]
    deploy:
      replicas: 2
      resources:
        limits: { cpus: "2", memory: "4G" }

  llm:
    image: vllm/vllm-openai:latest
    ports: ["8001:8001"]
    command: >
      --model meta-llama/Meta-Llama-3-8B-Instruct
      --tensor-parallel-size 1
      --max-model-len 8192
    deploy:
      resources:
        reservations: { devices: [{ driver: nvidia, count: 1, capabilities: [gpu] }] }

  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6333:6333"]
    volumes: ["qdrant_data:/qdrant/storage"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: hrchat
      POSTGRES_USER: hr
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes: ["pg_data:/var/lib/postgresql/data"]

volumes:
  qdrant_data:
  pg_data:
```

## 19.3 Scaling Strategy

| Component | Scaling Approach | Trigger |
|-----------|-----------------|---------|
| API Server | Horizontal (add replicas) | CPU > 70% or QPS > 100/instance |
| LLM Gateway | Vertical (bigger GPU) or horizontal (multi-GPU) | Queue depth > 10 |
| Vector Store | Qdrant cluster sharding | Index > 5M chunks |
| Redis | Sentinel for HA | Failover requirement |
| PostgreSQL | Read replicas | Read QPS > 1000 |

## 19.4 Resource Estimates (5k Users)

| Component | CPU | RAM | GPU | Storage |
|-----------|-----|-----|-----|---------|
| API Server (×2) | 2 cores each | 4 GB each | — | — |
| LLM (vLLM, Llama 3 8B) | 4 cores | 16 GB | 1× A10G/L4 (24GB) | — |
| Qdrant | 2 cores | 8 GB | — | 50 GB SSD |
| Redis | 1 core | 2 GB | — | — |
| PostgreSQL | 2 cores | 4 GB | — | 20 GB SSD |
| **Total** | **13 cores** | **38 GB** | **1 GPU** | **70 GB** |

---

# SECTION 20 — API CONTRACT SPECIFICATION

## 20.1 Chat Endpoints

### POST /chat/query

```json
// Request
{
    "query": "How many vacation days do I get as a new employee?",
    "session_id": "uuid-or-null",     // null = create new session
    "include_sources": true,
    "include_trace": false
}

// Response
{
    "answer": "As a new employee, you receive 15 paid vacation days per year...",
    "session_id": "a1b2c3d4-...",
    "citations": [
        {
            "source": "Employee Handbook v2024",
            "page": 23,
            "excerpt": "New employees are entitled to 15 days of paid time off..."
        }
    ],
    "confidence": 0.92,
    "faithfulness_score": 0.95,
    "query_type": "factual",
    "latency_ms": 1240
}
```

### GET /chat/sessions

```json
// Response
{
    "sessions": [
        {
            "session_id": "a1b2c3d4-...",
            "created_at": "2024-03-15T10:30:00Z",
            "last_active": "2024-03-15T11:45:00Z",
            "turn_count": 8,
            "preview": "How many vacation days..."
        }
    ],
    "count": 5
}
```

### GET /chat/sessions/{session_id}/history

```json
// Response
{
    "session_id": "a1b2c3d4-...",
    "turns": [
        { "role": "user", "content": "How many vacation days?", "timestamp": 1710500000 },
        { "role": "assistant", "content": "As a new employee...", "timestamp": 1710500002 }
    ],
    "count": 8
}
```

## 20.2 Document Management Endpoints

### POST /documents/upload

```json
// Request (multipart/form-data)
// file: binary
// metadata: JSON string
{
    "title": "Employee Handbook 2024",
    "category": "handbook",
    "access_roles": ["employee", "manager", "hr_admin"],
    "effective_date": "2024-01-01",
    "version": "2024.1"
}

// Response
{
    "document_id": "d5e6f7g8-...",
    "chunk_count": 142,
    "status": "indexed",
    "processing_time_ms": 8500
}
```

### POST /documents/reindex

```json
// Request
{
    "document_id": "d5e6f7g8-...",   // optional — null = reindex all
    "force": false
}

// Response
{
    "documents_reindexed": 1,
    "total_chunks": 142,
    "status": "complete",
    "duration_ms": 12000
}
```

### GET /documents

```json
// Response
{
    "documents": [
        {
            "document_id": "d5e6f7g8-...",
            "title": "Employee Handbook 2024",
            "category": "handbook",
            "access_roles": ["employee", "manager", "hr_admin"],
            "chunk_count": 142,
            "uploaded_at": "2024-03-10T09:00:00Z",
            "version": "2024.1"
        }
    ],
    "count": 12
}
```

## 20.3 Admin Endpoints

### GET /admin/metrics

```json
// Response
{
    "queries_today": 342,
    "queries_this_week": 1850,
    "avg_latency_ms": 1150,
    "avg_faithfulness": 0.94,
    "hallucination_rate": 0.03,
    "active_sessions": 28,
    "total_documents": 12,
    "total_chunks": 2840,
    "top_query_topics": [
        { "topic": "leave", "count": 89 },
        { "topic": "benefits", "count": 67 },
        { "topic": "onboarding", "count": 45 }
    ]
}
```

### GET /admin/failed-queries

```json
// Response
{
    "failed_queries": [
        {
            "query": "What is the RSU vesting schedule?",
            "failure_reason": "no_relevant_chunks",
            "faithfulness_score": 0.2,
            "timestamp": "2024-03-15T14:30:00Z",
            "recommendation": "Ingest compensation/equity documentation"
        }
    ],
    "count": 5
}
```

### POST /admin/eval/run

```json
// Request
{
    "dataset": "default",     // or custom dataset name
    "sample_size": 50
}

// Response
{
    "eval_id": "e1f2g3h4-...",
    "status": "running",
    "estimated_duration_seconds": 120
}
```

### GET /admin/eval/{eval_id}

```json
// Response
{
    "eval_id": "e1f2g3h4-...",
    "status": "complete",
    "metrics": {
        "retrieval_precision": 0.84,
        "answer_faithfulness": 0.94,
        "hallucination_rate": 0.03,
        "latency_p50_ms": 1100,
        "latency_p95_ms": 2400,
        "keyword_match_rate": 0.88
    },
    "per_query_results": [ ... ]
}
```

## 20.4 Auth Endpoints

### POST /auth/login

```json
// Request
{
    "username": "john.doe",
    "password": "..."
}

// Response
{
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "expires_in": 28800,
    "user": {
        "user_id": "user-12345",
        "role": "manager",
        "department": "Engineering"
    }
}
```

### GET /health

```json
{
    "status": "operational",
    "checks": {
        "vector_store": "ok",
        "llm_gateway": "ok",
        "database": "ok",
        "redis": "ok"
    },
    "version": "1.0.0"
}
```

---

# SECTION 21 — DEVELOPMENT ROADMAP

## Phase 1 — Baseline HR RAG Chatbot (Weeks 1–3)

| Task | Deliverable |
|------|------------|
| Project scaffold | FastAPI app, config, health endpoint |
| Document ingestion | PDF/DOCX/MD/TXT loader + text extraction |
| Fixed-size chunking | Basic chunking with overlap |
| Embedding service | Ollama `nomic-embed-text` integration |
| FAISS vector store | In-memory index with persistence |
| Dense retrieval | Basic similarity search |
| LLM integration | Ollama `llama3:8b` chat completion |
| Simple prompt template | System prompt + context + query |
| Basic chat API | `POST /chat/query` endpoint |
| Session storage | SQLite session + turn persistence |
| JWT authentication | Token validation middleware |
| Basic RBAC | Role-based document filtering |

**Exit criteria:** Employee can ask a question and get a sourced answer from uploaded HR docs.

## Phase 2 — Hybrid Retrieval + Quality (Weeks 4–6)

| Task | Deliverable |
|------|------------|
| BM25 index | `rank_bm25` keyword search |
| Hybrid retrieval | RRF fusion of dense + BM25 |
| Cross-encoder reranking | `ms-marco-MiniLM` reranker |
| Heading-aware chunking | Section-preserving chunker for HR docs |
| Answer verification | Claim-vs-evidence grounding checker |
| Citation extraction | Source references in answers |
| Conversation context | Session history injected into prompts |
| Document management API | Upload, list, delete, reindex |
| RBAC enforcement hardening | Audit logging, access matrix |

**Exit criteria:** Measurably better retrieval precision and faithfulness vs Phase 1.

## Phase 3 — Evaluation Framework (Weeks 7–8)

| Task | Deliverable |
|------|------------|
| Eval dataset | 50+ annotated HR queries |
| Eval runner | Automated benchmark suite |
| Metrics dashboard | Faithfulness, hallucination, latency tracking |
| Regression testing | CI/CD eval gate (fail deploy if metrics drop) |
| User feedback loop | Thumbs up/down on answers |
| Failed query diagnostics | Admin dashboard for low-quality answers |

**Exit criteria:** Automated eval runs on every deploy, metrics tracked over time.

## Phase 4 — Multi-Agent Reasoning (Weeks 9–11)

| Task | Deliverable |
|------|------------|
| Query analysis agent | Classification, decomposition |
| Research agent | Multi-sub-query retrieval |
| Reasoning agent | Evidence interpretation, conclusion drafting |
| Verification agent | Claim verification, contradiction detection |
| Critic agent | Adversarial quality review |
| Orchestrator | Agent pipeline with skip-logic for simple queries |

**Exit criteria:** Complex multi-hop HR questions answered with higher accuracy.

## Phase 5 — Autonomous Optimization (Weeks 12–14)

| Task | Deliverable |
|------|------------|
| Query log analysis | Failure categorization |
| Parameter space definition | Tunable RAG parameters |
| A/B testing framework | Compare configs on eval dataset |
| Auto-tuning loop | Suggest and test parameter changes |
| Safe deployment | Canary rollout with safety gates |
| Continuous monitoring | Alerting on metric regression |

**Exit criteria:** System self-identifies and fixes retrieval quality issues.

---

# SECTION 22 — BEST PRACTICES

## 22.1 Prompt Engineering

```
DO:
  ✓ Include explicit "answer ONLY from context" instruction
  ✓ Require citation format in the system prompt
  ✓ Add "if unknown, say so" fallback instruction
  ✓ Keep temperature at 0.1 for factual HR answers
  ✓ Include the user's role context ("You are helping a [role]")

DON'T:
  ✗ Use temperature > 0.3 for HR queries (increases hallucination)
  ✗ Allow the model to "reason beyond" the provided documents
  ✗ Include example Q&As in the system prompt (wastes token budget)
  ✗ Let the prompt exceed 40% of the context window
```

## 22.2 Retrieval Tuning

```
START WITH:
  dense_top_k: 20, bm25_top_k: 20, rerank_top_n: 8
  dense_weight: 0.6, bm25_weight: 0.4 (in RRF)

TUNE WHEN:
  - Low recall → increase top_k values
  - Noisy results → decrease top_k, increase rerank_top_n
  - Acronym/exact-term misses → increase bm25_weight
  - Semantic misses → increase dense_weight
  - Slow latency → decrease top_k values

MEASURE:
  - Retrieval Precision@5 (target > 0.80)
  - Check that expected source docs appear in top 5
```

## 22.3 Chunking Optimization

```
RULES OF THUMB:
  - 400–512 tokens per chunk is optimal for most HR docs
  - Always use heading-aware chunking for policy documents
  - 50–75 token overlap prevents mid-sentence splits
  - Prepend section heading to every chunk for context
  - Discard chunks under 50 tokens (noise)

VALIDATE:
  - Sample 10 random chunks → are they self-contained and meaningful?
  - Search for a known policy question → does the right chunk appear in top 3?
  - Check chunk boundaries → do they split mid-sentence or mid-list?
```

## 22.4 Testing Strategy

```
UNIT TESTS:
  - Chunking produces expected number of chunks with correct metadata
  - RBAC filter excludes/includes correct roles
  - Session store creates/retrieves/updates correctly
  - Prompt assembly includes all components within token budget
  - Injection detection catches known patterns

INTEGRATION TESTS:
  - Full pipeline: query → retrieval → generation → verification
  - Document upload → chunks indexed → retrievable
  - Session continuity: multi-turn conversation maintains context
  - RBAC: employee cannot access manager-only documents

EVALUATION TESTS (CI/CD gate):
  - Run eval dataset on every deploy
  - Fail deploy if faithfulness < 0.90
  - Fail deploy if hallucination_rate > 0.08
  - Alert if latency P95 > 3.5s
```

## 22.5 Common Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| Chunks too large | Retrieval returns relevant doc but wrong section | Reduce chunk_size to 400 |
| Chunks too small | LLM lacks context to generate useful answer | Increase chunk_size to 500 |
| No heading context | LLM misinterprets chunk meaning | Prepend section heading |
| BM25 disabled | Misses acronyms ("PTO", "FMLA", "PIP") | Enable hybrid retrieval |
| No reranking | Irrelevant chunks in top positions | Add cross-encoder reranker |
| Temperature too high | Hallucinated policy details | Set temperature ≤ 0.1 |
| No verification | Ungrounded answers go undetected | Enable answer verification |
| RBAC at API only | Retrieval returns restricted docs | Filter at vector search level |
| No session context | User says "what about that?" → broken | Inject last 3–5 turns |
| Stale documents | Outdated policy answers | Version-track documents, re-index on update |

## 22.6 Development Checklist

```
□ FastAPI project with health endpoint
□ JWT authentication middleware
□ RBAC role hierarchy (employee < manager < hr_admin)
□ Document ingestion (PDF, DOCX, MD, TXT)
□ Heading-aware chunking with metadata
□ Embedding service (Ollama nomic-embed-text)
□ Vector store (FAISS for dev, Qdrant for prod)
□ BM25 keyword index
□ Hybrid retrieval with RRF fusion
□ Cross-encoder reranking
□ Context builder with token budgeting
□ LLM gateway (Ollama / vLLM)
□ System prompt with grounding rules
□ Session storage with conversation memory
□ Answer verification (faithfulness + citations)
□ Prompt injection defense
□ Audit logging
□ Prometheus metrics
□ Evaluation dataset (50+ queries)
□ Automated eval runner
□ Admin dashboard endpoints
□ Docker Compose deployment
□ CI/CD eval gate
```

---

# APPENDIX A — DATA MODEL REFERENCE

```python
# Core data types used throughout the system

@dataclass
class User:
    user_id: str
    role: str           # "employee" | "manager" | "hr_admin"
    department: str | None = None

@dataclass
class SearchResult:
    chunk_id: str
    text: str
    score: float
    source: str
    page: int | None
    metadata: dict | None = None

@dataclass
class Citation:
    source: str
    page: int | None
    text_excerpt: str

@dataclass
class VerificationResult:
    faithfulness_score: float
    hallucination_risk: float
    verified_claims: list[ClaimVerification]
    citations: list[Citation]
    verdict: str        # "grounded" | "partially_grounded" | "ungrounded"

@dataclass
class ChatResponse:
    answer: str
    session_id: str
    citations: list[Citation]
    confidence: float
    faithfulness_score: float
    query_type: str
    latency_ms: float
    flagged: bool = False

@dataclass
class LLMResponse:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
```

# APPENDIX B — ENVIRONMENT VARIABLES

```bash
# Application
APP_NAME=hr-chatbot
ENVIRONMENT=production     # development | production
API_PORT=8000

# Authentication
JWT_SECRET_KEY=<256-bit-secret>
ACCESS_TOKEN_EXPIRE_MINUTES=480

# LLM
LLM_PROVIDER=vllm         # ollama | vllm
LLM_MODEL=llama3:8b
VLLM_BASE_URL=http://localhost:8001/v1
OLLAMA_BASE_URL=http://localhost:11434

# Embeddings
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSION=768

# Vector Store
VECTOR_STORE_BACKEND=qdrant   # faiss | qdrant | pgvector
QDRANT_URL=http://localhost:6333
FAISS_INDEX_DIR=./faiss_index

# Database
DB_URL=postgresql://hr:pass@localhost:5432/hrchat
DB_PATH=./hr_chatbot.db       # SQLite fallback

# Redis
REDIS_URL=redis://localhost:6379

# RAG Pipeline
DENSE_TOP_K=20
BM25_TOP_K=20
RERANK_TOP_N=8
MAX_CONTEXT_TOKENS=3000
LLM_TEMPERATURE=0.1
MAX_RESPONSE_TOKENS=1024
VERIFY_GROUNDING=true

# Company
COMPANY_NAME=Acme Corp
HR_CONTACT_EMAIL=hr@acmecorp.com
```

# APPENDIX C — DIRECTORY STRUCTURE

```
hr-rag-chatbot/
├── src/
│   ├── api/
│   │   ├── main.py                 # FastAPI app + router wiring
│   │   ├── routers/
│   │   │   ├── chat.py             # /chat/* endpoints
│   │   │   ├── documents.py        # /documents/* endpoints
│   │   │   ├── admin.py            # /admin/* endpoints
│   │   │   └── auth.py             # /auth/* endpoints
│   │   └── middleware/
│   │       ├── auth.py             # JWT validation
│   │       └── injection.py        # Prompt injection filter
│   ├── ingestion/
│   │   ├── pipeline.py             # IngestionPipeline
│   │   ├── loaders.py              # PDF, DOCX, MD, TXT loaders
│   │   ├── chunker.py              # Heading-aware + fixed-size chunking
│   │   └── metadata.py             # Document + chunk metadata
│   ├── retrieval/
│   │   ├── dense.py                # Dense vector retrieval
│   │   ├── bm25.py                 # BM25 keyword retrieval
│   │   ├── hybrid.py               # RRF fusion
│   │   ├── reranker.py             # Cross-encoder reranking
│   │   └── orchestrator.py         # Retrieval orchestration
│   ├── generation/
│   │   ├── model_gateway.py        # vLLM / Ollama gateway
│   │   ├── prompt_builder.py       # Prompt assembly
│   │   └── context_builder.py      # Context construction
│   ├── verification/
│   │   └── verifier.py             # Answer grounding + citations
│   ├── session/
│   │   └── store.py                # Session + turn storage
│   ├── auth/
│   │   ├── jwt.py                  # Token creation / validation
│   │   └── rbac.py                 # Role hierarchy + permissions
│   ├── agents/                     # Phase 4 — multi-agent
│   │   ├── query_agent.py
│   │   ├── research_agent.py
│   │   ├── reasoning_agent.py
│   │   ├── verification_agent.py
│   │   ├── critic_agent.py
│   │   └── orchestrator.py
│   ├── evaluation/
│   │   ├── dataset.py              # Eval query definitions
│   │   ├── runner.py               # Automated eval runner
│   │   └── metrics.py              # Metric computation
│   ├── observability/
│   │   ├── logging.py              # Structured logging config
│   │   └── metrics.py              # Prometheus metrics
│   ├── config.py                   # Settings (Pydantic BaseSettings)
│   └── db/
│       └── __init__.py             # Database initialization
├── tests/
│   ├── conftest.py                 # Fixtures (temp DB, test JWT)
│   ├── test_ingestion.py
│   ├── test_retrieval.py
│   ├── test_generation.py
│   ├── test_verification.py
│   ├── test_session.py
│   ├── test_rbac.py
│   ├── test_api.py
│   └── eval/
│       └── test_eval.py            # Evaluation benchmark tests
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── .env.example
└── docs/
    └── HR_RAG_CHATBOT_SDD_BLUEPRINT.md   # This document
```

---

**END OF DOCUMENT**

*This blueprint is designed to be implementation-complete. Each section provides specifications, code patterns, and configuration that can be directly translated into working modules. Engineers should implement phases sequentially, validating each phase with the evaluation framework before proceeding.*
