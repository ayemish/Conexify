"""
Decision Matrix Routes
─────────────────────
Weighted multi-factor scoring for Repair / Replace / Defer decisions.

Six decision dimensions:
  1. Financial ROI      (numeric – NPV, payback, LCC)
  2. Energy Savings     (numeric – kWh delta, $ savings)
  3. Reliability Risk   (numeric – health score, RUL, fault probability)
  4. Regulatory Risk    (rules-based – refrigerant type, age, compliance)
  5. ESG Impact         (rules-based – carbon, GWP, energy intensity)
  6. Customer Impact    (rules-based – downtime, alert frequency, criticality)

Numeric dimensions pull from existing health/asset data.
Non-numeric dimensions use deterministic rules with optional LLM narrative.
"""

import logging
import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

decision_matrix_router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════
# Request / Response Schemas
# ═══════════════════════════════════════════════════════════════════════

class DimensionWeights(BaseModel):
    financial_roi: float = Field(default=30, ge=0, le=100)
    energy_savings: float = Field(default=20, ge=0, le=100)
    reliability_risk: float = Field(default=20, ge=0, le=100)
    regulatory_risk: float = Field(default=10, ge=0, le=100)
    esg_impact: float = Field(default=10, ge=0, le=100)
    customer_impact: float = Field(default=10, ge=0, le=100)


class FinancialParams(BaseModel):
    discount_rate: float = Field(default=0.08, ge=0.01, le=0.25)
    repair_threshold_pct: float = Field(default=50, ge=10, le=90)
    payback_target_years: float = Field(default=5, ge=1, le=15)
    energy_cost_per_kwh: float = Field(default=0.12, ge=0.01, le=1.0)
    budget_constraint: Optional[float] = Field(default=None, ge=0)


class EvaluateRequest(BaseModel):
    weights: DimensionWeights = Field(default_factory=DimensionWeights)
    financials: FinancialParams = Field(default_factory=FinancialParams)
    site_id: str = "default"


class DimensionScore(BaseModel):
    score: float = 0.0
    label: str = ""
    detail: str = ""


class AssetDecision(BaseModel):
    asset_id: str
    site_id: str = ""
    asset_type: str = ""
    manufacturer: str = ""
    model: str = ""
    estate: str = ""
    location: str = ""
    health_score: float = 0.0
    rul_hours: float = 0.0
    weighted_total: float = 0.0
    recommendation: str = "DEFER"
    dimensions: Dict[str, DimensionScore] = {}
    financials: Dict[str, Any] = {}
    narrative: str = ""


class PortfolioSummary(BaseModel):
    total_assets: int = 0
    replace_count: int = 0
    repair_count: int = 0
    defer_count: int = 0
    total_replace_capex: float = 0.0
    total_expected_npv: float = 0.0
    avg_weighted_score: float = 0.0


class EvaluateResponse(BaseModel):
    assets: List[AssetDecision] = []
    summary: PortfolioSummary = Field(default_factory=PortfolioSummary)
    weights_used: Dict[str, float] = {}


class ExplainRequest(BaseModel):
    asset_id: str
    scores: Dict[str, float] = {}
    weights: DimensionWeights = Field(default_factory=DimensionWeights)
    financials: Dict[str, Any] = {}
    asset_context: Dict[str, Any] = {}


class ExplainResponse(BaseModel):
    asset_id: str
    narrative: str


# ═══════════════════════════════════════════════════════════════════════
# Default Weights / Config
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_WEIGHTS = {
    "financial_roi": 30,
    "energy_savings": 20,
    "reliability_risk": 20,
    "regulatory_risk": 10,
    "esg_impact": 10,
    "customer_impact": 10,
}

DIMENSION_LABELS = {
    "financial_roi": "Financial ROI",
    "energy_savings": "Energy Savings",
    "reliability_risk": "Reliability Risk",
    "regulatory_risk": "Regulatory Risk",
    "esg_impact": "ESG Impact",
    "customer_impact": "Customer Impact",
}

# Replacement cost estimates by asset type
REPLACEMENT_COSTS = {
    "hvac_rtu": 18_000,
    "ahu": 35_000,
    "chiller": 85_000,
    "compressor_rack": 45_000,
    "condensing_unit": 12_000,
    "walk_in_cooler": 22_000,
    "walk_in_freezer": 28_000,
    "reach_in_case": 8_000,
    "boiler": 40_000,
    "vfd": 6_000,
}

# Refrigerant risk scoring (higher = more reason to replace)
REFRIGERANT_RISK = {
    "r-22": 95,     # Phase-out complete
    "r-404a": 70,   # High GWP, phase-down pressure
    "r-407c": 55,   # Moderate GWP
    "r-410a": 45,   # Common but moderate GWP
    "r-134a": 40,   # Moderate
    "r-32": 15,     # Low GWP
    "r-290": 10,    # Natural refrigerant
    "r-744": 5,     # CO2 — lowest GWP
}

REFRIGERANT_GWP = {
    "r-22": 1810,
    "r-404a": 3922,
    "r-407c": 1774,
    "r-410a": 2088,
    "r-134a": 1430,
    "r-32": 675,
    "r-290": 3,
    "r-744": 1,
}


# ═══════════════════════════════════════════════════════════════════════
# Scoring Functions (per dimension)
# ═══════════════════════════════════════════════════════════════════════

def _score_financial_roi(
    health_score: float,
    rul_hours: float,
    asset_type: str,
    financials: FinancialParams,
    maintenance_cost_annual: float = 0,
) -> DimensionScore:
    """Financial ROI score based on NPV-like comparison of keep vs replace."""
    replacement_cost = REPLACEMENT_COSTS.get(asset_type, 18_000)

    # Estimate annual repair cost from health degradation
    degradation_pct = max(0, (100 - health_score)) / 100
    estimated_annual_repair = max(
        replacement_cost * 0.03,  # minimum 3% of replacement
        replacement_cost * degradation_pct * 0.15,
    )
    if maintenance_cost_annual > 0:
        estimated_annual_repair = max(estimated_annual_repair, maintenance_cost_annual)

    # 50% rule: if annual repair > threshold % of replacement, replace
    repair_ratio = estimated_annual_repair / max(replacement_cost, 1)
    threshold = financials.repair_threshold_pct / 100

    # Estimated annual savings from replacement (energy + maintenance reduction)
    energy_savings_est = replacement_cost * degradation_pct * 0.08
    annual_savings = estimated_annual_repair * 0.6 + energy_savings_est

    # Simple payback
    payback_years = replacement_cost / max(annual_savings, 1)

    # Simple NPV (5-year horizon)
    npv = -replacement_cost
    for yr in range(1, 6):
        npv += annual_savings / ((1 + financials.discount_rate) ** yr)

    # Score: combine payback and repair ratio
    score = 0
    if repair_ratio >= threshold:
        score += 50
    if payback_years <= 3:
        score += 40
    elif payback_years <= financials.payback_target_years:
        score += 25
    elif payback_years <= 8:
        score += 10
    if npv > 0:
        score += 10

    score = min(100, max(0, score))

    detail_parts = []
    detail_parts.append(f"Payback: {payback_years:.1f}yr")
    detail_parts.append(f"NPV: ${npv:,.0f}")
    detail_parts.append(f"Repair ratio: {repair_ratio:.0%}")

    return DimensionScore(
        score=score,
        label=DIMENSION_LABELS["financial_roi"],
        detail=" | ".join(detail_parts),
    )


def _score_energy_savings(
    health_score: float,
    asset_type: str,
    financials: FinancialParams,
) -> DimensionScore:
    """Energy savings potential based on health degradation."""
    degradation_pct = max(0, (100 - health_score)) / 100

    # Estimated energy penalty from degradation
    # Typical degraded HVAC uses 10-25% more energy
    energy_penalty_pct = degradation_pct * 0.20

    # Estimated annual energy cost for this asset type
    base_annual_kwh = {
        "hvac_rtu": 35_000,
        "ahu": 80_000,
        "chiller": 200_000,
        "compressor_rack": 120_000,
        "condensing_unit": 25_000,
        "walk_in_cooler": 15_000,
        "walk_in_freezer": 25_000,
        "reach_in_case": 8_000,
        "boiler": 50_000,
        "vfd": 20_000,
    }.get(asset_type, 35_000)

    wasted_kwh = base_annual_kwh * energy_penalty_pct
    wasted_dollars = wasted_kwh * financials.energy_cost_per_kwh

    # Score
    if energy_penalty_pct >= 0.20:
        score = 90
    elif energy_penalty_pct >= 0.10:
        score = 65
    elif energy_penalty_pct >= 0.05:
        score = 40
    else:
        score = 15

    return DimensionScore(
        score=score,
        label=DIMENSION_LABELS["energy_savings"],
        detail=f"Est. waste: {wasted_kwh:,.0f} kWh/yr (${wasted_dollars:,.0f})",
    )


def _score_reliability_risk(
    health_score: float,
    rul_hours: float,
    degradation_score: float = 0,
    fault_probability: float = 0,
    alert_count: int = 0,
) -> DimensionScore:
    """Reliability risk from health metrics."""
    # Base score from health
    if health_score < 40:
        score = 90
    elif health_score < 60:
        score = 65
    elif health_score < 80:
        score = 35
    else:
        score = 10

    # Boost if RUL is critically low
    if rul_hours < 1000:
        score = min(100, score + 15)
    elif rul_hours < 2000:
        score = min(100, score + 8)

    # Boost if high fault probability
    if fault_probability > 50:
        score = min(100, score + 10)

    # Boost if many active alerts
    if alert_count >= 3:
        score = min(100, score + 5)

    detail_parts = [
        f"Health: {health_score:.0f}/100",
        f"RUL: {rul_hours:,.0f}h",
    ]
    if fault_probability > 0:
        detail_parts.append(f"Fault prob: {fault_probability:.0f}%")

    return DimensionScore(
        score=min(100, max(0, score)),
        label=DIMENSION_LABELS["reliability_risk"],
        detail=" | ".join(detail_parts),
    )


def _score_regulatory_risk(
    asset_type: str,
    install_date: Optional[str] = None,
    refrigerant_type: str = "",
) -> DimensionScore:
    """Regulatory risk from refrigerant type and equipment age."""
    # Refrigerant risk
    ref_lower = (refrigerant_type or "").lower().strip()
    ref_score = REFRIGERANT_RISK.get(ref_lower, 30)

    # Age risk — older equipment more likely non-compliant
    age_years = 0
    if install_date:
        try:
            if isinstance(install_date, str):
                dt = datetime.fromisoformat(install_date.replace("Z", "+00:00"))
            else:
                dt = install_date
            age_years = (datetime.now(timezone.utc) - dt.replace(tzinfo=timezone.utc)).days / 365.25
        except Exception:
            pass

    age_score = 0
    if age_years > 20:
        age_score = 80
    elif age_years > 15:
        age_score = 55
    elif age_years > 10:
        age_score = 30
    else:
        age_score = 10

    # Blend: refrigerant dominates for HVAC/R, age for others
    if asset_type in ("hvac_rtu", "compressor_rack", "condensing_unit", "chiller",
                      "walk_in_cooler", "walk_in_freezer", "reach_in_case"):
        score = ref_score * 0.7 + age_score * 0.3
    else:
        score = ref_score * 0.3 + age_score * 0.7

    detail_parts = []
    if ref_lower:
        detail_parts.append(f"Refrigerant: {refrigerant_type.upper()}")
    if age_years > 0:
        detail_parts.append(f"Age: {age_years:.0f}yr")
    if not detail_parts:
        detail_parts.append("No refrigerant/age data")

    return DimensionScore(
        score=min(100, max(0, round(score))),
        label=DIMENSION_LABELS["regulatory_risk"],
        detail=" | ".join(detail_parts),
    )


def _score_esg_impact(
    health_score: float,
    asset_type: str,
    refrigerant_type: str = "",
    financials: FinancialParams = None,
) -> DimensionScore:
    """ESG impact from carbon reduction potential and refrigerant GWP."""
    ref_lower = (refrigerant_type or "").lower().strip()
    gwp = REFRIGERANT_GWP.get(ref_lower, 1500)

    # Carbon reduction potential from energy savings
    degradation_pct = max(0, (100 - health_score)) / 100
    base_kwh = {
        "hvac_rtu": 35_000, "ahu": 80_000, "chiller": 200_000,
        "compressor_rack": 120_000, "condensing_unit": 25_000,
    }.get(asset_type, 35_000)

    co2_reduction_kg = degradation_pct * base_kwh * 0.20 * 0.000386 * 1000  # tCO2 → kg

    # GWP score
    if gwp > 3000:
        gwp_score = 85
    elif gwp > 1500:
        gwp_score = 60
    elif gwp > 500:
        gwp_score = 35
    else:
        gwp_score = 10

    # Energy intensity score
    energy_score = min(80, degradation_pct * 100)

    score = gwp_score * 0.5 + energy_score * 0.5

    detail_parts = []
    if ref_lower:
        detail_parts.append(f"GWP: {gwp:,}")
    detail_parts.append(f"CO₂ reduction: {co2_reduction_kg:.0f} kg/yr")

    return DimensionScore(
        score=min(100, max(0, round(score))),
        label=DIMENSION_LABELS["esg_impact"],
        detail=" | ".join(detail_parts),
    )


def _score_customer_impact(
    health_score: float,
    rul_hours: float,
    alert_count: int = 0,
    downtime_hours: float = 0,
    asset_type: str = "",
) -> DimensionScore:
    """Customer impact from downtime risk and comfort/food safety implications."""
    # Criticality tier by asset type
    criticality = {
        "compressor_rack": 90, "walk_in_freezer": 85, "walk_in_cooler": 80,
        "reach_in_case": 75, "chiller": 70, "hvac_rtu": 60, "ahu": 55,
        "boiler": 50, "condensing_unit": 45, "vfd": 30,
    }.get(asset_type, 50)

    # Downtime risk score
    if health_score < 40:
        downtime_risk = 85
    elif health_score < 60:
        downtime_risk = 55
    elif health_score < 80:
        downtime_risk = 25
    else:
        downtime_risk = 10

    # Alert frequency penalty
    alert_penalty = min(20, alert_count * 5)

    score = (criticality * 0.4 + downtime_risk * 0.4 + alert_penalty * 0.2)

    detail_parts = [f"Criticality: {criticality}/100"]
    if alert_count > 0:
        detail_parts.append(f"Active alerts: {alert_count}")
    if downtime_hours > 0:
        detail_parts.append(f"Downtime: {downtime_hours:.0f}h")

    return DimensionScore(
        score=min(100, max(0, round(score))),
        label=DIMENSION_LABELS["customer_impact"],
        detail=" | ".join(detail_parts),
    )


# ═══════════════════════════════════════════════════════════════════════
# Composite Scoring
# ═══════════════════════════════════════════════════════════════════════

def _compute_weighted_total(dimensions: Dict[str, DimensionScore], weights: DimensionWeights) -> float:
    """Weighted total score normalized to 0-100."""
    w = {
        "financial_roi": weights.financial_roi,
        "energy_savings": weights.energy_savings,
        "reliability_risk": weights.reliability_risk,
        "regulatory_risk": weights.regulatory_risk,
        "esg_impact": weights.esg_impact,
        "customer_impact": weights.customer_impact,
    }
    total_weight = sum(w.values())
    if total_weight == 0:
        return 0
    weighted_sum = sum(dimensions[k].score * w[k] for k in w if k in dimensions)
    return round(weighted_sum / total_weight, 1)


def _classify_recommendation(weighted_total: float) -> str:
    if weighted_total >= 70:
        return "REPLACE"
    elif weighted_total >= 45:
        return "REPAIR"
    else:
        return "DEFER"


# ═══════════════════════════════════════════════════════════════════════
# LLM Narrative (optional — uses OpenAI if available)
# ═══════════════════════════════════════════════════════════════════════

async def _generate_narrative(asset: AssetDecision, weights: DimensionWeights) -> str:
    """Generate a concise business-language narrative for an asset decision."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return _fallback_narrative(asset)

    try:
        import openai
        client = openai.AsyncOpenAI(api_key=api_key)

        dim_lines = []
        for k, dim in asset.dimensions.items():
            w = getattr(weights, k, 0)
            dim_lines.append(f"- {dim.label}: {dim.score:.0f}/100 (weight {w}%) — {dim.detail}")

        prompt = f"""You are a facilities capital planning advisor. Given the following decision matrix scores for asset {asset.asset_id} ({asset.asset_type}), write a concise 2-3 sentence recommendation.

Asset: {asset.asset_id} | Type: {asset.asset_type} | Location: {asset.estate} / {asset.location}
Health Score: {asset.health_score:.0f}/100 | RUL: {asset.rul_hours:,.0f} hours
Weighted Total: {asset.weighted_total:.0f}/100 → Recommendation: {asset.recommendation}

Dimension Scores:
{chr(10).join(dim_lines)}

Write a brief, action-oriented recommendation suitable for a capital planning committee. Focus on the top 2 drivers and the financial impact."""

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("LLM narrative generation failed: %s", e)
        return _fallback_narrative(asset)


def _fallback_narrative(asset: AssetDecision) -> str:
    """Deterministic narrative when LLM is unavailable."""
    top_dims = sorted(asset.dimensions.items(), key=lambda x: x[1].score, reverse=True)[:2]
    drivers = " and ".join(d.label for _, d in top_dims)

    if asset.recommendation == "REPLACE":
        return (
            f"{asset.asset_id} scores {asset.weighted_total:.0f}/100 for replacement priority, "
            f"driven primarily by {drivers}. "
            f"Recommend scheduling replacement within the next capital cycle."
        )
    elif asset.recommendation == "REPAIR":
        return (
            f"{asset.asset_id} scores {asset.weighted_total:.0f}/100 — repair or targeted retrofit "
            f"is recommended. Key factors: {drivers}. "
            f"Monitor closely and reassess at next review."
        )
    else:
        return (
            f"{asset.asset_id} scores {asset.weighted_total:.0f}/100. "
            f"No immediate action required. Continue standard maintenance program."
        )


# ═══════════════════════════════════════════════════════════════════════
# Data Collection (reuses fleet route helpers)
# ═══════════════════════════════════════════════════════════════════════

def _load_asset_and_health(site_id: str):
    """Load assets and health data using the same helpers as the fleet routes."""
    try:
        from .kpi_fleet_routes import _collect_data_from_db, _collect_health_data, _derive_estate_location
        asset_data, alert_data, _, _ = _collect_data_from_db(site_id)
        health_data = _collect_health_data(site_id, asset_data)
        return asset_data, alert_data, health_data, _derive_estate_location
    except Exception as e:
        logger.error("Failed to load asset/health data: %s", e)
        return [], [], [], lambda sid: ("Unknown", "Unknown")


# ═══════════════════════════════════════════════════════════════════════
# API Endpoints
# ═══════════════════════════════════════════════════════════════════════

@decision_matrix_router.get("/defaults")
async def get_defaults():
    """Return default weights and financial parameters."""
    return {
        "weights": DEFAULT_WEIGHTS,
        "financials": {
            "discount_rate": 0.08,
            "repair_threshold_pct": 50,
            "payback_target_years": 5,
            "energy_cost_per_kwh": 0.12,
            "budget_constraint": None,
        },
        "dimension_labels": DIMENSION_LABELS,
    }


@decision_matrix_router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_decision_matrix(req: EvaluateRequest):
    """Evaluate all assets against the weighted decision matrix."""
    asset_data, alert_data, health_data, derive_loc = _load_asset_and_health(req.site_id)

    if not asset_data:
        return EvaluateResponse(
            assets=[],
            summary=PortfolioSummary(),
            weights_used=req.weights.model_dump(),
        )

    # Build lookup maps
    health_map = {h["asset_id"]: h for h in health_data}
    alert_map: Dict[str, List] = {}
    for al in alert_data:
        alert_map.setdefault(al["asset_id"], []).append(al)

    decisions: List[AssetDecision] = []

    for a in asset_data:
        aid = a["asset_id"]
        h = health_map.get(aid, {})
        asset_alerts = alert_map.get(aid, [])
        active_alerts = [al for al in asset_alerts if al.get("status") == "active"]

        health_score = h.get("health_score", 50.0)
        rul_hours = h.get("rul_hours", 5000.0)
        degradation = h.get("degradation_score", 0.0)
        fault_prob = h.get("fault_probability_score", 0.0)
        asset_type = a.get("asset_type", "hvac_rtu")
        install_date = a.get("install_date")

        asset_site = a.get("site_id", req.site_id)
        estate, location = derive_loc(asset_site)

        # Score each dimension
        dims = {}
        dims["financial_roi"] = _score_financial_roi(
            health_score, rul_hours, asset_type, req.financials,
        )
        dims["energy_savings"] = _score_energy_savings(
            health_score, asset_type, req.financials,
        )
        dims["reliability_risk"] = _score_reliability_risk(
            health_score, rul_hours, degradation, fault_prob, len(active_alerts),
        )
        dims["regulatory_risk"] = _score_regulatory_risk(
            asset_type, str(install_date) if install_date else None,
        )
        dims["esg_impact"] = _score_esg_impact(
            health_score, asset_type, financials=req.financials,
        )
        dims["customer_impact"] = _score_customer_impact(
            health_score, rul_hours, len(active_alerts), asset_type=asset_type,
        )

        weighted_total = _compute_weighted_total(dims, req.weights)
        recommendation = _classify_recommendation(weighted_total)

        replacement_cost = REPLACEMENT_COSTS.get(asset_type, 18_000)
        degradation_pct = max(0, (100 - health_score)) / 100
        annual_savings_est = replacement_cost * degradation_pct * 0.15 + replacement_cost * degradation_pct * 0.08
        payback = replacement_cost / max(annual_savings_est, 1)

        npv = -replacement_cost
        for yr in range(1, 6):
            npv += annual_savings_est / ((1 + req.financials.discount_rate) ** yr)

        decision = AssetDecision(
            asset_id=aid,
            site_id=asset_site,
            asset_type=asset_type,
            manufacturer=a.get("manufacturer", ""),
            model=a.get("model_number", ""),
            estate=estate,
            location=location,
            health_score=round(health_score, 1),
            rul_hours=round(rul_hours, 0),
            weighted_total=weighted_total,
            recommendation=recommendation,
            dimensions=dims,
            financials={
                "replacement_cost": replacement_cost,
                "estimated_annual_savings": round(annual_savings_est),
                "simple_payback_years": round(payback, 1),
                "npv_5yr": round(npv),
            },
        )
        decisions.append(decision)

    # Sort by weighted total descending
    decisions.sort(key=lambda d: d.weighted_total, reverse=True)

    # Generate narratives for top 10 (to control LLM cost)
    for d in decisions[:10]:
        d.narrative = await _generate_narrative(d, req.weights)
    for d in decisions[10:]:
        d.narrative = _fallback_narrative(d)

    # Portfolio summary
    replace_assets = [d for d in decisions if d.recommendation == "REPLACE"]
    repair_assets = [d for d in decisions if d.recommendation == "REPAIR"]
    defer_assets = [d for d in decisions if d.recommendation == "DEFER"]

    summary = PortfolioSummary(
        total_assets=len(decisions),
        replace_count=len(replace_assets),
        repair_count=len(repair_assets),
        defer_count=len(defer_assets),
        total_replace_capex=sum(d.financials.get("replacement_cost", 0) for d in replace_assets),
        total_expected_npv=sum(d.financials.get("npv_5yr", 0) for d in replace_assets),
        avg_weighted_score=round(
            sum(d.weighted_total for d in decisions) / max(len(decisions), 1), 1
        ),
    )

    return EvaluateResponse(
        assets=decisions,
        summary=summary,
        weights_used=req.weights.model_dump(),
    )


@decision_matrix_router.post("/explain", response_model=ExplainResponse)
async def explain_asset_decision(req: ExplainRequest):
    """Generate an LLM narrative for a specific asset decision."""
    # Build a minimal AssetDecision for narrative generation
    dims = {}
    for k, score_val in req.scores.items():
        dims[k] = DimensionScore(
            score=score_val,
            label=DIMENSION_LABELS.get(k, k),
            detail="",
        )

    weighted_total = _compute_weighted_total(dims, req.weights)

    asset = AssetDecision(
        asset_id=req.asset_id,
        asset_type=req.asset_context.get("asset_type", "hvac_rtu"),
        estate=req.asset_context.get("estate", ""),
        location=req.asset_context.get("location", ""),
        health_score=req.asset_context.get("health_score", 50),
        rul_hours=req.asset_context.get("rul_hours", 5000),
        weighted_total=weighted_total,
        recommendation=_classify_recommendation(weighted_total),
        dimensions=dims,
        financials=req.financials,
    )

    narrative = await _generate_narrative(asset, req.weights)

    return ExplainResponse(asset_id=req.asset_id, narrative=narrative)
