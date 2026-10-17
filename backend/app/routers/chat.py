import uuid
from typing import Any, Dict, List, Literal, Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.app.services.chat import chat_service
from backend.app.services.deep_research import deep_research_service
from backend.app.services.progress import progress_service
from backend.app.services.search import search_service
from backend.app.services.cancellation import cancellation_service, OperationCancelledError
from backend.app.services.document import document_service
from backend.app.services.data_analysis import data_analysis_service

router = APIRouter()

# 用于异步构建索引的线程池
index_build_executor = ThreadPoolExecutor(max_workers=2)
index_build_tasks = {}  # 存储构建任务状态


class Message(BaseModel):
    role: str
    content: str


class CloudModelConfig(BaseModel):
    preset: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    general_model: Optional[str] = None
    reasoning_model: Optional[str] = None
    max_iterations: Optional[int] = None


class ChatRequest(BaseModel):
    message: str
    enable_rag: Optional[bool] = False
    enable_web_search: Optional[bool] = False
    llm_type: Optional[str] = "deepseek"
    mode: Optional[Literal["basic", "deep_research", "data_analysis"]] = "basic"
    progress_id: Optional[str] = None
    request_id: Optional[str] = None
    model_source: Optional[Literal["cloud", "local"]] = "cloud"
    cloud_config: Optional[CloudModelConfig] = None
    max_iterations: Optional[int] = None
    # RAG scope selection
    library_type: Optional[Literal["public", "private"]] = None  # None = search all
    knowledge_group_ids: Optional[List[str]] = None
    # Data analysis mode
    analysis_language: Optional[Literal["python", "r"]] = None
    analysis_action: Optional[Literal["generate", "run"]] = "generate"
    analysis_code: Optional[str] = None
    analysis_knowledge_group_id: Optional[str] = None


class CancelChatRequest(BaseModel):
    request_id: Optional[str] = None
    progress_id: Optional[str] = None


class ApprovePlanRequest(BaseModel):
    progress_id: str
    revised_plan: Dict[str, Any]  # 包含 overall_strategy 和 tasks


@router.post("/chat")
async def chat(request: ChatRequest):
    """
    聊天接口，支持上下文对话、RAG、联网搜索和本地模型
    """
    request_token = request.request_id or str(uuid.uuid4())
    progress_token: Optional[str] = None
    analysis_group_id: Optional[str] = None

    await cancellation_service.register(request_token)

    try:
        # search_results = None
        # if request.enable_web_search:
        #     # 调用搜索服务获取搜索结果
        #     search_results = await search_service.search(request.message)

        # 获取聊天回复
        mode = (request.mode or "basic").lower()
        cloud_config = (
            request.cloud_config.model_dump(exclude_none=True) if request.cloud_config else None
        )

        if mode == "deep_research":
            progress_token = request.progress_id or str(uuid.uuid4())
            await cancellation_service.register(progress_token)
            progress_service.init_progress(progress_token)
            await cancellation_service.raise_if_cancelled(request_token, progress_token)
            result = await deep_research_service.run_workflow(
                question=request.message,
                llm_type=request.llm_type or "deepseek",
                progress_id=progress_token,
                cancel_tokens=[request_token, progress_token],
                cloud_config=cloud_config,
                max_iterations=request.max_iterations,
                library_type=request.library_type,
                knowledge_group_ids=request.knowledge_group_ids,
                enable_web_search=request.enable_web_search,
                enable_rag=request.enable_rag,
            )
            result.setdefault("meta", {})["progress_id"] = progress_token
        elif mode == "data_analysis":
            # 数据分析模式仅关注文件本身，不启用RAG或向量索引
            analysis_group_id = (
                request.analysis_knowledge_group_id
                or (request.knowledge_group_ids[0] if request.knowledge_group_ids else None)
            )
            result = await data_analysis_service.handle_request(
                instruction=request.message,
                language=request.analysis_language,
                knowledge_group_id=analysis_group_id,
                action=request.analysis_action or "generate",
                code=request.analysis_code,
                llm_type=request.llm_type,
                cloud_config=cloud_config,
                cancel_tokens=[request_token],
            )
        else:
            await cancellation_service.raise_if_cancelled(request_token)
            result = await chat_service.get_response(
                message=request.message,
                llm_type=request.llm_type,
                enable_rag=request.enable_rag,
                enable_web_search=request.enable_web_search,
                cancel_tokens=[request_token],
                cloud_config=cloud_config,
                library_type=request.library_type,
                knowledge_group_ids=request.knowledge_group_ids,
            )

        result.setdefault("meta", {})["request_id"] = request_token
        return result
    except OperationCancelledError as exc:
        if progress_token:
            progress_service.cancel_progress(progress_token)
        raise HTTPException(status_code=499, detail=str(exc))
    except Exception as e:
        if progress_token:
            progress_service.mark_error(progress_token, str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await cancellation_service.clear(request_token)
        if progress_token:
            await cancellation_service.clear(progress_token)


@router.get("/chat/progress/{progress_id}")
async def get_chat_progress(progress_id: str):
    """
    获取深度研究的实时进度信息
    """
    progress = progress_service.get_progress(progress_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Progress not found")
    return progress


@router.post("/chat/cancel")
async def cancel_chat(request: CancelChatRequest):
    """
    主动取消正在进行的对话或深度研究任务
    """
    if not (request.request_id or request.progress_id):
        raise HTTPException(status_code=400, detail="request_id or progress_id is required")

    cancel_tokens: List[str] = []
    if request.request_id:
        cancel_tokens.append(request.request_id)
    if request.progress_id and request.progress_id not in cancel_tokens:
        cancel_tokens.append(request.progress_id)

    cancelled_any = False
    for token in cancel_tokens:
        cancelled = await cancellation_service.cancel(token)
        cancelled_any = cancelled_any or cancelled

    if request.progress_id and cancelled_any:
        progress_service.cancel_progress(request.progress_id)

    return {"cancelled": cancelled_any}


@router.post("/chat/approve-plan")
async def approve_plan(request: ApprovePlanRequest):
    """
    接收用户修订的计划并继续深度研究工作流
    """
    try:
        success = deep_research_service.approve_plan(
            progress_id=request.progress_id,
            revised_plan=request.revised_plan
        )

        if success:
            return {
                "status": "success",
                "message": "计划已确认，工作流将继续执行"
            }
        else:
            raise HTTPException(
                status_code=404,
                detail="未找到等待确认的计划，可能已超时或已被确认"
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/clear-history")
async def clear_chat_history():
    """
    清除会话历史（包括数据分析模式）
    """
    try:
        # 清空普通聊天历史
        chat_service.clear_history()
        # 清空数据分析历史（所有知识组）
        data_analysis_service.clear_history()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/env-config")
async def get_env_config():
    """
    获取环境变量中的API配置
    """
    import os
    try:
        return {
            "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
            "openai_base_url": os.getenv("OPENAI_BASE_URL", ""),
            "dashscope_api_key": os.getenv("DASHSCOPE_API_KEY", ""),
            "dashscope_base_url": os.getenv("DASHSCOPE_BASE_URL", ""),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/image-preview/{knowledge_group_id}/{filename}")
async def get_image_preview(knowledge_group_id: str, filename: str):
    """
    获取数据分析生成的图片预览
    """
    try:
        from backend.app.services.knowledge_group import knowledge_group_service

        # 获取知识组信息
        group = knowledge_group_service.get_group(knowledge_group_id)
        if not group:
            raise HTTPException(status_code=404, detail="知识组不存在")

        # 构建图片路径
        from pathlib import Path
        import os

        image_path = Path(group["storage_path"]) / filename

        # 安全检查：确保文件在知识组目录内
        if not str(image_path.resolve()).startswith(str(Path(group["storage_path"]).resolve())):
            raise HTTPException(status_code=403, detail="无权访问此文件")

        if not image_path.exists():
            raise HTTPException(status_code=404, detail="图片不存在")

        # 返回图片文件
        return FileResponse(
            path=str(image_path),
            media_type=f"image/{image_path.suffix[1:]}",
            filename=filename
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class BuildMergedIndexRequest(BaseModel):
    library_type: Optional[Literal["public", "private"]] = "public"
    knowledge_group_id: Optional[str] = None


def _build_index_sync(task_id: str, library_type: str, knowledge_group_id: Optional[str]):
    """同步构建索引的函数，在线程池中执行"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        index_build_tasks[task_id] = {"status": "running", "message": "正在构建索引..."}
        logger.info("开始构建索引: task_id=%s, library_type=%s, group_id=%s",
                   task_id, library_type, knowledge_group_id)

        # 调用document_service构建索引
        document_service.build_merged_index(library_type, knowledge_group_id)

        index_build_tasks[task_id] = {
            "status": "completed",
            "message": "索引构建成功",
            "library_type": library_type,
            "knowledge_group_id": knowledge_group_id
        }
        logger.info("索引构建完成: task_id=%s", task_id)
    except Exception as e:
        logger.error("索引构建失败: task_id=%s, error=%s", task_id, str(e), exc_info=True)
        index_build_tasks[task_id] = {
            "status": "failed",
            "message": f"构建失败: {str(e)}",
            "error": str(e)
        }


@router.post("/chat/build-merged-index")
async def build_merged_index(request: BuildMergedIndexRequest):
    """
    异步构建合并索引，立即返回任务ID，用于加速RAG检索
    """
    try:
        library_type = request.library_type or "public"
        knowledge_group_id = request.knowledge_group_id

        # 验证私人库必须提供knowledge_group_id
        if library_type == "private" and not knowledge_group_id:
            raise HTTPException(
                status_code=400,
                detail="私人库必须指定knowledge_group_id"
            )

        # 生成任务ID
        task_id = str(uuid.uuid4())

        # 在线程池中异步执行构建
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            index_build_executor,
            _build_index_sync,
            task_id,
            library_type,
            knowledge_group_id
        )

        return {
            "status": "started",
            "task_id": task_id,
            "message": "索引构建已开始，请使用task_id查询进度",
            "library_type": library_type,
            "knowledge_group_id": knowledge_group_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动索引构建失败: {str(e)}")


@router.get("/chat/build-merged-index/{task_id}")
async def get_build_index_status(task_id: str):
    """
    查询索引构建任务的状态
    """
    if task_id not in index_build_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    return index_build_tasks[task_id]


@router.post("/chat/load-index")
async def load_index_to_cache(request: BuildMergedIndexRequest):
    """
    将索引文件加载到内存缓存中，用于预热缓存
    """
    try:
        library_type = request.library_type or "public"
        knowledge_group_id = request.knowledge_group_id

        # 验证私人库必须提供knowledge_group_id
        if library_type == "private" and not knowledge_group_id:
            raise HTTPException(
                status_code=400,
                detail="私人库必须指定knowledge_group_id"
            )

        # 触发一次空检索来加载索引到缓存
        # 使用一个随机查询，触发缓存加载
        await document_service.search_similar_texts(
            query="预热缓存",
            k=1,
            library_type=library_type,
            knowledge_group_ids=[knowledge_group_id] if knowledge_group_id else None
        )

        return {
            "status": "success",
            "message": "索引已加载到内存缓存",
            "library_type": library_type,
            "knowledge_group_id": knowledge_group_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"加载索引失败: {str(e)}")
