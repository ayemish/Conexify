"""
Property-Based Test Suite for Sequential Change Detection

Uses hypothesis-style property testing to verify invariants of the
CUSUM, GLR, and joint change detection algorithms:

1. CUSUM monotonicity — S_t >= 0 always
2. No alarm on white noise — false positive rate bounded
3. Guaranteed alarm on persistent shift — false negative rate bounded
4. Persistence gating — no alarm before min_persistence
5. Transient regime immunity — alarms suppressed during transients
6. Stability score range — always in [0, 1]
7. Joint detection coherence — joint alarm requires per-sensor evidence
8. Reset idempotence — reset clears all state cleanly
"""

import math
import random
import sys
import os
from datetime import datetime, timedelta
from typing import List

import numpy as np
import pytest

# Ensure project root on path
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), ".."),
)

from predictive_maintenance.core.schemas import (
    ChangePointDetection,
    JointChangeDetection,
    OperatingRegime,
    ResidualObservation,
    SensorType,
)
from predictive_maintenance.services.change_detection_service import (
    ChangeDetectorConfig,
    CUSUMState,
    GLRState,
    SequentialChangeDetectionService,
)


# ── Helpers ──────────────────────────────────────────────────────────

def _make_obs(
    sensor_id: str = "temp_1",
    sensor_type: SensorType = SensorType.SUPPLY_AIR_TEMP,
    regime: OperatingRegime = OperatingRegime.STEADY_COOL,
    z_score: float = 0.0,
    log_likelihood: float = -1.5,
    timestamp: datetime = None,
) -> ResidualObservation:
    ts = timestamp or datetime.utcnow()
    return ResidualObservation(
        timestamp=ts,
        sensor_id=sensor_id,
        sensor_type=sensor_type,
        regime=regime,
        observed=70.0 + z_score,
        predicted=70.0,
        residual=z_score,
        z_score=z_score,
        log_likelihood=log_likelihood,
    )


def _make_service(
    cusum_threshold: float = 5.0,
    glr_threshold: float = 10.0,
    min_persistence_minutes: float = 0.0,
    min_steady_state_regimes: int = 0,
    min_stability_for_alarm: float = 0.0,
) -> SequentialChangeDetectionService:
    cfg = ChangeDetectorConfig(
        cusum_threshold=cusum_threshold,
        glr_threshold=glr_threshold,
        min_persistence_minutes=min_persistence_minutes,
        min_steady_state_regimes=min_steady_state_regimes,
        min_stability_for_alarm=min_stability_for_alarm,
        stability_window=10,
    )
    return SequentialChangeDetectionService("test_asset", cfg)


# ── Property 1: CUSUM non-negativity ────────────────────────────────

class TestCUSUMProperties:
    """CUSUM accumulator invariants."""

    @pytest.mark.parametrize("seed", range(10))
    def test_cusum_always_non_negative(self, seed):
        """S_pos and S_neg must never go below zero."""
        rng = np.random.default_rng(seed)
        svc = _make_service()
        sensor_id = "s1"

        for i in range(500):
            z = float(rng.standard_t(df=4))
            obs = _make_obs(
                sensor_id=sensor_id,
                z_score=z,
                log_likelihood=-0.5 * z ** 2,
                timestamp=datetime.utcnow() + timedelta(minutes=i),
            )
            svc.process_observation(obs, OperatingRegime.STEADY_COOL)

            state = svc.cusum_states[sensor_id]
            assert state.s_pos >= 0.0, f"s_pos negative at step {i}: {state.s_pos}"
            assert state.s_neg >= 0.0, f"s_neg negative at step {i}: {state.s_neg}"


# ── Property 2: No alarm on white noise ─────────────────────────────

class TestWhiteNoiseFalsePositive:
    """Under iid N(0,1) noise with persistence gating, FP rate should be low.

    The system's design philosophy is that persistence + regime gating
    suppresses point-anomaly false positives.  Without persistence, the
    raw CUSUM *will* cross its threshold on normal noise — that is
    expected and caught by the persistence filter.
    """

    @pytest.mark.parametrize("seed", range(5))
    def test_low_fp_with_persistence_gating(self, seed):
        """With 30-min persistence and 2-regime requirement, FP rate < 5%."""
        rng = np.random.default_rng(seed)
        svc = _make_service(
            cusum_threshold=5.0,
            glr_threshold=10.0,
            min_persistence_minutes=30.0,
            min_steady_state_regimes=2,
            min_stability_for_alarm=0.7,
        )
        sensor_id = "noise"
        n = 1000
        alarms = 0
        base = datetime(2025, 1, 1)

        for i in range(n):
            z = float(rng.normal(0, 1))
            obs = _make_obs(
                sensor_id=sensor_id,
                z_score=z,
                log_likelihood=-1.5 - 0.5 * z ** 2,
                timestamp=base + timedelta(minutes=i),
            )
            det = svc.process_observation(obs, OperatingRegime.STEADY_COOL)
            if det.change_detected:
                alarms += 1

        fp_rate = alarms / n
        assert fp_rate < 0.05, f"FP rate too high on white noise with persistence gating: {fp_rate:.2%}"


# ── Property 3: Guaranteed alarm on persistent shift ─────────────────

class TestPersistentShiftDetection:
    """A persistent mean shift must eventually trigger an alarm."""

    @pytest.mark.parametrize("shift", [2.0, 3.0, 5.0])
    def test_detects_persistent_shift(self, shift):
        """A shift of size `shift` σ should be detected within 200 samples."""
        svc = _make_service(
            cusum_threshold=5.0,
            min_persistence_minutes=0,
            min_steady_state_regimes=0,
            min_stability_for_alarm=0.0,
        )
        sensor_id = "shifted"
        rng = np.random.default_rng(42)
        base = datetime(2025, 1, 1)
        detected = False

        for i in range(200):
            z = float(rng.normal(shift, 1.0))
            obs = _make_obs(
                sensor_id=sensor_id,
                z_score=z,
                log_likelihood=-1.5 - 0.5 * z ** 2,
                timestamp=base + timedelta(minutes=i),
            )
            det = svc.process_observation(obs, OperatingRegime.STEADY_COOL)
            if det.change_detected:
                detected = True
                break

        assert detected, f"Failed to detect persistent shift of {shift}σ within 200 samples"


# ── Property 4: Persistence gating ──────────────────────────────────

class TestPersistenceGating:
    """Alarm should not fire before persistence window expires."""

    def test_no_alarm_before_persistence_window(self):
        """With 60 min persistence, alarm must not fire in first 59 min."""
        svc = _make_service(
            cusum_threshold=2.0,
            min_persistence_minutes=60.0,
            min_steady_state_regimes=0,
            min_stability_for_alarm=0.0,
        )
        sensor_id = "fast"
        base = datetime(2025, 1, 1)
        shift = 5.0

        for i in range(59):
            z = shift
            obs = _make_obs(
                sensor_id=sensor_id,
                z_score=z,
                log_likelihood=-1.5 - 0.5 * z ** 2,
                timestamp=base + timedelta(minutes=i),
            )
            det = svc.process_observation(obs, OperatingRegime.STEADY_COOL)
            assert not det.change_detected, (
                f"Alarm fired at minute {i}, before 60-min persistence window"
            )


# ── Property 5: Transient regime immunity ────────────────────────────

class TestTransientImmunity:
    """No alarm should fire during transient regimes."""

    @pytest.mark.parametrize("regime", [
        OperatingRegime.STARTUP,
        OperatingRegime.SHUTDOWN,
        OperatingRegime.TRANSIENT,
        OperatingRegime.RECOVERY,
        OperatingRegime.DEFROST,
    ])
    def test_no_alarm_during_transient(self, regime):
        svc = _make_service(
            cusum_threshold=2.0,
            min_persistence_minutes=0,
            min_steady_state_regimes=0,
            min_stability_for_alarm=0.0,
        )
        sensor_id = "transient_test"
        base = datetime(2025, 1, 1)
        shift = 10.0

        for i in range(100):
            obs = _make_obs(
                sensor_id=sensor_id,
                z_score=shift,
                log_likelihood=-1.5 - 0.5 * shift ** 2,
                timestamp=base + timedelta(minutes=i),
            )
            det = svc.process_observation(obs, regime)
            assert not det.change_detected, (
                f"Alarm fired during {regime.value} at step {i}"
            )


# ── Property 6: Stability score range ───────────────────────────────

class TestStabilityScoreRange:
    """Stability score must always be in [0, 1]."""

    @pytest.mark.parametrize("seed", range(5))
    def test_stability_bounded(self, seed):
        rng = np.random.default_rng(seed)
        svc = _make_service()
        sensor_id = "stab"
        base = datetime(2025, 1, 1)

        for i in range(300):
            z = float(rng.standard_t(df=3))
            obs = _make_obs(
                sensor_id=sensor_id,
                z_score=z,
                log_likelihood=-1.5 - 0.5 * z ** 2,
                timestamp=base + timedelta(minutes=i),
            )
            det = svc.process_observation(obs, OperatingRegime.STEADY_COOL)
            assert 0.0 <= det.stability_score <= 1.0, (
                f"Stability score out of range at step {i}: {det.stability_score}"
            )


# ── Property 7: Change score range ──────────────────────────────────

class TestChangeScoreRange:
    """Change score must always be in [0, 1]."""

    @pytest.mark.parametrize("seed", range(5))
    def test_change_score_bounded(self, seed):
        rng = np.random.default_rng(seed)
        svc = _make_service()
        sensor_id = "cs"
        base = datetime(2025, 1, 1)

        for i in range(300):
            z = float(rng.normal(0, 3))
            obs = _make_obs(
                sensor_id=sensor_id,
                z_score=z,
                log_likelihood=-1.5 - 0.5 * z ** 2,
                timestamp=base + timedelta(minutes=i),
            )
            det = svc.process_observation(obs, OperatingRegime.STEADY_COOL)
            assert 0.0 <= det.change_score <= 1.0, (
                f"Change score out of range at step {i}: {det.change_score}"
            )


# ── Property 8: Reset idempotence ───────────────────────────────────

class TestResetIdempotence:
    """Resetting a sensor should return it to initial state."""

    def test_reset_clears_state(self):
        svc = _make_service(cusum_threshold=2.0, min_persistence_minutes=0)
        sensor_id = "reset_test"
        base = datetime(2025, 1, 1)

        # Build up state
        for i in range(50):
            obs = _make_obs(
                sensor_id=sensor_id,
                z_score=5.0,
                log_likelihood=-14.0,
                timestamp=base + timedelta(minutes=i),
            )
            svc.process_observation(obs, OperatingRegime.STEADY_COOL)

        cusum_before = svc.cusum_states[sensor_id]
        assert cusum_before.s_pos > 0 or cusum_before.s_neg > 0

        svc.reset_sensor(sensor_id)

        cusum_after = svc.cusum_states[sensor_id]
        det_after = svc.detection_states[sensor_id]

        assert cusum_after.s_pos == 0.0
        assert cusum_after.s_neg == 0.0
        assert det_after.change_detected is False
        assert det_after.change_score == 0.0
        assert det_after.anomaly_start_time is None
        assert det_after.n_anomalous_samples == 0

    def test_double_reset_is_noop(self):
        svc = _make_service()
        sensor_id = "dr"
        obs = _make_obs(sensor_id=sensor_id, z_score=3.0)
        svc.process_observation(obs, OperatingRegime.STEADY_COOL)

        svc.reset_sensor(sensor_id)
        svc.reset_sensor(sensor_id)

        state = svc.cusum_states[sensor_id]
        assert state.s_pos == 0.0
        assert state.s_neg == 0.0


# ── Property 9: Joint detection coherence ────────────────────────────

class TestJointDetectionCoherence:
    """Joint change score should be bounded in [0,1]."""

    @pytest.mark.parametrize("seed", range(5))
    def test_joint_score_bounded(self, seed):
        rng = np.random.default_rng(seed)
        svc = _make_service()
        base = datetime(2025, 1, 1)

        for i in range(200):
            ts = base + timedelta(minutes=i)
            observations = {}
            trusts = {}
            for sid in ["s1", "s2", "s3"]:
                z = float(rng.normal(0, 2))
                observations[sid] = _make_obs(
                    sensor_id=sid,
                    z_score=z,
                    log_likelihood=-1.5 - 0.5 * z ** 2,
                    timestamp=ts,
                )
                trusts[sid] = 0.95

            jd = svc.process_joint_observations(
                observations, OperatingRegime.STEADY_COOL, trusts,
            )
            assert 0.0 <= jd.change_score <= 1.0, (
                f"Joint change score out of range at step {i}: {jd.change_score}"
            )


# ── Property 10: Low-trust sensors suppressed ───────────────────────

class TestLowTrustSuppression:
    """Low-trust sensors should not trigger alarms."""

    def test_low_trust_suppresses_alarm(self):
        svc = _make_service(
            cusum_threshold=2.0,
            min_persistence_minutes=0,
            min_steady_state_regimes=0,
            min_stability_for_alarm=0.0,
        )
        sensor_id = "low_trust"
        base = datetime(2025, 1, 1)

        for i in range(100):
            obs = _make_obs(
                sensor_id=sensor_id,
                z_score=10.0,
                log_likelihood=-51.5,
                timestamp=base + timedelta(minutes=i),
            )
            det = svc.process_observation(
                obs, OperatingRegime.STEADY_COOL, sensor_trust=0.3,
            )
            assert not det.change_detected, (
                f"Alarm fired with low trust at step {i}"
            )


# ── Property 11: Monotonic CUSUM growth under constant shift ────────

class TestCUSUMMonotonicGrowth:
    """Under constant positive shift, S_pos should be non-decreasing."""

    def test_cusum_grows_under_shift(self):
        svc = _make_service(cusum_threshold=100.0)  # high threshold so no reset
        sensor_id = "mono"
        base = datetime(2025, 1, 1)
        shift = 3.0
        prev_s_pos = 0.0

        for i in range(100):
            obs = _make_obs(
                sensor_id=sensor_id,
                z_score=shift,
                timestamp=base + timedelta(minutes=i),
            )
            svc.process_observation(obs, OperatingRegime.STEADY_COOL)
            s_pos = svc.cusum_states[sensor_id].s_pos
            assert s_pos >= prev_s_pos, (
                f"CUSUM S_pos decreased at step {i}: {prev_s_pos} → {s_pos}"
            )
            prev_s_pos = s_pos
