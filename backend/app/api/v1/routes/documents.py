"""`POST /documents` (upload + synchronous ingest) and `GET /documents` (list + status).

Synchronous on purpose: slow is acceptable, and a queue is out of scope for v1 (PLAN.md
Phase 5, ADR-0002). A large PDF will hold the request open for as long as embedding takes.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from app.api.deps import DbSession
from app.core.exceptions import UnsupportedFileType
from app.core.logging import get_logger
from app.llm.rag import loaders
from app.schemas.document import DocumentOut, IngestResponse
from app.services import document_service

router = APIRouter(tags=["documents"])
log = get_logger(__name__)


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[DocumentOut]:
    """Every ingested document with its status, page count and chunk count."""
    return await document_service.list_documents(session, limit=limit)


@router.post("/documents", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    session: DbSession,
    file: Annotated[UploadFile, File(description="A text-based PDF or a DOCX.")],
) -> IngestResponse:
    """Upload one document and ingest it before responding.

    **There is deliberately no `force` parameter.** A forced re-ingest deletes and re-inserts a
    document's chunks, which reassigns their ids and silently invalidates every
    `relevant_chunk_ids` in the golden set — the failure ADR-0005 exists to catch. Over HTTP
    that would be a checkbox in Swagger, one click away from destroying the only fixed point
    this project measures against, and a docstring is not a safeguard.

    Re-ingesting is still possible where it belongs: `make ingest FORCE=1` at a terminal, which
    announces what it is about to do. Uploading bytes that are already known is a no-op here
    (`status="skipped"`), which is the correct behaviour for an upload form.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="a filename is required"
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="the file is empty"
        )
    if len(content) > document_service.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"file is {len(content)} bytes; the limit is "
                f"{document_service.MAX_UPLOAD_BYTES} because ingest is synchronous"
            ),
        )

    try:
        result = await document_service.ingest_upload(
            session, filename=file.filename, content=content
        )
    except UnsupportedFileType as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"{exc} — supported: {', '.join(sorted(loaders.SUPPORTED_SUFFIXES))}. "
                "A scanned PDF needs OCR, which is out of scope for v1."
            ),
        ) from exc
    except Exception as exc:
        log.error("upload_failed", filename=file.filename, error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"ingest failed: {type(exc).__name__}",
        ) from exc

    # ingest_service returns a per-document failure rather than raising it. Surfaced as 422 with
    # the reason: the request was well-formed but this file could not be turned into chunks —
    # most often a scanned PDF with no text layer, which is out of scope for v1.
    if result.status == "failed":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=result.error or "the document could not be ingested",
        )
    return result
