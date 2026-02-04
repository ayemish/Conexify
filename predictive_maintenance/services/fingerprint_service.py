"""
PDM Equipment Fingerprint & Hierarchical Modeling Service

Learns "equipment fingerprints" for hierarchical modeling:
- Global model: general HVAC physics/behavior
- Per-unit adaptation: equipment fingerprint
- Per-climate/building adjustment

This prevents "different install" from being flagged as "fault".
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..core.schemas import (
    EquipmentFingerprint,
    HierarchicalModelConfig,
    OperatingRegime,
    SensorType,
)

logger = logging.getLogger(__name__)


@dataclass
class GlobalModelParameters:
    """Global model parameters learned from fleet"""
    model_id: str = "global_hvacr_v1"
    
    # Per-regime, per-sensor expected relationships
    # Maps (regime, sensor_type) -> {feature: coefficient}
    regime_coefficients: Dict[Tuple[OperatingRegime, SensorType], Dict[str, float]] = field(default_factory=dict)
    
    # Global baselines by sensor type
    sensor_baselines: Dict[SensorType, Dict[str, float]] = field(default_factory=dict)
    
    # Physics constraints
    min_superheat: float = 5.0
    max_superheat: float = 25.0
    min_subcool: float = 5.0
    max_subcool: float = 20.0
    
    # Fleet statistics
    n_units_trained: int = 0
    total_hours_data: float = 0.0
    last_updated: datetime = field(default_factory=datetime.utcnow)


@dataclass
class LocalAdaptation:
    """Per-unit local adaptation parameters"""
    asset_id: str = ""
    
    # Offset from global model per sensor
    sensor_offsets: Dict[SensorType, float] = field(default_factory=dict)
    
    # Scale adjustments
    sensor_scales: Dict[SensorType, float] = field(default_factory=dict)
    
    # Per-regime adjustments
    regime_offsets: Dict[Tuple[OperatingRegime, SensorType], float] = field(default_factory=dict)
    
    # Confidence in adaptation
    adaptation_confidence: float = 0.0
    hours_of_data: float = 0.0
    
    # Installation specifics learned
    typical_load_range: Tuple[float, float] = (0.3, 0.8)
    typical_ambient_range: Tuple[float, float] = (60.0, 95.0)


class EquipmentFingerprintService:
    """
    Learns and applies equipment fingerprints for hierarchical modeling.
    
    Architecture:
    1. Global model learns general HVAC physics/behavior (from fleet)
    2. Per-unit adaptation learns the fingerprint (local)
    3. Per-climate/building adjustment
    
    Prediction: y = w_global * f_global(x) + w_local * f_local(x)
    """
    
    def __init__(self, asset_id: str, config: Optional[HierarchicalModelConfig] = None):
        self.asset_id = asset_id
        self.config = config or HierarchicalModelConfig()
        
        # Global model (would be loaded from fleet training)
        self.global_model = GlobalModelParameters()
        self._initialize_global_model()
        
        # Local adaptation for this asset
        self.local_adaptation = LocalAdaptation(asset_id=asset_id)
        
        # Equipment fingerprint
        self.fingerprint = EquipmentFingerprint(asset_id=asset_id)
        
        # Training data buffer
        self.training_buffer: List[Dict[str, Any]] = []
        self.max_buffer_size = 10000
        
        # Regime observation counts
        self.regime_observations: Dict[OperatingRegime, int] = defaultdict(int)
        
        logger.info(f"EquipmentFingerprintService initialized for asset: {asset_id}")
    
    def _initialize_global_model(self):
        """Initialize global model with physics-based priors"""
        # These would come from fleet training in production
        
        # Suction pressure vs ambient (cooling mode)
        self.global_model.regime_coefficients[(OperatingRegime.STEADY_COOL, SensorType.SUCTION_PRESSURE)] = {
            "intercept": 70.0,  # Base suction pressure (psig for R410A)
            "ambient_temp": 0.3,  # Increase with ambient
            "load_proxy": 5.0,  # Increase with load
        }
        
        # Discharge pressure vs ambient (cooling mode)
        self.global_model.regime_coefficients[(OperatingRegime.STEADY_COOL, SensorType.DISCHARGE_PRESSURE)] = {
            "intercept": 200.0,
            "ambient_temp": 2.5,  # Strong relationship with ambient
            "load_proxy": 20.0,
        }
        
        # Compressor current vs load
        self.global_model.regime_coefficients[(OperatingRegime.STEADY_COOL, SensorType.COMPRESSOR_CURRENT)] = {
            "intercept": 5.0,
            "ambient_temp": 0.05,
            "load_proxy": 8.0,
        }
        
        # Supply air temp
        self.global_model.regime_coefficients[(OperatingRegime.STEADY_COOL, SensorType.SUPPLY_AIR_TEMP)] = {
            "intercept": 55.0,
            "ambient_temp": 0.1,
            "return_air_temp": 0.2,
        }
        
        # Sensor baselines (typical values)
        self.global_model.sensor_baselines = {
            SensorType.SUCTION_PRESSURE: {"mean": 75.0, "std": 15.0},
            SensorType.DISCHARGE_PRESSURE: {"mean": 280.0, "std": 50.0},
            SensorType.SUCTION_LINE_TEMP: {"mean": 55.0, "std": 10.0},
            SensorType.LIQUID_LINE_TEMP: {"mean": 95.0, "std": 15.0},
            SensorType.COMPRESSOR_CURRENT: {"mean": 12.0, "std": 5.0},
            SensorType.SUPPLY_AIR_TEMP: {"mean": 55.0, "std": 5.0},
            SensorType.RETURN_AIR_TEMP: {"mean": 75.0, "std": 5.0},
        }
    
    def predict_global(self, 
                       sensor_type: SensorType,
                       regime: OperatingRegime,
                       context: Dict[str, float]) -> Tuple[float, float]:
        """
        Make prediction using global model only.
        
        Returns (predicted_value, uncertainty)
        """
        key = (regime, sensor_type)
        
        if key in self.global_model.regime_coefficients:
            coeffs = self.global_model.regime_coefficients[key]
            prediction = coeffs.get("intercept", 0.0)
            
            for feature, coef in coeffs.items():
                if feature != "intercept" and feature in context:
                    prediction += coef * context[feature]
            
            # Uncertainty from baseline std
            baseline = self.global_model.sensor_baselines.get(sensor_type, {})
            uncertainty = baseline.get("std", 10.0)
            
            return prediction, uncertainty
        
        # Fall back to baseline
        baseline = self.global_model.sensor_baselines.get(sensor_type, {"mean": 0.0, "std": 10.0})
        return baseline["mean"], baseline["std"]
    
    def predict_local(self,
                      sensor_type: SensorType,
                      regime: OperatingRegime,
                      context: Dict[str, float]) -> Tuple[float, float]:
        """
        Make prediction using local adaptation.
        
        Returns (predicted_value, uncertainty)
        """
        # Start with global prediction
        global_pred, global_unc = self.predict_global(sensor_type, regime, context)
        
        # Apply local offset
        offset = self.local_adaptation.sensor_offsets.get(sensor_type, 0.0)
        
        # Apply regime-specific offset
        regime_key = (regime, sensor_type)
        regime_offset = self.local_adaptation.regime_offsets.get(regime_key, 0.0)
        
        # Apply scale
        scale = self.local_adaptation.sensor_scales.get(sensor_type, 1.0)
        
        local_pred = (global_pred + offset + regime_offset) * scale
        
        # Reduce uncertainty if we have good local adaptation
        local_unc = global_unc * (1.0 - 0.5 * self.local_adaptation.adaptation_confidence)
        
        return local_pred, local_unc
    
    def predict_hierarchical(self,
                              sensor_type: SensorType,
                              regime: OperatingRegime,
                              context: Dict[str, float]) -> Tuple[float, float]:
        """
        Make prediction using hierarchical combination.
        
        Returns (predicted_value, uncertainty)
        """
        global_pred, global_unc = self.predict_global(sensor_type, regime, context)
        local_pred, local_unc = self.predict_local(sensor_type, regime, context)
        
        # Weight by configuration
        w_global = self.config.global_weight
        w_local = self.config.local_weight
        
        # Adjust weights based on local confidence
        if self.local_adaptation.adaptation_confidence < 0.5:
            # Low local confidence - rely more on global
            w_global = 0.7
            w_local = 0.3
        
        combined_pred = w_global * global_pred + w_local * local_pred
        combined_unc = np.sqrt((w_global * global_unc) ** 2 + (w_local * local_unc) ** 2)
        
        return combined_pred, combined_unc
    
    def observe(self,
                sensor_type: SensorType,
                regime: OperatingRegime,
                observed_value: float,
                context: Dict[str, float]):
        """
        Observe a value and update local adaptation.
        """
        # Add to training buffer
        self.training_buffer.append({
            "sensor_type": sensor_type,
            "regime": regime,
            "observed": observed_value,
            "context": context.copy(),
            "timestamp": datetime.utcnow(),
        })
        
        # Limit buffer size
        if len(self.training_buffer) > self.max_buffer_size:
            self.training_buffer = self.training_buffer[-self.max_buffer_size // 2:]
        
        # Track regime observations
        self.regime_observations[regime] += 1
        
        # Incremental update of local adaptation
        self._incremental_update(sensor_type, regime, observed_value, context)
    
    def _incremental_update(self,
                             sensor_type: SensorType,
                             regime: OperatingRegime,
                             observed: float,
                             context: Dict[str, float]):
        """Incrementally update local adaptation parameters"""
        # Get global prediction
        global_pred, _ = self.predict_global(sensor_type, regime, context)
        
        # Compute residual from global
        residual = observed - global_pred
        
        # Update sensor offset with exponential smoothing
        lr = self.config.adaptation_learning_rate
        current_offset = self.local_adaptation.sensor_offsets.get(sensor_type, 0.0)
        new_offset = (1 - lr) * current_offset + lr * residual
        
        # Limit drift from global
        max_drift = self.config.max_adaptation_drift * abs(global_pred + 1)
        new_offset = max(-max_drift, min(max_drift, new_offset))
        
        self.local_adaptation.sensor_offsets[sensor_type] = new_offset
        
        # Update regime-specific offset
        regime_key = (regime, sensor_type)
        current_regime_offset = self.local_adaptation.regime_offsets.get(regime_key, 0.0)
        regime_residual = residual - new_offset
        new_regime_offset = (1 - lr) * current_regime_offset + lr * regime_residual
        self.local_adaptation.regime_offsets[regime_key] = new_regime_offset
        
        # Update hours of data and confidence
        self.local_adaptation.hours_of_data += 1 / 60.0  # Assume ~1 sample/minute
        self.local_adaptation.adaptation_confidence = min(
            1.0,
            self.local_adaptation.hours_of_data / 168.0  # Full confidence after 1 week
        )
    
    def fit_fingerprint(self):
        """
        Fit equipment fingerprint from accumulated data.
        
        Should be called after sufficient data collection.
        """
        if len(self.training_buffer) < self.config.min_samples_for_adaptation:
            logger.warning("Insufficient data for fingerprint fitting")
            return
        
        # Group data by regime and sensor
        regime_sensor_data: Dict[Tuple[OperatingRegime, SensorType], List[Dict]] = defaultdict(list)
        
        for sample in self.training_buffer:
            key = (sample["regime"], sample["sensor_type"])
            regime_sensor_data[key].append(sample)
        
        # Compute baselines per regime
        for key, samples in regime_sensor_data.items():
            regime, sensor_type = key
            values = [s["observed"] for s in samples]
            
            if len(values) >= 20:
                baseline = {
                    "mean": float(np.mean(values)),
                    "std": float(np.std(values)),
                    "n_samples": len(values),
                }
                
                if regime not in self.fingerprint.regime_baselines:
                    self.fingerprint.regime_baselines[regime] = {}
                
                self.fingerprint.regime_baselines[regime][sensor_type.value] = baseline
        
        # Update fingerprint metadata
        self.fingerprint.hours_of_data = self.local_adaptation.hours_of_data
        self.fingerprint.adaptation_confidence = self.local_adaptation.adaptation_confidence
        self.fingerprint.n_regimes_observed = dict(self.regime_observations)
        self.fingerprint.last_updated = datetime.utcnow()
        
        # Compute sensor offsets for fingerprint
        for sensor_type, offset in self.local_adaptation.sensor_offsets.items():
            self.fingerprint.sensor_offsets[sensor_type.value] = offset
        
        logger.info(f"Fitted fingerprint for {self.asset_id} with "
                   f"{len(self.training_buffer)} samples, "
                   f"{self.fingerprint.hours_of_data:.1f} hours of data")
    
    def is_fingerprint_ready(self) -> bool:
        """Check if fingerprint has sufficient data"""
        return self.fingerprint.is_sufficiently_learned()
    
    def get_fingerprint_summary(self) -> Dict[str, Any]:
        """Get summary of equipment fingerprint"""
        return {
            "asset_id": self.asset_id,
            "hours_of_data": self.fingerprint.hours_of_data,
            "adaptation_confidence": self.fingerprint.adaptation_confidence,
            "is_ready": self.is_fingerprint_ready(),
            "n_regimes_observed": dict(self.regime_observations),
            "sensor_offsets": {k: f"{v:.2f}" for k, v in self.fingerprint.sensor_offsets.items()},
            "regime_baselines": {
                regime.value: {
                    sensor: f"{data['mean']:.1f} ± {data['std']:.1f}"
                    for sensor, data in sensors.items()
                }
                for regime, sensors in self.fingerprint.regime_baselines.items()
            },
        }
    
    def compare_to_fleet(self, fleet_fingerprints: List[EquipmentFingerprint]) -> Dict[str, Any]:
        """
        Compare this unit's fingerprint to fleet.
        
        Identifies if unit is "different install" vs "fault".
        """
        if not fleet_fingerprints:
            return {"status": "no_fleet_data"}
        
        # Compute deviation from fleet mean for each sensor
        deviations = {}
        
        for sensor_type_str, local_offset in self.fingerprint.sensor_offsets.items():
            fleet_offsets = []
            for fp in fleet_fingerprints:
                if sensor_type_str in fp.sensor_offsets:
                    fleet_offsets.append(fp.sensor_offsets[sensor_type_str])
            
            if fleet_offsets:
                fleet_mean = np.mean(fleet_offsets)
                fleet_std = np.std(fleet_offsets) + 0.1  # Avoid division by zero
                z_score = (local_offset - fleet_mean) / fleet_std
                
                deviations[sensor_type_str] = {
                    "local_offset": local_offset,
                    "fleet_mean": fleet_mean,
                    "fleet_std": fleet_std,
                    "z_score": z_score,
                    "is_outlier": abs(z_score) > 2.0,
                }
        
        # Determine if unit is just "different install"
        n_outliers = sum(1 for d in deviations.values() if d.get("is_outlier", False))
        
        return {
            "status": "compared",
            "deviations": deviations,
            "n_outlier_sensors": n_outliers,
            "is_unusual_install": n_outliers >= 2,
            "recommendation": "Consider installation-specific factors" if n_outliers >= 2 else "Normal variation",
        }
    
    def transfer_from_similar(self, similar_fingerprint: EquipmentFingerprint):
        """
        Transfer learning from a similar unit's fingerprint.
        
        Used for cold-start when new unit has little data.
        """
        if not similar_fingerprint.is_sufficiently_learned():
            logger.warning("Similar fingerprint not sufficiently learned")
            return
        
        # Transfer sensor offsets with reduced weight
        transfer_weight = self.config.similar_asset_weight
        
        for sensor_str, offset in similar_fingerprint.sensor_offsets.items():
            try:
                sensor_type = SensorType(sensor_str)
                current = self.local_adaptation.sensor_offsets.get(sensor_type, 0.0)
                transferred = (1 - transfer_weight) * current + transfer_weight * offset
                self.local_adaptation.sensor_offsets[sensor_type] = transferred
            except ValueError:
                continue
        
        # Boost adaptation confidence slightly
        self.local_adaptation.adaptation_confidence = min(
            1.0,
            self.local_adaptation.adaptation_confidence + 0.2
        )
        
        logger.info(f"Transferred learning from {similar_fingerprint.asset_id} to {self.asset_id}")
