What's done
Phase 0 — scope lock + skeleton (2a86836, 2a9b4d9)

Wrote CLAUDE.md, PLAN.md, docs/architecture.md, and three ADRs: 0001 scope/data boundary (Gemini API approved, 8 Vietnamese HR PDFs as corpus), 0002 tech stack (Python 3.12, async SQLAlchemy/asyncpg, gemini-embedding-001 @ 768 dim, gemini-2.5-flash via LiteLLM).
Deleted 73 zero-byte .py files — the repo had the whole tree pre-scaffolded including Phase 6+ files, against the no-premature-scaffold rule. Directories now hold .gitkeep.
Phase 1 — infrastructure + schema (42c50dd)

docker-compose.yml (pgvector/pg16 + healthcheck), root Makefile, .env.example, backend/pyproject.toml.
app/core/ config/logging/exceptions · app/db/ async base+session · models document.py, chunk.py, query.py · alembic with the initial migration · app/main.py + health.py · one unit test.
Verified: alembic check no drift, downgrade→upgrade reversible, health returns 503 when postgres is down and recovers without restart, lint clean, 9 tests pass.
Phase 2 — synchronous ingest: not started. d634776 is just the handoff note.

Commands you can run now

make up        # start postgres+pgvector, waits for healthy
make migrate   # alembic upgrade head
make api       # uvicorn with reload -> localhost:8000
curl localhost:8000/api/v1/health   # {"status":"ok","database":"up"}
make test      # 9 pass
make lint      # ruff + mypy, clean
make psql      # psql shell in the container
make install logs down revision fmt
make ingest, make eval, make report are in CLAUDE.md §7 but do not exist yet — they arrive with Phases 2 and 4.

