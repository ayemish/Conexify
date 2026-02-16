"""Domain-aligned scenario routes for HVAC/R decision support."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ._routes_legacy import verify_api_key
from ...services.advisor import get_shared_advisor

scenario_router = APIRouter()


class PersonaResponse(BaseModel):
    id: str
    name: str
    tagline: str
    prompt: str


class PersonaListResponse(BaseModel):
    personas: List[PersonaResponse]


class ScenarioChatRequest(BaseModel):
    message: str = ""
    site_id: str = "default"
    scenario_id: Optional[str] = None
    session_id: Optional[str] = None
    risk_appetite: str = "balanced"
    parameters: Dict[str, Any] = Field(default_factory=dict)

    # Backward-compatible fields from legacy scenario API payloads.
    persona_id: Optional[str] = None
    persona_prompt: Optional[str] = None
    scope: str = "company"
    marketing_budget: Optional[str] = None
    risk_level: Optional[str] = None
    payback_timeline: Optional[str] = None


class ScenarioChatResponse(BaseModel):
    session_id: str
    message: str
    scenario_id: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


@scenario_router.get("/personas", response_model=PersonaListResponse)
async def get_personas(api_key: str = Depends(verify_api_key)):
    """List HVAC/R decision-support personas."""
    _ = api_key
    personas = [
        PersonaResponse(
            id="maintenance_operations",
            name="Maintenance Operations",
            tagline="Reactive-to-planned conversion, dispatch and labor optimization.",
            prompt=(
                "Focus on converting reactive HVAC/R work to planned interventions, "
                "reducing emergency dispatches and improving uptime."
            ),
        ),
        PersonaResponse(
            id="energy_sustainability",
            name="Energy & Sustainability",
            tagline="Energy savings, refrigerant leakage reduction, ESG outcomes.",
            prompt=(
                "Prioritize HVAC/R energy efficiency, refrigerant leak prevention, "
                "and measurable carbon reduction outcomes."
            ),
        ),
        PersonaResponse(
            id="capital_strategy",
            name="Capital Strategy",
            tagline="CapEx lifecycle timing, replace-vs-repair, portfolio ROI.",
            prompt=(
                "Optimize capital planning decisions using asset health, RUL, and "
                "cross-KPI tradeoffs across the full asset portfolio."
            ),
        ),
    ]
    return PersonaListResponse(personas=personas)


@scenario_router.post("/chat", response_model=ScenarioChatResponse)
async def scenario_chat(
    body: ScenarioChatRequest,
    api_key: str = Depends(verify_api_key),
):
    """Run a scenario or chat against the unified advisor."""
    _ = api_key
    advisor = get_shared_advisor()
    session_id = body.session_id

    if body.scenario_id:
        scenario_result = advisor._execute_scenario(
            scenario_id=body.scenario_id,
            site_id=body.site_id or "default",
            parameters=body.parameters or {},
            risk_appetite=body.risk_appetite or "balanced",
        )
        if not scenario_result.get("success", False):
            raise HTTPException(status_code=400, detail=scenario_result.get("error", "Scenario execution failed"))
        message = (
            scenario_result.get("decision_recommendation", {}) or {}
        ).get("executive_summary", "Scenario executed.")
        return ScenarioChatResponse(
            session_id=session_id or scenario_result.get("session_id", ""),
            message=message,
            scenario_id=body.scenario_id,
            data=scenario_result,
            created_at=datetime.utcnow(),
        )

    if not session_id:
        session = advisor.create_session(ecosystem="auto")
        session_id = session.session_id

    user_message = (body.message or "").strip()
    if not user_message:
        legacy_parts = [
            body.persona_prompt or "",
            body.marketing_budget or "",
            body.risk_level or "",
            body.payback_timeline or "",
        ]
        user_message = " ".join([p for p in legacy_parts if p]).strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="A message or scenario_id is required")

    resp = advisor.send_message(session_id, user_message, stream=False)
    return ScenarioChatResponse(
        session_id=session_id,
        message=resp.message,
        scenario_id=None,
        data=resp.to_dict(),
        created_at=datetime.utcnow(),
    )
