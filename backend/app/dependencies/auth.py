# backend/app/dependencies/auth.py

from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.app.models.user import User, UserRole
from backend.app.services.user_service import user_service
from backend.app.utils.auth import verify_token

# HTTP Bearer认证
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """获取当前登录用户"""
    token = credentials.credentials

    # 验证token
    token_data = verify_token(token)
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 获取用户信息
    user = user_service.get_user_by_id(token_data.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被停用"
        )

    return user


async def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """获取当前管理员用户（权限检查）"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足，需要管理员权限"
        )
    return current_user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> Optional[User]:
    """获取当前用户（可选，不强制要求登录）"""
    if credentials is None:
        return None

    token = credentials.credentials
    token_data = verify_token(token)
    if token_data is None:
        return None

    user = user_service.get_user_by_id(token_data.user_id)
    if user and user.is_active:
        return user

    return None
