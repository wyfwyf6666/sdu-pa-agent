"""Chinese social science reference provider.

Searches for Chinese social science references via Serper (site-specific search)
on NCPSSD, and other open Chinese academic platforms.

NOTE: This provider does NOT crawl CNKI/万方/维普 behind paywalls.
It only uses public search engine results.
"""

from __future__ import annotations

import json
import logging
import os
import time
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from backend.app.services.providers.base import BaseProvider, ProviderInfo, ProviderResult

LOGGER = logging.getLogger(__name__)

NCPSSD_SITE = "ncpssd.cn"
CNKI_OPEN_SITES = ["cnki.net", "cnki.com.cn"]


class ChineseSocialScienceProvider(BaseProvider):
    """Chinese social science literature provider using Serper site search.

    Modes:
    - disabled: completely off (default when no SERPER_API_KEY)
    - manual_import: relies on user-imported bibliography (handled by LocalDBProvider)
    - official_api: reserved for future CNKI/万方官方API (requires API_KEY)
    """

    def __init__(self):
        self.serper_key = os.getenv("SERPER_API_KEY", "")
        self._search_sites = [NCPSSD_SITE]

    @property
    def info(self) -> ProviderInfo:
        mode = "disabled"
        if self.serper_key:
            mode = "serper_site_search"
        return ProviderInfo(
            provider_id="chinese_social_science",
            name="Chinese Social Science",
            name_zh="中文社会科学文献",
            category="chinese",
            requires_auth=not bool(self.serper_key),
            enabled=bool(self.serper_key),
            priority="medium" if self.serper_key else "off",
            description=f"Serper-based search on {', '.join(self._search_sites)}. Mode: {mode}",
            base_url="https://google.serper.dev",
        )

    def search_by_doi(self, doi: str) -> Optional[ProviderResult]:
        if not self.serper_key:
            return ProviderResult(provider_id="chinese_social_science", provider_name="中文社科文献", found=False, status="disabled", error="No SERPER_API_KEY configured", query=f"doi:{doi}")
        return ProviderResult(provider_id="chinese_social_science", provider_name="中文社科文献", found=False, status="success", error="Chinese social science platforms do not have open DOI resolution", query=f"doi:{doi}")

    def search_by_metadata(self, title: str = "", authors: str = "", year: Optional[int] = None, journal: str = "") -> Optional[ProviderResult]:
        if not self.serper_key:
            return ProviderResult(provider_id="chinese_social_science", provider_name="中文社科文献", found=False, status="disabled", error="No SERPER_API_KEY configured")
        if not title.strip():
            return ProviderResult(provider_id="chinese_social_science", provider_name="中文社科文献", found=False, status="failed", error="Empty title")

        query_parts = [title]
        if authors:
            query_parts.append(authors)
        site_query = " ".join(f"site:{s}" for s in self._search_sites)
        search_query = f"{' '.join(query_parts)} {site_query}"

        t0 = time.time()
        try:
            import http.client
            conn = http.client.HTTPSConnection("google.serper.dev", timeout=10)
            payload = json.dumps({"q": search_query[:300], "gl": "cn", "hl": "zh-cn"})
            headers = {"X-API-KEY": self.serper_key, "Content-Type": "application/json"}
            conn.request("POST", "/search", payload, headers)
            resp = conn.getresponse()
            latency = (time.time() - t0) * 1000
            if resp.status != 200:
                conn.close()
                return ProviderResult(provider_id="chinese_social_science", provider_name="中文社科文献", found=False, status="failed", error=f"Serper HTTP {resp.status}", latency_ms=latency, query=search_query[:200])
            data = json.loads(resp.read().decode("utf-8"))
            conn.close()

            organic = data.get("organic", [])
            if not organic:
                return ProviderResult(provider_id="chinese_social_science", provider_name="中文社科文献", found=False, status="success", candidate_count=0, latency_ms=latency, query=search_query[:200])

            best_score = 0.0
            best_item = organic[0]
            for item in organic:
                snippet = item.get("snippet", "")
                if snippet:
                    sim = SequenceMatcher(None, title.lower(), snippet.lower()).ratio()
                    if sim > best_score:
                        best_score = sim
                        best_item = item

            if best_score < 0.2:
                return ProviderResult(provider_id="chinese_social_science", provider_name="中文社科文献", found=False, status="success", candidate_count=len(organic), latency_ms=latency, query=search_query[:200])

            return ProviderResult(
                provider_id="chinese_social_science", provider_name="中文社科文献", found=True,
                title=best_item.get("title", ""), authors=[], year=year,
                journal="", doi="", url=best_item.get("link", ""),
                match_score=round(best_score, 3),
                match_reasons=[f"Snippet similarity: {best_score:.2f} (via Serper on {', '.join(self._search_sites)})"],
                raw=best_item, status="success", latency_ms=latency,
                query=search_query[:200], candidate_count=len(organic),
            )
        except Exception as e:
            LOGGER.warning("Chinese social science search error: %s", e)
            return ProviderResult(provider_id="chinese_social_science", provider_name="中文社科文献", found=False, status="failed", error=str(e))
