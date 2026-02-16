"""
PDM Decision Policy Service

Enforces false positive budget and decides when to alarm.

Triggers only if:
- Change persists
- Confidence high
- Evidence consistent across points
- Not explained by sensor integrity issues

Emits:
- Alarm severity
- Recommended action
- "Wait and monitor" option

This is where operational false positive rate is controlled.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from ..core.schemas import (
    AlarmFeedback,
    AlertSeverity,
    AlertType,
    CalibrationDataset,
    ChangePointDetection,
    DeploymentMetrics,
    FalsePositiveBudget,
    FaultHypothesis,
    FaultType,
    FeedbackOutcome,
    JointChangeDetection,
    OperatingRegime,
    PDMAlert,
    SensorTrustScore,
)
from ..core.decision_contracts import (
    GateEvaluation,
    HardGate,
)
from ..services.fleet_budget_service import FleetBudgetService

try:
    from sqlalchemy.orm import Session  # type: ignore
except Exception:  # pragma: no cover
    Session = None  # type: ignore

from ..persistence.repositories import (
    AlertRepository,
    CalibrationRepository,
    FeedbackRepository,
)

logger = logging.getLogger(__name__)


@dataclass
class DecisionContext:
    """Context for making alarm decision"""
    timestamp: datetime
    asset_id: str
    
    # Regime
    current_regime: OperatingRegime
    is_steady_state: bool
    
    # Sensor trust
    sensor_trust_scores: Dict[str, SensorTrustScore]
    min_sensor_trust: float
    untrusted_sensors: List[str]
    
    # Change detection
    change_detections: Dict[str, ChangePointDetection]
    any_change_detected: bool
    max_change_score: float
    max_persistence_hours: float
    n_sensors_with_change: int
    
    # Fault hypothesis
    hypothesis: Optional[FaultHypothesis]
    top_fault: Optional[FaultType]
    top_fault_probability: float
    is_diagnosis_concentrated: bool
    
    # Telemetry context
    ambient_temp: Optional[float] = None
    load_proxy: Optional[float] = None

    # Joint (cross-sensor) change detection
    joint_change: Optional[JointChangeDetection] = None


class DecisionPolicyService:
    """
    Decision policy enforcing false positive budget.
    
    Key principles:
    1. Never alarm if sensor trust is low
    2. Require persistence (not point anomalies)
    3. Require confidence in diagnosis
    4. Track and respect false positive budget
    """
    _GATE_ORDER: List[HardGate] = [
        HardGate.SENSOR_TRUST,
        HardGate.STEADY_STATE_OR_CHANGE,
        HardGate.CHANGE_PRESENT,
        HardGate.PERSISTENCE,
        HardGate.DIAGNOSIS_CONFIDENCE,
        HardGate.BUDGET,
    ]
    
    def __init__(
        self,
        asset_id: str,
        budget: Optional[FalsePositiveBudget] = None,
        site_id: Optional[str] = None,
        session_factory: Optional[Callable[[], Session]] = None,
        fleet_budget_service: Optional[FleetBudgetService] = None,
        asset_type: str = "hvacr",
    ):
        self.asset_id = asset_id
        self.budget = budget or FalsePositiveBudget()
        self.site_id = site_id
        self.session_factory = session_factory
        self.fleet_budget_service = fleet_budget_service
        self.asset_type = asset_type
        
        # Alert history for calibration
        self.alert_history: List[PDMAlert] = []
        
        # Calibration data
        self.calibration_dataset = CalibrationDataset(asset_type="hvacr")
        
        # False alarm probability calibration (isotonic regression output)
        # Maps raw model confidence -> calibrated FA probability
        self.fa_calibration_curve: Dict[float, float] = {}
        self._initialize_default_calibration()
        self._loaded_feedback_ids: set = set()
        self._load_persistent_calibration()
        
        # Monthly tracking
        self.current_month_start: datetime = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
        self.monthly_alerts: int = 0
        self.monthly_no_issue_found: int = 0

        # Active actionable alert tracking (prevent alert spam)
        self.active_actionable_alert: Optional[PDMAlert] = None
        self.actionable_repeat_window_hours: float = 2.0
        self.last_gate_evaluations: List[GateEvaluation] = []
        
        logger.info(f"DecisionPolicyService initialized for asset: {asset_id}")

    def _load_persistent_calibration(self):
        """Load calibration curve and feedback from persistence, if available."""
        if self.session_factory is None:
            return
        try:
            session = self.session_factory()
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Calibration load skipped (session error): {exc}")
            return
        try:
            calib_repo = CalibrationRepository(session)
            state = calib_repo.get_for_asset(self.asset_id) or calib_repo.get_for_asset_type(self.asset_type)
            if state and state.calibration_curve:
                curve = {}
                for k, v in state.calibration_curve.items():
                    try:
                        curve[float(k)] = float(v)
                    except Exception:
                        continue
                if curve:
                    self.fa_calibration_curve.update(curve)
                    self.calibration_dataset.last_calibration = state.last_calibrated_at
            # Load feedback records for calibration
            feedback_repo = FeedbackRepository(session)
            records = feedback_repo.get_for_calibration(asset_type=self.asset_type, limit=2000)
            for fb in records:
                if fb.alert_id in self._loaded_feedback_ids:
                    continue
                self._loaded_feedback_ids.add(fb.alert_id)
                try:
                    predicted = {}
                    if fb.predicted_fault_distribution:
                        for k, v in fb.predicted_fault_distribution.items():
                            try:
                                predicted[FaultType(k)] = float(v)
                            except Exception:
                                continue
                    self.calibration_dataset.records.append(
                        AlarmFeedback(
                            alert_id=fb.alert_id,
                            asset_id=fb.asset_id,
                            outcome=FeedbackOutcome(fb.outcome),
                            confirmed_fault_type=FaultType(fb.confirmed_fault_type) if fb.confirmed_fault_type else None,
                            feedback_notes=fb.notes or "",
                            alarm_time=fb.alert_timestamp,
                            feedback_time=fb.feedback_at,
                            predicted_fault_distribution=predicted,
                            predicted_false_alarm_prob=fb.predicted_false_alarm_prob or 0.0,
                        )
                    )
                except Exception:
                    continue
        finally:
            session.close()
    
    def _initialize_default_calibration(self):
        """Initialize default FA calibration curve (conservative)"""
        # Default: assume model is overconfident
        # Calibration adjusts raw confidence to actual FA probability
        self.fa_calibration_curve = {
            0.0: 0.50,  # Low confidence -> 50% FA rate
            0.3: 0.30,
            0.5: 0.15,
            0.7: 0.08,
            0.8: 0.05,
            0.9: 0.03,
            0.95: 0.02,
            1.0: 0.01,
        }
    
    def evaluate(self, context: DecisionContext) -> PDMAlert:
        """
        Evaluate decision context and generate alert (or watch/no-alert).
        
        Returns PDMAlert with type, severity, and recommendations.
        """
        gates: List[GateEvaluation] = []

        # Check sensor trust first (Layer 1)
        sensor_alert = self._check_sensor_issues(context)
        sensor_gate_passed = sensor_alert is None
        sensor_reason = (
            "Sensor trust sufficient for analysis"
            if sensor_gate_passed
            else f"Minimum sensor trust {context.min_sensor_trust:.0%} below critical threshold 50%"
        )
        gates.append(
            GateEvaluation(
                gate=HardGate.SENSOR_TRUST,
                passed=sensor_gate_passed,
                reason=sensor_reason,
                metric=context.min_sensor_trust,
                threshold=0.5,
            )
        )
        # Check sensor trust first (Layer 1)
        if sensor_alert:
            self.active_actionable_alert = None
            self._finalize_gate_evaluations(gates)
            return sensor_alert
        
        # Check if we should suppress based on regime
        steady_or_change = context.is_steady_state or context.any_change_detected
        gates.append(
            GateEvaluation(
                gate=HardGate.STEADY_STATE_OR_CHANGE,
                passed=steady_or_change,
                reason=(
                    "Steady-state or active change condition satisfied"
                    if steady_or_change
                    else "System in transient regime without active changes"
                ),
                metric=1.0 if steady_or_change else 0.0,
                threshold=1.0,
            )
        )
        if not steady_or_change:
            self.active_actionable_alert = None
            self._finalize_gate_evaluations(gates)
            return self._create_no_alert(context, "System in transient regime; monitoring only")
        
        # Check change detection (Layer 2)
        gates.append(
            GateEvaluation(
                gate=HardGate.CHANGE_PRESENT,
                passed=context.any_change_detected,
                reason=(
                    "Persistent change detected"
                    if context.any_change_detected
                    else "No persistent change detected"
                ),
                metric=context.max_change_score,
                threshold=0.0,
            )
        )
        if not context.any_change_detected:
            self.active_actionable_alert = None
            self._finalize_gate_evaluations(gates)
            return self._create_no_alert(context, "No persistent change detected")
        
        # Check persistence criteria
        persistence_ok, persistence_reason = self._check_persistence(context)
        gates.append(
            GateEvaluation(
                gate=HardGate.PERSISTENCE,
                passed=persistence_ok,
                reason=persistence_reason if not persistence_ok else "Persistence criteria satisfied",
                metric=context.max_persistence_hours,
                threshold=self.budget.min_anomaly_persistence_hours,
            )
        )
        if not persistence_ok:
            self.active_actionable_alert = None
            self._finalize_gate_evaluations(gates)
            return self._create_watch_alert(context, persistence_reason)
        
        # Check diagnosis confidence (Layer 3)
        confidence_ok, confidence_reason = self._check_diagnosis_confidence(context)
        gates.append(
            GateEvaluation(
                gate=HardGate.DIAGNOSIS_CONFIDENCE,
                passed=confidence_ok,
                reason=confidence_reason if not confidence_ok else "Diagnosis confidence criteria satisfied",
                metric=context.top_fault_probability,
                threshold=self.budget.min_confidence_for_actionable,
            )
        )
        if not confidence_ok:
            self.active_actionable_alert = None
            self._finalize_gate_evaluations(gates)
            return self._create_watch_alert(context, confidence_reason)

        # If an actionable alert is already active for this event, reuse it
        if self._should_reuse_active_alert(context):
            gates.append(
                GateEvaluation(
                    gate=HardGate.BUDGET,
                    passed=True,
                    reason="Reusing active actionable alert within repeat window",
                    metric=self._calibrate_fa_probability(context.top_fault_probability),
                    threshold=self.budget.max_false_alarm_probability,
                )
            )
            self._finalize_gate_evaluations(gates)
            return self.active_actionable_alert
        
        # Check false positive budget
        budget_ok, budget_reason = self._check_budget(context)
        gates.append(
            GateEvaluation(
                gate=HardGate.BUDGET,
                passed=budget_ok,
                reason=budget_reason if not budget_ok else "False-positive budget constraints satisfied",
                metric=self._calibrate_fa_probability(context.top_fault_probability),
                threshold=self.budget.max_false_alarm_probability,
            )
        )
        if not budget_ok:
            self.active_actionable_alert = None
            self._finalize_gate_evaluations(gates)
            return self._create_watch_alert(context, budget_reason)
        
        # All checks passed - generate actionable alert
        self._finalize_gate_evaluations(gates)
        return self._create_actionable_alert(context)

    def _finalize_gate_evaluations(self, gates: List[GateEvaluation]):
        """Store ordered gate evaluations; mark any non-evaluated gates as skipped."""
        present = {g.gate for g in gates}
        for gate in self._GATE_ORDER:
            if gate not in present:
                gates.append(
                    GateEvaluation(
                        gate=gate,
                        passed=False,
                        reason="Skipped due to earlier gate failure",
                    )
                )
        gates.sort(key=lambda g: self._GATE_ORDER.index(g.gate))
        self.last_gate_evaluations = list(gates)

    def get_last_gate_evaluations(self) -> List[GateEvaluation]:
        """Return the gate evaluations recorded during the latest evaluation."""
        return list(self.last_gate_evaluations)

    def _should_reuse_active_alert(self, context: DecisionContext) -> bool:
        """Reuse active actionable alert within a short window to avoid alert spam."""
        if not self.active_actionable_alert:
            return False
        if not context.any_change_detected:
            return False
        age_seconds = (context.timestamp - self.active_actionable_alert.created_at).total_seconds()
        return age_seconds <= self.actionable_repeat_window_hours * 3600.0
    
    def _check_sensor_issues(self, context: DecisionContext) -> Optional[PDMAlert]:
        """Check for sensor integrity issues that would invalidate analysis"""
        if context.min_sensor_trust < 0.5:
            # Very low trust - sensor integrity alert
            return self._create_sensor_alert(context)
        
        if context.min_sensor_trust < self.budget.min_sensor_trust_score:
            # Below threshold but not critical - note in watch
            return None  # Handled by confidence check
        
        return None
    
    def _check_persistence(self, context: DecisionContext) -> Tuple[bool, str]:
        """Check if change meets persistence criteria"""
        # Minimum duration
        if context.max_persistence_hours < self.budget.min_anomaly_persistence_hours:
            remaining = self.budget.min_anomaly_persistence_hours - context.max_persistence_hours
            return False, f"Change detected but needs {remaining:.1f} more hours of persistence"
        
        # Minimum regime coverage
        for sensor_id, detection in context.change_detections.items():
            if detection.change_detected:
                if detection.n_regimes_observed < self.budget.min_regime_coverage_cycles:
                    return False, f"Need to observe change in {self.budget.min_regime_coverage_cycles - detection.n_regimes_observed} more steady-state cycles"
        
        return True, ""
    
    def _check_diagnosis_confidence(self, context: DecisionContext) -> Tuple[bool, str]:
        """Check if diagnosis is confident enough for actionable alert"""
        if not context.hypothesis:
            return False, "Gathering diagnostic evidence; no hypothesis yet"
        
        if not context.is_diagnosis_concentrated:
            return False, "Diagnosis not concentrated; multiple fault hypotheses possible"
        
        if context.top_fault_probability < self.budget.min_confidence_for_actionable:
            gap = self.budget.min_confidence_for_actionable - context.top_fault_probability
            return False, f"Confidence {context.top_fault_probability:.0%} below threshold; need {gap:.0%} more"
        
        # Check if top fault is sensor-related
        if context.top_fault in [FaultType.SENSOR_DRIFT, FaultType.SENSOR_STUCK]:
            # Sensor issues shouldn't be actionable maintenance alerts
            return False, "Top hypothesis is sensor issue; verify sensor before maintenance"
        
        return True, ""
    
    def _check_budget(self, context: DecisionContext) -> Tuple[bool, str]:
        """Check false positive budget constraints"""
        # Reset monthly counters if month has changed
        if context.timestamp.month != self.current_month_start.month or \
           context.timestamp.year != self.current_month_start.year:
            self.current_month_start = context.timestamp.replace(day=1, hour=0, minute=0, second=0)
            self.monthly_alerts = 0
            self.monthly_no_issue_found = 0

        # Enforce monthly alert budget (per unit)
        per_unit_count = self.monthly_alerts
        if self.fleet_budget_service is not None:
            try:
                per_unit_count = self.fleet_budget_service.count_actionable_for_asset(
                    self.asset_id, context.timestamp
                )
            except Exception:
                per_unit_count = self.monthly_alerts
        effective_unit_limit = self._effective_unit_alert_limit()
        if per_unit_count >= effective_unit_limit:
            return False, (
                f"Monthly alert budget exceeded: "
                f"{per_unit_count}/{effective_unit_limit} "
                f"(configured={self.budget.max_actionable_alarms_per_unit_per_month:.2f}/unit/month)"
            )

        # Enforce post-feedback no-issue-found cap
        if per_unit_count > 0:
            no_issue_rate = self.monthly_no_issue_found / per_unit_count
            if no_issue_rate > self.budget.max_no_issue_found_rate:
                return False, (
                    "No-issue-found rate exceeds budget: "
                    f"{no_issue_rate:.1%}/{self.budget.max_no_issue_found_rate:.1%}"
                )

        # Compute calibrated false alarm probability
        raw_confidence = context.top_fault_probability
        fa_prob = self._calibrate_fa_probability(raw_confidence)
        
        # Check against threshold
        if fa_prob > self.budget.max_false_alarm_probability:
            return False, f"Estimated FA probability {fa_prob:.1%} exceeds budget {self.budget.max_false_alarm_probability:.1%}"
        
        # Fleet/site-level budget enforcement
        if self.fleet_budget_service is not None and self.site_id:
            snapshot = self.fleet_budget_service.count_actionable_for_site(self.site_id, context.timestamp)
            fleet_limit = self.budget.max_actionable_alarms_per_fleet_per_month
            if fleet_limit is None and snapshot.total_assets > 0:
                # Use the raw fractional budget (e.g. 0.3/unit/month) for fleet
                # calculation, NOT the per-unit ceiling.  This preserves the
                # intended fleet-wide false-positive budget.
                fleet_limit = float(
                    self.budget.max_actionable_alarms_per_unit_per_month
                    * snapshot.total_assets
                )
            if fleet_limit is not None:
                fleet_limit = float(max(1, math.ceil(float(fleet_limit))))
            if fleet_limit is not None and snapshot.total_actionable_alerts >= fleet_limit:
                return False, (
                    f"Fleet alert budget exceeded: "
                    f"{snapshot.total_actionable_alerts}/{fleet_limit} "
                    f"(configured={self.budget.max_actionable_alarms_per_unit_per_month:.2f}/unit × "
                    f"{snapshot.total_assets} units)"
                )
        
        return True, ""

    def _effective_unit_alert_limit(self) -> int:
        """Convert configured monthly alert budget into an enforceable integer cap."""
        configured = float(self.budget.max_actionable_alarms_per_unit_per_month)
        if configured <= 0:
            return 0
        return max(1, int(math.ceil(configured)))
    
    def _calibrate_fa_probability(self, raw_confidence: float) -> float:
        """
        Apply calibration to get actual false alarm probability.
        
        Uses isotonic regression / Platt scaling results.
        """
        # Simple linear interpolation from calibration curve
        sorted_points = sorted(self.fa_calibration_curve.items())
        
        for i, (conf, fa) in enumerate(sorted_points):
            if raw_confidence <= conf:
                if i == 0:
                    return fa
                prev_conf, prev_fa = sorted_points[i-1]
                # Linear interpolation
                t = (raw_confidence - prev_conf) / (conf - prev_conf + 1e-10)
                return prev_fa + t * (fa - prev_fa)
        
        # Beyond highest point
        return sorted_points[-1][1]
    
    def _create_no_alert(self, context: DecisionContext, reason: str) -> PDMAlert:
        """Create a no-alert/normal status"""
        return PDMAlert(
            asset_id=self.asset_id,
            alert_type=AlertType.WATCH,
            severity=AlertSeverity.INFO,
            false_alarm_probability=1.0,  # Not an alarm
            confidence=0.0,
            fault_beliefs={},
            recommended_action=reason,
            action_urgency="monitor",
            regime_at_detection=context.current_regime,
            ambient_temp_at_detection=context.ambient_temp,
        )
    
    def _create_watch_alert(self, context: DecisionContext, reason: str) -> PDMAlert:
        """Create a watch alert - gathering more evidence"""
        # Include current hypothesis if available
        fault_beliefs = {}
        if context.hypothesis:
            fault_beliefs = context.hypothesis.posteriors.copy()
        
        # Compute preliminary FA estimate
        fa_prob = 0.5  # High uncertainty
        if context.top_fault_probability > 0:
            fa_prob = self._calibrate_fa_probability(context.top_fault_probability)
        
        evidence_summary = []
        if context.n_sensors_with_change > 0:
            evidence_summary.append(f"{context.n_sensors_with_change} sensors showing deviation")
        if context.max_persistence_hours > 0:
            evidence_summary.append(f"Anomaly persisting for {context.max_persistence_hours:.1f} hours")
        if context.top_fault:
            evidence_summary.append(f"Preliminary diagnosis: {context.top_fault.value}")
        
        return PDMAlert(
            asset_id=self.asset_id,
            alert_type=AlertType.WATCH,
            severity=AlertSeverity.LOW,
            false_alarm_probability=fa_prob,
            confidence=context.top_fault_probability,
            fault_beliefs=fault_beliefs,
            primary_fault=context.top_fault,
            evidence_summary=evidence_summary,
            recommended_action=f"Watch: {reason}",
            action_urgency="monitor",
            regime_at_detection=context.current_regime,
            ambient_temp_at_detection=context.ambient_temp,
        )
    
    def _create_sensor_alert(self, context: DecisionContext) -> PDMAlert:
        """Create sensor integrity alert"""
        evidence_summary = [
            f"Low sensor trust: {context.min_sensor_trust:.0%}",
            f"Untrusted sensors: {', '.join(context.untrusted_sensors[:3])}",
        ]
        
        return PDMAlert(
            asset_id=self.asset_id,
            alert_type=AlertType.SENSOR_INTEGRITY,
            severity=AlertSeverity.MEDIUM,
            false_alarm_probability=0.0,  # Not a false alarm - it's a real sensor issue
            confidence=0.9,
            fault_beliefs={FaultType.SENSOR_DRIFT: 0.5, FaultType.SENSOR_STUCK: 0.3},
            primary_fault=FaultType.SENSOR_DRIFT,
            evidence_summary=evidence_summary,
            recommended_action="Verify sensor calibration and wiring; do NOT dispatch for equipment fault",
            action_urgency="schedule",
            regime_at_detection=context.current_regime,
            ambient_temp_at_detection=context.ambient_temp,
        )
    
    def _create_actionable_alert(self, context: DecisionContext) -> PDMAlert:
        """Create actionable maintenance alert"""
        # Compute calibrated FA probability
        fa_prob = self._calibrate_fa_probability(context.top_fault_probability)
        
        # Build evidence summary
        evidence_summary = []
        if context.hypothesis:
            for ev in context.hypothesis.evidence[:5]:
                evidence_summary.append(ev.symptom)
        
        evidence_summary.append(f"Anomaly persistent for {context.max_persistence_hours:.1f} hours")
        evidence_summary.append(f"Observed in {context.n_sensors_with_change} sensors")
        
        # Determine severity based on fault type and probability
        severity = self._determine_severity(context)
        
        # Determine urgency
        urgency = self._determine_urgency(context, severity)

        # Escalation gate: if no-issue-found rate is approaching budget,
        # force human review before dispatch to protect false-positive budget.
        nif_escalate = False
        if self.monthly_alerts > 0:
            nif_rate = self.monthly_no_issue_found / self.monthly_alerts
            nif_threshold = self.budget.max_no_issue_found_rate
            if nif_rate >= nif_threshold * 0.75:
                nif_escalate = True
                urgency = "human_review"
                evidence_summary.append(
                    f"NIF rate {nif_rate:.0%} approaching budget {nif_threshold:.0%}; "
                    "routed for human review before dispatch"
                )
        
        # Get recommendation from hypothesis
        recommendation = ""
        if context.hypothesis:
            recommendation = context.hypothesis.recommended_action
        
        # Compute impact estimates
        energy_penalty, downtime_risk, comfort_risk = self._estimate_impact(context)
        
        alert = PDMAlert(
            asset_id=self.asset_id,
            alert_type=AlertType.ACTIONABLE,
            severity=severity,
            false_alarm_probability=fa_prob,
            confidence=context.top_fault_probability,
            fault_beliefs=context.hypothesis.posteriors if context.hypothesis else {},
            primary_fault=context.top_fault,
            secondary_fault=context.hypothesis.second_likely_fault if context.hypothesis else None,
            evidence_summary=evidence_summary,
            recommended_action=recommendation,
            action_urgency=urgency,
            energy_penalty_estimate_pct=energy_penalty,
            downtime_risk_score=downtime_risk,
            comfort_risk_score=comfort_risk,
            estimated_cost_if_ignored=self._estimate_cost_if_ignored(context),
            regime_at_detection=context.current_regime,
            ambient_temp_at_detection=context.ambient_temp,
            created_at=context.timestamp,
        )
        
        # Track alert
        self.alert_history.append(alert)
        self.monthly_alerts += 1
        self.active_actionable_alert = alert
        if self.fleet_budget_service is not None:
            self.fleet_budget_service.record_actionable_alert(self.asset_id, context.timestamp)
        self._persist_alert(alert)
        
        logger.info(f"Actionable alert generated: {context.top_fault.value if context.top_fault else 'unknown'} "
                   f"with confidence {context.top_fault_probability:.0%}")
        
        return alert
    
    def _determine_severity(self, context: DecisionContext) -> AlertSeverity:
        """Determine alert severity based on fault and confidence"""
        if not context.top_fault:
            return AlertSeverity.MEDIUM
        
        # Critical faults
        critical_faults = {FaultType.COMPRESSOR_DEGRADATION, FaultType.ELECTRICAL_ISSUE}
        if context.top_fault in critical_faults and context.top_fault_probability > 0.7:
            return AlertSeverity.CRITICAL
        
        # High severity faults
        high_faults = {FaultType.REFRIGERANT_LEAK, FaultType.TXV_RESTRICTION}
        if context.top_fault in high_faults and context.top_fault_probability > 0.6:
            return AlertSeverity.HIGH
        
        # Based on confidence
        if context.top_fault_probability > 0.8:
            return AlertSeverity.HIGH
        elif context.top_fault_probability > 0.6:
            return AlertSeverity.MEDIUM
        else:
            return AlertSeverity.LOW
    
    def _determine_urgency(self, context: DecisionContext, 
                           severity: AlertSeverity) -> str:
        """Determine action urgency"""
        if severity == AlertSeverity.CRITICAL:
            return "immediate"
        elif severity == AlertSeverity.HIGH:
            return "urgent"
        elif severity == AlertSeverity.MEDIUM:
            return "schedule"
        else:
            return "monitor"
    
    def _estimate_impact(self, context: DecisionContext) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Estimate impact if fault is not addressed"""
        if not context.top_fault:
            return None, None, None
        
        # Energy penalty estimates by fault type (%)
        energy_penalties = {
            FaultType.REFRIGERANT_LEAK: 15.0,
            FaultType.CONDENSER_FOULING: 20.0,
            FaultType.EVAPORATOR_FOULING: 15.0,
            FaultType.TXV_RESTRICTION: 10.0,
            FaultType.COMPRESSOR_DEGRADATION: 25.0,
            FaultType.FAN_DEGRADATION: 10.0,
        }
        
        # Downtime risk (probability of failure within 30 days)
        downtime_risks = {
            FaultType.REFRIGERANT_LEAK: 0.4,
            FaultType.COMPRESSOR_DEGRADATION: 0.6,
            FaultType.ELECTRICAL_ISSUE: 0.5,
            FaultType.TXV_RESTRICTION: 0.2,
            FaultType.FAN_DEGRADATION: 0.3,
        }
        
        # Comfort risk
        comfort_risks = {
            FaultType.REFRIGERANT_LEAK: 0.7,
            FaultType.COMPRESSOR_DEGRADATION: 0.8,
            FaultType.CONDENSER_FOULING: 0.5,
            FaultType.EVAPORATOR_FOULING: 0.5,
        }
        
        energy = energy_penalties.get(context.top_fault)
        downtime = downtime_risks.get(context.top_fault, 0.2)
        comfort = comfort_risks.get(context.top_fault, 0.3)
        
        # Scale by confidence
        if energy:
            energy *= context.top_fault_probability
        downtime *= context.top_fault_probability
        comfort *= context.top_fault_probability
        
        return energy, downtime, comfort
    
    def _estimate_cost_if_ignored(self, context: DecisionContext) -> Optional[float]:
        """Estimate cost if fault is ignored"""
        if not context.top_fault:
            return None
        
        # Base costs by fault type
        base_costs = {
            FaultType.REFRIGERANT_LEAK: 2000.0,
            FaultType.COMPRESSOR_DEGRADATION: 8000.0,
            FaultType.CONDENSER_FOULING: 500.0,
            FaultType.EVAPORATOR_FOULING: 500.0,
            FaultType.TXV_RESTRICTION: 1500.0,
            FaultType.FAN_DEGRADATION: 1000.0,
            FaultType.ELECTRICAL_ISSUE: 3000.0,
        }
        
        base = base_costs.get(context.top_fault, 1000.0)
        
        # Factor in confidence and add energy cost
        # Assuming 30-day delay and $0.12/kWh, 10kW unit, 40% runtime
        if context.top_fault in [FaultType.CONDENSER_FOULING, FaultType.EVAPORATOR_FOULING]:
            energy_cost = 0.15 * 10 * 24 * 30 * 0.4 * 0.12  # 15% penalty
            base += energy_cost
        
        return base * context.top_fault_probability
    
    def record_feedback(self, alert_id: str, outcome: FeedbackOutcome,
                        confirmed_fault: Optional[FaultType] = None,
                        notes: str = ""):
        """Record feedback for an alert (for calibration)"""
        # Find alert in history
        for alert in self.alert_history:
            if alert.alert_id == alert_id:
                alert.feedback_outcome = outcome
                alert.feedback_notes = notes
                alert.feedback_at = datetime.utcnow()
                
                if outcome == FeedbackOutcome.NO_ISSUE_FOUND:
                    self.monthly_no_issue_found += 1
                
                # Add to calibration dataset
                feedback = AlarmFeedback(
                    alert_id=alert_id,
                    asset_id=self.asset_id,
                    outcome=outcome,
                    confirmed_fault_type=confirmed_fault,
                    feedback_notes=notes,
                    alarm_time=alert.created_at,
                    feedback_time=datetime.utcnow(),
                    predicted_fault_distribution=alert.fault_beliefs,
                    predicted_false_alarm_prob=alert.false_alarm_probability,
                )
                self.calibration_dataset.records.append(feedback)
                self._persist_feedback(feedback)
                
                logger.info(f"Recorded feedback for alert {alert_id}: {outcome.value}")
                return

        # If not in memory, try to persist directly (use DB record if available)
        if self.session_factory is not None:
            try:
                session = self.session_factory()
                try:
                    repo = AlertRepository(session)
                    alert_model = repo.get_by_id(alert_id)
                    if alert_model:
                        predicted = {}
                        if alert_model.fault_beliefs:
                            for k, v in alert_model.fault_beliefs.items():
                                try:
                                    predicted[FaultType(k)] = float(v)
                                except Exception:
                                    continue
                        feedback = AlarmFeedback(
                            alert_id=alert_id,
                            asset_id=alert_model.asset_id,
                            outcome=outcome,
                            confirmed_fault_type=confirmed_fault,
                            feedback_notes=notes,
                            alarm_time=alert_model.created_at,
                            feedback_time=datetime.utcnow(),
                            predicted_fault_distribution=predicted,
                            predicted_false_alarm_prob=alert_model.false_alarm_probability or 0.0,
                        )
                        self.calibration_dataset.records.append(feedback)
                        self._persist_feedback(feedback)
                        # Update alert model with feedback metadata
                        repo.add_feedback(alert_id=alert_id, outcome=outcome.value, notes=notes)
                        session.commit()
                        logger.info(f"Recorded feedback from DB for alert {alert_id}: {outcome.value}")
                        return
                finally:
                    session.close()
            except Exception as exc:  # pragma: no cover
                logger.warning(f"Record feedback fallback failed: {exc}")
    
    def recalibrate(self):
        """Recalibrate false alarm probability from feedback data"""
        records = self.calibration_dataset.records
        if len(records) < 50:
            logger.warning("Insufficient feedback data for recalibration")
            return
        
        # Group by predicted FA probability bins
        bins = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        bin_outcomes: Dict[float, List[bool]] = {b: [] for b in bins[:-1]}
        
        for record in records:
            if record.outcome == FeedbackOutcome.PENDING:
                continue
            
            is_false_alarm = record.outcome == FeedbackOutcome.NO_ISSUE_FOUND
            pred_fa = record.predicted_false_alarm_prob
            
            # Find bin
            for i, b in enumerate(bins[:-1]):
                if b <= pred_fa < bins[i+1]:
                    bin_outcomes[b].append(is_false_alarm)
                    break
        
        # Compute actual FA rate per bin
        new_calibration = {}
        for b, outcomes in bin_outcomes.items():
            if len(outcomes) >= 5:
                actual_fa_rate = sum(outcomes) / len(outcomes)
                new_calibration[b] = actual_fa_rate
        
        if new_calibration:
            self.fa_calibration_curve.update(new_calibration)
            self.calibration_dataset.last_calibration = datetime.utcnow()
            self._persist_calibration_state(len(records))
            logger.info(f"Recalibrated FA curve with {len(records)} feedback records")
    
    def get_deployment_metrics(self, 
                                period_start: datetime,
                                period_end: datetime,
                                n_units: int = 1) -> DeploymentMetrics:
        """Compute deployment metrics for reporting"""
        # Filter alerts in period
        period_alerts = [
            a for a in self.alert_history
            if period_start <= a.created_at <= period_end
        ]
        
        actionable = [a for a in period_alerts if a.alert_type == AlertType.ACTIONABLE]
        watch = [a for a in period_alerts if a.alert_type == AlertType.WATCH]
        sensor = [a for a in period_alerts if a.alert_type == AlertType.SENSOR_INTEGRITY]
        
        # Compute no-issue-found rate
        with_feedback = [a for a in actionable if a.feedback_outcome is not None]
        no_issue = [a for a in with_feedback if a.feedback_outcome == FeedbackOutcome.NO_ISSUE_FOUND]
        no_issue_rate = len(no_issue) / max(len(with_feedback), 1)
        
        # Compute alarms per unit per month
        days = (period_end - period_start).days
        months = days / 30.0
        alarms_per_unit_per_month = len(actionable) / (n_units * max(months, 0.1))
        
        # Lead time (proxy: alert created -> feedback or resolution time)
        lead_times = []
        for alert in actionable:
            end_time = alert.feedback_at or alert.resolved_at
            if end_time and alert.created_at:
                hours = (end_time - alert.created_at).total_seconds() / 3600.0
                if hours >= 0:
                    lead_times.append(hours)

        lead_times_sorted = sorted(lead_times)
        def _percentile(values: List[float], pct: float) -> Optional[float]:
            if not values:
                return None
            k = int(round((len(values) - 1) * pct))
            return float(values[k])

        # Lead time histogram (hours)
        histogram = None
        if lead_times_sorted:
            bins = [0, 6, 24, 72, 168, 336, 720]
            labels = ["0-6h", "6-24h", "1-3d", "3-7d", "1-2w", "2-4w", ">4w"]
            counts = {label: 0 for label in labels}
            for lt in lead_times_sorted:
                placed = False
                for i in range(len(bins) - 1):
                    if bins[i] <= lt < bins[i + 1]:
                        counts[labels[i]] += 1
                        placed = True
                        break
                if not placed:
                    counts[labels[-1]] += 1
            histogram = counts

        # Precision@K for actionable alerts with feedback
        precision_at_k: Dict[int, float] = {}
        feedback_actionable = [a for a in actionable if a.feedback_outcome is not None]
        if feedback_actionable:
            sorted_by_conf = sorted(feedback_actionable, key=lambda a: a.confidence, reverse=True)
            for k in [1, 3, 5]:
                if len(sorted_by_conf) >= k:
                    top_k = sorted_by_conf[:k]
                    confirmed = sum(1 for a in top_k if a.feedback_outcome == FeedbackOutcome.CONFIRMED_FAULT)
                    precision_at_k[k] = confirmed / k
        
        return DeploymentMetrics(
            period_start=period_start,
            period_end=period_end,
            total_alarms=len(period_alerts),
            actionable_alarms=len(actionable),
            watch_alarms=len(watch),
            sensor_alerts=len(sensor),
            alarms_per_unit_per_month=alarms_per_unit_per_month,
            actionable_per_unit_per_month=len(actionable) / (n_units * max(months, 0.1)),
            no_issue_found_rate=no_issue_rate,
            lead_time_hours_mean=np.mean(lead_times) if lead_times else None,
            lead_time_hours_p50=np.median(lead_times) if lead_times else None,
            lead_time_hours_p90=_percentile(lead_times_sorted, 0.9),
            lead_time_hours_p95=_percentile(lead_times_sorted, 0.95),
            lead_time_hours_min=min(lead_times_sorted) if lead_times_sorted else None,
            lead_time_hours_max=max(lead_times_sorted) if lead_times_sorted else None,
            lead_time_hours_histogram=histogram,
            precision_at_k=precision_at_k,
        )
    
    def get_policy_summary(self) -> Dict[str, Any]:
        """Get summary of decision policy state"""
        return {
            "asset_id": self.asset_id,
            "budget": self.budget.to_dict(),
            "monthly_alerts": self.monthly_alerts,
            "monthly_no_issue_found": self.monthly_no_issue_found,
            "no_issue_found_rate": self.monthly_no_issue_found / max(self.monthly_alerts, 1),
            "total_alerts_tracked": len(self.alert_history),
            "calibration_records": len(self.calibration_dataset.records),
            "last_calibration": self.calibration_dataset.last_calibration.isoformat() 
                               if self.calibration_dataset.last_calibration else None,
        }

    def _persist_alert(self, alert: PDMAlert):
        """Persist alert to database if session factory is configured."""
        if self.session_factory is None:
            return
        try:
            session = self.session_factory()
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Persist alert skipped (session error): {exc}")
            return
        try:
            repo = AlertRepository(session)
            repo.create(
                asset_id=alert.asset_id,
                alert_id=alert.alert_id,
                alert_type=alert.alert_type.value,
                severity=alert.severity.value,
                false_alarm_probability=alert.false_alarm_probability,
                confidence=alert.confidence,
                primary_fault=alert.primary_fault.value if alert.primary_fault else None,
                secondary_fault=alert.secondary_fault.value if alert.secondary_fault else None,
                fault_beliefs={k.value: v for k, v in alert.fault_beliefs.items()},
                evidence_summary=alert.evidence_summary,
                recommended_action=alert.recommended_action,
                action_urgency=alert.action_urgency,
                energy_penalty_estimate_pct=alert.energy_penalty_estimate_pct,
                downtime_risk_score=alert.downtime_risk_score,
                comfort_risk_score=alert.comfort_risk_score,
                estimated_cost_if_ignored=alert.estimated_cost_if_ignored,
                regime_at_detection=alert.regime_at_detection.value if alert.regime_at_detection else None,
                ambient_temp_at_detection=alert.ambient_temp_at_detection,
                created_at=alert.created_at,
                resolved_at=alert.resolved_at,
                feedback_outcome=alert.feedback_outcome.value if alert.feedback_outcome else None,
                feedback_notes=alert.feedback_notes,
                feedback_at=alert.feedback_at,
            )
            session.commit()
        except Exception as exc:  # pragma: no cover
            session.rollback()
            logger.warning(f"Persist alert failed: {exc}")
        finally:
            session.close()

    def _persist_feedback(self, feedback: AlarmFeedback):
        """Persist feedback to database if session factory is configured."""
        if self.session_factory is None:
            return
        try:
            session = self.session_factory()
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Persist feedback skipped (session error): {exc}")
            return
        try:
            repo = FeedbackRepository(session)
            repo.create(
                alert_id=feedback.alert_id,
                asset_id=feedback.asset_id,
                outcome=feedback.outcome.value,
                confirmed_fault_type=feedback.confirmed_fault_type.value if feedback.confirmed_fault_type else None,
                notes=feedback.feedback_notes,
                alert_timestamp=feedback.alarm_time,
                predicted_fault_distribution={k.value: v for k, v in feedback.predicted_fault_distribution.items()},
                predicted_false_alarm_prob=feedback.predicted_false_alarm_prob,
            )
            session.commit()
        except Exception as exc:  # pragma: no cover
            session.rollback()
            logger.warning(f"Persist feedback failed: {exc}")
        finally:
            session.close()

    def _persist_calibration_state(self, n_records: int):
        """Persist calibration curve to database if session factory is configured."""
        if self.session_factory is None:
            return
        try:
            session = self.session_factory()
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Persist calibration skipped (session error): {exc}")
            return
        try:
            repo = CalibrationRepository(session)
            repo.upsert(
                asset_id=self.asset_id,
                asset_type=self.asset_type,
                calibration_curve={str(k): float(v) for k, v in self.fa_calibration_curve.items()},
                n_records=n_records,
                last_calibrated_at=self.calibration_dataset.last_calibration,
            )
            session.commit()
        except Exception as exc:  # pragma: no cover
            session.rollback()
            logger.warning(f"Persist calibration failed: {exc}")
        finally:
            session.close()
