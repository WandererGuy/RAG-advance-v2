"""GIN index on to_tsvector('simple', content) for the Phase 6 keyword retriever

Revision ID: 8b1c4e7a92d5
Revises: 42f575d6dccb
Create Date: 2026-08-12

Index-only. No column is added, no row is touched, no id is reassigned — so this cannot
invalidate `relevant_chunk_ids` in the golden set or the digest in `corpus.lock.json`
(ADR-0005). Running it is not a corpus change.

**`simple`, not `english`.** Postgres 16 ships no Vietnamese text-search configuration, and
`english` would stem Vietnamese as if it were English — it drops `được`/`nghỉ` as stopwords and
mangles what is left. `simple` only case-folds and splits on non-word characters, which is the
honest primitive for a language whose morphology Postgres does not model. The same reasoning is
already written into `DocumentRepository.search_text`, which is why that one uses ILIKE.

The expression here must stay character-identical to the one the retriever queries with, or the
planner silently falls back to a sequential scan: an expression index is only used for the exact
expression it was built on. It is written once in `app/llm/rag/retrievers/bm25.py` as
`TSVECTOR_EXPR` and both sides read it from there.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "8b1c4e7a92d5"
down_revision: str | Sequence[str] | None = "42f575d6dccb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_chunks_content_tsv_gin ON chunks "
        "USING gin (to_tsvector('simple', content))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_content_tsv_gin")
