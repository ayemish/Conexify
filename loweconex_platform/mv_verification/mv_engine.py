"""
M&V Engine — IPMVP-aligned Measurement & Verification.

Implements:
- M&V Plan objects per customer/location/KPI with baseline windows,
  adjustment rules, and uncertainty reporting
- IPMVP Option A–D support
- Continuous reconciliation engine comparing predicted vs realized savings
- Savings confidence bounds (statistical uncertainty propagation)
- Period-over-period reconciliation reports

References:
- IPMVP (Efficiency Valuation Organization)
- DOE Uniform Methods Project (LBNL rigor for whole-facility claims)
- ASHRAE Guideline 14 for measurement uncertainty
"""

from __future__ import annotations

import logging
import math
import statistics
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# IPMVP Options
# =============================================================================

class IPMVPOption(str, Enum):
    """IPMVP measurement boundary options."""
    OPTION_A = "A"   # Retrofit Isolation: Key Parameter Measurement
    OPTION_B = "B"   # Retrofit Isolation: All Parameter Measurement
    OPTION_C = "C"   # Whole Facility
    OPTION_D = "D"   # Calibrated Simulation


class AdjustmentType(str, Enum):
    """Types of baseline adjustments."""
    WEATHER = "weather"
    OCCUPANCY = "occupancy"
    PRODUCTION = "production"
    SCHEDULE = "schedule"
    EQUIPMENT_CHANGE = "equipment_change"
    RATE_CHANGE = "rate_change"
    CUSTOM = "custom"


class ReconciliationStatus(str, Enum):
    """Period reconciliation outcome."""
    ON_TRACK = "on_track"             # Realized within confidence bounds
    ABOVE_EXPECTED = "above_expected"  # Beating forecast
    BELOW_EXPECTED = "below_expected"  # Underperforming
    SIGNIFICANTLY_OFF = "significantly_off"  # Outside 2-sigma
    INSUFFICIENT_DATA = "insufficient_data"


# =============================================================================
# Baseline and adjustment models
# =============================================================================

@dataclass
class BaselineWindow:
    """
    Defines the baseline measurement period for M&V.
    """
    window_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    start_date: str = ""      # ISO date
    end_date: str = ""
    description: str = ""

    # Baseline metrics
    energy_kwh: Optional[float] = None
    cost_usd: Optional[float] = None
    degree_days_heating: Optional[float] = None
    degree_days_cooling: Optional[float] = None
    operating_hours: Optional[float] = None

    # Statistical properties
    mean_daily: Optional[float] = None
    std_daily: Optional[float] = None
    n_days: int = 0
    cv_rmse: Optional[float] = None  # Coefficient of variation of RMSE

    # Data quality
    completeness_pct: float = 100.0
    excluded_periods: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "window_id": self.window_id,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "description": self.description,
            "energy_kwh": self.energy_kwh,
            "cost_usd": self.cost_usd,
            "degree_days_heating": self.degree_days_heating,
            "degree_days_cooling": self.degree_days_cooling,
            "operating_hours": self.operating_hours,
            "mean_daily": self.mean_daily,
            "std_daily": self.std_daily,
            "n_days": self.n_days,
            "cv_rmse": self.cv_rmse,
            "completeness_pct": self.completeness_pct,
            "excluded_periods": self.excluded_periods,
        }


@dataclass
class AdjustmentRule:
    """
    A rule for adjusting baseline to reporting-period conditions.
    """
    rule_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    adjustment_type: str = AdjustmentType.WEATHER.value
    description: str = ""
    variable: str = ""          # e.g., "CDD_65", "occupancy_hours"
    method: str = "regression"  # regression, ratio, degree_day, manual
    coefficient: Optional[float] = None
    intercept: Optional[float] = None
    r_squared: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "adjustment_type": self.adjustment_type,
            "description": self.description,
            "variable": self.variable,
            "method": self.method,
            "coefficient": self.coefficient,
            "intercept": self.intercept,
            "r_squared": self.r_squared,
        }

    def compute_adjustment(self, baseline_value: float, reporting_value: float) -> float:
        """Compute the adjustment amount for a given variable change."""
        if self.coefficient is not None:
            return self.coefficient * (reporting_value - baseline_value)
        return 0.0


# =============================================================================
# M&V Plan
# =============================================================================

@dataclass
class MVPlan:
    """
    M&V Plan per customer/location/KPI.

    Defines how savings will be measured and verified over time,
    including baseline, adjustments, reporting periods, and acceptance criteria.
    """
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str = ""
    location_id: Optional[str] = None
    kpi_name: Optional[str] = None

    # IPMVP option
    ipmvp_option: str = IPMVPOption.OPTION_C.value
    measurement_boundary: str = "whole_facility"

    # Baseline
    baseline: Optional[BaselineWindow] = None
    adjustment_rules: List[AdjustmentRule] = field(default_factory=list)

    # Reporting configuration
    reporting_frequency: str = "monthly"  # monthly, quarterly, annual
    review_cadence: str = "quarterly"
    acceptance_cv_rmse: float = 0.25  # ASHRAE Guideline 14: CV(RMSE) < 25%
    acceptance_nmbe: float = 0.05     # ASHRAE Guideline 14: NMBE < 5%
    min_savings_significance: float = 0.10  # 10% minimum to claim

    # Uncertainty
    confidence_level: float = 0.90  # 90% confidence interval
    precision_target: float = 0.50  # +/- 50% at confidence level (IPMVP)

    # Metadata
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    approved_by: Optional[str] = None
    approved_ts: Optional[str] = None
    status: str = "draft"  # draft, approved, active, closed

    # Reconciliation history
    reconciliation_history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "company_id": self.company_id,
            "location_id": self.location_id,
            "kpi_name": self.kpi_name,
            "ipmvp_option": self.ipmvp_option,
            "measurement_boundary": self.measurement_boundary,
            "baseline": self.baseline.to_dict() if self.baseline else None,
            "adjustment_rules": [r.to_dict() for r in self.adjustment_rules],
            "reporting_frequency": self.reporting_frequency,
            "review_cadence": self.review_cadence,
            "acceptance_cv_rmse": self.acceptance_cv_rmse,
            "acceptance_nmbe": self.acceptance_nmbe,
            "min_savings_significance": self.min_savings_significance,
            "confidence_level": self.confidence_level,
            "precision_target": self.precision_target,
            "created_ts": self.created_ts,
            "approved_by": self.approved_by,
            "approved_ts": self.approved_ts,
            "status": self.status,
            "reconciliation_count": len(self.reconciliation_history),
        }


# =============================================================================
# Reconciliation report
# =============================================================================

@dataclass
class ReconciliationReport:
    """
    Period reconciliation: compares predicted savings against actuals.
    """
    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    plan_id: str = ""
    period_start: str = ""
    period_end: str = ""

    # Predicted (from KPI model)
    predicted_savings_kwh: float = 0.0
    predicted_savings_usd: float = 0.0
    predicted_confidence_low: float = 0.0
    predicted_confidence_high: float = 0.0

    # Actual (measured)
    actual_baseline_adjusted_kwh: float = 0.0
    actual_reporting_kwh: float = 0.0
    actual_savings_kwh: float = 0.0
    actual_savings_usd: float = 0.0

    # Adjustments applied
    adjustments_applied: List[Dict[str, Any]] = field(default_factory=list)
    total_adjustment_kwh: float = 0.0

    # Statistical metrics
    cv_rmse: Optional[float] = None
    nmbe: Optional[float] = None
    t_statistic: Optional[float] = None
    savings_uncertainty_pct: Optional[float] = None

    # Status
    status: str = ReconciliationStatus.INSUFFICIENT_DATA.value
    explanation: str = ""
    action_items: List[str] = field(default_factory=list)

    # Metadata
    generated_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    reviewed_by: Optional[str] = None
    reviewed_ts: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "plan_id": self.plan_id,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "predicted_savings_kwh": self.predicted_savings_kwh,
            "predicted_savings_usd": self.predicted_savings_usd,
            "predicted_confidence_low": self.predicted_confidence_low,
            "predicted_confidence_high": self.predicted_confidence_high,
            "actual_baseline_adjusted_kwh": self.actual_baseline_adjusted_kwh,
            "actual_reporting_kwh": self.actual_reporting_kwh,
            "actual_savings_kwh": self.actual_savings_kwh,
            "actual_savings_usd": self.actual_savings_usd,
            "adjustments_applied": self.adjustments_applied,
            "total_adjustment_kwh": self.total_adjustment_kwh,
            "cv_rmse": self.cv_rmse,
            "nmbe": self.nmbe,
            "t_statistic": self.t_statistic,
            "savings_uncertainty_pct": self.savings_uncertainty_pct,
            "status": self.status,
            "explanation": self.explanation,
            "action_items": self.action_items,
            "generated_ts": self.generated_ts,
            "reviewed_by": self.reviewed_by,
            "reviewed_ts": self.reviewed_ts,
        }


# =============================================================================
# M&V Engine
# =============================================================================

class MVEngine:
    """
    M&V reconciliation engine.

    Manages M&V plans, runs period reconciliations, computes savings
    confidence bounds, and generates reconciliation reports.
    """

    def __init__(self):
        self._plans: Dict[str, MVPlan] = {}

    def register_plan(self, plan: MVPlan):
        self._plans[plan.plan_id] = plan
        logger.info(f"Registered M&V plan {plan.plan_id} for {plan.company_id}")

    def get_plan(self, plan_id: str) -> Optional[MVPlan]:
        return self._plans.get(plan_id)

    def get_plans_for_location(
        self, company_id: str, location_id: str
    ) -> List[MVPlan]:
        return [
            p for p in self._plans.values()
            if p.company_id == company_id and p.location_id == location_id
        ]

    def reconcile_period(
        self,
        plan_id: str,
        period_start: str,
        period_end: str,
        predicted_savings_kwh: float,
        predicted_savings_usd: float,
        actual_baseline_kwh: float,
        actual_reporting_kwh: float,
        reporting_conditions: Optional[Dict[str, float]] = None,
        utility_rate: float = 0.10,
    ) -> ReconciliationReport:
        """
        Run a period reconciliation for an M&V plan.

        Compares predicted savings against adjusted baseline minus actuals.
        """
        plan = self._plans.get(plan_id)
        if not plan:
            raise ValueError(f"M&V plan {plan_id} not found")

        report = ReconciliationReport(
            plan_id=plan_id,
            period_start=period_start,
            period_end=period_end,
            predicted_savings_kwh=predicted_savings_kwh,
            predicted_savings_usd=predicted_savings_usd,
        )

        # Apply baseline adjustments
        adjusted_baseline = actual_baseline_kwh
        conditions = reporting_conditions or {}

        for rule in plan.adjustment_rules:
            if rule.variable in conditions and plan.baseline:
                baseline_val = getattr(plan.baseline, rule.variable, None)
                if baseline_val is None:
                    baseline_val = plan.baseline.mean_daily or 0
                reporting_val = conditions[rule.variable]
                adj = rule.compute_adjustment(baseline_val, reporting_val)
                adjusted_baseline += adj
                report.adjustments_applied.append({
                    "rule_id": rule.rule_id,
                    "type": rule.adjustment_type,
                    "variable": rule.variable,
                    "adjustment_kwh": adj,
                })
                report.total_adjustment_kwh += adj

        report.actual_baseline_adjusted_kwh = adjusted_baseline
        report.actual_reporting_kwh = actual_reporting_kwh
        report.actual_savings_kwh = adjusted_baseline - actual_reporting_kwh
        report.actual_savings_usd = report.actual_savings_kwh * utility_rate

        # Compute uncertainty
        uncertainty = self._compute_uncertainty(plan, report)
        report.cv_rmse = uncertainty.get("cv_rmse")
        report.nmbe = uncertainty.get("nmbe")
        report.t_statistic = uncertainty.get("t_statistic")
        report.savings_uncertainty_pct = uncertainty.get("uncertainty_pct")

        # Confidence bounds on predicted
        if predicted_savings_kwh > 0:
            half_width = predicted_savings_kwh * (report.savings_uncertainty_pct or 0.5)
            report.predicted_confidence_low = predicted_savings_kwh - half_width
            report.predicted_confidence_high = predicted_savings_kwh + half_width

        # Determine status
        report.status = self._determine_status(report)
        report.explanation = self._generate_explanation(report)
        report.action_items = self._generate_actions(report, plan)

        # Record in plan history
        plan.reconciliation_history.append(report.to_dict())

        logger.info(
            f"M&V reconciliation for plan {plan_id}: "
            f"predicted={predicted_savings_kwh:.0f} kWh, "
            f"actual={report.actual_savings_kwh:.0f} kWh, "
            f"status={report.status}"
        )
        return report

    def _compute_uncertainty(
        self, plan: MVPlan, report: ReconciliationReport
    ) -> Dict[str, float]:
        """
        Compute savings uncertainty per ASHRAE Guideline 14 / IPMVP.

        CV(RMSE) = RMSE / mean_baseline
        NMBE = sum(residuals) / (n * mean_baseline)
        Savings uncertainty = t * (CV(RMSE) / sqrt(n)) * F * (baseline/savings)
        """
        baseline = plan.baseline
        if not baseline or not baseline.mean_daily or baseline.n_days < 2:
            return {"cv_rmse": None, "nmbe": None, "uncertainty_pct": 0.50}

        n = baseline.n_days
        mean_b = baseline.mean_daily
        std_b = baseline.std_daily or mean_b * 0.15

        # CV(RMSE) from baseline model fit
        cv_rmse = baseline.cv_rmse or (std_b / mean_b if mean_b > 0 else 0.25)

        # NMBE approximation
        nmbe = 0.0
        if report.actual_baseline_adjusted_kwh > 0:
            residual = report.actual_baseline_adjusted_kwh - report.actual_reporting_kwh
            nmbe = residual / report.actual_baseline_adjusted_kwh

        # t-statistic for confidence level
        t_stat = 1.645 if plan.confidence_level >= 0.90 else 1.96

        # Fractional savings uncertainty (IPMVP equation)
        if report.actual_savings_kwh > 0 and mean_b > 0:
            f_factor = 1.0  # Autocorrelation correction
            savings_frac = report.actual_savings_kwh / (mean_b * n)
            if savings_frac > 0:
                uncertainty_pct = t_stat * (cv_rmse / math.sqrt(n)) * f_factor / savings_frac
                uncertainty_pct = min(uncertainty_pct, 2.0)  # Cap at 200%
            else:
                uncertainty_pct = 1.0
        else:
            uncertainty_pct = 0.50

        return {
            "cv_rmse": round(cv_rmse, 4),
            "nmbe": round(nmbe, 4),
            "t_statistic": t_stat,
            "uncertainty_pct": round(uncertainty_pct, 4),
        }

    def _determine_status(self, report: ReconciliationReport) -> str:
        if report.actual_savings_kwh == 0 and report.predicted_savings_kwh == 0:
            return ReconciliationStatus.INSUFFICIENT_DATA.value

        if report.predicted_savings_kwh <= 0:
            return ReconciliationStatus.INSUFFICIENT_DATA.value

        ratio = report.actual_savings_kwh / report.predicted_savings_kwh

        if report.predicted_confidence_low <= report.actual_savings_kwh <= report.predicted_confidence_high:
            if ratio >= 1.0:
                return ReconciliationStatus.ABOVE_EXPECTED.value
            return ReconciliationStatus.ON_TRACK.value
        elif report.actual_savings_kwh > report.predicted_confidence_high:
            return ReconciliationStatus.ABOVE_EXPECTED.value
        elif report.actual_savings_kwh < report.predicted_confidence_low:
            if ratio < 0.5:
                return ReconciliationStatus.SIGNIFICANTLY_OFF.value
            return ReconciliationStatus.BELOW_EXPECTED.value

        return ReconciliationStatus.ON_TRACK.value

    def _generate_explanation(self, report: ReconciliationReport) -> str:
        if report.status == ReconciliationStatus.ON_TRACK.value:
            return (
                f"Realized savings ({report.actual_savings_kwh:,.0f} kWh) are within "
                f"the predicted confidence interval "
                f"[{report.predicted_confidence_low:,.0f}, {report.predicted_confidence_high:,.0f}] kWh."
            )
        elif report.status == ReconciliationStatus.ABOVE_EXPECTED.value:
            return (
                f"Realized savings ({report.actual_savings_kwh:,.0f} kWh) exceed "
                f"predictions ({report.predicted_savings_kwh:,.0f} kWh). "
                f"Verify no non-routine adjustments are needed."
            )
        elif report.status == ReconciliationStatus.BELOW_EXPECTED.value:
            return (
                f"Realized savings ({report.actual_savings_kwh:,.0f} kWh) are below "
                f"the lower confidence bound ({report.predicted_confidence_low:,.0f} kWh). "
                f"Investigation recommended."
            )
        elif report.status == ReconciliationStatus.SIGNIFICANTLY_OFF.value:
            return (
                f"Realized savings ({report.actual_savings_kwh:,.0f} kWh) are significantly "
                f"below predictions ({report.predicted_savings_kwh:,.0f} kWh). "
                f"Root cause analysis required."
            )
        return "Insufficient data to assess savings realization."

    def _generate_actions(
        self, report: ReconciliationReport, plan: MVPlan
    ) -> List[str]:
        actions = []

        if report.cv_rmse and report.cv_rmse > plan.acceptance_cv_rmse:
            actions.append(
                f"CV(RMSE) ({report.cv_rmse:.2%}) exceeds acceptance threshold "
                f"({plan.acceptance_cv_rmse:.0%}). Improve baseline model."
            )

        if report.nmbe and abs(report.nmbe) > plan.acceptance_nmbe:
            actions.append(
                f"NMBE ({report.nmbe:.2%}) exceeds threshold ({plan.acceptance_nmbe:.0%}). "
                f"Check for systematic bias."
            )

        if report.status == ReconciliationStatus.SIGNIFICANTLY_OFF.value:
            actions.append("Schedule root cause analysis within 2 weeks.")
            actions.append("Check for non-routine events (equipment changes, occupancy shifts).")

        if report.status == ReconciliationStatus.BELOW_EXPECTED.value:
            actions.append("Review adjustment rules for missing variables.")
            actions.append("Verify measurement data quality.")

        if not actions:
            actions.append("No action required. Continue monitoring.")

        return actions

    def generate_summary(self, plan_id: str) -> Dict[str, Any]:
        """Generate a summary of all reconciliation periods for a plan."""
        plan = self._plans.get(plan_id)
        if not plan:
            return {"error": f"Plan {plan_id} not found"}

        history = plan.reconciliation_history
        if not history:
            return {"plan_id": plan_id, "periods": 0, "message": "No reconciliations yet"}

        total_predicted = sum(h.get("predicted_savings_kwh", 0) for h in history)
        total_actual = sum(h.get("actual_savings_kwh", 0) for h in history)
        statuses = [h.get("status", "") for h in history]

        return {
            "plan_id": plan_id,
            "company_id": plan.company_id,
            "location_id": plan.location_id,
            "kpi_name": plan.kpi_name,
            "ipmvp_option": plan.ipmvp_option,
            "periods": len(history),
            "total_predicted_kwh": total_predicted,
            "total_actual_kwh": total_actual,
            "realization_rate": total_actual / total_predicted if total_predicted > 0 else None,
            "on_track_periods": statuses.count(ReconciliationStatus.ON_TRACK.value),
            "above_periods": statuses.count(ReconciliationStatus.ABOVE_EXPECTED.value),
            "below_periods": statuses.count(ReconciliationStatus.BELOW_EXPECTED.value),
            "off_periods": statuses.count(ReconciliationStatus.SIGNIFICANTLY_OFF.value),
        }
