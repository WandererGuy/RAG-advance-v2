# Architecture — rag-chatbot

Q&A over internal company documents. Questions are asked in Vietnamese; every answer carries
citations (document name + page number).

## Layering

```
routes/  →  services/  →  repositories/  →  models/
                      →  llm/rag/pipelines/
```

- `routes/` validates input and calls a service. No business logic.
- `services/` does not know HTTP exists. No `fastapi` import, no `Request` parameter.
- `repositories/` is the only layer that may hold SQL / touch a session.
- `schemas/` (Pydantic, the API contract) is separate from `models/` (SQLAlchemy ORM).
  An ORM object is never returned from a route.

## The pipeline is the unit of evaluation

`app/llm/rag/pipelines/` holds implementations of the `RAGPipeline` protocol. One pipeline =
one complete RAG configuration, with a name, registered in `registry.py`. `eval/runner.py
--pipeline <name>` must work for any registered name.

A pipeline that already has results in `results/` is **immutable**. New idea → new file, new
name. Editing a pipeline after its results are committed destroys comparability.

The retriever is injected into the pipeline through its constructor; the pipeline never
instantiates one itself.

## Phase → directory map

Each phase creates only the files listed for that phase. Directories belonging to later phases
exist with a `.gitkeep` and stay empty. No empty `.py` files, no abstract classes "for later".

| Phase | Unlocks |
|---|---|
| 1 | `core/`, `db/`, `models/`, `main.py`, `alembic/`, `docker-compose.yml`, `Makefile` |
| 2 | `llm/rag/{chunking,embedder,vector_store}.py`, `repositories/document_repo.py`, `services/ingest_service.py`, `scripts/ingest_corpus.py` |
| 3 | `eval/datasets/` (incl. `validate.py`, `corpus.lock.json`), `scripts/find_chunks.py` |
| 4 | `llm/client.py`, `llm/prompts/`, `rag/retrievers/{base,dense}.py`, `rag/pipelines/{base,registry,naive_v1}.py`, `eval/{metrics,judge_prompts,runner,report}`, `results/` |
| 5 | `api/v1/routes/{chat,documents}.py`, `api/deps.py`, `schemas/`, `services/chat_service.py`, `frontend/` |
| 6 | `retrievers/{bm25,hybrid,reranker}.py`, `pipelines/hybrid_v2.py`, `.github/workflows/` |
| later | `workers/`, `llm/memory.py`, `llm/tools/`, `routes/conversations.py`, `repositories/{conversation,message}_repo.py` |

## Decisions

See `docs/adr/`. Every trade-off gets one ADR — the argument does not live in commit messages.

- [ADR-0001](adr/0001-scope-va-data-boundary.md) — scope and data boundary
- [ADR-0002](adr/0002-tech-stack-resolution.md) — resolving the stack conflict between CLAUDE.md, PLAN.md and `.env`
