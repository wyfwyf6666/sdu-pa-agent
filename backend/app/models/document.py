# backend/app/models/document.py

from pydantic import BaseModel
from typing import List, Optional

class Document(BaseModel):
    id: str               # UUID 或数据库主键
    filename: str         # 浏览器下载时显示的原始文件名
    stored_name: str      # 磁盘实际保存的文件名，如 uuid.pdf
    size: int
    upload_time: str
    category: str
    tags: List[str]
    type: str
    processed: bool

# 知识组相关模型
class KnowledgeGroup(BaseModel):
    """知识组模型"""
    id: str
    name: str
    description: Optional[str] = ""
    created_time: str
    updated_time: str
    document_count: int = 0
    storage_path: str
    vector_path: str
    user_id: str  # 知识组所属用户ID

class KnowledgeGroupCreate(BaseModel):
    """创建知识组请求"""
    name: str
    description: Optional[str] = ""

class KnowledgeGroupUpdate(BaseModel):
    """更新知识组请求"""
    name: Optional[str] = None
    description: Optional[str] = None
