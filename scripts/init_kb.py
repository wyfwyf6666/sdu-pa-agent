"""
知识库批量初始化脚本
遍历 data/public/documents/ 中的 PDF/Word 文件，进行文本分块、向量化、存入 FAISS 索引，
并调用 DeepSeek 为每篇文档自动生成一句话摘要和核心标签。

用法: python scripts/init_kb.py [--force] [--dry-run]
  --force    强制重建所有索引
  --dry-run  仅扫描不写入
"""
import argparse, hashlib, json, logging, os, sys, time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("init_kb")

ROOT = Path(__file__).resolve().parents[1]
DOC_DIR = ROOT / "backend" / "data" / "public" / "documents"
VEC_DIR = ROOT / "backend" / "data" / "public" / "vectors"
META_FILE = ROOT / "backend" / "data" / "metadata.json"
sys.path.insert(0, str(ROOT))


def compute_file_hash(filepath: Path) -> str:
    return hashlib.md5(filepath.read_bytes()).hexdigest()


def extract_text(filepath: Path) -> str:
    ext = filepath.suffix.lower()
    if ext == ".txt":
        return filepath.read_text(encoding="utf-8", errors="ignore")
    elif ext == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(filepath))
            if reader.is_encrypted:
                try: reader.decrypt("")
                except: pass
        except ImportError:
            import PyPDF2
            reader = PyPDF2.PdfReader(str(filepath))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    elif ext in (".docx", ".doc"):
        import docx
        doc = docx.Document(str(filepath))
        return "\n".join(p.text for p in doc.paragraphs)
    else:
        logger.warning("跳过不支持格式: %s", filepath.name)
        return ""


def generate_summary(text: str, filename: str) -> dict:
    """调用 DeepSeek 生成一句话摘要和标签"""
    from backend.app.services.chat import chat_service
    import asyncio
    prompt = (
        f"为以下文档生成元数据。输出严格JSON。\n"
        f"文档名：{filename}\n内容前段：{text[:3000]}\n"
        f'JSON: {{"one_liner":"一句话摘要（30字内）","tags":["标签1","标签2","标签3"],"category":"论文/案例/政策/数据"}}'
    )
    try:
        result = asyncio.run(chat_service.get_response(
            message=prompt, llm_type="deepseek",
            response_format={"type": "json_object"}))
        raw = result.get("response", "{}")
        return json.loads(raw)
    except Exception as e:
        logger.error("摘要生成失败 %s: %s", filename, e)
        return {"one_liner": "", "tags": [], "category": "论文"}


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list:
    """文本分块"""
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=overlap,
        separators=["\n\n", "\n", "。", ".", "！", "？", " ", ""])
    return splitter.split_text(text)


def build_index(texts: list, index_path: Path):
    """构建 FAISS 索引"""
    from sentence_transformers import SentenceTransformer
    import faiss, numpy as np, pickle

    model_path = ROOT / "backend" / "models" / "distiluse-base-multilingual-cased-v1"
    if model_path.exists():
        model = SentenceTransformer(str(model_path))
    else:
        model = SentenceTransformer("moka-ai/m3e-base")

    embeddings = model.encode(texts, show_progress_bar=True, batch_size=32)
    dim = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(np.array(embeddings, dtype=np.float32))

    faiss.write_index(index, str(index_path))
    logger.info("索引已保存: %s (%d 块)", index_path, len(texts))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    VEC_DIR.mkdir(parents=True, exist_ok=True)

    # 加载现有 metadata
    existing_meta = {}
    if META_FILE.exists():
        existing_meta = json.loads(META_FILE.read_text(encoding="utf-8"))

    files = sorted([f for f in DOC_DIR.iterdir() if f.is_file() and f.suffix.lower() in (".pdf", ".docx", ".doc", ".txt")])
    logger.info("扫描到 %d 个文档", len(files))

    processed = 0
    meta_updated = False

    for fp in files:
        file_hash = compute_file_hash(fp)
        vec_path = VEC_DIR / f"{file_hash}.faiss"

        # 已有索引且非 force 模式则跳过
        if vec_path.exists() and not args.force:
            # 检查 metadata 是否有摘要
            fname = fp.name
            if fname in existing_meta and existing_meta[fname].get("ai_summary"):
                continue

        logger.info("处理: %s", fp.name)

        if args.dry_run:
            logger.info("  [dry-run] 跳过实际处理")
            continue

        text = extract_text(fp)
        if not text or len(text) < 100:
            logger.warning("  文本过短，跳过")
            continue

        # 分块 + 索引
        chunks = chunk_text(text)
        if chunks:
            build_index(chunks, vec_path)

        # AI 摘要
        summary = generate_summary(text, fp.name)

        # 更新 metadata
        fname = fp.name
        if fname not in existing_meta:
            existing_meta[fname] = {}
        existing_meta[fname].update({
            "title": fp.stem,
            "size": fp.stat().st_size,
            "ai_summary": summary.get("one_liner", ""),
            "tags": summary.get("tags", []),
            "category": summary.get("category", "论文"),
            "file_hash": file_hash,
            "processed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        meta_updated = True
        processed += 1
        logger.info("  完成: 摘要=%s, 标签=%s", summary.get("one_liner"), summary.get("tags"))

    if meta_updated and not args.dry_run:
        META_FILE.write_text(json.dumps(existing_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("metadata 已更新: %s", META_FILE)

    logger.info("处理完成: %d 个文档", processed)
    logger.info("下一步：调用 POST /api/v1/chat/build-merged-index 构建合并索引")


if __name__ == "__main__":
    main()
