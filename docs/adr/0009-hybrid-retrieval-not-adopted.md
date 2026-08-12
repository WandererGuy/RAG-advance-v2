# ADR-0009 — Hybrid retrieval (`hybrid-v2`) is built, measured, and not adopted

- **Date:** 2026-08-12
- **Status:** accepted
- **Supersedes:** nothing. **Superseded by:** nothing.

## Context

PLAN.md Phase 6 lists hybrid retrieval first, by benefit/effort ratio, with a specific prediction:
*"usually the single biggest improvement for enterprise documents: lots of internal jargon and
reference codes that embeddings capture poorly."* That prediction is worth testing, and Phase 4
left a sharper version of the question. `naive-v1` reached `recall@5` 0.958 — 23 of 24 answerable
questions already retrieve every relevant chunk — so there is almost no recall headroom to win.
The stated target was therefore **MRR and nDCG@5**: get the right chunk *higher*, not merely
present.

`hybrid-v2` changes exactly one variable against `naive-v1` (CLAUDE.md 5.4): the retriever.
`top_k` 5, `answer_v1.jinja`, `text-embedding-3-large` at 768 dim, `gpt-5.6-luna`, chunk size 800
and overlap 100 are all unchanged.

The implementation is described where it lives — `retrievers/bm25.py` and `retrievers/hybrid.py`
carry the reasoning for `simple` over `english`, OR- over AND-semantics, a Python stopword list,
and RRF-by-rank over a weighted score sum. Only the decisions that outlived the experiment are
repeated here.

## Decision

**`naive-v1` remains the served pipeline. `hybrid-v2` is kept, with its results committed, and is
not adopted.**

The numbers, over the same 29 agent-authored questions and the same frozen 8-document corpus
(read [ADR-0004](0004-agent-authored-golden-set.md) before quoting any of them):

| | recall@5 | MRR | nDCG@5 | faithful | relevance | refusal | p50 ms |
|---|---|---|---|---|---|---|---|
| `naive-v1` | **0.958** | 0.840 | **0.857** | 4.897 | 4.250 | 1.000 | 2009 |
| `hybrid-v2` | 0.938 | **0.844** | 0.845 | 5.000 | **4.542** | 1.000 | **1611** |

Hybrid loses recall and nDCG, wins MRR by 0.004, and wins `answer_relevance` by 0.29. It did not
hit the target it was aimed at.

**The aggregate hides what actually happened.** Only 6 of the 24 answerable questions changed
their retrieval at all. Hybrid improved 2 and degraded 4:

| | change | what moved |
|---|---|---|
| q002 | ✅ rank 2 → 1 | the relevant chunk was already there, keyword agreement lifted it |
| q017 (multi_hop) | ✅ rank 3 → 1 | **RRF working as designed** — both halves agreed on chunk 5 |
| q006 | ❌ rank 1 → 2 | a keyword-heavy neighbour displaced it |
| q009 | ❌ rank 3 → 4 | as above |
| q024 (multi_hop) | ❌ rank 1 → 2 | as above |
| q021 (multi_hop) | ❌ **recall 1.0 → 0.5** | chunk 20 fell out of the top 5 entirely |

q021 is the whole recall regression and it is the diagnostic case. The question asks what penalty
applies for *lending a colleague your login account*. Chunk 20 (the account and password policy)
was displaced by chunks 28 and 29 from the code-of-conduct document, which share the surface words
`công việc`, `xử lý` and `vi phạm` with the question while being about something else entirely.
The keyword half was confidently wrong, and RRF gives it an equal vote.

**Why the predicted win did not materialise here.** The corpus is 8 synthetic HR documents written
in plain policy Vietnamese. It contains almost none of what BM25 exists to catch: no part numbers,
no reference codes in the questions, no rare jargon that an embedding model would miss. The one
lexical anchor a question does use (`HR-IT-05`-style document codes) never appears in the golden
set's phrasing. On this corpus, the dense retriever was already finding what there is to find, so
the keyword half had little to add and a real opportunity to do harm.

This is a statement about **this corpus**, not about hybrid retrieval.

## Consequences

**What is kept.** `bm25.py`, `hybrid.py`, `hybrid_v2.py`, their tests, and
`results/hybrid-v2.json` all stay in the tree. Negative results are information (PLAN.md
Phase 6), and the code is the cheap part of re-testing this later — the expensive part was
deciding how to fuse two rankings, and that is now written down and tested. The GIN index stays
too: it is index-only, costs one write per chunk on ingest, and re-testing without it would mean
another migration.

**What is not claimed.** `hybrid-v2` is **not** proven worse in a way that generalises. Two facts
limit how hard this result can be pushed:

1. **The differences are within noise for a dataset this size.** 6 questions changed out of 24. A
   single question is worth ~0.042 of recall; the entire recall gap is half of one question.
2. **Generation metrics are not reproducible run-to-run.** `hybrid-v2` was run twice on identical
   code and an identical corpus. Retrieval was byte-identical both times (0.9375 / 0.8438 /
   0.8449 — it is deterministic). Generation was not: `refusal_accuracy` came out 0.8 on the first
   run and 1.0 on the second, faithfulness 4.862 then 5.000, because `gpt-5.6-luna` rejects
   `temperature=0` and every run samples ([ADR-0008](0008-provider-migration-to-openai.md)). **The
   committed file is the second run.** Any generation-metric gap smaller than ~0.2 between two
   pipelines is indistinguishable from re-running the same one.

The `answer_relevance` win of +0.29 is therefore *suggestive and not conclusive*, and it is the
one result here worth following up.

**What would change this decision** — any of:

- **A corpus with real lexical anchors.** The moment ingest holds documents with part numbers,
  contract IDs, or internal jargon — and questions that quote them — this experiment should be
  re-run before anything else in Phase 6. That is the case PLAN.md was describing, and it has not
  been tested yet.
- **A human-written `golden_qa.v2.jsonl`.** Agent-written questions paraphrase the source text,
  which flatters dense retrieval specifically: the question and the chunk were produced from the
  same words. Humans quote and abbreviate, which is where keyword matching earns its place. ADR-0004
  already names this as the highest-value human action on the project; it is also the single change
  most likely to reverse this ADR.
- **Weighting the fusion.** RRF here gives both retrievers an equal vote, and on this corpus dense
  is the stronger of the two. A weighted RRF favouring dense would likely keep q002 and q017 while
  not losing q021 — but it is a new pipeline (`hybrid-w-v3`), one variable, its own results file.

**What was fixed on the way.** `eval/runner.py` hardcoded `retriever="dense"` into the config of
every pipeline it ran — correct while dense was the only retriever, and a mislabelling bug the
moment a second one existed. The first `hybrid-v2` run genuinely used hybrid retrieval while its
results file said `"retriever": "dense"`. The runner now passes no config and lets each pipeline's
`build()` name its own retriever. `results/naive-v1.json` is unaffected: it says `dense` and it
was dense.

**Serving is unchanged.** `PIPELINE_NAME` stays `naive-v1`. Pointing it at `hybrid-v2` is a
one-line `.env` change with no code change, which is what the registry is for — the option is
open, it is simply not the default.
