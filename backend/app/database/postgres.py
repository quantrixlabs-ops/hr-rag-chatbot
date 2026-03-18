"""Placeholder for PostgreSQL integration (production upgrade path).

In development the app uses SQLite via session_store.py.
This module provides the pgvector schema from Section 7.2 for teams
that want to switch to PostgreSQL.
"""

PGVECTOR_SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS hr_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL,
    text            TEXT NOT NULL,
    embedding       vector(768) NOT NULL,
    section_heading TEXT,
    page            INTEGER,
    chunk_index     INTEGER NOT NULL,
    access_roles    TEXT[] NOT NULL,
    category        TEXT NOT NULL,
    token_count     INTEGER NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON hr_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_chunks_roles ON hr_chunks USING GIN (access_roles);
CREATE INDEX IF NOT EXISTS idx_chunks_category ON hr_chunks (category);
"""
