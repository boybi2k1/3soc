from pydantic import BaseModel
from typing import List, Optional


class DetectionResult(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    score: float
    label: Optional[str] = None
    model: Optional[str] = None


class ImageDetectionResponse(BaseModel):
    detection_id: str
    status: str
    results: List[DetectionResult] = []


class VideoDetectionResponse(BaseModel):
    detection_id: str
    status: str
    frames_processed: int = 0
    results: List[DetectionResult] = []


class DetectionHistoryItem(BaseModel):
    detection_id: str
    created_at: str
    source: str
    summary: dict = {}


class DetectionHistoryResponse(BaseModel):
    total: int
    items: List[DetectionHistoryItem] = []


class StatisticsResponse(BaseModel):
    total_detections: int
    by_model: dict = {}
    by_date: dict = {}


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool

