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
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB


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

# Upload rate limiting: 5 uploads per minute per user
_upload_rate: dict[str, list[float]] = defaultdict(list)
UPLOAD_RATE_LIMIT = 5
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
    require_role(user, "hr_admin")

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

    # Check for duplicate documents — with version-aware upgrade support
    import hashlib
    content_hash = hashlib.sha256(content).hexdigest()
    s = get_settings()
    old_doc_id_to_replace = None
    with sqlite3.connect(s.db_path) as con:
        # Check by content hash first — identical content is always a duplicate
        hash_match = con.execute(
            "SELECT document_id, title FROM documents WHERE content_hash=?",
            (content_hash,)
        ).fetchone()
        if hash_match:
            raise HTTPException(
                409,
                f"Identical content already exists (ID: {hash_match[0]}, Title: {hash_match[1]})."
            )
        # Check by filename — same file may be a version upgrade
        fname_match = con.execute(
            "SELECT document_id, title, version FROM documents WHERE source_filename=?",
            (filename,)
        ).fetchone()
        if fname_match:
            old_version = fname_match[2] or "1.0"
            if version > old_version:
                # Version upgrade — mark old document for replacement
                old_doc_id_to_replace = fname_match[0]
                logger.info("version_upgrade", old_id=old_doc_id_to_replace,
                            old_version=old_version, new_version=version, filename=filename)
            else:
                raise HTTPException(
                    409,
                    f"Same or older version already exists (ID: {fname_match[0]}, "
                    f"Title: {fname_match[1]}, Version: {old_version}). "
                    f"Upload with a higher version number to replace it."
                )

    # Sanitize title to prevent stored XSS
    import html as html_mod
    title = html_mod.escape(title.strip(), quote=True)
    if not title:
        raise HTTPException(400, "Document title cannot be empty")

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
            "It may be a test document, exceed the maximum chunk limit (500), or be too large."
        )
    if result.status != "indexed":
        raise HTTPException(
            422,
            f"Document ingestion failed for '{filename}'. "
            "The file could not be processed — it may be empty, corrupted, or a scanned PDF."
        )
    log_document_upload(user, result.document_id, category, filename)
    resp = DocumentUploadResponse(document_id=result.document_id, chunk_count=result.chunk_count, status=result.status, processing_time_ms=result.processing_time_ms)
    if old_doc_id_to_replace:
        logger.info("version_replaced", old_id=old_doc_id_to_replace, new_id=result.document_id, version=version)
    return resp


@router.get("")
async def list_docs(user: User = Depends(get_current_user)):
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        rows = con.execute("SELECT document_id,title,category,access_roles,chunk_count,uploaded_at,version FROM documents ORDER BY uploaded_at DESC").fetchall()
    docs = []
    for r in rows:
        roles = json.loads(r[3])
        if can_access_document(user.role, roles):
            docs.append({"document_id": r[0], "title": r[1], "category": r[2], "access_roles": roles, "chunk_count": r[4], "uploaded_at": r[5], "version": r[6]})
    return {"documents": docs, "count": len(docs)}


@router.delete("/{document_id}")
async def delete_doc(document_id: str, user: User = Depends(get_current_user)):
    require_role(user, "hr_admin")
    s = get_settings()
    with sqlite3.connect(s.db_path) as con:
        row = con.execute("SELECT title FROM documents WHERE document_id=?", (document_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Document {document_id} not found")
    removed = _remove_document_chunks(document_id, s)
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
    filenames: dict[str, str] = {}
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
