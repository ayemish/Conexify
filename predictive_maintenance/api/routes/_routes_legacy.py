"""
PDM API Routes

REST API endpoints for the Predictive Maintenance system.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks, UploadFile, File, Form
from fastapi.security import APIKeyHeader

from ..schemas import (
    HealthResponse,
    ReadyResponse,
    TelemetryRequest,
    TelemetryBatchRequest,
    TelemetryResponse,
    AlertResponse,
    AlertListResponse,
    AlertAcknowledgeRequest,
    AlertDismissRequest,
    AlertResolveRequest,
    AlertFeedbackQuickRequest,
    FeedbackRequest,
    FeedbackResponse,
    AssetRequest,
    AssetResponse,
    AssetListResponse,
    SystemStatusResponse,
    DashboardResponse,
    DeploymentMetricsResponse,
    CalibrationMetricsResponse,
    QueryRequest,
    QueryResponse,
    QuerySource,
    ScenarioChatRequest,
    ScenarioChatResponse,
    ScenarioAgentInstruction,
    ScenarioAgentOutput,
    PersonaListResponse,
    PersonaResponse,
)

logger = logging.getLogger(__name__)

# API Key security (optional)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: Optional[str] = Depends(api_key_header)):
    """Verify API key if configured"""
    try:
        from ...config import settings
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
        from ...persistence.database import health_check as db_health
        db_ok = db_health()
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
    
    try:
        from ...integration.event_bus import RedisEventBus
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
_orchestrators: Dict[str, Any] = {}


def get_pdm_system(asset_id: str):
    """Get or create PDM system for an asset"""
    if asset_id not in _pdm_systems:
        from ...integration.advanced_system import create_pdm_system
        from ...config import settings
        session_factory = None
        if settings.persistence.enabled:
            try:
                from ...persistence.database import get_session_factory
                session_factory = get_session_factory()
            except Exception:
                session_factory = None
        _pdm_systems[asset_id] = create_pdm_system(
            asset_id,
            site_id=settings.site_id,
            session_factory=session_factory,
        )
    return _pdm_systems[asset_id]


def get_orchestrator(site_id: Optional[str] = None):
    """Get or create site-level orchestrator."""
    from ...config import settings
    effective_site = site_id or settings.site_id or "default"
    if effective_site not in _orchestrators:
        try:
            from ...agents.orchestrator import PDMModelOrchestrator
            _orchestrators[effective_site] = PDMModelOrchestrator(site_id=effective_site)
        except Exception as exc:  # pragma: no cover
            logger.warning("Orchestrator unavailable for site %s, falling back to kernel path: %s", effective_site, exc)
            _orchestrators[effective_site] = None
    return _orchestrators[effective_site]


def _to_orchestrator_input(request: TelemetryRequest):
    """Convert API telemetry request to orchestrator input type."""
    from ...agents.orchestrator import TelemetryInput
    from ...config import settings
    return TelemetryInput(
        timestamp=request.timestamp,
        asset_id=request.asset_id,
        site_id=request.site_id or settings.site_id or "default",
        compressor_on=request.compressor_on,
        compressor_current=request.compressor_current,
        compressor_power=request.compressor_power,
        evap_fan_on=request.evap_fan_on,
        condenser_fan_on=request.condenser_fan_on,
        supply_fan_speed=request.supply_fan_speed,
        suction_line_temp=request.suction_line_temp,
        discharge_temp=request.discharge_temp,
        supply_air_temp=request.supply_air_temp,
        return_air_temp=request.return_air_temp,
        ambient_temp=request.ambient_temp,
        suction_pressure=request.suction_pressure,
        discharge_pressure=request.discharge_pressure,
    )


def _normalize_fault_beliefs(beliefs: Optional[Dict[Any, Any]]) -> Dict[str, float]:
    normalized: Dict[str, float] = {}
    if not beliefs:
        return normalized
    for key, value in beliefs.items():
        k = key.value if hasattr(key, "value") else str(key)
        try:
            normalized[k] = float(value)
        except Exception:
            continue
    return normalized


def _build_alert_response(alert: Any, alert_type_override: Optional[str] = None, status: str = "active") -> AlertResponse:
    """Build API alert payload from kernel alert object."""
    return AlertResponse(
        alert_id=alert.alert_id,
        asset_id=alert.asset_id,
        alert_type=alert_type_override or (alert.alert_type.value if hasattr(alert.alert_type, "value") else str(alert.alert_type)),
        severity=alert.severity.value if hasattr(alert.severity, "value") else str(alert.severity),
        confidence=float(getattr(alert, "confidence", 0.0) or 0.0),
        false_alarm_probability=float(getattr(alert, "false_alarm_probability", 0.5) or 0.5),
        primary_fault=alert.primary_fault.value if getattr(alert, "primary_fault", None) else None,
        secondary_fault=alert.secondary_fault.value if getattr(alert, "secondary_fault", None) else None,
        fault_beliefs=_normalize_fault_beliefs(getattr(alert, "fault_beliefs", {})),
        evidence_summary=list(getattr(alert, "evidence_summary", []) or []),
        recommended_action=str(getattr(alert, "recommended_action", "") or ""),
        action_urgency=str(getattr(alert, "action_urgency", "monitor") or "monitor"),
        regime_at_detection=(
            alert.regime_at_detection.value
            if getattr(alert, "regime_at_detection", None) is not None and hasattr(alert.regime_at_detection, "value")
            else str(getattr(alert, "regime_at_detection", "unknown"))
        ),
        ambient_temp_at_detection=getattr(alert, "ambient_temp_at_detection", None),
        status=status,
        created_at=getattr(alert, "created_at", datetime.utcnow()),
        acknowledged_at=getattr(alert, "acknowledged_at", None),
        resolved_at=getattr(alert, "resolved_at", None),
    )


def _compute_decision_utilities(alert: Any, pdm_system: Any) -> Dict[str, float]:
    """Compute expected-utility scores for dispatch/review/wait choices.

    Delegates to :class:`DecisionUtilityService` which implements formal
    VoI routing, human–AI complementarity, and budget-state penalties.
    """
    from ...services.decision_utility_service import DecisionUtilityService

    budget = getattr(getattr(pdm_system, "decision_policy", None), "budget", None)
    if budget is None:
        return {"dispatch": 0.0, "review": 0.0, "wait": 0.0}

    svc = DecisionUtilityService.from_budget(budget)

    confidence = float(getattr(alert, "confidence", 0.0) or 0.0)
    fa_prob = float(getattr(alert, "false_alarm_probability", 0.5) or 0.5)
    p_fault = max(confidence, 1.0 - fa_prob)

    # Ensemble CI width from last context if available
    last_ctx = getattr(pdm_system, "last_context", {}) or {}
    ci_lower = float(last_ctx.get("ensemble_interval_lower", 0.0) or 0.0)
    ci_upper = float(last_ctx.get("ensemble_interval_upper", 0.0) or 0.0)
    ci_width = max(0.0, ci_upper - ci_lower)

    policy = getattr(pdm_system, "decision_policy", None)
    monthly_alerts = int(getattr(policy, "monthly_alerts", 0))
    monthly_nif = int(getattr(policy, "monthly_no_issue_found", 0))

    persistence_h = 0.0
    changes = getattr(pdm_system, "current_changes", {}) or {}
    for det in changes.values():
        h = float(getattr(det, "anomaly_duration_hours", 0.0) or 0.0)
        persistence_h = max(persistence_h, h)

    decision = svc.evaluate(
        p_fault=p_fault,
        fa_prob=fa_prob,
        ci_width=ci_width,
        monthly_alerts=monthly_alerts,
        monthly_nif=monthly_nif,
        persistence_hours=persistence_h,
    )

    return {
        "dispatch": decision.utilities.get("dispatch", _eu_zero()).expected_utility,
        "review": decision.utilities.get("human_review", _eu_zero()).expected_utility,
        "wait": decision.utilities.get("watch", _eu_zero()).expected_utility,
        "gather_data": decision.utilities.get("gather_data", _eu_zero()).expected_utility,
        "recommended_action": decision.recommended_action.value,
        "voi_review": decision.voi_review,
        "voi_gather": decision.voi_gather,
        "complementarity": decision.complementarity_score,
        "budget_headroom": decision.budget_headroom_frac,
    }


def _eu_zero():
    """Sentinel zero-utility object."""
    from ...services.decision_utility_service import ActionUtility, RoutingAction
    return ActionUtility(action=RoutingAction.WATCH, expected_utility=0.0)


def _should_queue_human_review(alert: Any, orchestrator_result: Any, pdm_system: Any, utilities: Dict[str, Any]) -> bool:
    """Route uncertain/high-consequence cases into human-review queue.

    Uses the formal ``DecisionUtilityService`` recommended action when
    available, with legacy heuristic fallbacks.
    """
    if orchestrator_result and getattr(orchestrator_result, "alert_type", None) == "human_review":
        return True

    if not alert:
        return False

    # Kernel-level NIF escalation: decision policy set urgency to human_review
    if getattr(alert, "action_urgency", None) == "human_review":
        return True

    current_alert_type = (
        alert.alert_type.value if hasattr(getattr(alert, "alert_type", None), "value") else str(getattr(alert, "alert_type", ""))
    )
    if current_alert_type != "actionable":
        return False

    # Formal utility-service recommendation (preferred path)
    recommended = utilities.get("recommended_action")
    if recommended == "human_review":
        return True

    budget = getattr(getattr(pdm_system, "decision_policy", None), "budget", None)
    if budget is None:
        return False

    # Legacy heuristic fallbacks
    confidence = float(getattr(alert, "confidence", 0.0) or 0.0)
    fa_prob = float(getattr(alert, "false_alarm_probability", 1.0) or 1.0)
    u_dispatch = float(utilities.get("dispatch", 0.0))
    u_review = float(utilities.get("review", 0.0))
    u_wait = float(utilities.get("wait", 0.0))
    utility_gap = u_dispatch - max(u_review, u_wait)

    if fa_prob >= float(budget.max_false_alarm_probability) * 0.75:
        return True
    if confidence <= float(budget.min_confidence_for_actionable) + 0.05:
        return True
    if utility_gap <= 0:
        return True
    return False


async def _enqueue_human_review(alert: Any, request: TelemetryRequest, orchestrator_result: Any, utilities: Dict[str, float]):
    """Create/queue a human-review item for uncertain actionable decisions."""
    from ...autopilot.approval_queue.routes import queue_service
    from ...autopilot.approval_queue.models import QueueItemStatus

    # Avoid repeated pending items for same alert.
    try:
        existing_items = queue_service.get_queue(tenant_id="default", limit=200, offset=0)
        for item in existing_items:
            evidence = item.evidence or {}
            if evidence.get("alert_id") == alert.alert_id and item.status in {
                QueueItemStatus.PENDING, QueueItemStatus.READY, QueueItemStatus.IN_REVIEW
            }:
                return
    except Exception:
        pass

    severity = str(getattr(alert.severity, "value", getattr(alert, "severity", "medium")))
    risk_tier = "HIGH" if severity in ("high", "critical") else "MEDIUM"
    queue_reason = (
        "orchestrator_human_review"
        if getattr(orchestrator_result, "alert_type", None) == "human_review"
        else "uncertainty_risk_policy"
    )
    await queue_service.add_item(
        approval_id=f"APR-{uuid.uuid4().hex[:12].upper()}",
        run_id=f"RUN-HR-{uuid.uuid4().hex[:10].upper()}",
        incident_id=f"INC-HR-{uuid.uuid4().hex[:10].upper()}",
        playbook_id="human_review_triage",
        step_id="review_alert",
        tenant_id="default",
        site_id=request.site_id or "default",
        asset_id=request.asset_id,
        item_type="action_approval",
        risk_tier=risk_tier,
        proposed_actions=[{
            "action": "human_review",
            "recommended_action": getattr(alert, "recommended_action", ""),
            "reason": queue_reason,
        }],
        action_summary=f"Human review required for alert {alert.alert_id} on asset {request.asset_id}",
        telemetry_snapshot=request.dict(exclude_none=True),
        fault_context={
            "primary_fault": getattr(getattr(alert, "primary_fault", None), "value", None),
            "confidence": float(getattr(alert, "confidence", 0.0) or 0.0),
            "false_alarm_probability": float(getattr(alert, "false_alarm_probability", 0.5) or 0.5),
            "orchestrator_alert_type": getattr(orchestrator_result, "alert_type", None),
        },
        evidence={
            "alert_id": alert.alert_id,
            "queue_reason": queue_reason,
            "decision_utilities": utilities,
            "kernel_artifact_id": getattr(orchestrator_result, "kernel_artifact_id", None),
        },
        priority=80 if risk_tier == "HIGH" else 65,
    )


def get_rag():
    """Get shared RAG interface used by both advisor and query routes."""
    try:
        from ...services.advisor import get_shared_advisor
        advisor = get_shared_advisor()
        return advisor.rag
    except Exception:
        # Fallback path if advisor initialization fails
        from ...config import settings
        session_factory = None
        if settings.persistence.enabled:
            try:
                from ...persistence.database import get_session_factory
                session_factory = get_session_factory()
            except Exception:
                session_factory = None
        from ...services.rag_service import get_rag_service
        return get_rag_service(session_factory)


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
        telemetry_input = _to_orchestrator_input(request)
        orchestrator_result = None
        pdm = None
        alert = None

        orchestrator = get_orchestrator(telemetry_input.site_id)
        if orchestrator is not None:
            try:
                orchestrator_result = orchestrator.process_telemetry(telemetry_input)
                try:
                    # Reuse orchestrator's kernel instance to avoid double-processing telemetry.
                    pdm = orchestrator._get_kernel_system(request.asset_id)  # noqa: SLF001
                except Exception:
                    pdm = get_pdm_system(request.asset_id)
                alert = getattr(pdm, "current_alert", None)
            except Exception as orchestrator_exc:
                logger.warning("Orchestrator telemetry path failed; using kernel fallback: %s", orchestrator_exc)
                orchestrator_result = None

        if pdm is None:
            pdm = get_pdm_system(request.asset_id)
            alert = pdm.process_telemetry(request.dict(exclude_none=True))

        alert_response = None
        if alert:
            final_alert_type = getattr(orchestrator_result, "alert_type", None)
            if final_alert_type is None and getattr(alert, "alert_type", None) is not None:
                final_alert_type = alert.alert_type.value if hasattr(alert.alert_type, "value") else str(alert.alert_type)

            decision_utilities = _compute_decision_utilities(alert, pdm)
            queue_for_human = _should_queue_human_review(
                alert=alert,
                orchestrator_result=orchestrator_result,
                pdm_system=pdm,
                utilities=decision_utilities,
            )
            if queue_for_human:
                await _enqueue_human_review(alert, request, orchestrator_result, decision_utilities)
                final_alert_type = "human_review"

            if final_alert_type != "watch":
                status = "pending_review" if final_alert_type == "human_review" else "active"
                alert_response = _build_alert_response(
                    alert,
                    alert_type_override=final_alert_type,
                    status=status,
                )
        
        # Get sensor trust summary
        trust_summary = {}
        for sensor_id, trust in getattr(pdm, "current_trust_scores", {}).items():
            trust_summary[sensor_id] = float(getattr(trust, "trust_score", 0.0))
        if not trust_summary:
            trust_summary["min_trust"] = float(getattr(orchestrator_result, "sensor_trust", 1.0))
        
        # Background: persist telemetry
        regime_value = (
            pdm.current_regime.value
            if hasattr(getattr(pdm, "current_regime", None), "value")
            else str(getattr(pdm, "current_regime", "unknown"))
        )
        background_tasks.add_task(persist_telemetry, request, regime_value)
        
        return TelemetryResponse(
            asset_id=request.asset_id,
            timestamp=request.timestamp,
            regime=(
                pdm.current_regime.value
                if hasattr(getattr(pdm, "current_regime", None), "value")
                else str(getattr(orchestrator_result, "regime", "unknown"))
            ),
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
            telemetry_input = _to_orchestrator_input(reading)
            orchestrator_result = None
            pdm = None
            alert = None

            orchestrator = get_orchestrator(telemetry_input.site_id)
            if orchestrator is not None:
                try:
                    orchestrator_result = orchestrator.process_telemetry(telemetry_input)
                    try:
                        pdm = orchestrator._get_kernel_system(reading.asset_id)  # noqa: SLF001
                    except Exception:
                        pdm = get_pdm_system(reading.asset_id)
                    alert = getattr(pdm, "current_alert", None)
                except Exception as orchestrator_exc:
                    logger.warning(
                        "Orchestrator telemetry batch path failed for asset %s; using kernel fallback: %s",
                        reading.asset_id,
                        orchestrator_exc,
                    )
                    orchestrator_result = None

            if pdm is None:
                pdm = get_pdm_system(reading.asset_id)
                alert = pdm.process_telemetry(reading.dict(exclude_none=True))

            has_alert = False
            if alert is not None:
                final_alert_type = getattr(orchestrator_result, "alert_type", None)
                if final_alert_type is None and getattr(alert, "alert_type", None) is not None:
                    final_alert_type = alert.alert_type.value if hasattr(alert.alert_type, "value") else str(alert.alert_type)
                decision_utilities = _compute_decision_utilities(alert, pdm)
                queue_for_human = _should_queue_human_review(
                    alert=alert,
                    orchestrator_result=orchestrator_result,
                    pdm_system=pdm,
                    utilities=decision_utilities,
                )
                if queue_for_human:
                    await _enqueue_human_review(alert, reading, orchestrator_result, decision_utilities)
                    final_alert_type = "human_review"
                has_alert = final_alert_type in {"actionable", "action", "dispatch", "human_review"}

            results.append({
                "asset_id": reading.asset_id,
                "timestamp": reading.timestamp.isoformat(),
                "processed": True,
                "has_alert": has_alert,
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
        from ...persistence.database import get_session
        from ...persistence.repositories import TelemetryRepository, AssetRepository
        
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
    status: Optional[str] = None,
    active: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    api_key: str = Depends(verify_api_key)
):
    """List alerts with filtering.

    ``active=true`` is a convenience alias that filters to non-terminal
    statuses (i.e. excludes resolved, dismissed, suppressed, expired).
    """
    _TERMINAL_STATUSES = {"resolved", "dismissed", "suppressed", "expired"}

    # Normalise: ``?active=true`` → status="active"
    effective_status = status
    if active is True and not effective_status:
        effective_status = "active"
    if effective_status is None:
        effective_status = "active"

    try:
        from ...persistence.database import get_session
        from ...persistence.repositories import AlertRepository
        from ...persistence.models import AlertModel
        
        with get_session() as session:
            repo = AlertRepository(session)
            query = session.query(AlertModel)
            if asset_id:
                query = query.filter(AlertModel.asset_id == asset_id)
            if alert_type:
                query = query.filter(AlertModel.alert_type == alert_type)
            if effective_status and effective_status.lower() == "active":
                query = query.filter(AlertModel.status.notin_(_TERMINAL_STATUSES))
            elif effective_status and effective_status.lower() != "all":
                query = query.filter(AlertModel.status == effective_status)

            total = query.count()
            alerts = (
                query.order_by(AlertModel.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            
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
                total=total,
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
        from ...persistence.database import get_session
        from ...persistence.repositories import AlertRepository
        
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
    request: Optional[AlertAcknowledgeRequest] = None,
    api_key: str = Depends(verify_api_key)
):
    """Acknowledge an alert"""
    try:
        from ...persistence.database import get_session
        from ...persistence.repositories import AlertRepository
        
        with get_session() as session:
            repo = AlertRepository(session)
            acknowledged_by = request.acknowledged_by if request else "operator_ui"
            repo.acknowledge(alert_id, acknowledged_by)
            
        return {"status": "acknowledged", "alert_id": alert_id}
    except Exception as e:
        logger.error(f"Error acknowledging alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@alerts_router.post("/{alert_id}/dismiss")
async def dismiss_alert(
    alert_id: str,
    request: Optional[AlertDismissRequest] = None,
    api_key: str = Depends(verify_api_key)
):
    """Dismiss/suppress an alert."""
    try:
        from ...persistence.database import get_session
        from ...persistence.repositories import AlertRepository

        with get_session() as session:
            repo = AlertRepository(session)
            dismissed_by = request.dismissed_by if request else "operator_ui"
            notes = request.notes if request else "dismissed"
            repo.dismiss(alert_id, dismissed_by, notes)

        return {"status": "dismissed", "alert_id": alert_id}
    except Exception as e:
        logger.error(f"Error dismissing alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@alerts_router.post("/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    request: AlertResolveRequest,
    api_key: str = Depends(verify_api_key)
):
    """Resolve an alert"""
    try:
        from ...persistence.database import get_session
        from ...persistence.repositories import AlertRepository
        
        with get_session() as session:
            repo = AlertRepository(session)
            repo.resolve(alert_id, request.resolved_by, request.resolution_notes)
            
        return {"status": "resolved", "alert_id": alert_id}
    except Exception as e:
        logger.error(f"Error resolving alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@alerts_router.post("/{alert_id}/feedback", response_model=FeedbackResponse)
async def submit_alert_feedback(
    alert_id: str,
    request: AlertFeedbackQuickRequest,
    api_key: str = Depends(verify_api_key)
):
    """Backward-compatible feedback endpoint under /alerts/{id}/feedback."""
    outcome = request.outcome
    if outcome is None and request.helpful is not None:
        outcome = "confirmed_fault" if request.helpful else "no_issue_found"
    if outcome is None:
        outcome = "pending"

    feedback_request = FeedbackRequest(
        alert_id=alert_id,
        outcome=outcome,
        confirmed_fault_type=request.confirmed_fault_type,
        notes=request.notes,
        feedback_by=request.feedback_by or "operator_ui",
    )
    return await submit_feedback(feedback_request, api_key=api_key)


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
        from ...persistence.database import get_session
        from ...persistence.repositories import AssetRepository
        
        with get_session() as session:
            repo = AssetRepository(session)
            
            if site_id:
                assets = repo.get_by_site(site_id, active_only)
            else:
                query = session.query(repo.session.query.__self__)
                if active_only:
                    from ...persistence.models import AssetModel
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
        from ...persistence.database import get_session
        from ...persistence.repositories import AssetRepository
        
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
        from ...persistence.database import get_session
        from ...persistence.repositories import AssetRepository
        
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
        from ...persistence.database import get_session
        from ...persistence.repositories import FeedbackRepository, AlertRepository
        
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
                try:
                    orchestrator = get_orchestrator(getattr(alert, "site_id", None))
                    pdm = orchestrator._get_kernel_system(alert.asset_id)  # noqa: SLF001
                except Exception:
                    pdm = get_pdm_system(alert.asset_id)
                from ...core.schemas import FeedbackOutcome, FaultType
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
        from ...persistence.database import get_session
        from ...persistence.repositories import FeedbackRepository
        
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


# =============================================================================
# Query / RAG Routes
# =============================================================================

query_router = APIRouter()


@query_router.post("", response_model=QueryResponse)
async def query_rag(
    request: QueryRequest,
    api_key: str = Depends(verify_api_key)
):
    """Query indexed agent summaries and digital twin snapshots."""
    try:
        rag = get_rag()
        results = rag.search(
            query=request.query,
            asset_id=request.asset_id,
            site_id=request.site_id,
            top_k=request.top_k,
        )
        answer = rag.answer(request.query, results)
        sources = [
            QuerySource(
                doc_id=r.doc_id,
                doc_type=r.doc_type,
                score=r.score,
                snippet=r.content[:400],
                asset_id=r.asset_id,
                site_id=r.site_id,
                metadata=r.metadata or {},
            )
            for r in results
        ]
        return QueryResponse(query=request.query, answer=answer, sources=sources)
    except Exception as e:
        logger.error(f"Error querying RAG: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@query_router.post("/voice", response_model=QueryResponse)
async def query_rag_voice(
    audio: UploadFile = File(...),
    asset_id: Optional[str] = Form(None),
    site_id: Optional[str] = Form(None),
    top_k: int = Form(5),
    api_key: str = Depends(verify_api_key)
):
    """Voice query using Whisper transcription + RAG."""
    try:
        rag = get_rag()
        transcription = rag.transcribe_audio(audio.file)
        results = rag.search(
            query=transcription,
            asset_id=asset_id,
            site_id=site_id,
            top_k=top_k,
        )
        answer = rag.answer(transcription, results)
        sources = [
            QuerySource(
                doc_id=r.doc_id,
                doc_type=r.doc_type,
                score=r.score,
                snippet=r.content[:400],
                asset_id=r.asset_id,
                site_id=r.site_id,
                metadata=r.metadata or {},
            )
            for r in results
        ]
        return QueryResponse(
            query=transcription,
            answer=answer,
            sources=sources,
            transcription=transcription,
        )
    except Exception as e:
        logger.error(f"Error querying RAG (voice): {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Scenario Chat Routes
# =============================================================================

scenario_router = APIRouter()


@scenario_router.get("/personas", response_model=PersonaListResponse)
async def get_personas(
    api_key: str = Depends(verify_api_key)
):
    """List available chat personas."""
    try:
        from ...services.scenario_service import get_scenario_service
        service = get_scenario_service()
        personas = [
            PersonaResponse(
                id=p["id"],
                name=p["name"],
                tagline=p["tagline"],
                prompt=p["prompt"],
            )
            for p in service.get_personas()
        ]
        return PersonaListResponse(personas=personas)
    except Exception as e:
        logger.error(f"Error listing personas: {e}")
        raise HTTPException(status_code=500, detail=str(e))




@scenario_router.post("/chat", response_model=ScenarioChatResponse)
async def scenario_chat(
    request: ScenarioChatRequest,
    api_key: str = Depends(verify_api_key)
):
    """Persona-driven scenario chat."""
    try:
        from ...services.scenario_service import get_scenario_service
        service = get_scenario_service()
        result = service.run_scenario(
            persona_id=request.persona_id,
            persona_prompt=request.persona_prompt,
            user_message=request.message,
            budget=request.marketing_budget,
            risk=request.risk_level,
            payback=request.payback_timeline,
            scope=request.scope,
        )
        return ScenarioChatResponse(
            persona_id=result.persona_id,
            instructions=[
                ScenarioAgentInstruction(
                    agent_id=i.agent_id,
                    title=i.title,
                    instruction=i.instruction,
                )
                for i in result.instructions
            ],
            outputs=[
                ScenarioAgentOutput(
                    agent_id=o["agent_id"],
                    title=o["title"],
                    summary=o["summary"],
                )
                for o in result.outputs
            ],
            created_at=result.created_at,
        )
    except Exception as e:
        logger.error(f"Error running scenario chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))
