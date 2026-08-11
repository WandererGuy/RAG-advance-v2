# PLAN.md — Build roadmap for rag-chatbot

Read `CLAUDE.md` first. Work through it sequentially, starting at Phase 0.
After each phase: run the Definition of Done → report → wait for confirmation before moving on.

- 🛑 **HUMAN GATE** — hard stop, a human is required. Do not fabricate data just to keep going.
- ✅ **Done** — verifiable by a command, not by gut feeling.

> **Scaffolding rule:** each phase creates only the files listed in that phase.
> For directories belonging to later phases: create the directory + `.gitkeep`, **do not** create empty `.py` files.

---

**Tech stack — resolved, see [ADR-0002](docs/adr/0002-tech-stack-resolution.md):** uv, Python 3.12 +
FastAPI, PostgreSQL 16 + pgvector accessed **asynchronously** (SQLAlchemy 2.x async + `asyncpg`),
Alembic, LiteLLM as the provider wrapper, PyMuPDF for PDF. **LLM and embedding models are read from
`.env`** — currently Gemini (`gemini-3.6-flash` per [ADR-0007](docs/adr/0007-llm-model-migration-to-gemini-3-6-flash.md),
`gemini-embedding-001` at 768 dim); nothing about
the provider is hardcoded.

Extras (Celery + Redis for background jobs, Chonkie for chunking, LangChain / LangGraph for
orchestration) are **not part of v1** — they can be added later when there is a concrete reason and
an ADR. Each is listed in ADR-0002 with the trigger that would justify it.

## Phase 0 — Lock the scope + skeleton (half a day)

🛑 **HUMAN GATE.** Ask the 5 questions below, record the answers in `docs/adr/0001-scope-va-data-boundary.md`:

1. **Is data allowed to leave for an external API (OpenAI / Anthropic)?**
   → If NO: stop everything, write a new ADR, switch the stack to self-hosted.
   This is the question that kills the project if you ask it too late.
2. Do we already have 20–50 real documents to put in `data/raw/`?
3. Document language: Vietnamese only / English only / mixed?
4. Text PDFs or scanned PDFs? (scanned = out of scope, needs OCR)
5. Who is going to write the golden set in Phase 3?

**Agent's tasks:**
- [ ] Create the full directory tree as designed, **directories + `.gitkeep` only**, no `.py` files yet.
- [ ] `.gitignore`: `.env`, `data/raw/*` (except `data/samples/`), `__pycache__`, `.venv`, `*.db`
- [ ] One-page `README.md`: goal, in/out of scope, how to run.
- [ ] `docs/architecture.md`: a table of **phase → which directories get unlocked** (copy from the table below).
- [ ] `docs/adr/0000-template.md` + `0001-scope-va-data-boundary.md` (left blank, awaiting answers).

**Phase → directory map** (put this in `docs/architecture.md`):

| Phase | Unlocks |
|---|---|
| 1 | `core/`, `db/`, `models/`, `main.py`, `alembic/`, `docker-compose.yml`, `Makefile` |
| 2 | `llm/rag/{chunking,embedder,vector_store}.py`, `repositories/document_repo.py`, `services/ingest_service.py`, `scripts/ingest_corpus.py` |
| 3 | `eval/datasets/` |
| 4 | `llm/client.py`, `llm/prompts/`, `rag/retrievers/{base,dense}.py`, `rag/pipelines/{base,registry,naive_v1}.py`, `eval/{metrics,judge_prompts,runner,report}`, `results/` |
| 5 | `api/v1/routes/{chat,documents}.py`, `api/deps.py`, `schemas/`, `services/chat_service.py`, `frontend/` |
| 6 | `retrievers/{bm25,hybrid,reranker}.py`, `pipelines/hybrid_v2.py`, `.github/workflows/` |
| later | `workers/`, `llm/memory.py`, `llm/tools/`, `routes/conversations.py`, `repositories/{conversation,message}_repo.py` |

✅ **Done when:** all 5 questions have answers written in ADR-0001, and `data/raw/` contains real documents.

---

## Phase 1 — Infrastructure + schema (1 day)

- [ ] `docker-compose.yml`: a `postgres` service using `pgvector/pgvector:pg16`, a persistent volume,
      env from `.env`. No Redis yet, no worker yet.
- [ ] `backend/pyproject.toml` — only the dependencies actually used in Phases 1–2.
- [ ] `Makefile` at the root: `up`, `down`, `migrate`, `test`, `lint`, `api`.
- [ ] `.env.example`: `DATABASE_URL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
      `EMBEDDING_MODEL`, `LLM_MODEL`, `LOG_LEVEL`.
- [ ] `app/core/config.py` — `Settings` (pydantic-settings) **and** `PipelineConfig`
      (dataclass: `chunk_size`, `chunk_overlap`, `top_k`, `retriever`, `embedding_model`,
      `llm_model`, `prompt_version`). `PipelineConfig` must be serializable to a dict —
      it gets embedded into every `results/*.json` file.
- [ ] `app/core/logging.py` — structlog, JSON output.
- [ ] `app/core/exceptions.py` — `DocumentNotFound`, `UnsupportedFileType`,
      `IngestFailed`, `PipelineNotFound`.
- [ ] `app/db/base.py` (DeclarativeBase + import models), `app/db/session.py` (engine, sessionmaker).
- [ ] `app/models/` — exactly 3 tables in this phase:

```
documents   id, filename, source_path, file_hash UNIQUE, mime_type,
            page_count, status, error_message, created_at
            status ∈ {pending, processing, done, failed}

chunks      id, document_id FK CASCADE, content TEXT, page_no INT,
            chunk_index INT, token_count INT,
            embedding vector(1536), created_at
            + HNSW index (vector_cosine_ops)

queries     id, question TEXT, answer TEXT, pipeline_name TEXT,
            retrieved_chunk_ids INT[], latency_ms INT, created_at
```

> `queries` often gets skipped. Don't skip it. It is the only source that later tells you what users
> **actually** ask, and it lets you grow the golden set from real traffic instead of from imagination.
> `pipeline_name` is there so you can later trace a bad answer back to the pipeline that produced it.

- [ ] `alembic/` init + first migration, including `CREATE EXTENSION IF NOT EXISTS vector`.
- [ ] `app/main.py` + `app/api/v1/router.py` with exactly 1 route, `GET /health` (checks the DB).

✅ **Done when:** `make up && make migrate` runs clean, `curl localhost:8000/api/v1/health` → 200,
`\dt` shows all 3 tables, `\di` shows the HNSW index.

---

## Phase 2 — Synchronous ingest (2–3 days)

No endpoints yet. CLI only. Don't touch `workers/` yet.

- [ ] `app/llm/rag/chunking.py` — `chunk(pages, cfg) -> list[Chunk]`.
      Split by characters, `size=800`, `overlap=100`, preferring the nearest sentence/paragraph boundary.
      Each chunk keeps its original `page_no`. **No** semantic chunking in this phase.
- [ ] `app/llm/rag/embedder.py` — an `Embedder` protocol + an OpenAI implementation.
      Batch of 32, retry with exponential backoff, token counting.
- [ ] `app/llm/rag/vector_store.py` — a `VectorStore` protocol
      (`add_chunks`, `search`, `delete_by_document`) + a **pgvector** implementation. pgvector only.
- [ ] `app/repositories/document_repo.py` — CRUD for documents + chunks; all SQL lives here.
- [ ] `app/services/ingest_service.py` — `ingest_file(path)`:
      hash → skip if it already exists (unless `force`) → load → chunk → embed →
      insert in a single transaction → `status=done`.
      On mid-way failure: rollback, `status=failed` + `error_message`, log it, move on to the next file.
      **Do not import fastapi.**
- [ ] Loaders go in `app/services/loaders.py` or `llm/rag/loaders.py`:
      `load_pdf` (PyMuPDF, real page numbers), `load_docx` (python-docx — no real page numbers,
      state that limitation clearly in the docstring).
- [ ] `backend/scripts/ingest_corpus.py` — `--path`, `--force`, progress bar, summary at the end.
- [ ] `tests/unit/test_chunking.py` — overlap is correct, `page_no` is preserved, text shorter than
      the chunk size, text containing Vietnamese characters.
- [ ] `tests/integration/test_ingest.py` — ingest a file from `data/samples/` twice,
      assert the chunk count doesn't change (idempotent).

✅ **Done when:**
```sql
SELECT status, count(*) FROM documents GROUP BY status;
SELECT count(*) FROM chunks;
SELECT content, page_no FROM chunks ORDER BY random() LIMIT 5;
```
And **a human reads those 5 random chunks** and confirms: no lost Vietnamese diacritics, no repeated
header/footer stuck in, no words cut in half, `page_no` correct. Eyeball check, mandatory.

---

## Phase 3 — Golden set (half a day) ⚠️

🛑 **HUMAN GATE. Stop before writing a single line of retrieval code.**

The phase most likely to get skipped. The urge right now will be *"let's do retrieval first, it's faster,
the golden set can wait."* Don't. Without a baseline, everything in Phase 6 is just gut feeling.

**Human's task** — hand-write 20–30 questions into `eval/datasets/golden_qa.v1.jsonl`:

```json
{"id": "q001",
 "q": "Chính sách nghỉ phép năm là bao nhiêu ngày?",
 "ground_truth": "12 ngày/năm, cộng thêm 1 ngày mỗi 5 năm làm việc",
 "relevant_chunk_ids": [142, 143],
 "type": "factual"}
```

Distribution: `factual` (1 chunk is enough to answer), `multi_hop` (needs ≥2 chunks),
`unanswerable` (not in the corpus — at least 3–5 questions, to measure whether the system dares to say
"I don't know"). With enterprise documents, making up an answer is far more dangerous than refusing.

**Agent's tasks:**
- [ ] `eval/datasets/README.md` — the format, and the versioning rule (`v1` is frozen once committed;
      new questions → `v2`, never edit `v1`).
- [ ] `backend/scripts/find_chunks.py --q "keyword"` — full-text search over `chunks`,
      printing `chunk_id + page_no + snippet` so the writer can look up `chunk_id` quickly.
- [ ] `eval/datasets/validate.py` — check the JSON is valid, `id`s are unique,
      `relevant_chunk_ids` actually exist in the DB, `unanswerable` questions have an empty array.
- [ ] **DO NOT generate questions yourself.** If asked to, refuse and explain why.

✅ **Done when:** `golden_qa.v1.jsonl` has ≥20 human-written lines and `python -m eval.datasets.validate` passes.

---

## Phase 4 — `naive-v1` baseline (1–2 days)

Deliberately simple. This is a reference point, not a product.

- [ ] `app/llm/client.py` — provider wrapper, retry, timeout. No streaming yet.
- [ ] `app/llm/prompts/answer_v1.jinja` — put the top-k chunks into the context; require answers
      **based only on the context**; require source citations in the form `[filename, p.N]`;
      **require saying "no information found in the documents" when the context is insufficient.**
- [ ] `app/llm/rag/retrievers/base.py` — the `Retriever.retrieve(q, k) -> list[RetrievedChunk]` protocol.
- [ ] `app/llm/rag/retrievers/dense.py` — embed the query → cosine top-k via `VectorStore`.
      No reranking, no filtering, no hybrid.
- [ ] `app/llm/rag/pipelines/base.py` — the `RAGPipeline` protocol + a `RAGAnswer` dataclass
      (`answer`, `citations`, `chunk_ids`, `latency_ms`, `pipeline_name`, `config`).
- [ ] `app/llm/rag/pipelines/registry.py` — `@register(name)` + `get_pipeline(name)`,
      raising `PipelineNotFound` when it doesn't exist.
- [ ] `app/llm/rag/pipelines/naive_v1.py` — `@register("naive-v1")`, dense top-5 + answer_v1.
- [ ] `eval/metrics/retrieval.py` — `recall@k`, `MRR`, `nDCG@k`.
- [ ] `eval/metrics/generation.py` — LLM-as-judge:
      - `faithfulness` 1–5: does it invent anything outside the context
      - `answer_relevance` 1–5
      - `refusal_accuracy`: are `unanswerable` questions correctly refused
- [ ] `eval/judge_prompts/faithfulness_v1.jinja`, `relevance_v1.jinja`.
- [ ] `eval/runner.py` — `python -m eval.runner --pipeline naive-v1 [--dataset v1]`.
      Writes `results/naive-v1.json` containing: `pipeline_name`, the **full `config`**,
      `dataset_version`, `git_sha`, `timestamp`, aggregate metrics, and per-question details.
- [ ] `eval/report.py` — read every `results/*.json` → `results/leaderboard.md` (comparison table).

✅ **Done when:** `results/naive-v1.json` exists and **has been committed**.
Even if the scores are bad — especially if they're bad. That's the baseline.
**Do not touch retrieval to make the numbers look nicer before committing this file.**
Once committed, `naive_v1.py` is frozen.

---

## Phase 5 — API + thin frontend (1–2 days)

- [ ] `app/schemas/` — `ChatRequest/ChatResponse`, `DocumentOut`, `Citation`
      (`filename`, `page_no`, `snippet`, `chunk_id`). Never return ORM objects.
- [ ] `app/api/deps.py` — `get_db`, `get_pipeline` (reads the pipeline name from Settings).
- [ ] `app/services/chat_service.py` — take the question → get the pipeline from the registry →
      `answer()` → write to the `queries` table → return a DTO. Do not import fastapi.
- [ ] `routes/documents.py` — `POST /documents` (upload + **synchronous** ingest),
      `GET /documents` (list + status). Slow is acceptable; don't add a queue.
- [ ] `routes/chat.py` — `POST /chat`. **Single-turn.** No `conversation_id` yet, no streaming yet.
- [ ] `frontend/` — a single-file Streamlit app is enough: upload, a question box, display the answer +
      clickable citations that show the snippet. It doesn't need to look good.
- [ ] `tests/integration/test_api.py` — smoke tests for the 3 endpoints.

✅ **Done when:** someone outside the team can click through it without instructions, and the `queries`
table has real data after the demo session.

---

## Phase 6 — Improvements, one pipeline at a time

The mandatory loop:

```
create a new pipeline (change EXACTLY 1 variable vs. the current best pipeline)
  → make eval P=<new name>
  → make report
  → better: commit both the code and the results
  → not better: keep the file + the results, write an ADR explaining "why we're not using it"
```

Don't edit old pipelines. Don't delete bad results — negative results are information too.

Order to try things in, by benefit/effort ratio:

1. [ ] `retrievers/bm25.py` + `hybrid.py` (RRF fusion, using Postgres `tsvector`)
       → `pipelines/hybrid_v2.py` → `results/hybrid-v2.json`.
       Usually the single biggest improvement for enterprise documents: lots of internal jargon and
       reference codes that embeddings capture poorly.
2. [ ] Chunk size / overlap: `chunk-500-v1`, `chunk-1200-v1`. Requires a full re-ingest →
       record clearly in `results/*.json` which corpus version was used.
3. [ ] `retrievers/reranker.py` — cross-encoder top-20 → top-5 → `rerank-v1`.
4. [ ] Query rewriting → `qrewrite-v1`.
- [ ] `.github/workflows/ci.yml` — lint + unit tests.
- [ ] `.github/workflows/eval.yml` — run eval on PRs, comment the diff against the baseline.
      Only do this once there are ≥3 pipelines, not earlier.

✅ **Done when:** `results/leaderboard.md` has ≥3 rows, and you can explain why you kept one and dropped
another — with numbers, not with feelings.

---

## After Phase 6 — only add these when there's a concrete reason

`workers/` + Redis (async ingest, once uploads take > 30s) · `llm/memory.py` + multi-turn ·
`conversations.py` + `conversation_repo`/`message_repo` · streaming · `llm/tools/` ·
document-level permissions · OCR · Qdrant.

Each one = 1 ADR describing the real problem you're hitting, written before the first line of code.

---

## Estimate

~2 weeks to get through Phase 5 with focused work.
The easiest place to slip is **Phase 3**. Don't slip.