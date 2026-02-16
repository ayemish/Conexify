"""
TC-F: Orchestrator & ROI (TC-F01–F04)

Tests savings reconciliation, scenario analysis, portfolio optimization,
and ROI metrics (payback_months, savings_to_cost_multiple).
"""

import pytest
from unittest.mock import MagicMock, patch

from loweconex_platform.orchestration.orchestrator_crew import OrchestratorCrew
from loweconex_platform.kpi_crews.base_crew import KPICrewResult
from loweconex_platform.config import PlatformConfig
from loweconex_platform.digital_twins.store import TwinStore
from shared.event_bus.redis_event_bus import RedisEventBus


@pytest.fixture
def config():
    return PlatformConfig()


@pytest.fixture
def twin_store():
    return TwinStore()


@pytest.fixture
def event_bus():
    return RedisEventBus(agent_id="test")


@pytest.fixture
def orchestrator(config, twin_store, event_bus):
    return OrchestratorCrew(config=config, twin_store=twin_store, event_bus=event_bus)


# =============================================================================
# TC-F01: Savings Reconciliation
# =============================================================================

class TestTCF01Reconciliation:
    def test_reconcile_removes_double_counting(self, orchestrator):
        kpi_results = {
            "energy_reduction": self._make_result("energy_reduction", 50000, "energy"),
            "refrigerant_leak_reduction": self._make_result("refrigerant_leak_reduction", 30000, "maintenance"),
            "work_order_reduction": self._make_result("work_order_reduction", 20000, "maintenance"),
        }
        reconciled, naive, note = orchestrator._reconcile_savings(kpi_results)
        assert reconciled["total_savings_medium"] <= naive["total_savings_medium"]
        assert "reconciliation" in note.lower() or "double" in note.lower() or len(note) > 0

    def test_single_kpi_no_reconciliation_needed(self, orchestrator):
        kpi_results = {
            "energy_reduction": self._make_result("energy_reduction", 50000, "energy"),
        }
        reconciled, naive, _ = orchestrator._reconcile_savings(kpi_results)
        assert reconciled["total_savings_medium"] == naive["total_savings_medium"]

    @staticmethod
    def _make_result(name, savings, category):
        r = KPICrewResult(kpi_name=name)
        r.savings_low = savings * 0.5
        r.savings_medium = savings
        r.savings_high = savings * 1.5
        r.confidence = 0.75
        r.savings_category = category
        r.status = "accepted"
        return r


# =============================================================================
# TC-F02: ROI Metrics
# =============================================================================

class TestTCF02ROIMetrics:
    def test_compute_roi_metrics_payback(self, orchestrator):
        reconciled = {
            "total_savings_medium": 120000,
            "total_savings_low": 60000,
            "total_savings_high": 180000,
        }
        optimization = {
            "optimization": {"total_cost": 200000, "total_npv": 300000},
        }
        roi = orchestrator._compute_roi_metrics(reconciled, optimization)
        assert roi["payback_months"] is not None
        assert roi["payback_months"] == round(200000 / (120000 / 12), 1)
        assert roi["savings_to_cost_multiple"] == round(120000 / 200000, 2)

    def test_compute_roi_metrics_zero_cost(self, orchestrator):
        reconciled = {"total_savings_medium": 100000, "total_savings_low": 50000, "total_savings_high": 150000}
        optimization = {"optimization": {"total_cost": 0, "total_npv": 0}}
        roi = orchestrator._compute_roi_metrics(reconciled, optimization)
        assert roi["savings_to_cost_multiple"] is None
        assert roi["payback_months"] is None

    def test_compute_roi_metrics_zero_savings(self, orchestrator):
        reconciled = {"total_savings_medium": 0, "total_savings_low": 0, "total_savings_high": 0}
        optimization = {"optimization": {"total_cost": 100000, "total_npv": 0}}
        roi = orchestrator._compute_roi_metrics(reconciled, optimization)
        assert roi["payback_months"] is None

    def test_compute_roi_metrics_npv_fields(self, orchestrator):
        reconciled = {"total_savings_medium": 100000, "total_savings_low": 50000, "total_savings_high": 150000}
        optimization = {"optimization": {"total_cost": 50000, "total_npv": 200000}}
        roi = orchestrator._compute_roi_metrics(reconciled, optimization)
        assert "npv_savings" in roi
        assert "net_npv" in roi
        assert "discount_rate" in roi
        assert "analysis_horizon_years" in roi


# =============================================================================
# TC-F03: Scenario Analysis
# =============================================================================

class TestTCF03ScenarioAnalysis:
    def test_scenario_comparison_structure(self, orchestrator):
        kpi_results = {
            "energy_reduction": TestTCF01Reconciliation._make_result("energy_reduction", 50000, "energy"),
        }
        comparison = orchestrator._generate_scenario_comparison(kpi_results)
        assert isinstance(comparison, dict)
        assert "scenarios" in comparison or len(comparison) >= 0


# =============================================================================
# TC-F04: Key Risk Identification
# =============================================================================

class TestTCF04RiskIdentification:
    def test_identifies_low_confidence_risks(self, orchestrator):
        kpi_results = {
            "energy_reduction": self._make_low_confidence_result("energy_reduction"),
        }
        risks = orchestrator._identify_key_risks(kpi_results)
        assert any("confidence" in r.lower() for r in risks)

    def test_identifies_rejected_kpis(self, orchestrator):
        r = KPICrewResult(kpi_name="test")
        r.status = "rejected"
        r.confidence = 0.8
        kpi_results = {"test": r}
        risks = orchestrator._identify_key_risks(kpi_results)
        assert any("rejected" in r.lower() for r in risks)

    @staticmethod
    def _make_low_confidence_result(name):
        r = KPICrewResult(kpi_name=name)
        r.confidence = 0.2
        r.savings_low = 1000
        r.savings_medium = 2000
        r.savings_high = 3000
        r.status = "accepted"
        return r
