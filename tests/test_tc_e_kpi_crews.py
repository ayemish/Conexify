"""
TC-E: KPI Crew Execution (TC-E01–E05)

Tests KPI crew specs, deterministic calculation, QA checks,
energy M&V integration, and food safety enhancements.
"""

import pytest
from unittest.mock import MagicMock

from loweconex_platform.kpi_crews.registry import (
    KPI_REGISTRY, get_all_kpi_names,
    calc_work_order_reduction, calc_energy_reduction,
    calc_food_safety_compliance, calc_refrigerant_leak_reduction,
    calc_esg_compliance, calc_capex_lifecycle_optimization,
    _safe_div, _savings_bands,
)
from loweconex_platform.kpi_crews.base_crew import (
    KPICrewSpec, KPICrewResult, KPICrewFactory, KPICrew,
)
from loweconex_platform.kpi_crews.tools import LoweconexTools, ArtifactStore
from loweconex_platform.digital_twins.store import TwinStore
from shared.event_bus.redis_event_bus import RedisEventBus


@pytest.fixture
def twin_store():
    return TwinStore()


@pytest.fixture
def event_bus():
    return RedisEventBus(agent_id="test")


@pytest.fixture
def tools(twin_store, event_bus):
    return LoweconexTools(twin_store, event_bus)


@pytest.fixture
def mock_tools():
    t = MagicMock(spec=LoweconexTools)
    t.query_events.return_value = []
    t.get_assets_for_scope.return_value = []
    t.get_locations_for_company.return_value = []
    t.load_research_snippets.return_value = []
    t.store_artifact.return_value = "art_mock_1"
    t.fetch_tariffs.return_value = {}
    return t


# =============================================================================
# TC-E01: KPI Registry Coverage
# =============================================================================

class TestTCE01Registry:
    def test_registry_has_14_kpis(self):
        assert len(KPI_REGISTRY) == 14

    def test_all_kpi_names_returns_14(self):
        names = get_all_kpi_names()
        assert len(names) == 14

    def test_every_spec_has_calculation_fn(self):
        for name, spec in KPI_REGISTRY.items():
            assert spec.calculation_fn is not None, f"{name} missing calculation_fn"

    def test_every_spec_has_required_fields(self):
        for name, spec in KPI_REGISTRY.items():
            assert spec.kpi_name, f"{name} missing kpi_name"
            assert spec.display_name, f"{name} missing display_name"
            assert spec.objective, f"{name} missing objective"
            assert len(spec.formulas) > 0, f"{name} missing formulas"
            assert len(spec.output_metrics) > 0, f"{name} missing output_metrics"
            assert spec.savings_category, f"{name} missing savings_category"


# =============================================================================
# TC-E02: Deterministic Calculation Functions
# =============================================================================

class TestTCE02Calculations:
    def test_work_order_reduction_with_defaults(self, mock_tools):
        result = calc_work_order_reduction(
            tools=mock_tools, company_id="COMP-1", location_id=None,
            assets=[{"asset_id": "A1"}, {"asset_id": "A2"}],
            locations=[], scenario_params={}, research={},
        )
        assert "metrics" in result
        assert "savings_low" in result
        assert "savings_medium" in result
        assert "savings_high" in result
        assert result["savings_low"] <= result["savings_medium"] <= result["savings_high"]
        assert 0 <= result["confidence"] <= 1

    def test_energy_reduction_with_sqft(self, mock_tools):
        result = calc_energy_reduction(
            tools=mock_tools, company_id="COMP-1", location_id="LOC-1",
            assets=[{"asset_id": "A1", "asset_type": "hvac_rtu"}],
            locations=[{"sqft": 60000}],
            scenario_params={"electricity_rate": 0.10, "energy_reduction_pct": 0.15},
            research={},
        )
        assert result["metrics"]["total_sqft"] == 60000
        assert result["metrics"]["reduction_pct"] == 0.15
        assert result["metrics"]["baseline_kwh_annual"] == 60000 * 52.5  # EIA CBECS 2018 benchmark
        assert result["savings_medium"] > 0

    def test_energy_reduction_includes_mv_result(self, mock_tools):
        result = calc_energy_reduction(
            tools=mock_tools, company_id="COMP-1", location_id=None,
            assets=[], locations=[{"sqft": 50000}],
            scenario_params={}, research={},
        )
        # M&V result should be present (either real or skipped)
        metrics = result["metrics"]
        assert "mv_status" in metrics

    def test_refrigerant_leak_reduction(self, mock_tools):
        result = calc_refrigerant_leak_reduction(
            tools=mock_tools, company_id="COMP-1", location_id=None,
            assets=[{"asset_id": "R1", "asset_type": "refrigeration_rack"}],
            locations=[{}], scenario_params={}, research={},
        )
        assert result["metrics"]["co2e_avoided_tonnes"] > 0
        assert result["metrics"]["baseline_leak_rate"] == 0.25  # EPA GreenChill 2022 industry avg

    def test_esg_compliance_scopes(self, mock_tools):
        result = calc_esg_compliance(
            tools=mock_tools, company_id="COMP-1", location_id=None,
            assets=[], locations=[{"sqft": 50000}],
            scenario_params={"energy_savings_kwh": 100000, "refrigerant_avoided_lbs": 500},
            research={},
        )
        assert result["metrics"]["scope2_reduction_tco2e"] > 0
        assert result["metrics"]["scope1_reduction_tco2e"] > 0
        assert result["metrics"]["total_reduction_tco2e"] > 0

    def test_capex_lifecycle_with_assets(self, mock_tools):
        assets = [
            {"asset_id": f"A{i}", "age_years": 15, "health": {"health_score": 50, "failure_risk_90d": 0.2},
             "economics": {"capex_replace_cost": 10000, "opex_baseline_monthly": 800}}
            for i in range(5)
        ]
        result = calc_capex_lifecycle_optimization(
            tools=mock_tools, company_id="COMP-1", location_id=None,
            assets=assets, locations=[],
            scenario_params={"annual_capex_budget": 100000}, research={},
        )
        assert result["metrics"]["total_assets_analyzed"] == 5
        assert result["metrics"]["replacements_recommended"] >= 0


# =============================================================================
# TC-E03: Food Safety KPI Enhancements
# =============================================================================

class TestTCE03FoodSafety:
    def test_food_safety_includes_time_out_of_range(self, mock_tools):
        result = calc_food_safety_compliance(
            tools=mock_tools, company_id="COMP-1", location_id=None,
            assets=[], locations=[{}], scenario_params={}, research={},
        )
        assert "time_out_of_range_hours_monthly" in result["metrics"]
        assert "corrective_action_sla_hours" in result["metrics"]
        assert "sla_compliance_rate" in result["metrics"]
        assert "violation_count_total" in result["metrics"]

    def test_food_safety_with_excursion_events(self, mock_tools):
        mock_tools.query_events.side_effect = lambda cid, f: (
            [{"payload": {"duration_minutes": 45}}, {"payload": {"duration_minutes": 20}}]
            if f.get("event_type") == "temp_excursion"
            else [{"payload": {"response_time_hours": 2.0}}, {"payload": {"response_time_hours": 6.0}}]
        )
        result = calc_food_safety_compliance(
            tools=mock_tools, company_id="COMP-1", location_id=None,
            assets=[], locations=[{}], scenario_params={"corrective_action_sla_hours": 4.0},
            research={},
        )
        assert result["metrics"]["excursion_count"] == 2
        assert result["metrics"]["sla_met_count"] == 1
        assert result["metrics"]["sla_breached_count"] == 1

    def test_food_safety_narrative_includes_sla(self, mock_tools):
        result = calc_food_safety_compliance(
            tools=mock_tools, company_id="COMP-1", location_id=None,
            assets=[], locations=[{}], scenario_params={}, research={},
        )
        assert "SLA compliance" in result["narrative"]
        assert "Time out of range" in result["narrative"]


# =============================================================================
# TC-E04: QA Checks
# =============================================================================

class TestTCE04QAChecks:
    def test_savings_ordering_check(self):
        result = KPICrewResult(kpi_name="test")
        result.savings_low = 100
        result.savings_medium = 50  # WRONG: low > medium
        result.savings_high = 200
        crew = KPICrew.__new__(KPICrew)
        crew.result = result
        crew.spec = KPICrewSpec(kpi_name="test", display_name="Test", objective="Test")
        issues = crew._run_qa_checks()
        assert any(i["type"] == "savings_ordering" for i in issues)

    def test_confidence_out_of_range(self):
        result = KPICrewResult(kpi_name="test")
        result.savings_low = 10
        result.savings_medium = 20
        result.savings_high = 30
        result.confidence = 1.5  # Out of range
        crew = KPICrew.__new__(KPICrew)
        crew.result = result
        crew.spec = KPICrewSpec(kpi_name="test", display_name="Test", objective="Test")
        issues = crew._run_qa_checks()
        assert any(i["type"] == "confidence_range" for i in issues)

    def test_valid_result_has_no_blockers(self):
        result = KPICrewResult(kpi_name="test")
        result.savings_low = 10
        result.savings_medium = 20
        result.savings_high = 30
        result.confidence = 0.7
        result.assumptions = ["test assumption"]
        crew = KPICrew.__new__(KPICrew)
        crew.result = result
        crew.spec = KPICrewSpec(kpi_name="test", display_name="Test", objective="Test")
        issues = crew._run_qa_checks()
        blockers = [i for i in issues if i.get("severity") == "blocker"]
        assert len(blockers) == 0


# =============================================================================
# TC-E05: Helper Utilities
# =============================================================================

class TestTCE05Helpers:
    def test_safe_div_normal(self):
        assert _safe_div(10, 2) == 5.0

    def test_safe_div_zero_denominator(self):
        assert _safe_div(10, 0) == 0.0

    def test_safe_div_custom_default(self):
        assert _safe_div(10, 0, default=-1.0) == -1.0

    def test_savings_bands(self):
        bands = _savings_bands(1000)
        assert bands["savings_low"] == 500
        assert bands["savings_medium"] == 1000
        assert bands["savings_high"] == 1500

    def test_savings_bands_custom_pcts(self):
        bands = _savings_bands(1000, low_pct=0.3, high_pct=2.0)
        assert bands["savings_low"] == 300
        assert bands["savings_high"] == 2000
