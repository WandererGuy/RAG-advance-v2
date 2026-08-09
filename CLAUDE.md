# CLAUDE.md — rag-chatbot

Context file auto-loaded by Claude Code. Read all of it before doing anything.
Build plan: `PLAN.md`. Phase → directory map: `docs/architecture.md`.

> **Start here: `docs/progress.md`.** It records which phases are done, the evidence they passed
> their Definition of Done, deviations from PLAN.md, and open items. **Phases 0 and 1 are complete;
> Phase 2 (synchronous ingest) is next.** Section 3 below has been partly superseded — read it
> together with `docs/adr/0002-tech-stack-resolution.md`.

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
| `frontend/` | Phase 5 |
| Qdrant version of `vector_store.py` | never — pgvector is enough |

Do not create empty `.py` files or abstract classes "for later use". If a directory is
empty, leave it empty (with a `.gitkeep`). Abstraction created before the need for it is
debt, not an asset.

## 3. Tech stack — decided

Four rows below were superseded during Phase 0 by
[ADR-0002](docs/adr/0002-tech-stack-resolution.md), after the human gate. **Build against the
"as built" column** — it is what is running and what the schema already encodes.

| | originally written here | as built |
|---|---|---|
| Python | 3.11, managed with `uv` | **3.12**, managed with `uv` |
| DB | PostgreSQL 16 + pgvector | same |
| ORM | SQLAlchemy 2.x + Alembic | same, **async** (`asyncpg`) |
| API | FastAPI + uvicorn | same |
| PDF | PyMuPDF (`fitz`) — accurate page numbers required | same |
| DOCX | `python-docx` | same |
| Embedding | `text-embedding-3-small` (1536 dim) | **`gemini-embedding-001`, 768 dim**, read from `.env` |
| LLM | read from env, defaults to `claude-sonnet-4-6` | read from `.env`, currently **`gemini-2.5-flash`** via LiteLLM |
| Prompt | Jinja2 templates in `app/llm/prompts/`, versioned filenames | same |
| Frontend | decided in Phase 5 (Streamlit if a demo is all that's needed) | same |
| Test | pytest | same (+ `pytest-asyncio`) |

The vector dimension **768** is written in three places that must change together: `.env`
(`EMBEDDING_DIMENSIONS`), `app/models/chunk.py` (`EMBEDDING_DIM`), and the initial migration.
Changing it is a migration plus a full re-ingest plus a re-run of every pipeline.

Deliberately **not** in v1, despite PLAN.md line 14 suggesting them: Celery + Redis, LangChain,
LangGraph, Chonkie. Each is rejected in ADR-0002 with a named trigger for revisiting. Do not add
them without an ADR.

> ✅ **Project-blocking question — answered 2026-08-09, see
> [ADR-0001](docs/adr/0001-scope-va-data-boundary.md).** Data **is** allowed to leave for an
> external API; Gemini is approved. Self-hosting (Ollama + `bge-m3`) is therefore not needed. Do
> not re-open this on your own; if it is reversed, every embedding and every committed result is
> invalidated.

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
instantiate one itself. Only write `dense.py` in Phase 4; the rest comes in Phase 6.

## 5. Working rules

1. **One phase at a time.** Finish phase N → run the Definition of Done → report → wait for
   confirmation. No skipping ahead, no "might as well do the next phase while I'm here".
2. **Only create a directory/file when its phase arrives.** Map is in `docs/architecture.md`.
3. **No premature optimization.** `chunk_size=800`, `overlap=100`, `top_k=5` are the starting
   values; keep them unchanged until Phase 6.
4. **From Phase 6 on: each experiment changes exactly 1 variable**, and is a new pipeline with
   its own name.
5. **No mocks, no fake data.** No real documents or API key yet → stop and ask.
   Absolutely do not generate sample PDFs just to "make it run".
6. **Do not write the golden set yourself** (Phase 3). If asked to, refuse and explain why.
7. **Every technical decision with a trade-off → write one ADR** in `docs/adr/NNNN-title.md`
   (Context / Decision / Consequences). Do not argue it out in commit messages.
8. **Every number must be written to `results/*.json` and committed.** No verbal reporting.
9. Commit per phase: `feat(phase-2): sync ingest pipeline`.
10. Secrets live only in `.env` (already gitignored). `.env.example` is committed with empty values.
11. **A phase is not finished until `docs/progress.md` has its entry.** Write it before the phase
    commit and include it in that same commit. Four things, every time: what was built, the
    command output proving the Definition of Done, deviations from PLAN.md and why, and open
    items — especially anything blocked on a human. Rule 8 applies here too: the evidence goes in
    the file, not only into the chat. The next session starts with this file and remembers
    nothing else.

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
make api         # uvicorn app.main:app --reload
make eval P=naive-v1
                 # python -m eval.runner --pipeline naive-v1
make report      # python -m eval.report -> results/leaderboard.md
make test
make lint        # ruff + mypy
```

Python commands run from `backend/`. The Makefile at root handles the `cd`.