"""
Orchestration Visibility API Routes

Exposes the multi-agent decision pipeline for the Orchestration Visibility UI:
- /api/v1/orchestration/status — agent status and metrics
- /api/v1/orchestration/history — recent orchestration results with votes
- /api/v1/orchestration/{asset_id}/latest — latest result for an asset
- /api/v1/orchestration/ingest/status — streaming ingest + ETL status
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

orchestration_router = APIRouter()


def _get_orchestrator(site_id: str = "default"):
    """Get the orchestrator instance for a site."""
    try:
        from . import get_orchestrator
        return get_orchestrator(site_id)
    except Exception as e:
        logger.debug("Orchestrator unavailable: %s", e)
        return None


@orchestration_router.get("/status")
async def get_orchestration_status(
    site_id: str = Query(default="default"),
):
    """Get agent status and orchestrator metrics."""
    orch = _get_orchestrator(site_id)
    if not orch:
        return {
            "available": False,
            "site_id": site_id,
            "agents": {},
            "metrics": {},
            "config": {},
        }

    return {
        "available": True,
        "site_id": site_id,
        "agents": orch.get_agent_status(),
        "metrics": orch.get_orchestrator_metrics(),
        "config": {
            "consensus_threshold": orch.config.consensus_threshold,
            "alert_confidence_threshold": orch.config.alert_confidence_threshold,
            "dispatch_confidence_threshold": orch.config.dispatch_confidence_threshold,
            "max_alerts_per_day": orch.config.max_alerts_per_day,
            "max_dispatches_per_week": orch.config.max_dispatches_per_week,
            "role_weights": {k.value: v for k, v in orch.config.role_weights.items()},
        },
    }


@orchestration_router.get("/history")
async def get_orchestration_history(
    site_id: str = Query(default="default"),
    limit: int = Query(default=50, le=200),
    alerts_only: bool = Query(default=False),
):
    """Get recent orchestration results with full decision trail.

    Returns PdM agent decision history when available, otherwise falls
    back to KPI pipeline run history so the UI always has data to show.
    """
    orch = _get_orchestrator(site_id)

    # ── PdM agent decision history ──
    if orch and orch.result_history:
        results = list(reversed(orch.result_history[-limit:]))
        if alerts_only:
            results = [r for r in results if r.should_alert]

        serialized = []
        for r in results:
            entry = r.to_dict()
            votes = []
            if r.decision:
                for v in r.decision.votes:
                    votes.append({
                        "agent_id": v.agent_id,
                        "agent_role": v.agent_role.value if hasattr(v.agent_role, "value") else str(v.agent_role),
                        "opinion": v.opinion.value if hasattr(v.opinion, "value") else str(v.opinion),
                        "confidence": v.confidence,
                        "weight": v.weight,
                        "rationale": v.rationale,
                        "evidence": list(v.evidence) if v.evidence else [],
                    })
                entry["collaborative_decision"] = {
                    "final_decision": r.decision.final_decision,
                    "consensus_reached": r.decision.consensus_reached,
                    "aggregate_confidence": r.decision.aggregate_confidence,
                    "votes": votes,
                }
            else:
                entry["collaborative_decision"] = None

            layer_summaries = {}
            for layer_name, layer_results in r.layer_results.items():
                layer_summaries[layer_name] = [
                    {
                        "agent_id": lr.agent_id,
                        "confidence": lr.confidence,
                        "recommendations": lr.recommendations,
                        "concerns": lr.concerns,
                        "result_data": {
                            k: v for k, v in lr.result_data.items()
                            if not isinstance(v, (bytes, memoryview))
                        } if lr.result_data else {},
                    }
                    for lr in layer_results
                ]
            entry["layer_summaries"] = layer_summaries
            entry["data_source"] = "orchestrator_result_history"
            entry["degraded_mode"] = False
            entry["warnings"] = []
            serialized.append(entry)

        return {"results": serialized, "total": len(orch.result_history)}

    # ── Fallback: KPI pipeline run history from DB ──
    return await _get_kpi_pipeline_runs(site_id, limit)


async def _get_kpi_pipeline_runs(site_id: str, limit: int = 50):
    """Retrieve KPI pipeline run history from the database."""
    try:
        from ...persistence.database import get_session
        from ...persistence.kpi_repository import KPIPipelineRepository

        with get_session() as session:
            repo = KPIPipelineRepository(session)
            runs = repo.get_recent_runs(site_id, limit=limit)

            results = []
            for run in runs:
                payload = run.result_payload or {}
                exec_summary = payload.get("executive_summary", {})
                scorecards = payload.get("scorecards", [])

                # Build crew status from scorecards
                crew_statuses = {}
                for sc in scorecards:
                    kpi_name = sc.get("kpi_name", "unknown")
                    crew_statuses[kpi_name] = {
                        "status": "completed" if run.status == "completed" else run.status,
                        "duration_ms": (run.duration_seconds or 0) * 1000 / max(len(scorecards), 1),
                    }

                results.append({
                    "result_id": run.run_id,
                    "run_id": run.run_id,
                    "site_id": run.site_id,
                    "timestamp": (run.started_at or run.created_at or datetime.utcnow()).isoformat(),
                    "status": run.status,
                    "phase": run.phase or "complete",
                    "phase_index": 6 if run.status == "completed" else 3,
                    "total_phases": 7,
                    "duration_seconds": run.duration_seconds,
                    "should_alert": False,
                    "regime": "kpi_pipeline",
                    "asset_id": f"pipeline-{run.run_id[:8]}",
                    "processing_time_ms": (run.duration_seconds or 0) * 1000,
                    "kpi_count": exec_summary.get("kpi_count", len(scorecards)),
                    "total_savings_medium": exec_summary.get("total_savings_medium", 0),
                    "error_message": run.error_message,
                    "crew_statuses": crew_statuses,
                    "collaborative_decision": None,
                    "layer_summaries": {},
                    "data_source": payload.get("data_source", "kpi_pipeline_history"),
                    "degraded_mode": bool(payload.get("degraded_mode", False)),
                    "warnings": payload.get("warnings", []),
                })

            return {"results": results, "total": len(results)}
    except Exception as e:
        logger.warning("KPI pipeline history fetch failed: %s", e)
        return {"results": [], "total": 0}


# ═══════════════════════════════════════════════════════════════════════
# Focused Pipeline Routes
# ═══════════════════════════════════════════════════════════════════════

# In-memory storage for pipeline run results (persisted across requests)
_pipeline_runs: Dict[str, List[Dict[str, Any]]] = {}


@orchestration_router.get("/pipelines")
async def list_pipeline_types():
    """List all available orchestration pipeline types with their KPI crews."""
    try:
        from ...services.kpi.orchestrator import PIPELINE_TYPES
        pipelines = []
        for key, ptype in PIPELINE_TYPES.items():
            pipelines.append({
                "pipeline_type": key,
                "name": ptype["name"],
                "description": ptype["description"],
                "icon": ptype["icon"],
                "color": ptype["color"],
                "goal": ptype["goal"],
                "kpi_count": len(ptype["kpis"]),
                "kpis": ptype["kpis"],
                "phases": ptype["phases"],
                "run_count": len(_pipeline_runs.get(key, [])),
            })
        return {"pipelines": pipelines}
    except Exception as e:
        logger.warning("Pipeline types fetch failed: %s", e)
        return {"pipelines": []}


@orchestration_router.post("/pipelines/{pipeline_type}/run")
async def run_pipeline(
    pipeline_type: str,
    site_id: str = Query(default="default"),
):
    """Execute a focused orchestration pipeline for a specific goal.

    Runs only the KPI crews relevant to the pipeline type and returns
    goal-specific results with recommendations.
    """
    try:
        from ...services.kpi.orchestrator import PIPELINE_TYPES, KPIOrchestrator
        from ...services.kpi.base import KPIConfig

        if pipeline_type not in PIPELINE_TYPES:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail=f"Unknown pipeline type: {pipeline_type}. "
                       f"Available: {list(PIPELINE_TYPES.keys())}",
            )

        # Collect data
        asset_data, alert_data, telemetry_summary, health_data = [], [], {"telemetry_count": 0}, []
        try:
            from ...persistence.database import get_session
            from ...persistence.repositories import (
                AssetRepository, AlertRepository, TelemetryRepository,
            )
            with get_session() as session:
                asset_repo = AssetRepository(session)
                alert_repo = AlertRepository(session)
                telemetry_repo = TelemetryRepository(session)
                asset_data = [a.__dict__ for a in asset_repo.get_all(limit=500)]
                alert_data = [a.__dict__ for a in alert_repo.get_recent(limit=1000)]
                telemetry_summary = telemetry_repo.get_summary() or {"telemetry_count": 0}
                health_data = [
                    {"asset_id": a.asset_id, "health_score": getattr(a, "health_score", 75)}
                    for a in asset_repo.get_all(limit=500)
                ]
        except Exception as e:
            logger.debug("Data collection for pipeline skipped: %s", e)

        config = KPIConfig(site_id=site_id)
        orchestrator = KPIOrchestrator(config)
        result = orchestrator.compute_pipeline(
            pipeline_type=pipeline_type,
            asset_data=asset_data,
            alert_data=alert_data,
            telemetry_summary=telemetry_summary,
            health_data=health_data,
        )

        # Store the run result
        _pipeline_runs.setdefault(pipeline_type, []).append(result)
        # Keep only last 20 runs per type
        if len(_pipeline_runs[pipeline_type]) > 20:
            _pipeline_runs[pipeline_type] = _pipeline_runs[pipeline_type][-20:]

        return result
    except Exception as e:
        logger.error("Pipeline %s run failed: %s", pipeline_type, e, exc_info=True)
        return {
            "pipeline_type": pipeline_type,
            "status": "failed",
            "error_message": str(e),
        }


@orchestration_router.get("/pipelines/{pipeline_type}/history")
async def get_pipeline_history(
    pipeline_type: str,
    limit: int = Query(default=20, le=50),
):
    """Get run history for a specific pipeline type."""
    runs = _pipeline_runs.get(pipeline_type, [])
    return {
        "pipeline_type": pipeline_type,
        "runs": list(reversed(runs[-limit:])),
        "total": len(runs),
    }


@orchestration_router.get("/{asset_id}/latest")
async def get_latest_orchestration(
    asset_id: str,
    site_id: str = Query(default="default"),
):
    """Get the latest orchestration result for a specific asset."""
    orch = _get_orchestrator(site_id)
    if not orch:
        return {"available": False, "asset_id": asset_id, "result": None}

    # Find most recent result for this asset
    for r in reversed(orch.result_history):
        if r.asset_id == asset_id:
            entry = r.to_dict()
            votes = []
            if r.decision:
                for v in r.decision.votes:
                    votes.append({
                        "agent_id": v.agent_id,
                        "agent_role": v.agent_role.value if hasattr(v.agent_role, "value") else str(v.agent_role),
                        "opinion": v.opinion.value if hasattr(v.opinion, "value") else str(v.opinion),
                        "confidence": v.confidence,
                        "weight": v.weight,
                        "rationale": v.rationale,
                    })
                entry["collaborative_decision"] = {
                    "final_decision": r.decision.final_decision,
                    "consensus_reached": r.decision.consensus_reached,
                    "aggregate_confidence": r.decision.aggregate_confidence,
                    "votes": votes,
                }
            return {"available": True, "asset_id": asset_id, "result": entry}

    return {"available": True, "asset_id": asset_id, "result": None}


@orchestration_router.get("/ingest/status")
async def get_ingest_status():
    """Get streaming ingest and ETL pipeline status."""
    ingest_status = {"available": False}
    etl_status = {"available": False}

    try:
        from ...integration.streaming_ingest import StreamingIngestService
        # If there's a running service we'd get stats; provide structure
        ingest_status = {
            "available": True,
            "protocols": ["mqtt", "bacnet"],
            "stats": {"readings_received": 0, "readings_processed": 0},
        }
    except Exception:
        pass

    try:
        from ...integration.etl_pipeline import ETLPipeline
        etl_status = {
            "available": True,
            "status": "idle",
            "stats": {"total_runs": 0, "total_records": 0},
            "history": [],
        }
    except Exception:
        pass

    return {
        "streaming_ingest": ingest_status,
        "etl_pipeline": etl_status,
    }
