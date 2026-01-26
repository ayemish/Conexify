"""
SLOTH: Simultaneous Learning of Time Series Hierarchies

End-to-end learning that produces coherent hierarchical forecasts
directly, without post-hoc reconciliation.

Key Innovation:
    Traditional: Train models → MinT reconciliation → Coherent forecasts
    SLOTH: Train with coherence constraint → Directly coherent forecasts

The coherence loss enforces: y = S × b
    where y = all forecasts, b = bottom-level forecasts, S = summing matrix

Reference: Rangapuram et al. (2021) "End-to-End Learning of Coherent 
Probabilistic Forecasts for Hierarchical Time Series"

Usage:
    hierarchy = HierarchyStructure(hierarchy_df)
    trainer = SLOTHTrainer(model, hierarchy, coherence_weight=0.1)
    trainer.train(train_loader)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class HierarchyLevel:
    """Defines a level in the hierarchy"""
    name: str
    column: str
    parent_column: Optional[str] = None


@dataclass 
class SLOTHConfig:
    """Configuration for SLOTH training"""
    # Coherence loss weight
    coherence_weight: float = 0.1
    
    # Annealing: increase coherence weight during training
    coherence_annealing: bool = True
    coherence_start_weight: float = 0.01
    coherence_end_weight: float = 0.5
    annealing_epochs: int = 20
    
    # Probabilistic coherence (for quantile forecasts)
    probabilistic_coherence: bool = True
    quantiles: Tuple[float, ...] = (0.1, 0.5, 0.9)
    
    # Regularization
    hierarchy_regularization: str = "l2"  # "l1", "l2", "huber"
    
    # Training
    learning_rate: float = 0.001
    max_epochs: int = 100
    early_stopping_patience: int = 10
    
    # Projection (soft vs hard coherence)
    use_projection: bool = False  # Project to coherent subspace after forward pass


class HierarchyStructure:
    """
    Manages hierarchical structure and summing matrix for SLOTH.
    
    Builds the summing matrix S that defines aggregation relationships:
    S × b = y, where b = bottom-level, y = all levels
    """
    
    def __init__(
        self,
        hierarchy_df: pd.DataFrame,
        bottom_level: str = "sku_id",
        levels: Optional[List[str]] = None
    ):
        """
        Args:
            hierarchy_df: DataFrame with hierarchy mapping
                Columns: [sku_id, subcategory_id, category_id, ...]
            bottom_level: Name of bottom-level column
            levels: Ordered list of level columns (bottom to top)
        """
        self.hierarchy_df = hierarchy_df
        self.bottom_level = bottom_level
        
        # Default level order
        self.levels = levels or [
            'sku_id', 'subcategory_id', 'category_id', 'region_id'
        ]
        self.levels = [l for l in self.levels if l in hierarchy_df.columns]
        
        self._build_structure()
    
    def _build_structure(self):
        """Build hierarchy indices and summing matrix"""
        df = self.hierarchy_df
        
        # Get unique entities at each level
        self.level_entities = {}
        for level in self.levels:
            self.level_entities[level] = sorted(df[level].unique().tolist())
        
        # Count series at each level
        self.n_bottom = len(self.level_entities[self.bottom_level])
        
        # Total series = bottom + aggregates + total
        self.n_total = 1  # Start with total
        for level in self.levels:
            self.n_total += len(self.level_entities[level])
        
        # Create index mappings
        self.entity_to_idx = {}
        self.idx_to_entity = {}
        
        idx = 0
        # Total is index 0
        self.entity_to_idx['TOTAL'] = idx
        self.idx_to_entity[idx] = ('TOTAL', 'total')
        idx += 1
        
        # Higher levels (excluding bottom)
        for level in reversed(self.levels[1:]):
            for entity in self.level_entities[level]:
                self.entity_to_idx[(level, entity)] = idx
                self.idx_to_entity[idx] = (level, entity)
                idx += 1
        
        # Bottom level
        for entity in self.level_entities[self.bottom_level]:
            self.entity_to_idx[(self.bottom_level, entity)] = idx
            self.idx_to_entity[idx] = (self.bottom_level, entity)
            idx += 1
        
        # Build summing matrix S
        self._build_summing_matrix()
        
        logger.info(f"Hierarchy: {self.n_total} total series, {self.n_bottom} bottom-level")
    
    def _build_summing_matrix(self):
        """
        Build summing matrix S of shape (n_total, n_bottom).
        
        S[i,j] = 1 if bottom series j contributes to aggregate series i
        """
        df = self.hierarchy_df
        m = self.n_total  # Total series
        n = self.n_bottom  # Bottom series
        
        S = np.zeros((m, n))
        
        # Total row: sum of all bottom series
        S[0, :] = 1
        
        # Aggregate levels
        for level in self.levels[1:]:  # Skip bottom level
            for entity in self.level_entities[level]:
                row_idx = self.entity_to_idx[(level, entity)]
                
                # Find all bottom-level series under this aggregate
                mask = df[level] == entity
                bottom_entities = df[mask][self.bottom_level].unique()
                
                for bottom_entity in bottom_entities:
                    col_idx = self.level_entities[self.bottom_level].index(bottom_entity)
                    S[row_idx, col_idx] = 1
        
        # Bottom level: identity matrix
        bottom_start = m - n
        S[bottom_start:, :] = np.eye(n)
        
        self.S = S
        self.S_tensor = torch.tensor(S, dtype=torch.float32)
    
    def get_summing_matrix(self, device: torch.device = None) -> torch.Tensor:
        """Get summing matrix as tensor"""
        if device:
            return self.S_tensor.to(device)
        return self.S_tensor
    
    def get_bottom_indices(self) -> List[int]:
        """Get indices of bottom-level series"""
        return list(range(self.n_total - self.n_bottom, self.n_total))
    
    def aggregate(self, bottom_forecasts: torch.Tensor) -> torch.Tensor:
        """
        Aggregate bottom-level forecasts to all levels.
        
        Args:
            bottom_forecasts: (batch, n_bottom, horizon) or (batch, n_bottom)
        
        Returns:
            all_forecasts: (batch, n_total, horizon) or (batch, n_total)
        """
        S = self.S_tensor.to(bottom_forecasts.device)
        
        if bottom_forecasts.dim() == 2:
            # (batch, n_bottom) -> (batch, n_total)
            return torch.einsum('mn,bn->bm', S, bottom_forecasts)
        else:
            # (batch, n_bottom, horizon) -> (batch, n_total, horizon)
            return torch.einsum('mn,bnh->bmh', S, bottom_forecasts)
    
    def project_to_coherent(self, forecasts: torch.Tensor) -> torch.Tensor:
        """
        Project forecasts to coherent subspace using MinT-style projection.
        
        P = S(S'S)^{-1}S'
        
        Args:
            forecasts: (batch, n_total, horizon)
        
        Returns:
            coherent: (batch, n_total, horizon) satisfying y = S × b
        """
        S = self.S_tensor.to(forecasts.device)
        
        # Compute projection matrix P = S @ (S.T @ S)^{-1} @ S.T
        StS = S.T @ S
        StS_inv = torch.linalg.inv(StS)
        P = S @ StS_inv @ S.T  # (n_total, n_total)
        
        if forecasts.dim() == 2:
            return torch.einsum('mn,bn->bm', P, forecasts)
        else:
            return torch.einsum('mn,bnh->bmh', P, forecasts)


class CoherenceLoss(nn.Module):
    """
    Coherence loss that enforces hierarchical constraints.
    
    Loss = ||y - S × b||² 
    
    where:
    - y = all forecasts (batch, n_total, horizon)
    - b = bottom-level forecasts (batch, n_bottom, horizon)
    - S = summing matrix (n_total, n_bottom)
    """
    
    def __init__(
        self,
        hierarchy: HierarchyStructure,
        regularization: str = "l2"
    ):
        super().__init__()
        self.hierarchy = hierarchy
        self.regularization = regularization
        self.register_buffer('S', hierarchy.get_summing_matrix())
    
    def forward(self, forecasts: torch.Tensor) -> torch.Tensor:
        """
        Compute coherence loss.
        
        Args:
            forecasts: (batch, n_total, horizon) or (batch, n_total)
        
        Returns:
            Scalar coherence loss
        """
        n_total = self.hierarchy.n_total
        n_bottom = self.hierarchy.n_bottom
        bottom_start = n_total - n_bottom
        
        # Extract bottom-level forecasts
        if forecasts.dim() == 2:
            bottom = forecasts[:, bottom_start:]  # (batch, n_bottom)
            aggregated = torch.einsum('mn,bn->bm', self.S, bottom)
        else:
            bottom = forecasts[:, bottom_start:, :]  # (batch, n_bottom, horizon)
            aggregated = torch.einsum('mn,bnh->bmh', self.S, bottom)
        
        # Coherence violation
        violation = forecasts - aggregated
        
        if self.regularization == "l1":
            return torch.abs(violation).mean()
        elif self.regularization == "huber":
            return F.smooth_l1_loss(forecasts, aggregated)
        else:  # l2
            return torch.pow(violation, 2).mean()


class ProbabilisticCoherenceLoss(nn.Module):
    """
    Coherence loss for probabilistic (quantile) forecasts.
    
    Ensures coherence holds for each quantile independently.
    """
    
    def __init__(
        self,
        hierarchy: HierarchyStructure,
        quantiles: Tuple[float, ...] = (0.1, 0.5, 0.9),
        regularization: str = "l2"
    ):
        super().__init__()
        self.hierarchy = hierarchy
        self.quantiles = quantiles
        self.regularization = regularization
        self.register_buffer('S', hierarchy.get_summing_matrix())
    
    def forward(self, quantile_forecasts: torch.Tensor) -> torch.Tensor:
        """
        Compute coherence loss for quantile forecasts.
        
        Args:
            quantile_forecasts: (batch, n_total, horizon, n_quantiles)
        
        Returns:
            Scalar coherence loss averaged across quantiles
        """
        n_total = self.hierarchy.n_total
        n_bottom = self.hierarchy.n_bottom
        bottom_start = n_total - n_bottom
        
        total_loss = 0.0
        
        for q_idx in range(len(self.quantiles)):
            # Extract quantile slice
            q_forecasts = quantile_forecasts[:, :, :, q_idx]  # (batch, n_total, horizon)
            
            # Bottom level
            bottom = q_forecasts[:, bottom_start:, :]  # (batch, n_bottom, horizon)
            aggregated = torch.einsum('mn,bnh->bmh', self.S, bottom)
            
            # Coherence violation
            violation = q_forecasts - aggregated
            
            if self.regularization == "l1":
                q_loss = torch.abs(violation).mean()
            elif self.regularization == "huber":
                q_loss = F.smooth_l1_loss(q_forecasts, aggregated)
            else:
                q_loss = torch.pow(violation, 2).mean()
            
            total_loss = total_loss + q_loss
        
        return total_loss / len(self.quantiles)


class SLOTHLoss(nn.Module):
    """
    Combined SLOTH loss: Forecast loss + Coherence loss.
    
    Total Loss = L_forecast + λ × L_coherence
    
    With optional weight annealing to gradually increase coherence emphasis.
    """
    
    def __init__(
        self,
        hierarchy: HierarchyStructure,
        config: SLOTHConfig,
        forecast_loss_fn: Optional[nn.Module] = None
    ):
        super().__init__()
        self.hierarchy = hierarchy
        self.config = config
        
        # Forecast loss (pinball for quantiles)
        self.forecast_loss_fn = forecast_loss_fn or PinballLoss(config.quantiles)
        
        # Coherence loss
        if config.probabilistic_coherence:
            self.coherence_loss_fn = ProbabilisticCoherenceLoss(
                hierarchy, config.quantiles, config.hierarchy_regularization
            )
        else:
            self.coherence_loss_fn = CoherenceLoss(
                hierarchy, config.hierarchy_regularization
            )
        
        # Current coherence weight (for annealing)
        self.current_weight = config.coherence_start_weight if config.coherence_annealing else config.coherence_weight
        self.current_epoch = 0
    
    def update_epoch(self, epoch: int):
        """Update coherence weight based on epoch (for annealing)"""
        self.current_epoch = epoch
        
        if self.config.coherence_annealing:
            progress = min(epoch / self.config.annealing_epochs, 1.0)
            self.current_weight = (
                self.config.coherence_start_weight + 
                progress * (self.config.coherence_end_weight - self.config.coherence_start_weight)
            )
    
    def forward(
        self,
        predictions: torch.Tensor,
        targets: torch.Tensor,
        return_components: bool = False
    ) -> Union[torch.Tensor, Tuple[torch.Tensor, Dict[str, torch.Tensor]]]:
        """
        Compute combined loss.
        
        Args:
            predictions: (batch, n_total, horizon, n_quantiles) for quantile forecasts
                        or (batch, n_total, horizon) for point forecasts
            targets: (batch, n_total, horizon)
            return_components: if True, return individual loss components
        
        Returns:
            total_loss: combined scalar loss
            components: dict with forecast_loss, coherence_loss (optional)
        """
        # Forecast loss
        if predictions.dim() == 4:  # Quantile forecasts
            # Use median for forecast loss target comparison
            median_idx = list(self.config.quantiles).index(0.5)
            forecast_loss = self.forecast_loss_fn(predictions, targets)
        else:
            forecast_loss = F.mse_loss(predictions, targets)
        
        # Coherence loss
        coherence_loss = self.coherence_loss_fn(predictions)
        
        # Combined loss
        total_loss = forecast_loss + self.current_weight * coherence_loss
        
        if return_components:
            return total_loss, {
                'forecast_loss': forecast_loss,
                'coherence_loss': coherence_loss,
                'coherence_weight': self.current_weight,
                'total_loss': total_loss
            }
        
        return total_loss


class PinballLoss(nn.Module):
    """Pinball loss for quantile forecasting"""
    
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
            predictions: (batch, n_series, horizon, n_quantiles)
            targets: (batch, n_series, horizon)
        """
        targets = targets.unsqueeze(-1)  # (batch, n_series, horizon, 1)
        
        losses = []
        for i, q in enumerate(self.quantiles):
            pred_q = predictions[:, :, :, i:i+1]
            errors = targets - pred_q
            loss_q = torch.max(q * errors, (q - 1) * errors)
            losses.append(loss_q)
        
        return torch.cat(losses, dim=-1).mean()


class HierarchicalModel(nn.Module):
    """
    Base class for hierarchical forecasting models compatible with SLOTH.
    
    Subclasses should implement `forward` to produce forecasts for all
    series in the hierarchy.
    """
    
    def __init__(
        self,
        hierarchy: HierarchyStructure,
        base_model: nn.Module,
        shared_encoder: bool = True
    ):
        super().__init__()
        self.hierarchy = hierarchy
        self.base_model = base_model
        self.shared_encoder = shared_encoder
        
        # Output projection to hierarchy
        self.n_total = hierarchy.n_total
    
    def forward(
        self,
        inputs: Dict[str, torch.Tensor],
        return_bottom_only: bool = False
    ) -> torch.Tensor:
        """
        Generate forecasts for all hierarchy levels.
        
        Args:
            inputs: Dict with keys for each bottom-level series
                   or batched input for all series
            return_bottom_only: if True, only return bottom-level forecasts
        
        Returns:
            forecasts: (batch, n_total, horizon, n_quantiles)
        """
        raise NotImplementedError("Subclasses must implement forward")


class SLOTHWrapper(nn.Module):
    """
    Wraps any forecasting model to add SLOTH coherence.
    
    Adds coherence projection layer and integrates with hierarchy.
    """
    
    def __init__(
        self,
        base_model: nn.Module,
        hierarchy: HierarchyStructure,
        config: SLOTHConfig
    ):
        super().__init__()
        self.base_model = base_model
        self.hierarchy = hierarchy
        self.config = config
        
        # Optional projection layer
        if config.use_projection:
            self.register_buffer('P', self._compute_projection_matrix())
    
    def _compute_projection_matrix(self) -> torch.Tensor:
        """Compute coherence projection matrix P = S(S'S)^{-1}S'"""
        S = self.hierarchy.S_tensor
        StS = S.T @ S
        StS_inv = torch.linalg.inv(StS)
        P = S @ StS_inv @ S.T
        return P
    
    def forward(
        self,
        x: torch.Tensor,
        **kwargs
    ) -> torch.Tensor:
        """
        Forward pass with optional coherence projection.
        
        Args:
            x: Input to base model (depends on model architecture)
            **kwargs: Additional arguments for base model
        
        Returns:
            forecasts: Optionally projected to coherent subspace
        """
        # Get base model forecasts
        forecasts = self.base_model(x, **kwargs)
        
        # Project to coherent subspace if enabled
        if self.config.use_projection and not self.training:
            # Only project during inference; during training, use soft coherence loss
            if forecasts.dim() == 4:  # (batch, n_total, horizon, n_quantiles)
                batch, n_total, horizon, n_q = forecasts.shape
                forecasts_flat = forecasts.permute(0, 3, 1, 2).reshape(-1, n_total, horizon)
                projected = self.hierarchy.project_to_coherent(forecasts_flat)
                forecasts = projected.reshape(batch, n_q, n_total, horizon).permute(0, 2, 3, 1)
            else:
                forecasts = self.hierarchy.project_to_coherent(forecasts)
        
        return forecasts


class SLOTHTrainer:
    """
    Trainer for SLOTH end-to-end hierarchical learning.
    
    Handles:
    - Training loop with coherence loss
    - Weight annealing
    - Coherence monitoring
    - Early stopping
    """
    
    def __init__(
        self,
        model: nn.Module,
        hierarchy: HierarchyStructure,
        config: Optional[SLOTHConfig] = None
    ):
        self.model = model
        self.hierarchy = hierarchy
        self.config = config or SLOTHConfig()
        
        # Loss function
        self.loss_fn = SLOTHLoss(hierarchy, self.config)
        
        # Optimizer
        self.optimizer = torch.optim.Adam(
            model.parameters(),
            lr=self.config.learning_rate
        )
        
        # Tracking
        self.history = {
            'train_loss': [],
            'forecast_loss': [],
            'coherence_loss': [],
            'coherence_weight': []
        }
        self.best_loss = float('inf')
        self.patience_counter = 0
    
    def train_epoch(
        self,
        train_loader: torch.utils.data.DataLoader,
        epoch: int
    ) -> Dict[str, float]:
        """Train for one epoch"""
        self.model.train()
        self.loss_fn.update_epoch(epoch)
        
        total_loss = 0.0
        total_forecast_loss = 0.0
        total_coherence_loss = 0.0
        num_batches = 0
        
        for batch in train_loader:
            inputs = batch['inputs']
            targets = batch['targets']
            
            self.optimizer.zero_grad()
            
            # Forward pass
            predictions = self.model(inputs)
            
            # Combined loss
            loss, components = self.loss_fn(predictions, targets, return_components=True)
            
            # Backward pass
            loss.backward()
            self.optimizer.step()
            
            # Accumulate
            total_loss += loss.item()
            total_forecast_loss += components['forecast_loss'].item()
            total_coherence_loss += components['coherence_loss'].item()
            num_batches += 1
        
        metrics = {
            'loss': total_loss / max(num_batches, 1),
            'forecast_loss': total_forecast_loss / max(num_batches, 1),
            'coherence_loss': total_coherence_loss / max(num_batches, 1),
            'coherence_weight': self.loss_fn.current_weight
        }
        
        # Update history
        for key, value in metrics.items():
            if key in self.history:
                self.history[key].append(value)
        
        return metrics
    
    def validate(
        self,
        val_loader: torch.utils.data.DataLoader
    ) -> Dict[str, float]:
        """Validate model"""
        self.model.eval()
        
        total_loss = 0.0
        total_coherence_violation = 0.0
        num_batches = 0
        
        with torch.no_grad():
            for batch in val_loader:
                inputs = batch['inputs']
                targets = batch['targets']
                
                predictions = self.model(inputs)
                loss, components = self.loss_fn(predictions, targets, return_components=True)
                
                total_loss += loss.item()
                total_coherence_violation += components['coherence_loss'].item()
                num_batches += 1
        
        return {
            'val_loss': total_loss / max(num_batches, 1),
            'val_coherence_violation': total_coherence_violation / max(num_batches, 1)
        }
    
    def train(
        self,
        train_loader: torch.utils.data.DataLoader,
        val_loader: Optional[torch.utils.data.DataLoader] = None,
        verbose: bool = True
    ) -> Dict[str, List[float]]:
        """
        Full training loop.
        
        Returns:
            history: Dict with training metrics over epochs
        """
        for epoch in range(self.config.max_epochs):
            # Train
            train_metrics = self.train_epoch(train_loader, epoch)
            
            # Validate
            if val_loader:
                val_metrics = self.validate(val_loader)
                current_loss = val_metrics['val_loss']
            else:
                val_metrics = {}
                current_loss = train_metrics['loss']
            
            # Early stopping
            if current_loss < self.best_loss:
                self.best_loss = current_loss
                self.patience_counter = 0
            else:
                self.patience_counter += 1
            
            if verbose and epoch % 5 == 0:
                logger.info(
                    f"Epoch {epoch}: loss={train_metrics['loss']:.4f}, "
                    f"coherence={train_metrics['coherence_loss']:.4f}, "
                    f"weight={train_metrics['coherence_weight']:.4f}"
                )
            
            if self.patience_counter >= self.config.early_stopping_patience:
                logger.info(f"Early stopping at epoch {epoch}")
                break
        
        return self.history
    
    def check_coherence(self, forecasts: torch.Tensor) -> Dict[str, float]:
        """
        Check coherence of forecasts.
        
        Returns metrics on how well forecasts satisfy hierarchy constraints.
        """
        n_total = self.hierarchy.n_total
        n_bottom = self.hierarchy.n_bottom
        bottom_start = n_total - n_bottom
        
        S = self.hierarchy.S_tensor.to(forecasts.device)
        
        # Handle different forecast shapes
        if forecasts.dim() == 4:  # (batch, n_total, horizon, n_quantiles)
            # Check median quantile
            median_idx = list(self.config.quantiles).index(0.5)
            forecasts = forecasts[:, :, :, median_idx]
        
        # Extract bottom and compute aggregated
        bottom = forecasts[:, bottom_start:, :]
        aggregated = torch.einsum('mn,bnh->bmh', S, bottom)
        
        # Compute violations
        violation = forecasts - aggregated
        
        return {
            'max_violation': violation.abs().max().item(),
            'mean_violation': violation.abs().mean().item(),
            'rmse_violation': torch.sqrt(torch.pow(violation, 2).mean()).item()
        }


def create_sloth_trainer(
    model: nn.Module,
    hierarchy_df: pd.DataFrame,
    coherence_weight: float = 0.1,
    **kwargs
) -> SLOTHTrainer:
    """Factory function for SLOTH trainer"""
    hierarchy = HierarchyStructure(hierarchy_df)
    config = SLOTHConfig(coherence_weight=coherence_weight, **kwargs)
    return SLOTHTrainer(model, hierarchy, config)


if __name__ == "__main__":
    print("Testing SLOTH Implementation")
    print("=" * 50)
    
    # Create sample hierarchy
    hierarchy_data = []
    categories = ['CAT-01', 'CAT-02']
    for cat_idx, cat in enumerate(categories):
        for subcat_idx in range(2):
            subcat = f'SUBCAT-{cat_idx * 2 + subcat_idx:02d}'
            for sku_idx in range(3):
                sku = f'SKU-{cat_idx * 6 + subcat_idx * 3 + sku_idx:04d}'
                hierarchy_data.append({
                    'sku_id': sku,
                    'subcategory_id': subcat,
                    'category_id': cat
                })
    
    hierarchy_df = pd.DataFrame(hierarchy_data)
    print(f"Hierarchy: {len(hierarchy_df)} SKUs")
    
    # Create hierarchy structure
    hierarchy = HierarchyStructure(hierarchy_df, levels=['sku_id', 'subcategory_id', 'category_id'])
    print(f"Total series: {hierarchy.n_total}")
    print(f"Bottom series: {hierarchy.n_bottom}")
    print(f"Summing matrix shape: {hierarchy.S.shape}")
    
    # Test coherence loss
    print("\n" + "=" * 50)
    print("Testing Coherence Loss")
    
    config = SLOTHConfig(
        coherence_weight=0.1,
        quantiles=(0.1, 0.5, 0.9)
    )
    
    coherence_loss = CoherenceLoss(hierarchy)
    
    # Create sample forecasts
    batch_size = 4
    horizon = 13
    n_quantiles = 3
    
    # Incoherent forecasts (random)
    forecasts_incoherent = torch.randn(batch_size, hierarchy.n_total, horizon)
    loss_incoherent = coherence_loss(forecasts_incoherent)
    print(f"Incoherent loss: {loss_incoherent.item():.4f}")
    
    # Coherent forecasts (aggregated from bottom)
    bottom_forecasts = torch.randn(batch_size, hierarchy.n_bottom, horizon).abs()
    forecasts_coherent = hierarchy.aggregate(bottom_forecasts)
    loss_coherent = coherence_loss(forecasts_coherent)
    print(f"Coherent loss: {loss_coherent.item():.6f}")
    
    # Test SLOTH loss
    print("\n" + "=" * 50)
    print("Testing SLOTH Loss with Annealing")
    
    sloth_loss = SLOTHLoss(hierarchy, config)
    
    # Simulate training epochs
    targets = torch.randn(batch_size, hierarchy.n_total, horizon).abs()
    predictions = torch.randn(batch_size, hierarchy.n_total, horizon, n_quantiles).abs()
    
    for epoch in [0, 5, 10, 20]:
        sloth_loss.update_epoch(epoch)
        loss, components = sloth_loss(predictions, targets, return_components=True)
        print(f"Epoch {epoch}: weight={components['coherence_weight']:.3f}, "
              f"forecast={components['forecast_loss'].item():.4f}, "
              f"coherence={components['coherence_loss'].item():.4f}")
    
    # Test projection
    print("\n" + "=" * 50)
    print("Testing Coherence Projection")
    
    projected = hierarchy.project_to_coherent(forecasts_incoherent)
    loss_projected = coherence_loss(projected)
    print(f"Loss after projection: {loss_projected.item():.6f}")
    
    # Create simple model for integration test
    print("\n" + "=" * 50)
    print("Testing SLOTHWrapper Integration")
    
    class SimpleModel(nn.Module):
        def __init__(self, n_total, horizon):
            super().__init__()
            self.fc = nn.Linear(52, n_total * horizon * 3)
            self.n_total = n_total
            self.horizon = horizon
        
        def forward(self, x):
            out = self.fc(x)
            return out.view(-1, self.n_total, self.horizon, 3)
    
    base_model = SimpleModel(hierarchy.n_total, horizon)
    wrapped_model = SLOTHWrapper(base_model, hierarchy, config)
    
    x = torch.randn(batch_size, 52)
    output = wrapped_model(x)
    print(f"Output shape: {output.shape}")
    
    # Create trainer
    trainer = SLOTHTrainer(wrapped_model, hierarchy, config)
    coherence_metrics = trainer.check_coherence(output)
    print(f"Coherence check: {coherence_metrics}")
    
    print("\n" + "=" * 50)
    print("SLOTH implementation complete!")
