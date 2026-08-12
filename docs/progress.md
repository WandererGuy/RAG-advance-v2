# Progress log — index

**Start here.** One file per phase in [`progress/`](progress/), each recording what was built, the
command output proving the Definition of Done, deviations from PLAN.md, and open items. Decisions
with trade-offs live in [`adr/`](adr/) — the progress log records what happened, not why a design
was chosen. Each entry ends with **"What you can do after this phase"**: the commands that work at
that point, what is and is not possible yet, what to watch out for, and what the next phase needs
to know.

| Phase | Status | Entry |
|---|---|---|
| 0 — Lock the scope + skeleton | ✅ done | [progress/phase-0.md](progress/phase-0.md) |
| 1 — Infrastructure + schema | ✅ done | [progress/phase-1.md](progress/phase-1.md) |
| 2 — Synchronous ingest | ✅ done — sign-off **agent-executed**, not human-signed | [progress/phase-2.md](progress/phase-2.md) |
| 3 — Golden set | ✅ done — questions **agent-authored** ([ADR-0004](adr/0004-agent-authored-golden-set.md)) | [progress/phase-3.md](progress/phase-3.md) |
| 4 — `naive-v1` baseline | ✅ done — baseline committed, run on OpenAI ([ADR-0008](adr/0008-provider-migration-to-openai.md)) | [progress/phase-4.md](progress/phase-4.md) |
| 5 — API + thin frontend | 🟡 code done — the demo gate needs **a human outside the team** | [progress/phase-5.md](progress/phase-5.md) |
| 6 — Improvements | ⬜ not started | — |

## Where the project stands

The corpus is ingested and now **frozen** ([ADR-0005](adr/0005-frozen-corpus-for-the-golden-set.md)):
8 documents, 34 chunks, 768-dim embeddings, idempotent on re-run. Since 2026-08-12 the 8 PDFs are
**committed to the repo** in `data/raw/HR_pdfs/` — they are synthetic demo documents, not real
company data, so they may be shown and shared freely
([ADR-0001](adr/0001-scope-va-data-boundary.md)). A fresh clone can `make ingest` with no document
hunting; the corpus is still frozen, and committing it is not permission to add to it. `eval/datasets/golden_qa.v1.jsonl`
holds 29 questions with verified chunk citations. The build is green (`make lint`, `make validate`,
`make test` → 132 passed).

**Phase 4 is done: `results/naive-v1.json` is committed.** All 29 questions ran, 0 failures, and
`results/leaderboard.md` has its first row. The headline numbers — read
[ADR-0004](adr/0004-agent-authored-golden-set.md) before quoting any of them — are
`recall@5 0.958 · MRR 0.840 · nDCG@5 0.857` over the 24 answerable questions,
`faithfulness 5.0 · answer_relevance 4.5` (self-graded), `citation_rate 1.0` with **zero**
unsupported citations, and `p50 3281 ms`.

The number that matters is the weak one: **`refusal_accuracy` 0.6** — 2 of the 5 `unanswerable`
questions were not refused. Phase 4 had flagged this metric as never exercised; it now is, and it
is the worst column in the file. Both misses (`q025`, `q027`) actually *say* the documents do not
contain the answer and then add adjacent real facts with valid citations, so they are hedged
partial answers rather than invention — `faithfulness` 5.0 and 0 unsupported citations agree.
They are counted as hallucinations because `is_refusal()` matches one exact sentence and nothing
else, which is the deliberate design of [ADR-0006](adr/0006-how-generation-is-scored.md). The
detector is behaving as specified; the specification did not anticipate a hedge. **This is the
first thing Phase 6 should attack**, and it is a prompt-or-detector question, not a retrieval one.

**Phase 5 built the API and the demo UI.** `POST /chat`, `POST /documents` (upload + synchronous
ingest) and `GET /documents` are live, a Streamlit page at `make ui` puts a browser in front of
them, and `queries` is written for the first time — the table that will eventually let a golden
set grow from real traffic instead of imagination. The build is green: `make lint` (57 source
files), `make test` (**148 passed**), `make validate` PASS. What is **not** done is the
Definition of Done itself: PLAN.md asks that someone outside the team click through it without
instructions, and nobody has. That is a human gate and an agent cannot sign it — see
[phase-5](progress/phase-5.md).

**The whole stack moved from Gemini to OpenAI** mid-session, by the project owner's decision:
`gpt-5.6-luna` and `text-embedding-3-large` at an unchanged 768 dim
([ADR-0008](adr/0008-provider-migration-to-openai.md), which supersedes ADR-0007). Two
consequences worth carrying: the 34 chunks were **re-embedded in place** by `make reembed` — an
UPDATE, never a `FORCE=1` re-ingest — so chunk ids, `corpus.lock.json` and all 29
`relevant_chunk_ids` survived byte-identical; and `gpt-5.6-luna` **rejects `temperature=0`**, so
the parameter is omitted and every results file records `temperature: null` rather than claiming a
reproducibility property the run did not have.

## Gates taken by the agent — read before quoting anything

Both human gates were **authorised by the project owner on 2026-08-11** and executed by the agent
because no human was available. Neither is human-signed, and the distinction is load-bearing.

1. **Phase 2 sign-off — agent-executed 2026-08-11.** PLAN.md asks a person to read 5 random chunks;
   instead all 34 were checked mechanically (page numbers, diacritics, word boundaries, running
   heads: clean) plus a visual read of two rendered pages. Evidence in
   [phase-2](progress/phase-2.md). A human countersigning it later costs minutes and upgrades what
   every downstream number may be claimed to be.
2. **The golden set is agent-authored** — nobody was ever named, so CLAUDE.md 5.6 is superseded by
   [ADR-0004](adr/0004-agent-authored-golden-set.md). All 29 questions carry `"author": "agent"`,
   and `make validate` says so on every run. That ADR names what this inflates (retrieval metrics
   most, `refusal_accuracy` least trustworthily), the method constraints the writing followed, and
   the triggers for a human-written `v2`. **Every `results/*.json` from Phase 4 on carries
   `golden_set_author`, and no number may be quoted without it.** The most valuable human action
   available on this project is reading those 29 lines and rewriting them as `v2`.

## Still blocked on a human

- **Phase 5's Definition of Done is a human gate and it is open.** *"Someone outside the team can
  click through it without instructions"* — the UI serves, renders the corpus and answers real
  questions, but no such person has used it. Nothing blocks Phase 6 technically; this gate is what
  stands between Phase 5 being "code done" and "done". Its second clause — real data in `queries`
  after a demo session — fills itself the moment a human uses the UI.
- **`backend/.env` is redundant and still on disk.** The live config is the repo-root `.env`, which
  `config.py` resolves by absolute path, so this file affects nothing. Deleting it has been blocked
  by a permission prompt three times; it has instead been emptied and replaced with a header saying
  it is dead. It is gitignored and was never committed. Deleting it for real is a 5-second human
  task.
- **Decide what to do about `refusal_accuracy` 0.6** — whether the refusal contract should accept a
  hedge that names its own uncertainty, or whether the prompt should forbid hedging outright. That
  is a judgement about what employees should see, not a technical fix, and it belongs to a human.

## Carried-over open items

Full detail in each phase entry; these are the ones that will bite a later phase.

- **`POST /documents?force=true` reassigns chunk ids too**, and it is reachable from an HTTP call
  rather than only from a Makefile target. Same failure as `make ingest FORCE=1`, same detector:
  run `make validate` after any upload session. An ordinary upload is also a corpus change — a
  document ingested to "try it out" changes what every future eval run measures, so delete it and
  re-validate. ([phase-5](progress/phase-5.md))
- **The API has no auth, no permissions and no rate limit**, which is in scope for v1 but means
  every `/chat` call spends a metered key. Do not expose it beyond a laptop or a trusted network.
  ([phase-5](progress/phase-5.md))
- **Chunk ids are reassigned by any `--force` re-ingest**, which invalidates the golden set's
  `relevant_chunk_ids`. Now caught rather than prevented: the corpus is frozen in
  `eval/datasets/corpus.lock.json` and `make validate` fails loudly, naming what happened
  ([ADR-0005](adr/0005-frozen-corpus-for-the-golden-set.md)). Recovery still means looking every
  affected id up again. ([phase-3](progress/phase-3.md))
- **Every generation score is self-graded** — one provider is configured, so the judge is the
  answering model ([ADR-0006](adr/0006-how-generation-is-scored.md)). `faithfulness` and
  `answer_relevance` are biased upward; `refusal_accuracy` and every retrieval metric are
  deterministic and are not. The ADR names the triggers for adding an independent judge.
  ([phase-4](progress/phase-4.md))
- **A model alias is never permitted in `LLM_MODEL`** — `gpt-5.1-chat-latest` and friends change
  silently under a frozen pipeline, and the results file would then name a configuration that no
  longer identifies what ran ([ADR-0007](adr/0007-llm-model-migration-to-gemini-3-6-flash.md), rule
  retained by [ADR-0008](adr/0008-provider-migration-to-openai.md)). Expect the pinned model to be
  retired in turn; the 404 is information, not a bug.
- **Changing the embedding model means `make reembed`, never `make ingest FORCE=1`.** A forced
  re-ingest reassigns chunk ids and silently invalidates every `relevant_chunk_ids` in the golden
  set. The in-place UPDATE path exists precisely to avoid that, and it is what kept the golden set
  alive across the OpenAI migration ([ADR-0008](adr/0008-provider-migration-to-openai.md)).
- **`naive-v1` is now frozen** (CLAUDE.md 4.1): `naive_v1.py`, `answer_v1.jinja` and both judge
  prompts must not be edited now that a results file is committed. A new idea is a new pipeline
  with a new name.
- **The committed baseline was run with a dirty tree** (`git_dirty: true`) — the migration code and
  the run landed in the same commit, so its `git_sha` names the commit that contains the code
  rather than a tree that predates it. Later runs should be made from a clean tree.
- **The `unanswerable` questions and the flattened tables are the two things to watch in Phase 4.**
  `q021` and `q024` aim straight at table content that extraction linearises; a confident answer to
  `q025`–`q029` is a hallucination, not a pass. ([phase-3](progress/phase-3.md))
- **Tables flatten into a linear stream of cells** at PDF extraction, and one source document has a
  word truncated in its own text layer. Both shape which questions can be answered.
  ([phase-2](progress/phase-2.md))
- **The 8-document corpus makes retrieval metrics optimistic** — relative comparison between
  pipelines stays valid, absolute numbers do not. ([phase-0](progress/phase-0.md))
- **`POSTGRES_PASSWORD=rag` is a laptop default** and must change before this runs anywhere else.
  ([phase-1](progress/phase-1.md))

## Adding an entry

A phase is not finished until its file exists (CLAUDE.md rule 11). Copy the shape of
[phase-2.md](progress/phase-2.md): what was built, an evidence table of real command output,
decisions made while building, deviations from PLAN.md and why, and open items. Then add the row
to the table above and lift anything blocking a human into the section above. Write it before the
phase commit and include it in that commit.
