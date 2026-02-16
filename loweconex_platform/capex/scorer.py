"""
Asset Scorer — multi-factor priority scoring for CapEx decisions.

Combines condition, risk, energy waste, fault burden, and maintenance
escalation into a single replace-priority score (0-100).

Ported from CapEx Generator featureCalculator.js scoring logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


DECISION_TYPES = {
    "REPLACE": "REPLACE",
    "DEFER": "DEFER",
    "INSPECT": "INSPECT",
    "REPAIR": "REPAIR",
}


@dataclass
class AssetScore:
    """Composite score for a single asset."""
    condition_score: float = 50.0
    risk_score: float = 50.0
    energy_waste_score: float = 50.0
    replace_priority_score: float = 50.0
    is_scoreable: bool = True
    explain_top_drivers: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "condition_score": self.condition_score,
            "risk_score": self.risk_score,
            "energy_waste_score": self.energy_waste_score,
            "replace_priority_score": self.replace_priority_score,
            "is_scoreable": self.is_scoreable,
            "explain_top_drivers": self.explain_top_drivers,
        }


class AssetScorer:
    """Score assets for CapEx prioritization."""

    @staticmethod
    def score(
        asset: Dict[str, Any],
        health_data: Optional[Dict[str, Any]] = None,
        survival_result: Optional[Dict[str, Any]] = None,
        fault_result: Optional[Dict[str, Any]] = None,
        energy_waste: Optional[Dict[str, Any]] = None,
        peer_percentile: int = 50,
    ) -> AssetScore:
        """Compute composite replacement priority score.

        Parameters
        ----------
        asset : dict with age_years, asset_type, etc.
        health_data : PdM health index (health_score, degradation_score, rul_hours)
        survival_result : SurvivalResult.to_dict()
        fault_result : fault detection summary
        energy_waste : energy waste summary
        peer_percentile : peer comparison percentile (0-100)
        """
        health = health_data or {}
        survival = survival_result or {}
        faults = fault_result or {}
        ewaste = energy_waste or {}

        age = asset.get("age_years", 5)
        health_score = health.get("health_score", 80)
        degradation = health.get("degradation_score", 10)

        # ── Condition Score (0-100, higher = worse condition) ─────
        age_factor = min(100, age * 5)  # 20yr → 100
        health_factor = 100 - health_score
        condition_score = round(age_factor * 0.4 + health_factor * 0.4 + degradation * 0.2)
        condition_score = min(100, max(0, condition_score))

        # ── Risk Score (0-100) ───────────────────────────────────
        survival_risk = survival.get("risk_score", 30)
        fault_burden = faults.get("fault_burden_score", 0)
        risk_score = min(100, round(survival_risk * 0.6 + fault_burden * 0.4))

        # ── Energy Waste Score (0-100) ───────────────────────────
        waste_percentile = ewaste.get("waste_percentile", 50)
        energy_waste_score = min(100, max(0, round(waste_percentile)))

        # ── Maintenance Cost Trend ───────────────────────────────
        maint_annual = health.get("annual_maintenance_cost", 0)
        maint_factor = min(100, maint_annual / 100 * 20) if maint_annual > 0 else 0

        # ── Replace Priority Score ───────────────────────────────
        priority = round(
            (100 - condition_score) * 0.0  # inverted: high condition_score = bad = high priority
            + condition_score * 0.20
            + energy_waste_score * 0.25
            + risk_score * 0.35
            + maint_factor * 0.20
        )
        priority = min(100, max(0, priority))

        # ── Top Drivers ──────────────────────────────────────────
        drivers: List[str] = []
        if age >= 12:
            drivers.append(f"Asset age ({age} years) exceeds typical service life")
        if health_score < 50:
            drivers.append(f"Poor health score ({health_score})")
        if survival_risk >= 60:
            drivers.append(f"High failure risk (risk score {survival_risk})")
        if fault_burden > 40:
            drivers.append(f"Active fault burden ({fault_burden})")
        if waste_percentile > 70:
            drivers.append(f"High energy waste (P{waste_percentile})")
        if peer_percentile < 25:
            drivers.append(f"Below-average peer comparison (P{peer_percentile})")
        if maint_annual > 3000:
            drivers.append(f"Escalating maintenance (${maint_annual:,.0f}/yr)")
        if degradation > 50:
            drivers.append(f"Significant degradation ({degradation}%)")

        return AssetScore(
            condition_score=condition_score,
            risk_score=risk_score,
            energy_waste_score=energy_waste_score,
            replace_priority_score=priority,
            is_scoreable=True,
            explain_top_drivers=drivers[:5],
        )

    @staticmethod
    def recommend_decision(
        asset: Dict[str, Any],
        score: AssetScore,
        best_option: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """Generate a replacement recommendation based on score + economics."""
        if not score.is_scoreable:
            return {
                "decision": DECISION_TYPES["INSPECT"],
                "reason": "Insufficient data coverage for reliable scoring",
            }

        npv = best_option.get("npv", 0) if best_option else 0
        payback = best_option.get("simple_payback", 999) if best_option else 999

        if score.replace_priority_score >= 70 and best_option and npv > 0:
            return {
                "decision": DECISION_TYPES["REPLACE"],
                "reason": (
                    f"High priority score ({score.replace_priority_score}) "
                    f"with positive NPV (${npv:,.0f})"
                ),
            }

        if score.risk_score >= 60 and score.condition_score >= 60:
            return {
                "decision": DECISION_TYPES["REPLACE"],
                "reason": (
                    f"High risk ({score.risk_score}) and poor condition "
                    f"({score.condition_score})"
                ),
            }

        if 40 <= score.replace_priority_score < 70:
            if best_option and npv > 0 and payback <= 7:
                return {
                    "decision": DECISION_TYPES["REPLACE"],
                    "reason": f"Moderate priority with good payback ({payback} years)",
                }
            if best_option and npv > 0:
                return {
                    "decision": DECISION_TYPES["INSPECT"],
                    "reason": (
                        f"Moderate priority score ({score.replace_priority_score}) "
                        f"with positive NPV (${npv:,.0f}) — recommend inspection"
                    ),
                }
            return {
                "decision": DECISION_TYPES["INSPECT"],
                "reason": (
                    f"Moderate priority score ({score.replace_priority_score}) "
                    "— recommend inspection"
                ),
            }

        age = asset.get("age_years", 0)
        if age >= 12 and score.condition_score >= 40:
            return {
                "decision": DECISION_TYPES["INSPECT"],
                "reason": f"Age ({age} years) warrants inspection",
            }

        return {
            "decision": DECISION_TYPES["DEFER"],
            "reason": (
                f"Low priority score ({score.replace_priority_score}) "
                "— continue monitoring"
            ),
        }
