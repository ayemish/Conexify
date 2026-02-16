"""FastAPI routes for AI-driven Work Order Management.

Endpoints:
- POST /api/v1/workorders/interpret      — NL text → structured WO draft (LLM)
- POST /api/v1/workorders/auto-create    — PdM signals → autonomous WO (LLM)
- POST /api/v1/workorders/prioritize     — AI impact assessment & triage (LLM)
- POST /api/v1/workorders/match          — Intelligent provider matching (LLM)
- POST /api/v1/workorders/recommend-cost — Cost & approval recommendation (LLM)
- POST /api/v1/workorders/verify         — Post-service verification (LLM)
- POST /api/v1/workorders/forecast       — Predictive forecast + narrative (LLM)
- POST /api/v1/workorders/ab-test        — A/B test LLM analysis
- GET  /api/v1/workorders/ab-baseline    — Real DB-computed A/B baseline metrics
- GET  /api/v1/workorders/status         — Service health & LLM availability
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ...services.workorder.models import (
    NLInterpretRequest,
    AutoCreateWORequest,
    PrioritizeRequest,
    MatchRequest,
    CostRecommendRequest,
    VerificationRequest,
    ForecastRequest,
    ABTestRequest,
)

logger = logging.getLogger(__name__)

workorder_router = APIRouter()


# ── Helpers ─────────────────────────────────────────────────────────

def _get_service():
    """Lazy-import to avoid circular imports during route registration."""
    from ...services.workorder.llm_service import get_wo_llm_service
    return get_wo_llm_service()


def _get_execution_engine():
    """Lazily get the ExecutionEngine for CMMS writeback. Returns None if unavailable."""
    try:
        from loweconex_platform.execution.execution_engine import (
            ExecutionEngine, WorkOrderRequest,
        )
        # Module-level singleton
        if not hasattr(_get_execution_engine, "_instance"):
            _get_execution_engine._instance = ExecutionEngine()
            logger.info("ExecutionEngine wired into workorder routes")
        return _get_execution_engine._instance
    except ImportError:
        return None


# ── Status ──────────────────────────────────────────────────────────

class WOStatusResponse(BaseModel):
    status: str
    llm_available: bool
    model: str
    fallback_active: bool


@workorder_router.get("/status", response_model=WOStatusResponse)
async def wo_status():
    """Check Work Order AI service health and LLM availability."""
    svc = _get_service()
    model = "none"
    if svc._client:
        model = getattr(svc._client, "model", "unknown")
    return WOStatusResponse(
        status="healthy",
        llm_available=svc.is_available,
        model=model,
        fallback_active=not svc.is_available,
    )


# ── 1. Natural Language Interpretation ──────────────────────────────

@workorder_router.post("/interpret")
async def interpret_nl(request: NLInterpretRequest):
    """Interpret natural-language text into a structured work order draft.

    Uses GPT-4 to extract: title, asset, location, priority, symptoms,
    problem type. Falls back to keyword heuristics when LLM unavailable.
    """
    svc = _get_service()
    result = svc.interpret(request)
    return result.model_dump()


# ── 2. Autonomous WO from PdM Signals ──────────────────────────────

@workorder_router.post("/auto-create")
async def auto_create_wo(request: AutoCreateWORequest):
    """Evaluate PdM sensor signals and auto-generate a work order if warranted.

    Analyzes change detection scores, fault hypotheses, persistence, and
    sensor trust to decide whether to create a WO. LLM provides diagnostic
    context and natural-language description.
    """
    svc = _get_service()
    result = svc.auto_create(request)
    response = result.model_dump()

    # Bridge to ExecutionEngine: submit to CMMS and track if WO was created
    if result.should_create:
        engine = _get_execution_engine()
        if engine:
            try:
                from loweconex_platform.execution.execution_engine import (
                    WorkOrderRequest, WorkOrderPriority as ExecWOPriority,
                )
                wo = WorkOrderRequest(
                    title=result.title,
                    description=result.description,
                    asset_id=result.asset_id,
                    priority=result.priority.value if hasattr(result.priority, 'value') else str(result.priority),
                    work_type="corrective",
                    trade="HVAC",
                    diagnostic_summary=result.diagnostic_context,
                    created_by="workorder_llm_service",
                    correlation_id=request.site_id,
                )
                submit_result = engine.cmms.submit_work_order(wo)
                response["execution_engine"] = {
                    "submitted": True,
                    "wo_id": wo.wo_id,
                    "cmms_result": submit_result,
                }
                logger.info("Auto-created WO %s submitted to ExecutionEngine CMMS", wo.wo_id)
            except Exception as e:
                logger.warning("ExecutionEngine CMMS submission failed: %s", e)
                response["execution_engine"] = {"submitted": False, "error": str(e)}

    return response


# ── 3. AI Prioritization & Triage ──────────────────────────────────

@workorder_router.post("/prioritize")
async def prioritize_wo(request: PrioritizeRequest):
    """AI impact assessment — scores safety, revenue, SLA, and brand risk.

    Returns a 0-100 priority score with explainable rationale generated
    by the LLM based on work order details and historical context.
    """
    svc = _get_service()
    result = svc.prioritize(request)
    return result.model_dump()


# ── 4. Provider Matching & Dispatch ─────────────────────────────────

@workorder_router.post("/match")
async def match_providers(request: MatchRequest):
    """Intelligent provider selection — ranks providers by skill, FTFR,
    availability, proximity, and cost using LLM-powered reasoning.
    """
    svc = _get_service()
    result = svc.match_providers(request)
    return result.model_dump()


# ── 5. Cost & Approval Recommendation ──────────────────────────────

@workorder_router.post("/recommend-cost")
async def recommend_cost(request: CostRecommendRequest):
    """AI cost recommendation — approve/reject/review with confidence
    and explainable rationale based on historical cost analysis.
    """
    svc = _get_service()
    result = svc.recommend_cost(request)
    return result.model_dump()


# ── 6. Post-Service Verification ───────────────────────────────────

@workorder_router.post("/verify")
async def verify_wo(request: VerificationRequest):
    """Post-service verification — compares pre/post metrics using LLM
    to determine if the fix was effective. Flags for reopen if not.
    """
    svc = _get_service()
    result = svc.verify(request)
    return result.model_dump()


# ── 7. Predictive Forecast ─────────────────────────────────────────

@workorder_router.post("/forecast")
async def forecast_wo(request: ForecastRequest):
    """Predictive WO forecast — time-series prediction with LLM-generated
    narrative interpretation, risk heat map, and seasonal analysis.
    """
    svc = _get_service()
    result = svc.forecast(request)
    return result.model_dump()


# ── 8. A/B Test Analysis ───────────────────────────────────────────

@workorder_router.post("/ab-test")
async def ab_test(request: ABTestRequest):
    """A/B test analysis — compares actual baseline WO KPIs against
    predicted AI-system KPIs. Returns LLM-generated analytical narrative,
    top improvements, risk areas, and executive summary.
    """
    svc = _get_service()
    result = svc.ab_test(request.baseline, request.predicted, request.time_range)
    return result.model_dump()


# ── 9. A/B Baseline from Real Data ────────────────────────────────

@workorder_router.get("/ab-baseline")
async def ab_baseline(
    site_id: str = Query(default="default", description="Site ID to scope metrics"),
    time_range: str = Query(default="30d", description="Analysis window: 7d, 30d, 90d, 12m"),
):
    """Compute all 12 A/B baseline metrics from real database records.

    Queries WorkOrderModel, AlertModel, and FeedbackModel for the time window,
    computes each metric with provenance tracking, fills gaps from KPIConfig
    or industry defaults, and applies documented improvement factors for the
    predicted (AI system) column.

    Returns: {baseline, predicted, provenance[], time_range, site_id, computed_at}
    """
    svc = _get_service()
    try:
        result = svc.compute_ab_baseline(site_id=site_id, time_range=time_range)
        return result.model_dump()
    except Exception as e:
        logger.error("AB baseline computation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Baseline computation error: {e}")
