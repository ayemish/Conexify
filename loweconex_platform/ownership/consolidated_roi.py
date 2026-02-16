"""
Consolidated ROI Engine — computes ROI with per-owner, per-quadrant,
and per-cost-type breakdowns.

Extends the existing SavingsEngine pattern with ownership-aware
dimensions, sensitivity analysis, and explainability drill-down.
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from loweconex_platform.ownership.cost_stack import CostStack, CostType, CostLineItem
from loweconex_platform.ownership.financial_constants import (
    DISCOUNT_RATE,
    HORIZON_YEARS,
    IMPLEMENTATION_COST,
)

logger = logging.getLogger(__name__)


@dataclass
class ROIBreakdown:
    """ROI breakdown for a single dimension (owner, quadrant, cost type)."""
    dimension_key: str = ""
    dimension_value: str = ""
    total_savings: float = 0.0
    total_cost: float = 0.0
    net_benefit: float = 0.0
    roi_pct: float = 0.0
    npv: float = 0.0
    payback_months: Optional[float] = None
    line_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension_key": self.dimension_key,
            "dimension_value": self.dimension_value,
            "total_savings": round(self.total_savings, 2),
            "total_cost": round(self.total_cost, 2),
            "net_benefit": round(self.net_benefit, 2),
            "roi_pct": round(self.roi_pct, 1),
            "npv": round(self.npv, 2),
            "payback_months": round(self.payback_months, 1) if self.payback_months else None,
            "line_count": self.line_count,
        }


@dataclass
class SensitivityResult:
    """Result of a sensitivity analysis for a single parameter."""
    parameter_name: str = ""
    base_value: float = 0.0
    low_value: float = 0.0
    high_value: float = 0.0
    base_roi: float = 0.0
    low_roi: float = 0.0
    high_roi: float = 0.0
    roi_swing: float = 0.0       # high_roi - low_roi (tornado width)
    sensitivity_rank: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameter_name": self.parameter_name,
            "base_value": self.base_value,
            "low_value": self.low_value,
            "high_value": self.high_value,
            "base_roi": round(self.base_roi, 2),
            "low_roi": round(self.low_roi, 2),
            "high_roi": round(self.high_roi, 2),
            "roi_swing": round(self.roi_swing, 2),
            "sensitivity_rank": self.sensitivity_rank,
        }


@dataclass
class ConsolidatedROI:
    """
    Full consolidated ROI result with multi-dimensional breakdowns.
    """
    scenario_id: str = ""
    scenario_name: str = ""

    # Top-level
    total_savings: float = 0.0
    total_cost: float = 0.0
    net_benefit: float = 0.0
    roi_pct: float = 0.0
    npv: float = 0.0
    irr: Optional[float] = None
    payback_months: Optional[float] = None

    # Confidence
    savings_low: float = 0.0
    savings_high: float = 0.0
    confidence_weighted_avg: float = 0.0

    # Breakdowns
    roi_by_owner: List[ROIBreakdown] = field(default_factory=list)
    roi_by_quadrant: List[ROIBreakdown] = field(default_factory=list)
    roi_by_cost_type: List[ROIBreakdown] = field(default_factory=list)

    # Year-by-year
    year_by_year_cashflow: List[Dict[str, float]] = field(default_factory=list)

    # Sensitivity
    sensitivity_results: List[SensitivityResult] = field(default_factory=list)

    # Baseline comparison
    baseline_decomposition: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    computed_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    line_count: int = 0
    missing_data_count: int = 0
    assumption_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "total_savings": round(self.total_savings, 2),
            "total_cost": round(self.total_cost, 2),
            "net_benefit": round(self.net_benefit, 2),
            "roi_pct": round(self.roi_pct, 1),
            "npv": round(self.npv, 2),
            "irr": round(self.irr, 3) if self.irr is not None else None,
            "payback_months": round(self.payback_months, 1) if self.payback_months else None,
            "savings_low": round(self.savings_low, 2),
            "savings_high": round(self.savings_high, 2),
            "confidence_weighted_avg": round(self.confidence_weighted_avg, 3),
            "roi_by_owner": [b.to_dict() for b in self.roi_by_owner],
            "roi_by_quadrant": [b.to_dict() for b in self.roi_by_quadrant],
            "roi_by_cost_type": [b.to_dict() for b in self.roi_by_cost_type],
            "year_by_year_cashflow": self.year_by_year_cashflow,
            "sensitivity_results": [s.to_dict() for s in self.sensitivity_results],
            "baseline_decomposition": self.baseline_decomposition,
            "computed_ts": self.computed_ts,
            "line_count": self.line_count,
            "missing_data_count": self.missing_data_count,
            "assumption_count": self.assumption_count,
        }


class ConsolidatedROIEngine:
    """
    Computes consolidated ROI from a CostStack with multi-dimensional
    breakdowns by owner, quadrant, and cost type.
    """

    def __init__(self, discount_rate: float = DISCOUNT_RATE, horizon_years: int = HORIZON_YEARS):
        self.discount_rate = discount_rate
        self.horizon_years = horizon_years

    def compute(
        self,
        cost_stack: CostStack,
        scenario_id: str = "",
        scenario_name: str = "",
        baseline_stack: Optional[CostStack] = None,
        implementation_cost: float = IMPLEMENTATION_COST,
    ) -> ConsolidatedROI:
        """
        Compute consolidated ROI from a cost stack.

        Args:
            cost_stack: The cost stack to analyze
            scenario_id: Scenario identifier
            scenario_name: Scenario display name
            baseline_stack: Optional baseline for decomposition
            implementation_cost: Upfront platform deployment cost deducted from NPV
        """
        roi = ConsolidatedROI(
            scenario_id=scenario_id,
            scenario_name=scenario_name,
        )

        lines = cost_stack.lines
        if not lines:
            return roi

        # ── Top-level totals ────────────────────────────────────────
        savings_lines = cost_stack.savings_lines()
        cost_lines = cost_stack.cost_lines()

        roi.total_savings = sum(l.amount for l in savings_lines)
        roi.total_cost = sum(abs(l.amount) for l in cost_lines)
        roi.net_benefit = roi.total_savings - roi.total_cost

        if roi.total_cost > 0:
            roi.roi_pct = (roi.net_benefit / roi.total_cost) * 100
            roi.payback_months = (roi.total_cost / roi.total_savings * 12) if roi.total_savings > 0 else None
        elif roi.total_savings > 0:
            roi.roi_pct = 999.9

        roi.npv = sum(l.npv for l in lines) - implementation_cost

        # Confidence bands
        roi.savings_low = sum(l.amount_low for l in savings_lines)
        roi.savings_high = sum(l.amount_high for l in savings_lines)

        # Confidence-weighted average
        total_weighted = sum(l.amount * l.confidence for l in savings_lines)
        total_amount = sum(l.amount for l in savings_lines)
        roi.confidence_weighted_avg = total_weighted / total_amount if total_amount > 0 else 0

        # IRR approximation
        roi.irr = self._approximate_irr(roi.total_cost, roi.total_savings, self.horizon_years)

        # ── Breakdowns ──────────────────────────────────────────────
        roi.roi_by_owner = self._breakdown_by_dimension(cost_stack, "owner")
        roi.roi_by_quadrant = self._breakdown_by_dimension(cost_stack, "quadrant")
        roi.roi_by_cost_type = self._breakdown_by_dimension(cost_stack, "cost_type")

        # ── Year-by-year cashflow ───────────────────────────────────
        roi.year_by_year_cashflow = cost_stack.year_by_year_cashflow(self.horizon_years)

        # ── Baseline decomposition ──────────────────────────────────
        if baseline_stack:
            roi.baseline_decomposition = self._compute_baseline_delta(baseline_stack, cost_stack)

        # ── Metadata ────────────────────────────────────────────────
        roi.line_count = len(lines)
        roi.missing_data_count = len(cost_stack.missing_data_lines())
        roi.assumption_count = len(cost_stack.assumption_based_lines())

        return roi

    def compare_scenarios(
        self, scenarios: Dict[str, ConsolidatedROI]
    ) -> Dict[str, Any]:
        """Compare multiple scenario ROI results side by side."""
        if not scenarios:
            return {"error": "No scenarios to compare"}

        comparison = {
            "scenarios": {},
            "ranking_by_npv": [],
            "ranking_by_roi": [],
            "ranking_by_payback": [],
        }

        entries = []
        for name, roi in scenarios.items():
            comparison["scenarios"][name] = roi.to_dict()
            entries.append((name, roi))

        # Rankings
        by_npv = sorted(entries, key=lambda x: x[1].npv, reverse=True)
        comparison["ranking_by_npv"] = [
            {"rank": i + 1, "scenario": n, "npv": round(r.npv, 2)}
            for i, (n, r) in enumerate(by_npv)
        ]

        by_roi = sorted(entries, key=lambda x: x[1].roi_pct, reverse=True)
        comparison["ranking_by_roi"] = [
            {"rank": i + 1, "scenario": n, "roi_pct": round(r.roi_pct, 1)}
            for i, (n, r) in enumerate(by_roi)
        ]

        payback_entries = [(n, r) for n, r in entries if r.payback_months is not None]
        by_payback = sorted(payback_entries, key=lambda x: x[1].payback_months)
        comparison["ranking_by_payback"] = [
            {"rank": i + 1, "scenario": n, "payback_months": round(r.payback_months, 1)}
            for i, (n, r) in enumerate(by_payback)
        ]

        # Deltas from first scenario
        if len(entries) >= 2:
            base_name, base_roi = entries[0]
            deltas = {}
            for other_name, other_roi in entries[1:]:
                deltas[f"{base_name}_vs_{other_name}"] = {
                    "npv_delta": round(other_roi.npv - base_roi.npv, 2),
                    "roi_delta": round(other_roi.roi_pct - base_roi.roi_pct, 1),
                    "savings_delta": round(other_roi.total_savings - base_roi.total_savings, 2),
                }
            comparison["deltas"] = deltas

        return comparison

    def run_sensitivity(
        self,
        cost_stack: CostStack,
        parameter_ranges: Dict[str, Tuple[float, float, float]],
        metric_inputs: Dict[str, Dict[str, Any]],
        rebuild_fn=None,
    ) -> List[SensitivityResult]:
        """
        Run tornado-style sensitivity analysis.

        Args:
            cost_stack: Current cost stack (for base ROI)
            parameter_ranges: {param_name: (low, base, high)}
            metric_inputs: Base metric inputs
            rebuild_fn: Callable(metric_inputs) -> CostStack for re-evaluation

        Returns:
            List of SensitivityResults sorted by swing (tornado order).
        """
        base_roi = self.compute(cost_stack)
        results = []

        for param_name, (low_val, base_val, high_val) in parameter_ranges.items():
            # Low scenario
            low_inputs = _apply_param_override(metric_inputs, param_name, low_val)
            low_stack = rebuild_fn(low_inputs) if rebuild_fn else cost_stack
            low_roi = self.compute(low_stack)

            # High scenario
            high_inputs = _apply_param_override(metric_inputs, param_name, high_val)
            high_stack = rebuild_fn(high_inputs) if rebuild_fn else cost_stack
            high_roi = self.compute(high_stack)

            results.append(SensitivityResult(
                parameter_name=param_name,
                base_value=base_val,
                low_value=low_val,
                high_value=high_val,
                base_roi=base_roi.npv,
                low_roi=low_roi.npv,
                high_roi=high_roi.npv,
                roi_swing=abs(high_roi.npv - low_roi.npv),
            ))

        # Rank by swing (tornado order)
        results.sort(key=lambda r: r.roi_swing, reverse=True)
        for i, r in enumerate(results):
            r.sensitivity_rank = i + 1

        return results

    # ── Helpers ─────────────────────────────────────────────────────

    def _breakdown_by_dimension(
        self, cost_stack: CostStack, dimension: str
    ) -> List[ROIBreakdown]:
        """Build ROI breakdowns for a given dimension."""
        if dimension == "owner":
            grouped = cost_stack.by_owner()
        elif dimension == "quadrant":
            grouped = cost_stack.by_quadrant()
        elif dimension == "cost_type":
            grouped = cost_stack.by_cost_type()
        else:
            return []

        breakdowns = []
        for key, agg in grouped.items():
            savings = agg.get("amount", 0)
            npv = agg.get("npv", 0)
            cost_val = abs(savings) if savings < 0 else 0
            savings_val = savings if savings > 0 else 0

            net = savings_val - cost_val
            roi_pct = (net / cost_val * 100) if cost_val > 0 else (float("inf") if net > 0 else 0)
            payback = (cost_val / savings_val * 12) if savings_val > 0 and cost_val > 0 else None

            breakdowns.append(ROIBreakdown(
                dimension_key=dimension,
                dimension_value=key,
                total_savings=savings_val,
                total_cost=cost_val,
                net_benefit=net,
                roi_pct=roi_pct if roi_pct != float("inf") else 999.9,
                npv=npv,
                payback_months=payback,
                line_count=int(agg.get("count", 0)),
            ))

        return sorted(breakdowns, key=lambda b: b.npv, reverse=True)

    def _compute_baseline_delta(
        self, baseline: CostStack, current: CostStack
    ) -> Dict[str, Any]:
        """Compute what changed between baseline and current scenario."""
        base_total = baseline.total()
        curr_total = current.total()

        base_by_type = baseline.by_cost_type()
        curr_by_type = current.by_cost_type()

        deltas_by_type = {}
        for ct in CostType:
            base_amt = base_by_type.get(ct.value, {}).get("amount", 0)
            curr_amt = curr_by_type.get(ct.value, {}).get("amount", 0)
            deltas_by_type[ct.value] = {
                "baseline": round(base_amt, 2),
                "current": round(curr_amt, 2),
                "delta": round(curr_amt - base_amt, 2),
                "delta_pct": round((curr_amt - base_amt) / base_amt * 100, 1) if base_amt else 0,
            }

        return {
            "total_delta": round(curr_total.get("amount", 0) - base_total.get("amount", 0), 2),
            "by_cost_type": deltas_by_type,
        }

    @staticmethod
    def _approximate_irr(
        initial_cost: float, annual_savings: float, years: int
    ) -> Optional[float]:
        """Approximate IRR using Newton's method."""
        if initial_cost <= 0 or annual_savings <= 0:
            return None

        # Cash flows: -cost at year 0, then annual_savings for N years
        cashflows = [-initial_cost] + [annual_savings] * years

        # Newton's method
        rate = 0.10  # initial guess
        for _ in range(100):
            npv = sum(cf / (1 + rate) ** t for t, cf in enumerate(cashflows))
            dnpv = sum(-t * cf / (1 + rate) ** (t + 1) for t, cf in enumerate(cashflows))
            if abs(dnpv) < 1e-10:
                break
            rate -= npv / dnpv
            if rate < -0.99:
                rate = -0.99
            if rate > 10.0:
                return None

        if -1.0 < rate < 10.0:
            return round(rate, 4)
        return None


def _apply_param_override(
    metric_inputs: Dict[str, Dict[str, Any]],
    param_name: str,
    value: float,
) -> Dict[str, Dict[str, Any]]:
    """Create a copy of metric_inputs with one parameter overridden."""
    import copy
    overridden = copy.deepcopy(metric_inputs)
    for mid, inputs in overridden.items():
        if param_name in inputs:
            inputs[param_name] = value
    return overridden
