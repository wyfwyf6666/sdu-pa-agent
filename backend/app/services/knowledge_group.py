from pathlib import Path
from typing import Dict, List, Any, Optional
import json
import uuid
from datetime import datetime, timezone
import shutil
import logging

logger = logging.getLogger(__name__)

class KnowledgeGroupService:
    """知识组管理服务"""

    def __init__(self):
        root_dir = Path(__file__).resolve().parents[3]
        self.private_root = root_dir / "backend" / "data" / "private"
        self.metadata_file = self.private_root / "metadata.json"
        self._ensure_structure()

    def _ensure_structure(self):
        """确保私人库目录结构存在"""
        self.private_root.mkdir(parents=True, exist_ok=True)
        if not self.metadata_file.exists():
            self._save_metadata({
                "library_type": "private",
                "knowledge_groups": {},
                "documents": {}
            })

    def _load_metadata(self) -> Dict[str, Any]:
        """加载私人库元数据"""
        with open(self.metadata_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_metadata(self, data: Dict[str, Any]):
        """保存私人库元数据"""
        with open(self.metadata_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _persist_group_paths(
        self,
        group_id: str,
        storage_path: Optional[str] = None,
        vector_path: Optional[str] = None
    ):
        """当检测到新的本地路径时，及时回写metadata"""
        if not storage_path and not vector_path:
            return
        metadata = self._load_metadata()
        group = metadata.get("knowledge_groups", {}).get(group_id)
        if not group:
            return

        updated = False
        if storage_path and group.get("storage_path") != storage_path:
            group["storage_path"] = storage_path
            updated = True
        if vector_path and group.get("vector_path") != vector_path:
            group["vector_path"] = vector_path
            updated = True

        if updated:
            metadata["knowledge_groups"][group_id] = group
            self._save_metadata(metadata)

    def _resolve_docs_path(self, group: Dict[str, Any]) -> Path:
        """
        解析知识组的 documents 目录，兼容不同机器的绝对路径。
        优先使用当前仓库下的实际目录，其次尝试 metadata 中的 storage_path。
        """
        group_id = group.get("id")
        if not group_id:
            raise ValueError("知识组缺少有效的ID")

        default_path = self.private_root / group_id / "documents"
        storage_path = group.get("storage_path")

        candidates: List[Path] = []
        if storage_path:
            candidates.append(Path(storage_path))
        candidates.append(default_path)

        for candidate in candidates:
            path_obj = candidate.expanduser()
            if not path_obj.is_absolute():
                path_obj = (self.private_root / path_obj).resolve()
            if path_obj.exists():
                if str(path_obj) != group.get("storage_path"):
                    self._persist_group_paths(group_id, storage_path=str(path_obj))
                    group["storage_path"] = str(path_obj)
                return path_obj

        # 如果都不存在，创建默认目录并回写
        default_path.mkdir(parents=True, exist_ok=True)
        self._persist_group_paths(group_id, storage_path=str(default_path))
        group["storage_path"] = str(default_path)
        return default_path

    def create_group(self, name: str, description: str = "", user_id: str = None) -> Dict[str, Any]:
        """创建知识组"""
        metadata = self._load_metadata()

        # 生成唯一ID
        group_id = f"kg_{uuid.uuid4().hex[:8]}"

        # 创建物理目录
        group_path = self.private_root / group_id
        docs_path = group_path / "documents"
        vectors_path = group_path / "vectors"

        docs_path.mkdir(parents=True, exist_ok=True)
        vectors_path.mkdir(parents=True, exist_ok=True)

        # 保存元数据
        now = datetime.now(timezone.utc).isoformat()
        group_info = {
            "id": group_id,
            "name": name,
            "description": description,
            "created_time": now,
            "updated_time": now,
            "document_count": 0,
            "storage_path": str(docs_path),
            "vector_path": str(vectors_path),
            "user_id": user_id  # 保存创建者的用户ID
        }

        metadata["knowledge_groups"][group_id] = group_info
        self._save_metadata(metadata)

        return group_info

    def list_groups(self, user_id: str = None, user_role: str = None) -> List[Dict[str, Any]]:
        """列出知识组

        Args:
            user_id: 用户ID
            user_role: 用户角色 (admin/user)

        Returns:
            知识组列表。管理员返回所有知识组，普通用户只返回自己的知识组
        """
        metadata = self._load_metadata()
        groups = list(metadata.get("knowledge_groups", {}).values())

        # 如果是管理员，返回所有知识组
        if user_role == "admin":
            groups.sort(key=lambda x: x.get("created_time", ""), reverse=True)
            return groups

        # 如果是普通用户，只返回自己的知识组
        if user_id:
            groups = [g for g in groups if g.get("user_id") == user_id]

        groups.sort(key=lambda x: x.get("created_time", ""), reverse=True)
        return groups

    def get_group(self, group_id: str) -> Optional[Dict[str, Any]]:
        """获取单个知识组"""
        metadata = self._load_metadata()
        return metadata.get("knowledge_groups", {}).get(group_id)

    def check_group_access(self, group_id: str, user_id: str, user_role: str) -> bool:
        """检查用户是否有权限访问知识组

        Args:
            group_id: 知识组ID
            user_id: 用户ID
            user_role: 用户角色 (admin/user)

        Returns:
            True 如果用户有权限访问，False 否则
        """
        # 管理员可以访问所有知识组
        if user_role == "admin":
            return True

        # 普通用户只能访问自己的知识组
        group = self.get_group(group_id)
        if not group:
            return False

        return group.get("user_id") == user_id

    def update_group(self, group_id: str, name: Optional[str], description: Optional[str]) -> Dict[str, Any]:
        """更新知识组信息"""
        metadata = self._load_metadata()
        group = metadata["knowledge_groups"].get(group_id)

        if not group:
            raise ValueError(f"知识组 {group_id} 不存在")

        if name is not None:
            group["name"] = name
        if description is not None:
            group["description"] = description

        group["updated_time"] = datetime.now(timezone.utc).isoformat()
        self._save_metadata(metadata)

        return group

    def delete_group(self, group_id: str, force: bool = False) -> Dict[str, Any]:
        """删除知识组"""
        metadata = self._load_metadata()
        group = metadata["knowledge_groups"].get(group_id)

        if not group:
            raise ValueError(f"知识组 {group_id} 不存在")

        # 检查是否包含文档
        group_docs = [
            doc for doc in metadata.get("documents", {}).values()
            if doc.get("knowledge_group_id") == group_id
        ]

        if group_docs and not force:
            raise ValueError(f"知识组包含 {len(group_docs)} 个文档，无法删除。使用 force=true 强制删除。")

        # 删除文档记录
        for doc in group_docs:
            metadata["documents"].pop(doc["filename"], None)

        # 删除物理目录
        group_path = self.private_root / group_id
        if group_path.exists():
            shutil.rmtree(group_path)

        # 删除元数据
        metadata["knowledge_groups"].pop(group_id)
        self._save_metadata(metadata)

        return {"deleted": True, "deleted_documents": len(group_docs)}

    def get_group_document_count(self, group_id: str) -> int:
        """获取知识组的文档数量"""
        metadata = self._load_metadata()
        count = sum(
            1 for doc in metadata.get("documents", {}).values()
            if doc.get("knowledge_group_id") == group_id
        )
        return count

    def update_group_document_count(self, group_id: str):
        """更新知识组的文档计数"""
        metadata = self._load_metadata()
        if group_id in metadata.get("knowledge_groups", {}):
            count = self.get_group_document_count(group_id)
            metadata["knowledge_groups"][group_id]["document_count"] = count
            metadata["knowledge_groups"][group_id]["updated_time"] = datetime.now(timezone.utc).isoformat()
            self._save_metadata(metadata)

    def get_group_data_files(self, group_id: str) -> List[Dict[str, Any]]:
        """获取知识组中的数据文件(csv/excel)

        Args:
            group_id: 知识组ID

        Returns:
            数据文件列表,每个文件包含filename, file_type, file_path等信息
        """
        group = self.get_group(group_id)
        if not group:
            raise ValueError(f"知识组 {group_id} 不存在")

        # 扫描documents目录
        docs_path = self._resolve_docs_path(group)
        data_files = []

        # 支持的数据文件扩展名
        data_extensions = {".csv", ".xlsx", ".xls", ".json"}

        for file_path in docs_path.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in data_extensions:
                data_files.append({
                    "filename": file_path.name,
                    "file_type": file_path.suffix.lower(),
                    "file_path": str(file_path),
                    "file_size": file_path.stat().st_size
                })

        return data_files

    def validate_group_for_data_analysis(self, group_id: str) -> Dict[str, Any]:
        """验证知识组是否适用于数据分析。

        规则：
        1) 必须至少包含1个数据文件(csv/excel/json)
        2) 可以包含其他类型的文件（如PDF、DOCX等），不影响数据分析
        """
        try:
            group = self.get_group(group_id)
            if not group:
                raise ValueError(f"知识组 {group_id} 不存在")

            docs_path = self._resolve_docs_path(group)
            data_extensions = {".csv", ".xlsx", ".xls", ".json"}
            data_files: List[Dict[str, Any]] = []

            for file_path in docs_path.iterdir():
                if not file_path.is_file():
                    continue
                suffix = file_path.suffix.lower()
                if suffix in data_extensions:
                    data_files.append({
                        "filename": file_path.name,
                        "file_type": suffix,
                        "file_path": str(file_path),
                        "file_size": file_path.stat().st_size
                    })

            if not data_files:
                return {
                    "valid": False,
                    "data_files": [],
                    "message": "该知识组不包含任何可用于分析的数据文件（CSV/Excel/JSON）"
                }

            return {
                "valid": True,
                "data_files": data_files,
                "message": f"找到 {len(data_files)} 个数据文件"
            }
        except Exception as exc:
            logger.error(f"验证知识组失败: {exc}")
            return {
                "valid": False,
                "data_files": [],
                "message": f"验证知识组时发生错误: {str(exc)}"
            }

    def get_all_groups(self) -> List[Dict[str, Any]]:
        """获取所有知识组。"""
        return list(self.groups.values())

# 创建全局实例
knowledge_group_service = KnowledgeGroupService()
