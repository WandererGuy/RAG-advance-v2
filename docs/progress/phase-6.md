## Phase 6 — Improvements, one pipeline at a time 🟡 in progress — experiment 1 of 4 done

**Built** 2026-08-12 · **`hybrid-v2` run** 2026-08-12, on OpenAI

`app/llm/rag/retrievers/bm25.py` · `app/llm/rag/retrievers/hybrid.py` ·
`app/llm/rag/pipelines/hybrid_v2.py` · `alembic/versions/002_gin_index_for_bm25_keyword_retrieval.py` ·
`DocumentRepository.search_keyword` · a `Chunk` model index · `tests/unit/test_retrievers_hybrid.py` ·
`tests/integration/test_retrieval.py` · [ADR-0009](../adr/0009-hybrid-retrieval-not-adopted.md).

The first of the four experiments PLAN.md lists. **It is a negative result, and it is committed
as one.** `results/leaderboard.md` now has two rows.

### The result: hybrid retrieval is built, measured, and not adopted

Read [ADR-0004](../adr/0004-agent-authored-golden-set.md) before quoting any of these.

| | recall@5 | MRR | nDCG@5 | faithful | relevance | refusal | p50 ms |
|---|---|---|---|---|---|---|---|
| `naive-v1` | **0.958** | 0.840 | **0.857** | 4.897 | 4.250 | 1.000 | 2009 |
| `hybrid-v2` | 0.938 | **0.844** | 0.845 | 5.000 | **4.542** | 1.000 | **1611** |

Hybrid was aimed at MRR and nDCG — Phase 4 left `recall@5` at 0.958 with no headroom, so "find the
chunk" was already solved and the target was "rank it higher". It missed: nDCG fell, MRR moved by
0.004, and recall fell by half a question. The full reasoning, the per-question breakdown and the
conditions that would reverse the decision are in [ADR-0009](../adr/0009-hybrid-retrieval-not-adopted.md).

**Only 6 of 24 answerable questions changed at all** — hybrid improved 2 (q002 rank 2→1; q017
rank 3→1, RRF working exactly as designed) and degraded 4 (q006, q009, q024 lost a rank; q021 lost
a relevant chunk outright). q021 is the entire recall regression and the diagnostic case: it asks
the penalty for lending a colleague a login account, and the keyword half displaced the
account-policy chunk with two code-of-conduct chunks that share the words `công việc`, `xử lý` and
`vi phạm` while being about something else. The keyword half was confidently wrong and RRF gives
it an equal vote.

**Why the predicted win did not appear:** 8 synthetic HR documents in plain policy Vietnamese
contain almost nothing BM25 exists to catch — no part numbers, no reference codes in the
questions, no rare jargon. This is a result about *this corpus*, not about hybrid retrieval.

### Two runs of the same pipeline do not produce the same generation numbers

`hybrid-v2` was run twice, on identical code against the identical frozen corpus. This is the most
transferable thing the phase learned:

| | run 1 | run 2 (**committed**) |
|---|---|---|
| recall@5 / MRR / nDCG@5 | 0.9375 / 0.8438 / 0.8449 | 0.9375 / 0.8438 / 0.8449 |
| faithfulness | 4.862 | 5.000 |
| answer_relevance | 4.458 | 4.542 |
| refusal_accuracy | **0.8** (1 hallucinated) | **1.0** (0 hallucinated) |

Retrieval is deterministic and reproduced byte-for-byte. Generation is not: `gpt-5.6-luna` rejects
`temperature=0`, so every run samples ([ADR-0008](../adr/0008-provider-migration-to-openai.md)).
**Any generation-metric gap smaller than ~0.2 between two pipelines is indistinguishable from
re-running the same pipeline twice.** `refusal_accuracy` swinging 0.8 → 1.0 with nothing changed is
the clearest warning this project has produced about how much weight a single run can carry — and
it lands on precisely the metric Phase 4 flagged as the one to fix.

The second run is committed. It is not "the better run": it is the run made after
`eval/runner.py` was corrected (below), and the first file was never committed.

### Evidence

| Check | Result |
|---|---|
| `make lint` | ruff + mypy clean, **60** source files (57 before) |
| `make test` | **183 passed** (148 before) — 35 new, 9 of them integration against real Postgres |
| `make validate` | PASS — 8 documents, 34 chunks, ids 1–34, 29 questions, all `author:agent` |
| `make migrate` | `42f575d6dccb -> 8b1c4e7a92d5` clean |
| GIN index actually used | `EXPLAIN` shows `Bitmap Index Scan on ix_chunks_content_tsv_gin`, not a seq scan |
| `make eval P=hybrid-v2` | 29 questions, 0 failures → `results/hybrid-v2.json` |
| `make report` | `results/leaderboard.md`, 2 pipelines |

Retrieval on a real question, showing the mechanism (`08_cong_tac_phi.pdf` is the correct source):

```
Q: Nhân viên đi công tác tỉnh xa được thanh toán phụ cấp bao nhiêu một ngày?

bm25    1. chunk  5  02_quy_che_luong_thuong_phuc_loi.pdf   2.30000
        3. chunk 31  08_cong_tac_phi.pdf                    1.80000
dense   1. chunk 32  08_cong_tac_phi.pdf                    0.64013
        3. chunk 31  08_cong_tac_phi.pdf                    0.59190
hybrid  1. chunk 31  08_cong_tac_phi.pdf   0.03175  via=dense+bm25   <- promoted 3+3 -> 1
        2. chunk 32  08_cong_tac_phi.pdf   0.03154  via=dense+bm25
```

### A real bug found and fixed in `eval/runner.py`

`_run()` hardcoded `retriever="dense"` into the `PipelineConfig` handed to **every** pipeline.
That was correct while dense was the only retriever and became a mislabelling bug the moment a
second one existed: the first `hybrid-v2` run really did use hybrid retrieval, while
`results/hybrid-v2.json` recorded `"retriever": "dense"`. A results file whose whole purpose is to
let a number be traced back to the configuration that produced it was misreporting that
configuration.

The runner now passes no config and lets each pipeline's `build()` name its own retriever.
`results/naive-v1.json` is unaffected — it says `dense`, and it was dense.

### Decisions made while building

- **`simple`, not `english`, as the text-search configuration.** Postgres 16 ships no Vietnamese
  configuration, and `english` stems and stopword-strips Vietnamese as if it were English. Verified
  rather than assumed: `to_tsvector('english', …)` drops `được` and mangles the rest, while
  `simple` preserves every syllable and its diacritics. Same reasoning already recorded on
  `DocumentRepository.search_text`, which is why that one uses ILIKE.
- **OR-of-terms, not `plainto_tsquery`'s AND.** Measured on the real corpus: the natural question
  above matches **zero** chunks under AND and ranks the right document top-3 under OR. A retriever
  that returns nothing for a well-formed question is not a retriever.
- **Stopwords are stripped in Python.** `simple` has no stopword list, so under OR every Vietnamese
  question word (`bao nhiêu`, `là`, `của`) matches nearly every chunk and flattens the ranking. The
  list errs deliberately small — a wrongly dropped term is one the retriever can never match on,
  and that failure is silent. `ngày`, `năm`, `phép` and `lương` look like stopwords and are the
  substance of HR questions; a test asserts they stay out of the list.
- **RRF fuses by rank, never by score.** A cosine similarity and a `ts_rank_cd` share no scale,
  range or distribution. A weighted sum would bake the shape of one corpus into a constant that
  needs re-tuning on every embedding-model change. `K=60` is the paper's value and is deliberately
  **not** tuned here: tuning it on 29 agent-authored questions would fit the constant to the golden
  set rather than to the problem.
- **Each half is asked for 4×k.** Fusing two top-5 lists and taking 5 discards the case RRF exists
  for — a chunk ranked 6th by dense and 1st by keyword. The pipeline still answers from 5 chunks;
  the widening happens below it.
- **The two halves run concurrently** (`asyncio.gather`), so hybrid costs roughly its slower half
  rather than the sum. Visible in the result: p50 1611 ms against the baseline's 2009 ms.
- **A keyword half returning nothing is normal; a keyword half raising is not.** An all-stopword
  question falls through to dense alone. An exception propagates, because a dense-only ranking must
  never be written to a results file labelled `hybrid`.
- **The GIN index is defined in both the migration and the `Chunk` model.** The migration is what
  runs in production; the model declaration is what `create_all` builds for the integration test
  database, so the two schemas do not drift. The expression must stay character-identical in three
  places (migration, model, `search_keyword`) — an expression index is only used for the exact
  expression it was built on, and a mismatch degrades to a sequential scan silently. Confirmed with
  `EXPLAIN` rather than trusted.
- **`hybrid_v2.py` duplicates `naive_v1.py`'s generation half rather than sharing a base class.**
  `naive_v1.py` is frozen (CLAUDE.md 4.1); factoring the common half out would mean editing it.
  Twenty duplicated lines are cheaper than trading away the project's only fixed point. When a
  third pipeline repeats it, extract a base from the *new* pipelines — still not by editing that one.
- **`search_keyword` lives in `DocumentRepository`**, not in `VectorStore`. `VectorStore` is the
  embedding-search seam; widening it with a keyword method would make every implementation carry a
  capability unrelated to vectors.

### Deviations from PLAN.md

- **PLAN.md says "BM25", and this is not Okapi BM25.** Postgres `ts_rank_cd` is a coverage-density
  rank — no `k1`, no `b`, document length handled differently. The file keeps PLAN.md's name and
  the docstring records the difference. Nothing depends on the scores being BM25, because fusion
  is by rank.
- **PLAN.md's order is unchanged but its prediction did not hold.** Hybrid was listed first for
  benefit/effort. The effort was right; the benefit was not, on this corpus, for the reasons in
  ADR-0009.
- **`.github/workflows/` is not created.** PLAN.md gates `eval.yml` on ≥3 pipelines and there are
  2. `ci.yml` (lint + unit tests) is ungated and is the obvious next non-experiment task.

### Open

- **The corpus is contaminated by demo traffic, and it happened again.** `make validate` failed at
  the start of this phase: `manh_application_2025 (3).pdf` (14 chunks) had been uploaded through
  the Phase 5 UI and joined the frozen corpus. Documents 1–8 and chunks 1–34 were untouched, so
  deleting it restored the corpus exactly and `validate` returned to PASS — but **the eval could
  not have run correctly before that**, and nothing would have said so except `make validate`.
  This is the second occurrence. Run it after every upload session.
- **Every number in this phase carries the run-to-run variance above.** The `answer_relevance` win
  of +0.29 is suggestive, not conclusive. It is the one hybrid result worth following up.
- **The three remaining Phase 6 experiments are untouched:** chunk size/overlap (needs a full
  re-ingest, which reassigns chunk ids and therefore needs `--write-lock` and a golden-set
  re-verification — read ADR-0005 first), cross-encoder reranking, and query rewriting.
- **`refusal_accuracy` is still the open question**, and it is still a human decision (Phase 4,
  Phase 5). It scored 1.0 here, but it scored 0.8 on the identical pipeline one run earlier —
  which is evidence about the metric's stability, not evidence that the problem is solved.
- **`hybrid-v2` is now frozen** (CLAUDE.md 4.1): its results file is committed, so `hybrid_v2.py`,
  `bm25.py` and `hybrid.py` must not be edited. A weighted-RRF idea is `hybrid-w-v3`, a new file.
- **Both committed runs are `git_dirty: true`.** Unrelated working-tree edits (`README.md`, a file
  under `old_code/`) were present. The recorded `git_sha` does name the commit holding the pipeline
  code in both cases.
- **`backend/.env` still exists**, emptied and marked dead. Carried from Phase 1.

### What you can do after this phase

**Available:** two pipelines and a real comparison between them. `make eval P=<name>` works for any
registered name, `make report` rebuilds the leaderboard from every results file, and the served
pipeline is a `PIPELINE_NAME` change in `.env` with no code change — `hybrid-v2` can be served
today if you want its lower latency and its +0.29 relevance, at 0.02 recall. Keyword retrieval is
available as a component (`BM25Retriever`) for any future pipeline, and the GIN index supporting it
is in the schema. What does **not** exist: reranking, query rewriting, alternative chunk sizes, CI,
and any pipeline that beats the baseline.

**Commands that work at this point:**

```bash
make up && make migrate                    # migration 002 adds the GIN index
make validate                              # run this after ANY upload session
make test                                  # 183 passed
make lint                                  # 60 source files, clean
make report                                # -> results/leaderboard.md, 2 rows

make api                                   # terminal 1
make ui                                    # terminal 2

# naive-v1 and hybrid-v2 are both frozen; the runner refuses to overwrite either.
# A new idea is a new name:
make eval P=hybrid-v2                      # -> refuses, the file is committed
```

```sql
-- what the keyword half actually matches, without going through Python
SELECT c.id, d.filename,
       ts_rank_cd(to_tsvector('simple', c.content),
                  to_tsquery('simple', 'phụ | cấp | công | tác')) AS rank
FROM chunks c JOIN documents d ON d.id = c.document_id
WHERE to_tsvector('simple', c.content) @@ to_tsquery('simple', 'phụ | cấp | công | tác')
ORDER BY rank DESC LIMIT 10;
```

```sql
SELECT count(*) FROM documents;    -- must stay 8
SELECT count(*) FROM chunks;       -- must stay 34
```

**Technical, possible now:** run `hybrid-v2` a third time and watch the generation metrics move
again — the cheapest way to internalise how little a single run proves. Build `hybrid-w-v3`
(weighted RRF favouring dense) — on the evidence it would likely keep q002 and q017 without losing
q021, and it is one variable and one new file. Or skip ahead to the reranker, which attacks
ordering directly, which is where the headroom actually is. `.github/workflows/ci.yml` (lint +
unit tests) is ungated and small.

**Non-technical, possible now:** the standing highest-leverage action is unchanged and this phase
strengthened the case for it — **read `golden_qa.v1.jsonl` and rewrite it as `v2` under your own
name.** Agent-written questions paraphrase the source text, which specifically flatters dense
retrieval, because question and chunk came from the same words. Humans quote and abbreviate, which
is where keyword matching earns its place — so a human-written `v2` is the single change most
likely to reverse ADR-0009. Also still open, and still human: the `refusal_accuracy` contract, and
Phase 5's demo gate.

**Notice:** **a negative result is a result and it stays committed** — do not delete
`hybrid-v2.json` or its code to tidy up. **Generation metrics do not reproduce between runs**
(0.8 → 1.0 on `refusal_accuracy`, same code, same corpus), so never conclude anything from a
single run or from a gap under ~0.2; retrieval metrics *are* deterministic and can be compared
directly. **The corpus was contaminated by demo traffic twice now** — `make validate` is the only
thing that catches it, and an eval run against a contaminated corpus produces numbers that look
completely normal. Experiment 2 (chunk size) **requires a re-ingest**, which reassigns chunk ids
and invalidates every `relevant_chunk_ids`: read [ADR-0005](../adr/0005-frozen-corpus-for-the-golden-set.md)
before starting it, and never reach for `make ingest FORCE=1` as a shortcut.

**For the next phase (still 6 — experiments 2 to 4):** the loop is proven end to end, including
its unhappy path: a new pipeline is one file, one import in `pipelines/__init__.py`, `make eval`,
`make report`, and an ADR whether it wins or loses. Change exactly one variable. The two
comparisons that remain interesting are **reranking** (attacks ordering, which is where the
headroom is, and it can reorder without dropping a chunk the way RRF did to q021) and **chunk
size** (the only experiment that touches the corpus, so it costs a re-lock and a golden-set
re-verification). Neither should be read as promising until run: this phase's first experiment was
the one PLAN.md was most confident about.
