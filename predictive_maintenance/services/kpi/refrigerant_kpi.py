"""
Refrigerant Leak Reduction KPI — savings from early leak detection.

Methodology grounded in:
- EPA Section 608 (40 CFR Part 82) — 20% commercial leak threshold
- EPA GreenChill 2022 — 12.3% partner avg vs 25% industry avg
- AHRI 580 — secondary energy penalty 35-65 kWh/lb leaked
- Per-asset refrigerant GWP lookup (R-404A, R-410A, R-448A, CO2)
"""

import logging
from typing import Any, Dict, List

from .base import BaseKPIService, KPIConfig, KPIResult

logger = logging.getLogger(__name__)

# Per-refrigerant GWP values (IPCC AR6 100-year GWP)
REFRIGERANT_GWP_MAP = {
    "R-404A": 3_922,
    "R-407A": 2_107,
    "R-410A": 2_088,
    "R-448A": 1_387,
    "R-449A": 1_397,
    "R-134a": 1_430,
    "R-290": 3,        # propane
    "R-744": 1,        # CO2
    "R-717": 0,        # ammonia
}

# Per-refrigerant cost per lb (2023 market range midpoints)
REFRIGERANT_COST_MAP = {
    "R-404A": 15.0,
    "R-407A": 14.0,
    "R-410A": 12.0,
    "R-448A": 21.5,
    "R-449A": 20.0,
    "R-134a": 10.0,
}

# Secondary energy penalty per lb leaked (AHRI 580: 35-65 kWh/lb)
_ENERGY_PENALTY_KWH_PER_LB = 50.0  # midpoint of AHRI 580 range


class RefrigerantLeakReductionKPI(BaseKPIService):
    kpi_name = "refrigerant_leak_reduction"
    display_name = "Refrigerant Leak Reduction"
    category = "Gas Leak Reduction"

    def _get_asset_gwp(self, asset: Dict[str, Any]) -> float:
        """Look up GWP for an asset's refrigerant type, fall back to config default."""
        ref_type = asset.get("refrigerant_type", "")
        if ref_type and ref_type in REFRIGERANT_GWP_MAP:
            return float(REFRIGERANT_GWP_MAP[ref_type])
        return float(self.config.refrigerant_gwp)

    def _get_asset_cost_per_lb(self, asset: Dict[str, Any]) -> float:
        """Look up cost/lb for an asset's refrigerant type."""
        ref_type = asset.get("refrigerant_type", "")
        if ref_type and ref_type in REFRIGERANT_COST_MAP:
            return float(REFRIGERANT_COST_MAP[ref_type])
        return float(self.config.refrigerant_cost_per_lb)

    def compute(
        self,
        asset_data: List[Dict[str, Any]],
        alert_data: List[Dict[str, Any]],
        telemetry_summary: Dict[str, Any],
        health_data: List[Dict[str, Any]],
    ) -> KPIResult:
        cfg = self.config
        n_assets = max(len(asset_data), cfg.total_assets)
        n_readings = telemetry_summary.get("telemetry_count", 0)

        # Count refrigerant leak detections from alerts
        leak_alerts = [
            a for a in alert_data
            if a.get("primary_fault") == "refrigerant_leak"
        ]
        confirmed_leaks = [
            a for a in leak_alerts
            if a.get("feedback_outcome") == "confirmed_fault"
        ]

        # Estimate reduction achievable via early detection
        baseline_leak_rate_pct = float(cfg.baseline_leak_rate_pct)
        observed_leak_rate = telemetry_summary.get("refrigerant_avg_leak_rate_pct")
        if observed_leak_rate is not None and float(observed_leak_rate or 0) > 0:
            baseline_leak_rate_pct = float(observed_leak_rate)

        baseline_loss_lbs = n_assets * cfg.avg_charge_lbs * (baseline_leak_rate_pct / 100)
        observed_lbs_added = float(telemetry_summary.get("refrigerant_lbs_added_annual", 0) or 0)
        if observed_lbs_added > 0:
            baseline_loss_lbs = max(baseline_loss_lbs, observed_lbs_added)

        # PdM typically reduces leak rate by 40-60% (AHRI: 50-80% with early detection)
        reduction_factor = cfg.refrigerant_reduction_factor
        if len(leak_alerts) > 0 and len(confirmed_leaks) > 0:
            detection_rate = len(confirmed_leaks) / max(len(leak_alerts), 1)
            reduction_factor = 0.40 + detection_rate * 0.20
        observed_leak_events = int(
            telemetry_summary.get("refrigerant_leak_events_annual", 0) or 0
        )
        if observed_leak_events > 0:
            reduction_factor = min(0.65, reduction_factor + 0.05)

        saved_lbs = baseline_loss_lbs * reduction_factor

        # ── Per-asset GWP and cost calculation ──
        # Use per-asset refrigerant type when available for accurate GWP and cost
        if asset_data and any(a.get("refrigerant_type") for a in asset_data):
            # Fleet-weighted GWP and cost
            total_gwp_weighted = 0.0
            total_cost_weighted = 0.0
            ref_type_counts: Dict[str, int] = {}
            for asset in asset_data:
                gwp = self._get_asset_gwp(asset)
                cost = self._get_asset_cost_per_lb(asset)
                total_gwp_weighted += gwp
                total_cost_weighted += cost
                rt = asset.get("refrigerant_type", "unknown")
                ref_type_counts[rt] = ref_type_counts.get(rt, 0) + 1
            fleet_avg_gwp = total_gwp_weighted / len(asset_data)
            fleet_avg_cost = total_cost_weighted / len(asset_data)
            gwp_source = "per_asset"
        else:
            fleet_avg_gwp = float(cfg.refrigerant_gwp)
            fleet_avg_cost = float(cfg.refrigerant_cost_per_lb)
            ref_type_counts = {"R-404A (default)": n_assets}
            gwp_source = "config_default"

        # Direct refrigerant cost savings
        refrigerant_savings = saved_lbs * fleet_avg_cost

        # ── Secondary energy penalty (AHRI 580) ──
        # Reduced leakage = better compressor efficiency = energy savings
        energy_penalty_kwh = saved_lbs * _ENERGY_PENALTY_KWH_PER_LB
        energy_rate = float(cfg.energy_cost_per_kwh)
        secondary_energy_savings = energy_penalty_kwh * energy_rate

        # ── EPA compliance savings (Section 608 penalties) ──
        # EPA threshold: 20% annual for commercial refrigeration
        epa_penalty_avoided = 0.0
        systems_over_threshold = 0
        if baseline_leak_rate_pct > 20:  # EPA commercial threshold (not 15%)
            systems_over_threshold = max(1, int(n_assets * 0.3))
            epa_penalty_avoided = systems_over_threshold * 5_000  # per system per year

        # ── CO2e avoided ──
        co2e_avoided_tonnes = (saved_lbs * 0.4536) * fleet_avg_gwp / 1_000_000

        # ── Total savings ──
        savings_medium = refrigerant_savings + secondary_energy_savings + epa_penalty_avoided

        low, med, high = self._tri_estimate(savings_medium, 0.5, 1.6)
        confidence = self._confidence_from_coverage(n_readings, 500, 0.45)
        if len(confirmed_leaks) > 0:
            confidence = min(1.0, confidence + 0.15)

        target_rate = baseline_leak_rate_pct * (1 - reduction_factor)

        return self._make_result(
            savings_low=low,
            savings_medium=med,
            savings_high=high,
            confidence=confidence,
            status="approved" if confidence >= 0.5 else "pending",
            narrative=(
                f"Reducing leak rate from {baseline_leak_rate_pct:.0f}% to "
                f"{target_rate:.1f}% avoids {saved_lbs:,.0f} lbs refrigerant loss. "
                f"Savings: ${refrigerant_savings:,.0f} (refrigerant) + "
                f"${secondary_energy_savings:,.0f} (energy efficiency) + "
                f"${epa_penalty_avoided:,.0f} (EPA compliance) = ${med:,.0f}/year. "
                f"CO2e avoided: {co2e_avoided_tonnes:,.1f} tonnes. "
                f"{len(leak_alerts)} leak alerts detected, {len(confirmed_leaks)} confirmed."
            ),
            assumptions=[
                f"Fleet: {n_assets} assets, avg charge {cfg.avg_charge_lbs} lbs",
                f"Baseline leak rate: {baseline_leak_rate_pct}%/year (EPA threshold: 20%)",
                f"Reduction factor: {reduction_factor*100:.0f}% (AHRI: 50-80% achievable)",
                f"Fleet avg GWP: {fleet_avg_gwp:,.0f} (source: {gwp_source})",
                f"Refrigerant types: {ref_type_counts}",
                f"Secondary energy penalty: {_ENERGY_PENALTY_KWH_PER_LB} kWh/lb (AHRI 580: 35-65 range)",
            ],
            supporting_metrics={
                "leak_alerts": len(leak_alerts),
                "confirmed_leaks": len(confirmed_leaks),
                "saved_lbs": round(saved_lbs),
                "refrigerant_savings": round(refrigerant_savings, 2),
                "secondary_energy_savings_kwh": round(energy_penalty_kwh),
                "secondary_energy_savings_cost": round(secondary_energy_savings, 2),
                "epa_penalty_avoided": round(epa_penalty_avoided, 2),
                "systems_over_epa_threshold": systems_over_threshold,
                "co2e_avoided_tonnes": round(co2e_avoided_tonnes, 1),
                "fleet_avg_gwp": round(fleet_avg_gwp),
                "fleet_avg_cost_per_lb": round(fleet_avg_cost, 2),
                "gwp_source": gwp_source,
                "observed_leak_events_annual": observed_leak_events,
            },
            data_points_used=n_readings,
            data_coverage_pct=min(100, n_readings / 10),
        )
