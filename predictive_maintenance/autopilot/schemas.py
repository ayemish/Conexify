"""
Autopilot Domain Schemas

Core data models for the Operations Autopilot system implementing:
- Incident detection and ingestion
- Playbook-driven remediation
- AutopilotRun execution with checkpointing
- Human-in-the-loop approvals
- Verification and evidence packs
- Policy constraints and governance
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import uuid


# =============================================================================
# Enumerations
# =============================================================================

class RiskTier(str, Enum):
    """Risk tier determines approval requirements"""
    LOW = "LOW"        # Auto-approve within allowlist
    MEDIUM = "MEDIUM"  # Require human approval for control writes
    HIGH = "HIGH"      # Require human approval + additional constraints


class IncidentStatus(str, Enum):
    """Incident lifecycle status"""
    OPEN = "open"
    MATCHED = "matched"       # Playbook matched
    RUN_STARTED = "run_started"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    CLOSED = "closed"


class RunStatus(str, Enum):
    """AutopilotRun lifecycle status"""
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    PAUSED = "paused"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class StepStatus(str, Enum):
    """Individual step execution status"""
    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ApprovalStatus(str, Enum):
    """Approval task status"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"
    EXPIRED = "expired"
    AUTO_APPROVED = "auto_approved"


class ApprovalDecision(str, Enum):
    """Human approval decision"""
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"


class ActionType(str, Enum):
    """Types of actions in playbook steps"""
    READ = "READ"
    WRITE_POINT = "WRITE_POINT"
    CREATE_TICKET = "CREATE_TICKET"
    UPDATE_TICKET = "UPDATE_TICKET"
    NOTIFY = "NOTIFY"
    WAIT = "WAIT"
    COMPUTE = "COMPUTE"
    RUN_TEST = "RUN_TEST"
    ESCALATE = "ESCALATE"


class VerificationStatus(str, Enum):
    """Verification outcome"""
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"
    TIMEOUT = "timeout"


class AssetClass(str, Enum):
    """Asset classification for playbook matching"""
    HVAC = "HVAC"
    REFRIGERATION = "REFRIGERATION"
    LIGHTING = "LIGHTING"
    ELECTRICAL = "ELECTRICAL"
    PLUMBING = "PLUMBING"
    OTHER = "OTHER"


class TicketPriority(str, Enum):
    """CMMS ticket priority levels"""
    P1 = "P1"  # Critical
    P2 = "P2"  # High
    P3 = "P3"  # Medium
    P4 = "P4"  # Low


# =============================================================================
# Incident
# =============================================================================

@dataclass
class Incident:
    """
    A detected condition requiring action.
    
    Incidents are ingested from:
    - Rules engine (thresholds, durations, slopes)
    - Anomaly detector
    - External /events feed
    """
    incident_id: str = field(default_factory=lambda: f"INC-{uuid.uuid4().hex[:12].upper()}")
    
    # Identity
    tenant_id: str = ""
    site_id: str = ""
    asset_id: str = ""
    
    # Classification
    fault_type: str = ""
    severity: str = "medium"  # info, low, medium, high, critical
    source: str = ""  # rules_engine, anomaly_detector, external
    
    # Timing
    start_ts: datetime = field(default_factory=datetime.utcnow)
    end_ts: Optional[datetime] = None
    detected_at: datetime = field(default_factory=datetime.utcnow)
    
    # Evidence
    trigger_evidence: Dict[str, Any] = field(default_factory=dict)
    point_values: Dict[str, float] = field(default_factory=dict)
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    
    # Status
    status: IncidentStatus = IncidentStatus.OPEN
    
    # Matching
    matched_playbook_id: Optional[str] = None
    match_reason: str = ""
    
    # Lifecycle
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None
    
    def dedup_key(self) -> str:
        """Key for deduplication: (asset_id, fault_type, active_window)"""
        return f"{self.asset_id}:{self.fault_type}:{self.start_ts.date().isoformat()}"


# =============================================================================
# Playbook Reference (full Playbook in playbook module)
# =============================================================================

@dataclass
class PlaybookRef:
    """Lightweight reference to a playbook for run context"""
    playbook_id: str
    version: str
    name: str
    asset_class: str
    fault_type: str
    risk_tier: RiskTier


# =============================================================================
# AutopilotRun
# =============================================================================

@dataclass
class AutopilotRun:
    """
    An execution instance of a playbook against an incident.
    
    Maintains durable workflow state with checkpointing for:
    - Pause/resume
    - Human approval interrupts
    - Replay from checkpoints for debugging/audit
    """
    run_id: str = field(default_factory=lambda: f"RUN-{uuid.uuid4().hex[:12].upper()}")
    
    # References
    incident_id: str = ""
    playbook_id: str = ""
    playbook_version: str = ""
    tenant_id: str = ""
    site_id: str = ""
    asset_id: str = ""
    
    # Workflow state
    thread_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    current_checkpoint_id: Optional[str] = None
    checkpoint_history: List[str] = field(default_factory=list)
    
    # Status
    status: RunStatus = RunStatus.PLANNING
    risk_tier: RiskTier = RiskTier.MEDIUM
    
    # Execution tracking
    current_step_index: int = 0
    steps: List["RunStep"] = field(default_factory=list)
    actions: List["RunAction"] = field(default_factory=list)
    
    # Approvals
    pending_approval_id: Optional[str] = None
    approvals: List[str] = field(default_factory=list)  # Approval IDs
    
    # Verification
    verification_results: List["VerificationResult"] = field(default_factory=list)
    
    # Evidence
    evidence_pack_id: Optional[str] = None
    
    # Outcome
    outcome: Optional[str] = None  # RESOLVED, PARTIAL, FAILED
    outcome_reason: str = ""
    
    # Explainability
    plan_rationale: str = ""
    action_rationales: List[str] = field(default_factory=list)
    
    # Lifecycle
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "incident_id": self.incident_id,
            "playbook_id": self.playbook_id,
            "playbook_version": self.playbook_version,
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "asset_id": self.asset_id,
            "status": self.status.value,
            "risk_tier": self.risk_tier.value,
            "current_step_index": self.current_step_index,
            "outcome": self.outcome,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


# =============================================================================
# RunStep
# =============================================================================

@dataclass
class RunStep:
    """Individual step within an AutopilotRun"""
    step_id: str = field(default_factory=lambda: f"STEP-{uuid.uuid4().hex[:8].upper()}")
    run_id: str = ""
    
    # From playbook
    playbook_step_id: str = ""
    step_index: int = 0
    action_type: ActionType = ActionType.READ
    
    # Parameters (resolved from playbook + context)
    params: Dict[str, Any] = field(default_factory=dict)
    
    # Approval
    requires_approval: bool = False
    approval_id: Optional[str] = None
    
    # Execution
    status: StepStatus = StepStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Result
    result: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    
    # Error handling
    on_error: str = "ESCALATE"  # RETRY, SKIP, ESCALATE, ABORT
    retry_count: int = 0
    max_retries: int = 3


# =============================================================================
# RunAction
# =============================================================================

@dataclass
class RunAction:
    """
    Immutable record of an action taken during a run.
    All actions are logged for audit trail.
    """
    action_id: str = field(default_factory=lambda: f"ACT-{uuid.uuid4().hex[:12].upper()}")
    run_id: str = ""
    step_id: str = ""
    
    # Action details
    action_type: ActionType = ActionType.READ
    target: str = ""  # point_id, ticket_id, notification_target
    
    # For control writes
    point_id: Optional[str] = None
    value_before: Optional[float] = None
    value_after: Optional[float] = None
    ttl_seconds: Optional[int] = None
    
    # Correlation
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    # Policy
    policy_approved: bool = False
    policy_id: Optional[str] = None
    
    # Execution
    executed_at: datetime = field(default_factory=datetime.utcnow)
    executed_by: str = "autopilot"  # autopilot, human:{user_id}
    
    # Result
    success: bool = False
    response: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


# =============================================================================
# Approval
# =============================================================================

@dataclass
class Approval:
    """
    Human approval record for an action or run.
    """
    approval_id: str = field(default_factory=lambda: f"APR-{uuid.uuid4().hex[:12].upper()}")
    
    # Context
    run_id: str = ""
    step_id: Optional[str] = None
    tenant_id: str = ""
    
    # What needs approval
    approval_type: str = "step"  # run, step, action
    risk_tier: RiskTier = RiskTier.MEDIUM
    
    # Proposed action details
    proposed_actions: List[Dict[str, Any]] = field(default_factory=list)
    rationale: str = ""
    evidence_snapshot: Dict[str, Any] = field(default_factory=dict)
    
    # Status
    status: ApprovalStatus = ApprovalStatus.PENDING
    
    # Decision
    decision: Optional[ApprovalDecision] = None
    decided_by: Optional[str] = None
    decided_at: Optional[datetime] = None
    decision_notes: str = ""
    
    # Edits (if decision == EDIT)
    edited_params: Dict[str, Any] = field(default_factory=dict)
    
    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    
    # Escalation on rejection
    escalation_triggered: bool = False


@dataclass
class ApprovalTask:
    """Operator-facing approval task view"""
    approval_id: str
    run_id: str
    asset_id: str
    site_id: str
    
    # Display
    title: str
    description: str
    risk_tier: RiskTier
    urgency: str  # low, medium, high, critical
    
    # Proposed actions
    proposed_actions: List[Dict[str, Any]]
    
    # Evidence
    evidence_summary: List[str]
    telemetry_snapshot: Dict[str, Any]
    
    # Options
    can_edit: bool = True
    can_approve: bool = True
    can_reject: bool = True
    
    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None


# =============================================================================
# Verification
# =============================================================================

@dataclass
class VerificationResult:
    """
    Result from verification engine after action execution.
    """
    verification_id: str = field(default_factory=lambda: f"VER-{uuid.uuid4().hex[:8].upper()}")
    run_id: str = ""
    
    # Check definition
    check_expression: str = ""
    window_seconds: int = 900  # 15 minutes default
    must_hold: bool = True
    
    # Execution
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    # Result
    status: VerificationStatus = VerificationStatus.PENDING
    passed: bool = False
    
    # Evidence
    before_values: Dict[str, float] = field(default_factory=dict)
    after_values: Dict[str, float] = field(default_factory=dict)
    delta: Dict[str, float] = field(default_factory=dict)
    
    # Details
    message: str = ""
    stability_achieved_at: Optional[datetime] = None


# =============================================================================
# Evidence Pack
# =============================================================================

@dataclass
class EvidencePack:
    """
    Immutable audit-grade artifact documenting a run.
    
    Includes:
    - Triggering telemetry window (before)
    - Action chain (who/what/when)
    - Verification results (after)
    - Outcome status
    """
    pack_id: str = field(default_factory=lambda: f"EVD-{uuid.uuid4().hex[:12].upper()}")
    run_id: str = ""
    incident_id: str = ""
    
    # Identity
    tenant_id: str = ""
    site_id: str = ""
    asset_id: str = ""
    
    # Playbook
    playbook_id: str = ""
    playbook_version: str = ""
    
    # Timing
    incident_start: datetime = field(default_factory=datetime.utcnow)
    run_start: datetime = field(default_factory=datetime.utcnow)
    run_end: datetime = field(default_factory=datetime.utcnow)
    
    # Before state
    before_telemetry_window: Dict[str, Any] = field(default_factory=dict)
    before_window_start: Optional[datetime] = None
    before_window_end: Optional[datetime] = None
    
    # Actions
    actions: List[Dict[str, Any]] = field(default_factory=list)
    approvals: List[Dict[str, Any]] = field(default_factory=list)
    
    # After state
    after_telemetry_window: Dict[str, Any] = field(default_factory=dict)
    after_window_start: Optional[datetime] = None
    after_window_end: Optional[datetime] = None
    
    # Verification
    verification_results: List[Dict[str, Any]] = field(default_factory=list)
    
    # Outcome
    outcome: str = ""  # RESOLVED, PARTIAL, FAILED
    outcome_reason: str = ""
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: str = "autopilot"
    
    # Immutability
    content_hash: Optional[str] = None
    signed_at: Optional[datetime] = None
    
    # Links
    cmms_ticket_ids: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "run_id": self.run_id,
            "incident_id": self.incident_id,
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "asset_id": self.asset_id,
            "playbook_id": self.playbook_id,
            "playbook_version": self.playbook_version,
            "incident_start": self.incident_start.isoformat(),
            "run_start": self.run_start.isoformat(),
            "run_end": self.run_end.isoformat(),
            "before_telemetry_window": self.before_telemetry_window,
            "actions": self.actions,
            "approvals": self.approvals,
            "after_telemetry_window": self.after_telemetry_window,
            "verification_results": self.verification_results,
            "outcome": self.outcome,
            "outcome_reason": self.outcome_reason,
            "created_at": self.created_at.isoformat(),
            "content_hash": self.content_hash,
            "cmms_ticket_ids": self.cmms_ticket_ids,
        }


# =============================================================================
# Policy
# =============================================================================

@dataclass
class PolicyConstraint:
    """Individual policy constraint"""
    constraint_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    constraint_type: str = ""  # allowlist, max_delta, time_window, rate_limit
    
    # For allowlists
    allowed_points: List[str] = field(default_factory=list)
    allowed_actions: List[ActionType] = field(default_factory=list)
    
    # For max_delta
    point_id: Optional[str] = None
    max_delta: Optional[float] = None
    
    # For time_window
    allowed_hours_start: Optional[int] = None  # 0-23
    allowed_hours_end: Optional[int] = None
    allowed_days: List[int] = field(default_factory=list)  # 0=Mon, 6=Sun
    
    # For rate_limit
    max_commands_per_hour: Optional[int] = None
    
    # For override duration
    max_override_duration_seconds: Optional[int] = None


@dataclass
class Policy:
    """
    Site/tenant policy constraints for autopilot actions.
    
    Policy rules:
    - Per-tenant allowlists of control actions (point write permissions)
    - Max delta per setpoint change
    - Max duration of override
    - Time-of-day constraints (e.g., store open)
    - Rate limits for commands per asset per hour
    """
    policy_id: str = field(default_factory=lambda: f"POL-{uuid.uuid4().hex[:8].upper()}")
    
    # Scope
    tenant_id: str = ""
    site_id: Optional[str] = None  # None = tenant-wide
    asset_id: Optional[str] = None  # None = site-wide
    
    # Name
    name: str = ""
    description: str = ""
    
    # Risk tier requirements
    auto_approve_risk_tiers: List[RiskTier] = field(default_factory=lambda: [RiskTier.LOW])
    require_approval_risk_tiers: List[RiskTier] = field(default_factory=lambda: [RiskTier.MEDIUM, RiskTier.HIGH])
    require_two_person_approval: bool = False
    
    # Constraints
    constraints: List[PolicyConstraint] = field(default_factory=list)
    
    # Global limits
    max_setpoint_delta: float = 5.0  # degrees
    max_override_duration_seconds: int = 3600  # 1 hour
    max_commands_per_asset_per_hour: int = 10
    
    # Store hours (for time-of-day constraints)
    store_hours_start: int = 6  # 6 AM
    store_hours_end: int = 22   # 10 PM
    
    # Lifecycle
    is_active: bool = True
    effective_from: datetime = field(default_factory=datetime.utcnow)
    retired_at: Optional[datetime] = None
    
    # Versioning
    version: str = "1.0.0"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def check_action(
        self, 
        action_type: ActionType, 
        point_id: Optional[str] = None,
        value_delta: Optional[float] = None,
        current_hour: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        Check if an action is allowed by this policy.
        
        Returns:
            (allowed, reason)
        """
        # Check allowlist constraints
        for constraint in self.constraints:
            if constraint.constraint_type == "allowlist":
                if constraint.allowed_actions and action_type not in constraint.allowed_actions:
                    return False, f"Action type {action_type.value} not in allowlist"
                if point_id and constraint.allowed_points and point_id not in constraint.allowed_points:
                    return False, f"Point {point_id} not in allowlist"
        
        # Check max_delta
        if value_delta is not None and abs(value_delta) > self.max_setpoint_delta:
            return False, f"Delta {value_delta} exceeds max {self.max_setpoint_delta}"
        
        # Check time-of-day
        if current_hour is not None:
            if not (self.store_hours_start <= current_hour < self.store_hours_end):
                # Outside store hours - may need stricter controls
                pass  # Allow for now, can add constraints
        
        return True, "Policy check passed"
    
    def clamp_value(self, current_value: float, proposed_value: float) -> float:
        """Clamp proposed value to stay within policy limits"""
        delta = proposed_value - current_value
        if abs(delta) > self.max_setpoint_delta:
            clamped_delta = self.max_setpoint_delta if delta > 0 else -self.max_setpoint_delta
            return current_value + clamped_delta
        return proposed_value


# =============================================================================
# Checkpoint (for durable execution)
# =============================================================================

@dataclass
class Checkpoint:
    """
    Workflow checkpoint for durable execution.
    
    Enables:
    - Pause/resume
    - Human approval interrupts
    - Replay from any point for debugging/audit
    """
    checkpoint_id: str = field(default_factory=lambda: f"CHK-{uuid.uuid4().hex[:12].upper()}")
    run_id: str = ""
    thread_id: str = ""
    
    # State
    step_index: int = 0
    run_status: RunStatus = RunStatus.PLANNING
    
    # Serialized state
    state_json: str = "{}"
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: str = "autopilot"
    reason: str = ""  # approval_pending, step_completed, error, manual_pause
    
    # For replay
    parent_checkpoint_id: Optional[str] = None
    is_replay: bool = False
