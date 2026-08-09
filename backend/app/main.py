from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import dispose_engine

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    log.info(
        "api_startup",
        llm_model=settings.llm_model,
        embedding_model=settings.embedding_model,
        embedding_dimensions=settings.embedding_dimensions,
    )
    yield
    await dispose_engine()
    log.info("api_shutdown")


app = FastAPI(
    title="rag-chatbot",
    version="0.1.0",
    summary="Q&A over internal company documents, with citations",
    lifespan=lifespan,
)
app.include_router(api_router)
