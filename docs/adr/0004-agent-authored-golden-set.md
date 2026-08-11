# ADR-0004 — The golden set is agent-authored, and every number must say so

- **Date:** 2026-08-11
- **Status:** accepted

## Context

PLAN.md Phase 3 and CLAUDE.md rule 5.6 make the golden set a hard human gate: *"DO NOT generate
questions yourself. If asked to, refuse and explain why."* The reason is sound — a golden set
written by the system under test measures the system against its own idea of a good question.

The gate has been open since Phase 0. No golden-set author was ever named, and no human is
available to name one. Phase 3 blocks Phase 4, which blocks everything: with no dataset there is
no baseline, and with no baseline every Phase 6 change is a guess. The project is otherwise
stalled indefinitely.

On **2026-08-11 the project owner authorised the agent to take this gate**, conditional on the
inflation being written down and carried by every number the project ever produces. This ADR is
that condition. The same authorisation covered the Phase 2 sign-off, which is recorded in
`docs/progress/phase-2.md`, not here — it was a verification, not a design decision.

## Decision

`eval/datasets/golden_qa.v1.jsonl` is **written by the agent** and labelled as such in the data
itself, not only in prose.

- Every line carries an **`author`** field — `"agent"` for every v1 line, a person's name when a
  human writes one. It is per-line, not per-file, so a future mixed set stays honest row by row.
- `eval/datasets/validate.py` **rejects any line without `author`**. A dataset that has lost its
  provenance fails validation rather than being silently used.
- Every `results/*.json` from Phase 4 on carries **`golden_set_author`** — the sorted distinct
  authors in the dataset it ran against — beside the existing `dataset_version`. `eval/report.py`
  prints it as a column in `results/leaderboard.md`. **No number from this project may be quoted
  without it.** CLAUDE.md rule 8 is amended to say so.

Method constraints on the writing, chosen to limit the inflation rather than pretend it is absent:

- Questions are drafted from the **rendered PDF pages**, not from the chunk text, so the
  chunker's vocabulary and boundaries do not leak into the question.
- Wording is deliberately **paraphrased away from the source sentence**. A question that reuses
  the document's own noun phrase is testing string matching, not retrieval.
- `unanswerable` questions must be **in-domain near-misses** — a plausible HR policy this corpus
  does not contain — never obvious out-of-domain topics. The easy version measures nothing.
- `relevant_chunk_ids` are looked up afterwards with `scripts/find_chunks.py` against a frozen
  corpus, not asserted from memory.

Rejected alternatives:

- **Keep refusing and stop the project.** The honest reading of rule 5.6, and it costs everything
  downstream. Rejected because a labelled, known-inflated baseline is worth more than no baseline,
  and the label makes it impossible to mistake one for the other.
- **Generate questions with a different model to "break the correlation".** A second model from a
  different family would reduce the phrasing overlap but not the structural problem: the questions
  would still be derived from the corpus by a machine, and the judge in Phase 4 is still an LLM.
  It buys the appearance of independence, which is worse than a stated dependence.
- **Skip the eval and go straight to a demo.** This is exactly what PLAN.md warns about ("without
  a baseline, everything in Phase 6 is just gut feeling").

## Consequences

**What this inflates — read before quoting any Phase 4+ number.**

| Metric | Direction | Why |
|---|---|---|
| `recall@k`, `MRR`, `nDCG@k` | **inflated, most severely** | The questions were derived from the corpus, so a relevant chunk provably exists and shares vocabulary and phrasing with the question. Real users ask in words the document never uses. |
| `faithfulness`, `answer_relevance` | **inflated** | LLM-as-judge scores an answer against a `ground_truth` an LLM wrote. Errors are correlated: the judge shares the writer's blind spots and agrees with itself. |
| `refusal_accuracy` | **inflated, and the least trustworthy** | The hard `unanswerable` case is the plausible near-miss. An agent picking what is "absent" is biased toward absences it can already see, which are the easy ones. This is the number most likely to look fine and be wrong in production. |
| Vietnamese input robustness | **not measured at all** | Agent questions are clean, fully diacriticised policy prose. Real employees write elliptically, with typos, abbreviations and no diacritics. |
| **Relative** comparison between pipelines | **still valid** | Two pipelines run against the same dataset are still ranked correctly by it. This is the one use the numbers are fit for — the same standing caveat the 8-document corpus already carries (see `docs/progress/phase-0.md`). |

So: **use these numbers to choose between pipelines; never to claim the system is accurate.**

**Trigger for replacement.** v1 is frozen once committed and is never edited (PLAN.md's versioning
rule). A human writes `golden_qa.v2.jsonl` — not a patch to v1 — when any of these fires:

1. **Before any number leaves the team** as a quality claim to a stakeholder, in a demo, or in a
   go/no-go decision. An agent-authored score is an engineering instrument, not evidence.
2. **Before Phase 6 accepts or rejects a pipeline on `refusal_accuracy` or `faithfulness`**
   alone. Those two are the most inflated; a decision resting only on them rests on this ADR's
   weakest ground.
3. **When two pipelines score within noise of each other** on the retrieval metrics. That is the
   dataset being too easy to separate them, not the pipelines being equivalent.
4. **As soon as the Phase 5 `queries` table holds real user questions.** That is the natural
   source of a human-grounded v2 and the cheapest one — real questions with a human writing the
   ground truth. Prefer this trigger; the others are backstops.

**Cost of reversal.** Low, and deliberately so. v2 does not invalidate the code — the runner takes
`--dataset`, and every results file already names its `dataset_version` and `golden_set_author`,
so v1 numbers stay interpretable forever. What it does destroy is comparability *across* dataset
versions: a v1 score and a v2 score are not the same measurement and must never share a
leaderboard row. Expect every absolute number to drop when v2 lands. That drop is the measurement
working, not a regression — and the size of it is the real value of this ADR.
