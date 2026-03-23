# HR RAG Chatbot — Roadmap & SaaS Evolution

> Consolidated from the original Advanced Roadmap and SaaS Architecture documents.
> All 5 core phases are **COMPLETE**. This document tracks remaining gaps and the SaaS evolution path.

---

## Current State (Phases 1–5 Complete)

| Phase | Status | What Was Delivered |
|---|---|---|
| **1 — Foundation** | DONE | PostgreSQL, Qdrant, Alembic, tenant_id hooks, Docker Compose |
| **2 — RBAC & Async** | DONE | 4 roles, Celery, permissions matrix, audit logging, doc versioning |
| **3 — Multi-Tenancy** | DONE | Tenant middleware, SSO (OIDC), MinIO, feature flags, API versioning |
| **4 — HRMS & Perf** | DONE | BambooHR + SAP adapters, semantic cache, multi-model routing, PgBouncer |
| **5 — Hardening** | DONE | Encryption, MFA, GDPR, Prometheus, OTel, Helm, CI/CD, backup |
| **UX/UI Layer** | DONE | Toast system, MFA login, settings page, mobile sidebar, branding |

---

## Remaining Gaps

Items from the original enterprise blueprint that are not yet implemented:

### High Priority

| # | Feature | Effort | Notes |
|---|---|---|---|
| G-01 | Load testing with Locust (100/500/1000 concurrent) | Medium | Validate PgBouncer + LLM scaling claims |
| G-02 | Penetration testing + OWASP ZAP scan | Medium | Automated security scan in CI |
| G-03 | HTTPS/TLS termination (Let's Encrypt or cert-manager) | Small | Currently HTTP in dev; handled by ingress in K8s |
| G-04 | Retrieval quality benchmarks (MRR, NDCG, Recall@k) | Medium | Baseline metrics for RAG tuning |
| G-05 | SOC2 evidence collection automation | Large | Map controls → automated evidence gathering |

### Medium Priority

| # | Feature | Effort | Notes |
|---|---|---|---|
| G-06 | Slack bot integration | Medium | Slash commands + conversational thread |
| G-07 | Microsoft Teams bot | Medium | Activity handler + adaptive cards |
| G-08 | Multi-language support | Large | Translation layer + multilingual embeddings |
| G-09 | WCAG 2.1 AA accessibility | Medium | Keyboard nav, screen reader, contrast |
| G-10 | A/B testing framework for RAG parameters | Medium | Compare chunk sizes, reranker models, etc. |
| G-11 | Semantic chunking (parent-child) | Medium | Improve retrieval quality for long docs |
| G-12 | Feedback-driven retrieval tuning | Medium | Negative feedback → deprioritize source |

### Low Priority / Future

| # | Feature | Effort | Notes |
|---|---|---|---|
| G-13 | Email gateway (receive questions via email) | Small | Parse inbound, reply with answer |
| G-14 | Voice interface (STT → RAG → TTS) | Large | WebRTC or Twilio integration |
| G-15 | Fine-tuning pipeline (LoRA/QLoRA) | Large | Domain-specific LLM adaptation |
| G-16 | Knowledge graph (entity relationships) | Large | Cross-policy concept linking |
| G-17 | Agentic workflows (multi-step tasks) | Large | "Help me request leave" → form filling |
| G-18 | Chat export / conversation download | Small | PDF or DOCX download per session |

---

## SaaS Evolution Path

### Current: Mode A (Single-Tenant / Demo)

```
Single Server (4-8 CPU, 16-32GB RAM, optional GPU)
├── FastAPI + Celery (Docker Compose)
├── PostgreSQL (shared DB, tenant_id isolation)
├── Qdrant (shared collection, tenant payload filtering)
├── Ollama (shared LLM)
└── Redis (shared cache, tenant-prefixed keys)
```

**Cost**: ~$50–150/month (cloud VM) or $0 (on-prem)
**Scale**: 1–50 concurrent users, 1–3 tenants

### Target: Mode B (Multi-Tenant SaaS)

```
                    ┌──────────────────────────────────┐
                    │       LOAD BALANCER / INGRESS     │
                    └─────────┬────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
    ┌────┴─────┐     ┌───────┴──────┐      ┌──────┴──────┐
    │ Web App  │     │  API Gateway  │      │ Integrations│
    │ (React)  │     │  (K8s pods)   │      │ Slack/Teams │
    │ Tenant   │     │  HPA 2→10    │      │ Webhooks    │
    │ Branding │     │              │      │ HRMS        │
    └──────────┘     └──────────────┘      └─────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
         PostgreSQL       Qdrant           Redis
         (shared or       (per-tenant      (prefixed)
          per-schema)      namespace)
```

**Scale**: 5000+ users/tenant, 100+ tenants
**Cost**: $500–5000/month depending on GPU + storage

### Migration Steps (ordered by priority)

| Step | Status | Description |
|---|---|---|
| 1. `tenant_id` on all tables | DONE | DEFAULT 'default' for demo |
| 2. Tenant middleware | DONE | Extracts tenant from JWT |
| 3. All queries filter by tenant | DONE | DB, vector store, cache |
| 4. Tenant management API | DONE | CRUD tenants with config JSONB |
| 5. Per-tenant feature flags | DONE | SSO, MFA, HRMS provider config |
| 6. Tenant onboarding flow | TODO | Self-serve signup + provisioning |
| 7. Billing integration (Stripe) | TODO | Usage-based or per-seat |
| 8. Per-tenant LLM routing | DONE | Via multi-model + tenant config |
| 9. Physical isolation option | TODO | Dedicated schema/DB for enterprise tier |

### LLM Cost Optimization

| Strategy | Impact |
|---|---|
| Semantic cache (Redis) | 30–60% cache hit rate, skip LLM entirely |
| Multi-model routing | Simple queries → small model (3B), complex → large (70B) |
| Shared GPU pool | 80% of requests on shared Ollama pool |
| Dedicated GPU tier | Enterprise tenants get isolated Ollama/vLLM instance |
| Cloud overflow | Route to API (OpenAI/Anthropic) when local GPU saturated |

---

## Best Practices Checklist

### Done

- [x] Type hints on all Python functions
- [x] Stateless services (session state in Redis/DB)
- [x] Database connection pooling (PgBouncer)
- [x] Feature flags for gradual rollout
- [x] Graceful shutdown handlers
- [x] OpenTelemetry instrumentation
- [x] Prometheus metrics
- [x] Grafana dashboards
- [x] CI/CD pipeline (GitHub Actions)
- [x] Helm charts with HPA + PDB
- [x] Automated backup script
- [x] GDPR compliance toolkit

### Remaining

- [ ] Pre-commit hooks (ruff, mypy, eslint, prettier)
- [ ] Code coverage target > 80%
- [ ] Staging environment with production-like data
- [ ] Blue/green or canary deployments
- [ ] Chaos testing (kill Ollama mid-request, DB drops)
- [ ] Log aggregation (ELK or Loki)
- [ ] PagerDuty/Opsgenie integration for alerts
- [ ] Dependency vulnerability scanning (dependabot)
- [ ] WCAG 2.1 AA compliance audit

---

## Demo Configuration

### Pre-loaded Tenant
- **Company**: "TechFlow Inc."
- **Industry**: Technology
- **Employees**: ~500

### Pre-loaded Users

| Username | Password | Role |
|---|---|---|
| admin | Admin@12345!! | hr_admin |
| manager1 | Manager@12345!! | manager |
| employee1 | Employee@12345!! | employee |

### Pre-loaded Documents
1. Employee Handbook 2024
2. Leave Policy (annual, sick, parental, FMLA)
3. Benefits Guide (health, 401k, HSA, dental)
4. Remote Work Policy
5. Performance Review Process
6. Onboarding Guide
