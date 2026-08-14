"""Retrievers: question -> ranked chunks. The protocol is in `base`, implementations beside it.

`dense` is Phase 4's; `bm25`, `hybrid` and `reranker` are Phase 6's, each added as a new file
with its own pipeline and its own results file (CLAUDE.md 5.4).

`reranker` is a two-stage *retriever*; the provider adapters it composes over live in the
sibling `rerankers/` package, because reordering is a different seam from retrieving.
"""

from __future__ import annotations

from app.llm.rag.retrievers.base import RetrievedChunk, Retriever
from app.llm.rag.retrievers.bm25 import BM25Retriever
from app.llm.rag.retrievers.dense import DenseRetriever
from app.llm.rag.retrievers.hybrid import HybridRetriever, reciprocal_rank_fusion
from app.llm.rag.retrievers.reranker import RerankingRetriever

__all__ = [
    "BM25Retriever",
    "DenseRetriever",
    "HybridRetriever",
    "RerankingRetriever",
    "RetrievedChunk",
    "Retriever",
    "reciprocal_rank_fusion",
]
