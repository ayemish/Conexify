"""
Governance Engine — RACI enforcement, approval gates, and audit trails
for the ownership decision support pipeline.

Bridges the ownership module's metric-centric RACI (OwnershipEngine) with
the enterprise operating_model's activity-centric RACI (RACIMatrix).

Key capabilities:
1. RACI enforcement: only the accountable owner can approve ownership changes
2. Approval gates: high-impact decisions require multi-stakeholder sign-off
3. Change audit trail: every ownership/parameter change is logged immutably
4. Decision provenance: traces from recommendation → approval → execution
5. Exception management: escalation when constraints conflict or data gaps exist
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from loweconex_platform.ownership.metric_catalog import MetricCatalog, Quadrant
from loweconex_platform.ownership.ownership_model import (
    OwnershipEngine, QUADRANT_DEFAULT_OWNERS, OwnerRole, RACIType,
)

logger = logging.getLogger(__name__)


# Try to import enterprise operating_model for RACI bridge
try:
    from loweconex_platform.operating_model import (
        RACIMatrix, RACIEntry, RACIRole,
        ExceptionManager, ExceptionRecord,
    )
    OPERATING_MODEL_AVAILABLE = True
except ImportError:
    OPERATING_MODEL_AVAILABLE = False
    logger.info("operating_model not available — governance uses ownership RACI only")


# ═══════════════════════════════════════════════════════════════════
# Enums and Data Classes
# ═══════════════════════════════════════════════════════════════════

class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    AUTO_APPROVED = "auto_approved"


class ChangeType(str, Enum):
    OWNERSHIP_OVERRIDE = "ownership_override"
    PARAMETER_OVERRIDE = "parameter_override"
    CONSTRAINT_OVERRIDE = "constraint_override"
    METRIC_ADDITION = "metric_addition"
    METRIC_REMOVAL = "metric_removal"
    RULE_MODIFICATION = "rule_modification"
    BUDGET_CHANGE = "budget_change"
    COMPLIANCE_WAIVER = "compliance_waiver"


class ImpactLevel(str, Enum):
    LOW = "low"           # Auto-approved, logged
    MEDIUM = "medium"     # Requires accountable owner approval
    HIGH = "high"         # Requires multi-stakeholder sign-off
    CRITICAL = "critical" # Requires executive + compliance approval


@dataclass
class ChangeRequest:
    """A request to change ownership, parameters, or constraints."""
    change_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    change_type: str = ChangeType.PARAMETER_OVERRIDE.value
    requestor: str = ""
    metric_id: str = ""
    quadrant: str = ""
    description: str = ""
    old_value: Any = None
    new_value: Any = None
    justification: str = ""
    impact_level: str = ImpactLevel.LOW.value
    status: str = ApprovalStatus.PENDING.value
    approvers: List[str] = field(default_factory=list)
    approvals_received: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    resolved_at: str = ""
    resolution_note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "change_id": self.change_id,
            "change_type": self.change_type,
            "requestor": self.requestor,
            "metric_id": self.metric_id,
            "quadrant": self.quadrant,
            "description": self.description,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "justification": self.justification,
            "impact_level": self.impact_level,
            "status": self.status,
            "approvers": self.approvers,
            "approvals_received": self.approvals_received,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "resolution_note": self.resolution_note,
        }


@dataclass
class AuditEntry:
    """An immutable audit log entry."""
    audit_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    actor: str = ""
    action: str = ""          # e.g., "approve_change", "reject_change", "override_parameter"
    entity_type: str = ""     # e.g., "metric", "parameter", "ownership", "constraint"
    entity_id: str = ""
    change_id: str = ""       # Links to ChangeRequest
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "timestamp": self.timestamp,
            "actor": self.actor,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "change_id": self.change_id,
            "details": self.details,
        }


# ═══════════════════════════════════════════════════════════════════
# Impact Assessment
# ═══════════════════════════════════════════════════════════════════

# Rules for determining impact level of a change
IMPACT_RULES: Dict[str, str] = {
    ChangeType.COMPLIANCE_WAIVER.value: ImpactLevel.CRITICAL.value,
    ChangeType.METRIC_REMOVAL.value: ImpactLevel.HIGH.value,
    ChangeType.BUDGET_CHANGE.value: ImpactLevel.HIGH.value,
    ChangeType.OWNERSHIP_OVERRIDE.value: ImpactLevel.MEDIUM.value,
    ChangeType.CONSTRAINT_OVERRIDE.value: ImpactLevel.MEDIUM.value,
    ChangeType.RULE_MODIFICATION.value: ImpactLevel.MEDIUM.value,
    ChangeType.METRIC_ADDITION.value: ImpactLevel.LOW.value,
    ChangeType.PARAMETER_OVERRIDE.value: ImpactLevel.LOW.value,
}

# Approvers required by impact level
APPROVAL_REQUIREMENTS: Dict[str, List[str]] = {
    ImpactLevel.LOW.value: [],  # Auto-approved
    ImpactLevel.MEDIUM.value: ["accountable_owner"],
    ImpactLevel.HIGH.value: ["accountable_owner", "finance"],
    ImpactLevel.CRITICAL.value: ["accountable_owner", "food_safety", "executive"],
}


# ═══════════════════════════════════════════════════════════════════
# Governance Engine
# ═══════════════════════════════════════════════════════════════════

class GovernanceEngine:
    """
    Orchestrates RACI enforcement, approval workflows, and audit trails.

    Integrates with:
    - OwnershipEngine: metric-centric RACI for determining approvers
    - RACIMatrix (operating_model): activity-centric RACI for enterprise alignment
    - ExceptionManager (operating_model): escalation of unresolved conflicts
    """

    def __init__(
        self,
        catalog: MetricCatalog,
        ownership: OwnershipEngine,
        raci_matrix: Optional[Any] = None,
        exception_manager: Optional[Any] = None,
    ):
        self.catalog = catalog
        self.ownership = ownership
        self._change_log: List[ChangeRequest] = []
        self._audit_log: List[AuditEntry] = []

        # Bridge to enterprise operating_model
        if raci_matrix is not None:
            self._raci_matrix = raci_matrix
        elif OPERATING_MODEL_AVAILABLE:
            self._raci_matrix = RACIMatrix()
            self._seed_raci_from_ownership()
        else:
            self._raci_matrix = None

        if exception_manager is not None:
            self._exception_mgr = exception_manager
        elif OPERATING_MODEL_AVAILABLE:
            self._exception_mgr = ExceptionManager()
        else:
            self._exception_mgr = None

    def _seed_raci_from_ownership(self):
        """Seed the enterprise RACIMatrix from ownership quadrant defaults."""
        if not self._raci_matrix or not OPERATING_MODEL_AVAILABLE:
            return

        for metric in self.catalog.list_all():
            mid = metric.metric_id
            quad = metric.quadrant
            quad_owners = QUADRANT_DEFAULT_OWNERS.get(quad, {})

            for activity in RACIMatrix.STANDARD_ACTIVITIES:
                for raci_type, owner_role in quad_owners.items():
                    raci_role_map = {
                        RACIType.ACCOUNTABLE.value: RACIRole.ACCOUNTABLE.value,
                        RACIType.RESPONSIBLE.value: RACIRole.RESPONSIBLE.value,
                        RACIType.CONSULTED.value: RACIRole.CONSULTED.value,
                        RACIType.INFORMED.value: RACIRole.INFORMED.value,
                    }
                    raci_role = raci_role_map.get(raci_type, RACIRole.INFORMED.value)
                    self._raci_matrix.assign(RACIEntry(
                        kpi_name=mid,
                        activity=activity,
                        person_or_role=owner_role,
                        raci_role=raci_role,
                    ))

    # ── Impact Assessment ─────────────────────────────────────────

    def assess_impact(self, change_type: str, metric_id: str = "", **kwargs) -> str:
        """
        Determine the impact level of a proposed change.

        Args:
            change_type: ChangeType enum value
            metric_id: Optional metric being changed

        Returns:
            ImpactLevel enum value
        """
        # Start with default from rules
        base_level = IMPACT_RULES.get(change_type, ImpactLevel.MEDIUM.value)

        # Escalate if metric is in a compliance quadrant
        if metric_id:
            metric_def = self.catalog.get(metric_id)
            if metric_def and metric_def.quadrant == "Q3":
                # Compliance metrics always at least MEDIUM
                if base_level == ImpactLevel.LOW.value:
                    base_level = ImpactLevel.MEDIUM.value
                # Constraint overrides on compliance are CRITICAL
                if change_type == ChangeType.CONSTRAINT_OVERRIDE.value:
                    base_level = ImpactLevel.CRITICAL.value

        # Budget changes above threshold are CRITICAL
        budget_amount = kwargs.get("budget_amount", 0)
        if change_type == ChangeType.BUDGET_CHANGE.value and budget_amount > 500000:
            base_level = ImpactLevel.CRITICAL.value

        return base_level

    # ── Change Request Management ─────────────────────────────────

    def submit_change(
        self,
        change_type: str,
        requestor: str,
        description: str,
        metric_id: str = "",
        old_value: Any = None,
        new_value: Any = None,
        justification: str = "",
        **kwargs,
    ) -> ChangeRequest:
        """
        Submit a change request. Auto-approves LOW impact changes.
        """
        # Determine quadrant
        quadrant = ""
        if metric_id:
            metric_def = self.catalog.get(metric_id)
            if metric_def:
                quadrant = metric_def.quadrant

        # Assess impact
        impact = self.assess_impact(change_type, metric_id, **kwargs)

        # Determine required approvers
        required = self._resolve_approvers(impact, metric_id, quadrant)

        request = ChangeRequest(
            change_type=change_type,
            requestor=requestor,
            metric_id=metric_id,
            quadrant=quadrant,
            description=description,
            old_value=old_value,
            new_value=new_value,
            justification=justification,
            impact_level=impact,
            approvers=required,
        )

        # Auto-approve LOW impact
        if impact == ImpactLevel.LOW.value:
            request.status = ApprovalStatus.AUTO_APPROVED.value
            request.resolved_at = datetime.utcnow().isoformat()
            request.resolution_note = "Auto-approved (low impact)"

        self._change_log.append(request)

        # Audit
        self._audit(
            actor=requestor,
            action="submit_change",
            entity_type=change_type,
            entity_id=metric_id,
            change_id=request.change_id,
            details={"impact_level": impact, "approvers_required": required},
        )

        logger.info(
            f"Change request {request.change_id}: {change_type} "
            f"(impact={impact}, status={request.status})"
        )
        return request

    def approve_change(
        self,
        change_id: str,
        approver: str,
        note: str = "",
    ) -> ChangeRequest:
        """
        Approve a pending change request.

        Only the required approvers can approve. Once all approvers
        have signed off, the change is marked as approved.
        """
        request = self._get_change(change_id)
        if not request:
            raise ValueError(f"Change request {change_id} not found")

        if request.status not in (ApprovalStatus.PENDING.value, ApprovalStatus.ESCALATED.value):
            raise ValueError(f"Change {change_id} is already {request.status}")

        # Verify approver is authorized
        if not self._is_authorized_approver(approver, request):
            raise PermissionError(
                f"'{approver}' is not an authorized approver for {change_id}. "
                f"Required: {request.approvers}"
            )

        # Record approval
        request.approvals_received.append({
            "approver": approver,
            "timestamp": datetime.utcnow().isoformat(),
            "note": note,
        })

        # Check if all approvals received
        approved_by = {a["approver"] for a in request.approvals_received}
        required_set = set(request.approvers)
        if required_set.issubset(approved_by):
            request.status = ApprovalStatus.APPROVED.value
            request.resolved_at = datetime.utcnow().isoformat()
            request.resolution_note = f"Approved by: {', '.join(approved_by)}"

        self._audit(
            actor=approver,
            action="approve_change",
            entity_type=request.change_type,
            entity_id=request.metric_id,
            change_id=change_id,
            details={"note": note, "fully_approved": request.status == ApprovalStatus.APPROVED.value},
        )

        return request

    def reject_change(
        self,
        change_id: str,
        rejector: str,
        reason: str,
    ) -> ChangeRequest:
        """Reject a pending change request."""
        request = self._get_change(change_id)
        if not request:
            raise ValueError(f"Change request {change_id} not found")

        request.status = ApprovalStatus.REJECTED.value
        request.resolved_at = datetime.utcnow().isoformat()
        request.resolution_note = f"Rejected by {rejector}: {reason}"

        self._audit(
            actor=rejector,
            action="reject_change",
            entity_type=request.change_type,
            entity_id=request.metric_id,
            change_id=change_id,
            details={"reason": reason},
        )

        return request

    def escalate_change(
        self,
        change_id: str,
        escalator: str,
        reason: str,
    ) -> ChangeRequest:
        """Escalate a change to the next approval level."""
        request = self._get_change(change_id)
        if not request:
            raise ValueError(f"Change request {change_id} not found")

        request.status = ApprovalStatus.ESCALATED.value

        # Increase impact level and add more approvers
        current_level = request.impact_level
        escalated_level = self._escalate_impact(current_level)
        request.impact_level = escalated_level
        new_approvers = self._resolve_approvers(
            escalated_level, request.metric_id, request.quadrant
        )
        request.approvers = list(set(request.approvers + new_approvers))

        self._audit(
            actor=escalator,
            action="escalate_change",
            entity_type=request.change_type,
            entity_id=request.metric_id,
            change_id=change_id,
            details={
                "reason": reason,
                "old_impact": current_level,
                "new_impact": escalated_level,
                "new_approvers": new_approvers,
            },
        )

        # Log exception if exception manager available
        if self._exception_mgr and OPERATING_MODEL_AVAILABLE:
            self._exception_mgr.create(ExceptionRecord(
                kpi_name=request.metric_id or "governance",
                exception_type="escalation",
                title=f"Governance escalation: {change_id}",
                description=f"Change {change_id} escalated: {reason}",
            ))

        return request

    # ── Query Methods ─────────────────────────────────────────────

    def get_pending_approvals(self, approver: str = "") -> List[ChangeRequest]:
        """Get all pending change requests, optionally filtered by approver."""
        pending = [
            r for r in self._change_log
            if r.status in (ApprovalStatus.PENDING.value, ApprovalStatus.ESCALATED.value)
        ]
        if approver:
            pending = [r for r in pending if approver in r.approvers]
        return pending

    def get_change_history(
        self,
        metric_id: str = "",
        change_type: str = "",
        limit: int = 50,
    ) -> List[ChangeRequest]:
        """Get change request history with optional filters."""
        results = self._change_log
        if metric_id:
            results = [r for r in results if r.metric_id == metric_id]
        if change_type:
            results = [r for r in results if r.change_type == change_type]
        return results[-limit:]

    def get_audit_log(
        self,
        entity_id: str = "",
        actor: str = "",
        limit: int = 100,
    ) -> List[AuditEntry]:
        """Get audit log with optional filters."""
        results = self._audit_log
        if entity_id:
            results = [e for e in results if e.entity_id == entity_id]
        if actor:
            results = [e for e in results if e.actor == actor]
        return results[-limit:]

    def get_governance_summary(self) -> Dict[str, Any]:
        """Get a summary of governance state."""
        total = len(self._change_log)
        approved = len([r for r in self._change_log if r.status in (
            ApprovalStatus.APPROVED.value, ApprovalStatus.AUTO_APPROVED.value
        )])
        rejected = len([r for r in self._change_log if r.status == ApprovalStatus.REJECTED.value])
        pending = len([r for r in self._change_log if r.status in (
            ApprovalStatus.PENDING.value, ApprovalStatus.ESCALATED.value
        )])

        impact_breakdown = {}
        for r in self._change_log:
            impact_breakdown[r.impact_level] = impact_breakdown.get(r.impact_level, 0) + 1

        type_breakdown = {}
        for r in self._change_log:
            type_breakdown[r.change_type] = type_breakdown.get(r.change_type, 0) + 1

        raci_valid = self._validate_raci_completeness()

        return {
            "total_changes": total,
            "approved": approved,
            "rejected": rejected,
            "pending": pending,
            "approval_rate": approved / total if total > 0 else 1.0,
            "impact_breakdown": impact_breakdown,
            "type_breakdown": type_breakdown,
            "audit_entries": len(self._audit_log),
            "raci_bridge_active": self._raci_matrix is not None,
            "exception_mgr_active": self._exception_mgr is not None,
            "raci_validation": raci_valid,
        }

    # ── RACI Validation ───────────────────────────────────────────

    def validate_ownership_action(
        self,
        actor: str,
        action: str,
        metric_id: str,
    ) -> Dict[str, Any]:
        """
        Check if an actor is authorized for an action on a metric.

        Returns:
            dict with: authorized (bool), required_role, actor_role, reason
        """
        assignment = self.ownership.resolve(metric_id)
        if not assignment:
            return {
                "authorized": False,
                "required_role": "unknown",
                "actor_role": actor,
                "reason": f"No ownership assignment for metric '{metric_id}'.",
            }

        # Map action to required RACI role
        action_to_raci = {
            "approve": RACIType.ACCOUNTABLE.value,
            "modify": RACIType.RESPONSIBLE.value,
            "review": RACIType.CONSULTED.value,
            "view": RACIType.INFORMED.value,
        }

        required_raci = action_to_raci.get(action, RACIType.ACCOUNTABLE.value)
        authorized_roles: Set[str] = set()

        # Collect all roles at or above the required level
        raci_hierarchy = [
            RACIType.INFORMED.value,
            RACIType.CONSULTED.value,
            RACIType.RESPONSIBLE.value,
            RACIType.ACCOUNTABLE.value,
        ]

        required_idx = raci_hierarchy.index(required_raci) if required_raci in raci_hierarchy else 3
        for i in range(required_idx, len(raci_hierarchy)):
            role_val = assignment.get(raci_hierarchy[i], "")
            # consulted/informed may be lists
            if isinstance(role_val, list):
                authorized_roles.update(r for r in role_val if r)
            elif role_val:
                authorized_roles.add(role_val)

        is_authorized = actor in authorized_roles

        return {
            "authorized": is_authorized,
            "required_role": required_raci,
            "actor_role": actor,
            "authorized_roles": sorted(authorized_roles),
            "reason": (
                f"Actor '{actor}' is authorized for '{action}' on '{metric_id}'."
                if is_authorized else
                f"Actor '{actor}' is not authorized for '{action}' on '{metric_id}'. "
                f"Required: {required_raci} ({sorted(authorized_roles)})."
            ),
        }

    # ── Internal Helpers ──────────────────────────────────────────

    def _resolve_approvers(
        self, impact_level: str, metric_id: str, quadrant: str
    ) -> List[str]:
        """Resolve the list of approver roles for a given impact level."""
        templates = APPROVAL_REQUIREMENTS.get(impact_level, [])
        approvers = []
        for template in templates:
            if template == "accountable_owner":
                if metric_id:
                    assignment = self.ownership.resolve(metric_id)
                    if assignment:
                        owner = assignment.get(RACIType.ACCOUNTABLE.value, "")
                        if owner:
                            approvers.append(owner)
                            continue
                # Fallback to quadrant default
                quad_owners = QUADRANT_DEFAULT_OWNERS.get(quadrant, {})
                owner = quad_owners.get(RACIType.ACCOUNTABLE.value, "executive")
                approvers.append(owner)
            else:
                approvers.append(template)
        return list(set(approvers))

    def _is_authorized_approver(self, approver: str, request: ChangeRequest) -> bool:
        """Check if an actor is in the required approvers list."""
        return approver in request.approvers

    def _get_change(self, change_id: str) -> Optional[ChangeRequest]:
        """Find a change request by ID."""
        for r in self._change_log:
            if r.change_id == change_id:
                return r
        return None

    def _escalate_impact(self, current: str) -> str:
        """Escalate to the next impact level."""
        levels = [
            ImpactLevel.LOW.value,
            ImpactLevel.MEDIUM.value,
            ImpactLevel.HIGH.value,
            ImpactLevel.CRITICAL.value,
        ]
        idx = levels.index(current) if current in levels else 0
        return levels[min(idx + 1, len(levels) - 1)]

    def _audit(self, **kwargs):
        """Add an audit log entry."""
        entry = AuditEntry(**kwargs)
        self._audit_log.append(entry)

    def _validate_raci_completeness(self) -> Dict[str, Any]:
        """Validate that all metrics have RACI assignments."""
        metrics = self.catalog.list_all()
        missing = []
        for m in metrics:
            assignment = self.ownership.resolve(m.metric_id)
            if not assignment:
                missing.append(m.metric_id)
            elif not assignment.get(RACIType.ACCOUNTABLE.value):
                missing.append(m.metric_id)

        return {
            "total_metrics": len(metrics),
            "with_raci": len(metrics) - len(missing),
            "missing_raci": missing,
            "complete": len(missing) == 0,
        }
