"""Request-scoped dependencies. The only place `routes/` gets a session or a pipeline.

`get_pipeline` reads the name from Settings and resolves it through the registry — it never
imports `NaiveV1`. That indirection is the point of the registry (CLAUDE.md 4.1): switching the
served pipeline to a Phase 6 one is an `.env` change, not a code change.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_sessionmaker

# Importing the package registers every pipeline as a side effect. Without it the registry is
# empty and `get_pipeline` would 500 on a name that is correctly configured.
import app.llm.rag.pipelines  # noqa: F401  isort: skip


async def get_db() -> AsyncIterator[AsyncSession]:
    """One session per request, rolled back on an unhandled error.

    No commit here: a service that writes decides when its write is final. Rolling back on the
    way out means a route that raised cannot leave a half-written transaction to be committed
    by whatever runs next on the same connection.
    """
    async with get_sessionmaker()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


DbSession = Annotated[AsyncSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]
