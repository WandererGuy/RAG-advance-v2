# ADR-0010 — Cross-encoder reranking (`rerank-v1`) is adopted and served

- **Date:** 2026-08-14
- **Status:** accepted
- **Supersedes:** nothing. **Superseded by:** nothing.
- **Amends:** [ADR-0008](0008-provider-migration-to-openai.md) — adds a third provider (Voyage) to
  a stack that ADR-0008 consolidated onto OpenAI. See *Consequences → A third vendor*.

## Context

Phase 6's second experiment, and the first pipeline in this project to beat the baseline.

[ADR-0009](0009-hybrid-retrieval-not-adopted.md) established the target. `naive-v1` reached
`recall@5` 0.958, so "find the chunk" was nearly solved and the remaining headroom was **ordering**
— MRR 0.840 and nDCG@5 0.857 mean the right chunk was frequently retrieved but not first. Hybrid
retrieval was aimed at that and missed, for a reason that also pointed at the fix: RRF gives the
keyword half an equal vote, so it could *displace* a relevant chunk (q021) while trying to promote
others. A reranker reorders a candidate list without dropping anything from it.

`rerank-v1` changes exactly one variable against `naive-v1` (CLAUDE.md 5.4): a second retrieval
stage. `top_k` 5, `answer_v1.jinja`, `text-embedding-3-large` at 768 dim, `gpt-5.6-luna`, chunk
size 800 and overlap 100 are all unchanged. Dense retrieval is widened to `RERANK_TOP_N=20`
candidates, a cross-encoder scores all 20 against the question, and the top 5 go to the prompt —
so the generation half sees the same number of chunks as the baseline.

## Decision

**`rerank-v1` is adopted and is now the served pipeline.** `PIPELINE_NAME=rerank-v1`.

Over the same 29 agent-authored questions and the same frozen 8-document corpus (read
[ADR-0004](0004-agent-authored-golden-set.md) before quoting any of these):

| | recall@5 | MRR | nDCG@5 | faithful | relevance | refusal | p50 ms |
|---|---|---|---|---|---|---|---|
| `naive-v1` | 0.958 | 0.840 | 0.857 | 4.897 | 4.250 | **1.000** | **2009** |
| `hybrid-v2` | 0.938 | 0.844 | 0.845 | **5.000** | **4.542** | **1.000** | **1611** |
| `rerank-v1` | **1.000** | **0.979** | **0.970** | 4.793 | 4.458 | 0.800 | 2074 |

**Every retrieval metric improves, and none regresses.** MRR 0.840 → 0.979 means the first
relevant chunk is at rank 1 for all but one answerable question. This was run twice; both runs
returned retrieval byte-identical (`1.0 / 0.9792 / 0.9699`), as retrieval is deterministic.

**The per-question breakdown is the strongest part of the result.** Of 24 answerable questions,
**6 improved and 0 degraded**:

| | change | what moved |
|---|---|---|
| q003 | ✅ **not retrieved → rank 1** | the entire recall gain, and the baseline's only `over_refusal` |
| q002 | ✅ rank 2 → 1 | |
| q009 | ✅ rank 3 → 2 | the chunk hybrid demoted to 4 |
| q010 | ✅ rank 2 → 1 | |
| q015 | ✅ rank 2 → 1 | |
| q017 (multi_hop) | ✅ rank 3 → 1 | also the case RRF got right |

Nothing was displaced. That is the structural difference from hybrid: RRF re-scores a *merged*
list and can push a relevant chunk out of the top 5, while a reranker only reorders candidates
dense already found. The failure mode ADR-0009 diagnosed on q021 cannot occur here.

**q003 is the case worth reading.** The baseline never retrieved its relevant chunk, so the model
correctly declined to answer — scored as an `over_refusal`. Widening to 20 candidates surfaced the
chunk and the cross-encoder ranked it first. One fix removed a recall miss and an over-refusal
together, which is what "the headroom is in ordering" looks like in practice.

**Latency is unchanged in practice**: p50 2074 ms vs 2009 ms (+65 ms), and p95 actually improves
(3901 vs 4112). Reranking 20 short chunks is cheap next to generation.

## Consequences

**`refusal_accuracy` drops to 0.800, and the cause is not reranking.** This is the one metric that
regresses and it deserves the space.

Two runs scored **0.6 and 0.8** — a 0.2 spread on identical code, consistent with the
non-reproducibility ADR-0009 recorded. Per-question, the picture is precise: `q029` flipped between
runs (noise), while **`q025` failed in both** and refuses correctly under the baseline. So one
question reproducibly regressed, not the metric generally.

`q025` asks the year-end bonus rate for an employee on 6 months' maternity leave — `unanswerable`,
empty `relevant_chunk_ids`. The `rerank-v1` answer:

> Tài liệu chỉ quy định nghỉ thai sản 06 tháng [04_nghi_phep_va_lam_viec_tu_xa.pdf, p.1]. Quy định
> thưởng theo tỷ lệ tháng làm việc thực tế chỉ áp dụng cho nhân viên vào làm trong năm
> [02_quy_che_luong_thuong_phuc_loi.pdf, p.2]. **Tài liệu không nêu tỷ lệ thưởng cuối năm đối với
> nhân viên nghỉ thai sản.**

It states plainly that the documents do not contain the answer, cites two real adjacent facts
correctly, and invents nothing. The judge scored it **faithfulness 5.0**. It counts as a
hallucination solely because `is_refusal()` matches one exact sentence by the deliberate design of
[ADR-0006](0006-how-generation-is-scored.md), and this answer does not open with it.

**Better retrieval caused it.** For an unanswerable question there is no correct chunk, so a
reranker returns the most topically *adjacent* material it can find — which is exactly what
invites a hedge. `naive-v1`'s weaker top-5 gave the model less to work with, so it fell back to the
canned sentence. This is the hedging blind spot flagged since Phase 4, now reproducing on demand
rather than intermittently.

**This is therefore counted as evidence for fixing the refusal contract, not as a cost of
reranking.** The open human decision (Phase 4, Phase 5, `progress.md`) is unchanged and now has a
reproducible test case: `q025` under `rerank-v1`. Adopting a pipeline whose `refusal_accuracy`
reads 0.800 is only defensible *because* the one reproducible failure is a detector artifact on an
answer that is substantively correct — and that is a claim about this specific question, verified
by reading it, not an argument that low refusal scores are generally acceptable.

**A third vendor, and a third metered key.** [ADR-0008](0008-provider-migration-to-openai.md)
consolidated the stack onto OpenAI; this adds Voyage (`voyage/rerank-2.5-lite`) for reranking
only. Accepted deliberately, with the lock-in kept shallow: `RerankerProvider` is an interface,
`RERANK_PROVIDER` selects between Voyage, Cohere, Together, DeepInfra, Fireworks and WatsonX via
LiteLLM's `arerank`, plus a direct adapter for Jina. Switching vendors is an `.env` change.
OpenAI does not offer a reranking endpoint, so serving this result at all means a second vendor;
the alternative was a self-hosted cross-encoder, which [ADR-0001](0001-scope-va-data-boundary.md)
does not require since data may leave for an approved external API.

**What this does not prove.**

1. **The corpus is 8 synthetic documents and the questions are agent-authored.** `recall@5` 1.000
   means "perfect on 24 paraphrase-derived questions over 34 chunks", not "perfect". A ceiling
   reached on an easy dataset is the least transferable kind of result, and it removes the headroom
   that made this experiment measurable — the next retrieval experiment has nothing left to win on
   recall here.
2. **Generation metrics still do not reproduce.** `faithfulness` 4.793 vs the baseline's 4.897 and
   `answer_relevance` 4.458 vs 4.250 are both well inside the ~0.2 noise floor and mean nothing.
   Only the retrieval columns and the `q025` diagnosis carry weight.

**What is kept.** `rerankers/` (base + providers), `retrievers/reranker.py`, `pipelines/rerank_v1.py`,
their tests, and both results files. `rerank-v1` is now **frozen** (CLAUDE.md 4.1): its results are
committed, so those files must not be edited. A different `RERANK_TOP_N`, a different reranker
model, or reranking on top of hybrid is a new pipeline with a new name.

**What would change this decision** — any of:

- **A human-written `golden_qa.v2.jsonl`.** Still the highest-value action on the project
  (ADR-0004). Agent questions paraphrase the source, which flatters dense retrieval; a reranker
  sits on top of dense candidates, so `v2` tests both stages at once. Perfect recall here is the
  clearest sign the current dataset has stopped discriminating between pipelines.
- **The refusal contract being decided.** If hedging becomes acceptable, `rerank-v1`'s
  `refusal_accuracy` is 1.000 in both runs and the only regression disappears. If hedging is
  forbidden by prompt instead, that is a new prompt file and a new pipeline.
- **Voyage cost or availability.** A per-query external call now sits in the served path.
  `RERANK_PROVIDER` is the switch; falling back to `naive-v1` is a one-line `.env` change.

**Serving changed.** `PIPELINE_NAME` is `rerank-v1` in the local `.env`. `.env.example` keeps
`naive-v1` as the committed default, so a fresh clone runs with no Voyage key and no third-party
dependency until someone opts in.

Note how that opt-in fails if it is done wrong. With `PIPELINE_NAME=rerank-v1` and an empty
`RERANK_API_KEY`, the Voyage path builds cleanly and raises `RerankFailed` at the first `/chat`
call, not at startup — LiteLLM is handed `api_key=None` and only the Jina adapter validates the
key in its constructor. A deployment that forgets the key therefore starts healthy and fails per
request. Validating `RERANK_API_KEY` at construction for every provider is an obvious improvement
and is deliberately **not** made here: `rerank_v1.py` and `rerankers/` are frozen by this ADR, so
it belongs to whoever next touches that code path.
