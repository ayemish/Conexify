"""
Cost Stack Schema — categorized cost structure with owner attribution.

Supports four cost types (Opex / Capex / Risk / Strategic) with
line-item drivers, owner roles, calculation references, and
multi-year time horizons.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from loweconex_platform.ownership.financial_constants import (
    DISCOUNT_RATE,
    HORIZON_LABEL,
)

logger = logging.getLogger(__name__)


class CostType(str, Enum):
    OPEX = "opex"
    CAPEX = "capex"
    RISK = "risk"
    STRATEGIC = "strategic"


class TimeHorizon(str, Enum):
    ONE_YEAR = "1yr"
    THREE_YEAR = "3yr"
    FIVE_YEAR = "5yr"
    TEN_YEAR = "10yr"


@dataclass
class CostLineItem:
    """
    A single line in the cost stack.

    Links a cost to its type, owner(s), source metric(s), and
    calculation formula.
    """
    line_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    cost_type: str = CostType.OPEX.value
    owner_roles: List[str] = field(default_factory=list)

    # Financial
    amount: float = 0.0
    amount_low: float = 0.0
    amount_high: float = 0.0
    currency: str = "USD"
    period: str = "annual"              # "annual", "monthly", "one_time"
    time_horizon: str = HORIZON_LABEL
    discount_rate: float = DISCOUNT_RATE

    # Lineage
    calculation_formula_ref: str = ""    # reference to TranslationRule id
    input_metric_ids: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    data_sources: List[str] = field(default_factory=list)
    confidence: float = 0.5             # 0.0 - 1.0

    # Flags
    is_savings: bool = False             # True = positive impact (savings)
    is_assumption_based: bool = False    # True if data was user-supplied assumption
    missing_inputs: List[str] = field(default_factory=list)

    # Metadata
    quadrant: str = ""
    scenario_id: Optional[str] = None
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def npv(self) -> float:
        """Simple NPV over time horizon."""
        years = _horizon_years(self.time_horizon)
        if self.period == "one_time":
            return self.amount
        if self.discount_rate <= 0:
            return self.amount * years
        factor = sum(1 / (1 + self.discount_rate) ** y for y in range(1, years + 1))
        return round(self.amount * factor, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "line_id": self.line_id,
            "name": self.name,
            "description": self.description,
            "cost_type": self.cost_type,
            "owner_roles": self.owner_roles,
            "amount": self.amount,
            "amount_low": self.amount_low,
            "amount_high": self.amount_high,
            "currency": self.currency,
            "period": self.period,
            "time_horizon": self.time_horizon,
            "discount_rate": self.discount_rate,
            "npv": self.npv,
            "calculation_formula_ref": self.calculation_formula_ref,
            "input_metric_ids": self.input_metric_ids,
            "assumptions": self.assumptions,
            "data_sources": self.data_sources,
            "confidence": self.confidence,
            "is_savings": self.is_savings,
            "is_assumption_based": self.is_assumption_based,
            "missing_inputs": self.missing_inputs,
            "quadrant": self.quadrant,
            "scenario_id": self.scenario_id,
            "created_ts": self.created_ts,
        }


class CostStack:
    """
    Aggregates CostLineItems and provides rollups by cost type,
    owner, quadrant, and time horizon.
    """

    def __init__(self, scenario_id: Optional[str] = None):
        self.scenario_id = scenario_id
        self._lines: List[CostLineItem] = []

    # ── Mutations ───────────────────────────────────────────────────

    def add_line(self, line: CostLineItem) -> CostLineItem:
        if self.scenario_id:
            line.scenario_id = self.scenario_id
        self._lines.append(line)
        return line

    def add_lines(self, lines: List[CostLineItem]):
        for line in lines:
            self.add_line(line)

    def clear(self):
        self._lines.clear()

    @property
    def lines(self) -> List[CostLineItem]:
        return list(self._lines)

    # ── Aggregation ─────────────────────────────────────────────────

    def total(self) -> Dict[str, float]:
        return self._sum_amounts(self._lines)

    def by_cost_type(self) -> Dict[str, Dict[str, float]]:
        result: Dict[str, Dict[str, float]] = {}
        for ct in CostType:
            items = [l for l in self._lines if l.cost_type == ct.value]
            if items:
                result[ct.value] = self._sum_amounts(items)
        return result

    def by_owner(self) -> Dict[str, Dict[str, float]]:
        result: Dict[str, Dict[str, float]] = {}
        for line in self._lines:
            for owner in line.owner_roles:
                if owner not in result:
                    result[owner] = {"amount": 0, "amount_low": 0, "amount_high": 0, "npv": 0, "count": 0}
                weight = 1.0 / len(line.owner_roles) if line.owner_roles else 1.0
                result[owner]["amount"] += line.amount * weight
                result[owner]["amount_low"] += line.amount_low * weight
                result[owner]["amount_high"] += line.amount_high * weight
                result[owner]["npv"] += line.npv * weight
                result[owner]["count"] += 1
        return result

    def by_quadrant(self) -> Dict[str, Dict[str, float]]:
        result: Dict[str, Dict[str, float]] = {}
        for line in self._lines:
            q = line.quadrant or "unclassified"
            if q not in result:
                result[q] = {"amount": 0, "amount_low": 0, "amount_high": 0, "npv": 0, "count": 0}
            result[q]["amount"] += line.amount
            result[q]["amount_low"] += line.amount_low
            result[q]["amount_high"] += line.amount_high
            result[q]["npv"] += line.npv
            result[q]["count"] += 1
        return result

    def savings_lines(self) -> List[CostLineItem]:
        return [l for l in self._lines if l.is_savings]

    def cost_lines(self) -> List[CostLineItem]:
        return [l for l in self._lines if not l.is_savings]

    def missing_data_lines(self) -> List[CostLineItem]:
        return [l for l in self._lines if l.missing_inputs]

    def assumption_based_lines(self) -> List[CostLineItem]:
        return [l for l in self._lines if l.is_assumption_based]

    def year_by_year_cashflow(self, horizon_years: int = 5) -> List[Dict[str, float]]:
        """Generate year-by-year cash flow breakdown."""
        cashflows = []
        for year in range(1, horizon_years + 1):
            year_data: Dict[str, float] = {"year": year}
            for ct in CostType:
                items = [l for l in self._lines if l.cost_type == ct.value]
                annual = 0.0
                for item in items:
                    if item.period == "one_time" and year == 1:
                        annual += item.amount
                    elif item.period != "one_time":
                        discounted = item.amount / (1 + item.discount_rate) ** year
                        annual += discounted
                sign = 1.0 if ct.value in (CostType.OPEX.value, CostType.CAPEX.value) else -1.0
                year_data[f"{ct.value}_cost"] = round(annual, 2)
                # Savings are already marked; costs vs savings handled by is_savings flag
            cashflows.append(year_data)
        return cashflows

    # ── Drill-down ──────────────────────────────────────────────────

    def drill_down(self, line_id: str) -> Optional[Dict[str, Any]]:
        """Full lineage drill-down for a single cost line item."""
        line = next((l for l in self._lines if l.line_id == line_id), None)
        if not line:
            return None
        return {
            "line": line.to_dict(),
            "lineage": {
                "metric_ids": line.input_metric_ids,
                "formula_ref": line.calculation_formula_ref,
                "data_sources": line.data_sources,
                "assumptions": line.assumptions,
                "confidence": line.confidence,
                "is_assumption_based": line.is_assumption_based,
                "missing_inputs": line.missing_inputs,
            },
        }

    # ── Serialization ───────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "line_count": len(self._lines),
            "total": self.total(),
            "by_cost_type": self.by_cost_type(),
            "by_owner": self.by_owner(),
            "by_quadrant": self.by_quadrant(),
            "lines": [l.to_dict() for l in self._lines],
            "missing_data_count": len(self.missing_data_lines()),
            "assumption_based_count": len(self.assumption_based_lines()),
        }

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _sum_amounts(items: List[CostLineItem]) -> Dict[str, float]:
        return {
            "amount": round(sum(l.amount for l in items), 2),
            "amount_low": round(sum(l.amount_low for l in items), 2),
            "amount_high": round(sum(l.amount_high for l in items), 2),
            "npv": round(sum(l.npv for l in items), 2),
            "count": len(items),
        }


def _horizon_years(horizon: str) -> int:
    mapping = {
        TimeHorizon.ONE_YEAR.value: 1,
        TimeHorizon.THREE_YEAR.value: 3,
        TimeHorizon.FIVE_YEAR.value: 5,
        TimeHorizon.TEN_YEAR.value: 10,
    }
    return mapping.get(horizon, 3)
