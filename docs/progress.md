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
| 2 — Synchronous ingest | 🟡 built, awaiting a human eyeball check | [progress/phase-2.md](progress/phase-2.md) |
| 3 — Golden set | ⬜ blocked, see below | — |
| 4 — `naive-v1` baseline | ⬜ not started | — |
| 5 — API + thin frontend | ⬜ not started | — |
| 6 — Improvements | ⬜ not started | — |

## Where the project stands

The corpus is ingested: 8 documents, 34 chunks, 768-dim embeddings, idempotent on re-run. The
build is green (`make lint`, `make test` → 31 passed). Nothing in Phase 2 is waiting on code.

## Blocked on a human — read before starting anything

1. **Nobody is named as the golden-set author.** Phase 3 is the next phase and is a hard gate: the
   agent must not write the questions (CLAUDE.md 5.6). This has been open since Phase 0 and now
   blocks all forward progress.
2. **Phase 2 is not signed off.** Its Definition of Done is a human reading 5 random chunks and
   confirming no lost diacritics, no header/footer contamination, no half-words, correct `page_no`.
   Draw a sample with `SELECT content, page_no FROM chunks ORDER BY random() LIMIT 5;`.
3. **`backend/.env` is redundant and still on disk** with a duplicate of both API keys. The live
   config is the repo-root `.env`. Deleting it has been blocked by a permission prompt twice. It is
   gitignored and was never committed.

## Carried-over open items

Full detail in each phase entry; these are the ones that will bite a later phase.

- **Chunk ids are reassigned by any `--force` re-ingest**, which invalidates the golden set's
  `relevant_chunk_ids`. Freeze the corpus before Phase 3 is written. ([phase-2](progress/phase-2.md))
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
