# Bổ sung kỹ thuật — từ `suggestion_rag.txt`

Phần này **chỉ chứa những gì file `6_ky_thuat_rag_chatbot.md` chưa có**. Mọi mục trùng đã được
lược bỏ và ghi lại ở mục 0 để không phải đọc chéo hai file.

Trạng thái tính đến 2026-08-14, commit `a7727e5`, **Phase 0–6 xong**. Ký hiệu giữ nguyên như file 6
(✅ đã có code · 📋 đã trong PLAN Phase 6 · 💡 ý tưởng mới · ⚠️ có nhưng không như tên gọi).

Ý tưởng mới của Mạnh `=))`
- Cho người dùng upload file cá nhân, lưu file trên S3 hoặc thư mục `/tmp` (nhớ ignore khi commit), show progress upload file hoặc 1 trang riêng upload file và upload progress (vì file cần ingest và embed vào DB)
- Judge model LLM-as-judge nên là model khác thông minh hơn hoặc khác provider để khách quan
- Cải thiện golden dataset: các chỉ số đang nói nhiều thứ, ví dụ như golden dataset quá sạch và câu hỏi được lấy từ đọc corpus, nên thêm do người viết
- Quan trọng: các sản phẩm thường có điều kiện nghiệm thu POC, MVP, cần specify nó ra
- Nếu tự tạo 1 tool/frontend để tạo golden dataset thì cũng rất hay, dù manual hay AI generate, rồi người có thể xác nhận, rồi luồng RAG này chạy tự động và sinh điểm
- Xử lí golden dataset bị outdate thông tin kiểu gì?
- Làm cho code trở nên OOP hơn, hiện tại nhiều function đơn lẻ quá chăng
- Thêm observability như Langfuse hoặc Langsmith

---

## 0. Cái gì trong `suggestion_rag.txt` đã có sẵn trong file 6

Đọc mục này trước để khỏi tưởng suggestion đưa ra nhiều thứ mới hơn thực tế.

| Ý trong suggestion | Đã nằm ở đâu trong file 6 |
|---|---|
| Thêm reranker | 2.7 ✅ — **đã làm và đã adopt**, `rerank-v1` là pipeline đang serve (ADR-0010) |
| Rewrite user query | 2.8 📋 — vẫn chưa làm |
| Phân rã query, chạy song song | 2.9 💡 (multi-query + RRF) |
| Agentic RAG, retriever as a tool | 6.2 💡 |
| MCP server, đọc tài liệu là 1 tool | 6.3 💡 |
| OCR / Docling cho PDF scan | 1.13, 1.14, 6.4 💡 |
| Câu trả lời phải có citation | 3.2 ✅ |
| Prompt cấm dùng kiến thức ngoài context | 3.1 ✅ (`answer_v1.jinja`) |
| Từ chối khi không đủ thông tin | 3.3 ✅ (refusal contract là constant) |
| Check citation id có thật không (`4a` trong suggestion) | 3.4 ✅ — **đã làm rồi**, `supported=false` + đếm |
| p95 latency | 4.11 ✅ |
| `tool_call_count`, số lần hop | 4.15 💡 |
| Groundedness bằng LLM-as-judge | 4.4 ✅ (`faithfulness` 1–5) |
| Refusal accuracy trên câu unanswerable | 4.6 ✅ + 4.16/4.17 ✅ (5 câu `unanswerable`) |
| Citation precision | 4.9 / 4.10 ✅ (`citation_rate`, `unsupported_citations`) |

**Kết luận mục 0:** suggestion mô tả "4 lớp chống hallucination" như thứ cần xây; repo **đã có
lớp 1 một phần, lớp 2 một phần, lớp 3 gần đủ, lớp 4 một phần (4a)**. Phần thật sự mới nằm dưới.

---

## 1. Chống hallucination — 4 lớp, phần còn thiếu

### 1.1 Retrieval gate — ngưỡng score trước khi gọi LLM 💡 — **ROI cao nhất trong file này**

Hiện tại `dense.py` luôn trả top-5 bất kể câu hỏi có liên quan corpus hay không. Model buộc
phải nói gì đó, và refusal hoàn toàn phụ thuộc prompt (lớp 3) — tức là phụ thuộc thiện chí của
model. Gate là lớp **không gọi LLM**: không sinh thì không bịa.

Hình dạng đúng với repo hiện tại: `reranker.py` đã bọc một retriever khác và trả về top-k đã
reorder — gate là một lớp bọc nữa ở ngoài cùng, đúng cùng Protocol:

```python
def retrieve_with_gate(query, k=5, min_score=...):
    hits = reranking_retriever.retrieve(query, k)   # dense top-20 -> rerank -> top-5
    if not hits or hits[0].score < min_score:
        return None            # -> refusal, KHÔNG gọi LLM
    return [h for h in hits if h.score >= min_score]
```

`min_score` để trống có chủ ý: nó phải chọn từ dữ liệu (xem hàng "Cách chọn ngưỡng"), và trên
thang cross-encoder chứ không phải cosine.

| | |
|---|---|
| Vì sao hợp repo này | 5 câu `unanswerable` trong golden set là **bộ dữ liệu sẵn có để chọn ngưỡng**, không phải đoán |
| Cách chọn ngưỡng | Chạy eval, vẽ phân bố `ChunkHit.score` của 24 câu có đáp án vs 5 câu unanswerable, chọn điểm cắt, **ghi con số + lý do vào ADR** |
| Rủi ro | Ngưỡng quá cao → `over_refusal_rate` tăng. Repo **đã có sẵn metric đó** (4.8) → đo được ngay hai chiều, không phải đánh đổi mù |
| Chi phí | Thấp. 1 tham số config → 1 pipeline mới `gate-v2` → đúng luật "1 thí nghiệm = 1 biến" |
| Cạm bẫy | `ChunkHit.score` là cosine, `RetrievedChunk.score` là "bất kỳ thứ gì retriever rank theo" (2.4). Ngưỡng gate chỉ có nghĩa **trên đúng thang của retriever đang chạy**. Pipeline đang serve là `rerank-v1` → score cuối là **điểm cross-encoder của Voyage**, không phải cosine và cũng không phải RRF. Ba thang khác nhau, `0.35` không bê được từ thang này sang thang kia |

**Đây là lớp phòng thủ duy nhất trong 4 lớp mà repo hiện chưa có gì cả.**

**Cập nhật sau Phase 6 — điều kiện chọn ngưỡng đã tốt lên:** cross-encoder score có ý nghĩa
tuyệt đối hơn cosine (nó chấm trực tiếp cặp *câu hỏi × chunk* thay vì khoảng cách hai vector độc
lập), nên phân bố "có đáp án" vs "unanswerable" tách bạch hơn → chọn điểm cắt dễ hơn so với thời
điểm viết mục này. Nhưng cũng cẩn thận hơn về **cái đang đo**: baseline `refusal_accuracy` hiện
là 1.000 (`naive-v1`) và 0.800 (`rerank-v1`), và metric này **không tái lập được giữa các lần
chạy** (file 6 mục 3.7). Muốn chứng minh gate có tác dụng thì phải chạy nhiều lần và so phân bố,
chứ không so hai con số đơn lẻ.

### 1.2 Đánh số citation ngay trong context 💡

Hiện prompt bắt model tự viết `[filename, p.N]`. Suggestion đề xuất đánh số sẵn `[1]`, `[2]`
trong context và model chỉ việc copy nhãn:

```
[1] guideline.pdf | trang 3 | mục "Chính sách hoàn tiền"
Khách hàng có thể yêu cầu hoàn tiền trong vòng 14 ngày...

[2] faq.md | trang 1 | mục "Đổi trả"
...
```

| | |
|---|---|
| Lợi | Model copy nhãn có sẵn thay vì tự tạo → giảm citation sai. Parse ngược ở 3.4 thành **exact int match**, hết mọi chuyện fuzzy filename |
| Thêm | Metadata ghi ở **đầu** mỗi chunk, không dồn xuống cuối |
| Ăn khớp | Trường `mục "..."` chính là **breadcrumb (1.10)** — 1.2 và 1.10 dùng chung một dữ liệu |
| Chi phí | Prompt mới `answer_v2.jinja` (luật 3.5: file mới, không sửa tại chỗ) + đổi parser 3.4 + pipeline mới |
| Đánh đổi | API trả `[1]` thì **frontend phải resolve số → chunk** (mục 3.1). UI đẹp hơn nhưng thêm một endpoint |

### 1.3 Structured output JSON + `sufficient` / `confidence` 💡

Bắt model trả JSON thay vì văn xuôi:

```json
{ "sufficient": bool, "answer": str, "citations": [int], "confidence": "high|medium|low" }
```

| | |
|---|---|
| Giá trị | `sufficient: false` là **tín hiệu từ chối có cấu trúc**, không phải string-match câu từ chối |
| Va chạm | 3.3 nói refusal là **constant** và `is_refusal()` match đúng constant đó. Chuyển sang JSON thì `is_refusal()` phải đổi định nghĩa → **đụng metric `refusal_accuracy` (4.6) đang là số safety-critical deterministic**. Phải ghi ADR, không lặng lẽ đổi |
| Khuyến nghị | Baseline đã có (3 cái). Nhưng điều kiện thật sự chưa đủ: `refusal_accuracy` **dao động giữa các lần chạy** (file 6 mục 3.7), nên phải có **phân bố nhiều lần chạy** làm mốc trước, không phải một con số |
| ⚠️ | `confidence` do model tự khai là **self-reported**, gần như vô nghĩa nếu không calibrate. Ghi nó ra results file thì được; dùng nó để chặn/không chặn thì phải chứng minh bằng số |

### 1.4 Quy tắc prompt còn thiếu 💡 — rẻ nhất, làm được ngay

Suggestion nêu 2 quy tắc mà `answer_v1.jinja` nên có (kiểm tra lại file trước khi kết luận thiếu):

- **"Tuyệt đối không dùng kiến thức ngoài CONTEXT, kể cả khi bạn chắc chắn điều đó đúng"** —
  vế sau ("kể cả khi chắc chắn") là vế hay bị bỏ sót. Không có nó, câu kiểu *"chính sách bảo
  hành bao lâu?"* mà context không nói rõ sẽ được điền đại "12 tháng" vì đó là con số phổ biến
  model học được — và câu trả lời nghe rất thuyết phục.
- **"Không suy diễn, không khái quát hóa vượt quá những gì được viết."**
- **Few-shot 1–2 ví dụ về ca từ chối.** Model bắt chước hành vi trong ví dụ mạnh hơn tuân theo
  mô tả trừu tượng.

Chi phí: `answer_v2.jinja`. Đo bằng `faithfulness` + `over_refusal_rate` đã có sẵn.

### 1.5 Post-check bằng regex — phần chưa làm 💡 — **rẻ và ăn điểm**

Repo đã có 4a (citation id có tồn tại không → 3.4). Còn thiếu 4b và 4c:

```python
# 4b. Câu khẳng định nào không có citation?
for sent in split_sentences(resp["answer"]):
    if is_claim(sent) and not re.search(r"\[\d+\]", sent):
        issues.append(f"câu thiếu nguồn: {sent[:50]}")

# 4c. Số liệu trong answer có xuất hiện trong context không?
nums_ans = set(re.findall(r"\d[\d.,]*", resp["answer"]))
nums_ctx = set(re.findall(r"\d[\d.,]*", context_text))
if nums_ans - nums_ctx:
    issues.append(f"số liệu không có trong nguồn: {nums_ans - nums_ctx}")
```

| | |
|---|---|
| **4c là mục đáng làm nhất** | Số liệu (ngày, %, tiền, thời hạn) là dạng hallucination **nguy hiểm nhất** trong tài liệu HR/guideline, và check bằng regex thì gần như miễn phí |
| Metric mới | `flagged_response_rate` — tỉ lệ response bị post-check bắt lỗi |
| Xử lý khi fail | Retry **đúng 1 lần** với `issues` đưa ngược vào prompt; vẫn fail thì hạ xuống refusal kèm cảnh báo. **Đừng retry vô hạn** |
| Cạm bẫy tiếng Việt | `split_sentences` và `is_claim` cho tiếng Việt không tầm thường. 4c (regex số) **không có vấn đề này** → làm 4c trước, 4b sau |
| Cạm bẫy 4c | False positive từ số trong ngày tháng model diễn đạt lại ("14 ngày" → "hai tuần" thì ngược lại là false negative). Normalize tối thiểu, và **báo cáo tỉ lệ flag, đừng tự động chặn** cho đến khi biết precision của chính cái check này |

### 1.6 Bảng "mỗi lớp phòng thủ ↔ một chỉ số chứng minh nó có tác dụng" 💡

Đây là **đóng góp lớn nhất về mặt trình bày** của suggestion: không tách "chống hallucination"
và "đánh giá chất lượng" thành hai gạch đầu dòng, mà trình bày như một khối.

| Lớp | Bắt lỗi gì | Đo bằng | Repo hiện có? |
|---|---|---|---|
| 1. Retrieval gate | Câu hỏi ngoài phạm vi tài liệu | `refusal_accuracy` trên 5 câu unanswerable | Metric ✅ · Gate 💡 |
| 2. Context design | Trộn thông tin giữa các chunk | Citation precision | ✅ (4.9/4.10) |
| 3. Prompt + JSON | Dùng kiến thức ngoài | Groundedness (LLM-as-judge) | ✅ (4.4 faithfulness) |
| 4. Post-check | Bịa số, bịa citation id | Tỉ lệ response bị flag | 4a ✅ · 4b/4c 💡 |

---

## 2. Vận hành & API — nhóm hoàn toàn mới, file 6 không có mục nào

**Phase 5 đã xong** — `POST /chat`, `POST /documents`, `GET /documents`, `GET /health`, và UI
Streamlit (`frontend/app.py`, `make ui`) là client thuần của API. Mục này giữ lại vì phần lớn
vẫn là việc chưa làm; các dòng đã làm được đánh dấu lại.

| # | Kỹ thuật | TT | Chi tiết |
|---|---|---|---|
| 2.1 | **Chat là API streaming** (SSE) | 💡 | Vẫn chưa làm — `POST /chat` hiện trả **một response đầy đủ**. Kéo theo `time_to_first_token`, metric mà eval batch **không đo được**. Đây vẫn là thay đổi contract |
| 2.2 | **Ingest là API + polling progress** | ⚠️ một phần | `POST /documents` **đã có**, và cố tình **giữ synchronous** — request mở đến khi embed xong. `GET /documents` trả `status` + `chunk_count` cho mọi document. Phần **chưa** có là progress theo thời gian thực của một lần upload đang chạy; cái đó mới cần `app/workers/` và **cần ADR** (ADR-0002 đã bác Celery+Redis) |
| 2.3 | **API resolve citation** `GET /chunks/{id}` | ⚠️ đã giải quyết theo cách khác | Không cần endpoint riêng: `POST /chat` trả citation **kèm sẵn** `filename`, `page_no`, `chunk_id` và `snippet`, UI expand ra đọc được ngay. Chỉ cần endpoint riêng nếu làm 1.2 (đánh số `[1]` và trả về số trần) |
| 2.4 | Cho người dùng upload tài liệu để test | ⚠️ đã làm, theo cách rẻ hơn | Upload **đã mở** qua `POST /documents`. Va chạm với ADR-0005 được xử lý không phải bằng cách tách hai search space, mà bằng ba thứ: (a) endpoint **không có tham số `force`** nên không bao giờ đánh lại chunk id, (b) upload trùng bytes là no-op (`status="skipped"`), (c) upload vẫn là đổi corpus → **luật là chạy `make validate` sau mỗi phiên upload**. Tách corpus eval/user (3.4) vẫn là lời giải đúng nếu sau này có nhiều người dùng thật |
| 2.5 | `max_recursive` / `max_loop` cho agentic | 💡 | Điều kiện tiên quyết của 6.2. Không có nó, agentic loop tiêu quota vô hạn — repo **đã đau vì quota** (7.3) |

---

## 3. UX — nhóm hoàn toàn mới

| # | Kỹ thuật | TT | Chi tiết |
|---|---|---|---|
| 3.1 | Citation `[1]` bấm được → xem chunk | ⚠️ đã có bản tương đương | UI Streamlit **đã** render mỗi citation thành một khối expand được: tên file, số trang, `chunk_id` và snippet gốc — người xem tự mở ra kiểm chứng. Khác bản đề xuất ở chỗ dữ liệu đi kèm response chứ không gọi API thứ hai (2.3). UI cũng **hiện riêng citation `supported=false`**, tức là phần hệ thống tự khai mình trích sai |
| 3.2 | Follow-up question bấm được | 💡 | Gợi ý 3 câu tiếp theo. **Cần multi-turn → sau Phase 6** (`llm/memory.py` đang khoá) |
| 3.3 | Selection để user xác nhận / bổ sung dữ kiện | 💡 | Khi query mơ hồ hoặc thiếu dữ kiện, model hỏi lại bằng **lựa chọn bấm được** thay vì text tự do. Cùng họ với 2.8 query rewriting nhưng có human-in-the-loop |
| 3.4 | Cô lập tài liệu bằng search-space table hoặc ACI | 💡 | Nền móng cho permissions. **ADR-0001 chốt v1 không có permissions** — nhưng cột `search_space` trong schema là chi phí thấp *nếu thêm ngay từ đầu*, đắt nếu thêm sau. Xem 2.4 |

---

## 4. Observability sản phẩm — khác hẳn eval, file 6 chưa tách bạch

Ý sắc nhất của suggestion: *"cái này để đánh giá performance tốt hơn cả eval và đánh giá từ
người dùng — vì người dùng lười đánh giá."*

File 6 mục 4 chỉ nói về **eval offline trên golden set 29 câu**. Đây là loại đo hoàn toàn khác:
đo **hệ thống đang chạy**, không cần ai chấm điểm.

| # | Chỉ số | TT | Chi tiết |
|---|---|---|---|
| 4.1 | `time_to_first_token` | 💡 | Chỉ có nghĩa khi có streaming (2.1). Eval batch hiện tại **không định nghĩa được** metric này |
| 4.2 | `end_to_end_answer_time` | 💡 | Khác `latency p95` hiện có (4.11) ở chỗ đo trên **traffic thật**, không phải 29 câu cố định |
| 4.3 | Số lần hop để đạt kết quả | 💡 | = `retrieval_rounds` (4.15) nhưng đo online |
| 4.4 | Số lần gọi tool | 💡 | = `tool_call_count` (4.15) đo online |
| 4.5 | **Visualize thống kê lịch sử người dùng** | 💡 | Dashboard phân bố các số trên. Đây là **thứ file 6 hoàn toàn không có** |
| 4.6 | Tỉ lệ refusal trên traffic thật | 💡 | So với `refusal_accuracy` offline → phát hiện drift giữa golden set và câu hỏi thật. **Đây là lý do mạnh nhất để làm nhóm này** |

**Điều kiện tiên quyết:** phải log per-request có cấu trúc. `core/logging.py` (structlog JSON,
5.8) **đã sẵn sàng** — chỉ cần thêm trường và một bảng/`table` để truy vấn.

**Cảnh báo:** đây là *product analytics*, không thay thế eval. Nó nói **hệ thống đang được dùng
thế nào**, không nói **câu trả lời có đúng không**. Đừng để nó chiếm chỗ của
`results/naive-v1.json` trong câu chuyện.

---

## 5. DeepEval — chuẩn hoá eval 💡

Suggestion đề xuất dùng DeepEval để eval "standardized", với 2 thang đo **chưa cần expected output**.

| | |
|---|---|
| Hai metric không cần ground truth | `Faithfulness` (answer có bám context không) và `AnswerRelevancy` (answer có trả lời đúng câu hỏi không) — **đúng hai thứ repo đã tự viết** ở 4.4/4.5 |
| Lợi | Tên metric chuẩn, người ngoài hiểu ngay; không phải tự bảo vệ định nghĩa của mình |
| **Hại** | Repo đã có **judge prompt versioned** (`faithfulness_v1.jinja`) và **tự khai bias judge = answer model** (ADR-0006, 4.20). DeepEval là **hộp đen hơn**: đổi version thư viện có thể đổi điểm mà results file không ghi được nguyên nhân — **phá thẳng nguyên tắc provenance (4.27)** |
| Khuyến nghị | **Đừng thay** judge tự viết. Nếu làm, chạy **song song** và ghi cả hai vào results file (`faithfulness_own`, `faithfulness_deepeval`) → chính nó thành **phép đo bias judge**, cùng họ với 4.21 independent judge |
| Nếu vẫn muốn thay | Pin version DeepEval trong results file, đúng luật cấm alias (5.11) |

---

## 6. Redis — trả lời câu hỏi trong suggestion

Suggestion tự hỏi *"redis làm gì được ở agentic rag này nhỉ, mình chỉ nghĩ ra cache câu trả lời
streaming fail."* Câu trả lời đầy đủ:

| Dùng làm gì | Đáng làm? | Lý do |
|---|---|---|
| Cache câu trả lời streaming bị đứt giữa chừng | 💡 có | Đúng như suggestion nghĩ. Client reconnect đọc lại buffer thay vì gọi lại LLM |
| **Cache embedding của query** | 💡 **đáng nhất** | Câu hỏi lặp lại (rất nhiều trong nội bộ công ty) → bỏ hẳn 1 API call embedding. Key = hash(query). **Trực tiếp giảm đau quota (7.3)** |
| Semantic cache câu trả lời | ⚠️ cẩn thận | Embed query, nếu cosine với query cũ > ngưỡng thì trả lại answer cũ. Nguy hiểm: corpus đổi thì answer cache **sai mà vẫn tự tin**. Phải invalidate theo `corpus.lock.json` hash |
| Rate limit / quota guard | 💡 có | Repo đã chết vì quota giữa Phase 4. Counter trong Redis chặn trước khi gọi provider |
| State cho agentic loop nhiều bước | 💡 sau | Chỉ có nghĩa khi làm 6.2 + 2.5 |
| Job queue cho ingest async | ⚠️ | = Celery + Redis, **ADR-0002 đã bác** với trigger cụ thể. Cần ADR mới, xem 2.2 |

**Lưu ý:** prompt caching (6.1 trong file 6) là caching **phía provider**, không phải Redis. Hai
thứ khác nhau, có thể làm cả hai.

---

## 7. Nghiệm thu — "specify các điều kiện nghiệm thu giả định" 💡

Đây là **yêu cầu về quy trình**, không phải kỹ thuật, và file 6 không có mục tương đương.

Repo đã có **Definition of Done per-phase** (CLAUDE.md luật 11) và `docs/progress/phase-N.md`.
Cái còn thiếu là **ngưỡng số**: hiện DoD là "code chạy, test pass", chưa phải "`faithfulness`
trung bình ≥ 4.0 và `over_refusal_rate` ≤ 15%".

| | |
|---|---|
| Việc cần làm | **Điều kiện đã đủ** — có 3 results file. Chốt ngưỡng chấp nhận cho từng metric và ghi vào ADR |
| Vì sao phải sau baseline | Đặt ngưỡng **trước khi biết baseline** là bịa số. Đặt sau baseline mà không ghi ngày thì thành *"chọn ngưỡng vừa đủ để mình pass"* — nên **ghi rõ ngày chốt và giá trị baseline tại thời điểm đó** |
| Đặt thế nào cho đúng | Ngưỡng **retrieval** đặt được ngay (deterministic): ví dụ recall@5 ≥ 0.95, MRR ≥ 0.90. Ngưỡng **generation** thì không được đặt bằng một lần chạy — với `refusal_accuracy` từng cho 0.8 rồi 1.0 trên cùng code, một ngưỡng "≥ 0.9" sẽ fail CI ngẫu nhiên. Hoặc đặt ngưỡng trên **trung vị nhiều lần chạy**, hoặc đặt rộng và chấp nhận nó chỉ bắt được sự cố lớn |
| Ăn khớp | Ngưỡng chính là điều kiện `.github/workflows/eval.yml` (4.30) sẽ fail CI |

---

## 8. Thứ tự khuyến nghị — bản gộp với file 6

Đã xong kể từ bản trước: baseline (`naive-v1`), `hybrid-v2`, cross-encoder rerank, và Phase 5
(API + UI). Danh sách còn lại, xếp lại theo tình hình hiện tại:

| # | Việc | Nguồn | Vì sao ở vị trí này |
|---|---|---|---|
| 1 | **Chạy lại `rerank-v1` nhiều lần** | file 6 3.7 | Không tốn code. Chưa biết `refusal` 0.800 là thật hay nhiễu, mà **mọi mục generation bên dưới đều đo bằng chính metric đó**. Làm trước, nếu không thì các thí nghiệm sau không đọc được |
| 2 | **Post-check 4c — số liệu không có trong nguồn** | 1.5 | ~20 dòng regex, **không cần thêm API call nào**, thêm được 1 metric mới. Vẫn rẻ nhất trong cả hai file |
| 3 | **Quy tắc prompt còn thiếu + few-shot refusal** | 1.4 | 1 file `answer_v2.jinja`, đo bằng harness sẵn có. **Đáng làm hơn trước**: retrieval đã kịch trần (recall@5 = 1.0), nên chỗ còn cải thiện được nằm ở nửa generation |
| 4 | **Retrieval gate** | 1.1 | Lớp phòng thủ duy nhất repo chưa có gì. Ngưỡng chọn trên **thang cross-encoder**, không phải cosine |
| 5 | Independent judge | file 6 4.21 | Càng đáng làm sau ADR-0010: judge tự chấm nên không phân xử được chênh lệch generation giữa 3 pipeline |
| 6 | **Cache embedding query bằng Redis** | 6 | Độc lập mọi thứ khác. Lưu ý: đau quota đã đỡ nhiều sau khi rời free tier (ADR-0008), nên lý do bây giờ là **latency và chi phí**, không còn là "bị chặn" |
| 7 | Breadcrumb metadata | file 6 1.10 | Không đổi — và **1.2 (đánh số citation) nên làm cùng lúc**, chung dữ liệu |
| 8 | **API streaming** | 2.1 | Phase 5 đã có API + UI, nhưng chưa streaming. Đây là thứ cải thiện cảm nhận demo rõ nhất |
| 9 | **Observability sản phẩm + dashboard** | mục 4 | Chỉ có nghĩa khi đã có traffic thật |
| 10 | Structured output JSON | 1.3 | Đụng `refusal_accuracy`; và bây giờ đụng **3 baseline** chứ không phải 1 |
| 11 | Prompt caching · Multi-query · Agentic RAG · MCP · Docling | file 6 | Không đổi, giữ cuối |

> **Nhắc lại cảnh báo trần corpus (file 6 mục 8):** recall@5 = 1.0 trên 34 chunk nghĩa là thước
> đo retrieval đã hết dư địa. Vì vậy danh sách này cố ý **không còn mục retrieval nào ở đầu** —
> việc đáng giá tiếp theo là làm phép đo tốt lên (mục 1, 5) và vá nửa generation (2, 3, 4).

---

## 9. Các va chạm phải ghi ADR trước khi code

Tổng hợp mọi chỗ suggestion đụng vào quyết định đã chốt của repo:

| Ý tưởng | Va chạm với | Hệ quả |
|---|---|---|
| Ingest async + polling (2.2) | CLAUDE.md: "synchronous ingest", `app/workers/` khoá sau Phase 6; ADR-0002 bác Celery+Redis | ADR mới. **Vẫn còn nguyên** — phần sync đã làm không mở khoá được phần async |
| ~~User upload tài liệu (2.4)~~ | ~~ADR-0005~~ | ✅ **đã giải quyết** — bỏ `force` khỏi HTTP + skip bytes trùng + `make validate` sau upload. Không cần tách hai corpus ở quy mô hiện tại |
| Structured output JSON (1.3) | 3.3 refusal constant → `is_refusal()` → `refusal_accuracy` (4.6, safety-critical) | ADR mới. Bây giờ đụng **3 results file đã đóng băng**, không phải 1 |
| DeepEval thay judge (mục 5) | 4.27 provenance, ADR-0006 | Chạy song song, đừng thay |
| Search space / ACI (3.4) | ADR-0001 "no permissions in v1" | Thêm cột sớm thì rẻ, sau thì đắt. **Đã qua điểm rẻ** — schema đã chạy và đã có dữ liệu |
| OCR / Docling | ADR-0001 out of scope + re-ingest phá chunk id | Đã ghi ở file 6 mục 6.4 |
| Follow-up question (3.2) | `llm/memory.py` khoá đến sau Phase 6 | **Phase 6 đã xong** → khoá đã mở về mặt luật, nhưng vẫn cần ADR vì phá giả định "single-turn" của v1 |
| Retrieval gate — chọn ngưỡng (1.1) | 2.4 — mỗi retriever một thang score | Pipeline serve là `rerank-v1` → ngưỡng đặt trên **điểm cross-encoder**. Đổi pipeline là phải hiệu chỉnh lại |
| **Thêm vendor thứ 3 (Voyage)** | ADR-0008 vừa gom stack về OpenAI | ✅ đã ghi — ADR-0010 sửa đổi ADR-0008. Hệ quả kể được: `/chat` giờ phụ thuộc **2 key có tính phí của 2 nhà cung cấp**, một điểm hỏng nữa |

---

## 10. Một câu tóm tắt

Suggestion đóng góp ba thứ file 6 không có: **(a)** lớp retrieval gate và post-check số liệu —
hai lớp chống hallucination rẻ và **vẫn chưa làm**; **(b)** toàn bộ nhóm API/UX/streaming — Phase 5
đã lấy phần API + UI + citation xem được, còn lại streaming và observability; **(c)** observability
sản phẩm như một loại đo **khác** eval offline. Phần còn lại trùng với file 6, liệt kê ở mục 0.

Cảnh báo của file 6 đổi nội dung nhưng không đổi tinh thần. `leaderboard.md` giờ có **3 dòng, một
trong đó là kết quả âm được giữ lại kèm ADR** — phần "chứng minh đo được" coi như xong. Điều cần
cảnh giác bây giờ ngược lại: `recall@5` đã 1.0 nên **thước đo hết dư địa trước khi kỹ thuật hết ý
tưởng**. Thêm một retriever nữa sẽ không cho thêm con số nào đọc được; việc đáng làm là làm phép
đo tốt lên — judge độc lập, chạy nhiều lần, golden set khó hơn do người viết.
