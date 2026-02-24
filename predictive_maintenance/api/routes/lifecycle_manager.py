"""Runtime lifecycle manager for route-scoped services.

Centralizes long-lived in-memory objects used by API routes:
- per-asset PdM systems
- per-site orchestrators

Includes bounded cache policies to prevent unbounded memory growth.
"""

from __future__ import annotations

import logging
import os
from collections import OrderedDict
from threading import RLock
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        parsed = int(os.getenv(name, str(default)))
        return max(1, parsed)
    except Exception:
        return default


class RuntimeLifecycleManager:
    """Manages lifecycle/caching of route runtime dependencies."""

    def __init__(
        self,
        max_pdm_systems: Optional[int] = None,
        max_orchestrators: Optional[int] = None,
    ):
        self.max_pdm_systems = max_pdm_systems or _env_int("PDM_PDM_SYSTEM_CACHE_SIZE", 512)
        self.max_orchestrators = max_orchestrators or _env_int("PDM_ORCHESTRATOR_CACHE_SIZE", 64)
        self._pdm_systems: "OrderedDict[str, Any]" = OrderedDict()
        self._orchestrators: "OrderedDict[str, Any]" = OrderedDict()
        self._lock = RLock()

    @property
    def pdm_systems(self) -> Dict[str, Any]:
        """Read/write compatibility view for legacy callers."""
        return self._pdm_systems

    @property
    def orchestrators(self) -> Dict[str, Any]:
        """Read/write compatibility view for legacy callers."""
        return self._orchestrators

    def _evict_if_needed(self, cache: "OrderedDict[str, Any]", max_size: int, cache_name: str) -> None:
        while len(cache) > max_size:
            evicted_key, _ = cache.popitem(last=False)
            logger.info("Evicted %s cache key due to bounded policy: %s", cache_name, evicted_key)

    def get_pdm_system(self, asset_id: str) -> Any:
        """Get or create a PdM system for an asset."""
        with self._lock:
            if asset_id in self._pdm_systems:
                system = self._pdm_systems.pop(asset_id)
                self._pdm_systems[asset_id] = system
                return system

        from ...config import settings
        from ...integration.advanced_system import create_pdm_system

        session_factory = None
        if settings.persistence.enabled:
            try:
                from ...persistence.database import get_session_factory

                session_factory = get_session_factory()
            except Exception:
                session_factory = None

        created = create_pdm_system(
            asset_id,
            site_id=settings.site_id,
            session_factory=session_factory,
        )

        with self._lock:
            self._pdm_systems[asset_id] = created
            self._evict_if_needed(self._pdm_systems, self.max_pdm_systems, "pdm_systems")
        return created

    def get_orchestrator(self, site_id: Optional[str] = None) -> Any:
        """Get or create a site-level orchestrator."""
        from ...config import settings

        effective_site = site_id or settings.site_id or "default"
        with self._lock:
            if effective_site in self._orchestrators:
                orch = self._orchestrators.pop(effective_site)
                self._orchestrators[effective_site] = orch
                return orch

        try:
            from ...agents.orchestrator import PDMModelOrchestrator

            created = PDMModelOrchestrator(site_id=effective_site)
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "Orchestrator unavailable for site %s, falling back to kernel path: %s",
                effective_site,
                exc,
            )
            created = None

        with self._lock:
            self._orchestrators[effective_site] = created
            self._evict_if_needed(self._orchestrators, self.max_orchestrators, "orchestrators")
        return created


_runtime_manager = RuntimeLifecycleManager()


def get_runtime_lifecycle_manager() -> RuntimeLifecycleManager:
    """Return singleton runtime lifecycle manager."""
    return _runtime_manager
