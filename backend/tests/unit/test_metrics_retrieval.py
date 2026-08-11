"""The retrieval metrics are the only fully reproducible numbers this project produces.

They are also the ones quoted first, so the cases here are the ones where a plausible-looking
implementation is wrong in a direction that flatters the pipeline: an `unanswerable` question
counted as a perfect score, a duplicate chunk id inflating recall, a hit below the cut-off
still earning MRR. No DB, no network.
"""

from __future__ import annotations

import math

import pytest

from eval.metrics.retrieval import (
    RetrievalScores,
    aggregate,
    mrr,
    ndcg_at_k,
    recall_at_k,
    score_question,
)


class TestRecall:
    def test_all_relevant_retrieved(self) -> None:
        assert recall_at_k([1, 2, 3], [1, 2], 5) == 1.0

    def test_partial(self) -> None:
        assert recall_at_k([1, 9, 8], [1, 2], 5) == 0.5

    def test_ignores_hits_below_the_cutoff(self) -> None:
        # The answer prompt only ever sees the top k; a hit at rank 6 helped nothing.
        assert recall_at_k([9, 8, 7, 6, 5, 1], [1], 5) == 0.0

    def test_duplicate_ids_cannot_inflate(self) -> None:
        # A retriever returning chunk 1 five times has found one relevant chunk, not five.
        assert recall_at_k([1, 1, 1, 1, 1], [1, 2], 5) == 0.5

    def test_undefined_without_relevant_chunks(self) -> None:
        with pytest.raises(ValueError, match="undefined"):
            recall_at_k([1, 2], [], 5)


class TestMRR:
    def test_first_position(self) -> None:
        assert mrr([7, 1, 2], [7], 5) == 1.0

    def test_third_position(self) -> None:
        assert mrr([8, 9, 7], [7], 5) == pytest.approx(1 / 3)

    def test_first_relevant_wins(self) -> None:
        assert mrr([8, 2, 7], [7, 2], 5) == 0.5

    def test_zero_when_nothing_relevant_is_retrieved(self) -> None:
        assert mrr([8, 9], [7], 5) == 0.0

    def test_respects_the_cutoff(self) -> None:
        assert mrr([8, 9, 7], [7], 2) == 0.0


class TestNDCG:
    def test_perfect_ranking_is_one(self) -> None:
        assert ndcg_at_k([1, 2, 3], [1, 2], 5) == pytest.approx(1.0)

    def test_worse_ranking_scores_lower(self) -> None:
        assert ndcg_at_k([9, 1], [1], 5) < ndcg_at_k([1, 9], [1], 5)

    def test_known_value(self) -> None:
        # One relevant chunk at rank 2: DCG = 1/log2(3), IDCG = 1/log2(2) = 1.
        assert ndcg_at_k([9, 1], [1], 5) == pytest.approx(1 / math.log2(3))

    def test_zero_when_nothing_relevant_is_retrieved(self) -> None:
        assert ndcg_at_k([8, 9], [1], 5) == 0.0


class TestScoreQuestion:
    def test_unanswerable_is_unscored_not_zero(self) -> None:
        # The trap this exists for: an unanswerable question scored as 0.0 would drag the mean
        # down, and as 1.0 would inflate it. It has no retrieval score at all.
        scores = score_question([1, 2, 3], [], 5)
        assert not scores.scored
        assert (scores.recall_at_k, scores.mrr, scores.ndcg_at_k) == (None, None, None)
        assert scores.to_dict()["recall@5"] is None

    def test_counts_are_deduplicated(self) -> None:
        scores = score_question([4, 4, 5], [4, 5, 6], 5)
        assert scores.hit_count == 2
        assert scores.relevant_count == 3
        assert scores.recall_at_k == pytest.approx(2 / 3)


class TestAggregate:
    def test_excluded_questions_are_reported_not_hidden(self) -> None:
        scored = score_question([1], [1], 5)
        unscored = score_question([1], [], 5)
        result = aggregate([scored, unscored, unscored], 5)
        assert result["questions_scored"] == 1
        assert result["questions_excluded"] == 2
        assert result["recall@5"] == 1.0

    def test_all_unanswerable_yields_no_metric(self) -> None:
        result = aggregate([score_question([1], [], 5)], 5)
        assert result["recall@5"] is None
        assert result["questions_scored"] == 0

    def test_mean_over_two_questions(self) -> None:
        first = score_question([1, 2], [1, 2], 5)  # recall 1.0
        second = score_question([9, 8], [1, 2], 5)  # recall 0.0
        assert aggregate([first, second], 5)["recall@5"] == 0.5

    def test_empty_input(self) -> None:
        assert aggregate([], 5)["questions_scored"] == 0

    def test_scores_dataclass_is_frozen(self) -> None:
        scores = RetrievalScores(recall_at_k=1.0, mrr=1.0, ndcg_at_k=1.0, k=5)
        with pytest.raises(AttributeError):
            scores.recall_at_k = 0.0  # type: ignore[misc]
