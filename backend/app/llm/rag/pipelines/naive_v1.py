"""`naive-v1` — dense top-5 + answer_v1. The baseline, and deliberately the dumbest thing.

Retrieve the top 5 chunks by cosine similarity, put them in the prompt, answer. No reranking,
no query rewriting, no threshold, no fallback when retrieval returns nothing useful. This is a
reference point, not a product (PLAN.md Phase 4).

**Frozen once `results/naive-v1.json` is committed.** Every later idea is a new file with a new
name, changing exactly one variable against this (CLAUDE.md 4.1, 5.4). Editing this file after
its results exist destroys the only fixed point the project has to measure against.
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
from app.llm.rag.retrievers.dense import DenseRetriever
from app.llm.rag.vector_store import PgVectorStore
from app.repositories.document_repo import DocumentRepository


@register("naive-v1")
class NaiveV1:
    """Dense retrieval + a single answer call."""

    name = "naive-v1"

    def __init__(
        self, retriever: Retriever, llm: LLMClient, config: PipelineConfig | None = None
    ) -> None:
        self.config = config or get_settings().pipeline_config(retriever=retriever.name)
        self._retriever = retriever
        self._llm = llm

    @classmethod
    def build(cls, session: AsyncSession, config: PipelineConfig | None = None) -> NaiveV1:
        """Production wiring. Tests construct the class directly with their own doubles."""
        config = config or get_settings().pipeline_config(retriever="dense")
        store = PgVectorStore(DocumentRepository(session))
        return cls(DenseRetriever(store), get_llm_client(), config)

    async def retrieve(self, question: str) -> list[RetrievedChunk]:
        return await self._retriever.retrieve(question, self.config.top_k)

    async def answer(self, question: str) -> RAGAnswer:
        """Retrieve, render, answer, then read the citations back out of the answer.

        When retrieval returns nothing the model is not called at all: there is no context to
        answer from, so the refusal is the only correct output and spending a call to obtain it
        would just add a way for the run to fail. This is a real case for the `unanswerable`
        questions on an 8-document corpus, not a defensive branch.
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
