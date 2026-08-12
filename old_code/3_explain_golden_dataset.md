# Giải thích golden set và các metric đánh giá retrieval

> Ghi lại buổi trao đổi về golden set của Phase 3. Gồm 2 phần:
> **Phần 1** — golden set là gì, format thật của từng dòng, và tại sao nó không chỉ là cặp Q&A.
> **Phần 2** — `recall@k`, `MRR`, `nDCG@k` là gì, tính thế nào, và một cái bẫy khi implement.
>
> Nguồn: `backend/eval/datasets/golden_qa.v1.jsonl`, `backend/eval/datasets/corpus.lock.json`,
> `docs/adr/0004-agent-authored-golden-set.md`, `docs/adr/0005-frozen-corpus-for-the-golden-set.md`,
> `PLAN.md` (dòng 174–190).

---

# PHẦN 1 — Golden set là gì

Câu hỏi ban đầu: *"golden set là 1 cặp q and a đúng không?"*

Gần đúng, nhưng mỗi dòng có **6 field**, không chỉ q + a. File
`backend/eval/datasets/golden_qa.v1.jsonl` là JSONL, 29 dòng, mỗi dòng 1 câu hỏi:

| field | ý nghĩa |
|---|---|
| `id` | `q001`…`q029` |
| `q` | câu hỏi (tiếng Việt) |
| `ground_truth` | câu trả lời đúng — **kèm lý do/ngữ cảnh**, không phải chỉ một con số |
| `relevant_chunk_ids` | chunk nào *phải* được retrieve mới trả lời được |
| `type` | `factual` (16) / `multi_hop` (8) / `unanswerable` (5) |
| `author` | `"agent"` — bắt buộc, theo ADR-0004 |

## Ví dụ thật, mỗi loại một dòng

**`factual` — q001**

```json
{
  "id": "q001",
  "q": "Buổi sáng muộn nhất mấy giờ thì mọi người phải có mặt?",
  "ground_truth": "10:00. Khung giờ bắt buộc có mặt (core hours) là 10:00 - 16:00; giờ bắt đầu được chọn linh hoạt trong khoảng 08:00 - 10:00 và phải làm đủ 8 giờ.",
  "relevant_chunk_ids": [1, 2],
  "type": "factual",
  "author": "agent"
}
```

**`multi_hop` — q017**, cần ≥2 chunk từ 2 tài liệu khác nhau ghép lại mới ra đáp án;
một chunk thôi là trả lời sai:

```json
{
  "id": "q017",
  "q": "Nhân viên chỉ lên văn phòng đúng mức tối thiểu của mô hình kết hợp thì có được nhận phụ cấp đi lại không?",
  "ground_truth": "Không. Mô hình kết hợp yêu cầu có mặt tại văn phòng tối thiểu 02 ngày mỗi tuần, trong khi phụ cấp đi lại 800.000 đồng/tháng chỉ áp dụng cho nhân viên làm việc tại văn phòng từ 3 ngày/tuần.",
  "relevant_chunk_ids": [5, 16],
  "type": "multi_hop",
  "author": "agent"
}
```

**`unanswerable` — q025**, `relevant_chunk_ids` rỗng, đáp án đúng là "không có trong tài liệu":

```json
{
  "id": "q025",
  "q": "Nhân viên nghỉ thai sản 06 tháng thì thưởng cuối năm được tính theo tỷ lệ nào?",
  "ground_truth": "Không có trong tài liệu. Bộ tài liệu quy định thưởng theo tỷ lệ cho người vào làm giữa năm và trường hợp nghỉ việc trước ngày chi thưởng, nhưng không nói cách tính khi nghỉ thai sản. Hệ thống phải trả lời là không tìm thấy thông tin thay vì suy ra một tỷ lệ.",
  "relevant_chunk_ids": [],
  "type": "unanswerable",
  "author": "agent"
}
```

## Hai điểm khiến nó không chỉ là "cặp Q&A"

**1. `relevant_chunk_ids` là phần đo retrieval, tách khỏi phần đo generation.**
Nó cho phép chấm hai thứ khác nhau: retriever có lấy đúng chunk không (recall@k, MRR), và LLM
có trả lời đúng từ chunk đó không. Không có field này thì một câu trả lời đúng do may mắn và
một câu đúng do retrieve chuẩn nhìn giống hệt nhau.

Đây cũng là lý do phải có `corpus.lock.json` (ADR-0005): re-ingest với `FORCE=1` sẽ đánh số lại
chunk id và toàn bộ field này trỏ sai chỗ **trong im lặng**. Lock file ghim `file_hash` của mỗi
tài liệu với đúng dãy chunk id nó sinh ra, cộng một digest của toàn bộ chunk text — `make validate`
biến lỗi vô hình đó thành một failure có tên.

**2. 5 câu `unanswerable` là bẫy hallucination cố ý.**
Câu hỏi nằm **trong** domain và có nội dung lân cận retrieve được (near-miss), nên model rất dễ
suy ra một đáp án nghe hợp lý. Ở q025: tài liệu có nói tỷ lệ thưởng cho người vào giữa năm và
người nghỉ việc trước ngày chi, nhưng **không** nói gì về thai sản. Trả lời "không tìm thấy
thông tin" mới là đúng.

## Provenance — `author: "agent"`

Theo ADR-0004, golden set này do agent viết, không phải người. Ràng buộc đi kèm:

- mỗi dòng **bắt buộc** có `author`; `validate.py` reject dòng thiếu field này,
- `make validate` cảnh báo về việc agent-authored ở **mọi** lần chạy,
- từ Phase 4 trở đi mọi `results/*.json` phải mang `golden_set_author`, và `leaderboard.md`
  hiện nó thành một cột — nên không con số nào của hệ thống được đọc hay trích dẫn mà thiếu
  provenance của bộ câu hỏi sinh ra nó (CLAUDE.md rule 8).

Đọc bảng inflation trong ADR-0004 trước khi trích bất kỳ điểm số nào. Việc một người viết
`golden_qa.v2.jsonl` vẫn là mục tiêu, không phải nice-to-have; ADR nêu rõ các trigger.

---

# PHẦN 2 — `recall@k`, `MRR`, `nDCG@k`

**Chưa được implement.** `backend/eval/metrics/` hiện còn trống; `PLAN.md` dòng 190 xếp
`eval/metrics/retrieval.py` vào Phase 4. Phần dưới là khái niệm, dùng chính dữ liệu golden set ở trên.

Cả hai metric chính đều chấm **retriever**, không chấm câu trả lời. Input là: danh sách chunk id
mà retriever trả về, đã xếp hạng theo điểm số, so với `relevant_chunk_ids` trong golden set.

## Recall@k — "có lấy đủ không"

Trong top-k kết quả, bao nhiêu phần trăm chunk cần thiết đã xuất hiện.

```
recall@k = |top_k ∩ relevant| / |relevant|
```

Lấy q017 (`relevant_chunk_ids: [5, 16]`), `top_k = 5`:

| retriever trả về | recall@5 |
|---|---|
| `[5, 16, 3, 9, 1]` | 2/2 = **1.0** |
| `[5, 3, 9, 1, 7]` | 1/2 = **0.5** |
| `[3, 9, 1, 7, 2]` | 0/2 = **0.0** |

Recall@5 = 0.5 ở một câu multi_hop nghĩa là LLM chỉ nhận được một nửa dữ kiện — nó sẽ trả lời
sai, nhưng nghe rất tự tin. Đây là lý do tách metric: bạn biết lỗi nằm ở retriever chứ không
phải ở prompt.

**Recall@k không quan tâm thứ tự.** `[5, 16, …]` và `[…, 5, 16]` cùng recall = 1.0.

## MRR — "có xếp nó lên đầu không"

Reciprocal Rank = 1 / (vị trí của chunk liên quan **đầu tiên**). MRR = trung bình RR trên toàn
bộ câu hỏi.

| chunk liên quan đầu tiên ở vị trí | RR |
|---|---|
| 1 | 1.0 |
| 2 | 0.5 |
| 3 | 0.333 |
| 5 | 0.2 |
| không có trong top-k | 0 |

Ví dụ 3 câu: RR = 1.0, 0.5, 0.0 → MRR = 1.5/3 = **0.5**.

Thứ tự quan trọng vì `top_k=5` là ngân sách cứng — chunk hạng 6 không bao giờ vào prompt.
MRR cao nghĩa là có thể giảm k: prompt ngắn hơn, ít nhiễu hơn, rẻ hơn.

## Hai cái bổ sung nhau

- **recall cao + MRR thấp** = tìm được nhưng chôn ở cuối → cần reranker (Phase 6).
- **recall thấp** = embedding hoặc chunking sai → reranker không cứu được.

## nDCG@k

`PLAN.md` có liệt kê. Giống MRR ở chỗ phạt theo thứ hạng (chia cho `log2(rank+1)`), nhưng tính
**tất cả** chunk liên quan chứ không chỉ cái đầu tiên — hợp với 8 câu multi_hop, nơi chunk thứ
hai nằm ở hạng 2 hay hạng 5 là khác biệt thật mà MRR bỏ qua.

## Một bẫy cho Phase 4

5 câu `unanswerable` có `relevant_chunk_ids: []`. Recall@k sẽ **chia cho 0**, và MRR không có
"chunk liên quan đầu tiên" để tìm.

**Phải loại chúng khỏi cả hai metric** — chấm trên 24 câu, không phải 29 — rồi đo riêng bằng
abstention rate (tỷ lệ model đúng khi nói "không tìm thấy thông tin").

Nếu gộp chung và cho RR = 0, MRR bị kéo xuống một cách vô nghĩa; nếu cho 1.0 thì được điểm miễn
phí. Cả hai đều làm số không so sánh được giữa các pipeline — mà so sánh được giữa các pipeline
chính là toàn bộ mục đích của `results/`.
