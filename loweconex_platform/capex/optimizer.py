"""
Knapsack Budget Optimizer — DP + greedy portfolio selection.

Selects the optimal set of asset replacements within a CapEx budget
to maximize NPV (or risk reduction, or a blended objective).

Ported from CapEx Generator knapsackOptimizer.js.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class OptimizationItem:
    """A candidate item for knapsack selection."""
    asset_id: str
    asset: Dict[str, Any]
    cost: float
    npv: float
    npv_per_dollar: float = 0.0
    risk_score: float = 0.0
    priority_score: float = 0.0
    option: Optional[Dict[str, Any]] = None
    evaluation: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "cost": self.cost,
            "npv": self.npv,
            "npv_per_dollar": self.npv_per_dollar,
            "risk_score": self.risk_score,
            "priority_score": self.priority_score,
        }


@dataclass
class OptimizedPlan:
    """Result of knapsack optimization."""
    items: List[Dict[str, Any]] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "items": self.items,
            "summary": self.summary,
        }


@dataclass
class SensitivityPoint:
    """One point on the budget sensitivity curve."""
    budget_multiplier: float
    budget: float
    assets_selected: int
    total_npv: float
    utilization_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "budget_multiplier": self.budget_multiplier,
            "budget": self.budget,
            "assets_selected": self.assets_selected,
            "total_npv": self.total_npv,
            "utilization_pct": self.utilization_pct,
        }


class KnapsackOptimizer:
    """Budget-constrained portfolio optimizer using DP + greedy hybrid."""

    SCALE_FACTOR = 100

    # ── Core Solvers ──────────────────────────────────────────────

    @staticmethod
    def solve_dp(items: List[OptimizationItem], budget: float) -> Dict[str, Any]:
        """Dynamic-programming 0/1 knapsack."""
        n = len(items)
        if n == 0 or budget <= 0:
            return {"selected": [], "total_cost": 0, "total_npv": 0}

        sf = KnapsackOptimizer.SCALE_FACTOR
        scaled_budget = int(budget / sf)

        dp = [[0] * (scaled_budget + 1) for _ in range(n + 1)]
        keep = [[False] * (scaled_budget + 1) for _ in range(n + 1)]

        for i in range(1, n + 1):
            item = items[i - 1]
            scaled_cost = math.ceil(item.cost / sf)
            value = item.npv

            for w in range(scaled_budget + 1):
                if scaled_cost <= w and value > 0:
                    with_item = dp[i - 1][w - scaled_cost] + value
                    without_item = dp[i - 1][w]
                    if with_item > without_item:
                        dp[i][w] = with_item
                        keep[i][w] = True
                    else:
                        dp[i][w] = without_item
                else:
                    dp[i][w] = dp[i - 1][w]

        selected = []
        w = scaled_budget
        for i in range(n, 0, -1):
            if keep[i][w]:
                selected.append(items[i - 1])
                w -= math.ceil(items[i - 1].cost / sf)
        selected.reverse()

        total_cost = sum(it.cost for it in selected)
        total_npv = sum(it.npv for it in selected)
        return {"selected": selected, "total_cost": total_cost, "total_npv": total_npv}

    @staticmethod
    def solve_greedy(items: List[OptimizationItem], budget: float) -> Dict[str, Any]:
        """Greedy knapsack by NPV/cost ratio."""
        valid = [it for it in items if it.cost <= budget and it.npv > 0]
        valid.sort(key=lambda it: it.npv / it.cost if it.cost > 0 else 0, reverse=True)

        selected = []
        remaining = budget
        for it in valid:
            if it.cost <= remaining:
                selected.append(it)
                remaining -= it.cost

        total_cost = sum(it.cost for it in selected)
        total_npv = sum(it.npv for it in selected)
        return {"selected": selected, "total_cost": total_cost, "total_npv": total_npv}

    # ── Full Optimization Pipeline ────────────────────────────────

    def optimize(
        self,
        evaluated_assets: List[Dict[str, Any]],
        budget: float,
        objective: str = "max_expected_npv",
    ) -> OptimizedPlan:
        """Optimize a portfolio of asset replacements within budget.

        Parameters
        ----------
        evaluated_assets : list of dicts, each with keys:
            asset, score, recommendation, best_option, survival_analysis, ...
        budget : total CapEx budget
        objective : 'max_expected_npv' | 'risk_reduction' | 'blended'
        """
        # Build candidate list (only REPLACE recommendations with a valid option)
        candidates: List[OptimizationItem] = []
        for ea in evaluated_assets:
            rec = ea.get("recommendation", {})
            best = ea.get("best_option", {})
            if rec.get("decision") != "REPLACE" or not best:
                continue
            asset = ea.get("asset", {})
            score = ea.get("score", {})
            candidates.append(OptimizationItem(
                asset_id=asset.get("asset_id", ""),
                asset=asset,
                cost=best.get("capex", 0),
                npv=best.get("npv", 0),
                npv_per_dollar=best.get("npv_per_capex_dollar", 0),
                risk_score=score.get("risk_score", 0),
                priority_score=score.get("replace_priority_score", 0),
                option=best,
                evaluation=ea,
            ))

        # Apply objective-specific value transformation
        items = list(candidates)
        if objective == "risk_reduction":
            items = [
                OptimizationItem(
                    asset_id=c.asset_id, asset=c.asset, cost=c.cost,
                    npv=c.risk_score * 1000,
                    npv_per_dollar=c.npv_per_dollar, risk_score=c.risk_score,
                    priority_score=c.priority_score, option=c.option, evaluation=c.evaluation,
                )
                for c in candidates
            ]
        elif objective == "blended":
            items = [
                OptimizationItem(
                    asset_id=c.asset_id, asset=c.asset, cost=c.cost,
                    npv=c.npv * 0.5 + c.risk_score * 500 + c.priority_score * 300,
                    npv_per_dollar=c.npv_per_dollar, risk_score=c.risk_score,
                    priority_score=c.priority_score, option=c.option, evaluation=c.evaluation,
                )
                for c in candidates
            ]

        # Run both solvers and pick best
        dp_result = self.solve_dp(items, budget)
        greedy_result = self.solve_greedy(items, budget)
        best = dp_result if dp_result["total_npv"] >= greedy_result["total_npv"] else greedy_result

        selected_ids = {it.asset_id for it in best["selected"]}

        # Build plan items for all evaluated assets
        plan_items: List[Dict[str, Any]] = []
        for ea in evaluated_assets:
            asset = ea.get("asset", {})
            aid = asset.get("asset_id", "")
            rec = ea.get("recommendation", {})
            best_opt = ea.get("best_option", {})
            is_selected = aid in selected_ids

            if is_selected:
                decision = "REPLACE"
                reason = "Selected for budget optimization"
            elif rec.get("decision") == "REPLACE":
                decision = "DEFER"
                reason = "Deferred due to budget constraints"
            else:
                decision = rec.get("decision", "DEFER")
                reason = rec.get("reason", "")

            plan_items.append({
                **ea,
                "plan_item": {
                    "asset_id": aid,
                    "decision": decision,
                    "selected_option_id": best_opt.get("option_id") if is_selected else None,
                    "capex_cost": best_opt.get("capex", 0) if is_selected else 0,
                    "npv_p50": best_opt.get("npv", 0),
                    "p_npv_positive": best_opt.get("p_npv_positive", 0),
                    "is_in_budget": is_selected,
                    "reason": reason,
                },
            })

        summary = {
            "budget": budget,
            "total_selected_cost": best["total_cost"],
            "total_expected_npv": best["total_npv"],
            "remaining_budget": budget - best["total_cost"],
            "assets_selected": len(best["selected"]),
            "assets_deferred": len(candidates) - len(best["selected"]),
            "assets_total": len(evaluated_assets),
            "utilization_pct": round(best["total_cost"] / budget * 100) if budget > 0 else 0,
        }

        return OptimizedPlan(items=plan_items, summary=summary)

    # ── Sensitivity Analysis ──────────────────────────────────────

    def sensitivity_analysis(
        self,
        evaluated_assets: List[Dict[str, Any]],
        base_budget: float,
        multipliers: Optional[List[float]] = None,
    ) -> List[SensitivityPoint]:
        """Run optimization at multiple budget levels."""
        mults = multipliers or [0.5, 0.75, 1.0, 1.25, 1.5]
        results = []
        for m in mults:
            test_budget = round(base_budget * m)
            plan = self.optimize(evaluated_assets, test_budget)
            results.append(SensitivityPoint(
                budget_multiplier=m,
                budget=test_budget,
                assets_selected=plan.summary.get("assets_selected", 0),
                total_npv=plan.summary.get("total_expected_npv", 0),
                utilization_pct=plan.summary.get("utilization_pct", 0),
            ))
        return results

    # ── Next Best Assets ──────────────────────────────────────────

    @staticmethod
    def get_next_best(
        evaluated_assets: List[Dict[str, Any]],
        current_plan: OptimizedPlan,
        count: int = 3,
    ) -> List[Dict[str, Any]]:
        """Return top deferred assets by NPV/dollar if budget were expanded."""
        selected_ids = {
            it["plan_item"]["asset_id"]
            for it in current_plan.items
            if it.get("plan_item", {}).get("is_in_budget")
        }
        deferred = []
        for ea in evaluated_assets:
            asset = ea.get("asset", {})
            aid = asset.get("asset_id", "")
            best = ea.get("best_option", {})
            rec = ea.get("recommendation", {})
            if aid not in selected_ids and rec.get("decision") == "REPLACE" and best.get("npv", 0) > 0:
                deferred.append({
                    "asset_id": aid,
                    "asset_type": asset.get("asset_type", ""),
                    "additional_cost": best.get("capex", 0),
                    "additional_npv": best.get("npv", 0),
                    "npv_per_dollar": best.get("npv_per_capex_dollar", 0),
                    "priority_score": ea.get("score", {}).get("replace_priority_score", 0),
                })
        deferred.sort(key=lambda x: x["npv_per_dollar"], reverse=True)
        return deferred[:count]
