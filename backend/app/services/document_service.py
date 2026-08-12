"""Listing documents, and ingesting an uploaded one. No FastAPI import (CLAUDE.md 4.2).

The upload path deliberately writes the bytes to a real file before calling `ingest_service`:
the loaders are file-based (PyMuPDF and python-docx both open a path), and `documents.file_hash`
is the hash of file content. Reimplementing an in-memory ingest path would be a second ingest
implementation that could drift from the one the corpus was built with.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import REPO_ROOT
from app.core.exceptions import UnsupportedFileType
from app.core.logging import get_logger
from app.llm.rag import loaders
from app.repositories.document_repo import DocumentRepository
from app.schemas.document import DocumentOut, IngestResponse
from app.services.ingest_service import ingest_file

log = get_logger(__name__)

# Uploads land beside the corpus, not inside data/raw/HR_pdfs/ — that directory is the frozen
# corpus the golden set is locked against (ADR-0005), and an upload must never silently join it.
UPLOAD_DIR = REPO_ROOT / "data" / "uploads"

# A cap, because ingest is synchronous and the whole file is read into memory to hash it.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


async def list_documents(session: AsyncSession, *, limit: int = 200) -> list[DocumentOut]:
    """Every document with its chunk count, newest first."""
    rows = await DocumentRepository(session).list_with_chunk_counts(limit=limit)
    return [DocumentOut.from_model(document, chunk_count=count) for document, count in rows]


async def ingest_upload(session: AsyncSession, *, filename: str, content: bytes) -> IngestResponse:
    """Persist an uploaded file and ingest it synchronously.

    Slow is acceptable here and there is deliberately no queue (PLAN.md Phase 5).

    **This path never forces a re-ingest**, and takes no parameter that would let a caller ask
    for one. A forced re-ingest reassigns chunk ids and silently invalidates the golden set
    (ADR-0005); it belongs at a terminal (`make ingest FORCE=1`), not behind an HTTP call.
    Known bytes are skipped, which is what an upload form should do anyway.

    The file is written to its final location in `data/uploads/` **before** ingest, because
    `documents.source_path` records where the file lives and a path under a temporary directory
    would be dangling the moment the request finished. If ingest fails the file is removed
    again, so a failed upload leaves nothing behind for a later `make ingest` to pick up.
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in loaders.SUPPORTED_SUFFIXES:
        raise UnsupportedFileType(filename, suffix)

    safe_name = Path(filename).name
    bound = log.bind(filename=safe_name, bytes=len(content))

    stored = _write(content, safe_name)
    try:
        result = await ingest_file(session, stored)
    except Exception:
        stored.unlink(missing_ok=True)
        raise

    if result.status == "failed":
        stored.unlink(missing_ok=True)
        bound.warning("upload_ingest_failed", error=result.error)
    elif result.status == "skipped":
        # Same bytes as a document already ingested: the row keeps pointing at the original
        # file, so this copy is redundant and keeping it would grow data/uploads/ on every
        # re-upload of an unchanged document.
        stored.unlink(missing_ok=True)
        bound.info("upload_skipped", document_id=result.document_id, reason="unchanged")
    else:
        bound.info(
            "upload_ingested",
            document_id=result.document_id,
            chunks=result.chunk_count,
            stored=str(stored),
        )
    return IngestResponse.from_result(result, filename=safe_name)


def _write(content: bytes, filename: str) -> Path:
    """Write the upload into `data/uploads/`, never overwriting an existing name.

    A name collision gets a numeric suffix rather than replacing the file: two different
    documents can legitimately arrive as `chinh-sach.pdf`, and the one already ingested is
    still the `source_path` of a row in `documents`.
    """
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stem, suffix = Path(filename).stem, Path(filename).suffix
    target = UPLOAD_DIR / filename
    counter = 1
    while target.exists():
        target = UPLOAD_DIR / f"{stem}-{counter}{suffix}"
        counter += 1
    target.write_bytes(content)
    return target
