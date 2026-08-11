"""Dense retrieval: embed the question, cosine top-k through the VectorStore. Nothing else.

No reranking, no metadata filtering, no query rewriting, no score threshold — PLAN.md Phase 4
is explicit, and every one of those is a Phase 6 experiment that must be its own pipeline with
its own results file. A threshold in particular would be the tempting one to add here, because
it would make the `unanswerable` questions look better; it would also change what the baseline
measures, and there would be nothing left to compare Phase 6 against.

The one thing that is not negotiable: the query is embedded with the same model and the same
dimension count as the corpus was. A 768-dim corpus searched with a 3072-dim query vector is a
database error at best and a silently meaningless ranking at worst, so the check is explicit.
"""

from __future__ import annotations

from app.core.exceptions import RagChatbotError
from app.llm.rag.embedder import Embedder, get_embedder
from app.llm.rag.retrievers.base import RetrievedChunk, from_hits
from app.llm.rag.vector_store import VectorStore


class RetrievalFailed(RagChatbotError):
    """The question could not be turned into a ranked list of chunks."""


class DenseRetriever:
    """Embedding similarity over `chunks.embedding`. The only retriever in v1."""

    name = "dense"

    def __init__(self, store: VectorStore, embedder: Embedder | None = None) -> None:
        self._store = store
        self._embedder = embedder or get_embedder()

    async def retrieve(self, question: str, k: int) -> list[RetrievedChunk]:
        """Top-k chunks for `question`, best first. Returns fewer than k if the corpus is small."""
        if not question.strip():
            raise RetrievalFailed("cannot retrieve for an empty question")
        if k < 1:
            raise RetrievalFailed(f"top_k must be at least 1, got {k}")

        vector = await self._embedder.embed_query(question)
        if len(vector) != self._embedder.dimensions:
            raise RetrievalFailed(
                f"query embedding has {len(vector)} dimensions, the corpus was embedded at "
                f"{self._embedder.dimensions} — the ranking would be meaningless"
            )

        hits = await self._store.search(vector, k)
        return from_hits(hits, retriever=self.name)
