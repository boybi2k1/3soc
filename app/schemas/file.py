from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class UserInfoBasic(BaseModel):
    id: int
    username: str
    email: str

    class Config:
        from_attributes = True


class VideoFileBase(BaseModel):
    filename: str
    filepath: str
    file_size: Optional[int] = None
    duration: Optional[float] = None


class VideoFileCreate(VideoFileBase):
    user_id: Optional[int] = None


class VideoFileUpdate(BaseModel):
    status: Optional[str] = None
    duration: Optional[float] = None


class VideoFileResponse(VideoFileBase):
    id: int
    user_id: Optional[int] = None
    status: str
    created_at: datetime
    owner: Optional[UserInfoBasic] = None

    class Config:
        from_attributes = True
