"""Pydantic request/response models for chat — Sections 4 & 20."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class User(BaseModel):
    user_id: str
    role: str = "employee"
    department: str | None = None


class ChatQueryRequest(BaseModel):
    query: str
    session_id: str | None = None
    include_sources: bool = True
    include_trace: bool = False


class CitationOut(BaseModel):
    source: str
    page: int | None = None
    excerpt: str = ""


class ChatQueryResponse(BaseModel):
    answer: str
    session_id: str
    citations: list[CitationOut] = []
    confidence: float = 0.0
    faithfulness_score: float = 0.0
    query_type: str = "factual"
    latency_ms: float = 0.0
    flagged: bool = False


class FeedbackRating(str, Enum):
    positive = "positive"
    negative = "negative"


class FeedbackRequest(BaseModel):
    session_id: str
    query: str
    answer: str
    rating: FeedbackRating
