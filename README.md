# rag-chatbot

Vietnamese version: [README.vi.md](README.vi.md).
Bản tiếng Việt giới thiệu ở: [README.vi.md](README.vi.md).

Q&A over internal company documents: users ask in Vietnamese, the system answers **with citations**
(document name + page number), or explicitly refuses when the documents do not contain the answer.

The v1 corpus is 8 Vietnamese HR documents (employee handbook, compensation and benefits, grading,
leave and remote work, information security, hiring, code of conduct, travel expenses) — 16 pages,
34 chunks. These are **synthetic** demo documents for a fictional company, not real data, so they
are committed to the repo at [data/raw/HR_pdfs/](data/raw/HR_pdfs/) and are safe to open, quote and
share ([ADR-0001](docs/adr/0001-scope-va-data-boundary.md)).

## Example

Both examples below are real output, taken from [results/naive-v1.json](results/naive-v1.json) — the
committed `naive-v1` run over the whole golden set.

```
Q:        Buổi sáng muộn nhất mấy giờ thì mọi người phải có mặt?
          ("What is the latest anyone has to be in, in the morning?")
A:        10:00 là giờ muộn nhất phải có mặt trong khung giờ bắt buộc (core hours).
          [01_so_tay_nhan_vien.pdf, p.1]
Citation: 01_so_tay_nhan_vien.pdf, page 1 (chunk 2) — supported: true
Latency:  retrieval 377 ms · generation 1427 ms
```

The case where the documents hold no answer — the system **refuses** rather than guessing:

```
Q:        Mỗi tháng được hỗ trợ bao nhiêu tiền bữa trưa?
          ("How much lunch allowance is there per month?")
A:        Không tìm thấy thông tin trong tài liệu.
          ("No information found in the documents.")
Citation: (none)
```

That refusal sentence is a **fixed string** (`REFUSAL_MARKER` in
[backend/app/llm/rag/pipelines/base.py](backend/app/llm/rag/pipelines/base.py)), injected into the
prompt and matched back by `is_refusal()`. The safety-critical metric of this project does not
depend on a model's judgement.

## Status

- **Working today:** synchronous ingest, dense retrieval, `make eval` over the 29-question golden
  set, an API serving `POST /api/v1/chat`, `POST /api/v1/documents`, `GET /api/v1/documents`,
  `GET /api/v1/health`, and a Streamlit page (`make ui`).
- **Committed baseline:** `results/naive-v1.json` and `results/leaderboard.md`. Phase 6 is under
  way — its first experiment, `hybrid-v2`, **lost and was committed anyway**
  ([ADR-0009](docs/adr/0009-hybrid-retrieval-not-adopted.md)).
- **Not built:** multi-turn memory, function calling, streaming, async workers, auth, OCR,
  reranking. Those directories stay empty until there is a concrete reason and an ADR.
- **Open gate:** Phase 5's Definition of Done asks that someone outside the team click through the
  UI without instructions, and nobody has ([docs/progress/phase-5.md](docs/progress/phase-5.md)).

## How it works

`PDF/DOCX → parse → chunk → embed → pgvector → retrieve top-k → prompt → answer + citations`

- **Page numbers survive the whole pipeline**: `Page.page_no` (1-based, PyMuPDF) → `TextChunk.page_no`
  → the `chunks.page_no` column → `c.page_no` in the prompt → the `[filename, p.N]` string in the
  answer → `parse_citations()` reading it back and resolving it against the chunks actually
  retrieved. A citation naming a source that was never retrieved is counted as `unsupported`. Each
  page is chunked on its own, so a chunk never spans a page break — which is why a citation carries
  an exact page rather than a guess ([chunking.py](backend/app/llm/rag/chunking.py)).
- **Retrieval is pure dense, top_k=5, cosine distance** over pgvector with an HNSW index. No
  reranking, no hybrid, no metadata filter, no score threshold — `naive-v1` is deliberately the
  dumbest possible reference point ([dense.py](backend/app/llm/rag/retrievers/dense.py)).
- **The prompt forces citations and forces refusal** — five binding rules in
  [answer_v1.jinja](backend/app/llm/prompts/answer_v1.jinja). When retrieval returns nothing the LLM
  is not called at all: refusal is the only correct output.

## Evaluation

A 29-question golden set ([backend/eval/datasets/golden_qa.v1.jsonl](backend/eval/datasets/golden_qa.v1.jsonl))
over a **frozen** corpus ([ADR-0005](docs/adr/0005-frozen-corpus-for-the-golden-set.md)): 16
`factual`, 8 `multi_hop`, 5 `unanswerable`, each line carrying verified `relevant_chunk_ids` and a
mandatory `author` field. Retrieval, refusal and citation metrics are arithmetic; `faithfulness` and
`answer_relevance` are LLM-judged 1–5 ([ADR-0006](docs/adr/0006-how-generation-is-scored.md)).

The committed `naive-v1` numbers — read [ADR-0004](docs/adr/0004-agent-authored-golden-set.md)
**before** quoting any of them:

| recall@5 | MRR | nDCG@5 | faithful | relevance | refusal | cite ok | p50 |
|---|---|---|---|---|---|---|---|
| 0.958 | 0.840 | 0.857 | 4.897 | 4.250 | 1.000 | 1.000 | 2009 ms |

Two limits go with them. The 29 questions were **written by the agent, not a human** — retrieval
metrics are inflated most by this. And the **judge is the answering model** (one provider is
configured), so `faithfulness` and `answer_relevance` are self-graded and biased upward
([ADR-0006](docs/adr/0006-how-generation-is-scored.md)). The retrieval and refusal columns are
deterministic and are not. Relative comparison between pipelines is valid; the absolute values are
not — and generation metrics do not reproduce run to run, so never read a single one on its own.

## Stack

| Layer | Choice | Notes |
|---|---|---|
| **Language** | Python 3.12 | dependencies and venv managed with `uv` |
| **API** | FastAPI + uvicorn | `python-multipart` for the upload route |
| **Database** | PostgreSQL 16 + pgvector | `pgvector/pgvector:pg16`, HNSW index (`vector_cosine_ops`) |
| **ORM** | SQLAlchemy 2.x + `asyncpg` | fully async; migrations with Alembic |
| **Generation** | `gpt-5.6-luna` (OpenAI) | via LiteLLM, model name read from `.env` |
| **Embedding** | `text-embedding-3-large` | **768 dim** by native truncation |
| **Parsing** | PyMuPDF · `python-docx` | PyMuPDF gives the exact page number a citation needs |
| **Prompts** | Jinja2 | version in the filename — `answer_v1.jinja` |
| **Frontend** | Streamlit | an optional `frontend` extra, so the API deploys without it |
| **Config / logging** | `pydantic-settings` · `structlog` | all config through `core/config.py`, JSON logs |
| **Test / lint** | pytest + `pytest-asyncio` · ruff · mypy | the `dev` extra |

The baseline retrieval parameters — `chunk_size=800`, `chunk_overlap=100`, `top_k=5` — are read from
`.env` and are what `naive-v1` was measured at.

Three constraints behind this table are worth knowing before changing anything in it:

- **Models are pinned, never a moving alias.** An alias changes silently underneath a frozen
  pipeline, and the results file would then name a configuration that no longer identifies what ran.
- **`gpt-5.6-luna` rejects `temperature=0`**, so the parameter is omitted and every results file
  records `temperature: null` ([ADR-0008](docs/adr/0008-provider-migration-to-openai.md)). Every run
  therefore samples — which is why generation metrics do not reproduce exactly.
- **768 is written in three places that must change together**: `.env`, `app/models/chunk.py`, and
  the initial migration. Changing it is a migration plus a re-embed plus a re-run of every pipeline.

Celery + Redis, Chonkie and LangChain / LangGraph are deliberately not in v1, each with a named
trigger for revisiting ([ADR-0002](docs/adr/0002-tech-stack-resolution.md)).

## Running it

First time — set up the environment and load the corpus:

```bash
cp .env.example .env    # fill DEFAULT_LLM_API_KEY + EMBEDDING_API_KEY (OpenAI)
make install            # uv sync --extra dev
make up                 # docker compose up -d --wait
make migrate            # alembic upgrade head
make ingest             # defaults to --path ../data/raw
```

After that, [scripts/start.sh](scripts/start.sh) brings up the whole stack in one command —
postgres → migrations → API → Streamlit, each step waited on before the next:

```bash
./scripts/start.sh          # API on :8000, UI on :8501
./scripts/start.sh --stop   # stops API + UI (postgres keeps running)
```

| | |
|---|---|
| API docs | http://127.0.0.1:8000/docs |
| Health | http://127.0.0.1:8000/api/v1/health → `{"status":"ok","database":"up"}` |
| UI | http://127.0.0.1:8501 |
| Logs | `.run/api.log` · `.run/ui.log` |

A smoke test against a running stack, answering from the committed corpus:

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"question":"Nhân viên được nghỉ phép bao nhiêu ngày một năm?"}'
# → "Nhân viên chính thức được nghỉ 15 ngày phép/năm; cứ 03 năm làm việc liên tục được cộng
#    thêm 01 ngày, tối đa 20 ngày. [04_nghi_phep_va_lam_viec_tu_xa.pdf, p.1]"
```

**On a remote host, or need to change ports?** Those `127.0.0.1` URLs only work in a browser on the
server itself. [docs/running.md](docs/running.md) covers remote access (including the EC2 public-IP
detection built into `start.sh`), port overrides, and what `--stop` actually stops.

## Operational notes

- **The API has no auth and no rate limit**, and every `/chat` call spends a metered key. Do not
  expose it beyond a laptop or a trusted network.
- **Changing the embedding model means `make reembed`, never `make ingest FORCE=1`.** `FORCE=1`
  reassigns chunk ids and invalidates every `relevant_chunk_ids` in the golden set. An HTTP upload
  is a corpus change too — `POST /documents` has no `force` parameter, but run `make validate` after
  any upload session ([ADR-0005](docs/adr/0005-frozen-corpus-for-the-golden-set.md),
  [ADR-0008](docs/adr/0008-provider-migration-to-openai.md)).
- Other targets: `make validate` · `make find Q="phụ cấp"` · `make eval P=naive-v1` · `make report` ·
  `make test` · `make lint` · `make fmt` · `make psql` · `make logs` · `make down` ·
  `make revision M="…"`.
- Further reading: [docs/progress.md](docs/progress.md) (phase status, what is blocked on a human),
  [CLAUDE.md](CLAUDE.md) (the working rules, in full), [PLAN.md](PLAN.md) (roadmap),
  [docs/architecture.md](docs/architecture.md) (layering and the phase → directory map).
