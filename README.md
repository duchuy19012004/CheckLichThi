# 🔔 Bot Thông Báo Lịch Thi HUFLIT

Bot tự động kiểm tra lịch thi trên [portal.huflit.edu.vn](https://portal.huflit.edu.vn/Home/Exam) và gửi thông báo qua Telegram khi có lịch thi mới hoặc thay đổi.

---

## 📁 Cấu Trúc Dự Án

```
lichthi/
├── bot.py              # Điểm khởi chạy chính, lên lịch kiểm tra định kỳ
├── fetcher.py          # Lấy HTML lịch thi từ portal HUFLIT
├── parser.py           # Phân tích HTML, trích xuất và băm dữ liệu lịch thi
├── telegram_notify.py  # So sánh thay đổi và gửi thông báo Telegram
├── config.json         # File cấu hình (cookie, token Telegram, v.v.)
├── requirements.txt    # Các thư viện Python cần thiết
└── state.json          # Lưu trạng thái hash lịch thi (tự động tạo)
```

---

## ⚙️ Cài Đặt

### 1. Yêu Cầu Python

Cần Python **3.10 trở lên**.

```bash
pip install -r requirements.txt
```

---

### 2. Lấy Cookie Từ Portal HUFLIT

Bot cần cookie phiên đăng nhập để truy cập dữ liệu lịch thi của bạn.

1. Đăng nhập vào [portal.huflit.edu.vn](https://portal.huflit.edu.vn/Home/Exam) trên trình duyệt (Chrome / Firefox)
2. Nhấn `F12` → chuyển sang tab **Network** (Mạng)
3. Tải lại trang bằng `F5`
4. Click vào request đầu tiên (thường là `Exam` hoặc URL portal)
5. Trong phần **Request Headers**, sao chép giá trị của trường `Cookie`
6. Dán vào `config.json`, thay thế `YOUR_COOKIE_HERE`

> ⚠️ **Lưu ý:** Cookie thường hết hạn sau **1–2 ngày**. Nếu bot không hoạt động, hãy cập nhật cookie mới.

---

### 3. Tạo Bot Telegram

1. Mở Telegram, tìm kiếm **@BotFather**
2. Gửi lệnh `/newbot`
3. Đặt tên cho bot (ví dụ: `LichThiBot`)
4. Sao chép **Bot Token** (dạng: `123456:ABC-...`) vào `config.json`
5. Tìm bot của bạn trên Telegram và gửi bất kỳ tin nhắn nào (ví dụ: `/start`)
6. Lấy **Chat ID** bằng một trong hai cách:
   - Truy cập: `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - Hoặc nhắn tin cho bot **@userinfobot**
7. Điền **Chat ID** vào `config.json`

---

### 4. Chỉnh Sửa `config.json`

```json
{
  "cookie": "ASP.NET_SessionId=xxx; PortalAuth=yyy; ...",
  "telegram_bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
  "telegram_chat_id": "YOUR_CHAT_ID",
  "academic_year": "2025-2026",
  "semester": "HK1",
  "check_interval_minutes": 15,
  "portal_url": "https://portal.huflit.edu.vn/Home/Exam"
}
```

| Trường                   | Mô tả                                                      |
| ------------------------ | ---------------------------------------------------------- |
| `cookie`                 | Cookie đăng nhập lấy từ portal HUFLIT                      |
| `telegram_bot_token`     | Token Telegram Bot lấy từ @BotFather                       |
| `telegram_chat_id`       | Chat ID của bạn (có thể là số âm, ví dụ: `-1001234567890`) |
| `academic_year`          | Năm học cần theo dõi (ví dụ: `2025-2026`)                  |
| `semester`               | Học kỳ: `HK1`, `HK2`, hoặc `HK3`                           |
| `check_interval_minutes` | Tần suất kiểm tra tính bằng phút (mặc định: `15`)          |

---

## ▶️ Chạy Bot

```bash
python bot.py
```

Bot sẽ kiểm tra lịch thi ngay lập tức khi khởi động, sau đó lặp lại theo chu kỳ đã cấu hình.

Để dừng bot: nhấn `Ctrl+C` trong terminal.

---

## 🔄 Cách Hoạt Động

```
Bot khởi động
  → Đọc config.json
  → Gửi GET request kèm cookie → Lấy HTML trang lịch thi
  → POST form (năm học + học kỳ) → Lấy HTML lịch thi đã lọc
  → Phân tích HTML → Trích xuất bảng lịch thi
  → Tính hash SHA-256 của lịch thi
  → So sánh với hash đã lưu trong state.json
     → Giống nhau : Không làm gì
     → Khác nhau  : Gửi thông báo Telegram → Lưu hash mới vào state.json
  → Lặp lại sau N phút
```

---

## 🗂️ Mô Tả Các Module

| File                 | Chức năng                                                          |
| -------------------- | ------------------------------------------------------------------ |
| `bot.py`             | Điều phối toàn bộ luồng xử lý; sử dụng APScheduler để chạy định kỳ |
| `fetcher.py`         | Thực hiện GET và POST đến portal HUFLIT để lấy HTML lịch thi       |
| `parser.py`          | Dùng BeautifulSoup phân tích HTML, tính hash và định dạng tin nhắn |
| `telegram_notify.py` | So sánh hash cũ/mới, gửi thông báo và cập nhật `state.json`        |

---

## 🛠️ Xử Lý Sự Cố

| Vấn đề                       | Nguyên nhân có thể            | Giải pháp                           |
| ---------------------------- | ----------------------------- | ----------------------------------- |
| Không lấy được HTML          | Cookie đã hết hạn             | Lấy cookie mới từ trình duyệt       |
| Lỗi gửi Telegram             | Token hoặc Chat ID sai        | Kiểm tra lại trong `config.json`    |
| Không tìm thấy bảng lịch thi | Portal thay đổi cấu trúc HTML | Kiểm tra selector trong `parser.py` |
| Bot chạy nhưng không gửi tin | Lịch thi chưa thay đổi        | Đây là hành vi bình thường          |

---

## 📌 Lưu Ý Quan Trọng

- **Thời hạn cookie:** Cookie HUFLIT thường hết hạn sau **1–2 ngày**, cần cập nhật thủ công.
- **Giới hạn request:** Không nên đặt `check_interval_minutes` quá nhỏ (khuyến nghị ≥ 10 phút) để tránh bị portal chặn IP.
- **File `state.json`:** Lưu hash lịch thi hiện tại. Xóa file này để buộc bot gửi thông báo ngay lần kiểm tra tiếp theo (dù lịch thi chưa đổi).

## Ảnh chụp lịch thi từ Portal

![alt text](image-1.png)

## Ảnh chụp lịch thi từ Telegram

![alt text](image.png)

## Ngoài lề

- Cảm ơn Cursor,Codex,Antigravity
