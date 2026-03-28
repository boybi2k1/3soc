from ultralytics import YOLO
from pathlib import Path
import torch
from typing import List, Dict, Any
import traceback


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
                res_list = model(frame, save=False, verbose=False)
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


def run_detection_on_image_temp(image_path: str) -> List[Dict[str, Any]]:
    """
    Run all models on a temporary image file and return detections immediately.
    No DB save - just return results. Used for quick image detection from API.
    """
    aggregate_results = []
    try:
        for model_name, model in _MODELS.items():
            try:
                res_list = model(str(image_path), save=False, verbose=False)
                if len(res_list) == 0:
                    continue
                res = res_list[0]
                boxes = _boxes_from_result(res)
                # attach model name and label to each box
                for b in boxes:
                    b["model"] = model_name
                    b["label"] = model_name  # Add label for frontend
                aggregate_results.extend(boxes)
            except Exception as e:
                print(f"[TASKS] error running model {model_name}: {e}")
                traceback.print_exc()
    except Exception as e:
        print(f"[TASKS] unexpected error in run_detection_on_image_temp: {e}")
        traceback.print_exc()
    
    return aggregate_results
