# backend/app/routers/auth.py

from fastapi import APIRouter, HTTPException, status, Depends
from backend.app.models.user import (
    UserCreate,
    UserLogin,
    Token,
    UserResponse,
    User,
    UserRole
)
from backend.app.services.user_service import user_service
from backend.app.utils.auth import create_access_token
from backend.app.dependencies.auth import get_current_user, get_current_admin_user
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Token, summary="用户注册")
async def register(user_create: UserCreate):
    """
    用户注册接口

    - **username**: 用户名（3-50字符）
    - **password**: 密码（至少6字符）
    """
    try:
        # 创建新用户（默认为普通用户）
        user = user_service.create_user(user_create, role=UserRole.USER)

        # 生成token
        access_token = create_access_token(
            data={
                "sub": user.user_id,
                "username": user.username,
                "role": user.role
            }
        )

        # 返回token和用户信息
        return Token(
            access_token=access_token,
            token_type="bearer",
            user=UserResponse(
                user_id=user.user_id,
                username=user.username,
                role=user.role,
                created_time=user.created_time,
                last_login=user.last_login,
                is_active=user.is_active
            )
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"注册失败：{str(e)}"
        )


@router.post("/login", response_model=Token, summary="用户登录")
async def login(user_login: UserLogin):
    """
    用户登录接口

    - **username**: 用户名
    - **password**: 密码

    返回JWT token
    """
    # 验证用户
    user = user_service.authenticate_user(user_login.username, user_login.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 生成token
    access_token = create_access_token(
        data={
            "sub": user.user_id,
            "username": user.username,
            "role": user.role
        }
    )

    # 返回token和用户信息
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            user_id=user.user_id,
            username=user.username,
            role=user.role,
            created_time=user.created_time,
            last_login=user.last_login,
            is_active=user.is_active
        )
    )


@router.get("/me", response_model=UserResponse, summary="获取当前用户信息")
async def get_me(current_user: User = Depends(get_current_user)):
    """
    获取当前登录用户信息

    需要在请求头中携带 Authorization: Bearer <token>
    """
    return UserResponse(
        user_id=current_user.user_id,
        username=current_user.username,
        role=current_user.role,
        created_time=current_user.created_time,
        last_login=current_user.last_login,
        is_active=current_user.is_active
    )


@router.post("/logout", summary="用户登出")
async def logout(current_user: User = Depends(get_current_user)):
    """
    用户登出（客户端需要删除token）

    服务端记录登出历史
    """
    return {"message": "登出成功"}


@router.get("/users", response_model=list[UserResponse], summary="获取所有用户")
async def list_users(current_user: User = Depends(get_current_admin_user)):
    """
    获取所有用户列表（仅管理员）
    """
    users = user_service.list_users()
    return users


@router.put("/users/{user_id}/role", response_model=UserResponse, summary="更新用户角色")
async def update_user_role(
    user_id: str,
    role: UserRole,
    current_user: User = Depends(get_current_admin_user)
):
    """
    更新用户角色（仅管理员）

    - **user_id**: 用户ID
    - **role**: 新角色（admin或user）
    """
    user = user_service.update_user_role(user_id, role)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )

    return UserResponse(
        user_id=user.user_id,
        username=user.username,
        role=user.role,
        created_time=user.created_time,
        last_login=user.last_login,
        is_active=user.is_active
    )


@router.delete("/users/{user_id}", summary="停用用户")
async def deactivate_user(
    user_id: str,
    current_user: User = Depends(get_current_admin_user)
):
    """
    停用用户（仅管理员）

    - **user_id**: 用户ID
    """
    user = user_service.deactivate_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )

    return {"message": f"用户 {user.username} 已停用"}
