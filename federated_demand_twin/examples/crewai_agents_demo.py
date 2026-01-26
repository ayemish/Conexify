#!/usr/bin/env python3
"""
CrewAI Agents Demo

Demonstrates the unified CrewAI-compliant agent architecture:
1. Agent registration and configuration
2. Bayesian belief management
3. Inter-agent messaging
4. Complete decision workflow
5. Decision pack generation

Usage:
    python examples/crewai_agents_demo.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import numpy as np
from datetime import datetime

from vendor.agents import (
    # Base
    AgentRegistry,
    AgentRole,
    AgentCategory,
    get_agent_summary,
    CREWAI_AVAILABLE,
    
    # Agents
    DataStewardAgent,
    AttributionAgent,
    ElasticityAgent,
    ScenarioGeneratorAgent,
    DigitalTwinAgent,
    BudgetOptimizerAgent,
    GovernanceAgent,
    RationaleAgent,
    
    # Orchestration
    create_orchestrator,
    create_retail_media_orchestrator,
)


def print_header(title: str):
    """Print formatted section header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_subheader(title: str):
    """Print formatted subsection header"""
    print(f"\n--- {title} ---")


def demo_individual_agents():
    """Demonstrate individual agent capabilities"""
    print_header("INDIVIDUAL AGENT DEMONSTRATION")
    
    # Data Steward Agent
    print_subheader("Data Steward Agent")
    data_steward = DataStewardAgent(
        agent_id="demo-data-steward",
        retailer_id="demo-retailer",
        stream_ids=["spend", "demand", "price"],
    )
    
    # Generate sample data
    np.random.seed(42)
    spend_data = np.random.lognormal(10, 1, 100)
    
    # Validate data
    quality_result = data_steward.validate_stream("spend", spend_data)
    print(f"  Stream: spend")
    print(f"  Quality Score: {quality_result['quality_score']:.2f}")
    print(f"  Records: {quality_result['n_records']}")
    print(f"  Issues: {quality_result['issues']}")
    
    # Attribution Agent
    print_subheader("Attribution Agent")
    attribution_agent = AttributionAgent(
        agent_id="demo-attribution",
        retailer_id="demo-retailer",
        drivers=["media", "price", "trade"],
    )
    
    # Sample conversion paths
    conversion_paths = [
        ["media", "media", "price"],
        ["trade", "media"],
        ["media"],
        ["price", "trade", "media"],
        ["media", "trade"],
    ] * 100
    
    attribution = attribution_agent.compute_attribution(conversion_paths, 1000000)
    print(f"  Total Value: ${attribution['total_value']:,.0f}")
    print(f"  Attribution Shares:")
    for driver, share in attribution['shares'].items():
        print(f"    {driver}: {share:.1%}")
    
    # Elasticity Agent
    print_subheader("Elasticity Agent")
    elasticity_agent = ElasticityAgent(
        agent_id="demo-elasticity",
        retailer_id="demo-retailer",
    )
    
    # Sample spend-response data
    spend = np.random.uniform(10000, 100000, 52)
    response = spend ** 0.15 * np.random.lognormal(0, 0.1, 52) * 100
    
    elasticity = elasticity_agent.estimate_elasticity(spend, response, "media")
    print(f"  Point Estimate: {elasticity['point_estimate']:.3f}")
    print(f"  Posterior Mean: {elasticity['posterior_mean']:.3f}")
    print(f"  90% CI: [{elasticity['ci_90'][0]:.3f}, {elasticity['ci_90'][1]:.3f}]")
    
    # Scenario Generator
    print_subheader("Scenario Generator Agent")
    scenario_agent = ScenarioGeneratorAgent(
        agent_id="demo-scenario",
        retailer_id="demo-retailer",
        drivers=["media", "price", "trade"],
    )
    
    current_allocation = {"media": 500000, "price": 300000, "trade": 200000}
    scenarios = scenario_agent.generate_scenarios(current_allocation, 1000000)
    
    print(f"  Generated {len(scenarios)} scenarios:")
    for s in scenarios:
        print(f"    - {s['name']}: {s['description']}")
    
    # Digital Twin
    print_subheader("Digital Twin Agent")
    twin_agent = DigitalTwinAgent(
        agent_id="demo-twin",
        retailer_id="demo-retailer",
    )
    
    # Simulate baseline scenario
    simulation = twin_agent.simulate(scenarios[0], n_simulations=1000)
    print(f"  Scenario: {simulation['scenario_name']}")
    print(f"  Expected Sales: ${simulation['expected_sales']:,.0f}")
    print(f"  90% CI: [${simulation['sales_ci_90'][0]:,.0f}, ${simulation['sales_ci_90'][1]:,.0f}]")
    print(f"  Expected ROAS: {simulation['expected_roas']:.1f}x")
    
    # Governance Agent
    print_subheader("Governance Agent")
    governance_agent = GovernanceAgent(
        agent_id="demo-governance",
        retailer_id="demo-retailer",
    )
    
    # Add policies
    governance_agent.add_policy(
        "min_confidence",
        lambda r: r.get("confidence", 0) >= 0.5,
        severity="critical"
    )
    governance_agent.add_policy(
        "max_budget_change",
        lambda r: abs(r.get("budget_change_pct", 0)) <= 0.25,
        severity="warning"
    )
    
    recommendation = {
        "id": "rec-001",
        "confidence": 0.8,
        "budget_change_pct": 0.1,
    }
    
    decision = governance_agent.validate(recommendation)
    print(f"  Approved: {decision['approved']}")
    print(f"  Requires Review: {decision['requires_review']}")
    print(f"  Policies Checked: {decision['n_policies']}")
    
    # Rationale Agent
    print_subheader("Rationale Agent")
    rationale_agent = RationaleAgent(
        agent_id="demo-rationale",
        retailer_id="demo-retailer",
    )
    
    rationale = rationale_agent.generate_rationale(
        {"name": "Baseline", "allocation": current_allocation},
        simulation,
        decision
    )
    print(f"  Executive Summary (excerpt):")
    print(f"    {rationale['executive_summary'][:200]}...")


def demo_agent_registry():
    """Demonstrate agent registry functionality"""
    print_header("AGENT REGISTRY")
    
    registry = AgentRegistry.get_instance()
    
    # Get summary
    summary = get_agent_summary()
    print(f"  Total Agents: {summary['total_agents']}")
    print(f"  CrewAI Available: {summary['crewai_available']}")
    print(f"  By Category:")
    for category, agents in summary.get('by_category', {}).items():
        print(f"    {category}: {len(agents)} agents")


def demo_orchestrator_workflow():
    """Demonstrate complete orchestrator workflow"""
    print_header("COMPLETE ORCHESTRATOR WORKFLOW")
    
    # Create orchestrator
    orchestrator = create_orchestrator(
        retailer_id="demo-retailer",
        drivers=["media", "price", "trade"],
        n_simulations=500,  # Reduced for demo
        n_scenarios=4,
        output_path="./reports/crewai_demo",
    )
    
    print_subheader("Agent Summary")
    summary = orchestrator.get_agent_summary()
    print(f"  Total Agents: {summary['total_agents']}")
    for category, agents in summary['by_category'].items():
        print(f"  {category.upper()}:")
        for a in agents:
            print(f"    - {a['role']}")
    
    # Generate sample data
    print_subheader("Generating Sample Data")
    np.random.seed(123)
    
    data_inputs = {
        "spend": np.random.lognormal(10, 1, 52),
        "demand": np.random.normal(1000, 100, 52),
        "price": np.random.uniform(5, 15, 52),
    }
    
    current_allocation = {
        "media": 500000,
        "price": 300000,
        "trade": 200000,
    }
    
    total_budget = 1000000
    
    print(f"  Data streams: {list(data_inputs.keys())}")
    print(f"  Current allocation: ${sum(current_allocation.values()):,.0f}")
    print(f"  Total budget: ${total_budget:,.0f}")
    
    # Run workflow
    print_subheader("Running Decision Workflow")
    print("  Executing: SENSE → UPDATE → SIMULATE → OPTIMIZE → EXPLAIN → LEARN")
    print()
    
    decision_pack = orchestrator.run(
        data_inputs=data_inputs,
        current_allocation=current_allocation,
        total_budget=total_budget,
    )
    
    # Display results
    print_subheader("Workflow Results")
    print(f"  Pack ID: {decision_pack.pack_id}")
    print(f"  Status: {decision_pack.overall_status.value}")
    print(f"  Confidence: {decision_pack.confidence_score:.1%}")
    
    print_subheader("Stage Results")
    for stage_name, stage_result in decision_pack.stage_results.items():
        status_icon = "✓" if stage_result.status.value == "completed" else "✗"
        print(f"  {status_icon} {stage_name}: {stage_result.status.value} ({stage_result.duration_seconds:.2f}s)")
    
    print_subheader("Recommendation")
    rec = decision_pack.recommendation
    print(f"  Scenario: {rec.get('name', 'Unknown')}")
    print(f"  Expected Sales: ${rec.get('expected_sales', 0):,.0f}")
    print(f"  Expected ROAS: {rec.get('expected_roas', 0):.1f}x")
    
    print_subheader("Scenario Comparison")
    print(f"  {'Scenario':<20} {'Expected Sales':>15} {'ROAS':>8}")
    print("  " + "-" * 45)
    for scenario_id, result in decision_pack.simulation_results.items():
        print(f"  {scenario_id:<20} ${result['expected_sales']:>12,.0f} {result['expected_roas']:>7.1f}x")
    
    print_subheader("Governance Decision")
    gov = decision_pack.governance_decision
    print(f"  Approved: {gov.get('approved', False)}")
    print(f"  Requires Review: {gov.get('requires_review', False)}")
    if gov.get('violations'):
        print(f"  Violations: {', '.join(gov['violations'])}")
    
    print_subheader("Generated Rationale (Excerpt)")
    print(decision_pack.rationale.get('executive_summary', '')[:300])
    
    return decision_pack


def demo_retail_media_orchestrator():
    """Demonstrate retail media specific orchestrator"""
    print_header("RETAIL MEDIA ORCHESTRATOR")
    
    orchestrator = create_retail_media_orchestrator(
        retailer_id="walmart",
        channels=["sponsored_search", "display", "email", "in_store"],
        n_simulations=500,
        output_path="./reports/retail_media_crewai",
    )
    
    print_subheader("Retail Media Configuration")
    summary = orchestrator.get_agent_summary()
    print(f"  Retailer: {summary['retailer_id']}")
    print(f"  Total Agents: {summary['total_agents']}")
    
    # Quick workflow run
    np.random.seed(456)
    
    data_inputs = {
        "spend": np.random.lognormal(11, 0.5, 52),
        "impressions": np.random.lognormal(15, 0.3, 52),
        "clicks": np.random.lognormal(10, 0.4, 52),
        "conversions": np.random.lognormal(7, 0.5, 52),
    }
    
    current_allocation = {
        "sponsored_search": 2000000,
        "display": 1500000,
        "email": 500000,
        "in_store": 1000000,
    }
    
    print_subheader("Running Retail Media Optimization")
    decision_pack = orchestrator.run(
        data_inputs=data_inputs,
        current_allocation=current_allocation,
        total_budget=5000000,
    )
    
    print(f"  Status: {decision_pack.overall_status.value}")
    print(f"  Confidence: {decision_pack.confidence_score:.1%}")
    print(f"  Report saved to: ./reports/retail_media_crewai/")


def main():
    """Run all demonstrations"""
    print("\n" + "🤖" * 35)
    print("  CREWAI AGENTS DEMONSTRATION")
    print("  Unified Agent Architecture for Demand Twin")
    print("🤖" * 35)
    
    print(f"\nCrewAI Available: {CREWAI_AVAILABLE}")
    if not CREWAI_AVAILABLE:
        print("Note: Running with mock CrewAI classes (install crewai for full functionality)")
    
    # Run demos
    demo_individual_agents()
    demo_agent_registry()
    decision_pack = demo_orchestrator_workflow()
    demo_retail_media_orchestrator()
    
    print_header("DEMO COMPLETE")
    print(f"  Decision Pack: {decision_pack.pack_id}")
    print(f"  Created: {decision_pack.created_at}")
    print(f"  Reports saved to: ./reports/")
    
    # Agent summary
    registry = AgentRegistry.get_instance()
    print(f"\n  Total agents created: {len(registry.get_all())}")
    
    print("\n✅ All demonstrations completed successfully!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
