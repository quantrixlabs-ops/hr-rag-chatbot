"""Pydantic models for documents & ingestion — Sections 5 & 20."""

from __future__ import annotations

from dataclasses import dataclass, field
from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    document_id: str
    chunk_count: int
    status: str
    processing_time_ms: float = 0.0


class ReindexRequest(BaseModel):
    document_id: Optional[str] = None
    force: bool = False


# ── Internal dataclasses used across services ────────────────────────────────

@dataclass
class DocumentMetadata:
    document_id: str
    title: str
    category: str
    access_roles: list[str]
    effective_date: str
    version: str
    source_filename: str
    uploaded_by: str
    uploaded_at: float
    page_count: int = 0
    chunk_count: int = 0


@dataclass
class ChunkMetadata:
    chunk_id: str
    document_id: str
    text: str
    page: Optional[int]
    section_heading: Optional[str]
    chunk_index: int
    access_roles: list[str]
    category: str
    token_count: int
    source: str = ""
    embedding_id: Optional[str] = None


@dataclass
class SearchResult:
    chunk_id: str
    text: str
    score: float
    source: str
    page: Optional[int]
    metadata: Optional[dict] = None


@dataclass
class Citation:
    source: str
    page: Optional[int]
    text_excerpt: str


@dataclass
class ClaimVerification:
    claim: str
    verified: bool
    evidence_chunks: list[str]
    confidence: float


@dataclass
class VerificationResult:
    faithfulness_score: float
    hallucination_risk: float
    verified_claims: list[ClaimVerification]
    citations: list[Citation]
    verdict: str


@dataclass
class LLMResponse:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int


@dataclass
class IngestionResult:
    document_id: str
    chunk_count: int
    status: str
    processing_time_ms: float = 0.0
