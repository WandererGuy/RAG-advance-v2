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

Phases 0–4 are done. Phase 5's code is done and waits on a human gate.

- Working today: synchronous ingest, dense retrieval, `make eval` over the 29-question golden set,
  and an API serving `POST /api/v1/chat`, `POST /api/v1/documents`, `GET /api/v1/documents`,
  `GET /api/v1/health`, plus a Streamlit page (`make ui`).
- The `naive-v1` baseline **is committed**: `results/naive-v1.json` and `results/leaderboard.md`.
- Not built: multi-turn memory, function calling, streaming, async workers, auth, OCR, reranking,
  hybrid retrieval — all Phase 6 and later.
- Phase 5's Definition of Done is open: PLAN.md asks that someone outside the team click through the
  UI without instructions, and nobody has ([docs/progress/phase-5.md](docs/progress/phase-5.md)).

## How it works

`PDF/DOCX → parse → chunk → embed → pgvector → retrieve top-k → prompt → answer + citations`

- **Character-window chunking, `chunk_size=800` / `chunk_overlap=100`**, not token-based. Each page
  is chunked on its own, so **a chunk never spans a page break** — that is precisely why a citation
  carries an exact page rather than a guess. Cut points snap backwards to the nearest paragraph →
  sentence → line → word boundary, so no chunk ends mid-word
  ([chunking.py](backend/app/llm/rag/chunking.py)).
- **Page numbers survive the whole pipeline**: `Page.page_no` (1-based, PyMuPDF) → `TextChunk.page_no`
  → the `chunks.page_no` column → `c.page_no` in the prompt → the `[filename, p.N]` string in the
  answer → `parse_citations()` reading it back and resolving it against the chunks actually
  retrieved. A citation naming a source that was never retrieved is counted as `unsupported`.
- **Retrieval is pure dense, top_k=5, cosine distance** over pgvector with an HNSW index
  (`vector_cosine_ops`, `m=16`, `ef_construction=64`). No reranking, no hybrid, no metadata filter,
  no score threshold — `naive-v1` is deliberately the dumbest possible reference point
  ([dense.py](backend/app/llm/rag/retrievers/dense.py)).
- **The prompt forces citations and forces refusal**: `answer_v1.jinja` states five binding rules —
  use only the DOCUMENTS section, cite `[filename, p.N]` after every claim, and when the context is
  insufficient reply with **exactly one sentence**, `Không tìm thấy thông tin trong tài liệu.`, and
  nothing else. When retrieval returns nothing the LLM is not called at all: refusal is the only
  correct output.
- **Vietnamese-specific handling**: the sentence-splitting regex requires a terminator to be
  **followed by whitespace**, so "6.3. Trong thời gian" is not cut inside the clause number; and
  `is_refusal()` normalises Unicode before matching, so a decomposed diacritic never decides a metric.

## Evaluation

A 29-question golden set ([backend/eval/datasets/golden_qa.v1.jsonl](backend/eval/datasets/golden_qa.v1.jsonl))
over a **frozen** corpus ([ADR-0005](docs/adr/0005-frozen-corpus-for-the-golden-set.md)): 16
`factual`, 8 `multi_hop`, 5 `unanswerable`. Every line carries verified `relevant_chunk_ids` and a
mandatory `author` field.

- **Retrieval (arithmetic, not model-scored):** `recall@5`, `MRR`, `nDCG@5`, over the 24 answerable
  questions only.
- **Generation (LLM-as-judge, 1–5):** `faithfulness` scores every question — is the answer fully
  contained in the context it was given — while `answer_relevance` scores only answerable ones
  against `ground_truth`. The judge returns JSON; a parse failure records `None`, never a default
  score.
- **Refusal and citations (arithmetic):** `refusal_accuracy`, `over_refusal_rate`, `citation_rate`,
  `unsupported_citations`.
- **~3 provider calls per question**: one answer, one faithfulness judgement, one relevance
  judgement (`unanswerable` questions skip relevance, so they cost two). About 82 calls per
  29-question run.

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
not.

## Stack

Python 3.12 (`uv`) · FastAPI · PostgreSQL 16 + pgvector, async via SQLAlchemy 2.x + `asyncpg` ·
Alembic · PyMuPDF (PDF) / `python-docx` (DOCX) · LiteLLM with the models read from `.env` — currently
OpenAI `gpt-5.6-luna` for generation and `text-embedding-3-large` at **768 dimensions** (native
truncation) · Jinja2 prompts versioned in the filename · Streamlit for the demo UI · pytest.

Models are **pinned, never a moving alias** — an alias changes silently underneath a frozen
pipeline, and the results file would then name a configuration that no longer identifies what ran.
`gpt-5.6-luna` rejects `temperature=0`, so the parameter is omitted and results record
`temperature: null` ([ADR-0008](docs/adr/0008-provider-migration-to-openai.md)).

Celery + Redis, Chonkie and LangChain / LangGraph are **deliberately not in v1**.
[ADR-0002](docs/adr/0002-tech-stack-resolution.md) records the reasoning and a named trigger for
revisiting each.

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

`--stop` frees ports 8000 and 8501 by port, not just by pidfile, so it also clears a server started
by hand with `make api` / `make ui`. Both ports are overridable: `API_PORT=8080 ./scripts/start.sh`.

**Running on a remote box?** Those `127.0.0.1` URLs — and the `0.0.0.0` / `localhost` ones Streamlit
prints — only work in a browser *on the server itself*. `0.0.0.0` is a bind address meaning "listen
on every interface", not a destination you can visit; from your laptop both it and `localhost` point
at your laptop, where nothing is running. Use the server's own address instead
(`http://<server-ip>:8501`), and set `PUBLIC_HOST=<server-ip>` to have the script print it for you.
The **API binds to localhost only** and is not reachable that way — that is deliberate, since it has
no auth and every `/chat` call spends a metered key. The Streamlit page calls it from the server
side, so the UI works regardless; to hit the API yourself, tunnel it:
`ssh -L 8000:127.0.0.1:8000 <user>@<server>`.

To run the pieces separately instead, `make api` and `make ui` still work in two terminals. Every
target runs from the repository root; the Makefile handles the `cd backend`.

## Scope

**In scope for v1 (Phases 0–5):** text-based PDF and DOCX · single-turn questions, no auth, no
permissions · an answer with citations or an explicit refusal · synchronous ingest · every question
recorded to the `queries` table.

**Out of scope for v1:** async workers, conversation memory, function calling, streaming,
document-level permissions, OCR, Qdrant. Those directories exist but stay empty until there is a
concrete reason and an ADR.

## Working rules

1. **A pipeline with committed results is frozen.** New idea → new pipeline file, new name. Editing
   `naive_v1.py` (or `answer_v1.jinja`) after `results/naive-v1.json` is committed destroys
   comparability between runs.
2. **Every number goes into `results/*.json` and gets committed — including the bad ones.** No
   verbal reporting. Negative results are information.

## Operational notes

- **Changing the embedding model means `make reembed`, never `make ingest FORCE=1`.** `FORCE=1`
  deletes and reinserts chunks, which **reassigns chunk ids** and invalidates every
  `relevant_chunk_ids` in the golden set. `make reembed` UPDATEs in place, so chunk ids,
  `corpus.lock.json` and the golden set all survive. The corpus is frozen and `make validate` fails
  loudly when this happens ([ADR-0005](docs/adr/0005-frozen-corpus-for-the-golden-set.md),
  [ADR-0008](docs/adr/0008-provider-migration-to-openai.md)).
- **Any HTTP upload is a corpus change too.** `POST /documents` deliberately has **no** `force`
  parameter, so it cannot reassign the ids of existing documents — but run `make validate` after any
  upload session regardless.
- **The API has no auth and no rate limit**, and every `/chat` call spends a metered key. Do not
  expose it beyond a laptop or a trusted network.
- Other targets: `make validate` · `make find Q="phụ cấp"` · `make eval P=naive-v1` · `make report` ·
  `make test` · `make lint` · `make fmt` · `make psql` · `make logs` · `make down` ·
  `make revision M="…"`.
- Further reading: [docs/progress.md](docs/progress.md) (phase status, what is blocked on a human),
  [CLAUDE.md](CLAUDE.md) (working rules), [PLAN.md](PLAN.md) (roadmap),
  [docs/architecture.md](docs/architecture.md) (layering and the phase → directory map).
