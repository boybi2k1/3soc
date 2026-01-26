# from fastapi import APIRouter, File, UploadFile, Form, HTTPException
# from fastapi.responses import JSONResponse
# from pathlib import Path
# import uuid
# import shutil
# import cv2
# from ultralytics import YOLO
# from typing import List, Dict, Any
# import torch
# import logging
# import json
# import datetime
# import os
# import subprocess

# # Determine device early so models load on correct device
# DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
# print(f"[INFO] DEVICE set to {DEVICE} (cuda_available={torch.cuda.is_available()})")
# # basic logger for this module
# logger = logging.getLogger("3soc")
# logger.setLevel(logging.INFO)
# if not logger.handlers:
#     ch = logging.StreamHandler()
#     ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
#     logger.addHandler(ch)

# router = APIRouter()
# FFMPEG = r"C:\Users\Admin\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe"

# # Map of short name -> model path
# MODELS = {
#     "co3soc": Path("models/3soc.pt"),
#     "duongluoibo": Path("models/duongluoibo.pt"),
#     "vnmap": Path("models/vnmap.pt"),
# }

# # Load models on import to keep them in memory between requests
# _LOADED_MODELS = {}
# for name, path in MODELS.items():
#     if path.exists():
#         try:
#             # load model onto desired device
#             _LOADED_MODELS[name] = YOLO(str(path))
#             print(f"[INFO] loaded model {name} on {DEVICE}")
#         except Exception as e:
#             print(f"[WARN] failed to load model {name}: {e}")


# def _save_upload_tmp(upload: UploadFile) -> Path:
#     tmp_dir = Path("tmp")
#     tmp_dir.mkdir(exist_ok=True)
#     suffix = Path(upload.filename).suffix or ".jpg"
#     tmp_path = tmp_dir / f"{uuid.uuid4().hex}{suffix}"
#     with tmp_path.open("wb") as f:
#         shutil.copyfileobj(upload.file, f)
#     return tmp_path


# def _boxes_to_list(res) -> List[Dict[str, Any]]:
#     boxes_out = []
#     try:
#         boxes = res.boxes
#         xyxy = boxes.xyxy.cpu().numpy()  # (N,4)
#         confs = boxes.conf.cpu().numpy()
#         cls = boxes.cls.cpu().numpy().astype(int)
#         for i, b in enumerate(xyxy):
#             x1, y1, x2, y2 = [float(x) for x in b]
#             boxes_out.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2, "score": float(confs[i]), "class": int(cls[i])})
#     except Exception:
#         # Best-effort: try older API or empty
#         try:
#             for box in getattr(res, "boxes", []):
#                 boxes_out.append({"x1": float(box[0]), "y1": float(box[1]), "x2": float(box[2]), "y2": float(box[3]), "score": float(box[4])})
#         except Exception:
#             pass
#     return boxes_out


# @router.get("/health")
# async def health():
#     return {"status": "ok"}



# @router.post("/predict_image")
# async def predict_image(file: UploadFile = File(...)):
#     """
#     Run inference on ALL loaded models using a single image upload.
#     Frontend will handle drawing bounding boxes, so we DO NOT draw or save annotated images here.
#     """
#     tmp_path = _save_upload_tmp(file)

#     results_all = {}

#     try:
#         # Read original image only to get size (for FE scaling)
#         annotated_bgr = cv2.imread(str(tmp_path))
#         if annotated_bgr is None:
#             # fallback: Windows unicode path
#             import numpy as np
#             annotated_bgr = cv2.imdecode(np.fromfile(str(tmp_path), dtype=np.uint8), cv2.IMREAD_COLOR)
#             if annotated_bgr is None:
#                 raise Exception("Failed to read uploaded image.")

#         original_height, original_width = annotated_bgr.shape[:2]

#         # Loop through models and run inference
#         for model_name, model in _LOADED_MODELS.items():
#             try:
#                 try:
#                     results = model(str(tmp_path), device=DEVICE)
#                 except TypeError:
#                     results = model(str(tmp_path))

#                 # no results
#                 if len(results) == 0:
#                     results_all[model_name] = {"boxes": []}
#                     continue

#                 res = results[0]
#                 boxes = _boxes_to_list(res)

#                 results_all[model_name] = {"boxes": boxes}

#             except Exception as e:
#                 results_all[model_name] = {"error": str(e)}

#         # Logging
#         try:
#             summary = {
#                 model: {
#                     "num_boxes": len(results_all.get(model, {}).get("boxes", [])),
#                     "error": results_all.get(model, {}).get("error")
#                 } for model in list(MODELS.keys())
#             }
#             logger.info("predict_all filename=%s summary=%s",
#                         file.filename, json.dumps(summary, ensure_ascii=False))

#             logs_dir = Path("logs")
#             logs_dir.mkdir(exist_ok=True)

#             log_record = {
#                 "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
#                 "filename": file.filename,
#                 "original_size": {"width": original_width, "height": original_height},
#                 "results": results_all
#             }

#             log_name = f"predict_all_{uuid.uuid4().hex}.json"
#             with (logs_dir / log_name).open("w", encoding="utf-8") as lf:
#                 json.dump(log_record, lf, ensure_ascii=False, indent=2)

#         except Exception as e:
#             logger.warning("Failed to write log: %s", e)

#         return JSONResponse({
#             "filename": file.filename,
#             "original_size": {"width": original_width, "height": original_height},
#             "results": results_all
#         })

#     finally:
#         try:
#             tmp_path.unlink()
#         except:
#             pass


# @router.post("/predict_video")
# async def predict_video_fast(file: UploadFile = File(...)):
#     """
#     Predict video using YOLO directly on frames (multi-thread),
#     no HTTP request, extremely fast.
#     """

#     # --- Save uploaded video to the common tmp directory ---
#     session_id = uuid.uuid4().hex
#     video_path = _save_upload_tmp(file)

#     # --- Get original video size early ---
#     cap_info = cv2.VideoCapture(str(video_path))
#     original_width = int(cap_info.get(cv2.CAP_PROP_FRAME_WIDTH))
#     original_height = int(cap_info.get(cv2.CAP_PROP_FRAME_HEIGHT))
#     cap_info.release()
#     logger.info(f"Original video size: {original_width}x{original_height}")

#     # --- Extract frames with FFmpeg into tmp ---
#     frames_dir = Path("tmp") / f"frames_{session_id}"
#     frames_dir.mkdir(parents=True, exist_ok=True)
#     cmd = [
#         FFMPEG,
#         "-y",
#         "-hide_banner",
#         "-loglevel", "error",
#         "-i", str(video_path),
#         "-vf", "fps=4",
#         str(frames_dir / "frame_%05d.jpg")
#     ]

#     # Log video file presence/size before running ffmpeg
#     try:
#         exists = video_path.exists()
#         size = video_path.stat().st_size if exists else 0
#     except Exception:
#         exists = False
#         size = 0
#     logger.info("Video file: %s exists=%s size=%d", video_path, exists, size)
#     result = subprocess.run(cmd, capture_output=True, text=True)
#     # Log ffmpeg command and outputs for debugging
#     try:
#         logger.info("FFMPEG CMD: %s", " ".join(cmd))
#         logger.info("FFMPEG RETURNCODE: %s", result.returncode)
#         logger.info("FFMPEG STDOUT: %s", result.stdout if result.stdout else "<empty>")
#         logger.info("FFMPEG STDERR: %s", result.stderr if result.stderr else "<empty>")
#         if result.returncode != 0:
#             logger.warning("FFMPEG returned non-zero exit code %s", result.returncode)
#     except Exception:
#         # fallback to prints if logging fails for some reason
#         print("FFMPEG CMD:", " ".join(cmd))
#         print("FFMPEG RETURNCODE:", result.returncode)
#         print("FFMPEG STDOUT:", result.stdout)
#         print("FFMPEG STDERR:", result.stderr)

#     # --- List frames ---
#     frames = sorted(frames_dir.glob("frame_*.jpg"))
#     logger.info("Frames extracted by ffmpeg: %d files in %s", len(frames), frames_dir)
#     if not frames:
#         logger.warning("FFMPEG produced no frames in %s; attempting OpenCV fallback", frames_dir)
#         try:
#             cap2 = cv2.VideoCapture(str(video_path))
#             if cap2.isOpened():
#                 src_fps = cap2.get(cv2.CAP_PROP_FPS) or 25
#                 # sample to ~4 fps
#                 target_fps = 4.0
#                 step = max(1, int(round(src_fps / target_fps)))
#                 idx = 0
#                 saved = 0
#                 while True:
#                     ok, img = cap2.read()
#                     if not ok or img is None:
#                         break
#                     if idx % step == 0:
#                         out_path = frames_dir / f"frame_{saved:05d}.jpg"
#                         cv2.imwrite(str(out_path), img)
#                         saved += 1
#                     idx += 1
#                 cap2.release()
#                 frames = sorted(frames_dir.glob("frame_*.jpg"))
#                 logger.info("OpenCV fallback saved %d frames to %s", len(frames), frames_dir)
#             else:
#                 # log diagnostic properties from VideoCapture even if not opened
#                 try:
#                     fc = cap2.get(cv2.CAP_PROP_FRAME_COUNT)
#                     fp = cap2.get(cv2.CAP_PROP_FPS)
#                     logger.warning("OpenCV could not open video for fallback: %s (frame_count=%s fps=%s)", video_path, fc, fp)
#                 except Exception:
#                     logger.warning("OpenCV could not open video for fallback: %s", video_path)
#         except Exception as e:
#             logger.warning("OpenCV fallback failed: %s", e)
#     if not frames:
#         # try one more check: try reading the first frame and save debug file
#         try:
#             cap_preview = cv2.VideoCapture(str(video_path))
#             ok, img0 = cap_preview.read()
#             cap_preview.release()
#             if ok and img0 is not None:
#                 debug_path = frames_dir / "debug_first_frame.jpg"
#                 frames_dir.mkdir(parents=True, exist_ok=True)
#                 cv2.imwrite(str(debug_path), img0)
#                 logger.info("Saved debug first frame to %s", debug_path)
#             else:
#                 logger.warning("OpenCV could not read even first frame for debug from %s", video_path)
#         except Exception as e:
#             logger.warning("Failed to capture debug first frame: %s", e)
#         return {"error": "Không thể extract frame; xem log để biết chi tiết"}

#     # --- Multithread detect ---
#     summary = {m: 0 for m in _LOADED_MODELS.keys()}
#     timeline = []

#     def detect_single_frame(frame_path, idx):
#         """YOLO detect trực tiếp trên frame."""
#         img = cv2.imread(str(frame_path))
#         if img is None:
#             return None

#         # Log frame size
#         h, w = img.shape[:2]
#         logger.info(f"Frame {idx}: {w}x{h}")

#         all_boxes = []

#         # Force calling model on the saved frame path (same behavior as predict_image)
#         for model_name, model in _LOADED_MODELS.items():
#             try:
#                 results = None
#                 try:
#                     results = model(str(frame_path), device=DEVICE)
#                 except TypeError:
#                     results = model(str(frame_path))
#                 except Exception:
#                     # try without device kwarg as final fallback
#                     try:
#                         results = model(str(frame_path))
#                     except Exception as e:
#                         logger.warning("Model %s failed on frame %s: %s", model_name, frame_path, e)
#                         continue

#                 if not results:
#                     continue
#                 r0 = results[0] if isinstance(results, (list, tuple)) else results
#                 boxes = _boxes_to_list(r0)

#                 summary[model_name] += len(boxes)
#                 for b in boxes:
#                     all_boxes.append({
#                         "label": model_name,
#                         "x1": int(b["x1"]),
#                         "y1": int(b["y1"]),
#                         "x2": int(b["x2"]),
#                         "y2": int(b["y2"]),
#                         "score": float(b.get("score", 0.0))
#                     })
#             except Exception as e:
#                 logger.warning(f"Detect error: {e}")

#         if all_boxes:
#             return {
#                 "frame_index": idx,
#                 "time_start_ms": idx * 250,
#                 "time_end_ms": (idx + 1) * 250,
#                 "boxes": all_boxes
#             }

#     # Run multithread
#     from concurrent.futures import ThreadPoolExecutor, as_completed

#     results = []
#     with ThreadPoolExecutor(max_workers=4) as executor:
#         futs = {executor.submit(detect_single_frame, f, i): (f, i)
#                 for i, f in enumerate(frames)}

#         for fut in as_completed(futs):
#             r = fut.result()
#             if r:
#                 results.append(r)

#     # Sort timeline by frame index
#     results.sort(key=lambda x: x["frame_index"])

#     # keep extracted frames in tmp (no extra folders); do not move to outputs
#     try:
#         video_path.unlink(missing_ok=True)
#     except Exception:
#         pass

#     return {
#         "filename": file.filename,
#         "original_size": {
#             "width": original_width,
#             "height": original_height
#         },
#         "frames_extracted": len(list(frames_dir.glob('frame_*.jpg'))),
#         "frames_dir": str(frames_dir),
#         "summary": summary,
#         "timeline": results
#     }
