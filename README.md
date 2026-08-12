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
Alembic · PyMuPDF · LiteLLM, with the LLM and embedding model read from `.env` — currently OpenAI
(`gpt-5.6-luna`, `text-embedding-3-large` at 768 dim) · Jinja2 prompts · pytest.

Celery + Redis, Chonkie and LangChain / LangGraph are deliberately not in v1; they can be added
later. See [ADR-0002](docs/adr/0002-tech-stack-resolution.md) for the reasoning and the trigger for
revisiting each.

## How to run

Phases 0–3 are done: the database, the schema, the health endpoint, synchronous ingest, and a
29-question golden set over a frozen corpus. Phase 4's code is complete — `naive-v1` retrieves,
answers with citations, and is scored by `make eval` — but **no baseline number has been committed
yet**; the provider's free tier cannot fit one evaluation run in a day. There is no chat endpoint
yet — that is Phase 5, and the only route the API serves today is `/api/v1/health`.

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
cp .env.example .env    # fill DEFAULT_LLM_API_KEY + EMBEDDING_API_KEY (OpenAI)
make install            # uv sync --extra dev
make up                 # docker compose up -d --wait
make migrate            # alembic upgrade head
make ingest             # defaults to --path ../data/raw
make api
```

All targets run from the repository root — the Makefile handles the `cd backend`. Also available:
`make validate` (golden set + frozen corpus), `make find Q="…"`, `make eval P=naive-v1`,
`make report`, `make test`, `make lint`, `make psql`, `make logs`, `make down`, and
`make ingest FORCE=1` to re-ingest.

After changing the embedding model, use `make reembed` — **not** `make ingest FORCE=1`. It
re-embeds every chunk in place, so chunk ids and the corpus lock survive
([ADR-0008](docs/adr/0008-provider-migration-to-openai.md)).

`make ingest FORCE=1` reassigns chunk ids, which invalidates the golden set's
`relevant_chunk_ids`. The corpus is frozen and `make validate` now fails loudly when that happens
— see [ADR-0005](docs/adr/0005-frozen-corpus-for-the-golden-set.md).

`make eval` calls the provider roughly three times per question (one answer, two judgements) —
about 82 calls for the 29-question golden set, on a metered OpenAI key.

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
