# CLAUDE.md — rag-chatbot

File context tự động nạp cho Claude Code. Đọc hết trước khi làm bất cứ việc gì.
Kế hoạch thi công: `PLAN.md`. Bản đồ phase → thư mục: `docs/architecture.md`.

---

## 1. Mục tiêu

Hỏi–đáp trên tài liệu nội bộ doanh nghiệp. Người dùng hỏi tiếng Việt, hệ thống trả lời
kèm **trích dẫn** (tên tài liệu + số trang).

Ưu tiên: **chạy được và đo được sớm**, rồi mới tối ưu. Cấu trúc thư mục đã được thiết kế
cho giai đoạn cuối — nhưng **không được scaffold hết ngay từ đầu**. Xem mục 4.

## 2. Phạm vi

**Trong scope v1 (Phase 0–5):**
- PDF + DOCX text-based
- Hỏi 1 lượt, không phân quyền, không auth
- Trả lời + citations
- Ingest đồng bộ

**Ngoài scope v1 — thư mục có sẵn nhưng ĐỂ TRỐNG:**

| Thư mục / file | Mở khoá ở |
|---|---|
| `app/workers/` | sau Phase 6 |
| `app/llm/memory.py` | sau Phase 6 (multi-turn) |
| `app/llm/tools/` | sau Phase 6 (function calling) |
| `app/api/v1/routes/conversations.py` | sau Phase 6 |
| `app/repositories/conversation_repo.py`, `message_repo.py` | sau Phase 6 |
| `frontend/` | Phase 5 |
| `vector_store.py` bản Qdrant | chưa bao giờ — pgvector là đủ |

Không tạo file `.py` rỗng hay class abstract "để sau này dùng". Thư mục rỗng thì để rỗng
(có `.gitkeep`). Abstraction sinh ra trước nhu cầu là nợ, không phải tài sản.

## 3. Tech stack — đã chốt

| | |
|---|---|
| Python | 3.11, quản lý bằng `uv` |
| DB | PostgreSQL 16 + pgvector |
| ORM | SQLAlchemy 2.x + Alembic |
| API | FastAPI + uvicorn |
| PDF | PyMuPDF (`fitz`) — cần số trang chính xác |
| DOCX | `python-docx` |
| Embedding | `text-embedding-3-small` (1536 dim) |
| LLM | đọc từ env, mặc định `claude-sonnet-4-6` |
| Prompt | Jinja2 template trong `app/llm/prompts/`, đặt tên có version |
| Frontend | Phase 5 quyết định (Streamlit nếu chỉ cần demo) |
| Test | pytest |

> ⚠️ **Câu hỏi chặn dự án:** dữ liệu có được gửi ra API bên ngoài không? Nếu KHÔNG,
> toàn bộ embedding/LLM phải self-host (Ollama + `bge-m3`) và stack đổi. Xem HUMAN GATE
> Phase 0. Không tự quyết.

## 4. Nguyên tắc kiến trúc

**4.1. Pipeline là đơn vị được eval.**
`app/llm/rag/pipelines/` chứa các implement của `RAGPipeline`. Mỗi pipeline là một
cấu hình RAG hoàn chỉnh, có tên, đăng ký trong `registry.py`:

```python
# app/llm/rag/pipelines/base.py
class RAGPipeline(Protocol):
    name: str
    config: PipelineConfig          # chunk_size, top_k, retriever, model...
    def retrieve(self, question: str) -> list[RetrievedChunk]: ...
    def answer(self, question: str) -> RAGAnswer: ...
```

```python
@register("naive-v1")
class NaiveV1: ...
```

Hệ quả bắt buộc:
- `eval/runner.py --pipeline naive-v1` chạy được với **bất kỳ** tên nào trong registry.
- **Pipeline đã có kết quả trong `results/` là bất biến.** Muốn thử ý tưởng mới →
  tạo file pipeline mới + tên mới. Không sửa `naive_v1.py` sau khi đã commit
  `results/naive-v1.json`. Sửa là làm hỏng khả năng so sánh.
- `chat_service.py` chọn pipeline qua registry theo config, không import trực tiếp class.

**4.2. Phân tầng — không được đi tắt.**
```
routes/  →  services/  →  repositories/  →  models/
                      →  llm/rag/pipelines/
```
- `routes/` chỉ validate + gọi service. Không có business logic.
- `services/` không biết HTTP tồn tại. Không import `fastapi`, không nhận `Request`.
- Chỉ `repositories/` được viết query SQL / dùng session. Service không tự query.
- `schemas/` (Pydantic, hợp đồng API) tách hẳn khỏi `models/` (ORM). Không trả ORM object
  ra route.

**4.3. Retriever là interface.**
`retrievers/base.py` định nghĩa protocol; `dense.py`, `bm25.py`, `hybrid.py`, `reranker.py`
là các implement. Pipeline nhận retriever qua constructor, không tự khởi tạo.
Chỉ viết `dense.py` ở Phase 4; phần còn lại ở Phase 6.

## 5. Quy tắc làm việc

1. **Một phase một lần.** Xong phase N → chạy Definition of Done → báo cáo → chờ xác nhận.
   Không nhảy cóc, không "làm luôn phase sau cho tiện".
2. **Chỉ tạo thư mục/file khi đến phase của nó.** Bản đồ ở `docs/architecture.md`.
3. **Không tối ưu sớm.** `chunk_size=800`, `overlap=100`, `top_k=5` là giá trị khởi đầu,
   giữ nguyên đến Phase 6.
4. **Từ Phase 6: mỗi experiment đổi đúng 1 biến**, và là một pipeline mới có tên riêng.
5. **Không mock, không dữ liệu giả.** Chưa có tài liệu thật hoặc API key → dừng, hỏi.
   Tuyệt đối không tự sinh PDF mẫu để "cho chạy được".
6. **Không tự viết golden set** (Phase 3). Nếu được yêu cầu, từ chối và giải thích.
7. **Mọi quyết định kỹ thuật có đánh đổi → ghi 1 ADR** vào `docs/adr/NNNN-tieu-de.md`
   (Context / Decision / Consequences). Không tranh luận trong commit message.
8. **Mọi số liệu phải ghi ra `results/*.json` và commit.** Không báo cáo miệng.
9. Commit theo phase: `feat(phase-2): sync ingest pipeline`.
10. Secrets chỉ ở `.env` (đã gitignore). `.env.example` commit với giá trị rỗng.

## 6. Quy ước code

- Type hints ở mọi hàm public. `mypy` không bắt buộc pass 100% nhưng đừng thêm `Any` bừa.
- Không `except: pass`. Exception của domain nằm ở `core/exceptions.py`.
- Config đọc qua `core/config.py`. Không `os.getenv()` rải rác.
- Log qua `core/logging.py` (structlog, JSON). Không `print()` ngoài `scripts/`.
- Ingest **idempotent**: chạy lại cùng file không sinh chunk trùng (dựa trên `file_hash`).
- Prompt không hardcode inline — luôn nằm trong `app/llm/prompts/*.jinja`, có version
  trong tên file (`answer_v1.jinja`). Đổi prompt = file mới.
- Test: `tests/unit/` không chạm DB/network; `tests/integration/` dùng Postgres thật
  qua docker compose.

## 7. Lệnh (tất cả qua Makefile, chạy từ repo root)

```bash
make up          # docker compose up -d (postgres + pgvector)
make migrate     # alembic upgrade head
make ingest      # python -m scripts.ingest_corpus --path data/raw
make api         # uvicorn app.main:app --reload
make eval P=naive-v1
                 # python -m eval.runner --pipeline naive-v1
make report      # python -m eval.report -> results/leaderboard.md
make test
make lint        # ruff + mypy
```

Lệnh Python chạy từ `backend/`. Makefile ở root lo việc `cd`.