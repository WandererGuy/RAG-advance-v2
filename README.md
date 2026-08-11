# rag-chatbot

Q&A over internal company documents. Users ask in Vietnamese; the system answers **with citations**
(document name + page number).

The corpus for v1 is 8 Vietnamese HR policy documents (handbook, compensation, grading, leave and
remote work, information security, hiring, code of conduct, travel expenses).

## Scope

**In scope for v1 (Phases 0–5)**

- Text-based PDF and DOCX
- Single-turn questions — no auth, no permissions
- An answer plus citations, or an explicit "no information found in the documents"
- Synchronous ingest

**Out of scope for v1** — these directories exist but stay empty until there is a concrete reason
and an ADR: async workers, multi-turn memory, function calling, conversation endpoints, streaming,
document-level permissions, OCR, Qdrant.

## Stack

Python 3.12 (`uv`) · FastAPI · PostgreSQL 16 + pgvector, async via SQLAlchemy 2.x + `asyncpg` ·
Alembic · PyMuPDF · LiteLLM, with the LLM and embedding model read from `.env` — currently Gemini
(`gemini-2.5-flash`, `gemini-embedding-001` at 768 dim) · Jinja2 prompts · pytest.

Celery + Redis, Chonkie and LangChain / LangGraph are deliberately not in v1; they can be added
later. See [ADR-0002](docs/adr/0002-tech-stack-resolution.md) for the reasoning and the trigger for
revisiting each.

## How to run

Phases 0–2 are done: the database, the schema, the health endpoint and synchronous ingest work.
There is no chat endpoint yet — that is Phase 5, and the only route the API serves today is
`/api/v1/health`.

### To run it right now

On a machine where the stack is already provisioned — postgres up, venv synced, migrations
applied, corpus ingested:

```bash
make up      # postgres is probably already up; this is a no-op safety check
make api     # uvicorn on :8000, with reload
curl localhost:8000/api/v1/health   # -> {"status":"ok","database":"up"}
```

### From scratch on a fresh machine

```bash
cp .env.example .env    # fill DEFAULT_LLM_API_KEY + EMBEDDING_API_KEY (Gemini)
make install            # uv sync --extra dev
make up                 # docker compose up -d --wait
make migrate            # alembic upgrade head
make ingest             # defaults to --path ../data/raw
make api
```

All targets run from the repository root — the Makefile handles the `cd backend`. Also available:
`make test`, `make lint`, `make psql`, `make logs`, `make down`, and `make ingest FORCE=1` to
re-ingest. Later phases add `make eval P=naive-v1` and `make report`.

`make ingest FORCE=1` reassigns chunk ids, which invalidates the Phase 3 golden set's
`relevant_chunk_ids`. Freeze the corpus before that golden set is written.

Progress index: [docs/progress.md](docs/progress.md) — phase status, what is blocked on a human,
and a link to the per-phase entry in [docs/progress/](docs/progress/) holding the verification
evidence.

## How the project is organised

Read [CLAUDE.md](CLAUDE.md) for the working rules, [PLAN.md](PLAN.md) for the phase-by-phase
roadmap, and [docs/architecture.md](docs/architecture.md) for the layering and the phase →
directory map.

Two rules matter more than the rest:

1. **A pipeline with committed results is frozen.** New idea → new pipeline file, new name. Editing
   one after `results/<name>.json` is committed destroys comparability between runs.
2. **Every number goes into `results/*.json` and gets committed** — including the bad ones. Negative
   results are information.
