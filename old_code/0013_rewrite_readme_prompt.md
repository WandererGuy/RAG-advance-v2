Rewrite README.md at the repo root. The current README is factually correct but
written for someone about to maintain the repo, not for an interviewer skimming
it in 90 seconds. New goal: a hiring manager or senior engineer reading for 90
seconds should understand what the system does, whether it actually runs, and
how I make technical decisions.

=== STEP 1: GATHER FACTS (do this before writing a single line) ===

Read the repo and extract real facts. Do not guess, do not fill in from memory.

1. .env.example and the config/settings module — current LLM model, embedding
   model, embedding dimension. NOTE: this repo has migrated from Gemini to
   OpenAI. Find EVERY remaining reference to Gemini (README, docs/, ADRs,
   .env.example, source, Makefile) and list them for me at the end. In the new
   README use only the OpenAI model strings you actually read from config —
   never write a model name from memory.
2. Chunking code — chunk size, overlap, splitting strategy (tokens / characters
   / heading-aware?), and whether page numbers are carried as chunk metadata.
3. Retrieval code — top-k, pure vector or hybrid, distance metric, reranking.
4. DB schema (SQLAlchemy models + Alembic migrations) — main tables and relations.
5. Corpus stats: number of documents, total pages, total chunks. Query the DB or
   read docs/progress/ if it's recorded there. If no source exists, omit it —
   do not estimate.
6. The 29-question golden set — where it lives, what fields each entry has.
7. The eval pipeline — which metrics are computed, what the LLM judge scores,
   why roughly two judgements per question, and the schema written to results/*.json.
8. The Makefile — the real target list and what each one actually does.
9. The Jinja2 prompts — how the system forces cited answers and forces an
   explicit refusal when the retrieved context is insufficient.
10. Find one REAL question/answer pair that has actually run (tests,
    docs/progress/, demo scripts, committed results). If you cannot find real
    output, DO NOT invent it: insert <<TODO: paste real output from make find>>
    and tell me.

=== STEP 2: WRITE THE README WITH THIS STRUCTURE ===

# rag-chatbot
One line on what it does, one line of corpus context (8 Vietnamese HR documents).

## Example
One real Q&A: Vietnamese question -> answer -> citation (document name + page).
Then a second example showing the "no information found in the documents" case.
This is the single most important section — put it first, in a code block.

## Status
Three or four lines: which phases are done, what runs today (ingest, retrieval,
eval), what does NOT exist yet (no chat endpoint — that's Phase 5; the only
route served today is /api/v1/health). State it plainly, no hedging.

## How it works
A one-line pipeline: PDF/DOCX -> parse -> chunk -> embed -> pgvector ->
retrieve top-k -> prompt -> answer + citations.
Then 4–5 design-decision bullets using the REAL numbers from Step 1: chunking,
retrieval, how page numbers survive so citations are possible, how the prompt
forces refusal on insufficient context. Add one bullet on Vietnamese-specific
handling (why this embedding model, diacritics/encoding issues parsing
Vietnamese PDFs) only if the repo actually shows evidence of it.

## Evaluation
29-question golden set over a frozen corpus. Which metrics, how the judge
scores, why ~3 provider calls per question. Baseline not yet committed — state
it once as a quota constraint, factually. No apology, no paragraph about it.

## Stack
Keep the old content, tightened. Update to OpenAI. Keep the ADR-0002 link and
the line about Celery/Redis/LangChain being deliberately out of v1.

## Running it
Five or six commands for a fresh machine. No more.

## Scope
In scope for v1 / out of scope for v1 — same spirit as the current README, shorter.

## Working rules
Keep both rules verbatim in spirit (a pipeline with committed results is frozen;
every number gets committed, including the bad ones). This is the strongest part
of the current README — do not dilute it.

## Operational notes
Push to the bottom: the FORCE=1 warning about invalidating relevant_chunk_ids
plus ADR-0005, the provider quota note, the full make target list, and the link
to docs/progress.md.

=== STEP 3: CONSTRAINTS ===

- English. Keep the existing voice: direct, no marketing, no emoji, no badges,
  no "🚀 Features" section.
- Every number in the README must be traceable to a file in the repo. If there's
  no source, write <<TODO: ...>> instead.
- Target ~120 lines. Shorter than the current README but denser in information.
- Preserve all existing internal links (CLAUDE.md, PLAN.md, docs/architecture.md,
  the ADRs) and verify each target file actually exists.
- Write to README.md. Do not create new files.

Finally, print two lists in your reply (not in the README):
(a) every remaining Gemini reference in the repo that needs fixing,
(b) every <<TODO>> left, and what I need to give you to fill it.