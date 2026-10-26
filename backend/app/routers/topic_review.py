"""选题建议与文献综述 —— API 路由

- POST /topic-review/generate  一步完成：选题建议 + 文献搜集 + 文献综述
- POST /topic-review/export    把前端已拿到的文献列表导出为 Excel 总结表
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.app.services.topic_review import topic_review_service

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/topic-review", tags=["选题综述"])


class TopicReviewRequest(BaseModel):
    topic: str = Field(..., min_length=2, max_length=500, description="用户拟研究的选题")
    en_limit: int = Field(8, ge=1, le=20, description="英文文献条数上限")
    zh_limit: int = Field(8, ge=1, le=20, description="中文文献条数上限")


class PaperModel(BaseModel):
    title: str = ""
    authors: List[str] = []
    year: Optional[int] = None
    journal: str = ""
    abstract: str = ""
    doi: str = ""
    url: str = ""
    source: str = ""
    language: str = ""


class ExcelExportRequest(BaseModel):
    topic: str = ""
    papers: List[PaperModel] = []


@router.post("/generate")
async def generate_topic_review(req: TopicReviewRequest) -> Dict[str, Any]:
    """一步完成：选题建议 → 文献搜集 → 文献综述。"""
    try:
        suggestion = await topic_review_service.suggest_topic(req.topic)
        papers = await topic_review_service.search_literature(
            req.topic,
            en_limit=req.en_limit,
            zh_limit=req.zh_limit,
        )
        review = await topic_review_service.generate_review(req.topic, papers)
        return {
            "topic": req.topic,
            "suggestion": suggestion,
            "review": review,
            "papers": papers,
            "stats": {
                "total": len(papers),
                "en": sum(1 for p in papers if p.get("language") == "en"),
                "zh": sum(1 for p in papers if p.get("language") == "zh"),
            },
        }
    except Exception as exc:
        LOGGER.exception("topic review generate failed")
        raise HTTPException(status_code=500, detail=f"生成失败：{exc}")


@router.post("/export")
async def export_topic_review_excel(req: ExcelExportRequest) -> StreamingResponse:
    """把文献列表导出为 Excel 总结表。"""
    try:
        data = topic_review_service.export_excel([p.model_dump() for p in req.papers])
    except Exception as exc:
        LOGGER.exception("topic review excel export failed")
        raise HTTPException(status_code=500, detail=f"导出失败：{exc}")

    import urllib.parse

    filename = urllib.parse.quote(f"文献总结表_{req.topic[:20] or '选题'}.xlsx")
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
