# -*- coding: utf-8 -*-
"""PDF 规范化（仅供前端「原始 PDF 对照」显示）。

背景：
    部分知网导出的学位论文，每一页都是一张铺满整页的扫描位图，且正文页
    大量使用 ``CCITTFaxDecode``（1 位黑白 G4）编码。前端 pdf.js 对这类整页
    CCITT 图的参数容错较差，会把整页图只画在页面底部约四分之一的窄条里，
    上部整片空白（PyMuPDF / Chrome PDFium 可正常铺满）。

做法：
    检测到整页 CCITT 位图后，用 PyMuPDF 逐页光栅化重建一份 pdf.js 友好的
    PDF——扫描页转标准 JPEG（黑白页转灰度、彩色页保留 RGB），矢量页原样
    复制。重建保持每一页原始 mediabox 尺寸、整页图铺满同一矩形，因此按
    point/百分比计算的荧光笔标注坐标空间与原件完全一致。

注意：
    - OCR、文本提取、审稿、荧光笔坐标定位仍一律使用**原始 PDF**；
    - 仅当确实检测到整页 CCITT 图时才重建，普通 PDF（含卢宵这类矢量/AES
      空密码 PDF）直接返回 ``None``，调用方回退原件，做到零改动、零回归。
"""

from __future__ import annotations

import io
import logging
from typing import Optional, Tuple

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# 整页位图占页面面积达到该比例即视为「整页扫描图」
_FULL_PAGE_AREA = 0.92
_GRAY_DPI = 200   # 黑白扫描页光栅化 DPI（屏幕对照阅读足够清晰）
_COLOR_DPI = 180  # 彩色页光栅化 DPI
_GRAY_QUALITY = 80
_COLOR_QUALITY = 86


def _full_page_image(page: "fitz.Page") -> Optional[Tuple[int, str, object]]:
    """返回该页覆盖整页的主图 (xref, filter, colorspace)，没有则 None。"""
    rect = page.rect
    page_area = float(rect.width * rect.height)
    if page_area <= 0:
        return None
    best = None
    best_area = 0.0
    try:
        images = page.get_images(full=True)
    except Exception:
        return None
    for im in images:
        xref = im[0]
        filt = im[8] if len(im) > 8 else ""
        cs = im[5] if len(im) > 5 else None
        try:
            rects = page.get_image_rects(xref)
        except Exception:
            rects = []
        for r in rects:
            area = float(r.width * r.height) / page_area
            if area > best_area:
                best_area = area
                best = (xref, filt, cs)
    if best is not None and best_area >= _FULL_PAGE_AREA:
        return best
    return None


def needs_normalization(pdf_bytes: bytes) -> bool:
    """仅当文档中存在整页 CCITTFaxDecode 扫描图时才需要规范化。"""
    if not pdf_bytes:
        return False
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:  # 打不开就不处理，交由原有流程报错
        logger.warning("needs_normalization open failed: %s", e)
        return False
    try:
        for page in doc:
            fi = _full_page_image(page)
            if fi and fi[1] == "CCITTFaxDecode":
                return True
        return False
    finally:
        doc.close()


def normalize_for_viewing(pdf_bytes: bytes) -> Optional[bytes]:
    """返回 pdf.js 友好的规范化 PDF 字节；无需规范化时返回 None。"""
    if not needs_normalization(pdf_bytes):
        return None

    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    out = fitz.open()
    gray_n = color_n = vector_n = 0
    try:
        for pno in range(src.page_count):
            page = src[pno]
            rect = page.rect
            new_page = out.new_page(width=rect.width, height=rect.height)
            full_rect = fitz.Rect(0, 0, rect.width, rect.height)
            fi = _full_page_image(page)
            if fi is not None:
                _xref, filt, cs = fi
                is_color = filt == "DCTDecode" and str(cs) in ("DeviceRGB", "3")
                if is_color:
                    pix = page.get_pixmap(
                        matrix=fitz.Matrix(_COLOR_DPI / 72.0, _COLOR_DPI / 72.0),
                        colorspace=fitz.csRGB,
                    )
                    jpg = pix.tobytes("jpg", jpg_quality=_COLOR_QUALITY)
                    color_n += 1
                else:
                    # CCITT / 其它整页位图：灰度光栅化（整页渲染，连带小插图一起保留）
                    pix = page.get_pixmap(
                        matrix=fitz.Matrix(_GRAY_DPI / 72.0, _GRAY_DPI / 72.0),
                        colorspace=fitz.csGRAY,
                    )
                    jpg = pix.tobytes("jpg", jpg_quality=_GRAY_QUALITY)
                    gray_n += 1
                new_page.insert_image(full_rect, stream=jpg, keep_proportion=False)
            else:
                # 矢量 / 混合页：原样复制，保留矢量文字与非整页图
                new_page.show_pdf_page(new_page.rect, src, pno)
                vector_n += 1

        buf = io.BytesIO()
        out.save(buf, deflate=True, garbage=3)
        data = buf.getvalue()
        logger.info(
            "PDF normalized for viewing: %d pages (gray=%d color=%d vector=%d), %.1f MB",
            src.page_count, gray_n, color_n, vector_n, len(data) / 1024.0 / 1024.0,
        )
        return data
    except Exception as e:
        logger.warning("normalize_for_viewing failed, fallback to original: %s", e)
        return None
    finally:
        out.close()
        src.close()
