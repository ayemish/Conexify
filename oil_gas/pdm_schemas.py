"""
PDM Advanced Schemas - Core Data Models for Predictive Maintenance

Implements radar-inspired detection theory with:
- False positive budget constraints (Neyman-Pearson)
- Operating regime segmentation
- Three-layer inference (sensor trust, behavior deviation, fault hypothesis)
- Probabilistic fault hypothesis testing
- Equipment fingerprints and hierarchical modeling
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
    RECOVERY = "recovery"  # Recovery after setpoint changes
    UNKNOWN = "unknown"


class AlertType(str, Enum):
    """Three-tier alert classification"""
    SENSOR_INTEGRITY = "sensor_integrity"  # Never a truck roll for hardware
    WATCH = "watch"  # Anomaly detected, gathering more evidence
    ACTIONABLE = "actionable"  # High confidence, recommend action


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
    # Refrigeration
    SUCTION_PRESSURE = "suction_pressure"
    DISCHARGE_PRESSURE = "discharge_pressure"
    SUCTION_LINE_TEMP = "suction_line_temp"
    LIQUID_LINE_TEMP = "liquid_line_temp"
    COMPRESSOR_CURRENT = "compressor_current"
    COMPRESSOR_POWER = "compressor_power"
    EVAP_FAN_STATUS = "evap_fan_status"
    CONDENSER_FAN_STATUS = "condenser_fan_status"
    VALVE_POSITION = "valve_position"
    # HVAC Airside
    RETURN_AIR_TEMP = "return_air_temp"
    SUPPLY_AIR_TEMP = "supply_air_temp"
    MIXED_AIR_TEMP = "mixed_air_temp"
    SUPPLY_FAN_SPEED = "supply_fan_speed"
    DAMPER_POSITION = "damper_position"
    COOLING_VALVE = "cooling_valve"
    HEATING_VALVE = "heating_valve"
    ZONE_TEMP = "zone_temp"
    # Environmental
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
    
    # Operational constraints
    max_actionable_alarms_per_unit_per_month: float = 0.3
    max_no_issue_found_rate: float = 0.05  # ≤5% truck rolls find nothing
    
    # Cost model
    cost_truck_roll: float = 250.0  # USD
    cost_missed_failure: float = 5000.0  # USD (includes downtime, emergency repair)
    cost_false_alarm: float = 300.0  # USD (truck roll + reputation)
    
    # Decision thresholds derived from budget
    min_confidence_for_actionable: float = 0.85
    max_false_alarm_probability: float = 0.02  # P(FA) < 2%
    min_anomaly_persistence_hours: float = 6.0
    min_regime_coverage_cycles: int = 2  # At least 2 steady-state cycles
    min_sensor_trust_score: float = 0.8
    
    # Calibration tracking
    realized_alarms_this_month: int = 0
    realized_no_issue_found: int = 0
    last_calibration: Optional[datetime] = None
    
    def get_remaining_budget(self, units_monitored: int) -> float:
        """Calculate remaining alarm budget for the month"""
        total_budget = self.max_actionable_alarms_per_unit_per_month * units_monitored
        return max(0, total_budget - self.realized_alarms_this_month)
    
    def should_suppress_alarm(self, false_alarm_prob: float, 
                               confidence: float) -> Tuple[bool, str]:
        """Check if alarm should be suppressed based on budget"""
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
            "min_confidence_for_actionable": self.min_confidence_for_actionable,
            "max_false_alarm_probability": self.max_false_alarm_probability,
        }


# =============================================================================
# Sensor Trust Model (Layer 1)
# =============================================================================

@dataclass
class SensorTrustScore:
    """
    Per-sensor trust assessment - Layer 1 of three-layer inference.
    "Do I trust this sensor stream right now?"
    """
    sensor_id: str
    sensor_type: SensorType
    asset_id: str
    
    # Trust components
    trust_score: float = 1.0  # Overall trust [0, 1]
    drift_likelihood: float = 0.0
    stuck_likelihood: float = 0.0
    comms_integrity: float = 1.0
    out_of_range_probability: float = 0.0
    
    # Evidence
    last_value: Optional[float] = None
    value_variance_24h: Optional[float] = None
    missing_data_rate: float = 0.0
    consecutive_identical_readings: int = 0
    
    # Timestamps
    computed_at: datetime = field(default_factory=datetime.utcnow)
    last_calibration: Optional[datetime] = None
    
    def is_trusted(self, threshold: float = 0.8) -> bool:
        return self.trust_score >= threshold
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sensor_id": self.sensor_id,
            "sensor_type": self.sensor_type.value,
            "trust_score": self.trust_score,
            "drift_likelihood": self.drift_likelihood,
            "stuck_likelihood": self.stuck_likelihood,
            "comms_integrity": self.comms_integrity,
            "is_trusted": self.is_trusted(),
        }


# =============================================================================
# Regime Segmentation
# =============================================================================

@dataclass
class RegimeState:
    """Current operating regime with confidence"""
    regime: OperatingRegime
    confidence: float
    start_time: datetime
    duration_seconds: float = 0.0
    
    # Context at regime start
    ambient_temp: Optional[float] = None
    load_proxy: Optional[float] = None
    
    # Transition info
    previous_regime: Optional[OperatingRegime] = None
    transition_reason: str = ""


@dataclass 
class RegimeSegment:
    """A segment of time in a specific regime"""
    segment_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    asset_id: str = ""
    regime: OperatingRegime = OperatingRegime.UNKNOWN
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    confidence: float = 1.0
    
    # Aggregate stats during segment
    avg_load: Optional[float] = None
    avg_ambient_temp: Optional[float] = None
    n_samples: int = 0


# =============================================================================
# Residual Error Model (Radar-Inspired)
# =============================================================================

@dataclass
class ResidualDistribution:
    """
    Regime-conditional residual distribution parameters.
    Models: r_t | regime, load ~ StudentT(μ, σ(load), ν)
    """
    regime: OperatingRegime
    sensor_type: SensorType
    
    # Distribution parameters
    mu: float = 0.0  # Location (should be ~0 for well-calibrated model)
    sigma: float = 1.0  # Scale (load-dependent)
    nu: float = 4.0  # Degrees of freedom (heavy tails)
    
    # Heteroskedasticity: σ = σ_base + σ_load * load
    sigma_base: float = 1.0
    sigma_load_coef: float = 0.0
    
    # Autocorrelation: r_t = φ * r_{t-1} + ε_t
    phi: float = 0.0  # AR(1) coefficient
    
    # Drift parameters
    drift_rate: float = 0.0  # Mean drift per hour
    
    # Calibration
    n_samples_fitted: int = 0
    last_updated: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ResidualObservation:
    """Single residual observation with context"""
    timestamp: datetime
    sensor_id: str
    sensor_type: SensorType
    regime: OperatingRegime
    
    # Values
    observed: float
    predicted: float
    residual: float
    
    # Context
    load_proxy: Optional[float] = None
    ambient_temp: Optional[float] = None
    
    # Statistical measures
    z_score: Optional[float] = None
    p_value: Optional[float] = None  # P(|R| ≥ |r| | normal)
    log_likelihood: Optional[float] = None


# =============================================================================
# Change Detection (Sequential Tests)
# =============================================================================

@dataclass
class ChangePointDetection:
    """
    Sequential change detection state (CUSUM/GLR style).
    Detects: "System no longer behaving like itself under these conditions."
    """
    detector_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    asset_id: str = ""
    sensor_type: SensorType = SensorType.SUCTION_PRESSURE
    
    # CUSUM state
    cusum_pos: float = 0.0  # Positive CUSUM
    cusum_neg: float = 0.0  # Negative CUSUM
    cusum_threshold: float = 5.0  # Detection threshold
    
    # GLR (Generalized Likelihood Ratio) state
    glr_statistic: float = 0.0
    glr_threshold: float = 10.0
    
    # Detection state
    change_detected: bool = False
    change_score: float = 0.0  # [0, 1] confidence
    estimated_onset_time: Optional[datetime] = None
    stability_score: float = 1.0  # How stable/consistent the change is
    
    # Persistence tracking
    anomaly_start_time: Optional[datetime] = None
    anomaly_duration_hours: float = 0.0
    n_anomalous_samples: int = 0
    n_regimes_observed: int = 0
    
    # State
    last_updated: datetime = field(default_factory=datetime.utcnow)
    
    def meets_persistence_criteria(self, min_hours: float = 6.0, 
                                    min_regimes: int = 2) -> bool:
        """Check if change meets persistence criteria for alerting"""
        return (self.anomaly_duration_hours >= min_hours and 
                self.n_regimes_observed >= min_regimes)


# =============================================================================
# Fault Hypothesis Model (Bayesian Evidence Fusion)
# =============================================================================

@dataclass
class FaultEvidence:
    """Evidence factor for a specific fault hypothesis"""
    evidence_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    fault_type: FaultType = FaultType.UNKNOWN_ANOMALY
    
    # Evidence description
    symptom: str = ""  # e.g., "rising superheat trend"
    sensor_sources: List[str] = field(default_factory=list)
    
    # Likelihood ratio: P(evidence | fault) / P(evidence | normal)
    likelihood_ratio: float = 1.0
    
    # Evidence strength
    strength: float = 0.0  # [0, 1]
    confidence: float = 0.0
    
    # Temporal
    first_observed: datetime = field(default_factory=datetime.utcnow)
    last_observed: datetime = field(default_factory=datetime.utcnow)
    persistence_hours: float = 0.0


@dataclass
class FaultHypothesis:
    """
    Probabilistic fault hypothesis - NOT multiclass classification.
    Maintains belief state P(fault_i | evidence).
    """
    hypothesis_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    asset_id: str = ""
    
    # Prior probabilities (from fleet statistics)
    priors: Dict[FaultType, float] = field(default_factory=dict)
    
    # Posterior probabilities P(fault | evidence)
    posteriors: Dict[FaultType, float] = field(default_factory=dict)
    
    # Evidence accumulated
    evidence: List[FaultEvidence] = field(default_factory=list)
    
    # Top hypotheses
    most_likely_fault: Optional[FaultType] = None
    second_likely_fault: Optional[FaultType] = None
    probability_mass_top2: float = 0.0  # Concentration on top 2
    
    # Decision support
    is_concentrated: bool = False  # Probability mass on 1-2 hypotheses
    recommended_action: str = ""
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def get_belief_distribution(self) -> Dict[str, float]:
        """Get current belief distribution as dict"""
        return {ft.value: prob for ft, prob in self.posteriors.items()}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "asset_id": self.asset_id,
            "posteriors": self.get_belief_distribution(),
            "most_likely_fault": self.most_likely_fault.value if self.most_likely_fault else None,
            "probability_mass_top2": self.probability_mass_top2,
            "is_concentrated": self.is_concentrated,
            "n_evidence": len(self.evidence),
        }


# =============================================================================
# Alarm / Alert Output
# =============================================================================

@dataclass
class PDMAlert:
    """
    Complete alert output with probabilistic information.
    Every alarm includes: estimated FA probability + confidence + evidence.
    """
    alert_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    asset_id: str = ""
    
    # Alert classification
    alert_type: AlertType = AlertType.WATCH
    severity: AlertSeverity = AlertSeverity.MEDIUM
    
    # Probabilistic outputs (non-negotiable requirement)
    false_alarm_probability: float = 0.5  # Fleet-calibrated
    confidence: float = 0.5
    
    # Fault belief distribution
    fault_beliefs: Dict[FaultType, float] = field(default_factory=dict)
    primary_fault: Optional[FaultType] = None
    secondary_fault: Optional[FaultType] = None
    
    # Evidence summary
    evidence_summary: List[str] = field(default_factory=list)
    # e.g., ["Head pressure elevated vs ambient by +2.4σ",
    #        "Superheat trend +1.8°F/day over last 7 days"]
    
    # Recommended action
    recommended_action: str = ""
    action_urgency: str = "monitor"  # monitor, schedule, urgent, immediate
    
    # Impact estimates
    energy_penalty_estimate_pct: Optional[float] = None
    downtime_risk_score: Optional[float] = None  # [0, 1]
    comfort_risk_score: Optional[float] = None  # [0, 1]
    estimated_cost_if_ignored: Optional[float] = None
    
    # Context
    regime_at_detection: OperatingRegime = OperatingRegime.UNKNOWN
    ambient_temp_at_detection: Optional[float] = None
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    
    # Feedback tracking
    feedback_outcome: Optional[FeedbackOutcome] = None
    feedback_notes: str = ""
    time_to_resolution_hours: Optional[float] = None
    
    def to_operator_dict(self) -> Dict[str, Any]:
        """Format for operator-facing display"""
        return {
            "alert_id": self.alert_id,
            "asset_id": self.asset_id,
            "type": self.alert_type.value,
            "severity": self.severity.value,
            "fault_belief_distribution": {
                ft.value: f"{prob:.0%}" 
                for ft, prob in sorted(self.fault_beliefs.items(), 
                                       key=lambda x: -x[1])[:5]
            },
            "false_alarm_likelihood": f"{self.false_alarm_probability:.1%} (fleet-calibrated)",
            "confidence": f"{self.confidence:.0%}",
            "evidence": self.evidence_summary,
            "recommended_action": self.recommended_action,
            "impact": {
                "energy_penalty": f"{self.energy_penalty_estimate_pct:.1f}%" if self.energy_penalty_estimate_pct else "N/A",
                "downtime_risk": f"{self.downtime_risk_score:.0%}" if self.downtime_risk_score else "N/A",
                "comfort_risk": f"{self.comfort_risk_score:.0%}" if self.comfort_risk_score else "N/A",
            },
        }


# =============================================================================
# Equipment Fingerprint & Hierarchical Model
# =============================================================================

@dataclass
class EquipmentFingerprint:
    """
    Per-unit learned fingerprint for hierarchical modeling.
    Prevents "different install" from being flagged as "fault".
    """
    fingerprint_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    asset_id: str = ""
    asset_type: str = ""  # e.g., "rooftop_unit", "split_system", "chiller"
    
    # Installation context
    climate_zone: str = ""
    building_type: str = ""
    installation_date: Optional[datetime] = None
    
    # Learned baseline parameters (per regime)
    regime_baselines: Dict[OperatingRegime, Dict[str, float]] = field(default_factory=dict)
    # e.g., {STEADY_COOL: {"superheat_mean": 12.5, "superheat_std": 1.2, ...}}
    
    # Sensor calibration offsets
    sensor_offsets: Dict[str, float] = field(default_factory=dict)
    
    # Operating characteristics
    typical_duty_cycle: Optional[float] = None
    typical_cycles_per_hour: Optional[float] = None
    capacity_rating: Optional[float] = None  # tons or kW
    
    # Adaptation tracking
    hours_of_data: float = 0.0
    n_regimes_observed: Dict[OperatingRegime, int] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=datetime.utcnow)
    adaptation_confidence: float = 0.0  # [0, 1]
    
    def is_sufficiently_learned(self, min_hours: float = 168.0) -> bool:
        """Check if fingerprint has enough data"""
        return self.hours_of_data >= min_hours and self.adaptation_confidence >= 0.7


@dataclass
class HierarchicalModelConfig:
    """
    Configuration for hierarchical model structure:
    - Global model: general HVAC physics/behavior
    - Per-unit adaptation: equipment fingerprint
    - Per-climate/building adjustment
    """
    config_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    
    # Global model weight vs local adaptation
    global_weight: float = 0.3  # Start with 30% global
    local_weight: float = 0.7  # 70% local adaptation
    
    # Adaptation parameters
    adaptation_learning_rate: float = 0.01
    min_samples_for_adaptation: int = 1000
    max_adaptation_drift: float = 0.2  # Max deviation from global
    
    # Transfer learning
    enable_fleet_transfer: bool = True
    similar_asset_weight: float = 0.1  # Weight for similar assets


# =============================================================================
# Human Feedback Loop
# =============================================================================

@dataclass
class AlarmFeedback:
    """Human feedback for alarm calibration"""
    feedback_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    alert_id: str = ""
    asset_id: str = ""
    
    # Outcome
    outcome: FeedbackOutcome = FeedbackOutcome.PENDING
    confirmed_fault_type: Optional[FaultType] = None
    
    # Details
    technician_id: str = ""
    feedback_notes: str = ""
    work_order_id: Optional[str] = None
    
    # Timing
    alarm_time: datetime = field(default_factory=datetime.utcnow)
    feedback_time: Optional[datetime] = None
    time_to_resolution_hours: Optional[float] = None
    
    # Model predictions at alarm time (for calibration)
    predicted_fault_distribution: Dict[FaultType, float] = field(default_factory=dict)
    predicted_false_alarm_prob: float = 0.0
    
    def to_calibration_record(self) -> Dict[str, Any]:
        """Format for calibration dataset"""
        return {
            "alert_id": self.alert_id,
            "asset_id": self.asset_id,
            "outcome": self.outcome.value,
            "confirmed_fault": self.confirmed_fault_type.value if self.confirmed_fault_type else None,
            "predicted_fa_prob": self.predicted_false_alarm_prob,
            "was_false_alarm": self.outcome == FeedbackOutcome.NO_ISSUE_FOUND,
            "time_to_resolution_hours": self.time_to_resolution_hours,
        }


@dataclass
class CalibrationDataset:
    """Dataset for false alarm probability calibration"""
    dataset_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    asset_type: str = ""
    
    # Records
    records: List[AlarmFeedback] = field(default_factory=list)
    
    # Calibration results
    calibration_curve: Dict[str, float] = field(default_factory=dict)
    # Maps predicted probability bin -> actual false alarm rate
    
    # Statistics
    total_alarms: int = 0
    confirmed_faults: int = 0
    false_alarms: int = 0
    sensor_issues: int = 0
    
    last_calibration: Optional[datetime] = None
    calibration_quality: float = 0.0  # Brier score or similar


# =============================================================================
# Evaluation Metrics (Deployment-Focused)
# =============================================================================

@dataclass
class DeploymentMetrics:
    """
    Evaluation metrics that matter for deployment.
    Not just AUROC - actual operational impact.
    """
    metrics_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    period_start: datetime = field(default_factory=datetime.utcnow)
    period_end: datetime = field(default_factory=datetime.utcnow)
    
    # Alarm volume
    total_alarms: int = 0
    actionable_alarms: int = 0
    watch_alarms: int = 0
    sensor_alerts: int = 0
    
    # Per-unit rates
    alarms_per_unit_per_month: float = 0.0
    actionable_per_unit_per_month: float = 0.0
    
    # Precision metrics
    precision_at_top_k: Dict[int, float] = field(default_factory=dict)
    # e.g., {5: 0.95, 10: 0.90, 20: 0.85}
    
    no_issue_found_rate: float = 0.0
    sensor_issue_rate: float = 0.0
    
    # Detection quality
    lead_time_hours_mean: Optional[float] = None
    lead_time_hours_p50: Optional[float] = None
    lead_time_hours_p90: Optional[float] = None
    
    # Business impact
    truck_rolls_saved: int = 0
    estimated_cost_savings: float = 0.0
    downtime_prevented_hours: float = 0.0
    
    # Calibration quality
    calibration_error: float = 0.0  # Expected calibration error
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "period": f"{self.period_start.date()} to {self.period_end.date()}",
            "alarms_per_unit_per_month": f"{self.alarms_per_unit_per_month:.2f}",
            "no_issue_found_rate": f"{self.no_issue_found_rate:.1%}",
            "precision_at_top_5": f"{self.precision_at_top_k.get(5, 0):.1%}",
            "lead_time_p50_hours": self.lead_time_hours_p50,
            "truck_rolls_saved": self.truck_rolls_saved,
            "estimated_savings": f"${self.estimated_cost_savings:,.0f}",
        }
