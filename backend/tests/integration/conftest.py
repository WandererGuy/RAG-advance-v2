"""Integration fixtures: a real Postgres, in a database of its own.

Tests run against `<database>_test`, created on demand from the same models, never against the
development database. That isolation is not fastidiousness — a re-ingest deletes and rebuilds
chunks, so a test sharing the corpus database would renumber the very chunk ids Phase 3's
golden set is about to reference.

No mocks anywhere (CLAUDE.md 5.5): real Postgres, real pgvector, real embedding calls. When the
database or the API key is unavailable the tests skip with a reason rather than pretending.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# app.models is imported for its side effect: it registers all three tables on Base.metadata,
# without which create_all builds an empty schema. See app/db/base.py.
import app.models  # noqa: F401
from app.core.config import get_settings
from app.db.base import Base


def _test_database_url() -> str:
    """`rag` -> `rag_test`. Derived, not a new env var: one DATABASE_URL stays the source."""
    url = make_url(get_settings().database_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


async def _ensure_database() -> None:
    """CREATE DATABASE if it is not there yet.

    Connects to the `postgres` maintenance database because you cannot create a database from
    inside itself, and with AUTOCOMMIT because CREATE DATABASE cannot run in a transaction.
    """
    url = make_url(_test_database_url())
    admin_url = url.set(database="postgres").render_as_string(hide_password=False)
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with admin_engine.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
            )
            if not exists:
                await connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        await admin_engine.dispose()


@pytest_asyncio.fixture
async def sessionmaker_test() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A schema-fresh test database, torn down to empty tables after each test."""
    try:
        await _ensure_database()
    except Exception as exc:  # noqa: BLE001 - the reason is what makes the skip actionable
        pytest.skip(f"postgres unavailable ({type(exc).__name__}: {exc}) — run `make up`")

    engine = create_async_engine(_test_database_url())
    try:
        async with engine.begin() as connection:
            # The models declare vector columns and an HNSW index; both need the extension
            # in place before create_all emits their DDL.
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await connection.run_sync(Base.metadata.create_all)

        yield async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

        async with engine.begin() as connection:
            await connection.execute(text("TRUNCATE documents, chunks, queries RESTART IDENTITY"))
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def session(
    sessionmaker_test: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with sessionmaker_test() as session:
        yield session


@pytest.fixture
def require_embedding_api() -> None:
    """Skip when there is no key. These tests call the provider for real."""
    if not get_settings().embedding_api_key:
        pytest.skip("EMBEDDING_API_KEY is not set — ingest cannot embed without it")
