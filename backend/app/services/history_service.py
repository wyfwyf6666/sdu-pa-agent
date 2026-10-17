# backend/app/services/history_service.py

from datetime import datetime
from typing import List, Optional
from backend.app.models.history import HistoryItem
from uuid import uuid4

# 内存存储操作历史；重启服务会丢失，生产环境需要换成持久化存储
_LOG: List[HistoryItem] = []

# 加入一些初始的 mock 数据，可根据需要删除
_LOG.extend([
    HistoryItem(
        id="1",
        type="upload",
        title="上传政策文件",
        description="成功上传《2024年政府工作报告》",
        timestamp=datetime(2024, 1, 15, 14, 30),
        status="success",
        user="张三"
    ),
    # … 其他初始记录
])

async def list_history(
    start: Optional[datetime] = None,
    end:   Optional[datetime] = None,
    type:  Optional[str]      = None,
    query: Optional[str]      = None,
) -> List[HistoryItem]:
    """
    按条件过滤并返回操作历史。支持按时间范围、类型、关键字过滤。
    """
    items = _LOG.copy()

    # 处理时区差异：将带 tzinfo 的参数转换为 naive datetime
    if start:
        if start.tzinfo is not None:
            start = start.replace(tzinfo=None)
        items = [i for i in items if i.timestamp >= start]
    if end:
        if end.tzinfo is not None:
            end = end.replace(tzinfo=None)
        items = [i for i in items if i.timestamp <= end]

    if type:
        items = [i for i in items if i.type == type]

    if query:
        q = query.lower()
        items = [
            i for i in items
            if q in i.title.lower() or q in i.description.lower()
        ]

    # 按时间倒序
    items.sort(key=lambda x: x.timestamp, reverse=True)
    return items

async def log_history(
    *,
    type:        str,
    title:       str,
    description: str,
    user:        Optional[str] = None,
    status:      Optional[str] = None,
    details:     Optional[dict]  = None,
):
    """
    记录一条操作历史到内存日志。
    id 会自动生成 UUID；
    timestamp 使用当前 UTC 时间。
    details 可以包含额外字段，比如 fileSize、duration 等。
    """
    item_dict = {
        "id": uuid4().hex,
        "type": type,
        "title": title,
        "description": description,
        "timestamp": datetime.utcnow(),
        "user": user,
        "status": status,
    }
    if details:
        item_dict.update(details)

    # 使用 Pydantic 验证并构造 HistoryItem
    item = HistoryItem(**item_dict)
    _LOG.append(item)
