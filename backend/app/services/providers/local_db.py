"""Local bibliography database provider.

Searches the local SQLite/JSON bibliography for reference matches.
"""

from __future__ import annotations

import json
import logging
import os
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.services.providers.base import BaseProvider, ProviderInfo, ProviderResult

LOGGER = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[4]
LOCAL_WORKS_PATH = ROOT_DIR / "backend" / "data" / "public_admin_academic" / "works.json"


class LocalDBProvider(BaseProvider):
    """Searches the local bibliography database (JSON or SQLite)."""

    def __init__(self):
        self._works: Optional[List[Dict[str, Any]]] = None
        self._initialized = False

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            provider_id="local_db",
            name="Local Bibliography DB",
            name_zh="本地题录库",
            category="local",
            requires_auth=False,
            enabled=True,
            priority="high",
            description="User-imported and seeded bibliography records",
            base_url=str(LOCAL_WORKS_PATH),
        )

    def _ensure_loaded(self):
        if self._initialized:
            return
        self._works = []
        if LOCAL_WORKS_PATH.exists():
            try:
                with open(LOCAL_WORKS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self._works = data
                elif isinstance(data, dict):
                    self._works = list(data.values())
                LOGGER.info("Local DB provider loaded %d works", len(self._works))
            except Exception as e:
                LOGGER.warning("Failed to load local works: %s", e)
        self._initialized = True

    def search_by_doi(self, doi: str) -> Optional[ProviderResult]:
        self._ensure_loaded()
        doi_lower = doi.strip().lower()
        for w in self._works:
            w_doi = (w.get("doi") or "").lower()
            if doi_lower and w_doi and doi_lower == w_doi:
                return self._to_result(w, match_score=1.0, match_reasons=["DOI exact match"], query=f"doi:{doi}")
        return ProviderResult(provider_id="local_db", provider_name="本地题录库", found=False, doi=doi, status="success", query=f"doi:{doi}")

    def search_by_metadata(self, title: str = "", authors: str = "", year: Optional[int] = None, journal: str = "") -> Optional[ProviderResult]:
        self._ensure_loaded()
        if not title.strip():
            return ProviderResult(provider_id="local_db", provider_name="本地题录库", found=False, status="failed", error="Empty title")

        title_lower = title.lower().strip()
        best_score = 0.0
        best_work = None

        for w in self._works:
            w_title = (w.get("title") or "").lower().strip()
            if not w_title:
                continue
            sim = SequenceMatcher(None, title_lower, w_title).ratio()
            if sim > best_score:
                best_score = sim
                best_work = w

        if best_work and best_score >= 0.5:
            return self._to_result(best_work, match_score=round(best_score, 3), match_reasons=[f"Title similarity: {best_score:.2f} (local DB)"], query=title[:200])
        if best_work and best_score >= 0.3:
            return self._to_result(best_work, match_score=round(best_score, 3), match_reasons=[f"Weak title similarity: {best_score:.2f} (local DB)"], query=title[:200])
        return ProviderResult(provider_id="local_db", provider_name="本地题录库", found=False, status="success", query=title[:200])

    def _to_result(self, work: Dict[str, Any], match_score: float = 0.0, match_reasons: Optional[List[str]] = None, query: str = "") -> ProviderResult:
        authors = work.get("authors", [])
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(";") if a.strip()]
        return ProviderResult(
            provider_id="local_db", provider_name="本地题录库", found=True,
            title=work.get("title", ""), authors=authors,
            year=work.get("year"), journal=work.get("journal", ""),
            doi=work.get("doi", ""), url=work.get("url", ""),
            match_score=match_score, match_reasons=match_reasons or [],
            raw=work, status="success", query=query,
        )

    def add_work(self, work: Dict[str, Any]) -> None:
        self._ensure_loaded()
        self._works.append(work)
        self._save()

    def bulk_import(self, works: List[Dict[str, Any]]) -> int:
        self._ensure_loaded()
        count = 0
        existing_titles = {w.get("title", "").lower().strip() for w in self._works}
        for w in works:
            if w.get("title", "").lower().strip() not in existing_titles:
                self._works.append(w)
                existing_titles.add(w.get("title", "").lower().strip())
                count += 1
        self._save()
        return count

    def _save(self):
        LOCAL_WORKS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOCAL_WORKS_PATH, "w", encoding="utf-8") as f:
            json.dump(self._works, f, ensure_ascii=False, indent=2)

    def stats(self) -> Dict[str, Any]:
        self._ensure_loaded()
        return {"total_works": len(self._works) if self._works else 0}
