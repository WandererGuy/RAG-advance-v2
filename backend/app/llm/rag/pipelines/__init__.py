"""Pipelines. Importing this package is what populates the registry.

Every implementation must be imported here — a pipeline that is never imported is never
registered, and `--pipeline <name>` would fail with "not registered" for a file that exists.
That is the one line a new Phase 6 pipeline adds outside its own file.
"""

from __future__ import annotations

from app.llm.rag.pipelines.base import (
    REFUSAL_MARKER,
    Citation,
    RAGAnswer,
    RAGPipeline,
    is_refusal,
    parse_citations,
)
from app.llm.rag.pipelines.hybrid_v2 import HybridV2
from app.llm.rag.pipelines.naive_v1 import NaiveV1
from app.llm.rag.pipelines.registry import available, build_pipeline, get_pipeline, register
from app.llm.rag.pipelines.rerank_v1 import RerankV1

__all__ = [
    "REFUSAL_MARKER",
    "Citation",
    "HybridV2",
    "NaiveV1",
    "RerankV1",
    "RAGAnswer",
    "RAGPipeline",
    "available",
    "build_pipeline",
    "get_pipeline",
    "is_refusal",
    "parse_citations",
    "register",
]
