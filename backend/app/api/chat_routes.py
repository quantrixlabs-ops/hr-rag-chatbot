"""Chat endpoints — Section 20.1."""


import hashlib
import json
import sqlite3
import time
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from backend.app.core.config import get_settings
from backend.app.core.dependencies import get_registry
from backend.app.core.security import get_current_user, sanitize_query, check_prompt_injection, mask_pii, check_repeated_query, log_security_event
from backend.app.models.chat_models import ChatQueryRequest, ChatQueryResponse, CitationOut, FeedbackRequest, RetrievalTrace, User
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

    # Per-tenant quota enforcement
    from backend.app.core.tenant import TenantQuotaEnforcer
    TenantQuotaEnforcer.check_query_quota()

    # Validate query length
    if not req.query or not req.query.strip():
        raise HTTPException(400, "Query cannot be empty")
    if len(req.query) > MAX_QUERY_LENGTH:
        raise HTTPException(400, f"Query exceeds maximum length of {MAX_QUERY_LENGTH} characters")

    # Phase 4: Sanitize and check injection on REST path (matches streaming path)
    query = sanitize_query(req.query.strip())
    if check_prompt_injection(query):
        log_security_event("prompt_injection_blocked", {"query_preview": query[:80]}, user_id=user.user_id)
        raise HTTPException(400, "Query blocked by security filter")

    # Phase 4: Repeated-query abuse detection
    query_hash = hashlib.sha256(query.lower().encode()).hexdigest()[:16]
    if check_repeated_query(user.user_id, query_hash):
        log_security_event("repeated_query_abuse", {"query_hash": query_hash}, user_id=user.user_id)

    # Verify session ownership
    if req.session_id:
        _verify_session_owner(req.session_id, user.user_id)

    svc = _chat_service()
    result = svc.handle_query(query, user, req.session_id)
    citations = [CitationOut(source=c.source, page=c.page, excerpt=c.text_excerpt) for c in result.citations] if req.include_sources else []
    # Build explainability trace if requested
    trace = None
    if req.include_trace:
        trace = RetrievalTrace(
            query_type=result.query_type,
            detected_topics=list({c.source.split(".")[0] for c in result.chunks}) if result.chunks else [],
            chunks_retrieved=len(result.chunks),
            top_sources=list({c.source for c in result.chunks})[:5] if result.chunks else [],
            top_chunk_score=round(result.chunks[0].score, 3) if result.chunks else 0.0,
            verdict=result.verification.verdict if result.verification else "",
        )

    return ChatQueryResponse(
        answer=result.answer, session_id=result.session_id, citations=citations,
        confidence=result.confidence, faithfulness_score=result.faithfulness_score,
        query_type=result.query_type, latency_ms=result.latency_ms, flagged=result.flagged,
        suggested_questions=result.suggested_questions,
        trace=trace,
        intent=result.intent,
        has_contradictions=result.has_contradictions,
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


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user: User = Depends(get_current_user)):
    """Delete a chat session and all its turns."""
    _verify_session_owner(session_id, user.user_id)
    reg = get_registry()
    reg["session_store"].delete_session(session_id)
    return {"status": "deleted", "session_id": session_id}


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


# ── Escalation to HR ────────────────────────────────────────────────────────

class EscalationRequest(BaseModel):
    query: str
    answer: str = ""
    session_id: Optional[str] = None
    reason: str = "User requested human assistance"


@router.post("/escalate")
async def escalate_to_hr(req: EscalationRequest, user: User = Depends(get_current_user)):
    """Escalate a conversation to a human HR representative."""
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        con.execute(
            "INSERT INTO escalations (user_id, session_id, query, answer, reason, status, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (user.user_id, req.session_id, req.query, req.answer, req.reason, "open", time.time()),
        )
    log_security_event("escalation_created", {"query": req.query[:80], "reason": req.reason}, user_id=user.user_id)
    return {"status": "escalated", "message": "Your question has been escalated to an HR representative. You will receive a response shortly."}


# ── Saved Prompts ────────────────────────────────────────────────────────────

class SavedPromptRequest(BaseModel):
    title: str
    prompt_text: str


@router.get("/saved-prompts")
async def list_saved_prompts(user: User = Depends(get_current_user)):
    """List user's saved prompts."""
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        rows = con.execute(
            "SELECT id, title, prompt_text, created_at FROM saved_prompts WHERE user_id=? ORDER BY created_at DESC",
            (user.user_id,),
        ).fetchall()
    return {"prompts": [{"id": r[0], "title": r[1], "prompt_text": r[2], "created_at": r[3]} for r in rows]}


@router.post("/saved-prompts")
async def save_prompt(req: SavedPromptRequest, user: User = Depends(get_current_user)):
    """Save a prompt for reuse."""
    if not req.title.strip() or not req.prompt_text.strip():
        raise HTTPException(400, "Title and prompt text are required")
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        con.execute(
            "INSERT INTO saved_prompts (user_id, title, prompt_text, created_at) VALUES (?,?,?,?)",
            (user.user_id, req.title.strip()[:100], req.prompt_text.strip()[:1000], time.time()),
        )
    return {"status": "saved"}


@router.delete("/saved-prompts/{prompt_id}")
async def delete_saved_prompt(prompt_id: int, user: User = Depends(get_current_user)):
    """Delete a saved prompt."""
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute("SELECT user_id FROM saved_prompts WHERE id=?", (prompt_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Prompt not found")
        if row[0] != user.user_id:
            raise HTTPException(403, "Not your prompt")
        con.execute("DELETE FROM saved_prompts WHERE id=?", (prompt_id,))
    return {"status": "deleted"}


@router.post("/query/stream")
async def chat_query_stream(req: ChatQueryRequest, user: User = Depends(get_current_user)):
    """Streaming version of /chat/query — sends SSE token chunks.

    Improvements:
    - Heartbeat keepalive every 15s to prevent proxy/LB timeout
    - Error recovery: stream error event instead of silent failure
    - Connection timeout: 120s max generation time
    """
    if not req.query or not req.query.strip():
        raise HTTPException(400, "Query cannot be empty")
    if len(req.query) > MAX_QUERY_LENGTH:
        raise HTTPException(400, f"Query exceeds maximum length of {MAX_QUERY_LENGTH} characters")
    if req.session_id:
        _verify_session_owner(req.session_id, user.user_id)

    query = sanitize_query(req.query.strip())
    if check_prompt_injection(query):
        log_security_event("prompt_injection_blocked", {"query_preview": query[:80]}, user_id=user.user_id)
        raise HTTPException(400, "Query blocked by security filter")

    # Phase 4: Repeated-query abuse detection (log only, don't block stream)
    stream_query_hash = hashlib.sha256(query.lower().encode()).hexdigest()[:16]
    if check_repeated_query(user.user_id, stream_query_hash):
        log_security_event("repeated_query_abuse", {"query_hash": stream_query_hash}, user_id=user.user_id)

    reg = get_registry()
    s = get_settings()
    from backend.app.core.security import get_allowed_roles
    from backend.app.prompts.system_prompt import filter_prompt_leakage
    from backend.app.rag.pipeline import _build_prompt

    # Create or load session (same as non-streaming path)
    ss = reg["session_store"]
    if req.session_id:
        session = ss.get_session(req.session_id)
        if not session:
            session = ss.create_session(user.user_id, user.role)
    else:
        session = ss.create_session(user.user_id, user.role)

    role_filter = get_allowed_roles(user.role)
    chunks, _ = reg["retrieval"].retrieve(query, role_filter=role_filter)
    if not chunks:
        async def empty_gen():
            yield f"data: {json.dumps({'token': 'No HR documents found. Please contact HR directly.', 'done': True, 'session_id': session.session_id})}\n\n"
        return StreamingResponse(empty_gen(), media_type="text/event-stream")

    context = reg["ctx"].build(chunks)
    prompt = _build_prompt(query, context, company=s.company_name, hr_contact=s.hr_contact_email)

    # Save user turn before streaming
    ss.add_turn(session.session_id, "user", query)

    STREAM_TIMEOUT = 120  # Max seconds for generation
    HEARTBEAT_INTERVAL = 15  # Seconds between keepalive pings

    async def token_generator():
        full_text = ""
        last_heartbeat = time.time()
        stream_start = time.time()
        token_count = 0

        try:
            for token in reg["llm"].generate_stream(prompt, s.llm_model, s.llm_temperature, s.max_response_tokens):
                now = time.time()

                # Timeout guard — prevent runaway generation
                if now - stream_start > STREAM_TIMEOUT:
                    yield f"data: {json.dumps({'token': '', 'done': True, 'error': 'Response generation timed out', 'full_text': full_text, 'session_id': session.session_id})}\n\n"
                    if full_text:
                        ss.add_turn(session.session_id, "assistant", full_text + "\n\n[Response truncated due to timeout]")
                    return

                full_text += token
                token_count += 1
                yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"

                # Heartbeat keepalive — prevents nginx/LB from closing idle connection
                if now - last_heartbeat > HEARTBEAT_INTERVAL:
                    yield ": heartbeat\n\n"
                    last_heartbeat = now

            # Verify and filter the completed response
            filtered = filter_prompt_leakage(full_text)

            # Phase 4: Content safety + PII scrubbing on streamed output
            from backend.app.core.content_safety import check_content_safety, sanitize_response
            safety = check_content_safety(filtered)
            filtered = sanitize_response(filtered)
            filtered = mask_pii(filtered)

            from backend.app.services.verification_service import AnswerVerifier
            verifier = AnswerVerifier()
            verification = verifier.verify(filtered, chunks, query)
            citations = [
                {"source": c.source, "page": c.page, "excerpt": c.text_excerpt}
                for c in verification.citations
            ]
            # Save assistant turn
            ss.add_turn(session.session_id, "assistant", filtered)

            from backend.app.rag.pipeline import RAGPipeline
            suggestions = RAGPipeline._generate_suggestions(None, query, filtered, chunks)

            # Phase 2: Detect contradictions in streamed response (Phase 4: safe fallback)
            from backend.app.services.contradiction_detector import ContradictionDetector, ContradictionResult
            try:
                contradiction_result = ContradictionDetector().detect(chunks, query)
            except Exception:
                contradiction_result = ContradictionResult(has_contradictions=False, contradictions=[], warning_message="")

            final_event = {
                "token": "", "done": True,
                "full_text": filtered,
                "session_id": session.session_id,
                "citations": citations,
                "confidence": round(verification.faithfulness_score, 3),
                "faithfulness_score": round(verification.faithfulness_score, 3),
                "suggested_questions": suggestions,
                "token_count": token_count,
                "generation_ms": round((time.time() - stream_start) * 1000),
                "intent": "policy_lookup",  # Streaming doesn't run full analyzer yet
                "has_contradictions": contradiction_result.has_contradictions,
            }
            yield f"data: {json.dumps(final_event)}\n\n"

        except GeneratorExit:
            # Client disconnected — save what we have
            if full_text:
                try:
                    ss.add_turn(session.session_id, "assistant", full_text + "\n\n[Client disconnected]")
                except Exception:
                    pass
        except Exception as e:
            # Stream error event to client instead of silent failure
            import structlog
            structlog.get_logger().error("stream_error", error=str(e), user_id=user.user_id)
            error_msg = "I encountered an error generating the response. Please try again."
            yield f"data: {json.dumps({'token': '', 'done': True, 'error': error_msg, 'session_id': session.session_id})}\n\n"
            if full_text:
                try:
                    ss.add_turn(session.session_id, "assistant", full_text + f"\n\n[Error: {error_msg}]")
                except Exception:
                    pass

    return StreamingResponse(
        token_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
