# CLAUDE.md — rag-chatbot

Context file auto-loaded by Claude Code. Read all of it before doing anything.

> **Then read `docs/progress.md`** — the status of every phase, what is blocked on a human, and a
> link to one file per phase in `docs/progress/` holding the evidence, deviations and open items.
> This file says what is *true*; the progress log says what has *happened*; `docs/adr/` says *why*.

Build plan: `PLAN.md`. Phase → directory map: `docs/architecture.md`.

---

## 1. Goal

Q&A over internal company documents. Users ask in Vietnamese; the system answers
with **citations** (document name + page number).

Priority: **get it running and measurable early**, optimize later. The directory structure
is designed for the final stage — but **do not scaffold all of it up front**. See section 4.

## 2. Scope

**In scope for v1 (Phase 0–5):**
- Text-based PDF + DOCX
- Single-turn questions, no permissions, no auth
- Answer + citations
- Synchronous ingest

**Out of scope for v1 — directories exist but stay EMPTY:**

| Directory / file | Unlocked at |
|---|---|
| `app/workers/` | after Phase 6 |
| `app/llm/memory.py` | after Phase 6 (multi-turn) |
| `app/llm/tools/` | after Phase 6 (function calling) |
| `app/api/v1/routes/conversations.py` | after Phase 6 |
| `app/repositories/conversation_repo.py`, `message_repo.py` | after Phase 6 |
| Qdrant version of `vector_store.py` | never — pgvector is enough |

Do not create empty `.py` files or abstract classes "for later use". If a directory is
empty, leave it empty (with a `.gitkeep`). Abstraction created before the need for it is
debt, not an asset.

## 3. Tech stack — as built

This is what is running and what the schema already encodes. Where it differs from PLAN.md's
original wording, [ADR-0002](docs/adr/0002-tech-stack-resolution.md) records why.

| | |
|---|---|
| Python | 3.12, managed with `uv` |
| DB | PostgreSQL 16 + pgvector |
| ORM | SQLAlchemy 2.x + Alembic, **async** (`asyncpg`) |
| API | FastAPI + uvicorn |
| PDF | PyMuPDF (`fitz`) — accurate page numbers required |
| DOCX | `python-docx` |
| Embedding | `text-embedding-3-large`, **768 dim** (native truncation), read from `.env` |
| LLM | read from `.env`, currently `gpt-5.6-luna` via LiteLLM ([ADR-0008](docs/adr/0008-provider-migration-to-openai.md)). **Pinned, never a moving alias.** It rejects `temperature=0`, so `LLM_SUPPORTS_TEMPERATURE=false` and results files record `temperature: null` |
| Prompt | Jinja2 templates in `app/llm/prompts/`, versioned filenames |
| Frontend | Streamlit, single file (`frontend/app.py`, `make ui`) — a client of the API, holding no logic. An optional `frontend` extra, so the API deploys without it |
| Test | pytest + `pytest-asyncio` |

The vector dimension **768** is written in three places that must change together: `.env`
(`EMBEDDING_DIMENSIONS`), `app/models/chunk.py` (`EMBEDDING_DIM`), and the initial migration.
Changing it is a migration plus a re-embed plus a re-run of every pipeline.

**Changing the embedding model — even at the same dimension — invalidates every stored vector**,
because embeddings are only comparable to others from the same model. Re-embed with `make reembed`,
which UPDATEs the vectors in place. **Never `make ingest FORCE=1`**: that reassigns chunk ids and
silently invalidates every `relevant_chunk_ids` in the golden set (ADR-0005, ADR-0008). That trap
is deliberately **not** reachable over HTTP: `POST /documents` has no `force` parameter and always
skips known bytes. An ordinary upload is still a corpus change, so run `make validate` after any
upload session.

Deliberately **not** in v1: Celery + Redis, LangChain, LangGraph, Chonkie. Each is rejected in
ADR-0002 with a named trigger for revisiting. Do not add them without an ADR.

**The corpus is synthetic and committed.** The 8 Vietnamese HR PDFs in `data/raw/HR_pdfs/` are demo
documents for a fictional company, not real company data. They are **in git** and may be shown,
quoted and shared freely — in docs, screenshots or bug reports ([ADR-0001](docs/adr/0001-scope-va-data-boundary.md)).
`.gitignore` un-ignores that one directory and keeps the rest of `data/raw/` ignored, so a *real*
document added later is still not committed by accident. Nothing else about the corpus changes: it
is still frozen under ADR-0005, and being committed is not permission to add to it.

> ✅ **Data is allowed to leave for an external API; OpenAI is approved**
> ([ADR-0001](docs/adr/0001-scope-va-data-boundary.md), 2026-08-09). Self-hosting is therefore not
> needed. Do not re-open this on your own — if it is reversed, every embedding and every committed
> result is invalidated.

## 4. Architecture principles

**4.1. The pipeline is the unit of evaluation.**
`app/llm/rag/pipelines/` holds implementations of `RAGPipeline`. Each pipeline is one
complete RAG configuration, has a name, and is registered in `registry.py`:

```python
# app/llm/rag/pipelines/base.py
class RAGPipeline(Protocol):
    name: str
    config: PipelineConfig          # chunk_size, top_k, retriever, model...
    def retrieve(self, question: str) -> list[RetrievedChunk]: ...
    def answer(self, question: str) -> RAGAnswer: ...
```

```python
@register("naive-v1")
class NaiveV1: ...
```

Mandatory consequences:
- `eval/runner.py --pipeline naive-v1` must work with **any** name in the registry.
- **A pipeline that already has results in `results/` is immutable.** To try a new idea →
  create a new pipeline file with a new name. Do not edit `naive_v1.py` after
  `results/naive-v1.json` has been committed. Editing it destroys comparability.
- `chat_service.py` selects the pipeline through the registry based on config; it does not
  import the class directly.

**4.2. Layering — no shortcuts.**
```
routes/  →  services/  →  repositories/  →  models/
                      →  llm/rag/pipelines/
```
- `routes/` only validates and calls a service. No business logic.
- `services/` does not know HTTP exists. No importing `fastapi`, no accepting `Request`.
- Only `repositories/` may write SQL queries / use a session. Services do not query directly.
- `schemas/` (Pydantic, the API contract) is fully separate from `models/` (ORM). Never return
  an ORM object from a route.

**4.3. The retriever is an interface.**
`retrievers/base.py` defines the protocol; `dense.py`, `bm25.py`, `hybrid.py`, `reranker.py`
are implementations. The pipeline receives a retriever through its constructor; it does not
instantiate one itself. `dense.py` (Phase 4), `bm25.py` and `hybrid.py` (Phase 6) exist;
`reranker.py` does not yet.

**Retrieval scores are per-retriever and never comparable across retrievers.** A cosine similarity
and a `ts_rank_cd` share no scale; `RetrievedChunk.score` means whatever the retriever that
produced it ranks by. That is why `hybrid.py` fuses by **rank** (RRF, K=60) rather than by any
weighted sum of scores.

## 5. Working rules

1. **One phase at a time.** Finish phase N → run the Definition of Done → report → wait for
   confirmation. No skipping ahead, no "might as well do the next phase while I'm here".
2. **Only create a directory/file when its phase arrives.** Map is in `docs/architecture.md`.
3. **No premature optimization.** `chunk_size=800`, `overlap=100`, `top_k=5` are the baseline
   values. Phase 6 may vary them — one at a time, as a new pipeline. Changing chunk size means a
   re-ingest, which reassigns chunk ids: read ADR-0005 before starting that one.
4. **Each Phase 6 experiment changes exactly 1 variable**, and is a new pipeline with its own
   name. **A pipeline that loses is committed anyway**, with an ADR saying why it was not adopted
   — `hybrid-v2` is the worked example ([ADR-0009](docs/adr/0009-hybrid-retrieval-not-adopted.md)).
   Never delete a negative result to tidy up.
5. **No mocks, no fake data.** No real documents or API key yet → stop and ask.
   Absolutely do not generate sample PDFs just to "make it run".
6. **The golden set is agent-authored**, under
   [ADR-0004](docs/adr/0004-agent-authored-golden-set.md). Its conditions are binding: every line
   carries an `author` field, `validate.py` rejects a line without one, and every `results/*.json`
   carries `golden_set_author`. **Read the ADR's inflation table before quoting any number.** A
   human writing `golden_qa.v2.jsonl` is still the goal, not a nice-to-have — the ADR names the
   triggers.
7. **Every technical decision with a trade-off → write one ADR** in `docs/adr/NNNN-title.md`
   (Context / Decision / Consequences). Do not argue it out in commit messages.
8. **Every number must be written to `results/*.json` and committed.** No verbal reporting. From
   Phase 4 on, every results file also carries **`golden_set_author`** next to `dataset_version`,
   and `leaderboard.md` shows it as a column — so no score of this system can be read, quoted or
   pasted without the provenance of the questions that produced it (ADR-0004).
9. Commit per phase: `feat(phase-2): sync ingest pipeline`.
10. Secrets live only in `.env` (already gitignored). `.env.example` is committed with empty values.
11. **A phase is not finished until `docs/progress/phase-N.md` exists**, with its row added to the
    `docs/progress.md` index, in the same commit as the code. Five sections: what was built · the
    command output proving the Definition of Done · deviations from PLAN.md and why · open items,
    especially anything **blocked on a human** · **"What you can do after this phase"** (rule 12).
    Rule 8 applies here too — the evidence goes in the file, not only into the chat. The next
    session starts with these files and remembers nothing else.
12. **Every phase entry ends with "What you can do after this phase"**, in five parts, matching
    `docs/progress/phase-{0,1,2}.md`: **Available** · **Commands that work at this point**
    (copy-pasteable, nothing from a later phase) · **Technical / Non-technical, possible now**
    (including what only a human can decide) · **Notice** (the traps) · **For the next phase
    (N+1)**.
13. **`/phase-done N` is how 11 and 12 get done** — it holds the full procedure, checks → entry →
    index → commit, and the detail of what each section must contain.
14. **Keep this file true, not historical.** When a rule here is superseded, rewrite it and let the
    ADR carry the history. No strike-throughs, no "originally / as built" columns.
15. **`old_code/` is off-limits.** Do not read, grep, list or edit anything under it as part of
    normal work — it is legacy notes kept in the repo for reference only, and reading it burns
    context for nothing. Touch it *only*
    when the user names it explicitly in a request ("look in old_code for X"), and then read only
    the specific files needed. It is never a source of truth: `PLAN.md`, `docs/` and the code in
    `backend/` are.
16. **Retrieval metrics are deterministic; generation metrics are not.** `gpt-5.6-luna` rejects
    `temperature=0`, so every run samples. Two runs of `hybrid-v2` on identical code and an
    identical corpus produced `refusal_accuracy` **0.8 and 1.0**, while every retrieval metric came
    back byte-identical. **Never draw a conclusion from a single run, or from a generation-metric
    gap under ~0.2 between two pipelines.** Retrieval numbers may be compared directly
    ([ADR-0009](docs/adr/0009-hybrid-retrieval-not-adopted.md)).

## 6. Code conventions

- Type hints on every public function. `mypy` doesn't have to pass 100%, but don't sprinkle
  `Any` around.
- No `except: pass`. Domain exceptions live in `core/exceptions.py`.
- Config is read through `core/config.py`. No `os.getenv()` scattered around.
- Log through `core/logging.py` (structlog, JSON). No `print()` outside `scripts/`.
- Ingest is **idempotent**: re-running on the same file produces no duplicate chunks
  (based on `file_hash`).
- Prompts are never hardcoded inline — they always live in `app/llm/prompts/*.jinja`, with the
  version in the filename (`answer_v1.jinja`). Changing a prompt = a new file.
- Tests: `tests/unit/` touches no DB/network; `tests/integration/` uses a real Postgres
  via docker compose.

## 7. Commands (all through the Makefile, run from repo root)

```bash
make up          # docker compose up -d (postgres + pgvector)
make migrate     # alembic upgrade head
make ingest      # python -m scripts.ingest_corpus --path data/raw
make reembed     # re-embed in place after an embedding-model change (never ingest FORCE=1)
make find Q="phụ cấp"
                 # python -m scripts.find_chunks --q "…" — chunk ids for the golden set
make validate    # python -m eval.datasets.validate — golden set + frozen corpus (ADR-0005)
make api         # uvicorn app.main:app --reload
make ui          # streamlit run frontend/app.py — needs `make api` in another terminal
make eval P=naive-v1
                 # python -m eval.runner --pipeline naive-v1
make report      # python -m eval.report -> results/leaderboard.md
make test
make lint        # ruff + mypy
```

Python commands run from `backend/`. The Makefile at root handles the `cd`.

Slash commands in `.claude/commands/`:

| Command | Does |
|---|---|
| `/phase-done N` | closes out phase N: DoD checks → `docs/progress/phase-N.md` → index → commit (rules 8–12) |
