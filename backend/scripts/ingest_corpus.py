"""CLI: ingest a corpus directory (or a single file) into the database.

    python -m scripts.ingest_corpus --path ../data/raw [--force]

print() is deliberate here — scripts/ is the one place CLAUDE.md 6 allows it. The structured
JSON log stream still carries every per-document event; this is the human-facing summary.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from tqdm import tqdm

from app.core.config import REPO_ROOT, get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import dispose_engine, session_scope
from app.repositories.document_repo import DocumentRepository
from app.services.ingest_service import IngestResult, ingest_file, iter_supported_files

log = get_logger(__name__)

DEFAULT_PATH = REPO_ROOT / "data" / "raw"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ingest_corpus",
        description="Chunk, embed and store every supported document under --path.",
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_PATH,
        help=f"file or directory to ingest (default: {DEFAULT_PATH})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-ingest documents already marked done; their chunks are deleted and rebuilt, "
        "which assigns new chunk ids",
    )
    return parser.parse_args(argv)


async def run(path: Path, *, force: bool) -> int:
    """Ingest everything under `path`. Returns the process exit code."""
    if not path.exists():
        print(f"error: path does not exist: {path}", file=sys.stderr)
        return 2

    files = list(iter_supported_files(path))
    if not files:
        print(f"error: no .pdf or .docx files under {path}", file=sys.stderr)
        return 2

    settings = get_settings()
    print(f"ingesting {len(files)} file(s) from {path}")
    print(f"  embedding: {settings.embedding_model} @ {settings.embedding_dimensions}d")
    print(f"  chunking:  size={settings.chunk_size} overlap={settings.chunk_overlap}")
    if force:
        print("  --force:   existing chunks will be deleted and rebuilt with new ids")

    results: list[IngestResult] = []
    async with session_scope() as session:
        progress = tqdm(files, unit="doc", desc="ingest")
        for file_path in progress:
            progress.set_postfix_str(file_path.name[:40])
            results.append(await ingest_file(session, file_path, force=force))
        progress.close()

        repo = DocumentRepository(session)
        status_counts = await repo.status_counts()
        total_chunks = await repo.count_chunks()

    _summarize(results, status_counts, total_chunks)
    return 1 if any(r.status == "failed" for r in results) else 0


def _summarize(
    results: list[IngestResult], status_counts: dict[str, int], total_chunks: int
) -> None:
    ingested = [r for r in results if r.status == "ingested"]
    skipped = [r for r in results if r.status == "skipped"]
    failed = [r for r in results if r.status == "failed"]

    print("\n" + "=" * 72)
    print(f"ingested {len(ingested)}  ·  skipped {len(skipped)}  ·  failed {len(failed)}")
    print(f"chunks written this run: {sum(r.chunk_count for r in ingested)}")
    print(f"documents table: {status_counts or 'empty'}")
    print(f"chunks table:    {total_chunks}")

    for result in failed:
        print(f"  FAILED  {result.path.name}: {result.error}", file=sys.stderr)

    if ingested:
        # The corpus is frozen (ADR-0005): anything that wrote chunks may have just invalidated
        # every relevant_chunk_ids in the golden set, and only the lock check will say so.
        print("\nnext: confirm the golden set still points at the right chunks")
        print("  make validate")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging()
    try:
        return asyncio.run(_main(args.path, force=args.force))
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


async def _main(path: Path, *, force: bool) -> int:
    try:
        return await run(path, force=force)
    finally:
        # Scripts own the engine's lifetime; leaving the pool open holds asyncpg connections
        # past the end of the event loop and produces a noisy shutdown.
        await dispose_engine()


if __name__ == "__main__":
    raise SystemExit(main())
