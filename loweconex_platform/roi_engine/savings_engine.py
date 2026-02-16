"""
Savings Engine — computes total ROI, payback, savings-to-cost multiple,
NPV, and IRR from KPI results and program costs.

Aligned with the FRD Section 11 "Total Savings & ROI Engine" requirements.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from loweconex_platform.roi_engine.attribution_ledger import AttributionEntry, AttributionLedger
from loweconex_platform.roi_engine.cost_model import CostModel, ProgramCosts

logger = logging.getLogger(__name__)


@dataclass
class ROIResult:
    """Complete ROI computation result."""
    # Savings
    total_savings_low: float = 0.0
    total_savings_medium: float = 0.0
    total_savings_high: float = 0.0
    savings_by_category: Dict[str, Dict[str, float]] = field(default_factory=dict)
    savings_report_lines: List[Dict[str, Any]] = field(default_factory=list)

    # Costs
    total_cost_year1: float = 0.0
    total_cost_3year: float = 0.0
    cost_by_category: Dict[str, float] = field(default_factory=dict)

    # ROI metrics
    monthly_savings_medium: float = 0.0
    payback_months: Optional[float] = None
    savings_to_cost_multiple: Optional[float] = None
    npv: Optional[float] = None
    irr: Optional[float] = None

    # First-year view
    first_year_monthly_savings: List[float] = field(default_factory=list)
    first_year_monthly_costs: List[float] = field(default_factory=list)
    first_year_cumulative_net: List[float] = field(default_factory=list)

    # Metadata
    analysis_years: int = 3
    discount_rate: float = 0.08
    scenario_id: Optional[str] = None
    computed_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_savings_low": self.total_savings_low,
            "total_savings_medium": self.total_savings_medium,
            "total_savings_high": self.total_savings_high,
            "savings_by_category": self.savings_by_category,
            "savings_report_lines": self.savings_report_lines,
            "total_cost_year1": self.total_cost_year1,
            "total_cost_3year": self.total_cost_3year,
            "cost_by_category": self.cost_by_category,
            "monthly_savings_medium": self.monthly_savings_medium,
            "payback_months": self.payback_months,
            "savings_to_cost_multiple": self.savings_to_cost_multiple,
            "npv": self.npv,
            "irr": self.irr,
            "first_year_monthly_savings": self.first_year_monthly_savings,
            "first_year_monthly_costs": self.first_year_monthly_costs,
            "first_year_cumulative_net": self.first_year_cumulative_net,
            "analysis_years": self.analysis_years,
            "discount_rate": self.discount_rate,
            "scenario_id": self.scenario_id,
            "computed_ts": self.computed_ts,
        }


class SavingsEngine:
    """
    Computes total savings and ROI metrics from KPI results and program costs.
    
    Produces rollups consistent with the FRD Section 11 table structure:
    - Savings (Low / Medium / High) by category
    - Total program cost (year 1 and 3-year)
    - Monthly savings and payback period
    - Savings-to-cost multiple
    - Optional: NPV, IRR
    """

    def __init__(
        self,
        discount_rate: float = 0.08,
        analysis_years: int = 3,
    ):
        self.discount_rate = discount_rate
        self.analysis_years = analysis_years

    def compute_roi(
        self,
        kpi_results: Dict[str, Dict[str, Any]],
        costs: ProgramCosts,
        double_counting_policy: str = "first_claim",
        scenario_id: Optional[str] = None,
    ) -> ROIResult:
        """
        Compute full ROI from KPI results and program costs.
        
        Args:
            kpi_results: Dict of KPI name -> result dict (with savings_low/med/high)
            costs: Program cost structure
            double_counting_policy: Policy for resolving overlapping savings
            scenario_id: Optional scenario identifier
        """
        # Build attribution ledger
        ledger = AttributionLedger(policy=double_counting_policy)
        for kpi_name, result in kpi_results.items():
            entry = AttributionEntry(
                kpi_source=kpi_name,
                savings_type=result.get("savings_category", kpi_name),
                amount_low=result.get("savings_low", 0),
                amount_medium=result.get("savings_medium", 0),
                amount_high=result.get("savings_high", 0),
                confidence=result.get("confidence", 0),
                evidence_refs=result.get("evidence_refs", []),
                scenario_id=scenario_id,
            )
            ledger.add_entry(entry)

        # Get reconciled totals
        totals = ledger.get_grand_totals(scenario_id)
        by_category = ledger.get_total_by_category(scenario_id)
        report_lines = ledger.to_report_lines(scenario_id)

        # Cost totals
        cost_year1 = costs.total_year1()
        cost_3year = costs.total_3year()

        # Monthly savings
        monthly_savings = totals["total_medium"] / 12

        # Payback
        if monthly_savings > 0:
            payback_months = cost_year1 / monthly_savings
        else:
            payback_months = None

        # Savings-to-cost multiple (3-year)
        if cost_3year > 0:
            savings_3year = totals["total_medium"] * self.analysis_years
            savings_to_cost = savings_3year / cost_3year
        else:
            savings_to_cost = None

        # NPV
        npv = self._compute_npv(totals["total_medium"], cost_year1, costs.total_recurring())

        # IRR
        irr = self._compute_irr(totals["total_medium"], cost_year1, costs.total_recurring())

        # First-year monthly view (with ramp)
        monthly_costs_y1 = costs.monthly_cost_year1()
        ramp = costs.ramp_schedule[:12]
        monthly_savings_y1 = [monthly_savings * r for r in ramp]
        cumulative_net = []
        running_total = 0.0
        for i in range(12):
            running_total += monthly_savings_y1[i] - monthly_costs_y1[i]
            cumulative_net.append(round(running_total, 2))

        result = ROIResult(
            total_savings_low=totals["total_low"],
            total_savings_medium=totals["total_medium"],
            total_savings_high=totals["total_high"],
            savings_by_category=by_category,
            savings_report_lines=report_lines,
            total_cost_year1=cost_year1,
            total_cost_3year=cost_3year,
            cost_by_category=costs.by_category(),
            monthly_savings_medium=monthly_savings,
            payback_months=round(payback_months, 1) if payback_months else None,
            savings_to_cost_multiple=round(savings_to_cost, 2) if savings_to_cost else None,
            npv=round(npv, 2) if npv else None,
            irr=round(irr, 4) if irr else None,
            first_year_monthly_savings=[round(s, 2) for s in monthly_savings_y1],
            first_year_monthly_costs=[round(c, 2) for c in monthly_costs_y1],
            first_year_cumulative_net=cumulative_net,
            analysis_years=self.analysis_years,
            discount_rate=self.discount_rate,
            scenario_id=scenario_id,
        )

        logger.info(
            f"ROI computed: savings_med=${result.total_savings_medium:,.0f}/yr, "
            f"cost_3yr=${result.total_cost_3year:,.0f}, "
            f"payback={result.payback_months or 'N/A'} months, "
            f"multiple={result.savings_to_cost_multiple or 'N/A'}x"
        )

        return result

    def _compute_npv(
        self, annual_savings: float, cost_year1: float, cost_recurring: float
    ) -> Optional[float]:
        """Compute Net Present Value over the analysis horizon."""
        if annual_savings <= 0:
            return None

        r = self.discount_rate
        npv = -cost_year1

        for year in range(1, self.analysis_years + 1):
            net_cashflow = annual_savings - (cost_recurring if year > 1 else 0)
            npv += net_cashflow / (1 + r) ** year

        return npv

    def _compute_irr(
        self, annual_savings: float, cost_year1: float, cost_recurring: float
    ) -> Optional[float]:
        """
        Compute Internal Rate of Return using bisection method.
        
        Returns annual IRR as a decimal (e.g., 0.25 = 25%).
        """
        if annual_savings <= 0 or cost_year1 <= 0:
            return None

        def npv_at_rate(rate: float) -> float:
            npv = -cost_year1
            for year in range(1, self.analysis_years + 1):
                net = annual_savings - (cost_recurring if year > 1 else 0)
                npv += net / (1 + rate) ** year
            return npv

        # Bisection
        low, high = -0.5, 5.0
        if npv_at_rate(low) * npv_at_rate(high) > 0:
            return None

        for _ in range(100):
            mid = (low + high) / 2
            if abs(npv_at_rate(mid)) < 1.0:
                return mid
            if npv_at_rate(mid) > 0:
                low = mid
            else:
                high = mid

        return (low + high) / 2

    def compute_location_roi(
        self,
        location_kpi_results: Dict[str, Dict[str, Any]],
        location_cost_share: float,
        costs: ProgramCosts,
        scenario_id: Optional[str] = None,
    ) -> ROIResult:
        """Compute ROI for a single location (pro-rata cost allocation)."""
        location_costs = ProgramCosts(
            analysis_years=costs.analysis_years,
            location_count=1,
        )
        from loweconex_platform.roi_engine.cost_model import CostLineItem
        for item in costs.line_items:
            location_costs.add_item(CostLineItem(
                name=item.name,
                category=item.category,
                amount_year1=item.amount_year1 * location_cost_share,
                amount_recurring=item.amount_recurring * location_cost_share,
                is_one_time=item.is_one_time,
            ))

        return self.compute_roi(
            location_kpi_results, location_costs,
            scenario_id=scenario_id,
        )
