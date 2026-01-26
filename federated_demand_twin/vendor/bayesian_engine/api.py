"""
Bayesian Decision Engine API

FastAPI service for the Bayesian decision engine.
Provides endpoints for uncertainty quantification and scenario analysis.

FR-6.1: Ingest forecast distributions and output posterior distributions
FR-6.2: Support scenario comparison with posterior intervals
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

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from vendor.bayesian_engine.decision_engine import (
    BayesianDecisionEngine, BayesianEngineConfig, DemandDistribution,
    create_bayesian_engine
)
from shared.schemas.data_contracts import (
    DemandForecastSummary, BayesianInput, PosteriorOutcome,
    HierarchyLevel
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# App Configuration
# =============================================================================

app = FastAPI(
    title="Bayesian Decision Engine API",
    description="Uncertainty quantification and scenario analysis for demand forecasting",
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

# Global engine instance
engine: Optional[BayesianDecisionEngine] = None


# =============================================================================
# Request/Response Models
# =============================================================================

class ForecastInput(BaseModel):
    """Forecast quantiles for a single period"""
    week_start: date
    q10: float
    q50: float
    q90: float


class InventoryStateInput(BaseModel):
    """Current inventory state"""
    on_hand: float
    on_order: float = 0.0
    backorders: float = 0.0


class SupplyParamsInput(BaseModel):
    """Supply chain parameters"""
    lead_time_weeks: int
    moq: int = 1
    case_pack: int = 1


class AnalyzeEntityRequest(BaseModel):
    """Request to analyze a single entity"""
    entity_id: str
    entity_level: str = "sku"
    forecasts: List[ForecastInput]
    inventory_state: InventoryStateInput
    supply_params: SupplyParamsInput
    model_version: str = "v1.0.0"
    scenarios: Optional[List[str]] = None


class ScenarioComparisonRequest(BaseModel):
    """Request for scenario comparison"""
    entity_id: str
    forecasts: List[ForecastInput]
    inventory_state: InventoryStateInput
    supply_params: SupplyParamsInput
    scenarios: Dict[str, Dict[str, Any]]  # scenario_name -> modifications


class PosteriorResponse(BaseModel):
    """Posterior outcome response"""
    entity_id: str
    scenario_name: str
    stockout_probability: float
    stockout_ci_lower: float
    stockout_ci_upper: float
    expected_margin_impact: float
    margin_ci_lower: float
    margin_ci_upper: float
    service_level_estimate: float
    weeks_of_supply: float
    computation_time_ms: float


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    engine_initialized: bool
    cache_enabled: bool
    timestamp: str


# =============================================================================
# Lifecycle Events
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize engine on startup"""
    global engine
    
    config = BayesianEngineConfig(
        num_samples=int(os.getenv("NUM_SAMPLES", "2000")),
        cache_posteriors=True,
        cache_path=os.getenv("CACHE_PATH", "/app/cache/bayesian")
    )
    
    engine = create_bayesian_engine(config)
    logger.info("Bayesian Decision Engine initialized")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Bayesian Decision Engine shutting down")


# =============================================================================
# API Endpoints
# =============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy" if engine else "initializing",
        engine_initialized=engine is not None,
        cache_enabled=engine.config.cache_posteriors if engine else False,
        timestamp=datetime.utcnow().isoformat()
    )


@app.post("/analyze", response_model=Dict[str, PosteriorResponse])
async def analyze_entity(request: AnalyzeEntityRequest):
    """
    Analyze a single entity and compute posterior distributions.
    
    Returns posteriors for stockout risk, margin impact, and service level.
    """
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    try:
        # Convert forecasts to summaries
        forecast_summaries = [
            DemandForecastSummary(
                entity_id=request.entity_id,
                entity_level=HierarchyLevel(request.entity_level),
                week_start=f.week_start,
                q10=f.q10,
                q50=f.q50,
                q90=f.q90,
                model_version=request.model_version,
                run_id="api-request"
            )
            for f in request.forecasts
        ]
        
        # Run analysis
        import time
        start = time.time()
        
        result = engine.analyze_entity(
            entity_id=request.entity_id,
            forecast_summaries=forecast_summaries,
            inventory_state={
                'on_hand': request.inventory_state.on_hand,
                'on_order': request.inventory_state.on_order,
                'backorders': request.inventory_state.backorders
            },
            supply_params={
                'lead_time_weeks': request.supply_params.lead_time_weeks,
                'moq': request.supply_params.moq,
                'case_pack': request.supply_params.case_pack
            },
            model_version=request.model_version
        )
        
        elapsed_ms = (time.time() - start) * 1000
        
        # Format response
        responses = {}
        for scenario_name, outcome_data in result.get('outcomes', {}).items():
            responses[scenario_name] = PosteriorResponse(
                entity_id=request.entity_id,
                scenario_name=scenario_name,
                stockout_probability=outcome_data.get('stockout_probability', 0.0),
                stockout_ci_lower=outcome_data.get('stockout_ci_lower', 0.0),
                stockout_ci_upper=outcome_data.get('stockout_ci_upper', 0.0),
                expected_margin_impact=outcome_data.get('expected_margin_impact', 0.0),
                margin_ci_lower=outcome_data.get('margin_ci_lower', 0.0),
                margin_ci_upper=outcome_data.get('margin_ci_upper', 0.0),
                service_level_estimate=outcome_data.get('service_level_estimate', 0.95),
                weeks_of_supply=outcome_data.get('weeks_of_supply', 0.0),
                computation_time_ms=elapsed_ms
            )
        
        return responses
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/compare-scenarios", response_model=Dict[str, PosteriorResponse])
async def compare_scenarios(request: ScenarioComparisonRequest):
    """
    Compare multiple scenarios and return posterior distributions for each.
    
    Enables decision support by contrasting baseline vs. alternative policies.
    """
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    try:
        import time
        start = time.time()
        
        # Convert forecasts
        forecast_summaries = [
            DemandForecastSummary(
                entity_id=request.entity_id,
                entity_level=HierarchyLevel.SKU,
                week_start=f.week_start,
                q10=f.q10,
                q50=f.q50,
                q90=f.q90,
                model_version="api-request",
                run_id="scenario-comparison"
            )
            for f in request.forecasts
        ]
        
        # Run scenario comparison
        results = engine.compare_scenarios(
            entity_id=request.entity_id,
            forecast_summaries=forecast_summaries,
            inventory_state={
                'on_hand': request.inventory_state.on_hand,
                'on_order': request.inventory_state.on_order
            },
            supply_params={
                'lead_time_weeks': request.supply_params.lead_time_weeks,
                'moq': request.supply_params.moq,
                'case_pack': request.supply_params.case_pack
            },
            scenarios=request.scenarios
        )
        
        elapsed_ms = (time.time() - start) * 1000
        
        # Format response
        responses = {}
        for scenario_name, outcome_data in results.items():
            responses[scenario_name] = PosteriorResponse(
                entity_id=request.entity_id,
                scenario_name=scenario_name,
                stockout_probability=outcome_data.get('stockout_probability', 0.0),
                stockout_ci_lower=outcome_data.get('stockout_ci_lower', 0.0),
                stockout_ci_upper=outcome_data.get('stockout_ci_upper', 0.0),
                expected_margin_impact=outcome_data.get('expected_margin_impact', 0.0),
                margin_ci_lower=outcome_data.get('margin_ci_lower', 0.0),
                margin_ci_upper=outcome_data.get('margin_ci_upper', 0.0),
                service_level_estimate=outcome_data.get('service_level_estimate', 0.95),
                weeks_of_supply=outcome_data.get('weeks_of_supply', 0.0),
                computation_time_ms=elapsed_ms / len(request.scenarios)
            )
        
        return responses
        
    except Exception as e:
        logger.error(f"Scenario comparison failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze-with-twin-scenarios")
async def analyze_with_twin_scenarios(
    entity_id: str,
    twin_scenario_results: Dict[str, Any],
    model_version: str = "v1.0.0"
):
    """
    Analyze entity using scenario results from Digital Twin.
    
    This endpoint connects Twin → Bayesian for scenario-informed posteriors.
    """
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    try:
        # Extract scenario KPIs from twin results
        posteriors = {}
        
        for scenario_name, scenario_data in twin_scenario_results.items():
            kpi_distributions = scenario_data.get('kpi_distributions', {})
            
            # Convert twin Monte Carlo results to Bayesian posteriors
            stockout_samples = kpi_distributions.get('stockout_probability', [0.05])
            margin_samples = kpi_distributions.get('margin_impact', [0.0])
            service_samples = kpi_distributions.get('service_level', [0.95])
            
            import numpy as np
            posteriors[scenario_name] = {
                'entity_id': entity_id,
                'scenario_name': scenario_name,
                'stockout_probability': float(np.mean(stockout_samples)),
                'stockout_ci_lower': float(np.percentile(stockout_samples, 5)),
                'stockout_ci_upper': float(np.percentile(stockout_samples, 95)),
                'expected_margin_impact': float(np.mean(margin_samples)),
                'margin_ci_lower': float(np.percentile(margin_samples, 5)),
                'margin_ci_upper': float(np.percentile(margin_samples, 95)),
                'service_level_estimate': float(np.mean(service_samples)),
                'model_version': model_version
            }
        
        return posteriors
        
    except Exception as e:
        logger.error(f"Twin-informed analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8081"))
    
    uvicorn.run(app, host=host, port=port)
