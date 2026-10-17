from fastapi import APIRouter, HTTPException, Query
import logging
from typing import Optional

from backend.app.services.knowledge_graph import knowledge_graph_service

router = APIRouter()
logger = logging.getLogger(__name__)


def _handle_not_found(exc: FileNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.get("/knowledge-graph/overview")
async def get_graph_overview():
    """知识图谱整体概览。"""
    try:
        data = knowledge_graph_service.get_overview()
        return {"status": "success", "data": data}
    except FileNotFoundError as exc:
        raise _handle_not_found(exc)
    except Exception as exc:  # pragma: no cover - 记录异常
        logger.exception("获取知识图谱概览失败: %s", exc)
        raise HTTPException(status_code=500, detail="获取知识图谱概览失败")


@router.get("/knowledge-graph/predicates")
async def list_predicates():
    """返回谓词列表用于筛选。"""
    try:
        data = knowledge_graph_service.get_predicates()
        return {"status": "success", "data": data}
    except FileNotFoundError as exc:
        raise _handle_not_found(exc)
    except Exception as exc:
        logger.exception("获取谓词列表失败: %s", exc)
        raise HTTPException(status_code=500, detail="获取谓词列表失败")


@router.get("/knowledge-graph/triples")
async def list_triples(
    q: Optional[str] = Query(None, description="关键词（模糊匹配）"),
    predicate: Optional[str] = Query(None, description="按谓词过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    """获取知识图谱三元组列表。"""
    try:
        data = knowledge_graph_service.search_triples(q, predicate, page, page_size)
        return {"status": "success", "data": data}
    except FileNotFoundError as exc:
        raise _handle_not_found(exc)
    except Exception as exc:
        logger.exception("获取三元组列表失败: %s", exc)
        raise HTTPException(status_code=500, detail="获取三元组失败")


@router.get("/knowledge-graph/graph")
async def get_graph_view(
    center: Optional[str] = Query(None, description="中心节点（模糊匹配）"),
    depth: int = Query(1, ge=1, le=5),
    limit: int = Query(120, ge=20, le=300),
):
    """获取图谱可视化数据。"""
    try:
        data = knowledge_graph_service.get_graph_view(center=center, depth=depth, limit=limit)
        return {"status": "success", "data": data}
    except FileNotFoundError as exc:
        raise _handle_not_found(exc)
    except Exception as exc:
        logger.exception("获取图谱视图失败: %s", exc)
        raise HTTPException(status_code=500, detail="获取图谱视图失败")


@router.post("/knowledge-graph/reload")
async def reload_graph():
    """重新加载city.json。"""
    try:
        data = knowledge_graph_service.reload()
        return {"status": "success", "data": data}
    except FileNotFoundError as exc:
        raise _handle_not_found(exc)
    except Exception as exc:
        logger.exception("重新加载知识图谱失败: %s", exc)
        raise HTTPException(status_code=500, detail="重新加载失败")
