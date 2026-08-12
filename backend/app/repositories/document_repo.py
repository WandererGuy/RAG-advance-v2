"""All SQL for documents and chunks. Nothing above this layer writes a query (CLAUDE.md 4.2).

The repository never commits. Transaction boundaries belong to the caller — the ingest service
needs the whole chunk rewrite of one document to land or not land as a unit, and it can only
decide that if this layer stays out of it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, Document, DocumentStatus


@dataclass(frozen=True)
class ChunkHit:
    """One row from a similarity search, flattened with the document fields a citation needs."""

    chunk_id: int
    document_id: int
    filename: str
    page_no: int | None
    chunk_index: int
    content: str
    # 1 - cosine distance. 1.0 is identical, 0.0 is orthogonal.
    score: float


@dataclass(frozen=True)
class ChunkMatch:
    """One row from the keyword lookup used to write the golden set.

    Deliberately not a ChunkHit: there is no similarity score here and inventing one would
    invite someone to compare a keyword match against a retrieval score.
    """

    chunk_id: int
    filename: str
    page_no: int | None
    chunk_index: int
    content: str


@dataclass(frozen=True)
class CorpusChunkRow:
    """A chunk reduced to what the corpus lock needs to detect a re-ingest."""

    chunk_id: int
    file_hash: str
    filename: str
    page_no: int | None
    chunk_index: int
    content: str


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- documents ---------------------------------------------------------------

    async def get_by_hash(self, file_hash: str) -> Document | None:
        """The idempotency lookup: same bytes means same document, whatever it is named."""
        result = await self._session.execute(
            select(Document).where(Document.file_hash == file_hash)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, document_id: int) -> Document | None:
        return await self._session.get(Document, document_id)

    async def create(
        self,
        *,
        filename: str,
        source_path: str,
        file_hash: str,
        mime_type: str,
        status: str = DocumentStatus.PENDING,
    ) -> Document:
        document = Document(
            filename=filename,
            source_path=source_path,
            file_hash=file_hash,
            mime_type=mime_type,
            status=status,
        )
        self._session.add(document)
        # Flush, not commit: the caller still owns the transaction, but it needs the generated
        # id to attach chunks to.
        await self._session.flush()
        return document

    async def set_status(
        self,
        document: Document,
        status: str,
        *,
        error_message: str | None = None,
        page_count: int | None = None,
    ) -> None:
        """Move a document through pending -> processing -> done|failed.

        `error_message` is cleared on any non-failed status so a document that succeeds on a
        retry does not keep advertising the error from the attempt before.
        """
        document.status = status
        document.error_message = error_message if status == DocumentStatus.FAILED else None
        if page_count is not None:
            document.page_count = page_count
        await self._session.flush()

    async def list_with_chunk_counts(self, limit: int = 200) -> list[tuple[Document, int]]:
        """Every document, newest first, each with how many chunks it has.

        One LEFT JOIN + GROUP BY rather than a count per document: `GET /documents` renders the
        whole table, and a per-row count would be an N+1 that grows with the corpus. LEFT, so a
        `failed` document with no chunks still appears — that row is the one worth seeing.
        """
        chunk_count = func.count(Chunk.id)
        result = await self._session.execute(
            select(Document, chunk_count)
            .outerjoin(Chunk, Chunk.document_id == Document.id)
            .group_by(Document.id)
            .order_by(Document.created_at.desc(), Document.id.desc())
            .limit(limit)
        )
        return [(document, int(count)) for document, count in result.all()]

    async def status_counts(self) -> dict[str, int]:
        """`SELECT status, count(*) FROM documents GROUP BY status` — the Phase 2 DoD query."""
        result = await self._session.execute(
            select(Document.status, func.count()).group_by(Document.status)
        )
        return {status: count for status, count in result.all()}

    # --- chunks ------------------------------------------------------------------

    async def delete_chunks(self, document_id: int) -> int:
        """Remove every chunk of a document. Returns how many were deleted.

        Always run before re-inserting: `ix_chunks_document_id_chunk_index` is unique on
        `(document_id, chunk_index)`, so a re-ingest that skipped this would collide on the
        first chunk rather than silently duplicate.
        """
        result = await self._session.execute(delete(Chunk).where(Chunk.document_id == document_id))
        # A DELETE always yields a CursorResult; only the generic Result type lacks rowcount.
        return cast("CursorResult[Any]", result).rowcount or 0

    async def add_chunks(self, document_id: int, rows: Sequence[dict[str, Any]]) -> int:
        """Bulk-insert chunks. A row is content/page_no/chunk_index/token_count/embedding.

        A single executemany rather than a session.add() per chunk: the ORM path would emit one
        INSERT per row and a corpus re-ingest is thousands of rows.
        """
        if not rows:
            return 0
        payload = [{"document_id": document_id, **row} for row in rows]
        await self._session.execute(insert(Chunk), payload)
        return len(payload)

    async def update_chunk_embeddings(self, vectors: Mapping[int, Sequence[float]]) -> int:
        """Replace the embedding of existing chunks, keyed by chunk id. Returns rows updated.

        The only supported way to change embedding model without destroying the golden set.
        `delete_chunks` + `add_chunks` would reassign serial ids, and `relevant_chunk_ids` in
        `golden_qa.v1.jsonl` are bare integers that would then point at the wrong text — the
        failure ADR-0005 exists to catch. An UPDATE touches no id, no content and no
        chunk_index, so `corpus.lock.json` stays valid: re-embedding is not a corpus change.
        """
        if not vectors:
            return 0
        # ORM "bulk UPDATE by primary key": each row carries `id`, and SQLAlchemy derives the
        # WHERE from it. An explicit .where(bindparam(...)) instead lands on a different code
        # path that cannot synchronize the identity map and refuses the executemany outright.
        payload = [
            {"id": chunk_id, "embedding": list(vector)} for chunk_id, vector in vectors.items()
        ]
        await self._session.execute(update(Chunk), payload)
        return len(payload)

    async def count_chunks(self, document_id: int | None = None) -> int:
        statement = select(func.count()).select_from(Chunk)
        if document_id is not None:
            statement = statement.where(Chunk.document_id == document_id)
        result = await self._session.execute(statement)
        return int(result.scalar_one())

    async def search_text(
        self, terms: Sequence[str], *, limit: int = 20, filename_like: str | None = None
    ) -> list[ChunkMatch]:
        """Chunks containing **every** term, case-insensitively. Not a retriever.

        This exists so a golden-set writer can find the chunk id behind a policy sentence
        (Phase 3). ILIKE, not tsvector: Postgres has no Vietnamese text-search configuration,
        so `to_tsvector` would stem Vietnamese as if it were English and quietly return the
        wrong rows. A substring match is the honest primitive here.
        """
        statement = (
            select(
                Chunk.id,
                Document.filename,
                Chunk.page_no,
                Chunk.chunk_index,
                Chunk.content,
            )
            .join(Document, Document.id == Chunk.document_id)
            .order_by(Document.filename, Chunk.chunk_index)
            .limit(limit)
        )
        for term in terms:
            statement = statement.where(Chunk.content.ilike(f"%{term}%"))
        if filename_like:
            statement = statement.where(Document.filename.ilike(f"%{filename_like}%"))

        result = await self._session.execute(statement)
        return [
            ChunkMatch(
                chunk_id=row.id,
                filename=row.filename,
                page_no=row.page_no,
                chunk_index=row.chunk_index,
                content=row.content,
            )
            for row in result.all()
        ]

    async def all_chunks_for_lock(self) -> list[CorpusChunkRow]:
        """Every chunk with its document's file_hash, ordered deterministically.

        Feeds `eval/datasets/corpus.lock.json`. Ordered by (file_hash, chunk_index) rather than
        by id so the lock's own digest does not change just because ids were reassigned — the
        id list is compared separately and on purpose.
        """
        result = await self._session.execute(
            select(
                Chunk.id,
                Document.file_hash,
                Document.filename,
                Chunk.page_no,
                Chunk.chunk_index,
                Chunk.content,
            )
            .join(Document, Document.id == Chunk.document_id)
            .order_by(Document.file_hash, Chunk.chunk_index)
        )
        return [
            CorpusChunkRow(
                chunk_id=row.id,
                file_hash=row.file_hash,
                filename=row.filename,
                page_no=row.page_no,
                chunk_index=row.chunk_index,
                content=row.content,
            )
            for row in result.all()
        ]

    async def search_similar(
        self, embedding: Sequence[float], top_k: int, *, document_ids: Sequence[int] | None = None
    ) -> list[ChunkHit]:
        """Cosine top-k over `chunks.embedding`, joined to the document for citation fields.

        `<=>` is cosine *distance*, which is what `ix_chunks_embedding_hnsw` is built for —
        ordering by anything else would drop the index and fall back to a sequential scan.
        """
        distance = Chunk.embedding.cosine_distance(list(embedding))
        statement = (
            select(
                Chunk.id,
                Chunk.document_id,
                Document.filename,
                Chunk.page_no,
                Chunk.chunk_index,
                Chunk.content,
                distance.label("distance"),
            )
            .join(Document, Document.id == Chunk.document_id)
            .where(Chunk.embedding.is_not(None))
            .order_by(distance)
            .limit(top_k)
        )
        if document_ids:
            statement = statement.where(Chunk.document_id.in_(list(document_ids)))

        result = await self._session.execute(statement)
        return [
            ChunkHit(
                chunk_id=row.id,
                document_id=row.document_id,
                filename=row.filename,
                page_no=row.page_no,
                chunk_index=row.chunk_index,
                content=row.content,
                score=1.0 - float(row.distance),
            )
            for row in result.all()
        ]
