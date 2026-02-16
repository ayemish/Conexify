"""FastAPI routes for the Scenario Advisor conversational interface.

Endpoints:
- POST /api/advisor/chat — Create session
- POST /api/advisor/chat/{session_id}/message — Send message
- GET  /api/advisor/chat/{session_id}/history — Get history
- DELETE /api/advisor/chat/{session_id} — Delete session
- GET  /api/advisor/scenarios/{ecosystem} — List scenarios
- GET  /api/advisor/agents/{ecosystem} — List agents
- GET  /api/advisor/status — System status
- GET  /api/advisor/current-state — Current portfolio state
- POST /api/advisor/search — RAG search
"""

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

advisor_router = APIRouter()

# ---------------------------------------------------------------------------
# Singleton advisor instance
# ---------------------------------------------------------------------------

def _get_advisor():
    from ...services.advisor import get_shared_advisor
    return get_shared_advisor()


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class CreateSessionRequest(BaseModel):
    ecosystem: str = Field(default="auto", description="Ecosystem: rmn, demand_procurement, or auto")


class CreateSessionResponse(BaseModel):
    session_id: str
    created_at: str
    ecosystem: str


class SendMessageRequest(BaseModel):
    message: str = Field(..., description="User message text")
    stream: bool = Field(default=False, description="Whether to stream the response")


class AdvisorResponseModel(BaseModel):
    message: str
    ecosystem: Optional[str] = None
    scenario_ids: List[str] = []
    data: Optional[Dict[str, Any]] = None
    actions: List[Dict[str, Any]] = []
    agent_source: Optional[str] = None
    confidence: float = 0.5
    timestamp: str = ""


class SendMessageResponse(BaseModel):
    session_id: str
    response: AdvisorResponseModel


class HistoryResponse(BaseModel):
    session_id: str
    ecosystem: str
    messages: List[Dict[str, Any]]
    context: Dict[str, Any]


class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    top_k: int = Field(default=4, description="Number of results")


class SearchResponse(BaseModel):
    query: str
    top_k: int
    results: List[Dict[str, Any]]
    count: int


class StatusResponse(BaseModel):
    status: str
    openai_available: bool
    model: str
    active_sessions: int
    ecosystems: List[str]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@advisor_router.post("/chat", response_model=CreateSessionResponse)
async def create_session(body: CreateSessionRequest):
    """Create a new advisor chat session."""
    advisor = _get_advisor()
    session = advisor.create_session(ecosystem=body.ecosystem)
    return CreateSessionResponse(
        session_id=session.session_id,
        created_at=session.created_at.isoformat(),
        ecosystem=session.ecosystem.value,
    )


@advisor_router.post("/chat/{session_id}/message", response_model=SendMessageResponse)
async def send_message(session_id: str, body: SendMessageRequest):
    """Send a message to an advisor session.

    When ``stream=True``, returns a ``text/event-stream`` SSE response
    with incremental token chunks.  Each SSE event has ``data: {json}``
    with keys ``token`` (partial text) or ``done`` (final metadata).
    """
    advisor = _get_advisor()
    session = advisor.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    # ── Streaming path ──────────────────────────────────────────
    if body.stream:
        return StreamingResponse(
            _stream_advisor_response(advisor, session_id, body.message),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # ── Non-streaming path ──────────────────────────────────────
    result = advisor.send_message(session_id, body.message, stream=False)
    return SendMessageResponse(
        session_id=session_id,
        response=AdvisorResponseModel(
            message=result.message,
            ecosystem=result.ecosystem.value if result.ecosystem else None,
            scenario_ids=result.scenario_ids,
            data=result.data,
            actions=result.actions,
            agent_source=result.agent_source,
            confidence=result.confidence,
            timestamp=result.timestamp.isoformat(),
        ),
    )


async def _stream_advisor_response(advisor, session_id: str, message: str):
    """SSE generator that streams advisor response tokens."""
    try:
        # Build the message history for OpenAI streaming
        session = advisor.get_session(session_id)
        messages = advisor._build_messages(session_id, message)

        # Get the OpenAI client from the advisor
        client = (
            getattr(advisor, "client", None)
            or getattr(advisor, "_openai_client", None)
            or getattr(advisor, "llm_client", None)
        )
        if client is None or not getattr(client, 'is_available', False):
            # Fall back to non-streaming and send as single SSE event
            result = advisor.send_message(session_id, message, stream=False)
            data = json.dumps({"token": result.message})
            yield f"data: {data}\n\n"
            done = json.dumps({
                "done": True,
                "ecosystem": result.ecosystem.value if result.ecosystem else None,
                "confidence": result.confidence,
                "agent_source": result.agent_source,
            })
            yield f"data: {done}\n\n"
            return

        # Stream tokens from OpenAI
        full_response = ""
        for token in client.chat_stream(messages):
            full_response += token
            data = json.dumps({"token": token})
            yield f"data: {data}\n\n"

        # Record the full response in session history
        advisor._record_assistant_response(session_id, full_response)

        # Send done event with metadata
        done = json.dumps({
            "done": True,
            "full_response": full_response,
            "ecosystem": session.ecosystem.value if session and session.ecosystem else None,
        })
        yield f"data: {done}\n\n"

    except Exception as exc:
        logger.error("Streaming advisor response failed: %s", exc)
        error = json.dumps({"error": str(exc)})
        yield f"data: {error}\n\n"


@advisor_router.get("/chat/{session_id}/history", response_model=HistoryResponse)
async def get_history(session_id: str):
    """Get conversation history for a session."""
    advisor = _get_advisor()
    session = advisor.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    return HistoryResponse(
        session_id=session.session_id,
        ecosystem=session.ecosystem.value,
        messages=session.get_history(),
        context=session.context,
    )


@advisor_router.delete("/chat/{session_id}", status_code=204)
async def delete_session(session_id: str):
    """Delete an advisor session."""
    advisor = _get_advisor()
    if not advisor.delete_session(session_id):
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")


@advisor_router.get("/scenarios/{ecosystem}")
async def get_scenarios(ecosystem: str):
    """List available scenarios for an ecosystem."""
    advisor = _get_advisor()
    scenarios = advisor.catalog
    categories: Dict[str, List[Dict[str, Any]]] = {}
    for s in scenarios:
        cat = s["category"]
        categories.setdefault(cat, []).append({
            "scenario_id": s["scenario_id"],
            "name": s["name"],
            "description": s["description"],
        })
    return {
        "ecosystem": ecosystem,
        "scenarios": [
            {"scenario_id": s["scenario_id"], "name": s["name"],
             "category": s["category"], "description": s["description"]}
            for s in scenarios
        ],
        "categories": list(categories.keys()),
    }


@advisor_router.get("/agents/{ecosystem}")
async def get_agents(ecosystem: str):
    """List available agents for an ecosystem.

    Ecosystems:
    - maintenance: Core PdM agents for energy, refrigerant, work orders, and asset health
    - compliance: Food safety, ESG, and regulatory compliance agents
    - all (or any other value): All available agents
    """
    maintenance_agents = [
        {"name": "energy_reduction", "role": "Energy Optimization Crew", "ecosystem": "maintenance",
         "description": "Analyzes energy savings from PdM-driven HVAC/R efficiency improvements."},
        {"name": "refrigerant_leak_reduction", "role": "Refrigerant Management Crew", "ecosystem": "maintenance",
         "description": "Detects and prevents refrigerant leaks, manages EPA compliance."},
        {"name": "work_order_reduction", "role": "Work Order Optimization Crew", "ecosystem": "maintenance",
         "description": "Converts reactive maintenance to planned through predictive insights."},
        {"name": "asset_failure_prediction", "role": "Asset Health Prediction Crew", "ecosystem": "maintenance",
         "description": "Predicts asset failures using health scores, RUL, and fault diagnosis."},
        {"name": "capex_lifecycle_optimization", "role": "CapEx Lifecycle Crew", "ecosystem": "maintenance",
         "description": "Optimizes capital expenditure timing using Weibull survival and NPV analysis."},
        {"name": "asset_uptime_increase", "role": "Uptime Maximization Crew", "ecosystem": "maintenance",
         "description": "Maximizes equipment availability through predictive failure prevention."},
        {"name": "service_bureau_reduction", "role": "Service Dispatch Optimization Crew", "ecosystem": "maintenance",
         "description": "Reduces third-party service dispatches via in-house PdM diagnostics."},
        {"name": "fleet_diagnostics", "role": "Fleet Diagnostics Agent", "ecosystem": "maintenance",
         "description": "Provides fleet-wide health assessment, triage, and failure mode analysis."},
        {"name": "scenario_advisor", "role": "Scenario Analysis Agent", "ecosystem": "maintenance",
         "description": "Runs what-if scenarios with custom parameter overrides across all KPIs."},
    ]
    compliance_agents = [
        {"name": "food_waste_reduction", "role": "Food Waste Prevention Crew", "ecosystem": "compliance",
         "description": "Prevents temperature excursions and reduces shrink from equipment failures."},
        {"name": "food_safety_compliance", "role": "Food Safety Compliance Crew", "ecosystem": "compliance",
         "description": "Monitors food safety violations and ensures regulatory compliance."},
        {"name": "esg_carbon_reduction", "role": "ESG & Carbon Reduction Crew", "ecosystem": "compliance",
         "description": "Tracks carbon reduction, refrigerant GWP, and sustainability metrics."},
        {"name": "call_center_reduction", "role": "Call Center Optimization Crew", "ecosystem": "compliance",
         "description": "Reduces inbound maintenance calls through proactive alerting."},
    ]
    if ecosystem == "maintenance":
        agents = maintenance_agents
    elif ecosystem == "compliance":
        agents = compliance_agents
    else:
        agents = maintenance_agents + compliance_agents
    return {"ecosystem": ecosystem, "agents": agents}


@advisor_router.get("/status", response_model=StatusResponse)
async def get_status():
    """Get advisor system status."""
    advisor = _get_advisor()
    return StatusResponse(
        status="healthy",
        openai_available=advisor.client.is_available,
        model=advisor.client.model,
        active_sessions=len(advisor.sessions),
        ecosystems=["maintenance", "compliance"],
    )


@advisor_router.get("/current-state")
async def get_current_state(
    site_id: Optional[str] = Query(default=None),
    retailer_id: Optional[str] = Query(default=None),
    include_kpis: bool = Query(default=False, description="Include live KPI dashboard data"),
):
    """Get current fleet health state, optionally with live KPI data.

    When include_kpis=true, the advisor response is grounded in the latest
    computed KPI dashboard (gap #30 fix).
    """
    advisor = _get_advisor()
    state = advisor._get_current_state(site_id or retailer_id)

    if include_kpis:
        try:
            from ...persistence.kpi_repository import get_dashboard_cache
            effective_site = site_id or retailer_id or "default"
            cache = get_dashboard_cache()
            cached_dashboard = cache.get(effective_site)
            if cached_dashboard:
                state["kpi_dashboard"] = {
                    "executive_summary": cached_dashboard.get("executive_summary", {}),
                    "scorecards": [
                        {
                            "kpi_name": sc.get("kpi_name"),
                            "display_name": sc.get("display_name"),
                            "savings_medium": sc.get("savings_medium", 0),
                            "confidence": sc.get("confidence", 0),
                            "status": sc.get("status"),
                        }
                        for sc in cached_dashboard.get("scorecards", [])
                    ],
                    "roi": cached_dashboard.get("roi", {}),
                    "computed_at": cached_dashboard.get("computed_at"),
                }
            else:
                state["kpi_dashboard"] = {"status": "not_computed", "message": "Run the KPI dashboard first"}
        except Exception as kpi_err:
            logger.debug("Live KPI state for advisor skipped: %s", kpi_err)
            state["kpi_dashboard"] = {"status": "unavailable", "error": str(kpi_err)}

    return state


@advisor_router.post("/search", response_model=SearchResponse)
async def search_knowledge(body: SearchRequest):
    """Semantic search over the RAG knowledge base."""
    advisor = _get_advisor()
    results = advisor.rag.search(body.query, top_k=body.top_k)
    return SearchResponse(
        query=body.query,
        top_k=body.top_k,
        results=[
            {"doc_id": r.doc_id, "doc_type": r.doc_type,
             "content": r.content[:300], "score": round(r.score, 3),
             "metadata": r.metadata}
            for r in results
        ],
        count=len(results),
    )
