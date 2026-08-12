"""`hybrid-v2` — dense+keyword RRF top-5 + answer_v1. One variable changed against `naive-v1`.

**The one variable is the retriever.** `top_k` is still 5, the prompt is still `answer_v1.jinja`,
the embedding model, the LLM and the chunking are untouched. That is CLAUDE.md 5.4, and it is
what makes the difference between this results file and `naive-v1.json` attributable to hybrid
retrieval rather than to a bundle of simultaneous changes.

The generation half is deliberately identical to `naive_v1.py`, down to the no-context early
return. It is duplicated rather than shared through a base class: `naive_v1.py` is frozen
(CLAUDE.md 4.1), so factoring the common half out would mean editing it, and a refactor that
touches a frozen pipeline to avoid twenty duplicated lines trades the project's only fixed point
for a DRY that nothing is asking for. When a third pipeline repeats this a second time, that is
the moment to extract a shared base — from the *new* pipelines, still not by editing this one.

What Phase 4 says to watch, and what this file is aimed at: `recall@5` is already 0.958 with
almost no headroom, so hybrid must prove itself in **MRR and nDCG@5** — getting the right chunk
*higher*, not merely present — and in `answer_relevance` downstream of that. A hybrid pipeline
that moves recall by 0.01 and MRR by nothing has not earned its latency.
"""

from __future__ import annotations

import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import PipelineConfig, get_settings
from app.llm.client import LLMClient, get_llm_client
from app.llm.prompts import render_prompt
from app.llm.rag.pipelines.base import REFUSAL_MARKER, RAGAnswer, parse_citations
from app.llm.rag.pipelines.registry import register
from app.llm.rag.retrievers.base import RetrievedChunk, Retriever
from app.llm.rag.retrievers.bm25 import BM25Retriever
from app.llm.rag.retrievers.dense import DenseRetriever
from app.llm.rag.retrievers.hybrid import HybridRetriever
from app.llm.rag.vector_store import PgVectorStore
from app.repositories.document_repo import DocumentRepository


@register("hybrid-v2")
class HybridV2:
    """Hybrid retrieval + a single answer call."""

    name = "hybrid-v2"

    def __init__(
        self, retriever: Retriever, llm: LLMClient, config: PipelineConfig | None = None
    ) -> None:
        self.config = config or get_settings().pipeline_config(retriever=retriever.name)
        self._retriever = retriever
        self._llm = llm

    @classmethod
    def build(cls, session: AsyncSession, config: PipelineConfig | None = None) -> HybridV2:
        """Production wiring. Tests construct the class directly with their own doubles."""
        config = config or get_settings().pipeline_config(retriever="hybrid")
        repo = DocumentRepository(session)
        retriever = HybridRetriever(
            dense=DenseRetriever(PgVectorStore(repo)),
            keyword=BM25Retriever(repo),
        )
        return cls(retriever, get_llm_client(), config)

    async def retrieve(self, question: str) -> list[RetrievedChunk]:
        return await self._retriever.retrieve(question, self.config.top_k)

    async def answer(self, question: str) -> RAGAnswer:
        """Retrieve, render, answer, then read the citations back out of the answer.

        As in `naive-v1`: when retrieval returns nothing the model is not called at all. There
        is no context to answer from, so the refusal is the only correct output and a call
        would only add a way for the run to fail.
        """
        started = time.perf_counter()

        retrieval_started = time.perf_counter()
        chunks = await self.retrieve(question)
        retrieval_ms = int((time.perf_counter() - retrieval_started) * 1000)

        if not chunks:
            return RAGAnswer(
                question=question,
                answer=REFUSAL_MARKER,
                citations=[],
                chunk_ids=[],
                pipeline_name=self.name,
                config=self.config,
                latency_ms=int((time.perf_counter() - started) * 1000),
                retrieved=[],
                retrieval_ms=retrieval_ms,
                generation_ms=0,
            )

        prompt = render_prompt(
            f"answer_{self.config.prompt_version}",
            question=question,
            chunks=chunks,
            refusal_marker=REFUSAL_MARKER,
        )
        response = await self._llm.complete(prompt)

        return RAGAnswer(
            question=question,
            answer=response.text,
            citations=parse_citations(response.text, chunks),
            chunk_ids=[c.chunk_id for c in chunks],
            pipeline_name=self.name,
            config=self.config,
            latency_ms=int((time.perf_counter() - started) * 1000),
            retrieved=chunks,
            retrieval_ms=retrieval_ms,
            generation_ms=response.latency_ms,
        )
