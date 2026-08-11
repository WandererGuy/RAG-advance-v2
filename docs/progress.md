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
| 4 — `naive-v1` baseline | ⬜ not started | — |
| 5 — API + thin frontend | ⬜ not started | — |
| 6 — Improvements | ⬜ not started | — |

## Where the project stands

The corpus is ingested and now **frozen** ([ADR-0005](adr/0005-frozen-corpus-for-the-golden-set.md)):
8 documents, 34 chunks, 768-dim embeddings, idempotent on re-run. `eval/datasets/golden_qa.v1.jsonl`
holds 29 questions with verified chunk citations. The build is green (`make lint`, `make validate`,
`make test` → 52 passed). Phase 4 is next and nothing blocks it: `naive-v1`, the dense retriever,
the runner and the first numbers in `results/`.

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

- **`backend/.env` is redundant and still on disk** with a duplicate of both API keys. The live
  config is the repo-root `.env`. Deleting it has been blocked by a permission prompt twice. It is
  gitignored and was never committed.

## Carried-over open items

Full detail in each phase entry; these are the ones that will bite a later phase.

- **Chunk ids are reassigned by any `--force` re-ingest**, which invalidates the golden set's
  `relevant_chunk_ids`. Now caught rather than prevented: the corpus is frozen in
  `eval/datasets/corpus.lock.json` and `make validate` fails loudly, naming what happened
  ([ADR-0005](adr/0005-frozen-corpus-for-the-golden-set.md)). Recovery still means looking every
  affected id up again. ([phase-3](progress/phase-3.md))
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
