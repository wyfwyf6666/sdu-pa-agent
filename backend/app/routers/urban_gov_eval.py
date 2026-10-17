from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.models.eval import (
    UrbanGovEvalPerTaskResult,
    UrbanGovEvalSummary,
    UrbanGovEvalTask,
)
from backend.app.services.urban_gov_eval import urban_gov_eval_service


router = APIRouter(prefix="/urban-gov-eval", tags=["urban_gov_eval"])


class RunEvalRequest(BaseModel):
    model_name: str = Field(..., description="参评模型名称")
    normalization_method: Literal["ratio", "relative"] = Field(
        "ratio", description="RACE-UG 归一化方式"
    )
    task_limit: Optional[int] = Field(
        None,
        ge=1,
        le=200,
        description="本次评测抽取题目上限（不填则使用后端默认阈值）",
    )


class LeaderboardItem(BaseModel):
    model_name: str
    overall_score: float
    race_score: float
    citation_accuracy: float
    effective_citations_norm: float
    task_metrics_norm: float
    updated_at: str


@router.get("/tasks", response_model=List[UrbanGovEvalTask])
async def list_tasks() -> List[UrbanGovEvalTask]:
    """列出 UrbanGovEval 任务集."""
    return urban_gov_eval_service.list_tasks()


@router.post("/run", response_model=UrbanGovEvalSummary)
async def run_eval(request: RunEvalRequest) -> UrbanGovEvalSummary:
    """触发评估流程."""
    return urban_gov_eval_service.run_evaluation(
        model_name=request.model_name.strip(),
        normalization_method=request.normalization_method,
        task_limit=request.task_limit,
    )


@router.get("/summary/{model_name}", response_model=UrbanGovEvalSummary)
async def get_summary(model_name: str) -> UrbanGovEvalSummary:
    """获取单模型评估摘要."""
    summary = urban_gov_eval_service.load_summary(model_name.strip())
    if not summary:
        raise HTTPException(status_code=404, detail="未找到该模型的评测结果")
    return summary


@router.get("/leaderboard", response_model=List[LeaderboardItem])
async def get_leaderboard() -> List[LeaderboardItem]:
    """获取 UrbanGovEval 评分榜."""
    items = urban_gov_eval_service.list_leaderboard()
    return [LeaderboardItem(**item) for item in items]


@router.get(
    "/per-task/{model_name}/{task_id}",
    response_model=UrbanGovEvalPerTaskResult,
)
async def get_per_task(model_name: str, task_id: str) -> UrbanGovEvalPerTaskResult:
    """获取单题落地剧本."""
    result = urban_gov_eval_service.load_per_task(
        model_name=model_name.strip(),
        task_id=task_id.strip(),
    )
    if not result:
        raise HTTPException(status_code=404, detail="未找到该题目的评测结果")
    return result
