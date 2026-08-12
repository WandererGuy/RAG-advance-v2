"""RRF fusion and keyword query building. No DB, no network.

These are the two pieces of Phase 6 that are pure functions, and they are where a silent bug
would be most expensive: a fusion that mis-ranks produces a plausible-looking results file, and
a tokenizer that drops the wrong word produces a keyword half that quietly contributes nothing.
The database-facing half of `bm25` is covered by `tests/integration/test_retrieval.py`.
"""

from __future__ import annotations

import pytest

from app.llm.rag.retrievers.base import RetrievedChunk
from app.llm.rag.retrievers.bm25 import VIETNAMESE_STOPWORDS, build_tsquery, tokenize
from app.llm.rag.retrievers.hybrid import (
    RRF_K,
    HybridRetrievalFailed,
    HybridRetriever,
    reciprocal_rank_fusion,
)


def chunk(chunk_id: int, rank: int, *, retriever: str = "dense") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=1,
        filename="08_cong_tac_phi.pdf",
        page_no=1,
        chunk_index=chunk_id,
        content=f"nội dung {chunk_id}",
        score=1.0 / rank,
        rank=rank,
        retriever=retriever,
    )


def ranking(ids: list[int], *, retriever: str) -> list[RetrievedChunk]:
    return [chunk(cid, rank, retriever=retriever) for rank, cid in enumerate(ids, start=1)]


class TestReciprocalRankFusion:
    def test_score_is_the_sum_of_reciprocal_ranks(self) -> None:
        fused = reciprocal_rank_fusion([ranking([7], retriever="dense")])
        assert fused[0].score == pytest.approx(1.0 / (RRF_K + 1))

    def test_agreement_between_retrievers_outranks_a_single_first_place(self) -> None:
        # The entire point of RRF. Chunk 5 is 2nd on both lists and beats chunk 1 and chunk 9,
        # each of which is 1st on one list and absent from the other:
        #   5 -> 1/62 + 1/62 = 0.03226
        #   1 -> 1/61        = 0.01639
        dense = ranking([1, 5, 3], retriever="dense")
        keyword = ranking([9, 5, 4], retriever="bm25")
        fused = reciprocal_rank_fusion([dense, keyword])
        assert fused[0].chunk_id == 5
        assert fused[0].score == pytest.approx(2.0 / (RRF_K + 2))

    def test_records_which_retrievers_found_each_chunk(self) -> None:
        # This is the diagnostic that answers "is the keyword half contributing at all?".
        fused = reciprocal_rank_fusion(
            [ranking([1, 5], retriever="dense"), ranking([5, 9], retriever="bm25")]
        )
        by_id = {c.chunk_id: c.retriever for c in fused}
        assert by_id[5] == "dense+bm25"
        assert by_id[1] == "dense"
        assert by_id[9] == "bm25"

    def test_ranks_are_renumbered_from_one_and_contiguous(self) -> None:
        fused = reciprocal_rank_fusion(
            [ranking([1, 2, 3], retriever="dense"), ranking([3, 4], retriever="bm25")]
        )
        assert [c.rank for c in fused] == [1, 2, 3, 4]

    def test_a_chunk_appears_once_however_many_lists_hold_it(self) -> None:
        fused = reciprocal_rank_fusion(
            [ranking([7], retriever="dense"), ranking([7], retriever="bm25")]
        )
        assert len(fused) == 1

    def test_citation_fields_survive_fusion(self) -> None:
        # The fused chunk is what the prompt renders and what a citation resolves against, so
        # losing content or filename here would break the answer, not just the ranking.
        fused = reciprocal_rank_fusion([ranking([7], retriever="dense")])
        assert fused[0].content == "nội dung 7"
        assert fused[0].filename == "08_cong_tac_phi.pdf"
        assert fused[0].page_no == 1

    def test_ties_are_broken_deterministically(self) -> None:
        # Two chunks at identical rank in identical positions: whatever order comes out, it must
        # be the same order every run, or an eval diff would report noise as a result.
        first = reciprocal_rank_fusion([ranking([4, 9], retriever="dense")])
        second = reciprocal_rank_fusion([ranking([4, 9], retriever="dense")])
        assert [c.chunk_id for c in first] == [c.chunk_id for c in second]

    def test_an_empty_ranking_contributes_nothing(self) -> None:
        fused = reciprocal_rank_fusion([ranking([1, 2], retriever="dense"), []])
        assert [c.chunk_id for c in fused] == [1, 2]

    def test_no_rankings_at_all(self) -> None:
        assert reciprocal_rank_fusion([]) == []

    def test_k_must_be_positive(self) -> None:
        with pytest.raises(HybridRetrievalFailed):
            reciprocal_rank_fusion([ranking([1], retriever="dense")], k=0)


class FakeRetriever:
    """Records the k it was asked for, so the fetch-widening can be asserted."""

    def __init__(self, name: str, ids: list[int]) -> None:
        self.name = name
        self._ids = ids
        self.asked_for: int | None = None

    async def retrieve(self, question: str, k: int) -> list[RetrievedChunk]:
        self.asked_for = k
        return ranking(self._ids[:k], retriever=self.name)


class TestHybridRetriever:
    @pytest.mark.asyncio
    async def test_asks_each_half_for_more_than_k(self) -> None:
        # Fusing two top-5 lists and taking 5 would discard the chunk RRF exists to rescue:
        # 6th by dense, 1st by keyword.
        dense = FakeRetriever("dense", list(range(1, 30)))
        keyword = FakeRetriever("bm25", list(range(1, 30)))
        await HybridRetriever(dense, keyword, fetch_multiplier=4).retrieve("phụ cấp", 5)
        assert dense.asked_for == 20
        assert keyword.asked_for == 20

    @pytest.mark.asyncio
    async def test_returns_exactly_k_after_fusing_wider_lists(self) -> None:
        dense = FakeRetriever("dense", list(range(1, 30)))
        keyword = FakeRetriever("bm25", list(range(15, 40)))
        result = await HybridRetriever(dense, keyword).retrieve("phụ cấp", 5)
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_an_empty_keyword_half_falls_through_to_dense(self) -> None:
        # A question made entirely of stopwords is a real case, not an error.
        dense = FakeRetriever("dense", [1, 2, 3])
        result = await HybridRetriever(dense, FakeRetriever("bm25", [])).retrieve("cái đó là gì", 3)
        assert [c.chunk_id for c in result] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_a_raising_half_is_not_swallowed(self) -> None:
        # A dense-only ranking must never be written to a results file labelled `hybrid`.
        class Broken:
            name = "bm25"

            async def retrieve(self, question: str, k: int) -> list[RetrievedChunk]:
                raise RuntimeError("full-text scan failed")

        hybrid = HybridRetriever(FakeRetriever("dense", [1, 2]), Broken())
        with pytest.raises(RuntimeError):
            await hybrid.retrieve("phụ cấp", 2)

    @pytest.mark.asyncio
    async def test_k_must_be_positive(self) -> None:
        hybrid = HybridRetriever(FakeRetriever("dense", [1]), FakeRetriever("bm25", [1]))
        with pytest.raises(HybridRetrievalFailed):
            await hybrid.retrieve("phụ cấp", 0)


class TestKeywordQueryBuilding:
    def test_content_words_survive_with_their_diacritics(self) -> None:
        assert tokenize("Phụ cấp công tác") == ["phụ", "cấp", "công", "tác"]

    def test_stopwords_are_dropped(self) -> None:
        # "bao nhiêu" matches nearly every chunk and flattens the ranking toward noise.
        assert "bao" not in tokenize("Phụ cấp là bao nhiêu?")
        assert "phụ" in tokenize("Phụ cấp là bao nhiêu?")

    def test_words_that_look_like_stopwords_but_carry_meaning_are_kept(self) -> None:
        # `ngày`, `năm`, `phép` and `lương` are the substance of HR questions, and dropping one
        # would make a whole class of question unmatchable — silently.
        for term in ("ngày", "năm", "phép", "lương"):
            assert term not in VIETNAMESE_STOPWORDS
            assert term in tokenize(f"Chính sách {term} thế nào?")

    def test_punctuation_is_not_a_term(self) -> None:
        assert tokenize("phép/năm; phụ-cấp!") == ["phép", "năm", "phụ", "cấp"]

    def test_duplicates_are_dropped_but_order_is_kept(self) -> None:
        assert tokenize("phụ cấp phụ cấp công tác") == ["phụ", "cấp", "công", "tác"]

    def test_tsquery_ors_every_term(self) -> None:
        # AND semantics returns zero rows for a real question — the reason this is OR at all.
        assert build_tsquery("Phụ cấp công tác") == "'phụ' | 'cấp' | 'công' | 'tác'"

    def test_a_question_of_only_stopwords_yields_no_query(self) -> None:
        assert build_tsquery("Cái đó là gì?") == ""

    def test_an_apostrophe_cannot_break_the_query_syntax(self) -> None:
        # `\w+` splits on the apostrophe and the leftover `s` is dropped as too short, so no
        # quote ever reaches the query. Asserted as behaviour rather than as intent: if a later
        # change to the token pattern lets one through, `build_tsquery` doubles it, and this
        # test is where that shows up as a change rather than as a 500.
        assert build_tsquery("nhân's") == "'nhân'"

    def test_a_term_containing_a_quote_would_be_escaped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The escaping in build_tsquery is unreachable through the current tokenizer, so it is
        # exercised by widening the tokenizer — which is exactly the change that would make it
        # reachable for real. Without the doubling this is a tsquery syntax error, i.e. a 500.
        monkeypatch.setattr("app.llm.rag.retrievers.bm25.tokenize", lambda q: ["nhân's"])
        assert build_tsquery("ignored") == "'nhân''s'"
