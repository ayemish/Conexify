"""
Oil & Gas Four-Plane Architecture - Data Plane

Handles: Ingestion, stream processing, evidence store, forensic bundles.
Based on industrial standards: OPC-UA, WITSML, PRODML.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from enum import Enum
import json
import hashlib
import uuid


# =============================================================================
# Enums for Data Plane
# =============================================================================

class SignalSource(str, Enum):
    """Sources of incoming signals"""
    IOT_SENSOR = "iot_sensor"
    BAS_SCADA = "bas_scada"
    DEVICE_EVENT = "device_event"
    MAINTENANCE_SYSTEM = "maintenance_system"
    WEATHER_API = "weather_api"
    TARIFF_FEED = "tariff_feed"
    OCCUPANCY_SYSTEM = "occupancy_system"
    MANUAL_ENTRY = "manual_entry"


class AlertClassification(str, Enum):
    """Business impact classification"""
    COMFORT = "comfort"
    ENERGY_WASTE = "energy_waste"
    IMPENDING_FAILURE = "impending_failure"
    SAFETY = "safety"
    COMPLIANCE = "compliance"
    SLA_RISK = "sla_risk"


class CaseState(str, Enum):
    """Case lifecycle states (9-state machine)"""
    INTAKE = "intake"
    TRIAGE = "triage"
    DIAGNOSE = "diagnose"
    PLAN = "plan"
    AUTHORIZE = "authorize"
    EXECUTE = "execute"
    VERIFY = "verify"
    CLOSE = "close"
    LEARN = "learn"


class CasePriority(str, Enum):
    """Case priority levels"""
    P1_CRITICAL = "P1"  # Safety, immediate action required
    P2_HIGH = "P2"      # Impending failure, SLA risk
    P3_MEDIUM = "P3"    # Energy waste, comfort degradation
    P4_LOW = "P4"       # Optimization opportunity
    P5_INFO = "P5"      # Informational


class AutonomyLevel(str, Enum):
    """Policy-based autonomy levels per customer/site/system"""
    OBSERVE_ONLY = "observe_only"           # No actions, only monitoring
    RECOMMEND_ONLY = "recommend_only"       # Generate recommendations, no execution
    AUTO_LOW_RISK = "auto_low_risk"         # Auto-execute low-risk reversible actions
    AUTO_MEDIUM_RISK = "auto_medium_risk"   # Auto-execute medium-risk with logging
    FULL_AUTONOMY = "full_autonomy"         # Full auto-execution (rare, specific systems)


class ActionRiskLevel(str, Enum):
    """Risk classification for actions"""
    SAFE = "safe"               # Read-only, no system impact
    LOW = "low"                 # Reversible, minimal impact
    MEDIUM = "medium"           # Reversible with effort, moderate impact
    HIGH = "high"               # Difficult to reverse, significant impact
    CRITICAL = "critical"       # Irreversible, safety implications


# =============================================================================
# Evidence & Forensics
# =============================================================================

@dataclass
class TelemetryPoint:
    """Single telemetry data point"""
    sensor_id: str
    timestamp: datetime
    value: float
    unit: str
    quality: float = 1.0
    source: SignalSource = SignalSource.IOT_SENSOR
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sensor_id": self.sensor_id,
            "timestamp": self.timestamp.isoformat(),
            "value": self.value,
            "unit": self.unit,
            "quality": self.quality,
            "source": self.source.value,
        }


@dataclass
class DeviceEvent:
    """Device state change or event"""
    event_id: str
    device_id: str
    event_type: str
    timestamp: datetime
    severity: str
    description: str
    source: SignalSource = SignalSource.DEVICE_EVENT
    raw_payload: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "device_id": self.device_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity,
            "description": self.description,
        }


@dataclass
class MaintenanceRecord:
    """Historical maintenance record"""
    record_id: str
    equipment_id: str
    maintenance_type: str
    performed_at: datetime
    performed_by: str
    description: str
    parts_replaced: List[str] = field(default_factory=list)
    cost: float = 0.0
    next_scheduled: Optional[datetime] = None


@dataclass
class ContextData:
    """Environmental and operational context"""
    timestamp: datetime
    weather: Dict[str, Any] = field(default_factory=dict)  # temp, humidity, conditions
    occupancy: Dict[str, Any] = field(default_factory=dict)  # building occupancy data
    tariff: Dict[str, Any] = field(default_factory=dict)  # energy pricing
    schedule: Dict[str, Any] = field(default_factory=dict)  # building/equipment schedule


@dataclass
class EvidenceBundle:
    """
    Forensic evidence bundle for a case.
    Contains all data needed to understand and reproduce the incident.
    """
    bundle_id: str
    case_id: str
    created_at: datetime
    
    # Telemetry snapshot (time window around incident)
    telemetry_window: List[TelemetryPoint] = field(default_factory=list)
    
    # Related events
    device_events: List[DeviceEvent] = field(default_factory=list)
    
    # Historical context
    maintenance_history: List[MaintenanceRecord] = field(default_factory=list)
    
    # Environmental context
    context: Optional[ContextData] = None
    
    # Derived features
    features: Dict[str, Any] = field(default_factory=dict)
    
    # Anomaly scores and model outputs
    anomaly_scores: Dict[str, float] = field(default_factory=dict)
    model_predictions: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "case_id": self.case_id,
            "created_at": self.created_at.isoformat(),
            "n_telemetry_points": len(self.telemetry_window),
            "n_events": len(self.device_events),
            "features": self.features,
            "anomaly_scores": self.anomaly_scores,
        }


# =============================================================================
# Case Management
# =============================================================================

@dataclass
class Alert:
    """
    Raw alert from detection systems.
    May be deduplicated, suppressed, or merged into cases.
    """
    alert_id: str
    source_system: str
    device_id: str
    site_id: str
    
    # Classification
    alert_type: str
    severity: str
    message: str  # Required field - must come before optional fields
    
    # Optional details
    classification: Optional[AlertClassification] = None
    current_value: Optional[float] = None
    threshold: Optional[float] = None
    
    # Timing
    triggered_at: datetime = field(default_factory=datetime.utcnow)
    
    # State
    suppressed: bool = False
    deduplicated: bool = False
    merged_into_case: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "device_id": self.device_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "message": self.message,
            "triggered_at": self.triggered_at.isoformat(),
        }


@dataclass
class Hypothesis:
    """Root cause hypothesis with confidence"""
    hypothesis_id: str
    description: str
    confidence: float  # 0-1
    evidence_for: List[str] = field(default_factory=list)
    evidence_against: List[str] = field(default_factory=list)
    validations_required: List[str] = field(default_factory=list)
    invalidated: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "description": self.description,
            "confidence": self.confidence,
            "evidence_for": self.evidence_for,
            "evidence_against": self.evidence_against,
            "invalidated": self.invalidated,
        }


@dataclass
class ActionStep:
    """Single action step in a remediation plan"""
    step_id: str
    sequence: int
    action_type: str
    description: str
    risk_level: ActionRiskLevel
    
    # Tool details
    tool_name: Optional[str] = None
    tool_params: Dict[str, Any] = field(default_factory=dict)
    
    # Execution
    requires_approval: bool = False
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    executed: bool = False
    executed_at: Optional[datetime] = None
    execution_result: Optional[Dict[str, Any]] = None
    
    # Rollback
    rollback_steps: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "sequence": self.sequence,
            "action_type": self.action_type,
            "description": self.description,
            "risk_level": self.risk_level.value,
            "requires_approval": self.requires_approval,
            "executed": self.executed,
        }


@dataclass
class RemediationPlan:
    """Ordered action plan with risk levels and rollback"""
    plan_id: str
    case_id: str
    created_at: datetime
    created_by: str  # agent_id
    
    # Plan structure
    steps: List[ActionStep] = field(default_factory=list)
    
    # Risk assessment
    overall_risk: ActionRiskLevel = ActionRiskLevel.LOW
    estimated_duration_minutes: int = 0
    
    # State
    approved: bool = False
    approval_required: bool = True
    current_step: int = 0
    completed: bool = False
    
    def get_next_step(self) -> Optional[ActionStep]:
        """Get next unexecuted step"""
        for step in self.steps:
            if not step.executed:
                return step
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "case_id": self.case_id,
            "n_steps": len(self.steps),
            "overall_risk": self.overall_risk.value,
            "approved": self.approved,
            "completed": self.completed,
            "steps": [s.to_dict() for s in self.steps],
        }


@dataclass
class CaseTimeline:
    """Timeline entry for case history"""
    entry_id: str
    timestamp: datetime
    event_type: str  # state_change, action, note, escalation
    description: str
    actor: str  # agent_id or user_id
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Case:
    """
    Central case object for incident management.
    Follows 9-state lifecycle: Intake → Triage → Diagnose → Plan → Authorize → Execute → Verify → Close → Learn
    """
    case_id: str
    site_id: str
    created_at: datetime
    
    # State machine
    state: CaseState = CaseState.INTAKE
    state_history: List[Dict[str, Any]] = field(default_factory=list)
    
    # Classification
    priority: CasePriority = CasePriority.P3_MEDIUM
    classification: Optional[AlertClassification] = None
    
    # SLA
    sla_deadline: Optional[datetime] = None
    sla_breached: bool = False
    
    # Alerts that triggered/comprise this case
    source_alerts: List[Alert] = field(default_factory=list)
    
    # Evidence
    evidence_bundle: Optional[EvidenceBundle] = None
    
    # Diagnosis
    hypotheses: List[Hypothesis] = field(default_factory=list)
    root_cause: Optional[Hypothesis] = None
    
    # Remediation
    remediation_plan: Optional[RemediationPlan] = None
    
    # Timeline
    timeline: List[CaseTimeline] = field(default_factory=list)
    
    # Ownership
    assigned_agent: Optional[str] = None
    escalated_to: Optional[str] = None
    human_owner: Optional[str] = None
    
    # Resolution
    resolved: bool = False
    resolution_summary: str = ""
    resolution_time: Optional[datetime] = None
    customer_notified: bool = False
    
    # Learning
    lessons_learned: List[str] = field(default_factory=list)
    runbook_updates: List[str] = field(default_factory=list)
    model_feedback: Dict[str, Any] = field(default_factory=dict)
    
    def transition_to(self, new_state: CaseState, actor: str, reason: str = ""):
        """Transition case to new state"""
        old_state = self.state
        self.state = new_state
        
        transition = {
            "from": old_state.value,
            "to": new_state.value,
            "timestamp": datetime.utcnow().isoformat(),
            "actor": actor,
            "reason": reason,
        }
        self.state_history.append(transition)
        
        self.timeline.append(CaseTimeline(
            entry_id=str(uuid.uuid4())[:8],
            timestamp=datetime.utcnow(),
            event_type="state_change",
            description=f"State: {old_state.value} → {new_state.value}",
            actor=actor,
            details=transition,
        ))
    
    def add_timeline_entry(self, event_type: str, description: str, actor: str, details: Dict[str, Any] = None):
        """Add entry to case timeline"""
        self.timeline.append(CaseTimeline(
            entry_id=str(uuid.uuid4())[:8],
            timestamp=datetime.utcnow(),
            event_type=event_type,
            description=description,
            actor=actor,
            details=details or {},
        ))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "site_id": self.site_id,
            "state": self.state.value,
            "priority": self.priority.value,
            "classification": self.classification.value if self.classification else None,
            "n_alerts": len(self.source_alerts),
            "n_hypotheses": len(self.hypotheses),
            "has_plan": self.remediation_plan is not None,
            "resolved": self.resolved,
            "created_at": self.created_at.isoformat(),
        }


# =============================================================================
# Evidence Store
# =============================================================================

class EvidenceStore:
    """
    Central evidence store for cases.
    Maintains time-series data, events, and forensic bundles.
    """
    
    def __init__(self, retention_hours: int = 168):  # 1 week default
        self.retention_hours = retention_hours
        
        # Time-series storage
        self.telemetry: Dict[str, List[TelemetryPoint]] = {}  # sensor_id -> points
        
        # Event storage
        self.events: List[DeviceEvent] = []
        
        # Case bundles
        self.bundles: Dict[str, EvidenceBundle] = {}  # bundle_id -> bundle
        
        # Maintenance history
        self.maintenance: Dict[str, List[MaintenanceRecord]] = {}  # equipment_id -> records
    
    def ingest_telemetry(self, points: List[TelemetryPoint]):
        """Ingest telemetry points"""
        for point in points:
            if point.sensor_id not in self.telemetry:
                self.telemetry[point.sensor_id] = []
            self.telemetry[point.sensor_id].append(point)
        
        self._prune_old_data()
    
    def ingest_events(self, events: List[DeviceEvent]):
        """Ingest device events"""
        self.events.extend(events)
        self._prune_old_data()
    
    def get_telemetry_window(
        self,
        sensor_ids: List[str],
        start: datetime,
        end: datetime
    ) -> List[TelemetryPoint]:
        """Get telemetry for sensors in time window"""
        result = []
        for sensor_id in sensor_ids:
            if sensor_id in self.telemetry:
                for point in self.telemetry[sensor_id]:
                    if start <= point.timestamp <= end:
                        result.append(point)
        return sorted(result, key=lambda x: x.timestamp)
    
    def get_events_window(
        self,
        device_ids: List[str],
        start: datetime,
        end: datetime
    ) -> List[DeviceEvent]:
        """Get events for devices in time window"""
        return [
            e for e in self.events
            if e.device_id in device_ids and start <= e.timestamp <= end
        ]
    
    def create_evidence_bundle(
        self,
        case_id: str,
        sensor_ids: List[str],
        device_ids: List[str],
        window_hours: int = 24
    ) -> EvidenceBundle:
        """Create forensic evidence bundle for a case"""
        end = datetime.utcnow()
        start = end - timedelta(hours=window_hours)
        
        bundle = EvidenceBundle(
            bundle_id=str(uuid.uuid4())[:12],
            case_id=case_id,
            created_at=datetime.utcnow(),
            telemetry_window=self.get_telemetry_window(sensor_ids, start, end),
            device_events=self.get_events_window(device_ids, start, end),
            maintenance_history=[
                r for d in device_ids
                for r in self.maintenance.get(d, [])
            ],
        )
        
        self.bundles[bundle.bundle_id] = bundle
        return bundle
    
    def _prune_old_data(self):
        """Remove data older than retention period"""
        cutoff = datetime.utcnow() - timedelta(hours=self.retention_hours)
        
        for sensor_id in list(self.telemetry.keys()):
            self.telemetry[sensor_id] = [
                p for p in self.telemetry[sensor_id]
                if p.timestamp > cutoff
            ]
        
        self.events = [e for e in self.events if e.timestamp > cutoff]


# =============================================================================
# Stream Processing
# =============================================================================

@dataclass
class ProcessedSignal:
    """Signal after stream processing"""
    original: TelemetryPoint
    normalized_value: float
    unit_harmonized: str
    
    # Feature extraction
    rate_of_change: float = 0.0
    moving_average: float = 0.0
    std_deviation: float = 0.0
    
    # Rule checks
    threshold_breach: bool = False
    anomaly_score: float = 0.0


class StreamProcessor:
    """
    Real-time stream processing for telemetry.
    Handles: normalization, unit harmonization, feature extraction, rule checks.
    """
    
    def __init__(self):
        self.window_size = 60  # points for moving stats
        self.buffers: Dict[str, List[float]] = {}
        
        # Unit conversion factors (to SI)
        self.unit_conversions = {
            "psi": ("Pa", 6894.76),
            "bar": ("Pa", 100000),
            "F": ("K", lambda x: (x - 32) * 5/9 + 273.15),
            "C": ("K", lambda x: x + 273.15),
            "bpd": ("m3/s", 1.84e-6),
            "mscfd": ("m3/s", 0.000328),
        }
        
        # Threshold rules
        self.thresholds: Dict[str, Dict[str, float]] = {}
    
    def set_threshold(self, sensor_id: str, warning: float, critical: float):
        """Set threshold rules for a sensor"""
        self.thresholds[sensor_id] = {"warning": warning, "critical": critical}
    
    def process(self, point: TelemetryPoint) -> ProcessedSignal:
        """Process a single telemetry point"""
        # Initialize buffer
        if point.sensor_id not in self.buffers:
            self.buffers[point.sensor_id] = []
        
        buffer = self.buffers[point.sensor_id]
        buffer.append(point.value)
        
        # Keep window size
        if len(buffer) > self.window_size:
            buffer.pop(0)
        
        # Unit harmonization
        normalized_value = point.value
        unit_harmonized = point.unit
        if point.unit in self.unit_conversions:
            target_unit, factor = self.unit_conversions[point.unit]
            if callable(factor):
                normalized_value = factor(point.value)
            else:
                normalized_value = point.value * factor
            unit_harmonized = target_unit
        
        # Feature extraction
        import numpy as np
        arr = np.array(buffer)
        
        rate_of_change = 0.0
        if len(buffer) >= 2:
            rate_of_change = buffer[-1] - buffer[-2]
        
        moving_average = float(np.mean(arr))
        std_deviation = float(np.std(arr)) if len(arr) > 1 else 0.0
        
        # Anomaly score (z-score based)
        anomaly_score = 0.0
        if std_deviation > 1e-6:
            anomaly_score = abs(point.value - moving_average) / std_deviation
        
        # Threshold check
        threshold_breach = False
        if point.sensor_id in self.thresholds:
            thresh = self.thresholds[point.sensor_id]
            if point.value > thresh.get("critical", float('inf')):
                threshold_breach = True
        
        return ProcessedSignal(
            original=point,
            normalized_value=normalized_value,
            unit_harmonized=unit_harmonized,
            rate_of_change=rate_of_change,
            moving_average=moving_average,
            std_deviation=std_deviation,
            threshold_breach=threshold_breach,
            anomaly_score=anomaly_score,
        )
    
    def process_batch(self, points: List[TelemetryPoint]) -> List[ProcessedSignal]:
        """Process batch of points"""
        return [self.process(p) for p in points]
