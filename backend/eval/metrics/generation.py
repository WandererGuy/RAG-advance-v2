"""Generation metrics: `faithfulness`, `answer_relevance` (a model judges), `refusal_accuracy`
and the citation checks (arithmetic).

Read ADR-0006 before quoting any number from this file. Two things in it decide what these
numbers are worth:

* **The judge is the same model that wrote the answer.** There is one provider configured, so
  `gemini-3.6-flash` grades its own output. That inflates scores in a known direction and is
  worth doing anyway — a self-graded score still moves when a pipeline gets better, which is
  all Phase 6 needs. `--judge-model` overrides it, and the model used is written into every
  results file.
* **Refusal is not judged, it is detected.** `is_refusal()` is an exact-string check against
  the sentence `answer_v1.jinja` demands. The safety-critical metric of this project does not
  get to depend on a model's mood.

A judge that fails to return parseable JSON produces `None`, never a default score. A silent
3-out-of-5 for a call that never succeeded would be indistinguishable from a real mediocre
answer, so the count of failures is reported next to the mean instead.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.llm.client import LLMClient
from app.llm.prompts import render_template
from app.llm.rag.pipelines.base import RAGAnswer, is_refusal

JUDGE_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "judge_prompts"

SCORE_MIN = 1
SCORE_MAX = 5
# One retry: a judge that returns prose instead of JSON usually complies on a second ask, and
# more than one retry per question turns a 29-question run into a quota problem.
JUDGE_ATTEMPTS = 2

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True)
class JudgeScore:
    """One judgement. `score is None` means the judge failed, not that it scored badly."""

    score: int | None
    reason: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"score": self.score, "reason": self.reason}
        if self.error:
            payload["error"] = self.error
        return payload


class Judge:
    """LLM-as-judge over `eval/judge_prompts/*.jinja`."""

    def __init__(self, llm: LLMClient, *, prompt_version: str = "v1") -> None:
        self._llm = llm
        self._version = prompt_version
        self.model = llm.model

    async def faithfulness(self, result: RAGAnswer) -> JudgeScore:
        """Is every claim supported by the chunks this answer was actually given?

        Judged for every question, including `unanswerable` ones: a fabricated answer to a
        question with no support in the corpus is exactly what this metric exists to catch,
        and skipping those would remove the most dangerous case from the measurement.
        """
        return await self._judge(
            f"faithfulness_{self._version}",
            question=result.question,
            answer=result.answer,
            chunks=result.retrieved,
        )

    async def relevance(self, question: str, answer: str, ground_truth: str) -> JudgeScore:
        """Does the answer answer the question, against the golden set's reference answer?"""
        return await self._judge(
            f"relevance_{self._version}",
            question=question,
            answer=answer,
            ground_truth=ground_truth,
        )

    async def _judge(self, prompt_name: str, **context: Any) -> JudgeScore:
        prompt = render_template(JUDGE_PROMPTS_DIR, prompt_name, **context)
        last_error = ""
        for _ in range(JUDGE_ATTEMPTS):
            try:
                response = await self._llm.complete(prompt, temperature=0.0)
            except Exception as exc:  # noqa: BLE001 - recorded per question, never fatal
                last_error = f"{type(exc).__name__}: {exc}"
                continue
            score, reason, error = parse_judgement(response.text)
            if score is not None:
                return JudgeScore(score=score, reason=reason)
            last_error = error
        return JudgeScore(score=None, error=last_error or "judge returned no usable score")


def parse_judgement(text: str) -> tuple[int | None, str, str]:
    """Read `{"score": n, "reason": "..."}` out of a completion. Returns (score, reason, error).

    Tolerant about what wraps the JSON — a ```json fence or a sentence before it is common and
    harmless — and strict about the score itself: out of range is a failure, not a clamp, since
    a clamped 7 would enter the mean as a 5 and quietly raise it.
    """
    match = _JSON_OBJECT.search(text)
    if not match:
        return None, "", f"no JSON object in judge output: {text[:200]!r}"
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        return None, "", f"judge output is not valid JSON ({exc.msg}): {match.group(0)[:200]!r}"
    if not isinstance(payload, dict):
        return None, "", f"judge returned {type(payload).__name__}, expected an object"

    raw = payload.get("score")
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return None, "", f"judge score is not a number: {raw!r}"
    score = int(raw)
    if not SCORE_MIN <= score <= SCORE_MAX:
        return None, "", f"judge score {score} outside {SCORE_MIN}-{SCORE_MAX}"

    reason = payload.get("reason") or ""
    return score, str(reason), ""


# --- deterministic answer-level checks --------------------------------------------


def refusal_outcome(question_type: str, answer: str) -> str:
    """Classify one answer against what its question type required.

    Four outcomes, kept apart because they are four different failures:
    `correct_refusal` and `answered` are right; `hallucinated` is an answer to a question the
    corpus cannot support, the worst outcome this project has; `over_refusal` is a refusal on
    an answerable question, which is safe but useless.
    """
    refused = is_refusal(answer)
    if question_type == "unanswerable":
        return "correct_refusal" if refused else "hallucinated"
    return "over_refusal" if refused else "answered"


def citation_stats(results: Sequence[RAGAnswer]) -> dict[str, Any]:
    """How well the answers cited, without asking a model.

    `unsupported_citations` counts citations naming a file/page that was not in the answer's own
    context — a fabricated source, and the failure most likely to be believed by a reader.
    Refusals are excluded from the denominator: a refusal is supposed to have no citations.
    """
    answered = [r for r in results if not r.refused]
    if not answered:
        return {
            "answers_considered": 0,
            "answers_with_citation": 0,
            "citation_rate": None,
            "unsupported_citations": 0,
            "answers_with_unsupported_citation": 0,
        }

    with_citation = [r for r in answered if r.citations]
    unsupported = [c for r in answered for c in r.citations if not c.supported]
    return {
        "answers_considered": len(answered),
        "answers_with_citation": len(with_citation),
        "citation_rate": round(len(with_citation) / len(answered), 4),
        "unsupported_citations": len(unsupported),
        "answers_with_unsupported_citation": sum(
            1 for r in answered if any(not c.supported for c in r.citations)
        ),
    }


def aggregate(
    faithfulness: Sequence[JudgeScore],
    relevance: Sequence[JudgeScore],
    outcomes: Sequence[str],
) -> dict[str, Any]:
    """Means over the judgements that succeeded, plus the deterministic refusal counts."""
    counts = {
        outcome: sum(1 for o in outcomes if o == outcome)
        for outcome in ("answered", "correct_refusal", "hallucinated", "over_refusal")
    }
    unanswerable_total = counts["correct_refusal"] + counts["hallucinated"]
    answerable_total = counts["answered"] + counts["over_refusal"]

    return {
        "faithfulness": _mean_block(faithfulness),
        "answer_relevance": _mean_block(relevance),
        # Deterministic. The one number here that is not a model's opinion.
        "refusal_accuracy": (
            round(counts["correct_refusal"] / unanswerable_total, 4) if unanswerable_total else None
        ),
        "over_refusal_rate": (
            round(counts["over_refusal"] / answerable_total, 4) if answerable_total else None
        ),
        "outcomes": counts,
        "judge_failures": sum(1 for s in [*faithfulness, *relevance] if s.score is None),
    }


def _mean_block(scores: Sequence[JudgeScore]) -> dict[str, Any]:
    """Mean plus how many judgements it is made of — a mean over 3 of 29 is not a score."""
    present = [s.score for s in scores if s.score is not None]
    return {
        "mean": round(sum(present) / len(present), 4) if present else None,
        "scored": len(present),
        "failed": len(scores) - len(present),
    }
