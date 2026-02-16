"""
Work Order Repository — persistence for AI work order lifecycle.

Provides:
- Create WO from LLM service outputs (interpret, auto-create)
- Update status, priority, provider, verification results
- List/filter WOs by site, status, priority, asset
- Link source_alert_id for PdM-originated WOs
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .models import WorkOrderModel

logger = logging.getLogger(__name__)


class WorkOrderRepository:
    """Repository for AI-generated work order persistence."""

    def __init__(self, session: Session):
        self.session = session

    # ── Create ────────────────────────────────────────────────────────

    def create(
        self,
        asset_id: str,
        site_id: str,
        title: str,
        description: str = "",
        priority: str = "medium",
        wo_type: str = "reactive",
        source: str = "manual",
        estimated_cost: float = 0.0,
        source_alert_id: Optional[str] = None,
        provider: str = "in_house",
    ) -> WorkOrderModel:
        """Create a new work order row and return it."""
        wo_id = f"WO-{datetime.now(timezone.utc).strftime('%Y')}-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc)

        wo = WorkOrderModel(
            wo_id=wo_id,
            asset_id=asset_id,
            site_id=site_id,
            wo_type=wo_type,
            priority=priority,
            status="open",
            cost=estimated_cost,
            description=f"[{source}] {title}\n\n{description}",
            provider=provider,
            opened_at=now,
            created_at=now,
            source_alert_id=source_alert_id,
        )
        self.session.add(wo)
        self.session.flush()
        logger.info("Created WO %s for asset %s (source=%s)", wo_id, asset_id, source)
        return wo

    def create_from_interpret(
        self,
        interpret_result: Dict[str, Any],
        site_id: str = "default",
    ) -> WorkOrderModel:
        """Persist a WO from NL-interpret response."""
        return self.create(
            asset_id=interpret_result.get("asset_id") or "TBD",
            site_id=site_id,
            title=interpret_result.get("title", "Maintenance Request"),
            description=interpret_result.get("description", ""),
            priority=interpret_result.get("priority", "medium"),
            wo_type="reactive",
            source="ai_nlp",
        )

    def create_from_auto(
        self,
        auto_result: Dict[str, Any],
        site_id: str = "default",
        source_alert_id: Optional[str] = None,
    ) -> WorkOrderModel:
        """Persist a WO from auto-create (PdM signals) response."""
        return self.create(
            asset_id=auto_result.get("asset_id", "unknown"),
            site_id=site_id,
            title=auto_result.get("title", "PdM Auto-Created WO"),
            description=auto_result.get("description", ""),
            priority=auto_result.get("priority", "high"),
            wo_type="planned",
            source="ai_sensor",
            source_alert_id=source_alert_id,
        )

    # ── Read ──────────────────────────────────────────────────────────

    def get_by_wo_id(self, wo_id: str) -> Optional[WorkOrderModel]:
        return self.session.query(WorkOrderModel).filter(
            WorkOrderModel.wo_id == wo_id
        ).first()

    def list_by_site(
        self,
        site_id: str,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 100,
    ) -> List[WorkOrderModel]:
        q = self.session.query(WorkOrderModel).filter(
            WorkOrderModel.site_id == site_id
        )
        if status:
            q = q.filter(WorkOrderModel.status == status)
        if priority:
            q = q.filter(WorkOrderModel.priority == priority)
        return q.order_by(WorkOrderModel.opened_at.desc()).limit(limit).all()

    def list_by_asset(self, asset_id: str, limit: int = 50) -> List[WorkOrderModel]:
        return (
            self.session.query(WorkOrderModel)
            .filter(WorkOrderModel.asset_id == asset_id)
            .order_by(WorkOrderModel.opened_at.desc())
            .limit(limit)
            .all()
        )

    # ── Update ────────────────────────────────────────────────────────

    def update_status(self, wo_id: str, status: str) -> bool:
        """Transition WO status. Returns True if row found."""
        updated = self.session.query(WorkOrderModel).filter(
            WorkOrderModel.wo_id == wo_id
        ).update({"status": status})
        if updated:
            logger.info("WO %s status → %s", wo_id, status)
        return bool(updated)

    def update_priority(self, wo_id: str, priority: str) -> bool:
        updated = self.session.query(WorkOrderModel).filter(
            WorkOrderModel.wo_id == wo_id
        ).update({"priority": priority})
        return bool(updated)

    def update_provider(self, wo_id: str, provider: str) -> bool:
        updated = self.session.query(WorkOrderModel).filter(
            WorkOrderModel.wo_id == wo_id
        ).update({"provider": provider})
        return bool(updated)

    def dispatch(self, wo_id: str, provider: str) -> bool:
        """Record dispatch timestamp and provider."""
        now = datetime.now(timezone.utc)
        updated = self.session.query(WorkOrderModel).filter(
            WorkOrderModel.wo_id == wo_id
        ).update({
            "status": "in_progress",
            "provider": provider,
            "dispatched_at": now,
        })
        if updated:
            logger.info("WO %s dispatched to %s", wo_id, provider)
        return bool(updated)

    def close(self, wo_id: str, resolution: str = "", actual_cost: Optional[float] = None) -> bool:
        """Close a WO with resolution notes."""
        now = datetime.now(timezone.utc)
        updates: Dict[str, Any] = {
            "status": "completed",
            "closed_at": now,
            "resolution": resolution,
        }
        if actual_cost is not None:
            updates["cost"] = actual_cost
        updated = self.session.query(WorkOrderModel).filter(
            WorkOrderModel.wo_id == wo_id
        ).update(updates)
        if updated:
            logger.info("WO %s closed", wo_id)
        return bool(updated)

    def reopen(self, wo_id: str, reason: str = "") -> bool:
        """Reopen a WO after failed verification."""
        updated = self.session.query(WorkOrderModel).filter(
            WorkOrderModel.wo_id == wo_id
        ).update({
            "status": "open",
            "resolution": reason,
            "closed_at": None,
        })
        if updated:
            logger.info("WO %s reopened: %s", wo_id, reason)
        return bool(updated)
