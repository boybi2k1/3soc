from sqlalchemy import Column, Integer, String, DateTime, Text, JSON
from sqlalchemy.sql import func
from app.db import Base


class Detection(Base):
    __tablename__ = "detections"
    id = Column(Integer, primary_key=True, index=True)
    detection_id = Column(String(64), unique=True, index=True, nullable=False)
    source = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    results = Column(JSON, nullable=True)
    summary = Column(JSON, nullable=True)

