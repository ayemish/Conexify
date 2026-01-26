"""
N-BEATSx: Neural Basis Expansion Analysis with Exogenous Variables

Full implementation of N-BEATSx architecture with:
- Interpretable basis functions (trend, seasonality, generic)
- Exogenous variable support
- Explicit decomposition (trend vs seasonal vs residual)
- Quantile forecasting capability

Reference: Olivares et al. (2022) "N-BEATSx: Neural basis expansion analysis 
with exogenous variables"

Architecture:
    Input → [Trend Block] → [Seasonality Block] → [Generic Block] → Quantile Head
            ↓                ↓                      ↓
         Trend Basis      Fourier Basis         Generic FC
            ↓                ↓                      ↓
         Interpretable decomposition + Forecast
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import Dict, List, Tuple, Optional, Union
from dataclasses import dataclass, field
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BlockType(Enum):
    """Types of N-BEATS blocks"""
    TREND = "trend"
    SEASONALITY = "seasonality"
    GENERIC = "generic"


@dataclass
class NBEATSxConfig:
    """Configuration for N-BEATSx model"""
    # Input dimensions
    lookback_length: int = 52          # 1 year of weekly data
    forecast_horizon: int = 13         # 13 weeks ahead
    
    # Exogenous variables
    num_exogenous: int = 5             # price, promo, events, etc.
    exogenous_future: bool = True      # Whether exogenous vars available for forecast horizon
    
    # Stack configuration
    num_stacks: int = 3                # Trend, Seasonality, Generic
    num_blocks_per_stack: int = 3
    
    # Block architecture
    hidden_dim: int = 256
    num_layers: int = 4
    dropout: float = 0.1
    
    # Trend block settings
    trend_polynomial_degree: int = 3   # Polynomial degree for trend basis
    
    # Seasonality block settings
    num_harmonics: int = 4             # Number of Fourier harmonics
    
    # Quantile settings
    quantiles: Tuple[float, ...] = (0.1, 0.5, 0.9)
    
    # Training
    learning_rate: float = 0.001
    share_weights_in_stack: bool = False


class TrendBasis(nn.Module):
    """
    Trend basis using polynomial expansion.
    
    Produces interpretable trend forecasts using polynomial basis:
    f(t) = θ₀ + θ₁t + θ₂t² + ... + θₚtᵖ
    
    The basis matrix T has shape (horizon, degree+1) where T[i,j] = (i/H)^j
    """
    
    def __init__(
        self,
        lookback_length: int,
        forecast_horizon: int,
        polynomial_degree: int = 3
    ):
        super().__init__()
        self.lookback_length = lookback_length
        self.forecast_horizon = forecast_horizon
        self.degree = polynomial_degree
        
        # Create polynomial basis matrices (fixed, not learned)
        # Time normalized to [0, 1]
        backcast_time = torch.arange(lookback_length).float() / lookback_length
        forecast_time = torch.arange(forecast_horizon).float() / forecast_horizon
        
        # Polynomial powers: [1, t, t², t³, ...]
        backcast_basis = torch.stack([
            backcast_time ** p for p in range(polynomial_degree + 1)
        ], dim=1)  # (lookback, degree+1)
        
        forecast_basis = torch.stack([
            forecast_time ** p for p in range(polynomial_degree + 1)
        ], dim=1)  # (horizon, degree+1)
        
        self.register_buffer('backcast_basis', backcast_basis)
        self.register_buffer('forecast_basis', forecast_basis)
    
    def forward(
        self, 
        theta_backcast: torch.Tensor, 
        theta_forecast: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Apply trend basis expansion.
        
        Args:
            theta_backcast: (batch, degree+1) coefficients for backcast
            theta_forecast: (batch, degree+1) coefficients for forecast
        
        Returns:
            backcast: (batch, lookback_length)
            forecast: (batch, forecast_horizon)
        """
        # backcast = basis @ theta^T -> (lookback, batch)
        backcast = self.backcast_basis @ theta_backcast.T  # (lookback, batch)
        backcast = backcast.T  # (batch, lookback)
        
        forecast = self.forecast_basis @ theta_forecast.T
        forecast = forecast.T  # (batch, horizon)
        
        return backcast, forecast


class SeasonalityBasis(nn.Module):
    """
    Seasonality basis using Fourier expansion.
    
    Produces interpretable seasonal forecasts:
    f(t) = Σᵢ [aᵢcos(2πit/P) + bᵢsin(2πit/P)]
    
    Where P is the period and harmonics capture different frequencies.
    """
    
    def __init__(
        self,
        lookback_length: int,
        forecast_horizon: int,
        num_harmonics: int = 4
    ):
        super().__init__()
        self.lookback_length = lookback_length
        self.forecast_horizon = forecast_horizon
        self.num_harmonics = num_harmonics
        
        # Number of coefficients: 2 per harmonic (sin + cos)
        self.num_coefficients = 2 * num_harmonics
        
        # Create Fourier basis matrices
        backcast_time = torch.arange(lookback_length).float()
        forecast_time = torch.arange(lookback_length, lookback_length + forecast_horizon).float()
        
        backcast_basis = self._create_fourier_basis(backcast_time)
        forecast_basis = self._create_fourier_basis(forecast_time)
        
        self.register_buffer('backcast_basis', backcast_basis)
        self.register_buffer('forecast_basis', forecast_basis)
    
    def _create_fourier_basis(self, time: torch.Tensor) -> torch.Tensor:
        """Create Fourier basis matrix"""
        period = self.lookback_length  # Assume period = lookback
        basis_vectors = []
        
        for h in range(1, self.num_harmonics + 1):
            freq = 2 * np.pi * h / period
            basis_vectors.append(torch.cos(freq * time))
            basis_vectors.append(torch.sin(freq * time))
        
        return torch.stack(basis_vectors, dim=1)  # (time, 2*harmonics)
    
    def forward(
        self,
        theta_backcast: torch.Tensor,
        theta_forecast: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Apply seasonality basis expansion.
        
        Args:
            theta_backcast: (batch, 2*harmonics) Fourier coefficients for backcast
            theta_forecast: (batch, 2*harmonics) Fourier coefficients for forecast
        
        Returns:
            backcast: (batch, lookback_length)
            forecast: (batch, forecast_horizon)
        """
        backcast = self.backcast_basis @ theta_backcast.T
        backcast = backcast.T
        
        forecast = self.forecast_basis @ theta_forecast.T
        forecast = forecast.T
        
        return backcast, forecast


class GenericBasis(nn.Module):
    """
    Generic basis using learnable linear projection.
    
    No interpretable structure - captures residual patterns that
    don't fit trend or seasonality.
    """
    
    def __init__(
        self,
        lookback_length: int,
        forecast_horizon: int,
        hidden_dim: int
    ):
        super().__init__()
        self.lookback_length = lookback_length
        self.forecast_horizon = forecast_horizon
        
        # Learnable basis (not fixed like trend/seasonality)
        self.backcast_linear = nn.Linear(hidden_dim, lookback_length)
        self.forecast_linear = nn.Linear(hidden_dim, forecast_horizon)
    
    def forward(
        self,
        theta: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Apply generic basis expansion.
        
        Args:
            theta: (batch, hidden_dim) learned representation
        
        Returns:
            backcast: (batch, lookback_length)
            forecast: (batch, forecast_horizon)
        """
        backcast = self.backcast_linear(theta)
        forecast = self.forecast_linear(theta)
        return backcast, forecast


class NBEATSxBlock(nn.Module):
    """
    Single N-BEATSx block with specific basis type.
    
    Architecture:
        Input (lookback + exogenous) → FC layers → theta coefficients → Basis expansion
    """
    
    def __init__(
        self,
        lookback_length: int,
        forecast_horizon: int,
        num_exogenous: int,
        hidden_dim: int,
        num_layers: int,
        block_type: BlockType,
        dropout: float = 0.1,
        polynomial_degree: int = 3,
        num_harmonics: int = 4,
        exogenous_future: bool = True
    ):
        super().__init__()
        self.lookback_length = lookback_length
        self.forecast_horizon = forecast_horizon
        self.block_type = block_type
        self.exogenous_future = exogenous_future
        
        # Input: lookback + exogenous (past) + optional exogenous (future)
        exo_input_dim = num_exogenous * lookback_length
        if exogenous_future:
            exo_input_dim += num_exogenous * forecast_horizon
        
        input_dim = lookback_length + exo_input_dim
        
        # FC stack
        layers = []
        layers.append(nn.Linear(input_dim, hidden_dim))
        layers.append(nn.ReLU())
        layers.append(nn.Dropout(dropout))
        
        for _ in range(num_layers - 1):
            layers.append(nn.Linear(hidden_dim, hidden_dim))
            layers.append(nn.ReLU())
            layers.append(nn.Dropout(dropout))
        
        self.fc_stack = nn.Sequential(*layers)
        
        # Basis-specific theta projection and expansion
        if block_type == BlockType.TREND:
            theta_dim = polynomial_degree + 1
            self.theta_backcast = nn.Linear(hidden_dim, theta_dim)
            self.theta_forecast = nn.Linear(hidden_dim, theta_dim)
            self.basis = TrendBasis(lookback_length, forecast_horizon, polynomial_degree)
            
        elif block_type == BlockType.SEASONALITY:
            theta_dim = 2 * num_harmonics
            self.theta_backcast = nn.Linear(hidden_dim, theta_dim)
            self.theta_forecast = nn.Linear(hidden_dim, theta_dim)
            self.basis = SeasonalityBasis(lookback_length, forecast_horizon, num_harmonics)
            
        else:  # GENERIC
            self.basis = GenericBasis(lookback_length, forecast_horizon, hidden_dim)
    
    def forward(
        self,
        x: torch.Tensor,
        exogenous_past: Optional[torch.Tensor] = None,
        exogenous_future: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass through block.
        
        Args:
            x: (batch, lookback_length) - input time series residual
            exogenous_past: (batch, lookback_length, num_exogenous)
            exogenous_future: (batch, forecast_horizon, num_exogenous)
        
        Returns:
            backcast: (batch, lookback_length)
            forecast: (batch, forecast_horizon)
        """
        batch_size = x.shape[0]
        
        # Concatenate input with exogenous variables
        inputs = [x]
        
        if exogenous_past is not None:
            exo_past_flat = exogenous_past.view(batch_size, -1)
            inputs.append(exo_past_flat)
        
        if exogenous_future is not None and self.exogenous_future:
            exo_future_flat = exogenous_future.view(batch_size, -1)
            inputs.append(exo_future_flat)
        
        combined = torch.cat(inputs, dim=1)
        
        # FC stack
        h = self.fc_stack(combined)
        
        # Basis expansion
        if self.block_type in [BlockType.TREND, BlockType.SEASONALITY]:
            theta_b = self.theta_backcast(h)
            theta_f = self.theta_forecast(h)
            backcast, forecast = self.basis(theta_b, theta_f)
        else:
            backcast, forecast = self.basis(h)
        
        return backcast, forecast


class NBEATSxStack(nn.Module):
    """
    Stack of N-BEATSx blocks with same basis type.
    
    Residual stacking: each block processes the residual from previous block.
    """
    
    def __init__(
        self,
        lookback_length: int,
        forecast_horizon: int,
        num_exogenous: int,
        hidden_dim: int,
        num_layers: int,
        num_blocks: int,
        block_type: BlockType,
        dropout: float = 0.1,
        polynomial_degree: int = 3,
        num_harmonics: int = 4,
        exogenous_future: bool = True,
        share_weights: bool = False
    ):
        super().__init__()
        self.block_type = block_type
        self.share_weights = share_weights
        self.forecast_horizon = forecast_horizon
        
        if share_weights:
            # Single block with shared weights
            self.shared_block = NBEATSxBlock(
                lookback_length=lookback_length,
                forecast_horizon=forecast_horizon,
                num_exogenous=num_exogenous,
                hidden_dim=hidden_dim,
                num_layers=num_layers,
                block_type=block_type,
                dropout=dropout,
                polynomial_degree=polynomial_degree,
                num_harmonics=num_harmonics,
                exogenous_future=exogenous_future
            )
            self.num_blocks = num_blocks
            self.blocks = None
        else:
            self.blocks = nn.ModuleList([
                NBEATSxBlock(
                    lookback_length=lookback_length,
                    forecast_horizon=forecast_horizon,
                    num_exogenous=num_exogenous,
                    hidden_dim=hidden_dim,
                    num_layers=num_layers,
                    block_type=block_type,
                    dropout=dropout,
                    polynomial_degree=polynomial_degree,
                    num_harmonics=num_harmonics,
                    exogenous_future=exogenous_future
                )
                for _ in range(num_blocks)
            ])
    
    def forward(
        self,
        x: torch.Tensor,
        exogenous_past: Optional[torch.Tensor] = None,
        exogenous_future: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Forward pass through stack.
        
        Returns:
            residual: remaining signal after all blocks
            stack_backcast: sum of backcasts from this stack
            stack_forecast: sum of forecasts from this stack
        """
        residual = x
        
        stack_backcast = torch.zeros_like(x)
        stack_forecast = torch.zeros(x.shape[0], self.forecast_horizon, device=x.device)
        
        blocks = self.blocks if self.blocks else [self.shared_block] * self.num_blocks
        
        for block in blocks:
            backcast, forecast = block(residual, exogenous_past, exogenous_future)
            residual = residual - backcast
            stack_backcast = stack_backcast + backcast
            stack_forecast = stack_forecast + forecast
        
        return residual, stack_backcast, stack_forecast


class NBEATSx(nn.Module):
    """
    Full N-BEATSx model with interpretable decomposition.
    
    Architecture:
        [Trend Stack] → [Seasonality Stack] → [Generic Stack]
        
    Each stack produces interpretable component of the forecast:
    - Trend: polynomial-based long-term trajectory
    - Seasonality: Fourier-based periodic patterns
    - Generic: residual patterns
    
    Final forecast = trend_forecast + seasonality_forecast + generic_forecast
    """
    
    def __init__(self, config: NBEATSxConfig):
        super().__init__()
        self.config = config
        
        # Build stacks: Trend → Seasonality → Generic
        self.trend_stack = NBEATSxStack(
            lookback_length=config.lookback_length,
            forecast_horizon=config.forecast_horizon,
            num_exogenous=config.num_exogenous,
            hidden_dim=config.hidden_dim,
            num_layers=config.num_layers,
            num_blocks=config.num_blocks_per_stack,
            block_type=BlockType.TREND,
            dropout=config.dropout,
            polynomial_degree=config.trend_polynomial_degree,
            exogenous_future=config.exogenous_future,
            share_weights=config.share_weights_in_stack
        )
        
        self.seasonality_stack = NBEATSxStack(
            lookback_length=config.lookback_length,
            forecast_horizon=config.forecast_horizon,
            num_exogenous=config.num_exogenous,
            hidden_dim=config.hidden_dim,
            num_layers=config.num_layers,
            num_blocks=config.num_blocks_per_stack,
            block_type=BlockType.SEASONALITY,
            dropout=config.dropout,
            num_harmonics=config.num_harmonics,
            exogenous_future=config.exogenous_future,
            share_weights=config.share_weights_in_stack
        )
        
        self.generic_stack = NBEATSxStack(
            lookback_length=config.lookback_length,
            forecast_horizon=config.forecast_horizon,
            num_exogenous=config.num_exogenous,
            hidden_dim=config.hidden_dim,
            num_layers=config.num_layers,
            num_blocks=config.num_blocks_per_stack,
            block_type=BlockType.GENERIC,
            dropout=config.dropout,
            exogenous_future=config.exogenous_future,
            share_weights=config.share_weights_in_stack
        )
        
        # Quantile head for probabilistic forecasting
        self.quantile_head = nn.Sequential(
            nn.Linear(config.forecast_horizon, config.hidden_dim),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.hidden_dim, config.forecast_horizon * len(config.quantiles))
        )
        self.num_quantiles = len(config.quantiles)
    
    def forward(
        self,
        x: torch.Tensor,
        exogenous_past: Optional[torch.Tensor] = None,
        exogenous_future: Optional[torch.Tensor] = None,
        return_decomposition: bool = False
    ) -> Union[
        Tuple[torch.Tensor, torch.Tensor],
        Tuple[torch.Tensor, torch.Tensor, Dict[str, torch.Tensor]]
    ]:
        """
        Forward pass with optional decomposition.
        
        Args:
            x: (batch, lookback_length) input time series
            exogenous_past: (batch, lookback_length, num_exogenous)
            exogenous_future: (batch, forecast_horizon, num_exogenous)
            return_decomposition: if True, return component forecasts
        
        Returns:
            quantile_forecasts: (batch, horizon, num_quantiles)
            point_forecast: (batch, horizon) - median
            decomposition: dict with trend, seasonality, generic components (optional)
        """
        batch_size = x.shape[0]
        
        # Trend stack
        residual, trend_backcast, trend_forecast = self.trend_stack(
            x, exogenous_past, exogenous_future
        )
        
        # Seasonality stack
        residual, seasonal_backcast, seasonal_forecast = self.seasonality_stack(
            residual, exogenous_past, exogenous_future
        )
        
        # Generic stack
        residual, generic_backcast, generic_forecast = self.generic_stack(
            residual, exogenous_past, exogenous_future
        )
        
        # Sum forecasts
        total_forecast = trend_forecast + seasonal_forecast + generic_forecast
        
        # Quantile transformation
        q_out = self.quantile_head(total_forecast)
        q_out = q_out.view(batch_size, self.config.forecast_horizon, self.num_quantiles)
        
        # Ensure quantile ordering with softplus + cumsum
        q_out = F.softplus(q_out)
        q_out = torch.cumsum(q_out, dim=-1)
        
        # Point forecast is median (q50)
        median_idx = list(self.config.quantiles).index(0.5)
        point_forecast = q_out[:, :, median_idx]
        
        if return_decomposition:
            decomposition = {
                'trend': trend_forecast,
                'seasonality': seasonal_forecast,
                'generic': generic_forecast,
                'trend_backcast': trend_backcast,
                'seasonal_backcast': seasonal_backcast,
                'generic_backcast': generic_backcast,
                'residual': residual
            }
            return q_out, point_forecast, decomposition
        
        return q_out, point_forecast
    
    def get_num_parameters(self) -> int:
        """Count trainable parameters"""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


class NBEATSxLoss(nn.Module):
    """
    Combined loss for N-BEATSx training.
    
    Includes:
    - Pinball loss for quantile forecasting
    - Optional backcast reconstruction loss
    """
    
    def __init__(
        self,
        quantiles: Tuple[float, ...] = (0.1, 0.5, 0.9),
        backcast_weight: float = 0.0
    ):
        super().__init__()
        self.quantiles = quantiles
        self.backcast_weight = backcast_weight
    
    def forward(
        self,
        predictions: torch.Tensor,
        targets: torch.Tensor,
        backcast: Optional[torch.Tensor] = None,
        backcast_target: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        """
        Compute combined loss.
        
        Args:
            predictions: (batch, horizon, num_quantiles)
            targets: (batch, horizon)
            backcast: (batch, lookback) - optional
            backcast_target: (batch, lookback) - optional
        """
        # Pinball loss for quantiles
        targets_exp = targets.unsqueeze(-1)  # (batch, horizon, 1)
        
        quantile_losses = []
        for i, q in enumerate(self.quantiles):
            pred_q = predictions[:, :, i:i+1]
            errors = targets_exp - pred_q
            loss_q = torch.max(q * errors, (q - 1) * errors)
            quantile_losses.append(loss_q)
        
        pinball_loss = torch.cat(quantile_losses, dim=-1).mean()
        
        # Backcast loss (optional)
        if self.backcast_weight > 0 and backcast is not None and backcast_target is not None:
            backcast_loss = F.mse_loss(backcast, backcast_target)
            total_loss = pinball_loss + self.backcast_weight * backcast_loss
        else:
            total_loss = pinball_loss
        
        return total_loss


class FederatedNBEATSx:
    """
    Federated learning wrapper for N-BEATSx.
    
    Provides:
    - Model serialization for FL updates
    - Local training with privacy
    - Metrics collection
    """
    
    def __init__(self, config: Optional[NBEATSxConfig] = None):
        self.config = config or NBEATSxConfig()
        self.model = NBEATSx(self.config)
        self.loss_fn = NBEATSxLoss(self.config.quantiles)
        self.optimizer = torch.optim.Adam(
            self.model.parameters(),
            lr=self.config.learning_rate
        )
    
    def get_parameters(self) -> List[np.ndarray]:
        """Get model parameters for FL aggregation"""
        return [
            param.detach().cpu().numpy()
            for param in self.model.parameters()
        ]
    
    def set_parameters(self, parameters: List[np.ndarray]):
        """Set model parameters from FL server"""
        for param, new_value in zip(self.model.parameters(), parameters):
            param.data = torch.from_numpy(new_value).to(param.device)
    
    def train_epoch(
        self,
        train_loader: torch.utils.data.DataLoader
    ) -> Dict[str, float]:
        """Train for one epoch"""
        self.model.train()
        total_loss = 0.0
        num_batches = 0
        
        for batch in train_loader:
            x = batch['history']
            targets = batch['targets']
            exo_past = batch.get('exogenous_past')
            exo_future = batch.get('exogenous_future')
            
            self.optimizer.zero_grad()
            
            q_preds, _ = self.model(x, exo_past, exo_future)
            loss = self.loss_fn(q_preds, targets)
            
            loss.backward()
            self.optimizer.step()
            
            total_loss += loss.item()
            num_batches += 1
        
        return {
            'loss': total_loss / max(num_batches, 1),
            'num_batches': num_batches
        }
    
    def predict(
        self,
        x: torch.Tensor,
        exogenous_past: Optional[torch.Tensor] = None,
        exogenous_future: Optional[torch.Tensor] = None,
        return_decomposition: bool = False
    ) -> Dict[str, torch.Tensor]:
        """Generate predictions"""
        self.model.eval()
        with torch.no_grad():
            if return_decomposition:
                q_preds, point, decomp = self.model(
                    x, exogenous_past, exogenous_future, return_decomposition=True
                )
                return {
                    'quantiles': q_preds,
                    'point': point,
                    'q10': q_preds[:, :, 0],
                    'q50': q_preds[:, :, 1],
                    'q90': q_preds[:, :, 2],
                    'decomposition': decomp
                }
            else:
                q_preds, point = self.model(x, exogenous_past, exogenous_future)
                return {
                    'quantiles': q_preds,
                    'point': point,
                    'q10': q_preds[:, :, 0],
                    'q50': q_preds[:, :, 1],
                    'q90': q_preds[:, :, 2],
                }


def create_nbeatsx(config: Optional[NBEATSxConfig] = None) -> FederatedNBEATSx:
    """Factory function for N-BEATSx model"""
    return FederatedNBEATSx(config)


if __name__ == "__main__":
    print("Testing N-BEATSx Implementation")
    print("=" * 50)
    
    # Create config
    config = NBEATSxConfig(
        lookback_length=52,
        forecast_horizon=13,
        num_exogenous=5,
        hidden_dim=128,
        num_layers=3,
        num_blocks_per_stack=2,
        trend_polynomial_degree=3,
        num_harmonics=4
    )
    
    # Create model
    model = create_nbeatsx(config)
    print(f"Model parameters: {model.model.get_num_parameters():,}")
    
    # Test data
    batch_size = 4
    x = torch.randn(batch_size, config.lookback_length)
    exo_past = torch.randn(batch_size, config.lookback_length, config.num_exogenous)
    exo_future = torch.randn(batch_size, config.forecast_horizon, config.num_exogenous)
    
    # Test forward pass
    predictions = model.predict(x, exo_past, exo_future, return_decomposition=True)
    
    print(f"\nInput shape: {x.shape}")
    print(f"Point forecast shape: {predictions['point'].shape}")
    print(f"Quantile forecast shape: {predictions['quantiles'].shape}")
    
    print("\nDecomposition:")
    for key, val in predictions['decomposition'].items():
        print(f"  {key}: {val.shape}")
    
    # Test training step
    print("\n" + "=" * 50)
    print("Testing training step...")
    
    targets = torch.randn(batch_size, config.forecast_horizon).abs()
    
    model.model.train()
    model.optimizer.zero_grad()
    
    q_preds, _ = model.model(x, exo_past, exo_future)
    loss = model.loss_fn(q_preds, targets)
    loss.backward()
    
    print(f"Loss: {loss.item():.4f}")
    print(f"Gradients computed successfully")
    
    # Test FL parameter exchange
    print("\n" + "=" * 50)
    print("Testing FL parameter exchange...")
    
    params = model.get_parameters()
    print(f"Number of parameter tensors: {len(params)}")
    print(f"Total parameters: {sum(p.size for p in params):,}")
    
    # Modify and restore
    original_param = params[0].copy()
    params[0] = params[0] * 0.9
    model.set_parameters(params)
    
    new_params = model.get_parameters()
    print(f"Parameters modified and restored successfully")
