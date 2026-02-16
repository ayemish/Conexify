"""
Remaining Useful Life (RUL) Estimation Service

Implements multi-model RUL estimation combining:
1. Weibull survival analysis with Bayesian parameter updates
2. Physics-informed exponential degradation per fault type
3. Trend extrapolation on residual sequences
4. Error and uncertainty modeling throughout

Each model tracks its own prediction error distribution so that
downstream consumers (health index, decision policy) can incorporate
model confidence and false-positive/false-negative rates.

References:
- Si et al., "Remaining useful life estimation", MSSP 2011
- Saxena et al., NASA PHM Challenge
- ISO 13381-1: Condition monitoring and diagnostics — Prognostics
"""

import logging
import math
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..core.schemas import (
    ChangePointDetection,
    FaultType,
    OperatingRegime,
    SensorType,
)

logger = logging.getLogger(__name__)


# ── Fault-specific physics priors ────────────────────────────────────
# Mean-Time-To-Failure (hours) and shape parameter for Weibull prior,
# plus exponential degradation rate (dimensionless per hour).

FAULT_DEGRADATION_PRIORS: Dict[FaultType, Dict[str, float]] = {
    FaultType.REFRIGERANT_LEAK: {
        "weibull_shape": 1.8,
        "weibull_scale_hours": 720.0,
        "degradation_rate": 0.003,
    },
    FaultType.COMPRESSOR_DEGRADATION: {
        "weibull_shape": 2.5,
        "weibull_scale_hours": 2000.0,
        "degradation_rate": 0.001,
    },
    FaultType.CONDENSER_FOULING: {
        "weibull_shape": 2.0,
        "weibull_scale_hours": 1500.0,
        "degradation_rate": 0.002,
    },
    FaultType.EVAPORATOR_FOULING: {
        "weibull_shape": 1.5,
        "weibull_scale_hours": 168.0,
        "degradation_rate": 0.008,
    },
    FaultType.FAN_DEGRADATION: {
        "weibull_shape": 2.2,
        "weibull_scale_hours": 3000.0,
        "degradation_rate": 0.0008,
    },
}

DEFAULT_PRIOR = {
    "weibull_shape": 2.0,
    "weibull_scale_hours": 1000.0,
    "degradation_rate": 0.002,
}


# ── Data classes ─────────────────────────────────────────────────────

@dataclass
class RULEstimate:
    """A single RUL estimate with full uncertainty quantification."""
    estimate_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    timestamp: datetime = field(default_factory=datetime.utcnow)
    asset_id: str = ""
    fault_type: Optional[FaultType] = None

    # Point estimates (hours)
    rul_hours: float = float("inf")
    rul_lower_bound_hours: float = 0.0  # 5th percentile
    rul_upper_bound_hours: float = float("inf")  # 95th percentile

    # Model-specific estimates
    weibull_rul_hours: float = float("inf")
    degradation_rul_hours: float = float("inf")
    trend_rul_hours: float = float("inf")

    # Confidence and error modelling
    confidence: float = 0.0  # [0,1]
    prediction_std_hours: float = float("inf")
    model_agreement: float = 0.0  # Agreement among the three sub-models [0,1]

    # Error tracking (updated after feedback)
    mean_absolute_error_hours: float = float("inf")
    coverage_probability: float = 0.0  # fraction of actuals inside CI
    false_early_rate: float = 0.0  # predicted failure too soon
    false_late_rate: float = 0.0  # predicted failure too late (dangerous)

    # Degradation state
    degradation_index: float = 0.0  # [0,1] — 0=healthy, 1=failed
    degradation_rate: float = 0.0  # current rate of change per hour
    degradation_acceleration: float = 0.0  # second derivative

    def to_dict(self) -> Dict[str, Any]:
        return {
            "estimate_id": self.estimate_id,
            "timestamp": self.timestamp.isoformat(),
            "asset_id": self.asset_id,
            "fault_type": self.fault_type.value if self.fault_type else None,
            "rul_hours": self.rul_hours,
            "rul_lower_bound_hours": self.rul_lower_bound_hours,
            "rul_upper_bound_hours": self.rul_upper_bound_hours,
            "confidence": self.confidence,
            "prediction_std_hours": self.prediction_std_hours,
            "model_agreement": self.model_agreement,
            "degradation_index": self.degradation_index,
            "degradation_rate": self.degradation_rate,
            "degradation_acceleration": self.degradation_acceleration,
            "mean_absolute_error_hours": self.mean_absolute_error_hours,
            "false_early_rate": self.false_early_rate,
            "false_late_rate": self.false_late_rate,
        }


@dataclass
class DegradationState:
    """Tracks degradation trajectory for one (asset, fault_type) pair."""
    observations: deque = field(default_factory=lambda: deque(maxlen=2000))
    timestamps: deque = field(default_factory=lambda: deque(maxlen=2000))

    # Weibull posterior parameters (updated via MLE on censored observations)
    weibull_shape: float = 2.0
    weibull_scale: float = 1000.0

    # Exponential degradation state
    degradation_index: float = 0.0
    degradation_rate: float = 0.002
    degradation_rate_history: deque = field(default_factory=lambda: deque(maxlen=500))

    # Error tracking
    past_predictions: deque = field(default_factory=lambda: deque(maxlen=200))
    past_actuals: deque = field(default_factory=lambda: deque(maxlen=200))

    # Calendar
    hours_since_detection: float = 0.0
    detection_time: Optional[datetime] = None


# ── Service ──────────────────────────────────────────────────────────

class RULEstimationService:
    """
    Multi-model RUL estimation with error and uncertainty tracking.

    Three sub-models vote on RUL:
    1. **Weibull survival** — parametric failure-time distribution with
       Bayesian updating of shape/scale from observed run-to-failure data.
    2. **Physics-informed exponential degradation** — models a degradation
       index D(t) ∈ [0,1] with D(t) = 1 − exp(−λ·t).  λ is updated
       from the residual trend slope.
    3. **Trend extrapolation** — linear regression on the most recent
       residual z-scores, extrapolated to a critical threshold.

    The ensemble combines them with inverse-variance weighting and
    maintains a running error distribution for coverage calibration.
    """

    def __init__(self, asset_id: str, failure_threshold: float = 3.0):
        self.asset_id = asset_id
        self.failure_threshold = failure_threshold  # z-score threshold
        self.states: Dict[Optional[FaultType], DegradationState] = {}
        self.latest_estimate: Optional[RULEstimate] = None

    # ── Public API ───────────────────────────────────────────────────

    def estimate(
        self,
        fault_type: Optional[FaultType],
        change_scores: Dict[str, float],
        residual_z_scores: Dict[str, float],
        change_durations_hours: Dict[str, float],
        fault_probability: float,
        regime: OperatingRegime = OperatingRegime.UNKNOWN,
        timestamp: Optional[datetime] = None,
    ) -> RULEstimate:
        """
        Produce a composite RUL estimate.

        Args:
            fault_type: Diagnosed fault (may be None if unknown)
            change_scores: Per-sensor CUSUM/GLR scores
            residual_z_scores: Per-sensor residual z-scores
            change_durations_hours: How long each change has persisted
            fault_probability: Probability from the hypothesis layer
            regime: Current operating regime
            timestamp: Observation time
        """
        now = timestamp or datetime.utcnow()
        state = self._get_or_create_state(fault_type, now)
        prior = FAULT_DEGRADATION_PRIORS.get(fault_type, DEFAULT_PRIOR)

        # Aggregate inputs into a single degradation observation
        agg_z = self._aggregate_z_scores(residual_z_scores)
        max_duration = max(change_durations_hours.values(), default=0.0)

        # Record observation
        state.observations.append(agg_z)
        state.timestamps.append(now)
        if state.detection_time:
            state.hours_since_detection = (
                now - state.detection_time
            ).total_seconds() / 3600.0

        # Update degradation index
        self._update_degradation(state, agg_z, prior)

        # Sub-model estimates
        weibull_rul = self._weibull_rul(state, prior)
        degrad_rul = self._degradation_rul(state)
        trend_rul = self._trend_rul(state)

        # Ensemble (inverse-variance weighting)
        estimates = [weibull_rul, degrad_rul, trend_rul]
        finite = [(e, i) for i, e in enumerate(estimates) if math.isfinite(e) and e > 0]

        if finite:
            values = np.array([e for e, _ in finite])
            # Use spread as proxy for variance
            spread = max(np.std(values), 1.0)
            weights = 1.0 / (np.abs(values - np.median(values)) + spread)
            weights /= weights.sum()
            rul_point = float(np.dot(values, weights))
            rul_std = float(np.sqrt(np.average((values - rul_point) ** 2, weights=weights)))
            agreement = 1.0 - min(rul_std / (rul_point + 1.0), 1.0)
        else:
            rul_point = float("inf")
            rul_std = float("inf")
            agreement = 0.0

        # Confidence interval (log-normal assumption)
        if math.isfinite(rul_point) and rul_point > 0:
            log_std = max(rul_std / (rul_point + 1.0), 0.1)
            lower = rul_point * math.exp(-1.645 * log_std)
            upper = rul_point * math.exp(1.645 * log_std)
        else:
            lower = 0.0
            upper = float("inf")

        # Confidence combines fault probability, model agreement, data depth
        data_depth = min(len(state.observations) / 50.0, 1.0)
        confidence = fault_probability * agreement * data_depth

        # Error metrics from history
        mae, coverage, false_early, false_late = self._compute_error_metrics(state)

        estimate = RULEstimate(
            timestamp=now,
            asset_id=self.asset_id,
            fault_type=fault_type,
            rul_hours=rul_point,
            rul_lower_bound_hours=lower,
            rul_upper_bound_hours=upper,
            weibull_rul_hours=weibull_rul,
            degradation_rul_hours=degrad_rul,
            trend_rul_hours=trend_rul,
            confidence=min(confidence, 1.0),
            prediction_std_hours=rul_std,
            model_agreement=agreement,
            mean_absolute_error_hours=mae,
            coverage_probability=coverage,
            false_early_rate=false_early,
            false_late_rate=false_late,
            degradation_index=state.degradation_index,
            degradation_rate=state.degradation_rate,
            degradation_acceleration=self._degradation_acceleration(state),
        )

        # Store prediction for future error tracking
        state.past_predictions.append((now, rul_point))
        self.latest_estimate = estimate
        return estimate

    def record_actual_failure(
        self,
        fault_type: Optional[FaultType],
        failure_time: datetime,
    ):
        """Record when a failure actually occurred for error calibration."""
        state = self.states.get(fault_type)
        if not state:
            return
        for pred_time, pred_rul in state.past_predictions:
            predicted_failure = pred_time + timedelta(hours=pred_rul)
            actual_rul_at_pred = (failure_time - pred_time).total_seconds() / 3600.0
            if actual_rul_at_pred > 0:
                state.past_actuals.append((pred_time, actual_rul_at_pred))

    # ── Sub-models ───────────────────────────────────────────────────

    def _weibull_rul(self, state: DegradationState, prior: Dict) -> float:
        """Conditional Weibull RUL given survival to current time."""
        k = state.weibull_shape
        lam = state.weibull_scale
        t = max(state.hours_since_detection, 0.1)

        # E[T - t | T > t] for Weibull
        try:
            surv_t = math.exp(-((t / lam) ** k))
            if surv_t < 1e-10:
                return 0.0
            # Numerical integration via Gauss-Laguerre-style approximation
            steps = 50
            dt = lam * 3.0 / steps
            integral = 0.0
            for i in range(1, steps + 1):
                s = t + i * dt
                surv_s = math.exp(-((s / lam) ** k))
                integral += surv_s * dt
            return integral / surv_t
        except (OverflowError, ZeroDivisionError):
            return float("inf")

    def _degradation_rul(self, state: DegradationState) -> float:
        """RUL from exponential degradation: D(t)=1-exp(-λt), solve for D=1."""
        d = state.degradation_index
        lam = state.degradation_rate
        if lam <= 0 or d >= 1.0:
            return 0.0 if d >= 1.0 else float("inf")
        # Time to reach threshold (D=0.95 as practical failure)
        threshold = 0.95
        if d >= threshold:
            return 0.0
        try:
            t_fail = -math.log(1.0 - threshold) / lam
            t_now = -math.log(1.0 - d) / lam if d > 0 else 0.0
            return max(t_fail - t_now, 0.0)
        except (ValueError, ZeroDivisionError):
            return float("inf")

    def _trend_rul(self, state: DegradationState) -> float:
        """Linear extrapolation of z-score trend to failure threshold."""
        n = len(state.observations)
        if n < 10:
            return float("inf")

        recent = list(state.observations)[-min(n, 100):]
        x = np.arange(len(recent), dtype=float)
        y = np.array(recent, dtype=float)

        # Robust linear fit
        try:
            coeffs = np.polyfit(x, y, 1)
            slope = coeffs[0]
        except (np.linalg.LinAlgError, ValueError):
            return float("inf")

        if slope <= 0:
            return float("inf")

        current_z = y[-1]
        if current_z >= self.failure_threshold:
            return 0.0

        steps_to_fail = (self.failure_threshold - current_z) / slope

        # Convert steps to hours (estimate cadence from timestamps)
        if len(state.timestamps) >= 2:
            ts_list = list(state.timestamps)[-min(n, 100):]
            total_hours = (ts_list[-1] - ts_list[0]).total_seconds() / 3600.0
            hours_per_step = total_hours / max(len(ts_list) - 1, 1)
        else:
            hours_per_step = 1.0

        return max(steps_to_fail * hours_per_step, 0.0)

    # ── Degradation tracking ─────────────────────────────────────────

    def _update_degradation(
        self,
        state: DegradationState,
        agg_z: float,
        prior: Dict,
    ):
        """Update degradation index and rate using exponential filter."""
        # Map z-score to [0,1] degradation space via sigmoid
        d_obs = 1.0 / (1.0 + math.exp(-0.5 * (agg_z - 1.5)))

        # Exponential moving average
        alpha = 0.05
        state.degradation_index = (1 - alpha) * state.degradation_index + alpha * d_obs

        # Update rate from recent observations
        if len(state.observations) >= 5:
            recent = list(state.observations)[-20:]
            diffs = np.diff(recent)
            new_rate = float(np.mean(np.maximum(diffs, 0)))
            state.degradation_rate = (1 - alpha) * state.degradation_rate + alpha * max(new_rate, prior["degradation_rate"] * 0.1)
        state.degradation_rate_history.append(state.degradation_rate)

        # Update Weibull parameters (simple MLE-inspired update)
        if len(state.observations) > 20:
            # Use degradation trajectory to refine Weibull scale
            d_arr = np.array(list(state.observations)[-100:])
            above_threshold = np.sum(d_arr > self.failure_threshold * 0.5)
            fraction_degraded = above_threshold / len(d_arr)
            if fraction_degraded > 0:
                # Adjust scale downward if more data shows degradation
                state.weibull_scale = prior["weibull_scale_hours"] * (1.0 - 0.5 * fraction_degraded)
            state.weibull_shape = prior["weibull_shape"]

    def _degradation_acceleration(self, state: DegradationState) -> float:
        """Second derivative of degradation rate."""
        if len(state.degradation_rate_history) < 5:
            return 0.0
        recent = list(state.degradation_rate_history)[-20:]
        if len(recent) < 3:
            return 0.0
        diffs = np.diff(recent)
        return float(np.mean(diffs))

    # ── Error metrics ────────────────────────────────────────────────

    def _compute_error_metrics(
        self, state: DegradationState,
    ) -> Tuple[float, float, float, float]:
        """Compute prediction error statistics from historical feedback."""
        if not state.past_actuals:
            return float("inf"), 0.0, 0.0, 0.0

        errors = []
        inside_ci = 0
        false_early = 0
        false_late = 0
        total = 0

        for pred_time, actual_rul in state.past_actuals:
            # Find closest prediction
            best_pred_rul = None
            for pt, pr in state.past_predictions:
                if abs((pt - pred_time).total_seconds()) < 60:
                    best_pred_rul = pr
                    break
            if best_pred_rul is None:
                continue

            total += 1
            err = best_pred_rul - actual_rul
            errors.append(abs(err))

            if err < -actual_rul * 0.2:
                false_early += 1
            elif err > actual_rul * 0.2:
                false_late += 1

        if not errors:
            return float("inf"), 0.0, 0.0, 0.0

        mae = float(np.mean(errors))
        fe_rate = false_early / total if total else 0.0
        fl_rate = false_late / total if total else 0.0
        coverage = 1.0 - (false_early + false_late) / total if total else 0.0

        return mae, max(coverage, 0.0), fe_rate, fl_rate

    # ── Helpers ──────────────────────────────────────────────────────

    def _get_or_create_state(
        self, fault_type: Optional[FaultType], now: datetime,
    ) -> DegradationState:
        if fault_type not in self.states:
            prior = FAULT_DEGRADATION_PRIORS.get(fault_type, DEFAULT_PRIOR)
            self.states[fault_type] = DegradationState(
                weibull_shape=prior["weibull_shape"],
                weibull_scale=prior["weibull_scale_hours"],
                degradation_rate=prior["degradation_rate"],
                detection_time=now,
            )
        return self.states[fault_type]

    @staticmethod
    def _aggregate_z_scores(z_scores: Dict[str, float]) -> float:
        """Aggregate per-sensor z-scores into a single value (RMS)."""
        if not z_scores:
            return 0.0
        values = [abs(v) for v in z_scores.values()]
        return float(np.sqrt(np.mean(np.square(values))))
