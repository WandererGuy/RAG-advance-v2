"""CLI: find the chunk id behind a phrase, so a golden-set question can cite it.

    python -m scripts.find_chunks --q "nghỉ phép" --q "thâm niên" [--doc 04] [--limit 20] [--full]

Every --q must appear in the chunk. This is a lookup tool for writing
`eval/datasets/golden_qa.v1.jsonl`, not a retriever — see ADR-0004 on why the questions
themselves must not be drafted from what this prints.

print() is deliberate: scripts/ is the one place CLAUDE.md 6 allows it.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys

from app.core.logging import configure_logging
from app.db.session import dispose_engine, session_scope
from app.repositories.document_repo import ChunkMatch, DocumentRepository

SNIPPET_PAD = 60


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="find_chunks",
        description="Keyword lookup over chunks: prints chunk_id, page_no and a snippet.",
    )
    parser.add_argument(
        "--q",
        action="append",
        required=True,
        metavar="TERM",
        help="term that must appear in the chunk; repeat to AND several together",
    )
    parser.add_argument("--doc", default=None, help="restrict to filenames containing this")
    parser.add_argument("--limit", type=int, default=20, help="max rows (default: 20)")
    parser.add_argument("--full", action="store_true", help="print whole chunks, not snippets")
    return parser.parse_args(argv)


def _snippet(content: str, terms: list[str]) -> str:
    """The window around the first term hit, whitespace-collapsed for one-line printing."""
    flat = re.sub(r"\s+", " ", content)
    lowered = flat.lower()
    positions = [lowered.find(t.lower()) for t in terms]
    hit = min((p for p in positions if p >= 0), default=0)
    start = max(0, hit - SNIPPET_PAD)
    end = min(len(flat), hit + SNIPPET_PAD * 2)
    return ("…" if start else "") + flat[start:end] + ("…" if end < len(flat) else "")


def _print(matches: list[ChunkMatch], terms: list[str], *, full: bool) -> None:
    for match in matches:
        page = f"p.{match.page_no}" if match.page_no is not None else "p.?"
        print(f"\nchunk_id={match.chunk_id}  {match.filename}  {page}  #{match.chunk_index}")
        print(f"  {match.content if full else _snippet(match.content, terms)}")


async def run(terms: list[str], *, doc: str | None, limit: int, full: bool) -> int:
    async with session_scope() as session:
        matches = await DocumentRepository(session).search_text(
            terms, limit=limit, filename_like=doc
        )

    if not matches:
        print(f"no chunk contains all of: {terms}", file=sys.stderr)
        return 1

    print(f"{len(matches)} chunk(s) containing all of: {terms}")
    _print(matches, terms, full=full)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging()
    try:
        return asyncio.run(_main(args))
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


async def _main(args: argparse.Namespace) -> int:
    try:
        return await run(args.q, doc=args.doc, limit=args.limit, full=args.full)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    raise SystemExit(main())
