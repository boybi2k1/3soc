from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Float, ForeignKey, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, backref
from app.db.db import Base


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), default="user")  # user, admin
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationship
    video_files = relationship("VideoFile", back_populates="owner")


class VideoFile(Base):
    __tablename__ = "video_files"
    
    id = Column(String(64), primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    filepath = Column(String(500), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    file_size = Column(Integer)  # bytes
    duration = Column(Float)  # seconds
    status = Column(String(50), default="uploaded")  # uploaded, processing, completed, error
    detection_id = Column(String(64), nullable=True, index=True)  # Link to detection folder
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationship
    owner = relationship("User", back_populates="video_files")



class Violation(Base):
    __tablename__ = "violations"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    video_id     = Column(String(64), ForeignKey("video_files.id"), nullable=False, index=True)
    frame_number = Column(Integer, nullable=False)
    timestamp    = Column(Float, nullable=False)        # milliseconds
    image_path   = Column(String(500), nullable=False)  # web path: /uploads/violations/...
    detections   = Column(JSON, nullable=False)         # [{x,y,width,height,label,confidence}]
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    video = relationship(
        "VideoFile",
        backref=backref("violations", cascade="all, delete-orphan")
    )
