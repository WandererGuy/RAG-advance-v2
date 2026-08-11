# ADR-0007 — The answering model moves to `gemini-3.6-flash`, pinned, never an alias

- **Date:** 2026-08-11
- **Status:** accepted — supersedes the LLM row of [ADR-0002](0002-tech-stack-resolution.md)

## Context

The first attempt at the Phase 4 baseline run failed on every question, at the answer call, with
the provider returning HTTP 404:

```
LLMCallFailed: completion failed after 5 attempts (gemini/gemini-2.5-flash):
litellm.NotFoundError: GeminiException - {"error": {"code": 404,
  "message": "This model models/gemini-2.5-flash is no longer available to new users. …"}}
```

`gemini-2.5-flash` — the model ADR-0002 recorded and `.env` named — has been retired for keys
created after its cut-off. Our key is one of those. Note the shape of the failure: the model is
still listed by the `models` endpoint and only 404s on `generateContent`, so "is it configured
correctly" and "does it still work" are different questions.

Embedding was unaffected: `gemini-embedding-001` still serves this key, retrieval scored normally,
and the 34-chunk corpus and its 768 dimensions are untouched. **This is a generation-side change
only** — no re-ingest, no migration, no invalidated embeddings.

Candidates verified working against the live key before choosing: `gemini-3.6-flash`,
`gemini-3.5-flash`, `gemini-flash-latest`, `gemini-2.5-pro`.

## Decision

`DEFAULT_LLM_MODEL_NAME=gemini-3.6-flash` — the current stable flash-tier model, **pinned by
version**. Chosen by the project owner on 2026-08-11 from the verified list above.

**No moving aliases.** `gemini-flash-latest` resolves to a different model over time, which would
silently change the model behind a frozen pipeline: `results/naive-v1.json` would say
`gemini/gemini-flash-latest` and two runs of it, months apart, would be two different systems with
one name. Pipeline immutability (CLAUDE.md 4.1) is only meaningful if the config recorded in a
results file identifies exactly what ran. Aliases are therefore not permitted in `LLM_MODEL`.

**Same tier, deliberately.** PLAN.md Phase 4 wants a cheap, fast baseline; `gemini-2.5-pro` also
works with this key and was rejected for that reason. Trying a stronger model is a legitimate
Phase 6 experiment — as a new pipeline, changing exactly one variable, with its own results file.

The changed places, all of which had to move together: `.env`, `.env.example`,
`Settings.default_llm_model_name` (the fallback when `.env` is absent), and the documentation
lines in `CLAUDE.md`, `PLAN.md` and `README.md` that quoted the old model.

## Consequences

**The baseline is `gemini-3.6-flash` from its first committed number.** No results file was ever
produced against `gemini-2.5-flash`, so nothing had to be re-run and no comparison is broken. Had
this happened one commit later it would have invalidated the baseline, which is the argument for
keeping `llm_model` inside `PipelineConfig` and inside every results file.

**A retired model is now a known failure mode, and it is loud.** `LLMCallFailed` names the model
and the provider message, the runner records the failure per question rather than aborting, and a
run where every question failed writes a results file with `failed_questions: 29` instead of
silently producing nothing. That is how this was diagnosed in one run.

**The judge moved with it.** ADR-0006's self-grading judge is the answering model, so both sides
of every generation score changed at once. Since no numbers existed before, there is nothing to
compare across the change — but this is exactly the coupling ADR-0006 names as a reason to revisit
the single-judge decision when a *pipeline* changes model.

**Historical ADRs are not rewritten.** ADR-0002's table still says `gemini-2.5-flash`; that was
true when it was written. This ADR supersedes that row, and the "as built" column in CLAUDE.md
points here.

**When to revisit.** When this model is retired in turn — expect it, and treat the 404 as
information rather than a bug in the code. The response is the same each time: verify candidates
against the live key, pick a pinned version, write the ADR, and re-run every pipeline whose
results are still being compared, because a model change invalidates every generation number
measured against the old one.
