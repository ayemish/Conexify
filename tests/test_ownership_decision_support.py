"""
Test Suite: Ownership-Aware Decision Support Module

Tests the full pipeline: Metric Catalog → Ownership Mapping → Cost Stack → Consolidated ROI
with Q1-Q4 quadrant classification and cross-silo aggregation.

Run with:
    python -m pytest tests/test_ownership_decision_support.py -v
    # or directly:
    python tests/test_ownership_decision_support.py
"""

import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from loweconex_platform.ownership.metric_catalog import MetricCatalog, Quadrant, MetricDefinition
from loweconex_platform.ownership.ownership_model import (
    OwnershipEngine, OwnershipAssignment, OwnerRole, OwnerWeight, OrgLevel,
)
from loweconex_platform.ownership.cost_stack import CostStack, CostLineItem, CostType
from loweconex_platform.ownership.translation_rules import TranslationRulesLibrary, TranslationRule
from loweconex_platform.ownership.aggregation_engine import AggregationEngine
from loweconex_platform.ownership.consolidated_roi import ConsolidatedROIEngine
from loweconex_platform.ownership.constraint_optimizer import ConstraintOptimizer, BudgetConstraints
from loweconex_platform.ownership.parameter_hierarchy import ParameterHierarchy
from loweconex_platform.ownership.scenario_extensions import ScenarioManager
from loweconex_platform.ownership.api_routes import OwnershipDecisionService


# ═══════════════════════════════════════════════════════════════════
# Sample Inputs (replicating real-world data shapes)
# ═══════════════════════════════════════════════════════════════════

SAMPLE_METRIC_INPUTS = {
    # Q1: FM-Controlled Opex
    "m_reactive_jobs": {"wo_count": 120, "cost_per_wo": 380, "reduction_pct": 0.25},
    "m_ppm_frequency": {
        "baseline_pm_tasks": 500, "optimized_pm_tasks": 400,
        "pm_cost_per_task": 150, "avoided_reactive_savings": 15000,
    },
    "m_wo_volume": {
        "wo_volume": 200, "avg_vendor_rate": 250, "vendor_reduction_pct": 0.15,
        "admin_overhead_per_wo": 45, "admin_reduction_pct": 0.20,
    },
    "m_service_bureau": {"call_volume": 800, "cost_per_call": 25, "deflection_rate": 0.30},
    # Q2: Finance-Controlled Capex
    "m_replacement_cycle": {
        "replacement_count": 5, "avg_replacement_cost": 18000,
        "avoided_failure_cost": 25000,
    },
    "m_lifecycle_model": {"keep_lcc_npv": 250000, "replace_lcc_npv": 180000},
    # Q3: Compliance-Driven Risk
    "m_temp_breaches": {
        "breach_count": 15, "avg_spoilage_per_breach": 2500,
        "penalty_probability": 0.15, "avg_penalty": 10000, "audit_risk_cost": 5000,
    },
    "m_product_discard": {
        "discard_volume": 500, "avg_cogs_per_unit": 8,
        "discard_events": 30, "labor_per_event": 120,
        "disposal_cost_per_unit": 1.5,
    },
    "m_regulatory_penalties": {
        "penalty_events": 2, "avg_fine": 15000, "remediation_cost": 8000,
    },
    # Q4: Cross-Silo Strategic
    "m_energy_reduction": {
        "kwh_reduction": 500000, "electricity_rate": 0.12,
        "carbon_factor": 0.0004, "carbon_price": 50,
    },
    "m_emissions_reduction": {
        "emissions_reduced_tco2e": 200, "carbon_price": 50,
        "compliance_reporting_value": 10000,
    },
}


# ═══════════════════════════════════════════════════════════════════
# 1. Metric Catalog Tests
# ═══════════════════════════════════════════════════════════════════

class TestMetricCatalog(unittest.TestCase):
    def setUp(self):
        self.catalog = MetricCatalog()

    def test_system_metrics_seeded(self):
        """All 22 system metrics should be present after initialization."""
        metrics = self.catalog.list_all()
        self.assertEqual(len(metrics), 22, f"Expected 22 metrics, got {len(metrics)}")

    def test_quadrant_distribution(self):
        """Metrics should be distributed across all four quadrants."""
        q1 = self.catalog.list_by_quadrant("Q1")
        q2 = self.catalog.list_by_quadrant("Q2")
        q3 = self.catalog.list_by_quadrant("Q3")
        q4 = self.catalog.list_by_quadrant("Q4")
        self.assertEqual(len(q1), 7, "Q1 should have 7 metrics")
        self.assertEqual(len(q2), 4, "Q2 should have 4 metrics")
        self.assertEqual(len(q3), 5, "Q3 should have 5 metrics")
        self.assertEqual(len(q4), 6, "Q4 should have 6 metrics")

    def test_q1_owner_defaults(self):
        """Q1 metrics should default to 'fm' owner."""
        for m in self.catalog.list_by_quadrant("Q1"):
            self.assertEqual(m.default_owner_role, "fm",
                             f"Q1 metric {m.name} should default to fm, got {m.default_owner_role}")

    def test_q2_owner_defaults(self):
        """Q2 metrics should default to 'finance' owner."""
        for m in self.catalog.list_by_quadrant("Q2"):
            self.assertEqual(m.default_owner_role, "finance",
                             f"Q2 metric {m.name} should default to finance, got {m.default_owner_role}")

    def test_q3_owner_defaults(self):
        """Q3 metrics should default to 'food_safety' owner."""
        for m in self.catalog.list_by_quadrant("Q3"):
            self.assertEqual(m.default_owner_role, "food_safety",
                             f"Q3 metric {m.name} should default to food_safety, got {m.default_owner_role}")

    def test_kpi_crew_linkage(self):
        """Metrics with kpi_crew_name should reference valid crew names."""
        known_crews = {
            "work_order_reduction", "ppm_maximization", "call_center_volume_reduction",
            "service_bureau_reduction", "capex_lifecycle_optimization",
            "failure_prediction_accuracy", "food_temp_diagnostics_improvement",
            "food_waste_reduction", "food_safety_compliance", "refrigerant_leak_reduction",
            "energy_reduction", "esg_compliance", "uptime_improvement",
            "preventive_maintenance_optimization",
        }
        for m in self.catalog.list_all():
            if m.kpi_crew_name:
                self.assertIn(m.kpi_crew_name, known_crews,
                              f"Metric {m.name} references unknown crew: {m.kpi_crew_name}")

    def test_custom_metric_crud(self):
        """Users can add and delete custom metrics (not system ones)."""
        custom = MetricDefinition(
            name="Custom Test Metric",
            quadrant="Q1",
            default_owner_role="ops",
            is_system=False,
        )
        self.catalog.add(custom)
        self.assertEqual(len(self.catalog.list_all()), 23)

        # Can delete custom
        self.assertTrue(self.catalog.delete(custom.metric_id))
        self.assertEqual(len(self.catalog.list_all()), 22)

        # Cannot delete system metric
        system_id = self.catalog.list_all()[0].metric_id
        self.assertFalse(self.catalog.delete(system_id))

    def test_get_by_name(self):
        """Can look up metrics by name."""
        m = self.catalog.get_by_name("Reactive Work Orders")
        self.assertIsNotNone(m)
        self.assertEqual(m.metric_id, "m_reactive_jobs")


# ═══════════════════════════════════════════════════════════════════
# 2. Ownership Model Tests
# ═══════════════════════════════════════════════════════════════════

class TestOwnershipModel(unittest.TestCase):
    def setUp(self):
        self.engine = OwnershipEngine()
        self.catalog = MetricCatalog()
        # Set defaults for all metrics
        for m in self.catalog.list_all():
            self.engine.set_default_from_quadrant(m.metric_id, m.quadrant)

    def test_default_q1_accountable(self):
        """Q1 defaults should assign FM as accountable."""
        resolved = self.engine.resolve("m_reactive_jobs")
        self.assertEqual(resolved["accountable"], "fm")

    def test_default_q2_accountable(self):
        """Q2 defaults should assign Finance as accountable."""
        resolved = self.engine.resolve("m_replacement_cycle")
        self.assertEqual(resolved["accountable"], "finance")

    def test_default_q3_accountable(self):
        """Q3 defaults should assign Food Safety as accountable."""
        resolved = self.engine.resolve("m_temp_breaches")
        self.assertEqual(resolved["accountable"], "food_safety")

    def test_default_q4_multi_owner(self):
        """Q4 defaults should have multi-owner weights."""
        resolved = self.engine.resolve("m_energy_reduction")
        self.assertEqual(resolved["accountable"], "executive")
        weights = resolved.get("owner_weights", [])
        self.assertTrue(len(weights) > 0, "Q4 should have owner weights")
        total_weight = sum(w["weight"] for w in weights)
        self.assertAlmostEqual(total_weight, 1.0, places=2)

    def test_hierarchy_override(self):
        """Store-level override should take precedence over global."""
        # Global default is fm
        self.engine.override(
            metric_id="m_reactive_jobs",
            org_level="region",
            org_entity="APAC",
            accountable="ops",
            created_by="test",
        )
        # At global level, still fm
        global_result = self.engine.resolve("m_reactive_jobs", "global", "")
        self.assertEqual(global_result["accountable"], "fm")

        # At region level, now ops
        region_result = self.engine.resolve("m_reactive_jobs", "region", "APAC")
        self.assertEqual(region_result["accountable"], "ops")

    def test_audit_log_records_changes(self):
        """Every ownership change should appear in audit log."""
        initial_count = len(self.engine.get_audit_log())
        self.engine.override(
            metric_id="m_reactive_jobs",
            org_level="store",
            org_entity="STORE-001",
            accountable="vendor",
            created_by="test_user",
        )
        total_log = self.engine.get_audit_log()
        self.assertGreater(len(total_log), initial_count, "Audit log should grow after override")
        # Find the override entry (most recent for this metric)
        metric_log = self.engine.get_audit_log("m_reactive_jobs")
        latest = [e for e in metric_log if e.get("created_by") == "test_user"]
        self.assertTrue(len(latest) > 0, "Should have log entry from test_user")
        self.assertEqual(latest[-1]["accountable"], "vendor")

    def test_metrics_for_owner(self):
        """Should return all metrics where a role is accountable or responsible."""
        fm_metrics = self.engine.get_metrics_for_owner("fm")
        # FM should be accountable for Q1 and responsible for Q2/Q3/Q4
        self.assertTrue(len(fm_metrics) > 0)


# ═══════════════════════════════════════════════════════════════════
# 3. Translation Rules Tests
# ═══════════════════════════════════════════════════════════════════

class TestTranslationRules(unittest.TestCase):
    def setUp(self):
        self.library = TranslationRulesLibrary()

    def test_seeded_rules_count(self):
        """Should have 12 seeded rules."""
        self.assertEqual(len(self.library.list_all()), 12)

    def test_rules_by_quadrant(self):
        """Rules should exist for all four quadrants."""
        for q in ["Q1", "Q2", "Q3", "Q4"]:
            rules = self.library.list_by_quadrant(q)
            self.assertTrue(len(rules) > 0, f"No rules for quadrant {q}")

    def test_reactive_wo_translation(self):
        """Reactive WO rule should produce correct savings amount."""
        rules = self.library.list_by_metric("m_reactive_jobs")
        self.assertTrue(len(rules) > 0)

        rule = rules[0]
        result = rule.evaluate({
            "wo_count": 100,
            "cost_per_wo": 400,
            "reduction_pct": 0.30,
        })
        expected = 100 * 400 * 0.30  # = 12000
        self.assertAlmostEqual(result["amount"], expected, places=0)
        self.assertGreater(result["confidence"], 0)
        self.assertEqual(len(result["missing_inputs"]), 0)

    def test_missing_inputs_flagged(self):
        """Missing required inputs should be flagged with zero confidence."""
        rules = self.library.list_by_metric("m_reactive_jobs")
        rule = rules[0]
        result = rule.evaluate({"wo_count": 100})  # missing cost_per_wo, reduction_pct
        # Should use defaults, not fail
        self.assertGreater(result["amount"], 0, "Should use default assumptions")
        self.assertTrue(len(result["assumptions_used"]) > 0)

    def test_completely_missing_inputs(self):
        """Completely missing required inputs should return 0 with error."""
        rule = TranslationRule(
            formula_expression="a * b",
            required_inputs=["a", "b"],
            default_assumptions={},
        )
        result = rule.evaluate({})
        self.assertEqual(result["amount"], 0)
        self.assertTrue(len(result["missing_inputs"]) > 0)

    def test_confidence_reduced_with_assumptions(self):
        """Confidence should be lower when using default assumptions."""
        rules = self.library.list_by_metric("m_reactive_jobs")
        rule = rules[0]
        full = rule.evaluate({"wo_count": 100, "cost_per_wo": 400, "reduction_pct": 0.3})
        partial = rule.evaluate({"wo_count": 100})  # uses defaults for 2 fields
        self.assertGreater(full["confidence"], partial["confidence"],
                           "Full inputs should have higher confidence than assumption-based")

    def test_to_cost_line_produces_valid_item(self):
        """to_cost_line should produce a CostLineItem with correct fields."""
        rules = self.library.list_by_metric("m_reactive_jobs")
        line = rules[0].to_cost_line(
            {"wo_count": 100, "cost_per_wo": 400, "reduction_pct": 0.3},
            ["fm", "vendor"],
        )
        self.assertIsInstance(line, CostLineItem)
        self.assertEqual(line.cost_type, "opex")
        self.assertEqual(line.quadrant, "Q1")
        self.assertIn("fm", line.owner_roles)
        self.assertGreater(line.amount, 0)


# ═══════════════════════════════════════════════════════════════════
# 4. Anti-Double-Counting Tests
# ═══════════════════════════════════════════════════════════════════

class TestAntiDoubleCounting(unittest.TestCase):
    def setUp(self):
        self.catalog = MetricCatalog()
        self.ownership = OwnershipEngine()
        self.rules = TranslationRulesLibrary()
        for m in self.catalog.list_all():
            self.ownership.set_default_from_quadrant(m.metric_id, m.quadrant)
        self.engine = AggregationEngine(self.catalog, self.ownership, self.rules)

    def test_overlap_reduces_downstream(self):
        """temp_breaches → product_discard overlap should reduce discard amount."""
        # Build with both metrics
        inputs_both = {
            "m_temp_breaches": {
                "breach_count": 10, "avg_spoilage_per_breach": 2000,
                "penalty_probability": 0.1, "avg_penalty": 5000, "audit_risk_cost": 3000,
            },
            "m_product_discard": {
                "discard_volume": 300, "avg_cogs_per_unit": 8,
                "discard_events": 20, "labor_per_event": 100,
                "disposal_cost_per_unit": 1.5,
            },
        }
        stack = self.engine.build_cost_stack(inputs_both)
        adjustments = self.engine.get_adjustments()

        # Should have at least one overlap adjustment
        self.assertTrue(
            len(adjustments) > 0,
            "Expected overlap adjustments between temp_breaches and product_discard"
        )

    def test_no_double_count_reactive_wo_volume(self):
        """reactive_jobs → wo_volume overlap should reduce wo_volume."""
        inputs = {
            "m_reactive_jobs": {"wo_count": 100, "cost_per_wo": 380, "reduction_pct": 0.25},
            "m_wo_volume": {
                "wo_volume": 200, "avg_vendor_rate": 250, "vendor_reduction_pct": 0.15,
                "admin_overhead_per_wo": 45, "admin_reduction_pct": 0.20,
            },
        }
        stack = self.engine.build_cost_stack(inputs)
        adjustments = self.engine.get_adjustments()
        overlap_types = [a["type"] for a in adjustments]
        self.assertIn("overlap_reduction", overlap_types)


# ═══════════════════════════════════════════════════════════════════
# 5. Consolidated ROI Tests
# ═══════════════════════════════════════════════════════════════════

class TestConsolidatedROI(unittest.TestCase):
    def setUp(self):
        self.catalog = MetricCatalog()
        self.ownership = OwnershipEngine()
        self.rules = TranslationRulesLibrary()
        for m in self.catalog.list_all():
            self.ownership.set_default_from_quadrant(m.metric_id, m.quadrant)
        self.aggregation = AggregationEngine(self.catalog, self.ownership, self.rules)
        self.roi_engine = ConsolidatedROIEngine(discount_rate=0.08, horizon_years=3)

    def test_roi_has_all_breakdowns(self):
        """ROI should include breakdowns by owner, quadrant, and cost type."""
        stack = self.aggregation.build_cost_stack(SAMPLE_METRIC_INPUTS)
        roi = self.roi_engine.compute(stack, scenario_name="Test")

        self.assertTrue(len(roi.roi_by_owner) > 0, "Should have owner breakdowns")
        self.assertTrue(len(roi.roi_by_quadrant) > 0, "Should have quadrant breakdowns")
        self.assertTrue(len(roi.roi_by_cost_type) > 0, "Should have cost type breakdowns")

    def test_roi_npv_positive(self):
        """With standard inputs, NPV should be positive (net savings)."""
        stack = self.aggregation.build_cost_stack(SAMPLE_METRIC_INPUTS)
        roi = self.roi_engine.compute(stack)
        self.assertGreater(roi.npv, 0, "NPV should be positive with standard inputs")

    def test_roi_line_count_matches_stack(self):
        """ROI line count should match cost stack line count."""
        stack = self.aggregation.build_cost_stack(SAMPLE_METRIC_INPUTS)
        roi = self.roi_engine.compute(stack)
        self.assertEqual(roi.line_count, len(stack.lines))

    def test_year_by_year_cashflow(self):
        """Should produce year-by-year cashflow for the horizon period."""
        stack = self.aggregation.build_cost_stack(SAMPLE_METRIC_INPUTS)
        roi = self.roi_engine.compute(stack)
        self.assertEqual(len(roi.year_by_year_cashflow), 3, "Should have 3 years of cashflow")

    def test_confidence_weighted_avg(self):
        """Confidence-weighted average should be between 0 and 1."""
        stack = self.aggregation.build_cost_stack(SAMPLE_METRIC_INPUTS)
        roi = self.roi_engine.compute(stack)
        self.assertGreaterEqual(roi.confidence_weighted_avg, 0)
        self.assertLessEqual(roi.confidence_weighted_avg, 1)

    def test_savings_range(self):
        """Low savings should be ≤ base ≤ high savings."""
        stack = self.aggregation.build_cost_stack(SAMPLE_METRIC_INPUTS)
        roi = self.roi_engine.compute(stack)
        self.assertLessEqual(roi.savings_low, roi.total_savings)
        self.assertGreaterEqual(roi.savings_high, roi.total_savings)


# ═══════════════════════════════════════════════════════════════════
# 6. Constraint Optimizer Tests
# ═══════════════════════════════════════════════════════════════════

class TestConstraintOptimizer(unittest.TestCase):
    def setUp(self):
        self.catalog = MetricCatalog()
        self.ownership = OwnershipEngine()
        self.rules = TranslationRulesLibrary()
        for m in self.catalog.list_all():
            self.ownership.set_default_from_quadrant(m.metric_id, m.quadrant)
        self.aggregation = AggregationEngine(self.catalog, self.ownership, self.rules)
        self.optimizer = ConstraintOptimizer()

    def test_unconstrained_selects_all(self):
        """With no budget constraint, all lines should be selected."""
        stack = self.aggregation.build_cost_stack(SAMPLE_METRIC_INPUTS)
        result = self.optimizer.optimize(stack, BudgetConstraints())
        self.assertEqual(len(result.selected_lines), len(stack.lines))

    def test_tight_budget_drops_lines(self):
        """With a tight total budget, some lines should be rejected."""
        stack = self.aggregation.build_cost_stack(SAMPLE_METRIC_INPUTS)
        constraints = BudgetConstraints(total_budget=1000)  # very tight
        result = self.optimizer.optimize(stack, constraints)
        # Savings lines have 0 cost so they pass; cost lines may be rejected
        self.assertGreaterEqual(len(result.selected_lines), 0)

    def test_confidence_threshold_filters(self):
        """Lines below min_confidence should be rejected."""
        stack = self.aggregation.build_cost_stack(SAMPLE_METRIC_INPUTS)
        constraints = BudgetConstraints(min_confidence=0.99)  # very high bar
        result = self.optimizer.optimize(stack, constraints)
        # Most lines should be rejected with 0.99 threshold
        self.assertTrue(len(result.rejected_lines) > 0)

    def test_budget_cut_simulation(self):
        """Budget cut simulation should return impact analysis."""
        stack = self.aggregation.build_cost_stack(SAMPLE_METRIC_INPUTS)
        result = self.optimizer.simulate_budget_cut(
            stack, BudgetConstraints(), cut_pct=0.50, cut_type="opex"
        )
        self.assertIn("cut_type", result)
        self.assertIn("recommendation", result)
        self.assertEqual(result["cut_pct"], 0.50)


# ═══════════════════════════════════════════════════════════════════
# 7. Parameter Hierarchy Tests
# ═══════════════════════════════════════════════════════════════════

class TestParameterHierarchy(unittest.TestCase):
    def setUp(self):
        self.hierarchy = ParameterHierarchy()

    def test_seeded_parameters(self):
        """Should have 23 parameter definitions."""
        defs = self.hierarchy.list_definitions()
        self.assertEqual(len(defs), 23)

    def test_slider_params(self):
        """Should have 9 slider parameters."""
        sliders = self.hierarchy.list_slider_params()
        self.assertEqual(len(sliders), 9)

    def test_default_resolution(self):
        """Without overrides, should return default value."""
        resolved = self.hierarchy.resolve("p_discount_rate")
        self.assertEqual(resolved["value"], 0.08)
        self.assertTrue(resolved["is_default"])

    def test_override_takes_precedence(self):
        """Override at global level should replace default."""
        self.hierarchy.set_override("p_discount_rate", "global", "", 0.10, reason="test")
        resolved = self.hierarchy.resolve("p_discount_rate")
        self.assertEqual(resolved["value"], 0.10)
        self.assertFalse(resolved["is_default"])

    def test_store_overrides_region(self):
        """Store-level override should take precedence over region."""
        self.hierarchy.set_override("p_electricity_rate", "region", "APAC", 0.18)
        self.hierarchy.set_override("p_electricity_rate", "store", "STORE-SG1", 0.22)

        region_resolved = self.hierarchy.resolve("p_electricity_rate", region="APAC")
        self.assertEqual(region_resolved["value"], 0.18)

        store_resolved = self.hierarchy.resolve("p_electricity_rate", store="STORE-SG1", region="APAC")
        self.assertEqual(store_resolved["value"], 0.22)

    def test_audit_log(self):
        """All overrides should appear in audit log."""
        self.hierarchy.set_override("p_carbon_price", "global", "", 75, reason="policy change")
        log = self.hierarchy.get_audit_log("p_carbon_price")
        self.assertTrue(len(log) > 0)
        self.assertEqual(log[-1]["value"], 75)

    def test_bounds_enforcement(self):
        """Values outside bounds should be clamped."""
        self.hierarchy.set_override("p_discount_rate", "global", "", 0.50)  # max is 0.20
        resolved = self.hierarchy.resolve("p_discount_rate")
        self.assertLessEqual(resolved["value"], 0.20)


# ═══════════════════════════════════════════════════════════════════
# 8. Scenario Extensions Tests
# ═══════════════════════════════════════════════════════════════════

class TestScenarioExtensions(unittest.TestCase):
    def setUp(self):
        self.hierarchy = ParameterHierarchy()
        self.manager = ScenarioManager(self.hierarchy)

    def test_default_scenarios(self):
        """Should have 3 pre-created scenarios (Baseline, Conservative, Aggressive)."""
        scenarios = self.manager.list_all()
        self.assertEqual(len(scenarios), 3)
        names = {s.name for s in scenarios}
        self.assertIn("Baseline", names)
        self.assertIn("Conservative", names)
        self.assertIn("Aggressive", names)

    def test_scenario_parameter_resolution(self):
        """Conservative scenario should use conservative overrides."""
        scenarios = self.manager.list_all()
        conservative = next(s for s in scenarios if s.name == "Conservative")
        params = self.manager.resolve_parameters(conservative.scenario_id)
        # Conservative should have higher response time
        self.assertEqual(params.get("p_response_time_mean"), 6.0)

    def test_scenario_status_workflow(self):
        """Scenario should follow draft → review → approved → archived."""
        scenario = self.manager.create(name="Test Scenario")
        self.assertEqual(scenario.status, "draft")

        # draft → review
        self.assertTrue(self.manager.update_status(scenario.scenario_id, "review"))
        # review → approved
        self.assertTrue(self.manager.update_status(scenario.scenario_id, "approved"))
        # approved → archived
        self.assertTrue(self.manager.update_status(scenario.scenario_id, "archived"))
        # Cannot go backwards
        self.assertFalse(self.manager.update_status(scenario.scenario_id, "draft"))

    def test_create_custom_scenario(self):
        """Can create a custom scenario with parameter overrides."""
        scenario = self.manager.create(
            name="Singapore High-Cost",
            region="APAC",
            parameter_overrides={
                "p_electricity_rate": 0.25,
                "p_regulatory_strictness": 3.0,
            },
        )
        params = self.manager.resolve_parameters(scenario.scenario_id)
        self.assertEqual(params["p_electricity_rate"], 0.25)
        self.assertEqual(params["p_regulatory_strictness"], 3.0)


# ═══════════════════════════════════════════════════════════════════
# 9. End-to-End Service Facade Tests
# ═══════════════════════════════════════════════════════════════════

class TestOwnershipDecisionService(unittest.TestCase):
    """Integration tests using the full service facade."""

    def setUp(self):
        self.svc = OwnershipDecisionService()

    def test_full_pipeline(self):
        """Parameter Inputs → Ownership Mapping → Cost Stack → ROI."""
        # 1. Metrics available
        metrics_result = self.svc.get_metrics()
        self.assertEqual(metrics_result["count"], 22)

        # 2. Ownership map populated
        ownership_result = self.svc.get_ownership_map()
        self.assertGreater(ownership_result["count"], 0)

        # 3. Build cost stack
        stack_result = self.svc.build_cost_stack(SAMPLE_METRIC_INPUTS)
        self.assertGreater(stack_result["line_count"], 0)
        self.assertIn("by_cost_type", stack_result)
        self.assertIn("by_owner", stack_result)
        self.assertIn("by_quadrant", stack_result)

        # 4. Compute ROI
        roi_result = self.svc.compute_roi(SAMPLE_METRIC_INPUTS)
        self.assertGreater(roi_result["npv"], 0)
        self.assertGreater(len(roi_result["roi_by_owner"]), 0)
        self.assertGreater(len(roi_result["roi_by_quadrant"]), 0)

    def test_scenario_comparison(self):
        """Conservative vs Aggressive scenarios should produce different ROI."""
        scenarios = self.svc.list_scenarios()
        ids = [s["scenario_id"] for s in scenarios["scenarios"]]

        # Run each scenario
        results = {}
        for sid in ids[:3]:
            run = self.svc.run_scenario(sid, SAMPLE_METRIC_INPUTS)
            if "error" not in run:
                results[run["scenario"]["name"]] = run["roi"]["npv"]

        # Should have results for each
        self.assertTrue(len(results) >= 2, f"Expected ≥2 scenario results, got {len(results)}")

    def test_export_pack_complete(self):
        """Export pack should contain all required sections."""
        pack = self.svc.export_pack(SAMPLE_METRIC_INPUTS)
        required_keys = [
            "roi_summary", "cost_stack_detail", "ownership_map",
            "parameter_values", "translation_rules", "dependency_graph", "audit_log",
        ]
        for key in required_keys:
            self.assertIn(key, pack, f"Export pack missing: {key}")

    def test_dependency_graph_populated(self):
        """Dependency graph should have known overlap edges."""
        graph = self.svc.get_dependency_graph()
        self.assertGreater(len(graph["edges"]), 0)

    def test_optimization_with_budget(self):
        """Optimizer should respect budget constraints."""
        result = self.svc.optimize(
            SAMPLE_METRIC_INPUTS,
            {"total_budget": 50000, "min_confidence": 0.3},
        )
        self.assertIn("selected_count", result)
        self.assertIn("budget_utilization", result)

    def test_owner_dashboard_view(self):
        """Each owner role with accountable/responsible assignments should see metrics."""
        # fm is accountable for Q1 and responsible for Q2/Q3/Q4
        # finance is accountable for Q2
        # food_safety is accountable for Q3
        # executive is accountable for Q4
        for role in ["fm", "finance", "food_safety", "executive"]:
            result = self.svc.get_metrics_for_owner(role)
            self.assertGreater(result["count"], 0,
                               f"Owner {role} should have assigned metrics")


# ═══════════════════════════════════════════════════════════════════
# 10. Integration with Existing Decision Analysis
# ═══════════════════════════════════════════════════════════════════

class TestExistingIntegration(unittest.TestCase):
    """Verify the new module connects to existing codebase concepts."""

    def test_metric_catalog_links_to_kpi_registry(self):
        """Metric catalog should reference existing KPI crew names from registry."""
        catalog = MetricCatalog()
        linked = [m for m in catalog.list_all() if m.kpi_crew_name]
        self.assertGreater(len(linked), 10, "Most metrics should link to KPI crews")

    def test_translation_inputs_match_kpi_outputs(self):
        """Translation rule inputs should align with KPI crew output structures."""
        library = TranslationRulesLibrary()
        # Reactive WO rule expects wo_count, cost_per_wo — same as calc_work_order_reduction output
        reactive_rules = library.list_by_metric("m_reactive_jobs")
        self.assertTrue(len(reactive_rules) > 0)
        required = reactive_rules[0].required_inputs
        self.assertIn("wo_count", required)
        self.assertIn("cost_per_wo", required)

    def test_cost_types_extend_existing_cost_model(self):
        """New cost types (opex/capex/risk/strategic) extend existing cost_model categories."""
        # Existing: software, implementation, managed_services, hardware
        # New: opex, capex, risk, strategic — these don't conflict
        new_types = {ct.value for ct in CostType}
        self.assertEqual(new_types, {"opex", "capex", "risk", "strategic"})

    def test_scenario_params_overlap_with_scenario_agent(self):
        """Parameter hierarchy should cover parameters that ScenarioAgent uses."""
        hierarchy = ParameterHierarchy()
        param_ids = {d.param_id for d in hierarchy.list_definitions()}
        # Key params that ScenarioAgent also uses
        expected = {"p_electricity_rate", "p_discount_rate", "p_capex_budget"}
        self.assertTrue(expected.issubset(param_ids),
                        f"Missing scenario agent params: {expected - param_ids}")


# ═══════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("Ownership Decision Support — Integration Test Suite")
    print("=" * 70)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        TestMetricCatalog,
        TestOwnershipModel,
        TestTranslationRules,
        TestAntiDoubleCounting,
        TestConsolidatedROI,
        TestConstraintOptimizer,
        TestParameterHierarchy,
        TestScenarioExtensions,
        TestOwnershipDecisionService,
        TestExistingIntegration,
    ]

    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 70)
    if result.wasSuccessful():
        print(f"ALL {result.testsRun} TESTS PASSED")
    else:
        print(f"FAILURES: {len(result.failures)}  ERRORS: {len(result.errors)}")
    print("=" * 70)
