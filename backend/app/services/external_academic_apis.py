"""外部学术API客户端封装

封装 Crossref、OpenAlex、Semantic Scholar、Unpaywall 等开放学术API。
特性：超时控制、速率限制、重试机制、结果缓存、统一返回格式。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = float(os.getenv("ACADEMIC_CHECK_TIMEOUT_SECONDS", "8"))
CACHE_TTL_HOURS = int(os.getenv("ACADEMIC_CHECK_CACHE_TTL_HOURS", "24"))


# =============================================================================
# 缓存
# =============================================================================

class SimpleCache:
    """简单内存缓存"""

    def __init__(self, ttl_hours: int = CACHE_TTL_HOURS):
        self._store: Dict[str, tuple[Any, float]] = {}
        self.ttl = ttl_hours * 3600

    def _key(self, *args: Any) -> str:
        raw = json.dumps(args, sort_keys=True, default=str)
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, *args: Any) -> Optional[Any]:
        key = self._key(*args)
        entry = self._store.get(key)
        if entry is None:
            return None
        value, ts = entry
        if time.time() - ts > self.ttl:
            del self._store[key]
            return None
        return value

    def set(self, value: Any, *args: Any) -> None:
        key = self._key(*args)
        self._store[key] = (value, time.time())


_cache = SimpleCache()


# =============================================================================
# 速率限制器
# =============================================================================

class RateLimiter:
    """简单的令牌桶速率限制"""

    def __init__(self, calls_per_second: float = 1.0):
        self.rate = calls_per_second
        self._last_call = 0.0

    def wait(self) -> None:
        now = time.time()
        elapsed = now - self._last_call
        wait_time = max(0, 1.0 / self.rate - elapsed)
        if wait_time > 0:
            time.sleep(wait_time)
        self._last_call = time.time()


# =============================================================================
# 统一返回结构
# =============================================================================

def make_api_result(
    provider: str,
    found: bool,
    title: str = "",
    authors: Optional[List[str]] = None,
    year: Optional[int] = None,
    journal: str = "",
    doi: str = "",
    url: str = "",
    raw: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "provider": provider,
        "found": found,
        "title": title or "",
        "authors": authors or [],
        "year": year,
        "journal": journal or "",
        "doi": doi or "",
        "url": url or "",
        "raw": raw or {},
    }


# =============================================================================
# Crossref Client
# =============================================================================

class CrossrefClient:
    """Crossref API 客户端"""

    BASE_URL = "https://api.crossref.org"

    def __init__(self, mailto: str = ""):
        self.mailto = mailto or os.getenv("CROSSREF_MAILTO", "")
        self._limiter = RateLimiter(calls_per_second=1.0)
        self._client = httpx.Client(timeout=DEFAULT_TIMEOUT)

    @property
    def available(self) -> bool:
        return True  # Crossref 免费可用，无需 API key

    def _headers(self) -> Dict[str, str]:
        h = {"User-Agent": f"AcademicIntegrityChecker/1.0 (mailto:{self.mailto})"}
        return h

    def search_by_doi(self, doi: str) -> Dict[str, Any]:
        """通过 DOI 查询 Crossref"""
        doi = doi.strip()
        if not doi:
            return make_api_result("Crossref", False)

        cached = _cache.get("crossref_doi", doi)
        if cached is not None:
            return cached

        self._limiter.wait()
        try:
            url = f"{self.BASE_URL}/works/{quote(doi, safe='')}"
            resp = self._client.get(url, headers=self._headers())
            if resp.status_code == 404:
                result = make_api_result("Crossref", False, doi=doi)
                _cache.set(result, "crossref_doi", doi)
                return result
            resp.raise_for_status()
            data = resp.json()
            msg = data.get("message", {})
            authors = [
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in msg.get("author", [])
            ]
            title_list = msg.get("title", [])
            title = title_list[0] if title_list else ""
            year = None
            published = msg.get("published-print", {}) or msg.get("published-online", {}) or {}
            date_parts = published.get("date-parts", [[None]])[0]
            if date_parts and date_parts[0]:
                year = date_parts[0]

            journal = ""
            container = msg.get("container-title", [])
            if container:
                journal = container[0] if isinstance(container, list) else str(container)

            result = make_api_result(
                "Crossref", True,
                title=title, authors=authors, year=year,
                journal=journal, doi=msg.get("DOI", doi),
                url=msg.get("URL", ""), raw=msg,
            )
            _cache.set(result, "crossref_doi", doi)
            return result
        except Exception as e:
            LOGGER.warning("Crossref DOI search error: %s", e)
            return make_api_result("Crossref", False, doi=doi)

    def search_by_bibliographic(self, query: str) -> Dict[str, Any]:
        """通过文献信息查询"""
        if not query.strip():
            return make_api_result("Crossref", False)
        cached = _cache.get("crossref_bib", query)
        if cached is not None:
            return cached

        self._limiter.wait()
        try:
            url = f"{self.BASE_URL}/works?query.bibliographic={quote(query)}&rows=3"
            resp = self._client.get(url, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            items = data.get("message", {}).get("items", [])
            if not items:
                result = make_api_result("Crossref", False)
                _cache.set(result, "crossref_bib", query)
                return result
            return self._parse_work_item("Crossref", items[0])
        except Exception as e:
            LOGGER.warning("Crossref bibliographic search error: %s", e)
            return make_api_result("Crossref", False)

    def search_by_title_author_year(
        self, title: str, author: str = "", year: Optional[int] = None
    ) -> Dict[str, Any]:
        """通过标题 + 作者 + 年份查询"""
        parts = [title]
        if author:
            parts.append(author)
        query = " ".join(parts)
        result = self.search_by_bibliographic(query)
        # 如果返回结果，用年份做二次过滤
        if result["found"] and year and result["year"] and abs(result["year"] - year) > 2:
            result["found"] = False
        return result

    def _parse_work_item(self, provider: str, item: Dict[str, Any]) -> Dict[str, Any]:
        authors = [
            f"{a.get('given', '')} {a.get('family', '')}".strip()
            for a in item.get("author", [])
        ]
        title_list = item.get("title", [])
        title = title_list[0] if title_list else ""
        year = None
        published = item.get("published-print", {}) or item.get("published-online", {}) or {}
        date_parts = published.get("date-parts", [[None]])[0]
        if date_parts and date_parts[0]:
            year = date_parts[0]
        container = item.get("container-title", [])
        journal = container[0] if container else ""
        result = make_api_result(
            provider, True,
            title=title, authors=authors, year=year,
            journal=journal, doi=item.get("DOI", ""),
            url=item.get("URL", ""), raw=item,
        )
        return result


# =============================================================================
# OpenAlex Client
# =============================================================================

class OpenAlexClient:
    """OpenAlex API 客户端（免费、无需 API key）"""

    BASE_URL = "https://api.openalex.org"

    def __init__(self):
        self._limiter = RateLimiter(calls_per_second=0.8)  # OpenAlex 有速率限制
        self._client = httpx.Client(timeout=DEFAULT_TIMEOUT)

    @property
    def available(self) -> bool:
        return True

    def _headers(self) -> Dict[str, str]:
        return {"User-Agent": "AcademicIntegrityChecker/1.0 (mailto:research@example.com)"}

    def search_work_by_doi(self, doi: str) -> Dict[str, Any]:
        """通过 DOI 查询 OpenAlex"""
        doi = doi.strip()
        if not doi:
            return make_api_result("OpenAlex", False)

        cached = _cache.get("openalex_doi", doi)
        if cached is not None:
            return cached

        self._limiter.wait()
        try:
            url = f"{self.BASE_URL}/works/doi:{quote(doi, safe='')}"
            resp = self._client.get(url, headers=self._headers())
            if resp.status_code == 404:
                result = make_api_result("OpenAlex", False, doi=doi)
                _cache.set(result, "openalex_doi", doi)
                return result
            resp.raise_for_status()
            data = resp.json()
            return self._parse_work("OpenAlex", data)
        except Exception as e:
            LOGGER.warning("OpenAlex DOI search error: %s", e)
            return make_api_result("OpenAlex", False, doi=doi)

    def search_works(self, query: str) -> List[Dict[str, Any]]:
        """搜索作品"""
        if not query.strip():
            return []
        # Safety: truncate overly long queries
        if len(query) > 500:
            query = query[:500]
        cached = _cache.get("openalex_search", query)
        if cached is not None:
            return cached

        self._limiter.wait()
        try:
            url = f"{self.BASE_URL}/works?search={quote(query)}&per_page=5"
            resp = self._client.get(url, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            results = [self._parse_work("OpenAlex", w) for w in data.get("results", [])]
            _cache.set(results, "openalex_search", query)
            return results
        except Exception as e:
            LOGGER.warning("OpenAlex search error: %s", e)
            return []

    def search_by_title(self, title: str) -> Dict[str, Any]:
        """通过标题搜索"""
        results = self.search_works(title)
        if results:
            return results[0]
        return make_api_result("OpenAlex", False)

    def _parse_work(self, provider: str, data: Dict[str, Any]) -> Dict[str, Any]:
        authors = [
            a.get("author", {}).get("display_name", "")
            for a in data.get("authorships", [])
        ]
        title = data.get("title", "")
        year = data.get("publication_year")
        journal = data.get("primary_location", {}).get("source", {}).get("display_name", "")
        doi = data.get("doi", "").replace("https://doi.org/", "") if data.get("doi") else ""
        return make_api_result(
            provider, True,
            title=title, authors=authors, year=year,
            journal=journal, doi=doi,
            url=data.get("id", ""), raw=data,
        )


# =============================================================================
# Semantic Scholar Client
# =============================================================================

class SemanticScholarClient:
    """Semantic Scholar API 客户端"""

    BASE_URL = "https://api.semanticscholar.org/graph/v1"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
        self._limiter = RateLimiter(calls_per_second=1.0 if self.api_key else 0.5)
        self._client = httpx.Client(timeout=DEFAULT_TIMEOUT)

    @property
    def available(self) -> bool:
        return True  # Semantic Scholar 免费可用，有 API key 速率更高

    def _headers(self) -> Dict[str, Any]:
        h = {}
        if self.api_key:
            h["x-api-key"] = self.api_key
        return h

    def search_paper_by_doi(self, doi: str) -> Dict[str, Any]:
        """通过 DOI 查询"""
        doi = doi.strip()
        if not doi:
            return make_api_result("SemanticScholar", False)

        cached = _cache.get("s2_doi", doi)
        if cached is not None:
            return cached

        self._limiter.wait()
        try:
            url = f"{self.BASE_URL}/paper/DOI:{quote(doi, safe='')}?fields=title,authors,year,journal,externalIds,url"
            resp = self._client.get(url, headers=self._headers())
            if resp.status_code == 404:
                result = make_api_result("SemanticScholar", False, doi=doi)
                _cache.set(result, "s2_doi", doi)
                return result
            resp.raise_for_status()
            data = resp.json()
            result = self._parse_paper("SemanticScholar", data)
            _cache.set(result, "s2_doi", doi)
            return result
        except Exception as e:
            LOGGER.warning("SemanticScholar DOI search error: %s", e)
            return make_api_result("SemanticScholar", False, doi=doi)

    def search_paper_by_title(self, title: str) -> Dict[str, Any]:
        """通过标题搜索"""
        if not title.strip():
            return make_api_result("SemanticScholar", False)
        # Safety: truncate long titles (should not be full document)
        if len(title) > 500:
            title = title[:500]

        cached = _cache.get("s2_title", title)
        if cached is not None:
            return cached

        self._limiter.wait()
        try:
            url = f"{self.BASE_URL}/paper/search?query={quote(title)}&limit=3&fields=title,authors,year,journal,externalIds,url"
            resp = self._client.get(url, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            papers = data.get("data", [])
            if not papers:
                result = make_api_result("SemanticScholar", False)
                _cache.set(result, "s2_title", title)
                return result
            result = self._parse_paper("SemanticScholar", papers[0])
            _cache.set(result, "s2_title", title)
            return result
        except Exception as e:
            LOGGER.warning("SemanticScholar title search error: %s", e)
            return make_api_result("SemanticScholar", False)

    def _parse_paper(self, provider: str, data: Dict[str, Any]) -> Dict[str, Any]:
        authors = [a.get("name", "") for a in data.get("authors", [])]
        title = data.get("title", "")
        year = data.get("year")
        journal = data.get("journal", {}).get("name", "") if isinstance(data.get("journal"), dict) else ""
        external_ids = data.get("externalIds", {})
        doi = external_ids.get("DOI", "")
        return make_api_result(
            provider, True,
            title=title, authors=authors, year=year,
            journal=journal, doi=doi,
            url=data.get("url", ""), raw=data,
        )


# =============================================================================
# Unpaywall Client
# =============================================================================

class UnpaywallClient:
    """Unpaywall API 客户端（用于验证 DOI 是否存在）"""

    BASE_URL = "https://api.unpaywall.org/v2"

    def __init__(self, email: str = ""):
        self.email = email or os.getenv("UNPAYWALL_EMAIL", "")
        self._limiter = RateLimiter(calls_per_second=0.5)
        self._client = httpx.Client(timeout=DEFAULT_TIMEOUT)

    @property
    def available(self) -> bool:
        return True  # 可以有礼貌地使用（需要 email）

    def search_by_doi(self, doi: str) -> Dict[str, Any]:
        """通过 DOI 查询"""
        doi = doi.strip()
        if not doi:
            return make_api_result("Unpaywall", False)

        cached = _cache.get("unpaywall_doi", doi)
        if cached is not None:
            return cached

        self._limiter.wait()
        try:
            email_param = quote(self.email) if self.email else "research@example.com"
            url = f"{self.BASE_URL}/{quote(doi, safe='')}?email={email_param}"
            resp = self._client.get(url)
            if resp.status_code == 404:
                result = make_api_result("Unpaywall", False, doi=doi)
                _cache.set(result, "unpaywall_doi", doi)
                return result
            resp.raise_for_status()
            data = resp.json()
            authors = [
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in data.get("z_authors", [])
            ]
            title = data.get("title", "")
            year = data.get("year")
            journal = data.get("journal_name", "")
            result = make_api_result(
                "Unpaywall", True,
                title=title, authors=authors, year=year,
                journal=journal, doi=data.get("doi", doi),
                url=data.get("best_oa_location", {}).get("url", "") if data.get("best_oa_location") else "",
                raw=data,
            )
            _cache.set(result, "unpaywall_doi", doi)
            return result
        except Exception as e:
            LOGGER.warning("Unpaywall DOI search error: %s", e)
            return make_api_result("Unpaywall", False, doi=doi)


# =============================================================================
# 聚合客户端
# =============================================================================

class ExternalAcademicAPIClient:
    """外部学术API聚合客户端，统一调用各个provider"""

    def __init__(self):
        self.crossref = CrossrefClient()
        self.openalex = OpenAlexClient()
        self.semantic_scholar = SemanticScholarClient()
        self.unpaywall = UnpaywallClient()

    def search_doi(self, doi: str) -> List[Dict[str, Any]]:
        """在所有可用 provider 中查询 DOI"""
        results: List[Dict[str, Any]] = []
        providers = [
            ("Crossref", self.crossref.search_by_doi),
            ("OpenAlex", self.openalex.search_work_by_doi),
            ("SemanticScholar", self.semantic_scholar.search_paper_by_doi),
            ("Unpaywall", self.unpaywall.search_by_doi),
        ]
        for name, func in providers:
            try:
                result = func(doi)
                if result["found"]:
                    results.append(result)
            except Exception as e:
                LOGGER.warning("Provider %s failed for DOI %s: %s", name, doi, e)
        return results

    def search_reference(
        self, title: str = "", authors: str = "", year: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """通过文献元数据搜索"""
        results: List[Dict[str, Any]] = []
        # 先尝试 Crossref
        try:
            query_parts = [title]
            if authors:
                query_parts.append(authors)
            query = " ".join(q for q in query_parts if q)
            r = self.crossref.search_by_bibliographic(query)
            if r["found"]:
                results.append(r)
        except Exception as e:
            LOGGER.warning("Crossref reference search error: %s", e)

        # OpenAlex
        try:
            oa_results = self.openalex.search_works(title)
            for r in oa_results:
                if r["found"]:
                    results.append(r)
        except Exception as e:
            LOGGER.warning("OpenAlex reference search error: %s", e)

        # Semantic Scholar
        try:
            r = self.semantic_scholar.search_paper_by_title(title)
            if r["found"]:
                results.append(r)
        except Exception as e:
            LOGGER.warning("SemanticScholar reference search error: %s", e)

        return results


# 全局实例
external_academic_client = ExternalAcademicAPIClient()
