# HR RAG Chatbot — 2-Year Knowledge Training Strategy & Roadmap

**Document Type:** Knowledge Training Strategy & Long-Term Roadmap
**System:** Enterprise HR RAG Chatbot (FastAPI + React + Ollama + FAISS)
**Date:** 2026-03-25
**Version:** 1.0

> **Change Control Directive:** No base logic of the application shall be modified.
> All enhancements are additive — new modules, new endpoints, new UI components.
> The existing RAG pipeline, FAISS vector store, ingestion service, and chat flow remain untouched.

---

## Executive Summary

This document defines an 8-phase knowledge training strategy and 2-year implementation roadmap for the HR RAG Chatbot platform. The strategy ensures the system continuously improves its knowledge quality, retrieval accuracy, and response reliability — without modifying the core RAG pipeline or application logic.

**Core Principle:** The chatbot's intelligence comes from *the quality of its knowledge base*, not from retraining or fine-tuning LLMs. By improving how documents are structured, chunked, validated, and maintained, we improve every answer the system produces.

---

## Phase 1 — Data Understanding & Audit (Months 1-3)

**Goal:** Build a complete map of what the chatbot knows, what it doesn't know, and where knowledge gaps exist.

### 1.1 Document Inventory Audit

| Task | Description | Output |
|------|-------------|--------|
| Catalog all HR documents | List every document in the system with title, category, version, page count, chunk count | `docs/KNOWLEDGE_INVENTORY.md` |
| Categorize by policy domain | Map documents to HR domains: Leave, Benefits, Compensation, Onboarding, Legal, Performance, Safety | Category coverage matrix |
| Identify version currency | Flag documents older than 12 months that may contain outdated policies | Staleness report |
| Measure chunk coverage | For each document, verify chunk count vs page count ratio is healthy (5-15 chunks/page) | Chunk health dashboard |

### 1.2 Knowledge Gap Analysis

| Gap Type | How to Detect | Action |
|----------|---------------|--------|
| Missing topics | Employee queries with low retrieval scores (<0.3 cosine similarity) | Flag for HR to provide source documents |
| Thin coverage | Topics with <5 chunks in FAISS | Request additional policy documents |
| Stale content | Documents not updated in >12 months | Queue for HR review and re-upload |
| Conflicting info | Multiple documents answering same query with different answers | Flag for HR to reconcile and version |

### 1.3 Query Pattern Analysis

Analyze the `messages` table to understand what employees actually ask:

- **Top 50 queries** by frequency — are these well-covered in the knowledge base?
- **Failed queries** (low confidence responses) — what topics are employees asking that the system can't answer?
- **Query clusters** — group similar questions to identify topic demand
- **Seasonal patterns** — benefits enrollment questions spike in Q4, tax questions in Q1

**Deliverable:** A `KNOWLEDGE_GAPS.md` report that HR uses to prioritize document uploads.

### 1.4 Auto-Reindex Verification

The system already supports automatic FAISS reindexing when HR uploads or replaces documents:

| Scenario | How It Works | Code Location |
|----------|-------------|---------------|
| New document upload | Ingested → chunked → embedded → indexed in FAISS → saved to disk | `ingestion_service.py` → `ingest()` |
| Same filename re-upload | Old chunks removed from FAISS → new content re-ingested | `document_routes.py` → `upload()` detects by `source_filename` |
| Same content hash | Duplicate detected → old version replaced | `document_routes.py` → `upload()` detects by `content_hash` |
| Document deletion | Chunks removed from FAISS → index rebuilt → saved to disk | `document_routes.py` → `_remove_document_chunks()` |
| BM25 rebuild | BM25 keyword index rebuilt after every FAISS change | `bm25.build_index(vs.metadata)` after removal |

**No code changes needed.** HR can upload updated documents through the existing Upload Documents page, and FAISS automatically reindexes. The semantic cache is also invalidated for any queries that cited the changed document (`invalidate_on_document_change()`).

---

## Phase 2 — Knowledge Structure Design (Months 2-5)

**Goal:** Define how HR knowledge should be organized for optimal retrieval quality, without changing the chunking or embedding logic.

### 2.1 Document Preparation Guidelines for HR

Create an HR-facing guide on how to structure documents for best chatbot performance:

| Guideline | Reason | Impact |
|-----------|--------|--------|
| Use clear headings (H1, H2, H3) | Heading-based chunking produces topically focused chunks | +15-20% retrieval accuracy |
| One policy per document | Prevents cross-topic chunk contamination | Cleaner search results |
| Keep sections under 500 words | Aligns with chunk size parameters (400 words) | Better chunk boundaries |
| Use bullet points for eligibility/procedures | Structured content chunks better than prose | More precise answers |
| Include a summary at the top of each document | Summary chunk often matches broad queries | Faster first-hit retrieval |
| Version documents with dates | Version tracking in the system uses this metadata | Accurate version display |
| Avoid scanned PDFs | pdfplumber cannot extract text from images | Zero text = zero chunks |

**Deliverable:** `docs/HR_DOCUMENT_GUIDELINES.md` — a non-technical guide for the HR team.

### 2.2 Category Taxonomy

Standardize document categories to improve retrieval filtering:

```
HR Knowledge Taxonomy
├── Leave & Attendance
│   ├── Annual Leave
│   ├── Sick Leave
│   ├── Parental Leave (Maternity/Paternity)
│   ├── FMLA / Statutory Leave
│   ├── Bereavement Leave
│   └── Attendance Policy
├── Compensation & Benefits
│   ├── Salary Structure
│   ├── Health Insurance
│   ├── 401(k) / Retirement
│   ├── HSA / FSA
│   ├── Dental & Vision
│   ├── Life Insurance
│   └── Stock Options / ESOP
├── Employment Policies
│   ├── Employee Handbook
│   ├── Code of Conduct
│   ├── Anti-Harassment
│   ├── Remote Work
│   ├── Dress Code
│   └── Workplace Safety
├── Onboarding & Offboarding
│   ├── New Hire Guide
│   ├── IT Setup
│   ├── Benefits Enrollment
│   ├── Exit Process
│   └── Knowledge Transfer
├── Performance & Development
│   ├── Review Process
│   ├── Goal Setting
│   ├── Training & Learning
│   ├── Promotion Criteria
│   └── PIP Process
└── Legal & Compliance
    ├── Data Privacy (GDPR)
    ├── Equal Opportunity
    ├── Whistleblower Policy
    ├── NDA / IP Agreement
    └── Regulatory Compliance
```

### 2.3 FAQ Knowledge Layer

Build a curated FAQ database that provides instant, high-confidence answers for the most common questions:

| Component | Description |
|-----------|-------------|
| FAQ entries | Top 100 most-asked questions with verified answers |
| Source linking | Each FAQ maps to the source document and page |
| Priority routing | FAQ check runs before RAG retrieval (already implemented in pipeline) |
| Maintenance | HR reviews FAQs quarterly, updates via admin panel |

The existing `faq_service.py` already supports this — HR needs to populate it through the admin interface.

---

## Phase 3 — Learning Strategy (Months 4-8)

**Goal:** Define how the system "learns" from new information without retraining any models.

### 3.1 Knowledge Update Workflow

```
HR Identifies Policy Change
        │
        ▼
HR Updates Document (Word/PDF)
        │
        ▼
HR Uploads via Upload Documents Page
        │
        ▼
System Auto-Detects (filename or content hash match)
        │
        ├── Old chunks removed from FAISS
        ├── New document parsed, chunked, embedded
        ├── New chunks indexed in FAISS + BM25
        ├── Semantic cache invalidated for affected queries
        └── FAISS persisted to disk
        │
        ▼
Employees Get Updated Answers Immediately
```

**No code changes required.** This workflow is fully implemented.

### 3.2 Continuous Learning Signals

The system learns from employee interactions without any model retraining:

| Signal | Source | How It Improves Knowledge |
|--------|--------|--------------------------|
| Low-confidence queries | Confidence indicator (<0.4 score) | Flag topics needing better documentation |
| Repeated queries on same topic | Query frequency analysis | Indicates high-demand topics — prioritize FAQ creation |
| Thumbs down feedback | User feedback on responses | Identify wrong/incomplete answers for HR review |
| Zero-result queries | Queries with no FAISS matches above threshold | Completely missing knowledge areas |
| Citation patterns | Which documents are cited most/least | Identify underutilized or over-relied-upon documents |

### 3.3 Knowledge Freshness Policy

| Document Type | Review Frequency | Owner | Action on Expiry |
|---------------|-----------------|-------|------------------|
| Leave policies | Every 6 months | HR Head | Re-upload updated version |
| Benefits guides | Annually (before enrollment) | Benefits team | Full replacement upload |
| Employee handbook | Annually | HR Head | Section-by-section update |
| Legal/compliance | On regulatory change | Legal team | Immediate replacement |
| Onboarding guides | Every 6 months | HR team | Review and update |
| Performance processes | Annually (before review cycle) | HR Head | Update criteria and timelines |

---

## Phase 4 — Guardrails Enforcement (Months 5-10)

**Goal:** Ensure the chatbot never provides harmful, incorrect, or unauthorized information.

### 4.1 Content Safety Guardrails (Already Implemented)

The existing `content_safety.py` module enforces:

| Guardrail | What It Blocks | Status |
|-----------|---------------|--------|
| PII detection | SSN, credit card, phone numbers in responses | Active |
| Toxic content filter | Discriminatory, harassing, or offensive language | Active |
| Topic boundaries | Blocks medical advice, legal counsel, financial advice | Active |
| Role-based access | Employees can't see manager-only documents | Active |
| Hallucination disclaimer | Low-confidence answers show warning banner | Active |

### 4.2 Knowledge Boundary Guardrails (New — Additive)

Add guardrail rules as configuration (not code changes):

| Rule | Implementation | Location |
|------|---------------|----------|
| "I don't know" threshold | If top retrieval score < 0.25, respond with "I don't have information on this topic. Please contact HR directly." | `guardrails/` config |
| Source requirement | Every factual claim must cite at least one source document | Already enforced by RAG pipeline |
| Recency check | If cited document is >18 months old, add disclaimer: "This policy may have been updated. Please verify with HR." | `guardrails/` config |
| Scope limitation | Block queries about other employees' data (salary, performance) | Already enforced by RBAC |
| Escalation trigger | Detect queries about termination, legal disputes, discrimination → recommend speaking with HR directly | `guardrails/` config |

### 4.3 Answer Verification (Already Implemented)

The `verification_service.py` already cross-checks LLM responses against source chunks:

- Verifies claims are grounded in retrieved context
- Flags unsupported statements
- Adds confidence scoring based on source overlap

**No changes needed.** This runs on every response automatically.

---

## Phase 5 — Multi-LLM Optimization (Months 8-14)

**Goal:** Optimize which LLM handles which queries for best quality/cost/speed tradeoff.

### 5.1 Current Model Architecture

```
Query → Query Analyzer → Complexity Classification
                              │
                ┌──────────────┼──────────────┐
                ▼              ▼              ▼
           Simple FAQ      Standard RAG    Complex Reasoning
           (cached)        (llama3:8b)     (AI Router → external)
```

### 5.2 Model Routing Strategy (Already Implemented)

The `ai_router.py` and `model_router.py` already handle:

| Query Type | Model | Rationale |
|------------|-------|-----------|
| FAQ hit (exact match) | No LLM needed | Cached answer, instant response |
| Simple factual | llama3:8b (local) | Fast, zero cost, good for direct lookups |
| Complex policy interpretation | llama3:8b with extended context | Multi-chunk reasoning |
| Fallback (Ollama down) | External API (if configured) | AIRouter handles failover |

### 5.3 Future Optimization (Additive Only)

| Enhancement | Timeline | Approach |
|-------------|----------|----------|
| Semantic cache tuning | Month 8-9 | Adjust similarity threshold (currently 0.92) based on cache hit quality analysis |
| Query complexity classifier | Month 10-11 | Add lightweight classifier to route simple vs complex queries (config-driven) |
| Response quality scoring | Month 12-13 | Log retrieval scores + response length + user feedback for quality analytics |
| Model A/B testing | Month 13-14 | Compare response quality between models on same queries (analytics only) |

---

## Phase 6 — Analytics & Continuous Improvement (Months 10-18)

**Goal:** Build analytics that drive knowledge improvement decisions.

### 6.1 Knowledge Quality Dashboard

Track these metrics in the admin dashboard:

| Metric | What It Measures | Target |
|--------|-----------------|--------|
| Retrieval accuracy (avg top-1 score) | How well chunks match queries | >0.45 cosine similarity |
| Answer confidence distribution | % of High/Medium/Low confidence responses | >70% High |
| FAQ hit rate | % of queries answered from FAQ cache | >20% |
| Semantic cache hit rate | % of queries answered from cache | >30% |
| Knowledge coverage | % of HR topics with >=10 chunks | >90% |
| Document freshness | % of documents updated within 12 months | >80% |
| Zero-result rate | % of queries with no relevant chunks found | <5% |
| User satisfaction | Thumbs up/down ratio | >85% positive |

### 6.2 Improvement Feedback Loop

```
Monthly Cycle:
┌─────────────────────────────────────────────────────┐
│  1. Export low-confidence queries from last 30 days  │
│  2. Identify top 10 knowledge gaps                   │
│  3. HR creates/updates documents to fill gaps        │
│  4. Upload documents (auto-reindex via FAISS)        │
│  5. Add top questions to FAQ database                │
│  6. Measure improvement in next month's metrics      │
└─────────────────────────────────────────────────────┘
```

### 6.3 Quarterly Knowledge Review

| Quarter | Focus Area | Deliverable |
|---------|-----------|-------------|
| Q1 | Benefits enrollment, tax documents | Updated benefits guide, new tax FAQ |
| Q2 | Mid-year review process, summer policies | Performance review guide update |
| Q3 | New hire onboarding (fall hiring wave) | Onboarding guide refresh |
| Q4 | Year-end policies, holiday schedules | Handbook annual update, leave policy refresh |

---

## Phase 7 — 2-Year Implementation Roadmap (Full Timeline)

### Year 1: Foundation & Optimization

```
Month 1-2:   ████ Phase 1 — Document Inventory & Knowledge Gap Audit
Month 2-4:   ██████ Phase 2 — Knowledge Structure Design & HR Guidelines
Month 3-5:   ████ Phase 1 cont. — Query Pattern Analysis & Gap Report
Month 4-6:   ████ Phase 3 — Knowledge Update Workflow & Freshness Policy
Month 5-8:   ██████ Phase 4 — Guardrails Configuration & Boundary Rules
Month 6-9:   ██████ Phase 6a — Knowledge Quality Dashboard (admin panel)
Month 8-10:  ████ Phase 5a — Semantic Cache Tuning
Month 10-12: ████ Phase 5b — Query Complexity Classifier
```

**Year 1 Milestones:**

| Milestone | Target Date | Success Criteria |
|-----------|------------|------------------|
| Knowledge inventory complete | Month 2 | 100% of documents cataloged with gap analysis |
| HR document guidelines published | Month 4 | HR team trained on document preparation |
| FAQ database populated | Month 5 | Top 100 questions with verified answers |
| Guardrails config deployed | Month 8 | All boundary rules active, zero harmful responses |
| Knowledge dashboard live | Month 9 | Real-time metrics visible in admin panel |
| Cache optimization complete | Month 10 | >30% cache hit rate achieved |
| Year 1 knowledge coverage >85% | Month 12 | Measured across all HR topic categories |

### Year 2: Scale & Maturity

```
Month 13-14: ████ Phase 5c — Model A/B Testing & Response Quality Scoring
Month 14-16: ████ Phase 6b — Automated Gap Detection Pipeline
Month 16-18: ████ Phase 6c — Quarterly Review Automation
Month 18-20: ████ Phase 7a — Multi-Department Knowledge Expansion
Month 20-22: ████ Phase 7b — Knowledge Lifecycle Automation
Month 22-24: ████ Phase 8 — Testing & Validation Framework
```

**Year 2 Milestones:**

| Milestone | Target Date | Success Criteria |
|-----------|------------|------------------|
| A/B testing framework operational | Month 14 | Can compare model quality on same queries |
| Automated gap detection running | Month 16 | Monthly reports auto-generated from query logs |
| Quarterly review process established | Month 18 | HR completes 2 quarterly reviews successfully |
| Multi-department expansion | Month 20 | IT, Finance, Legal departments onboarded |
| Knowledge lifecycle automated | Month 22 | Stale document alerts, auto-review reminders |
| Validation framework complete | Month 24 | Retrieval benchmarks (MRR, NDCG) tracked |

### Year 2 Expansion — Multi-Department Knowledge

| Department | Document Types | Estimated Chunks |
|-----------|---------------|-----------------|
| HR (current) | Policies, handbooks, benefits, leave | ~1000 chunks |
| IT | Security policies, VPN guide, software catalog | ~300 chunks |
| Finance | Expense policy, travel policy, procurement | ~200 chunks |
| Legal | NDA templates, IP policy, compliance guides | ~200 chunks |
| Operations | Safety manual, facilities guide, emergency procedures | ~150 chunks |

**Total projected:** ~1850 chunks across 5 departments (FAISS handles this easily).

---

## Phase 8 — Testing & Validation Framework (Months 22-24)

**Goal:** Establish repeatable benchmarks to measure and maintain knowledge quality.

### 8.1 Retrieval Quality Benchmarks

| Metric | Description | Target | How to Measure |
|--------|-------------|--------|---------------|
| MRR (Mean Reciprocal Rank) | Position of first relevant chunk in results | >0.7 | Test queries with known correct chunks |
| Recall@5 | % of relevant chunks in top 5 results | >0.8 | Ground truth test set |
| NDCG@10 | Ranking quality of top 10 results | >0.75 | Graded relevance judgments |
| Answer accuracy | % of answers verified as correct by HR | >90% | Monthly HR spot-check (sample of 50 queries) |

### 8.2 Test Query Set

Build a curated set of 200+ test queries with expected answers:

| Category | Sample Query | Expected Source | Expected Answer Contains |
|----------|-------------|----------------|------------------------|
| Leave | "How many sick days do I get?" | Leave Policy, Section 3.2 | "X days per year" |
| Benefits | "What is the 401k match?" | Benefits Guide, Section 5 | "X% match up to Y%" |
| Onboarding | "What do I need on my first day?" | Onboarding Guide, Page 1 | Checklist items |
| Performance | "When is the review cycle?" | Performance Process, Section 1 | Date range |

### 8.3 Regression Testing

Before any knowledge base change (new document upload, category restructure), run:

1. Execute test query set against current knowledge base → baseline scores
2. Apply knowledge change
3. Re-run test query set → compare scores
4. Flag any query where score dropped >10%
5. Investigate regressions before approving change

### 8.4 Validation Schedule

| Frequency | What | Who |
|-----------|------|-----|
| Weekly | Review zero-result queries, update FAQ | HR team |
| Monthly | Run knowledge gap analysis, upload new documents | HR Head |
| Quarterly | Full retrieval benchmark, document freshness audit | HR Head + Engineering |
| Annually | Complete knowledge review, taxonomy update, roadmap refresh | HR Director + Engineering Lead |

---

## Change Control Summary

| What Changes | What Does NOT Change |
|-------------|---------------------|
| Document content (HR uploads new/updated docs) | RAG pipeline logic (`pipeline.py`) |
| FAQ database entries | FAISS vector store code (`faiss_store.py`) |
| Guardrail configuration rules | Ingestion service logic (`ingestion_service.py`) |
| Category taxonomy | Embedding model or chunking parameters |
| Dashboard analytics queries | Authentication or RBAC system |
| Test query sets and benchmarks | Chat flow or message handling |
| Model routing configuration | Frontend component architecture |
| Cache tuning thresholds | Core API endpoint structure |

**Principle:** The application is the engine. Knowledge is the fuel. We improve the fuel, not the engine.

---

## Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| HR doesn't maintain documents | Medium | High — stale answers | Automated staleness alerts + quarterly review process |
| Knowledge gaps persist | Medium | Medium — low confidence answers | Monthly gap analysis + FAQ as safety net |
| Document quality varies | High | Medium — poor chunking | HR guidelines document + document review checklist |
| FAISS grows too large | Low | Low — FAISS handles 10K+ chunks easily | Monitor chunk count; archive obsolete documents |
| LLM hallucinations | Medium | High — incorrect policy answers | Verification service + guardrails + confidence indicators |
| Employee trust erosion | Low | High — reduced adoption | Consistent quality + transparent confidence indicators |

---

## Success Metrics (2-Year Targets)

| Metric | Current (Baseline) | Year 1 Target | Year 2 Target |
|--------|-------------------|---------------|---------------|
| Knowledge coverage (topics) | ~60% | >85% | >95% |
| Average retrieval score | ~0.38 | >0.45 | >0.55 |
| High-confidence response rate | ~55% | >70% | >80% |
| FAQ hit rate | ~5% | >20% | >30% |
| Semantic cache hit rate | ~15% | >30% | >40% |
| Zero-result query rate | ~12% | <5% | <3% |
| User satisfaction (thumbs up) | ~70% | >85% | >90% |
| Document freshness (within 12mo) | ~50% | >80% | >90% |
| Active departments | 1 (HR) | 1 (HR) | 3-5 departments |

---

*Document: KNOWLEDGE_TRAINING_STRATEGY.md*
*Version: 1.0 | Created: 2026-03-25*
*Next Review: 2026-06-25 (Quarterly)*
