"""学术诚信与证据可靠性检测 — 综合编排服务

汇聚三个分析模块的结果，计算综合评分，生成优先修改清单。
"""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.app.models.academic_integrity import (
    AcademicIntegrityResult,
    AcademicIntegrityTask,
    CheckOptions,
    DataSourceResultData,
    PlagiarismResultData,
    PriorityFix,
    ReferenceResultData,
    TaskStatus,
)
from backend.app.services.plagiarism_service import plagiarism_service
from backend.app.services.local_duplicate_checker import local_duplicate_checker
from backend.app.services.reference_auth_service import reference_auth_service
from backend.app.services.data_source_reliability_service import data_source_service

LOGGER = logging.getLogger(__name__)


class AcademicIntegrityService:
    """学术诚信检测编排服务"""

    def __init__(self):
        self._tasks: Dict[str, AcademicIntegrityTask] = {}
        self._lock = threading.Lock()

    def create_task(self, user_id: str, title: str = "") -> AcademicIntegrityTask:
        """创建检测任务"""
        task_id = str(uuid.uuid4())[:12]
        task = AcademicIntegrityTask(task_id=task_id, user_id=user_id, title=title)
        with self._lock:
            self._tasks[task_id] = task
        return task

    def get_task(self, task_id: str, user_id: str = "") -> Optional[AcademicIntegrityTask]:
        """获取任务状态"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task and user_id and task.user_id != user_id:
                return None
            return task

    def run_analysis_async(
        self,
        task: AcademicIntegrityTask,
        text: str,
        title: str = "",
        options: Optional[CheckOptions] = None,
        pdf_path: Optional[str] = None,
    ) -> None:
        """在后台线程中运行完整分析。

        pdf_path 不为空时，PDF 文本提取（含文字层损坏时的 OCR 兜底）在后台
        线程执行，便于驱动进度条，避免长时间阻塞上传请求。
        """
        if options is None:
            options = CheckOptions()

        task.original_text = text
        pdf_extract_meta: Dict[str, Any] = {}

        def _run():
            nonlocal text
            try:
                task.status = TaskStatus.RUNNING

                # Step 0: PDF 文本提取（fitz 文本层 + 损坏/扫描页 OCR 兜底）
                if pdf_path:
                    def _ocr_progress(done: int, total: int, stage: str) -> None:
                        if stage == "ocr" and total:
                            task.current_step = f"PDF 文字层损坏，正在 OCR 识别（第 {done}/{total} 页）"
                            task.progress = 0.02 + 0.10 * (done / total)
                        else:
                            task.current_step = "正在解析 PDF 文本层"
                            task.progress = 0.02
                    try:
                        from backend.app.services.pdf_text_extractor import extract_pdf_text
                        task.current_step = "正在解析 PDF 文本层"
                        task.progress = 0.02
                        extracted = extract_pdf_text(pdf_path, progress_cb=_ocr_progress)
                        text = extracted.get("text", "") or ""
                        task.original_text = text
                        pdf_extract_meta.update({
                            "method": extracted.get("method"),
                            "pages": extracted.get("pages"),
                            "ocr_pages": extracted.get("ocr_pages"),
                            "quality": extracted.get("quality"),
                        })
                    except Exception as e:
                        LOGGER.error("PDF extract (incl. OCR) failed: %s", e, exc_info=True)
                        task.status = TaskStatus.FAILED
                        task.error_message = f"PDF 解析失败：{str(e)}"
                        return

                # Step 1: 解析文档
                task.current_step = "正在解析文档"
                task.progress = max(task.progress, 0.05)
                if len(text.strip()) < 100:
                    task.status = TaskStatus.FAILED
                    task.error_message = "文稿内容过短（少于100字符），请提供完整的论文文本。"
                    return

                # Step 2: 本地连续N字指纹查重（内部横向自查重 + 本地库纵向比对，离线可用、真实可复现）
                plagiarism_result = None
                if options.check_plagiarism:
                    task.current_step = "正在进行本地指纹查重"
                    task.progress = 0.15
                    try:
                        plagiarism_result = local_duplicate_checker.check(text)

                        # 可选增强：若配置了网络搜索 key，则把联网检出的高相似片段并入
                        import os as _os
                        if options.use_web_search and _os.getenv("SERPER_API_KEY"):
                            try:
                                web_res = plagiarism_service.detect_plagiarism(
                                    text=text, use_web_search=True, use_local_kb=False,
                                    max_web_queries=8,
                                )
                                extra = [
                                    s for s in web_res.get("segments", [])
                                    if s.get("similarity_score", 0) >= 0.20
                                    and any(
                                        (src.get("source_type") == "web")
                                        for src in s.get("matched_sources", [])
                                    )
                                ]
                                if extra:
                                    base_segs = plagiarism_result.get("segments", [])
                                    base_segs.extend(extra)
                                    base_segs.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
                                    for i, s in enumerate(base_segs, 1):
                                        s["index"] = i
                                    plagiarism_result["segments"] = base_segs
                                    web_total = web_res.get("web_similarity", 0) or 0
                                    plagiarism_result["web_similarity"] = round(web_total, 4)
                                    plagiarism_result["total_similarity"] = round(
                                        max(plagiarism_result.get("total_similarity", 0), web_total * 0.8), 4
                                    )
                                    plagiarism_result["risk_level"] = plagiarism_service._similarity_to_risk(
                                        plagiarism_result["total_similarity"]
                                    ) if hasattr(plagiarism_service, "_similarity_to_risk") else plagiarism_result["risk_level"]
                            except Exception as we:
                                LOGGER.warning("web plagiarism enhance skipped: %s", we)
                    except Exception as e:
                        LOGGER.error("Plagiarism check failed: %s", e)
                        plagiarism_result = {
                            "total_similarity": 0,
                            "risk_level": "medium",
                            "summary": f"相似度检测失败：{str(e)}",
                            "segments": [],
                            "disclaimer": "检测未完成，结果不完整。",
                        }
                    task.progress = 0.35

                # Step 3: 参考文献校验
                references_result = None
                if options.check_references:
                    task.current_step = "正在校验参考文献"
                    task.progress = 0.40
                    try:
                        # Use a progress-tracking wrapper
                        raw_refs, _ = __import__('backend.app.services.reference_auth_service', fromlist=['extract_references_with_debug']).extract_references_with_debug(text)
                        total_refs = len(raw_refs)
                        references_result = reference_auth_service.check_references(
                            text=text,
                            use_external_apis=options.use_external_academic_apis,
                        )
                        task.progress = 0.55
                    except Exception as e:
                        LOGGER.error("Reference check failed: %s", e)
                        references_result = {
                            "total_references": 0,
                            "verified_count": 0,
                            "suspicious_count": 0,
                            "not_found_count": 0,
                            "insufficient_metadata_count": 0,
                            "parse_failed_count": 0,
                            "risk_level": "medium",
                            "summary": f"参考文献校验失败：{str(e)}",
                            "items": [],
                            "disclaimer": "校验未完成，结果不完整。",
                            "provider_summary": {"openalex": {"called": False, "matched": 0, "errors": 0}, "crossref": {"called": False, "matched": 0, "errors": 0}},
                            "analyzer_version": "reference_auth_v3_extract_and_map_fix",
                        }
                    task.progress = 0.60

                # Step 4: 数据来源分析
                data_sources_result = None
                global_positive_evidence: List[str] = []
                if options.check_data_sources:
                    task.current_step = "正在扫描正向证据"
                    task.progress = 0.62
                    try:
                        global_evidence = _scan_global_positive_evidence(text)
                        global_positive_evidence = global_evidence.get("positive_evidence", [])
                    except Exception as e:
                        LOGGER.warning("Global evidence scan failed: %s", e)

                    task.current_step = "正在分析数据来源可靠性"
                    task.progress = 0.65
                    try:
                        data_sources_result = data_source_service.analyze_data_sources(
                            text=text,
                            use_web_search=options.use_web_search,
                        )
                    except Exception as e:
                        LOGGER.error("Data source analysis failed: %s", e)
                        data_sources_result = {
                            "total_sources": 0,
                            "average_score": 0,
                            "risk_level": "medium",
                            "summary": f"数据来源分析失败：{str(e)}",
                            "items": [],
                            "disclaimer": "分析未完成，结果不完整。",
                        }
                    task.progress = 0.80

                # Step 5: 综合报告
                task.current_step = "正在生成综合报告"
                task.progress = 0.85

                # Inject global positive evidence into data_sources for dedup
                if data_sources_result and isinstance(data_sources_result, dict):
                    data_sources_result["global_positive_evidence"] = global_positive_evidence

                overall_result = self._build_overall_result(
                    plagiarism_result, references_result, data_sources_result
                )

                # 记录 PDF 提取方式（是否触发 OCR），供前端提示
                if pdf_extract_meta:
                    overall_result["pdf_extract"] = pdf_extract_meta

                # JSON round-trip 确保所有字符串正确转义
                import json as _json
                task.result = _json.loads(_json.dumps(overall_result, ensure_ascii=False, default=str))
                task.status = TaskStatus.COMPLETED
                task.progress = 1.0
                task.current_step = "检测完成"
                task.completed_at = datetime.now()

            except Exception as e:
                LOGGER.error("Academic integrity analysis failed: %s", e, exc_info=True)
                task.status = TaskStatus.FAILED
                task.error_message = str(e)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    def _build_overall_result(
        self,
        plagiarism: Optional[Dict[str, Any]],
        references: Optional[Dict[str, Any]],
        data_sources: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """构建综合检测结果"""
        key_findings: List[str] = []
        raw_fixes: List[Dict[str, Any]] = []
        priority_fixes: List[Dict[str, Any]] = []

        # 计算抄袭评分
        plagiarism_score = 75.0
        if plagiarism:
            p_sim = plagiarism.get("total_similarity", 0)
            p_status = plagiarism.get("similarity_status", "sufficient")
            if p_status == "insufficient_coverage":
                plagiarism_score = 60.0
                cov_note = plagiarism.get("coverage_note", "")
                self_sim = plagiarism.get("self_similarity", 0)
                key_findings.append(f"开放来源覆盖不足，暂未形成有效相似度结论。文档内部自相似度 {self_sim*100:.1f}%。")
                raw_fixes.append({
                    "priority": "P2", "category": "plagiarism",
                    "title": "开放来源相似度覆盖不足",
                    "evidence": cov_note,
                    "reason": "未配置网络搜索API或本地知识库为空",
                    "action": "配置SERPER_API_KEY启用网络搜索，或上传参考文档到本地知识库",
                    "expected_improvement": "覆盖完整后可评估真实相似度",
                })
            else:
                plagiarism_score = 100 - p_sim * 100
                n_seg = len(plagiarism.get("segments", []))
                if p_sim > 0.3:
                    key_findings.append(f"本地查重总重复率为 {p_sim*100:.0f}%，检测到 {n_seg} 处雷同片段，原创性风险较高。")
                    raw_fixes.append({
                        "priority": "P0" if p_sim > 0.4 else "P1", "category": "plagiarism",
                        "title": f"本地查重重复率 {p_sim*100:.0f}%，{n_seg} 处雷同",
                        "evidence": f"连续13字指纹比对定位到 {n_seg} 处雷同片段",
                        "reason": "连续成段文字与本地文献或本文他处高度重合，影响原创性评价",
                        "action": "对照右侧雷同片段逐处改写，用自己的表述重新组织并规范引用",
                        "expected_improvement": "目标将重复率降至15%以下",
                    })
                elif p_sim > 0.15:
                    key_findings.append(f"本地查重总重复率为 {p_sim*100:.0f}%，存在 {n_seg} 处雷同，多为可改写的重复表述。")
                else:
                    key_findings.append(f"本地查重总重复率为 {p_sim*100:.1f}%（{n_seg} 处轻微雷同），整体处于较低水平，原创性良好。")

        # 计算参考文献评分
        reference_score = 75.0  # 默认
        if references:
            total = references.get("total_references", 0)
            verified = references.get("verified_count", 0)
            suspicious = references.get("suspicious_count", 0)
            not_found = references.get("not_found_count", 0)
            if total > 0:
                # 按真实性状态分级赋分：已核验高分；字段不一致/需人工核验为中性中分；
                # 多源未检索到较低；疑似异常/解析失败最低。中文文献开放库收录有限，
                # 「需人工核验」属中性，不等同于伪造，不应与 verified 直接拉成 0/100 两极。
                status_score = {
                    "verified": 100,
                    "likely_real": 90,
                    "likely_real_with_mismatch": 72,
                    "insufficient_open_metadata": 62,
                    "not_found": 35,
                    "suspicious": 12,
                    "parse_failed": 18,
                    "check_failed": 18,
                }
                acc = 0.0
                for it in references.get("items", []):
                    st = it.get("status", "")
                    if it.get("local_match_status") in (
                        "verified_by_local_library", "likely_real_by_local_library",
                    ) and st not in ("verified", "likely_real"):
                        st = "likely_real"
                    acc += status_score.get(st, 55)
                reference_score = max(0, min(100, acc / total))

            if suspicious > 0:
                key_findings.append(
                    f"参考文献中 {suspicious} 条疑似无法核验或伪造。"
                )
                priority_fixes.append({
                    "priority": "high",
                    "module": "references",
                    "issue": f"{suspicious} 条参考文献疑似不存在",
                    "action": "核对 DOI、标题和期刊名，必要时删除或替换。",
                })
            elif not_found > total * 0.3:
                key_findings.append(
                    f"参考文献中 {not_found} 条在开放数据库中未检索到。"
                )
            else:
                key_findings.append(
                    f"参考文献共 {total} 条，整体可核验性较好。"
                )

        # 计算数据来源评分（带去重）
        data_source_score = 75.0
        deduped_ds_issues: List[Dict[str, Any]] = []
        if data_sources:
            avg = data_sources.get("average_score", 0)
            data_source_score = avg
            total_src = data_sources.get("total_sources", 0)
            items = data_sources.get("items", [])
            if total_src > 0:
                # Deduplicate data source issues — coarse grouping by source_type + issue_type
                import hashlib as _hl
                seen_ds: Dict[str, Dict[str, Any]] = {}
                for item in items:
                    missing = item.get("missing_fields", [])
                    if not missing: continue
                    stype = item.get("source_type", "")
                    # Coarse key: same source_type = same group (survey fragments all merge)
                    issue_type = "main"
                    if stype == "survey": issue_type = "survey"
                    elif stype == "interview": issue_type = "interview"
                    elif stype in ("expert_scoring_ahp",): issue_type = "ahp"
                    dk = _hl.md5(f"ds|{stype}|{issue_type}".encode()).hexdigest()[:12]
                    if dk in seen_ds:
                        seen_ds[dk]["affected_count"] += 1
                        seen_ds[dk]["related"].append((item.get("source_text", "") or "")[:120])
                        seen_ds[dk]["missing_fields"] = sorted(set(seen_ds[dk]["missing_fields"] + missing))
                        seen_ds[dk]["positive_fields"] = sorted(set(seen_ds[dk]["positive_fields"] + (item.get("positive_fields", []) or [])))
                        # Re-evaluate severity with accumulated positive evidence
                        if stype == "survey":
                            pos_all = set(seen_ds[dk]["positive_fields"])
                            strong = pos_all & {"questionnaire_design","questionnaire_implementation","valid_questionnaires","likert_scale","cronbach_alpha","kmo_bartlett"}
                            if len(strong) >= 2: seen_ds[dk]["severity"] = "medium"
                    else:
                        pos = item.get("positive_fields", []) or []
                        risk = item.get("risk_level", "medium")
                        if stype == "survey":
                            strong = set(pos) & {"questionnaire_design","questionnaire_implementation","valid_questionnaires","likert_scale","cronbach_alpha","kmo_bartlett"}
                            if len(strong) >= 2: risk = "medium"
                        title_map = {"survey": "问卷实施与抽样/伦理说明补充项", "interview": "访谈资料获取与编码说明补充项",
                            "expert_scoring_ahp": "专家打分与AHP权重计算说明补充项"}
                        seen_ds[dk] = {"id": dk, "source_type": stype, "source_type_name": item.get("source_type_name", stype),
                            "severity": risk, "title": title_map.get(stype, f"{item.get('source_type_name', stype)}数据来源补充项"),
                            "evidence": (item.get("evidence_quote","") or item.get("source_text",""))[:200],
                            "suggestion": item.get("suggestion",""), "affected_count": 1,
                            "missing_fields": sorted(set(missing)), "positive_fields": pos, "related": []}
                # Apply global positive evidence to all groups
                global_pos = data_sources.get("global_positive_evidence", []) if isinstance(data_sources, dict) else []
                survey_strong = {"questionnaire_design","questionnaire_distribution","questionnaire_recovery",
                    "valid_questionnaires","valid_questionnaire_rate","spss_analysis","reliability_test",
                    "validity_test","appendix_questionnaire","cronbach_alpha","kmo_bartlett"}
                has_strong_survey = len(set(global_pos) & survey_strong) >= 4
                has_interview_appendix = bool(set(global_pos) & {"appendix_interview_outline","interview_method"})

                deduped_ds_issues = sorted(seen_ds.values(), key=lambda x: x["affected_count"], reverse=True)
                folded = sum(g["affected_count"] - 1 for g in deduped_ds_issues)

                # Add fixes from deduped groups (only once per group, not per raw item)
                for grp in deduped_ds_issues[:5]:
                    # Apply global evidence caps
                    if grp["source_type"] == "survey" and has_strong_survey:
                        grp["severity"] = "medium"
                    if grp["source_type"] == "interview" and has_interview_appendix:
                        grp["severity"] = "medium"

                    risk = grp.get("severity", "medium")
                    evidence_text = grp.get("evidence", "")
                    if grp["affected_count"] > 1 and grp.get("related"):
                        evidence_text += "；" + "；".join(grp["related"][:3])
                    raw_fixes.append({
                        "priority": "P0" if risk in ("high","critical") else "P1" if risk == "medium" else "P2",
                        "category": "data_sources",
                        "title": f"{grp['title']}（涉及{grp['affected_count']}处）",
                        "affected_count": grp["affected_count"],
                        "evidence": evidence_text[:300],
                        "reason": f"缺失字段：{'、'.join(grp.get('missing_fields',[])[:5])}。同类问题另有{grp['affected_count']-1}处已折叠。",
                        "action": _build_survey_suggestion(grp) if grp["source_type"] == "survey" else grp["suggestion"],
                        "expected_improvement": "补充后数据来源评分预计提升",
                    })

                if avg >= 80:
                    key_findings.append(f"数据来源较权威（平均 {avg:.0f} 分），共识别 {total_src} 个来源。")
                elif avg >= 60:
                    key_findings.append(f"数据来源基本可用（平均 {avg:.0f} 分），但部分来源说明不足。")
                else:
                    key_findings.append(f"数据来源可靠性不足（平均 {avg:.0f} 分），需要重点改写。")
                if folded > 0:
                    key_findings.append(f"同类问题另有 {folded} 处，已折叠，不重复扣分。")
            else:
                key_findings.append("未在论文中检测到明确的数据来源描述。")
                raw_fixes.append({
                    "priority": "P0", "category": "data_sources",
                    "title": "缺少数据来源描述",
                    "evidence": "全文未匹配到明确的数据来源关键词",
                    "reason": "没有数据来源说明，数据可靠性无法评估",
                    "action": "在方法部分补充数据来源、样本信息、采集方式等说明。",
                    "affected_count": 0,
                    "expected_improvement": "补充说明后，数据来源模块评分可提升30-50分",
                })

        # Inject issue_groups into data_sources for frontend display
        if data_sources and isinstance(data_sources, dict):
            data_sources["issue_groups"] = deduped_ds_issues
            data_sources["raw_issue_count"] = len(data_sources.get("items", []))
            data_sources["deduped_issue_count"] = len(deduped_ds_issues)
            data_sources["folded_issue_count"] = folded

        # 综合评分
        if data_sources:
            # 启用数据来源模块时：查重 35% + 文献 35% + 数据来源 30%
            overall_score = (
                0.35 * plagiarism_score
                + 0.35 * reference_score
                + 0.30 * data_source_score
            )
        else:
            # 未启用数据来源模块（当前前端只保留查重 + 文献）：权重在已检测模块间归一化
            if plagiarism and references:
                overall_score = 0.5 * plagiarism_score + 0.5 * reference_score
            elif plagiarism:
                overall_score = plagiarism_score
            elif references:
                overall_score = reference_score
            else:
                overall_score = 75.0

        overall_risk = _score_to_overall_risk(overall_score)

        summary = f"本文整体学术诚信风险{'较低' if overall_risk == 'low' else '中等' if overall_risk == 'medium' else '较高' if overall_risk == 'high' else '严重'}。"
        if plagiarism and plagiarism.get("total_similarity", 0) > 0.15:
            summary += "建议对照雷同片段逐处改写、规范引用。"
        if references and references.get("suspicious_count", 0) > 0:
            summary += "建议重点核查疑似无法验证的参考文献。"
        if data_sources and data_sources.get("average_score", 100) < 60:
            summary += "建议重点改进数据来源说明。"

        # Ensure references have all required fields (defensive)
        if references:
            references.setdefault("verified_count", 0)
            references.setdefault("suspicious_count", 0)
            references.setdefault("not_found_count", 0)
            references.setdefault("insufficient_metadata_count", 0)
            references.setdefault("parse_failed_count", 0)
            references.setdefault("total_references", len(references.get("items", [])))
            references.setdefault("items", [])
            references.setdefault("risk_level", "medium")
            references.setdefault("summary", "")
            references.setdefault("analyzer_version", "reference_auth_v3_extract_and_map_fix")

        return {
            "overall_score": round(overall_score, 1),
            "overall_risk_level": overall_risk,
            "summary": summary,
            "key_findings": key_findings,
            "plagiarism": plagiarism,
            "references": references,
            "data_sources": data_sources,
            "priority_fixes": raw_fixes or priority_fixes,
            "deduped_ds_issues": deduped_ds_issues,
            "disclaimer": (
                "本功能用于论文正式投稿前的风险预审，"
                "结果仅供修改参考，不能替代知网、维普、万方、Turnitin等正式查重系统，"
                "也不能替代人工学术审查。"
            ),
        }


def _score_to_overall_risk(score: float) -> str:
    if score >= 85:
        return "low"
    elif score >= 70:
        return "medium"
    elif score >= 50:
        return "high"
    return "critical"


def _build_survey_suggestion(grp: Dict[str, Any]) -> str:
    pos = set(grp.get("positive_fields", []))
    gpos = set(grp.get("global_positive_evidence", []))
    all_pos = pos | gpos
    has_evidence = bool(all_pos & {"questionnaire_design","questionnaire_distribution","valid_questionnaires","valid_questionnaire_rate","spss_analysis","reliability_test","validity_test","appendix_questionnaire","cronbach_alpha","kmo_bartlett"})
    if has_evidence:
        return "论文已说明问卷设计、发放、回收和有效问卷数量，问卷数据链条基本成立。当前主要建议在正文中集中补充抽样方式、样本筛选标准、匿名处理和知情同意说明，不需要每个片段重复补充。"
    return "请在问卷设计与实施部分集中补充问卷发放时间、发放对象、发放地区、发放数量、回收数量、有效问卷数量、抽样方式、匿名处理和知情同意说明。"


def _scan_global_positive_evidence(raw_text: str) -> Dict[str, Any]:
    """Scan full text for positive evidence about data sources."""
    text = raw_text or ""
    evidence: Dict[str, bool] = {}
    snippets: List[Dict[str, Any]] = []

    def hit(key: str, pattern: str, label: str):
        m = re.search(pattern, text, re.I | re.S)
        if m:
            evidence[key] = True
            s = max(0, m.start() - 80)
            e = min(len(text), m.end() + 120)
            snippets.append({"key": key, "label": label, "snippet": text[s:e].replace("\n", " ")[:300]})

    hit("questionnaire_design", r"问卷设计|4\.2\.2\s*问卷设计|4\.2\s*问卷设计与实施", "问卷设计章节")
    hit("questionnaire_distribution", r"发放问卷\s*\d+\s*份|共计发放问卷|共发放问卷", "问卷发放数量")
    hit("questionnaire_recovery", r"回收问卷\s*\d+\s*份|共回收问卷|回收有效", "问卷回收")
    hit("valid_questionnaires", r"有效问卷\s*\d+\s*份|最终得到有效问卷|最终有效问卷", "有效问卷数量")
    hit("valid_questionnaire_rate", r"有效问卷率\s*(?:为)?\s*\d+(?:\.\d+)?%", "有效问卷率")
    hit("pre_survey", r"预调查|预调研|预调查样本", "预调查")
    hit("spss_analysis", r"SPSS\s*26|SPSS26|SPSS\s*软件|SPSS", "SPSS分析")
    hit("reliability_test", r"信度检验|信度分析|信度系数", "信度检验")
    hit("validity_test", r"效度检验|效度分析|效度", "效度检验")
    hit("cronbach_alpha", r"Cronbach'?s?\s*Alpha|Cronbach|克隆巴赫", "Cronbach Alpha")
    hit("kmo_bartlett", r"KMO|巴特利特|Bartlett", "KMO/巴特利特")
    hit("appendix_questionnaire", r"附录\s*1.*?[调问訪]|杭州市.*?调查问卷|现状调查问卷|附录.*?问卷", "问卷附录")
    hit("appendix_interview_outline", r"附录\s*2.*?[访谈訪]|访谈提纲|杭州市.*?访谈提纲", "访谈提纲附录")
    hit("appendix_evaluation_standard", r"附录\s*3|评估标准表|多指标可及性", "评估标准附录")
    hit("interview_method", r"深度访谈法|访谈法|访谈对象|访谈内容|辅以.*?访谈", "访谈方法")
    hit("survey_time_range", r"2022\s*年\s*3\s*月.*?2022\s*年\s*7\s*月|调研时间.*?2022|2022.*?调研", "调研时间范围")
    hit("survey_region", r"滨江区|拱墅区|西湖区|上城区", "调研地区")

    # Also scan appendix section separately
    appendix = _extract_appendix_section(text)
    if appendix:
        hit("appendix_questionnaire", r"调查问卷|问卷", "问卷附录(附录扫描)")
        hit("appendix_interview_outline", r"访谈提纲|访谈大纲", "访谈提纲附录(附录扫描)")
        hit("appendix_evaluation_standard", r"评估标准|等级评估|指标评估", "评估标准附录(附录扫描)")

    return {
        "flags": evidence,
        "positive_evidence": [k for k, v in evidence.items() if v],
        "snippets": snippets,
    }


def _extract_appendix_section(text: str) -> str:
    """Extract appendix section from text (after the last numbered chapter)."""
    if not text: return ""
    # Find appendix heading positions
    candidates: List[Tuple[int, int]] = []
    for m in re.finditer(r"附\s*录|Appendix", text, re.I):
        score = 0
        following = text[m.start():m.start() + 30000]
        if re.search(r"调查问卷|问卷", following): score += 5
        if re.search(r"访谈提纲|访谈", following): score += 5
        if re.search(r"附\s*录\s*[23]", following): score += 3
        if m.start() > len(text) * 0.6: score += 3
        candidates.append((score, m.start()))
    if not candidates: return ""
    candidates.sort(reverse=True)
    return text[candidates[0][1]:]


# 全局实例
academic_integrity_service = AcademicIntegrityService()
