"""Import smoke tests for monorepo package boundaries."""

from pathlib import Path
import sys
import importlib

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _import(module: str) -> None:
    importlib.import_module(module)


def test_import_smoke():
    modules = [
        "predictive_maintenance",
        "oil_gas",
        "shared",
        "shared.agents",
        "oil_gas.agents",
        "oil_gas.agents.pdm_model_agents",
        "oil_gas.pdm_integrated_system",
    ]

    for module in modules:
        _import(module)


def test_import_loweconex_platform():
    modules = [
        "loweconex_platform",
        "loweconex_platform.config",
        "loweconex_platform.digital_twins.models",
        "loweconex_platform.digital_twins.store",
        "loweconex_platform.digital_twins.relationships",
        "loweconex_platform.event_bus.events",
        "loweconex_platform.event_bus.redis_streams",
        "loweconex_platform.ingestion.connectors",
        "loweconex_platform.ingestion.normalizer",
        "loweconex_platform.kpi_crews.registry",
        "loweconex_platform.kpi_crews.base_crew",
        "loweconex_platform.kpi_crews.tools",
        "loweconex_platform.kpi_crews.crewai_tools",
        "loweconex_platform.orchestration.orchestrator_crew",
        "loweconex_platform.orchestration.scenario_agent",
        "loweconex_platform.orchestration.decision_ledger",
        "loweconex_platform.orchestration.portfolio_optimizer",
        "loweconex_platform.roi_engine.savings_engine",
        "loweconex_platform.roi_engine.attribution_ledger",
        "loweconex_platform.roi_engine.cost_model",
        "loweconex_platform.reporting.composite_report",
        "loweconex_platform.reporting.exporters",
        "loweconex_platform.governance.rbac",
        "loweconex_platform.lineage",
        "loweconex_platform.semantic",
        "loweconex_platform.twin_versioning",
        "loweconex_platform.mv_verification",
        "loweconex_platform.mlops",
        "loweconex_platform.ai_risk",
        "loweconex_platform.data_quality",
        "loweconex_platform.execution",
        "loweconex_platform.security",
        "loweconex_platform.operating_model",
        "loweconex_platform.benchmarking",
        "loweconex_platform.agent_ops",
        "loweconex_platform.pdm_bridge",
        "loweconex_platform.pdm_bridge.bridge",
        "loweconex_platform.orchestration.decision_advisory_agent",
    ]

    for module in modules:
        _import(module)
