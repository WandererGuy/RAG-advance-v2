"""The golden-set validator is the only thing that can catch a silently invalidated dataset.

Two failures it exists for, neither of which shows up as an error anywhere else: a question
whose `author` was dropped (ADR-0004 makes provenance part of the data), and a corpus that was
re-ingested after the questions were written, which renumbers chunk ids and points every
`relevant_chunk_ids` at the wrong text. No DB, no network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.repositories.document_repo import CorpusChunkRow
from eval.datasets.validate import (
    DEFAULT_DATASET,
    build_lock,
    check_records,
    compare_lock,
    load_lines,
)


def make_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "id": "q001",
        "q": "Mỗi tháng được hỗ trợ bao nhiêu tiền bữa trưa?",
        "ground_truth": "1.100.000 đồng/tháng.",
        "relevant_chunk_ids": [5],
        "type": "factual",
        "author": "agent",
        "_line": 1,
    }
    return record | overrides


def errors_for(*records: dict[str, object]) -> list[str]:
    """Structural errors only, with the two corpus-wide minimums filtered out."""
    report = check_records(list(records))
    corpus_wide = ("Definition of Done", "questions, need")
    return [e for e in report.errors if not any(f in e for f in corpus_wide)]


# --- the committed dataset ---------------------------------------------------------


def test_committed_dataset_is_structurally_valid() -> None:
    records, parse_errors = load_lines(DEFAULT_DATASET)
    report = check_records(records)
    assert parse_errors == []
    assert report.errors == []
    assert report.counts["total"] >= 20


def test_every_committed_question_declares_an_author() -> None:
    records, _ = load_lines(DEFAULT_DATASET)
    assert all(r["author"] for r in records)


# --- structure ---------------------------------------------------------------------


def test_missing_author_is_rejected() -> None:
    record = make_record()
    del record["author"]
    assert any("'author'" in e for e in errors_for(record))


def test_blank_author_is_rejected() -> None:
    assert any("'author'" in e for e in errors_for(make_record(author="  ")))


def test_unknown_field_is_rejected() -> None:
    # A typo'd key is silent data loss: the runner would simply never read it.
    assert any("unknown field" in e for e in errors_for(make_record(relevant_chunks=[5])))


def test_duplicate_id_is_rejected() -> None:
    first = make_record()
    second = make_record(_line=2)
    assert any("duplicate id" in e for e in errors_for(first, second))


@pytest.mark.parametrize(
    ("record", "fragment"),
    [
        (make_record(type="factoid"), "not in"),
        (make_record(type="factual", relevant_chunk_ids=[]), "at least 1"),
        (make_record(type="multi_hop", relevant_chunk_ids=[5]), "at least 2"),
        (make_record(type="unanswerable", relevant_chunk_ids=[5]), "must have relevant_chunk_ids"),
        (make_record(relevant_chunk_ids=[5, 5]), "repeats an id"),
        (make_record(relevant_chunk_ids=["5"]), "list of integers"),
    ],
)
def test_rejected_shapes(record: dict[str, object], fragment: str) -> None:
    assert any(fragment in e for e in errors_for(record))


def test_too_few_questions_fails_the_definition_of_done() -> None:
    report = check_records([make_record()])
    assert any("Definition of Done" in e for e in report.errors)


def test_an_all_agent_dataset_warns() -> None:
    report = check_records([make_record()])
    assert any("ADR-0004" in w for w in report.warnings)


def test_malformed_json_reports_its_line_number() -> None:
    path = Path(__file__).parent / "_broken.jsonl"
    path.write_text('{"id": "q001"}\nnot json\n', encoding="utf-8")
    try:
        records, errors = load_lines(path)
        assert len(records) == 1
        assert errors and "line 2" in errors[0]
    finally:
        path.unlink()


# --- corpus lock -------------------------------------------------------------------


def rows(*ids: int) -> list[CorpusChunkRow]:
    return [
        CorpusChunkRow(
            chunk_id=chunk_id,
            file_hash="hash-a",
            filename="01_so_tay_nhan_vien.pdf",
            page_no=1,
            chunk_index=index,
            content=f"nội dung {index}",
        )
        for index, chunk_id in enumerate(ids)
    ]


def test_unchanged_corpus_compares_clean() -> None:
    lock = build_lock(rows(1, 2, 3))
    assert compare_lock(lock, build_lock(rows(1, 2, 3))) == []


def test_reingest_that_renumbers_ids_is_caught() -> None:
    # Exactly what `make ingest FORCE=1` does: same text, new ids.
    lock = build_lock(rows(1, 2, 3))
    errors = compare_lock(lock, build_lock(rows(41, 42, 43)))
    assert any("chunk ids changed" in e for e in errors)


def test_changed_chunk_text_under_stable_ids_is_caught() -> None:
    lock = build_lock(rows(1, 2, 3))
    current = build_lock(rows(1, 2, 3))
    current["corpus_digest"] = "0" * 64
    assert any("chunk text does not" in e for e in compare_lock(lock, current))


def test_added_document_is_caught() -> None:
    lock = build_lock(rows(1, 2))
    current = build_lock(rows(1, 2))
    current["documents"].append({"filename": "09_new.pdf", "file_hash": "hash-b", "chunk_ids": [3]})
    assert any("not in the lock" in e for e in compare_lock(lock, current))


def test_removed_document_is_caught() -> None:
    lock = build_lock(rows(1, 2))
    current = build_lock(rows(1, 2))
    current["documents"] = []
    assert any("not in the database" in e for e in compare_lock(lock, current))


def test_committed_lock_matches_the_committed_dataset() -> None:
    """Every relevant_chunk_id must exist in the frozen corpus, without touching the database."""
    lock = json.loads((DEFAULT_DATASET.parent / "corpus.lock.json").read_text("utf-8"))
    frozen = {i for doc in lock["documents"] for i in doc["chunk_ids"]}
    records, _ = load_lines(DEFAULT_DATASET)
    cited = {i for r in records for i in r["relevant_chunk_ids"]}
    assert cited <= frozen
