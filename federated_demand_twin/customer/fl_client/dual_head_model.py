"""
Dual-Head Demand and Revenue Forecasting Model

Extends the base demand forecasting model with a parallel revenue forecasting head.
This enables FL to abstract both demand (units) and revenue simultaneously.

Key features:
1. Shared encoder backbone for feature extraction
2. Separate heads for demand and revenue forecasting
3. Quantile outputs for both targets
4. Joint loss with configurable weighting
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import Tuple, List, Dict, Optional
from dataclasses import dataclass, field

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@dataclass
class DualHeadConfig:
    """Configuration for dual-head demand/revenue forecasting model"""
    # Input configuration
    lookback_weeks: int = 26  # 6 months of history
    forecast_horizon: int = 13  # 13 weeks ahead
    num_demand_features: int = 3  # units, promo_flag, seasonality
    num_price_features: int = 2  # price, price_index
    
    # Architecture
    encoder_hidden_dim: int = 128
    encoder_num_blocks: int = 3
    head_hidden_dim: int = 64
    head_num_layers: int = 2
    dropout: float = 0.1
    
    # Quantile forecasting
    demand_quantiles: Tuple[float, ...] = (0.1, 0.5, 0.9)
    revenue_quantiles: Tuple[float, ...] = (0.1, 0.5, 0.9)
    
    # Loss weighting
    demand_loss_weight: float = 0.6
    revenue_loss_weight: float = 0.4
    
    # Training
    learning_rate: float = 0.001
    batch_size: int = 32
    max_epochs: int = 50


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


class SharedEncoder(nn.Module):
    """
    Shared encoder backbone for both demand and revenue forecasting.
    
    Extracts common temporal features from input sequences.
    """
    
    def __init__(
        self,
        input_dim: int,
        hidden_dim: int,
        num_blocks: int,
        dropout: float = 0.1
    ):
        super().__init__()
        
        # Input projection
        self.input_proj = nn.Linear(input_dim, hidden_dim)
        
        # Stack of residual blocks
        self.blocks = nn.ModuleList([
            ResidualBlock(hidden_dim, hidden_dim * 2, dropout)
            for _ in range(num_blocks)
        ])
        
        # Layer norm
        self.norm = nn.LayerNorm(hidden_dim)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: Input tensor of shape (batch, lookback, features)
        
        Returns:
            Encoded representation of shape (batch, hidden_dim)
        """
        # Flatten temporal dimension
        batch_size = x.shape[0]
        x = x.reshape(batch_size, -1)
        
        # Project to hidden dim
        x = F.relu(self.input_proj(x))
        
        # Pass through residual blocks
        for block in self.blocks:
            x = block(x)
        
        return self.norm(x)


class QuantileForecastHead(nn.Module):
    """
    Forecasting head that produces quantile predictions.
    
    Used for both demand and revenue forecasting.
    """
    
    def __init__(
        self,
        input_dim: int,
        hidden_dim: int,
        forecast_horizon: int,
        quantiles: Tuple[float, ...],
        num_layers: int = 2,
        dropout: float = 0.1
    ):
        super().__init__()
        self.forecast_horizon = forecast_horizon
        self.num_quantiles = len(quantiles)
        self.quantiles = quantiles
        
        # Hidden layers
        layers = []
        prev_dim = input_dim
        for _ in range(num_layers):
            layers.extend([
                nn.Linear(prev_dim, hidden_dim),
                nn.ReLU(),
                nn.Dropout(dropout)
            ])
            prev_dim = hidden_dim
        
        self.hidden = nn.Sequential(*layers)
        
        # Output: horizon * num_quantiles
        self.output = nn.Linear(hidden_dim, forecast_horizon * self.num_quantiles)
    
    def forward(self, encoded: torch.Tensor) -> torch.Tensor:
        """
        Args:
            encoded: Encoded representation from shared encoder
        
        Returns:
            Quantile forecasts of shape (batch, horizon, num_quantiles)
        """
        x = self.hidden(encoded)
        x = self.output(x)
        
        # Reshape to (batch, horizon, num_quantiles)
        batch_size = x.shape[0]
        x = x.view(batch_size, self.forecast_horizon, self.num_quantiles)
        
        # Ensure quantile ordering (q10 <= q50 <= q90)
        x = self._enforce_quantile_ordering(x)
        
        return x
    
    def _enforce_quantile_ordering(self, x: torch.Tensor) -> torch.Tensor:
        """Ensure quantile predictions are monotonically increasing"""
        # Use softplus to ensure positive differences between quantiles
        q_sorted = torch.zeros_like(x)
        q_sorted[:, :, 0] = F.softplus(x[:, :, 0])  # q10 (positive)
        
        for i in range(1, self.num_quantiles):
            # Each subsequent quantile = previous + positive increment
            q_sorted[:, :, i] = q_sorted[:, :, i-1] + F.softplus(x[:, :, i])
        
        return q_sorted


class DualHeadForecastModel(nn.Module):
    """
    Dual-head model for joint demand and revenue forecasting.
    
    Architecture:
    1. Shared encoder backbone
    2. Demand forecasting head (units)
    3. Revenue forecasting head (dollars)
    
    Both heads produce quantile forecasts (q10, q50, q90).
    """
    
    def __init__(self, config: DualHeadConfig):
        super().__init__()
        self.config = config
        
        # Calculate input dimension for encoder
        input_dim = config.lookback_weeks * (config.num_demand_features + config.num_price_features)
        
        # Shared encoder
        self.encoder = SharedEncoder(
            input_dim=input_dim,
            hidden_dim=config.encoder_hidden_dim,
            num_blocks=config.encoder_num_blocks,
            dropout=config.dropout
        )
        
        # Demand forecasting head
        self.demand_head = QuantileForecastHead(
            input_dim=config.encoder_hidden_dim,
            hidden_dim=config.head_hidden_dim,
            forecast_horizon=config.forecast_horizon,
            quantiles=config.demand_quantiles,
            num_layers=config.head_num_layers,
            dropout=config.dropout
        )
        
        # Revenue forecasting head
        self.revenue_head = QuantileForecastHead(
            input_dim=config.encoder_hidden_dim,
            hidden_dim=config.head_hidden_dim,
            forecast_horizon=config.forecast_horizon,
            quantiles=config.revenue_quantiles,
            num_layers=config.head_num_layers,
            dropout=config.dropout
        )
        
        # Price encoder for revenue head (optional additional input)
        self.price_proj = nn.Linear(config.lookback_weeks, config.head_hidden_dim // 2)
    
    def forward(
        self,
        demand_features: torch.Tensor,
        price_features: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass producing demand and revenue forecasts.
        
        Args:
            demand_features: (batch, lookback, num_demand_features)
            price_features: (batch, lookback, num_price_features)
        
        Returns:
            demand_forecasts: (batch, horizon, num_quantiles) - units
            revenue_forecasts: (batch, horizon, num_quantiles) - dollars
        """
        # Concatenate features for encoder
        combined = torch.cat([demand_features, price_features], dim=-1)
        
        # Encode
        encoded = self.encoder(combined)
        
        # Demand forecast
        demand_forecasts = self.demand_head(encoded)
        
        # Revenue forecast (optionally use price info)
        # For simplicity, use same encoding; could add price projection
        revenue_forecasts = self.revenue_head(encoded)
        
        return demand_forecasts, revenue_forecasts
    
    def forecast(
        self,
        demand_features: torch.Tensor,
        price_features: torch.Tensor
    ) -> Dict[str, Dict[str, torch.Tensor]]:
        """
        Generate forecasts with named outputs.
        
        Returns:
            Dict with 'demand' and 'revenue' keys, each containing
            'q10', 'q50', 'q90' tensors of shape (batch, horizon)
        """
        self.eval()
        with torch.no_grad():
            demand_q, revenue_q = self.forward(demand_features, price_features)
        
        return {
            'demand': {
                'q10': demand_q[:, :, 0],
                'q50': demand_q[:, :, 1],
                'q90': demand_q[:, :, 2]
            },
            'revenue': {
                'q10': revenue_q[:, :, 0],
                'q50': revenue_q[:, :, 1],
                'q90': revenue_q[:, :, 2]
            }
        }


class DualHeadQuantileLoss(nn.Module):
    """
    Combined quantile loss for dual-head model.
    
    Computes weighted sum of demand and revenue quantile losses.
    """
    
    def __init__(
        self,
        demand_quantiles: Tuple[float, ...] = (0.1, 0.5, 0.9),
        revenue_quantiles: Tuple[float, ...] = (0.1, 0.5, 0.9),
        demand_weight: float = 0.6,
        revenue_weight: float = 0.4
    ):
        super().__init__()
        self.demand_quantiles = torch.tensor(demand_quantiles)
        self.revenue_quantiles = torch.tensor(revenue_quantiles)
        self.demand_weight = demand_weight
        self.revenue_weight = revenue_weight
    
    def forward(
        self,
        demand_pred: torch.Tensor,
        demand_target: torch.Tensor,
        revenue_pred: torch.Tensor,
        revenue_target: torch.Tensor
    ) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        """
        Compute combined loss.
        
        Args:
            demand_pred: (batch, horizon, num_quantiles)
            demand_target: (batch, horizon)
            revenue_pred: (batch, horizon, num_quantiles)
            revenue_target: (batch, horizon)
        
        Returns:
            total_loss: Combined weighted loss
            components: Dict with individual loss components
        """
        demand_loss = self._quantile_loss(
            demand_pred, demand_target, self.demand_quantiles.to(demand_pred.device)
        )
        
        revenue_loss = self._quantile_loss(
            revenue_pred, revenue_target, self.revenue_quantiles.to(revenue_pred.device)
        )
        
        total_loss = (
            self.demand_weight * demand_loss + 
            self.revenue_weight * revenue_loss
        )
        
        return total_loss, {
            'demand_loss': demand_loss,
            'revenue_loss': revenue_loss,
            'total_loss': total_loss
        }
    
    def _quantile_loss(
        self,
        pred: torch.Tensor,
        target: torch.Tensor,
        quantiles: torch.Tensor
    ) -> torch.Tensor:
        """Compute pinball loss for quantile regression"""
        # Expand target for each quantile
        target = target.unsqueeze(-1)  # (batch, horizon, 1)
        
        # Compute errors
        errors = target - pred  # (batch, horizon, num_quantiles)
        
        # Pinball loss
        loss = torch.where(
            errors >= 0,
            quantiles * errors,
            (quantiles - 1) * errors
        )
        
        return loss.mean()


class DualHeadTrainer:
    """
    Trainer for dual-head demand/revenue forecasting model.
    
    Handles training loop with joint optimization.
    """
    
    def __init__(
        self,
        model: DualHeadForecastModel,
        config: DualHeadConfig
    ):
        self.model = model
        self.config = config
        
        self.optimizer = torch.optim.Adam(
            model.parameters(),
            lr=config.learning_rate
        )
        
        self.loss_fn = DualHeadQuantileLoss(
            demand_quantiles=config.demand_quantiles,
            revenue_quantiles=config.revenue_quantiles,
            demand_weight=config.demand_loss_weight,
            revenue_weight=config.revenue_loss_weight
        )
        
        self.training_history: List[Dict[str, float]] = []
    
    def train_epoch(
        self,
        demand_features: torch.Tensor,
        price_features: torch.Tensor,
        demand_targets: torch.Tensor,
        revenue_targets: torch.Tensor
    ) -> Dict[str, float]:
        """Train for one epoch"""
        self.model.train()
        
        # Forward pass
        demand_pred, revenue_pred = self.model(demand_features, price_features)
        
        # Compute loss
        total_loss, loss_components = self.loss_fn(
            demand_pred, demand_targets,
            revenue_pred, revenue_targets
        )
        
        # Backward pass
        self.optimizer.zero_grad()
        total_loss.backward()
        self.optimizer.step()
        
        metrics = {
            'loss': total_loss.item(),
            'demand_loss': loss_components['demand_loss'].item(),
            'revenue_loss': loss_components['revenue_loss'].item()
        }
        
        self.training_history.append(metrics)
        
        return metrics
    
    def train(
        self,
        demand_features: torch.Tensor,
        price_features: torch.Tensor,
        demand_targets: torch.Tensor,
        revenue_targets: torch.Tensor,
        num_epochs: Optional[int] = None
    ) -> List[Dict[str, float]]:
        """Full training loop"""
        epochs = num_epochs or self.config.max_epochs
        
        for epoch in range(epochs):
            metrics = self.train_epoch(
                demand_features, price_features,
                demand_targets, revenue_targets
            )
            
            if (epoch + 1) % 10 == 0:
                print(f"Epoch {epoch+1}/{epochs} - Loss: {metrics['loss']:.4f} "
                      f"(Demand: {metrics['demand_loss']:.4f}, "
                      f"Revenue: {metrics['revenue_loss']:.4f})")
        
        return self.training_history


class FederatedDualHeadModel:
    """
    Federated learning wrapper for dual-head model.
    
    Provides methods for:
    - Parameter extraction for FL aggregation
    - Parameter loading from global model
    - Local training with privacy controls
    """
    
    def __init__(self, config: DualHeadConfig):
        self.config = config
        self.model = DualHeadForecastModel(config)
        self.trainer = DualHeadTrainer(self.model, config)
    
    def get_parameters(self) -> List[np.ndarray]:
        """Extract model parameters for FL"""
        return [
            param.detach().cpu().numpy()
            for param in self.model.parameters()
        ]
    
    def set_parameters(self, parameters: List[np.ndarray]):
        """Load parameters from FL aggregation"""
        for param, new_value in zip(self.model.parameters(), parameters):
            param.data = torch.tensor(new_value, dtype=param.dtype)
    
    def local_train(
        self,
        demand_features: np.ndarray,
        price_features: np.ndarray,
        demand_targets: np.ndarray,
        revenue_targets: np.ndarray,
        epochs: int = 3
    ) -> Dict[str, float]:
        """
        Perform local training for federated round.
        
        Returns:
            Final epoch metrics
        """
        # Convert to tensors
        demand_feat = torch.tensor(demand_features, dtype=torch.float32)
        price_feat = torch.tensor(price_features, dtype=torch.float32)
        demand_tgt = torch.tensor(demand_targets, dtype=torch.float32)
        revenue_tgt = torch.tensor(revenue_targets, dtype=torch.float32)
        
        # Train
        history = self.trainer.train(
            demand_feat, price_feat,
            demand_tgt, revenue_tgt,
            num_epochs=epochs
        )
        
        return history[-1] if history else {'loss': 0.0}
    
    def forecast(
        self,
        demand_features: np.ndarray,
        price_features: np.ndarray
    ) -> Dict[str, Dict[str, np.ndarray]]:
        """Generate forecasts"""
        demand_feat = torch.tensor(demand_features, dtype=torch.float32)
        price_feat = torch.tensor(price_features, dtype=torch.float32)
        
        forecasts = self.model.forecast(demand_feat, price_feat)
        
        return {
            'demand': {
                'q10': forecasts['demand']['q10'].numpy(),
                'q50': forecasts['demand']['q50'].numpy(),
                'q90': forecasts['demand']['q90'].numpy()
            },
            'revenue': {
                'q10': forecasts['revenue']['q10'].numpy(),
                'q50': forecasts['revenue']['q50'].numpy(),
                'q90': forecasts['revenue']['q90'].numpy()
            }
        }


def create_dual_head_model(config: Optional[DualHeadConfig] = None) -> FederatedDualHeadModel:
    """Factory function for creating dual-head model"""
    config = config or DualHeadConfig()
    return FederatedDualHeadModel(config)
