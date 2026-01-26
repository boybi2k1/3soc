from ultralytics import YOLO
from pathlib import Path
import torch
from app.db import SessionLocal
from app.models import Detection
from typing import List, Dict, Any
import traceback
import cv2
import numpy as np

# Configure device
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"[TASKS] DEVICE={DEVICE} (cuda_available={torch.cuda.is_available()})")

# Models to run (3 models)
MODEL_FILES = {
    "co3soc": Path("models/3soc.pt"),
    "duongluoibo": Path("models/duongluoibo.pt"),
    "vnmap": Path("models/vnmap.pt"),
}

# load models
_MODELS = {}
for name, p in MODEL_FILES.items():
    if p.exists():
        try:
            _MODELS[name] = YOLO(str(p))
            print(f"[TASKS] loaded model {name} on {DEVICE}")
        except Exception as e:
            print(f"[TASKS] failed to load {name}: {e}")


def _compute_image_hash(image_path: str) -> str:
    """Compute a perceptual hash of an image for duplicate detection."""
    try:
        img = cv2.imread(image_path)
        if img is None:
            return ""
        # Resize to 8x8
        img_small = cv2.resize(img, (8, 8))
        # Convert to grayscale
        img_gray = cv2.cvtColor(img_small, cv2.COLOR_BGR2GRAY)
        # Compute mean
        mean = img_gray.mean()
        # Create hash: 1 if pixel > mean, 0 otherwise
        hash_str = "".join(["1" if pixel > mean else "0" for pixel in img_gray.flatten()])
        return hash_str
    except Exception as e:
        print(f"[TASKS] Error computing image hash: {e}")
        return ""


def _image_hash_distance(hash1: str, hash2: str) -> int:
    """Compute Hamming distance between two image hashes."""
    if not hash1 or not hash2 or len(hash1) != len(hash2):
        return float('inf')
    return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))


def _is_duplicate_frame(new_image_path: str, previous_frames: List[Dict], threshold: int = 8) -> bool:
    """
    Check if image is similar to any previous frame (using perceptual hash).
    threshold: Hamming distance threshold (0-64, lower = more similar)
    """
    if not previous_frames:
        return False
    
    new_hash = _compute_image_hash(new_image_path)
    if not new_hash:
        return False
    
    for prev in previous_frames[-5:]:  # Only compare with last 5 frames
        prev_hash = prev.get("_hash")
        if prev_hash and _image_hash_distance(new_hash, prev_hash) < threshold:
            return True
    
    return False


def _boxes_from_result(res) -> List[Dict[str, Any]]:
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
        # fallback
        try:
            for box in getattr(res, "boxes", []):
                boxes_out.append({"x1": float(box[0]), "y1": float(box[1]), "x2": float(box[2]), "y2": float(box[3]), "score": float(box[4])})
        except Exception:
            pass
    return boxes_out


def run_detection_on_frame(frame) -> List[Dict[str, Any]]:
    """
    Run all models on a single frame (numpy array) and return list of detections.
    Used for real-time frame processing in video detection.
    """
    aggregate_results = []
    try:
        for model_name, model in _MODELS.items():
            try:
                res_list = model(frame)
                if len(res_list) == 0:
                    continue
                res = res_list[0]
                boxes = _boxes_from_result(res)
                # attach model name to each box
                for b in boxes:
                    b["model"] = model_name
                aggregate_results.extend(boxes)
            except Exception as e:
                print(f"[TASKS] error running model {model_name} on frame: {e}")
    except Exception as e:
        print(f"[TASKS] unexpected error in run_detection_on_frame: {e}")
        traceback.print_exc()
    
    return aggregate_results


def run_detection_on_image(detection_id: str, image_path: str):
    """
    Run all available models on image_path and save aggregated results to DB.
    This runs in-process (background task) and updates the Detection record.
    """
    print(f"[TASKS] run_detection_on_image id={detection_id} image={image_path}")
    results_summary = {}
    aggregate_results = []
    try:
        for model_name, model in _MODELS.items():
            try:
                res_list = model(str(image_path))
                if len(res_list) == 0:
                    continue
                res = res_list[0]
                boxes = _boxes_from_result(res)
                # attach model name to each box
                for b in boxes:
                    b["model"] = model_name
                aggregate_results.extend(boxes)
                results_summary[model_name] = {"count": len(boxes)}
            except Exception as e:
                print(f"[TASKS] error running model {model_name}: {e}")
                traceback.print_exc()
                results_summary[model_name] = {"error": str(e)}

        # save to DB
        db = SessionLocal()
        try:
            record = db.query(Detection).filter(Detection.detection_id == detection_id).first()
            if record:
                record.results = aggregate_results
                record.summary = results_summary
                db.add(record)
                db.commit()
                print(f"[TASKS] saved results for {detection_id} (total_boxes={len(aggregate_results)})")
            else:
                print(f"[TASKS] record not found for {detection_id}")
        except Exception as e:
            db.rollback()
            print(f"[TASKS] failed to save results: {e}")
            traceback.print_exc()
        finally:
            db.close()
    except Exception as e:
        print(f"[TASKS] unexpected error: {e}")
        traceback.print_exc()
