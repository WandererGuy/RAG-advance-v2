"""Provenance: a number may not leave this project without the questions that produced it.

CLAUDE.md 8 and ADR-0004 make `golden_set_author` part of every results file and a column in
the leaderboard. This file is what stops that from being a convention someone forgets. It also
covers the runner's refusal to overwrite a results file, since a committed results file is the
fixed point its pipeline is frozen against. No DB, no network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.core.config import get_settings
from eval.report import render
from eval.runner import (
    QuestionRun,
    build_payload,
    dataset_path,
    dataset_version,
    golden_set_author,
    write_results,
)

CONFIG = get_settings().pipeline_config(retriever="dense")


def records(*authors: str) -> list[dict[str, Any]]:
    return [
        {
            "id": f"q{n:03d}",
            "q": "câu hỏi",
            "ground_truth": "trả lời",
            "relevant_chunk_ids": [1],
            "type": "factual",
            "author": author,
        }
        for n, author in enumerate(authors, start=1)
    ]


def payload_for(*authors: str, **overrides: Any) -> dict[str, Any]:
    rows = records(*authors)
    payload = build_payload(
        pipeline_name="naive-v1",
        config=CONFIG,
        records=rows,
        runs=[QuestionRun(record=r, error="LLMCallFailed: no key") for r in rows],
        dataset=Path("eval/datasets/golden_qa.v1.jsonl"),
        judge_model=CONFIG.llm_model,
        elapsed_seconds=1.0,
        validated=True,
    )
    return payload | overrides


class TestDatasetNaming:
    def test_version_shorthand_resolves_to_a_file(self) -> None:
        assert dataset_path("v1").name == "golden_qa.v1.jsonl"

    def test_an_explicit_path_is_used_as_given(self) -> None:
        assert dataset_path("/tmp/mine.jsonl") == Path("/tmp/mine.jsonl")

    def test_version_is_read_back_out_of_the_filename(self) -> None:
        assert dataset_version(Path("golden_qa.v2.jsonl")) == "v2"


class TestGoldenSetAuthor:
    def test_sorted_and_deduplicated(self) -> None:
        assert golden_set_author(records("agent", "hoa", "agent")) == ["agent", "hoa"]

    def test_a_mixed_dataset_keeps_both_names(self) -> None:
        # A v2 written by a person lands beside agent lines during the transition; summarising
        # that to one label is exactly the information ADR-0004 refuses to lose.
        payload = payload_for("agent", "hoa")
        assert payload["golden_set_author"] == ["agent", "hoa"]


class TestResultsPayload:
    def test_carries_the_full_provenance_block(self) -> None:
        payload = payload_for("agent")
        for key in (
            "pipeline_name",
            "config",
            "dataset_version",
            "golden_set_author",
            "judge_model",
            "git_sha",
            "timestamp",
        ):
            assert key in payload, f"results file lost {key}"
        assert payload["config"]["top_k"] == CONFIG.top_k

    def test_self_judging_is_recorded(self) -> None:
        # The judge being the answering model is a caveat on every generation score (ADR-0006).
        assert payload_for("agent")["judge_is_answer_model"] is True

    def test_failed_questions_are_counted_not_dropped(self) -> None:
        payload = payload_for("agent", "agent")
        assert payload["question_count"] == 2
        assert payload["failed_questions"] == 2
        assert payload["questions"][0]["error"].startswith("LLMCallFailed")


class TestWriteResults:
    def test_refuses_to_clobber_an_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "naive-v1.json"
        target.write_text("{}", encoding="utf-8")
        with pytest.raises(SystemExit, match="already exists"):
            write_results(payload_for("agent"), target, overwrite=False)

    def test_overwrite_is_explicit(self, tmp_path: Path) -> None:
        target = tmp_path / "naive-v1.json"
        write_results(payload_for("agent"), target, overwrite=False)
        write_results(payload_for("agent"), target, overwrite=True)
        assert json.loads(target.read_text(encoding="utf-8"))["pipeline_name"] == "naive-v1"


class TestLeaderboard:
    def test_author_is_a_column_not_a_footnote(self) -> None:
        markdown = render([payload_for("agent") | {"_file": "naive-v1.json"}])
        assert "golden_set_author" in markdown
        assert "| agent |" in markdown

    def test_agent_authorship_is_spelled_out_under_the_table(self) -> None:
        markdown = render([payload_for("agent") | {"_file": "naive-v1.json"}])
        assert "ADR-0004" in markdown

    def test_mixed_datasets_are_flagged_as_incomparable(self) -> None:
        rows = [
            payload_for("agent") | {"_file": "a.json"},
            payload_for("agent", dataset_version="v2") | {"_file": "b.json"},
        ]
        assert "do not share a dataset" in render(rows)

    def test_a_partial_run_is_marked(self) -> None:
        row = payload_for("agent", partial_run={"limit": 3}) | {"_file": "a.json"}
        assert "partial(3)" in render([row])

    def test_no_results_yet(self) -> None:
        assert "No results yet" in render([])
