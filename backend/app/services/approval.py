from typing import Any, List, Optional, Dict
from datetime import datetime
import json
from pathlib import Path
from backend.app.models.approval import (
    Approval,
    ApprovalCreate,
    ApprovalAction,
    ApprovalStatus,
    ApprovalStep,
    ApprovalComment,
    ApprovalFile
)

class ApprovalService:
    def __init__(self):
        # 使用本地路径
        root_dir = Path(__file__).resolve().parents[3]
        self.data_dir = root_dir / "backend" / "data"
        self.approvals_file = self.data_dir / "approvals.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 加载已有的审批数据
        self.approvals: Dict[int, Approval] = {}
        self._load_data()
        
        self._next_id = max(self.approvals.keys(), default=0) + 1

    def _load_data(self):
        """加载审批数据，同时兼容旧版 files 数组缺少 file_size 或 path 字段"""
        if self.approvals_file.exists():
            with open(self.approvals_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                for item in raw_data:
                    # 1. 转换 submit_time
                    item["submit_time"] = datetime.fromisoformat(item["submit_time"])

                    # 2. 转换每个步骤里的 approve_time
                    for step in item["steps"]:
                        if step.get("approve_time"):
                            step["approve_time"] = datetime.fromisoformat(step["approve_time"])

                    # 3. 转换每个评论里的 create_time
                    for comment in item["comments"]:
                        comment["create_time"] = datetime.fromisoformat(comment["create_time"])

                    # 4. 兼容“文件”数组：确保每个 file 都有 upload_time、file_size、path
                    for file in item["files"]:
                        # 把 upload_time 从字符串转成 datetime
                        if file.get("upload_time"):
                            file["upload_time"] = datetime.fromisoformat(file["upload_time"])
                        # 如果旧数据里缺 file_size，就补成 0
                        if "file_size" not in file:
                            file["file_size"] = 0
                        # 如果旧数据里缺 path，就补成 None
                        if "path" not in file:
                            file["path"] = None

                    # 最后，用 Pydantic 把它们转换成 Approval 对象
                    approval = Approval(**item)
                    self.approvals[approval.id] = approval


    def _save_data(self):
        """保存审批数据到 JSON，同时把 datetime 转为字符串"""
        data_to_dump: List[Dict[str, Any]] = []
        for approval in self.approvals.values():
            d = approval.dict()
            # 转换 submit_time
            d["submit_time"] = d["submit_time"].isoformat()
            # 转换每个步骤
            for step in d["steps"]:
                if step.get("approve_time"):
                    step["approve_time"] = step["approve_time"].isoformat()
            # 转换每个评论
            for comment in d["comments"]:
                comment["create_time"] = comment["create_time"].isoformat()
            # 转换每个文件
            for file in d["files"]:
                file["upload_time"] = file["upload_time"].isoformat()
                # path 本身是字符串或 None，无需转换
            data_to_dump.append(d)

        with open(self.approvals_file, "w", encoding="utf-8") as f:
            json.dump(data_to_dump, f, ensure_ascii=False, indent=2)

    async def create_approval(self, data: ApprovalCreate, applicant: str, department: str) -> Approval:
        """创建新的审批申请"""
        # 创建审批步骤
        steps = [
            ApprovalStep(
                step_id=i + 1,
                name=f"第{i + 1}步审批",
                approver=approver
            )
            for i, approver in enumerate(data.steps)
        ]
        
        # 创建审批
        approval = Approval(
            id=self._next_id,
            title=data.title,
            type=data.type,
            content=data.content,
            applicant=applicant,
            department=department,
            urgency=data.urgency,
            steps=steps
        )
        
        # 保存审批
        self.approvals[approval.id] = approval
        self._next_id += 1
        self._save_data()
        
        return approval

    async def get_approval(self, approval_id: int) -> Optional[Approval]:
        """获取审批详情"""
        return self.approvals.get(approval_id)

    async def list_approvals(
        self,
        status: Optional[str] = None,
        department: Optional[str] = None,
        applicant: Optional[str] = None
    ) -> List[Approval]:
        """获取审批列表"""
        approvals = list(self.approvals.values())
        
        # 过滤
        if status:
            approvals = [a for a in approvals if a.status == status]
        if department:
            approvals = [a for a in approvals if a.department == department]
        if applicant:
            approvals = [a for a in approvals if a.applicant == applicant]
            
        # 按提交时间倒序排序
        approvals.sort(key=lambda x: x.submit_time, reverse=True)
        return approvals

    async def process_approval(
        self,
        approval_id: int,
        action: ApprovalAction,
        processor: str
    ) -> Optional[Approval]:
        """处理审批"""
        approval = self.approvals.get(approval_id)
        if not approval:
            return None
            
        # 获取当前步骤
        current_step = approval.steps[approval.current_step - 1]
        
        # 检查处理人是否匹配
        # if current_step.approver != processor:
        #     raise ValueError("您不是当前步骤的审批人")
            
        # 处理审批
        if action.action == "approve":
            # 通过当前步骤
            current_step.status = ApprovalStatus.APPROVED
            current_step.comment = action.comment
            current_step.approve_time = datetime.now()
            
            # 如果还有下一步
            if approval.current_step < len(approval.steps):
                approval.current_step += 1
            else:
                # 完成审批
                approval.status = ApprovalStatus.APPROVED
                
        elif action.action == "reject":
            # 拒绝审批
            current_step.status = ApprovalStatus.REJECTED
            current_step.comment = action.comment
            current_step.approve_time = datetime.now()
            approval.status = ApprovalStatus.REJECTED
            
        elif action.action == "transfer":
            # 转交审批
            if not action.transfer_to:
                raise ValueError("未指定转交目标")
            current_step.approver = action.transfer_to
            
        # 添加评论
        if action.comment:
            comment = ApprovalComment(
                comment_id=len(approval.comments) + 1,
                user=processor,
                content=action.comment
            )
            approval.comments.append(comment)
            
        self._save_data()
        return approval

    async def add_approval_file(
        self,
        approval_id: int,
        filename: str,
        file_type: str,
        file_size: int,
        path: Optional[str] = None
    ) -> Optional[ApprovalFile]:
        """添加审批附件：把文件元数据（包含 path）保存到 JSON"""
        approval = self.approvals.get(approval_id)
        if not approval:
            return None
        
        # 构造 Pydantic 模型
        file_obj = ApprovalFile(
            file_id=len(approval.files) + 1,
            filename=filename,
            file_type=file_type,
            upload_time=datetime.now(),
            path=path
        )
        approval.files.append(file_obj)
        self._save_data()
        return file_obj

    async def get_approval_statistics(
        self,
        department: Optional[str] = None
    ) -> Dict[str, int]:
        """获取审批统计信息"""
        approvals = await self.list_approvals(department=department)
        
        stats = {
            "total": len(approvals),
            "pending": len([a for a in approvals if a.status == ApprovalStatus.PENDING]),
            "approved": len([a for a in approvals if a.status == ApprovalStatus.APPROVED]),
            "rejected": len([a for a in approvals if a.status == ApprovalStatus.REJECTED])
        }
        
        return stats

# 创建审批服务实例
approval_service = ApprovalService() 
