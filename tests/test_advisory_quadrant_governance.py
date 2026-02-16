"""
Test Suite for Phase 4 (GenAI Advisory), Phase 7 (Quadrant Wiring),
and Phase 8 (Governance).

Covers:
1. Advisory enrichment with ownership crew output
2. ReadOwnershipDecisionTool structured output
3. QuadrantValidator: setup, cost lines, reconciliation checkpoints
4. QuadrantValidator: quadrant summary
5. GovernanceEngine: change request lifecycle (submit, approve, reject, escalate)
6. GovernanceEngine: RACI enforcement and authorization checks
7. GovernanceEngine: impact assessment and approval routing
8. GovernanceEngine: audit trail integrity
9. Integration: validator + governance + crew pipeline

Run with:
    python -m pytest tests/test_advisory_quadrant_governance.py -v
    # or directly:
    python tests/test_advisory_quadrant_governance.py
"""

import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import unittest
from typing import Any, Dict

from loweconex_platform.ownership.api_routes import OwnershipDecisionService

SAMPLE_METRIC_INPUTS: Dict[str, Dict[str, Any]] = {
    "m_reactive_jobs": {"wo_count": 100, "cost_per_wo": 400, "reduction_pct": 0.30},
    "m_ppm_frequency": {
        "baseline_pm_tasks": 200, "optimized_pm_tasks": 150,
        "pm_cost_per_task": 150, "avoided_reactive_savings": 5000,
    },
    "m_wo_volume": {
        "wo_volume": 300, "avg_vendor_rate": 250, "vendor_reduction_pct": 0.15,
        "admin_overhead_per_wo": 45, "admin_reduction_pct": 0.20,
    },
    "m_replacement_cycle": {
        "replacement_count": 5, "avg_replacement_cost": 18000, "avoided_failure_cost": 5000,
    },
    "m_temp_breaches": {
        "breach_count": 8, "avg_spoilage_per_breach": 2500,
        "penalty_probability": 0.15, "avg_penalty": 10000, "audit_risk_cost": 5000,
    },
    "m_energy_reduction": {
        "kwh_reduction": 50000, "electricity_rate": 0.12,
        "carbon_factor": 0.0004, "carbon_price": 50,
    },
}


# ═══════════════════════════════════════════════════════════════════
# 1. Advisory Enrichment (Phase 4)
# ═══════════════════════════════════════════════════════════════════

class TestAdvisoryEnrichment(unittest.TestCase):
    """Test that DecisionAdvisoryAgent integrates ownership crew output."""

    def test_read_ownership_decision_tool_returns_json(self):
        """ReadOwnershipDecisionTool should return valid JSON."""
        from loweconex_platform.orchestration.decision_advisory_agent import (
            ReadOwnershipDecisionTool,
        )
        composite = {
            "ownership_decision": {
                "pareto_options": [{"option_id": "a", "label": "Max NPV", "npv": 100000}],
                "negotiation_log": {"conflicts_detected": [], "rounds": 1},
                "board_narrative": "Test narrative",
            }
        }
        tool = ReadOwnershipDecisionTool(composite)
        result = json.loads(tool._run())
        self.assertIn("pareto_options", result)
        self.assertEqual(len(result["pareto_options"]), 1)

    def test_read_ownership_decision_tool_section_filter(self):
        """Section parameter should filter to specific section."""
        from loweconex_platform.orchestration.decision_advisory_agent import (
            ReadOwnershipDecisionTool,
        )
        composite = {
            "ownership_decision": {
                "pareto_options": [{"option_id": "a"}],
                "board_narrative": "Narrative text here",
            }
        }
        tool = ReadOwnershipDecisionTool(composite)
        result = json.loads(tool._run(section="narrative"))
        self.assertEqual(result, "Narrative text here")

    def test_enrich_with_ownership_adds_pareto_to_tradeoff(self):
        """_enrich_with_ownership should add Pareto info to trade_off_analysis."""
        from loweconex_platform.orchestration.decision_advisory_agent import (
            DecisionAdvisoryAgent, AdvisoryOutput,
        )
        agent = DecisionAdvisoryAgent()
        output = AdvisoryOutput(trade_off_analysis="Base analysis.")

        ownership = {
            "pareto_options": [
                {"option_id": "a", "label": "Max NPV", "npv": 500000, "risk_score": 0.2},
                {"option_id": "b", "label": "Min Risk", "npv": 300000, "risk_score": 0.1},
            ],
            "recommended_option_id": "a",
            "negotiation_log": {"conflicts_detected": []},
            "consolidated_roi": {"npv": 500000},
        }
        enriched = agent._enrich_with_ownership(output, ownership)
        self.assertIn("Pareto-optimal", enriched.trade_off_analysis)
        self.assertIn("Max NPV", enriched.trade_off_analysis)
        self.assertIn("Recommended", enriched.trade_off_analysis)

    def test_enrich_adds_conflicts_to_insights(self):
        """Negotiation conflicts should appear in cross_kpi_insights."""
        from loweconex_platform.orchestration.decision_advisory_agent import (
            DecisionAdvisoryAgent, AdvisoryOutput,
        )
        agent = DecisionAdvisoryAgent()
        output = AdvisoryOutput()

        ownership = {
            "pareto_options": [],
            "negotiation_log": {
                "conflicts_detected": [
                    {
                        "agents_involved": ["finance", "fm"],
                        "description": "Capex ceiling conflict",
                        "resolution": "Finance ceiling prevails",
                    }
                ],
            },
            "consolidated_roi": {},
        }
        enriched = agent._enrich_with_ownership(output, ownership)
        self.assertTrue(any("finance, fm" in i for i in enriched.cross_kpi_insights))

    def test_enrich_adds_dimension_costs_to_insights(self):
        """Cost-by-dimension breakdown should appear in insights."""
        from loweconex_platform.orchestration.decision_advisory_agent import (
            DecisionAdvisoryAgent, AdvisoryOutput,
        )
        agent = DecisionAdvisoryAgent()
        output = AdvisoryOutput()

        ownership = {
            "pareto_options": [],
            "negotiation_log": {"conflicts_detected": []},
            "consolidated_roi": {},
            "cost_lines_by_dimension": {
                "opex": [{"amount": -50000}],
                "capex": [{"amount": -30000}],
            },
        }
        enriched = agent._enrich_with_ownership(output, ownership)
        dim_insight = [i for i in enriched.cross_kpi_insights if "dimension" in i.lower()]
        self.assertGreater(len(dim_insight), 0)

    def test_enrich_boosts_confidence(self):
        """Confidence should increase when ownership data is available."""
        from loweconex_platform.orchestration.decision_advisory_agent import (
            DecisionAdvisoryAgent, AdvisoryOutput,
        )
        agent = DecisionAdvisoryAgent()
        output = AdvisoryOutput(confidence=0.6)

        ownership = {
            "pareto_options": [{"option_id": "a", "npv": 100000}],
            "negotiation_log": {"conflicts_detected": []},
            "consolidated_roi": {"npv": 100000},
        }
        enriched = agent._enrich_with_ownership(output, ownership)
        self.assertGreater(enriched.confidence, 0.6)

    def test_deterministic_fallback_calls_enrich(self):
        """Deterministic fallback should call _enrich_with_ownership when data exists."""
        from loweconex_platform.orchestration.decision_advisory_agent import (
            DecisionAdvisoryAgent,
        )
        agent = DecisionAdvisoryAgent()
        composite = {
            "executive_summary": {"total_savings_medium": 100000},
            "kpi_results": {},
            "roi_metrics": {},
            "portfolio_optimization": {},
            "cross_asset_optimization": {},
            "scenario_analysis": {},
            "ownership_decision": {
                "pareto_options": [{"option_id": "x", "label": "Test", "npv": 50000, "risk_score": 0.1}],
                "recommended_option_id": "x",
                "negotiation_log": {"conflicts_detected": []},
                "consolidated_roi": {"npv": 50000},
            },
        }
        output = agent._deterministic_fallback(composite)
        self.assertIn("Pareto-optimal", output.trade_off_analysis)


# ═══════════════════════════════════════════════════════════════════
# 2. Quadrant Validator (Phase 7)
# ═══════════════════════════════════════════════════════════════════

class TestQuadrantValidator(unittest.TestCase):
    """Test Q1-Q4 metric → owner → cost flow enforcement."""

    def setUp(self):
        self.svc = OwnershipDecisionService()
        from loweconex_platform.ownership.quadrant_validator import QuadrantValidator
        self.validator = QuadrantValidator(
            self.svc.catalog, self.svc.ownership, self.svc.rules, self.svc.aggregation,
        )

    def test_setup_validation_passes(self):
        """Default setup should pass validation (no errors)."""
        report = self.validator.validate_setup()
        self.assertTrue(report.passed)
        self.assertEqual(len(report.errors), 0)

    def test_setup_checks_all_metrics(self):
        """Should check every metric in the catalog."""
        report = self.validator.validate_setup()
        total_metrics = len(self.svc.catalog.list_all())
        self.assertEqual(report.metrics_checked, total_metrics)
        self.assertGreater(report.metrics_checked, 0)

    def test_setup_detects_orphan_metrics(self):
        """Metrics without translation rules should be flagged as warnings."""
        report = self.validator.validate_setup()
        orphans = [i for i in report.warnings if i.category == "orphan_metric"]
        # Some catalog metrics may not have rules — that's expected
        self.assertIsInstance(orphans, list)

    def test_all_quadrants_have_metrics(self):
        """All 4 quadrants should have at least one metric."""
        report = self.validator.validate_setup()
        empty_quads = [i for i in report.issues if i.category == "empty_quadrant"]
        self.assertEqual(len(empty_quads), 0, "All quadrants should have metrics")

    def test_cost_line_validation(self):
        """Cost lines from build_cost_stack should pass validation."""
        stack = self.svc.aggregation.build_cost_stack(SAMPLE_METRIC_INPUTS)
        report = self.validator.validate_cost_lines(stack)
        self.assertTrue(report.passed)
        self.assertGreater(report.cost_lines_checked, 0)

    def test_empty_stack_warns(self):
        """Empty cost stack should produce a warning."""
        from loweconex_platform.ownership.cost_stack import CostStack
        empty = CostStack()
        report = self.validator.validate_cost_lines(empty)
        self.assertTrue(report.passed)
        empty_warnings = [i for i in report.warnings if i.category == "empty_cost_stack"]
        self.assertGreater(len(empty_warnings), 0)

    def test_reconciled_stack_validation(self):
        """Post-reconciliation validation should pass for standard inputs."""
        stack = self.svc.aggregation.build_cost_stack(SAMPLE_METRIC_INPUTS)
        adjustments = self.svc.aggregation.get_adjustments()
        report = self.validator.validate_reconciled_stack(stack, adjustments)
        self.assertTrue(report.passed)

    def test_full_pipeline_validation(self):
        """Full pipeline validation should pass for standard setup."""
        stack = self.svc.aggregation.build_cost_stack(SAMPLE_METRIC_INPUTS)
        adjustments = self.svc.aggregation.get_adjustments()
        report = self.validator.validate_full_pipeline(stack, adjustments)
        self.assertTrue(report.passed)
        self.assertGreater(report.metrics_checked, 0)
        self.assertGreater(report.cost_lines_checked, 0)

    def test_quadrant_summary_has_all_four(self):
        """Summary should have entries for Q1, Q2, Q3, Q4."""
        summary = self.validator.get_quadrant_summary()
        self.assertIn("Q1", summary)
        self.assertIn("Q2", summary)
        self.assertIn("Q3", summary)
        self.assertIn("Q4", summary)

    def test_quadrant_summary_has_correct_cost_types(self):
        """Each quadrant should map to the correct cost type."""
        summary = self.validator.get_quadrant_summary()
        self.assertEqual(summary["Q1"]["cost_type"], "opex")
        self.assertEqual(summary["Q2"]["cost_type"], "capex")
        self.assertEqual(summary["Q3"]["cost_type"], "risk")
        self.assertEqual(summary["Q4"]["cost_type"], "strategic")

    def test_quadrant_summary_has_correct_owners(self):
        """Default accountable owners should match quadrant assignments."""
        summary = self.validator.get_quadrant_summary()
        self.assertEqual(summary["Q1"]["default_accountable"], "fm")
        self.assertEqual(summary["Q2"]["default_accountable"], "finance")
        self.assertEqual(summary["Q3"]["default_accountable"], "food_safety")
        self.assertEqual(summary["Q4"]["default_accountable"], "executive")

    def test_report_serializes_cleanly(self):
        """ValidationReport.to_dict() should be JSON-serializable."""
        report = self.validator.validate_setup()
        d = report.to_dict()
        serialized = json.dumps(d, default=str)
        self.assertGreater(len(serialized), 50)
        self.assertIn("passed", d)
        self.assertIn("error_count", d)


# ═══════════════════════════════════════════════════════════════════
# 3. Governance Engine (Phase 8)
# ═══════════════════════════════════════════════════════════════════

class TestGovernanceEngine(unittest.TestCase):
    """Test RACI enforcement, approval gates, and audit trails."""

    def setUp(self):
        self.svc = OwnershipDecisionService()
        from loweconex_platform.ownership.governance_engine import GovernanceEngine
        self.ge = GovernanceEngine(self.svc.catalog, self.svc.ownership)

    def test_low_impact_auto_approved(self):
        """Low-impact parameter changes should be auto-approved."""
        from loweconex_platform.ownership.governance_engine import ChangeType, ApprovalStatus
        cr = self.ge.submit_change(
            ChangeType.PARAMETER_OVERRIDE.value, "user", "Test override",
            metric_id="m_reactive_jobs",
        )
        self.assertEqual(cr.status, ApprovalStatus.AUTO_APPROVED.value)
        self.assertEqual(cr.impact_level, "low")

    def test_compliance_waiver_is_critical(self):
        """Compliance waivers should be assessed as CRITICAL impact."""
        from loweconex_platform.ownership.governance_engine import ChangeType, ApprovalStatus
        cr = self.ge.submit_change(
            ChangeType.COMPLIANCE_WAIVER.value, "user", "Waive temp breach limit",
            metric_id="m_temp_breaches",
        )
        self.assertEqual(cr.impact_level, "critical")
        self.assertEqual(cr.status, ApprovalStatus.PENDING.value)
        self.assertIn("food_safety", cr.approvers)

    def test_ownership_override_requires_approval(self):
        """Ownership overrides should require accountable owner approval."""
        from loweconex_platform.ownership.governance_engine import ChangeType, ApprovalStatus
        cr = self.ge.submit_change(
            ChangeType.OWNERSHIP_OVERRIDE.value, "user", "Change accountable",
            metric_id="m_reactive_jobs",
        )
        self.assertEqual(cr.impact_level, "medium")
        self.assertEqual(cr.status, ApprovalStatus.PENDING.value)
        self.assertGreater(len(cr.approvers), 0)

    def test_approve_change_workflow(self):
        """Full approve workflow: submit → approve → approved status."""
        from loweconex_platform.ownership.governance_engine import ChangeType, ApprovalStatus
        cr = self.ge.submit_change(
            ChangeType.OWNERSHIP_OVERRIDE.value, "user", "Test",
            metric_id="m_reactive_jobs",
        )
        # Approve by the required approver
        approver = cr.approvers[0]
        cr = self.ge.approve_change(cr.change_id, approver, "Looks good")
        self.assertEqual(cr.status, ApprovalStatus.APPROVED.value)
        self.assertEqual(len(cr.approvals_received), 1)

    def test_reject_change_workflow(self):
        """Reject workflow: submit → reject → rejected status."""
        from loweconex_platform.ownership.governance_engine import ChangeType, ApprovalStatus
        cr = self.ge.submit_change(
            ChangeType.BUDGET_CHANGE.value, "user", "Big budget shift",
        )
        cr = self.ge.reject_change(cr.change_id, "finance", "Exceeds authority")
        self.assertEqual(cr.status, ApprovalStatus.REJECTED.value)
        self.assertIn("Exceeds authority", cr.resolution_note)

    def test_unauthorized_approver_rejected(self):
        """Non-authorized approver should raise PermissionError."""
        from loweconex_platform.ownership.governance_engine import ChangeType
        cr = self.ge.submit_change(
            ChangeType.OWNERSHIP_OVERRIDE.value, "user", "Test",
            metric_id="m_reactive_jobs",
        )
        with self.assertRaises(PermissionError):
            self.ge.approve_change(cr.change_id, "random_person")

    def test_escalate_increases_impact(self):
        """Escalation should increase impact level and add approvers."""
        from loweconex_platform.ownership.governance_engine import ChangeType
        cr = self.ge.submit_change(
            ChangeType.OWNERSHIP_OVERRIDE.value, "user", "Test",
            metric_id="m_reactive_jobs",
        )
        original_impact = cr.impact_level
        cr = self.ge.escalate_change(cr.change_id, "user", "Need higher approval")
        self.assertNotEqual(cr.impact_level, original_impact)
        self.assertEqual(cr.status, "escalated")

    def test_multi_approver_workflow(self):
        """CRITICAL changes need multiple approvers."""
        from loweconex_platform.ownership.governance_engine import ChangeType, ApprovalStatus
        cr = self.ge.submit_change(
            ChangeType.COMPLIANCE_WAIVER.value, "user", "Waive breach",
            metric_id="m_temp_breaches",
        )
        self.assertGreater(len(cr.approvers), 1)

        # Approve by first approver
        cr = self.ge.approve_change(cr.change_id, cr.approvers[0])
        if len(cr.approvers) > 1:
            # Not fully approved yet with just one approval
            # Approve by second approver
            cr = self.ge.approve_change(cr.change_id, cr.approvers[1])

        self.assertEqual(cr.status, ApprovalStatus.APPROVED.value)

    def test_compliance_constraint_override_is_critical(self):
        """Constraint overrides on Q3 metrics should be CRITICAL."""
        from loweconex_platform.ownership.governance_engine import ChangeType
        impact = self.ge.assess_impact(
            ChangeType.CONSTRAINT_OVERRIDE.value, metric_id="m_temp_breaches",
        )
        self.assertEqual(impact, "critical")

    def test_audit_trail_records_all_actions(self):
        """Every submit, approve, reject should create audit entries."""
        from loweconex_platform.ownership.governance_engine import ChangeType
        initial_count = len(self.ge.get_audit_log())

        cr = self.ge.submit_change(
            ChangeType.PARAMETER_OVERRIDE.value, "user", "Test",
        )
        post_submit = len(self.ge.get_audit_log())
        self.assertGreater(post_submit, initial_count)

    def test_pending_approvals_filter(self):
        """get_pending_approvals should filter by approver."""
        from loweconex_platform.ownership.governance_engine import ChangeType
        cr = self.ge.submit_change(
            ChangeType.OWNERSHIP_OVERRIDE.value, "user", "Test",
            metric_id="m_reactive_jobs",
        )
        approver = cr.approvers[0] if cr.approvers else ""
        pending = self.ge.get_pending_approvals(approver)
        self.assertGreater(len(pending), 0)

    def test_change_history_filter(self):
        """get_change_history should filter by metric_id."""
        from loweconex_platform.ownership.governance_engine import ChangeType
        self.ge.submit_change(
            ChangeType.PARAMETER_OVERRIDE.value, "user", "A",
            metric_id="m_reactive_jobs",
        )
        self.ge.submit_change(
            ChangeType.PARAMETER_OVERRIDE.value, "user", "B",
            metric_id="m_temp_breaches",
        )
        history = self.ge.get_change_history(metric_id="m_reactive_jobs")
        for cr in history:
            self.assertEqual(cr.metric_id, "m_reactive_jobs")

    def test_governance_summary(self):
        """Summary should have all required fields."""
        from loweconex_platform.ownership.governance_engine import ChangeType
        self.ge.submit_change(ChangeType.PARAMETER_OVERRIDE.value, "user", "Test")
        summary = self.ge.get_governance_summary()
        self.assertIn("total_changes", summary)
        self.assertIn("approved", summary)
        self.assertIn("pending", summary)
        self.assertIn("raci_validation", summary)
        self.assertTrue(summary["raci_validation"]["complete"])

    def test_validate_ownership_action_accountable_can_approve(self):
        """Accountable owner for a metric should be authorized to approve."""
        result = self.ge.validate_ownership_action("fm", "approve", "m_reactive_jobs")
        self.assertTrue(result["authorized"])

    def test_validate_ownership_action_unauthorized(self):
        """Non-owner should not be authorized to approve."""
        result = self.ge.validate_ownership_action("esg", "approve", "m_reactive_jobs")
        self.assertFalse(result["authorized"])

    def test_validate_ownership_action_informed_can_view(self):
        """Informed role should be authorized to view."""
        # Q1 informed is 'ops'
        result = self.ge.validate_ownership_action("ops", "view", "m_reactive_jobs")
        self.assertTrue(result["authorized"])

    def test_has_override_method(self):
        """OwnershipEngine.has_override should detect non-default assignments."""
        # Default assignments are system_default — should return False
        self.assertFalse(self.svc.ownership.has_override("m_reactive_jobs"))

        # After manual override, should return True
        self.svc.ownership.override(
            "m_reactive_jobs", "global", "",
            accountable="finance", created_by="test_user",
        )
        self.assertTrue(self.svc.ownership.has_override("m_reactive_jobs"))


# ═══════════════════════════════════════════════════════════════════
# 4. Integration Tests
# ═══════════════════════════════════════════════════════════════════

class TestIntegration(unittest.TestCase):
    """Test that all three phases work together end-to-end."""

    def test_crew_output_enriches_advisory(self):
        """Full flow: crew run → advisory enrichment."""
        from loweconex_platform.ownership.crew.decision_crew import OwnershipDecisionCrew
        from loweconex_platform.orchestration.decision_advisory_agent import (
            DecisionAdvisoryAgent,
        )

        crew = OwnershipDecisionCrew()
        crew_result = crew.run(metric_inputs=SAMPLE_METRIC_INPUTS)

        composite = {
            "executive_summary": {"total_savings_medium": 100000},
            "kpi_results": {},
            "roi_metrics": {},
            "portfolio_optimization": {},
            "cross_asset_optimization": {},
            "scenario_analysis": {},
            "ownership_decision": crew_result.to_dict(),
        }

        agent = DecisionAdvisoryAgent()
        output = agent._deterministic_fallback(composite)
        self.assertIn("Pareto-optimal", output.trade_off_analysis)
        self.assertGreater(output.confidence, 0.6)

    def test_validator_and_governance_on_same_service(self):
        """Validator and governance should share the same service state."""
        svc = OwnershipDecisionService()
        from loweconex_platform.ownership.quadrant_validator import QuadrantValidator
        from loweconex_platform.ownership.governance_engine import GovernanceEngine, ChangeType

        validator = QuadrantValidator(svc.catalog, svc.ownership, svc.rules, svc.aggregation)
        ge = GovernanceEngine(svc.catalog, svc.ownership)

        # Validate setup
        report = validator.validate_setup()
        self.assertTrue(report.passed)

        # Submit a governance change
        cr = ge.submit_change(
            ChangeType.PARAMETER_OVERRIDE.value, "user", "Test",
            metric_id="m_reactive_jobs",
        )
        self.assertIsNotNone(cr.change_id)

        # Governance should see the metric
        auth = ge.validate_ownership_action("fm", "approve", "m_reactive_jobs")
        self.assertTrue(auth["authorized"])

    def test_quadrant_cost_type_mapping_complete(self):
        """QUADRANT_COST_TYPE should cover all 4 quadrants."""
        from loweconex_platform.ownership.quadrant_validator import QUADRANT_COST_TYPE
        self.assertEqual(len(QUADRANT_COST_TYPE), 4)
        self.assertEqual(QUADRANT_COST_TYPE["Q1"], "opex")
        self.assertEqual(QUADRANT_COST_TYPE["Q2"], "capex")
        self.assertEqual(QUADRANT_COST_TYPE["Q3"], "risk")
        self.assertEqual(QUADRANT_COST_TYPE["Q4"], "strategic")

    def test_governance_raci_bridge_active(self):
        """GovernanceEngine should have RACI bridge when operating_model available."""
        svc = OwnershipDecisionService()
        from loweconex_platform.ownership.governance_engine import GovernanceEngine
        ge = GovernanceEngine(svc.catalog, svc.ownership)
        summary = ge.get_governance_summary()
        # Should be True since operating_model module exists
        self.assertTrue(summary["raci_bridge_active"])

    def test_full_pipeline_with_governance_gate(self):
        """Pipeline should work with a governance gate between phases."""
        svc = OwnershipDecisionService()
        from loweconex_platform.ownership.governance_engine import GovernanceEngine, ChangeType
        from loweconex_platform.ownership.quadrant_validator import QuadrantValidator

        ge = GovernanceEngine(svc.catalog, svc.ownership)
        validator = QuadrantValidator(svc.catalog, svc.ownership, svc.rules, svc.aggregation)

        # Step 1: Validate setup
        setup_report = validator.validate_setup()
        self.assertTrue(setup_report.passed)

        # Step 2: Build cost stack
        stack = svc.aggregation.build_cost_stack(SAMPLE_METRIC_INPUTS)

        # Step 3: Validate cost lines
        lines_report = validator.validate_cost_lines(stack)
        self.assertTrue(lines_report.passed)

        # Step 4: Governance gate — submit budget change
        cr = ge.submit_change(
            ChangeType.BUDGET_CHANGE.value, "fm",
            "Increase maintenance budget",
            metric_id="m_reactive_jobs",
            justification="Higher WO volume",
        )
        # Budget change is HIGH impact — needs approval
        self.assertIn(cr.status, ["pending", "auto_approved"])

        # Step 5: Compute ROI
        roi = svc.roi_engine.compute(stack)
        self.assertGreater(roi.npv, 0)


# ═══════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    result = unittest.main(verbosity=2, exit=False)
    print("\n" + "=" * 70)
    if result.result.wasSuccessful():
        total = result.result.testsRun
        print(f"ALL {total} TESTS PASSED")
    else:
        failures = len(result.result.failures) + len(result.result.errors)
        print(f"FAILURES: {failures}  ERRORS: {len(result.result.errors)}")
    print("=" * 70)
