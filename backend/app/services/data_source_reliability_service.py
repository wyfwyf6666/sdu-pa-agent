"""数据来源可靠性分析服务 — 公共管理场景优化版

支持19种数据来源类型的识别、6维度加权评分、强制actionable建议生成。
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

LOGGER = logging.getLogger(__name__)

# ============================================================================
# 公共管理关键词词典
# ============================================================================

PUBLIC_ADMIN_KEYWORDS = [
    "政府公开", "政府信息公开", "政务公开", "政策文件", "政策文本",
    "条例", "办法", "规章", "实施意见", "通知", "规划",
    "统计年鉴", "统计公报", "国家统计局", "地方统计局",
    "民政局", "人社局", "住建局", "发改委", "财政局", "教育局",
    "卫健委", "医保局", "市场监管局", "政务服务平台", "公共服务平台",
    "社区治理", "基层治理", "养老服务", "智慧养老", "居家养老",
    "社会保障", "城市治理", "数字政府", "公共数据开放",
    "问卷调查", "访谈资料", "案例研究", "文本分析",
    "政策量化", "政策工具", "扎根理论", "内容分析",
    "人民政府", "gov.cn", "信息公开", "人大", "司法",
    "国务院", "民政部", "人社部", "住建部", "生态环境",
    "交通运输", "水利", "农业农村", "商务部", "文化和旅游",
    "退役军人", "应急管理", "审计署", "国资委", "海关总署",
    "税务总局", "广电总局", "体育总局", "统计局数据",
    "北大法宝", "政府公报", "地方志", "白皮书",
]

# ============================================================================
# 来源类型映射
# ============================================================================

SOURCE_TYPE_NAMES: Dict[str, str] = {
    "central_government_website": "中央政府官网",
    "local_government_website": "地方政府官网",
    "government_information_disclosure": "政府信息公开平台",
    "government_policy_document": "政府政策文件",
    "local_regulation": "地方性法规/条例/办法",
    "statistical_bureau_data": "统计局数据",
    "statistical_yearbook": "统计年鉴",
    "public_data_platform": "公共数据开放平台",
    "official_report": "政府部门正式报告",
    "academic_literature_synthesis": "学术文献整理",
    "academic_database": "学术数据库",
    "survey": "问卷调查",
    "interview": "访谈资料",
    "case_material": "案例材料",
    "media_report": "新闻媒体报道",
    "enterprise_or_industry_report": "企业/行业/智库报告",
    "platform_data": "平台数据",
    "web_crawling": "网络爬虫数据",
    "unknown": "来源不明",
}

# ============================================================================
# 识别规则
# ============================================================================

def _make_pattern(regex: str) -> re.Pattern:
    return re.compile(regex)

# (pattern, source_type, priority) — priority越高越优先匹配
IDENTIFICATION_RULES: List[Tuple[re.Pattern, str, int]] = [
    # ===== 政府/官方类 =====
    (_make_pattern(r"(?:国务院|中共中央|全国人大|全国人大常委会|中央人民政府)"), "central_government_website", 100),
    (_make_pattern(r"(?:民政部|人社部|住建部|发改委|财政部|教育部|卫健委|医保局|市场监管总局|生态环境部|交通运输部|水利部|农业农村部|商务部|退役军人事务部|应急管理部|审计署|国资委|海关总署|税务总局|国家统计局|体育总局|广电总局)(?:官网|网站|数据|信息|公开|统计|公报)"), "central_government_website", 98),
    (_make_pattern(r"(?:人民政府|gov\.cn|政府网|政府门户)(?:站)?(?:\s*(?:网站|官网|门户|信息|公开|数据))?"), "local_government_website", 95),
    (_make_pattern(r"(?:政府信息|政务)公开(?:平台|网站|专栏|目录)"), "government_information_disclosure", 93),
    (_make_pattern(r"(?:地方|政府|行政)(?:规章|条例|办法|细则|规定|实施意见|通知|规划|方案|意见|公告|决定|命令)"), "local_regulation", 96),
    (_make_pattern(r"(?:国务院|中央|国家|全国)(?:条例|办法|规定|通知|意见|规划|方案|决定|公告)"), "government_policy_document", 92),
    (_make_pattern(r"《[^》]{2,60}?(?:条例|办法|规定|细则|实施意见|通知|规划|方案|意见)》"), "government_policy_document", 94),
    (_make_pattern(r"(?:政策|法规|条例|规章)(?:文本|文件|内容)(?:来源于|选自|来自)"), "government_policy_document", 86),
    # ===== 无书名号的政策文件 / 条例识别 =====
    (_make_pattern(r"(?:[一-鿿]{2,20}(?:市|省|区|县))(?:居家|养老|医疗|教育|环保|交通|城建|物业|垃圾分类|数字经济|营商环境|人才).{0,10}(?:条例|办法|规定|细则)"), "local_regulation", 91),
    (_make_pattern(r"(?:[一-鿿]{2,8}(?:市|省|区|县))(?:.{0,5}(?:条例|办法|规定|细则|规章))"), "local_regulation", 89),
    (_make_pattern(r"(?:居家|养老|医疗|教育|环保|交通|城建|物业|垃圾分类|数字经济|营商环境).{0,10}(?:条例|办法|规定|细则)"), "local_regulation", 87),
    # ===== 统计类 =====
    (_make_pattern(r"(?:统计年鉴|统计公报|国民经济和社会发展统计)"), "statistical_yearbook", 85),
    (_make_pattern(r"(?:国家统计局|统计局|地方统计局)(?:数据|统计|发布)"), "statistical_bureau_data", 83),
    (_make_pattern(r"(?:统计局|统计部门|统计机构)(?:\d{4})?(?:年)?(?:.{0,10}(?:数据|统计|资料))?"), "statistical_bureau_data", 80),
    (_make_pattern(r"(?:统计局|统计年鉴).{0,20}(?:年)?(?:数据|统计|资料|年鉴)"), "statistical_bureau_data", 79),
    # ===== 学术文献类 =====
    (_make_pattern(r"(?:根据|参考|依据)(?:学者|已有研究|现有文献|既有研究|前人研究|相关文献|学术界).{0,25}(?:整理|建立|构建|编制|提出|归纳|总结)"), "academic_literature_synthesis", 78),
    (_make_pattern(r"(?:学者|作者)(?:根据|基于|参照|采用|借鉴|引用).{0,15}(?:指标|体系|框架|模型|量表|分类|维度)"), "academic_literature_synthesis", 76),
    (_make_pattern(r"(?:文献|已有研究)(?:整理|归纳|梳理|总结)(?:所得|形成|获得|得到)"), "academic_literature_synthesis", 75),
    (_make_pattern(r"(?:CNKI|知网|万方|维普|Web\s*of\s*Science|Scopus|CSSCI|北大核心|PubMed|中国知网|哲社文献)"), "academic_database", 70),
    # ===== 调查/访谈类 =====
    (_make_pattern(r"(?:问卷|调查问卷)(?:调查|发放|回收|设计|编制|采用)"), "survey", 65),
    (_make_pattern(r"(?:发放|回收|共发放|共回收|有效问卷)\s*\d+\s*(?:份|张|套)"), "survey", 63),
    (_make_pattern(r"(?:半结构化|深度|结构化)?(?:访谈|座谈|焦点小组)(?:.{0,10}(?:对象|资料|数据|记录|收集))?"), "interview", 62),
    (_make_pattern(r"(?:访谈|座谈|深度访谈)(?:\d+)?(?:人|位|名|次)"), "interview", 60),
    (_make_pattern(r"(?:访谈|深度访谈|半结构化访谈)(?:收集|获取|采集|资料)"), "interview", 58),
    # ===== 平台/数据库类 =====
    (_make_pattern(r"(?:公共数据开放平台|数据开放平台|开放数据平台)"), "public_data_platform", 58),
    (_make_pattern(r"(?:政务服务平台|政务平台|政务系统|一网通办|政务服务网)"), "platform_data", 55),
    (_make_pattern(r"(?:案例|个案)(?:资料|数据|来源|选取|选择|材料)"), "case_material", 53),
    # ===== 报告/媒体类 =====
    (_make_pattern(r"(?:政府|部门|官方)(?:报告|公报|白皮书|蓝皮书)"), "official_report", 50),
    (_make_pattern(r"(?:企业|行业|市场|咨询|智库)(?:报告|数据|年报|研究)"), "enterprise_or_industry_report", 48),
    (_make_pattern(r"(?:麦肯锡|德勤|毕马威|普华永道|安永|艾瑞|智研|前瞻|中商|中国信通院|赛迪)"), "enterprise_or_industry_report", 47),
    (_make_pattern(r"(?:新闻|报道|媒体|报纸|新华社|人民日报|光明日报|央视|新华网|人民网)"), "media_report", 45),
    # ===== 网络数据类 =====
    (_make_pattern(r"(?:爬虫|网络爬取|数据采集|网页数据|抓取数据|Python|Scrapy)"), "web_crawling", 35),
    (_make_pattern(r"(?:平台数据|网站数据|App数据|API数据)"), "platform_data", 30),
    # ===== 通用兜底 =====
    (_make_pattern(r"(?:数据|样本|材料|资料|信息)(?:来源|选自|来自|来源于|取自|获取)(?:于|自)?\s*[：:]"), "unknown", 10),
]


def identify_data_sources(text: str) -> List[Dict[str, Any]]:
    """从论文全文中识别所有数据来源，使用多优先级规则匹配"""
    sources: List[Dict[str, Any]] = []
    seen_texts = set()
    lines = text.split("\n")

    for line in lines:
        line = line.strip()
        if len(line) < 6:
            continue

        best_match = None
        best_priority = -1

        for pattern, source_type, priority in IDENTIFICATION_RULES:
            m = pattern.search(line)
            if m and priority > best_priority:
                source_text = line[:300]
                best_match = (source_text, source_type, priority, m)
                best_priority = priority

        if best_match:
            source_text, source_type, priority, match_obj = best_match

            # 去重
            normalized = source_text[:60]
            if normalized in seen_texts:
                continue
            seen_texts.add(normalized)

            # 提取来源名称
            name_match = re.search(r"《([^》]{2,80})》", source_text)
            source_name = name_match.group(1) if name_match else source_text[:100]

            # 提取 URL
            url_match = re.search(r"https?://[^\s，。；\n]{5,200}", source_text)
            source_url = url_match.group(0).rstrip(".,;，。；") if url_match else None

            # 提取年份
            year_match = re.search(r"((?:19|20)\d{2})", source_text)
            year_str = year_match.group(1) if year_match else None

            # 提取地区
            region = _extract_region(source_text)

            sources.append({
                "source_text": source_text,
                "source_type": source_type,
                "source_name": source_name,
                "source_url": source_url,
                "year": year_str,
                "region": region,
            })

    return sources


def _extract_region(text: str) -> str:
    """提取文本中的地区信息"""
    region_patterns = [
        r"(?:浙江|杭州|宁波|温州|嘉兴|湖州|绍兴|金华|衢州|舟山|台州|丽水)",
        r"(?:北京|上海|天津|重庆)",
        r"(?:广东|广州|深圳|江苏|南京|苏州|山东|济南|青岛|福建|福州|厦门)",
        r"(?:湖北|武汉|湖南|长沙|河南|郑州|河北|石家庄|山西|太原|辽宁|沈阳|大连)",
        r"(?:吉林|长春|黑龙江|哈尔滨|安徽|合肥|江西|南昌|海南|海口|四川|成都)",
        r"(?:贵州|贵阳|云南|昆明|陕西|西安|甘肃|兰州|青海|西宁|广西|南宁|内蒙古|呼和浩特)",
        r"(?:西藏|拉萨|宁夏|银川|新疆|乌鲁木齐)",
        r"(?:长三角|珠三角|京津冀|成渝|粤港澳)",
    ]
    for pat in region_patterns:
        m = re.search(pat, text)
        if m:
            return m.group(0)
    if re.search(r"(?:全国|中国|国家|中央)", text):
        return "全国"
    return ""


# ============================================================================
# 评分逻辑
# ============================================================================

# 不同来源类型的维度权重
SOURCE_WEIGHTS: Dict[str, Dict[str, float]] = {
    # 政府统计/年鉴：权威性和可追溯性权重高
    "statistical_bureau_data": {"authority": 0.30, "traceability": 0.25, "timeliness": 0.15, "completeness": 0.20, "ethics": 0.05, "method_match": 0.05},
    "statistical_yearbook": {"authority": 0.30, "traceability": 0.25, "timeliness": 0.15, "completeness": 0.20, "ethics": 0.05, "method_match": 0.05},
    "official_report": {"authority": 0.30, "traceability": 0.25, "timeliness": 0.15, "completeness": 0.20, "ethics": 0.05, "method_match": 0.05},
    # 政府网站/政策：权威性+可追溯+时效
    "central_government_website": {"authority": 0.30, "traceability": 0.25, "timeliness": 0.20, "completeness": 0.15, "ethics": 0.05, "method_match": 0.05},
    "local_government_website": {"authority": 0.30, "traceability": 0.25, "timeliness": 0.20, "completeness": 0.15, "ethics": 0.05, "method_match": 0.05},
    "government_information_disclosure": {"authority": 0.30, "traceability": 0.25, "timeliness": 0.20, "completeness": 0.15, "ethics": 0.05, "method_match": 0.05},
    "government_policy_document": {"authority": 0.30, "traceability": 0.25, "timeliness": 0.20, "completeness": 0.15, "ethics": 0.05, "method_match": 0.05},
    "local_regulation": {"authority": 0.30, "traceability": 0.25, "timeliness": 0.20, "completeness": 0.15, "ethics": 0.05, "method_match": 0.05},
    "public_data_platform": {"authority": 0.25, "traceability": 0.25, "timeliness": 0.20, "completeness": 0.20, "ethics": 0.05, "method_match": 0.05},
    # 问卷/访谈：完整性和伦理合规权重高
    "survey": {"authority": 0.10, "traceability": 0.20, "timeliness": 0.10, "completeness": 0.25, "ethics": 0.20, "method_match": 0.15},
    "interview": {"authority": 0.10, "traceability": 0.20, "timeliness": 0.10, "completeness": 0.25, "ethics": 0.20, "method_match": 0.15},
    # 学术文献整理：完整性+方法匹配权重高
    "academic_literature_synthesis": {"authority": 0.20, "traceability": 0.25, "timeliness": 0.10, "completeness": 0.25, "ethics": 0.05, "method_match": 0.15},
    "academic_database": {"authority": 0.25, "traceability": 0.25, "timeliness": 0.15, "completeness": 0.20, "ethics": 0.05, "method_match": 0.10},
    # 案例材料
    "case_material": {"authority": 0.15, "traceability": 0.20, "timeliness": 0.10, "completeness": 0.25, "ethics": 0.15, "method_match": 0.15},
    # 媒体/企业报告
    "media_report": {"authority": 0.15, "traceability": 0.20, "timeliness": 0.25, "completeness": 0.15, "ethics": 0.10, "method_match": 0.15},
    "enterprise_or_industry_report": {"authority": 0.15, "traceability": 0.20, "timeliness": 0.25, "completeness": 0.15, "ethics": 0.10, "method_match": 0.15},
    # 网络数据
    "platform_data": {"authority": 0.10, "traceability": 0.20, "timeliness": 0.20, "completeness": 0.20, "ethics": 0.10, "method_match": 0.20},
    "web_crawling": {"authority": 0.10, "traceability": 0.20, "timeliness": 0.15, "completeness": 0.20, "ethics": 0.15, "method_match": 0.20},
    # 默认
    "unknown": {"authority": 0.20, "traceability": 0.20, "timeliness": 0.15, "completeness": 0.15, "ethics": 0.15, "method_match": 0.15},
}


def _get_default_weights(source_type: str) -> Dict[str, float]:
    return SOURCE_WEIGHTS.get(source_type, SOURCE_WEIGHTS["unknown"])


def classify_research_design(text: str) -> str:
    """分类研究设计类型"""
    t = text.lower()

    if re.search(r'systematic\s+literature\s+review|systematic\s+review|prisma|meta[\s-]analysis', t):
        return "systematic_review"
    if re.search(r'literature\s+review|review.*literature|review\s+and\s+research\s+agenda|research\s+agenda|本文综述|文献综述|研究综述|研究述评|reviews\s+existing\s+literature|review\s+of\s+the\s+literature', t):
        return "literature_review"
    if re.search(r'theoretical\s+framework|conceptual\s+framework|本文从理论上|理论分析|理论框架|概念框架', t):
        return "theoretical_analysis"
    if re.search(r'policy\s+analysis|policy\s+document|政策分析|政策文本|政策文件|policy[\s-]cycle', t):
        return "policy_analysis"
    if re.search(r'case\s+study|case\s+analysis|案例研究|个案研究|案例分', t):
        return "case_study"
    if re.search(r'survey|questionnaire|regression|dataset|sample\s+size|empirical\s+analysis|问卷|回归|样本量|数据集|定量', t):
        return "empirical_quantitative"
    if re.search(r'interview|fieldwork|qualitative|访谈|扎根理论|田野调查|质性', t):
        return "empirical_qualitative"
    if re.search(r'mixed[\s-]method|混合方法|定量.*定性|定性.*定量', t):
        return "mixed_methods"
    if re.search(r'硕士论文|博士论文|毕业论文|学位论文|thesis|dissertation', t):
        return "thesis_or_dissertation"
    return "unknown"


RESEARCH_DESIGN_LABELS = {
    "systematic_review": "系统综述",
    "literature_review": "文献综述",
    "theoretical_analysis": "理论分析",
    "policy_analysis": "政策分析",
    "case_study": "案例研究",
    "empirical_quantitative": "实证定量研究",
    "empirical_qualitative": "实证质性研究",
    "mixed_methods": "混合方法研究",
    "thesis_or_dissertation": "学位论文",
    "unknown": "未分类",
}


def _review_score_to_risk(score: float) -> str:
    if score >= 70: return "low"
    elif score >= 50: return "medium"
    elif score >= 35: return "high"
    return "critical"


def score_literature_review_data_source(text: str, research_design: str) -> Dict[str, Any]:
    """对系统综述/文献综述类论文的数据来源评分"""
    t = text.lower()
    is_systematic = research_design == "systematic_review"

    # 1. Database score
    db_keywords = [
        "web of science", "scopus", "google scholar", "pubmed", "sciencedirect",
        "springerlink", "ieee xplore", "acm digital library", "proquest", "ebsco",
        "cnki", "wanfang", "cssci", "jstor", "taylor & francis", "sage",
        "emerald", "database", "databases", "bibliographic database",
    ]
    db_found = [k for k in db_keywords if k in t]
    database_score = min(100, 40 + len(db_found) * 25)

    # 2. Keyword score
    kw_keywords = [
        "search terms", "keywords", "query", "search string", "search strategy",
        "retrieval strategy", "检索词", "关键词", "检索式", "检索策略",
    ]
    kw_found = [k for k in kw_keywords if k in t]
    keyword_score = min(100, 30 + len(kw_found) * 30)

    # 3. Time range score
    time_keywords = [
        "between", "from", "published between", "time span", "publication period",
        "时间范围", "检索时间", "发表时间", "年份范围", "2010", "2015", "2020",
    ]
    time_found = [k for k in time_keywords if k in t]
    time_range_score = min(100, 25 + len(time_found) * 20)

    # 4. Inclusion/exclusion score
    ie_keywords = [
        "inclusion criteria", "exclusion criteria", "eligibility criteria",
        "selection criteria", "included articles", "excluded articles",
        "screening", "纳入标准", "排除标准", "筛选标准", "文献筛选",
        "prisma",
    ]
    ie_found = [k for k in ie_keywords if k in t]
    inclusion_exclusion_score = min(100, 20 + len(ie_found) * 30)

    # 5. Sample count score
    sample_keywords = [
        "articles were selected", "papers were included", "final sample",
        "studies included", "selected publications", "最终纳入",
        "纳入文献", "样本文献", "文献数量",
    ]
    sample_found = [k for k in sample_keywords if k in t]
    sample_count_score = min(100, 15 + len(sample_found) * 35)

    # 6. Reproducibility score
    repro_keywords = [
        "prisma", "coding", "screening process", "review protocol",
        "inter-coder reliability", "coding scheme", "flow diagram",
        "reproducibility", "可复现", "编码", "筛选流程", "研究协议",
    ]
    repro_found = [k for k in repro_keywords if k in t]
    reproducibility_score = min(100, len(repro_found) * 40)

    # Weighted total
    review_score = (
        0.20 * database_score +
        0.20 * keyword_score +
        0.15 * time_range_score +
        0.20 * inclusion_exclusion_score +
        0.15 * sample_count_score +
        0.10 * reproducibility_score
    )

    # Floor protection
    if is_systematic and review_score < 45:
        review_score = 45
    elif research_design == "literature_review" and review_score < 40:
        review_score = 40

    # Detected evidence
    evidence = []
    if is_systematic:
        evidence.append({"type": "research_design", "text": "systematic literature review", "meaning": "检测到系统综述研究设计"})
    elif research_design == "literature_review":
        evidence.append({"type": "research_design", "text": "literature review", "meaning": "检测到文献综述研究设计"})
    for k in db_found[:4]:
        evidence.append({"type": "database", "text": k, "meaning": f"检测到文献数据库: {k}"})
    for k in kw_found[:4]:
        evidence.append({"type": "keyword", "text": k, "meaning": f"检测到检索关键词说明: {k}"})

    # Missing items
    missing = []
    if database_score < 40: missing.append("文献检索数据库")
    if keyword_score < 40: missing.append("检索关键词")
    if time_range_score < 40: missing.append("时间范围")
    if inclusion_exclusion_score < 40: missing.append("纳入排除标准")
    if sample_count_score < 40: missing.append("最终纳入文献数量")
    if reproducibility_score < 40: missing.append("筛选流程/可复现性")

    # Summary
    if review_score >= 70:
        summary = (
            f"系统判断本文属于{RESEARCH_DESIGN_LABELS.get(research_design, '文献综述')}类研究。"
            f"当前已识别到较好的文献检索说明（评分{review_score:.0f}分），数据来源可靠性较高。"
        )
    elif review_score >= 50:
        summary = (
            f"系统判断本文属于{RESEARCH_DESIGN_LABELS.get(research_design, '文献综述')}类研究。"
            f"检测到部分文献检索信息（评分{review_score:.0f}分），建议补充：{'、'.join(missing[:4])}。"
        )
    else:
        summary = (
            f"系统判断本文属于{RESEARCH_DESIGN_LABELS.get(research_design, '文献综述')}类研究。"
            f"该类论文的数据来源主要是已有学术文献，不一定需要问卷或一手数据。"
            f"当前文本中尚未充分识别到文献检索数据库、检索关键词、时间范围、纳入排除标准或筛选流程"
            f"（评分{review_score:.0f}分），建议补充这些信息以增强可复核性。"
        )

    # Default item
    default_item = {
        "index": 1,
        "source_type": "academic_literature",
        "source_type_name": "已有学术文献",
        "source_name": "已有学术文献与文献数据库",
        "source_text": "系统根据文本内容判断本文属于文献综述类研究，其主要数据来源应为已有学术文献和文献数据库。",
        "source_url": None,
        "scores": {
            "authority": 70, "traceability": review_score, "timeliness": 60,
            "completeness": review_score, "ethics": 100, "method_match": 80,
            "total": review_score,
        },
        "risk_level": _review_score_to_risk(review_score),
        "missing_fields": missing,
        "risk_reason": f"文献综述类论文的数据来源尚不够透明，缺失：{'、'.join(missing[:4])}" if missing else "文献检索说明较完整",
        "suggestion": (
            f"建议补充：文献检索数据库（如Web of Science、Scopus）、检索关键词、"
            f"检索时间范围、纳入排除标准和筛选流程、最终纳入文献数量。"
        ),
    }

    return {
        "review_score": round(review_score, 1),
        "score_breakdown": {
            "database_score": database_score,
            "keyword_score": keyword_score,
            "time_range_score": time_range_score,
            "inclusion_exclusion_score": inclusion_exclusion_score,
            "sample_count_score": sample_count_score,
            "reproducibility_score": reproducibility_score,
        },
        "detected_evidence": evidence,
        "missing_items": missing,
        "summary": summary,
        "default_item": default_item,
        "debug": {
            "raw_text_length": len(text),
            "research_design_detected": research_design,
            "matched_research_design_keywords": [k for k in ["systematic literature review", "systematic review", "literature review", "research agenda"] if k in t],
            "matched_data_source_keywords": db_found + kw_found,
            "score_before_fallback": review_score,
            "fallback_applied": review_score < 50,
            "analyzer_version": "data_source_review_scoring_v2",
        },
    }


class DataSourceReliabilityService:
    """数据来源可靠性分析服务 — 公共管理场景优化版"""

    def __init__(self):
        pass

    def analyze_data_sources(self, text: str, use_web_search: bool = True) -> Dict[str, Any]:
        """分析论文中的数据来源可靠性"""
        research_design = classify_research_design(text)
        raw_sources = identify_data_sources(text)

        non_empirical = ["literature_review", "systematic_review", "theoretical_analysis", "policy_analysis"]

        if not raw_sources:
            if research_design in non_empirical:
                review_result = score_literature_review_data_source(text, research_design)
                return {
                    "total_sources": 1,
                    "average_score": review_result["review_score"],
                    "risk_level": _review_score_to_risk(review_result["review_score"]),
                    "research_design": research_design,
                    "research_design_label": RESEARCH_DESIGN_LABELS.get(research_design, "未分类"),
                    "summary": review_result["summary"],
                    "items": [review_result["default_item"]],
                    "score_breakdown": review_result["score_breakdown"],
                    "detected_evidence": review_result["detected_evidence"],
                    "missing_items": review_result["missing_items"],
                    "data_source_debug": review_result["debug"],
                    "disclaimer": self._disclaimer(),
                    "analyzer_version": "data_source_review_scoring_v2",
                }
            else:
                summary = "未在论文中检测到明确的数据来源描述。建议作者补充数据来源、样本信息、采集方式等说明。"
                return {
                    "total_sources": 0, "average_score": 0, "risk_level": "medium",
                    "research_design": research_design,
                    "research_design_label": RESEARCH_DESIGN_LABELS.get(research_design, "未分类"),
                    "summary": summary,
                    "items": [], "disclaimer": self._disclaimer(),
                    "analyzer_version": "data_source_reliability_v3_actionable_suggestions",
                }

        items: List[Dict[str, Any]] = []
        total_score = 0.0

        for i, src in enumerate(raw_sources):
            scores = self._score_source(src)
            weights = _get_default_weights(src["source_type"])
            total = (
                weights["authority"] * scores["authority"]
                + weights["traceability"] * scores["traceability"]
                + weights["timeliness"] * scores["timeliness"]
                + weights["completeness"] * scores["completeness"]
                + weights["ethics"] * scores["ethics"]
                + weights["method_match"] * scores["method_match"]
            )
            risk_level = _score_to_risk_level(total, src["source_type"], scores)
            missing_fields = _detect_missing_fields(src, scores)
            suggestion = generate_actionable_suggestion(
                src, risk_level, missing_fields, src["source_type"], scores
            )

            items.append({
                "index": i + 1,
                "source_text": src["source_text"],
                "source_type": src["source_type"],
                "source_type_name": SOURCE_TYPE_NAMES.get(src["source_type"], src["source_type"]),
                "source_name": src["source_name"],
                "source_url": src["source_url"],
                "scores": {
                    "authority": scores["authority"],
                    "traceability": scores["traceability"],
                    "timeliness": scores["timeliness"],
                    "completeness": scores["completeness"],
                    "ethics": scores["ethics"],
                    "method_match": scores["method_match"],
                    "total": round(total, 1),
                },
                "risk_level": risk_level,
                "missing_fields": missing_fields,
                "risk_reason": _build_risk_reason(scores, src, missing_fields),
                "suggestion": suggestion,
            })
            total_score += total

        avg_score = total_score / len(items) if items else 0

        # For non-empirical papers, compute review score and blend with item scores
        review_score = None
        score_breakdown = None
        detected_evidence = None
        missing_items = None
        if research_design in non_empirical:
            review_result = score_literature_review_data_source(text, research_design)
            review_score = review_result["review_score"]
            score_breakdown = review_result["score_breakdown"]
            detected_evidence = review_result["detected_evidence"]
            missing_items = review_result["missing_items"]
            # Blend: 70% review score + 30% item-based score
            avg_score = 0.7 * review_score + 0.3 * avg_score

        avg_risk = _score_to_risk_level(avg_score, "unknown", {})
        summary = _build_summary(len(items), avg_score)
        if research_design in non_empirical and review_score is not None:
            summary = review_result.get("summary", summary)

        result = {
            "total_sources": len(items) or (1 if research_design in non_empirical else 0),
            "average_score": round(avg_score, 1),
            "risk_level": avg_risk,
            "research_design": research_design,
            "research_design_label": RESEARCH_DESIGN_LABELS.get(research_design, "未分类"),
            "summary": summary,
            "items": items,
            "disclaimer": self._disclaimer(),
            "analyzer_version": "data_source_review_scoring_v2" if research_design in non_empirical else "data_source_reliability_v3_actionable_suggestions",
        }
        if score_breakdown is not None:
            result["score_breakdown"] = score_breakdown
            result["detected_evidence"] = detected_evidence
            result["missing_items"] = missing_items
        return result

    def _score_source(self, src: Dict[str, Any]) -> Dict[str, float]:
        """6维度评分"""
        source_type = src.get("source_type", "unknown")
        source_text = src.get("source_text", "")
        source_name = src.get("source_name", "")
        source_url = src.get("source_url")

        return {
            "authority": _score_authority(source_type, source_name, source_text, source_url),
            "traceability": _score_traceability(source_type, source_name, source_text, source_url),
            "timeliness": _score_timeliness(source_text),
            "completeness": _score_completeness(source_text, source_type),
            "ethics": _score_ethics(source_text, source_type),
            "method_match": _score_method_match(source_text, source_type),
        }

    def _disclaimer(self) -> str:
        return "本功能用于论文正式投稿前的风险预审，结果仅供修改参考，不能替代正式查重和人工审查。"


# ============================================================================
# 各维度评分函数
# ============================================================================

def _score_authority(source_type: str, name: str, text: str, url: Optional[str] = None) -> float:
    """权威性评分"""
    high_authority_types = {
        "central_government_website": 95, "local_government_website": 88,
        "government_information_disclosure": 90, "government_policy_document": 92,
        "local_regulation": 90, "statistical_bureau_data": 90, "statistical_yearbook": 88,
        "official_report": 85, "public_data_platform": 82,
    }
    medium_authority = {"academic_database": 78, "academic_literature_synthesis": 65,
                        "survey": 60, "interview": 55, "case_material": 55,
                        "platform_data": 45, "media_report": 50,
                        "enterprise_or_industry_report": 55}
    low_authority = {"web_crawling": 35, "unknown": 25}

    if source_type in high_authority_types:
        score = float(high_authority_types[source_type])
    elif source_type in medium_authority:
        score = float(medium_authority[source_type])
    elif source_type in low_authority:
        score = float(low_authority[source_type])
    else:
        score = 40.0

    # 加分项
    if url and re.search(r"\.gov\.cn", url):
        score += 5
    if re.search(r"(?:国务院|中共中央|国家统计局|民政部|人社部)", name):
        score += 3
    if re.search(r"(?:政府公报|白皮书|蓝皮书|统计年鉴|统计公报)", text):
        score += 2

    # 减分项
    if source_type == "unknown" and not re.search(r"(?:政府|官方|统计|年鉴|条例|政策|法规)", text):
        score -= 10

    return min(100, max(0, score))


def _score_traceability(source_type: str, name: str, text: str, url: Optional[str] = None) -> float:
    """可追溯性评分"""
    score = 40.0

    # 有 URL 加分
    if url:
        score += 25
        if re.search(r"\.gov\.cn", url):
            score += 10
        elif re.search(r"\.edu\.cn", url):
            score += 8
        elif re.search(r"\.org", url):
            score += 3

    # 完整名称
    if len(name) > 10:
        score += 10
    elif len(name) > 5:
        score += 5

    # 年份提及
    if re.search(r"(?:20\d{2}|19\d{2})", text):
        score += 10

    # 发布日期
    if re.search(r"(?:发布|颁布|施行|通过|生效)(?:日期|时间|于)", text):
        score += 8

    # 访问日期
    if re.search(r"(?:访问|检索|查阅|获取)(?:日期|时间|于)", text):
        score += 5

    # 文号
    if re.search(r"(?:[〔\(]\d{4}[〕\)]\s*\d+|国发|国办发|财社|发改|民发|人社)", text):
        score += 8

    # 模糊描述减分
    fuzzy_patterns = [
        r"来自网络", r"相关网站", r"公开资料(?:整理)?", r"网络数据",
        r"资料整理", r"自行整理", r"来源于网络", r"网上搜集",
    ]
    for pat in fuzzy_patterns:
        if re.search(pat, text):
            score -= 15
            break

    return min(100, max(0, score))


def _score_timeliness(text: str) -> float:
    """时效性评分"""
    score = 55.0
    years = [int(y) for y in re.findall(r"(?:20\d{2}|19\d{2})", text)]
    from datetime import datetime
    current_year = datetime.now().year

    if years:
        latest = max(years)
        if current_year - latest <= 3:
            score += 25
        elif current_year - latest <= 5:
            score += 15
        elif current_year - latest <= 10:
            score += 5
        else:
            score -= 10
        if re.search(r"\d{4}[-—~]\d{4}", text) or re.search(r"(?:期间|时间段|年份范围为)", text):
            score += 10
    else:
        score -= 10

    for y in years:
        if y > current_year + 1:
            score -= 20
            break

    return min(100, max(0, score))


def _score_completeness(text: str, source_type: str) -> float:
    """完整性评分"""
    score = 45.0

    if re.search(r"(?:样本|观测|记录|条目|对象)\s*(?:量|数|为|共计?)\s*\d+", text):
        score += 12
    if re.search(r"\d+\s*(?:份|张|条|个|次|人|位|名|篇|部|项)", text):
        score += 8
    if re.search(r"(?:筛选|排除|纳入|抽样)(?:标准|条件|方法|方式)", text):
        score += 10
    if re.search(r"(?:变量|指标|维度|因子)(?:为|包括|包含|定义|测量|说明)", text):
        score += 10
    if re.search(r"(?:缺失|缺失值|异常值|离群值)(?:处理|填补|删除)", text):
        score += 5

    if source_type == "survey":
        if re.search(r"(?:回收|有效)(?:率|问卷)", text): score += 12
        if re.search(r"发放\s*\d+.*回收\s*\d+", text): score += 10
    elif source_type == "interview":
        if re.search(r"(?:访谈提纲|编码|转录|主题分析)", text): score += 10
    elif source_type in ("government_policy_document", "local_regulation"):
        if re.search(r"(?:发布机关|文号|施行日期|有效期)", text): score += 12
    elif source_type in ("statistical_yearbook", "statistical_bureau_data"):
        if re.search(r"(?:表号|指标|口径|页码|指标名称)", text): score += 12

    return min(100, max(0, score))


def _score_ethics(text: str, source_type: str) -> float:
    """伦理合规性评分"""
    score = 60.0
    human_subject_types = ["survey", "interview", "case_material", "web_crawling"]

    if source_type in human_subject_types:
        if re.search(r"(?:匿名|脱敏|去标识|化名|隐私|知情同意|伦理|IRB|伦理委员会|Ethics|伦理审查)", text):
            score += 20
        elif re.search(r"(?:合规|合法|授权|许可|批准)(?:获取|处理|使用|采集)", text):
            score += 12
        else:
            if re.search(r"(?:个人|用户|居民|市民|受访者|调查对象)(?:信息|数据|隐私)", text):
                score -= 12
        if source_type == "web_crawling":
            if re.search(r"(?:API|授权|robots|合规|合法)(?:爬取|采集|获取)", text):
                score += 8
            else:
                score -= 8
    else:
        score += 18  # 政府数据、年鉴等通常合规

    return min(100, max(0, score))


def _score_method_match(text: str, source_type: str) -> float:
    """方法匹配度评分"""
    score = 50.0

    has_quantitative = bool(re.search(
        r"(?:回归|相关|显著性|p\s*[<>=]|t\s*检验|方差|ANOVA|因子分析|结构方程|SEM|OLS|Logit|Probit|DID|RD[DR]?|IV\s|工具变量)",
        text, re.IGNORECASE,
    ))
    has_qualitative = bool(re.search(
        r"(?:案例研究|扎根理论|内容分析|文本分析|话语分析|叙事分析|主题分析|编码|NVivo|过程追踪|比较案例)",
        text,
    ))

    source_type_for_method = ["survey", "statistical_bureau_data", "statistical_yearbook",
                              "academic_database", "platform_data"]
    qualitative_types = ["interview", "case_material", "government_policy_document",
                         "local_regulation", "academic_literature_synthesis"]

    if source_type in source_type_for_method:
        if has_quantitative:
            score += 20
        if re.search(r"(?:样本量|变量|指标|描述统计|回归模型|计量模型)", text):
            score += 12
    elif source_type in qualitative_types:
        if has_qualitative:
            score += 20
        if re.search(r"(?:编码|主题|框架|饱和|三角验证|内容分析)", text):
            score += 12
    else:
        score += 8

    return min(100, max(0, score))


# ============================================================================
# 风险等级
# ============================================================================

def _score_to_risk_level(total_score: float, source_type: str = "unknown",
                         scores: Optional[Dict[str, float]] = None) -> str:
    """根据总分 + 来源类型修正规则判断风险等级"""
    if scores is None:
        scores = {}

    # Survey types: relax - at most medium if score >= 60
    if source_type in ("survey", "survey_statistical_analysis"):
        if total_score >= 85: return "low"
        if total_score >= 60: return "medium"
        if total_score >= 45: return "medium"
        return "high"

    # Expert scoring AHP: never critical
    if source_type == "expert_scoring_ahp":
        if total_score >= 70: return "low"
        if total_score >= 50: return "medium"
        return "high"

    # Interview: relax
    if source_type == "interview":
        if total_score >= 80: return "low"
        if total_score >= 55: return "medium"
        return "high"

    exempt_from_critical = {
        "government_policy_document", "local_regulation",
        "statistical_yearbook", "statistical_bureau_data",
        "central_government_website", "local_government_website",
        "government_information_disclosure", "official_report",
    }
    if source_type == "academic_literature_synthesis" and scores.get("authority", 0) >= 50:
        if total_score < 40:
            total_score = 42

    if total_score >= 85: return "low"
    elif total_score >= 70: return "medium"
    elif total_score >= 50: return "high"
    else:
        if source_type in exempt_from_critical and scores.get("authority", 0) >= 80:
            return "high"
        if source_type == "unknown" and (not scores.get("authority", 0)):
            return "critical"
        return "critical"


# ============================================================================
# 缺失字段检测
# ============================================================================

def _detect_missing_fields(src: Dict[str, Any], scores: Dict[str, float]) -> List[str]:
    """检测数据来源的缺失字段"""
    missing = []
    text = src.get("source_text", "")
    source_type = src.get("source_type", "unknown")

    # Survey/interview/expert/SPSS types do NOT need url/year/region
    NO_URL_TYPES = {"survey", "interview", "expert_scoring_ahp", "survey_statistical_analysis", "case_material", "academic_literature_synthesis"}
    if source_type not in NO_URL_TYPES:
        if not src.get("source_name") or len(src.get("source_name", "")) < 3:
            missing.append("source_name")
        if not src.get("source_url") and scores.get("traceability", 100) < 60:
            missing.append("url")
        if not src.get("year"):
            missing.append("year")
        if not src.get("region"):
            missing.append("region")

    # 政府政策/条例专用
    if source_type in ("government_policy_document", "local_regulation"):
        if not re.search(r"(?:发布机关|颁布机关|发文机关|制定机关)", text):
            missing.append("issuing_authority")
        if not re.search(r"(?:文号|[〔\(]\d{4}[〕\)]\s*\d+)", text):
            missing.append("document_number")
        if not re.search(r"(?:施行|生效|通过|发布)(?:日期|时间|于)", text):
            missing.append("publish_date")
        if not re.search(r"(?:有效|失效|废止|现行有效)", text):
            missing.append("validity_status")
        if not re.search(r"https?://", text):
            missing.append("official_url")

    # 统计年鉴专用
    if source_type in ("statistical_yearbook", "statistical_bureau_data"):
        if not re.search(r"(?:表号|表\s*\d+|表格|Table)", text):
            missing.append("table_number")
        if not re.search(r"(?:指标|变量)(?:名称|定义|说明|含义)", text):
            missing.append("indicator_name")
        if not re.search(r"(?:口径|统计口径|统计范围|调查范围)", text):
            missing.append("statistical_caliber")
        if not re.search(r"(?:页|page|p\.)\s*\d+", text):
            missing.append("page_number")

    # 学术文献整理专用
    if source_type == "academic_literature_synthesis":
        if not re.search(r"(?:作者|学者|研究者|文献)[^。]{0,30}(?:[\(（]\d{4}[\)）]|\d{4})", text):
            missing.append("original_author_or_year")
        if not re.search(r"(?:指标|变量|维度|因子).{0,30}(?:定义|说明|含义|测量|计算|构建)", text):
            missing.append("indicator_definition")
        if not re.search(r"(?:调整|修改|修订|删除|增加|适应|适配|情境)", text):
            missing.append("adaptation_explanation")

    # 问卷专用
    if source_type == "survey":
        if not re.search(r"\d+\s*(?:份|张|人|位|名)", text):
            missing.append("sample_size")
        if not re.search(r"(?:抽样|随机|分层|整群|配额|方便|目的)(?:方法|方式|抽样)", text):
            missing.append("sampling_method")
        if not re.search(r"(?:信度|效度|可靠性|Cronbach|Alpha|KMO|因子分析)", text):
            missing.append("reliability_validity")
        if not re.search(r"(?:匿名|隐私|知情|伦理|伦理|IRB|合规)", text):
            missing.append("ethics_statement")

    # 访谈专用
    if source_type == "interview":
        if not re.search(r"\d+\s*(?:人|位|名|次|场|轮)", text):
            missing.append("interview_count")
        if not re.search(r"(?:编码|转录|NVivo|主题分析|扎根|内容分析)", text):
            missing.append("coding_method")
        if not re.search(r"(?:匿名|隐私|知情|伦理)", text):
            missing.append("anonymity_statement")

    return missing


# ============================================================================
# 强制 Actionable 建议生成
# ============================================================================

FORBIDDEN_SUGGESTIONS = [
    "该数据来源目前无明显改进建议。",
    "暂无建议。",
    "建议进一步完善。",
    "建议加强说明。",
    "无明显改进建议。",
]


def generate_actionable_suggestion(
    src: Dict[str, Any],
    risk_level: str,
    missing_fields: List[str],
    source_type: str,
    scores: Dict[str, float],
) -> str:
    """生成具体可执行的修改建议 — high/critical 必须有实质内容"""
    name = src.get("source_name", "该来源")
    text = src.get("source_text", "")

    # 政府网站/信息公开类
    if source_type in ("central_government_website", "local_government_website",
                       "government_information_disclosure", "public_data_platform"):
        parts = [f"请补充{name}的完整名称、栏目名称、页面标题、发布日期、访问日期和 URL；"]
        parts.append("优先使用 gov.cn 域名的政府官网、政府信息公开平台或部门官网作为来源，并在正文或脚注中注明检索路径。")
        if "url" in missing_fields:
            parts.append("当前缺少 URL 链接，建议在参考文献或脚注中补充完整的政府网站页面地址。")

    # 政策文件/条例类
    elif source_type in ("government_policy_document", "local_regulation"):
        parts = [f"请补充「{name}」的发布机关、通过日期、施行日期、文号、现行有效状态和官方发布链接。"]
        parts.append("建议优先引用中国政府网、地方人大网、司法行政部门官网或地方政府官网的正式文本。")
        if "issuing_authority" in missing_fields:
            parts.append("需明确发文机关全称。")
        if "document_number" in missing_fields:
            parts.append("需补充完整的发文字号（如：国发〔2023〕XX号）。")
        if "official_url" in missing_fields:
            parts.append("需补充政策文件的官方发布 URL 或政府公报链接。")
        if "validity_status" in missing_fields:
            parts.append("需说明该文件的现行有效状态（现行有效/已修订/已废止）。")

    # 统计局数据/统计年鉴
    elif source_type in ("statistical_bureau_data", "statistical_yearbook"):
        parts = [f"请补充「{name}」的年鉴全称、年份、表号、指标名称、统计口径、地区范围和页码。"]
        parts.append("如使用网络数据，请补充国家统计局或地方统计局数据查询链接。")
        if "table_number" in missing_fields:
            parts.append("需注明具体表号或表格编号。")
        if "indicator_name" in missing_fields:
            parts.append("需明确具体使用的指标名称及变量定义。")
        if "statistical_caliber" in missing_fields:
            parts.append("需说明统计口径（如：全市/城镇/农村、规模以上/全口径等）。")

    # 学术文献整理
    elif source_type == "academic_literature_synthesis":
        parts = [f"请补充「{name}」所依据的原始文献的完整参考文献格式（作者、年份、题名、期刊/出版社）。"]
        parts.append("建议在方法部分增加'指标来源与修订说明'表格，说明采用了哪些指标、是否调整了指标权重、是否进行了本研究对象的适配。")
        if "original_author_or_year" in missing_fields:
            parts.append("需明确被依据文献的作者和出版年份。")
        if "indicator_definition" in missing_fields:
            parts.append("需说明每个指标的定义、计算方式和数据来源。")
        if "adaptation_explanation" in missing_fields:
            parts.append("需解释对本研究的适配修改（如删除了不适用的指标、增加了新指标等）。")

    # 问卷调查
    elif source_type == "survey":
        parts = ["请补充问卷发放时间、发放对象、发放地区、发放数量、回收数量、有效问卷数量、抽样方式。"]
        parts.append("请补充问卷的信效度检验结果（如 Cronbach's Alpha、KMO、因子分析结果等）。")
        parts.append("请补充问卷调查的伦理说明（匿名化、知情同意、隐私保护措施）。")
        if "sample_size" in missing_fields:
            parts.append("需明确样本量及有效样本数量。")
        if "sampling_method" in missing_fields:
            parts.append("需说明抽样方法（随机抽样/分层抽样/便利抽样等）及抽样框。")

    # 访谈
    elif source_type == "interview":
        parts = ["请补充访谈对象类型、人数、访谈时间、地点、访谈提纲。"]
        parts.append("请补充访谈资料的编码方法、信效度策略和匿名化处理说明。")
        parts.append("请补充是否获得了受访者的知情同意。")
        if "coding_method" in missing_fields:
            parts.append("需说明编码方式（开放编码/主轴编码/选择性编码等）及编码过程。")

    # 网络爬虫
    elif source_type == "web_crawling":
        parts = ["请补充爬取平台名称、搜索关键词、时间范围、字段清单。"]
        parts.append("请补充去重规则、数据清洗规则和合规说明。")
        parts.append("注意：不要爬取需要登录或禁止抓取的内容，遵守 robots.txt 和网站使用协议。")

    # 案例材料
    elif source_type == "case_material":
        parts = [f"请补充「{name}」的案例选择逻辑、案例代表性说明、资料来源和获取方式。"]
        parts.append("建议说明案例的时间范围、地理范围和数据收集的具体方式。")

    # 平台数据
    elif source_type == "platform_data":
        parts = [f"请补充「{name}」的平台全称、数据接口或导出方式、时间范围、字段说明。"]
        parts.append("请说明数据获取是否获得了平台授权或符合平台使用协议。")

    # unknown
    elif source_type == "unknown":
        parts = [f"当前数据来源「{name}」无法自动识别类型，请明确说明："]
        parts.append("1) 数据的具体来源机构或平台名称；")
        parts.append("2) 数据的发布时间或时间段；")
        parts.append("3) 数据的获取方式（公开下载/申请获取/自行采集等）；")
        parts.append("4) 如为政府公开数据，请提供 gov.cn 链接；如为学术数据，请提供数据库名称和检索式。")

    else:
        parts = [f"请补充「{name}」的数据来源详细信息。"]
        parts.append("包括但不限于：来源机构全称、发布/采集时间、获取方式、数据范围、变量定义。")
        if "url" in missing_fields:
            parts.append("建议补充公开可访问的 URL 链接。")
        if "year" in missing_fields:
            parts.append("建议补充数据的具体年份或时间范围。")

    # high/critical 追加强调
    if risk_level in ("high", "critical"):
        suggestion = " ".join(parts)
        # 确保非空
        if not suggestion.strip() or suggestion.strip() in FORBIDDEN_SUGGESTIONS:
            suggestion = (
                f"该来源被判定为{risk_level}风险，请补充来源名称、发布机构、年份、链接、数据口径、"
                f"访问日期等关键信息。对于{scores.get('authority', 0):.0f}分的权威性和"
                f"{scores.get('traceability', 0):.0f}分的可追溯性，建议优先引用政府官网、"
                f"统计局数据或正式出版物。"
            )
        return suggestion

    return " ".join(parts)


# ============================================================================
# 辅助函数
# ============================================================================

def _build_risk_reason(scores: Dict[str, float], src: Dict[str, Any],
                       missing_fields: List[str]) -> str:
    weak_points = []
    labels = [
        ("authority", "权威性"), ("traceability", "可追溯性"),
        ("timeliness", "时效性"), ("completeness", "完整性"),
        ("ethics", "伦理合规性"), ("method_match", "方法匹配度"),
    ]
    for key, label in labels:
        s = scores.get(key, 0)
        if s < 50:
            weak_points.append(f"{label}不足({s:.0f}分)")

    if weak_points:
        reason = f"存在以下风险：{'；'.join(weak_points)}。"
    else:
        reason = "该数据来源整体可靠性较好，未发现明显风险。"

    if missing_fields:
        reason += f" 缺失关键字段：{'、'.join(missing_fields[:6])}。"

    return reason


def _build_summary(total: int, avg_score: float) -> str:
    if total == 0:
        return "未检测到数据来源。"
    if avg_score >= 85:
        return f"共识别 {total} 个数据来源，平均可靠性 {avg_score:.0f} 分，整体较为可靠。"
    elif avg_score >= 70:
        return f"共识别 {total} 个数据来源，平均可靠性 {avg_score:.0f} 分，基本可用但部分来源需补充说明。"
    elif avg_score >= 50:
        return f"共识别 {total} 个数据来源，平均可靠性 {avg_score:.0f} 分，部分数据来源可靠性不足，建议补充说明。"
    return f"共识别 {total} 个数据来源，平均可靠性 {avg_score:.0f} 分，存在较高可靠性风险，需要重新说明或替换数据来源。"


# 全局实例
data_source_service = DataSourceReliabilityService()
