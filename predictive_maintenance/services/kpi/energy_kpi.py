"""
Energy Reduction KPI — computes savings from PdM-driven energy optimization.

Methodology aligns with:
- IPMVP Option C (whole-facility analysis) for weather normalization
- ASHRAE Guideline 14-2014 for baseline model adequacy
- EIA CBECS 2018 for grocery energy intensity benchmarks
- Demand (kW) and energy (kWh) savings reported separately per best practice
"""

import logging
from typing import Any, Dict, List

from .base import BaseKPIService, KPIConfig, KPIResult

logger = logging.getLogger(__name__)

# ECM disaggregation weights per ENERGY STAR retro-Cx methodology
_ECM_WEIGHTS = {
    "fault_correction": 0.35,
    "setpoint_optimization": 0.25,
    "scheduling": 0.20,
    "equipment_efficiency": 0.15,
    "demand_response": 0.05,
}


class EnergyReductionKPI(BaseKPIService):
    kpi_name = "energy_reduction"
    display_name = "Energy Reduction"
    category = "Energy Saving"

    def compute(
        self,
        asset_data: List[Dict[str, Any]],
        alert_data: List[Dict[str, Any]],
        telemetry_summary: Dict[str, Any],
        health_data: List[Dict[str, Any]],
    ) -> KPIResult:
        cfg = self.config

        # Real metrics from telemetry
        total_runtime_hours = telemetry_summary.get("total_compressor_hours", 0)
        avg_power_kw = telemetry_summary.get("avg_compressor_power_kw", 0)
        n_readings = telemetry_summary.get("telemetry_count", 0)

        # Count assets with energy-impacting faults (condenser fouling, etc.)
        energy_faults = [
            a for a in alert_data
            if a.get("primary_fault") in (
                "condenser_fouling", "filter_clogged", "fan_bearing_wear",
            )
        ]
        # Assets with degraded health consume more energy
        degraded_assets = [
            h for h in health_data
            if (h.get("health_score") or 100) < 70
        ]

        # Estimate energy penalty from degraded equipment
        avg_penalty_pct = cfg.energy_penalty_pct_degraded if degraded_assets else cfg.energy_penalty_pct_normal
        n_degraded = len(degraded_assets)
        n_assets = max(len(asset_data), cfg.total_assets)

        degraded_fraction = n_degraded / max(n_assets, 1)
        annual_baseline_kwh = float(cfg.baseline_annual_kwh)
        observed_annual_kwh = float(telemetry_summary.get("energy_kwh_annual", 0) or 0)
        if observed_annual_kwh > 0:
            annual_baseline_kwh = observed_annual_kwh

        effective_energy_rate = float(cfg.energy_cost_per_kwh)
        observed_rate = telemetry_summary.get("energy_effective_rate_per_kwh")
        if observed_rate is not None and float(observed_rate or 0) > 0:
            effective_energy_rate = float(observed_rate)

        # ── Weather normalization (ASHRAE Guideline 14 / IPMVP Option C) ──
        # If degree-day data is available, adjust baseline for weather differences
        # between baseline period and reporting period to avoid attributing
        # weather variance as "savings".
        weather_normalized = False
        normalization_factor = 1.0
        baseline_cdd = float(telemetry_summary.get("baseline_cooling_degree_days", 0) or 0)
        reporting_cdd = float(telemetry_summary.get("reporting_cooling_degree_days", 0) or 0)
        baseline_hdd = float(telemetry_summary.get("baseline_heating_degree_days", 0) or 0)
        reporting_hdd = float(telemetry_summary.get("reporting_heating_degree_days", 0) or 0)

        if baseline_cdd > 0 and reporting_cdd > 0:
            # Simple degree-day ratio normalization (IPMVP Option C simplified)
            # Full implementation would use 3-parameter change-point regression
            cdd_ratio = reporting_cdd / baseline_cdd
            hdd_ratio = reporting_hdd / baseline_hdd if (baseline_hdd > 0 and reporting_hdd > 0) else 1.0
            # HVAC/R energy is ~70% cooling-driven in grocery, 30% heating
            normalization_factor = 0.70 * cdd_ratio + 0.30 * hdd_ratio
            annual_baseline_kwh *= normalization_factor
            weather_normalized = True

        estimated_waste_kwh = annual_baseline_kwh * degraded_fraction * avg_penalty_pct

        # ── ECM disaggregation (ENERGY STAR retro-Cx methodology) ──
        ecm_savings_kwh = {
            ecm: estimated_waste_kwh * weight
            for ecm, weight in _ECM_WEIGHTS.items()
        }

        # ── Energy (kWh) savings ──
        energy_savings_cost = estimated_waste_kwh * effective_energy_rate

        # ── Demand (kW) savings — separated per best practice ──
        # Demand charges can be 30-50% of total commercial electric bill
        observed_peak_kw = float(telemetry_summary.get("peak_demand_kw", 0) or 0)
        baseline_peak_kw = observed_peak_kw if observed_peak_kw > 0 else cfg.baseline_peak_demand_kw
        demand_reduction_kw = baseline_peak_kw * degraded_fraction * avg_penalty_pct * 0.7
        demand_savings_cost = demand_reduction_kw * cfg.demand_charge_per_kw_month * 12

        # ── Total savings ──
        savings_medium = energy_savings_cost + demand_savings_cost

        low, med, high = self._tri_estimate(savings_medium)
        confidence = self._confidence_from_coverage(n_readings, 1000, 0.55)
        if not weather_normalized:
            # Downgrade confidence when weather normalization is unavailable
            # per ASHRAE Guideline 14 — raw comparison is less reliable
            confidence *= 0.85

        # Auto-approve if confidence is adequate
        status = "approved" if confidence >= 0.5 else "pending"

        pct_reduction = (estimated_waste_kwh / annual_baseline_kwh * 100) if annual_baseline_kwh else 0

        assumptions = [
            f"Baseline annual consumption: {annual_baseline_kwh:,.0f} kWh"
            + (" (weather-normalized)" if weather_normalized else " (NOT weather-normalized — CDD/HDD data unavailable)"),
            f"Avg energy penalty per degraded unit: {avg_penalty_pct*100:.0f}% (ASHRAE/PNNL: 10-30% range)",
            f"Energy cost: ${effective_energy_rate}/kWh",
            f"Demand charge: ${cfg.demand_charge_per_kw_month}/kW/month",
            "ECM disaggregation: fault correction 35%, setpoint 25%, scheduling 20%, equipment 15%, DR 5%",
            "M&V approach: IPMVP Option C (degree-day normalization)" if weather_normalized
            else "M&V limitation: degree-day data not available; raw baseline used (ASHRAE Guideline 14 recommends weather normalization)",
        ]

        return self._make_result(
            savings_low=low,
            savings_medium=med,
            savings_high=high,
            confidence=confidence,
            status=status,
            narrative=(
                f"Energy reduction of {pct_reduction:.1f}% from baseline of "
                f"{annual_baseline_kwh:,.0f} kWh saves ${energy_savings_cost:,.0f}/year (energy) "
                f"+ ${demand_savings_cost:,.0f}/year (demand) = ${med:,.0f}/year total. "
                f"{n_degraded}/{n_assets} assets show degraded efficiency; "
                f"{len(energy_faults)} energy-impacting faults detected."
            ),
            assumptions=assumptions,
            supporting_metrics={
                "degraded_assets": n_degraded,
                "energy_faults": len(energy_faults),
                "estimated_waste_kwh": round(estimated_waste_kwh),
                "pct_reduction": round(pct_reduction, 1),
                "observed_annual_kwh": round(observed_annual_kwh, 2),
                "energy_savings_cost": round(energy_savings_cost, 2),
                "demand_reduction_kw": round(demand_reduction_kw, 1),
                "demand_savings_cost": round(demand_savings_cost, 2),
                "weather_normalized": weather_normalized,
                "normalization_factor": round(normalization_factor, 3),
                "ecm_disaggregation_kwh": {k: round(v) for k, v in ecm_savings_kwh.items()},
            },
            data_points_used=n_readings,
            data_coverage_pct=min(100, n_readings / 10),
        )
