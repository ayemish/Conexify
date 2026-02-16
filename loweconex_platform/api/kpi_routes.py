"""
KPI Dashboard API Routes — serves KPI results, scenario comparisons,
decision advisory output, and location rankings to the React frontend.

All routes enforce tenant isolation via AuthMiddleware.
Data comes from the in-memory pipeline cache (populated by OrchestratorCrew runs)
or from the ArtifactStore for historical results.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from loweconex_platform.execution.execution_engine import RecommendationTracker

logger = logging.getLogger(__name__)


class KPIDashboardCache:
    """
    In-memory cache for the latest pipeline results per company.
    Populated by OrchestratorCrew.run_full_pipeline() completion hook.
    In production, backed by Redis or PostgreSQL.
    """

    def __init__(self):
        self._results: Dict[str, Dict[str, Any]] = {}  # company_id -> composite_result

    def store(self, company_id: str, composite_result: Dict[str, Any]):
        self._results[company_id] = composite_result

    def get(self, company_id: str) -> Optional[Dict[str, Any]]:
        return self._results.get(company_id)

    def get_kpi_results(self, company_id: str) -> Dict[str, Any]:
        result = self.get(company_id)
        if not result:
            return {}
        return result.get("kpi_results", {})

    def get_scenarios(self, company_id: str) -> Dict[str, Any]:
        result = self.get(company_id)
        if not result:
            return {}
        return result.get("scenario_results", {})

    def get_advisory(self, company_id: str) -> Dict[str, Any]:
        result = self.get(company_id)
        if not result:
            return {}
        return result.get("decision_advisory", {})

    def get_executive_summary(self, company_id: str) -> Dict[str, Any]:
        result = self.get(company_id)
        if not result:
            return {}
        return result.get("executive_summary", {})

    def get_location_ranking(self, company_id: str) -> List[Dict[str, Any]]:
        result = self.get(company_id)
        if not result:
            return []
        return result.get("location_ranking", [])

    def get_governance(self, company_id: str) -> Dict[str, Any]:
        result = self.get(company_id)
        if not result:
            return {}
        return result.get("governance", {})


def create_kpi_routes(
    auth=None,
    cache: Optional[KPIDashboardCache] = None,
    recommendation_tracker: Optional[RecommendationTracker] = None,
) -> Dict[str, Any]:
    """
    Create KPI dashboard route handlers.

    Returns a dict of route_pattern -> handler for mounting into the API.
    """
    _cache = cache or KPIDashboardCache()
    _tracker = recommendation_tracker or RecommendationTracker()

    def _auth_check(authorization: str, company_id: str) -> Optional[Dict[str, Any]]:
        if auth:
            ctx = auth.authenticate(authorization)
            if not ctx.authenticated:
                return {"error": "Unauthorized", "status": 401}
            if not auth.authorize_company_access(ctx, company_id):
                return {"error": "Forbidden", "status": 403}
        return None

    # -----------------------------------------------------------------
    # GET /api/v1/kpi/{company_id}/dashboard
    # -----------------------------------------------------------------
    def get_dashboard(company_id: str, authorization: str = "") -> Dict[str, Any]:
        """Full dashboard payload: summary + all KPI scorecards + scenarios + advisory."""
        err = _auth_check(authorization, company_id)
        if err:
            return err

        composite = _cache.get(company_id)
        if not composite:
            return {"status": 404, "error": "No pipeline results found for this company"}

        kpi_results = composite.get("kpi_results", {})
        scorecards = []
        for kpi_name, result in kpi_results.items():
            r = result if isinstance(result, dict) else result.to_dict()
            scorecards.append({
                "kpi_name": kpi_name,
                "display_name": r.get("kpi_name", kpi_name).replace("_", " ").title(),
                "status": r.get("status", r.get("qa_status", "pending")),
                "savings_low": r.get("savings_low", 0),
                "savings_medium": r.get("savings_medium", 0),
                "savings_high": r.get("savings_high", 0),
                "confidence": r.get("confidence", 0),
                "narrative": r.get("narrative", ""),
                "assumptions": r.get("assumptions", []),
                "metrics": r.get("metrics", {}),
                "qa_issues": r.get("qa_issues", []),
            })

        scorecards.sort(key=lambda s: s["savings_medium"], reverse=True)

        return {
            "status": 200,
            "company_id": company_id,
            "run_id": composite.get("run_id", ""),
            "executive_summary": composite.get("executive_summary", {}),
            "scorecards": scorecards,
            "scenario_comparison": _build_scenario_comparison(composite),
            "decision_advisory": composite.get("decision_advisory", {}),
            "location_ranking": composite.get("location_ranking", []),
            "governance": composite.get("governance", {}),
            "roi": composite.get("roi", {}),
        }

    # -----------------------------------------------------------------
    # GET /api/v1/kpi/{company_id}/scorecards
    # -----------------------------------------------------------------
    def get_scorecards(company_id: str, authorization: str = "") -> Dict[str, Any]:
        err = _auth_check(authorization, company_id)
        if err:
            return err

        kpi_results = _cache.get_kpi_results(company_id)
        if not kpi_results:
            return {"status": 404, "error": "No KPI results found"}

        scorecards = []
        for kpi_name, result in kpi_results.items():
            r = result if isinstance(result, dict) else result.to_dict()
            scorecards.append({
                "kpi_name": kpi_name,
                "display_name": r.get("kpi_name", kpi_name).replace("_", " ").title(),
                "status": r.get("status", r.get("qa_status", "pending")),
                "savings_low": r.get("savings_low", 0),
                "savings_medium": r.get("savings_medium", 0),
                "savings_high": r.get("savings_high", 0),
                "confidence": r.get("confidence", 0),
                "narrative": r.get("narrative", ""),
            })
        scorecards.sort(key=lambda s: s["savings_medium"], reverse=True)
        return {"status": 200, "scorecards": scorecards}

    # -----------------------------------------------------------------
    # GET /api/v1/kpi/{company_id}/kpi/{kpi_name}
    # -----------------------------------------------------------------
    def get_kpi_detail(company_id: str, kpi_name: str, authorization: str = "") -> Dict[str, Any]:
        err = _auth_check(authorization, company_id)
        if err:
            return err

        kpi_results = _cache.get_kpi_results(company_id)
        result = kpi_results.get(kpi_name)
        if not result:
            return {"status": 404, "error": f"KPI '{kpi_name}' not found"}

        r = result if isinstance(result, dict) else result.to_dict()
        return {"status": 200, "kpi": r}

    # -----------------------------------------------------------------
    # GET /api/v1/kpi/{company_id}/scenarios
    # -----------------------------------------------------------------
    def get_scenarios(company_id: str, authorization: str = "") -> Dict[str, Any]:
        err = _auth_check(authorization, company_id)
        if err:
            return err
        scenarios = _cache.get_scenarios(company_id)
        if not scenarios:
            return {"status": 404, "error": "No scenario results found"}
        return {"status": 200, "scenarios": scenarios}

    # -----------------------------------------------------------------
    # GET /api/v1/kpi/{company_id}/advisory
    # -----------------------------------------------------------------
    def get_advisory(company_id: str, authorization: str = "") -> Dict[str, Any]:
        err = _auth_check(authorization, company_id)
        if err:
            return err
        advisory = _cache.get_advisory(company_id)
        if not advisory:
            return {"status": 404, "error": "No advisory output found"}
        return {"status": 200, "advisory": advisory}

    # -----------------------------------------------------------------
    # GET /api/v1/kpi/{company_id}/locations
    # -----------------------------------------------------------------
    def get_location_ranking(company_id: str, authorization: str = "") -> Dict[str, Any]:
        err = _auth_check(authorization, company_id)
        if err:
            return err
        ranking = _cache.get_location_ranking(company_id)
        return {"status": 200, "locations": ranking}

    # -----------------------------------------------------------------
    # GET /api/v1/kpi/{company_id}/recommendations
    # -----------------------------------------------------------------
    def get_recommendations(company_id: str, authorization: str = "") -> Dict[str, Any]:
        """List all recommendations for a company with their lifecycle status."""
        err = _auth_check(authorization, company_id)
        if err:
            return err
        recs = _tracker.get_by_company(company_id)
        return {
            "status": 200,
            "recommendations": [r.to_dict() for r in recs],
            "stats": _tracker.acceptance_rate(),
        }

    # -----------------------------------------------------------------
    # POST /api/v1/kpi/{company_id}/recommendations/{rec_id}/accept
    # -----------------------------------------------------------------
    def accept_recommendation(
        company_id: str, rec_id: str,
        accepted_by: str = "operator",
        modifications: Optional[List[str]] = None,
        authorization: str = "",
    ) -> Dict[str, Any]:
        """Operator accepts (or partially accepts) a recommendation."""
        err = _auth_check(authorization, company_id)
        if err:
            return err
        rec = _tracker.get(rec_id)
        if not rec:
            return {"status": 404, "error": f"Recommendation '{rec_id}' not found"}
        if rec.company_id != company_id:
            return {"status": 403, "error": "Tenant boundary violation"}
        _tracker.accept(rec_id, accepted_by, modifications)
        logger.info(f"Recommendation {rec_id} accepted by {accepted_by}")
        return {"status": 200, "rec_id": rec_id, "acceptance_status": rec.acceptance_status}

    # -----------------------------------------------------------------
    # POST /api/v1/kpi/{company_id}/recommendations/{rec_id}/reject
    # -----------------------------------------------------------------
    def reject_recommendation(
        company_id: str, rec_id: str,
        reason: str = "",
        authorization: str = "",
    ) -> Dict[str, Any]:
        """Operator rejects a recommendation with a reason."""
        err = _auth_check(authorization, company_id)
        if err:
            return err
        rec = _tracker.get(rec_id)
        if not rec:
            return {"status": 404, "error": f"Recommendation '{rec_id}' not found"}
        if rec.company_id != company_id:
            return {"status": 403, "error": "Tenant boundary violation"}
        _tracker.reject(rec_id, reason)
        logger.info(f"Recommendation {rec_id} rejected: {reason}")
        return {"status": 200, "rec_id": rec_id, "acceptance_status": "rejected"}

    # -----------------------------------------------------------------
    # POST /api/v1/kpi/{company_id}/recommendations/{rec_id}/implement
    # -----------------------------------------------------------------
    def record_implementation(
        company_id: str, rec_id: str,
        implementation_date: str = "",
        work_order_ids: Optional[List[str]] = None,
        authorization: str = "",
    ) -> Dict[str, Any]:
        """Record that a recommendation has been implemented."""
        err = _auth_check(authorization, company_id)
        if err:
            return err
        rec = _tracker.get(rec_id)
        if not rec:
            return {"status": 404, "error": f"Recommendation '{rec_id}' not found"}
        if rec.company_id != company_id:
            return {"status": 403, "error": "Tenant boundary violation"}
        from datetime import datetime
        date = implementation_date or datetime.utcnow().isoformat()
        _tracker.record_implementation(rec_id, date, work_order_ids)
        logger.info(f"Recommendation {rec_id} implemented on {date}")
        return {"status": 200, "rec_id": rec_id, "implemented": True}

    # -----------------------------------------------------------------
    # POST /api/v1/kpi/{company_id}/recommendations/{rec_id}/outcome
    # -----------------------------------------------------------------
    def record_outcome(
        company_id: str, rec_id: str,
        actual_savings_usd: float = 0.0,
        actual_cost_usd: float = 0.0,
        notes: str = "",
        authorization: str = "",
    ) -> Dict[str, Any]:
        """Record actual outcome for a recommendation (closes the feedback loop)."""
        err = _auth_check(authorization, company_id)
        if err:
            return err
        rec = _tracker.get(rec_id)
        if not rec:
            return {"status": 404, "error": f"Recommendation '{rec_id}' not found"}
        if rec.company_id != company_id:
            return {"status": 403, "error": "Tenant boundary violation"}
        _tracker.record_outcome(rec_id, actual_savings_usd, actual_cost_usd, notes)
        realization = (
            actual_savings_usd / rec.estimated_savings_usd
            if rec.estimated_savings_usd > 0 else 0
        )
        logger.info(
            f"Recommendation {rec_id} outcome: actual=${actual_savings_usd:,.0f} "
            f"(realization={realization:.0%})"
        )
        return {
            "status": 200,
            "rec_id": rec_id,
            "actual_savings_usd": actual_savings_usd,
            "realization_pct": realization,
        }

    # -----------------------------------------------------------------
    # GET /api/v1/kpi/{company_id}/feedback-stats
    # -----------------------------------------------------------------
    def get_feedback_stats(company_id: str, authorization: str = "") -> Dict[str, Any]:
        """Aggregate feedback statistics for the advisory learning loop."""
        err = _auth_check(authorization, company_id)
        if err:
            return err
        stats = _tracker.acceptance_rate()
        company_recs = _tracker.get_by_company(company_id)

        # Per-KPI realization
        kpi_realization = {}
        for rec in company_recs:
            if rec.actual_savings_usd is not None and rec.estimated_savings_usd > 0:
                kpi = rec.kpi_name or "unknown"
                kpi_realization.setdefault(kpi, {"estimated": 0, "actual": 0})
                kpi_realization[kpi]["estimated"] += rec.estimated_savings_usd
                kpi_realization[kpi]["actual"] += rec.actual_savings_usd

        for kpi, vals in kpi_realization.items():
            vals["realization_pct"] = (
                vals["actual"] / vals["estimated"] if vals["estimated"] > 0 else 0
            )

        return {
            "status": 200,
            "aggregate": stats,
            "company_total_recommendations": len(company_recs),
            "kpi_realization": kpi_realization,
        }

    routes = {
        "GET /api/v1/kpi/{company_id}/dashboard": get_dashboard,
        "GET /api/v1/kpi/{company_id}/scorecards": get_scorecards,
        "GET /api/v1/kpi/{company_id}/kpi/{kpi_name}": get_kpi_detail,
        "GET /api/v1/kpi/{company_id}/scenarios": get_scenarios,
        "GET /api/v1/kpi/{company_id}/advisory": get_advisory,
        "GET /api/v1/kpi/{company_id}/locations": get_location_ranking,
        "GET /api/v1/kpi/{company_id}/recommendations": get_recommendations,
        "POST /api/v1/kpi/{company_id}/recommendations/{rec_id}/accept": accept_recommendation,
        "POST /api/v1/kpi/{company_id}/recommendations/{rec_id}/reject": reject_recommendation,
        "POST /api/v1/kpi/{company_id}/recommendations/{rec_id}/implement": record_implementation,
        "POST /api/v1/kpi/{company_id}/recommendations/{rec_id}/outcome": record_outcome,
        "GET /api/v1/kpi/{company_id}/feedback-stats": get_feedback_stats,
    }

    return {"routes": routes, "cache": _cache, "recommendation_tracker": _tracker}


def _build_scenario_comparison(composite: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build a structured scenario comparison from composite results."""
    scenarios = composite.get("scenario_results", {})
    comparison = []
    for name, data in scenarios.items():
        kpi_impacts = data.get("kpi_impacts", {})
        total_savings = sum(
            v.get("savings_medium", 0) for v in kpi_impacts.values()
        ) if isinstance(kpi_impacts, dict) else 0

        comparison.append({
            "scenario_name": name,
            "description": data.get("description", ""),
            "total_savings_medium": total_savings,
            "kpi_count": len(kpi_impacts),
            "kpi_impacts": kpi_impacts,
        })
    comparison.sort(key=lambda s: s["total_savings_medium"], reverse=True)
    return comparison
