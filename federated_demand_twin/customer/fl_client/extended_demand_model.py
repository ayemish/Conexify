"""
Extended Demand Forecasting Model with Endogenous Variable Support

Extends the base NBEATS model to support:
- Dynamic covariate dimensions (base + endogenous)
- Uncertainty quantification from Bayesian layers
- FL-compatible parameter exchange
- Integration with iQueue agent beliefs
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import Tuple, List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ExtendedModelConfig:
    """Configuration for extended demand forecasting model"""
    # Input configuration
    lookback_weeks: int = 26
    forecast_horizon: int = 13
    
    # Covariate configuration
    base_covariates: int = 5      # price, promo, seasonality (sin/cos), trend
    endogenous_covariates: int = 8  # basket, penetration, items, size + trends + confidence
    
    # Architecture
    hidden_dim: int = 128
    num_blocks: int = 3
    num_layers_per_block: int = 2
    dropout: float = 0.1
    
    # Bayesian settings
    use_bayesian: bool = True
    prior_std: float = 1.0
    
    # Quantile forecasting
    quantiles: Tuple[float, ...] = (0.1, 0.5, 0.9)
    
    # Training
    learning_rate: float = 0.001
    kl_weight: float = 0.01
    
    @property
    def total_covariates(self) -> int:
        return self.base_covariates + self.endogenous_covariates


class BayesianLinear(nn.Module):
    """Linear layer with Bayesian weight distributions"""
    
    def __init__(self, in_features: int, out_features: int, prior_std: float = 1.0):
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.prior_std = prior_std
        
        # Weight mean and log-variance
        self.weight_mu = nn.Parameter(torch.Tensor(out_features, in_features))
        self.weight_logvar = nn.Parameter(torch.Tensor(out_features, in_features))
        
        # Bias mean and log-variance
        self.bias_mu = nn.Parameter(torch.Tensor(out_features))
        self.bias_logvar = nn.Parameter(torch.Tensor(out_features))
        
        self.reset_parameters()
    
    def reset_parameters(self):
        nn.init.kaiming_uniform_(self.weight_mu, a=np.sqrt(5))
        nn.init.constant_(self.weight_logvar, -5.0)
        nn.init.zeros_(self.bias_mu)
        nn.init.constant_(self.bias_logvar, -5.0)
    
    def forward(self, x: torch.Tensor, sample: bool = True) -> torch.Tensor:
        if sample and self.training:
            weight_std = torch.exp(0.5 * self.weight_logvar)
            weight = self.weight_mu + weight_std * torch.randn_like(weight_std)
            
            bias_std = torch.exp(0.5 * self.bias_logvar)
            bias = self.bias_mu + bias_std * torch.randn_like(bias_std)
        else:
            weight = self.weight_mu
            bias = self.bias_mu
        
        return F.linear(x, weight, bias)
    
    def kl_divergence(self) -> torch.Tensor:
        """KL divergence from prior N(0, prior_std)"""
        prior_var = self.prior_std ** 2
        
        kl_weight = 0.5 * torch.sum(
            (torch.exp(self.weight_logvar) + self.weight_mu**2) / prior_var
            - 1 - self.weight_logvar + np.log(prior_var)
        )
        
        kl_bias = 0.5 * torch.sum(
            (torch.exp(self.bias_logvar) + self.bias_mu**2) / prior_var
            - 1 - self.bias_logvar + np.log(prior_var)
        )
        
        return kl_weight + kl_bias


class ExtendedNBEATSBlock(nn.Module):
    """NBEATS block with optional Bayesian layers"""
    
    def __init__(
        self,
        lookback: int,
        forecast_horizon: int,
        hidden_dim: int,
        dropout: float = 0.1,
        use_bayesian: bool = True,
        prior_std: float = 1.0
    ):
        super().__init__()
        self.lookback = lookback
        self.forecast_horizon = forecast_horizon
        self.use_bayesian = use_bayesian
        
        if use_bayesian:
            self.fc1 = BayesianLinear(lookback, hidden_dim, prior_std)
            self.fc2 = BayesianLinear(hidden_dim, hidden_dim, prior_std)
            self.fc3 = BayesianLinear(hidden_dim, lookback, prior_std)
        else:
            self.fc1 = nn.Linear(lookback, hidden_dim)
            self.fc2 = nn.Linear(hidden_dim, hidden_dim)
            self.fc3 = nn.Linear(hidden_dim, lookback)
        
        self.dropout = nn.Dropout(dropout)
        self.norm = nn.LayerNorm(lookback)
        
        self.backcast_fc = nn.Linear(lookback, lookback)
        self.forecast_fc = nn.Linear(lookback, forecast_horizon)
    
    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        residual = x
        
        if self.use_bayesian:
            h = F.relu(self.fc1(x, sample=self.training))
            h = self.dropout(h)
            h = F.relu(self.fc2(h, sample=self.training))
            h = self.dropout(h)
            h = self.fc3(h, sample=self.training)
        else:
            h = F.relu(self.fc1(x))
            h = self.dropout(h)
            h = F.relu(self.fc2(h))
            h = self.dropout(h)
            h = self.fc3(h)
        
        h = self.norm(h + residual)
        
        backcast = self.backcast_fc(h)
        forecast = self.forecast_fc(h)
        
        return backcast, forecast
    
    def kl_divergence(self) -> torch.Tensor:
        if not self.use_bayesian:
            return torch.tensor(0.0)
        
        return self.fc1.kl_divergence() + self.fc2.kl_divergence() + self.fc3.kl_divergence()


class EndogenousCovariateEncoder(nn.Module):
    """
    Encoder for endogenous covariates from iQueue agents.
    
    Handles:
    - Basket dynamics (baskets, penetration, items/basket, size/item)
    - Trend signals
    - Confidence weighting
    """
    
    def __init__(
        self,
        lookback: int,
        endogenous_dim: int,
        hidden_dim: int,
        output_dim: int
    ):
        super().__init__()
        self.lookback = lookback
        self.endogenous_dim = endogenous_dim
        
        # Separate encoders for different endogenous types
        # Levels (basket, penetration, items, size)
        self.level_encoder = nn.Sequential(
            nn.Linear(lookback * 4, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, hidden_dim // 2)
        )
        
        # Trends (4 trend signals)
        self.trend_encoder = nn.Sequential(
            nn.Linear(lookback * 4, hidden_dim // 2),
            nn.Tanh()  # Trends can be positive or negative
        )
        
        # Combine and project
        self.combiner = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, output_dim)
        )
        
        # Confidence gate (uses last covariate as confidence)
        self.confidence_gate = nn.Sequential(
            nn.Linear(lookback, 1),
            nn.Sigmoid()
        )
    
    def forward(self, endogenous: torch.Tensor) -> torch.Tensor:
        """
        Args:
            endogenous: (batch, lookback, endogenous_dim)
                Dimensions: [penetration, items, size, basket_trend, 
                            pen_trend, items_trend, size_trend, confidence]
        
        Returns:
            encoded: (batch, output_dim)
        """
        batch_size = endogenous.shape[0]
        
        # Split endogenous variables
        levels = endogenous[:, :, :4]  # penetration, items, size, (implicit basket from levels)
        trends = endogenous[:, :, 3:7] if endogenous.shape[2] > 3 else endogenous[:, :, :4]
        confidence = endogenous[:, :, -1] if endogenous.shape[2] > 7 else torch.ones(batch_size, self.lookback)
        
        # Encode
        level_flat = levels.reshape(batch_size, -1)
        level_encoded = self.level_encoder(level_flat)
        
        trend_flat = trends.reshape(batch_size, -1)
        trend_encoded = self.trend_encoder(trend_flat)
        
        # Combine
        combined = torch.cat([level_encoded, trend_encoded], dim=-1)
        output = self.combiner(combined)
        
        # Apply confidence gating
        conf_weight = self.confidence_gate(confidence)
        output = output * conf_weight
        
        return output


class ExtendedDemandForecastModel(nn.Module):
    """
    Extended NBEATS model with endogenous variable support.
    
    Features:
    - Separate encoders for base and endogenous covariates
    - Bayesian weight distributions for uncertainty
    - FL-compatible parameter extraction
    """
    
    def __init__(self, config: ExtendedModelConfig):
        super().__init__()
        self.config = config
        
        # Base covariate encoder (price, promo, seasonality)
        self.base_encoder = nn.Sequential(
            nn.Linear(config.base_covariates * config.lookback_weeks, config.hidden_dim),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.hidden_dim, config.lookback_weeks)
        )
        
        # Endogenous covariate encoder (from iQueue agents)
        self.endogenous_encoder = EndogenousCovariateEncoder(
            lookback=config.lookback_weeks,
            endogenous_dim=config.endogenous_covariates,
            hidden_dim=config.hidden_dim,
            output_dim=config.lookback_weeks
        )
        
        # NBEATS blocks
        self.blocks = nn.ModuleList([
            ExtendedNBEATSBlock(
                lookback=config.lookback_weeks,
                forecast_horizon=config.forecast_horizon,
                hidden_dim=config.hidden_dim,
                dropout=config.dropout,
                use_bayesian=config.use_bayesian,
                prior_std=config.prior_std
            )
            for _ in range(config.num_blocks)
        ])
        
        # Quantile head
        self.quantile_fc1 = nn.Linear(config.forecast_horizon, config.hidden_dim)
        self.quantile_fc2 = nn.Linear(
            config.hidden_dim, 
            config.forecast_horizon * len(config.quantiles)
        )
        
        self.num_quantiles = len(config.quantiles)
    
    def forward(
        self,
        demand_history: torch.Tensor,
        base_covariates: Optional[torch.Tensor] = None,
        endogenous_covariates: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass with separate covariate handling.
        
        Args:
            demand_history: (batch, lookback_weeks)
            base_covariates: (batch, lookback_weeks, base_covariates) - optional
            endogenous_covariates: (batch, lookback_weeks, endogenous_covariates) - optional
        
        Returns:
            quantile_forecasts: (batch, horizon, num_quantiles)
            point_forecast: (batch, horizon)
        """
        batch_size = demand_history.shape[0]
        x = demand_history
        
        # Encode base covariates
        if base_covariates is not None:
            base_flat = base_covariates.view(batch_size, -1)
            base_encoded = self.base_encoder(base_flat)
            x = x + base_encoded
        
        # Encode endogenous covariates
        if endogenous_covariates is not None:
            endogenous_encoded = self.endogenous_encoder(endogenous_covariates)
            x = x + endogenous_encoded
        
        # Process through NBEATS blocks
        residual = x
        forecast_sum = torch.zeros(batch_size, self.config.forecast_horizon, device=x.device)
        
        for block in self.blocks:
            backcast, forecast = block(residual)
            residual = residual - backcast
            forecast_sum = forecast_sum + forecast
        
        # Generate quantile forecasts
        h = F.relu(self.quantile_fc1(forecast_sum))
        q_out = self.quantile_fc2(h)
        q_out = q_out.view(batch_size, self.config.forecast_horizon, self.num_quantiles)
        
        # Ensure quantile ordering
        q_out = F.softplus(q_out)
        q_out = torch.cumsum(q_out, dim=-1)
        
        # Point forecast is median
        median_idx = list(self.config.quantiles).index(0.5)
        point_forecast = q_out[:, :, median_idx]
        
        return q_out, point_forecast
    
    def kl_divergence(self) -> torch.Tensor:
        """Total KL divergence for all Bayesian layers"""
        kl = torch.tensor(0.0)
        for block in self.blocks:
            kl = kl + block.kl_divergence()
        return kl
    
    def get_parameters_dict(self) -> Dict[str, np.ndarray]:
        """Get parameters as dict for FL"""
        return {
            name: param.detach().cpu().numpy()
            for name, param in self.named_parameters()
        }
    
    def set_parameters_dict(self, params: Dict[str, np.ndarray]):
        """Set parameters from dict"""
        for name, param in self.named_parameters():
            if name in params:
                param.data = torch.from_numpy(params[name]).to(param.device)


class IntegratedDemandForecaster:
    """
    Integrated forecaster combining FL model with endogenous variables.
    
    Provides the main interface for the unified pipeline.
    """
    
    def __init__(self, config: Optional[ExtendedModelConfig] = None):
        self.config = config or ExtendedModelConfig()
        self.model = ExtendedDemandForecastModel(self.config)
        self.optimizer = torch.optim.Adam(
            self.model.parameters(),
            lr=self.config.learning_rate
        )
        
        self.training_history = []
        self.is_trained = False
    
    def train_step(
        self,
        demand_history: torch.Tensor,
        targets: torch.Tensor,
        base_covariates: Optional[torch.Tensor] = None,
        endogenous_covariates: Optional[torch.Tensor] = None
    ) -> Dict[str, float]:
        """Single training step"""
        self.model.train()
        self.optimizer.zero_grad()
        
        # Forward pass
        quantile_preds, _ = self.model(
            demand_history, base_covariates, endogenous_covariates
        )
        
        # Pinball loss
        targets_expanded = targets.unsqueeze(-1)
        losses = []
        for i, q in enumerate(self.config.quantiles):
            pred_q = quantile_preds[:, :, i:i+1]
            errors = targets_expanded - pred_q
            loss_q = torch.max(q * errors, (q - 1) * errors)
            losses.append(loss_q)
        
        pinball_loss = torch.cat(losses, dim=-1).mean()
        
        # KL divergence loss
        kl_loss = self.model.kl_divergence()
        n_samples = demand_history.shape[0]
        kl_loss = kl_loss / n_samples
        
        # Total loss
        total_loss = pinball_loss + self.config.kl_weight * kl_loss
        
        total_loss.backward()
        self.optimizer.step()
        
        return {
            'total_loss': total_loss.item(),
            'pinball_loss': pinball_loss.item(),
            'kl_loss': kl_loss.item() if isinstance(kl_loss, torch.Tensor) else kl_loss
        }
    
    def predict(
        self,
        demand_history: np.ndarray,
        base_covariates: Optional[np.ndarray] = None,
        endogenous_covariates: Optional[np.ndarray] = None,
        n_samples: int = 50
    ) -> Dict[str, np.ndarray]:
        """
        Generate predictions with uncertainty quantification.
        
        Uses Monte Carlo sampling if Bayesian layers are enabled.
        """
        # Convert to tensors
        demand_tensor = torch.from_numpy(demand_history.astype(np.float32))
        if demand_tensor.dim() == 1:
            demand_tensor = demand_tensor.unsqueeze(0)
        
        base_tensor = None
        if base_covariates is not None:
            base_tensor = torch.from_numpy(base_covariates.astype(np.float32))
            if base_tensor.dim() == 2:
                base_tensor = base_tensor.unsqueeze(0)
        
        endogenous_tensor = None
        if endogenous_covariates is not None:
            endogenous_tensor = torch.from_numpy(endogenous_covariates.astype(np.float32))
            if endogenous_tensor.dim() == 2:
                endogenous_tensor = endogenous_tensor.unsqueeze(0)
        
        if self.config.use_bayesian and n_samples > 1:
            # Monte Carlo sampling
            self.model.train()  # Enable sampling
            
            all_quantiles = []
            for _ in range(n_samples):
                with torch.no_grad():
                    q_preds, _ = self.model(
                        demand_tensor, base_tensor, endogenous_tensor
                    )
                    all_quantiles.append(q_preds)
            
            all_quantiles = torch.stack(all_quantiles, dim=0)
            
            mean_quantiles = all_quantiles.mean(dim=0)
            std_quantiles = all_quantiles.std(dim=0)
            
            self.model.eval()
            
            return {
                'q10': mean_quantiles[0, :, 0].numpy(),
                'q50': mean_quantiles[0, :, 1].numpy(),
                'q90': mean_quantiles[0, :, 2].numpy(),
                'q10_std': std_quantiles[0, :, 0].numpy(),
                'q50_std': std_quantiles[0, :, 1].numpy(),
                'q90_std': std_quantiles[0, :, 2].numpy(),
                'uncertainty': std_quantiles.mean().numpy()
            }
        else:
            self.model.eval()
            with torch.no_grad():
                q_preds, point = self.model(
                    demand_tensor, base_tensor, endogenous_tensor
                )
            
            return {
                'q10': q_preds[0, :, 0].numpy(),
                'q50': q_preds[0, :, 1].numpy(),
                'q90': q_preds[0, :, 2].numpy(),
                'point': point[0].numpy()
            }
    
    def get_fl_parameters(self) -> Dict[str, np.ndarray]:
        """Get parameters for FL aggregation"""
        return self.model.get_parameters_dict()
    
    def set_fl_parameters(self, params: Dict[str, np.ndarray]):
        """Set parameters from FL aggregation"""
        self.model.set_parameters_dict(params)
    
    def interpolate_fl_parameters(
        self,
        global_params: Dict[str, np.ndarray],
        local_weight: float = 0.3
    ):
        """Interpolate between global and local parameters"""
        for name, param in self.model.named_parameters():
            if name in global_params:
                global_tensor = torch.from_numpy(global_params[name])
                param.data = local_weight * param.data + (1 - local_weight) * global_tensor


def create_extended_config(**kwargs) -> ExtendedModelConfig:
    """Factory for extended model config"""
    return ExtendedModelConfig(**kwargs)


def create_integrated_forecaster(
    config: Optional[ExtendedModelConfig] = None
) -> IntegratedDemandForecaster:
    """Factory for integrated forecaster"""
    return IntegratedDemandForecaster(config)
