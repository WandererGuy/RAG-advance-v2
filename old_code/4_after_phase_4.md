# After Phase 4 — the two closing answers of the session

Transcript of the two final replies from the session that built Phase 4 (commit `1148a3a`).
Kept verbatim as a record of what was reported at hand-off.

---

## 1. Report at the end of the phase (English)

Phase 4 is built, tested and committed. The one thing missing is the number itself.

**What's in `1148a3a`**

- `app/llm/client.py` — LiteLLM chat wrapper: retry with backoff, timeout, `temperature=0`, empty completions raised rather than returned (a blank answer would score as a refusal).
- `prompts/answer_v1.jinja` — Vietnamese, context-only, `[filename, p.N]` citations, exact refusal sentence. `StrictUndefined`, so a missing variable fails instead of silently rendering blank.
- `retrievers/{base,dense}.py` — dense top-5, nothing else. `RetrievedChunk` is deliberately not the repository's `ChunkHit`, so a Phase 6 fusion score can't be misread as cosine similarity.
- `pipelines/{base,registry,naive_v1}.py` — the registry rejects a rebound name and a `name` attribute that disagrees with its key.
- `eval/metrics/{retrieval,generation}.py`, `judge_prompts/`, `runner.py`, `report.py` — every results file carries `config`, `dataset_version`, `golden_set_author`, `judge_model`, `git_sha`; `leaderboard.md` shows the author as a column.
- Two ADRs, 79 new unit tests (131 total), `make eval` / `make report`, `docs/progress/phase-4.md`.

**Two things you should know**

The provider retired `gemini-2.5-flash` for this key mid-phase — every answer call 404'd. You picked `gemini-3.6-flash`; it's pinned, and ADR-0007 bans moving aliases in `LLM_MODEL` since they'd silently change the model behind a frozen pipeline. Embeddings were unaffected, so the corpus and all 34 chunk ids are untouched, and no results file existed yet to invalidate.

The baseline run is the remaining work. It got to question 10 of 29 (all `answered`, `recall=1.00`) before the 20/day free-tier quota ran out. A 3-question smoke run proved the whole path — recall@5 1.0, faithfulness 5.0, relevance 4.67, citation_rate 1.0, ~5.6s p50 — but I kept it out of `results/`, since a sample committed there gets read as the baseline. When you've cleared the quota, `make eval P=naive-v1` finishes the phase.

Worth flagging: `refusal_accuracy` has never actually fired — `q025`–`q029` are all in the untested tail, and it's the metric ADR-0004 already calls least trustworthy. Also unrelated to this work, your rename of the initial migration file is still sitting staged; I left it alone.

---

## 2. "Vậy bạn đã làm những gì" (tiếng Việt)

Tóm tắt những gì tôi đã làm trong phiên này — toàn bộ **Phase 4 (`naive-v1` baseline)**, commit `1148a3a`.

### 1. Đọc context trước khi code

`CLAUDE.md`, `docs/progress.md`, 4 file phase, `PLAN.md`, và đọc code Phase 1–3 (config, embedder, vector_store, document_repo, validate.py) để viết đúng style và đúng layering đã có.

### 2. Code mới (backend)

| File | Nội dung |
|---|---|
| `app/llm/client.py` | Wrapper LiteLLM cho chat: retry backoff, timeout, `temperature=0`, completion rỗng thì raise (nếu trả về chuỗi rỗng sẽ bị chấm nhầm thành "từ chối trả lời") |
| `app/llm/prompts/` | Loader Jinja2 với `StrictUndefined` + `answer_v1.jinja` — tiếng Việt, chỉ dùng context, bắt buộc trích dẫn `[tên tệp, p.N]`, câu từ chối cố định |
| `retrievers/base.py`, `dense.py` | Protocol + dense top-5. `RetrievedChunk` tách khỏi `ChunkHit` để điểm RRF của Phase 6 không bị đọc nhầm thành cosine |
| `pipelines/` | `RAGAnswer`, `parse_citations`, `is_refusal`, registry (`@register`), `naive_v1.py` |
| `eval/metrics/` | recall@k · MRR · nDCG@k (số học thuần); LLM-as-judge + refusal + kiểm tra trích dẫn |
| `eval/runner.py`, `report.py` | Chạy pipeline → `results/<name>.json` (kèm `config`, `dataset_version`, `golden_set_author`, `judge_model`, `git_sha`) → `leaderboard.md` |

Thêm `make eval` / `make report` vào `Makefile`, thêm `jinja2` vào dependencies.

### 3. Test và kiểm chứng thật

79 test unit mới → **131 passed**; `make lint` sạch trên 47 file; `make validate` PASS. Chạy thật 3 câu hỏi trên Postgres thật + Gemini thật: recall@5 = 1.0, faithfulness 5.0, citation_rate 1.0.

### 4. Hai quyết định phải hỏi bạn

- **Model chết giữa chừng:** `gemini-2.5-flash` trả 404 ("no longer available to new users"). Bạn chọn `gemini-3.6-flash` → ADR-0007, kèm luật cấm dùng alias kiểu `gemini-flash-latest`. Embedding không bị ảnh hưởng nên corpus và 34 chunk id còn nguyên.
- **Quota:** free tier chỉ 20 request/ngày/model, một lần chạy cần ~82. Bạn bảo để sau, nên tôi dừng lại.

Ngoài ra viết ADR-0006: judge chính là model trả lời (tự chấm điểm mình, có ghi rõ trong mọi results file), còn `refusal_accuracy` thì so khớp chuỗi chứ không nhờ model chấm.

### 5. Còn thiếu

**`results/naive-v1.json` chưa tồn tại** → theo PLAN.md thì Phase 4 **chưa xong**. Lần chạy đầy đủ mới tới câu 10/29 thì hết quota; tôi không commit bản chạy dở vào `results/` vì nó sẽ bị đọc nhầm là baseline. `docs/progress/phase-4.md` và `docs/progress.md` ghi rõ trạng thái 🟨 này.

Khi bạn mở quota xong: `make eval P=naive-v1` là xong phase.
