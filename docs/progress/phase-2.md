## Phase 2 — Synchronous ingest 🟡 built, awaiting the human eyeball check

**Built** 2026-08-09

`llm/rag/loaders.py` (PDF via PyMuPDF with real page numbers, DOCX via python-docx with none) ·
`llm/rag/chunking.py` · `llm/rag/embedder.py` · `llm/rag/vector_store.py` ·
`repositories/document_repo.py` · `services/ingest_service.py` · `scripts/ingest_corpus.py` ·
[ADR-0003](../adr/0003-vector-store-over-repository.md) · `tests/unit/test_chunking.py` (17 tests) ·
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

### What you can do after this phase

**Available:** the corpus is in the database — 8 documents, 34 chunks, every chunk carrying a
768-dim embedding and an exact `page_no`. Everything from Phase 1 still applies. There is still
**no retrieval and no question answering**: `retrievers/`, `pipelines/`, `eval/` and the chat route
are Phases 3–5. `VectorStore.search` exists but nothing calls it.

**Commands that work at this point:**

```bash
make up && make migrate                    # bring the environment back
make ingest                                # idempotent: re-running skips all 8
make ingest P=../data/samples              # ingest one directory or one file
make ingest FORCE=1                        # rebuild chunks — RENUMBERS chunk ids, see below
make test                                  # 31 passed (unit + integration against rag_test)
make lint                                  # 28 source files, clean
make psql
```

Useful inside `make psql`:

```sql
SELECT filename, status, page_count FROM documents ORDER BY filename;
SELECT count(*) FROM chunks;                      -- 34
SELECT count(*) FROM chunks WHERE embedding IS NULL;   -- must stay 0
SELECT content, page_no FROM chunks ORDER BY random() LIMIT 5;   -- the sign-off sample
SELECT document_id, page_no, left(content, 80) FROM chunks ORDER BY document_id, chunk_index;
```

**Technical, possible now:** read the actual chunk text and judge chunk quality before any
retrieval number exists to argue about; measure how the 800/100 split lands on these specific
documents (34 chunks over 16 pages) and note where a clause got cut; ingest a DOCX to exercise the
untested loader path — the corpus is PDF-only; delete a document row and re-ingest to watch
idempotency and the failure path; hand-write a `search` call in a scratch script if you want to see
what dense retrieval will return in Phase 4.

**Non-technical, possible now:** **do the Phase 2 sign-off** — read 5 random chunks and confirm
diacritics, page numbers, no half-words, no header/footer junk; that single act unblocks the phase.
**Name the golden-set author** — nothing past here moves without it. Regenerate
`05_bao_mat_thong_tin_va_thiet_bi.pdf`, whose own text layer truncates a word. Decide whether the
corpus is frozen; from Phase 3 on, adding or re-ingesting documents costs real rework.

**Notice:** `make ingest FORCE=1` deletes and reinserts chunks, which **assigns new chunk ids** —
run it freely now, never after the golden set is written. Ingest is sequential and calls a
rate-limited external API; ~9s for 8 documents, and a much larger corpus will be slow, not broken.
Table content is flattened into a stream of cells at extraction, so the answer to a
"which penalty applies to X" question may no longer be adjacent to X. A failed document does not
stop the run — check `SELECT filename, error_message FROM documents WHERE status = 'failed'` rather
than trusting a zero exit code.

**For the next phase (3 — golden set):** freeze the corpus first, then take chunk ids from a
database that will not be re-ingested. Aim some `multi_hop` questions at the flattened tables; they
are the ones most likely to fail in Phase 4 and the most informative when they do. Do not expect an
answer to anything that depends on the truncated word in document 05. The agent must not write the
questions (CLAUDE.md 5.6).

---

## Handoff notes written before this phase — superseded, kept for the record

Everything below was written by the previous session as instructions for building Phase 2. The
traps it lists were all real and all hit. Read the sections above for what actually happened.

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
