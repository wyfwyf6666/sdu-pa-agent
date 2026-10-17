"""统一 PDF 文本提取：PyMuPDF(fitz) 文本层 + 质量检测 + RapidOCR 兜底。

适配三类 PDF：
1. 文本层正常的 PDF：直接用 fitz，速度快、可复制、可检索；
2. 文本层损坏的 PDF（知网/学位论文常见：字体 ToUnicode 映射缺失，
   fitz 提取出私用区乱码 / “(cid:xxx)” / 全角拆字）：自动对问题页 OCR；
3. 扫描图片版 PDF（几乎无文本层）：整份 OCR。

左栏“原页 PDF 渲染”始终基于原始页面，与本模块互不影响；本模块只负责
为查重 / 参考文献核验 / 审稿提供**正确的分析文本**。
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Optional, Union

LOGGER = logging.getLogger(__name__)

# 私用区：BMP + 补充平面
def _is_pua(ch: str) -> bool:
    cp = ord(ch)
    return (0xE000 <= cp <= 0xF8FF) or (0xF0000 <= cp <= 0xFFFFD) or (0x100000 <= cp <= 0x10FFFD)


def _page_metrics(text: str) -> dict:
    """统计单页文本质量。"""
    t = text or ""
    visible = re.sub(r"\s", "", t)
    n = len(visible)
    cjk = sum(1 for c in visible if "一" <= c <= "鿿")
    pua = sum(1 for c in visible if _is_pua(c))
    cid = t.count("(cid:")
    repl = t.count("�") + t.count("□")
    # 全角数字 / 全角拉丁字母（文本层损坏的典型表现：Ｔｈｅｓｉｓ、Ｃ９３）
    fw = sum(
        1 for c in visible
        if (0xFF10 <= ord(c) <= 0xFF19) or (0xFF21 <= ord(c) <= 0xFF3A) or (0xFF41 <= ord(c) <= 0xFF5A)
    )
    hw = len(re.findall(r"[A-Za-z0-9]", t))
    fw_ratio = fw / max(1, fw + hw)
    pua_ratio = pua / max(1, n)

    bad = False
    if n >= 20:
        if pua_ratio > 0.03:
            bad = True
        elif cid >= 3 and cid / max(1, n) > 0.01:
            bad = True
        elif repl / max(1, n) > 0.02:
            bad = True
        elif fw >= 20 and fw_ratio > 0.6:
            bad = True
    return {
        "n": n, "cjk": cjk, "pua": pua, "cid": cid, "repl": repl,
        "fw": fw, "hw": hw, "fw_ratio": round(fw_ratio, 3),
        "pua_ratio": round(pua_ratio, 4), "bad": bad,
    }


_ocr_engine = None


def _get_ocr():
    """懒加载 RapidOCR（wheel 自带中英文 ONNX 模型，无需系统级安装）。

    限制 ONNX Runtime 的推理线程数，给 Web 服务事件循环和系统留出 CPU 核心，
    避免整本 PDF OCR 时占满所有核导致接口与其他请求长时间无响应。
    """
    global _ocr_engine
    if _ocr_engine is None:
        import os
        from rapidocr_onnxruntime import RapidOCR
        cpu = os.cpu_count() or 4
        threads = max(1, min(4, cpu - 2))
        try:
            _ocr_engine = RapidOCR(intra_op_num_threads=threads, inter_op_num_threads=1)
        except Exception:
            try:
                _ocr_engine = RapidOCR(intra_op_num_threads=threads)
            except Exception:
                _ocr_engine = RapidOCR()
    return _ocr_engine


def _ocr_page(page, dpi: int = 200) -> str:
    """把一页渲染成图片并 OCR。"""
    import os
    import tempfile

    pix = page.get_pixmap(dpi=dpi)
    engine = _get_ocr()

    # 优先内存解码（opencv 随 rapidocr 安装）
    try:
        import cv2
        import numpy as np
        img = cv2.imdecode(np.frombuffer(pix.tobytes("png"), np.uint8), cv2.IMREAD_COLOR)
        result, _ = engine(img)
        if result:
            return "\n".join(item[1] for item in result if len(item) > 1 and item[1])
        return ""
    except Exception:
        pass

    # 回落：临时文件
    fd, tmp = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        pix.save(tmp)
        result, _ = engine(tmp)
        if result:
            return "\n".join(item[1] for item in result if len(item) > 1 and item[1])
        return ""
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def extract_pdf_text(
    source: Union[bytes, bytearray, str],
    enable_ocr: bool = True,
    dpi: int = 200,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
) -> dict:
    """提取 PDF 全文。

    source: PDF 字节流或文件路径。
    progress_cb(done, total, stage): 仅 OCR 阶段回调，便于更新任务进度条。
    返回 {text, method(fitz/hybrid/ocr/failed), pages, ocr_pages, quality}。
    """
    import fitz  # PyMuPDF

    if isinstance(source, (bytes, bytearray)):
        doc = fitz.open(stream=bytes(source), filetype="pdf")
    else:
        doc = fitz.open(str(source))

    if doc.is_encrypted:
        for pw in ("", " ", "123456", "password"):
            try:
                if doc.authenticate(pw):
                    break
            except Exception:
                pass

    n_pages = doc.page_count
    page_texts: list[str] = []
    metrics: list[dict] = []
    for page in doc:
        t = page.get_text("text") or ""
        page_texts.append(t)
        metrics.append(_page_metrics(t))

    total_n = sum(m["n"] for m in metrics)
    valid = [m for m in metrics if m["n"] >= 20]
    bad_valid = sum(1 for m in valid if m["bad"])
    global_pua = sum(m["pua"] for m in metrics) / max(1, total_n)
    fw_all = sum(m["fw"] for m in metrics)
    hw_all = sum(m["hw"] for m in metrics)
    fw_ratio_all = fw_all / max(1, fw_all + hw_all)
    empty_pages = sum(1 for m in metrics if m["n"] < 20)

    # 全局判定是否需要 OCR
    need_ocr = enable_ocr and (
        (valid and bad_valid / len(valid) > 0.3)
        or (n_pages >= 3 and total_n / max(1, n_pages) < 80)  # 扫描件：每页几乎无文字
        or global_pua > 0.02
        or (fw_all >= 40 and fw_ratio_all > 0.5)
    )

    method = "fitz"
    ocr_pages = 0
    ocr_failed_pages = 0

    if need_ocr:
        # 对“乱码页 + 空白(图片)页”OCR，正常页保留 fitz
        targets = [i for i, m in enumerate(metrics) if m["bad"] or m["n"] < 20]
        if not targets:
            targets = list(range(n_pages))
        method = "hybrid"
        if progress_cb:
            progress_cb(0, len(targets), "ocr_start")
        for k, i in enumerate(targets):
            try:
                ot = _ocr_page(doc[i], dpi=dpi)
                if ot and ot.strip():
                    page_texts[i] = ot.strip()
                    ocr_pages += 1
                else:
                    ocr_failed_pages += 1
            except Exception as e:
                ocr_failed_pages += 1
                LOGGER.warning("OCR page %d failed: %s", i + 1, e)
            if progress_cb:
                progress_cb(k + 1, len(targets), "ocr")
        # 绝大多数页面来自 OCR 则标记为纯 OCR（扫描件）
        if ocr_pages >= 0.8 * n_pages:
            method = "ocr"

    doc.close()

    text = "\n".join(t.strip() for t in page_texts if t and t.strip())

    quality = {
        "pages": n_pages,
        "total_chars": total_n,
        "bad_pages": bad_valid,
        "empty_pages": empty_pages,
        "global_pua_ratio": round(global_pua, 4),
        "fullwidth_latin_ratio": round(fw_ratio_all, 3),
        "ocr_pages": ocr_pages,
        "ocr_failed_pages": ocr_failed_pages,
    }
    if len(text.strip()) < 50:
        method = "failed"
    return {"text": text, "method": method, "pages": n_pages, "ocr_pages": ocr_pages, "quality": quality}
