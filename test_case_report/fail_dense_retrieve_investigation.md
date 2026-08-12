# Điều tra: dense retrieval trượt chunk chứa câu trả lời

**Ngày:** 2026-08-12 · **Pipeline:** `naive-v1` (dense top-5) · **Trạng thái:** đã chẩn đoán, chưa sửa

> Ca thất bại thật, gặp khi dùng UI. Đây là bằng chứng cho hạng mục ưu tiên số 1 của Phase 6
> trong `PLAN.md`: `bm25.py` + `hybrid.py` (RRF fusion).
>
> **Ẩn danh:** tài liệu dùng trong ca này là một CV cá nhân. Mọi thông tin định danh (họ tên,
> điện thoại, email, liên kết mạng xã hội, tên người tham chiếu, tên tổ chức) đã được lược bỏ.
> Ở dưới nó được gọi là `CV.pdf`, và câu trả lời đúng được gọi là `<TÊN>`. Không tái tạo lại
> nội dung gốc khi trích dẫn ca này.

## Hiện tượng

Nạp một tài liệu mới (`CV.pdf`, 3 trang, 14 chunk, ingest `done`), rồi hỏi bằng tiếng Việt:

```
anh ấy tên đủ là gì
```

Kết quả:

```
Không tìm thấy thông tin trong tài liệu.
pipeline naive-v1 · 2175 ms · 5 chunk được truy xuất · query_id 8
```

Trong khi tên đầy đủ **có thật** trong tài liệu, nằm ngay dòng đầu trang 1.

## Chẩn đoán: retrieval trượt, không phải generation hỏng

Điểm mấu chốt là **"5 chunk được truy xuất"** — đường ống chạy đủ, LLM có context, nhưng
context không chứa câu trả lời.

`queries.retrieved_chunk_ids` của `query_id 8` là `{63, 15, 62, 3, 6}`:

| Hạng | chunk_id | Thuộc tài liệu | Trang | Nội dung |
|---|---|---|---|---|
| 1 | 63 | `CV.pdf` | 3 | Mục REFERENCES — tên **người tham chiếu**, không phải chủ CV |
| 2 | 15 | HR — nghỉ phép | 1 | Chính sách nghỉ phép năm |
| 3 | 62 | `CV.pdf` | 3 | Danh sách PUBLICATIONS |
| 4 | 3 | HR — sổ tay nhân viên | 1 | Bảo hiểm xã hội, y tế |
| 5 | 6 | HR — lương thưởng | 1 | Phụ cấp, làm thêm giờ |

**Câu trả lời nằm ở `chunk_id` 50** (`CV.pdf`, trang 1, `chunk_index` 0) — dòng đầu tiên của
tài liệu, chứa `<TÊN>` kèm khối thông tin liên hệ. **Chunk 50 không lọt vào top-5.**

Vậy LLM đã hành xử **đúng**: prompt yêu cầu chỉ trả lời từ context được đưa, không có thì phát
câu từ chối. Nếu nó trả lời đúng tên trong tình huống này thì đó mới là lỗi nghiêm trọng —
bịa từ trí nhớ mô hình chứ không phải đọc từ tài liệu.

## Vì sao dense retrieval trượt

Ba nguyên nhân cộng dồn:

**1. Câu hỏi gần như không mang nội dung ngữ nghĩa.** *"anh ấy tên đủ là gì"* — `"anh ấy"` là
đại từ không có tiền tố (hệ thống single-turn, không có lượt trước để tham chiếu). Câu này
không chứa từ khoá nào. Vector của nó gần với "văn bản nói về tên người" nói chung, nên hút vào
chunk 63 — mục REFERENCES dày đặc tên người và học hàm — mạnh hơn chunk 50.

**2. Lệch ngôn ngữ.** Câu hỏi tiếng Việt, tài liệu viết bằng tiếng Anh.

**3. Chunk chứa đáp án lại "loãng" về mặt ngữ nghĩa.** Chunk 50 mở đầu bằng tên rồi tới số điện
thoại, email và một loạt URL. Phần lớn token trong khối đó là chuỗi định danh, nên nhúng của nó
gần với "khối thông tin liên hệ" hơn là "tên của một người". Đây là nghịch lý của ca này: chunk
đúng bị chính đáp án làm nhiễu.

Đây đúng điểm yếu `PLAN.md` Phase 6 đã dự đoán cho dense retrieval: **danh từ riêng, mã hiệu,
thuật ngữ nội bộ**. BM25 sẽ bắt được chunk 50 nếu truy vấn chứa đúng chuỗi tên — nhưng câu hỏi
gốc thậm chí không có chuỗi đó, nên xem phần "Giới hạn" bên dưới.

## Quan sát phụ: top_k cứng, không có ngưỡng

**3 trong 5 chunk được truy xuất là tài liệu HR hoàn toàn không liên quan** tới câu hỏi.
`naive-v1` dùng `top_k=5` cố định và **không có ngưỡng điểm**, nên luôn nhồi đủ 5 chunk kể cả
khi chỉ có 1–2 chunk liên quan mơ hồ. Với corpus nhiều chủ đề tách biệt, việc này bơm nhiễu vào
prompt và làm loãng context.

Cùng hiện tượng ở `query_id 7` (`"anh bạn này tên gì"` → `{3, 20, 1, 15, 2}`): **không một chunk
nào thuộc `CV.pdf`**, cả 5 đều là tài liệu HR.

## Cách tái hiện

Cần một tài liệu có tên riêng ở dòng đầu, cùng tồn tại với corpus HR, rồi hỏi bằng đại từ mơ hồ:

```bash
curl -s -X POST localhost:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"question":"anh ấy tên đủ là gì"}' | python3 -m json.tool
```

Kiểm tra chunk nào thực sự được lấy:

```sql
SELECT id, question, retrieved_chunk_ids FROM queries ORDER BY id DESC LIMIT 5;

-- đối chiếu nội dung các chunk đó
SELECT c.id, d.filename, c.page_no, c.chunk_index, left(c.content, 200)
  FROM chunks c JOIN documents d ON d.id = c.document_id
 WHERE c.id IN (...);
```

## Giới hạn của ca này — đọc trước khi dùng làm căn cứ

- **RRF/BM25 chưa chắc cứu được đúng câu hỏi này.** Truy vấn gốc không chứa chuỗi tên, nên BM25
  cũng không có từ khoá để khớp. Ca này chứng minh **dense trượt**, chứ chưa chứng minh
  **hybrid thắng**. Muốn biết thì phải đo, và đó là việc của Phase 6 — không được suy đoán.
  Một biến thể có từ khoá (`"<TÊN> là ai"`) là phép thử tách bạch hai giả thuyết.
- **Một phần lỗi thuộc về câu hỏi, không thuộc về hệ thống.** Đại từ không tiền tố trong hệ
  thống single-turn là câu hỏi thiếu thông tin. Query rewriting (ưu tiên số 4 trong Phase 6) mới
  là thứ nhắm thẳng vào nó, chứ không phải hybrid retrieval.
- **Không có trong golden set.** 29 câu hỏi hiện tại đều nhắm vào corpus HR đông cứng; ca này
  dùng một tài liệu ngoài corpus, nên nó **không được đưa vào bất kỳ `results/*.json` nào**.
  Muốn dùng nó làm thước đo thì phải viết thành câu hỏi trong `golden_qa.v2.jsonl` với tài liệu
  phù hợp — mà v1 thì đông cứng, không sửa (ADR-0005).
- **Tài liệu gây ra ca này đã làm bẩn corpus đông cứng.** Nó nằm ngoài 8 tài liệu HR, nên
  `make validate` FAIL khi nó còn trong DB, và nó cũng bơm nhiễu vào kết quả của các câu hỏi HR
  (thấy rõ ở `query_id` 7 và 8). Xoá nó đi rồi `make validate` trước khi chạy bất kỳ
  `make eval` nào.

## Việc cần làm tiếp

1. Thử biến thể có từ khoá để tách bạch "dense trượt vì thiếu từ khoá" khỏi "câu hỏi quá mơ hồ".
2. Phase 6, ưu tiên 1: `retrievers/bm25.py` + `hybrid.py` (RRF) → `pipelines/hybrid_v2.py`.
   Đổi **đúng 1 biến** so với `naive-v1` (CLAUDE.md 5.4), tên mới, file mới — không sửa
   `naive_v1.py` vì baseline đã commit.
3. Cân nhắc ngưỡng điểm cho retrieval như một pipeline **riêng biệt** — đó là biến thứ hai, không
   được gộp chung với hybrid trong cùng một thí nghiệm.
4. Nếu vấn đề thật sự là đại từ mơ hồ thì đích đến là query rewriting (ưu tiên 4), không phải
   hybrid.

**Lưu ý khi đọc số:** `recall@5` của baseline đã là 0.958, gần hết dư địa, nên hybrid phải chứng
minh giá trị bằng **MRR, nDCG và `answer_relevance`**, không phải recall. `temperature` là `null`
nên chênh lệch nhỏ giữa hai pipeline có thể chỉ là nhiễu.
