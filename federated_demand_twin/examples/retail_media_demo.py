#!/usr/bin/env python3
"""
Retail Media Spend Optimization Demo

Demonstrates the complete Bayesian → Digital Twin → Agent pipeline
for retail media network optimization.

This demo:
1. Sets up retailers, channels, and SKUs
2. Simulates federated elasticity updates from multiple retailers
3. Runs the Digital Twin with Bayesian-calibrated posteriors
4. Executes the agent pipeline (Attribution, Scenario, Optimization, Governance, Rationale)
5. Produces a Decision Pack with recommendations and rationale

Usage:
    python examples/retail_media_demo.py
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import numpy as np
from datetime import datetime
import json

from vendor.retail_media.schemas import (
    MediaChannel,
    RetailerConfig,
    ChannelConfig,
    SKUConfig,
    MediaAllocation,
    AllocationStatus,
)

from vendor.retail_media.orchestrator import (
    RetailMediaOrchestrator,
    OrchestratorConfig,
)

from vendor.retail_media.bayesian_engine import BayesianEngineConfig
from vendor.retail_media.media_twin import TwinConfig
from vendor.retail_media.agents import AgentConfig


def print_header(title: str):
    """Print a formatted section header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_subheader(title: str):
    """Print a formatted subsection header"""
    print(f"\n--- {title} ---")


def setup_demo_orchestrator() -> RetailMediaOrchestrator:
    """Initialize the orchestrator with demo configuration"""
    print_header("INITIALIZING RETAIL MEDIA OPTIMIZATION SYSTEM")
    
    config = OrchestratorConfig(
        n_simulations=2000,  # Reduced for demo speed
        simulation_weeks=13,
        save_decision_packs=True,
        output_path="./reports/retail_media_demo"
    )
    
    orchestrator = RetailMediaOrchestrator(
        config=config,
        bayesian_config=BayesianEngineConfig(num_samples=2000),
        twin_config=TwinConfig(default_num_simulations=2000),
        agent_config=AgentConfig(max_scenarios=6)
    )
    
    print("✓ Orchestrator initialized")
    return orchestrator


def register_channels(orchestrator: RetailMediaOrchestrator):
    """Register media channels with priors"""
    print_subheader("Registering Media Channels")
    
    channel_configs = [
        ChannelConfig(
            channel=MediaChannel.SPONSORED_SEARCH,
            prior_elasticity_mean=0.18,
            prior_elasticity_std=0.04,
            adstock_decay=0.6
        ),
        ChannelConfig(
            channel=MediaChannel.IN_STORE_DISPLAY,
            prior_elasticity_mean=0.22,
            prior_elasticity_std=0.06,
            adstock_decay=0.5
        ),
        ChannelConfig(
            channel=MediaChannel.CONNECTED_TV,
            prior_elasticity_mean=0.10,
            prior_elasticity_std=0.05,
            adstock_decay=0.8
        ),
        ChannelConfig(
            channel=MediaChannel.EMAIL,
            prior_elasticity_mean=0.12,
            prior_elasticity_std=0.03,
            adstock_decay=0.4
        ),
        ChannelConfig(
            channel=MediaChannel.APP_NOTIFICATION,
            prior_elasticity_mean=0.08,
            prior_elasticity_std=0.03,
            adstock_decay=0.3
        ),
        ChannelConfig(
            channel=MediaChannel.WEBSITE_BANNER,
            prior_elasticity_mean=0.06,
            prior_elasticity_std=0.02,
            adstock_decay=0.5
        ),
    ]
    
    for config in channel_configs:
        orchestrator.register_channel(config)
        print(f"  ✓ {config.channel.value}: prior η={config.prior_elasticity_mean:.2f} ± {config.prior_elasticity_std:.2f}")


def register_retailers(orchestrator: RetailMediaOrchestrator) -> list:
    """Register retail media network partners"""
    print_subheader("Registering Retail Media Network Partners")
    
    retailers = [
        RetailerConfig(
            retailer_id="walmart",
            retailer_name="Walmart",
            available_channels=[
                MediaChannel.SPONSORED_SEARCH,
                MediaChannel.IN_STORE_DISPLAY,
                MediaChannel.WEBSITE_BANNER
            ],
            min_spend_share=0.15,
            avg_inventory_weeks=5.0,
            stockout_sensitivity=0.8,
            tier="premium",
            attribution_quality=0.9
        ),
        RetailerConfig(
            retailer_id="kroger",
            retailer_name="Kroger",
            available_channels=[
                MediaChannel.SPONSORED_SEARCH,
                MediaChannel.IN_STORE_DISPLAY,
                MediaChannel.EMAIL
            ],
            min_spend_share=0.12,
            avg_inventory_weeks=4.0,
            stockout_sensitivity=1.0,
            tier="premium",
            attribution_quality=0.85
        ),
        RetailerConfig(
            retailer_id="target",
            retailer_name="Target",
            available_channels=[
                MediaChannel.SPONSORED_SEARCH,
                MediaChannel.CONNECTED_TV,
                MediaChannel.APP_NOTIFICATION
            ],
            min_spend_share=0.10,
            avg_inventory_weeks=4.5,
            stockout_sensitivity=0.9,
            tier="premium",
            attribution_quality=0.88
        ),
        RetailerConfig(
            retailer_id="costco",
            retailer_name="Costco",
            available_channels=[
                MediaChannel.IN_STORE_DISPLAY,
                MediaChannel.EMAIL
            ],
            min_spend_share=0.08,
            avg_inventory_weeks=6.0,
            stockout_sensitivity=0.7,
            tier="standard",
            attribution_quality=0.75
        ),
        RetailerConfig(
            retailer_id="albertsons",
            retailer_name="Albertsons",
            available_channels=[
                MediaChannel.SPONSORED_SEARCH,
                MediaChannel.IN_STORE_DISPLAY
            ],
            min_spend_share=0.05,
            avg_inventory_weeks=3.5,
            stockout_sensitivity=1.2,
            tier="standard",
            attribution_quality=0.70
        ),
    ]
    
    for retailer in retailers:
        orchestrator.register_retailer(retailer)
        channels = ", ".join([c.value for c in retailer.available_channels])
        print(f"  ✓ {retailer.retailer_name} ({retailer.tier}): {channels}")
    
    return retailers


def register_skus(orchestrator: RetailMediaOrchestrator) -> list:
    """Register product SKUs"""
    print_subheader("Registering Product SKUs")
    
    skus = [
        SKUConfig(
            sku_id="bev-sparkling-12",
            sku_name="Sparkling Water 12pk",
            category="beverages",
            brand="AquaPure",
            unit_price=6.99,
            unit_cost=3.50,
            weekly_base_demand=150,
            demand_std=30,
            media_responsiveness=1.1
        ),
        SKUConfig(
            sku_id="bev-energy-4",
            sku_name="Energy Drink 4pk",
            category="beverages",
            brand="PowerUp",
            unit_price=9.99,
            unit_cost=5.00,
            weekly_base_demand=100,
            demand_std=25,
            media_responsiveness=1.3
        ),
        SKUConfig(
            sku_id="snk-protein-6",
            sku_name="Protein Bar 6pk",
            category="snacks",
            brand="FitFuel",
            unit_price=12.99,
            unit_cost=6.50,
            weekly_base_demand=80,
            demand_std=20,
            media_responsiveness=1.0
        ),
        SKUConfig(
            sku_id="snk-trail-16",
            sku_name="Trail Mix 16oz",
            category="snacks",
            brand="NatureBite",
            unit_price=7.99,
            unit_cost=4.00,
            weekly_base_demand=120,
            demand_std=25,
            media_responsiveness=0.9
        ),
    ]
    
    for sku in skus:
        orchestrator.register_sku(sku)
        margin = sku.unit_price - sku.unit_cost
        print(f"  ✓ {sku.sku_name}: ${sku.unit_price:.2f} (margin ${margin:.2f}), demand {sku.weekly_base_demand}/week")
    
    return skus


def initialize_twin_states(orchestrator: RetailMediaOrchestrator, retailers: list, skus: list):
    """Initialize Digital Twin state for all retailer-SKU combinations"""
    print_subheader("Initializing Digital Twin States")
    
    np.random.seed(42)  # Reproducibility
    
    state_count = 0
    for retailer in retailers:
        for sku in skus:
            # Retailer-specific demand variation
            demand_factor = 1.0 + np.random.uniform(-0.2, 0.3)
            
            orchestrator.initialize_twin_state(
                retailer_id=retailer.retailer_id,
                sku_id=sku.sku_id,
                initial_inventory=sku.weekly_base_demand * retailer.avg_inventory_weeks,
                base_demand_mean=sku.weekly_base_demand * demand_factor,
                base_demand_std=sku.demand_std
            )
            state_count += 1
    
    print(f"  ✓ Initialized {state_count} retailer-SKU states")
    print(f"  ✓ Twin state summary: {orchestrator.twin.get_state_summary()}")


def simulate_federated_elasticity_updates(orchestrator: RetailMediaOrchestrator, retailers: list):
    """
    Simulate federated learning: each retailer contributes local elasticity data
    without sharing raw data.
    """
    print_header("FEDERATED BAYESIAN LEARNING")
    print("Each retailer contributes local spend/lift data to update posteriors...")
    
    np.random.seed(123)
    
    categories = ["beverages", "snacks"]
    
    for retailer in retailers:
        print_subheader(f"Retailer: {retailer.retailer_name}")
        
        for channel in retailer.available_channels:
            for category in categories:
                # Simulate 26 weeks of historical data
                n_weeks = 26
                
                # Generate synthetic spend (varies by retailer size)
                base_spend = 50000 if retailer.tier == "premium" else 25000
                spend = np.random.uniform(0.5, 1.5, n_weeks) * base_spend
                
                # True elasticity with retailer variation
                true_elasticity = 0.15 + np.random.uniform(-0.05, 0.10)
                
                # Sales lift with noise
                noise = np.random.normal(0, 0.15, n_weeks)
                lift = spend / 50000 * true_elasticity * (1 + noise)
                lift = np.maximum(0.01, lift)
                
                # Update posterior
                posterior = orchestrator.update_elasticity_from_retailer_data(
                    retailer_id=retailer.retailer_id,
                    channel=channel,
                    category=category,
                    spend_history=spend,
                    sales_lift_history=lift
                )
                
                print(f"  {channel.value}:{category} → η={posterior.mean:.3f} "
                      f"[{posterior.ci_lower:.3f}, {posterior.ci_upper:.3f}] "
                      f"(evidence: {posterior.evidence_strength:.0%})")
    
    # Show federated aggregation
    print_subheader("Federated Posterior Aggregation")
    global_posteriors = orchestrator.bayesian_engine.federated_aggregator.get_all_global_posteriors()
    
    print("  Global posteriors (aggregated across all retailers):")
    for key, post in sorted(global_posteriors.items())[:6]:
        print(f"    {key}: η={post.mean:.3f} [{post.ci_lower:.3f}, {post.ci_upper:.3f}] "
              f"(n={post.n_observations} obs)")


def create_current_allocation(retailers: list, total_budget: float) -> MediaAllocation:
    """Create a sample current allocation"""
    spend = {}
    
    # Distribute budget across retailers (weighted by min_spend_share)
    total_min_share = sum(r.min_spend_share for r in retailers)
    
    for retailer in retailers:
        retailer_budget = total_budget * (retailer.min_spend_share / total_min_share)
        
        # Distribute across channels
        n_channels = len(retailer.available_channels)
        channel_budget = retailer_budget / n_channels
        
        spend[retailer.retailer_id] = {
            c.value: channel_budget for c in retailer.available_channels
        }
    
    return MediaAllocation(
        allocation_id="current-q1-2024",
        name="Current Q1 2024 Allocation",
        total_budget=total_budget,
        period_weeks=13,
        spend_by_retailer_channel=spend,
        status=AllocationStatus.ACTIVE
    )


def generate_conversion_paths(n_paths: int = 500) -> list:
    """Generate synthetic conversion paths for attribution"""
    np.random.seed(456)
    
    channels = [c.value for c in MediaChannel]
    paths = []
    
    for _ in range(n_paths):
        path_length = np.random.choice([1, 2, 3, 4], p=[0.3, 0.35, 0.25, 0.1])
        path = list(np.random.choice(channels, size=path_length, replace=True))
        paths.append(path)
    
    return paths


def run_demo():
    """Run the complete demo"""
    print("\n" + "🎯" * 35)
    print("  RETAIL MEDIA SPEND OPTIMIZATION DEMO")
    print("  Bayesian → Digital Twin → Agent Pipeline")
    print("🎯" * 35)
    
    # Step 1: Initialize
    orchestrator = setup_demo_orchestrator()
    
    # Step 2: Register components
    register_channels(orchestrator)
    retailers = register_retailers(orchestrator)
    skus = register_skus(orchestrator)
    initialize_twin_states(orchestrator, retailers, skus)
    
    # Step 3: Federated learning
    simulate_federated_elasticity_updates(orchestrator, retailers)
    
    # Step 4: Create current allocation
    print_header("CURRENT ALLOCATION")
    total_budget = 10_000_000  # $10M quarterly budget
    current_allocation = create_current_allocation(retailers, total_budget)
    
    print(f"Total Budget: ${total_budget/1e6:.1f}M for {current_allocation.period_weeks} weeks")
    print("\nCurrent spend by retailer:")
    for retailer_id, channels in current_allocation.spend_by_retailer_channel.items():
        total = sum(channels.values())
        print(f"  {retailer_id}: ${total/1e6:.2f}M")
        for channel, spend in channels.items():
            print(f"    - {channel}: ${spend/1e6:.3f}M")
    
    # Step 5: Generate attribution data
    print_header("ATTRIBUTION ANALYSIS")
    conversion_paths = generate_conversion_paths(500)
    spend_history = {
        c.value: current_allocation.get_channel_total(c.value)
        for c in MediaChannel
    }
    total_incremental_sales = 45_000_000  # $45M incremental sales
    
    print(f"Analyzing {len(conversion_paths)} conversion paths...")
    print(f"Total incremental sales: ${total_incremental_sales/1e6:.1f}M")
    
    # Step 6: Run the complete pipeline
    print_header("RUNNING OPTIMIZATION PIPELINE")
    print("Executing: Bayesian → Twin → Agents...")
    print()
    
    decision_pack = orchestrator.run_pipeline(
        current_allocation=current_allocation,
        total_budget=total_budget,
        period_weeks=13,
        conversion_paths=conversion_paths,
        spend_history=spend_history,
        total_incremental_sales=total_incremental_sales
    )
    
    # Step 7: Display results
    print_header("DECISION PACK RESULTS")
    
    print_subheader("Pipeline Steps")
    for step in orchestrator.pipeline_steps:
        status_icon = "✓" if step.status == "completed" else "✗"
        print(f"  {status_icon} {step.step_name}: {step.result_summary}")
    
    print_subheader("Recommended Allocation")
    rec = decision_pack.recommended_allocation
    print(f"Allocation ID: {rec.allocation_id}")
    print(f"Total Budget: ${rec.total_budget/1e6:.1f}M")
    print("\nRecommended spend by retailer:")
    for retailer_id, channels in rec.spend_by_retailer_channel.items():
        total = sum(channels.values())
        print(f"  {retailer_id}: ${total/1e6:.2f}M")
    
    print_subheader("Scenario Comparison")
    print(f"{'Scenario':<25} {'E[Sales]':>12} {'90% CI':>20} {'ROAS':>8} {'Stockout':>10}")
    print("-" * 75)
    for scenario_id, result in decision_pack.simulation_results.items():
        ci = f"[${result.sales_ci_lower/1e6:.1f}M, ${result.sales_ci_upper/1e6:.1f}M]"
        print(f"{result.scenario_name:<25} ${result.expected_incremental_sales/1e6:>10.1f}M {ci:>20} "
              f"{result.expected_roas:>7.1f}x {result.expected_stockout_rate:>9.1%}")
    
    print_subheader("Governance Decision")
    if decision_pack.governance_decision:
        gov = decision_pack.governance_decision
        print(f"Status: {gov.status.value}")
        print(f"Approved: {gov.approved}")
        if gov.escalation_reason:
            print(f"Escalation: {gov.escalation_reason}")
        print("\nValidation Checks:")
        for check in gov.checks[:5]:
            icon = "✓" if check.passed else "✗"
            print(f"  {icon} {check.rule_name}: {check.message}")
    
    print_subheader("Confidence Metrics")
    print(f"Overall Confidence: {decision_pack.overall_confidence:.1%}")
    print(f"Data Quality Score: {decision_pack.data_quality_score:.1%}")
    
    print_header("EXECUTIVE SUMMARY (LLM-Generated Rationale)")
    print(decision_pack.executive_summary)
    
    print_subheader("Uncertainty Acknowledgment")
    print(decision_pack.uncertainty_acknowledgment)
    
    # Step 8: Save summary
    print_header("DEMO COMPLETE")
    print(f"Decision Pack ID: {decision_pack.pack_id}")
    print(f"Created: {decision_pack.created_at}")
    print(f"\nReports saved to: {orchestrator.config.output_path}")
    
    return decision_pack


if __name__ == "__main__":
    try:
        decision_pack = run_demo()
        print("\n✅ Demo completed successfully!")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
