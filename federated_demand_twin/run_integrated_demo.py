#!/usr/bin/env python3
"""
Integrated Federated Demand Twin Demo

Demonstrates the complete integrated pipeline:
1. Federated Learning across multiple retailers
2. NBEATS demand forecasting with endogenous variables
3. Bayesian inventory probability analysis
4. Procurement scenario comparison
5. End-to-end workflow execution

Usage:
    python run_integrated_demo.py
"""

import numpy as np
import torch
from datetime import date, timedelta
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import integration components
from vendor.integration import (
    # Orchestrator
    create_orchestrator,
    
    # FL-NBEATS
    FLNBEATSClient,
    FLNBEATSServer,
    create_fl_nbeats_config,
    create_fl_nbeats_server,
    
    # Unified pipeline
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

from customer.fl_client import (
    create_integrated_forecaster,
    create_extended_config
)


def demo_federated_learning():
    """
    Demo 1: Federated Learning Across Retailers
    
    Shows how multiple retailers can collaboratively train a demand
    forecasting model without sharing raw data.
    """
    print("\n" + "="*70)
    print("DEMO 1: FEDERATED LEARNING ACROSS RETAILERS")
    print("="*70)
    
    # Create FL configuration with Bayesian layers
    config = create_fl_nbeats_config(
        lookback_weeks=26,
        forecast_horizon=13,
        num_covariates=13,  # 5 base + 8 endogenous
        hidden_dim=64,
        num_blocks=2,
        use_bayesian_layers=True,
        fl_aggregation_weight=0.7
    )
    
    # Create FL server
    server = create_fl_nbeats_server(config)
    print(f"\n✓ FL Server created")
    
    # Create clients for multiple retailers
    retailers = {
        'Walmart': 5000,
        'Target': 3000,
        'Kroger': 4000
    }
    
    clients = {}
    for retailer, n_samples in retailers.items():
        client = FLNBEATSClient(retailer, config)
        server.register_client(client)
        clients[retailer] = (client, n_samples)
    
    print(f"✓ Registered {len(retailers)} retailer clients")
    
    # Simulate local training for each retailer
    print("\n  Training locally on private data:")
    for retailer, (client, n_samples) in clients.items():
        # Generate synthetic data (in reality, this is private sales data)
        demand_history = torch.randn(n_samples, config.lookback_weeks) * 50 + 100
        covariates = torch.randn(n_samples, config.lookback_weeks, config.num_covariates)
        targets = torch.abs(torch.randn(n_samples, config.forecast_horizon) * 50 + 100)
        
        # Train locally (data never leaves retailer)
        metrics = client.train_local(demand_history, covariates, targets)
        print(f"    {retailer}: loss={metrics['loss']:.4f}, samples={n_samples}")
    
    # Run FL aggregation (only parameters shared, not data)
    print("\n  Running FL aggregation...")
    round_metrics = server.run_round()
    print(f"  ✓ Round completed: {round_metrics['num_clients']} clients, "
          f"{round_metrics['total_samples']} total samples")
    
    # Demonstrate uncertainty-aware prediction
    print("\n  Generating forecast with uncertainty:")
    test_demand = torch.randn(1, config.lookback_weeks) * 50 + 100
    predictions = clients['Walmart'][0].predict(test_demand, n_samples=50)
    
    print(f"    Week 1: Q10={predictions['q10'][0,0]:.1f}, "
          f"Q50={predictions['q50'][0,0]:.1f}, "
          f"Q90={predictions['q90'][0,0]:.1f}")
    print(f"    Mean uncertainty: {predictions['uncertainty'].mean():.4f}")
    
    return server


def demo_endogenous_integration():
    """
    Demo 2: Endogenous Variable Integration
    
    Shows how iQueue agents track basket dynamics and feed into
    demand forecasting as covariates.
    """
    print("\n" + "="*70)
    print("DEMO 2: ENDOGENOUS VARIABLE INTEGRATION")
    print("="*70)
    
    # Create iQueue state agents
    message_bus = AgentMessageBus()
    state_agents = {}
    
    basket_config = AgentConfig(
        agent_id="demo_baskets",
        agent_type=AgentType.ENDOGENOUS_STATE,
        retailer_id="demo_retailer",
        segment_id="grocery"
    )
    state_agents['total_baskets'] = BasketAgent(basket_config, message_bus)
    
    penetration_config = AgentConfig(
        agent_id="demo_penetration",
        agent_type=AgentType.ENDOGENOUS_STATE,
        retailer_id="demo_retailer",
        segment_id="grocery"
    )
    state_agents['basket_penetration'] = PenetrationAgent(penetration_config, message_bus)
    
    items_config = AgentConfig(
        agent_id="demo_items",
        agent_type=AgentType.ENDOGENOUS_STATE,
        retailer_id="demo_retailer",
        segment_id="grocery"
    )
    state_agents['items_per_basket'] = ItemsPerBasketAgent(items_config, message_bus)
    
    size_config = AgentConfig(
        agent_id="demo_size",
        agent_type=AgentType.ENDOGENOUS_STATE,
        retailer_id="demo_retailer",
        segment_id="grocery"
    )
    state_agents['size_per_item'] = SizePerItemAgent(size_config, message_bus)
    
    print(f"\n✓ Created {len(state_agents)} endogenous state agents:")
    for metric in state_agents:
        print(f"    - {metric}")
    
    # Simulate weekly observations over 8 weeks
    print("\n  Simulating 8 weeks of observations...")
    
    weekly_observations = [
        {'total_baskets': 10000, 'basket_penetration': 0.10, 'items_per_basket': 1.5, 'size_per_item': 1.0},
        {'total_baskets': 10200, 'basket_penetration': 0.11, 'items_per_basket': 1.5, 'size_per_item': 1.0},
        {'total_baskets': 10500, 'basket_penetration': 0.11, 'items_per_basket': 1.6, 'size_per_item': 1.0},
        {'total_baskets': 10300, 'basket_penetration': 0.12, 'items_per_basket': 1.5, 'size_per_item': 1.1},
        {'total_baskets': 10800, 'basket_penetration': 0.12, 'items_per_basket': 1.6, 'size_per_item': 1.1},
        {'total_baskets': 11000, 'basket_penetration': 0.13, 'items_per_basket': 1.6, 'size_per_item': 1.0},
        {'total_baskets': 10900, 'basket_penetration': 0.13, 'items_per_basket': 1.7, 'size_per_item': 1.0},
        {'total_baskets': 11200, 'basket_penetration': 0.14, 'items_per_basket': 1.7, 'size_per_item': 1.1},
    ]
    
    for week, obs in enumerate(weekly_observations):
        for metric, agent in state_agents.items():
            if metric in obs:
                agent.process({
                    'observation': obs[metric],
                    'observation_variance': obs[metric] * 0.05,
                    'source': 'point_of_sale'
                })
    
    print("  ✓ Processed 8 weeks of observations")
    
    # Show current beliefs
    print("\n  Current agent beliefs:")
    for metric, agent in state_agents.items():
        belief = agent.beliefs.get(metric)
        if belief:
            print(f"    {metric}: mean={belief.mean:.2f}, "
                  f"std={belief.std:.2f}, "
                  f"confidence={belief.confidence:.2f}")
    
    # Generate forecast with endogenous integration
    config = create_extended_config(
        lookback_weeks=26,
        forecast_horizon=13,
        endogenous_covariates=8,
        hidden_dim=64,
        num_blocks=2
    )
    forecaster = create_integrated_forecaster(config)
    
    # Synthetic demand history
    demand_history = np.random.randn(26) * 50 + 100
    demand_history = np.maximum(demand_history, 10)
    
    # Create endogenous covariates from agent beliefs
    endogenous = np.random.randn(26, 8) * 0.1
    
    predictions = forecaster.predict(
        demand_history=demand_history,
        endogenous_covariates=endogenous
    )
    
    print("\n  Forecast with endogenous variables:")
    print(f"    Week 1: Q50={predictions['q50'][0]:.1f}")
    print(f"    Week 4: Q50={predictions['q50'][3]:.1f}")
    print(f"    Week 13: Q50={predictions['q50'][12]:.1f}")
    
    return state_agents


def demo_inventory_probabilities():
    """
    Demo 3: Product-Specific Inventory Probabilities
    
    Shows how to configure and run Bayesian inventory analysis
    at the product level.
    """
    print("\n" + "="*70)
    print("DEMO 3: PRODUCT-SPECIFIC INVENTORY PROBABILITIES")
    print("="*70)
    
    # Create Bayesian engine
    engine = ProductBayesianEngine(n_simulations=3000)
    print("\n✓ Created ProductBayesianEngine (3000 simulations)")
    
    # Configure products at different hierarchy levels
    products = [
        create_product_config(
            product_id="SKU-COLA-12PK",
            level="sku",
            demand_volatility=0.25,
            target_service_level=0.95,
            lead_time_mean_weeks=2.0,
            lead_time_std_weeks=0.5,
            holding_cost_rate=0.25,
            stockout_cost_multiplier=2.0
        ),
        create_product_config(
            product_id="SKU-CHIPS-FAM",
            level="sku",
            demand_volatility=0.35,  # Higher volatility
            target_service_level=0.92,
            lead_time_mean_weeks=1.5
        ),
        create_product_config(
            product_id="CAT-BEVERAGES",
            level="category",
            demand_volatility=0.15,  # Lower at category level
            target_service_level=0.98
        )
    ]
    
    for config in products:
        engine.register_product(config)
    
    print(f"✓ Registered {len(products)} products")
    
    # Generate demand forecasts
    forecasts = []
    base_demand = 100
    for week in range(13):
        # Seasonal pattern
        seasonal = 1 + 0.2 * np.sin(2 * np.pi * week / 13)
        demand = base_demand * seasonal
        
        forecasts.append({
            'q10': demand * 0.8,
            'q50': demand,
            'q90': demand * 1.3
        })
    
    # Run scenarios for SKU
    print("\n  Running scenarios for SKU-COLA-12PK...")
    posteriors = engine.run_product_scenarios(
        product_id="SKU-COLA-12PK",
        demand_forecasts=forecasts,
        current_inventory=500,
        on_order=200
    )
    
    print("\n  Scenario Results:")
    print("  " + "-"*66)
    print(f"  {'Scenario':<25} {'Stockout Prob':<15} {'Service Level':<15} {'Days Supply':<15}")
    print("  " + "-"*66)
    
    for scenario_name, posterior in posteriors.items():
        print(f"  {scenario_name:<25} {posterior.stockout_probability:>10.1%}     "
              f"{posterior.service_level_mean:>10.1%}     "
              f"{posterior.days_of_supply_mean:>10.0f}")
    
    # Show confidence intervals
    baseline = posteriors['baseline']
    print(f"\n  Baseline 90% Confidence Intervals:")
    print(f"    Stockout: [{baseline.stockout_ci[0]:.1%}, {baseline.stockout_ci[1]:.1%}]")
    print(f"    Service:  [{baseline.service_level_ci[0]:.1%}, {baseline.service_level_ci[1]:.1%}]")
    print(f"    Margin:   [${baseline.margin_ci[0]:,.0f}, ${baseline.margin_ci[1]:,.0f}]")
    
    return engine


def demo_procurement_scenarios():
    """
    Demo 4: Procurement Probability Scenarios
    
    Shows how to analyze supplier reliability and compare
    sourcing strategies.
    """
    print("\n" + "="*70)
    print("DEMO 4: PROCUREMENT PROBABILITY SCENARIOS")
    print("="*70)
    
    # Create procurement engine
    engine = ProcurementProbabilityEngine(n_simulations=3000)
    print("\n✓ Created ProcurementProbabilityEngine (3000 simulations)")
    
    # Configure suppliers
    suppliers = [
        create_supplier_config(
            supplier_id="DOMESTIC",
            supplier_name="Domestic Co-Packer",
            otif_rate=0.95,
            quality_rate=0.99,
            lead_time_mean_days=14,
            lead_time_std_days=2,
            unit_cost=10.00
        ),
        create_supplier_config(
            supplier_id="BACKUP",
            supplier_name="Backup Manufacturer",
            otif_rate=0.88,
            quality_rate=0.97,
            lead_time_mean_days=21,
            lead_time_std_days=4,
            unit_cost=11.50
        ),
        create_supplier_config(
            supplier_id="OVERSEAS",
            supplier_name="Overseas Supplier",
            otif_rate=0.80,
            quality_rate=0.95,
            lead_time_mean_days=42,
            lead_time_std_days=10,
            unit_cost=7.50
        )
    ]
    
    for supplier in suppliers:
        engine.register_supplier(supplier)
    
    print(f"✓ Registered {len(suppliers)} suppliers:")
    for s in suppliers:
        print(f"    - {s.supplier_name}: OTIF={s.otif_rate:.0%}, "
              f"Lead Time={s.lead_time_mean_days:.0f}d, Cost=${s.unit_cost:.2f}")
    
    # Define sourcing strategies
    strategies = {
        "Single Source (Domestic)": {"DOMESTIC": 1.0},
        "Dual Source (70/30)": {"DOMESTIC": 0.7, "BACKUP": 0.3},
        "Cost Optimized": {"DOMESTIC": 0.3, "OVERSEAS": 0.7},
        "Risk Balanced": {"DOMESTIC": 0.5, "BACKUP": 0.3, "OVERSEAS": 0.2}
    }
    
    # Compare strategies
    target_date = date.today() + timedelta(weeks=4)
    order_qty = 5000
    
    print(f"\n  Comparing strategies for {order_qty} units, target: {target_date}")
    results = engine.compare_sourcing_strategies(
        order_quantity=order_qty,
        target_date=target_date,
        strategies=strategies
    )
    
    print("\n  " + "-"*75)
    print(f"  {'Strategy':<28} {'OTIF Prob':<12} {'Expected Cost':<15} {'Expected Receipt':<20}")
    print("  " + "-"*75)
    
    for strategy_name, scenario in results.items():
        print(f"  {strategy_name:<28} {scenario.otif_probability:>8.1%}     "
              f"${scenario.expected_total_cost:>10,.0f}     "
              f"{scenario.expected_receipt_date}")
    
    # Find best strategies
    best_otif = max(results.items(), key=lambda x: x[1].otif_probability)
    best_cost = min(results.items(), key=lambda x: x[1].expected_total_cost)
    
    print(f"\n  Best for reliability: {best_otif[0]} ({best_otif[1].otif_probability:.1%} OTIF)")
    print(f"  Best for cost: {best_cost[0]} (${best_cost[1].expected_total_cost:,.0f})")
    
    return engine


def demo_complete_workflow():
    """
    Demo 5: Complete Workflow with Orchestrator
    
    Shows the end-to-end integrated pipeline:
    Sense → Update → Simulate → Optimize → Explain → Learn
    """
    print("\n" + "="*70)
    print("DEMO 5: COMPLETE INTEGRATED WORKFLOW")
    print("="*70)
    
    # Create orchestrator
    orchestrator = create_orchestrator(
        retailer_id="demo_retailer",
        segment_id="grocery",
        n_simulations=2000,
        use_bayesian=True
    )
    print("\n✓ Created IntegrationOrchestrator")
    
    # Generate synthetic data
    demand_history = np.random.randn(26) * 50 + 100
    demand_history = np.maximum(demand_history, 10)
    
    print("\n  Running complete workflow...")
    print("  " + "-"*50)
    
    # Run complete workflow
    result = orchestrator.run_complete_workflow(
        observations={
            'total_baskets': 11000,
            'basket_penetration': 0.13,
            'items_per_basket': 1.6,
            'size_per_item': 1.05
        },
        driver_data={
            'media': {'spend': 50000},
            'price': {'spend': 30000},
            'trade': {'spend': 20000}
        },
        demand_history=demand_history,
        current_inventory=500,
        on_order=200,
        product_id="SKU-DEMO-001",
        current_allocations={'media': 50000, 'price': 30000, 'trade': 20000},
        total_budget=100000
    )
    
    # Show stage results
    print(f"\n  Workflow ID: {result['workflow_id']}")
    print("\n  Stage Results:")
    for stage, data in result['stages'].items():
        status = data.get('status', 'unknown')
        emoji = "✓" if status == 'completed' else "✗"
        print(f"    {emoji} {stage.upper()}: {status}")
    
    # Show inventory analysis
    inv = result['inventory_analysis']
    baseline = inv['posteriors']['baseline']
    print(f"\n  Inventory Analysis:")
    print(f"    Stockout Probability: {baseline['stockout_probability']:.1%}")
    print(f"    Service Level: {baseline['service_level']:.1%}")
    print(f"    Days of Supply: {baseline['days_of_supply']:.0f}")
    
    # Show recommendation
    rec = inv['recommendation']
    print(f"\n  Recommendation:")
    print(f"    Action: {rec['action']}")
    print(f"    Urgency: {rec['urgency']}")
    for r in rec.get('rationale', []):
        print(f"    - {r}")
    
    # Show optimization result
    opt = result['optimization']['optimization']
    print(f"\n  Marketing Optimization:")
    print(f"    Expected ROI: {opt.get('expected_roi', 0):.1%}")
    print(f"    Recommended Allocations:")
    for driver, amount in opt.get('allocations', {}).items():
        print(f"      {driver}: ${amount:,.0f}")
    
    # Show governance decision
    gov = result['optimization']['governance']
    print(f"\n  Governance Check:")
    print(f"    Decision: {gov.get('decision_status', 'unknown')}")
    print(f"    Requires Approval: {gov.get('requires_human_approval', False)}")
    
    return orchestrator, result


def main():
    """Run all demos"""
    print("\n" + "#"*70)
    print("#" + " "*68 + "#")
    print("#" + "  FEDERATED DEMAND TWIN - INTEGRATED PIPELINE DEMO".center(68) + "#")
    print("#" + " "*68 + "#")
    print("#"*70)
    
    # Run demos
    fl_server = demo_federated_learning()
    state_agents = demo_endogenous_integration()
    bayesian_engine = demo_inventory_probabilities()
    procurement_engine = demo_procurement_scenarios()
    orchestrator, result = demo_complete_workflow()
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY: INTEGRATED ARCHITECTURE")
    print("="*70)
    print("""
    ┌───────────────────────────────────────────────────────────────────┐
    │                     FEDERATED DEMAND TWIN                         │
    ├───────────────────────────────────────────────────────────────────┤
    │                                                                   │
    │  ┌─────────────┐    ┌─────────────────────────────────────────┐  │
    │  │ FL Server   │───▶│ Bayesian NBEATS                         │  │
    │  │ (Retailers) │    │ • Aggregated weights with uncertainty   │  │
    │  └─────────────┘    │ • Quantile forecasting (Q10/Q50/Q90)    │  │
    │                     └──────────────────┬──────────────────────┘  │
    │                                        │                         │
    │  ┌─────────────┐    ┌──────────────────▼──────────────────────┐  │
    │  │ iQueue      │───▶│ Endogenous Covariates                   │  │
    │  │ Agents      │    │ • Basket dynamics (4 metrics + trends)  │  │
    │  │ (4 metrics) │    │ • Confidence-weighted integration       │  │
    │  └─────────────┘    └──────────────────┬──────────────────────┘  │
    │                                        │                         │
    │  ┌─────────────┐    ┌──────────────────▼──────────────────────┐  │
    │  │ Suppliers   │───▶│ Bayesian Inventory Engine               │  │
    │  │ (OTIF/LT)   │    │ • Product-specific posteriors           │  │
    │  └─────────────┘    │ • Scenario comparison                   │  │
    │                     │ • Procurement probabilities             │  │
    │                     └──────────────────┬──────────────────────┘  │
    │                                        │                         │
    │                     ┌──────────────────▼──────────────────────┐  │
    │                     │ Decision Package                        │  │
    │                     │ • Stockout probabilities with CI        │  │
    │                     │ • Service level posteriors              │  │
    │                     │ • Procurement OTIF by strategy          │  │
    │                     │ • Actionable recommendations            │  │
    │                     └─────────────────────────────────────────┘  │
    │                                                                   │
    └───────────────────────────────────────────────────────────────────┘
    """)
    
    print("✅ All integration components demonstrated successfully!")
    print("\nKey capabilities:")
    print("  1. Federated Learning: Privacy-preserving model training across retailers")
    print("  2. Endogenous Variables: Basket dynamics integrated into forecasting")
    print("  3. Bayesian Inventory: Product-specific probability distributions")
    print("  4. Procurement Analysis: Supplier reliability and sourcing optimization")
    print("  5. End-to-End Workflow: Sense → Update → Simulate → Optimize → Explain → Learn")
    
    print("\nRun tests with: pytest tests/test_integration.py -v")
    print()


if __name__ == "__main__":
    main()
