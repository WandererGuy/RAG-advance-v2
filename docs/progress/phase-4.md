## Phase 4 — `naive-v1` baseline 🟨 code complete, **the baseline number does not exist yet**

**Built** 2026-08-11

`app/llm/client.py` · `app/llm/prompts/{__init__.py,answer_v1.jinja}` ·
`app/llm/rag/retrievers/{base,dense}.py` · `app/llm/rag/pipelines/{base,registry,naive_v1}.py` ·
`eval/metrics/{retrieval,generation}.py` · `eval/judge_prompts/{faithfulness_v1,relevance_v1}.jinja` ·
`eval/{runner,report}.py` · [ADR-0006](../adr/0006-how-generation-is-scored.md) ·
[ADR-0007](../adr/0007-llm-model-migration-to-gemini-3-6-flash.md) ·
4 unit test files (79 new tests) · `make eval`, `make report`.

### The phase is not done

**PLAN.md's Definition of Done is `results/naive-v1.json`, committed. That file does not exist.**
The pipeline runs, end to end, against the real corpus and the real provider — but the provider's
free tier allows **20 generate-content requests per day, per model**, and a full run of the 29
questions needs ~29 answer calls plus ~53 judge calls. The run reached question 10 of 29 before
the daily quota was exhausted, and was stopped rather than left to record 19 quota failures as if
they were results.

The project owner has said they will clear the quota; the run is the first thing to do next
session. **Nothing else in this phase is blocked, and no number from it may be quoted until that
file exists.** No partial or smoke-run output was committed to `results/` — a results file that is
really a 3-question sample is worse than no baseline, because it will be read as the baseline.

### Evidence

| Check | Result |
|---|---|
| `make lint` | ruff + mypy clean, **47** source files (33 before) |
| `make test` | **131 passed** (52 before; +79 unit tests, none touching DB or network) |
| `make validate` | PASS — corpus lock intact, 34 chunks, still 29 questions, all `author:agent` |
| smoke run, 3 questions, real DB + real Gemini | `recall@5 1.0 · mrr 1.0 · ndcg@5 0.9501 · faithfulness 5.0 · answer_relevance 4.667 · citation_rate 1.0 · p50 5625 ms` — **not a baseline, 3 of 29 questions** |
| partial run, 10 questions | all 10 `answered`, `recall=1.00` on each, then quota |
| `make report` on an empty `results/` | `No results yet. Run make eval P=naive-v1 — the baseline is the first row.` |
| `make eval P=hybrid-v2` | `error: pipeline not registered: 'hybrid-v2' (registered: naive-v1)`, exit 2, no calls made |

The smoke run's own provenance block, written by the runner and reproduced here because it is the
part that matters more than the scores:

```json
{"config": {"chunk_size": 800, "chunk_overlap": 100, "top_k": 5, "retriever": "dense",
            "embedding_model": "gemini/gemini-embedding-001", "embedding_dimensions": 768,
            "llm_model": "gemini/gemini-3.6-flash", "prompt_version": "v1"},
 "dataset_version": "v1", "golden_set_author": ["agent"],
 "judge_model": "gemini/gemini-3.6-flash", "judge_is_answer_model": true,
 "git_sha": "2d18c2b…", "corpus_validated": true}
```

### The provider retired the configured model, mid-phase

The first run failed on **every** question with a 404: `gemini-2.5-flash` "is no longer available
to new users". Embedding was unaffected — `gemini-embedding-001` still serves this key — so the
corpus, its 768 dimensions and the chunk ids are all untouched, and no re-ingest was needed.

The project owner chose `gemini-3.6-flash` from the models verified working against the live key.
[ADR-0007](../adr/0007-llm-model-migration-to-gemini-3-6-flash.md) records it, and the rule it
adds: **a model alias like `gemini-flash-latest` is never permitted in `LLM_MODEL`**, because the
model behind it changes silently and a frozen pipeline's results file would then name a
configuration that no longer identifies what ran. `.env`, `.env.example`, `Settings`, CLAUDE.md,
PLAN.md and README.md were moved together. No results file existed yet, so nothing was invalidated
— one commit later it would have destroyed the baseline.

Worth keeping in mind: the model still appears in the provider's `models` list and only 404s on
the actual call. "Configured correctly" and "still works" are different questions.

### Decisions made while building

- **Refusal is detected, not judged** ([ADR-0006](../adr/0006-how-generation-is-scored.md)). The
  prompt receives the refusal sentence as a variable from the same constant `is_refusal()` matches,
  so the prompt and the metric cannot drift. The safety-critical number of this project is
  arithmetic, not a model's opinion.
- **The judge is the answering model, and every results file says so** — `judge_model` plus the
  boolean `judge_is_answer_model`, and `leaderboard.md` prints a line naming the self-graded
  pipelines. There is one provider (ADR-0001); a second judge is named in ADR-0006 with its
  triggers. `--judge-model` swaps it without touching a pipeline.
- **Four outcomes, not "refused / did not refuse":** `answered`, `correct_refusal`,
  `hallucinated`, `over_refusal`. A pipeline that refuses everything must not be able to look safe.
- **`unanswerable` questions are excluded from the retrieval metrics**, not scored 0 and not 1 —
  their relevant set is empty, so recall has no denominator. `questions_excluded` is reported
  beside every retrieval aggregate so nobody reads `recall@5` as covering all 29.
- **A judge failure is `None`, never a default score**, and `judge_failures` sits next to the mean
  it is missing from. A silent 3/5 for a call that never succeeded is indistinguishable from a
  real mediocre answer.
- **Citations are parsed back out of the answer and resolved against the chunks that answer was
  given.** One that matches nothing is kept with `supported=false` and counted — a fabricated
  source is the failure a reader is most likely to believe, and dropping it would erase it.
- **`RetrievedChunk` is a separate type from the repository's `ChunkHit`** — `ChunkHit.score` means
  cosine similarity specifically, while a retriever's score means whatever it ranks by. Phase 6's
  RRF fusion score must not be readable as a cosine similarity.
- **The registry rejects a rebound name and a `name` attribute that disagrees with it.**
  `results/<name>.json` takes the registry key and `RAGAnswer.pipeline_name` takes the attribute;
  a mismatch would file one pipeline's answers under another's name.
- **The runner refuses to overwrite an existing results file**, and checks that before spending a
  single provider call — discovering it after ~80 calls is an invitation to pass `--overwrite` in
  irritation.
- **`StrictUndefined` on every prompt template.** A typo'd variable would otherwise render as an
  empty string: a prompt silently missing its context produces output that looks fine and numbers
  that mean nothing.
- **`temperature=0` and an explicit timeout on every LLM call.** Not reproducibility — nothing
  hosted guarantees that — but the closest available, and one hung request must not hang a run.

### Deviations from PLAN.md

- **`retrieve()` and `answer()` are `async`.** CLAUDE.md 4.1 sketches them synchronous; the whole
  stack has been async since ADR-0002 and a sync façade over it would need its own event loop.
- **`RAGAnswer` carries `retrieved` (the chunks, not only their ids)** beyond PLAN.md's field list.
  The faithfulness judge scores an answer against the context it was actually given; ids alone
  cannot be rendered into a judge prompt.
- **Extra metrics PLAN.md does not name:** `over_refusal_rate`, `citation_rate`,
  `unsupported_citations`, and latency percentiles. Each answers a question the three named
  metrics cannot: whether a "safe" pipeline is merely useless, and whether its sources are real.
- **`eval/runner.py` also writes `schema_version`, `git_dirty`, `corpus_validated`,
  `judge_is_answer_model` and `partial_run`.** Every one of them marks a way a results file can
  look like a comparable full run without being one.
- **No unit test drives `NaiveV1` end to end with a stub retriever and a stub LLM.** CLAUDE.md 5.5
  is strict about mocks, so the unit tests cover the pure contracts (refusal, citations, registry,
  metrics, prompt rendering, judge parsing) and the assembled pipeline is proven by the real
  smoke run above. If that trade turns out wrong, the honest fix is an integration test against
  the real database and the real provider, not a mock.
- **`--limit`, `--no-judge`, `--judge-model`, `--skip-validation`, `--overwrite` and `--out`**
  are beyond PLAN.md's `--pipeline [--dataset]`. `--limit` and `--no-judge` are what made it
  possible to prove the pipeline works without spending the quota the baseline needs.

### Open

- **The baseline run itself.** Blocked on the provider quota, which the project owner is clearing.
  Until `results/naive-v1.json` is committed, Phase 4's Definition of Done is not met and Phase 5
  should not start.
- **`refusal_accuracy` has never been exercised.** The 10 questions the partial run reached were
  all answerable; every `unanswerable` question is in the untested tail (`q025`–`q029`). The one
  metric ADR-0004 calls least trustworthy is also the one with the least evidence behind it so far.
- **`q021` and `q024`, the flattened-table questions, were not reached either.** Phase 3 named them
  the likeliest failures; if they fail, the fix is a structured extractor with its own ADR, not a
  bigger `top_k`.
- **All 10 answered questions scored `recall@5 = 1.0`.** That is what an 8-document corpus with 34
  chunks and a `top_k` of 5 does — retrieval sees roughly 15% of the corpus per query. It is
  evidence that the plumbing works and no evidence at all about retrieval quality.
- **`backend/.env` still exists** with a duplicate of both API keys — and now a *stale* model name,
  which would resurrect the 404 for anyone whose tooling reads it. The live config is the repo-root
  `.env`. Deleting it is still blocked by a permission prompt. Carried from Phase 1.
- **The judge costs more calls than the pipeline it grades** (~53 vs ~29). On a metered key that
  ratio is worth knowing before enabling billing.

### What you can do after this phase

**Available:** a registered, runnable `naive-v1` — dense top-5 retrieval, a Vietnamese answer
prompt that demands `[filename, p.N]` citations and an exact refusal sentence, an LLM-as-judge, a
runner that writes a fully provenanced results file, and a leaderboard generator. What does **not**
exist: **any committed number**. `results/` holds only `.gitkeep`. There is still no API and no
frontend (Phase 5), and no second pipeline to compare against (Phase 6).

**Commands that work at this point:**

```bash
make up && make migrate                    # bring the environment back
make ingest                                # idempotent: skips all 8
make validate                              # golden set + frozen corpus lock
make find Q="phụ cấp"
make test                                  # 131 passed
make lint                                  # 47 source files, clean

make eval P=naive-v1                       # THE baseline run — needs provider quota
make report                                # -> results/leaderboard.md
make psql
```

```bash
cd backend
# prove the pipeline without spending the quota the baseline needs:
uv run python -m eval.runner --pipeline naive-v1 --limit 3 --out /tmp/smoke.json --overwrite
uv run python -m eval.runner --pipeline naive-v1 --no-judge      # retrieval + refusal only
uv run python -m eval.runner --pipeline naive-v1 --judge-model gemini/gemini-3.5-flash-lite
uv run python -m eval.report --stdout
```

```sql
SELECT count(*) FROM chunks;                                   -- must stay 34
-- nothing writes to `queries` yet; that arrives with chat_service.py in Phase 5
```

**Technical, possible now:** clear the provider quota and run the baseline — that is the whole of
this phase's remaining work. Read the per-question block of the results file before reading its
aggregates: `outcome`, `citations[].supported` and the judge's `reason` say more than any mean.
Check whether `q025`–`q029` were refused. Re-run with `--judge-model` pointed at a different model
and compare — the gap between the two is the first measurement of the self-grading bias ADR-0006
describes. Read `answer_v1.jinja` against a few real answers and decide whether the refusal
sentence is being obeyed literally.

**Non-technical, possible now:** read the answers themselves once the run lands — they are
Vietnamese prose with citations you can check against the PDFs by page number, and no technical
background is needed to spot a confident answer to a question the documents do not cover. Decide
whether the provider key gets billing (the free tier cannot complete one evaluation run in a day).
Judge whether the refusal sentence is the wording you want employees to see. And the standing
highest-leverage action from Phase 3 is unchanged: read `golden_qa.v1.jsonl` and rewrite the
weakest questions as `v2` under your own name.

**Notice:** the free tier is **20 generate-content requests per day per model** — one full eval run
does not fit, and a quota failure surfaces as a *question-level error in the results file*, not as
a crash, so a file with `failed_questions: 19` is a quota story and not a pipeline story. Read
`failed_questions` before any mean. `--limit` and `--skip-validation` both mark the results file
(`partial_run`, `corpus_validated: false`) — do not commit either as a baseline. Once
`results/naive-v1.json` is committed, `naive_v1.py`, `answer_v1.jinja` and both judge prompts are
**frozen**: a new idea is a new file with a new name (CLAUDE.md 4.1). The provider retires models
without warning — when the next 404 arrives, it is information, not a bug (ADR-0007). And every
generation score is self-graded until a second judge exists.

**For the next phase (5 — API + thin frontend):** do not start it until `results/naive-v1.json` is
committed; the baseline is what Phase 5 demos and what Phase 6 measures against. When it does
start: `chat_service.py` reaches the pipeline through `build_pipeline(settings.pipeline_name, …)`
and never imports `NaiveV1` — that indirection is the whole point of the registry. `RAGAnswer`
already carries everything `ChatResponse` and `Citation` need, including `chunk_id` and
`supported`, so the schema is a projection of it and not a second model of the domain; a citation
with `supported=false` must not be rendered as a normal source in the UI. `queries` is still empty
and Phase 5 is what fills it. And `health.py`'s local session dependency is deleted when
`api/deps.py` lands (carried from Phase 1).
