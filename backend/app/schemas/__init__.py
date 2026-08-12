"""The API contract. Pydantic only — never an ORM object, never a domain dataclass (CLAUDE.md 4.2).

These are a *projection* of `RAGAnswer` and `Document`, not a second model of the domain. Every
field here exists because a client needs it; anything a client does not need (chunk content,
embeddings, `source_path`) stays out, and the `from_*` classmethods are the only place the
mapping is written down.
"""

from __future__ import annotations

from app.schemas.chat import ChatRequest, ChatResponse, Citation
from app.schemas.document import DocumentOut, IngestResponse

__all__ = [
    "ChatRequest",
    "ChatResponse",
    "Citation",
    "DocumentOut",
    "IngestResponse",
]
