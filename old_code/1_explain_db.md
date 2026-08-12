# Giải thích database của rag-chatbot

> Ghi lại toàn bộ nội dung buổi trao đổi giải thích schema. Gồm 2 phần:
> **Phần 1** — bản chi tiết (tiếng Anh gốc, đi theo từng bảng/cột).
> **Phần 2** — bản giải thích dễ hiểu bằng tiếng Việt, tập trung vào file migration.
>
> Nguồn: `backend/app/models/`, `backend/alembic/versions/42f575d6dccb_initial_schema_documents_chunks_queries.py`,
> `backend/app/db/base.py`, `backend/app/repositories/document_repo.py`.

---

# PHẦN 1 — Bản chi tiết

Three tables, defined in `backend/app/models/` and created by one migration:
`backend/alembic/versions/42f575d6dccb_initial_schema_documents_chunks_queries.py`.

## The shape

```
documents  ──1:N──>  chunks
   (one file)         (one slice of text + its 768-dim vector)

queries    ──"soft" link──>  chunks   (array of ids, NO foreign key)
```

Only **one real foreign key exists in the whole schema**: `chunks.document_id → documents.id`.
That's worth noticing — it tells you the design intent.

---

## 1. `documents` — one row per ingested file

`backend/app/models/document.py`

| Column | Why it exists |
|---|---|
| `id` | PK |
| `filename`, `source_path` | where it came from; `filename` is half of a citation |
| `file_hash` | **SHA-256 of file content, UNIQUE + indexed** |
| `mime_type` | pdf vs docx → picks the loader |
| `page_count` | nullable — DOCX has no real pages |
| `status` | `pending / processing / done / failed` |
| `error_message` | filled when `status='failed'` |
| `created_at` | from `TimestampMixin`, DB-side `now()` |

`file_hash` is the interesting one. It's the **idempotency key**: re-running `make ingest` on the
same folder hashes each file, finds the existing row, and skips it. That's how CLAUDE.md's
"ingest is idempotent" rule is actually enforced — at the database level, by a unique index, not
by application logic that could drift.

`status` is a `String(16)` plus a `CHECK` constraint rather than a Postgres `ENUM` type. The
comment in the model explains the trade-off: adding a new status later is a one-line constraint
swap instead of `ALTER TYPE`.

## 2. `chunks` — the actual retrieval unit

`backend/app/models/chunk.py`

| Column | Why it exists |
|---|---|
| `id` | PK |
| `document_id` | FK → `documents.id`, **`ON DELETE CASCADE`** |
| `content` | the ~800-token text slice; this is what goes into the LLM prompt |
| `page_no` | nullable — **the other half of a citation** |
| `chunk_index` | 0,1,2… order within the document |
| `token_count` | for budgeting the prompt |
| `embedding` | `Vector(768)`, nullable |

Three things to understand here:

**The cascade.** `ondelete="CASCADE"` on the DB side, `cascade="all, delete-orphan",
passive_deletes=True` on the ORM side. Deleting a document deletes its chunks, and
`passive_deletes=True` means SQLAlchemy lets Postgres do it in one statement instead of loading
every child row into Python first. Re-ingesting with `--force` uses this.

**`page_no` is why the project exists.** The stated goal is answers with citations (document name
+ page). `documents.filename` + `chunks.page_no` is that citation. It's nullable purely because
DOCX has no pagination — that nullability is a known gap, not an oversight.

**`embedding` is nullable.** A chunk can exist before it has been embedded. That splits ingest
into two phases and means a crashed embedding run leaves recoverable state rather than losing the
parsed text.

Two indexes beyond the FK:

```python
Index("ix_chunks_embedding_hnsw", "embedding",
      postgresql_using="hnsw",
      postgresql_with={"m": 16, "ef_construction": 64},
      postgresql_ops={"embedding": "vector_cosine_ops"})
```

HNSW with **cosine** ops, matching the `embedding <=> query` operator the dense retriever uses. If
the opclass and the query operator disagree, Postgres silently ignores the index and does a full
scan — so these two must stay in sync. The migration comment notes HNSW was chosen over IVFFlat
specifically because it's incremental: it can be built on an empty table and stays valid as rows
arrive, whereas IVFFlat would need a rebuild after ingest to get useful centroids.

```python
Index("ix_chunks_document_id_chunk_index", "document_id", "chunk_index", unique=True)
```

A `UNIQUE(document_id, chunk_index)` — second line of defence on idempotency. Even if the hash
check were bypassed, you physically cannot insert chunk #3 of document 7 twice.

## 3. `queries` — the observability table

`backend/app/models/query.py`

| Column | Why |
|---|---|
| `question` | what the user actually asked |
| `answer` | nullable — failures are still worth recording |
| `pipeline_name` | indexed; ties an answer to the pipeline that produced it |
| `retrieved_chunk_ids` | `ARRAY(Integer)` — **no FK** |
| `latency_ms` | nullable |

This table is **not connected by a foreign key on purpose**, and the docstring says why: chunks
get deleted and recreated by re-ingests, so a real FK would either block the re-ingest or
cascade-delete your query history. Holding ids that may no longer resolve is judged less bad than
losing the trace. That's a deliberate integrity-vs-history trade-off.

`pipeline_name` is what makes CLAUDE.md §4.1 work — every pipeline is a named, immutable
configuration, so a bad answer in production can be attributed to a specific one.

---

## The 768 that lives in three places

`EMBEDDING_DIM = 768` appears in the model, in the migration, and as `EMBEDDING_DIMENSIONS` in
`.env`. It's duplicated because a Postgres column type cannot be resolved from runtime config at
migration time. All three must change together, and changing them means: a migration + a full
re-ingest + a re-run of every pipeline. That's the practical cost of having switched from OpenAI's
1536-dim model to Gemini's 768-dim one (ADR-0002).

## How a query moves through them

**Ingest:** hash file → check `documents.file_hash` → insert `documents` row (`pending`) → parse →
insert `chunks` with `page_no` → embed → fill `chunks.embedding` → set `documents.status='done'`.

**Ask:** embed the question → `ORDER BY embedding <=> $1 LIMIT 5` on `chunks` (hits the HNSW index)
→ **join back to `documents`** for `filename` → build a prompt from `chunk.content` → LLM answers →
cite `filename` + `page_no` → write a `queries` row.

That join is the one place all three concepts meet: the vector lives on the chunk, but the
citation needs the parent document's name.

## Where it's queried from

All of it goes through `backend/app/repositories/document_repo.py` — `get_by_hash`, `add_chunks`,
`search_similar`, `delete_chunks`, etc. Per CLAUDE.md §4.2, that's the only layer allowed to touch
a session or write SQL; services call the repo, never the ORM directly. Note there is no
`chunk_repo.py` — chunks are only ever reached through their document, which matches how the data
is actually shaped.

---
---

# PHẦN 2 — Giải thích dễ hiểu (tiếng Việt)

## File migration là cái gì?

File migration là **"bản hướng dẫn xây database"**. Bạn không tự vào Postgres gõ `CREATE TABLE`.
Bạn viết file này, chạy `make migrate`, Alembic đọc và tạo bảng giúp bạn.

Nó có 2 hàm:
- `upgrade()` — xây database lên (tạo bảng)
- `downgrade()` — phá đi (xoá bảng), để lỡ sai còn quay lại được

Dòng `down_revision = None` nghĩa là: **đây là bản đầu tiên**, phía trước không có gì cả.

---

## 3 cái bảng, hiểu như thế này

Tưởng tượng bạn có một tủ hồ sơ công ty:

**`documents` = danh sách các file PDF/DOCX bạn đã nạp vào**
Mỗi dòng là 1 file. Tên file, đường dẫn, bao nhiêu trang, đã xử lý xong chưa.

**`chunks` = từng mẩu nhỏ cắt ra từ file đó**
1 file PDF 50 trang → cắt thành ~200 mẩu, mỗi mẩu ~800 chữ. Mỗi mẩu nhớ nó nằm ở **trang mấy**.
Mỗi mẩu có 1 dãy 768 số (embedding) — đó là "ý nghĩa" của đoạn text được mã hoá thành số.

**`queries` = nhật ký câu hỏi**
Ai hỏi gì, máy trả lời gì, lâu bao nhiêu ms.

Quan hệ:
```
1 documents  ──có nhiều──>  chunks
```
Chỉ có **đúng 1 khoá ngoại (foreign key)** trong cả database: `chunks.document_id` trỏ về
`documents.id`. Đơn giản vậy thôi.

---

## Vài dòng "lạ" trong file, giải thích từng cái

**`op.execute("CREATE EXTENSION IF NOT EXISTS vector")`**
Postgres bình thường không biết lưu vector. Dòng này bật thêm module `pgvector` vào. Phải chạy
**trước** khi tạo bảng `chunks`, vì bảng đó có cột kiểu `Vector`. Giống như phải cài app trước rồi
mới mở được file của nó.

**`Vector(768)`**
Cột chứa 768 con số. Con số 768 này nằm ở **3 chỗ** (file migration, `app/models/chunk.py`, và
`.env`) và **phải giống nhau**. Vì sao phải chép 3 lần? Vì lúc tạo bảng, Postgres cần biết ngay
con số cụ thể — không thể đọc từ config lúc chạy được.

Đổi số này = phải làm lại migration + nạp lại toàn bộ tài liệu + chạy lại mọi pipeline. Nên đừng
đụng vào.

**`ondelete="CASCADE"`**
Xoá 1 document → Postgres tự động xoá sạch chunks của nó. Không để lại rác.

**`unique=True` ở `file_hash`**
Đây là chỗ chống trùng. Mỗi file được băm ra 1 chuỗi 64 ký tự. Chạy `make ingest` 2 lần trên cùng
thư mục → lần 2 thấy hash đã tồn tại → bỏ qua, không nạp lại. Database ép buộc điều này, chứ không
phải code tự nhớ.

**`ix_chunks_document_id_chunk_index` với `unique=True`**
Lớp bảo vệ thứ hai. Không thể tồn tại 2 mẩu cùng là "mẩu số 3 của tài liệu số 7". Về mặt vật lý là
không thể.

**Cái index HNSW (dòng cuối, phức tạp nhất)**
```python
postgresql_using="hnsw",
postgresql_ops={"embedding": "vector_cosine_ops"},
```
Đây là **index để tìm kiếm vector cho nhanh**. Không có nó, mỗi câu hỏi Postgres phải so sánh với
TẤT CẢ các chunk → chậm.

Chữ `vector_cosine_ops` nghĩa là index này dùng khoảng cách **cosine**. Quan trọng: lúc truy vấn,
code phải dùng toán tử `<=>` (cũng là cosine). **Nếu 2 cái này lệch nhau, Postgres im lặng bỏ qua
index và quét toàn bộ bảng** — vẫn ra kết quả đúng, chỉ là chậm khủng khiếp và không báo lỗi gì.
Đây là cái bẫy dễ dính nhất.

---

## Còn phần comment ở đầu file nói gì?

> "Autogenerated, then hand-edited for three things autogenerate cannot produce"

Nghĩa là: Alembic có lệnh tự sinh migration từ models. Nhưng nó **không tự sinh được 3 thứ**, phải
sửa tay:
1. `CREATE EXTENSION vector`
2. Dòng `import Vector` ở đầu file
3. Cái index HNSW (Alembic không hiểu `vector_cosine_ops`)

Đây là lời nhắc cho người sau: **đừng xoá file này rồi tự sinh lại**, vì 3 thứ đó sẽ mất.

---

## Luồng chạy thực tế

**Khi nạp tài liệu:**
```
băm file → kiểm tra file_hash đã có chưa
   ↓ chưa có
tạo dòng documents (status = pending)
   ↓
đọc PDF, cắt nhỏ → tạo nhiều dòng chunks (nhớ page_no)
   ↓
gọi Gemini để lấy embedding → điền vào chunks.embedding
   ↓
documents.status = done
```

**Khi người dùng hỏi:**
```
câu hỏi → embedding (768 số)
   ↓
tìm trong chunks: ORDER BY embedding <=> câu_hỏi LIMIT 5   ← index HNSW ăn ở đây
   ↓
join sang documents để lấy filename
   ↓
đưa 5 đoạn text cho LLM → trả lời + trích dẫn "file X, trang Y"
   ↓
ghi 1 dòng vào queries
```

Chỗ `join sang documents` là mấu chốt: **vector nằm ở chunk, nhưng tên file để trích dẫn nằm ở
document**. Phải nối 2 bảng mới ra được trích dẫn đầy đủ.

---

## Một điểm thiết kế đáng chú ý

Bảng `queries` có cột `retrieved_chunk_ids` (mảng các id chunk) nhưng **cố tình KHÔNG làm foreign
key**.

Lý do: nạp lại tài liệu sẽ xoá và tạo lại chunks. Nếu có FK thật thì hoặc là không nạp lại được,
hoặc là lịch sử câu hỏi bị xoá theo. Họ chọn: thà giữ id trỏ vào chỗ không còn tồn tại, còn hơn
mất lịch sử.

Đây là đánh đổi có chủ đích, không phải quên.
