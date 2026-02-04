"""
Fleet-level false positive budget enforcement.

Provides aggregated alert counts across assets (site/fleet) to enforce
alarms/month budgets beyond per-unit limits.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Callable

try:
    from sqlalchemy.orm import Session
except Exception:  # pragma: no cover - optional dependency
    Session = None  # type: ignore

from ..persistence.repositories import AlertRepository, AssetRepository

logger = logging.getLogger(__name__)


@dataclass
class FleetBudgetSnapshot:
    """Fleet budget state for a period."""
    year: int
    month: int
    site_id: str
    total_actionable_alerts: int
    total_assets: int


class FleetBudgetService:
    """Aggregate alert counts across assets for fleet-level budget checks."""

    def __init__(self, session_factory: Optional[Callable[[], Session]] = None):
        self.session_factory = session_factory
        # In-memory fallback if no DB
        self._memory_counts = {}

    def _with_session(self):
        if self.session_factory is None:
            return None
        try:
            return self.session_factory()
        except Exception as exc:  # pragma: no cover
            logger.warning(f"FleetBudgetService: failed to open session: {exc}")
            return None

    def count_actionable_for_asset(self, asset_id: str, when: datetime) -> int:
        """Count actionable alerts for a single asset in a given month."""
        session = self._with_session()
        if session is None:
            key = (asset_id, when.year, when.month)
            return self._memory_counts.get(key, 0)
        try:
            repo = AlertRepository(session)
            return repo.count_by_type_and_month(
                asset_id=asset_id,
                alert_type="actionable",
                year=when.year,
                month=when.month,
            )
        finally:
            session.close()

    def count_actionable_for_site(self, site_id: str, when: datetime) -> FleetBudgetSnapshot:
        """Count actionable alerts across a site (fleet) in a given month."""
        session = self._with_session()
        if session is None:
            # Fall back to unknown fleet size and zero counts
            return FleetBudgetSnapshot(
                year=when.year,
                month=when.month,
                site_id=site_id,
                total_actionable_alerts=0,
                total_assets=0,
            )
        try:
            alert_repo = AlertRepository(session)
            asset_repo = AssetRepository(session)
            total_alerts = alert_repo.count_by_type_and_month_for_site(
                site_id=site_id,
                alert_type="actionable",
                year=when.year,
                month=when.month,
            )
            total_assets = asset_repo.count_by_site(site_id)
            return FleetBudgetSnapshot(
                year=when.year,
                month=when.month,
                site_id=site_id,
                total_actionable_alerts=total_alerts,
                total_assets=total_assets,
            )
        finally:
            session.close()

    def record_actionable_alert(self, asset_id: str, when: datetime):
        """Record an actionable alert in memory for non-persistent mode."""
        key = (asset_id, when.year, when.month)
        self._memory_counts[key] = self._memory_counts.get(key, 0) + 1
