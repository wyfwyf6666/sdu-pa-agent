# backend/app/services/user_service.py

import json
import uuid
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime
import bcrypt
from backend.app.models.user import User, UserCreate, UserRole, UserResponse

# 用户数据存储路径
ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT_DIR / "backend" / "data"
USERS_FILE = DATA_DIR / "users.json"


class UserService:
    """用户服务"""

    def __init__(self):
        """初始化用户服务"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._ensure_users_file()
        self._ensure_admin_exists()

    def _ensure_users_file(self):
        """确保用户文件存在"""
        if not USERS_FILE.exists():
            self._save_users({})

    def _ensure_admin_exists(self):
        """确保默认管理员账号存在"""
        users = self._load_users()
        # 检查是否已有管理员
        has_admin = any(u.get("role") == UserRole.ADMIN for u in users.values())

        if not has_admin:
            # 创建默认管理员账号
            admin = User(
                user_id=str(uuid.uuid4()),
                username="admin",
                password_hash=self.hash_password("admin123"),
                role=UserRole.ADMIN,
                created_time=datetime.now(),
                is_active=True
            )
            users[admin.user_id] = admin.dict()
            self._save_users(users)
            print(f"默认管理员账号已创建: username=admin, password=admin123")

    def _load_users(self) -> Dict:
        """加载用户数据"""
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_users(self, users: Dict):
        """保存用户数据"""
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2, default=str)

    def hash_password(self, password: str) -> str:
        """加密密码"""
        # 将密码转换为bytes并生成hash
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password_bytes, salt)
        # 返回字符串格式的hash
        return hashed.decode('utf-8')

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        password_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)

    def get_user_by_username(self, username: str) -> Optional[User]:
        """通过用户名获取用户"""
        users = self._load_users()
        for user_data in users.values():
            if user_data.get("username") == username:
                return User(**user_data)
        return None

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """通过ID获取用户"""
        users = self._load_users()
        user_data = users.get(user_id)
        if user_data:
            return User(**user_data)
        return None

    def create_user(self, user_create: UserCreate, role: UserRole = UserRole.USER) -> User:
        """创建新用户"""
        # 检查用户名是否已存在
        if self.get_user_by_username(user_create.username):
            raise ValueError(f"用户名 {user_create.username} 已存在")

        # 创建用户
        user = User(
            user_id=str(uuid.uuid4()),
            username=user_create.username,
            password_hash=self.hash_password(user_create.password),
            role=role,
            created_time=datetime.now(),
            is_active=True
        )

        # 保存用户
        users = self._load_users()
        users[user.user_id] = user.dict()
        self._save_users(users)

        return user

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """验证用户"""
        user = self.get_user_by_username(username)
        if not user:
            return None
        if not self.verify_password(password, user.password_hash):
            return None
        if not user.is_active:
            return None

        # 更新最后登录时间
        user.last_login = datetime.now()
        users = self._load_users()
        users[user.user_id] = user.dict()
        self._save_users(users)

        return user

    def list_users(self) -> List[UserResponse]:
        """获取所有用户列表"""
        users = self._load_users()
        return [
            UserResponse(
                user_id=user_data["user_id"],
                username=user_data["username"],
                role=user_data["role"],
                created_time=datetime.fromisoformat(user_data["created_time"]),
                last_login=datetime.fromisoformat(user_data["last_login"]) if user_data.get("last_login") else None,
                is_active=user_data.get("is_active", True)
            )
            for user_data in users.values()
        ]

    def update_user_role(self, user_id: str, new_role: UserRole) -> Optional[User]:
        """更新用户角色"""
        users = self._load_users()
        user_data = users.get(user_id)
        if not user_data:
            return None

        user_data["role"] = new_role
        users[user_id] = user_data
        self._save_users(users)

        return User(**user_data)

    def deactivate_user(self, user_id: str) -> Optional[User]:
        """停用用户"""
        users = self._load_users()
        user_data = users.get(user_id)
        if not user_data:
            return None

        user_data["is_active"] = False
        users[user_id] = user_data
        self._save_users(users)

        return User(**user_data)


# 全局用户服务实例
user_service = UserService()
