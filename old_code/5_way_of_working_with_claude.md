# Cách làm việc với Claude — đánh giá workflow và bài học cho dự án sau

> Ghi lại nguyên văn buổi trao đổi ngày 2026-08-11, sau khi Phase 4 commit (`1148a3a`) nhưng
> baseline chưa chạy được. Gồm 3 phần:
> **Phần 1** — workflow hiện tại (PLAN / CLAUDE / progress / architecture / ADR) đã ổn chưa, so
> với BMAD và superpowers.
> **Phần 2** — hai thay đổi đã thực hiện: `/phase-done` và dọn `CLAUDE.md`.
> **Phần 3** — nên làm gì ở dự án mới.
>
> Đường dẫn trong file này tính từ thư mục gốc repo (`../`).

---

# PHẦN 1 — Workflow hiện tại đã ổn chưa?

**Câu hỏi:** *"những cách mình làm, tạo file plan, claude, progress, architecture, adr đã đủ ổn
chưa, mình ko biết workflow vậy ổn chưa nhỉ, hay bên bmad hay superpower trên mạng làm ổn hơn"*

Đã đọc qua `CLAUDE.md`, `PLAN.md`, `docs/architecture.md`, 5 file progress, 7 ADR và `command.md`.
Trả lời ngắn gọn trước: **workflow của bạn ổn hơn mức trung bình khá nhiều**, và ở một điểm quan
trọng nó tốt hơn cả BMAD lẫn superpowers. Nhưng nó đang thiếu đúng một lớp mà hai framework kia
mạnh.

## Cái bạn đang làm tốt (đừng đổi)

**Eval là Definition of Done.** Đây là thứ hiếm. Rule 8 ("mọi con số phải nằm trong `results/*.json`
và được commit") + `golden_set_author` + `corpus.lock.json` + `make validate` — bạn đã biến tính
trung thực thành một lệnh chạy được thay vì một lời hứa. Phase 4 dừng ở câu 10/29 và **không commit
kết quả một phần** là ví dụ rõ nhất: quy tắc đó đã thật sự chặn được một quyết định tồi. BMAD không
có gì tương đương; superpowers cũng không.

**Tách đúng 3 loại tài liệu.** ADR = *tại sao*, progress = *đã xảy ra gì + bằng chứng*, PLAN = *sắp
làm gì*. Rất nhiều người trộn cả ba vào một file rồi 2 tuần sau không đọc nổi. `docs/progress.md`
làm index là lựa chọn đúng.

**Rule 4.1 (pipeline đã có kết quả là immutable)** — đây là tư duy của người làm nghiên cứu, không
phải người viết CRUD.

## 4 chỗ đang yếu

**1. Không có `.claude/` — đây là gap lớn nhất.** Bạn đang mã hoá toàn bộ workflow bằng *văn xuôi
trong CLAUDE.md* và trông chờ model đọc kỹ. BMAD/superpowers về bản chất chỉ là: persona (subagent)
+ workflow lặp lại (slash command) + template. Bạn đã có template và kỷ luật; thiếu phần **thực
thi**. Cụ thể nên có:

- `.claude/commands/phase-done.md` — chạy `make lint && make test && make validate`, viết
  `docs/progress/phase-N.md` theo đúng 5 phần của rule 11–12, thêm dòng vào index, rồi commit. Đây
  là thứ bạn đang lặp lại thủ công mỗi phase.
- `.claude/commands/new-adr.md` — copy `0000-template.md`, đánh số kế tiếp, thêm link vào
  `architecture.md`.
- `.claude/settings.json` với hook `PreToolUse` chặn `Edit` vào `naive_v1.py` khi
  `results/naive-v1.json` đã tồn tại. Rule 4.1 hiện chỉ là lời cầu nguyện; hook biến nó thành hàng
  rào.

**2. `CLAUDE.md` đang bắt đầu mục rữa.** 201 dòng, trong đó có: một blockquote "section 3 đã bị
superseded một phần", một rule 5.6 bị gạch ngang, một bảng "originally written / as built". Đó là
địa tầng khảo cổ, không phải chỉ dẫn. File này được nạp vào *mọi* context — nó phải nói **hiện tại
đúng là gì**, còn lịch sử thì để ADR giữ.

**3. `command.md` nên xoá.** Nó là bản sao cũ của cây thư mục đã có trong `docs/architecture.md`,
lại còn liệt kê `workers/`, `memory.py`, `hybrid_v2.py`, `conversations.py` — đúng những file mà
rule 2 cấm tạo sớm. Hai nguồn sự thật mâu thuẫn nhau về cùng một thứ.

**4. `.github/workflows/` vẫn là `.gitkeep`.** Architecture map hoãn CI đến Phase 6, nhưng
`make lint && make test && make validate` chạy được từ Phase 3 rồi. CI ở đây rẻ và nó bảo vệ đúng
thứ dễ vỡ nhất: corpus lock.

## So với BMAD / superpowers

**BMAD** mạnh ở greenfield từ số 0: analyst → PM → architect → scrum master sinh ra PRD và story đã
shard. Bạn đã đi qua giai đoạn đó rồi — `PLAN.md` + ADR-0001 chính là output của nó. Kéo BMAD vào
lúc này bạn chỉ nhận thêm ceremony: story file, epic, retrospective cho một dự án solo 6 phase.
Phần đáng học duy nhất là *sharding* — chia tài liệu lớn thành mảnh vừa context — mà bạn đã tự làm
khi tách `progress.md` thành một file/phase.

**Superpowers** (skills + workflow đóng gói) đáng học hơn, nhưng đúng ở phần nói ở mục 1: **cách
đóng gói**, không phải nội dung. Nội dung của bạn tự viết vẫn tốt hơn vì nó nói về *dự án này* —
"768 nằm ở 3 chỗ phải đổi cùng nhau", "gemini free tier 20 req/ngày, một run cần 82" — không
framework nào biết được những thứ đó.

Đánh giá thật: nếu cho điểm, tài liệu/kỷ luật của bạn ~8/10, tự động hoá ~2/10. BMAD ngược lại.
Đổi sang framework là bỏ 8 để lấy 6.

## Đề xuất

Không đổi workflow. Thêm lớp thực thi, theo thứ tự này — nhưng **sau khi Phase 4 có số**, vì rule 1
và vì baseline đang là thứ chặn mọi thứ khác:

1. `.claude/commands/phase-done.md` (tiết kiệm nhiều nhất, mỗi phase một lần)
2. Cắt gọn `CLAUDE.md`, xoá `command.md`
3. Hook chặn sửa pipeline đã có kết quả
4. `ci.yml` chạy lint + test + validate

---

# PHẦN 2 — Hai thay đổi đã thực hiện

**Câu hỏi:** *"ok bạn làm đi"* (mục 1 và 2 ở trên)

Xong cả hai. Chưa commit — `command.md` ở trạng thái staged-delete, `.claude/` chưa track.

## 1. `/phase-done N` — `.claude/commands/phase-done.md`

Slash command 5 bước, đóng gói đúng quy trình vẫn làm tay mỗi phase:

1. **Chứng minh DoD** — đọc dòng `✅ Done when:` của phase đó trong PLAN.md *trước*, rồi chạy
   `make lint`, `make test`, `make validate` và bắt output thật. Nếu fail hoặc artefact DoD chưa
   tồn tại thì **dừng, không viết entry, không commit** — có nhắc thẳng Phase 4 làm tiền lệ.
2. **Viết `docs/progress/phase-N.md`** — bắt đọc `phase-2.md` và `phase-4.md` trước để theo đúng
   heading cũ thay vì bịa cái mới. Có câu chặn: *"Real numbers pasted from the terminal. Never a
   summary of output you did not run."*
3. **Cập nhật index** — cả bảng lẫn phần văn xuôi bên dưới ("Where the project stands", "Still
   blocked on a human"), và kiểm tra xem phase vừa rồi có làm sai lệch `CLAUDE.md` / `PLAN.md` /
   `architecture.md` không.
4. **Commit** — code + entry + index trong *một* commit, show diffstat trước, không push.
5. **Report rồi dừng** — rule 1.

`allowed-tools` giới hạn ở `make:*`, `git:*` và file tools, nên nó không tự ý chạy `make eval` đốt
quota.

## 2. `CLAUDE.md` — dọn địa tầng

Chỉ giảm 202 → 198 dòng, nên nói thẳng: **cái được không phải là ngắn hơn, mà là không còn tự mâu
thuẫn.** Cụ thể:

- Bỏ blockquote đầu file (thứ đang kể trạng thái phase — việc của `progress.md`, và nó đã cũ: vẫn
  viết "Phases 0–2 are complete" trong khi Phase 3 xong rồi).
- Section 3: bỏ cột `originally written here`. Giờ chỉ còn một cột **as built**, ADR-0002 giữ lịch
  sử. Không ai còn phải đọc chéo hai cột để biết cái nào đang chạy.
- Rule 5.6: bỏ gạch ngang, viết lại thẳng theo ADR-0004.
- Rule 11–12: nén lại, chi tiết chuyển vào `/phase-done` — một nguồn sự thật thay vì hai bản mô tả
  cùng thứ.
- Thêm **rule 14**: file này phải *đúng ở hiện tại, không phải lịch sử* — cấm strike-through và cột
  "originally/as built". Đây là cái ngăn nó mục lại sau 3 phase nữa.
- Section 7 thêm bảng slash command.

## 3. Xoá `command.md`

Đã grep — không file nào tham chiếu tới nó. Nội dung đã có trong `docs/architecture.md`, và bản cũ
còn liệt kê `workers/`, `memory.py`, `hybrid_v2.py` — đúng những file rule 2 cấm tạo sớm.

**Còn lại 2 việc** trong đề xuất ban đầu, chưa làm: hook chặn sửa pipeline đã có `results/`, và
`ci.yml`. Cả hai đều nên đợi Phase 4 có số — cái hook không có gì để chặn khi `results/` còn rỗng.

---

# PHẦN 3 — Dự án mới thì nên làm gì

**Câu hỏi:** *"vậy nếu về sau vào dự án mới, những gì mình nên làm ở dự án đó, học hỏi được từ dự án
này và từ kiến thức mà bạn nghĩ nên bổ sung"*

Dưới đây là bản rút ra từ chính những gì dự án này **đã trả giá**, không phải lý thuyết chung.

## A. Giữ nguyên — đã chứng minh là đúng

**1. Tách 3 loại tài liệu theo *thì*, không theo chủ đề.**

| File | Trả lời | Thì |
|---|---|---|
| `CLAUDE.md` | cái gì đang đúng | hiện tại |
| `docs/adr/` | tại sao chọn thế | quá khứ, bất biến |
| `docs/progress/` | đã xảy ra gì, bằng chứng đâu | quá khứ, append-only |
| `PLAN.md` | sắp làm gì | tương lai |

Quy tắc phái sinh quan trọng nhất: **file "hiện tại" không được chứa lịch sử**. Đó chính là rule 14
vừa thêm — và nó sinh ra vì `CLAUDE.md` ở đây đã kịp mọc gạch ngang và cột "originally / as built"
chỉ sau 4 phase.

**2. DoD là một file trong git, không phải cảm giác.** Đây là thứ giá trị nhất của dự án này và nó
tổng quát được ra ngoài RAG: mỗi phase kết thúc bằng một **artefact commit được** mà người khác
kiểm chứng lại được — `results/naive-v1.json`, `corpus.lock.json`, output của `make validate`.
Không phải "đã xong ingest" mà là "34 chunks, hash này, lệnh này in ra cái này".

**3. Đơn vị thí nghiệm là bất biến và có tên.** `naive-v1` đã có kết quả thì không sửa, muốn đổi thì
tạo tên mới. Áp dụng được cho bất cứ thứ gì bạn đo: model, prompt, config scraper, chiến lược cache.

**4. Bảng "cái gì KHÔNG tồn tại và tồn tại lúc nào".** Bảng out-of-scope + `.gitkeep` đã ngăn được
rất nhiều scaffold thừa. Với agent thì đây là chỉ dẫn hiệu quả hơn mọi lời khuyên "hãy đơn giản".

**5. Provenance dính liền với con số.** `golden_set_author` nằm ngay trong file kết quả nên không ai
copy con số ra khỏi ngữ cảnh của nó được. Tổng quát: **metadata về độ tin cậy phải nằm cùng chỗ với
dữ liệu**, không nằm trong file README cạnh bên.

## B. Sửa — dự án này đã trả giá

**1. Ngày 0 phải là "reality check", không phải viết PLAN.**

Ở đây `PLAN.md` được viết trước, rồi Phase 0 phát hiện stack trong `CLAUDE.md`, `PLAN.md` và `.env`
mâu thuẫn nhau → tốn nguyên ADR-0002 để hoà giải. Lần sau, việc đầu tiên là chạy được **một đường
xuyên suốt qua toàn bộ phụ thuộc bên ngoài** rồi mới viết plan:

```
API key có thật không → model name có tồn tại không → embed 1 câu →
parse 1 tài liệu thật → ghi 1 dòng vào DB → đọc lại
```

Khoảng 30 dòng script, vứt đi sau. Nó trả lời được 5 câu hỏi mà plan đang *giả định*.

**2. Tính chi phí của một vòng eval trước khi thiết kế vòng eval.**

Đây là lỗi đắt nhất của dự án: Phase 4 code xong hết, chạy đúng, rồi chết ở câu 10/29 vì free tier
cho 20 request/ngày còn một run cần ~82. Con số 82 đó **tính được từ lúc viết PLAN**: 29 câu ×
(1 answer + ~1.8 judge). Lần sau, PLAN phải có một dòng:

> Một full run = N câu × M lời gọi = X request, Y token, Z đồng, mất T phút. Quota/ngân sách hiện
> có: …

Và hệ quả thiết kế: **runner phải có tier từ đầu** — `--limit 3` (smoke), `--limit 10` (partial, có
checkpoint), full — cộng với **resume**. Nếu runner biết ghi checkpoint từng câu, cái run chết ở câu
10 hôm đó đã không mất trắng.

**3. Một gate không có tên người thì không phải gate.**

Phase 0 hỏi đúng câu "ai sẽ viết golden set?" — nhưng câu trả lời không bao giờ được điền, và 3
phase sau nó nổ ra thành ADR-0004. Format nên là:

> 🛑 GATE: `<việc>` — người: **`<tên>`** — hạn: **`<ngày>`** — nếu quá hạn: **`<fallback đã định
> trước>`**

Fallback định trước lúc bình tĩnh sẽ tốt hơn fallback nghĩ ra lúc đang bị chặn. Dự án này *đã* xử lý
tốt (ADR + `author` field + không giấu), nhưng là xử lý phản ứng.

**4. Automation từ ngày 1, không hoãn tới Phase 6.**

Ở đây `.github/workflows/` bị lịch trình hoãn đến Phase 6 trong khi
`make lint && make test && make validate` chạy được từ Phase 3. Nguyên tắc: **mỗi khi bạn viết một
rule bằng văn xuôi, hỏi ngay "cái này thành lệnh được không?"** — `make validate` là ví dụ hoàn hảo,
còn rule 4.1 (pipeline bất biến) thì vẫn đang chỉ là lời cầu nguyện.

**5. Một sự thật một chỗ.** `command.md` là bản sao cây thư mục của `architecture.md`, lệch nhau, và
đã bị xoá trong phiên này. Trước khi tạo file docs mới, hỏi: file này có đang lặp lại file nào không?

## C. Bổ sung — chưa có ở dự án này

**1. `docs/journal.md` — nhật ký ngắn cho những thứ không xứng đáng một ADR.** ADR có ngưỡng khá cao
(phải có trade-off), nên rất nhiều thứ "tôi đã thử X, không được, vì Y" bị rơi mất. Một dòng/ngày:
*ngày — đã thử gì — kết quả — bỏ hay giữ*. Rẻ, và nó ngăn bạn thử lại đúng ngõ cụt sau 6 tuần.

**2. `docs/risks.md` — cái gì có thể giết dự án, ai kiểm tra, khi nào.** Với dự án này lẽ ra sẽ có 3
dòng: *dữ liệu có được ra ngoài không* (đã hỏi, tốt), *quota provider* (đã bỏ sót → mất Phase 4),
*model bị khai tử* (đã bỏ sót → ADR-0007). Cả hai cái bỏ sót đều đoán được trước.

**3. Tách "cost tier" ra khỏi code.** Bất cứ dự án nào gọi API tính tiền: một biến duy nhất điều
khiển quy mô chạy, và mọi script đều tôn trọng nó. Không bao giờ để "chạy thử" và "chạy thật" chỉ
khác nhau ở việc bạn có nhớ thêm cờ hay không.

**4. Ngưỡng "khi nào thì file này quá dài".** `docs/progress/phase-2.md` 245 dòng, `phase-4.md` 216.
Vẫn ổn vì có index, nhưng đặt luật trước: quá ~200 dòng thì phần chi tiết tách xuống phụ lục, entry
giữ lại phần một session mới *bắt buộc* phải đọc.

**5. Một `Makefile` target `make doctor`.** Kiểm tra môi trường: DB có chạy không, migration có mới
nhất không, `.env` thiếu key nào, model trong `.env` có gọi được không, corpus lock có khớp không.
Chạy trong 5 giây, tiết kiệm 20 phút debug mỗi lần bạn quay lại dự án sau 2 tuần.

**6. Với agent: viết CLAUDE.md ở thể mệnh lệnh, kèm lý do ngắn.** Cái này bạn đã làm tốt sẵn. Điểm
nâng thêm: mỗi rule nên nói rõ **thất bại trông như thế nào**. "Không sửa pipeline đã có kết quả"
yếu hơn "sửa nó sẽ khiến hai dòng trong leaderboard không còn so sánh được, và không ai phát hiện ra".

## D. Thứ tự khởi động dự án mới

1. **Reality check script** — xuyên qua mọi phụ thuộc ngoài. Vứt đi sau.
2. **`docs/risks.md`** — 5 dòng, gồm chi phí/quota và cái gì giết dự án.
3. **`PLAN.md`** — chỉ viết sau khi 1 và 2 xong, và mỗi phase có DoD là *một file commit được*.
4. **`CLAUDE.md`** — thể hiện tại, kèm bảng "cái gì chưa tồn tại".
5. **CI + `make doctor` + `/phase-done`** — trước khi viết dòng code nghiệp vụ đầu tiên.
6. Bắt đầu Phase 1.

## E. Khi nào *không* cần bộ này

Bộ này có chi phí thật — dự án hiện tại có ~2000 dòng tài liệu cho 47 file source. Nó xứng đáng vì
đây là dự án **có số đo và có so sánh giữa các phương án**. Với một script chạy một lần, một PoC 2
ngày, hay CRUD không có gì để đo, thì áp nguyên xi vào là nghi thức thừa. Phần lõi vẫn nên giữ trong
mọi trường hợp: **CLAUDE.md ở thì hiện tại + ADR khi có trade-off + DoD là artefact**. Ba thứ đó rẻ.
Phần phase-gate + progress log/phase mới là phần đắt.

---

## Việc còn treo sau buổi này

- Đóng gói phần 3 thành một repo template dùng được luôn (`CLAUDE.md` khung, `PLAN.md` khung,
  `risks.md`, `.claude/commands/{phase-done,new-adr}.md`, `ci.yml`, `make doctor`) — **đã đề nghị,
  chưa làm.**
- Hook `PreToolUse` chặn sửa pipeline đã có `results/` — đợi Phase 4 có số.
- `.github/workflows/ci.yml` — đợi Phase 4 có số.
