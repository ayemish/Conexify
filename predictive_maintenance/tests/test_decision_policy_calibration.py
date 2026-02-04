import sys
import pathlib
from datetime import datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from predictive_maintenance.core.schemas import (
    AlarmFeedback,
    AlertType,
    ChangePointDetection,
    FaultHypothesis,
    FaultType,
    FeedbackOutcome,
    OperatingRegime,
    SensorType,
    SensorTrustScore,
)
from predictive_maintenance.services.decision_policy_service import (
    DecisionContext,
    DecisionPolicyService,
)


def _build_context(change_detected: bool = True) -> DecisionContext:
    sensor_trust = SensorTrustScore(
        sensor_id="s1",
        sensor_type=SensorType.SUCTION_PRESSURE,
        asset_id="asset_1",
        trust_score=1.0,
    )

    change = ChangePointDetection(
        asset_id="asset_1",
        sensor_type=SensorType.SUCTION_PRESSURE,
        change_detected=change_detected,
        anomaly_duration_hours=6.0,
        n_regimes_observed=2,
        change_score=0.9,
    )

    hypothesis = FaultHypothesis(
        asset_id="asset_1",
        priors={FaultType.REFRIGERANT_LEAK: 0.1},
        posteriors={FaultType.REFRIGERANT_LEAK: 0.9},
        most_likely_fault=FaultType.REFRIGERANT_LEAK,
        second_likely_fault=None,
        probability_mass_top2=0.9,
        is_concentrated=True,
        updated_at=datetime.utcnow(),
    )

    return DecisionContext(
        timestamp=datetime.utcnow(),
        asset_id="asset_1",
        current_regime=OperatingRegime.STEADY_COOL,
        is_steady_state=True,
        sensor_trust_scores={"s1": sensor_trust},
        min_sensor_trust=1.0,
        untrusted_sensors=[],
        change_detections={"s1": change},
        any_change_detected=True,
        max_change_score=0.9,
        max_persistence_hours=6.0,
        n_sensors_with_change=1,
        hypothesis=hypothesis,
        top_fault=FaultType.REFRIGERANT_LEAK,
        top_fault_probability=0.9,
        is_diagnosis_concentrated=True,
        ambient_temp=85.0,
        load_proxy=0.6,
    )


def test_calibration_impacts_budget_gate():
    service = DecisionPolicyService("asset_1")
    context = _build_context()

    # Before recalibration, default calibration makes FA prob at 0.9 too high
    alert = service.evaluate(context)
    assert alert.alert_type == AlertType.WATCH

    # Add feedback indicating alerts at 0.9 confidence are true positives
    for i in range(50):
        service.calibration_dataset.records.append(
            AlarmFeedback(
                alert_id=f"a{i}",
                asset_id="asset_1",
                outcome=FeedbackOutcome.CONFIRMED_FAULT,
                confirmed_fault_type=FaultType.REFRIGERANT_LEAK,
                feedback_notes="ok",
                alarm_time=datetime.utcnow() - timedelta(days=1),
                feedback_time=datetime.utcnow(),
                predicted_fault_distribution={FaultType.REFRIGERANT_LEAK: 0.9},
                predicted_false_alarm_prob=0.9,
            )
        )

    service.recalibrate()
    alert_after = service.evaluate(context)

    assert alert_after.alert_type == AlertType.ACTIONABLE
