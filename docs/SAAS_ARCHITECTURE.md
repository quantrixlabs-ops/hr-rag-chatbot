# HR RAG Chatbot — SaaS Architecture Design

## Demo-First, SaaS-Ready

This document describes the architecture for evolving the current single-tenant HR chatbot
into a multi-tenant SaaS platform while keeping the demo path fast and impressive.

---

## Mode A: Demo (Current + Enhancements)

```
Single Server (4-8 CPU, 16-32GB RAM, 1 GPU optional)
├── FastAPI Backend (single process + uvicorn workers)
├── React Frontend (nginx or Vite dev server)
├── SQLite → PostgreSQL (single database)
├── FAISS (in-process vector store)
├── Ollama (local LLM, shared)
└── Redis (rate limiting, token cache)
```

**Cost**: ~$50-150/month (cloud VM with GPU) or $0 (on-prem Mac/Linux)
**Scale**: 1-50 concurrent users, 1 organization

---

## Mode B: SaaS (Future Evolution)

```
┌──────────────────────────────────────────────────────────────┐
│                    LOAD BALANCER (nginx/ALB)                  │
└──────────┬───────────────────────────────────┬───────────────┘
           │                                   │
┌──────────┴──────────┐           ┌────────────┴──────────────┐
│   WEB APP (React)   │           │   INTEGRATION LAYER       │
│   - Tenant branding │           │   - Slack/Teams bots      │
│   - Role-based UI   │           │   - Embeddable widget     │
│   - Chat + Admin    │           │   - REST API for clients  │
└──────────┬──────────┘           └────────────┬──────────────┘
           │                                   │
┌──────────┴───────────────────────────────────┴──────────────┐
│                    API GATEWAY (FastAPI)                      │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ TENANT MIDDLEWARE: Extract tenant → inject into context  │ │
│  │ Every request carries tenant_id throughout the stack     │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  Auth │ Chat │ Documents │ Admin │ Tenant Mgmt │ Billing     │
└──────────────────────────────────────────────────────────────┘
           │           │           │           │
┌──────────┴──┐  ┌─────┴─────┐  ┌─┴────┐  ┌───┴──────┐
│ PostgreSQL  │  │  Vector   │  │Redis │  │  Ollama/ │
│ (shared DB  │  │  Store    │  │      │  │  vLLM    │
│  tenant_id) │  │ (per-     │  │      │  │  (shared │
│             │  │  tenant   │  │      │  │  or per- │
│             │  │  namespace│  │      │  │  tenant) │
└─────────────┘  └───────────┘  └──────┘  └──────────┘
```

**Scale**: 5000+ users/tenant, 100+ tenants
**Cost**: $500-5000/month depending on GPU + storage

---

## Multi-Tenancy Strategy

### Phase 1 (Demo/MVP): Logical Isolation
- Single PostgreSQL database
- Every table has `tenant_id` column (DEFAULT 'default' for demo)
- FAISS index includes tenant_id in chunk metadata (already has access_roles)
- All queries automatically filter by tenant_id

### Phase 2 (Growth): Enhanced Isolation
- Separate FAISS index files per tenant (already in separate dirs)
- Redis key prefixed by tenant_id
- Per-tenant rate limits and quotas

### Phase 3 (Enterprise): Physical Isolation
- Option for dedicated PostgreSQL schema per tenant
- Dedicated vector store instance per tenant
- Dedicated LLM instance for premium tenants

### Migration Path (Demo → SaaS)
```
Step 1: Add tenant_id to all tables (DEFAULT 'default')     ← DO NOW
Step 2: Add TenantMiddleware that extracts tenant from JWT   ← DO NOW
Step 3: All DB queries filter by tenant_id                   ← DO NOW
Step 4: Tenant management API (CRUD tenants)                 ← Later
Step 5: Tenant onboarding flow (self-serve signup)           ← Later
Step 6: Billing integration (Stripe)                         ← Later
Step 7: Per-tenant FAISS directories                         ← Later
Step 8: Per-tenant LLM routing                               ← Later
```

Steps 1-3 are backwards-compatible and should be done NOW to avoid painful migration later.

---

## Database Design (SaaS-Ready)

### Tenants Table (NEW)
```sql
CREATE TABLE tenants (
    tenant_id    TEXT PRIMARY KEY,        -- UUID
    name         TEXT NOT NULL,           -- "Acme Corp"
    slug         TEXT UNIQUE NOT NULL,    -- "acme-corp" (URL-friendly)
    plan         TEXT DEFAULT 'trial',    -- trial/starter/pro/enterprise
    settings     TEXT DEFAULT '{}',       -- JSON (branding, LLM model, etc.)
    created_at   REAL NOT NULL,
    is_active    INTEGER DEFAULT 1
);
```

### All Existing Tables: Add tenant_id
```sql
-- Users: add tenant_id
ALTER TABLE users ADD COLUMN tenant_id TEXT DEFAULT 'default' REFERENCES tenants(tenant_id);

-- Sessions: add tenant_id
ALTER TABLE sessions ADD COLUMN tenant_id TEXT DEFAULT 'default';

-- Documents: add tenant_id
ALTER TABLE documents ADD COLUMN tenant_id TEXT DEFAULT 'default';

-- query_logs, feedback, security_events: add tenant_id
```

### Tenant-Aware Queries
```python
# BEFORE (single-tenant):
con.execute("SELECT * FROM documents WHERE category=?", (cat,))

# AFTER (multi-tenant ready):
con.execute("SELECT * FROM documents WHERE tenant_id=? AND category=?", (tenant_id, cat))
```

---

## RBAC (5-Level, SaaS-Ready)

| Role | Scope | Permissions |
|------|-------|-------------|
| **super_admin** | Platform | Manage tenants, platform settings, billing |
| **tenant_admin** | Tenant | Manage users, roles, tenant settings |
| **hr_admin** | Tenant | Upload/delete docs, view analytics, manage HR content |
| **manager** | Tenant | View team analytics, access manager-level docs |
| **employee** | Tenant | Chat, view employee-level docs, give feedback |

For the demo, super_admin and tenant_admin are equivalent. The split matters in SaaS.

---

## LLM Strategy

### Demo (Now)
- Single Ollama instance running Llama3:8b
- Shared across all users
- nomic-embed-text for embeddings
- Cost: $0 (local) or ~$50/month (cloud GPU)

### SaaS (Future)
```
Request → Tenant Config Lookup → Model Router
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
              Shared Pool      Dedicated GPU      Cloud Fallback
              (Ollama/vLLM)    (Enterprise tier)  (OpenAI/Anthropic)
              Free/Starter     Enterprise plan    Overflow only
```

### Cost Optimization
- Shared GPU pool: 80% of requests (low-cost tenants)
- Response caching in Redis: cache frequent HR answers (30-60% cache hit rate)
- Smaller model for simple queries (Llama3:8b), larger for complex (Llama3:70b)
- Embedding cache: don't re-embed identical queries

---

## Demo Scenario

### Pre-loaded Tenant
- **Company**: "TechFlow Inc."
- **Industry**: Technology
- **Employees**: ~500

### Pre-loaded Users

| Username | Password | Role | Name |
|----------|----------|------|------|
| admin | Admin@12345!! | hr_admin | Sarah Mitchell |
| manager1 | Manager@12345!! | manager | James Wilson |
| employee1 | Employee@12345!! | employee | Alex Chen |

### Pre-loaded Documents
1. Employee Handbook 2024 (leave, benefits, code of conduct)
2. Leave Policy (annual, sick, parental, FMLA)
3. Benefits Guide (health insurance, 401k, HSA, dental/vision)
4. Remote Work Policy (eligibility, equipment, expectations)
5. Performance Review Process (timeline, criteria, ratings)
6. Onboarding Guide (first week, systems access, training)

### Demo Conversation Flows
1. **Employee asks**: "How many vacation days do I get?" → Grounded answer with citation
2. **Employee asks**: "Tell me about benefits" → Ambiguity detection, clarification prompt
3. **Manager asks**: "What is the performance review timeline?" → Manager-level doc access
4. **Admin uploads**: New policy document → Indexed, searchable immediately
5. **Admin views**: Dashboard with metrics, failed queries, security events
