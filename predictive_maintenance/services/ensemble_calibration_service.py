"""
Ensemble Calibration Service with Conformal Prediction

Implements multi-model ensemble calibration:
1. Conformal prediction for valid prediction intervals
2. Isotonic regression for probability calibration
3. Model weight optimization based on recent performance
4. Distribution-free uncertainty quantification

References:
- Vovk et al., "Algorithmic Learning in a Random World", 2005
- Gneiting & Raftery, "Strictly Proper Scoring Rules", 2007
- Romano et al., "Conformalized Quantile Regression", NeurIPS 2019
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CalibrationPoint:
    """Single calibration data point"""
    point_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Predictions from each model
    model_predictions: Dict[str, float] = field(default_factory=dict)
    model_intervals: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    
    # Ensemble prediction
    ensemble_prediction: float = 0.0
    ensemble_lower: float = 0.0
    ensemble_upper: float = 0.0
    
    # Ground truth (filled in after observation)
    actual_value: Optional[float] = None
    
    # Conformity scores
    conformity_score: Optional[float] = None


@dataclass
class ModelPerformance:
    """Performance tracking for individual models"""
    model_id: str
    
    # Recent error history
    errors: deque = field(default_factory=lambda: deque(maxlen=500))
    absolute_errors: deque = field(default_factory=lambda: deque(maxlen=500))
    
    # Calibration metrics
    coverage_90: float = 0.90
    coverage_80: float = 0.80
    mean_interval_width: float = 0.0
    
    # Performance metrics
    mae: float = 0.0
    rmse: float = 0.0
    bias: float = 0.0
    
    # Adaptive weight
    current_weight: float = 1.0
    
    def update(self, prediction: float, actual: float, interval: Tuple[float, float] = None):
        """Update performance metrics with new observation"""
        error = actual - prediction
        self.errors.append(error)
        self.absolute_errors.append(abs(error))
        
        if len(self.absolute_errors) >= 10:
            self.mae = float(np.mean(list(self.absolute_errors)))
            self.rmse = float(np.sqrt(np.mean([e**2 for e in self.errors])))
            self.bias = float(np.mean(list(self.errors)))
            
            if interval:
                lower, upper = interval
                in_interval = lower <= actual <= upper
                self.mean_interval_width = upper - lower


@dataclass 
class ConformalPredictionSet:
    """Conformal prediction set with coverage guarantee"""
    point_estimate: float
    lower_bound: float
    upper_bound: float
    coverage_level: float
    conformity_threshold: float
    
    # Model contributions
    model_weights: Dict[str, float] = field(default_factory=dict)
    model_predictions: Dict[str, float] = field(default_factory=dict)
    
    # Calibration info
    calibration_set_size: int = 0
    is_valid: bool = True


class EnsembleCalibrationService:
    """
    Calibrates multi-model ensemble predictions using conformal prediction.
    
    Key features:
    1. Distribution-free prediction intervals with coverage guarantees
    2. Adaptive model weighting based on recent performance
    3. Isotonic regression for probability calibration
    4. Online calibration set updates
    """
    
    def __init__(
        self,
        model_ids: List[str],
        coverage_level: float = 0.90,
        calibration_set_size: int = 200,
        weight_decay: float = 0.95,
    ):
        self.model_ids = model_ids
        self.coverage_level = coverage_level
        self.calibration_set_size = calibration_set_size
        self.weight_decay = weight_decay
        
        # Model performance tracking
        self.model_performance: Dict[str, ModelPerformance] = {
            mid: ModelPerformance(model_id=mid, current_weight=1.0 / len(model_ids))
            for mid in model_ids
        }
        
        # Calibration set (conformity scores from past predictions)
        self.conformity_scores: deque = deque(maxlen=calibration_set_size)
        
        # Calibration history
        self.calibration_points: deque = deque(maxlen=1000)
        
        # Isotonic calibration (maps raw confidence → calibrated probability)
        self._isotonic_mapping: List[Tuple[float, float]] = []
        
        logger.info(
            f"EnsembleCalibrationService initialized with {len(model_ids)} models, "
            f"coverage={coverage_level:.0%}"
        )
    
    def predict(
        self,
        model_predictions: Dict[str, float],
        model_intervals: Optional[Dict[str, Tuple[float, float]]] = None,
    ) -> ConformalPredictionSet:
        """
        Generate calibrated ensemble prediction with conformal interval.
        
        Args:
            model_predictions: {model_id: point_prediction}
            model_intervals: {model_id: (lower, upper)} optional
            
        Returns:
            ConformalPredictionSet with calibrated interval
        """
        # Get current model weights
        weights = self._get_normalized_weights()
        
        # Weighted ensemble prediction
        point_estimate = sum(
            weights.get(mid, 0) * pred
            for mid, pred in model_predictions.items()
        )
        
        # Calculate conformity threshold from calibration set
        if len(self.conformity_scores) >= 10:
            sorted_scores = sorted(self.conformity_scores)
            q_index = int(np.ceil((len(sorted_scores) + 1) * self.coverage_level)) - 1
            q_index = max(0, min(q_index, len(sorted_scores) - 1))
            conformity_threshold = sorted_scores[q_index]
        else:
            # Not enough calibration data - use model intervals or default
            conformity_threshold = self._estimate_initial_threshold(model_intervals)
        
        # Prediction interval
        lower_bound = point_estimate - conformity_threshold
        upper_bound = point_estimate + conformity_threshold
        
        # If model intervals provided, use weighted combination as sanity check
        if model_intervals:
            model_lower = sum(
                weights.get(mid, 0) * interval[0]
                for mid, interval in model_intervals.items()
                if mid in weights
            )
            model_upper = sum(
                weights.get(mid, 0) * interval[1]
                for mid, interval in model_intervals.items()
                if mid in weights
            )
            # Take wider interval for safety
            lower_bound = min(lower_bound, model_lower)
            upper_bound = max(upper_bound, model_upper)
        
        return ConformalPredictionSet(
            point_estimate=point_estimate,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            coverage_level=self.coverage_level,
            conformity_threshold=conformity_threshold,
            model_weights=weights,
            model_predictions=model_predictions,
            calibration_set_size=len(self.conformity_scores),
            is_valid=len(self.conformity_scores) >= 10,
        )
    
    def update(
        self,
        model_predictions: Dict[str, float],
        actual_value: float,
        model_intervals: Optional[Dict[str, Tuple[float, float]]] = None,
    ):
        """
        Update calibration with observed ground truth.
        
        This is the key step for conformal prediction:
        - Compute conformity score for this observation
        - Add to calibration set
        - Update model performance metrics
        """
        # Update individual model performance
        for mid, pred in model_predictions.items():
            if mid in self.model_performance:
                interval = model_intervals.get(mid) if model_intervals else None
                self.model_performance[mid].update(pred, actual_value, interval)

        # Recompute ensemble prediction interval from the current calibration state.
        prediction_set = self.predict(model_predictions, model_intervals)
        ensemble_pred = prediction_set.point_estimate
        ensemble_lower = prediction_set.lower_bound
        ensemble_upper = prediction_set.upper_bound
        
        # Conformity score = |actual - prediction|
        conformity_score = abs(actual_value - ensemble_pred)
        self.conformity_scores.append(conformity_score)
        
        # Store calibration point
        point = CalibrationPoint(
            model_predictions=model_predictions,
            model_intervals=model_intervals or {},
            ensemble_prediction=ensemble_pred,
            ensemble_lower=ensemble_lower,
            ensemble_upper=ensemble_upper,
            actual_value=actual_value,
            conformity_score=conformity_score,
        )
        self.calibration_points.append(point)
        
        # Update model weights based on performance
        self._update_weights()
        
        # Update isotonic calibration
        if len(self.calibration_points) % 50 == 0:
            self._update_isotonic_calibration()
    
    def _get_normalized_weights(self) -> Dict[str, float]:
        """Get normalized model weights"""
        total = sum(mp.current_weight for mp in self.model_performance.values())
        if total <= 0:
            total = len(self.model_performance)
        return {
            mid: mp.current_weight / total
            for mid, mp in self.model_performance.items()
        }
    
    def _update_weights(self):
        """Update model weights based on recent performance"""
        for mid, mp in self.model_performance.items():
            # Decay current weight
            mp.current_weight *= self.weight_decay
            
            # Boost based on inverse MAE (better models get higher weight)
            if mp.mae > 0 and len(mp.absolute_errors) >= 10:
                performance_boost = 1.0 / (1.0 + mp.mae)
                mp.current_weight += (1 - self.weight_decay) * performance_boost
            else:
                mp.current_weight += (1 - self.weight_decay) / len(self.model_performance)
            
            # Ensure minimum weight
            mp.current_weight = max(0.01, mp.current_weight)
    
    def _estimate_initial_threshold(
        self,
        model_intervals: Optional[Dict[str, Tuple[float, float]]],
    ) -> float:
        """Estimate initial conformity threshold before calibration"""
        if model_intervals:
            widths = [u - l for l, u in model_intervals.values()]
            return np.mean(widths) / 2 if widths else 10.0
        return 10.0
    
    def _update_isotonic_calibration(self):
        """Update isotonic regression mapping for probability calibration"""
        if len(self.calibration_points) < 30:
            return
        
        # Collect (predicted_confidence, actual_outcome) pairs
        # For binary outcomes (e.g., fault occurred or not)
        pairs = []
        for point in self.calibration_points:
            if point.actual_value is not None:
                # Use conformity score as proxy for calibration
                predicted_conf = 1.0 / (1.0 + point.conformity_score)
                actual_in_interval = point.ensemble_lower <= point.actual_value <= point.ensemble_upper
                pairs.append((predicted_conf, 1.0 if actual_in_interval else 0.0))
        
        if len(pairs) < 20:
            return
        
        # Sort by predicted confidence
        pairs.sort(key=lambda x: x[0])
        
        # Simple isotonic regression (pool adjacent violators)
        self._isotonic_mapping = self._isotonic_regression(pairs)
    
    def _isotonic_regression(
        self,
        pairs: List[Tuple[float, float]],
    ) -> List[Tuple[float, float]]:
        """Pool adjacent violators algorithm for isotonic regression"""
        if not pairs:
            return []
        
        # Initialize with input pairs
        result = list(pairs)
        
        # Pool adjacent violators
        changed = True
        while changed:
            changed = False
            i = 0
            while i < len(result) - 1:
                if result[i][1] > result[i + 1][1]:
                    # Violator - pool them
                    avg = (result[i][1] + result[i + 1][1]) / 2
                    x_avg = (result[i][0] + result[i + 1][0]) / 2
                    result[i] = (x_avg, avg)
                    result.pop(i + 1)
                    changed = True
                else:
                    i += 1
        
        return result
    
    def calibrate_probability(self, raw_probability: float) -> float:
        """Apply isotonic calibration to raw probability"""
        if not self._isotonic_mapping:
            return raw_probability
        
        # Find closest point in isotonic mapping
        for i, (x, y) in enumerate(self._isotonic_mapping):
            if raw_probability <= x:
                if i == 0:
                    return y
                # Linear interpolation
                x_prev, y_prev = self._isotonic_mapping[i - 1]
                if x == x_prev:
                    return y
                t = (raw_probability - x_prev) / (x - x_prev)
                return y_prev + t * (y - y_prev)
        
        return self._isotonic_mapping[-1][1] if self._isotonic_mapping else raw_probability
    
    def get_calibration_metrics(self) -> Dict[str, Any]:
        """Get current calibration metrics"""
        if len(self.calibration_points) < 10:
            return {"status": "insufficient_data", "n_points": len(self.calibration_points)}
        
        # Calculate empirical coverage
        covered = 0
        for point in self.calibration_points:
            if point.actual_value is not None:
                # Check if actual is within expected range
                threshold = np.percentile(
                    list(self.conformity_scores),
                    self.coverage_level * 100,
                ) if self.conformity_scores else 0
                if point.conformity_score <= threshold:
                    covered += 1
        
        n_points = len([p for p in self.calibration_points if p.actual_value is not None])
        empirical_coverage = covered / max(n_points, 1)
        
        return {
            "status": "calibrated",
            "n_calibration_points": len(self.conformity_scores),
            "target_coverage": self.coverage_level,
            "empirical_coverage": empirical_coverage,
            "coverage_gap": empirical_coverage - self.coverage_level,
            "model_weights": self._get_normalized_weights(),
            "model_performance": {
                mid: {
                    "mae": mp.mae,
                    "rmse": mp.rmse,
                    "bias": mp.bias,
                    "weight": mp.current_weight,
                }
                for mid, mp in self.model_performance.items()
            },
        }
    
    def get_model_ranking(self) -> List[Tuple[str, float, float]]:
        """Get models ranked by current performance (id, weight, mae)"""
        ranking = [
            (mid, mp.current_weight, mp.mae)
            for mid, mp in self.model_performance.items()
        ]
        return sorted(ranking, key=lambda x: -x[1])
