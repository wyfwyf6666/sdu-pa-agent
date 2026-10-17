"""Provider abstraction layer for reference checking.

Defines the BaseProvider ABC and shared data classes used by all providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ProviderInfo:
    provider_id: str
    name: str
    name_zh: str
    category: str  # "international" | "chinese" | "local" | "manual"
    requires_auth: bool = False
    enabled: bool = True
    priority: str = "medium"  # "high" | "medium" | "low" | "off"
    description: str = ""
    base_url: str = ""


@dataclass
class ProviderResult:
    provider_id: str
    provider_name: str
    found: bool = False
    title: str = ""
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    journal: str = ""
    doi: str = ""
    url: str = ""
    match_score: float = 0.0
    match_reasons: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    called: bool = True
    status: str = "success"  # "success" | "failed" | "disabled" | "unauthorized" | "rate_limited"
    query: str = ""
    candidate_count: int = 0
    latency_ms: float = 0.0


@dataclass
class Candidate:
    title: str = ""
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    venue: str = ""
    doi: str = ""
    url: str = ""
    source_type: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)
    match_score: float = 0.0
    match_reasons: List[str] = field(default_factory=list)


class BaseProvider(ABC):
    """Abstract base class for all reference checking providers."""

    @property
    @abstractmethod
    def info(self) -> ProviderInfo:
        """Return provider metadata."""
        ...

    @abstractmethod
    def search_by_doi(self, doi: str) -> Optional[ProviderResult]:
        """Search for a reference by DOI."""
        ...

    @abstractmethod
    def search_by_metadata(
        self,
        title: str,
        authors: str = "",
        year: Optional[int] = None,
        journal: str = "",
    ) -> Optional[ProviderResult]:
        """Search for a reference by bibliographic metadata."""
        ...

    def is_available(self) -> bool:
        """Check if the provider is currently reachable and configured."""
        return self.info.enabled
