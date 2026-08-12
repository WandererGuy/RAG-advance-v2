---
description: Close out a phase — run the checks, write docs/progress/phase-N.md, update the index, commit
argument-hint: <phase number>
allowed-tools: Bash(make:*), Bash(git:*), Read, Write, Edit, Glob, Grep
---

Close out **Phase $1** of rag-chatbot. This is the procedure behind CLAUDE.md rules 8, 9, 11 and 12
— follow it in order and do not skip a step because it "obviously passes".

## 1. Prove the Definition of Done

Read Phase $1's `✅ Done when:` line in `PLAN.md` first — that is the bar, not this checklist.
Then run, from the repo root, capturing the real output of each:

```
make lint
make test
make validate
```

Anything a phase-specific DoD needs on top of those (a committed `results/*.json`, a migration
applied, an endpoint answering) must be run and captured too.

**If any of it fails, or a DoD artefact does not exist: stop here.** Report what failed and do not
write the progress entry or commit. A phase entry that claims a phase is done when it is not is
worse than no entry — the next session starts from these files and remembers nothing else. Phase 4
is the precedent: code complete, no number committed, and the entry says exactly that.

## 2. Write `docs/progress/phase-$1.md`

Match the shape of the existing entries — read `docs/progress/phase-2.md` and `phase-4.md` before
writing, and follow their headings rather than inventing new ones. Five things, every time:

1. **Built** — the files created, with links, and the date.
2. **Evidence** — the actual command output from step 1, as a table or fenced block. Real numbers
   pasted from the terminal. Never a summary of output you did not run.
3. **Deviations from PLAN.md** — what differs and why. If a deviation involved a trade-off, it
   needs its own ADR (rule 7); link it here, do not argue it in this file.
4. **Open items** — anything unfinished, and separately anything **blocked on a human**, named as
   such. Human gates that were agent-executed must say so in those words.
5. **What you can do after this phase** — rule 12, in its five parts, in this order:
   - **Available** — what runs now, and what explicitly does *not* yet.
   - **Commands that work at this point** — copy-pasteable, only commands that work *after this
     phase*. No command from a later phase. Include the useful SQL / `curl` calls.
   - **Technical, possible now** and **Non-technical, possible now** — including the review,
     decision and naming steps only a human can take.
   - **Notice** — the traps: destructive flags, things that look fine but fail later, silent
     failure modes.
   - **For the next phase ($1+1)** — what the next session must know before writing any code.

## 3. Update the index

Add or update Phase $1's row in the `docs/progress.md` table, and refresh the prose below it:
"Where the project stands", anything under "Still blocked on a human", and any gate the agent took
rather than a human. The index is what a fresh session reads first — it must not describe a state
the repo has moved past.

Also check whether this phase invalidated anything in `CLAUDE.md`, `PLAN.md` or
`docs/architecture.md`. If a rule there is now wrong, fix it in place; history belongs in the ADR,
not in a strike-through.

## 4. Commit

One commit, containing the code *and* the progress entry *and* the index update:

```
feat(phase-$1): <short description>
```

Show `git status` and the diffstat before committing. Do not push.

## 5. Report

Tell me: the DoD result, anything blocked on a human, and the one thing Phase $1+1 needs. Then
stop — rule 1, no starting the next phase.
