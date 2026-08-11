"""`@register("name")` + `get_pipeline("name")`. The registry is what makes the runner generic.

`chat_service.py` (Phase 5) and `eval/runner.py` both reach a pipeline only through here — never
by importing the class — so adding a Phase 6 pipeline is one new file plus one import in
`__init__`, and nothing else changes.

Two rules the registry enforces rather than documents:

* **A name is claimed once.** Re-registering a name would silently rebind it, and two results
  files would then describe two different pipelines under one name — exactly the comparability
  loss CLAUDE.md 4.1 freezes pipelines to prevent.
* **A pipeline's `name` attribute must equal the name it registered under.** They are written
  in two places and used in two places (`results/<name>.json` takes the registry key,
  `RAGAnswer.pipeline_name` takes the attribute), so a mismatch would put one pipeline's answers
  in another pipeline's file.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import PipelineConfig
from app.core.exceptions import PipelineNotFound
from app.llm.rag.pipelines.base import RAGPipeline

_REGISTRY: dict[str, type[RAGPipeline]] = {}

P = TypeVar("P", bound=type[RAGPipeline])


def register(name: str) -> Callable[[P], P]:
    """Class decorator claiming `name` for a pipeline."""

    def decorator(cls: P) -> P:
        if name in _REGISTRY and _REGISTRY[name] is not cls:
            raise ValueError(
                f"pipeline name {name!r} is already registered to "
                f"{_REGISTRY[name].__name__} — a name identifies one configuration forever"
            )
        declared = getattr(cls, "name", None)
        if declared != name:
            raise ValueError(
                f"{cls.__name__}.name is {declared!r} but it registers as {name!r} — "
                "results/<name>.json and RAGAnswer.pipeline_name would disagree"
            )
        _REGISTRY[name] = cls
        return cls

    return decorator


def get_pipeline(name: str) -> type[RAGPipeline]:
    """The registered class, or `PipelineNotFound` naming what is available."""
    try:
        return _REGISTRY[name]
    except KeyError:
        raise PipelineNotFound(name, available=list(_REGISTRY)) from None


def build_pipeline(
    name: str, session: AsyncSession, config: PipelineConfig | None = None
) -> RAGPipeline:
    """Construct a registered pipeline with its default dependencies.

    The dependencies are still injected through `__init__` (CLAUDE.md 4.3) — this only supplies
    the production ones, so a test can build the same class with a fake retriever and no
    database. The session is passed in rather than opened here: the caller owns the transaction.
    """
    cls = get_pipeline(name)
    build = getattr(cls, "build", None)
    if build is None:
        raise PipelineNotFound(
            f"{name} (registered, but has no build() classmethod to construct it)"
        )
    pipeline: RAGPipeline = build(session, config)
    return pipeline


def available() -> list[str]:
    """Every registered name, sorted. Used by `--pipeline` help and by error messages."""
    return sorted(_REGISTRY)
