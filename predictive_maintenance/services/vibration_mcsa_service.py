"""
Vibration & Motor Current Signature Analysis (MCSA) Service

Implements spectral analysis for mechanical fault detection in HVAC/R:
1. **Vibration analysis** — bearing defect frequencies, envelope analysis
2. **Motor current signature analysis** — broken rotor bars, eccentricity
3. **Acoustic emission** — compressor valve leaks, refrigerant flow noise

Each analysis path produces anomaly scores with explicit false-positive
and false-negative rate tracking.

References:
- Randall, "Vibration-based Condition Monitoring", 2011
- Benbouzid, "A review of induction motors signature analysis", 2000
- ISO 10816-1: Mechanical vibration evaluation
"""

import logging
import math
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ── Bearing geometry constants ───────────────────────────────────────
# These are expressed as multiples of shaft RPM.

@dataclass
class BearingGeometry:
    """Bearing defect frequency ratios (× shaft frequency)."""
    n_balls: int = 8
    ball_diameter_mm: float = 12.0
    pitch_diameter_mm: float = 52.0
    contact_angle_deg: float = 0.0

    @property
    def _cos_alpha(self) -> float:
        return math.cos(math.radians(self.contact_angle_deg))

    @property
    def bpfo_ratio(self) -> float:
        """Ball Pass Frequency Outer race."""
        return (self.n_balls / 2) * (1 - (self.ball_diameter_mm / self.pitch_diameter_mm) * self._cos_alpha)

    @property
    def bpfi_ratio(self) -> float:
        """Ball Pass Frequency Inner race."""
        return (self.n_balls / 2) * (1 + (self.ball_diameter_mm / self.pitch_diameter_mm) * self._cos_alpha)

    @property
    def bsf_ratio(self) -> float:
        """Ball Spin Frequency."""
        bd = self.ball_diameter_mm
        pd = self.pitch_diameter_mm
        ca = self._cos_alpha
        return (pd / (2 * bd)) * (1 - (bd / pd * ca) ** 2)

    @property
    def ftf_ratio(self) -> float:
        """Fundamental Train (cage) Frequency."""
        return 0.5 * (1 - (self.ball_diameter_mm / self.pitch_diameter_mm) * self._cos_alpha)


# ── Output data classes ──────────────────────────────────────────────

@dataclass
class VibrationAnalysisResult:
    """Result from vibration spectral analysis."""
    analysis_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    timestamp: datetime = field(default_factory=datetime.utcnow)
    asset_id: str = ""

    # Overall vibration severity (ISO 10816)
    rms_velocity_mm_s: float = 0.0
    peak_acceleration_g: float = 0.0
    crest_factor: float = 0.0
    severity_class: str = "A"  # A=good, B=acceptable, C=alert, D=danger

    # Bearing defect indicators
    bpfo_amplitude: float = 0.0
    bpfi_amplitude: float = 0.0
    bsf_amplitude: float = 0.0
    bearing_anomaly_score: float = 0.0  # [0,1]

    # Imbalance / misalignment indicators
    imbalance_score: float = 0.0
    misalignment_score: float = 0.0

    # Error model
    false_positive_rate: float = 0.0
    false_negative_rate: float = 0.0
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "timestamp": self.timestamp.isoformat(),
            "asset_id": self.asset_id,
            "rms_velocity_mm_s": round(self.rms_velocity_mm_s, 3),
            "peak_acceleration_g": round(self.peak_acceleration_g, 4),
            "crest_factor": round(self.crest_factor, 2),
            "severity_class": self.severity_class,
            "bearing_anomaly_score": round(self.bearing_anomaly_score, 3),
            "imbalance_score": round(self.imbalance_score, 3),
            "misalignment_score": round(self.misalignment_score, 3),
            "confidence": round(self.confidence, 3),
            "false_positive_rate": round(self.false_positive_rate, 3),
            "false_negative_rate": round(self.false_negative_rate, 3),
        }


@dataclass
class MCSAResult:
    """Result from Motor Current Signature Analysis."""
    analysis_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    timestamp: datetime = field(default_factory=datetime.utcnow)
    asset_id: str = ""

    # Current quality
    current_thd: float = 0.0  # Total Harmonic Distortion
    current_rms_a: float = 0.0

    # Fault indicators
    broken_rotor_bar_score: float = 0.0  # [0,1]
    eccentricity_score: float = 0.0  # [0,1]
    stator_winding_score: float = 0.0  # [0,1]
    bearing_electrical_score: float = 0.0  # [0,1]

    # Sideband analysis (for rotor bar detection)
    lower_sideband_db: float = 0.0
    upper_sideband_db: float = 0.0
    slip_frequency_hz: float = 0.0

    # Error model
    false_positive_rate: float = 0.0
    false_negative_rate: float = 0.0
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "timestamp": self.timestamp.isoformat(),
            "asset_id": self.asset_id,
            "current_thd": round(self.current_thd, 4),
            "broken_rotor_bar_score": round(self.broken_rotor_bar_score, 3),
            "eccentricity_score": round(self.eccentricity_score, 3),
            "stator_winding_score": round(self.stator_winding_score, 3),
            "bearing_electrical_score": round(self.bearing_electrical_score, 3),
            "confidence": round(self.confidence, 3),
            "false_positive_rate": round(self.false_positive_rate, 3),
            "false_negative_rate": round(self.false_negative_rate, 3),
        }


# ── Service ──────────────────────────────────────────────────────────

class VibrationMCSAService:
    """
    Spectral analysis for vibration and motor current signals.

    Designed to receive raw waveform buffers (numpy arrays) at the
    equipment's sampling rate and produce anomaly scores with calibrated
    error models.

    For environments without high-frequency waveforms, the service also
    supports a "summary mode" that works with pre-computed RMS / peak
    values from the BMS.
    """

    def __init__(
        self,
        asset_id: str,
        shaft_rpm: float = 1750.0,
        supply_freq_hz: float = 60.0,
        n_poles: int = 4,
        bearing: Optional[BearingGeometry] = None,
        sample_rate_hz: float = 10000.0,
    ):
        self.asset_id = asset_id
        self.shaft_rpm = shaft_rpm
        self.shaft_freq_hz = shaft_rpm / 60.0
        self.supply_freq_hz = supply_freq_hz
        self.n_poles = n_poles
        self.sync_speed_hz = supply_freq_hz / (n_poles / 2)
        self.bearing = bearing or BearingGeometry()
        self.sample_rate_hz = sample_rate_hz

        # Baseline statistics (built from healthy data)
        self._vib_baseline_rms: deque = deque(maxlen=500)
        self._mcsa_baseline_thd: deque = deque(maxlen=500)
        self._vib_baseline_set = False
        self._mcsa_baseline_set = False

        # Error calibration
        self._vib_predictions: deque = deque(maxlen=200)
        self._mcsa_predictions: deque = deque(maxlen=200)
        self._vib_actuals: deque = deque(maxlen=200)
        self._mcsa_actuals: deque = deque(maxlen=200)

    # ── Vibration Analysis ───────────────────────────────────────────

    def analyze_vibration(
        self,
        waveform: Optional[np.ndarray] = None,
        rms_velocity_mm_s: Optional[float] = None,
        peak_acceleration_g: Optional[float] = None,
        timestamp: Optional[datetime] = None,
    ) -> VibrationAnalysisResult:
        """
        Analyze vibration from a waveform buffer or pre-computed summaries.

        Args:
            waveform: Raw acceleration waveform (1D numpy array)
            rms_velocity_mm_s: Pre-computed RMS velocity (if no waveform)
            peak_acceleration_g: Pre-computed peak acceleration (if no waveform)
        """
        now = timestamp or datetime.utcnow()
        result = VibrationAnalysisResult(timestamp=now, asset_id=self.asset_id)

        if waveform is not None and len(waveform) > 64:
            result = self._analyze_waveform(waveform, result)
        elif rms_velocity_mm_s is not None:
            result.rms_velocity_mm_s = rms_velocity_mm_s
            result.peak_acceleration_g = peak_acceleration_g or 0.0
            result.crest_factor = (
                result.peak_acceleration_g / max(result.rms_velocity_mm_s * 0.1, 1e-6)
            )

        # ISO 10816 severity classification
        result.severity_class = self._classify_severity(result.rms_velocity_mm_s)

        # Update baseline
        self._vib_baseline_rms.append(result.rms_velocity_mm_s)
        if len(self._vib_baseline_rms) >= 50:
            self._vib_baseline_set = True

        # Anomaly scoring against baseline
        if self._vib_baseline_set:
            baseline = np.array(self._vib_baseline_rms)
            mu, sigma = np.mean(baseline), max(np.std(baseline), 1e-6)
            z = (result.rms_velocity_mm_s - mu) / sigma
            result.bearing_anomaly_score = min(max(z / 3.0, 0.0), 1.0)
            result.confidence = min(len(self._vib_baseline_rms) / 200.0, 1.0)

        # Error rates from historical feedback
        fp, fn = self._compute_error_rates(self._vib_predictions, self._vib_actuals)
        result.false_positive_rate = fp
        result.false_negative_rate = fn

        self._vib_predictions.append((now, result.bearing_anomaly_score > 0.5))
        return result

    def _analyze_waveform(
        self, waveform: np.ndarray, result: VibrationAnalysisResult,
    ) -> VibrationAnalysisResult:
        """Full spectral analysis of vibration waveform."""
        n = len(waveform)
        dt = 1.0 / self.sample_rate_hz

        # Time-domain statistics
        rms = float(np.sqrt(np.mean(waveform ** 2)))
        peak = float(np.max(np.abs(waveform)))
        result.rms_velocity_mm_s = rms
        result.peak_acceleration_g = peak / 9.81
        result.crest_factor = peak / max(rms, 1e-9)

        # FFT
        freqs = np.fft.rfftfreq(n, dt)
        spectrum = np.abs(np.fft.rfft(waveform * np.hanning(n))) / n

        # Bearing defect frequency analysis
        shaft_freq = self.shaft_freq_hz
        bpfo_freq = shaft_freq * self.bearing.bpfo_ratio
        bpfi_freq = shaft_freq * self.bearing.bpfi_ratio
        bsf_freq = shaft_freq * self.bearing.bsf_ratio

        result.bpfo_amplitude = self._spectral_amplitude_at(freqs, spectrum, bpfo_freq)
        result.bpfi_amplitude = self._spectral_amplitude_at(freqs, spectrum, bpfi_freq)
        result.bsf_amplitude = self._spectral_amplitude_at(freqs, spectrum, bsf_freq)

        # Bearing anomaly = max normalized defect amplitude
        noise_floor = float(np.median(spectrum)) + 1e-9
        bearing_peaks = [
            result.bpfo_amplitude / noise_floor,
            result.bpfi_amplitude / noise_floor,
            result.bsf_amplitude / noise_floor,
        ]
        result.bearing_anomaly_score = min(max(max(bearing_peaks) / 10.0, 0.0), 1.0)

        # Imbalance: 1× shaft frequency
        amp_1x = self._spectral_amplitude_at(freqs, spectrum, shaft_freq)
        result.imbalance_score = min(amp_1x / (noise_floor * 8.0), 1.0)

        # Misalignment: 2× shaft frequency
        amp_2x = self._spectral_amplitude_at(freqs, spectrum, shaft_freq * 2.0)
        result.misalignment_score = min(amp_2x / (noise_floor * 6.0), 1.0)

        return result

    # ── MCSA Analysis ────────────────────────────────────────────────

    def analyze_motor_current(
        self,
        waveform: Optional[np.ndarray] = None,
        current_rms_a: Optional[float] = None,
        current_thd: Optional[float] = None,
        timestamp: Optional[datetime] = None,
    ) -> MCSAResult:
        """
        Motor Current Signature Analysis.

        Args:
            waveform: Raw current waveform (1D numpy array)
            current_rms_a: Pre-computed RMS current (if no waveform)
            current_thd: Pre-computed THD (if no waveform)
        """
        now = timestamp or datetime.utcnow()
        result = MCSAResult(timestamp=now, asset_id=self.asset_id)

        if waveform is not None and len(waveform) > 64:
            result = self._analyze_current_waveform(waveform, result)
        else:
            result.current_rms_a = current_rms_a or 0.0
            result.current_thd = current_thd or 0.0

        # Anomaly scoring from THD against baseline
        self._mcsa_baseline_thd.append(result.current_thd)
        if len(self._mcsa_baseline_thd) >= 30:
            self._mcsa_baseline_set = True

        if self._mcsa_baseline_set:
            baseline = np.array(self._mcsa_baseline_thd)
            mu, sigma = np.mean(baseline), max(np.std(baseline), 1e-6)
            z = (result.current_thd - mu) / sigma
            result.stator_winding_score = min(max(z / 3.0, 0.0), 1.0)
            result.confidence = min(len(self._mcsa_baseline_thd) / 100.0, 1.0)

        # Error rates
        fp, fn = self._compute_error_rates(self._mcsa_predictions, self._mcsa_actuals)
        result.false_positive_rate = fp
        result.false_negative_rate = fn

        anomalous = max(
            result.broken_rotor_bar_score,
            result.eccentricity_score,
            result.stator_winding_score,
        ) > 0.5
        self._mcsa_predictions.append((now, anomalous))
        return result

    def _analyze_current_waveform(
        self, waveform: np.ndarray, result: MCSAResult,
    ) -> MCSAResult:
        """Full spectral analysis of motor current waveform."""
        n = len(waveform)
        dt = 1.0 / self.sample_rate_hz

        result.current_rms_a = float(np.sqrt(np.mean(waveform ** 2)))

        # FFT
        freqs = np.fft.rfftfreq(n, dt)
        spectrum = np.abs(np.fft.rfft(waveform * np.hanning(n))) / n

        # Fundamental amplitude
        fund_idx = np.argmin(np.abs(freqs - self.supply_freq_hz))
        fund_amp = spectrum[fund_idx] if fund_idx < len(spectrum) else 1e-9

        # THD
        harmonics_power = 0.0
        for h in range(2, 8):
            h_idx = np.argmin(np.abs(freqs - self.supply_freq_hz * h))
            if h_idx < len(spectrum):
                harmonics_power += spectrum[h_idx] ** 2
        result.current_thd = math.sqrt(harmonics_power) / max(fund_amp, 1e-9)

        # Broken rotor bar detection (sidebands at f ± 2·s·f)
        slip = max(1.0 - (self.shaft_freq_hz / self.sync_speed_hz), 0.001)
        result.slip_frequency_hz = slip * self.supply_freq_hz

        sideband_offset = 2.0 * slip * self.supply_freq_hz
        lower_freq = self.supply_freq_hz - sideband_offset
        upper_freq = self.supply_freq_hz + sideband_offset

        lower_amp = self._spectral_amplitude_at(freqs, spectrum, lower_freq)
        upper_amp = self._spectral_amplitude_at(freqs, spectrum, upper_freq)

        result.lower_sideband_db = 20 * math.log10(max(lower_amp / fund_amp, 1e-12))
        result.upper_sideband_db = 20 * math.log10(max(upper_amp / fund_amp, 1e-12))

        # Score: healthy motor has sidebands < -50 dB, broken bar > -35 dB
        sideband_db = max(result.lower_sideband_db, result.upper_sideband_db)
        result.broken_rotor_bar_score = min(max((sideband_db + 50) / 20.0, 0.0), 1.0)

        # Eccentricity: sidebands at f ± f_r (shaft frequency)
        ecc_lower = self._spectral_amplitude_at(freqs, spectrum, self.supply_freq_hz - self.shaft_freq_hz)
        ecc_upper = self._spectral_amplitude_at(freqs, spectrum, self.supply_freq_hz + self.shaft_freq_hz)
        ecc_db = 20 * math.log10(max(max(ecc_lower, ecc_upper) / fund_amp, 1e-12))
        result.eccentricity_score = min(max((ecc_db + 45) / 20.0, 0.0), 1.0)

        return result

    # ── Feedback ─────────────────────────────────────────────────────

    def record_vibration_outcome(self, timestamp: datetime, was_anomalous: bool):
        """Record ground truth for vibration predictions."""
        self._vib_actuals.append((timestamp, was_anomalous))

    def record_mcsa_outcome(self, timestamp: datetime, was_anomalous: bool):
        """Record ground truth for MCSA predictions."""
        self._mcsa_actuals.append((timestamp, was_anomalous))

    # ── Utilities ────────────────────────────────────────────────────

    @staticmethod
    def _spectral_amplitude_at(
        freqs: np.ndarray, spectrum: np.ndarray, target_freq: float, bw_hz: float = 2.0,
    ) -> float:
        """Get peak spectral amplitude near a target frequency."""
        mask = np.abs(freqs - target_freq) < bw_hz
        if not np.any(mask):
            return 0.0
        return float(np.max(spectrum[mask]))

    @staticmethod
    def _classify_severity(rms_vel: float) -> str:
        """ISO 10816-1 severity for small machines (Class I)."""
        if rms_vel < 0.71:
            return "A"  # Good
        if rms_vel < 1.8:
            return "B"  # Acceptable
        if rms_vel < 4.5:
            return "C"  # Alert
        return "D"  # Danger

    @staticmethod
    def _compute_error_rates(predictions: deque, actuals: deque) -> Tuple[float, float]:
        """Compute FP and FN rates from prediction/outcome pairs."""
        if not actuals:
            return 0.0, 0.0

        fp = fn = tp = tn = 0
        for (at, actual) in actuals:
            # Find closest prediction
            closest_pred = None
            closest_dt = float("inf")
            for (pt, pred) in predictions:
                dt = abs((pt - at).total_seconds())
                if dt < closest_dt:
                    closest_dt = dt
                    closest_pred = pred

            if closest_pred is None or closest_dt > 3600:
                continue

            if closest_pred and actual:
                tp += 1
            elif closest_pred and not actual:
                fp += 1
            elif not closest_pred and actual:
                fn += 1
            else:
                tn += 1

        total_neg = fp + tn
        total_pos = fn + tp
        fp_rate = fp / max(total_neg, 1)
        fn_rate = fn / max(total_pos, 1)
        return fp_rate, fn_rate
