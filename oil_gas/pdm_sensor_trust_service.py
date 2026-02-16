"""
PDM Sensor Trust Service

Layer 1 of three-layer inference: "Do I trust this sensor stream right now?"

Outputs per-sensor trust score:
- drift likelihood
- stuck sensor likelihood
- comms integrity
- out-of-range probability

This prevents "bad telemetry = fault alarm" - the primary source of false positives.
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Deque, Dict, List, Optional, Tuple

import numpy as np

from .pdm_schemas import (
    SensorTrustScore,
    SensorType,
)

logger = logging.getLogger(__name__)


@dataclass
class SensorReading:
    """Single sensor reading with metadata"""
    timestamp: datetime
    sensor_id: str
    sensor_type: SensorType
    value: float
    quality_code: int = 0  # 0 = good, non-zero = quality issue
    is_interpolated: bool = False


@dataclass
class SensorSpec:
    """Sensor specification and valid ranges"""
    sensor_type: SensorType
    
    # Physical limits
    min_valid: float = -1000.0
    max_valid: float = 1000.0
    
    # Expected operating range
    min_expected: float = -100.0
    max_expected: float = 100.0
    
    # Rate of change limits (per minute)
    max_rate_of_change: float = 10.0
    
    # Stuck detection
    stuck_variance_threshold: float = 0.01
    stuck_window_samples: int = 30
    
    # Drift detection
    drift_window_hours: float = 24.0
    drift_threshold: float = 5.0  # Units per day


# Default sensor specifications
DEFAULT_SENSOR_SPECS: Dict[SensorType, SensorSpec] = {
    SensorType.SUCTION_PRESSURE: SensorSpec(
        sensor_type=SensorType.SUCTION_PRESSURE,
        min_valid=0.0, max_valid=200.0,
        min_expected=20.0, max_expected=120.0,
        max_rate_of_change=20.0,
        stuck_variance_threshold=0.1,
    ),
    SensorType.DISCHARGE_PRESSURE: SensorSpec(
        sensor_type=SensorType.DISCHARGE_PRESSURE,
        min_valid=0.0, max_valid=600.0,
        min_expected=150.0, max_expected=450.0,
        max_rate_of_change=30.0,
        stuck_variance_threshold=0.5,
    ),
    SensorType.SUCTION_LINE_TEMP: SensorSpec(
        sensor_type=SensorType.SUCTION_LINE_TEMP,
        min_valid=-50.0, max_valid=150.0,
        min_expected=30.0, max_expected=80.0,
        max_rate_of_change=5.0,
        stuck_variance_threshold=0.05,
    ),
    SensorType.LIQUID_LINE_TEMP: SensorSpec(
        sensor_type=SensorType.LIQUID_LINE_TEMP,
        min_valid=-20.0, max_valid=200.0,
        min_expected=70.0, max_expected=130.0,
        max_rate_of_change=5.0,
        stuck_variance_threshold=0.1,
    ),
    SensorType.COMPRESSOR_CURRENT: SensorSpec(
        sensor_type=SensorType.COMPRESSOR_CURRENT,
        min_valid=0.0, max_valid=100.0,
        min_expected=0.0, max_expected=50.0,
        max_rate_of_change=20.0,
        stuck_variance_threshold=0.05,
    ),
    SensorType.COMPRESSOR_POWER: SensorSpec(
        sensor_type=SensorType.COMPRESSOR_POWER,
        min_valid=0.0, max_valid=50.0,
        min_expected=0.0, max_expected=20.0,
        max_rate_of_change=10.0,
        stuck_variance_threshold=0.05,
    ),
    SensorType.RETURN_AIR_TEMP: SensorSpec(
        sensor_type=SensorType.RETURN_AIR_TEMP,
        min_valid=30.0, max_valid=110.0,
        min_expected=60.0, max_expected=85.0,
        max_rate_of_change=2.0,
        stuck_variance_threshold=0.02,
    ),
    SensorType.SUPPLY_AIR_TEMP: SensorSpec(
        sensor_type=SensorType.SUPPLY_AIR_TEMP,
        min_valid=30.0, max_valid=130.0,
        min_expected=45.0, max_expected=95.0,
        max_rate_of_change=3.0,
        stuck_variance_threshold=0.02,
    ),
    SensorType.AMBIENT_TEMP: SensorSpec(
        sensor_type=SensorType.AMBIENT_TEMP,
        min_valid=-40.0, max_valid=130.0,
        min_expected=0.0, max_expected=110.0,
        max_rate_of_change=1.0,
        stuck_variance_threshold=0.01,
    ),
    SensorType.ZONE_TEMP: SensorSpec(
        sensor_type=SensorType.ZONE_TEMP,
        min_valid=40.0, max_valid=100.0,
        min_expected=60.0, max_expected=85.0,
        max_rate_of_change=1.0,
        stuck_variance_threshold=0.02,
    ),
}


class SensorTrustService:
    """
    Evaluates sensor data quality and trustworthiness.
    
    Detects:
    - Stuck sensors (constant readings)
    - Drifting sensors (gradual bias)
    - Out-of-range values
    - Communication issues (gaps, interpolation)
    - Rate-of-change violations
    
    This is LAYER 1 - must pass before behavioral analysis.
    """
    
    def __init__(self, asset_id: str):
        self.asset_id = asset_id
        
        # Per-sensor state
        self.sensor_history: Dict[str, Deque[SensorReading]] = {}
        self.sensor_specs: Dict[str, SensorSpec] = {}
        self.trust_scores: Dict[str, SensorTrustScore] = {}
        
        # Configuration
        self.history_window = 1000  # samples per sensor
        self.min_samples_for_trust = 30
        
        # Baseline tracking for drift detection
        self.sensor_baselines: Dict[str, Dict[str, float]] = {}
        self.baseline_window_hours = 168  # 1 week
        
        logger.info(f"SensorTrustService initialized for asset: {asset_id}")
    
    def register_sensor(self, sensor_id: str, sensor_type: SensorType,
                        spec: Optional[SensorSpec] = None):
        """Register a sensor with its specification"""
        if spec is None:
            spec = DEFAULT_SENSOR_SPECS.get(sensor_type, SensorSpec(sensor_type=sensor_type))
        
        self.sensor_specs[sensor_id] = spec
        self.sensor_history[sensor_id] = deque(maxlen=self.history_window)
        
        logger.debug(f"Registered sensor {sensor_id} of type {sensor_type.value}")
    
    def process_reading(self, reading: SensorReading) -> SensorTrustScore:
        """
        Process a sensor reading and update trust score.
        
        Returns updated trust score for this sensor.
        """
        sensor_id = reading.sensor_id
        
        # Auto-register if needed
        if sensor_id not in self.sensor_history:
            self.register_sensor(sensor_id, reading.sensor_type)
        
        # Add to history
        self.sensor_history[sensor_id].append(reading)
        
        # Compute trust score
        trust = self._compute_trust_score(sensor_id, reading)
        self.trust_scores[sensor_id] = trust
        
        return trust
    
    def _compute_trust_score(self, sensor_id: str, latest: SensorReading) -> SensorTrustScore:
        """Compute comprehensive trust score for a sensor"""
        spec = self.sensor_specs.get(sensor_id)
        history = list(self.sensor_history[sensor_id])
        
        # Initialize component scores
        out_of_range_prob = 0.0
        stuck_likelihood = 0.0
        drift_likelihood = 0.0
        comms_integrity = 1.0
        
        # 1. Out-of-range check
        out_of_range_prob = self._check_out_of_range(latest.value, spec)
        
        # 2. Stuck sensor detection
        if len(history) >= spec.stuck_window_samples:
            stuck_likelihood = self._check_stuck_sensor(history, spec)
        
        # 3. Drift detection
        if len(history) >= self.min_samples_for_trust:
            drift_likelihood = self._check_drift(sensor_id, history, spec)
        
        # 4. Communication integrity
        comms_integrity = self._check_comms_integrity(history, latest)
        
        # 5. Rate of change check
        roc_penalty = 0.0
        if len(history) >= 2:
            roc_penalty = self._check_rate_of_change(history, spec)
        
        # Combine into overall trust score
        # Trust is reduced by each issue type
        trust_score = 1.0
        trust_score -= out_of_range_prob * 0.5  # Out of range is a moderate penalty
        trust_score -= stuck_likelihood * 0.4  # Stuck sensor is concerning
        trust_score -= drift_likelihood * 0.3  # Drift is gradual concern
        trust_score -= (1.0 - comms_integrity) * 0.3  # Comms issues
        trust_score -= roc_penalty * 0.2  # Rate of change violations
        
        trust_score = max(0.0, min(1.0, trust_score))
        
        # Compute variance for diagnostics
        variance_24h = None
        if len(history) >= 100:
            recent_values = [r.value for r in history[-100:]]
            variance_24h = float(np.var(recent_values))
        
        # Count consecutive identical readings
        consecutive_identical = self._count_consecutive_identical(history)
        
        return SensorTrustScore(
            sensor_id=sensor_id,
            sensor_type=latest.sensor_type,
            asset_id=self.asset_id,
            trust_score=trust_score,
            drift_likelihood=drift_likelihood,
            stuck_likelihood=stuck_likelihood,
            comms_integrity=comms_integrity,
            out_of_range_probability=out_of_range_prob,
            last_value=latest.value,
            value_variance_24h=variance_24h,
            missing_data_rate=1.0 - comms_integrity,
            consecutive_identical_readings=consecutive_identical,
            computed_at=datetime.utcnow(),
        )
    
    def _check_out_of_range(self, value: float, spec: SensorSpec) -> float:
        """Check if value is out of valid/expected range"""
        # Hard out of range (physical limits)
        if value < spec.min_valid or value > spec.max_valid:
            return 1.0
        
        # Soft out of range (expected operating range)
        if value < spec.min_expected:
            distance = spec.min_expected - value
            range_size = spec.min_expected - spec.min_valid
            if range_size > 0:
                return min(1.0, distance / range_size * 0.5)
        
        if value > spec.max_expected:
            distance = value - spec.max_expected
            range_size = spec.max_valid - spec.max_expected
            if range_size > 0:
                return min(1.0, distance / range_size * 0.5)
        
        return 0.0
    
    def _check_stuck_sensor(self, history: List[SensorReading], spec: SensorSpec) -> float:
        """Detect stuck sensor (constant or near-constant readings)"""
        recent = history[-spec.stuck_window_samples:]
        values = [r.value for r in recent]
        
        if len(values) < 5:
            return 0.0
        
        variance = np.var(values)
        
        if variance < spec.stuck_variance_threshold:
            # Very low variance suggests stuck sensor
            # Scale likelihood based on how low variance is
            if variance < spec.stuck_variance_threshold * 0.1:
                return 0.95  # Almost certainly stuck
            elif variance < spec.stuck_variance_threshold * 0.5:
                return 0.7
            else:
                return 0.4
        
        return 0.0
    
    def _check_drift(self, sensor_id: str, history: List[SensorReading], 
                     spec: SensorSpec) -> float:
        """Detect sensor drift over time"""
        if len(history) < 100:
            return 0.0
        
        # Compare recent mean to historical baseline
        values = [r.value for r in history]
        
        # Split into baseline (older) and recent
        split_point = len(values) // 2
        baseline_values = values[:split_point]
        recent_values = values[split_point:]
        
        baseline_mean = np.mean(baseline_values)
        recent_mean = np.mean(recent_values)
        baseline_std = np.std(baseline_values)
        
        if baseline_std < 0.01:
            baseline_std = 0.01  # Avoid division by zero
        
        # Drift in standard deviations
        drift_z = abs(recent_mean - baseline_mean) / baseline_std
        
        # Convert to likelihood
        if drift_z > 3.0:
            return 0.9
        elif drift_z > 2.0:
            return 0.6
        elif drift_z > 1.5:
            return 0.3
        
        return 0.0
    
    def _check_comms_integrity(self, history: List[SensorReading], 
                               latest: SensorReading) -> float:
        """Check communication integrity (gaps, interpolation)"""
        if len(history) < 2:
            return 1.0
        
        # Check quality codes
        recent = history[-20:]
        quality_issues = sum(1 for r in recent if r.quality_code != 0)
        interpolated = sum(1 for r in recent if r.is_interpolated)
        
        issue_rate = (quality_issues + interpolated) / len(recent)
        
        # Check for gaps in timestamps
        timestamps = [r.timestamp for r in recent]
        gaps = []
        for i in range(1, len(timestamps)):
            gap = (timestamps[i] - timestamps[i-1]).total_seconds()
            gaps.append(gap)
        
        if gaps:
            median_gap = np.median(gaps)
            if median_gap > 0:
                # Count abnormally large gaps
                large_gaps = sum(1 for g in gaps if g > median_gap * 3)
                gap_issue_rate = large_gaps / len(gaps)
                issue_rate = max(issue_rate, gap_issue_rate)
        
        return 1.0 - min(1.0, issue_rate)
    
    def _check_rate_of_change(self, history: List[SensorReading], 
                               spec: SensorSpec) -> float:
        """Check for physically impossible rate of change"""
        if len(history) < 2:
            return 0.0
        
        recent = history[-10:]
        violations = 0
        
        for i in range(1, len(recent)):
            dt = (recent[i].timestamp - recent[i-1].timestamp).total_seconds()
            if dt <= 0:
                continue
            
            dv = abs(recent[i].value - recent[i-1].value)
            rate_per_minute = dv / (dt / 60.0)
            
            if rate_per_minute > spec.max_rate_of_change:
                violations += 1
        
        return min(1.0, violations / len(recent))
    
    def _count_consecutive_identical(self, history: List[SensorReading]) -> int:
        """Count consecutive identical readings at end of history"""
        if len(history) < 2:
            return 0
        
        count = 1
        last_value = history[-1].value
        
        for i in range(len(history) - 2, -1, -1):
            if abs(history[i].value - last_value) < 0.001:
                count += 1
            else:
                break
        
        return count
    
    def get_trust_score(self, sensor_id: str) -> Optional[SensorTrustScore]:
        """Get current trust score for a sensor"""
        return self.trust_scores.get(sensor_id)
    
    def get_all_trust_scores(self) -> Dict[str, SensorTrustScore]:
        """Get all current trust scores"""
        return self.trust_scores.copy()
    
    def get_untrusted_sensors(self, threshold: float = 0.8) -> List[str]:
        """Get list of sensors below trust threshold"""
        return [
            sensor_id for sensor_id, trust in self.trust_scores.items()
            if trust.trust_score < threshold
        ]
    
    def get_aggregate_trust(self) -> float:
        """Get aggregate trust score across all sensors"""
        if not self.trust_scores:
            return 1.0
        
        scores = [t.trust_score for t in self.trust_scores.values()]
        # Use minimum to be conservative
        return min(scores)
    
    def should_trust_for_analysis(self, sensor_ids: List[str], 
                                   min_trust: float = 0.8) -> Tuple[bool, List[str]]:
        """
        Check if all specified sensors are trusted enough for analysis.
        Returns (is_trusted, list of untrusted sensor ids)
        """
        untrusted = []
        for sensor_id in sensor_ids:
            trust = self.trust_scores.get(sensor_id)
            if trust is None or trust.trust_score < min_trust:
                untrusted.append(sensor_id)
        
        return len(untrusted) == 0, untrusted
    
    def create_sensor_integrity_alert(self, sensor_id: str) -> Optional[Dict[str, Any]]:
        """Create a sensor integrity alert if trust is low"""
        trust = self.trust_scores.get(sensor_id)
        if trust is None:
            return None
        
        if trust.trust_score >= 0.8:
            return None
        
        # Determine primary issue
        issues = []
        if trust.stuck_likelihood > 0.5:
            issues.append(f"Sensor appears stuck (likelihood: {trust.stuck_likelihood:.0%})")
        if trust.drift_likelihood > 0.3:
            issues.append(f"Sensor drift detected (likelihood: {trust.drift_likelihood:.0%})")
        if trust.out_of_range_probability > 0.3:
            issues.append(f"Values out of expected range")
        if trust.comms_integrity < 0.7:
            issues.append(f"Communication issues detected")
        
        return {
            "alert_type": "sensor_integrity",
            "sensor_id": sensor_id,
            "sensor_type": trust.sensor_type.value,
            "trust_score": trust.trust_score,
            "issues": issues,
            "recommended_action": "Verify sensor calibration and wiring; do not dispatch for equipment fault",
            "is_actionable": False,  # Never a truck roll for sensor issues
        }
