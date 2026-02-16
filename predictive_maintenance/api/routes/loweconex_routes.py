"""
Loweconex Platform API Routes

Exposes the full Loweconex CrewAI-powered pipeline via the PdM API server:
- POST /api/v1/loweconex/pipeline — Run the full 7-phase orchestrator pipeline
- GET  /api/v1/loweconex/pipeline/status — Bridge & crew availability
- POST /api/v1/loweconex/crews/{kpi_name} — Run a single KPI crew
- GET  /api/v1/loweconex/crews — List available KPI crews
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

loweconex_router = APIRouter()


# ── Request / Response Models ───────────────────────────────────────

class PipelineRequest(BaseModel):
    site_id: str = Field(default="default", description="Site ID to run pipeline for")
    company_id: Optional[str] = Field(default=None, description="Override company ID")
    run_scenarios: bool = Field(default=True, description="Run scenario comparison")
    run_capex: bool = Field(default=True, description="Run CapEx planning")


class PipelineStatusResponse(BaseModel):
    loweconex_available: bool
    crewai_orchestration_available: bool
    registered_crews: List[str]
    crew_count: int


class CrewRunRequest(BaseModel):
    company_id: str = Field(default="default", description="Company/site ID")
    location_id: Optional[str] = Field(default=None, description="Optional location filter")
    scenario_params: Optional[Dict[str, Any]] = Field(default=None, description="Scenario overrides")


class PipelineResponse(BaseModel):
    site_id: str
    started_at: str
    mode: str = Field(description="Execution mode: 'crewai' or 'deterministic'")
    kpi_results: List[Dict[str, Any]] = Field(default_factory=list)
    scenario_comparison: List[Dict[str, Any]] = Field(default_factory=list)
    orchestration_summary: Dict[str, Any] = Field(default_factory=dict)
    completed_at: Optional[str] = None


class CrewSpecResponse(BaseModel):
    kpi_name: str
    display_name: str
    objective: str = ""
    has_calculation_fn: bool = False
    required_inputs: List[str] = Field(default_factory=list)
    savings_category: str = ""
    research_topics: List[str] = Field(default_factory=list)
    specialist_agents: int = 0


class CrewListResponse(BaseModel):
    crews: List[CrewSpecResponse]
    count: int


class CrewRunResponse(BaseModel):
    kpi_name: str = ""
    status: str = "completed"
    savings_low: float = 0.0
    savings_medium: float = 0.0
    savings_high: float = 0.0
    confidence: float = 0.0
    narrative: str = ""
    assumptions: List[str] = Field(default_factory=list)
    supporting_metrics: Dict[str, Any] = Field(default_factory=dict)
    reasoning_trace: List[str] = Field(default_factory=list)
    qa_checks: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"


# ── Endpoints ───────────────────────────────────────────────────────

@loweconex_router.get("/pipeline/status", response_model=PipelineStatusResponse)
async def get_pipeline_status():
    """Check availability of the Loweconex CrewAI pipeline."""
    from ...services.kpi.loweconex_bridge import get_bridge_status
    status = get_bridge_status()
    return PipelineStatusResponse(**status)


@loweconex_router.post("/pipeline", response_model=PipelineResponse)
async def run_pipeline(req: PipelineRequest):
    """Run the full Loweconex 7-phase orchestrator pipeline.

    Phases: PdM Bridge → KPI Crews (14) → Scenarios → Cross-Asset
    Optimization → CapEx → Portfolio Optimization → Decision Advisory.

    When CrewAI is available, runs the full agent pipeline. Otherwise
    falls back to the deterministic KPI computation stack.
    """
    from ...services.kpi.loweconex_bridge import (
        CREWAI_ORCHESTRATION_AVAILABLE,
        LOWECONEX_AVAILABLE,
        run_full_crew_pipeline,
    )
    from ...services.kpi.base import KPIConfig
    from ...config import settings

    config = KPIConfig.load_from_db(req.site_id)
    company_id = req.company_id or req.site_id

    result = {
        "site_id": req.site_id,
        "started_at": datetime.utcnow().isoformat(),
        "mode": "deterministic",
        "kpi_results": [],
        "scenario_comparison": [],
        "orchestration_summary": {},
    }

    def _run_deterministic_orchestrator():
        try:
            from loweconex_platform.config import PlatformConfig
            from loweconex_platform.orchestration.orchestrator_crew import OrchestratorCrew
            from loweconex_platform.digital_twins.store import get_default_store
            from loweconex_platform.event_bus.redis_streams import LoweconexEventBus

            twin_store = get_default_store()
            platform_config = PlatformConfig()
            try:
                event_bus = LoweconexEventBus(agent_id="loweconex_pipeline")
            except Exception:
                from shared.event_bus.redis_event_bus import InMemoryEventBus
                event_bus = InMemoryEventBus(agent_id="loweconex_pipeline")

            # Wire PdM Bridge so Phase 0 enrichment feeds PdM model
            # outputs (health scores, RUL, fault beliefs) into KPI crews.
            pdm_bridge = None
            try:
                from loweconex_platform.pdm_bridge import PdMBridge
                pdm_bridge = PdMBridge(
                    twin_store=twin_store,
                    event_bus=event_bus,
                )
                logger.info("PdM bridge wired into orchestrator pipeline")
            except Exception as e:
                logger.warning("PdM bridge not available: %s", e)

            orch = OrchestratorCrew(
                config=platform_config,
                twin_store=twin_store,
                event_bus=event_bus,
                pdm_bridge=pdm_bridge,
            )
            pipeline_result = orch.run_full_pipeline(
                company_id=company_id,
                run_scenarios=req.run_scenarios,
            )
            result["orchestration_summary"] = (
                pipeline_result.to_dict()
                if hasattr(pipeline_result, "to_dict")
                else pipeline_result
            )
        except Exception as e:
            logger.error("Loweconex orchestrator failed: %s", e, exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Orchestrator pipeline failed: {e}",
            )

    # ── Phase 1: KPI Computation ────────────────────────────────
    if not LOWECONEX_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="Loweconex platform not available. Install loweconex_platform package.",
        )

    api_key = (
        os.environ.get("OPENAI_API_KEY", "").strip()
        or (settings.openai.api_key or "").strip()
    )
    if not api_key:
        for k, v in os.environ.items():
            if k.lower() == "openai_api_key":
                api_key = (v or "").strip()
                break
    can_run_crewai = CREWAI_ORCHESTRATION_AVAILABLE and bool(api_key)

    if can_run_crewai:
        try:
            crew_results = run_full_crew_pipeline(config, company_id)
            result["kpi_results"] = crew_results
            result["mode"] = "crewai"
        except Exception as e:
            logger.error(
                "CrewAI pipeline failed, falling back to deterministic mode: %s",
                e,
                exc_info=True,
            )
            result["mode"] = "deterministic"
            _run_deterministic_orchestrator()
    else:
        if CREWAI_ORCHESTRATION_AVAILABLE and not api_key:
            logger.warning(
                "OPENAI_API_KEY not configured for loweconex pipeline; using deterministic mode"
            )
        result["mode"] = "deterministic"
        _run_deterministic_orchestrator()

    # ── Phase 2: Scenario Comparison ────────────────────────────
    if req.run_scenarios:
        try:
            from ...services.kpi.loweconex_bridge import run_scenario_comparison
            scenarios = run_scenario_comparison([], config)
            result["scenario_comparison"] = scenarios
        except Exception as e:
            logger.warning("Scenario comparison failed: %s", e)

    result["completed_at"] = datetime.utcnow().isoformat()
    return result


@loweconex_router.get("/crews", response_model=CrewListResponse)
async def list_crews():
    """List all registered KPI crew specifications."""
    try:
        from loweconex_platform.kpi_crews.registry import KPI_REGISTRY as CREW_REGISTRY

        crews = []
        for name, spec in CREW_REGISTRY.items():
            crews.append({
                "kpi_name": name,
                "display_name": spec.display_name,
                "objective": spec.objective,
                "has_calculation_fn": spec.calculation_fn is not None,
                "required_inputs": spec.required_inputs,
                "savings_category": spec.savings_category,
                "research_topics": spec.research_topics,
                "specialist_agents": len(spec.specialist_agents),
            })
        return {"crews": crews, "count": len(crews)}
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="Loweconex KPI crews not available",
        )


@loweconex_router.post("/crews/{kpi_name}", response_model=CrewRunResponse)
async def run_single_crew(kpi_name: str, req: CrewRunRequest):
    """Run a single KPI crew by name."""
    from ...services.kpi.loweconex_bridge import CREWAI_ORCHESTRATION_AVAILABLE

    if not CREWAI_ORCHESTRATION_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="CrewAI orchestration not available",
        )

    try:
        from loweconex_platform.kpi_crews.registry import KPI_REGISTRY as CREW_REGISTRY
        from loweconex_platform.kpi_crews.base_crew import KPICrewFactory
        from loweconex_platform.kpi_crews.tools import LoweconexTools, ArtifactStore
        from loweconex_platform.digital_twins.store import get_default_store
        from loweconex_platform.event_bus.redis_streams import LoweconexEventBus

        spec = CREW_REGISTRY.get(kpi_name)
        if spec is None:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown KPI crew: {kpi_name}. Available: {list(CREW_REGISTRY.keys())}",
            )

        from ...config import settings
        api_key = (
            os.environ.get("OPENAI_API_KEY", "").strip()
            or (settings.openai.api_key or "").strip()
        )
        if not api_key:
            for k, v in os.environ.items():
                if k.lower() == "openai_api_key":
                    api_key = (v or "").strip()
                    break
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail="OPENAI_API_KEY is not configured. Set it to run CrewAI crews.",
            )

        twin_store = get_default_store()
        try:
            event_bus = LoweconexEventBus(agent_id=f"crew_{kpi_name}")
        except Exception:
            from shared.event_bus.redis_event_bus import InMemoryEventBus
            event_bus = InMemoryEventBus(agent_id=f"crew_{kpi_name}")
        artifact_store = ArtifactStore()
        tools = LoweconexTools(
            twin_store=twin_store,
            event_bus=event_bus,
            artifact_store=artifact_store,
        )

        factory = KPICrewFactory(tools=tools, event_bus=event_bus)
        result = factory.run_crew(
            spec=spec,
            company_id=req.company_id,
            location_id=req.location_id,
            scenario_params=req.scenario_params,
        )
        return result.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Crew %s failed: %s", kpi_name, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
