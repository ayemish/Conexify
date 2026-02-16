"""
Attribution Ledger — tracks every dollar of savings back to its source
with precedence rules and double-counting controls.

Each savings entry carries: kpi_source, asset_id/location_id,
savings_type, amount, period, evidence_refs[].
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class AttributionEntry:
    """A single savings attribution record."""
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    kpi_source: str = ""
    asset_id: Optional[str] = None
    location_id: Optional[str] = None
    savings_type: str = ""
    amount_low: float = 0.0
    amount_medium: float = 0.0
    amount_high: float = 0.0
    period: str = "annual"
    confidence: float = 0.0
    evidence_refs: List[Dict[str, Any]] = field(default_factory=list)
    scenario_id: Optional[str] = None
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    adjusted: bool = False
    adjustment_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
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
            "scenario_id": self.scenario_id,
            "created_ts": self.created_ts,
            "adjusted": self.adjusted,
            "adjustment_reason": self.adjustment_reason,
        }


# Savings type hierarchy for precedence
SAVINGS_TYPE_PRECEDENCE = {
    "energy": ["energy_reduction", "refrigerant_leak_reduction", "preventive_maintenance_optimization"],
    "labor": ["work_order_reduction", "ppm_maximization", "service_bureau_reduction"],
    "refrigerant": ["refrigerant_leak_reduction"],
    "compliance": ["food_safety_compliance", "esg_compliance"],
    "waste": ["food_waste_reduction"],
    "call_center": ["call_center_volume_reduction"],
    "capex": ["capex_lifecycle_optimization"],
    "emissions": ["esg_compliance"],
}


class AttributionLedger:
    """
    Maintains audit-ready savings attribution with double-counting controls.
    
    Every savings dollar is tracked to a single KPI source. Precedence rules
    determine which KPI gets credit when multiple KPIs claim the same savings.
    """

    def __init__(self, policy: str = "first_claim"):
        """
        Args:
            policy: "first_claim" | "split" | "highest_confidence" | "precedence_table"
        """
        self.policy = policy
        self._entries: List[AttributionEntry] = []
        self._adjustments: List[Dict[str, Any]] = []

    def add_entry(self, entry: AttributionEntry) -> Tuple[bool, Optional[str]]:
        """
        Add a savings attribution entry.
        
        Returns (accepted, reason). If rejected due to double-counting,
        reason explains why.
        """
        conflicts = self._find_overlapping(entry)

        if not conflicts:
            self._entries.append(entry)
            return True, None

        if self.policy == "first_claim":
            reason = f"Rejected: first_claim policy, {conflicts[0].kpi_source} already claimed {entry.savings_type}"
            self._adjustments.append({
                "type": "rejected",
                "entry": entry.to_dict(),
                "conflict_with": conflicts[0].entry_id,
                "reason": reason,
            })
            return False, reason

        elif self.policy == "highest_confidence":
            for conflict in conflicts:
                if entry.confidence > conflict.confidence:
                    self._entries.remove(conflict)
                    conflict.adjusted = True
                    conflict.adjustment_reason = f"Superseded by {entry.kpi_source} (higher confidence)"
                    self._adjustments.append({
                        "type": "superseded",
                        "removed": conflict.to_dict(),
                        "replaced_by": entry.entry_id,
                    })
                    self._entries.append(entry)
                    return True, None
                else:
                    reason = f"Rejected: lower confidence than {conflict.kpi_source}"
                    return False, reason

        elif self.policy == "split":
            factor = 1.0 / (len(conflicts) + 1)
            entry.amount_low *= factor
            entry.amount_medium *= factor
            entry.amount_high *= factor
            entry.adjusted = True
            entry.adjustment_reason = f"Split {factor:.0%} with {len(conflicts)} conflicting entries"
            for conflict in conflicts:
                conflict.amount_low *= factor * len(conflicts)
                conflict.amount_medium *= factor * len(conflicts)
                conflict.amount_high *= factor * len(conflicts)
                conflict.adjusted = True
                conflict.adjustment_reason = f"Split adjusted for overlap with {entry.kpi_source}"
            self._entries.append(entry)
            self._adjustments.append({
                "type": "split",
                "new_entry": entry.entry_id,
                "conflicts": [c.entry_id for c in conflicts],
                "split_factor": factor,
            })
            return True, f"Split {factor:.0%}"

        elif self.policy == "precedence_table":
            precedence = SAVINGS_TYPE_PRECEDENCE.get(entry.savings_type, [])
            for conflict in conflicts:
                entry_rank = precedence.index(entry.kpi_source) if entry.kpi_source in precedence else 999
                conflict_rank = precedence.index(conflict.kpi_source) if conflict.kpi_source in precedence else 999
                if entry_rank < conflict_rank:
                    self._entries.remove(conflict)
                    self._entries.append(entry)
                    self._adjustments.append({
                        "type": "precedence_override",
                        "winner": entry.kpi_source,
                        "loser": conflict.kpi_source,
                        "savings_type": entry.savings_type,
                    })
                    return True, None
            return False, f"Lower precedence than existing entry for {entry.savings_type}"

        self._entries.append(entry)
        return True, None

    def _find_overlapping(self, entry: AttributionEntry) -> List[AttributionEntry]:
        """Find entries that overlap with the given entry (same savings type + scope)."""
        overlapping = []
        for existing in self._entries:
            if (existing.savings_type == entry.savings_type and
                existing.kpi_source != entry.kpi_source and
                existing.scenario_id == entry.scenario_id):
                # Check scope overlap
                if entry.asset_id and existing.asset_id:
                    if entry.asset_id == existing.asset_id:
                        overlapping.append(existing)
                elif entry.location_id and existing.location_id:
                    if entry.location_id == existing.location_id:
                        overlapping.append(existing)
                elif not entry.asset_id and not entry.location_id:
                    overlapping.append(existing)
        return overlapping

    def get_total_by_category(self, scenario_id: Optional[str] = None) -> Dict[str, Dict[str, float]]:
        """Get totals grouped by savings category."""
        entries = self._entries
        if scenario_id:
            entries = [e for e in entries if e.scenario_id == scenario_id]

        by_cat: Dict[str, Dict[str, float]] = {}
        for entry in entries:
            cat = entry.savings_type or entry.kpi_source
            if cat not in by_cat:
                by_cat[cat] = {"low": 0, "medium": 0, "high": 0}
            by_cat[cat]["low"] += entry.amount_low
            by_cat[cat]["medium"] += entry.amount_medium
            by_cat[cat]["high"] += entry.amount_high
        return by_cat

    def get_total_by_kpi(self, scenario_id: Optional[str] = None) -> Dict[str, Dict[str, float]]:
        """Get totals grouped by KPI source."""
        entries = self._entries
        if scenario_id:
            entries = [e for e in entries if e.scenario_id == scenario_id]

        by_kpi: Dict[str, Dict[str, float]] = {}
        for entry in entries:
            kpi = entry.kpi_source
            if kpi not in by_kpi:
                by_kpi[kpi] = {"low": 0, "medium": 0, "high": 0}
            by_kpi[kpi]["low"] += entry.amount_low
            by_kpi[kpi]["medium"] += entry.amount_medium
            by_kpi[kpi]["high"] += entry.amount_high
        return by_kpi

    def get_grand_totals(self, scenario_id: Optional[str] = None) -> Dict[str, float]:
        """Get grand totals across all categories."""
        by_cat = self.get_total_by_category(scenario_id)
        return {
            "total_low": sum(v["low"] for v in by_cat.values()),
            "total_medium": sum(v["medium"] for v in by_cat.values()),
            "total_high": sum(v["high"] for v in by_cat.values()),
        }

    def get_audit_trail(self) -> List[Dict[str, Any]]:
        """Get full audit trail of all entries and adjustments."""
        return {
            "entries": [e.to_dict() for e in self._entries],
            "adjustments": self._adjustments,
            "policy": self.policy,
            "entry_count": len(self._entries),
            "adjustment_count": len(self._adjustments),
        }

    def to_report_lines(self, scenario_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Generate report-ready savings lines matching the FRD rollup structure:
        - Workorder Reduction
        - 3rd Party Job Reduction
        - Gas Leak Reduction
        - Energy Saving
        - Store Manager Productivity
        - Call Center Cost Productivity
        - Shrink Reduction
        - PPM Savings
        """
        REPORT_LINE_MAP = {
            "Workorder Reduction": ["work_order_reduction"],
            "3rd Party Job Reduction": ["service_bureau_reduction"],
            "Gas Leak Reduction": ["refrigerant_leak_reduction"],
            "Energy Saving": ["energy_reduction"],
            "Store Manager Productivity": ["asset_uptime_increase", "food_temp_diagnostics_improvement"],
            "Call Center Cost Productivity": ["call_center_volume_reduction"],
            "Shrink Reduction": ["food_waste_reduction"],
            "PPM Savings": ["ppm_maximization", "preventive_maintenance_optimization"],
            "Food Safety Compliance": ["food_safety_compliance"],
            "ESG Compliance": ["esg_compliance"],
            "Asset Failure Prevention": ["asset_failure_prediction"],
            "CapEx Optimization": ["capex_lifecycle_optimization"],
        }

        by_kpi = self.get_total_by_kpi(scenario_id)
        lines = []

        for line_name, kpi_sources in REPORT_LINE_MAP.items():
            low = sum(by_kpi.get(kpi, {}).get("low", 0) for kpi in kpi_sources)
            med = sum(by_kpi.get(kpi, {}).get("medium", 0) for kpi in kpi_sources)
            high = sum(by_kpi.get(kpi, {}).get("high", 0) for kpi in kpi_sources)
            if med > 0 or low > 0 or high > 0:
                lines.append({
                    "line_name": line_name,
                    "savings_low": low,
                    "savings_medium": med,
                    "savings_high": high,
                    "kpi_sources": kpi_sources,
                })

        return lines
