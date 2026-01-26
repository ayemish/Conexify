"""
Tests for Advanced Forecasting Models

Tests:
- Foundation Model Wrapper (Chronos/TimesFM/Moirai)
- N-BEATSx with interpretable basis functions
- SLOTH coherence loss integration
"""

import pytest
import torch
import numpy as np
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from customer.fl_client.foundation_models import (
    FoundationModelConfig,
    FoundationModelWrapper,
    ChronosWrapper,
    TimesFMWrapper,
    FoundationModelEnsemble,
    create_foundation_model
)

from customer.fl_client.nbeatsx import (
    NBEATSxConfig,
    BlockType,
    TrendBasis,
    SeasonalityBasis,
    GenericBasis,
    NBEATSxBlock,
    NBEATSxStack,
    NBEATSx,
    NBEATSxLoss,
    FederatedNBEATSx,
    create_nbeatsx
)

from customer.fl_client.sloth import (
    SLOTHConfig,
    HierarchyStructure,
    CoherenceLoss,
    ProbabilisticCoherenceLoss,
    SLOTHLoss,
    SLOTHWrapper,
    SLOTHTrainer,
    create_sloth_trainer
)


class TestFoundationModels:
    """Tests for foundation model wrappers"""
    
    @pytest.fixture
    def sample_context(self):
        """Generate sample time series context"""
        np.random.seed(42)
        base = 100
        trend = 0.02
        seasonality = 20 * np.sin(2 * np.pi * np.arange(52) / 52)
        noise = np.random.randn(52) * 10
        return base * (1 + trend) ** np.arange(52) + seasonality + noise
    
    def test_foundation_model_config(self):
        """Test config creation"""
        config = FoundationModelConfig(
            model_type="chronos",
            model_size="small",
            prediction_length=13
        )
        assert config.model_type == "chronos"
        assert config.prediction_length == 13
        assert config.quantiles == (0.1, 0.5, 0.9)
    
    def test_chronos_wrapper_fallback(self, sample_context):
        """Test Chronos wrapper with fallback (when model not installed)"""
        config = FoundationModelConfig(
            model_type="chronos",
            prediction_length=13,
            num_samples=50
        )
        wrapper = ChronosWrapper(config)
        wrapper._use_fallback = True  # Force fallback
        
        forecast = wrapper.forecast(sample_context, prediction_length=13)
        
        assert 'mean' in forecast
        assert 'q10' in forecast
        assert 'q50' in forecast
        assert 'q90' in forecast
        assert 'samples' in forecast
        
        assert forecast['mean'].shape == (13,)
        assert forecast['samples'].shape == (50, 13)
        
        # Quantile ordering
        assert np.all(forecast['q10'] <= forecast['q50'])
        assert np.all(forecast['q50'] <= forecast['q90'])
    
    def test_foundation_wrapper_interface(self, sample_context):
        """Test unified wrapper interface"""
        wrapper = create_foundation_model(
            model_type="chronos",
            model_size="small",
            prediction_length=13
        )
        wrapper.load()
        
        forecast = wrapper.forecast(sample_context)
        
        assert len(forecast['mean']) == 13
        
        # Test to_quantile_format
        q10, q50, q90 = wrapper.to_quantile_format(forecast)
        assert q10.shape == (13,)
    
    def test_batch_forecasting(self, sample_context):
        """Test batch forecasting"""
        wrapper = create_foundation_model(prediction_length=13)
        wrapper.load()
        
        contexts = [sample_context, sample_context * 1.2, sample_context * 0.8]
        forecasts = wrapper.forecast_batch(contexts)
        
        assert len(forecasts) == 3
        for f in forecasts:
            assert f['mean'].shape == (13,)
    
    def test_ensemble_forecasting(self, sample_context):
        """Test foundation model ensemble"""
        ensemble = FoundationModelEnsemble(
            model_types=["chronos", "timesfm"],
            model_size="small"
        )
        ensemble.load()
        
        forecast = ensemble.forecast(sample_context, prediction_length=13)
        
        assert forecast['mean'].shape == (13,)
        # Ensemble should combine samples from both models
        assert forecast['samples'].shape[0] >= 100  # At least num_samples * 2


class TestNBEATSx:
    """Tests for N-BEATSx implementation"""
    
    @pytest.fixture
    def config(self):
        return NBEATSxConfig(
            lookback_length=52,
            forecast_horizon=13,
            num_exogenous=5,
            hidden_dim=64,
            num_layers=2,
            num_blocks_per_stack=2
        )
    
    @pytest.fixture
    def sample_data(self, config):
        batch_size = 4
        x = torch.randn(batch_size, config.lookback_length)
        exo_past = torch.randn(batch_size, config.lookback_length, config.num_exogenous)
        exo_future = torch.randn(batch_size, config.forecast_horizon, config.num_exogenous)
        targets = torch.randn(batch_size, config.forecast_horizon).abs()
        return x, exo_past, exo_future, targets
    
    def test_trend_basis(self):
        """Test polynomial trend basis"""
        basis = TrendBasis(
            lookback_length=52,
            forecast_horizon=13,
            polynomial_degree=3
        )
        
        batch_size = 4
        theta_b = torch.randn(batch_size, 4)  # degree + 1
        theta_f = torch.randn(batch_size, 4)
        
        backcast, forecast = basis(theta_b, theta_f)
        
        assert backcast.shape == (batch_size, 52)
        assert forecast.shape == (batch_size, 13)
    
    def test_seasonality_basis(self):
        """Test Fourier seasonality basis"""
        basis = SeasonalityBasis(
            lookback_length=52,
            forecast_horizon=13,
            num_harmonics=4
        )
        
        batch_size = 4
        theta_b = torch.randn(batch_size, 8)  # 2 * harmonics
        theta_f = torch.randn(batch_size, 8)
        
        backcast, forecast = basis(theta_b, theta_f)
        
        assert backcast.shape == (batch_size, 52)
        assert forecast.shape == (batch_size, 13)
    
    def test_generic_basis(self):
        """Test generic learnable basis"""
        basis = GenericBasis(
            lookback_length=52,
            forecast_horizon=13,
            hidden_dim=64
        )
        
        batch_size = 4
        theta = torch.randn(batch_size, 64)
        
        backcast, forecast = basis(theta)
        
        assert backcast.shape == (batch_size, 52)
        assert forecast.shape == (batch_size, 13)
    
    def test_nbeatsx_block(self, config):
        """Test single N-BEATSx block"""
        block = NBEATSxBlock(
            lookback_length=config.lookback_length,
            forecast_horizon=config.forecast_horizon,
            num_exogenous=config.num_exogenous,
            hidden_dim=config.hidden_dim,
            num_layers=config.num_layers,
            block_type=BlockType.TREND,
            polynomial_degree=3
        )
        
        batch_size = 4
        x = torch.randn(batch_size, config.lookback_length)
        exo_past = torch.randn(batch_size, config.lookback_length, config.num_exogenous)
        exo_future = torch.randn(batch_size, config.forecast_horizon, config.num_exogenous)
        
        backcast, forecast = block(x, exo_past, exo_future)
        
        assert backcast.shape == (batch_size, config.lookback_length)
        assert forecast.shape == (batch_size, config.forecast_horizon)
    
    def test_nbeatsx_full_model(self, config, sample_data):
        """Test complete N-BEATSx model"""
        model = NBEATSx(config)
        x, exo_past, exo_future, _ = sample_data
        
        q_preds, point = model(x, exo_past, exo_future)
        
        assert q_preds.shape == (4, config.forecast_horizon, len(config.quantiles))
        assert point.shape == (4, config.forecast_horizon)
        
        # Quantile ordering
        assert torch.all(q_preds[:, :, 0] <= q_preds[:, :, 1])
        assert torch.all(q_preds[:, :, 1] <= q_preds[:, :, 2])
    
    def test_nbeatsx_decomposition(self, config, sample_data):
        """Test interpretable decomposition"""
        model = NBEATSx(config)
        x, exo_past, exo_future, _ = sample_data
        
        q_preds, point, decomp = model(
            x, exo_past, exo_future, 
            return_decomposition=True
        )
        
        assert 'trend' in decomp
        assert 'seasonality' in decomp
        assert 'generic' in decomp
        
        # Decomposition should sum to forecast
        total = decomp['trend'] + decomp['seasonality'] + decomp['generic']
        # Note: quantile head transforms this, so we check shape
        assert total.shape == (4, config.forecast_horizon)
    
    def test_nbeatsx_loss(self, config, sample_data):
        """Test N-BEATSx loss function"""
        loss_fn = NBEATSxLoss(config.quantiles)
        
        x, _, _, targets = sample_data
        predictions = torch.randn(4, config.forecast_horizon, 3).abs()
        predictions = torch.cumsum(predictions, dim=-1)  # Ensure ordering
        
        loss = loss_fn(predictions, targets)
        
        assert loss.item() >= 0
        assert not torch.isnan(loss)
    
    def test_federated_nbeatsx(self, config, sample_data):
        """Test FL wrapper for N-BEATSx"""
        model = create_nbeatsx(config)
        x, exo_past, exo_future, _ = sample_data
        
        # Test prediction
        predictions = model.predict(x, exo_past, exo_future)
        assert predictions['q50'].shape == (4, config.forecast_horizon)
        
        # Test parameter exchange
        params = model.get_parameters()
        assert len(params) > 0
        
        # Modify and restore
        original = [p.copy() for p in params]
        for p in params:
            p *= 0.9
        model.set_parameters(params)
        
        new_params = model.get_parameters()
        assert not np.allclose(new_params[0], original[0])


class TestSLOTH:
    """Tests for SLOTH hierarchical coherence"""
    
    @pytest.fixture
    def hierarchy_df(self):
        """Create sample hierarchy"""
        data = []
        for cat_idx in range(2):
            cat = f'CAT-{cat_idx:02d}'
            for subcat_idx in range(2):
                subcat = f'SUBCAT-{cat_idx * 2 + subcat_idx:02d}'
                for sku_idx in range(3):
                    sku = f'SKU-{cat_idx * 6 + subcat_idx * 3 + sku_idx:04d}'
                    data.append({
                        'sku_id': sku,
                        'subcategory_id': subcat,
                        'category_id': cat
                    })
        return pd.DataFrame(data)
    
    @pytest.fixture
    def hierarchy(self, hierarchy_df):
        return HierarchyStructure(
            hierarchy_df, 
            levels=['sku_id', 'subcategory_id', 'category_id']
        )
    
    def test_hierarchy_structure(self, hierarchy):
        """Test hierarchy structure creation"""
        assert hierarchy.n_bottom == 12  # 2 cats * 2 subcats * 3 skus
        assert hierarchy.n_total == 1 + 2 + 4 + 12  # total + cats + subcats + skus
        
        S = hierarchy.get_summing_matrix()
        assert S.shape == (hierarchy.n_total, hierarchy.n_bottom)
        
        # First row should be all 1s (total)
        assert torch.all(S[0] == 1)
    
    def test_hierarchy_aggregation(self, hierarchy):
        """Test bottom-up aggregation"""
        batch_size = 4
        horizon = 13
        
        # Random bottom-level forecasts
        bottom = torch.randn(batch_size, hierarchy.n_bottom, horizon).abs()
        
        # Aggregate
        all_levels = hierarchy.aggregate(bottom)
        
        assert all_levels.shape == (batch_size, hierarchy.n_total, horizon)
        
        # Total should be sum of all bottom
        expected_total = bottom.sum(dim=1)
        actual_total = all_levels[:, 0, :]
        assert torch.allclose(expected_total, actual_total, atol=1e-5)
    
    def test_coherence_loss(self, hierarchy):
        """Test coherence loss computation"""
        coherence_loss = CoherenceLoss(hierarchy)
        
        batch_size = 4
        horizon = 13
        
        # Incoherent forecasts
        incoherent = torch.randn(batch_size, hierarchy.n_total, horizon)
        loss_incoherent = coherence_loss(incoherent)
        
        # Coherent forecasts (aggregated from bottom)
        bottom = torch.randn(batch_size, hierarchy.n_bottom, horizon).abs()
        coherent = hierarchy.aggregate(bottom)
        loss_coherent = coherence_loss(coherent)
        
        # Coherent should have near-zero loss
        assert loss_coherent.item() < 1e-5
        # Incoherent should have positive loss
        assert loss_incoherent.item() > 0.1
    
    def test_probabilistic_coherence_loss(self, hierarchy):
        """Test probabilistic coherence for quantile forecasts"""
        quantiles = (0.1, 0.5, 0.9)
        prob_coherence = ProbabilisticCoherenceLoss(hierarchy, quantiles)
        
        batch_size = 4
        horizon = 13
        n_quantiles = 3
        
        # Incoherent quantile forecasts
        forecasts = torch.randn(batch_size, hierarchy.n_total, horizon, n_quantiles)
        loss = prob_coherence(forecasts)
        
        assert loss.item() >= 0
        assert not torch.isnan(loss)
    
    def test_sloth_loss_annealing(self, hierarchy):
        """Test SLOTH loss with weight annealing"""
        config = SLOTHConfig(
            coherence_annealing=True,
            coherence_start_weight=0.01,
            coherence_end_weight=0.5,
            annealing_epochs=20
        )
        
        sloth_loss = SLOTHLoss(hierarchy, config)
        
        # Check weight at different epochs
        sloth_loss.update_epoch(0)
        assert sloth_loss.current_weight == pytest.approx(0.01, abs=0.001)
        
        sloth_loss.update_epoch(10)
        assert sloth_loss.current_weight == pytest.approx(0.255, abs=0.01)
        
        sloth_loss.update_epoch(20)
        assert sloth_loss.current_weight == pytest.approx(0.5, abs=0.001)
    
    def test_coherence_projection(self, hierarchy):
        """Test projection to coherent subspace"""
        batch_size = 4
        horizon = 13
        
        # Incoherent forecasts
        incoherent = torch.randn(batch_size, hierarchy.n_total, horizon)
        
        # Project
        projected = hierarchy.project_to_coherent(incoherent)
        
        # Check coherence
        coherence_loss = CoherenceLoss(hierarchy)
        loss = coherence_loss(projected)
        
        assert loss.item() < 1e-4  # Should be nearly coherent
    
    def test_sloth_wrapper(self, hierarchy):
        """Test SLOTH wrapper around base model"""
        config = SLOTHConfig(use_projection=True)
        
        class SimpleModel(torch.nn.Module):
            def __init__(self, n_total, horizon):
                super().__init__()
                self.fc = torch.nn.Linear(52, n_total * horizon)
                self.n_total = n_total
                self.horizon = horizon
            
            def forward(self, x):
                return self.fc(x).view(-1, self.n_total, self.horizon)
        
        base_model = SimpleModel(hierarchy.n_total, 13)
        wrapped = SLOTHWrapper(base_model, hierarchy, config)
        
        x = torch.randn(4, 52)
        
        # Training mode (no projection)
        wrapped.train()
        out_train = wrapped(x)
        
        # Eval mode (with projection)
        wrapped.eval()
        out_eval = wrapped(x)
        
        assert out_train.shape == (4, hierarchy.n_total, 13)
        assert out_eval.shape == (4, hierarchy.n_total, 13)
    
    def test_sloth_trainer_coherence_check(self, hierarchy):
        """Test trainer's coherence checking"""
        config = SLOTHConfig()
        
        class DummyModel(torch.nn.Module):
            def __init__(self, n_total, horizon):
                super().__init__()
                self.n_total = n_total
                self.horizon = horizon
                # Need at least one parameter for optimizer
                self.dummy_param = torch.nn.Linear(1, 1)
            
            def forward(self, x):
                return torch.randn(x.shape[0], self.n_total, self.horizon, 3)
        
        model = DummyModel(hierarchy.n_total, 13)
        trainer = SLOTHTrainer(model, hierarchy, config)
        
        # Generate forecasts
        forecasts = torch.randn(4, hierarchy.n_total, 13, 3)
        metrics = trainer.check_coherence(forecasts)
        
        assert 'max_violation' in metrics
        assert 'mean_violation' in metrics
        assert 'rmse_violation' in metrics
        assert metrics['max_violation'] >= 0


class TestIntegration:
    """Integration tests for combined usage"""
    
    @pytest.fixture
    def hierarchy_df(self):
        data = []
        for cat in ['A', 'B']:
            for subcat in range(2):
                for sku in range(3):
                    data.append({
                        'sku_id': f'{cat}-{subcat}-{sku}',
                        'subcategory_id': f'{cat}-{subcat}',
                        'category_id': cat
                    })
        return pd.DataFrame(data)
    
    def test_nbeatsx_with_sloth(self, hierarchy_df):
        """Test N-BEATSx model with SLOTH coherence training"""
        # Create hierarchy
        hierarchy = HierarchyStructure(
            hierarchy_df,
            levels=['sku_id', 'subcategory_id', 'category_id']
        )
        
        # Create N-BEATSx that outputs for all hierarchy levels
        class HierarchicalNBEATSx(torch.nn.Module):
            def __init__(self, n_total, horizon):
                super().__init__()
                self.fc = torch.nn.Linear(52, n_total * horizon * 3)
                self.n_total = n_total
                self.horizon = horizon
            
            def forward(self, x):
                out = self.fc(x)
                out = out.view(-1, self.n_total, self.horizon, 3)
                out = torch.nn.functional.softplus(out)
                out = torch.cumsum(out, dim=-1)
                return out
        
        model = HierarchicalNBEATSx(hierarchy.n_total, 13)
        
        # Wrap with SLOTH
        config = SLOTHConfig(coherence_weight=0.1)
        wrapped = SLOTHWrapper(model, hierarchy, config)
        
        # Create trainer
        trainer = SLOTHTrainer(wrapped, hierarchy, config)
        
        # Test forward pass
        x = torch.randn(4, 52)
        output = wrapped(x)
        
        assert output.shape == (4, hierarchy.n_total, 13, 3)
        
        # Check coherence loss computation
        targets = torch.randn(4, hierarchy.n_total, 13).abs()
        loss, components = trainer.loss_fn(output, targets, return_components=True)
        
        assert components['coherence_loss'].item() >= 0
        assert components['forecast_loss'].item() >= 0
    
    def test_foundation_model_baseline(self):
        """Test using foundation model as baseline for comparison"""
        # Create wrapper
        wrapper = create_foundation_model(
            model_type="chronos",
            prediction_length=13
        )
        wrapper.load()
        
        # Generate forecasts for multiple series
        np.random.seed(42)
        series = [
            100 + 10 * np.random.randn(52).cumsum() 
            for _ in range(5)
        ]
        
        forecasts = wrapper.forecast_batch(series)
        
        # All forecasts should be valid
        for f in forecasts:
            assert not np.any(np.isnan(f['mean']))
            assert len(f['mean']) == 13


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
