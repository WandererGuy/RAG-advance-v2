"""The reranker seam: `rerank(question, chunks, top_n) -> list[RetrievedChunk]`, reordered.

A reranker is **not** a `Retriever`. It never touches the corpus and cannot find a chunk that
retrieval missed — it takes a candidate list someone else produced and reorders it. Giving it
the `Retriever` protocol would let it be wired in as a first-stage retriever, where it would
silently rank nothing at all. Two protocols, because they consume different things.

**The score is the provider's relevance score, and it is not comparable to anything else** —
not to a cosine similarity, not to a `ts_rank_cd`, not to a score from a different rerank
model. `RetrievedChunk.score` is documented as retriever-specific (see `retrievers/base.py`)
and the same rule holds here: the number written into `results/*.json` means "what
voyage/rerank-2.5-lite thought", not "how relevant this is".

**Why an adapter protocol rather than one hardcoded provider.** Rerank APIs have not converged
the way chat and embedding APIs did. LiteLLM 1.96 routes `arerank` to Cohere, Voyage, Together,
DeepInfra, Fireworks and WatsonX — but not Jina, which needs its own HTTP call. Programming
against a protocol means the choice is an `.env` change (`RERANK_PROVIDER`), and a provider
that LiteLLM adds support for later collapses from a new file into a deleted one.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from app.core.exceptions import RagChatbotError

if TYPE_CHECKING:
    # Import-time only. `retrievers/__init__` pulls in `retrievers/reranker`, which imports
    # this module, so importing `RetrievedChunk` eagerly here closes a cycle. It is used
    # purely as an annotation, and `from __future__ import annotations` keeps those lazy.
    from app.llm.rag.retrievers.base import RetrievedChunk


class RerankFailed(RagChatbotError):
    """The rerank provider could not be made to return a usable ordering."""


@runtime_checkable
class Reranker(Protocol):
    """What a reranking retriever receives in its constructor. It never builds one itself."""

    #: Provider-qualified model identifier, e.g. "voyage/rerank-2.5-lite". Written verbatim
    #: into every results file, so a score can be traced to the model that produced it.
    model: str

    async def rerank(
        self, question: str, chunks: Sequence[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]: ...
