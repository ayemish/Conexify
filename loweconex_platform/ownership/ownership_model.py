"""
Ownership Model — RACI-ready metric-to-owner assignment engine.

Supports per-metric ownership with org hierarchy overrides
(Global → Region → Banner → Store) and effective date versioning.
Extends the existing operating_model.RACIMatrix pattern but is
metric-centric rather than activity-centric.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from loweconex_platform.ownership.metric_catalog import Quadrant

logger = logging.getLogger(__name__)


class OwnerRole(str, Enum):
    """Organizational owner roles for metrics and cost line items."""
    FM = "fm"
    FINANCE = "finance"
    OPS = "ops"
    FOOD_SAFETY = "food_safety"
    ESG = "esg"
    VENDOR = "vendor"
    EXECUTIVE = "executive"


class RACIType(str, Enum):
    ACCOUNTABLE = "accountable"
    RESPONSIBLE = "responsible"
    CONSULTED = "consulted"
    INFORMED = "informed"


class OrgLevel(str, Enum):
    GLOBAL = "global"
    REGION = "region"
    BANNER = "banner"
    STORE = "store"


# Quadrant → default RACI assignment
QUADRANT_DEFAULT_OWNERS: Dict[str, Dict[str, str]] = {
    Quadrant.Q1_FM_OPEX.value: {
        RACIType.ACCOUNTABLE.value: OwnerRole.FM.value,
        RACIType.RESPONSIBLE.value: OwnerRole.VENDOR.value,
        RACIType.CONSULTED.value: OwnerRole.FINANCE.value,
        RACIType.INFORMED.value: OwnerRole.OPS.value,
    },
    Quadrant.Q2_FINANCE_CAPEX.value: {
        RACIType.ACCOUNTABLE.value: OwnerRole.FINANCE.value,
        RACIType.RESPONSIBLE.value: OwnerRole.FM.value,
        RACIType.CONSULTED.value: OwnerRole.OPS.value,
        RACIType.INFORMED.value: OwnerRole.EXECUTIVE.value,
    },
    Quadrant.Q3_COMPLIANCE_RISK.value: {
        RACIType.ACCOUNTABLE.value: OwnerRole.FOOD_SAFETY.value,
        RACIType.RESPONSIBLE.value: OwnerRole.FM.value,
        RACIType.CONSULTED.value: OwnerRole.OPS.value,
        RACIType.INFORMED.value: OwnerRole.EXECUTIVE.value,
    },
    Quadrant.Q4_CROSS_SILO.value: {
        RACIType.ACCOUNTABLE.value: OwnerRole.EXECUTIVE.value,
        RACIType.RESPONSIBLE.value: OwnerRole.FM.value,
        RACIType.CONSULTED.value: OwnerRole.ESG.value,
        RACIType.INFORMED.value: OwnerRole.FINANCE.value,
    },
}


@dataclass
class OwnerWeight:
    """Weighting for a single owner in a multi-owner assignment (Q4)."""
    owner_role: str = OwnerRole.FM.value
    weight: float = 1.0     # fraction of benefit/cost attributed

    def to_dict(self) -> Dict[str, Any]:
        return {"owner_role": self.owner_role, "weight": self.weight}


@dataclass
class OwnershipAssignment:
    """
    RACI ownership assignment for a single metric at a specific org level.

    Supports multi-owner weighting for Q4 cross-silo metrics.
    """
    assignment_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metric_id: str = ""
    org_level: str = OrgLevel.GLOBAL.value
    org_entity: str = ""          # e.g. region name, banner name, store ID

    # RACI roles
    accountable: str = ""
    responsible: str = ""
    consulted: List[str] = field(default_factory=list)
    informed: List[str] = field(default_factory=list)

    # Multi-owner weighting (for Q4 cross-silo)
    owner_weights: List[OwnerWeight] = field(default_factory=list)

    # Effective date range
    effective_from: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    effective_to: Optional[str] = None

    # Audit
    created_by: str = "system"
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def is_active(self) -> bool:
        now = datetime.utcnow().isoformat()
        if self.effective_to and now > self.effective_to:
            return False
        return now >= self.effective_from

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assignment_id": self.assignment_id,
            "metric_id": self.metric_id,
            "org_level": self.org_level,
            "org_entity": self.org_entity,
            "accountable": self.accountable,
            "responsible": self.responsible,
            "consulted": self.consulted,
            "informed": self.informed,
            "owner_weights": [w.to_dict() for w in self.owner_weights],
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "is_active": self.is_active,
            "created_by": self.created_by,
            "created_ts": self.created_ts,
        }


class OwnershipEngine:
    """
    Manages metric → owner assignments with hierarchy-based resolution.

    Resolution order: Store > Banner > Region > Global > Quadrant default.
    """

    ORG_LEVEL_PRECEDENCE = [
        OrgLevel.STORE.value,
        OrgLevel.BANNER.value,
        OrgLevel.REGION.value,
        OrgLevel.GLOBAL.value,
    ]

    def __init__(self):
        self._assignments: Dict[str, List[OwnershipAssignment]] = {}
        self._audit_log: List[Dict[str, Any]] = []

    # ── Assignment CRUD ─────────────────────────────────────────────

    def assign(self, assignment: OwnershipAssignment) -> OwnershipAssignment:
        """Add or replace an ownership assignment for a metric."""
        if assignment.metric_id not in self._assignments:
            self._assignments[assignment.metric_id] = []

        # Deactivate existing assignment at same level/entity
        for existing in self._assignments[assignment.metric_id]:
            if (existing.org_level == assignment.org_level
                    and existing.org_entity == assignment.org_entity
                    and existing.is_active):
                existing.effective_to = datetime.utcnow().isoformat()
                self._log_change("deactivated", existing)

        self._assignments[assignment.metric_id].append(assignment)
        self._log_change("assigned", assignment)
        return assignment

    def set_default_from_quadrant(self, metric_id: str, quadrant: str) -> OwnershipAssignment:
        """Create a global-level default assignment from quadrant defaults."""
        defaults = QUADRANT_DEFAULT_OWNERS.get(quadrant, QUADRANT_DEFAULT_OWNERS[Quadrant.Q1_FM_OPEX.value])
        assignment = OwnershipAssignment(
            metric_id=metric_id,
            org_level=OrgLevel.GLOBAL.value,
            accountable=defaults[RACIType.ACCOUNTABLE.value],
            responsible=defaults[RACIType.RESPONSIBLE.value],
            consulted=[defaults[RACIType.CONSULTED.value]],
            informed=[defaults[RACIType.INFORMED.value]],
            created_by="system_default",
        )
        # For Q4, add multi-owner weights
        if quadrant == Quadrant.Q4_CROSS_SILO.value:
            assignment.owner_weights = [
                OwnerWeight(OwnerRole.FM.value, 0.25),
                OwnerWeight(OwnerRole.OPS.value, 0.20),
                OwnerWeight(OwnerRole.ESG.value, 0.20),
                OwnerWeight(OwnerRole.FOOD_SAFETY.value, 0.15),
                OwnerWeight(OwnerRole.FINANCE.value, 0.20),
            ]
        return self.assign(assignment)

    def override(
        self,
        metric_id: str,
        org_level: str,
        org_entity: str,
        accountable: Optional[str] = None,
        responsible: Optional[str] = None,
        consulted: Optional[List[str]] = None,
        informed: Optional[List[str]] = None,
        owner_weights: Optional[List[OwnerWeight]] = None,
        created_by: str = "user",
    ) -> OwnershipAssignment:
        """Override ownership at a specific org level (region/banner/store)."""
        # Resolve current to get base values
        current = self.resolve(metric_id, org_level, org_entity)
        assignment = OwnershipAssignment(
            metric_id=metric_id,
            org_level=org_level,
            org_entity=org_entity,
            accountable=accountable or current.get("accountable", ""),
            responsible=responsible or current.get("responsible", ""),
            consulted=consulted if consulted is not None else current.get("consulted", []),
            informed=informed if informed is not None else current.get("informed", []),
            owner_weights=owner_weights or [],
            created_by=created_by,
        )
        return self.assign(assignment)

    # ── Resolution ──────────────────────────────────────────────────

    def resolve(
        self,
        metric_id: str,
        org_level: str = OrgLevel.GLOBAL.value,
        org_entity: str = "",
    ) -> Dict[str, Any]:
        """
        Resolve effective ownership for a metric at a given scope.

        Walks up the hierarchy: Store → Banner → Region → Global → Quadrant default.
        """
        assignments = self._assignments.get(metric_id, [])
        active = [a for a in assignments if a.is_active]

        # Build hierarchy chain to walk
        hierarchy_chain = self._build_hierarchy_chain(org_level, org_entity)

        for level, entity in hierarchy_chain:
            match = self._find_match(active, level, entity)
            if match:
                return match.to_dict()

        # Fallback: check for any global assignment
        global_match = self._find_match(active, OrgLevel.GLOBAL.value, "")
        if global_match:
            return global_match.to_dict()

        # No assignment found — return empty
        return {
            "metric_id": metric_id,
            "accountable": "",
            "responsible": "",
            "consulted": [],
            "informed": [],
            "owner_weights": [],
            "org_level": "unassigned",
        }

    def resolve_all(self) -> Dict[str, Dict[str, Any]]:
        """Resolve effective global ownership for all assigned metrics."""
        result = {}
        for metric_id in self._assignments:
            result[metric_id] = self.resolve(metric_id)
        return result

    # ── Owner-centric views ─────────────────────────────────────────

    def get_metrics_for_owner(self, owner_role: str) -> List[Dict[str, Any]]:
        """Get all metrics where the given role is accountable or responsible."""
        result = []
        for metric_id in self._assignments:
            resolved = self.resolve(metric_id)
            if (resolved.get("accountable") == owner_role
                    or resolved.get("responsible") == owner_role):
                result.append(resolved)
        return result

    def get_cross_silo_dependencies(self, metric_id: str) -> List[Dict[str, Any]]:
        """
        For a given metric, find metrics owned by other roles that
        drive its outcomes (Q4 dependency map).
        """
        resolved = self.resolve(metric_id)
        owner = resolved.get("accountable", "")
        dependencies = []

        for mid, assignments in self._assignments.items():
            if mid == metric_id:
                continue
            other = self.resolve(mid)
            if other.get("accountable") != owner and other.get("accountable"):
                dependencies.append({
                    "dependent_metric_id": metric_id,
                    "dependency_metric_id": mid,
                    "dependency_owner": other.get("accountable"),
                    "relationship": "drives_outcome",
                })
        return dependencies

    def has_override(self, metric_id: str) -> bool:
        """Check if a metric has a non-system-default ownership assignment."""
        assignments = self._assignments.get(metric_id, [])
        active = [a for a in assignments if a.is_active]
        for a in active:
            if a.created_by != "system_default":
                return True
        return False

    # ── Audit ───────────────────────────────────────────────────────

    def get_audit_log(self, metric_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if metric_id:
            return [e for e in self._audit_log if e.get("metric_id") == metric_id]
        return list(self._audit_log)

    # ── Helpers ─────────────────────────────────────────────────────

    def _find_match(
        self, assignments: List[OwnershipAssignment], level: str, entity: str
    ) -> Optional[OwnershipAssignment]:
        for a in sorted(assignments, key=lambda x: x.created_ts, reverse=True):
            if a.org_level == level and a.org_entity == entity:
                return a
        return None

    def _build_hierarchy_chain(
        self, org_level: str, org_entity: str
    ) -> List[Tuple[str, str]]:
        """Build the resolution chain from specific to global."""
        chain = []
        if org_level == OrgLevel.STORE.value:
            chain.append((OrgLevel.STORE.value, org_entity))
        if org_level in (OrgLevel.STORE.value, OrgLevel.BANNER.value):
            chain.append((OrgLevel.BANNER.value, org_entity))
        if org_level in (OrgLevel.STORE.value, OrgLevel.BANNER.value, OrgLevel.REGION.value):
            chain.append((OrgLevel.REGION.value, org_entity))
        chain.append((OrgLevel.GLOBAL.value, ""))
        return chain

    def _log_change(self, action: str, assignment: OwnershipAssignment):
        self._audit_log.append({
            "action": action,
            "metric_id": assignment.metric_id,
            "org_level": assignment.org_level,
            "org_entity": assignment.org_entity,
            "accountable": assignment.accountable,
            "responsible": assignment.responsible,
            "created_by": assignment.created_by,
            "timestamp": datetime.utcnow().isoformat(),
        })
        logger.info(
            f"Ownership {action}: metric={assignment.metric_id} "
            f"accountable={assignment.accountable} at {assignment.org_level}/{assignment.org_entity}"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assignments": {
                mid: [a.to_dict() for a in assignments]
                for mid, assignments in self._assignments.items()
            },
            "audit_log_count": len(self._audit_log),
        }
