# Progress log

One entry per phase: what was built, the evidence the Definition of Done was met, and anything
that deviated from PLAN.md. Decisions with trade-offs live in `docs/adr/` — this file records
what happened, not why a design was chosen.

---

## Phase 0 — Lock the scope + skeleton ✅

**Completed** 2026-08-09 · commits `2a86836`, `2a9b4d9`

Human gate answered and recorded in [ADR-0001](adr/0001-scope-va-data-boundary.md): Gemini API
approved for document data, 8 Vietnamese HR PDFs accepted as the v1 corpus, golden set owned by a
human other than the agent.

Built: `.gitignore`, `README.md`, `docs/architecture.md` with the phase → directory map,
`docs/adr/0000-template.md`, ADR-0001, and [ADR-0002](adr/0002-tech-stack-resolution.md).

**Definition of Done** — all 5 questions answered in ADR-0001; `data/raw/HR_pdfs/` holds 8 real
documents, verified text-based with PyMuPDF (2020 characters off page 1, diacritics intact).

### Deviations

- **Removed 73 zero-byte `.py` files.** The repository arrived with the entire tree scaffolded
  ahead of time, including Phase 6+ files. This contradicted the scaffolding rule in both CLAUDE.md
  and PLAN.md. Directories now hold a `.gitkeep` until their phase arrives.
- **Wrote ADR-0002, which PLAN.md did not ask for.** Three sources specified three different
  stacks and the embedding dimension is baked into the first migration, so the conflict had to be
  resolved before Phase 1 rather than discovered during it.
- **CLAUDE.md §3 is now partly superseded** by ADR-0002 (embedding dimension 768 not 1536, Gemini
  not OpenAI/Anthropic, Python 3.12 not 3.11). CLAUDE.md itself was left unedited — it is the
  user's context file. Read ADR-0002 alongside it.

### Open

- **The golden-set owner has not been named.** Phase 3 is a hard block; it must be resolved before
  Phase 2 finishes or the project stalls with nothing to work on.
- The 8-document corpus makes retrieval metrics optimistic — fewer distractor chunks than
  production. Relative comparison between pipelines stays valid, absolute numbers do not.

---

## Phase 1 — Infrastructure + schema ✅

**Completed** 2026-08-09

Built: `docker-compose.yml` (pgvector/pg16, named volume, healthcheck) · root `.env.example` and
`.env` · `backend/pyproject.toml` (Phase 1–2 dependencies only) · root `Makefile` ·
`app/core/{config,logging,exceptions}.py` · `app/db/{base,session}.py` · the three models ·
`alembic/` with the async template and the initial migration · `app/main.py`,
`app/api/v1/router.py`, `app/api/v1/routes/health.py` · `tests/unit/test_config.py`.

**Definition of Done** — `make up && make migrate` run clean;
`curl localhost:8000/api/v1/health` → `200 {"status":"ok","database":"up"}`; `\dt` shows
`documents`, `chunks`, `queries` (plus `alembic_version`); `\di` shows
`ix_chunks_embedding_hnsw` as `hnsw (embedding vector_cosine_ops) WITH (m='16',
ef_construction='64')`; `embedding` is `vector(768)`.

Verified beyond the stated bar:

| Check | Result |
|---|---|
| `alembic check` | no drift between models and schema |
| `alembic downgrade base` → `upgrade head` | 4 tables → 1 → 4; migration is reversible |
| `/health` with postgres stopped | `503 {"status":"degraded","database":"down"}` |
| `/health` after postgres restarted | back to 200 without an API restart (`pool_pre_ping`) |
| `make lint` | ruff + mypy clean, 18 source files |
| `make test` | 9 passed |

### Decisions made while building

- **One `.env` at the repo root**, read by both docker compose and the backend. `Settings`
  resolves the path from `__file__`, not the working directory, because the Makefile runs commands
  from `backend/` while compose runs from the root. The API keys that were in `backend/.env` were
  carried over.
- **The vector dimension is written in three places** — `.env` (`EMBEDDING_DIMENSIONS`),
  `app/models/chunk.py` (`EMBEDDING_DIM`), and the migration. A column type cannot be resolved
  from config at migration time, so the duplication is deliberate; each site carries a comment
  pointing at the other two.
- **`alembic/env.py` excludes `ix_chunks_embedding_hnsw` from autogenerate.** Alembic cannot render
  a vector opclass, so every autogenerate run would otherwise emit a spurious drop of the index.
- **Logging routes stdlib records through the same JSON renderer** (`ProcessorFormatter` plus
  clearing uvicorn's own handlers). Without it, uvicorn's output bypasses the formatter and stdout
  is two interleaved formats rather than one parseable stream.
- **`Query.retrieved_chunk_ids` has no foreign key.** A re-ingest deletes chunks, and losing the
  record of what was retrieved is worse than holding ids that no longer resolve.
- **`documents.status` is a `CHECK` constraint, not a native PG enum** — adding a status later is a
  constraint swap instead of `ALTER TYPE`.

### Deviations

- **`app/api/v1/routes/health.py` carries a local session dependency.** `app/api/deps.py` with the
  real request-scoped `get_db` belongs to Phase 5; the route needs a session before then. Delete
  `_session` when `deps.py` lands.
- **The Makefile has more targets than PLAN.md listed** — `install`, `logs`, `psql`, `revision`,
  `fmt` alongside the required `up`/`down`/`migrate`/`test`/`lint`/`api`. All are thin wrappers.
- **Phase 1 has a unit test, which PLAN.md did not ask for.** `PipelineConfig` is serialized into
  every `results/*.json`, so its serialization is load-bearing; `make test` also exited 5 with zero
  tests collected, which would have read as a broken target for the rest of Phase 1.

### Open

- **`backend/.env` is now redundant** and still on disk holding a duplicate of both API keys.
  Deleting it was blocked by a permission prompt — please remove it. It is gitignored, so it was
  never committed.
- `POSTGRES_PASSWORD=rag` is a local-development default. It needs changing before this runs
  anywhere other than a laptop.

---

## Phase 2 — Synchronous ingest ⬜ not started
