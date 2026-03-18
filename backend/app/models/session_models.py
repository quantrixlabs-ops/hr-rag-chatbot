"""Session & conversation data models — Section 12."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConversationTurn:
    role: str
    content: str
    timestamp: float
    metadata: Optional[dict] = None


@dataclass
class Session:
    session_id: str
    user_id: str
    user_role: str
    turns: list[ConversationTurn]
    created_at: float
    last_active: float
    metadata: dict = field(default_factory=dict)


@dataclass
class ChatResult:
    answer: str
    session_id: str
    citations: list
    confidence: float
    faithfulness_score: float
    query_type: str
    latency_ms: float
    flagged: bool = False
    chunks: list = field(default_factory=list)
    verification: Optional[object] = None
