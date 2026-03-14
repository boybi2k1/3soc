import asyncio
import json
import base64
import logging
import time
from pathlib import Path
from typing import Dict, Set

import cv2 # type: ignore
import numpy as np # type: ignore
import psutil # type: ignore
from fastapi import WebSocket # type: ignore
from app.config import UPLOAD_DIR
logger = logging.getLogger("3soc")


class WebSocketManager:

    def __init__(self, loaded_models, device):

        self.active_connections: Set[WebSocket] = set()
        self.loaded_models = loaded_models
        self.device = device

        # Keep separate counters for stats and persistent frame numbering.
        self.client_total_frames: Dict[WebSocket, int] = {}
        self.client_last_stats_frames: Dict[WebSocket, int] = {}
        self.video_frame_counters: Dict[str, int] = {}
        self.last_stats_time = time.time()

        # queue for saving violation frames
        self.save_queue = asyncio.Queue()
        self.sse_queues: Dict[str, asyncio.Queue] = {}

        self.stats_task = None
        self.save_worker_task = None

        # Limit how frequently violation frames are persisted per video stream.
        self.SAVE_COOLDOWN_SECONDS: float = 2.0
        self.last_saved_at_ms: Dict[str, float] = {}

    # -----------------------------
    # Connection management
    # -----------------------------

    async def connect(self, websocket: WebSocket):

        await websocket.accept()

        self.active_connections.add(websocket)
        self.client_total_frames[websocket] = 0
        self.client_last_stats_frames[websocket] = 0

        logger.info(f"[WebSocket] Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):

        self.active_connections.discard(websocket)
        self.client_total_frames.pop(websocket, None)
        self.client_last_stats_frames.pop(websocket, None)

        logger.info(f"[WebSocket] Client disconnected. Total: {len(self.active_connections)}")

    # -----------------------------
    # Background tasks
    # -----------------------------

    async def start_background_tasks(self):

        if not self.stats_task:
            self.stats_task = asyncio.create_task(self.broadcast_stats())

        if not self.save_worker_task:
            self.save_worker_task = asyncio.create_task(self.save_worker())

    async def close_all(self):
        """Close active websocket connections and stop background tasks."""
        # Stop background tasks first so they do not keep touching closed sockets.
        tasks = [self.stats_task, self.save_worker_task]
        for task in tasks:
            if task and not task.done():
                task.cancel()

        for task in tasks:
            if not task:
                continue
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(f"[Shutdown] Background task error: {e}")

        self.stats_task = None
        self.save_worker_task = None

        for websocket in list(self.active_connections):
            try:
                await websocket.close(code=1001, reason="Server reloading")
            except Exception:
                pass
            self.disconnect(websocket)

        self.sse_queues.clear()

    # -----------------------------
    # Stats broadcaster
    # -----------------------------

    async def broadcast_stats(self):

        while True:
            try:
                await asyncio.sleep(1)

                total_frames = 0
                for ws, total in list(self.client_total_frames.items()):
                    prev_total = self.client_last_stats_frames.get(ws, 0)
                    total_frames += max(0, total - prev_total)
                    self.client_last_stats_frames[ws] = total

                current_time = time.time()
                elapsed = current_time - self.last_stats_time

                fps = total_frames / elapsed if elapsed > 0 else 0

                self.last_stats_time = current_time

                cpu_percent = psutil.cpu_percent(interval=0.05)
                memory = psutil.virtual_memory()

                stats = {
                    "type": "stats",
                    "fps": round(fps, 2),
                    "cpuLoad": cpu_percent,
                    "memoryUsage": memory.used,
                    "memoryTotal": memory.total,
                    "queueLength": self.save_queue.qsize(),
                    "clients": len(self.active_connections),
                    "timestamp": current_time
                }

                await self.broadcast(json.dumps(stats))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[Stats] Error: {e}")

    # -----------------------------
    # Broadcast
    # -----------------------------

    async def broadcast(self, message: str):

        disconnected = []

        for connection in self.active_connections:

            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)

        for ws in disconnected:
            self.disconnect(ws)

    # -----------------------------
    # Frame handler
    # -----------------------------

    async def handle_frame(self, websocket: WebSocket, message: dict):

        try:

            frame_data = message.get("frameData")
            timestamp = message.get("timestamp", 0)
            video_id = message.get("videoId", "unknown")

            if not frame_data:
                return

            header, encoded = frame_data.split(",", 1)

            image_bytes = base64.b64decode(encoded)
            image_array = np.frombuffer(image_bytes, dtype=np.uint8)

            frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

            if frame is None:
                return

            self.client_total_frames[websocket] = self.client_total_frames.get(websocket, 0) + 1
            frame_number = self.video_frame_counters.get(video_id, 0) + 1
            self.video_frame_counters[video_id] = frame_number

            frame_height, frame_width = frame.shape[:2]

            tasks = [
                asyncio.to_thread(self.run_model, model_name, model, frame)
                for model_name, model in self.loaded_models.items()
            ]

            results = await asyncio.gather(*tasks)

            boxes = [box for model_boxes in results for box in model_boxes]

            # save violation
            if boxes:
                await self.save_queue.put(
                    (frame.copy(), video_id, frame_number, timestamp, boxes)
                )

            response = {
                "type": "detection",
                "timestamp": timestamp,
                "boxes": boxes,
                "frameSize": {
                    "width": frame_width,
                    "height": frame_height
                }
            }

            await websocket.send_text(json.dumps(response))

        except Exception as e:
            logger.error(f"[Frame] Error: {e}")

    # -----------------------------
    # Model inference
    # -----------------------------

    def run_model(self, model_name, model, frame):

        boxes = []

        try:

            results = model(frame, device=self.device)

            if results and len(results) > 0:

                res = results[0]

                if hasattr(res, "boxes"):

                    xyxy = res.boxes.xyxy.cpu().numpy()
                    confs = res.boxes.conf.cpu().numpy()

                    for i, box in enumerate(xyxy):

                        x1, y1, x2, y2 = box
                        conf = float(confs[i])

                        width = x2 - x1
                        height = y2 - y1

                        boxes.append({
                            "x": int(x1),
                            "y": int(y1),
                            "width": int(width),
                            "height": int(height),
                            "label": model_name,
                            "confidence": round(conf, 4)
                        })

        except Exception as e:
            logger.warning(f"[Model] {model_name} failed: {e}")

        return boxes

    # -----------------------------
    # Background save worker
    # -----------------------------

    async def save_worker(self):

        while True:

            frame, video_id, frame_number, timestamp, boxes = await self.save_queue.get()

            try:

                last_saved_ms = self.last_saved_at_ms.get(video_id, 0)
                # Skip disk writes if we are inside cooldown window for this video.
                if (timestamp - last_saved_ms) / 1000 < self.SAVE_COOLDOWN_SECONDS:
                    continue

                result = await asyncio.to_thread(
                    save_violation_frame,
                    frame,
                    video_id,
                    frame_number,
                    timestamp,
                    boxes
                )

                self.last_saved_at_ms[video_id] = timestamp
                # push event to SSE
                if video_id in self.sse_queues:
                    await self.sse_queues[video_id].put(result)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[SaveWorker] Failed: {e}")
            finally:
                self.save_queue.task_done()
    
    async def register_sse(self, video_id: str):

        queue = asyncio.Queue()
        self.sse_queues[video_id] = queue
        return queue


    def remove_sse(self, video_id: str):

        if video_id in self.sse_queues:
            del self.sse_queues[video_id]
            


ws_manager = None


def init_websocket_manager(loaded_models, device):
        global ws_manager
        ws_manager = WebSocketManager(loaded_models, device)
        return ws_manager


def get_websocket_manager():
        global ws_manager
        return ws_manager



def save_violation_frame(frame, detection_id, frame_number, timestamp, detections):
    violation_dir = UPLOAD_DIR / "violations" / detection_id
    violation_dir.mkdir(parents=True, exist_ok=True)

    safe_ts = f"{timestamp:08.2f}" 
    frame_filename = f"ts_{safe_ts}_f{frame_number}.jpg"
    frame_path = violation_dir / frame_filename

    # Lưu ảnh
    cv2.imwrite(str(frame_path), frame)

    metadata_filename = f"ts_{safe_ts}_f{frame_number}_metadata.json"
    metadata_file = violation_dir / metadata_filename

    with open(metadata_file, "w") as f:
        json.dump({
            "frame_number": frame_number,
            "timestamp": round(timestamp, 2),
            "detections": detections
        }, f)

    return {
        "frame_number": frame_number,
        "timestamp": round(timestamp, 2),
        "image_path": f"/uploads/violations/{detection_id}/{frame_filename}",
        "detections": detections
    }