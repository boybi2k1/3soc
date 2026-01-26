import asyncio
import json
import base64
import logging
import time
from io import BytesIO
import cv2
import numpy as np
from fastapi import WebSocket
from typing import Set
import psutil

logger = logging.getLogger("3soc")

class WebSocketManager:
    def __init__(self, loaded_models, device):
        self.active_connections: Set[WebSocket] = set()
        self.loaded_models = loaded_models
        self.device = device
        self.stats_task = None
        self.frame_count = 0
        self.last_stats_time = time.time()
        self.fps = 0

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"[WebSocket] Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"[WebSocket] Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast_stats(self):
        """Broadcast system stats every 1 second"""
        while True:
            try:
                await asyncio.sleep(1)
                
                # Calculate FPS
                current_time = time.time()
                if current_time - self.last_stats_time > 0:
                    self.fps = self.frame_count / (current_time - self.last_stats_time)
                    self.frame_count = 0
                    self.last_stats_time = current_time

                # Get system stats
                cpu_percent = psutil.cpu_percent(interval=0.1)
                memory = psutil.virtual_memory()
                memory_usage = memory.used
                memory_total = memory.total

                # GPU stats (if available)
                gpu_load = 0
                try:
                    import torch
                    if torch.cuda.is_available():
                        # Simple GPU load estimation
                        torch.cuda.synchronize()
                        props = torch.cuda.get_device_properties(0)
                        gpu_load = 45  # Placeholder - requires nvidia-ml-py for accurate value
                except Exception:
                    pass

                stats = {
                    "type": "stats",
                    "fps": round(self.fps, 2),
                    "cpuLoad": round(cpu_percent, 1),
                    "gpuLoad": round(gpu_load, 1),
                    "memoryUsage": memory_usage,
                    "memoryTotal": memory_total,
                    "queueLength": 0,  # TODO: implement queue tracking
                    "isOnline": True,
                    "timestamp": current_time
                }

                await self.broadcast(json.dumps(stats))
            except Exception as e:
                logger.warning(f"[WebSocket] Error broadcasting stats: {e}")

    async def broadcast(self, message: str):
        """Broadcast message to all connected clients"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.warning(f"[WebSocket] Failed to send to client: {e}")
                disconnected.append(connection)

        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)

    async def handle_frame(self, websocket: WebSocket, message: dict):
        """Handle frame detection"""
        try:
            frame_data = message.get("frameData", "")
            timestamp = message.get("timestamp", 0)
            video_id = message.get("videoId", "")

            # Decode base64 frame
            if not frame_data.startswith("data:image"):
                logger.warning("[WebSocket] Invalid frame data format")
                return

            # Extract base64 string
            header, encoded = frame_data.split(",", 1)
            image_data = base64.b64decode(encoded)
            image_array = np.frombuffer(image_data, dtype=np.uint8)
            frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

            if frame is None:
                logger.warning("[WebSocket] Failed to decode frame")
                return

            self.frame_count += 1

            # Get frame dimensions
            frame_height, frame_width = frame.shape[:2]

            # Run YOLO detection on all models
            boxes = []
            for model_name, model in self.loaded_models.items():
                try:
                    results = model(frame, device=self.device)
                    if results and len(results) > 0:
                        res = results[0]
                        
                        # Extract boxes - XYXY format (top-left, bottom-right)
                        if hasattr(res, 'boxes'):
                            xyxy = res.boxes.xyxy.cpu().numpy() if hasattr(res.boxes.xyxy, 'cpu') else res.boxes.xyxy
                            confs = res.boxes.conf.cpu().numpy() if hasattr(res.boxes.conf, 'cpu') else res.boxes.conf
                            
                            for i, box in enumerate(xyxy):
                                x1, y1, x2, y2 = [float(v) for v in box]
                                conf = float(confs[i]) if i < len(confs) else 0.0
                                
                                # Convert from XYXY to X, Y, Width, Height format
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
                    logger.warning(f"[WebSocket] Model {model_name} inference failed: {e}")

            # Send detection results back to client
            response = {
                "type": "detection",
                "timestamp": timestamp,
                "boxes": boxes,
                "frameSize": {
                    "width": frame_width,
                    "height": frame_height
                },
                "frameCount": self.frame_count
            }

            await websocket.send_text(json.dumps(response))

        except Exception as e:
            logger.error(f"[WebSocket] Error handling frame: {e}")


# Global WebSocket manager instance
ws_manager = None


def init_websocket_manager(loaded_models, device):
    """Initialize the WebSocket manager with models and device"""
    global ws_manager
    ws_manager = WebSocketManager(loaded_models, device)
    return ws_manager


def get_websocket_manager():
    """Get the WebSocket manager instance"""
    global ws_manager
    return ws_manager
