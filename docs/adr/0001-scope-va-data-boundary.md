# ADR-0001 — Scope and data boundary

- **Date:** 2026-08-09
- **Status:** accepted

## Context

Five questions had to be answered by a human before any code was written (PLAN.md Phase 0). The
first one is the one that kills the project if asked late: whether internal company documents may
be sent to a third-party API. Every other stack choice depends on the answer.

Three of the five were answerable from evidence already in the repository and were verified rather
than guessed; two required a human decision and were answered on 2026-08-09.

## Decision

**1. May the data leave for an external API?** — **Yes.** Google Gemini is approved. Document text
(chunks) and user questions are sent to the Gemini API for embedding and for answer generation.

Consequence accepted: no self-hosted inference is needed, so the stack stays as configured in
`backend/.env` (`gemini-2.5-flash`, `gemini-embedding-001`). Had the answer been no, the whole
stack would have moved to Ollama + `bge-m3` and this ADR would have been superseded.

**2. Do we have 20–50 real documents?** — **No, we have 8**, and 8 was accepted as sufficient for
v1. They are in `data/raw/HR_pdfs/`: employee handbook, compensation, grading and appraisal, leave
and remote work, information security, hiring and probation, code of conduct, travel expenses. They
are HR policy documents for a fictional Công ty Cổ phần Công nghệ Vector.

**These 8 PDFs are synthetic demo documents, not real company data.** They are therefore
**committed to the repository** and may be shown, shared and read freely — in a demo, in a
screenshot, in a bug report. `data/raw/HR_pdfs/` is un-ignored in `.gitignore` for exactly this
reason, while the rest of `data/raw/` stays ignored so that a real document dropped in later is
never committed by accident. Confirmed by the owner on 2026-08-12.

Consequence accepted: a small corpus makes retrieval metrics noisier and inflates recall@k, because
there are fewer distractor chunks to confuse the retriever than there would be in production. The
absolute numbers in `results/` are therefore optimistic; the *relative* comparison between
pipelines, which is what Phase 6 uses them for, stays valid. If the corpus grows, the golden set
must be re-validated and every pipeline re-run — results across different corpus sizes are not
comparable, so `results/*.json` records which corpus was used.

**3. Document language?** — **Vietnamese only.** Verified by extracting text: all documents are
Vietnamese with full diacritics. This makes tokenisation for BM25 (Phase 6) a real question rather
than a formality — Postgres has no Vietnamese text-search configuration, so `simple` will be the
starting point.

**4. Text PDFs or scanned?** — **Text-based.** Verified with PyMuPDF: page 1 of
`04_nghi_phep_va_lam_viec_tu_xa.pdf` yields 2020 characters with diacritics intact. No OCR is
needed and OCR stays out of scope. No DOCX files are present in the corpus, but `load_docx` is
still built in Phase 2 as CLAUDE.md puts DOCX in scope.

**5. Who writes the golden set?** — **A human other than the agent.** The owner has not yet been
named. The agent builds only the Phase 3 tooling (`find_chunks.py`, `validate.py`, the dataset
README) and stops at the gate.

Consequence accepted: Phase 3 is a hard block. The agent will not generate the questions itself —
a golden set written by the same model being evaluated measures self-consistency, not correctness,
and would make every number from Phase 4 onward meaningless. **The owner must be named before
Phase 2 completes**, or the project stalls at the Phase 3 gate with nothing to work on.

## Consequences

- In scope for v1 (Phases 0–5): text PDF + DOCX, single-turn questions, no auth, no permissions,
  synchronous ingest, answers with citations.
- Out of scope, directories stay empty: async workers, multi-turn memory, function calling,
  conversation endpoints, OCR, Qdrant.
- Reversing decision 1 (data may no longer leave) invalidates the vector column dimension, every
  embedding in the database, and every committed result — it is a full re-ingest plus a re-run of
  all pipelines, not a config change. This is the expensive one.
- Reversing decision 2 (growing the corpus) invalidates `relevant_chunk_ids` in the golden set and
  all committed results.
