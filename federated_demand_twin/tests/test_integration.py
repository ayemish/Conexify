"""
Integration Tests for the Federated Demand Twin

Tests the complete pipeline:
1. FL → NBEATS integration
2. Endogenous variable integration
3. Bayesian inventory probabilities
4. Procurement scenarios
5. End-to-end orchestrator workflow
"""

import numpy as np
import torch
import pytest
from datetime import date, timedelta
import sys
from pathlib import Path

# Add parent paths
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import all components
from vendor.integration import (
    # Orchestrator
    create_orchestrator,
    OrchestratorConfig,
    IntegrationOrchestrator,
    
    # FL-NBEATS
    FLNBEATSConfig,
    FLNBEATSClient,
    FLNBEATSServer,
    create_fl_nbeats_config,
    create_fl_nbeats_server,
    
    # Unified pipeline
    EndogenousBridge,
    ProductBayesianEngine,
    ProcurementProbabilityEngine,
    create_product_config,
    create_supplier_config
)

from vendor.agents.iqueue import (
    AgentConfig,
    BasketAgent,
    PenetrationAgent,
    ItemsPerBasketAgent,
    SizePerItemAgent
)
from vendor.agents.iqueue.base import AgentType, AgentMessageBus

from customer.fl_client.extended_demand_model import (
    ExtendedModelConfig,
    IntegratedDemandForecaster,
    create_extended_config,
    create_integrated_forecaster
)


class TestFLNBEATSIntegration:
    """Test FL + NBEATS integration"""
    
    def test_fl_server_creation(self):
        """Test FL server can be created"""
        config = create_fl_nbeats_config(
            lookback_weeks=26,
            forecast_horizon=13,
            use_bayesian_layers=True
        )
        server = create_fl_nbeats_server(config)
        assert server is not None
        assert server.global_model is not None
    
    def test_fl_client_creation(self):
        """Test FL client can be created"""
        config = create_fl_nbeats_config()
        client = FLNBEATSClient("test_client", config)
        assert client is not None
        assert client.model is not None
    
    def test_fl_parameter_exchange(self):
        """Test FL parameter exchange between server and clients"""
        config = create_fl_nbeats_config(hidden_dim=32, num_blocks=1)
        server = create_fl_nbeats_server(config)
        
        # Create clients
        clients = []
        for i in range(3):
            client = FLNBEATSClient(f"client_{i}", config)
            server.register_client(client)
            clients.append(client)
        
        # Simulate local training
        for client in clients:
            demand = torch.randn(50, config.lookback_weeks)
            covariates = torch.randn(50, config.lookback_weeks, config.num_covariates)
            targets = torch.randn(50, config.forecast_horizon)
            client.train_local(demand, covariates, targets)
        
        # Run aggregation round
        metrics = server.run_round()
        
        assert 'num_clients' in metrics
        assert metrics['num_clients'] == 3
    
    def test_fl_forecast_with_uncertainty(self):
        """Test forecasting with uncertainty quantification"""
        config = create_fl_nbeats_config(use_bayesian_layers=True)
        client = FLNBEATSClient("test_client", config)
        
        # Generate prediction
        demand = torch.randn(1, config.lookback_weeks)
        predictions = client.predict(demand, n_samples=10)
        
        assert 'q10' in predictions
        assert 'q50' in predictions
        assert 'q90' in predictions
        assert predictions['q50'].shape[1] == config.forecast_horizon


class TestEndogenousIntegration:
    """Test endogenous variable integration"""
    
    def test_endogenous_bridge_creation(self):
        """Test endogenous bridge can be created"""
        bridge = EndogenousBridge(lookback_weeks=26)
        assert bridge is not None
        assert len(bridge.state_history) == 0
    
    def test_endogenous_bridge_with_agents(self):
        """Test endogenous bridge updates from iQueue agents"""
        message_bus = AgentMessageBus()
        
        # Create state agents
        state_agents = {}
        
        basket_config = AgentConfig(
            agent_id="test_baskets",
            agent_type=AgentType.ENDOGENOUS_STATE,
            retailer_id="test_retailer"
        )
        state_agents['total_baskets'] = BasketAgent(basket_config, message_bus)
        
        penetration_config = AgentConfig(
            agent_id="test_penetration",
            agent_type=AgentType.ENDOGENOUS_STATE,
            retailer_id="test_retailer"
        )
        state_agents['basket_penetration'] = PenetrationAgent(penetration_config, message_bus)
        
        items_config = AgentConfig(
            agent_id="test_items",
            agent_type=AgentType.ENDOGENOUS_STATE,
            retailer_id="test_retailer"
        )
        state_agents['items_per_basket'] = ItemsPerBasketAgent(items_config, message_bus)
        
        size_config = AgentConfig(
            agent_id="test_size",
            agent_type=AgentType.ENDOGENOUS_STATE,
            retailer_id="test_retailer"
        )
        state_agents['size_per_item'] = SizePerItemAgent(size_config, message_bus)
        
        # Update agents with observations
        for metric, agent in state_agents.items():
            obs = {
                'total_baskets': 1000,
                'basket_penetration': 0.1,
                'items_per_basket': 1.5,
                'size_per_item': 1.0
            }.get(metric, 100)
            
            agent.process({
                'observation': obs,
                'observation_variance': obs * 0.1,
                'source': 'test'
            })
        
        # Create bridge and update
        bridge = EndogenousBridge(lookback_weeks=26)
        state = bridge.update_from_agents(
            basket_agent=state_agents['total_baskets'],
            penetration_agent=state_agents['basket_penetration'],
            items_agent=state_agents['items_per_basket'],
            size_agent=state_agents['size_per_item']
        )
        
        assert state is not None
        assert state.total_baskets > 0
        assert len(bridge.state_history) == 1
    
    def test_covariate_matrix_generation(self):
        """Test covariate matrix generation"""
        bridge = EndogenousBridge(lookback_weeks=26)
        
        # Get matrix (should be zeros initially)
        matrix = bridge.get_covariate_matrix()
        assert matrix.shape == (26, 8)


class TestBayesianInventory:
    """Test Bayesian inventory probability engine"""
    
    def test_product_bayesian_engine_creation(self):
        """Test Bayesian engine creation"""
        engine = ProductBayesianEngine(n_simulations=100)
        assert engine is not None
    
    def test_product_config_registration(self):
        """Test product configuration"""
        engine = ProductBayesianEngine(n_simulations=100)
        
        config = create_product_config(
            product_id="SKU-001",
            level="sku",
            target_service_level=0.95,
            lead_time_mean_weeks=2.0
        )
        
        engine.register_product(config)
        assert "SKU-001" in engine.product_configs
    
    def test_inventory_probability_computation(self):
        """Test inventory probability computation"""
        engine = ProductBayesianEngine(n_simulations=500)
        
        # Register product
        config = create_product_config(
            product_id="SKU-001",
            level="sku"
        )
        engine.register_product(config)
        
        # Create demand forecasts
        forecasts = [
            {'q10': 80, 'q50': 100, 'q90': 130}
            for _ in range(13)
        ]
        
        # Compute posterior
        posterior = engine.compute_inventory_probabilities(
            product_id="SKU-001",
            demand_forecasts=forecasts,
            current_inventory=500,
            on_order=200
        )
        
        assert posterior.stockout_probability >= 0
        assert posterior.stockout_probability <= 1
        assert posterior.service_level_mean >= 0
        assert posterior.service_level_mean <= 1
    
    def test_scenario_comparison(self):
        """Test scenario comparison"""
        engine = ProductBayesianEngine(n_simulations=500)
        
        config = create_product_config(product_id="SKU-001", level="sku")
        engine.register_product(config)
        
        forecasts = [{'q10': 80, 'q50': 100, 'q90': 130} for _ in range(13)]
        
        posteriors = engine.run_product_scenarios(
            product_id="SKU-001",
            demand_forecasts=forecasts,
            current_inventory=500,
            on_order=200
        )
        
        assert 'baseline' in posteriors
        assert 'demand_up_20pct' in posteriors
        assert 'supply_disruption' in posteriors
        
        # All scenarios should have valid probabilities
        assert 0 <= posteriors['supply_disruption'].stockout_probability <= 1
        assert 0 <= posteriors['baseline'].stockout_probability <= 1


class TestProcurementScenarios:
    """Test procurement probability scenarios"""
    
    def test_procurement_engine_creation(self):
        """Test procurement engine creation"""
        engine = ProcurementProbabilityEngine(n_simulations=100)
        assert engine is not None
    
    def test_supplier_registration(self):
        """Test supplier registration"""
        engine = ProcurementProbabilityEngine(n_simulations=100)
        
        supplier = create_supplier_config(
            supplier_id="SUP-001",
            supplier_name="Test Supplier",
            otif_rate=0.95,
            lead_time_mean_days=14
        )
        
        engine.register_supplier(supplier)
        assert "SUP-001" in engine.suppliers
    
    def test_sourcing_strategy_comparison(self):
        """Test sourcing strategy comparison"""
        engine = ProcurementProbabilityEngine(n_simulations=500)
        
        # Register suppliers
        engine.register_supplier(create_supplier_config(
            supplier_id="A",
            supplier_name="Supplier A",
            otif_rate=0.95,
            lead_time_mean_days=14
        ))
        engine.register_supplier(create_supplier_config(
            supplier_id="B",
            supplier_name="Supplier B",
            otif_rate=0.85,
            lead_time_mean_days=21
        ))
        
        # Compare strategies
        strategies = {
            "single_A": {"A": 1.0},
            "dual": {"A": 0.7, "B": 0.3}
        }
        
        results = engine.compare_sourcing_strategies(
            order_quantity=1000,
            target_date=date.today() + timedelta(weeks=3),
            strategies=strategies
        )
        
        assert "single_A" in results
        assert "dual" in results
        assert results["single_A"].otif_probability is not None


class TestExtendedDemandModel:
    """Test extended demand model with endogenous covariates"""
    
    def test_model_creation(self):
        """Test model creation"""
        config = create_extended_config(
            lookback_weeks=26,
            forecast_horizon=13,
            use_bayesian=True
        )
        forecaster = create_integrated_forecaster(config)
        assert forecaster is not None
    
    def test_forward_pass(self):
        """Test forward pass with all covariates"""
        config = create_extended_config(hidden_dim=32, num_blocks=1)
        forecaster = create_integrated_forecaster(config)
        
        demand = np.random.randn(26) * 50 + 100
        base_cov = np.random.randn(26, 5)
        endogenous = np.random.randn(26, 8)
        
        predictions = forecaster.predict(
            demand_history=demand,
            base_covariates=base_cov,
            endogenous_covariates=endogenous
        )
        
        assert 'q10' in predictions
        assert 'q50' in predictions
        assert 'q90' in predictions
        assert len(predictions['q50']) == config.forecast_horizon
    
    def test_training_step(self):
        """Test training step"""
        config = create_extended_config(hidden_dim=32, num_blocks=1)
        forecaster = create_integrated_forecaster(config)
        
        demand = torch.randn(10, 26)
        targets = torch.randn(10, 13)
        
        metrics = forecaster.train_step(demand, targets)
        
        assert 'total_loss' in metrics
        assert 'pinball_loss' in metrics


class TestIntegrationOrchestrator:
    """Test the full integration orchestrator"""
    
    def test_orchestrator_creation(self):
        """Test orchestrator creation"""
        orchestrator = create_orchestrator(
            retailer_id="test_retailer",
            n_simulations=100
        )
        assert orchestrator is not None
    
    def test_state_agent_updates(self):
        """Test state agent updates"""
        orchestrator = create_orchestrator(
            retailer_id="test_retailer",
            n_simulations=100
        )
        
        observations = {
            'total_baskets': 1000,
            'basket_penetration': 0.1,
            'items_per_basket': 1.5,
            'size_per_item': 1.0
        }
        
        results = orchestrator.update_state_agents(observations)
        assert len(results) > 0
    
    def test_forecast_generation(self):
        """Test forecast generation"""
        orchestrator = create_orchestrator(
            retailer_id="test_retailer",
            n_simulations=100
        )
        
        demand_history = np.random.randn(26) * 50 + 100
        
        predictions = orchestrator.generate_forecast(
            demand_history=demand_history,
            include_endogenous=False
        )
        
        assert 'q50' in predictions
    
    def test_inventory_analysis(self):
        """Test inventory analysis"""
        orchestrator = create_orchestrator(
            retailer_id="test_retailer",
            n_simulations=500
        )
        
        demand_history = np.random.randn(26) * 50 + 100
        demand_history = np.maximum(demand_history, 10)
        
        result = orchestrator.run_inventory_analysis(
            product_id="SKU-001",
            demand_history=demand_history,
            current_inventory=500,
            on_order=200
        )
        
        assert 'posteriors' in result
        assert 'baseline' in result['posteriors']
        assert 'recommendation' in result
    
    def test_complete_workflow(self):
        """Test complete workflow execution"""
        orchestrator = create_orchestrator(
            retailer_id="test_retailer",
            n_simulations=200
        )
        
        result = orchestrator.run_complete_workflow(
            observations={
                'total_baskets': 1000,
                'basket_penetration': 0.1,
                'items_per_basket': 1.5,
                'size_per_item': 1.0
            },
            driver_data={
                'media': {'spend': 10000},
                'price': {'spend': 5000}
            },
            demand_history=np.maximum(np.random.randn(26) * 50 + 100, 10),
            current_inventory=500,
            on_order=200,
            product_id="SKU-001",
            current_allocations={'media': 10000, 'price': 5000, 'trade': 5000},
            total_budget=20000
        )
        
        assert 'workflow_id' in result
        assert 'stages' in result
        assert all(stage in result['stages'] for stage in 
                  ['sense', 'update', 'simulate', 'optimize', 'explain', 'learn'])
    
    def test_state_summary(self):
        """Test state summary"""
        orchestrator = create_orchestrator(
            retailer_id="test_retailer",
            n_simulations=100
        )
        
        summary = orchestrator.get_state_summary()
        
        assert 'retailer_id' in summary
        assert summary['retailer_id'] == 'test_retailer'


def run_tests():
    """Run all tests"""
    pytest.main([__file__, '-v', '--tb=short'])


if __name__ == "__main__":
    run_tests()
