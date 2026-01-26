"""
Hierarchical Forecast Reconciliation

FR-4.1: Produce coherent forecasts across hierarchy levels (SKU → subcategory → category)
using reconciliation methods in the MVP.

FR-4.2: Include "SLOTH-track placeholder" indicating where hierarchy-aware learning
would integrate later.

Implements MinT (Minimum Trace) reconciliation for forecast coherence.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import date
import logging
from pathlib import Path
from scipy import linalg

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.schemas.data_contracts import (
    DemandForecastSummary, HierarchyMap, HierarchyLevel
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ReconciliationConfig:
    """Configuration for hierarchical reconciliation"""
    method: str = "mint"  # "mint", "bottom_up", "top_down", "ols"
    
    # MinT settings
    covariance_method: str = "shrink"  # "ols", "wls", "shrink", "sample"
    shrinkage_factor: float = 0.5
    
    # Validation
    check_coherence: bool = True
    coherence_tolerance: float = 1e-6
    
    # SLOTH placeholder (FR-4.2)
    sloth_enabled: bool = False  # Phase-2 feature flag


class HierarchyMatrix:
    """
    Builds and manages the summing matrix S for hierarchical reconciliation.
    
    For a hierarchy with:
    - n bottom-level series (SKUs)
    - m total series (all levels)
    
    S is an m x n matrix where S[i,j] = 1 if bottom series j contributes to series i
    """
    
    def __init__(self, hierarchy_map: pd.DataFrame):
        """
        Args:
            hierarchy_map: DataFrame with columns [sku_id, subcategory_id, category_id, region_id]
        """
        self.hierarchy_df = hierarchy_map
        self._build_structure()
    
    def _build_structure(self):
        """Build hierarchy structure and summing matrix"""
        df = self.hierarchy_df
        
        # Get unique entities at each level
        self.skus = sorted(df['sku_id'].unique())
        self.subcategories = sorted(df['subcategory_id'].unique())
        self.categories = sorted(df['category_id'].unique())
        
        # Total series = SKUs + subcategories + categories + 1 (total)
        self.n_bottom = len(self.skus)
        self.n_middle = len(self.subcategories)
        self.n_top = len(self.categories)
        self.n_total_series = self.n_bottom + self.n_middle + self.n_top + 1
        
        # Create index mappings
        self.sku_to_idx = {sku: i for i, sku in enumerate(self.skus)}
        
        # Build summing matrix S (m x n)
        # Order: [Total, Categories, Subcategories, SKUs]
        m = self.n_total_series
        n = self.n_bottom
        
        S = np.zeros((m, n))
        
        # Total row (sum of all SKUs)
        S[0, :] = 1
        
        # Category rows
        cat_start = 1
        for i, cat in enumerate(self.categories):
            cat_skus = df[df['category_id'] == cat]['sku_id'].values
            for sku in cat_skus:
                S[cat_start + i, self.sku_to_idx[sku]] = 1
        
        # Subcategory rows
        subcat_start = cat_start + self.n_top
        for i, subcat in enumerate(self.subcategories):
            subcat_skus = df[df['subcategory_id'] == subcat]['sku_id'].values
            for sku in subcat_skus:
                S[subcat_start + i, self.sku_to_idx[sku]] = 1
        
        # SKU rows (identity)
        sku_start = subcat_start + self.n_middle
        S[sku_start:, :] = np.eye(n)
        
        self.S = S
        self.series_names = (
            ['Total'] + 
            [f'Cat:{c}' for c in self.categories] +
            [f'Subcat:{s}' for s in self.subcategories] +
            self.skus
        )
        
        logger.info(f"Built hierarchy matrix: {m} total series, {n} bottom-level SKUs")
    
    def get_summing_matrix(self) -> np.ndarray:
        """Return the summing matrix S"""
        return self.S
    
    def get_series_index(self, entity_id: str, level: HierarchyLevel) -> int:
        """Get index of a series in the hierarchy"""
        if level == HierarchyLevel.CATEGORY:
            return 1 + self.categories.index(entity_id)
        elif level == HierarchyLevel.SUBCATEGORY:
            return 1 + self.n_top + self.subcategories.index(entity_id)
        elif level == HierarchyLevel.SKU:
            return 1 + self.n_top + self.n_middle + self.skus.index(entity_id)
        else:
            return 0  # Total
    
    def aggregate_bottom_up(self, sku_forecasts: np.ndarray) -> np.ndarray:
        """Aggregate SKU forecasts to all hierarchy levels"""
        return self.S @ sku_forecasts


class MinTReconciler:
    """
    Minimum Trace (MinT) optimal reconciliation.
    
    Finds reconciled forecasts that minimize trace of forecast error covariance
    while ensuring coherence (y_tilde = S @ b_tilde).
    
    Reference: Wickramasuriya, Athanasopoulos, Hyndman (2019)
    """
    
    def __init__(self, hierarchy: HierarchyMatrix, config: ReconciliationConfig):
        self.hierarchy = hierarchy
        self.config = config
        self.S = hierarchy.get_summing_matrix()
        
        # Compute reconciliation matrix G
        self._compute_reconciliation_matrix()
    
    def _compute_reconciliation_matrix(self):
        """
        Compute the reconciliation matrix G such that:
        y_tilde = S @ G @ y_hat
        
        For MinT: G = (S'WS)^{-1} S'W
        where W is the inverse of the forecast error covariance
        """
        S = self.S
        m, n = S.shape
        
        if self.config.covariance_method == "ols":
            # OLS: W = I (assumes equal variance, no correlation)
            W = np.eye(m)
        
        elif self.config.covariance_method == "wls":
            # WLS: W = diag(1/var) where var estimated from data
            # For MVP, use uniform variance
            W = np.eye(m)
        
        elif self.config.covariance_method == "shrink":
            # Shrinkage: W = (1-λ)I + λ*diag
            # Simplified for MVP
            W = np.eye(m) * (1 - self.config.shrinkage_factor) + \
                np.diag(np.ones(m)) * self.config.shrinkage_factor
        
        else:  # "sample" - would need historical forecast errors
            W = np.eye(m)
        
        # Compute G = (S'WS)^{-1} S'W
        StW = S.T @ W
        StWS = StW @ S
        
        try:
            StWS_inv = linalg.inv(StWS)
            self.G = StWS_inv @ StW
        except linalg.LinAlgError:
            logger.warning("Matrix inversion failed, using pseudo-inverse")
            self.G = linalg.pinv(StWS) @ StW
        
        # Reconciliation matrix P = S @ G
        self.P = S @ self.G
    
    def reconcile(self, base_forecasts: np.ndarray) -> np.ndarray:
        """
        Reconcile base forecasts to ensure coherence.
        
        Args:
            base_forecasts: Array of shape (m,) or (m, h) with base forecasts
                           m = number of series, h = forecast horizon
        
        Returns:
            Reconciled forecasts of same shape
        """
        if base_forecasts.ndim == 1:
            base_forecasts = base_forecasts.reshape(-1, 1)
        
        # Apply reconciliation: y_tilde = P @ y_hat
        reconciled = self.P @ base_forecasts
        
        # Ensure non-negative
        reconciled = np.maximum(reconciled, 0)
        
        if self.config.check_coherence:
            self._verify_coherence(reconciled)
        
        return reconciled.squeeze()
    
    def _verify_coherence(self, reconciled: np.ndarray):
        """Verify that reconciled forecasts are coherent"""
        if reconciled.ndim == 1:
            reconciled = reconciled.reshape(-1, 1)
        
        S = self.S
        n_bottom = S.shape[1]
        
        # Extract bottom-level forecasts
        bottom_idx = S.shape[0] - n_bottom
        bottom_forecasts = reconciled[bottom_idx:, :]
        
        # Compute aggregated
        aggregated = S @ bottom_forecasts
        
        # Check coherence
        diff = np.abs(reconciled - aggregated)
        max_diff = np.max(diff)
        
        if max_diff > self.config.coherence_tolerance:
            logger.warning(f"Coherence violation: max diff = {max_diff:.6f}")
        else:
            logger.debug(f"Coherence verified: max diff = {max_diff:.2e}")


class HierarchicalForecaster:
    """
    Main interface for hierarchical forecasting with reconciliation.
    
    FR-4.1: Produce coherent forecasts across hierarchy levels
    FR-4.2: SLOTH placeholder for future hierarchy-aware learning
    """
    
    def __init__(
        self,
        hierarchy_map: pd.DataFrame,
        config: Optional[ReconciliationConfig] = None
    ):
        self.config = config or ReconciliationConfig()
        self.hierarchy = HierarchyMatrix(hierarchy_map)
        
        # Initialize reconciler based on method
        if self.config.method == "mint":
            self.reconciler = MinTReconciler(self.hierarchy, self.config)
        else:
            self.reconciler = None  # Bottom-up doesn't need reconciler
        
        # SLOTH placeholder (FR-4.2)
        if self.config.sloth_enabled:
            logger.info("SLOTH hierarchy-aware learning: PLACEHOLDER - Phase 2")
            # Future: self.sloth_model = SLOTHModel(hierarchy)
    
    def reconcile_forecasts(
        self,
        forecasts: Dict[str, Dict[str, np.ndarray]],
        horizon: int = 13
    ) -> Dict[str, Dict[str, np.ndarray]]:
        """
        Reconcile forecasts across hierarchy.
        
        Args:
            forecasts: Dict[entity_id -> Dict[quantile -> forecast_array]]
                      e.g., {"SKU-001": {"q50": array([...])}}
            horizon: Forecast horizon in weeks
        
        Returns:
            Reconciled forecasts with same structure, plus aggregated levels
        """
        # Process each quantile separately
        quantiles = ['q10', 'q50', 'q90']
        reconciled_forecasts = {}
        
        for quantile in quantiles:
            # Build base forecast matrix (m x h)
            m = self.hierarchy.n_total_series
            base_matrix = np.zeros((m, horizon))
            
            # Fill in available forecasts
            for entity_id, entity_forecasts in forecasts.items():
                if quantile not in entity_forecasts:
                    continue
                
                forecast = entity_forecasts[quantile]
                
                # Determine level and index
                if entity_id in self.hierarchy.skus:
                    idx = self.hierarchy.get_series_index(entity_id, HierarchyLevel.SKU)
                elif entity_id in self.hierarchy.subcategories:
                    idx = self.hierarchy.get_series_index(entity_id, HierarchyLevel.SUBCATEGORY)
                elif entity_id in self.hierarchy.categories:
                    idx = self.hierarchy.get_series_index(entity_id, HierarchyLevel.CATEGORY)
                else:
                    continue
                
                base_matrix[idx, :len(forecast)] = forecast[:horizon]
            
            # Reconcile
            if self.config.method == "bottom_up":
                # Simple aggregation from SKU level
                sku_start = self.hierarchy.n_total_series - self.hierarchy.n_bottom
                sku_forecasts = base_matrix[sku_start:, :]
                reconciled_matrix = self.hierarchy.aggregate_bottom_up(sku_forecasts.T).T
            else:
                # MinT reconciliation
                reconciled_matrix = np.zeros_like(base_matrix)
                for h in range(horizon):
                    reconciled_matrix[:, h] = self.reconciler.reconcile(base_matrix[:, h])
            
            # Extract reconciled forecasts
            for i, series_name in enumerate(self.hierarchy.series_names):
                if series_name not in reconciled_forecasts:
                    reconciled_forecasts[series_name] = {}
                reconciled_forecasts[series_name][quantile] = reconciled_matrix[i, :]
        
        return reconciled_forecasts
    
    def create_forecast_summaries(
        self,
        reconciled_forecasts: Dict[str, Dict[str, np.ndarray]],
        start_date: date,
        model_version: str,
        run_id: str
    ) -> List[DemandForecastSummary]:
        """
        Convert reconciled forecasts to DemandForecastSummary objects.
        
        Returns summaries ready for export to vendor.
        """
        from datetime import timedelta
        
        summaries = []
        
        for entity_name, quantiles in reconciled_forecasts.items():
            # Determine hierarchy level
            if entity_name == 'Total':
                level = HierarchyLevel.REGION  # Use region for total
                entity_id = 'TOTAL'
            elif entity_name.startswith('Cat:'):
                level = HierarchyLevel.CATEGORY
                entity_id = entity_name.replace('Cat:', '')
            elif entity_name.startswith('Subcat:'):
                level = HierarchyLevel.SUBCATEGORY
                entity_id = entity_name.replace('Subcat:', '')
            else:
                level = HierarchyLevel.SKU
                entity_id = entity_name
            
            # Create summary for each week
            q10 = quantiles.get('q10', np.zeros(13))
            q50 = quantiles.get('q50', np.zeros(13))
            q90 = quantiles.get('q90', np.zeros(13))
            
            for week_idx in range(len(q50)):
                week_start = start_date + timedelta(weeks=week_idx)
                
                summary = DemandForecastSummary(
                    entity_id=entity_id,
                    entity_level=level,
                    week_start=week_start,
                    q10=float(max(0, q10[week_idx])),
                    q50=float(max(0, q50[week_idx])),
                    q90=float(max(0, q90[week_idx])),
                    model_version=model_version,
                    run_id=run_id
                )
                summaries.append(summary)
        
        return summaries


# =============================================================================
# SLOTH Placeholder (FR-4.2)
# =============================================================================

class SLOTHPlaceholder:
    """
    SLOTH (Simultaneous Learning of Time Series Hierarchies) Placeholder
    
    FR-4.2: Interface boundary for future hierarchy-aware learning integration.
    
    SLOTH would replace post-hoc reconciliation with joint learning that
    incorporates hierarchy constraints directly into the loss function.
    
    Phase 2 Implementation Notes:
    - Modify loss function to include coherence penalty
    - Train single model that produces coherent forecasts directly
    - Eliminate need for reconciliation step
    - Potentially improve forecast accuracy by sharing information across hierarchy
    
    Reference: Rangapuram et al. (2021) "End-to-End Learning of Coherent Probabilistic Forecasts"
    """
    
    def __init__(self, hierarchy: HierarchyMatrix):
        self.hierarchy = hierarchy
        self.S = hierarchy.get_summing_matrix()
        logger.info("SLOTH placeholder initialized - Phase 2 feature")
    
    def coherence_loss(self, predictions: np.ndarray) -> float:
        """
        Compute coherence loss for training.
        
        Loss = ||y - S @ b||^2
        where y = all predictions, b = bottom-level predictions
        
        This would be added to the main forecast loss during training.
        """
        m, n = self.S.shape
        bottom_idx = m - n
        
        bottom_preds = predictions[bottom_idx:]
        aggregated = self.S @ bottom_preds
        
        coherence_loss = np.sum((predictions - aggregated) ** 2)
        return coherence_loss
    
    def train_joint_model(self, data, **kwargs):
        """
        Placeholder for joint training with hierarchy constraints.
        
        Would modify the training loop to:
        1. Compute standard forecast loss
        2. Add coherence loss term
        3. Backpropagate through hierarchy structure
        """
        raise NotImplementedError("SLOTH training is a Phase 2 feature")


def create_hierarchical_forecaster(
    hierarchy_map: pd.DataFrame,
    config: Optional[ReconciliationConfig] = None
) -> HierarchicalForecaster:
    """Factory function for hierarchical forecaster"""
    return HierarchicalForecaster(hierarchy_map, config)


if __name__ == "__main__":
    # Test hierarchical reconciliation
    
    # Create sample hierarchy
    hierarchy_data = []
    categories = ['CAT-01', 'CAT-02']
    for cat_idx, cat in enumerate(categories):
        for subcat_idx in range(3):
            subcat = f'SUBCAT-{cat_idx * 3 + subcat_idx:02d}'
            for sku_idx in range(5):
                sku = f'SKU-{cat_idx * 15 + subcat_idx * 5 + sku_idx:04d}'
                hierarchy_data.append({
                    'sku_id': sku,
                    'subcategory_id': subcat,
                    'category_id': cat,
                    'region_id': 'REGION-01'
                })
    
    hierarchy_df = pd.DataFrame(hierarchy_data)
    
    # Create forecaster
    config = ReconciliationConfig(method="mint")
    forecaster = create_hierarchical_forecaster(hierarchy_df, config)
    
    # Generate sample base forecasts (SKU level only)
    np.random.seed(42)
    base_forecasts = {}
    for sku in forecaster.hierarchy.skus:
        base_demand = np.random.uniform(50, 200)
        trend = np.random.uniform(-0.02, 0.05)
        
        forecast = base_demand * (1 + trend) ** np.arange(13)
        noise = np.random.randn(13) * 0.1 * base_demand
        
        base_forecasts[sku] = {
            'q10': forecast * 0.8 + noise,
            'q50': forecast + noise,
            'q90': forecast * 1.3 + noise,
        }
    
    # Reconcile
    reconciled = forecaster.reconcile_forecasts(base_forecasts, horizon=13)
    
    print("\n=== Hierarchical Reconciliation Results ===")
    print(f"Input: {len(base_forecasts)} SKU forecasts")
    print(f"Output: {len(reconciled)} reconciled series")
    
    # Show sample
    print("\nSample reconciled forecasts (week 1):")
    for name in ['Total', 'Cat:CAT-01', 'Subcat:SUBCAT-00', 'SKU-0000']:
        if name in reconciled:
            q50 = reconciled[name]['q50'][0]
            print(f"  {name}: {q50:.1f}")
    
    # Verify coherence
    total_q50 = reconciled['Total']['q50'][0]
    sum_categories = sum(reconciled[f'Cat:{cat}']['q50'][0] for cat in categories)
    print(f"\nCoherence check:")
    print(f"  Total forecast: {total_q50:.1f}")
    print(f"  Sum of categories: {sum_categories:.1f}")
    print(f"  Difference: {abs(total_q50 - sum_categories):.6f}")
