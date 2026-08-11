# ADR-0005 — The corpus is frozen, and the freeze is machine-checked

- **Date:** 2026-08-11
- **Status:** accepted

## Context

`relevant_chunk_ids` in the golden set are bare integers pointing at `chunks.id`. Those ids are
assigned by Postgres on insert, and `make ingest FORCE=1` deletes every chunk of a document and
reinserts it — so the same document, unchanged, comes back with different ids. This has been a
known open item since Phase 2 (`docs/progress/phase-2.md`).

The failure is silent and expensive. Nothing errors: the ids still exist, the pipeline still
retrieves, the judge still scores. Recall simply drops, across the board, and looks exactly like a
pipeline regression. The natural response — tune the retriever — chases a bug in the dataset. Worse,
if it happens between two committed results files, the comparison between them is meaningless and
nothing in either file records why.

Alternatives to bare ids were considered and rejected:

- **Cite `(file_hash, chunk_index)` instead of `chunk.id`.** Genuinely more stable, and it would
  survive a re-ingest. Rejected because it does not survive a *chunker* change, which renumbers
  `chunk_index` too — so it trades one silent failure for a rarer one, at the cost of a
  compound key threaded through the runner, the metrics and every results file. The lock catches
  both cases with none of that.
- **Cite a text snippet and re-resolve it at eval time.** Robust to renumbering, but it makes
  every eval run depend on a fuzzy match, and a snippet that resolves to two chunks after a
  chunk-size change fails in a new and more confusing way.
- **Just write it down in the README.** It has been written down since Phase 2. The trap is one
  flag on a routine command, and the whole point is that nobody notices they hit it.

## Decision

The corpus behind `eval/datasets/*.jsonl` is **frozen** at the state ingested on 2026-08-09:
8 documents, 34 chunks, ids 1–34.

`eval/datasets/corpus.lock.json` records, per document, its `file_hash` and the list of chunk ids
that hash produced, plus a SHA-256 digest over `(file_hash, chunk_index, content)` for every chunk.
`python -m eval.datasets.validate` compares the lock against the live database on every run and
fails loudly, naming what someone did:

- **chunk ids changed** for a document whose hash is unchanged → a `FORCE=1` re-ingest happened;
  every `relevant_chunk_ids` now points at the wrong text.
- **a document is in the lock but not the database** → deleted, or edited and re-ingested under a
  new hash.
- **a document is in the database but not the lock** → the corpus grew after the freeze.
- **ids match but the digest does not** → the chunker changed under a frozen corpus, so every
  question was written against text that no longer exists.

Re-freezing is explicit and separate: `validate.py --write-lock`. It is never automatic, and it is
not the remedy for a failing check — overwriting the lock makes the error disappear without making
the dataset correct again.

## Consequences

**What this costs.** Adding a document to the corpus is no longer free. It now means: ingest,
extend the golden set to cover the new material, re-run `--write-lock`, and treat every existing
`results/*.json` as measured against a different corpus. That friction is the point — it makes the
cost visible at the moment it is incurred rather than three phases later.

**What it does not protect.** The lock notices drift, it does not prevent it: `make ingest FORCE=1`
still runs and still renumbers. Recovery from an accidental re-ingest is to look the affected chunk
ids up again with `scripts/find_chunks.py` and correct the dataset — the questions themselves stay
valid, only their citations break. And nothing here freezes the *files*: editing a PDF in place
changes its `file_hash`, which the lock reports as a deleted document plus an added one.

**Interaction with the pipeline immutability rule.** CLAUDE.md 4.1 already freezes a pipeline once
it has results. This freezes the other half of the same measurement. A results file is only
comparable to another when the pipeline, the dataset version and the corpus lock all match — which
is why `dataset_version` and `golden_set_author` are recorded in every one of them (ADR-0004).

**When to unfreeze.** When the corpus stops being a demo corpus. Eight documents make retrieval
metrics optimistic anyway (`docs/progress/phase-0.md`); the moment real volume arrives, the golden
set is rewritten against it and the lock is regenerated in the same commit — not before, and never
piecemeal.
