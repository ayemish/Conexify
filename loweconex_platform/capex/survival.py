"""
Survival / Hazard Modeling for Failure Prediction.

Weibull parametric + Cox proportional hazards models.
Ported from CapEx Generator survivalModeling.js.

Reference: https://www.sciencedirect.com/science/article/pii/S0951832020306244
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# ─── Weibull Parameters by Asset Type ────────────────────────────────

WEIBULL_PARAMETERS: Dict[str, Dict[str, float]] = {
    "RTU":              {"shape": 2.2, "scale": 15},
    "AHU":              {"shape": 2.5, "scale": 20},
    "COMPRESSOR_RACK":  {"shape": 2.0, "scale": 12},
    "CONDENSING_UNIT":  {"shape": 2.1, "scale": 14},
    "WALK_IN_COOLER":   {"shape": 2.3, "scale": 18},
    "WALK_IN_FREEZER":  {"shape": 2.1, "scale": 16},
    "REACH_IN_CASE":    {"shape": 2.4, "scale": 12},
    "CHILLER":          {"shape": 2.6, "scale": 22},
    "BOILER":           {"shape": 2.8, "scale": 25},
    "VFD":              {"shape": 2.0, "scale": 12},
    "DEFAULT":          {"shape": 2.2, "scale": 15},
}


# ─── Weibull Functions ───────────────────────────────────────────────

def weibull_survival(t: float, shape: float, scale: float) -> float:
    """S(t) = exp(-(t/scale)^shape)"""
    if t <= 0:
        return 1.0
    return math.exp(-((t / scale) ** shape))


def weibull_hazard(t: float, shape: float, scale: float) -> float:
    """h(t) = (shape/scale) * (t/scale)^(shape-1)"""
    if t <= 0:
        return 0.0
    return (shape / scale) * ((t / scale) ** (shape - 1))


def weibull_cumulative_hazard(t: float, shape: float, scale: float) -> float:
    """H(t) = (t/scale)^shape"""
    if t <= 0:
        return 0.0
    return (t / scale) ** shape


def weibull_failure_probability(t: float, horizon: float, shape: float, scale: float) -> float:
    """P(T <= t+h | T > t) = 1 - S(t+h)/S(t)"""
    s_t = weibull_survival(t, shape, scale)
    if s_t <= 0:
        return 1.0
    s_th = weibull_survival(t + horizon, shape, scale)
    return 1 - s_th / s_t


def weibull_expected_remaining_life(t: float, shape: float, scale: float, max_years: int = 30) -> float:
    """Approximate E[T-t | T>t] via discrete summation."""
    total = 0.0
    s_t = weibull_survival(t, shape, scale)
    if s_t <= 0:
        return 0.0
    for yr in range(1, max_years + 1):
        total += weibull_survival(t + yr, shape, scale) / s_t
    return round(total, 1)


# ─── Cox Proportional Hazards Adjustment ─────────────────────────────

# Baseline coefficients for covariate adjustment
COX_COEFFICIENTS: Dict[str, float] = {
    "poor_peer_percentile":   0.4,    # below P25 in peer comparison
    "high_fault_burden":      0.5,    # many active faults
    "high_energy_waste":      0.3,    # significant energy waste
    "heavy_maintenance":      0.35,   # escalating maintenance costs
    "harsh_environment":      0.2,    # extreme climate zone
    "high_utilization":       0.25,   # continuous duty cycle
}


def cox_hazard_ratio(covariates: Dict[str, float]) -> float:
    """Compute exp(beta · X) hazard ratio from covariates."""
    linear = sum(
        COX_COEFFICIENTS.get(k, 0) * v
        for k, v in covariates.items()
    )
    return math.exp(linear)


# ─── Survival Model ──────────────────────────────────────────────────

@dataclass
class SurvivalResult:
    """Output of survival analysis for a single asset."""
    asset_id: str = ""
    asset_type: str = ""
    current_age: float = 0.0
    weibull_shape: float = 2.2
    weibull_scale: float = 15.0
    hazard_ratio: float = 1.0
    effective_age: float = 0.0

    # Probabilities
    failure_probabilities: Dict[str, float] = field(default_factory=dict)

    # Summary
    risk_score: float = 0.0
    risk_category: str = "low"
    expected_remaining_life_years: float = 10.0
    interpretation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "asset_type": self.asset_type,
            "current_age": self.current_age,
            "weibull_shape": self.weibull_shape,
            "weibull_scale": self.weibull_scale,
            "hazard_ratio": self.hazard_ratio,
            "effective_age": self.effective_age,
            "failure_probabilities": self.failure_probabilities,
            "risk_score": self.risk_score,
            "risk_category": self.risk_category,
            "expected_remaining_life_years": self.expected_remaining_life_years,
            "interpretation": self.interpretation,
        }


class SurvivalModel:
    """Compute Weibull + Cox PH survival analysis for an asset."""

    @staticmethod
    def analyze(
        asset: Dict[str, Any],
        features: Optional[Dict[str, Any]] = None,
    ) -> SurvivalResult:
        """Run survival analysis for a single asset.

        Parameters
        ----------
        asset : dict with keys: asset_id, asset_type, age_years, ...
        features : optional enriched features (peer comparison, fault detection, energy waste)
        """
        asset_type = asset.get("asset_type", "DEFAULT")
        params = WEIBULL_PARAMETERS.get(asset_type, WEIBULL_PARAMETERS["DEFAULT"])
        shape = params["shape"]
        scale = params["scale"]
        age = asset.get("age_years", 5)

        # Build covariates from features
        covariates: Dict[str, float] = {}
        if features:
            peer = features.get("peer_percentile", 50)
            if peer < 25:
                covariates["poor_peer_percentile"] = 1.0

            fault_burden = features.get("fault_burden_score", 0)
            if fault_burden > 50:
                covariates["high_fault_burden"] = fault_burden / 100.0

            energy_waste = features.get("energy_waste_percentile", 50)
            if energy_waste > 70:
                covariates["high_energy_waste"] = energy_waste / 100.0

            maint_trend = features.get("maintenance_trend", 0)
            if maint_trend > 0.3:
                covariates["heavy_maintenance"] = maint_trend

        hr = cox_hazard_ratio(covariates)

        # Effective age accounts for condition-based aging
        effective_age = age * (hr ** 0.5)

        # Failure probabilities at various horizons
        p_90d = weibull_failure_probability(effective_age, 0.25, shape, scale)
        p_1y = weibull_failure_probability(effective_age, 1, shape, scale)
        p_2y = weibull_failure_probability(effective_age, 2, shape, scale)
        p_3y = weibull_failure_probability(effective_age, 3, shape, scale)
        p_5y = weibull_failure_probability(effective_age, 5, shape, scale)

        fail_probs = {
            "p90d": round(p_90d, 4),
            "p1y": round(p_1y, 4),
            "p2y": round(p_2y, 4),
            "p3y": round(p_3y, 4),
            "p5y": round(p_5y, 4),
        }

        erl = weibull_expected_remaining_life(effective_age, shape, scale)

        # Risk score (0-100)
        risk_score = min(100, round(
            p_1y * 40 + p_3y * 30 + (1 - weibull_survival(effective_age, shape, scale)) * 30
        ) * 100 / 100)

        # Risk category
        if risk_score >= 75:
            category = "critical"
        elif risk_score >= 55:
            category = "high"
        elif risk_score >= 35:
            category = "elevated"
        elif risk_score >= 15:
            category = "moderate"
        else:
            category = "low"

        # Interpretation
        interp = (
            f"{asset_type} at {age}y (effective {effective_age:.1f}y with HR={hr:.2f}). "
            f"P(fail 1yr)={p_1y:.0%}, P(fail 3yr)={p_3y:.0%}. "
            f"Expected remaining life: {erl:.1f}y. Risk: {category}."
        )

        return SurvivalResult(
            asset_id=asset.get("asset_id", ""),
            asset_type=asset_type,
            current_age=age,
            weibull_shape=shape,
            weibull_scale=scale,
            hazard_ratio=round(hr, 3),
            effective_age=round(effective_age, 1),
            failure_probabilities=fail_probs,
            risk_score=risk_score,
            risk_category=category,
            expected_remaining_life_years=erl,
            interpretation=interp,
        )
