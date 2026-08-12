# rag-chatbot

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

Phase 0–4 đã xong. Phase 5 **code đã xong**, còn treo ở một cửa của con người.

- Chạy được hôm nay: ingest đồng bộ, dense retrieval, `make eval` trên golden set 29 câu, và API với
  `POST /api/v1/chat`, `POST /api/v1/documents`, `GET /api/v1/documents`, `GET /api/v1/health`, cùng
  một trang Streamlit (`make ui`).
- Baseline `naive-v1` **đã commit**: `results/naive-v1.json` + `results/leaderboard.md`.
- Chưa có: multi-turn / conversation memory, function calling, streaming, async worker, auth, OCR,
  reranker, hybrid retrieval — tất cả thuộc Phase 6 trở đi.
- Definition of Done của Phase 5 chưa đạt: PLAN.md yêu cầu một người ngoài team click thử UI mà không
  cần hướng dẫn; chưa ai làm ([docs/progress/phase-5.md](docs/progress/phase-5.md)).

## Cách hoạt động

`PDF/DOCX → parse → chunk → embed → pgvector → retrieve top-k → prompt → answer + citations`

- **Chunking theo cửa sổ ký tự, `chunk_size=800` / `chunk_overlap=100`**, không phải theo token.
  Mỗi trang được chunk riêng nên **một chunk không bao giờ vắt qua ranh giới trang** — đó chính là
  lý do citation chỉ được đúng số trang chứ không phải đoán. Điểm cắt được "snap" lùi về ranh giới
  đoạn → câu → dòng → từ, nên chunk không đứt giữa từ
  ([chunking.py](backend/app/llm/rag/chunking.py)).
- **Số trang sống sót qua toàn bộ pipeline**: `Page.page_no` (1-based, PyMuPDF) → `TextChunk.page_no`
  → cột `chunks.page_no` trong DB → biến `c.page_no` trong prompt → chuỗi `[tên_tệp, p.N]` trong câu
  trả lời → `parse_citations()` đọc ngược ra và đối chiếu với đúng các chunk đã retrieve. Citation
  trỏ tới nguồn chưa từng được retrieve bị đếm là `unsupported`.
- **Retrieval: dense thuần, top_k=5, cosine distance** qua pgvector với index HNSW
  (`vector_cosine_ops`, `m=16`, `ef_construction=64`). Không rerank, không hybrid, không lọc metadata,
  không ngưỡng score — `naive-v1` cố tình là thứ ngu nhất có thể để làm mốc so sánh
  ([dense.py](backend/app/llm/rag/retrievers/dense.py)).
- **Prompt ép trích dẫn và ép từ chối**: `answer_v1.jinja` ra 5 quy tắc bắt buộc — chỉ dùng nội dung
  trong phần TÀI LIỆU, ghi nguồn dạng `[tên tệp, p.số trang]` sau mỗi thông tin, và khi không đủ
  thông tin thì trả lời **đúng một câu** `Không tìm thấy thông tin trong tài liệu.` và không thêm gì
  khác. Khi retrieval trả về rỗng, pipeline không gọi LLM: từ chối là output đúng duy nhất.
- **Xử lý tiếng Việt**: regex cắt câu yêu cầu dấu câu **phải theo sau bởi khoảng trắng**, để "6.3.
  Trong thời gian" không bị cắt giữa số hiệu điều khoản; `is_refusal()` chuẩn hóa Unicode trước khi
  so khớp, nên một dấu thanh ở dạng decomposed không quyết định được một metric.

## Đánh giá

Golden set 29 câu ([backend/eval/datasets/golden_qa.v1.jsonl](backend/eval/datasets/golden_qa.v1.jsonl))
trên corpus đã **đóng băng** ([ADR-0005](docs/adr/0005-frozen-corpus-for-the-golden-set.md)): 16 câu
`factual`, 8 câu `multi_hop`, 5 câu `unanswerable`. Mỗi dòng có `relevant_chunk_ids` đã xác minh và
một trường `author` bắt buộc.

- **Retrieval (số học, không do model chấm):** `recall@5`, `MRR`, `nDCG@5` — chỉ tính trên 24 câu
  answerable.
- **Generation (LLM-as-judge, thang 1–5):** `faithfulness` chấm mọi câu (câu trả lời có nằm trọn
  trong context đã retrieve không), `answer_relevance` chỉ chấm câu answerable, đối chiếu với
  `ground_truth`. Judge trả JSON; parse hỏng thì ghi `None`, không bao giờ ghi điểm mặc định.
- **Refusal & citation (số học):** `refusal_accuracy`, `over_refusal_rate`, `citation_rate`,
  `unsupported_citations`.
- **~3 lệnh gọi provider mỗi câu**: 1 answer + 1 faithfulness + 1 relevance (câu `unanswerable`
  không chấm relevance nên tốn 2). Khoảng 82 call cho một lần chạy 29 câu.

Kết quả `naive-v1` đã commit — đọc [ADR-0004](docs/adr/0004-agent-authored-golden-set.md) **trước
khi** trích bất kỳ con số nào:

| recall@5 | MRR | nDCG@5 | faithful | relevance | refusal | cite ok | p50 |
|---|---|---|---|---|---|---|---|
| 0.958 | 0.840 | 0.857 | 4.897 | 4.250 | 1.000 | 1.000 | 2009 ms |

Hai giới hạn phải nói kèm: **29 câu do agent viết**, không phải người — retrieval metric bị thổi lên
nhiều nhất; và **judge chính là model trả lời** (chỉ có một provider được cấu hình), nên
`faithfulness` và `answer_relevance` là tự chấm và lệch lên
([ADR-0006](docs/adr/0006-how-generation-is-scored.md)). Các cột retrieval và refusal là deterministic,
không bị ảnh hưởng. So sánh tương đối giữa các pipeline là hợp lệ; giá trị tuyệt đối thì không.

## Stack

Python 3.12 (`uv`) · FastAPI · PostgreSQL 16 + pgvector, async qua SQLAlchemy 2.x + `asyncpg` ·
Alembic · PyMuPDF (PDF) / `python-docx` (DOCX) · LiteLLM với model đọc từ `.env` — hiện tại OpenAI
`gpt-5.6-luna` cho generation và `text-embedding-3-large` ở **768 chiều** (truncation native) ·
prompt Jinja2 có version trong tên file · Streamlit cho UI demo · pytest.

Model được **pin cứng, không bao giờ dùng alias động** — một alias thay đổi âm thầm sẽ khiến file
results ghi tên một cấu hình không còn định danh được thứ đã chạy. `gpt-5.6-luna` từ chối
`temperature=0`, nên tham số bị bỏ và results ghi `temperature: null`
([ADR-0008](docs/adr/0008-provider-migration-to-openai.md)).

Celery + Redis, Chonkie, LangChain / LangGraph **cố tình không có trong v1**.
[ADR-0002](docs/adr/0002-tech-stack-resolution.md) ghi lý do và trigger để xem xét lại từng cái.

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

`--stop` giải phóng cổng 8000 và 8501 theo cổng chứ không chỉ theo pidfile, nên dọn được cả server
bật tay bằng `make api` / `make ui`. Hai cổng đều đổi được: `API_PORT=8080 ./scripts/start.sh`.

**Chạy trên máy chủ từ xa?** Các URL `127.0.0.1` ở trên — và cả `0.0.0.0` / `localhost` mà Streamlit
in ra — chỉ mở được bằng trình duyệt **ngay trên máy chủ đó**. `0.0.0.0` là địa chỉ bind, nghĩa là
"nghe trên mọi interface", không phải một đích đến để truy cập; từ laptop của bạn thì cả nó lẫn
`localhost` đều trỏ về chính laptop, nơi không có gì chạy. Hãy dùng địa chỉ của máy chủ
(`http://<ip-máy-chủ>:8501`), và đặt `PUBLIC_HOST=<ip-máy-chủ>` để script tự in ra URL đó.
**API chỉ bind vào localhost** nên không truy cập được theo cách này — đây là cố ý, vì API không có
auth và mỗi lệnh gọi `/chat` tiêu tốn một key có tính phí. Trang Streamlit gọi API từ phía máy chủ
nên UI vẫn chạy bình thường; muốn gọi thẳng API thì mở tunnel:
`ssh -L 8000:127.0.0.1:8000 <user>@<server>`.

Nếu muốn chạy tách rời thì `make api` và `make ui` ở hai terminal vẫn dùng được như cũ. Mọi target
chạy từ thư mục gốc; Makefile tự `cd backend`.

## Phạm vi

**Trong phạm vi v1 (Phase 0–5):** PDF/DOCX dạng text · câu hỏi single-turn, không auth, không phân
quyền · câu trả lời kèm citation hoặc câu từ chối tường minh · ingest đồng bộ · ghi lại mọi câu hỏi
vào bảng `queries`.

**Ngoài phạm vi v1:** async worker, conversation memory, function calling, streaming, phân quyền theo
tài liệu, OCR, Qdrant. Các thư mục tương ứng tồn tại nhưng để trống cho tới khi có lý do cụ thể và
một ADR.

## Quy tắc làm việc

1. **Pipeline đã có results committed là bị đóng băng.** Ý tưởng mới → file pipeline mới, tên mới.
   Sửa `naive_v1.py` (hay `answer_v1.jinja`) sau khi `results/naive-v1.json` đã commit là phá hủy khả
   năng so sánh giữa các lần chạy.
2. **Mọi con số phải được ghi vào `results/*.json` và commit — kể cả số xấu.** Không báo cáo miệng.
   Kết quả tiêu cực cũng là thông tin.

## Ghi chú vận hành

- **Đổi embedding model → `make reembed`, tuyệt đối không `make ingest FORCE=1`.** `FORCE=1` xóa và
  chèn lại chunk, tức là **cấp lại chunk id mới**, làm vô hiệu toàn bộ `relevant_chunk_ids` của golden
  set. `make reembed` UPDATE tại chỗ nên chunk id, `corpus.lock.json` và golden set sống sót. Corpus
  đang bị đóng băng và `make validate` sẽ FAIL lớn tiếng khi phát hiện
  ([ADR-0005](docs/adr/0005-frozen-corpus-for-the-golden-set.md),
  [ADR-0008](docs/adr/0008-provider-migration-to-openai.md)).
- **Mỗi lần upload qua HTTP cũng là một thay đổi corpus** — `POST /documents` cố tình **không có**
  tham số `force` nên không thể cấp lại id của tài liệu cũ, nhưng vẫn nên chạy `make validate` sau mỗi
  phiên upload.
- **API không có auth, không rate limit**, và mỗi lệnh gọi `/chat` tiêu tốn một key có tính phí. Đừng
  expose ra ngoài laptop hoặc mạng tin cậy.
- Các target khác: `make validate` · `make find Q="phụ cấp"` · `make eval P=naive-v1` · `make report` ·
  `make test` · `make lint` · `make fmt` · `make psql` · `make logs` · `make down` · `make revision M="…"`.
- Đọc thêm: [docs/progress.md](docs/progress.md) (trạng thái từng phase, cái gì đang chờ người),
  [CLAUDE.md](CLAUDE.md) (quy tắc làm việc), [PLAN.md](PLAN.md) (lộ trình),
  [docs/architecture.md](docs/architecture.md) (phân tầng và bản đồ phase → thư mục).
