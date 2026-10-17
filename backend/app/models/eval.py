from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EvaluationCriterion(BaseModel):
    """UrbanGovEval 任务自适应评价标准."""

    id: str
    name: str
    description: str
    dimension: str
    weight: float
    reference_score: float
    reference_comment: Optional[str] = None


class FactExpectation(BaseModel):
    """任务级证据引用期望，用于归一化 FACT 指标."""

    expected_pairs: int = Field(..., ge=0)
    min_authority_ratio: float = Field(0.0, ge=0.0, le=1.0)
    min_timeliness_ratio: float = Field(0.0, ge=0.0, le=1.0)


class TaskMetricDefinition(BaseModel):
    """任务专属评价指标基线."""

    metric: str
    description: Optional[str] = None
    reference_value: Optional[float] = None


class UrbanGovEvalTask(BaseModel):
    """UrbanGovEval 单题定义."""

    task_id: str
    title: str
    domain: str
    task_type: str
    language: str
    difficulty: str
    time_ref: str
    query: str
    deliverable: str
    output_format: str
    reference_report: str
    criteria: List[EvaluationCriterion]
    fact_expectation: Optional[FactExpectation] = None
    task_metrics: List[TaskMetricDefinition] = Field(default_factory=list)


class CriterionScore(BaseModel):
    """单条 Criterion 的评估结果."""

    criterion_id: str
    name: str
    dimension: str
    weight: float
    target_score: float
    reference_score: float
    gap: float
    explanation: str
    reference_comment: Optional[str] = None


class RaceDimensionScore(BaseModel):
    """面向覆盖 / 深度 / 遵循 / 可读等维度的拆解."""

    dimension: str
    weighted_score: float
    normalized_score: float


class RaceResult(BaseModel):
    """RACE-UG 总分."""

    method: str
    target_total: float
    reference_total: float
    normalized_score: float
    ratio_score: float
    relative_advantage_score: float
    dimension_scores: List[RaceDimensionScore]


class FactPairResult(BaseModel):
    """声明 - 引用对的评判结果."""

    statement: str
    citation: str
    normalized_citation: str
    support: bool
    authority: bool
    timeliness: bool
    misuse: bool
    notes: Optional[str] = None


class FactMetrics(BaseModel):
    """FACT-UG 指标."""

    total_pairs: int
    supported_pairs: int
    authoritative_pairs: int
    timely_pairs: int
    misuse_pairs: int
    citation_accuracy: float
    effective_citations: int
    source_authority_ratio: float
    timeliness_ratio: float
    misuse_rate: float
    pairs: List[FactPairResult]


class TaskMetricScore(BaseModel):
    """任务专属指标得分."""

    metric: str
    value: float
    normalized: float
    description: Optional[str] = None
    reference_value: Optional[float] = None
    direction: str = "higher_is_better"


class ConfidenceInterval(BaseModel):
    """95% 置信区间."""

    lower: float
    upper: float


class DomainScore(BaseModel):
    """按主题域聚合的得分."""

    domain: str
    task_count: int
    race: float
    citation_accuracy: float
    effective_citations_norm: float
    task_metrics_norm: float
    overall: float


class UrbanGovEvalPerTaskResult(BaseModel):
    """每题落地剧本."""

    model_name: str
    task_id: str
    generated_at: datetime
    normalization_method: str
    race: RaceResult
    criteria: List[CriterionScore]
    fact: FactMetrics
    task_metrics: List[TaskMetricScore]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UrbanGovEvalSummary(BaseModel):
    """模型总体评估摘要."""

    model_name: str
    generated_at: datetime
    normalization_method: str
    task_count: int
    race_score: float
    citation_accuracy: float
    effective_citations_norm: float
    task_metrics_norm: float
    overall_score: float
    race_ci: ConfidenceInterval
    citation_accuracy_ci: ConfidenceInterval
    overall_ci: ConfidenceInterval
    metrics: Dict[str, Any]
    domain_breakdown: List[DomainScore]
    references: Dict[str, Any] = Field(default_factory=dict)

