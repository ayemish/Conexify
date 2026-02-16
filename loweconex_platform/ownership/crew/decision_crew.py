"""
OwnershipDecisionCrew — main entry point for the 12-agent multi-agent
decision optimization pipeline.

Assembles all agents with tools bound to the shared ownership module state,
runs the 5-stage task pipeline (ingest → validate → translate → reconcile →
optimize+govern), and returns a DecisionCrewOutput with full audit trail.

Provides a deterministic fallback when CrewAI is unavailable, matching
the pattern in DecisionAdvisoryAgent.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from shared.agents.crewai_base import (
    Agent, Crew, Process, Task, CREWAI_AVAILABLE,
)

from loweconex_platform.ownership.metric_catalog import MetricCatalog, Quadrant
from loweconex_platform.ownership.ownership_model import OwnershipEngine
from loweconex_platform.ownership.cost_stack import CostStack, CostLineItem, CostType
from loweconex_platform.ownership.translation_rules import TranslationRulesLibrary
from loweconex_platform.ownership.aggregation_engine import AggregationEngine
from loweconex_platform.ownership.consolidated_roi import ConsolidatedROIEngine, ConsolidatedROI
from loweconex_platform.ownership.constraint_optimizer import ConstraintOptimizer, BudgetConstraints
from loweconex_platform.ownership.parameter_hierarchy import ParameterHierarchy
from loweconex_platform.ownership.scenario_extensions import ScenarioManager

from loweconex_platform.ownership.crew.schemas import (
    AgentMessage,
    AssumptionRecord,
    DecisionCrewOutput,
    NegotiationLog,
    ParetoOption,
    StakeholderPosition,
    Constraint,
    TradeBand,
)
from loweconex_platform.ownership.crew.tools import (
    ReadParameterSetTool,
    ReadOwnershipMapTool,
    ReadMetricEvidenceTool,
    ReadCostLinesTool,
    ReadDependencyGraphTool,
    WriteCostLineTool,
    WriteAssumptionTool,
    ReadScenarioTool,
    RunTranslationTool,
    RunOptimizationTool,
    ReadROITool,
    SubmitStakeholderPositionTool,
)
from loweconex_platform.ownership.crew.agents import (
    create_fm_agent,
    create_finance_agent,
    create_compliance_agent,
    create_ops_agent,
    create_esg_agent,
    create_opex_modeler,
    create_capex_modeler,
    create_risk_modeler,
    create_strategic_modeler,
    create_reconciliation_agent,
    create_optimizer_agent,
    create_audit_narrator,
    create_orchestrator,
    get_agent_count,
)
from loweconex_platform.ownership.crew.tasks import assemble_task_pipeline
from loweconex_platform.ownership.crew.negotiation import NegotiationEngine
from loweconex_platform.ownership.crew.pareto import ParetoOptimizer
from loweconex_platform.ownership.financial_constants import IMPLEMENTATION_COST

logger = logging.getLogger(__name__)


class OwnershipDecisionCrew:
    """
    Multi-agent crew for ownership-aware cost optimization.

    12 agents in 3 groups:
      A) Stakeholder Agents (5): FM, Finance, Compliance, Ops, ESG
      B) Dimension Agents (4): Opex, Capex, Risk, Strategic modelers
      C) Governance Agents (3): Reconciliation, Optimizer, Audit Narrator

    + 1 Orchestrator as manager.
    """

    def __init__(
        self,
        catalog: Optional[MetricCatalog] = None,
        ownership: Optional[OwnershipEngine] = None,
        rules: Optional[TranslationRulesLibrary] = None,
        params: Optional[ParameterHierarchy] = None,
        roi_engine: Optional[ConsolidatedROIEngine] = None,
        optimizer: Optional[ConstraintOptimizer] = None,
        aggregation: Optional[AggregationEngine] = None,
        scenarios: Optional[ScenarioManager] = None,
    ):
        # Core ownership components (create defaults if not provided)
        self.catalog = catalog or MetricCatalog()
        self.ownership = ownership or OwnershipEngine()
        self.rules = rules or TranslationRulesLibrary()
        self.params = params or ParameterHierarchy()
        self.roi_engine = roi_engine or ConsolidatedROIEngine()
        self.optimizer = optimizer or ConstraintOptimizer()

        if aggregation:
            self.aggregation = aggregation
        else:
            self.aggregation = AggregationEngine(
                metric_catalog=self.catalog,
                ownership_engine=self.ownership,
                rules_library=self.rules,
            )

        self.scenarios = scenarios or ScenarioManager(parameter_hierarchy=self.params)

        # Shared mutable state for tools
        self._cost_stack_ref: List[CostStack] = []
        self._roi_ref: List[Dict[str, Any]] = []
        self._positions: List[StakeholderPosition] = []
        self._assumptions: List[AssumptionRecord] = []
        self._messages: List[AgentMessage] = []

        # Sub-engines
        self._negotiation = NegotiationEngine()
        self._pareto = ParetoOptimizer(self.optimizer)

    def run(
        self,
        metric_inputs: Dict[str, Dict[str, Any]],
        constraints: Optional[Dict[str, Any]] = None,
        scenario_id: Optional[str] = None,
    ) -> DecisionCrewOutput:
        """
        Execute the full multi-agent decision pipeline.

        Args:
            metric_inputs: {metric_id: {input_name: value, ...}}
            constraints: Optional budget constraints dict.
            scenario_id: Optional scenario to run against.

        Returns:
            DecisionCrewOutput with all pipeline artifacts.
        """
        start_time = time.time()
        run_id = str(uuid.uuid4())

        logger.info(f"=== OwnershipDecisionCrew Started (run_id={run_id}) ===")
        logger.info(f"Metrics: {len(metric_inputs)}, CrewAI available: {CREWAI_AVAILABLE}")

        # Reset shared state
        self._cost_stack_ref.clear()
        self._roi_ref.clear()
        self._positions.clear()
        self._assumptions.clear()
        self._messages.clear()

        # Check if real CrewAI agents can be created (need API key)
        _can_use_crewai = CREWAI_AVAILABLE
        if _can_use_crewai:
            from shared.agents.crewai_base import _MockAgent
            test_agent = create_fm_agent()
            if isinstance(test_agent, _MockAgent):
                _can_use_crewai = False
                logger.info("CrewAI installed but agents are mocks (no API key?)")

        if _can_use_crewai:
            try:
                output = self._run_crewai_pipeline(
                    metric_inputs, constraints or {}, scenario_id, run_id
                )
            except Exception as e:
                logger.error(f"CrewAI pipeline failed: {e}", exc_info=True)
                logger.info("Falling back to deterministic pipeline")
                output = self._run_deterministic_pipeline(
                    metric_inputs, constraints or {}, scenario_id, run_id
                )
        else:
            logger.info("CrewAI not available — running deterministic pipeline")
            output = self._run_deterministic_pipeline(
                metric_inputs, constraints or {}, scenario_id, run_id
            )

        output.execution_time_ms = int((time.time() - start_time) * 1000)
        logger.info(
            f"=== OwnershipDecisionCrew Completed in {output.execution_time_ms}ms "
            f"(run_id={run_id}) ==="
        )
        return output

    # ═══════════════════════════════════════════════════════════════
    # CrewAI Pipeline
    # ═══════════════════════════════════════════════════════════════

    def _run_crewai_pipeline(
        self,
        metric_inputs: Dict[str, Dict[str, Any]],
        constraints: Dict[str, Any],
        scenario_id: Optional[str],
        run_id: str,
    ) -> DecisionCrewOutput:
        """Run the full pipeline using CrewAI agents."""
        # Build tools
        tools = self._build_tools(metric_inputs)

        # Create agents with tools
        agents = self._create_agents(tools)

        # Assemble task pipeline
        tasks = assemble_task_pipeline(agents)

        # Build crew
        crew = Crew(
            agents=list(agents.values()),
            tasks=tasks,
            process=Process.hierarchical,
            manager_agent=agents["orchestrator"],
            verbose=True,
        )

        # Kick off
        crew_output = crew.kickoff(inputs={
            "metric_inputs": json.dumps(metric_inputs, default=str),
            "constraints": json.dumps(constraints, default=str),
            "scenario_id": scenario_id or "",
            "run_id": run_id,
        })

        # Build output from shared state + crew output
        return self._build_output(
            metric_inputs, constraints, scenario_id, run_id,
            crewai_used=True,
        )

    # ═══════════════════════════════════════════════════════════════
    # Deterministic Fallback Pipeline
    # ═══════════════════════════════════════════════════════════════

    def _run_deterministic_pipeline(
        self,
        metric_inputs: Dict[str, Dict[str, Any]],
        constraints: Dict[str, Any],
        scenario_id: Optional[str],
        run_id: str,
    ) -> DecisionCrewOutput:
        """
        Rule-based fallback when CrewAI is unavailable.

        Executes the same 5-stage logic deterministically:
        Stage 0: Parameter resolution
        Stage 1: Ownership validation + stakeholder positions
        Stage 2: Cost translation via aggregation engine
        Stage 3: Anti-double-counting reconciliation
        Stage 4: Optimization + ROI computation + narrative
        """
        # ── Stage 0: Parameter Resolution ────────────────────────────
        logger.info("--- Stage 0: Parameter Resolution ---")
        resolved_params = self.params.resolve_all()
        self._messages.append(AgentMessage(
            sender="orchestrator", receiver="all",
            message_type="stage_transition", stage=0,
            content=f"Pipeline initiated. Resolved {len(resolved_params)} parameters for scope.",
            data_summary={"parameters_resolved": len(resolved_params)},
        ))

        # ── Stage 1: Ownership Validation + Stakeholder Positions ──
        logger.info("--- Stage 1: Ownership Validation + Stakeholder Positions ---")
        positions = self._deterministic_stakeholder_validation(metric_inputs)
        self._positions = positions

        # Emit context hand-off from orchestrator to each stakeholder
        for pos in positions:
            self._messages.append(AgentMessage(
                sender="orchestrator", receiver=pos.agent_id,
                message_type="delegation", stage=1,
                content=f"Delegating {pos.quadrant_authority} metric validation to {pos.agent_role}.",
                data_summary={"quadrant": pos.quadrant_authority, "metrics_in_scope": len(pos.validated_metric_ids)},
            ))
            # Each stakeholder emits their position back
            n_hard = len(pos.non_negotiables or [])
            n_soft = len(pos.preferences or [])
            self._messages.append(AgentMessage(
                sender=pos.agent_id, receiver="orchestrator",
                message_type="context_handoff", stage=1,
                content=(
                    f"{pos.agent_role} validated {len(pos.validated_metric_ids)} metrics. "
                    f"Emitting {n_hard} hard constraints, {n_soft} preferences. "
                    f"{'Signed off.' if pos.sign_off else 'Objections raised.'}"
                ),
                data_summary={
                    "non_negotiables": n_hard, "preferences": n_soft,
                    "trade_bands": len(pos.trade_bands or []), "sign_off": pos.sign_off,
                },
            ))

        # ── Stage 1.5: Negotiation ─────────────────────────────────
        logger.info("--- Stage 1.5: Negotiation ---")
        negotiation_log = self._negotiation.negotiate(positions)

        if negotiation_log.conflicts_detected:
            for conflict in negotiation_log.conflicts_detected:
                self._messages.append(AgentMessage(
                    sender="reconciler",
                    receiver=", ".join(conflict.agents_involved),
                    message_type="negotiation", stage=1,
                    content=f"Conflict detected: {conflict.description}",
                    data_summary={
                        "conflict_type": conflict.conflict_type,
                        "agents": conflict.agents_involved,
                        "resolution": conflict.resolution or "pending",
                        "method": conflict.resolution_method or "",
                    },
                ))
            self._messages.append(AgentMessage(
                sender="reconciler", receiver="orchestrator",
                message_type="negotiation", stage=1,
                content=(
                    f"Negotiation complete: {negotiation_log.conflicts_resolved}/{len(negotiation_log.conflicts_detected)} "
                    f"conflicts resolved in {negotiation_log.rounds} rounds."
                ),
                data_summary={
                    "conflicts_detected": len(negotiation_log.conflicts_detected),
                    "conflicts_resolved": negotiation_log.conflicts_resolved,
                    "rounds": negotiation_log.rounds,
                    "sign_offs": negotiation_log.final_sign_offs,
                },
            ))
        else:
            self._messages.append(AgentMessage(
                sender="reconciler", receiver="orchestrator",
                message_type="negotiation", stage=1,
                content="No conflicts between stakeholder positions. All agents signed off.",
                data_summary={"conflicts_detected": 0, "sign_offs": negotiation_log.final_sign_offs},
            ))

        # Sign-off messages
        for agent_id, signed in negotiation_log.final_sign_offs.items():
            self._messages.append(AgentMessage(
                sender=agent_id, receiver="orchestrator",
                message_type="sign_off", stage=1,
                content=f"{'Signed off on negotiated constraints.' if signed else 'Withheld sign-off — unresolved objections.'}",
                data_summary={"signed_off": signed},
            ))

        # ── Stage 2: Cost Translation ──────────────────────────────
        logger.info("--- Stage 2+3: Cost Translation + Reconciliation ---")
        # Hand-off from stakeholder positions to dimension agents
        dim_agents = [
            ("opex_modeler", "Opex Cost Modeler", "Q1"),
            ("capex_modeler", "Capex/Lifecycle Modeler", "Q2"),
            ("risk_modeler", "Risk/Compliance EV Modeler", "Q3"),
            ("strategic_modeler", "Cross-Silo Value Modeler", "Q4"),
        ]
        for agent_id, role, quad in dim_agents:
            self._messages.append(AgentMessage(
                sender="orchestrator", receiver=agent_id,
                message_type="context_handoff", stage=2,
                content=f"Passing validated stakeholder constraints and {quad} metric inputs to {role}.",
                data_summary={"quadrant": quad, "metric_count": len(metric_inputs)},
            ))

        cost_stack = self.aggregation.build_cost_stack(metric_inputs, scenario_id)
        self._cost_stack_ref = [cost_stack]

        # Each dimension agent reports back
        dim_lines = self._group_lines_by_dimension(cost_stack)
        for agent_id, role, quad in dim_agents:
            ct = {"opex_modeler": "opex", "capex_modeler": "capex", "risk_modeler": "risk", "strategic_modeler": "strategic"}[agent_id]
            lines = dim_lines.get(ct, [])
            total = sum(abs(l.get("amount", 0)) for l in lines)
            self._messages.append(AgentMessage(
                sender=agent_id, receiver="reconciler",
                message_type="context_handoff", stage=2,
                content=f"{role} produced {len(lines)} cost lines totaling ${total:,.0f}.",
                data_summary={"cost_type": ct, "line_count": len(lines), "total": round(total, 2)},
            ))

        # ── Stage 3: Reconciliation ────────────────────────────────
        adjustments = self.aggregation.get_adjustments()
        self._messages.append(AgentMessage(
            sender="reconciler", receiver="optimizer",
            message_type="context_handoff", stage=3,
            content=(
                f"Unified cost stack built: {len(cost_stack.lines)} lines. "
                f"Applied {len(adjustments)} anti-double-counting adjustments."
            ),
            data_summary={
                "total_lines": len(cost_stack.lines),
                "adjustments": len(adjustments),
            },
        ))

        # ── Stage 4: ROI + Optimization ────────────────────────────
        logger.info("--- Stage 4: ROI + Optimization ---")
        impl_cost = constraints.get("implementation_cost", IMPLEMENTATION_COST)
        roi = self.roi_engine.compute(
            cost_stack=cost_stack,
            scenario_id=scenario_id or "",
            scenario_name=scenario_id or "default",
            implementation_cost=impl_cost,
        )
        self._roi_ref = [roi.to_dict()]

        budget_constraints = BudgetConstraints(
            total_budget=constraints.get("total_budget", float("inf")),
            capex_budget=constraints.get("capex_budget", float("inf")),
            opex_budget=constraints.get("opex_budget", float("inf")),
            owner_budgets=constraints.get("owner_budgets", {}),
            min_confidence=constraints.get("min_confidence", 0),
        )

        stakeholder_constraints = self._negotiation.get_effective_constraints()
        pareto_options = self._pareto.generate_pareto_frontier(
            cost_stack, budget_constraints, stakeholder_constraints,
            implementation_cost=impl_cost,
        )
        recommended_id = self._pareto.recommend(pareto_options)

        self._messages.append(AgentMessage(
            sender="optimizer", receiver="auditor",
            message_type="context_handoff", stage=4,
            content=f"Generated {len(pareto_options)} Pareto-optimal options. Recommended: {recommended_id}.",
            data_summary={"pareto_options": len(pareto_options), "recommended": recommended_id},
        ))

        # ── Stage 4b: Narrative ────────────────────────────────────
        logger.info("--- Stage 5: Narrative Generation ---")
        narrative = self._generate_deterministic_narrative(roi, cost_stack, pareto_options)

        self._messages.append(AgentMessage(
            sender="auditor", receiver="orchestrator",
            message_type="context_handoff", stage=4,
            content=f"Board narrative generated ({len(narrative)} chars). Pipeline complete.",
            data_summary={"narrative_length": len(narrative)},
        ))

        # Build assumptions from translation rules
        assumptions = self._collect_assumptions(cost_stack)

        return DecisionCrewOutput(
            run_id=run_id,
            stakeholder_positions=positions,
            cost_lines_by_dimension=dim_lines,
            unified_cost_stack=cost_stack.to_dict(),
            adjustments_applied=adjustments,
            consolidated_roi=roi.to_dict(),
            pareto_options=pareto_options,
            recommended_option_id=recommended_id,
            negotiation_log=negotiation_log,
            assumption_register=assumptions,
            board_narrative=narrative,
            lineage_summary=self._build_lineage_summary(cost_stack),
            agent_messages=list(self._messages),
            agent_count=get_agent_count(),
            task_count=13,
            crewai_used=False,
        )

    # ═══════════════════════════════════════════════════════════════
    # Deterministic Stakeholder Validation
    # ═══════════════════════════════════════════════════════════════

    def _deterministic_stakeholder_validation(
        self, metric_inputs: Dict[str, Dict[str, Any]]
    ) -> List[StakeholderPosition]:
        """Generate stakeholder positions deterministically based on quadrant rules."""
        positions = []

        # FM Agent — Q1
        q1_metrics = self.catalog.list_by_quadrant(Quadrant.Q1_FM_OPEX.value)
        q1_ids = [m.metric_id for m in q1_metrics if m.metric_id in metric_inputs]
        positions.append(StakeholderPosition(
            agent_id="fm",
            agent_role="FM Operations Agent",
            quadrant_authority="Q1",
            non_negotiables=[
                Constraint(
                    agent_id="fm",
                    constraint_type="hard",
                    description="P1 response time ≤ 4 hours",
                    parameter_id="p_response_time_p1",
                    operator="lte",
                    value=4.0,
                    justification="SLA requirement for critical asset failures",
                ),
            ],
            preferences=[
                Constraint(
                    agent_id="fm",
                    constraint_type="soft",
                    description="Target 25-40% reactive WO reduction",
                    parameter_id="p_wo_reduction_pct",
                    operator="between",
                    value=0.25,
                    value_upper=0.40,
                    weight=0.8,
                    justification="Industry benchmark range (Jardine et al. 2006)",
                ),
            ],
            trade_bands=[
                TradeBand(
                    parameter_id="p_wo_reduction_pct",
                    min_acceptable=0.15,
                    max_acceptable=0.50,
                    preferred=0.30,
                ),
            ],
            validated_metric_ids=q1_ids,
            sign_off=True,
        ))

        # Finance Agent — Q2
        q2_metrics = self.catalog.list_by_quadrant(Quadrant.Q2_FINANCE_CAPEX.value)
        q2_ids = [m.metric_id for m in q2_metrics if m.metric_id in metric_inputs]
        capex_budget = metric_inputs.get("m_replacement_cycle", {}).get(
            "capex_budget", 500000
        )
        positions.append(StakeholderPosition(
            agent_id="finance",
            agent_role="Finance Agent",
            quadrant_authority="Q2",
            non_negotiables=[
                Constraint(
                    agent_id="finance",
                    constraint_type="hard",
                    description=f"Capex budget ceiling ${capex_budget:,.0f}",
                    parameter_id="p_capex_budget",
                    operator="lte",
                    value=capex_budget,
                    justification="Board-approved annual capex envelope",
                ),
                Constraint(
                    agent_id="finance",
                    constraint_type="hard",
                    description="Minimum hurdle rate 8%",
                    parameter_id="p_hurdle_rate",
                    operator="gte",
                    value=0.08,
                    justification="Corporate finance policy",
                ),
            ],
            preferences=[
                Constraint(
                    agent_id="finance",
                    constraint_type="soft",
                    description="Prefer discount rate 8-10%",
                    parameter_id="p_discount_rate",
                    operator="between",
                    value=0.08,
                    value_upper=0.10,
                    weight=0.7,
                    justification="WACC range for facilities investment",
                ),
            ],
            validated_metric_ids=q2_ids,
            sign_off=True,
        ))

        # Compliance Agent — Q3
        q3_metrics = self.catalog.list_by_quadrant(Quadrant.Q3_COMPLIANCE_RISK.value)
        q3_ids = [m.metric_id for m in q3_metrics if m.metric_id in metric_inputs]
        positions.append(StakeholderPosition(
            agent_id="compliance",
            agent_role="Compliance/Food Safety Agent",
            quadrant_authority="Q3",
            non_negotiables=[
                Constraint(
                    agent_id="compliance",
                    constraint_type="hard",
                    description="Temperature breach threshold cannot be relaxed",
                    metric_id="m_temp_breaches",
                    operator="lte",
                    value=0,
                    justification="FDA 21 CFR Part 110 / local health code",
                ),
                Constraint(
                    agent_id="compliance",
                    constraint_type="hard",
                    description="Continuous monitoring required for all cold chain assets",
                    parameter_id="p_monitoring_frequency",
                    operator="eq",
                    value=1.0,
                    justification="Regulatory compliance requirement",
                ),
            ],
            validated_metric_ids=q3_ids,
            sign_off=True,
        ))

        # Operations Agent
        positions.append(StakeholderPosition(
            agent_id="ops",
            agent_role="Operations Agent",
            quadrant_authority="cross",
            non_negotiables=[
                Constraint(
                    agent_id="ops",
                    constraint_type="hard",
                    description="Minimum system uptime 95%",
                    parameter_id="p_min_uptime",
                    operator="gte",
                    value=0.95,
                    justification="Store operations SLA",
                ),
            ],
            preferences=[
                Constraint(
                    agent_id="ops",
                    constraint_type="soft",
                    description="Prefer maintenance during off-peak hours (22:00-06:00)",
                    parameter_id="p_maintenance_window",
                    operator="eq",
                    value=1.0,
                    weight=0.6,
                    justification="Minimize store disruption",
                ),
            ],
            validated_metric_ids=[],
            sign_off=True,
        ))

        # ESG Agent — Q4
        q4_metrics = self.catalog.list_by_quadrant(Quadrant.Q4_CROSS_SILO.value)
        q4_ids = [m.metric_id for m in q4_metrics if m.metric_id in metric_inputs]
        positions.append(StakeholderPosition(
            agent_id="esg",
            agent_role="ESG/Sustainability Agent",
            quadrant_authority="Q4",
            preferences=[
                Constraint(
                    agent_id="esg",
                    constraint_type="soft",
                    description="Carbon price $30-$80/tCO2e",
                    parameter_id="p_carbon_price",
                    operator="between",
                    value=30.0,
                    value_upper=80.0,
                    weight=0.5,
                    justification="Voluntary carbon market range (2024)",
                ),
            ],
            trade_bands=[
                TradeBand(
                    parameter_id="p_energy_reduction_pct",
                    min_acceptable=0.05,
                    max_acceptable=0.25,
                    preferred=0.15,
                ),
            ],
            validated_metric_ids=q4_ids,
            sign_off=True,
        ))

        return positions

    # ═══════════════════════════════════════════════════════════════
    # Output Assembly
    # ═══════════════════════════════════════════════════════════════

    def _build_output(
        self,
        metric_inputs: Dict[str, Dict[str, Any]],
        constraints: Dict[str, Any],
        scenario_id: Optional[str],
        run_id: str,
        crewai_used: bool = False,
    ) -> DecisionCrewOutput:
        """Build DecisionCrewOutput from shared state after crew execution."""
        # Build cost stack if not already populated
        if not self._cost_stack_ref:
            cost_stack = self.aggregation.build_cost_stack(metric_inputs, scenario_id)
            self._cost_stack_ref = [cost_stack]
        else:
            cost_stack = self._cost_stack_ref[0]

        # Compute ROI if not already done
        impl_cost = constraints.get("implementation_cost", IMPLEMENTATION_COST)
        if not self._roi_ref:
            roi = self.roi_engine.compute(
                cost_stack, scenario_id=scenario_id or "",
                implementation_cost=impl_cost,
            )
            self._roi_ref = [roi.to_dict()]

        # Run negotiation if positions were collected
        negotiation_log = NegotiationLog()
        if self._positions:
            negotiation_log = self._negotiation.negotiate(self._positions)

        # Pareto optimization
        budget_constraints = BudgetConstraints(
            total_budget=constraints.get("total_budget", float("inf")),
            capex_budget=constraints.get("capex_budget", float("inf")),
            opex_budget=constraints.get("opex_budget", float("inf")),
            owner_budgets=constraints.get("owner_budgets", {}),
            min_confidence=constraints.get("min_confidence", 0),
        )
        stakeholder_constraints = self._negotiation.get_effective_constraints()
        pareto_options = self._pareto.generate_pareto_frontier(
            cost_stack, budget_constraints, stakeholder_constraints,
            implementation_cost=impl_cost,
        )
        recommended_id = self._pareto.recommend(pareto_options)

        # Narrative
        roi_data = self._roi_ref[0] if self._roi_ref else {}
        narrative = self._generate_deterministic_narrative_from_dict(
            roi_data, cost_stack, pareto_options
        )

        return DecisionCrewOutput(
            run_id=run_id,
            stakeholder_positions=self._positions,
            cost_lines_by_dimension=self._group_lines_by_dimension(cost_stack),
            unified_cost_stack=cost_stack.to_dict(),
            adjustments_applied=self.aggregation.get_adjustments(),
            consolidated_roi=roi_data,
            pareto_options=pareto_options,
            recommended_option_id=recommended_id,
            negotiation_log=negotiation_log,
            assumption_register=self._assumptions,
            board_narrative=narrative,
            lineage_summary=self._build_lineage_summary(cost_stack),
            agent_messages=list(self._messages),
            agent_count=get_agent_count(),
            task_count=13,
            crewai_used=crewai_used,
        )

    # ═══════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════

    def _build_tools(self, metric_inputs: Dict[str, Dict[str, Any]]) -> Dict[str, list]:
        """Build tool instances bound to shared state."""
        # Shared mutable refs for inter-agent state
        positions_store = self._positions
        assumption_store = self._assumptions

        common = [
            ReadParameterSetTool(self.params),
            ReadOwnershipMapTool(self.ownership),
            ReadMetricEvidenceTool(self.catalog, metric_inputs),
        ]

        stakeholder_tools = common + [
            SubmitStakeholderPositionTool(positions_store),
        ]

        dimension_tools = common + [
            RunTranslationTool(self.rules, self.ownership),
            WriteCostLineTool(self._cost_stack_ref),
            WriteAssumptionTool(assumption_store),
            ReadDependencyGraphTool(self.aggregation),
        ]

        governance_tools = common + [
            ReadCostLinesTool(self._cost_stack_ref),
            ReadDependencyGraphTool(self.aggregation),
            RunOptimizationTool(self.optimizer, self._cost_stack_ref),
            ReadROITool(self._roi_ref),
        ]

        orchestrator_tools = common + [
            ReadScenarioTool(self.scenarios),
            ReadCostLinesTool(self._cost_stack_ref),
            ReadROITool(self._roi_ref),
        ]

        return {
            "stakeholder": stakeholder_tools,
            "dimension": dimension_tools,
            "governance": governance_tools,
            "orchestrator": orchestrator_tools,
        }

    def _create_agents(self, tools: Dict[str, list]) -> Dict[str, Agent]:
        """Create all 13 agents with appropriate tool bindings."""
        return {
            "orchestrator": create_orchestrator(tools["orchestrator"]),
            "fm": create_fm_agent(tools["stakeholder"]),
            "finance": create_finance_agent(tools["stakeholder"]),
            "compliance": create_compliance_agent(tools["stakeholder"]),
            "ops": create_ops_agent(tools["stakeholder"]),
            "esg": create_esg_agent(tools["stakeholder"]),
            "opex_modeler": create_opex_modeler(tools["dimension"]),
            "capex_modeler": create_capex_modeler(tools["dimension"]),
            "risk_modeler": create_risk_modeler(tools["dimension"]),
            "strategic_modeler": create_strategic_modeler(tools["dimension"]),
            "reconciler": create_reconciliation_agent(tools["governance"]),
            "optimizer": create_optimizer_agent(tools["governance"]),
            "auditor": create_audit_narrator(tools["governance"]),
        }

    def _group_lines_by_dimension(self, cost_stack: CostStack) -> Dict[str, List[Dict[str, Any]]]:
        """Group cost lines by cost type dimension."""
        groups: Dict[str, List[Dict[str, Any]]] = {
            "opex": [], "capex": [], "risk": [], "strategic": [],
        }
        for line in cost_stack.lines:
            key = line.cost_type if line.cost_type in groups else "strategic"
            groups[key].append(line.to_dict())
        return groups

    def _collect_assumptions(self, cost_stack: CostStack) -> List[AssumptionRecord]:
        """Collect assumptions from cost stack lines + any manually recorded."""
        assumptions = list(self._assumptions)

        for line in cost_stack.lines:
            if line.is_assumption_based:
                for note in line.assumptions:
                    assumptions.append(AssumptionRecord(
                        description=note,
                        owner_agent="translation_engine",
                        justification="Default assumption from translation rule",
                        source="default",
                        metric_id=line.input_metric_ids[0] if line.input_metric_ids else None,
                    ))

        return assumptions

    def _build_lineage_summary(self, cost_stack: CostStack) -> Dict[str, Any]:
        """Build a lineage summary tracing metrics → rules → cost lines → ROI."""
        return {
            "metrics_used": list({
                mid for line in cost_stack.lines for mid in line.input_metric_ids
            }),
            "translation_rules_applied": list({
                line.calculation_formula_ref for line in cost_stack.lines
                if line.calculation_formula_ref
            }),
            "cost_lines_produced": len(cost_stack.lines),
            "adjustments_applied": len(self.aggregation.get_adjustments()),
            "dependency_edges": len(self.aggregation.get_dependency_graph()),
        }

    def _generate_deterministic_narrative(
        self,
        roi: ConsolidatedROI,
        cost_stack: CostStack,
        pareto_options: List[ParetoOption],
    ) -> str:
        """Generate board narrative from ConsolidatedROI object."""
        return self._generate_deterministic_narrative_from_dict(
            roi.to_dict(), cost_stack, pareto_options
        )

    def _generate_deterministic_narrative_from_dict(
        self,
        roi_data: Dict[str, Any],
        cost_stack: CostStack,
        pareto_options: List[ParetoOption],
    ) -> str:
        """Generate a deterministic board-ready narrative from ROI data."""
        total_savings = roi_data.get("total_savings", 0)
        savings_low = roi_data.get("savings_low", 0)
        savings_high = roi_data.get("savings_high", 0)
        npv = roi_data.get("npv", 0)
        payback = roi_data.get("payback_months")
        line_count = roi_data.get("line_count", 0)
        missing = roi_data.get("missing_data_count", 0)

        lines = [
            f"The ownership-aware decision analysis identified ${total_savings:,.0f}/year "
            f"in savings across {line_count} cost line items "
            f"(range: ${savings_low:,.0f} – ${savings_high:,.0f}).",
            "",
        ]

        if npv > 0:
            lines.append(f"Net present value over the analysis horizon: ${npv:,.0f}.")
        if payback:
            lines.append(f"Estimated payback period: {payback:.1f} months.")

        # Top savings by quadrant
        by_quadrant = roi_data.get("roi_by_quadrant", [])
        if by_quadrant:
            lines.append("")
            lines.append("Savings by quadrant:")
            for bq in by_quadrant[:4]:
                lines.append(
                    f"  • {bq.get('dimension_value', 'N/A')}: "
                    f"${bq.get('total_savings', 0):,.0f} "
                    f"(NPV: ${bq.get('npv', 0):,.0f})"
                )

        # Pareto options
        if pareto_options:
            lines.append("")
            lines.append(f"{len(pareto_options)} Pareto-optimal scenarios evaluated:")
            for opt in pareto_options[:4]:
                lines.append(
                    f"  • {opt.label}: NPV ${opt.npv:,.0f}, "
                    f"Risk score {opt.risk_score:.2f}"
                )

        # Data gaps
        if missing > 0:
            lines.append("")
            lines.append(
                f"Data gap: {missing} cost lines rely on default assumptions. "
                f"Improving data coverage for these items would narrow confidence bands."
            )

        # Cost of inaction
        lines.append("")
        lines.append(
            f"Cost of inaction: delaying 12 months foregoes an estimated "
            f"${total_savings:,.0f} in annual savings, with compounding effects "
            f"from deferred maintenance and continued compliance exposure."
        )

        return "\n".join(lines)
