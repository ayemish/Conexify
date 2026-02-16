"""
Agent Tools — BaseTool subclasses that wrap ownership module data structures.

All tools return structured JSON, never prose. Each tool is bound to a
specific ownership module component at construction time.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from shared.agents.crewai_base import BaseTool

from loweconex_platform.ownership.crew.schemas import (
    AssumptionRecord,
    StakeholderPosition,
    Constraint,
    TradeBand,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════════════════════════════

def _json(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════════
# 1. ReadParameterSetTool
# ═══════════════════════════════════════════════════════════════════

class ReadParameterSetTool(BaseTool):
    """Returns all resolved parameters for the current scope as JSON."""

    name: str = "read_parameter_set"
    description: str = (
        "Returns the full ParameterSet JSON with all resolved parameter values "
        "for the current scope (store/banner/region/global). Includes slider "
        "ranges, defaults, and active overrides."
    )

    def __init__(self, param_hierarchy):
        super().__init__()
        self._params = param_hierarchy

    def _run(self, store: str = "", banner: str = "", region: str = "") -> str:
        resolved = self._params.resolve_all(store=store, banner=banner, region=region)
        sliders = [d.to_dict() for d in self._params.list_slider_params()]
        return _json({"resolved_parameters": resolved, "slider_params": sliders})


# ═══════════════════════════════════════════════════════════════════
# 2. ReadOwnershipMapTool
# ═══════════════════════════════════════════════════════════════════

class ReadOwnershipMapTool(BaseTool):
    """Returns the full ownership map (metric → RACI + weights) as JSON."""

    name: str = "read_ownership_map"
    description: str = (
        "Returns the OwnershipMap JSON: metric_id → accountable owner, "
        "RACI roles, multi-owner weights, and org-level resolution."
    )

    def __init__(self, ownership_engine):
        super().__init__()
        self._ownership = ownership_engine

    def _run(self, metric_id: str = "") -> str:
        if metric_id:
            return _json(self._ownership.resolve(metric_id))
        return _json(self._ownership.resolve_all())


# ═══════════════════════════════════════════════════════════════════
# 3. ReadMetricEvidenceTool
# ═══════════════════════════════════════════════════════════════════

class ReadMetricEvidenceTool(BaseTool):
    """Returns metric definitions and input evidence as JSON."""

    name: str = "read_metric_evidence"
    description: str = (
        "Returns MetricEvidence[] JSON: metric definitions from the catalog "
        "combined with current input values. Filter by quadrant or owner."
    )

    def __init__(self, metric_catalog, metric_inputs: Dict[str, Dict[str, Any]]):
        super().__init__()
        self._catalog = metric_catalog
        self._inputs = metric_inputs

    def _run(self, quadrant: str = "", owner: str = "") -> str:
        if quadrant:
            metrics = self._catalog.list_by_quadrant(quadrant)
        elif owner:
            metrics = self._catalog.list_by_owner(owner)
        else:
            metrics = self._catalog.list_all()

        evidence = []
        for m in metrics:
            entry = m.to_dict()
            entry["current_inputs"] = self._inputs.get(m.metric_id, {})
            entry["has_inputs"] = bool(self._inputs.get(m.metric_id))
            evidence.append(entry)
        return _json({"metric_evidence": evidence, "count": len(evidence)})


# ═══════════════════════════════════════════════════════════════════
# 4. ReadCostLinesTool
# ═══════════════════════════════════════════════════════════════════

class ReadCostLinesTool(BaseTool):
    """Returns cost lines from the current cost stack, filterable."""

    name: str = "read_cost_lines"
    description: str = (
        "Returns CostLine[] JSON from the current cost stack. "
        "Filter by cost_type (opex/capex/risk/strategic), owner, or quadrant."
    )

    def __init__(self, cost_stack_ref: list):
        super().__init__()
        self._stack_ref = cost_stack_ref  # mutable list holding [CostStack]

    def _run(self, cost_type: str = "", owner: str = "", quadrant: str = "") -> str:
        if not self._stack_ref:
            return _json({"cost_lines": [], "count": 0})

        stack = self._stack_ref[0]
        lines = stack.lines

        if cost_type:
            lines = [l for l in lines if l.cost_type == cost_type]
        if owner:
            lines = [l for l in lines if owner in l.owner_roles]
        if quadrant:
            lines = [l for l in lines if l.quadrant == quadrant]

        return _json({
            "cost_lines": [l.to_dict() for l in lines],
            "count": len(lines),
            "total_amount": round(sum(l.amount for l in lines), 2),
            "total_npv": round(sum(l.npv for l in lines), 2),
        })


# ═══════════════════════════════════════════════════════════════════
# 5. ReadDependencyGraphTool
# ═══════════════════════════════════════════════════════════════════

class ReadDependencyGraphTool(BaseTool):
    """Returns the benefit dependency graph edges as JSON."""

    name: str = "read_dependency_graph"
    description: str = (
        "Returns dependency graph edges showing metric overlap relationships "
        "used for anti-double-counting allocation."
    )

    def __init__(self, aggregation_engine):
        super().__init__()
        self._aggregation = aggregation_engine

    def _run(self) -> str:
        edges = self._aggregation.get_dependency_graph()
        return _json({"edges": edges, "count": len(edges)})


# ═══════════════════════════════════════════════════════════════════
# 6. WriteCostLineTool
# ═══════════════════════════════════════════════════════════════════

class WriteCostLineTool(BaseTool):
    """Appends a CostLineItem to the shared cost stack."""

    name: str = "write_cost_line"
    description: str = (
        "Appends a new CostLineItem to the shared cost stack. "
        "Provide: name, cost_type, amount, amount_low, amount_high, "
        "owner_roles, quadrant, confidence, input_metric_ids."
    )

    def __init__(self, cost_stack_ref: list):
        super().__init__()
        self._stack_ref = cost_stack_ref

    def _run(self, line_json: str = "") -> str:
        from loweconex_platform.ownership.cost_stack import CostLineItem
        try:
            data = json.loads(line_json) if isinstance(line_json, str) else line_json
        except (json.JSONDecodeError, TypeError):
            return _json({"error": "Invalid JSON for cost line"})

        if not self._stack_ref:
            from loweconex_platform.ownership.cost_stack import CostStack
            self._stack_ref.append(CostStack())

        line = CostLineItem(
            name=data.get("name", ""),
            description=data.get("description", ""),
            cost_type=data.get("cost_type", "opex"),
            owner_roles=data.get("owner_roles", []),
            amount=data.get("amount", 0.0),
            amount_low=data.get("amount_low", 0.0),
            amount_high=data.get("amount_high", 0.0),
            confidence=data.get("confidence", 0.5),
            input_metric_ids=data.get("input_metric_ids", []),
            assumptions=data.get("assumptions", []),
            quadrant=data.get("quadrant", ""),
            is_savings=data.get("is_savings", data.get("amount", 0) > 0),
        )
        self._stack_ref[0].add_line(line)
        return _json({"line_id": line.line_id, "status": "added"})


# ═══════════════════════════════════════════════════════════════════
# 7. WriteAssumptionTool
# ═══════════════════════════════════════════════════════════════════

class WriteAssumptionTool(BaseTool):
    """Records an assumption in the shared assumption register."""

    name: str = "write_assumption"
    description: str = (
        "Records an assumption with owner, justification, impact rank, "
        "and linked parameter/metric. Used by all agents to declare "
        "explicit assumptions for auditability."
    )

    def __init__(self, assumption_register: List[AssumptionRecord]):
        super().__init__()
        self._register = assumption_register

    def _run(self, assumption_json: str = "") -> str:
        try:
            data = json.loads(assumption_json) if isinstance(assumption_json, str) else assumption_json
        except (json.JSONDecodeError, TypeError):
            return _json({"error": "Invalid JSON for assumption"})

        record = AssumptionRecord(
            description=data.get("description", ""),
            owner_agent=data.get("owner_agent", ""),
            justification=data.get("justification", ""),
            impact_rank=data.get("impact_rank", 0),
            parameter_id=data.get("parameter_id"),
            metric_id=data.get("metric_id"),
            value=data.get("value"),
            source=data.get("source", "model"),
        )
        self._register.append(record)
        return _json({"assumption_id": record.assumption_id, "status": "recorded"})


# ═══════════════════════════════════════════════════════════════════
# 8. ReadScenarioTool
# ═══════════════════════════════════════════════════════════════════

class ReadScenarioTool(BaseTool):
    """Returns scenario details with resolved parameters."""

    name: str = "read_scenario"
    description: str = (
        "Returns Scenario JSON with resolved parameters for a given "
        "scenario_id. Lists parameter overrides and constraints."
    )

    def __init__(self, scenario_manager):
        super().__init__()
        self._scenarios = scenario_manager

    def _run(self, scenario_id: str = "") -> str:
        if scenario_id:
            scenario = self._scenarios.get(scenario_id)
            if scenario:
                return _json(scenario.to_dict())
            return _json({"error": f"Scenario {scenario_id} not found"})
        scenarios = self._scenarios.list_all()
        return _json({"scenarios": [s.to_dict() for s in scenarios], "count": len(scenarios)})


# ═══════════════════════════════════════════════════════════════════
# 9. RunTranslationTool
# ═══════════════════════════════════════════════════════════════════

class RunTranslationTool(BaseTool):
    """Evaluates translation rules for a metric and returns cost lines."""

    name: str = "run_translation"
    description: str = (
        "Evaluates all translation rules for a given metric_id with "
        "provided inputs and owner_roles. Returns CostLineItem[] JSON."
    )

    def __init__(self, rules_library, ownership_engine):
        super().__init__()
        self._rules = rules_library
        self._ownership = ownership_engine

    def _run(self, metric_id: str = "", inputs_json: str = "") -> str:
        try:
            inputs = json.loads(inputs_json) if isinstance(inputs_json, str) else inputs_json
        except (json.JSONDecodeError, TypeError):
            inputs = {}

        ownership = self._ownership.resolve(metric_id)
        owner_roles = [ownership.get("accountable", "fm")]
        if ownership.get("responsible"):
            owner_roles.append(ownership["responsible"])

        lines = self._rules.evaluate_all_for_metric(metric_id, inputs, owner_roles)
        return _json({
            "metric_id": metric_id,
            "cost_lines": [l.to_dict() for l in lines],
            "count": len(lines),
        })


# ═══════════════════════════════════════════════════════════════════
# 10. RunOptimizationTool
# ═══════════════════════════════════════════════════════════════════

class RunOptimizationTool(BaseTool):
    """Runs constraint-aware optimization on the cost stack."""

    name: str = "run_optimization"
    description: str = (
        "Runs constraint-aware optimization on the current cost stack. "
        "Provide constraints as JSON: total_budget, capex_budget, "
        "opex_budget, owner_budgets, min_confidence."
    )

    def __init__(self, optimizer, cost_stack_ref: list):
        super().__init__()
        self._optimizer = optimizer
        self._stack_ref = cost_stack_ref

    def _run(self, constraints_json: str = "{}") -> str:
        from loweconex_platform.ownership.constraint_optimizer import BudgetConstraints
        try:
            data = json.loads(constraints_json) if isinstance(constraints_json, str) else constraints_json
        except (json.JSONDecodeError, TypeError):
            data = {}

        if not self._stack_ref:
            return _json({"error": "No cost stack available for optimization"})

        constraints = BudgetConstraints(
            total_budget=data.get("total_budget", float("inf")),
            capex_budget=data.get("capex_budget", float("inf")),
            opex_budget=data.get("opex_budget", float("inf")),
            owner_budgets=data.get("owner_budgets", {}),
            min_confidence=data.get("min_confidence", 0),
        )
        result = self._optimizer.optimize(self._stack_ref[0], constraints)
        return _json(result.to_dict())


# ═══════════════════════════════════════════════════════════════════
# 11. ReadROITool
# ═══════════════════════════════════════════════════════════════════

class ReadROITool(BaseTool):
    """Returns the consolidated ROI report as JSON."""

    name: str = "read_roi"
    description: str = (
        "Returns the consolidated ROI report JSON with breakdowns by "
        "owner, quadrant, cost type, year-by-year cashflow, IRR, NPV, payback."
    )

    def __init__(self, roi_ref: list):
        super().__init__()
        self._roi_ref = roi_ref  # mutable list holding [ConsolidatedROI dict]

    def _run(self) -> str:
        if self._roi_ref:
            return _json(self._roi_ref[0])
        return _json({"error": "No ROI computed yet"})


# ═══════════════════════════════════════════════════════════════════
# 12. SubmitStakeholderPositionTool
# ═══════════════════════════════════════════════════════════════════

class SubmitStakeholderPositionTool(BaseTool):
    """Records a stakeholder agent's negotiation position."""

    name: str = "submit_stakeholder_position"
    description: str = (
        "Submit this agent's negotiation position: non-negotiables (hard constraints), "
        "preferences (soft constraints with weights), trade bands, and sign-off."
    )

    def __init__(self, positions_store: List[StakeholderPosition]):
        super().__init__()
        self._store = positions_store

    def _run(self, position_json: str = "") -> str:
        try:
            data = json.loads(position_json) if isinstance(position_json, str) else position_json
        except (json.JSONDecodeError, TypeError):
            return _json({"error": "Invalid JSON for position"})

        non_negotiables = [
            Constraint(
                agent_id=data.get("agent_id", ""),
                constraint_type="hard",
                description=c.get("description", ""),
                parameter_id=c.get("parameter_id"),
                metric_id=c.get("metric_id"),
                operator=c.get("operator", "lte"),
                value=c.get("value", 0),
                justification=c.get("justification", ""),
            )
            for c in data.get("non_negotiables", [])
        ]

        preferences = [
            Constraint(
                agent_id=data.get("agent_id", ""),
                constraint_type="soft",
                description=c.get("description", ""),
                parameter_id=c.get("parameter_id"),
                metric_id=c.get("metric_id"),
                operator=c.get("operator", "lte"),
                value=c.get("value", 0),
                weight=c.get("weight", 0.5),
                justification=c.get("justification", ""),
            )
            for c in data.get("preferences", [])
        ]

        trade_bands = [
            TradeBand(
                parameter_id=tb.get("parameter_id", ""),
                min_acceptable=tb.get("min_acceptable", 0),
                max_acceptable=tb.get("max_acceptable", 0),
                preferred=tb.get("preferred", 0),
            )
            for tb in data.get("trade_bands", [])
        ]

        position = StakeholderPosition(
            agent_id=data.get("agent_id", ""),
            agent_role=data.get("agent_role", ""),
            quadrant_authority=data.get("quadrant_authority", ""),
            non_negotiables=non_negotiables,
            preferences=preferences,
            trade_bands=trade_bands,
            validated_metric_ids=data.get("validated_metric_ids", []),
            objections=data.get("objections", []),
            sign_off=data.get("sign_off", False),
        )
        self._store.append(position)
        return _json({"status": "position_recorded", "agent_id": position.agent_id})
