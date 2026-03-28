import torch
import numpy as np
from pathlib import Path
from ultralytics import YOLO

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.routers.users import router as users_router
from app.routers.files import router as files_router
from app.db.db import init_db, SessionLocal
from app.utils.auth import get_password_hash
from app.db.models import User



MODELS = {
    "co3soc": Path("models/3soc.pt"),
    "duongluoibo": Path("models/duongluoibo.pt"),
    "vnmap": Path("models/vnmap.pt"),
}
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
DEVICE_STR = DEVICE
_LOADED_MODELS = {}
for name, path in MODELS.items():
    if path.exists():
        try:
            # load model onto desired device
            _LOADED_MODELS[name] = YOLO(str(path))
            print(f"[INFO] loaded model {name} on {DEVICE_STR}")
        except Exception as e:
            print(f"[WARN] failed to load model {name}: {e}")
app = FastAPI(title="YOLO Flag Detection API")


@app.middleware("http")
async def add_uploads_cors_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/uploads/"):
        origin = request.headers.get("origin")
        response.headers["Access-Control-Allow-Origin"] = origin or "*"
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
    return response

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(users_router, prefix="/api")
app.include_router(files_router, prefix="/api")

# Serve uploaded files statically at /uploads
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


def seed_admin_if_missing():
    """Check if admin exists, if not create default users"""
    db = SessionLocal()
    try:
        # Check if admin user exists
        admin_exists = db.query(User).filter(User.username == "admin").first()
        
        if admin_exists:
            print("[INFO] Admin user already exists")
            return
        
        print("[INFO] Admin not found, creating default users...")
        
        # Create admin user
        admin = User(
            username="admin",
            email="admin@example.com",
            password_hash=get_password_hash("admin123"),
            role="admin",
            is_active=True
        )
        db.add(admin)
        
        # Create regular user
        user = User(
            username="user",
            email="user@example.com",
            password_hash=get_password_hash("user123"),
            role="user",
            is_active=True
        )
        db.add(user)
        
        db.commit()
        print("[INFO] ✓ Default users created successfully!")
        print("[INFO]   - Admin: admin / admin123")
        print("[INFO]   - User: user / user123")
        
    except Exception as e:
        print(f"[ERROR] Failed to seed admin user: {e}")
        db.rollback()
    finally:
        db.close()


@app.on_event("startup")
async def startup_event():
    # Initialize database
    print("[INFO] Initializing database...")
    init_db()
    
    # Seed admin user if missing
    print("[INFO] Checking for admin user...")
    seed_admin_if_missing()
    
    # Print device info at startup so logs show whether GPU will be used
    try:
        cuda_available = torch.cuda.is_available()
        print(f"[INFO] Using device: {DEVICE_STR} (cuda_available={cuda_available})")
        if cuda_available:
            try:
                print(f"[INFO] CUDA device name: {torch.cuda.get_device_name(0)}")
            except Exception:
                pass
    except Exception:
        print(f"[INFO] Using device: {DEVICE_STR}")
    
    # Warm up models with dummy frame to reduce first inference latency
    print("[INFO] Warming up models...")
    try:
        dummy_frame = np.zeros((640, 480, 3), dtype=np.uint8)
        for model_name, model in _LOADED_MODELS.items():
            try:
                print(f"[INFO] Warming up model: {model_name}")
                results = model(dummy_frame, device=DEVICE_STR, save=False, verbose=False)
                print(f"[INFO] ✓ Model {model_name} warmed up successfully")
            except TypeError:
                # Fallback if device parameter not supported
                try:
                    results = model(dummy_frame, save=False, verbose=False)
                    print(f"[INFO] ✓ Model {model_name} warmed up successfully (no device param)")
                except Exception as e:
                    print(f"[WARN] Failed to warm up {model_name}: {e}")
            except Exception as e:
                print(f"[WARN] Failed to warm up {model_name}: {e}")
    except Exception as e:
        print(f"[WARN] Model warm-up failed: {e}")
    
@app.on_event("shutdown")
async def shutdown_event():
    """Graceful shutdown"""
    print("[INFO] Shutting down application...")
    print("[INFO] Shutdown complete")

