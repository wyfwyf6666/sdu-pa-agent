# backend/app/models/user.py

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from enum import Enum


class UserRole(str, Enum):
    """用户角色枚举"""
    ADMIN = "admin"
    USER = "user"


class UserBase(BaseModel):
    """用户基础模型"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    role: UserRole = Field(default=UserRole.USER, description="用户角色")


class UserCreate(BaseModel):
    """创建用户请求模型"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=100, description="密码")


class UserLogin(BaseModel):
    """登录请求模型"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class User(UserBase):
    """完整用户模型"""
    user_id: str = Field(..., description="用户ID")
    password_hash: str = Field(..., description="密码哈希")
    created_time: datetime = Field(default_factory=datetime.now, description="创建时间")
    last_login: Optional[datetime] = Field(default=None, description="最后登录时间")
    is_active: bool = Field(default=True, description="是否激活")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class UserResponse(UserBase):
    """用户响应模型（不包含密码）"""
    user_id: str
    created_time: datetime
    last_login: Optional[datetime] = None
    is_active: bool = True

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class Token(BaseModel):
    """Token响应模型"""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TokenData(BaseModel):
    """Token数据模型"""
    user_id: str
    username: str
    role: UserRole
