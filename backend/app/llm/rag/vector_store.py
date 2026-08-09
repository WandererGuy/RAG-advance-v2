"""The vector-store seam: `add_chunks`, `search`, `delete_by_document`. pgvector only.

This module holds **no SQL**. It is a protocol plus a thin adapter over `DocumentRepository`,
which keeps CLAUDE.md 4.2 ("only repositories/ may write queries") intact while still giving
Phase 4's dense retriever the interface PLAN.md specifies. See ADR-0003.

There will be no Qdrant implementation — CLAUDE.md scopes that out permanently.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.llm.rag.chunking import TextChunk
from app.repositories.document_repo import ChunkHit, DocumentRepository


@runtime_checkable
class VectorStore(Protocol):
    """What the ingest service writes through and the dense retriever reads through."""

    async def add_chunks(
        self, document_id: int, chunks: Sequence[TextChunk], embeddings: Sequence[Sequence[float]]
    ) -> int: ...

    async def search(self, embedding: Sequence[float], top_k: int) -> list[ChunkHit]: ...

    async def delete_by_document(self, document_id: int) -> int: ...


class PgVectorStore:
    """pgvector-backed store. Transaction control stays with the caller, as in the repository."""

    def __init__(self, repo: DocumentRepository) -> None:
        self._repo = repo

    async def add_chunks(
        self, document_id: int, chunks: Sequence[TextChunk], embeddings: Sequence[Sequence[float]]
    ) -> int:
        """Attach one embedding per chunk and insert. Order is the contract.

        `embed_texts` returns vectors in input order, so position i of `embeddings` belongs to
        position i of `chunks`. The length check is what stops a truncated provider response
        from silently shifting every vector onto the wrong chunk.
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"{len(chunks)} chunks but {len(embeddings)} embeddings — "
                "a vector would be attached to the wrong chunk"
            )

        rows = [
            {
                "content": chunk.content,
                "page_no": chunk.page_no,
                "chunk_index": chunk.chunk_index,
                "token_count": chunk.token_count,
                "embedding": list(embedding),
            }
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        return await self._repo.add_chunks(document_id, rows)

    async def search(self, embedding: Sequence[float], top_k: int) -> list[ChunkHit]:
        return await self._repo.search_similar(embedding, top_k)

    async def delete_by_document(self, document_id: int) -> int:
        return await self._repo.delete_chunks(document_id)
