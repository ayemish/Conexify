"""
Closed-Loop Execution Engine — CMMS writeback, control actions, recommendation tracking.

Implements:
- CMMS/ITSM connector interface (create/update work orders, attach evidence, close-out)
- Control action pipeline with safety policy constraints and approval gates
- Control Action Log for full audit trail
- Recommendation acceptance tracking (who accepted, what changed, outcome)

Turns insights into operational change with full traceability.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Work order model
# =============================================================================

class WorkOrderStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    VERIFIED = "verified"
    CANCELLED = "cancelled"


class WorkOrderPriority(str, Enum):
    # Keep in sync with predictive_maintenance.services.workorder.models.WorkOrderPriority
    EMERGENCY = "emergency"
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    PLANNED = "planned"


@dataclass
class WorkOrderRequest:
    """A work order to be written back to CMMS/ITSM."""
    wo_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    priority: str = WorkOrderPriority.MEDIUM.value
    status: str = WorkOrderStatus.DRAFT.value

    # Identifiers
    company_id: str = ""
    location_id: Optional[str] = None
    asset_id: Optional[str] = None
    case_id: Optional[str] = None
    kpi_name: Optional[str] = None

    # Work details
    work_type: str = ""  # preventive, corrective, inspection, project
    trade: str = ""  # HVAC, refrigeration, electrical, plumbing
    estimated_hours: float = 0.0
    estimated_cost_usd: float = 0.0

    # Evidence bundle
    evidence_artifact_ids: List[str] = field(default_factory=list)
    diagnostic_summary: str = ""
    recommended_parts: List[str] = field(default_factory=list)

    # Categorization (auto-categorize from KPI/case)
    category: str = ""
    subcategory: str = ""
    failure_code: Optional[str] = None

    # Close-out
    close_out_code: Optional[str] = None
    close_out_notes: str = ""
    actual_hours: Optional[float] = None
    actual_cost_usd: Optional[float] = None
    completed_ts: Optional[str] = None

    # External CMMS reference
    external_id: Optional[str] = None
    external_system: Optional[str] = None

    # Metadata
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_by: str = ""
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "wo_id": self.wo_id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "company_id": self.company_id,
            "location_id": self.location_id,
            "asset_id": self.asset_id,
            "case_id": self.case_id,
            "kpi_name": self.kpi_name,
            "work_type": self.work_type,
            "trade": self.trade,
            "estimated_hours": self.estimated_hours,
            "estimated_cost_usd": self.estimated_cost_usd,
            "evidence_artifact_ids": self.evidence_artifact_ids,
            "diagnostic_summary": self.diagnostic_summary,
            "recommended_parts": self.recommended_parts,
            "category": self.category,
            "subcategory": self.subcategory,
            "failure_code": self.failure_code,
            "close_out_code": self.close_out_code,
            "close_out_notes": self.close_out_notes,
            "actual_hours": self.actual_hours,
            "actual_cost_usd": self.actual_cost_usd,
            "completed_ts": self.completed_ts,
            "external_id": self.external_id,
            "external_system": self.external_system,
            "created_ts": self.created_ts,
            "created_by": self.created_by,
            "correlation_id": self.correlation_id,
        }


# =============================================================================
# Control action model
# =============================================================================

class ActionType(str, Enum):
    SETPOINT_CHANGE = "setpoint_change"
    SCHEDULE_CHANGE = "schedule_change"
    MODE_CHANGE = "mode_change"
    EQUIPMENT_ENABLE = "equipment_enable"
    EQUIPMENT_DISABLE = "equipment_disable"
    ALARM_SUPPRESS = "alarm_suppress"
    WORK_ORDER = "work_order"
    NOTIFICATION = "notification"
    CUSTOM = "custom"


class ActionStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class ControlAction:
    """A control action to be executed in the field."""
    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    action_type: str = ActionType.SETPOINT_CHANGE.value
    status: str = ActionStatus.PROPOSED.value
    description: str = ""

    # Target
    asset_id: str = ""
    point_id: Optional[str] = None
    parameter: str = ""
    current_value: Any = None
    proposed_value: Any = None

    # Safety constraints
    safety_class: str = "normal"  # normal, elevated, critical
    requires_approval: bool = True
    max_deviation: Optional[float] = None
    rollback_value: Any = None
    rollback_timeout_minutes: int = 60

    # Rationale
    rationale: str = ""
    kpi_impact_estimate: Optional[float] = None
    confidence: float = 0.0

    # Approval chain
    proposed_by: str = ""
    approved_by: Optional[str] = None
    approved_ts: Optional[str] = None
    rejection_reason: Optional[str] = None

    # Execution
    executed_ts: Optional[str] = None
    execution_result: Optional[str] = None
    rolled_back_ts: Optional[str] = None

    # Metadata
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "status": self.status,
            "description": self.description,
            "asset_id": self.asset_id,
            "point_id": self.point_id,
            "parameter": self.parameter,
            "current_value": self.current_value,
            "proposed_value": self.proposed_value,
            "safety_class": self.safety_class,
            "requires_approval": self.requires_approval,
            "max_deviation": self.max_deviation,
            "rollback_value": self.rollback_value,
            "rollback_timeout_minutes": self.rollback_timeout_minutes,
            "rationale": self.rationale,
            "kpi_impact_estimate": self.kpi_impact_estimate,
            "confidence": self.confidence,
            "proposed_by": self.proposed_by,
            "approved_by": self.approved_by,
            "approved_ts": self.approved_ts,
            "rejection_reason": self.rejection_reason,
            "executed_ts": self.executed_ts,
            "execution_result": self.execution_result,
            "rolled_back_ts": self.rolled_back_ts,
            "created_ts": self.created_ts,
            "correlation_id": self.correlation_id,
        }


# =============================================================================
# Control Action Log
# =============================================================================

class ControlActionLog:
    """Immutable audit log of all control actions."""

    def __init__(self):
        self._log: List[Dict[str, Any]] = []

    def record(self, action: ControlAction, event: str, details: str = ""):
        entry = {
            "log_id": str(uuid.uuid4()),
            "action_id": action.action_id,
            "event": event,
            "status": action.status,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details,
            "actor": action.approved_by or action.proposed_by or "",
            "snapshot": action.to_dict(),
        }
        self._log.append(entry)
        logger.info(f"Action log: {action.action_id} -> {event}")

    def get_history(self, action_id: str) -> List[Dict[str, Any]]:
        return [e for e in self._log if e["action_id"] == action_id]

    def get_all(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self._log[-limit:]

    def stats(self) -> Dict[str, Any]:
        events = {}
        for e in self._log:
            events[e["event"]] = events.get(e["event"], 0) + 1
        return {"total_entries": len(self._log), "by_event": events}


# =============================================================================
# Recommendation tracker
# =============================================================================

class AcceptanceStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    PARTIALLY_ACCEPTED = "partially_accepted"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    EXPIRED = "expired"


@dataclass
class RecommendationRecord:
    """Tracks a recommendation through acceptance and outcome."""
    rec_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    kpi_name: Optional[str] = None
    company_id: str = ""
    location_id: Optional[str] = None

    # The recommendation
    recommended_action: str = ""
    estimated_savings_usd: float = 0.0
    estimated_cost_usd: float = 0.0
    payback_months: Optional[float] = None
    confidence: float = 0.0

    # Acceptance
    acceptance_status: str = AcceptanceStatus.PENDING.value
    accepted_by: Optional[str] = None
    accepted_ts: Optional[str] = None
    rejection_reason: Optional[str] = None
    modifications: List[str] = field(default_factory=list)

    # Outcome tracking
    implemented: bool = False
    implementation_date: Optional[str] = None
    actual_savings_usd: Optional[float] = None
    actual_cost_usd: Optional[float] = None
    outcome_notes: str = ""
    outcome_assessed_ts: Optional[str] = None

    # Linked artifacts
    work_order_ids: List[str] = field(default_factory=list)
    action_ids: List[str] = field(default_factory=list)
    correlation_id: Optional[str] = None

    # Metadata
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rec_id": self.rec_id,
            "title": self.title,
            "description": self.description,
            "kpi_name": self.kpi_name,
            "company_id": self.company_id,
            "location_id": self.location_id,
            "recommended_action": self.recommended_action,
            "estimated_savings_usd": self.estimated_savings_usd,
            "estimated_cost_usd": self.estimated_cost_usd,
            "payback_months": self.payback_months,
            "confidence": self.confidence,
            "acceptance_status": self.acceptance_status,
            "accepted_by": self.accepted_by,
            "accepted_ts": self.accepted_ts,
            "rejection_reason": self.rejection_reason,
            "modifications": self.modifications,
            "implemented": self.implemented,
            "implementation_date": self.implementation_date,
            "actual_savings_usd": self.actual_savings_usd,
            "actual_cost_usd": self.actual_cost_usd,
            "outcome_notes": self.outcome_notes,
            "outcome_assessed_ts": self.outcome_assessed_ts,
            "work_order_ids": self.work_order_ids,
            "action_ids": self.action_ids,
            "correlation_id": self.correlation_id,
            "created_ts": self.created_ts,
        }


class RecommendationTracker:
    """Tracks recommendations through acceptance → implementation → outcome."""

    def __init__(self):
        self._records: Dict[str, RecommendationRecord] = {}

    def create(self, rec: RecommendationRecord) -> str:
        self._records[rec.rec_id] = rec
        logger.info(f"Recommendation created: {rec.title}")
        return rec.rec_id

    def accept(self, rec_id: str, accepted_by: str, modifications: Optional[List[str]] = None):
        rec = self._records.get(rec_id)
        if not rec:
            return
        rec.acceptance_status = AcceptanceStatus.ACCEPTED.value
        if modifications:
            rec.acceptance_status = AcceptanceStatus.PARTIALLY_ACCEPTED.value
            rec.modifications = modifications
        rec.accepted_by = accepted_by
        rec.accepted_ts = datetime.utcnow().isoformat()
        logger.info(f"Recommendation accepted: {rec_id} by {accepted_by}")

    def reject(self, rec_id: str, reason: str):
        rec = self._records.get(rec_id)
        if not rec:
            return
        rec.acceptance_status = AcceptanceStatus.REJECTED.value
        rec.rejection_reason = reason
        logger.info(f"Recommendation rejected: {rec_id}")

    def record_implementation(self, rec_id: str, date: str, work_order_ids: Optional[List[str]] = None):
        rec = self._records.get(rec_id)
        if not rec:
            return
        rec.implemented = True
        rec.implementation_date = date
        if work_order_ids:
            rec.work_order_ids.extend(work_order_ids)

    def record_outcome(
        self, rec_id: str, actual_savings_usd: float,
        actual_cost_usd: float, notes: str = ""
    ):
        rec = self._records.get(rec_id)
        if not rec:
            return
        rec.actual_savings_usd = actual_savings_usd
        rec.actual_cost_usd = actual_cost_usd
        rec.outcome_notes = notes
        rec.outcome_assessed_ts = datetime.utcnow().isoformat()

    def get(self, rec_id: str) -> Optional[RecommendationRecord]:
        return self._records.get(rec_id)

    def get_by_company(self, company_id: str) -> List[RecommendationRecord]:
        return [r for r in self._records.values() if r.company_id == company_id]

    def acceptance_rate(self) -> Dict[str, Any]:
        total = len(self._records)
        if total == 0:
            return {"total": 0}
        accepted = sum(1 for r in self._records.values()
                       if r.acceptance_status in (AcceptanceStatus.ACCEPTED.value, AcceptanceStatus.PARTIALLY_ACCEPTED.value))
        implemented = sum(1 for r in self._records.values() if r.implemented)
        assessed = [r for r in self._records.values() if r.actual_savings_usd is not None]

        total_estimated = sum(r.estimated_savings_usd for r in self._records.values())
        total_actual = sum(r.actual_savings_usd for r in assessed if r.actual_savings_usd)

        return {
            "total": total,
            "accepted": accepted,
            "acceptance_rate": accepted / total,
            "implemented": implemented,
            "implementation_rate": implemented / total,
            "assessed": len(assessed),
            "total_estimated_savings": total_estimated,
            "total_actual_savings": total_actual,
            "realization_rate": total_actual / total_estimated if total_estimated > 0 else None,
        }


# =============================================================================
# CMMS Connector interface
# =============================================================================

class CMMSConnector:
    """
    Abstract CMMS/ITSM connector interface.

    Concrete implementations connect to specific CMMS systems
    (e.g., Maximo, ServiceNow, eMaint, Fiix).
    """

    def __init__(self, system_name: str = "generic", base_url: str = "", api_key: str = ""):
        self.system_name = system_name
        self.base_url = base_url
        self.api_key = api_key
        self._submitted: List[WorkOrderRequest] = []

    def submit_work_order(self, wo: WorkOrderRequest) -> Dict[str, Any]:
        """Submit a work order to the external CMMS."""
        wo.status = WorkOrderStatus.SUBMITTED.value
        wo.external_system = self.system_name
        self._submitted.append(wo)

        # In production, this would call the CMMS API
        logger.info(f"Submitted WO to {self.system_name}: {wo.title}")
        return {
            "status": "submitted",
            "wo_id": wo.wo_id,
            "external_system": self.system_name,
            "external_id": wo.external_id,
        }

    def update_work_order(self, wo_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing work order in the CMMS."""
        logger.info(f"Updated WO {wo_id} in {self.system_name}: {list(updates.keys())}")
        return {"status": "updated", "wo_id": wo_id}

    def attach_evidence(self, wo_id: str, artifact_ids: List[str]) -> Dict[str, Any]:
        """Attach evidence bundles to a work order."""
        logger.info(f"Attached {len(artifact_ids)} artifacts to WO {wo_id}")
        return {"status": "attached", "wo_id": wo_id, "artifact_count": len(artifact_ids)}

    def close_work_order(
        self, wo_id: str, close_code: str, notes: str = "",
        actual_hours: Optional[float] = None, actual_cost: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Close out a work order with completion details."""
        logger.info(f"Closed WO {wo_id} with code {close_code}")
        return {
            "status": "closed",
            "wo_id": wo_id,
            "close_code": close_code,
            "actual_hours": actual_hours,
            "actual_cost": actual_cost,
        }

    def get_submitted(self) -> List[WorkOrderRequest]:
        return list(self._submitted)


# =============================================================================
# Execution Engine — orchestrates the closed loop
# =============================================================================

class ExecutionEngine:
    """
    Orchestrates the full closed-loop execution pipeline:
    1. Recommendation generation (from KPI crews)
    2. Human review / approval gate
    3. Work order creation in CMMS
    4. Control action execution with safety checks
    5. Outcome tracking and M&V reconciliation linkage
    """

    def __init__(
        self,
        cmms: Optional[CMMSConnector] = None,
    ):
        self.cmms = cmms or CMMSConnector()
        self.action_log = ControlActionLog()
        self.recommendation_tracker = RecommendationTracker()
        self._actions: Dict[str, ControlAction] = {}
        self._safety_policies: List[Callable[[ControlAction], bool]] = []

    def add_safety_policy(self, policy_fn: Callable[[ControlAction], bool]):
        """Add a safety policy. Returns True if action is safe to proceed."""
        self._safety_policies.append(policy_fn)

    def propose_action(self, action: ControlAction) -> Dict[str, Any]:
        """Propose a control action (goes through safety checks)."""
        # Safety check
        for policy in self._safety_policies:
            if not policy(action):
                action.status = ActionStatus.REJECTED.value
                action.rejection_reason = "Blocked by safety policy"
                self._actions[action.action_id] = action
                self.action_log.record(action, "safety_blocked")
                return {"status": "blocked", "reason": "Safety policy violation"}

        action.status = ActionStatus.PROPOSED.value
        self._actions[action.action_id] = action
        self.action_log.record(action, "proposed")

        if not action.requires_approval:
            return self.execute_action(action.action_id)

        return {"status": "proposed", "action_id": action.action_id, "requires_approval": True}

    def approve_action(self, action_id: str, approved_by: str) -> Dict[str, Any]:
        action = self._actions.get(action_id)
        if not action:
            return {"status": "not_found"}

        action.status = ActionStatus.APPROVED.value
        action.approved_by = approved_by
        action.approved_ts = datetime.utcnow().isoformat()
        self.action_log.record(action, "approved", f"by {approved_by}")
        return {"status": "approved", "action_id": action_id}

    def execute_action(self, action_id: str) -> Dict[str, Any]:
        """Execute an approved control action."""
        action = self._actions.get(action_id)
        if not action:
            return {"status": "not_found"}

        if action.requires_approval and action.status != ActionStatus.APPROVED.value:
            return {"status": "not_approved"}

        action.status = ActionStatus.EXECUTING.value
        action.executed_ts = datetime.utcnow().isoformat()
        self.action_log.record(action, "executing")

        # In production, this would interface with BMS/controls
        action.status = ActionStatus.COMPLETED.value
        action.execution_result = "success"
        self.action_log.record(action, "completed")

        return {"status": "completed", "action_id": action_id}

    def rollback_action(self, action_id: str, reason: str = "") -> Dict[str, Any]:
        action = self._actions.get(action_id)
        if not action:
            return {"status": "not_found"}

        action.status = ActionStatus.ROLLED_BACK.value
        action.rolled_back_ts = datetime.utcnow().isoformat()
        self.action_log.record(action, "rolled_back", reason)

        return {"status": "rolled_back", "action_id": action_id, "rollback_value": action.rollback_value}

    def create_work_order_from_recommendation(
        self, rec_id: str
    ) -> Optional[WorkOrderRequest]:
        """Create a CMMS work order from an accepted recommendation."""
        rec = self.recommendation_tracker.get(rec_id)
        if not rec or rec.acceptance_status not in (
            AcceptanceStatus.ACCEPTED.value, AcceptanceStatus.PARTIALLY_ACCEPTED.value
        ):
            return None

        wo = WorkOrderRequest(
            title=rec.title,
            description=rec.recommended_action,
            company_id=rec.company_id,
            location_id=rec.location_id,
            kpi_name=rec.kpi_name,
            estimated_cost_usd=rec.estimated_cost_usd,
            correlation_id=rec.correlation_id,
            created_by="execution_engine",
        )

        result = self.cmms.submit_work_order(wo)
        rec.work_order_ids.append(wo.wo_id)

        return wo

    def stats(self) -> Dict[str, Any]:
        statuses = {}
        for a in self._actions.values():
            statuses[a.status] = statuses.get(a.status, 0) + 1
        return {
            "total_actions": len(self._actions),
            "by_status": statuses,
            "action_log_entries": self.action_log.stats()["total_entries"],
            "recommendations": self.recommendation_tracker.acceptance_rate(),
        }
