"""Rerank provider adapters: `(question, candidates) -> reordered candidates`.

The protocol is in `base`, the adapters in `providers`. A reranker is a separate seam from a
`Retriever` because it cannot retrieve — it only reorders what something else found. The
provider is an `.env` choice (`RERANK_PROVIDER`), never a hardcoded import.
"""

from __future__ import annotations

from app.llm.rag.rerankers.base import Reranker, RerankFailed
from app.llm.rag.rerankers.providers import JinaReranker, LiteLLMReranker, get_reranker

__all__ = [
    "JinaReranker",
    "LiteLLMReranker",
    "RerankFailed",
    "Reranker",
    "get_reranker",
]
