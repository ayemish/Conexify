"""
Retraining Trigger Service

Bridges technician feedback and drift detection into automatic model
retraining decisions.  Tracks per-model error statistics, decides when
the accumulated evidence justifies a retrain, and emits events via the
Redis event bus.

Trigger conditions (any one is sufficient):
1. CASE_FEEDBACK — N consecutive incorrect predictions for the same fault type
2. DRIFT_DETECTED — concept drift detector fires (see drift_detection_service)
3. PERFORMANCE_DEGRADATION — rolling false-positive or false-negative rate exceeds threshold
4. NEW_DATA_VOLUME — accumulated observations since last training exceeds threshold
5. SCHEDULED — calendar-based periodic retrain

Each trigger carries a full error model snapshot so the training pipeline
can prioritize which sub-models need updating.
"""

import logging
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RetrainingRequest:
    """Emitted when a retrain is warranted."""
    request_id: str = field(default_factory=lambda: f"RTR-{uuid.uuid4().hex[:10].upper()}")
    timestamp: datetime = field(default_factory=datetime.utcnow)
    trigger_type: str = ""  # case_feedback | drift | performance | volume | scheduled
    model_id: str = ""
    asset_id: str = ""
    fault_type: Optional[str] = None

    # Error snapshot at trigger time
    false_positive_rate: float = 0.0
    false_negative_rate: float = 0.0
    mean_absolute_error: float = 0.0
    n_incorrect_recent: int = 0
    n_observations_since_train: int = 0

    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
            "trigger_type": self.trigger_type,
            "model_id": self.model_id,
            "asset_id": self.asset_id,
            "fault_type": self.fault_type,
            "false_positive_rate": self.false_positive_rate,
            "false_negative_rate": self.false_negative_rate,
            "mean_absolute_error": self.mean_absolute_error,
            "n_incorrect_recent": self.n_incorrect_recent,
            "n_observations_since_train": self.n_observations_since_train,
            "evidence": self.evidence,
        }


@dataclass
class FeedbackRecord:
    timestamp: datetime
    asset_id: str
    fault_type: Optional[str]
    predicted_outcome: str
    actual_outcome: str
    was_correct: bool
    notes: str = ""


class RetrainingTriggerService:
    """
    Accumulates feedback and performance signals, emits RetrainingRequest
    when thresholds are crossed.
    """

    def __init__(
        self,
        incorrect_streak_threshold: int = 5,
        fp_rate_threshold: float = 0.15,
        fn_rate_threshold: float = 0.10,
        volume_threshold: int = 5000,
        window_size: int = 100,
        event_bus_publish: Optional[Callable] = None,
    ):
        self.incorrect_streak_threshold = incorrect_streak_threshold
        self.fp_rate_threshold = fp_rate_threshold
        self.fn_rate_threshold = fn_rate_threshold
        self.volume_threshold = volume_threshold
        self.window_size = window_size
        self._publish = event_bus_publish

        # Per-fault-type tracking
        self._feedback: Dict[Optional[str], deque] = defaultdict(
            lambda: deque(maxlen=self.window_size)
        )
        self._streak: Dict[Optional[str], int] = defaultdict(int)
        self._obs_since_train: Dict[str, int] = defaultdict(int)
        self._last_train: Dict[str, datetime] = {}

        # Emitted requests (for auditing)
        self.pending_requests: List[RetrainingRequest] = []

    # ── Public ───────────────────────────────────────────────────────

    def record_feedback(self, record: FeedbackRecord) -> Optional[RetrainingRequest]:
        """
        Ingest one feedback record and check if any trigger fires.

        Returns a RetrainingRequest if a retrain is warranted, else None.
        """
        ft = record.fault_type
        self._feedback[ft].append(record)

        # Update streak
        if record.was_correct:
            self._streak[ft] = 0
        else:
            self._streak[ft] += 1

        # Check streak trigger
        if self._streak[ft] >= self.incorrect_streak_threshold:
            return self._emit(
                trigger_type="case_feedback",
                fault_type=ft,
                asset_id=record.asset_id,
                evidence={"streak_length": self._streak[ft]},
            )

        # Check rolling FP/FN rate
        fp, fn = self._compute_rates(ft)
        if fp > self.fp_rate_threshold:
            return self._emit(
                trigger_type="performance",
                fault_type=ft,
                asset_id=record.asset_id,
                evidence={"false_positive_rate": fp, "threshold": self.fp_rate_threshold},
            )
        if fn > self.fn_rate_threshold:
            return self._emit(
                trigger_type="performance",
                fault_type=ft,
                asset_id=record.asset_id,
                evidence={"false_negative_rate": fn, "threshold": self.fn_rate_threshold},
            )

        return None

    def record_observation(self, model_id: str):
        """Tick observation counter; check volume trigger."""
        self._obs_since_train[model_id] += 1
        if self._obs_since_train[model_id] >= self.volume_threshold:
            req = self._emit(
                trigger_type="volume",
                model_id=model_id,
                evidence={"observations": self._obs_since_train[model_id]},
            )
            self._obs_since_train[model_id] = 0
            return req
        return None

    def record_drift_detected(
        self,
        model_id: str,
        asset_id: str = "",
        drift_score: float = 0.0,
        drift_type: str = "input",
    ) -> RetrainingRequest:
        """External drift detector notifies us."""
        return self._emit(
            trigger_type="drift",
            model_id=model_id,
            asset_id=asset_id,
            evidence={"drift_score": drift_score, "drift_type": drift_type},
        )

    def mark_retrained(self, model_id: str):
        """Called after a model is retrained to reset counters."""
        self._obs_since_train[model_id] = 0
        self._last_train[model_id] = datetime.utcnow()
        for ft in list(self._streak.keys()):
            self._streak[ft] = 0

    # ── Internal ─────────────────────────────────────────────────────

    def _compute_rates(self, fault_type: Optional[str]):
        records = list(self._feedback[fault_type])
        if not records:
            return 0.0, 0.0

        tp = fp = fn = tn = 0
        for r in records:
            predicted_positive = r.predicted_outcome not in ("normal", "no_fault", "watch")
            actual_positive = r.actual_outcome not in ("normal", "no_fault", "no_issue_found")

            if predicted_positive and actual_positive:
                tp += 1
            elif predicted_positive and not actual_positive:
                fp += 1
            elif not predicted_positive and actual_positive:
                fn += 1
            else:
                tn += 1

        fp_rate = fp / max(fp + tn, 1)
        fn_rate = fn / max(fn + tp, 1)
        return fp_rate, fn_rate

    def _emit(
        self,
        trigger_type: str,
        fault_type: Optional[str] = None,
        model_id: str = "",
        asset_id: str = "",
        evidence: Dict[str, Any] = None,
    ) -> RetrainingRequest:
        fp, fn = self._compute_rates(fault_type)

        req = RetrainingRequest(
            trigger_type=trigger_type,
            model_id=model_id,
            asset_id=asset_id,
            fault_type=fault_type,
            false_positive_rate=fp,
            false_negative_rate=fn,
            n_incorrect_recent=self._streak.get(fault_type, 0),
            n_observations_since_train=self._obs_since_train.get(model_id, 0),
            evidence=evidence or {},
        )

        self.pending_requests.append(req)

        # Publish via event bus if wired
        if self._publish:
            try:
                self._publish("retraining.requested", req.to_dict())
            except Exception as e:
                logger.error(f"Failed to publish retraining request: {e}")

        logger.info(
            "Retraining requested: trigger=%s model=%s fault=%s",
            trigger_type, model_id, fault_type,
        )
        return req
