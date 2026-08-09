# ADR-0003 — VectorStore is an adapter over the repository, not a second SQL layer

- **Date:** 2026-08-09
- **Status:** accepted

## Context

Two project rules collided in Phase 2.

PLAN.md asks for `app/llm/rag/vector_store.py` holding a `VectorStore` protocol
(`add_chunks`, `search`, `delete_by_document`) with a pgvector implementation. Written the
obvious way, that implementation takes a session and issues `INSERT`, `DELETE` and an
`ORDER BY embedding <=> :q` query.

CLAUDE.md 4.2 says only `repositories/` may write queries or use a session, and PLAN.md
separately asks `repositories/document_repo.py` to hold "CRUD for documents + chunks; **all SQL
lives here**". Both files cannot own the chunk SQL.

Leaving it unresolved would have meant two modules writing to `chunks` — the exact split where
one of them forgets that `ix_chunks_document_id_chunk_index` is unique and a re-ingest starts
failing on the second run.

## Decision

`DocumentRepository` owns every statement, including the cosine top-k. `PgVectorStore` holds no
SQL: it takes a repository, maps `TextChunk` + embedding pairs onto insert rows, and delegates.
The `VectorStore` protocol stays exactly as PLAN.md specifies, because Phase 4's dense retriever
is supposed to program against that seam rather than against the repository.

Rejected alternatives:

- **Put the SQL in `vector_store.py` and treat it as an honorary repository.** Cheapest to
  write, and it breaks the layering rule for every reader who comes after.
- **Drop `vector_store.py` and let the retriever use the repository directly.** Honest, but it
  deletes the seam that Phase 6 needs: `hybrid.py` and `bm25.py` are supposed to be swapped in
  behind an interface, and a retriever holding a repository knows too much to be swapped.

## Consequences

Easy: one place to change when the chunk schema moves. The retriever still sees the interface
PLAN.md promised it. `PgVectorStore` is trivial enough to read in one sitting, which is what a
layer that only forwards should be.

Hard: one extra hop for anybody tracing a query from the pipeline down to SQL, and a temptation
to add a method to the store that does not correspond to anything the repository exposes. Resist
it — a store method that needs new SQL means the repository needs a new method first.

Reversing is cheap while `PgVectorStore` remains a forwarder: inline the three methods into the
repository and update Phase 4's retriever construction. It stops being cheap once a second
`VectorStore` implementation exists, which for this project it never will — CLAUDE.md scopes
Qdrant out permanently.
