"""
Loweconex Platform — Main entry point and demo runner.

Demonstrates the full pipeline:
1. Create sample digital twins (assets, locations, estate)
2. Run all 14 KPI crews
3. Run 3 scenario simulations
4. Compute ROI with attribution ledger
5. Generate composite report (JSON + HTML)
6. Run compliance checks
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loweconex_platform.config import PlatformConfig
from loweconex_platform.digital_twins.models import (
    AssetEconomics,
    AssetTwin,
    AssetType,
    EstateTwin,
    HealthState,
    LocationTwin,
    RelationshipType,
    TwinRelationship,
)
from loweconex_platform.digital_twins.relationships import RelationshipGraph
from loweconex_platform.digital_twins.store import OperationalEvent, TwinStore
from loweconex_platform.event_bus.redis_streams import InMemoryEventBus
from loweconex_platform.governance.audit_log import AuditAction, AuditLog
from loweconex_platform.governance.compliance import ComplianceChecker
from loweconex_platform.governance.rbac import Permission, RBACManager, Role, User
from loweconex_platform.ingestion.normalizer import IdentityResolver
from loweconex_platform.kpi_crews.registry import KPI_REGISTRY, get_all_kpi_names
from loweconex_platform.kpi_crews.tools import LoweconexTools
from loweconex_platform.orchestration.orchestrator_crew import OrchestratorCrew
from loweconex_platform.reporting.composite_report import CompositeReportBuilder
from loweconex_platform.reporting.exporters import JSONExporter, PDFExporter, WebExporter
from loweconex_platform.roi_engine.cost_model import CostModel
from loweconex_platform.roi_engine.savings_engine import SavingsEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("loweconex_platform")


# =============================================================================
# Sample Data Generator
# =============================================================================

def create_sample_data(twin_store: TwinStore, graph: RelationshipGraph) -> str:
    """
    Create sample digital twins for demonstration.
    
    Returns the company_id.
    """
    company_id = "acme_grocery"
    now = datetime.utcnow()

    # -------------------------------------------------------------------------
    # Estate
    # -------------------------------------------------------------------------
    estate = EstateTwin(
        company_id=company_id,
        company_name="ACME Grocery Holdings",
        location_ids=["loc_001", "loc_002", "loc_003"],
    )
    twin_store.upsert_estate(estate)

    # -------------------------------------------------------------------------
    # Locations
    # -------------------------------------------------------------------------
    locations = [
        LocationTwin(
            location_id="loc_001", company_id=company_id,
            address="123 Main St, Springfield, IL",
            store_format="supermarket", sqft=55000,
            climate_zone="4A",
            geo={"lat": 39.78, "lon": -89.65},
            utility_tariffs={"electricity": {"rate_kwh": 0.11, "demand_kw": 12.50}, "gas": {"rate_therm": 1.10}},
        ),
        LocationTwin(
            location_id="loc_002", company_id=company_id,
            address="456 Oak Ave, Decatur, IL",
            store_format="supermarket", sqft=48000,
            climate_zone="4A",
            geo={"lat": 39.84, "lon": -88.95},
            utility_tariffs={"electricity": {"rate_kwh": 0.12, "demand_kw": 13.00}, "gas": {"rate_therm": 1.15}},
        ),
        LocationTwin(
            location_id="loc_003", company_id=company_id,
            address="789 Elm Rd, Champaign, IL",
            store_format="neighborhood_market", sqft=32000,
            climate_zone="5A",
            geo={"lat": 40.12, "lon": -88.24},
            utility_tariffs={"electricity": {"rate_kwh": 0.10, "demand_kw": 11.00}, "gas": {"rate_therm": 1.05}},
        ),
    ]
    for loc in locations:
        twin_store.upsert_location(loc)

    # -------------------------------------------------------------------------
    # Assets (per location)
    # -------------------------------------------------------------------------
    asset_templates = [
        # (type, manufacturer, age_years, health_score, opex_monthly, replace_cost)
        (AssetType.HVAC_RTU, "Carrier", 8, 72, 800, 25000),
        (AssetType.HVAC_RTU, "Trane", 12, 58, 1100, 28000),
        (AssetType.HVAC_AHU, "York", 5, 88, 500, 18000),
        (AssetType.REFRIGERATION_RACK, "Heatcraft", 6, 80, 1500, 45000),
        (AssetType.REFRIGERATION_RACK, "Hussmann", 10, 65, 2000, 50000),
        (AssetType.REFRIGERATION_CASE, "Zero Zone", 4, 90, 200, 8000),
        (AssetType.REFRIGERATION_CASE, "Hussmann", 7, 78, 250, 9000),
        (AssetType.REFRIGERATION_CASE, "Tyler", 9, 70, 280, 8500),
        (AssetType.COMPRESSOR, "Copeland", 6, 82, 600, 12000),
        (AssetType.CONDENSER, "Bohn", 5, 85, 400, 15000),
        (AssetType.EVAPORATOR, "Heatcraft", 7, 75, 300, 6000),
        (AssetType.LEAK_DETECTOR, "Bacharach", 2, 95, 50, 3000),
    ]

    for loc in locations:
        for idx, (atype, mfg, age, health, opex, capex) in enumerate(asset_templates):
            asset_id = f"asset_{loc.location_id}_{idx:03d}"
            asset = AssetTwin(
                asset_id=asset_id,
                location_id=loc.location_id,
                company_id=company_id,
                asset_type=atype,
                manufacturer=mfg,
                age_years=age,
                install_date=now - timedelta(days=age * 365),
                health=HealthState(
                    health_score=health,
                    failure_risk_30d=max(0, (100 - health) / 200),
                    failure_risk_90d=max(0, (100 - health) / 100),
                    last_assessment_ts=now,
                ),
                economics=AssetEconomics(
                    opex_baseline_monthly=opex,
                    capex_replace_cost=capex,
                    remaining_useful_life_months=max(12, (20 - age) * 12),
                ),
            )
            twin_store.upsert_asset(asset)

            # Add to location's asset list
            loc.asset_ids.append(asset_id)

        twin_store.upsert_location(loc)

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    for loc in locations:
        assets = twin_store.get_assets_by_location(loc.location_id)
        racks = [a for a in assets if a.asset_type == AssetType.REFRIGERATION_RACK]
        cases = [a for a in assets if a.asset_type == AssetType.REFRIGERATION_CASE]
        rtus = [a for a in assets if a.asset_type == AssetType.HVAC_RTU]
        condensers = [a for a in assets if a.asset_type == AssetType.CONDENSER]

        # Racks serve cases
        for rack in racks:
            for case in cases:
                graph.add_edge(rack.asset_id, case.asset_id, RelationshipType.SERVES)

        # Condensers reject heat to roof environment (affects HVAC)
        for cond in condensers:
            for rtu in rtus:
                graph.add_edge(cond.asset_id, rtu.asset_id, RelationshipType.REJECTS_HEAT_TO)

        # HVAC ambient affects condenser performance
        for rtu in rtus:
            for cond in condensers:
                graph.add_edge(rtu.asset_id, cond.asset_id, RelationshipType.AFFECTS_LOAD_OF)

    # -------------------------------------------------------------------------
    # Sample Events
    # -------------------------------------------------------------------------
    event_types = [
        ("work_order", 20), ("temp_excursion", 8), ("refrigerant_leak", 3),
        ("downtime", 5), ("food_safety_violation", 2), ("call_center_ticket", 10),
        ("vendor_job", 6), ("pm_completion", 15), ("failure", 3),
    ]

    for loc in locations:
        assets = twin_store.get_assets_by_location(loc.location_id)
        for etype, count in event_types:
            for i in range(count):
                asset = assets[i % len(assets)] if assets else None
                event = OperationalEvent(
                    event_id=f"evt_{loc.location_id}_{etype}_{i:03d}",
                    event_type=etype,
                    source_system="sample_generator",
                    start_ts=now - timedelta(days=30 - i, hours=i * 2),
                    end_ts=now - timedelta(days=30 - i, hours=i * 2 - 1) if etype != "downtime" else None,
                    asset_id=asset.asset_id if asset else None,
                    location_id=loc.location_id,
                    company_id=company_id,
                    severity="medium" if i % 3 == 0 else "low",
                    confidence=0.85,
                    code=f"{etype.upper()[:3]}-{i:03d}",
                    payload={
                        "category": "pm" if etype == "pm_completion" else "reactive",
                        "repeat": i % 5 == 0,
                        "labor_hours": 2.5 + i * 0.3,
                        "parts_cost": 150 + i * 25,
                    },
                )
                twin_store.store_event(event)

    logger.info(f"Sample data created: {twin_store.stats()}")
    logger.info(f"Relationship graph: {graph.stats()}")
    return company_id


# =============================================================================
# Demo Runner
# =============================================================================

def run_demo(
    output_dir: str = "./reports",
    kpi_subset: Optional[List[str]] = None,
    run_scenarios: bool = True,
) -> Dict[str, Any]:
    """
    Run the full Loweconex platform demo pipeline.
    
    Returns the composite result dict.
    """
    logger.info("=" * 70)
    logger.info("LOWECONEX DIGITAL TWIN → MULTI-AGENT COMPOSITE ROI PLATFORM")
    logger.info("=" * 70)

    # -------------------------------------------------------------------------
    # 1. Initialize Platform
    # -------------------------------------------------------------------------
    config = PlatformConfig()
    config.report.output_dir = output_dir
    twin_store = TwinStore()
    event_bus = InMemoryEventBus()
    graph = RelationshipGraph()
    audit_log = AuditLog()

    # -------------------------------------------------------------------------
    # 2. RBAC Setup
    # -------------------------------------------------------------------------
    rbac = RBACManager()
    demo_user = User(
        user_id="demo_user",
        email="demo@acmegrocery.com",
        display_name="Demo Analyst",
        company_id="acme_grocery",
        roles=[Role.ANALYST],
    )
    rbac.add_user(demo_user)

    # -------------------------------------------------------------------------
    # 3. Create Sample Data
    # -------------------------------------------------------------------------
    logger.info("\n--- Creating Sample Digital Twins ---")
    company_id = create_sample_data(twin_store, graph)

    audit_log.log(
        action=AuditAction.DATA_IMPORT,
        company_id=company_id,
        user_id="demo_user",
        details={"source": "sample_generator", "stats": twin_store.stats()},
    )

    # -------------------------------------------------------------------------
    # 4. Access Check
    # -------------------------------------------------------------------------
    if not rbac.check_access(demo_user.user_id, company_id, Permission.SCENARIO_RUN):
        logger.error("Access denied for demo user")
        return {"error": "Access denied"}

    # -------------------------------------------------------------------------
    # 5. Run Orchestrator Pipeline
    # -------------------------------------------------------------------------
    logger.info("\n--- Running Orchestrator Pipeline ---")
    tools = LoweconexTools(twin_store, event_bus)

    # Wire PdM Bridge so Phase 0 feeds PdM model outputs into KPI crews
    pdm_bridge = None
    try:
        from loweconex_platform.pdm_bridge import PdMBridge
        pdm_bridge = PdMBridge(twin_store=twin_store, event_bus=event_bus)
        logger.info("PdM bridge wired into orchestrator")
    except Exception as e:
        logger.warning("PdM bridge not available: %s", e)

    orchestrator = OrchestratorCrew(config, twin_store, event_bus, tools, pdm_bridge=pdm_bridge)

    composite_result = orchestrator.run_full_pipeline(
        company_id=company_id,
        kpi_names=kpi_subset,
        run_scenarios=run_scenarios,
    )

    audit_log.log(
        action=AuditAction.SCENARIO_RUN,
        company_id=company_id,
        user_id="demo_user",
        details={"run_id": composite_result.get("run_id"), "kpi_count": len(composite_result.get("kpi_results", {}))},
    )

    # -------------------------------------------------------------------------
    # 6. ROI Computation
    # -------------------------------------------------------------------------
    logger.info("\n--- Computing ROI ---")
    savings_engine = SavingsEngine(
        discount_rate=config.roi_engine.discount_rate,
        analysis_years=config.roi_engine.analysis_horizon_years,
    )

    location_count = len(twin_store.get_locations_by_company(company_id))
    asset_count = len(twin_store.get_assets_by_company(company_id))
    costs = CostModel.build_default_costs(
        location_count=location_count,
        asset_count=asset_count,
        analysis_years=config.roi_engine.analysis_horizon_years,
    )

    roi_result = savings_engine.compute_roi(
        kpi_results={k: v for k, v in composite_result.get("kpi_results", {}).items()},
        costs=costs,
        double_counting_policy=config.roi_engine.double_counting_policy,
    )

    composite_result["roi"] = roi_result.to_dict()
    composite_result["program_costs"] = costs.to_dict()

    # -------------------------------------------------------------------------
    # 7. Compliance Check
    # -------------------------------------------------------------------------
    logger.info("\n--- Running Compliance Checks ---")
    compliance = ComplianceChecker()
    compliance_report = compliance.run_all_checks(composite_result.get("kpi_results", {}))
    composite_result["compliance_report"] = compliance_report.to_dict()

    # -------------------------------------------------------------------------
    # 8. Generate Report
    # -------------------------------------------------------------------------
    logger.info("\n--- Generating Composite Report ---")
    report_builder = CompositeReportBuilder()
    report = report_builder.build_full_report(composite_result)

    audit_log.log(
        action=AuditAction.REPORT_GENERATED,
        company_id=company_id,
        user_id="demo_user",
        details={"report_id": report.get("report_id"), "sections": list(report.get("sections", {}).keys())},
    )

    # -------------------------------------------------------------------------
    # 9. Export Reports
    # -------------------------------------------------------------------------
    logger.info("\n--- Exporting Reports ---")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    json_path = os.path.join(output_dir, "composite_roi_report.json")
    JSONExporter().export(report, json_path)

    html_path = os.path.join(output_dir, "composite_roi_report.html")
    WebExporter().export(report, html_path)

    pdf_path = os.path.join(output_dir, "composite_roi_report.pdf")
    PDFExporter().export(report, pdf_path)

    audit_log.log(
        action=AuditAction.REPORT_EXPORTED,
        company_id=company_id,
        user_id="demo_user",
        details={"formats": ["json", "html", "pdf"], "output_dir": output_dir},
    )

    # -------------------------------------------------------------------------
    # 10. Print Summary
    # -------------------------------------------------------------------------
    _print_summary(composite_result, roi_result, compliance_report, output_dir)

    return composite_result


def _print_summary(composite, roi, compliance, output_dir):
    """Print a formatted summary to console."""
    print("\n" + "=" * 70)
    print("COMPOSITE ROI REPORT SUMMARY")
    print("=" * 70)

    exec_summary = composite.get("executive_summary", {})
    print(f"\nTotal Annual Savings (Medium): ${exec_summary.get('total_savings_medium', 0):>12,.0f}")
    print(f"Total Annual Savings (Low):    ${exec_summary.get('total_savings_low', 0):>12,.0f}")
    print(f"Total Annual Savings (High):   ${exec_summary.get('total_savings_high', 0):>12,.0f}")

    print(f"\nKPIs Analyzed: {exec_summary.get('kpi_count', 0)}")
    print(f"KPIs Approved: {exec_summary.get('approved_kpis', 0)}")

    roi_dict = composite.get("roi", {})
    print(f"\nProgram Cost (Year 1):      ${roi_dict.get('total_cost_year1', 0):>12,.0f}")
    print(f"Program Cost (3-Year):      ${roi_dict.get('total_cost_3year', 0):>12,.0f}")
    print(f"Monthly Savings:            ${roi_dict.get('monthly_savings_medium', 0):>12,.0f}")
    payback = roi_dict.get('payback_months')
    print(f"Payback Period:             {f'{payback:.1f} months' if payback else 'N/A':>12s}")
    multiple = roi_dict.get('savings_to_cost_multiple')
    print(f"Savings-to-Cost Multiple:   {f'{multiple:.2f}x' if multiple else 'N/A':>12s}")
    npv = roi_dict.get('npv')
    print(f"NPV:                        ${npv:>11,.0f}" if npv else "NPV:                            N/A")

    print(f"\nCompliance: {compliance.overall_status.upper()}")
    print(f"  Passed: {compliance.to_dict()['passed']}, Failed: {compliance.to_dict()['failed']}, Warnings: {compliance.to_dict()['warnings']}")

    # Savings by category
    reconciled = composite.get("savings_reconciliation", {}).get("reconciled_totals", {})
    by_cat = reconciled.get("by_category", {})
    if by_cat:
        print("\nSavings by Category:")
        print(f"  {'Category':<35s} {'Low':>12s} {'Medium':>12s} {'High':>12s}")
        print("  " + "-" * 73)
        for cat, vals in sorted(by_cat.items(), key=lambda x: x[1].get("medium", 0), reverse=True):
            print(f"  {cat:<35s} ${vals.get('low', 0):>10,.0f} ${vals.get('medium', 0):>10,.0f} ${vals.get('high', 0):>10,.0f}")

    # Risks
    risks = exec_summary.get("key_risks", [])
    if risks:
        print(f"\nKey Risks:")
        for risk in risks:
            print(f"  - {risk}")

    print(f"\nReports exported to: {output_dir}/")
    print("  - composite_roi_report.json")
    print("  - composite_roi_report.html")
    print("  - composite_roi_report.pdf (or .txt)")
    print("=" * 70)


# =============================================================================
# CLI Entry Point
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Loweconex Digital Twin → Multi-Agent Composite ROI Platform"
    )
    parser.add_argument(
        "--output-dir", default="./reports",
        help="Output directory for reports (default: ./reports)"
    )
    parser.add_argument(
        "--kpis", nargs="*", default=None,
        help="Specific KPIs to run (default: all 14)"
    )
    parser.add_argument(
        "--no-scenarios", action="store_true",
        help="Skip scenario simulation"
    )
    parser.add_argument(
        "--list-kpis", action="store_true",
        help="List all available KPI names"
    )

    args = parser.parse_args()

    if args.list_kpis:
        print("Available KPI crews:")
        for name in get_all_kpi_names():
            spec = KPI_REGISTRY[name]
            print(f"  {name:<45s} {spec.display_name}")
        sys.exit(0)

    result = run_demo(
        output_dir=args.output_dir,
        kpi_subset=args.kpis,
        run_scenarios=not args.no_scenarios,
    )
