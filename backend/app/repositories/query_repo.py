"""All SQL for the `queries` table. Like DocumentRepository, it never commits.

`queries` is the only record of what users actually ask (PLAN.md Phase 1), so the golden set can
later grow from real traffic instead of imagination. Nothing wrote to it before Phase 5.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Query


class QueryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        question: str,
        answer: str | None,
        pipeline_name: str,
        retrieved_chunk_ids: Sequence[int],
        latency_ms: int | None,
    ) -> Query:
        """Write one asked question. `answer=None` records a question that failed to answer.

        Flush, not commit — the caller owns the transaction, and it needs the generated id to
        put in the response.
        """
        row = Query(
            question=question,
            answer=answer,
            pipeline_name=pipeline_name,
            retrieved_chunk_ids=list(retrieved_chunk_ids),
            latency_ms=latency_ms,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def recent(self, limit: int = 50) -> list[Query]:
        """Newest first. For inspecting a demo session's real traffic."""
        result = await self._session.execute(
            select(Query).order_by(desc(Query.created_at), desc(Query.id)).limit(limit)
        )
        return list(result.scalars().all())

    async def count(self) -> int:
        result = await self._session.execute(select(func.count()).select_from(Query))
        return int(result.scalar_one())
