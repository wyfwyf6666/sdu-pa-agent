"""Crossref provider adapter."""

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
        elapsed = now - self._last_call
        wait_time = max(0, 1.0 / self.rate - elapsed)
        if wait_time > 0:
            time.sleep(wait_time)
        self._last_call = time.time()


class CrossrefProvider(BaseProvider):
    """Crossref API provider."""

    BASE_URL = "https://api.crossref.org"

    def __init__(self):
        self.mailto = os.getenv("CROSSREF_MAILTO", "")
        self._limiter = _RateLimiter(calls_per_second=1.0)
        self._cache = _SimpleCache()
        self._client = httpx.Client(timeout=DEFAULT_TIMEOUT)

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            provider_id="crossref",
            name="Crossref",
            name_zh="Crossref",
            category="international",
            requires_auth=False,
            enabled=True,
            priority="high",
            description="Crossref REST API for DOI and bibliographic metadata lookup",
            base_url=self.BASE_URL,
        )

    def _headers(self) -> Dict[str, str]:
        return {"User-Agent": f"AcademicIntegrityChecker/1.0 (mailto:{self.mailto})"}

    def search_by_doi(self, doi: str) -> Optional[ProviderResult]:
        doi = doi.strip()
        if not doi:
            return ProviderResult(provider_id="crossref", provider_name="Crossref", found=False, status="failed", error="Empty DOI")

        cached = self._cache.get("cr_doi", doi)
        if cached is not None:
            return cached

        self._limiter.wait()
        t0 = time.time()
        try:
            url = f"{self.BASE_URL}/works/{quote(doi, safe='')}"
            resp = self._client.get(url, headers=self._headers())
            latency = (time.time() - t0) * 1000
            if resp.status_code == 404:
                result = ProviderResult(provider_id="crossref", provider_name="Crossref", found=False, doi=doi, status="success", latency_ms=latency, query=f"doi:{doi}")
                self._cache.set(result, "cr_doi", doi)
                return result
            resp.raise_for_status()
            data = resp.json()
            msg = data.get("message", {})
            authors = [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in msg.get("author", [])]
            title_list = msg.get("title", [])
            title = title_list[0] if title_list else ""
            year = None
            published = msg.get("published-print", {}) or msg.get("published-online", {}) or {}
            date_parts = published.get("date-parts", [[None]])[0]
            if date_parts and date_parts[0]:
                year = date_parts[0]
            container = msg.get("container-title", [])
            journal = container[0] if container else ""

            result = ProviderResult(
                provider_id="crossref", provider_name="Crossref", found=True,
                title=title, authors=authors, year=year, journal=journal,
                doi=msg.get("DOI", doi), url=msg.get("URL", ""),
                match_score=1.0, match_reasons=["DOI exact match"],
                raw=msg, status="success", latency_ms=latency, query=f"doi:{doi}",
            )
            self._cache.set(result, "cr_doi", doi)
            return result
        except Exception as e:
            LOGGER.warning("Crossref DOI search error: %s", e)
            return ProviderResult(provider_id="crossref", provider_name="Crossref", found=False, doi=doi, status="failed", error=str(e), latency_ms=(time.time() - t0) * 1000)

    def search_by_metadata(self, title: str = "", authors: str = "", year: Optional[int] = None, journal: str = "") -> Optional[ProviderResult]:
        if not title.strip():
            return ProviderResult(provider_id="crossref", provider_name="Crossref", found=False, status="failed", error="Empty title")

        parts = [title]
        if authors:
            parts.append(authors)
        query = " ".join(parts)
        cached = self._cache.get("cr_bib", query)
        if cached is not None:
            return cached

        self._limiter.wait()
        t0 = time.time()
        try:
            url = f"{self.BASE_URL}/works?query.bibliographic={quote(query)}&rows=3"
            resp = self._client.get(url, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            items = data.get("message", {}).get("items", [])
            latency = (time.time() - t0) * 1000
            if not items:
                result = ProviderResult(provider_id="crossref", provider_name="Crossref", found=False, status="success", latency_ms=latency, query=query[:200])
                self._cache.set(result, "cr_bib", query)
                return result
            item = items[0]

            item_authors = [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in item.get("author", [])]
            item_title = (item.get("title", []) or [""])[0]
            item_year = None
            pub = item.get("published-print", {}) or item.get("published-online", {}) or {}
            dp = pub.get("date-parts", [[None]])[0]
            if dp and dp[0]:
                item_year = dp[0]
            container = item.get("container-title", [])
            item_journal = container[0] if container else ""

            import difflib
            title_sim = difflib.SequenceMatcher(None, title.lower(), item_title.lower()).ratio()

            result = ProviderResult(
                provider_id="crossref", provider_name="Crossref", found=True,
                title=item_title, authors=item_authors, year=item_year, journal=item_journal,
                doi=item.get("DOI", ""), url=item.get("URL", ""),
                match_score=round(title_sim, 3), match_reasons=[f"Title similarity: {title_sim:.2f}"],
                raw=item, status="success", latency_ms=latency, query=query[:200],
            )
            self._cache.set(result, "cr_bib", query)
            return result
        except Exception as e:
            LOGGER.warning("Crossref bibliographic search error: %s", e)
            return ProviderResult(provider_id="crossref", provider_name="Crossref", found=False, status="failed", error=str(e))
