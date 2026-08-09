"""Ingest against a real Postgres and a real embedding provider.

The property that matters most here is idempotency: `make ingest` is going to be run repeatedly
while the corpus grows, and a second run that doubles the chunk count would poison retrieval
with duplicates long before anyone noticed the row count.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import REPO_ROOT, get_settings
from app.models import Chunk, Document, DocumentStatus
from app.repositories.document_repo import DocumentRepository
from app.services.ingest_service import file_hash, ingest_file, iter_supported_files

SAMPLE = REPO_ROOT / "data" / "samples" / "04_nghi_phep_va_lam_viec_tu_xa.pdf"

pytestmark = pytest.mark.usefixtures("require_embedding_api")


@pytest.fixture(autouse=True)
def _require_sample() -> None:
    if not SAMPLE.exists():
        pytest.skip(f"missing fixture {SAMPLE} — copy one real PDF from data/raw/HR_pdfs/")


async def test_ingest_is_idempotent(session: AsyncSession) -> None:
    """Ingest the same file twice; the chunk count must not move."""
    first = await ingest_file(session, SAMPLE)
    assert first.status == "ingested"
    assert first.chunk_count > 0

    second = await ingest_file(session, SAMPLE)

    assert second.status == "skipped"
    assert second.document_id == first.document_id
    assert second.chunk_count == first.chunk_count

    repo = DocumentRepository(session)
    assert await repo.count_chunks() == first.chunk_count
    documents = (await session.execute(select(Document))).scalars().all()
    assert len(documents) == 1, "same bytes must not produce a second document row"


async def test_force_rebuilds_chunks_without_duplicating_them(session: AsyncSession) -> None:
    """--force deletes and re-inserts. The count is stable; the ids are not.

    Re-ingest assigning new chunk ids is the reason Phase 3's golden set must be regenerated
    after any forced run.
    """
    first = await ingest_file(session, SAMPLE)
    original_ids = await _chunk_ids(session)

    forced = await ingest_file(session, SAMPLE, force=True)

    assert forced.status == "ingested"
    assert forced.chunk_count == first.chunk_count
    assert await DocumentRepository(session).count_chunks() == first.chunk_count
    assert await _chunk_ids(session) != original_ids


async def test_ingested_chunks_carry_citable_metadata(session: AsyncSession) -> None:
    """Every chunk must be able to answer "which document, which page" — that is the product."""
    result = await ingest_file(session, SAMPLE)
    settings = get_settings()

    chunks = (await session.execute(select(Chunk).order_by(Chunk.chunk_index))).scalars().all()

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert all(c.page_no is not None and c.page_no >= 1 for c in chunks), "PDF pages are known"
    assert all(c.page_no <= (result.page_count or 0) for c in chunks)
    assert all(c.content.strip() for c in chunks)
    assert all(c.token_count and c.token_count > 0 for c in chunks)
    assert all(len(c.embedding) == settings.embedding_dimensions for c in chunks)


async def test_document_row_reaches_done_with_a_page_count(session: AsyncSession) -> None:
    await ingest_file(session, SAMPLE)

    document = (await session.execute(select(Document))).scalar_one()

    assert document.status == DocumentStatus.DONE
    assert document.error_message is None
    assert document.page_count == 2
    assert document.file_hash == file_hash(SAMPLE)
    assert document.filename == SAMPLE.name


async def test_similarity_search_finds_the_ingested_chunks(session: AsyncSession) -> None:
    """The vector-store read path, end to end: HNSW index, cosine ordering, citation fields."""
    from app.llm.rag.embedder import get_embedder
    from app.llm.rag.vector_store import PgVectorStore

    await ingest_file(session, SAMPLE)
    store = PgVectorStore(DocumentRepository(session))

    query = await get_embedder().embed_query("Nhân viên được nghỉ phép bao nhiêu ngày một năm?")
    hits = await store.search(query, top_k=3)

    assert 0 < len(hits) <= 3
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)
    assert all(h.filename == SAMPLE.name and h.page_no is not None for h in hits)
    assert all(-1.0 <= h.score <= 1.0 for h in hits)


async def test_an_unreadable_file_fails_that_document_only(
    session: AsyncSession, tmp_path: Path
) -> None:
    """A corrupt document records why it failed and does not abort the run."""
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4 this is not actually a pdf")

    result = await ingest_file(session, broken)

    assert result.status == "failed"
    assert result.error
    document = (await session.execute(select(Document))).scalar_one()
    assert document.status == DocumentStatus.FAILED
    assert document.error_message == result.error
    assert await DocumentRepository(session).count_chunks() == 0

    # The session is still usable afterwards — the next file in the loop depends on it.
    assert (await ingest_file(session, SAMPLE)).status == "ingested"


def test_iter_supported_files_finds_the_corpus_and_ignores_other_formats(tmp_path: Path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"x")
    (tmp_path / "b.docx").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("skip me")
    (tmp_path / ".hidden.pdf").write_bytes(b"x")

    found = [p.name for p in iter_supported_files(tmp_path)]

    assert found == ["a.pdf", "b.docx"]


async def _chunk_ids(session: AsyncSession) -> list[int]:
    result = await session.execute(select(Chunk.id).order_by(Chunk.chunk_index))
    return list(result.scalars().all())
