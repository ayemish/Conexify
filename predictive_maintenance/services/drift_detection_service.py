"""
Concept Drift Detection Service

Monitors model inputs, predictions, and calibration for distributional
shift.  When drift is detected the service notifies the retraining
trigger so that the appropriate sub-model can be retrained.

Three drift detectors run in parallel:
1. **Input drift** — KL divergence / PSI on feature distributions
2. **Prediction drift** — tracks calibration curve slope and intercept
3. **Label drift** — monitors fault-type frequency distribution

Each detector maintains its own error model (false-alarm rate for drift
alarms, missed-drift rate from retrospective checks).

References:
- Gama et al., "A Survey on Concept Drift Adaptation", ACM 2014
- Page-Hinkley test for sequential change detection on scalar statistics
"""

import logging
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ── Data classes ─────────────────────────────────────────────────────

@dataclass
class DriftSignal:
    """Emitted when drift is detected on a specific axis."""
    signal_id: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    drift_type: str = ""  # input | prediction | label
    model_id: str = ""
    asset_id: str = ""
    score: float = 0.0
    threshold: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)

    # Error model for this detector
    false_alarm_rate: float = 0.0
    missed_drift_rate: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "timestamp": self.timestamp.isoformat(),
            "drift_type": self.drift_type,
            "model_id": self.model_id,
            "asset_id": self.asset_id,
            "score": self.score,
            "threshold": self.threshold,
            "false_alarm_rate": self.false_alarm_rate,
            "missed_drift_rate": self.missed_drift_rate,
            "details": self.details,
        }


@dataclass
class PageHinkleyState:
    """State for the Page-Hinkley sequential drift test."""
    cumulative_sum: float = 0.0
    min_cumulative: float = 0.0
    n: int = 0
    running_mean: float = 0.0
    running_m2: float = 0.0  # for Welford variance

    def mean(self) -> float:
        return self.running_mean

    def variance(self) -> float:
        if self.n < 2:
            return 1.0
        return self.running_m2 / (self.n - 1)


# ── Service ──────────────────────────────────────────────────────────

class DriftDetectionService:
    """
    Monitors three drift axes and emits DriftSignal when thresholds are
    crossed.  Designed to be called once per telemetry tick (lightweight).
    """

    def __init__(
        self,
        asset_id: str,
        model_id: str = "behavior_model",
        input_psi_threshold: float = 0.25,
        prediction_ph_threshold: float = 15.0,
        label_psi_threshold: float = 0.30,
        reference_window: int = 500,
        test_window: int = 100,
        on_drift: Optional[Callable[[DriftSignal], None]] = None,
    ):
        self.asset_id = asset_id
        self.model_id = model_id
        self.input_psi_threshold = input_psi_threshold
        self.prediction_ph_threshold = prediction_ph_threshold
        self.label_psi_threshold = label_psi_threshold
        self.reference_window = reference_window
        self.test_window = test_window
        self._on_drift = on_drift

        # Input drift: feature histograms (reference vs recent)
        self._feature_ref: Dict[str, deque] = {}
        self._feature_test: Dict[str, deque] = {}

        # Prediction drift: Page-Hinkley on residual mean
        self._ph_state = PageHinkleyState()

        # Label drift: fault-type frequency
        self._label_ref: deque = deque(maxlen=reference_window)
        self._label_test: deque = deque(maxlen=test_window)

        # Error calibration
        self._drift_alarms: List[DriftSignal] = []
        self._confirmed_drifts: int = 0
        self._false_drift_alarms: int = 0
        self._missed_drifts: int = 0

        self._tick = 0

    # ── Public API ───────────────────────────────────────────────────

    def observe(
        self,
        features: Dict[str, float],
        prediction_error: float,
        fault_label: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> List[DriftSignal]:
        """
        Ingest one observation and return any drift signals fired.

        Args:
            features: Dict of feature_name → value (e.g. sensor readings)
            prediction_error: Signed residual (actual - predicted)
            fault_label: Current fault-type label (or None/normal)
            timestamp: Observation time

        Returns:
            List of DriftSignal (empty if no drift detected)
        """
        self._tick += 1
        now = timestamp or datetime.utcnow()
        signals: List[DriftSignal] = []

        # 1. Input drift (PSI on features)
        input_signal = self._check_input_drift(features, now)
        if input_signal:
            signals.append(input_signal)

        # 2. Prediction drift (Page-Hinkley on residual)
        pred_signal = self._check_prediction_drift(prediction_error, now)
        if pred_signal:
            signals.append(pred_signal)

        # 3. Label drift (PSI on fault-type distribution)
        if fault_label:
            self._label_test.append(fault_label)
            if self._tick <= self.reference_window:
                self._label_ref.append(fault_label)
        if self._tick % self.test_window == 0 and len(self._label_test) >= self.test_window // 2:
            label_signal = self._check_label_drift(now)
            if label_signal:
                signals.append(label_signal)

        # Fire callbacks
        for sig in signals:
            self._drift_alarms.append(sig)
            if self._on_drift:
                try:
                    self._on_drift(sig)
                except Exception as e:
                    logger.error(f"Drift callback failed: {e}")

        return signals

    def confirm_drift(self, was_real: bool):
        """Provide ground-truth for drift alarm calibration."""
        if was_real:
            self._confirmed_drifts += 1
        else:
            self._false_drift_alarms += 1

    def record_missed_drift(self):
        """Record that drift occurred but was not detected."""
        self._missed_drifts += 1

    @property
    def false_alarm_rate(self) -> float:
        total = self._confirmed_drifts + self._false_drift_alarms
        return self._false_drift_alarms / max(total, 1)

    @property
    def missed_drift_rate(self) -> float:
        total = self._confirmed_drifts + self._missed_drifts
        return self._missed_drifts / max(total, 1)

    # ── Input drift (PSI) ────────────────────────────────────────────

    def _check_input_drift(
        self, features: Dict[str, float], now: datetime,
    ) -> Optional[DriftSignal]:
        for name, value in features.items():
            if name not in self._feature_ref:
                self._feature_ref[name] = deque(maxlen=self.reference_window)
                self._feature_test[name] = deque(maxlen=self.test_window)

            if self._tick <= self.reference_window:
                self._feature_ref[name].append(value)
            self._feature_test[name].append(value)

        # Only check periodically
        if self._tick % self.test_window != 0:
            return None
        if self._tick <= self.reference_window:
            return None

        psi_scores = {}
        for name in self._feature_ref:
            ref = np.array(self._feature_ref[name])
            test = np.array(self._feature_test[name])
            if len(ref) < 20 or len(test) < 20:
                continue
            psi = self._compute_psi(ref, test)
            psi_scores[name] = psi

        if not psi_scores:
            return None

        max_psi = max(psi_scores.values())
        worst_feature = max(psi_scores, key=psi_scores.get)

        if max_psi > self.input_psi_threshold:
            return DriftSignal(
                signal_id=f"DRIFT-IN-{self._tick}",
                timestamp=now,
                drift_type="input",
                model_id=self.model_id,
                asset_id=self.asset_id,
                score=max_psi,
                threshold=self.input_psi_threshold,
                false_alarm_rate=self.false_alarm_rate,
                missed_drift_rate=self.missed_drift_rate,
                details={
                    "worst_feature": worst_feature,
                    "psi_scores": {k: round(v, 4) for k, v in psi_scores.items()},
                },
            )
        return None

    # ── Prediction drift (Page-Hinkley) ──────────────────────────────

    def _check_prediction_drift(
        self, error: float, now: datetime,
    ) -> Optional[DriftSignal]:
        ph = self._ph_state
        ph.n += 1
        delta = error - ph.running_mean
        ph.running_mean += delta / ph.n
        ph.running_m2 += delta * (error - ph.running_mean)

        # Page-Hinkley statistic
        ph.cumulative_sum += error - ph.running_mean - 0.005  # allowance δ
        ph.min_cumulative = min(ph.min_cumulative, ph.cumulative_sum)
        ph_stat = ph.cumulative_sum - ph.min_cumulative

        if ph.n > 30 and ph_stat > self.prediction_ph_threshold:
            # Reset after detection
            signal = DriftSignal(
                signal_id=f"DRIFT-PRED-{self._tick}",
                timestamp=now,
                drift_type="prediction",
                model_id=self.model_id,
                asset_id=self.asset_id,
                score=ph_stat,
                threshold=self.prediction_ph_threshold,
                false_alarm_rate=self.false_alarm_rate,
                missed_drift_rate=self.missed_drift_rate,
                details={
                    "residual_mean": ph.running_mean,
                    "residual_var": ph.variance(),
                    "n_observations": ph.n,
                },
            )
            # Partial reset (keep running mean for reference)
            ph.cumulative_sum = 0.0
            ph.min_cumulative = 0.0
            return signal
        return None

    # ── Label drift (PSI on fault categories) ────────────────────────

    def _check_label_drift(self, now: datetime) -> Optional[DriftSignal]:
        if len(self._label_ref) < 20 or len(self._label_test) < 20:
            return None

        ref_counts = self._label_counts(self._label_ref)
        test_counts = self._label_counts(self._label_test)

        all_labels = set(ref_counts) | set(test_counts)
        n_ref = sum(ref_counts.values())
        n_test = sum(test_counts.values())

        psi = 0.0
        for label in all_labels:
            p_ref = (ref_counts.get(label, 0) + 0.5) / (n_ref + 0.5 * len(all_labels))
            p_test = (test_counts.get(label, 0) + 0.5) / (n_test + 0.5 * len(all_labels))
            if p_ref > 0 and p_test > 0:
                psi += (p_test - p_ref) * math.log(p_test / p_ref)

        if psi > self.label_psi_threshold:
            return DriftSignal(
                signal_id=f"DRIFT-LBL-{self._tick}",
                timestamp=now,
                drift_type="label",
                model_id=self.model_id,
                asset_id=self.asset_id,
                score=psi,
                threshold=self.label_psi_threshold,
                false_alarm_rate=self.false_alarm_rate,
                missed_drift_rate=self.missed_drift_rate,
                details={
                    "ref_distribution": dict(ref_counts),
                    "test_distribution": dict(test_counts),
                },
            )
        return None

    # ── Utilities ────────────────────────────────────────────────────

    @staticmethod
    def _compute_psi(reference: np.ndarray, test: np.ndarray, n_bins: int = 10) -> float:
        """Population Stability Index between two distributions."""
        # Use reference quantiles as bin edges for stability
        edges = np.percentile(reference, np.linspace(0, 100, n_bins + 1))
        edges[0] = -np.inf
        edges[-1] = np.inf
        # Remove duplicates
        edges = np.unique(edges)
        if len(edges) < 3:
            return 0.0

        ref_hist, _ = np.histogram(reference, bins=edges)
        test_hist, _ = np.histogram(test, bins=edges)

        # Normalize with Laplace smoothing
        ref_pct = (ref_hist + 0.5) / (len(reference) + 0.5 * len(ref_hist))
        test_pct = (test_hist + 0.5) / (len(test) + 0.5 * len(test_hist))

        psi = float(np.sum((test_pct - ref_pct) * np.log(test_pct / ref_pct)))
        return max(psi, 0.0)

    @staticmethod
    def _label_counts(labels) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for lbl in labels:
            counts[lbl] = counts.get(lbl, 0) + 1
        return counts
