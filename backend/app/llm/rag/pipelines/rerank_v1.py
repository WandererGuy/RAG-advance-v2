"""`rerank-v1` — dense top-20, cross-encoder reranked to top-5, + answer_v1.

**The one variable is the reranking stage.** The base retriever is still dense, `top_k` is still
5, the prompt is still `answer_v1.jinja`, the embedding model, the LLM and the chunking are
untouched (CLAUDE.md 5.4). The comparison is against `naive-v1`, not against `hybrid-v2`:
`naive-v1` is dense top-5 and this is dense top-20 reordered down to 5, so the difference
between the two results files is attributable to the reranker and to nothing else. Wiring this
over hybrid instead would have changed two variables and made a win unattributable.

**What it is aimed at.** `recall@5` is 0.958 with essentially no headroom, so — as with
`hybrid-v2` — this must prove itself in **MRR** (0.840) and **nDCG@5** (0.857). Unlike
`hybrid-v2`, it attacks ordering directly rather than as a side effect of fusion, and it cannot
displace a chunk out of the candidate set the way RRF displaced q021: reranking a superset of
the baseline's top-5 preserves recall@20 by construction. If MRR does not move here, the
conclusion is that the ordering problem is not one a cross-encoder can see, which is worth
knowing.

**It costs a provider call per question**, on top of the embedding call and the answer call.
That shows up in p50 and it is part of what is being judged: an ordering win that doubles
latency is a trade, not a free improvement.

The generation half is duplicated from `naive_v1.py` for the third time. CLAUDE.md 4.1 freezes
that file and `hybrid_v2.py`, and phase-6 called this the moment to extract a shared base "from
the *new* pipelines". It is not done here: doing it right means a base class that both this and
a future pipeline inherit, and building that from a single new pipeline would be guessing at the
second one's shape. The extraction belongs with pipeline 4, when there are two new files to
factor and the common shape is observed rather than predicted.
"""

from __future__ import annotations

import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import PipelineConfig, get_settings
from app.llm.client import LLMClient, get_llm_client
from app.llm.prompts import render_prompt
from app.llm.rag.pipelines.base import REFUSAL_MARKER, RAGAnswer, parse_citations
from app.llm.rag.pipelines.registry import register
from app.llm.rag.rerankers import get_reranker
from app.llm.rag.retrievers.base import RetrievedChunk, Retriever
from app.llm.rag.retrievers.dense import DenseRetriever
from app.llm.rag.retrievers.reranker import RerankingRetriever
from app.llm.rag.vector_store import PgVectorStore
from app.repositories.document_repo import DocumentRepository


@register("rerank-v1")
class RerankV1:
    """Dense retrieval, cross-encoder reranking, and a single answer call."""

    name = "rerank-v1"

    def __init__(
        self, retriever: Retriever, llm: LLMClient, config: PipelineConfig | None = None
    ) -> None:
        self.config = config or get_settings().pipeline_config(retriever=retriever.name)
        self._retriever = retriever
        self._llm = llm

    @classmethod
    def build(cls, session: AsyncSession, config: PipelineConfig | None = None) -> RerankV1:
        """Production wiring. Tests construct the class directly with their own doubles.

        The rerank model and candidate width are recorded in the config, not just used: a
        rerank score in a results file is uninterpretable without knowing which model produced
        it and how long the list it was choosing from was.
        """
        settings = get_settings()
        reranker = get_reranker(settings)
        fetch_multiplier = max(1, settings.rerank_top_n // settings.top_k)
        config = config or settings.pipeline_config(
            retriever="dense>rerank",
            reranker=reranker.model,
            rerank_top_n=settings.top_k * fetch_multiplier,
        )
        repo = DocumentRepository(session)
        retriever = RerankingRetriever(
            base=DenseRetriever(PgVectorStore(repo)),
            reranker=reranker,
            fetch_multiplier=fetch_multiplier,
        )
        return cls(retriever, get_llm_client(), config)

    async def retrieve(self, question: str) -> list[RetrievedChunk]:
        return await self._retriever.retrieve(question, self.config.top_k)

    async def answer(self, question: str) -> RAGAnswer:
        """Retrieve, rerank, render, answer, then read the citations back out of the answer.

        As in `naive-v1` and `hybrid-v2`: when retrieval returns nothing the model is not called
        at all. There is no context to answer from, so the refusal is the only correct output.
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
