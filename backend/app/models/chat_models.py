"""Pydantic request/response models for chat — Sections 4 & 20."""


from enum import Enum

from typing import List, Optional

from pydantic import BaseModel, Field


class User(BaseModel):
    user_id: str
    role: str = "employee"
    department: Optional[str] = None


class ChatQueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    include_sources: bool = True
    include_trace: bool = False


class CitationOut(BaseModel):
    source: str
    page: Optional[int] = None
    excerpt: str = ""


class ChatQueryResponse(BaseModel):
    answer: str
    session_id: str
    citations: List[CitationOut] = []
    confidence: float = 0.0
    faithfulness_score: float = 0.0
    query_type: str = "factual"
    latency_ms: float = 0.0
    flagged: bool = False
    suggested_questions: List[str] = []


class FeedbackRating(str, Enum):
    positive = "positive"
    negative = "negative"


class FeedbackRequest(BaseModel):
    session_id: str
    query: str
    answer: str
    rating: FeedbackRating
