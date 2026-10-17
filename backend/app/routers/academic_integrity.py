"""学术诚信与证据可靠性检测 - API路由"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from backend.app.dependencies.auth import get_current_user, get_optional_user
from backend.app.models.academic_integrity import (
    AcademicIntegrityAnalyzeRequest,
    AcademicIntegrityResult,
    CheckOptions,
    DataSourceRequest,
    DataSourceResultData,
    PlagiarismRequest,
    PlagiarismResultData,
    ReferenceCheckRequest,
    ReferenceResultData,
    TaskCreateResponse,
    TaskStatusResponse,
)
from backend.app.models.user import User
from backend.app.services.academic_integrity_service import academic_integrity_service
from backend.app.services.plagiarism_service import plagiarism_service
from backend.app.services.reference_auth_service import reference_auth_service
from backend.app.services.data_source_reliability_service import data_source_service

LOGGER = logging.getLogger(__name__)
router = APIRouter()


def _sanitize_text(text: str) -> str:
    """将ASCII双引号替换为中文引号，防止JSON序列化异常"""
    result = list(text)
    is_open = True
    for i, ch in enumerate(result):
        if ch == '"':
            result[i] = '“' if is_open else '”'
            is_open = not is_open
    return ''.join(result)


# =============================================================================
# 综合检测接口
# =============================================================================

@router.post(
    "/pre-review/academic-integrity/analyze",
    response_model=TaskCreateResponse,
    summary="执行学术诚信综合检测",
)
async def analyze_academic_integrity(
    request: AcademicIntegrityAnalyzeRequest,
    current_user: User = Depends(get_current_user),
):
    """一次性执行三个检测模块：相似度检测、参考文献校验、数据来源分析"""
    text = _sanitize_text(request.text) if request.text else request.text

    # 如果提供了 document_id，尝试加载文档
    if not text and request.document_id:
        raise HTTPException(status_code=400, detail="document_id 暂不支持，请直接提供 text 字段。")

    if not text or len(text.strip()) < 100:
        raise HTTPException(
            status_code=400,
            detail="文稿内容过短（少于100字符），请提供完整的论文文本或上传文件。",
        )

    task = academic_integrity_service.create_task(
        user_id=current_user.user_id, title=request.title or "未命名文稿"
    )

    academic_integrity_service.run_analysis_async(
        task=task,
        text=text,
        title=request.title or "",
        options=request.options,
    )

    return TaskCreateResponse(
        task_id=task.id,
        status=task.status,
        message="已开始检测，请稍后查询结果。",
    )


@router.post(
    "/pre-review/academic-integrity/upload",
    response_model=TaskCreateResponse,
    summary="上传文件进行学术诚信检测",
)
async def upload_for_integrity_check(
    file: UploadFile = File(...),
    title: str = Form(""),
    options: str = Form(""),
    current_user: User = Depends(get_current_user),
):
    """上传 TXT / PDF / DOCX 文件进行学术诚信检测"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="请选择文件")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("txt", "pdf", "docx"):
        raise HTTPException(status_code=400, detail="仅支持 .txt / .pdf / .docx 格式")

    content_bytes = await file.read()
    text = ""
    pdf_bytes: Optional[bytes] = None

    if ext == "txt":
        try:
            text = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = content_bytes.decode("gbk")
            except UnicodeDecodeError:
                text = content_bytes.decode("latin-1")
    elif ext == "pdf":
        # PDF 文本提取（fitz 文本层 + 文字层损坏/扫描件的 OCR 兜底）统一放到
        # 后台任务执行，避免大文件或 OCR 长时间阻塞上传请求，并可驱动进度条。
        pdf_bytes = content_bytes
    elif ext == "docx":
        try:
            import io
            import docx
            doc = docx.Document(io.BytesIO(content_bytes))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            text = "\n".join(paragraphs)
        except ImportError:
            raise HTTPException(status_code=500, detail="DOCX解析组件未安装（python-docx）")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"DOCX解析失败: {str(e)}")

    if ext != "pdf" and (not text or len(text.strip()) < 100):
        raise HTTPException(status_code=400, detail="文件内容过短或无法提取有效文本")

    if ext != "pdf":
        text = _sanitize_text(text)

    doc_title = title or (file.filename.rsplit(".", 1)[0] if "." in file.filename else file.filename)

    task = academic_integrity_service.create_task(
        user_id=current_user.user_id, title=doc_title
    )

    # PDF：前端左侧「原始 PDF 对照」使用 pdf.js 友好的规范化版本（整页 CCITT
    # 扫描图会被重建为标准 JPEG，避免 pdf.js 只渲染底部窄条）；OCR / 文本分析
    # 仍使用原始 PDF。无需规范化的普通 PDF 直接存原件，两者为同一文件。
    pdf_path: Optional[str] = None
    if ext == "pdf" and pdf_bytes is not None:
        import asyncio
        from pathlib import Path
        from backend.app.services.pdf_normalizer import normalize_for_viewing

        pdf_dir = Path("backend/data/academic_integrity_pdf")
        pdf_dir.mkdir(parents=True, exist_ok=True)
        view_path = pdf_dir / f"{task.id}.pdf"
        try:
            view_bytes = await asyncio.get_event_loop().run_in_executor(
                None, normalize_for_viewing, pdf_bytes
            )
        except Exception as e:
            LOGGER.warning("pdf normalize failed, fallback to original: %s", e)
            view_bytes = None

        if view_bytes is not None:
            src_path = pdf_dir / f"{task.id}.src.pdf"
            src_path.write_bytes(pdf_bytes)    # 原件：OCR / 分析输入
            view_path.write_bytes(view_bytes)  # 规范化版：前端显示
            pdf_path = str(src_path)
        else:
            view_path.write_bytes(pdf_bytes)
            pdf_path = str(view_path)

    # 解析检测选项：默认只跑「本地指纹查重 + 参考文献核验」，数据来源模块默认关闭
    check_options = CheckOptions()
    try:
        check_options.check_data_sources = False
        if options:
            payload = json.loads(options)
            for _k in (
                "check_plagiarism", "check_references", "check_data_sources",
                "use_web_search", "use_local_knowledge_base", "use_external_academic_apis",
                "language",
            ):
                if _k in payload:
                    setattr(check_options, _k, payload[_k])
    except Exception as e:
        LOGGER.warning("parse upload options failed, use defaults: %s", e)

    academic_integrity_service.run_analysis_async(
        task=task, text=text, title=doc_title, options=check_options,
        pdf_path=pdf_path,
    )

    return TaskCreateResponse(
        task_id=task.id,
        status=task.status,
        message="文件已上传并开始检测。",
    )


# =============================================================================
# 任务状态查询
# =============================================================================

@router.get(
    "/pre-review/academic-integrity/{task_id}",
    response_model=TaskStatusResponse,
    summary="查询检测任务状态和结果",
)
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """查询任务状态和最终检测结果"""
    task = academic_integrity_service.get_task(task_id, current_user.user_id)
    if not task:
        raise HTTPException(status_code=404, detail="未找到该检测任务")

    # 确保 result 是 JSON 安全的
    safe_result = task.result
    if safe_result is not None:
        try:
            safe_result = json.loads(json.dumps(safe_result, ensure_ascii=False, default=str))
        except Exception:
            pass

    # PDF 原文件是否存在（左 PDF 右意见两栏用）
    from pathlib import Path
    pdf_path = Path("backend/data/academic_integrity_pdf") / f"{task.id}.pdf"
    pdf_url = f"/api/v1/pre-review/academic-integrity/pdf/{task.id}" if pdf_path.exists() else ""

    # 手动序列化，绕过 FastAPI 的自动序列化器，确保 JSON 正确
    content = {
        "task_id": task.id,
        "status": task.status,
        "progress": task.progress,
        "current_step": task.current_step,
        "result": safe_result,
        "error_message": task.error_message,
        "pdf_url": pdf_url,
    }
    return JSONResponse(content=json.loads(json.dumps(content, ensure_ascii=False, default=str)))


@router.get(
    "/pre-review/academic-integrity/pdf/{task_id}",
    summary="获取任务原始 PDF",
)
async def get_task_pdf(task_id: str):
    from pathlib import Path
    from fastapi.responses import FileResponse
    pdf_path = Path("backend/data/academic_integrity_pdf") / f"{task_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="该任务没有原始 PDF 文件")
    return FileResponse(path=str(pdf_path), media_type="application/pdf", filename=f"{task_id}.pdf")


# =============================================================================
# 单独模块接口
# =============================================================================

@router.post(
    "/pre-review/academic-integrity/plagiarism",
    response_model=Dict[str, Any],
    summary="单独执行开放来源相似度检测",
)
async def check_plagiarism(
    request: PlagiarismRequest,
    current_user: User = Depends(get_current_user),
):
    """单独执行开放来源相似度检测"""
    if not request.text or len(request.text.strip()) < 100:
        raise HTTPException(status_code=400, detail="文稿内容过短")

    result = plagiarism_service.detect_plagiarism(
        text=request.text,
        use_web_search=request.use_web_search,
        use_local_kb=request.use_local_knowledge_base,
    )
    return result


@router.post(
    "/pre-review/academic-integrity/references",
    response_model=Dict[str, Any],
    summary="单独执行参考文献真实性校验",
)
async def check_references(
    request: ReferenceCheckRequest,
    current_user: User = Depends(get_current_user),
):
    """单独执行参考文献真实性校验"""
    if not request.text or len(request.text.strip()) < 100:
        raise HTTPException(status_code=400, detail="文稿内容过短")

    result = reference_auth_service.check_references(
        text=request.text,
        use_external_apis=request.use_external_apis,
    )
    return result


@router.post(
    "/pre-review/academic-integrity/data-sources",
    response_model=Dict[str, Any],
    summary="单独执行数据来源可靠性分析",
)
async def check_data_sources(
    request: DataSourceRequest,
    current_user: User = Depends(get_current_user),
):
    """单独执行数据来源可靠性分析"""
    if not request.text or len(request.text.strip()) < 6:
        raise HTTPException(status_code=400, detail="文稿内容过短，请至少提供一段完整的来源描述")

    result = data_source_service.analyze_data_sources(
        text=request.text,
        use_web_search=request.use_web_search,
    )
    return result


# =============================================================================
# 公共管理开放证据库
# =============================================================================

from pydantic import BaseModel as PydanticBaseModel


class EvidenceSearchRequest(PydanticBaseModel):
    query: str = ""
    source_type: str = ""
    region: str = ""
    year: Optional[int] = None
    top_k: int = 10


class BuildIndexRequest(PydanticBaseModel):
    source_categories: Optional[List[str]] = None
    max_pages_per_source: int = 100
    respect_robots: bool = True
    dry_run: bool = False


@router.post("/evidence/public-admin/build-index", summary="构建公共管理开放证据索引")
async def build_evidence_index(request: BuildIndexRequest):
    """管理员触发公共管理开放证据索引构建"""
    from backend.app.services.public_admin_evidence_service import build_evidence_index as build_idx
    result = build_idx(
        source_categories=request.source_categories,
        max_pages_per_source=request.max_pages_per_source,
        respect_robots=request.respect_robots,
        dry_run=request.dry_run,
    )
    return result


@router.get("/evidence/public-admin/sources", summary="获取证据源列表")
async def list_evidence_sources():
    """查看当前证据源注册表"""
    from backend.app.services.public_admin_evidence_service import evidence_service
    registry = evidence_service.index.get_source_registry()
    stats = evidence_service.index.get_stats()
    return {"sources": registry, "stats": stats}


@router.post("/evidence/public-admin/search", summary="检索证据库")
async def search_evidence(
    request: EvidenceSearchRequest,
    current_user: User = Depends(get_current_user),
):
    """根据标题、关键词、地区、年份检索证据库"""
    from backend.app.services.public_admin_evidence_service import evidence_service
    results = evidence_service.index.search(
        query=request.query,
        source_type=request.source_type,
        region=request.region,
        year=request.year,
        top_k=request.top_k,
    )
    return {"query": request.query, "results": results, "count": len(results)}


@router.post("/pre-review/academic-integrity/verify-source", summary="验证数据来源")
async def verify_source(
    request: Dict[str, Any],
    current_user: User = Depends(get_current_user),
):
    """单独验证一个数据来源"""
    from backend.app.services.public_admin_evidence_service import evidence_service
    result = evidence_service.verify_government_source(request)
    return result


# =============================================================================
# 公共管理学术元数据增强
# =============================================================================

@router.get("/evidence/public-admin-academic/sources", summary="查看公共管理学术元数据源")
async def list_academic_sources():
    from backend.app.services.public_admin_academic_service import public_admin_academic_service as paas
    return {"sources": paas.get_sources(), "stats": paas.db.stats()}


@router.post("/evidence/public-admin-academic/import", summary="导入公共管理文献题录")
async def import_academic_works(
    records: List[Dict[str, Any]],
    current_user: User = Depends(get_current_user),
):
    from backend.app.services.public_admin_academic_service import public_admin_academic_service as paas
    result = paas.import_works(records)
    return result


@router.post("/evidence/public-admin-academic/search", summary="检索本地公共管理文献库")
async def search_academic_works(
    request: Dict[str, Any],
    current_user: User = Depends(get_current_user),
):
    from backend.app.services.public_admin_academic_service import public_admin_academic_service as paas
    results = paas.search_local(
        title=request.get("title", ""),
        author=request.get("author", ""),
        year=request.get("year"),
        journal=request.get("journal", ""),
        top_k=request.get("top_k", 10),
    )
    return {"results": results, "count": len(results)}


# =============================================================================
# Provider# =============================================================================
# Provider 状态诊断
# =============================================================================

@router.get("/pre-review/academic-integrity/provider-status", summary="诊断所有 provider 状态")
async def get_provider_status():
    """返回所有学术 provider 和搜索服务的配置与状态"""
    import os
    from backend.app.services.external_academic_apis import external_academic_client

    serper_configured = bool(os.getenv("SERPER_API_KEY", ""))

    return {
        "academic_providers": {
            "openalex": {
                "enabled": True,
                "configured": True,
                "requires_api_key": False,
                "available": external_academic_client.openalex.available,
            },
            "crossref": {
                "enabled": True,
                "configured": True,
                "requires_api_key": False,
                "mailto": os.getenv("CROSSREF_MAILTO", ""),
                "available": external_academic_client.crossref.available,
            },
            "semantic_scholar": {
                "enabled": True,
                "configured": bool(os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")),
                "requires_api_key": False,
                "available": external_academic_client.semantic_scholar.available,
            },
            "unpaywall": {
                "enabled": True,
                "configured": bool(os.getenv("UNPAYWALL_EMAIL", "")),
                "requires_email": True,
                "available": external_academic_client.unpaywall.available,
            },
            "wanfang_open": {
                "enabled": bool(os.getenv("WANFANG_APP_KEY", "")),
                "configured": bool(os.getenv("WANFANG_APP_KEY", "")),
                "requires_api_key": True,
            },
            "ncpssd": {
                "enabled": True,
                "configured": bool(os.getenv("NCPSSD_API_KEY", "")),
                "mode": "search_engine_via_serper" if serper_configured else "not_available",
            },
        },
        "web_search": {
            "serper": {
                "enabled": True,
                "configured": serper_configured,
            }
        },
        "evidence_index": {
            "enabled": True,
        },
    }


# =============================================================================
# 报告导出
# =============================================================================

@router.get(
    "/pre-review/academic-integrity/{task_id}/full-text",
    summary="获取任务原始文本",
)
async def get_task_full_text(task_id: str, current_user: User = Depends(get_current_user)):
    task = academic_integrity_service.get_task(task_id, current_user.user_id)
    if not task:
        raise HTTPException(status_code=404, detail="未找到该检测任务")
    text = getattr(task, "original_text", "") or ""
    return {"task_id": task_id, "text": text, "title": task.title}


@router.get(
    "/pre-review/academic-integrity/{task_id}/export",
    summary="导出检测报告",
)
async def export_report(
    task_id: str,
    format: str = "html",
    current_user: User = Depends(get_current_user),
):
    """导出学术诚信检测报告为 HTML 或 TXT"""
    task = academic_integrity_service.get_task(task_id, current_user.user_id)
    if not task:
        raise HTTPException(status_code=404, detail="未找到该检测任务")
    if not task.result:
        raise HTTPException(status_code=400, detail="检测尚未完成")

    result = task.result

    # Helper functions
    ref_status_map = {
        "verified": "已核验", "likely_real": "较可能真实",
        "likely_real_with_mismatch": "可能真实但字段不一致",
        "insufficient_open_metadata": "开放元数据不足，需人工核验",
        "not_found": "多源未检索到", "suspicious": "疑似异常",
        "parse_failed": "解析失败", "check_failed": "校验失败",
    }

    def fmt_pct(v):
        if v is None: return "-"
        try:
            v = float(v)
            return f"{round(v * 100) if v <= 1 else round(v)}%"
        except (ValueError, TypeError):
            return "-"

    def ref_label(item):
        return item.get("status_label") or ref_status_map.get(item.get("status", ""), item.get("status", ""))

    # Count references by status
    ref_items = result.get("references", {}).get("items", []) if result.get("references") else []
    ref_counts = {"verified": 0, "likely_real": 0, "insufficient": 0, "parse_failed": 0, "not_found": 0, "suspicious": 0}
    for it in ref_items:
        s = it.get("status", "")
        if s == "verified": ref_counts["verified"] += 1
        elif s in ("likely_real", "likely_real_with_mismatch"): ref_counts["likely_real"] += 1
        elif s in ("insufficient_open_metadata",): ref_counts["insufficient"] += 1
        elif s in ("parse_failed", "check_failed"): ref_counts["parse_failed"] += 1
        elif s == "not_found": ref_counts["not_found"] += 1
        elif s == "suspicious": ref_counts["suspicious"] += 1

    if format == "txt":
        lines = [
            "=" * 60,
            "山大政管·砺文智审 — 学术诚信与证据可靠性检测报告",
            "=" * 60,
            f"题目：{task.title or '未命名文稿'}",
            f"生成时间：{task.completed_at.isoformat() if task.completed_at else ''}",
            f"报告模板版本：reference_export_v3_split_scores",
            "",
            f"总体评分：{result.get('overall_score', 0):.1f}/100",
            f"总体风险等级：{result.get('overall_risk_level', '')}",
            f"综合摘要：{result.get('summary', '')}",
            "",
        ]
        _pe = result.get("pdf_extract") or {}
        if _pe.get("method") in ("ocr", "hybrid") and _pe.get("ocr_pages"):
            lines.append(f"【文本提取】该 PDF 文字层损坏，已通过 OCR 识别 {_pe.get('ocr_pages')}/{_pe.get('pages')} 页，个别字符可能存在识别误差，请对照原文。")
            lines.append("")
        lines.append("【主要发现】")
        for f in result.get("key_findings", []):
            lines.append(f"  - {f}")

        # Plagiarism
        plag = result.get("plagiarism")
        if plag:
            lines.append(f"\n--- 本地指纹查重（连续13字指纹：本地库纵向 + 内部横向自查重） ---")
            lines.append(f"总重复率：{plag.get('total_similarity', 0) * 100:.1f}%（内部重复 {plag.get('self_similarity', 0)*100:.1f}% / 本地库重合 {plag.get('local_similarity', 0)*100:.1f}%）")
            for seg in plag.get("segments", [])[:10]:
                src = (seg.get("matched_sources") or [{}])[0].get("title", "")
                lines.append(f"  片段{seg.get('index','')}: 相似度{seg.get('similarity_score',0)*100:.0f}% 来源={src}")
                lines.append(f"    原文：{seg.get('text','')[:80]}")
                lines.append(f"    建议：{seg.get('suggestion','')}")

        # References
        refs = result.get("references")
        if refs:
            total = refs.get("total_references", 0)
            lines.append(f"\n--- 参考文献真实性校验 ---")
            lines.append(f"总数：{total} | 已核验：{ref_counts['verified']} | 较可能真实：{ref_counts['likely_real']} | 需人工核验：{ref_counts['insufficient']} | 解析失败：{ref_counts['parse_failed']} | 疑似异常：{ref_counts['suspicious']}")
            for it in ref_items:
                lines.append(f"\n  [{it.get('index','')}] {it.get('raw_reference','')[:100]}")
                lines.append(f"  状态：{ref_label(it)}")
                lines.append(f"  格式完整度：{fmt_pct(it.get('format_score'))}  开放源匹配度：{fmt_pct(it.get('match_confidence'))}  综合：{fmt_pct(it.get('final_confidence'))}")
                lines.append(f"  不一致字段：{', '.join(it.get('mismatch_fields', [])) or '-'}")
                lines.append(f"  风险说明：{it.get('risk_reason', '-')}")
                if it.get('confidence_explanation'):
                    lines.append(f"  置信度说明：{it['confidence_explanation']}")
                lines.append(f"  建议：{it.get('suggestion', '-')}")
                _mlinks = it.get("manual_check_links") or []
                if _mlinks and it.get("status") not in ("verified", "likely_real"):
                    lines.append("  一键人工核验：" + " ｜ ".join(f"{l.get('name')}: {l.get('url')}" for l in _mlinks))

        # Data sources
        ds = result.get("data_sources")
        if ds:
            lines.append(f"\n--- 数据来源可靠性分析 ---")
            lines.append(f"研究类型：{ds.get('research_design_label', '未分类')}")
            lines.append(f"总来源数：{ds.get('total_sources', 0)}  平均可靠性：{ds.get('average_score', 0):.0f}分")
            for it in ds.get("items", [])[:5]:
                lines.append(f"  [{it.get('index','')}] {it.get('source_name','')[:40]} 类型={it.get('source_type','')} 总分={it.get('scores',{}).get('total',0):.0f}")

        lines.append(f"\n{result.get('disclaimer', '')}")
        lines.append(f"\n报告模板版本：reference_export_v3_split_scores")
        return PlainTextResponse(content="\n".join(lines), media_type="text/plain; charset=utf-8")

    # HTML 导出
    risk = result.get("overall_risk_level", "")
    risk_colors = {"low": "#16a34a", "medium": "#d97706", "high": "#dc2626", "critical": "#991b1b"}
    risk_color = risk_colors.get(risk, "#6b7280")

    html_parts = [
        '<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8">',
        '<title>砺文智审 — 学术诚信检测报告</title>',
        '<style>',
        'body{font-family:"Microsoft YaHei",SimSun,sans-serif;max-width:900px;margin:0 auto;padding:20px;color:#333;line-height:1.8}',
        'h1{text-align:center;color:#8a4f00;border-bottom:3px solid #ef7d00;padding-bottom:10px}',
        'h2{color:#d06a00;border-left:4px solid #ef7d00;padding-left:10px;margin-top:25px}',
        '.score{font-size:56px;font-weight:bold;text-align:center}',
        '.card{background:#fefdf9;border:1px solid #eadbbf;border-radius:12px;padding:16px;margin:12px 0}',
        'table{width:100%;border-collapse:collapse;margin:10px 0;font-size:13px}',
        'td,th{border:1px solid #e0d5c0;padding:6px 10px;text-align:left}',
        'th{background:#fef7eb;color:#8a4f00}',
        '.tag{display:inline-block;padding:2px 8px;border-radius:12px;font-size:12px;margin:2px}',
        '.tag-low{background:#dcfce7;color:#166534}',
        '.tag-medium{background:#fef3c7;color:#92400e}',
        '.tag-high{background:#fee2e2;color:#991b1b}',
        '.tag-critical{background:#fecaca;color:#7f1d1d}',
        '.footer{text-align:center;color:#999;font-size:11px;margin-top:40px;border-top:1px solid #eadbbf;padding-top:20px}',
        '.disclaimer{background:#fef8e7;border:1px solid #fcd34d;border-radius:8px;padding:12px;margin:16px 0;font-size:13px;color:#92400e}',
        '.ref-table-wrap{overflow-x:auto;margin:12px 0}',
        '.ref-table{width:100%;border-collapse:collapse;font-size:11px;min-width:1100px}',
        '.ref-table th,.ref-table td{border:1px solid #e0d5c0;padding:6px 8px;vertical-align:top;white-space:normal;word-break:break-word;line-height:1.5}',
        '.ref-table th{background:#fef7eb;color:#8a4f00;font-weight:600;font-size:11px}',
        '.ref-table td{font-size:11px}',
        '.tag-st-ok{color:#166534;font-weight:600} .tag-st-warn{color:#92400e} .tag-st-review{color:#2563eb}',
        '.version{text-align:right;font-size:10px;color:#bbb;margin-top:10px}',
        '</style></head><body>',
        '<h1>山大政管·砺文智审<br>学术诚信与证据可靠性检测报告</h1>',
        f'<p style="text-align:center">题目：{task.title or "未命名文稿"} | {task.completed_at.isoformat() if task.completed_at else ""}</p>',
        f'<div class="score" style="color:{risk_color}">{result.get("overall_score", 0):.0f}<span style="font-size:20px">/100</span></div>',
        f'<p style="text-align:center">综合风险等级：<span class="tag tag-{risk}">{risk}</span></p>',
        f'<div class="card"><strong>综合摘要：</strong>{result.get("summary", "")}</div>',
    ]
    _pe = result.get("pdf_extract") or {}
    if _pe.get("method") in ("ocr", "hybrid") and _pe.get("ocr_pages"):
        html_parts.append(
            f'<div class="disclaimer">该 PDF 文字层损坏，已通过 OCR 光学识别提取 {_pe.get("ocr_pages")}/{_pe.get("pages")} 页文本用于查重与文献核验，'
            f'个别字符可能存在识别误差，关键结论请对照原始 PDF。</div>'
        )
    html_parts.append('<h2>主要发现</h2>')
    for f in result.get("key_findings", []):
        html_parts.append(f'<p>• {f}</p>')

    # 相似度检测
    plag = result.get("plagiarism")
    if plag:
        html_parts.append('<h2>本地指纹查重</h2>')
        html_parts.append(
            f'<p>总重复率：<strong>{plag.get("total_similarity", 0) * 100:.1f}%</strong>'
            f'（内部重复 {plag.get("self_similarity", 0)*100:.1f}% / 本地库重合 {plag.get("local_similarity", 0)*100:.1f}%'
            f'，比对库 {plag.get("corpus_size", 0)} 篇）| 风险：{plag.get("risk_level", "")}</p>'
        )
        html_parts.append(f'<p style="color:#8a6d3b;font-size:12px">{plag.get("check_method", "")}。{plag.get("disclaimer", "")}</p>')
        segs = plag.get("segments", [])
        if segs:
            html_parts.append('<table><tr><th>#</th><th>雷同片段</th><th>相似度</th><th>类型/来源</th><th>判定与建议</th></tr>')
            for s in segs:
                src = (s.get("matched_sources") or [{}])[0]
                src_title = src.get("title", "")
                ctype = "内部重复" if s.get("check_type") == "self" or src.get("source_type") == "self_duplicate" else "本地库雷同"
                html_parts.append(
                    f'<tr><td>{s.get("index", "")}</td>'
                    f'<td>{s.get("text", "")[:120]}</td>'
                    f'<td>{s.get("similarity_score", 0) * 100:.0f}%</td>'
                    f'<td>{ctype}<br><small>{src_title}</small></td>'
                    f'<td>{s.get("reason", "")}<br>{s.get("suggestion", "")}</td></tr>'
                )
            html_parts.append('</table>')

    # 参考文献
    refs = result.get("references")
    if refs:
        total = refs.get("total_references", 0)
        html_parts.append('<h2>参考文献真实性校验</h2>')
        html_parts.append(
            f'<p><strong>总数：{total}</strong> | '
            f'已核验：{ref_counts["verified"]} | '
            f'较可能真实：{ref_counts["likely_real"]} | '
            f'需人工核验：{ref_counts["insufficient"]} | '
            f'解析失败：{ref_counts["parse_failed"]} | '
            f'疑似异常：{ref_counts["suspicious"]}</p>'
        )
        items = refs.get("items", [])
        if items:
            html_parts.append(
                '<div class="ref-table-wrap">'
                '<table class="ref-table">'
                '<colgroup>'
                '<col style="width:4%">'
                '<col style="width:28%">'
                '<col style="width:9%">'
                '<col style="width:6%">'
                '<col style="width:6%">'
                '<col style="width:6%">'
                '<col style="width:8%">'
                '<col style="width:20%">'
                '<col style="width:13%">'
                '</colgroup>'
                '<tr>'
                '<th>#</th><th>原始文献</th><th>状态</th>'
                '<th>格式<br>完整度</th><th>匹配度</th><th>综合</th>'
                '<th>不一致<br>字段</th><th>风险说明</th><th>建议</th>'
                '</tr>'
            )
            for it in items:
                status_label = ref_label(it)
                status = it.get("status", "")
                status_class = "tag-st-ok" if status == "verified" else ("tag-st-warn" if status in ("likely_real", "likely_real_with_mismatch") else "tag-st-review")
                mlinks_html = ""
                _ml = it.get("manual_check_links") or []
                if _ml and status not in ("verified", "likely_real"):
                    mlinks_html = "<br>" + " ".join(
                        f'<a href="{l.get("url","")}" target="_blank" style="display:inline-block;margin:3px 4px 0 0;padding:1px 8px;border:1px solid #8a4f00;border-radius:10px;color:#8a4f00;font-size:10px;text-decoration:none;">{l.get("name","")}</a>'
                        for l in _ml
                    )
                provider_detail = ""
                trace = it.get("provider_trace") or []
                if trace:
                    called = [t["provider"] for t in trace if t.get("called")]
                    if called:
                        provider_detail = f"<br><small>检索源：{', '.join(called)}</small>"
                mismatch = ", ".join(it.get("mismatch_fields", [])) or "-"
                html_parts.append(
                    f'<tr>'
                    f'<td>{it.get("index", "")}</td>'
                    f'<td class="raw-ref">{it.get("raw_reference", "")[:120]}</td>'
                    f'<td class="st-col"><span class="{status_class}">{status_label}</span></td>'
                    f'<td>{fmt_pct(it.get("format_score"))}</td>'
                    f'<td>{fmt_pct(it.get("match_confidence"))}</td>'
                    f'<td>{fmt_pct(it.get("final_confidence"))}</td>'
                    f'<td>{mismatch}</td>'
                    f'<td class="risk-col">{it.get("risk_reason", "")}{provider_detail}</td>'
                    f'<td class="sug-col">{it.get("suggestion", "-")[:120]}{mlinks_html}</td>'
                    f'</tr>'
                )
            html_parts.append('</table>')
            html_parts.append('</div>')

    # 数据来源
    ds = result.get("data_sources")
    if ds:
        html_parts.append('<h2>数据来源可靠性分析</h2>')
        html_parts.append(f'<p>总来源：{ds.get("total_sources", 0)} | 平均可靠性：{ds.get("average_score", 0):.0f}分</p>')
        items = ds.get("items", [])
        if items:
            html_parts.append('<table><tr><th>#</th><th>来源</th><th>类型</th><th>总分</th><th>风险</th><th>建议</th></tr>')
            for it in items:
                html_parts.append(
                    f'<tr><td>{it.get("index", "")}</td>'
                    f'<td>{it.get("source_name", "")[:30]}</td>'
                    f'<td>{it.get("source_type", "")}</td>'
                    f'<td>{it.get("scores", {}).get("total", 0):.0f}</td>'
                    f'<td><span class="tag tag-{it.get("risk_level", "")}">{it.get("risk_level", "")}</span></td>'
                    f'<td>{it.get("suggestion", "")[:80]}</td></tr>'
                )
            html_parts.append('</table>')

    # 优先修改
    fixes = result.get("priority_fixes", [])
    if fixes:
        html_parts.append('<h2>优先修改清单</h2>')
        for fix in fixes:
            p = fix.get("priority", "")
            html_parts.append(
                f'<div class="card"><span class="tag tag-{p}">{p}</span> '
                f'<strong>{fix.get("module", "")}: </strong>'
                f'{fix.get("issue", "")} — {fix.get("action", "")}</div>'
            )

    html_parts.append(f'<div class="disclaimer"><strong>免责声明：</strong>{result.get("disclaimer", "")}</div>')
    html_parts.append('<div class="footer">本报告由 AI 辅助生成 | 山大政管·砺文智审系统</div>')
    html_parts.append('<div class="version">报告模板版本：reference_export_v3_split_scores</div>')
    html_parts.append('</body></html>')

    return HTMLResponse(content="".join(html_parts))
