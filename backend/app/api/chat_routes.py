"""Chat endpoints — Section 20.1."""


import hashlib
import json
import sqlite3
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import StreamingResponse

from backend.app.core.config import get_settings
from backend.app.core.dependencies import get_registry
from backend.app.core.security import get_current_user, sanitize_query, check_prompt_injection, mask_pii
from backend.app.models.chat_models import ChatQueryRequest, ChatQueryResponse, CitationOut, FeedbackRequest, User
from backend.app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])

MAX_QUERY_LENGTH = 1000

# Per-user query rate limiting: 10 queries/min
_user_query_rate: dict[str, list[float]] = defaultdict(list)
USER_QUERY_RATE_LIMIT = 10
USER_QUERY_RATE_WINDOW = 60


def _check_user_query_rate(user_id: str) -> None:
    now = time.time()
    _user_query_rate[user_id] = [t for t in _user_query_rate[user_id]
                                  if now - t < USER_QUERY_RATE_WINDOW]
    if len(_user_query_rate[user_id]) >= USER_QUERY_RATE_LIMIT:
        raise HTTPException(429, "Query rate limit exceeded. Please wait before sending more questions.")
    _user_query_rate[user_id].append(now)


def _chat_service() -> ChatService:
    reg = get_registry()
    return reg["chat_service"]


def _verify_session_owner(session_id: str, user_id: str) -> None:
    """Verify that the session belongs to the requesting user.

    Fails CLOSED: if session does not exist OR owner does not match, reject.
    """
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT user_id FROM sessions WHERE session_id=?", (session_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Session not found")
    if row[0] != user_id:
        raise HTTPException(403, "You do not have access to this session")


@router.post("/query", response_model=ChatQueryResponse)
async def chat_query(req: ChatQueryRequest, user: User = Depends(get_current_user)):
    # Per-user rate limiting
    _check_user_query_rate(user.user_id)

    # Validate query length
    if not req.query or not req.query.strip():
        raise HTTPException(400, "Query cannot be empty")
    if len(req.query) > MAX_QUERY_LENGTH:
        raise HTTPException(400, f"Query exceeds maximum length of {MAX_QUERY_LENGTH} characters")

    # Verify session ownership
    if req.session_id:
        _verify_session_owner(req.session_id, user.user_id)

    svc = _chat_service()
    result = svc.handle_query(req.query.strip(), user, req.session_id)
    citations = [CitationOut(source=c.source, page=c.page, excerpt=c.text_excerpt) for c in result.citations] if req.include_sources else []
    return ChatQueryResponse(
        answer=result.answer, session_id=result.session_id, citations=citations,
        confidence=result.confidence, faithfulness_score=result.faithfulness_score,
        query_type=result.query_type, latency_ms=result.latency_ms, flagged=result.flagged,
        suggested_questions=result.suggested_questions,
    )


@router.get("/sessions")
async def list_sessions(user: User = Depends(get_current_user)):
    reg = get_registry()
    sessions = reg["session_store"].get_user_sessions(user.user_id)
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/sessions/{session_id}/history")
async def session_history(session_id: str, user: User = Depends(get_current_user)):
    # Verify session exists and belongs to user (raises 404/403)
    _verify_session_owner(session_id, user.user_id)
    reg = get_registry()
    turns = reg["session_store"].get_recent_turns(session_id, limit=100)
    return {"session_id": session_id, "turns": [{"role": t.role, "content": t.content, "timestamp": t.timestamp} for t in turns], "count": len(turns)}


@router.post("/feedback")
async def feedback(req: FeedbackRequest, user: User = Depends(get_current_user)):
    # Verify session exists and belongs to user (raises 404/403)
    _verify_session_owner(req.session_id, user.user_id)
    s = get_settings()
    # SECTION 3: Store query hash, not raw query text
    query_hash = hashlib.sha256(mask_pii(req.query).encode()).hexdigest()[:16]
    with sqlite3.connect(s.db_path) as con:
        con.execute("INSERT INTO feedback (session_id,query,answer,rating,timestamp,user_id) VALUES (?,?,?,?,?,?)",
                    (req.session_id, query_hash, req.answer, req.rating.value, time.time(), user.user_id))
    return {"status": "recorded", "rating": req.rating.value}


@router.post("/query/stream")
async def chat_query_stream(req: ChatQueryRequest, user: User = Depends(get_current_user)):
    """Streaming version of /chat/query — sends SSE token chunks."""
    if not req.query or not req.query.strip():
        raise HTTPException(400, "Query cannot be empty")
    if len(req.query) > MAX_QUERY_LENGTH:
        raise HTTPException(400, f"Query exceeds maximum length of {MAX_QUERY_LENGTH} characters")
    if req.session_id:
        _verify_session_owner(req.session_id, user.user_id)

    query = sanitize_query(req.query.strip())
    if check_prompt_injection(query):
        raise HTTPException(400, "Query blocked by security filter")

    reg = get_registry()
    s = get_settings()
    from backend.app.core.security import get_allowed_roles
    from backend.app.rag.context_builder import ContextBuilder
    from backend.app.prompts.system_prompt import filter_prompt_leakage
    from backend.app.rag.pipeline import _build_prompt

    role_filter = get_allowed_roles(user.role)
    chunks, _ = reg["retrieval"].retrieve(query, role_filter=role_filter)
    if not chunks:
        async def empty_gen():
            yield f"data: {json.dumps({'token': 'No HR documents found. Please contact HR directly.', 'done': True})}\n\n"
        return StreamingResponse(empty_gen(), media_type="text/event-stream")

    context = reg["ctx"].build(chunks)
    prompt = _build_prompt(query, context, company=s.company_name, hr_contact=s.hr_contact_email)

    async def token_generator():
        full_text = ""
        for token in reg["llm"].generate_stream(prompt, s.llm_model, s.llm_temperature, s.max_response_tokens):
            full_text += token
            yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"
        # Verify and filter the completed response
        filtered = filter_prompt_leakage(full_text)
        from backend.app.services.verification_service import AnswerVerifier
        verifier = AnswerVerifier()
        verification = verifier.verify(filtered, chunks, query)
        citations = [
            {"source": c.source, "page": c.page, "excerpt": c.text_excerpt}
            for c in verification.citations
        ]
        # Generate follow-up suggestions from chunks
        from backend.app.rag.pipeline import RAGPipeline
        suggestions = RAGPipeline._generate_suggestions(None, query, filtered, chunks)
        yield f"data: {json.dumps({'token': '', 'done': True, 'full_text': filtered, 'citations': citations, 'confidence': round(verification.faithfulness_score, 3), 'faithfulness_score': round(verification.faithfulness_score, 3), 'suggested_questions': suggestions})}\n\n"

    return StreamingResponse(token_generator(), media_type="text/event-stream")
