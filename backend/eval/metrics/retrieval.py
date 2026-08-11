"""recall@k, MRR, nDCG@k over a ranked list of chunk ids. No model, no network, no randomness.

These are the only numbers in the project that are fully reproducible: same corpus, same
question, same retriever ⇒ same value, forever. Everything in `generation.py` is a model's
opinion. When the two disagree about whether a pipeline improved, this file is the one to trust.

Three decisions that change what the numbers mean, made here once and written into every
results file rather than left to the reader:

* **Relevance is binary.** The golden set says a chunk is relevant or it does not mention it.
  There are no graded judgements to feed nDCG, so gains are 1 and 0 — which makes nDCG@k here
  a position-weighted recall rather than the ranking-quality measure it is with graded labels.
* **`unanswerable` questions are excluded**, not scored as 0 and not as 1. Their relevant set
  is empty by definition, so recall has no denominator. Including them either way would move
  the retrieval score without any retrieval having got better or worse. They are measured by
  `refusal_accuracy` instead, and the excluded count is reported next to the metric.
* **A duplicate chunk id in the ranking is a bug, not a boost.** Ranks are deduplicated before
  scoring, so a retriever returning the same chunk twice cannot inflate recall.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RetrievalScores:
    """Per-question retrieval scores. All None when the question has no relevant chunks."""

    recall_at_k: float | None
    mrr: float | None
    ndcg_at_k: float | None
    k: int
    hit_count: int = 0
    relevant_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            f"recall@{self.k}": _round(self.recall_at_k),
            "mrr": _round(self.mrr),
            f"ndcg@{self.k}": _round(self.ndcg_at_k),
            "hit_count": self.hit_count,
            "relevant_count": self.relevant_count,
        }

    @property
    def scored(self) -> bool:
        """False for `unanswerable` questions, which have nothing to be recalled."""
        return self.recall_at_k is not None


def _dedupe(ranking: Sequence[int]) -> list[int]:
    """Keep the first occurrence of each chunk id, preserving rank order."""
    seen: set[int] = set()
    ordered: list[int] = []
    for chunk_id in ranking:
        if chunk_id not in seen:
            seen.add(chunk_id)
            ordered.append(chunk_id)
    return ordered


def recall_at_k(ranking: Sequence[int], relevant: Iterable[int], k: int) -> float:
    """Fraction of the relevant chunks that appear in the top k."""
    relevant_set = set(relevant)
    if not relevant_set:
        raise ValueError("recall is undefined with no relevant chunks")
    top = set(_dedupe(ranking)[:k])
    return len(top & relevant_set) / len(relevant_set)


def mrr(ranking: Sequence[int], relevant: Iterable[int], k: int | None = None) -> float:
    """Reciprocal rank of the first relevant chunk; 0.0 when none is retrieved.

    Cut off at k like the other two: an MRR computed over an uncut ranking would reward a hit
    at position 40 that the answer prompt never sees.
    """
    relevant_set = set(relevant)
    if not relevant_set:
        raise ValueError("MRR is undefined with no relevant chunks")
    ordered = _dedupe(ranking)[:k] if k else _dedupe(ranking)
    for position, chunk_id in enumerate(ordered, start=1):
        if chunk_id in relevant_set:
            return 1.0 / position
    return 0.0


def ndcg_at_k(ranking: Sequence[int], relevant: Iterable[int], k: int) -> float:
    """Binary-gain nDCG@k: DCG of the actual ranking over the DCG of the best possible one."""
    relevant_set = set(relevant)
    if not relevant_set:
        raise ValueError("nDCG is undefined with no relevant chunks")
    top = _dedupe(ranking)[:k]

    dcg = sum(
        1.0 / math.log2(position + 1) for position, i in enumerate(top, 1) if i in relevant_set
    )
    ideal = sum(
        1.0 / math.log2(position + 1) for position in range(1, min(len(relevant_set), k) + 1)
    )
    return dcg / ideal if ideal else 0.0


def score_question(ranking: Sequence[int], relevant: Sequence[int], k: int) -> RetrievalScores:
    """All three metrics for one question, or an unscored result if it has no relevant chunks."""
    if not relevant:
        return RetrievalScores(
            recall_at_k=None, mrr=None, ndcg_at_k=None, k=k, relevant_count=0, hit_count=0
        )
    top = set(_dedupe(ranking)[:k])
    return RetrievalScores(
        recall_at_k=recall_at_k(ranking, relevant, k),
        mrr=mrr(ranking, relevant, k),
        ndcg_at_k=ndcg_at_k(ranking, relevant, k),
        k=k,
        hit_count=len(top & set(relevant)),
        relevant_count=len(set(relevant)),
    )


def aggregate(scores: Sequence[RetrievalScores], k: int) -> dict[str, Any]:
    """Mean of each metric over the scored questions, with the excluded count kept visible."""
    scored = [s for s in scores if s.scored]
    if not scored:
        return {
            f"recall@{k}": None,
            "mrr": None,
            f"ndcg@{k}": None,
            "questions_scored": 0,
            "questions_excluded": len(scores),
        }
    return {
        f"recall@{k}": _round(_mean(s.recall_at_k for s in scored)),
        "mrr": _round(_mean(s.mrr for s in scored)),
        f"ndcg@{k}": _round(_mean(s.ndcg_at_k for s in scored)),
        "questions_scored": len(scored),
        # Not a footnote: these are the unanswerable questions, and a reader who assumes the
        # retrieval metric covers the whole dataset is reading a different number.
        "questions_excluded": len(scores) - len(scored),
    }


def _mean(values: Iterable[float | None]) -> float:
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else 0.0


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 4)
