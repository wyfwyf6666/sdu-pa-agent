from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import List, Optional
from backend.app.models.approval import ApprovalCreate, ApprovalAction
from backend.app.services.approval import approval_service
from backend.app.services.approval_ai import approval_ai_service
import logging

from backend.app.services.history_service import log_history

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/approvals")
async def create_approval(data: ApprovalCreate):
    """
    创建新的审批申请
    """
    try:
        # TODO: 从认证信息中获取申请人和部门
        applicant = "测试用户"
        department = "测试部门"

        approval = await approval_service.create_approval(data, applicant, department)
        return approval
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/approvals")
async def list_approvals(
        status: Optional[str] = None,
        department: Optional[str] = None,
        applicant: Optional[str] = None
):
    """
    获取审批列表
    """
    try:
        approvals = await approval_service.list_approvals(
            status=status,
            department=department,
            applicant=applicant
        )
        return approvals
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/approvals/{approval_id}")
async def get_approval(approval_id: int):
    """
    获取审批详情
    """
    try:
        approval = await approval_service.get_approval(approval_id)
        if not approval:
            raise HTTPException(status_code=404, detail="审批不存在")
        return approval
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approvals/{approval_id}/process")
async def process_approval(approval_id: int, action: ApprovalAction):
    """
    处理审批
    """
    try:
        logger.info(f"处理审批请求: approval_id={approval_id}, action={action}")

        # TODO: 从认证信息中获取处理人
        processor = "测试审批人"

        # 检查审批是否存在
        approval = await approval_service.get_approval(approval_id)
        if not approval:
            logger.error(f"审批不存在: approval_id={approval_id}")
            raise HTTPException(
                status_code=404,
                detail="找不到该审批申请"
            )

        # 处理审批
        result = await approval_service.process_approval(
            approval_id=approval_id,
            action=action,
            processor=processor
        )
        await log_history(
            type="approval",
            title="审批处理",
            description=f"审批 ID={approval_id} 操作：{action.action}",  # 用 action.action
            user=processor,
            status="success"
        )

        if not result:
            logger.error(f"审批处理失败: approval_id={approval_id}")
            raise HTTPException(
                status_code=400,
                detail="审批处理失败，请稍后重试"
            )

        logger.info(f"审批处理成功: approval_id={approval_id}, status={result.status}")
        return result

    except ValueError as e:
        logger.error(f"审批处理参数错误: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"审批处理异常: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="系统处理失败，请联系管理员"
        )


@router.post("/approvals/{approval_id}/files")
async def add_approval_file(
        approval_id: int,
        file: UploadFile = File(...)
):
    """
    添加审批附件
    """
    try:
        # 添加文件记录
        file_record = await approval_service.add_approval_file(
            approval_id=approval_id,
            filename=file.filename,
            file_type=file.content_type,
            file_size=0  # TODO: 获取文件大小
        )

        if not file_record:
            raise HTTPException(status_code=404, detail="审批不存在")

        # TODO: 保存文件到存储系统

        return file_record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/approvals/statistics")
async def get_approval_statistics(department: Optional[str] = None):
    """
    获取审批统计信息
    """
    try:
        stats = await approval_service.get_approval_statistics(department)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approvals/ai/analyze")
async def analyze_approval(approval_data: dict):
    """AI分析审批内容"""
    try:
        analysis = await approval_ai_service.analyze_approval(approval_data)
        return analysis
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approvals/ai/similar-cases")
async def get_similar_cases(approval_data: dict):
    """获取相似审批案例"""
    try:
        similar_cases = await approval_ai_service.get_similar_cases(approval_data)
        return similar_cases
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approvals/ai/suggest-comment")
async def suggest_approval_comment(data: dict):
    """生成AI建议的审批意见"""
    try:
        comment = await approval_ai_service.generate_approval_comment(
            data["approval"],
            data["analysis"]
        )
        return {"comment": comment}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
