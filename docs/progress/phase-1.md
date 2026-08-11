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

### What you can do after this phase

**Available:** a running database and a running API with exactly one route. There is still no
ingest, no retrieval and no chat — `scripts/` and `services/` are empty. The tables exist and are
empty.

**Commands that work at this point:**

```bash
cp .env.example .env      # then fill DEFAULT_LLM_API_KEY and EMBEDDING_API_KEY
make install              # uv sync, first run only
make up                   # postgres + pgvector, waits for the healthcheck
make migrate              # alembic upgrade head -> documents, chunks, queries
make api                  # uvicorn with reload, http://localhost:8000
curl localhost:8000/api/v1/health          # {"status":"ok","database":"up"}
open http://localhost:8000/docs            # FastAPI's generated docs
make psql                 # \dt  \di  \d chunks
make test                 # 9 passed
make lint                 # ruff + mypy
make fmt                  # format + autofix
make revision M="..."     # autogenerate a migration
make logs / make down     # the pgdata volume survives `down`
```

**Technical, possible now:** confirm the schema by eye (`\d chunks` should show
`embedding vector(768)` and `ix_chunks_embedding_hnsw`); prove the migration is reversible with
`alembic downgrade base && alembic upgrade head`; watch `/health` flip to `503 degraded` when you
`make down` and recover on its own once postgres is back; add a route or a model and let
`alembic check` tell you whether the schema drifted; write against `get_settings()` — every config
value in `.env.example` is already typed and validated.

**Non-technical, possible now:** demo that the stack stands up from a clean clone in four commands
— that is the whole point of this phase; hand the repo to a second person and see whether
`README.md` plus `.env.example` is enough for them to reach a green `/health`; decide the real
Postgres password if this will ever leave a laptop.

**Notice:** the two API keys are not exercised by anything yet, so a wrong key looks fine until the
first embedding call in Phase 2 — check them early. `make ingest` is listed in CLAUDE.md §7 but
does not exist until Phase 2. `docker compose down -v` (with `-v`) destroys the volume and means a
re-migrate and, later, a full re-ingest.

**For the next phase (2):** `app/db/base.py` importing every model at the bottom is a circular
import waiting to fire — it only worked because tests and alembic happened to import it first
(Phase 2 hit this on the very first `make ingest`). `gemini-embedding-001` returns 3072 dimensions
unless 768 is requested explicitly, and the column will reject it. `ix_chunks_document_id_chunk_index`
is unique on `(document_id, chunk_index)`, so a re-ingest must delete old chunks first.
`chunks.page_no` is nullable because DOCX has no page numbers.

### Open

- **`backend/.env` is now redundant** and still on disk holding a duplicate of both API keys.
  Deleting it was blocked by a permission prompt — please remove it. It is gitignored, so it was
  never committed.
- `POSTGRES_PASSWORD=rag` is a local-development default. It needs changing before this runs
  anywhere other than a laptop.
