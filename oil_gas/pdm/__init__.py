"""
PDM Advanced - Predictive Maintenance with Radar-Inspired Detection

A comprehensive HVAC/R predictive maintenance system implementing:

A) False Positive Budget (Neyman-Pearson)
   - Explicit operational constraints before modeling
   - "Given fixed false alarm rate, maximize early detection lead time"

B) Radar-Inspired Residual Modeling
   - System baseline (physics-informed / hybrid model)
   - Residual process with regime-conditional distribution
   - Autocorrelation, heavy tails, drift modeling
   - Sequential change detection (CUSUM/GLR), not point anomaly scoring

C) Regime Segmentation as First-Class Design
   - OFF, STARTUP, STEADY_COOL, STEADY_HEAT, ECONOMIZER, DEFROST, etc.
   - Separate behavior models per regime
   - Reduces FP by not comparing apples to oranges

D) Three-Layer Inference
   1. Sensor Trust: "Do I trust this sensor stream right now?"
   2. Behavioral Deviation: "Is the unit behaving abnormally given regime/context?"
   3. Fault Hypothesis: "If abnormal, what are the most plausible fault modes?"

E) Probabilistic Hypothesis Testing
   - Maintains belief state over fault types
   - Alarm when probability mass crosses threshold
   - Otherwise keep monitoring and gathering evidence

F) Calibrated Uncertainty
   - Every prediction outputs: confidence, expected FA rate, recommended action
   - Evaluation: alarms/month, precision@K, lead time distribution, savings

G) Equipment Fingerprints & Hierarchical Modeling
   - Global model: general HVAC physics
   - Per-unit adaptation: equipment fingerprint
   - Per-climate/building adjustment
   - Prevents "different install" from being flagged as "fault"

Usage:
    from .pdm import create_pdm_system, HVACRPdMAdvancedSystem
    
    system = create_pdm_system(
        asset_id="RTU-001",
        max_alarms_per_month=0.3,
        max_fa_rate=0.05
    )
    
    # Process telemetry
    alert = system.process_telemetry({
        "timestamp": datetime.utcnow(),
        "compressor_on": True,
        "suction_pressure": 72.5,
        "discharge_pressure": 285.0,
        "ambient_temp": 85.0,
        # ... other sensors
    })
    
    # Check alert type
    if alert.alert_type == AlertType.ACTIONABLE:
        print(f"Fault: {alert.primary_fault}")
        print(f"Confidence: {alert.confidence:.0%}")
        print(f"FA Probability: {alert.false_alarm_probability:.1%}")
        print(f"Action: {alert.recommended_action}")
    
    # Record feedback
    system.record_feedback(
        alert_id=alert.alert_id,
        outcome=FeedbackOutcome.CONFIRMED_FAULT,
        confirmed_fault=FaultType.REFRIGERANT_LEAK
    )
"""

# Core schemas
from ..pdm_schemas import (
    # Enums
    AlertSeverity,
    AlertType,
    FaultType,
    FeedbackOutcome,
    OperatingRegime,
    SensorType,
    # Data classes
    AlarmFeedback,
    CalibrationDataset,
    ChangePointDetection,
    DeploymentMetrics,
    EquipmentFingerprint,
    FalsePositiveBudget,
    FaultEvidence,
    FaultHypothesis,
    HierarchicalModelConfig,
    PDMAlert,
    RegimeSegment,
    RegimeState,
    ResidualDistribution,
    ResidualObservation,
    SensorTrustScore,
)

# Services
from ..pdm_regime_service import (
    RegimeSegmentationService,
    TelemetrySnapshot,
    RegimeConfig,
)

from ..pdm_sensor_trust_service import (
    SensorTrustService,
    SensorReading,
    SensorSpec,
)

from ..pdm_residual_service import (
    BehaviorModelService,
    BehaviorPrediction,
    ResidualErrorModelService,
)

from ..pdm_change_detection_service import (
    ChangeDetectorConfig,
    SequentialChangeDetectionService,
)

from ..pdm_fault_hypothesis_service import (
    FaultHypothesisService,
    SymptomExtraction,
)

from ..pdm_decision_policy_service import (
    DecisionContext,
    DecisionPolicyService,
)

from ..pdm_fingerprint_service import (
    EquipmentFingerprintService,
    GlobalModelParameters,
    LocalAdaptation,
)

# Integrated system
from ..pdm_advanced_system import (
    HVACRPdMAdvancedSystem,
    PDMSystemConfig,
    create_pdm_system,
)

__all__ = [
    # Enums
    "AlertSeverity",
    "AlertType",
    "FaultType",
    "FeedbackOutcome",
    "OperatingRegime",
    "SensorType",
    # Core data classes
    "AlarmFeedback",
    "CalibrationDataset",
    "ChangePointDetection",
    "DeploymentMetrics",
    "EquipmentFingerprint",
    "FalsePositiveBudget",
    "FaultEvidence",
    "FaultHypothesis",
    "HierarchicalModelConfig",
    "PDMAlert",
    "RegimeSegment",
    "RegimeState",
    "ResidualDistribution",
    "ResidualObservation",
    "SensorTrustScore",
    # Regime service
    "RegimeSegmentationService",
    "TelemetrySnapshot",
    "RegimeConfig",
    # Sensor trust service
    "SensorTrustService",
    "SensorReading",
    "SensorSpec",
    # Behavior/Residual service
    "BehaviorModelService",
    "BehaviorPrediction",
    "ResidualErrorModelService",
    # Change detection service
    "ChangeDetectorConfig",
    "SequentialChangeDetectionService",
    # Fault hypothesis service
    "FaultHypothesisService",
    "SymptomExtraction",
    # Decision policy service
    "DecisionContext",
    "DecisionPolicyService",
    # Fingerprint service
    "EquipmentFingerprintService",
    "GlobalModelParameters",
    "LocalAdaptation",
    # Integrated system
    "HVACRPdMAdvancedSystem",
    "PDMSystemConfig",
    "create_pdm_system",
]
