# Kết nối tới database bằng GUI client

> Ghi lại buổi trao đổi về việc điền form "Connect to server" của một database client
> (Navicat / DBeaver / Database Client cho VSCode — các field giống nhau).
>
> Nguồn: `.env`, `.env.example`, `docker-compose.yml`,
> `backend/tests/integration/conftest.py`.

---

## Điền gì vào form

Your `.env` has the real values — the dialog's defaults (`postgres`/`postgres`) are wrong for
this project.

**Fill in:**

| Field | Value |
|---|---|
| Name | `rag-chatbot` (free text, any label) |
| Group | leave as-is / None — it's just folder organization in the client |
| Scope | leave default (usually "Global"/"Current workspace") |
| Server Type | **PostgreSQL** |
| Host | `127.0.0.1` ✓ (already correct) |
| Port | `5432` ✓ |
| Username | `rag` ← change |
| Password | `rag` ← change |
| Database | `rag` ← change |

Features checkboxes (Type / Trigger / Sequence / Foreign Table / Materialized View): tick none —
you don't need any of them. Leave "Use Connection String" and "SSL" off; the container has no TLS.

Or paste the connection string instead: `postgresql://rag:rag@127.0.0.1:5432/rag`

**Two things to check first:**

- Container must be up: `make up` (compose maps `${POSTGRES_PORT:-5432}` → 5432).
- Note the app's own `DATABASE_URL` uses the `postgresql+asyncpg://` scheme — that's a SQLAlchemy
  driver prefix, don't paste it into the GUI. Strip it to `postgresql://`.

Once connected, the tables from Phase 1 live in the default `public` schema (`documents`,
`chunks`, `alembic_version`).

---

## Tại sao thấy 3 database: `rag`, `rag_test`, `postgres`

All three are expected — that's a healthy install, nothing to clean up:

- **`rag`** — your actual development database, created by docker compose from `POSTGRES_DB=rag`.
  This is the one you want. Phase 1/2 tables (`documents`, `chunks`, `alembic_version`) are here.
- **`rag_test`** — created on demand by the integration tests
  (`backend/tests/integration/conftest.py`) by appending `_test` to the DATABASE_URL database
  name. It exists because a re-ingest deletes and rebuilds chunks, so tests sharing `rag` would
  renumber the chunk ids Phase 3's golden set will reference. Its tables are emptied after each
  test, so it will normally look populated-but-blank.
- **`postgres`** — the maintenance database that ships with every Postgres image. The test fixture
  connects to it only to issue `CREATE DATABASE rag_test`, since you cannot create a database from
  inside itself. It has no tables of yours.

So: set **Database = `rag`**. Don't point the GUI at `postgres` (empty) and don't do exploratory
work in `rag_test` — `make test` wipes its rows.

One caution: if you browse `rag_test` while `make test` is running, you may see tables appear and
empty out under you. That's the teardown, not corruption.
