"""
PDM Residual Error Model Service (Radar-Inspired)

Models residual like radar engineers model the atmosphere:
- System baseline (physics-informed / hybrid model)
- Residual process: conditional distribution given regime and load
- Autocorrelation (stateful), heavy tails, drift
- Change detection on residual (not point anomaly scoring)

Yields alarms that mean:
"The system is no longer behaving like itself under these conditions."
Not: "The temperature is weird."
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Deque, Dict, List, Optional, Tuple

import numpy as np

try:
    from scipy import stats  # type: ignore
except Exception:
    import math

    class _TFallback:
        @staticmethod
        def cdf(x, df):
            return 0.5 * (1 + math.erf(x / math.sqrt(2)))

        @staticmethod
        def logpdf(x, df, scale=1.0):
            var = scale * scale
            return -0.5 * math.log(2 * math.pi * var) - (x ** 2) / (2 * var)

        @staticmethod
        def entropy(df):
            return 0.5 * math.log(2 * math.pi * math.e)

    class _StatsFallback:
        t = _TFallback()

        @staticmethod
        def linregress(x, y):
            if len(x) < 2:
                intercept = float(y[0]) if len(y) else 0.0
                return 0.0, intercept, 0.0, 0.0, 0.0
            slope, intercept = np.polyfit(x, y, 1)
            r_value = float(np.corrcoef(x, y)[0, 1])
            return slope, intercept, r_value, 0.0, 0.0

    stats = _StatsFallback()

from ..core.schemas import (
    OperatingRegime,
    ResidualDistribution,
    ResidualObservation,
    SensorType,
)

logger = logging.getLogger(__name__)


@dataclass
class BehaviorPrediction:
    """Expected value prediction from behavior model"""
    timestamp: datetime
    sensor_type: SensorType
    predicted_value: float
    prediction_std: float
    regime: OperatingRegime
    load_proxy: Optional[float] = None
    model_confidence: float = 1.0


class ResidualErrorModelService:
    """
    Models residual error distribution per regime.
    
    For each regime:
    - Model residual distribution: r_t | regime, load ~ StudentT(μ, σ(load), ν)
    - Add time dependence: AR(1) on residuals
    - Output p-value and log-likelihood for each observation
    
    This gives explicit false alarm probability.
    """
    
    def __init__(self, asset_id: str):
        self.asset_id = asset_id
        
        # Per-regime, per-sensor residual distributions
        self.distributions: Dict[Tuple[OperatingRegime, SensorType], ResidualDistribution] = {}
        
        # Residual history for fitting
        self.residual_history: Dict[Tuple[OperatingRegime, SensorType], Deque[ResidualObservation]] = {}
        self.history_window = 5000  # samples per regime/sensor combo
        
        # AR(1) state tracking
        self.last_residual: Dict[Tuple[OperatingRegime, SensorType], float] = {}
        
        # Fitting configuration
        self.min_samples_for_fit = 100
        self.refit_interval_samples = 500
        self.samples_since_refit: Dict[Tuple[OperatingRegime, SensorType], int] = {}
        
        # Default distribution parameters (before fitting)
        self.default_nu = 4.0  # Student-t degrees of freedom (heavy tails)
        self.default_sigma = 1.0
        
        logger.info(f"ResidualErrorModelService initialized for asset: {asset_id}")
    
    def compute_residual(self, 
                         observed: float,
                         prediction: BehaviorPrediction,
                         sensor_id: str) -> ResidualObservation:
        """
        Compute residual and statistical measures.
        
        Returns ResidualObservation with p-value and log-likelihood.
        """
        regime = prediction.regime
        sensor_type = prediction.sensor_type
        key = (regime, sensor_type)
        
        # Compute raw residual
        residual = observed - prediction.predicted_value
        
        # Get or create distribution
        dist = self._get_distribution(key)
        
        # Adjust for AR(1) if we have previous residual
        adjusted_residual = residual
        if key in self.last_residual and dist.phi != 0:
            expected_from_ar = dist.phi * self.last_residual[key]
            adjusted_residual = residual - expected_from_ar
        
        # Compute sigma adjusted for load (heteroskedasticity)
        sigma = dist.sigma_base
        if prediction.load_proxy is not None:
            sigma = dist.sigma_base + dist.sigma_load_coef * prediction.load_proxy
        sigma = max(sigma, 0.01)  # Prevent division by zero
        
        # Compute z-score (standardized residual)
        z_score = adjusted_residual / sigma
        
        # Compute p-value using Student-t distribution
        # P(|R| >= |r| | normal)
        p_value = 2 * (1 - stats.t.cdf(abs(z_score), df=dist.nu))
        
        # Compute log-likelihood
        log_likelihood = stats.t.logpdf(z_score, df=dist.nu, scale=1.0)
        
        # Create observation
        obs = ResidualObservation(
            timestamp=prediction.timestamp,
            sensor_id=sensor_id,
            sensor_type=sensor_type,
            regime=regime,
            observed=observed,
            predicted=prediction.predicted_value,
            residual=residual,
            load_proxy=prediction.load_proxy,
            z_score=z_score,
            p_value=p_value,
            log_likelihood=log_likelihood,
        )
        
        # Update state
        self.last_residual[key] = residual
        self._add_to_history(key, obs)
        
        # Check if we should refit
        self._maybe_refit(key)
        
        return obs
    
    def _get_distribution(self, key: Tuple[OperatingRegime, SensorType]) -> ResidualDistribution:
        """Get or create distribution for regime/sensor combo"""
        if key not in self.distributions:
            regime, sensor_type = key
            self.distributions[key] = ResidualDistribution(
                regime=regime,
                sensor_type=sensor_type,
                mu=0.0,
                sigma=self.default_sigma,
                nu=self.default_nu,
                sigma_base=self.default_sigma,
                sigma_load_coef=0.0,
                phi=0.0,
            )
        return self.distributions[key]
    
    def _add_to_history(self, key: Tuple[OperatingRegime, SensorType], 
                        obs: ResidualObservation):
        """Add observation to history"""
        if key not in self.residual_history:
            self.residual_history[key] = deque(maxlen=self.history_window)
        
        self.residual_history[key].append(obs)
        
        # Track samples since refit
        if key not in self.samples_since_refit:
            self.samples_since_refit[key] = 0
        self.samples_since_refit[key] += 1
    
    def _maybe_refit(self, key: Tuple[OperatingRegime, SensorType]):
        """Check if distribution should be refit"""
        samples = self.samples_since_refit.get(key, 0)
        history = self.residual_history.get(key, [])
        
        if samples >= self.refit_interval_samples and len(history) >= self.min_samples_for_fit:
            self._fit_distribution(key)
            self.samples_since_refit[key] = 0
    
    def _fit_distribution(self, key: Tuple[OperatingRegime, SensorType]):
        """Fit distribution parameters from history"""
        history = list(self.residual_history.get(key, []))
        if len(history) < self.min_samples_for_fit:
            return
        
        residuals = np.array([obs.residual for obs in history])
        loads = np.array([obs.load_proxy if obs.load_proxy is not None else 0.5 
                         for obs in history])
        
        regime, sensor_type = key
        dist = self.distributions[key]
        
        # Fit location (should be ~0 for well-calibrated model)
        dist.mu = float(np.mean(residuals))
        
        # Fit scale (base sigma)
        dist.sigma_base = float(np.std(residuals))
        if dist.sigma_base < 0.01:
            dist.sigma_base = 0.01
        
        # Fit heteroskedasticity (sigma vs load)
        if np.std(loads) > 0.01:
            try:
                # Simple linear regression of |residual| on load
                abs_residuals = np.abs(residuals - dist.mu)
                slope, intercept, _, _, _ = stats.linregress(loads, abs_residuals)
                if slope > 0:
                    dist.sigma_load_coef = float(slope)
                    dist.sigma_base = float(max(intercept, 0.01))
            except Exception:
                pass
        
        # Fit degrees of freedom (tail heaviness)
        try:
            standardized = (residuals - dist.mu) / dist.sigma_base
            # Use method of moments for nu
            kurtosis = stats.kurtosis(standardized, fisher=True)
            if kurtosis > 0:
                # For Student-t, excess kurtosis = 6/(nu-4) for nu > 4
                # Solving: nu = 4 + 6/kurtosis
                nu_estimate = 4 + 6 / max(kurtosis, 0.1)
                dist.nu = float(max(3.0, min(30.0, nu_estimate)))
            else:
                dist.nu = 30.0  # Approximately Gaussian
        except Exception:
            dist.nu = self.default_nu
        
        # Fit AR(1) coefficient
        if len(residuals) > 10:
            try:
                # Lag-1 autocorrelation
                residuals_centered = residuals - np.mean(residuals)
                autocorr = np.correlate(residuals_centered, residuals_centered, mode='full')
                autocorr = autocorr[len(autocorr)//2:]
                if autocorr[0] > 0:
                    phi = autocorr[1] / autocorr[0]
                    dist.phi = float(max(-0.95, min(0.95, phi)))
            except Exception:
                pass
        
        dist.n_samples_fitted = len(history)
        dist.last_updated = datetime.utcnow()
        
        logger.debug(f"Refit distribution for {regime.value}/{sensor_type.value}: "
                    f"μ={dist.mu:.3f}, σ={dist.sigma_base:.3f}, ν={dist.nu:.1f}, φ={dist.phi:.3f}")
    
    def get_rolling_likelihood(self, 
                               key: Tuple[OperatingRegime, SensorType],
                               window_size: int = 20) -> Optional[float]:
        """Compute rolling log-likelihood over recent observations"""
        history = self.residual_history.get(key)
        if not history or len(history) < window_size:
            return None
        
        recent = list(history)[-window_size:]
        log_likelihoods = [obs.log_likelihood for obs in recent 
                          if obs.log_likelihood is not None]
        
        if not log_likelihoods:
            return None
        
        return float(np.mean(log_likelihoods))
    
    def get_anomaly_score(self,
                          key: Tuple[OperatingRegime, SensorType],
                          window_size: int = 20) -> Optional[float]:
        """
        Compute anomaly score based on rolling likelihood ratio.
        
        Higher score = more anomalous (deviation from learned distribution).
        """
        rolling_ll = self.get_rolling_likelihood(key, window_size)
        if rolling_ll is None:
            return None
        
        dist = self._get_distribution(key)
        
        # Expected log-likelihood under fitted distribution
        # For standardized Student-t, E[log p(x)] depends on nu
        expected_ll = stats.t.entropy(df=dist.nu)
        
        # Anomaly score: negative of normalized log-likelihood
        # More negative LL = more anomalous
        anomaly_score = -(rolling_ll - (-expected_ll)) / expected_ll
        
        return float(max(0, min(1, anomaly_score)))
    
    def get_distribution_summary(self, 
                                  key: Tuple[OperatingRegime, SensorType]) -> Dict[str, Any]:
        """Get summary of fitted distribution"""
        dist = self._get_distribution(key)
        return {
            "regime": key[0].value,
            "sensor_type": key[1].value,
            "mu": dist.mu,
            "sigma_base": dist.sigma_base,
            "sigma_load_coef": dist.sigma_load_coef,
            "nu": dist.nu,
            "phi": dist.phi,
            "n_samples_fitted": dist.n_samples_fitted,
            "last_updated": dist.last_updated.isoformat() if dist.last_updated else None,
        }
    
    def get_all_distributions(self) -> List[Dict[str, Any]]:
        """Get summaries of all fitted distributions"""
        return [self.get_distribution_summary(key) for key in self.distributions.keys()]


class BehaviorModelService:
    """
    Predicts expected values under current regime/context.
    
    This is the "Digital Twin Lite" - NOT a single big LSTM.
    Uses per-regime models with physics-informed constraints.
    
    Recommended models:
    - Gradient boosted trees (XGBoost/LightGBM)
    - or GAMs for interpretability
    - or physics-informed regression
    """
    
    def __init__(self, asset_id: str):
        self.asset_id = asset_id
        
        # Per-regime baselines (simple statistical model as starting point)
        self.regime_baselines: Dict[Tuple[OperatingRegime, SensorType], Dict[str, float]] = {}
        
        # Per-regime model coefficients (for linear/polynomial models)
        self.regime_models: Dict[Tuple[OperatingRegime, SensorType], Dict[str, Any]] = {}
        
        # Training data accumulation
        self.training_data: Dict[Tuple[OperatingRegime, SensorType], List[Dict]] = {}
        self.min_training_samples = 200
        
        logger.info(f"BehaviorModelService initialized for asset: {asset_id}")
    
    def predict(self,
                sensor_type: SensorType,
                regime: OperatingRegime,
                context: Dict[str, float],
                timestamp: datetime) -> BehaviorPrediction:
        """
        Predict expected value for sensor given regime and context.
        
        Context should include:
        - ambient_temp
        - load_proxy (duty cycle, power, etc.)
        - setpoint (if applicable)
        - time features (hour, day)
        """
        key = (regime, sensor_type)
        
        # Get baseline or model
        baseline = self.regime_baselines.get(key)
        model = self.regime_models.get(key)
        
        if model is not None:
            # Use fitted model
            predicted, std = self._apply_model(model, context)
            confidence = min(1.0, model.get("n_samples", 0) / 1000)
        elif baseline is not None:
            # Use simple baseline
            predicted = baseline["mean"]
            std = baseline["std"]
            confidence = 0.5
        else:
            # No model available - return NaN with low confidence
            predicted = np.nan
            std = 10.0
            confidence = 0.0
        
        return BehaviorPrediction(
            timestamp=timestamp,
            sensor_type=sensor_type,
            predicted_value=predicted,
            prediction_std=std,
            regime=regime,
            load_proxy=context.get("load_proxy"),
            model_confidence=confidence,
        )
    
    def _apply_model(self, model: Dict[str, Any], context: Dict[str, float]) -> Tuple[float, float]:
        """Apply fitted model to context"""
        model_type = model.get("type", "baseline")
        
        if model_type == "baseline":
            return model["mean"], model["std"]
        
        elif model_type == "linear":
            # Linear model: y = intercept + sum(coef_i * x_i)
            predicted = model["intercept"]
            for feature, coef in model["coefficients"].items():
                if feature in context:
                    predicted += coef * context[feature]
            return predicted, model["residual_std"]
        
        elif model_type == "polynomial":
            # Polynomial features on ambient_temp
            predicted = model["intercept"]
            ambient = context.get("ambient_temp", 70)
            for degree, coef in enumerate(model["coefficients"]):
                predicted += coef * (ambient ** degree)
            return predicted, model["residual_std"]
        
        return model.get("mean", 0), model.get("std", 1)
    
    def update_with_observation(self,
                                 observed: float,
                                 sensor_type: SensorType,
                                 regime: OperatingRegime,
                                 context: Dict[str, float]):
        """Add observation to training data for model updates"""
        key = (regime, sensor_type)
        
        if key not in self.training_data:
            self.training_data[key] = []
        
        self.training_data[key].append({
            "observed": observed,
            "context": context.copy(),
            "timestamp": datetime.utcnow(),
        })
        
        # Limit storage
        if len(self.training_data[key]) > 10000:
            self.training_data[key] = self.training_data[key][-5000:]
        
        # Update baseline statistics
        self._update_baseline(key)
        
        # Fit model if enough data
        if len(self.training_data[key]) >= self.min_training_samples:
            if len(self.training_data[key]) % 100 == 0:  # Refit periodically
                self._fit_model(key)
    
    def _update_baseline(self, key: Tuple[OperatingRegime, SensorType]):
        """Update simple baseline statistics"""
        data = self.training_data.get(key, [])
        if len(data) < 10:
            return
        
        values = [d["observed"] for d in data[-1000:]]  # Use recent data
        self.regime_baselines[key] = {
            "mean": float(np.mean(values)),
            "std": float(np.std(values)),
            "n_samples": len(values),
        }
    
    def _fit_model(self, key: Tuple[OperatingRegime, SensorType]):
        """Fit a simple linear model for the regime/sensor"""
        data = self.training_data.get(key, [])
        if len(data) < self.min_training_samples:
            return
        
        recent_data = data[-2000:]
        
        # Extract features
        y = np.array([d["observed"] for d in recent_data])
        
        # Try to fit linear model on ambient_temp if available
        ambient_temps = [d["context"].get("ambient_temp") for d in recent_data]
        if all(t is not None for t in ambient_temps):
            X = np.array(ambient_temps)
            
            try:
                slope, intercept, r_value, _, _ = stats.linregress(X, y)
                residuals = y - (intercept + slope * X)
                residual_std = float(np.std(residuals))
                
                self.regime_models[key] = {
                    "type": "linear",
                    "intercept": float(intercept),
                    "coefficients": {"ambient_temp": float(slope)},
                    "residual_std": residual_std,
                    "r_squared": float(r_value ** 2),
                    "n_samples": len(recent_data),
                }
                
                logger.debug(f"Fit linear model for {key[0].value}/{key[1].value}: "
                           f"R²={r_value**2:.3f}")
                return
            except Exception as e:
                logger.warning(f"Failed to fit linear model: {e}")
        
        # Fall back to baseline model
        baseline = self.regime_baselines.get(key, {})
        self.regime_models[key] = {
            "type": "baseline",
            "mean": baseline.get("mean", float(np.mean(y))),
            "std": baseline.get("std", float(np.std(y))),
            "n_samples": len(recent_data),
        }
    
    def get_model_summary(self) -> Dict[str, Any]:
        """Get summary of all fitted models"""
        return {
            "n_regime_sensor_combos": len(self.regime_models),
            "models": {
                f"{k[0].value}/{k[1].value}": {
                    "type": v.get("type"),
                    "n_samples": v.get("n_samples", 0),
                    "r_squared": v.get("r_squared"),
                }
                for k, v in self.regime_models.items()
            }
        }
