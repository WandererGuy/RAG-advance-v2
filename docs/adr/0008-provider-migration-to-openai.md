# ADR-0008 — The whole stack moves to OpenAI: `gpt-5.6-luna` + `text-embedding-3-large` @ 768

- **Date:** 2026-08-12
- **Status:** accepted — supersedes [ADR-0007](0007-llm-model-migration-to-gemini-3-6-flash.md)
  and the LLM/embedding rows of [ADR-0002](0002-tech-stack-resolution.md)

## Context

The project owner switched providers: the Gemini key is retired and an OpenAI key replaces it.
This is not a model retirement like ADR-0007 — that was generation-side only and left the corpus
untouched. **This one moves the embedding model too**, which is the expensive half.

Constraints given: keep the vector dimension at **768**, use "luna" for answering and the large
embedding model. Verified against the live key before anything was changed:

| | Result |
|---|---|
| `GET /v1/models` | 200, 126 models. `gpt-5.6-luna` present; no other "luna" |
| `gpt-5.6-luna`, Vietnamese prompt | 200, correct answer, `model` echoed as `gpt-5.6-luna` |
| `text-embedding-3-large`, `dimensions: 768` | 200, vector length **768** |

Two facts made this cheap. `text-embedding-3-large` supports **native dimension truncation** —
768 is a supported output size, not a client-side slice — so `EMBEDDING_DIMENSIONS=768`,
`chunks.embedding vector(768)`, the HNSW index and the migration are all unchanged. **No schema
migration was needed.** And `gpt-5.6-luna` is already a leaf name that echoes itself back rather
than resolving to a dated snapshot, so ADR-0007's no-aliases rule is satisfied by the name as
given; there is no `gpt-5.6-luna-2026-xx-xx` to pin to instead.

### The part that is not free: every stored vector was wrong

A vector is only comparable to vectors from the same model. The moment `EMBEDDING_MODEL_NAME`
changed, all 34 stored embeddings belonged to a space the query embedder no longer speaks, and
cosine similarity across the two is noise — noise that reads as a merely mediocre retriever
rather than as an error. The corpus had to be re-embedded.

The obvious route, `make ingest FORCE=1`, would have been a disaster: it deletes and reinserts
chunk rows, assigning **new serial ids**, and `relevant_chunk_ids` in `golden_qa.v1.jsonl` are
bare integers. Every one of the 29 questions would then have pointed at the wrong text. That is
exactly the failure [ADR-0005](0005-frozen-corpus-for-the-golden-set.md) froze the corpus to
catch, and the golden set would have needed rebuilding by hand.

### `gpt-5.6-luna` rejects `temperature=0`

Discovered on the first smoke run, as a 400 on every question after 5 retries:

```
litellm.BadRequestError: OpenAIException - Unsupported value: 'temperature' does not
support 0 with this model. Only the default (1) value is supported.
```

`app/llm/client.py` has sent `temperature=0` on every call since Phase 4, deliberately: it is
the one knob that keeps two runs of a frozen pipeline close to each other. This model removes it.

## Decision

1. **Provider is OpenAI for both roles.** `DEFAULT_LLM_MODEL_NAME=gpt-5.6-luna`,
   `EMBEDDING_MODEL_NAME=text-embedding-3-large`, `EMBEDDING_DIMENSIONS=768` unchanged. Both
   `.env` and `.env.example` moved together, along with the `Settings` defaults, so a fresh
   clone does not come up configured for a provider the project no longer uses.

2. **Re-embed in place; never re-ingest.** New: `scripts/reembed_corpus.py` / `make reembed`,
   and `DocumentRepository.update_chunk_embeddings()`, which UPDATEs the embedding column of
   existing rows. Chunk ids, `content`, `page_no` and `chunk_index` are untouched, so
   `corpus.lock.json` — which hashes `file_hash + chunk_index + content` and lists chunk ids —
   stays valid by construction. **Re-embedding is not a corpus change.** `make validate` passed
   afterwards with the lock and the golden set unmodified, byte for byte.

   The script embeds everything before writing anything: a provider failure half-way through
   leaves the database wholly on the old model rather than in a mix of two vector spaces, which
   is the one state that is both broken and invisible.

3. **When a model refuses an explicit temperature, omit the parameter — and say so in the
   results file.** `LLM_SUPPORTS_TEMPERATURE=false` makes the client drop `temperature` from the
   request, and `PipelineConfig.temperature` is then `None`, which lands in every
   `results/*.json`. Never write `0.0` there to mean "we asked for 0": the run used the
   provider's default of 1.

## Consequences

- **Every number this project could have quoted is now unquotable — and there were none.** The
  only reason this migration is cheap is that `results/` still holds nothing but `.gitkeep`. Had
  the Phase 4 baseline landed yesterday, it would have been invalidated in full: different
  embedding space, different answering model, different temperature. The blocked quota that
  stalled Phase 4 turns out to have saved a re-run.
- **The baseline is less reproducible than Phase 4 intended.** Answers now come back at the
  provider's default temperature, so two runs of `naive-v1` will differ more than they would
  have under Gemini. `temperature: null` in the results file is the marker; it is not a bug to
  be fixed but a property of the chosen model, and it slightly widens the noise floor under any
  Phase 6 comparison. A pipeline that beats the baseline by a hair has not clearly beaten it.
- **Self-grading continues, and gets tighter.** [ADR-0006](0006-how-generation-is-scored.md)
  already recorded that the judge is the answering model. That is still true, now with
  `gpt-5.6-luna` grading itself — and unlike before, the retrieval side shares the vendor too.
  The triggers in ADR-0006 for adding an independent judge are unchanged and slightly more
  pressing; an OpenAI key with more than one model family available makes `--judge-model` a
  cheap experiment.
- **The quota story changes shape.** The Gemini free tier's 20 requests/day/model is gone; an
  OpenAI key is metered instead. A full run is ~29 answer calls plus ~53 judge calls, and the
  judge costs more than the pipeline it grades. That is a billing question now, not a blocker.
- **ADR-0007's rule survives its own provider.** No alias in `LLM_MODEL` — `gpt-5.1-chat-latest`
  and friends exist on this key and are exactly what must not be used. Expect this model to be
  retired in turn; the 404 will be information, not a bug.
- **`count_tokens` became accurate by accident.** It has always used tiktoken `cl100k_base`,
  which was a stand-in under Gemini and is the real tokenizer for OpenAI embedding models. It is
  still not a billing figure and nothing branches on it.
- **Revisit if:** the owner moves providers again (re-embed, don't re-ingest — that is the whole
  lesson here); a `gpt-5.6-luna` snapshot with a date appears (pin to it); or the model starts
  honouring `temperature=0` (set `LLM_SUPPORTS_TEMPERATURE=true` and note it, because results
  from before and after are not strictly comparable).
