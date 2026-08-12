"""The API contract: RAGAnswer -> ChatResponse, and the input validation on ChatRequest.

Pure projection tests — no database, no network (CLAUDE.md 6). What they pin down is that the
schema is a *view* of RAGAnswer and never invents or loses a field, especially `supported`.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import PipelineConfig
from app.llm.rag.pipelines.base import REFUSAL_MARKER, Citation, RAGAnswer
from app.llm.rag.retrievers.base import RetrievedChunk
from app.schemas.chat import MAX_QUESTION_CHARS, SNIPPET_CHARS, ChatRequest, ChatResponse

CONFIG = PipelineConfig(
    chunk_size=800,
    chunk_overlap=100,
    top_k=5,
    retriever="dense",
    embedding_model="openai/text-embedding-3-large",
    embedding_dimensions=768,
    llm_model="openai/gpt-5.6-luna",
    temperature=None,
    prompt_version="v1",
)


def chunk(
    chunk_id: int, *, filename: str = "so-tay.pdf", page_no: int = 3, content: str = "x"
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=1,
        filename=filename,
        page_no=page_no,
        chunk_index=chunk_id,
        content=content,
        score=0.9,
        rank=1,
        retriever="dense",
    )


def answer_with(
    *, answer: str, citations: list[Citation], retrieved: list[RetrievedChunk]
) -> RAGAnswer:
    return RAGAnswer(
        question="Nghỉ phép năm bao nhiêu ngày?",
        answer=answer,
        citations=citations,
        chunk_ids=[c.chunk_id for c in retrieved],
        pipeline_name="naive-v1",
        config=CONFIG,
        latency_ms=1234,
        retrieved=retrieved,
    )


def test_from_answer_carries_the_snippet_of_the_cited_chunk() -> None:
    retrieved = [chunk(42, content="Nhân viên được nghỉ 12 ngày phép mỗi năm.")]
    response = ChatResponse.from_answer(
        answer_with(
            answer="12 ngày [so-tay.pdf, p.3]",
            citations=[Citation(filename="so-tay.pdf", page_no=3, chunk_id=42, supported=True)],
            retrieved=retrieved,
        ),
        query_id=7,
    )

    assert response.query_id == 7
    assert response.refused is False
    assert response.chunk_ids == [42]
    (citation,) = response.citations
    assert citation.chunk_id == 42
    assert citation.supported is True
    assert citation.snippet == "Nhân viên được nghỉ 12 ngày phép mỗi năm."


def test_unsupported_citation_survives_the_projection() -> None:
    """A fabricated citation must reach the client labelled, never silently dropped."""
    response = ChatResponse.from_answer(
        answer_with(
            answer="… [khong-ton-tai.pdf, p.9]",
            citations=[
                Citation(filename="khong-ton-tai.pdf", page_no=9, chunk_id=None, supported=False)
            ],
            retrieved=[chunk(42)],
        )
    )

    (citation,) = response.citations
    assert citation.supported is False
    assert citation.chunk_id is None
    assert citation.snippet is None


def test_refusal_is_reported_as_refused() -> None:
    response = ChatResponse.from_answer(
        answer_with(answer=REFUSAL_MARKER, citations=[], retrieved=[])
    )
    assert response.refused is True
    assert response.citations == []


def test_snippet_is_truncated_and_whitespace_collapsed() -> None:
    long = "từ " * 400
    response = ChatResponse.from_answer(
        answer_with(
            answer="… [so-tay.pdf, p.3]",
            citations=[Citation(filename="so-tay.pdf", page_no=3, chunk_id=1, supported=True)],
            retrieved=[chunk(1, content=f"  a\n\nb  {long}")],
        )
    )
    snippet = response.citations[0].snippet
    assert snippet is not None
    assert snippet.startswith("a b từ")
    assert len(snippet) <= SNIPPET_CHARS + 1  # the ellipsis
    assert snippet.endswith("…")


def test_query_id_is_optional_so_a_failed_write_still_returns_the_answer() -> None:
    response = ChatResponse.from_answer(answer_with(answer="ok", citations=[], retrieved=[]))
    assert response.query_id is None
    assert response.answer == "ok"


@pytest.mark.parametrize("question", ["", "x" * (MAX_QUESTION_CHARS + 1)])
def test_chat_request_rejects_empty_and_oversized_questions(question: str) -> None:
    with pytest.raises(ValidationError):
        ChatRequest(question=question)


def test_chat_request_accepts_a_normal_vietnamese_question() -> None:
    assert ChatRequest(question="Phụ cấp ăn trưa là bao nhiêu?").question
