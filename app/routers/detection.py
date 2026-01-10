from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from uuid import uuid4
from app.schemas.response import ImageDetectionResponse, VideoDetectionResponse
from typing import List
from pathlib import Path
import shutil
from app.db import SessionLocal
from app.models import Detection
from app import tasks
import json
from fastapi import Query
from app.schemas.response import DetectionHistoryResponse, DetectionHistoryItem
from datetime import datetime

router = APIRouter()


MEDIA_DIR = Path("media")
MEDIA_DIR.mkdir(exist_ok=True)


@router.post("/detect/image", response_model=ImageDetectionResponse)
async def detect_image(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Accept an image file, save to disk, create DB record and enqueue background detection.
    Processing will run in background worker to run 3 models and save results into database.
    """
    # save upload
    suffix = Path(file.filename).suffix or ".jpg"
    filename = f"{Path(file.filename).stem}__{uuid4().hex}{suffix}"
    dest = MEDIA_DIR / filename
    try:
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to save upload: {e}")

    detection_id = str(uuid4())

    # create DB record
    db = SessionLocal()
    try:
        record = Detection(detection_id=detection_id, source=str(dest), results=None, summary=None)
        db.add(record)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"failed to create DB record: {e}")
    finally:
        db.close()

    # enqueue background task
    background_tasks.add_task(tasks.run_detection_on_image, detection_id, str(dest))

    return {"detection_id": detection_id, "status": "queued", "results": []}


@router.post("/detect/video", response_model=VideoDetectionResponse)
async def detect_video(file: UploadFile = File(...)):
    """
    Accept a video file, enqueue processing to extract frames and run detection.
    """
    detection_id = str(uuid4())
    # TODO: implement video saving, DB record and enqueue background job
    return {"detection_id": detection_id, "status": "queued", "frames_processed": 0, "results": []}


@router.get("/detections", response_model=DetectionHistoryResponse)
async def list_detections(page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=200)):
    """
    List detection history with pagination.
    """
    db = SessionLocal()
    try:
        total = db.query(Detection).count()
        items_q = db.query(Detection).order_by(Detection.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
        items = []
        for r in items_q:
            items.append(DetectionHistoryItem(detection_id=r.detection_id, created_at=(r.created_at.isoformat() if r.created_at else ""), source=r.source, summary=r.summary or {}))
        return {"total": total, "items": items}
    finally:
        db.close()


@router.get("/detections/{detection_id}")
async def get_detection(detection_id: str):
    """
    Get detailed detection record by detection_id.
    """
    db = SessionLocal()
    try:
        r = db.query(Detection).filter(Detection.detection_id == detection_id).first()
        if not r:
            raise HTTPException(status_code=404, detail="detection not found")
        return {
            "detection_id": r.detection_id,
            "created_at": (r.created_at.isoformat() if r.created_at else None),
            "source": r.source,
            "results": r.results or [],
            "summary": r.summary or {},
        }
    finally:
        db.close()

