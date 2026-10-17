"""参考文献真实性校验服务

检查参考文献是否真实存在、是否疑似 AI 生成文献。
通过 DOI、标题、作者、年份、期刊名等字段交叉验证。
"""

from __future__ import annotations

import logging
import os
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from backend.app.models.academic_integrity import ReferenceStatus
from backend.app.services.external_academic_apis import external_academic_client

LOGGER = logging.getLogger(__name__)

DOI_PATTERN = re.compile(r"\b(10\.\d{4,}/[^\s\"'，。；]+)\b", re.IGNORECASE)

# CNKI-like DOI: 10.27xxx/d.cnki.xxxxx
CNKI_DOI_PATTERN = re.compile(r"10\.\d{4,}/d?\s*\.?\s*cnki\.[^\s\"'，。；]+", re.IGNORECASE)

REF_PATTERNS = [
    # GB/T 7714 [J]: 作者. 题名[J]. 期刊名, 年, 卷(期): 页码.
    re.compile(
        r"\[(?P<idx>\d+)\]\s*"
        r"(?P<authors>[^\.]{2,80})\."
        r"\s*(?P<title>[^\[\.]+?)"
        r"\[(?P<type>[J])\]\."
        r"\s*(?P<journal>[^,]+?),"
        r"\s*(?P<year>\d{4})"
        r"(?:,\s*(?P<volume>\d+)\s*(?:\((?P<issue>[\d\-]+)\))?)?"
        r"(?::\s*(?P<pages>[\d\-]+))?"
    ),
    # GB/T 7714 [M]: 作者. 题名[M]. 出版地: 出版社, 年.
    re.compile(
        r"\[(?P<idx>\d+)\]\s*"
        r"(?P<authors>[^\.]{2,80})\."
        r"\s*(?P<title>[^\[\.]+?)"
        r"\[(?P<type>M)\]\."
        r"\s*(?:(?P<place>[^,:]+?)[:：])?\s*"
        r"(?P<publisher>[^,]+?),"
        r"\s*(?P<year>\d{4})"
    ),
    # GB/T 7714 [D]: 作者. 题名[D]. 学校, 年.
    re.compile(
        r"\[(?P<idx>\d+)\]\s*"
        r"(?P<authors>[^\.]{2,80})\."
        r"\s*(?P<title>[^\[\.]+?)"
        r"\[(?P<type>D)\]\."
        r"\s*(?P<institution>[^,]+?),"
        r"\s*(?P<year>\d{4})"
    ),
    # GB/T 7714 [C]: 作者. 题名[C]//会议名. 地点: 出版者, 年.
    re.compile(
        r"\[(?P<idx>\d+)\]\s*"
        r"(?P<authors>[^\.]{2,80})\."
        r"\s*(?P<title>[^/]+?)"
        r"\[(?P<type>C)\]\s*//"
        r"\s*(?P<conf>[^,]+?),"
    ),
    # GB/T 7714 [N]: 作者. 题名[N]. 报纸名, 日期(版次).
    re.compile(
        r"\[(?P<idx>\d+)\]\s*"
        r"(?P<authors>[^\.]{2,80})\."
        r"\s*(?P<title>[^\[\.]+?)"
        r"\[(?P<type>N)\]\."
        r"\s*(?P<newspaper>[^,]+?),"
    ),
    # GB/T 7714 [EB/OL]: 作者. 题名[EB/OL]. URL, 访问日期.
    re.compile(
        r"\[(?P<idx>\d+)\]\s*"
        r"(?P<authors>[^\.]{2,80})\."
        r"\s*(?P<title>[^\[\.]+?)"
        r"\[(?:EB/OL|EB|OL)\]\."
        r"\s*(?P<url>https?://[^\s,]+)"
    ),
    # APA: Author, A. (Year). Title. Journal, Vol(Issue), Pages.
    re.compile(
        r"(?P<authors>[^\(]+)"
        r"\((?P<year>\d{4})\)\."
        r"\s*(?P<title>[^\.]+)\."
        r"\s*(?P<journal>[^,]+),"
        r"\s*(?P<volume>\d+)\((?P<issue>\d+)\)?,?"
        r"\s*(?P<pages>[\d\-]+)?"
    ),
    # DOI pattern
    re.compile(
        r"(?P<authors>[^\(]+)"
        r"\((?P<year>\d{4})\)"
        r"[^D]*DOI[:\s]*(?P<doi>10\.\d{4,}/[^\s]+)",
        re.IGNORECASE,
    ),
]


def extract_references(text: str) -> List[str]:
    """从论文全文中提取参考文献列表"""
    refs, _ = extract_references_with_debug(text)
    return refs


def extract_references_with_debug(text: str) -> tuple:
    """提取参考文献 + 调试信息"""
    debug = {
        "raw_text_length": len(text),
        "contains_reference_heading": False,
        "reference_heading_index": -1,
        "reference_section_found": False,
        "extract_method": "failed",
        "detected_reference_markers": [],
        "extracted_entry_count": 0,
        "parser_warnings": [],
    }

    # Normalize: fullwidth -> halfwidth, merge spaces
    normalized = text
    normalized = normalized.replace("　", " ")
    normalized = re.sub(r"［", "[", normalized)  # ［ -> [
    normalized = re.sub(r"］", "]", normalized)  # ］ -> ]
    normalized = re.sub(r"【", "[", normalized)  # 【 -> [
    normalized = re.sub(r"】", "]", normalized)  # 】 -> ]
    normalized = re.sub(r"[ \t]{2,}", " ", normalized)

    ref_section_patterns = [
        r"^(?:参\s*考\s*文\s*献|参考资料|注释与参考文献|References|Bibliography)\s*[:：]?\s*$",
        r"^(?:参\s*考\s*文\s*献|参考资料|注释与参考文献|References|Bibliography)\s*[:：]+\s*.+$",
        r"^#+\s*(?:参考文献|References|Bibliography)",
        r"^【\s*参\s*考\s*文\s*献\s*】\s*[:：]*",
        r"^\[\s*参\s*考\s*文\s*献\s*\]\s*[:：]*",
    ]
    lines = normalized.split("\n")
    ref_start = -1
    for i, line in enumerate(lines):
        for pat in ref_section_patterns:
            if re.match(pat, line.strip()):
                ref_start = i
                debug["contains_reference_heading"] = True
                debug["reference_heading_index"] = i
                break
        if ref_start >= 0:
            break

    if ref_start < 0:
        # Fallback: search for [1] marker in last 30% of text
        total_lines = len(lines)
        search_start = max(0, int(total_lines * 0.7))
        for i in range(search_start, total_lines):
            if re.match(r"^\s*\[\s*\d+\s*\]", lines[i].strip()):
                ref_start = i - 1  # start from line before first numbered ref
                debug["parser_warnings"].append("参考文献标题未找到，使用编号回退定位")
                break

    if ref_start < 0:
        ref_start = max(0, len(lines) - 50)

    ref_lines = lines[ref_start:]
    # Clean the first line: remove heading so it doesn't become a ref entry
    if ref_lines and re.match(r"^(?:参\s*考\s*文\s*献|参考资料|注释与参考文献|References|Bibliography)", ref_lines[0].strip()):
        cleaned_first = re.sub(
            r"^(?:参\s*考\s*文\s*献|参考资料|注释与参考文献|References|Bibliography)\s*[:：]?\s*",
            "", ref_lines[0], count=1
        )
        if cleaned_first.strip():
            ref_lines[0] = cleaned_first
        else:
            ref_lines = ref_lines[1:]

    ref_text = "\n".join(ref_lines)
    debug["reference_section_found"] = len(ref_text.strip()) > 20
    debug["reference_section_length"] = len(ref_text)
    debug["reference_section_preview"] = ref_text[:500]

    # Merge cross-line refs: join continuation lines, but DON'T merge across
    # numbered markers OR author-year patterns (e.g., "Surname (2020)" or "Surname 2020")
    new_entry_re = re.compile(
        r"^\s*"
        r"(?:"
        r"[\[\(（]\s*\d+\s*[\]\)）\.\．、]"  # numbered marker: [1], (1), 1.
        r"|"
        r"[A-Z][a-z]+.*?\((?:19|20)\d{2}\)"  # Author (Year)
        r"|"
        r"[A-Z][a-z]+.*?\b(?:19|20)\d{2}\b"  # Author Year
        r")"
    )
    merged_lines = []
    for line in ref_lines:
        stripped = line.strip()
        if not stripped:
            merged_lines.append("")
            continue
        if merged_lines and merged_lines[-1] and not new_entry_re.match(stripped):
            merged_lines[-1] = merged_lines[-1] + " " + stripped
        else:
            merged_lines.append(stripped)
    ref_text = "\n".join(merged_lines)

    # Find all numbered markers
    marker_regex = r'(?:^|\n)\s*(?:\[\s*\d{1,3}\s*\]|\(\s*\d{1,3}\s*\)|（\s*\d{1,3}\s*）|\d{1,3}\s*[\.\．、)]\s+)'
    markers = list(re.finditer(marker_regex, ref_text))
    # Filter out false markers (journal page numbers like "154." not followed by ref content)
    valid_markers = []
    for m in markers:
        after = ref_text[m.end():m.end() + 30].strip()
        # Real ref marker is followed by author name or Chinese chars, not lowercase or number
        looks_like_ref = bool(after and (after[0].isupper() or '一' <= after[0] <= '鿿'))
        looks_like_page = bool(re.match(r'^\d', after))  # e.g., "154." followed by another number
        if looks_like_ref or not looks_like_page:
            valid_markers.append(m)
    markers = valid_markers
    debug["detected_reference_markers"] = [m.group().strip() for m in markers[:10]]

    # Split by marker positions
    if len(markers) >= 1:
        entries = []
        for idx, m in enumerate(markers):
            start = m.start()
            if idx + 1 < len(markers):
                end = markers[idx + 1].start()
            else:
                end = len(ref_text)
            entry = ref_text[start:end].strip()
            # Remove leading marker for cleaner entry
            entry = re.sub(r'^\s*(?:\[\s*\d{1,3}\s*\]|\(\s*\d{1,3}\s*\)|（\s*\d{1,3}\s*）|\d{1,3}\s*[\.\．、)]\s+)', '', entry).strip()
            if len(entry) > 15:
                entries.append(entry)

        if entries:
            debug["extract_method"] = "numbered_markers"
            debug["extracted_entry_count"] = len(entries)
            return entries, debug

    # Fallback: blank line split
    blank_split = re.split(r"\n\s*\n", ref_text)
    entries = [r.strip() for r in blank_split if len(r.strip()) > 20]

    # Check if blank split missed entries (English author-year format)
    year_count = len(re.findall(r'\((?:19|20)\d{2}[a-z]?\)|\b(?:19|20)\d{2}[a-z]?\b', ref_text))
    if year_count >= 2:
        author_year_entries = split_unnumbered_author_year_references(ref_text)
        if len(author_year_entries) > len(entries):
            debug["parser_warnings"].append(
                f"blank_split={len(entries)} but {year_count} years detected ({len(author_year_entries)} author-year entries found)"
            )
            debug["extract_method"] = "unnumbered_author_year"
            debug["extracted_entry_count"] = len(author_year_entries)
            return author_year_entries, debug

    if entries:
        debug["extract_method"] = "blank_line_split"
    else:
        debug["extract_method"] = "failed"

    debug["extracted_entry_count"] = len(entries)
    return entries, debug


def split_unnumbered_author_year_references(section_text: str) -> List[str]:
    """Split unnumbered author-year (Harvard/APA) references"""
    if not section_text.strip():
        return []

    # Normalize
    text = re.sub(r'\n{3,}', '\n\n', section_text)

    # Author-year start pattern: Capital letter surname, followed by year
    author_year_pattern = re.compile(
        r'(?:^|\n)\s*'
        r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+[A-Z]\.?)?'
        r'(?:,\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+[A-Z]\.?)?))*'
        r'(?:\s+(?:and|&)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+[A-Z]\.?)?)?'
        r'(?:\s+et\s+al\.?)?'
        r'.*?'
        r'(?:\((?:19|20)\d{2}[a-z]?\)|(?:19|20)\d{2}[a-z]?)',
        re.MULTILINE
    )

    # Find all reference starting positions
    starts = []
    for m in author_year_pattern.finditer(text):
        pos = m.start()
        # Check this isn't mid-continuation (preceded by lowercase line)
        line_start = text.rfind('\n', 0, pos) + 1
        preceding_text = text[line_start:pos].strip()
        if preceding_text and preceding_text[0].islower():
            continue
        starts.append(pos)

    if len(starts) < 2:
        return []

    # Extract entries
    entries = []
    for i, start_pos in enumerate(starts):
        if i + 1 < len(starts):
            end_pos = starts[i + 1]
        else:
            end_pos = len(text)
        entry = text[start_pos:end_pos].strip()
        # Clean up internal line breaks within entry (not between entries)
        entry = re.sub(r'\n(?!\n)', ' ', entry)
        entry = re.sub(r'\s{2,}', ' ', entry)
        if len(entry) > 20:
            entries.append(entry)

    return entries


def extract_doi(text: str) -> str:
    """从文本中提取 DOI"""
    match = DOI_PATTERN.search(text)
    if match:
        doi = match.group(1).rstrip(".")
        return doi
    return ""


def detect_doi_type(doi: str) -> str:
    """识别 DOI 类型：crossref / cnki / datacite / other"""
    if not doi:
        return "none"
    if CNKI_DOI_PATTERN.search(doi):
        return "cnki"
    if re.search(r"cnki", doi, re.IGNORECASE):
        return "cnki_like"
    if re.search(r"10\.\d{4,}/d\.", doi):
        return "datacite_like"
    return "crossref_like"


def fallback_author_extraction(raw_ref: str) -> List[str]:
    """Fallback: extract authors from English references when regex patterns fail"""
    text = raw_ref.strip()
    text = re.sub(r'^[\.\.,\s;；]+', '', text)

    # Pattern 1: "Lastname, Firstname." or "Lastname, Firstname; Lastname, Firstname."
    m = re.match(
        r'^([A-Z][A-Za-z\'-]+,\s*[A-Z][A-Za-z\'-]+(?:\s*[;，,]\s*[A-Z][A-Za-z\'-]+,\s*[A-Z][A-Za-z\'-]+)*)\.?\s',
        text
    )
    if m:
        author_str = m.group(1)
        authors = re.split(r'\s*[;，]\s*', author_str)
        return [a.strip() for a in authors if a.strip()]

    # Pattern 2: "Lastname Y and Lastname Z" or "Lastname Y, Lastname Z"
    m = re.match(
        r'^([A-Z][A-Za-z\'-]+(?:\s+[A-Z]\.?)(?:\s+(?:and|&)\s+[A-Z][A-Za-z\'-]+(?:\s+[A-Z]\.?))*(?:\s*,\s*[A-Z][A-Za-z\'-]+(?:\s+[A-Z]\.?))*)',
        text
    )
    if m:
        author_str = m.group(1)
        authors = re.split(r'\s+(?:and|&)\s+|\s*,\s*', author_str)
        authors = [a.strip() for a in authors if a.strip()]
        if len(authors) >= 1 and len(authors[0].split()) >= 2:
            return authors

    # Pattern 3: Chinese authors: "张三, 李四" or "张三，李四"
    m = re.match(r'^([一-龥]{2,4}[，,、\s][一-龥]{2,4}(?:[，,、\s][一-龥]{2,4})*)', text)
    if m:
        author_str = m.group(1)
        authors = re.split(r'[，,、\s]+', author_str)
        return [a.strip() for a in authors if a.strip() and len(a) >= 2]

    return []


def compute_chinese_confidence(parsed: Dict[str, Any],
                               api_results: List[Dict[str, Any]]) -> float:
    """中文文献置信度计算"""
    title = parsed.get("title", "")
    authors = parsed.get("authors", [])
    year = parsed.get("year")
    doi = parsed.get("doi", "")

    if doi and api_results:
        best = api_results[0]
        if best.get("matched_title") and title_similarity(title, best["matched_title"]) > 0.85:
            return 0.92
        return 0.75

    if api_results:
        best = api_results[0]
        ts = title_similarity(title, best.get("matched_title", ""))
        ao = author_overlap(authors, best.get("matched_authors", []))
        ym = 1.0 if (year and best.get("matched_year") and abs(year - best["matched_year"]) <= 1) else 0.5
        return 0.40 * ts + 0.20 * ao + 0.15 * ym + 0.15 * min(ts, 0.8) + 0.10 * (1.0 if doi else 0.0)

    # No API results - use format completeness
    score = 0.0
    if title and len(title) > 8:
        score += 0.30
    if authors and len(authors) > 0:
        score += 0.20
    if year and 1900 < year < 2030:
        score += 0.15
    if parsed.get("journal") or parsed.get("publisher"):
        score += 0.20
    if doi:
        score += 0.15
    return min(0.75, score)


def parse_reference(ref_text: str) -> Dict[str, Any]:
    """Parse reference fields from a single reference string."""
    # Normalize: strip leading noise (. , ; excess spaces)
    normalized = ref_text.strip()
    normalized = re.sub(r'^[\.\.,\s;；]+', '', normalized)
    normalized = re.sub(r'\s{2,}', ' ', normalized)
    normalized = re.sub(r'\[\s*J\s*\]', '[J]', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'\[\s*M\s*\]', '[M]', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'\[\s*D\s*\]', '[D]', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'［\s*J\s*］', '[J]', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'［\s*M\s*］', '[M]', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r',\s*(\d{2})\s*\(', r', \1(', normalized)  # fix "2020,35(" -> "2020, 35("

    result: Dict[str, Any] = {
        "raw": ref_text,
        "title": "",
        "authors": [],
        "year": None,
        "journal": "",
        "doi": extract_doi(normalized),
        "volume": "",
        "issue": "",
        "pages": "",
        "url": "",
    }

    clean_text = re.sub(r"^\[?\d+\]?\s*\.?\s*", "", normalized.strip())

    # Try GB/T 7714 first
    for pat in REF_PATTERNS:
        m = pat.search(ref_text.strip())
        if m:
            groups = m.groupdict()
            if groups.get("title"):
                result["title"] = groups["title"].strip().rstrip(".")
            if groups.get("authors"):
                authors_str = groups["authors"].strip()
                if ";" in authors_str:
                    result["authors"] = [a.strip() for a in authors_str.split(";") if a.strip()]
                elif "," in authors_str and any("一" <= c <= "鿿" for c in authors_str[:3]):
                    result["authors"] = [a.strip() for a in authors_str.split(",") if a.strip()]
                else:
                    result["authors"] = [authors_str]
            if groups.get("year"):
                try:
                    result["year"] = int(groups["year"])
                except (ValueError, TypeError):
                    pass
            if groups.get("journal"):
                result["journal"] = groups["journal"].strip()
            if groups.get("volume"):
                result["volume"] = groups.get("volume", "")
            if groups.get("issue"):
                result["issue"] = groups.get("issue", "")
            if groups.get("pages"):
                result["pages"] = groups.get("pages", "")
            if groups.get("doi") and not result["doi"]:
                result["doi"] = groups["doi"].strip()
            break

    # Fallback: APA / generic "Author. Title." pattern
    if not result["title"]:
        # Match: Author(s). Title. [Rest...]
        m = re.match(
            r"(?P<authors>[^\.]{2,60})\."
            r"\s*(?P<title>.{5,200}?)(?:\.\s*(?P<rest>.+))?$",
            clean_text,
        )
        if m:
            groups = m.groupdict()
            if groups.get("title"):
                t = groups["title"].strip().rstrip(".")
                if not re.match(r"^\d{4}$", t):  # avoid year-only
                    result["title"] = t
            if groups.get("authors") and not result["authors"]:
                a = re.sub(r"^\[?\d+\]?\s*", "", groups["authors"].strip().rstrip("."))
                if a:
                    result["authors"] = [a]
            rest = groups.get("rest", "")
            if rest:
                # Year anywhere in rest
                ym = re.search(r"\b((?:19|20)\d{2})\b", rest)
                if ym:
                    try:
                        result["year"] = int(ym.group(1))
                    except ValueError:
                        pass
                # Publisher/Journal
                pub_m = re.search(
                    r"([^.,]+(?:Press|Routledge|Springer|Wiley|Elsevier|Sage|Taylor|Francis)[^.,]*)",
                    rest, re.IGNORECASE,
                )
                if pub_m:
                    result["journal"] = pub_m.group(1).strip()
                elif not result["journal"]:
                    first = rest.split(",")[0].strip()
                    if len(first) > 3 and not first.isdigit():
                        result["journal"] = first

    # Try quoted title
    if not result["title"]:
        qm = re.findall(r'["""]([^"""]{5,})["\"”]', ref_text)
        if qm:
            result["title"] = qm[0].strip()

    # Fallback: use longest segment as title
    if not result["title"]:
        parts = [
            p.strip() for p in clean_text.replace("\n", " ").split(".")
            if len(p.strip()) > 10 and not re.match(r"^\d+$", p.strip())
        ]
        if parts:
            result["title"] = parts[0][:200]

    # Fallback author extraction
    if not result["authors"]:
        result["authors"] = fallback_author_extraction(normalized)

    # Extract year from anywhere if missing
    if not result["year"]:
        ym = re.search(r"\b((?:19|20)\d{2})\b", ref_text)
        if ym:
            try:
                result["year"] = int(ym.group(1))
            except ValueError:
                pass

    # Extract URL
    um = re.search(r"https?://[^\s]+", ref_text)
    if um:
        result["url"] = um.group(0).rstrip(".")

    return result


def title_similarity(t1: str, t2: str) -> float:
    """计算两个标题的相似度"""
    if not t1 or not t2:
        return 0.0
    t1 = t1.lower().strip().rstrip(".")
    t2 = t2.lower().strip().rstrip(".")
    return SequenceMatcher(None, t1, t2).ratio()


def author_overlap(authors1: List[str], authors2: List[str]) -> float:
    """计算作者列表的重合度"""
    if not authors1 or not authors2:
        return 0.0
    lastnames1 = {a.split()[-1].lower().rstrip(",") for a in authors1 if a.strip()}
    lastnames2 = {a.split()[-1].lower().rstrip(",") for a in authors2 if a.strip()}
    if not lastnames1 or not lastnames2:
        return 0.0
    return len(lastnames1 & lastnames2) / max(len(lastnames1), len(lastnames2))


def build_manual_check_links(title: str, is_zh: bool) -> List[Dict[str, str]]:
    """生成“一键人工核验”链接。

    中文期刊/学位论文的权威数据普遍在知网、万方、维普付费墙后，没有免费且高覆盖
    的自动核验 API；因此对开放渠道未能自动核验的文献，直接给出权威库/学术搜索的
    直达检索链接，用户点击即可在新标签页确认该文献是否真实存在。
    """
    from urllib.parse import quote_plus
    q = re.sub(r"\s*\[[JDMCRENSP]\]\s*$", "", (title or "").strip())
    q = q.strip(" ：:，,。.;；")
    if not q:
        return []
    if is_zh:
        return [
            {"name": "百度学术", "url": "https://xueshu.baidu.com/s?wd=" + quote_plus(q)},
            {"name": "知网", "url": "https://kns.cnki.net/kns8s/defaultresult/index?kw=" + quote_plus(q)},
            {"name": "万方", "url": "https://s.wanfangdata.com.cn/paper?q=" + quote_plus(q)},
            {"name": "谷歌学术", "url": "https://scholar.google.com/scholar?q=" + quote_plus(q) + "&hl=zh-CN"},
        ]
    return [
        {"name": "Google Scholar", "url": "https://scholar.google.com/scholar?q=" + quote_plus(q)},
        {"name": "Crossref", "url": "https://search.crossref.org/?q=" + quote_plus(q)},
        {"name": "Semantic Scholar", "url": "https://www.semanticscholar.org/search?q=" + quote_plus(q)},
    ]


class ReferenceAuthService:
    """参考文献真实性校验服务"""

    def __init__(self):
        pass

    def check_references(
        self, text: str, use_external_apis: bool = True
    ) -> Dict[str, Any]:
        """检查参考文献真实性"""
        raw_refs, reference_debug = extract_references_with_debug(text)
        if not raw_refs:
            return {
                "total_references": 0,
                "verified_count": 0,
                "suspicious_count": 0,
                "not_found_count": 0,
                "chinese_web_configured": bool(os.getenv("SERPER_API_KEY", "").strip()),
                "risk_level": "medium",
                "summary": "未检测到参考文献列表，请确认参考文献格式。",
                "items": [],
                "reference_debug": reference_debug,
                "disclaimer": (
                    "本系统已尝试通过 Crossref / OpenAlex / Semantic Scholar 检索，"
                    "但国际开放数据库对中文社科文献的收录不完整。建议结合 CNKI、万方、"
                    "维普、国家哲学社会科学文献中心或高校图书馆进行人工核验。"
                ),
            }

        items: List[Optional[Dict[str, Any]]] = [None] * len(raw_refs)

        def _process_one(idx: int, raw: str) -> Dict[str, Any]:
            parsed = parse_reference(raw)
            try:
                result = self._validate_reference(parsed, use_external_apis)
                if len(result) == 7:
                    status, confidence, matched_sources, mismatch_fields, risk_reason, suggestion, ref_provider_trace = result
                elif len(result) == 6:
                    status, confidence, matched_sources, mismatch_fields, risk_reason, suggestion = result
                    ref_provider_trace = []
                else:
                    raise ValueError(f"Unexpected result length: {len(result)}")
            except Exception as e:
                LOGGER.warning("Reference %d validation failed: %s", idx + 1, e)
                status = ReferenceStatus.PARSE_FAILED
                confidence = 0.0
                matched_sources = []
                mismatch_fields = []
                risk_reason = f"该条参考文献校验异常：{str(e)[:100]}"
                suggestion = "请人工核对该条参考文献。"
                ref_provider_trace = [{"provider": "error", "called": True, "status": "error", "error": str(e)[:100]}]

            # Add DOI lookup trace if missing
            doi = parsed.get("doi", "")
            if doi and use_external_apis and not any(t.get("provider") == "doi_lookup" for t in ref_provider_trace):
                dt = detect_doi_type(doi)
                ref_provider_trace.append({
                    "provider": "doi_lookup",
                    "called": dt not in ("cnki", "cnki_like"),
                    "query": doi,
                    "status": "matched" if matched_sources else "no_match",
                    "doi_type": dt,
                    "candidate_count": len(matched_sources),
                    "error": None if dt not in ("cnki", "cnki_like") else "CNKI-like DOI - skipped Crossref lookup",
                })

            # Compute format score and status label
            try:
                from backend.app.services.public_admin_academic_service import public_admin_academic_service as paas
                format_score = paas.compute_format_score(parsed)
                status_label = paas.format_reference_status(
                    status.value if isinstance(status, ReferenceStatus) else status
                )
            except Exception:
                format_score = 0.0
                status_label = str(status.value if isinstance(status, ReferenceStatus) else status)

            # Local match score from provider_trace
            local_match = 0.0
            chinese_match = 0.0
            for t in ref_provider_trace:
                if t.get("provider") == "local_public_admin_db" and t.get("top_candidates"):
                    local_match = t["top_candidates"][0].get("match_score", 0)
                if t.get("provider") == "chinese_social_science" and t.get("top_candidates"):
                    chinese_match = max(chinese_match, t["top_candidates"][0].get("match_score", 0))

            # Compute match_confidence from matched_sources
            match_conf = 0.0
            if matched_sources:
                match_conf = max(ms.get("score", 0) for ms in matched_sources)

            # Compute final_confidence: blend format_score and match_confidence
            final_conf = 0.35 * format_score + 0.55 * match_conf + 0.10 * (0.5 if matched_sources else 0)

            # Build confidence_explanation
            status_str = status.value if isinstance(status, ReferenceStatus) else str(status)
            if status_str == "verified":
                conf_expl = f"开放数据库高置信匹配（匹配度{match_conf:.0%}），文献真实可信。"
            elif status_str in ("likely_real", "likely_real_with_mismatch"):
                conf_expl = f"开放数据库/本地库发现相似文献（匹配度{match_conf:.0%}），但字段未完全一致，建议人工核对。"
            elif status_str == "insufficient_open_metadata":
                conf_expl = f"参考文献格式较完整（{format_score:.0%}），但国际开放数据库未获得高置信匹配（匹配度{match_conf:.0%}）。该结果不代表文献不存在。"
            else:
                conf_expl = f"格式完整度{format_score:.0%}，开放源匹配度{match_conf:.0%}。"

            is_zh_lang = any("一" <= c <= "鿿" for c in (parsed.get("title", "") + parsed.get("journal", "")))
            return {
                "index": idx + 1,
                "raw_reference": raw,
                "parsed": {
                    "title": parsed["title"],
                    "authors": parsed["authors"],
                    "year": parsed["year"],
                    "journal": parsed["journal"],
                    "doi": parsed["doi"],
                    "volume": parsed["volume"],
                    "issue": parsed["issue"],
                    "pages": parsed["pages"],
                    "url": parsed["url"],
                },
                "status": status.value if isinstance(status, ReferenceStatus) else status,
                "status_label": status_label,
                "format_score": format_score,
                "local_match_score": round(local_match, 3),
                "chinese_source_match_score": round(chinese_match, 3),
                "confidence": round(confidence, 3),
                "match_confidence": round(match_conf, 3),
                "final_confidence": round(final_conf, 3),
                "confidence_explanation": conf_expl,
                "matched_sources": matched_sources,
                "mismatch_fields": mismatch_fields,
                "risk_reason": risk_reason,
                "suggestion": suggestion,
                "provider_trace": ref_provider_trace,
                "doi_type": detect_doi_type(doi) if doi else "none",
                "language": "zh" if is_zh_lang else "en",
                "manual_check_links": build_manual_check_links(parsed.get("title", ""), is_zh_lang),
            }

        # 文献级并发核验：各条文献的联网核验相互独立，线程池并行可把总耗时由
        # “条数 × 单条耗时”降为约“ceil(条数/并发) × 单条耗时”。
        from concurrent.futures import ThreadPoolExecutor, as_completed
        max_workers = min(5, max(1, len(raw_refs)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(_process_one, i, raw): i for i, raw in enumerate(raw_refs)
            }
            for future in as_completed(future_map):
                i = future_map[future]
                items[i] = future.result()

        # 状态计数（item["status"] 为状态码字符串）
        verified = sum(1 for it in items if it["status"] in ("verified", "likely_real"))
        suspicious = sum(1 for it in items if it["status"] == "suspicious")
        not_found = sum(1 for it in items if it["status"] in ("not_found", "parse_failed"))

        # ---- Add local bibliography match (supplementary) ----
        local_verified = 0
        try:
            from backend.app.services.local_bibliography import match_reference as local_match
            for item in items:
                flat = {
                    "title": item["parsed"].get("title", ""),
                    "authors": "; ".join(item["parsed"].get("authors", [])) if isinstance(item["parsed"].get("authors"), list) else str(item["parsed"].get("authors", "")),
                    "year": item["parsed"].get("year"),
                    "journal": item["parsed"].get("journal", ""),
                    "doi": item["parsed"].get("doi", ""),
                }
                lm = local_match(flat)
                item["local_match_status"] = lm.get("local_match_status", "not_matched")
                item["local_match_score"] = lm.get("local_match_score", 0.0)
                item["local_match_reasons"] = lm.get("local_match_reasons", [])
                # Count local matches as verified too
                if lm.get("local_match_status") in ("verified_by_local_library", "likely_real_by_local_library"):
                    if item.get("status") not in (ReferenceStatus.VERIFIED.value, ReferenceStatus.LIKELY_REAL.value):
                        local_verified += 1
        except Exception as e:
            LOGGER.warning("Local bibliography matching failed: %s", e)
        verified += local_verified

        risk_level = self._compute_reference_risk_level(
            len(raw_refs), verified, suspicious, not_found
        )
        summary = self._build_reference_summary(
            len(raw_refs), verified, suspicious, not_found
        )

        return {
            "total_references": len(raw_refs),
            "verified_count": verified,
            "suspicious_count": suspicious,
            "not_found_count": not_found,
            "chinese_web_configured": bool(os.getenv("SERPER_API_KEY", "").strip()),
            "risk_level": risk_level,
            "summary": summary,
            "items": items,
            "reference_debug": reference_debug,
            "disclaimer": (
                "开放数据库未收录不等于文献不存在，"
                "中文文献需结合 CNKI、万方、维普或图书馆资源人工复核。"
            ),
        }

    def _validate_reference(
        self, parsed: Dict[str, Any], use_external_apis: bool
    ) -> tuple:
        """校验单条参考文献"""
        doi = parsed["doi"]
        title = parsed["title"]
        authors = parsed.get("authors", [])
        year = parsed.get("year")
        matched_sources: List[Dict[str, Any]] = []
        mismatch_fields: List[str] = []

        # Detect DOI type to handle CNKI-like differently
        doi_type = detect_doi_type(doi) if doi else "none"

        # Skip international API for Chinese references (rarely matched, wastes time)
        is_zh = any('一' <= c <= '鿿' for c in (parsed.get("title", "") + parsed.get("journal", "")))

        # DOI priority check - skip CNKI-like DOIs and Chinese refs for Crossref/OpenAlex
        if doi and use_external_apis and doi_type not in ("cnki", "cnki_like") and not is_zh:
            try:
                api_results = external_academic_client.search_doi(doi)
                if api_results:
                    best = api_results[0]
                    matched_sources.append({
                        "provider": best["provider"],
                        "matched_title": best["title"],
                        "matched_doi": best["doi"],
                        "matched_authors": best["authors"],
                        "matched_year": best["year"],
                        "url": best["url"],
                        "score": 0.95,
                        "raw": {},
                    })
                    if title and best["title"]:
                        ts = title_similarity(title, best["title"])
                        if ts < 0.6:
                            mismatch_fields.append("title")
                    if best["authors"] and authors:
                        ao = author_overlap(authors, best["authors"])
                        if ao < 0.3:
                            mismatch_fields.append("authors")
                    if year and best["year"] and abs(year - best["year"]) > 2:
                        mismatch_fields.append("year")
                    if mismatch_fields:
                        return (
                            ReferenceStatus.LIKELY_REAL_WITH_MISMATCH, 0.78,
                            matched_sources, mismatch_fields,
                            f"DOI可查但以下字段不一致：{'、'.join(mismatch_fields)}。",
                            "请核对原文 PDF 或数据库导出的标准引用格式。",
                            [],
                        )
                    return (
                        ReferenceStatus.VERIFIED, 0.95,
                        matched_sources, [],
                        "DOI 验证通过。", "该参考文献真实可信。",
                        [],
                    )
                else:
                    if bool(re.match(r"^10\.\d{4,}/", doi)):
                        return (
                            ReferenceStatus.SUSPICIOUS, 0.3, [], [],
                            "DOI 格式正确但多个开放数据库均未检索到，存在疑似伪造风险。",
                            "建议核对 DOI 是否输入正确，或通过出版商官网直接查询。",
                            [],
                        )
            except Exception as e:
                LOGGER.warning("DOI API validation error: %s", e)

        # Title/author search - skip international API for Chinese refs
        provider_trace: List[Dict[str, Any]] = []
        if use_external_apis and title and not is_zh:
            try:
                author_str = authors[0] if authors else ""
                api_results = external_academic_client.search_reference(
                    title=title, authors=author_str, year=year
                )
                best_score = 0.0
                best_result = None
                for r in api_results:
                    ts = title_similarity(title, r["title"])
                    ao = author_overlap(authors, r.get("authors", []))
                    score = 0.6 * ts + 0.4 * ao
                    provider_trace.append({
                        "provider": r["provider"],
                        "called": True,
                        "query": title[:80],
                        "status": "matched" if score >= 0.3 else "no_match",
                        "candidate_count": 1,
                        "score": round(score, 3),
                        "matched_title": r.get("title", "")[:80],
                        "error": None,
                    })
                    if score > best_score:
                        best_score = score
                        best_result = r
                    # Keep low-score matches too for transparency
                    if score >= 0.2:
                        matched_sources.append({
                            "provider": r["provider"],
                            "matched_title": r["title"],
                            "matched_doi": r["doi"],
                            "matched_authors": r.get("authors", []),
                            "matched_year": r.get("year"),
                            "url": r.get("url", ""),
                            "score": round(score, 3),
                            "raw": {},
                        })
                if best_result and best_score > 0.5:
                    if best_result.get("title") and title_similarity(title, best_result["title"]) < 0.7:
                        mismatch_fields.append("title")
                    if best_result.get("year") and year and abs(best_result["year"] - year) > 2:
                        mismatch_fields.append("year")
                    if mismatch_fields:
                        return (
                            ReferenceStatus.LIKELY_REAL_WITH_MISMATCH, best_score,
                            matched_sources, mismatch_fields,
                            f"开放数据库可找到相似文献，但以下字段不一致：{'、'.join(mismatch_fields)}。",
                            "请核对原文 PDF 或数据库导出的标准引用格式。",
                            provider_trace,
                        )
                    return (
                        ReferenceStatus.LIKELY_REAL, best_score,
                        matched_sources, [],
                        "开放数据库可找到相似文献。",
                        "建议通过 CNKI 或图书馆数据库进一步确认。",
                        provider_trace,
                    )
            except Exception as e:
                LOGGER.warning("Reference search error: %s", e)
                provider_trace.append({
                    "provider": "search_reference",
                    "called": True,
                    "query": title[:80],
                    "status": "error",
                    "candidate_count": 0,
                    "error": str(e)[:100],
                })

        # 6. 本地公共管理题录库 + 中文权威库联网核验
        #    （国家哲社文献中心 / 知网 / 万方 / 维普，站内检索需配置 SERPER_API_KEY）
        local_results: List[Dict[str, Any]] = []
        chinese_results: List[Dict[str, Any]] = []
        zh_web_providers = {"ncpssd", "ncpssd_cn", "cnki", "wanfang", "cqvip"}
        if title:
            try:
                from backend.app.services.public_admin_academic_service import public_admin_academic_service as paas
                author_str = authors[0] if authors else ""
                local_results = paas.search_local(
                    title=title, author=author_str, year=year,
                    journal=parsed.get("journal", ""), top_k=5,
                )
                chinese_results = paas.search_chinese_social_science(title=title, author=author_str)

                # 6a. 本地题录库高相似命中
                for lr in local_results:
                    if (lr.get("_match_score", 0) or 0) >= 0.6:
                        matched_sources.append({
                            "provider": "本地公共管理中文文献库",
                            "matched_title": lr.get("title", ""),
                            "matched_doi": lr.get("doi", ""),
                            "matched_authors": [lr.get("first_author")] if lr.get("first_author") else [],
                            "matched_year": lr.get("year"),
                            "url": lr.get("source_url", ""),
                            "score": lr.get("_match_score", 0),
                            "raw": {"match_reason": "本地题录库命中"},
                        })

                # 6b. 中文权威库站内联网检索结果
                web_hits = [cr for cr in chinese_results if cr.get("provider") in zh_web_providers]
                for cr in web_hits:
                    ms = cr.get("match_score", 0) or 0
                    if cr.get("found") and ms >= 0.6:
                        matched_sources.append({
                            "provider": cr.get("provider_name") or cr.get("provider", "中文权威库"),
                            "matched_title": cr.get("title", ""),
                            "matched_doi": "",
                            "matched_authors": [author_str] if author_str else [],
                            "matched_year": None,
                            "url": cr.get("source_url", ""),
                            "score": ms,
                            "raw": {
                                "snippet": cr.get("snippet", ""),
                                "title_similarity": cr.get("title_similarity"),
                                "provider_id": cr.get("provider"),
                            },
                        })

                # 6c. 高置信：权威中文库站内检索到高度一致题名 → 较可能真实（计入已核验）
                if web_hits:
                    best_web = max(web_hits, key=lambda x: x.get("match_score", 0) or 0)
                    bw = best_web.get("match_score", 0) or 0
                    if bw >= 0.8:
                        pname = best_web.get("provider_name") or best_web.get("provider")
                        ts = best_web.get("title_similarity", 0) or 0
                        web_trace = [{
                            "provider": "chinese_social_science",
                            "called": True,
                            "status": "matched",
                            "query": title[:80],
                            "matched_title": best_web.get("title", "")[:120],
                            "source": best_web.get("provider"),
                            "source_name": pname,
                            "score": bw,
                            "title_similarity": ts,
                            "url": best_web.get("source_url", ""),
                        }]
                        return (
                            ReferenceStatus.LIKELY_REAL,
                            round(bw, 2),
                            matched_sources,
                            [],
                            f"在{pname}站内检索到高度一致的题名（标题相似度约{ts:.0%}），"
                            f"该文献真实存在的可能性高。",
                            "中文文献以知网、万方、维普、国家哲学社会科学文献中心等权威中文数据库的"
                            "收录为准；如需完全确认，可点开来源链接核对作者、卷、期、页码。",
                            web_trace,
                        )
            except Exception as e:
                LOGGER.warning("Local public admin search failed: %s", e)

        # Build detailed provider_trace
        try:
            from backend.app.services.public_admin_academic_service import public_admin_academic_service as paas
            provider_trace = paas.build_detailed_provider_trace(
                parsed, local_results, matched_sources, chinese_results
            )
        except Exception:
            pass  # provider_trace already defined, keep it

        # Rule-based fallback with Chinese confidence scoring
        status, risk_reason, suggestion = self._rule_based_check(parsed)
        confidence = compute_chinese_confidence(parsed, matched_sources)

        return (status, confidence, matched_sources, mismatch_fields, risk_reason, suggestion, provider_trace)

    def _rule_based_check(self, parsed: Dict[str, Any]) -> tuple:
        """基于规则的参考文献检查 — 增强中文文献支持"""
        title = parsed.get("title", "")
        authors = parsed.get("authors", [])
        year = parsed.get("year")
        doi = parsed.get("doi", "")
        journal = parsed.get("journal", "")
        publisher = parsed.get("publisher", "")
        is_chinese = any("一" <= c <= "鿿" for c in (title + journal + publisher))

        # DOI format check - distinguish CNKI-like DOI
        if doi:
            doi_type = detect_doi_type(doi)
            if doi_type in ("cnki", "cnki_like"):
                if title and authors and year:
                    return (
                        ReferenceStatus.INSUFFICIENT_OPEN_METADATA,
                        "检测到CNKI/中文学位论文类DOI。该DOI可能未被Crossref等国际数据库收录，"
                        "不能据此判定为伪造。建议通过CNKI、万方、维普或高校图书馆学位论文库进行人工核验。",
                        f"建议：1) 在CNKI博硕论文库中搜索题名「{title}」；"
                        f"2) 或直接访问 https://doi.org/{doi} 确认是否可解析。",
                    )
                return (
                    ReferenceStatus.INSUFFICIENT_OPEN_METADATA,
                    "检测到CNKI类DOI但参考文献字段不完整，无法完成自动化核验。",
                    "建议通过CNKI学位论文库搜索或访问DOI链接进行人工确认。",
                )
            if not re.match(r"^10\.\d{4,}/", doi):
                return (
                    ReferenceStatus.SUSPICIOUS,
                    "DOI 格式不正确，疑似伪造。",
                    "请检查 DOI 格式，标准格式为 10.xxxx/xxxx。",
                )

        # Year rationality
        if year:
            from datetime import datetime
            current_year = datetime.now().year
            if year > current_year + 1:
                return (
                    ReferenceStatus.SUSPICIOUS,
                    f"出版年份 {year} 晚于当前年份，明显不合理。",
                    "请检查引用年份是否正确。",
                )
            if year < 1900:
                return (
                    ReferenceStatus.SUSPICIOUS,
                    f"出版年份 {year} 异常。",
                    "请检查引用年份是否正确。",
                )

        # Title quality
        if title:
            if len(title) < 3:
                return (
                    ReferenceStatus.SUSPICIOUS,
                    "文献标题过短，信息不完整。",
                    "请补充完整的文献标题。",
                )
            has_cn = any("一" <= c <= "鿿" for c in title)
            has_en = bool(re.search(r"[a-zA-Z]{3,}", title))
            if has_cn and has_en and len(title) < 20:
                return (
                    ReferenceStatus.LIKELY_REAL_WITH_MISMATCH,
                    "标题存在中英文混杂，可能格式不规范。",
                    "请确认文献标题的原始语言。",
                )

        # Missing key fields
        missing = []
        if not title:
            missing.append("标题")
        if not authors:
            missing.append("作者")
        if not year and not doi:
            missing.append("年份")
        if missing:
            return (
                ReferenceStatus.PARSE_FAILED,
                f"参考文献解析不完整，缺少：{'、'.join(missing)}。",
                "请补充完整的参考文献信息（作者、题名、年份、期刊/出版社、卷期页码）。",
            )

        # Chinese-specific handling
        if is_chinese:
            venue = journal or publisher
            if venue and title and authors:
                return (
                    ReferenceStatus.INSUFFICIENT_OPEN_METADATA,
                    "已检索开放学术元数据源（Crossref/OpenAlex/SemanticScholar），"
                    "但该中文文献未获得高置信匹配。中文社科文献可能未被国际开放数据库完整收录。",
                    f"建议通过以下渠道人工核验：1) CNKI中国知网搜索题名「{title}」；"
                    f"2) 万方数据知识服务平台；3) 维普中文期刊服务平台；"
                    f"4) 国家哲学社会科学文献中心(ncpssd.org)；5) 高校图书馆数据库。",
                )

        return (
            ReferenceStatus.INSUFFICIENT_OPEN_METADATA,
            "已尝试开放学术元数据源（Crossref/OpenAlex/SemanticScholar）检索，"
            "但该中文文献未获得高置信匹配。中文社科文献可能未被国际开放数据库完整收录。"
            "建议通过以下渠道人工核验：1) 国家哲学社会科学文献中心(ncpssd.org)；"
            "2) 万方数据知识服务平台；3) 维普中文期刊服务平台；4) 知网CNKI；5) 高校图书馆数据库。",
            "建议补充文献的 DOI、ISBN 或官方 URL 以便系统自动核验。",
        )


    def _compute_reference_risk_level(
        self, total: int, verified: int, suspicious: int, not_found: int
    ) -> str:
        if total == 0:
            return "medium"
        sup_ratio = suspicious / total
        nf_ratio = not_found / total
        if sup_ratio > 0.3 or nf_ratio > 0.5:
            return "critical"
        elif sup_ratio > 0.15 or nf_ratio > 0.3:
            return "high"
        elif sup_ratio > 0.05 or nf_ratio > 0.15:
            return "medium"
        return "low"

    def _build_reference_summary(
        self, total: int, verified: int, suspicious: int, not_found: int
    ) -> str:
        parts = [f"共检测到 {total} 条参考文献。"]
        if verified > 0:
            parts.append(f"已核验 {verified} 条。")
        if suspicious > 0:
            parts.append(f"疑似伪造或 AI 生成 {suspicious} 条。")
        if not_found > 0:
            parts.append(f"开放数据库未检索到 {not_found} 条。")
        if suspicious > 0:
            parts.append("存在伪造参考文献风险，请重点核查。")
        elif not_found > total * 0.3:
            parts.append("较多文献无法在开放数据库中检索到，建议结合 CNKI 等中文数据库人工复核。")
        else:
            parts.append("参考文献整体可核验性较好。")
        return "".join(parts)


def use_external_apis_fallback() -> bool:
    return True


reference_auth_service = ReferenceAuthService()
