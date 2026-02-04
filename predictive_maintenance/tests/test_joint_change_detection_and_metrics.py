from datetime import datetime, timedelta

import pytest

from predictive_maintenance.core.schemas import (
    AlertType,
    FeedbackOutcome,
    OperatingRegime,
    PDMAlert,
    ResidualObservation,
    SensorType,
)
from predictive_maintenance.services.change_detection_service import (
    ChangeDetectorConfig,
    SequentialChangeDetectionService,
)
from predictive_maintenance.services.decision_policy_service import DecisionPolicyService


def _make_obs(sensor_id: str, sensor_type: SensorType, ts: datetime) -> ResidualObservation:
    return ResidualObservation(
        timestamp=ts,
        sensor_id=sensor_id,
        sensor_type=sensor_type,
        regime=OperatingRegime.STEADY_COOL,
        observed=1.0,
        predicted=0.0,
        residual=1.0,
        z_score=3.0,
        log_likelihood=5.0,
    )


def test_joint_change_detection_triggers():
    cfg = ChangeDetectorConfig(
        joint_enabled=True,
        joint_cusum_threshold=4.0,
        joint_glr_threshold=1000.0,
        joint_min_trusted_sensors=2,
        joint_min_persistence_minutes=0.0,
    )
    detector = SequentialChangeDetectionService("asset_1", cfg)
    ts = datetime.utcnow()

    observations = {
        "s1": _make_obs("s1", SensorType.SUCTION_PRESSURE, ts),
        "s2": _make_obs("s2", SensorType.DISCHARGE_PRESSURE, ts),
    }
    trusts = {"s1": 1.0, "s2": 1.0}

    joint = detector.process_joint_observations(
        observations,
        OperatingRegime.STEADY_COOL,
        trusts,
    )

    assert joint.change_detected is True
    assert joint.n_trusted_sensors == 2
    assert joint.change_score > 0


def test_precision_at_k_metrics():
    service = DecisionPolicyService("asset_1")
    now = datetime.utcnow()

    alerts = [
        PDMAlert(
            asset_id="asset_1",
            alert_type=AlertType.ACTIONABLE,
            confidence=0.9,
            false_alarm_probability=0.1,
            feedback_outcome=FeedbackOutcome.CONFIRMED_FAULT,
            created_at=now - timedelta(days=2),
            feedback_at=now - timedelta(days=1),
        ),
        PDMAlert(
            asset_id="asset_1",
            alert_type=AlertType.ACTIONABLE,
            confidence=0.8,
            false_alarm_probability=0.2,
            feedback_outcome=FeedbackOutcome.NO_ISSUE_FOUND,
            created_at=now - timedelta(days=2),
            feedback_at=now - timedelta(days=1),
        ),
        PDMAlert(
            asset_id="asset_1",
            alert_type=AlertType.ACTIONABLE,
            confidence=0.7,
            false_alarm_probability=0.3,
            feedback_outcome=FeedbackOutcome.CONFIRMED_FAULT,
            created_at=now - timedelta(days=2),
            feedback_at=now - timedelta(days=1),
        ),
    ]
    service.alert_history = alerts

    metrics = service.get_deployment_metrics(
        period_start=now - timedelta(days=7),
        period_end=now,
        n_units=1,
    )

    assert metrics.precision_at_k[1] == 1.0
    assert metrics.precision_at_k[3] == pytest.approx(2 / 3)
