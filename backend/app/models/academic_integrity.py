"""学术诚信与证据可靠性检测 - Pydantic模型定义"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# 枚举定义
# =============================================================================

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReferenceStatus(str, Enum):
    VERIFIED = "verified"
    LIKELY_REAL = "likely_real"
    LIKELY_REAL_WITH_MISMATCH = "likely_real_with_mismatch"
    NOT_FOUND = "not_found"
    SUSPICIOUS = "suspicious"
    INSUFFICIENT_OPEN_METADATA = "insufficient_open_metadata"
    PARSE_FAILED = "parse_failed"


class SourceType(str, Enum):
    OFFICIAL_GOVERNMENT = "official_government"
    STATISTICAL_YEARBOOK = "statistical_yearbook"
    ACADEMIC_DATABASE = "academic_database"
    SURVEY = "survey"
    INTERVIEW = "interview"
    WEB_CRAWLING = "web_crawling"
    PLATFORM_DATA = "platform_data"
    ENTERPRISE_REPORT = "enterprise_report"
    MEDIA_REPORT = "media_report"
    POLICY_TEXT = "policy_text"
    UNKNOWN = "unknown"


# =============================================================================
# 请求模型
# =============================================================================

class CheckOptions(BaseModel):
    check_plagiarism: bool = True
    check_references: bool = True
    check_data_sources: bool = True
    use_web_search: bool = True
    use_local_knowledge_base: bool = True
    use_external_academic_apis: bool = True
    language: str = "zh-CN"


class AcademicIntegrityAnalyzeRequest(BaseModel):
    document_id: Optional[str] = None
    text: Optional[str] = None
    title: str = ""
    discipline: str = ""
    options: CheckOptions = Field(default_factory=CheckOptions)


class PlagiarismRequest(BaseModel):
    text: str
    title: str = ""
    use_web_search: bool = True
    use_local_knowledge_base: bool = True


class ReferenceCheckRequest(BaseModel):
    text: str
    use_external_apis: bool = True


class DataSourceRequest(BaseModel):
    text: str
    use_web_search: bool = True


# =============================================================================
# 响应模型 — 通用
# =============================================================================

class TaskCreateResponse(BaseModel):
    task_id: str
    status: TaskStatus
    message: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    progress: float = 0.0
    current_step: str = ""
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


DISCLAIMER_TEXT = (
    "本功能用于论文正式投稿前的风险预审，结果仅供修改参考，"
    "不能替代知网、维普、万方、Turnitin等正式查重系统，也不能替代人工学术审查。"
)


# =============================================================================
# 响应模型 — 相似度检测
# =============================================================================

class MatchedSource(BaseModel):
    title: str = ""
    url: str = ""
    source_type: str = ""  # web / local_knowledge_base
    similarity: float = 0.0
    snippet: str = ""


class PlagiarismSegmentResult(BaseModel):
    index: int
    text: str = ""
    start_char: int = 0
    end_char: int = 0
    similarity_score: float = 0.0
    risk_level: str = ""
    matched_sources: List[MatchedSource] = Field(default_factory=list)
    reason: str = ""
    suggestion: str = ""


class PlagiarismResultData(BaseModel):
    total_similarity: float = 0.0
    local_similarity: float = 0.0
    web_similarity: float = 0.0
    risk_level: str = ""
    summary: str = ""
    segments: List[PlagiarismSegmentResult] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER_TEXT


# =============================================================================
# 响应模型 — 参考文献校验
# =============================================================================

class ParsedReference(BaseModel):
    title: str = ""
    authors: List[str] = Field(default_factory=list)
    year: Optional[int] = None
    journal: str = ""
    doi: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    url: str = ""


class MatchedApiSource(BaseModel):
    provider: str = ""
    matched_title: str = ""
    matched_doi: str = ""
    matched_authors: List[str] = Field(default_factory=list)
    matched_year: Optional[int] = None
    url: str = ""
    score: float = 0.0
    raw: Dict[str, Any] = Field(default_factory=dict)


class ReferenceCheckItem(BaseModel):
    index: int
    raw_reference: str = ""
    parsed: ParsedReference = Field(default_factory=ParsedReference)
    status: ReferenceStatus = ReferenceStatus.PARSE_FAILED
    confidence: float = 0.0
    matched_sources: List[MatchedApiSource] = Field(default_factory=list)
    mismatch_fields: List[str] = Field(default_factory=list)
    risk_reason: str = ""
    suggestion: str = ""


class ReferenceResultData(BaseModel):
    total_references: int = 0
    verified_count: int = 0
    suspicious_count: int = 0
    not_found_count: int = 0
    risk_level: str = ""
    summary: str = ""
    items: List[ReferenceCheckItem] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER_TEXT


# =============================================================================
# 响应模型 — 数据来源分析
# =============================================================================

class DataSourceScores(BaseModel):
    authority: float = 0.0
    traceability: float = 0.0
    timeliness: float = 0.0
    completeness: float = 0.0
    ethics: float = 0.0
    method_match: float = 0.0
    total: float = 0.0


class DataSourceItem(BaseModel):
    index: int
    source_text: str = ""
    source_type: str = ""
    source_name: str = ""
    source_url: Optional[str] = None
    scores: DataSourceScores = Field(default_factory=DataSourceScores)
    risk_level: str = ""
    evidence: List[str] = Field(default_factory=list)
    risk_reason: str = ""
    suggestion: str = ""


class DataSourceResultData(BaseModel):
    total_sources: int = 0
    average_score: float = 0.0
    risk_level: str = ""
    summary: str = ""
    items: List[DataSourceItem] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER_TEXT


# =============================================================================
# 综合结果
# =============================================================================

class PriorityFix(BaseModel):
    priority: str = ""
    module: str = ""
    issue: str = ""
    action: str = ""


class AcademicIntegrityResult(BaseModel):
    overall_score: float = 0.0
    overall_risk_level: str = ""
    summary: str = ""
    key_findings: List[str] = Field(default_factory=list)
    plagiarism: Optional[PlagiarismResultData] = None
    references: Optional[ReferenceResultData] = None
    data_sources: Optional[DataSourceResultData] = None
    priority_fixes: List[PriorityFix] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER_TEXT


# =============================================================================
# 任务存储模型（内存中）
# =============================================================================

class AcademicIntegrityTask:
    def __init__(self, task_id: str, user_id: str, title: str = ""):
        self.id = task_id
        self.user_id = user_id
        self.title = title
        self.status = TaskStatus.PENDING
        self.progress: float = 0.0
        self.current_step: str = ""
        self.result: Optional[Dict[str, Any]] = None
        self.error_message: Optional[str] = None
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.completed_at: Optional[datetime] = None
