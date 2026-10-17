"""Semantic Scholar provider adapter."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

from backend.app.services.providers.base import BaseProvider, ProviderInfo, ProviderResult

LOGGER = logging.getLogger(__name__)
DEFAULT_TIMEOUT = float(os.getenv("ACADEMIC_CHECK_TIMEOUT_SECONDS", "8"))
CACHE_TTL_HOURS = int(os.getenv("ACADEMIC_CHECK_CACHE_TTL_HOURS", "24"))


class _SimpleCache:
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


class _RateLimiter:
    def __init__(self, calls_per_second: float = 1.0):
        self.rate = calls_per_second
        self._last_call = 0.0

    def wait(self) -> None:
        now = time.time()
        wait_time = max(0, 1.0 / self.rate - (now - self._last_call))
        if wait_time > 0:
            time.sleep(wait_time)
        self._last_call = time.time()


class SemanticScholarProvider(BaseProvider):
    BASE_URL = "https://api.semanticscholar.org/graph/v1"

    def __init__(self):
        self.api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
        self._limiter = _RateLimiter(calls_per_second=1.0 if self.api_key else 0.5)
        self._cache = _SimpleCache()
        self._client = httpx.Client(timeout=DEFAULT_TIMEOUT)

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            provider_id="semantic_scholar",
            name="Semantic Scholar",
            name_zh="Semantic Scholar",
            category="international",
            requires_auth=bool(self.api_key),
            enabled=True,
            priority="high" if self.api_key else "medium",
            description="Semantic Scholar Academic Graph API",
            base_url=self.BASE_URL,
        )

    def _headers(self) -> Dict[str, str]:
        h = {}
        if self.api_key:
            h["x-api-key"] = self.api_key
        return h

    def _parse_paper(self, data: Dict[str, Any]) -> ProviderResult:
        authors = [a.get("name", "") for a in data.get("authors", [])]
        title = data.get("title", "")
        year = data.get("year")
        journal = data.get("journal", {}).get("name", "") if isinstance(data.get("journal"), dict) else ""
        external_ids = data.get("externalIds", {})
        doi = external_ids.get("DOI", "")
        return ProviderResult(
            provider_id="semantic_scholar", provider_name="Semantic Scholar", found=True,
            title=title, authors=authors, year=year, journal=journal, doi=doi,
            url=data.get("url", ""), raw=data, status="success",
        )

    def search_by_doi(self, doi: str) -> Optional[ProviderResult]:
        doi = doi.strip()
        if not doi:
            return ProviderResult(provider_id="semantic_scholar", provider_name="Semantic Scholar", found=False, status="failed", error="Empty DOI")

        cached = self._cache.get("s2_doi", doi)
        if cached is not None:
            return cached

        self._limiter.wait()
        t0 = time.time()
        try:
            fields = "title,authors,year,journal,externalIds,url"
            url = f"{self.BASE_URL}/paper/DOI:{quote(doi, safe='')}?fields={fields}"
            resp = self._client.get(url, headers=self._headers())
            latency = (time.time() - t0) * 1000
            if resp.status_code == 404:
                result = ProviderResult(provider_id="semantic_scholar", provider_name="Semantic Scholar", found=False, doi=doi, status="success", latency_ms=latency)
                self._cache.set(result, "s2_doi", doi)
                return result
            resp.raise_for_status()
            data = resp.json()
            result = self._parse_paper(data)
            result.latency_ms = latency
            result.match_score = 1.0
            result.match_reasons = ["DOI exact match"]
            result.query = f"doi:{doi}"
            self._cache.set(result, "s2_doi", doi)
            return result
        except Exception as e:
            LOGGER.warning("SemanticScholar DOI search error: %s", e)
            return ProviderResult(provider_id="semantic_scholar", provider_name="Semantic Scholar", found=False, doi=doi, status="failed", error=str(e))

    def search_by_metadata(self, title: str = "", authors: str = "", year: Optional[int] = None, journal: str = "") -> Optional[ProviderResult]:
        if not title.strip():
            return ProviderResult(provider_id="semantic_scholar", provider_name="Semantic Scholar", found=False, status="failed", error="Empty title")
        if len(title) > 500:
            title = title[:500]

        cached = self._cache.get("s2_title", title)
        if cached is not None:
            return cached

        self._limiter.wait()
        t0 = time.time()
        try:
            fields = "title,authors,year,journal,externalIds,url"
            url = f"{self.BASE_URL}/paper/search?query={quote(title)}&limit=3&fields={fields}"
            resp = self._client.get(url, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            papers = data.get("data", [])
            latency = (time.time() - t0) * 1000
            if not papers:
                result = ProviderResult(provider_id="semantic_scholar", provider_name="Semantic Scholar", found=False, status="success", latency_ms=latency, query=title[:200], candidate_count=0)
                self._cache.set(result, "s2_title", title)
                return result
            result = self._parse_paper(papers[0])
            result.latency_ms = latency
            result.query = title[:200]
            result.candidate_count = len(papers)

            import difflib
            title_sim = difflib.SequenceMatcher(None, title.lower(), result.title.lower()).ratio()
            result.match_score = round(title_sim, 3)
            result.match_reasons = [f"Title similarity: {title_sim:.2f}"]
            self._cache.set(result, "s2_title", title)
            return result
        except Exception as e:
            LOGGER.warning("SemanticScholar metadata search error: %s", e)
            return ProviderResult(provider_id="semantic_scholar", provider_name="Semantic Scholar", found=False, status="failed", error=str(e))
