"""Chunking is the one Phase 2 component whose bugs are invisible downstream.

A chunk cut mid-word still embeds, still retrieves, still gets cited — it just quietly answers
worse. These tests are the only thing standing between that and the corpus. No DB, no network.
"""

from __future__ import annotations

import pytest

from app.core.config import PipelineConfig
from app.llm.rag.chunking import TextChunk, chunk
from app.llm.rag.loaders import Page

# Real Vietnamese HR prose, the same shape as the corpus: hard-wrapped lines, numbered clauses,
# full diacritics. Written out rather than loaded so the unit suite touches no files.
VIETNAMESE = (
    "1. GIỚI THIỆU\n"
    "Vector là công ty phát triển phần mềm thành lập năm 2015, hiện có 640 nhân sự tại ba\n"
    "văn phòng Hà Nội, Đà Nẵng và Thành phố Hồ Chí Minh. Sổ tay này tóm tắt các chính\n"
    "sách nhân sự chính.\n"
    "2. NGHỈ PHÉP\n"
    "2.1. Nhân viên chính thức được hưởng 12 ngày phép năm, cộng thêm 01 ngày cho mỗi 05\n"
    "năm làm việc liên tục tại công ty.\n"
    "2.2. Ngày phép chưa dùng được chuyển sang quý I của năm kế tiếp, tối đa 05 ngày.\n"
)


def _cfg(size: int = 800, overlap: int = 100) -> PipelineConfig:
    return PipelineConfig(
        chunk_size=size,
        chunk_overlap=overlap,
        top_k=5,
        retriever="dense",
        embedding_model="gemini/gemini-embedding-001",
        embedding_dimensions=768,
        llm_model="gemini/gemini-3.6-flash",
        prompt_version="v1",
    )


def _pages(*texts: str) -> list[Page]:
    return [Page(page_no=i + 1, text=text) for i, text in enumerate(texts)]


# --- shorter than the window ------------------------------------------------------


def test_text_shorter_than_chunk_size_is_one_chunk() -> None:
    chunks = chunk(_pages("Ngắn hơn một chunk."), _cfg())

    assert len(chunks) == 1
    assert chunks[0].content == "Ngắn hơn một chunk."
    assert chunks[0].chunk_index == 0


def test_empty_and_whitespace_pages_produce_nothing() -> None:
    """A blank page in a PDF must not become a chunk — it would embed to noise."""
    assert chunk(_pages("", "   \n\n  \t "), _cfg()) == []


# --- page numbers -----------------------------------------------------------------


def test_page_no_is_preserved_per_page() -> None:
    """The whole citation feature rests on this."""
    chunks = chunk(_pages(VIETNAMESE, VIETNAMESE), _cfg(size=200, overlap=40))

    assert {c.page_no for c in chunks} == {1, 2}
    # Identical pages chunk identically, and pages are processed in order.
    page_numbers = [c.page_no for c in chunks]
    assert page_numbers == sorted(page_numbers)  # type: ignore[type-var]
    assert page_numbers.count(1) == page_numbers.count(2)


def test_a_chunk_never_spans_a_page_break() -> None:
    """Page A's tail and page B's head must not end up in the same chunk."""
    chunks = chunk(_pages("A" * 50, "B" * 50), _cfg())

    assert len(chunks) == 2
    assert chunks[0].content == "A" * 50
    assert chunks[1].content == "B" * 50


def test_docx_style_pages_carry_a_null_page_no() -> None:
    chunks = chunk([Page(page_no=None, text=VIETNAMESE)], _cfg(size=200, overlap=40))

    assert chunks
    assert all(c.page_no is None for c in chunks)


# --- indices ----------------------------------------------------------------------


def test_chunk_index_is_document_wide_and_gapless() -> None:
    """chunk_index is half of the unique key (document_id, chunk_index)."""
    chunks = chunk(_pages(VIETNAMESE, VIETNAMESE, VIETNAMESE), _cfg(size=150, overlap=30))

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


# --- overlap ----------------------------------------------------------------------


def test_consecutive_chunks_overlap() -> None:
    """Overlap is what keeps a fact that straddles a boundary retrievable from either side."""
    size, overlap = 200, 60
    chunks = chunk(_pages(VIETNAMESE), _cfg(size=size, overlap=overlap))

    assert len(chunks) > 1
    for previous, current in zip(chunks, chunks[1:], strict=False):
        head = current.content[:20]
        assert head in previous.content, (
            f"chunk {current.chunk_index} does not overlap its predecessor"
        )


def test_overlap_is_bounded_by_the_configured_amount() -> None:
    """Boundary snapping may widen the overlap a little; it must not run away.

    Unbounded overlap would mean near-duplicate chunks competing with each other in retrieval.
    """
    size, overlap = 200, 60
    chunks = chunk(_pages(VIETNAMESE), _cfg(size=size, overlap=overlap))

    for previous, current in zip(chunks, chunks[1:], strict=False):
        shared = _shared_suffix_prefix(previous.content, current.content)
        assert shared <= overlap * 2, f"overlap of {shared} chars for a configured {overlap}"


def test_windows_advance_on_pathological_input() -> None:
    """One unbroken token far longer than the window must still terminate."""
    chunks = chunk(_pages("x" * 1000), _cfg(size=100, overlap=20))

    assert len(chunks) > 1
    assert "".join(c.content for c in chunks).count("x") >= 1000


# --- word integrity ---------------------------------------------------------------


def test_no_chunk_cuts_a_word_in_half() -> None:
    """The Definition of Done asks a human to check exactly this. Check it here first."""
    size, overlap = 200, 60
    chunks = chunk(_pages(VIETNAMESE), _cfg(size=size, overlap=overlap))
    words = set(VIETNAMESE.split())

    for piece in chunks:
        for word in piece.content.split():
            assert word in words, f"{word!r} is not a whole word from the source"


def test_diacritics_survive_intact() -> None:
    """Chunking is pure slicing — nothing may normalize or strip a Vietnamese tone mark."""
    chunks = chunk(_pages(VIETNAMESE), _cfg(size=150, overlap=30))
    rejoined = "".join(c.content for c in chunks)

    for marker in ("NGHỈ PHÉP", "Đà Nẵng", "GIỚI THIỆU", "liên tục", "ngày phép năm"):
        assert marker.replace(" ", "") in rejoined.replace(" ", "").replace("\n", "")


def test_every_chunk_is_stripped_and_non_empty() -> None:
    chunks = chunk(_pages(VIETNAMESE), _cfg(size=150, overlap=30))

    assert all(c.content == c.content.strip() and c.content for c in chunks)


# --- coverage ---------------------------------------------------------------------


def test_no_content_is_dropped_between_chunks() -> None:
    """Reassembling the chunks in order must recover the source, overlap aside.

    A gap here means a fact in the corpus that no question can ever retrieve.
    """
    source = VIETNAMESE.strip()
    chunks = chunk(_pages(source), _cfg(size=200, overlap=60))

    reassembled = chunks[0].content
    for current in chunks[1:]:
        shared = _shared_suffix_prefix(reassembled, current.content)
        reassembled += current.content[shared:]

    assert _squash(reassembled) == _squash(source)


# --- configuration ----------------------------------------------------------------


def test_overlap_at_least_the_chunk_size_is_rejected() -> None:
    """It would mean a window that never advances — a hang, not a bad result."""
    with pytest.raises(ValueError, match="must be smaller than"):
        chunk(_pages(VIETNAMESE), _cfg(size=100, overlap=100))


def test_token_count_starts_unset() -> None:
    """Chunking does not know which tokenizer; the ingest service fills this from the embedder."""
    chunks = chunk(_pages(VIETNAMESE), _cfg())

    assert all(isinstance(c, TextChunk) and c.token_count is None for c in chunks)


# --- helpers ----------------------------------------------------------------------


def _shared_suffix_prefix(left: str, right: str) -> int:
    """Longest suffix of `left` that is also a prefix of `right`."""
    for length in range(min(len(left), len(right)), 0, -1):
        if left.endswith(right[:length]):
            return length
    return 0


def _squash(text: str) -> str:
    """Compare content while ignoring the whitespace that stripping chunk edges rearranges."""
    return "".join(text.split())
