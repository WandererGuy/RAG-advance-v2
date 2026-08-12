# Giải thích các trường trong `results/leaderboard.md`

Ghi chú tham khảo. Nguồn sự thật vẫn là code: `backend/eval/report.py` (dựng bảng),
`backend/eval/metrics/retrieval.py` và `backend/eval/metrics/generation.py` (tính số).

`leaderboard.md` được sinh tự động bằng `make report`, đọc **mọi** file `results/*.json`,
mỗi file là một dòng, sắp xếp theo `timestamp` (chạy cũ ở trên, mới ở dưới). **Không sửa tay.**

Bảng hiện tại:

| pipeline | dataset | golden_set_author | recall@k | MRR | nDCG@k | faithful | relevance | refusal | cite ok | p50 ms | run |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `naive-v1` | v1 | agent | 0.958 | 0.840 | 0.857 | 4.897 | 4.250 | 1.000 | 1.000 | 2009 | dirty |

## Bảng ngưỡng — tra nhanh

Mỗi mục bên dưới có một dòng **Ngưỡng** ngay đầu. Tổng hợp lại:

| Chỉ số | Ngưỡng pass | `naive-v1` | Trạng thái |
|---|---|---|---|
| `hallucinated` (JSON) | **= 0** | 0 | ✅ pass |
| `unsupported_citations` (JSON) | **= 0** | 0 | ✅ pass |
| `refusal` | **= 1.000** | 1.000 | ✅ pass |
| `cite ok` | **= 1.000** | 1.000 | ✅ pass |
| `faithful` | ≥ 4.80 | 4.897 | ✅ pass |
| `recall@5` | ≥ 0.958 (baseline) | 0.958 | ✅ pass (là baseline) |
| `MRR` | ≥ 0.840 (baseline) | 0.840 | ✅ pass (là baseline) |
| `nDCG@5` | — (thừa, xem mục 2) | 0.857 | — |
| `relevance` | ≥ 4.25 (baseline) | 4.250 | ✅ pass (là baseline) |
| `over_refusal_rate` (JSON) | ≤ 0.0417 | 0.0417 | ✅ pass (sát biên) |
| `p50 ms` | < 3000 | 2009 | ✅ pass |
| `judge_failures` (JSON) | ≤ 2 | 0 | ✅ pass |
| `failed_questions` (JSON) | = 0 | 0 | ✅ pass |
| **`run`** | **`full`** | **`dirty`** | ❌ **KHÔNG ĐẠT** |

**Tổng: mọi chỉ số chất lượng đều pass, nhưng run không hợp lệ để làm baseline chính thức** vì
`dirty` (mục 7). Cần commit sạch rồi chạy lại `make eval P=naive-v1`.

> ⚠️ Các ngưỡng này là **đề xuất, chưa được chốt** — CLAUDE.md và các ADR chưa đặt ngưỡng nào.
> Muốn chúng có hiệu lực thì phải viết thành ADR. Lý do đằng sau từng con số, và vì sao ngưỡng
> chia làm hai loại (tuyệt đối / tương đối so với baseline), nằm ở
> [9_doc_va_dat_nguong_cho_chi_so_eval.md](9_doc_va_dat_nguong_cho_chi_so_eval.md) mục 3.

**Đọc ngưỡng cho đúng:** các chỉ số ✅ ở trên chia làm hai loại rất khác nhau.
`hallucinated`, `unsupported_citations`, `refusal`, `cite ok` là **ngưỡng tuyệt đối** — tất định,
pass nghĩa là pass thật. `recall`, `MRR`, `faithful`, `relevance` là **ngưỡng tương đối** — chúng
"pass" chỉ vì đang *là* baseline; chúng không nói chất lượng tuyệt đối tốt (xem mục 1 và mục 9).

---

## 1. Các cột định danh (ai chạy, chạy trên cái gì)

### `pipeline`
`pipeline_name` trong file JSON — tên đăng ký trong `app/llm/rag/pipelines/registry.py`
(vd. `naive-v1`). Đây là đơn vị so sánh của cả dự án: một dòng = một cấu hình RAG hoàn chỉnh
(chunk_size, top_k, retriever, model, prompt version).

> Một pipeline đã có kết quả trong `results/` là **bất biến**. Muốn thử ý tưởng mới → tạo
> pipeline mới với tên mới, không sửa `naive_v1.py`. Sửa là mất tính so sánh được của bảng này.

### `dataset`
`dataset_version` — phiên bản golden set đã dùng (hiện là `v1`, tức `eval/datasets/golden_qa.v1.jsonl`).

**Hai dòng khác `dataset` thì không so sánh được với nhau.** Khi trong bảng có nhiều hơn một
`dataset_version`, `report.py` tự chèn thêm một dòng cảnh báo ở mục "Reading this table" thay vì
xếp chung một bảng xếp hạng.

### `golden_set_author`
Ai viết các câu hỏi đánh giá. Hiện là `agent` — **do agent tự viết** (ADR-0004).

Đây là cột chứ không phải footnote một cách có chủ ý: leaderboard là thứ người ta copy-paste vào
tin nhắn/slide, và một bảng điểm không có dấu vết ai ra đề chính là cách một con số agent-authored
biến thành "hệ thống đạt 4.6 faithfulness" trong slide của người khác.

Nếu file JSON thiếu trường này, ô hiển thị **`unknown`** (in đậm) — cố ý gây khó chịu.

Hệ quả với các số hiện tại: agent viết câu hỏi *sau khi* đã nhìn corpus, nên câu hỏi bám sát
từ ngữ trong tài liệu → **nhóm retrieval bị thổi phồng nhiều nhất**, `refusal` là cột đáng tin
thấp nhất trong đó. Đọc bảng inflation trong ADR-0004 trước khi trích bất kỳ con số nào.

---

## 2. Nhóm retrieval — `recall@k`, `MRR`, `nDCG@k`

Ba cột này **hoàn toàn tất định**: cùng corpus + cùng câu hỏi + cùng retriever ⇒ cùng con số,
mãi mãi. Không có model, không có network, không có randomness. Khi nhóm này và nhóm judge
(`faithful`/`relevance`) mâu thuẫn về việc pipeline có tốt lên không, **tin nhóm này**.

`k` lấy từ `config.top_k` của chính run đó (hiện `k = 5`), nên tên cột trong file JSON là
`recall@5`, `ndcg@5`.

Ba quyết định định nghĩa lại ý nghĩa của chúng, chốt một lần trong `retrieval.py`:

- **Relevance là nhị phân.** Golden set chỉ nói một chunk là liên quan hoặc không nhắc tới nó,
  không có nhãn theo thang. Gain chỉ là 1 và 0.
- **Câu `unanswerable` bị loại khỏi phép tính**, không tính 0 cũng không tính 1. Tập chunk liên
  quan của chúng rỗng theo định nghĩa nên recall không có mẫu số. Chúng được đo bằng `refusal`.
  Số bị loại nằm ở `metrics.retrieval.questions_excluded` (run hiện tại: **24 câu được chấm,
  5 câu bị loại** trên tổng 29).
- **Chunk id trùng trong ranking là bug, không phải điểm thưởng.** Ranking được khử trùng lặp
  trước khi chấm, nên retriever trả cùng một chunk hai lần không thổi được recall.

### `recall@k` — 0.958

> **Ngưỡng:** ≥ 0.958 (baseline) · hồi quy nếu < 0.93 · **✅ pass** — nhưng đây *là* baseline,
> nên "pass" ở đây chỉ có nghĩa là chưa có gì để so.

Tỉ lệ **chunk liên quan** lọt vào top-k, lấy trung bình trên các câu được chấm.

```
recall@k = |top_k ∩ relevant| / |relevant|
```

Trả lời câu hỏi: *"những mẩu tài liệu cần thiết có được đưa vào prompt không?"* Đây là trần trên
của chất lượng câu trả lời — cái gì không được retrieve thì LLM không thể trả lời đúng, trừ khi
nó bịa.

0.958 = gần như luôn lấy đủ chunk cần thiết. Nhưng xem cảnh báo ở mục 1: câu hỏi do agent viết
từ chính corpus.

⚠️ **Vì sao ngưỡng "không đạt" đặt ở 0.93 chứ không phải 0.95:** chỉ 24 câu được chấm, nên
**một câu đổi kết quả ≈ 0.042 recall**. Rơi từ 0.958 xuống 0.917 chỉ là *một câu* — có thể là
nhiễu. Ngưỡng 0.93 nghĩa là: rơi một câu thì xem lại, rơi hai câu mới là tín hiệu.

### `MRR` — 0.840

> **Ngưỡng:** ≥ 0.840 (baseline) · hồi quy nếu < 0.80 · **✅ pass** (là baseline)

Mean Reciprocal Rank: nghịch đảo thứ hạng của chunk liên quan **đầu tiên**, trung bình trên
các câu. Chunk liên quan đầu tiên ở hạng 1 → 1.0; hạng 2 → 0.5; hạng 3 → 0.333; không có chunk
liên quan nào trong top-k → 0.0.

Cũng bị cắt ở `k` giống hai cột kia — một MRR tính trên ranking không cắt sẽ thưởng cho một hit
ở vị trí 40 mà prompt sinh câu trả lời không bao giờ nhìn thấy.

Trả lời câu hỏi: *"chunk đúng có nằm ở **đầu** danh sách không?"* MRR thấp trong khi recall cao
= đủ thông tin nhưng xếp hạng kém, chunk nhiễu chen lên trên.

### `nDCG@k` — 0.857

> **Ngưỡng:** không đặt. Với gain nhị phân nó gần như trùng thông tin với `recall@k` (xem cảnh
> báo cuối mục này), nên **đặt ngưỡng riêng cho nó là đếm hai lần cùng một tín hiệu**. Theo dõi
> `recall@k` + `MRR` là đủ.

Normalized Discounted Cumulative Gain: DCG của ranking thực chia cho DCG của ranking lý tưởng.

```
DCG   = Σ  1 / log2(vị_trí + 1)   với các vị trí trúng chunk liên quan
ideal = Σ  1 / log2(vị_trí + 1)   với vị_trí = 1..min(|relevant|, k)
nDCG  = DCG / ideal
```

Khác MRR ở chỗ nó tính **mọi** chunk liên quan trong top-k chứ không chỉ chunk đầu tiên, có chiết
khấu theo vị trí.

⚠️ Vì gain nhị phân (xem trên), **nDCG ở đây thực chất là recall có trọng số vị trí**, không phải
thước đo chất lượng xếp hạng như nDCG với nhãn theo thang. Đừng mô tả nó như nDCG "đầy đủ".

---

## 3. Nhóm generation — `faithful`, `relevance`

Hai cột này là **ý kiến của một model**, thang **1–5** (không phải 0–1 như các cột khác — 4.897
là "gần như tuyệt đối", không phải "489%"). Đọc ADR-0006 trước khi trích.

> **Judge chính là model đã viết câu trả lời.** Dự án chỉ cấu hình một provider, nên
> `gpt-5.6-luna` tự chấm bài của chính nó. Điều đó thổi điểm lên theo một hướng đã biết, và vẫn
> đáng làm: điểm tự chấm vẫn *dịch chuyển* khi pipeline tốt lên, đó là tất cả những gì Phase 6
> cần. Cột `judge_model` trong JSON ghi lại model đã dùng; `--judge-model` cho phép ghi đè.

Judge trả JSON không parse được → điểm là `None`, **không bao giờ là giá trị mặc định**. Một con
3/5 âm thầm cho một lần gọi thất bại sẽ không phân biệt được với một câu trả lời trung bình thật.
Số lần thất bại nằm cạnh mean trong JSON (`scored` / `failed` / `judge_failures`), không lên bảng.
Điểm ngoài khoảng 1–5 bị coi là thất bại chứ không bị kẹp về biên — kẹp một con 7 thành 5 sẽ âm
thầm kéo mean lên.

### `faithful` — 4.897 (`metrics.faithfulness.mean`)

> **Ngưỡng:** ≥ 4.80 · hồi quy nếu < 4.70 · **✅ pass**
> Ngưỡng tuyệt đối duy nhất trong nhóm judge, vì đây là chỉ số đo bịa đặt — nhưng vẫn phải đọc
> như detector hồi quy, không phải điểm chất lượng (self-judge).

*Mọi khẳng định trong câu trả lời có được chống đỡ bởi chính các chunk mà câu trả lời đó được
đưa cho không?* Nói cách khác: **đo bịa đặt**, không đo đúng/sai.

Chấm cho **tất cả** 29 câu, kể cả `unanswerable` — một câu trả lời bịa cho câu hỏi corpus không
đỡ nổi chính là thứ metric này tồn tại để bắt, bỏ chúng ra là loại đúng ca nguy hiểm nhất khỏi
phép đo. Run hiện tại: `scored: 29`, `failed: 0`.

### `relevance` — 4.250 (`metrics.answer_relevance.mean`)

> **Ngưỡng:** ≥ 4.25 (baseline) · hồi quy nếu < 4.05 · **✅ pass** (là baseline)

*Câu trả lời có trả lời đúng câu hỏi không*, đối chiếu với `ground_truth` (câu trả lời tham chiếu)
trong golden set.

Chỉ chấm 24 câu (`scored: 24`) — các câu `unanswerable` không có ground truth để đối chiếu.

Faithful cao + relevance thấp hơn = trả lời trung thực với tài liệu nhưng lạc đề hoặc thiếu ý
so với đáp án tham chiếu. Đó đúng là hình dạng của run này (4.897 vs 4.250).

⚠️ **Nhiễu của judge, áp dụng cho cả hai cột:** cùng một câu trả lời, judge có thể cho 4 hoặc 5 ở
hai lần chạy khác nhau. **Chênh lệch 0.05 trên thang 1–5 với n=29 không phải tín hiệu.** Đừng ăn
mừng vì 4.897 → 4.93, và cũng đừng hoảng vì 4.897 → 4.85. Đó là lý do vùng "không đạt" của hai
cột này cách baseline khá xa (0.10–0.20) thay vì sát biên.

---

## 4. `refusal` — 1.000

> **Ngưỡng: = 1.000. Bất kỳ giá trị nào < 1.000 là KHÔNG ĐẠT — lỗi chặn phát hành, không phải
> "cần cải thiện".** · **✅ pass**
>
> **Không có vùng đệm**, và đó là cố ý. Với 5 câu unanswerable, chỉ số này chỉ nhận được các giá
> trị 0.0 / 0.2 / 0.4 / 0.6 / 0.8 / 1.0 — một câu hallucinate làm nó tụt thẳng xuống 0.8. Đặt
> ngưỡng "≥ 0.9" là **vô nghĩa về mặt số học** vì không có giá trị nào nằm giữa. Xuống dưới 1.000
> thì đi đọc câu đó trong `questions[]`, không thương lượng với con số.

`metrics.refusal_accuracy`. **Tất định, không phải do model chấm** — đây là con số duy nhất trong
nhóm generation không phải ý kiến của ai. `is_refusal()` là phép so khớp **chuỗi chính xác** với
câu từ chối mà `answer_v1.jinja` bắt buộc. Metric an toàn quan trọng nhất của dự án không được
phép phụ thuộc vào tâm trạng của một model.

```
refusal_accuracy = correct_refusal / (correct_refusal + hallucinated)
```

Tức: **trong các câu `unanswerable`, bao nhiêu phần trăm hệ thống đã đúng đắn từ chối.**
1.000 = 5/5 câu unanswerable đều bị từ chối, **0 hallucination**.

`refusal_outcome()` phân loại mỗi câu trả lời thành 4 kết cục — tách riêng vì đó là 4 loại lỗi
khác nhau (JSON, `metrics.outcomes`):

| Kết cục | Câu hỏi loại | Hệ thống làm gì | Ngưỡng | Run này |
|---|---|---|---|---|
| `answered` | trả lời được | trả lời | càng cao càng tốt | 23 ✅ |
| `correct_refusal` | unanswerable | từ chối | = 5 (toàn bộ) | 5 ✅ |
| `hallucinated` | unanswerable | **trả lời** | **= 0, không đàm phán** | 0 ✅ — kết cục tệ nhất dự án này có |
| `over_refusal` | trả lời được | **từ chối** | ≤ 1 | 1 ✅ — an toàn nhưng vô dụng |

Chỉ `refusal_accuracy` lên bảng. Mặt còn lại, `over_refusal_rate` = 1/24 = **0.0417**, chỉ có
trong JSON — **`refusal` 1.000 không có nghĩa là hành vi từ chối hoàn hảo**, nó chỉ nói không có
hallucination. Muốn biết hệ thống có từ chối quá tay không thì phải mở file JSON.

> **Ngưỡng `over_refusal_rate`:** ≤ 0.0417 (baseline, = 1/24) · không đạt nếu ≥ 0.0833 (2/24) ·
> **✅ pass, nhưng sát biên** — chỉ cần thêm **một** câu bị từ chối oan là rơi thẳng sang không đạt.
> Chỉ số này rời rạc như `refusal_accuracy`, không có giá trị nào nằm giữa 1 câu và 2 câu.
>
> Đây là **cái giá** phải trả cho `hallucinated = 0`, nên luôn đọc cặp: siết prompt để hallucination
> về 0 thì phải kiểm tra cột này không phình ra. Một pipeline đạt `refusal` 1.000 bằng cách từ chối
> mọi thứ là vô dụng, và chỉ có chỉ số này bắt được điều đó.

---

## 5. `cite ok` — 1.000

> **Ngưỡng: = 1.000. Bất kỳ giá trị nào < 1.000 là KHÔNG ĐẠT** · **✅ pass**
>
> Không có vùng đệm: prompt **bắt buộc** citation, nên < 1.000 không phải "hơi kém", nó là bằng
> chứng prompt hoặc parser đang hỏng. Vì nó gần như không bao giờ dịch chuyển, giá trị chính của
> cột này là để phát hiện khi nó **rơi** — đây là một ràng buộc, không phải một mục tiêu để tối ưu.

`metrics.citations.citation_rate`. Tất định. Tỉ lệ câu trả lời **không phải từ chối** có mang ít
nhất một citation. Từ chối bị loại khỏi mẫu số vì một câu từ chối lẽ ra không được có citation nào.

```
citation_rate = answers_with_citation / answers_considered   # 23 / 23 = 1.000
```

⚠️ Nó chỉ đo **có citation hay không**, không đo citation **đúng hay không**. Con số kiểm tra
điều đó nằm trong JSON chứ không lên bảng:

- `unsupported_citations` — số citation trỏ tới file/trang **không hề nằm trong context** của
  chính câu trả lời đó, tức nguồn bịa. Đây là loại lỗi dễ được người đọc tin nhất.
  **Ngưỡng: = 0, không đàm phán.** Run này = 0 ✅
- `answers_with_unsupported_citation` — số câu trả lời dính ít nhất một citation như vậy.
  **Ngưỡng: = 0.** Run này = 0 ✅

Run hiện tại cả hai đều bằng **0**, nên `cite ok = 1.000` ở đây thực sự lành.

⚠️ `unsupported_citations` nguy hiểm hơn cả bịa nội dung, vì citation làm người đọc **ngừng kiểm
tra**. Nó thuộc nhóm ngưỡng nghiêm ngặt nhất cùng `hallucinated` — nhưng **không lên leaderboard**,
nên phải chủ động mở JSON mới thấy.

---

## 6. `p50 ms` — 2009

> **Ngưỡng:** tốt nếu `p50` < 3000 và `p95` < 6000 · chấp nhận nếu `p50` < 5000 và `p95` < 10000 ·
> không đạt nếu `p95` > 10000, hoặc `p50` tăng > 2× baseline mà không có lý do đã biết ·
> **✅ pass** (p50 2009 / p95 4112 / max 6600 — thoải mái trong vùng tốt)
>
> Đây là **ngưỡng kiểm tra, không phải ngưỡng tối ưu**: miễn dưới ngưỡng thì không ai quan tâm
> 2.0s hay 2.4s. Hai lưu ý làm nó khác mọi ngưỡng khác trong file này — (1) nó gồm cả latency API
> của provider nên một run chậm bất thường không phải bằng chứng pipeline chậm đi; (2) từ Phase 6,
> thêm reranker sẽ làm nó tăng **có chủ đích**, lúc đó tăng latency không phải "không đạt" mà là
> cái giá, và câu hỏi là recall/MRR có tăng đủ để bù không.

`metrics.latency_ms.p50` — trung vị độ trễ end-to-end một câu hỏi (retrieve + sinh câu trả lời),
mili-giây. Trung vị chứ không phải trung bình, nên một câu chậm bất thường không kéo lệch.

JSON còn có `p95: 4112` và `max: 6600` (~6.6 giây cho câu chậm nhất) — cả hai đều không lên bảng.
Khi so sánh trải nghiệm người dùng thực, đuôi phân phối mới là thứ đáng nhìn.

Lưu ý: đây là độ trễ đo trong lúc chạy eval, không phải dưới tải; nó gồm cả latency API của
provider nên phụ thuộc mạng và thời điểm chạy. Không phải benchmark hiệu năng.

---

## 7. `run` — `dirty`

> **Ngưỡng: `full`. Mọi giá trị khác là KHÔNG ĐẠT** — không phải vì chất lượng kém, mà vì run
> **không hợp lệ để đem so sánh**. · ❌ **KHÔNG ĐẠT — đây là chỉ số duy nhất trong file này chưa pass**
>
> Đây là ngưỡng phải kiểm tra **trước tiên**: nếu `run` không phải `full` thì mọi ô còn lại trên
> dòng đó không dùng được làm mốc, dù chúng đẹp đến đâu.

Cột trung thực. Mặc định là `full`; nếu không, nó liệt kê các cờ cảnh báo, nối bằng dấu phẩy.
Cả một run một phần lẫn một run đầy đủ đều trông giống hệt nhau một khi đã thành một dòng trong
bảng — cột này ngăn điều đó.

| Giá trị | Nguồn trong JSON | Nghĩa |
|---|---|---|
| `full` | (không cờ nào) | Chạy đầy đủ, corpus đã validate, code sạch |
| `partial(N)` | `partial_run.limit` | Chạy với `--limit N`, **không phải toàn bộ golden set** |
| `unvalidated` | `corpus_validated: false` | Corpus chưa qua `make validate` — có thể đã lệch khỏi `corpus.lock.json` (ADR-0005) |
| `dirty` | `git_dirty: true` | Working tree có thay đổi chưa commit lúc chạy → **`git_sha` không tái tạo lại được run này** |
| `N failed` | `failed_questions` | N câu hỏi lỗi hoàn toàn và bị loại |

Dòng `naive-v1` đang là **`dirty`**: nó chạy lúc working tree bẩn, nên `git_sha`
`f4ab0d4...` không mô tả chính xác code đã sinh ra con số này. Muốn có một dòng `full` thì
commit trước rồi `make eval P=naive-v1` lại.

**Hệ quả:** nghiêm ngặt mà nói, **baseline chính thức của dự án chưa tồn tại.** Mọi ngưỡng
"≥ baseline" trong file này đang neo vào một run không tái tạo được. Đây là việc cần làm trước
khi bắt đầu các thí nghiệm Phase 6, nếu không thì dòng thứ hai trên leaderboard sẽ đem so với
một mốc không đáng tin.

### Ngưỡng meta — phải đúng trước khi đọc bất kỳ ngưỡng nào khác

| Trường | Yêu cầu | `naive-v1` |
|---|---|---|
| `run` | `full` | ❌ `dirty` |
| `corpus_validated` | `true` | ✅ true |
| `dataset_version` | trùng dòng đem ra so | ✅ v1 |
| `questions_scored` | 24 (giảm đi = golden set đã đổi) | ✅ 24 |
| `question_count` | 29 | ✅ 29 |

---

## 8. Những trường có trong JSON nhưng không lên bảng

Bảng cố ý hẹp. Trước khi trích một con số, mở `results/<pipeline>.json`:

- `config.*` — `chunk_size` 800, `chunk_overlap` 100, `top_k` 5, `retriever` `dense`,
  `embedding_model`, `embedding_dimensions` 768, `llm_model`, `prompt_version`. Đây là các biến
  mà từ Phase 6 trở đi **mỗi thí nghiệm chỉ được đổi đúng 1** (CLAUDE.md rule 4).
- `config.temperature: null` — luna từ chối `temperature=0`, nên trường này là `null` chứ không
  phải 0 (ADR-0008). Judge thì vẫn được gọi với `temperature=0.0`.
- `judge_is_answer_model: true` — cờ khiến `report.py` in ra dòng cảnh báo self-judge.
- `question_count` 29 / `failed_questions` 0 (**ngưỡng: = 0** ✅) / `elapsed_seconds` 154.2.
- `metrics.retrieval.questions_scored` 24 và `questions_excluded` 5 — **mẫu số thật của nhóm
  retrieval**. Người đọc tưởng recall phủ toàn bộ dataset là đang đọc một con số khác.
- `metrics.faithfulness.{scored,failed}`, `answer_relevance.{scored,failed}`, `judge_failures` —
  một mean trên 3/29 không phải là điểm số. **Ngưỡng `judge_failures`: ≤ 2**, trên mức đó thì mean
  không đáng tin. Run này = 0 ✅
- `over_refusal_rate` (**ngưỡng ≤ 0.0417, pass sát biên**), `metrics.outcomes.*` (**`hallucinated`
  ngưỡng = 0** ✅) — xem mục 4.
- `metrics.citations.unsupported_citations` — **ngưỡng = 0** ✅, xem mục 5.
- `metrics.latency_ms.{p95,max}` — xem mục 6.
- `questions[]` — chi tiết từng câu: ranking, chunk trúng, câu trả lời, lý do của judge. Đây là
  nơi để debug khi một cột tổng hợp trông kỳ lạ.
- `schema_version` 1 — phiên bản định dạng file kết quả.

---

## 9. Đọc bảng này cho đúng — tóm tắt

1. **Chỉ so sánh trong cùng `dataset`.** Khác version golden set thì không so được.
2. **Cột tất định vs cột chủ quan.** Tất định: `recall@k`, `MRR`, `nDCG@k`, `refusal`, `cite ok`,
   `p50 ms`. Chủ quan (model tự chấm): `faithful`, `relevance`. Khi hai nhóm mâu thuẫn, tin nhóm
   tất định.
3. **Thang đo khác nhau.** `faithful`/`relevance` là 1–5. Còn lại là 0–1 (trừ `p50 ms`).
4. **Corpus 8 tài liệu, câu hỏi do agent viết.** So sánh tương đối giữa các pipeline là hợp lệ;
   giá trị tuyệt đối là lạc quan. Đừng bao giờ trích một ô khỏi bảng mà bỏ lại cột
   `golden_set_author`.
5. **Đọc cột `run` trước khi đọc điểm.** Dòng hiện tại là `dirty` — chỉ số duy nhất chưa đạt.
6. **Ngưỡng có hai loại, không đánh đổi được cho nhau.** Loại tuyệt đối (`hallucinated`,
   `unsupported_citations`, `refusal`, `cite ok`) **phải hoàn hảo**; loại tương đối (`recall`,
   `MRR`, `faithful`, `relevance`) **chỉ cần không hồi quy**. Một pipeline mới đạt `recall@5` 0.99
   nhưng có 1 hallucination là **không đạt** — không có phép đánh đổi nào giữa hai loại này.
7. **Hai ngưỡng nghiêm ngặt nhất không có trên bảng.** `hallucinated` và `unsupported_citations`
   chỉ nằm trong `results/*.json`. Không mở JSON = không biết chỉ số quan trọng nhất.
