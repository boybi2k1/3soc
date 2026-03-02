from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import datetime
import os
import shutil
from pathlib import Path
from uuid import uuid4
import cv2
import json
from app.db import SessionLocal
from app.models import VideoFile, Detection
from app.schemas.file import VideoFileCreate, VideoFileUpdate, VideoFileResponse
from app.schemas.response import DetectionResult
from app.auth import get_current_user_from_token
from app import tasks

router = APIRouter(prefix="/files", tags=["files"])

# Upload directory
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/upload", response_model=VideoFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
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
    timestamp = int(os.path.getmtime(__file__) * 1000) if os.path.exists(__file__) else 0
    file_ext = Path(file.filename).suffix
    unique_filename = f"{timestamp}_{file.filename}"
    actual_path = UPLOAD_DIR / unique_filename
    
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
    web_path = f"/uploads/{unique_filename}"

    db_file = VideoFile(
        filename=file.filename,
        filepath=web_path,
        user_id=user_id,
        file_size=file_size,
        duration=duration,
        status="uploaded"
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)
    
    return db_file


@router.get("", response_model=List[VideoFileResponse])
def get_files(skip: int = 0, limit: int = 100, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    """Get list of files - users see only their own, admins see all"""
    # Get user from token
    user_data = get_current_user_from_token(authorization)
    user_id = user_data.get("user_id")
    role = user_data.get("role")
    
    # Filter based on role
    if role == "admin":
        # Admin sees all files
        files = db.query(VideoFile).options(joinedload(VideoFile.owner)).offset(skip).limit(limit).all()
    else:
        # Regular users see only their own files
        files = db.query(VideoFile).options(joinedload(VideoFile.owner)).filter(VideoFile.user_id == user_id).offset(skip).limit(limit).all()
    
    return files


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(file_id: int, db: Session = Depends(get_db)):
    """Delete file"""
    file = db.query(VideoFile).filter(VideoFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Delete physical file
    try:
        # file.filepath is a web path like /uploads/<filename>
        # Resolve physical path by basename
        filename = os.path.basename(file.filepath)
        physical_path = UPLOAD_DIR / filename
        if physical_path.exists():
            physical_path.unlink()
    except Exception as e:
        print(f"Warning: Failed to delete physical file: {e}")
    
    # Delete database record
    db.delete(file)
    db.commit()
    return None


@router.post("/{file_id}/detect")
def detect_file(file_id: int, db: Session = Depends(get_db)):
    """
    Run detection on video file.
    - Check if violations folder exists → load from folder
    - Otherwise process and save to folder
    """
    file = db.query(VideoFile).filter(VideoFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    # If already detected, load from folder
    if file.detection_id:
        violation_dir = UPLOAD_DIR / "violations" / file.detection_id
        if violation_dir.exists():
            print(f"[FILES] Loading cached detection from folder: {file.detection_id}")
            violations = _load_violations_from_folder(violation_dir, file.detection_id)
            return {
                "detection_id": file.detection_id,
                "total_frames": 0,
                "processed_frames": len(violations),
                "violation_count": len(violations),
                "violations": violations,
                "cached": True,
            }

    # Not cached, need to process
    filename = os.path.basename(file.filepath)
    video_path = UPLOAD_DIR / filename

    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Physical file not found")

    # Create detection ID and violation directory
    detection_id = str(uuid4())
    violation_dir = UPLOAD_DIR / "violations" / detection_id
    violation_dir.mkdir(parents=True, exist_ok=True)
    
    # Save detection_id to file record
    file.detection_id = detection_id
    db.add(file)
    db.commit()
    
    print(f"[FILES] Starting detection: {detection_id}")
    print(f"[FILES] Video path: {video_path}")

    # Extract frames every 0.25 seconds (4 frames per second)
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_interval = int(fps * 0.25)  # Extract every 0.25s
    
    print(f"[FILES] Video: {total_frames} frames, {fps} fps, interval={frame_interval}")

    # Process frames
    violation_images = []
    frame_count = 0
    processed_frame_count = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # Extract every N frames (0.25s interval)
        if frame_count % frame_interval == 0:
            processed_frame_count += 1
            timestamp = frame_count / fps
            
            # Run detection on this frame
            frame_results = tasks.run_detection_on_frame(frame)
            
            # If there are detections, save the frame
            if frame_results:
                # Save violation frame first
                frame_filename = f"frame_{processed_frame_count:05d}_ts{timestamp:.2f}.jpg"
                frame_path = violation_dir / frame_filename
                cv2.imwrite(str(frame_path), frame)
                
                # Check if this frame is a duplicate of previous frames
                is_duplicate = tasks._is_duplicate_frame(str(frame_path), violation_images)
                
                if is_duplicate:
                    print(f"[FILES] Frame {processed_frame_count} @ {timestamp:.2f}s - Duplicate, skipping")
                    try:
                        frame_path.unlink()
                    except:
                        pass
                    frame_count += 1
                    continue
                
                # Compute perceptual hash
                frame_hash = tasks._compute_image_hash(str(frame_path))
                
                # Save violation record (only if not duplicate)
                violation_record = {
                    "frame_number": processed_frame_count,
                    "timestamp": round(timestamp, 2),
                    "image_path": f"/uploads/violations/{detection_id}/{frame_filename}",
                    "detections": frame_results,
                    "_hash": frame_hash,
                }
                violation_images.append(violation_record)
                
                # Save metadata JSON (only if not duplicate)
                metadata_file = violation_dir / f"frame_{processed_frame_count:05d}_metadata.json"
                with open(metadata_file, 'w') as f:
                    json.dump({
                        "frame_number": processed_frame_count,
                        "timestamp": round(timestamp, 2),
                        "detections": frame_results,
                    }, f)
                
                print(f"[FILES] Frame {processed_frame_count} @ {timestamp:.2f}s - {len(frame_results)} detections (saved)")
        
        frame_count += 1
    
    cap.release()

    # Remove internal _hash field
    for v in violation_images:
        v.pop("_hash", None)

    print(f"[FILES] Detection complete: {len(violation_images)} unique violation frames found")
    
    return {
        "detection_id": detection_id,
        "total_frames": total_frames,
        "processed_frames": processed_frame_count,
        "violation_count": len(violation_images),
        "violations": violation_images,
        "cached": False,
    }


def _load_violations_from_folder(violation_dir: Path, detection_id: str) -> list:
    """Load violation images and metadata from folder."""
    violations = []
    
    # Find all metadata JSON files
    metadata_files = sorted(violation_dir.glob("*_metadata.json"))
    
    for metadata_file in metadata_files:
        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            # Get corresponding image
            frame_num = metadata.get("frame_number", 0)
            image_filename = f"frame_{frame_num:05d}_ts{metadata.get('timestamp', 0):.2f}.jpg"
            image_path = violation_dir / image_filename
            
            # Only add if image file exists
            if not image_path.exists():
                print(f"[FILES] Warning: Image not found for {metadata_file.name}, skipping")
                continue
            
            violation = {
                "frame_number": metadata.get("frame_number"),
                "timestamp": metadata.get("timestamp"),
                "image_path": f"/uploads/violations/{detection_id}/{image_filename}",
                "detections": metadata.get("detections", []),
            }
            violations.append(violation)
        except Exception as e:
            print(f"[FILES] Error loading metadata {metadata_file}: {e}")
    
    return violations



@router.get("/{file_id}/detect-stream")
def detect_file_stream(file_id: int, db: Session = Depends(get_db)):
    """
    SSE endpoint to stream violations as they're detected.
    Frontend can listen to this to get real-time updates.
    """
    file = db.query(VideoFile).filter(VideoFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    filename = os.path.basename(file.filepath)
    video_path = UPLOAD_DIR / filename

    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Physical file not found")

    # Reuse existing detection_id or create new one
    detection_id = file.detection_id or str(uuid4())
    violation_dir = UPLOAD_DIR / "violations" / detection_id
    
    # If already detected and cached, stream cached results
    if file.detection_id and violation_dir.exists():
        cached_violations = _load_violations_from_folder(violation_dir, detection_id)
        
        def stream_cached():
            yield f"data: {json.dumps({'type': 'init', 'detection_id': detection_id})}\n\n"
            yield f"data: {json.dumps({'type': 'metadata', 'total_frames': len(cached_violations), 'fps': None})}\n\n"
            for v in cached_violations:
                yield f"data: {json.dumps({'type': 'violation', 'data': v})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'total_violations': len(cached_violations)})}\n\n"
        
        return StreamingResponse(stream_cached(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})

    # Not cached, need to process
    violation_dir.mkdir(parents=True, exist_ok=True)

    # Create a generator that yields SSE events
    def stream_detection():
        # Save detection_id to file record if new
        db_new = SessionLocal()
        file_update = db_new.query(VideoFile).filter(VideoFile.id == file_id).first()
        if file_update and not file_update.detection_id:
            file_update.detection_id = detection_id
            file_update.status = "processing"
            db_new.add(file_update)
            db_new.commit()
        
        # Create detection record
        record = Detection(
            detection_id=detection_id,
            source=str(video_path),
            results=[],
            summary={"total_frames": 0, "processed_frames": 0},
        )
        db_new.add(record)
        db_new.commit()
        db_new.refresh(record)
        
        # Yield metadata
        yield f"data: {json.dumps({'type': 'init', 'detection_id': detection_id})}\n\n"

        # Extract frames
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_interval = int(fps * 0.25)
        
        yield f"data: {json.dumps({'type': 'metadata', 'total_frames': total_frames, 'fps': fps})}\n\n"

        violation_images = []
        frame_count = 0
        processed_frame_count = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            if frame_count % frame_interval == 0:
                processed_frame_count += 1
                timestamp = frame_count / fps
                
                frame_results = tasks.run_detection_on_frame(frame)
                
                if frame_results:
                    # Save frame first
                    frame_filename = f"frame_{processed_frame_count:05d}_ts{timestamp:.2f}.jpg"
                    frame_path = violation_dir / frame_filename
                    cv2.imwrite(str(frame_path), frame)
                    
                    # Check for duplicate
                    is_duplicate = tasks._is_duplicate_frame(str(frame_path), violation_images)
                    
                    if is_duplicate:
                        print(f"[SSE] Frame {processed_frame_count} @ {timestamp:.2f}s - Duplicate, skipping")
                        try:
                            frame_path.unlink()
                        except:
                            pass
                        frame_count += 1
                        continue
                    
                    frame_hash = tasks._compute_image_hash(str(frame_path))
                    
                    violation_record = {
                        "frame_number": processed_frame_count,
                        "timestamp": round(timestamp, 2),
                        "image_path": f"/uploads/violations/{detection_id}/{frame_filename}",
                        "detections": frame_results,
                        "_hash": frame_hash,
                    }
                    violation_images.append(violation_record)
                    
                    # Save metadata JSON
                    metadata_file = violation_dir / f"frame_{processed_frame_count:05d}_metadata.json"
                    with open(metadata_file, 'w') as f:
                        json.dump({
                            "frame_number": processed_frame_count,
                            "timestamp": round(timestamp, 2),
                            "detections": frame_results,
                        }, f)
                    
                    # Yield violation via SSE
                    violation_to_send = {
                        "frame_number": violation_record["frame_number"],
                        "timestamp": violation_record["timestamp"],
                        "image_path": violation_record["image_path"],
                        "detections": violation_record["detections"],
                    }
                    yield f"data: {json.dumps({'type': 'violation', 'data': violation_to_send})}\n\n"
                    
                    # Update DB
                    record.results = violation_images
                    record.summary = {
                        "total_frames": total_frames,
                        "processed_frames": processed_frame_count,
                        "violation_count": len(violation_images),
                    }
                    db_new.add(record)
                    db_new.commit()
            
            frame_count += 1
        
        cap.release()
        
        # Remove hashes
        for v in violation_images:
            v.pop("_hash", None)
        
        # Final update
        record.results = violation_images
        record.summary = {
            "total_frames": total_frames,
            "processed_frames": processed_frame_count,
            "violation_count": len(violation_images),
        }
        db_new.add(record)
        db_new.commit()
        
        # Update file
        file_update = db_new.query(VideoFile).filter(VideoFile.id == file_id).first()
        if file_update:
            file_update.status = "completed"
            db_new.add(file_update)
            db_new.commit()
        
        db_new.close()
        
        # Yield completion
        yield f"data: {json.dumps({'type': 'complete', 'total_violations': len(violation_images)})}\n\n"

    return StreamingResponse(stream_detection(), media_type="text/event-stream")


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
            