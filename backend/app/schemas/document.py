"""`GET /documents` and `POST /documents`.

`source_path` and `file_hash` are deliberately **not** exposed. The path is a server filesystem
detail and the hash is the idempotency key; neither is something a client should key off, and
publishing the path in a demo UI is how an absolute path ends up in a screenshot.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models import Document
from app.services.ingest_service import IngestResult


class DocumentOut(BaseModel):
    """One row of `GET /documents`."""

    id: int
    filename: str
    mime_type: str
    status: Literal["pending", "processing", "done", "failed"]
    page_count: int | None = None
    chunk_count: int = Field(
        default=0, description="0 for a document that failed before its chunks were inserted."
    )
    error_message: str | None = Field(default=None, description="Set only when status is 'failed'.")
    created_at: datetime

    @classmethod
    def from_model(cls, document: Document, *, chunk_count: int = 0) -> DocumentOut:
        return cls(
            id=document.id,
            filename=document.filename,
            mime_type=document.mime_type,
            # `documents.status` is a plain str column; `ck_documents_status` is what actually
            # constrains it to these four values, and Pydantic re-checks them here.
            status=document.status,
            page_count=document.page_count,
            chunk_count=chunk_count,
            error_message=document.error_message,
            created_at=document.created_at,
        )


class IngestResponse(BaseModel):
    """The result of one synchronous upload.

    `status` distinguishes `skipped` from `ingested` rather than collapsing both into success:
    re-uploading the same bytes is a no-op by design (the hash is the identity), and a UI that
    reported "ingested" would make a silent no-op look like work.
    """

    status: Literal["ingested", "skipped", "failed"]
    filename: str
    document_id: int | None = None
    chunk_count: int = 0
    page_count: int | None = None
    error: str | None = None

    @classmethod
    def from_result(cls, result: IngestResult, *, filename: str) -> IngestResponse:
        return cls(
            status=result.status,
            filename=filename,
            document_id=result.document_id,
            chunk_count=result.chunk_count,
            page_count=result.page_count,
            error=result.error,
        )
