"""
TC-H: Lineage Tracking & M&V Verification (TC-H01–H03)

Tests LineageTracker provenance, MVEngine reconciliation,
and baseline/reporting period management.
"""

import pytest

from loweconex_platform.lineage.lineage_tracker import (
    LineageTracker, LineageGraph, DatasetFacet, JobFacet, RunFacet,
    DatasetType, JobType,
)
from loweconex_platform.mv_verification.mv_engine import (
    MVEngine, MVPlan, BaselineWindow, ReconciliationReport,
    IPMVPOption, AdjustmentRule, AdjustmentType,
)


# =============================================================================
# TC-H01: Lineage Tracker
# =============================================================================

class TestTCH01Lineage:
    def test_start_and_complete_job(self):
        tracker = LineageTracker()
        run_id = tracker.start_job(
            job_name="ingest_telemetry",
            job_type=JobType.INGESTION.value,
            company_id="COMP-1",
        )
        assert run_id is not None
        ds_in = DatasetFacet(name="bms:telemetry", dataset_type=DatasetType.RAW_TELEMETRY.value, row_count=1000)
        ds_out = DatasetFacet(name="twin_store:COMP-1", dataset_type=DatasetType.TWIN_SNAPSHOT.value)
        tracker.add_input(run_id, ds_in)
        tracker.add_output(run_id, ds_out)
        event = tracker.complete_job(run_id)
        assert event is not None
        assert len(event.input_datasets) == 1
        assert len(event.output_datasets) == 1

    def test_fail_job_records_error(self):
        tracker = LineageTracker()
        run_id = tracker.start_job(job_name="bad_job", job_type=JobType.INGESTION.value)
        event = tracker.fail_job(run_id, error="Connection timeout")
        assert event is not None
        assert event.run.error_message == "Connection timeout"
        assert event.event_type == "FAIL"

    def test_lineage_graph_build(self):
        graph = LineageGraph()
        tracker = LineageTracker(graph=graph)
        run_id = tracker.start_job(job_name="etl_job", job_type=JobType.NORMALIZATION.value)
        ds_in = DatasetFacet(name="raw_data", dataset_type=DatasetType.RAW_TELEMETRY.value)
        ds_out = DatasetFacet(name="clean_data", dataset_type=DatasetType.NORMALIZED.value)
        tracker.add_input(run_id, ds_in)
        tracker.add_output(run_id, ds_out)
        tracker.complete_job(run_id)
        # Graph should have recorded events, datasets, and jobs
        assert len(graph._events) >= 2  # START + COMPLETE
        assert len(graph._datasets) >= 2

    def test_lineage_query_by_dataset(self):
        graph = LineageGraph()
        tracker = LineageTracker(graph=graph)
        j1 = tracker.start_job(job_name="job_a", job_type=JobType.INGESTION.value)
        ds_x = DatasetFacet(name="dataset_x", dataset_type=DatasetType.NORMALIZED.value)
        tracker.add_output(j1, ds_x)
        tracker.complete_job(j1)
        j2 = tracker.start_job(job_name="job_b", job_type=JobType.KPI_CALCULATION.value)
        tracker.add_input(j2, ds_x)
        tracker.complete_job(j2)
        # dataset_x should be both produced and consumed
        assert ds_x.dataset_id in graph._produced_by
        assert ds_x.dataset_id in graph._consumed_by


# =============================================================================
# TC-H02: M&V Engine
# =============================================================================

class TestTCH02MVEngine:
    def test_register_plan(self):
        engine = MVEngine()
        plan = MVPlan(
            plan_id="mv-001",
            company_id="COMP-1",
            ipmvp_option=IPMVPOption.OPTION_C.value,
            baseline=BaselineWindow(
                start_date="2024-01-01", end_date="2024-12-31",
                mean_daily=100.0, std_daily=15.0, n_days=365,
                cv_rmse=0.12,
            ),
        )
        engine.register_plan(plan)
        retrieved = engine.get_plan("mv-001")
        assert retrieved is not None
        assert retrieved.ipmvp_option == IPMVPOption.OPTION_C.value

    def test_reconcile_period_savings(self):
        engine = MVEngine()
        plan = MVPlan(
            plan_id="mv-002",
            company_id="COMP-1",
            ipmvp_option=IPMVPOption.OPTION_C.value,
            baseline=BaselineWindow(
                start_date="2024-01-01", end_date="2024-12-31",
                mean_daily=100.0, std_daily=15.0, n_days=365,
                cv_rmse=0.10,
            ),
        )
        engine.register_plan(plan)
        report = engine.reconcile_period(
            plan_id="mv-002",
            period_start="2025-01-01",
            period_end="2025-12-31",
            predicted_savings_kwh=4500,
            predicted_savings_usd=450,
            actual_baseline_kwh=36500,
            actual_reporting_kwh=32000,
        )
        assert report is not None
        assert report.actual_savings_kwh > 0
        assert report.actual_savings_usd > 0

    def test_ipmvp_options_exist(self):
        assert IPMVPOption.OPTION_A.value == "A"
        assert IPMVPOption.OPTION_B.value == "B"
        assert IPMVPOption.OPTION_C.value == "C"
        assert IPMVPOption.OPTION_D.value == "D"

    def test_reconcile_no_savings(self):
        engine = MVEngine()
        plan = MVPlan(
            plan_id="mv-003",
            company_id="COMP-1",
            ipmvp_option=IPMVPOption.OPTION_C.value,
            baseline=BaselineWindow(
                start_date="2024-01-01", end_date="2024-12-31",
                mean_daily=100.0, std_daily=15.0, n_days=365,
                cv_rmse=0.10,
            ),
        )
        engine.register_plan(plan)
        report = engine.reconcile_period(
            plan_id="mv-003",
            period_start="2025-01-01",
            period_end="2025-12-31",
            predicted_savings_kwh=0,
            predicted_savings_usd=0,
            actual_baseline_kwh=36500,
            actual_reporting_kwh=36500,
        )
        assert report is not None
        assert report.actual_savings_kwh == 0


# =============================================================================
# TC-H03: Adjustment Rules
# =============================================================================

class TestTCH03AdjustmentRules:
    def test_adjustment_rule_creation(self):
        rule = AdjustmentRule(
            rule_id="adj-001",
            adjustment_type=AdjustmentType.WEATHER.value,
            description="Normalize baseline for heating/cooling degree days",
            variable="CDD_65",
            method="regression",
            coefficient=2.5,
        )
        assert rule.rule_id == "adj-001"
        assert rule.adjustment_type == "weather"
        assert rule.coefficient == 2.5

    def test_adjustment_rule_compute(self):
        rule = AdjustmentRule(coefficient=2.5, variable="CDD_65")
        adj = rule.compute_adjustment(baseline_value=1000, reporting_value=1200)
        assert adj == 2.5 * (1200 - 1000)

    def test_engine_with_adjustment_rules(self):
        engine = MVEngine()
        plan = MVPlan(
            plan_id="mv-adj",
            company_id="COMP-1",
            ipmvp_option=IPMVPOption.OPTION_C.value,
            baseline=BaselineWindow(
                start_date="2024-01-01", end_date="2024-12-31",
                mean_daily=100.0, std_daily=15.0, n_days=365,
                cv_rmse=0.10,
            ),
            adjustment_rules=[
                AdjustmentRule(
                    rule_id="adj-weather",
                    adjustment_type=AdjustmentType.WEATHER.value,
                    variable="CDD_65",
                    coefficient=2.0,
                ),
            ],
        )
        engine.register_plan(plan)
        retrieved = engine.get_plan("mv-adj")
        assert len(retrieved.adjustment_rules) == 1
