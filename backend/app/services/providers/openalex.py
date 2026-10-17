"""OpenAlex provider adapter."""

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


class OpenAlexProvider(BaseProvider):
    BASE_URL = "https://api.openalex.org"

    def __init__(self):
        self._limiter = _RateLimiter(calls_per_second=0.8)
        self._cache = _SimpleCache()
        self._client = httpx.Client(timeout=DEFAULT_TIMEOUT)

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            provider_id="openalex",
            name="OpenAlex",
            name_zh="OpenAlex",
            category="international",
            requires_auth=False,
            enabled=True,
            priority="high",
            description="OpenAlex open catalog of scholarly works",
            base_url=self.BASE_URL,
        )

    def _headers(self) -> Dict[str, str]:
        return {"User-Agent": "AcademicIntegrityChecker/1.0 (mailto:research@example.com)"}

    def _parse_work(self, data: Dict[str, Any]) -> ProviderResult:
        authors = [a.get("author", {}).get("display_name", "") for a in data.get("authorships", [])]
        title = data.get("title", "")
        year = data.get("publication_year")
        journal = data.get("primary_location", {}).get("source", {}).get("display_name", "")
        doi = data.get("doi", "").replace("https://doi.org/", "") if data.get("doi") else ""
        return ProviderResult(
            provider_id="openalex", provider_name="OpenAlex", found=True,
            title=title, authors=authors, year=year, journal=journal, doi=doi,
            url=data.get("id", ""), raw=data, status="success",
        )

    def search_by_doi(self, doi: str) -> Optional[ProviderResult]:
        doi = doi.strip()
        if not doi:
            return ProviderResult(provider_id="openalex", provider_name="OpenAlex", found=False, status="failed", error="Empty DOI")

        cached = self._cache.get("oa_doi", doi)
        if cached is not None:
            return cached

        self._limiter.wait()
        t0 = time.time()
        try:
            url = f"{self.BASE_URL}/works/doi:{quote(doi, safe='')}"
            resp = self._client.get(url, headers=self._headers())
            latency = (time.time() - t0) * 1000
            if resp.status_code == 404:
                result = ProviderResult(provider_id="openalex", provider_name="OpenAlex", found=False, doi=doi, status="success", latency_ms=latency)
                self._cache.set(result, "oa_doi", doi)
                return result
            resp.raise_for_status()
            data = resp.json()
            result = self._parse_work(data)
            result.latency_ms = latency
            result.match_score = 1.0
            result.match_reasons = ["DOI exact match"]
            result.query = f"doi:{doi}"
            self._cache.set(result, "oa_doi", doi)
            return result
        except Exception as e:
            LOGGER.warning("OpenAlex DOI search error: %s", e)
            return ProviderResult(provider_id="openalex", provider_name="OpenAlex", found=False, doi=doi, status="failed", error=str(e))

    def search_by_metadata(self, title: str = "", authors: str = "", year: Optional[int] = None, journal: str = "") -> Optional[ProviderResult]:
        if not title.strip():
            return ProviderResult(provider_id="openalex", provider_name="OpenAlex", found=False, status="failed", error="Empty title")
        if len(title) > 500:
            title = title[:500]

        cached = self._cache.get("oa_search", title)
        if cached is not None:
            return cached

        self._limiter.wait()
        t0 = time.time()
        try:
            url = f"{self.BASE_URL}/works?search={quote(title)}&per_page=3"
            resp = self._client.get(url, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            latency = (time.time() - t0) * 1000
            if not results:
                result = ProviderResult(provider_id="openalex", provider_name="OpenAlex", found=False, status="success", latency_ms=latency, query=title[:200], candidate_count=0)
                self._cache.set(result, "oa_search", title)
                return result
            best = self._parse_work(results[0])
            best.latency_ms = latency
            best.query = title[:200]
            best.candidate_count = len(results)

            import difflib
            title_sim = difflib.SequenceMatcher(None, title.lower(), best.title.lower()).ratio()
            best.match_score = round(title_sim, 3)
            best.match_reasons = [f"Title similarity: {title_sim:.2f}"]
            self._cache.set(best, "oa_search", title)
            return best
        except Exception as e:
            LOGGER.warning("OpenAlex metadata search error: %s", e)
            return ProviderResult(provider_id="openalex", provider_name="OpenAlex", found=False, status="failed", error=str(e))
