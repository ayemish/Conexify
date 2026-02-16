"""
KPI Dashboard, Fleet Overview, and Data Upload API Routes

Provides real data-backed endpoints that replace the frontend mock data:
- /api/v1/kpi/{site_id}/dashboard — full KPI dashboard with 14 scorecards
- /api/v1/fleet/assets — fleet asset list with health data
- /api/v1/fleet/metrics — aggregated fleet metrics
- /api/v1/upload/csv — CSV telemetry upload
"""

import csv
import io
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════════


class KPIDashboardResponse(BaseModel):
    site_id: str
    computed_at: datetime
    executive_summary: Dict[str, Any]
    scorecards: List[Dict[str, Any]]
    scenario_comparison: List[Dict[str, Any]]
    decision_advisory: Dict[str, Any]
    location_ranking: List[Dict[str, Any]]
    roi: Dict[str, Any]
    governance: Dict[str, Any]
    budget: Optional[Dict[str, Any]] = None


class FleetAssetResponse(BaseModel):
    asset_id: str
    site_id: str = ""
    asset_type: str = "hvac_rtu"
    manufacturer: str = ""
    model: str = ""
    status: str = "normal"
    regime: str = "unknown"
    estate: Optional[str] = None
    location: Optional[str] = None
    hours_monitored: float = 0
    health_score: float = 100.0
    rul_hours: float = 9999.0
    sensor_trust: float = 1.0
    health: Dict[str, Any] = Field(default_factory=dict)
    rul: Dict[str, Any] = Field(default_factory=dict)
    primary_fault: Optional[str] = None
    confidence: Optional[float] = None
    false_alarm_prob: Optional[float] = None
    recommended_action: Optional[str] = None
    sensor_health: str = ""
    active_alert: Optional[Dict[str, Any]] = None


class FleetAssetsListResponse(BaseModel):
    assets: List[FleetAssetResponse]
    total: int = 0
    offset: int = 0
    limit: int = 50


class FleetMetricsResponse(BaseModel):
    avg_rul_hours: float = 0
    degrading_count: int = 0
    open_incidents: int = 0
    total_assets: int = 0
    avg_health_score: float = 100.0
    critical_count: int = 0


class UploadResponse(BaseModel):
    status: str
    records_processed: int = 0
    records_failed: int = 0
    asset_ids: List[str] = Field(default_factory=list)
    message: str = ""


class CapExPlanResponse(BaseModel):
    site_id: str
    computed_at: datetime
    budget: float
    summary: Dict[str, Any]
    optimized_plan: Dict[str, Any]
    sensitivity: List[Dict[str, Any]]
    next_best_assets: List[Dict[str, Any]]


class KPIApprovalRequest(BaseModel):
    kpi_name: str
    action: str  # approve, reject, pending
    reviewer: str = ""
    notes: str = ""


class KPIApprovalResponse(BaseModel):
    kpi_name: str
    previous_status: str
    new_status: str
    reviewer: str
    notes: str
    updated_at: datetime


class MaintenanceScenarioRequest(BaseModel):
    asset_id: str
    scenario_type: str = "defer_maintenance"  # defer_maintenance, replace_vs_repair, run_to_failure
    defer_days: int = 30
    message: str = ""


class MaintenanceScenarioResponse(BaseModel):
    scenario_id: str
    asset_id: str
    scenario_type: str
    analyses: List[Dict[str, Any]]
    recommendation: str
    created_at: datetime


# ═══════════════════════════════════════════════════════════════════════
# Data Collection Helpers
# ═══════════════════════════════════════════════════════════════════════


def _collect_data_from_db(site_id: str) -> tuple:
    """Collect asset, alert, telemetry, and health data from persistence."""
    asset_data = []
    alert_data = []
    telemetry_summary = {"telemetry_count": 0}
    health_data = []

    try:
        from ...persistence.database import get_session
        from ...persistence.repositories import (
            AssetRepository, AlertRepository, TelemetryRepository,
        )

        with get_session() as session:
            asset_repo = AssetRepository(session)
            alert_repo = AlertRepository(session)
            telemetry_repo = TelemetryRepository(session)

            # Assets — "default" means all sites (catch-all for demo/single-tenant)
            if site_id == "default":
                from ...persistence.models import AssetModel
                assets = session.query(AssetModel).filter(AssetModel.is_active == True).all()
            else:
                assets = asset_repo.get_by_site(site_id)
            for a in assets:
                asset_data.append({
                    "asset_id": a.asset_id,
                    "site_id": a.site_id,
                    "asset_type": a.asset_type or "hvac_rtu",
                    "manufacturer": a.manufacturer or "",
                    "model_number": a.model_number or "",
                    "is_active": a.is_active,
                    "install_date": a.install_date,
                })

            # Alerts — single batch query instead of N per-asset queries
            now = datetime.now(timezone.utc)
            from ...persistence.models import AlertModel
            asset_ids = [a.asset_id for a in assets]
            if asset_ids:
                active_alerts = session.query(AlertModel).filter(
                    AlertModel.asset_id.in_(asset_ids),
                    AlertModel.status == "active",
                ).all()
            else:
                active_alerts = []
            for al in active_alerts:
                alert_data.append({
                    "alert_id": al.alert_id,
                    "asset_id": al.asset_id,
                    "alert_type": al.alert_type,
                    "severity": al.severity,
                    "primary_fault": al.primary_fault,
                    "confidence": al.confidence,
                    "false_alarm_probability": al.false_alarm_probability,
                    "feedback_outcome": al.feedback_outcome,
                    "status": al.status,
                    "created_at": al.created_at,
                })

            # Telemetry summary — sample up to 50 assets (scaled from fleet)
            total_count = 0
            total_power = 0.0
            total_hours = 0.0
            power_readings = 0
            sample_size = min(len(assets), 50)
            for a in assets[:sample_size]:
                latest = telemetry_repo.get_latest(a.asset_id, n=100)
                total_count += len(latest)
                for t in latest:
                    if t.compressor_power and t.compressor_power > 0:
                        total_power += t.compressor_power
                        power_readings += 1
            # Scale sampled counts to full fleet
            if sample_size > 0 and sample_size < len(assets):
                scale_factor = len(assets) / sample_size
                total_count = int(total_count * scale_factor)

            telemetry_summary = {
                "telemetry_count": total_count,
                "avg_compressor_power_kw": (
                    total_power / power_readings if power_readings > 0 else 0
                ),
                "total_compressor_hours": total_count * 5 / 60,  # assume 5-min intervals
            }

            # Additional KPI-linked datasets (uploaded CSVs)
            try:
                from ...persistence.models import (
                    WorkOrderModel,
                    EnergyDataModel,
                    MaintenanceHistoryModel,
                    RefrigerantRecordModel,
                )

                annual_start = now - timedelta(days=365)

                wo_query = session.query(WorkOrderModel)
                if site_id != "default":
                    wo_query = wo_query.filter(WorkOrderModel.site_id == site_id)
                work_orders = wo_query.filter(WorkOrderModel.opened_at >= annual_start).all()
                reactive_wos = [
                    wo for wo in work_orders
                    if (wo.wo_type or "").lower() in ("reactive", "emergency")
                ]
                wo_total_cost = sum(float(wo.cost or 0.0) for wo in work_orders)
                telemetry_summary.update({
                    "work_order_count_annual": len(work_orders),
                    "reactive_work_order_count_annual": len(reactive_wos),
                    "work_order_total_cost_annual": round(wo_total_cost, 2),
                    "work_order_avg_cost": round(wo_total_cost / max(len(work_orders), 1), 2),
                })

                energy_query = session.query(EnergyDataModel)
                if site_id != "default":
                    energy_query = energy_query.filter(EnergyDataModel.site_id == site_id)
                energy_rows = energy_query.filter(EnergyDataModel.period_start >= annual_start).all()
                annual_kwh = sum(float(r.kwh_consumed or 0.0) for r in energy_rows)
                annual_energy_cost = sum(float(r.cost or 0.0) for r in energy_rows)
                telemetry_summary.update({
                    "energy_kwh_annual": round(annual_kwh, 2),
                    "energy_cost_annual": round(annual_energy_cost, 2),
                    "energy_effective_rate_per_kwh": (
                        round(annual_energy_cost / annual_kwh, 6) if annual_kwh > 0 else None
                    ),
                })

                maint_query = session.query(MaintenanceHistoryModel)
                if site_id != "default":
                    maint_query = maint_query.filter(MaintenanceHistoryModel.site_id == site_id)
                maintenance_rows = maint_query.filter(MaintenanceHistoryModel.service_date >= annual_start).all()
                pm_rows = [
                    r for r in maintenance_rows
                    if (r.service_type or "").lower() in ("pm", "preventive", "inspection")
                ]
                maint_total_cost = sum(float(r.cost or 0.0) for r in maintenance_rows)
                telemetry_summary.update({
                    "maintenance_records_annual": len(maintenance_rows),
                    "pm_records_annual": len(pm_rows),
                    "maintenance_total_cost_annual": round(maint_total_cost, 2),
                })

                refrig_query = session.query(RefrigerantRecordModel)
                if site_id != "default":
                    refrig_query = refrig_query.filter(RefrigerantRecordModel.site_id == site_id)
                refrig_rows = refrig_query.filter(RefrigerantRecordModel.record_date >= annual_start).all()
                lbs_added = sum(float(r.lbs_added or 0.0) for r in refrig_rows)
                leak_events = sum(1 for r in refrig_rows if bool(r.leak_detected))
                leak_rate_values = [
                    float(r.leak_rate_pct) for r in refrig_rows
                    if r.leak_rate_pct is not None
                ]
                telemetry_summary.update({
                    "refrigerant_records_annual": len(refrig_rows),
                    "refrigerant_lbs_added_annual": round(lbs_added, 2),
                    "refrigerant_leak_events_annual": leak_events,
                    "refrigerant_avg_leak_rate_pct": (
                        round(sum(leak_rate_values) / len(leak_rate_values), 3)
                        if leak_rate_values else None
                    ),
                })
            except Exception as dataset_err:
                logger.debug("Additional KPI dataset aggregation skipped: %s", dataset_err)

    except Exception as e:
        logger.warning("Database collection failed, using in-memory data: %s", e)

    return asset_data, alert_data, telemetry_summary, health_data


def _collect_health_data(site_id: str, asset_data: List[Dict]) -> List[Dict[str, Any]]:
    """Collect health index data from in-memory PdM systems + persisted snapshots.

    Priority order:
    1. Live in-memory PdM system state (most current)
    2. Persisted health snapshots in PostgreSQL (survives restarts)
    3. Conservative defaults for unknown assets
    """
    health_data = []
    known_ids = set()

    # ── 1. In-memory PdM systems (live state) ─────────────────────────
    try:
        from . import _pdm_systems
        for a in asset_data:
            aid = a.get("asset_id", "")
            sys = _pdm_systems.get(aid)
            if sys and hasattr(sys, "health_index"):
                hi = sys.health_index
                entry = {
                    "asset_id": aid,
                    "health_score": getattr(hi, "health_score", 100),
                    "health_band": getattr(hi, "health_band", "healthy"),
                    "sensor_trust_score": getattr(hi, "sensor_trust_score", 100),
                    "change_detection_score": getattr(hi, "change_detection_score", 100),
                    "fault_probability_score": getattr(hi, "fault_probability_score", 0),
                    "rul_score": getattr(hi, "rul_score", 100),
                    "degradation_score": getattr(hi, "degradation_score", 0),
                    "rul_hours": getattr(hi, "rul_hours", 9999),
                }
                health_data.append(entry)
                known_ids.add(aid)

                # T2-7: Persist snapshot to DB for cross-restart recovery
                _persist_health_snapshot(aid, site_id, entry)
    except Exception as e:
        logger.debug("Health data collection from memory: %s", e)

    # ── 2. Persisted health snapshots (for assets not in memory) ───────
    if len(known_ids) < len(asset_data):
        missing_ids = [a.get("asset_id", "") for a in asset_data if a.get("asset_id", "") not in known_ids]
        persisted = _load_persisted_health(missing_ids)
        for entry in persisted:
            if entry["asset_id"] not in known_ids:
                health_data.append(entry)
                known_ids.add(entry["asset_id"])

    # ── 3. Conservative defaults for remaining unknown assets ──────────
    for a in asset_data:
        aid = a.get("asset_id", "")
        if aid not in known_ids:
            health_data.append({
                "asset_id": aid,
                "health_score": 50.0,
                "health_band": "unknown",
                "sensor_trust_score": 50.0,
                "change_detection_score": 50.0,
                "fault_probability_score": 0.0,
                "rul_score": 50.0,
                "degradation_score": 0.0,
                "rul_hours": 5000.0,
            })

    return health_data


def _persist_health_snapshot(asset_id: str, site_id: str, entry: Dict[str, Any]):
    """Persist a health snapshot to PostgreSQL for cross-restart recovery."""
    try:
        from ...persistence.database import get_session
        with get_session() as session:
            session.execute(
                _health_snapshot_upsert(),
                {
                    "asset_id": asset_id,
                    "site_id": site_id,
                    "health_score": entry.get("health_score", 50),
                    "health_band": entry.get("health_band", "unknown"),
                    "sensor_trust_score": entry.get("sensor_trust_score", 50),
                    "change_detection_score": entry.get("change_detection_score", 50),
                    "fault_probability_score": entry.get("fault_probability_score", 0),
                    "rul_score": entry.get("rul_score", 50),
                    "degradation_score": entry.get("degradation_score", 0),
                    "rul_hours": entry.get("rul_hours", 5000),
                },
            )
            session.commit()
    except Exception as e:
        logger.debug("Health snapshot persist skipped: %s", e)


def _health_snapshot_upsert():
    """Return a DB-agnostic upsert statement for health snapshots."""
    from sqlalchemy import text
    return text("""
        INSERT INTO health_snapshots
            (asset_id, site_id, health_score, health_band, sensor_trust_score,
             change_detection_score, fault_probability_score, rul_score,
             degradation_score, rul_hours, updated_at)
        VALUES
            (:asset_id, :site_id, :health_score, :health_band, :sensor_trust_score,
             :change_detection_score, :fault_probability_score, :rul_score,
             :degradation_score, :rul_hours, NOW())
        ON CONFLICT (asset_id)
        DO UPDATE SET
            health_score = EXCLUDED.health_score,
            health_band = EXCLUDED.health_band,
            sensor_trust_score = EXCLUDED.sensor_trust_score,
            change_detection_score = EXCLUDED.change_detection_score,
            fault_probability_score = EXCLUDED.fault_probability_score,
            rul_score = EXCLUDED.rul_score,
            degradation_score = EXCLUDED.degradation_score,
            rul_hours = EXCLUDED.rul_hours,
            updated_at = NOW()
    """)


def _load_persisted_health(asset_ids: List[str]) -> List[Dict[str, Any]]:
    """Load persisted health snapshots from PostgreSQL."""
    if not asset_ids:
        return []
    try:
        from ...persistence.database import get_session
        from sqlalchemy import text

        with get_session() as session:
            rows = session.execute(
                text("SELECT * FROM health_snapshots WHERE asset_id = ANY(:ids)"),
                {"ids": asset_ids},
            ).fetchall()

            results = []
            for row in rows:
                results.append({
                    "asset_id": row.asset_id,
                    "health_score": float(row.health_score or 50),
                    "health_band": row.health_band or "unknown",
                    "sensor_trust_score": float(row.sensor_trust_score or 50),
                    "change_detection_score": float(row.change_detection_score or 50),
                    "fault_probability_score": float(row.fault_probability_score or 0),
                    "rul_score": float(row.rul_score or 50),
                    "degradation_score": float(row.degradation_score or 0),
                    "rul_hours": float(row.rul_hours or 5000),
                })
            return results
    except Exception as e:
        logger.debug("Persisted health load failed: %s", e)
        return []


def _normalize_scenario_comparison(raw: Any) -> List[Dict[str, Any]]:
    """Normalize scenario outputs from multiple orchestrator implementations."""
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    if not isinstance(raw, dict):
        return []

    summary_table = raw.get("summary_table")
    if isinstance(summary_table, list):
        return [r for r in summary_table if isinstance(r, dict)]

    scenarios = raw.get("scenarios")
    if isinstance(scenarios, dict):
        rows = []
        for scenario_name, vals in scenarios.items():
            if not isinstance(vals, dict):
                continue
            rows.append({
                "scenario": scenario_name,
                "savings_medium": float(vals.get("total_savings_medium", 0.0) or 0.0),
                "savings_low": float(vals.get("total_savings_low", 0.0) or 0.0),
                "savings_high": float(vals.get("total_savings_high", 0.0) or 0.0),
            })
        return rows
    return []


def _dashboard_from_loweconex(site_id: str, composite: Dict[str, Any]) -> Dict[str, Any]:
    """Map OrchestratorCrew composite output into KPIDashboardResponse shape."""
    kpi_results = composite.get("kpi_results", {}) or {}
    scorecards: List[Dict[str, Any]] = []
    for kpi_name, payload in kpi_results.items():
        if not isinstance(payload, dict):
            continue
        scorecards.append({
            "kpi_name": kpi_name,
            "display_name": payload.get("display_name") or kpi_name.replace("_", " ").title(),
            "category": payload.get("savings_category") or kpi_name,
            "savings_low": float(payload.get("savings_low", 0.0) or 0.0),
            "savings_medium": float(payload.get("savings_medium", 0.0) or 0.0),
            "savings_high": float(payload.get("savings_high", 0.0) or 0.0),
            "confidence": float(payload.get("confidence", 0.0) or 0.0),
            "status": payload.get("status", "pending"),
            "assumptions": payload.get("assumptions", []),
            "supporting_metrics": payload.get("metrics", {}),
            "narrative": payload.get("narrative", ""),
            "gaps": payload.get("gaps", []),
        })
    scorecards.sort(key=lambda r: float(r.get("savings_medium", 0.0) or 0.0), reverse=True)

    cross_asset = composite.get("cross_asset_optimization", {}) or {}
    location_ranking: List[Dict[str, Any]] = []
    for idx, group in enumerate(cross_asset.get("group_marginal_impacts", []) or []):
        if not isinstance(group, dict):
            continue
        location_ranking.append({
            "location_id": f"group_{idx}",
            "address": "",
            "total_savings": float(group.get("total_savings_medium", 0.0) or 0.0),
            "kpi_count": len(group.get("contributing_kpis", []) or []),
            "top_kpi": (group.get("contributing_kpis") or [""])[0],
            "asset_ids": group.get("asset_ids", []),
        })
    location_ranking.sort(key=lambda r: float(r.get("total_savings", 0.0) or 0.0), reverse=True)

    governance = composite.get("governance", {}) or {}
    if composite.get("savings_reconciliation"):
        governance["savings_reconciliation"] = composite.get("savings_reconciliation")
    governance["source_orchestrator"] = "loweconex_orchestrator_crew"

    computed_at = composite.get("completed_ts") or datetime.now(timezone.utc).isoformat()
    return {
        "site_id": site_id,
        "computed_at": computed_at,
        "executive_summary": composite.get("executive_summary", {}) or {},
        "scorecards": scorecards,
        "scenario_comparison": _normalize_scenario_comparison(
            composite.get("scenario_analysis", {})
        ),
        "decision_advisory": composite.get("decision_advisory", {}) or {},
        "location_ranking": location_ranking,
        "roi": composite.get("roi_metrics", {}) or {},
        "governance": governance,
    }


def compute_dashboard_data(
    site_id: str,
    asset_data: Optional[List[Dict[str, Any]]] = None,
    alert_data: Optional[List[Dict[str, Any]]] = None,
    telemetry_summary: Optional[Dict[str, Any]] = None,
    health_data: Optional[List[Dict[str, Any]]] = None,
    implementation_cost: float = 250_000.0,
    required_kpis: Optional[List[str]] = None,
    run_scenarios: bool = True,
    custom_scenario_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute dashboard output using orchestrator crew by default with deterministic fallback."""
    # OrchestratorCrew (CrewAI) path — enabled when loweconex_platform + CrewAI are installed.
    # Set PDM_SKIP_CREW_ENRICHMENT=true to disable.
    import os as _os
    if _os.environ.get("PDM_SKIP_CREW_ENRICHMENT", "").lower() not in ("1", "true", "yes"):
        try:
            from loweconex_platform.config import PlatformConfig
            from loweconex_platform.orchestration.orchestrator_crew import OrchestratorCrew
            from loweconex_platform.digital_twins.store import get_default_store
            from loweconex_platform.event_bus.redis_streams import LoweconexEventBus

            twin_store = get_default_store()
            platform_config = PlatformConfig()
            try:
                event_bus = LoweconexEventBus(agent_id="kpi_dashboard")
            except Exception:
                from shared.event_bus.redis_event_bus import InMemoryEventBus
                event_bus = InMemoryEventBus(agent_id="kpi_dashboard")

            orchestrator = OrchestratorCrew(
                config=platform_config,
                twin_store=twin_store,
                event_bus=event_bus,
            )
            composite = orchestrator.run_full_pipeline(
                company_id=site_id,
                kpi_names=required_kpis,
                run_scenarios=run_scenarios,
                custom_scenario_params=custom_scenario_params,
            )
            return _dashboard_from_loweconex(site_id, composite)
        except Exception as orch_err:
            logger.info("Loweconex orchestrator path unavailable, using deterministic KPI orchestrator: %s", orch_err)
    else:
        logger.info("CrewAI orchestrator disabled — using deterministic KPI orchestrator")

    # Deterministic fallback path
    from ...services.kpi import KPIOrchestrator, KPIConfig

    if asset_data is None or alert_data is None or telemetry_summary is None:
        asset_data, alert_data, telemetry_summary, _ = _collect_data_from_db(site_id)
    if health_data is None:
        health_data = _collect_health_data(site_id, asset_data or [])

    config = KPIConfig.load_from_db(site_id)
    config.total_assets = max(len(asset_data or []), config.total_assets)
    orchestrator = KPIOrchestrator(config)
    result = orchestrator.compute_all(
        asset_data=asset_data or [],
        alert_data=alert_data or [],
        telemetry_summary=telemetry_summary or {"telemetry_count": 0},
        health_data=health_data or [],
        implementation_cost=implementation_cost,
    )
    result_dict = result.to_dict()
    if required_kpis:
        required_set = set(required_kpis)
        filtered_scorecards = [
            s for s in (result_dict.get("scorecards", []) or [])
            if str(s.get("kpi_name", "")) in required_set
        ]
        result_dict["scorecards"] = filtered_scorecards
        if filtered_scorecards:
            total_med = sum(float(s.get("savings_medium", 0.0) or 0.0) for s in filtered_scorecards)
            total_low = sum(float(s.get("savings_low", 0.0) or 0.0) for s in filtered_scorecards)
            total_high = sum(float(s.get("savings_high", 0.0) or 0.0) for s in filtered_scorecards)
            avg_conf = sum(float(s.get("confidence", 0.0) or 0.0) for s in filtered_scorecards) / max(
                len(filtered_scorecards), 1
            )
            approved_count = sum(1 for s in filtered_scorecards if s.get("status") == "approved")
            result_dict["executive_summary"] = {
                **(result_dict.get("executive_summary", {}) or {}),
                "total_savings_medium": round(total_med, 2),
                "total_savings_low": round(total_low, 2),
                "total_savings_high": round(total_high, 2),
                "kpi_count": len(filtered_scorecards),
                "approved_kpis": approved_count,
                "avg_confidence": round(avg_conf, 3),
            }
    if not run_scenarios:
        result_dict["scenario_comparison"] = []
    result_dict.setdefault("governance", {})["source_orchestrator"] = "deterministic_kpi_orchestrator"
    return result_dict


def _enrich_kpis_from_capex(
    site_id: str,
    result_dict: Dict[str, Any],
    asset_data: List[Dict[str, Any]],
    health_data: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """T2-8: Cross-reference CapEx engine outputs into capex/asset KPI scorecards.

    When the CapEx engine is available, replace the theoretical KPI savings
    with actual optimizer-computed NPV and lifecycle cost savings.
    """
    try:
        from loweconex_platform.capex.engine import CapExEngine
    except ImportError:
        return result_dict

    try:
        health_map = {h["asset_id"]: h for h in health_data}
        enriched_assets = []
        h_map_engine: Dict[str, Dict] = {}
        replacement_options: Dict[str, list] = {}

        for a in asset_data:
            aid = a.get("asset_id", "")
            h = health_map.get(aid, {})
            install = a.get("install_date")
            age = 5
            if install:
                try:
                    if isinstance(install, str):
                        install = datetime.fromisoformat(install)
                    age = max(1, (datetime.now(timezone.utc) - install).days // 365)
                except Exception:
                    pass

            enriched_assets.append({**a, "age_years": age, "asset_type": a.get("asset_type", "RTU").upper()})
            hs = h.get("health_score", 80)
            h_map_engine[aid] = {
                "health_score": hs,
                "degradation_score": h.get("degradation_score", 10),
                "rul_hours": h.get("rul_hours", 5000),
                "annual_maintenance_cost": 2000 + (100 - hs) * 30,
                "kwh_day": 80 + (100 - hs) * 2,
            }
            cost_map = {"RTU": 18000, "AHU": 25000, "HVAC_RTU": 18000, "CHILLER": 45000}
            rc = cost_map.get(a.get("asset_type", "RTU").upper(), 15000)
            replacement_options[aid] = [{"option_id": f"opt-{aid}", "capex_installed_cost": rc,
                                         "efficiency_delta": 0.18, "maintenance_delta_per_year": -800,
                                         "expected_life_years": 15}]

        engine = CapExEngine()
        capex_result = engine.analyze(
            store={"name": f"Site {site_id}", "store_id": site_id},
            assets=enriched_assets,
            replacement_options=replacement_options,
            economic_assumption={"discount_rate": 0.08, "analysis_horizon_years": 10},
            utility_rate={"energy_rate": 0.12, "escalation_rate": 0.03},
            budget=500_000,
            health_data=h_map_engine,
        )

        capex_summary = getattr(capex_result, "summary", {}) or {}
        total_npv = float(capex_summary.get("total_npv", 0) or 0)
        assets_selected = int(capex_summary.get("assets_selected", 0) or 0)

        for sc in result_dict.get("scorecards", []):
            kn = sc.get("kpi_name", "")
            if kn == "capex_lifecycle_optimization" and total_npv > 0:
                sc["supporting_metrics"] = sc.get("supporting_metrics", {})
                sc["supporting_metrics"]["capex_engine_npv"] = round(total_npv, 2)
                sc["supporting_metrics"]["capex_assets_selected"] = assets_selected
                sc["supporting_metrics"]["capex_engine_linked"] = True
            elif kn == "asset_failure_prediction" and assets_selected > 0:
                sc["supporting_metrics"] = sc.get("supporting_metrics", {})
                sc["supporting_metrics"]["capex_high_risk_assets"] = assets_selected
                sc["supporting_metrics"]["capex_engine_linked"] = True

        logger.info("CapEx engine enriched KPI dashboard: NPV=%s, assets=%s", total_npv, assets_selected)
    except Exception as e:
        logger.debug("CapEx KPI enrichment skipped: %s", e)

    return result_dict


# ═══════════════════════════════════════════════════════════════════════
# KPI Routes
# ═══════════════════════════════════════════════════════════════════════

kpi_router = APIRouter()


@kpi_router.get("/{site_id}/dashboard", response_model=KPIDashboardResponse)
async def get_kpi_dashboard(site_id: str, force_recompute: bool = False):
    """Compute the full KPI dashboard from real data for a site.

    Uses Redis-backed cache when available. Set force_recompute=true to bypass cache.
    Results are persisted to PostgreSQL for audit trail.
    """
    from ...persistence.kpi_repository import get_dashboard_cache

    # Check cache first
    cache = get_dashboard_cache()
    if not force_recompute:
        cached = cache.get(site_id)
        if cached:
            try:
                from ...services.advisor import get_shared_advisor
                get_shared_advisor()._index_kpi_dashboard(site_id=site_id, dashboard=cached)
            except Exception as rag_sync_err:
                logger.debug("Cached dashboard RAG sync skipped: %s", rag_sync_err)
            return KPIDashboardResponse(**cached)

    # Compute from real data
    asset_data, alert_data, telemetry_summary, _ = _collect_data_from_db(site_id)
    health_data = _collect_health_data(site_id, asset_data)

    # Load budget data if available to use as implementation_cost
    impl_cost = 250_000.0  # default
    budget_data = None
    try:
        from .budget_routes import _budget_path
        import json as _json
        bp = _budget_path(site_id)
        if not bp.exists() and site_id != "default":
            bp = _budget_path("default")
        if bp.exists():
            budget_data = _json.loads(bp.read_text())
            capex = float(budget_data.get("overall_capex", 0) or 0)
            if capex > 0:
                impl_cost = capex
                logger.info("Using budget CapEx ($%,.0f) as implementation cost for ROI", capex)
    except Exception as budget_err:
        logger.debug("Budget load skipped: %s", budget_err)

    result_dict = compute_dashboard_data(
        site_id=site_id,
        asset_data=asset_data,
        alert_data=alert_data,
        telemetry_summary=telemetry_summary,
        health_data=health_data,
        run_scenarios=True,
        implementation_cost=impl_cost,
    )

    # Attach budget context to the result so frontend can display it
    if budget_data:
        result_dict["budget"] = budget_data

    # T2-8: Enrich CapEx-related KPIs with actual CapEx engine outputs
    result_dict = _enrich_kpis_from_capex(site_id, result_dict, asset_data, health_data)

    # Keep conversational RAG synchronized with the latest KPI dashboard.
    try:
        from ...services.advisor import get_shared_advisor
        get_shared_advisor()._index_kpi_dashboard(site_id=site_id, dashboard=result_dict)
    except Exception as rag_sync_err:
        logger.debug("KPI dashboard RAG sync skipped: %s", rag_sync_err)

    # Cache the result
    cache.set(site_id, result_dict)

    # Persist to PostgreSQL
    try:
        from ...persistence.database import get_session
        from ...persistence.kpi_repository import KPIPipelineRepository, KPIResultRepository

        with get_session() as session:
            pipeline_repo = KPIPipelineRepository(session)
            result_repo = KPIResultRepository(session)

            run = pipeline_repo.create_run(site_id)
            pipeline_repo.complete_run(run.run_id, result_dict)
            result_repo.store_results(run.run_id, site_id, result_dict.get("scorecards", []))
            session.commit()
    except Exception as e:
        logger.warning("KPI result persistence failed: %s", e)

    return KPIDashboardResponse(**result_dict)


# ═══════════════════════════════════════════════════════════════════════
# KPI History Routes
# ═══════════════════════════════════════════════════════════════════════


class KPIRunSummary(BaseModel):
    run_id: str
    site_id: str
    status: str
    phase: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    kpi_count: int = 0
    total_savings_medium: float = 0.0
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None


class KPIHistoryResponse(BaseModel):
    site_id: str
    runs: List[KPIRunSummary]
    total: int = 0


class KPIRunDetailResponse(BaseModel):
    run_id: str
    site_id: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    scorecards: List[Dict[str, Any]] = Field(default_factory=list)
    result_payload: Optional[Dict[str, Any]] = None


@kpi_router.get("/{site_id}/history", response_model=KPIHistoryResponse)
async def get_kpi_history(
    site_id: str,
    limit: int = Query(default=20, ge=1, le=100, description="Max number of runs to return"),
):
    """Get historical KPI pipeline runs for a site.

    Returns a list of past KPI computation runs with status, timing,
    and summary savings. Use the run_id to fetch full details via
    GET /{site_id}/history/{run_id}.
    """
    try:
        from ...persistence.database import get_session
        from ...persistence.kpi_repository import KPIPipelineRepository

        with get_session() as session:
            repo = KPIPipelineRepository(session)
            runs = repo.get_recent_runs(site_id, limit=limit)

            summaries = []
            for run in runs:
                payload = run.result_payload or {}
                exec_summary = payload.get("executive_summary", {})
                summaries.append(KPIRunSummary(
                    run_id=run.run_id,
                    site_id=run.site_id,
                    status=run.status,
                    phase=run.phase or "",
                    started_at=run.started_at,
                    completed_at=run.completed_at,
                    duration_seconds=run.duration_seconds,
                    kpi_count=exec_summary.get("kpi_count", 0),
                    total_savings_medium=exec_summary.get("total_savings_medium", 0),
                    error_message=run.error_message,
                    created_at=run.created_at,
                ))

            return KPIHistoryResponse(
                site_id=site_id,
                runs=summaries,
                total=len(summaries),
            )
    except Exception as e:
        logger.warning("KPI history fetch failed: %s", e)
        return KPIHistoryResponse(site_id=site_id, runs=[], total=0)


@kpi_router.get("/{site_id}/history/{run_id}", response_model=KPIRunDetailResponse)
async def get_kpi_run_detail(site_id: str, run_id: str):
    """Get full details for a specific KPI pipeline run, including scorecards."""
    try:
        from ...persistence.database import get_session
        from ...persistence.kpi_repository import KPIPipelineRepository, KPIResultRepository

        with get_session() as session:
            pipeline_repo = KPIPipelineRepository(session)
            result_repo = KPIResultRepository(session)

            run = pipeline_repo.get_run(run_id)
            if not run or run.site_id != site_id:
                raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found for site '{site_id}'")

            results = result_repo.get_by_run(run_id)
            scorecards = [
                {
                    "kpi_name": r.kpi_name,
                    "display_name": r.display_name,
                    "category": r.category,
                    "savings_low": r.savings_low,
                    "savings_medium": r.savings_medium,
                    "savings_high": r.savings_high,
                    "confidence": r.confidence,
                    "status": r.status,
                    "narrative": r.narrative,
                    "data_points_used": r.data_points_used,
                    "data_coverage_pct": r.data_coverage_pct,
                }
                for r in results
            ]

            return KPIRunDetailResponse(
                run_id=run.run_id,
                site_id=run.site_id,
                status=run.status,
                started_at=run.started_at,
                completed_at=run.completed_at,
                duration_seconds=run.duration_seconds,
                scorecards=scorecards,
                result_payload=run.result_payload,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("KPI run detail fetch failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════
# KPI Approval Routes
# ═══════════════════════════════════════════════════════════════════════

# In-memory status overrides: {(site_id, kpi_name): {status, reviewer, notes, updated_at}}
_kpi_status_overrides: Dict[tuple, Dict[str, Any]] = {}
_kpi_overrides_hydrated: bool = False


def _hydrate_kpi_overrides():
    """Load persisted KPI approval overrides from the database on first access."""
    global _kpi_overrides_hydrated
    if _kpi_overrides_hydrated:
        return
    _kpi_overrides_hydrated = True
    try:
        from ...persistence.database import get_session
        from ...persistence.models import KPIResultModel

        with get_session() as session:
            rows = session.query(KPIResultModel).filter(
                KPIResultModel.status.in_(["approved", "rejected"])
            ).all()
            for row in rows:
                key = (row.site_id, row.kpi_name)
                if key not in _kpi_status_overrides:
                    _kpi_status_overrides[key] = {
                        "status": row.status,
                        "reviewer": "",
                        "notes": "",
                        "updated_at": row.computed_at,
                    }
        logger.info("Hydrated %d KPI approval overrides from DB", len(_kpi_status_overrides))
    except Exception as e:
        logger.debug("KPI approval hydration skipped: %s", e)


@kpi_router.post("/{site_id}/approve", response_model=KPIApprovalResponse)
async def approve_kpi(site_id: str, req: KPIApprovalRequest):
    """Manually approve, reject, or reset a KPI scorecard.

    This overrides the auto-computed confidence-based status.
    - **approve**: Include this KPI in ROI calculations and reports.
    - **reject**: Exclude this KPI — savings estimate is not credible.
    - **pending**: Reset to auto-computed status.
    """
    if req.action not in ("approve", "reject", "pending"):
        raise HTTPException(status_code=400, detail="action must be approve, reject, or pending")

    _hydrate_kpi_overrides()
    key = (site_id, req.kpi_name)
    previous = _kpi_status_overrides.get(key, {}).get("status", "auto")
    now = datetime.now(timezone.utc)

    if req.action == "pending":
        _kpi_status_overrides.pop(key, None)
    else:
        _kpi_status_overrides[key] = {
            "status": req.action + "d",  # approved / rejected
            "reviewer": req.reviewer,
            "notes": req.notes,
            "updated_at": now,
        }

    # Persist to DB if available
    try:
        from ...persistence.database import get_session
        from ...persistence.models import KPIResultModel

        with get_session() as session:
            rows = session.query(KPIResultModel).filter(
                KPIResultModel.site_id == site_id,
                KPIResultModel.kpi_name == req.kpi_name,
            ).order_by(KPIResultModel.computed_at.desc()).limit(1).all()
            for row in rows:
                row.status = req.action + "d" if req.action != "pending" else "pending"
            session.commit()
    except Exception as e:
        logger.debug("KPI approval DB persist skipped: %s", e)

    new_status = req.action + "d" if req.action != "pending" else "pending"
    return KPIApprovalResponse(
        kpi_name=req.kpi_name,
        previous_status=previous,
        new_status=new_status,
        reviewer=req.reviewer,
        notes=req.notes,
        updated_at=now,
    )


@kpi_router.get("/{site_id}/approvals")
async def get_kpi_approvals(site_id: str):
    """Get all manual status overrides for a site."""
    _hydrate_kpi_overrides()
    overrides = {}
    for (sid, kpi_name), info in _kpi_status_overrides.items():
        if sid == site_id:
            overrides[kpi_name] = info
    return {"site_id": site_id, "overrides": overrides}


# ═══════════════════════════════════════════════════════════════════════
# CapEx Planning Routes
# ═══════════════════════════════════════════════════════════════════════


@kpi_router.get("/{site_id}/capex", response_model=CapExPlanResponse)
async def get_capex_plan(
    site_id: str,
    budget: float = Query(default=500_000, description="Total CapEx budget"),
    objective: str = Query(default="max_expected_npv", description="Optimization objective"),
):
    """Run full CapEx lifecycle analysis for a site.

    Uses the CapEx Generator engine: Weibull survival modeling,
    ASTM E917 LCC with Monte Carlo NPV, and knapsack budget optimization.
    """
    try:
        from loweconex_platform.capex.engine import CapExEngine
    except ImportError:
        raise HTTPException(status_code=501, detail="CapEx engine module not available")

    # Collect data
    asset_data, alert_data, telemetry_summary, _ = _collect_data_from_db(site_id)
    health_data = _collect_health_data(site_id, asset_data)

    if not asset_data:
        raise HTTPException(status_code=404, detail="No assets found for this site")

    # Enrich assets with age and economics
    health_map: Dict[str, Dict] = {}
    fault_map: Dict[str, Dict] = {}
    waste_map: Dict[str, Dict] = {}
    peer_map: Dict[str, int] = {}
    enriched_assets = []

    for a in asset_data:
        aid = a.get("asset_id", "")
        h = next((hd for hd in health_data if hd.get("asset_id") == aid), {})

        # Compute age from install_date
        install = a.get("install_date")
        age = 5
        if install:
            try:
                from datetime import datetime as _dt
                if isinstance(install, str):
                    install = _dt.fromisoformat(install)
                age = max(1, (datetime.now(timezone.utc) - install).days // 365)
            except Exception:
                pass

        enriched = {
            **a,
            "age_years": age,
            "asset_type": a.get("asset_type", "RTU").upper().replace(" ", "_"),
        }
        enriched_assets.append(enriched)

        health_score = h.get("health_score", 80)
        health_map[aid] = {
            "health_score": health_score,
            "degradation_score": h.get("degradation_score", 10),
            "rul_hours": h.get("rul_hours", 5000),
            "annual_maintenance_cost": 2000 + (100 - health_score) * 30,
            "kwh_day": 80 + (100 - health_score) * 2,
            "maintenance_trend": max(0, age - 10) / 20,
        }
        fault_map[aid] = {
            "fault_burden_score": h.get("fault_probability_score", 0),
        }
        waste_map[aid] = {
            "waste_percentile": min(100, max(0, 100 - health_score + 20)),
        }
        peer_map[aid] = max(5, min(95, health_score - 10))

    # Build replacement options
    replacement_options: Dict[str, list] = {}
    for a in enriched_assets:
        aid = a.get("asset_id", "")
        atype = a.get("asset_type", "RTU")
        # Estimate replacement cost by type
        cost_map = {
            "RTU": 18_000, "AHU": 25_000, "COMPRESSOR_RACK": 30_000,
            "CONDENSING_UNIT": 15_000, "WALK_IN_COOLER": 12_000,
            "WALK_IN_FREEZER": 14_000, "REACH_IN_CASE": 8_000,
            "CHILLER": 45_000, "HVAC_RTU": 18_000,
            "HVAC_SPLIT_SYSTEM": 12_000, "HVAC_VRF": 35_000,
            "HEAT_PUMP": 14_000, "DISPLAY_CASE": 10_000,
            "COOLER_COMPRESSOR": 8_000,
        }
        replace_cost = cost_map.get(atype, 15_000)
        replacement_options[aid] = [{
            "option_id": f"opt-std-{aid}",
            "option_name": f"Standard {atype} replacement",
            "capex_installed_cost": replace_cost,
            "efficiency_delta": 0.18,
            "maintenance_delta_per_year": -800,
            "expected_life_years": 15,
            "warranty_years": 1,
        }]

    economic_assumption = {
        "discount_rate": 0.08,
        "analysis_horizon_years": 10,
        "failure_event_cost_by_type": {
            "RTU": 15_000, "AHU": 20_000, "COMPRESSOR_RACK": 25_000,
            "CONDENSING_UNIT": 12_000, "WALK_IN_COOLER": 10_000,
            "WALK_IN_FREEZER": 12_000, "REACH_IN_CASE": 8_000,
            "CHILLER": 30_000, "HVAC_RTU": 15_000,
            "HVAC_SPLIT_SYSTEM": 10_000, "HVAC_VRF": 28_000,
            "HEAT_PUMP": 12_000, "DISPLAY_CASE": 8_000,
            "COOLER_COMPRESSOR": 6_000,
        },
    }
    utility_rate = {"energy_rate": 0.12, "escalation_rate": 0.03}

    engine = CapExEngine()
    result = engine.analyze(
        store={"name": f"Site {site_id}", "store_id": site_id},
        assets=enriched_assets,
        replacement_options=replacement_options,
        economic_assumption=economic_assumption,
        utility_rate=utility_rate,
        budget=budget,
        objective=objective,
        health_data=health_map,
        fault_data=fault_map,
        energy_waste_data=waste_map,
        peer_data=peer_map,
    )

    return CapExPlanResponse(
        site_id=site_id,
        computed_at=datetime.now(timezone.utc),
        budget=budget,
        summary=result.summary,
        optimized_plan=result.optimized_plan,
        sensitivity=result.sensitivity,
        next_best_assets=result.next_best_assets,
    )


# ═══════════════════════════════════════════════════════════════════════
# Fleet Routes
# ═══════════════════════════════════════════════════════════════════════

fleet_router = APIRouter()


def _derive_estate_location(site_id: str):
    """Derive estate (region) and location from site_id.

    Maps 'test site N' to regional estates and clean location names.
    """
    import re
    m = re.search(r"(\d+)$", (site_id or "").strip())
    if m:
        num = int(m.group(1))
        if num <= 8:
            estate = "North Region"
        elif num <= 16:
            estate = "South Region"
        elif num <= 24:
            estate = "East Region"
        else:
            estate = "West Region"
        location = f"Location {num}"
        return estate, location
    # Fallback: use site_id directly
    return "Default Estate", site_id or "Unknown"


@fleet_router.get("/assets", response_model=FleetAssetsListResponse)
async def get_fleet_assets(
    site_id: str = Query(default="default", description="Site ID to filter assets"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    limit: int = Query(default=50, ge=1, le=500, description="Page size (max 500)"),
    status_filter: Optional[str] = Query(default=None, description="Filter by status: normal, watching, action_required, no_data"),
    sort_by: Optional[str] = Query(default=None, description="Sort field: health_score, rul_hours, asset_id"),
    sort_desc: bool = Query(default=True, description="Sort descending"),
):
    """Get fleet assets with health data, supporting pagination and filtering."""
    asset_data, alert_data, _, _ = _collect_data_from_db(site_id)
    health_data = _collect_health_data(site_id, asset_data)

    # Build lookup maps
    health_map = {h["asset_id"]: h for h in health_data}
    alert_map: Dict[str, List] = {}
    for al in alert_data:
        alert_map.setdefault(al["asset_id"], []).append(al)

    assets = []
    for a in asset_data:
        aid = a["asset_id"]
        h = health_map.get(aid, {})
        asset_alerts = alert_map.get(aid, [])
        active_alerts = [al for al in asset_alerts if al.get("status") == "active"]

        health_score = h.get("health_score") or 0.0
        rul_hours = h.get("rul_hours") or 0.0
        _sensor_trust_raw = h.get("sensor_trust_score")
        sensor_trust = (_sensor_trust_raw / 100) if _sensor_trust_raw is not None else 0.0

        # Determine status from health band
        band = h.get("health_band") or "unknown"
        status = "normal"
        if band == "unknown":
            status = "no_data"
        elif band in ("action", "critical"):
            status = "action_required"
        elif band in ("monitoring", "alert"):
            status = "watching"

        primary_alert = active_alerts[0] if active_alerts else None

        asset_site = a.get("site_id", site_id)
        estate, location = _derive_estate_location(asset_site)

        assets.append(FleetAssetResponse(
            asset_id=aid,
            site_id=asset_site,
            asset_type=a.get("asset_type", "hvac_rtu"),
            manufacturer=a.get("manufacturer", ""),
            model=a.get("model_number", ""),
            status=status,
            regime="unknown",
            estate=estate,
            location=location,
            hours_monitored=0,
            health_score=health_score,
            rul_hours=rul_hours,
            sensor_trust=sensor_trust,
            health={
                "health_score": health_score,
                "health_band": band,
                "sensor_trust_score": h.get("sensor_trust_score"),
                "change_detection_score": h.get("change_detection_score"),
                "fault_probability_score": h.get("fault_probability_score"),
                "rul_score": h.get("rul_score"),
                "degradation_score": h.get("degradation_score"),
                "score_trend": 0.0,
                "pf_position": (h.get("degradation_score") or 0) / 100,
                "confidence": 0.0 if band == "unknown" else 0.8,
            },
            rul={
                "rul_hours": rul_hours,
                "confidence": 0.0 if band == "unknown" else 0.8,
                "degradation_index": (h.get("degradation_score") or 0) / 100,
                "model_agreement": 0.0 if band == "unknown" else 0.85,
                "fault_type": primary_alert.get("primary_fault") if primary_alert else None,
            },
            primary_fault=primary_alert.get("primary_fault") if primary_alert else None,
            confidence=primary_alert.get("confidence") if primary_alert else None,
            false_alarm_prob=primary_alert.get("false_alarm_probability") if primary_alert else None,
            recommended_action=None,
            sensor_health=f"{int(sensor_trust * 12)}/12 sensors trusted" if _sensor_trust_raw is not None else "no data",
            active_alert={
                "alert_type": primary_alert["alert_type"],
                "primary_fault": primary_alert.get("primary_fault"),
                "confidence": primary_alert.get("confidence", 0),
                "false_alarm_prob": primary_alert.get("false_alarm_probability", 0),
                "recommended_action": "Schedule inspection",
                "timestamp": (primary_alert.get("created_at") or datetime.now(timezone.utc)).isoformat(),
            } if primary_alert else None,
        ))

    # Apply status filter
    if status_filter:
        assets = [a for a in assets if a.status == status_filter]

    total = len(assets)

    # Sort
    if sort_by in ("health_score", "rul_hours", "asset_id"):
        assets.sort(key=lambda a: getattr(a, sort_by, 0) or 0, reverse=sort_desc)

    # Paginate
    assets = assets[offset:offset + limit]

    return FleetAssetsListResponse(assets=assets, total=total, offset=offset, limit=limit)


@fleet_router.get("/sites")
async def get_fleet_sites():
    """Return locations and asset type summary from the TwinStore ecosystem mapping.

    This is the authoritative source for location/asset data used by the Budget page,
    Ecosystem Optimizer, and the global site selector.
    """
    sites = []
    asset_type_summary = []

    # ── 1. TwinStore (primary) ───────────────────────────────────────
    try:
        from loweconex_platform.digital_twins.store import get_default_store

        twin_store = get_default_store()
        # Iterate all locations across all estates
        all_locations = list(twin_store._locations.values())
        asset_type_counts: Dict[str, int] = {}

        for loc in all_locations:
            loc_assets = twin_store.get_assets_by_location(loc.location_id)
            type_counts: Dict[str, int] = {}
            for a in loc_assets:
                atype = a.asset_type.value if hasattr(a.asset_type, "value") else str(a.asset_type)
                type_counts[atype] = type_counts.get(atype, 0) + 1
                asset_type_counts[atype] = asset_type_counts.get(atype, 0) + 1

            sites.append({
                "id": loc.location_id,
                "name": loc.address or loc.location_id.replace("_", " ").title(),
                "address": loc.address or "",
                "store_format": loc.store_format or "",
                "sqft": loc.sqft,
                "climate_zone": loc.climate_zone or "",
                "asset_count": len(loc_assets),
                "asset_types": type_counts,
            })

        for atype, count in sorted(asset_type_counts.items()):
            asset_type_summary.append({"asset_type": atype, "count": count})

    except Exception as e:
        logger.debug("TwinStore site enumeration skipped: %s", e)

    # ── 2. DB fallback if TwinStore is empty ──────────────────────────
    if not sites:
        try:
            from ...persistence.database import get_session
            from ...persistence.models import AssetModel

            with get_session() as session:
                rows = session.query(AssetModel).filter(AssetModel.is_active == True).all()
                loc_map: Dict[str, Dict[str, int]] = {}
                for r in rows:
                    sid = r.site_id or "default"
                    atype = r.asset_type or "unknown"
                    loc_map.setdefault(sid, {})
                    loc_map[sid][atype] = loc_map[sid].get(atype, 0) + 1

                atype_totals: Dict[str, int] = {}
                for sid, types in loc_map.items():
                    sites.append({
                        "id": sid,
                        "name": sid.replace("_", " ").title(),
                        "address": "",
                        "store_format": "",
                        "sqft": None,
                        "climate_zone": "",
                        "asset_count": sum(types.values()),
                        "asset_types": types,
                    })
                    for at, c in types.items():
                        atype_totals[at] = atype_totals.get(at, 0) + c

                for atype, count in sorted(atype_totals.items()):
                    asset_type_summary.append({"asset_type": atype, "count": count})
        except Exception as e2:
            logger.debug("DB site enumeration also skipped: %s", e2)

    return {"sites": sites, "asset_types": asset_type_summary}


@fleet_router.get("/metrics", response_model=FleetMetricsResponse)
async def get_fleet_metrics(
    site_id: str = Query(default="default", description="Site ID"),
):
    """Get aggregated fleet metrics."""
    asset_data, alert_data, _, _ = _collect_data_from_db(site_id)
    health_data = _collect_health_data(site_id, asset_data)

    n_assets = len(health_data)
    if n_assets == 0:
        return FleetMetricsResponse()

    # Only include assets with real health data in averages
    known_health = [h for h in health_data if h.get("health_score") is not None]
    n_known = len(known_health) or 1  # avoid division by zero
    avg_rul = sum(h.get("rul_hours") or 0 for h in known_health) / n_known
    avg_health = sum(h.get("health_score") or 0 for h in known_health) / n_known
    degrading = sum(1 for h in known_health if (h.get("health_score") or 0) < 60)
    critical = sum(1 for h in known_health if (h.get("health_score") or 0) < 30)
    open_incidents = sum(1 for a in alert_data if a.get("status") == "active")

    return FleetMetricsResponse(
        avg_rul_hours=round(avg_rul),
        degrading_count=degrading,
        open_incidents=open_incidents,
        total_assets=n_assets,
        avg_health_score=round(avg_health, 1),
        critical_count=critical,
    )


# ═══════════════════════════════════════════════════════════════════════
# Data Upload Routes
# ═══════════════════════════════════════════════════════════════════════

upload_router = APIRouter()


@upload_router.post("/csv", response_model=UploadResponse)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file with telemetry data"),
    site_id: str = Form(default="default"),
    asset_id_column: str = Form(default="asset_id"),
    timestamp_column: str = Form(default="timestamp"),
):
    """Upload a CSV file of telemetry data for processing.

    The CSV should have columns matching TelemetryRequest fields.
    At minimum: timestamp, asset_id, and one or more sensor readings.
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    records_processed = 0
    records_failed = 0
    asset_ids_seen = set()

    # Mapping from common CSV column names to our telemetry fields
    FIELD_MAP = {
        "suction_line_temp": ["suction_line_temp", "suction_temp", "SuctionTemp"],
        "discharge_temp": ["discharge_temp", "DischargeTemp"],
        "supply_air_temp": ["supply_air_temp", "SupplyAirTemp", "SAT"],
        "return_air_temp": ["return_air_temp", "ReturnAirTemp", "RAT"],
        "ambient_temp": ["ambient_temp", "AmbientTemp", "OAT"],
        "zone_temp": ["zone_temp", "ZoneTemp", "SpaceTemp"],
        "suction_pressure": ["suction_pressure", "SuctionPressure"],
        "discharge_pressure": ["discharge_pressure", "DischargePressure"],
        "compressor_current": ["compressor_current", "CompressorCurrent"],
        "compressor_power": ["compressor_power", "CompressorPower"],
        "superheat": ["superheat", "Superheat", "SH"],
        "subcool": ["subcool", "Subcool", "SC"],
        "compressor_on": ["compressor_on", "CompressorOn", "compressor_status"],
    }

    batch = []
    for row in reader:
        try:
            asset_id = row.get(asset_id_column, "").strip()
            ts_raw = row.get(timestamp_column, "").strip()
            if not asset_id or not ts_raw:
                records_failed += 1
                continue

            # Parse timestamp
            ts = None
            for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M"]:
                try:
                    ts = datetime.strptime(ts_raw, fmt)
                    break
                except ValueError:
                    continue
            if ts is None:
                records_failed += 1
                continue

            # Build telemetry dict
            telemetry = {
                "asset_id": asset_id,
                "site_id": site_id,
                "timestamp": ts,
            }

            for target_field, source_names in FIELD_MAP.items():
                for src in source_names:
                    val = row.get(src)
                    if val is not None and val.strip():
                        try:
                            if target_field == "compressor_on":
                                telemetry[target_field] = val.strip().lower() in ("1", "true", "on", "yes")
                            else:
                                telemetry[target_field] = float(val)
                        except (ValueError, TypeError):
                            pass
                        break

            batch.append(telemetry)
            asset_ids_seen.add(asset_id)
            records_processed += 1

        except Exception as e:
            logger.debug("Row parse error: %s", e)
            records_failed += 1

    # Persist to database
    persisted = 0
    try:
        from ...persistence.database import get_session
        from ...persistence.repositories import TelemetryRepository, AssetRepository

        with get_session() as session:
            asset_repo = AssetRepository(session)
            telem_repo = TelemetryRepository(session)

            # Ensure assets exist
            for aid in asset_ids_seen:
                existing = asset_repo.get_by_id(aid)
                if not existing:
                    asset_repo.create(asset_id=aid, site_id=site_id)

            # Bulk insert telemetry
            if batch:
                persisted = telem_repo.bulk_create(batch)

            session.commit()
    except Exception as e:
        logger.warning("Persistence failed, data processed in-memory only: %s", e)

    # Feed through loweconex ingestion pipeline (Normalizer → TwinStore)
    ingestion_stats = {}
    try:
        from loweconex_platform.ingestion.normalizer import Normalizer, SchemaMapping
        from loweconex_platform.ingestion.validators import DataValidator
        from loweconex_platform.digital_twins.store import get_default_store

        twin_store = get_default_store()
        validator = DataValidator(twin_store)

        # Convert wide telemetry rows into canonical point rows expected by Normalizer.
        canonical_rows: List[Dict[str, Any]] = []
        for record in batch:
            aid = record.get("asset_id", "")
            ts = record.get("timestamp")
            for key, value in record.items():
                if key in {"asset_id", "site_id", "timestamp"}:
                    continue
                if isinstance(value, bool):
                    value = 1.0 if value else 0.0
                if not isinstance(value, (int, float)):
                    continue
                canonical_rows.append({
                    "asset_id": aid,
                    "location_id": site_id,
                    "timestamp": ts,
                    "point_name": key,
                    "value": float(value),
                    "unit": "kW" if key == "compressor_power" else "",
                })

        validation = validator.validate(
            canonical_rows,
            required_fields=["asset_id", "timestamp", "point_name", "value"],
            unique_fields=None,
            check_referential_integrity=False,
        )
        ingestion_stats["validation_score"] = getattr(validation, "quality_score", 1.0)
        ingestion_stats["validation_issues"] = len(getattr(validation, "issues", []))

        normalizer = Normalizer(twin_store)
        mapping = SchemaMapping(
            name="csv_upload_telemetry",
            source_type="telemetry",
            timezone="UTC",
        )
        mapping.add_field(source="asset_id", canonical="asset_id")
        mapping.add_field(source="location_id", canonical="location_id")
        mapping.add_field(source="timestamp", canonical="timestamp", transform="datetime")
        mapping.add_field(source="point_name", canonical="point_name")
        mapping.add_field(source="value", canonical="value", transform="float")
        mapping.add_field(source="unit", canonical="unit")
        mapping.identity_fields["asset_id"] = "asset_id"
        mapping.identity_fields["location_id"] = "location_id"

        norm_stats = normalizer.normalize_and_load(
            data=canonical_rows,
            mapping=mapping,
            company_id=site_id,
            source_system="csv_upload",
        )
        ingestion_stats["normalized_records"] = int(norm_stats.get("timeseries_points", 0))
        logger.info("Loweconex ingestion pipeline: %s", ingestion_stats)
    except ImportError:
        logger.debug("Loweconex ingestion pipeline not available")
    except Exception as e:
        logger.warning("Loweconex ingestion pipeline error: %s", e)
        ingestion_stats["error"] = str(e)

    # Feed through PdM systems
    pdm_processed = 0
    try:
        from . import get_pdm_system
        for record in batch[:500]:  # limit processing batch
            aid = record["asset_id"]
            try:
                system = get_pdm_system(aid)
                if system:
                    system.process_reading(record)
                    pdm_processed += 1
            except Exception:
                pass
    except Exception as e:
        logger.debug("PdM processing: %s", e)

    ingestion_msg = ""
    if ingestion_stats.get("normalized_records"):
        ingestion_msg = f" {ingestion_stats['normalized_records']} normalized via ingestion pipeline."
    if ingestion_stats.get("validation_score"):
        ingestion_msg += f" Data quality: {ingestion_stats['validation_score']:.0%}."

    # ── T2-6: Invalidate KPI cache + emit event on new data ────────────
    if records_processed > 0:
        try:
            from ...persistence.kpi_repository import get_dashboard_cache
            cache = get_dashboard_cache()
            cache.invalidate(site_id)
            logger.info("KPI cache invalidated for site %s after data upload", site_id)
        except Exception as cache_err:
            logger.debug("KPI cache invalidation skipped: %s", cache_err)

        try:
            from ..websocket import get_connection_manager
            import asyncio
            mgr = get_connection_manager()
            asyncio.create_task(mgr.broadcast_to_operators({
                "type": "data_uploaded",
                "site_id": site_id,
                "records_processed": records_processed,
                "asset_ids": sorted(asset_ids_seen),
                "message": "New data uploaded — KPI dashboard will refresh on next load.",
            }))
        except Exception:
            pass

    return UploadResponse(
        status="success" if records_processed > 0 else "no_data",
        records_processed=records_processed,
        records_failed=records_failed,
        asset_ids=sorted(asset_ids_seen),
        message=(
            f"Processed {records_processed} records for {len(asset_ids_seen)} assets. "
            f"{persisted} persisted to DB. {pdm_processed} processed through PdM pipeline."
            f"{ingestion_msg}"
        ),
    )


# ── Generic CSV parse helper ─────────────────────────────────────────

def _parse_csv_text(content: bytes) -> csv.DictReader:
    """Decode bytes and return a csv.DictReader."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    return csv.DictReader(io.StringIO(text))


def _parse_ts(raw: str) -> Optional[datetime]:
    """Try common timestamp formats."""
    for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y %H:%M", "%m/%d/%Y"]:
        try:
            return datetime.strptime(raw.strip(), fmt)
        except ValueError:
            continue
    return None


def _resolve_col(row: Dict, candidates: List[str]) -> Optional[str]:
    """Return the first non-empty value from candidate column names."""
    for c in candidates:
        v = row.get(c, "").strip() if row.get(c) else ""
        if v:
            return v
    return None


def _resolve_float(row: Dict, candidates: List[str]) -> Optional[float]:
    """Return the first parseable float from candidate column names."""
    v = _resolve_col(row, candidates)
    if v:
        try:
            return float(v.replace(",", "").replace("$", ""))
        except (ValueError, TypeError):
            pass
    return None


# ── Asset Inventory Upload ───────────────────────────────────────────

@upload_router.post("/assets", response_model=UploadResponse)
async def upload_asset_inventory(
    file: UploadFile = File(..., description="CSV file with asset inventory"),
    site_id: str = Form(default="default"),
):
    """Upload an asset inventory CSV.

    Required columns: asset_id
    Optional: asset_type, manufacturer, model, serial_number, install_date, site_id,
              refrigerant_type, capacity_tons
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    reader = _parse_csv_text(await file.read())
    processed = 0
    failed = 0
    asset_ids = set()

    try:
        from ...persistence.database import get_session
        from ...persistence.repositories import AssetRepository

        with get_session() as session:
            repo = AssetRepository(session)
            for row in reader:
                try:
                    aid = _resolve_col(row, ["asset_id", "AssetID", "asset", "equipment_id", "EquipmentID"])
                    if not aid:
                        failed += 1
                        continue

                    row_site = _resolve_col(row, ["site_id", "SiteID", "location_id", "store_id", "StoreID"]) or site_id
                    install_str = _resolve_col(row, ["install_date", "InstallDate", "installation_date", "commissioned"])
                    install_dt = _parse_ts(install_str) if install_str else None

                    existing = repo.get_by_id(aid)
                    if existing:
                        existing.asset_type = _resolve_col(row, ["asset_type", "AssetType", "type", "equipment_type"]) or existing.asset_type
                        existing.manufacturer = _resolve_col(row, ["manufacturer", "Manufacturer", "make", "brand"]) or existing.manufacturer
                        existing.model_number = _resolve_col(row, ["model", "Model", "model_number", "ModelNumber"]) or existing.model_number
                        existing.serial_number = _resolve_col(row, ["serial_number", "SerialNumber", "serial"]) or existing.serial_number
                        if install_dt:
                            existing.install_date = install_dt
                        existing.site_id = row_site
                        existing.refrigerant_type = _resolve_col(row, ["refrigerant_type", "refrigerant", "RefrigerantType"]) or existing.refrigerant_type
                        cap = _resolve_float(row, ["capacity_tons", "nominal_capacity_tons", "tons"])
                        if cap:
                            existing.nominal_capacity_tons = cap
                    else:
                        repo.create(
                            asset_id=aid,
                            site_id=row_site,
                            asset_type=_resolve_col(row, ["asset_type", "AssetType", "type", "equipment_type"]) or "hvac_rtu",
                            manufacturer=_resolve_col(row, ["manufacturer", "Manufacturer", "make"]) or "",
                            model_number=_resolve_col(row, ["model", "Model", "model_number"]) or "",
                            serial_number=_resolve_col(row, ["serial_number", "SerialNumber"]) or "",
                            install_date=install_dt,
                            refrigerant_type=_resolve_col(row, ["refrigerant_type", "refrigerant"]) or None,
                            nominal_capacity_tons=_resolve_float(row, ["capacity_tons", "tons"]),
                        )

                    asset_ids.add(aid)
                    processed += 1
                except Exception as e:
                    logger.debug("Asset row parse error: %s", e)
                    failed += 1

            session.commit()
    except Exception as e:
        logger.warning("Asset upload persistence failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    return UploadResponse(
        status="success" if processed > 0 else "no_data",
        records_processed=processed,
        records_failed=failed,
        asset_ids=sorted(asset_ids),
        message=f"Imported {processed} assets ({failed} failed). Site: {site_id}.",
    )


# ── Work Order Upload ────────────────────────────────────────────────

@upload_router.post("/work-orders", response_model=UploadResponse)
async def upload_work_orders(
    file: UploadFile = File(..., description="CSV file with work orders"),
    site_id: str = Form(default="default"),
):
    """Upload a work order CSV.

    Required columns: wo_id (or work_order_id), asset_id, opened_at (or date)
    Optional: wo_type, priority, status, cost, labor_hours, description,
              resolution, provider, closed_at, dispatched_at, source_alert_id
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    reader = _parse_csv_text(await file.read())
    processed = 0
    failed = 0
    asset_ids = set()

    try:
        from ...persistence.database import get_session
        from ...persistence.models import WorkOrderModel

        with get_session() as session:
            for row in reader:
                try:
                    wo_id = _resolve_col(row, ["wo_id", "work_order_id", "WorkOrderID", "wo_number", "WO"])
                    aid = _resolve_col(row, ["asset_id", "AssetID", "equipment_id"])
                    date_str = _resolve_col(row, ["opened_at", "date", "open_date", "created_date", "OpenDate"])
                    if not wo_id or not aid or not date_str:
                        failed += 1
                        continue
                    opened = _parse_ts(date_str)
                    if not opened:
                        failed += 1
                        continue

                    closed_str = _resolve_col(row, ["closed_at", "close_date", "completed_date", "CloseDate"])
                    dispatched_str = _resolve_col(row, ["dispatched_at", "dispatch_date", "DispatchDate", "assigned_at", "dispatch_time"])

                    wo = WorkOrderModel(
                        wo_id=wo_id,
                        asset_id=aid,
                        site_id=_resolve_col(row, ["site_id", "SiteID"]) or site_id,
                        wo_type=_resolve_col(row, ["wo_type", "type", "order_type", "WorkType"]) or "reactive",
                        priority=_resolve_col(row, ["priority", "Priority"]) or "normal",
                        status=_resolve_col(row, ["status", "Status"]) or "completed",
                        cost=_resolve_float(row, ["cost", "total_cost", "Cost", "amount"]) or 0.0,
                        labor_hours=_resolve_float(row, ["labor_hours", "hours", "LaborHours"]) or 0.0,
                        description=_resolve_col(row, ["description", "Description", "notes", "problem"]) or "",
                        resolution=_resolve_col(row, ["resolution", "Resolution", "fix", "action_taken"]) or "",
                        provider=_resolve_col(row, ["provider", "Provider", "vendor", "technician"]) or "in_house",
                        opened_at=opened,
                        dispatched_at=_parse_ts(dispatched_str) if dispatched_str else None,
                        closed_at=_parse_ts(closed_str) if closed_str else None,
                        source_alert_id=_resolve_col(row, ["source_alert_id", "alert_id", "AlertID", "originating_alert"]) or None,
                    )
                    session.merge(wo)
                    asset_ids.add(aid)
                    processed += 1
                except Exception as e:
                    logger.debug("WO row error: %s", e)
                    failed += 1

            session.commit()
    except Exception as e:
        logger.warning("Work order upload failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    return UploadResponse(
        status="success" if processed > 0 else "no_data",
        records_processed=processed,
        records_failed=failed,
        asset_ids=sorted(asset_ids),
        message=f"Imported {processed} work orders ({failed} failed).",
    )


# ── Energy Data Upload ───────────────────────────────────────────────

@upload_router.post("/energy", response_model=UploadResponse)
async def upload_energy_data(
    file: UploadFile = File(..., description="CSV file with energy usage/cost data"),
    site_id: str = Form(default="default"),
):
    """Upload energy consumption and cost CSV.

    Required columns: period_start (or date, month), kwh_consumed (or kwh, usage_kwh)
    Optional: period_end, cost, rate_per_kwh, demand_kw, site_id, asset_id, source
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    reader = _parse_csv_text(await file.read())
    processed = 0
    failed = 0

    try:
        from ...persistence.database import get_session
        from ...persistence.models import EnergyDataModel

        with get_session() as session:
            for row in reader:
                try:
                    date_str = _resolve_col(row, ["period_start", "date", "month", "billing_date", "Date", "Period"])
                    kwh = _resolve_float(row, ["kwh_consumed", "kwh", "usage_kwh", "kWh", "consumption", "total_kwh"])
                    if not date_str or kwh is None:
                        failed += 1
                        continue
                    period_start = _parse_ts(date_str)
                    if not period_start:
                        failed += 1
                        continue

                    end_str = _resolve_col(row, ["period_end", "end_date", "PeriodEnd"])

                    rec = EnergyDataModel(
                        site_id=_resolve_col(row, ["site_id", "SiteID", "location"]) or site_id,
                        asset_id=_resolve_col(row, ["asset_id", "AssetID", "meter_id"]),
                        period_start=period_start,
                        period_end=_parse_ts(end_str) if end_str else None,
                        kwh_consumed=kwh,
                        cost=_resolve_float(row, ["cost", "total_cost", "amount", "bill_amount"]) or 0.0,
                        rate_per_kwh=_resolve_float(row, ["rate_per_kwh", "rate", "price_per_kwh", "$/kWh"]),
                        demand_kw=_resolve_float(row, ["demand_kw", "peak_demand", "demand"]),
                        source=_resolve_col(row, ["source", "Source", "data_source"]) or "utility_bill",
                    )
                    session.add(rec)
                    processed += 1
                except Exception as e:
                    logger.debug("Energy row error: %s", e)
                    failed += 1

            session.commit()
    except Exception as e:
        logger.warning("Energy upload failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    return UploadResponse(
        status="success" if processed > 0 else "no_data",
        records_processed=processed,
        records_failed=failed,
        asset_ids=[],
        message=f"Imported {processed} energy records ({failed} failed).",
    )


# ── Maintenance History Upload ───────────────────────────────────────

@upload_router.post("/maintenance", response_model=UploadResponse)
async def upload_maintenance_history(
    file: UploadFile = File(..., description="CSV file with maintenance service history"),
    site_id: str = Form(default="default"),
):
    """Upload maintenance service history CSV.

    Required columns: asset_id, service_date (or date)
    Optional: service_type, cost, labor_hours, provider, description,
              parts_replaced, site_id
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    reader = _parse_csv_text(await file.read())
    processed = 0
    failed = 0
    asset_ids = set()

    try:
        from ...persistence.database import get_session
        from ...persistence.models import MaintenanceHistoryModel

        with get_session() as session:
            for row in reader:
                try:
                    aid = _resolve_col(row, ["asset_id", "AssetID", "equipment_id"])
                    date_str = _resolve_col(row, ["service_date", "date", "Date", "completed_date", "ServiceDate"])
                    if not aid or not date_str:
                        failed += 1
                        continue
                    svc_date = _parse_ts(date_str)
                    if not svc_date:
                        failed += 1
                        continue

                    rec = MaintenanceHistoryModel(
                        asset_id=aid,
                        site_id=_resolve_col(row, ["site_id", "SiteID"]) or site_id,
                        service_date=svc_date,
                        service_type=_resolve_col(row, ["service_type", "type", "ServiceType", "maintenance_type"]) or "pm",
                        cost=_resolve_float(row, ["cost", "total_cost", "Cost", "amount"]) or 0.0,
                        labor_hours=_resolve_float(row, ["labor_hours", "hours", "LaborHours"]) or 0.0,
                        provider=_resolve_col(row, ["provider", "Provider", "vendor", "technician"]) or "",
                        description=_resolve_col(row, ["description", "Description", "notes"]) or "",
                        parts_replaced=_resolve_col(row, ["parts_replaced", "parts", "PartsReplaced"]) or "",
                    )
                    session.add(rec)
                    asset_ids.add(aid)
                    processed += 1
                except Exception as e:
                    logger.debug("Maintenance row error: %s", e)
                    failed += 1

            session.commit()
    except Exception as e:
        logger.warning("Maintenance history upload failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    return UploadResponse(
        status="success" if processed > 0 else "no_data",
        records_processed=processed,
        records_failed=failed,
        asset_ids=sorted(asset_ids),
        message=f"Imported {processed} maintenance records ({failed} failed).",
    )


# ── Refrigerant Records Upload ───────────────────────────────────────

@upload_router.post("/refrigerant", response_model=UploadResponse)
async def upload_refrigerant_records(
    file: UploadFile = File(..., description="CSV file with refrigerant tracking records"),
    site_id: str = Form(default="default"),
):
    """Upload refrigerant tracking CSV.

    Required columns: asset_id, record_date (or date)
    Optional: refrigerant_type, charge_lbs, lbs_added, lbs_recovered,
              leak_detected, leak_rate_pct, notes, site_id
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    reader = _parse_csv_text(await file.read())
    processed = 0
    failed = 0
    asset_ids = set()

    try:
        from ...persistence.database import get_session
        from ...persistence.models import RefrigerantRecordModel

        with get_session() as session:
            for row in reader:
                try:
                    aid = _resolve_col(row, ["asset_id", "AssetID", "equipment_id"])
                    date_str = _resolve_col(row, ["record_date", "date", "Date", "service_date"])
                    if not aid or not date_str:
                        failed += 1
                        continue
                    rec_date = _parse_ts(date_str)
                    if not rec_date:
                        failed += 1
                        continue

                    leak_str = _resolve_col(row, ["leak_detected", "leak", "LeakDetected"])
                    leak = leak_str.lower() in ("1", "true", "yes", "y") if leak_str else False

                    rec = RefrigerantRecordModel(
                        asset_id=aid,
                        site_id=_resolve_col(row, ["site_id", "SiteID"]) or site_id,
                        record_date=rec_date,
                        refrigerant_type=_resolve_col(row, ["refrigerant_type", "refrigerant", "type", "RefType"]) or "R-410A",
                        charge_lbs=_resolve_float(row, ["charge_lbs", "charge", "total_charge", "ChargeLbs"]) or 0.0,
                        lbs_added=_resolve_float(row, ["lbs_added", "added", "LbsAdded", "quantity_added"]) or 0.0,
                        lbs_recovered=_resolve_float(row, ["lbs_recovered", "recovered", "LbsRecovered"]) or 0.0,
                        leak_detected=leak,
                        leak_rate_pct=_resolve_float(row, ["leak_rate_pct", "leak_rate", "LeakRate"]),
                        notes=_resolve_col(row, ["notes", "Notes", "comments"]) or "",
                    )
                    session.add(rec)
                    asset_ids.add(aid)
                    processed += 1
                except Exception as e:
                    logger.debug("Refrigerant row error: %s", e)
                    failed += 1

            session.commit()
    except Exception as e:
        logger.warning("Refrigerant upload failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    return UploadResponse(
        status="success" if processed > 0 else "no_data",
        records_processed=processed,
        records_failed=failed,
        asset_ids=sorted(asset_ids),
        message=f"Imported {processed} refrigerant records ({failed} failed).",
    )


# ── Alerts Upload ─────────────────────────────────────────────────────

@upload_router.post("/alerts", response_model=UploadResponse)
async def upload_alerts(
    file: UploadFile = File(..., description="CSV file with historical alerts"),
    site_id: str = Form(default="default"),
):
    """Upload historical alert CSV.

    Required columns: alert_id, asset_id, alert_type, severity
    Optional: confidence, false_alarm_probability, primary_fault, secondary_fault,
              recommended_action, action_urgency, status, created_at,
              acknowledged_at, resolved_at, feedback_outcome, regime_at_detection,
              energy_penalty_estimate_pct, downtime_risk_score, estimated_cost_if_ignored
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    reader = _parse_csv_text(await file.read())
    processed = 0
    failed = 0
    asset_ids = set()

    try:
        from ...persistence.database import get_session
        from ...persistence.models import AlertModel
        from ...persistence.repositories import AssetRepository

        with get_session() as session:
            asset_repo = AssetRepository(session)
            for row in reader:
                try:
                    alert_id = _resolve_col(row, ["alert_id", "AlertID", "alert_number", "id"])
                    aid = _resolve_col(row, ["asset_id", "AssetID", "equipment_id"])
                    alert_type = _resolve_col(row, ["alert_type", "AlertType", "type"]) or "actionable"
                    severity = _resolve_col(row, ["severity", "Severity", "level"]) or "medium"

                    if not alert_id or not aid:
                        failed += 1
                        continue

                    # Ensure asset exists
                    if not asset_repo.get_by_id(aid):
                        asset_repo.create(asset_id=aid, site_id=site_id)

                    created_str = _resolve_col(row, ["created_at", "date", "timestamp", "detected_at", "CreatedAt"])
                    ack_str = _resolve_col(row, ["acknowledged_at", "ack_date", "AcknowledgedAt"])
                    resolved_str = _resolve_col(row, ["resolved_at", "resolve_date", "closed_at", "ResolvedAt"])

                    alert = AlertModel(
                        alert_id=alert_id,
                        asset_id=aid,
                        alert_type=alert_type,
                        severity=severity,
                        confidence=_resolve_float(row, ["confidence", "Confidence", "score"]),
                        false_alarm_probability=_resolve_float(row, ["false_alarm_probability", "fa_prob", "FAProb"]),
                        primary_fault=_resolve_col(row, ["primary_fault", "PrimaryFault", "fault", "fault_type"]),
                        secondary_fault=_resolve_col(row, ["secondary_fault", "SecondaryFault"]),
                        recommended_action=_resolve_col(row, ["recommended_action", "action", "recommendation"]),
                        action_urgency=_resolve_col(row, ["action_urgency", "urgency", "ActionUrgency"]) or "monitor",
                        regime_at_detection=_resolve_col(row, ["regime_at_detection", "regime", "operating_regime"]),
                        energy_penalty_estimate_pct=_resolve_float(row, ["energy_penalty_estimate_pct", "energy_penalty"]),
                        downtime_risk_score=_resolve_float(row, ["downtime_risk_score", "downtime_risk"]),
                        estimated_cost_if_ignored=_resolve_float(row, ["estimated_cost_if_ignored", "cost_if_ignored"]),
                        status=_resolve_col(row, ["status", "Status"]) or "active",
                        created_at=_parse_ts(created_str) if created_str else datetime.now(timezone.utc),
                        acknowledged_at=_parse_ts(ack_str) if ack_str else None,
                        resolved_at=_parse_ts(resolved_str) if resolved_str else None,
                        feedback_outcome=_resolve_col(row, ["feedback_outcome", "outcome", "FeedbackOutcome"]),
                    )
                    session.merge(alert)
                    asset_ids.add(aid)
                    processed += 1
                except Exception as e:
                    logger.debug("Alert row error: %s", e)
                    failed += 1

            session.commit()
    except Exception as e:
        logger.warning("Alert upload failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    return UploadResponse(
        status="success" if processed > 0 else "no_data",
        records_processed=processed,
        records_failed=failed,
        asset_ids=sorted(asset_ids),
        message=f"Imported {processed} alerts ({failed} failed).",
    )


# ── Feedback Upload ──────────────────────────────────────────────────

@upload_router.post("/feedback", response_model=UploadResponse)
async def upload_feedback(
    file: UploadFile = File(..., description="CSV file with alert feedback records"),
    site_id: str = Form(default="default"),
):
    """Upload bulk alert feedback CSV.

    Required columns: alert_id, asset_id, outcome
    Optional: confirmed_fault_type, notes, feedback_by, feedback_at,
              alert_timestamp, predicted_false_alarm_prob

    Outcome values: confirmed_fault, no_issue_found, sensor_problem
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    reader = _parse_csv_text(await file.read())
    processed = 0
    failed = 0
    asset_ids = set()

    try:
        from ...persistence.database import get_session
        from ...persistence.models import FeedbackModel
        from ...persistence.repositories import AssetRepository

        with get_session() as session:
            asset_repo = AssetRepository(session)
            for row in reader:
                try:
                    alert_id = _resolve_col(row, ["alert_id", "AlertID", "alert_number"])
                    aid = _resolve_col(row, ["asset_id", "AssetID", "equipment_id"])
                    outcome = _resolve_col(row, ["outcome", "Outcome", "feedback_outcome", "result"])

                    if not alert_id or not aid or not outcome:
                        failed += 1
                        continue

                    # Normalise outcome values
                    outcome_lower = outcome.lower().replace(" ", "_").replace("-", "_")
                    valid_outcomes = {"confirmed_fault", "no_issue_found", "sensor_problem"}
                    # Map common aliases
                    outcome_aliases = {
                        "confirmed": "confirmed_fault", "fault": "confirmed_fault",
                        "true_positive": "confirmed_fault", "tp": "confirmed_fault",
                        "no_issue": "no_issue_found", "nif": "no_issue_found",
                        "false_positive": "no_issue_found", "fp": "no_issue_found",
                        "false_alarm": "no_issue_found",
                        "sensor": "sensor_problem", "sensor_issue": "sensor_problem",
                    }
                    outcome_normalized = outcome_aliases.get(outcome_lower, outcome_lower)
                    if outcome_normalized not in valid_outcomes:
                        failed += 1
                        continue

                    # Ensure asset exists
                    if not asset_repo.get_by_id(aid):
                        asset_repo.create(asset_id=aid, site_id=site_id)

                    fb_at_str = _resolve_col(row, ["feedback_at", "date", "Date", "FeedbackAt", "timestamp"])
                    alert_ts_str = _resolve_col(row, ["alert_timestamp", "alert_date", "AlertTimestamp"])

                    fb = FeedbackModel(
                        alert_id=alert_id,
                        asset_id=aid,
                        outcome=outcome_normalized,
                        confirmed_fault_type=_resolve_col(row, ["confirmed_fault_type", "fault_type", "FaultType"]),
                        notes=_resolve_col(row, ["notes", "Notes", "comments", "description"]),
                        feedback_by=_resolve_col(row, ["feedback_by", "FeedbackBy", "technician", "operator"]) or "csv_import",
                        feedback_at=_parse_ts(fb_at_str) if fb_at_str else datetime.now(timezone.utc),
                        alert_timestamp=_parse_ts(alert_ts_str) if alert_ts_str else None,
                        predicted_false_alarm_prob=_resolve_float(row, ["predicted_false_alarm_prob", "fa_prob", "predicted_fa"]),
                    )
                    session.add(fb)
                    asset_ids.add(aid)
                    processed += 1
                except Exception as e:
                    logger.debug("Feedback row error: %s", e)
                    failed += 1

            session.commit()
    except Exception as e:
        logger.warning("Feedback upload failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    return UploadResponse(
        status="success" if processed > 0 else "no_data",
        records_processed=processed,
        records_failed=failed,
        asset_ids=sorted(asset_ids),
        message=f"Imported {processed} feedback records ({failed} failed).",
    )


# ═══════════════════════════════════════════════════════════════════════
# Maintenance Scenario Routes (PdM-focused, replaces marketing scenarios)
# ═══════════════════════════════════════════════════════════════════════

scenario_maint_router = APIRouter()


@scenario_maint_router.post("/analyze", response_model=MaintenanceScenarioResponse)
async def analyze_maintenance_scenario(req: MaintenanceScenarioRequest):
    """Run a maintenance what-if scenario for an asset.

    Scenario types:
    - defer_maintenance: What if we defer maintenance N days?
    - replace_vs_repair: Should we replace or repair this asset?
    - run_to_failure: What's the cost of running to failure?
    """
    from ...services.kpi import KPIConfig

    asset_id = req.asset_id
    analyses = []

    # Get asset health data
    health = {}
    try:
        from . import _pdm_systems
        sys = _pdm_systems.get(asset_id)
        if sys and hasattr(sys, "health_index"):
            hi = sys.health_index
            health = {
                "health_score": getattr(hi, "health_score", 85),
                "rul_hours": getattr(hi, "rul_hours", 5000),
                "degradation_index": getattr(hi, "degradation_index", 0.1),
                "primary_fault": getattr(hi, "primary_fault", None),
            }
    except Exception:
        health = {"health_score": 85, "rul_hours": 5000, "degradation_index": 0.1}

    rul_hours = health.get("rul_hours", 5000)
    health_score = health.get("health_score", 85)
    deg_idx = health.get("degradation_index", 0.1)

    config = KPIConfig()

    if req.scenario_type == "defer_maintenance":
        defer_hours = req.defer_days * 24
        # Risk of failure during deferral
        failure_prob = min(0.95, deg_idx + (defer_hours / max(rul_hours, 1)) * 0.5)
        expected_cost_if_fail = config.avg_wo_cost * 3 + config.hourly_downtime_cost * 8
        expected_loss = failure_prob * expected_cost_if_fail
        pm_cost = config.avg_wo_cost

        analyses.append({
            "agent": "Risk Analyst",
            "title": "Deferral Risk Assessment",
            "summary": (
                f"Deferring {req.defer_days} days: {failure_prob*100:.0f}% failure probability. "
                f"Expected loss: ${expected_loss:,.0f}. "
                f"RUL remaining: {rul_hours:.0f}h. Health score: {health_score:.0f}."
            ),
            "metrics": {"failure_probability": round(failure_prob, 3),
                        "expected_loss": round(expected_loss, 2),
                        "rul_hours": rul_hours},
        })
        analyses.append({
            "agent": "Budget Analyst",
            "title": "Cost Comparison",
            "summary": (
                f"Planned maintenance now: ${pm_cost:,.0f}. "
                f"Expected cost if deferred and fails: ${expected_loss:,.0f}. "
                f"Net risk of deferral: ${expected_loss - pm_cost:,.0f}."
            ),
            "metrics": {"pm_cost": pm_cost, "deferral_risk": round(expected_loss - pm_cost, 2)},
        })
        recommendation = (
            f"{'Proceed with deferral' if failure_prob < 0.20 else 'Schedule maintenance now'} — "
            f"failure risk is {'low' if failure_prob < 0.20 else 'moderate' if failure_prob < 0.50 else 'high'}."
        )

    elif req.scenario_type == "replace_vs_repair":
        repair_cost = config.avg_wo_cost * 2
        replace_cost = config.avg_asset_replacement_cost
        annual_repair_savings = config.baseline_annual_kwh / config.total_assets * 0.20 * config.energy_cost_per_kwh
        remaining_life = rul_hours / 8760  # years

        # NPV of repair vs replace
        repair_npv = -repair_cost
        for yr in range(1, int(remaining_life) + 1):
            repair_npv += annual_repair_savings * 0.3 / ((1 + config.discount_rate) ** yr)

        replace_npv = -replace_cost
        for yr in range(1, 11):
            replace_npv += annual_repair_savings / ((1 + config.discount_rate) ** yr)

        analyses.append({
            "agent": "CapEx Analyst",
            "title": "Replace vs Repair NPV",
            "summary": (
                f"Repair NPV ({remaining_life:.1f}yr life): ${repair_npv:,.0f}. "
                f"Replace NPV (10yr life): ${replace_npv:,.0f}. "
                f"Replacement {'recommended' if replace_npv > repair_npv else 'not recommended'}."
            ),
            "metrics": {"repair_npv": round(repair_npv), "replace_npv": round(replace_npv)},
        })
        recommendation = (
            f"{'Replace' if replace_npv > repair_npv else 'Repair'} the asset — "
            f"NPV difference: ${abs(replace_npv - repair_npv):,.0f}."
        )

    else:  # run_to_failure
        emergency_cost = config.avg_wo_cost * 4
        downtime_hours = 24
        downtime_cost = downtime_hours * config.hourly_downtime_cost
        total_rtf_cost = emergency_cost + downtime_cost
        pm_cost = config.avg_wo_cost

        analyses.append({
            "agent": "Risk Analyst",
            "title": "Run-to-Failure Cost",
            "summary": (
                f"Emergency repair: ${emergency_cost:,.0f} + "
                f"{downtime_hours}h downtime (${downtime_cost:,.0f}) = "
                f"${total_rtf_cost:,.0f} total. Planned maintenance: ${pm_cost:,.0f}."
            ),
            "metrics": {"rtf_cost": total_rtf_cost, "pm_cost": pm_cost,
                        "savings_from_pm": total_rtf_cost - pm_cost},
        })
        recommendation = (
            f"Planned maintenance saves ${total_rtf_cost - pm_cost:,.0f} vs run-to-failure."
        )

    return MaintenanceScenarioResponse(
        scenario_id=f"SCN-{uuid.uuid4().hex[:8].upper()}",
        asset_id=asset_id,
        scenario_type=req.scenario_type,
        analyses=analyses,
        recommendation=recommendation,
        created_at=datetime.now(timezone.utc),
    )


# ═══════════════════════════════════════════════════════════════════════
# Custom KPI Scenario Routes (user-defined what-if analysis)
# ═══════════════════════════════════════════════════════════════════════

class CustomScenarioRequest(BaseModel):
    name: str = Field(..., description="Human-readable scenario name")
    description: str = Field(default="", description="Scenario description")
    parameter_overrides: Dict[str, float] = Field(
        ...,
        description=(
            "KPIConfig parameter overrides. Keys are config field names "
            "(e.g. 'energy_cost_per_kwh', 'baseline_reactive_wo_per_month'), "
            "values are the new absolute values to use."
        ),
    )


class CustomScenarioResponse(BaseModel):
    scenario_id: str
    name: str
    description: str
    parameter_overrides: Dict[str, float]
    created_at: datetime


class CustomScenarioRunResponse(BaseModel):
    scenario_id: str
    name: str
    site_id: str
    computed_at: datetime
    total_savings_medium: float
    scorecards: List[Dict[str, Any]]
    comparison_to_baseline: Dict[str, Any]


# In-memory scenario store (persisted to DB when available)
_custom_scenarios: Dict[str, Dict[str, Any]] = {}


@scenario_maint_router.post("/custom", response_model=CustomScenarioResponse)
async def create_custom_scenario(req: CustomScenarioRequest):
    """Create and save a custom KPI scenario with parameter overrides.

    Allows users to define what-if scenarios by overriding any KPIConfig
    parameter (energy costs, baseline work orders, leak rates, etc.)
    and saving them for later execution and comparison.
    """
    from ...services.kpi import KPIConfig

    # Validate that all parameter keys are valid KPIConfig fields
    valid_fields = set(KPIConfig.__dataclass_fields__.keys())
    invalid = set(req.parameter_overrides.keys()) - valid_fields
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid parameter names: {sorted(invalid)}. "
                   f"Valid fields: {sorted(valid_fields - {'site_id', 'customer_name'})}",
        )

    scenario_id = f"CSCN-{uuid.uuid4().hex[:8].upper()}"
    now = datetime.now(timezone.utc)

    scenario_record = {
        "scenario_id": scenario_id,
        "name": req.name,
        "description": req.description,
        "parameter_overrides": req.parameter_overrides,
        "created_at": now,
    }
    _custom_scenarios[scenario_id] = scenario_record

    # Persist to DB if available
    try:
        from ...persistence.database import get_session
        from ...persistence.kpi_repository import SchemaMappingRepository
        with get_session() as session:
            # Reuse schema mapping table for scenario storage
            from ...persistence.models import SchemaMappingModel
            mapping = SchemaMappingModel(
                mapping_id=scenario_id,
                site_id="__scenarios__",
                name=req.name,
                description=req.description,
                source_type="custom_scenario",
                field_mappings=req.parameter_overrides,
            )
            session.add(mapping)
            session.commit()
    except Exception as e:
        logger.debug("Scenario persistence skipped: %s", e)

    return CustomScenarioResponse(
        scenario_id=scenario_id,
        name=req.name,
        description=req.description,
        parameter_overrides=req.parameter_overrides,
        created_at=now,
    )


@scenario_maint_router.get("/custom", response_model=List[CustomScenarioResponse])
async def list_custom_scenarios():
    """List all saved custom KPI scenarios."""
    # Hydrate from DB if memory is empty
    if not _custom_scenarios:
        try:
            from ...persistence.database import get_session
            from ...persistence.models import SchemaMappingModel
            with get_session() as session:
                rows = session.query(SchemaMappingModel).filter(
                    SchemaMappingModel.site_id == "__scenarios__",
                    SchemaMappingModel.source_type == "custom_scenario",
                    SchemaMappingModel.is_active == True,
                ).all()
                for row in rows:
                    _custom_scenarios[row.mapping_id] = {
                        "scenario_id": row.mapping_id,
                        "name": row.name,
                        "description": row.description or "",
                        "parameter_overrides": row.field_mappings or {},
                        "created_at": row.created_at or datetime.now(timezone.utc),
                    }
        except Exception as e:
            logger.debug("Scenario hydration skipped: %s", e)

    return [
        CustomScenarioResponse(**s) for s in _custom_scenarios.values()
    ]


@scenario_maint_router.post("/custom/{scenario_id}/run", response_model=CustomScenarioRunResponse)
async def run_custom_scenario(
    scenario_id: str,
    site_id: str = Query(default="default", description="Site ID to run scenario against"),
):
    """Execute a saved custom scenario against real site data.

    Applies the scenario's parameter overrides to the site's KPIConfig,
    re-runs all 14 KPI computations, and returns the results alongside
    a comparison to the baseline (unmodified) computation.
    """
    import copy
    from ...services.kpi import KPIOrchestrator, KPIConfig
    from ...services.kpi.registry import KPI_REGISTRY, get_kpi_service

    scenario = _custom_scenarios.get(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")

    # Collect real data
    asset_data, alert_data, telemetry_summary, _ = _collect_data_from_db(site_id)
    health_data = _collect_health_data(site_id, asset_data)

    # Baseline computation
    baseline_config = KPIConfig.load_from_db(site_id)
    baseline_config.total_assets = max(len(asset_data), baseline_config.total_assets)
    baseline_orchestrator = KPIOrchestrator(baseline_config)
    baseline_result = baseline_orchestrator.compute_all(
        asset_data=asset_data,
        alert_data=alert_data,
        telemetry_summary=telemetry_summary,
        health_data=health_data,
    )
    baseline_total = baseline_result.executive_summary.get("total_savings_medium", 0)

    # Scenario computation with overrides
    scenario_config = copy.deepcopy(baseline_config)
    for param, value in scenario["parameter_overrides"].items():
        if hasattr(scenario_config, param):
            setattr(scenario_config, param, type(getattr(scenario_config, param))(value))

    scenario_orchestrator = KPIOrchestrator(scenario_config)
    scenario_result = scenario_orchestrator.compute_all(
        asset_data=asset_data,
        alert_data=alert_data,
        telemetry_summary=telemetry_summary,
        health_data=health_data,
    )
    scenario_total = scenario_result.executive_summary.get("total_savings_medium", 0)

    delta = scenario_total - baseline_total
    pct_change = (delta / baseline_total * 100) if baseline_total > 0 else 0

    return CustomScenarioRunResponse(
        scenario_id=scenario_id,
        name=scenario["name"],
        site_id=site_id,
        computed_at=datetime.now(timezone.utc),
        total_savings_medium=scenario_total,
        scorecards=scenario_result.scorecards,
        comparison_to_baseline={
            "baseline_total_savings": round(baseline_total, 2),
            "scenario_total_savings": round(scenario_total, 2),
            "delta": round(delta, 2),
            "pct_change": round(pct_change, 1),
            "parameter_overrides_applied": scenario["parameter_overrides"],
        },
    )


@scenario_maint_router.delete("/custom/{scenario_id}", status_code=204)
async def delete_custom_scenario(scenario_id: str):
    """Delete a saved custom scenario."""
    removed = _custom_scenarios.pop(scenario_id, None)
    if removed is None:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")

    try:
        from ...persistence.database import get_session
        from ...persistence.models import SchemaMappingModel
        with get_session() as session:
            session.query(SchemaMappingModel).filter(
                SchemaMappingModel.mapping_id == scenario_id,
            ).update({"is_active": False})
            session.commit()
    except Exception as e:
        logger.debug("Scenario deletion persistence skipped: %s", e)
