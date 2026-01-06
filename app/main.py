import torch
from fastapi import FastAPI
from app.routes import router as predict_router, DEVICE

DEVICE_STR = DEVICE

app = FastAPI(title="YOLO Flag Detection API")
app.include_router(predict_router, prefix="/api")


@app.on_event("startup")
async def startup_event():
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

