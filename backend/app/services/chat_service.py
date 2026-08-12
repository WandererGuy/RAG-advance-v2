"""Ask a question, record it, return a DTO. No FastAPI import, ever (CLAUDE.md 4.2).

The pipeline is reached through `build_pipeline(settings.pipeline_name, ...)` and never by
importing `NaiveV1` — that indirection is the entire point of the registry (CLAUDE.md 4.1), and
it is what makes serving a Phase 6 pipeline an `.env` change rather than a code change.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.llm.rag.pipelines.base import RAGAnswer, RAGPipeline
from app.llm.rag.pipelines.registry import build_pipeline
from app.repositories.query_repo import QueryRepository
from app.schemas.chat import ChatResponse

log = get_logger(__name__)


async def answer_question(
    session: AsyncSession,
    question: str,
    *,
    settings: Settings | None = None,
    pipeline: RAGPipeline | None = None,
) -> ChatResponse:
    """Answer one question and persist it to `queries`.

    `pipeline` is injectable so a test can drive this with a double; production passes None and
    gets the configured pipeline from the registry.
    """
    settings = settings or get_settings()
    pipeline = pipeline or build_pipeline(settings.pipeline_name, session)
    question = question.strip()

    bound = log.bind(pipeline=pipeline.name)
    answer = await pipeline.answer(question)

    query_id = await _record(session, answer)
    bound.info(
        "chat_answered",
        query_id=query_id,
        refused=answer.refused,
        chunk_ids=answer.chunk_ids,
        citations=len(answer.citations),
        unsupported_citations=sum(1 for c in answer.citations if not c.supported),
        latency_ms=answer.latency_ms,
    )
    return ChatResponse.from_answer(answer, query_id=query_id)


async def _record(session: AsyncSession, answer: RAGAnswer) -> int | None:
    """Write the query row. A failure here must not cost the user their answer.

    `queries` is an observability record, not part of the answer. If the INSERT fails the
    answer has already been produced and paid for, so it is returned with `query_id=None` and
    the failure goes to the log — losing the trace is bad, losing the answer is worse.
    """
    try:
        row = await QueryRepository(session).record(
            question=answer.question,
            answer=answer.answer,
            pipeline_name=answer.pipeline_name,
            retrieved_chunk_ids=answer.chunk_ids,
            latency_ms=answer.latency_ms,
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        log.error("chat_query_not_recorded", error=str(exc), exc_info=True)
        return None
    return row.id
