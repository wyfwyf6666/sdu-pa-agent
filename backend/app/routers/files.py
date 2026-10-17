from __future__ import annotations

import json
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from io import BytesIO
import zipfile
import hashlib
import re
import asyncio
import logging

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, Depends
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from backend.app.services.document import document_service
from backend.app.services.tagging import tagging_service
from backend.app.dependencies.auth import get_current_admin_user, get_optional_user
from backend.app.models.user import User

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量配置
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[3]

# Windows中文路径兼容：FAISS C++库无法处理中文路径，使用ASCII junction
_ASCII_DATA = Path("C:/city_research_data")
if _ASCII_DATA.exists():
    PUBLIC_UPLOAD_DIR = _ASCII_DATA / "public" / "documents"
    PUBLIC_METADATA_FILE = _ASCII_DATA / "public" / "metadata.json"
    PRIVATE_ROOT = _ASCII_DATA / "private"
    PRIVATE_METADATA_FILE = PRIVATE_ROOT / "metadata.json"
else:
    PUBLIC_UPLOAD_DIR = ROOT_DIR / "backend" / "data" / "public" / "documents"
    PUBLIC_METADATA_FILE = ROOT_DIR / "backend" / "data" / "public" / "metadata.json"
    PRIVATE_ROOT = ROOT_DIR / "backend" / "data" / "private"
    PRIVATE_METADATA_FILE = PRIVATE_ROOT / "metadata.json"

# 兼容旧代码：默认使用公共库路径
UPLOAD_DIR = PUBLIC_UPLOAD_DIR
METADATA_FILE = PUBLIC_METADATA_FILE

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv", ".xlsx", ".xls", ".json"}
ALLOWED_CATEGORIES = {"论文", "案例", "政策", "数据"}
DEFAULT_CATEGORY = "论文"

PUBLIC_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PUBLIC_METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def get_metadata_file(library_type: str = "public") -> Path:
    """根据库类型获取metadata文件路径"""
    if library_type == "public":
        return PUBLIC_METADATA_FILE
    elif library_type == "private":
        return PRIVATE_METADATA_FILE
    else:
        return PUBLIC_METADATA_FILE  # 默认公共库


def get_upload_dir(library_type: str = "public", knowledge_group_id: Optional[str] = None) -> Path:
    """根据库类型和知识组ID获取上传目录"""
    if library_type == "public":
        return PUBLIC_UPLOAD_DIR
    elif library_type == "private" and knowledge_group_id:
        upload_dir = PRIVATE_ROOT / knowledge_group_id / "documents"
        upload_dir.mkdir(parents=True, exist_ok=True)
        return upload_dir
    else:
        raise ValueError("私人库必须指定knowledge_group_id")


def load_metadata(library_type: str = "public") -> Dict[str, Dict[str, Any]]:
    """
    加载metadata，支持公共库和私人库

    Args:
        library_type: "public" 或 "private"

    Returns:
        如果是公共库，返回 {filename: doc_info}
        如果是私人库，返回 metadata.documents 部分
    """
    metadata_file = get_metadata_file(library_type)

    if metadata_file.exists():
        with open(metadata_file, "r", encoding="utf-8") as file:
            data = json.load(file)

            # 私人库的metadata结构包含knowledge_groups和documents
            if library_type == "private":
                documents = data.get("documents", {})
            else:
                # 公共库的metadata可能是旧格式（直接是文档字典）或新格式
                if "documents" in data:
                    documents = data["documents"]
                else:
                    documents = data  # 兼容旧格式

            # 设置默认值
            for doc in documents.values():
                doc.setdefault("tags", [])
                doc.setdefault("category", DEFAULT_CATEGORY)
                doc.setdefault("title", doc.get("filename", "未命名文档"))
                doc.setdefault("library_type", library_type)

            return documents
    return {}


def save_metadata(metadata: Dict[str, Dict[str, Any]], library_type: str = "public") -> None:
    """
    保存metadata

    Args:
        metadata: 文档字典 {filename: doc_info}
        library_type: "public" 或 "private"
    """
    metadata_file = get_metadata_file(library_type)

    if library_type == "private":
        # 私人库需要保留knowledge_groups信息
        if metadata_file.exists():
            with open(metadata_file, "r", encoding="utf-8") as f:
                full_data = json.load(f)
        else:
            full_data = {
                "library_type": "private",
                "knowledge_groups": {},
                "documents": {}
            }

        full_data["documents"] = metadata

        with open(metadata_file, "w", encoding="utf-8") as file:
            json.dump(full_data, file, ensure_ascii=False, indent=2)
    else:
        # 公共库使用新格式
        full_data = {
            "library_type": "public",
            "documents": metadata
        }

        with open(metadata_file, "w", encoding="utf-8") as file:
            json.dump(full_data, file, ensure_ascii=False, indent=2)


def collect_existing_tags(
    metadata: Dict[str, Dict[str, Any]],
    *,
    exclude_filename: Optional[str] = None,
) -> List[str]:
    unique: List[str] = []
    seen = set()
    for name, doc in metadata.items():
        if exclude_filename and name == exclude_filename:
            continue
        for tag in doc.get("tags", []) or []:
            tag_str = str(tag).strip()
            if not tag_str:
                continue
            lowered = tag_str.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            unique.append(tag_str)
    return unique


def parse_metadata_payload(metadata_json: Optional[str]) -> Dict[str, Dict[str, Any]]:
    if not metadata_json:
        return {}
    try:
        payload = json.loads(metadata_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"metadata 解析失败: {exc}") from exc

    result: Dict[str, Dict[str, Any]] = {}

    if isinstance(payload, list):
        iterable: Iterable[Any] = payload
    elif isinstance(payload, dict):
        temp: List[Any] = []
        for key, value in payload.items():
            if isinstance(value, dict):
                value = {**value}
                value.setdefault("filename", key)
                temp.append(value)
        iterable = temp
    else:
        iterable = []

    for item in iterable:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or item.get("name") or "").strip()
        if not filename:
            continue
        result[filename] = item

    return result


def normalize_category(category: Optional[str]) -> str:
    if not category:
        return DEFAULT_CATEGORY
    category = str(category).strip()
    if category in ALLOWED_CATEGORIES:
        return category
    raise HTTPException(
        status_code=400,
        detail=f"分类 {category} 不被支持，仅允许: {', '.join(ALLOWED_CATEGORIES)}",
    )


def parse_tags_value(value: Any) -> List[str]:
    if isinstance(value, list):
        tags = [str(tag).strip() for tag in value if str(tag).strip()]
        return tags
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def sanitize_filename(name: str) -> str:
    return Path(name).name


def _fallback_vector_paths(filename: str) -> tuple[Path, Path]:
    stem = Path(filename).stem
    safe_chars = []
    for ch in stem:
        if ch.isascii() and (ch.isalnum() or ch in {"_", "-"}):
            safe_chars.append(ch)
        else:
            safe_chars.append("_")
    safe_stem = re.sub(r"_+", "_", "".join(safe_chars)).strip("_")
    if not safe_stem:
        safe_stem = hashlib.md5(stem.encode("utf-8"), usedforsecurity=False).hexdigest()
    base_path = document_service.vector_store_path
    return base_path / f"{safe_stem}.faiss", base_path / f"{safe_stem}.pkl"


def resolve_vector_paths(
    filename: str,
    library_type: str = "public",
    knowledge_group_id: Optional[str] = None
) -> tuple[Path, Path]:
    helper = getattr(document_service, "get_vector_paths_for_filename", None)
    if callable(helper):
        try:
            return helper(filename, library_type, knowledge_group_id)
        except Exception:
            pass
    return _fallback_vector_paths(filename)


def resolve_document_path(record: Dict[str, Any], library_type: Optional[str] = None) -> Path:
    """
    根据记录信息解析出真实文件路径，兼容不同环境产生的绝对路径。
    如果找到新的有效路径，会回写到记录中。
    """
    lib_type = (library_type or record.get("library_type") or "public").lower()
    raw_path = record.get("path")
    candidate_paths: List[Path] = []
    seen: set[str] = set()

    def add_candidate(path: Path | str) -> None:
        path_obj = Path(path).expanduser()
        if not path_obj.is_absolute():
            path_obj = (ROOT_DIR / path_obj).resolve()
        key = str(path_obj)
        if key not in seen:
            seen.add(key)
            candidate_paths.append(path_obj)

    if raw_path:
        add_candidate(raw_path)

    name_candidates: List[str] = []
    for key in ("filename", "title"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            name_candidates.append(value.strip())
    if raw_path:
        name_candidates.append(Path(raw_path).name)

    normalized_names: List[str] = []
    for name in name_candidates:
        for variant in {name, sanitize_filename(name)}:
            clean = variant.strip()
            if clean and clean not in normalized_names:
                normalized_names.append(clean)

    base_dirs: List[Path] = []
    if lib_type == "public":
        base_dirs.append(PUBLIC_UPLOAD_DIR)
    else:
        group_id = record.get("knowledge_group_id")
        if group_id:
            base_dirs.append(PRIVATE_ROOT / group_id / "documents")

    for base_dir in base_dirs:
        for filename in normalized_names:
            add_candidate(base_dir / filename)

    for candidate in candidate_paths:
        if candidate.exists():
            record["path"] = str(candidate)
            return candidate

    raise FileNotFoundError("文件内容不存在")


def resolve_document_records(
    metadata: Dict[str, Dict[str, Any]],
    filenames: Sequence[str],
    library_type: str = "public"
) -> Tuple[List[Dict[str, Any]], List[str]]:
    records: List[Dict[str, Any]] = []
    missing: List[str] = []
    for raw_name in filenames:
        filename = sanitize_filename(raw_name)
        record = metadata.get(filename)
        if not record:
            missing.append(filename)
            continue
        record_library_type = record.get("library_type", library_type)
        try:
            resolve_document_path(record, record_library_type)
        except FileNotFoundError:
            missing.append(filename)
            continue
        records.append(record)
    return records, missing


async def process_document_async(
    file_path: str,
    library_type: str = "public",
    knowledge_group_id: Optional[str] = None
) -> Dict[str, Any]:
    processor = getattr(document_service, "process_document", None)
    if processor:
        result = processor(file_path, library_type, knowledge_group_id)
        if hasattr(result, "__await__"):
            return await result
        return result
    # fallback to legacy sync processing
    return await run_in_threadpool(
        document_service._process_single_document,
        file_path,
        library_type,
        knowledge_group_id
    )


# ---------------------------------------------------------------------------
# 路由实现
# ---------------------------------------------------------------------------
@router.post("/documents/upload")
async def upload_documents(
    files: List[UploadFile] = File(None),
    file: Optional[UploadFile] = File(None),
    metadata_json: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    library_type: str = Form("public", description="库类型: public 或 private"),
    knowledge_group_id: Optional[str] = Form(None, description="知识组ID（私人库时必填）"),
    current_user: Optional[User] = Depends(get_optional_user),
) -> Dict[str, Any]:
    """
    上传知识库文档，支持批量上传、自动标签和分类设置。
    支持上传到公共库或指定知识组的私人库。

    **权限要求**：
    - 公共库上传：需要管理员权限
    - 私人库上传：需要登录
    """
    # 调试日志
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"上传请求 - library_type: {library_type}, knowledge_group_id: {knowledge_group_id}")
    logger.info(f"当前用户: {current_user.username if current_user else 'None'}, 角色: {current_user.role if current_user else 'None'}")

    # 权限检查：公共库需要登录
    if library_type == "public":
        if not current_user:
            raise HTTPException(
                status_code=403,
                detail="请先登录后上传文档"
            )
    # 私人库需要登录
    elif library_type == "private":
        if not current_user:
            logger.error("私人库上传失败：用户未登录")
            raise HTTPException(
                status_code=401,
                detail="请先登录后上传文档到私人库"
            )

    # 验证参数
    if library_type == "private" and not knowledge_group_id:
        raise HTTPException(status_code=400, detail="上传到私人库时必须指定knowledge_group_id")

    # 如果是私人库，验证用户是否有权限访问该知识组
    if library_type == "private" and knowledge_group_id:
        from backend.app.services.knowledge_group import knowledge_group_service
        if not knowledge_group_service.check_group_access(
            knowledge_group_id, current_user.user_id, current_user.role.value
        ):
            raise HTTPException(
                status_code=403,
                detail="无权上传文档到该知识组"
            )

    upload_files: List[UploadFile] = []
    if files:
        upload_files.extend(files)
    if file:
        upload_files.append(file)

    if not upload_files:
        raise HTTPException(status_code=400, detail="至少上传一个文件")

    # 获取正确的上传目录
    try:
        upload_dir = get_upload_dir(library_type, knowledge_group_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    metadata = load_metadata(library_type)
    metadata_payload = parse_metadata_payload(metadata_json)
    single_defaults = {
        "title": title,
        "category": category,
        "tags": tags,
    }

    existing_tags = set(collect_existing_tags(metadata))
    processed_entries: List[Dict[str, Any]] = []

    for upload in upload_files:
        original_filename = sanitize_filename(upload.filename or "")
        if not original_filename:
            raise HTTPException(status_code=400, detail="文件名无效")

        suffix = Path(original_filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型: {suffix}，仅支持 {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            )

        meta_info = metadata_payload.get(original_filename, {})
        if not meta_info:
            meta_info = {k: v for k, v in single_defaults.items() if v is not None}

        manual_tags = parse_tags_value(meta_info.get("tags"))
        auto_tag = bool(meta_info.get("autoTag", True))
        if manual_tags:
            auto_tag = False

        document_category = normalize_category(meta_info.get("category"))
        document_title = str(meta_info.get("title") or Path(original_filename).stem)

        content = await upload.read()
        file_path = upload_dir / original_filename
        with open(file_path, "wb") as dest:
            dest.write(content)

        document_record = {
            "filename": original_filename,
            "title": document_title,
            "size": len(content),
            "upload_time": datetime.now(timezone.utc).isoformat(),
            "category": document_category,
            "tags": manual_tags,
            "type": suffix.lstrip("."),
            "path": str(file_path),
            "processed": False,
            "library_type": library_type,  # 新增字段
            "knowledge_group_id": knowledge_group_id,  # 新增字段
        }

        # 如果是数据文件，提取元信息
        if suffix in {".csv", ".xlsx", ".xls", ".json"}:
            data_metadata = document_service.get_data_file_metadata(str(file_path))
            document_record["data_metadata"] = data_metadata

        metadata[original_filename] = document_record
        processed_entries.append(
            {
                "record": document_record,
                "auto_tag": auto_tag,
                "category": document_category,
                "manual_tags": manual_tags,
                "path": str(file_path),
            }
        )

        if manual_tags:
            existing_tags.update(manual_tags)

    save_metadata(metadata, library_type)

    # 向量化处理 - 传递library_type和knowledge_group_id
    for entry in processed_entries:
        await process_document_async(entry["path"], library_type, knowledge_group_id)
        entry["record"]["processed"] = True

    # 自动补全标签和分类特定字段
    for entry in processed_entries:
        record = entry["record"]
        if entry["auto_tag"]:
            preview_text = document_service.get_document_preview(entry["path"], max_chars=1500)
            # 使用新的extract_metadata方法一次性提取所有元数据
            metadata_result = await tagging_service.extract_metadata(
                preview_text,
                entry["category"],
                sorted(existing_tags),
            )
            record["tags"] = metadata_result.get("tags", [])
            existing_tags.update(record["tags"])

            # 存储分类特定字段
            category_fields = metadata_result.get("category_fields", {})
            if entry["category"] == "政策":
                record["effectiveness_level"] = category_fields.get("effectiveness_level", "")
                record["document_type"] = category_fields.get("document_type", "")
            elif entry["category"] == "论文":
                record["discipline"] = category_fields.get("discipline", "")
                record["main_topic"] = category_fields.get("main_topic", "")
            elif entry["category"] == "案例":
                record["region"] = category_fields.get("region", "")
                record["main_topic"] = category_fields.get("main_topic", "")
        else:
            # 手动填写时，保存用户填写的标签和分类字段
            record["tags"] = entry["manual_tags"]

            # 从meta_info中获取手动填写的分类特定字段
            meta_info = metadata_payload.get(record["filename"], {})
            if entry["category"] == "政策":
                record["effectiveness_level"] = str(meta_info.get("effectiveness_level", "")).strip()
                record["document_type"] = str(meta_info.get("document_type", "")).strip()
            elif entry["category"] == "论文":
                record["discipline"] = str(meta_info.get("discipline", "")).strip()
                record["main_topic"] = str(meta_info.get("main_topic", "")).strip()
            elif entry["category"] == "案例":
                record["region"] = str(meta_info.get("region", "")).strip()
                record["main_topic"] = str(meta_info.get("main_topic", "")).strip()

        record["updated_time"] = datetime.now(timezone.utc).isoformat()

    save_metadata(metadata, library_type)

    # 如果是私人库，更新知识组的文档计数
    if library_type == "private" and knowledge_group_id:
        from backend.app.services.knowledge_group import knowledge_group_service
        knowledge_group_service.update_group_document_count(knowledge_group_id)

    # 不再自动触发索引合并，检索时会同时检索合并索引和未合并的小索引
    # asyncio.create_task(
    #     run_in_threadpool(
    #         document_service.build_merged_index,
    #         library_type,
    #         knowledge_group_id
    #     )
    # )
    # logger.info("触发增量索引更新: library_type=%s, group_id=%s", library_type, knowledge_group_id)

    return {
        "status": "success",
        "message": "文件上传成功",
        "data": [entry["record"] for entry in processed_entries],
    }


@router.get("/documents")
async def list_documents(
    library_type: Optional[str] = Query(None, description="库类型: public 或 private"),
    knowledge_group_id: Optional[str] = Query(None, description="知识组ID（私人库时使用）"),
    category: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    current_user: Optional[User] = Depends(get_optional_user),
) -> Dict[str, Any]:
    """
    获取文档列表，支持分类、标签及标题检索。
    支持公共库和私人库过滤。
    """
    # 如果未指定library_type，默认返回公共库
    if library_type is None:
        library_type = "public"

    # 如果是私人库，需要验证权限
    if library_type == "private":
        if not current_user:
            raise HTTPException(
                status_code=401,
                detail="访问私人库需要登录"
            )

        # 如果指定了knowledge_group_id，验证用户是否有权限访问该知识组
        if knowledge_group_id:
            from backend.app.services.knowledge_group import knowledge_group_service
            if not knowledge_group_service.check_group_access(
                knowledge_group_id, current_user.user_id, current_user.role.value
            ):
                raise HTTPException(
                    status_code=403,
                    detail="无权访问该知识组"
                )

    metadata = load_metadata(library_type)
    documents = list(metadata.values())

    # 如果是私人库且指定了knowledge_group_id，进一步过滤
    if library_type == "private" and knowledge_group_id:
        documents = [
            doc for doc in documents
            if doc.get("knowledge_group_id") == knowledge_group_id
        ]

    if category:
        documents = [doc for doc in documents if doc.get("category") == category]
    if tag:
        documents = [doc for doc in documents if tag in (doc.get("tags") or [])]
    if search:
        documents = [
            doc for doc in documents if search.lower() in doc.get("title", "").lower()
        ]

    documents.sort(key=lambda doc: doc.get("upload_time", ""), reverse=True)

    return {"status": "success", "data": documents}


@router.get("/documents/categories")
async def get_categories(
    library_type: Optional[str] = Query("public", description="库类型: public 或 private"),
) -> Dict[str, Any]:
    """
    返回所有可用分类，始终包含默认分类。
    支持按库类型过滤。
    """
    metadata = load_metadata(library_type)
    categories = set(ALLOWED_CATEGORIES)
    categories.update(doc.get("category") for doc in metadata.values() if doc.get("category"))
    return {"status": "success", "data": sorted(categories)}


@router.get("/documents/tags")
async def get_tags(
    library_type: Optional[str] = Query("public", description="库类型: public 或 private"),
) -> Dict[str, Any]:
    """
    返回知识库中出现过的全部标签。
    支持按库类型过滤。
    """
    metadata = load_metadata(library_type)
    tags = collect_existing_tags(metadata)
    return {"status": "success", "data": tags}


@router.get("/documents/{filename}/preview")
async def preview_document(
    filename: str,
    max_chars: int = Query(800, ge=100, le=4000),
    library_type: Optional[str] = Query("public", description="库类型: public 或 private"),
) -> Dict[str, Any]:
    metadata = load_metadata(library_type)
    record = metadata.get(filename)
    if not record:
        raise HTTPException(status_code=404, detail="文件不存在")

    try:
        file_path = resolve_document_path(record, library_type)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件内容不存在")

    preview_text = document_service.get_document_preview(str(file_path), max_chars=max_chars)
    return {
        "status": "success",
        "data": {
            "filename": filename,
            "title": record.get("title"),
            "preview": preview_text,
        },
    }


@router.get("/documents/{filename}/download")
async def download_document(
    filename: str,
    library_type: Optional[str] = Query("public", description="库类型: public 或 private"),
) -> FileResponse:
    metadata = load_metadata(library_type)
    record = metadata.get(filename)
    if not record:
        raise HTTPException(status_code=404, detail="文件不存在")

    try:
        file_path = resolve_document_path(record, library_type)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件内容不存在")

    media_type, _ = mimetypes.guess_type(file_path.name)
    return FileResponse(
        path=file_path,
        media_type=media_type or "application/octet-stream",
        filename=record.get("filename", file_path.name),
    )


class DocumentUpdatePayload(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[Sequence[str]] = None
    regenerate_tags: Optional[bool] = False
    # 政策类字段
    effectiveness_level: Optional[str] = None
    document_type: Optional[str] = None
    # 论文类字段
    discipline: Optional[str] = None
    # 案例类字段
    region: Optional[str] = None
    # 论文和案例共有字段
    main_topic: Optional[str] = None


class BatchDocumentRequest(BaseModel):
    filenames: Sequence[str]

    @property
    def normalized(self) -> List[str]:
        return [sanitize_filename(name) for name in self.filenames if sanitize_filename(name)]


@router.put("/documents/{filename}")
async def update_document(
    filename: str,
    payload: DocumentUpdatePayload,
    library_type: Optional[str] = Query("public", description="库类型: public 或 private"),
    current_user: Optional[User] = Depends(get_optional_user),
) -> Dict[str, Any]:
    """
    更新文档信息

    **权限要求**：
    - 公共库：需要管理员权限
    - 私人库：需要登录
    """
    # 权限检查
    if library_type == "public":
        if not current_user or current_user.role != "admin":
            raise HTTPException(
                status_code=403,
                detail="只有管理员可以修改公共库文档"
            )
    elif library_type == "private":
        if not current_user:
            raise HTTPException(
                status_code=401,
                detail="请先登录后修改私人库文档"
            )

    metadata = load_metadata(library_type)
    record = metadata.get(filename)
    if not record:
        raise HTTPException(status_code=404, detail="文件不存在")

    if payload.title is not None:
        record["title"] = payload.title.strip() or record.get("title")

    if payload.category is not None:
        record["category"] = normalize_category(payload.category)

    if payload.tags is not None:
        record["tags"] = [tag.strip() for tag in payload.tags if tag and tag.strip()]

    # 更新分类特定字段
    if payload.effectiveness_level is not None:
        record["effectiveness_level"] = payload.effectiveness_level.strip()
    if payload.document_type is not None:
        record["document_type"] = payload.document_type.strip()
    if payload.discipline is not None:
        record["discipline"] = payload.discipline.strip()
    if payload.region is not None:
        record["region"] = payload.region.strip()
    if payload.main_topic is not None:
        record["main_topic"] = payload.main_topic.strip()

    if payload.regenerate_tags:
        try:
            file_path = resolve_document_path(record, library_type)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="文件内容不存在")

        existing_tags = collect_existing_tags(metadata, exclude_filename=filename)
        preview_text = document_service.get_document_preview(str(file_path), max_chars=1500)

        # 使用新的extract_metadata方法重新提取元数据
        metadata_result = await tagging_service.extract_metadata(
            preview_text,
            record.get("category", "论文"),
            existing_tags,
        )
        record["tags"] = metadata_result.get("tags", [])

        # 更新分类特定字段
        category_fields = metadata_result.get("category_fields", {})
        if record.get("category") == "政策":
            record["effectiveness_level"] = category_fields.get("effectiveness_level", "")
            record["document_type"] = category_fields.get("document_type", "")
        elif record.get("category") == "论文":
            record["discipline"] = category_fields.get("discipline", "")
            record["main_topic"] = category_fields.get("main_topic", "")
        elif record.get("category") == "案例":
            record["region"] = category_fields.get("region", "")
            record["main_topic"] = category_fields.get("main_topic", "")

    record["updated_time"] = datetime.now(timezone.utc).isoformat()
    metadata[filename] = record
    save_metadata(metadata, library_type)

    return {"status": "success", "data": record}


@router.delete("/documents/{filename}")
async def delete_document(
    filename: str,
    library_type: Optional[str] = Query("public", description="库类型: public 或 private"),
    current_user: Optional[User] = Depends(get_optional_user),
) -> Dict[str, Any]:
    """
    删除文档

    **权限要求**：
    - 公共库：需要管理员权限
    - 私人库：需要登录
    """
    # 权限检查
    if library_type == "public":
        if not current_user or current_user.role != "admin":
            raise HTTPException(
                status_code=403,
                detail="只有管理员可以删除公共库文档"
            )
    elif library_type == "private":
        if not current_user:
            raise HTTPException(
                status_code=401,
                detail="请先登录后删除私人库文档"
            )

    metadata = load_metadata(library_type)
    record = metadata.get(filename)
    if not record:
        raise HTTPException(status_code=404, detail="文件不存在")

    # 保存knowledge_group_id用于后续更新计数
    knowledge_group_id = record.get("knowledge_group_id")
    record_library_type = record.get("library_type", library_type)

    try:
        file_path = resolve_document_path(record, record_library_type)
    except FileNotFoundError:
        file_path = None

    if file_path and file_path.exists():
        file_path.unlink()

    # 使用文档记录中的library_type和knowledge_group_id来查找正确的向量路径
    index_path, texts_path = resolve_vector_paths(filename, record_library_type, knowledge_group_id)
    for path in (index_path, texts_path):
        if path.exists():
            path.unlink()

    metadata.pop(filename, None)
    save_metadata(metadata, library_type)

    # 如果是私人库，更新知识组的文档计数
    if library_type == "private" and knowledge_group_id:
        from backend.app.services.knowledge_group import knowledge_group_service
        knowledge_group_service.update_group_document_count(knowledge_group_id)

    # 不再自动触发索引合并，检索时会同时检索合并索引和未合并的小索引
    # asyncio.create_task(
    #     run_in_threadpool(
    #         document_service.build_merged_index,
    #         library_type,
    #         knowledge_group_id
    #     )
    # )
    # logger.info("删除文档后触发索引更新: library_type=%s, group_id=%s", library_type, knowledge_group_id)

    return {"status": "success", "message": "文件删除成功"}


@router.post("/documents/batch-download")
async def batch_download_documents(
    payload: BatchDocumentRequest,
    library_type: Optional[str] = Query("public", description="库类型: public 或 private"),
) -> StreamingResponse:
    filenames = list(payload.normalized)
    if not filenames:
        raise HTTPException(status_code=400, detail="请提供至少一个文件名")

    metadata = load_metadata(library_type)
    records, missing = resolve_document_records(metadata, filenames, library_type or "public")

    if missing:
        raise HTTPException(status_code=404, detail=f"以下文件不存在或无法访问: {', '.join(missing)}")

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for record in records:
            file_path = Path(record.get("path", ""))
            arcname = record.get("filename") or file_path.name
            archive.write(file_path, arcname=arcname)

    buffer.seek(0)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    headers = {
        "Content-Disposition": f'attachment; filename="documents-{timestamp}.zip"',
        "Access-Control-Expose-Headers": "Content-Disposition",
    }
    return StreamingResponse(buffer, media_type="application/zip", headers=headers)


@router.post("/documents/batch-delete")
async def batch_delete_documents(
    payload: BatchDocumentRequest,
    library_type: Optional[str] = Query("public", description="库类型: public 或 private"),
    current_user: Optional[User] = Depends(get_optional_user),
) -> Dict[str, Any]:
    """
    批量删除文档

    **权限要求**：
    - 公共库：需要管理员权限
    - 私人库：需要登录
    """
    # 权限检查
    if library_type == "public":
        if not current_user or current_user.role != "admin":
            raise HTTPException(
                status_code=403,
                detail="只有管理员可以删除公共库文档"
            )
    elif library_type == "private":
        if not current_user:
            raise HTTPException(
                status_code=401,
                detail="请先登录后删除私人库文档"
            )

    filenames = list(payload.normalized)
    if not filenames:
        raise HTTPException(status_code=400, detail="请提供至少一个文件名")

    metadata = load_metadata(library_type)
    deleted: List[str] = []
    missing: List[str] = []
    affected_groups: set = set()  # 记录受影响的知识组ID

    for filename in filenames:
        record = metadata.get(filename)
        if not record:
            missing.append(filename)
            continue

        # 保存knowledge_group_id和library_type
        knowledge_group_id = record.get("knowledge_group_id")
        record_library_type = record.get("library_type", library_type)
        if knowledge_group_id:
            affected_groups.add(knowledge_group_id)

        try:
            file_path = resolve_document_path(record, record_library_type)
        except FileNotFoundError:
            file_path = None

        if file_path and file_path.exists():
            file_path.unlink()

        # 使用文档记录中的library_type和knowledge_group_id来查找正确的向量路径
        index_path, texts_path = resolve_vector_paths(filename, record_library_type, knowledge_group_id)
        for path in (index_path, texts_path):
            if path.exists():
                path.unlink()

        metadata.pop(filename, None)
        deleted.append(filename)

    save_metadata(metadata, library_type)

    # 如果是私人库，更新所有受影响的知识组的文档计数
    if library_type == "private" and affected_groups:
        from backend.app.services.knowledge_group import knowledge_group_service
        for group_id in affected_groups:
            knowledge_group_service.update_group_document_count(group_id)

    # 不再自动触发索引合并，检索时会同时检索合并索引和未合并的小索引
    # 对于批量删除，如果涉及多个知识组，需要为每个组触发更新
    # if library_type == "private" and affected_groups:
    #     for group_id in affected_groups:
    #         asyncio.create_task(
    #             run_in_threadpool(
    #                 document_service.build_merged_index,
    #                 library_type,
    #                 group_id
    #             )
    #         )
    #         logger.info("批量删除后触发索引更新: library_type=%s, group_id=%s", library_type, group_id)
    # else:
    #     # 公共库只需触发一次
    #     asyncio.create_task(
    #         run_in_threadpool(
    #             document_service.build_merged_index,
    #             library_type,
    #             None
    #         )
    #     )
    #     logger.info("批量删除后触发索引更新: library_type=%s", library_type)

    return {
        "status": "success",
        "data": {
            "deleted": deleted,
            "missing": missing,
        },
    }
