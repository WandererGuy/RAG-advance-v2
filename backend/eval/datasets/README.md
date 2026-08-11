# Golden sets

The questions every pipeline is scored against. Nothing in `results/` means anything without the
file that produced it, so read this before changing anything here.

> **`golden_qa.v1.jsonl` is agent-authored.** Read
> [ADR-0004](../../../docs/adr/0004-agent-authored-golden-set.md) before quoting any number
> measured against it. Short version: retrieval metrics are inflated, `refusal_accuracy` is the
> least trustworthy of them, and the numbers are fit for **comparing pipelines to each other** and
> nothing else.

## Format

One JSON object per line. Every field is required.

```json
{"id": "q001",
 "q": "Mỗi tháng được hỗ trợ bao nhiêu tiền bữa trưa?",
 "ground_truth": "1.100.000 đồng/tháng, áp dụng cho toàn bộ nhân viên và không tính thuế TNCN.",
 "relevant_chunk_ids": [5],
 "type": "factual",
 "author": "agent"}
```

| Field | Rule |
|---|---|
| `id` | unique across the file |
| `q` | the question, in Vietnamese, as a user would actually type it |
| `ground_truth` | the correct answer, for the Phase 4 judge. For `unanswerable`, say *why* it is absent and what the system must not substitute instead |
| `relevant_chunk_ids` | chunk ids from the **frozen** corpus — see below. Empty for `unanswerable` |
| `type` | `factual` (one chunk suffices) · `multi_hop` (needs ≥2) · `unanswerable` (not in the corpus) |
| `author` | `agent`, or the name of the person who wrote the line. **Never omit it** — `validate.py` rejects the line, and every `results/*.json` carries these values forward as `golden_set_author` (CLAUDE.md rule 8) |

Distribution in `v1`: 16 `factual`, 8 `multi_hop`, 5 `unanswerable`.

## Versioning

**`v1` is frozen the moment it is committed.** New or corrected questions go into
`golden_qa.v2.jsonl` — never into `v1`. A score from `v1` and a score from `v2` are different
measurements and must not share a leaderboard row, which is why `dataset_version` and
`golden_set_author` travel with every result. ADR-0004 lists the triggers for writing `v2`; the
cheapest one is real user questions arriving in the Phase 5 `queries` table.

## The frozen corpus

`corpus.lock.json` pins each document's `file_hash` to the chunk ids it produced, plus a digest
of all chunk text. It exists because `relevant_chunk_ids` are bare integers: a
`make ingest FORCE=1` deletes and reinserts chunks, **assigns new ids**, and every id here then
points at the wrong text — recall just drops and looks like a bad pipeline. See
[ADR-0005](../../../docs/adr/0005-frozen-corpus-for-the-golden-set.md).

```bash
make validate                                      # dataset + corpus lock
cd backend && uv run python -m eval.datasets.validate --no-db       # structure only, no database
cd backend && uv run python -m eval.datasets.validate --write-lock  # re-freeze after a corpus change
```

`--write-lock` is not a fix for a failing check. If the lock reports drift, either restore the
corpus or accept that the affected `relevant_chunk_ids` must be looked up again.

## Writing a question

```bash
make find Q="phụ cấp"                                   # chunk_id + page + snippet
cd backend && uv run python -m scripts.find_chunks --q "nghỉ phép" --q "31/3" --full
```

Constraints from ADR-0004, binding on `v1` and worth keeping afterwards:

- **Draft from the rendered PDF page, not from chunk text.** Reusing the chunker's vocabulary
  turns a retrieval test into a string-matching test.
- **Paraphrase away from the source sentence.** If the question repeats the document's own noun
  phrase, it measures nothing.
- **`unanswerable` must be an in-domain near-miss** — a plausible policy this corpus does not
  contain. "Does the office allow pets" measures nothing; "how is the year-end bonus prorated
  during maternity leave" measures whether the system will invent a rule.
- **Look chunk ids up afterwards** with `find_chunks.py`, never from memory.
- Do not write a question that depends on the truncated table cell on p.2 of
  `05_bao_mat_thong_tin_va_thiet_bi.pdf` — the words are missing from the source PDF itself
  (`docs/progress/phase-2.md`).
