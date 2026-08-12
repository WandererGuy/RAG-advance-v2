"""Run one pipeline over the golden set and write `results/<pipeline>.json`.

    python -m eval.runner --pipeline naive-v1 [--dataset v1] [--limit N] [--no-judge]

Everything a number needs in order to still mean something in three months goes into that file:
the pipeline name, its **full config**, the dataset version, **`golden_set_author`**, the judge
model, the git sha, the timestamp, the aggregates and every per-question detail. CLAUDE.md 8
and ADR-0004: no score of this system may be read without the provenance of the questions that
produced it, so the runner writes provenance even when it makes the file uglier.

Three refusals built into this file, each of which exists because the alternative silently
produces a wrong number rather than an error:

1. **A run cannot start against a drifted corpus.** `eval.datasets.validate` runs first, lock
   included. `relevant_chunk_ids` after a `make ingest FORCE=1` point at the wrong text, and
   the only symptom would be a recall score that looks like a bad pipeline (ADR-0005).
2. **An existing results file is never overwritten** without `--overwrite`. A committed results
   file is the fixed point its pipeline is frozen against.
3. **A failed question is recorded, not skipped.** It lands in the file with its error and is
   excluded from the means, with the count reported. Dropping it would quietly raise every
   average by removing the hardest questions.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import PipelineConfig
from app.core.exceptions import PipelineNotFound
from app.core.logging import configure_logging, get_logger
from app.db.session import dispose_engine, session_scope
from app.llm.client import get_llm_client
from app.llm.rag.pipelines import available, build_pipeline, get_pipeline
from app.llm.rag.pipelines.base import RAGAnswer
from eval.datasets import validate as dataset_validate
from eval.metrics import generation, retrieval

log = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "results"
SCHEMA_VERSION = 1


@dataclass
class QuestionRun:
    """One question end to end: what the pipeline produced and what it scored."""

    record: dict[str, Any]
    result: RAGAnswer | None = None
    error: str | None = None
    scores: retrieval.RetrievalScores | None = None
    faithfulness: generation.JudgeScore | None = None
    relevance: generation.JudgeScore | None = None
    outcome: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.record["id"],
            "type": self.record["type"],
            "author": self.record["author"],
            "q": self.record["q"],
            "relevant_chunk_ids": self.record["relevant_chunk_ids"],
        }
        if self.error is not None:
            payload["error"] = self.error
            return payload

        assert self.result is not None  # noqa: S101 - error is None means result is set
        payload |= self.result.to_dict()
        payload["outcome"] = self.outcome
        payload["retrieval"] = self.scores.to_dict() if self.scores else None
        payload["faithfulness"] = self.faithfulness.to_dict() if self.faithfulness else None
        payload["answer_relevance"] = self.relevance.to_dict() if self.relevance else None
        return payload


# --- dataset ---------------------------------------------------------------------


def dataset_path(name: str) -> Path:
    """`v1` -> `eval/datasets/golden_qa.v1.jsonl`. A path is also accepted as-is."""
    candidate = Path(name)
    if candidate.suffix == ".jsonl":
        return candidate
    return dataset_validate.DATASETS_DIR / f"golden_qa.{name}.jsonl"


def dataset_version(path: Path) -> str:
    """`golden_qa.v1.jsonl` -> `v1`."""
    parts = path.name.split(".")
    return parts[1] if len(parts) >= 3 else path.stem


def load_dataset(path: Path, *, skip_validation: bool = False) -> list[dict[str, Any]]:
    """Parse and validate. Raises SystemExit rather than running against a broken dataset."""
    if not path.exists():
        raise SystemExit(f"error: no dataset at {path}")

    records, parse_errors = dataset_validate.load_lines(path)
    report = dataset_validate.check_records(records)
    errors = parse_errors + report.errors

    if not skip_validation:
        chunk_ids = {
            i for r in records for i in r.get("relevant_chunk_ids", []) if isinstance(i, int)
        }
        corpus_errors, corpus_warnings = asyncio.run(_validate_corpus(chunk_ids))
        errors += corpus_errors
        report.warnings += corpus_warnings

    for warning in report.warnings:
        print(f"warning: {warning}")
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        raise SystemExit(
            "the dataset or the corpus behind it is not valid — every number this run "
            "produced would be meaningless. Fix it, or re-run with --skip-validation and "
            "accept that the results file says so."
        )
    return records


async def _validate_corpus(chunk_ids: set[int]) -> tuple[list[str], list[str]]:
    """Corpus check in its own event loop, closing the pool behind it.

    The pool must not survive this call: the run itself opens a second `asyncio.run`, and an
    asyncpg connection created in a loop that has since closed fails on first use.
    """
    try:
        return await dataset_validate.check_corpus(chunk_ids, write_lock=False)
    finally:
        await dispose_engine()


def golden_set_author(records: list[dict[str, Any]]) -> list[str]:
    """The sorted distinct authors. Carried into the results file, never summarised away."""
    return sorted({str(r["author"]) for r in records})


# --- the run ---------------------------------------------------------------------


async def run_questions(
    pipeline_name: str,
    records: list[dict[str, Any]],
    *,
    config: PipelineConfig | None = None,
    judge: generation.Judge | None = None,
) -> tuple[list[QuestionRun], PipelineConfig]:
    """Answer every question, score it, and keep going past a failure."""
    runs: list[QuestionRun] = []
    async with session_scope() as session:
        pipeline = build_pipeline(pipeline_name, session, config)
        for position, record in enumerate(records, start=1):
            run = QuestionRun(record=record)
            try:
                run.result = await pipeline.answer(record["q"])
            except Exception as exc:  # noqa: BLE001 - one bad question must not lose the run
                run.error = f"{type(exc).__name__}: {exc}"
                log.error("eval_question_failed", question_id=record["id"], error=run.error)
                runs.append(run)
                continue

            run.scores = retrieval.score_question(
                run.result.chunk_ids, record["relevant_chunk_ids"], pipeline.config.top_k
            )
            run.outcome = generation.refusal_outcome(record["type"], run.result.answer)
            print(
                f"  [{position}/{len(records)}] {record['id']:<5} {run.outcome:<15} "
                f"recall={_fmt(run.scores.recall_at_k)} {run.result.latency_ms:>6} ms"
            )
            runs.append(run)

        config = pipeline.config

    if judge is not None:
        await _judge_runs(runs, judge)
    return runs, config


async def _judge_runs(runs: list[QuestionRun], judge: generation.Judge) -> None:
    """Score faithfulness on every answered question, relevance on the answerable ones.

    Sequential, like ingest: the provider is rate-limited and the eval is not latency-sensitive.
    Judging happens after the database session has closed — a judge call takes seconds and
    holding a Postgres connection open across ~60 of them serves nothing.
    """
    judged = [r for r in runs if r.result is not None]
    for position, run in enumerate(judged, start=1):
        assert run.result is not None  # noqa: S101
        run.faithfulness = await judge.faithfulness(run.result)
        if run.record["type"] != "unanswerable":
            run.relevance = await judge.relevance(
                run.record["q"], run.result.answer, run.record["ground_truth"]
            )
        print(
            f"  judged [{position}/{len(judged)}] {run.record['id']:<5} "
            f"faithfulness={_fmt(run.faithfulness.score)} "
            f"relevance={_fmt(run.relevance.score if run.relevance else None)}"
        )


def build_payload(
    *,
    pipeline_name: str,
    config: PipelineConfig,
    records: list[dict[str, Any]],
    runs: list[QuestionRun],
    dataset: Path,
    judge_model: str | None,
    elapsed_seconds: float,
    validated: bool,
) -> dict[str, Any]:
    """Assemble `results/<pipeline>.json`. Provenance first, then numbers."""
    ok = [r for r in runs if r.result is not None]
    latencies = sorted(r.result.latency_ms for r in ok if r.result)

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "pipeline_name": pipeline_name,
        "config": config.to_dict(),
        "dataset_version": dataset_version(dataset),
        # ADR-0004 / CLAUDE.md 8. Sits beside dataset_version because it qualifies every
        # number below it just as strongly.
        "golden_set_author": golden_set_author(records),
        "judge_model": judge_model,
        "judge_is_answer_model": judge_model == config.llm_model,
        "git_sha": git_sha(),
        "git_dirty": git_dirty(),
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "corpus_validated": validated,
        "question_count": len(runs),
        "failed_questions": len(runs) - len(ok),
        "elapsed_seconds": round(elapsed_seconds, 1),
        "metrics": {
            "retrieval": retrieval.aggregate([r.scores for r in ok if r.scores], config.top_k),
            **generation.aggregate(
                [r.faithfulness for r in ok if r.faithfulness],
                [r.relevance for r in ok if r.relevance],
                [r.outcome for r in ok if r.outcome],
            ),
            "citations": generation.citation_stats([r.result for r in ok if r.result]),
            "latency_ms": {
                "p50": _percentile(latencies, 50),
                "p95": _percentile(latencies, 95),
                "max": latencies[-1] if latencies else None,
            },
        },
        "questions": [r.to_dict() for r in runs],
    }
    return payload


def write_results(payload: dict[str, Any], path: Path, *, overwrite: bool) -> None:
    """Write the file, refusing to clobber an existing one without being told to."""
    if path.exists() and not overwrite:
        raise SystemExit(
            f"error: {_display(path)} already exists. A committed results file is "
            "the fixed point its pipeline is frozen against (CLAUDE.md 4.1) — to try a new "
            "idea, add a new pipeline with a new name. Pass --overwrite only if this run "
            "replaces a result that was never committed."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# --- helpers ---------------------------------------------------------------------


def _display(path: Path) -> str:
    """Repo-relative when it can be, absolute otherwise — `--out` may point anywhere."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def git_sha() -> str:
    return _git("rev-parse", "HEAD") or "unknown"


def git_dirty() -> bool:
    """True when the tree had uncommitted changes — the code that ran is not the sha."""
    return bool(_git("status", "--porcelain"))


def _git(*args: str) -> str:
    try:
        return subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _percentile(values: list[int], percentile: int) -> int | None:
    if not values:
        return None
    index = min(len(values) - 1, int(round((percentile / 100) * (len(values) - 1))))
    return values[index]


def _fmt(value: float | None) -> str:
    return "  n/a" if value is None else f"{value:5.2f}"


def print_summary(payload: dict[str, Any]) -> None:
    metrics = payload["metrics"]
    k = payload["config"]["top_k"]
    print(f"\n{payload['pipeline_name']}  ({payload['question_count']} questions)")
    print(f"  dataset            {payload['dataset_version']}")
    print(f"  golden_set_author  {', '.join(payload['golden_set_author'])}")
    print(f"  recall@{k}           {metrics['retrieval'][f'recall@{k}']}")
    print(f"  mrr                {metrics['retrieval']['mrr']}")
    print(f"  ndcg@{k}             {metrics['retrieval'][f'ndcg@{k}']}")
    print(
        f"  faithfulness       {metrics['faithfulness']['mean']} "
        f"({metrics['faithfulness']['scored']} scored)"
    )
    print(
        f"  answer_relevance   {metrics['answer_relevance']['mean']} "
        f"({metrics['answer_relevance']['scored']} scored)"
    )
    print(f"  refusal_accuracy   {metrics['refusal_accuracy']}   outcomes={metrics['outcomes']}")
    print(
        f"  latency p50/p95    {metrics['latency_ms']['p50']} / {metrics['latency_ms']['p95']} ms"
    )
    if payload["failed_questions"]:
        print(f"  FAILED QUESTIONS   {payload['failed_questions']}")
    if payload["golden_set_author"] == ["agent"]:
        print("\nwarning: every question is agent-authored — read ADR-0004 before quoting these.")


# --- entrypoint ------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="eval.runner",
        description="Run one registered pipeline over a golden set and write results/<name>.json.",
    )
    parser.add_argument(
        "--pipeline",
        required=True,
        help=f"registered pipeline (available: {', '.join(available())})",
    )
    parser.add_argument("--dataset", default="v1", help="dataset version or path (default: v1)")
    parser.add_argument("--limit", type=int, default=None, help="run only the first N questions")
    parser.add_argument(
        "--out", type=Path, default=None, help="results file (default: results/<pipeline>.json)"
    )
    parser.add_argument("--overwrite", action="store_true", help="replace an existing results file")
    parser.add_argument(
        "--no-judge", action="store_true", help="skip the LLM judge (retrieval + refusal only)"
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help="override the judge model (default: the answering model)",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="do not check the corpus lock first — the results file records that it was skipped",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging()

    # Checked first, before the database and before the dataset: a typo in --pipeline is the
    # most likely way to start a run, and it should cost nothing rather than a full validation
    # pass and a traceback.
    try:
        get_pipeline(args.pipeline)
    except PipelineNotFound as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    out = args.out or RESULTS_DIR / f"{args.pipeline}.json"
    if out.exists() and not args.overwrite:
        # Also checked up front. Discovering it after ~80 provider calls would be a waste of
        # quota and, worse, an invitation to pass --overwrite in irritation.
        print(
            f"error: {_display(out)} already exists — a committed results file is the fixed "
            "point its pipeline is frozen against (CLAUDE.md 4.1). New idea, new pipeline "
            "name; --overwrite only replaces a result that was never committed.",
            file=sys.stderr,
        )
        return 2

    dataset = dataset_path(args.dataset)
    records = load_dataset(dataset, skip_validation=args.skip_validation)
    if args.limit is not None:
        records = records[: args.limit]
        print(f"warning: --limit {args.limit} — a partial run, not a comparable result")

    judge = None if args.no_judge else generation.Judge(get_llm_client(model=args.judge_model))

    print(f"running {args.pipeline} over {dataset.name} ({len(records)} questions)")
    started = time.perf_counter()
    try:
        runs, config = asyncio.run(_run(args.pipeline, records, judge=judge))
    except KeyboardInterrupt:
        print("\ninterrupted — nothing written", file=sys.stderr)
        return 130

    payload = build_payload(
        pipeline_name=args.pipeline,
        config=config,
        records=records,
        runs=runs,
        dataset=dataset,
        judge_model=judge.model if judge else None,
        elapsed_seconds=time.perf_counter() - started,
        validated=not args.skip_validation,
    )
    if args.limit is not None:
        payload["partial_run"] = {"limit": args.limit}

    write_results(payload, out, overwrite=args.overwrite)
    print_summary(payload)
    print(f"\nwrote {_display(out)}")
    return 0


async def _run(
    pipeline_name: str,
    records: list[dict[str, Any]],
    *,
    judge: generation.Judge | None,
) -> tuple[list[QuestionRun], PipelineConfig]:
    # No config is supplied: each pipeline's `build()` names its own retriever, and the runner
    # must not overrule it. This used to pass `retriever="dense"` — correct while dense was the
    # only retriever, and a mislabelling bug the moment `hybrid-v2` arrived, because the run
    # really was hybrid while `results/hybrid-v2.json` said `"retriever": "dense"`. A results
    # file that misreports its own configuration defeats the reason the config is in there.
    try:
        return await run_questions(pipeline_name, records, config=None, judge=judge)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    raise SystemExit(main())
