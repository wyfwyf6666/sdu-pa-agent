# backend/app/utils/auth.py

from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from backend.app.models.user import TokenData, UserRole

# JWT配置
SECRET_KEY = "your-secret-key-change-this-in-production"  # 生产环境请使用环境变量
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24小时


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建JWT token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[TokenData]:
    """验证JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        username: str = payload.get("username")
        role: str = payload.get("role")

        if user_id is None or username is None or role is None:
            return None

        token_data = TokenData(
            user_id=user_id,
            username=username,
            role=UserRole(role)
        )
        return token_data
    except JWTError:
        return None
