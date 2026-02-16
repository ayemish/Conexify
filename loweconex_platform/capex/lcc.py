"""
Life-Cycle Cost Analysis Engine — ASTM E917 compliant.

Provides:
- Keep vs Replace LCC comparison
- Equivalent Annual Cost (EAC) for cross-lifespan comparison
- Probabilistic NPV via Monte Carlo simulation
- Discounted payback, IRR, and confidence levels

Ported from CapEx Generator enhancedLCC.js + economicEvaluation.js.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ─── Financial Primitives ────────────────────────────────────────────


def present_value(future_value: float, discount_rate: float, year: int) -> float:
    """PV of a single future cash flow."""
    return future_value / ((1 + discount_rate) ** year)


def present_value_annuity(annual_payment: float, discount_rate: float, years: int) -> float:
    """PV of equal annual payments."""
    if discount_rate == 0:
        return annual_payment * years
    return annual_payment * (1 - (1 + discount_rate) ** (-years)) / discount_rate


def equivalent_annual_cost(npv: float, discount_rate: float, years: int) -> float:
    """Annualize a net present value for cross-lifespan comparison."""
    if years == 0:
        return 0.0
    if discount_rate == 0:
        return npv / years
    annuity_factor = (1 - (1 + discount_rate) ** (-years)) / discount_rate
    return npv / annuity_factor


def capital_recovery_factor(discount_rate: float, years: int) -> float:
    if years == 0:
        return 0.0
    if discount_rate == 0:
        return 1.0 / years
    return (discount_rate * (1 + discount_rate) ** years) / ((1 + discount_rate) ** years - 1)


# ─── Keep LCC ────────────────────────────────────────────────────────


@dataclass
class KeepLCCParams:
    current_age: int = 5
    energy_cost_per_year: float = 10_000.0
    maintenance_cost_per_year: float = 2_000.0
    failure_probabilities: Dict[str, float] = field(default_factory=lambda: {"p1y": 0.1})
    failure_event_cost: float = 15_000.0
    discount_rate: float = 0.08
    energy_escalation: float = 0.03
    maintenance_escalation: float = 0.04
    horizon: int = 10


@dataclass
class KeepLCCResult:
    scenario: str = "keep"
    initial_cost: float = 0.0
    pv_operating_costs: float = 0.0
    pv_total: float = 0.0
    eac: float = 0.0
    annual_costs: List[Dict[str, Any]] = field(default_factory=list)
    horizon: int = 10
    discount_rate: float = 0.08

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario": self.scenario,
            "initial_cost": self.initial_cost,
            "pv_operating_costs": self.pv_operating_costs,
            "pv_total": self.pv_total,
            "eac": self.eac,
            "horizon": self.horizon,
            "annual_costs": self.annual_costs,
        }


def compute_keep_lcc(params: KeepLCCParams) -> KeepLCCResult:
    """Comprehensive LCC for the 'Keep' scenario."""
    annual_costs = []
    pv_total = 0.0
    cumulative_survival = 1.0

    for year in range(1, params.horizon + 1):
        age_factor = 1 + 0.02 * (params.current_age + year - 1)

        escalated_energy = (
            params.energy_cost_per_year
            * ((1 + params.energy_escalation) ** (year - 1))
            * age_factor
        )
        escalated_maint = (
            params.maintenance_cost_per_year
            * ((1 + params.maintenance_escalation) ** (year - 1))
            * age_factor
        )

        p_fail = params.failure_probabilities.get(
            f"year{year}",
            params.failure_probabilities.get("p1y", 0.1) * (1 + 0.1 * (year - 1)),
        )
        expected_failure = p_fail * params.failure_event_cost * cumulative_survival
        cumulative_survival *= 1 - p_fail

        total_year = escalated_energy + escalated_maint + expected_failure
        pv_year = present_value(total_year, params.discount_rate, year)
        pv_total += pv_year

        annual_costs.append({
            "year": year,
            "energy_cost": round(escalated_energy),
            "maintenance_cost": round(escalated_maint),
            "expected_failure_cost": round(expected_failure),
            "total_cost": round(total_year),
            "pv_cost": round(pv_year),
            "cumulative_survival": round(cumulative_survival, 3),
        })

    eac = equivalent_annual_cost(pv_total, params.discount_rate, params.horizon)

    return KeepLCCResult(
        pv_operating_costs=round(pv_total),
        pv_total=round(pv_total),
        eac=round(eac),
        annual_costs=annual_costs,
        horizon=params.horizon,
        discount_rate=params.discount_rate,
    )


# ─── Replace LCC ─────────────────────────────────────────────────────


@dataclass
class ReplaceLCCParams:
    capex: float = 20_000.0
    new_equipment_life: int = 15
    new_energy_cost_per_year: float = 7_000.0
    new_maintenance_cost_per_year: float = 1_000.0
    new_failure_probability: float = 0.02
    failure_event_cost: float = 15_000.0
    discount_rate: float = 0.08
    energy_escalation: float = 0.03
    maintenance_escalation: float = 0.03
    horizon: int = 10
    salvage_value_pct: float = 0.1
    warranty_years: int = 1
    # used by Monte Carlo perturbation
    efficiency_gain: float = 0.15


@dataclass
class ReplaceLCCResult:
    scenario: str = "replace"
    initial_cost: float = 0.0
    pv_operating_costs: float = 0.0
    pv_salvage_value: float = 0.0
    pv_total: float = 0.0
    eac: float = 0.0
    annual_costs: List[Dict[str, Any]] = field(default_factory=list)
    horizon: int = 10
    discount_rate: float = 0.08
    warranty_years: int = 1
    new_equipment_life: int = 15

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario": self.scenario,
            "initial_cost": self.initial_cost,
            "pv_operating_costs": self.pv_operating_costs,
            "pv_salvage_value": self.pv_salvage_value,
            "pv_total": self.pv_total,
            "eac": self.eac,
            "horizon": self.horizon,
            "annual_costs": self.annual_costs,
        }


def compute_replace_lcc(params: ReplaceLCCParams) -> ReplaceLCCResult:
    """Comprehensive LCC for the 'Replace' scenario."""
    annual_costs = []
    pv_operating = 0.0
    cumulative_survival = 1.0

    for year in range(1, params.horizon + 1):
        equipment_age = year
        age_factor = 1 + 0.01 * equipment_age

        escalated_energy = (
            params.new_energy_cost_per_year
            * ((1 + params.energy_escalation) ** (year - 1))
            * age_factor
        )

        escalated_maint = (
            params.new_maintenance_cost_per_year
            * ((1 + params.maintenance_escalation) ** (year - 1))
            * age_factor
        )
        if year <= params.warranty_years:
            escalated_maint *= 0.3

        p_fail = params.new_failure_probability * (1 + 0.05 * max(0, equipment_age - 3))
        expected_failure = p_fail * params.failure_event_cost * cumulative_survival
        cumulative_survival *= 1 - p_fail

        total_year = escalated_energy + escalated_maint + expected_failure
        pv_year = present_value(total_year, params.discount_rate, year)
        pv_operating += pv_year

        annual_costs.append({
            "year": year,
            "energy_cost": round(escalated_energy),
            "maintenance_cost": round(escalated_maint),
            "expected_failure_cost": round(expected_failure),
            "total_cost": round(total_year),
            "pv_cost": round(pv_year),
            "cumulative_survival": round(cumulative_survival, 3),
        })

    salvage = (
        params.capex
        * params.salvage_value_pct
        * max(0, (params.new_equipment_life - params.horizon) / params.new_equipment_life)
    )
    pv_salvage = present_value(salvage, params.discount_rate, params.horizon)

    pv_total = params.capex + pv_operating - pv_salvage
    eac = equivalent_annual_cost(pv_total, params.discount_rate, params.horizon)

    return ReplaceLCCResult(
        initial_cost=params.capex,
        pv_operating_costs=round(pv_operating),
        pv_salvage_value=round(pv_salvage),
        pv_total=round(pv_total),
        eac=round(eac),
        annual_costs=annual_costs,
        horizon=params.horizon,
        discount_rate=params.discount_rate,
        warranty_years=params.warranty_years,
        new_equipment_life=params.new_equipment_life,
    )


# ─── NPV Comparison ──────────────────────────────────────────────────


@dataclass
class NPVComparison:
    npv: float = 0.0
    npv_per_capex_dollar: float = 0.0
    eac_savings: float = 0.0
    simple_payback_years: Optional[int] = None
    discounted_payback_years: Optional[int] = None
    irr: Optional[float] = None
    recommendation: str = "KEEP"
    confidence_level: str = "low"
    annual_savings: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "npv": self.npv,
            "npv_per_capex_dollar": self.npv_per_capex_dollar,
            "eac_savings": self.eac_savings,
            "simple_payback_years": self.simple_payback_years,
            "discounted_payback_years": self.discounted_payback_years,
            "irr": self.irr,
            "recommendation": self.recommendation,
            "confidence_level": self.confidence_level,
        }


def _compute_irr(initial_cost: float, cash_flows: List[float], max_iter: int = 100) -> Optional[float]:
    """Bisection IRR solver."""
    low, high = -0.5, 2.0

    def npv_at(rate):
        val = -initial_cost
        for i, cf in enumerate(cash_flows):
            val += cf / ((1 + rate) ** (i + 1))
        return val

    if npv_at(high) > 0:
        return high
    if npv_at(low) < 0:
        return None

    for _ in range(max_iter):
        mid = (low + high) / 2
        val = npv_at(mid)
        if abs(val) < 1:
            return mid
        if val > 0:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def _confidence_level(npv: float, capex: float) -> str:
    ratio = npv / capex if capex > 0 else 0
    if ratio > 0.5:
        return "high"
    if ratio > 0.2:
        return "medium"
    if ratio > 0:
        return "low"
    return "negative"


def compute_npv_comparison(keep: KeepLCCResult, replace: ReplaceLCCResult) -> NPVComparison:
    """Compare Keep vs Replace LCC results."""
    npv = keep.pv_total - replace.pv_total
    eac_savings = keep.eac - replace.eac

    annual_savings = []
    cumulative = -replace.initial_cost
    for i, k in enumerate(keep.annual_costs):
        r = replace.annual_costs[i] if i < len(replace.annual_costs) else {"total_cost": 0}
        saving = k["total_cost"] - r["total_cost"]
        cumulative += saving
        annual_savings.append({
            "year": k["year"],
            "keep_cost": k["total_cost"],
            "replace_cost": r["total_cost"],
            "savings": round(saving),
            "cumulative_savings": round(cumulative),
        })

    payback_year = None
    for s in annual_savings:
        if s["cumulative_savings"] >= 0:
            payback_year = s["year"]
            break

    discounted_payback = None
    disc_cum = -replace.initial_cost
    for i, s in enumerate(annual_savings):
        disc_cum += present_value(s["savings"], keep.discount_rate, i + 1)
        if disc_cum >= 0 and discounted_payback is None:
            discounted_payback = i + 1
            break

    irr = _compute_irr(replace.initial_cost, [s["savings"] for s in annual_savings])

    return NPVComparison(
        npv=round(npv),
        npv_per_capex_dollar=round(npv / replace.initial_cost, 2) if replace.initial_cost > 0 else 0,
        eac_savings=round(eac_savings),
        simple_payback_years=payback_year,
        discounted_payback_years=discounted_payback,
        irr=round(irr * 100, 1) if irr is not None else None,
        recommendation="REPLACE" if npv > 0 else "KEEP",
        confidence_level=_confidence_level(npv, replace.initial_cost),
        annual_savings=annual_savings,
    )


# ─── Monte Carlo NPV ─────────────────────────────────────────────────


@dataclass
class MonteCarloResult:
    iterations: int = 1000
    mean: float = 0.0
    std_dev: float = 0.0
    percentiles: Dict[str, float] = field(default_factory=dict)
    p_npv_positive: float = 0.0
    risk_assessment: str = "balanced"
    value_at_risk_5: float = 0.0
    expected_shortfall_5: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iterations": self.iterations,
            "mean": self.mean,
            "std_dev": self.std_dev,
            "percentiles": self.percentiles,
            "p_npv_positive": self.p_npv_positive,
            "risk_assessment": self.risk_assessment,
            "value_at_risk_5": self.value_at_risk_5,
            "expected_shortfall_5": self.expected_shortfall_5,
        }


def monte_carlo_npv(
    base_keep_params: KeepLCCParams,
    base_replace_params: ReplaceLCCParams,
    uncertainty_ranges: Optional[Dict[str, float]] = None,
    iterations: int = 1000,
    seed: Optional[int] = None,
) -> MonteCarloResult:
    """Run Monte Carlo simulation for probabilistic NPV."""
    if seed is not None:
        random.seed(seed)

    unc = uncertainty_ranges or {
        "energy_cost": 0.15,
        "maintenance_cost": 0.25,
        "failure_probability": 0.30,
        "efficiency_gain": 0.20,
    }

    results: List[float] = []

    for _ in range(iterations):
        kp = KeepLCCParams(
            current_age=base_keep_params.current_age,
            energy_cost_per_year=base_keep_params.energy_cost_per_year,
            maintenance_cost_per_year=base_keep_params.maintenance_cost_per_year,
            failure_probabilities=dict(base_keep_params.failure_probabilities),
            failure_event_cost=base_keep_params.failure_event_cost,
            discount_rate=base_keep_params.discount_rate,
            energy_escalation=base_keep_params.energy_escalation,
            maintenance_escalation=base_keep_params.maintenance_escalation,
            horizon=base_keep_params.horizon,
        )
        rp = ReplaceLCCParams(
            capex=base_replace_params.capex,
            new_equipment_life=base_replace_params.new_equipment_life,
            new_energy_cost_per_year=base_replace_params.new_energy_cost_per_year,
            new_maintenance_cost_per_year=base_replace_params.new_maintenance_cost_per_year,
            new_failure_probability=base_replace_params.new_failure_probability,
            failure_event_cost=base_replace_params.failure_event_cost,
            discount_rate=base_replace_params.discount_rate,
            energy_escalation=base_replace_params.energy_escalation,
            maintenance_escalation=base_replace_params.maintenance_escalation,
            horizon=base_replace_params.horizon,
            salvage_value_pct=base_replace_params.salvage_value_pct,
            warranty_years=base_replace_params.warranty_years,
            efficiency_gain=base_replace_params.efficiency_gain,
        )

        if "energy_cost" in unc:
            factor = 1 + (random.random() - 0.5) * 2 * unc["energy_cost"]
            kp.energy_cost_per_year *= factor
            rp.new_energy_cost_per_year *= factor

        if "maintenance_cost" in unc:
            factor = 1 + (random.random() - 0.5) * 2 * unc["maintenance_cost"]
            kp.maintenance_cost_per_year *= factor
            rp.new_maintenance_cost_per_year *= factor

        if "failure_probability" in unc:
            factor = 1 + (random.random() - 0.5) * 2 * unc["failure_probability"]
            kp.failure_probabilities = {
                k: v * factor for k, v in kp.failure_probabilities.items()
            }

        if "efficiency_gain" in unc and base_replace_params.efficiency_gain > 0:
            eff = base_replace_params.efficiency_gain * (
                1 + (random.random() - 0.5) * 2 * unc["efficiency_gain"]
            )
            rp.new_energy_cost_per_year = base_keep_params.energy_cost_per_year * (1 - eff)

        keep_lcc = compute_keep_lcc(kp)
        replace_lcc = compute_replace_lcc(rp)
        npv = keep_lcc.pv_total - replace_lcc.pv_total
        results.append(npv)

    results.sort()
    n = len(results)
    mean = sum(results) / n
    variance = sum((x - mean) ** 2 for x in results) / n
    std_dev = math.sqrt(variance)

    p05 = results[int(n * 0.05)]
    p25 = results[int(n * 0.25)]
    p50 = results[int(n * 0.50)]
    p75 = results[int(n * 0.75)]
    p95 = results[int(n * 0.95)]

    positive_count = sum(1 for x in results if x > 0)
    p_positive = positive_count / n

    tail_5 = results[: max(1, int(n * 0.05))]
    es5 = sum(tail_5) / len(tail_5) if tail_5 else 0

    if p_positive >= 0.9:
        risk = "low_risk"
    elif p_positive >= 0.7:
        risk = "moderate_risk"
    elif p_positive >= 0.5:
        risk = "balanced"
    else:
        risk = "high_risk"

    return MonteCarloResult(
        iterations=iterations,
        mean=round(mean),
        std_dev=round(std_dev),
        percentiles={
            "p05": round(p05),
            "p25": round(p25),
            "p50": round(p50),
            "p75": round(p75),
            "p95": round(p95),
        },
        p_npv_positive=round(p_positive, 2),
        risk_assessment=risk,
        value_at_risk_5=round(p05),
        expected_shortfall_5=round(es5),
    )


# ─── Convenience Wrapper ─────────────────────────────────────────────


class LCCEngine:
    """High-level wrapper that runs the full enhanced economic evaluation for one asset/option pair."""

    @staticmethod
    def evaluate(
        asset: Dict[str, Any],
        features: Dict[str, Any],
        replacement_option: Dict[str, Any],
        economic_assumption: Dict[str, Any],
        utility_rate: Dict[str, Any],
        survival_analysis: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run full LCC evaluation: Keep vs Replace + Monte Carlo."""
        horizon = economic_assumption.get("analysis_horizon_years", 10)
        discount_rate = economic_assumption.get("discount_rate", 0.08)

        kwh_per_year = features.get("kwh_day", 100) * 365
        energy_rate = utility_rate.get("energy_rate", 0.12)
        current_energy = kwh_per_year * energy_rate
        current_maint = features.get("maintenance_cost_365d", 2000)
        failure_cost = economic_assumption.get(
            "failure_event_cost_by_type", {}
        ).get(asset.get("asset_type", ""), 15_000)

        fail_probs = {"p1y": 0.1}
        if survival_analysis:
            fail_probs = survival_analysis.get("failure_probabilities", fail_probs)

        keep_params = KeepLCCParams(
            current_age=asset.get("age_years", 5),
            energy_cost_per_year=current_energy,
            maintenance_cost_per_year=current_maint,
            failure_probabilities=fail_probs,
            failure_event_cost=failure_cost,
            discount_rate=discount_rate,
            energy_escalation=utility_rate.get("escalation_rate", 0.03),
            maintenance_escalation=0.04,
            horizon=horizon,
        )

        eff_gain = replacement_option.get("efficiency_delta", 0.15)
        new_energy = current_energy * (1 - eff_gain)
        new_maint = max(500, current_maint + replacement_option.get("maintenance_delta_per_year", -500))

        replace_params = ReplaceLCCParams(
            capex=replacement_option.get("capex_installed_cost", 20_000),
            new_equipment_life=replacement_option.get("expected_life_years", 15),
            new_energy_cost_per_year=new_energy,
            new_maintenance_cost_per_year=new_maint,
            new_failure_probability=0.02,
            failure_event_cost=failure_cost,
            discount_rate=discount_rate,
            energy_escalation=utility_rate.get("escalation_rate", 0.03),
            maintenance_escalation=0.03,
            horizon=horizon,
            salvage_value_pct=0.1,
            warranty_years=replacement_option.get("warranty_years", 1),
            efficiency_gain=eff_gain,
        )

        keep_lcc = compute_keep_lcc(keep_params)
        replace_lcc = compute_replace_lcc(replace_params)
        comparison = compute_npv_comparison(keep_lcc, replace_lcc)
        mc = monte_carlo_npv(keep_params, replace_params, iterations=500)

        return {
            "option": {
                "id": replacement_option.get("option_id", ""),
                "name": replacement_option.get("option_name", ""),
                "capex": replacement_option.get("capex_installed_cost", 0),
            },
            "keep_lcc": keep_lcc.to_dict(),
            "replace_lcc": replace_lcc.to_dict(),
            "comparison": comparison.to_dict(),
            "monte_carlo": mc.to_dict(),
            "summary": {
                "npv": comparison.npv,
                "npv_p50": mc.percentiles.get("p50", 0),
                "p_npv_positive": mc.p_npv_positive,
                "eac_savings": comparison.eac_savings,
                "simple_payback": comparison.simple_payback_years,
                "discounted_payback": comparison.discounted_payback_years,
                "irr": comparison.irr,
                "risk_assessment": mc.risk_assessment,
                "recommendation": comparison.recommendation,
                "confidence_level": (
                    "high" if mc.p_npv_positive >= 0.8
                    else "medium" if mc.p_npv_positive >= 0.6
                    else "low"
                ),
            },
        }
