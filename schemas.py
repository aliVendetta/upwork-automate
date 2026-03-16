from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    upwork_user_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AdminResponse(BaseModel):
    id: int
    email: str
    username: str
    upwork_access_token: Optional[str]
    upwork_user_id: Optional[str] = None
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class JobQuery(BaseModel):
    job_id: str
