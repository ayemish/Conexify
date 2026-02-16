"""
KPI Confidence Recalibration Service

Feeds actual work-order outcomes and M&V verification results back into
KPI confidence scores so predictions improve over time.

Tier 2 Fix: T2-9 (WO actuals → KPI confidence)
Tier 3 Fix: T3-17 (M&V verification wiring)
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import KPIConfig, KPIResult

logger = logging.getLogger(__name__)


def recalibrate_from_work_orders(
    results: List[KPIResult],
    config: KPIConfig,
) -> List[KPIResult]:
    """Adjust KPI confidence using actual work-order outcome data.

    Compares predicted savings (from KPI models) against realised savings
    (from WO cost actuals) and scales confidence proportionally.

    Returns the same list with updated confidence scores.
    """
    wo_actuals = _fetch_wo_actuals(config.site_id)
    if not wo_actuals:
        return results

    for result in results:
        adjustment = _compute_wo_adjustment(result, wo_actuals)
        if adjustment is not None:
            old_conf = result.confidence
            result.confidence = max(0.05, min(1.0, result.confidence * adjustment))
            result.supporting_metrics["wo_recalibration"] = {
                "adjustment_factor": round(adjustment, 3),
                "confidence_before": round(old_conf, 3),
                "confidence_after": round(result.confidence, 3),
                "source": "work_order_actuals",
            }
            # Re-evaluate auto-approval after recalibration
            if result.confidence >= 0.50 and result.status == "pending":
                result.approve()
            elif result.confidence < 0.50 and result.status == "approved":
                result.status = "pending"

    return results


def recalibrate_from_mv(
    results: List[KPIResult],
    config: KPIConfig,
) -> List[KPIResult]:
    """Adjust KPI confidence using M&V verification reconciliation reports.

    When the IPMVP M&V engine is available, compares predicted energy/cost
    savings against metered post-deployment baselines.
    """
    mv_report = _fetch_mv_report(config.site_id)
    if not mv_report:
        return results

    for result in results:
        kpi_mv = mv_report.get(result.kpi_name)
        if not kpi_mv:
            continue

        predicted = result.savings_medium
        verified = kpi_mv.get("verified_savings", 0.0)
        if predicted <= 0:
            continue

        # Accuracy ratio: how close prediction was to verified reality
        accuracy = min(verified / predicted, 2.0) if predicted > 0 else 0.0
        # Narrow confidence toward 1.0 when predictions are accurate
        if accuracy >= 0.8 and accuracy <= 1.2:
            boost = 1.0 + (accuracy - 1.0) * 0.5  # slight boost for accurate predictions
        elif accuracy < 0.8:
            boost = 0.7 + accuracy * 0.3  # penalise overestimation
        else:
            boost = 0.9  # slight penalty for underestimation

        old_conf = result.confidence
        result.confidence = max(0.05, min(1.0, result.confidence * boost))
        result.supporting_metrics["mv_recalibration"] = {
            "predicted_savings": round(predicted, 2),
            "verified_savings": round(verified, 2),
            "accuracy_ratio": round(accuracy, 3),
            "boost_factor": round(boost, 3),
            "confidence_before": round(old_conf, 3),
            "confidence_after": round(result.confidence, 3),
            "mv_plan_id": kpi_mv.get("plan_id", ""),
            "source": "ipmvp_mv_verification",
        }

    return results


def _fetch_wo_actuals(site_id: str) -> Dict[str, Any]:
    """Fetch aggregated work-order actuals from the database."""
    try:
        from ...persistence.database import get_session
        from ...persistence.models import WorkOrderModel
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        annual_start = now - timedelta(days=365)

        with get_session() as session:
            query = session.query(WorkOrderModel)
            if site_id != "default":
                query = query.filter(WorkOrderModel.site_id == site_id)
            work_orders = query.filter(WorkOrderModel.opened_at >= annual_start).all()

            if not work_orders:
                return {}

            reactive = [wo for wo in work_orders if (wo.wo_type or "").lower() in ("reactive", "emergency")]
            planned = [wo for wo in work_orders if (wo.wo_type or "").lower() in ("planned", "preventive", "pm")]
            total_cost = sum(float(wo.cost or 0) for wo in work_orders)
            reactive_cost = sum(float(wo.cost or 0) for wo in reactive)

            return {
                "total_wo_count": len(work_orders),
                "reactive_count": len(reactive),
                "planned_count": len(planned),
                "total_cost": total_cost,
                "reactive_cost": reactive_cost,
                "reactive_pct": len(reactive) / max(len(work_orders), 1),
                "avg_wo_cost": total_cost / max(len(work_orders), 1),
            }
    except Exception as e:
        logger.debug("WO actuals fetch failed: %s", e)
        return {}


def _compute_wo_adjustment(result: KPIResult, actuals: Dict[str, Any]) -> Optional[float]:
    """Compute a confidence adjustment factor for a KPI based on WO actuals.

    Returns a multiplier (0.5–1.5) or None if not applicable.
    """
    kpi = result.kpi_name

    if kpi == "work_order_reduction":
        # Compare predicted reduction rate vs actual reactive %
        actual_reactive_pct = actuals.get("reactive_pct", 0)
        predicted_reduction = result.supporting_metrics.get("predicted_reduction_pct", 0.25)
        if actual_reactive_pct > 0 and predicted_reduction > 0:
            # If actuals show fewer reactives than predicted baseline, boost confidence
            return min(1.3, 0.7 + actual_reactive_pct / max(predicted_reduction, 0.01) * 0.3)

    elif kpi == "service_bureau_reduction":
        if actuals.get("total_cost", 0) > 0:
            actual_avg = actuals["avg_wo_cost"]
            predicted_avg = result.supporting_metrics.get("avg_dispatch_cost", 450)
            ratio = min(actual_avg / max(predicted_avg, 1), 2.0)
            return 0.7 + ratio * 0.3

    elif kpi in ("energy_reduction", "refrigerant_leak_reduction", "asset_failure_prediction"):
        # Gentle boost if WO data exists (indicates active monitoring)
        if actuals.get("total_wo_count", 0) > 10:
            return 1.05

    return None


def _fetch_mv_report(site_id: str) -> Dict[str, Dict[str, Any]]:
    """Fetch M&V reconciliation results from the loweconex_platform M&V engine."""
    try:
        from loweconex_platform.mv_verification import MVEngine

        engine = MVEngine()
        reports = engine.get_reconciliation_reports(company_id=site_id)
        if not reports:
            return {}

        # Map KPI names to their latest reconciliation data
        mv_map = {}
        for report in reports:
            kpi_name = getattr(report, "kpi_name", None) or getattr(report, "measure_id", "")
            if kpi_name:
                mv_map[kpi_name] = {
                    "plan_id": getattr(report, "plan_id", ""),
                    "verified_savings": float(getattr(report, "verified_savings", 0)),
                    "measurement_period_days": getattr(report, "period_days", 0),
                    "confidence_level": getattr(report, "confidence_level", 0.9),
                }
        return mv_map
    except ImportError:
        logger.debug("M&V engine not available")
        return {}
    except Exception as e:
        logger.debug("M&V report fetch failed: %s", e)
        return {}
