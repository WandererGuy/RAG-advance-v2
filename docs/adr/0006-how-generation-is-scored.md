# ADR-0006 — How generation is scored: a self-grading judge, and a refusal that is not judged

- **Date:** 2026-08-11
- **Status:** accepted

## Context

Phase 4 has to turn an answer into a number. Retrieval is arithmetic — `recall@k`, `MRR`,
`nDCG@k` are fully determined by the ranking and the golden set. Generation is not: whether an
answer is grounded in its context, and whether it actually answers the question, are judgements.

PLAN.md specifies LLM-as-judge with `faithfulness`, `answer_relevance` and `refusal_accuracy`.
Three things about our situation make that specification underdetermined:

1. **There is one provider configured.** ADR-0001 approved Gemini; nothing else has a key. So the
   judge is the same model that wrote the answer, which is a known bias — models score their own
   output higher than a third party's, and higher than a human would.
2. **`refusal_accuracy` is the safety-critical metric of this project.** The corpus is HR policy;
   ADR-0004 already flags this as the metric the agent-authored golden set inflates most
   dangerously. Asking a model "did it refuse?" makes the number that matters most depend on the
   component we trust least.
3. **The five `unanswerable` questions have a `ground_truth` that is prose about what the system
   must not do** ("Không có trong tài liệu. … Hệ thống phải trả lời là không tìm thấy thông tin"),
   not an answer. Feeding that to a relevance judge as a reference answer scores nonsense.

Alternatives considered:

- **A second provider as an independent judge.** The right answer for a system that ships. It needs
  a second API key, a second data-boundary decision on top of ADR-0001, and a second dependency,
  for a baseline whose numbers are already caveated by an agent-authored dataset. Deferred, with
  the trigger named below.
- **Human scoring of 29 answers.** More trustworthy than either. Nobody is available — the same
  gap that produced ADR-0004 — and a metric that only exists when someone is free is not a metric
  Phase 6 can iterate against.
- **Judge refusal with the model too**, for consistency with the other two. Rejected: see below.
- **String-match the answer against `ground_truth`** instead of judging. Vietnamese paraphrase
  makes this measure phrasing, not correctness, and it would reward a pipeline for copying the
  document's wording — the exact failure ADR-0004's question-writing method was designed against.

## Decision

**1. The judge is the answering model, and every results file says so.** `eval/metrics/generation.py`
scores `faithfulness` (1–5, against the chunks the answer actually received) and `answer_relevance`
(1–5, against the golden set's reference answer) through `eval/judge_prompts/*_v1.jinja`. Every
`results/*.json` carries `judge_model` and the boolean `judge_is_answer_model`, and
`leaderboard.md` prints a line naming the pipelines that self-graded. `--judge-model` swaps the
judge without touching a pipeline.

**2. Refusal is detected, not judged.** `is_refusal()` matches the exact sentence that
`answer_v1.jinja` requires, normalised for case, Unicode form and whitespace. The prompt receives
that sentence as a variable from the same constant the detector uses, so the two cannot drift.
`refusal_accuracy` is therefore arithmetic, like the retrieval metrics, and does not move when the
judge has a bad day.

**3. Four outcomes, not two.** Every answer is classified `answered`, `correct_refusal`,
`hallucinated` (answered a question the corpus cannot support) or `over_refusal` (refused an
answerable one). `refusal_accuracy` is `correct_refusal / unanswerable`; `over_refusal_rate` is
reported separately. Collapsing these into one score would let a pipeline that refuses everything
look safe.

**4. Faithfulness is judged on every question; relevance only on answerable ones.** A fabricated
answer to an `unanswerable` question is the worst thing this system can do, so it must not be
excluded from the faithfulness measurement. Relevance is skipped there because the reference text
is a description of correct behaviour, not an answer — that is what `refusal_outcome` measures.

**5. A judge that fails produces `None`, never a default.** Unparseable output, an out-of-range
score, or a call that failed after one retry is recorded as a failure with its reason, excluded
from the mean, and counted in `judge_failures` next to the mean it is missing from. A silent 3/5
for a call that never succeeded is indistinguishable from a real mediocre answer.

**6. Citations are checked without a model.** Every `[filename, p.N]` in an answer is resolved
against the chunks that answer was given. One that matches nothing is kept with `supported=false`
and counted as `unsupported_citations` — a fabricated source, and the failure a reader is most
likely to believe.

## Consequences

**Read `faithfulness` and `answer_relevance` as biased upward.** They are useful for the one thing
Phase 6 needs — the direction and size of a change between two pipelines on the same dataset — and
they are not evidence of quality in absolute terms. Combined with ADR-0004 (the questions are
agent-authored) and the 8-document corpus, no absolute number this project produces should be
quoted outside it without all three caveats attached.

**`refusal_accuracy`, `over_refusal_rate` and every retrieval metric are not model opinions.** They
are the numbers to trust when the two kinds disagree. They are still measured against agent-written
questions, so ADR-0004 still applies to what they are measuring — but not to how they are measured.

**A prompt change is a new file and a new pipeline.** `answer_v1.jinja` and the judge prompts are
frozen the moment `results/naive-v1.json` is committed. A `v2` rubric changes what every score
means, so it lands as `faithfulness_v2.jinja` and the affected results are re-run, never edited.

**The refusal string is now load-bearing.** Changing `REFUSAL_MARKER` changes what every committed
refusal number means. It moves only with a new prompt version and a new pipeline name.

**When to revisit.** Any of these makes the second judge mandatory rather than better: a decision
to publish a number outside the team; a Phase 6 experiment whose entire claimed improvement is
under one point of self-graded faithfulness; a pipeline that changes the answering model, where a
self-grading judge silently changes the grader at the same time as the thing being graded; or a
human becoming available to spot-check 29 answers, which would also quantify the bias for the
first time.
