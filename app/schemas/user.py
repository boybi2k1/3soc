from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, List
from app.schemas.response import PaginationMeta


class UserBase(BaseModel):
    username: str
    email: EmailStr
    role: Optional[str] = "user"


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class LogoutResponse(BaseModel):
    message: str = "Logged out successfully"


class UserListResponse(BaseModel):
    items: List[UserResponse]
    meta: PaginationMeta
