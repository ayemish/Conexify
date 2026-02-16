"""
TC-K: Agent Ops & Operating Model (TC-K01–K04)

Tests golden test suites, runbooks, replay engine,
RACIMatrix, SLA tracker, and agent health monitoring.
"""

import pytest

from loweconex_platform.agent_ops.agent_ops_engine import (
    GoldenTestSuite, GoldenTestCase, Runbook, RunbookStep, RunbookTrigger,
    ReplayEngine, AgentHealthMonitor, create_standard_runbooks,
)
from loweconex_platform.operating_model.operating_model import (
    RACIMatrix, RACIEntry, RACIRole,
    SLATracker, SLADefinition,
    ReviewScheduler, ReviewCadence, ReviewType,
    ExceptionManager, ExceptionRecord, ExceptionType, ExceptionPriority,
)


# =============================================================================
# TC-K01: Golden Test Suite
# =============================================================================

class TestTCK01GoldenTests:
    def test_create_golden_test_case(self):
        case = GoldenTestCase(
            test_id="gt-001",
            name="Energy KPI smoke test",
            kpi_name="energy_reduction",
            inputs={"company_id": "COMP-1", "assets": [], "locations": [{"sqft": 50000}]},
            expected_outputs={"savings_medium": 36000, "confidence": 0.75},
            tolerances={"savings_medium": 0.10},
        )
        assert case.test_id == "gt-001"
        assert case.kpi_name == "energy_reduction"

    def test_golden_suite_add_and_run(self):
        suite = GoldenTestSuite(suite_name="test_suite", kpi_name="test")
        suite.add_case(GoldenTestCase(
            test_id="gt-001",
            name="Basic test",
            kpi_name="test",
            inputs={"x": 10},
            expected_outputs={"result": 20},
        ))
        result = suite.run_all(lambda inputs: {"result": inputs["x"] * 2})
        assert result["all_passed"] is True
        assert result["passed"] == 1

    def test_golden_suite_detects_failure(self):
        suite = GoldenTestSuite(suite_name="fail_suite")
        suite.add_case(GoldenTestCase(
            test_id="gt-fail",
            name="Failing test",
            inputs={"x": 10},
            expected_outputs={"result": 20},
        ))
        result = suite.run_all(lambda inputs: {"result": 999})
        assert result["all_passed"] is False
        assert result["failed"] == 1

    def test_golden_suite_input_hash(self):
        case = GoldenTestCase(inputs={"a": 1, "b": 2})
        h = case.compute_input_hash()
        assert h is not None
        assert len(h) == 16


# =============================================================================
# TC-K02: Runbooks
# =============================================================================

class TestTCK02Runbooks:
    def test_create_runbook_with_steps(self):
        runbook = Runbook(
            runbook_id="rb-001",
            name="Energy KPI Recovery",
            description="Steps to recover failed energy KPI calculation",
            trigger=RunbookTrigger.AGENT_FAILURE.value,
            steps=[
                RunbookStep(1, "Check twin store", "Verify connectivity"),
                RunbookStep(2, "Verify data freshness", "Check timestamps"),
                RunbookStep(3, "Re-trigger crew", "Restart energy crew"),
            ],
        )
        assert runbook.runbook_id == "rb-001"
        assert len(runbook.steps) == 3

    def test_runbook_to_dict(self):
        runbook = Runbook(
            runbook_id="rb-002",
            name="Test",
            steps=[RunbookStep(1, "Step 1", "Do thing")],
        )
        d = runbook.to_dict()
        assert d["runbook_id"] == "rb-002"
        assert len(d["steps"]) == 1

    def test_standard_runbooks_created(self):
        runbooks = create_standard_runbooks()
        assert len(runbooks) >= 3
        names = [r.name for r in runbooks]
        assert any("Dead-Letter" in n for n in names)
        assert any("Agent Failure" in n or "KPI Agent" in n for n in names)


# =============================================================================
# TC-K03: Replay Engine
# =============================================================================

class TestTCK03ReplayEngine:
    def test_create_and_replay_session(self):
        engine = ReplayEngine()
        session = engine.create_session(
            original_run_id="run-001",
            lineage_event_id="le-001",
            kpi_name="energy_reduction",
            frozen_inputs={"x": 10},
            frozen_config={},
            original_outputs={"result": 20},
        )
        replayed = engine.replay(
            session.session_id,
            calculation_fn=lambda inputs: {"result": inputs["x"] * 2},
        )
        assert replayed.outputs_match is True

    def test_replay_detects_drift(self):
        engine = ReplayEngine()
        session = engine.create_session(
            original_run_id="run-002",
            lineage_event_id="le-002",
            kpi_name="test",
            frozen_inputs={"x": 10},
            frozen_config={},
            original_outputs={"result": 20},
        )
        replayed = engine.replay(
            session.session_id,
            calculation_fn=lambda inputs: {"result": 999},
        )
        assert replayed.outputs_match is False
        assert len(replayed.mismatches) >= 1

    def test_reproducibility_report(self):
        engine = ReplayEngine()
        s1 = engine.create_session("r1", "le1", "kpi_a", {"x": 1}, {}, {"y": 2})
        engine.replay(s1.session_id, lambda i: {"y": 2})
        s2 = engine.create_session("r2", "le2", "kpi_b", {"x": 1}, {}, {"y": 2})
        engine.replay(s2.session_id, lambda i: {"y": 999})
        report = engine.reproducibility_report()
        assert report["total_sessions"] == 2
        assert report["matched"] == 1
        assert report["drifted"] == 1


# =============================================================================
# TC-K04: Agent Health Monitor
# =============================================================================

class TestTCK04AgentHealth:
    def test_record_execution_and_check_health(self):
        monitor = AgentHealthMonitor()
        for _ in range(10):
            monitor.record_execution("energy_crew", success=True, duration_ms=200)
        health = monitor.get_health("energy_crew")
        assert health["status"] == "healthy"
        assert health["failure_rate"] == 0.0

    def test_detect_degraded_agent(self):
        monitor = AgentHealthMonitor(degradation_threshold=0.15)
        for _ in range(8):
            monitor.record_execution("bad_agent", success=True, duration_ms=100)
        for _ in range(4):
            monitor.record_execution("bad_agent", success=False, duration_ms=100)
        health = monitor.get_health("bad_agent")
        assert health["status"] in ("degraded", "unhealthy")

    def test_agent_health_stats(self):
        monitor = AgentHealthMonitor()
        monitor.record_execution("a1", success=True, duration_ms=100)
        monitor.record_execution("a2", success=True, duration_ms=100)
        stats = monitor.stats()
        assert stats["tracked_agents"] == 2

    def test_get_all_health(self):
        monitor = AgentHealthMonitor()
        monitor.record_execution("a1", success=True, duration_ms=100)
        monitor.record_execution("a2", success=True, duration_ms=100)
        all_health = monitor.get_all_health()
        assert len(all_health) == 2


# =============================================================================
# TC-K: Operating Model (RACI, SLA, Reviews, Exceptions)
# =============================================================================

class TestTCKOperatingModel:
    def test_raci_matrix_assign_and_query(self):
        raci = RACIMatrix()
        raci.assign(RACIEntry(
            kpi_name="energy_reduction",
            activity="kpi_calculation",
            raci_role=RACIRole.RESPONSIBLE.value,
            person_or_role="kpi_crew",
        ))
        raci.assign(RACIEntry(
            kpi_name="energy_reduction",
            activity="kpi_calculation",
            raci_role=RACIRole.ACCOUNTABLE.value,
            person_or_role="platform_admin",
        ))
        responsible = raci.get_responsible("energy_reduction", "kpi_calculation")
        assert "kpi_crew" in responsible
        accountable = raci.get_accountable("energy_reduction", "kpi_calculation")
        assert accountable == "platform_admin"

    def test_sla_tracker_met(self):
        tracker = SLATracker()
        sla = SLADefinition(
            sla_id="sla-001",
            name="KPI Latency",
            metric="kpi_latency_hours",
            target_value=4,
            warning_threshold=8,
            breach_threshold=24,
            operator="<",
        )
        tracker.register_sla(sla)
        tracker.record_measurement("sla-001", 2.0)
        summary = tracker.compliance_summary()
        assert summary["KPI Latency"]["last_status"] == "met"

    def test_sla_tracker_breach(self):
        tracker = SLATracker()
        sla = SLADefinition(
            sla_id="sla-002",
            name="Data Freshness",
            metric="data_age_hours",
            target_value=24,
            warning_threshold=36,
            breach_threshold=48,
            operator="<",
        )
        tracker.register_sla(sla)
        tracker.record_measurement("sla-002", 72.0)
        breaches = tracker.get_breaches()
        assert len(breaches) >= 1

    def test_review_scheduler(self):
        scheduler = ReviewScheduler()
        scheduler.add_standard_cadence()
        all_reviews = scheduler.get_all()
        assert len(all_reviews) >= 4

    def test_exception_manager_lifecycle(self):
        manager = ExceptionManager()
        exc = ExceptionRecord(
            title="KPI calculation exceeded time limit",
            exception_type=ExceptionType.CALCULATION_ERROR.value,
            priority=ExceptionPriority.MEDIUM.value,
            description="Energy KPI took >4h",
        )
        exc_id = manager.create(exc)
        assert exc_id is not None
        manager.triage(exc_id, assigned_to="engineer-1")
        manager.resolve(exc_id, resolution="Scaled worker pool", root_cause="Data volume spike")
        open_exc = manager.get_open()
        assert len(open_exc) == 0

    def test_exception_pattern_analysis(self):
        manager = ExceptionManager()
        for i in range(5):
            manager.create(ExceptionRecord(
                title=f"Data gap {i}",
                exception_type=ExceptionType.DATA_GAP.value,
                kpi_name="energy_reduction",
            ))
        analysis = manager.pattern_analysis()
        assert analysis["total"] == 5
        assert analysis["by_type"]["data_gap"] == 5
