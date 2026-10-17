"""Provider registry - aggregates all reference checking providers."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from backend.app.services.providers.base import BaseProvider, ProviderResult
from backend.app.services.providers.crossref import CrossrefProvider
from backend.app.services.providers.openalex import OpenAlexProvider
from backend.app.services.providers.semantic_scholar import SemanticScholarProvider
from backend.app.services.providers.unpaywall import UnpaywallProvider
from backend.app.services.providers.local_db import LocalDBProvider
from backend.app.services.providers.chinese_social_science import ChineseSocialScienceProvider

LOGGER = logging.getLogger(__name__)


class ProviderRegistry:
    """Registry that aggregates all reference checking providers.

    Supports querying by category (international / chinese / local / manual)
    and respects priority ordering.
    """

    def __init__(self):
        self._providers: Dict[str, BaseProvider] = {}
        self._init_defaults()

    def _init_defaults(self):
        self.register(CrossrefProvider())
        self.register(OpenAlexProvider())
        self.register(SemanticScholarProvider())
        self.register(UnpaywallProvider())
        self.register(LocalDBProvider())
        self.register(ChineseSocialScienceProvider())

    def register(self, provider: BaseProvider) -> None:
        self._providers[provider.info.provider_id] = provider

    def get(self, provider_id: str) -> Optional[BaseProvider]:
        return self._providers.get(provider_id)

    def list_all(self) -> List[BaseProvider]:
        return list(self._providers.values())

    def list_enabled(self, categories: Optional[List[str]] = None) -> List[BaseProvider]:
        providers = [p for p in self._providers.values() if p.info.enabled]
        if categories:
            providers = [p for p in providers if p.info.category in categories]
        providers.sort(key=lambda p: {"high": 0, "medium": 1, "low": 2, "off": 3}.get(p.info.priority, 1))
        return providers

    def search_by_doi(self, doi: str, categories: Optional[List[str]] = None) -> List[ProviderResult]:
        results: List[ProviderResult] = []
        for provider in self.list_enabled(categories):
            try:
                result = provider.search_by_doi(doi)
                if result and result.found:
                    results.append(result)
            except Exception as e:
                LOGGER.warning("Provider %s search_by_doi failed: %s", provider.info.provider_id, e)
        return results

    def search_by_metadata(self, title: str = "", authors: str = "", year: Optional[int] = None, journal: str = "", categories: Optional[List[str]] = None) -> List[ProviderResult]:
        results: List[ProviderResult] = []
        for provider in self.list_enabled(categories):
            try:
                result = provider.search_by_metadata(title=title, authors=authors, year=year, journal=journal)
                if result and result.found:
                    results.append(result)
            except Exception as e:
                LOGGER.warning("Provider %s search_by_metadata failed: %s", provider.info.provider_id, e)
        return results

    def search_with_trace(self, parsed_ref: Dict[str, Any], categories: Optional[List[str]] = None, skip_chinese_for_non_zh: bool = True) -> List[ProviderResult]:
        """Search all enabled providers and return results with full trace.

        Args:
            parsed_ref: Dict with keys: title, authors, year, journal, doi
            categories: Optional filter by provider category
            skip_chinese_for_non_zh: If True, skip chinese providers for non-Chinese refs
        """
        doi = (parsed_ref.get("doi") or "").strip()
        title = str(parsed_ref.get("title") or "").strip()
        authors = str(parsed_ref.get("authors") or "").strip()
        if isinstance(parsed_ref.get("authors"), list):
            authors = " ".join(parsed_ref.get("authors"))
        year = parsed_ref.get("year")
        journal = str(parsed_ref.get("journal") or "").strip()
        language = parsed_ref.get("language", "")
        is_zh = bool(language == "zh" or any('一' <= c <= '鿿' for c in title))

        all_results: List[ProviderResult] = []
        trace: List[Dict[str, Any]] = []

        for provider in self.list_enabled(categories):
            if skip_chinese_for_non_zh and not is_zh and provider.info.category == "chinese":
                continue
            t0 = time.time()
            try:
                result = None
                if doi:
                    result = provider.search_by_doi(doi)
                if (not result or not result.found) and title:
                    md_result = provider.search_by_metadata(title=title, authors=authors, year=year, journal=journal)
                    if result and result.found:
                        pass
                    else:
                        result = md_result

                if result is None:
                    result = ProviderResult(
                        provider_id=provider.info.provider_id,
                        provider_name=provider.info.name_zh or provider.info.name,
                        found=False, status="failed", error="No search performed",
                    )

                all_results.append(result)
                trace.append({
                    "provider": provider.info.provider_id,
                    "called": True,
                    "query": result.query or title[:200],
                    "status": result.status,
                    "candidate_count": result.candidate_count,
                    "found": result.found,
                    "score": result.match_score,
                    "matched_title": result.title[:100] if result.found else "",
                    "error": result.error,
                    "latency_ms": round(result.latency_ms, 1) if result.latency_ms else 0,
                })
            except Exception as e:
                LOGGER.warning("Provider %s trace failed: %s", provider.info.provider_id, e)
                trace.append({
                    "provider": provider.info.provider_id,
                    "called": True,
                    "status": "failed",
                    "error": str(e),
                    "found": False,
                })

        return all_results

    def provider_status(self) -> Dict[str, Any]:
        status = {}
        for p in self._providers.values():
            status[p.info.provider_id] = {
                "name": p.info.name,
                "name_zh": p.info.name_zh,
                "category": p.info.category,
                "enabled": p.info.enabled,
                "priority": p.info.priority,
                "requires_auth": p.info.requires_auth,
            }
        return status


_provider_registry: Optional[ProviderRegistry] = None


def get_provider_registry() -> ProviderRegistry:
    global _provider_registry
    if _provider_registry is None:
        _provider_registry = ProviderRegistry()
    return _provider_registry
