"""
PDM API Routes

REST API endpoints for the Predictive Maintenance system.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from fastapi.security import APIKeyHeader

from .schemas import (
    HealthResponse,
    ReadyResponse,
    TelemetryRequest,
    TelemetryBatchRequest,
    TelemetryResponse,
    AlertResponse,
    AlertListResponse,
    AlertAcknowledgeRequest,
    AlertResolveRequest,
    FeedbackRequest,
    FeedbackResponse,
    AssetRequest,
    AssetResponse,
    AssetListResponse,
    SystemStatusResponse,
    DashboardResponse,
    DeploymentMetricsResponse,
    CalibrationMetricsResponse,
)

logger = logging.getLogger(__name__)

# API Key security (optional)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: Optional[str] = Depends(api_key_header)):
    """Verify API key if configured"""
    try:
        from ..config import settings
        if settings.api.api_keys and api_key not in settings.api.api_keys:
            raise HTTPException(status_code=401, detail="Invalid API key")
    except ImportError:
        pass  # Config not available, skip auth
    return api_key


# =============================================================================
# Health Routes
# =============================================================================

health_router = APIRouter()


@health_router.get("/health", response_model=HealthResponse)
async def health_check():
    """Basic health check endpoint"""
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        timestamp=datetime.utcnow(),
        checks={"api": True}
    )


@health_router.get("/ready", response_model=ReadyResponse)
async def readiness_check():
    """Readiness check including dependencies"""
    db_ok = False
    redis_ok = False
    
    try:
        from ..persistence.database import health_check as db_health
        db_ok = db_health()
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
    
    try:
        from ..integration.event_bus import RedisEventBus
        bus = RedisEventBus()
        redis_ok = bus.health_check()
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
    
    ready = db_ok  # Minimum requirement
    message = "Ready" if ready else "Not ready - database unavailable"
    
    return ReadyResponse(
        ready=ready,
        database=db_ok,
        redis=redis_ok,
        message=message
    )


@health_router.get("/live")
async def liveness_check():
    """Simple liveness probe"""
    return {"status": "alive"}


# =============================================================================
# Telemetry Routes
# =============================================================================

telemetry_router = APIRouter()

# In-memory PDM systems cache (per-asset)
_pdm_systems: Dict[str, Any] = {}


def get_pdm_system(asset_id: str):
    """Get or create PDM system for an asset"""
    if asset_id not in _pdm_systems:
        from ..integration.advanced_system import create_pdm_system
        from ..config import settings
        session_factory = None
        if settings.persistence.enabled:
            try:
                from ..persistence.database import get_session_factory
                session_factory = get_session_factory()
            except Exception:
                session_factory = None
        _pdm_systems[asset_id] = create_pdm_system(
            asset_id,
            site_id=settings.site_id,
            session_factory=session_factory,
        )
    return _pdm_systems[asset_id]


@telemetry_router.post("", response_model=TelemetryResponse)
async def process_telemetry(
    request: TelemetryRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    """
    Process a single telemetry reading.
    
    This is the main entry point for telemetry data. Each reading is:
    1. Validated
    2. Processed through the PDM pipeline (regime detection, sensor trust, etc.)
    3. Stored in the database (async)
    4. Returns current alert status
    """
    try:
        pdm = get_pdm_system(request.asset_id)
        
        # Convert to dict for processing
        telemetry_dict = request.dict(exclude_none=True)
        
        # Process through PDM system
        alert = pdm.process_telemetry(telemetry_dict)
        
        # Build response
        alert_response = None
        if alert and alert.alert_type.value != "watch":
            alert_response = AlertResponse(
                alert_id=alert.alert_id,
                asset_id=alert.asset_id,
                alert_type=alert.alert_type.value,
                severity=alert.severity.value,
                confidence=alert.confidence,
                false_alarm_probability=alert.false_alarm_probability,
                primary_fault=alert.primary_fault.value if alert.primary_fault else None,
                secondary_fault=alert.secondary_fault.value if alert.secondary_fault else None,
                fault_beliefs={k.value: v for k, v in alert.fault_beliefs.items()},
                evidence_summary=list(alert.evidence_summary),
                recommended_action=alert.recommended_action,
                action_urgency=alert.action_urgency,
                regime_at_detection=alert.regime_at_detection.value,
                ambient_temp_at_detection=alert.ambient_temp_at_detection,
                status="active",
                created_at=alert.created_at,
            )
        
        # Get sensor trust summary
        trust_summary = {}
        for sensor_id, trust in pdm.current_trust_scores.items():
            trust_summary[sensor_id] = trust.trust_score
        
        # Background: persist telemetry
        background_tasks.add_task(persist_telemetry, request, pdm.current_regime.value)
        
        return TelemetryResponse(
            asset_id=request.asset_id,
            timestamp=request.timestamp,
            regime=pdm.current_regime.value,
            regime_confidence=0.9,  # From regime service
            sensor_trust_summary=trust_summary,
            alert=alert_response,
            processed=True,
        )
        
    except Exception as e:
        logger.error(f"Error processing telemetry: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@telemetry_router.post("/batch", response_model=Dict[str, Any])
async def process_telemetry_batch(
    request: TelemetryBatchRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    """Process a batch of telemetry readings"""
    results = []
    errors = []
    
    for reading in request.readings:
        try:
            pdm = get_pdm_system(reading.asset_id)
            telemetry_dict = reading.dict(exclude_none=True)
            alert = pdm.process_telemetry(telemetry_dict)
            results.append({
                "asset_id": reading.asset_id,
                "timestamp": reading.timestamp.isoformat(),
                "processed": True,
                "has_alert": alert is not None and alert.alert_type.value == "actionable"
            })
        except Exception as e:
            errors.append({
                "asset_id": reading.asset_id,
                "timestamp": reading.timestamp.isoformat(),
                "error": str(e)
            })
    
    return {
        "processed": len(results),
        "errors": len(errors),
        "results": results,
        "error_details": errors if errors else None
    }


async def persist_telemetry(request: TelemetryRequest, regime: str):
    """Background task to persist telemetry"""
    try:
        from ..persistence.database import get_session
        from ..persistence.repositories import TelemetryRepository, AssetRepository
        
        with get_session() as session:
            # Ensure asset exists
            asset_repo = AssetRepository(session)
            if not asset_repo.get_by_id(request.asset_id):
                asset_repo.create(
                    asset_id=request.asset_id,
                    site_id=request.site_id or "default"
                )
            
            # Store telemetry
            telemetry_repo = TelemetryRepository(session)
            telemetry_repo.create(
                asset_id=request.asset_id,
                timestamp=request.timestamp,
                regime=regime,
                **request.dict(exclude={"asset_id", "timestamp", "site_id", "extra_data"})
            )
            asset_repo.update_last_telemetry(request.asset_id, request.timestamp)
    except Exception as e:
        logger.error(f"Failed to persist telemetry: {e}")


# =============================================================================
# Alerts Routes
# =============================================================================

alerts_router = APIRouter()


@alerts_router.get("", response_model=AlertListResponse)
async def list_alerts(
    asset_id: Optional[str] = None,
    alert_type: Optional[str] = None,
    status: str = "active",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    api_key: str = Depends(verify_api_key)
):
    """List alerts with filtering"""
    try:
        from ..persistence.database import get_session
        from ..persistence.repositories import AlertRepository
        
        with get_session() as session:
            repo = AlertRepository(session)
            
            if asset_id:
                alerts = repo.get_active(asset_id)
            else:
                # Get all recent alerts
                alerts = session.query(repo.session.query.__self__).limit(page_size).all()
            
            alert_responses = [
                AlertResponse(
                    alert_id=a.alert_id,
                    asset_id=a.asset_id,
                    alert_type=a.alert_type,
                    severity=a.severity,
                    confidence=a.confidence or 0.5,
                    false_alarm_probability=a.false_alarm_probability or 0.5,
                    primary_fault=a.primary_fault,
                    secondary_fault=a.secondary_fault,
                    fault_beliefs=a.fault_beliefs or {},
                    evidence_summary=a.evidence_summary or [],
                    recommended_action=a.recommended_action or "",
                    action_urgency=a.action_urgency or "monitor",
                    regime_at_detection=a.regime_at_detection or "unknown",
                    status=a.status,
                    created_at=a.created_at,
                    acknowledged_at=a.acknowledged_at,
                    resolved_at=a.resolved_at,
                )
                for a in alerts
            ]
            
            return AlertListResponse(
                alerts=alert_responses,
                total=len(alert_responses),
                page=page,
                page_size=page_size
            )
    except Exception as e:
        logger.error(f"Error listing alerts: {e}")
        return AlertListResponse(alerts=[], total=0, page=page, page_size=page_size)


@alerts_router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: str, api_key: str = Depends(verify_api_key)):
    """Get a specific alert"""
    try:
        from ..persistence.database import get_session
        from ..persistence.repositories import AlertRepository
        
        with get_session() as session:
            repo = AlertRepository(session)
            alert = repo.get_by_id(alert_id)
            
            if not alert:
                raise HTTPException(status_code=404, detail="Alert not found")
            
            return AlertResponse(
                alert_id=alert.alert_id,
                asset_id=alert.asset_id,
                alert_type=alert.alert_type,
                severity=alert.severity,
                confidence=alert.confidence or 0.5,
                false_alarm_probability=alert.false_alarm_probability or 0.5,
                primary_fault=alert.primary_fault,
                secondary_fault=alert.secondary_fault,
                fault_beliefs=alert.fault_beliefs or {},
                evidence_summary=alert.evidence_summary or [],
                recommended_action=alert.recommended_action or "",
                action_urgency=alert.action_urgency or "monitor",
                regime_at_detection=alert.regime_at_detection or "unknown",
                status=alert.status,
                created_at=alert.created_at,
                acknowledged_at=alert.acknowledged_at,
                resolved_at=alert.resolved_at,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@alerts_router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    request: AlertAcknowledgeRequest,
    api_key: str = Depends(verify_api_key)
):
    """Acknowledge an alert"""
    try:
        from ..persistence.database import get_session
        from ..persistence.repositories import AlertRepository
        
        with get_session() as session:
            repo = AlertRepository(session)
            repo.acknowledge(alert_id, request.acknowledged_by)
            
        return {"status": "acknowledged", "alert_id": alert_id}
    except Exception as e:
        logger.error(f"Error acknowledging alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@alerts_router.post("/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    request: AlertResolveRequest,
    api_key: str = Depends(verify_api_key)
):
    """Resolve an alert"""
    try:
        from ..persistence.database import get_session
        from ..persistence.repositories import AlertRepository
        
        with get_session() as session:
            repo = AlertRepository(session)
            repo.resolve(alert_id, request.resolved_by, request.resolution_notes)
            
        return {"status": "resolved", "alert_id": alert_id}
    except Exception as e:
        logger.error(f"Error resolving alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Assets Routes
# =============================================================================

assets_router = APIRouter()


@assets_router.get("", response_model=AssetListResponse)
async def list_assets(
    site_id: Optional[str] = None,
    active_only: bool = True,
    api_key: str = Depends(verify_api_key)
):
    """List assets"""
    try:
        from ..persistence.database import get_session
        from ..persistence.repositories import AssetRepository
        
        with get_session() as session:
            repo = AssetRepository(session)
            
            if site_id:
                assets = repo.get_by_site(site_id, active_only)
            else:
                query = session.query(repo.session.query.__self__)
                if active_only:
                    from ..persistence.models import AssetModel
                    query = session.query(AssetModel).filter(AssetModel.is_active == True)
                assets = query.limit(1000).all()
            
            asset_responses = [
                AssetResponse(
                    asset_id=a.asset_id,
                    site_id=a.site_id,
                    asset_type=a.asset_type,
                    manufacturer=a.manufacturer,
                    model_number=a.model_number,
                    is_active=a.is_active,
                    last_telemetry_at=a.last_telemetry_at,
                    created_at=a.created_at,
                )
                for a in assets
            ]
            
            return AssetListResponse(assets=asset_responses, total=len(asset_responses))
    except Exception as e:
        logger.error(f"Error listing assets: {e}")
        return AssetListResponse(assets=[], total=0)


@assets_router.post("", response_model=AssetResponse)
async def create_asset(
    request: AssetRequest,
    api_key: str = Depends(verify_api_key)
):
    """Create or update an asset"""
    try:
        from ..persistence.database import get_session
        from ..persistence.repositories import AssetRepository
        
        with get_session() as session:
            repo = AssetRepository(session)
            
            existing = repo.get_by_id(request.asset_id)
            if existing:
                # Update existing
                for key, value in request.dict(exclude_none=True).items():
                    setattr(existing, key, value)
                asset = existing
            else:
                asset = repo.create(**request.dict(exclude_none=True))
            
            return AssetResponse(
                asset_id=asset.asset_id,
                site_id=asset.site_id,
                asset_type=asset.asset_type,
                manufacturer=asset.manufacturer,
                model_number=asset.model_number,
                is_active=asset.is_active,
                last_telemetry_at=asset.last_telemetry_at,
                created_at=asset.created_at,
            )
    except Exception as e:
        logger.error(f"Error creating asset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@assets_router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(asset_id: str, api_key: str = Depends(verify_api_key)):
    """Get asset details"""
    try:
        from ..persistence.database import get_session
        from ..persistence.repositories import AssetRepository
        
        with get_session() as session:
            repo = AssetRepository(session)
            asset = repo.get_by_id(asset_id)
            
            if not asset:
                raise HTTPException(status_code=404, detail="Asset not found")
            
            return AssetResponse(
                asset_id=asset.asset_id,
                site_id=asset.site_id,
                asset_type=asset.asset_type,
                manufacturer=asset.manufacturer,
                model_number=asset.model_number,
                is_active=asset.is_active,
                last_telemetry_at=asset.last_telemetry_at,
                created_at=asset.created_at,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting asset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@assets_router.get("/{asset_id}/status", response_model=SystemStatusResponse)
async def get_asset_status(asset_id: str, api_key: str = Depends(verify_api_key)):
    """Get detailed system status for an asset"""
    try:
        pdm = get_pdm_system(asset_id)
        status = pdm.get_system_status()
        
        return SystemStatusResponse(**status)
    except Exception as e:
        logger.error(f"Error getting asset status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@assets_router.get("/{asset_id}/dashboard", response_model=DashboardResponse)
async def get_asset_dashboard(asset_id: str, api_key: str = Depends(verify_api_key)):
    """Get operator dashboard for an asset"""
    try:
        pdm = get_pdm_system(asset_id)
        dashboard = pdm.get_operator_dashboard()
        
        return DashboardResponse(**dashboard)
    except Exception as e:
        logger.error(f"Error getting dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Feedback Routes
# =============================================================================

feedback_router = APIRouter()


@feedback_router.post("", response_model=FeedbackResponse)
async def submit_feedback(
    request: FeedbackRequest,
    api_key: str = Depends(verify_api_key)
):
    """Submit feedback for an alert"""
    try:
        from ..persistence.database import get_session
        from ..persistence.repositories import FeedbackRepository, AlertRepository
        
        with get_session() as session:
            alert_repo = AlertRepository(session)
            alert = alert_repo.get_by_id(request.alert_id)
            
            if not alert:
                raise HTTPException(status_code=404, detail="Alert not found")
            
            # Record feedback
            feedback_repo = FeedbackRepository(session)
            feedback = feedback_repo.create(
                alert_id=request.alert_id,
                asset_id=alert.asset_id,
                outcome=request.outcome,
                confirmed_fault_type=request.confirmed_fault_type,
                notes=request.notes,
                feedback_by=request.feedback_by,
            )
            
            # Update alert
            alert_repo.add_feedback(request.alert_id, request.outcome, request.notes)
            
            # Trigger PDM system feedback recording
            try:
                pdm = get_pdm_system(alert.asset_id)
                from ..core.schemas import FeedbackOutcome, FaultType
                outcome_enum = FeedbackOutcome(request.outcome)
                fault_enum = FaultType(request.confirmed_fault_type) if request.confirmed_fault_type else None
                pdm.record_feedback(request.alert_id, outcome_enum, fault_enum, request.notes)
            except Exception as e:
                logger.warning(f"Could not update PDM system with feedback: {e}")
            
            return FeedbackResponse(
                feedback_id=str(feedback.id),
                alert_id=request.alert_id,
                outcome=request.outcome,
                recorded_at=datetime.utcnow()
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Metrics Routes
# =============================================================================

metrics_router = APIRouter()


@metrics_router.get("/deployment", response_model=DeploymentMetricsResponse)
async def get_deployment_metrics(
    asset_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    api_key: str = Depends(verify_api_key)
):
    """Get deployment metrics"""
    try:
        period_end = datetime.utcnow()
        period_start = period_end - timedelta(days=days)
        
        if asset_id:
            pdm = get_pdm_system(asset_id)
            metrics = pdm.get_deployment_metrics(period_start, period_end)
            
            return DeploymentMetricsResponse(
                period_start=metrics.period_start,
                period_end=metrics.period_end,
                total_alarms=metrics.total_alarms,
                actionable_alarms=metrics.actionable_alarms,
                watch_alarms=metrics.watch_alarms,
                sensor_alerts=metrics.sensor_alerts,
                alarms_per_unit_per_month=metrics.alarms_per_unit_per_month,
                actionable_per_unit_per_month=metrics.actionable_per_unit_per_month,
                no_issue_found_rate=metrics.no_issue_found_rate,
                lead_time_hours_mean=metrics.lead_time_hours_mean,
                lead_time_hours_p50=metrics.lead_time_hours_p50,
                lead_time_hours_p90=metrics.lead_time_hours_p90,
                lead_time_hours_p95=metrics.lead_time_hours_p95,
                lead_time_hours_min=metrics.lead_time_hours_min,
                lead_time_hours_max=metrics.lead_time_hours_max,
                lead_time_hours_histogram=metrics.lead_time_hours_histogram,
                precision_at_k=metrics.precision_at_k,
            )
        else:
            # Aggregate metrics (placeholder)
            return DeploymentMetricsResponse(
                period_start=period_start,
                period_end=period_end,
                total_alarms=0,
                actionable_alarms=0,
                watch_alarms=0,
                sensor_alerts=0,
                alarms_per_unit_per_month=0.0,
                actionable_per_unit_per_month=0.0,
                no_issue_found_rate=0.0,
                lead_time_hours_histogram={},
                precision_at_k={},
            )
    except Exception as e:
        logger.error(f"Error getting deployment metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@metrics_router.get("/calibration", response_model=CalibrationMetricsResponse)
async def get_calibration_metrics(
    asset_id: Optional[str] = None,
    api_key: str = Depends(verify_api_key)
):
    """Get calibration metrics"""
    try:
        from ..persistence.database import get_session
        from ..persistence.repositories import FeedbackRepository
        
        with get_session() as session:
            repo = FeedbackRepository(session)
            counts = repo.count_by_outcome(asset_id)
            
            return CalibrationMetricsResponse(
                total_feedback_records=sum(counts.values()),
                feedback_by_outcome=counts,
                calibration_curve={},
                last_calibration=None
            )
    except Exception as e:
        logger.error(f"Error getting calibration metrics: {e}")
        return CalibrationMetricsResponse(
            total_feedback_records=0,
            feedback_by_outcome={},
            calibration_curve={},
            last_calibration=None
        )
