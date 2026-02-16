"""
CapEx Engine — top-level orchestrator for full store/fleet CapEx analysis.

Coordinates survival modeling, scoring, LCC evaluation, and knapsack
optimization into a single analysis pipeline.

Ported from CapEx Generator capexEngine.js.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from loweconex_platform.capex.lcc import LCCEngine
from loweconex_platform.capex.survival import SurvivalModel
from loweconex_platform.capex.scorer import AssetScorer, DECISION_TYPES
from loweconex_platform.capex.optimizer import KnapsackOptimizer

logger = logging.getLogger(__name__)


@dataclass
class CapExAnalysisResult:
    """Complete output of a CapEx analysis run."""
    store: Dict[str, Any] = field(default_factory=dict)
    budget: float = 0.0
    objective: str = "max_expected_npv"
    as_of_date: str = ""

    evaluated_assets: List[Dict[str, Any]] = field(default_factory=list)
    optimized_plan: Dict[str, Any] = field(default_factory=dict)
    sensitivity: List[Dict[str, Any]] = field(default_factory=list)
    next_best_assets: List[Dict[str, Any]] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "store": self.store,
            "budget": self.budget,
            "objective": self.objective,
            "as_of_date": self.as_of_date,
            "evaluated_assets": [
                {k: v for k, v in ea.items() if k != "evaluation"}
                for ea in self.evaluated_assets
            ],
            "optimized_plan": self.optimized_plan,
            "sensitivity": self.sensitivity,
            "next_best_assets": self.next_best_assets,
            "summary": self.summary,
        }


class CapExEngine:
    """
    Run the full CapEx analysis pipeline for a store/location.

    Pipeline:
    1. Survival analysis per asset
    2. Multi-factor scoring
    3. LCC evaluation per replacement option
    4. Recommendation generation
    5. Knapsack budget optimization
    6. Sensitivity analysis
    """

    def __init__(self):
        self.optimizer = KnapsackOptimizer()

    def analyze(
        self,
        store: Dict[str, Any],
        assets: List[Dict[str, Any]],
        replacement_options: Dict[str, List[Dict[str, Any]]],
        economic_assumption: Dict[str, Any],
        utility_rate: Dict[str, Any],
        budget: float,
        objective: str = "max_expected_npv",
        health_data: Optional[Dict[str, Dict[str, Any]]] = None,
        fault_data: Optional[Dict[str, Dict[str, Any]]] = None,
        energy_waste_data: Optional[Dict[str, Dict[str, Any]]] = None,
        peer_data: Optional[Dict[str, int]] = None,
    ) -> CapExAnalysisResult:
        """Run the full CapEx analysis pipeline.

        Parameters
        ----------
        store : store/location metadata
        assets : list of asset dicts (asset_id, asset_type, age_years, ...)
        replacement_options : {asset_id: [option_dicts]}
        economic_assumption : {discount_rate, analysis_horizon_years, failure_event_cost_by_type}
        utility_rate : {energy_rate, escalation_rate}
        budget : total CapEx budget
        objective : 'max_expected_npv' | 'risk_reduction' | 'blended'
        health_data : optional {asset_id: health_dict} from PdM bridge
        fault_data : optional {asset_id: fault_dict}
        energy_waste_data : optional {asset_id: energy_waste_dict}
        peer_data : optional {asset_id: percentile}
        """
        health_map = health_data or {}
        fault_map = fault_data or {}
        waste_map = energy_waste_data or {}
        peer_map = peer_data or {}

        logger.info(
            f"[CapEx Engine] Starting analysis for {store.get('name', 'unknown')} — "
            f"{len(assets)} assets, budget=${budget:,.0f}"
        )

        # ── Step 1: Survival Analysis ─────────────────────────────
        logger.info("[CapEx Engine] Step 1: Survival analysis...")
        survival_results: Dict[str, Dict[str, Any]] = {}
        for asset in assets:
            aid = asset.get("asset_id", "")
            features = {
                "peer_percentile": peer_map.get(aid, 50),
                "fault_burden_score": fault_map.get(aid, {}).get("fault_burden_score", 0),
                "energy_waste_percentile": waste_map.get(aid, {}).get("waste_percentile", 50),
                "maintenance_trend": health_map.get(aid, {}).get("maintenance_trend", 0),
            }
            result = SurvivalModel.analyze(asset, features)
            survival_results[aid] = result.to_dict()

        # ── Step 2: Asset Scoring ─────────────────────────────────
        logger.info("[CapEx Engine] Step 2: Scoring assets...")
        scores: Dict[str, Dict[str, Any]] = {}
        for asset in assets:
            aid = asset.get("asset_id", "")
            score = AssetScorer.score(
                asset=asset,
                health_data=health_map.get(aid),
                survival_result=survival_results.get(aid),
                fault_result=fault_map.get(aid),
                energy_waste=waste_map.get(aid),
                peer_percentile=peer_map.get(aid, 50),
            )
            scores[aid] = score.to_dict()

        # ── Step 3: LCC Evaluation ────────────────────────────────
        logger.info("[CapEx Engine] Step 3: LCC evaluation...")
        option_evals: Dict[str, List[Dict[str, Any]]] = {}
        for asset in assets:
            aid = asset.get("asset_id", "")
            options = replacement_options.get(aid, [])
            if not options:
                option_evals[aid] = []
                continue

            health = health_map.get(aid, {})
            features = {
                "kwh_day": health.get("kwh_day", 100),
                "maintenance_cost_365d": health.get("annual_maintenance_cost", 2000),
            }
            survival = survival_results.get(aid)

            evals = []
            for opt in options:
                result = LCCEngine.evaluate(
                    asset=asset,
                    features=features,
                    replacement_option=opt,
                    economic_assumption=economic_assumption,
                    utility_rate=utility_rate,
                    survival_analysis=survival,
                )
                evals.append(result)
            # Sort by NPV descending
            evals.sort(key=lambda e: e.get("summary", {}).get("npv", 0), reverse=True)
            option_evals[aid] = evals

        # ── Step 4: Recommendations ───────────────────────────────
        logger.info("[CapEx Engine] Step 4: Generating recommendations...")
        evaluated_assets: List[Dict[str, Any]] = []
        for asset in assets:
            aid = asset.get("asset_id", "")
            score_dict = scores.get(aid, {})
            evals = option_evals.get(aid, [])
            best = evals[0] if evals else None
            best_summary = best.get("summary", {}) if best else {}
            # Merge capex cost from option into summary so optimizer can use it
            if best and best.get("option"):
                best_summary["capex"] = best["option"].get("capex", 0)
                capex_cost = best_summary["capex"]
                if capex_cost > 0 and best_summary.get("npv"):
                    best_summary["npv_per_capex_dollar"] = round(
                        best_summary["npv"] / capex_cost, 2
                    )

            # Create AssetScore for recommendation
            from loweconex_platform.capex.scorer import AssetScore
            score_obj = AssetScore(
                condition_score=score_dict.get("condition_score", 50),
                risk_score=score_dict.get("risk_score", 50),
                energy_waste_score=score_dict.get("energy_waste_score", 50),
                replace_priority_score=score_dict.get("replace_priority_score", 50),
                is_scoreable=score_dict.get("is_scoreable", True),
                explain_top_drivers=score_dict.get("explain_top_drivers", []),
            )

            rec = AssetScorer.recommend_decision(asset, score_obj, best_summary)

            evaluated_assets.append({
                "asset": asset,
                "score": score_dict,
                "survival_analysis": survival_results.get(aid, {}),
                "fault_detection": fault_map.get(aid, {}),
                "energy_waste": waste_map.get(aid, {}),
                "peer_percentile": peer_map.get(aid, 50),
                "option_evaluations": [
                    {**e.get("summary", {}), "capex": e.get("option", {}).get("capex", 0)}
                    for e in evals
                ],
                "best_option": best_summary if best else {},
                "recommendation": rec,
            })

        # Sort by priority score descending
        evaluated_assets.sort(
            key=lambda ea: ea.get("score", {}).get("replace_priority_score", 0),
            reverse=True,
        )

        # ── Step 5: Budget Optimization ───────────────────────────
        logger.info("[CapEx Engine] Step 5: Optimizing budget allocation...")
        plan = self.optimizer.optimize(evaluated_assets, budget, objective)

        # ── Step 6: Sensitivity Analysis ──────────────────────────
        logger.info("[CapEx Engine] Step 6: Sensitivity analysis...")
        sensitivity = self.optimizer.sensitivity_analysis(evaluated_assets, budget)

        # ── Step 7: Next Best Assets ──────────────────────────────
        next_best = self.optimizer.get_next_best(evaluated_assets, plan, count=3)

        # ── Build Summary ─────────────────────────────────────────
        summary = self._build_summary(plan, evaluated_assets, store, budget)

        logger.info(
            f"[CapEx Engine] Complete — {summary.get('assets_selected', 0)} assets selected, "
            f"NPV=${summary.get('total_expected_npv', 0):,.0f}"
        )

        return CapExAnalysisResult(
            store=store,
            budget=budget,
            objective=objective,
            as_of_date=datetime.utcnow().isoformat(),
            evaluated_assets=evaluated_assets,
            optimized_plan=plan.to_dict(),
            sensitivity=[s.to_dict() for s in sensitivity],
            next_best_assets=next_best,
            summary=summary,
        )

    def _build_summary(
        self,
        plan,
        evaluated_assets: List[Dict[str, Any]],
        store: Dict[str, Any],
        budget: float,
    ) -> Dict[str, Any]:
        """Build executive summary from plan results."""
        selected = [
            it for it in plan.items
            if it.get("plan_item", {}).get("is_in_budget")
        ]
        deferred = [
            it for it in plan.items
            if not it.get("plan_item", {}).get("is_in_budget")
            and it.get("recommendation", {}).get("decision") == "REPLACE"
        ]

        total_annual_savings = sum(
            it.get("best_option", {}).get("eac_savings", 0) for it in selected
        )
        avg_payback = 0
        paybacks = [
            it.get("best_option", {}).get("simple_payback", 0)
            for it in selected
            if it.get("best_option", {}).get("simple_payback")
        ]
        if paybacks:
            avg_payback = sum(paybacks) / len(paybacks)

        risk_reduction = sum(
            it.get("score", {}).get("risk_score", 0) - 20
            for it in selected
        )

        by_type: Dict[str, Dict[str, Any]] = {}
        for it in selected:
            atype = it.get("asset", {}).get("asset_type", "Unknown")
            if atype not in by_type:
                by_type[atype] = {"count": 0, "total_cost": 0, "total_npv": 0}
            by_type[atype]["count"] += 1
            by_type[atype]["total_cost"] += it.get("plan_item", {}).get("capex_cost", 0)
            by_type[atype]["total_npv"] += it.get("best_option", {}).get("npv", 0)

        # Top drivers across selected
        driver_counts: Dict[str, int] = {}
        for it in selected:
            for d in it.get("score", {}).get("explain_top_drivers", []):
                driver_counts[d] = driver_counts.get(d, 0) + 1
        top_drivers = sorted(driver_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "store_name": store.get("name", ""),
            "store_id": store.get("store_id", store.get("location_id", "")),
            "budget": budget,
            "total_capex_selected": plan.summary.get("total_selected_cost", 0),
            "total_expected_npv": plan.summary.get("total_expected_npv", 0),
            "remaining_budget": plan.summary.get("remaining_budget", 0),
            "budget_utilization": plan.summary.get("utilization_pct", 0),
            "assets_analyzed": len(evaluated_assets),
            "assets_selected_for_replacement": plan.summary.get("assets_selected", 0),
            "assets_deferred": plan.summary.get("assets_deferred", 0),
            "total_annual_savings": round(total_annual_savings),
            "avg_simple_payback_years": round(avg_payback, 1),
            "estimated_risk_reduction": risk_reduction,
            "breakdown_by_asset_type": by_type,
            "top_drivers": [{"driver": d, "count": c} for d, c in top_drivers],
            "deferred_opportunities": [
                {
                    "asset_id": it.get("asset", {}).get("asset_id", ""),
                    "asset_type": it.get("asset", {}).get("asset_type", ""),
                    "capex_required": it.get("best_option", {}).get("capex", 0),
                    "npv_if_funded": it.get("best_option", {}).get("npv", 0),
                    "priority_score": it.get("score", {}).get("replace_priority_score", 0),
                }
                for it in deferred[:5]
            ],
        }
