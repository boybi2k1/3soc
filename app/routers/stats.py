from fastapi import APIRouter
from app.schemas.response import StatisticsResponse

router = APIRouter()


@router.get("/stats/overview", response_model=StatisticsResponse)
async def stats_overview():
    """
    Return basic statistics overview.
    """
    return {"total_detections": 0, "by_model": {}, "by_date": {}}


@router.get("/stats/by-model", response_model=dict)
async def stats_by_model():
    return {}


@router.get("/stats/by-date", response_model=dict)
async def stats_by_date():
    return {}

