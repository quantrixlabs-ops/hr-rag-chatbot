"""Celery application — Phase 4 extension (F-38/F-43).

Phase 2: document ingestion queue
Phase 4 adds:
  - hrms_sync queue:  HRMS data pull every 4 hours per tenant
  - cache_warm queue: top-50 query warming daily at 6am
  - webhook queue:    async webhook dispatch with retry
  - Celery Beat:      periodic task scheduler

Broker:  Redis (REDIS_URL)
Backend: Redis (task results, 24h TTL)

Queues:
  ingestion   → document parsing, chunking, embedding, vector store write
  hrms_sync   → HRMS data pull tasks (per tenant)
  cache_warm  → cache warming tasks
  webhooks    → async webhook dispatch
  default     → all other tasks
"""

from __future__ import annotations

import os
from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

app = Celery(
    "hr_chatbot",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "backend.app.workers.ingestion_tasks",
        "backend.app.workers.hrms_tasks",
        "backend.app.workers.webhook_tasks",
    ],
)

app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Result TTL — 24 hours (admin polls job status)
    result_expires=86400,

    # Reliability
    task_acks_late=True,            # Re-queue on worker crash
    task_reject_on_worker_lost=True,

    # Routing — each task type gets its own queue
    task_routes={
        "backend.app.workers.ingestion_tasks.ingest_document":    {"queue": "ingestion"},
        "backend.app.workers.hrms_tasks.sync_tenant_hrms_data":   {"queue": "hrms_sync"},
        "backend.app.workers.hrms_tasks.sync_all_tenants_hrms":   {"queue": "hrms_sync"},
        "backend.app.workers.hrms_tasks.warm_tenant_cache":       {"queue": "cache_warm"},
        "backend.app.workers.hrms_tasks.cleanup_stale_sessions":  {"queue": "default"},
        "backend.app.workers.webhook_tasks.deliver_webhook":      {"queue": "webhooks"},
    },

    # Timezone
    timezone="UTC",
    enable_utc=True,
)

# ── Celery Beat — Periodic task schedule ──────────────────────────────────────
app.conf.beat_schedule = {
    # HRMS sync: pull all tenant data every 4 hours
    "hrms-sync-all-tenants": {
        "task": "backend.app.workers.hrms_tasks.sync_all_tenants_hrms",
        "schedule": crontab(minute=0, hour="*/4"),  # Every 4 hours at :00
        "options": {"queue": "hrms_sync"},
    },

    # Cache warming: pre-populate top queries daily at 6am UTC
    "cache-warm-all-tenants": {
        "task": "backend.app.workers.hrms_tasks.warm_all_tenants_cache",
        "schedule": crontab(minute=0, hour=6),  # 6:00 UTC daily
        "options": {"queue": "cache_warm"},
    },

    # Session cleanup: delete expired sessions daily at 2am UTC
    "cleanup-stale-sessions": {
        "task": "backend.app.workers.hrms_tasks.cleanup_stale_sessions",
        "schedule": crontab(minute=0, hour=2),  # 2:00 UTC daily
        "options": {"queue": "default"},
    },
}
