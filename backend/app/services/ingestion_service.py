"""Document ingestion pipeline — Section 5.

file → extract → clean → chunk → embed → index → register

Fixes applied:
- Per-page PDF extraction preserves page numbers in chunk metadata
- Robust fallback chunking when heading detection finds no sections
- MIN_CHUNK lowered to 30 so short policy paragraphs aren't discarded
- Batch embedding with progress logging
- Empty-document and zero-chunk validation
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import unicodedata
import uuid
from pathlib import Path

import structlog

from backend.app.core.config import get_settings
from backend.app.models.document_models import ChunkMetadata, DocumentMetadata, IngestionResult
from backend.app.services.embedding_service import EmbeddingService

logger = structlog.get_logger()

# ── Chunking parameters ──────────────────────────────────────────────────────
HR_CHUNK_RULES: dict[str, dict] = {
    "policy": {"size": 400, "overlap": 60},
    "handbook": {"size": 400, "overlap": 60},
    "benefits": {"size": 400, "overlap": 60},
    "leave": {"size": 400, "overlap": 60},
    "onboarding": {"size": 400, "overlap": 60},
    "legal": {"size": 400, "overlap": 60},
}
MIN_CHUNK_WORDS = 30   # lowered — short policy paragraphs are valid
MAX_CHUNK_WORDS = 800
MAX_CHUNKS_PER_DOCUMENT = 500  # Hard limit — reject documents that produce more chunks
MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB

# Reject documents whose title/filename matches test/QA patterns
_TEST_DOC_PATTERNS = re.compile(
    r"(^test[_\s]|_test$|^qa[_\s]|_qa$|^dummy|^sample[_\s]|^fake|^mock|huge\s*file\s*qa)",
    re.IGNORECASE,
)

HEADING_RE = re.compile(
    r"^(#{1,4}\s.+|[A-Z][A-Za-z\s]{2,60}\n[=-]+|\d+\.\d*\s+[A-Z].{5,80}|[A-Z][A-Z\s]{5,60}$)",
    re.MULTILINE,
)


# ── Chunking ─────────────────────────────────────────────────────────────────
def _fixed_chunk(text: str, size: int = 400, overlap: int = 60) -> list[str]:
    """Split text into overlapping word-count windows."""
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + size, len(words))
        chunk = " ".join(words[start:end])
        if len(chunk.split()) >= MIN_CHUNK_WORDS:
            chunks.append(chunk)
        start += size - overlap
        if start >= len(words):
            break
    return chunks


def _heading_chunk(text: str, size: int = 400, overlap: int = 60) -> list[tuple[str, str]]:
    """Split on headings first, then subdivide large sections."""
    sections = re.split(HEADING_RE, text)
    out: list[tuple[str, str]] = []
    heading = ""

    for s in sections:
        stripped = s.strip()
        if not stripped:
            continue
        if HEADING_RE.match(stripped):
            heading = stripped
            continue

        word_count = len(stripped.split())
        if word_count <= size:
            body = f"{heading}\n\n{stripped}" if heading else stripped
            if word_count >= MIN_CHUNK_WORDS:
                out.append((body, heading))
        else:
            for sub in _fixed_chunk(stripped, size, overlap):
                body = f"{heading}\n\n{sub}" if heading else sub
                out.append((body, heading))

    # Fallback: if heading detection found nothing, use fixed-size chunking
    if not out and text.strip():
        for sub in _fixed_chunk(text.strip(), size, overlap):
            out.append((sub, ""))

    return out


def chunk_document(
    text: str,
    meta: DocumentMetadata,
    page_number: int | None = None,
) -> list[ChunkMetadata]:
    """Chunk a single text block, attaching page number if provided."""
    rules = HR_CHUNK_RULES.get(meta.category, {"size": 400, "overlap": 60})
    raw = _heading_chunk(text, rules["size"], rules["overlap"])
    chunks: list[ChunkMetadata] = []
    for i, (txt, hd) in enumerate(raw):
        tc = len(txt.split())
        if tc < MIN_CHUNK_WORDS:
            continue
        cid = str(uuid.uuid4())
        chunks.append(ChunkMetadata(
            chunk_id=cid,
            document_id=meta.document_id,
            text=txt,
            page=page_number,
            section_heading=hd if hd else None,
            chunk_index=len(chunks),
            access_roles=meta.access_roles,
            category=meta.category,
            token_count=tc,
            source=meta.title,
            embedding_id=cid,
        ))
    return chunks


def chunk_document_by_pages(
    pages: list[tuple[str, int]],
    meta: DocumentMetadata,
) -> list[ChunkMetadata]:
    """Chunk a multi-page document, preserving page numbers.

    Args:
        pages: list of (page_text, page_number) tuples
        meta: document metadata
    """
    all_chunks: list[ChunkMetadata] = []
    for page_text, page_num in pages:
        page_chunks = chunk_document(page_text, meta, page_number=page_num)
        all_chunks.extend(page_chunks)

    # Re-index chunk_index sequentially across pages
    for i, c in enumerate(all_chunks):
        c.chunk_index = i

    return all_chunks


# ── Loaders ──────────────────────────────────────────────────────────────────
def _load_pdf(path: str) -> tuple[list[tuple[str, int]], int]:
    """Load PDF, return list of (page_text, page_number) and total page count.

    Handles:
    - Large PDFs (>500 pages): logs warning, processes anyway
    - Scanned PDFs (no extractable text): logs error with hint
    - Corrupt PDFs: catches exceptions, returns empty
    """
    import pdfplumber
    try:
        with pdfplumber.open(path) as pdf:
            total_pages = len(pdf.pages)
            if total_pages > 500:
                logger.warning("pdf_very_large", path=path, pages=total_pages,
                               hint="Consider splitting large PDFs for better chunking")
            pages: list[tuple[str, int]] = []
            empty_page_count = 0
            for i, p in enumerate(pdf.pages, 1):
                try:
                    text = p.extract_text()
                    if text and len(text.strip()) > 20:
                        pages.append((text, i))
                    else:
                        empty_page_count += 1
                except Exception as e:
                    logger.warning("pdf_page_extraction_failed", path=path, page=i, error=str(e))
                    continue

            if not pages and total_pages > 0:
                logger.error("pdf_no_text_extracted", path=path, total_pages=total_pages,
                             empty_pages=empty_page_count,
                             hint="This may be a scanned PDF. OCR is not currently supported.")
            elif empty_page_count > 0:
                logger.info("pdf_extraction_summary", path=path,
                            total_pages=total_pages, pages_with_text=len(pages),
                            empty_pages=empty_page_count)
            return pages, total_pages

    except Exception as e:
        logger.error("pdf_load_failed", path=path, error=str(e),
                     hint="PDF may be corrupted or password-protected")
        return [], 0


def _load_text(path: str) -> tuple[list[tuple[str, int]], int]:
    """Load text/markdown/docx, return as single-page list."""
    ext = Path(path).suffix.lower()
    if ext == ".docx":
        from docx import Document
        doc = Document(path)
        text = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    else:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    return [(text, 1)] if text.strip() else [], 1


def _load(path: str) -> tuple[list[tuple[str, int]], int]:
    """Load any supported file, return (pages_with_numbers, total_pages)."""
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return _load_pdf(path)
    return _load_text(path)


def _clean(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"Page\s+\d+\s*(of\s+\d+)?", "", text)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    # Collapse repeated dots/dashes/underscores (TOC leader lines in PDFs)
    # "ABOUT US .......................9" → "ABOUT US ... 9"
    text = re.sub(r"[.\u2026]{4,}", "...", text)
    text = re.sub(r"[-_]{4,}", "---", text)
    # Collapse repeated spaces
    text = re.sub(r"[ \t]{3,}", " ", text)
    return text.strip()


# ── Pipeline class ───────────────────────────────────────────────────────────
class IngestionPipeline:
    def __init__(self, embedding_service: EmbeddingService, vector_store, bm25_retriever=None):
        self.emb = embedding_service
        self.vs = vector_store
        self.bm25 = bm25_retriever

    def ingest(
        self,
        file_content: bytes,
        filename: str,
        title: str,
        category: str,
        access_roles: list[str],
        effective_date: str = "",
        version: str = "1.0",
        uploaded_by: str = "system",
    ) -> IngestionResult:
        import hashlib as _hashlib
        t0 = time.time()
        s = get_settings()
        doc_id = str(uuid.uuid4())
        content_hash = _hashlib.sha256(file_content).hexdigest()

        # ── Pre-flight validation ────────────────────────────────────────
        # Reject test/QA documents that could contaminate the vector store
        if _TEST_DOC_PATTERNS.search(title) or _TEST_DOC_PATTERNS.search(filename):
            logger.warning("ingestion_rejected_test_doc", filename=filename, title=title)
            return IngestionResult(doc_id, 0, "rejected", 0.0)

        # Reject oversized files
        if len(file_content) > MAX_DOCUMENT_SIZE_BYTES:
            logger.warning("ingestion_rejected_oversize", filename=filename,
                           size_mb=round(len(file_content) / (1024 * 1024), 1))
            return IngestionResult(doc_id, 0, "rejected", 0.0)

        try:
            # 1. Save file — defense-in-depth: sanitize filename again
            os.makedirs(s.upload_dir, exist_ok=True)
            safe_filename = os.path.basename(filename)
            if not safe_filename or ".." in safe_filename:
                raise ValueError(f"Unsafe filename rejected: {filename}")
            fp = os.path.join(s.upload_dir, safe_filename)
            # Verify resolved path is inside upload_dir
            if not os.path.realpath(fp).startswith(os.path.realpath(s.upload_dir)):
                raise ValueError(f"Path traversal detected: {filename}")
            with open(fp, "wb") as f:
                f.write(file_content)
            logger.info("ingestion_step", step="1_file_saved", filename=filename,
                        size_bytes=len(file_content), doc_id=doc_id)

            # 2. Extract text per page
            pages, total_pages = _load(fp)
            total_chars = sum(len(t) for t, _ in pages)
            if not pages or total_chars < 100:
                logger.error("ingestion_step", step="2_extraction_failed",
                             filename=filename, chars=total_chars, total_pages=total_pages,
                             hint="No extractable text found — file may be scanned or empty")
                return IngestionResult(doc_id, 0, "failed", (time.time() - t0) * 1000)
            logger.info("ingestion_step", step="2_text_extracted", filename=filename,
                        documents_processed=1, pages_extracted=len(pages),
                        total_pages=total_pages, total_chars=total_chars)

            # 3. Clean each page
            cleaned_pages = [(_clean(text), page_num) for text, page_num in pages]
            cleaned_pages = [(t, p) for t, p in cleaned_pages if len(t.strip()) > 20]
            logger.info("ingestion_step", step="3_text_cleaned", filename=filename,
                        pages_after_cleaning=len(cleaned_pages))

            # 4. Build metadata
            meta = DocumentMetadata(
                document_id=doc_id, title=title, category=category,
                access_roles=access_roles, effective_date=effective_date,
                version=version, source_filename=filename,
                uploaded_by=uploaded_by, uploaded_at=time.time(),
                page_count=total_pages,
            )

            # 5. Chunk — per-page to preserve page numbers
            chunks = chunk_document_by_pages(cleaned_pages, meta)
            if not chunks:
                logger.error("ingestion_step", step="5_no_chunks",
                             filename=filename, cleaned_pages=len(cleaned_pages))
                return IngestionResult(doc_id, 0, "failed", (time.time() - t0) * 1000)
            meta.chunk_count = len(chunks)
            token_counts = [c.token_count for c in chunks]
            logger.info("ingestion_step", step="5_chunked", filename=filename,
                        chunks_generated=len(chunks),
                        avg_tokens=sum(token_counts) // len(token_counts),
                        min_tokens=min(token_counts),
                        max_tokens=max(token_counts))

            # Validate chunk count range (expected 30-150 per document)
            if len(chunks) < 5:
                logger.warning("ingestion_low_chunk_count", filename=filename,
                               chunks=len(chunks), hint="Very few chunks — document may be too short")
            elif len(chunks) > MAX_CHUNKS_PER_DOCUMENT:
                logger.error("ingestion_rejected_too_many_chunks", filename=filename,
                             chunks=len(chunks), limit=MAX_CHUNKS_PER_DOCUMENT,
                             hint="Document is too large and would dominate retrieval")
                return IngestionResult(doc_id, 0, "rejected", (time.time() - t0) * 1000)
            elif len(chunks) > 300:
                logger.warning("ingestion_high_chunk_count", filename=filename,
                               chunks=len(chunks), hint="Very many chunks — consider larger chunk size")

            # 6. Embed
            t_embed = time.time()
            texts = [c.text for c in chunks]
            embeddings = self.emb.embed_batch(texts)
            embed_ms = (time.time() - t_embed) * 1000
            logger.info("ingestion_step", step="6_embedded", filename=filename,
                        embeddings_generated=embeddings.shape[0],
                        embedding_dim=embeddings.shape[1],
                        embed_latency_ms=round(embed_ms))

            # 7. Index into FAISS
            self.vs.add(embeddings, chunks)
            logger.info("ingestion_step", step="7_indexed", filename=filename,
                        new_chunks=len(chunks),
                        embeddings_stored=embeddings.shape[0],
                        total_in_faiss=self.vs.total_chunks)

            # 8. Update BM25
            if self.bm25:
                self.bm25.add_chunks(chunks)
                logger.info("ingestion_step", step="8_bm25_updated",
                            filename=filename, bm25_total=self.bm25.total_chunks)

            # 9. Register in DB
            self._register(meta, content_hash=content_hash)
            logger.info("ingestion_step", step="9_db_registered",
                        filename=filename, doc_id=doc_id)

            # 10. Persist FAISS to disk
            try:
                self.vs.save()
                logger.info("ingestion_step", step="10_faiss_persisted",
                            filename=filename, index_size=self.vs.total_chunks)
            except Exception as e:
                logger.warning("ingestion_step", step="10_faiss_save_failed", error=str(e))

            ms = (time.time() - t0) * 1000
            logger.info("ingestion_complete", doc_id=doc_id, title=title,
                        documents_processed=1, pages_extracted=len(pages),
                        chunks_generated=len(chunks), embeddings_stored=embeddings.shape[0],
                        processing_time_ms=round(ms),
                        faiss_total=self.vs.total_chunks)
            return IngestionResult(doc_id, len(chunks), "indexed", ms)

        except Exception as e:
            ms = (time.time() - t0) * 1000
            logger.error("ingestion_failed", doc_id=doc_id, error=str(e),
                         filename=filename, processing_time_ms=round(ms))
            return IngestionResult(doc_id, 0, "failed", ms)

    def _register(self, m: DocumentMetadata, content_hash: str = "") -> None:
        with sqlite3.connect(get_settings().db_path) as con:
            con.execute(
                "INSERT OR REPLACE INTO documents (document_id,title,category,access_roles,"
                "effective_date,version,source_filename,uploaded_by,uploaded_at,page_count,chunk_count,content_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (m.document_id, m.title, m.category, json.dumps(m.access_roles),
                 m.effective_date, m.version, m.source_filename, m.uploaded_by,
                 m.uploaded_at, m.page_count, m.chunk_count, content_hash),
            )
