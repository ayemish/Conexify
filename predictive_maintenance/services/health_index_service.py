"""
Composite Health Index (PHI) Service

Fuses multi-model signals into a single 0–100 health score per asset,
enabling fleet-level prioritization and P-F curve positioning.

The index combines:
- Sensor trust (inverted: low trust = penalty)
- Change detection persistence and magnitude
- Fault hypothesis probability
- RUL estimate (when available)
- Degradation index

Each component tracks its own error distribution so that the composite
score carries calibrated uncertainty.

The score maps to the ISO 13374 CBM framework:
  100  = healthy (no detected issues)
  70-99 = monitoring (early indicators)
  40-69 = alert (confirmed degradation)
  10-39 = action required (imminent failure)
  0-9   = critical / failed
"""

import logging
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..core.schemas import AlertType, FaultType, OperatingRegime

logger = logging.getLogger(__name__)


# ── Component weights (configurable) ────────────────────────────────

@dataclass
class HealthIndexWeights:
    """Relative weights for each component of the health index."""
    sensor_trust: float = 0.15
    change_detection: float = 0.20
    fault_probability: float = 0.25
    rul_normalized: float = 0.25
    degradation: float = 0.15

    def total(self) -> float:
        return (
            self.sensor_trust + self.change_detection
            + self.fault_probability + self.rul_normalized
            + self.degradation
        )

    def normalized(self) -> "HealthIndexWeights":
        t = self.total()
        if t == 0:
            return self
        return HealthIndexWeights(
            sensor_trust=self.sensor_trust / t,
            change_detection=self.change_detection / t,
            fault_probability=self.fault_probability / t,
            rul_normalized=self.rul_normalized / t,
            degradation=self.degradation / t,
        )


# ── Output data class ───────────────────────────────────────────────

@dataclass
class HealthIndexResult:
    """Composite health index with component breakdown."""
    asset_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Composite score 0-100
    health_score: float = 100.0
    health_band: str = "healthy"  # healthy/monitoring/alert/action/critical

    # Component scores (each 0-100, higher=healthier)
    sensor_trust_score: float = 100.0
    change_detection_score: float = 100.0
    fault_probability_score: float = 100.0
    rul_score: float = 100.0
    degradation_score: float = 100.0

    # Uncertainty
    confidence: float = 0.0
    score_std: float = 0.0
    component_agreement: float = 1.0

    # Error model: how well does this score predict outcomes?
    false_healthy_rate: float = 0.0  # scored healthy but failed
    false_critical_rate: float = 0.0  # scored critical but was fine
    mean_score_error: float = 0.0

    # Trend
    score_trend: float = 0.0  # positive=improving, negative=degrading
    hours_in_current_band: float = 0.0

    # P-F curve position (0=potential failure detected, 1=functional failure)
    pf_position: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "timestamp": self.timestamp.isoformat(),
            "health_score": round(self.health_score, 1),
            "health_band": self.health_band,
            "sensor_trust_score": round(self.sensor_trust_score, 1),
            "change_detection_score": round(self.change_detection_score, 1),
            "fault_probability_score": round(self.fault_probability_score, 1),
            "rul_score": round(self.rul_score, 1),
            "degradation_score": round(self.degradation_score, 1),
            "confidence": round(self.confidence, 3),
            "score_std": round(self.score_std, 1),
            "score_trend": round(self.score_trend, 2),
            "pf_position": round(self.pf_position, 3),
            "false_healthy_rate": round(self.false_healthy_rate, 3),
            "false_critical_rate": round(self.false_critical_rate, 3),
        }


# ── Service ──────────────────────────────────────────────────────────

class HealthIndexService:
    """
    Computes a composite health index from multi-model PdM signals.

    Maintains a score history for trend analysis and tracks prediction
    errors from technician feedback to calibrate the false-healthy and
    false-critical rates.
    """

    def __init__(
        self,
        asset_id: str,
        weights: Optional[HealthIndexWeights] = None,
        rul_horizon_hours: float = 720.0,
    ):
        self.asset_id = asset_id
        self.weights = (weights or HealthIndexWeights()).normalized()
        self.rul_horizon_hours = rul_horizon_hours

        # History
        self.score_history: deque = deque(maxlen=2000)
        self.band_entered_at: Optional[datetime] = None
        self.current_band: str = "healthy"

        # Error calibration
        self._predictions: deque = deque(maxlen=500)
        self._outcomes: deque = deque(maxlen=500)

        self.latest_result: Optional[HealthIndexResult] = None

    # ── Public API ───────────────────────────────────────────────────

    def compute(
        self,
        min_sensor_trust: float = 1.0,
        max_change_score: float = 0.0,
        max_change_duration_hours: float = 0.0,
        n_changes: int = 0,
        top_fault_probability: float = 0.0,
        rul_hours: float = float("inf"),
        degradation_index: float = 0.0,
        regime: OperatingRegime = OperatingRegime.UNKNOWN,
        timestamp: Optional[datetime] = None,
    ) -> HealthIndexResult:
        """
        Compute the composite health index.

        All inputs should come from the existing kernel/orchestrator output.
        """
        now = timestamp or datetime.utcnow()

        # Map each input to a 0-100 health sub-score
        st_score = self._sensor_trust_to_score(min_sensor_trust)
        cd_score = self._change_detection_to_score(
            max_change_score, max_change_duration_hours, n_changes,
        )
        fp_score = self._fault_probability_to_score(top_fault_probability)
        rul_sc = self._rul_to_score(rul_hours)
        dg_score = self._degradation_to_score(degradation_index)

        # Weighted composite
        w = self.weights
        composite = (
            w.sensor_trust * st_score
            + w.change_detection * cd_score
            + w.fault_probability * fp_score
            + w.rul_normalized * rul_sc
            + w.degradation * dg_score
        )
        composite = max(0.0, min(100.0, composite))

        # Component agreement
        components = [st_score, cd_score, fp_score, rul_sc, dg_score]
        std = float(np.std(components))
        agreement = max(0.0, 1.0 - std / 50.0)

        # Confidence (more data + better agreement = higher confidence)
        data_depth = min(len(self.score_history) / 30.0, 1.0)
        confidence = agreement * data_depth

        # Band classification
        band = self._classify_band(composite)

        # Track band duration
        if band != self.current_band:
            self.band_entered_at = now
            self.current_band = band
        hours_in_band = 0.0
        if self.band_entered_at:
            hours_in_band = (now - self.band_entered_at).total_seconds() / 3600.0

        # Trend (slope of last N scores)
        trend = self._compute_trend()

        # P-F position: 0=just detected potential failure, 1=functional failure
        pf = self._compute_pf_position(composite, degradation_index)

        # Error metrics
        fh_rate, fc_rate, mse = self._compute_error_metrics()

        result = HealthIndexResult(
            asset_id=self.asset_id,
            timestamp=now,
            health_score=composite,
            health_band=band,
            sensor_trust_score=st_score,
            change_detection_score=cd_score,
            fault_probability_score=fp_score,
            rul_score=rul_sc,
            degradation_score=dg_score,
            confidence=confidence,
            score_std=std,
            component_agreement=agreement,
            false_healthy_rate=fh_rate,
            false_critical_rate=fc_rate,
            mean_score_error=mse,
            score_trend=trend,
            hours_in_current_band=hours_in_band,
            pf_position=pf,
        )

        self.score_history.append((now, composite))
        self._predictions.append((now, composite, band))
        self.latest_result = result
        return result

    def record_outcome(
        self,
        timestamp: datetime,
        actual_healthy: bool,
        notes: str = "",
    ):
        """Record technician feedback for error calibration."""
        self._outcomes.append((timestamp, actual_healthy, notes))

    # ── Mapping functions ────────────────────────────────────────────

    @staticmethod
    def _sensor_trust_to_score(min_trust: float) -> float:
        """Higher trust → higher score."""
        return max(0.0, min(100.0, min_trust * 100.0))

    @staticmethod
    def _change_detection_to_score(
        max_score: float, max_duration: float, n_changes: int,
    ) -> float:
        """No changes → 100; severe persistent changes → 0."""
        if n_changes == 0:
            return 100.0
        # Score penalty from magnitude
        magnitude_penalty = min(max_score / 20.0, 1.0) * 40.0
        # Penalty from persistence (>24h is very bad)
        persistence_penalty = min(max_duration / 24.0, 1.0) * 30.0
        # Penalty from breadth
        breadth_penalty = min(n_changes / 4.0, 1.0) * 30.0
        return max(0.0, 100.0 - magnitude_penalty - persistence_penalty - breadth_penalty)

    @staticmethod
    def _fault_probability_to_score(prob: float) -> float:
        """P(fault)=0 → 100; P(fault)=1 → 0."""
        return max(0.0, min(100.0, (1.0 - prob) * 100.0))

    def _rul_to_score(self, rul_hours: float) -> float:
        """Map RUL to 0-100: >horizon=100, 0=0, linear between."""
        if not math.isfinite(rul_hours) or rul_hours >= self.rul_horizon_hours:
            return 100.0
        if rul_hours <= 0:
            return 0.0
        return (rul_hours / self.rul_horizon_hours) * 100.0

    @staticmethod
    def _degradation_to_score(deg_index: float) -> float:
        """D=0 → 100; D=1 → 0."""
        return max(0.0, min(100.0, (1.0 - deg_index) * 100.0))

    @staticmethod
    def _classify_band(score: float) -> str:
        if score >= 70:
            return "healthy" if score >= 90 else "monitoring"
        if score >= 40:
            return "alert"
        if score >= 10:
            return "action"
        return "critical"

    def _compute_trend(self) -> float:
        """Slope of recent scores (positive=improving)."""
        if len(self.score_history) < 5:
            return 0.0
        recent = list(self.score_history)[-min(len(self.score_history), 50):]
        y = np.array([s for _, s in recent])
        x = np.arange(len(y), dtype=float)
        try:
            slope = float(np.polyfit(x, y, 1)[0])
        except (np.linalg.LinAlgError, ValueError):
            slope = 0.0
        return slope

    @staticmethod
    def _compute_pf_position(score: float, deg_index: float) -> float:
        """Position on the P-F curve: 0=early warning, 1=failure."""
        # Blend score (inverted) and degradation index
        score_pos = 1.0 - score / 100.0
        return 0.6 * deg_index + 0.4 * score_pos

    def _compute_error_metrics(self) -> Tuple[float, float, float]:
        """Compute error rates from feedback."""
        if not self._outcomes:
            return 0.0, 0.0, 0.0

        false_healthy = 0
        false_critical = 0
        total = 0
        score_errors = []

        for out_ts, actual_healthy, _ in self._outcomes:
            # Find closest prediction
            closest = None
            closest_dt = float("inf")
            for pred_ts, pred_score, pred_band in self._predictions:
                dt = abs((pred_ts - out_ts).total_seconds())
                if dt < closest_dt:
                    closest_dt = dt
                    closest = (pred_score, pred_band)

            if closest is None or closest_dt > 3600:
                continue

            total += 1
            pred_score, pred_band = closest
            actual_score = 100.0 if actual_healthy else 20.0
            score_errors.append(abs(pred_score - actual_score))

            if pred_band in ("healthy", "monitoring") and not actual_healthy:
                false_healthy += 1
            if pred_band in ("action", "critical") and actual_healthy:
                false_critical += 1

        if total == 0:
            return 0.0, 0.0, 0.0

        return (
            false_healthy / total,
            false_critical / total,
            float(np.mean(score_errors)),
        )
