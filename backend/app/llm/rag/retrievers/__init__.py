"""Retrievers: question -> ranked chunks. The protocol is in `base`, implementations beside it.

`dense` is Phase 4's; `bm25` and `hybrid` are Phase 6's, each added as a new file with its own
pipeline and its own results file (CLAUDE.md 5.4). `reranker` is still to come.
"""

from __future__ import annotations

from app.llm.rag.retrievers.base import RetrievedChunk, Retriever
from app.llm.rag.retrievers.bm25 import BM25Retriever
from app.llm.rag.retrievers.dense import DenseRetriever
from app.llm.rag.retrievers.hybrid import HybridRetriever, reciprocal_rank_fusion

__all__ = [
    "BM25Retriever",
    "DenseRetriever",
    "HybridRetriever",
    "RetrievedChunk",
    "Retriever",
    "reciprocal_rank_fusion",
]
