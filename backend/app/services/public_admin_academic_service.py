"""公共管理中文学术元数据增强库

提供本地公共管理文献检索、provider source registry、弱匹配搜索。
不保存付费全文，只保存题录元数据。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from difflib import SequenceMatcher
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

LOGGER = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "backend" / "data" / "public_admin_academic"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# Source Registry
# ============================================================================

ACADEMIC_METADATA_SOURCES: List[Dict[str, Any]] = [
    {"id": "openalex", "name": "OpenAlex", "category": "international_scholarly_metadata",
     "fetch_mode": "api", "requires_auth": False, "priority": "high", "enabled": True},
    {"id": "crossref", "name": "Crossref", "category": "international_scholarly_metadata",
     "fetch_mode": "api", "requires_auth": False, "priority": "high", "enabled": True},
    {"id": "semantic_scholar", "name": "Semantic Scholar", "category": "international_scholarly_metadata",
     "fetch_mode": "api", "requires_auth": False, "priority": "medium", "enabled": True},
    {"id": "datacite", "name": "DataCite", "category": "international_scholarly_metadata",
     "fetch_mode": "api", "requires_auth": False, "priority": "medium", "enabled": bool(os.getenv("DATACITE_ENABLED", "true").lower() == "true")},
    {"id": "unpaywall", "name": "Unpaywall", "category": "international_scholarly_metadata",
     "fetch_mode": "api", "requires_auth": False, "priority": "medium", "enabled": True},
    {"id": "doaj", "name": "DOAJ", "category": "international_scholarly_metadata",
     "fetch_mode": "api", "requires_auth": False, "priority": "medium",
     "enabled": bool(os.getenv("DOAJ_ENABLED", "true").lower() == "true")},
    {"id": "ncpssd", "name": "国家哲学社会科学文献中心", "category": "chinese_social_science",
     "fetch_mode": "search_snippet", "requires_auth": False, "priority": "high", "enabled": True,
     "note": "无官方API时使用Serper公开搜索site:ncpssd.org弱匹配"},
    {"id": "wanfang_open", "name": "万方开放平台", "category": "chinese_scholarly_metadata",
     "fetch_mode": "api", "requires_auth": True, "priority": "high",
     "enabled": bool(os.getenv("WANFANG_APP_KEY", "")), "note": "需配置WANFANG_APP_KEY"},
    {"id": "cnki_snippet", "name": "CNKI公开检索", "category": "chinese_scholarly_metadata",
     "fetch_mode": "search_snippet", "requires_auth": False, "priority": "manual_check",
     "enabled": bool(os.getenv("CNKI_SNIPPET_SEARCH_ENABLED", "true").lower() == "true"),
     "note": "仅用搜素引擎公开结果弱匹配，不抓取付费页面"},
    {"id": "vip_snippet", "name": "维普公开检索", "category": "chinese_scholarly_metadata",
     "fetch_mode": "search_snippet", "requires_auth": False, "priority": "manual_check",
     "enabled": bool(os.getenv("VIP_SNIPPET_SEARCH_ENABLED", "true").lower() == "true"),
     "note": "仅用搜索引擎公开结果弱匹配"},
    {"id": "local_public_admin_db", "name": "本地公共管理中文文献库", "category": "public_admin_journal",
     "fetch_mode": "user_import", "requires_auth": False, "priority": "high", "enabled": True},
    {"id": "manual_cnki", "name": "CNKI（人工核验）", "category": "manual_check",
     "fetch_mode": "manual_only", "requires_auth": True, "priority": "manual_check", "enabled": True},
    {"id": "manual_wanfang", "name": "万方（人工核验）", "category": "manual_check",
     "fetch_mode": "manual_only", "requires_auth": True, "priority": "manual_check", "enabled": True},
    {"id": "manual_library", "name": "高校图书馆数据库", "category": "manual_check",
     "fetch_mode": "manual_only", "requires_auth": True, "priority": "manual_check", "enabled": True},
]


# ============================================================================
# Public Admin Journal Seed
# ============================================================================

PUBLIC_ADMIN_JOURNALS = [
    "公共管理学报", "中国行政管理", "行政论坛", "行政管理改革",
    "公共行政评论", "北京行政学院学报", "国家行政学院学报",
    "社会保障研究", "人口与发展", "人口与经济",
    "中国社会保障", "中国民政", "中国社会工作",
    "华中科技大学学报(社会科学版)", "浙江社会科学", "南京社会科学",
    "理论探索", "求实", "领导科学", "探索",
    "社会科学", "社会科学战线", "学术论坛",
    "东岳论丛", "学习与实践", "江汉论坛",
]

PUBLIC_ADMIN_TOPICS = [
    "公共管理", "城市治理", "数字政府", "智慧治理", "基层治理",
    "社区治理", "公共服务", "政府购买服务", "社会保障", "养老服务",
    "居家养老", "智慧养老", "医疗保障", "营商环境", "政务服务",
    "公共政策", "政策工具", "政策文本", "政策扩散", "协同治理",
    "风险治理", "应急管理", "社会治理", "城市社区",
]


# ============================================================================
# Local Academic Work DB
# ============================================================================

class PublicAdminAcademicDB:
    """本地公共管理中文文献题录库（JSON文件存储）"""

    def __init__(self):
        self._db_path = DATA_DIR / "works.json"
        self._works: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        if self._db_path.exists():
            try:
                with open(self._db_path, "r", encoding="utf-8") as f:
                    self._works = json.load(f)
                LOGGER.info("Loaded %d public admin academic works", len(self._works))
            except Exception as e:
                LOGGER.warning("Failed to load works DB: %s", e)
                self._works = {}

    def _save(self):
        with open(self._db_path, "w", encoding="utf-8") as f:
            json.dump(self._works, f, ensure_ascii=False, indent=2)

    def _make_id(self, title: str, authors: str, year: Any) -> str:
        raw = f"{title}|{authors}|{year}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def add(self, work: Dict[str, Any]) -> str:
        wid = work.get("id") or self._make_id(
            work.get("title", ""),
            work.get("first_author", ""),
            work.get("year", ""),
        )
        work["id"] = wid
        work.setdefault("imported_at", datetime.now().isoformat())
        work.setdefault("metadata_quality_score", self._quality_score(work))
        self._works[wid] = work
        self._save()
        return wid

    def _quality_score(self, work: Dict[str, Any]) -> float:
        score = 0.0
        if work.get("title"): score += 0.25
        if work.get("authors_json") or work.get("first_author"): score += 0.20
        if work.get("year"): score += 0.15
        if work.get("journal") or work.get("publisher"): score += 0.15
        if work.get("doi") or work.get("source_url"): score += 0.15
        if work.get("abstract"): score += 0.05
        if work.get("keywords_json"): score += 0.05
        return round(min(1.0, score), 2)

    def search(self, title: str = "", author: str = "", year: Any = None,
               journal: str = "", top_k: int = 10) -> List[Dict[str, Any]]:
        """检索本地公共管理文献库"""
        results: List[tuple[float, Dict[str, Any]]] = []

        for work in self._works.values():
            score = 0.0
            wt = (work.get("title") or "").lower()
            wn = (work.get("normalized_title") or wt).lower()

            if title:
                qt = title.lower().strip().rstrip(".")
                # Exact match
                if qt == wt or qt == wn:
                    score += 0.60
                # Fuzzy match
                else:
                    sim = SequenceMatcher(None, qt[:100], wt[:100]).ratio()
                    score += 0.50 * sim

            if author and work.get("first_author"):
                if author.lower().strip() in (work.get("first_author") or "").lower():
                    score += 0.20

            if year and work.get("year"):
                try:
                    if abs(int(year) - int(work["year"])) <= 1:
                        score += 0.10
                except (ValueError, TypeError):
                    pass

            if journal and work.get("journal"):
                jsim = SequenceMatcher(None, journal.lower()[:60],
                                       (work["journal"] or "").lower()[:60]).ratio()
                score += 0.10 * jsim

            if score > 0.10:
                results.append((score, work))

        results.sort(key=lambda x: x[0], reverse=True)
        return [{**w, "_match_score": round(s, 3)} for s, w in results[:top_k]]

    def stats(self) -> Dict[str, Any]:
        return {"total_works": len(self._works)}


# ============================================================================
# Public Admin Academic Service
# ============================================================================

class PublicAdminAcademicService:
    """公共管理学术元数据增强服务"""

    def __init__(self):
        self.db = PublicAdminAcademicDB()
        self.serper_key = os.getenv("SERPER_API_KEY", "")
        self._sources = {s["id"]: s for s in ACADEMIC_METADATA_SOURCES}

    def get_sources(self) -> List[Dict[str, Any]]:
        return ACADEMIC_METADATA_SOURCES

    def search_local(self, title: str = "", author: str = "", year: Any = None,
                     journal: str = "", top_k: int = 10) -> List[Dict[str, Any]]:
        return self.db.search(title=title, author=author, year=year, journal=journal, top_k=top_k)

    def import_works(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """批量导入文献题录"""
        imported = 0
        duplicates = 0
        errors = 0

        for rec in records:
            try:
                title = rec.get("title", "").strip()
                authors = rec.get("authors", rec.get("authors_json", []))
                if isinstance(authors, str):
                    try:
                        authors = json.loads(authors)
                    except json.JSONDecodeError:
                        authors = [a.strip() for a in authors.split(";") if a.strip()]

                work = {
                    "title": title,
                    "normalized_title": title.lower().strip().rstrip("."),
                    "authors_json": json.dumps(authors, ensure_ascii=False),
                    "first_author": authors[0] if authors else "",
                    "year": rec.get("year"),
                    "journal": rec.get("journal", ""),
                    "publisher": rec.get("publisher", ""),
                    "volume": rec.get("volume", ""),
                    "issue": rec.get("issue", ""),
                    "pages": rec.get("pages", ""),
                    "doi": rec.get("doi", ""),
                    "keywords_json": json.dumps(rec.get("keywords", []), ensure_ascii=False),
                    "abstract": rec.get("abstract", ""),
                    "source_url": rec.get("source_url", ""),
                    "source_platform": rec.get("source_platform", "manual_import"),
                }

                wid = self.db.add(work)
                if wid:
                    imported += 1
                else:
                    duplicates += 1
            except Exception as e:
                LOGGER.warning("Import error: %s", e)
                errors += 1

        return {"imported": imported, "duplicates": duplicates, "errors": errors}

    def search_chinese_social_science(self, title: str, author: str = "") -> List[Dict[str, Any]]:
        """搜索中文社科源（Serper site搜索 + 本地库）"""
        results = []

        # 1. Local DB first
        local = self.db.search(title=title, author=author, top_k=3)
        for w in local:
            results.append({
                "provider": "local_public_admin_db",
                "found": True,
                "match_score": w.get("_match_score", 0),
                "title": w.get("title", ""),
                "authors": json.loads(w.get("authors_json", "[]")),
                "year": w.get("year"),
                "journal": w.get("journal", ""),
                "source_url": w.get("source_url", ""),
                "match_reason": "本地公共管理文献库匹配" if w.get("_match_score", 0) > 0.5 else "本地库弱匹配",
            })

        # 2. Serper site search for NCPSSD
        if self.serper_key and title:
            snippet_results = self._serper_site_search(title, author)
            results.extend(snippet_results)

        return results

    def _serper_site_search(self, title: str, author: str = "") -> List[Dict[str, Any]]:
        """通过 Serper 在权威中文学术库站内检索，按真实标题相似度打分。

        检索国家哲社文献中心、知网、万方、维普；查询用引号精确短语，
        仅采信返回标题与目标标题高度一致的结果，避免“主题相近但非同一篇”的误配。
        需配置 SERPER_API_KEY（serper.dev，注册即送免费额度）。
        """
        if not (self.serper_key and title):
            return []

        import http.client

        sites: List[tuple] = [
            ("ncpssd", "国家哲学社会科学文献中心", "site:ncpssd.org"),
            ("ncpssd_cn", "国家哲学社会科学文献中心", "site:ncpssd.cn"),
        ]
        if os.getenv("CNKI_SNIPPET_SEARCH_ENABLED", "true").lower() == "true":
            sites.append(("cnki", "中国知网", "site:cnki.net"))
        sites.append(("wanfang", "万方数据", "site:wanfangdata.com.cn"))
        if os.getenv("VIP_SNIPPET_SEARCH_ENABLED", "true").lower() == "true":
            sites.append(("cqvip", "维普中文期刊", "site:cqvip.com"))

        title_short = re.sub(r"\s*\[[JDMCRENSP]\]\s*$", "", title[:80]).strip()
        author_short = author[:20] if author else ""

        def clean(t: str) -> str:
            # 搜索结果标题常带 “- 中国知网”“_万方数据” 等站点/期刊尾巴，取分隔符前主体
            t = re.split(r"[\-_–—|【\u3014]", t or "")[0]
            return re.sub(r"[\s《》<>「」\"'.,:;·（）()\[\]，。、？?！!]", "", t)

        def tsim(a: str, b: str) -> float:
            ca, cb = clean(a), clean(b)
            if not ca or not cb:
                return 0.0
            return SequenceMatcher(None, ca, cb).ratio()

        def _one_site(site_tuple):
            provider_id, provider_name, site_prefix = site_tuple
            out: List[Dict[str, Any]] = []
            # 只用标题精确短语做站内检索；作者名通常不在页面可索引文本中，
            # 强制双引号会导致零结果。标题相似度阈值仍负责排除“主题相近但非同篇”。
            query = f'{site_prefix} "{title_short}"'
            try:
                conn = http.client.HTTPSConnection("google.serper.dev", timeout=8)
                payload = json.dumps({"q": query[:300], "gl": "cn", "hl": "zh-cn"})
                headers = {"X-API-KEY": self.serper_key, "Content-Type": "application/json"}
                conn.request("POST", "/search", payload, headers)
                resp = conn.getresponse()
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    for item in data.get("organic", [])[:3]:
                        hit_title = item.get("title", "") or ""
                        link = item.get("link", "") or ""
                        ts = tsim(title, hit_title)
                        if ts < 0.45:  # 引号精确检索下仍要求标题高度一致
                            continue
                        score = round(min(0.95, 0.55 + 0.40 * ts), 3)  # 0.45→0.73, 1.0→0.95
                        out.append({
                            "provider": provider_id,
                            "provider_name": provider_name,
                            "found": True,
                            "match_score": score,
                            "title": hit_title,
                            "source_url": link,
                            "snippet": item.get("snippet", ""),
                            "title_similarity": round(ts, 3),
                            "match_reason": f"{provider_name}站内检索到高度一致题名（标题相似度{ts:.0%}）",
                            "_key": link or hit_title,
                        })
                conn.close()
            except Exception as e:
                LOGGER.debug("Serper site search %s failed: %s", provider_id, e)
            return out

        # 各站点并发检索，避免串行累积超时（中文文献较多时，单条最坏延迟由 ~5×8s 降到 ~12s）
        from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
        candidates: List[Dict[str, Any]] = []
        pool = ThreadPoolExecutor(max_workers=max(1, len(sites)))
        try:
            futures = [pool.submit(_one_site, s) for s in sites]
            for fut in as_completed(futures, timeout=12):
                try:
                    candidates.extend(fut.result(timeout=1))
                except Exception:
                    pass
        except FuturesTimeout:
            pass  # 个别站点超时：保留已完成站点的结果
        finally:
            pool.shutdown(wait=False)

        results: List[Dict[str, Any]] = []
        seen = set()
        for r in candidates:
            key = r.pop("_key", "")
            if not key or key in seen:
                continue
            seen.add(key)
            results.append(r)
        results.sort(key=lambda r: r.get("match_score", 0), reverse=True)
        return results

    def build_detailed_provider_trace(self, ref: Dict[str, Any],
                                      local_results: List[Dict[str, Any]],
                                      api_results: List[Dict[str, Any]],
                                      chinese_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """构建详细的 provider_trace"""
        trace = []

        # Local DB
        trace.append({
            "provider": "local_public_admin_db",
            "called": True,
            "status": "matched" if any(r.get("match_score", 0) > 0.5 for r in local_results) else "no_match",
            "candidate_count": len(local_results),
            "top_candidates": [
                {"title": r.get("title", "")[:60], "match_score": r.get("match_score", 0)}
                for r in local_results[:2]
            ],
            "error": None,
        })

        # Chinese social science search（国家哲社/知网/万方/维普 站内检索）
        zh_web = {"ncpssd", "ncpssd_cn", "cnki", "wanfang", "cqvip"}
        zh_hits = [r for r in chinese_results if r.get("provider") in zh_web]
        trace.append({
            "provider": "chinese_social_science",
            "called": bool(self.serper_key),
            "status": "matched" if zh_hits else ("no_match" if self.serper_key else "not_configured"),
            "candidate_count": len(zh_hits),
            "top_candidates": [
                {"title": r.get("title", "")[:60], "source": r.get("provider", "")}
                for r in zh_hits[:2]
            ],
            "error": None if self.serper_key else "SERPER_API_KEY not configured",
        })

        # International sources
        for provider in ["crossref", "openalex", "semantic_scholar"]:
            provider_results = [r for r in api_results if r.get("provider", "").lower() == provider]
            trace.append({
                "provider": provider,
                "called": True,
                "status": "matched" if provider_results else "no_match",
                "candidate_count": len(provider_results),
                "top_candidates": [
                    {"title": r.get("title", "")[:60], "match_score": r.get("match_score", r.get("score", 0))}
                    for r in provider_results[:2]
                ],
                "error": None,
            })

        return trace

    def format_reference_status(self, status: str) -> str:
        """将后端状态码转为前端展示中文"""
        mapping = {
            "verified": "已核验",
            "likely_real": "较可能真实",
            "likely_real_with_mismatch": "字段不一致",
            "insufficient_open_metadata": "格式完整但开放元数据不足",
            "not_found": "未检索到",
            "suspicious": "疑似异常",
            "parse_failed": "解析失败",
            "check_failed": "校验异常",
        }
        return mapping.get(status, status)

    def compute_format_score(self, parsed: Dict[str, Any]) -> float:
        """计算参考文献格式完整度（0-1）"""
        score = 0.0
        if parsed.get("title") and len(parsed["title"]) > 5: score += 0.30
        if parsed.get("authors") and len(parsed["authors"]) > 0: score += 0.25
        if parsed.get("year") and 1900 < parsed["year"] < 2030: score += 0.15
        if parsed.get("journal") or parsed.get("publisher"): score += 0.15
        if parsed.get("doi") or parsed.get("url"): score += 0.10
        if parsed.get("volume") or parsed.get("pages"): score += 0.05
        return round(min(1.0, score), 2)


# Global instance
public_admin_academic_service = PublicAdminAcademicService()
