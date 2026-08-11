"""Prompt rendering and judge parsing — the two places a silent default would fake a number.

A prompt rendered with a missing variable still looks like a prompt, and a judge whose output
could not be parsed would, with a default score, look like a mediocre answer. Both must fail
loudly instead. No DB, no network.
"""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.llm.prompts import PROMPTS_DIR, PromptNotFound, render_prompt, render_template
from app.llm.rag.pipelines.base import REFUSAL_MARKER, Citation, RAGAnswer
from app.llm.rag.retrievers.base import RetrievedChunk
from eval.metrics.generation import (
    JUDGE_PROMPTS_DIR,
    JudgeScore,
    aggregate,
    citation_stats,
    parse_judgement,
    refusal_outcome,
)

CHUNKS = [
    RetrievedChunk(
        chunk_id=5,
        document_id=1,
        filename="04_nghi_phep.pdf",
        page_no=2,
        chunk_index=0,
        content="Phép năm 12 ngày, cộng 01 ngày mỗi 03 năm.",
        score=0.81,
        rank=1,
        retriever="dense",
    )
]


def answer_record(text: str, citations: list[Citation] | None = None) -> RAGAnswer:
    return RAGAnswer(
        question="Phép năm bao nhiêu ngày?",
        answer=text,
        citations=citations or [],
        chunk_ids=[5],
        pipeline_name="naive-v1",
        config=get_settings().pipeline_config(retriever="dense"),
        latency_ms=100,
        retrieved=CHUNKS,
    )


class TestAnswerPrompt:
    def test_carries_the_context_the_question_and_the_marker(self) -> None:
        rendered = render_prompt(
            "answer_v1", question="Phép năm?", chunks=CHUNKS, refusal_marker=REFUSAL_MARKER
        )
        assert "Phép năm 12 ngày" in rendered
        assert "04_nghi_phep.pdf, p.2" in rendered
        assert "Phép năm?" in rendered
        # The refusal sentence is injected, never typed in the template — that is what keeps
        # the prompt and is_refusal() from drifting apart.
        assert REFUSAL_MARKER in rendered

    def test_missing_variable_raises_instead_of_rendering_blank(self) -> None:
        with pytest.raises(Exception, match="refusal_marker"):
            render_prompt("answer_v1", question="x", chunks=CHUNKS)

    def test_unknown_prompt_lists_the_known_ones(self) -> None:
        with pytest.raises(PromptNotFound, match="answer_v1"):
            render_prompt("answer_v9")

    def test_page_placeholder_for_a_docx_chunk(self) -> None:
        docx = [
            RetrievedChunk(
                chunk_id=1,
                document_id=1,
                filename="so_tay.docx",
                page_no=None,
                chunk_index=0,
                content="nội dung",
                score=0.5,
                rank=1,
                retriever="dense",
            )
        ]
        rendered = render_prompt(
            "answer_v1", question="x", chunks=docx, refusal_marker=REFUSAL_MARKER
        )
        assert "so_tay.docx, p.?" in rendered

    def test_prompt_versions_are_files_not_edits(self) -> None:
        assert (PROMPTS_DIR / "answer_v1.jinja").exists()


class TestJudgePrompts:
    def test_faithfulness_renders_context_and_answer(self) -> None:
        rendered = render_template(
            JUDGE_PROMPTS_DIR,
            "faithfulness_v1",
            question="Phép năm?",
            answer="12 ngày",
            chunks=CHUNKS,
        )
        assert "Phép năm 12 ngày" in rendered
        assert '"score"' in rendered

    def test_relevance_renders_the_reference_answer(self) -> None:
        rendered = render_template(
            JUDGE_PROMPTS_DIR,
            "relevance_v1",
            question="Phép năm?",
            answer="12 ngày",
            ground_truth="12 ngày/năm",
        )
        assert "12 ngày/năm" in rendered


class TestParseJudgement:
    def test_plain_json(self) -> None:
        assert parse_judgement('{"score": 4, "reason": "ok"}')[:2] == (4, "ok")

    def test_inside_a_markdown_fence(self) -> None:
        assert parse_judgement('```json\n{"score": 5, "reason": "r"}\n```')[0] == 5

    def test_float_score_is_truncated_to_an_int(self) -> None:
        assert parse_judgement('{"score": 4.0, "reason": ""}')[0] == 4

    def test_out_of_range_fails_rather_than_clamping(self) -> None:
        # A clamped 7 would enter the mean as a 5 and quietly raise it.
        score, _, error = parse_judgement('{"score": 7, "reason": ""}')
        assert score is None and "outside" in error

    def test_prose_instead_of_json(self) -> None:
        score, _, error = parse_judgement("I think this answer is quite good.")
        assert score is None and "no JSON" in error

    def test_missing_score_key(self) -> None:
        assert parse_judgement('{"reason": "forgot"}')[0] is None

    def test_boolean_is_not_a_score(self) -> None:
        assert parse_judgement('{"score": true}')[0] is None


class TestRefusalOutcome:
    def test_refusing_an_unanswerable_question_is_correct(self) -> None:
        assert refusal_outcome("unanswerable", REFUSAL_MARKER) == "correct_refusal"

    def test_answering_an_unanswerable_question_is_a_hallucination(self) -> None:
        assert refusal_outcome("unanswerable", "Thưởng thâm niên là 5 triệu.") == "hallucinated"

    def test_answering_a_factual_question(self) -> None:
        assert refusal_outcome("factual", "12 ngày") == "answered"

    def test_refusing_an_answerable_question_is_over_refusal(self) -> None:
        assert refusal_outcome("multi_hop", REFUSAL_MARKER) == "over_refusal"


class TestAggregation:
    def test_failed_judgements_do_not_become_scores(self) -> None:
        block = aggregate([JudgeScore(5), JudgeScore(None, error="boom")], [], ["answered"])
        assert block["faithfulness"] == {"mean": 5.0, "scored": 1, "failed": 1}
        assert block["judge_failures"] == 1

    def test_refusal_accuracy_over_unanswerable_questions_only(self) -> None:
        outcomes = ["correct_refusal", "correct_refusal", "hallucinated", "answered"]
        block = aggregate([], [], outcomes)
        assert block["refusal_accuracy"] == pytest.approx(2 / 3, abs=1e-4)
        assert block["over_refusal_rate"] == 0.0

    def test_no_unanswerable_questions_means_no_refusal_accuracy(self) -> None:
        assert aggregate([], [], ["answered"])["refusal_accuracy"] is None


class TestCitationStats:
    def test_refusals_are_not_counted_against_the_citation_rate(self) -> None:
        stats = citation_stats([answer_record(REFUSAL_MARKER)])
        assert stats["answers_considered"] == 0
        assert stats["citation_rate"] is None

    def test_unsupported_citations_are_counted(self) -> None:
        record = answer_record(
            "12 ngày [x.pdf, p.9]",
            [Citation(filename="x.pdf", page_no=9, chunk_id=None, supported=False)],
        )
        stats = citation_stats([record])
        assert stats["unsupported_citations"] == 1
        assert stats["answers_with_unsupported_citation"] == 1
        assert stats["citation_rate"] == 1.0

    def test_an_answer_with_no_citation_lowers_the_rate(self) -> None:
        stats = citation_stats(
            [
                answer_record("12 ngày"),
                answer_record(
                    "12 ngày", [Citation(filename="04_nghi_phep.pdf", page_no=2, chunk_id=5)]
                ),
            ]
        )
        assert stats["citation_rate"] == 0.5
