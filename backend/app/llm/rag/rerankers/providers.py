"""Rerank provider adapters. Two of them, because the APIs have not converged.

* **Voyage** (`voyage/rerank-2.5-lite`, the default) goes through LiteLLM's `arerank`, the same
  way `client.py` and `embedder.py` go through `acompletion` and `aembedding`. Nothing
  provider-specific reaches this project.
* **Jina** (`jina/jina-reranker-v2-base-multilingual`) is a direct HTTPS call, because LiteLLM
  1.96 does not route Jina reranking. When it does, this class becomes a two-line delegation to
  the LiteLLM adapter and then deletes itself.

Both return **indices into the input list**, never rewritten chunks. That is the invariant this
module protects: a reranker reorders and truncates, it never edits content, never invents a
chunk id, and never returns a chunk that was not in its input. `_reorder` enforces it centrally
so neither adapter can drift from it, and so a provider returning a garbage index fails loudly
here instead of producing a citation pointing at the wrong document.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.llm.rag.rerankers.base import RerankFailed
from app.llm.rag.retrievers.base import RetrievedChunk

log = get_logger(__name__)

MAX_ATTEMPTS = 4
BACKOFF_BASE_SECONDS = 1.0
TIMEOUT_SECONDS = 60.0

JINA_API_URL = "https://api.jina.ai/v1/rerank"


def _reorder(
    chunks: Sequence[RetrievedChunk],
    scored: Sequence[tuple[int, float]],
    *,
    model: str,
    top_n: int,
) -> list[RetrievedChunk]:
    """Turn (index, score) pairs from a provider into re-ranked chunks, best first.

    Every index is bounds-checked and de-duplicated before it is used. A provider that returns
    an out-of-range index has misunderstood the request, and the failure mode if it were
    trusted is the worst kind this project has: a confidently cited answer attached to the
    wrong source document. Cheaper to raise.

    `rank` is renumbered from 1 and `score` is replaced with the provider's relevance score;
    `retriever` records both stages ("dense>voyage-rerank") so a results file says what actually
    produced the ordering rather than only naming the last step.
    """
    seen: set[int] = set()
    out: list[RetrievedChunk] = []
    for index, score in scored:
        if not 0 <= index < len(chunks):
            raise RerankFailed(
                f"{model} returned index {index} for a candidate list of {len(chunks)} — "
                "the ordering cannot be trusted"
            )
        if index in seen:
            continue
        seen.add(index)
        source = chunks[index]
        out.append(
            replace(
                source,
                score=score,
                rank=len(out) + 1,
                retriever=f"{source.retriever}>{model.split('/')[-1]}",
            )
        )
        if len(out) >= top_n:
            break
    return out


async def _with_retry(call: Any, *, model: str) -> Any:
    """Retry transport and rate-limit errors with exponential backoff.

    Deliberately does not retry a `RerankFailed`: that is raised for a malformed response or a
    bad index, which is a configuration or contract problem and identical on every attempt.
    """
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return await call()
        except RerankFailed:
            raise
        except Exception as exc:  # provider/transport errors are all retryable
            last_error = exc
            if attempt == MAX_ATTEMPTS:
                break
            delay = BACKOFF_BASE_SECONDS * 2 ** (attempt - 1)
            log.warning(
                "rerank_retry",
                model=model,
                attempt=attempt,
                max_attempts=MAX_ATTEMPTS,
                delay_seconds=delay,
                error=str(exc),
            )
            await asyncio.sleep(delay)

    raise RerankFailed(f"rerank failed after {MAX_ATTEMPTS} attempts ({model}): {last_error}")


class LiteLLMReranker:
    """Voyage, Cohere and anything else LiteLLM's `arerank` routes. The default path."""

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self.model = settings.rerank_model
        self._provider = settings.rerank_provider.lower()
        self._api_key = settings.rerank_api_key or None

    async def rerank(
        self, question: str, chunks: Sequence[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []

        async def call() -> Any:
            import litellm

            return await litellm.arerank(
                model=self.model,
                query=question,
                documents=[c.content for c in chunks],
                custom_llm_provider=self._provider,
                top_n=min(top_n, len(chunks)),
                # The chunks are already in hand; asking for them back doubles the response
                # size and this project never reads the echoed text.
                return_documents=False,
                api_key=self._api_key,
                timeout=TIMEOUT_SECONDS,
            )

        response = await _with_retry(call, model=self.model)
        return _reorder(chunks, _parse_litellm(response, self.model), model=self.model, top_n=top_n)


class JinaReranker:
    """`jina-reranker-v2-base-multilingual`, over raw HTTPS.

    Exists because LiteLLM 1.96 does not route Jina reranking. The request and response shapes
    follow Cohere's rerank convention, which is what Jina implemented.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self.model = settings.rerank_model
        self._api_key = settings.rerank_api_key
        if not self._api_key:
            raise RerankFailed("RERANK_API_KEY is empty — the Jina rerank API requires a key")

    async def rerank(
        self, question: str, chunks: Sequence[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []

        async def call() -> Any:
            import httpx

            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
                response = await client.post(
                    JINA_API_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        # Jina wants the bare model name, not the provider-qualified one.
                        "model": self.model.split("/", 1)[-1],
                        "query": question,
                        "documents": [c.content for c in chunks],
                        "top_n": min(top_n, len(chunks)),
                        "return_documents": False,
                    },
                )
                response.raise_for_status()
                return response.json()

        payload = await _with_retry(call, model=self.model)
        return _reorder(chunks, _parse_jina(payload, self.model), model=self.model, top_n=top_n)


def _parse_litellm(response: object, model: str) -> list[tuple[int, float]]:
    """Pull (index, relevance_score) out of a LiteLLM RerankResponse without trusting its shape.

    LiteLLM normalises providers onto Cohere's response object, but `results` arrives as a list
    of dicts on some providers and of objects on others. Reading both keeps a provider swap from
    surfacing as an AttributeError inside a pipeline.
    """
    results = getattr(response, "results", None)
    if results is None and isinstance(response, dict):
        results = response.get("results")
    if not results:
        raise RerankFailed(f"{model} returned no rerank results: {response!r}"[:500])

    scored: list[tuple[int, float]] = []
    for item in results:
        if isinstance(item, dict):
            index, score = item.get("index"), item.get("relevance_score")
        else:
            index = getattr(item, "index", None)
            score = getattr(item, "relevance_score", None)
        if index is None:
            raise RerankFailed(f"{model} returned a result with no index: {item!r}"[:300])
        scored.append((int(index), float(score if score is not None else 0.0)))
    return scored


def _parse_jina(payload: object, model: str) -> list[tuple[int, float]]:
    """Same, for Jina's JSON body."""
    if not isinstance(payload, dict):
        raise RerankFailed(f"{model} returned a non-object response: {payload!r}"[:300])
    results = payload.get("results")
    if not results:
        raise RerankFailed(f"{model} returned no rerank results: {payload!r}"[:500])

    scored: list[tuple[int, float]] = []
    for item in results:
        index, score = item.get("index"), item.get("relevance_score")
        if index is None:
            raise RerankFailed(f"{model} returned a result with no index: {item!r}"[:300])
        scored.append((int(index), float(score if score is not None else 0.0)))
    return scored


def get_reranker(settings: Settings | None = None) -> Any:
    """Construct the configured reranker. Callers depend on the `Reranker` protocol.

    The provider is read from `.env` and never hardcoded, exactly as for the LLM and the
    embedder. An unknown provider raises here, at construction, rather than at the first
    question of a 29-question eval run.
    """
    settings = settings or get_settings()
    provider = settings.rerank_provider.lower()
    if provider == "jina":
        return JinaReranker(settings)
    if provider in {"voyage", "cohere", "together_ai", "deepinfra", "fireworks_ai", "watsonx"}:
        return LiteLLMReranker(settings)
    raise RerankFailed(
        f"unknown RERANK_PROVIDER {settings.rerank_provider!r} — expected one of: "
        "voyage, jina, cohere, together_ai, deepinfra, fireworks_ai, watsonx"
    )
