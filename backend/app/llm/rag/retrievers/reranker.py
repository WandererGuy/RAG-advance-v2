"""Two-stage retrieval: a base retriever fetches wide, a cross-encoder reorders, top-k survives.

**Why this is the experiment worth running after hybrid failed.** Phase 4 left `recall@5` at
0.958 — the right chunk is nearly always *found*, so there is no headroom in finding it. The
headroom is in `MRR` (0.840) and `nDCG@5` (0.857): the chunk is present but ranked below
something less useful. A cross-encoder reads the question and the chunk *together* rather than
comparing two independently-computed vectors, which is exactly the ordering problem.

**And it cannot lose a chunk the way RRF did.** ADR-0009's whole recall regression was q021:
the keyword half voted a wrong chunk up and displaced the right one out of the top 5. Reranking
a superset cannot do that — every candidate the base retriever found is still a candidate, so
`recall@fetch_k` is preserved by construction and only the *order* changes. Recall@5 can still
fall if the reranker pushes a relevant chunk below rank 5, but nothing is dropped unseen.

**`fetch_k` is the one knob that matters.** Rerank 5 candidates and there is almost nothing to
reorder; rerank 100 and every question costs a large provider call. 20 is the default here
(4x the pipeline's k, matching `hybrid.py`'s multiplier) and it is a constructor argument so a
later experiment can vary it — as its own pipeline with its own results file, one variable at a
time (CLAUDE.md 5.4).
"""

from __future__ import annotations

from app.llm.rag.rerankers.base import Reranker, RerankFailed
from app.llm.rag.retrievers.base import RetrievedChunk, Retriever

__all__ = ["DEFAULT_FETCH_MULTIPLIER", "RerankingRetriever"]

# How much wider the base retriever searches than the pipeline finally uses. Matches
# hybrid.py's multiplier deliberately: the two Phase 6 retrievers should differ in mechanism,
# not in how much corpus they get to see.
DEFAULT_FETCH_MULTIPLIER = 4


class RerankingRetriever:
    """A base retriever plus a cross-encoder second stage.

    Composes rather than subclasses: the base stage is any `Retriever`, so this works over
    dense, bm25 or hybrid without knowing which. `rerank-v1` wires it over dense, changing
    exactly one variable against `naive-v1`.
    """

    name = "rerank"

    def __init__(
        self,
        base: Retriever,
        reranker: Reranker,
        *,
        fetch_multiplier: int = DEFAULT_FETCH_MULTIPLIER,
    ) -> None:
        self._base = base
        self._reranker = reranker
        self._fetch_multiplier = fetch_multiplier

    async def retrieve(self, question: str, k: int) -> list[RetrievedChunk]:
        """Fetch `k * fetch_multiplier` candidates, rerank them, return the best k.

        A base retriever returning nothing short-circuits: there is nothing to reorder, and a
        rerank call on an empty candidate list is a wasted request. A reranker *raising* is not
        swallowed — a silent fallback to the base ordering would write dense-ordered results
        into a file labelled `rerank`, which is the same mislabelling bug Phase 6 already found
        and fixed once in `eval/runner.py`.
        """
        if k < 1:
            raise RerankFailed(f"top_k must be at least 1, got {k}")

        candidates = await self._base.retrieve(question, k * self._fetch_multiplier)
        if not candidates:
            return []

        return await self._reranker.rerank(question, candidates, k)
