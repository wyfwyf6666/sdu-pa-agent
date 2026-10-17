from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

class ApprovalStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class UrgencyLevel:
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"

class ApprovalType:
    MEETING = "meeting"      # 会议申请
    BUDGET = "budget"       # 预算申请
    PURCHASE = "purchase"   # 采购申请
    LEAVE = "leave"        # 请假申请
    OTHER = "other"        # 其他

class ApprovalStep(BaseModel):
    """审批步骤"""
    step_id: int
    name: str
    approver: str
    status: str = ApprovalStatus.PENDING
    comment: Optional[str] = None
    approve_time: Optional[datetime] = None

class ApprovalComment(BaseModel):
    """审批评论"""
    comment_id: int
    user: str
    content: str
    create_time: datetime = datetime.now()

class ApprovalFile(BaseModel):
    """审批附件"""
    file_id: int
    filename: str
    file_type: str
    file_size: int
    upload_time: datetime = datetime.now()

class Approval(BaseModel):
    """审批申请"""
    id: int
    title: str
    type: str
    content: str
    applicant: str
    department: str
    submit_time: datetime = datetime.now()
    status: str = ApprovalStatus.PENDING
    urgency: str = UrgencyLevel.NORMAL
    current_step: int = 1
    steps: List[ApprovalStep]
    comments: List[ApprovalComment] = []
    files: List[ApprovalFile] = []

class ApprovalCreate(BaseModel):
    """创建审批的请求模型"""
    title: str
    type: str
    content: str
    urgency: str = UrgencyLevel.NORMAL
    steps: List[str]  # 审批人列表

class ApprovalAction(BaseModel):
    """审批操作的请求模型"""
    action: str  # approve/reject/transfer
    comment: Optional[str] = None
    transfer_to: Optional[str] = None  # 转交目标 