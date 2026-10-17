# backend/app/models/history.py

from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class HistoryItem(BaseModel):
    id: str
    type: str               # 'document'|'chat'|'login'|'upload'|'approval'
    title: str
    description: str
    timestamp: datetime
    status: Optional[str] = None
    user: Optional[str] = None
    # 如果还有 details 字段，也可以加：
    # fileSize: Optional[str] = None
    # duration: Optional[str] = None
