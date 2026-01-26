"""
Demand Forecasting Model for Federated Learning

Implements a lightweight N-BEATS-inspired architecture suitable for:
- Local training on private sales data
- Federated aggregation of model updates
- Probabilistic forecasting with quantile outputs

FR-2.2: Local training on private data
FR-3.1: Probabilistic forecasts as quantiles
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import Tuple, List, Dict, Optional
from dataclasses import dataclass


@dataclass
class ModelConfig:
    """Configuration for demand forecasting model"""
    # Input configuration
    lookback_weeks: int = 26  # 6 months of history
    forecast_horizon: int = 13  # 13 weeks ahead
    num_covariates: int = 5  # price, promo, seasonality indicators
    
    # Architecture
    hidden_dim: int = 128
    num_blocks: int = 3
    num_layers_per_block: int = 2
    dropout: float = 0.1
    
    # Quantile forecasting
    quantiles: Tuple[float, ...] = (0.1, 0.5, 0.9)
    
    # Training
    learning_rate: float = 0.001
    batch_size: int = 32
    max_epochs: int = 50
    early_stopping_patience: int = 5


class ResidualBlock(nn.Module):
    """Residual block with skip connection"""
    
    def __init__(self, input_dim: int, hidden_dim: int, dropout: float = 0.1):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.fc3 = nn.Linear(hidden_dim, input_dim)
        self.dropout = nn.Dropout(dropout)
        self.norm = nn.LayerNorm(input_dim)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = x
        x = F.relu(self.fc1(x))
        x = self.dropout(x)
        x = F.relu(self.fc2(x))
        x = self.dropout(x)
        x = self.fc3(x)
        return self.norm(x + residual)


class NBEATSBlock(nn.Module):
    """
    Simplified N-BEATS-inspired block for demand forecasting.
    
    Produces both backcast (reconstruction of input) and forecast.
    """
    
    def __init__(
        self, 
        lookback: int, 
        forecast_horizon: int, 
        hidden_dim: int,
        num_layers: int = 2,
        dropout: float = 0.1
    ):
        super().__init__()
        self.lookback = lookback
        self.forecast_horizon = forecast_horizon
        
        # Stack of residual layers
        layers = []
        input_dim = lookback
        for _ in range(num_layers):
            layers.append(ResidualBlock(input_dim, hidden_dim, dropout))
        self.stack = nn.Sequential(*layers)
        
        # Backcast and forecast projections
        self.backcast_fc = nn.Linear(lookback, lookback)
        self.forecast_fc = nn.Linear(lookback, forecast_horizon)
    
    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            x: Input tensor of shape (batch, lookback)
        
        Returns:
            backcast: Reconstruction of shape (batch, lookback)
            forecast: Prediction of shape (batch, forecast_horizon)
        """
        h = self.stack(x)
        backcast = self.backcast_fc(h)
        forecast = self.forecast_fc(h)
        return backcast, forecast


class QuantileHead(nn.Module):
    """
    Quantile regression head for probabilistic forecasting.
    
    FR-3.1: Produces q10/q50/q90 quantile forecasts
    """
    
    def __init__(self, forecast_horizon: int, hidden_dim: int, quantiles: Tuple[float, ...]):
        super().__init__()
        self.quantiles = quantiles
        self.num_quantiles = len(quantiles)
        
        self.fc1 = nn.Linear(forecast_horizon, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, forecast_horizon * self.num_quantiles)
        self.forecast_horizon = forecast_horizon
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: Forecast tensor of shape (batch, forecast_horizon)
        
        Returns:
            Quantile forecasts of shape (batch, forecast_horizon, num_quantiles)
        """
        h = F.relu(self.fc1(x))
        out = self.fc2(h)
        out = out.view(-1, self.forecast_horizon, self.num_quantiles)
        
        # Ensure quantile ordering (q10 <= q50 <= q90)
        # Use softplus to ensure positive values, then cumsum for ordering
        out = F.softplus(out)
        out = torch.cumsum(out, dim=-1)
        
        return out


class DemandForecastModel(nn.Module):
    """
    Main demand forecasting model for federated learning.
    
    Architecture:
    1. Covariate encoder
    2. Stack of N-BEATS-style blocks with residual connections
    3. Quantile prediction head
    """
    
    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config
        
        # Covariate encoder
        self.covariate_encoder = nn.Sequential(
            nn.Linear(config.num_covariates * config.lookback_weeks, config.hidden_dim),
            nn.ReLU(),
            nn.Linear(config.hidden_dim, config.lookback_weeks),
        )
        
        # N-BEATS blocks
        self.blocks = nn.ModuleList([
            NBEATSBlock(
                lookback=config.lookback_weeks,
                forecast_horizon=config.forecast_horizon,
                hidden_dim=config.hidden_dim,
                num_layers=config.num_layers_per_block,
                dropout=config.dropout
            )
            for _ in range(config.num_blocks)
        ])
        
        # Quantile head
        self.quantile_head = QuantileHead(
            forecast_horizon=config.forecast_horizon,
            hidden_dim=config.hidden_dim,
            quantiles=config.quantiles
        )
    
    def forward(
        self, 
        demand_history: torch.Tensor,
        covariates: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass producing quantile forecasts.
        
        Args:
            demand_history: Shape (batch, lookback_weeks)
            covariates: Shape (batch, lookback_weeks, num_covariates) or None
        
        Returns:
            quantile_forecasts: Shape (batch, forecast_horizon, num_quantiles)
            point_forecast: Shape (batch, forecast_horizon) - median forecast
        """
        # Encode covariates if provided
        if covariates is not None:
            batch_size = demand_history.shape[0]
            cov_flat = covariates.view(batch_size, -1)
            cov_encoded = self.covariate_encoder(cov_flat)
            x = demand_history + cov_encoded
        else:
            x = demand_history
        
        # Process through N-BEATS blocks with residual stacking
        residual = x
        forecast_sum = torch.zeros(
            x.shape[0], self.config.forecast_horizon, device=x.device
        )
        
        for block in self.blocks:
            backcast, forecast = block(residual)
            residual = residual - backcast  # Subtract backcast for next block
            forecast_sum = forecast_sum + forecast  # Accumulate forecasts
        
        # Generate quantile forecasts
        quantile_forecasts = self.quantile_head(forecast_sum)
        
        # Point forecast is median (q50)
        median_idx = self.config.quantiles.index(0.5)
        point_forecast = quantile_forecasts[:, :, median_idx]
        
        return quantile_forecasts, point_forecast
    
    def get_num_parameters(self) -> int:
        """Count trainable parameters"""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


class QuantileLoss(nn.Module):
    """
    Pinball loss for quantile regression.
    
    Ensures well-calibrated probabilistic forecasts.
    """
    
    def __init__(self, quantiles: Tuple[float, ...]):
        super().__init__()
        self.quantiles = quantiles
    
    def forward(
        self, 
        predictions: torch.Tensor, 
        targets: torch.Tensor
    ) -> torch.Tensor:
        """
        Args:
            predictions: Shape (batch, horizon, num_quantiles)
            targets: Shape (batch, horizon)
        
        Returns:
            Scalar loss
        """
        targets = targets.unsqueeze(-1)  # (batch, horizon, 1)
        
        losses = []
        for i, q in enumerate(self.quantiles):
            pred_q = predictions[:, :, i:i+1]
            errors = targets - pred_q
            loss_q = torch.max(q * errors, (q - 1) * errors)
            losses.append(loss_q)
        
        total_loss = torch.cat(losses, dim=-1).mean()
        return total_loss


class FederatedDemandModel:
    """
    Wrapper for federated learning operations.
    
    Provides:
    - Model serialization/deserialization for FL updates
    - Local training with privacy considerations
    - Metrics collection
    """
    
    def __init__(self, config: Optional[ModelConfig] = None):
        self.config = config or ModelConfig()
        self.model = DemandForecastModel(self.config)
        self.loss_fn = QuantileLoss(self.config.quantiles)
        self.optimizer = torch.optim.Adam(
            self.model.parameters(), 
            lr=self.config.learning_rate
        )
    
    def get_parameters(self) -> List[np.ndarray]:
        """Get model parameters as numpy arrays for FL"""
        return [
            param.detach().cpu().numpy() 
            for param in self.model.parameters()
        ]
    
    def set_parameters(self, parameters: List[np.ndarray]):
        """Set model parameters from numpy arrays"""
        params_dict = zip(self.model.parameters(), parameters)
        for param, new_value in params_dict:
            param.data = torch.from_numpy(new_value).to(param.device)
    
    def train_epoch(
        self, 
        train_loader: torch.utils.data.DataLoader
    ) -> Dict[str, float]:
        """
        Train for one epoch on local data.
        
        FR-2.2: Local training on private data
        """
        self.model.train()
        total_loss = 0.0
        num_batches = 0
        
        for batch in train_loader:
            demand_history = batch['demand_history']
            covariates = batch.get('covariates')
            targets = batch['targets']
            
            self.optimizer.zero_grad()
            
            quantile_preds, _ = self.model(demand_history, covariates)
            loss = self.loss_fn(quantile_preds, targets)
            
            loss.backward()
            self.optimizer.step()
            
            total_loss += loss.item()
            num_batches += 1
        
        return {
            'loss': total_loss / max(num_batches, 1),
            'num_batches': num_batches
        }
    
    def evaluate(
        self, 
        val_loader: torch.utils.data.DataLoader
    ) -> Dict[str, float]:
        """Evaluate model on validation data"""
        self.model.eval()
        total_loss = 0.0
        num_batches = 0
        
        with torch.no_grad():
            for batch in val_loader:
                demand_history = batch['demand_history']
                covariates = batch.get('covariates')
                targets = batch['targets']
                
                quantile_preds, _ = self.model(demand_history, covariates)
                loss = self.loss_fn(quantile_preds, targets)
                
                total_loss += loss.item()
                num_batches += 1
        
        return {
            'val_loss': total_loss / max(num_batches, 1),
            'num_samples': num_batches * self.config.batch_size
        }
    
    def predict(
        self, 
        demand_history: torch.Tensor,
        covariates: Optional[torch.Tensor] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Generate predictions with quantiles.
        
        FR-3.1: Probabilistic forecasts as quantiles
        """
        self.model.eval()
        with torch.no_grad():
            quantile_preds, point_pred = self.model(demand_history, covariates)
        
        return {
            'quantiles': quantile_preds,
            'point': point_pred,
            'q10': quantile_preds[:, :, 0],
            'q50': quantile_preds[:, :, 1],
            'q90': quantile_preds[:, :, 2],
        }


def create_model(config: Optional[ModelConfig] = None) -> FederatedDemandModel:
    """Factory function to create a demand forecasting model"""
    return FederatedDemandModel(config)


if __name__ == "__main__":
    # Test model creation and forward pass
    config = ModelConfig()
    model = create_model(config)
    
    print(f"Model parameters: {model.model.get_num_parameters():,}")
    
    # Test forward pass
    batch_size = 4
    demand = torch.randn(batch_size, config.lookback_weeks)
    covariates = torch.randn(batch_size, config.lookback_weeks, config.num_covariates)
    
    predictions = model.predict(demand, covariates)
    
    print(f"Point forecast shape: {predictions['point'].shape}")
    print(f"Quantile forecast shape: {predictions['quantiles'].shape}")
    print(f"Q10 shape: {predictions['q10'].shape}")
    print(f"Q50 shape: {predictions['q50'].shape}")
    print(f"Q90 shape: {predictions['q90'].shape}")
