from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.chunk import Chunk


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)

    # The idempotency key: ingest hashes file content and skips a document it has already
    # seen, unless --force. Re-running the corpus must not duplicate chunks.
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    # NULL until the loader has read the file; DOCX has no real page count (see loaders).
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DocumentStatus.PENDING, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )

    # A CHECK rather than a native PG enum: adding a status later is a one-line constraint
    # swap instead of ALTER TYPE, and the allowed values stay readable in the schema dump.
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'done', 'failed')",
            name="ck_documents_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename={self.filename!r} status={self.status}>"
