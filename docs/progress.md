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
| 4 — `naive-v1` baseline | 🟨 code complete — **no number committed yet**, blocked on provider quota | [progress/phase-4.md](progress/phase-4.md) |
| 5 — API + thin frontend | ⬜ not started | — |
| 6 — Improvements | ⬜ not started | — |

## Where the project stands

The corpus is ingested and now **frozen** ([ADR-0005](adr/0005-frozen-corpus-for-the-golden-set.md)):
8 documents, 34 chunks, 768-dim embeddings, idempotent on re-run. `eval/datasets/golden_qa.v1.jsonl`
holds 29 questions with verified chunk citations. The build is green (`make lint`, `make validate`,
`make test` → 131 passed).

Phase 4's code is complete and proven end to end against the real corpus and the real provider —
`naive-v1`, the dense retriever, the judge, the runner and the leaderboard all run — but **no
number has been committed**. `results/` still holds only `.gitkeep`. The provider's free tier
allows 20 generate-content requests per day per model and one full run needs about 82, so the
baseline run stopped at question 10 of 29 and nothing partial was saved. Clearing that quota and
running `make eval P=naive-v1` is the single remaining task of the phase, and Phase 5 should not
start before it lands.

Mid-phase the provider retired the configured `gemini-2.5-flash` (404, "no longer available to new
users"); the answering model is now `gemini-3.6-flash`, pinned and never an alias
([ADR-0007](adr/0007-llm-model-migration-to-gemini-3-6-flash.md)). Embeddings were unaffected, so
the corpus and every chunk id survived untouched.

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

- **The provider quota, and therefore the entire Phase 4 baseline.** The free tier cannot complete
  one evaluation run in a day (20 requests/day/model vs ~82 needed). The project owner has said
  they will clear it. Until then no score of this system exists. ([phase-4](progress/phase-4.md))
- **`backend/.env` is redundant and still on disk** with a duplicate of both API keys. The live
  config is the repo-root `.env`. Deleting it has been blocked by a permission prompt twice. It is
  gitignored and was never committed. **As of Phase 4 it also holds a stale model name**, which
  would resurrect the retired-model 404 for anyone whose tooling reads it.

## Carried-over open items

Full detail in each phase entry; these are the ones that will bite a later phase.

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
- **A model alias is never permitted in `LLM_MODEL`** — `gemini-flash-latest` and friends change
  silently under a frozen pipeline, and the results file would then name a configuration that no
  longer identifies what ran ([ADR-0007](adr/0007-llm-model-migration-to-gemini-3-6-flash.md)).
  Expect the pinned model to be retired in turn; the 404 is information, not a bug.
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
- **`health.py` carries a local session dependency** to be deleted when `api/deps.py` lands in
  Phase 5. ([phase-1](progress/phase-1.md))

## Adding an entry

A phase is not finished until its file exists (CLAUDE.md rule 11). Copy the shape of
[phase-2.md](progress/phase-2.md): what was built, an evidence table of real command output,
decisions made while building, deviations from PLAN.md and why, and open items. Then add the row
to the table above and lift anything blocking a human into the section above. Write it before the
phase commit and include it in that commit.
