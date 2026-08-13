# rag-chatbot

Bản tiếng Anh: [README.md](README.md).

Hệ thống Q&A trên tài liệu nội bộ: người dùng hỏi bằng tiếng Việt, hệ thống trả lời **kèm trích dẫn**
(tên tài liệu + số trang), hoặc từ chối trả lời khi tài liệu không có thông tin.

Corpus của v1 là 8 tài liệu HR tiếng Việt (sổ tay nhân viên, lương thưởng phúc lợi, khung cấp bậc,
nghỉ phép & làm việc từ xa, bảo mật thông tin, tuyển dụng, quy tắc ứng xử, công tác phí) — 16 trang,
34 chunk. Đây là tài liệu demo **tổng hợp** của một công ty hư cấu, không phải dữ liệu thật, nên được
commit thẳng vào repo tại [data/raw/HR_pdfs/](data/raw/HR_pdfs/) và có thể mở, trích, chia sẻ tự do
([ADR-0001](docs/adr/0001-scope-va-data-boundary.md)).

## Ví dụ

Cả hai ví dụ dưới đây là output thật, lấy từ [results/naive-v1.json](results/naive-v1.json) —
lần chạy `naive-v1` đã commit trên toàn bộ golden set.

```
Hỏi:      Buổi sáng muộn nhất mấy giờ thì mọi người phải có mặt?
Trả lời:  10:00 là giờ muộn nhất phải có mặt trong khung giờ bắt buộc (core hours).
          [01_so_tay_nhan_vien.pdf, p.1]
Citation: 01_so_tay_nhan_vien.pdf, trang 1 (chunk 2) — supported: true
Latency:  retrieval 377 ms · generation 1427 ms
```

Trường hợp không có thông tin trong tài liệu — hệ thống **từ chối**, không đoán:

```
Hỏi:      Mỗi tháng được hỗ trợ bao nhiêu tiền bữa trưa?
Trả lời:  Không tìm thấy thông tin trong tài liệu.
Citation: (không có)
```

Câu từ chối là một **chuỗi cố định** (`REFUSAL_MARKER` trong
[backend/app/llm/rag/pipelines/base.py](backend/app/llm/rag/pipelines/base.py)), được inject vào
prompt và được `is_refusal()` khớp lại bằng string — chỉ số an toàn nhất của dự án không phụ thuộc
vào phán đoán của model.

## Trạng thái

- **Chạy được hôm nay:** ingest đồng bộ, dense retrieval, `make eval` trên golden set 29 câu, API với
  `POST /api/v1/chat`, `POST /api/v1/documents`, `GET /api/v1/documents`, `GET /api/v1/health`, cùng
  một trang Streamlit (`make ui`).
- **Baseline đã commit:** `results/naive-v1.json` + `results/leaderboard.md`. Phase 6 đang chạy —
  thí nghiệm đầu tiên, `hybrid-v2`, **thua và vẫn được commit**
  ([ADR-0009](docs/adr/0009-hybrid-retrieval-not-adopted.md)).
- **Chưa có:** multi-turn / conversation memory, function calling, streaming, async worker, auth,
  OCR, reranker. Các thư mục tương ứng để trống cho tới khi có lý do cụ thể và một ADR.
- **Đang treo:** Definition of Done của Phase 5 yêu cầu một người ngoài team click thử UI mà không
  cần hướng dẫn; chưa ai làm ([docs/progress/phase-5.md](docs/progress/phase-5.md)).

## Cách hoạt động

`PDF/DOCX → parse → chunk → embed → pgvector → retrieve top-k → prompt → answer + citations`

- **Số trang sống sót qua toàn bộ pipeline**: `Page.page_no` (1-based, PyMuPDF) → `TextChunk.page_no`
  → cột `chunks.page_no` trong DB → biến `c.page_no` trong prompt → chuỗi `[tên_tệp, p.N]` trong câu
  trả lời → `parse_citations()` đọc ngược ra và đối chiếu với đúng các chunk đã retrieve. Citation
  trỏ tới nguồn chưa từng được retrieve bị đếm là `unsupported`. Mỗi trang được chunk riêng nên một
  chunk không bao giờ vắt qua ranh giới trang — đó chính là lý do citation chỉ được đúng số trang
  chứ không phải đoán ([chunking.py](backend/app/llm/rag/chunking.py)).
- **Retrieval: dense thuần, top_k=5, cosine distance** qua pgvector với index HNSW. Không rerank,
  không hybrid, không lọc metadata, không ngưỡng score — `naive-v1` cố tình là thứ ngu nhất có thể
  để làm mốc so sánh ([dense.py](backend/app/llm/rag/retrievers/dense.py)).
- **Prompt ép trích dẫn và ép từ chối** — 5 quy tắc bắt buộc trong
  [answer_v1.jinja](backend/app/llm/prompts/answer_v1.jinja). Khi retrieval trả về rỗng, pipeline
  không gọi LLM: từ chối là output đúng duy nhất.

## Đánh giá

Golden set 29 câu ([backend/eval/datasets/golden_qa.v1.jsonl](backend/eval/datasets/golden_qa.v1.jsonl))
trên corpus đã **đóng băng** ([ADR-0005](docs/adr/0005-frozen-corpus-for-the-golden-set.md)): 16 câu
`factual`, 8 câu `multi_hop`, 5 câu `unanswerable`, mỗi dòng có `relevant_chunk_ids` đã xác minh và
một trường `author` bắt buộc. Metric retrieval, refusal và citation đều là số học; `faithfulness` và
`answer_relevance` do LLM chấm thang 1–5 ([ADR-0006](docs/adr/0006-how-generation-is-scored.md)).

Kết quả `naive-v1` đã commit — đọc [ADR-0004](docs/adr/0004-agent-authored-golden-set.md) **trước
khi** trích bất kỳ con số nào:

| recall@5 | MRR | nDCG@5 | faithful | relevance | refusal | cite ok | p50 |
|---|---|---|---|---|---|---|---|
| 0.958 | 0.840 | 0.857 | 4.897 | 4.250 | 1.000 | 1.000 | 2009 ms |

Hai giới hạn phải nói kèm: **29 câu do agent viết**, không phải người — retrieval metric bị thổi lên
nhiều nhất; và **judge chính là model trả lời** (chỉ có một provider được cấu hình), nên
`faithfulness` và `answer_relevance` là tự chấm và lệch lên
([ADR-0006](docs/adr/0006-how-generation-is-scored.md)). Các cột retrieval và refusal là deterministic,
không bị ảnh hưởng. So sánh tương đối giữa các pipeline là hợp lệ; giá trị tuyệt đối thì không — và
metric generation không tái lập được giữa hai lần chạy, nên đừng bao giờ đọc một con số đơn lẻ.

## Stack

| Tầng | Lựa chọn | Ghi chú |
|---|---|---|
| **Ngôn ngữ** | Python 3.12 | quản lý dependency và venv bằng `uv` |
| **API** | FastAPI + uvicorn | `python-multipart` cho route upload |
| **Database** | PostgreSQL 16 + pgvector | `pgvector/pgvector:pg16`, index HNSW (`vector_cosine_ops`) |
| **ORM** | SQLAlchemy 2.x + `asyncpg` | async hoàn toàn; migration bằng Alembic |
| **Generation** | `gpt-5.6-luna` (OpenAI) | qua LiteLLM, tên model đọc từ `.env` |
| **Embedding** | `text-embedding-3-large` | **768 chiều** bằng truncation native |
| **Parsing** | PyMuPDF · `python-docx` | PyMuPDF cho đúng số trang mà citation cần |
| **Prompt** | Jinja2 | version nằm trong tên file — `answer_v1.jinja` |
| **Frontend** | Streamlit | là extra `frontend` tùy chọn, API deploy được mà không cần nó |
| **Config / logging** | `pydantic-settings` · `structlog` | mọi config qua `core/config.py`, log JSON |
| **Test / lint** | pytest + `pytest-asyncio` · ruff · mypy | thuộc extra `dev` |

Các tham số retrieval của baseline — `chunk_size=800`, `chunk_overlap=100`, `top_k=5` — đọc từ `.env`
và là giá trị mà `naive-v1` đã được đo.

Ba ràng buộc đằng sau bảng này cần biết trước khi đổi bất cứ thứ gì trong đó:

- **Model được pin cứng, không bao giờ dùng alias động.** Một alias thay đổi âm thầm dưới chân một
  pipeline đã đóng băng sẽ khiến file results ghi tên một cấu hình không còn định danh được thứ đã chạy.
- **`gpt-5.6-luna` từ chối `temperature=0`**, nên tham số bị bỏ và mọi file results ghi
  `temperature: null` ([ADR-0008](docs/adr/0008-provider-migration-to-openai.md)). Vì vậy mỗi lần
  chạy đều có sampling — đó là lý do metric generation không tái lập chính xác được.
- **Con số 768 nằm ở ba nơi phải đổi cùng nhau**: `.env`, `app/models/chunk.py`, và migration đầu
  tiên. Đổi nó là một migration + một lần re-embed + chạy lại toàn bộ pipeline.

Celery + Redis, Chonkie, LangChain / LangGraph cố tình không có trong v1, mỗi cái đều có trigger để
xem xét lại ([ADR-0002](docs/adr/0002-tech-stack-resolution.md)).

## Chạy thử

Lần đầu — dựng môi trường và nạp corpus:

```bash
cp .env.example .env    # điền DEFAULT_LLM_API_KEY + EMBEDDING_API_KEY (OpenAI)
make install            # uv sync --extra dev
make up                 # docker compose up -d --wait
make migrate            # alembic upgrade head
make ingest             # mặc định --path ../data/raw
```

Sau đó, [scripts/start.sh](scripts/start.sh) bật toàn bộ stack bằng một lệnh —
postgres → migration → API → Streamlit, mỗi bước chờ healthy rồi mới sang bước sau:

```bash
./scripts/start.sh          # API ở :8000, UI ở :8501
./scripts/start.sh --stop   # tắt API + UI (postgres vẫn chạy)
```

| | |
|---|---|
| API docs | http://127.0.0.1:8000/docs |
| Health | http://127.0.0.1:8000/api/v1/health → `{"status":"ok","database":"up"}` |
| UI | http://127.0.0.1:8501 |
| Log | `.run/api.log` · `.run/ui.log` |

Smoke test khi stack đang chạy, trả lời từ corpus đã commit:

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"question":"Nhân viên được nghỉ phép bao nhiêu ngày một năm?"}'
# → "Nhân viên chính thức được nghỉ 15 ngày phép/năm; cứ 03 năm làm việc liên tục được cộng
#    thêm 01 ngày, tối đa 20 ngày. [04_nghi_phep_va_lam_viec_tu_xa.pdf, p.1]"
```

**Chạy trên máy chủ từ xa, hoặc cần đổi cổng?** Các URL `127.0.0.1` ở trên chỉ mở được bằng trình
duyệt ngay trên máy chủ đó. Xem [docs/running.vi.md](docs/running.vi.md) cho truy cập từ xa (bao gồm
cả việc `start.sh` tự dò public IP trên EC2), đổi cổng, và `--stop` thực sự tắt những gì.

## Ghi chú vận hành

- **API không có auth, không rate limit**, và mỗi lệnh gọi `/chat` tiêu tốn một key có tính phí. Đừng
  expose ra ngoài laptop hoặc mạng tin cậy.
- **Đổi embedding model → `make reembed`, tuyệt đối không `make ingest FORCE=1`.** `FORCE=1` cấp lại
  chunk id mới, làm vô hiệu toàn bộ `relevant_chunk_ids` của golden set. Upload qua HTTP cũng là một
  thay đổi corpus — `POST /documents` không có tham số `force`, nhưng vẫn nên chạy `make validate`
  sau mỗi phiên upload ([ADR-0005](docs/adr/0005-frozen-corpus-for-the-golden-set.md),
  [ADR-0008](docs/adr/0008-provider-migration-to-openai.md)).
- Các target khác: `make validate` · `make find Q="phụ cấp"` · `make eval P=naive-v1` · `make report` ·
  `make test` · `make lint` · `make fmt` · `make psql` · `make logs` · `make down` · `make revision M="…"`.
- Đọc thêm: [docs/progress.md](docs/progress.md) (trạng thái từng phase, cái gì đang chờ người),
  [CLAUDE.md](CLAUDE.md) (toàn bộ quy tắc làm việc), [PLAN.md](PLAN.md) (lộ trình),
  [docs/architecture.md](docs/architecture.md) (phân tầng và bản đồ phase → thư mục).
