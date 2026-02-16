"""
Remaining KPI Service Implementations

Contains the 11 additional KPI computation services beyond energy,
refrigerant, and work-order (which have their own modules).
"""

import logging
import math
from typing import Any, Dict, List

from .base import BaseKPIService, KPIConfig, KPIResult

logger = logging.getLogger(__name__)

# ── Q10 spoilage factors by product department (FDA Food Code 2022, Arrhenius) ──
# Q10 = factor by which spoilage rate doubles per 10°F (or ~5.5°C) above optimal.
# Higher Q10 = more temperature-sensitive.
_Q10_BY_DEPARTMENT = {
    "dairy":       {"q10": 2.0, "optimal_f": 36, "shrink_pct": 0.028},  # FMI 2020
    "meat":        {"q10": 3.0, "optimal_f": 30, "shrink_pct": 0.041},
    "deli_bakery": {"q10": 3.5, "optimal_f": 36, "shrink_pct": 0.087},
    "produce":     {"q10": 2.5, "optimal_f": 40, "shrink_pct": 0.058},
    "frozen":      {"q10": 1.5, "optimal_f": -5, "shrink_pct": 0.015},
    "general":     {"q10": 2.0, "optimal_f": 38, "shrink_pct": 0.042},  # FMI avg
}

# ── ISO 14224:2016 annual failure rates by component type ──
_ISO_14224_FAILURE_RATES = {
    "hvac_rtu":            0.055,  # 3-8%, midpoint
    "hvac_ahu":            0.050,
    "compressor":          0.040,  # 2-6%, midpoint
    "condenser":           0.025,  # 1-4%, midpoint
    "evaporator":          0.020,  # 1-3%, midpoint
    "refrigeration_rack":  0.060,
    "refrigeration_case":  0.035,
    "default":             0.050,  # fleet average when type unknown
}

# ── Refrigerant GWP map (shared with refrigerant_kpi.py) ──
_REFRIGERANT_GWP_MAP = {
    "R-404A": 3_922, "R-407A": 2_107, "R-410A": 2_088,
    "R-448A": 1_387, "R-449A": 1_397, "R-134a": 1_430,
    "R-290": 3, "R-744": 1, "R-717": 0,
}


# ── 4. Food Waste Reduction ──────────────────────────────────────────

class FoodWasteReductionKPI(BaseKPIService):
    """Food waste KPI using Q10 Arrhenius spoilage model per product department.

    Severity is scored by magnitude × duration × product sensitivity (Q10),
    not just excursion event count.  Per-department shrink baselines from
    FMI Shrink Survey 2020; Q10 factors from FDA Food Code 2022.
    """
    kpi_name = "food_waste_reduction"
    display_name = "Food Waste Reduction"
    category = "Shrink Reduction"

    def _score_excursion_severity(self, alert: Dict[str, Any]) -> float:
        """Score excursion severity using Q10 model (0-10 scale).

        Considers magnitude (temp above threshold), duration, and product
        sensitivity.  A 42°F excursion for 20 min is fundamentally different
        from 55°F for 4 hours.
        """
        dept = alert.get("department", "general")
        dept_info = _Q10_BY_DEPARTMENT.get(dept, _Q10_BY_DEPARTMENT["general"])
        q10 = dept_info["q10"]
        optimal_f = dept_info["optimal_f"]

        peak_temp_f = float(alert.get("peak_temp_f", 45) or 45)
        duration_min = float(alert.get("duration_minutes", 30) or 30)

        # Temperature magnitude above threshold
        delta_t = max(0, peak_temp_f - optimal_f)

        # Arrhenius-inspired severity: Q10^(deltaT/10) × duration
        if delta_t > 0:
            spoilage_accel = q10 ** (delta_t / 10.0)
        else:
            spoilage_accel = 1.0

        # Normalize to 0-10 scale (duration in hours, capped)
        duration_hours = min(duration_min / 60.0, 8.0)
        raw_severity = spoilage_accel * duration_hours
        return min(10.0, raw_severity)

    def compute(self, asset_data, alert_data, telemetry_summary, health_data) -> KPIResult:
        cfg = self.config
        n_readings = telemetry_summary.get("telemetry_count", 0)

        # Count temperature excursion events from alerts
        temp_alerts = [
            a for a in alert_data
            if "temp" in (a.get("primary_fault") or "").lower()
            or a.get("alert_type") == "sensor_integrity"
        ]
        # Degraded cooling assets increase excursion risk
        cooling_faults = [
            a for a in alert_data
            if a.get("primary_fault") in ("refrigerant_leak", "compressor_degradation", "condenser_fouling")
        ]

        # ── Per-department severity-weighted shrink estimation ──
        dept_impact: Dict[str, Dict[str, float]] = {}
        total_severity = 0.0
        for alert in temp_alerts:
            dept = alert.get("department", "general")
            severity = self._score_excursion_severity(alert)
            total_severity += severity
            if dept not in dept_impact:
                dept_info = _Q10_BY_DEPARTMENT.get(dept, _Q10_BY_DEPARTMENT["general"])
                dept_impact[dept] = {
                    "events": 0, "total_severity": 0.0,
                    "q10": dept_info["q10"], "shrink_pct": dept_info["shrink_pct"],
                }
            dept_impact[dept]["events"] += 1
            dept_impact[dept]["total_severity"] += severity

        # Classify excursions by severity tier
        severity_tiers = {"critical": 0, "moderate": 0, "minor": 0}
        for alert in temp_alerts:
            sev = self._score_excursion_severity(alert)
            if sev >= 6.0:
                severity_tiers["critical"] += 1
            elif sev >= 3.0:
                severity_tiers["moderate"] += 1
            else:
                severity_tiers["minor"] += 1

        # Calculate savings using severity-weighted model
        baseline_annual_events = cfg.avg_temp_excursion_events_per_month * 12
        reduction_pct = cfg.food_waste_reduction_pct
        if len(cooling_faults) > 0:
            reduction_pct = min(0.50, cfg.food_waste_reduction_pct + len(cooling_faults) * 0.02)

        if temp_alerts and total_severity > 0:
            # Severity-weighted cost per event (higher severity = more product loss)
            avg_severity = total_severity / len(temp_alerts)
            severity_cost_multiplier = min(2.5, avg_severity / 3.0)  # scale around baseline
            effective_cost_per_event = cfg.food_waste_cost_per_event * severity_cost_multiplier
        else:
            avg_severity = 3.0  # assume moderate if no data
            effective_cost_per_event = cfg.food_waste_cost_per_event

        prevented_events = baseline_annual_events * reduction_pct
        savings_medium = prevented_events * effective_cost_per_event
        low, med, high = self._tri_estimate(savings_medium, 0.4, 1.5)
        confidence = self._confidence_from_coverage(n_readings, 500, 0.35)

        return self._make_result(
            savings_low=low, savings_medium=med, savings_high=high,
            confidence=confidence,
            status="approved" if confidence >= 0.4 else "pending",
            narrative=f"Reducing excursion-driven shrink by {reduction_pct*100:.0f}% using Q10 spoilage model. "
                      f"{prevented_events:.0f} events prevented. Avg severity: {avg_severity:.1f}/10. "
                      f"Severity tiers: {severity_tiers['critical']} critical, "
                      f"{severity_tiers['moderate']} moderate, {severity_tiers['minor']} minor.",
            assumptions=[
                f"Baseline excursions: {baseline_annual_events}/year",
                f"Cost per event: ${effective_cost_per_event:,.0f} (severity-adjusted, base ${cfg.food_waste_cost_per_event})",
                "Spoilage model: Arrhenius Q10 (FDA Food Code 2022)",
                "Per-department shrink: dairy 2.8%, meat 4.1%, deli 8.7%, produce 5.8% (FMI 2020)",
            ],
            supporting_metrics={
                "temp_alerts": len(temp_alerts), "cooling_faults": len(cooling_faults),
                "avg_severity": round(avg_severity, 2),
                "severity_tiers": severity_tiers,
                "department_impact": {
                    d: {"events": info["events"], "avg_severity": round(info["total_severity"] / max(info["events"], 1), 2), "q10": info["q10"]}
                    for d, info in dept_impact.items()
                },
                "effective_cost_per_event": round(effective_cost_per_event, 2),
            },
            data_points_used=n_readings, data_coverage_pct=min(100, n_readings / 10),
        )


# ── 5. Asset Failure Prediction ──────────────────────────────────────

class AssetFailurePredictionKPI(BaseKPIService):
    """Asset failure prediction KPI using ISO 14224:2016 component-specific
    annual failure rates instead of crude quarterly extrapolation.

    McKinsey 2020: PdM reduces unplanned downtime 30-50%, extends
    equipment life 20-40%.  Collateral damage factor: 20-40% of primary
    failure cost.
    """
    kpi_name = "asset_failure_prediction"
    display_name = "Asset Failure Prediction"
    category = "Asset Failure Prevention"

    def _annual_expected_failures(self, asset_data: List[Dict[str, Any]], n_assets: int) -> float:
        """Estimate annual expected failures using ISO 14224 rates per asset type."""
        if not asset_data:
            return n_assets * _ISO_14224_FAILURE_RATES["default"]
        total = 0.0
        for asset in asset_data:
            asset_type = asset.get("asset_type", "default")
            rate = _ISO_14224_FAILURE_RATES.get(asset_type, _ISO_14224_FAILURE_RATES["default"])
            total += rate
        return total

    def compute(self, asset_data, alert_data, telemetry_summary, health_data) -> KPIResult:
        cfg = self.config
        n_readings = telemetry_summary.get("telemetry_count", 0)
        n_assets = max(len(asset_data), cfg.total_assets)

        # Use real health data to find at-risk assets
        at_risk = [h for h in health_data if (h.get("health_score") or 100) < 40]
        actionable_alerts = [a for a in alert_data if a.get("alert_type") == "actionable"]
        confirmed = [a for a in alert_data if a.get("feedback_outcome") == "confirmed_fault"]

        # ── ISO 14224 failure rate model ──
        # Annual expected failures based on component-type-specific rates
        annual_expected_failures = self._annual_expected_failures(asset_data, n_assets)

        # PdM prevention rate: McKinsey 2020 says 30-50% of unplanned failures preventable
        pdm_prevention_rate = 0.40  # midpoint
        if len(confirmed) > 0 and annual_expected_failures > 0:
            # Empirical detection rate adjusts the prevention estimate
            empirical_rate = min(0.55, len(confirmed) / max(annual_expected_failures, 1))
            pdm_prevention_rate = max(pdm_prevention_rate, empirical_rate)

        annual_prevented = annual_expected_failures * pdm_prevention_rate

        # Emergency repair cost with collateral damage factor (McKinsey: 20-40%)
        emergency_repair_cost = cfg.avg_wo_cost * 3  # 3x emergency multiplier (Deloitte)
        collateral_damage_factor = 1.30  # 30% collateral damage adder
        effective_cost_per_failure = emergency_repair_cost * collateral_damage_factor

        savings_medium = annual_prevented * effective_cost_per_failure
        low, med, high = self._tri_estimate(savings_medium, 0.5, 1.5)

        # Confidence scales with confirmed feedback
        confidence = self._confidence_from_coverage(n_readings, 500, 0.50)
        if len(confirmed) >= 3:
            confidence = min(1.0, confidence + 0.20)

        # Per-type failure breakdown
        type_breakdown = {}
        for asset in asset_data:
            atype = asset.get("asset_type", "default")
            rate = _ISO_14224_FAILURE_RATES.get(atype, _ISO_14224_FAILURE_RATES["default"])
            if atype not in type_breakdown:
                type_breakdown[atype] = {"count": 0, "annual_rate": rate, "expected_failures": 0.0}
            type_breakdown[atype]["count"] += 1
            type_breakdown[atype]["expected_failures"] += rate

        return self._make_result(
            savings_low=low, savings_medium=med, savings_high=high,
            confidence=confidence,
            status="approved" if confidence >= 0.5 else "pending",
            narrative=f"ISO 14224 model: {annual_expected_failures:.1f} expected failures/year, "
                      f"{annual_prevented:.1f} preventable via PdM ({pdm_prevention_rate*100:.0f}% rate). "
                      f"{len(at_risk)} at-risk assets, {len(confirmed)} confirmed detections. "
                      f"Savings: ${med:,.0f}/year.",
            assumptions=[
                f"Annual expected failures: {annual_expected_failures:.1f} (ISO 14224 component rates)",
                f"PdM prevention rate: {pdm_prevention_rate*100:.0f}% (McKinsey 2020: 30-50%)",
                f"Cost per failure: ${effective_cost_per_failure:,.0f} (3x emergency + 30% collateral)",
            ],
            supporting_metrics={
                "at_risk_assets": len(at_risk), "confirmed": len(confirmed),
                "actionable_alerts": len(actionable_alerts),
                "annual_expected_failures": round(annual_expected_failures, 1),
                "annual_prevented": round(annual_prevented, 1),
                "pdm_prevention_rate": round(pdm_prevention_rate, 3),
                "effective_cost_per_failure": round(effective_cost_per_failure, 2),
                "failure_rate_by_type": type_breakdown,
            },
            data_points_used=n_readings, data_coverage_pct=min(100, n_readings / 10),
        )


# ── 6. PPM Maximization ─────────────────────────────────────────────

class PPMMaximizationKPI(BaseKPIService):
    kpi_name = "ppm_maximization"
    display_name = "PPM Maximization"
    category = "PPM Savings"

    def compute(self, asset_data, alert_data, telemetry_summary, health_data) -> KPIResult:
        cfg = self.config
        n_readings = telemetry_summary.get("telemetry_count", 0)

        reactive = [a for a in alert_data if a.get("alert_type") in ("actionable", "dispatch")]
        planned = [a for a in alert_data if a.get("alert_type") == "watch"]

        reactive_count = max(len(reactive), cfg.baseline_reactive_wo_per_month)
        planned_count = len(planned)
        total = reactive_count + planned_count or 1
        reactive_ratio = reactive_count / total

        # Target: shift reactive to planned (cheaper)
        shift_pct = cfg.ppm_shift_pct
        shifted = reactive_count * shift_pct * 12  # annualize
        cost_diff = cfg.avg_wo_cost * 0.4  # planned is ~40% cheaper
        savings_medium = shifted * cost_diff

        low, med, high = self._tri_estimate(savings_medium, 0.5, 1.5)
        confidence = self._confidence_from_coverage(len(alert_data), 30, 0.45)

        return self._make_result(
            savings_low=low, savings_medium=med, savings_high=high,
            confidence=confidence,
            status="approved" if confidence >= 0.45 else "pending",
            narrative=f"Converting reactive to planned maintenance. Current reactive ratio: "
                      f"{reactive_ratio*100:.0f}%. Shifting {shift_pct*100:.0f}% saves ${med:,.0f}/year.",
            assumptions=[f"Cost differential planned vs reactive: {cost_diff:.0f}/WO",
                         f"Shift target: {shift_pct*100:.0f}% of reactive"],
            supporting_metrics={"reactive_ratio": round(reactive_ratio, 2), "shifted_wos": round(shifted)},
            data_points_used=len(alert_data), data_coverage_pct=min(100, len(alert_data) / 5),
        )


# ── 7. Food Safety Compliance ────────────────────────────────────────

class FoodSafetyComplianceKPI(BaseKPIService):
    kpi_name = "food_safety_compliance"
    display_name = "Food Safety Compliance"
    category = "Food Safety Compliance"

    def compute(self, asset_data, alert_data, telemetry_summary, health_data) -> KPIResult:
        cfg = self.config
        n_readings = telemetry_summary.get("telemetry_count", 0)

        # Cooling failures that could cause food safety violations
        cooling_failures = [
            a for a in alert_data
            if a.get("primary_fault") in ("refrigerant_leak", "compressor_degradation")
            and a.get("alert_type") in ("actionable", "dispatch")
        ]

        reduction_pct = cfg.food_safety_reduction_pct
        avoided_violations = cfg.baseline_violations_per_year * reduction_pct
        savings_medium = avoided_violations * cfg.food_safety_violation_cost

        low, med, high = self._tri_estimate(savings_medium, 0.5, 1.5)
        confidence = self._confidence_from_coverage(n_readings, 500, 0.40)

        return self._make_result(
            savings_low=low, savings_medium=med, savings_high=high,
            confidence=confidence,
            status="approved" if confidence >= 0.4 else "pending",
            narrative=f"Reducing food safety violations by {reduction_pct*100:.0f}%. "
                      f"{avoided_violations:.0f} violations avoided at ${cfg.food_safety_violation_cost:,.0f}/violation.",
            assumptions=[f"Baseline violations: {cfg.baseline_violations_per_year}/year",
                         f"Penalty per violation: ${cfg.food_safety_violation_cost:,.0f}"],
            supporting_metrics={"cooling_failures": len(cooling_failures),
                                "avoided_violations": round(avoided_violations)},
            data_points_used=n_readings, data_coverage_pct=min(100, n_readings / 10),
        )


# ── 8. ESG Compliance ────────────────────────────────────────────────

class ESGComplianceKPI(BaseKPIService):
    """ESG/carbon compliance KPI using per-asset GWP, EPA eGRID2022 grid
    factors, and EPA WARM food waste emission factors.

    Scope 1: refrigerant leaks (per-asset GWP)
    Scope 2: purchased electricity (eGRID regional factors)
    Scope 3 proxy: food waste diversion (EPA WARM model)
    """
    kpi_name = "esg_compliance"
    display_name = "ESG Compliance"
    category = "ESG Compliance"

    def _fleet_weighted_gwp(self, asset_data: List[Dict[str, Any]], default_gwp: float) -> float:
        """Compute fleet-weighted average GWP from per-asset refrigerant types."""
        if not asset_data:
            return default_gwp
        total_gwp = 0.0
        counted = 0
        for asset in asset_data:
            ref_type = asset.get("refrigerant_type", "")
            if ref_type and ref_type in _REFRIGERANT_GWP_MAP:
                total_gwp += _REFRIGERANT_GWP_MAP[ref_type]
                counted += 1
        if counted > 0:
            return total_gwp / counted
        return default_gwp

    def compute(self, asset_data, alert_data, telemetry_summary, health_data) -> KPIResult:
        cfg = self.config
        n_readings = telemetry_summary.get("telemetry_count", 0)
        n_assets = max(len(asset_data), cfg.total_assets)

        # ── Scope 2: Energy-based emissions reduction ──
        degraded = [h for h in health_data if (h.get("health_score") or 100) < 70]
        degraded_frac = len(degraded) / max(n_assets, 1)
        kwh_saved = cfg.baseline_annual_kwh * degraded_frac * 0.15
        co2_energy = kwh_saved * cfg.grid_emission_factor_tco2_per_kwh

        # ── Scope 1: Refrigerant emissions reduction (per-asset GWP) ──
        fleet_gwp = self._fleet_weighted_gwp(asset_data, cfg.refrigerant_gwp)
        leak_alerts = [a for a in alert_data if a.get("primary_fault") == "refrigerant_leak"]
        lbs_saved = n_assets * cfg.avg_charge_lbs * (cfg.baseline_leak_rate_pct / 100) * 0.50
        co2_refrigerant = (lbs_saved * 0.4536) * fleet_gwp / 1_000_000  # lbs→kg, then tCO2e

        # ── Scope 3 proxy: Food waste diversion (EPA WARM model) ──
        # Food waste to landfill: 2.53 tCO2e/ton; composting: 0.18 tCO2e/ton
        # Diversion credit: 2.35 tCO2e/ton avoided
        excursion_events_prevented = cfg.avg_temp_excursion_events_per_month * 12 * cfg.food_waste_reduction_pct
        lbs_food_waste_avoided = excursion_events_prevented * 50  # ~50 lbs per event
        tons_food_waste_avoided = lbs_food_waste_avoided / 2000
        co2_food_waste = tons_food_waste_avoided * 2.35  # EPA WARM diversion credit

        total_tco2 = co2_energy + co2_refrigerant + co2_food_waste
        carbon_price = cfg.carbon_price_per_tco2
        savings_medium = total_tco2 * carbon_price

        low, med, high = self._tri_estimate(savings_medium, 0.3, 2.0)
        confidence = self._confidence_from_coverage(n_readings, 500, 0.30)

        gwp_source = "per_asset" if any(a.get("refrigerant_type") for a in asset_data) else "config_default"

        return self._make_result(
            savings_low=low, savings_medium=med, savings_high=high,
            confidence=confidence,
            status="approved" if confidence >= 0.35 else "pending",
            narrative=f"Total emissions reduction: {total_tco2:,.1f} tCO2e "
                      f"(Scope 2 energy: {co2_energy:,.1f}, Scope 1 refrigerant: {co2_refrigerant:,.1f}, "
                      f"Scope 3 food waste: {co2_food_waste:,.1f}). "
                      f"Carbon value: ${savings_medium:,.0f}/year at ${carbon_price}/tCO2e.",
            assumptions=[
                f"Grid factor: {cfg.grid_emission_factor_tco2_per_kwh} tCO2/kWh (EPA eGRID2022 US avg)",
                f"Fleet avg GWP: {fleet_gwp:,.0f} (source: {gwp_source})",
                f"Carbon price: ${carbon_price}/tCO2e (EPA IWG 2024 social cost)",
                "Food waste: EPA WARM diversion credit 2.35 tCO2e/ton",
            ],
            supporting_metrics={
                "scope2_tco2_energy": round(co2_energy, 2),
                "scope1_tco2_refrigerant": round(co2_refrigerant, 2),
                "scope3_tco2_food_waste": round(co2_food_waste, 2),
                "total_tco2": round(total_tco2, 2),
                "fleet_avg_gwp": round(fleet_gwp),
                "gwp_source": gwp_source,
            },
            data_points_used=n_readings, data_coverage_pct=min(100, n_readings / 10),
        )


# ── 9. Asset Uptime Increase ─────────────────────────────────────────

class AssetUptimeIncreaseKPI(BaseKPIService):
    kpi_name = "asset_uptime_increase"
    display_name = "Asset Uptime Increase"
    category = "Uptime Improvement"

    def compute(self, asset_data, alert_data, telemetry_summary, health_data) -> KPIResult:
        cfg = self.config
        n_readings = telemetry_summary.get("telemetry_count", 0)

        # Calculate actual uptime from health data
        healthy_assets = [h for h in health_data if (h.get("health_score") or 100) >= 80]
        n_assets = max(len(asset_data), cfg.total_assets)
        current_uptime = len(healthy_assets) / max(n_assets, 1)
        current_uptime_pct = max(current_uptime * 100, cfg.baseline_uptime_pct)

        target_uptime_pct = cfg.uptime_target_pct
        improvement_pct = target_uptime_pct - current_uptime_pct
        improvement_hours = (improvement_pct / 100) * cfg.operating_hours_per_year * n_assets

        savings_medium = improvement_hours * cfg.hourly_downtime_cost
        low, med, high = self._tri_estimate(savings_medium, 0.5, 1.4)
        confidence = self._confidence_from_coverage(n_readings, 500, 0.50)

        return self._make_result(
            savings_low=low, savings_medium=med, savings_high=high,
            confidence=confidence,
            status="approved" if confidence >= 0.5 else "pending",
            narrative=f"Improving uptime from {current_uptime_pct:.0f}% to {target_uptime_pct:.0f}%. "
                      f"{improvement_hours:,.0f} additional operating hours across fleet.",
            assumptions=[f"Current uptime: {current_uptime_pct:.0f}%",
                         f"Target: {target_uptime_pct:.0f}%",
                         f"Downtime cost: ${cfg.hourly_downtime_cost}/hour"],
            supporting_metrics={"current_uptime_pct": round(current_uptime_pct, 1),
                                "improvement_hours": round(improvement_hours)},
            data_points_used=n_readings, data_coverage_pct=min(100, n_readings / 10),
        )


# ── 10. Call Center Volume Reduction ─────────────────────────────────

class CallCenterReductionKPI(BaseKPIService):
    kpi_name = "call_center_volume_reduction"
    display_name = "Call Center Reduction"
    category = "Call Center Cost Productivity"

    def compute(self, asset_data, alert_data, telemetry_summary, health_data) -> KPIResult:
        cfg = self.config
        n_readings = telemetry_summary.get("telemetry_count", 0)

        # Proactive alerts reduce inbound calls
        proactive_watches = [a for a in alert_data if a.get("alert_type") == "watch"]
        deflection_pct = cfg.call_center_deflection_pct
        annual_calls = cfg.baseline_calls_per_month * 12
        deflected = annual_calls * deflection_pct
        savings_medium = deflected * cfg.cost_per_call

        low, med, high = self._tri_estimate(savings_medium, 0.5, 1.5)
        confidence = self._confidence_from_coverage(n_readings, 200, 0.40)

        return self._make_result(
            savings_low=low, savings_medium=med, savings_high=high,
            confidence=confidence,
            status="approved" if confidence >= 0.4 else "pending",
            narrative=f"Deflecting {deflection_pct*100:.0f}% of inbound calls. "
                      f"{deflected:.0f} calls avoided at ${cfg.cost_per_call}/call.",
            assumptions=[f"Baseline: {annual_calls} calls/year",
                         f"Deflection rate: {deflection_pct*100:.0f}%"],
            supporting_metrics={"proactive_watches": len(proactive_watches),
                                "deflected_calls": round(deflected)},
            data_points_used=n_readings, data_coverage_pct=min(100, n_readings / 10),
        )


# ── 11. Service Bureau Reduction ─────────────────────────────────────

class ServiceBureauReductionKPI(BaseKPIService):
    kpi_name = "service_bureau_reduction"
    display_name = "Service Bureau Reduction"
    category = "3rd Party Job Reduction"

    def compute(self, asset_data, alert_data, telemetry_summary, health_data) -> KPIResult:
        cfg = self.config
        n_readings = telemetry_summary.get("telemetry_count", 0)

        # Dispatches avoided by early detection
        dispatch_alerts = [a for a in alert_data if a.get("alert_type") == "dispatch"]
        nif_dispatches = [a for a in alert_data if a.get("feedback_outcome") == "no_issue_found"]

        avoidance_pct = cfg.service_bureau_avoidance_pct
        annual_dispatches = cfg.baseline_dispatches_per_month * 12
        observed_reactive_wo = float(telemetry_summary.get("reactive_work_order_count_annual", 0) or 0)
        if observed_reactive_wo > 0:
            annual_dispatches = max(annual_dispatches, observed_reactive_wo * 0.6)
        avoided = annual_dispatches * avoidance_pct
        savings_medium = avoided * cfg.avg_dispatch_cost

        low, med, high = self._tri_estimate(savings_medium, 0.5, 1.5)
        confidence = self._confidence_from_coverage(len(alert_data), 30, 0.40)

        return self._make_result(
            savings_low=low, savings_medium=med, savings_high=high,
            confidence=confidence,
            status="approved" if confidence >= 0.4 else "pending",
            narrative=f"Avoiding {avoided:.0f} vendor dispatches/year at ${cfg.avg_dispatch_cost}/dispatch.",
            assumptions=[f"Baseline: {annual_dispatches} dispatches/year",
                         f"Avoidance rate: {avoidance_pct*100:.0f}%"],
            supporting_metrics={"dispatch_alerts": len(dispatch_alerts),
                                "nif_dispatches": len(nif_dispatches)},
            data_points_used=len(alert_data), data_coverage_pct=min(100, len(alert_data) / 5),
        )


# ── 12. Preventive Maintenance Optimization ──────────────────────────

class PreventiveMaintenanceOptKPI(BaseKPIService):
    kpi_name = "preventive_maintenance_optimization"
    display_name = "PM Optimization"
    category = "PPM Savings"

    def compute(self, asset_data, alert_data, telemetry_summary, health_data) -> KPIResult:
        cfg = self.config
        n_readings = telemetry_summary.get("telemetry_count", 0)

        # Condition-based scheduling reduces unnecessary PM visits
        healthy_assets = [h for h in health_data if (h.get("health_score") or 100) >= 80]
        n_assets = max(len(asset_data), cfg.total_assets)
        healthy_frac = len(healthy_assets) / max(n_assets, 1)

        # Skip PM for healthy units = savings
        skip_pct = healthy_frac * cfg.pm_skip_pct_factor
        effective_pm_cost = float(cfg.baseline_pm_cost_annual)
        observed_maintenance_cost = float(
            telemetry_summary.get("maintenance_total_cost_annual", 0) or 0
        )
        if observed_maintenance_cost > 0:
            effective_pm_cost = observed_maintenance_cost

        savings_medium = effective_pm_cost * skip_pct

        low, med, high = self._tri_estimate(savings_medium, 0.6, 1.4)
        confidence = self._confidence_from_coverage(n_readings, 500, 0.45)

        return self._make_result(
            savings_low=low, savings_medium=med, savings_high=high,
            confidence=confidence,
            status="approved" if confidence >= 0.45 else "pending",
            narrative=f"PM optimization reduces total maintenance cost by {skip_pct*100:.0f}%. "
                      f"{len(healthy_assets)}/{n_assets} assets qualify for deferred PM.",
            assumptions=[f"Baseline PM cost: ${effective_pm_cost:,.0f}/year",
                         f"Deferral rate for healthy assets: 30%"],
            supporting_metrics={"healthy_assets": len(healthy_assets),
                                "skip_pct": round(skip_pct, 2),
                                "observed_maintenance_cost_annual": round(observed_maintenance_cost, 2)},
            data_points_used=n_readings, data_coverage_pct=min(100, n_readings / 10),
        )


# ── 13. Food Temp Diagnostics Improvement ────────────────────────────

class FoodTempDiagnosticsKPI(BaseKPIService):
    kpi_name = "food_temp_diagnostics_improvement"
    display_name = "Food Temp Diagnostics"
    category = "Food Temperature Diagnostics"

    def compute(self, asset_data, alert_data, telemetry_summary, health_data) -> KPIResult:
        cfg = self.config
        n_readings = telemetry_summary.get("telemetry_count", 0)

        # Faster root-cause analysis reduces MTTR
        sensor_alerts = [a for a in alert_data if a.get("alert_type") == "sensor_integrity"]
        avg_trust = sum(h.get("sensor_trust_score", 100) for h in health_data) / max(len(health_data), 1)

        # Better diagnostics = faster resolution = fewer lost hours
        mttr_reduction_hours = cfg.mttr_reduction_hours
        incidents_per_year = max(len(sensor_alerts) * 4, 30)  # annualize
        savings_medium = incidents_per_year * mttr_reduction_hours * cfg.hourly_downtime_cost

        low, med, high = self._tri_estimate(savings_medium, 0.5, 1.5)
        confidence = self._confidence_from_coverage(n_readings, 300, 0.35)

        return self._make_result(
            savings_low=low, savings_medium=med, savings_high=high,
            confidence=confidence,
            status="approved" if confidence >= 0.35 else "pending",
            narrative=f"Improved diagnostics reduces root cause time by {mttr_reduction_hours}h/incident. "
                      f"Avg sensor trust: {avg_trust:.0f}%. {len(sensor_alerts)} sensor alerts detected.",
            assumptions=[f"MTTR reduction: {mttr_reduction_hours} hours/incident",
                         f"Projected incidents: {incidents_per_year}/year"],
            supporting_metrics={"sensor_alerts": len(sensor_alerts),
                                "avg_sensor_trust": round(avg_trust, 1)},
            data_points_used=n_readings, data_coverage_pct=min(100, n_readings / 10),
        )


# ── 14. CapEx Lifecycle Optimization ─────────────────────────────────

class CapExLifecycleKPI(BaseKPIService):
    kpi_name = "capex_lifecycle_optimization"
    display_name = "CapEx Lifecycle"
    category = "CapEx Optimization"

    def compute(self, asset_data, alert_data, telemetry_summary, health_data) -> KPIResult:
        cfg = self.config
        n_readings = telemetry_summary.get("telemetry_count", 0)

        # Find end-of-life assets via health score + RUL
        eol_assets = [
            h for h in health_data
            if (h.get("health_score") or 100) < 30
            or (h.get("rul_hours", 99999) < 500 and h.get("rul_hours", 99999) > 0)
        ]
        n_replacements = len(eol_assets) if eol_assets else max(1, len(asset_data) // 8)

        # NPV-positive replacement: new unit saves energy + avoids emergency repairs
        effective_energy_kwh = float(telemetry_summary.get("energy_kwh_annual", 0) or 0)
        if effective_energy_kwh <= 0:
            effective_energy_kwh = float(cfg.baseline_annual_kwh)
        annual_savings_per_replacement = (
            cfg.avg_wo_cost * 6  # avoided emergency repairs
            + effective_energy_kwh / max(cfg.total_assets, 1) * 0.20 * cfg.energy_cost_per_kwh  # 20% energy savings
        )
        total_replacement_cost = n_replacements * cfg.avg_asset_replacement_cost
        annual_savings = n_replacements * annual_savings_per_replacement

        # Simple NPV over 10 years
        npv = -total_replacement_cost
        for yr in range(1, 11):
            npv += annual_savings / ((1 + cfg.discount_rate) ** yr)

        savings_medium = annual_savings if npv > 0 else annual_savings * 0.5
        low, med, high = self._tri_estimate(savings_medium, 0.5, 1.25)
        confidence = self._confidence_from_coverage(n_readings, 500, 0.35)
        if len(eol_assets) > 0:
            confidence = min(1.0, confidence + 0.15)

        return self._make_result(
            savings_low=low, savings_medium=med, savings_high=high,
            confidence=confidence,
            status="approved" if confidence >= 0.4 else "pending",
            narrative=f"{n_replacements} replacements recommended within budget. "
                      f"10-year NPV: ${npv:,.0f}. Annual savings: ${annual_savings:,.0f}.",
            assumptions=[f"Replacement cost: ${cfg.avg_asset_replacement_cost:,.0f}/unit",
                         f"Discount rate: {cfg.discount_rate*100:.0f}%",
                         f"Analysis horizon: 10 years"],
            supporting_metrics={"eol_assets": len(eol_assets),
                                "n_replacements": n_replacements,
                                "npv": round(npv),
                                "replacement_cost": total_replacement_cost},
            data_points_used=n_readings, data_coverage_pct=min(100, n_readings / 10),
        )
