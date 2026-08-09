from __future__ import annotations

from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.document import Document

# Must match EMBEDDING_DIMENSIONS in .env. Hardcoded because a column type cannot be
# resolved at migration time from config — changing it is a migration plus a full re-ingest
# plus a re-run of every pipeline. See ADR-0002.
EMBEDDING_DIM = 768


class Chunk(Base, TimestampMixin):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # The whole citation feature rests on this column. NULL only for formats with no real
    # pagination (DOCX); PDF chunks always carry the page they came from.
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)

    document: Mapped[Document] = relationship(back_populates="chunks")

    __table_args__ = (
        # HNSW with cosine distance: the dense retriever orders by `embedding <=> query`.
        # Built here rather than left to autogenerate, which does not emit vector opclasses.
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunks_document_id_chunk_index", "document_id", "chunk_index", unique=True),
    )

    def __repr__(self) -> str:
        return f"<Chunk id={self.id} doc={self.document_id} page={self.page_no}>"
