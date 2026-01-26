"""
Digital Twin Simulation API

FastAPI service for the digital twin simulation.
Provides endpoints for state management and scenario simulation.

FR-8.1: Maintain living state representation
FR-8.2: Provide scenario simulation endpoints
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import date, datetime
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from vendor.digital_twin.twin_service import (
    DigitalTwinService, TwinConfig, create_digital_twin
)
from shared.schemas.data_contracts import (
    TwinState, ScenarioRequest, ScenarioResult,
    DemandForecastSummary, HierarchyLevel
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# App Configuration
# =============================================================================

app = FastAPI(
    title="Digital Twin Simulation API",
    description="Stateful inventory simulation and scenario analysis",
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

twin: Optional[DigitalTwinService] = None


# =============================================================================
# Request/Response Models
# =============================================================================

class EntityStateInput(BaseModel):
    """Input for entity state"""
    entity_id: str
    on_hand: float
    on_order: float = 0.0
    backorders: float = 0.0
    expected_weekly_demand: float
    demand_std: float
    lead_time_weeks: int
    moq: int = 1
    case_pack: int = 1
    reorder_point: float
    order_quantity: float
    unit_cost: float = 10.0
    holding_cost_rate: float = 0.25
    stockout_cost: float = 5.0


class InitializeStateRequest(BaseModel):
    """Request to initialize twin state"""
    week_start: date
    entities: List[EntityStateInput]
    forecasts: Optional[List[Dict[str, Any]]] = None


class ScenarioRequestInput(BaseModel):
    """Request for scenario simulation"""
    scenario_name: str
    base_state_id: str
    modifications: Dict[str, Any]
    simulation_weeks: int = 13
    num_simulations: int = 1000


class CompareScenarioRequest(BaseModel):
    """Request to compare multiple scenarios"""
    scenarios: List[ScenarioRequestInput]


class KPIDistribution(BaseModel):
    """KPI distribution from simulation"""
    mean: float
    std: float
    p5: float
    p25: float
    p50: float
    p75: float
    p95: float
    samples: Optional[List[float]] = None


class ScenarioResultResponse(BaseModel):
    """Scenario simulation result"""
    scenario_name: str
    base_state_id: str
    kpi_distributions: Dict[str, KPIDistribution]
    recommended_actions: List[str]
    simulation_count: int
    computation_time_ms: float


class StateResponse(BaseModel):
    """State information response"""
    state_id: str
    week_start: str
    entity_count: int
    total_inventory_value: float
    created_at: str


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    twin_initialized: bool
    active_states: int
    timestamp: str


# =============================================================================
# Lifecycle Events
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize twin on startup"""
    global twin
    
    config = TwinConfig(
        state_store_path=os.getenv("STATE_STORE_PATH", "/app/data/twin_states"),
        default_num_simulations=int(os.getenv("DEFAULT_SIMULATIONS", "1000"))
    )
    
    twin = create_digital_twin(config)
    logger.info("Digital Twin Service initialized")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Digital Twin Service shutting down")


# =============================================================================
# API Endpoints
# =============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy" if twin else "initializing",
        twin_initialized=twin is not None,
        active_states=len(twin.states) if twin else 0,
        timestamp=datetime.utcnow().isoformat()
    )


@app.post("/state/initialize", response_model=StateResponse)
async def initialize_state(request: InitializeStateRequest):
    """
    Initialize a new twin state with entity data.
    
    Creates a snapshot of current inventory positions for simulation.
    """
    if not twin:
        raise HTTPException(status_code=503, detail="Twin not initialized")
    
    try:
        import pandas as pd
        
        # Convert entities to DataFrames
        inventory_data = pd.DataFrame([
            {
                'sku_id': e.entity_id,
                'store_id': 'default',
                'on_hand': e.on_hand,
                'on_order': e.on_order,
                'backorders': e.backorders
            }
            for e in request.entities
        ])
        
        supply_data = pd.DataFrame([
            {
                'sku_id': e.entity_id,
                'supplier_id': 'default',
                'lead_time_weeks': e.lead_time_weeks,
                'moq': e.moq,
                'case_pack': e.case_pack
            }
            for e in request.entities
        ])
        
        # Convert forecasts if provided
        forecast_summaries = []
        if request.forecasts:
            for f in request.forecasts:
                forecast_summaries.append(
                    DemandForecastSummary(
                        entity_id=f['entity_id'],
                        entity_level=HierarchyLevel(f.get('entity_level', 'sku')),
                        week_start=f['week_start'],
                        q10=f['q10'],
                        q50=f['q50'],
                        q90=f['q90'],
                        model_version=f.get('model_version', 'api'),
                        run_id="api-init"
                    )
                )
        
        # Initialize state
        state_id = twin.initialize_state(
            inventory_data=inventory_data,
            supply_params=supply_data,
            forecast_summaries=forecast_summaries if forecast_summaries else None,
            week_start=request.week_start
        )
        
        # Calculate total value
        total_value = sum(
            e.on_hand * e.unit_cost for e in request.entities
        )
        
        return StateResponse(
            state_id=state_id,
            week_start=str(request.week_start),
            entity_count=len(request.entities),
            total_inventory_value=total_value,
            created_at=datetime.utcnow().isoformat()
        )
        
    except Exception as e:
        logger.error(f"State initialization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/state/{state_id}", response_model=Dict[str, Any])
async def get_state(state_id: str):
    """
    Retrieve current twin state.
    """
    if not twin:
        raise HTTPException(status_code=503, detail="Twin not initialized")
    
    if state_id not in twin.states:
        raise HTTPException(status_code=404, detail=f"State {state_id} not found")
    
    state = twin.states[state_id]
    return {
        'state_id': state_id,
        'week_start': str(state.week_start),
        'entities': [e.to_dict() for e in state.entities.values()],
        'created_at': state.created_at.isoformat()
    }


@app.post("/simulate", response_model=ScenarioResultResponse)
async def simulate_scenario(request: ScenarioRequestInput):
    """
    Run Monte Carlo simulation for a single scenario.
    
    Returns KPI distributions based on demand uncertainty.
    """
    if not twin:
        raise HTTPException(status_code=503, detail="Twin not initialized")
    
    try:
        import time
        start = time.time()
        
        # Create scenario request
        scenario = ScenarioRequest(
            scenario_name=request.scenario_name,
            base_state_id=request.base_state_id,
            modifications=request.modifications,
            simulation_weeks=request.simulation_weeks,
            num_simulations=request.num_simulations
        )
        
        # Run simulation
        result = twin.simulate_scenario(scenario)
        
        elapsed_ms = (time.time() - start) * 1000
        
        # Format KPI distributions
        import numpy as np
        kpi_dists = {}
        for kpi_name, samples in result.kpi_distributions.items():
            samples_arr = np.array(samples)
            kpi_dists[kpi_name] = KPIDistribution(
                mean=float(np.mean(samples_arr)),
                std=float(np.std(samples_arr)),
                p5=float(np.percentile(samples_arr, 5)),
                p25=float(np.percentile(samples_arr, 25)),
                p50=float(np.percentile(samples_arr, 50)),
                p75=float(np.percentile(samples_arr, 75)),
                p95=float(np.percentile(samples_arr, 95)),
                samples=samples[:100] if len(samples) > 100 else samples  # Limit samples returned
            )
        
        return ScenarioResultResponse(
            scenario_name=result.scenario_name,
            base_state_id=result.base_state_id,
            kpi_distributions=kpi_dists,
            recommended_actions=result.recommended_actions,
            simulation_count=request.num_simulations,
            computation_time_ms=elapsed_ms
        )
        
    except Exception as e:
        logger.error(f"Simulation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/compare-scenarios", response_model=Dict[str, ScenarioResultResponse])
async def compare_scenarios(request: CompareScenarioRequest):
    """
    Compare multiple scenarios and return KPI distributions for each.
    
    Enables decision support by contrasting baseline vs. alternatives.
    """
    if not twin:
        raise HTTPException(status_code=503, detail="Twin not initialized")
    
    try:
        import time
        import numpy as np
        start = time.time()
        
        # Convert to ScenarioRequest objects
        scenarios = [
            ScenarioRequest(
                scenario_name=s.scenario_name,
                base_state_id=s.base_state_id,
                modifications=s.modifications,
                simulation_weeks=s.simulation_weeks,
                num_simulations=s.num_simulations
            )
            for s in request.scenarios
        ]
        
        # Run comparisons
        results = twin.compare_scenarios(scenarios)
        
        elapsed_ms = (time.time() - start) * 1000
        
        # Format responses
        responses = {}
        for scenario_name, result in results.items():
            kpi_dists = {}
            for kpi_name, samples in result.kpi_distributions.items():
                samples_arr = np.array(samples)
                kpi_dists[kpi_name] = KPIDistribution(
                    mean=float(np.mean(samples_arr)),
                    std=float(np.std(samples_arr)),
                    p5=float(np.percentile(samples_arr, 5)),
                    p25=float(np.percentile(samples_arr, 25)),
                    p50=float(np.percentile(samples_arr, 50)),
                    p75=float(np.percentile(samples_arr, 75)),
                    p95=float(np.percentile(samples_arr, 95))
                )
            
            responses[scenario_name] = ScenarioResultResponse(
                scenario_name=result.scenario_name,
                base_state_id=result.base_state_id,
                kpi_distributions=kpi_dists,
                recommended_actions=result.recommended_actions,
                simulation_count=request.scenarios[0].num_simulations,
                computation_time_ms=elapsed_ms / len(request.scenarios)
            )
        
        return responses
        
    except Exception as e:
        logger.error(f"Scenario comparison failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/feed-to-bayesian/{state_id}")
async def get_scenarios_for_bayesian(
    state_id: str,
    scenarios: List[str] = ["baseline", "demand_surge", "lead_time_increase"]
):
    """
    Generate scenario results formatted for Bayesian engine consumption.
    
    This endpoint enables the Twin → Bayesian data flow.
    """
    if not twin:
        raise HTTPException(status_code=503, detail="Twin not initialized")
    
    if state_id not in twin.states:
        raise HTTPException(status_code=404, detail=f"State {state_id} not found")
    
    try:
        import numpy as np
        
        # Define scenario modifications
        scenario_mods = {
            "baseline": {},
            "demand_surge": {"demand_multiplier": 1.3},
            "lead_time_increase": {"lead_time_delta": 2},
            "supply_disruption": {"supply_availability": 0.7},
            "promo_campaign": {"promo_effect": 0.25}
        }
        
        # Run simulations for requested scenarios
        results_for_bayesian = {}
        
        for scenario_name in scenarios:
            if scenario_name not in scenario_mods:
                continue
            
            scenario = ScenarioRequest(
                scenario_name=scenario_name,
                base_state_id=state_id,
                modifications=scenario_mods[scenario_name],
                simulation_weeks=13,
                num_simulations=500
            )
            
            result = twin.simulate_scenario(scenario)
            
            # Format for Bayesian engine
            results_for_bayesian[scenario_name] = {
                'kpi_distributions': {
                    kpi: samples for kpi, samples in result.kpi_distributions.items()
                },
                'summary_stats': {
                    kpi: {
                        'mean': float(np.mean(samples)),
                        'std': float(np.std(samples)),
                        'ci_lower': float(np.percentile(samples, 5)),
                        'ci_upper': float(np.percentile(samples, 95))
                    }
                    for kpi, samples in result.kpi_distributions.items()
                },
                'recommended_actions': result.recommended_actions
            }
        
        return {
            'state_id': state_id,
            'scenarios': results_for_bayesian,
            'ready_for_bayesian': True
        }
        
    except Exception as e:
        logger.error(f"Failed to prepare scenarios for Bayesian: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8083"))
    
    uvicorn.run(app, host=host, port=port)
