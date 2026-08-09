"""Text -> vectors, through LiteLLM. The provider is never hardcoded (ADR-0002).

The one trap this module exists to close: **`gemini-embedding-001` returns 3072 dimensions by
default** while the `chunks.embedding` column is `vector(768)`. Every call therefore passes
`dimensions` explicitly, and every response is length-checked before it can reach the database —
a mismatch caught here names the model and both numbers, instead of surfacing as an asyncpg
error on a bulk insert of a thousand rows.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.core.config import Settings, get_settings
from app.core.exceptions import RagChatbotError
from app.core.logging import get_logger

log = get_logger(__name__)

# Gemini accepts up to 100 inputs per embedContent batch; 32 keeps a single failed batch cheap
# to retry and the request body comfortably small.
BATCH_SIZE = 32

MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 1.0


class EmbeddingFailed(RagChatbotError):
    """The provider could not be made to return usable vectors."""


@runtime_checkable
class Embedder(Protocol):
    """What the ingest service and (from Phase 4) the dense retriever program against."""

    model: str
    dimensions: int

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...

    def count_tokens(self, text: str) -> int: ...


class LiteLLMEmbedder:
    """The only implementation. Swapping provider is an .env change, not a code change."""

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self.model = settings.embedding_model
        self.dimensions = settings.embedding_dimensions
        self._api_key = settings.embedding_api_key or None

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed in batches of BATCH_SIZE, preserving input order.

        Returns one vector per input text, in the same order — the caller zips these straight
        onto its chunks, so a reordered response would silently attach every vector to the
        wrong chunk.
        """
        if not texts:
            return []

        vectors: list[list[float]] = []
        for offset in range(0, len(texts), BATCH_SIZE):
            batch = list(texts[offset : offset + BATCH_SIZE])
            vectors.extend(await self._embed_batch(batch, offset))
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_texts([text]))[0]

    def count_tokens(self, text: str) -> int:
        """Approximate token count, used for `chunks.token_count` and for logging.

        Gemini does not publish a local tokenizer, so this is tiktoken's `cl100k_base` standing
        in. It is an estimate, not a billing figure, and nothing in the pipeline branches on it.
        """
        import tiktoken

        return len(tiktoken.get_encoding("cl100k_base").encode(text))

    async def _embed_batch(self, batch: list[str], offset: int) -> list[list[float]]:
        """One batch, retried with exponential backoff, then validated."""
        import litellm

        last_error: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await litellm.aembedding(
                    model=self.model,
                    input=batch,
                    api_key=self._api_key,
                    # Not optional. See the module docstring.
                    dimensions=self.dimensions,
                )
                return self._validate(response, batch, offset)
            except EmbeddingFailed:
                # A dimension mismatch is a configuration error; retrying it just burns quota.
                raise
            except Exception as exc:  # provider/transport errors are all retryable
                last_error = exc
                if attempt == MAX_ATTEMPTS:
                    break
                delay = BACKOFF_BASE_SECONDS * 2 ** (attempt - 1)
                log.warning(
                    "embedding_batch_retry",
                    model=self.model,
                    attempt=attempt,
                    max_attempts=MAX_ATTEMPTS,
                    delay_seconds=delay,
                    error=str(exc),
                )
                await asyncio.sleep(delay)

        raise EmbeddingFailed(
            f"embedding failed after {MAX_ATTEMPTS} attempts "
            f"({self.model}, batch of {len(batch)}): {last_error}"
        ) from last_error

    def _validate(self, response: object, batch: list[str], offset: int) -> list[list[float]]:
        """Check count and dimension before anything reaches the database."""
        data = list(getattr(response, "data", []) or [])
        if len(data) != len(batch):
            raise EmbeddingFailed(
                f"{self.model} returned {len(data)} vectors for {len(batch)} inputs"
            )

        # The provider carries an `index` per item; sort by it rather than trusting arrival
        # order, since a reordered batch would attach every vector to the wrong chunk.
        if all(item.get("index") is not None for item in data):
            data.sort(key=lambda item: item["index"])

        vectors: list[list[float]] = []
        for position, item in enumerate(data):
            vector = list(item["embedding"])
            if len(vector) != self.dimensions:
                raise EmbeddingFailed(
                    f"{self.model} returned {len(vector)} dimensions, expected "
                    f"{self.dimensions} (input {offset + position}). The chunks.embedding "
                    f"column is vector({self.dimensions}); see ADR-0002."
                )
            vectors.append(vector)
        return vectors


def get_embedder(settings: Settings | None = None) -> Embedder:
    """Construct the configured embedder. Callers depend on the protocol, not the class."""
    return LiteLLMEmbedder(settings)
