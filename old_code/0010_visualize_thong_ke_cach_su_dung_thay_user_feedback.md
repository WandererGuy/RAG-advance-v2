# Eval chatbot RAG bằng thống kê khi người dùng không feedback

> **Vấn đề**: tỷ lệ bấm 👍👎 thực tế thường chỉ 1–3%, và bị lệch nặng về phía người bực mình. Đừng xây eval trên đó.
>
> **Hướng đi**: tín hiệu ngầm (implicit) + LLM-judge chạy trên traffic thật. Con số nghiệm thu vẫn giữ ở offline eval.

---

## 1. Tín hiệu ngầm từ hành vi — mạnh nhất, rẻ nhất

Chỉ cần log per-request đã có, thêm vài event ở frontend.

| Tín hiệu | Ý nghĩa | Độ tin |
|---|---|---|
| **Reformulation** — hỏi lại câu tương tự trong <90s (cosine sim > 0.8 giữa 2 query liên tiếp) | Trả lời không xài được | ⭐⭐⭐ Cao |
| **Ngôn ngữ bực** — "sai rồi", "không phải", "tôi hỏi là…", "không đúng" | Fail rõ ràng | ⭐⭐⭐ Rất cao |
| **Escalation** — "cho tôi số HR", "gặp người thật" | Bot thua | ⭐⭐⭐ Rất cao |
| **Copy answer** | Dùng thật, hài lòng | ⭐⭐⭐ Cao |
| **Click citation** | Mơ hồ: tin nên xem thêm, hoặc nghi nên đi kiểm | ⭐ Thấp |
| **Abandonment** — hỏi 1 câu rồi thoát | Mơ hồ: xong việc, hoặc bỏ cuộc | ⭐ Thấp |
| **Return rate** — user quay lại tuần sau | Giá trị thật của sản phẩm | ⭐⭐⭐ Cao |

Ba tín hiệu đầu là thứ đáng đầu tư. **Reformulation rate** đặc biệt tốt: nó gần như là "thumbs down ngầm", và có ở 100% traffic.

Ghép lại thành một chỉ số duy nhất:

> **Session Success Rate** = % session không có reformulation, không có ngôn ngữ bực, không escalation

**Cảnh báo**: click citation và abandonment nghe hay nhưng diễn giải hai chiều — đừng đưa vào công thức chính, chỉ để tham khảo.

---

## 2. Tín hiệu từ chính hệ thống — không cần user làm gì

- **Retrieval score distribution**: log max/mean similarity của top-k. Vẽ histogram, đặt ngưỡng nghi ngờ. % request rơi dưới ngưỡng là proxy tốt cho "sắp bịa".
- **Self-consistency**: với 5% request, chạy lại 3 lần ở temperature cao, đo độ phân kỳ giữa 3 câu trả lời. Phân kỳ cao ≈ model đang đoán. Không cần ground truth.
- **Hedging detection**: đếm cụm "có thể", "thường thì", "tôi không chắc" — tăng đột biến là dấu hiệu retrieval kém.

---

## 3. LLM-as-judge trên traffic thật — thay được ground truth

Mảnh ghép quan trọng nhất và hay bị bỏ qua. Với RAG, **không cần đáp án chuẩn** để chấm hai thứ:

- **Faithfulness / groundedness**: tách answer thành các claim, hỏi judge "claim này có được support bởi context đã retrieve không?". Đây chính là đo tỷ lệ bịa — trên dữ liệu thật, không phải golden set.
- **Context relevance**: context retrieve về có liên quan đến câu hỏi không → tách bạch lỗi retrieval hay lỗi generation.

Chạy được trên 100% traffic nếu dùng model nhỏ, hoặc sample 10%. Chi phí thấp hơn nhiều so với giá trị.

> **Điều kiện bắt buộc**: phải calibrate judge. Lấy ~100 mẫu, cho người thật chấm, đo agreement với judge (Cohen's kappa). Báo cáo con số đó kèm mọi metric từ judge. Nếu không, khách sẽ hỏi ngay *"vậy ai chấm cái máy chấm?"* và bạn không có gì để trả lời.

---

## 4. Đào log để mở rộng golden set — giá trị lớn nhất cho khách

Cluster toàn bộ câu hỏi thật (embedding + HDBSCAN), rồi xếp cluster theo **tần suất × tỷ lệ fail**:

- **Cluster tần suất cao + refusal cao** = lỗ hổng tài liệu.
  Đây là báo cáo mà HR cực thích: *"300 lượt hỏi về nghỉ không lương, hệ thống không trả lời được vì chưa có quy định nào bằng văn bản."*
- **Cluster tần suất cao + faithfulness thấp** = chỗ cần fix chunking/retrieval.

Mỗi tháng bốc câu đại diện từ cluster mới bổ sung vào golden set — golden set ban đầu do HR ngồi nghĩ ra bao giờ cũng lệch so với câu hỏi thật.

---

## 5. Nếu vẫn muốn feedback tường minh

- Bỏ 👍, chỉ giữ 👎 nhưng bấm xong hiện **chip chọn nhanh**: *Sai thông tin / Thiếu ý / Nguồn không đúng / Không hiểu câu hỏi*. Một cú tap, tỷ lệ trả lời cao hơn hẳn ô text.
- **Micro-survey ngẫu nhiên** 1/20 request: "Câu trả lời này có giúp bạn không?" — random sampling nên không bị lệch như feedback tự nguyện.
- **Reviewer có trả công**: nhờ 2–3 chuyên viên HR chấm 20 câu/tuần lấy từ log. ~80 nhãn người/tháng, đủ để calibrate judge và làm số liệu "chính thức" khi báo cáo.

---

## Ba cái bẫy thống kê

**Traffic nội bộ nhỏ.**
Vài trăm request/tuần thì confidence interval rộng khủng khiếp. Đừng vẽ chart theo ngày rồi kết luận "hôm qua tệ hơn". Dùng cửa sổ tuần, luôn kèm CI, và tính trước cần bao nhiêu mẫu để phát hiện chênh lệch 5%.

**Survivorship bias — nguy hiểm nhất.**
Người ghét bot sẽ bỏ dùng. Metric per-request đẹp dần lên trong khi sản phẩm đang chết. Bắt buộc theo dõi song song: *số active user*, *return rate*, *số câu hỏi/user*. Chất lượng tăng mà active user giảm = tin xấu, không phải tin tốt.

**Nhầm proxy với sự thật.**
Session Success Rate cao không có nghĩa câu trả lời đúng — có thể user không đủ chuyên môn để biết mình bị trả lời sai. Với HR thì đây là rủi ro thật. Chỉ có faithfulness check và human review mới trả lời được câu "có đúng không".

---

## Kết luận

Cái này **không thay eval**. Vai trò của nó là:

1. Phát hiện drift giữa golden set và câu hỏi thật
2. Tìm chỗ hỏng để fix
3. Nuôi golden set lớn dần

Con số đem đi nghiệm thu vẫn phải là `results/naive-v1.json` chấm trên bộ câu hỏi đã đóng băng.

> **Nếu chỉ làm được một thứ**: làm **reformulation rate** — rẻ nhất, chạy trên 100% traffic, và tương quan tốt với chất lượng thật.