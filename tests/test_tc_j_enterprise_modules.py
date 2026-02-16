"""
TC-J: Enterprise Modules (TC-J01–J06)

Tests twin versioning/schema registry, data quality engine,
MLOps model registry, execution engine, security controls,
and benchmarking engine.
"""

import pytest

from loweconex_platform.twin_versioning.schema_registry import (
    SchemaRegistry, SchemaVersion, SchemaField, SchemaContract,
    CompatibilityChecker, CompatibilityMode,
)
from loweconex_platform.data_quality.quality_engine import (
    DataQualityEngine, ExpectationSuite, Expectation, ExpectationType,
    QualityGate, QualityReport, QualityDimension,
)
from loweconex_platform.mlops.model_registry import (
    ModelRegistry, ModelVersion, ModelCard, DriftMonitor,
)
from loweconex_platform.execution.execution_engine import (
    ExecutionEngine, ControlActionLog, RecommendationTracker, RecommendationRecord,
)
from loweconex_platform.security.security_controls import (
    SecurityControlsRegistry, OWASPCheck, SLSAProvenance, ComplianceReport,
)
from loweconex_platform.benchmarking.benchmark_engine import (
    BenchmarkEngine, CohortDefinition, NormalizationMethod, BenchmarkProvenance,
    BenchmarkDistribution, NormalizationType,
)


# =============================================================================
# TC-J01: Twin Versioning / Schema Registry
# =============================================================================

class TestTCJ01SchemaRegistry:
    def test_register_and_get_schema(self):
        registry = SchemaRegistry()
        version = SchemaVersion(
            schema_id="asset_twin_v1",
            model_name="AssetTwin",
            version="1.0.0",
            fields=[
                SchemaField(name="asset_id", field_type="string", required=True),
                SchemaField(name="location_id", field_type="string", required=True),
                SchemaField(name="asset_type", field_type="string"),
            ],
        )
        result = registry.register_schema(version)
        assert result["status"] == "registered"
        retrieved = registry.get_schema("asset_twin_v1")
        assert retrieved is not None
        assert retrieved.version == "1.0.0"

    def test_schema_version_bump(self):
        registry = SchemaRegistry()
        v1 = SchemaVersion(schema_id="v1", model_name="Twin", version="1.0.0",
                           fields=[SchemaField(name="a", field_type="string")])
        v2 = SchemaVersion(schema_id="v2", model_name="Twin", version="2.0.0",
                           fields=[SchemaField(name="a", field_type="string"),
                                   SchemaField(name="b", field_type="int")],
                           previous_version="v1")
        registry.register_schema(v1)
        registry.register_schema(v2)
        latest = registry.get_latest("Twin")
        assert latest.version == "2.0.0"

    def test_compatibility_check_backward(self):
        old = SchemaVersion(schema_id="s1", model_name="T", version="1.0.0",
                            fields=[SchemaField(name="a", field_type="string")])
        new = SchemaVersion(schema_id="s2", model_name="T", version="2.0.0",
                            fields=[SchemaField(name="a", field_type="string"),
                                    SchemaField(name="b", field_type="int")])
        result = CompatibilityChecker.check(old, new, CompatibilityMode.BACKWARD)
        assert result["compatible"] is True

    def test_compatibility_check_breaking(self):
        old = SchemaVersion(schema_id="s1", model_name="T", version="1.0.0",
                            fields=[SchemaField(name="a", field_type="string"),
                                    SchemaField(name="b", field_type="int")])
        new = SchemaVersion(schema_id="s2", model_name="T", version="2.0.0",
                            fields=[SchemaField(name="a", field_type="string")])
        result = CompatibilityChecker.check(old, new, CompatibilityMode.BACKWARD)
        assert result["compatible"] is False

    def test_schema_contract(self):
        contract = SchemaContract(
            contract_id="c1",
            kpi_name="energy_reduction",
            input_schema_id="asset_twin_v1",
            output_schema_id="kpi_output_v1",
            min_input_version="1.0.0",
        )
        assert contract.kpi_name == "energy_reduction"


# =============================================================================
# TC-J02: Data Quality Engine
# =============================================================================

class TestTCJ02DataQuality:
    def test_expectation_suite_creation(self):
        suite = ExpectationSuite(suite_id="telemetry_quality", dataset_name="telemetry")
        suite.add_expectation(Expectation(
            name="asset_id_not_null", expectation_type=ExpectationType.NOT_NULL.value,
            column="asset_id",
        ))
        suite.add_expectation(Expectation(
            name="timestamp_not_null", expectation_type=ExpectationType.NOT_NULL.value,
            column="timestamp",
        ))
        suite.add_expectation(Expectation(
            name="temp_in_range", expectation_type=ExpectationType.IN_RANGE.value,
            column="temperature", params={"min": -40, "max": 150},
        ))
        assert len(suite.expectations) == 3

    def test_quality_engine_passes_good_data(self):
        engine = DataQualityEngine()
        suite = ExpectationSuite(suite_id="test", dataset_name="test_data")
        suite.add_expectation(Expectation(
            name="val_not_null", expectation_type=ExpectationType.NOT_NULL.value,
            column="value",
        ))
        engine.register_suite(suite)
        data = [{"value": 1}, {"value": 2}, {"value": 3}]
        report = engine.validate("test", data)
        assert report.pass_rate >= 0.9

    def test_quality_engine_fails_bad_data(self):
        engine = DataQualityEngine()
        suite = ExpectationSuite(suite_id="strict", dataset_name="strict_data")
        suite.add_expectation(Expectation(
            name="val_not_null", expectation_type=ExpectationType.NOT_NULL.value,
            column="value",
        ))
        engine.register_suite(suite)
        data = [{"value": None}, {"value": None}, {"value": 3}]
        report = engine.validate("strict", data)
        assert report.pass_rate < 1.0

    def test_quality_gate_evaluates_report(self):
        gate = QualityGate(min_overall_score=0.9)
        good_report = QualityReport(overall_score=0.95)
        bad_report = QualityReport(overall_score=0.5)
        good_result = gate.evaluate(good_report)
        bad_result = gate.evaluate(bad_report)
        assert good_result["decision"] == "pass"
        assert bad_result["decision"] == "block"


# =============================================================================
# TC-J03: MLOps Model Registry
# =============================================================================

class TestTCJ03MLOps:
    def test_register_model_version(self):
        registry = ModelRegistry()
        version = ModelVersion(
            model_name="fault_detector",
            version="1.0.0",
            metrics={"accuracy": 0.92, "f1": 0.89},
        )
        vid = registry.register_version(version)
        assert vid is not None
        retrieved = registry.get_version(vid)
        assert retrieved is not None
        assert retrieved.metrics["accuracy"] == 0.92

    def test_model_card_creation(self):
        card = ModelCard(
            model_name="fault_detector",
            description="HVAC fault detection model",
            intended_use="Predictive maintenance for RTUs",
            limitations=["Limited to RTU assets", "Requires 30 days of baseline data"],
            training_data_description="12 months of telemetry from 500 RTUs",
        )
        assert card.model_name == "fault_detector"
        assert len(card.limitations) == 2

    def test_drift_monitor_no_drift(self):
        monitor = DriftMonitor(perf_decay_warning=0.10, perf_decay_critical=0.25)
        monitor.set_baseline("model_a", metrics={"accuracy": 0.92})
        alerts = monitor.check_performance_drift("model_a", {"accuracy": 0.91})
        assert len(alerts) == 0

    def test_drift_monitor_detects_drift(self):
        monitor = DriftMonitor(perf_decay_warning=0.10, perf_decay_critical=0.25)
        monitor.set_baseline("model_a", metrics={"accuracy": 0.92})
        alerts = monitor.check_performance_drift("model_a", {"accuracy": 0.60})
        assert len(alerts) >= 1
        assert alerts[0].severity in ("warning", "critical")

    def test_model_registry_list_versions(self):
        registry = ModelRegistry()
        registry.register_version(ModelVersion(model_name="m1", version="1.0.0"))
        registry.register_version(ModelVersion(model_name="m1", version="1.1.0"))
        registry.register_version(ModelVersion(model_name="m1", version="2.0.0"))
        versions = registry.get_all_versions("m1")
        assert len(versions) == 3


# =============================================================================
# TC-J04: Execution Engine
# =============================================================================

class TestTCJ04Execution:
    def test_recommendation_tracker_lifecycle(self):
        tracker = RecommendationTracker()
        rec = RecommendationRecord(
            title="Replace RTU-005",
            kpi_name="energy_reduction",
            company_id="COMP-1",
            recommended_action="Replace aging RTU with high-efficiency unit",
            estimated_savings_usd=12000,
        )
        rec_id = tracker.create(rec)
        assert rec_id is not None
        tracker.accept(rec_id, accepted_by="manager-1")
        accepted = tracker.get(rec_id)
        assert accepted.acceptance_status in ("accepted", "partially_accepted")

    def test_recommendation_rejection(self):
        tracker = RecommendationTracker()
        rec = RecommendationRecord(title="Low-value rec", company_id="COMP-1")
        rec_id = tracker.create(rec)
        tracker.reject(rec_id, reason="Cost too high")
        rejected = tracker.get(rec_id)
        assert rejected.acceptance_status == "rejected"

    def test_execution_engine_propose_action(self):
        engine = ExecutionEngine()
        from loweconex_platform.execution.execution_engine import ControlAction
        action = ControlAction(
            action_type="setpoint_change",
            asset_id="RTU-001",
            description="Lower cooling setpoint to 72F",
            proposed_by="energy_crew",
        )
        result = engine.propose_action(action)
        assert result is not None
        assert "status" in result


# =============================================================================
# TC-J05: Security Controls
# =============================================================================

class TestTCJ05Security:
    def test_owasp_check_creation(self):
        check = OWASPCheck(
            asvs_ref="V4.1.1",
            category="Access Control",
            requirement="Verify access controls on every API endpoint",
        )
        assert check.asvs_ref == "V4.1.1"
        d = check.to_dict()
        assert d["category"] == "Access Control"

    def test_slsa_provenance_creation(self):
        prov = SLSAProvenance(
            artifact_name="energy_crew_agent",
            artifact_type="agent",
            builder="github_actions",
            source_repo="github.com/org/repo",
            source_ref="abc123",
        )
        assert prov.artifact_name == "energy_crew_agent"
        d = prov.to_dict()
        assert d["builder"] == "github_actions"

    def test_compliance_report_generation(self):
        registry = SecurityControlsRegistry()
        registry.add_baseline_controls()
        registry.add_baseline_owasp_checks()
        report = registry.generate_compliance_report()
        assert report.iso_controls_total > 0
        assert report.owasp_checks_total > 0


# =============================================================================
# TC-J06: Benchmarking Engine
# =============================================================================

class TestTCJ06Benchmarking:
    def test_cohort_definition(self):
        cohort = CohortDefinition(
            cohort_id="grocery_southeast",
            name="Southeast Grocery Stores",
        )
        assert cohort.cohort_id == "grocery_southeast"

    def test_benchmark_distribution(self):
        dist = BenchmarkDistribution(
            cohort_id="test_cohort",
            kpi_name="energy_reduction",
            metric_name="kwh_per_sqft",
        )
        dist.compute_from_values([48, 52, 55, 60, 42, 50])
        assert dist.n_samples == 6
        assert dist.median > 0
        assert dist.p25 > 0
        assert dist.p75 > 0

    def test_normalization_method(self):
        method = NormalizationMethod(
            name="Per Square Foot",
            normalization_type=NormalizationType.FLOOR_AREA.value,
        )
        result = method.normalize(raw_value=50000, normalizing_factor=10000)
        assert result == 5.0

    def test_benchmark_provenance(self):
        prov = BenchmarkProvenance(
            cohort_id="grocery_southeast",
            source_type="internal_portfolio",
            source_name="twin_store",
            methodology="median comparison",
        )
        assert prov.methodology == "median comparison"
        d = prov.to_dict()
        assert d["source_type"] == "internal_portfolio"
