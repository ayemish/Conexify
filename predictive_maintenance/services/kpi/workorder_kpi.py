"""
Work Order Reduction KPI — savings from converting reactive to planned maintenance.

Methodology uses failure-mode decomposition per FMEA/RCM principles
(SAE JA1011, ISO 14224:2016) rather than a flat reduction percentage.
Category-specific reducibility rates based on P-F interval availability:
- Controls faults: 40-60% reducible (instantly detectable via analytics)
- Mechanical faults: 25-40% reducible (vibration/thermal CBM, 1-6 month P-F)
- Refrigerant faults: 20-35% reducible (pressure trending)
- Electrical faults: 20-35% reducible (power quality monitoring)
- Structural/environmental: 5-15% reducible (visual inspection, long P-F)
"""

import logging
from typing import Any, Dict, List

from .base import BaseKPIService, KPIConfig, KPIResult

logger = logging.getLogger(__name__)

# Failure mode categories with reducibility rates (Jardine et al. 2006, SAE JA1011)
# Each category maps to: (reduction_rate, fault_types_that_match)
_FAILURE_MODE_REDUCIBILITY = {
    "controls": {
        "reduction": 0.50,  # 40-60%, midpoint
        "faults": {"sensor_drift", "setpoint_error", "controller_fault", "scheduling_error"},
    },
    "mechanical": {
        "reduction": 0.33,  # 25-40%, midpoint
        "faults": {"fan_bearing_wear", "compressor_degradation", "belt_wear", "motor_fault"},
    },
    "refrigerant": {
        "reduction": 0.28,  # 20-35%, midpoint
        "faults": {"refrigerant_leak", "txv_failure", "charge_imbalance"},
    },
    "electrical": {
        "reduction": 0.28,  # 20-35%, midpoint
        "faults": {"electrical_fault", "power_quality", "capacitor_failure", "contactor_fault"},
    },
    "thermal": {
        "reduction": 0.35,  # condenser/filter faults detectable via temp trending
        "faults": {"condenser_fouling", "filter_clogged", "evaporator_icing", "heat_exchanger_fouling"},
    },
    "structural": {
        "reduction": 0.10,  # 5-15%, largely unpredictable
        "faults": {"cabinet_damage", "insulation_failure", "corrosion", "vandalism", "weather_damage"},
    },
}

# Default distribution when no fault data is available (industry typical)
_DEFAULT_FAILURE_MODE_DISTRIBUTION = {
    "controls": 0.20,
    "mechanical": 0.25,
    "refrigerant": 0.15,
    "electrical": 0.10,
    "thermal": 0.20,
    "structural": 0.10,
}


class WorkOrderReductionKPI(BaseKPIService):
    kpi_name = "work_order_reduction"
    display_name = "Work Order Reduction"
    category = "Workorder Reduction"

    def _classify_fault(self, fault_type: str) -> str:
        """Classify a fault type into a failure mode category."""
        if not fault_type:
            return "structural"  # unknown defaults to lowest reducibility
        ft = fault_type.lower().strip()
        for category, info in _FAILURE_MODE_REDUCIBILITY.items():
            if ft in info["faults"]:
                return category
        return "structural"

    def compute(
        self,
        asset_data: List[Dict[str, Any]],
        alert_data: List[Dict[str, Any]],
        telemetry_summary: Dict[str, Any],
        health_data: List[Dict[str, Any]],
    ) -> KPIResult:
        cfg = self.config
        n_readings = telemetry_summary.get("telemetry_count", 0)

        # Categorize alerts by type
        actionable = [a for a in alert_data if a.get("alert_type") == "actionable"]
        watches = [a for a in alert_data if a.get("alert_type") == "watch"]
        resolved_confirmed = [
            a for a in alert_data
            if a.get("feedback_outcome") == "confirmed_fault"
        ]
        nif = [
            a for a in alert_data
            if a.get("feedback_outcome") == "no_issue_found"
        ]

        baseline_annual_reactive = cfg.baseline_reactive_wo_per_month * 12
        observed_reactive_annual = int(
            telemetry_summary.get("reactive_work_order_count_annual", 0) or 0
        )
        if observed_reactive_annual > 0:
            baseline_annual_reactive = max(baseline_annual_reactive, observed_reactive_annual)

        effective_wo_cost = float(cfg.avg_wo_cost)
        observed_wo_cost = float(telemetry_summary.get("work_order_avg_cost", 0) or 0)
        if observed_wo_cost > 0:
            effective_wo_cost = observed_wo_cost

        # ── Failure-mode decomposition (FMEA/RCM per SAE JA1011) ──
        # Classify alerts by failure mode category to apply category-specific
        # reduction rates instead of a single flat percentage.
        category_counts: Dict[str, int] = {cat: 0 for cat in _FAILURE_MODE_REDUCIBILITY}
        for alert in alert_data:
            fault = alert.get("primary_fault", "")
            cat = self._classify_fault(fault)
            category_counts[cat] += 1

        total_classified = sum(category_counts.values())

        # Compute failure mode distribution from real data or use industry defaults
        if total_classified >= 10:
            # Enough data for empirical distribution
            fm_distribution = {
                cat: count / total_classified
                for cat, count in category_counts.items()
            }
            distribution_source = "empirical"
        else:
            fm_distribution = _DEFAULT_FAILURE_MODE_DISTRIBUTION.copy()
            distribution_source = "industry_default"

        # Weighted reduction rate across all failure mode categories
        weighted_reduction = sum(
            fm_distribution[cat] * _FAILURE_MODE_REDUCIBILITY[cat]["reduction"]
            for cat in fm_distribution
        )

        # Adjust with empirical signal if confirmed fault detections exist
        prevented = len(resolved_confirmed)
        if baseline_annual_reactive > 0 and prevented > 0:
            empirical_reduction = min(0.50, prevented / baseline_annual_reactive)
            weighted_reduction = max(weighted_reduction, empirical_reduction)

        # Per-category savings breakdown
        category_savings = {}
        total_reduced_wos = 0.0
        for cat, pct in fm_distribution.items():
            cat_wos = baseline_annual_reactive * pct
            cat_reduction = _FAILURE_MODE_REDUCIBILITY[cat]["reduction"]
            cat_reduced = cat_wos * cat_reduction
            cat_savings_val = cat_reduced * effective_wo_cost
            category_savings[cat] = {
                "baseline_wos": round(cat_wos, 1),
                "reduction_rate": cat_reduction,
                "reduced_wos": round(cat_reduced, 1),
                "savings": round(cat_savings_val, 2),
            }
            total_reduced_wos += cat_reduced

        savings_medium = total_reduced_wos * effective_wo_cost

        low, med, high = self._tri_estimate(savings_medium, 0.5, 1.5)
        confidence = self._confidence_from_coverage(len(alert_data), 50, 0.50)
        if len(resolved_confirmed) > 5:
            confidence = min(1.0, confidence + 0.10)
        if distribution_source == "empirical":
            confidence = min(1.0, confidence + 0.05)

        # Find top failure mode category
        top_category = max(fm_distribution, key=fm_distribution.get)

        return self._make_result(
            savings_low=low,
            savings_medium=med,
            savings_high=high,
            confidence=confidence,
            status="approved" if confidence >= 0.5 else "pending",
            narrative=(
                f"Work order reduction targets {weighted_reduction*100:.0f}% fewer reactive WOs "
                f"(weighted by failure mode). {total_reduced_wos:.0f} WOs avoided at "
                f"${effective_wo_cost:,.0f}/WO = ${med:,.0f}/year. "
                f"Top failure mode: {top_category} ({fm_distribution[top_category]*100:.0f}% of WOs). "
                f"{prevented} confirmed fault detections support this estimate."
            ),
            assumptions=[
                f"Baseline reactive WOs: {baseline_annual_reactive}/year",
                f"Avg WO cost: ${effective_wo_cost} (ISO 14224: $250-$600 range)",
                f"Weighted reduction: {weighted_reduction*100:.0f}% (failure-mode decomposed, not flat %)",
                f"Failure mode distribution: {distribution_source}",
                "Reducibility: controls 50%, thermal 35%, mechanical 33%, "
                "refrigerant 28%, electrical 28%, structural 10%",
            ],
            supporting_metrics={
                "actionable_alerts": len(actionable),
                "confirmed_detections": len(resolved_confirmed),
                "nif_count": len(nif),
                "reduced_wos": round(total_reduced_wos),
                "weighted_reduction_pct": round(weighted_reduction, 3),
                "observed_reactive_wos_annual": observed_reactive_annual,
                "failure_mode_distribution": {k: round(v, 3) for k, v in fm_distribution.items()},
                "failure_mode_savings": category_savings,
                "distribution_source": distribution_source,
                "top_failure_mode": top_category,
            },
            data_points_used=len(alert_data),
            data_coverage_pct=min(100, len(alert_data) / 5),
        )
