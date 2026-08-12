# Luồng RAG / chat — đi từ `POST /chat` xuống tận SQL

Ghi lại ngày 2026-08-12, ứng với code sau commit `66f7b67` (phase 5).
Nguồn sự thật vẫn là code trong `backend/`; file này chỉ là bản đồ đọc code.

---

## 1. Sơ đồ

```
POST /api/v1/chat
  │
  ├─ app/api/v1/routes/chat.py         validate câu hỏi rỗng, map lỗi → HTTP code
  │
  ├─ app/services/chat_service.py      build_pipeline(settings.pipeline_name) qua REGISTRY
  │
  ├─ app/llm/rag/pipelines/naive_v1.py  answer(question)
  │    │
  │    ├─ retrievers/dense.py           embed_query() → vector 768 chiều
  │    │    └─ vector_store.py          → document_repo.search_similar()
  │    │         └─ SQL: ORDER BY embedding <=> :q LIMIT 5
  │    │
  │    ├─ prompts/answer_v1.jinja       render prompt = 5 quy tắc + chunks + câu hỏi
  │    ├─ llm/client.py                 LiteLLM complete() → text
  │    └─ pipelines/base.py             parse_citations() đọc [file, p.N] ra khỏi answer
  │
  ├─ repositories/query_repo.py         INSERT vào bảng queries (observability)
  │
  └─ app/schemas/chat.py                ChatResponse trả về client
```

Tầng đi đúng theo CLAUDE.md 4.2: `routes/ → services/ → repositories/ → models/`,
và `services/ → llm/rag/pipelines/`. Không có đường tắt nào.

---

## 2. Từng bước

### Bước 1 — Route: `app/api/v1/routes/chat.py`

Route chỉ làm hai việc, không có business logic:

- `question.strip()` rỗng → **422**.
- Gọi `chat_service.answer_question(...)`.

Phân loại lỗi ở đây có chủ đích:

| Tình huống | Code | Vì sao |
|---|---|---|
| `PipelineNotFound` | 500 | `PIPELINE_NAME` trong `.env` trỏ vào pipeline không tồn tại → *mọi* request đều hỏng như nhau. Đây là sai cấu hình, không phải input xấu. |
| Exception khác | 502 | Thủ phạm khả dĩ nhất là provider: timeout, 429, model bị retire. 502 = "upstream hỏng", đúng cái đã xảy ra. |
| Từ chối trả lời | **200** | "Không tìm thấy thông tin trong tài liệu." là một câu trả lời **đúng và thành công**, không phải 404 (ADR-0006). Client đọc field `refused`. |

Điểm cuối cùng là điểm dễ làm sai nhất khi sửa route sau này.

### Bước 2 — Service: `app/services/chat_service.py`

```python
pipeline = pipeline or build_pipeline(settings.pipeline_name, session)
answer   = await pipeline.answer(question)
query_id = await _record(session, answer)
return ChatResponse.from_answer(answer, query_id=query_id)
```

Ba điều đáng nhớ:

1. **Không import `NaiveV1`.** Pipeline luôn lấy qua registry. Đó là toàn bộ lý do
   registry tồn tại (CLAUDE.md 4.1): phục vụ một pipeline phase 6 chỉ là sửa `.env`,
   không phải sửa code.
2. Tham số `pipeline` có thể inject → test drive được service bằng double, không cần DB.
3. Service **không** import `fastapi`, không nhận `Request`. Nó không biết HTTP tồn tại.

`_record()` nuốt exception có chủ ý: bảng `queries` là bản ghi quan sát, không phải một
phần của câu trả lời. Câu trả lời đã sinh ra và đã trả tiền rồi — nếu INSERT hỏng thì
rollback, log, trả `query_id=None`. **Mất trace là dở, mất answer còn dở hơn.**

Service cũng là nơi log ra `unsupported_citations` — số citation mà model bịa ra.

### Bước 3 — Pipeline: `app/llm/rag/pipelines/naive_v1.py`

Cấu hình đầy đủ của một lần trả lời. Trình tự trong `answer()`:

1. `retrieve(question)` → top_k (=5) chunk, bấm giờ `retrieval_ms`.
2. **Không có chunk nào → trả refusal luôn, không gọi LLM.**
   Không có context thì refusal là output duy nhất đúng; bỏ tiền gọi model chỉ để nhận
   lại đúng câu đó là thêm một đường để chạy hỏng. Đây là case thật với nhóm câu hỏi
   `unanswerable` trên corpus 8 tài liệu, không phải nhánh phòng thủ thừa.
3. Render `answer_v1.jinja` với `question`, `chunks`, `refusal_marker`.
4. Gọi LLM **đúng một lần**.
5. `parse_citations(response.text, chunks)`.
6. Gói tất cả vào `RAGAnswer` — kèm `retrieved` (chunk đầy đủ, không chỉ id),
   `retrieval_ms`, `generation_ms`, `latency_ms`.

Cố ý **không có**: rerank, viết lại truy vấn, ngưỡng điểm, fallback khi retrieval kém.
Đây là mốc tham chiếu, không phải sản phẩm.

> ⚠️ File này **đã đóng băng** kể từ khi `results/naive-v1.json` được commit.
> Ý tưởng mới = file mới + tên mới trong registry. Sửa file này là phá mất điểm cố định
> duy nhất mà cả dự án dùng để đo (CLAUDE.md 4.1 và 5.4).

### Bước 4 — Retriever: `app/llm/rag/retrievers/dense.py`

```python
vector = await self._embedder.embed_query(question)
if len(vector) != self._embedder.dimensions:   # phải là 768
    raise RetrievalFailed(...)
hits = await self._store.search(vector, k)
```

Điều không thương lượng: câu hỏi phải được embed **bằng đúng model và đúng số chiều** mà
corpus đã dùng. Corpus 768 chiều bị truy vấn bằng vector 3072 chiều thì nhẹ là lỗi DB,
nặng là ranking vô nghĩa mà không ai biết — nên check này viết tường minh chứ không tin
vào config.

Pipeline **nhận** retriever qua constructor, không tự tạo (CLAUDE.md 4.3). `bm25.py`,
`hybrid.py`, `reranker.py` là phase 6, mỗi cái một pipeline riêng với results riêng.

### Bước 5 — Vector store: `app/llm/rag/vector_store.py`

Module này **không chứa SQL**. Nó là một Protocol cộng adapter mỏng trên
`DocumentRepository` — giữ nguyên luật "chỉ `repositories/` được viết query" (ADR-0003)
mà vẫn cho retriever cái interface nó cần. Sẽ không bao giờ có bản Qdrant.

### Bước 6 — SQL thật: `app/repositories/document_repo.py::search_similar`

```sql
SELECT chunks.id, chunks.document_id, documents.filename,
       chunks.page_no, chunks.chunk_index, chunks.content,
       chunks.embedding <=> :query_vector AS distance
FROM chunks JOIN documents ON documents.id = chunks.document_id
WHERE chunks.embedding IS NOT NULL
ORDER BY distance
LIMIT :top_k
```

- `<=>` là **cosine distance** — đúng toán tử mà index `ix_chunks_embedding_hnsw` được
  dựng cho. Order by bất cứ thứ gì khác là mất index, tụt về sequential scan.
- JOIN `documents` để lấy `filename`, vì citation cần tên tệp chứ không cần id.
- Điểm trả về là `score = 1.0 - distance`, tức càng cao càng giống.

### Bước 7 — Prompt: `app/llm/prompts/answer_v1.jinja`

Năm quy tắc bắt buộc, viết bằng tiếng Việt:

1. Chỉ dùng nội dung trong phần TÀI LIỆU. Không kiến thức ngoài, không suy đoán, không
   dựa vào luật lao động chung.
2. Ghi nguồn sau mỗi thông tin, đúng dạng `[tên tệp, p.số trang]`.
3. Không đủ thông tin → trả **đúng một câu** refusal, không thêm gì.
4. Chỉ trả lời được một phần → nêu phần có kèm trích dẫn, rồi nói rõ phần nào không có.
5. Tiếng Việt, ngắn gọn, đi thẳng vào con số và điều kiện.

Chunk được nối vào dưới header `--- [tên tệp, p.N] ---` để model có sẵn đúng chuỗi cần
trích dẫn.

**Câu refusal được inject vào qua biến `refusal_marker`, không gõ cứng trong file.**
Runner phát hiện refusal bằng so chuỗi, nên một bản sao của câu đó nằm trong template sẽ
để prompt và detector trôi xa nhau lúc nào không hay.

Prompt không bao giờ viết inline trong code, và đổi prompt = file mới (`answer_v2.jinja`).

### Bước 8 — LLM client: `app/llm/client.py`

Một lớp mỏng trên LiteLLM. Có retry với backoff cho lỗi transport và rate-limit.

Một chỗ tinh tế: **completion rỗng bị raise thành lỗi, không trả về như answer rỗng.**
Chuỗi rỗng đi qua judge trông y hệt một refusal, và sẽ lặng lẽ trở thành điểm
`refusal_accuracy` đạt cho một câu hỏi mà hệ thống chưa từng thực sự trả lời.

`gpt-5.6-luna` từ chối `temperature=0`, nên `LLM_SUPPORTS_TEMPERATURE=false` và results
ghi `temperature: null` (ADR-0008).

### Bước 9 — Citation và refusal: `app/llm/rag/pipelines/base.py`

Ba thứ nằm ở đây thay vì trong pipeline, vì **mọi pipeline và eval runner phải thống
nhất tuyệt đối** về chúng:

**`REFUSAL_MARKER`** — `"Không tìm thấy thông tin trong tài liệu."`
Đổi câu này là đổi ý nghĩa của mọi con số refusal đã commit, nên nó chỉ đổi kèm prompt
version mới và tên pipeline mới.

**`is_refusal()`** — so **substring sau khi normalize** (NFC + casefold + gộp khoảng
trắng), không so `==`. Model hay thêm một câu giải thích phía sau; bắt khớp tuyệt đối sẽ
chấm một lần từ chối trung thực thành hallucination. Normalize trước để một dấu cách thừa
hay một dấu tiếng Việt bị phân rã không quyết định được một metric.

**`parse_citations()`** — regex bắt `[tên tệp, p.N]` (chấp cả `tr.`/`trang`, và `p.?`
cho chunk DOCX không có phân trang thật), rồi đối chiếu `(filename, page_no)` với chính
những chunk vừa retrieve, khôi phục `chunk_id` để phase 5 bấm vào được.

> Citation không khớp gì trong context **vẫn được giữ lại**, với `supported=False`.
> Đó là nguồn bịa — thất bại giàu thông tin nhất mà dự án này ghi được. Vứt nó đi là xoá
> luôn bằng chứng.

---

## 3. Hai điều dễ quên

**Eval đi cùng một đường.** `eval/runner.py` cũng lấy pipeline qua `build_pipeline`, cũng
dùng `parse_citations` và `is_refusal` ở `base.py`. Nhờ vậy con số trong
`results/naive-v1.json` là con số của đúng thứ mà API đang phục vụ, chứ không phải của
một bản sao song song.

**Đổi pipeline không cần sửa code.** Thêm file trong `pipelines/`, `@register("ten-moi")`,
thêm một dòng import trong `__init__.py`, đổi `PIPELINE_NAME` trong `.env`. Registry chặn
hai lỗi ngay lúc import: trùng tên, và `cls.name` khác tên đăng ký (nếu lệch thì câu trả
lời của pipeline này sẽ rơi vào file results của pipeline kia).
