"""Provider abstraction layer for reference checking.

Usage:
    from backend.app.services.providers import get_provider_registry
    registry = get_provider_registry()
    results = registry.search_with_trace(parsed_ref)
"""

from backend.app.services.providers.base import BaseProvider, ProviderInfo, ProviderResult, Candidate
from backend.app.services.providers.registry import ProviderRegistry, get_provider_registry

__all__ = [
    "BaseProvider",
    "ProviderInfo",
    "ProviderResult",
    "Candidate",
    "ProviderRegistry",
    "get_provider_registry",
]
