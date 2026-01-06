from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from pathlib import Path
import uuid
import shutil
import cv2
from ultralytics import YOLO
from typing import List, Dict, Any
import torch

# Determine device early so models load on correct device
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"[INFO] DEVICE set to {DEVICE} (cuda_available={torch.cuda.is_available()})")

router = APIRouter()

# Map of short name -> model path
MODELS = {
    "co3soc": Path("models/co3soc.pt"),
    "duongluoibo": Path("models/duongluoibo.pt"),
}

# Load models on import to keep them in memory between requests
_LOADED_MODELS = {}
for name, path in MODELS.items():
    if path.exists():
        try:
            # load model onto desired device
            _LOADED_MODELS[name] = YOLO(str(path), device=DEVICE)
            print(f"[INFO] loaded model {name} on {DEVICE}")
        except Exception as e:
            print(f"[WARN] failed to load model {name}: {e}")


def _save_upload_tmp(upload: UploadFile) -> Path:
    tmp_dir = Path("tmp")
    tmp_dir.mkdir(exist_ok=True)
    suffix = Path(upload.filename).suffix or ".jpg"
    tmp_path = tmp_dir / f"{uuid.uuid4().hex}{suffix}"
    with tmp_path.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    return tmp_path


def _boxes_to_list(res) -> List[Dict[str, Any]]:
    boxes_out = []
    try:
        boxes = res.boxes
        xyxy = boxes.xyxy.cpu().numpy()  # (N,4)
        confs = boxes.conf.cpu().numpy()
        cls = boxes.cls.cpu().numpy().astype(int)
        for i, b in enumerate(xyxy):
            x1, y1, x2, y2 = [float(x) for x in b]
            boxes_out.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2, "score": float(confs[i]), "class": int(cls[i])})
    except Exception:
        # Best-effort: try older API or empty
        try:
            for box in getattr(res, "boxes", []):
                boxes_out.append({"x1": float(box[0]), "y1": float(box[1]), "x2": float(box[2]), "y2": float(box[3]), "score": float(box[4])})
        except Exception:
            pass
    return boxes_out


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/predict")
async def predict(model_name: str = Form(...), file: UploadFile = File(...)):
    """
    Single-image prediction.
    - model_name: 'co3soc' or 'duongluoibo'
    - file: image file upload
    """
    model_name = model_name.lower()
    if model_name not in MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown model '{model_name}'. Supported: {list(MODELS.keys())}")
    if model_name not in _LOADED_MODELS:
        # try to lazy-load
        model_path = MODELS[model_name]
        if not model_path.exists():
            raise HTTPException(status_code=500, detail=f"Model file not found on server: {model_path}")
        _LOADED_MODELS[model_name] = YOLO(str(model_path))

    tmp_path = _save_upload_tmp(file)
    try:
        model = _LOADED_MODELS[model_name]
        # ensure inference runs on selected device
        try:
            results = model(str(tmp_path), device=DEVICE)
        except TypeError:
            # fallback if model(...) does not accept device
            results = model(str(tmp_path))
        if len(results) == 0:
            return JSONResponse({"filename": file.filename, "boxes": [], "annotated_image": None})
        res = results[0]
        boxes = _boxes_to_list(res)
        # annotated image (RGB numpy)
        annotated = res.plot()
        out_dir = Path("outputs")
        out_dir.mkdir(exist_ok=True)
        out_name = f"{Path(file.filename).stem}__{model_name}__{uuid.uuid4().hex}.jpg"
        out_path = out_dir / out_name
        annotated_bgr = cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR)
        cv2.imwrite(str(out_path), annotated_bgr)
        return JSONResponse({"filename": file.filename, "boxes": boxes, "annotated_image": str(out_path)})
    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass

