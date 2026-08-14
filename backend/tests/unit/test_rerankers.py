"""Rerank adapters and the two-stage retriever. No DB, no network.

The provider call itself is stubbed — what is tested here is everything *around* it, which is
where a silent bug would be expensive. A reranker that mis-maps an index attaches a citation to
the wrong document while looking completely normal in a results file, and that is the failure
this project can least afford (ADR-0006 on why an unsupported citation is the metric that
matters). The response-shape parsing is tested against both shapes real providers return.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest

from app.core.config import Settings
from app.llm.rag.rerankers.base import RerankFailed
from app.llm.rag.rerankers.providers import (
    JinaReranker,
    LiteLLMReranker,
    _parse_jina,
    _parse_litellm,
    _reorder,
    get_reranker,
)
from app.llm.rag.retrievers.base import RetrievedChunk
from app.llm.rag.retrievers.reranker import RerankingRetriever


def chunk(chunk_id: int, rank: int, *, retriever: str = "dense") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=1,
        filename=f"{chunk_id:02d}_chinh_sach.pdf",
        page_no=rank,
        chunk_index=chunk_id,
        content=f"nội dung {chunk_id}",
        score=1.0 / rank,
        rank=rank,
        retriever=retriever,
    )


def candidates(ids: list[int]) -> list[RetrievedChunk]:
    return [chunk(cid, rank) for rank, cid in enumerate(ids, start=1)]


class StubReranker:
    """Returns a fixed permutation of the candidate list, by position."""

    model = "voyage/rerank-2.5-lite"

    def __init__(self, order: list[int]) -> None:
        self.order = order
        self.seen: list[tuple[str, int]] = []

    async def rerank(
        self, question: str, chunks: Sequence[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]:
        self.seen.append((question, len(chunks)))
        scored = [(i, 1.0 - n / 100) for n, i in enumerate(self.order)]
        return _reorder(chunks, scored, model=self.model, top_n=top_n)


class StubBase:
    name = "dense"

    def __init__(self, hits: list[RetrievedChunk]) -> None:
        self.hits = hits
        self.asked_for: list[int] = []

    async def retrieve(self, question: str, k: int) -> list[RetrievedChunk]:
        self.asked_for.append(k)
        return self.hits[:k]


class TestReorder:
    def test_reorders_by_provider_index_not_by_original_rank(self) -> None:
        chunks = candidates([10, 20, 30])
        out = _reorder(chunks, [(2, 0.9), (0, 0.5)], model="voyage/rerank-2.5-lite", top_n=5)
        assert [c.chunk_id for c in out] == [30, 10]

    def test_ranks_are_renumbered_from_one(self) -> None:
        chunks = candidates([10, 20, 30])
        out = _reorder(chunks, [(2, 0.9), (1, 0.5), (0, 0.1)], model="m", top_n=5)
        assert [c.rank for c in out] == [1, 2, 3]

    def test_score_becomes_the_provider_relevance_score(self) -> None:
        chunks = candidates([10, 20])
        out = _reorder(chunks, [(1, 0.87)], model="m", top_n=5)
        assert out[0].score == pytest.approx(0.87)

    def test_retriever_records_both_stages(self) -> None:
        # A results file must say the ordering came from dense *then* a reranker, not just
        # name the last step — otherwise the candidate source is unrecoverable.
        out = _reorder(candidates([10]), [(0, 0.9)], model="voyage/rerank-2.5-lite", top_n=5)
        assert out[0].retriever == "dense>rerank-2.5-lite"

    def test_content_and_ids_are_never_rewritten(self) -> None:
        # The reranker reorders; it must not become a way for provider text to reach a citation.
        chunks = candidates([10, 20])
        out = _reorder(chunks, [(1, 0.9), (0, 0.1)], model="m", top_n=5)
        assert [(c.chunk_id, c.content, c.filename) for c in out] == [
            (20, "nội dung 20", "20_chinh_sach.pdf"),
            (10, "nội dung 10", "10_chinh_sach.pdf"),
        ]

    def test_truncates_to_top_n(self) -> None:
        out = _reorder(candidates([1, 2, 3, 4]), [(i, 0.5) for i in range(4)], model="m", top_n=2)
        assert len(out) == 2

    def test_out_of_range_index_raises_rather_than_mis_citing(self) -> None:
        # The important one. Trusting this index would cite the wrong document confidently.
        with pytest.raises(RerankFailed, match="index 9"):
            _reorder(candidates([10, 20]), [(9, 0.9)], model="m", top_n=5)

    def test_negative_index_raises(self) -> None:
        with pytest.raises(RerankFailed, match="index -1"):
            _reorder(candidates([10, 20]), [(-1, 0.9)], model="m", top_n=5)

    def test_duplicate_indices_are_dropped_not_repeated(self) -> None:
        out = _reorder(candidates([10, 20]), [(0, 0.9), (0, 0.8), (1, 0.7)], model="m", top_n=5)
        assert [c.chunk_id for c in out] == [10, 20]


class TestParsing:
    def test_litellm_object_shape(self) -> None:
        class Item:
            def __init__(self, index: int, score: float) -> None:
                self.index, self.relevance_score = index, score

        class Response:
            results = [Item(2, 0.9), Item(0, 0.4)]

        assert _parse_litellm(Response(), "m") == [(2, 0.9), (0, 0.4)]

    def test_litellm_dict_shape(self) -> None:
        response = {"results": [{"index": 1, "relevance_score": 0.7}]}
        assert _parse_litellm(response, "m") == [(1, 0.7)]

    def test_litellm_empty_results_raise(self) -> None:
        with pytest.raises(RerankFailed, match="no rerank results"):
            _parse_litellm({"results": []}, "m")

    def test_litellm_missing_index_raises(self) -> None:
        with pytest.raises(RerankFailed, match="no index"):
            _parse_litellm({"results": [{"relevance_score": 0.5}]}, "m")

    def test_jina_shape(self) -> None:
        payload = {"results": [{"index": 3, "relevance_score": 0.95}]}
        assert _parse_jina(payload, "m") == [(3, 0.95)]

    def test_jina_missing_score_defaults_to_zero_rather_than_crashing(self) -> None:
        assert _parse_jina({"results": [{"index": 0}]}, "m") == [(0, 0.0)]


class TestRerankingRetriever:
    @pytest.mark.asyncio
    async def test_asks_the_base_retriever_for_more_than_k(self) -> None:
        # The whole point: reranking 5 candidates has almost nothing to reorder.
        base = StubBase(candidates(list(range(1, 21))))
        retriever = RerankingRetriever(base, StubReranker(list(range(20))), fetch_multiplier=4)
        await retriever.retrieve("câu hỏi", 5)
        assert base.asked_for == [20]

    @pytest.mark.asyncio
    async def test_returns_exactly_k_after_reranking(self) -> None:
        base = StubBase(candidates(list(range(1, 21))))
        retriever = RerankingRetriever(base, StubReranker(list(range(20))), fetch_multiplier=4)
        assert len(await retriever.retrieve("câu hỏi", 5)) == 5

    @pytest.mark.asyncio
    async def test_a_chunk_the_base_ranked_below_k_can_be_promoted_into_the_answer(self) -> None:
        # The mechanism this experiment exists to test: chunk 12 is 12th by dense and would
        # never reach the prompt under naive-v1. Reranking is what can rescue it.
        base = StubBase(candidates(list(range(1, 21))))
        reranker = StubReranker([11, 0, 1, 2, 3])
        retriever = RerankingRetriever(base, reranker, fetch_multiplier=4)
        out = await retriever.retrieve("câu hỏi", 5)
        assert out[0].chunk_id == 12

    @pytest.mark.asyncio
    async def test_empty_base_result_short_circuits_without_calling_the_provider(self) -> None:
        reranker = StubReranker([0])
        retriever = RerankingRetriever(StubBase([]), reranker)
        assert await retriever.retrieve("câu hỏi", 5) == []
        assert reranker.seen == []

    @pytest.mark.asyncio
    async def test_a_failing_reranker_propagates_rather_than_falling_back_to_dense(self) -> None:
        # A silent fallback would write dense-ordered results into a file labelled `rerank` —
        # the same mislabelling bug Phase 6 already found once in eval/runner.py.
        class Failing:
            model = "voyage/rerank-2.5-lite"

            async def rerank(self, question: str, chunks: Any, top_n: int) -> Any:
                raise RerankFailed("provider is down")

        retriever = RerankingRetriever(StubBase(candidates([1, 2, 3])), Failing())
        with pytest.raises(RerankFailed):
            await retriever.retrieve("câu hỏi", 5)

    @pytest.mark.asyncio
    async def test_k_below_one_raises(self) -> None:
        retriever = RerankingRetriever(StubBase(candidates([1])), StubReranker([0]))
        with pytest.raises(RerankFailed, match="top_k"):
            await retriever.retrieve("câu hỏi", 0)


class TestProviderSelection:
    def test_voyage_is_the_default_and_routes_through_litellm(self) -> None:
        settings = Settings(rerank_provider="VOYAGE", rerank_api_key="k")
        reranker = get_reranker(settings)
        assert isinstance(reranker, LiteLLMReranker)
        assert reranker.model == "voyage/rerank-2.5-lite"

    def test_jina_routes_to_the_direct_http_adapter(self) -> None:
        settings = Settings(
            rerank_provider="JINA",
            rerank_model_name="jina-reranker-v2-base-multilingual",
            rerank_api_key="k",
        )
        reranker = get_reranker(settings)
        assert isinstance(reranker, JinaReranker)
        assert reranker.model == "jina/jina-reranker-v2-base-multilingual"

    def test_jina_without_a_key_fails_at_construction_not_mid_eval(self) -> None:
        settings = Settings(rerank_provider="JINA", rerank_api_key="")
        with pytest.raises(RerankFailed, match="RERANK_API_KEY"):
            get_reranker(settings)

    def test_an_unknown_provider_names_the_valid_ones(self) -> None:
        settings = Settings(rerank_provider="NOPE", rerank_api_key="k")
        with pytest.raises(RerankFailed, match="voyage, jina"):
            get_reranker(settings)

    def test_provider_is_case_insensitive(self) -> None:
        assert isinstance(get_reranker(Settings(rerank_provider="voyage")), LiteLLMReranker)


class TestPackageImports:
    def test_the_two_packages_import_in_either_order(self) -> None:
        """`rerankers` and `retrievers` import each other and once formed a cycle.

        The rest of this file imports submodules directly, which is exactly the path that does
        *not* trigger it — the cycle only closed when `retrievers/__init__` ran first and pulled
        in `reranker.py`. Importing both packages here is what catches a regression before it
        surfaces as an ImportError at `make api` or at the first question of an eval run.
        """
        import importlib

        for name in (
            "app.llm.rag.rerankers",
            "app.llm.rag.retrievers",
            "app.llm.rag.pipelines",
        ):
            assert importlib.import_module(name) is not None


class TestPipelineConfigRecordsTheReranker:
    def test_a_non_reranking_pipeline_records_none(self) -> None:
        # Adding the field must not change what the two frozen pipelines report.
        config = Settings().pipeline_config(retriever="dense")
        assert config.reranker is None
        assert config.rerank_top_n is None

    def test_a_reranking_pipeline_records_the_model_and_the_width(self) -> None:
        config = Settings().pipeline_config(
            retriever="dense>rerank", reranker="voyage/rerank-2.5-lite", rerank_top_n=20
        )
        assert config.to_dict()["reranker"] == "voyage/rerank-2.5-lite"
        assert config.to_dict()["rerank_top_n"] == 20
