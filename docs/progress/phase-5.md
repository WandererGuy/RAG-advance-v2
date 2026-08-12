## Phase 5 — API + thin frontend ✅ code done — **the demo gate is not human-signed**

**Built** 2026-08-12

`app/api/deps.py` · `app/api/v1/routes/{chat,documents}.py` · `app/schemas/{__init__,chat,document}.py` ·
`app/services/{chat_service,document_service}.py` · `app/repositories/query_repo.py` ·
`frontend/app.py` (Streamlit) · `tests/integration/test_api.py` · `tests/unit/test_schemas.py` ·
`make ui` · `DocumentRepository.list_with_chunk_counts`.

Three endpoints beyond `/health`: `POST /chat` (single-turn), `POST /documents` (upload +
synchronous ingest), `GET /documents` (list + status). `queries` is written for the first time.

### Evidence

| Check | Result |
|---|---|
| `make lint` | ruff + mypy clean, **57** source files (48 before) |
| `make test` | **148 passed** (132 before) — 16 new, 8 of them integration against real Postgres |
| `make validate` | PASS — corpus lock intact, 34 chunks, 29 questions, all `author:agent` — **re-run after the upload tests**, which is the point |
| `GET /api/v1/health` | `{"status":"ok","database":"up"}` |
| `GET /api/v1/documents` | 8 documents, real chunk counts (`08_cong_tac_phi.pdf` → 4 chunks, 2 pages) |
| `POST /documents` (`.txt`) | **415**, listing the supported suffixes |
| `POST /documents` (corpus PDF again) | `{"status":"skipped","document_id":8,"chunk_count":4}` — **the frozen corpus was not touched** |
| `POST /documents` (new `.docx`) | `{"status":"ingested","document_id":9,"chunk_count":1,"page_count":null}` |
| `POST /chat` (factual) | answered with a resolving citation, `query_id` written |
| `POST /chat` (out of corpus) | `refused: true`, 0 citations, still recorded as `query_id` 2 |
| `make ui` | Streamlit serves on :8501; the render path exercised against the live API, no exception |

The two `/chat` calls, which are also the proof that `queries` is no longer empty:

```
Q: Chính sách nghỉ phép năm là bao nhiêu ngày?
A: Nhân viên chính thức được 15 ngày phép/năm; cứ 03 năm làm việc liên tục được cộng thêm
   01 ngày, tối đa 20 ngày. […] [04_nghi_phep_va_lam_viec_tu_xa.pdf, p.1]
   refused=false · citations=1 (supported, chunk_id 15) · 6110 ms · query_id 1

Q: Công ty có chính sách nuôi thú cưng tại văn phòng không?
A: Không tìm thấy thông tin trong tài liệu.
   refused=true · citations=0 · query_id 2
```

```
 id | pipeline_name | latency_ms | retrieved_chunk_ids
----+---------------+------------+---------------------
  1 | naive-v1      |       6110 | {15,14,17,16,4}
  2 | naive-v1      |       1689 | {28,16,2,27,17}
```

**The upload tests were cleaned up and the corpus restored.** The `.docx` written to prove the
upload path (document 9, 1 chunk) was deleted and `data/uploads/` emptied, because the corpus is
frozen under [ADR-0005](../adr/0005-frozen-corpus-for-the-golden-set.md) and a ninth document
would have invalidated `corpus.lock.json`. `make validate` PASSes and the database is back to
**8 documents / 34 chunks**. The `.docx` was worth ingesting once: it is the only exercise of the
DOCX path, of `page_count: null`, and of the `[filename, p.?]` citation form for a document with
no real pagination — all three parsed correctly.

### Decisions made while building

- **`ChatResponse` is a projection of `RAGAnswer`, not a second model of the domain.**
  `from_answer()` is the only place the mapping is written, and `supported=false` **travels to
  the client** rather than being filtered out here. The API's job is to label a fabricated
  citation; the UI's job is to not render it as a source. The Streamlit page shows those in a
  red block that says not to trust them.
- **A refusal is a 200, not a 404.** "Không tìm thấy thông tin trong tài liệu." is a successful
  and correct answer — the most important one this system produces (ADR-0006) — and the client
  reads the `refused` boolean. The UI styles it as information, not as an error.
- **A failed `queries` INSERT does not cost the user their answer.** `queries` is an
  observability record; the answer has already been produced and paid for by the time it is
  written. On failure the response carries `query_id: null` and the error goes to the log.
- **The upload is written to `data/uploads/` before ingest, not to a temp directory.**
  `documents.source_path` records where a file lives, and a path under a `TemporaryDirectory`
  would dangle the moment the request finished. A failed *or skipped* upload deletes its copy
  again, so a re-upload of an unchanged document does not grow the directory.
- **Uploads land in `data/uploads/`, never in `data/raw/HR_pdfs/`** — that directory is the
  frozen corpus, and an upload must not silently join it.
- **`GET /documents` is one LEFT JOIN + GROUP BY**, not a count per row: it renders the whole
  table, and a per-document count would be an N+1 growing with the corpus. LEFT so a `failed`
  document with no chunks still appears — that row is the one worth seeing.
- **`get_db` never commits and rolls back on an unhandled error.** A service that writes decides
  when its write is final; a route that raised must not leave a half-written transaction for
  whatever runs next on that connection.
- **`source_path` and `file_hash` are not exposed.** The path is a server filesystem detail and
  the hash is the idempotency key; publishing the path is how an absolute path ends up in a
  demo screenshot.
- **`health.py`'s local session dependency is deleted**, as Phase 1 promised — it now uses
  `deps.DbSession` like every other route.
- **`python-multipart` became a runtime dependency**, not a dev one: FastAPI refuses to *build*
  the upload route without it, at import time. Streamlit and `requests` are an optional
  `frontend` extra — the API must be deployable without the UI, which is a client, not a part
  of the service.

### Deviations from PLAN.md

- **No `get_pipeline` FastAPI dependency.** PLAN.md lists one in `deps.py`; the pipeline needs
  the request's session, so building it inside `chat_service` (which already has the session)
  is one seam instead of two. The registry indirection PLAN.md was protecting is intact:
  `chat_service` calls `build_pipeline(settings.pipeline_name, session)` and never imports
  `NaiveV1`.
- **`IngestResponse` is not in PLAN.md's schema list.** `POST /documents` needed a body that
  distinguishes `skipped` from `ingested`; re-uploading the same bytes is a no-op by design,
  and a UI reporting "ingested" would make a silent no-op look like work.
- **A per-document ingest failure is surfaced as 422**, with the reason in `detail`. The service
  returns those rather than raising, but a request whose file cannot be turned into chunks —
  most often a scanned PDF — is not a success and must not be rendered as one.
- **`tests/integration/test_api.py` overrides `get_db`** to point at the test database. That is
  dependency injection, not a mock (CLAUDE.md 5.5): same session type, same schema, same SQL.
  The chat test runs on an *empty* corpus, where retrieval returns nothing and `naive-v1`
  refuses without calling the LLM at all — so it proves the wiring
  (route → service → pipeline → repository → `queries`) for the price of one embedding call.
  Answer quality is `eval/runner.py`'s job, against the frozen corpus and the golden set.
- **`MAX_QUESTION_CHARS = 1000` and `MAX_UPLOAD_BYTES = 25 MB`** are not in PLAN.md. Ingest is
  synchronous and both paths spend someone's metered key.

### Open

- 🛑 **The Definition of Done is not met, and it is a human gate.** PLAN.md asks that *"someone
  outside the team can click through it without instructions"*. The UI serves, renders the
  corpus and answers real questions — that is verified — but **no person outside the team has
  used it**, and an agent cannot sign that. This is the same shape as the Phase 2 sign-off.
- **`queries` holds 2 rows, both from this verification.** PLAN.md's second DoD clause is "the
  `queries` table has real data after the demo session"; these are agent-generated. The table
  is wired and proven, and it fills with real traffic the first time a human uses the UI.
- **The Streamlit UI has no test.** It is a client with no logic worth asserting, and its render
  path was exercised against the live API by hand. If it grows logic, that stops being true.
- **`POST /documents?force=true` is exposed and is genuinely dangerous** — it deletes and
  re-inserts a document's chunks, which **reassigns chunk ids** and silently invalidates
  `relevant_chunk_ids` in the golden set (ADR-0005). It is there because a genuinely re-uploaded
  document needs it, not because it is safe to click. The route's docstring says so; nothing
  enforces it.
- **An upload is ingested with the *current* embedding model** and joins a corpus embedded with
  whatever model was current when it ran. After an embedding-model change, `make reembed` covers
  existing chunks; a document uploaded in between is the case nothing checks.
- **`backend/.env` still exists**, emptied and marked dead. Deleting it has now been blocked by a
  permission prompt four times. Carried from Phase 1.
- **No auth, no permissions, no rate limit.** In scope for v1 (CLAUDE.md 2), and the reason this
  must not be exposed beyond a laptop or a trusted network — `POST /chat` spends a metered key
  on every call.

### What you can do after this phase

**Available:** a working demo, end to end. Upload a PDF or DOCX through the browser, ask a
question in Vietnamese, get an answer with clickable citations that show the cited snippet and
its `chunk_id`. `GET /documents` shows every document's status, page count and chunk count, and
every question asked is recorded in `queries` with its pipeline, latency and retrieved chunk ids.
The served pipeline is whatever `PIPELINE_NAME` names in `.env`, resolved through the registry.
What does **not** exist yet: multi-turn (each question is independent), streaming, auth, a second
pipeline to compare against, and any background processing — a large upload holds the request
open for as long as embedding takes.

**Commands that work at this point:**

```bash
make up && make migrate
make ingest                                # idempotent: skips all 8
make validate                              # golden set + frozen corpus lock
make test                                  # 148 passed
make lint                                  # 57 source files, clean
make report                                # -> results/leaderboard.md
make psql

make api                                   # terminal 1 — http://localhost:8000/docs
make ui                                    # terminal 2 — http://localhost:8501
```

```bash
curl -s localhost:8000/api/v1/health
curl -s localhost:8000/api/v1/documents | python3 -m json.tool

curl -s -X POST localhost:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"question":"Chính sách nghỉ phép năm là bao nhiêu ngày?"}' | python3 -m json.tool

# Upload. Without ?force=true a known document is skipped, which is what you want.
curl -s -X POST localhost:8000/api/v1/documents -F "file=@/path/to/tai-lieu.pdf"
```

```sql
SELECT count(*) FROM documents;    -- must stay 8
SELECT count(*) FROM chunks;       -- must stay 34
SELECT id, question, pipeline_name, latency_ms, retrieved_chunk_ids
  FROM queries ORDER BY id DESC LIMIT 20;   -- what people actually asked
```

**Technical, possible now:** read `queries` after a demo session — it is the first real evidence
of what people ask, and the raw material for a `golden_qa.v2.jsonl` grown from traffic instead of
imagination (ADR-0004 names this as a trigger). Point `PIPELINE_NAME` at a different registered
pipeline and the API serves it with no code change; there is only one today, which is exactly
what Phase 6 fixes. Watch `latency_ms` in `queries` against the baseline's `p50 3281 ms`.

**Non-technical, possible now:** **use it, and let someone outside the team use it** — that is
the Definition of Done and the one thing blocking this phase from being signed. Watch where they
hesitate, whether the citations are enough to make them trust an answer, and what they type that
the system refuses. Then decide the `refusal_accuracy` question still open from Phase 4: an
employee asking something the handbook does not cover currently gets one flat sentence — is that
what you want them to see, or should it hedge and name the nearest real fact? And the standing
highest-leverage action is unchanged: read `golden_qa.v1.jsonl` and rewrite the weakest questions
as `v2` under your own name.

**Notice:** **`?force=true` on an upload reassigns chunk ids and silently invalidates the golden
set** — the same trap as `make ingest FORCE=1` (ADR-0005), now reachable from an HTTP call. Run
`make validate` after any upload session; it is the only thing that catches it. An upload joins
the frozen corpus, so ingesting a document to "try it out" changes what every future eval run
measures — delete it and re-validate, as this phase did. There is **no auth and no rate limit**:
every `/chat` call spends a metered key, so do not expose this beyond a laptop. Ingest is
synchronous and capped at 25 MB. A citation with `supported: false` names a source the model was
never given — the UI marks those in red and they must never be read as a real source. And
`refusal_accuracy` 0.6 travels with every quotation of the baseline's numbers.

**For the next phase (6 — improvements, one pipeline at a time):** the serving path is now
config, not code — a new pipeline is one file, one import in `pipelines/__init__.py`, and a
`PIPELINE_NAME` change to serve it; `make eval P=<name>` already works for any registered name.
Change **exactly one variable** per pipeline (CLAUDE.md 5.4) and never edit `naive_v1.py`. Phase 4
left the target: `recall@5` is 0.958 with almost no headroom, so hybrid retrieval must prove
itself in **MRR, nDCG and `answer_relevance`**, not recall — and the highest-value target is not
retrieval at all but `refusal_accuracy` 0.6, which is a prompt-and-detector question waiting on
the human decision above. `temperature` is `null`, so a small gap between two pipelines may be
noise. Results files are immutable and negative results get committed too.
