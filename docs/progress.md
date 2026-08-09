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

## Phase 2 — Synchronous ingest 🟡 built, awaiting the human eyeball check

**Built** 2026-08-09

`llm/rag/loaders.py` (PDF via PyMuPDF with real page numbers, DOCX via python-docx with none) ·
`llm/rag/chunking.py` · `llm/rag/embedder.py` · `llm/rag/vector_store.py` ·
`repositories/document_repo.py` · `services/ingest_service.py` · `scripts/ingest_corpus.py` ·
[ADR-0003](adr/0003-vector-store-over-repository.md) · `tests/unit/test_chunking.py` (17 tests) ·
`tests/integration/{conftest,test_ingest}.py` (7 tests) · `make ingest`.

**Corpus ingested:** 8 documents, all `done`, **34 chunks**, zero null embeddings, ~9s wall clock.
A second `make ingest` reports `ingested 0 · skipped 8 · failed 0` with the chunk count still 34 —
idempotency on `file_hash` holds.

| Check | Result |
|---|---|
| `SELECT status, count(*) FROM documents GROUP BY status` | `done: 8` |
| `SELECT count(*) FROM chunks` | `34` |
| chunks with `embedding IS NULL` | `0` |
| returned embedding length | 768, matching `vector(768)` |
| `make lint` | ruff + mypy clean, 28 source files |
| `make test` | 31 passed |
| `alembic check` | still no drift after the import fix below |

### ⛔ Definition of Done is NOT met yet — it needs you

PLAN.md makes the sign-off a human eyeball check, and CLAUDE.md forbids the agent from making it.
Five random chunks were pulled and printed for review; **a person still has to confirm** no lost
diacritics, no header/footer contamination, no half-words, correct `page_no`. To re-draw a sample:

```sql
SELECT content, page_no FROM chunks ORDER BY random() LIMIT 5;
```

### What the sample already showed

- **Diacritics and `page_no` were correct** in all five chunks; no chunk mixed two pages.
- **`05_bao_mat_thong_tin_va_thiet_bi.pdf` p.2 contains `ảnh hưởng xếp loạ`** — a word truncated
  **in the PDF's own text layer**, confirmed by reading the raw PyMuPDF extraction. Not a chunking
  bug, and not fixable downstream. The source document needs regenerating.
- **Tables flatten into a linear stream of cells.** The same page's violation-severity table
  becomes `Mức độ / Ví dụ / Hình thức xử lý / Nhẹ / …`, losing which example belongs to which
  severity. Naive text extraction does this to every table. Questions whose answer lives in a
  table cell are the ones most likely to fail in Phase 4 — worth a few `multi_hop` golden-set
  questions aimed straight at them.

### Decisions made while building

- **A chunk never spans a page break**, so every `page_no` is exact rather than inferred. The cost
  is that a sentence crossing a page boundary becomes two partial chunks. With 2-page documents
  averaging 4 chunks each, that boundary is hit once per document.
- **Boundary snapping order: paragraph → sentence → line → space**, searching back up to a quarter
  of the window. The sentence regex requires whitespace after the terminator, which is what keeps
  clause numbers like `6.3` from being split down the middle.
- **`token_count` is tiktoken `cl100k_base`, an approximation.** Gemini publishes no local
  tokenizer. Nothing branches on the number; it is for inspection.
- **Three commits per document, not one** — `processing` lands first so a crash mid-embed leaves a
  record; the chunk rewrite and `status=done` commit together; a failure rolls back and then writes
  `status=failed` in its own transaction, since a rolled-back one cannot record why it rolled back.
- **Ingest is sequential.** The embedding provider is the bottleneck and is rate-limited;
  concurrency here buys latency and pays in 429s.
- **Integration tests run against a `rag_test` database**, created on demand from the models and
  truncated after each test. Sharing the dev database would have meant tests renumbering the very
  chunk ids Phase 3 is about to reference. No mocks: real Postgres, real embedding calls; the
  suite skips with a reason when either is unavailable.
- **No header/footer stripping.** All 16 pages were checked for repeated running heads: there are
  none. The only repeated line is each document's title on its own page 1, which is real content.
  A stripping heuristic here would only be a way to delete content by accident.

### Deviations

- **Fixed a latent circular import in Phase 1 code.** `app/db/base.py` imported every model at the
  bottom while each model imported `Base` from it, so whether an entrypoint worked depended on
  which side it reached first. Tests and alembic happened to import `app.db.base` first; the very
  first run of `make ingest` imported `app.models` first and died with an `ImportError`. `base.py`
  is now a leaf, and **importing `app.models` is what completes the metadata** — `alembic/env.py`
  and the test schema builder do that explicitly. `alembic check` still reports no drift.
- **`data/samples/04_nghi_phep_va_lam_viec_tu_xa.pdf`** is a copy of a real corpus document, per
  the handoff note. Nothing was generated.
- **`make ingest` takes `P=` and `FORCE=1`**, beyond the bare target CLAUDE.md §7 lists.
- **The integration suite has 7 tests, not the 1 PLAN.md asked for.** Idempotency alone would not
  have caught a wrong-length embedding, a lost `page_no`, or a failed document taking the whole run
  down with it.

### Open

- **The golden-set owner is still unnamed** — carried over from Phase 0 and now urgent. Phase 3 is
  the next phase and it is a hard human gate; the agent must not write the questions
  (CLAUDE.md 5.6). Nothing else can proceed past Phase 2 until someone is named.
- **`backend/.env` still exists** with a duplicate of both API keys; deleting it was blocked by a
  permission prompt again. The live config is the repo-root `.env`. Gitignored, never committed.
- **Chunk ids are assigned on insert, so any `--force` re-ingest renumbers them.** Phase 3's
  `relevant_chunk_ids` will point at the wrong text the moment someone re-ingests. Freeze the
  corpus before the golden set is written, or plan to regenerate it.
- Tables lose their structure at extraction (above). If Phase 4 shows table questions failing, the
  fix is a structured extractor, not a bigger `top_k` — and it needs its own ADR.
- The staged deletion of `backend/eval/*/.gitkeep` and `results/.gitkeep` predates this phase and
  was left alone; those are Phase 3–4 directories. Commit or restore it as you see fit.

---

## Phase 2 — original handoff notes

### Handoff — read this before starting

State: working tree clean at `42c50dd`, the `rag_postgres` container is up and migrated. Bring the
environment back with `make up && make migrate`, and confirm with
`curl localhost:8000/api/v1/health` → `{"status":"ok","database":"up"}`.

Blocking on a human, both carried over from earlier phases:

1. **Nobody is named as the golden-set author.** Phase 3 is a hard gate — the agent must not write
   the questions (CLAUDE.md 5.6). Resolve this while Phase 2 is in flight, or the project stalls
   the moment Phase 2 ends.
2. **`backend/.env` still exists** with a duplicate of both API keys. The live config is the
   repo-root `.env`. Deleting the stale one was blocked by a permission prompt.

What Phase 2 builds, per PLAN.md: `llm/rag/chunking.py` (800/100, character split preferring
sentence/paragraph boundaries, `page_no` preserved) · `llm/rag/embedder.py` (`Embedder` protocol +
implementation, batches of 32, exponential backoff, token counting) · `llm/rag/vector_store.py`
(`VectorStore` protocol — `add_chunks`, `search`, `delete_by_document` — pgvector only) ·
`repositories/document_repo.py` (all SQL lives here) · `services/ingest_service.py` (hash → skip
unless `--force` → load → chunk → embed → single transaction → `status=done`; on failure rollback,
`status=failed` + `error_message`, log, continue to the next file; **no fastapi import**) ·
loaders for PDF and DOCX · `scripts/ingest_corpus.py` · `tests/unit/test_chunking.py` ·
`tests/integration/test_ingest.py`.

Traps found while building Phases 0–1 that Phase 2 will hit:

- **`gemini-embedding-001` returns 3072 dimensions by default.** The schema is `vector(768)`, so
  the embedder must explicitly request 768 (`dimensions=768` through LiteLLM) or every insert will
  fail on dimension mismatch. Verify the returned vector length before the first bulk ingest.
- **`data/samples/` is empty**, so the integration test has no fixture. Copy one of the 8 real PDFs
  from `data/raw/HR_pdfs/` into it — do not generate a sample PDF (CLAUDE.md 5.5). `data/samples/`
  is deliberately un-ignored in `.gitignore` while `data/raw/*` is ignored.
- **DOCX has no real page numbers**; `chunks.page_no` is nullable for exactly this reason. State the
  limitation in the loader docstring. The corpus is PDF-only, so this path is untested by the corpus.
- **`app/llm/`, `app/llm/rag/`, `app/repositories/` and `app/services/` have no `__init__.py`** —
  they were removed to keep Phase 2+ directories free of empty `.py` files. Add them when the
  modules land.
- **`ix_chunks_document_id_chunk_index` is unique on `(document_id, chunk_index)`.** A re-ingest
  that does not delete old chunks first will violate it — which is the constraint doing its job.
- Ingest must be idempotent on `file_hash`; `documents.file_hash` is already `UNIQUE`.

Definition of Done is a **mandatory human eyeball check**: 5 random chunks read by a person, who
confirms no lost Vietnamese diacritics, no header/footer contamination, no words cut in half, and
correct `page_no`. The agent cannot sign this off.
