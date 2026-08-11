"""The retriever seam: `retrieve(question, k) -> list[RetrievedChunk]`, ranked, best first.

`RetrievedChunk` is deliberately a separate type from the repository's `ChunkHit`. `ChunkHit`
is a row shape belonging to the storage layer, and `score` there means one specific thing
(cosine similarity). A retriever's score means whatever that retriever ranks by — RRF for
`hybrid`, a cross-encoder logit for `reranker` — so the two must not be the same class, or a
Phase 6 fusion score would silently be read as a cosine similarity.

`rank` is carried explicitly rather than left implicit in list order: the eval metrics rank
positions, and the answer prompt renders the same list, and a reordering bug between them
would be invisible if position were the only record of it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.repositories.document_repo import ChunkHit


@dataclass(frozen=True)
class RetrievedChunk:
    """One retrieved chunk, with everything a citation and a judge prompt need."""

    chunk_id: int
    document_id: int
    filename: str
    page_no: int | None
    chunk_index: int
    content: str
    # Higher is better. The *meaning* is the retriever's, not a shared scale — never compare
    # a score from one retriever against a score from another.
    score: float
    rank: int
    # Which retriever produced this, so a hybrid result can say where each chunk came from.
    retriever: str

    def to_dict(self) -> dict[str, Any]:
        """For results/*.json. `content` is excluded — the results file would be unreadable."""
        return {
            "chunk_id": self.chunk_id,
            "filename": self.filename,
            "page_no": self.page_no,
            "score": round(self.score, 6),
            "rank": self.rank,
        }


@runtime_checkable
class Retriever(Protocol):
    """What a pipeline receives in its constructor. It never builds one itself (CLAUDE.md 4.3)."""

    name: str

    async def retrieve(self, question: str, k: int) -> list[RetrievedChunk]: ...


def from_hits(hits: Sequence[ChunkHit], *, retriever: str) -> list[RetrievedChunk]:
    """Adapt storage rows to retrieval results, numbering ranks from 1 in arrival order."""
    return [
        RetrievedChunk(
            chunk_id=hit.chunk_id,
            document_id=hit.document_id,
            filename=hit.filename,
            page_no=hit.page_no,
            chunk_index=hit.chunk_index,
            content=hit.content,
            score=hit.score,
            rank=rank,
            retriever=retriever,
        )
        for rank, hit in enumerate(hits, start=1)
    ]
