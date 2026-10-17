"""Evidence graph and deduplication for data source reliability analysis.

Builds evidence bundles, recognizes positive evidence, deduplicates issues,
and generates personalized suggestions.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

LOGGER = logging.getLogger(__name__)

# ============================================================================
# Positive evidence keyword dictionaries
# ============================================================================

SURVEY_POSITIVE_KEYWORDS = {
    "questionnaire_design": ["问卷设计", "问卷编制", "设计问卷", "编制问卷", "调查问卷设计"],
    "questionnaire_implementation": ["问卷实施", "发放问卷", "回收问卷", "问卷调查实施", "问卷发放"],
    "sample_size": ["发放问卷", "回收问卷", "有效问卷", "份问卷", "发放数量", "回收数量"],
    "valid_questionnaires": ["有效问卷", "有效问卷率", "有效回收"],
    "response_rate": ["回收率", "有效问卷率", "有效率"],
    "time_range": ["调查时间", "调研期间", "调查时间范围为", "年在", "月", "日至"],
    "region": ["调研地区", "调查区域", "调查范围为", "选取"],
    "likert_scale": ["李克特", "Likert", "级量表", "分量表"],
    "cronbach_alpha": ["Cronbach", "Alpha", "信度", "克隆巴赫", "信度系数", "信度检验"],
    "kmo_bartlett": ["KMO", "巴特利特", "Bartlett", "球形检验", "效度检验", "效度分析"],
    "spss": ["SPSS", "统计分析软件", "描述性统计"],
    "sample_basic_stats": ["样本基本情况", "描述性统计", "人口统计学", "样本构成"],
    "appendix_questionnaire": ["附录.*调查问卷", "附录.*问卷", "调查问卷.*附录"],
}

INTERVIEW_POSITIVE_KEYWORDS = {
    "interview_outline": ["访谈提纲", "访谈大纲", "半结构化访谈", "深度访谈"],
    "interview_count": ["访谈对象", "位受访", "名受访", "人参与"],
    "interview_time": ["访谈时间", "访谈日期", "访谈进行"],
    "coding_method": ["编码", "NVivo", "主题分析", "扎根理论", "内容分析", "开放式编码"],
    "anonymity": ["匿名", "化名", "隐私保护", "知情同意", "伦理"],
}

APPENDIX_POSITIVE_KEYWORDS = {
    "survey_questionnaire": ["附录", "调查问卷", "问卷"],
    "interview_outline": ["附录", "访谈提纲", "访谈大纲"],
    "evaluation_table": ["附录", "指标评估标准", "评估标准表"],
}

METHOD_CHAPTER_KEYWORDS = [
    "研究方法", "研究设计", "数据来源", "问卷设计与实施", "样本选择",
    "研究方法与数据", "数据收集", "数据分析方法",
]


def _detect_positive_evidence(text: str, source_type: str) -> Tuple[List[str], List[str]]:
    """Detect positive evidence fields in text for a given source type.

    Returns: (positive_fields, evidence_quotes)
    """
    positive_fields = []
    evidence_quotes = []

    if source_type in ("survey",):
        for field, patterns in SURVEY_POSITIVE_KEYWORDS.items():
            for pat in patterns:
                m = re.search(pat, text)
                if m:
                    start = max(0, m.start() - 20)
                    end = min(len(text), m.end() + 60)
                    evidence_quotes.append(text[start:end].strip())
                    if field not in positive_fields:
                        positive_fields.append(field)
                    break

    elif source_type in ("interview",):
        for field, patterns in INTERVIEW_POSITIVE_KEYWORDS.items():
            for pat in patterns:
                m = re.search(pat, text)
                if m:
                    start = max(0, m.start() - 20)
                    end = min(len(text), m.end() + 60)
                    evidence_quotes.append(text[start:end].strip())
                    if field not in positive_fields:
                        positive_fields.append(field)
                    break

    # Appendix evidence (for all types)
    for field, patterns in APPENDIX_POSITIVE_KEYWORDS.items():
        for pat in patterns:
            m = re.search(pat, text)
            if m and m.start() > len(text) * 0.7:  # Appendix is typically near the end
                if f"appendix_{field}" not in positive_fields:
                    positive_fields.append(f"appendix_{field}")
                start = max(0, m.start() - 20)
                end = min(len(text), m.end() + 60)
                evidence_quotes.append(text[start:end].strip())
                break

    return positive_fields, evidence_quotes


def _detect_method_chapter_evidence(text: str) -> Dict[str, Any]:
    """Detect evidence in the methodology section."""
    result: Dict[str, Any] = {
        "has_method_section": False,
        "method_section_keywords": [],
        "has_appendix_reference": False,
    }
    lower_text = text.lower()
    for kw in METHOD_CHAPTER_KEYWORDS:
        if kw.lower() in lower_text:
            result["has_method_section"] = True
            result["method_section_keywords"].append(kw)

    result["has_appendix_reference"] = bool(re.search(r"附录|Appendix", text, re.IGNORECASE))
    return result


def _make_dedupe_key(category: str, source_type: str, missing_fields: List[str]) -> str:
    """Generate a deduplication fingerprint."""
    normalized_missing = sorted(set(missing_fields))
    raw = f"{category}|{source_type}|{'|'.join(normalized_missing)}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


class EvidenceGraph:
    """Evidence graph that bundles evidence and deduplicates issues."""

    def __init__(self):
        self._seen_dedupe_keys: Set[str] = set()
        self._folded_count: Dict[str, int] = {}

    def analyze_sources(
        self, text: str, sources: List[Dict[str, Any]],
        research_design: str = "unknown",
    ) -> Dict[str, Any]:
        """Analyze all data sources with evidence recognition and dedup.

        Returns enriched items, deduplicated issues, and positive evidence summary.
        """
        method_evidence = _detect_method_chapter_evidence(text)
        enriched_items = []
        deduplicated_issues: List[Dict[str, Any]] = []
        all_positive_fields: Set[str] = set()

        for src in sources:
            source_type = src.get("source_type", "unknown")
            source_text = src.get("source_text", "")

            # Detect positive evidence
            positive_fields, quotes = _detect_positive_evidence(source_text, source_type)

            # Detect appendix evidence from full text
            appendix_fields, appendix_quotes = _detect_positive_evidence(text, source_type)
            for f in appendix_fields:
                if f not in positive_fields:
                    positive_fields.append(f)
            for q in appendix_quotes:
                if q not in quotes:
                    quotes.append(q)

            all_positive_fields.update(positive_fields)

            # Generate dedupe key for missing fields
            missing = src.get("missing_fields", [])
            dedupe_key = _make_dedupe_key("data_source", source_type, missing)

            # Evidence quote - use the most relevant one
            best_quote = ""
            if quotes:
                best_quote = max(quotes, key=len)

            enriched_item = {
                **src,
                "positive_fields": positive_fields,
                "evidence_quote": best_quote,
                "dedupe_key": dedupe_key,
            }
            enriched_items.append(enriched_item)

            # Collect deduplicated issues
            if missing:
                if dedupe_key in self._seen_dedupe_keys:
                    self._folded_count[dedupe_key] = self._folded_count.get(dedupe_key, 0) + 1
                    # Skip adding this issue - already covered
                    continue
                self._seen_dedupe_keys.add(dedupe_key)

                issue_type = self._classify_issue(source_type, missing)
                deduplicated_issues.append({
                    "dedupe_key": dedupe_key,
                    "category": "data_sources",
                    "source_type": source_type,
                    "source_type_name": src.get("source_type_name", source_type),
                    "missing_fields": missing[:6],
                    "positive_fields": positive_fields,
                    "evidence_quote": best_quote,
                    "risk_level": src.get("risk_level", "medium"),
                    "suggestion": src.get("suggestion", ""),
                    "issue_type": issue_type,
                })

        # Build summary
        total_folded = sum(self._folded_count.values())
        positive_summary = self._build_positive_summary(list(all_positive_fields), sources)

        return {
            "enriched_items": enriched_items,
            "deduplicated_issues": deduplicated_issues,
            "folded_issue_count": total_folded,
            "positive_fields": sorted(all_positive_fields),
            "positive_summary": positive_summary,
            "method_evidence": method_evidence,
        }

    def _classify_issue(self, source_type: str, missing_fields: List[str]) -> str:
        """Classify the type of issue for deduplication."""
        if source_type == "survey" and "sample_size" in missing_fields:
            return "survey_missing_sample"
        if source_type == "survey" and "reliability_validity" in missing_fields:
            return "survey_missing_reliability"
        if source_type == "survey" and "ethics_statement" in missing_fields:
            return "survey_missing_ethics"
        if source_type == "interview" and "interview_count" in missing_fields:
            return "interview_missing_count"
        if source_type == "interview" and "coding_method" in missing_fields:
            return "interview_missing_coding"
        if "url" in missing_fields and source_type.startswith("government"):
            return "government_missing_url"
        return f"{source_type}_missing_fields"

    def _build_positive_summary(
        self, positive_fields: List[str], sources: List[Dict[str, Any]]
    ) -> str:
        """Build a summary of positive evidence found."""
        if not positive_fields:
            return ""
        parts = []
        field_labels = {
            "questionnaire_design": "问卷设计说明",
            "questionnaire_implementation": "问卷实施说明",
            "sample_size": "样本量说明",
            "valid_questionnaires": "有效问卷数量",
            "response_rate": "问卷回收率",
            "time_range": "调研时间范围",
            "region": "调研地区",
            "likert_scale": "李克特量表",
            "cronbach_alpha": "信度检验(Cronbach's Alpha)",
            "kmo_bartlett": "效度检验(KMO/Bartlett)",
            "spss": "SPSS统计分析",
            "sample_basic_stats": "样本基本情况统计",
            "appendix_questionnaire": "附录·调查问卷",
            "appendix_interview_outline": "附录·访谈提纲",
            "appendix_evaluation_table": "附录·评估标准表",
            "interview_outline": "访谈提纲",
            "interview_count": "访谈对象数量",
            "interview_time": "访谈时间",
            "coding_method": "编码方法",
            "anonymity": "匿名化/伦理说明",
        }
        for field in positive_fields:
            if field in field_labels:
                parts.append(field_labels[field])
            elif field.startswith("appendix_"):
                parts.append(field.replace("appendix_", "附录·").replace("_", " ").title())
        if parts:
            return f"正面证据（已检测到）：{', '.join(parts)}。"
        return ""


def generate_personalized_suggestion(
    src: Dict[str, Any],
    positive_fields: List[str],
    missing_fields: List[str],
    evidence_quote: str,
    risk_level: str,
) -> str:
    """Generate a personalized suggestion using detected evidence.

    This replaces the template-based generate_actionable_suggestion.
    """
    source_type = src.get("source_type", "unknown")
    source_name = src.get("source_name", "该来源")

    # Survey with positive evidence
    if source_type == "survey":
        if positive_fields:
            has_valid_q = "valid_questionnaires" in positive_fields
            has_cronbach = "cronbach_alpha" in positive_fields
            has_kmo = "kmo_bartlett" in positive_fields
            has_appendix = any(f.startswith("appendix_") for f in positive_fields)

            if has_valid_q and has_cronbach and has_kmo:
                suggestion = (
                    "论文已说明问卷发放、回收和信效度检验，数据链条基本成立。"
                    "当前主要问题不是缺少问卷数据，而是建议在正文中进一步补充"
                )
                if "sampling_method" in missing_fields:
                    suggestion += "抽样方式、调研对象筛选标准"
                if "ethics_statement" in missing_fields:
                    suggestion += "和伦理/匿名说明"
                suggestion += "。"
                if has_appendix:
                    suggestion += "系统在附录中检测到调查问卷，可作为正文方法说明的有力补充。"
                return suggestion

        # Survey without evidence
        parts = []
        if "sample_size" in missing_fields:
            parts.append("发放和回收数量")
        if "sampling_method" in missing_fields:
            parts.append("抽样方法和抽样框")
        if "reliability_validity" in missing_fields:
            parts.append("问卷信度和效度检验结果（如Cronbach's Alpha、KMO值）")
        if "ethics_statement" in missing_fields:
            parts.append("问卷调查的伦理说明（匿名化、知情同意）")
        return f"请补充问卷{'、'.join(parts)}。建议在研究方法章节增加'问卷设计与实施'小节，并在附录中附上完整问卷。"

    # Interview with partial evidence
    if source_type == "interview":
        has_appendix_outline = any("appendix" in f and "interview" in f for f in positive_fields)
        has_outline = "interview_outline" in positive_fields

        if (has_appendix_outline or has_outline) and ("interview_count" in missing_fields or "coding_method" in missing_fields):
            suggestion_parts = ["系统在"]
            if has_appendix_outline:
                suggestion_parts.append("附录中识别到访谈提纲")
            elif has_outline:
                suggestion_parts.append("正文中识别到访谈提纲")
            suggestion_parts.append("，说明访谈工具存在。建议补充")
            needs = []
            if "interview_count" in missing_fields:
                needs.append("访谈对象类型和人数")
            if "interview_time" in missing_fields:
                needs.append("访谈时间和地点")
            if "coding_method" in missing_fields:
                needs.append("资料编码方式（如开放编码、主轴编码）")
            if "anonymity" in missing_fields:
                needs.append("匿名化处理和知情同意说明")
            suggestion_parts.append("、".join(needs))
            suggestion_parts.append("，以提升质性资料可追溯性。")
            return "".join(suggestion_parts)

    # Fallback to evidence-quote-driven suggestion
    if evidence_quote and missing_fields:
        return f"检测到原文片段「{evidence_quote[:80]}...」。建议补充：{'、'.join(missing_fields[:5])}。"
    if missing_fields:
        return f"请补充「{source_name}」的以下信息：{'、'.join(missing_fields[:5])}。"
    if risk_level in ("low",):
        return f"「{source_name}」的数据来源信息较为完整，当前无显著风险。"
    return f"请补充「{source_name}」的详细来源信息。"


def apply_survey_scoring_floor(
    positive_fields: List[str],
    has_appendix_survey: bool,
    method_chapter_has_implementation: bool,
    current_total: float,
) -> float:
    """Apply scoring floor for survey research with positive evidence."""
    score = current_total

    # Count quality evidence
    quality_count = sum(1 for f in positive_fields if f in (
        "questionnaire_design", "questionnaire_implementation", "sample_size",
        "valid_questionnaires", "response_rate", "likert_scale",
        "cronbach_alpha", "kmo_bartlett", "spss", "sample_basic_stats",
    ))
    has_survey_appendix = any("appendix" in f and "questionnaire" in f for f in positive_fields)

    # If strong evidence exists, floor at 75
    if quality_count >= 5 and ("cronbach_alpha" in positive_fields or "kmo_bartlett" in positive_fields):
        score = max(score, 75.0)

    # If appendix questionnaire corroborates method chapter, +5 bonus
    if has_survey_appendix and method_chapter_has_implementation:
        score += 5.0

    # If partial evidence, floor at 60
    if quality_count >= 3:
        score = max(score, 60.0)

    return min(100.0, score)


def apply_interview_scoring_cap(
    positive_fields: List[str],
    missing_fields: List[str],
    current_risk: str,
) -> str:
    """Cap interview risk at 'medium' when appendix outline is present but details are missing."""
    has_outline = "interview_outline" in positive_fields or any("appendix" in f and "interview" in f for f in positive_fields)
    if has_outline and current_risk in ("high", "critical"):
        # Interview outline exists, details missing → medium risk, not high/critical
        return "medium"
    return current_risk
