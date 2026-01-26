"""
Decision Orchestrator API

FastAPI service for the CrewAI-based decision operating system.
Provides endpoints for pipeline orchestration and decision pack generation.

FR-9.1: Agent layer orchestrates pipeline steps
FR-9.2: Agent layer produces human-readable rationales
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import date, datetime
import logging
import os
import sys
from pathlib import Path
import httpx

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from vendor.agents.decision_os import (
    DecisionOrchestrator, OrchestratorConfig, create_decision_orchestrator
)
from shared.schemas.data_contracts import (
    DecisionPack, DecisionPackItem, MonitoringAlert,
    RunStatus
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# App Configuration
# =============================================================================

app = FastAPI(
    title="Decision Orchestrator API",
    description="CrewAI-based pipeline orchestration and decision pack generation",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator: Optional[DecisionOrchestrator] = None

# Service URLs (configured via environment)
BAYESIAN_URL = os.getenv("BAYESIAN_URL", "http://bayesian-engine:8081")
OPTIMIZER_URL = os.getenv("OPTIMIZER_URL", "http://optimizer:8082")
TWIN_URL = os.getenv("TWIN_URL", "http://digital-twin:8083")


# =============================================================================
# Request/Response Models
# =============================================================================

class ForecastInput(BaseModel):
    """Forecast input for pipeline"""
    entity_id: str
    week_start: date
    q10: float
    q50: float
    q90: float


class EntityInput(BaseModel):
    """Entity configuration for pipeline"""
    entity_id: str
    current_inventory: float
    on_order: float = 0.0
    expected_weekly_demand: float
    demand_std: float
    lead_time_weeks: int
    moq: int = 1
    case_pack: int = 1
    unit_cost: float = 10.0


class RunPipelineRequest(BaseModel):
    """Request to run full orchestration pipeline"""
    entities: List[EntityInput]
    forecasts: List[ForecastInput]
    scenarios: Optional[List[str]] = ["baseline", "demand_surge", "lead_time_increase"]
    model_version: str = "v1.0.0"
    generate_report: bool = True


class PipelineStepResult(BaseModel):
    """Result of a single pipeline step"""
    step_name: str
    status: str
    started_at: Optional[str]
    completed_at: Optional[str]
    duration_ms: Optional[float]
    result_summary: Optional[Dict[str, Any]]
    error: Optional[str]


class DecisionPackResponse(BaseModel):
    """Decision pack response"""
    pack_id: str
    generated_at: str
    model_version: str
    recommendations: List[Dict[str, Any]]
    monitoring_alerts: List[Dict[str, Any]]
    scenario_comparisons: Dict[str, Any]
    report_path: Optional[str]


class PipelineRunResponse(BaseModel):
    """Full pipeline run response"""
    run_id: str
    status: str
    steps: List[PipelineStepResult]
    decision_pack: Optional[DecisionPackResponse]
    total_duration_ms: float


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    orchestrator_initialized: bool
    service_connections: Dict[str, bool]
    timestamp: str


# =============================================================================
# Lifecycle Events
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize orchestrator on startup"""
    global orchestrator
    
    config = OrchestratorConfig(
        output_path=os.getenv("OUTPUT_PATH", "/app/reports"),
        generate_markdown=True,
        generate_json=True
    )
    
    orchestrator = create_decision_orchestrator(config)
    logger.info("Decision Orchestrator initialized")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Decision Orchestrator shutting down")


# =============================================================================
# Helper Functions
# =============================================================================

async def check_service_health(url: str) -> bool:
    """Check if a service is healthy"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/health")
            return response.status_code == 200
    except Exception:
        return False


async def call_bayesian_engine(
    entity_id: str,
    forecasts: List[Dict],
    inventory_state: Dict,
    supply_params: Dict
) -> Dict:
    """Call Bayesian engine API"""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{BAYESIAN_URL}/analyze",
                json={
                    "entity_id": entity_id,
                    "forecasts": forecasts,
                    "inventory_state": inventory_state,
                    "supply_params": supply_params
                }
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Bayesian engine call failed: {e}")
        return {"error": str(e)}


async def call_optimizer(entity: Dict, posterior: Optional[Dict] = None) -> Dict:
    """Call optimizer API"""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {**entity}
            if posterior:
                payload["posterior"] = posterior
            
            response = await client.post(
                f"{OPTIMIZER_URL}/optimize",
                json=payload
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Optimizer call failed: {e}")
        return {"error": str(e)}


async def call_digital_twin(state_id: str, scenarios: List[str]) -> Dict:
    """Call digital twin API"""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{TWIN_URL}/feed-to-bayesian/{state_id}",
                params={"scenarios": scenarios}
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Digital twin call failed: {e}")
        return {"error": str(e)}


# =============================================================================
# API Endpoints
# =============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint with service connectivity"""
    service_health = {
        "bayesian_engine": await check_service_health(BAYESIAN_URL),
        "optimizer": await check_service_health(OPTIMIZER_URL),
        "digital_twin": await check_service_health(TWIN_URL)
    }
    
    return HealthResponse(
        status="healthy" if orchestrator else "initializing",
        orchestrator_initialized=orchestrator is not None,
        service_connections=service_health,
        timestamp=datetime.utcnow().isoformat()
    )


@app.post("/run-pipeline", response_model=PipelineRunResponse)
async def run_pipeline(request: RunPipelineRequest, background_tasks: BackgroundTasks):
    """
    Run the full orchestration pipeline.
    
    Steps:
    1. Initialize digital twin state
    2. Run scenario simulations
    3. Feed scenarios to Bayesian engine
    4. Run optimization with posteriors
    5. Generate decision pack
    """
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    
    import time
    import uuid
    
    run_id = str(uuid.uuid4())[:8]
    start_time = time.time()
    steps = []
    
    try:
        # Step 1: Initialize Twin State
        step_start = time.time()
        steps.append(PipelineStepResult(
            step_name="initialize_twin",
            status="running",
            started_at=datetime.utcnow().isoformat(),
            completed_at=None,
            duration_ms=None,
            result_summary=None,
            error=None
        ))
        
        # Initialize state via API
        async with httpx.AsyncClient(timeout=60.0) as client:
            init_response = await client.post(
                f"{TWIN_URL}/state/initialize",
                json={
                    "week_start": str(date.today()),
                    "entities": [
                        {
                            "entity_id": e.entity_id,
                            "on_hand": e.current_inventory,
                            "on_order": e.on_order,
                            "expected_weekly_demand": e.expected_weekly_demand,
                            "demand_std": e.demand_std,
                            "lead_time_weeks": e.lead_time_weeks,
                            "moq": e.moq,
                            "case_pack": e.case_pack,
                            "reorder_point": e.current_inventory * 0.3,
                            "order_quantity": int(e.expected_weekly_demand * 4),
                            "unit_cost": e.unit_cost
                        }
                        for e in request.entities
                    ],
                    "forecasts": [
                        {
                            "entity_id": f.entity_id,
                            "entity_level": "sku",
                            "week_start": str(f.week_start),
                            "q10": f.q10,
                            "q50": f.q50,
                            "q90": f.q90,
                            "model_version": request.model_version
                        }
                        for f in request.forecasts
                    ]
                }
            )
            init_response.raise_for_status()
            state_data = init_response.json()
            state_id = state_data["state_id"]
        
        steps[-1].status = "completed"
        steps[-1].completed_at = datetime.utcnow().isoformat()
        steps[-1].duration_ms = (time.time() - step_start) * 1000
        steps[-1].result_summary = {"state_id": state_id}
        
        # Step 2: Run Scenario Simulations
        step_start = time.time()
        steps.append(PipelineStepResult(
            step_name="run_scenarios",
            status="running",
            started_at=datetime.utcnow().isoformat(),
            completed_at=None,
            duration_ms=None,
            result_summary=None,
            error=None
        ))
        
        twin_scenarios = await call_digital_twin(state_id, request.scenarios)
        
        steps[-1].status = "completed"
        steps[-1].completed_at = datetime.utcnow().isoformat()
        steps[-1].duration_ms = (time.time() - step_start) * 1000
        steps[-1].result_summary = {"scenarios_run": len(request.scenarios)}
        
        # Step 3: Bayesian Analysis with Twin Scenarios
        step_start = time.time()
        steps.append(PipelineStepResult(
            step_name="bayesian_analysis",
            status="running",
            started_at=datetime.utcnow().isoformat(),
            completed_at=None,
            duration_ms=None,
            result_summary=None,
            error=None
        ))
        
        posteriors = {}
        for entity in request.entities:
            entity_forecasts = [
                {"week_start": str(f.week_start), "q10": f.q10, "q50": f.q50, "q90": f.q90}
                for f in request.forecasts if f.entity_id == entity.entity_id
            ]
            
            if entity_forecasts:
                # Use twin scenarios for informed posteriors
                async with httpx.AsyncClient(timeout=60.0) as client:
                    bayes_response = await client.post(
                        f"{BAYESIAN_URL}/analyze-with-twin-scenarios",
                        params={
                            "entity_id": entity.entity_id,
                            "model_version": request.model_version
                        },
                        json=twin_scenarios.get("scenarios", {})
                    )
                    if bayes_response.status_code == 200:
                        posteriors[entity.entity_id] = bayes_response.json()
        
        steps[-1].status = "completed"
        steps[-1].completed_at = datetime.utcnow().isoformat()
        steps[-1].duration_ms = (time.time() - step_start) * 1000
        steps[-1].result_summary = {"entities_analyzed": len(posteriors)}
        
        # Step 4: Optimization with Posteriors
        step_start = time.time()
        steps.append(PipelineStepResult(
            step_name="optimization",
            status="running",
            started_at=datetime.utcnow().isoformat(),
            completed_at=None,
            duration_ms=None,
            result_summary=None,
            error=None
        ))
        
        optimization_results = []
        for entity in request.entities:
            entity_posterior = posteriors.get(entity.entity_id, {}).get("baseline", {})
            
            opt_result = await call_optimizer(
                {
                    "entity_id": entity.entity_id,
                    "current_inventory": entity.current_inventory,
                    "on_order": entity.on_order,
                    "expected_weekly_demand": entity.expected_weekly_demand,
                    "demand_std": entity.demand_std,
                    "lead_time_weeks": entity.lead_time_weeks,
                    "moq": entity.moq,
                    "case_pack": entity.case_pack,
                    "unit_cost": entity.unit_cost
                },
                entity_posterior if entity_posterior else None
            )
            
            if "error" not in opt_result:
                optimization_results.append(opt_result)
        
        steps[-1].status = "completed"
        steps[-1].completed_at = datetime.utcnow().isoformat()
        steps[-1].duration_ms = (time.time() - step_start) * 1000
        steps[-1].result_summary = {"entities_optimized": len(optimization_results)}
        
        # Step 5: Generate Decision Pack
        step_start = time.time()
        steps.append(PipelineStepResult(
            step_name="generate_decision_pack",
            status="running",
            started_at=datetime.utcnow().isoformat(),
            completed_at=None,
            duration_ms=None,
            result_summary=None,
            error=None
        ))
        
        # Generate recommendations and alerts
        recommendations = []
        alerts = []
        
        for opt in optimization_results:
            recommendations.append({
                "entity_id": opt["entity_id"],
                "action": "reorder" if opt["recommended_order_quantity"] > 0 else "hold",
                "quantity": opt["recommended_order_quantity"],
                "reorder_point": opt["recommended_reorder_point"],
                "expected_service_level": opt["expected_service_level"],
                "rationale": f"Optimized to achieve {opt['expected_service_level']:.1%} service level"
            })
            
            if opt["expected_stockout_risk"] > 0.10:
                alerts.append({
                    "entity_id": opt["entity_id"],
                    "severity": "warning",
                    "message": f"High stockout risk: {opt['expected_stockout_risk']:.1%}",
                    "recommended_action": "Expedite order or increase safety stock"
                })
        
        # Save decision pack
        pack_id = f"pack-{run_id}"
        report_path = None
        
        if request.generate_report:
            report_path = f"{orchestrator.config.output_path}/{pack_id}.md"
            Path(orchestrator.config.output_path).mkdir(parents=True, exist_ok=True)
            
            with open(report_path, 'w') as f:
                f.write(f"# Decision Pack: {pack_id}\n\n")
                f.write(f"Generated: {datetime.utcnow().isoformat()}\n\n")
                f.write(f"## Recommendations\n\n")
                for rec in recommendations:
                    f.write(f"- **{rec['entity_id']}**: {rec['action']} {rec['quantity']} units\n")
                f.write(f"\n## Alerts\n\n")
                for alert in alerts:
                    f.write(f"- [{alert['severity'].upper()}] {alert['entity_id']}: {alert['message']}\n")
        
        decision_pack = DecisionPackResponse(
            pack_id=pack_id,
            generated_at=datetime.utcnow().isoformat(),
            model_version=request.model_version,
            recommendations=recommendations,
            monitoring_alerts=alerts,
            scenario_comparisons=twin_scenarios.get("scenarios", {}),
            report_path=report_path
        )
        
        steps[-1].status = "completed"
        steps[-1].completed_at = datetime.utcnow().isoformat()
        steps[-1].duration_ms = (time.time() - step_start) * 1000
        steps[-1].result_summary = {
            "pack_id": pack_id,
            "recommendations": len(recommendations),
            "alerts": len(alerts)
        }
        
        total_duration = (time.time() - start_time) * 1000
        
        return PipelineRunResponse(
            run_id=run_id,
            status="completed",
            steps=steps,
            decision_pack=decision_pack,
            total_duration_ms=total_duration
        )
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        
        # Mark current step as failed
        if steps and steps[-1].status == "running":
            steps[-1].status = "failed"
            steps[-1].error = str(e)
            steps[-1].completed_at = datetime.utcnow().isoformat()
        
        return PipelineRunResponse(
            run_id=run_id,
            status="failed",
            steps=steps,
            decision_pack=None,
            total_duration_ms=(time.time() - start_time) * 1000
        )


@app.get("/reports/{pack_id}")
async def get_report(pack_id: str):
    """Retrieve generated decision pack report"""
    report_path = Path(orchestrator.config.output_path) / f"{pack_id}.md"
    
    if not report_path.exists():
        raise HTTPException(status_code=404, detail=f"Report {pack_id} not found")
    
    return FileResponse(report_path, media_type="text/markdown")


@app.get("/reports")
async def list_reports():
    """List all generated reports"""
    reports_dir = Path(orchestrator.config.output_path)
    
    if not reports_dir.exists():
        return {"reports": []}
    
    reports = []
    for f in reports_dir.glob("*.md"):
        reports.append({
            "pack_id": f.stem,
            "path": str(f),
            "created_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
        })
    
    return {"reports": sorted(reports, key=lambda x: x["created_at"], reverse=True)}


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8084"))
    
    uvicorn.run(app, host=host, port=port)
