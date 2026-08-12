# PLAN.md — Lộ trình thi công rag-chatbot

Đọc `CLAUDE.md` trước. Làm tuần tự từ Phase 0.
Sau mỗi phase: chạy Definition of Done → báo cáo → chờ xác nhận rồi mới đi tiếp.

- 🛑 **HUMAN GATE** — dừng hẳn, cần con người. Không tự chế dữ liệu để đi tiếp.
- ✅ **Done** — verify được bằng lệnh, không phải bằng cảm giác.

> **Quy tắc scaffold:** mỗi phase chỉ tạo đúng những file được liệt kê trong phase đó.
> Thư mục của phase sau: tạo thư mục + `.gitkeep`, **không** tạo file `.py` rỗng.

---

Gợi ý tech stack: uv, Python 3.12 + FastAPI, asyncpg để truy cập PostgreSQL bất đồng bộ, LiteLLM, Celery cho job nền, Redis làm broker/result backend, Chonkie để chunk tài liệu, LangChain, Langgraph , cùng một số LLM và embedding ở .env 

## Phase 0 — Chốt scope + skeleton (nửa ngày)

🛑 **HUMAN GATE.** Hỏi 5 câu sau, ghi câu trả lời vào `docs/adr/0001-scope-va-data-boundary.md`:

1. **Dữ liệu có được gửi ra API bên ngoài (OpenAI / Anthropic) không?**
   → Nếu KHÔNG: dừng toàn bộ, viết ADR mới, đổi stack sang self-host.
   Đây là câu hỏi giết dự án nếu hỏi muộn.
2. Đã có 20–50 tài liệu thật để đặt vào `data/raw/` chưa?
3. Ngôn ngữ tài liệu: thuần Việt / thuần Anh / lẫn lộn?
4. PDF text hay PDF scan? (scan = ngoài scope, cần OCR)
5. Ai sẽ viết golden set ở Phase 3?

**Việc của agent:**
- [ ] Tạo cây thư mục đầy đủ như thiết kế, **chỉ thư mục + `.gitkeep`**, chưa có file `.py`.
- [ ] `.gitignore`: `.env`, `data/raw/*` (trừ `data/samples/`), `__pycache__`, `.venv`, `*.db`
- [ ] `README.md` một trang: mục tiêu, trong/ngoài scope, cách chạy.
- [ ] `docs/architecture.md`: bảng **phase → thư mục nào được mở khoá** (chép từ bảng dưới).
- [ ] `docs/adr/0000-template.md` + `0001-scope-va-data-boundary.md` (để trống chờ trả lời).

**Bản đồ phase → thư mục** (đưa vào `docs/architecture.md`):

| Phase | Mở khoá |
|---|---|
| 1 | `core/`, `db/`, `models/`, `main.py`, `alembic/`, `docker-compose.yml`, `Makefile` |
| 2 | `llm/rag/{chunking,embedder,vector_store}.py`, `repositories/document_repo.py`, `services/ingest_service.py`, `scripts/ingest_corpus.py` |
| 3 | `eval/datasets/` |
| 4 | `llm/client.py`, `llm/prompts/`, `rag/retrievers/{base,dense}.py`, `rag/pipelines/{base,registry,naive_v1}.py`, `eval/{metrics,judge_prompts,runner,report}`, `results/` |
| 5 | `api/v1/routes/{chat,documents}.py`, `api/deps.py`, `schemas/`, `services/chat_service.py`, `frontend/` |
| 6 | `retrievers/{bm25,hybrid,reranker}.py`, `pipelines/hybrid_v2.py`, `.github/workflows/` |
| sau | `workers/`, `llm/memory.py`, `llm/tools/`, `routes/conversations.py`, `repositories/{conversation,message}_repo.py` |

✅ **Done khi:** 5 câu hỏi đã có câu trả lời trong ADR-0001, và `data/raw/` có tài liệu thật.

---

## Phase 1 — Hạ tầng + schema (1 ngày)

- [ ] `docker-compose.yml`: service `postgres` dùng `pgvector/pgvector:pg16`, volume persist,
      env từ `.env`. Chưa Redis, chưa worker.
- [ ] `backend/pyproject.toml` — chỉ dependency thực sự dùng ở Phase 1–2.
- [ ] `Makefile` ở root: `up`, `down`, `migrate`, `test`, `lint`, `api`.
- [ ] `.env.example`: `DATABASE_URL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
      `EMBEDDING_MODEL`, `LLM_MODEL`, `LOG_LEVEL`.
- [ ] `app/core/config.py` — `Settings` (pydantic-settings) **và** `PipelineConfig`
      (dataclass: `chunk_size`, `chunk_overlap`, `top_k`, `retriever`, `embedding_model`,
      `llm_model`, `prompt_version`). `PipelineConfig` phải serialize được ra dict —
      nó sẽ được nhúng vào mọi file `results/*.json`.
- [ ] `app/core/logging.py` — structlog, JSON output.
- [ ] `app/core/exceptions.py` — `DocumentNotFound`, `UnsupportedFileType`,
      `IngestFailed`, `PipelineNotFound`.
- [ ] `app/db/base.py` (DeclarativeBase + import models), `app/db/session.py` (engine, sessionmaker).
- [ ] `app/models/` — đúng 3 bảng ở phase này:

```
documents   id, filename, source_path, file_hash UNIQUE, mime_type,
            page_count, status, error_message, created_at
            status ∈ {pending, processing, done, failed}

chunks      id, document_id FK CASCADE, content TEXT, page_no INT,
            chunk_index INT, token_count INT,
            embedding vector(1536), created_at
            + HNSW index (vector_cosine_ops)

queries     id, question TEXT, answer TEXT, pipeline_name TEXT,
            retrieved_chunk_ids INT[], latency_ms INT, created_at
```

> `queries` hay bị bỏ qua. Đừng bỏ. Đó là nguồn duy nhất để sau này biết người dùng
> **thật sự** hỏi gì, và để mở rộng golden set từ traffic thật thay vì tưởng tượng.
> `pipeline_name` để về sau truy được câu trả lời tệ đến từ pipeline nào.

- [ ] `alembic/` init + migration đầu, có `CREATE EXTENSION IF NOT EXISTS vector`.
- [ ] `app/main.py` + `app/api/v1/router.py` với đúng 1 route `GET /health` (check DB).

✅ **Done khi:** `make up && make migrate` sạch, `curl localhost:8000/api/v1/health` → 200,
`\dt` thấy đủ 3 bảng, `\di` thấy index HNSW.

---

## Phase 2 — Ingest đồng bộ (2–3 ngày)

Chưa làm endpoint. Chỉ CLI. Chưa đụng `workers/`.

- [ ] `app/llm/rag/chunking.py` — `chunk(pages, cfg) -> list[Chunk]`.
      Cắt theo ký tự `size=800`, `overlap=100`, ưu tiên ranh giới câu/đoạn gần nhất.
      Mỗi chunk giữ `page_no` gốc. **Không** semantic chunking ở phase này.
- [ ] `app/llm/rag/embedder.py` — protocol `Embedder` + impl OpenAI.
      Batch 32, retry + exponential backoff, đếm token.
- [ ] `app/llm/rag/vector_store.py` — protocol `VectorStore`
      (`add_chunks`, `search`, `delete_by_document`) + impl **pgvector**. Chỉ pgvector.
- [ ] `app/repositories/document_repo.py` — CRUD documents + chunks, tất cả SQL ở đây.
- [ ] `app/services/ingest_service.py` — `ingest_file(path)`:
      hash → đã tồn tại thì skip (trừ `force`) → load → chunk → embed →
      insert trong 1 transaction → `status=done`.
      Lỗi giữa chừng: rollback, `status=failed` + `error_message`, log, đi tiếp file kế.
      **Không import fastapi.**
- [ ] Loader đặt trong `app/services/loaders.py` hoặc `llm/rag/loaders.py`:
      `load_pdf` (PyMuPDF, số trang thật), `load_docx` (python-docx — không có trang thật,
      ghi rõ giới hạn trong docstring).
- [ ] `backend/scripts/ingest_corpus.py` — `--path`, `--force`, progress bar, tổng kết.
- [ ] `tests/unit/test_chunking.py` — overlap đúng, giữ `page_no`, text ngắn hơn size,
      text có ký tự tiếng Việt.
- [ ] `tests/integration/test_ingest.py` — ingest file trong `data/samples/` 2 lần,
      assert số chunk không đổi (idempotent).

✅ **Done khi:**
```sql
SELECT status, count(*) FROM documents GROUP BY status;
SELECT count(*) FROM chunks;
SELECT content, page_no FROM chunks ORDER BY random() LIMIT 5;
```
Và **con người đọc 5 chunk random đó**, xác nhận: không mất dấu tiếng Việt, không dính
header/footer lặp lại, không cắt giữa từ, `page_no` đúng. Kiểm tra bằng mắt, bắt buộc.

---

## Phase 3 — Golden set (nửa ngày) ⚠️

🛑 **HUMAN GATE. Dừng trước khi viết bất kỳ dòng retrieval nào.**

Phase dễ bị bỏ qua nhất. Cảm giác lúc này sẽ là *"làm retrieval trước cho nhanh, golden set
để sau"*. Đừng. Không có baseline thì mọi thứ ở Phase 6 chỉ là cảm tính.

**Việc của con người** — tự tay viết 20–30 câu vào `eval/datasets/golden_qa.v1.jsonl`:

```json
{"id": "q001",
 "q": "Chính sách nghỉ phép năm là bao nhiêu ngày?",
 "ground_truth": "12 ngày/năm, cộng thêm 1 ngày mỗi 5 năm làm việc",
 "relevant_chunk_ids": [142, 143],
 "type": "factual"}
```

Phân bổ: `factual` (1 chunk đủ trả lời), `multi_hop` (cần ≥2 chunk),
`unanswerable` (corpus không có — ít nhất 3–5 câu, để đo hệ thống có dám nói "không biết").
Với tài liệu doanh nghiệp, bịa ra câu trả lời nguy hiểm hơn nhiều so với từ chối.

**Việc của agent:**
- [ ] `eval/datasets/README.md` — format, quy tắc version (`v1` đóng băng sau khi commit;
      thêm câu mới → `v2`, không sửa `v1`).
- [ ] `backend/scripts/find_chunks.py --q "từ khoá"` — full-text search trong `chunks`,
      in ra `chunk_id + page_no + snippet` để người viết tra `chunk_id` nhanh.
- [ ] `eval/datasets/validate.py` — check JSON hợp lệ, `id` không trùng,
      `relevant_chunk_ids` tồn tại thật trong DB, câu `unanswerable` phải có mảng rỗng.
- [ ] **KHÔNG tự sinh câu hỏi.** Nếu được yêu cầu, từ chối và giải thích lý do.

✅ **Done khi:** `golden_qa.v1.jsonl` ≥20 dòng do người viết, `python -m eval.datasets.validate` pass.

---

## Phase 4 — Baseline `naive-v1` (1–2 ngày)

Cố tình đơn giản. Đây là mốc so sánh, không phải sản phẩm.

- [ ] `app/llm/client.py` — wrapper provider, retry, timeout. Chưa streaming.
- [ ] `app/llm/prompts/answer_v1.jinja` — đưa top-k chunk vào context; yêu cầu trả lời
      **chỉ dựa trên context**; bắt buộc trích nguồn `[filename, tr.N]`;
      **bắt buộc nói "không tìm thấy thông tin trong tài liệu" nếu context không đủ.**
- [ ] `app/llm/rag/retrievers/base.py` — protocol `Retriever.retrieve(q, k) -> list[RetrievedChunk]`.
- [ ] `app/llm/rag/retrievers/dense.py` — embed query → cosine top-k qua `VectorStore`.
      Không rerank, không filter, không hybrid.
- [ ] `app/llm/rag/pipelines/base.py` — `RAGPipeline` protocol + `RAGAnswer` dataclass
      (`answer`, `citations`, `chunk_ids`, `latency_ms`, `pipeline_name`, `config`).
- [ ] `app/llm/rag/pipelines/registry.py` — `@register(name)` + `get_pipeline(name)`,
      raise `PipelineNotFound` nếu không có.
- [ ] `app/llm/rag/pipelines/naive_v1.py` — `@register("naive-v1")`, dense top-5 + answer_v1.
- [ ] `eval/metrics/retrieval.py` — `recall@k`, `MRR`, `nDCG@k`.
- [ ] `eval/metrics/generation.py` — LLM-as-judge:
      - `faithfulness` 1–5: có bịa ngoài context không
      - `answer_relevance` 1–5
      - `refusal_accuracy`: câu `unanswerable` có được từ chối đúng không
- [ ] `eval/judge_prompts/faithfulness_v1.jinja`, `relevance_v1.jinja`.
- [ ] `eval/runner.py` — `python -m eval.runner --pipeline naive-v1 [--dataset v1]`.
      Ghi `results/naive-v1.json` gồm: `pipeline_name`, **`config` đầy đủ**,
      `dataset_version`, `git_sha`, `timestamp`, metrics tổng, chi tiết từng câu.
- [ ] `eval/report.py` — đọc mọi `results/*.json` → `results/leaderboard.md` (bảng so sánh).

✅ **Done khi:** `results/naive-v1.json` tồn tại và **đã commit**.
Kể cả khi điểm tệ — nhất là khi điểm tệ. Đó là baseline.
**Không được sửa retrieval để làm đẹp số trước khi commit file này.**
Sau khi commit, `naive_v1.py` đóng băng.

---

## Phase 5 — API + frontend mỏng (1–2 ngày)

- [ ] `app/schemas/` — `ChatRequest/ChatResponse`, `DocumentOut`, `Citation`
      (`filename`, `page_no`, `snippet`, `chunk_id`). Không trả ORM object.
- [ ] `app/api/deps.py` — `get_db`, `get_pipeline` (đọc tên pipeline từ Settings).
- [ ] `app/services/chat_service.py` — nhận question → lấy pipeline qua registry →
      `answer()` → ghi bảng `queries` → trả DTO. Không import fastapi.
- [ ] `routes/documents.py` — `POST /documents` (upload + ingest **đồng bộ**),
      `GET /documents` (list + status). Chậm chấp nhận được, không thêm queue.
- [ ] `routes/chat.py` — `POST /chat`. **Single-turn.** Chưa `conversation_id`, chưa stream.
- [ ] `frontend/` — Streamlit một file là đủ: upload, ô hỏi, hiển thị answer +
      citation bấm được để xem snippet. Không cần đẹp.
- [ ] `tests/integration/test_api.py` — smoke 3 endpoint.

✅ **Done khi:** người ngoài team tự bấm được mà không cần hướng dẫn, và bảng `queries`
có dữ liệu thật sau buổi demo.

---

## Phase 6 — Cải tiến, mỗi lần một pipeline

Vòng lặp bắt buộc:

```
tạo pipeline mới (đổi ĐÚNG 1 biến so với pipeline tốt nhất hiện tại)
  → make eval P=<tên mới>
  → make report
  → tốt hơn: commit cả code lẫn results
  → không tốt hơn: giữ nguyên file + kết quả, ghi ADR "vì sao không dùng"
```

Không sửa pipeline cũ. Không xoá kết quả xấu — kết quả âm cũng là thông tin.

Thứ tự thử, theo tỉ lệ lợi ích/công sức:

1. [ ] `retrievers/bm25.py` + `hybrid.py` (RRF fusion, dùng `tsvector` của Postgres)
       → `pipelines/hybrid_v2.py` → `results/hybrid-v2.json`.
       Thường là bước cải thiện lớn nhất với tài liệu doanh nghiệp: nhiều thuật ngữ và
       mã số nội bộ mà embedding bắt kém.
2. [ ] Chunk size / overlap: `chunk-500-v1`, `chunk-1200-v1`. Phải re-ingest toàn bộ →
       ghi rõ trong `results/*.json` là dùng corpus phiên bản nào.
3. [ ] `retrievers/reranker.py` — cross-encoder top-20 → top-5 → `rerank-v1`.
4. [ ] Query rewriting → `qrewrite-v1`.
- [ ] `.github/workflows/ci.yml` — lint + unit test.
- [ ] `.github/workflows/eval.yml` — chạy eval trên PR, comment diff so với baseline.
      Chỉ làm khi đã có ≥3 pipeline, không sớm hơn.

✅ **Done khi:** `results/leaderboard.md` có ≥3 dòng, và giải thích được vì sao
giữ cái này bỏ cái kia — bằng số, không bằng cảm giác.

---

## Sau Phase 6 — chỉ thêm khi có lý do cụ thể

`workers/` + Redis (ingest bất đồng bộ, khi upload > 30s) · `llm/memory.py` + multi-turn ·
`conversations.py` + `conversation_repo`/`message_repo` · streaming · `llm/tools/` ·
phân quyền tài liệu · OCR · Qdrant.

Mỗi thứ = 1 ADR mô tả vấn đề thật đang gặp trước khi viết dòng code đầu tiên.

---

## Ước lượng

~2 tuần đến hết Phase 5 nếu làm tập trung.
Điểm dễ trượt nhất là **Phase 3**. Đừng trượt.