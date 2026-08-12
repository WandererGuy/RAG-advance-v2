"""Keyword retrieval against a real Postgres. The half of `bm25` that unit tests cannot reach.

Everything interesting here is Postgres behaviour, not Python: whether `simple` preserves
Vietnamese diacritics, whether OR-semantics actually returns rows where AND returns none, and
whether `ts_rank_cd` ranks the chunk a human would pick. Asserting those against a fake would
assert nothing (CLAUDE.md 5.5), so these use real rows in the real test database.

No embedding calls: chunks are inserted with a NULL embedding, because keyword retrieval never
touches the vector column. That makes this file cheap enough to run on every `make test`.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.rag.retrievers.bm25 import BM25Retriever
from app.models import DocumentStatus
from app.repositories.document_repo import DocumentRepository

# Sentences lifted in shape (not verbatim) from the HR corpus: a per-diem policy, a leave
# policy, and one chunk sharing a common word with both so ranking has something to separate.
CORPUS = [
    "Nhân viên đi công tác được thanh toán phụ cấp công tác phí 300.000 đồng một ngày.",
    "Nhân viên chính thức được 15 ngày phép năm, cộng thêm 01 ngày sau mỗi 03 năm làm việc.",
    "Nhân viên phải chấm công đầy đủ mỗi ngày làm việc tại văn phòng.",
]


@pytest.fixture
async def corpus(session: AsyncSession) -> list[int]:
    """Three chunks in one document. Returns their ids in CORPUS order."""
    repo = DocumentRepository(session)
    document = await repo.create(
        filename="test_hr.pdf",
        source_path="/tmp/test_hr.pdf",
        file_hash="f" * 64,
        mime_type="application/pdf",
        status=DocumentStatus.DONE,
    )
    await repo.add_chunks(
        document.id,
        [
            {
                "content": content,
                "page_no": 1,
                "chunk_index": index,
                "token_count": None,
                "embedding": None,
            }
            for index, content in enumerate(CORPUS)
        ],
    )
    await session.flush()
    rows = sorted(await repo.all_chunks_for_lock(), key=lambda r: r.chunk_index)
    return [row.chunk_id for row in rows]


class TestKeywordRetrieval:
    async def test_finds_the_chunk_a_human_would_pick(
        self, session: AsyncSession, corpus: list[int]
    ) -> None:
        hits = await BM25Retriever(DocumentRepository(session)).retrieve(
            "Phụ cấp công tác phí là bao nhiêu một ngày?", 3
        )
        assert hits, "a question full of corpus terms must match something"
        assert hits[0].chunk_id == corpus[0]

    async def test_returns_rows_where_and_semantics_would_return_none(
        self, session: AsyncSession, corpus: list[int]
    ) -> None:
        # The reason build_tsquery ORs. Under AND, one absent term ("tỉnh") empties the result;
        # this question contains several words no chunk has.
        hits = await BM25Retriever(DocumentRepository(session)).retrieve(
            "Nhân viên đi công tác tỉnh xa được thanh toán phụ cấp thế nào?", 3
        )
        assert hits[0].chunk_id == corpus[0]

    async def test_diacritics_are_significant(
        self, session: AsyncSession, corpus: list[int]
    ) -> None:
        # `simple` case-folds but does not strip diacritics, so "phép" (leave) and "phí" (fee)
        # are different lexemes. If this ever fails, the configuration has drifted to one that
        # normalises Vietnamese away — and the two policies become indistinguishable.
        repo = DocumentRepository(session)
        leave = await BM25Retriever(repo).retrieve("ngày phép năm", 3)
        assert leave[0].chunk_id == corpus[1]

    async def test_ranking_is_ordered_best_first(
        self, session: AsyncSession, corpus: list[int]
    ) -> None:
        repo = DocumentRepository(session)
        hits = await BM25Retriever(repo).retrieve("phụ cấp công tác phí", 3)
        assert [h.rank for h in hits] == list(range(1, len(hits) + 1))
        assert all(
            earlier.score >= later.score for earlier, later in zip(hits, hits[1:], strict=False)
        )

    async def test_respects_k(self, session: AsyncSession, corpus: list[int]) -> None:
        hits = await BM25Retriever(DocumentRepository(session)).retrieve("nhân viên ngày", 2)
        assert len(hits) == 2

    async def test_a_question_of_only_stopwords_returns_nothing(
        self, session: AsyncSession, corpus: list[int]
    ) -> None:
        # Not an error: there is no lexical anchor to match on, and HybridRetriever falls
        # through to dense alone.
        assert await BM25Retriever(DocumentRepository(session)).retrieve("Cái đó là gì?", 3) == []

    async def test_a_question_matching_nothing_returns_nothing(
        self, session: AsyncSession, corpus: list[int]
    ) -> None:
        hits = await BM25Retriever(DocumentRepository(session)).retrieve("blockchain kubernetes", 3)
        assert hits == []

    async def test_an_apostrophe_does_not_break_the_query(
        self, session: AsyncSession, corpus: list[int]
    ) -> None:
        # A syntax error here would be a 500 on the serving path, not a bad ranking.
        await BM25Retriever(DocumentRepository(session)).retrieve("nhân's viên O'Brien", 3)

    async def test_carries_the_fields_a_citation_needs(
        self, session: AsyncSession, corpus: list[int]
    ) -> None:
        hit = (await BM25Retriever(DocumentRepository(session)).retrieve("phụ cấp công tác", 1))[0]
        assert hit.filename == "test_hr.pdf"
        assert hit.page_no == 1
        assert hit.retriever == "bm25"
        assert hit.content
