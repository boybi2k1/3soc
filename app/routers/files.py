from fastapi import APIRouter, Depends, HTTPException, status, UploadFile,Form, File, Header, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import datetime
import os
import shutil
import threading
import queue
from pathlib import Path
from uuid import uuid4
import cv2
import json
from app.db.db import SessionLocal
from app.db.models import VideoFile, Violation
from app.schemas.file import VideoFileResponse, VideoFileListResponse
from app.utils.auth import get_current_user_from_token
from app.utils import tasks
from app.config import UPLOAD_DIR
router = APIRouter(prefix="/files", tags=["files"])


def _resolve_physical_video_path(file: VideoFile) -> Optional[Path]:
    """Resolve physical video path from stored filepath, with legacy fallback."""
    filename = os.path.basename(file.filepath or "")
    direct = UPLOAD_DIR / filename
    if direct.exists():
        return direct

    # Legacy rows may store "/uploads/<id>" without extension.
    candidates = sorted(UPLOAD_DIR.glob(f"{filename}.*")) if filename else []
    if candidates:
        return candidates[0]

    return None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/upload", response_model=VideoFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    video_id: str = Form(...),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """Upload a video file"""
    # Get user from token
    user_data = get_current_user_from_token(authorization)
    user_id = user_data.get("user_id")
    
    # Validate file type
    if not file.content_type.startswith("video/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only video files are allowed"
        )
    
    # Generate unique filename
    # timestamp = int(os.path.getmtime(__file__) * 1000) if os.path.exists(__file__) else 0
    # file_ext = Path(file.filename).suffix
    # unique_filename = f"{timestamp}_{file.filename}"
    file_ext = Path(file.filename).suffix # Láº¥y .mp4, .mov...
    actual_path = UPLOAD_DIR / f"{video_id}{file_ext}"
    
    # Save file
    try:
        with actual_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}"
        )
    
    # Get file size
    file_size = actual_path.stat().st_size
    
    # Get video duration using OpenCV
    duration = None
    try:
        cap = cv2.VideoCapture(str(actual_path))
        if cap.isOpened():
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if fps > 0:
                duration = frame_count / fps
        cap.release()
    except Exception as e:
        print(f"Failed to get video duration: {e}")
    
    # Create database record
    # Store web-accessible path for frontend
    web_path = f"/uploads/{video_id}{file_ext}"

    db_file = VideoFile(
        id=video_id,
        filename=file.filename,
        filepath=web_path,
        user_id=user_id,
        file_size=file_size,
        duration=duration,
        # status="uploaded"
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)
    
    return db_file


@router.get("", response_model=VideoFileListResponse)
def get_files(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    skip: Optional[int] = Query(None, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=100),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Get list of files - users see only their own, admins see all"""
    # Get user from token
    user_data = get_current_user_from_token(authorization)
    user_id = user_data.get("user_id")
    role = user_data.get("role")

    if limit is not None:
        page_size = limit
    if skip is not None:
        page = (skip // page_size) + 1

    offset = (page - 1) * page_size
    
    # Filter based on role
    if role == "admin":
        # Admin sees all files
        base_query = db.query(VideoFile).options(joinedload(VideoFile.owner))
    else:
        # Regular users see only their own files
        base_query = db.query(VideoFile).options(joinedload(VideoFile.owner)).filter(VideoFile.user_id == user_id)

    total = base_query.count()
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    if sort_order == "asc":
        base_query = base_query.order_by(VideoFile.created_at.asc())
    else:
        base_query = base_query.order_by(VideoFile.created_at.desc())

    files = base_query.offset(offset).limit(page_size).all()

    return {
        "items": files,
        "meta": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1 and total_pages > 0,
        },
    }


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(file_id: str, db: Session = Depends(get_db)):
    """Delete file"""
    file = db.query(VideoFile).filter(VideoFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Delete physical file
    try:
        # file.filepath is a web path like /uploads/<filename>
        # Resolve physical path by basename
        physical_path = _resolve_physical_video_path(file)
        if physical_path and physical_path.exists():
            physical_path.unlink()
    except Exception as e:
        print(f"Warning: Failed to delete physical file: {e}")
    
    # Delete database record
    db.delete(file)
    db.commit()
    return None



def _load_violations_from_folder(video_id: str) -> list:
    """Load violation records from DB."""
    db = SessionLocal()
    try:
        rows = (
            db.query(Violation)
            .filter(Violation.video_id == video_id)
            .order_by(Violation.timestamp.asc())
            .all()
        )
        return [
            {
                "frame_number": r.frame_number,
                "timestamp": r.timestamp,
                "image_path": r.image_path,
                "detections": r.detections,
            }
            for r in rows
        ]
    except Exception as e:
        print(f"[FILES] _load_violations DB error: {e}")
        return []
    finally:
        db.close()


def _has_cached_violations(video_id: str) -> bool:
    """Return True when there are violation rows in DB for this video."""
    db = SessionLocal()
    try:
        return (
            db.query(Violation.id)
            .filter(Violation.video_id == video_id)
            .limit(1)
            .scalar()
            is not None
        )
    except Exception as e:
        print(f"[FILES] _has_cached_violations DB error: {e}")
        return False
    finally:
        db.close()



def _normalize_detections_for_ws_format(detections: list) -> list:
    """Normalize detection payload to websocket-style bbox format."""
    normalized = []

    for det in detections or []:
        if not isinstance(det, dict):
            continue

        # Already in websocket format.
        if all(k in det for k in ("x", "y", "width", "height")):
            normalized.append({
                "x": int(det.get("x", 0)),
                "y": int(det.get("y", 0)),
                "width": int(det.get("width", 0)),
                "height": int(det.get("height", 0)),
                "label": det.get("label") or det.get("model") or "object",
                "confidence": round(float(det.get("confidence", det.get("score", 0.0))), 4),
            })
            continue

        # Convert xyxy format to websocket format.
        if all(k in det for k in ("x1", "y1", "x2", "y2")):
            x1 = float(det.get("x1", 0))
            y1 = float(det.get("y1", 0))
            x2 = float(det.get("x2", x1))
            y2 = float(det.get("y2", y1))
            normalized.append({
                "x": int(x1),
                "y": int(y1),
                "width": int(max(0.0, x2 - x1)),
                "height": int(max(0.0, y2 - y1)),
                "label": det.get("label") or det.get("model") or "object",
                "confidence": round(float(det.get("confidence", det.get("score", 0.0))), 4),
            })

    return normalized



@router.get("/{file_id}/detect-stream")
def detect_file_stream(
    file_id: str,
    sample_ms: int = Query(100, ge=50, le=1000),
    cooldown_ms: int = Query(500, ge=0, le=5000),
    save_image_ms: int = Query(2000, ge=200, le=10000),
    db: Session = Depends(get_db),
):

    file = db.query(VideoFile).filter(VideoFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    video_path = _resolve_physical_video_path(file)

    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Physical file not found")

    violation_dir = UPLOAD_DIR / "violations" / file_id

    # =========================
    # STREAM CACHED RESULT
    # =========================
    if file.id and _has_cached_violations(file_id):

        cached = _load_violations_from_folder(file_id)

        def stream_cached():

            yield f"data: {json.dumps({'type':'init','detection_id':file_id})}\n\n"

            yield f"data: {json.dumps({'type':'metadata','total_frames':len(cached),'fps':None})}\n\n"

            for v in cached:
                yield f"data: {json.dumps({'type':'violation','data':v})}\n\n"

            yield f"data: {json.dumps({'type':'complete','total_violations':len(cached)})}\n\n"

        return StreamingResponse(
            stream_cached(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    violation_dir.mkdir(parents=True, exist_ok=True)

    # =========================
    # REALTIME DETECTION
    # =========================
    def stream_detection():

        db_new = SessionLocal()

        file_update = db_new.query(VideoFile).filter(VideoFile.id == file_id).first()
        if file_update:
            if not file_update.detection_id:
                file_update.detection_id = file_id
            file_update.status = "processing"
            db_new.add(file_update)
            db_new.commit()

        frame_queue = queue.Queue(maxsize=30)
        result_queue = queue.Queue(maxsize=30)

        stop_event = threading.Event()

        worker_count = 1   # náº¿u GPU â†’ 1, CPU â†’ 2-4

        violation_images = []

        # -----------------------
        # FRAME READER
        # -----------------------
        def read_frames():

            cap = cv2.VideoCapture(str(video_path))

            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            frame_interval = max(1, int(fps * (sample_ms / 1000)))

            frame_index = 0
            sampled_index = 0

            while not stop_event.is_set():

                ret, frame = cap.read()
                if not ret:
                    break

                if frame_index % frame_interval == 0:

                    sampled_index += 1
                    # Keep timestamp format aligned with websocket flow (milliseconds).
                    timestamp = int(round((frame_index / fps) * 1000))

                    frame_queue.put((sampled_index, timestamp, frame))

                frame_index += 1

            cap.release()

            for _ in range(worker_count):
                frame_queue.put(None)

        # -----------------------
        # DETECTION WORKER
        # -----------------------
        def detect_worker():

            while not stop_event.is_set():

                item = frame_queue.get()

                if item is None:
                    break

                frame_number, timestamp, frame = item

                try:

                    results = tasks.run_detection_on_frame(frame)
                    normalized_results = _normalize_detections_for_ws_format(results or [])

                    result_queue.put({
                        "frame_number": frame_number,
                        "timestamp": timestamp,
                        "frame": frame,
                        "detections": normalized_results
                    })

                except Exception as e:
                    print("Detection error:", e)

            result_queue.put({"type": "done"})

        # -----------------------
        # START THREADS
        # -----------------------
        reader = threading.Thread(target=read_frames, daemon=True)

        workers = [
            threading.Thread(target=detect_worker, daemon=True)
            for _ in range(worker_count)
        ]

        reader.start()

        for w in workers:
            w.start()

        # -----------------------
        # INIT SSE
        # -----------------------
        yield f"data: {json.dumps({'type':'init','detection_id':file_id})}\n\n"

        cap_meta = cv2.VideoCapture(str(video_path))
        fps = cap_meta.get(cv2.CAP_PROP_FPS) or 30
        total_frames = int(cap_meta.get(cv2.CAP_PROP_FRAME_COUNT))
        cap_meta.release()

        yield f"data: {json.dumps({'type':'metadata','total_frames':total_frames,'fps':fps})}\n\n"

        done_count = 0
        SAVE_COOLDOWN_SECONDS = cooldown_ms / 1000
        SAVE_IMAGE_SECONDS = save_image_ms / 1000
        # Cooldown riÃªng theo tá»«ng label cho event violation (áº£nh lÆ°u).
        last_saved_label_ms: dict = {}
        # Cooldown toÃ n cá»¥c cho viá»‡c lÆ°u áº£nh thumbnail.
        last_saved_image_ms = -1.0

        # -----------------------
        # RESULT LOOP
        # -----------------------
        while done_count < worker_count:

            try:
                item = result_queue.get(timeout=1)
            except queue.Empty:
                continue

            if item.get("type") == "done":
                done_count += 1
                continue

            frame_number = item["frame_number"]
            timestamp = item["timestamp"]
            frame = item["frame"]
            detections = item["detections"]

            # 1) Emit detection liÃªn tá»¥c Ä‘á»ƒ FE váº½ bbox mÆ°á»£t.
            yield f"data: {json.dumps({'type':'detection','data': {'frame_number': frame_number, 'timestamp': round(timestamp, 2), 'detections': detections}})}\n\n"
            if not detections:
                continue


            # 2) Chá»‰ chá»n label Ä‘á»§ cooldown Ä‘á»ƒ lÆ°u áº£nh violation.
            eligible = [
                d for d in detections
                if (timestamp - last_saved_label_ms.get(d.get("label", ""), 0)) / 1000 >= SAVE_COOLDOWN_SECONDS
            ]

            if not eligible:
                continue

            # 3) Cháº·n táº§n suáº¥t lÆ°u áº£nh toÃ n cá»¥c.
            if last_saved_image_ms >= 0 and (timestamp - last_saved_image_ms) / 1000 < SAVE_IMAGE_SECONDS:
                continue

            # Cáº­p nháº­t cooldown sau khi quyáº¿t Ä‘á»‹nh lÆ°u.
            for d in eligible:
                last_saved_label_ms[d.get("label", "")] = timestamp
            last_saved_image_ms = float(timestamp)

            safe_ts = f"{timestamp:08.2f}"
            frame_filename = f"ts_{safe_ts}_f{frame_number}.jpg"
            frame_path = violation_dir / frame_filename

            cv2.imwrite(str(frame_path), frame)

            violation = {
                "frame_number": frame_number,
                "timestamp": round(timestamp, 2),
                "image_path": f"/uploads/violations/{file_id}/{frame_filename}",
                "detections": eligible
            }

            violation_images.append(violation)

            try:
                db_new.add(Violation(
                    video_id=file_id,
                    frame_number=frame_number,
                    timestamp=round(timestamp, 2),
                    image_path=violation["image_path"],
                    detections=eligible,
                ))
                db_new.commit()
            except Exception as db_err:
                db_new.rollback()
                print(f"[FILES] Violation DB insert error: {db_err}")

            yield f"data: {json.dumps({'type':'violation','data':violation})}\n\n"

        stop_event.set()

        file_update = db_new.query(VideoFile).filter(VideoFile.id == file_id).first()
        if file_update:
            file_update.status = "completed"
            db_new.add(file_update)
            db_new.commit()

        db_new.close()

        yield f"data: {json.dumps({'type':'complete','total_violations':len(violation_images)})}\n\n"

    return StreamingResponse(
        stream_detection(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

#  detect image
@router.post("/detect-image")
def detect_image(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None)
):
    """
    Upload an image file and run detection on it.
    Returns detection results.
    """
    # Get user from token (optional)
    user_id = None
    try:
        if authorization:
            user_data = get_current_user_from_token(authorization)
            user_id = user_data.get("user_id")
    except Exception as e:
        print(f"[FILES] Warning: Failed to get user from token: {e}")
    
    # Validate file type
    if not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only image files are allowed"
        )
    
    # Save uploaded image to a temp location
    temp_dir = UPLOAD_DIR / "temp"
    temp_dir.mkdir(exist_ok=True)
    temp_image_path = temp_dir / f"{uuid4()}_{file.filename}"
    
    try:
        with temp_image_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Run detection
        results = tasks.run_detection_on_image_temp(str(temp_image_path))
        
        return {
            "filename": file.filename,
            "detections": results,
            "path": f"/uploads/temp/{temp_image_path.name}",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "user_id": user_id
        }
    except Exception as e:
        print(f"[FILES] Detection error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Detection failed: {str(e)}"
        )
    finally:
        # Clean up temp file
        try:
            if temp_image_path.exists():
                temp_image_path.unlink()
        except:
            pass
            
