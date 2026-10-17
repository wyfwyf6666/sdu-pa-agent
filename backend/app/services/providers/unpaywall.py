"""Unpaywall provider adapter."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, Optional
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


class UnpaywallProvider(BaseProvider):
    BASE_URL = "https://api.unpaywall.org/v2"

    def __init__(self):
        self.email = os.getenv("UNPAYWALL_EMAIL", "")
        self._limiter = _RateLimiter(calls_per_second=0.5)
        self._cache = _SimpleCache()
        self._client = httpx.Client(timeout=DEFAULT_TIMEOUT)

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            provider_id="unpaywall",
            name="Unpaywall",
            name_zh="Unpaywall",
            category="international",
            requires_auth=not bool(self.email),
            enabled=True,
            priority="low",
            description="Unpaywall DOI verification (OA status)",
            base_url=self.BASE_URL,
        )

    def search_by_doi(self, doi: str) -> Optional[ProviderResult]:
        doi = doi.strip()
        if not doi:
            return ProviderResult(provider_id="unpaywall", provider_name="Unpaywall", found=False, status="failed", error="Empty DOI")

        cached = self._cache.get("up_doi", doi)
        if cached is not None:
            return cached

        self._limiter.wait()
        t0 = time.time()
        try:
            email_param = quote(self.email) if self.email else "research@example.com"
            url = f"{self.BASE_URL}/{quote(doi, safe='')}?email={email_param}"
            resp = self._client.get(url)
            latency = (time.time() - t0) * 1000
            if resp.status_code == 404:
                result = ProviderResult(provider_id="unpaywall", provider_name="Unpaywall", found=False, doi=doi, status="success", latency_ms=latency)
                self._cache.set(result, "up_doi", doi)
                return result
            resp.raise_for_status()
            data = resp.json()
            authors = [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in data.get("z_authors", [])]
            title = data.get("title", "")
            year = data.get("year")
            journal = data.get("journal_name", "")
            best_oa = data.get("best_oa_location", {}) or {}
            result = ProviderResult(
                provider_id="unpaywall", provider_name="Unpaywall", found=True,
                title=title, authors=authors, year=year, journal=journal,
                doi=data.get("doi", doi), url=best_oa.get("url", ""),
                match_score=1.0, match_reasons=["DOI exact match"],
                raw=data, status="success", latency_ms=latency, query=f"doi:{doi}",
            )
            self._cache.set(result, "up_doi", doi)
            return result
        except Exception as e:
            LOGGER.warning("Unpaywall DOI search error: %s", e)
            return ProviderResult(provider_id="unpaywall", provider_name="Unpaywall", found=False, doi=doi, status="failed", error=str(e))

    def search_by_metadata(self, title: str = "", authors: str = "", year: Optional[int] = None, journal: str = "") -> Optional[ProviderResult]:
        return ProviderResult(provider_id="unpaywall", provider_name="Unpaywall", found=False, status="disabled", error="Unpaywall only supports DOI lookup")
