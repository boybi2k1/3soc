# 3SOC — Hệ thống phát hiện vi phạm chủ quyền bằng AI

> **Backend** — FastAPI + Python + YOLOv8 + MySQL
> Phát hiện tự động các biểu tượng vi phạm chủ quyền Việt Nam trong ảnh và video: Cờ 3 sọc, Đường lưỡi bò, Bản đồ sai.

---

## Mục lục

1. [Tổng quan hệ thống](#1-tổng-quan-hệ-thống)
2. [Yêu cầu cài đặt](#2-yêu-cầu-cài-đặt)
3. [Cách chạy dự án](#3-cách-chạy-dự-án)
4. [Tổ chức thư mục](#4-tổ-chức-thư-mục)
5. [Cơ sở dữ liệu](#5-cơ-sở-dữ-liệu)
6. [API Endpoints](#6-api-endpoints)
7. [Các luồng chức năng chính](#7-các-luồng-chức-năng-chính)
8. [Quy tắc cooldown — tránh lưu trùng](#8-quy-tắc-cooldown--tránh-lưu-trùng)
9. [Xác thực & Phân quyền](#9-xác-thực--phân-quyền)
10. [Mô hình AI](#10-mô-hình-ai)
11. [Tài khoản mặc định](#11-tài-khoản-mặc-định)

---

## 1. Tổng quan hệ thống

Dự án **3soc** là phần **Backend** (máy chủ) của hệ thống. Nó đảm nhận:

- Nhận video/ảnh từ phía người dùng (qua Frontend `admin-web` hoặc app mobile `3soc-app`)
- Chạy 3 mô hình AI (YOLO) để phát hiện vi phạm
- Lưu ảnh frame vi phạm vào ổ đĩa, metadata vào database MySQL
- Cung cấp API REST và SSE cho Frontend

```
Frontend (admin-web / 3soc-app)
        │
        │  HTTP / SSE
        ▼
Backend (3soc) ← FastAPI, port 8000
        │
        ├── MySQL Database (lưu user, video, violations)
        ├── Ổ đĩa /uploads/ (lưu file video, ảnh vi phạm .jpg)
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

---

## 3. Cách chạy dự án

### Bước 1: Tạo database MySQL

```sql
CREATE DATABASE detect_3soc CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### Bước 2: Cấu hình kết nối database

Tạo file `.env` ở thư mục gốc:

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
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Bước 5: Kiểm tra hoạt động

Mở trình duyệt: **http://localhost:8000/docs**

Nếu thấy giao diện Swagger UI → server đã chạy thành công ✅

> **Lưu ý:** Bảng trong MySQL được tạo **tự động** khi server khởi động lần đầu, không cần chạy script SQL thủ công.

---

## 4. Tổ chức thư mục

```
3soc/
│
├── app/                        ← Toàn bộ mã nguồn ứng dụng
│   ├── main.py                 ← Điểm khởi động: tạo app FastAPI, load model AI,
│   │                              đăng ký router, warm-up model
│   │
│   ├── config.py               ← Cấu hình đường dẫn (thư mục uploads)
│   │
│   ├── db/                     ← Tầng database
│   │   ├── db.py               ← Kết nối MySQL, tạo bảng tự động, seed user mặc định
│   │   └── models.py           ← Định nghĩa cấu trúc bảng (User, VideoFile, Violation)
│   │
│   ├── routers/                ← Xử lý các API endpoint
│   │   ├── users.py            ← Đăng ký, đăng nhập, quản lý user
│   │   └── files.py            ← Upload video/ảnh, detect, stream SSE, xoá
│   │
│   ├── schemas/                ← Định nghĩa kiểu dữ liệu vào/ra của API
│   │   ├── user.py             ← Schema cho user
│   │   ├── file.py             ← Schema cho file video
│   │   └── response.py         ← Schema dùng chung
│   │
│   └── utils/                  ← Các tiện ích dùng chung
│       ├── auth.py             ← Mã hoá mật khẩu, tạo/xác thực JWT token
│       └── tasks.py            ← Chạy mô hình AI trên frame/ảnh
│
├── models/                     ← File mô hình AI (*.pt) — KHÔNG commit lên Git
│
├── uploads/                    ← Thư mục lưu file người dùng upload (tạo tự động)
│   ├── {video_id}.mp4          ← Video đã upload
│   ├── temp/                   ← Ảnh tạm thời khi detect ảnh (xoá sau khi xong)
│   └── violations/             ← Ảnh frame vi phạm (*.jpg)
│       └── {video_id}/
│           └── ts_00001250.00_f42.jpg
│
├── requirements.txt
├── run.bat
└── .env
```

---

## 5. Cơ sở dữ liệu

Database: **MySQL**, tên: `detect_3soc`
ORM: **SQLAlchemy** — Python tự tạo bảng khi khởi động (`Base.metadata.create_all()`)

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
| `status` | VARCHAR(50) | Trạng thái: `uploaded` / `processing` / `completed` |
| `detection_id` | VARCHAR(64) | Liên kết đến thư mục lưu ảnh vi phạm |
| `created_at` | DATETIME | Thời gian upload |

---

### Bảng `violations` — Lưu từng frame vi phạm phát hiện được

Mỗi frame vi phạm được lưu thành **1 row** trong bảng này. Khi xoá video, toàn bộ violations liên quan tự động bị xoá theo (cascade).

| Cột | Kiểu dữ liệu | Mô tả |
|-----|-------------|-------|
| `id` | INT (PK) | ID tự tăng |
| `video_id` | VARCHAR(64) (FK → video_files.id) | Video chứa frame vi phạm này |
| `frame_number` | INT | Số thứ tự frame trong video |
| `timestamp` | FLOAT | Thời điểm frame trong video (milliseconds) |
| `image_path` | VARCHAR(500) | Đường dẫn web tới ảnh `.jpg` |
| `detections` | JSON | Danh sách vi phạm: `[{x, y, width, height, label, confidence}]` |
| `created_at` | DATETIME | Thời điểm lưu vào DB |

**Ví dụ một row trong `violations`:**
```json
{
  "id": 1,
  "video_id": "1234567890",
  "frame_number": 42,
  "timestamp": 1400.00,
  "image_path": "/uploads/violations/1234567890/ts_00001400.00_f42.jpg",
  "detections": [
    { "x": 100, "y": 200, "width": 80, "height": 60, "label": "co3soc",      "confidence": 0.9234 },
    { "x": 300, "y": 150, "width": 60, "height": 50, "label": "duongluoibo", "confidence": 0.8811 }
  ]
}
```

> **Một frame có thể chứa nhiều loại vi phạm** — tất cả được gom vào mảng `detections` của cùng 1 row.

---

### Sơ đồ quan hệ

```
users (1) ────────────── (N) video_files (1) ────────────── (N) violations
  id ◄──────────────────── user_id              id ◄──────────── video_id
                                                                  (cascade delete)
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
| DELETE | `/api/files/{id}` | Có | Xoá file video + ảnh vi phạm + rows violations |
| POST | `/api/files/detect-image` | Tuỳ chọn | Upload ảnh → detect ngay, trả kết quả (không lưu) |
| GET | `/api/files/{id}/detect-stream` | Không | **SSE** — stream kết quả detect video |

---

### Static Files

| Đường dẫn | Mô tả |
|-----------|-------|
| `/uploads/*` | Truy cập file video, ảnh vi phạm đã lưu trên disk |

---

## 7. Các luồng chức năng chính

### Luồng 1: Phát hiện video qua SSE

```
[Frontend] Chọn file video → upload lên server
    │  POST /api/files/upload  { file, video_id }
    │  Server lưu file vào uploads/, tạo record trong bảng video_files
    │
    ▼
[Frontend] Bấm "Bắt đầu phát hiện"
    │  GET /api/files/{id}/detect-stream
    │
    ▼
[Backend] Kiểm tra bảng violations: video này đã có kết quả chưa?
    │
    ├── ĐÃ CÓ (cache hit) ─────────────────────────────────────────────┐
    │   Query toàn bộ violations từ DB                                 │
    │   Stream ngay về Frontend, không chạy AI lại:                    │
    │   SSE: init → metadata → violation × N → complete               │
    │                                                                  ▼
    └── CHƯA CÓ → Bắt đầu detect:                            [Frontend] Hiển thị
                                                               danh sách vi phạm
         Thread 1 (reader): đọc video, lấy 1 frame mỗi DETECT_SAMPLE_MS
         Thread 2 (worker): chạy 3 model YOLO trên từng frame

         Mỗi frame:
           → Yield SSE "detection" (luôn luôn, kể cả frame trống):
             { type:"detection", data:{ timestamp, detections:[{x,y,w,h,label,conf}] } }

           → Nếu có vi phạm + đủ cooldown:
               - Lưu ảnh .jpg → uploads/violations/{id}/
               - INSERT row vào bảng violations
               - Yield SSE "violation":
                 { type:"violation", data:{ frame_number, timestamp, image_path, detections } }

         Kết thúc: cập nhật status="completed"
           → Yield SSE "complete": { type:"complete", total_violations: N }
```

**Cấu trúc SSE events:**
```
data: {"type": "init",      "detection_id": "1234567890"}
data: {"type": "metadata",  "total_frames": 1800, "fps": 30}
data: {"type": "detection", "data": {"timestamp": 1400, "detections": [{...}]}}
data: {"type": "violation", "data": {"frame_number": 42, "timestamp": 1400.0,
                                      "image_path": "/uploads/violations/.../ts_...jpg",
                                      "detections": [{...}]}}
data: {"type": "complete",  "total_violations": 5}
```

---

### Luồng 2: Detect ảnh tĩnh

```
[Frontend] Chọn file ảnh → POST /api/files/detect-image
    │
    ▼
[Backend] Lưu ảnh tạm vào uploads/temp/
          → Chạy 3 model YOLO trên ảnh
          → Xoá file tạm ngay sau khi xong
          → Trả về kết quả:
          {
            "filename": "anh.jpg",
            "detections": [ { "x":100, "y":200, "width":80, "height":60,
                               "label": "co3soc", "confidence": 0.92 } ],
            "timestamp": "2026-03-16T10:00:00Z"
          }
    │
    ▼
[Frontend] Vẽ bounding box lên ảnh

※ Ảnh detect đơn lẻ KHÔNG lưu vào DB, KHÔNG lưu disk — chỉ trả kết quả tức thì.
```

---

### Luồng 3: Đăng nhập

```
[Frontend] Nhập username + password → POST /api/users/login
    │
    ▼
[Backend] Tìm user trong DB → kiểm tra mật khẩu (Argon2)
          → Tạo JWT token (hết hạn sau 7 ngày)
          → Trả về:
          {
            "access_token": "eyJ...",
            "token_type": "bearer",
            "user": { "id": 1, "username": "admin", "role": "admin" }
          }
    │
    ▼
[Frontend] Lưu token vào localStorage
           Tất cả request sau gửi kèm header: Authorization: Bearer <token>
```

---

### Luồng 4: Xoá video

```
[Frontend] Bấm xoá → DELETE /api/files/{id}
    │
    ▼
[Backend] Xoá file video vật lý trên disk (uploads/{id}.mp4)
          → Xoá record trong bảng video_files
          → Bảng violations tự xoá toàn bộ rows liên quan (CASCADE)
          ※ Ảnh .jpg trong uploads/violations/{id}/ KHÔNG tự xoá —
            cần dọn thủ công hoặc thêm logic sau.
```

---

### Tóm tắt: Ai ghi DB, ai đọc DB

| Luồng | Ghi DB | Đọc DB |
|-------|--------|--------|
| SSE detect-stream (lần đầu) | ✅ INSERT violations | ❌ không |
| SSE detect-stream (cache hit) | ❌ không | ✅ SELECT violations |
| Detect ảnh tĩnh | ❌ không | ❌ không |

---

## 8. Quy tắc cooldown — tránh lưu trùng

**Vấn đề:** Nếu video có vi phạm liên tục trong 30 giây, hệ thống sẽ lưu hàng trăm ảnh giống nhau → tốn disk và DB.

**Giải pháp:** 2 lớp cooldown độc lập:

| Cooldown | Tham số | Mô tả |
|----------|---------|-------|
| Theo label | `cooldown_ms` (mặc định 200ms) | Mỗi label (co3soc, duongluoibo, vnmap) có cooldown riêng |
| Toàn cục | `save_image_ms` (mặc định 2000ms) | Dù bao nhiêu detection, chỉ lưu 1 ảnh mỗi 2 giây |

**Ví dụ minh hoạ:**

```
t = 1000ms  →  phát hiện: [co3soc, duongluoibo]
               → Lưu cả 2 ✅  (lần đầu)

t = 1100ms  →  phát hiện: [co3soc]
               → Bỏ qua ❌  (cooldown label chưa đủ, và cooldown ảnh toàn cục chưa đủ 2s)

t = 3100ms  →  phát hiện: [co3soc, vnmap]
               → co3soc: cooldown đủ (3100-1000=2100ms > 2000ms) ✅
               → vnmap:  lần đầu ✅
               → Lưu ảnh ✅  (cooldown toàn cục đủ)
```

---

## 9. Xác thực & Phân quyền

**Thuật toán:** JWT (JSON Web Token) — HS256
**Mã hoá mật khẩu:** Argon2
**Thời hạn token:** 7 ngày

**JWT token chứa:**
```json
{ "sub": "admin", "user_id": 1, "role": "admin", "exp": 1234567890 }
```

| Dependency | Tác dụng |
|-----------|---------|
| `get_current_user_from_token` | Đọc header `Authorization: Bearer ...`, giải mã JWT, trả về thông tin user |
| `require_admin` | Gọi hàm trên + kiểm tra thêm `role == "admin"`, nếu không → HTTP 403 |

---

## 10. Mô hình AI

Ba mô hình **YOLOv8/v11** được load khi server khởi động và warm-up sẵn để giảm latency lần detect đầu tiên:

| Tên model | File | Phát hiện |
|-----------|------|----------|
| `co3soc` | `models/3soc.pt` | Cờ 3 sọc (cờ Việt Nam Cộng Hoà) |
| `duongluoibo` | `models/duongluoibo.pt` | Đường lưỡi bò (bản đồ 9 đoạn của Trung Quốc) |
| `vnmap` | `models/vnmap.pt` | Bản đồ Việt Nam sai lệch |

**Kết quả bounding box trả về Frontend:**
```json
{ "x": 100, "y": 200, "width": 80, "height": 60,
  "label": "co3soc", "confidence": 0.9234 }
```

**Màu hiển thị:**
- `co3soc` → 🔴 Đỏ
- `duongluoibo` → 🟢 Xanh lá
- `vnmap` → 🔵 Xanh dương

**GPU/CPU:** Tự động dùng CUDA nếu có, fallback sang CPU nếu không.

---

## 11. Tài khoản mặc định

Khi server khởi động lần đầu, hệ thống tự tạo 2 tài khoản:

| Username | Mật khẩu | Vai trò |
|----------|----------|---------|
| `admin` | `admin123` | Admin (toàn quyền) |
| `user` | `user123` | User thường |

> ⚠️ **Hãy đổi mật khẩu ngay sau khi deploy lên production!**

---

## Checklist kiểm tra sau khi deploy

- [ ] `GET http://localhost:8000/docs` → Swagger UI hiện lên
- [ ] `POST /api/users/login` với `admin / admin123` → nhận được `access_token`
- [ ] `POST /api/files/upload` → upload video thành công, DB có row trong `video_files`
- [ ] `GET /api/files/{id}/detect-stream` → SSE stream chạy, nhận được events `detection` và `violation`
- [ ] Sau khi scan xong: DB có rows trong `violations`, ảnh `.jpg` xuất hiện trong `uploads/violations/{id}/`
- [ ] Scan lại video đã scan → nhận ngay kết quả cache (không chạy AI lại)
- [ ] Xoá video → rows trong `violations` tự biến mất (cascade)
- [ ] `POST /api/files/detect-image` với file ảnh → nhận kết quả detect, không có gì lưu vào DB
