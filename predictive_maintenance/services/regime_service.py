"""
PDM Regime Segmentation Service

Labels each timestamp with operating regime - first-class design element.
Uses rules + ML hybrid approach (HMM refinement optional).

Regimes:
- OFF, STARTUP, STEADY_COOL, STEADY_HEAT, ECONOMIZER, DEFROST, TRANSIENT, etc.

Reduces false positives by not comparing apples to oranges.
"""

import logging
from collections import deque, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Deque, Dict, List, Optional, Tuple

import numpy as np

from ..core.schemas import (
    OperatingRegime,
    RegimeSegment,
    RegimeState,
    SensorType,
)

logger = logging.getLogger(__name__)


@dataclass
class TelemetrySnapshot:
    """Point-in-time telemetry for regime detection"""
    timestamp: datetime
    asset_id: str
    
    # Compressor/system status
    compressor_on: bool = False
    compressor_current: Optional[float] = None
    compressor_power: Optional[float] = None
    
    # Fan status
    evap_fan_on: bool = False
    condenser_fan_on: bool = False
    supply_fan_speed: Optional[float] = None
    
    # Temperatures
    suction_temp: Optional[float] = None
    discharge_temp: Optional[float] = None
    supply_air_temp: Optional[float] = None
    return_air_temp: Optional[float] = None
    ambient_temp: Optional[float] = None
    zone_temp: Optional[float] = None
    setpoint: Optional[float] = None
    
    # Pressures
    suction_pressure: Optional[float] = None
    discharge_pressure: Optional[float] = None
    
    # Valves/dampers
    cooling_valve_pct: Optional[float] = None
    heating_valve_pct: Optional[float] = None
    damper_position_pct: Optional[float] = None
    reversing_valve_heat: bool = False  # Heat pump
    
    # Derived
    superheat: Optional[float] = None
    subcool: Optional[float] = None


class RegimeSegmentationService:
    """
    Segments telemetry into operating regimes.
    
    Step 1: Deterministic logic based on:
    - compressor ON/OFF
    - fan ON/OFF
    - valve open %
    - temperature rate-of-change
    
    Step 2 (optional): HMM refinement for smoothing
    """
    
    def __init__(self, asset_id: str):
        self.asset_id = asset_id
        
        # Current state
        self.current_regime: OperatingRegime = OperatingRegime.UNKNOWN
        self.current_state: Optional[RegimeState] = None
        self.regime_start_time: Optional[datetime] = None
        
        # History for transition detection
        self.history_window = 60  # samples
        self.history: Deque[TelemetrySnapshot] = deque(maxlen=self.history_window)
        
        # Segment tracking
        self.active_segment: Optional[RegimeSegment] = None
        self.completed_segments: List[RegimeSegment] = []
        
        # Configuration thresholds
        self.config = RegimeConfig()

        # HMM-style refinement state (optional)
        self.hmm_belief: Dict[OperatingRegime, float] = {}
        self.validation_history: Deque[Dict[str, Any]] = deque(maxlen=1000)
        
        # Statistics per regime
        self.regime_stats: Dict[OperatingRegime, Dict[str, Any]] = {}
        
        logger.info(f"RegimeSegmentationService initialized for asset: {asset_id}")
    
    def classify_regime(self, snapshot: TelemetrySnapshot) -> RegimeState:
        """
        Classify current operating regime from telemetry snapshot.
        Uses deterministic rules as primary method.
        """
        self.history.append(snapshot)
        
        # Determine regime using rule-based logic
        rule_regime, confidence, reason = self._apply_regime_rules(snapshot)
        rule_confidence = confidence
        regime = rule_regime

        # Optional HMM-style refinement
        if self.config.use_hmm_refinement:
            refined_regime, refined_confidence = self._refine_with_hmm(rule_regime, confidence)
            # Use refined regime if confidence improves
            if refined_confidence >= confidence or refined_regime == rule_regime:
                regime = refined_regime
                confidence = refined_confidence
        
        # Record validation trace
        self.validation_history.append({
            "timestamp": snapshot.timestamp,
            "rule_regime": rule_regime,
            "final_regime": regime,
            "rule_confidence": rule_confidence,
            "final_confidence": confidence,
        })
        
        # Check for transitions
        previous_regime = self.current_regime
        is_transition = regime != previous_regime
        
        if is_transition:
            self._handle_regime_transition(previous_regime, regime, snapshot)
        
        # Create state
        duration = 0.0
        if self.regime_start_time:
            duration = (snapshot.timestamp - self.regime_start_time).total_seconds()
        
        state = RegimeState(
            regime=regime,
            confidence=confidence,
            start_time=self.regime_start_time or snapshot.timestamp,
            duration_seconds=duration,
            ambient_temp=snapshot.ambient_temp,
            load_proxy=self._estimate_load(snapshot),
            previous_regime=previous_regime if is_transition else None,
            transition_reason=reason if is_transition else "",
        )
        
        self.current_regime = regime
        self.current_state = state
        
        # Update active segment
        if self.active_segment:
            self.active_segment.n_samples += 1
            if snapshot.ambient_temp:
                if self.active_segment.avg_ambient_temp:
                    # Running average
                    n = self.active_segment.n_samples
                    self.active_segment.avg_ambient_temp = (
                        (self.active_segment.avg_ambient_temp * (n - 1) + snapshot.ambient_temp) / n
                    )
                else:
                    self.active_segment.avg_ambient_temp = snapshot.ambient_temp
        
        return state

    def _refine_with_hmm(self, rule_regime: OperatingRegime, rule_confidence: float) -> Tuple[OperatingRegime, float]:
        """
        Lightweight HMM-style refinement with fixed transition probabilities.
        This smooths regime noise and provides validation metrics.
        """
        regimes = list(OperatingRegime)
        n = len(regimes)
        stay_prob = self.config.hmm_stay_probability
        transition_prob = (1.0 - stay_prob) / max(1, n - 1)

        # Initialize belief if needed
        if not self.hmm_belief:
            self.hmm_belief = {r: 1.0 / n for r in regimes}
            if self.current_regime != OperatingRegime.UNKNOWN:
                for r in regimes:
                    self.hmm_belief[r] = 0.0
                self.hmm_belief[self.current_regime] = 1.0

        # Build transition matrix on the fly (fixed probabilities)
        prior = {}
        for r in regimes:
            prior[r] = 0.0
            for r_prev, prev_prob in self.hmm_belief.items():
                trans = stay_prob if r_prev == r else transition_prob
                prior[r] += prev_prob * trans

        # Emission probabilities based on rule confidence
        rule_confidence = max(self.config.hmm_confidence_floor, min(1.0, rule_confidence))
        emission = {r: (1.0 - rule_confidence) / max(1, n - 1) for r in regimes}
        emission[rule_regime] = rule_confidence

        # Update belief
        unnorm = {r: prior[r] * emission[r] for r in regimes}
        total = sum(unnorm.values()) or 1.0
        self.hmm_belief = {r: unnorm[r] / total for r in regimes}

        # Select refined regime
        refined_regime = max(self.hmm_belief.items(), key=lambda kv: kv[1])[0]
        refined_confidence = float(self.hmm_belief[refined_regime])
        return refined_regime, refined_confidence

    def get_validation_metrics(self) -> Dict[str, Any]:
        """Summarize regime validation and smoothing behavior."""
        if not self.validation_history:
            return {"status": "no_data"}

        total = len(self.validation_history)
        overrides = sum(1 for v in self.validation_history if v["rule_regime"] != v["final_regime"])
        avg_conf = float(np.mean([v["final_confidence"] for v in self.validation_history]))
        return {
            "samples": total,
            "hmm_override_rate": overrides / max(total, 1),
            "avg_final_confidence": avg_conf,
            "use_hmm_refinement": self.config.use_hmm_refinement,
        }
    
    def _apply_regime_rules(self, snapshot: TelemetrySnapshot) -> Tuple[OperatingRegime, float, str]:
        """Apply deterministic regime classification rules"""
        
        # Rule 1: OFF state
        if not snapshot.compressor_on and not snapshot.evap_fan_on:
            if snapshot.supply_fan_speed is None or snapshot.supply_fan_speed < 5:
                return OperatingRegime.OFF, 0.95, "System off"
        
        # Rule 2: DEFROST (refrigeration)
        if self._is_defrost_mode(snapshot):
            return OperatingRegime.DEFROST, 0.90, "Defrost cycle detected"
        
        # Rule 3: STARTUP detection
        if self._is_startup(snapshot):
            return OperatingRegime.STARTUP, 0.85, "Startup transient"
        
        # Rule 4: SHUTDOWN detection
        if self._is_shutdown(snapshot):
            return OperatingRegime.SHUTDOWN, 0.85, "Shutdown transient"
        
        # Rule 5: TRANSIENT / CONTROL_EVENT
        if self._is_transient(snapshot):
            return OperatingRegime.TRANSIENT, 0.75, "Transient detected"
        
        # Rule 6: RECOVERY after setpoint change
        if self._is_recovery(snapshot):
            return OperatingRegime.RECOVERY, 0.80, "Recovery from setpoint change"
        
        # Rule 7: ECONOMIZER mode
        if self._is_economizer(snapshot):
            return OperatingRegime.ECONOMIZER, 0.90, "Economizer mode"
        
        # Rule 8: STEADY_HEAT vs STEADY_COOL
        if snapshot.compressor_on:
            if snapshot.reversing_valve_heat or (snapshot.heating_valve_pct and snapshot.heating_valve_pct > 50):
                return OperatingRegime.STEADY_HEAT, 0.90, "Steady heating"
            else:
                return OperatingRegime.STEADY_COOL, 0.90, "Steady cooling"
        
        # Rule 9: Heating without compressor (gas/electric heat)
        if snapshot.heating_valve_pct and snapshot.heating_valve_pct > 50:
            return OperatingRegime.STEADY_HEAT, 0.85, "Non-compressor heating"
        
        # Default: if fan on but no clear mode
        if snapshot.evap_fan_on or (snapshot.supply_fan_speed and snapshot.supply_fan_speed > 10):
            return OperatingRegime.TRANSIENT, 0.60, "Ventilation only or unknown"
        
        return OperatingRegime.UNKNOWN, 0.50, "Unable to classify"
    
    def _is_defrost_mode(self, snapshot: TelemetrySnapshot) -> bool:
        """Detect defrost cycle"""
        if not snapshot.compressor_on:
            return False
        
        # Defrost indicators:
        # - Reversing valve in heat mode temporarily
        # - Evap fan OFF while compressor ON
        # - Rapid discharge temp rise
        
        if snapshot.reversing_valve_heat and not snapshot.evap_fan_on:
            return True
        
        # Check for rapid temperature change indicating defrost
        if len(self.history) >= 5:
            recent_discharge = [s.discharge_temp for s in list(self.history)[-5:] 
                               if s.discharge_temp is not None]
            if len(recent_discharge) >= 3:
                temp_rise = recent_discharge[-1] - recent_discharge[0]
                if temp_rise > self.config.defrost_temp_rise_threshold:
                    return True
        
        return False
    
    def _is_startup(self, snapshot: TelemetrySnapshot) -> bool:
        """Detect startup transient"""
        if not snapshot.compressor_on:
            return False
        
        # Check if we recently transitioned from OFF
        if len(self.history) < 3:
            return True  # Not enough history, assume startup
        
        recent = list(self.history)[-10:]
        off_count = sum(1 for s in recent if not s.compressor_on)
        
        # If many recent samples were OFF, we're in startup
        if off_count >= len(recent) * 0.5:
            return True
        
        # Check for startup duration
        if self.current_regime == OperatingRegime.STARTUP:
            if self.current_state and self.current_state.duration_seconds < self.config.startup_duration_seconds:
                return True
        
        # Check for unstable pressures (startup signature)
        if len(self.history) >= 5:
            suction_pressures = [s.suction_pressure for s in list(self.history)[-5:] 
                                if s.suction_pressure is not None]
            if len(suction_pressures) >= 3:
                pressure_std = np.std(suction_pressures)
                if pressure_std > self.config.startup_pressure_variance_threshold:
                    return True
        
        return False
    
    def _is_shutdown(self, snapshot: TelemetrySnapshot) -> bool:
        """Detect shutdown transient"""
        if snapshot.compressor_on:
            return False
        
        # Check if we recently had compressor ON
        if len(self.history) < 3:
            return False
        
        recent = list(self.history)[-10:]
        on_count = sum(1 for s in recent if s.compressor_on)
        
        # If many recent samples had compressor ON but now OFF
        if on_count >= len(recent) * 0.3:
            # Check pressure decay (shutdown signature)
            if len(self.history) >= 5:
                suction_pressures = [s.suction_pressure for s in list(self.history)[-5:] 
                                    if s.suction_pressure is not None]
                if len(suction_pressures) >= 3:
                    pressure_trend = suction_pressures[-1] - suction_pressures[0]
                    if abs(pressure_trend) > self.config.shutdown_pressure_decay_threshold:
                        return True
            return True
        
        return False
    
    def _is_transient(self, snapshot: TelemetrySnapshot) -> bool:
        """Detect general transient conditions"""
        if len(self.history) < 5:
            return False
        
        # Check temperature rate of change
        recent_temps = [s.supply_air_temp for s in list(self.history)[-5:] 
                       if s.supply_air_temp is not None]
        if len(recent_temps) >= 3:
            temp_change = abs(recent_temps[-1] - recent_temps[0])
            if temp_change > self.config.transient_temp_change_threshold:
                return True
        
        # Check pressure rate of change
        recent_suction = [s.suction_pressure for s in list(self.history)[-5:] 
                         if s.suction_pressure is not None]
        if len(recent_suction) >= 3:
            pressure_change = abs(recent_suction[-1] - recent_suction[0])
            if pressure_change > self.config.transient_pressure_change_threshold:
                return True
        
        return False
    
    def _is_recovery(self, snapshot: TelemetrySnapshot) -> bool:
        """Detect recovery after setpoint change"""
        if not snapshot.compressor_on:
            return False
        
        if snapshot.zone_temp is None or snapshot.setpoint is None:
            return False
        
        # Large gap between zone temp and setpoint
        gap = abs(snapshot.zone_temp - snapshot.setpoint)
        if gap > self.config.recovery_temp_gap_threshold:
            return True
        
        return False
    
    def _is_economizer(self, snapshot: TelemetrySnapshot) -> bool:
        """Detect economizer mode"""
        # Economizer: damper open, compressor typically off or modulating
        if snapshot.damper_position_pct is None:
            return False
        
        if snapshot.damper_position_pct > self.config.economizer_damper_threshold:
            if not snapshot.compressor_on or (snapshot.compressor_power and 
                                               snapshot.compressor_power < self.config.economizer_compressor_threshold):
                return True
        
        return False
    
    def _estimate_load(self, snapshot: TelemetrySnapshot) -> Optional[float]:
        """Estimate load proxy [0, 1] from telemetry"""
        load_indicators = []
        
        # Compressor power as load proxy
        if snapshot.compressor_power is not None:
            # Normalize to expected range (adjust based on equipment)
            normalized = min(1.0, snapshot.compressor_power / 10.0)  # Assuming 10kW max
            load_indicators.append(normalized)
        
        # Duty cycle from history
        if len(self.history) >= 10:
            on_count = sum(1 for s in self.history if s.compressor_on)
            duty = on_count / len(self.history)
            load_indicators.append(duty)
        
        # Delta T as load proxy
        if snapshot.return_air_temp and snapshot.supply_air_temp:
            delta_t = abs(snapshot.return_air_temp - snapshot.supply_air_temp)
            normalized_dt = min(1.0, delta_t / 20.0)  # Assuming 20°F max delta
            load_indicators.append(normalized_dt)
        
        if load_indicators:
            return np.mean(load_indicators)
        return None
    
    def _handle_regime_transition(self, from_regime: OperatingRegime, 
                                   to_regime: OperatingRegime,
                                   snapshot: TelemetrySnapshot):
        """Handle regime transition - close old segment, start new"""
        # Close active segment
        if self.active_segment:
            self.active_segment.end_time = snapshot.timestamp
            self.completed_segments.append(self.active_segment)
            
            # Keep only recent segments
            if len(self.completed_segments) > 1000:
                self.completed_segments = self.completed_segments[-500:]
        
        # Start new segment
        self.active_segment = RegimeSegment(
            asset_id=self.asset_id,
            regime=to_regime,
            start_time=snapshot.timestamp,
            confidence=0.9,
            n_samples=1,
            avg_ambient_temp=snapshot.ambient_temp,
        )
        
        self.regime_start_time = snapshot.timestamp
        
        logger.debug(f"Regime transition: {from_regime.value} -> {to_regime.value}")
    
    def get_regime_statistics(self) -> Dict[OperatingRegime, Dict[str, Any]]:
        """Get statistics per regime from completed segments"""
        stats = {}
        
        for regime in OperatingRegime:
            regime_segments = [s for s in self.completed_segments if s.regime == regime]
            if not regime_segments:
                continue
            
            durations = []
            for seg in regime_segments:
                if seg.end_time and seg.start_time:
                    dur = (seg.end_time - seg.start_time).total_seconds() / 60.0
                    durations.append(dur)
            
            stats[regime] = {
                "count": len(regime_segments),
                "avg_duration_minutes": np.mean(durations) if durations else 0,
                "total_samples": sum(s.n_samples for s in regime_segments),
            }
        
        return stats
    
    def get_current_state(self) -> Optional[RegimeState]:
        """Get current regime state"""
        return self.current_state
    
    def is_steady_state(self) -> bool:
        """Check if currently in a steady-state regime"""
        return self.current_regime in [
            OperatingRegime.STEADY_COOL,
            OperatingRegime.STEADY_HEAT,
            OperatingRegime.ECONOMIZER,
        ]
    
    def get_recent_regimes(self, n_segments: int = 10) -> List[RegimeSegment]:
        """Get recent regime segments"""
        segments = self.completed_segments[-n_segments:]
        if self.active_segment:
            segments = segments + [self.active_segment]
        return segments


@dataclass
class RegimeConfig:
    """Configuration thresholds for regime detection"""
    # Startup
    startup_duration_seconds: float = 300.0  # 5 minutes
    startup_pressure_variance_threshold: float = 5.0  # psi
    
    # Shutdown
    shutdown_pressure_decay_threshold: float = 10.0  # psi
    
    # Defrost
    defrost_temp_rise_threshold: float = 20.0  # °F
    
    # Transient
    transient_temp_change_threshold: float = 5.0  # °F in window
    transient_pressure_change_threshold: float = 8.0  # psi in window
    
    # Recovery
    recovery_temp_gap_threshold: float = 3.0  # °F
    
    # Economizer
    economizer_damper_threshold: float = 70.0  # % open
    economizer_compressor_threshold: float = 1.0  # kW

    # HMM-style refinement
    use_hmm_refinement: bool = False
    hmm_stay_probability: float = 0.85
    hmm_confidence_floor: float = 0.2
