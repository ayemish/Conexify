"""
Portfolio Optimizer — selects best actions under constraints.

Supports:
1. Greedy portfolio optimizer (fast, explainable)
2. MILP/constraint solver integration (optional) for budget/coverage constraints

Objective: maximize NPV and/or minimize Payback_months subject to
risk/compliance constraints.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class OptimizationAction:
    """A candidate action for the portfolio optimizer."""
    action_id: str
    title: str
    category: str  # "opex", "capex", "policy"
    asset_ids: List[str] = field(default_factory=list)
    location_ids: List[str] = field(default_factory=list)
    kpi_sources: List[str] = field(default_factory=list)

    # Economics
    cost: float = 0.0
    annual_savings: float = 0.0
    npv: float = 0.0
    payback_months: Optional[float] = None
    confidence: float = 0.0

    # Constraints
    requires_capex: bool = False
    compliance_required: bool = False
    risk_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "title": self.title,
            "category": self.category,
            "asset_ids": self.asset_ids,
            "location_ids": self.location_ids,
            "kpi_sources": self.kpi_sources,
            "cost": self.cost,
            "annual_savings": self.annual_savings,
            "npv": self.npv,
            "payback_months": self.payback_months,
            "confidence": self.confidence,
            "requires_capex": self.requires_capex,
            "compliance_required": self.compliance_required,
            "risk_score": self.risk_score,
        }


@dataclass
class OptimizationConstraints:
    """Constraints for portfolio optimization."""
    total_budget: float = float("inf")
    capex_budget: float = float("inf")
    opex_budget: float = float("inf")
    max_actions: int = 1000
    min_confidence: float = 0.0
    required_compliance_actions: bool = True
    max_risk_score: float = 1.0
    min_npv: float = 0.0


@dataclass
class OptimizationResult:
    """Result of portfolio optimization."""
    selected_actions: List[OptimizationAction] = field(default_factory=list)
    rejected_actions: List[Dict[str, Any]] = field(default_factory=list)
    total_cost: float = 0.0
    total_annual_savings: float = 0.0
    total_npv: float = 0.0
    portfolio_payback_months: Optional[float] = None
    budget_utilization: float = 0.0
    optimization_method: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_actions": [a.to_dict() for a in self.selected_actions],
            "rejected_actions": self.rejected_actions,
            "total_cost": self.total_cost,
            "total_annual_savings": self.total_annual_savings,
            "total_npv": self.total_npv,
            "portfolio_payback_months": self.portfolio_payback_months,
            "budget_utilization": self.budget_utilization,
            "optimization_method": self.optimization_method,
            "selected_count": len(self.selected_actions),
        }


class PortfolioOptimizer:
    """
    Selects the best set of actions from KPI recommendations
    subject to budget and risk constraints.
    """

    def optimize_greedy(
        self,
        actions: List[OptimizationAction],
        constraints: OptimizationConstraints,
    ) -> OptimizationResult:
        """
        Greedy optimizer: sort by NPV/cost ratio, select top actions
        within budget. Fast and explainable.
        """
        result = OptimizationResult(optimization_method="greedy_npv_ratio")

        # Filter by constraints
        eligible = []
        for action in actions:
            if action.confidence < constraints.min_confidence:
                result.rejected_actions.append({
                    "action_id": action.action_id,
                    "reason": f"confidence {action.confidence} < min {constraints.min_confidence}",
                })
                continue
            if action.risk_score > constraints.max_risk_score:
                result.rejected_actions.append({
                    "action_id": action.action_id,
                    "reason": f"risk {action.risk_score} > max {constraints.max_risk_score}",
                })
                continue
            eligible.append(action)

        # Compliance-required actions go first
        compliance_actions = [a for a in eligible if a.compliance_required]
        optional_actions = [a for a in eligible if not a.compliance_required]

        # Sort optional by NPV/cost efficiency
        for a in optional_actions:
            a._efficiency = a.npv / max(a.cost, 1.0)  # type: ignore
        optional_actions.sort(key=lambda a: a._efficiency, reverse=True)  # type: ignore

        budget_remaining = constraints.total_budget
        capex_remaining = constraints.capex_budget
        actions_remaining = constraints.max_actions

        # Select compliance actions first
        if constraints.required_compliance_actions:
            for action in compliance_actions:
                if actions_remaining <= 0:
                    break
                cost = action.cost
                if action.requires_capex and cost > capex_remaining:
                    result.rejected_actions.append({
                        "action_id": action.action_id,
                        "reason": "exceeds capex budget (compliance)",
                    })
                    continue
                result.selected_actions.append(action)
                budget_remaining -= cost
                if action.requires_capex:
                    capex_remaining -= cost
                actions_remaining -= 1

        # Fill with optional actions
        for action in optional_actions:
            if actions_remaining <= 0 or budget_remaining <= 0:
                break
            cost = action.cost
            if cost > budget_remaining:
                result.rejected_actions.append({
                    "action_id": action.action_id,
                    "reason": "exceeds remaining budget",
                })
                continue
            if action.requires_capex and cost > capex_remaining:
                result.rejected_actions.append({
                    "action_id": action.action_id,
                    "reason": "exceeds capex budget",
                })
                continue
            if action.npv < constraints.min_npv:
                result.rejected_actions.append({
                    "action_id": action.action_id,
                    "reason": f"NPV {action.npv} < min {constraints.min_npv}",
                })
                continue

            result.selected_actions.append(action)
            budget_remaining -= cost
            if action.requires_capex:
                capex_remaining -= cost
            actions_remaining -= 1

        # Compute totals
        result.total_cost = sum(a.cost for a in result.selected_actions)
        result.total_annual_savings = sum(a.annual_savings for a in result.selected_actions)
        result.total_npv = sum(a.npv for a in result.selected_actions)

        if result.total_annual_savings > 0 and result.total_cost > 0:
            result.portfolio_payback_months = (result.total_cost / result.total_annual_savings) * 12
        else:
            result.portfolio_payback_months = None

        result.budget_utilization = result.total_cost / constraints.total_budget if constraints.total_budget < float("inf") else 0

        logger.info(
            f"Greedy optimization: {len(result.selected_actions)} actions selected, "
            f"NPV=${result.total_npv:,.0f}, payback={result.portfolio_payback_months or 'N/A'} months"
        )
        return result

    def optimize_knapsack(
        self,
        actions: List[OptimizationAction],
        constraints: OptimizationConstraints,
    ) -> OptimizationResult:
        """
        0-1 knapsack approximation for budget-constrained optimization.
        Uses dynamic programming with discretized costs.
        """
        result = OptimizationResult(optimization_method="knapsack_dp")

        eligible = [a for a in actions if a.confidence >= constraints.min_confidence and a.risk_score <= constraints.max_risk_score]

        if not eligible:
            return result

        # Discretize budget into integer units (thousands)
        budget_units = int(constraints.total_budget / 1000)
        if budget_units <= 0:
            return self.optimize_greedy(actions, constraints)

        n = len(eligible)
        costs = [max(1, int(a.cost / 1000)) for a in eligible]
        values = [max(0, int(a.npv)) for a in eligible]

        # DP table (use 1D optimization for memory)
        dp = [0] * (budget_units + 1)
        selected = [[False] * n for _ in range(budget_units + 1)]

        for i in range(n):
            for w in range(budget_units, costs[i] - 1, -1):
                if dp[w - costs[i]] + values[i] > dp[w]:
                    dp[w] = dp[w - costs[i]] + values[i]
                    selected[w] = selected[w - costs[i]][:]
                    selected[w][i] = True

        # Extract selected actions
        for i, action in enumerate(eligible):
            if selected[budget_units][i]:
                result.selected_actions.append(action)
            else:
                result.rejected_actions.append({
                    "action_id": action.action_id,
                    "reason": "not selected by knapsack",
                })

        result.total_cost = sum(a.cost for a in result.selected_actions)
        result.total_annual_savings = sum(a.annual_savings for a in result.selected_actions)
        result.total_npv = sum(a.npv for a in result.selected_actions)

        if result.total_annual_savings > 0 and result.total_cost > 0:
            result.portfolio_payback_months = (result.total_cost / result.total_annual_savings) * 12

        result.budget_utilization = result.total_cost / constraints.total_budget if constraints.total_budget < float("inf") else 0

        return result

    def categorize_actions(
        self, actions: List[OptimizationAction]
    ) -> Dict[str, List[OptimizationAction]]:
        """Categorize actions into quick wins, structural fixes, and CapEx replacements."""
        categories = {
            "quick_wins": [],
            "structural_fixes": [],
            "capex_replacements": [],
            "policy_changes": [],
        }

        for action in actions:
            if action.cost == 0 or (action.payback_months and action.payback_months < 3):
                categories["quick_wins"].append(action)
            elif action.requires_capex:
                categories["capex_replacements"].append(action)
            elif action.category == "policy":
                categories["policy_changes"].append(action)
            else:
                categories["structural_fixes"].append(action)

        return categories

    def generate_actions_from_kpi_results(
        self, kpi_results: Dict[str, Dict[str, Any]]
    ) -> List[OptimizationAction]:
        """
        Generate candidate optimization actions from KPI crew results.
        Each KPI result contributes one or more actions.
        """
        actions = []
        action_counter = 0

        for kpi_name, result in kpi_results.items():
            savings = result.get("savings_medium", 0)
            confidence = result.get("confidence", 0)
            if savings <= 0:
                continue

            action_counter += 1
            is_capex = kpi_name == "capex_lifecycle_optimization"

            # Estimate implementation cost as fraction of savings
            if is_capex:
                cost = result.get("metrics", {}).get("total_replace_cost", savings * 2)
            else:
                cost = savings * 0.15  # 15% of savings as implementation cost

            npv = savings * 3 - cost  # Simple 3-year NPV
            payback = (cost / savings * 12) if savings > 0 else None

            actions.append(OptimizationAction(
                action_id=f"action_{action_counter:03d}_{kpi_name}",
                title=f"Implement {result.get('display_name', kpi_name)}",
                category="capex" if is_capex else "opex",
                kpi_sources=[kpi_name],
                cost=cost,
                annual_savings=savings,
                npv=npv,
                payback_months=payback,
                confidence=confidence,
                requires_capex=is_capex,
                compliance_required=kpi_name in ("food_safety_compliance", "esg_compliance"),
            ))

        return actions
