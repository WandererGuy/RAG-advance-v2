# Sprint 2 — Plan (DRAFT, chờ chốt)

**Viết** 2026-08-14, sau khi Sprint 1 (Phase 0–6) đóng.
**Trạng thái: DRAFT.** Chưa chốt thì chưa code. Sau khi chốt, file này không sửa giữa sprint —
phát hiện sai thì re-plan toàn bộ phần còn lại hoặc cắt sprint sớm (`0015`).

Đọc trước: [`retro-phase-5-6.md`](retro-phase-5-6.md) · [`progress.md`](progress.md) · `CLAUDE.md`.

---

## 1. Mục tiêu sprint

> **Từ demo single-turn → trợ lý hội thoại quan sát được, đo bằng tiêu chí thay vì chunk id.**

Một câu, đủ lớn để có tầm nhìn, đủ nhỏ để demo được cuối sprint.

**Vì sao là cái này, không phải golden set v2 như retro đề xuất:** retro xếp hạng theo *kỹ thuật*.
Nguyên tắc sprint (`0015`) nói ưu tiên *feature*. Hai thứ hoà giải được: multi-turn không bị chặn
bởi `recall@5 = 1.0` vì nó **không đo bằng golden set hiện tại** — nên nó là feature duy nhất
chạy được ngay mà không cần ai ngồi viết 29 câu trước.

---

## 2. Hai quyết định nền móng đã chốt

### 2.1. Eval: chuyển hẳn sang criteria-based

**Quyết định:** bỏ chunk-id-based eval (`recall@k`, `MRR`, `nDCG@k`) làm thước đo chính. Thay bằng
tiêu chí không cần `relevant_chunk_ids`.

**Lý do (của người quyết):** chunk-id eval **ép corpus phải đóng băng**. Mà frozen corpus thì
không thử được chunk size, không cho user upload thật, không lớn được dataset. Nó đang chặn chính
những thứ sprint này muốn làm.

**Cái giá, ghi thẳng ra:**
- `results/{naive-v1,hybrid-v2,rerank-v1}.json` **không so được** với bất cứ số nào sau sprint này.
- ADR-0009 (hybrid không adopt) và ADR-0010 (rerank adopt) dựa hoàn toàn vào recall/MRR. Chúng
  **vẫn đúng trong phạm vi của chúng** và không bị rút lại.
- Mất provenance kiểu 4.27 nếu dùng thư viện hộp đen → phải pin version, xem 4.3.

**Cách không mất mát:** **không xoá gì cả.**
- `results/leaderboard.md` hiện tại đóng băng, đổi tên thành `results/leaderboard-sprint1.md` với
  một dòng đầu ghi *"chunk-id era, Sprint 1, không so được với bảng sau"*.
- Eval mới ghi vào bảng mới. Hai bảng, hai kỷ nguyên, không trộn.
- `eval/` cũ **không xoá** — nó là bằng chứng của 3 thí nghiệm đã chạy.

**Cần ADR-0011** trước dòng code đầu tiên.

### 2.2. Chủ đề: multi-turn + observability

Mở khoá `llm/memory.py`, `llm/tools/` (chưa dùng), `routes/conversations.py`,
`conversation_repo.py`, `message_repo.py` — CLAUDE.md mục 2 ghi "unlocked at after Phase 6", và
Phase 6 đã xong. Nhưng phá giả định **"single-turn"** của v1 → **cần ADR-0012**.

---

## 3. Phases

Mỗi phase: 1 commit, message có phase ID, kèm `docs/progress/sprint2-phase-N.md` (CLAUDE.md 11–12).

### Phase 7 — ADR + khung eval mới

Không có feature nào ở đây. Đây là phase "chốt thước đo trước khi đo" (`0015`: *eval phải chốt
cùng lúc chốt plan*).

- [ ] `ADR-0011` — criteria-based eval thay chunk-id eval. Context / Decision / Consequences, kèm
      cái giá ở 2.1 và cách giữ Sprint 1 nguyên vẹn.
- [ ] `ADR-0012` — multi-turn, phá giả định single-turn của v1.
- [ ] `eval/criteria/` — bộ tiêu chí mới, không phụ thuộc `relevant_chunk_ids`:
      `faithfulness`, `answer_relevance`, `refusal_correctness`, `citation_validity`.
      Ba cái đầu đã có bản tự viết ở `eval/metrics/generation.py` → **tái dùng, không viết lại**.
- [ ] Đóng băng `leaderboard-sprint1.md`, khởi tạo bảng mới.
- [ ] Chạy lại `rerank-v1` **3 lần** trên thước đo mới → baseline là **phân bố**, không phải một số.
      (File 6 mục 3.7: generation metric không tái lập được. Đây là mục #1 trong cả hai file 6 và 7.)

**DoD:** hai ADR tồn tại · bảng mới có baseline 3 lần chạy của `rerank-v1` · `make lint`, `make test` xanh.

### Phase 8 — Observability (Langfuse hoặc LangSmith)

Làm **trước** multi-turn, có chủ ý: không có trace thì multi-turn là hộp đen, debug bằng mắt.

- [ ] Chọn Langfuse vs LangSmith → ghi vào ADR-0013 (self-host được hay không là tiêu chí chính,
      ADR-0001 cho phép data ra ngoài nên không phải blocker).
- [ ] Trace mọi `/chat`: câu hỏi, chunk truy xuất, prompt render, response, latency từng bước.
- [ ] Log per-request có cấu trúc — `core/logging.py` (structlog JSON) đã sẵn sàng, chỉ thêm trường.
- [ ] Không thay `queries` table; bổ sung, không thay thế.

**DoD:** một câu hỏi thật trên UI → thấy đủ trace trên dashboard, chỉ ra được chunk nào vào prompt.

### Phase 9 — 3 tầng LLM: light / medium / heavy

Điều kiện tiên quyết của query contextualization ở Phase 10.

- [ ] `Settings` thêm `llm_light_*`, `llm_heavy_*` bên cạnh `default_llm_*` hiện có.
      Giữ nguyên `default_llm_*` để không phá gì đang chạy.
- [ ] `llm/client.py` nhận tier. **Luật cấm alias (ADR-0007) áp cho cả ba tier.**
- [ ] Light dùng cho contextualization/rewrite; heavy cho answer.

**DoD:** đổi tier bằng `.env`, không đụng code · results file ghi cả ba model name.

### Phase 10 — Multi-turn + query contextualization

Feature chính của sprint.

- [ ] `models/` — `conversations`, `messages` + migration.
- [ ] `repositories/conversation_repo.py`, `message_repo.py`.
- [ ] `llm/memory.py` — lấy N lượt gần nhất.
- [ ] **Query contextualization**: dùng model **light** + vài lượt gần nhất sinh câu truy vấn độc
      lập để retrieve. Đây chính là 2.8 query rewriting đang 📋 trong file 6, giờ có lý do thật.
      Prompt mới `contextualize_v1.jinja` (luật 3.5: file mới).
- [ ] `routes/conversations.py` + `POST /chat` nhận `conversation_id` (optional → single-turn vẫn chạy).
- [ ] Streamlit giữ lịch sử hội thoại.

**DoD:** hỏi "chính sách nghỉ phép bao nhiêu ngày?" → "còn thâm niên 5 năm thì sao?" và câu 2 được
hiểu đúng · đo trên thước đo Phase 7 · single-turn cũ không regression.

### Phase 11 — Retro + demo

- [ ] Demo được: hội thoại nhiều lượt, có citation, có trace.
- [ ] `docs/retro-sprint-2.md`.
- [ ] Cập nhật `CLAUDE.md` những gì học được (luật 14: viết lại, không gạch ngang).

---

## 4. Tiêu chí nghiệm thu — chốt cùng plan, không viết sau

Theo `0015`: **đo output, đừng đo đường đi**. Ít mà chuẩn.

| # | Tiêu chí | Ngưỡng | Vì sao con số này |
|---|---|---|---|
| 1 | Multi-turn hiểu câu hỏi phụ thuộc ngữ cảnh | **8/10 cặp câu** tự soạn khi bắt đầu Phase 10 | Không phải 10/10: contextualization dùng model light, sai vài ca là chấp nhận được nếu không sai kiểu nguy hiểm |
| 2 | Không regression single-turn | `faithfulness` **không thấp hơn baseline 3-lần-chạy quá 0.2** | 0.2 là biên độ nhiễu đã quan sát được (CLAUDE.md 16). Đặt chặt hơn sẽ fail ngẫu nhiên |
| 3 | Trace đọc được | 1 câu judgment: *"mở dashboard, chỉ ra được chunk nào đã vào prompt của câu trả lời này không?"* | Không ép thành số. `0015`: có thứ chỉ cần judgment rõ ràng |

**Cho phép tiêu chí sai.** Chạy xong phát hiện đo nhầm thứ → ghi nhận là finding của sprint, sửa ở
retro, ghi rõ *sửa vì đo sai* chứ không phải vì trượt.

---

## 5. Câu hỏi bắt buộc trước khi chốt (`0015`)

> **Plan này có giả định gì, rủi ro ở đâu, và cái gì chứng minh nó sai sớm nhất?**

**Giả định:**
1. Criteria-based eval **phân biệt được** pipeline tốt/xấu mà không cần chunk id. *Chưa được chứng
   minh trên repo này.*
2. Query contextualization bằng model light **đủ tốt** cho tiếng Việt.
3. Langfuse/LangSmith cắm vào LiteLLM không phải viết lại `client.py`.

**Rủi ro lớn nhất:** giả định 1. Nếu criteria-based eval cho cả 3 pipeline điểm gần như nhau thì ta
vừa **bỏ thước đo cũ mà chưa có thước đo mới** — tệ hơn cả hai lựa chọn ban đầu.

**Cái chứng minh sai sớm nhất — và rẻ nhất:** Phase 7 chạy criteria mới trên **cả 3 pipeline cũ**,
không chỉ `rerank-v1`. Ta đã biết sự thật từ chunk-id eval: `rerank-v1` > `naive-v1` rõ rệt về thứ
tự. Nếu thước đo mới **không thấy được chênh lệch đó**, nó không phân biệt được và phải sửa ngay ở
Phase 7 — trước khi Phase 8–10 xây lên trên.

Đây là lý do Phase 7 chạy 3 pipeline chứ không phải 1. Rẻ, và nó là canary của cả sprint.

---

## 6. Cố ý KHÔNG làm trong sprint này

- **Thêm retriever** — `recall@5 = 1.0`, thước đo hết dư địa (file 6 mục 8).
- **`golden_qa.v2` do người viết** — vẫn đáng giá, nhưng criteria-based eval giảm mức độ chặn. Đưa
  vào sprint 3.
- **Async ingest + workers** — ADR-0002 bác Celery+Redis, cần ADR riêng, không nhét vào sprint này.
- **Agentic RAG, MCP, Docling, streaming** — sau, mỗi cái 1 ADR.
- **OOP refactor** — không có demo nhìn thấy được; làm khi có lý do cụ thể, không làm cho đẹp.
- **Retrieval gate, post-check 4c** — rẻ và đáng, nhưng là technique. Sprint 3.

---

## 7. Việc vẫn chờ người

Không nằm trong DoD của sprint, nhưng vẫn mở:

- Một người ngoài team click thử UI (10 phút) — nợ từ Phase 5.
- Quyết định refusal contract — nợ 3 phase. **Criteria-based eval có thể giải quyết gián tiếp**:
  `refusal_correctness` định nghĩa lại được để chấp nhận hedge, thay vì string-match một câu.
  Ghi vào ADR-0011.
- `backend/.env` thừa còn trên đĩa — xoá 5 giây.
