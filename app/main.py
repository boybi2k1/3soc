import torch
import asyncio
import numpy as np
import cv2
from fastapi.responses import JSONResponse
from pathlib import Path
import uuid
import shutil
from ultralytics import YOLO
from typing import List, Dict, Any
import torch
import logging
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.utils.websocket_handler import init_websocket_manager, get_websocket_manager
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
logger = logging.getLogger("3soc")

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
                results = model(dummy_frame, device=DEVICE_STR)
                print(f"[INFO] ✓ Model {model_name} warmed up successfully")
            except TypeError:
                # Fallback if device parameter not supported
                try:
                    results = model(dummy_frame)
                    print(f"[INFO] ✓ Model {model_name} warmed up successfully (no device param)")
                except Exception as e:
                    print(f"[WARN] Failed to warm up {model_name}: {e}")
            except Exception as e:
                print(f"[WARN] Failed to warm up {model_name}: {e}")
    except Exception as e:
        print(f"[WARN] Model warm-up failed: {e}")
    
    # Initialize WebSocket manager with loaded models.
    # Background tasks are started lazily when the first websocket client connects.
    ws_manager = init_websocket_manager(_LOADED_MODELS, DEVICE_STR)
    print(f"[INFO] WebSocket manager initialized with {len(_LOADED_MODELS)} models")


@app.on_event("shutdown")
async def shutdown_event():
    """Graceful shutdown"""
    print("[INFO] Shutting down application...")
    try:
        ws_manager = get_websocket_manager()
        if ws_manager:
            await ws_manager.close_all()
    except Exception as e:
        print(f"[WARN] Error during shutdown: {e}")
    print("[INFO] Shutdown complete")

@app.websocket("/realtime")
async def websocket_endpoint(websocket: WebSocket):

    ws_manager = get_websocket_manager()

    if not ws_manager:
        await websocket.close(code=1000, reason="WebSocket manager not initialized")
        return

    await ws_manager.connect(websocket)

    # start background tasks (stats + save worker)
    await ws_manager.start_background_tasks()

    try:

        while True:

            data = await websocket.receive_text()

            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                logger.warning("[WebSocket] Invalid JSON received")
                continue

            message_type = message.get("type")

            if message_type == "frame":

                await ws_manager.handle_frame(websocket, message)

            elif message_type == "ping":

                await websocket.send_text(
                    json.dumps({"type": "pong"})
                )

            else:

                logger.debug(f"[WebSocket] Unknown message type: {message_type}")

    except WebSocketDisconnect:

        ws_manager.disconnect(websocket)
        logger.info("[WebSocket] Client disconnected")

    except Exception as e:

        logger.error(f"[WebSocket] Error: {e}")
        ws_manager.disconnect(websocket)


from fastapi.responses import StreamingResponse

@app.get("/file-stream/{video_id}")
async def stream_files(video_id: str):

    ws_manager = get_websocket_manager()

    queue = await ws_manager.register_sse(video_id)

    async def event_stream():

        try:

            while True:

                data = await queue.get()
                
                payload = {
                    "type": "violation",
                    "data": data
                }

                yield f"data: {json.dumps(payload)}\n\n"

        except asyncio.CancelledError:
            ws_manager.remove_sse(video_id)

    return StreamingResponse(event_stream(), media_type="text/event-stream")

