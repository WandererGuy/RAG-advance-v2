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

### What you can do after this phase

**Available:** documents and decisions only. No code runs yet — there is no `Makefile`, no
`docker-compose.yml`, no dependencies installed. `backend/` is directories and `.gitkeep` files.
`data/raw/HR_pdfs/` holds the 8 PDFs. (They were gitignored and on-disk-only at the time of this
phase; on 2026-08-12 they were confirmed synthetic and committed to the repo — see
[ADR-0001](../adr/0001-scope-va-data-boundary.md) and `docs/progress.md`.)

**Commands that work at this point:**

```bash
git log --oneline                      # 2a86836, 2a9b4d9
ls data/raw/HR_pdfs                    # the 8-document corpus
```

Nothing else — `make`, `alembic`, `pytest`, `uvicorn` all arrive in Phase 1.

**Technical, possible now:** read [`docs/architecture.md`](../architecture.md) for the phase →
directory map and confirm which directory a file belongs in before writing it; read
[ADR-0002](../adr/0002-tech-stack-resolution.md) to know what the stack actually is (it, not
CLAUDE.md §3, is authoritative on the embedding dimension, provider and Python version); check a
PDF's text layer by hand with PyMuPDF before trusting that it is text-based.

**Non-technical, possible now:** review and object to ADR-0001 and ADR-0002 while reversing them is
still cheap — after Phase 1 the 768 dimension is baked into a migration and after Phase 2 into
every stored vector; **name the golden-set author** (this is the one thing that unblocks the
critical path); decide whether the 8-document corpus is the final v1 corpus or more documents are
coming, because adding documents later renumbers nothing but does change every retrieval number
already committed.

**Notice:** CLAUDE.md §3 is partly wrong on purpose and was left unedited — always read it next to
ADR-0002. The empty directories are deliberate; do not fill them ahead of their phase.

**For the next phase (1):** the vector dimension 768 must be written identically in `.env`,
`app/models/chunk.py` and the initial migration — a mismatch is not caught until the first insert.
The corpus is Vietnamese, so any collation or encoding shortcut in the schema will surface as lost
diacritics later.

### Open

- **The golden-set owner has not been named.** Phase 3 is a hard block; it must be resolved before
  Phase 2 finishes or the project stalls with nothing to work on.
- The 8-document corpus makes retrieval metrics optimistic — fewer distractor chunks than
  production. Relative comparison between pipelines stays valid, absolute numbers do not.
