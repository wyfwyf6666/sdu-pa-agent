from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote as urlquote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from backend.app.models.pre_review import PreReviewRequest, PreReviewResponse
from backend.app.services.pre_review import MODULE_NAMES, pre_review_service
from backend.app.dependencies.auth import get_optional_user as get_current_user_optional

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/pre-review", tags=["预审稿"])

ALLOWED_EXTENSIONS = {".docx", ".doc", ".pdf", ".txt", ".wps"}
MAX_FILE_SIZE = 20 * 1024 * 1024


def _extract_docx(file_path: Path) -> str:
    try:
        from docx import Document
        doc = Document(str(file_path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        LOGGER.error("docx extract failed: %s", e)
        raise HTTPException(status_code=500, detail=f"DOCX解析失败：{e}")


def _extract_pdf(file_path: Path) -> str:
    """提取 PDF 文本，统一走 pdf_text_extractor：PyMuPDF 文本层 + 质量检测 + RapidOCR 兜底。

    - 正常文本层 PDF：直接 fitz，速度快、与荧光笔坐标(_locate_pdf_spans)同源；
    - 兼容 AES 空密码加密的知网/期刊导出 PDF；
    - 文字层损坏（私用区乱码、全角拆字）或纯扫描页：自动 OCR，保证审稿拿到正确文本。
    """
    # 1) 统一提取（fitz → 质量检测 → OCR）
    try:
        from backend.app.services.pdf_text_extractor import extract_pdf_text
        res = extract_pdf_text(str(file_path))
        text = res.get("text", "") or ""
        if len(text.strip()) >= 50:
            if res.get("method") in ("ocr", "hybrid"):
                LOGGER.info(
                    "pre_review PDF %s extracted via %s (ocr_pages=%s/%s)",
                    file_path.name, res.get("method"), res.get("ocr_pages"), res.get("pages"),
                )
            return text
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.warning("unified pdf extract failed: %s", e)

    # 2) 兜底：pypdf / PyPDF2（极少数 fitz 无法处理的情形；AES 依赖 pycryptodome）
    text = ""
    for backend in ("pypdf", "PyPDF2"):
        try:
            if backend == "pypdf":
                from pypdf import PdfReader
            else:
                from PyPDF2 import PdfReader
            reader = PdfReader(str(file_path))
            if getattr(reader, "is_encrypted", False):
                unlocked = 0
                for pw in ("", " "):
                    try:
                        unlocked = int(reader.decrypt(pw) or 0)
                    except Exception:
                        unlocked = 0
                    if unlocked:
                        break
                if not unlocked:
                    raise HTTPException(
                        status_code=400,
                        detail="该 PDF 已加密且需要打开密码，无法直接解析；请在 PDF 阅读器中另存为无密码版本，或直接复制正文文字粘贴上传。",
                    )
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            if text.strip():
                break
        except HTTPException:
            raise
        except Exception as e:
            LOGGER.warning("pdf backend %s failed: %s", backend, e)

    if not text.strip():
        raise HTTPException(
            status_code=400,
            detail="未能从该 PDF 提取到有效文字（OCR 也未识别出足够内容）；请确认页面清晰，或直接复制正文文字粘贴到文本框后提交。",
        )
    return text


def _extract_text_file(file_path: Path) -> str:
    for encoding in ("utf-8", "gb18030", "gbk"):
        try:
            return file_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(status_code=400, detail="无法识别文本文件编码，请另存为 UTF-8 后重试")


def _extract_manuscript(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix in (".docx", ".doc", ".wps"):
        return _extract_docx(file_path)
    if suffix == ".pdf":
        return _extract_pdf(file_path)
    if suffix == ".txt":
        return _extract_text_file(file_path)
    raise HTTPException(status_code=400, detail="暂不支持该文件格式")


def _norm_pdf_text(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _locate_pdf_spans(pdf_path: Path, annotations: List[Any]) -> None:
    """用 PyMuPDF 在原始 PDF 上为每条意见定位页码与荧光笔坐标（pt，原点左上）。

    直接改写 annotation.page / annotation.bbox。定位失败的条目保持空值，前端自动回退到纯文字视图。
    """
    try:
        import fitz  # PyMuPDF
    except Exception as e:  # pragma: no cover
        LOGGER.warning("PyMuPDF not available, skip pdf locating: %s", e)
        return
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        LOGGER.warning("fitz open failed: %s", e)
        return
    try:
        if doc.is_encrypted:
            for pw in ("", " "):
                try:
                    if doc.authenticate(pw):
                        break
                except Exception:
                    pass
        n_pages = len(doc)
        if n_pages == 0:
            return
        page_texts = [doc[i].get_text() for i in range(n_pages)]
        norm_pages = [_norm_pdf_text(t) for t in page_texts]
        for ann in annotations:
            q = (getattr(ann, "quote", "") or "").strip()
            if not q:
                continue
            queries = []
            for n in (40, 25, 15):
                frag = q[:n]
                if frag and frag not in queries:
                    queries.append(frag)
            found = False
            for query in queries:
                nq = _norm_pdf_text(query)
                if not nq:
                    continue
                cand = [i for i, np_ in enumerate(norm_pages) if nq in np_]
                if not cand:
                    continue
                for pi in cand[:3]:
                    try:
                        rects = doc[pi].search_for(query)
                    except Exception:
                        rects = []
                    if rects:
                        r = rects[0]
                        ann.page = pi + 1
                        ann.bbox = [round(r.x0, 1), round(r.y0, 1), round(r.x1, 1), round(r.y1, 1)]
                        found = True
                        break
                if found:
                    break
    except Exception as e:
        LOGGER.warning("locate pdf spans failed: %s", e)
    finally:
        try:
            doc.close()
        except Exception:
            pass


def _build_radar_svg(depth_items: List[Dict[str, Any]]) -> str:
    labels = [item.get("label", "") for item in depth_items]
    scores = [float(item.get("score", 0) or 0) for item in depth_items]
    if not labels:
        return ""
    count = len(labels)
    cx = cy = 220
    radius = 150
    points = []
    label_points = []
    for i in range(count):
        angle = -math.pi / 2 + 2 * math.pi * i / count
        r = radius * scores[i] / 100
        points.append(f"{cx + r * math.cos(angle):.1f},{cy + r * math.sin(angle):.1f}")
        lr = radius + 34
        label_points.append((cx + lr * math.cos(angle), cy + lr * math.sin(angle), labels[i], scores[i]))
    grid = []
    for level in (0.2, 0.4, 0.6, 0.8, 1.0):
        gp = []
        for i in range(count):
            angle = -math.pi / 2 + 2 * math.pi * i / count
            gp.append(f"{cx + radius * level * math.cos(angle):.1f},{cy + radius * level * math.sin(angle):.1f}")
        grid.append(f'<polygon points="{" ".join(gp)}" fill="none" stroke="#e5e7eb" stroke-width="1"/>')
    axes = []
    for i in range(count):
        angle = -math.pi / 2 + 2 * math.pi * i / count
        axes.append(f'<line x1="{cx}" y1="{cy}" x2="{cx + radius * math.cos(angle):.1f}" y2="{cy + radius * math.sin(angle):.1f}" stroke="#e5e7eb"/>')
    texts = []
    for x, y, label, score in label_points:
        anchor = "middle"
        if x > cx + 10:
            anchor = "start"
        elif x < cx - 10:
            anchor = "end"
        texts.append(f'<text x="{x:.1f}" y="{y - 4:.1f}" text-anchor="{anchor}" font-size="12" fill="#374151">{label}</text>')
        texts.append(f'<text x="{x:.1f}" y="{y + 11:.1f}" text-anchor="{anchor}" font-size="11" fill="#b91c1c">{score:.0f}</text>')
    return (
        '<svg width="440" height="440" viewBox="0 0 440 440" xmlns="http://www.w3.org/2000/svg">'
        + "".join(grid) + "".join(axes)
        + f'<polygon points="{" ".join(points)}" fill="rgba(185,28,28,0.18)" stroke="#b91c1c" stroke-width="2"/>'
        + "".join(f'<circle cx="{p.split(",")[0]}" cy="{p.split(",")[1]}" r="3" fill="#b91c1c"/>' for p in points)
        + "".join(texts) + "</svg>"
    )


SEVERITY_COLOR = {"严重": "#b91c1c", "一般": "#b45309", "建议": "#1d4ed8", "高": "#b91c1c", "中": "#b45309", "低": "#1d4ed8"}
SEVERITY_BG = {"严重": "#fef2f2", "一般": "#fffbeb", "建议": "#eff6ff", "高": "#fef2f2", "中": "#fffbeb", "低": "#eff6ff"}


# ----------------------------------------------------------------------
# 路由
# ----------------------------------------------------------------------
@router.post("/review", response_model=PreReviewResponse)
async def create_review(body: PreReviewRequest, current_user=Depends(get_current_user_optional)):
    if not body.title.strip() or not body.manuscript.strip():
        raise HTTPException(status_code=400, detail="题目和文稿内容不能为空")
    if len(body.manuscript) > 50000:
        raise HTTPException(status_code=400, detail="文稿内容过长，请控制在5万字以内")
    try:
        import asyncio
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: pre_review_service.run_full_review(body.title.strip(), body.manuscript.strip(), body.modules),
        )
        return response
    except Exception as e:
        LOGGER.exception("Pre-review create failed")
        raise HTTPException(status_code=500, detail=f"预审稿生成失败：{e}")


# 兼容旧路径
@router.post("/create", response_model=PreReviewResponse)
async def create_review_alias(body: PreReviewRequest, current_user=Depends(get_current_user_optional)):
    return await create_review(body, current_user)


@router.get("/history")
async def list_history():
    history = []
    for rid, cached in pre_review_service.review_cache.items():
        overall = cached.get("overall_assessment", {})
        history.append({
            "request_id": rid,
            "title": cached.get("title", ""),
            "document_type": overall.get("document_type", ""),
            "overall_score": overall.get("overall_score", 0),
            "created_at": cached.get("created_at", ""),
        })
    history.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"history": history[:50]}


@router.get("/history/{request_id}", response_model=PreReviewResponse)
async def get_review_by_history(request_id: str):
    cached = pre_review_service.review_cache.get(request_id)
    if not cached:
        raise HTTPException(status_code=404, detail="报告不存在或已过期，请重新提交文稿")
    return cached


@router.get("/modules")
async def list_modules():
    return {"modules": [{"key": k, "name": v} for k, v in MODULE_NAMES.items()]}


@router.get("/pdf/{request_id}")
async def get_review_pdf(request_id: str):
    stored = Path("backend/data/pre_review_pdf") / f"{request_id}.pdf"
    if not stored.exists():
        raise HTTPException(status_code=404, detail="原始 PDF 不存在或已过期，请重新上传文稿")
    return FileResponse(
        path=str(stored),
        media_type="application/pdf",
        filename=stored.name,
    )


@router.get("/{request_id}", response_model=PreReviewResponse)
async def get_review(request_id: str):
    cached = pre_review_service.review_cache.get(request_id)
    if not cached:
        raise HTTPException(status_code=404, detail="报告不存在或已过期，请重新提交文稿")
    return cached


@router.post("/upload", response_model=PreReviewResponse)
async def upload_and_review(file: UploadFile = File(...), current_user=Depends(get_current_user_optional)):
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="仅支持 DOCX、DOC、PDF、TXT、WPS 格式")
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件大小不能超过20MB")

    upload_dir = Path("backend/data/temp/pre_review")
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{Path(filename).name}"
    file_path = upload_dir / safe_name
    file_path.write_bytes(content)

    try:
        title = Path(filename).stem.strip() or "上传文稿"
        import asyncio

        def _prepare_and_review():
            # 提取（含可能的 OCR）与审稿都在线程池执行，避免长耗时 OCR 阻塞事件循环
            manuscript = _extract_manuscript(file_path)
            if not manuscript.strip():
                raise HTTPException(
                    status_code=400,
                    detail="未能从文件中提取到有效文字；若为扫描件请确认页面清晰，或直接复制正文文字粘贴上传。",
                )
            return pre_review_service.run_full_review(title, manuscript, None)

        response = await asyncio.get_event_loop().run_in_executor(None, _prepare_and_review)
        # PDF：前端左侧显示 pdf.js 友好的规范化版本（整页 CCITT 扫描图重建为标准
        # JPEG，避免 pdf.js 只渲染底部窄条）；荧光笔坐标仍在原始 PDF（含文字层）上
        # 定位，规范化版保持相同页面尺寸与坐标空间，标注位置一致。
        if suffix == ".pdf":
            try:
                pdf_dir = Path("backend/data/pre_review_pdf")
                pdf_dir.mkdir(parents=True, exist_ok=True)
                stored = pdf_dir / f"{response.request_id}.pdf"

                def _prepare_view_pdf():
                    from backend.app.services.pdf_normalizer import normalize_for_viewing
                    view_bytes = normalize_for_viewing(content)
                    # bbox 必须在原件（含文字层）上 search；规范化版为整页位图、无文字层
                    _locate_pdf_spans(file_path, response.annotations)
                    return view_bytes

                view_bytes = await asyncio.get_event_loop().run_in_executor(None, _prepare_view_pdf)
                stored.write_bytes(view_bytes if view_bytes is not None else content)
                response.pdf_url = f"/api/v1/pre-review/pdf/{response.request_id}"
                pre_review_service.review_cache[response.request_id] = response.model_dump()
            except Exception as e:
                LOGGER.warning("pdf annotate failed, fallback to text view: %s", e)
                response.pdf_url = ""
        return response
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.exception("Pre-review upload failed")
        raise HTTPException(status_code=500, detail=f"文件预审失败：{e}")
    finally:
        try:
            file_path.unlink(missing_ok=True)
        except Exception:
            pass


class TranslateBody(BaseModel):
    text: str
    direction: str = "auto"


@router.post("/translate")
async def translate(body: TranslateBody):
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="翻译内容不能为空")
    try:
        import asyncio
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: pre_review_service.run_translation(body.text, body.direction)
        )
        return result
    except Exception as e:
        LOGGER.exception("Translation failed")
        raise HTTPException(status_code=500, detail=f"翻译失败：{e}")


class ExportBody(BaseModel):
    request_id: str
    format: str = "html"


@router.post("/export")
async def export_report(body: ExportBody):
    request_id = body.request_id
    fmt = body.format or "html"
    cached = pre_review_service.review_cache.get(request_id)
    if not cached:
        raise HTTPException(status_code=404, detail="报告不存在或已过期，请重新提交文稿")

    overall = cached.get("overall_assessment", {})
    annotations = cached.get("annotations", []) or []
    module_results = cached.get("module_results", [])
    checklist = cached.get("modification_checklist", [])
    risks = cached.get("risk_warnings", [])
    rewrites = cached.get("rewrite_examples", [])
    depth_items: List[Dict[str, Any]] = []
    for mod in module_results:
        if mod.get("module_key") == "depth":
            depth_items = mod.get("items", [])
            break
    radar_svg = _build_radar_svg(depth_items)

    sev_count = {"严重": 0, "一般": 0, "建议": 0}
    for a in annotations:
        s = a.get("severity", "")
        if s in sev_count:
            sev_count[s] += 1

    safe_title = str(cached.get("title", "文稿"))[:20]

    if fmt == "txt" or fmt == "text":
        lines = [
            "=" * 60, "千章预审稿 · 审阅报告", "=" * 60,
            f"题目：{cached.get('title', '')}",
            f"文稿类型：{overall.get('document_type', '')}",
            f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "", "一、总体判断", "-" * 40,
            f"完成度评价：{overall.get('completion_level', '')}",
            f"综合评分：{overall.get('overall_score', 0)}/100",
            "主要优点：",
            *[f"  · {s}" for s in overall.get("strengths", [])],
            "主要短板：",
            *[f"  · {w}" for w in overall.get("weaknesses", [])],
            f"优先修改：{overall.get('priority', '')}",
            "", "二、逐条审阅意见（附原文定位）", "-" * 40,
        ]
        for i, ann in enumerate(annotations, 1):
            para = ann.get("paragraph", -1)
            loc = f"第{para}段" if para and int(para) > 0 else "位置未精确匹配"
            lines.extend([
                f"[{i}] 【{ann.get('severity', '')}｜{ann.get('module_name', '')}｜{loc}】",
                f"    原文摘录：{ann.get('quote', '')}",
                f"    问题：{ann.get('issue', '')}",
                f"    建议：{ann.get('suggestion', '')}", "",
            ])
        lines.extend(["三、修改清单", "-" * 40])
        for i, item in enumerate(checklist, 1):
            lines.append(f"{i}. [{item.get('priority', '')}] {item.get('action', '')}（{item.get('category', '')}）")
            if item.get("detail"):
                lines.append(f"   {item['detail']}")
        if risks:
            lines.extend(["", "四、风险提示", "-" * 40])
            for r in risks:
                lines.append(f"[{r.get('severity', '')}] {r.get('risk_type', '')}：{r.get('description', '')}（{r.get('suggestion', '')}）")
        if rewrites:
            lines.extend(["", "五、学术化改写示例", "-" * 40])
            for i, ex in enumerate(rewrites, 1):
                lines.extend([f"示例{i}：{ex.get('section', '')}", f"  原文：{ex.get('original', '')}", f"  改写：{ex.get('rewritten', '')}", f"  说明：{ex.get('notes', '')}", ""])
        lines.extend(["", "=" * 60, "说明：本报告为AI辅助预审结果，最终学术判断请结合导师意见与学院规范。", "=" * 60])
        filename = f"审阅报告_{safe_title}.txt"
        return Response(
            content="\n".join(lines),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{urlquote(filename)}"},
        )

    # ---------- HTML ----------
    def li(items: List[str]) -> str:
        return "".join(f"<li>{x}</li>" for x in items)

    def render_annotation(ann: Dict[str, Any]) -> str:
        sev = ann.get("severity", "一般")
        color = SEVERITY_COLOR.get(sev, "#374151")
        bg = SEVERITY_BG.get(sev, "#f9fafb")
        para = ann.get("paragraph", -1)
        try:
            loc = f"第 {int(para)} 段" if para and int(para) > 0 else "位置未精确匹配"
        except (TypeError, ValueError):
            loc = "位置未精确匹配"
        quote = ann.get("quote", "")
        issue = ann.get("issue", "")
        suggestion = ann.get("suggestion", "")
        module_name = ann.get("module_name", "")
        matched = ann.get("quote_matched", True)
        quote_note = "" if matched else '<div style="font-size:11px;color:#9ca3af;margin-top:2px;">（摘录与原文未能逐字匹配，已按段落定位）</div>'
        return f"""
        <div style="border:1px solid #e5e7eb;border-left:4px solid {color};border-radius:8px;padding:12px 14px;margin:10px 0;page-break-inside:avoid;background:{bg};">
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px;">
            <span style="background:{color};color:#fff;border-radius:4px;padding:1px 8px;font-size:12px;font-weight:600;">{sev}</span>
            <span style="background:#f3f4f6;color:#374151;border-radius:4px;padding:1px 8px;font-size:12px;">{module_name}</span>
            <span style="color:#6b7280;font-size:12px;">原文定位：{loc}</span>
          </div>
          <div style="background:#fff;border-left:3px solid #d1d5db;padding:6px 10px;margin:6px 0;color:#374151;font-size:13px;">{quote}</div>
          {quote_note}
          <div style="margin:6px 0;font-size:13px;"><b style="color:#111827;">问题：</b>{issue}</div>
          <div style="margin:6px 0;font-size:13px;"><b style="color:#065f46;">修改建议：</b>{suggestion}</div>
        </div>"""

    if annotations:
        severe_html = "".join(render_annotation(a) for a in annotations if a.get("severity") == "严重")
        normal_html = "".join(render_annotation(a) for a in annotations if a.get("severity") == "一般")
        minor_html = "".join(render_annotation(a) for a in annotations if a.get("severity") == "建议")
        annotations_section = f"""
        <h2>二、逐条审阅意见（共 {len(annotations)} 条，均附原文定位）</h2>
        <div style="display:flex;gap:10px;flex-wrap:wrap;margin:8px 0 14px;">
          <span style="background:#fef2f2;color:#b91c1c;border:1px solid #fecaca;border-radius:6px;padding:3px 12px;font-size:13px;">严重 {sev_count['严重']}</span>
          <span style="background:#fffbeb;color:#b45309;border:1px solid #fde68a;border-radius:6px;padding:3px 12px;font-size:13px;">一般 {sev_count['一般']}</span>
          <span style="background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;border-radius:6px;padding:3px 12px;font-size:13px;">建议 {sev_count['建议']}</span>
        </div>
        {('<h3 style="color:#b91c1c;">必须修改</h3>' + severe_html) if severe_html else ''}
        {('<h3 style="color:#b45309;">建议修改</h3>' + normal_html) if normal_html else ''}
        {('<h3 style="color:#1d4ed8;">优化建议</h3>' + minor_html) if minor_html else ''}
        """
    else:
        annotations_section = """
        <h2>二、逐条审阅意见</h2>
        <p style="color:#6b7280;">本次逐段审查未生成带原文定位的意见，请检查文稿内容或重新提交。</p>"""

    modules_html = ""
    for mod in module_results:
        if mod.get("module_key") in ("references", "language", "format", "data_methods"):
            continue  # 已在"逐条审阅意见"中呈现
        modules_html += f'<h2>{mod.get("module_name", "")}</h2>'
        if mod.get("summary"):
            modules_html += f'<p style="color:#6b7280;">{mod["summary"]}</p>'
        items = mod.get("items", [])
        if mod.get("module_key") == "depth" and radar_svg:
            rows = "".join(
                f'<tr><td>{it.get("label", "")}</td><td style="text-align:center;">{it.get("score", "")}</td><td>{it.get("note", "")}</td></tr>'
                for it in items
            )
            modules_html += f'<div style="text-align:center;">{radar_svg}</div><table><tr><th>维度</th><th style="width:60px;">评分</th><th>评分依据（来自原文）</th></tr>{rows}</table>'
        elif items and all(isinstance(it, dict) and "col0" in it for it in items):
            rows = "".join(f'<tr><td>{it.get("col0", "")}</td><td>{it.get("col1", "")}</td><td>{it.get("col2", "")}</td></tr>' for it in items)
            modules_html += f"<table>{rows}</table>"
        elif items and all(isinstance(it, dict) and "level" in it for it in items):
            rows = "".join(f'<tr><td style="width:30%;">{it.get("level", "")}</td><td>{it.get("note", "")}</td></tr>' for it in items)
            modules_html += f"<table>{rows}</table>"
        elif items and all(isinstance(it, dict) and "label" in it for it in items):
            rows = "".join(f'<tr><td>{it.get("label", "")}</td><td style="text-align:center;">{it.get("score", "")}</td><td>{it.get("note", "")}</td></tr>' for it in items)
            modules_html += f"<table>{rows}</table>"
        elif items and all(isinstance(it, dict) and "translated" in it for it in items):
            modules_html += "".join(f'<div style="white-space:pre-wrap;line-height:1.8;">{it.get("translated", "")}</div>' for it in items)
        elif items:
            modules_html += "<ul>" + "".join(f"<li>{it.get('content', '') if isinstance(it, dict) else it}</li>" for it in items) + "</ul>"

    checklist_html = ""
    for item in checklist:
        pri = item.get("priority", "")
        color = SEVERITY_COLOR.get(pri, "#6b7280")
        checklist_html += f'<tr><td style="text-align:center;color:{color};font-weight:600;">{pri}</td><td>{item.get("category", "")}</td><td><b>{item.get("action", "")}</b><div style="color:#6b7280;font-size:12px;">{item.get("detail", "")}</div></td></tr>'

    risks_html = ""
    for r in risks:
        sev = r.get("severity", "")
        color = SEVERITY_COLOR.get(sev, "#6b7280")
        risks_html += f'<div style="border-left:4px solid {color};background:#f9fafb;padding:10px 14px;margin:8px 0;border-radius:4px;"><b>[{sev}] {r.get("risk_type", "")}</b><p>{r.get("description", "")}</p><p style="color:#6b7280;font-size:13px;">应对：{r.get("suggestion", "")}</p></div>'

    rewrites_html = ""
    for i, ex in enumerate(rewrites, 1):
        rewrites_html += f"""
        <div style="border:1px solid #e5e7eb;border-radius:8px;padding:14px;margin:10px 0;">
          <h3 style="margin-top:0;">示例{i}：{ex.get('section', '')}</h3>
          <div style="background:#fef2f2;border-left:3px solid #b91c1c;padding:8px 12px;margin:6px 0;"><b>原文：</b>{ex.get('original', '')}</div>
          <div style="background:#f0fdf4;border-left:3px solid #16a34a;padding:8px 12px;margin:6px 0;"><b>改写：</b>{ex.get('rewritten', '')}</div>
          <p style="color:#6b7280;font-size:13px;">说明：{ex.get('notes', '')}</p>
        </div>"""

    title_text = str(cached.get("title", ""))
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>审阅报告 - {title_text}</title>
<style>
body {{ font-family: 'Microsoft YaHei', sans-serif; max-width: 900px; margin: 0 auto; padding: 30px; color: #1f2937; line-height: 1.7; }}
h1 {{ color: #7A1014; text-align: center; margin-bottom: 4px; }}
h2 {{ color: #7A1014; border-bottom: 2px solid #7A1014; padding-bottom: 6px; margin-top: 32px; }}
h3 {{ margin-top: 20px; }}
table {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 13px; }}
th, td {{ border: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; vertical-align: top; }}
th {{ background: #fef2f2; }}
.cover {{ text-align: center; padding: 40px 0; border-bottom: 2px solid #7A1014; margin-bottom: 24px; }}
.score {{ font-size: 42px; color: #b91c1c; font-weight: bold; }}
.box {{ background: #f9fafb; border-radius: 8px; padding: 14px 18px; margin: 10px 0; }}
@media print {{ .no-print {{ display: none; }} body {{ padding: 10px; }} }}
</style>
</head>
<body>
<div class="no-print" style="text-align:right;margin-bottom:10px;">
  <button onclick="window.print()" style="background:#7A1014;color:#fff;border:none;padding:8px 22px;border-radius:6px;cursor:pointer;font-size:14px;">打印 / 另存为 PDF</button>
</div>
<div class="cover">
  <h1>千章预审稿 · 审阅报告</h1>
  <p style="color:#6b7280;">山东大学政治学与公共管理学院 · AI 辅助预审</p>
  <h2 style="border:none;">{title_text}</h2>
  <p>文稿类型：{overall.get('document_type', '')} ｜ 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
  <div class="score">{overall.get('overall_score', 0)}<span style="font-size:18px;color:#6b7280;">/100</span></div>
  <p style="color:#6b7280;">共定位 <b>{len(annotations)}</b> 条具体意见：严重 {sev_count['严重']} · 一般 {sev_count['一般']} · 建议 {sev_count['建议']}</p>
</div>

<h2>一、总体判断</h2>
<div class="box"><p>{overall.get('completion_level', '')}</p></div>
<h3>主要优点</h3><ul>{li(overall.get('strengths', []))}</ul>
<h3>主要短板</h3><ul>{li(overall.get('weaknesses', []))}</ul>
<div class="box" style="border-left:4px solid #b91c1c;"><b>优先修改：</b>{overall.get('priority', '')}</div>

{annotations_section}

{modules_html}

<h2>修改清单</h2>
<table><tr><th style="width:60px;">优先级</th><th style="width:110px;">分类</th><th>行动项</th></tr>{checklist_html}</table>

{('<h2>风险提示</h2>' + risks_html) if risks_html else ''}
{('<h2>学术化改写示例</h2>' + rewrites_html) if rewrites_html else ''}

<div style="margin-top:40px;padding:16px;background:#f9fafb;border-radius:8px;font-size:12px;color:#6b7280;">
  <p><b>免责声明：</b>本报告由AI基于文稿原文逐段生成，意见均附原文摘录与定位，供修改参考；AI可能存在误判，请结合导师意见、课程要求与学院规范综合判断。</p>
</div>
</body>
</html>"""
    filename = f"审阅报告_{safe_title}.html"
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{urlquote(filename)}"},
    )
