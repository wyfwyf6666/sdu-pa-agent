from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional
import hashlib
import re
import json
import csv
import os

import faiss
import numpy as np
import PyPDF2
import docx
import pandas as pd
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class DocumentService:
    """负责知识库文档的持久化、索引和检索。"""

    def __init__(self) -> None:
        # 获取项目根目录的绝对路径
        self.root_dir = Path(__file__).resolve().parents[3]

        # Windows中文路径兼容：FAISS的C++库无法读取含中文字符的路径
        # 若存在ASCII junction则优先使用
        ascii_data = Path("C:/city_research_data")
        if ascii_data.exists():
            self.public_vector_store_path = ascii_data / "public" / "vectors"
            self.public_documents_path = ascii_data / "public" / "documents"
            self.private_root_path = ascii_data / "private"
        else:
            self.public_vector_store_path = self.root_dir / "backend" / "data" / "public" / "vectors"
            self.public_documents_path = self.root_dir / "backend" / "data" / "public" / "documents"
            self.private_root_path = self.root_dir / "backend" / "data" / "private"

        # 兼容旧代码：默认使用公共库路径
        self.vector_store_path = self.public_vector_store_path
        self.documents_path = self.public_documents_path

        self.public_vector_store_path.mkdir(parents=True, exist_ok=True)
        self.public_documents_path.mkdir(parents=True, exist_ok=True)

        self.index: Optional[faiss.IndexFlatL2] = None

        # 内存缓存：避免重复加载索引文件
        # 缓存格式：{(library_type, knowledge_group_id): (faiss_index, metadata, file_mtime)}
        self._index_cache: Dict[tuple[str, Optional[str]], tuple[Any, List[Dict[str, Any]], float]] = {}

        # 切割文本的配置
        self._ensure_text_splitter()

        self.model = self._load_embedding_model()
        self.embedding_dim = self.model.get_sentence_embedding_dimension()

        detected_dim = self._detect_existing_index_dimension()
        if detected_dim and detected_dim != self.embedding_dim:
            logger.warning(
                "当前嵌入模型维度 %d 与已存在索引维度 %d 不一致，尝试重新加载兼容模型",
                self.embedding_dim,
                detected_dim,
            )
            fallback_model_name = os.getenv("EMBEDDING_FALLBACK_MODEL", "moka-ai/m3e-base")
            try:
                self.model = SentenceTransformer(fallback_model_name)
                self.embedding_dim = self.model.get_sentence_embedding_dimension()
                logger.info("已加载兼容嵌入模型 %s，维度=%d", fallback_model_name, self.embedding_dim)
            except Exception as exc:
                logger.error("加载兼容嵌入模型失败: %s", exc)
                raise

            if self.embedding_dim != detected_dim:
                logger.error(
                    "重新加载后的嵌入维度 %d 仍与索引维度 %d 不一致，检索可能失败",
                    self.embedding_dim,
                    detected_dim,
                )

        logger.info("Embedding model ready，维度=%d", self.embedding_dim)

    def _load_embedding_model(self) -> SentenceTransformer:
        """加载嵌入模型，优先使用环境变量配置。"""
        env_model_path = os.getenv("EMBEDDING_MODEL_PATH")
        if env_model_path:
            path = Path(env_model_path)
            if path.exists():
                logger.info("从环境变量路径加载嵌入模型: %s", path)
                return SentenceTransformer(str(path))
            logger.warning("指定的 EMBEDDING_MODEL_PATH 不存在: %s", path)

        env_model_name = os.getenv("EMBEDDING_MODEL_NAME")
        if env_model_name:
            logger.info("从模型名称加载嵌入模型: %s", env_model_name)
            return SentenceTransformer(env_model_name)

        local_model_path = self.root_dir / "backend" / "models" / "distiluse-base-multilingual-cased-v1"
        if local_model_path.exists():
            logger.info("使用本地嵌入模型: %s", local_model_path)
            return SentenceTransformer(str(local_model_path))

        fallback_model_name = os.getenv("EMBEDDING_FALLBACK_MODEL", "moka-ai/m3e-base")
        logger.warning(
            "未找到本地嵌入模型，使用默认远程模型: %s（首次会自动下载）",
            fallback_model_name,
        )
        return SentenceTransformer(fallback_model_name)

    def _ensure_text_splitter(self) -> None:
        """确保文本切割器已创建（兼容旧实例）。"""
        if hasattr(self, "text_splitter") and self.text_splitter is not None:
            return
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            length_function=len,
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?"],
        )

    def _detect_existing_index_dimension(self) -> Optional[int]:
        """检测已有FAISS索引的向量维度，用于校验当前嵌入模型。"""
        candidate_paths: List[Path] = []

        def add_candidates(base: Path) -> None:
            if not base.exists():
                return
            merged = base / "_merged_index.faiss"
            candidate_paths.append(merged)
            candidate_paths.extend(sorted(base.glob("*.faiss")))

        add_candidates(self.public_vector_store_path)

        if self.private_root_path.exists():
            for group_dir in self.private_root_path.iterdir():
                if not group_dir.is_dir():
                    continue
                vectors_dir = group_dir / "vectors"
                add_candidates(vectors_dir)

        seen: set[Path] = set()
        for path in candidate_paths:
            if path in seen or not path.exists():
                continue
            seen.add(path)
            try:
                index = faiss.read_index(str(path))
                logger.info("检测到索引 %s，维度=%d", path, index.d)
                return index.d
            except Exception as exc:
                logger.warning("读取索引 %s 失败: %s", path, exc)

        return None

        # 切割文本的配置
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            length_function=len,
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?"],
        )

        # 初始化时自动处理已有文档
        self._initialize_vectors()

    # -------------------------------------------------------------------------
    # 统一索引管理
    # -------------------------------------------------------------------------
    def _get_merged_index_paths(self, library_type: str = "public", knowledge_group_id: Optional[str] = None) -> tuple[Path, Path]:
        """获取合并索引的路径"""
        vector_store_path = self.get_vector_store_path(library_type, knowledge_group_id)
        return (
            vector_store_path / "_merged_index.faiss",
            vector_store_path / "_merged_metadata.pkl"
        )

    def build_merged_index(self, library_type: str = "public", knowledge_group_id: Optional[str] = None, force_full_rebuild: bool = False) -> None:
        """
        构建或增量更新统一索引

        Args:
            library_type: 库类型
            knowledge_group_id: 知识组ID
            force_full_rebuild: 是否强制全量重建（默认False，使用增量更新）
        """
        logger.info("开始构建统一索引: library_type=%s, group_id=%s, force_full=%s",
                   library_type, knowledge_group_id, force_full_rebuild)

        vector_store_path = self.get_vector_store_path(library_type, knowledge_group_id)
        merged_index_path, merged_metadata_path = self._get_merged_index_paths(library_type, knowledge_group_id)

        # 获取所有原始索引文件
        index_files = list(vector_store_path.glob("*.faiss"))
        index_files = [f for f in index_files if f.name != "_merged_index.faiss"]

        logger.info("找到 %d 个向量文件", len(index_files))

        if not index_files:
            logger.warning("没有找到需要合并的索引文件")
            return

        # 检查是否可以增量更新
        can_incremental = (
            not force_full_rebuild
            and merged_index_path.exists()
            and merged_metadata_path.exists()
        )

        if can_incremental:
            # 增量更新模式
            logger.info("使用增量更新模式")
            merged_mtime = merged_index_path.stat().st_mtime

            # 找出所有新增或更新的文件
            new_or_updated_files = [
                f for f in index_files
                if f.stat().st_mtime > merged_mtime
            ]

            if not new_or_updated_files:
                logger.info("没有新增或更新的文件，索引已是最新")
                return

            logger.info("发现 %d 个新增或更新的文件，进行增量更新", len(new_or_updated_files))

            try:
                # 加载现有的合并索引和元数据
                existing_index = faiss.read_index(str(merged_index_path))
                with open(merged_metadata_path, "rb") as f:
                    existing_metadata = pickle.load(f)

                dimension = existing_index.d
                logger.info("加载现有索引完成: %d 个向量, 维度=%d", existing_index.ntotal, dimension)

                # 创建一个source到索引位置的映射，用于去重
                source_to_indices = {}
                for idx, meta in enumerate(existing_metadata):
                    source = meta.get("source")
                    if source:
                        if source not in source_to_indices:
                            source_to_indices[source] = []
                        source_to_indices[source].append(idx)

                # 收集需要删除的索引位置（被更新的文档）
                indices_to_remove = set()

                # 收集新向量和元数据
                new_vectors: List[np.ndarray] = []
                new_metadata: List[Dict[str, Any]] = []

                for index_file in new_or_updated_files:
                    logger.info("处理更新文件: %s", index_file.name)
                    texts_file = vector_store_path / f"{index_file.stem}.pkl"

                    if not texts_file.exists():
                        logger.warning("pkl文件不存在，跳过: %s", texts_file)
                        continue

                    try:
                        # 如果这个文档之前存在，标记旧数据需要删除
                        if index_file.stem in source_to_indices:
                            indices_to_remove.update(source_to_indices[index_file.stem])
                            logger.info("文档 %s 已存在，将替换旧数据", index_file.stem)

                        # 读取新索引和元数据
                        index = faiss.read_index(str(index_file))
                        if index.d != dimension:
                            logger.error("向量维度不匹配: expected %d, got %d", dimension, index.d)
                            continue

                        # 提取所有向量
                        vectors = np.zeros((index.ntotal, dimension), dtype='float32')
                        for i in range(index.ntotal):
                            vectors[i] = index.reconstruct(int(i))

                        # 读取元数据
                        with open(texts_file, "rb") as f:
                            stored_entries = pickle.load(f)

                        # 标准化元数据格式
                        if stored_entries and isinstance(stored_entries[0], str):
                            entries = [
                                {"content": chunk, "source": index_file.stem, "chunk_index": chunk_idx}
                                for chunk_idx, chunk in enumerate(stored_entries)
                            ]
                        else:
                            entries = stored_entries

                        new_vectors.append(vectors)
                        new_metadata.extend(entries)

                    except Exception as exc:
                        logger.error("处理文件 %s 时出错: %s", index_file.name, exc)
                        continue

                if not new_vectors:
                    logger.info("没有新的向量数据需要添加")
                    return

                # 如果有旧数据需要删除，重建整个索引（FAISS不支持删除）
                if indices_to_remove:
                    logger.info("检测到 %d 个向量需要替换，执行完整重建", len(indices_to_remove))
                    # 保留未被删除的元数据和向量
                    kept_metadata = [
                        meta for idx, meta in enumerate(existing_metadata)
                        if idx not in indices_to_remove
                    ]

                    # 提取未被删除的向量
                    kept_vectors = []
                    for idx in range(existing_index.ntotal):
                        if idx not in indices_to_remove:
                            kept_vectors.append(existing_index.reconstruct(int(idx)))

                    if kept_vectors:
                        kept_vectors_array = np.array(kept_vectors, dtype='float32')
                    else:
                        kept_vectors_array = None

                    # 合并保留的和新的
                    all_metadata = kept_metadata + new_metadata
                    if kept_vectors_array is not None:
                        all_vectors_array = np.vstack([kept_vectors_array] + new_vectors)
                    else:
                        all_vectors_array = np.vstack(new_vectors)

                    # 重建索引
                    new_index = faiss.IndexFlatL2(dimension)
                    new_index.add(all_vectors_array)

                    logger.info("重建完成: 删除 %d 个旧向量, 添加 %d 个新向量, 总计 %d 个",
                               len(indices_to_remove), len(new_metadata), new_index.ntotal)
                else:
                    # 纯增量：直接追加新向量
                    new_vectors_array = np.vstack(new_vectors)
                    existing_index.add(new_vectors_array)

                    all_metadata = existing_metadata + new_metadata
                    new_index = existing_index

                    logger.info("增量更新完成: 添加 %d 个新向量, 总计 %d 个",
                               len(new_metadata), new_index.ntotal)

                # 保存更新后的索引
                faiss.write_index(new_index, str(merged_index_path))
                with open(merged_metadata_path, "wb") as f:
                    pickle.dump(all_metadata, f)

                logger.info("索引增量更新成功")
                return

            except Exception as exc:
                logger.error("增量更新失败，回退到全量重建: %s", exc)
                # 继续执行全量重建

        # 全量重建模式
        logger.info("使用全量重建模式")
        all_vectors: List[np.ndarray] = []
        all_metadata: List[Dict[str, Any]] = []
        dimension = None

        for idx, index_file in enumerate(index_files):
            logger.info("合并文件 %d/%d: %s", idx + 1, len(index_files), index_file.name)
            texts_file = vector_store_path / f"{index_file.stem}.pkl"

            if not texts_file.exists():
                logger.warning("pkl文件不存在，跳过: %s", texts_file)
                continue

            try:
                # 读取索引
                index = faiss.read_index(str(index_file))
                if dimension is None:
                    dimension = index.d
                elif dimension != index.d:
                    logger.error("向量维度不匹配: expected %d, got %d", dimension, index.d)
                    continue

                # 提取所有向量
                vectors = np.zeros((index.ntotal, dimension), dtype='float32')
                for i in range(index.ntotal):
                    vectors[i] = index.reconstruct(int(i))

                # 读取元数据
                with open(texts_file, "rb") as f:
                    stored_entries = pickle.load(f)

                # 标准化元数据格式
                if stored_entries and isinstance(stored_entries[0], str):
                    entries = [
                        {"content": chunk, "source": index_file.stem, "chunk_index": chunk_idx}
                        for chunk_idx, chunk in enumerate(stored_entries)
                    ]
                else:
                    entries = stored_entries

                all_vectors.append(vectors)
                all_metadata.extend(entries)

            except Exception as exc:
                logger.error("处理文件 %s 时出错: %s", index_file.name, exc)
                continue

        if not all_vectors:
            logger.error("没有成功读取任何向量数据")
            return

        # 合并所有向量
        logger.info("合并 %d 个文件的向量...", len(all_vectors))
        merged_vectors = np.vstack(all_vectors)
        logger.info("合并完成，总共 %d 个向量", len(merged_vectors))

        # 创建新的统一索引
        merged_index = faiss.IndexFlatL2(dimension)
        merged_index.add(merged_vectors)

        # 保存统一索引和元数据
        faiss.write_index(merged_index, str(merged_index_path))
        with open(merged_metadata_path, "wb") as f:
            pickle.dump(all_metadata, f)

        logger.info("统一索引构建完成: %s (%d 个向量)", merged_index_path, merged_index.ntotal)

    def _check_merged_index_valid(self, library_type: str = "public", knowledge_group_id: Optional[str] = None) -> bool:
        """检查统一索引是否存在且有效"""
        merged_index_path, merged_metadata_path = self._get_merged_index_paths(library_type, knowledge_group_id)

        if not merged_index_path.exists() or not merged_metadata_path.exists():
            return False

        # 检查统一索引是否比所有小索引都新
        vector_store_path = self.get_vector_store_path(library_type, knowledge_group_id)
        index_files = [f for f in vector_store_path.glob("*.faiss") if f.name != "_merged_index.faiss"]

        if not index_files:
            return False

        merged_mtime = merged_index_path.stat().st_mtime
        for index_file in index_files:
            if index_file.stat().st_mtime > merged_mtime:
                logger.info("检测到索引文件 %s 比统一索引更新，需要重建", index_file.name)
                return False

        return True

    # -------------------------------------------------------------------------
    # 路径管理 - 支持公共/私人库
    # -------------------------------------------------------------------------
    def get_vector_store_path(self, library_type: str = "public", knowledge_group_id: Optional[str] = None) -> Path:
        """根据库类型和知识组ID获取向量存储路径"""
        if library_type == "public":
            return self.public_vector_store_path
        elif library_type == "private" and knowledge_group_id:
            path = self.private_root_path / knowledge_group_id / "vectors"
            path.mkdir(parents=True, exist_ok=True)
            return path
        else:
            raise ValueError("私人库必须指定knowledge_group_id")

    def get_documents_path(self, library_type: str = "public", knowledge_group_id: Optional[str] = None) -> Path:
        """根据库类型和知识组ID获取文档存储路径"""
        if library_type == "public":
            return self.public_documents_path
        elif library_type == "private" and knowledge_group_id:
            path = self.private_root_path / knowledge_group_id / "documents"
            path.mkdir(parents=True, exist_ok=True)
            return path
        else:
            raise ValueError("私人库必须指定knowledge_group_id")

    # -------------------------------------------------------------------------
    # 初始化与批处理
    # -------------------------------------------------------------------------
    def _initialize_vectors(self) -> None:
        """在启动时检查向量存储是否可用，否则对全部文档进行初始化。"""
        try:
            vector_files = list(self.vector_store_path.glob("*.faiss"))

            if not vector_files:
                logger.info("Vector store is empty. Starting document processing...")
                self._process_all_documents()
            else:
                logger.info("Vector store already contains vectors. Skipping initial processing.")
        except Exception as exc:  # pragma: no cover - 仅记录日志
            logger.error("Error during vector store initialization: %s", exc)

    def _process_all_documents(self) -> None:
        """遍历 documents 目录，对支持的文件类型进行批量处理。"""
        supported_extensions = {".pdf", ".docx", ".txt", ".csv", ".xlsx", ".xls", ".json"}

        try:
            doc_files: List[Path] = []
            for ext in supported_extensions:
                doc_files.extend(self.documents_path.glob(f"*{ext}"))

            if not doc_files:
                logger.warning("No supported documents found in documents directory.")
                return

            logger.info("Found %d documents to process.", len(doc_files))

            for doc_path in doc_files:
                try:
                    logger.info("Processing document: %s", doc_path.name)
                    self._process_single_document(str(doc_path))
                    logger.info("Successfully processed: %s", doc_path.name)
                except Exception as exc:  # pragma: no cover - 记录日志
                    logger.error("Error processing document %s: %s", doc_path.name, exc)
                    continue

            logger.info("Completed processing all documents.")
        except Exception as exc:  # pragma: no cover - 记录日志
            logger.error("Error during batch document processing: %s", exc)

    # -------------------------------------------------------------------------
    # 文档读取与分割
    # -------------------------------------------------------------------------
    def _process_single_document(
        self,
        file_path: str,
        library_type: str = "public",
        knowledge_group_id: Optional[str] = None
    ) -> Dict[str, str]:
        """加载、分割并向量化单个文档。"""
        try:
            texts = self.load_document(file_path)
            self.create_or_update_vector_store(texts, file_path, library_type, knowledge_group_id)
            return {"message": "文档处理成功"}
        except Exception as exc:
            raise Exception(f"文档处理失败: {exc}") from exc

    def _get_embeddings(self, texts: List[str]) -> np.ndarray:
        """对文本片段生成嵌入向量。"""
        return self.model.encode(texts, show_progress_bar=True)

    def _read_pdf(self, file_path: str) -> str:
        """读取 PDF 文本内容（优先用 pypdf，降级 PyPDF2）。"""
        text = ""
        try:
            with open(file_path, "rb") as file:
                try:
                    from pypdf import PdfReader
                    pdf_reader = PdfReader(file)
                    # 尝试解密（如果是加密PDF）
                    if pdf_reader.is_encrypted:
                        try:
                            pdf_reader.decrypt("")
                        except Exception:
                            pass
                except ImportError:
                    pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
            logger.info("PDF 文本提取完成，长度: %d", len(text))
            return text
        except Exception as exc:
            logger.error("PDF 读取错误: %s", exc)
            raise

    def _read_docx(self, file_path: str) -> str:
        """读取 DOCX 文本内容。"""
        try:
            doc = docx.Document(file_path)
            paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
            text = "\n".join(paragraphs)
            logger.info("DOCX 文本提取完成，长度: %d", len(text))
            return text
        except Exception as exc:
            logger.error("DOCX 读取错误: %s", exc)
            raise

    def _read_txt(self, file_path: str) -> str:
        """读取 TXT 文本内容。"""
        with open(file_path, "r", encoding="utf-8") as file:
            return file.read()

    def _read_csv(self, file_path: str) -> str:
        """读取 CSV 文件并转换为 JSON 格式文本。"""
        try:
            df = pd.read_csv(file_path, encoding="utf-8")

            # 将 DataFrame 转换为 JSON 格式
            text = f"CSV 文件数据 (共 {len(df)} 行，{len(df.columns)} 列)\n\n"
            text += f"列名: {', '.join(df.columns.tolist())}\n\n"

            # 将所有数据转换为 JSON 格式
            data_json = df.to_dict(orient='records')
            text += "完整数据（JSON 格式）:\n"
            text += json.dumps(data_json, ensure_ascii=False, indent=2)

            logger.info("CSV 文件读取完成，行数: %d", len(df))
            return text
        except Exception as exc:
            logger.error("CSV 读取错误: %s", exc)
            raise

    def _read_excel(self, file_path: str) -> str:
        """读取 Excel 文件并转换为 JSON 格式文本。"""
        try:
            # 使用上下文管理器确保文件正确关闭
            with pd.ExcelFile(file_path) as xl_file:
                text = f"Excel 文件包含 {len(xl_file.sheet_names)} 个工作表\n\n"

                all_sheets_data = {}
                for sheet_name in xl_file.sheet_names:
                    df = pd.read_excel(xl_file, sheet_name=sheet_name)
                    text += f"\n{'='*50}\n"
                    text += f"工作表: {sheet_name}\n"
                    text += f"共 {len(df)} 行，{len(df.columns)} 列\n"
                    text += f"列名: {', '.join(df.columns.tolist())}\n\n"

                    # 将工作表数据转换为 JSON
                    sheet_data = df.to_dict(orient='records')
                    all_sheets_data[sheet_name] = sheet_data

                # 输出所有工作表的完整数据（JSON格式）
                text += f"\n{'='*50}\n"
                text += "完整数据（JSON 格式）:\n"
                text += json.dumps(all_sheets_data, ensure_ascii=False, indent=2)

                logger.info("Excel 文件读取完成，工作表数: %d", len(xl_file.sheet_names))
                return text
        except Exception as exc:
            logger.error("Excel 读取错误: %s", exc)
            raise

    def _read_json(self, file_path: str) -> str:
        """读取 JSON 文件并转换为文本。"""
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                data = json.load(file)

            # 将 JSON 数据转换为格式化的字符串
            text = "JSON 文件内容:\n\n"
            text += json.dumps(data, ensure_ascii=False, indent=2)

            # 如果是列表，提供额外的统计信息
            if isinstance(data, list):
                text += f"\n\n数据统计: 共包含 {len(data)} 个项目"
                if len(data) > 0 and isinstance(data[0], dict):
                    text += f"\n每个项目的键: {', '.join(data[0].keys())}"
            elif isinstance(data, dict):
                text += f"\n\n数据统计: 共包含 {len(data)} 个键"
                text += f"\n键名: {', '.join(data.keys())}"

            logger.info("JSON 文件读取完成")
            return text
        except Exception as exc:
            logger.error("JSON 读取错误: %s", exc)
            raise

    def _read_document_text(self, file_path: str) -> str:
        """根据扩展名读取原始文档文本。"""
        suffix = Path(file_path).suffix.lower()
        if suffix == ".pdf":
            return self._read_pdf(file_path)
        if suffix == ".docx":
            return self._read_docx(file_path)
        if suffix == ".txt":
            return self._read_txt(file_path)
        if suffix == ".csv":
            return self._read_csv(file_path)
        if suffix in {".xlsx", ".xls"}:
            return self._read_excel(file_path)
        if suffix == ".json":
            return self._read_json(file_path)
        raise ValueError("不支持的文件类型")

    def get_data_file_metadata(self, file_path: str) -> Dict[str, Any]:
        """提取数据文件的元信息（行数、列数、表头等）。"""
        suffix = Path(file_path).suffix.lower()

        try:
            if suffix == ".csv":
                df = pd.read_csv(file_path, encoding="utf-8")
                return {
                    "rows": len(df),
                    "columns": len(df.columns),
                    "headers": df.columns.tolist(),
                    "data_type": "CSV"
                }
            elif suffix in {".xlsx", ".xls"}:
                with pd.ExcelFile(file_path) as xl_file:
                    sheets_info = []
                    total_rows = 0
                    all_headers = []

                    for sheet_name in xl_file.sheet_names:
                        df = pd.read_excel(xl_file, sheet_name=sheet_name)
                        sheets_info.append({
                            "name": sheet_name,
                            "rows": len(df),
                            "columns": len(df.columns),
                            "headers": df.columns.tolist()
                        })
                        total_rows += len(df)
                        all_headers.extend(df.columns.tolist())

                    return {
                        "rows": total_rows,
                        "columns": len(set(all_headers)),
                        "headers": list(set(all_headers)),
                        "sheets": sheets_info,
                        "sheet_count": len(xl_file.sheet_names),
                        "data_type": "Excel"
                    }
            elif suffix == ".json":
                with open(file_path, "r", encoding="utf-8") as file:
                    data = json.load(file)

                if isinstance(data, list):
                    item_count = len(data)
                    if item_count > 0 and isinstance(data[0], dict):
                        headers = list(data[0].keys())
                    else:
                        headers = []
                    return {
                        "rows": item_count,
                        "columns": len(headers) if headers else 0,
                        "headers": headers,
                        "data_type": "JSON (Array)"
                    }
                elif isinstance(data, dict):
                    return {
                        "rows": 1,
                        "columns": len(data.keys()),
                        "headers": list(data.keys()),
                        "data_type": "JSON (Object)"
                    }
                else:
                    return {
                        "data_type": "JSON (Other)",
                        "type": str(type(data).__name__)
                    }
            else:
                return {}
        except Exception as exc:
            logger.error("提取数据文件元信息失败: %s", exc)
            return {}

    def get_document_text(self, file_path: str, max_chars: Optional[int] = None) -> str:
        """返回文档全文，可选截断长度。"""
        text = self._normalize_text_encoding(self._read_document_text(file_path)).strip()
        if max_chars is not None and max_chars > 0:
            return text[:max_chars]
        return text

    def get_document_preview(self, file_path: str, max_chars: int = 1200) -> str:
        """返回用于预览的文本片段。"""
        return self.get_document_text(file_path, max_chars=max_chars)

    def load_document(self, file_path: str) -> List[str]:
        """加载文档并切分为片段。"""
        self._ensure_text_splitter()
        try:
            text = self._normalize_text_encoding(self._read_document_text(file_path))
            logger.info("文档 %s 读取完成，文本长度: %d", file_path, len(text))

            if not text.strip():
                logger.warning("文档 %s 提取的文本为空", file_path)
                return []

            chunks = self.text_splitter.split_text(text)
            logger.info("文本分割完成，共 %d 个片段", len(chunks))

            if not chunks:
                logger.warning("文档 %s 分割后没有文本片段", file_path)
                return []

            return chunks
        except Exception as exc:
            logger.error("文档加载失败: %s", exc)
            raise

    @staticmethod
    def _normalize_text_encoding(text: str) -> str:
        """尝试修复 GBK 等编码被误按 latin-1 解码导致的乱码。"""
        if not text:
            return text
        sample = text[:2000]
        latin1_like = sum(1 for ch in sample if "\u00A0" <= ch <= "\u00FF")
        cjk_chars = sum(1 for ch in sample if "\u4E00" <= ch <= "\u9FFF")
        if latin1_like > 30 and cjk_chars * 3 < latin1_like:
            try:
                recovered = text.encode("latin-1", errors="ignore").decode("gbk")
                return recovered
            except UnicodeError:
                return text
        return text

    # -------------------------------------------------------------------------
    # 向量化与搜索
    # -------------------------------------------------------------------------
    @staticmethod
    def _sanitize_vector_stem(original_stem: str) -> str:
        safe_chars: List[str] = []
        for ch in original_stem:
            if ch.isascii() and (ch.isalnum() or ch in {"_", "-"}):
                safe_chars.append(ch)
            else:
                safe_chars.append("_")
        sanitized = re.sub(r"_+", "_", "".join(safe_chars)).strip("_")
        if not sanitized:
            sanitized = hashlib.md5(original_stem.encode("utf-8"), usedforsecurity=False).hexdigest()
        return sanitized

    def get_vector_paths_for_filename(
        self,
        filename: str,
        library_type: str = "public",
        knowledge_group_id: Optional[str] = None
    ) -> tuple[Path, Path]:
        original_stem = Path(filename).stem
        safe_stem = self._sanitize_vector_stem(original_stem)
        vector_store_path = self.get_vector_store_path(library_type, knowledge_group_id)
        return (
            vector_store_path / f"{safe_stem}.faiss",
            vector_store_path / f"{safe_stem}.pkl",
        )

    def create_or_update_vector_store(
        self,
        texts: List[str],
        file_path: str,
        library_type: str = "public",
        knowledge_group_id: Optional[str] = None
    ) -> None:
        """根据文本片段创建或更新向量存储。"""
        try:
            if not texts:
                logger.warning("文档 %s 没有可用的文本片段，跳过向量存储更新", file_path)
                return

            metadata_entries = [
                {"content": chunk, "source": Path(file_path).name, "chunk_index": idx}
                for idx, chunk in enumerate(texts)
            ]

            embeddings = self._get_embeddings([entry["content"] for entry in metadata_entries])
            dimension = embeddings.shape[1]

            index_path, texts_path = self.get_vector_paths_for_filename(
                Path(file_path).name,
                library_type,
                knowledge_group_id
            )

            index = faiss.IndexFlatL2(dimension)
            index.add(embeddings.astype("float32"))

            faiss.write_index(index, str(index_path))
            with open(texts_path, "wb") as file:
                pickle.dump(metadata_entries, file)

            logger.info("向量存储创建或更新成功: %s", index_path)
        except Exception as exc:
            logger.error("向量存储创建失败: %s", exc)
            raise

    async def process_document(
        self,
        file_path: str,
        library_type: str = "public",
        knowledge_group_id: Optional[str] = None
    ) -> Dict[str, str]:
        """异步封装单文档处理流程。"""
        return self._process_single_document(file_path, library_type, knowledge_group_id)

    async def search_similar_texts(
        self,
        query: str,
        k: int = 3,
        library_type: Optional[str] = None,
        knowledge_group_ids: Optional[List[str]] = None,
        distance_threshold: float = 150.0  # L2距离阈值，过滤不相关结果
    ) -> List[Dict[str, Any]]:
        """
        在指定范围内执行相似度检索并合并结果。
        使用统一的合并索引来加速搜索。

        Args:
            query: 搜索查询
            k: 返回结果数量
            library_type: 库类型 "public" | "private" | None (搜索全部)
            knowledge_group_ids: 私人库时指定要搜索的知识组ID列表
            distance_threshold: L2距离阈值，大于此值的结果将被过滤
        """
        try:
            query_embedding = self._get_embeddings([query]).astype("float32")
            results: List[tuple[float, Dict[str, Any]]] = []
            fallback_candidates: List[tuple[float, Dict[str, Any]]] = []

            # 确定要搜索的库配置列表
            search_configs: List[tuple[str, Optional[str]]] = []

            if library_type is None or library_type == "public":
                search_configs.append(("public", None))

            if library_type is None or library_type == "private":
                if knowledge_group_ids:
                    for group_id in knowledge_group_ids:
                        group_vector_path = self.private_root_path / group_id / "vectors"
                        if group_vector_path.exists():
                            search_configs.append(("private", group_id))
                elif library_type == "private":
                    # 搜索所有私人库知识组
                    if self.private_root_path.exists():
                        for group_dir in self.private_root_path.iterdir():
                            if group_dir.is_dir():
                                group_vector_path = group_dir / "vectors"
                                if group_vector_path.exists():
                                    search_configs.append(("private", group_dir.name))

            logger.info("开始搜索，共 %d 个库配置", len(search_configs))

            # 对每个库配置检索合并索引 + 未合并的小索引
            for config_idx, (current_library_type, current_group_id) in enumerate(search_configs):
                logger.info("搜索配置 %d/%d: library_type=%s, group_id=%s",
                           config_idx + 1, len(search_configs), current_library_type, current_group_id)

                vector_path = self.get_vector_store_path(current_library_type, current_group_id)

                # 获取合并索引路径
                merged_index_path, merged_metadata_path = self._get_merged_index_paths(
                    current_library_type, current_group_id
                )

                # 记录合并索引的修改时间（如果存在）
                merged_mtime = merged_index_path.stat().st_mtime if merged_index_path.exists() else 0

                # 找出所有索引文件
                all_index_files = [f for f in vector_path.glob("*.faiss") if f.name != "_merged_index.faiss"]

                # 分类：已合并的和未合并的
                unmerged_files = []
                if merged_mtime > 0:
                    # 有合并索引，找出比它更新的文件
                    unmerged_files = [f for f in all_index_files if f.stat().st_mtime > merged_mtime]
                else:
                    # 没有合并索引，所有文件都是未合并的
                    unmerged_files = all_index_files

                logger.info("索引状态: 合并索引=%s, 未合并小索引=%d个",
                           "存在" if merged_mtime > 0 else "不存在", len(unmerged_files))

                # 1. 检索合并索引（如果存在）
                if merged_mtime > 0 and merged_index_path.exists() and merged_metadata_path.exists():
                    # 使用内存缓存加载合并索引
                    cache_key = (current_library_type, current_group_id)
                    current_mtime = merged_index_path.stat().st_mtime

                    # 检查缓存是否有效
                    if cache_key in self._index_cache:
                        cached_index, cached_metadata, cached_mtime = self._index_cache[cache_key]
                        if cached_mtime == current_mtime:
                            # 缓存有效，直接使用
                            logger.info("使用缓存的合并索引: library_type=%s, group_id=%s, 向量数=%d",
                                       current_library_type, current_group_id, cached_index.ntotal)
                            merged_index = cached_index
                            all_metadata = cached_metadata
                        else:
                            # 文件已更新，清除缓存
                            logger.info("合并索引文件已更新，清除缓存: library_type=%s, group_id=%s",
                                       current_library_type, current_group_id)
                            del self._index_cache[cache_key]
                            merged_index = None
                            all_metadata = None
                    else:
                        merged_index = None
                        all_metadata = None

                    # 如果缓存未命中，从文件加载
                    if merged_index is None:
                        try:
                            logger.info("从文件加载合并索引: %s", merged_index_path)
                            merged_index = faiss.read_index(str(merged_index_path))

                            logger.info("从文件加载合并元数据: %s", merged_metadata_path)
                            with open(merged_metadata_path, "rb") as f:
                                all_metadata = pickle.load(f)

                            logger.info("合并索引加载完成，共 %d 个向量，缓存到内存", merged_index.ntotal)

                            # 缓存到内存
                            self._index_cache[cache_key] = (merged_index, all_metadata, current_mtime)
                        except Exception as load_exc:
                            logger.error("加载合并索引失败: %s", load_exc)
                            merged_index = None
                            all_metadata = None

                    # 在合并索引中搜索
                    if merged_index is not None and all_metadata is not None:
                        try:
                            search_k = min(k * 3, merged_index.ntotal)  # 搜索更多结果以便后续过滤
                            distances, indices = merged_index.search(query_embedding, search_k)

                            matched_count = 0
                            for dist, idx in zip(distances[0], indices[0]):
                                if 0 <= idx < len(all_metadata):
                                    entry = all_metadata[idx]
                                    entry_with_score = {
                                        "content": entry.get("content", ""),
                                        "source": entry.get("source", "未知来源"),
                                        "chunk_index": entry.get("chunk_index", idx),
                                        "score": float(dist),
                                        "library_type": current_library_type,
                                        "knowledge_group_id": current_group_id,
                                        "knowledge_group_name": self._get_group_name(current_group_id),
                                    }
                                    if dist <= distance_threshold:
                                        results.append((dist, entry_with_score))
                                        matched_count += 1
                                    else:
                                        fallback_candidates.append((dist, entry_with_score))

                            logger.info("在合并索引中匹配到 %d 个结果", matched_count)

                        except Exception as exc:
                            logger.error("合并索引搜索失败: %s", exc)

                # 2. 检索未合并的小索引
                if unmerged_files:
                    logger.info("开始检索 %d 个未合并的小索引", len(unmerged_files))
                    for index_file in unmerged_files[:30]:  # 限制最多处理30个文件
                        texts_file = vector_path / f"{index_file.stem}.pkl"
                        if not texts_file.exists():
                            continue

                        try:
                            index = faiss.read_index(str(index_file))
                            with open(texts_file, "rb") as file:
                                stored_entries = pickle.load(file)

                            if stored_entries and isinstance(stored_entries[0], str):
                                stored_entries = [
                                    {"content": chunk, "source": index_file.stem, "chunk_index": i}
                                    for i, chunk in enumerate(stored_entries)
                                ]

                            top_k = min(k, index.ntotal)
                            distances, indices = index.search(query_embedding, top_k)

                            for dist, idx in zip(distances[0], indices[0]):
                                if idx < 0 or idx >= len(stored_entries):
                                    continue

                                entry = stored_entries[idx]
                                entry_with_score = {
                                    "content": entry.get("content", ""),
                                    "source": entry.get("source", index_file.stem),
                                    "chunk_index": entry.get("chunk_index", idx),
                                    "score": float(dist),
                                    "library_type": current_library_type,
                                    "knowledge_group_id": current_group_id,
                                    "knowledge_group_name": self._get_group_name(current_group_id),
                                }
                                if dist <= distance_threshold:
                                    results.append((dist, entry_with_score))
                                else:
                                    fallback_candidates.append((dist, entry_with_score))

                        except Exception as fallback_exc:
                            logger.error("检索未合并索引 %s 时出错: %s", index_file.name, fallback_exc)
                            continue

                    logger.info("未合并索引检索完成")

            # 按距离排序并返回前k个结果
            results.sort(key=lambda item: item[0])
            filtered_results = [entry for _, entry in results[:k]]

            if not filtered_results and fallback_candidates:
                logger.info(
                    "所有候选都被距离阈值过滤，使用距离最小的 %d 条备选结果",
                    min(k, len(fallback_candidates)),
                )
                fallback_candidates.sort(key=lambda item: item[0])
                filtered_results = [entry for _, entry in fallback_candidates[:k]]

            logger.info("检索完成：原始候选 %d 个，返回 %d 个",
                       len(results), len(filtered_results))
            return filtered_results
        except Exception as exc:
            raise Exception(f"相似文本搜索失败: {exc}") from exc

    def _get_group_name(self, group_id: Optional[str]) -> Optional[str]:
        """从metadata获取知识组名称"""
        if not group_id:
            return None

        try:
            import json
            metadata_file = self.private_root_path / "metadata.json"
            if metadata_file.exists():
                with open(metadata_file, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                group_info = metadata.get("knowledge_groups", {}).get(group_id)
                return group_info.get("name") if group_info else None
        except Exception:
            return None


document_service = DocumentService()
