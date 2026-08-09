"""Synchronous ingest: hash -> skip -> load -> chunk -> embed -> insert -> done.

No FastAPI import, ever (CLAUDE.md 4.2). This service is driven by `scripts/ingest_corpus.py`
today and by `POST /documents` in Phase 5; it must not learn that HTTP exists.

**Failure is per-document, not per-run.** One unreadable file marks itself `failed` with the
reason on the row and the loop moves to the next file. A corpus ingest that aborts halfway
because document 5 of 8 is corrupt is worse than one that tells you which document was corrupt.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import PipelineConfig, get_settings
from app.core.exceptions import IngestFailed
from app.core.logging import get_logger
from app.llm.rag import loaders
from app.llm.rag.chunking import TextChunk, chunk
from app.llm.rag.embedder import Embedder, get_embedder
from app.llm.rag.vector_store import PgVectorStore, VectorStore
from app.models import Document, DocumentStatus
from app.repositories.document_repo import DocumentRepository

log = get_logger(__name__)

# documents.error_message is TEXT, but a provider traceback pasted whole makes `\dt` output
# unreadable and tells you nothing the log does not already have.
MAX_ERROR_CHARS = 2000

IngestStatus = Literal["ingested", "skipped", "failed"]


@dataclass(frozen=True)
class IngestResult:
    path: Path
    status: IngestStatus
    document_id: int | None = None
    chunk_count: int = 0
    page_count: int | None = None
    error: str | None = None


def file_hash(path: Path) -> str:
    """SHA-256 of the file's bytes — the idempotency key.

    Content-based, so renaming or moving a document is not a new document, and editing one is.
    Read in blocks because the whole file need not fit in memory.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def iter_supported_files(root: Path) -> Iterator[Path]:
    """Yield ingestable files under `root`, sorted, skipping hidden files.

    Sorted so a corpus ingest is reproducible: chunk ids are assigned in insertion order, and
    Phase 3's golden set will reference them.
    """
    if root.is_file():
        if root.suffix.lower() in loaders.SUPPORTED_SUFFIXES:
            yield root
        return

    for path in sorted(root.rglob("*")):
        if (
            path.is_file()
            and path.suffix.lower() in loaders.SUPPORTED_SUFFIXES
            and not path.name.startswith(".")
        ):
            yield path


async def ingest_file(
    session: AsyncSession,
    path: Path,
    *,
    force: bool = False,
    embedder: Embedder | None = None,
    cfg: PipelineConfig | None = None,
) -> IngestResult:
    """Ingest one file. Never raises for a per-document failure — it returns one.

    Transaction shape, and why it is three commits rather than one:

    1. the document row reaches `processing` and commits, so a crash mid-embed leaves a visible
       record instead of no trace of the attempt;
    2. delete-old-chunks + insert-new-chunks + `status=done` commit **together**, so the table
       never shows a document as done with half its chunks;
    3. on failure, a rollback followed by its own small transaction writing `status=failed` —
       the same session cannot record the error inside the transaction it just rolled back.
    """
    cfg = cfg or get_settings().pipeline_config()
    embedder = embedder or get_embedder()
    repo = DocumentRepository(session)
    store: VectorStore = PgVectorStore(repo)
    bound = log.bind(path=str(path), filename=path.name)

    try:
        digest = file_hash(path)
    except OSError as exc:
        bound.error("ingest_unreadable", error=str(exc))
        return IngestResult(path=path, status="failed", error=f"cannot read file: {exc}")

    existing = await repo.get_by_hash(digest)
    if existing is not None and existing.status == DocumentStatus.DONE and not force:
        chunk_count = await repo.count_chunks(existing.id)
        bound.info(
            "ingest_skipped", document_id=existing.id, chunks=chunk_count, reason="unchanged"
        )
        return IngestResult(
            path=path,
            status="skipped",
            document_id=existing.id,
            chunk_count=chunk_count,
            page_count=existing.page_count,
        )

    document = await _claim(repo, existing, path, digest)
    await session.commit()
    bound = bound.bind(document_id=document.id)

    try:
        chunks, page_count = _prepare(path, cfg, embedder)
        vectors = await embedder.embed_texts([c.content for c in chunks])

        await store.delete_by_document(document.id)
        inserted = await store.add_chunks(document.id, chunks, vectors)
        await repo.set_status(document, DocumentStatus.DONE, page_count=page_count)
        await session.commit()
    except Exception as exc:
        await session.rollback()
        reason = f"{type(exc).__name__}: {exc}"[:MAX_ERROR_CHARS]
        bound.error("ingest_failed", error=reason, exc_info=True)
        await repo.set_status(document, DocumentStatus.FAILED, error_message=reason)
        await session.commit()
        return IngestResult(path=path, status="failed", document_id=document.id, error=reason)

    bound.info("ingest_done", chunks=inserted, pages=page_count)
    return IngestResult(
        path=path,
        status="ingested",
        document_id=document.id,
        chunk_count=inserted,
        page_count=page_count,
    )


async def ingest_paths(
    session: AsyncSession,
    paths: Sequence[Path],
    *,
    force: bool = False,
    embedder: Embedder | None = None,
    cfg: PipelineConfig | None = None,
) -> list[IngestResult]:
    """Ingest many files, one at a time, continuing past a failure.

    Sequential on purpose: the embedding provider is the bottleneck and it is rate-limited, so
    concurrency here would buy latency and pay for it in 429s.
    """
    embedder = embedder or get_embedder()
    cfg = cfg or get_settings().pipeline_config()
    return [
        await ingest_file(session, path, force=force, embedder=embedder, cfg=cfg) for path in paths
    ]


async def _claim(
    repo: DocumentRepository, existing: Document | None, path: Path, digest: str
) -> Document:
    """Get the document row into `processing`, creating it if this file is new."""
    mime_type = loaders.PDF_MIME if path.suffix.lower() == ".pdf" else loaders.DOCX_MIME
    if existing is None:
        return await repo.create(
            filename=path.name,
            source_path=str(path.resolve()),
            file_hash=digest,
            mime_type=mime_type,
            status=DocumentStatus.PROCESSING,
        )

    # Same bytes, possibly moved or renamed since the last run — keep the row, refresh where
    # it came from, and let the re-ingest replace its chunks.
    existing.filename = path.name
    existing.source_path = str(path.resolve())
    await repo.set_status(existing, DocumentStatus.PROCESSING)
    return existing


def _prepare(
    path: Path, cfg: PipelineConfig, embedder: Embedder
) -> tuple[list[TextChunk], int | None]:
    """Load, chunk and count tokens. Pure CPU — no database, no network."""
    document = loaders.load(path)
    chunks = chunk(document.pages, cfg)
    if not chunks:
        raise IngestFailed(
            str(path),
            "no extractable text — a scanned PDF needs OCR, which is out of scope for v1",
        )
    counted = [
        TextChunk(
            content=c.content,
            page_no=c.page_no,
            chunk_index=c.chunk_index,
            token_count=embedder.count_tokens(c.content),
        )
        for c in chunks
    ]
    return counted, document.page_count
