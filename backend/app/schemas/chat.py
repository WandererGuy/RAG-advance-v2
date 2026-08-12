"""`POST /chat` request and response.

`Citation` carries `supported` out to the client rather than filtering unsupported citations
away here. A citation the model produced that resolves to nothing retrieved is the single most
informative failure this system can record (ADR-0006, and the reason `parse_citations` keeps
them); the API's job is to label it, and the UI's job is to not render it as a normal source.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.llm.rag.pipelines.base import Citation as DomainCitation
from app.llm.rag.pipelines.base import RAGAnswer

# Long enough for a real policy question, short enough that the embedding call cannot be used
# to push an essay through the provider on someone else's key.
MAX_QUESTION_CHARS = 1000

# The snippet shown under a citation in the UI. Whole chunks are up to chunk_size characters
# and would bury the answer.
SNIPPET_CHARS = 300


class ChatRequest(BaseModel):
    """Single-turn. No `conversation_id` — multi-turn is post-Phase-6 (CLAUDE.md 2)."""

    question: str = Field(
        min_length=1,
        max_length=MAX_QUESTION_CHARS,
        description="The user's question, in Vietnamese.",
    )


class Citation(BaseModel):
    """One `[filename, p.N]` from the answer, resolved back to the chunk it came from."""

    filename: str
    page_no: int | None = Field(
        default=None,
        description="None for a DOCX chunk, which has no real pagination (see loaders.load_docx).",
    )
    chunk_id: int | None = Field(
        default=None, description="None when the citation resolved to nothing retrieved."
    )
    snippet: str | None = Field(
        default=None, description="The start of the cited chunk. None when chunk_id is None."
    )
    supported: bool = Field(
        description=(
            "False when the answer cited a source that was not in its own context — a "
            "fabricated citation. Must not be rendered as a normal source."
        )
    )


class ChatResponse(BaseModel):
    """What the client renders. A projection of RAGAnswer, plus the query row's id."""

    query_id: int | None = Field(
        default=None,
        description=(
            "Row in `queries`. None when the answer was produced but persisting it failed — "
            "the user still gets their answer."
        ),
    )
    question: str
    answer: str
    refused: bool = Field(
        description=(
            "True when the answer is the refusal sentence — detected by string, never judged "
            "(ADR-0006)."
        )
    )
    citations: list[Citation] = Field(default_factory=list)
    chunk_ids: list[int] = Field(
        default_factory=list,
        description="Everything retrieved, in rank order — not only what was cited.",
    )
    pipeline_name: str
    latency_ms: int

    @classmethod
    def from_answer(
        cls,
        answer: RAGAnswer,
        *,
        query_id: int | None = None,
    ) -> ChatResponse:
        """The one place RAGAnswer becomes the wire format."""
        snippets = {c.chunk_id: c.content for c in answer.retrieved}
        return cls(
            query_id=query_id,
            question=answer.question,
            answer=answer.answer,
            refused=answer.refused,
            citations=[_citation(c, snippets) for c in answer.citations],
            chunk_ids=answer.chunk_ids,
            pipeline_name=answer.pipeline_name,
            latency_ms=answer.latency_ms,
        )


def _citation(citation: DomainCitation, snippets: dict[int, str]) -> Citation:
    content = snippets.get(citation.chunk_id) if citation.chunk_id is not None else None
    return Citation(
        filename=citation.filename,
        page_no=citation.page_no,
        chunk_id=citation.chunk_id,
        snippet=_snippet(content),
        supported=citation.supported,
    )


def _snippet(content: str | None) -> str | None:
    if content is None:
        return None
    text = " ".join(content.split())
    return text if len(text) <= SNIPPET_CHARS else text[:SNIPPET_CHARS].rstrip() + "…"
