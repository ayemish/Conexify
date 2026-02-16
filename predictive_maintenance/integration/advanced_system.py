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
import uuid
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
    JointChangeDetection,
    HierarchicalModelConfig,
    OperatingRegime,
    PDMAlert,
    ResidualObservation,
    SensorTrustScore,
    SensorType,
)
from ..core.decision_contracts import (
    HypothesisSnapshot,
    KernelDecisionArtifact,
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
from ..services.context_service import ContextService
from ..services.fleet_budget_service import FleetBudgetService
from ..services.rag_service import get_rag_service
from ..services.alert_incident_bridge import AlertIncidentBridge
from ..services.rul_estimation_service import RULEstimationService
from ..services.health_index_service import HealthIndexService
from ..services.drift_detection_service import DriftDetectionService
from ..services.retraining_trigger_service import RetrainingTriggerService
from ..integration.event_bus import PdMEventFactory, InMemoryEventBus

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
                 config: Optional[PDMSystemConfig] = None,
                 site_id: Optional[str] = None,
                 session_factory: Optional[Any] = None):
        self.asset_id = asset_id
        self.config = config or PDMSystemConfig()
        self.site_id = site_id
        self.session_factory = session_factory
        
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
            asset_id,
            self.config.false_positive_budget,
            site_id=self.site_id,
            session_factory=self.session_factory,
            fleet_budget_service=FleetBudgetService(self.session_factory),
            asset_type="hvacr",
        )
        self.fingerprint_service = EquipmentFingerprintService(
            asset_id, self.config.hierarchical_config
        )
        self.context_service = ContextService()
        self.alert_bridge = AlertIncidentBridge(
            session_factory=self.session_factory,
            tenant_id="default",
            auto_create_run=True,
        )
        self.rul_service = RULEstimationService(asset_id)
        self.health_index_service = HealthIndexService(asset_id)
        self.retraining_trigger = RetrainingTriggerService()
        self.drift_detector = DriftDetectionService(
            asset_id=asset_id,
            on_drift=lambda sig: self.retraining_trigger.record_drift_detected(
                model_id=sig.model_id,
                asset_id=asset_id,
                drift_score=sig.score,
                drift_type=sig.drift_type,
            ),
        )
        
        # Event bus for pipeline event publishing
        self._event_factory = PdMEventFactory(
            source_agent="kernel",
            tenant_id="default",
        )
        self._event_bus = None  # lazily resolved
        
        # Phase 3-4 Advanced Services (optional, lazy-loaded)
        self._explainability_service = None
        self._ensemble_calibration = None
        self._adaptive_weights = None
        self._tft_predictor = None
        self._physics_constraints = None
        self._fleet_correlation = None
        
        # State tracking
        self.current_regime: OperatingRegime = OperatingRegime.UNKNOWN
        self.last_regime_update: Optional[datetime] = None
        self.last_hypothesis_update: Optional[datetime] = None
        self.last_rag_index_at: Optional[datetime] = None
        
        # Accumulated observations
        self.current_residuals: Dict[SensorType, ResidualObservation] = {}
        self.current_residuals_by_id: Dict[str, ResidualObservation] = {}
        self.current_trust_scores: Dict[str, SensorTrustScore] = {}
        self.current_changes: Dict[str, ChangePointDetection] = {}
        self.joint_change: Optional[JointChangeDetection] = None
        self.last_context: Dict[str, float] = {}
        
        # Latest alert
        self.current_alert: Optional[PDMAlert] = None
        self.last_decision_artifact: Optional[KernelDecisionArtifact] = None
        self.current_rul = None
        self.current_health = None
        
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

        # Reset per-tick observation containers
        self.current_residuals = {}
        self.current_residuals_by_id = {}
        
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
        self.last_context = context
        
        # 5. For each sensor, compute residual
        for reading in sensor_readings:
            if not self.current_trust_scores.get(reading.sensor_id, 
                                                  SensorTrustScore(reading.sensor_id, 
                                                                   reading.sensor_type, 
                                                                   self.asset_id)).is_trusted(0.6):
                continue  # Skip untrusted sensors
            
            # Get behavior prediction
            prediction = self._predict_behavior(reading, context, timestamp)
            
            # Compute residual
            residual = self.residual_model.compute_residual(
                reading.value,
                prediction,
                reading.sensor_id
            )
            self.current_residuals[reading.sensor_type] = residual
            self.current_residuals_by_id[reading.sensor_id] = residual
            
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

        # 6b. Joint change detection (cross-sensor fused LLR)
        trust_scores = {
            sensor_id: trust.trust_score for sensor_id, trust in self.current_trust_scores.items()
        }
        self.joint_change = self.change_detector.process_joint_observations(
            self.current_residuals_by_id,
            self.current_regime,
            trust_scores,
        )
        
        # 6c. Feed drift detector with feature values and residual errors
        try:
            feature_dict = {
                sid: reading.value
                for reading in sensor_readings
                for sid in [reading.sensor_id]
            }
            avg_residual_error = 0.0
            if self.current_residuals_by_id:
                z_vals = [
                    getattr(r, "z_score", 0.0)
                    for r in self.current_residuals_by_id.values()
                ]
                avg_residual_error = float(np.mean(z_vals)) if z_vals else 0.0

            fault_label = None
            if hasattr(self, "fault_hypothesis") and self.fault_hypothesis:
                h = self.fault_hypothesis.get_current_hypothesis()
                if h and hasattr(h, "top_fault") and h.top_fault:
                    fault_label = h.top_fault.value if hasattr(h.top_fault, "value") else str(h.top_fault)

            self.drift_detector.observe(
                features=feature_dict,
                prediction_error=avg_residual_error,
                fault_label=fault_label,
                timestamp=timestamp,
            )
        except Exception as exc:
            logger.debug(f"Drift detection skipped: {exc}")

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

        # 9a. Calibrate ensemble uncertainty on top of policy output
        # (post-gate adjustment to avoid changing deterministic gate order).
        self._apply_ensemble_uncertainty(alert, decision_context)
        
        # Update hours of operation
        if self.last_regime_update:
            dt = (timestamp - self.last_regime_update).total_seconds() / 3600.0
            if self.current_regime != OperatingRegime.OFF:
                self.hours_of_operation += dt
        self.last_regime_update = timestamp

        # 9b. RUL estimation (runs after fault hypothesis and decision)
        try:
            change_scores = {
                sid: det.cusum_score for sid, det in self.current_changes.items()
                if hasattr(det, "cusum_score")
            }
            residual_z = {
                sid: res.z_score for sid, res in self.current_residuals_by_id.items()
                if hasattr(res, "z_score")
            }
            change_durations = {
                sid: det.duration_hours for sid, det in self.current_changes.items()
                if hasattr(det, "duration_hours")
            }
            top_fault = decision_context.top_fault
            fault_prob = decision_context.top_fault_probability

            self.current_rul = self.rul_service.estimate(
                fault_type=top_fault,
                change_scores=change_scores,
                residual_z_scores=residual_z,
                change_durations_hours=change_durations,
                fault_probability=fault_prob,
                regime=self.current_regime,
                timestamp=timestamp,
            )
        except Exception as exc:
            logger.debug(f"RUL estimation skipped: {exc}")
            self.current_rul = None

        # 9c. Composite Health Index
        try:
            rul_hours = self.current_rul.rul_hours if self.current_rul else float("inf")
            deg_index = self.current_rul.degradation_index if self.current_rul else 0.0
            self.current_health = self.health_index_service.compute(
                min_sensor_trust=decision_context.min_sensor_trust,
                max_change_score=decision_context.max_change_score,
                max_change_duration_hours=decision_context.max_persistence_hours,
                n_changes=decision_context.n_sensors_with_change,
                top_fault_probability=decision_context.top_fault_probability,
                rul_hours=rul_hours,
                degradation_index=deg_index,
                regime=self.current_regime,
                timestamp=timestamp,
            )
        except Exception as exc:
            logger.debug(f"Health index computation skipped: {exc}")
            self.current_health = None

        # 10. Index digital twin snapshot into RAG (throttled)
        try:
            should_index = False
            if self.last_rag_index_at is None:
                should_index = True
            else:
                elapsed = (timestamp - self.last_rag_index_at).total_seconds()
                should_index = elapsed >= 600  # at most every 10 minutes
            if alert and alert.alert_type == AlertType.ACTIONABLE:
                should_index = True
            if should_index:
                self._index_digital_twin_snapshot(timestamp)
                self.last_rag_index_at = timestamp
        except Exception as exc:
            logger.debug(f"RAG digital twin index skipped: {exc}")

        # 11. Build kernel decision artifact for downstream orchestrators
        self.last_decision_artifact = self._build_decision_artifact(
            decision_context,
            alert,
            telemetry,
            timestamp,
        )

        # 12. Bridge actionable alerts into the autopilot incident pipeline
        if alert and alert.alert_type in (AlertType.ACTIONABLE, AlertType.SENSOR_INTEGRITY):
            try:
                self.alert_bridge.process_alert(
                    alert,
                    site_id=self.site_id,
                    telemetry_snapshot=telemetry,
                )
            except Exception as exc:
                logger.debug(f"Alert→incident bridge skipped: {exc}")

        # 13. Publish pipeline events to event bus for downstream consumers
        self._publish_pipeline_events(alert, timestamp)
        
        return alert

    def process_telemetry_with_artifact(
        self, telemetry: Dict[str, Any]
    ) -> Tuple[PDMAlert, KernelDecisionArtifact]:
        """Process telemetry and return both alert and deterministic kernel artifact."""
        alert = self.process_telemetry(telemetry)
        artifact = self.last_decision_artifact
        if artifact is None:
            timestamp = telemetry.get("timestamp", datetime.utcnow())
            decision_context = self._build_decision_context(telemetry, timestamp)
            artifact = self._build_decision_artifact(
                decision_context,
                alert,
                telemetry,
                timestamp,
            )
            self.last_decision_artifact = artifact
        return alert, artifact

    def ingest_context(self,
                       weather: Optional[Dict[str, Any]] = None,
                       occupancy: Optional[Dict[str, Any]] = None,
                       tariff: Optional[Dict[str, Any]] = None):
        """Ingest external context data (weather/occupancy/tariff)."""
        now = datetime.utcnow()
        if weather:
            self.context_service.ingest_weather(
                asset_id=self.asset_id,
                timestamp=weather.get("timestamp", now),
                ambient_temp=weather.get("ambient_temp"),
                ambient_humidity=weather.get("ambient_humidity"),
                ambient_pressure=weather.get("ambient_pressure"),
            )
        if occupancy:
            self.context_service.ingest_occupancy(
                asset_id=self.asset_id,
                timestamp=occupancy.get("timestamp", now),
                occupancy_fraction=occupancy.get("occupancy_fraction", 0.0),
            )
        if tariff:
            self.context_service.ingest_tariff(
                asset_id=self.asset_id,
                timestamp=tariff.get("timestamp", now),
                energy_price=tariff.get("energy_price", 0.0),
            )
    
    def _publish_pipeline_events(self, alert: Optional[PDMAlert], timestamp: datetime):
        """Publish key pipeline events to the event bus for downstream consumers."""
        try:
            if self._event_bus is None:
                from ..core.service_registry import get_registry
                try:
                    self._event_bus = get_registry().get("event_bus")
                except Exception:
                    self._event_bus = InMemoryEventBus()

            from ..integration.event_bus import PdMEventType, PdMEvent
            import uuid as _uuid

            self._event_bus.publish(PdMEvent(
                event_id=str(_uuid.uuid4()),
                event_type=PdMEventType.ANALYSIS_COMPLETE,
                source_agent="kernel",
                timestamp=timestamp,
                asset_id=self.asset_id,
                site_id=self.site_id,
                payload={
                    "regime": self.current_regime.value if hasattr(self.current_regime, "value") else str(self.current_regime),
                    "n_sensors": len(self.current_trust_scores),
                    "n_changes": sum(1 for d in self.current_changes.values() if getattr(d, "change_detected", False)),
                    "health_score": self.current_health.health_score if self.current_health else None,
                    "rul_hours": self.current_rul.rul_hours if self.current_rul else None,
                    "alert_type": alert.alert_type.value if alert and hasattr(alert.alert_type, "value") else None,
                },
            ))

            # Publish alert event if actionable
            if alert and alert.alert_type == AlertType.ACTIONABLE:
                # Compute expected-value score from cost estimate and confidence
                _cost = float(getattr(alert, "estimated_cost_if_ignored", 0.0) or 0.0)
                _conf = float(getattr(alert, "confidence", 0.0) or 0.0)
                _ev_score = _cost * _conf

                self._event_bus.publish(self._event_factory.alert_created(
                    alert_id=getattr(alert, "alert_id", str(_uuid.uuid4())[:12]),
                    asset_id=self.asset_id,
                    site_id=self.site_id or "",
                    alert_type=alert.alert_type.value if hasattr(alert.alert_type, "value") else str(alert.alert_type),
                    severity=getattr(alert, "severity", "medium"),
                    confidence=_conf,
                    ev_score=_ev_score,
                    contributing_metrics=[],
                ))
        except Exception as exc:
            logger.debug(f"Event bus publish skipped: {exc}")

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
            ambient_temp=self.last_context.get("ambient_temp") if self.last_context else telemetry.get("ambient_temp"),
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
            "ambient_humidity": SensorType.AMBIENT_HUMIDITY,
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
        context = self.context_service.build_context(self.asset_id, telemetry, snapshot.timestamp)
        
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

    def _predict_behavior(self,
                          reading: SensorReading,
                          context: Dict[str, float],
                          timestamp: datetime) -> BehaviorPrediction:
        """Blend behavior model and fingerprint predictions."""
        base_pred = self.behavior_model.predict(
            reading.sensor_type,
            self.current_regime,
            context,
            timestamp,
        )
        fp_pred, fp_std = self.fingerprint_service.predict_hierarchical(
            reading.sensor_type,
            self.current_regime,
            context,
        )
        if np.isnan(base_pred.predicted_value):
            return BehaviorPrediction(
                timestamp=timestamp,
                sensor_type=reading.sensor_type,
                predicted_value=fp_pred,
                prediction_std=fp_std,
                regime=self.current_regime,
                load_proxy=context.get("load_proxy"),
                model_confidence=self.fingerprint_service.local_adaptation.adaptation_confidence,
            )
        # Weight blending based on fingerprint readiness
        fp_ready = self.fingerprint_service.is_fingerprint_ready()
        w_fp = 0.6 if fp_ready else 0.3
        w_model = 1.0 - w_fp
        combined = w_model * base_pred.predicted_value + w_fp * fp_pred
        combined_std = np.sqrt((w_model * base_pred.prediction_std) ** 2 + (w_fp * fp_std) ** 2)
        confidence = max(base_pred.model_confidence, self.fingerprint_service.local_adaptation.adaptation_confidence)
        return BehaviorPrediction(
            timestamp=timestamp,
            sensor_type=reading.sensor_type,
            predicted_value=combined,
            prediction_std=combined_std,
            regime=self.current_regime,
            load_proxy=context.get("load_proxy"),
            model_confidence=confidence,
        )
    
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
        if self.joint_change:
            any_change = any_change or self.joint_change.change_detected
            max_change_score = max(max_change_score, self.joint_change.change_score)
            max_persistence = max(max_persistence, self.joint_change.anomaly_duration_hours)
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
            load_proxy=self.last_context.get("load_proxy"),
            joint_change=self.joint_change,
        )
    
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
            "joint_change": {
                "change_detected": self.joint_change.change_detected,
                "score": self.joint_change.change_score,
                "n_sensors": self.joint_change.n_sensors,
                "n_trusted_sensors": self.joint_change.n_trusted_sensors,
                "duration_hours": self.joint_change.anomaly_duration_hours,
            } if self.joint_change else None,
            "current_hypothesis": self.fault_hypothesis.get_hypothesis_summary(),
            "current_alert": self.current_alert.to_operator_dict() if self.current_alert else None,
            "fingerprint_ready": self.fingerprint_service.is_fingerprint_ready(),
            "policy_summary": self.decision_policy.get_policy_summary(),
            "regime_validation": self.regime_service.get_validation_metrics(),
        }

    def _index_digital_twin_snapshot(self, timestamp: datetime):
        status = self.get_system_status()
        summary = {
            "timestamp": timestamp.isoformat(),
            "asset_id": self.asset_id,
            "current_regime": status.get("current_regime"),
            "is_steady_state": status.get("is_steady_state"),
            "active_changes": status.get("active_changes"),
            "joint_change": status.get("joint_change"),
            "current_hypothesis": status.get("current_hypothesis"),
            "current_alert": status.get("current_alert"),
            "fingerprint_ready": status.get("fingerprint_ready"),
        }
        rag = get_rag_service(self.session_factory)
        content = rag.format_document("digital_twin", summary)
        rag.index_document(
            doc_type="digital_twin",
            content=content,
            asset_id=self.asset_id,
            site_id=self.site_id,
            metadata={"source": "advanced_system"},
        )

    def _build_decision_artifact(
        self,
        decision_context: DecisionContext,
        alert: PDMAlert,
        telemetry: Dict[str, Any],
        timestamp: datetime,
    ) -> KernelDecisionArtifact:
        """Build deterministic kernel artifact for agent orchestration."""
        change_scores = {
            sensor_id: detection.change_score
            for sensor_id, detection in self.current_changes.items()
        }
        change_detected = {
            sensor_id: detection.change_detected
            for sensor_id, detection in self.current_changes.items()
        }
        change_duration_hours = {
            sensor_id: detection.anomaly_duration_hours
            for sensor_id, detection in self.current_changes.items()
        }
        trust_scores = {
            sensor_id: trust.trust_score
            for sensor_id, trust in self.current_trust_scores.items()
        }

        hypothesis = decision_context.hypothesis
        beliefs: Dict[str, float] = {}
        if hypothesis:
            beliefs = {
                fault.value if hasattr(fault, "value") else str(fault): prob
                for fault, prob in hypothesis.posteriors.items()
            }
        hypothesis_snapshot = HypothesisSnapshot(
            top_fault=decision_context.top_fault,
            top_probability=decision_context.top_fault_probability,
            is_concentrated=decision_context.is_diagnosis_concentrated,
            beliefs=beliefs,
        )

        return KernelDecisionArtifact(
            artifact_id=str(uuid.uuid4()),
            asset_id=self.asset_id,
            site_id=self.site_id,
            timestamp=timestamp,
            regime=self.current_regime,
            is_steady_state=decision_context.is_steady_state,
            trust_scores=trust_scores,
            untrusted_sensors=list(decision_context.untrusted_sensors),
            change_scores=change_scores,
            change_detected=change_detected,
            change_duration_hours=change_duration_hours,
            joint_change_detected=self.joint_change.change_detected if self.joint_change else False,
            joint_change_score=self.joint_change.change_score if self.joint_change else 0.0,
            hypothesis=hypothesis_snapshot,
            base_alert_type=alert.alert_type,
            base_alert_confidence=alert.confidence,
            base_false_alarm_probability=alert.false_alarm_probability,
            base_recommended_action=alert.recommended_action,
            gates=self.decision_policy.get_last_gate_evaluations(),
            context={
                "ambient_temp": decision_context.ambient_temp,
                "load_proxy": decision_context.load_proxy,
                "telemetry_timestamp": timestamp.isoformat(),
                "telemetry_sensor_count": len(
                    [k for k, v in telemetry.items() if isinstance(v, (int, float))]
                ),
            },
        )

    def export_decision_artifact(self) -> Optional[KernelDecisionArtifact]:
        """Return the most recent kernel artifact."""
        return self.last_decision_artifact

    def record_feedback(
        self,
        alert_id: str,
        outcome: FeedbackOutcome,
        confirmed_fault: Optional[FaultType] = None,
        notes: str = "",
    ):
        """Record technician feedback and propagate to all calibration paths.

        Updates:
        1. Decision policy calibration (FA probability curve + NIF rate).
        2. Ensemble calibration service (conformal prediction intervals).
        3. Gating thresholds via closed-loop governance adjustment.
        """
        # 1. Decision policy calibration (existing path)
        self.decision_policy.record_feedback(alert_id, outcome, confirmed_fault, notes)

        # 2. Ensemble calibration — feed ground truth so conformal intervals
        #    tighten over time.  Map feedback outcome to a numeric actual_value
        #    in [0, 1] suitable for the binary calibration model.
        try:
            calibrator = self._get_ensemble_calibration()
            actual_value = 1.0 if outcome == FeedbackOutcome.CONFIRMED_FAULT else 0.0

            # Re-derive model predictions from the alert's context snapshot
            alert_obj = None
            for a in self.decision_policy.alert_history:
                if a.alert_id == alert_id:
                    alert_obj = a
                    break

            if alert_obj is not None:
                model_predictions = {
                    "fault_probability": float(np.clip(alert_obj.confidence, 0.0, 1.0)),
                    "sensor_trust": 1.0,  # approximate — exact value was transient
                    "joint_change": 0.5,
                    "rul_signal": 0.5,
                }
                model_intervals = {
                    k: (max(0.0, v - 0.1), min(1.0, v + 0.1))
                    for k, v in model_predictions.items()
                }
                calibrator.update(model_predictions, actual_value, model_intervals)
        except Exception as exc:
            logger.debug(f"Ensemble calibration feedback skipped: {exc}")

        # 3. Closed-loop governance: adjust gating thresholds based on
        #    accumulated feedback.  If confirmed-fault rate is high, we can
        #    afford to be slightly more aggressive (lower confidence threshold).
        #    If NIF rate is high, tighten the gates.
        try:
            dataset = self.decision_policy.calibration_dataset
            if len(dataset.records) >= 20:
                recent = dataset.records[-min(100, len(dataset.records)):]
                n_confirmed = sum(
                    1 for r in recent if r.outcome == FeedbackOutcome.CONFIRMED_FAULT
                )
                n_nif = sum(
                    1 for r in recent if r.outcome == FeedbackOutcome.NO_ISSUE_FOUND
                )
                n_total = n_confirmed + n_nif
                if n_total >= 10:
                    nif_rate = n_nif / n_total
                    budget = self.decision_policy.budget
                    # Tighten confidence threshold when NIF rate is high
                    if nif_rate > budget.max_no_issue_found_rate:
                        delta = min(0.02, (nif_rate - budget.max_no_issue_found_rate) * 0.1)
                        budget.min_confidence_for_actionable = min(
                            0.98, budget.min_confidence_for_actionable + delta
                        )
                        logger.info(
                            "Closed-loop governance: tightened min_confidence to %.2f "
                            "(NIF rate %.1f%% > budget %.1f%%)",
                            budget.min_confidence_for_actionable,
                            nif_rate * 100,
                            budget.max_no_issue_found_rate * 100,
                        )
                    # Relax slightly when NIF rate is well under budget
                    elif nif_rate < budget.max_no_issue_found_rate * 0.5 and n_confirmed >= 5:
                        delta = min(0.01, (budget.max_no_issue_found_rate - nif_rate) * 0.05)
                        budget.min_confidence_for_actionable = max(
                            0.70, budget.min_confidence_for_actionable - delta
                        )
        except Exception as exc:
            logger.debug(f"Closed-loop governance adjustment skipped: {exc}")

        # 4. Trigger periodic FA-curve recalibration
        if len(self.decision_policy.calibration_dataset.records) % 50 == 0:
            self.decision_policy.recalibrate()

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
        
        # RUL estimate
        if self.current_rul:
            dashboard["rul"] = self.current_rul.to_dict()
        
        # Health index
        if self.current_health:
            dashboard["health"] = self.current_health.to_dict()
        
        return dashboard

    # ── Phase 3-4 Advanced Services Integration ─────────────────────

    def _get_explainability_service(self):
        """Lazy-load explainability service"""
        if self._explainability_service is None:
            from ..services.explainability_service import ExplainabilityService
            self._explainability_service = ExplainabilityService(
                feature_baselines={
                    "suction_pressure": 70,
                    "discharge_pressure": 250,
                    "superheat": 10,
                    "subcooling": 12,
                    "compressor_current": 15,
                },
            )
        return self._explainability_service

    def _get_ensemble_calibration(self):
        """Lazy-load ensemble calibration service"""
        if self._ensemble_calibration is None:
            from ..services.ensemble_calibration_service import EnsembleCalibrationService
            self._ensemble_calibration = EnsembleCalibrationService(
                model_ids=["fault_probability", "sensor_trust", "joint_change", "rul_signal"],
                coverage_level=0.90,
            )
        return self._ensemble_calibration

    def _apply_ensemble_uncertainty(
        self,
        alert: Optional[PDMAlert],
        decision_context: DecisionContext,
    ) -> None:
        """Apply ensemble uncertainty calibration to alert confidence/FA post-gating."""
        if alert is None:
            return
        try:
            calibrator = self._get_ensemble_calibration()

            joint_score_raw = 0.0
            if self.joint_change is not None:
                joint_score_raw = float(getattr(self.joint_change, "joint_score", 0.0))
            elif hasattr(decision_context, "max_change_score"):
                joint_score_raw = float(decision_context.max_change_score)

            rul_signal = 0.0
            if self.current_rul is not None:
                rul_hours = float(getattr(self.current_rul, "rul_hours", 0.0) or 0.0)
                if rul_hours > 0 and np.isfinite(rul_hours):
                    # Map larger RUL to lower near-term risk signal.
                    rul_signal = 1.0 / (1.0 + (rul_hours / 24.0))

            model_predictions = {
                "fault_probability": float(np.clip(decision_context.top_fault_probability, 0.0, 1.0)),
                "sensor_trust": float(np.clip(decision_context.min_sensor_trust, 0.0, 1.0)),
                "joint_change": float(np.clip(joint_score_raw, 0.0, 1.0)),
                "rul_signal": float(np.clip(rul_signal, 0.0, 1.0)),
            }
            model_intervals = {
                key: (max(0.0, value - 0.1), min(1.0, value + 0.1))
                for key, value in model_predictions.items()
            }

            prediction_set = calibrator.predict(model_predictions, model_intervals)
            calibrated_conf = float(
                np.clip(
                    calibrator.calibrate_probability(model_predictions["fault_probability"]),
                    0.0,
                    1.0,
                )
            )

            alert.confidence = float(np.clip((float(alert.confidence) + calibrated_conf) / 2.0, 0.0, 1.0))
            interval_width = max(0.0, float(prediction_set.upper_bound - prediction_set.lower_bound))
            uncertainty_penalty = min(0.2, interval_width * 0.1)
            baseline_fa = max(float(alert.false_alarm_probability), 1.0 - alert.confidence)
            alert.false_alarm_probability = float(np.clip(baseline_fa + uncertainty_penalty, 0.0, 1.0))

            if self.last_context is not None:
                self.last_context["ensemble_point_estimate"] = float(prediction_set.point_estimate)
                self.last_context["ensemble_interval_lower"] = float(prediction_set.lower_bound)
                self.last_context["ensemble_interval_upper"] = float(prediction_set.upper_bound)
        except Exception as exc:  # pragma: no cover
            logger.debug(f"Ensemble uncertainty calibration skipped: {exc}")

    def _get_adaptive_weights(self):
        """Lazy-load adaptive agent weights service"""
        if self._adaptive_weights is None:
            from ..services.adaptive_agent_weights import AdaptiveAgentWeights
            self._adaptive_weights = AdaptiveAgentWeights(
                agent_roles=[
                    "regime_detector", "sensor_trust", "behavior_modeler",
                    "change_detector", "fault_hypothesis", "decision_policy",
                ],
            )
        return self._adaptive_weights

    def _get_fleet_correlation(self):
        """Lazy-load fleet correlation service"""
        if self._fleet_correlation is None:
            from ..services.fleet_correlation_service import FleetCorrelationService
            self._fleet_correlation = FleetCorrelationService()
        return self._fleet_correlation

    def _get_tft_predictor(self):
        """Lazy-load TFT predictor"""
        if self._tft_predictor is None:
            from ..models.temporal_fusion_transformer import TFTRULPredictor
            self._tft_predictor = TFTRULPredictor()
        return self._tft_predictor

    def _get_physics_constraints(self):
        """Lazy-load physics constraints"""
        if self._physics_constraints is None:
            from ..models.physics_informed_constraints import PhysicsInformedLoss
            self._physics_constraints = PhysicsInformedLoss()
        return self._physics_constraints

    def explain_current_alert(self) -> Dict[str, Any]:
        """
        Generate SHAP-based explanation for the current alert.
        
        Returns comprehensive explanation including:
        - Feature contributions
        - Counterfactual explanations
        - Similar historical cases
        - Recommended investigation steps
        """
        if not self.current_alert:
            return {"status": "no_alert", "message": "No current alert to explain"}
        
        service = self._get_explainability_service()
        
        # Build features from current state
        features = dict(self.last_context)
        
        # Get fault belief from hypothesis
        hypothesis = self.fault_hypothesis.current_hypothesis
        fault_belief = {}
        if hypothesis:
            fault_belief = {
                str(f.value) if hasattr(f, 'value') else str(f): p
                for f, p in hypothesis.posteriors.items()
            }
        
        # Get gate evaluations
        gate_evals = self.decision_policy.get_last_gate_evaluations()
        
        explanation = service.explain_fault_hypothesis(
            asset_id=self.asset_id,
            features=features,
            fault_belief=fault_belief,
            predicted_fault=str(self.current_alert.primary_fault.value) if self.current_alert.primary_fault else "unknown",
            confidence=self.current_alert.confidence,
            false_alarm_probability=self.current_alert.false_alarm_probability,
            gate_evaluations=gate_evals,
        )
        
        return explanation.to_dict()

    def get_fleet_voting_context(self) -> Dict[str, Any]:
        """Get fleet correlation context for agent voting decisions"""
        service = self._get_fleet_correlation()
        return service.get_voting_context(self.asset_id)

    def get_calibrated_rul_prediction(self, temporal_features: list) -> Dict[str, Any]:
        """
        Get TFT-based RUL prediction with uncertainty quantification.
        
        Args:
            temporal_features: List of recent telemetry snapshots
            
        Returns:
            RUL prediction with confidence intervals
        """
        predictor = self._get_tft_predictor()
        
        static_features = {
            "asset_age": self.hours_of_operation,
            "asset_type": 1,
            "site_id": hash(self.site_id or "default") % 1000,
            "model_variant": 1,
            "install_year": 2020,
        }
        
        result = predictor.predict(static_features, temporal_features)
        
        return {
            "rul_hours": result.rul_hours,
            "rul_lower": result.rul_lower,
            "rul_upper": result.rul_upper,
            "degradation_rate": result.degradation_rate,
            "point_forecast": result.point_forecast.tolist() if len(result.point_forecast) > 0 else [],
        }

    def check_physics_constraints(self, telemetry: Dict[str, float]) -> Dict[str, Any]:
        """
        Check physics constraints for given telemetry.
        
        Returns penalty score and list of violations.
        """
        physics = self._get_physics_constraints()
        penalty, violations = physics.compute_penalty(telemetry)
        
        return {
            "total_penalty": penalty,
            "n_violations": len(violations),
            "violations": [
                {"name": v.constraint_name, "residual": v.residual, "penalty": v.penalty}
                for v in violations
            ],
        }


def create_pdm_system(asset_id: str,
                      max_alarms_per_month: float = 0.3,
                      max_fa_rate: float = 0.05,
                      site_id: Optional[str] = None,
                      session_factory: Optional[Any] = None) -> HVACRPdMAdvancedSystem:
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
    
    return HVACRPdMAdvancedSystem(asset_id, config, site_id=site_id, session_factory=session_factory)
