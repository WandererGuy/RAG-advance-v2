# Kiểm kê kỹ thuật — rag-chatbot

Danh sách đầy đủ mọi kỹ thuật: đã làm · đã có kế hoạch · dự định thêm.
Trạng thái tính đến 2026-08-12, commit `14880f9`, Phase 0–3 xong, Phase 4 code xong nhưng
chưa có baseline commit.

Chú thích trạng thái:

| Ký hiệu | Nghĩa |
|---|---|
| ✅ | Đã có code trong repo, nói được, chỉ được ra file |
| 📋 | Đã nằm trong `PLAN.md` Phase 6 — "sẽ làm", có căn cứ |
| 💡 | Ý tưởng thêm, chưa có trong repo lẫn PLAN |
| ⚠️ | Có nhưng KHÔNG phải như tên gọi — đọc kỹ cột ghi chú |

---

## 1. Ingestion & Indexing

| # | Kỹ thuật | TT | Chi tiết / vị trí trong repo |
|---|---|---|---|
| 1.1 | Fixed-size chunking + overlap | ✅ | `chunk_size=800`, `overlap=100`, ưu tiên biên câu/đoạn gần nhất — `app/llm/rag/chunking.py` |
| 1.2 | Page-fidelity extraction (PyMuPDF) | ✅ | Giữ `page_no` thật cho từng chunk — điều kiện bắt buộc để citation `[file, p.N]` có thật |
| 1.3 | DOCX extraction (`python-docx`) | ✅ | `app/llm/rag/loaders.py` |
| 1.4 | Batch embedding + exponential backoff | ✅ | batch 32, retry, token counting — `app/llm/rag/embedder.py` |
| 1.5 | Content-hash idempotency | ✅ | `file_hash` UNIQUE → re-ingest không sinh chunk trùng |
| 1.6 | Transactional ingest + per-file isolation | ✅ | hash → chunk → embed → insert trong 1 transaction; fail giữa chừng thì rollback + `status=failed` + `error_message`, vẫn chạy tiếp file sau |
| 1.7 | pgvector HNSW index | ✅ | `vector_cosine_ops`, `CREATE EXTENSION` trong migration |
| 1.8 | Corpus freezing / lockfile | ✅ | `corpus.lock.json` + `make validate` — chống chunk-id drift phá golden set (ADR-0005) |
| 1.9 | MRL truncation 3072 → 768 dim | ⚠️ | **KHÔNG phải "dùng Matryoshka"** — xem mục 7.1. Đây chỉ là một con số cố định trong config |
| 1.10 | Breadcrumb / structural metadata | 💡 | `Sổ tay NV > Chương 3 > 3.2 Phụ cấp > Bảng 3.1` prepend vào chunk trước khi embed |
| 1.11 | Semantic / late chunking | 💡 | Thay `chunk-500-v1` bằng biến thể có ý nghĩa hơn ablation thuần size |
| 1.12 | Contextual Retrieval (Anthropic) | 💡 | LLM sinh 1–2 câu ngữ cảnh cho mỗi chunk trước khi embed — cùng họ breadcrumb nhưng mạnh hơn |
| 1.13 | Docling — structured document model | 💡 | Bảng thành bảng thật + heading hierarchy thật. Xem mục 6.3 về chi phí |
| 1.14 | OCR cho scanned PDF | 💡 | ADR-0001 đã chốt **out of scope v1** — làm thì cần ADR mới |

---

## 2. Retrieval

| # | Kỹ thuật | TT | Chi tiết |
|---|---|---|---|
| 2.1 | Dense vector search, cosine top-k | ✅ | `top_k=5` — `app/llm/rag/retrievers/dense.py` |
| 2.2 | Retriever là Protocol, DI qua constructor | ✅ | `retrievers/base.py` — pipeline nhận retriever, không tự khởi tạo |
| 2.3 | VectorStore abstraction | ✅ | `add_chunks` / `search` / `delete_by_document` (ADR-0003) |
| 2.4 | Tách `RetrievedChunk` khỏi `ChunkHit` | ✅ | `ChunkHit.score` = cosine cụ thể; retriever score = "bất kỳ thứ gì nó rank theo". RRF score Phase 6 không được đọc nhầm thành cosine |
| 2.5 | BM25 sparse retrieval | 📋 | `retrievers/bm25.py`, Postgres `tsvector` |
| 2.6 | Hybrid search + RRF fusion | 📋 | `retrievers/hybrid.py` → pipeline `hybrid-v2`. PLAN gọi đây là cải thiện **lớn nhất** cho tài liệu doanh nghiệp: nhiều jargon nội bộ và mã tham chiếu mà embedding bắt kém |
| 2.7 | Cross-encoder reranking | 📋 | `retrievers/reranker.py`, top-20 → top-5 |
| 2.8 | Query rewriting | 📋 | pipeline `qrewrite-v1` |
| 2.9 | Multi-query retrieval / query expansion | 💡 | Sinh 3–5 biến thể → retrieve song song → RRF hợp nhất. Rất hợp tiếng Việt (nhiều cách diễn đạt cùng khái niệm HR). Dùng lại đúng code RRF của 2.6. Chi phí: +1 LLM call/query |
| 2.10 | Small-to-big / parent-document retrieval | 💡 | Embed chunk nhỏ để match chính xác, trả chunk cha để LLM đủ ngữ cảnh. **Trực tiếp giúp 8 câu `multi_hop`** trong golden set |
| 2.11 | Matryoshka coarse-to-fine two-stage | 💡 | Index song song 768 + 3072 → coarse top-50 ở dim thấp → rerank dim cao → top-5. Xem 7.1 |

---

## 3. Generation & Anti-hallucination

Cụm mạnh nhất của repo.

| # | Kỹ thuật | TT | Chi tiết |
|---|---|---|---|
| 3.1 | Grounded prompting | ✅ | Chỉ dùng context — `app/llm/prompts/answer_v1.jinja` |
| 3.2 | Forced citation format | ✅ | `[filename, p.N]` |
| 3.3 | Explicit refusal contract | ✅ | Câu từ chối là **constant**; prompt nhận nó như một **biến** từ đúng constant mà `is_refusal()` match → prompt và metric **không thể drift** khỏi nhau |
| 3.4 | **Citation verification loop** | ✅ | Parse citation **ngược ra khỏi câu trả lời**, resolve lại với đúng chunk đã đưa cho model. Không match → giữ với `supported=false` và **đếm nó**. Xoá đi là che giấu lỗi người đọc dễ tin nhất |
| 3.5 | Prompt versioning | ✅ | Đổi prompt = file mới (`answer_v1.jinja`), không sửa tại chỗ |
| 3.6 | Jinja2 `StrictUndefined` | ✅ | Biến typo **nổ** thay vì render chuỗi rỗng. Prompt thiếu context tạo ra output trông ổn và số vô nghĩa |
| 3.7 | `temperature=0` + timeout tường minh | ✅ | Trên mọi call |
| 3.8 | Provider-agnostic qua LiteLLM | ✅ | Đổi provider không đụng pipeline |
| 3.9 | Prompt caching | 💡 | Xem mục 6.1 |

---

## 4. Evaluation — cụm đáng show nhất

### 4a. Metrics

| # | Metric | TT | Chi tiết |
|---|---|---|---|
| 4.1 | `recall@k` | ✅ | |
| 4.2 | `MRR` | ✅ | |
| 4.3 | `nDCG@k` | ✅ | |
| 4.4 | LLM-as-judge — `faithfulness` 1–5 | ✅ | `eval/judge_prompts/faithfulness_v1.jinja` |
| 4.5 | LLM-as-judge — `answer_relevance` 1–5 | ✅ | `eval/judge_prompts/relevance_v1.jinja`, versioned riêng |
| 4.6 | `refusal_accuracy` | ✅ | **Deterministic, không dùng judge** (ADR-0006) — số safety-critical không phụ thuộc ý kiến model |
| 4.7 | **4 outcome thay vì nhị phân** | ✅ | `answered` / `correct_refusal` / `hallucinated` / `over_refusal` → pipeline từ chối hết **không thể** trông có vẻ an toàn |
| 4.8 | `over_refusal_rate` | ✅ | |
| 4.9 | `citation_rate` | ✅ | |
| 4.10 | `unsupported_citations` | ✅ | |
| 4.11 | Latency p50 / p95 | ✅ | |
| 4.12 | Loại trừ `unanswerable` khỏi retrieval metrics | ✅ | Không chấm 0 — loại hẳn, kèm `questions_excluded` in cạnh mọi aggregate |
| 4.13 | Judge fail = `None`, không bao giờ điểm mặc định | ✅ | `judge_failures` nằm cạnh mean |
| 4.14 | `cache_hit_rate` + `cost_usd` | 💡 | Đi kèm prompt caching (6.1) |
| 4.15 | `tool_call_count`, `retrieval_rounds`, `token_cost_per_answer` | 💡 | Bắt buộc nếu làm agentic RAG (6.2) |

### 4b. Golden set

| # | Kỹ thuật | TT | Chi tiết |
|---|---|---|---|
| 4.16 | Golden set 29 câu, phân bố có chủ đích | ✅ | 16 `factual` / 8 `multi_hop` / **5 `unanswerable`** |
| 4.17 | Nhóm `unanswerable` | ✅ | Đo được hệ thống **có dám nói "không biết"** không — không chỉ đo nó trả lời hay |
| 4.18 | Validator nghiêm | ✅ | Chunk id phải tồn tại **thật trong DB**; `unanswerable` phải có mảng rỗng; mọi dòng phải có `author` |
| 4.19 | Tự khai bias: agent-authored | ✅ | ADR-0004 + **bảng lạm phát** metric nào bị thổi nhiều nhất |
| 4.20 | Tự khai bias: judge = answer model | ✅ | ADR-0006; `leaderboard.md` in dòng nêu tên pipeline tự chấm |
| 4.21 | Independent judge model | 💡 | `--judge-model` **đã có flag**, trigger đã ghi trong ADR-0006. **Rẻ nhất trong toàn bộ danh sách** — biến "em biết mình bias" thành "em đã đo bias là bao nhiêu" |

### 4c. Experiment hygiene

| # | Kỹ thuật | TT | Chi tiết |
|---|---|---|---|
| 4.22 | Pipeline registry `@register(name)` | ✅ | `chat_service` lấy pipeline qua registry, không import class |
| 4.23 | Một thí nghiệm = đúng 1 biến = 1 pipeline mới | ✅ | Luật trong CLAUDE.md |
| 4.24 | Pipeline có kết quả đã commit thì **đóng băng** | ✅ | Sửa `naive_v1.py` sau khi commit `results/naive-v1.json` là phá comparability |
| 4.25 | Registry từ chối tên rebind / `name` lệch key | ✅ | |
| 4.26 | Runner từ chối ghi đè results file | ✅ | Và kiểm tra điều đó **trước khi tiêu 1 API call nào** |
| 4.27 | Full provenance trong mọi results file | ✅ | `config`, `dataset_version`, `golden_set_author`, `judge_model`, `judge_is_answer_model`, `git_sha`, `git_dirty`, `corpus_validated`, `partial_run`, `schema_version` |
| 4.28 | Không commit kết quả một phần | ✅ | Dừng ở câu 10/29 vì quota — "một file kết quả thực chất là mẫu 3 câu còn tệ hơn không có baseline, vì nó sẽ bị đọc như baseline" |
| 4.29 | Chunk-size ablation | 📋 | `chunk-500-v1`, `chunk-1200-v1` — cần re-ingest → phải ghi rõ corpus version |
| 4.30 | CI/CD cho eval | 📋 | `.github/workflows/eval.yml` — chạy eval trên PR, comment diff so baseline. Chỉ làm khi đã có ≥3 pipeline |

---

## 5. Software engineering (phần bị loại nhiều nhất ở vòng middle)

| # | Kỹ thuật | TT | Chi tiết |
|---|---|---|---|
| 5.1 | Async Python đúng | ✅ | SQLAlchemy 2.x async + `asyncpg` xuyên suốt, không sync façade chắp vá |
| 5.2 | Layering nghiêm | ✅ | `routes → services → repositories → models`; service không import `fastapi`, chỉ repo viết SQL |
| 5.3 | Protocol-based design | ✅ | `Retriever`, `VectorStore`, `Embedder`, `RAGPipeline` |
| 5.4 | Tách `schemas/` (Pydantic) khỏi `models/` (ORM) | ✅ | Không bao giờ trả ORM object từ route |
| 5.5 | Type safety | ✅ | `mypy` + `ruff` clean trên 47 file |
| 5.6 | Test 131 case, tách unit / integration | ✅ | `unit/` không chạm DB/network; `integration/` dùng Postgres thật qua docker compose |
| 5.7 | Alembic migration | ✅ | |
| 5.8 | Structured logging | ✅ | structlog JSON — `core/logging.py`, không `print()` ngoài `scripts/` |
| 5.9 | Centralized config | ✅ | `core/config.py`, không `os.getenv()` rải rác |
| 5.10 | Domain exceptions | ✅ | `core/exceptions.py`, không `except: pass` |
| 5.11 | Pinned model, **cấm alias** | ✅ | Alias đổi ngầm dưới pipeline đóng băng → results file ghi tên một cấu hình không còn định danh cái đã chạy (ADR-0007) |
| 5.12 | 7 ADR — Context / Decision / Consequences | ✅ | Kèm trigger cụ thể để xem xét lại từng quyết định |
| 5.13 | Progress log per-phase + mục "blocked on a human" | ✅ | `docs/progress/phase-N.md` |

---

## 6. Tính năng dự định thêm — phân tích chi phí

### 6.1 Prompt caching 💡 — khớp hoàn hảo, chi phí thấp

Ăn khớp vì đã đi qua LiteLLM và đã đau vì quota.

| | |
|---|---|
| Cache được | System prompt + few-shot (tĩnh) |
| **Không** cache được | Top-5 chunk (~4000 char, đổi mỗi query) |
| **Giá trị thật** | **Judge** — judge prompt gần như tĩnh và gọi ~53 lần/run. Cache prefix judge prompt là nơi tiết kiệm rõ nhất |
| Đo bằng | Thêm `cache_hit_rate` + `cost_usd` vào results file — provenance đã có sẵn, chỉ thêm field |

### 6.2 Agentic RAG — retriever as tool 💡 — sức nặng cao nhất, phá vỡ giả định v1

| | |
|---|---|
| Nội dung | LLM tự quyết gọi `search_documents(query, top_k)` bao nhiêu lần, tự reformulate khi kết quả kém, tự dừng khi đủ |
| Xung đột | CLAUDE.md liệt `llm/tools/` là **sau Phase 6**; phá giả định "single-turn" của v1 |
| **Chỗ khó thật sự** | **Eval harness hiện tại giả định 1 lượt retrieve/câu hỏi.** Agentic loop có N lượt → `recall@5` không còn định nghĩa được như cũ |
| Cần metric mới | `tool_call_count`, `retrieval_rounds`, `token_cost_per_answer` |
| Tín hiệu phỏng vấn | Nhận ra điều trên **trước khi code** là tín hiệu rất mạnh |

### 6.3 MCP server bọc retriever 💡

| | |
|---|---|
| Nội dung | Expose corpus như MCP server (`search_documents`, `get_document_page`) → Claude Desktop / Cursor dùng trực tiếp |
| Chi phí | Thấp — lớp vỏ mỏng trên `DenseRetriever` sẵn có |
| Cảnh báo | Đây là **integration**, không phải AI technique. Đừng để nó chiếm chỗ của breadcrumb / multi-query trong câu chuyện |

### 6.4 Docling / OCR 💡 — đắt nhất

| | |
|---|---|
| Giá trị thật | **Không chỉ OCR** — xuất structured document model: bảng thành bảng thật, heading hierarchy thật |
| Đánh trúng | Hai open item đã ghi trong repo: **bảng bị làm phẳng thành luồng cell tuyến tính** (phase-2), và breadcrumb cần heading hierarchy → **6.4 và 1.10 là cùng một mũi tên** |
| Golden set liên quan | `q021` / `q024` nhắm thẳng vào nội dung bảng |
| **Chi phí** | Đổi extraction = **re-ingest toàn bộ** = chunk id đánh lại = **phá `relevant_chunk_ids`** → ADR-0005 sẽ fail to tiếng, đúng như thiết kế |
| Điều kiện | Cần ADR mới (ADR-0001 đã chốt scanned PDF out of scope v1) |
| Tín hiệu phỏng vấn | Biết chi phí này và nói ra được chính là thứ đáng giá |

---

## 7. Cạm bẫy khi trình bày

### 7.1 Matryoshka — cách nói không bị bắt bài

**Thực trạng:** `gemini-embedding-001` là MRL model, gốc 3072 dim, đang truncate xuống 768.
Nhưng dùng như **con số cố định trong config**, không phải như kỹ thuật. Không adaptive
dimension, không coarse-to-fine two-stage, không shortlist dim thấp rồi rerank dim cao.

❌ *"Em dùng Matryoshka embedding."* → bị bắt bài ngay.

✅ Nói thế này:

> `gemini-embedding-001` là MRL model, gốc 3072 dim. Em truncate xuống 768 — đủ cho corpus
> quy mô này, giảm 4 lần dung lượng index và chi phí distance. Em **chưa khai thác MRL đúng
> nghĩa**, tức là coarse-to-fine two-stage search, vì với 34 chunk thì shortlist ở dim thấp
> không tiết kiệm được gì đo được. Ở quy mô hàng trăm nghìn vector thì đó là thứ em sẽ làm
> trước tiên — và vì con số 768 nằm ở **ba nơi phải đổi đồng thời** (`.env`, `EMBEDDING_DIM`,
> migration), đổi nó là một migration cộng full re-ingest cộng chạy lại mọi pipeline.

Câu sau cho thấy hiểu kỹ thuật **và** hiểu chi phí đổi nó. Đó mới là middle.

### 7.2 Các con số phải nói trước khi bị hỏi

| Vấn đề | Cách nói |
|---|---|
| **Chưa có `results/naive-v1.json`** | Nghiêm trọng nhất. Toàn bộ câu chuyện "evaluation-first" mà không có con số nào → mất sức thuyết phục |
| `recall@5 = 1.0` | Corpus 34 chunk, `top_k=5` nhìn thấy ~15% corpus → con số vô nghĩa. Đã tự ghi trong phase-4: đó là bằng chứng **plumbing chạy**, không phải bằng chứng retrieval tốt |
| Golden set do agent viết | ADR-0004 + bảng lạm phát |
| Judge tự chấm | ADR-0006; và 4.21 là cách rẻ nhất để sửa |
| Chỉ 1 pipeline | Chưa chứng minh được vòng lặp cải tiến |
| Chưa có API chat / UI | Phase 5 — không demo được |

### 7.3 Sự cố thật đã xử lý — kể được

| Sự cố | Xử lý |
|---|---|
| Provider khai tử `gemini-2.5-flash` giữa Phase 4 → 404 toàn bộ | Đổi sang `gemini-3.6-flash` pinned + luật cấm alias (ADR-0007). Ghi chú sắc: *"model vẫn xuất hiện trong `models` list và chỉ 404 khi gọi thật — 'cấu hình đúng' và 'còn chạy được' là hai câu hỏi khác nhau"* |
| Chunk id đánh lại khi `--force` re-ingest → phá golden set | `corpus.lock.json` + `make validate` fail to tiếng (ADR-0005) |
| Quota free tier 20 req/ngày/model vs ~82 req cần cho 1 run | Dừng ở câu 10/29, **không commit kết quả một phần** |

---

## 8. Thứ tự khuyến nghị

| # | Việc | Vì sao |
|---|---|---|
| 1 | `results/naive-v1.json` | Không có baseline thì mọi thứ ở trên là lý thuyết |
| 2 | `hybrid-v2` (BM25 + RRF) | Đã trong PLAN, ROI cao nhất |
| 3 | Independent judge (4.21) | Rẻ nhất — biến điểm yếu thành phép đo |
| 4 | Breadcrumb metadata (1.10) | Đánh trúng vấn đề bảng đã ghi nhận; là **1 biến duy nhất** → đúng luật Phase 6, thành `breadcrumb-v2`, đo ngay bằng harness sẵn có |
| 5 | Prompt caching (6.1) | Giải quyết đau quota có thật |
| 6 | Multi-query (2.9) | |
| 7 | Agentic RAG (6.2) / MCP (6.3) | Sau Phase 6, cần ADR |
| 8 | Docling (6.4) | Đắt nhất — cần ADR + chấp nhận re-ingest |

> **Cảnh báo:** với JD middle, **2 pipeline có số so sánh được đánh bại 8 kỹ thuật kể miệng.**
> Danh sách dài chứng minh bạn đọc nhiều; một dòng thứ hai trong `leaderboard.md` chứng minh
> bạn **đo được**. Nhà tuyển dụng phân biệt hai thứ đó rất nhanh.
