"""
Federated Learning + NBEATS Integration

This module bridges the gap between:
1. Federated Bayesian Learning (cross-retailer aggregation with uncertainty)
2. NBEATS Demand Forecasting (local time series with covariates)

The integration enables:
- FL-aggregated parameters to inform local NBEATS models
- Uncertainty from FL to propagate into forecast confidence
- Bayesian weight distributions from FL to improve generalization
- Privacy-preserving demand forecasting across retailers
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import logging
import copy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class FLNBEATSConfig:
    """Configuration for FL-integrated NBEATS"""
    # NBEATS architecture
    lookback_weeks: int = 26
    forecast_horizon: int = 13
    num_covariates: int = 13  # 5 base + 8 endogenous
    hidden_dim: int = 128
    num_blocks: int = 3
    dropout: float = 0.1
    quantiles: Tuple[float, ...] = (0.1, 0.5, 0.9)
    
    # Federated learning
    fl_aggregation_weight: float = 0.7  # Weight for FL global vs local
    uncertainty_scaling: float = 1.0  # Scale factor for FL uncertainty
    min_local_samples: int = 100  # Min samples before using local model
    
    # Bayesian integration
    use_bayesian_layers: bool = True
    prior_strength: float = 1.0
    
    # Training
    learning_rate: float = 0.001
    local_epochs: int = 5


class BayesianNBEATSBlock(nn.Module):
    """
    NBEATS block with Bayesian weight distributions.
    
    Enables uncertainty quantification from FL to propagate through forecasting.
    """
    
    def __init__(
        self,
        lookback: int,
        forecast_horizon: int,
        hidden_dim: int,
        dropout: float = 0.1,
        use_bayesian: bool = True
    ):
        super().__init__()
        self.lookback = lookback
        self.forecast_horizon = forecast_horizon
        self.use_bayesian = use_bayesian
        
        # Core layers
        self.fc1 = nn.Linear(lookback, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.fc3 = nn.Linear(hidden_dim, lookback)
        self.dropout = nn.Dropout(dropout)
        self.norm = nn.LayerNorm(lookback)
        
        # Output projections
        self.backcast_fc = nn.Linear(lookback, lookback)
        self.forecast_fc = nn.Linear(lookback, forecast_horizon)
        
        # Bayesian parameters (log variance for each weight)
        if use_bayesian:
            self.fc1_logvar = nn.Parameter(torch.full_like(self.fc1.weight, -3.0))
            self.fc2_logvar = nn.Parameter(torch.full_like(self.fc2.weight, -3.0))
            self.fc3_logvar = nn.Parameter(torch.full_like(self.fc3.weight, -3.0))
    
    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Forward pass with optional weight sampling"""
        if self.training and self.use_bayesian:
            # Sample weights during training
            h = self._bayesian_linear(x, self.fc1, self.fc1_logvar)
        else:
            h = self.fc1(x)
        
        h = F.relu(h)
        h = self.dropout(h)
        
        if self.training and self.use_bayesian:
            h = self._bayesian_linear(h, self.fc2, self.fc2_logvar)
        else:
            h = self.fc2(h)
        
        h = F.relu(h)
        h = self.dropout(h)
        
        if self.training and self.use_bayesian:
            h = self._bayesian_linear(h, self.fc3, self.fc3_logvar)
        else:
            h = self.fc3(h)
        
        h = self.norm(h + x)
        
        backcast = self.backcast_fc(h)
        forecast = self.forecast_fc(h)
        
        return backcast, forecast
    
    def _bayesian_linear(
        self,
        x: torch.Tensor,
        layer: nn.Linear,
        logvar: torch.Tensor
    ) -> torch.Tensor:
        """Apply linear layer with sampled weights"""
        std = torch.exp(0.5 * logvar)
        weight = layer.weight + std * torch.randn_like(std)
        return F.linear(x, weight, layer.bias)
    
    def get_kl_divergence(self) -> torch.Tensor:
        """KL divergence from prior (standard normal)"""
        if not self.use_bayesian:
            return torch.tensor(0.0)
        
        kl = 0.0
        for logvar in [self.fc1_logvar, self.fc2_logvar, self.fc3_logvar]:
            # KL(N(mu, sigma) || N(0, 1)) for each weight
            kl += 0.5 * torch.sum(torch.exp(logvar) - 1 - logvar)
        
        return kl


class FederatedNBEATSModel(nn.Module):
    """
    NBEATS model designed for federated learning with Bayesian layers.
    
    Features:
    - Bayesian weight distributions for uncertainty
    - Covariate encoder for exogenous variables
    - Quantile outputs for probabilistic forecasting
    - FL-compatible parameter extraction/injection
    """
    
    def __init__(self, config: FLNBEATSConfig):
        super().__init__()
        self.config = config
        
        # Covariate encoder (handles base + endogenous covariates)
        self.covariate_encoder = nn.Sequential(
            nn.Linear(config.num_covariates * config.lookback_weeks, config.hidden_dim),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.hidden_dim, config.lookback_weeks)
        )
        
        # Bayesian NBEATS blocks
        self.blocks = nn.ModuleList([
            BayesianNBEATSBlock(
                lookback=config.lookback_weeks,
                forecast_horizon=config.forecast_horizon,
                hidden_dim=config.hidden_dim,
                dropout=config.dropout,
                use_bayesian=config.use_bayesian_layers
            )
            for _ in range(config.num_blocks)
        ])
        
        # Quantile head
        self.quantile_fc1 = nn.Linear(config.forecast_horizon, config.hidden_dim)
        self.quantile_fc2 = nn.Linear(config.hidden_dim, config.forecast_horizon * len(config.quantiles))
        
        self.num_quantiles = len(config.quantiles)
    
    def forward(
        self,
        demand_history: torch.Tensor,
        covariates: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass.
        
        Args:
            demand_history: (batch, lookback_weeks)
            covariates: (batch, lookback_weeks, num_covariates) or None
            
        Returns:
            quantile_forecasts: (batch, horizon, num_quantiles)
            point_forecast: (batch, horizon)
        """
        batch_size = demand_history.shape[0]
        
        # Encode covariates
        if covariates is not None:
            cov_flat = covariates.view(batch_size, -1)
            cov_encoded = self.covariate_encoder(cov_flat)
            x = demand_history + cov_encoded
        else:
            x = demand_history
        
        # Process through blocks
        residual = x
        forecast_sum = torch.zeros(batch_size, self.config.forecast_horizon, device=x.device)
        
        for block in self.blocks:
            backcast, forecast = block(residual)
            residual = residual - backcast
            forecast_sum = forecast_sum + forecast
        
        # Quantile outputs
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
    
    def get_total_kl_divergence(self) -> torch.Tensor:
        """Get total KL divergence across all Bayesian blocks"""
        kl = torch.tensor(0.0)
        for block in self.blocks:
            kl = kl + block.get_kl_divergence()
        return kl
    
    def get_fl_parameters(self) -> Dict[str, np.ndarray]:
        """Extract parameters for FL aggregation"""
        params = {}
        for name, param in self.named_parameters():
            params[name] = param.detach().cpu().numpy()
        return params
    
    def set_fl_parameters(self, params: Dict[str, np.ndarray]):
        """Set parameters from FL aggregation"""
        for name, param in self.named_parameters():
            if name in params:
                param.data = torch.from_numpy(params[name]).to(param.device)
    
    def interpolate_fl_parameters(
        self,
        global_params: Dict[str, np.ndarray],
        local_weight: float = 0.3
    ):
        """
        Interpolate between global FL parameters and local parameters.
        
        Enables personalization while benefiting from federated aggregation.
        """
        for name, param in self.named_parameters():
            if name in global_params:
                global_tensor = torch.from_numpy(global_params[name]).to(param.device)
                param.data = local_weight * param.data + (1 - local_weight) * global_tensor


class FLNBEATSClient:
    """
    Federated learning client for NBEATS demand forecasting.
    
    Handles:
    - Local training on private sales data
    - Parameter exchange with FL server
    - Uncertainty propagation from Bayesian layers
    - Personalization vs. global model tradeoff
    """
    
    def __init__(
        self,
        client_id: str,
        config: Optional[FLNBEATSConfig] = None
    ):
        self.client_id = client_id
        self.config = config or FLNBEATSConfig()
        self.model = FederatedNBEATSModel(self.config)
        self.optimizer = torch.optim.Adam(
            self.model.parameters(),
            lr=self.config.learning_rate
        )
        
        # Training history
        self.train_history = []
        self.local_samples = 0
    
    def train_local(
        self,
        demand_history: torch.Tensor,
        covariates: Optional[torch.Tensor],
        targets: torch.Tensor
    ) -> Dict[str, float]:
        """
        Train on local data for one round.
        
        Includes KL divergence term for Bayesian regularization.
        """
        self.model.train()
        self.local_samples = demand_history.shape[0]
        
        total_loss = 0.0
        
        for epoch in range(self.config.local_epochs):
            self.optimizer.zero_grad()
            
            # Forward pass
            quantile_preds, _ = self.model(demand_history, covariates)
            
            # Quantile loss (pinball)
            targets_expanded = targets.unsqueeze(-1)
            losses = []
            for i, q in enumerate(self.config.quantiles):
                pred_q = quantile_preds[:, :, i:i+1]
                errors = targets_expanded - pred_q
                loss_q = torch.max(q * errors, (q - 1) * errors)
                losses.append(loss_q)
            
            pinball_loss = torch.cat(losses, dim=-1).mean()
            
            # KL divergence loss
            kl_loss = self.model.get_total_kl_divergence() / self.local_samples
            
            # Total loss
            loss = pinball_loss + self.config.prior_strength * kl_loss
            
            loss.backward()
            self.optimizer.step()
            
            total_loss += loss.item()
        
        avg_loss = total_loss / self.config.local_epochs
        self.train_history.append({'loss': avg_loss, 'samples': self.local_samples})
        
        return {
            'loss': avg_loss,
            'samples': self.local_samples,
            'kl_divergence': kl_loss.item() if isinstance(kl_loss, torch.Tensor) else kl_loss
        }
    
    def get_parameters(self) -> Dict[str, np.ndarray]:
        """Get model parameters for FL server"""
        return self.model.get_fl_parameters()
    
    def set_parameters(self, params: Dict[str, np.ndarray]):
        """Set model parameters from FL server"""
        if self.local_samples >= self.config.min_local_samples:
            # Personalized: interpolate with local
            self.model.interpolate_fl_parameters(
                params,
                local_weight=1 - self.config.fl_aggregation_weight
            )
        else:
            # Not enough local data: use global
            self.model.set_fl_parameters(params)
    
    def predict(
        self,
        demand_history: torch.Tensor,
        covariates: Optional[torch.Tensor] = None,
        n_samples: int = 100
    ) -> Dict[str, torch.Tensor]:
        """
        Generate predictions with uncertainty quantification.
        
        If using Bayesian layers, samples multiple times for uncertainty.
        """
        self.model.eval()
        
        if self.config.use_bayesian_layers and n_samples > 1:
            # Monte Carlo sampling for uncertainty
            self.model.train()  # Enable dropout and weight sampling
            
            all_quantiles = []
            for _ in range(n_samples):
                with torch.no_grad():
                    q_preds, _ = self.model(demand_history, covariates)
                    all_quantiles.append(q_preds)
            
            all_quantiles = torch.stack(all_quantiles, dim=0)
            
            # Compute statistics across samples
            mean_quantiles = all_quantiles.mean(dim=0)
            std_quantiles = all_quantiles.std(dim=0)
            
            self.model.eval()
            
            return {
                'quantiles': mean_quantiles,
                'quantile_std': std_quantiles,
                'q10': mean_quantiles[:, :, 0],
                'q50': mean_quantiles[:, :, 1],
                'q90': mean_quantiles[:, :, 2],
                'uncertainty': std_quantiles.mean(dim=-1)
            }
        else:
            with torch.no_grad():
                q_preds, point = self.model(demand_history, covariates)
            
            return {
                'quantiles': q_preds,
                'q10': q_preds[:, :, 0],
                'q50': q_preds[:, :, 1],
                'q90': q_preds[:, :, 2],
                'point': point
            }


class FLNBEATSServer:
    """
    Federated learning server for NBEATS aggregation.
    
    Aggregates Bayesian NBEATS parameters from multiple retailers
    while preserving uncertainty information.
    """
    
    def __init__(self, config: Optional[FLNBEATSConfig] = None):
        self.config = config or FLNBEATSConfig()
        self.global_model = FederatedNBEATSModel(self.config)
        self.clients: Dict[str, FLNBEATSClient] = {}
        self.round_history = []
    
    def register_client(self, client: FLNBEATSClient):
        """Register a client for federated learning"""
        self.clients[client.client_id] = client
    
    def aggregate_parameters(
        self,
        client_params: List[Dict[str, np.ndarray]],
        client_weights: List[float]
    ) -> Dict[str, np.ndarray]:
        """
        Aggregate parameters using weighted average with variance tracking.
        
        For Bayesian layers, also aggregates log-variance parameters
        to preserve uncertainty information.
        """
        # Normalize weights
        total_weight = sum(client_weights)
        weights = [w / total_weight for w in client_weights]
        
        aggregated = {}
        
        for param_name in client_params[0].keys():
            param_stack = np.stack([p[param_name] for p in client_params])
            
            if 'logvar' in param_name:
                # For variance parameters: aggregate in variance space
                # then convert back to log-variance
                variances = np.exp(param_stack)
                weighted_var = np.sum(
                    [w * v for w, v in zip(weights, variances)],
                    axis=0
                )
                aggregated[param_name] = np.log(weighted_var + 1e-8)
            else:
                # For mean parameters: weighted average
                aggregated[param_name] = np.sum(
                    [w * p for w, p in zip(weights, param_stack)],
                    axis=0
                )
        
        return aggregated
    
    def run_round(self) -> Dict[str, float]:
        """Run one round of federated learning"""
        # Collect parameters from clients
        client_params = []
        client_weights = []
        
        for client_id, client in self.clients.items():
            params = client.get_parameters()
            client_params.append(params)
            client_weights.append(client.local_samples)
        
        if not client_params:
            return {'error': 'No client parameters'}
        
        # Aggregate
        aggregated = self.aggregate_parameters(client_params, client_weights)
        
        # Update global model
        self.global_model.set_fl_parameters(aggregated)
        
        # Distribute to clients
        for client in self.clients.values():
            client.set_parameters(aggregated)
        
        # Record round
        round_metrics = {
            'num_clients': len(self.clients),
            'total_samples': sum(client_weights)
        }
        self.round_history.append(round_metrics)
        
        return round_metrics
    
    def get_global_parameters(self) -> Dict[str, np.ndarray]:
        """Get current global model parameters"""
        return self.global_model.get_fl_parameters()


# =============================================================================
# INTEGRATION WITH UNIFIED PIPELINE
# =============================================================================

class FLIntegratedForecaster:
    """
    Forecaster that combines FL-aggregated model with local adaptation.
    
    Designed to plug into the UnifiedPipeline.
    """
    
    def __init__(
        self,
        client_id: str,
        config: Optional[FLNBEATSConfig] = None
    ):
        self.client = FLNBEATSClient(client_id, config)
        self.config = self.client.config
        self.is_trained = False
    
    def update_from_fl_server(self, server: FLNBEATSServer):
        """Update local model with global FL parameters"""
        global_params = server.get_global_parameters()
        self.client.set_parameters(global_params)
    
    def train_local(
        self,
        demand_history: np.ndarray,
        covariates: Optional[np.ndarray],
        targets: np.ndarray
    ) -> Dict[str, float]:
        """Train on local data"""
        demand_tensor = torch.from_numpy(demand_history.astype(np.float32))
        target_tensor = torch.from_numpy(targets.astype(np.float32))
        
        cov_tensor = None
        if covariates is not None:
            cov_tensor = torch.from_numpy(covariates.astype(np.float32))
        
        metrics = self.client.train_local(demand_tensor, cov_tensor, target_tensor)
        self.is_trained = True
        
        return metrics
    
    def predict(
        self,
        demand_history: np.ndarray,
        covariates: Optional[np.ndarray] = None
    ) -> Dict[str, np.ndarray]:
        """Generate forecast with uncertainty"""
        demand_tensor = torch.from_numpy(demand_history.astype(np.float32))
        
        if demand_tensor.dim() == 1:
            demand_tensor = demand_tensor.unsqueeze(0)
        
        cov_tensor = None
        if covariates is not None:
            cov_tensor = torch.from_numpy(covariates.astype(np.float32))
            if cov_tensor.dim() == 2:
                cov_tensor = cov_tensor.unsqueeze(0)
        
        predictions = self.client.predict(demand_tensor, cov_tensor)
        
        return {
            'q10': predictions['q10'].numpy(),
            'q50': predictions['q50'].numpy(),
            'q90': predictions['q90'].numpy(),
            'uncertainty': predictions.get('uncertainty', torch.zeros(1)).numpy()
        }
    
    @property
    def model(self):
        """Access underlying model for UnifiedPipeline compatibility"""
        return self.client.model


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

def create_fl_nbeats_config(**kwargs) -> FLNBEATSConfig:
    """Create FL-NBEATS configuration"""
    return FLNBEATSConfig(**kwargs)


def create_fl_nbeats_client(
    client_id: str,
    config: Optional[FLNBEATSConfig] = None
) -> FLNBEATSClient:
    """Create an FL-NBEATS client"""
    return FLNBEATSClient(client_id, config)


def create_fl_nbeats_server(
    config: Optional[FLNBEATSConfig] = None
) -> FLNBEATSServer:
    """Create an FL-NBEATS server"""
    return FLNBEATSServer(config)


def create_fl_integrated_forecaster(
    client_id: str,
    config: Optional[FLNBEATSConfig] = None
) -> FLIntegratedForecaster:
    """Create an FL-integrated forecaster for the pipeline"""
    return FLIntegratedForecaster(client_id, config)
