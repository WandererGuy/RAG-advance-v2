"""Validate a golden-set file, and the corpus it points at.

    python -m eval.datasets.validate                       # validate golden_qa.v1.jsonl
    python -m eval.datasets.validate --no-db               # structure only, no database
    python -m eval.datasets.validate --write-lock          # (re)freeze the corpus

Two things are checked, and the second is the one that will save a run:

1. **The dataset is well formed** — one JSON object per line, unique ids, a known `type`, and an
   `author` on every line. A line without `author` is rejected outright: ADR-0004 makes the
   provenance of the questions part of the data, not a footnote, because every results file has
   to carry it forward into `golden_set_author`.
2. **The corpus still is what the dataset was written against** — `corpus.lock.json` pins each
   document's `file_hash` to the chunk ids it produced. `relevant_chunk_ids` are integers with no
   meaning of their own; a `make ingest FORCE=1` deletes and reinserts chunks, which assigns new
   ids, and every id in the golden set then silently points at the wrong text. That failure is
   invisible in the numbers — recall just drops and looks like a bad pipeline. The lock turns it
   into a loud error here instead.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.db.session import dispose_engine, session_scope
from app.repositories.document_repo import CorpusChunkRow, DocumentRepository

DATASETS_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET = DATASETS_DIR / "golden_qa.v1.jsonl"
LOCK_PATH = DATASETS_DIR / "corpus.lock.json"

REQUIRED_FIELDS = {"id", "q", "ground_truth", "relevant_chunk_ids", "type", "author"}
QUESTION_TYPES = {"factual", "multi_hop", "unanswerable"}
MIN_QUESTIONS = 20
MIN_UNANSWERABLE = 3


@dataclass
class Report:
    errors: list[str]
    warnings: list[str]
    counts: Counter[str]

    @property
    def ok(self) -> bool:
        return not self.errors


# --- dataset structure (no database) ---------------------------------------------


def load_lines(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse a .jsonl file. Returns the records that parsed, and one error per line that did not."""
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"line {number}: not valid JSON ({exc.msg} at column {exc.colno})")
            continue
        if not isinstance(parsed, dict):
            errors.append(f"line {number}: expected a JSON object, got {type(parsed).__name__}")
            continue
        parsed["_line"] = number
        records.append(parsed)
    return records, errors


def check_records(records: list[dict[str, Any]]) -> Report:
    """Every structural rule that does not need the database."""
    errors: list[str] = []
    warnings: list[str] = []
    counts: Counter[str] = Counter()
    seen: dict[str, int] = {}

    for record in records:
        line = record.get("_line")
        where = f"line {line}"
        fields = set(record) - {"_line"}

        if missing := REQUIRED_FIELDS - fields:
            errors.append(f"{where}: missing field(s) {sorted(missing)}")
        if unknown := fields - REQUIRED_FIELDS:
            # A typo'd field name is silent data loss: the runner would never read it.
            errors.append(f"{where}: unknown field(s) {sorted(unknown)}")
        if missing:
            continue

        question_id = record["id"]
        where = f"{question_id} ({where})"
        if question_id in seen:
            errors.append(f"{where}: duplicate id, already used on line {seen[question_id]}")
        else:
            seen[question_id] = line  # type: ignore[assignment]

        for field in ("q", "ground_truth", "author"):
            value = record[field]
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{where}: '{field}' must be a non-empty string")

        question_type = record["type"]
        if question_type not in QUESTION_TYPES:
            errors.append(f"{where}: type {question_type!r} not in {sorted(QUESTION_TYPES)}")
        else:
            counts[question_type] += 1
            counts[f"author:{record['author']}"] += 1

        chunk_ids = record["relevant_chunk_ids"]
        if not isinstance(chunk_ids, list) or not all(isinstance(i, int) for i in chunk_ids):
            errors.append(f"{where}: 'relevant_chunk_ids' must be a list of integers")
            continue
        if len(set(chunk_ids)) != len(chunk_ids):
            errors.append(f"{where}: 'relevant_chunk_ids' repeats an id")

        if question_type == "unanswerable" and chunk_ids:
            errors.append(
                f"{where}: an unanswerable question must have relevant_chunk_ids == [], "
                f"got {chunk_ids}"
            )
        if question_type == "factual" and not chunk_ids:
            errors.append(f"{where}: a factual question needs at least 1 relevant chunk")
        if question_type == "multi_hop" and len(chunk_ids) < 2:
            errors.append(
                f"{where}: a multi_hop question needs at least 2 relevant chunks, got "
                f"{len(chunk_ids)} — if one chunk answers it, it is factual"
            )

    counts["total"] = len(records)
    if len(records) < MIN_QUESTIONS:
        errors.append(f"{len(records)} questions, the Definition of Done needs {MIN_QUESTIONS}")
    if counts["unanswerable"] < MIN_UNANSWERABLE:
        errors.append(
            f"{counts['unanswerable']} unanswerable questions, need {MIN_UNANSWERABLE} — without "
            "them nothing measures whether the system dares to say it does not know"
        )
    if len(set(r.get("author") for r in records)) == 1 and records:
        author = records[0].get("author")
        if author == "agent":
            warnings.append(
                "every question is agent-authored: read ADR-0004 before quoting any number "
                "produced against this dataset"
            )

    return Report(errors=errors, warnings=warnings, counts=counts)


# --- corpus lock -----------------------------------------------------------------


def build_lock(rows: list[CorpusChunkRow]) -> dict[str, Any]:
    """The lock: per document, its file_hash and the chunk ids that hash produced."""
    by_document: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry = by_document.setdefault(
            row.file_hash,
            {"filename": row.filename, "file_hash": row.file_hash, "chunk_ids": [], "digest": ""},
        )
        entry["chunk_ids"].append(row.chunk_id)

    digest = hashlib.sha256()
    for row in rows:
        digest.update(f"{row.file_hash}\x1f{row.chunk_index}\x1f{row.content}\x1e".encode())

    return {
        "chunk_count": len(rows),
        "corpus_digest": digest.hexdigest(),
        "documents": sorted(by_document.values(), key=lambda d: str(d["filename"])),
    }


def compare_lock(lock: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """Explain, in terms of what someone actually did, how the corpus drifted."""
    errors: list[str] = []
    locked_docs = {d["file_hash"]: d for d in lock["documents"]}
    current_docs = {d["file_hash"]: d for d in current["documents"]}

    for file_hash, doc in locked_docs.items():
        if file_hash not in current_docs:
            errors.append(
                f"{doc['filename']}: in the lock but not in the database — it was deleted, "
                "or the file was edited and re-ingested under a new hash"
            )
            continue
        if doc["chunk_ids"] != current_docs[file_hash]["chunk_ids"]:
            errors.append(
                f"{doc['filename']}: chunk ids changed "
                f"{doc['chunk_ids']} -> {current_docs[file_hash]['chunk_ids']} — this is what a "
                "`make ingest FORCE=1` does, and every relevant_chunk_ids in the golden set now "
                "points at the wrong text"
            )

    for file_hash, doc in current_docs.items():
        if file_hash not in locked_docs:
            errors.append(
                f"{doc['filename']}: in the database but not in the lock — a document was added "
                "after the corpus was frozen. Extend the golden set, then --write-lock"
            )

    if not errors and lock["corpus_digest"] != current["corpus_digest"]:
        errors.append(
            "chunk ids match but the chunk text does not: the chunker changed under a frozen "
            "corpus. Every question was written against different text"
        )
    return errors


async def check_corpus(chunk_ids: set[int], *, write_lock: bool) -> tuple[list[str], list[str]]:
    async with session_scope() as session:
        rows = await DocumentRepository(session).all_chunks_for_lock()

    errors: list[str] = []
    warnings: list[str] = []
    current = build_lock(rows)

    if write_lock:
        payload = {
            "note": (
                "Frozen corpus for eval/datasets/*.jsonl. relevant_chunk_ids are only meaningful "
                "against this exact state — see ADR-0005."
            ),
            **current,
        }
        LOCK_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", "utf-8")
        warnings.append(f"wrote {LOCK_PATH.name}: {current['chunk_count']} chunks")
    elif LOCK_PATH.exists():
        errors.extend(compare_lock(json.loads(LOCK_PATH.read_text("utf-8")), current))
    else:
        warnings.append(f"{LOCK_PATH.name} does not exist — run --write-lock to freeze the corpus")

    known = {row.chunk_id for row in rows}
    if missing := sorted(chunk_ids - known):
        errors.append(f"relevant_chunk_ids not present in the database: {missing}")

    return errors, warnings


# --- entrypoint ------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="eval.datasets.validate",
        description="Validate a golden-set .jsonl file and the frozen corpus behind it.",
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--no-db", action="store_true", help="skip every check that needs a database"
    )
    parser.add_argument(
        "--write-lock",
        action="store_true",
        help="freeze the current corpus into corpus.lock.json (overwrites it)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.dataset.exists():
        print(f"error: no dataset at {args.dataset}", file=sys.stderr)
        return 2

    records, parse_errors = load_lines(args.dataset)
    report = check_records(records)
    report.errors = parse_errors + report.errors

    if not args.no_db:
        chunk_ids = {
            i
            for r in records
            for i in r.get("relevant_chunk_ids", [])
            if isinstance(i, int)  # malformed ones are already reported above
        }
        errors, warnings = asyncio.run(_check_corpus(chunk_ids, write_lock=args.write_lock))
        report.errors += errors
        report.warnings += warnings

    return _print_report(args.dataset, report)


async def _check_corpus(chunk_ids: set[int], *, write_lock: bool) -> tuple[list[str], list[str]]:
    try:
        return await check_corpus(chunk_ids, write_lock=write_lock)
    finally:
        await dispose_engine()


def _print_report(dataset: Path, report: Report) -> int:
    print(f"{dataset.name}: {report.counts['total']} question(s)")
    for question_type in sorted(QUESTION_TYPES):
        print(f"  {question_type:14s} {report.counts[question_type]}")
    for key in sorted(k for k in report.counts if k.startswith("author:")):
        print(f"  {key:14s} {report.counts[key]}")

    for warning in report.warnings:
        print(f"warning: {warning}")
    for error in report.errors:
        print(f"error: {error}", file=sys.stderr)

    print("PASS" if report.ok else f"FAIL ({len(report.errors)} error(s))")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
