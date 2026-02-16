"""
Decision Ledger — central record of all KPI outputs, recommendations,
and savings attributions used by the orchestration crew.

Resolves overlaps/double-counting and maintains a reconciled view
of cross-KPI impacts.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class SavingsAttribution:
    """
    A single savings claim in the attribution ledger.
    
    Every dollar of savings is attributed to exactly one KPI source,
    preventing double-counting across KPI crews.
    """
    attribution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    kpi_source: str = ""
    asset_id: Optional[str] = None
    location_id: Optional[str] = None
    savings_type: str = ""  # "energy", "labor", "parts", "refrigerant", "compliance", "waste"
    amount_low: float = 0.0
    amount_medium: float = 0.0
    amount_high: float = 0.0
    period: str = "annual"
    confidence: float = 0.0
    evidence_refs: List[Dict[str, Any]] = field(default_factory=list)
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attribution_id": self.attribution_id,
            "kpi_source": self.kpi_source,
            "asset_id": self.asset_id,
            "location_id": self.location_id,
            "savings_type": self.savings_type,
            "amount_low": self.amount_low,
            "amount_medium": self.amount_medium,
            "amount_high": self.amount_high,
            "period": self.period,
            "confidence": self.confidence,
            "evidence_refs": self.evidence_refs,
            "created_ts": self.created_ts,
        }


@dataclass
class Recommendation:
    """A ranked recommendation from the orchestration process."""
    recommendation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    category: str = ""  # "quick_win", "structural_fix", "capex_replacement", "policy_change"
    priority_rank: int = 0
    asset_ids: List[str] = field(default_factory=list)
    location_ids: List[str] = field(default_factory=list)
    kpi_impacts: Dict[str, float] = field(default_factory=dict)
    estimated_savings: float = 0.0
    estimated_cost: float = 0.0
    payback_months: Optional[float] = None
    confidence: float = 0.0
    evidence_summary: str = ""
    validation_checklist: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "priority_rank": self.priority_rank,
            "asset_ids": self.asset_ids,
            "location_ids": self.location_ids,
            "kpi_impacts": self.kpi_impacts,
            "estimated_savings": self.estimated_savings,
            "estimated_cost": self.estimated_cost,
            "payback_months": self.payback_months,
            "confidence": self.confidence,
            "evidence_summary": self.evidence_summary,
            "validation_checklist": self.validation_checklist,
        }


# Double-counting precedence rules
DOUBLE_COUNT_PRECEDENCE = {
    # (savings_type, kpi_a, kpi_b) -> winner
    ("energy", "energy_reduction", "refrigerant_leak_reduction"): "energy_reduction",
    ("energy", "energy_reduction", "preventive_maintenance_optimization"): "energy_reduction",
    ("labor", "work_order_reduction", "ppm_maximization"): "work_order_reduction",
    ("labor", "work_order_reduction", "service_bureau_reduction"): "work_order_reduction",
    ("compliance", "food_safety_compliance", "food_temp_diagnostics_improvement"): "food_safety_compliance",
    ("waste", "food_waste_reduction", "food_safety_compliance"): "food_waste_reduction",
    ("emissions", "esg_compliance", "energy_reduction"): "esg_compliance",
    ("emissions", "esg_compliance", "refrigerant_leak_reduction"): "esg_compliance",
}


class DecisionLedger:
    """
    Central ledger that collects KPI outputs, resolves double-counting,
    and maintains reconciled savings totals.
    
    Supports multiple scenarios with independent attribution records.
    """

    def __init__(self, double_counting_policy: str = "first_claim"):
        """
        Args:
            double_counting_policy: "first_claim" | "split" | "highest_confidence"
        """
        self.double_counting_policy = double_counting_policy
        # KPI results indexed by kpi_name
        self._kpi_results: Dict[str, Dict[str, Any]] = {}
        # Attribution ledger
        self._attributions: List[SavingsAttribution] = []
        # Recommendations
        self._recommendations: List[Recommendation] = []
        # Double-counting adjustments log
        self._adjustments: List[Dict[str, Any]] = []
        # Scenario isolation
        self._scenario_id: Optional[str] = None

    def set_scenario(self, scenario_id: str):
        self._scenario_id = scenario_id

    def register_kpi_result(self, kpi_name: str, result: Dict[str, Any]):
        """Register a completed KPI crew result."""
        self._kpi_results[kpi_name] = result
        logger.info(f"Registered KPI result: {kpi_name} (savings_med=${result.get('savings_medium', 0):,.0f})")

    def add_attribution(self, attr: SavingsAttribution):
        """Add a savings attribution, checking for double-counting."""
        conflicts = self._find_conflicts(attr)
        if conflicts:
            resolved = self._resolve_conflicts(attr, conflicts)
            if resolved:
                self._attributions.append(resolved)
        else:
            self._attributions.append(attr)

    def _find_conflicts(self, new_attr: SavingsAttribution) -> List[SavingsAttribution]:
        """Find existing attributions that overlap with the new one."""
        conflicts = []
        for existing in self._attributions:
            if (existing.savings_type == new_attr.savings_type and
                existing.asset_id == new_attr.asset_id and
                existing.location_id == new_attr.location_id and
                existing.kpi_source != new_attr.kpi_source):
                conflicts.append(existing)
        return conflicts

    def _resolve_conflicts(
        self, new_attr: SavingsAttribution, conflicts: List[SavingsAttribution]
    ) -> Optional[SavingsAttribution]:
        """Resolve double-counting based on policy."""
        for conflict in conflicts:
            key = (new_attr.savings_type, new_attr.kpi_source, conflict.kpi_source)
            rev_key = (new_attr.savings_type, conflict.kpi_source, new_attr.kpi_source)

            if self.double_counting_policy == "first_claim":
                # First registered wins
                self._adjustments.append({
                    "type": "first_claim_rejection",
                    "rejected_kpi": new_attr.kpi_source,
                    "kept_kpi": conflict.kpi_source,
                    "savings_type": new_attr.savings_type,
                    "rejected_amount": new_attr.amount_medium,
                })
                return None

            elif self.double_counting_policy == "highest_confidence":
                if new_attr.confidence > conflict.confidence:
                    self._attributions.remove(conflict)
                    self._adjustments.append({
                        "type": "confidence_override",
                        "winner": new_attr.kpi_source,
                        "loser": conflict.kpi_source,
                        "savings_type": new_attr.savings_type,
                    })
                    return new_attr
                else:
                    self._adjustments.append({
                        "type": "confidence_rejection",
                        "rejected_kpi": new_attr.kpi_source,
                        "kept_kpi": conflict.kpi_source,
                    })
                    return None

            elif self.double_counting_policy == "split":
                # Split 50/50
                new_attr.amount_low *= 0.5
                new_attr.amount_medium *= 0.5
                new_attr.amount_high *= 0.5
                conflict.amount_low *= 0.5
                conflict.amount_medium *= 0.5
                conflict.amount_high *= 0.5
                self._adjustments.append({
                    "type": "split",
                    "kpis": [new_attr.kpi_source, conflict.kpi_source],
                    "savings_type": new_attr.savings_type,
                })
                return new_attr

            else:
                # Check precedence table
                winner = DOUBLE_COUNT_PRECEDENCE.get(key) or DOUBLE_COUNT_PRECEDENCE.get(rev_key)
                if winner == new_attr.kpi_source:
                    self._attributions.remove(conflict)
                    return new_attr
                elif winner == conflict.kpi_source:
                    return None
                else:
                    return None  # Default: first claim wins

        return new_attr

    def build_attributions_from_kpi_results(self):
        """Auto-generate attribution entries from registered KPI results."""
        for kpi_name, result in self._kpi_results.items():
            attr = SavingsAttribution(
                kpi_source=kpi_name,
                savings_type=result.get("savings_category", kpi_name),
                amount_low=result.get("savings_low", 0),
                amount_medium=result.get("savings_medium", 0),
                amount_high=result.get("savings_high", 0),
                confidence=result.get("confidence", 0),
                evidence_refs=result.get("evidence_refs", []),
            )
            self.add_attribution(attr)

    def get_reconciled_totals(self) -> Dict[str, Any]:
        """Get reconciled savings totals after double-counting resolution."""
        by_category: Dict[str, Dict[str, float]] = {}
        for attr in self._attributions:
            cat = attr.savings_type or attr.kpi_source
            if cat not in by_category:
                by_category[cat] = {"low": 0, "medium": 0, "high": 0}
            by_category[cat]["low"] += attr.amount_low
            by_category[cat]["medium"] += attr.amount_medium
            by_category[cat]["high"] += attr.amount_high

        total_low = sum(v["low"] for v in by_category.values())
        total_medium = sum(v["medium"] for v in by_category.values())
        total_high = sum(v["high"] for v in by_category.values())

        return {
            "by_category": by_category,
            "total_savings_low": total_low,
            "total_savings_medium": total_medium,
            "total_savings_high": total_high,
            "adjustments": self._adjustments,
            "attribution_count": len(self._attributions),
            "scenario_id": self._scenario_id,
        }

    def add_recommendation(self, rec: Recommendation):
        self._recommendations.append(rec)

    def get_ranked_recommendations(self) -> List[Dict[str, Any]]:
        """Get recommendations sorted by priority rank."""
        sorted_recs = sorted(self._recommendations, key=lambda r: r.priority_rank)
        return [r.to_dict() for r in sorted_recs]

    def get_naive_totals(self) -> Dict[str, float]:
        """Get naive (un-reconciled) totals for comparison."""
        total_low = sum(r.get("savings_low", 0) for r in self._kpi_results.values())
        total_med = sum(r.get("savings_medium", 0) for r in self._kpi_results.values())
        total_high = sum(r.get("savings_high", 0) for r in self._kpi_results.values())
        return {"naive_low": total_low, "naive_medium": total_med, "naive_high": total_high}

    def get_reconciliation_explanation(self) -> str:
        """Explain why reconciled totals differ from naive sums."""
        naive = self.get_naive_totals()
        reconciled = self.get_reconciled_totals()
        diff = naive["naive_medium"] - reconciled["total_savings_medium"]

        if abs(diff) < 1.0:
            return "No double-counting adjustments were needed."

        lines = [
            f"Naive total (medium): ${naive['naive_medium']:,.0f}",
            f"Reconciled total (medium): ${reconciled['total_savings_medium']:,.0f}",
            f"Adjustment: ${diff:,.0f} ({len(self._adjustments)} adjustments)",
            "",
            "Adjustments applied:",
        ]
        for adj in self._adjustments:
            lines.append(f"  - {adj['type']}: {adj}")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kpi_results": {k: v for k, v in self._kpi_results.items()},
            "attributions": [a.to_dict() for a in self._attributions],
            "recommendations": [r.to_dict() for r in self._recommendations],
            "reconciled_totals": self.get_reconciled_totals(),
            "naive_totals": self.get_naive_totals(),
            "adjustments": self._adjustments,
            "scenario_id": self._scenario_id,
        }

    def clear(self):
        self._kpi_results.clear()
        self._attributions.clear()
        self._recommendations.clear()
        self._adjustments.clear()
        self._scenario_id = None
