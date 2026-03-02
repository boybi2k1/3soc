# 3SOC - YOLO Detection Backend (FastAPI)

Backend API cho bài toán phát hiện vi phạm giao thông bằng YOLO, hỗ trợ:
- Quản lý người dùng + xác thực JWT
- Upload video, detect vi phạm theo frame, lưu cache kết quả
- Detect ảnh nhanh (single image)
- Realtime detection qua WebSocket
- Stream tiến trình detect video qua SSE

---

## 1) Tổng quan kiến trúc

### Thành phần chính
- **FastAPI app**: `app/main.py`
- **Routers API**:
  - `app/routers/users.py` (auth + user management)
  - `app/routers/files.py` (upload, detect video/image, stream)
  - `app/routers/stats.py` (đã viết nhưng hiện **chưa include** vào `main.py`)
- **Database layer**:
  - `app/db.py` (SQLAlchemy engine, session, init DB)
  - `app/models.py` (ORM models)
- **YOLO inference logic**: `app/tasks.py`
- **Realtime WebSocket handler**: `app/websocket_handler.py`

### Các model YOLO đang dùng
Trong thư mục `models/`:
- `3soc.pt`
- `duongluoibo.pt`
- `vnmap.pt`

Hệ thống load nhiều model và gộp kết quả detection.

---

## 2) Cơ sở dữ liệu (DB)

### Kết nối
Trong `app/db.py`:
- Dùng SQLAlchemy với mặc định:
  - `mysql+pymysql://root:1234567890@localhost/detect_3soc`
- Có thể override bằng biến môi trường `DATABASE_URL`.

### Bảng dữ liệu

#### `users`
Lưu tài khoản hệ thống.

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | Integer (PK) | ID user |
| username | String(100), unique | Tên đăng nhập |
| email | String(255), unique | Email |
| password_hash | String(255) | Mật khẩu đã hash (argon2) |
| role | String(50) | `user` / `admin` |
| is_active | Boolean | Trạng thái tài khoản |
| created_at | DateTime | Thời điểm tạo |
| updated_at | DateTime | Thời điểm cập nhật |

Quan hệ: `users (1) -> (n) video_files`.

#### `video_files`
Lưu metadata video upload.

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | Integer (PK) | ID file |
| filename | String(255) | Tên gốc |
| filepath | String(500) | Web path, ví dụ `/uploads/<filename>` |
| user_id | Integer (FK users.id) | Chủ sở hữu |
| file_size | Integer | Byte |
| duration | Float | Giây |
| status | String(50) | `uploaded` / `processing` / `completed` / `error` |
| detection_id | String(64), index | Liên kết folder/record detect |
| created_at | DateTime | Thời điểm tạo |

#### `detections`
Lưu kết quả detect tổng hợp (đặc biệt cho luồng stream/realtime xử lý video).

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | Integer (PK) | ID record |
| detection_id | String(64), unique | Mã detect |
| source | String(255) | Nguồn dữ liệu |
| created_at | DateTime | Thời điểm tạo |
| results | JSON | Danh sách box detect |
| summary | JSON | Metadata thống kê |

### Khởi tạo và seed dữ liệu
- `init_db()` gọi `Base.metadata.create_all(...)` khi app startup.
- Startup sẽ seed user mặc định nếu thiếu:
  - `admin / admin123`
  - `user / user123`

---

## 3) Cấu trúc lưu file

- `uploads/`:
  - Video upload trực tiếp
  - `uploads/temp/`: ảnh tạm detect-image
  - `uploads/violations/<detection_id>/`:
    - Ảnh frame vi phạm `frame_XXXXX_tsYY.YY.jpg`
    - Metadata từng frame `frame_XXXXX_metadata.json`

Static mount tại `/uploads` nên frontend truy cập trực tiếp được qua URL path.

---

## 4) Xác thực và phân quyền

Trong `app/auth.py`:
- Hash password: **argon2** (`passlib`)
- JWT:
  - `ALGORITHM = HS256`
  - Expire mặc định: **7 ngày**
  - `SECRET_KEY` lấy từ env (fallback có sẵn, nên thay ở production)
- Header yêu cầu: `Authorization: Bearer <token>`

Phân quyền:
- API admin dùng dependency `require_admin`
- API file list tự lọc theo role:
  - admin xem tất cả
  - user chỉ xem file của chính mình

---

## 5) Luồng nghiệp vụ detection

### Video detection (`POST /api/files/{file_id}/detect`)
1. Kiểm tra file tồn tại.
2. Nếu file đã có `detection_id` và folder vi phạm còn tồn tại -> load cache từ JSON + ảnh, trả ngay.
3. Nếu chưa cache:
   - Tạo `detection_id`
   - Cắt frame mỗi `0.25s` (khoảng 4 FPS xử lý)
   - Chạy tất cả model YOLO trên frame
   - Nếu có detection thì lưu ảnh frame
   - Khử trùng lặp bằng perceptual hash (`_compute_image_hash`, `_is_duplicate_frame`)
   - Lưu metadata JSON
4. Trả danh sách vi phạm + thông tin tổng hợp.

### Video detection stream SSE (`GET /api/files/{file_id}/detect-stream`)
- Trả `text/event-stream`, emit các event:
  - `init`
  - `metadata`
  - `violation` (mỗi frame hợp lệ)
  - `complete`
- Nếu đã cache thì stream từ cache.
- Nếu chưa cache thì vừa xử lý vừa stream realtime.

### Image detection (`POST /api/files/detect-image`)
- Nhận 1 ảnh upload.
- Lưu tạm vào `uploads/temp/`.
- Chạy tất cả model qua `run_detection_on_image_temp`.
- Trả kết quả ngay, sau đó xóa file tạm.

### Realtime WebSocket (`/realtime`)
- Client gửi frame base64 theo message type `frame`.
- Server decode ảnh, chạy YOLO trên tất cả model, trả về `boxes`.
- Có task broadcast metrics mỗi giây (`fps`, cpu, memory, ...).

---

## 6) API chi tiết

Base URL mặc định khi chạy local: `http://localhost:8000`

> Router được mount với prefix `/api`.

## 6.1 Users API (`/api/users`)

### `POST /api/users/register`
Đăng ký user mới.

Body:
```json
{
  "username": "string",
  "email": "user@example.com",
  "password": "string",
  "role": "user"
}
```

### `POST /api/users/login`
Đăng nhập, trả JWT.

Body:
```json
{
  "username": "admin",
  "password": "admin123"
}
```

Response chính:
```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "user": { "id": 1, "username": "admin", "email": "admin@example.com", "role": "admin", "is_active": true, "created_at": "...", "updated_at": null }
}
```

### `GET /api/users/me`
Lấy thông tin user hiện tại (cần Bearer token).

### `GET /api/users`
Lấy danh sách user (**admin only**).

### `GET /api/users/{user_id}`
Lấy user theo ID (**admin only**).

### `PUT /api/users/{user_id}`
Cập nhật user (**admin only**).

Body có thể gồm:
- `username`, `email`, `password`, `role`, `is_active`

### `DELETE /api/users/{user_id}`
Xóa user (**admin only**).

### `POST /api/users/change-password`
Đổi mật khẩu user hiện tại.

Body:
```json
{
  "old_password": "old",
  "new_password": "new"
}
```

### `POST /api/users/logout`
Logout phía client (server trả message, không có token blacklist).

---

## 6.2 Files API (`/api/files`)

### `POST /api/files/upload`
Upload file video (multipart).

- Field: `file`
- Header: `Authorization: Bearer <token>`

Validation:
- Chỉ nhận `content_type` bắt đầu bằng `video/`.

### `GET /api/files`
Lấy danh sách file.

- `admin`: xem tất cả
- `user`: chỉ xem file của mình

Query:
- `skip` (default 0)
- `limit` (default 100)

### `DELETE /api/files/{file_id}`
Xóa file DB + cố gắng xóa file vật lý trong `uploads/`.

### `POST /api/files/{file_id}/detect`
Detect video theo batch (không stream), có cơ chế cache theo `detection_id`.

Response gồm:
- `detection_id`
- `total_frames`
- `processed_frames`
- `violation_count`
- `violations` (mỗi item có `frame_number`, `timestamp`, `image_path`, `detections`)
- `cached` (`true/false`)

### `GET /api/files/{file_id}/detect-stream`
Detect video theo SSE (`text/event-stream`).

Event payload dạng:
```json
{ "type": "init", "detection_id": "..." }
{ "type": "metadata", "total_frames": 1234, "fps": 30 }
{ "type": "violation", "data": { "frame_number": 10, "timestamp": 2.5, "image_path": "/uploads/violations/...", "detections": [] } }
{ "type": "complete", "total_violations": 12 }
```

### `POST /api/files/detect-image`
Detect ảnh đơn (multipart `file`, content-type phải là `image/*`).

Response gồm:
- `filename`
- `detections`
- `path` (đường dẫn temp đã xử lý)
- `timestamp`
- `user_id` (nếu có token hợp lệ)

---

## 6.3 Stats API

File `app/routers/stats.py` có các endpoint:
- `GET /stats/overview`
- `GET /stats/by-model`
- `GET /stats/by-date`

Hiện tại router stats **chưa được include** trong `app/main.py`, nên mặc định chưa truy cập được qua API runtime.

---

## 7) Realtime protocol (WebSocket)

Endpoint: `ws://localhost:8000/realtime`

Client gửi:
```json
{
  "type": "frame",
  "frameData": "data:image/jpeg;base64,...",
  "timestamp": 1710000000000,
  "videoId": "abc"
}
```

Server trả:
```json
{
  "type": "detection",
  "timestamp": 1710000000000,
  "boxes": [
    {
      "x": 100,
      "y": 120,
      "width": 60,
      "height": 80,
      "label": "co3soc",
      "confidence": 0.91
    }
  ],
  "frameSize": { "width": 1280, "height": 720 },
  "frameCount": 10
}
```

Ngoài ra server broadcast định kỳ event `stats` cho tất cả client đang kết nối.

---

## 8) Cài đặt và chạy project

### Yêu cầu
- Python 3.9+
- MySQL
- (Tùy chọn) GPU CUDA để tăng tốc inference

### Cài dependencies
```bash
pip install -r requirements.txt
```

### Biến môi trường khuyến nghị
```bash
set DATABASE_URL=mysql+pymysql://root:password@localhost/detect_3soc
set SECRET_KEY=your-very-strong-secret
```

### Chạy server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Mở docs:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## 9) Ghi chú kỹ thuật

- `requirements.txt` có lặp `passlib[bcrypt]`, nhưng code auth đang dùng `argon2` (`passlib` + `argon2-cffi`).
- `app/main.py` đang log model load với biến `DEVICE` trước khi biến này được gán; có thể gây warning khi startup tùy môi trường.
- Project có script demo riêng: `infer_yolo.py` (chạy test inference ảnh đơn, độc lập API).

---

## 10) Hướng mở rộng đề xuất

- Thêm Alembic migration thay cho `create_all` trực tiếp.
- Thêm token blacklist/refresh token cho logout chuẩn hơn.
- Chuẩn hóa response schema cho các API detect (thống nhất kiểu dữ liệu).
- Tách worker queue (Celery/Redis) cho xử lý video dài.
