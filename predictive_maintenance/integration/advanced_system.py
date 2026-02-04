"""
PDM Advanced System - Integrated HVAC/R Predictive Maintenance

Integrates all advanced modeling approaches:
A) False positive budget (Neyman-Pearson constraint)
B) Radar-inspired residual modeling
C) Regime segmentation as first-class design
D) Three-layer inference (sensor trust, behavior, fault)
E) Probabilistic hypothesis testing
F) Calibrated uncertainty with deployment metrics
G) Equipment fingerprints and hierarchical modeling

This is the main entry point for the advanced PDM system.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..core.schemas import (
    AlertType,
    ChangePointDetection,
    DeploymentMetrics,
    EquipmentFingerprint,
    FalsePositiveBudget,
    FaultHypothesis,
    FaultType,
    FeedbackOutcome,
    HierarchicalModelConfig,
    OperatingRegime,
    PDMAlert,
    ResidualObservation,
    SensorTrustScore,
    SensorType,
)

from ..services.regime_service import (
    RegimeSegmentationService,
    TelemetrySnapshot,
)

from ..services.sensor_trust_service import (
    SensorTrustService,
    SensorReading,
)

from ..services.residual_service import (
    BehaviorModelService,
    BehaviorPrediction,
    ResidualErrorModelService,
)

from ..services.change_detection_service import (
    ChangeDetectorConfig,
    SequentialChangeDetectionService,
)

from ..services.fault_hypothesis_service import (
    FaultHypothesisService,
)

from ..services.decision_policy_service import (
    DecisionContext,
    DecisionPolicyService,
)

from ..services.fingerprint_service import (
    EquipmentFingerprintService,
)

logger = logging.getLogger(__name__)


@dataclass
class PDMSystemConfig:
    """Configuration for the integrated PDM system"""
    # False positive budget
    false_positive_budget: FalsePositiveBudget = field(default_factory=FalsePositiveBudget)
    
    # Change detection config
    change_detection_config: ChangeDetectorConfig = field(default_factory=ChangeDetectorConfig)
    
    # Hierarchical model config
    hierarchical_config: HierarchicalModelConfig = field(default_factory=HierarchicalModelConfig)
    
    # Processing intervals
    regime_update_interval_seconds: float = 60.0
    trust_update_interval_seconds: float = 60.0
    hypothesis_update_interval_seconds: float = 300.0
    
    # Minimum data requirements
    min_hours_for_baseline: float = 24.0
    min_hours_for_fingerprint: float = 168.0  # 1 week


class HVACRPdMAdvancedSystem:
    """
    Integrated HVAC/R Predictive Maintenance System.
    
    Implements the complete pipeline:
    1. Data ingestion with context
    2. Regime segmentation
    3. Sensor trust evaluation (Layer 1)
    4. Behavior prediction with hierarchical model
    5. Residual error modeling (radar-inspired)
    6. Sequential change detection (Layer 2)
    7. Fault hypothesis testing (Layer 3)
    8. Decision policy with FA budget
    9. Alert generation
    10. Human feedback loop
    
    Design Goals (non-negotiable):
    - ≤ 0.3 actionable alarms / unit / month
    - ≤ 5% of alarms lead to "no issue found" truck roll
    - Every alarm includes: estimated FA probability + confidence + evidence
    - Sensor integrity ≠ equipment health
    - Anomaly detection ≠ fault diagnosis
    """
    
    def __init__(self, 
                 asset_id: str,
                 config: Optional[PDMSystemConfig] = None):
        self.asset_id = asset_id
        self.config = config or PDMSystemConfig()
        
        # Initialize all services
        self.regime_service = RegimeSegmentationService(asset_id)
        self.sensor_trust_service = SensorTrustService(asset_id)
        self.behavior_model = BehaviorModelService(asset_id)
        self.residual_model = ResidualErrorModelService(asset_id)
        self.change_detector = SequentialChangeDetectionService(
            asset_id, self.config.change_detection_config
        )
        self.fault_hypothesis = FaultHypothesisService(asset_id)
        self.decision_policy = DecisionPolicyService(
            asset_id, self.config.false_positive_budget
        )
        self.fingerprint_service = EquipmentFingerprintService(
            asset_id, self.config.hierarchical_config
        )
        
        # State tracking
        self.current_regime: OperatingRegime = OperatingRegime.UNKNOWN
        self.last_regime_update: Optional[datetime] = None
        self.last_hypothesis_update: Optional[datetime] = None
        
        # Accumulated observations
        self.current_residuals: Dict[SensorType, ResidualObservation] = {}
        self.current_trust_scores: Dict[str, SensorTrustScore] = {}
        self.current_changes: Dict[str, ChangePointDetection] = {}
        
        # Latest alert
        self.current_alert: Optional[PDMAlert] = None
        
        # Statistics
        self.total_observations: int = 0
        self.hours_of_operation: float = 0.0
        self.start_time: datetime = datetime.utcnow()
        
        logger.info(f"HVACRPdMAdvancedSystem initialized for asset: {asset_id}")
    
    def process_telemetry(self, telemetry: Dict[str, Any]) -> PDMAlert:
        """
        Main entry point - process a telemetry snapshot.
        
        telemetry should include:
        - timestamp: datetime
        - sensor readings: {sensor_id: value}
        - compressor_on, fan_on, etc. for regime detection
        - ambient_temp (optional but recommended)
        
        Returns current alert status.
        """
        timestamp = telemetry.get("timestamp", datetime.utcnow())
        self.total_observations += 1
        
        # 1. Build telemetry snapshot for regime detection
        snapshot = self._build_snapshot(telemetry, timestamp)
        
        # 2. Regime segmentation
        regime_state = self.regime_service.classify_regime(snapshot)
        self.current_regime = regime_state.regime
        
        # 3. Process sensor readings through trust service
        sensor_readings = self._extract_sensor_readings(telemetry, timestamp)
        for reading in sensor_readings:
            trust = self.sensor_trust_service.process_reading(reading)
            self.current_trust_scores[reading.sensor_id] = trust
        
        # 4. Build context for behavior model
        context = self._build_context(telemetry, snapshot)
        
        # 5. For each sensor, compute residual
        for reading in sensor_readings:
            if not self.current_trust_scores.get(reading.sensor_id, 
                                                  SensorTrustScore(reading.sensor_id, 
                                                                   reading.sensor_type, 
                                                                   self.asset_id)).is_trusted(0.6):
                continue  # Skip untrusted sensors
            
            # Get behavior prediction
            prediction = self.behavior_model.predict(
                reading.sensor_type,
                self.current_regime,
                context,
                timestamp
            )
            
            # Compute residual
            residual = self.residual_model.compute_residual(
                reading.value,
                prediction,
                reading.sensor_id
            )
            self.current_residuals[reading.sensor_type] = residual
            
            # Update fingerprint
            self.fingerprint_service.observe(
                reading.sensor_type,
                self.current_regime,
                reading.value,
                context
            )
            
            # Update behavior model with observation
            self.behavior_model.update_with_observation(
                reading.value,
                reading.sensor_type,
                self.current_regime,
                context
            )
        
        # 6. Run change detection on residuals (use per-sensor trust)
        for sensor_type, residual in self.current_residuals.items():
            trust_score = self.current_trust_scores.get(
                residual.sensor_id,
                SensorTrustScore(
                    sensor_id=residual.sensor_id,
                    sensor_type=residual.sensor_type,
                    asset_id=self.asset_id,
                ),
            ).trust_score
            detection = self.change_detector.process_observation(
                residual,
                self.current_regime,
                trust_score,
            )
            self.current_changes[residual.sensor_id] = detection
        
        # 7. Update fault hypothesis periodically
        if self._should_update_hypothesis(timestamp):
            symptoms = self.fault_hypothesis.extract_symptoms(
                self.current_residuals,
                self.current_changes,
                telemetry
            )
            if symptoms:
                self.fault_hypothesis.update_hypothesis(symptoms)
            self.last_hypothesis_update = timestamp
        
        # 8. Build decision context
        decision_context = self._build_decision_context(telemetry, timestamp)
        
        # 9. Evaluate decision policy
        alert = self.decision_policy.evaluate(decision_context)
        self.current_alert = alert
        
        # Update hours of operation
        if self.last_regime_update:
            dt = (timestamp - self.last_regime_update).total_seconds() / 3600.0
            if self.current_regime != OperatingRegime.OFF:
                self.hours_of_operation += dt
        self.last_regime_update = timestamp
        
        return alert
    
    def _build_snapshot(self, telemetry: Dict[str, Any], 
                        timestamp: datetime) -> TelemetrySnapshot:
        """Build TelemetrySnapshot from raw telemetry"""
        return TelemetrySnapshot(
            timestamp=timestamp,
            asset_id=self.asset_id,
            compressor_on=telemetry.get("compressor_on", False),
            compressor_current=telemetry.get("compressor_current"),
            compressor_power=telemetry.get("compressor_power"),
            evap_fan_on=telemetry.get("evap_fan_on", False),
            condenser_fan_on=telemetry.get("condenser_fan_on", False),
            supply_fan_speed=telemetry.get("supply_fan_speed"),
            suction_temp=telemetry.get("suction_line_temp"),
            discharge_temp=telemetry.get("discharge_temp"),
            supply_air_temp=telemetry.get("supply_air_temp"),
            return_air_temp=telemetry.get("return_air_temp"),
            ambient_temp=telemetry.get("ambient_temp"),
            zone_temp=telemetry.get("zone_temp"),
            setpoint=telemetry.get("setpoint"),
            suction_pressure=telemetry.get("suction_pressure"),
            discharge_pressure=telemetry.get("discharge_pressure"),
            cooling_valve_pct=telemetry.get("cooling_valve_pct"),
            heating_valve_pct=telemetry.get("heating_valve_pct"),
            damper_position_pct=telemetry.get("damper_position_pct"),
            reversing_valve_heat=telemetry.get("reversing_valve_heat", False),
            superheat=telemetry.get("superheat"),
            subcool=telemetry.get("subcool"),
        )
    
    def _extract_sensor_readings(self, telemetry: Dict[str, Any],
                                  timestamp: datetime) -> List[SensorReading]:
        """Extract sensor readings from telemetry"""
        readings = []
        
        sensor_mapping = {
            "suction_pressure": SensorType.SUCTION_PRESSURE,
            "discharge_pressure": SensorType.DISCHARGE_PRESSURE,
            "suction_line_temp": SensorType.SUCTION_LINE_TEMP,
            "liquid_line_temp": SensorType.LIQUID_LINE_TEMP,
            "compressor_current": SensorType.COMPRESSOR_CURRENT,
            "compressor_power": SensorType.COMPRESSOR_POWER,
            "return_air_temp": SensorType.RETURN_AIR_TEMP,
            "supply_air_temp": SensorType.SUPPLY_AIR_TEMP,
            "ambient_temp": SensorType.AMBIENT_TEMP,
            "zone_temp": SensorType.ZONE_TEMP,
        }
        
        for key, sensor_type in sensor_mapping.items():
            if key in telemetry and telemetry[key] is not None:
                readings.append(SensorReading(
                    timestamp=timestamp,
                    sensor_id=f"{self.asset_id}_{key}",
                    sensor_type=sensor_type,
                    value=float(telemetry[key]),
                ))
        
        return readings
    
    def _build_context(self, telemetry: Dict[str, Any],
                       snapshot: TelemetrySnapshot) -> Dict[str, float]:
        """Build context dict for models"""
        context = {}
        
        if snapshot.ambient_temp is not None:
            context["ambient_temp"] = snapshot.ambient_temp
        
        if snapshot.return_air_temp is not None:
            context["return_air_temp"] = snapshot.return_air_temp
        
        if snapshot.setpoint is not None:
            context["setpoint"] = snapshot.setpoint
        
        # Estimate load proxy
        load_indicators = []
        if snapshot.compressor_power is not None:
            load_indicators.append(min(1.0, snapshot.compressor_power / 10.0))
        if snapshot.compressor_current is not None:
            load_indicators.append(min(1.0, snapshot.compressor_current / 20.0))
        
        if load_indicators:
            context["load_proxy"] = np.mean(load_indicators)
        else:
            context["load_proxy"] = 0.5 if snapshot.compressor_on else 0.0
        
        return context
    
    def _should_update_hypothesis(self, timestamp: datetime) -> bool:
        """Check if we should update fault hypothesis"""
        if self.last_hypothesis_update is None:
            return True
        
        elapsed = (timestamp - self.last_hypothesis_update).total_seconds()
        return elapsed >= self.config.hypothesis_update_interval_seconds
    
    def _build_decision_context(self, telemetry: Dict[str, Any],
                                 timestamp: datetime) -> DecisionContext:
        """Build decision context for policy evaluation"""
        # Get untrusted sensors
        untrusted = self.sensor_trust_service.get_untrusted_sensors(0.8)
        
        # Get min trust
        trust_scores = self.sensor_trust_service.get_all_trust_scores()
        min_trust = min([t.trust_score for t in trust_scores.values()], default=1.0)
        
        # Check for changes
        any_change = any(d.change_detected for d in self.current_changes.values())
        max_change_score = max([d.change_score for d in self.current_changes.values()], default=0.0)
        max_persistence = max([d.anomaly_duration_hours for d in self.current_changes.values()], default=0.0)
        n_sensors_change = sum(1 for d in self.current_changes.values() if d.change_score > 0.3)
        
        # Get hypothesis
        hypothesis = self.fault_hypothesis.current_hypothesis
        top_fault = None
        top_prob = 0.0
        is_concentrated = False
        
        if hypothesis:
            top_fault = hypothesis.most_likely_fault
            top_prob = hypothesis.posteriors.get(top_fault, 0) if top_fault else 0
            is_concentrated = hypothesis.is_concentrated
        
        return DecisionContext(
            timestamp=timestamp,
            asset_id=self.asset_id,
            current_regime=self.current_regime,
            is_steady_state=self.regime_service.is_steady_state(),
            sensor_trust_scores=trust_scores,
            min_sensor_trust=min_trust,
            untrusted_sensors=untrusted,
            change_detections=self.current_changes,
            any_change_detected=any_change,
            max_change_score=max_change_score,
            max_persistence_hours=max_persistence,
            n_sensors_with_change=n_sensors_change,
            hypothesis=hypothesis,
            top_fault=top_fault,
            top_fault_probability=top_prob,
            is_diagnosis_concentrated=is_concentrated,
            ambient_temp=telemetry.get("ambient_temp"),
            load_proxy=telemetry.get("load_proxy"),
        )
    
    def record_feedback(self, alert_id: str, outcome: FeedbackOutcome,
                        confirmed_fault: Optional[FaultType] = None,
                        notes: str = ""):
        """Record human feedback for an alert"""
        self.decision_policy.record_feedback(alert_id, outcome, confirmed_fault, notes)
        
        # Trigger recalibration if we have enough data
        if len(self.decision_policy.calibration_dataset.records) % 50 == 0:
            self.decision_policy.recalibrate()
    
    def fit_fingerprint(self):
        """Fit equipment fingerprint from accumulated data"""
        self.fingerprint_service.fit_fingerprint()
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        return {
            "asset_id": self.asset_id,
            "current_regime": self.current_regime.value,
            "is_steady_state": self.regime_service.is_steady_state(),
            "hours_of_operation": self.hours_of_operation,
            "total_observations": self.total_observations,
            "sensor_trust": {
                sensor_id: {
                    "trust": trust.trust_score,
                    "is_trusted": trust.is_trusted(),
                }
                for sensor_id, trust in self.current_trust_scores.items()
            },
            "active_changes": [
                {
                    "sensor": d.sensor_type.value,
                    "score": d.change_score,
                    "duration_hours": d.anomaly_duration_hours,
                }
                for d in self.current_changes.values()
                if d.change_score > 0.3
            ],
            "current_hypothesis": self.fault_hypothesis.get_hypothesis_summary(),
            "current_alert": self.current_alert.to_operator_dict() if self.current_alert else None,
            "fingerprint_ready": self.fingerprint_service.is_fingerprint_ready(),
            "policy_summary": self.decision_policy.get_policy_summary(),
        }
    
    def get_deployment_metrics(self,
                                period_start: datetime,
                                period_end: datetime) -> DeploymentMetrics:
        """Get deployment metrics for the specified period"""
        return self.decision_policy.get_deployment_metrics(period_start, period_end, n_units=1)
    
    def get_operator_dashboard(self) -> Dict[str, Any]:
        """Get operator-facing dashboard data"""
        status = self.get_system_status()
        
        dashboard = {
            "asset_id": self.asset_id,
            "status": "normal",
            "regime": status["current_regime"],
            "hours_monitored": self.hours_of_operation,
        }
        
        # Determine overall status
        if self.current_alert:
            if self.current_alert.alert_type == AlertType.ACTIONABLE:
                dashboard["status"] = "action_required"
            elif self.current_alert.alert_type == AlertType.WATCH:
                dashboard["status"] = "watching"
            elif self.current_alert.alert_type == AlertType.SENSOR_INTEGRITY:
                dashboard["status"] = "sensor_issue"
        
        # Add sensor health summary
        n_trusted = sum(1 for t in self.current_trust_scores.values() if t.is_trusted())
        n_total = len(self.current_trust_scores)
        dashboard["sensor_health"] = f"{n_trusted}/{n_total} sensors trusted"
        
        # Add fault summary if available
        if self.current_alert and self.current_alert.alert_type == AlertType.ACTIONABLE:
            dashboard["primary_fault"] = self.current_alert.primary_fault.value if self.current_alert.primary_fault else "unknown"
            dashboard["confidence"] = f"{self.current_alert.confidence:.0%}"
            dashboard["false_alarm_prob"] = f"{self.current_alert.false_alarm_probability:.1%}"
            dashboard["recommended_action"] = self.current_alert.recommended_action
        
        return dashboard


def create_pdm_system(asset_id: str,
                      max_alarms_per_month: float = 0.3,
                      max_fa_rate: float = 0.05) -> HVACRPdMAdvancedSystem:
    """
    Factory function to create a configured PDM system.
    
    Args:
        asset_id: Unique identifier for the asset
        max_alarms_per_month: Maximum actionable alarms per unit per month
        max_fa_rate: Maximum acceptable false alarm rate
    
    Returns:
        Configured HVACRPdMAdvancedSystem
    """
    budget = FalsePositiveBudget(
        max_actionable_alarms_per_unit_per_month=max_alarms_per_month,
        max_no_issue_found_rate=max_fa_rate,
    )
    
    config = PDMSystemConfig(
        false_positive_budget=budget,
    )
    
    return HVACRPdMAdvancedSystem(asset_id, config)
