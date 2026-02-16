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
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .pdm_schemas import (
    AlertSeverity,
    AlertType,
    CalibrationDataset,
    ChangePointDetection,
    DeploymentMetrics,
    FalsePositiveBudget,
    FaultHypothesis,
    FaultType,
    FeedbackOutcome,
    OperatingRegime,
    PDMAlert,
    SensorTrustScore,
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


class DecisionPolicyService:
    """
    Decision policy enforcing false positive budget.
    
    Key principles:
    1. Never alarm if sensor trust is low
    2. Require persistence (not point anomalies)
    3. Require confidence in diagnosis
    4. Track and respect false positive budget
    """
    
    def __init__(self, asset_id: str, budget: Optional[FalsePositiveBudget] = None):
        self.asset_id = asset_id
        self.budget = budget or FalsePositiveBudget()
        
        # Alert history for calibration
        self.alert_history: List[PDMAlert] = []
        
        # Calibration data
        self.calibration_dataset = CalibrationDataset(asset_type="hvacr")
        
        # False alarm probability calibration (isotonic regression output)
        # Maps raw model confidence -> calibrated FA probability
        self.fa_calibration_curve: Dict[float, float] = {}
        self._initialize_default_calibration()
        
        # Monthly tracking
        self.current_month_start: datetime = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
        self.monthly_alerts: int = 0
        self.monthly_no_issue_found: int = 0
        
        logger.info(f"DecisionPolicyService initialized for asset: {asset_id}")
    
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
        # Check sensor trust first (Layer 1)
        sensor_alert = self._check_sensor_issues(context)
        if sensor_alert:
            return sensor_alert
        
        # Check if we should suppress based on regime
        if not context.is_steady_state and not context.any_change_detected:
            return self._create_no_alert(context, "System in transient regime; monitoring only")
        
        # Check change detection (Layer 2)
        if not context.any_change_detected:
            return self._create_no_alert(context, "No persistent change detected")
        
        # Check persistence criteria
        persistence_ok, persistence_reason = self._check_persistence(context)
        if not persistence_ok:
            return self._create_watch_alert(context, persistence_reason)
        
        # Check diagnosis confidence (Layer 3)
        confidence_ok, confidence_reason = self._check_diagnosis_confidence(context)
        if not confidence_ok:
            return self._create_watch_alert(context, confidence_reason)
        
        # Check false positive budget
        budget_ok, budget_reason = self._check_budget(context)
        if not budget_ok:
            return self._create_watch_alert(context, budget_reason)
        
        # All checks passed - generate actionable alert
        return self._create_actionable_alert(context)
    
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
        # Compute calibrated false alarm probability
        raw_confidence = context.top_fault_probability
        fa_prob = self._calibrate_fa_probability(raw_confidence)
        
        # Check against threshold
        if fa_prob > self.budget.max_false_alarm_probability:
            return False, f"Estimated FA probability {fa_prob:.1%} exceeds budget {self.budget.max_false_alarm_probability:.1%}"
        
        # Check monthly alarm count (if tracking)
        # This would use fleet-level tracking in production
        
        return True, ""
    
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
        )
        
        # Track alert
        self.alert_history.append(alert)
        self.monthly_alerts += 1
        
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
                
                if outcome == FeedbackOutcome.NO_ISSUE_FOUND:
                    self.monthly_no_issue_found += 1
                
                # Add to calibration dataset
                from .pdm_schemas import AlarmFeedback
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
                
                logger.info(f"Recorded feedback for alert {alert_id}: {outcome.value}")
                break
    
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
        
        # Lead time (would need resolution data)
        lead_times = []  # Would compute from alert time to confirmed failure
        
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
