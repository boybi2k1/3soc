#!/usr/bin/env python3
"""
Simple inference script that loads YOLO .pt models from `models/`
and runs them on example images (co3soc.png, duongluoibo.png).
Saves annotated images to `outputs/`.

Usage:
    pip install ultralytics opencv-python
    python infer_yolo.py
"""
from pathlib import Path
import sys
import cv2
from ultralytics import YOLO


MODELS = {
    "co3soc": Path("models/co3soc.pt"),
    "duongluoibo": Path("models/duongluoibo.pt"),
}


def run_model(model_path: Path, image_path: Path, out_dir: Path, conf: float = 0.25, imgsz: int = 1280):
    """
    Run a single YOLO model on a single image and save annotated output.
    """
    model = YOLO(str(model_path))
    results = model(str(image_path), imgsz=imgsz, conf=conf)
    if len(results) == 0:
        print(f"No results for {image_path.name} with model {model_path.name}")
        return
    res = results[0]
    # res.plot() returns an RGB numpy array with drawn boxes/labels
    annotated = res.plot()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{image_path.stem}__{model_path.stem}.jpg"
    # Convert RGB -> BGR for OpenCV saving
    annotated_bgr = cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR)
    cv2.imwrite(str(out_path), annotated_bgr)
    # Count boxes if available
    try:
        num_boxes = len(res.boxes)
    except Exception:
        num_boxes = 0
    print(f"Model={model_path.name} Image={image_path.name} -> saved {out_path} ({num_boxes} boxes)")


def main():
    out_dir = Path("outputs")
    pairs = [
        (MODELS["co3soc"], Path("co3soc.png")),
        (MODELS["duongluoibo"], Path("duongluoibo.png")),
    ]
    any_run = False
    for model_path, img_path in pairs:
        if not model_path.exists():
            print(f"[WARN] model file not found: {model_path}", file=sys.stderr)
            continue
        if not img_path.exists():
            print(f"[WARN] image file not found: {img_path}", file=sys.stderr)
            continue
        any_run = True
        run_model(model_path, img_path, out_dir)

    if not any_run:
        print("Nothing ran. Make sure model files exist in `models/` and images in project root.")


if __name__ == "__main__":
    main()

