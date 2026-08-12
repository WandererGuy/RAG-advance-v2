"""CLI: re-embed every chunk in place, after the embedding model changed.

    python -m scripts.reembed_corpus [--dry-run] [--batch 32]

**Why this exists instead of `make ingest FORCE=1`.** A vector is only comparable to vectors
produced by the same model: once `EMBEDDING_MODEL_NAME` changes, every stored embedding belongs
to a vector space the query embedder no longer speaks, and cosine similarity over the mix is
noise that looks like a merely bad retriever. The corpus therefore has to be re-embedded.

The obvious way to do that — a forced re-ingest — deletes and reinserts the chunk rows, which
assigns **new serial ids**. That is precisely the failure ADR-0005 froze the corpus against:
`relevant_chunk_ids` in `golden_qa.v1.jsonl` are bare integers, so every one of them would then
point at the wrong text, `make validate` would fail, and the golden set would need rebuilding by
hand.

So this script does the one thing a re-ingest cannot: it **UPDATEs the embedding column of the
existing rows**. Nothing else about a chunk is touched — not `content`, not `page_no`, not
`chunk_index`, and above all not `id`. `corpus.lock.json` hashes `file_hash + chunk_index +
content` and lists chunk ids; none of those inputs change, so the lock stays valid by
construction and `make validate` keeps passing. Re-embedding is not a corpus change.

Chunking is unchanged too (same size, same overlap, same files), which is what makes this sound:
the text being embedded is byte-for-byte the text the golden set was written against.

print() is deliberate: scripts/ is the one place CLAUDE.md 6 allows it.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import dispose_engine, session_scope
from app.llm.rag.embedder import get_embedder
from app.repositories.document_repo import DocumentRepository


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="reembed_corpus",
        description="Re-embed every chunk in place, preserving chunk ids and the corpus lock.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be re-embedded and exit without calling the provider",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=32,
        help="chunks per UPDATE round-trip (default: 32); embedding batches independently",
    )
    return parser.parse_args(argv)


async def run(*, dry_run: bool, batch: int) -> int:
    settings = get_settings()
    embedder = get_embedder(settings)

    print(f"embedding model : {embedder.model}")
    print(f"dimensions      : {embedder.dimensions}")

    async with session_scope() as session:
        repository = DocumentRepository(session)
        rows = await repository.all_chunks_for_lock()

    if not rows:
        print("no chunks in the database — run `make ingest` first", file=sys.stderr)
        return 2

    print(
        f"chunks to re-embed: {len(rows)} (ids {min(r.chunk_id for r in rows)}"
        f"–{max(r.chunk_id for r in rows)})"
    )

    if dry_run:
        print("\n--dry-run: no provider calls made, nothing written.")
        return 0

    # Embed everything first, then write. A provider failure half-way through leaves the
    # database entirely on the old model rather than in a mix of two vector spaces, which is
    # the one state that is both broken and invisible.
    print("\nembedding…")
    vectors = await embedder.embed_texts([row.content for row in rows])
    if len(vectors) != len(rows):
        print(f"error: got {len(vectors)} vectors for {len(rows)} chunks", file=sys.stderr)
        return 1

    print("writing…")
    written = 0
    async with session_scope() as session:
        repository = DocumentRepository(session)
        for offset in range(0, len(rows), batch):
            window = list(
                zip(
                    rows[offset : offset + batch],
                    vectors[offset : offset + batch],
                    strict=True,
                )
            )
            written += await repository.update_chunk_embeddings(
                {row.chunk_id: vector for row, vector in window}
            )

    print(f"\nre-embedded {written} chunk(s) in place. Chunk ids unchanged.")
    print("Next: `make validate` (the lock must still pass), then re-run every pipeline —")
    print("any results file produced against the old embeddings is no longer comparable.")
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = parse_args(argv)
    try:
        return asyncio.run(_run(dry_run=args.dry_run, batch=args.batch))
    except KeyboardInterrupt:
        print(
            "\ninterrupted — the database is unchanged unless 'writing…' was reached",
            file=sys.stderr,
        )
        return 130


async def _run(*, dry_run: bool, batch: int) -> int:
    try:
        return await run(dry_run=dry_run, batch=batch)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    raise SystemExit(main())
