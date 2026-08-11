"""The pipeline seam. One pipeline = one complete RAG configuration with a name (CLAUDE.md 4.1).

A pipeline that has results in `results/` is **immutable**. New idea → new file, new name.

Three things live here rather than in a pipeline implementation, because every pipeline and the
eval runner have to agree on them exactly:

* **`REFUSAL_MARKER`** — the sentence a pipeline must emit when the context is insufficient. It
  is injected into `answer_v1.jinja` and matched by `is_refusal()`, so the prompt and the
  detector cannot drift. Refusal is detected by string, not judged by a model: see ADR-0006.
* **`parse_citations()`** — the `[filename, p.N]` format the prompt demands, read back out of
  the answer. A citation naming a chunk that was never retrieved is a fabricated source, and
  the runner counts those; that only works if one parser defines what a citation is.
* **`RAGAnswer`** — what the runner writes down. It carries the retrieved chunks, not only
  their ids, because the faithfulness judge scores the answer against the context it was
  actually given.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.core.config import PipelineConfig
from app.llm.rag.retrievers.base import RetrievedChunk

# The exact sentence. Changing it changes what every committed refusal number means, so it
# changes with a new prompt version and a new pipeline name, never on its own.
REFUSAL_MARKER = "Không tìm thấy thông tin trong tài liệu."

# [filename, p.12] — the format answer_v1.jinja requires. The page group also accepts "?" so a
# DOCX chunk with no real pagination can still be cited rather than silently dropped.
_CITATION = re.compile(r"\[\s*([^\[\],]+?)\s*,\s*(?:p\.|tr\.|trang)\s*(\d+|\?)\s*\]")


@dataclass(frozen=True)
class Citation:
    """One `[filename, p.N]` found in an answer, resolved against what was retrieved."""

    filename: str
    page_no: int | None
    chunk_id: int | None = None
    # False when the answer cited a file/page that was not in its own context — a fabricated
    # source. Kept rather than dropped: silently discarding it would hide the failure.
    supported: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "page_no": self.page_no,
            "chunk_id": self.chunk_id,
            "supported": self.supported,
        }


@dataclass(frozen=True)
class RAGAnswer:
    """The full record of answering one question — everything a results file needs."""

    question: str
    answer: str
    citations: list[Citation]
    chunk_ids: list[int]
    pipeline_name: str
    config: PipelineConfig
    latency_ms: int
    retrieved: list[RetrievedChunk] = field(default_factory=list)
    retrieval_ms: int = 0
    generation_ms: int = 0

    @property
    def refused(self) -> bool:
        return is_refusal(self.answer)

    def to_dict(self, *, include_answer: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "question": self.question,
            "refused": self.refused,
            "chunk_ids": self.chunk_ids,
            "citations": [c.to_dict() for c in self.citations],
            "retrieved": [c.to_dict() for c in self.retrieved],
            "latency_ms": self.latency_ms,
            "retrieval_ms": self.retrieval_ms,
            "generation_ms": self.generation_ms,
        }
        if include_answer:
            payload["answer"] = self.answer
        return payload


@runtime_checkable
class RAGPipeline(Protocol):
    """`eval/runner.py --pipeline <name>` works for any implementation of this."""

    name: str
    config: PipelineConfig

    async def retrieve(self, question: str) -> list[RetrievedChunk]: ...

    async def answer(self, question: str) -> RAGAnswer: ...


def _normalise(text: str) -> str:
    """Casefold + NFC + collapsed whitespace, for comparing Vietnamese strings."""
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def is_refusal(answer: str) -> bool:
    """True when the answer is the refusal sentence.

    Substring, not equality: models append a clarifying line often enough that requiring an
    exact match would score honest refusals as hallucinations. Normalised first so a stray
    double space or a decomposed diacritic does not decide a metric.
    """
    return _normalise(REFUSAL_MARKER) in _normalise(answer)


def parse_citations(answer: str, retrieved: Sequence[RetrievedChunk]) -> list[Citation]:
    """Extract `[filename, p.N]` citations and resolve each against the retrieved context.

    Resolution is by (filename, page_no) because that is all the model is given to cite with;
    the chunk id is recovered from the retrieved set so a citation can be clicked in Phase 5.
    A citation that matches nothing retrieved is kept with `supported=False` — it is the single
    most informative failure this project can record, and dropping it would erase it.
    """
    by_source: dict[tuple[str, int | None], int] = {}
    for chunk in retrieved:
        by_source.setdefault((chunk.filename.casefold(), chunk.page_no), chunk.chunk_id)

    citations: list[Citation] = []
    seen: set[tuple[str, int | None]] = set()
    for filename, page in _CITATION.findall(answer):
        page_no = None if page == "?" else int(page)
        key = (filename.casefold(), page_no)
        if key in seen:
            continue
        seen.add(key)
        chunk_id = by_source.get(key)
        citations.append(
            Citation(
                filename=filename,
                page_no=page_no,
                chunk_id=chunk_id,
                supported=chunk_id is not None,
            )
        )
    return citations
