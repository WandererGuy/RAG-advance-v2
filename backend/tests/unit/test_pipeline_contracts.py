"""The contracts every pipeline and the runner must agree on: refusal, citations, the registry.

These three are what turn an answer into a number. If `is_refusal` drifts from the prompt,
`refusal_accuracy` measures nothing; if `parse_citations` drops an unsupported citation, the
worst failure mode of the system becomes invisible; if the registry lets a name be rebound,
two results files describe two different pipelines under one name. No DB, no network.
"""

from __future__ import annotations

import pytest

from app.core.exceptions import PipelineNotFound
from app.llm.rag.pipelines import registry
from app.llm.rag.pipelines.base import REFUSAL_MARKER, is_refusal, parse_citations
from app.llm.rag.retrievers.base import RetrievedChunk


def chunk(
    chunk_id: int, filename: str = "04_nghi_phep.pdf", page_no: int | None = 2
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=1,
        filename=filename,
        page_no=page_no,
        chunk_index=chunk_id,
        content="Phép năm 12 ngày.",
        score=0.9,
        rank=chunk_id,
        retriever="dense",
    )


class TestRefusalDetection:
    def test_exact_marker(self) -> None:
        assert is_refusal(REFUSAL_MARKER)

    def test_marker_with_a_trailing_sentence(self) -> None:
        # Models add a clarifying line often enough that exact equality would score honest
        # refusals as hallucinations.
        assert is_refusal(f"{REFUSAL_MARKER} Bạn có thể hỏi bộ phận nhân sự.")

    def test_survives_whitespace_and_case(self) -> None:
        assert is_refusal("  không tìm thấy   thông tin trong tài liệu.  ")

    def test_a_real_answer_is_not_a_refusal(self) -> None:
        assert not is_refusal("Phép năm là 12 ngày [04_nghi_phep.pdf, p.2].")

    def test_a_near_miss_is_not_a_refusal(self) -> None:
        # Similar wording, different sentence: the metric must not be satisfied by a paraphrase
        # the prompt never asked for.
        assert not is_refusal("Tôi không chắc tài liệu có thông tin này.")

    def test_empty_answer_is_not_a_refusal(self) -> None:
        assert not is_refusal("")


class TestCitationParsing:
    def test_resolves_to_the_retrieved_chunk(self) -> None:
        citations = parse_citations("12 ngày [04_nghi_phep.pdf, p.2].", [chunk(7)])
        assert [(c.filename, c.page_no, c.chunk_id, c.supported) for c in citations] == [
            ("04_nghi_phep.pdf", 2, 7, True)
        ]

    def test_unsupported_citation_is_kept_and_flagged(self) -> None:
        # The most informative failure the project can record. Dropping it would erase it.
        citations = parse_citations("[08_cong_tac_phi.pdf, p.9]", [chunk(7)])
        assert len(citations) == 1
        assert not citations[0].supported
        assert citations[0].chunk_id is None

    def test_right_file_wrong_page_is_unsupported(self) -> None:
        assert not parse_citations("[04_nghi_phep.pdf, p.11]", [chunk(7)])[0].supported

    def test_duplicates_are_collapsed(self) -> None:
        answer = "[04_nghi_phep.pdf, p.2] và [04_nghi_phep.pdf, p.2]"
        assert len(parse_citations(answer, [chunk(7)])) == 1

    def test_several_citations_in_one_answer(self) -> None:
        chunks = [chunk(7), chunk(8, "02_luong.pdf", 3)]
        answer = "A [04_nghi_phep.pdf, p.2], B [02_luong.pdf, p.3]."
        assert [c.chunk_id for c in parse_citations(answer, chunks)] == [7, 8]

    def test_vietnamese_page_prefix(self) -> None:
        assert parse_citations("[04_nghi_phep.pdf, trang 2]", [chunk(7)])[0].chunk_id == 7

    def test_docx_without_a_page(self) -> None:
        chunks = [chunk(7, "so_tay.docx", None)]
        assert parse_citations("[so_tay.docx, p.?]", chunks)[0].chunk_id == 7

    def test_no_citations(self) -> None:
        assert parse_citations("Phép năm là 12 ngày.", [chunk(7)]) == []

    def test_a_bracket_that_is_not_a_citation(self) -> None:
        assert parse_citations("Điều [3] quy định", [chunk(7)]) == []


class TestRegistry:
    def test_naive_v1_is_registered_by_importing_the_package(self) -> None:
        assert "naive-v1" in registry.available()
        assert registry.get_pipeline("naive-v1").name == "naive-v1"

    def test_unknown_name_lists_what_exists(self) -> None:
        with pytest.raises(PipelineNotFound) as exc:
            registry.get_pipeline("hybrid-v2")
        assert "naive-v1" in str(exc.value)

    def test_a_name_cannot_be_rebound(self) -> None:
        with pytest.raises(ValueError, match="already registered"):

            @registry.register("naive-v1")
            class Impostor:
                name = "naive-v1"

    def test_name_attribute_must_match_the_registered_name(self) -> None:
        # results/<name>.json takes the registry key, RAGAnswer.pipeline_name takes the
        # attribute — a mismatch files one pipeline's answers under another's name.
        with pytest.raises(ValueError, match="registers as"):

            @registry.register("test-mismatch-v1")
            class Mismatched:
                name = "something-else"
