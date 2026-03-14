from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"

# Tạo thư mục nếu chưa có
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
