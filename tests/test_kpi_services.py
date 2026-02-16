"""
Unit tests for all 14 KPI computation services, the orchestrator,
and the deterministic double-counting reconciliation.

These tests use synthetic data and do not require a database or external services.
"""

import sys
import os
import pytest
from datetime import datetime, timezone
from typing import Any, Dict, List

# Ensure project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from predictive_maintenance.services.kpi.base import KPIConfig, KPIResult, BaseKPIService
from predictive_maintenance.services.kpi.registry import KPI_REGISTRY, get_kpi_service
from predictive_maintenance.services.kpi.energy_kpi import EnergyReductionKPI
from predictive_maintenance.services.kpi.refrigerant_kpi import RefrigerantLeakReductionKPI
from predictive_maintenance.services.kpi.workorder_kpi import WorkOrderReductionKPI
from predictive_maintenance.services.kpi.remaining_kpis import (
    FoodWasteReductionKPI,
    AssetFailurePredictionKPI,
    PPMMaximizationKPI,
    FoodSafetyComplianceKPI,
    ESGComplianceKPI,
    AssetUptimeIncreaseKPI,
    CallCenterReductionKPI,
    ServiceBureauReductionKPI,
    PreventiveMaintenanceOptKPI,
    FoodTempDiagnosticsKPI,
    CapExLifecycleKPI,
)
from predictive_maintenance.services.kpi.loweconex_bridge import (
    _deterministic_reconciliation,
    _OVERLAP_PAIRS,
)


# ── Test fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def config():
    """Default KPIConfig for testing."""
    return KPIConfig(
        site_id="test-site",
        customer_name="Test Corp",
        total_assets=50,
        total_locations=3,
    )


@pytest.fixture
def asset_data():
    """Synthetic asset list."""
    return [
        {"asset_id": f"A-{i:03d}", "site_id": "test-site", "asset_type": "hvac_rtu",
         "manufacturer": "Carrier", "is_active": True, "install_date": "2018-01-01"}
        for i in range(50)
    ]


@pytest.fixture
def alert_data():
    """Synthetic alert list with a mix of types and outcomes."""
    alerts = []
    for i in range(30):
        alerts.append({
            "alert_id": f"ALR-{i:03d}",
            "asset_id": f"A-{i % 50:03d}",
            "alert_type": "actionable" if i % 3 == 0 else "watch" if i % 3 == 1 else "dispatch",
            "severity": "high" if i % 5 == 0 else "medium",
            "primary_fault": ["compressor_degradation", "refrigerant_leak", "condenser_fouling",
                              "fan_bearing_wear", "sensor_drift"][i % 5],
            "confidence": 0.85,
            "false_alarm_probability": 0.10,
            "feedback_outcome": "confirmed_fault" if i % 4 == 0 else "no_issue_found" if i % 4 == 1 else None,
            "status": "active",
            "created_at": datetime.now(timezone.utc),
        })
    return alerts


@pytest.fixture
def telemetry_summary():
    """Synthetic telemetry summary."""
    return {
        "telemetry_count": 10_000,
        "avg_compressor_power_kw": 3.5,
        "total_compressor_hours": 8_333,
        "energy_kwh_annual": 7_000_000,
        "reactive_work_order_count_annual": 480,
        "work_order_avg_cost": 350,
        "work_order_count_annual": 600,
        "work_order_total_cost_annual": 210_000,
        "maintenance_total_cost_annual": 175_000,
    }


@pytest.fixture
def health_data():
    """Synthetic health data with a range of scores."""
    return [
        {"asset_id": f"A-{i:03d}", "health_score": 90 - i, "rul_hours": 5000 - i * 100,
         "degradation_index": 0.05 + i * 0.02, "sensor_trust_score": 95 - i}
        for i in range(50)
    ]


# ── Registry Tests ────────────────────────────────────────────────────

class TestKPIRegistry:
    def test_registry_has_14_kpis(self):
        assert len(KPI_REGISTRY) == 14

    def test_all_registry_entries_are_base_subclasses(self):
        for name, cls in KPI_REGISTRY.items():
            assert issubclass(cls, BaseKPIService), f"{name} is not a BaseKPIService subclass"

    def test_get_kpi_service_valid(self, config):
        svc = get_kpi_service("energy_reduction", config)
        assert isinstance(svc, EnergyReductionKPI)

    def test_get_kpi_service_invalid(self, config):
        with pytest.raises(KeyError):
            get_kpi_service("nonexistent_kpi", config)


# ── KPIConfig Tests ───────────────────────────────────────────────────

class TestKPIConfig:
    def test_default_config_validates(self):
        cfg = KPIConfig()
        errors = cfg.validate()
        assert errors == [], f"Default config has validation errors: {errors}"

    def test_invalid_config_catches_errors(self):
        cfg = KPIConfig(total_assets=-1, energy_cost_per_kwh=0, discount_rate=5.0)
        errors = cfg.validate()
        assert len(errors) >= 3
        assert any("total_assets" in e for e in errors)
        assert any("energy_cost_per_kwh" in e for e in errors)
        assert any("discount_rate" in e for e in errors)

    def test_configurable_reduction_fields_exist(self):
        cfg = KPIConfig()
        assert hasattr(cfg, "energy_penalty_pct_degraded")
        assert hasattr(cfg, "wo_reduction_pct")
        assert hasattr(cfg, "refrigerant_reduction_factor")
        assert hasattr(cfg, "carbon_price_per_tco2")
        assert hasattr(cfg, "food_waste_reduction_pct")


# ── KPIResult Tests ───────────────────────────────────────────────────

class TestKPIResult:
    def test_data_grounded_auto_set(self):
        r = KPIResult(kpi_name="test", display_name="Test", category="Test",
                      data_points_used=100, data_coverage_pct=0.10)
        assert r.data_grounded is True

    def test_data_not_grounded_without_data(self):
        r = KPIResult(kpi_name="test", display_name="Test", category="Test",
                      data_points_used=0, data_coverage_pct=0.0)
        assert r.data_grounded is False

    def test_approve_sets_status(self):
        r = KPIResult(kpi_name="test", display_name="Test", category="Test")
        r.approve()
        assert r.status == "approved"

    def test_to_dict_keys(self):
        r = KPIResult(kpi_name="test", display_name="Test", category="Test",
                      savings_medium=1000.0)
        d = r.to_dict()
        assert "kpi_name" in d
        assert "savings_medium" in d
        assert "confidence" in d
        assert "data_grounded" in d
        assert d["savings_medium"] == 1000.0


# ── Individual KPI Service Tests ──────────────────────────────────────

class TestEnergyReductionKPI:
    def test_compute_returns_positive_savings(self, config, asset_data, alert_data,
                                               telemetry_summary, health_data):
        svc = EnergyReductionKPI(config)
        result = svc.compute(asset_data, alert_data, telemetry_summary, health_data)
        assert result.savings_medium > 0
        assert result.savings_low <= result.savings_medium <= result.savings_high
        assert 0 < result.confidence <= 1.0
        assert result.kpi_name == "energy_reduction"

    def test_uses_configurable_penalty(self, config, asset_data, alert_data,
                                        telemetry_summary, health_data):
        config.energy_penalty_pct_degraded = 0.30
        svc = EnergyReductionKPI(config)
        result_high = svc.compute(asset_data, alert_data, telemetry_summary, health_data)

        config.energy_penalty_pct_degraded = 0.05
        svc2 = EnergyReductionKPI(config)
        result_low = svc2.compute(asset_data, alert_data, telemetry_summary, health_data)

        assert result_high.savings_medium > result_low.savings_medium


class TestRefrigerantLeakReductionKPI:
    def test_compute_returns_positive_savings(self, config, asset_data, alert_data,
                                               telemetry_summary, health_data):
        svc = RefrigerantLeakReductionKPI(config)
        result = svc.compute(asset_data, alert_data, telemetry_summary, health_data)
        assert result.savings_medium > 0
        assert result.kpi_name == "refrigerant_leak_reduction"

    def test_epa_penalty_applied_for_high_leak_rate(self, config, asset_data, alert_data,
                                                      telemetry_summary, health_data):
        config.baseline_leak_rate_pct = 20.0  # above 15% EPA threshold
        svc = RefrigerantLeakReductionKPI(config)
        result = svc.compute(asset_data, alert_data, telemetry_summary, health_data)
        assert result.supporting_metrics["epa_penalty_avoided"] > 0


class TestWorkOrderReductionKPI:
    def test_compute_returns_positive_savings(self, config, asset_data, alert_data,
                                               telemetry_summary, health_data):
        svc = WorkOrderReductionKPI(config)
        result = svc.compute(asset_data, alert_data, telemetry_summary, health_data)
        assert result.savings_medium > 0
        assert result.kpi_name == "work_order_reduction"


class TestAllRemainingKPIs:
    """Parametric test that every KPI service computes without errors."""

    @pytest.mark.parametrize("kpi_name", list(KPI_REGISTRY.keys()))
    def test_kpi_computes_without_error(self, kpi_name, config, asset_data,
                                         alert_data, telemetry_summary, health_data):
        svc = get_kpi_service(kpi_name, config)
        result = svc.compute(asset_data, alert_data, telemetry_summary, health_data)

        assert isinstance(result, KPIResult)
        assert result.kpi_name == kpi_name
        assert result.savings_low <= result.savings_medium <= result.savings_high
        assert 0 <= result.confidence <= 1.0
        assert result.status in ("pending", "approved", "rejected", "error")
        assert len(result.narrative) > 0

    @pytest.mark.parametrize("kpi_name", list(KPI_REGISTRY.keys()))
    def test_kpi_handles_empty_data(self, kpi_name, config):
        """KPIs should not crash with completely empty data inputs."""
        svc = get_kpi_service(kpi_name, config)
        result = svc.compute([], [], {"telemetry_count": 0}, [])

        assert isinstance(result, KPIResult)
        assert result.kpi_name == kpi_name
        assert result.savings_medium >= 0


# ── ESG Math Bug Regression Test ──────────────────────────────────────

class TestESGComplianceKPI:
    def test_savings_not_inflated(self, config, asset_data, alert_data,
                                   telemetry_summary, health_data):
        """Regression: ESG savings should be total_tco2 * carbon_price, not *1000."""
        svc = ESGComplianceKPI(config)
        result = svc.compute(asset_data, alert_data, telemetry_summary, health_data)
        # With default config, total tCO2 should be modest (< 500 tCO2e for 50 assets).
        # At $50/tCO2, savings_medium should be < $25,000 (not millions).
        assert result.savings_medium < 100_000, (
            f"ESG savings_medium={result.savings_medium} looks inflated (math bug regression)"
        )

    def test_uses_configurable_carbon_price(self, config, asset_data, alert_data,
                                              telemetry_summary, health_data):
        config.carbon_price_per_tco2 = 100.0
        svc_high = ESGComplianceKPI(config)
        result_high = svc_high.compute(asset_data, alert_data, telemetry_summary, health_data)

        config.carbon_price_per_tco2 = 25.0
        svc_low = ESGComplianceKPI(config)
        result_low = svc_low.compute(asset_data, alert_data, telemetry_summary, health_data)

        assert result_high.savings_medium > result_low.savings_medium


# ── Double-Counting Reconciliation Tests ──────────────────────────────

class TestDeterministicReconciliation:
    def test_reconciliation_reduces_totals(self):
        """Total after reconciliation should be less than raw sum."""
        results = [
            KPIResult(kpi_name="energy_reduction", display_name="Energy", category="Energy",
                      savings_medium=50_000),
            KPIResult(kpi_name="esg_compliance", display_name="ESG", category="ESG",
                      savings_medium=10_000),
            KPIResult(kpi_name="work_order_reduction", display_name="WO", category="WO",
                      savings_medium=30_000),
            KPIResult(kpi_name="service_bureau_reduction", display_name="SB", category="SB",
                      savings_medium=20_000),
        ]
        raw_total = sum(r.savings_medium for r in results)

        recon = _deterministic_reconciliation(results)
        assert recon["reconciled"] is True
        assert recon["total_after_reconciliation"] < raw_total
        assert recon["total_haircut"] > 0
        assert len(recon["adjustments"]) > 0

    def test_no_overlap_when_single_kpi(self):
        results = [
            KPIResult(kpi_name="energy_reduction", display_name="Energy", category="Energy",
                      savings_medium=50_000),
        ]
        recon = _deterministic_reconciliation(results)
        assert recon["total_after_reconciliation"] == 50_000
        assert recon["total_haircut"] == 0.0
        assert len(recon["adjustments"]) == 0

    def test_overlap_pairs_are_valid_kpi_names(self):
        valid_names = set(KPI_REGISTRY.keys())
        for kpi_a, kpi_b, pct in _OVERLAP_PAIRS:
            assert kpi_a in valid_names, f"{kpi_a} not in registry"
            assert kpi_b in valid_names, f"{kpi_b} not in registry"
            assert 0 < pct < 1.0, f"Haircut {pct} out of range"


# ── Orchestrator Smoke Test ───────────────────────────────────────────

class TestKPIOrchestrator:
    def test_compute_all_returns_dashboard(self, config, asset_data, alert_data,
                                            telemetry_summary, health_data):
        from predictive_maintenance.services.kpi.orchestrator import KPIOrchestrator
        orch = KPIOrchestrator(config)
        result = orch.compute_all(
            asset_data=asset_data,
            alert_data=alert_data,
            telemetry_summary=telemetry_summary,
            health_data=health_data,
        )
        assert hasattr(result, "scorecards")
        assert len(result.scorecards) == 14
        assert result.executive_summary["total_savings_medium"] > 0

    def test_compute_pipeline_returns_result(self, config, asset_data, alert_data,
                                              telemetry_summary, health_data):
        from predictive_maintenance.services.kpi.orchestrator import KPIOrchestrator
        orch = KPIOrchestrator(config)
        result = orch.compute_pipeline(
            pipeline_type="capex_asset_replacement",
            asset_data=asset_data,
            alert_data=alert_data,
            telemetry_summary=telemetry_summary,
            health_data=health_data,
        )
        assert result["status"] == "completed"
        assert len(result["scorecards"]) > 0
