"""
Complete Pipeline Demonstration

Shows how all components work together:
1. Federated Learning aggregation across retailers
2. NBEATS demand forecasting with endogenous variables
3. Bayesian inventory probability computation
4. Procurement scenario analysis

This answers the key architecture questions:
- How to configure product-specific inventory probabilities
- How to run procurement probability scenarios
- How to incorporate FL + endogenous variables into NBEATS
"""

import numpy as np
import torch
from datetime import date, timedelta
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import integration components
from vendor.integration import (
    # FL-NBEATS
    FLNBEATSConfig,
    FLNBEATSClient,
    FLNBEATSServer,
    FLIntegratedForecaster,
    create_fl_nbeats_config,
    create_fl_nbeats_server,
    create_fl_integrated_forecaster,
    
    # Unified pipeline
    UnifiedPipeline,
    ProductConfig,
    ProductLevel,
    SupplierConfig,
    EndogenousBridge,
    EndogenousState,
    ProcurementProbabilityEngine,
    ProductBayesianEngine,
    create_unified_pipeline,
    create_product_config,
    create_supplier_config
)

# Import iQueue agents
from vendor.agents.iqueue import (
    create_state_agent_ensemble,
    AgentMessageBus
)


def demo_fl_nbeats_integration():
    """
    Demonstrates FL-NBEATS integration.
    
    Shows:
    - Multi-retailer federated learning
    - Bayesian weight aggregation
    - Uncertainty-aware forecasting
    """
    print("\n" + "="*60)
    print("DEMO 1: Federated Learning + NBEATS Integration")
    print("="*60)
    
    # 1. Create FL configuration
    config = create_fl_nbeats_config(
        lookback_weeks=26,
        forecast_horizon=13,
        num_covariates=13,  # 5 base + 8 endogenous
        hidden_dim=64,
        num_blocks=2,
        use_bayesian_layers=True,
        fl_aggregation_weight=0.7
    )
    
    # 2. Create FL server
    server = create_fl_nbeats_server(config)
    
    # 3. Create clients for multiple retailers
    retailers = ['RetailerA', 'RetailerB', 'RetailerC']
    clients = {}
    
    for retailer in retailers:
        client = FLNBEATSClient(retailer, config)
        server.register_client(client)
        clients[retailer] = client
    
    print(f"\nRegistered {len(retailers)} retailer clients")
    
    # 4. Simulate local training for each retailer
    for retailer, client in clients.items():
        # Generate synthetic data
        n_samples = 100
        demand_history = torch.randn(n_samples, config.lookback_weeks) * 50 + 100
        covariates = torch.randn(n_samples, config.lookback_weeks, config.num_covariates)
        targets = torch.randn(n_samples, config.forecast_horizon) * 50 + 100
        
        # Train locally
        metrics = client.train_local(demand_history, covariates, targets)
        print(f"  {retailer}: loss={metrics['loss']:.4f}, samples={metrics['samples']}")
    
    # 5. Run FL aggregation round
    round_metrics = server.run_round()
    print(f"\nFL Round completed: {round_metrics}")
    
    # 6. Generate forecast with uncertainty
    forecaster = FLIntegratedForecaster('TestRetailer', config)
    forecaster.update_from_fl_server(server)
    
    test_demand = np.random.randn(26) * 50 + 100
    test_covariates = np.random.randn(26, 13)
    
    predictions = forecaster.predict(test_demand, test_covariates)
    
    print(f"\nForecast Results (13-week horizon):")
    print(f"  Q10 (week 1): {predictions['q10'][0, 0]:.1f}")
    print(f"  Q50 (week 1): {predictions['q50'][0, 0]:.1f}")
    print(f"  Q90 (week 1): {predictions['q90'][0, 0]:.1f}")
    print(f"  Mean uncertainty: {predictions['uncertainty'].mean():.4f}")
    
    return forecaster


def demo_endogenous_integration():
    """
    Demonstrates endogenous variable integration.
    
    Shows:
    - iQueue agent state extraction
    - Conversion to NBEATS covariates
    - Trend tracking
    """
    print("\n" + "="*60)
    print("DEMO 2: Endogenous Variable Integration")
    print("="*60)
    
    # 1. Create iQueue state agents
    message_bus = AgentMessageBus()
    state_agents = create_state_agent_ensemble(
        retailer_id="demo_retailer",
        segment_id="grocery",
        message_bus=message_bus
    )
    
    print(f"\nCreated {len(state_agents)} endogenous state agents:")
    for metric, agent in state_agents.items():
        print(f"  - {metric}: {agent.config.agent_id}")
    
    # 2. Simulate agent updates
    for metric, agent in state_agents.items():
        observation = {
            'total_baskets': 1000 + np.random.randn() * 50,
            'basket_penetration': 0.1 + np.random.randn() * 0.01,
            'items_per_basket': 1.5 + np.random.randn() * 0.1,
            'size_per_item': 1.0 + np.random.randn() * 0.05
        }.get(metric, 100)
        
        result = agent.process({
            'observation': observation,
            'observation_variance': abs(observation * 0.1),
            'source': 'demo'
        })
    
    # 3. Create endogenous bridge
    bridge = EndogenousBridge(lookback_weeks=26)
    
    # 4. Update bridge from agents
    state = bridge.update_from_agents(
        basket_agent=state_agents['total_baskets'],
        penetration_agent=state_agents['basket_penetration'],
        items_agent=state_agents['items_per_basket'],
        size_agent=state_agents['size_per_item']
    )
    
    print(f"\nEndogenous State:")
    print(f"  Total Baskets: {state.total_baskets:.0f}")
    print(f"  Penetration: {state.basket_penetration:.3f}")
    print(f"  Items/Basket: {state.items_per_basket:.2f}")
    print(f"  Size/Item: {state.size_per_item:.2f}")
    print(f"  Derived Total Units: {state.total_units:.0f}")
    print(f"  Confidence: {state.confidence:.2f}")
    
    # 5. Get covariate matrix
    covariate_matrix = bridge.get_covariate_matrix()
    print(f"\nCovariate Matrix Shape: {covariate_matrix.shape}")
    print(f"  (lookback_weeks x n_endogenous_features)")
    
    return bridge, state_agents


def demo_procurement_scenarios():
    """
    Demonstrates procurement probability scenarios.
    
    Shows:
    - Supplier configuration
    - OTIF probability computation
    - Multi-sourcing comparison
    """
    print("\n" + "="*60)
    print("DEMO 3: Procurement Probability Scenarios")
    print("="*60)
    
    # 1. Create procurement engine
    engine = ProcurementProbabilityEngine(n_simulations=5000)
    
    # 2. Configure suppliers
    supplier_a = create_supplier_config(
        supplier_id="SUP_A",
        supplier_name="Primary Supplier",
        otif_rate=0.95,
        quality_rate=0.99,
        lead_time_mean_days=14,
        lead_time_std_days=2,
        unit_cost=10.0
    )
    
    supplier_b = create_supplier_config(
        supplier_id="SUP_B",
        supplier_name="Backup Supplier",
        otif_rate=0.90,
        quality_rate=0.98,
        lead_time_mean_days=21,
        lead_time_std_days=4,
        unit_cost=11.0
    )
    
    supplier_c = create_supplier_config(
        supplier_id="SUP_C",
        supplier_name="Overseas Supplier",
        otif_rate=0.85,
        quality_rate=0.97,
        lead_time_mean_days=35,
        lead_time_std_days=7,
        unit_cost=8.0
    )
    
    engine.register_supplier(supplier_a)
    engine.register_supplier(supplier_b)
    engine.register_supplier(supplier_c)
    
    print(f"\nRegistered {len(engine.suppliers)} suppliers")
    
    # 3. Define sourcing strategies
    strategies = {
        "single_source_A": {"SUP_A": 1.0},
        "dual_source_AB": {"SUP_A": 0.7, "SUP_B": 0.3},
        "diversified": {"SUP_A": 0.5, "SUP_B": 0.3, "SUP_C": 0.2}
    }
    
    # 4. Compare strategies
    target_date = date.today() + timedelta(weeks=3)
    order_qty = 1000
    
    results = engine.compare_sourcing_strategies(
        order_quantity=order_qty,
        target_date=target_date,
        strategies=strategies
    )
    
    print(f"\nProcurement Scenario Comparison (Order: {order_qty} units, Target: {target_date})")
    print("-" * 70)
    print(f"{'Strategy':<20} {'OTIF Prob':<12} {'Exp. Cost':<12} {'Exp. Receipt':<15}")
    print("-" * 70)
    
    for strategy_name, scenario in results.items():
        print(f"{strategy_name:<20} {scenario.otif_probability:.1%}         "
              f"${scenario.expected_total_cost:,.0f}       "
              f"{scenario.expected_receipt_date}")
    
    return engine, results


def demo_product_inventory_probabilities():
    """
    Demonstrates product-specific inventory probability configuration.
    
    Shows:
    - Product hierarchy configuration
    - Inventory probability computation
    - Scenario comparison
    """
    print("\n" + "="*60)
    print("DEMO 4: Product-Specific Inventory Probabilities")
    print("="*60)
    
    # 1. Create Bayesian engine
    engine = ProductBayesianEngine(n_simulations=5000)
    
    # 2. Configure products at different hierarchy levels
    sku_config = create_product_config(
        product_id="SKU-12345",
        level="sku",
        demand_volatility=0.25,
        target_service_level=0.95,
        lead_time_mean_weeks=2.0,
        lead_time_std_weeks=0.5,
        holding_cost_rate=0.25,
        stockout_cost_multiplier=2.0
    )
    
    category_config = create_product_config(
        product_id="CAT-BEVERAGES",
        level="category",
        demand_volatility=0.15,  # Lower volatility at category level
        target_service_level=0.98
    )
    
    engine.register_product(sku_config)
    engine.register_product(category_config)
    
    print(f"\nRegistered products:")
    print(f"  - {sku_config.product_id} ({sku_config.level.value})")
    print(f"  - {category_config.product_id} ({category_config.level.value})")
    
    # 3. Generate demand forecasts
    demand_forecasts = [
        {'q10': 80, 'q50': 100, 'q90': 130},
        {'q10': 85, 'q50': 105, 'q90': 140},
        {'q10': 90, 'q50': 110, 'q90': 145},
        {'q10': 95, 'q50': 115, 'q90': 150},
        {'q10': 100, 'q50': 120, 'q90': 155},
        {'q10': 95, 'q50': 115, 'q90': 150},
        {'q10': 90, 'q50': 110, 'q90': 145},
        {'q10': 85, 'q50': 105, 'q90': 140},
        {'q10': 80, 'q50': 100, 'q90': 135},
        {'q10': 75, 'q50': 95, 'q90': 125},
        {'q10': 70, 'q50': 90, 'q90': 120},
        {'q10': 65, 'q50': 85, 'q90': 115},
        {'q10': 60, 'q50': 80, 'q90': 110}
    ]
    
    # 4. Run scenarios
    current_inventory = 500
    on_order = 200
    
    posteriors = engine.run_product_scenarios(
        product_id="SKU-12345",
        demand_forecasts=demand_forecasts,
        current_inventory=current_inventory,
        on_order=on_order
    )
    
    print(f"\nInventory Probability Scenarios (Current Inv: {current_inventory}, On Order: {on_order})")
    print("-" * 80)
    print(f"{'Scenario':<25} {'Stockout Prob':<15} {'Service Level':<15} {'Days Supply':<15}")
    print("-" * 80)
    
    for scenario_name, posterior in posteriors.items():
        print(f"{scenario_name:<25} {posterior.stockout_probability:.1%}            "
              f"{posterior.service_level_mean:.1%}           "
              f"{posterior.days_of_supply_mean:.0f}")
    
    # 5. Show confidence intervals
    baseline = posteriors['baseline']
    print(f"\nBaseline Confidence Intervals (90%):")
    print(f"  Stockout: [{baseline.stockout_ci[0]:.1%}, {baseline.stockout_ci[1]:.1%}]")
    print(f"  Service:  [{baseline.service_level_ci[0]:.1%}, {baseline.service_level_ci[1]:.1%}]")
    print(f"  Margin:   [${baseline.margin_ci[0]:,.0f}, ${baseline.margin_ci[1]:,.0f}]")
    
    return engine, posteriors


def demo_unified_pipeline():
    """
    Demonstrates the complete unified pipeline.
    
    Shows full integration:
    - FL → NBEATS → Endogenous → Bayesian
    """
    print("\n" + "="*60)
    print("DEMO 5: Unified Pipeline (End-to-End)")
    print("="*60)
    
    # 1. Create the unified pipeline
    pipeline = create_unified_pipeline(
        lookback_weeks=26,
        n_simulations=3000
    )
    
    print("\nUnifiedPipeline created with:")
    print(f"  - EndogenousBridge (lookback: 26 weeks)")
    print(f"  - ProcurementProbabilityEngine (3000 simulations)")
    print(f"  - ProductBayesianEngine (3000 simulations)")
    
    # 2. Register product
    product_config = create_product_config(
        product_id="PROD-001",
        level="sku",
        target_service_level=0.95,
        lead_time_mean_weeks=2.0
    )
    pipeline.bayesian_engine.register_product(product_config)
    
    # 3. Register suppliers
    suppliers = [
        create_supplier_config(
            supplier_id="MAIN",
            supplier_name="Main Supplier",
            otif_rate=0.95,
            lead_time_mean_days=14
        ),
        create_supplier_config(
            supplier_id="BACKUP",
            supplier_name="Backup Supplier",
            otif_rate=0.90,
            lead_time_mean_days=21
        )
    ]
    
    sourcing_strategies = {
        "primary_only": {"MAIN": 1.0},
        "split_70_30": {"MAIN": 0.7, "BACKUP": 0.3}
    }
    
    # 4. Generate synthetic demand history
    demand_history = np.random.randn(26) * 30 + 100
    demand_history = np.maximum(demand_history, 10)  # Ensure positive
    
    # 5. Run complete analysis
    result = pipeline.run_product_analysis(
        product_id="PROD-001",
        demand_history=demand_history,
        current_inventory=400,
        on_order=150,
        suppliers=suppliers,
        sourcing_strategies=sourcing_strategies
    )
    
    print(f"\nComplete Analysis Results for {result['product_id']}:")
    print(f"  Timestamp: {result['timestamp']}")
    
    print(f"\n  Demand Forecasts (first 4 weeks):")
    for i, f in enumerate(result['demand_forecasts'][:4]):
        print(f"    Week {i+1}: Q10={f['q10']:.0f}, Q50={f['q50']:.0f}, Q90={f['q90']:.0f}")
    
    print(f"\n  Procurement Scenarios:")
    for strategy, data in result['procurement_scenarios'].items():
        print(f"    {strategy}: OTIF={data['otif_probability']:.1%}, Cost=${data['expected_cost']:,.0f}")
    
    print(f"\n  Inventory Posteriors:")
    for scenario, posterior in result['posteriors'].items():
        print(f"    {scenario}: Stockout={posterior['stockout_probability']:.1%}, "
              f"Service={posterior['service_level']:.1%}")
    
    print(f"\n  Recommendation:")
    rec = result['recommendation']
    print(f"    Action: {rec['action']}")
    print(f"    Urgency: {rec['urgency']}")
    for r in rec.get('rationale', []):
        print(f"    - {r}")
    
    return pipeline, result


def main():
    """Run all demonstrations"""
    print("\n" + "#"*60)
    print("# FEDERATED DEMAND TWIN - COMPLETE PIPELINE DEMONSTRATION")
    print("#"*60)
    
    # Run each demo
    forecaster = demo_fl_nbeats_integration()
    bridge, state_agents = demo_endogenous_integration()
    procurement_engine, procurement_results = demo_procurement_scenarios()
    bayesian_engine, posteriors = demo_product_inventory_probabilities()
    pipeline, final_result = demo_unified_pipeline()
    
    print("\n" + "="*60)
    print("SUMMARY: Architecture Components Connected")
    print("="*60)
    print("""
    ┌─────────────────────────────────────────────────────────────┐
    │                    UNIFIED PIPELINE                         │
    ├─────────────────────────────────────────────────────────────┤
    │                                                             │
    │  ┌───────────────┐     ┌────────────────┐                  │
    │  │ FL Server     │────▶│ FL-NBEATS      │                  │
    │  │ (RetailerA,   │     │ (Bayesian      │                  │
    │  │  RetailerB,   │     │  weights)      │                  │
    │  │  RetailerC)   │     └───────┬────────┘                  │
    │  └───────────────┘             │                            │
    │                                ▼                            │
    │  ┌───────────────┐     ┌────────────────┐                  │
    │  │ iQueue Agents │────▶│ Endogenous     │──┐               │
    │  │ (Basket,      │     │ Bridge         │  │               │
    │  │  Penetration, │     │ (Covariates)   │  │               │
    │  │  Items, Size) │     └────────────────┘  │               │
    │  └───────────────┘                         │               │
    │                                            ▼               │
    │  ┌───────────────┐     ┌────────────────────────────┐      │
    │  │ Suppliers     │────▶│ Demand Forecasts           │      │
    │  │ (OTIF, Lead   │     │ (Q10/Q50/Q90 + Uncertainty)│      │
    │  │  Time, Cost)  │     └─────────────┬──────────────┘      │
    │  └───────┬───────┘                   │                     │
    │          │                           ▼                     │
    │          │         ┌─────────────────────────────────┐     │
    │          └────────▶│ Product Bayesian Engine         │     │
    │                    │ • Inventory Probabilities       │     │
    │                    │ • Procurement Scenarios         │     │
    │                    │ • Scenario Comparison           │     │
    │                    └─────────────┬───────────────────┘     │
    │                                  │                         │
    │                                  ▼                         │
    │                    ┌─────────────────────────────────┐     │
    │                    │ Decision Package                │     │
    │                    │ • Stockout Probabilities (CI)   │     │
    │                    │ • Service Level Posteriors      │     │
    │                    │ • Procurement OTIF              │     │
    │                    │ • Recommendations               │     │
    │                    └─────────────────────────────────┘     │
    │                                                             │
    └─────────────────────────────────────────────────────────────┘
    """)
    
    print("\n✅ All architecture components now connected!")
    print("\nKey Integrations Demonstrated:")
    print("  1. FL → NBEATS: Bayesian weight aggregation across retailers")
    print("  2. Endogenous → NBEATS: Basket dynamics as forecast covariates")
    print("  3. NBEATS → Bayesian: Quantile forecasts to inventory probabilities")
    print("  4. Suppliers → Bayesian: Procurement OTIF in stockout scenarios")
    print("  5. Unified Pipeline: End-to-end product-level analysis")


if __name__ == "__main__":
    main()
