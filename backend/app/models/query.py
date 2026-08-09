from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Query(Base, TimestampMixin):
    """Every question asked of the system, and what came back.

    Deliberately not skipped in v1. This is the only record of what users *actually* ask, so
    the golden set can grow from real traffic instead of from imagination. pipeline_name is
    what lets a bad answer be traced back to the pipeline that produced it.
    """

    __tablename__ = "queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    # NULL when answering failed — the question is still worth keeping.
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    pipeline_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # No FK: chunks may be deleted by a re-ingest, and losing the trace of what was
    # retrieved would be worse than holding ids that no longer resolve.
    retrieved_chunk_ids: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, default=list
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<Query id={self.id} pipeline={self.pipeline_name!r}>"
