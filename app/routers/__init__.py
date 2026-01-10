from fastapi import APIRouter
from app.routers.detection import router as detection_router
from app.routers.stats import router as stats_router

router = APIRouter()
router.include_router(detection_router, prefix="/api")
router.include_router(stats_router, prefix="/api")

