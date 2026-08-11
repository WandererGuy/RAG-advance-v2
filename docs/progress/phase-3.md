## Phase 3 — Golden set ✅ done (questions agent-authored, not human-written)

**Built** 2026-08-11

`eval/datasets/golden_qa.v1.jsonl` (29 questions) · `eval/datasets/validate.py` ·
`eval/datasets/corpus.lock.json` · `eval/datasets/README.md` · `scripts/find_chunks.py` ·
`DocumentRepository.search_text` + `.all_chunks_for_lock` ·
[ADR-0005](../adr/0005-frozen-corpus-for-the-golden-set.md) ·
`tests/unit/test_validate_golden.py` (21 tests) · `make find`, `make validate`.

**The gate.** PLAN.md and CLAUDE.md 5.6 reserved the questions for a human. Nobody was ever named,
so on 2026-08-11 the project owner authorised the agent to write them under
[ADR-0004](../adr/0004-agent-authored-golden-set.md). **Every line is `"author": "agent"`, and
`make validate` prints a warning saying so on every run.** Read ADR-0004's inflation table before
quoting any Phase 4 number: retrieval metrics are inflated most, `refusal_accuracy` is the least
trustworthy, and the numbers are fit for comparing pipelines to each other and nothing else.

### Definition of Done

`golden_qa.v1.jsonl` has ≥20 lines and `python -m eval.datasets.validate` passes.

```
$ make validate
golden_qa.v1.jsonl: 29 question(s)
  factual        16
  multi_hop      8
  unanswerable   5
  author:agent   29
warning: every question is agent-authored: read ADR-0004 before quoting any number produced against this dataset
PASS
```

| Check | Result |
|---|---|
| questions | 29 (16 `factual` · 8 `multi_hop` · 5 `unanswerable`) — PLAN.md asked for 20–30 with 3–5 unanswerable |
| `make validate` | PASS, including all 34 chunk ids resolving against the live database |
| `make lint` | ruff + mypy clean, **33** source files (`mypy` now covers `eval/` and `scripts/`, not only `app/`) |
| `make test` | **52 passed** (31 before + 21 new) |
| `make ingest` | `ingested 0 · skipped 8 · failed 0`, chunks still 34 — the frozen corpus is intact |

### How the questions were written

ADR-0004's method constraints, and what each cost:

- **Drafted from the rendered PDF pages, not from chunk text.** All 16 pages were rendered at
  110 dpi and read as images before a single question was written, so the chunker's vocabulary
  and its 800/100 boundaries could not leak into the questions.
- **Paraphrased away from the source sentence.** `q002` asks about *"quên ghi nhận giờ làm"* where
  the document says *"chấm công"*; `q015` asks for *"tiền phòng ngủ"* against a table headed
  *"Khách sạn"*. A question that reuses the document's own noun phrase tests string matching.
- **Chunk ids looked up afterwards** with `make find`, never from memory.
- **`unanswerable` are in-domain near-misses.** Four of the five have adjacent, retrievable
  content the system will be tempted to answer from: `q025` asks how the year-end bonus is
  prorated across maternity leave — the corpus has the 06-month entitlement and two other bonus
  proration rules, but nothing joining them. `q027` asks the premium for insuring a parent, where
  the table says only *"tự nguyện, tự đóng phí"*. The remaining one (`q029`, a seniority bonus)
  was confirmed absent with `make find Q="thâm niên"` → no chunk.
- **Two questions aim at the flattened tables** Phase 2 flagged as the likeliest Phase 4 failures:
  `q021` (violation severity → sanction) and `q024` (region → hotel cap, plus the cabin-class
  exception). Neither touches the truncated cell in document 05.

### Decisions made while building

- **The corpus is frozen and the freeze is machine-checked** — `corpus.lock.json`, and
  [ADR-0005](../adr/0005-frozen-corpus-for-the-golden-set.md) for why a README note was not enough.
  This closes the Phase 2 open item that a `FORCE=1` re-ingest silently invalidates every
  `relevant_chunk_ids`. It is now a loud failure in `make validate`, naming what happened.
- **`author` is per line, not per file.** A `v2` written by a person will land beside agent lines
  during the transition, and a file-level label would go stale the moment it does.
- **`validate.py` rejects unknown fields.** A typo'd key is silent data loss — the runner would
  simply never read it, and the question would score as if the field had never been intended.
- **`search_text` uses ILIKE, not `to_tsvector`.** Postgres ships no Vietnamese text-search
  configuration; the English stemmer would quietly return the wrong rows. A substring match is
  the honest primitive for a lookup tool, and it is explicitly not a retriever — it returns
  `ChunkMatch`, which has no score field, so nothing can compare it against a retrieval result.
- **`multi_hop` requires ≥2 chunk ids, enforced.** Without the check the label drifts to mean
  "hard question" and the type distribution stops meaning anything.
- **`mypy` now runs over `eval/` and `scripts/` too.** They were outside the lint scope and are
  about to hold the evaluation logic every number depends on.

### Deviations

- **29 questions, not the 20 the Definition of Done requires.** The corpus is 8 documents; 20
  would have left whole documents uncovered.
- **`corpus.lock.json`, `find_chunks.py`'s `--full` flag and the `make find`/`make validate`
  targets are beyond PLAN.md's Phase 3 list.** The lock has its own ADR. The rest is what made
  writing 29 questions against 34 chunks practical.
- **`scripts/ingest_corpus.py`'s closing hint changed** from "eyeball 5 random chunks" (the Phase 2
  human gate, now taken) to `make validate` (the frozen-corpus check, now the thing that matters
  after any ingest).
- **21 unit tests for a validator PLAN.md describes in one line.** The validator is the only
  thing that can catch a silently invalidated dataset, and a validator that passes when it should
  fail is worse than no validator.

### Open

- **Nobody has reviewed the questions.** The whole of ADR-0004 is this open item. The single most
  valuable human action available on this project is reading `golden_qa.v1.jsonl` and rewriting it
  as `golden_qa.v2.jsonl` — the ADR lists the triggers that make it mandatory rather than merely
  better.
- **`ground_truth` for the 5 `unanswerable` questions is prose about what the system must not do.**
  The Phase 4 judge prompt has to handle that shape deliberately; scoring a refusal against it as
  if it were a factual answer will produce nonsense.
- **`make find` exits 1 when nothing matches**, so `make` prints `Error 1`. That is grep-like and
  intentional — but it reads like a build failure at a glance.
- **`backend/.env` still exists** with a duplicate of both API keys; deleting it is still blocked
  by a permission prompt. Carried from Phase 1.

### What you can do after this phase

**Available:** a frozen 34-chunk corpus, 29 questions with verified chunk citations, a validator
that fails loudly when the two drift apart, and a keyword lookup tool for writing more. There is
still **no retrieval, no LLM call and no scoring** — `retrievers/`, `pipelines/`, `eval/runner.py`,
`eval/metrics/` and `results/` are all Phase 4. Nothing has been measured yet.

**Commands that work at this point:**

```bash
make up && make migrate                    # bring the environment back
make ingest                                # idempotent: skips all 8
make validate                              # golden set + frozen corpus lock
make find Q="phụ cấp"                      # chunk_id + page + snippet
make test                                  # 52 passed
make lint                                  # 33 source files, clean
make psql
```

```bash
cd backend
uv run python -m scripts.find_chunks --q "nghỉ phép" --q "31/3" --full   # AND several terms
uv run python -m eval.datasets.validate --no-db                          # structure only
uv run python -m eval.datasets.validate --write-lock                     # re-freeze (see Notice)
```

```sql
SELECT count(*) FROM chunks;                                   -- must stay 34
SELECT id, page_no, left(content, 80) FROM chunks WHERE id IN (5, 16);  -- read a citation
```

**Technical, possible now:** read every question against the chunks it cites and disagree — the
citations are the part most likely to be subtly wrong; add questions (new ids, same file, then
`make validate`); check the type balance against what you expect users to ask; deliberately break
the lock in a scratch database to see the error text; measure how many questions a naive keyword
search would already answer, as a floor for Phase 4 to beat.

**Non-technical, possible now:** **read `golden_qa.v1.jsonl`** — it is 29 lines of Vietnamese and
needs no technical background, and it is the highest-leverage review left on this project. Judge
whether these are the questions employees would actually ask, whether the `unanswerable` five are
genuinely absent from the documents, and whether any `ground_truth` is wrong. Decide whether the
corpus is final, since ADR-0005 now makes adding a document a deliberate, costed act. Rewrite the
weakest questions as `golden_qa.v2.jsonl` and put your own name in `author`.

**Notice:** `--write-lock` **overwrites the freeze** — it makes a lock error disappear without
making the dataset correct, and is only right after a deliberate corpus change. `make ingest
FORCE=1` still renumbers chunk ids; the lock now catches it, but recovery still means looking up
every affected id again. `v1` is frozen: new questions go in `v2`, never as edits here, or two
results files silently describe different measurements. The five `unanswerable` questions are
near-misses on purpose — if Phase 4 shows the system answering them confidently, that is the
finding, not a bad question. And `make validate` warns on every single run that these questions
are agent-authored; do not learn to skip that line.

**For the next phase (4 — `naive-v1` baseline):** the runner must write `dataset_version`,
`golden_set_author` (the sorted distinct `author` values in the dataset) and the `PipelineConfig`
into every `results/*.json`, and `eval/report.py` must show `golden_set_author` as a column in
`leaderboard.md` — CLAUDE.md rule 8 and ADR-0004 both require it, and it is the only thing keeping
an inflated number from being quoted as a plain one. Load the dataset through
`eval.datasets.validate` (or call it first) so a run cannot start against a drifted corpus. Expect
`refusal_accuracy` to look good and trust it least. `q021` and `q024` are the two questions most
likely to fail on the flattened tables; if they do, the fix is a structured extractor with its own
ADR, not a bigger `top_k`.
