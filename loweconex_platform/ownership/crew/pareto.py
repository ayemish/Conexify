"""
Multi-Objective Optimizer — extends ConstraintOptimizer with selectable
objective functions and Pareto frontier generation.

Objective Functions:
  1. Max consolidated NPV (default)
  2. Max risk-adjusted ROI (penalize low confidence)
  3. Min compliance risk subject to budget
  4. Min Opex subject to uptime constraint
  5. Multi-objective Pareto frontier (3-5 non-dominated solutions)
"""

from __future__ import annotations

import copy
import logging
import uuid
from typing import Any, Dict, List, Optional

from loweconex_platform.ownership.cost_stack import CostLineItem, CostStack, CostType
from loweconex_platform.ownership.constraint_optimizer import (
    BudgetConstraints,
    ConstraintOptimizer,
    OptimizationResult,
)
from loweconex_platform.ownership.crew.schemas import ParetoOption
from loweconex_platform.ownership.financial_constants import IMPLEMENTATION_COST

logger = logging.getLogger(__name__)


class ObjectiveFunction:
    """Defines a named objective function for optimization."""

    MAX_NPV = "max_npv"
    MAX_RISK_ADJUSTED_ROI = "max_risk_adjusted_roi"
    MIN_COMPLIANCE_RISK = "min_compliance_risk"
    MIN_OPEX = "min_opex"

    ALL = [MAX_NPV, MAX_RISK_ADJUSTED_ROI, MIN_COMPLIANCE_RISK, MIN_OPEX]

    LABELS = {
        MAX_NPV: "Max Consolidated NPV",
        MAX_RISK_ADJUSTED_ROI: "Max Risk-Adjusted ROI",
        MIN_COMPLIANCE_RISK: "Min Compliance Risk",
        MIN_OPEX: "Min Opex (Budget Saver)",
    }


class ParetoOptimizer:
    """
    Generates 3-5 Pareto-optimal solutions by running the ConstraintOptimizer
    with different objective functions and constraint variations.
    """

    def __init__(self, base_optimizer: Optional[ConstraintOptimizer] = None):
        self._optimizer = base_optimizer or ConstraintOptimizer()

    def generate_pareto_frontier(
        self,
        cost_stack: CostStack,
        constraints: BudgetConstraints,
        stakeholder_constraints: Optional[Dict[str, Any]] = None,
        implementation_cost: float = IMPLEMENTATION_COST,
    ) -> List[ParetoOption]:
        """
        Generate Pareto-optimal options by running multiple objective functions.

        Args:
            cost_stack: The reconciled cost stack.
            constraints: Base budget constraints.
            stakeholder_constraints: Hard/soft constraints from negotiation.
            implementation_cost: Upfront platform deployment cost deducted from NPV.

        Returns:
            3-5 ParetoOption objects representing non-dominated solutions.
        """
        self._impl_cost = implementation_cost
        options: List[ParetoOption] = []

        # Option 1: Max NPV (default greedy)
        opt1 = self._run_max_npv(cost_stack, constraints)
        options.append(opt1)

        # Option 2: Max Risk-Adjusted ROI
        opt2 = self._run_risk_adjusted(cost_stack, constraints)
        options.append(opt2)

        # Option 3: Min Compliance Risk
        opt3 = self._run_min_compliance_risk(cost_stack, constraints)
        options.append(opt3)

        # Option 4: Min Opex (budget saver)
        opt4 = self._run_min_opex(cost_stack, constraints)
        options.append(opt4)

        # Remove dominated options
        non_dominated = self._filter_dominated(options)

        # Ensure at least 3 options
        if len(non_dominated) < 3:
            non_dominated = options[:4]

        # Score stakeholder utility for each option
        if stakeholder_constraints:
            for opt in non_dominated:
                opt.stakeholder_utility_scores = self._score_stakeholder_utility(
                    opt, stakeholder_constraints
                )

        return non_dominated

    def recommend(self, options: List[ParetoOption]) -> str:
        """Return the option_id of the recommended option (highest NPV among non-dominated)."""
        if not options:
            return ""
        best = max(options, key=lambda o: o.npv)
        return best.option_id

    # ── Objective 1: Max NPV ────────────────────────────────────

    def _run_max_npv(
        self, cost_stack: CostStack, constraints: BudgetConstraints
    ) -> ParetoOption:
        """Standard greedy NPV maximization."""
        result = self._optimizer.optimize(cost_stack, constraints)
        return self._result_to_option(
            result, ObjectiveFunction.MAX_NPV,
            ObjectiveFunction.LABELS[ObjectiveFunction.MAX_NPV],
            cost_stack,
        )

    # ── Objective 2: Risk-Adjusted ROI ──────────────────────────

    def _run_risk_adjusted(
        self, cost_stack: CostStack, constraints: BudgetConstraints
    ) -> ParetoOption:
        """Maximize NPV * confidence (penalize uncertain lines)."""
        # Create a modified stack where amounts are confidence-weighted
        adjusted_stack = CostStack(scenario_id=cost_stack.scenario_id)
        for line in cost_stack.lines:
            adjusted_line = copy.deepcopy(line)
            adjusted_line.amount = line.amount * line.confidence
            adjusted_line.amount_low = line.amount_low * line.confidence
            adjusted_line.amount_high = line.amount_high * line.confidence
            adjusted_stack.add_line(adjusted_line)

        result = self._optimizer.optimize(adjusted_stack, constraints)

        # But report actual amounts from original lines
        original_ids = {l.line_id for l in result.selected_lines}
        actual_savings = sum(
            l.amount for l in cost_stack.lines
            if l.line_id in original_ids and l.is_savings
        )
        actual_npv = sum(
            l.npv for l in cost_stack.lines if l.line_id in original_ids
        )

        option = self._result_to_option(
            result, ObjectiveFunction.MAX_RISK_ADJUSTED_ROI,
            ObjectiveFunction.LABELS[ObjectiveFunction.MAX_RISK_ADJUSTED_ROI],
            cost_stack,
        )
        option.total_savings = actual_savings
        option.npv = actual_npv - self._impl_cost

        # Risk score = avg confidence of selected lines
        confs = [l.confidence for l in cost_stack.lines if l.line_id in original_ids]
        option.risk_score = 1.0 - (sum(confs) / len(confs)) if confs else 1.0

        return option

    # ── Objective 3: Min Compliance Risk ────────────────────────

    def _run_min_compliance_risk(
        self, cost_stack: CostStack, constraints: BudgetConstraints
    ) -> ParetoOption:
        """Prioritize Q3 compliance lines first, then fill with highest NPV."""
        # Create constraints that heavily prioritize compliance
        compliance_constraints = copy.deepcopy(constraints)
        compliance_constraints.compliance_required = True
        compliance_constraints.min_confidence = 0.0  # Include all compliance lines

        result = self._optimizer.optimize(cost_stack, compliance_constraints)

        option = self._result_to_option(
            result, ObjectiveFunction.MIN_COMPLIANCE_RISK,
            ObjectiveFunction.LABELS[ObjectiveFunction.MIN_COMPLIANCE_RISK],
            cost_stack,
        )

        # Compute compliance gap
        q3_total = sum(
            l.amount for l in cost_stack.lines if l.quadrant == "Q3"
        )
        q3_selected = sum(
            l.amount for l in result.selected_lines if l.quadrant == "Q3"
        )
        option.compliance_gap = max(0, q3_total - q3_selected)

        return option

    # ── Objective 4: Min Opex ───────────────────────────────────

    def _run_min_opex(
        self, cost_stack: CostStack, constraints: BudgetConstraints
    ) -> ParetoOption:
        """Minimize opex spend: select only compliance + highest-ROI items."""
        tight_constraints = copy.deepcopy(constraints)
        # Cut opex budget by 50% to force selection of only highest-value items
        if tight_constraints.opex_budget < float("inf"):
            tight_constraints.opex_budget *= 0.5
        else:
            # Estimate opex total and set to 50%
            opex_total = sum(
                abs(l.amount) for l in cost_stack.lines
                if l.cost_type == CostType.OPEX.value and not l.is_savings
            )
            if opex_total > 0:
                tight_constraints.opex_budget = opex_total * 0.5

        # Also raise confidence threshold to exclude low-confidence items
        tight_constraints.min_confidence = max(constraints.min_confidence, 0.5)

        result = self._optimizer.optimize(cost_stack, tight_constraints)

        return self._result_to_option(
            result, ObjectiveFunction.MIN_OPEX,
            ObjectiveFunction.LABELS[ObjectiveFunction.MIN_OPEX],
            cost_stack,
        )

    # ── Helpers ─────────────────────────────────────────────────

    def _result_to_option(
        self,
        result: OptimizationResult,
        objective: str,
        label: str,
        cost_stack: CostStack,
    ) -> ParetoOption:
        """Convert an OptimizationResult to a ParetoOption."""
        total_savings = result.total_selected_savings
        total_cost = result.total_selected_cost
        roi_pct = (
            (total_savings - total_cost) / total_cost * 100
            if total_cost > 0 else (float("inf") if total_savings > 0 else 0)
        )

        confs = [l.confidence for l in result.selected_lines] if result.selected_lines else [0]
        risk_score = 1.0 - (sum(confs) / len(confs))

        return ParetoOption(
            label=label,
            objective_function=objective,
            npv=round(result.total_npv - self._impl_cost, 2),
            roi_pct=round(min(roi_pct, 999.9), 1),
            risk_score=round(risk_score, 3),
            compliance_gap=0.0,
            total_cost=round(total_cost, 2),
            total_savings=round(total_savings, 2),
            selected_line_ids=[l.line_id for l in result.selected_lines],
            budget_utilization=result.budget_utilization,
        )

    def _filter_dominated(self, options: List[ParetoOption]) -> List[ParetoOption]:
        """
        Remove dominated options from the set.

        An option is dominated if another option is better on ALL objectives
        (higher NPV, lower risk, lower compliance gap).
        """
        non_dominated = []

        for i, opt_a in enumerate(options):
            dominated = False
            for j, opt_b in enumerate(options):
                if i == j:
                    continue
                if (opt_b.npv >= opt_a.npv
                        and opt_b.risk_score <= opt_a.risk_score
                        and opt_b.compliance_gap <= opt_a.compliance_gap
                        and (opt_b.npv > opt_a.npv
                             or opt_b.risk_score < opt_a.risk_score
                             or opt_b.compliance_gap < opt_a.compliance_gap)):
                    dominated = True
                    break
            if not dominated:
                non_dominated.append(opt_a)

        return non_dominated

    def _score_stakeholder_utility(
        self,
        option: ParetoOption,
        stakeholder_constraints: Dict[str, Any],
    ) -> Dict[str, float]:
        """
        Score how well an option satisfies each stakeholder's preferences.

        Returns: {agent_id: utility_score (0-1)}
        """
        utilities: Dict[str, float] = {}
        soft_prefs = stakeholder_constraints.get("soft_preferences", {})

        # Simple scoring: fraction of soft preferences satisfied
        agent_prefs: Dict[str, List] = {}
        for param_key, prefs in soft_prefs.items():
            for pref in prefs:
                agent_id = pref.get("agent", "")
                if agent_id not in agent_prefs:
                    agent_prefs[agent_id] = []
                agent_prefs[agent_id].append(pref)

        for agent_id, prefs in agent_prefs.items():
            if not prefs:
                utilities[agent_id] = 1.0
                continue
            # For now, give base utility based on NPV and compliance
            base_utility = min(1.0, option.npv / max(option.total_savings, 1.0))
            compliance_bonus = 0.2 if option.compliance_gap == 0 else 0.0
            utilities[agent_id] = round(min(1.0, base_utility + compliance_bonus), 3)

        return utilities
