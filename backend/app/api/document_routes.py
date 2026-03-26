"""Document management endpoints — Section 20.2."""


import json
import os
import sqlite3
import time
from collections import defaultdict
from typing import List

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend.app.core.config import get_settings
from backend.app.core.dependencies import get_registry
from backend.app.core.security import can_access_document, get_current_user, log_document_upload, require_role
from backend.app.models.chat_models import User
from backend.app.models.document_models import DocumentUploadResponse, ReindexRequest

logger = structlog.get_logger()
router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".md", ".txt"}
MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB


def _remove_document_chunks(document_id: str, s=None) -> int:
    """Remove a document's chunks from FAISS + BM25 + DB. Returns chunks removed."""
    if s is None:
        s = get_settings()
    reg = get_registry()
    vs = reg["vector_store"]
    bm25 = reg["bm25"]

    keep_indices = []
    keep_metadata = []
    removed = 0
    for i, meta in enumerate(vs.metadata):
        if meta.document_id != document_id:
            keep_indices.append(i)
            keep_metadata.append(meta)
        else:
            removed += 1

    if removed > 0:
        import faiss
        if keep_indices:
            old_index = vs.index
            new_index = faiss.IndexFlatIP(vs.dimension)
            for idx in keep_indices:
                vec = old_index.reconstruct(idx).reshape(1, -1)
                new_index.add(vec)
            vs.index = new_index
            vs.metadata = keep_metadata
        else:
            vs.index = faiss.IndexFlatIP(vs.dimension)
            vs.metadata = []
        bm25.build_index(vs.metadata)
        vs.save()

    with sqlite3.connect(s.db_path) as con:
        row = con.execute("SELECT source_filename FROM documents WHERE document_id=?", (document_id,)).fetchone()
        con.execute("DELETE FROM documents WHERE document_id=?", (document_id,))
    if row:
        upload_path = os.path.join(s.upload_dir, row[0])
        if os.path.exists(upload_path):
            os.remove(upload_path)

    logger.info("document_removed", document_id=document_id, chunks_removed=removed)
    return removed

# Upload rate limiting: 200 uploads per minute per user (supports large batch upload)
_upload_rate: defaultdict = defaultdict(list)
UPLOAD_RATE_LIMIT = 200
UPLOAD_RATE_WINDOW = 60


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload(
    file: UploadFile = File(...),
    title: str = Form(...),
    category: str = Form("policy"),
    access_roles: str = Form('["employee","manager","hr_admin"]'),
    effective_date: str = Form(""),
    version: str = Form("1.0"),
    user: User = Depends(get_current_user),
):
    # Phase C: HR Team can upload (pending approval); HR Head+ uploads are auto-approved
    _HR_UPLOAD_ROLES = {"hr_team", "hr_head", "hr_admin", "admin", "super_admin"}
    if user.role not in _HR_UPLOAD_ROLES:
        require_role(user, "hr_admin")  # Fallback — blocks non-HR roles

    # Per-tenant upload & document count quota enforcement
    from backend.app.core.tenant import TenantQuotaEnforcer
    TenantQuotaEnforcer.check_upload_quota()
    TenantQuotaEnforcer.check_document_count_quota()

    # Upload rate limiting: 5 per minute per user
    now = time.time()
    _upload_rate[user.user_id] = [t for t in _upload_rate[user.user_id] if now - t < UPLOAD_RATE_WINDOW]
    if len(_upload_rate[user.user_id]) >= UPLOAD_RATE_LIMIT:
        raise HTTPException(429, "Upload rate limit exceeded. Please wait before uploading more documents.")
    _upload_rate[user.user_id].append(now)

    # Sanitize filename — prevent path traversal (DOC-010)
    raw_filename = file.filename or "unknown"
    filename = os.path.basename(raw_filename)
    # Reject any remaining traversal attempts
    if not filename or filename.startswith(".") or ".." in filename:
        raise HTTPException(400, "Invalid filename")

    # Validate file extension (DOC-005)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            f"Unsupported file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    content = await file.read()

    # Validate empty file (DOC-006)
    if len(content) == 0:
        raise HTTPException(400, "Uploaded file is empty")

    # Validate file size
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(400, f"File exceeds maximum size of {MAX_UPLOAD_SIZE // (1024*1024)} MB")

    # Check for duplicate documents — auto-replace if same content or filename
    import hashlib
    content_hash = hashlib.sha256(content).hexdigest()
    s = get_settings()
    from backend.app.core.tenant import get_current_tenant
    tenant_id = get_current_tenant()
    old_doc_id_to_replace = None
    with sqlite3.connect(s.db_path) as con:
        # Check by content hash — identical content replaces existing
        hash_match = con.execute(
            "SELECT document_id, title FROM documents WHERE content_hash=? AND tenant_id=?",
            (content_hash, tenant_id)
        ).fetchone()
        if hash_match:
            old_doc_id_to_replace = hash_match[0]
            logger.info("duplicate_content_replace", old_id=old_doc_id_to_replace,
                        old_title=hash_match[1], filename=filename)
        else:
            # Check by filename — same filename replaces existing
            fname_match = con.execute(
                "SELECT document_id, title, version FROM documents WHERE source_filename=? AND tenant_id=?",
                (filename, tenant_id)
            ).fetchone()
            if fname_match:
                old_doc_id_to_replace = fname_match[0]
                logger.info("same_filename_replace", old_id=old_doc_id_to_replace,
                            old_title=fname_match[1], old_version=fname_match[2],
                            new_version=version, filename=filename)

    # Sanitize title to prevent stored XSS
    import html as html_mod
    title = html_mod.escape(title.strip(), quote=True)
    if not title:
        raise HTTPException(400, "Document title cannot be empty")

    # Auto-classify document category if set to "auto" or default "policy"
    if category in ("auto", "policy"):
        from backend.app.rag.query_analyzer import auto_classify_document
        content_preview = content.decode("utf-8", errors="ignore")[:1000]
        detected = auto_classify_document(title, content_preview)
        if detected != "policy" or category == "auto":
            category = detected
            logger.info("document_auto_classified", title=title, category=category)

    # If replacing an old version, remove it from FAISS + DB first
    if old_doc_id_to_replace:
        _remove_document_chunks(old_doc_id_to_replace, s)

    roles = json.loads(access_roles)
    reg = get_registry()
    result = reg["ingestion"].ingest(content, filename, title, category, roles, effective_date, version, user.user_id)
    if result.status == "rejected":
        raise HTTPException(
            400,
            f"Document '{filename}' was rejected. "
            "It may be a test document (filename matches test patterns), "
            f"exceed the maximum chunk limit ({2000}), or be larger than 100 MB."
        )
    if result.status != "indexed":
        raise HTTPException(
            422,
            f"Document ingestion failed for '{filename}'. "
            "The file could not be processed — it may be empty, corrupted, or a scanned PDF."
        )
    log_document_upload(user, result.document_id, category, filename)

    # Phase C: Document approval workflow
    # HR Head/Admin uploads are auto-approved; HR Team uploads require approval
    _AUTO_APPROVE_ROLES = {"hr_head", "hr_admin", "admin", "super_admin"}
    if user.role in _AUTO_APPROVE_ROLES:
        approval_status = "approved"
        approved_by = user.user_id
        approved_at = time.time()
    else:
        approval_status = "pending"
        approved_by = ""
        approved_at = None

    with sqlite3.connect(s.db_path) as con:
        if approved_at:
            con.execute(
                "UPDATE documents SET approval_status=?, approved_by=?, approved_at=? WHERE document_id=?",
                (approval_status, approved_by, approved_at, result.document_id),
            )
        else:
            con.execute(
                "UPDATE documents SET approval_status=?, approved_by=? WHERE document_id=?",
                (approval_status, approved_by, result.document_id),
            )

    # Phase D: Notify HR Head when document needs approval
    if approval_status == "pending":
        try:
            from backend.app.api.notification_routes import notify_role
            notify_role("hr_head", f"Document pending approval: {title[:80]}",
                        "A new document was uploaded and requires your approval.",
                        "action", f"/documents/{result.document_id}", s.db_path)
        except Exception:
            pass

    resp = DocumentUploadResponse(document_id=result.document_id, chunk_count=result.chunk_count, status=result.status, processing_time_ms=result.processing_time_ms)
    if old_doc_id_to_replace:
        logger.info("version_replaced", old_id=old_doc_id_to_replace, new_id=result.document_id, version=version)

    # Invalidate cached answers that cited this document (content may have changed)
    from backend.app.core.semantic_cache import invalidate_on_document_change
    invalidate_on_document_change(filename)

    return resp


@router.get("/{document_id}/content")
async def get_document_content(
    document_id: str,
    user: User = Depends(get_current_user),
    page: int = 0,
    window: int = 5,
):
    """Return document content with optional pagination.

    When page > 0, only extract pages in [page-window, page+window] range
    from the PDF — avoids re-parsing all 600 pages on every citation click.
    When page == 0 (default), returns all pages (legacy behaviour).
    """
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT title, category, source_filename, access_roles, version, page_count, chunk_count "
            "FROM documents WHERE document_id=?",
            (document_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Document not found")

    roles = json.loads(row[3])
    if not can_access_document(user.role, roles):
        raise HTTPException(403, "Access denied to this document")

    # Read the source file
    filepath = os.path.join(s.upload_dir, row[2])
    if not os.path.exists(filepath):
        raise HTTPException(404, "Source file not found on disk")

    ext = os.path.splitext(row[2])[1].lower()
    pages = []
    total_pages = 0

    paginated = page > 0  # True = fast path, only extract a page window

    if ext == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                total_pages = len(pdf.pages)
                if paginated:
                    lo = max(0, page - 1 - window)
                    hi = min(total_pages, page - 1 + window + 1)
                    for i in range(lo, hi):
                        text = pdf.pages[i].extract_text() or ""
                        pages.append({"page": i + 1, "text": text})
                else:
                    for i, pg in enumerate(pdf.pages, 1):
                        text = pg.extract_text() or ""
                        pages.append({"page": i, "text": text})
        except Exception:
            with open(filepath, "r", errors="ignore") as f:
                pages = [{"page": 1, "text": f.read()}]
            total_pages = 1
    elif ext == ".docx":
        try:
            import docx
            doc = docx.Document(filepath)
            full_text = "\n".join(p.text for p in doc.paragraphs)
            pages = [{"page": 1, "text": full_text}]
        except Exception:
            pages = [{"page": 1, "text": "(Could not read .docx file)"}]
        total_pages = 1
    else:
        with open(filepath, "r", errors="ignore") as f:
            content = f.read()
        # Split into sections by headings for better navigation
        lines = content.split("\n")
        current_page = 1
        current_text: list[str] = []
        for line in lines:
            if line.startswith("# ") and current_text:
                pages.append({"page": current_page, "text": "\n".join(current_text)})
                current_page += 1
                current_text = [line]
            else:
                current_text.append(line)
        if current_text:
            pages.append({"page": current_page, "text": "\n".join(current_text)})
        total_pages = len(pages)

    # Chunk highlights — skip on paginated requests (not needed for viewer)
    chunk_highlights: list[dict] = []
    if not paginated:
        reg = get_registry()
        vs = reg["vector_store"]
        for meta in vs.metadata:
            if meta.document_id == document_id:
                chunk_highlights.append({
                    "chunk_index": meta.chunk_index,
                    "page": meta.page,
                    "text_preview": meta.text[:150],
                    "section": meta.section_heading or "",
                })

    return {
        "document_id": document_id,
        "title": row[0],
        "category": row[1],
        "version": row[4],
        "page_count": total_pages or len(pages),
        "chunk_count": row[6],
        "pages": pages,
        "chunks": sorted(chunk_highlights, key=lambda c: c["chunk_index"]) if chunk_highlights else [],
    }


@router.get("")
async def list_docs(user: User = Depends(get_current_user)):
    s = get_settings()
    from backend.app.core.tenant import get_current_tenant
    tenant_id = get_current_tenant()
    _HR_ROLES = {"hr_team", "hr_head", "hr_admin", "admin", "super_admin"}
    with sqlite3.connect(s.db_path) as con:
        rows = con.execute(
            "SELECT document_id,title,category,access_roles,chunk_count,uploaded_at,version,"
            "COALESCE(approval_status,'approved'),COALESCE(approved_by,''),uploaded_by "
            "FROM documents WHERE tenant_id=? ORDER BY uploaded_at DESC",
            (tenant_id,),
        ).fetchall()
    docs = []
    for r in rows:
        roles = json.loads(r[3])
        approval = r[7]
        # Phase C: Non-HR users only see approved documents
        if user.role not in _HR_ROLES and approval != "approved":
            continue
        if can_access_document(user.role, roles):
            docs.append({
                "document_id": r[0], "title": r[1], "category": r[2],
                "access_roles": roles, "chunk_count": r[4], "uploaded_at": r[5],
                "version": r[6], "approval_status": approval,
                "approved_by": r[8], "uploaded_by": r[9],
            })
    return {"documents": docs, "count": len(docs)}


# ── Phase C: Document Approval Workflow ───────────────────────────────────────

class DocumentApprovalRequest(BaseModel):
    action: str  # "approve" or "reject"
    comment: str = ""


@router.get("/pending")
async def list_pending_documents(user: User = Depends(get_current_user)):
    """List documents awaiting approval — HR Head+ only."""
    require_role(user, "hr_admin")
    s = get_settings()
    from backend.app.core.tenant import get_current_tenant
    tenant_id = get_current_tenant()
    with sqlite3.connect(s.db_path) as con:
        rows = con.execute(
            "SELECT d.document_id, d.title, d.category, d.chunk_count, d.uploaded_at, "
            "d.version, d.source_filename, d.uploaded_by, "
            "COALESCE(u.full_name, u.username, d.uploaded_by) "
            "FROM documents d LEFT JOIN users u ON d.uploaded_by = u.user_id "
            "WHERE d.approval_status='pending' AND d.tenant_id=? "
            "ORDER BY d.uploaded_at ASC",
            (tenant_id,),
        ).fetchall()
    return {
        "pending": [
            {
                "document_id": r[0], "title": r[1], "category": r[2],
                "chunk_count": r[3], "uploaded_at": r[4], "version": r[5],
                "source_filename": r[6], "uploaded_by": r[7],
                "uploaded_by_name": r[8],
            }
            for r in rows
        ],
        "count": len(rows),
    }


@router.post("/{document_id}/approve")
async def approve_or_reject_document(
    document_id: str, req: DocumentApprovalRequest, user: User = Depends(get_current_user),
):
    """Approve or reject a pending document — HR Head+ only.

    Approved documents become visible to all users with matching access roles.
    Rejected documents are removed from the index and deleted.
    """
    require_role(user, "hr_admin")
    if req.action not in ("approve", "reject"):
        raise HTTPException(400, "Action must be 'approve' or 'reject'")

    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT title, approval_status, uploaded_by FROM documents WHERE document_id=?",
            (document_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Document not found")
        if row[1] != "pending":
            raise HTTPException(409, f"Document is already {row[1]}")

        if req.action == "approve":
            now = time.time()
            con.execute(
                "UPDATE documents SET approval_status='approved', approved_by=?, approved_at=? "
                "WHERE document_id=?",
                (user.user_id, now, document_id),
            )
            from backend.app.core.security import log_security_event
            log_security_event("document_approved", {
                "document_id": document_id, "title": row[0],
                "uploaded_by": row[2], "comment": req.comment,
            }, user_id=user.user_id)
            # Phase D: Notify uploader
            try:
                from backend.app.api.notification_routes import create_notification
                if row[2]:  # uploaded_by
                    create_notification(
                        row[2], f"Document approved: {row[0][:80]}",
                        "Your uploaded document has been approved and is now searchable.",
                        "success", f"/documents/{document_id}",
                    )
            except Exception:
                pass
            return {"status": "approved", "document_id": document_id, "title": row[0]}
        else:
            # Reject — remove from index and mark as rejected
            from backend.app.core.security import log_security_event
            con.execute(
                "UPDATE documents SET approval_status='rejected', approved_by=?, approved_at=? "
                "WHERE document_id=?",
                (user.user_id, time.time(), document_id),
            )
            # Remove chunks from search index so rejected docs aren't searchable
            removed = _remove_document_chunks(document_id, s)
            log_security_event("document_rejected", {
                "document_id": document_id, "title": row[0],
                "uploaded_by": row[2], "comment": req.comment,
                "chunks_removed": removed,
            }, user_id=user.user_id)
            # Phase D: Notify uploader
            try:
                from backend.app.api.notification_routes import create_notification
                if row[2]:  # uploaded_by
                    create_notification(
                        row[2], f"Document rejected: {row[0][:80]}",
                        f"Reason: {req.comment or 'No reason given'}",
                        "warning", f"/documents/{document_id}",
                    )
            except Exception:
                pass
            return {"status": "rejected", "document_id": document_id, "title": row[0]}


@router.delete("/{document_id}")
async def delete_doc(document_id: str, user: User = Depends(get_current_user)):
    require_role(user, "hr_admin")
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute("SELECT title FROM documents WHERE document_id=?", (document_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Document {document_id} not found")
    removed = _remove_document_chunks(document_id, s)

    # Invalidate cached answers that cited the deleted document
    from backend.app.core.semantic_cache import invalidate_on_document_change
    invalidate_on_document_change(row[0])

    return {"status": "deleted", "document_id": document_id, "chunks_removed": removed}


class BatchDeleteRequest(BaseModel):
    document_ids: List[str]


@router.post("/batch-delete")
async def batch_delete(req: BatchDeleteRequest, user: User = Depends(get_current_user)):
    """Delete multiple documents and their indexed chunks in one operation."""
    require_role(user, "hr_admin")

    if not req.document_ids:
        raise HTTPException(400, "No document IDs provided")
    if len(req.document_ids) > 50:
        raise HTTPException(400, "Cannot delete more than 50 documents at once")

    s = get_settings()
    reg = get_registry()
    vs = reg["vector_store"]
    bm25 = reg["bm25"]

    ids_to_delete = set(req.document_ids)

    # Verify all documents exist and collect filenames
    filenames = {}  # type: dict
    with sqlite3.connect(s.db_path) as con:
        for doc_id in ids_to_delete:
            row = con.execute("SELECT title, source_filename FROM documents WHERE document_id=?", (doc_id,)).fetchone()
            if row:
                filenames[doc_id] = row[1]

    if not filenames:
        raise HTTPException(404, "None of the specified documents were found")

    # Rebuild FAISS index excluding all deleted documents at once
    keep_indices = []
    keep_metadata = []
    removed_count = 0
    for i, meta in enumerate(vs.metadata):
        if meta.document_id not in ids_to_delete:
            keep_indices.append(i)
            keep_metadata.append(meta)
        else:
            removed_count += 1

    if removed_count > 0:
        import faiss
        if keep_indices:
            old_index = vs.index
            new_index = faiss.IndexFlatIP(vs.dimension)
            for idx in keep_indices:
                vec = old_index.reconstruct(idx)
                vec = vec.reshape(1, -1)
                new_index.add(vec)
            vs.index = new_index
            vs.metadata = keep_metadata
        else:
            vs.index = faiss.IndexFlatIP(vs.dimension)
            vs.metadata = []

        bm25.build_index(vs.metadata)
        vs.save()
        logger.info("batch_delete_from_index", doc_count=len(filenames),
                     removed_chunks=removed_count, remaining=vs.total_chunks)

    # Remove from database and disk
    deleted_ids = []
    with sqlite3.connect(s.db_path) as con:
        for doc_id in filenames:
            con.execute("DELETE FROM documents WHERE document_id=?", (doc_id,))
            deleted_ids.append(doc_id)

    for doc_id, fname in filenames.items():
        upload_path = os.path.join(s.upload_dir, fname)
        if os.path.exists(upload_path):
            os.remove(upload_path)

    # Invalidate cached answers that cited any of the deleted documents
    from backend.app.core.semantic_cache import invalidate_on_document_change
    for fname in filenames.values():
        invalidate_on_document_change(fname)

    return {
        "status": "deleted",
        "deleted_count": len(deleted_ids),
        "chunks_removed": removed_count,
        "deleted_ids": deleted_ids,
    }


@router.post("/reindex")
async def reindex(req: ReindexRequest, user: User = Depends(get_current_user)):
    require_role(user, "hr_admin")
    reg = get_registry()
    s = get_settings()

    if req.document_id:
        # Reindex a specific document
        with sqlite3.connect(s.db_path) as con:
            row = con.execute(
                "SELECT source_filename, title, category, access_roles, effective_date, version, uploaded_by FROM documents WHERE document_id=?",
                (req.document_id,)
            ).fetchone()
        if not row:
            raise HTTPException(404, f"Document {req.document_id} not found")

        filepath = os.path.join(s.upload_dir, row[0])
        if not os.path.exists(filepath):
            raise HTTPException(404, f"Source file not found on disk: {row[0]}")

        # Delete old chunks first
        vs = reg["vector_store"]
        keep_indices = [i for i, m in enumerate(vs.metadata) if m.document_id != req.document_id]
        if len(keep_indices) < len(vs.metadata):
            import faiss
            new_index = faiss.IndexFlatIP(vs.dimension)
            keep_metadata = []
            for idx in keep_indices:
                vec = vs.index.reconstruct(idx)
                vec = vec.reshape(1, -1)
                new_index.add(vec)
                keep_metadata.append(vs.metadata[idx])
            vs.index = new_index
            vs.metadata = keep_metadata

        # Re-ingest
        with open(filepath, "rb") as f:
            content = f.read()
        roles = json.loads(row[3])
        result = reg["ingestion"].ingest(content, row[0], row[1], row[2], roles, row[4], row[5], row[6])

        # Remove old DB entry (ingestion creates new one)
        with sqlite3.connect(s.db_path) as con:
            con.execute("DELETE FROM documents WHERE document_id=?", (req.document_id,))

        return {"status": "complete", "document_id": result.document_id, "chunk_count": result.chunk_count}
    else:
        # Full reindex: rebuild everything from uploaded files
        with sqlite3.connect(s.db_path) as con:
            all_docs = con.execute(
                "SELECT document_id, source_filename, title, category, access_roles, "
                "effective_date, version, uploaded_by FROM documents"
            ).fetchall()
        if not all_docs:
            return {"status": "complete", "reindexed": 0, "message": "No documents to reindex"}

        # Clear entire vector store
        import faiss
        vs = reg["vector_store"]
        bm25 = reg["bm25"]
        vs.index = faiss.IndexFlatIP(vs.dimension)
        vs.metadata = []

        results = []
        errors = []
        for doc in all_docs:
            doc_id, fname, title_val, cat, roles_json, eff_date, ver, uploader = doc
            filepath = os.path.join(s.upload_dir, fname)
            if not os.path.exists(filepath):
                errors.append({"document_id": doc_id, "error": f"File missing: {fname}"})
                continue
            try:
                with open(filepath, "rb") as f:
                    file_content = f.read()
                roles_list = json.loads(roles_json)
                r = reg["ingestion"].ingest(file_content, fname, title_val, cat, roles_list, eff_date, ver, uploader)
                # Remove old DB entry (ingest creates new)
                with sqlite3.connect(s.db_path) as con:
                    con.execute("DELETE FROM documents WHERE document_id=?", (doc_id,))
                results.append({"old_id": doc_id, "new_id": r.document_id, "chunks": r.chunk_count})
            except Exception as e:
                errors.append({"document_id": doc_id, "error": str(e)})

        bm25.build_index(vs.metadata)
        vs.save()
        logger.info("full_reindex_complete", reindexed=len(results), errors=len(errors), total_chunks=vs.total_chunks)
        return {"status": "complete", "reindexed": len(results), "errors": errors, "total_chunks": vs.total_chunks}


# ── Phase 2: Async upload (Celery-backed) ────────────────────────────────────

@router.post("/upload-async", status_code=202)
async def upload_async(
    file: UploadFile = File(...),
    title: str = Form(...),
    category: str = Form("policy"),
    access_roles: str = Form('["employee","manager","hr_admin"]'),
    version: str = Form("1.0"),
    user: User = Depends(get_current_user),
):
    """Async document upload — returns 202 + job_id immediately.

    File is saved to disk, Celery worker handles ingestion in the background.
    Poll GET /documents/jobs/{job_id} for status.
    """
    require_role(user, "hr_admin")
    from backend.app.core.permissions import require_permission
    if not require_permission(user.role, "documents.upload"):
        raise HTTPException(403, "Insufficient permissions to upload documents")

    s = get_settings()

    # Rate limit
    now = time.time()
    _upload_rate[user.user_id] = [t for t in _upload_rate[user.user_id] if now - t < UPLOAD_RATE_WINDOW]
    if len(_upload_rate[user.user_id]) >= UPLOAD_RATE_LIMIT:
        raise HTTPException(429, "Upload rate limit exceeded. Try again in a minute.")
    _upload_rate[user.user_id].append(now)

    # Validate filename
    raw_filename = file.filename or "unknown"
    filename = os.path.basename(raw_filename)
    if not filename or filename.startswith(".") or ".." in filename:
        raise HTTPException(400, "Invalid filename")

    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(400, "Uploaded file is empty")
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(400, f"File exceeds {MAX_UPLOAD_SIZE // (1024*1024)} MB limit")

    import hashlib, uuid as _uuid, html as html_mod
    content_hash = hashlib.sha256(content).hexdigest()
    title = html_mod.escape(title.strip(), quote=True)
    if not title:
        raise HTTPException(400, "Document title cannot be empty")

    # Auto-replace duplicate (tenant-scoped)
    from backend.app.core.tenant import get_current_tenant
    tenant_id = get_current_tenant()
    with sqlite3.connect(s.db_path) as con:
        dup = con.execute("SELECT document_id FROM documents WHERE content_hash=? AND tenant_id=?", (content_hash, tenant_id)).fetchone()
        if dup:
            _remove_document_chunks(dup[0], s)
            logger.info("async_duplicate_replaced", old_id=dup[0])

    # Save file to disk (worker reads it from here)
    document_id = str(_uuid.uuid4())
    safe_filename = f"{document_id}_{filename}"
    file_path = os.path.join(s.upload_dir, safe_filename)
    with open(file_path, "wb") as f:
        f.write(content)

    # Register document in SQLite as pending
    roles = json.loads(access_roles)
    now_ts = time.time()
    with sqlite3.connect(s.db_path) as con:
        con.execute(
            "INSERT INTO documents (document_id,title,category,access_roles,source_filename,"
            "uploaded_by,uploaded_at,chunk_count,content_hash,ingestion_status) "
            "VALUES (?,?,?,?,?,?,?,0,?,'pending')",
            (document_id, title, category, json.dumps(roles), safe_filename, user.user_id, now_ts, content_hash),
        )

    # Enqueue Celery ingestion task
    try:
        from backend.app.workers.ingestion_tasks import ingest_document as _ingest_task
        job = _ingest_task.delay(
            document_id=document_id,
            file_path=file_path,
            filename=filename,
            category=category,
            access_roles=roles,
            tenant_id=tenant_id,
        )
        job_id = job.id
    except Exception as e:
        logger.error("celery_enqueue_failed", error=str(e), doc_id=document_id)
        # Fallback: mark as failed so admin can retry
        with sqlite3.connect(s.db_path) as con:
            con.execute("UPDATE documents SET ingestion_status='failed' WHERE document_id=?", (document_id,))
        raise HTTPException(503, "Task queue unavailable. Document saved but not ingested. Use retry endpoint.")

    # Audit log
    from backend.app.database.postgres import write_audit_log
    write_audit_log(
        action="document.upload_async",
        target_type="document",
        target_id=document_id,
        extra={"filename": filename, "category": category, "job_id": job_id},
    )

    logger.info("document_upload_async_queued", doc_id=document_id, job_id=job_id, filename=filename)
    return {
        "status": "pending",
        "document_id": document_id,
        "job_id": job_id,
        "message": f"Document '{filename}' queued for ingestion. Poll /documents/jobs/{job_id} for status.",
    }


# ── Phase 2: Job status polling ───────────────────────────────────────────────

@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, user: User = Depends(get_current_user)):
    """Poll the status of an async ingestion job."""
    require_role(user, "hr_admin")
    try:
        from backend.app.workers.celery_app import app as celery_app
        result = celery_app.AsyncResult(job_id)
        state = result.state
        info = result.info or {}

        if state == "SUCCESS":
            return {"job_id": job_id, "status": "done", "result": info}
        elif state == "FAILURE":
            return {"job_id": job_id, "status": "failed", "error": str(info)}
        elif state == "STARTED":
            return {"job_id": job_id, "status": "processing"}
        else:
            return {"job_id": job_id, "status": "pending"}
    except Exception as e:
        raise HTTPException(503, f"Task queue unavailable: {e}")


# ── Phase 2: Retry failed document ingestion ──────────────────────────────────

@router.post("/{document_id}/retry")
async def retry_ingestion(document_id: str, user: User = Depends(get_current_user)):
    """Retry ingestion for a document that failed or is stuck in pending."""
    require_role(user, "hr_admin")
    s = get_settings()
    from backend.app.core.tenant import get_current_tenant
    tenant_id = get_current_tenant()

    with sqlite3.connect(s.db_path) as con:
        row = con.execute(
            "SELECT source_filename, title, category, access_roles, ingestion_status "
            "FROM documents WHERE document_id=?",
            (document_id,),
        ).fetchone()

    if not row:
        raise HTTPException(404, f"Document {document_id} not found")

    filename, title, category, access_roles_json, current_status = row

    if current_status == "processing":
        raise HTTPException(409, "Document is currently being processed. Wait for it to complete or fail.")
    if current_status == "done":
        raise HTTPException(409, "Document is already successfully ingested. Use reindex if needed.")

    file_path = os.path.join(s.upload_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(404, f"Source file not found on disk: {filename}. Re-upload required.")

    roles = json.loads(access_roles_json)

    # Reset status to pending
    with sqlite3.connect(s.db_path) as con:
        con.execute("UPDATE documents SET ingestion_status='pending' WHERE document_id=?", (document_id,))

    try:
        from backend.app.workers.ingestion_tasks import ingest_document as _ingest_task
        job = _ingest_task.delay(
            document_id=document_id,
            file_path=file_path,
            filename=os.path.basename(filename).split("_", 1)[-1],  # strip UUID prefix
            category=category,
            access_roles=roles,
            tenant_id=tenant_id,
        )
        job_id = job.id
    except Exception as e:
        raise HTTPException(503, f"Task queue unavailable: {e}")

    logger.info("document_retry_queued", doc_id=document_id, job_id=job_id)
    return {"status": "pending", "document_id": document_id, "job_id": job_id}


# ── Phase 2: Document version history ────────────────────────────────────────

@router.get("/{document_id}/versions")
async def get_document_versions(document_id: str, user: User = Depends(get_current_user)):
    """View version history for a document (requires hr_admin)."""
    require_role(user, "hr_admin")

    from backend.app.core.permissions import require_permission
    if not require_permission(user.role, "documents.view_versions"):
        raise HTTPException(403, "Insufficient permissions")

    s = get_settings()

    # Check document exists
    with sqlite3.connect(s.db_path) as con:
        doc = con.execute(
            "SELECT title, category, version, ingestion_status FROM documents WHERE document_id=?",
            (document_id,),
        ).fetchone()

    if not doc:
        raise HTTPException(404, f"Document {document_id} not found")

    # Fetch versions from PostgreSQL if available
    versions = []
    if s.database_url.startswith("postgresql"):
        try:
            from backend.app.database.postgres import get_connection
            from sqlalchemy import text
            with get_connection() as conn:
                rows = conn.execute(
                    text(
                        "SELECT id, version_number, is_current, archived_at, created_at "
                        "FROM document_versions WHERE document_id = :doc_id ORDER BY version_number DESC"
                    ),
                    {"doc_id": document_id},
                ).fetchall()
                versions = [
                    {
                        "version_id": str(r[0]),
                        "version_number": r[1],
                        "is_current": r[2],
                        "archived_at": str(r[3]) if r[3] else None,
                        "created_at": str(r[4]),
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.warning("version_history_pg_failed", error=str(e))

    return {
        "document_id": document_id,
        "title": doc[0],
        "category": doc[1],
        "current_version": doc[2],
        "ingestion_status": doc[3],
        "version_history": versions,
    }
