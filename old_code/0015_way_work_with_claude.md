# cách tôi làm việc với claude

hạn chế sửa những gì tôi viết trừ khi bạn viết được hay hơn hay ý tốt hơn

---

## nguyên tắc

mọi chiến thắng ở con đường sai lầm , đều là thất bại - do hacker viẻt thai có trích

nên cố gắng đi better path hơn thôi , ko perfect được và quan trọng là có plan , kể cả bad plan , còn hơn ko có plan - trong cờ vua

các file ở old code được ignore để claude khỏi đưa vào context gây ngập token

---

## sprint

sprint nên có mục tiêu lớn vừa , ko bị nhỏ quá như task để có plan có tầm nhìn xa hơn là task , hiện tại chưa cần estimate, cuối sprint cần retrospective , planning cho sprint sau 

sprint nên ưu tiên feature, thay vì cố theo đuổi technique tech 

việc đầu tiên là lên plan cho sprint này , hết sprint có thể có demo , feedback , retro để xem claude đã làm tốt hay ko tốt gì để bổ sung vào claude.md

sprint sau , mình có thể brainstorm , sprint planning

đưa ra các task cụ thể rồi nhờ claude break down task

việc đưa ra plan , và hạn chế chỉnh sửa plan mid run rất quan trọng , vì claude nó có flow nghĩ rất liền mạch , việc sửa 1 phase ở plan sẽ cần sửa rất nhiều ở phase sau , mấy file md progress và spec bị mâu thuẫn ; nên bước plan ở mỗi sprint rất rất quan trọng , và cần chốt

### khi phát hiện plan sai giữa sprint

đừng vá 1 phase . chính cái vá lẻ đó tạo ra mâu thuẫn spec/progress

hai lựa chọn sạch hơn :
- chạy nốt phase hiện tại rồi **re-plan lại toàn bộ phần còn lại** (viết lại , ko patch)
- hoặc cắt sprint sớm và mở sprint mới

plan sai là output hợp lệ của sprint , ko phải thất bại

### trước khi chốt plan , hỏi 1 câu

> plan này có giả định gì , rủi ro ở đâu , và cái gì sẽ chứng minh nó sai sớm nhất ?

phát hiện plan sai ở bước plan rẻ hơn phát hiện ở phase 4 rất nhiều

---

## break down

mình có sprint rồi thì mình chia phase (hơi giống break down task nhỉ) , nói chung cái gì quá phức tạp , nên break down nó thành 1 cấp nhỏ hơn , đương nhiên ko break down quá mức , đến mức nó thiếu sự liền mạch , kết nối giữa các mảnh , và ko tạo room cho innovate (vì 1 output có nhiều con đường đến đó) , và mất đi tầm nhìn objective lớn hơn khi task micro quá ; nên để ý là keep it simple (cũng chỉ là input , output mà) và cần đủ thành phần (plan , eval , run , etc)

đi từng task 1 , rất có thể mới vỡ ra được con đường phía trước , brainstorm được ý hay hơn sau khi khám phá được những thứ mới khi làm xong task cũ

---

## eval

ở claude.md mình có bổ sung về eval rất quan trọng , để đo được việc cải thiện có cải thiện baseline ko ; chứng minh các cách là khả thi

**eval phải chốt cùng lúc chốt plan , ko phải viết sau khi chạy**
viết eval sau khi thấy kết quả thì nó chỉ là lời tự khen chứ ko đo được gì . baseline + tiêu chí pass phải nằm trong plan đã chốt

### rõ ràng nhưng đừng rigid

tiêu chí rõ ràng là điểm cộng vì nó đo đạc được , nhưng đừng cứng quá

nguyên tắc chính : **đo output , đừng đo đường đi**

- "latency p95 < 200ms" , "8/10 case pass" , "ko regression so với baseline" — đo được , vẫn chừa nhiều đường đi tới đó
- "phải dùng cách X , phải theo đúng 5 bước này" — vừa khó đo vừa giết room innovate

cách giữ nó ko cứng :

- **số cần có lý do , ko phải cho đẹp** . đặt 90% mà ko giải thích được tại sao ko phải 85% thì con số đó là giả . thà ghi "tốt hơn baseline rõ rệt , baseline = X" còn thật hơn
- **cho phép tiêu chí sai** . chạy xong phát hiện đo nhầm thứ (metric lên nhưng thực tế tệ hơn) — ghi nhận là finding của sprint , sửa ở retro , đừng ép kết quả cho khớp con số đã chốt . nhưng sửa thì ghi rõ *sửa vì đo sai* , ko phải vì trượt
- **ko phải cái gì cũng ép thành số** . có thứ chỉ cần 1 câu judgment rõ ràng ("đọc code này 6 tháng sau còn hiểu ko") — vẫn là tiêu chí , vẫn review được . ép nó thành metric giả mới là rigid
- **ít mà chuẩn** . 2-3 tiêu chí thật sự quyết định pass/fail . dài 10 dòng thì lần sau sẽ bỏ qua hết

---

## cấu trúc file

mình đã thiết kế claude có
- claude.md (có cả DoD để review)
- plan.md
- progress.md
- và các file ở folder progress lưu được những gì nó làm

mình có để ở ./claude , agent eval , ko để ở claude.md để nó khỏi quên lost in the middle hoặc khi context dài

### progress/ nên append-only , 1 file / phase

cửa sổ mới chỉ cần đọc plan + file phase gần nhất + git log , ko phải nuốt cả lịch sử — đúng cái vấn đề token đang né

### git history là nguồn sự thật , file md có thể drift

khi mở cửa sổ mới mà progress.md và commit mâu thuẫn → tin commit

để map được : mỗi phase xong = 1 commit , message có phase ID

### DoD có 1 dòng cứng

**phase chưa xong nếu eval chưa chạy**

ko có dòng này thì eval sẽ là thứ đầu tiên bị bỏ khi vội

---

## các câu hay dùng

mình thường quên mất đã từng làm gì , hoặc ko muốn phí token ở cửa sổ claude hiện tại , sang cửa sổ mới và

```
read progress, plan , phases , commits history and tell me what you gonna do next
```

nếu vẫn khó hiểu :

```
what u recommend to do next , i follow
```

sau khi claude đã làm hết , nó sẽ thông báo nhiều , nhưng nếu khó hiểu , gõ

```
bạn đã làm những gì , giờ cần gì và làm gì tiếp
```

nếu vẫn khó hiểu , gõ

```
tôi cần làm gì
```