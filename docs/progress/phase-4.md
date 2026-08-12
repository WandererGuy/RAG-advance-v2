## Phase 4 — `naive-v1` baseline ✅ done — **the baseline is committed**

**Built** 2026-08-11 · **baseline run** 2026-08-12, on OpenAI
([ADR-0008](../adr/0008-provider-migration-to-openai.md))

`app/llm/client.py` · `app/llm/prompts/{__init__.py,answer_v1.jinja}` ·
`app/llm/rag/retrievers/{base,dense}.py` · `app/llm/rag/pipelines/{base,registry,naive_v1}.py` ·
`eval/metrics/{retrieval,generation}.py` · `eval/judge_prompts/{faithfulness_v1,relevance_v1}.jinja` ·
`eval/{runner,report}.py` · [ADR-0006](../adr/0006-how-generation-is-scored.md) ·
[ADR-0007](../adr/0007-llm-model-migration-to-gemini-3-6-flash.md) ·
4 unit test files (79 new tests) · `make eval`, `make report`.

### The baseline

`results/naive-v1.json` is committed. All 29 questions ran, `failed_questions: 0`. The quota that
blocked this for a day stopped being a constraint when the stack moved to a metered OpenAI key
([ADR-0008](../adr/0008-provider-migration-to-openai.md)).

| | |
|---|---|
| `recall@5` · `MRR` · `nDCG@5` | 0.958 · 0.840 · 0.857 — over 24 questions, 5 `unanswerable` excluded |
| `faithfulness` · `answer_relevance` | 5.0 (29 scored) · 4.5 (24 scored) — **self-graded**, 0 judge failures |
| `refusal_accuracy` | **0.6** · `over_refusal_rate` 0.042 |
| outcomes | 23 `answered` · 3 `correct_refusal` · **2 `hallucinated`** · 1 `over_refusal` |
| citations | `citation_rate` 1.0, **0** unsupported citations out of 25 answers |
| latency | p50 3281 ms · p95 9238 ms · max 17722 ms |

**Read `refusal_accuracy` before anything else in that table.** It is the worst number and the one
this phase previously had no evidence for at all.

### The two hallucinations are hedges, and that is the interesting part

`q025` and `q027` are counted as hallucinations. Both of them say, in the answer itself, that the
documents do not contain what was asked — *"Tài liệu chỉ quy định tính theo tỷ lệ tháng làm việc…"*
and *"tài liệu không nêu mức phí một năm"* — and then supply an adjacent real fact with a citation
that resolves. `faithfulness` scored 5.0 and `unsupported_citations` is 0, so nothing was invented.

They fail because `is_refusal()` matches exactly one sentence and treats everything else as a
non-refusal. That is deliberate ([ADR-0006](../adr/0006-how-generation-is-scored.md)): the
safety-critical number is arithmetic, not a model's opinion of itself. The detector did what it
was specified to do; the specification did not anticipate a model that hedges accurately.

So the real question is a design one, and it is a human's to answer: should an answer that names
its own uncertainty count as a refusal, or should the prompt forbid hedging so the contract stays
binary? Both are defensible. Changing either is a **new pipeline with a new name** — `naive-v1` is
frozen now. This is the highest-value thing for Phase 6 to work on, and it is not a retrieval
problem.

The `over_refusal`, `q003`, is the mirror image: *"Mỗi tháng được hỗ trợ bao nhiêu tiền bữa trưa?"*
was refused although it is a `factual` question, so the system is not simply over-eager to answer.

### Evidence

| Check | Result |
|---|---|
| `make lint` | ruff + mypy clean, **48** source files (33 before) |
| `make test` | **132 passed** (52 before; none touching DB or network) |
| `make validate` | PASS — corpus lock intact, 34 chunks, still 29 questions, all `author:agent` — **after** the re-embed, which is the point |
| `make reembed` | `re-embedded 34 chunk(s) in place. Chunk ids unchanged.` — `git diff` on `corpus.lock.json` and `golden_qa.v1.jsonl` empty |
| **`make eval P=naive-v1`** | **29/29 questions, `failed_questions: 0`** — the table above |
| `make report` | `wrote results/leaderboard.md (1 pipeline(s))` |
| `make eval P=hybrid-v2` | `error: pipeline not registered: 'hybrid-v2' (registered: naive-v1)`, exit 2, no calls made |

The baseline's own provenance block, written by the runner and reproduced here because it is the
part that matters more than the scores:

```json
{"config": {"chunk_size": 800, "chunk_overlap": 100, "top_k": 5, "retriever": "dense",
            "embedding_model": "openai/text-embedding-3-large", "embedding_dimensions": 768,
            "llm_model": "openai/gpt-5.6-luna", "temperature": null, "prompt_version": "v1"},
 "dataset_version": "v1", "golden_set_author": ["agent"],
 "judge_model": "openai/gpt-5.6-luna", "judge_is_answer_model": true,
 "git_sha": "8ce76a3…", "git_dirty": true, "corpus_validated": true}
```

### The provider changed twice, and the second time took the embeddings with it

First, mid-phase, `gemini-2.5-flash` was retired under us — a 404 on every question, while the
model still appeared in the provider's `models` list. `gemini-3.6-flash` replaced it
([ADR-0007](../adr/0007-llm-model-migration-to-gemini-3-6-flash.md)), which also established the
rule that **a moving alias is never permitted in `LLM_MODEL`**. "Configured correctly" and "still
works" are different questions.

Then the project owner moved the whole stack to OpenAI: `gpt-5.6-luna` and
`text-embedding-3-large`, 768 dim unchanged ([ADR-0008](../adr/0008-provider-migration-to-openai.md),
superseding ADR-0007). Unlike the first migration, **this one invalidated every stored vector** — a
`gemini-embedding-001` embedding is not comparable to a `text-embedding-3-large` query embedding,
and the resulting cosine scores would have been noise that reads exactly like a mediocre retriever.

The corpus had to be re-embedded, and the obvious way to do it — `make ingest FORCE=1` — is the
precise action [ADR-0005](../adr/0005-frozen-corpus-for-the-golden-set.md) exists to prevent: it
deletes and reinserts chunk rows, PostgreSQL assigns new serial ids, and all 34 bare integers in
the golden set's `relevant_chunk_ids` would then point at the wrong text. So
`scripts/reembed_corpus.py` (`make reembed`) was written to **UPDATE the embedding column in
place**, touching no id, no content and no `chunk_index`. `corpus.lock.json` digests exactly those
untouched fields, so the lock held by construction: after re-embedding all 34 chunks,
`make validate` passed and `git diff` on both the lock and the golden set was empty.

`gpt-5.6-luna` then refused `temperature=0` outright (400, "only the default (1) value is
supported"), against a client that had set it deliberately since Phase 4 for reproducibility. The
parameter is now **omitted** rather than silently replaced with 1.0, and `PipelineConfig` records
`temperature: null` — because a results file claiming `0.0` would assert a reproducibility property
the run did not have. The cost is real and is written into the leaderboard's caveats: repeat runs
vary more than they used to.

Both migrations landed before any results file was committed. One commit later, either would have
destroyed the baseline instead of merely preceding it.

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

- **`refusal_accuracy` 0.6 is the open problem of this project**, and it is a contract question,
  not a retrieval one — see the hedging section above. Deciding it is a human's call; acting on it
  is a new pipeline, because `naive-v1` is frozen.
- **Phase 3's prediction about the flattened tables was right.** `q024` — the seat-class question
  aimed at table content that PDF extraction linearises — scored `answer_relevance` **3**, the
  lowest in the run, and `q021` scored 4. Both were `answered` with supported citations, so this is
  a quality problem, not a failure. If it is worth fixing, the fix is a structured extractor with
  its own ADR, not a bigger `top_k`.
- **Every `answer_relevance` below 5 is a multi_hop or a table question** (`q011`, `q012`, `q014`,
  `q021`–`q024`). `factual` questions score 5 almost uniformly. That is the clearest signal in the
  file about where the pipeline is actually weak.
- **No question missed retrieval outright.** Nothing scored `recall = 0`; the aggregate 0.958 comes
  from multi_hop questions retrieving some but not all of their relevant chunks. With 34 chunks and
  `top_k=5`, retrieval sees ~15% of the corpus per query, so this remains evidence that the
  plumbing works and weak evidence about retrieval quality. It also means **`recall@5` has almost
  no headroom left to demonstrate a Phase 6 improvement** — hybrid retrieval will have to show its
  value in MRR, nDCG and `answer_relevance`, not recall.
- **The run was made with a dirty tree** (`git_dirty: true`): the OpenAI migration and the baseline
  landed in one commit, so the recorded `git_sha` is the commit containing the code rather than a
  tree that predates it. Future runs should start from a clean tree.
- **`backend/.env` still exists.** It has been emptied and marked dead, and `config.py` reads the
  repo-root `.env` by absolute path, so it influences nothing. Actually deleting it has now been
  blocked by a permission prompt three times. Carried from Phase 1.
- **The judge costs more calls than the pipeline it grades** (~53 vs ~29). The key is metered now,
  so that ratio is a cost question rather than a quota question.

### What you can do after this phase

**Available:** **a committed baseline** — `results/naive-v1.json` and `results/leaderboard.md`, one
row, fully provenanced. A registered, runnable `naive-v1` (dense top-5, a Vietnamese answer prompt
demanding `[filename, p.N]` citations and an exact refusal sentence), an LLM-as-judge, the runner
and the leaderboard generator. Also new: `make reembed`, which changes the embedding model without
destroying the golden set. There is still no API and no frontend (Phase 5), and no second pipeline
to compare against (Phase 6) — a one-row leaderboard is a starting point, not a comparison.

**Commands that work at this point:**

```bash
make up && make migrate                    # bring the environment back
make ingest                                # idempotent: skips all 8
make validate                              # golden set + frozen corpus lock
make find Q="phụ cấp"
make test                                  # 132 passed
make lint                                  # 48 source files, clean
make report                                # -> results/leaderboard.md
make psql

make reembed ARGS=--dry-run                # after an embedding-model change; NEVER ingest FORCE=1
```

```bash
cd backend
# naive-v1 is frozen and its results file exists; the runner refuses to overwrite it.
# Explore without touching the baseline:
uv run python -m eval.runner --pipeline naive-v1 --limit 3 --out /tmp/smoke.json --overwrite
uv run python -m eval.runner --pipeline naive-v1 --no-judge      # retrieval + refusal only
uv run python -m eval.runner --pipeline naive-v1 --judge-model openai/gpt-5.4-mini \
    --out /tmp/other-judge.json            # measure the self-grading bias of ADR-0006
uv run python -m eval.report --stdout
```

```sql
SELECT count(*) FROM chunks;                                   -- must stay 34
-- nothing writes to `queries` yet; that arrives with chat_service.py in Phase 5
```

**Technical, possible now:** re-run with `--judge-model` pointed at a *different* model and diff the
two — that gap is the first real measurement of the self-grading bias ADR-0006 describes, and it is
cheap now that quota is not a constraint. Read the per-question blocks for `q021`–`q024`: every
`answer_relevance` below 5 is there, and they are the multi_hop and table questions. Read `q025` and
`q027` and decide whether their hedging should count as a refusal — then build the pipeline that
implements whichever answer you choose.

**Non-technical, possible now:** read the 29 answers. They are Vietnamese prose with citations you
can check against the PDFs by page number, and no technical background is needed to judge whether
`q025`'s and `q027`'s hedged answers are what you want an employee to receive when the handbook does
not cover their question — that single decision is worth more than any metric in the file. Then
decide whether the refusal sentence is the wording you want. And the standing highest-leverage
action from Phase 3 is unchanged: read `golden_qa.v1.jsonl` and rewrite the weakest questions as
`v2` under your own name.

**Notice:** `naive_v1.py`, `answer_v1.jinja` and both judge prompts are **frozen** now that the
results file is committed — a new idea is a new file with a new name (CLAUDE.md 4.1), and the runner
will refuse to overwrite `results/naive-v1.json`. `--limit` and `--skip-validation` mark the results
file (`partial_run`, `corpus_validated: false`); never commit either as a baseline. **Never run
`make ingest FORCE=1`** — it reassigns chunk ids and silently invalidates the golden set;
`make reembed` is the supported path for an embedding change (ADR-0008). `refusal_accuracy` 0.6 must
travel with every quotation of these numbers. `temperature` is `null`, so repeat runs will vary more
than they would at 0 — a small difference between two pipelines may be noise. The provider retires
models without warning; when the next 404 arrives it is information, not a bug (ADR-0007). And every
generation score is self-graded until a second judge exists.

**For the next phase (5 — API + thin frontend):** Phase 5 is unblocked — the baseline it demos and
that Phase 6 measures against is committed. `chat_service.py` reaches the pipeline through
`build_pipeline(settings.pipeline_name, …)`
and never imports `NaiveV1` — that indirection is the whole point of the registry. `RAGAnswer`
already carries everything `ChatResponse` and `Citation` need, including `chunk_id` and
`supported`, so the schema is a projection of it and not a second model of the domain; a citation
with `supported=false` must not be rendered as a normal source in the UI. `queries` is still empty
and Phase 5 is what fills it. And `health.py`'s local session dependency is deleted when
`api/deps.py` lands (carried from Phase 1).
