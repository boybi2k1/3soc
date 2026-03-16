# 3SOC — Hệ thống phát hiện vi phạm chủ quyền bằng AI

> **Backend** — FastAPI + Python + YOLOv8 + MySQL
> Phát hiện tự động các biểu tượng vi phạm chủ quyền Việt Nam trong ảnh và video: Cờ 3 sọc, Đường lưỡi bò, Bản đồ sai.

---

## Mục lục

1. [Tổng quan hệ thống](#1-tổng-quan-hệ-thống)
2. [Yêu cầu cài đặt](#2-yêu-cầu-cài-đặt)
3. [Cách chạy dự án](#3-cách-chạy-dự-án)
4. [Tổ chức thư mục (giải thích chi tiết)](#4-tổ-chức-thư-mục)
5. [Cơ sở dữ liệu](#5-cơ-sở-dữ-liệu)
6. [API Endpoints](#6-api-endpoints)
7. [Các luồng chức năng chính](#7-các-luồng-chức-năng-chính)
8. [Xác thực & Phân quyền](#8-xác-thực--phân-quyền)
9. [Mô hình AI](#9-mô-hình-ai)
10. [Tài khoản mặc định](#10-tài-khoản-mặc-định)

---

## 1. Tổng quan hệ thống

Dự án **3soc** là phần **Backend** (máy chủ) của hệ thống. Nó đảm nhận:

- Nhận video/ảnh từ phía người dùng (qua Frontend `admin-web`)
- Chạy 3 mô hình AI (YOLO) để phát hiện vi phạm
- Lưu kết quả vào database MySQL và ổ đĩa
- Cung cấp API REST, WebSocket, SSE cho Frontend

```
Frontend (admin-web)
        │
        │  HTTP / WebSocket / SSE
        ▼
Backend (3soc) ← FastAPI, port 8000
        │
        ├── MySQL Database (lưu user, video, detection)
        ├── Ổ đĩa /uploads/ (lưu file video, ảnh vi phạm)
        └── AI Models (3soc.pt, duongluoibo.pt, vnmap.pt)
```

---

## 2. Yêu cầu cài đặt

| Phần mềm | Phiên bản | Ghi chú |
|----------|-----------|---------|
| Python | 3.10+ | Bắt buộc |
| MySQL | 8.0+ | Cần tạo database trước |
| CUDA (GPU) | Tuỳ chọn | Không có thì dùng CPU, chậm hơn |

**Thư viện Python chính:**

| Thư viện | Mục đích |
|----------|----------|
| `fastapi` | Framework API chính |
| `uvicorn` | Máy chủ chạy FastAPI |
| `ultralytics` | Chạy mô hình YOLO |
| `opencv-python` | Đọc/xử lý video, ảnh |
| `torch` | PyTorch — nền tảng deep learning |
| `sqlalchemy` | ORM kết nối database |
| `pymysql` | Driver kết nối MySQL |
| `python-jose` | Tạo và xác thực JWT token |
| `passlib[argon2]` | Mã hoá mật khẩu (Argon2) |
| `psutil` | Đọc thông số CPU, RAM |

---

## 3. Cách chạy dự án

### Bước 1: Tạo database MySQL

```sql
CREATE DATABASE detect_3soc CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### Bước 2: Cấu hình kết nối database

Tạo file `.env` ở thư mục gốc (hoặc chỉnh sửa nếu đã có):

```env
DATABASE_URL=mysql+pymysql://root:YOUR_PASSWORD@localhost/detect_3soc
SECRET_KEY=your-secret-key-change-this-in-production
```

> Thay `YOUR_PASSWORD` bằng mật khẩu MySQL của bạn.

### Bước 3: Đặt file mô hình AI

Đặt 3 file `.pt` vào thư mục `models/`:
```
3soc/
└── models/
    ├── 3soc.pt
    ├── duongluoibo.pt
    └── vnmap.pt
```

### Bước 4: Chạy server

**Cách 1 — Windows (tự động):**
```bat
run.bat
```
Script này tự động: tạo môi trường ảo Python, cài thư viện, tạo thư mục `uploads/`, khởi động server.

**Cách 2 — Thủ công:**
```bash
# Tạo môi trường ảo
python -m venv venv

# Kích hoạt (Windows)
venv\Scripts\activate

# Cài thư viện
pip install -r requirements.txt

# Chạy server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Bước 5: Kiểm tra hoạt động

Mở trình duyệt: **http://localhost:8000/docs**

Nếu thấy giao diện Swagger UI → server đã chạy thành công ✅

---

## 4. Tổ chức thư mục

```
3soc/
│
├── app/                        ← Toàn bộ mã nguồn ứng dụng
│   ├── main.py                 ← Điểm khởi động: tạo app FastAPI, load model AI,
│   │                              đăng ký router, xử lý WebSocket, SSE
│   │
│   ├── config.py               ← Cấu hình đường dẫn (thư mục uploads)
│   │
│   ├── db/                     ← Tầng database
│   │   ├── db.py               ← Kết nối MySQL, tạo bảng, seed user mặc định
│   │   └── models.py           ← Định nghĩa cấu trúc bảng (User, VideoFile, Detection)
│   │
│   ├── routers/                ← Xử lý các API endpoint
│   │   ├── users.py            ← Đăng ký, đăng nhập, quản lý user
│   │   └── files.py            ← Upload video, xem danh sách, detect, xoá
│   │
│   ├── schemas/                ← Định nghĩa kiểu dữ liệu vào/ra của API
│   │   ├── user.py             ← Schema cho user (tạo, cập nhật, response...)
│   │   ├── file.py             ← Schema cho file video
│   │   └── response.py         ← Schema dùng chung (pagination, detection result...)
│   │
│   └── utils/                  ← Các tiện ích dùng chung
│       ├── auth.py             ← Mã hoá mật khẩu, tạo/xác thực JWT token
│       ├── tasks.py            ← Chạy mô hình AI trên frame/ảnh
│       └── websocket_handler.py← Quản lý WebSocket, nhận frame, lưu vi phạm
│
├── models/                     ← File mô hình AI (*.pt) — KHÔNG commit lên Git
│   ├── 3soc.pt
│   ├── duongluoibo.pt
│   └── vnmap.pt
│
├── uploads/                    ← Thư mục lưu file người dùng upload (tạo tự động)
│   ├── {video_id}.mp4          ← Video đã upload
│   ├── temp/                   ← Ảnh tạm thời (xoá sau khi detect xong)
│   └── violations/             ← Ảnh và metadata vi phạm
│       └── {video_id}/
│           ├── ts_00001250_f42.jpg          ← Ảnh frame vi phạm
│           └── ts_00001250_f42_metadata.json← Thông tin vi phạm của frame đó
│
├── venv/                       ← Môi trường Python ảo (tạo tự động, KHÔNG commit)
│
├── requirements.txt            ← Danh sách thư viện Python cần cài
├── run.bat                     ← Script khởi động trên Windows
├── infer_yolo.py               ← Script test chạy AI độc lập (không liên quan server)
├── .env                        ← Cấu hình môi trường (DATABASE_URL, SECRET_KEY)
└── .gitignore
```

### Giải thích luồng đọc code cho người mới

> **Muốn hiểu server khởi động thế nào?** → Đọc `app/main.py`
> **Muốn hiểu database có gì?** → Đọc `app/db/models.py`
> **Muốn hiểu API user (login, register...)?** → Đọc `app/routers/users.py`
> **Muốn hiểu AI chạy thế nào?** → Đọc `app/utils/tasks.py` và `app/utils/websocket_handler.py`
> **Muốn hiểu dữ liệu vào/ra của API?** → Đọc `app/schemas/`

---

## 5. Cơ sở dữ liệu

Database: **MySQL**, tên: `detect_3soc`
ORM: **SQLAlchemy** — Python tự tạo bảng khi khởi động (`init_db()` trong `app/db/db.py`)

### Bảng `users` — Lưu thông tin người dùng

| Cột | Kiểu dữ liệu | Mô tả |
|-----|-------------|-------|
| `id` | INT (PK) | ID tự tăng |
| `username` | VARCHAR(100) | Tên đăng nhập, **duy nhất** |
| `email` | VARCHAR(255) | Email, **duy nhất** |
| `password_hash` | VARCHAR(255) | Mật khẩu đã mã hoá (Argon2) |
| `role` | VARCHAR(50) | Vai trò: `"user"` hoặc `"admin"` |
| `is_active` | BOOLEAN | Tài khoản có hoạt động không |
| `created_at` | DATETIME | Thời gian tạo |
| `updated_at` | DATETIME | Thời gian cập nhật gần nhất |

---

### Bảng `video_files` — Lưu thông tin video đã upload

| Cột | Kiểu dữ liệu | Mô tả |
|-----|-------------|-------|
| `id` | VARCHAR(64) (PK) | ID video (do Frontend tạo bằng `Date.now()`) |
| `filename` | VARCHAR(255) | Tên file gốc (ví dụ: `video.mp4`) |
| `filepath` | VARCHAR(500) | Đường dẫn web (ví dụ: `/uploads/1234567890.mp4`) |
| `user_id` | INT (FK → users.id) | Người upload |
| `file_size` | INT | Dung lượng file (bytes) |
| `duration` | FLOAT | Thời lượng video (giây) |
| `status` | VARCHAR(50) | Trạng thái: `uploaded` / `processing` / `completed` / `error` |
| `detection_id` | VARCHAR(64) | Liên kết đến thư mục lưu vi phạm |
| `created_at` | DATETIME | Thời gian upload |

---

### Bảng `detections` — Lưu kết quả phát hiện theo batch

| Cột | Kiểu dữ liệu | Mô tả |
|-----|-------------|-------|
| `id` | INT (PK) | ID tự tăng |
| `detection_id` | VARCHAR(64) | Mã phiên detect, **duy nhất** |
| `source` | VARCHAR(255) | File nguồn |
| `created_at` | DATETIME | Thời gian tạo |
| `results` | JSON | Danh sách tất cả bounding box tìm được |
| `summary` | JSON | Thống kê theo từng model |

---

### File vi phạm lưu trên ổ đĩa (không phải trong DB)

Khi phát hiện vi phạm, hệ thống lưu vào `uploads/violations/{video_id}/`:

**Ảnh frame:** `ts_00001250_f42.jpg`
**Metadata JSON:** `ts_00001250_f42_metadata.json`

Nội dung file metadata:
```json
{
  "frame_number": 42,
  "timestamp": 1250.00,
  "detections": [
    {
      "x": 100,
      "y": 200,
      "width": 80,
      "height": 60,
      "label": "co3soc",
      "confidence": 0.9234
    }
  ]
}
```

---

### Sơ đồ quan hệ

```
users (1) ──────────── (N) video_files
  id ◄──────────────────── user_id
```

---

## 6. API Endpoints

**Base URL:** `http://localhost:8000`
**Tài liệu tương tác:** http://localhost:8000/docs

### Nhóm User — `/api/users`

| Method | Endpoint | Cần đăng nhập | Mô tả |
|--------|----------|---------------|-------|
| POST | `/api/users/register` | Không | Đăng ký tài khoản mới |
| POST | `/api/users/login` | Không | Đăng nhập → nhận JWT token |
| GET | `/api/users/me` | Có | Xem thông tin bản thân |
| POST | `/api/users/change-password` | Có | Đổi mật khẩu |
| POST | `/api/users/logout` | Có | Đăng xuất |
| GET | `/api/users` | Admin | Danh sách tất cả user (phân trang) |
| GET | `/api/users/{id}` | Admin | Xem chi tiết một user |
| PUT | `/api/users/{id}` | Admin | Sửa thông tin user |
| DELETE | `/api/users/{id}` | Admin | Xoá user |

---

### Nhóm File — `/api/files`

| Method | Endpoint | Cần đăng nhập | Mô tả |
|--------|----------|---------------|-------|
| POST | `/api/files/upload` | Có | Upload video (multipart/form-data) |
| GET | `/api/files` | Có | Danh sách file (user thấy của mình, admin thấy tất cả) |
| DELETE | `/api/files/{id}` | Có | Xoá file video |
| POST | `/api/files/detect-image` | Tuỳ chọn | Upload ảnh → detect ngay, trả kết quả |
| GET | `/api/files/{id}/detect-stream` | Không | **SSE stream** kết quả detect video theo batch |

---

### WebSocket & SSE (Real-time)

| Giao thức | Đường dẫn | Mô tả |
|-----------|-----------|-------|
| WebSocket | `ws://localhost:8000/realtime` | Gửi frame ảnh, nhận kết quả detect real-time |
| SSE (GET) | `/file-stream/{video_id}` | Nhận thông báo khi có vi phạm được lưu |

---

### Static Files

| Đường dẫn | Mô tả |
|-----------|-------|
| `/uploads/*` | Truy cập file video, ảnh vi phạm đã lưu |

---

## 7. Các luồng chức năng chính

### Luồng 1: Phát hiện real-time qua WebSocket

Đây là luồng chính khi người dùng phát video trực tiếp trên trang chủ:

```
[Frontend] Chọn file video
    │
    ▼
[Frontend] Upload video → POST /api/files/upload
    │  Server lưu file vào uploads/, tạo record DB
    │
    ▼
[Frontend] Mở WebSocket → ws://localhost:8000/realtime
    │
    ▼
[Frontend] Mỗi 200ms: chụp 1 frame từ video đang phát
           Gửi qua WebSocket dạng JSON:
           {
             "type": "frame",
             "frameData": "data:image/jpeg;base64,...",
             "timestamp": 1250,
             "videoId": "1234567890"
           }
    │
    ▼
[Backend] WebSocketManager.handle_frame():
    │  1. Giải mã base64 → numpy array
    │  2. Chạy 3 model YOLO song song (asyncio.to_thread)
    │  3. Gộp tất cả bounding box lại
    │  4. Nếu có vi phạm → đẩy vào save_queue
    │  5. Gửi kết quả ngay cho client:
    │     { "type": "detection", "timestamp": 1250,
    │       "boxes": [{"x":100,"y":200,"width":80,"height":60,
    │                  "label":"co3soc","confidence":0.92}] }
    │
    ▼
[Backend] save_worker() (chạy nền):
    │  - Chờ item từ save_queue
    │  - Kiểm tra cooldown 2 giây (tránh lưu quá nhiều)
    │  - Lưu frame JPEG vào uploads/violations/{video_id}/
    │  - Lưu metadata JSON cạnh file ảnh
    │  - Gửi event vào sse_queues[video_id]
    │
    ▼
[Backend] SSE /file-stream/{video_id}:
    Gửi event tới Frontend:
    { "type": "violation", "data": { frame_number, timestamp,
                                     image_path, detections } }
    │
    ▼
[Frontend] Hiển thị thumbnail vi phạm ở cuối trang
```

---

### Luồng 2: Phát hiện batch video đã upload (SSE)

Khi người dùng bấm "Chon xem chi tiet" ở trang Files:

```
[Frontend] Bấm "Scan" → GET /api/files/{id}/detect-stream
    │
    ▼
[Backend] Kiểm tra: đã có kết quả cache chưa?
    │
    ├── CÓ CACHE → Stream toàn bộ vi phạm đã lưu ngay:
    │    SSE: init → metadata → violation × N → complete
    │
    └── CHƯA CÓ → Bắt đầu detect:
         
         1. Thread read_frames(): đọc video, lấy 1 frame mỗi 0.25s
         2. Thread detect_worker(): gọi run_detection_on_frame()
         3. Kết quả → lưu file JPEG + JSON → yield SSE event
         4. Kết thúc: status = "completed"
         SSE: init → metadata → violation × N → complete
```

---

### Luồng 3: Phát hiện ảnh tĩnh

```
[Frontend] Chọn file ảnh → POST /api/files/detect-image
    │
    ▼
[Backend] Lưu ảnh tạm vào uploads/temp/
    │
    ▼
[Backend] Chạy 3 model YOLO trên ảnh
    │
    ▼
[Backend] Xoá file tạm
    │
    ▼
[Backend] Trả về kết quả ngay:
    { "filename": "...", "detections": [...], "timestamp": "..." }
    │
    ▼
[Frontend] Vẽ bounding box lên ảnh bằng canvas
```

---

### Luồng 4: Đăng nhập

```
[Frontend] Nhập username + password → POST /api/users/login
    │
    ▼
[Backend] Tìm user trong DB theo username
    │
    ▼
[Backend] So sánh mật khẩu với Argon2 (verify_password)
    │
    ▼
[Backend] Tạo JWT token (hết hạn sau 7 ngày):
    payload = { "sub": "admin", "user_id": 1, "role": "admin" }
    │
    ▼
[Backend] Trả về: { "access_token": "...", "token_type": "bearer", "user": {...} }
    │
    ▼
[Frontend] Lưu token vào localStorage
           Tất cả request sau sẽ gửi kèm: Authorization: Bearer <token>
```

---

## 8. Xác thực & Phân quyền

**Thuật toán:** JWT (JSON Web Token) — HS256
**Mã hoá mật khẩu:** Argon2 (mạnh hơn bcrypt)
**Thời hạn token:** 7 ngày

### JWT token chứa thông tin:
```json
{
  "sub": "admin",
  "user_id": 1,
  "role": "admin",
  "exp": 1234567890
}
```

### Cách kiểm tra quyền:

| Dependency | Tác dụng |
|-----------|---------|
| `get_current_user_from_token` | Đọc token từ header `Authorization: Bearer ...`, giải mã, trả về thông tin user |
| `require_admin` | Gọi `get_current_user_from_token`, kiểm tra thêm `role == "admin"`, nếu không → HTTP 403 |

---

## 9. Mô hình AI

Ba mô hình **YOLOv8/v11** được load khi server khởi động:

| Tên model | File | Phát hiện |
|-----------|------|----------|
| `co3soc` | `models/3soc.pt` | Cờ 3 sọc (cờ Việt Nam Cộng Hoà) |
| `duongluoibo` | `models/duongluoibo.pt` | Đường lưỡi bò (bản đồ 9 đoạn của Trung Quốc) |
| `vnmap` | `models/vnmap.pt` | Bản đồ Việt Nam sai lệch |

**Kết quả detect (bounding box):**
```json
{
  "x": 100,
  "y": 200,
  "width": 80,
  "height": 60,
  "label": "co3soc",
  "confidence": 0.9234
}
```

**Màu hiển thị trên Frontend:**
- `co3soc` → 🔴 Đỏ
- `duongluoibo` → 🟢 Xanh lá
- `vnmap` → 🔵 Xanh dương

**GPU/CPU:** Tự động dùng CUDA (GPU) nếu có, fallback sang CPU nếu không.

---

## 10. Tài khoản mặc định

Khi server khởi động lần đầu, hệ thống tự tạo 2 tài khoản:

| Username | Mật khẩu | Vai trò |
|----------|----------|---------|
| `admin` | `admin123` | Admin (toàn quyền) |
| `user` | `user123` | User thường |

> **Lưu ý bảo mật:** Hãy đổi mật khẩu ngay sau khi deploy lên production!
