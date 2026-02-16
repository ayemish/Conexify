"""
Governance API Routes — /api/v1/governance/*

Exposes endpoints for:
- Compliance reports
- Risk heat maps
- SLA dashboards
- Exception boards
- Lineage thread queries
- Model registry status
- Data quality gate history
- Benchmark comparisons

Phase 3.4 integration — follows the same handler-dict pattern as server.py.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Graceful imports for enterprise modules
try:
    from loweconex_platform.security.security_controls import SecurityControlsRegistry
    SECURITY_AVAILABLE = True
except ImportError:
    SECURITY_AVAILABLE = False

try:
    from loweconex_platform.ai_risk.ai_risk_framework import AIRiskRegistry
    RISK_AVAILABLE = True
except ImportError:
    RISK_AVAILABLE = False

try:
    from loweconex_platform.operating_model.operating_model import (
        SLATracker, ExceptionManager,
    )
    OPERATING_MODEL_AVAILABLE = True
except ImportError:
    OPERATING_MODEL_AVAILABLE = False

try:
    from loweconex_platform.lineage.lineage_tracker import LineageTracker
    LINEAGE_AVAILABLE = True
except ImportError:
    LINEAGE_AVAILABLE = False

try:
    from loweconex_platform.mlops.model_registry import ModelRegistry
    MLOPS_AVAILABLE = True
except ImportError:
    MLOPS_AVAILABLE = False

try:
    from loweconex_platform.data_quality.quality_engine import DataQualityEngine
    DQ_AVAILABLE = True
except ImportError:
    DQ_AVAILABLE = False

try:
    from loweconex_platform.benchmarking.benchmark_engine import BenchmarkEngine
    BENCHMARK_AVAILABLE = True
except ImportError:
    BENCHMARK_AVAILABLE = False

try:
    from loweconex_platform.agent_ops.agent_ops_engine import AgentHealthMonitor
    AGENT_OPS_AVAILABLE = True
except ImportError:
    AGENT_OPS_AVAILABLE = False


def _require_auth(auth, authorization: str, company_id: str, permission: str) -> Optional[Dict[str, Any]]:
    """Shared auth check. Returns error dict or None if authorized."""
    ctx = auth.authenticate(authorization)
    if not ctx.authenticated:
        return {"error": "Unauthorized", "status": 401}
    if not auth.authorize_company_access(ctx, company_id):
        return {"error": "Forbidden: tenant boundary violation", "status": 403}
    if not auth.authorize_permission(ctx, permission):
        return {"error": "Forbidden: insufficient permissions", "status": 403}
    return None


def create_governance_routes(
    auth: Any,
    security_registry: Optional[Any] = None,
    risk_registry: Optional[Any] = None,
    sla_tracker: Optional[Any] = None,
    exception_manager: Optional[Any] = None,
    lineage_tracker: Optional[Any] = None,
    model_registry: Optional[Any] = None,
    dq_engine: Optional[Any] = None,
    benchmark_engine: Optional[Any] = None,
    health_monitor: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Create governance API route handlers.

    Returns a dict of route handlers in the same format as server.create_app().
    """

    # --- Compliance Reports ---

    def get_compliance_report(company_id: str, authorization: str) -> Dict[str, Any]:
        """GET /api/v1/governance/{company_id}/compliance"""
        err = _require_auth(auth, authorization, company_id, "view_compliance")
        if err:
            return err
        if not security_registry:
            return {"status": 503, "error": "Security controls registry not available"}
        try:
            report = security_registry.generate_compliance_report()
            return {"status": 200, "company_id": company_id, "compliance_report": report}
        except Exception as e:
            logger.error(f"Compliance report failed: {e}")
            return {"status": 500, "error": str(e)}

    # --- Risk Heat Map ---

    def get_risk_heatmap(company_id: str, authorization: str) -> Dict[str, Any]:
        """GET /api/v1/governance/{company_id}/risks/heatmap"""
        err = _require_auth(auth, authorization, company_id, "view_risks")
        if err:
            return err
        if not risk_registry:
            return {"status": 503, "error": "AI risk registry not available"}
        try:
            risks = risk_registry.get_all_risks()
            heatmap = _build_risk_heatmap(risks)
            return {"status": 200, "company_id": company_id, "heatmap": heatmap}
        except Exception as e:
            logger.error(f"Risk heatmap failed: {e}")
            return {"status": 500, "error": str(e)}

    # --- SLA Dashboard ---

    def get_sla_dashboard(company_id: str, authorization: str) -> Dict[str, Any]:
        """GET /api/v1/governance/{company_id}/sla/dashboard"""
        err = _require_auth(auth, authorization, company_id, "view_sla")
        if err:
            return err
        if not sla_tracker:
            return {"status": 503, "error": "SLA tracker not available"}
        try:
            summary = sla_tracker.summary()
            return {"status": 200, "company_id": company_id, "sla_dashboard": summary}
        except Exception as e:
            logger.error(f"SLA dashboard failed: {e}")
            return {"status": 500, "error": str(e)}

    # --- Exception Board ---

    def get_exception_board(company_id: str, authorization: str,
                            status_filter: Optional[str] = None) -> Dict[str, Any]:
        """GET /api/v1/governance/{company_id}/exceptions"""
        err = _require_auth(auth, authorization, company_id, "view_exceptions")
        if err:
            return err
        if not exception_manager:
            return {"status": 503, "error": "Exception manager not available"}
        try:
            exceptions = exception_manager.get_by_company(company_id)
            if status_filter:
                exceptions = [e for e in exceptions if e.status == status_filter]
            return {
                "status": 200,
                "company_id": company_id,
                "exceptions": [e.to_dict() if hasattr(e, 'to_dict') else vars(e) for e in exceptions],
                "total": len(exceptions),
            }
        except Exception as e:
            logger.error(f"Exception board failed: {e}")
            return {"status": 500, "error": str(e)}

    def get_exception_detail(company_id: str, exception_id: str,
                             authorization: str) -> Dict[str, Any]:
        """GET /api/v1/governance/{company_id}/exceptions/{exception_id}"""
        err = _require_auth(auth, authorization, company_id, "view_exceptions")
        if err:
            return err
        if not exception_manager:
            return {"status": 503, "error": "Exception manager not available"}
        try:
            exc = exception_manager.get(exception_id)
            if not exc:
                return {"status": 404, "error": "Exception not found"}
            return {
                "status": 200,
                "exception": exc.to_dict() if hasattr(exc, 'to_dict') else vars(exc),
            }
        except Exception as e:
            return {"status": 500, "error": str(e)}

    # --- Lineage Thread ---

    def get_lineage_thread(company_id: str, correlation_id: str,
                           authorization: str) -> Dict[str, Any]:
        """GET /api/v1/governance/{company_id}/lineage/{correlation_id}"""
        err = _require_auth(auth, authorization, company_id, "view_lineage")
        if err:
            return err
        if not lineage_tracker:
            return {"status": 503, "error": "Lineage tracker not available"}
        try:
            thread = lineage_tracker.get_full_thread(correlation_id)
            return {"status": 200, "company_id": company_id, "lineage_thread": thread}
        except Exception as e:
            logger.error(f"Lineage thread query failed: {e}")
            return {"status": 500, "error": str(e)}

    # --- Model Registry ---

    def get_model_registry_status(company_id: str, authorization: str) -> Dict[str, Any]:
        """GET /api/v1/governance/{company_id}/models"""
        err = _require_auth(auth, authorization, company_id, "view_models")
        if err:
            return err
        if not model_registry:
            return {"status": 503, "error": "Model registry not available"}
        try:
            stats = model_registry.stats()
            return {"status": 200, "company_id": company_id, "model_registry": stats}
        except Exception as e:
            return {"status": 500, "error": str(e)}

    def get_model_versions(company_id: str, model_name: str,
                           authorization: str) -> Dict[str, Any]:
        """GET /api/v1/governance/{company_id}/models/{model_name}/versions"""
        err = _require_auth(auth, authorization, company_id, "view_models")
        if err:
            return err
        if not model_registry:
            return {"status": 503, "error": "Model registry not available"}
        try:
            versions = model_registry.get_all_versions(model_name)
            return {
                "status": 200,
                "model_name": model_name,
                "versions": [v.to_dict() if hasattr(v, 'to_dict') else vars(v) for v in versions],
            }
        except Exception as e:
            return {"status": 500, "error": str(e)}

    # --- Data Quality Gate History ---

    def get_quality_history(company_id: str, authorization: str,
                            dataset_name: Optional[str] = None) -> Dict[str, Any]:
        """GET /api/v1/governance/{company_id}/quality"""
        err = _require_auth(auth, authorization, company_id, "view_quality")
        if err:
            return err
        if not dq_engine:
            return {"status": 503, "error": "Data quality engine not available"}
        try:
            stats = dq_engine.stats()
            return {"status": 200, "company_id": company_id, "data_quality": stats}
        except Exception as e:
            return {"status": 500, "error": str(e)}

    # --- Benchmark Comparisons ---

    def get_benchmark_status(company_id: str, authorization: str) -> Dict[str, Any]:
        """GET /api/v1/governance/{company_id}/benchmarks"""
        err = _require_auth(auth, authorization, company_id, "view_benchmarks")
        if err:
            return err
        if not benchmark_engine:
            return {"status": 503, "error": "Benchmark engine not available"}
        try:
            stats = benchmark_engine.stats()
            return {"status": 200, "company_id": company_id, "benchmarks": stats}
        except Exception as e:
            return {"status": 500, "error": str(e)}

    # --- Agent Health ---

    def get_agent_health(company_id: str, authorization: str) -> Dict[str, Any]:
        """GET /api/v1/governance/{company_id}/agents/health"""
        err = _require_auth(auth, authorization, company_id, "view_agent_health")
        if err:
            return err
        if not health_monitor:
            return {"status": 503, "error": "Agent health monitor not available"}
        try:
            stats = health_monitor.stats()
            return {"status": 200, "company_id": company_id, "agent_health": stats}
        except Exception as e:
            return {"status": 500, "error": str(e)}

    # --- Governance Overview ---

    def get_governance_overview(company_id: str, authorization: str) -> Dict[str, Any]:
        """GET /api/v1/governance/{company_id}/overview"""
        err = _require_auth(auth, authorization, company_id, "view_governance")
        if err:
            return err

        overview: Dict[str, Any] = {
            "company_id": company_id,
            "modules": {},
            "ts": datetime.utcnow().isoformat(),
        }

        for name, module, stat_fn in [
            ("security", security_registry, "generate_compliance_report"),
            ("sla", sla_tracker, "summary"),
            ("exceptions", exception_manager, "pattern_analysis"),
            ("models", model_registry, "stats"),
            ("data_quality", dq_engine, "stats"),
            ("benchmarks", benchmark_engine, "stats"),
            ("agent_health", health_monitor, "stats"),
        ]:
            if module:
                try:
                    fn = getattr(module, stat_fn, None)
                    if fn:
                        overview["modules"][name] = fn()
                except Exception as e:
                    overview["modules"][name] = {"error": str(e)}

        return {"status": 200, **overview}

    # --- Route registry ---

    return {
        "routes": {
            "GET /api/v1/governance/{company_id}/compliance": get_compliance_report,
            "GET /api/v1/governance/{company_id}/risks/heatmap": get_risk_heatmap,
            "GET /api/v1/governance/{company_id}/sla/dashboard": get_sla_dashboard,
            "GET /api/v1/governance/{company_id}/exceptions": get_exception_board,
            "GET /api/v1/governance/{company_id}/exceptions/{exception_id}": get_exception_detail,
            "GET /api/v1/governance/{company_id}/lineage/{correlation_id}": get_lineage_thread,
            "GET /api/v1/governance/{company_id}/models": get_model_registry_status,
            "GET /api/v1/governance/{company_id}/models/{model_name}/versions": get_model_versions,
            "GET /api/v1/governance/{company_id}/quality": get_quality_history,
            "GET /api/v1/governance/{company_id}/benchmarks": get_benchmark_status,
            "GET /api/v1/governance/{company_id}/agents/health": get_agent_health,
            "GET /api/v1/governance/{company_id}/overview": get_governance_overview,
        },
    }


def _build_risk_heatmap(risks: list) -> Dict[str, Any]:
    """Build a risk heat map from risk entries (likelihood × impact grid)."""
    grid: Dict[str, Dict[str, list]] = {}
    likelihood_levels = ["very_low", "low", "medium", "high", "very_high"]
    impact_levels = ["negligible", "minor", "moderate", "significant", "severe"]

    for level in likelihood_levels:
        grid[level] = {imp: [] for imp in impact_levels}

    for risk in risks:
        lik = getattr(risk, "likelihood", "medium")
        imp = getattr(risk, "impact", "moderate")
        rid = getattr(risk, "risk_id", "unknown")
        title = getattr(risk, "title", "")
        if lik in grid and imp in grid.get(lik, {}):
            grid[lik][imp].append({"risk_id": rid, "title": title})

    total = len(risks)
    high_risks = sum(
        1 for r in risks
        if getattr(r, "likelihood", "") in ("high", "very_high")
        and getattr(r, "impact", "") in ("significant", "severe")
    )

    return {
        "grid": grid,
        "total_risks": total,
        "high_risks": high_risks,
        "risk_score": round(high_risks / total, 2) if total > 0 else 0.0,
    }
