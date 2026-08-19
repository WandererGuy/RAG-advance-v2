# Luồng chat — hai đầu mút: Streamlit và `ChatResponse`

Ghi lại ngày 2026-08-14, trên nhánh `feat/rerank-v1`.

**Phần backend (route → service → pipeline → retriever → SQL → prompt → LLM → citation)
đã có đầy đủ trong [`0012_luong_rag_chat.md`](0012_luong_rag_chat.md).** File này không
chép lại; nó bù đúng hai đoạn mà 0012 dừng lại trước: câu hỏi rời khỏi trình duyệt như
thế nào, và câu trả lời được dịch ra wire format rồi vẽ lên màn hình ra sao.

Nguồn sự thật vẫn là code trong `backend/` và `frontend/app.py`.

---

## 0. Toàn cảnh, để nối hai file

```
Streamlit  →  POST /chat  →  chat_service  →  registry → pipeline
   ▲                                               ↓
   │                                 retriever → embedder → pgvector
   │                                               ↓
   │                                 Jinja prompt → LiteLLM → LLM
   │                                               ↓
   └────  ChatResponse  ←  parse_citations  ←──────┘
        ^^^^^^^^^^^^^^                    (phần giữa: xem 0012)
```

Mỗi câu hỏi tốn **đúng 2 lần gọi ra mạng**: một lần embed câu hỏi, một lần gọi LLM.
Không hơn. Nếu retrieval trả về rỗng thì chỉ còn 1 — LLM không được gọi.

---

## 1. Đầu vào: Streamlit gửi gì

`frontend/app.py:245`

```python
requests.post(f"{API_BASE}/chat", json={"question": question}, timeout=CHAT_TIMEOUT)
```

Chỉ có thế. Frontend là **client của API, không giữ logic nào** (CLAUDE.md mục 3). Không
có chỗ nào trong `frontend/` biết pipeline là gì, chunk là gì, hay embedding là gì — nó
chỉ đọc các field mà API trả về. Đó là lý do đổi pipeline trong `.env` không cần đụng vào
frontend.

Ràng buộc độ dài **nằm ở backend, không ở đây**: `ChatRequest` giới hạn
`max_length=1000` (`app/schemas/chat.py`). Comment trong file nói rõ lý do — đủ dài cho
một câu hỏi chính sách thật, đủ ngắn để không ai đẩy được cả bài luận qua API embedding
trên key của mình. Đặt cái chặn đó ở frontend thì `curl` đi vòng qua được ngay.

Hai lỗi được bắt riêng, không gộp:

| except | Hiển thị | Nghĩa |
|---|---|---|
| `requests.HTTPError` | `detail_of(exc)` | API trả lời, nhưng là 4xx/5xx — đọc field `detail` ra cho người dùng |
| `requests.RequestException` | "Không gọi được API" | Không tới được API: chưa `make api`, sai port, timeout |

Phân biệt được hai cái này là khác biệt giữa "hệ thống hỏng" và "chưa bật server".

---

## 2. Đầu ra: `RAGAnswer` → `ChatResponse`

`app/schemas/chat.py::from_answer` là **chỗ duy nhất** domain object trở thành wire
format. Không bao giờ trả ORM object hay dataclass nội bộ ra route (CLAUDE.md 4.2).

Những gì được chiếu ra ngoài, và vì sao:

**`refused`** — bool, tính bằng `is_refusal(answer)`, tức so chuỗi chứ không phải model
chấm (ADR-0006). Nhờ nó mà refusal đi ra dưới dạng **HTTP 200 kèm một lá cờ**, chứ không
phải 404.

**`chunk_ids`** — *mọi thứ đã truy xuất, theo thứ tự rank*, không chỉ những cái được
trích dẫn. Nên nhìn vào response là thấy model đã bỏ qua bao nhiêu chunk nó được cho.

**`citations[].snippet`** — cắt 300 ký tự (`SNIPPET_CHARS`) từ nội dung chunk. Chunk đầy
đủ dài tới `chunk_size` (800) và sẽ chôn mất câu trả lời nếu render nguyên.
`_snippet()` gộp khoảng trắng trước rồi mới cắt, thêm `…` khi tràn.

**`citations[].supported`** — được **mang ra tận client** chứ không lọc bỏ ở backend.
Comment đầu file nói thẳng phân công: *việc của API là dán nhãn, việc của UI là không vẽ
nó như một nguồn bình thường.*

**`query_id`** — `None` khi câu trả lời đã sinh ra nhưng ghi vào bảng `queries` hỏng.
Người dùng vẫn nhận được câu trả lời (xem `_record()` trong 0012, bước 2).

---

## 3. Render: ba nhóm, không trộn

`frontend/app.py:257-304`

### 3.1. Thân câu trả lời

```python
if answer["refused"]:
    st.warning(answer["answer"])     # vàng — thông tin
else:
    st.markdown(answer["answer"])
```

Refusal tô **`warning`, không phải `error`**, có chủ ý. Khi corpus không phủ câu hỏi thì
từ chối *là* câu trả lời đúng; vẽ nó màu đỏ sẽ dạy người dùng rằng hệ thống vừa hỏng.

### 3.2. Trích dẫn hợp lệ → `st.expander`

```python
supported   = [c for c in answer["citations"] if c["supported"]]
unsupported = [c for c in answer["citations"] if not c["supported"]]
```

Tách ngay từ dòng đầu. Với mỗi cái `supported`: nhãn là `tên tệp — trang N`, mở ra thấy
`snippet`, caption ghi `chunk_id`. `chunk_id` hiện ra để truy vết được ngược về DB —
`make find` và golden set đều nói bằng ngôn ngữ chunk id.

`page_no` có thể là `None` với chunk DOCX (không có phân trang thật), nên nhãn nối thêm
" — trang N" **có điều kiện** thay vì in ra `trang None`.

### 3.3. Trích dẫn bịa → `st.error`

```python
if unsupported:
    st.error("⚠️ Trích dẫn không đối chiếu được với tài liệu đã truy xuất (không nên tin): …")
```

Đây là điểm quan trọng nhất của cả màn hình. Một citation `supported=False` nghĩa là
model trích một tệp/trang **không hề có trong context của chính nó** — nguồn bịa.

Chuỗi giữ-lại-chứ-không-vứt này chạy suốt ba lớp, và chỉ có tác dụng khi cả ba cùng giữ:

```
parse_citations()  giữ lại với supported=False   (base.py — vứt là xoá bằng chứng)
      ↓
ChatResponse       mang cờ ra client              (schemas/chat.py — API dán nhãn)
      ↓
Streamlit          vẽ đỏ, tách hẳn khỏi Trích dẫn (app.py — UI không vẽ như nguồn thường)
      ↓
chat_service       log unsupported_citations=N    (đếm được, không cần mở UI)
```

Chỉ cần một lớp "dọn cho gọn" là cả chuỗi mất tác dụng.

### 3.4. Gợi ý tài liệu — một cái bẫy đã được rào

```python
if expected_source and supported:
    # Only a hint about retrieval, never a verdict on the answer.
```

Các câu hỏi gợi ý trong `SUGGESTED_QUESTIONS` có kèm tệp nguồn dự kiến. Sau khi trả lời,
UI đối chiếu tệp đó với các tệp được trích dẫn: khớp → `st.success`, lệch → `st.info`
(xanh nhạt, **không phải cảnh báo**).

Comment ghi rõ vì sao chỉ là gợi ý: *một câu hỏi hoàn toàn có thể được trả lời đúng từ
một tài liệu khác với tài liệu đã gợi ra nó.* Nếu để cái này thành ✅/❌ thì nó sẽ bị đọc
như một chỉ số chất lượng — mà chỉ số chất lượng thì chỉ có ở `results/*.json`, chạy trên
golden set, không phải ở một dòng màu trên UI (CLAUDE.md 5.8).

### 3.5. Chân trang

```
pipeline `naive-v1` · 3021 ms · 5 chunk được truy xuất · query_id 42
```

Bốn thứ này hiện lên màn hình để một buổi demo không cần mở log: đang chạy pipeline nào,
mất bao lâu, lấy được mấy chunk, và ghi vào DB có thành công không.

---

## 4. Ba điều dễ đọc sai

**Refusal là 200.** Đã nói ở 0012, nhắc lại vì đây là chỗ dễ "sửa cho đúng chuẩn REST"
nhất. `"Không tìm thấy thông tin trong tài liệu."` là câu trả lời quan trọng nhất hệ
thống này sản xuất, không phải một lỗi.

**Score không so được giữa các retriever.** Cosine similarity và `ts_rank_cd` không chung
thang đo; `RetrievedChunk.score` chỉ có nghĩa trong phạm vi retriever sinh ra nó. Đó là
lý do `hybrid.py` fuse bằng **rank** (RRF, K=60) chứ không phải tổng có trọng số các
score. UI vì vậy **không hiển thị score** — hiển thị ra là mời người ta so hai con số
không so được.

**Retrieval tất định, generation thì không.** Cùng code, cùng corpus, hai lần chạy cho
`refusal_accuracy` 0.8 rồi 1.0, trong khi mọi chỉ số retrieval khớp từng byte. Hỏi cùng
một câu hai lần trên UI mà ra hai câu chữ khác nhau là **bình thường** — `gpt-5.6-luna`
từ chối `temperature=0` nên mọi lần gọi đều đang sampling (ADR-0008, ADR-0009). Đừng kết
luận từ một lần chạy, hay từ khoảng cách generation-metric dưới ~0.2.
