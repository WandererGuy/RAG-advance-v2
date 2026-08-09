## Phase 0 — Lock the scope + skeleton ✅

**Completed** 2026-08-09 · commits `2a86836`, `2a9b4d9`

Human gate answered and recorded in [ADR-0001](../adr/0001-scope-va-data-boundary.md): Gemini API
approved for document data, 8 Vietnamese HR PDFs accepted as the v1 corpus, golden set owned by a
human other than the agent.

Built: `.gitignore`, `README.md`, `docs/architecture.md` with the phase → directory map,
`docs/adr/0000-template.md`, ADR-0001, and [ADR-0002](../adr/0002-tech-stack-resolution.md).

**Definition of Done** — all 5 questions answered in ADR-0001; `data/raw/HR_pdfs/` holds 8 real
documents, verified text-based with PyMuPDF (2020 characters off page 1, diacritics intact).

### Deviations

- **Removed 73 zero-byte `.py` files.** The repository arrived with the entire tree scaffolded
  ahead of time, including Phase 6+ files. This contradicted the scaffolding rule in both CLAUDE.md
  and PLAN.md. Directories now hold a `.gitkeep` until their phase arrives.
- **Wrote ADR-0002, which PLAN.md did not ask for.** Three sources specified three different
  stacks and the embedding dimension is baked into the first migration, so the conflict had to be
  resolved before Phase 1 rather than discovered during it.
- **CLAUDE.md §3 is now partly superseded** by ADR-0002 (embedding dimension 768 not 1536, Gemini
  not OpenAI/Anthropic, Python 3.12 not 3.11). CLAUDE.md itself was left unedited — it is the
  user's context file. Read ADR-0002 alongside it.

### Open

- **The golden-set owner has not been named.** Phase 3 is a hard block; it must be resolved before
  Phase 2 finishes or the project stalls with nothing to work on.
- The 8-document corpus makes retrieval metrics optimistic — fewer distractor chunks than
  production. Relative comparison between pipelines stays valid, absolute numbers do not.
