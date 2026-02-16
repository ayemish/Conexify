"""
Cost Model — models program costs for ROI computation.

Costs include software license, implementation, managed services,
and optional hardware. Supports first-year ramp/rollout scheduling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CostLineItem:
    """A single cost line item."""
    name: str
    category: str  # "software", "implementation", "managed_services", "hardware"
    amount_year1: float = 0.0
    amount_recurring: float = 0.0  # annual after year 1
    is_one_time: bool = False
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "amount_year1": self.amount_year1,
            "amount_recurring": self.amount_recurring,
            "is_one_time": self.is_one_time,
            "notes": self.notes,
        }


@dataclass
class ProgramCosts:
    """Complete program cost structure."""
    line_items: List[CostLineItem] = field(default_factory=list)
    analysis_years: int = 3
    rollout_months: int = 12
    location_count: int = 1

    # First-year ramp schedule (monthly multipliers, 0-1)
    ramp_schedule: List[float] = field(default_factory=lambda: [
        0.08, 0.17, 0.25, 0.33, 0.42, 0.50,
        0.58, 0.67, 0.75, 0.83, 0.92, 1.00
    ])

    def add_item(self, item: CostLineItem):
        self.line_items.append(item)

    def total_year1(self) -> float:
        return sum(item.amount_year1 for item in self.line_items)

    def total_recurring(self) -> float:
        return sum(item.amount_recurring for item in self.line_items if not item.is_one_time)

    def total_3year(self) -> float:
        return self.total_year1() + self.total_recurring() * (self.analysis_years - 1)

    def by_category(self) -> Dict[str, float]:
        cats: Dict[str, float] = {}
        for item in self.line_items:
            cats[item.category] = cats.get(item.category, 0) + item.amount_year1
        return cats

    def monthly_cost_year1(self) -> List[float]:
        """Monthly cost schedule for year 1 accounting for ramp."""
        monthly_base = self.total_year1() / 12
        return [monthly_base * mult for mult in self.ramp_schedule[:12]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "line_items": [item.to_dict() for item in self.line_items],
            "total_year1": self.total_year1(),
            "total_recurring": self.total_recurring(),
            "total_3year": self.total_3year(),
            "by_category": self.by_category(),
            "analysis_years": self.analysis_years,
            "rollout_months": self.rollout_months,
            "location_count": self.location_count,
        }


class CostModel:
    """
    Builds program cost structures from configuration.
    
    Default cost templates are provided but can be overridden
    with actual vendor quotes and customer-specific rates.
    """

    @staticmethod
    def build_default_costs(
        location_count: int = 100,
        asset_count: int = 5000,
        analysis_years: int = 3,
    ) -> ProgramCosts:
        """Build default program costs scaled by location/asset count."""
        costs = ProgramCosts(
            analysis_years=analysis_years,
            location_count=location_count,
        )

        # Software license (per-location pricing)
        per_loc_monthly = 200.0
        costs.add_item(CostLineItem(
            name="Platform Software License",
            category="software",
            amount_year1=location_count * per_loc_monthly * 12,
            amount_recurring=location_count * per_loc_monthly * 12,
            notes=f"${per_loc_monthly}/location/month x {location_count} locations",
        ))

        # Implementation / professional services (one-time)
        impl_per_loc = 500.0
        costs.add_item(CostLineItem(
            name="Implementation & Professional Services",
            category="implementation",
            amount_year1=location_count * impl_per_loc,
            amount_recurring=0,
            is_one_time=True,
            notes=f"${impl_per_loc}/location one-time",
        ))

        # Data integration setup (one-time)
        costs.add_item(CostLineItem(
            name="Data Integration & Mapping",
            category="implementation",
            amount_year1=50_000,
            amount_recurring=0,
            is_one_time=True,
            notes="One-time data integration, schema mapping, identity resolution",
        ))

        # Managed services / ongoing support
        support_annual = max(50_000, location_count * 50)
        costs.add_item(CostLineItem(
            name="Managed Services & Support",
            category="managed_services",
            amount_year1=support_annual,
            amount_recurring=support_annual,
            notes="Ongoing platform support, model updates, report generation",
        ))

        # Optional hardware (leak detection sensors, power meters)
        hw_per_loc = 1_000.0
        coverage_pct = 0.3  # 30% of locations get hardware
        costs.add_item(CostLineItem(
            name="Hardware Sensors (optional)",
            category="hardware",
            amount_year1=int(location_count * coverage_pct) * hw_per_loc,
            amount_recurring=int(location_count * coverage_pct) * hw_per_loc * 0.10,
            notes=f"Leak detection + power metering for {coverage_pct*100:.0f}% of locations",
        ))

        return costs

    @staticmethod
    def build_custom_costs(
        line_items: List[Dict[str, Any]],
        analysis_years: int = 3,
        location_count: int = 1,
    ) -> ProgramCosts:
        """Build costs from custom line items."""
        costs = ProgramCosts(
            analysis_years=analysis_years,
            location_count=location_count,
        )
        for item_dict in line_items:
            costs.add_item(CostLineItem(**item_dict))
        return costs
