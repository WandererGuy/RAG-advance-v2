"""Retrievers: question -> ranked chunks. The protocol is in `base`, implementations beside it.

Only `dense` exists in Phase 4. `bm25`, `hybrid` and `reranker` are Phase 6 and are added as
new files, each with its own pipeline and its own results file (CLAUDE.md 5.4).
"""

from __future__ import annotations

from app.llm.rag.retrievers.base import RetrievedChunk, Retriever
from app.llm.rag.retrievers.dense import DenseRetriever

__all__ = ["DenseRetriever", "RetrievedChunk", "Retriever"]
