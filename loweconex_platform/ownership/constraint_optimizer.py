"""
Constraint-Aware Optimizer — selects best actions under per-owner
budget constraints to maximize consolidated ROI.

Extends the existing PortfolioOptimizer and KnapsackOptimizer patterns
with owner-aware budget constraints and trade-off reporting.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from loweconex_platform.ownership.cost_stack import CostLineItem, CostStack, CostType
from loweconex_platform.ownership.ownership_model import OwnerRole

logger = logging.getLogger(__name__)


@dataclass
class BudgetConstraints:
    """Per-owner and per-type budget constraints."""
    total_budget: float = float("inf")
    capex_budget: float = float("inf")
    opex_budget: float = float("inf")

    # Per-owner budgets (optional)
    owner_budgets: Dict[str, float] = field(default_factory=dict)

    # Minimum confidence threshold
    min_confidence: float = 0.0

    # Compliance-required lines always included
    compliance_required: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_budget": self.total_budget,
            "capex_budget": self.capex_budget,
            "opex_budget": self.opex_budget,
            "owner_budgets": self.owner_budgets,
            "min_confidence": self.min_confidence,
            "compliance_required": self.compliance_required,
        }


@dataclass
class OptimizationResult:
    """Result of constraint-aware optimization."""
    selected_lines: List[CostLineItem] = field(default_factory=list)
    rejected_lines: List[Dict[str, Any]] = field(default_factory=list)
    total_selected_cost: float = 0.0
    total_selected_savings: float = 0.0
    total_npv: float = 0.0
    budget_utilization: Dict[str, float] = field(default_factory=dict)
    trade_offs_by_owner: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    optimization_method: str = "greedy"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_count": len(self.selected_lines),
            "rejected_count": len(self.rejected_lines),
            "total_selected_cost": round(self.total_selected_cost, 2),
            "total_selected_savings": round(self.total_selected_savings, 2),
            "total_npv": round(self.total_npv, 2),
            "budget_utilization": self.budget_utilization,
            "trade_offs_by_owner": self.trade_offs_by_owner,
            "optimization_method": self.optimization_method,
            "selected_lines": [l.to_dict() for l in self.selected_lines],
            "rejected_lines": self.rejected_lines,
        }


class ConstraintOptimizer:
    """
    Selects the best set of cost line items (actions) under budget
    constraints to maximize consolidated ROI.
    """

    def optimize(
        self,
        cost_stack: CostStack,
        constraints: BudgetConstraints,
    ) -> OptimizationResult:
        """
        Greedy optimization: sort by NPV efficiency, select within constraints.
        Compliance lines are always included first.
        """
        result = OptimizationResult(optimization_method="greedy_npv_efficiency")

        lines = cost_stack.lines
        if not lines:
            return result

        # Separate compliance-required (Q3 risk) and optional lines
        compliance_lines = []
        optional_lines = []
        for line in lines:
            if line.confidence < constraints.min_confidence:
                result.rejected_lines.append({
                    "line_id": line.line_id,
                    "name": line.name,
                    "reason": f"confidence {line.confidence:.2f} < min {constraints.min_confidence:.2f}",
                })
                continue

            if constraints.compliance_required and line.quadrant == "Q3":
                compliance_lines.append(line)
            else:
                optional_lines.append(line)

        # Sort optional by NPV efficiency (NPV / cost)
        for line in optional_lines:
            cost_val = abs(line.amount) if not line.is_savings else 0
            line._efficiency = line.npv / max(cost_val, 1.0)
        optional_lines.sort(key=lambda l: l._efficiency, reverse=True)

        # Track remaining budgets
        remaining = {
            "total": constraints.total_budget,
            "capex": constraints.capex_budget,
            "opex": constraints.opex_budget,
        }
        owner_remaining = dict(constraints.owner_budgets)

        # Select compliance lines first
        for line in compliance_lines:
            if self._fits_budget(line, remaining, owner_remaining):
                self._consume_budget(line, remaining, owner_remaining)
                result.selected_lines.append(line)
            else:
                result.rejected_lines.append({
                    "line_id": line.line_id,
                    "name": line.name,
                    "reason": "exceeds budget (compliance line)",
                })

        # Fill with optional lines
        for line in optional_lines:
            if self._fits_budget(line, remaining, owner_remaining):
                self._consume_budget(line, remaining, owner_remaining)
                result.selected_lines.append(line)
            else:
                result.rejected_lines.append({
                    "line_id": line.line_id,
                    "name": line.name,
                    "reason": "exceeds budget",
                })

        # Compute totals
        result.total_selected_savings = sum(
            l.amount for l in result.selected_lines if l.is_savings
        )
        result.total_selected_cost = sum(
            abs(l.amount) for l in result.selected_lines if not l.is_savings
        )
        result.total_npv = sum(l.npv for l in result.selected_lines)

        # Budget utilization
        result.budget_utilization = {
            "total": self._utilization(constraints.total_budget, remaining["total"]),
            "capex": self._utilization(constraints.capex_budget, remaining["capex"]),
            "opex": self._utilization(constraints.opex_budget, remaining["opex"]),
        }
        for owner, budget in constraints.owner_budgets.items():
            used = budget - owner_remaining.get(owner, budget)
            result.budget_utilization[f"owner_{owner}"] = round(used / budget * 100, 1) if budget > 0 else 0

        # Trade-offs by owner
        result.trade_offs_by_owner = self._compute_trade_offs(result, constraints)

        return result

    def simulate_budget_cut(
        self,
        cost_stack: CostStack,
        current_constraints: BudgetConstraints,
        cut_pct: float = 0.50,
        cut_type: str = "opex",
    ) -> Dict[str, Any]:
        """
        Simulate a budget cut and return recommended reallocation.

        Args:
            cost_stack: Current cost stack
            current_constraints: Current constraints
            cut_pct: Fraction to cut (0.5 = 50% cut)
            cut_type: "opex", "capex", or "total"
        """
        import copy
        cut_constraints = copy.deepcopy(current_constraints)

        if cut_type == "opex":
            cut_constraints.opex_budget *= (1 - cut_pct)
        elif cut_type == "capex":
            cut_constraints.capex_budget *= (1 - cut_pct)
        else:
            cut_constraints.total_budget *= (1 - cut_pct)

        # Run optimization with cut budget
        before = self.optimize(cost_stack, current_constraints)
        after = self.optimize(cost_stack, cut_constraints)

        # Find what was dropped
        selected_before = {l.line_id for l in before.selected_lines}
        selected_after = {l.line_id for l in after.selected_lines}
        dropped = selected_before - selected_after

        dropped_lines = [l for l in before.selected_lines if l.line_id in dropped]

        return {
            "cut_type": cut_type,
            "cut_pct": cut_pct,
            "before_npv": round(before.total_npv, 2),
            "after_npv": round(after.total_npv, 2),
            "npv_impact": round(after.total_npv - before.total_npv, 2),
            "lines_dropped": len(dropped_lines),
            "dropped_details": [
                {"name": l.name, "npv": l.npv, "owner": l.owner_roles, "quadrant": l.quadrant}
                for l in dropped_lines
            ],
            "recommendation": self._generate_cut_recommendation(dropped_lines, cut_pct, cut_type),
        }

    # ── Helpers ─────────────────────────────────────────────────────

    def _fits_budget(
        self,
        line: CostLineItem,
        remaining: Dict[str, float],
        owner_remaining: Dict[str, float],
    ) -> bool:
        cost = abs(line.amount) if not line.is_savings else 0
        if cost <= 0:
            return True

        if cost > remaining["total"]:
            return False

        if line.cost_type == CostType.CAPEX.value and cost > remaining["capex"]:
            return False
        if line.cost_type == CostType.OPEX.value and cost > remaining["opex"]:
            return False

        # Check per-owner budgets
        for owner in line.owner_roles:
            if owner in owner_remaining:
                weight = 1.0 / len(line.owner_roles)
                if cost * weight > owner_remaining[owner]:
                    return False

        return True

    def _consume_budget(
        self,
        line: CostLineItem,
        remaining: Dict[str, float],
        owner_remaining: Dict[str, float],
    ):
        cost = abs(line.amount) if not line.is_savings else 0
        if cost <= 0:
            return

        remaining["total"] -= cost
        if line.cost_type == CostType.CAPEX.value:
            remaining["capex"] -= cost
        elif line.cost_type == CostType.OPEX.value:
            remaining["opex"] -= cost

        for owner in line.owner_roles:
            if owner in owner_remaining:
                weight = 1.0 / len(line.owner_roles)
                owner_remaining[owner] -= cost * weight

    @staticmethod
    def _utilization(budget: float, remaining: float) -> float:
        if budget == float("inf") or budget <= 0:
            return 0.0
        return round((budget - remaining) / budget * 100, 1)

    def _compute_trade_offs(
        self,
        result: OptimizationResult,
        constraints: BudgetConstraints,
    ) -> Dict[str, Dict[str, Any]]:
        """Compute what each owner gains/loses from the optimization."""
        trade_offs: Dict[str, Dict[str, Any]] = {}

        for line in result.selected_lines:
            for owner in line.owner_roles:
                if owner not in trade_offs:
                    trade_offs[owner] = {"selected_npv": 0, "selected_count": 0, "rejected_npv": 0, "rejected_count": 0}
                weight = 1.0 / len(line.owner_roles)
                trade_offs[owner]["selected_npv"] += line.npv * weight
                trade_offs[owner]["selected_count"] += 1

        for rejected in result.rejected_lines:
            line_id = rejected.get("line_id", "")
            # Find the original line to get owner info
            # (rejected lines don't carry full data, so this is approximate)

        return trade_offs

    @staticmethod
    def _generate_cut_recommendation(
        dropped: List[CostLineItem],
        cut_pct: float,
        cut_type: str,
    ) -> str:
        if not dropped:
            return f"A {cut_pct*100:.0f}% {cut_type} budget cut can be absorbed with no impact on selected initiatives."

        q3_dropped = [l for l in dropped if l.quadrant == "Q3"]
        if q3_dropped:
            return (
                f"WARNING: A {cut_pct*100:.0f}% {cut_type} cut drops {len(dropped)} lines "
                f"including {len(q3_dropped)} compliance-related items. "
                f"Recommend protecting Q3 compliance lines and cutting lower-NPV Q1/Q4 items instead."
            )

        return (
            f"A {cut_pct*100:.0f}% {cut_type} cut drops {len(dropped)} lines. "
            f"Recommend prioritizing highest-NPV items and deferring low-confidence initiatives."
        )
