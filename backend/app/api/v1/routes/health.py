"""GET /health — liveness plus a real database round-trip."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import DbSession
from app.core.logging import get_logger

router = APIRouter(tags=["health"])
log = get_logger(__name__)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["up", "down"]


@router.get("/health", response_model=HealthResponse)
async def health(session: DbSession) -> JSONResponse:
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
