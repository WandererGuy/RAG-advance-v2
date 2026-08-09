"""GET /health — the only route in Phase 1."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_sessionmaker

router = APIRouter(tags=["health"])
log = get_logger(__name__)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["up", "down"]


async def _session() -> AsyncIterator[AsyncSession]:
    """Local session dependency.

    Phase 5 introduces app/api/deps.py with the real request-scoped get_db; until then this
    route needs a session and there is nowhere else for it to come from. Read-only, so it
    never commits.
    """
    async with get_sessionmaker()() as session:
        yield session


@router.get("/health", response_model=HealthResponse)
async def health(session: Annotated[AsyncSession, Depends(_session)]) -> JSONResponse:
    """Liveness plus a real database round-trip.

    A health check that does not touch the database would report ok while every request
    fails, which is the failure mode this endpoint exists to catch.
    """
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        log.error("health_check_failed", error=str(exc), exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=HealthResponse(status="degraded", database="down").model_dump(),
        )
    return JSONResponse(content=HealthResponse(status="ok", database="up").model_dump())
