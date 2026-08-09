# ADR-0002 — Resolving the stack conflict between CLAUDE.md, PLAN.md and .env

- **Date:** 2026-08-09
- **Status:** accepted

## Context

Three sources in the repository specified three different stacks, and Phase 1 cannot start without
picking one — the embedding dimension is baked into the first migration as `vector(N)`, and getting
it wrong means a full re-ingest.

| | CLAUDE.md §3 ("decided") | PLAN.md L14 ("suggest") | `backend/.env` (as configured) |
|---|---|---|---|
| Python | 3.11 | 3.12 | — |
| Embedding | `text-embedding-3-small`, 1536 dim | from env | `gemini-embedding-001`, **768 dim** |
| LLM | `claude-sonnet-4-6` | from env | `gemini-2.5-flash` |
| DB access | SQLAlchemy 2.x + Alembic | asyncpg, async | — |
| Chunking | own code, 800/100 chars | Chonkie | — |
| Background jobs | none until after Phase 6 | Celery + Redis | — |
| Orchestration | none | LangChain + LangGraph | — |

CLAUDE.md called its table "decided", but `.env` is what a human actually configured with a working
key, and PLAN.md's own line says "suggest". So the sources rank: `.env` is ground truth for models,
CLAUDE.md is ground truth for architecture and scope, PLAN.md's stack line is advisory.

## Decision

**Models come from `.env`.** Gemini `gemini-2.5-flash` for generation, `gemini-embedding-001` at
**768 dimensions**. The `chunks.embedding` column is `vector(768)`. CLAUDE.md's 1536 is treated as
superseded — there is no OpenAI key in `.env`, so its number was aspirational.

**Python 3.12**, managed with `uv`. It is what is installed, and PLAN.md asks for it. Nothing in the
project needs 3.11.

**LiteLLM** as the provider wrapper inside `app/llm/client.py`. This satisfies PLAN.md's suggestion
while keeping the shape CLAUDE.md asks for: a single wrapper with retry and timeout. It also means
that reversing ADR-0001 (moving to self-hosted Ollama) is a change of two env vars rather than a
rewrite, which is the main reason to accept the dependency at all.

**PyMuPDF** for PDF loading. Not negotiable regardless of what else changes: accurate page numbers
are a product requirement, since every answer must cite `[filename, p.N]`, and PyMuPDF is the option
that gives real page boundaries.

**Sync SQLAlchemy 2.x** with the `psycopg` v3 driver, rejecting PLAN.md's asyncpg suggestion. The
two heaviest workloads are `scripts/ingest_corpus.py` and `eval/runner.py`, both of which are
sequential CLI processes where async buys nothing. `/chat` is dominated by time spent waiting on
Gemini, not on Postgres. Async sessions would make the repository layer harder to test and would put
`await` in every call path for no measured gain.

**Rejected for v1: Celery + Redis, LangChain, LangGraph, Chonkie.**

- Celery + Redis: CLAUDE.md explicitly locks `app/workers/` until after Phase 6, and v1 ingest is
  synchronous by design. Adding a broker now means operating two more services to run a CLI script.
  The trigger to revisit is stated in PLAN.md: uploads exceeding 30 seconds.
- Chonkie: Phase 2 needs character splitting at 800/100 with the page number carried through. That
  is a function, not a dependency, and writing it directly keeps `page_no` provenance under our own
  control — which is exactly the part that must not break, because it feeds the citations.
- LangChain / LangGraph: the project's own `RAGPipeline` protocol *is* the orchestration abstraction,
  and it is the unit that `eval/runner.py` measures. Introducing a second orchestration layer on top
  would put the thing being evaluated behind someone else's abstraction. Revisit if multi-turn plus
  function calling arrives after Phase 6, where a graph starts to earn its keep.

## Consequences

- `.env.example` documents Gemini variables plus `EMBEDDING_DIMENSIONS`; `PipelineConfig` carries
  `embedding_model` and `llm_model` so every `results/*.json` records which models produced it.
- Changing the embedding model or its dimension is a schema migration plus a full re-ingest plus a
  re-run of every pipeline. `EMBEDDING_DIMENSIONS` is read from config, but the migration hard-codes
  768 — Alembic cannot generate a dynamic column type, so the two must be changed together.
- Dependency count in Phases 1–2 stays small: fastapi, uvicorn, sqlalchemy, alembic, psycopg,
  pgvector, pydantic-settings, structlog, litellm, pymupdf, python-docx, tiktoken, pytest.
- The rejections above are recorded so Phase 6 does not relitigate them from scratch; each has a
  named trigger for revisiting, and reversing any one of them is additive rather than destructive.
