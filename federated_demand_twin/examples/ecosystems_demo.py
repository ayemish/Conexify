#!/usr/bin/env python3
"""
Agent Ecosystems Demo

Demonstrates all three self-contained agent ecosystems:
1. RMN (Retail Media Network) Optimization
2. Oil & Gas Telemetry Monitoring
3. Demand Forecast & Procurement

Usage:
    python examples/ecosystems_demo.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import numpy as np
from datetime import datetime, date, timedelta

from vendor.agents.crewai_base import CREWAI_AVAILABLE, AgentRegistry


def print_header(title: str):
    """Print formatted section header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_subheader(title: str):
    """Print formatted subsection header"""
    print(f"\n--- {title} ---")


# =============================================================================
# RMN ECOSYSTEM DEMO
# =============================================================================

def demo_rmn_ecosystem():
    """Demonstrate RMN Optimization ecosystem"""
    print_header("🛒 RMN (RETAIL MEDIA NETWORK) OPTIMIZATION")
    
    from vendor.agents.ecosystems.rmn import (
        create_rmn_orchestrator,
        MediaSpendData,
        ChannelType,
    )
    
    # Create orchestrator for a retailer
    orchestrator = create_rmn_orchestrator(
        retailer_id="walmart",
        retailer_name="Walmart Connect",
        n_simulations=500,
        n_scenarios=4,
    )
    
    print_subheader("Agent Summary")
    summary = orchestrator.get_agent_summary()
    print(f"  Ecosystem: {summary['ecosystem']}")
    print(f"  Retailer: {summary['retailer_id']}")
    print(f"  Channels: {summary['n_channels']}")
    print(f"  Agents: {', '.join(summary['agents'])}")
    
    # Generate sample spend data
    print_subheader("Generating Sample Data")
    np.random.seed(42)
    
    channels = ["sponsored_search", "sponsored_product", "display", "video", "email"]
    spend_data = []
    
    for i in range(52):  # 52 weeks of data
        for channel in channels:
            spend = np.random.lognormal(10, 0.5)
            revenue = spend * np.random.uniform(1.5, 4.0)
            record = MediaSpendData(
                channel_id=channel,
                date=date.today() - timedelta(weeks=52-i),
                spend=spend,
                impressions=int(spend * 100),
                clicks=int(spend * 5),
                conversions=int(spend * 0.1),
                revenue=revenue,
            )
            spend_data.append(record)
    
    # Generate conversion paths
    conversion_paths = []
    for _ in range(500):
        path_len = np.random.randint(1, 5)
        path = list(np.random.choice(channels, size=path_len))
        conversion_paths.append(path)
    
    current_allocation = {
        "sponsored_search": 500000,
        "sponsored_product": 400000,
        "display": 300000,
        "video": 200000,
        "email": 100000,
    }
    
    print(f"  Spend records: {len(spend_data)}")
    print(f"  Conversion paths: {len(conversion_paths)}")
    print(f"  Current budget: ${sum(current_allocation.values()):,}")
    
    # Run optimization
    print_subheader("Running RMN Optimization")
    decision_pack = orchestrator.run(
        spend_data=spend_data,
        conversion_paths=conversion_paths,
        current_allocation=current_allocation,
        base_revenue=5000000,
    )
    
    print_subheader("Results")
    print(f"  Pack ID: {decision_pack.pack_id}")
    print(f"  Status: {decision_pack.status}")
    print(f"  Confidence: {decision_pack.confidence_score:.1%}")
    
    print_subheader("Attribution Shares")
    for channel, share in decision_pack.attribution.channel_shares.items():
        print(f"  {channel}: {share:.1%}")
    
    print_subheader("Channel Elasticities")
    for channel_id, el in decision_pack.elasticities.items():
        print(f"  {channel_id}: {el.mean:.3f} ± {el.std:.3f}")
    
    print_subheader("Scenario Comparison")
    print(f"  {'Scenario':<25} {'Revenue':>12} {'ROAS':>8}")
    print("  " + "-" * 47)
    for scenario_id, sim in decision_pack.simulations.items():
        print(f"  {sim.scenario_name:<25} ${sim.expected_revenue/1e6:>9.2f}M {sim.expected_roas:>7.2f}x")
    
    print_subheader("Recommendation")
    opt = decision_pack.optimization
    print(f"  Selected: {opt.selected_scenario_id}")
    print(f"  Expected Revenue: ${opt.expected_revenue:,.0f}")
    print(f"  Expected ROAS: {opt.expected_roas:.2f}x")
    
    print_subheader("Governance")
    gov = decision_pack.governance
    print(f"  Approved: {gov.approved}")
    print(f"  Risk Score: {gov.risk_score:.2f}")
    
    return decision_pack


# =============================================================================
# OIL & GAS ECOSYSTEM DEMO
# =============================================================================

def demo_oil_gas_ecosystem():
    """Demonstrate Oil & Gas Telemetry ecosystem"""
    print_header("🛢️ OIL & GAS TELEMETRY MONITORING")
    
    from vendor.agents.ecosystems.oil_gas import (
        create_oil_gas_orchestrator,
        TelemetryReading,
        SensorType,
    )
    
    # Create orchestrator for a site
    orchestrator = create_oil_gas_orchestrator(
        site_id="permian_site_001",
        site_name="Permian Basin Site 1",
        operator="Demo Oil Corp",
    )
    
    print_subheader("Agent Summary")
    summary = orchestrator.get_agent_summary()
    print(f"  Ecosystem: {summary['ecosystem']}")
    print(f"  Site: {summary['site_id']}")
    print(f"  Wells: {summary['n_wells']}")
    print(f"  Sensors: {summary['n_sensors']}")
    print(f"  Agents: {', '.join(summary['agents'])}")
    
    # Generate sample telemetry
    print_subheader("Generating Telemetry Data")
    np.random.seed(123)
    
    readings = []
    now = datetime.utcnow()
    
    # Well 1 sensors
    for i in range(100):
        ts = now - timedelta(minutes=i)
        
        # Normal readings
        readings.append(TelemetryReading(
            sensor_id="well_001_tubing_pressure",
            timestamp=ts,
            value=np.random.normal(2500, 100),
            unit="psi",
            well_id="well_001",
        ))
        readings.append(TelemetryReading(
            sensor_id="well_001_oil_flow",
            timestamp=ts,
            value=np.random.normal(450, 50),
            unit="bpd",
            well_id="well_001",
        ))
        readings.append(TelemetryReading(
            sensor_id="well_001_h2s",
            timestamp=ts,
            value=np.random.exponential(2),  # Usually low
            unit="ppm",
            well_id="well_001",
        ))
    
    # Well 2 with an anomaly
    for i in range(100):
        ts = now - timedelta(minutes=i)
        
        # Add a vibration spike
        vibration = np.random.normal(5, 1) if i > 20 else np.random.normal(15, 3)  # Anomaly in recent readings
        
        readings.append(TelemetryReading(
            sensor_id="well_002_vibration",
            timestamp=ts,
            value=vibration,
            unit="mm/s",
            well_id="well_002",
        ))
        readings.append(TelemetryReading(
            sensor_id="well_002_oil_flow",
            timestamp=ts,
            value=np.random.normal(320, 40),
            unit="bpd",
            well_id="well_002",
        ))
    
    print(f"  Total readings: {len(readings)}")
    print(f"  Time range: {(now - timedelta(minutes=100)).strftime('%H:%M')} - {now.strftime('%H:%M')}")
    
    # Run monitoring
    print_subheader("Running Oil & Gas Monitoring")
    decision_pack = orchestrator.run(
        telemetry_readings=readings,
        include_compliance=True,
    )
    
    print_subheader("Results")
    print(f"  Pack ID: {decision_pack.pack_id}")
    print(f"  Health Score: {decision_pack.overall_health_score:.2f}")
    
    print_subheader("Safety Status")
    safety = decision_pack.safety_status
    print(f"  Safe: {'✅' if safety.is_safe else '🚨'}")
    print(f"  Active Alerts: {safety.active_alerts}")
    print(f"  Critical Alerts: {safety.critical_alerts}")
    print(f"  H2S Level: {safety.h2s_level_ppm:.2f} ppm")
    
    print_subheader("Production Metrics")
    for well_id, metrics in decision_pack.production_metrics.items():
        print(f"  {well_id}:")
        print(f"    Oil Rate: {metrics.oil_rate_bpd:.0f} BPD")
        print(f"    Water Cut: {metrics.water_cut_pct:.1f}%")
    
    print_subheader("Active Alerts")
    if decision_pack.active_alerts:
        for alert in decision_pack.active_alerts[:5]:
            print(f"  [{alert.severity.value.upper()}] {alert.sensor_id}: {alert.anomaly_type}")
    else:
        print("  No active alerts")
    
    print_subheader("Maintenance Predictions")
    if decision_pack.maintenance_predictions:
        for pred in decision_pack.maintenance_predictions:
            print(f"  {pred.equipment_id}: {pred.recommended_action} (P{pred.priority})")
    else:
        print("  No maintenance needed")
    
    if decision_pack.compliance_report:
        print_subheader("Compliance")
        print(f"  Compliant: {'✅' if decision_pack.compliance_report.is_compliant else '❌'}")
        if decision_pack.compliance_report.violations:
            for v in decision_pack.compliance_report.violations:
                print(f"  ⚠️ {v}")
    
    return decision_pack


# =============================================================================
# DEMAND & PROCUREMENT ECOSYSTEM DEMO
# =============================================================================

def demo_demand_procurement_ecosystem():
    """Demonstrate Demand & Procurement ecosystem"""
    print_header("📦 DEMAND FORECAST & PROCUREMENT")
    
    from vendor.agents.ecosystems.demand_procurement import (
        create_demand_procurement_orchestrator,
    )
    
    # Create orchestrator
    orchestrator = create_demand_procurement_orchestrator(
        organization_id="acme_corp",
        organization_name="ACME Corporation",
        forecast_horizon_weeks=13,
    )
    
    print_subheader("Agent Summary")
    summary = orchestrator.get_agent_summary()
    print(f"  Ecosystem: {summary['ecosystem']}")
    print(f"  Organization: {summary['organization_id']}")
    print(f"  SKUs: {summary['n_skus']}")
    print(f"  Suppliers: {summary['n_suppliers']}")
    print(f"  Agents: {', '.join(summary['agents'])}")
    
    # Generate sample demand history
    print_subheader("Generating Demand History")
    np.random.seed(456)
    
    demand_history = {
        "SKU-001": np.random.normal(200, 30, 52).clip(50),  # Steady demand
        "SKU-002": np.random.normal(150, 25, 52).clip(30),
        "SKU-003": np.random.normal(50, 15, 52).clip(10),   # Lower volume
        "SKU-004": np.random.normal(80, 20, 52).clip(20),
        "SKU-005": np.random.normal(500, 80, 52).clip(100), # High volume component
    }
    
    current_inventory = {
        "SKU-001": 500,
        "SKU-002": 150,  # Low - will trigger order
        "SKU-003": 200,
        "SKU-004": 50,   # Very low - high risk
        "SKU-005": 1000,
    }
    
    print(f"  SKUs analyzed: {len(demand_history)}")
    print(f"  History weeks: 52")
    print(f"  Total current inventory: {sum(current_inventory.values()):,} units")
    
    # Run optimization
    print_subheader("Running Demand & Procurement Optimization")
    decision_pack = orchestrator.run(
        demand_history=demand_history,
        current_inventory=current_inventory,
    )
    
    print_subheader("Results")
    print(f"  Pack ID: {decision_pack.pack_id}")
    print(f"  Status: {decision_pack.status}")
    print(f"  Confidence: {decision_pack.confidence_score:.1%}")
    
    print_subheader("Demand Forecasts")
    for sku_id, forecast in decision_pack.forecasts.items():
        print(f"  {sku_id}: {forecast.mean_weekly_demand:.0f}/week (total: {forecast.total_forecast:.0f})")
    
    print_subheader("Inventory Policies")
    print(f"  {'SKU':<10} {'ROP':>6} {'EOQ':>6} {'Safety':>8} {'Service':>8}")
    print("  " + "-" * 42)
    for sku_id, policy in decision_pack.policies.items():
        print(f"  {sku_id:<10} {policy.reorder_point:>6} {policy.order_quantity:>6} {policy.safety_stock:>8} {policy.expected_service_level:>7.0%}")
    
    print_subheader("Risk Assessment")
    for sku_id, risk in decision_pack.risk_assessments.items():
        risk_emoji = "🔴" if risk.risk_level == "critical" else "🟡" if risk.risk_level == "high" else "🟢"
        print(f"  {risk_emoji} {sku_id}: {risk.risk_level.upper()} (stockout prob: {risk.stockout_probability:.1%})")
    
    print_subheader("Procurement Plans")
    if decision_pack.procurement_plans:
        print(f"  {'SKU':<10} {'Supplier':<12} {'Qty':>6} {'Cost':>10} {'Priority':>8}")
        print("  " + "-" * 50)
        for plan in decision_pack.procurement_plans:
            print(f"  {plan.sku_id:<10} {plan.supplier_id:<12} {plan.order_quantity:>6} ${plan.total_cost:>8,.0f} {'P'+str(plan.priority):>8}")
    else:
        print("  No orders needed")
    
    print_subheader("Scenario Comparison")
    for scenario_id, result in decision_pack.scenario_results.items():
        selected = "✓" if scenario_id == decision_pack.selected_scenario else " "
        print(f"  {selected} {result.scenario_name}: SL={result.expected_service_level:.1%}, Cost=${result.expected_total_cost:,.0f}")
    
    return decision_pack


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Run all ecosystem demonstrations"""
    print("\n" + "🌐" * 35)
    print("  AGENT ECOSYSTEMS DEMONSTRATION")
    print("  Three Self-Contained Agentic Solutions")
    print("🌐" * 35)
    
    print(f"\nCrewAI Available: {CREWAI_AVAILABLE}")
    print(f"Timestamp: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    
    # Run all demos
    rmn_pack = demo_rmn_ecosystem()
    oil_gas_pack = demo_oil_gas_ecosystem()
    dp_pack = demo_demand_procurement_ecosystem()
    
    # Summary
    print_header("📊 ECOSYSTEM SUMMARY")
    
    registry = AgentRegistry.get_instance()
    total_agents = len(registry.get_all())
    
    print(f"\n  Total Agents Created: {total_agents}")
    print(f"\n  Ecosystems:")
    print(f"    1. RMN Optimization: Pack {rmn_pack.pack_id}")
    print(f"       Status: {rmn_pack.status}, Confidence: {rmn_pack.confidence_score:.1%}")
    print(f"    2. Oil & Gas Telemetry: Pack {oil_gas_pack.pack_id}")
    print(f"       Health Score: {oil_gas_pack.overall_health_score:.2f}")
    print(f"    3. Demand & Procurement: Pack {dp_pack.pack_id}")
    print(f"       Status: {dp_pack.status}, Orders: {len(dp_pack.procurement_plans)}")
    
    print("\n✅ All ecosystem demonstrations completed successfully!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
