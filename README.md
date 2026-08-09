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

Python 3.12 (`uv`) · FastAPI · PostgreSQL 16 + pgvector · SQLAlchemy 2.x + Alembic · PyMuPDF ·
LiteLLM → Gemini (`gemini-2.5-flash`, `gemini-embedding-001` at 768 dim) · Jinja2 prompts · pytest.

See [ADR-0002](docs/adr/0002-tech-stack-resolution.md) for why, and what was deliberately left out.

## How to run

Not runnable yet — Phase 0 is complete, Phase 1 (infrastructure and schema) is next. Once Phase 1
lands, from the repository root:

```bash
cp .env.example .env    # then fill in DEFAULT_LLM_API_KEY and EMBEDDING_API_KEY
make up                 # postgres + pgvector
make migrate            # alembic upgrade head
make api                # uvicorn, then curl localhost:8000/api/v1/health
```

Later phases add `make ingest`, `make eval P=naive-v1`, `make report`, `make test`, `make lint`.
All commands run from the repository root; the Makefile handles the `cd backend`.

## How the project is organised

Read [CLAUDE.md](CLAUDE.md) for the working rules, [PLAN.md](PLAN.md) for the phase-by-phase
roadmap, and [docs/architecture.md](docs/architecture.md) for the layering and the phase →
directory map.

Two rules matter more than the rest:

1. **A pipeline with committed results is frozen.** New idea → new pipeline file, new name. Editing
   one after `results/<name>.json` is committed destroys comparability between runs.
2. **Every number goes into `results/*.json` and gets committed** — including the bad ones. Negative
   results are information.
