# 3SOC — Hệ thống Phát hiện Vi phạm Giao thông bằng YOLO

> **Dành cho người mới nhận dự án** — Tài liệu này giải thích toàn bộ hệ thống từ A đến Z: kiến trúc, cơ sở dữ liệu, từng API, luồng xử lý, cách cài đặt và chạy.

---

## Mục lục

1. [Tổng quan dự án](#1-tổng-quan-dự-án)
2. [Công nghệ sử dụng](#2-công-nghệ-sử-dụng)
3. [Cấu trúc thư mục](#3-cấu-trúc-thư-mục)
4. [Cài đặt và chạy project](#4-cài-đặt-và-chạy-project)
5. [Cấu hình môi trường (.env)](#5-cấu-hình-môi-trường-env)
6. [Cơ sở dữ liệu](#6-cơ-sở-dữ-liệu)
7. [Xác thực và phân quyền](#7-xác-thực-và-phân-quyền)
8. [Các model YOLO](#8-các-model-yolo)
9. [Luồng xử lý nghiệp vụ](#9-luồng-xử-lý-nghiệp-vụ)
10. [API chi tiết](#10-api-chi-tiết)
11. [WebSocket Realtime](#11-websocket-realtime)
12. [Lưu trữ file](#12-lưu-trữ-file)
13. [Giải thích từng file code](#13-giải-thích-từng-file-code)
14. [Tài khoản mặc định](#14-tài-khoản-mặc-định)
15. [Ghi chú kỹ thuật quan trọng](#15-ghi-chú-kỹ-thuật-quan-trọng)
16. [Hướng mở rộng đề xuất](#16-hướng-mở-rộng-đề-xuất)

---

## 1. Tổng quan dự án

**3SOC** là một **backend API** phát hiện vi phạm giao thông tự động từ video hoặc luồng camera thời gian thực. Hệ thống sử dụng **3 model AI (YOLO)** chạy song song để phát hiện các vi phạm:

| Model | File | Vi phạm phát hiện |
|---|---|---|
| **3SOC** | `models/3soc.pt` | Xe cộ gắn biểu tượng "cờ 3 sọc" |
| **Đường lưới bò** | `models/duongluoibo.pt` | Xe dừng/đỗ sai trên vạch kẻ đường |
| **Bản đồ VN** | `models/vnmap.pt` | Vi phạm liên quan ký hiệu bản đồ Việt Nam |

### Hệ thống hỗ trợ 3 chế độ phát hiện:

```
┌─────────────────────────────────────────────┐
│           3 Chế độ phát hiện                │
├─────────────────┬───────────────┬────────────┤
│  Upload Video   │  Ảnh đơn      │  Realtime  │
│  → Detect SSE  │  → Detect     │  WebSocket │
│  (stream kết   │  ngay tức thì │  Camera    │
│   quả realtime)│               │  livestream│
└─────────────────┴───────────────┴────────────┘
```

---

## 2. Công nghệ sử dụng

| Thư viện | Phiên bản | Vai trò |
|---|---|---|
| **FastAPI** | 0.128.0 | Framework web API chính, tự động tạo docs |
| **Uvicorn** | 0.40.0 | ASGI server thực thi FastAPI |
| **Ultralytics (YOLO)** | 8.3.251 | Load model `.pt` và chạy object detection |
| **PyTorch** | 2.9.1 | Deep learning backend, hỗ trợ GPU/CUDA |
| **OpenCV** | 4.12.0 | Đọc video, cắt frame, xử lý ảnh |
| **NumPy** | 2.2.6 | Thao tác mảng số (pixel, tensor) |
| **Pillow** | 12.1.0 | Đọc/ghi ảnh (YOLO render bounding box) |
| **SQLAlchemy** | 2.0.45 | ORM - ánh xạ class Python ↔ bảng MySQL |
| **PyMySQL** | 1.1.2 | Driver kết nối MySQL thuần Python |
| **Pydantic** | 2.12.5 | Validate dữ liệu request/response tự động |
| **python-jose** | 3.5.0 | Tạo và xác thực JWT token |
| **passlib + argon2-cffi** | 1.7.4 / 25.1.0 | Hash mật khẩu an toàn (Argon2) |
| **python-multipart** | 0.0.21 | Parse multipart form (upload file) |
| **websockets** | 16.0 | Giao tiếp WebSocket 2 chiều |
| **psutil** | 7.2.1 | Đọc thông số CPU%, RAM% hệ thống |
| **python-dotenv** | 1.2.1 | Đọc biến môi trường từ file `.env` |

---

## 3. Cấu trúc thư mục

```
3soc/
│
├── 📄 app/                        ← Toàn bộ source code chính
│   ├── main.py                    ← Điểm khởi động ứng dụng
│   ├── config.py                  ← Cấu hình đường dẫn thư mục
│   │
│   ├── db/                        ← Tầng database
│   │   ├── db.py                  ← Kết nối DB, tạo bảng, session
│   │   └── models.py              ← Định nghĩa bảng (ORM models)
│   │
│   ├── routers/                   ← Các nhóm API endpoint
│   │   ├── users.py               ← API quản lý người dùng + đăng nhập
│   │   └── files.py               ← API upload video, detect, stream
│   │
│   ├── schemas/                   ← Cấu trúc dữ liệu request/response
│   │   ├── user.py                ← Schema cho user
│   │   ├── file.py                ← Schema cho video file
│   │   └── response.py            ← Schema dùng chung (pagination, detection)
│   │
│   └── utils/                     ← Các tiện ích hỗ trợ
│       ├── auth.py                ← JWT + hash mật khẩu
│       ├── tasks.py               ← Logic chạy YOLO trên frame/ảnh
│       └── websocket_handler.py   ← Quản lý WebSocket realtime
│
├── 📄 models/                     ← Thư mục chứa file model YOLO (.pt)
│   ├── 3soc.pt
│   ├── duongluoibo.pt
│   └── vnmap.pt
│
├── 📄 uploads/                    ← Thư mục lưu file upload (tạo tự động)
│   ├── <video>.mp4                ← Video đã upload
│   ├── temp/                      ← Ảnh tạm (detect-image)
│   └── violations/
│       └── <detection_id>/        ← Ảnh frame vi phạm + metadata JSON
│
├── 📄 infer_yolo.py               ← Script test YOLO độc lập (không cần API)
├── 📄 requirements.txt            ← Danh sách thư viện cần cài
├── 📄 run.bat                     ← Lệnh chạy server (Windows)
├── 📄 run.sh                      ← Lệnh chạy server (Linux/Mac)
├── 📄 .env                        ← Biến môi trường (DB, secret key)
└── 📄 README.md                   ← Tài liệu này
```

---

## 4. Cài đặt và chạy project

### Yêu cầu hệ thống

- **Python 3.10+** (khuyến nghị 3.12)
- **MySQL 8.0+** (đã cài và đang chạy)
- **GPU NVIDIA + CUDA 12.6** *(tùy chọn — có GPU thì detect nhanh hơn ~10-20 lần)*

---

### Bước 1 — Cài Python

Tải Python tại: https://python.org/downloads

> Khi cài trên Windows, nhớ tick **"Add Python to PATH"**

---

### Bước 2 — Cài MySQL và tạo database

```sql
-- Đăng nhập MySQL
mysql -u root -p

-- Tạo database
CREATE DATABASE detect_3soc CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Thoát
EXIT;
```

---

### Bước 3 — Clone / tải source code

```bash
# Nếu dùng git
git clone <repo-url>
cd 3soc

# Hoặc giải nén file zip vào thư mục 3soc/
```

---

### Bước 4 — Cấu hình file .env

Tạo file `.env` ở thư mục gốc (hoặc sửa file đã có):

```env
DATABASE_URL=mysql+pymysql://root:YOUR_MYSQL_PASSWORD@localhost/detect_3soc
SECRET_KEY=thay-bang-chuoi-bi-mat-rat-dai-va-ngau-nhien
```

> **Giải thích:**
> - `DATABASE_URL`: Chuỗi kết nối MySQL. Thay `YOUR_MYSQL_PASSWORD` bằng mật khẩu MySQL của bạn.
> - `SECRET_KEY`: Khóa bí mật dùng để ký JWT. **Phải thay** ở môi trường production.

---

### Bước 5 — Đặt model YOLO

Copy các file model vào thư mục `models/`:

```
models/
├── 3soc.pt
├── duongluoibo.pt
└── vnmap.pt
```

> Nếu chưa có file `.pt`, liên hệ người phụ trách ML để lấy.

---

### Bước 6 — Cài thư viện và chạy

**Cách 1: Chạy tự động (khuyến nghị cho người mới)**

```bash
# Windows — Double-click hoặc chạy trong terminal:
run.bat

# Linux / Mac:
chmod +x run.sh
./run.sh
```

Script sẽ tự động:
1. Tạo virtual environment (`venv/`)
2. Cài tất cả thư viện từ `requirements.txt`
3. Tạo thư mục `uploads/` cần thiết
4. Khởi động server

---

**Cách 2: Chạy thủ công từng bước**

```bash
# Tạo môi trường ảo
python -m venv venv

# Kích hoạt (Windows)
venv\Scripts\activate

# Kích hoạt (Linux/Mac)
source venv/bin/activate

# Cài thư viện
pip install -r requirements.txt

# Chạy server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

### Kết quả khi chạy thành công

```
INFO:     Started server process [XXXX]
INFO:     Waiting for application startup.
INFO:     [DB] Tables created successfully
INFO:     [DB] Default users seeded
INFO:     [YOLO] Loading models...
INFO:     [YOLO] Loaded: 3soc
INFO:     [YOLO] Loaded: duongluoibo
INFO:     [YOLO] Loaded: vnmap
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

Truy cập:
- **API Docs (Swagger UI):** http://localhost:8000/docs
- **API Docs (ReDoc):** http://localhost:8000/redoc
- **Base API:** http://localhost:8000

---

## 5. Cấu hình môi trường (.env)

| Biến | Mô tả | Ví dụ |
|---|---|---|
| `DATABASE_URL` | Chuỗi kết nối MySQL đầy đủ | `mysql+pymysql://root:1234@localhost/detect_3soc` |
| `SECRET_KEY` | Khóa ký JWT (càng dài càng tốt) | `abc123xyz...` (ít nhất 32 ký tự) |

> **Lưu ý:** Nếu không tạo file `.env`, hệ thống dùng giá trị mặc định trong code:
> - DB: `mysql+pymysql://root:1234567890@localhost/detect_3soc`
> - SECRET_KEY: giá trị mặc định không an toàn

---

## 6. Cơ sở dữ liệu

Hệ thống dùng **MySQL** với **SQLAlchemy ORM**. Các bảng được tạo tự động khi khởi động ứng dụng lần đầu (`init_db()` gọi `Base.metadata.create_all()`).

### Sơ đồ quan hệ

```
users (1) ──────────── (nhiều) video_files
                                    │
                         detection_id (string)
                                    │
                                    ▼
                              detections
```

---

### Bảng `users` — Tài khoản hệ thống

| Cột | Kiểu dữ liệu | Bắt buộc | Mô tả |
|---|---|---|---|
| `id` | Integer (PK, auto) | ✅ | ID tự tăng |
| `username` | String(100), unique | ✅ | Tên đăng nhập, không trùng |
| `email` | String(255), unique | ✅ | Email, không trùng |
| `password_hash` | String(255) | ✅ | Mật khẩu đã hash bằng Argon2 |
| `role` | String(50) | ✅ | `"user"` hoặc `"admin"` |
| `is_active` | Boolean | ✅ | `true` = tài khoản hoạt động |
| `created_at` | DateTime | ✅ | Thời điểm tạo (tự động) |
| `updated_at` | DateTime | ❌ | Thời điểm cập nhật cuối |

---

### Bảng `video_files` — Thông tin video đã upload

| Cột | Kiểu dữ liệu | Bắt buộc | Mô tả |
|---|---|---|---|
| `id` | String (PK, UUID) | ✅ | ID do client gửi lên |
| `filename` | String(255) | ✅ | Tên file gốc |
| `filepath` | String(500) | ✅ | Đường dẫn web (ví dụ: `/uploads/abc.mp4`) |
| `user_id` | Integer (FK → users.id) | ✅ | Người upload |
| `file_size` | Integer | ❌ | Kích thước file (bytes) |
| `duration` | Float | ❌ | Thời lượng video (giây) |
| `status` | String(50) | ✅ | `uploaded` / `processing` / `completed` / `error` |
| `detection_id` | String(64), index | ❌ | Mã liên kết với kết quả detect |
| `created_at` | DateTime | ✅ | Thời điểm upload |

---

### Bảng `detections` — Kết quả phát hiện vi phạm

| Cột | Kiểu dữ liệu | Bắt buộc | Mô tả |
|---|---|---|---|
| `id` | Integer (PK, auto) | ✅ | ID tự tăng |
| `detection_id` | String(64), unique | ✅ | Mã detect duy nhất |
| `source` | String(255) | ❌ | Nguồn (tên file, camera ID...) |
| `created_at` | DateTime | ✅ | Thời điểm tạo |
| `results` | JSON | ❌ | Danh sách bounding box phát hiện được |
| `summary` | JSON | ❌ | Thống kê tổng hợp (tổng frame, vi phạm...) |

---

## 7. Xác thực và phân quyền

Hệ thống dùng **JWT (JSON Web Token)** để xác thực người dùng.

### Luồng đăng nhập

```
Client                          Server
  │                               │
  │── POST /api/users/login ──────►│
  │   { username, password }      │  1. Tìm user trong DB
  │                               │  2. Kiểm tra password bằng Argon2
  │                               │  3. Tạo JWT token (hết hạn sau 7 ngày)
  │◄── { access_token, user } ───│
  │                               │
  │── GET /api/users/me ──────────►│
  │   Authorization: Bearer <JWT> │  4. Giải mã JWT
  │                               │  5. Tìm user trong DB
  │◄── { user info } ────────────│
```

### Phân quyền

| Role | Quyền |
|---|---|
| **admin** | Xem/sửa/xóa tất cả user và video file |
| **user** | Chỉ xem video file của chính mình |

### Cách dùng token

Sau khi đăng nhập, thêm header vào mọi request cần xác thực:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Bảo mật mật khẩu

Mật khẩu được hash bằng **Argon2** (thuật toán hash hiện đại nhất, an toàn hơn bcrypt). Mật khẩu gốc **không bao giờ** được lưu vào database.

---

## 8. Các model YOLO

Hệ thống load **3 model YOLO** khi khởi động. Mỗi model được train để phát hiện một loại vi phạm khác nhau.

```python
# Trong app/main.py — load khi startup
_LOADED_MODELS = {
    "3soc":        YOLO("models/3soc.pt"),
    "duongluoibo": YOLO("models/duongluoibo.pt"),
    "vnmap":       YOLO("models/vnmap.pt"),
}
```

### Cách detect hoạt động

Với mỗi frame ảnh:
1. Frame được gửi qua **cả 3 model** song song
2. Kết quả bounding box từ 3 model được **gộp lại**
3. Mỗi box có thông tin: `label`, `confidence`, `x`, `y`, `width`, `height`, `model_name`
4. Các frame trùng lặp bị lọc bằng **perceptual hash** (so sánh nội dung ảnh)

### Hỗ trợ GPU

Nếu máy có GPU NVIDIA:
```python
# PyTorch tự phát hiện CUDA
device = "cuda" if torch.cuda.is_available() else "cpu"
```

Với CUDA 12.6, inference nhanh hơn ~10-20 lần so với CPU.

---

## 9. Luồng xử lý nghiệp vụ

### 9.1 Upload + Detect Video (SSE Stream)

Đây là luồng chính, phổ biến nhất:

```
┌──────────────────────────────────────────────────────────────┐
│                    LUỒNG DETECT VIDEO                         │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  1. Client upload video                                       │
│     POST /api/files/upload                                    │
│     → Video lưu vào uploads/<video_id>.mp4                   │
│     → Ghi metadata vào DB (bảng video_files)                 │
│                                                               │
│  2. Client yêu cầu detect                                     │
│     GET /api/files/{file_id}/detect-stream                    │
│                                                               │
│  3. Server kiểm tra cache                                     │
│     ┌─ Đã detect trước? ──► Stream kết quả từ cache          │
│     └─ Chưa detect       ──► Bắt đầu xử lý mới              │
│                                                               │
│  4. Xử lý video (nếu chưa cache)                             │
│     Thread A: cv2.VideoCapture đọc frame mỗi 0.25 giây      │
│               → đưa vào frame_queue                          │
│     Thread B: lấy frame từ queue                             │
│               → chạy qua 3 model YOLO                        │
│               → nếu có vi phạm: lưu ảnh .jpg + metadata.json │
│               → gửi SSE event "violation" về client          │
│                                                               │
│  5. Kết thúc                                                  │
│     → Gửi SSE event "complete" với tổng số vi phạm          │
│     → Cập nhật status DB: "completed"                        │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

**SSE Events (Server-Sent Events) trả về:**

```json
// Bắt đầu
{ "type": "init", "detection_id": "abc123" }

// Thông tin video
{ "type": "metadata", "total_frames": 3600, "fps": 30 }

// Mỗi frame vi phạm
{
  "type": "violation",
  "data": {
    "frame_number": 450,
    "timestamp": 15.0,
    "image_path": "/uploads/violations/abc123/frame_00450_ts15.00.jpg",
    "detections": [
      { "label": "co3soc", "confidence": 0.94, "x": 120, "y": 80, "width": 60, "height": 90, "model": "3soc" }
    ]
  }
}

// Hoàn thành
{ "type": "complete", "total_violations": 12 }
```

---

### 9.2 Detect Ảnh Đơn

```
Client POST /api/files/detect-image (multipart ảnh)
    │
    ▼
Lưu tạm vào uploads/temp/<uuid>_<tên_file>
    │
    ▼
Chạy 3 model YOLO trên ảnh
    │
    ▼
Trả kết quả JSON ngay lập tức
    │
    ▼
Xóa file tạm (trong finally block)
```

---

### 9.3 Detect Realtime qua WebSocket

```
                  WebSocket ws://localhost:8000/realtime
Client ◄────────────────────────────────────────────► Server
  │                                                     │
  │── { type: "frame", frameData: "base64..." } ───────►│
  │                                                     │  1. Decode base64 → numpy array
  │                                                     │  2. Chạy 3 model YOLO song song
  │                                                     │  3. Gộp kết quả boxes
  │◄── { type: "detection", boxes: [...] } ────────────│
  │                                                     │
  │◄── { type: "stats", fps: 15, cpu: 45, ram: 60 } ──│  (broadcast mỗi 1 giây)
```

**Dùng cho:** Camera livestream, gửi frame liên tục và nhận phản hồi detection ngay lập tức.

---

## 10. API chi tiết

Base URL: `http://localhost:8000`
API Prefix: `/api`
Swagger Docs: http://localhost:8000/docs

---

### 10.1 Users API (`/api/users`)

#### `POST /api/users/register` — Đăng ký tài khoản

```json
// Request body
{
  "username": "nguyen_van_a",
  "email": "a@example.com",
  "password": "matkhau123",
  "role": "user"
}

// Response 200
{
  "id": 3,
  "username": "nguyen_van_a",
  "email": "a@example.com",
  "role": "user",
  "is_active": true,
  "created_at": "2024-01-15T09:30:00"
}
```

---

#### `POST /api/users/login` — Đăng nhập

```json
// Request body
{
  "username": "admin",
  "password": "admin123"
}

// Response 200
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "admin",
    "email": "admin@example.com",
    "role": "admin",
    "is_active": true,
    "created_at": "2024-01-01T00:00:00"
  }
}
```

---

#### `GET /api/users/me` — Thông tin user hiện tại

```
Header: Authorization: Bearer <token>
```

```json
// Response 200
{
  "id": 1,
  "username": "admin",
  "email": "admin@example.com",
  "role": "admin",
  "is_active": true
}
```

---

#### `GET /api/users` — Danh sách user *(Admin only)*

```
Header: Authorization: Bearer <admin_token>
Query:  ?skip=0&limit=100
```

---

#### `GET /api/users/{user_id}` — Chi tiết user *(Admin only)*

---

#### `PUT /api/users/{user_id}` — Cập nhật user *(Admin only)*

```json
// Request body (tất cả trường đều optional)
{
  "username": "ten_moi",
  "email": "email_moi@example.com",
  "password": "matkhau_moi",
  "role": "admin",
  "is_active": true
}
```

---

#### `DELETE /api/users/{user_id}` — Xóa user *(Admin only)*

---

#### `POST /api/users/change-password` — Đổi mật khẩu

```json
// Request body
{
  "old_password": "matkhau_cu",
  "new_password": "matkhau_moi"
}
```

---

#### `POST /api/users/logout` — Đăng xuất

> **Lưu ý:** Server không có token blacklist. Logout chỉ là thông báo phía server; client cần tự xóa token.

---

### 10.2 Files API (`/api/files`)

#### `POST /api/files/upload` — Upload video

```
Header:       Authorization: Bearer <token>
Content-Type: multipart/form-data
Field:        file (video file, content-type phải là video/*)
```

```json
// Response 200
{
  "id": "uuid-abc-123",
  "filename": "camera_01.mp4",
  "filepath": "/uploads/camera_01.mp4",
  "file_size": 52428800,
  "duration": 120.5,
  "status": "uploaded",
  "created_at": "2024-01-15T10:00:00"
}
```

---

#### `GET /api/files` — Danh sách video

```
Header: Authorization: Bearer <token>
Query:  ?skip=0&limit=100
```

> - **admin**: thấy tất cả video
> - **user**: chỉ thấy video của mình

---

#### `DELETE /api/files/{file_id}` — Xóa video

Xóa bản ghi DB + file vật lý trong `uploads/`.

---

#### `POST /api/files/{file_id}/detect` — Detect video (batch, không stream)

Chạy detect và **đợi đến khi xong** mới trả kết quả. Có cache — nếu đã detect rồi thì trả ngay từ cache.

```json
// Response 200
{
  "detection_id": "abc123",
  "total_frames": 3600,
  "processed_frames": 480,
  "violation_count": 12,
  "cached": false,
  "violations": [
    {
      "frame_number": 450,
      "timestamp": 15.0,
      "image_path": "/uploads/violations/abc123/frame_00450_ts15.00.jpg",
      "detections": [
        {
          "label": "co3soc",
          "confidence": 0.94,
          "x": 120, "y": 80,
          "width": 60, "height": 90,
          "model": "3soc"
        }
      ]
    }
  ]
}
```

---

#### `GET /api/files/{file_id}/detect-stream` — Detect video (SSE stream)

Trả kết quả **realtime** trong khi đang xử lý. Kết nối dạng `text/event-stream`.

> **Khuyến nghị dùng endpoint này** thay vì `/detect` vì frontend có thể hiển thị tiến trình ngay lập tức.

---

#### `POST /api/files/detect-image` — Detect ảnh đơn

```
Header:       Authorization: Bearer <token> (optional)
Content-Type: multipart/form-data
Field:        file (image file, content-type phải là image/*)
```

```json
// Response 200
{
  "filename": "screenshot.jpg",
  "detections": [
    { "label": "duongluoibo", "confidence": 0.87, "x": 200, "y": 150, "width": 80, "height": 60, "model": "duongluoibo" }
  ],
  "timestamp": "2024-01-15T10:05:00",
  "user_id": 1
}
```

---

## 11. WebSocket Realtime

Kết nối: `ws://localhost:8000/realtime`

### Client gửi frame

```json
{
  "type": "frame",
  "frameData": "data:image/jpeg;base64,/9j/4AAQSkZJRgAB...",
  "timestamp": 1705312800000,
  "videoId": "camera-01"
}
```

### Server trả detection

```json
{
  "type": "detection",
  "timestamp": 1705312800000,
  "boxes": [
    {
      "x": 100, "y": 120,
      "width": 60, "height": 80,
      "label": "co3soc",
      "confidence": 0.91,
      "model": "3soc"
    }
  ],
  "frameSize": { "width": 1280, "height": 720 },
  "frameCount": 47
}
```

### Server broadcast stats (mỗi 1 giây)

```json
{
  "type": "stats",
  "fps": 15.3,
  "cpu_percent": 45.2,
  "memory_percent": 62.1,
  "connected_clients": 2
}
```

---

## 12. Lưu trữ file

### Cấu trúc thư mục `uploads/`

```
uploads/
├── camera_recording.mp4          ← Video upload trực tiếp
├── another_video.avi
│
├── temp/                          ← Ảnh tạm (tự xóa sau khi detect)
│   └── uuid1234_screenshot.jpg
│
└── violations/
    └── abc123def456/              ← Một lần detect = một thư mục
        ├── frame_00450_ts15.00.jpg       ← Ảnh frame vi phạm
        ├── frame_00450_metadata.json     ← Metadata frame đó
        ├── frame_00720_ts24.00.jpg
        ├── frame_00720_metadata.json
        └── ...
```

### Nội dung metadata JSON

```json
{
  "frame_number": 450,
  "timestamp": 15.0,
  "detections": [
    {
      "label": "co3soc",
      "confidence": 0.94,
      "bbox": [120, 80, 180, 170],
      "model": "3soc"
    }
  ]
}
```

### Truy cập ảnh qua URL

Thư mục `uploads/` được mount dưới path `/uploads`, vì vậy frontend có thể truy cập ảnh trực tiếp:

```
http://localhost:8000/uploads/violations/abc123/frame_00450_ts15.00.jpg
```

---

## 13. Giải thích từng file code

### `app/main.py` — Điểm khởi động

- Tạo FastAPI app, cấu hình CORS (cho phép frontend truy cập từ domain khác)
- Mount thư mục `uploads/` dưới URL `/uploads`
- **Startup hook:** Load 3 model YOLO vào RAM, khởi tạo DB, tạo user mặc định
- **Shutdown hook:** Giải phóng WebSocket manager
- Đăng ký 2 router: `users_router` và `files_router`
- Xử lý WebSocket endpoint `/realtime`

---

### `app/config.py` — Cấu hình đường dẫn

```python
UPLOAD_DIR = Path("uploads")  # Thư mục lưu file upload
```

Đơn giản chỉ định nghĩa đường dẫn thư mục upload để dùng chung toàn app.

---

### `app/db/db.py` — Kết nối database

- Đọc `DATABASE_URL` từ biến môi trường
- Tạo SQLAlchemy engine (connection pool tới MySQL)
- Tạo `SessionLocal` factory — mỗi request HTTP nhận 1 session riêng
- `init_db()`: tạo tất cả bảng nếu chưa có
- `seed_default_users()`: tạo tài khoản admin/user mặc định

---

### `app/db/models.py` — Định nghĩa bảng (ORM)

Định nghĩa 3 class Python tương ứng 3 bảng MySQL:
- `User` → bảng `users`
- `VideoFile` → bảng `video_files`
- `Detection` → bảng `detections`

SQLAlchemy tự động tạo câu SQL từ các class này.

---

### `app/utils/auth.py` — Xác thực

- **Hash password:** Dùng `passlib` với backend `argon2` — an toàn hơn bcrypt
- **Verify password:** So khớp password gốc với hash trong DB
- **Create JWT:** Tạo token với `python-jose`, hết hạn sau 7 ngày
- **get_current_user_from_token:** Dependency FastAPI, decode JWT và trả User object
- **require_admin:** Dependency kiểm tra role, trả 403 nếu không phải admin

---

### `app/utils/tasks.py` — Logic YOLO inference

Đây là file quan trọng nhất về mặt xử lý AI:

- **`run_detection_on_frame(frame)`:** Nhận numpy array (1 frame ảnh), chạy qua cả 3 model, gộp kết quả
- **`run_detection_on_image_temp(path)`:** Đọc file ảnh từ disk, chạy detect, trả boxes
- **`_compute_image_hash(img)`:** Tính perceptual hash của ảnh để phát hiện frame trùng
- **`_is_duplicate_frame(hash, seen_hashes)`:** Kiểm tra frame có trùng với frame đã lưu không

---

### `app/utils/websocket_handler.py` — WebSocket Manager

- Quản lý danh sách client đang kết nối WebSocket
- Nhận frame từ client, decode base64, chạy YOLO
- Broadcast stats (CPU, RAM, FPS) cho tất cả client mỗi giây
- Queue lưu ảnh vi phạm xuống disk không block luồng inference

---

### `app/routers/users.py` — API User

Xử lý tất cả endpoint liên quan user: đăng ký, đăng nhập, CRUD user (admin).

---

### `app/routers/files.py` — API Files

Xử lý upload video, detect video (batch + SSE stream), detect ảnh đơn.

**Điểm quan trọng:** SSE stream dùng Python generator + `StreamingResponse` của FastAPI để gửi data từng phần thay vì đợi xong mới gửi.

---

### `app/schemas/` — Schema dữ liệu

Dùng Pydantic để:
- Validate dữ liệu đầu vào (request body)
- Serialize dữ liệu đầu ra (response)
- Tự động tạo docs cho Swagger UI

---

### `infer_yolo.py` — Script test độc lập

Script chạy YOLO trên 1 ảnh/video mà **không cần khởi động server**. Dùng để test model có hoạt động không.

```bash
python infer_yolo.py
```

---

## 14. Tài khoản mặc định

Khi khởi động lần đầu, hệ thống tự tạo 2 tài khoản:

| Username | Password | Role |
|---|---|---|
| `admin` | `admin123` | admin |
| `user` | `user123` | user |

> ⚠️ **Bắt buộc phải đổi mật khẩu** trước khi deploy lên server thật!

---

## 15. Ghi chú kỹ thuật quan trọng

### Cache kết quả detect

Khi một video đã được detect, kết quả được lưu vào:
- Thư mục `uploads/violations/<detection_id>/` (ảnh + JSON)
- Trường `detection_id` trong bảng `video_files`

Lần sau gọi detect lại cùng video → hệ thống đọc từ cache, không chạy YOLO lại → nhanh hơn nhiều.

### Sampling rate

Hệ thống không xử lý từng frame (quá chậm), mà lấy mẫu **1 frame mỗi 0.25 giây** (~4 frames/giây). Điều này giảm tải tính toán trong khi vẫn đủ để phát hiện vi phạm.

### Loại bỏ frame trùng lặp

Perceptual hash so sánh nội dung ảnh (không phải byte-by-byte). Nếu 2 frame quá giống nhau (camera tĩnh, không có thay đổi), frame thứ 2 bị bỏ qua để tránh lưu nhiều ảnh giống nhau.

### GPU vs CPU

- Với GPU: ~50-100 frames/giây
- Với CPU: ~3-10 frames/giây

### Phụ thuộc thư viện

Một số thư viện như `scipy`, `matplotlib`, `pillow` được cài vì **ultralytics yêu cầu** — không cần dùng trực tiếp trong code.

---

## 16. Hướng mở rộng đề xuất

| Tính năng | Công nghệ gợi ý | Lý do |
|---|---|---|
| Migration DB | **Alembic** | Thay `create_all` — quản lý thay đổi schema an toàn hơn |
| Xử lý video dài | **Celery + Redis** | Video dài cần chạy nền, không block HTTP request |
| Refresh token | python-jose | JWT hết hạn 7 ngày — thêm refresh token an toàn hơn |
| Token blacklist | Redis | Logout thực sự vô hiệu hóa token |
| Rate limiting | **slowapi** | Chống spam request detect |
| Logging | **structlog** | Log có cấu trúc, dễ phân tích |
| Monitoring | **Prometheus + Grafana** | Theo dõi hiệu năng server |
| Deploy | **Docker + docker-compose** | Đóng gói ứng dụng dễ deploy |
| HTTPS | **Nginx + Let's Encrypt** | Bắt buộc ở production |

---

*Cập nhật: 2026-03-14*
