from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

ModuleKey = Literal[
    "references", "depth", "language", "literature",
    "reviewers", "journals", "comparison", "translation",
    "format", "data_methods",
]

DocumentType = Literal[
    "选题报告", "课程论文", "实训报告", "毕业论文",
    "投稿论文", "开题报告", "摘要初稿", "其他",
]


class PreReviewRequest(BaseModel):
    title: str = ""
    manuscript: str
    modules: Optional[List[ModuleKey]] = None
    target_journal: Optional[str] = None
    target_journal_text: Optional[str] = None


class OverallAssessment(BaseModel):
    document_type: str = ""
    completion_level: str = ""
    overall_score: int = 0
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    priority: str = ""


class MainIssue(BaseModel):
    severity: str = ""
    description: str = ""
    reason: str = ""


class Annotation(BaseModel):
    """带原文证据的逐条审阅意见（两栏联动核心数据）。"""
    id: int = 0
    module: str = ""           # 模块 key: depth/language/references/format/data_methods
    module_name: str = ""      # 模块中文名
    severity: str = ""         # 严重 / 一般 / 建议
    paragraph: int = -1        # 段落编号（1-based），-1 表示未能定位
    quote: str = ""            # 原文逐字摘录
    quote_matched: bool = True # 摘录是否在原文中校验通过
    issue: str = ""            # 针对摘录的具体问题分析
    suggestion: str = ""       # 针对该处的具体修改建议
    page: Optional[int] = None  # 原文 PDF 页码（1-based），仅 PDF 上传时有值
    bbox: Optional[List[float]] = None  # 原文 PDF 中的高亮坐标 [x0,y0,x1,y1]（PDF 坐标系，原点左上）


class ReferenceCheck(BaseModel):
    label: str
    status: str
    detail: str


class DimensionalScore(BaseModel):
    label: str
    score: int
    note: str


class ModuleResult(BaseModel):
    module_key: str
    module_name: str
    summary: str = ""
    items: List[Dict[str, Any]] = Field(default_factory=list)


class ChecklistItem(BaseModel):
    priority: str = ""
    category: str = ""
    action: str = ""
    detail: str = ""


class RiskWarning(BaseModel):
    risk_type: str = ""
    severity: str = ""
    description: str = ""
    suggestion: str = ""


class RewriteExample(BaseModel):
    section: str = ""
    original: str = ""
    rewritten: str = ""
    notes: str = ""


class PreReviewResponse(BaseModel):
    request_id: str
    title: str
    document_type: str
    raw_text: str = ""
    paragraphs: List[str] = Field(default_factory=list)
    overall_assessment: OverallAssessment
    main_issues: List[MainIssue] = Field(default_factory=list)
    annotations: List[Annotation] = Field(default_factory=list)
    module_results: List[ModuleResult] = Field(default_factory=list)
    modification_checklist: List[ChecklistItem] = Field(default_factory=list)
    risk_warnings: List[RiskWarning] = Field(default_factory=list)
    rewrite_examples: List[RewriteExample] = Field(default_factory=list)
    created_at: str = ""
    pdf_url: str = ""  # 原始 PDF 访问地址（仅 PDF 上传时非空，前端据此做原页+荧光笔）
