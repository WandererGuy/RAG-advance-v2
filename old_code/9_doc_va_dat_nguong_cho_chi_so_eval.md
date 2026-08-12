# Đọc và đặt ngưỡng cho các chỉ số eval

Ghi chú tham khảo, viết tiếp [8_giai_thich_cac_truong_leaderboard.md](8_giai_thich_cac_truong_leaderboard.md).
File số 8 nói **mỗi cột nghĩa là gì**; file này nói **cột nào quan trọng hơn cột nào**, **tại sao
con số hiện tại lạc quan**, và **ngưỡng nào là đạt / không đạt**.

> ⚠️ Các ngưỡng ở mục 3 là **đề xuất, chưa được chốt**. CLAUDE.md và các ADR hiện chưa đặt ngưỡng
> nào. Muốn chúng có hiệu lực thì phải viết thành ADR (`docs/adr/0009-eval-thresholds.md`), không
> phải để trong ghi chú này.

---

## 1. Thứ tự ưu tiên các chỉ số khi eval

Xếp theo mức độ quan trọng với một RAG chatbot nội bộ có citation, và cụ thể cho dự án này.

### Nhóm 1 — Quyết định (an toàn, không đàm phán được)

**1. `hallucinated`** (`metrics.outcomes.hallucinated`, **không lên bảng**)
Số câu hệ thống trả lời một câu hỏi mà corpus không đỡ nổi. Đây là chỉ số duy nhất mà một con số
xấu là **lỗi chặn phát hành**, không phải "cần cải thiện". Một chatbot HR bịa ra chính sách phụ
cấp gây hại nhiều hơn là không trả lời. Tất định, không phải model chấm. Run `naive-v1` = 0, tốt.

**2. `faithful`** (faithfulness)
Cùng loại rủi ro nhưng ở mức trong câu: câu trả lời có bịa chi tiết ngoài chunk không. Đây là chỉ
số chất lượng số 1 mà người dùng thực sự cảm nhận. Điểm yếu: model tự chấm → thổi lên. Coi nó là
**detector hồi quy** (rơi từ 4.9 xuống 4.2 là tín hiệu thật), không phải điểm tuyệt đối.

**3. `unsupported_citations`** (JSON, **không lên bảng**)
Citation trỏ tới file/trang không có trong context = nguồn bịa. Nguy hiểm hơn cả bịa nội dung, vì
citation làm người đọc **ngừng kiểm tra**. Tất định. Phải là 0.

### Nhóm 2 — Chẩn đoán (nói cho bạn biết phải sửa ở đâu)

**4. `recall@k`**
Trần trên của mọi thứ phía sau. Cái gì không retrieve được thì không cách nào trả lời đúng. Đây là
chỉ số tối ưu chính ở Phase 6 (hybrid, reranker), và là chỉ số tất định đáng tin nhất.

**5. `relevance`**
Có trả lời đúng câu được hỏi không. Quan trọng cho tính hữu dụng, nhưng đứng sau faithfulness: câu
trả lời lạc đề gây khó chịu, câu trả lời bịa gây thiệt hại. Cũng bị self-judge.

**6. `over_refusal_rate`** (JSON)
Từ chối câu trả lời được — an toàn nhưng vô dụng. Đây là **cái giá** phải trả cho chỉ số #1. Chỉ
có ý nghĩa khi đọc cặp với `refusal`: siết prompt để hallucination về 0 thì phải kiểm tra cột này
không phình ra.

### Nhóm 3 — Xếp hạng (tinh chỉnh)

**7. `MRR` / `nDCG@k`**
Chỉ đáng nhìn khi `recall@k` đã cao. Recall cao + MRR thấp = đủ thông tin nhưng chunk đúng bị chôn
dưới, nhiễu chen lên trên → đó chính là lúc reranker có tác dụng. Ở dự án này nDCG gần như trùng
thông tin với recall (gain nhị phân, xem file 8 mục 2), nên **MRR đủ dùng, nDCG gần như thừa**.

### Nhóm 4 — Ràng buộc, không phải mục tiêu

**8. `cite ok`**
Chỉ đo *có* citation. Prompt bắt buộc citation nên nó dính 1.000 và gần như không bao giờ dịch
chuyển — giá trị chính là để phát hiện khi nó **rơi**.

**9. `p50 ms`**
Kiểm tra ngưỡng, không phải thứ để tối ưu. Miễn dưới ngưỡng chấp nhận được thì không ai quan tâm
2.0s hay 2.4s. Chỉ thành quan trọng khi thêm reranker ở Phase 6 và nó nhảy vọt — lúc đó nhìn
`p95`/`max`, không nhìn `p50`.

### Đọc thực tế

Hai chỉ số quan trọng nhất của dự án này (`hallucinated`, `unsupported_citations`) **không có trên
leaderboard** — chúng chỉ nằm trong `results/naive-v1.json`. Bảng chỉ cho `refusal` ở dạng tỉ lệ
đã gộp.

Nếu chỉ được nhìn 3 con số để quyết một pipeline có tốt hơn không:
**`hallucinated` (phải là 0) → `recall@k` → `faithful`.**

---

## 2. Vì sao `recall@5 = 0.958` là trần trên, không phải kỳ vọng

Con số 0.958 gần như chắc chắn **cao hơn** recall thật khi người thật đặt câu hỏi. Lý do nằm ở
cách golden set được tạo ra (ADR-0004).

### Cơ chế

Agent viết câu hỏi **sau khi** đã đọc corpus. Khi viết một câu hỏi, nó đang nhìn vào một đoạn văn
cụ thể và diễn đạt lại đoạn đó thành câu hỏi. Từ ngữ trong câu hỏi vì thế mang chính từ vựng của
tài liệu.

Retriever hiện tại là `dense` — so khớp bằng độ tương đồng embedding. Câu hỏi càng dùng đúng từ
ngữ của chunk thì embedding càng gần nhau. **Golden set này vô tình được xây theo đúng cách để
retriever dễ ăn điểm nhất.**

Nhân viên thật thì không viết như vậy. Họ hỏi bằng từ của họ:

| Nguồn | Câu hỏi |
|---|---|
| Golden set (agent viết sau khi đọc tài liệu) | *"Mức phụ cấp xăng xe hàng tháng là bao nhiêu?"* — tài liệu có thể đang dùng đúng cụm "phụ cấp xăng xe" |
| Người thật | *"đi làm bằng xe máy có được hỗ trợ tiền xăng không"* |
| Người thật | *"cty có trả tiền đi lại ko"* |

Hai câu sau **cũng phải khớp vào đúng chunk đó**, nhưng khoảng cách từ vựng xa hơn nhiều. Đó là
chỗ dense retrieval hụt, và là chỗ 0.958 không nói cho bạn biết.

Có một vòng lặp nữa làm nó tệ hơn: **`relevant_chunk_ids` cũng do agent gán.** Nhãn "chunk nào là
đúng" được viết bởi cùng một tác nhân, cùng lúc, dựa trên cùng cách hiểu — không có ai độc lập
kiểm tra rằng đó thực sự là chunk mà một người dùng thật cần.

### Nên hiểu 0.958 thế nào

**Không** đọc là "95.8% câu hỏi thật sẽ retrieve đúng". Đọc là:

> *"Trên loại câu hỏi dễ nhất có thể có — câu hỏi diễn đạt lại chính văn bản — retriever đạt
> 0.958. Với câu hỏi thật, đây là trần trên, không phải kỳ vọng."*

Điều này **không làm con số vô dụng**. Nó vẫn hợp lệ cho việc **so sánh** giữa các pipeline: nếu
Phase 6 thêm hybrid retrieval và recall lên 0.98 trên cùng bộ câu hỏi đó, cải thiện là thật. Bias
là hằng số, nó nằm nguyên ở cả hai dòng và triệt tiêu khi lấy hiệu.

Cái không dùng được là mọi **phát biểu tuyệt đối** — "hệ thống lấy đúng tài liệu 96% thời gian"
gửi cho ai đó ngoài dự án là sai lệch.

### Hệ quả cụ thể cho Phase 6

Vì bias tập trung vào **từ vựng**, nó ăn mất phần lớn lợi ích mà BM25 và hybrid retrieval lẽ ra
thể hiện được. Với recall đã 0.958, trần còn lại chỉ **0.042** — một thí nghiệm hybrid gần như
không có chỗ để chứng minh giá trị của nó trên bộ câu hỏi này, **kể cả khi nó thực sự giúp ích
nhiều cho người dùng thật**. Golden set hiện tại đang gần bão hòa với chỉ số retrieval.

Đây chính là lý do ADR-0004 giữ nguyên mục tiêu có `golden_qa.v2.jsonl` do người thật viết, và tại
sao `golden_set_author` là một cột trên leaderboard chứ không phải footnote.

---

## 3. Ngưỡng đề xuất cho từng chỉ số

Nguyên tắc nền: **các ngưỡng cho `faithful`/`relevance`/`recall` chỉ có nghĩa như ngưỡng hồi quy
tương đối, không phải ngưỡng chất lượng tuyệt đối** — vì lý do ở mục 2 (agent-authored) và vì
self-judge (ADR-0006). Nên chúng được tách làm hai loại.

### Loại A — Ngưỡng tuyệt đối (tất định, có nghĩa thật)

Các chỉ số không do model chấm và không bị golden set thổi phồng theo hướng thuận lợi.

| Chỉ số | Tối đa | Chấp nhận tối thiểu | Không đạt |
|---|---|---|---|
| `hallucinated` | 0 | **0** | ≥ 1 |
| `unsupported_citations` | 0 | **0** | ≥ 1 |
| `refusal_accuracy` | 1.000 | **1.000** | < 1.000 |
| `cite ok` | 1.000 | **1.000** | < 1.000 |
| `judge_failures` | 0 | ≤ 2 | > 2 (mean không đáng tin) |
| `failed_questions` | 0 | 0 | ≥ 1 |

Ba dòng đầu **không có vùng đệm**, và đó là điểm mấu chốt. Với 5 câu unanswerable,
`refusal_accuracy` chỉ nhận được các giá trị 0.0 / 0.2 / 0.4 / 0.6 / 0.8 / 1.0. Một câu hallucinate
làm nó tụt thẳng xuống 0.8. Đặt ngưỡng "≥ 0.9" là **vô nghĩa về mặt số học** — không có giá trị
nào nằm giữa. Ngưỡng đúng là: *bất kỳ hallucination nào cũng là không đạt*, và đi đọc câu đó trong
`questions[]` chứ không thương lượng với con số.

`cite ok` tương tự: prompt **bắt buộc** citation, nên bất kỳ giá trị nào < 1.000 không phải "hơi
kém", nó là bằng chứng prompt hoặc parser đang hỏng.

### Loại B — Ngưỡng tương đối (so với baseline, không đọc tuyệt đối)

Câu hỏi đúng không phải "0.958 có tốt không" mà là "**so với `naive-v1` thì thế nào**".

| Chỉ số | Baseline `naive-v1` | Đạt | Không đạt (hồi quy) |
|---|---|---|---|
| `recall@5` | 0.958 | ≥ 0.958 | < 0.93 |
| `MRR` | 0.840 | ≥ 0.840 | < 0.80 |
| `faithful` | 4.897 | ≥ 4.80 | < 4.70 |
| `relevance` | 4.250 | ≥ 4.25 | < 4.05 |
| `over_refusal_rate` | 0.0417 | ≤ 0.0417 | > 0.084 (2/24) |

Vùng "không đạt" rộng hơn một bậc so với baseline là có lý do: với 24 câu được chấm, **một câu đổi
kết quả ≈ 0.042 recall**. Recall rơi từ 0.958 xuống 0.917 chỉ là *một câu* — hoàn toàn có thể là
nhiễu. Ngưỡng "< 0.93" nghĩa là: rơi một câu thì ghi nhận và xem lại, rơi hai câu thì đó là tín hiệu.

Với `faithful`/`relevance` còn thêm nhiễu của judge: cùng một câu trả lời, judge có thể cho 4 hoặc
5 ở hai lần chạy khác nhau. **Chênh lệch 0.05 trên thang 1–5 với n=29 không phải tín hiệu.** Đừng
ăn mừng vì 4.897 → 4.93.

### `p50 ms` — ngưỡng kiểm tra, không phải ngưỡng tối ưu

| | |
|---|---|
| Tốt | `p50` < 3000ms, `p95` < 6000ms |
| Chấp nhận | `p50` < 5000ms, `p95` < 10000ms |
| Không đạt | `p95` > 10000ms, hoặc `p50` tăng > 2× so với baseline mà không có lý do đã biết |

Baseline: p50 2009 / p95 4112 / max 6600 — thoải mái trong vùng tốt.

Hai lưu ý làm ngưỡng này khác các ngưỡng trên:
- Nó **gồm cả latency API của provider**, nên phụ thuộc mạng và thời điểm chạy. Một run chậm bất
  thường không phải bằng chứng pipeline chậm đi.
- Từ Phase 6, thêm reranker sẽ làm nó tăng **có chủ đích**. Lúc đó tăng latency không phải "không
  đạt" — nó là cái giá, và câu hỏi là recall/MRR có tăng đủ để bù không.

### Ngưỡng meta — phải đúng trước khi đọc bất kỳ ngưỡng nào ở trên

| Trường | Yêu cầu |
|---|---|
| `run` | `full`. **`dirty` = không dùng để so sánh chính thức** — `git_sha` không tái tạo được run |
| `corpus_validated` | `true` |
| `dataset_version` | trùng với dòng đang đem ra so |
| `questions_scored` | 24 (giảm đi = golden set đã đổi, không so được) |
| `question_count` | 29 |

**Dòng `naive-v1` hiện tại trượt cái đầu tiên** — nó là `dirty`. Nghiêm ngặt mà nói, baseline chính
thức chưa tồn tại; cần commit sạch rồi chạy lại `make eval P=naive-v1` để có một dòng `full` làm
mốc so sánh cho Phase 6.

### Nếu chỉ nhớ một quy tắc

**Loại A phải hoàn hảo, loại B chỉ cần không hồi quy.**

Một pipeline mới đạt `recall@5` 0.99 nhưng có 1 hallucination là **không đạt** — không có phép
đánh đổi nào giữa hai loại này. Đó là toàn bộ lý do chúng được tách ra.
