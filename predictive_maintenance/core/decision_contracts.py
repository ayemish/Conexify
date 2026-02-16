"""Decision contracts for kernel and agent orchestration layers.

These contracts formalize how the deterministic PdM kernel shares decision
state with the multi-agent control plane while preserving hard safety gates.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from .schemas import AlertType, FaultType, OperatingRegime


class HardGate(str, Enum):
    """Non-bypassable policy gates for actionable decisions."""

    SENSOR_TRUST = "sensor_trust"
    STEADY_STATE_OR_CHANGE = "steady_state_or_change"
    CHANGE_PRESENT = "change_present"
    PERSISTENCE = "persistence"
    DIAGNOSIS_CONFIDENCE = "diagnosis_confidence"
    BUDGET = "budget"


@dataclass(frozen=True)
class GateEvaluation:
    """Evaluation result for one hard gate."""

    gate: HardGate
    passed: bool
    reason: str
    metric: Optional[float] = None
    threshold: Optional[float] = None


@dataclass(frozen=True)
class HypothesisSnapshot:
    """Compact hypothesis view for orchestration and persistence."""

    top_fault: Optional[FaultType]
    top_probability: float
    is_concentrated: bool
    beliefs: Dict[str, float]


@dataclass(frozen=True)
class KernelDecisionArtifact:
    """Deterministic kernel output consumed by advisory agents."""

    artifact_id: str
    asset_id: str
    site_id: Optional[str]
    timestamp: datetime
    regime: OperatingRegime
    is_steady_state: bool
    trust_scores: Dict[str, float]
    untrusted_sensors: List[str]
    change_scores: Dict[str, float]
    change_detected: Dict[str, bool]
    change_duration_hours: Dict[str, float]
    joint_change_detected: bool
    joint_change_score: float
    hypothesis: HypothesisSnapshot
    base_alert_type: AlertType
    base_alert_confidence: float
    base_false_alarm_probability: float
    base_recommended_action: str
    gates: List[GateEvaluation] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)


class AdvisoryAction(str, Enum):
    """Allowed advisory actions from agent layer."""

    KEEP = "keep"
    DOWNGRADE_TO_WATCH = "downgrade_to_watch"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    SUPPRESS_FOR_DATA_QUALITY = "suppress_for_data_quality"
    ENRICH_ACTION_PLAN = "enrich_action_plan"


@dataclass(frozen=True)
class AgentAdvisory:
    """Structured recommendation from an advisory agent."""

    agent_id: str
    agent_role: str
    action: AdvisoryAction
    confidence: float
    rationale: str
    evidence: List[Dict[str, Any]] = field(default_factory=list)


class FinalDisposition(str, Enum):
    """Final operational disposition after guardian merge."""

    AUTO_MONITOR = "auto_monitor"
    AUTO_ACTIONABLE = "auto_actionable"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    HUMAN_APPROVED = "human_approved"
    HUMAN_REJECTED = "human_rejected"


@dataclass(frozen=True)
class GuardianDecision:
    """Merged decision after applying advisory constraints."""

    disposition: FinalDisposition
    final_alert_type: AlertType
    confidence: float
    false_alarm_probability: float
    recommended_action: str
    reasons: List[str]
    advisories_used: List[str]
