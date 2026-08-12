"""Smoke tests for the three endpoints, against a real Postgres.

No mocks (CLAUDE.md 5.5). `get_db` is overridden to point at the *test* database — that is
dependency injection, not a mock: the same session type, the same schema, the same SQL. The
chat tests additionally call the real provider and skip when there is no key.

The corpus here is whatever this test inserts, so `POST /chat` runs against an empty or tiny
corpus and the answer will usually be a refusal. That is the point: these tests prove the wiring
(route -> service -> pipeline -> repository -> `queries`), not answer quality. Answer quality is
measured by `eval/runner.py` against the frozen corpus and the golden set.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_db
from app.core.config import get_settings
from app.main import app
from app.repositories.query_repo import QueryRepository


@pytest_asyncio.fixture
async def client(
    sessionmaker_test: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    """The real app, with its session dependency bound to the test database."""

    async def _test_db() -> AsyncIterator[AsyncSession]:
        async with sessionmaker_test() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _test_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


async def test_health_reports_the_database_is_up(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "up"}


async def test_documents_is_empty_on_a_fresh_database(client: AsyncClient) -> None:
    response = await client.get("/api/v1/documents")
    assert response.status_code == 200
    assert response.json() == []


async def test_upload_rejects_an_unsupported_file_type(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/documents", files={"file": ("notes.txt", b"khong phai pdf")}
    )
    assert response.status_code == 415
    assert ".pdf" in response.json()["detail"]


async def test_upload_rejects_an_empty_file(client: AsyncClient) -> None:
    response = await client.post("/api/v1/documents", files={"file": ("empty.pdf", b"")})
    assert response.status_code == 422


async def test_upload_rejects_a_pdf_with_no_readable_text(client: AsyncClient) -> None:
    """A well-formed request whose file cannot be turned into chunks is a 422, with the reason.

    `%PDF-` with nothing behind it is the cheapest stand-in for the real case this guards —
    a scanned PDF, which has no text layer and is out of scope for v1.
    """
    response = await client.post(
        "/api/v1/documents", files={"file": ("scan.pdf", b"%PDF-1.4\nnot really a pdf")}
    )
    assert response.status_code == 422
    assert response.json()["detail"]


@pytest.mark.parametrize("question", ["", "   "])
async def test_chat_rejects_a_blank_question(client: AsyncClient, question: str) -> None:
    response = await client.post("/api/v1/chat", json={"question": question})
    assert response.status_code == 422


async def test_chat_answers_and_records_the_query(
    client: AsyncClient,
    sessionmaker_test: async_sessionmaker[AsyncSession],
    require_embedding_api: None,
) -> None:
    """The full path, on an empty corpus: the answer must be a refusal, and it must be logged.

    With no chunks in the database, retrieval returns nothing and `naive-v1` refuses without
    calling the LLM at all — but the *query* is still embedded, so this needs the embedding key
    and not the LLM one. That makes it the one end-to-end assertion that costs almost nothing
    and still proves route -> service -> pipeline -> `queries`.
    """
    question = "Chính sách nghỉ phép năm là bao nhiêu ngày?"
    response = await client.post("/api/v1/chat", json={"question": question})

    assert response.status_code == 200
    body = response.json()
    assert body["refused"] is True
    assert body["chunk_ids"] == []
    assert body["citations"] == []
    assert body["pipeline_name"] == get_settings().pipeline_name
    assert body["query_id"] is not None

    async with sessionmaker_test() as session:
        rows = await QueryRepository(session).recent()
    assert [row.question for row in rows] == [question]
    assert rows[0].pipeline_name == body["pipeline_name"]
    assert rows[0].retrieved_chunk_ids == []
