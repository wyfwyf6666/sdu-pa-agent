from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Dict, Any, Optional
from backend.app.models.document import (
    KnowledgeGroup,
    KnowledgeGroupCreate,
    KnowledgeGroupUpdate
)
from backend.app.models.user import User
from backend.app.dependencies.auth import get_current_user
from backend.app.services.knowledge_group import knowledge_group_service
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/knowledge-groups", response_model=Dict[str, Any])
async def create_knowledge_group(
    payload: KnowledgeGroupCreate,
    current_user: User = Depends(get_current_user)
):
    """创建新的知识组"""
    try:
        group = knowledge_group_service.create_group(
            name=payload.name,
            description=payload.description or "",
            user_id=current_user.user_id
        )
        return {
            "status": "success",
            "data": group
        }
    except Exception as e:
        logger.error(f"创建知识组失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge-groups", response_model=Dict[str, Any])
async def list_knowledge_groups(current_user: User = Depends(get_current_user)):
    """获取知识组列表（管理员看所有，普通用户看自己的）"""
    try:
        groups = knowledge_group_service.list_groups(
            user_id=current_user.user_id,
            user_role=current_user.role.value
        )
        return {
            "status": "success",
            "data": groups
        }
    except Exception as e:
        logger.error(f"获取知识组列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge-groups/{group_id}", response_model=Dict[str, Any])
async def get_knowledge_group(
    group_id: str,
    current_user: User = Depends(get_current_user)
):
    """获取单个知识组详情"""
    try:
        # 检查权限
        if not knowledge_group_service.check_group_access(
            group_id, current_user.user_id, current_user.role.value
        ):
            raise HTTPException(
                status_code=403,
                detail="无权访问该知识组"
            )

        group = knowledge_group_service.get_group(group_id)
        if not group:
            raise HTTPException(status_code=404, detail=f"知识组 {group_id} 不存在")
        return {
            "status": "success",
            "data": group
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取知识组详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge-groups/{group_id}/data-files", response_model=Dict[str, Any])
async def validate_group_data_files(
    group_id: str,
    current_user: User = Depends(get_current_user)
):
    """校验并返回知识组中的数据文件列表"""
    try:
        # 检查权限
        if not knowledge_group_service.check_group_access(
            group_id, current_user.user_id, current_user.role.value
        ):
            raise HTTPException(
                status_code=403,
                detail="无权访问该知识组"
            )

        result = knowledge_group_service.validate_group_for_data_analysis(group_id)
        return {
            "status": "success" if result.get("valid") else "error",
            "data": result.get("data_files", []),
            "non_data_files": result.get("non_data_files", []),
            "message": result.get("message"),
            "valid": result.get("valid", False),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"校验知识组数据文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/knowledge-groups/{group_id}", response_model=Dict[str, Any])
async def update_knowledge_group(
    group_id: str,
    payload: KnowledgeGroupUpdate,
    current_user: User = Depends(get_current_user)
):
    """更新知识组信息"""
    try:
        # 检查权限
        if not knowledge_group_service.check_group_access(
            group_id, current_user.user_id, current_user.role.value
        ):
            raise HTTPException(
                status_code=403,
                detail="无权修改该知识组"
            )

        group = knowledge_group_service.update_group(
            group_id=group_id,
            name=payload.name,
            description=payload.description
        )
        return {
            "status": "success",
            "data": group
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"更新知识组失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/knowledge-groups/{group_id}", response_model=Dict[str, Any])
async def delete_knowledge_group(
    group_id: str,
    force: bool = Query(False, description="强制删除（包括其中的文档）"),
    current_user: User = Depends(get_current_user)
):
    """删除知识组"""
    try:
        # 检查权限
        if not knowledge_group_service.check_group_access(
            group_id, current_user.user_id, current_user.role.value
        ):
            raise HTTPException(
                status_code=403,
                detail="无权删除该知识组"
            )

        result = knowledge_group_service.delete_group(group_id, force=force)
        return {
            "status": "success",
            "data": result
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"删除知识组失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
