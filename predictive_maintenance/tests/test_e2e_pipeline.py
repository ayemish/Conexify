import sys
import pathlib
from datetime import datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from predictive_maintenance.core.schemas import (
    AlertType,
    FalsePositiveBudget,
    FeedbackOutcome,
)
from predictive_maintenance.integration.advanced_system import HVACRPdMAdvancedSystem, PDMSystemConfig
from predictive_maintenance.services.change_detection_service import ChangeDetectorConfig
from predictive_maintenance.services.decision_policy_service import DecisionPolicyService
from predictive_maintenance.core.schemas import PDMAlert


def _make_budget(**overrides) -> FalsePositiveBudget:
    budget = FalsePositiveBudget()
    for key, value in overrides.items():
        setattr(budget, key, value)
    return budget


def _make_system(budget: FalsePositiveBudget, change_cfg: ChangeDetectorConfig) -> HVACRPdMAdvancedSystem:
    config = PDMSystemConfig(
        false_positive_budget=budget,
        change_detection_config=change_cfg,
    )
    return HVACRPdMAdvancedSystem("asset_1", config)


def _telemetry_sample(
    ts: datetime,
    suction_pressure: float = 70.0,
    suction_line_temp: float = 55.0,
    discharge_pressure: float = 280.0,
    compressor_on: bool = True,
    heating: bool = False,
    out_of_range: bool = False,
) -> dict:
    if out_of_range:
        suction_pressure = -10.0

    return {
        "timestamp": ts,
        "compressor_on": compressor_on,
        "compressor_current": 12.0,
        "compressor_power": 5.0,
        "evap_fan_on": compressor_on,
        "condenser_fan_on": compressor_on,
        "supply_fan_speed": 50.0 if compressor_on else 0.0,
        "suction_line_temp": suction_line_temp,
        "discharge_temp": 110.0,
        "supply_air_temp": 55.0,
        "return_air_temp": 75.0,
        "ambient_temp": 85.0,
        "suction_pressure": suction_pressure,
        "discharge_pressure": discharge_pressure,
        "heating_valve_pct": 60.0 if heating else 0.0,
        "reversing_valve_heat": True if heating else False,
    }


def _run_phases(system: HVACRPdMAdvancedSystem, start: datetime, step_min: int, phases: list) -> PDMAlert:
    ts = start
    last_alert = None
    for count, kwargs in phases:
        for _ in range(count):
            telemetry = _telemetry_sample(ts, **kwargs)
            last_alert = system.process_telemetry(telemetry)
            ts += timedelta(minutes=step_min)
    return last_alert


def test_e2e_happy_path_actionable_alert():
    # Relax thresholds to make the happy path actionable with synthetic data
    budget = _make_budget(
        min_confidence_for_actionable=0.6,
        max_false_alarm_probability=0.2,
        min_anomaly_persistence_hours=0.5,
        min_regime_coverage_cycles=1,
        max_actionable_alarms_per_unit_per_month=10.0,
    )
    change_cfg = ChangeDetectorConfig(
        cusum_threshold=1.5,
        cusum_slack=0.1,
        glr_threshold=2.0,
        min_persistence_minutes=30.0,
        min_steady_state_regimes=1,
        stability_window=10,
    )
    system = _make_system(budget, change_cfg)

    phases = [
        (12, {"suction_pressure": 70.0, "suction_line_temp": 55.0, "heating": False}),
        (20, {"suction_pressure": 67.0, "suction_line_temp": 58.0, "heating": False}),
    ]

    alert = _run_phases(system, datetime.utcnow(), 5, phases)

    assert alert.alert_type == AlertType.ACTIONABLE
    assert any(d.change_detected for d in system.current_changes.values())
    assert system.fault_hypothesis.current_hypothesis is not None


def test_e2e_sensor_fault_path():
    budget = _make_budget()
    change_cfg = ChangeDetectorConfig()
    system = _make_system(budget, change_cfg)

    phases = [
        (35, {"suction_pressure": -10.0, "out_of_range": True, "heating": False}),
    ]

    alert = _run_phases(system, datetime.utcnow(), 5, phases)

    assert alert.alert_type == AlertType.SENSOR_INTEGRITY


def test_e2e_transient_regime_suppression():
    budget = _make_budget()
    change_cfg = ChangeDetectorConfig()
    system = _make_system(budget, change_cfg)

    ts = datetime.utcnow()
    last_alert = None
    for i in range(20):
        compressor_on = (i % 2 == 0)
        telemetry = _telemetry_sample(
            ts,
            suction_pressure=70.0,
            suction_line_temp=55.0,
            compressor_on=compressor_on,
            heating=False,
        )
        last_alert = system.process_telemetry(telemetry)
        ts += timedelta(minutes=5)

    assert last_alert.alert_type != AlertType.ACTIONABLE


def test_e2e_false_positive_budget_enforcement():
    budget = _make_budget(
        min_confidence_for_actionable=0.6,
        max_false_alarm_probability=0.2,
        min_anomaly_persistence_hours=0.5,
        min_regime_coverage_cycles=1,
        max_actionable_alarms_per_unit_per_month=1.0,
    )
    change_cfg = ChangeDetectorConfig(
        cusum_threshold=1.5,
        cusum_slack=0.1,
        glr_threshold=2.0,
        min_persistence_minutes=30.0,
        min_steady_state_regimes=1,
        stability_window=10,
    )
    system = _make_system(budget, change_cfg)

    phases = [
        (12, {"suction_pressure": 70.0, "suction_line_temp": 55.0, "heating": False}),
        (20, {"suction_pressure": 67.0, "suction_line_temp": 58.0, "heating": False}),
    ]
    first_alert = _run_phases(system, datetime.utcnow(), 5, phases)
    assert first_alert.alert_type == AlertType.ACTIONABLE

    # Continue anomaly; budget should suppress subsequent actionable alert
    followup = _run_phases(system, datetime.utcnow() + timedelta(hours=4), 5, [
        (10, {"suction_pressure": 67.0, "suction_line_temp": 58.0, "heating": False}),
    ])
    assert followup.alert_type != AlertType.ACTIONABLE


def test_e2e_calibration_feedback_loop():
    service = DecisionPolicyService("asset_1")
    initial = service.fa_calibration_curve.get(0.9)

    # Add a dummy alert so record_feedback can attach feedback
    alert = PDMAlert(asset_id="asset_1", alert_type=AlertType.ACTIONABLE, false_alarm_probability=0.9)
    service.alert_history.append(alert)

    for i in range(50):
        service.record_feedback(
            alert.alert_id,
            FeedbackOutcome.NO_ISSUE_FOUND,
            confirmed_fault=None,
            notes="false positive",
        )

    service.recalibrate()
    updated = service.fa_calibration_curve.get(0.9)

    assert updated is not None
    assert initial is None or updated >= initial
