"""
PDM Core Schemas - Core Data Models for Predictive Maintenance

Implements radar-inspired detection theory with:
- False positive budget constraints (Neyman-Pearson)
- Operating regime segmentation
- Three-layer inference (sensor trust, behavior deviation, fault hypothesis)
- Probabilistic fault hypothesis testing
- Equipment fingerprints and hierarchical modeling

This module is part of the SEPARATE Predictive Maintenance project.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import uuid


# =============================================================================
# Operating Regimes
# =============================================================================

class OperatingRegime(str, Enum):
    """Operating regimes for HVAC/R equipment - first-class design element"""
    OFF = "off"
    STARTUP = "startup"
    SHUTDOWN = "shutdown"
    STEADY_COOL = "steady_cool"
    STEADY_HEAT = "steady_heat"
    ECONOMIZER = "economizer"
    DEFROST = "defrost"
    TRANSIENT = "transient"
    CONTROL_EVENT = "control_event"
    RECOVERY = "recovery"
    UNKNOWN = "unknown"


class AlertType(str, Enum):
    """Three-tier alert classification"""
    SENSOR_INTEGRITY = "sensor_integrity"
    WATCH = "watch"
    ACTIONABLE = "actionable"


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FaultType(str, Enum):
    """Known fault types for HVAC/R systems"""
    REFRIGERANT_LEAK = "refrigerant_leak"
    REFRIGERANT_OVERCHARGE = "refrigerant_overcharge"
    TXV_RESTRICTION = "txv_restriction"
    CONDENSER_FOULING = "condenser_fouling"
    EVAPORATOR_FOULING = "evaporator_fouling"
    FAN_DEGRADATION = "fan_degradation"
    COMPRESSOR_DEGRADATION = "compressor_degradation"
    SENSOR_DRIFT = "sensor_drift"
    SENSOR_STUCK = "sensor_stuck"
    CONTROL_INSTABILITY = "control_instability"
    ELECTRICAL_ISSUE = "electrical_issue"
    UNKNOWN_ANOMALY = "unknown_anomaly"


class SensorType(str, Enum):
    """Sensor types for HVAC/R monitoring"""
    SUCTION_PRESSURE = "suction_pressure"
    DISCHARGE_PRESSURE = "discharge_pressure"
    SUCTION_LINE_TEMP = "suction_line_temp"
    LIQUID_LINE_TEMP = "liquid_line_temp"
    COMPRESSOR_CURRENT = "compressor_current"
    COMPRESSOR_POWER = "compressor_power"
    EVAP_FAN_STATUS = "evap_fan_status"
    CONDENSER_FAN_STATUS = "condenser_fan_status"
    VALVE_POSITION = "valve_position"
    RETURN_AIR_TEMP = "return_air_temp"
    SUPPLY_AIR_TEMP = "supply_air_temp"
    MIXED_AIR_TEMP = "mixed_air_temp"
    SUPPLY_FAN_SPEED = "supply_fan_speed"
    DAMPER_POSITION = "damper_position"
    COOLING_VALVE = "cooling_valve"
    HEATING_VALVE = "heating_valve"
    ZONE_TEMP = "zone_temp"
    AMBIENT_TEMP = "ambient_temp"
    AMBIENT_HUMIDITY = "ambient_humidity"


class FeedbackOutcome(str, Enum):
    """Human feedback outcomes for alarm calibration"""
    CONFIRMED_FAULT = "confirmed_fault"
    NO_ISSUE_FOUND = "no_issue_found"
    SENSOR_PROBLEM = "sensor_problem"
    PENDING = "pending"


# =============================================================================
# False Positive Budget (Neyman-Pearson Constraint)
# =============================================================================

@dataclass
class FalsePositiveBudget:
    """
    Explicit false positive budget - defined BEFORE modeling.
    Changes objective to: "Given fixed false alarm rate, maximize early detection."
    """
    budget_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    
    max_actionable_alarms_per_unit_per_month: float = 0.3
    max_no_issue_found_rate: float = 0.05
    
    cost_truck_roll: float = 250.0
    cost_missed_failure: float = 5000.0
    cost_false_alarm: float = 300.0
    
    min_confidence_for_actionable: float = 0.85
    max_false_alarm_probability: float = 0.02
    min_anomaly_persistence_hours: float = 6.0
    min_regime_coverage_cycles: int = 2
    min_sensor_trust_score: float = 0.8
    
    realized_alarms_this_month: int = 0
    realized_no_issue_found: int = 0
    last_calibration: Optional[datetime] = None
    
    def get_remaining_budget(self, units_monitored: int) -> float:
        total_budget = self.max_actionable_alarms_per_unit_per_month * units_monitored
        return max(0, total_budget - self.realized_alarms_this_month)
    
    def should_suppress_alarm(self, false_alarm_prob: float, 
                               confidence: float) -> Tuple[bool, str]:
        if false_alarm_prob > self.max_false_alarm_probability:
            return True, f"FA probability {false_alarm_prob:.1%} exceeds budget {self.max_false_alarm_probability:.1%}"
        if confidence < self.min_confidence_for_actionable:
            return True, f"Confidence {confidence:.1%} below threshold {self.min_confidence_for_actionable:.1%}"
        return False, ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "budget_id": self.budget_id,
            "max_actionable_alarms_per_unit_per_month": self.max_actionable_alarms_per_unit_per_month,
            "max_no_issue_found_rate": self.max_no_issue_found_rate,
            "cost_truck_roll": self.cost_truck_roll,
            "cost_missed_failure": self.cost_missed_failure,
            "cost_false_alarm": self.cost_false_alarm,
            "min_confidence_for_actionable": self.min_confidence_for_actionable,
            "max_false_alarm_probability": self.max_false_alarm_probability,
            "min_anomaly_persistence_hours": self.min_anomaly_persistence_hours,
            "min_regime_coverage_cycles": self.min_regime_coverage_cycles,
            "min_sensor_trust_score": self.min_sensor_trust_score,
            "realized_alarms_this_month": self.realized_alarms_this_month,
            "realized_no_issue_found": self.realized_no_issue_found,
            "last_calibration": self.last_calibration.isoformat() if self.last_calibration else None,
        }


# =============================================================================
# Telemetry Snapshot
# =============================================================================

@dataclass
class TelemetrySnapshot:
    """Complete telemetry snapshot for a single timestamp"""
    timestamp: datetime
    asset_id: str
    
    compressor_on: bool = False
    compressor_current: Optional[float] = None
    compressor_power: Optional[float] = None
    
    evap_fan_on: bool = False
    condenser_fan_on: bool = False
    supply_fan_speed: Optional[float] = None
    
    suction_temp: Optional[float] = None
    discharge_temp: Optional[float] = None
    supply_air_temp: Optional[float] = None
    return_air_temp: Optional[float] = None
    ambient_temp: Optional[float] = None
    
    suction_pressure: Optional[float] = None
    discharge_pressure: Optional[float] = None


# =============================================================================
# Sensor Reading
# =============================================================================

@dataclass
class SensorReading:
    """Individual sensor reading"""
    timestamp: datetime
    sensor_id: str
    sensor_type: SensorType
    value: float
    quality: float = 1.0


# =============================================================================
# Regime State
# =============================================================================

@dataclass
class RegimeState:
    """Current operating regime with confidence"""
    regime: OperatingRegime
    confidence: float
    start_time: datetime
    duration_seconds: float = 0.0
    
    ambient_temp: Optional[float] = None
    load_proxy: Optional[float] = None
    
    previous_regime: Optional[OperatingRegime] = None
    transition_reason: str = ""


# =============================================================================
# Regime Segment
# =============================================================================

@dataclass
class RegimeSegment:
    """Contiguous segment of a single operating regime"""
    asset_id: str
    regime: OperatingRegime
    start_time: datetime
    end_time: Optional[datetime] = None
    confidence: float = 0.0
    n_samples: int = 0
    avg_ambient_temp: Optional[float] = None


# =============================================================================
# Sensor Trust
# =============================================================================

@dataclass
class SensorTrust:
    """Per-sensor trust assessment"""
    sensor_id: str
    sensor_type: SensorType
    asset_id: str
    
    trust_score: float = 1.0
    drift_likelihood: float = 0.0
    stuck_likelihood: float = 0.0
    comms_integrity: float = 1.0
    out_of_range_probability: float = 0.0
    
    last_value: Optional[float] = None
    value_variance_24h: Optional[float] = None
    missing_data_rate: float = 0.0
    consecutive_identical_readings: int = 0
    
    computed_at: datetime = field(default_factory=datetime.utcnow)
    
    def is_trusted(self, threshold: float = 0.8) -> bool:
        return self.trust_score >= threshold


# Backward-compatible alias used across services
SensorTrustScore = SensorTrust


# =============================================================================
# Residual Observation
# =============================================================================

@dataclass
class ResidualObservation:
    """Single residual observation with context"""
    timestamp: datetime
    sensor_id: str
    sensor_type: SensorType
    regime: OperatingRegime
    
    observed: float
    predicted: float
    residual: float
    
    load_proxy: Optional[float] = None
    ambient_temp: Optional[float] = None
    
    z_score: Optional[float] = None
    p_value: Optional[float] = None
    log_likelihood: Optional[float] = None


# =============================================================================
# Residual Distribution
# =============================================================================

@dataclass
class ResidualDistribution:
    """Fitted residual distribution parameters for a regime/sensor"""
    regime: OperatingRegime
    sensor_type: SensorType
    mu: float = 0.0
    sigma: float = 1.0
    nu: float = 4.0
    sigma_base: float = 1.0
    sigma_load_coef: float = 0.0
    phi: float = 0.0  # AR(1) coefficient
    n_samples_fitted: int = 0
    last_updated: Optional[datetime] = None


# =============================================================================
# Change Detection Result
# =============================================================================

@dataclass
class ChangeDetectionResult:
    """Result from sequential change detection"""
    detector_id: str = ""
    asset_id: str = ""
    sensor_type: Optional[SensorType] = None
    
    cusum_pos: float = 0.0
    cusum_neg: float = 0.0
    cusum_threshold: float = 5.0
    
    glr_statistic: float = 0.0
    glr_threshold: float = 10.0
    
    change_detected: bool = False
    change_score: float = 0.0
    estimated_onset_time: Optional[datetime] = None
    stability_score: float = 1.0
    
    anomaly_start_time: Optional[datetime] = None
    anomaly_duration_hours: float = 0.0
    n_anomalous_samples: int = 0
    n_regimes_observed: int = 0
    
    last_updated: datetime = field(default_factory=datetime.utcnow)
    
    def meets_persistence_criteria(self, min_hours: float = 6.0, 
                                    min_regimes: int = 2) -> bool:
        return (self.anomaly_duration_hours >= min_hours and 
                self.n_regimes_observed >= min_regimes)


# Backward-compatible alias used across services
ChangePointDetection = ChangeDetectionResult


# =============================================================================
# Fault Evidence
# =============================================================================

@dataclass
class FaultEvidence:
    """Evidence item supporting a fault hypothesis"""
    fault_type: FaultType
    symptom: str
    sensor_sources: List[str] = field(default_factory=list)
    likelihood_ratio: float = 1.0
    strength: float = 0.0
    confidence: float = 0.0
    first_observed: Optional[datetime] = None
    last_observed: Optional[datetime] = None


# =============================================================================
# Fault Hypothesis
# =============================================================================

@dataclass
class FaultHypothesis:
    """Probabilistic fault hypothesis"""
    hypothesis_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    asset_id: str = ""
    
    priors: Dict[FaultType, float] = field(default_factory=dict)
    posteriors: Dict[FaultType, float] = field(default_factory=dict)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    
    most_likely_fault: Optional[FaultType] = None
    second_likely_fault: Optional[FaultType] = None
    probability_mass_top2: float = 0.0
    
    is_concentrated: bool = False
    recommended_action: str = ""
    
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def get_belief_distribution(self) -> Dict[str, float]:
        return {ft.value: prob for ft, prob in self.posteriors.items()}


# =============================================================================
# Hierarchical Modeling / Fingerprints
# =============================================================================

@dataclass
class HierarchicalModelConfig:
    """Configuration for hierarchical (global + local) models"""
    global_weight: float = 0.7
    local_weight: float = 0.3
    adaptation_learning_rate: float = 0.05
    max_adaptation_drift: float = 0.5
    min_samples_for_adaptation: int = 200
    similar_asset_weight: float = 0.2


@dataclass
class EquipmentFingerprint:
    """Learned equipment fingerprint for a single asset"""
    fingerprint_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    asset_id: str = ""
    sensor_offsets: Dict[str, float] = field(default_factory=dict)
    regime_baselines: Dict[OperatingRegime, Dict[str, Dict[str, float]]] = field(default_factory=dict)
    hours_of_data: float = 0.0
    adaptation_confidence: float = 0.0
    n_regimes_observed: Dict[OperatingRegime, int] = field(default_factory=dict)
    last_updated: Optional[datetime] = None

    def is_sufficiently_learned(self, min_hours: float = 168.0,
                                min_confidence: float = 0.6) -> bool:
        return self.hours_of_data >= min_hours or self.adaptation_confidence >= min_confidence


# =============================================================================
# Maintenance Alert
# =============================================================================

@dataclass
class MaintenanceAlert:
    """Complete alert output with probabilistic information"""
    alert_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    asset_id: str = ""
    
    alert_type: AlertType = AlertType.WATCH
    severity: AlertSeverity = AlertSeverity.MEDIUM
    
    false_alarm_probability: float = 0.5
    confidence: float = 0.5
    
    fault_beliefs: Dict[FaultType, float] = field(default_factory=dict)
    primary_fault: Optional[FaultType] = None
    secondary_fault: Optional[FaultType] = None
    
    evidence_summary: List[str] = field(default_factory=list)
    
    recommended_action: str = ""
    action_urgency: str = "monitor"
    
    energy_penalty_estimate_pct: Optional[float] = None
    downtime_risk_score: Optional[float] = None
    comfort_risk_score: Optional[float] = None
    estimated_cost_if_ignored: Optional[float] = None
    
    regime_at_detection: OperatingRegime = OperatingRegime.UNKNOWN
    ambient_temp_at_detection: Optional[float] = None
    
    created_at: datetime = field(default_factory=datetime.utcnow)
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    
    feedback_outcome: Optional[FeedbackOutcome] = None
    feedback_notes: str = ""

    def to_operator_dict(self) -> Dict[str, Any]:
        """Operator-friendly alert representation"""
        return {
            "alert_id": self.alert_id,
            "asset_id": self.asset_id,
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "confidence": self.confidence,
            "false_alarm_probability": self.false_alarm_probability,
            "primary_fault": self.primary_fault.value if self.primary_fault else None,
            "secondary_fault": self.secondary_fault.value if self.secondary_fault else None,
            "evidence_summary": list(self.evidence_summary),
            "recommended_action": self.recommended_action,
            "action_urgency": self.action_urgency,
            "regime_at_detection": self.regime_at_detection.value,
            "created_at": self.created_at.isoformat(),
        }


# Backward-compatible alias used across services
PDMAlert = MaintenanceAlert


# =============================================================================
# Calibration / Feedback
# =============================================================================

@dataclass
class AlarmFeedback:
    """Human feedback on alert outcomes (for calibration)"""
    alert_id: str
    asset_id: str
    outcome: FeedbackOutcome
    confirmed_fault_type: Optional[FaultType] = None
    feedback_notes: str = ""
    alarm_time: Optional[datetime] = None
    feedback_time: Optional[datetime] = None
    predicted_fault_distribution: Dict[FaultType, float] = field(default_factory=dict)
    predicted_false_alarm_prob: float = 0.0


@dataclass
class CalibrationDataset:
    """Dataset for calibration and feedback"""
    asset_type: str
    records: List[AlarmFeedback] = field(default_factory=list)
    last_calibration: Optional[datetime] = None


# =============================================================================
# Deployment Metrics
# =============================================================================

@dataclass
class DeploymentMetrics:
    """Deployment-level metrics for reporting"""
    period_start: datetime
    period_end: datetime
    total_alarms: int
    actionable_alarms: int
    watch_alarms: int
    sensor_alerts: int
    alarms_per_unit_per_month: float
    actionable_per_unit_per_month: float
    no_issue_found_rate: float
    lead_time_hours_mean: Optional[float] = None
    lead_time_hours_p50: Optional[float] = None
