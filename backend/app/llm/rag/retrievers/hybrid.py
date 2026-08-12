"""Hybrid retrieval: dense + keyword, fused by Reciprocal Rank Fusion.

**Why RRF and not a weighted score sum.** A cosine similarity and a `ts_rank_cd` share no scale,
no range and no distribution — cosine over a real corpus clusters in a narrow band near the top
of [0, 1], while `ts_rank_cd` is unbounded and depends on term density. Adding them, even with a
weight, means picking a constant that silently encodes the shape of one particular corpus, and
re-tuning it every time the embedding model changes. RRF reads only the *rank* each retriever
assigned, which is the one thing the two lists genuinely have in common. `RetrievedChunk.score`
is documented as retriever-specific for exactly this reason, and this is the file that would
otherwise be tempted to violate it.

    RRF(chunk) = sum over retrievers of 1 / (K + rank)

**K = 60** is the constant from the original RRF paper (Cormack et al., 2009) and the value
every mainstream implementation uses. It is deliberately not tuned here: tuning it on 29
agent-authored questions over an 8-document corpus would fit the constant to the golden set
rather than to the problem (ADR-0004 on what these numbers can and cannot support). It is a
constructor argument so a later experiment *can* change it — as its own pipeline, with its own
results file, changing exactly one variable (CLAUDE.md 5.4).

**Each retriever is asked for more than k.** Fusing two top-5 lists and taking the top 5 would
throw away the case RRF exists for: a chunk ranked 6th by dense and 1st by keyword is exactly
the chunk hybrid retrieval is supposed to rescue, and it is invisible if dense only reports 5.
`fetch_k` defaults to 4x k for that reason. The *pipeline* still answers from k chunks; the
widening happens below the pipeline and does not change what the prompt sees.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import replace

from app.core.exceptions import RagChatbotError
from app.llm.rag.retrievers.base import RetrievedChunk, Retriever

__all__ = ["DEFAULT_FETCH_MULTIPLIER", "RRF_K", "HybridRetriever", "reciprocal_rank_fusion"]

# Cormack et al. 2009. Not tuned on this corpus — see the module docstring.
RRF_K = 60

# How much wider each retriever searches than the pipeline finally uses.
DEFAULT_FETCH_MULTIPLIER = 4


class HybridRetrievalFailed(RagChatbotError):
    """Neither half of the hybrid retriever could produce a ranking."""


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[RetrievedChunk]], *, k: int = RRF_K
) -> list[RetrievedChunk]:
    """Fuse ranked lists into one, best first, by summing 1 / (k + rank).

    A chunk appearing in several lists accumulates a contribution from each, which is the whole
    mechanism: agreement between two retrievers that rank by unrelated criteria is strong
    evidence, and RRF expresses that without either retriever's score.

    The returned chunks carry the **fused** score and a re-numbered rank. `retriever` is set to
    a `+`-joined summary of which retrievers found each chunk ("dense+bm25", "bm25"), so a
    results file records not just that hybrid ran but where each chunk actually came from —
    which is the diagnostic that says whether the keyword half is contributing at all.

    Ties are broken by best single rank, then by chunk id. Deterministic ordering matters more
    than the tie-break being clever: an eval run that reorders equal-scoring chunks between
    runs would report a metric difference that is pure noise.
    """
    if k < 1:
        raise HybridRetrievalFailed(f"RRF k must be at least 1, got {k}")

    scores: dict[int, float] = {}
    best_rank: dict[int, int] = {}
    sources: dict[int, list[str]] = {}
    chunks: dict[int, RetrievedChunk] = {}

    for ranking in rankings:
        for chunk in ranking:
            cid = chunk.chunk_id
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + chunk.rank)
            best_rank[cid] = min(best_rank.get(cid, chunk.rank), chunk.rank)
            # The first list to contribute a chunk owns the copy that gets returned, so the
            # content and citation fields come from a real retrieval result rather than being
            # rebuilt here.
            chunks.setdefault(cid, chunk)
            if chunk.retriever not in sources.setdefault(cid, []):
                sources[cid].append(chunk.retriever)

    ordered = sorted(scores, key=lambda cid: (-scores[cid], best_rank[cid], cid))
    return [
        replace(
            chunks[cid],
            score=scores[cid],
            rank=rank,
            retriever="+".join(sources[cid]),
        )
        for rank, cid in enumerate(ordered, start=1)
    ]


class HybridRetriever:
    """Dense + keyword, fused by RRF. The Phase 6 retriever."""

    name = "hybrid"

    def __init__(
        self,
        dense: Retriever,
        keyword: Retriever,
        *,
        rrf_k: int = RRF_K,
        fetch_multiplier: int = DEFAULT_FETCH_MULTIPLIER,
    ) -> None:
        self._dense = dense
        self._keyword = keyword
        self._rrf_k = rrf_k
        self._fetch_multiplier = fetch_multiplier

    async def retrieve(self, question: str, k: int) -> list[RetrievedChunk]:
        """Both retrievers concurrently, fused, truncated to k.

        The two halves are independent I/O — one embedding call plus a vector scan, one
        full-text scan — so they run concurrently and hybrid retrieval costs roughly the
        latency of its slower half rather than the sum. That matters: the baseline's p50 is
        already 2 seconds and this is on the serving path, not only in eval.

        A keyword half returning nothing is normal (a question with no content words) and
        falls through to dense alone. A keyword half *raising* is not swallowed: an unusable
        ranking must not be silently downgraded into a dense-only answer that the results file
        would then label `hybrid`.
        """
        if k < 1:
            raise HybridRetrievalFailed(f"top_k must be at least 1, got {k}")

        fetch_k = k * self._fetch_multiplier
        dense_hits, keyword_hits = await asyncio.gather(
            self._dense.retrieve(question, fetch_k),
            self._keyword.retrieve(question, fetch_k),
        )

        fused = reciprocal_rank_fusion([dense_hits, keyword_hits], k=self._rrf_k)
        return fused[:k]
