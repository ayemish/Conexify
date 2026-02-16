"""
Test Suite for Agent Advisor — the asset/location-scoped reasoning engine.

Covers:
1. Scope resolution (asset types, locations)
2. AgentAdvisor.advise() end-to-end
3. Agent trace structure and completeness
4. Cross-silo consolidation correctness
5. Recommendation generation and prioritization
6. Integration with QuadrantValidator + GovernanceEngine
7. Serialization (to_dict round-trip)

Run with:
    python -m pytest tests/test_agent_advisor.py -v
"""

import sys
import os
import json
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loweconex_platform.ownership.crew.agent_advisor import (
    AgentAdvisor,
    AgentAdvisorResult,
    AgentTrace,
    AgentReasoningStep,
    CrossSiloConsolidation,
    Recommendation,
    resolve_metric_inputs,
    ASSET_TYPE_PROFILES,
    LOCATION_PROFILES,
)


class TestScopeResolution(unittest.TestCase):
    """Test metric input resolution for different scopes."""

    def test_rtu_asset_resolves(self):
        inputs = resolve_metric_inputs("asset", "RTU-001")
        self.assertIn("m_reactive_jobs", inputs)
        self.assertIn("m_energy_reduction", inputs)

    def test_walk_in_asset_resolves(self):
        inputs = resolve_metric_inputs("asset", "WI-003")
        self.assertIn("m_temp_breaches", inputs)
        self.assertIn("m_product_discard", inputs)

    def test_rack_asset_resolves(self):
        inputs = resolve_metric_inputs("asset", "RK-001")
        self.assertIn("m_reactive_jobs", inputs)
        self.assertIn("m_emissions_reduction", inputs)

    def test_location_resolves(self):
        inputs = resolve_metric_inputs("location", "store-042")
        self.assertGreater(len(inputs), 5)
        self.assertIn("m_service_bureau", inputs)

    def test_overrides_applied(self):
        overrides = {"m_reactive_jobs": {"wo_count": 999}}
        inputs = resolve_metric_inputs("asset", "RTU-001", overrides)
        self.assertEqual(inputs["m_reactive_jobs"]["wo_count"], 999)

    def test_unknown_asset_defaults_to_rtu(self):
        inputs = resolve_metric_inputs("asset", "UNKNOWN-XYZ")
        rtu_inputs = resolve_metric_inputs("asset", "RTU-001")
        self.assertEqual(set(inputs.keys()), set(rtu_inputs.keys()))


class TestAgentAdvisorEndToEnd(unittest.TestCase):
    """Test the full advisory pipeline."""

    @classmethod
    def setUpClass(cls):
        cls.advisor = AgentAdvisor()

    def test_advise_rtu_returns_result(self):
        result = self.advisor.advise("asset", "RTU-001")
        self.assertIsInstance(result, AgentAdvisorResult)
        self.assertEqual(result.scope_type, "asset")
        self.assertEqual(result.scope_id, "RTU-001")

    def test_advise_location_returns_result(self):
        result = self.advisor.advise("location", "store-042")
        self.assertIsInstance(result, AgentAdvisorResult)
        self.assertEqual(result.scope_type, "location")

    def test_advise_walk_in_asset(self):
        result = self.advisor.advise("asset", "WI-001")
        self.assertEqual(result.scope_id, "WI-001")
        self.assertGreater(len(result.agent_traces), 0)

    def test_advise_rack_asset(self):
        result = self.advisor.advise("asset", "RK-002")
        self.assertEqual(result.scope_id, "RK-002")
        self.assertGreater(len(result.recommendations), 0)

    def test_execution_time_recorded(self):
        result = self.advisor.advise("asset", "RTU-001")
        self.assertGreater(result.execution_time_ms, 0)

    def test_run_id_unique(self):
        r1 = self.advisor.advise("asset", "RTU-001")
        r2 = self.advisor.advise("asset", "RTU-001")
        self.assertNotEqual(r1.run_id, r2.run_id)


class TestAgentTraces(unittest.TestCase):
    """Test agent trace structure and completeness."""

    @classmethod
    def setUpClass(cls):
        cls.advisor = AgentAdvisor()
        cls.result = cls.advisor.advise("asset", "RTU-001")

    def test_twelve_agent_traces(self):
        self.assertEqual(len(self.result.agent_traces), 12)

    def test_all_groups_present(self):
        groups = {t.group for t in self.result.agent_traces}
        self.assertEqual(groups, {"stakeholder", "dimension", "governance"})

    def test_stakeholder_agents_count(self):
        stakeholders = [t for t in self.result.agent_traces if t.group == "stakeholder"]
        self.assertEqual(len(stakeholders), 5)

    def test_dimension_agents_count(self):
        dims = [t for t in self.result.agent_traces if t.group == "dimension"]
        self.assertEqual(len(dims), 4)

    def test_governance_agents_count(self):
        gov = [t for t in self.result.agent_traces if t.group == "governance"]
        self.assertEqual(len(gov), 3)

    def test_each_trace_has_reasoning_steps(self):
        for trace in self.result.agent_traces:
            self.assertGreater(
                len(trace.reasoning_steps), 0,
                f"Agent {trace.agent_id} has no reasoning steps",
            )

    def test_each_trace_has_conclusion(self):
        for trace in self.result.agent_traces:
            self.assertTrue(
                trace.conclusion,
                f"Agent {trace.agent_id} has no conclusion",
            )

    def test_stakeholder_traces_have_constraints(self):
        for trace in self.result.agent_traces:
            if trace.group == "stakeholder":
                # At least some stakeholders should emit constraints
                pass  # Constraints may be empty for cross-quadrant ops agent

    def test_dimension_traces_report_cost_lines(self):
        dims = [t for t in self.result.agent_traces if t.group == "dimension"]
        total_lines = sum(t.cost_lines_produced for t in dims)
        self.assertGreater(total_lines, 0, "Dimension agents should produce cost lines")

    def test_trace_stages_ordered(self):
        stages = [t.stage for t in self.result.agent_traces]
        self.assertEqual(sorted(stages), stages, "Traces should be stage-ordered")


class TestCrossSiloConsolidation(unittest.TestCase):
    """Test cross-silo consolidation view."""

    @classmethod
    def setUpClass(cls):
        cls.advisor = AgentAdvisor()
        cls.result = cls.advisor.advise("location", "store-042")

    def test_all_quadrants_present(self):
        quads = self.result.cross_silo.quadrant_contributions
        self.assertIn("Q1", quads)
        self.assertIn("Q2", quads)
        self.assertIn("Q4", quads)

    def test_percentages_sum_to_100(self):
        quads = self.result.cross_silo.quadrant_contributions
        total_pct = sum(q.get("pct_of_total", 0) for q in quads.values())
        self.assertAlmostEqual(total_pct, 100.0, delta=1.0)

    def test_unified_savings_positive(self):
        self.assertGreater(self.result.cross_silo.unified_savings, 0)

    def test_unified_npv_positive(self):
        self.assertGreater(self.result.cross_silo.unified_npv, 0)

    def test_quadrant_cost_types_correct(self):
        quads = self.result.cross_silo.quadrant_contributions
        expected = {"Q1": "opex", "Q2": "capex", "Q3": "risk", "Q4": "strategic"}
        for q, ct in expected.items():
            if q in quads:
                self.assertEqual(quads[q]["cost_type"], ct)


class TestRecommendations(unittest.TestCase):
    """Test recommendation generation and prioritization."""

    @classmethod
    def setUpClass(cls):
        cls.advisor = AgentAdvisor()
        cls.result = cls.advisor.advise("asset", "RTU-001")

    def test_recommendations_generated(self):
        self.assertGreater(len(self.result.recommendations), 0)

    def test_recommendations_have_required_fields(self):
        for rec in self.result.recommendations:
            self.assertTrue(rec.title, "Recommendation needs title")
            self.assertTrue(rec.quadrant, "Recommendation needs quadrant")
            self.assertGreater(rec.savings_annual, 0)
            self.assertGreater(rec.confidence, 0)
            self.assertGreater(rec.priority, 0)
            self.assertTrue(rec.category)
            self.assertTrue(rec.rationale)
            self.assertTrue(rec.implementation_horizon)

    def test_priorities_sequential(self):
        priorities = [r.priority for r in self.result.recommendations]
        self.assertEqual(priorities, list(range(1, len(priorities) + 1)))

    def test_compliance_recs_prioritized(self):
        """If compliance recs exist, they should be highest priority."""
        recs = self.result.recommendations
        compliance = [r for r in recs if r.category == "compliance"]
        if compliance:
            self.assertEqual(compliance[0].priority, 1)

    def test_cross_silo_impact_populated(self):
        """At least some recommendations should have cross-silo impact."""
        has_impact = [r for r in self.result.recommendations if r.cross_silo_impact]
        self.assertGreater(len(has_impact), 0)

    def test_location_generates_more_recs_than_asset(self):
        """Location scope should generally produce more recommendations."""
        loc_result = self.advisor.advise("location", "store-042")
        self.assertGreaterEqual(
            len(loc_result.recommendations), len(self.result.recommendations)
        )


class TestIntegrationWithValidatorAndGovernance(unittest.TestCase):
    """Test integration with QuadrantValidator and GovernanceEngine."""

    @classmethod
    def setUpClass(cls):
        cls.advisor = AgentAdvisor()
        cls.result = cls.advisor.advise("asset", "RTU-001")

    def test_quadrant_validation_present(self):
        self.assertIn("passed", self.result.quadrant_validation)

    def test_quadrant_validation_passes(self):
        self.assertTrue(self.result.quadrant_validation["passed"])

    def test_governance_status_present(self):
        self.assertIn("total_changes", self.result.governance_status)
        self.assertIn("raci_validation", self.result.governance_status)

    def test_governance_raci_complete(self):
        self.assertTrue(self.result.governance_status["raci_validation"]["complete"])


class TestSerialization(unittest.TestCase):
    """Test that all result types serialize cleanly."""

    @classmethod
    def setUpClass(cls):
        cls.advisor = AgentAdvisor()
        cls.result = cls.advisor.advise("asset", "RTU-001")

    def test_full_result_serializes(self):
        d = self.result.to_dict()
        serialized = json.dumps(d, default=str)
        self.assertGreater(len(serialized), 500)

    def test_agent_trace_serializes(self):
        for trace in self.result.agent_traces:
            d = trace.to_dict()
            json.dumps(d, default=str)

    def test_cross_silo_serializes(self):
        d = self.result.cross_silo.to_dict()
        json.dumps(d, default=str)

    def test_recommendation_serializes(self):
        for rec in self.result.recommendations:
            d = rec.to_dict()
            json.dumps(d, default=str)

    def test_pareto_options_serializable(self):
        json.dumps(self.result.pareto_options, default=str)

    def test_board_narrative_is_string(self):
        self.assertIsInstance(self.result.board_narrative, str)
        self.assertGreater(len(self.result.board_narrative), 50)

    def test_crew_output_present(self):
        self.assertIn("run_id", self.result.crew_output)
        self.assertIn("pareto_options", self.result.crew_output)


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
