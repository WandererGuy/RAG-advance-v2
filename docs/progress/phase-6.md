## Phase 6 — Improvements, one pipeline at a time ✅ done — 2 of 4 experiments run, DoD met

**Built** 2026-08-12 · **`hybrid-v2` run** 2026-08-12, on OpenAI
**Experiment 2** built and run 2026-08-14 — **`rerank-v1` adopted and served**
([ADR-0010](../adr/0010-cross-encoder-reranking-adopted.md)); jump to
[Experiment 2](#experiment-2--cross-encoder-reranking-adopted-and-served).
**Closed** 2026-08-14 · retrospective: [`docs/retro-phase-5-6.md`](../retro-phase-5-6.md)

> **Why 2 of 4 experiments closes this phase.** PLAN.md's Definition of Done is
> *"`results/leaderboard.md` has ≥3 rows, and you can explain why you kept one and dropped another
> — with numbers, not with feelings."* Both clauses are met: 3 rows (`naive-v1`, `hybrid-v2`,
> `rerank-v1`), with [ADR-0009](../adr/0009-hybrid-retrieval-not-adopted.md) dropping hybrid and
> [ADR-0010](../adr/0010-cross-encoder-reranking-adopted.md) adopting rerank, both on numbers. The
> four-item list in PLAN.md is an *order to try things in*, not a completion checklist.
>
> The two untried experiments — chunk size and query rewriting — are **deliberately not run**
> rather than merely skipped. `rerank-v1` scores `recall@5` **1.000** and MRR **0.979** on 24
> agent-authored questions, so there is no retrieval headroom left to measure a third or fourth
> pipeline against. Running them now would add rows that read 1.000 and prove nothing. They are
> unblocked by a human-written `golden_qa.v2.jsonl`, not by more code.

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

---

## Experiment 2 — cross-encoder reranking, adopted and served

**Built and run** 2026-08-14 · [ADR-0010](../adr/0010-cross-encoder-reranking-adopted.md)

`app/llm/rag/rerankers/base.py` + `providers.py` · `app/llm/rag/retrievers/reranker.py` ·
`app/llm/rag/pipelines/rerank_v1.py` · four `RERANK_*` settings in `core/config.py` ·
`PipelineConfig.reranker` + `rerank_top_n` · `tests/unit/test_rerankers.py`.

**The first pipeline in this project to beat the baseline.** `PIPELINE_NAME` is now `rerank-v1`.

Dense retrieval is widened to 20 candidates, `voyage/rerank-2.5-lite` scores all 20 against the
question, and the top 5 go to the prompt — so generation sees the same 5 chunks as the baseline
and the only variable is their selection and order.

| | recall@5 | MRR | nDCG@5 | faithful | relevance | refusal | p50 ms |
|---|---|---|---|---|---|---|---|
| `naive-v1` | 0.958 | 0.840 | 0.857 | 4.897 | 4.250 | **1.000** | **2009** |
| `hybrid-v2` | 0.938 | 0.844 | 0.845 | **5.000** | **4.542** | **1.000** | **1611** |
| `rerank-v1` | **1.000** | **0.979** | **0.970** | 4.793 | 4.458 | 0.800 | 2074 |

Every retrieval metric improves; none regresses. Run twice, retrieval byte-identical both times.

**6 of 24 answerable questions improved, 0 degraded** — q003 (not retrieved → rank 1), q002, q009,
q010, q015 (rank 2–3 → 1–2) and q017 (multi_hop, 3 → 1). Nothing was displaced, which is the
structural difference from hybrid: RRF re-scores a merged list and can push a relevant chunk out of
the top 5 (q021), while a reranker only reorders what dense already found.

**q003 is the case to read.** The baseline never retrieved its relevant chunk, so the model
correctly declined — the baseline's only `over_refusal`. Widening to 20 candidates surfaced it and
the cross-encoder ranked it first, fixing a recall miss and an over-refusal with one change. It is
the whole of the recall gain to 1.000.

### `refusal_accuracy` 0.800 — one reproducible question, and it is the detector

The one metric that regresses. Two runs scored **0.6 then 0.8**; per-question, `q029` flipped
between runs (noise) while **`q025` failed in both** and refuses correctly under `naive-v1`. So one
question reproducibly regressed, not the metric generally — the kind of distinction a single run
cannot make, and the reason the second run was worth its 137 seconds.

`q025` is `unanswerable`. The answer says the documents do not state the year-end bonus rate for
employees on maternity leave, cites two real adjacent facts correctly, and invents nothing — the
judge scored it **faithfulness 5.0**. It counts as a hallucination only because `is_refusal()`
matches one exact sentence ([ADR-0006](../adr/0006-how-generation-is-scored.md)).

**Better retrieval caused it**: for an unanswerable question there is no correct chunk, so a
reranker surfaces the most topically adjacent material, which is exactly what invites a hedge. This
is the Phase 4 hedging blind spot, now reproducing on demand instead of intermittently. It is
counted as evidence *for* fixing the refusal contract, not as a cost of reranking — see ADR-0010,
which is explicit that this is a claim about `q025` specifically, verified by reading the answer.

### Evidence

| Check | Result |
|---|---|
| `make validate` | PASS — 8 documents, 34 chunks, 29 questions, all `author:agent` |
| `make lint` | ruff + mypy clean, **65** source files (60 before) |
| `make test` | **212 passed** (183 before) — 29 new reranker tests |
| `make eval P=rerank-v1 --overwrite` | 29 questions, 0 failures, run twice |
| `make report` | `results/leaderboard.md`, 3 pipelines |
| served path | `PIPELINE_NAME=rerank-v1` resolves to `dense>rerank` via `voyage/rerank-2.5-lite`, answers with a citation |

### Decisions made while building

- **A third vendor, accepted deliberately.** OpenAI has no reranking endpoint, so serving this
  result means a second provider. Lock-in is kept shallow: `RERANK_PROVIDER` switches between
  Voyage, Cohere, Together, DeepInfra, Fireworks and WatsonX through LiteLLM's `arerank`, with a
  direct HTTPS adapter for Jina because LiteLLM 1.96 does not route it. Amends
  [ADR-0008](../adr/0008-provider-migration-to-openai.md).
- **`reranker` and `rerank_top_n` default to `None` on `PipelineConfig`**, so adding the fields does
  not change what the two frozen pipelines report in their committed results files.
- **`RERANK_TOP_N=20`, untuned.** Tuning the candidate width on 29 agent-authored questions would
  fit it to the golden set rather than the problem — the same reasoning that left RRF's `K=60`
  alone.
- **The reranker is a retriever, not a pipeline concern.** `RerankingRetriever` wraps a base
  retriever and satisfies the same protocol, so `rerank-v1` wires it in its `build()` exactly as
  `naive-v1` wires dense (CLAUDE.md 4.3).

### Open

- **`rerank-v1` is now frozen** (CLAUDE.md 4.1): `rerank_v1.py`, `reranker.py` and `rerankers/` must
  not be edited. A different `RERANK_TOP_N`, a different reranker model, or reranking on top of
  hybrid is a new pipeline with a new name.
- **An empty `RERANK_API_KEY` fails per-request, not at startup.** With `PIPELINE_NAME=rerank-v1`
  the Voyage path builds cleanly and raises `RerankFailed` at the first `/chat` call — LiteLLM is
  handed `api_key=None`, and only the Jina adapter validates its key in the constructor. A
  deployment that forgets the key starts healthy and fails on every request. The fix belongs to
  whoever next touches that frozen code path.
- **Perfect recall means the golden set has stopped discriminating.** `recall@5` 1.000 on 24
  paraphrase-derived questions over 34 chunks leaves no retrieval headroom to measure the remaining
  experiments against. This strengthens the standing case for a human-written `v2` from "highest
  value" to "the next experiment needs it".
- **The served path now makes a per-query external call to a third vendor.** No auth and no rate
  limit still apply (Phase 5) — now spending two metered keys per question.

### What you can do after this phase

**Available:** three pipelines, an adopted winner, and two real comparisons. `make eval P=<name>`
works for any registered name, `make report` rebuilds the leaderboard from every results file, and
the served pipeline is a `PIPELINE_NAME` change in `.env` with no code change. **The served stack
is now `rerank-v1`** — dense top-20 reordered by `voyage/rerank-2.5-lite` down to top-5, needing a
Voyage key in `RERANK_API_KEY`. Falling back to `naive-v1` (no third-party call, no second key) is
that same one-line change. Keyword retrieval (`BM25Retriever`) and reranking
(`RerankingRetriever`, six providers plus Jina) are both available as components for any future
pipeline. What does **not** exist: query rewriting, alternative chunk sizes, and CI.

**Commands that work at this point:**

```bash
make up && make migrate                    # migration 002 adds the GIN index
make validate                              # run this after ANY upload session
make test                                  # 212 passed
make lint                                  # 65 source files, clean
make report                                # -> results/leaderboard.md, 3 rows

make api                                   # terminal 1 — now serves rerank-v1
make ui                                    # terminal 2

# all three pipelines are frozen; the runner refuses to overwrite a results file.
# A new idea is a new name:
make eval P=rerank-v1                      # -> refuses, the file is committed
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

**Technical, possible now:** the honest answer is that **the remaining retrieval experiments have
little left to measure on this dataset** — `recall@5` is 1.000 and MRR 0.979, so query rewriting
and chunk-size tuning would be competing for 0.02 of headroom against a golden set that no longer
discriminates. Worth doing anyway, and cheaply: `.github/workflows/ci.yml` (lint + unit tests) is
ungated and small; a `rerank-hybrid-v4` (rerank on top of RRF candidates rather than dense) is one
new file and would test whether hybrid's q021 displacement is recoverable; validating
`RERANK_API_KEY` at construction for every provider fixes the fail-per-request trap above. Serving
`naive-v1` again is one line if the Voyage dependency is unwanted.

**Non-technical, possible now:** **read `golden_qa.v1.jsonl` and rewrite it as `v2` under your own
name.** This was already the highest-leverage action; experiment 2 changed it from valuable to
blocking. A pipeline scoring perfect recall on 24 paraphrase-derived questions has exhausted what
this dataset can tell us — the next experiment cannot be evaluated against a ceiling. Agent-written
questions paraphrase the source text, which flatters dense retrieval and, now, the reranker sitting
on top of it. Also still open, and still human: **the `refusal_accuracy` contract**, which now has
a reproducible test case in `q025` and is the only thing standing between `rerank-v1` and a clean
sweep of every metric; and Phase 5's demo gate.

**Notice:** **a negative result is a result and it stays committed** — do not delete
`hybrid-v2.json` or its code to tidy up. **Generation metrics do not reproduce between runs**
(0.8 → 1.0 on `refusal_accuracy`, same code, same corpus), so never conclude anything from a
single run or from a gap under ~0.2; retrieval metrics *are* deterministic and can be compared
directly. Experiment 2 is the worked example of why that rule pays: two runs separated a
reproducible failure (`q025`) from a sampling flip (`q029`), and one run could not have. **The
served path now spends two metered keys per question** and makes an external call to a third
vendor — still no auth and no rate limit, so do not expose it. **The corpus was contaminated by
demo traffic twice** — `make validate` is the only thing that catches it, and a contaminated run
produces numbers that look completely normal. The chunk-size experiment **requires a re-ingest**,
which reassigns chunk ids and invalidates every `relevant_chunk_ids`: read
[ADR-0005](../adr/0005-frozen-corpus-for-the-golden-set.md) before starting it, and never reach for
`make ingest FORCE=1` as a shortcut.

**For the next phase (still 6 — experiments 3 and 4):** the loop is proven in both directions now —
a rejected experiment ([ADR-0009](../adr/0009-hybrid-retrieval-not-adopted.md)) and an adopted one
([ADR-0010](../adr/0010-cross-encoder-reranking-adopted.md)), each one file, one import in
`pipelines/__init__.py`, `make eval`, `make report`, an ADR either way. What the two experiments
together taught: **reordering beats re-scoring** — hybrid could displace a relevant chunk and did
(q021), while reranking only reorders candidates dense already found and degraded nothing. Apply
that when designing experiment 3. But the binding constraint is no longer the pipeline: it is the
golden set, and lifting it is a human's job.
