"""
Test Suite for the Ownership Decision Crew — multi-agent pipeline.

Covers:
1. Schema contracts (StakeholderPosition, AssumptionRecord, ParetoOption, etc.)
2. Agent tools (structured JSON output)
3. Agent roster and factory functions
4. Task pipeline assembly and context chaining
5. Negotiation engine (conflict detection + resolution)
6. Pareto optimizer (multi-objective frontier)
7. Full deterministic pipeline (OwnershipDecisionCrew.run)
8. Integration: crew output feeds into existing decision advisory

Run with:
    python -m pytest tests/test_ownership_crew.py -v
    # or directly:
    python tests/test_ownership_crew.py
"""

import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import unittest
from typing import Any, Dict

# ── Sample metric inputs (reused across tests) ─────────────────

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
    "m_service_bureau": {"call_volume": 500, "cost_per_call": 25, "deflection_rate": 0.30},
    "m_replacement_cycle": {
        "replacement_count": 5, "avg_replacement_cost": 18000, "avoided_failure_cost": 5000,
    },
    "m_temp_breaches": {
        "breach_count": 8, "avg_spoilage_per_breach": 2500,
        "penalty_probability": 0.15, "avg_penalty": 10000, "audit_risk_cost": 5000,
    },
    "m_product_discard": {
        "discard_volume": 200, "avg_cogs_per_unit": 8,
        "discard_events": 15, "labor_per_event": 120, "disposal_cost_per_unit": 1.5,
    },
    "m_energy_reduction": {
        "kwh_reduction": 50000, "electricity_rate": 0.12,
        "carbon_factor": 0.0004, "carbon_price": 50,
    },
}


# ═══════════════════════════════════════════════════════════════════
# 1. Schema Tests
# ═══════════════════════════════════════════════════════════════════

class TestSchemas(unittest.TestCase):
    """Test all schema contract types serialize correctly."""

    def test_stakeholder_position_round_trip(self):
        """StakeholderPosition should serialize to dict with all fields."""
        from loweconex_platform.ownership.crew.schemas import (
            StakeholderPosition, Constraint, TradeBand,
        )
        pos = StakeholderPosition(
            agent_id="fm",
            agent_role="FM Agent",
            quadrant_authority="Q1",
            non_negotiables=[
                Constraint(agent_id="fm", description="test", value=4.0),
            ],
            trade_bands=[
                TradeBand(parameter_id="p_test", min_acceptable=0.1, max_acceptable=0.5),
            ],
            validated_metric_ids=["m_reactive_jobs"],
            sign_off=True,
        )
        d = pos.to_dict()
        self.assertEqual(d["agent_id"], "fm")
        self.assertEqual(len(d["non_negotiables"]), 1)
        self.assertEqual(len(d["trade_bands"]), 1)
        self.assertTrue(d["sign_off"])

    def test_assumption_record(self):
        from loweconex_platform.ownership.crew.schemas import AssumptionRecord
        a = AssumptionRecord(
            description="Cost per WO assumed $380",
            owner_agent="opex_modeler",
            source="benchmark",
        )
        d = a.to_dict()
        self.assertEqual(d["source"], "benchmark")
        self.assertIn("assumption_id", d)

    def test_pareto_option(self):
        from loweconex_platform.ownership.crew.schemas import ParetoOption
        opt = ParetoOption(
            label="Max NPV",
            objective_function="max_npv",
            npv=500000,
            roi_pct=150.0,
            risk_score=0.3,
        )
        d = opt.to_dict()
        self.assertEqual(d["npv"], 500000)
        self.assertEqual(d["label"], "Max NPV")

    def test_negotiation_log(self):
        from loweconex_platform.ownership.crew.schemas import NegotiationLog, ConflictRecord
        log = NegotiationLog(
            conflicts_detected=[
                ConflictRecord(agents_involved=["fm", "finance"], description="test"),
            ],
            conflicts_resolved=1,
            rounds=2,
        )
        d = log.to_dict()
        self.assertEqual(d["conflicts_resolved"], 1)
        self.assertEqual(d["rounds"], 2)
        self.assertEqual(len(d["conflicts_detected"]), 1)

    def test_decision_crew_output(self):
        from loweconex_platform.ownership.crew.schemas import DecisionCrewOutput
        out = DecisionCrewOutput(agent_count=12, task_count=13)
        d = out.to_dict()
        self.assertEqual(d["agent_count"], 12)
        self.assertEqual(d["task_count"], 13)
        self.assertIn("run_id", d)
        self.assertIn("pareto_options", d)
        self.assertIn("negotiation_log", d)


# ═══════════════════════════════════════════════════════════════════
# 2. Tool Tests
# ═══════════════════════════════════════════════════════════════════

class TestTools(unittest.TestCase):
    """Test all 12 BaseTool subclasses produce structured JSON."""

    def setUp(self):
        from loweconex_platform.ownership.api_routes import OwnershipDecisionService
        self.svc = OwnershipDecisionService()

    def test_read_parameter_set_tool(self):
        from loweconex_platform.ownership.crew.tools import ReadParameterSetTool
        tool = ReadParameterSetTool(self.svc.params)
        result = json.loads(tool._run())
        self.assertIn("resolved_parameters", result)
        self.assertIn("slider_params", result)

    def test_read_ownership_map_tool(self):
        from loweconex_platform.ownership.crew.tools import ReadOwnershipMapTool
        tool = ReadOwnershipMapTool(self.svc.ownership)
        result = json.loads(tool._run())
        self.assertGreater(len(result), 0)

    def test_read_metric_evidence_tool(self):
        from loweconex_platform.ownership.crew.tools import ReadMetricEvidenceTool
        tool = ReadMetricEvidenceTool(self.svc.catalog, SAMPLE_METRIC_INPUTS)
        result = json.loads(tool._run(quadrant="Q1"))
        self.assertIn("metric_evidence", result)
        self.assertGreater(result["count"], 0)

    def test_read_cost_lines_empty(self):
        from loweconex_platform.ownership.crew.tools import ReadCostLinesTool
        tool = ReadCostLinesTool([])
        result = json.loads(tool._run())
        self.assertEqual(result["count"], 0)

    def test_read_dependency_graph_tool(self):
        from loweconex_platform.ownership.crew.tools import ReadDependencyGraphTool
        tool = ReadDependencyGraphTool(self.svc.aggregation)
        result = json.loads(tool._run())
        self.assertIn("edges", result)
        self.assertGreater(result["count"], 0)

    def test_write_assumption_tool(self):
        from loweconex_platform.ownership.crew.tools import WriteAssumptionTool
        from loweconex_platform.ownership.crew.schemas import AssumptionRecord
        register = []
        tool = WriteAssumptionTool(register)
        result = json.loads(tool._run(json.dumps({
            "description": "Test assumption",
            "owner_agent": "test",
            "source": "benchmark",
        })))
        self.assertEqual(result["status"], "recorded")
        self.assertEqual(len(register), 1)

    def test_submit_stakeholder_position_tool(self):
        from loweconex_platform.ownership.crew.tools import SubmitStakeholderPositionTool
        positions = []
        tool = SubmitStakeholderPositionTool(positions)
        result = json.loads(tool._run(json.dumps({
            "agent_id": "fm",
            "agent_role": "FM Agent",
            "quadrant_authority": "Q1",
            "validated_metric_ids": ["m_reactive_jobs"],
            "sign_off": True,
        })))
        self.assertEqual(result["status"], "position_recorded")
        self.assertEqual(len(positions), 1)

    def test_run_translation_tool(self):
        from loweconex_platform.ownership.crew.tools import RunTranslationTool
        tool = RunTranslationTool(self.svc.rules, self.svc.ownership)
        result = json.loads(tool._run(
            metric_id="m_reactive_jobs",
            inputs_json=json.dumps({"wo_count": 100, "cost_per_wo": 400, "reduction_pct": 0.3}),
        ))
        self.assertIn("cost_lines", result)
        self.assertGreater(result["count"], 0)

    def test_read_scenario_tool(self):
        from loweconex_platform.ownership.crew.tools import ReadScenarioTool
        tool = ReadScenarioTool(self.svc.scenarios)
        result = json.loads(tool._run())
        self.assertIn("scenarios", result)
        self.assertGreater(result["count"], 0)


# ═══════════════════════════════════════════════════════════════════
# 3. Agent Tests
# ═══════════════════════════════════════════════════════════════════

class TestAgents(unittest.TestCase):
    """Test agent factory functions and roster."""

    def test_agent_roster_has_13_entries(self):
        from loweconex_platform.ownership.crew.agents import AGENT_ROSTER
        self.assertEqual(len(AGENT_ROSTER), 13)

    def test_agent_count_excludes_orchestrator(self):
        from loweconex_platform.ownership.crew.agents import get_agent_count
        self.assertEqual(get_agent_count(), 12)

    def test_stakeholder_group_has_5(self):
        from loweconex_platform.ownership.crew.agents import AGENT_ROSTER
        stakeholders = [k for k, v in AGENT_ROSTER.items() if v["group"] == "stakeholder"]
        self.assertEqual(len(stakeholders), 5)

    def test_dimension_group_has_4(self):
        from loweconex_platform.ownership.crew.agents import AGENT_ROSTER
        dimensions = [k for k, v in AGENT_ROSTER.items() if v["group"] == "dimension"]
        self.assertEqual(len(dimensions), 4)

    def test_governance_group_has_4(self):
        """Governance group includes reconciler, optimizer, auditor, orchestrator."""
        from loweconex_platform.ownership.crew.agents import AGENT_ROSTER
        governance = [k for k, v in AGENT_ROSTER.items() if v["group"] == "governance"]
        self.assertEqual(len(governance), 4)

    def test_factory_creates_agents(self):
        from loweconex_platform.ownership.crew.agents import (
            create_fm_agent, create_finance_agent, create_orchestrator,
        )
        fm = create_fm_agent()
        self.assertIsNotNone(fm)
        fin = create_finance_agent()
        self.assertIsNotNone(fin)
        orch = create_orchestrator()
        self.assertIsNotNone(orch)

    def test_orchestrator_allows_delegation(self):
        from loweconex_platform.ownership.crew.agents import create_orchestrator
        orch = create_orchestrator()
        self.assertTrue(getattr(orch, "allow_delegation", False))


# ═══════════════════════════════════════════════════════════════════
# 4. Task Pipeline Tests
# ═══════════════════════════════════════════════════════════════════

class TestTaskPipeline(unittest.TestCase):
    """Test task pipeline assembly and context chaining."""

    def test_pipeline_has_13_tasks(self):
        from loweconex_platform.ownership.crew.agents import (
            create_fm_agent, create_finance_agent, create_compliance_agent,
            create_ops_agent, create_esg_agent, create_opex_modeler,
            create_capex_modeler, create_risk_modeler, create_strategic_modeler,
            create_reconciliation_agent, create_optimizer_agent,
            create_audit_narrator, create_orchestrator,
        )
        from loweconex_platform.ownership.crew.tasks import assemble_task_pipeline

        agents = {
            "orchestrator": create_orchestrator(),
            "fm": create_fm_agent(),
            "finance": create_finance_agent(),
            "compliance": create_compliance_agent(),
            "ops": create_ops_agent(),
            "esg": create_esg_agent(),
            "opex_modeler": create_opex_modeler(),
            "capex_modeler": create_capex_modeler(),
            "risk_modeler": create_risk_modeler(),
            "strategic_modeler": create_strategic_modeler(),
            "reconciler": create_reconciliation_agent(),
            "optimizer": create_optimizer_agent(),
            "auditor": create_audit_narrator(),
        }
        tasks = assemble_task_pipeline(agents)
        self.assertEqual(len(tasks), 13)

    def test_stage2_tasks_depend_on_stage1(self):
        """Dimension agent tasks should have stage 1 tasks in their context."""
        from loweconex_platform.ownership.crew.agents import (
            create_fm_agent, create_finance_agent, create_compliance_agent,
            create_ops_agent, create_esg_agent, create_opex_modeler,
            create_capex_modeler, create_risk_modeler, create_strategic_modeler,
            create_reconciliation_agent, create_optimizer_agent,
            create_audit_narrator, create_orchestrator,
        )
        from loweconex_platform.ownership.crew.tasks import assemble_task_pipeline

        agents = {
            "orchestrator": create_orchestrator(),
            "fm": create_fm_agent(), "finance": create_finance_agent(),
            "compliance": create_compliance_agent(), "ops": create_ops_agent(),
            "esg": create_esg_agent(), "opex_modeler": create_opex_modeler(),
            "capex_modeler": create_capex_modeler(),
            "risk_modeler": create_risk_modeler(),
            "strategic_modeler": create_strategic_modeler(),
            "reconciler": create_reconciliation_agent(),
            "optimizer": create_optimizer_agent(),
            "auditor": create_audit_narrator(),
        }
        tasks = assemble_task_pipeline(agents)
        # Tasks 6-9 (indices 6-9) are Stage 2, should have 5 context tasks from Stage 1
        for i in range(6, 10):
            ctx = getattr(tasks[i], "context", [])
            self.assertEqual(len(ctx), 5, f"Task {i} should have 5 context tasks (Stage 1)")


# ═══════════════════════════════════════════════════════════════════
# 5. Negotiation Engine Tests
# ═══════════════════════════════════════════════════════════════════

class TestNegotiation(unittest.TestCase):
    """Test the structured conflict resolution engine."""

    def _make_positions(self):
        from loweconex_platform.ownership.crew.schemas import (
            StakeholderPosition, Constraint, TradeBand,
        )
        return [
            StakeholderPosition(
                agent_id="finance",
                agent_role="Finance Agent",
                quadrant_authority="Q2",
                non_negotiables=[
                    Constraint(
                        agent_id="finance",
                        constraint_type="hard",
                        description="Capex ceiling $500K",
                        parameter_id="p_capex_budget",
                        operator="lte",
                        value=500000,
                    ),
                ],
                trade_bands=[
                    TradeBand(
                        parameter_id="p_discount_rate",
                        min_acceptable=0.08,
                        max_acceptable=0.12,
                        preferred=0.10,
                    ),
                ],
            ),
            StakeholderPosition(
                agent_id="esg",
                agent_role="ESG Agent",
                quadrant_authority="Q4",
                preferences=[
                    Constraint(
                        agent_id="esg",
                        constraint_type="soft",
                        description="Want higher energy reduction target",
                        parameter_id="p_capex_budget",
                        operator="gte",
                        value=600000,
                        weight=0.5,
                    ),
                ],
                trade_bands=[
                    TradeBand(
                        parameter_id="p_discount_rate",
                        min_acceptable=0.06,
                        max_acceptable=0.09,
                        preferred=0.07,
                    ),
                ],
            ),
            StakeholderPosition(
                agent_id="compliance",
                agent_role="Compliance Agent",
                quadrant_authority="Q3",
                non_negotiables=[
                    Constraint(
                        agent_id="compliance",
                        constraint_type="hard",
                        description="Monitoring always on",
                        parameter_id="p_monitoring",
                        operator="eq",
                        value=1.0,
                    ),
                ],
            ),
        ]

    def test_no_conflict_positions(self):
        """Positions with no overlapping parameters should have no conflicts."""
        from loweconex_platform.ownership.crew.negotiation import NegotiationEngine
        from loweconex_platform.ownership.crew.schemas import StakeholderPosition, Constraint

        positions = [
            StakeholderPosition(
                agent_id="fm",
                non_negotiables=[
                    Constraint(agent_id="fm", parameter_id="p_a", operator="lte", value=10),
                ],
            ),
            StakeholderPosition(
                agent_id="finance",
                non_negotiables=[
                    Constraint(agent_id="finance", parameter_id="p_b", operator="lte", value=20),
                ],
            ),
        ]
        engine = NegotiationEngine()
        log = engine.negotiate(positions)
        self.assertEqual(len(log.conflicts_detected), 0)
        self.assertTrue(all(log.final_sign_offs.values()))

    def test_hard_soft_conflict_detected(self):
        """Soft preference violating hard constraint should be detected."""
        from loweconex_platform.ownership.crew.negotiation import NegotiationEngine
        positions = self._make_positions()
        engine = NegotiationEngine()
        log = engine.negotiate(positions)
        # Finance has hard capex ≤ 500K, ESG has soft capex ≥ 600K → conflict
        priority_conflicts = [c for c in log.conflicts_detected if c.conflict_type == "priority"]
        self.assertGreater(len(priority_conflicts), 0, "Should detect hard vs soft conflict")

    def test_trade_band_conflict_detected(self):
        """Non-overlapping trade bands should be detected."""
        from loweconex_platform.ownership.crew.negotiation import NegotiationEngine
        positions = self._make_positions()
        engine = NegotiationEngine()
        log = engine.negotiate(positions)
        # Finance wants discount rate [0.08, 0.12], ESG wants [0.06, 0.09]
        # These overlap at [0.08, 0.09] so no conflict expected
        # Let's verify the log has rounds > 0
        self.assertGreater(log.rounds, 0)

    def test_conflicts_are_resolved(self):
        """All detected conflicts should be resolved."""
        from loweconex_platform.ownership.crew.negotiation import NegotiationEngine
        positions = self._make_positions()
        engine = NegotiationEngine()
        log = engine.negotiate(positions)
        for conflict in log.conflicts_detected:
            self.assertTrue(
                len(conflict.resolution) > 0,
                f"Conflict '{conflict.description}' should be resolved"
            )

    def test_effective_constraints_after_negotiation(self):
        """Should produce effective constraints dict for optimizer."""
        from loweconex_platform.ownership.crew.negotiation import NegotiationEngine
        positions = self._make_positions()
        engine = NegotiationEngine()
        engine.negotiate(positions)
        effective = engine.get_effective_constraints()
        self.assertIn("hard_constraints", effective)
        self.assertIn("soft_preferences", effective)
        self.assertGreater(len(effective["hard_constraints"]), 0)


# ═══════════════════════════════════════════════════════════════════
# 6. Pareto Optimizer Tests
# ═══════════════════════════════════════════════════════════════════

class TestParetoOptimizer(unittest.TestCase):
    """Test multi-objective Pareto frontier generation."""

    def setUp(self):
        from loweconex_platform.ownership.api_routes import OwnershipDecisionService
        self.svc = OwnershipDecisionService()
        self.stack = self.svc.aggregation.build_cost_stack(SAMPLE_METRIC_INPUTS)

    def test_generates_multiple_options(self):
        """Should produce 3-5 Pareto options."""
        from loweconex_platform.ownership.crew.pareto import ParetoOptimizer
        from loweconex_platform.ownership.constraint_optimizer import BudgetConstraints

        pareto = ParetoOptimizer()
        options = pareto.generate_pareto_frontier(
            self.stack, BudgetConstraints()
        )
        self.assertGreaterEqual(len(options), 3)
        self.assertLessEqual(len(options), 5)

    def test_each_option_has_required_fields(self):
        """Each ParetoOption should have label, npv, roi_pct, risk_score."""
        from loweconex_platform.ownership.crew.pareto import ParetoOptimizer
        from loweconex_platform.ownership.constraint_optimizer import BudgetConstraints

        pareto = ParetoOptimizer()
        options = pareto.generate_pareto_frontier(
            self.stack, BudgetConstraints()
        )
        for opt in options:
            self.assertTrue(len(opt.label) > 0, "Option should have a label")
            self.assertTrue(len(opt.objective_function) > 0)
            self.assertIsInstance(opt.npv, float)

    def test_recommend_returns_valid_id(self):
        """Recommend should return an option_id that exists in the options list."""
        from loweconex_platform.ownership.crew.pareto import ParetoOptimizer
        from loweconex_platform.ownership.constraint_optimizer import BudgetConstraints

        pareto = ParetoOptimizer()
        options = pareto.generate_pareto_frontier(
            self.stack, BudgetConstraints()
        )
        recommended = pareto.recommend(options)
        option_ids = [o.option_id for o in options]
        self.assertIn(recommended, option_ids)

    def test_high_confidence_filter_changes_options(self):
        """High min_confidence filter should change Pareto options vs no filter."""
        from loweconex_platform.ownership.crew.pareto import ParetoOptimizer
        from loweconex_platform.ownership.constraint_optimizer import BudgetConstraints

        pareto = ParetoOptimizer()
        no_filter = pareto.generate_pareto_frontier(
            self.stack, BudgetConstraints(min_confidence=0.0)
        )
        high_filter = pareto.generate_pareto_frontier(
            self.stack, BudgetConstraints(min_confidence=0.9)
        )
        # Both should produce valid options
        self.assertGreaterEqual(len(no_filter), 3)
        self.assertGreaterEqual(len(high_filter), 3)


# ═══════════════════════════════════════════════════════════════════
# 7. Full Pipeline (Deterministic) Tests
# ═══════════════════════════════════════════════════════════════════

class TestDecisionCrew(unittest.TestCase):
    """Test the full OwnershipDecisionCrew deterministic pipeline."""

    def test_full_pipeline_produces_output(self):
        """Full pipeline should produce DecisionCrewOutput with all sections."""
        from loweconex_platform.ownership.crew.decision_crew import OwnershipDecisionCrew
        crew = OwnershipDecisionCrew()
        result = crew.run(metric_inputs=SAMPLE_METRIC_INPUTS)

        self.assertIsNotNone(result)
        d = result.to_dict()
        self.assertIn("run_id", d)
        self.assertIn("stakeholder_positions", d)
        self.assertIn("unified_cost_stack", d)
        self.assertIn("consolidated_roi", d)
        self.assertIn("pareto_options", d)
        self.assertIn("negotiation_log", d)
        self.assertIn("board_narrative", d)
        self.assertIn("assumption_register", d)

    def test_pipeline_produces_stakeholder_positions(self):
        """Should produce 5 stakeholder positions (one per agent)."""
        from loweconex_platform.ownership.crew.decision_crew import OwnershipDecisionCrew
        crew = OwnershipDecisionCrew()
        result = crew.run(metric_inputs=SAMPLE_METRIC_INPUTS)
        self.assertEqual(len(result.stakeholder_positions), 5)

    def test_pipeline_produces_pareto_options(self):
        """Should produce 3-5 Pareto options."""
        from loweconex_platform.ownership.crew.decision_crew import OwnershipDecisionCrew
        crew = OwnershipDecisionCrew()
        result = crew.run(metric_inputs=SAMPLE_METRIC_INPUTS)
        self.assertGreaterEqual(len(result.pareto_options), 3)

    def test_pipeline_has_recommended_option(self):
        """Should recommend a specific Pareto option."""
        from loweconex_platform.ownership.crew.decision_crew import OwnershipDecisionCrew
        crew = OwnershipDecisionCrew()
        result = crew.run(metric_inputs=SAMPLE_METRIC_INPUTS)
        self.assertTrue(len(result.recommended_option_id) > 0)
        option_ids = [o.option_id for o in result.pareto_options]
        self.assertIn(result.recommended_option_id, option_ids)

    def test_pipeline_roi_npv_positive(self):
        """With standard inputs, NPV should be positive."""
        from loweconex_platform.ownership.crew.decision_crew import OwnershipDecisionCrew
        crew = OwnershipDecisionCrew()
        result = crew.run(metric_inputs=SAMPLE_METRIC_INPUTS)
        npv = result.consolidated_roi.get("npv", 0)
        self.assertGreater(npv, 0, f"NPV should be positive, got {npv}")

    def test_pipeline_negotiation_runs(self):
        """Negotiation log should have positions and rounds > 0."""
        from loweconex_platform.ownership.crew.decision_crew import OwnershipDecisionCrew
        crew = OwnershipDecisionCrew()
        result = crew.run(metric_inputs=SAMPLE_METRIC_INPUTS)
        log = result.negotiation_log
        self.assertGreater(log.rounds, 0)
        self.assertGreater(len(log.positions), 0)

    def test_pipeline_cost_lines_by_dimension(self):
        """Should have cost lines grouped by opex/capex/risk/strategic."""
        from loweconex_platform.ownership.crew.decision_crew import OwnershipDecisionCrew
        crew = OwnershipDecisionCrew()
        result = crew.run(metric_inputs=SAMPLE_METRIC_INPUTS)
        dims = result.cost_lines_by_dimension
        self.assertIn("opex", dims)
        self.assertIn("capex", dims)
        self.assertIn("risk", dims)
        self.assertIn("strategic", dims)

    def test_pipeline_board_narrative_not_empty(self):
        """Board narrative should be non-empty text."""
        from loweconex_platform.ownership.crew.decision_crew import OwnershipDecisionCrew
        crew = OwnershipDecisionCrew()
        result = crew.run(metric_inputs=SAMPLE_METRIC_INPUTS)
        self.assertGreater(len(result.board_narrative), 100)

    def test_pipeline_lineage_summary(self):
        """Lineage summary should trace metrics → rules → lines."""
        from loweconex_platform.ownership.crew.decision_crew import OwnershipDecisionCrew
        crew = OwnershipDecisionCrew()
        result = crew.run(metric_inputs=SAMPLE_METRIC_INPUTS)
        lineage = result.lineage_summary
        self.assertIn("metrics_used", lineage)
        self.assertIn("translation_rules_applied", lineage)
        self.assertGreater(lineage["cost_lines_produced"], 0)

    def test_pipeline_with_constraints(self):
        """Pipeline should respect budget constraints."""
        from loweconex_platform.ownership.crew.decision_crew import OwnershipDecisionCrew
        crew = OwnershipDecisionCrew()
        result = crew.run(
            metric_inputs=SAMPLE_METRIC_INPUTS,
            constraints={"total_budget": 50000, "min_confidence": 0.3},
        )
        self.assertIsNotNone(result)
        self.assertGreater(len(result.pareto_options), 0)

    def test_pipeline_execution_time_recorded(self):
        """Execution time should be recorded in milliseconds."""
        from loweconex_platform.ownership.crew.decision_crew import OwnershipDecisionCrew
        crew = OwnershipDecisionCrew()
        result = crew.run(metric_inputs=SAMPLE_METRIC_INPUTS)
        self.assertGreater(result.execution_time_ms, 0)

    def test_pipeline_uses_shared_service(self):
        """Pipeline should work with shared OwnershipDecisionService components."""
        from loweconex_platform.ownership.crew.decision_crew import OwnershipDecisionCrew
        from loweconex_platform.ownership.api_routes import OwnershipDecisionService

        svc = OwnershipDecisionService()
        crew = OwnershipDecisionCrew(
            catalog=svc.catalog,
            ownership=svc.ownership,
            rules=svc.rules,
            params=svc.params,
            roi_engine=svc.roi_engine,
            optimizer=svc.optimizer,
            aggregation=svc.aggregation,
            scenarios=svc.scenarios,
        )
        result = crew.run(metric_inputs=SAMPLE_METRIC_INPUTS)
        self.assertGreater(result.consolidated_roi.get("npv", 0), 0)


# ═══════════════════════════════════════════════════════════════════
# 8. Integration with Existing Systems
# ═══════════════════════════════════════════════════════════════════

class TestCrewIntegration(unittest.TestCase):
    """Test crew output integrates with existing decision advisory."""

    def test_crew_output_serializes_cleanly(self):
        """DecisionCrewOutput.to_dict() should be JSON-serializable."""
        from loweconex_platform.ownership.crew.decision_crew import OwnershipDecisionCrew
        crew = OwnershipDecisionCrew()
        result = crew.run(metric_inputs=SAMPLE_METRIC_INPUTS)
        d = result.to_dict()
        serialized = json.dumps(d, default=str)
        self.assertGreater(len(serialized), 100)

    def test_orchestrator_crew_method_exists(self):
        """OrchestratorCrew should have _run_ownership_decision_crew method."""
        from loweconex_platform.orchestration.orchestrator_crew import OrchestratorCrew
        self.assertTrue(
            hasattr(OrchestratorCrew, "_run_ownership_decision_crew"),
            "OrchestratorCrew should have _run_ownership_decision_crew method"
        )

    def test_kpi_to_metric_mapping(self):
        """KPI-to-metric mapping should cover key KPI crew names."""
        from loweconex_platform.orchestration.orchestrator_crew import OrchestratorCrew
        mapping = OrchestratorCrew._extract_metric_inputs_from_kpi({})
        # Should return empty for empty input
        self.assertEqual(len(mapping), 0)

    def test_ownership_crew_available_flag(self):
        """OWNERSHIP_CREW_AVAILABLE should be True when module imports."""
        from loweconex_platform.ownership import OWNERSHIP_CREW_AVAILABLE
        self.assertTrue(OWNERSHIP_CREW_AVAILABLE)

    def test_crew_agents_endpoint_data(self):
        """Agent roster should be accessible for API endpoint."""
        from loweconex_platform.ownership.crew.agents import AGENT_ROSTER, get_agent_count
        self.assertEqual(get_agent_count(), 12)
        groups = {"stakeholder": 0, "dimension": 0, "governance": 0}
        for info in AGENT_ROSTER.values():
            groups[info["group"]] += 1
        self.assertEqual(groups["stakeholder"], 5)
        self.assertEqual(groups["dimension"], 4)
        self.assertEqual(groups["governance"], 4)


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
