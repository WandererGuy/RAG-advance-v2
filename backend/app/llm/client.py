"""Chat completions, through LiteLLM. The provider is never hardcoded (ADR-0002).

The sibling of `rag/embedder.py`, and deliberately shaped like it: a protocol the callers
program against, one implementation, retry with exponential backoff, and every provider-shaped
surprise turned into a named exception here rather than an AttributeError three layers up.

Two things this module fixes in place, because an evaluation number that cannot be reproduced
is not a number:

* **`temperature=0` by default.** Two runs of the same pipeline over the same corpus should
  differ as little as the provider allows. It is not a guarantee — nothing about a hosted model
  is — but a default of 1.0 would make the baseline unrepeatable by construction.
* **A timeout on every call.** `eval/runner.py` makes ~4 calls per question; one request that
  hangs forever would hang the whole run with no partial results written.

No streaming (PLAN.md Phase 4 says so explicitly): the eval runner has nothing to stream to,
and Phase 5's frontend can render a whole answer.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.core.config import Settings, get_settings
from app.core.exceptions import RagChatbotError
from app.core.logging import get_logger

log = get_logger(__name__)

MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 2.0
TIMEOUT_SECONDS = 120.0


class LLMCallFailed(RagChatbotError):
    """The provider could not be made to return a usable completion."""


@dataclass(frozen=True)
class LLMResponse:
    """One completion, plus what it cost and how long it took."""

    text: str
    model: str
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@runtime_checkable
class LLMClient(Protocol):
    """What a pipeline and the judge program against."""

    model: str

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse: ...


class LiteLLMClient:
    """The only implementation. Swapping provider is a .env change, not a code change."""

    def __init__(self, settings: Settings | None = None, *, model: str | None = None) -> None:
        settings = settings or get_settings()
        self.model = model or settings.llm_model
        self._api_key = settings.default_llm_api_key or None
        self._api_base = settings.default_llm_api_base or None

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """One completion, retried on transport and rate-limit errors.

        An empty completion is raised as a failure rather than returned as an empty answer: a
        blank string scored by the judge would look like a refusal and quietly become a passing
        `refusal_accuracy` for a question the system never actually answered.
        """
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        started = time.perf_counter()
        response = await self._call_with_retry(messages, temperature, max_tokens)
        latency_ms = int((time.perf_counter() - started) * 1000)

        text = _extract_text(response)
        if not text.strip():
            raise LLMCallFailed(f"{self.model} returned an empty completion")

        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=text.strip(),
            model=self.model,
            latency_ms=latency_ms,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
        )

    async def _call_with_retry(
        self, messages: Sequence[dict[str, str]], temperature: float, max_tokens: int | None
    ) -> Any:
        import litellm

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "temperature": temperature,
            "timeout": TIMEOUT_SECONDS,
        }
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._api_base:
            kwargs["api_base"] = self._api_base
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        last_error: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return await litellm.acompletion(**kwargs)
            except Exception as exc:  # provider/transport errors are all retryable
                last_error = exc
                if attempt == MAX_ATTEMPTS:
                    break
                # Base 2, not 1: the free Gemini tier answers a 429 with a per-minute window,
                # and a sub-second retry just spends the next quota unit on the same failure.
                delay = BACKOFF_BASE_SECONDS * 2 ** (attempt - 1)
                log.warning(
                    "llm_call_retry",
                    model=self.model,
                    attempt=attempt,
                    max_attempts=MAX_ATTEMPTS,
                    delay_seconds=delay,
                    error=str(exc),
                )
                await asyncio.sleep(delay)

        raise LLMCallFailed(
            f"completion failed after {MAX_ATTEMPTS} attempts ({self.model}): {last_error}"
        ) from last_error


def _extract_text(response: object) -> str:
    """Pull the message content out of a LiteLLM response without trusting its shape.

    LiteLLM normalises providers onto the OpenAI response object, but a blocked or truncated
    Gemini response can arrive with no `choices` at all. Reading through it defensively turns
    that into an LLMCallFailed with the model name instead of an IndexError inside a pipeline.
    """
    choices = list(getattr(response, "choices", []) or [])
    if not choices:
        raise LLMCallFailed(
            "provider returned no choices — the response was blocked, or the request was "
            f"rejected: {response!r}"[:500]
        )
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    return content or ""


def get_llm_client(settings: Settings | None = None, *, model: str | None = None) -> LLMClient:
    """Construct the configured client. Callers depend on the protocol, not the class."""
    return LiteLLMClient(settings, model=model)
