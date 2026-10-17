# backend/app/routers/history.py

from fastapi import APIRouter, Query
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
from backend.app.services.history_service import list_history
from backend.app.models.history import HistoryItem

router = APIRouter(prefix="/history", tags=["history"])

@router.get("", response_model=List[HistoryItem])
async def history(
    start: Optional[datetime] = Query(None),
    end:   Optional[datetime] = Query(None),
    type:  Optional[str]      = Query(None),
    query: Optional[str]      = Query(None),
):
    return await list_history(start=start, end=end, type=type, query=query)