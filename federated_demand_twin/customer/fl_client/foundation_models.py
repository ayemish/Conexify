"""
Foundation Model Wrapper for Time Series Forecasting

Provides unified interface for pretrained foundation models:
- TimesFM (Google): General-purpose time series foundation model
- Chronos (Amazon): Probabilistic forecasting via language model tokenization
- TimeGPT (Nixtla): API-based foundation model
- Moirai (Salesforce): Universal forecasting transformer

These models enable:
- Zero-shot forecasting for cold-start SKUs
- Anomaly detection baselines
- Fast bootstrapping before fine-tuning
- Ensemble diversification

Usage:
    wrapper = FoundationModelWrapper(model_type="chronos")
    forecasts = wrapper.forecast(historical_data, horizon=13)
"""

import torch
import torch.nn as nn
import numpy as np
from typing import Dict, List, Tuple, Optional, Any, Union
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class FoundationModelConfig:
    """Configuration for foundation model wrapper"""
    model_type: str = "chronos"  # chronos, timesfm, timegpt, moirai
    model_size: str = "small"    # small, base, large
    
    # Forecasting settings
    prediction_length: int = 13
    context_length: int = 52     # 1 year of weekly data
    
    # Quantile settings
    quantiles: Tuple[float, ...] = (0.1, 0.5, 0.9)
    num_samples: int = 100       # For probabilistic models
    
    # Device settings
    device: str = "auto"         # auto, cpu, cuda, mps
    
    # API settings (for TimeGPT)
    api_key: Optional[str] = None
    api_endpoint: Optional[str] = None
    
    # Fine-tuning settings
    allow_fine_tuning: bool = False
    fine_tune_epochs: int = 5
    fine_tune_lr: float = 1e-5


class BaseFoundationModel(ABC):
    """Abstract base class for foundation model wrappers"""
    
    def __init__(self, config: FoundationModelConfig):
        self.config = config
        self.model = None
        self.tokenizer = None
        self._setup_device()
    
    def _setup_device(self):
        """Setup compute device"""
        if self.config.device == "auto":
            if torch.cuda.is_available():
                self.device = torch.device("cuda")
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                self.device = torch.device("mps")
            else:
                self.device = torch.device("cpu")
        else:
            self.device = torch.device(self.config.device)
        logger.info(f"Using device: {self.device}")
    
    @abstractmethod
    def load_model(self):
        """Load the pretrained model"""
        pass
    
    @abstractmethod
    def forecast(
        self,
        context: np.ndarray,
        prediction_length: Optional[int] = None
    ) -> Dict[str, np.ndarray]:
        """Generate forecasts"""
        pass
    
    @abstractmethod
    def forecast_batch(
        self,
        contexts: List[np.ndarray],
        prediction_length: Optional[int] = None
    ) -> List[Dict[str, np.ndarray]]:
        """Generate forecasts for multiple series"""
        pass


class ChronosWrapper(BaseFoundationModel):
    """
    Wrapper for Amazon Chronos foundation model.
    
    Chronos uses language model architecture with tokenized time series.
    Produces probabilistic forecasts via sampling.
    
    Reference: Ansari et al. (2024) "Chronos: Learning the Language of Time Series"
    """
    
    MODEL_SIZES = {
        "tiny": "amazon/chronos-t5-tiny",
        "mini": "amazon/chronos-t5-mini", 
        "small": "amazon/chronos-t5-small",
        "base": "amazon/chronos-t5-base",
        "large": "amazon/chronos-t5-large"
    }
    
    def __init__(self, config: FoundationModelConfig):
        super().__init__(config)
        self.pipeline = None
    
    def load_model(self):
        """Load Chronos model via transformers pipeline"""
        try:
            from chronos import ChronosPipeline
            
            model_name = self.MODEL_SIZES.get(
                self.config.model_size, 
                self.MODEL_SIZES["small"]
            )
            
            self.pipeline = ChronosPipeline.from_pretrained(
                model_name,
                device_map=str(self.device),
                torch_dtype=torch.float32
            )
            logger.info(f"Loaded Chronos model: {model_name}")
            
        except ImportError:
            logger.warning("Chronos not installed. Using fallback implementation.")
            self._use_fallback = True
    
    def forecast(
        self,
        context: np.ndarray,
        prediction_length: Optional[int] = None
    ) -> Dict[str, np.ndarray]:
        """
        Generate probabilistic forecast for single series.
        
        Args:
            context: Historical values of shape (context_length,)
            prediction_length: Forecast horizon (default from config)
        
        Returns:
            Dict with keys: 'samples', 'mean', 'q10', 'q50', 'q90'
        """
        horizon = prediction_length or self.config.prediction_length
        
        if hasattr(self, '_use_fallback') and self._use_fallback:
            return self._fallback_forecast(context, horizon)
        
        # Prepare context tensor
        context_tensor = torch.tensor(context, dtype=torch.float32).unsqueeze(0)
        
        # Generate samples
        forecast_samples = self.pipeline.predict(
            context_tensor,
            prediction_length=horizon,
            num_samples=self.config.num_samples
        )
        
        # Extract samples and compute quantiles
        samples = forecast_samples[0].numpy()  # (num_samples, horizon)
        
        return {
            'samples': samples,
            'mean': np.mean(samples, axis=0),
            'std': np.std(samples, axis=0),
            'q10': np.percentile(samples, 10, axis=0),
            'q50': np.percentile(samples, 50, axis=0),
            'q90': np.percentile(samples, 90, axis=0),
        }
    
    def forecast_batch(
        self,
        contexts: List[np.ndarray],
        prediction_length: Optional[int] = None
    ) -> List[Dict[str, np.ndarray]]:
        """Generate forecasts for multiple series efficiently"""
        horizon = prediction_length or self.config.prediction_length
        
        if hasattr(self, '_use_fallback') and self._use_fallback:
            return [self._fallback_forecast(ctx, horizon) for ctx in contexts]
        
        # Stack contexts
        context_tensor = torch.tensor(
            np.stack(contexts), 
            dtype=torch.float32
        )
        
        # Batch prediction
        forecast_samples = self.pipeline.predict(
            context_tensor,
            prediction_length=horizon,
            num_samples=self.config.num_samples
        )
        
        # Process each series
        results = []
        for i in range(len(contexts)):
            samples = forecast_samples[i].numpy()
            results.append({
                'samples': samples,
                'mean': np.mean(samples, axis=0),
                'std': np.std(samples, axis=0),
                'q10': np.percentile(samples, 10, axis=0),
                'q50': np.percentile(samples, 50, axis=0),
                'q90': np.percentile(samples, 90, axis=0),
            })
        
        return results
    
    def _fallback_forecast(
        self, 
        context: np.ndarray, 
        horizon: int
    ) -> Dict[str, np.ndarray]:
        """Fallback forecast using simple statistical methods"""
        # Use exponential smoothing as fallback
        alpha = 0.3
        level = context[-1]
        trend = np.mean(np.diff(context[-13:])) if len(context) > 13 else 0
        
        forecasts = []
        for h in range(horizon):
            forecasts.append(level + trend * (h + 1))
        
        mean = np.array(forecasts)
        std = np.std(context[-26:]) if len(context) >= 26 else np.std(context)
        
        # Generate samples
        samples = np.random.normal(
            mean.reshape(1, -1), 
            std, 
            (self.config.num_samples, horizon)
        )
        samples = np.maximum(samples, 0)  # Ensure non-negative
        
        return {
            'samples': samples,
            'mean': mean,
            'std': np.full(horizon, std),
            'q10': np.percentile(samples, 10, axis=0),
            'q50': np.percentile(samples, 50, axis=0),
            'q90': np.percentile(samples, 90, axis=0),
        }


class TimesFMWrapper(BaseFoundationModel):
    """
    Wrapper for Google TimesFM foundation model.
    
    TimesFM is trained on 100B+ time points with patched decoder architecture.
    Supports zero-shot forecasting across domains.
    
    Reference: Das et al. (2024) "A decoder-only foundation model for time-series forecasting"
    """
    
    def __init__(self, config: FoundationModelConfig):
        super().__init__(config)
        self.tfm = None
    
    def load_model(self):
        """Load TimesFM model"""
        try:
            import timesfm
            
            # TimesFM uses different size configurations
            self.tfm = timesfm.TimesFm(
                context_len=self.config.context_length,
                horizon_len=self.config.prediction_length,
                input_patch_len=32,
                output_patch_len=128,
                num_layers=20,
                model_dims=1280,
                backend="gpu" if self.device.type == "cuda" else "cpu"
            )
            self.tfm.load_from_checkpoint()
            logger.info("Loaded TimesFM model")
            
        except ImportError:
            logger.warning("TimesFM not installed. Using fallback implementation.")
            self._use_fallback = True
    
    def forecast(
        self,
        context: np.ndarray,
        prediction_length: Optional[int] = None
    ) -> Dict[str, np.ndarray]:
        """Generate point forecast with uncertainty estimation"""
        horizon = prediction_length or self.config.prediction_length
        
        if hasattr(self, '_use_fallback') and self._use_fallback:
            return self._fallback_forecast(context, horizon)
        
        # TimesFM expects (batch, time) input
        context_input = context.reshape(1, -1)
        
        # Get point forecast
        point_forecast, _ = self.tfm.forecast(
            context_input,
            freq=[0]  # 0 = unknown frequency
        )
        
        mean = point_forecast[0]
        
        # Estimate uncertainty from context volatility
        std = np.std(context[-26:]) if len(context) >= 26 else np.std(context)
        
        # Generate samples for probabilistic output
        samples = np.random.normal(
            mean.reshape(1, -1),
            std * np.sqrt(1 + np.arange(horizon) * 0.1),  # Growing uncertainty
            (self.config.num_samples, horizon)
        )
        samples = np.maximum(samples, 0)
        
        return {
            'samples': samples,
            'mean': mean,
            'std': np.full(horizon, std),
            'q10': np.percentile(samples, 10, axis=0),
            'q50': np.percentile(samples, 50, axis=0),
            'q90': np.percentile(samples, 90, axis=0),
        }
    
    def forecast_batch(
        self,
        contexts: List[np.ndarray],
        prediction_length: Optional[int] = None
    ) -> List[Dict[str, np.ndarray]]:
        """Batch forecasting"""
        horizon = prediction_length or self.config.prediction_length
        
        if hasattr(self, '_use_fallback') and self._use_fallback:
            return [self._fallback_forecast(ctx, horizon) for ctx in contexts]
        
        # Pad/truncate to same length
        max_len = max(len(c) for c in contexts)
        padded = np.zeros((len(contexts), max_len))
        for i, ctx in enumerate(contexts):
            padded[i, -len(ctx):] = ctx
        
        point_forecasts, _ = self.tfm.forecast(
            padded,
            freq=[0] * len(contexts)
        )
        
        results = []
        for i, ctx in enumerate(contexts):
            mean = point_forecasts[i]
            std = np.std(ctx[-26:]) if len(ctx) >= 26 else np.std(ctx)
            
            samples = np.random.normal(
                mean.reshape(1, -1),
                std * np.sqrt(1 + np.arange(horizon) * 0.1),
                (self.config.num_samples, horizon)
            )
            samples = np.maximum(samples, 0)
            
            results.append({
                'samples': samples,
                'mean': mean,
                'std': np.full(horizon, std),
                'q10': np.percentile(samples, 10, axis=0),
                'q50': np.percentile(samples, 50, axis=0),
                'q90': np.percentile(samples, 90, axis=0),
            })
        
        return results
    
    def _fallback_forecast(self, context: np.ndarray, horizon: int) -> Dict[str, np.ndarray]:
        """Same fallback as Chronos"""
        return ChronosWrapper._fallback_forecast(self, context, horizon)


class MoiraiWrapper(BaseFoundationModel):
    """
    Wrapper for Salesforce Moirai foundation model.
    
    Moirai is a universal forecasting transformer supporting:
    - Any-variate forecasting (univariate and multivariate)
    - Any-frequency data
    - Any-horizon predictions
    
    Reference: Woo et al. (2024) "Unified Training of Universal Time Series Forecasting Transformers"
    """
    
    MODEL_SIZES = {
        "small": "Salesforce/moirai-1.0-R-small",
        "base": "Salesforce/moirai-1.0-R-base",
        "large": "Salesforce/moirai-1.0-R-large"
    }
    
    def __init__(self, config: FoundationModelConfig):
        super().__init__(config)
    
    def load_model(self):
        """Load Moirai model"""
        try:
            from uni2ts.model.moirai import MoiraiForecast, MoiraiModule
            
            model_name = self.MODEL_SIZES.get(
                self.config.model_size,
                self.MODEL_SIZES["small"]
            )
            
            self.model = MoiraiForecast.load_from_checkpoint(
                prediction_length=self.config.prediction_length,
                context_length=self.config.context_length,
                patch_size="auto",
                num_samples=self.config.num_samples,
                target_dim=1,
                feat_dynamic_real_dim=0,
                past_feat_dynamic_real_dim=0,
            )
            logger.info(f"Loaded Moirai model: {model_name}")
            
        except ImportError:
            logger.warning("Moirai/uni2ts not installed. Using fallback.")
            self._use_fallback = True
    
    def forecast(
        self,
        context: np.ndarray,
        prediction_length: Optional[int] = None
    ) -> Dict[str, np.ndarray]:
        """Generate forecast"""
        horizon = prediction_length or self.config.prediction_length
        
        if hasattr(self, '_use_fallback') and self._use_fallback:
            return ChronosWrapper._fallback_forecast(self, context, horizon)
        
        # Prepare input
        forecast_samples = self.model(
            past_target=torch.tensor(context).unsqueeze(0).unsqueeze(-1),
            past_observed_target=torch.ones_like(torch.tensor(context)).unsqueeze(0).unsqueeze(-1),
        )
        
        samples = forecast_samples.squeeze(-1).numpy()
        
        return {
            'samples': samples,
            'mean': np.mean(samples, axis=0),
            'std': np.std(samples, axis=0),
            'q10': np.percentile(samples, 10, axis=0),
            'q50': np.percentile(samples, 50, axis=0),
            'q90': np.percentile(samples, 90, axis=0),
        }
    
    def forecast_batch(
        self,
        contexts: List[np.ndarray],
        prediction_length: Optional[int] = None
    ) -> List[Dict[str, np.ndarray]]:
        """Batch forecasting"""
        return [self.forecast(ctx, prediction_length) for ctx in contexts]


class FoundationModelWrapper:
    """
    Unified interface for all foundation models.
    
    Provides:
    - Automatic model selection and loading
    - Consistent output format across models
    - Fallback handling when models unavailable
    - Ensemble capabilities
    
    Example:
        wrapper = FoundationModelWrapper(model_type="chronos", model_size="small")
        wrapper.load()
        forecast = wrapper.forecast(historical_data, horizon=13)
    """
    
    MODEL_CLASSES = {
        "chronos": ChronosWrapper,
        "timesfm": TimesFMWrapper,
        "moirai": MoiraiWrapper,
    }
    
    def __init__(
        self,
        model_type: str = "chronos",
        model_size: str = "small",
        config: Optional[FoundationModelConfig] = None
    ):
        if config is None:
            config = FoundationModelConfig(
                model_type=model_type,
                model_size=model_size
            )
        
        self.config = config
        self._model: Optional[BaseFoundationModel] = None
    
    def load(self):
        """Load the specified foundation model"""
        model_class = self.MODEL_CLASSES.get(self.config.model_type)
        if model_class is None:
            raise ValueError(f"Unknown model type: {self.config.model_type}")
        
        self._model = model_class(self.config)
        self._model.load_model()
        logger.info(f"Foundation model ready: {self.config.model_type}")
    
    def forecast(
        self,
        context: Union[np.ndarray, List[float]],
        prediction_length: Optional[int] = None
    ) -> Dict[str, np.ndarray]:
        """
        Generate forecast for a single time series.
        
        Args:
            context: Historical values
            prediction_length: Forecast horizon
        
        Returns:
            Dict containing: samples, mean, std, q10, q50, q90
        """
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load() first.")
        
        context = np.asarray(context)
        return self._model.forecast(context, prediction_length)
    
    def forecast_batch(
        self,
        contexts: List[np.ndarray],
        prediction_length: Optional[int] = None
    ) -> List[Dict[str, np.ndarray]]:
        """Generate forecasts for multiple series"""
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load() first.")
        
        return self._model.forecast_batch(contexts, prediction_length)
    
    def to_quantile_format(
        self,
        forecast: Dict[str, np.ndarray]
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Convert forecast dict to (q10, q50, q90) tuple"""
        return forecast['q10'], forecast['q50'], forecast['q90']


class FoundationModelEnsemble:
    """
    Ensemble of multiple foundation models for robust forecasting.
    
    Combines predictions from multiple models using:
    - Simple averaging
    - Weighted averaging based on validation performance
    - Quantile combination
    """
    
    def __init__(
        self,
        model_types: List[str] = ["chronos", "timesfm"],
        model_size: str = "small",
        weights: Optional[List[float]] = None
    ):
        self.model_types = model_types
        self.model_size = model_size
        self.weights = weights or [1.0 / len(model_types)] * len(model_types)
        self.models: List[FoundationModelWrapper] = []
    
    def load(self):
        """Load all models in ensemble"""
        for model_type in self.model_types:
            wrapper = FoundationModelWrapper(
                model_type=model_type,
                model_size=self.model_size
            )
            wrapper.load()
            self.models.append(wrapper)
        logger.info(f"Loaded {len(self.models)} foundation models for ensemble")
    
    def forecast(
        self,
        context: np.ndarray,
        prediction_length: Optional[int] = None
    ) -> Dict[str, np.ndarray]:
        """Generate ensemble forecast"""
        forecasts = [
            model.forecast(context, prediction_length) 
            for model in self.models
        ]
        
        # Weighted combination
        horizon = len(forecasts[0]['mean'])
        combined = {
            'mean': np.zeros(horizon),
            'q10': np.zeros(horizon),
            'q50': np.zeros(horizon),
            'q90': np.zeros(horizon),
        }
        
        all_samples = []
        for f, w in zip(forecasts, self.weights):
            combined['mean'] += w * f['mean']
            combined['q10'] += w * f['q10']
            combined['q50'] += w * f['q50']
            combined['q90'] += w * f['q90']
            all_samples.append(f['samples'])
        
        # Combine samples for uncertainty estimation
        combined['samples'] = np.concatenate(all_samples, axis=0)
        combined['std'] = np.std(combined['samples'], axis=0)
        
        return combined
    
    def update_weights(self, validation_errors: List[float]):
        """Update ensemble weights based on validation performance"""
        # Inverse error weighting
        inv_errors = [1.0 / (e + 1e-6) for e in validation_errors]
        total = sum(inv_errors)
        self.weights = [ie / total for ie in inv_errors]
        logger.info(f"Updated ensemble weights: {self.weights}")


def create_foundation_model(
    model_type: str = "chronos",
    model_size: str = "small",
    prediction_length: int = 13,
    context_length: int = 52
) -> FoundationModelWrapper:
    """Factory function for creating foundation model wrapper"""
    config = FoundationModelConfig(
        model_type=model_type,
        model_size=model_size,
        prediction_length=prediction_length,
        context_length=context_length
    )
    wrapper = FoundationModelWrapper(config=config)
    return wrapper


if __name__ == "__main__":
    # Test foundation model wrapper
    print("Testing Foundation Model Wrapper")
    print("=" * 50)
    
    # Create wrapper (will use fallback if Chronos not installed)
    wrapper = create_foundation_model(
        model_type="chronos",
        model_size="small",
        prediction_length=13
    )
    wrapper.load()
    
    # Generate sample data
    np.random.seed(42)
    base_demand = 100
    trend = 0.02
    seasonality = 20 * np.sin(2 * np.pi * np.arange(52) / 52)
    noise = np.random.randn(52) * 10
    
    context = base_demand * (1 + trend) ** np.arange(52) + seasonality + noise
    context = np.maximum(context, 0)
    
    # Generate forecast
    forecast = wrapper.forecast(context, prediction_length=13)
    
    print(f"\nContext length: {len(context)}")
    print(f"Forecast horizon: 13 weeks")
    print(f"\nForecast results:")
    print(f"  Mean:  {forecast['mean'][:5].round(1)} ...")
    print(f"  Q10:   {forecast['q10'][:5].round(1)} ...")
    print(f"  Q50:   {forecast['q50'][:5].round(1)} ...")
    print(f"  Q90:   {forecast['q90'][:5].round(1)} ...")
    print(f"  Samples shape: {forecast['samples'].shape}")
    
    # Test batch forecasting
    contexts = [context, context * 1.2, context * 0.8]
    batch_forecasts = wrapper.forecast_batch(contexts)
    print(f"\nBatch forecast: {len(batch_forecasts)} series processed")
    
    # Test ensemble
    print("\n" + "=" * 50)
    print("Testing Foundation Model Ensemble")
    
    ensemble = FoundationModelEnsemble(
        model_types=["chronos", "timesfm"],
        model_size="small"
    )
    ensemble.load()
    
    ensemble_forecast = ensemble.forecast(context)
    print(f"\nEnsemble forecast:")
    print(f"  Mean:  {ensemble_forecast['mean'][:5].round(1)} ...")
    print(f"  Combined samples: {ensemble_forecast['samples'].shape}")
