# Chạy hệ thống — cổng, tắt, máy chủ từ xa

Đường đi thường ngày nằm ở [README.vi.md](../README.vi.md): `./scripts/start.sh`, rồi mở
http://127.0.0.1:8501. File này chỉ cần đến khi một cổng bị chiếm, khi server vẫn còn chạy dù bạn
tưởng đã tắt, hoặc khi máy chủ không phải cái đang ở trước mặt bạn.

## Cổng

Cả hai cổng đều đổi được:

```bash
API_PORT=8080 UI_PORT=8600 ./scripts/start.sh
```

## Tắt

```bash
./scripts/start.sh --stop
```

Lệnh này giải phóng cổng **theo cổng chứ không chỉ theo pidfile**, nên dọn được cả API hoặc UI đã bật
tay bằng `make api` / `make ui` ở terminal khác. Postgres vẫn chạy — muốn tắt thì `make down`.

Nếu muốn chạy tách rời thì `make api` và `make ui` ở hai terminal vẫn dùng được như cũ. Mọi target
chạy từ thư mục gốc; Makefile tự `cd backend`.

## Chạy trên máy chủ từ xa

Các URL `127.0.0.1` — và cả `0.0.0.0` / `localhost` mà Streamlit in ra — chỉ mở được bằng trình duyệt
**ngay trên máy chủ đó**. `0.0.0.0` là địa chỉ bind, nghĩa là "nghe trên mọi interface", không phải
một đích đến để truy cập; từ laptop của bạn thì cả nó lẫn `localhost` đều trỏ về chính laptop, nơi
không có gì chạy.

Hãy dùng địa chỉ của máy chủ (`http://<ip-máy-chủ>:8501`). **Trên EC2 script tự dò ra địa chỉ này** —
nó hỏi instance metadata service lấy public IPv4 rồi in thêm dòng `from your own browser:` bên cạnh
các URL local. URL đó vẫn cần cổng 8501 được mở trong security group của instance. Ở môi trường khác
(hoặc sau proxy, hoặc muốn dùng tên DNS riêng), tự đặt `PUBLIC_HOST=<ip-hoặc-hostname>` thì script
dùng đúng giá trị đó.

**API chỉ bind vào localhost** nên không truy cập được theo cách này. Đây là cố ý: API không có auth
và mỗi lệnh gọi `/chat` tiêu tốn một key có tính phí. Trang Streamlit gọi API từ phía máy chủ nên UI
vẫn chạy bình thường. Muốn gọi thẳng API thì mở tunnel:

```bash
ssh -L 8000:127.0.0.1:8000 <user>@<server>
```
