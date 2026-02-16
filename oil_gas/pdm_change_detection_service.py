"""
PDM Sequential Change Detection Service

Runs change detection on residual stream using:
- CUSUM (Cumulative Sum)
- GLR (Generalized Likelihood Ratio)
- Bayesian Online Change Point Detection

Produces:
- change score
- estimated onset time
- stability/consistency metrics

This is where false positives drop dramatically - 
we detect persistent changes, not point anomalies.
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Deque, Dict, List, Optional, Tuple

import numpy as np

from .pdm_schemas import (
    ChangePointDetection,
    OperatingRegime,
    ResidualObservation,
    SensorType,
)

logger = logging.getLogger(__name__)


@dataclass
class CUSUMState:
    """State for CUSUM detector"""
    s_pos: float = 0.0  # Positive CUSUM
    s_neg: float = 0.0  # Negative CUSUM
    max_s_pos: float = 0.0  # Running max for positive
    max_s_neg: float = 0.0  # Running max for negative
    n_samples: int = 0
    last_reset: datetime = field(default_factory=datetime.utcnow)


@dataclass
class GLRState:
    """State for Generalized Likelihood Ratio detector"""
    log_likelihood_ratio: float = 0.0
    window_likelihoods: List[float] = field(default_factory=list)
    max_window_size: int = 100
    n_samples: int = 0


@dataclass
class ChangeDetectorConfig:
    """Configuration for change detection"""
    # CUSUM parameters
    cusum_threshold: float = 5.0  # Detection threshold
    cusum_slack: float = 0.5  # Slack parameter (allowable deviation)
    cusum_reset_on_alarm: bool = False
    
    # GLR parameters
    glr_threshold: float = 10.0
    glr_window_size: int = 50
    
    # Persistence requirements
    min_persistence_minutes: float = 30.0
    min_steady_state_regimes: int = 2
    
    # Stability thresholds
    stability_window: int = 20
    min_stability_for_alarm: float = 0.7


class SequentialChangeDetectionService:
    """
    Sequential change detection on residual streams.
    
    Key principle: Detect PERSISTENT changes, not point anomalies.
    This dramatically reduces false positives.
    
    Trigger conditions:
    - Change persists for N minutes
    - Not in transient regime
    - Sensor trust above threshold
    """
    
    def __init__(self, asset_id: str, config: Optional[ChangeDetectorConfig] = None):
        self.asset_id = asset_id
        self.config = config or ChangeDetectorConfig()
        
        # Per-sensor detectors
        self.cusum_states: Dict[str, CUSUMState] = {}
        self.glr_states: Dict[str, GLRState] = {}
        self.detection_states: Dict[str, ChangePointDetection] = {}
        
        # Observation history for analysis
        self.observation_history: Dict[str, Deque[ResidualObservation]] = {}
        self.history_window = 500
        
        # Regime tracking for persistence validation
        self.regime_history: Deque[Tuple[datetime, OperatingRegime]] = deque(maxlen=1000)
        
        # Alarm state
        self.active_alarms: Dict[str, ChangePointDetection] = {}
        
        logger.info(f"SequentialChangeDetectionService initialized for asset: {asset_id}")
    
    def process_observation(self, 
                            obs: ResidualObservation,
                            current_regime: OperatingRegime,
                            sensor_trust: float = 1.0) -> ChangePointDetection:
        """
        Process a residual observation through change detection.
        
        Returns updated change detection state.
        """
        sensor_id = obs.sensor_id
        
        # Initialize states if needed
        if sensor_id not in self.cusum_states:
            self._initialize_sensor(sensor_id, obs.sensor_type)
        
        # Add to history
        if sensor_id not in self.observation_history:
            self.observation_history[sensor_id] = deque(maxlen=self.history_window)
        self.observation_history[sensor_id].append(obs)
        
        # Track regime
        self.regime_history.append((obs.timestamp, current_regime))
        
        # Skip change detection if in transient regime
        is_transient = current_regime in [
            OperatingRegime.STARTUP,
            OperatingRegime.SHUTDOWN,
            OperatingRegime.TRANSIENT,
            OperatingRegime.RECOVERY,
            OperatingRegime.DEFROST,
        ]
        
        # Get z-score for detection (use standardized residual)
        z_score = obs.z_score if obs.z_score is not None else 0.0
        
        # Run CUSUM
        cusum_alarm = False
        if not is_transient and sensor_trust >= 0.7:
            cusum_alarm = self._update_cusum(sensor_id, z_score)
        
        # Run GLR
        glr_alarm = False
        if not is_transient and sensor_trust >= 0.7:
            glr_alarm = self._update_glr(sensor_id, obs)
        
        # Update detection state
        detection = self._update_detection_state(
            sensor_id, obs, current_regime,
            cusum_alarm, glr_alarm, sensor_trust
        )
        
        return detection
    
    def _initialize_sensor(self, sensor_id: str, sensor_type: SensorType):
        """Initialize detector states for a sensor"""
        self.cusum_states[sensor_id] = CUSUMState()
        self.glr_states[sensor_id] = GLRState()
        self.detection_states[sensor_id] = ChangePointDetection(
            asset_id=self.asset_id,
            sensor_type=sensor_type,
        )
    
    def _update_cusum(self, sensor_id: str, z_score: float) -> bool:
        """
        Update CUSUM detector.
        
        CUSUM: S_t = max(0, S_{t-1} + z_t - k)
        where k is the slack parameter.
        
        Returns True if threshold exceeded.
        """
        state = self.cusum_states[sensor_id]
        k = self.config.cusum_slack
        
        # Positive CUSUM (detects positive shift)
        state.s_pos = max(0, state.s_pos + z_score - k)
        
        # Negative CUSUM (detects negative shift)
        state.s_neg = max(0, state.s_neg - z_score - k)
        
        # Track maximums
        state.max_s_pos = max(state.max_s_pos, state.s_pos)
        state.max_s_neg = max(state.max_s_neg, state.s_neg)
        state.n_samples += 1
        
        # Check threshold
        alarm = (state.s_pos > self.config.cusum_threshold or 
                 state.s_neg > self.config.cusum_threshold)
        
        if alarm and self.config.cusum_reset_on_alarm:
            state.s_pos = 0.0
            state.s_neg = 0.0
            state.last_reset = datetime.utcnow()
        
        return alarm
    
    def _update_glr(self, sensor_id: str, obs: ResidualObservation) -> bool:
        """
        Update Generalized Likelihood Ratio detector.
        
        GLR: Compare likelihood under normal vs changed hypothesis.
        
        Returns True if threshold exceeded.
        """
        state = self.glr_states[sensor_id]
        
        # Use log-likelihood from observation
        if obs.log_likelihood is not None:
            state.window_likelihoods.append(obs.log_likelihood)
        
        # Trim to window size
        if len(state.window_likelihoods) > state.max_window_size:
            state.window_likelihoods = state.window_likelihoods[-state.max_window_size:]
        
        state.n_samples += 1
        
        if len(state.window_likelihoods) < 10:
            return False
        
        # Compute GLR statistic
        # Compare recent window to expected under normal
        recent = state.window_likelihoods[-self.config.glr_window_size:]
        mean_ll = np.mean(recent)
        
        # Under null (normal), expect log-likelihood ~ -1 to -2 for Student-t
        # Large negative = unlikely under normal
        expected_ll = -1.5
        
        # GLR statistic: cumulative evidence for change
        glr = -2 * sum(ll - expected_ll for ll in recent)
        state.log_likelihood_ratio = glr
        
        return glr > self.config.glr_threshold
    
    def _update_detection_state(self,
                                 sensor_id: str,
                                 obs: ResidualObservation,
                                 current_regime: OperatingRegime,
                                 cusum_alarm: bool,
                                 glr_alarm: bool,
                                 sensor_trust: float) -> ChangePointDetection:
        """Update overall detection state combining CUSUM and GLR"""
        detection = self.detection_states[sensor_id]
        cusum = self.cusum_states[sensor_id]
        glr = self.glr_states[sensor_id]
        
        # Update CUSUM values in detection state
        detection.cusum_pos = cusum.s_pos
        detection.cusum_neg = cusum.s_neg
        detection.cusum_threshold = self.config.cusum_threshold
        
        # Update GLR values
        detection.glr_statistic = glr.log_likelihood_ratio
        detection.glr_threshold = self.config.glr_threshold
        
        # Compute change score [0, 1]
        cusum_score = max(cusum.s_pos, cusum.s_neg) / (self.config.cusum_threshold * 2)
        glr_score = glr.log_likelihood_ratio / (self.config.glr_threshold * 2)
        change_score = max(0.0, min(1.0, max(cusum_score, glr_score)))
        detection.change_score = change_score
        
        # Track anomaly persistence
        any_alarm = cusum_alarm or glr_alarm
        
        if any_alarm:
            if detection.anomaly_start_time is None:
                detection.anomaly_start_time = obs.timestamp
                detection.estimated_onset_time = obs.timestamp
            
            duration = (obs.timestamp - detection.anomaly_start_time).total_seconds() / 3600.0
            detection.anomaly_duration_hours = duration
            detection.n_anomalous_samples += 1
        else:
            # Reset if no alarm (with hysteresis)
            if detection.n_anomalous_samples > 0:
                # Decay anomaly count
                if detection.change_score < 0.3:
                    detection.n_anomalous_samples = max(0, detection.n_anomalous_samples - 1)
                    if detection.n_anomalous_samples == 0:
                        detection.anomaly_start_time = None
                        detection.anomaly_duration_hours = 0.0
        
        # Count unique regimes observed during anomaly
        if detection.anomaly_start_time:
            detection.n_regimes_observed = self._count_steady_state_regimes(
                detection.anomaly_start_time
            )
        
        # Compute stability score
        detection.stability_score = self._compute_stability(sensor_id)
        
        # Final change detection decision
        detection.change_detected = (
            any_alarm and
            detection.meets_persistence_criteria(
                min_hours=self.config.min_persistence_minutes / 60.0,
                min_regimes=self.config.min_steady_state_regimes
            ) and
            detection.stability_score >= self.config.min_stability_for_alarm and
            sensor_trust >= 0.8
        )
        
        detection.last_updated = datetime.utcnow()
        
        return detection
    
    def _count_steady_state_regimes(self, since: datetime) -> int:
        """Count number of steady-state regime cycles since a timestamp"""
        steady_regimes = {
            OperatingRegime.STEADY_COOL,
            OperatingRegime.STEADY_HEAT,
            OperatingRegime.ECONOMIZER,
        }
        
        regimes_seen = set()
        for ts, regime in self.regime_history:
            if ts >= since and regime in steady_regimes:
                regimes_seen.add(regime)
        
        return len(regimes_seen)
    
    def _compute_stability(self, sensor_id: str) -> float:
        """
        Compute stability score for the detected change.
        
        High stability = consistent deviation, not noise.
        """
        history = self.observation_history.get(sensor_id)
        if not history or len(history) < self.config.stability_window:
            return 0.5
        
        recent = list(history)[-self.config.stability_window:]
        z_scores = [obs.z_score for obs in recent if obs.z_score is not None]
        
        if len(z_scores) < 5:
            return 0.5
        
        # Check consistency of sign
        positive_count = sum(1 for z in z_scores if z > 0)
        negative_count = len(z_scores) - positive_count
        sign_consistency = max(positive_count, negative_count) / len(z_scores)
        
        # Check consistency of magnitude
        magnitudes = [abs(z) for z in z_scores]
        cv = np.std(magnitudes) / (np.mean(magnitudes) + 0.01)  # Coefficient of variation
        magnitude_consistency = 1.0 / (1.0 + cv)  # Lower CV = higher consistency
        
        # Combined stability
        stability = 0.5 * sign_consistency + 0.5 * magnitude_consistency
        
        return float(stability)
    
    def reset_sensor(self, sensor_id: str):
        """Reset all detection state for a sensor"""
        if sensor_id in self.cusum_states:
            self.cusum_states[sensor_id] = CUSUMState()
        if sensor_id in self.glr_states:
            self.glr_states[sensor_id] = GLRState()
        if sensor_id in self.detection_states:
            detection = self.detection_states[sensor_id]
            detection.change_detected = False
            detection.change_score = 0.0
            detection.anomaly_start_time = None
            detection.anomaly_duration_hours = 0.0
            detection.n_anomalous_samples = 0
    
    def get_detection_state(self, sensor_id: str) -> Optional[ChangePointDetection]:
        """Get current detection state for a sensor"""
        return self.detection_states.get(sensor_id)
    
    def get_all_active_changes(self) -> List[ChangePointDetection]:
        """Get all sensors with detected changes"""
        return [
            d for d in self.detection_states.values()
            if d.change_detected
        ]
    
    def get_detection_summary(self) -> Dict[str, Any]:
        """Get summary of all detectors"""
        active = self.get_all_active_changes()
        return {
            "n_sensors_monitored": len(self.detection_states),
            "n_active_changes": len(active),
            "active_sensors": [d.sensor_type.value for d in active],
            "detectors": {
                sensor_id: {
                    "change_score": d.change_score,
                    "cusum_pos": self.cusum_states.get(sensor_id, CUSUMState()).s_pos,
                    "cusum_neg": self.cusum_states.get(sensor_id, CUSUMState()).s_neg,
                    "glr": self.glr_states.get(sensor_id, GLRState()).log_likelihood_ratio,
                    "change_detected": d.change_detected,
                    "duration_hours": d.anomaly_duration_hours,
                }
                for sensor_id, d in self.detection_states.items()
            }
        }
