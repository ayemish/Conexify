"""
Retail Media Optimization API

FastAPI endpoints for the retail media spend optimization system.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging
import numpy as np

from .schemas import (
    MediaChannel,
    RetailerConfig,
    ChannelConfig,
    SKUConfig,
    MediaAllocation,
    AllocationStatus,
)

from .orchestrator import (
    RetailMediaOrchestrator,
    OrchestratorConfig,
)

from .bayesian_engine import BayesianEngineConfig
from .media_twin import TwinConfig
from .agents import AgentConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Retail Media Optimization API",
    description="Bayesian → Digital Twin → Agent pipeline for retail media spend optimization",
    version="1.0.0"
)

# Global orchestrator instance
orchestrator: Optional[RetailMediaOrchestrator] = None


# ============================================================================
# Pydantic Models for API
# ============================================================================

class RetailerConfigRequest(BaseModel):
    retailer_id: str
    retailer_name: str
    available_channels: List[str] = []
    min_quarterly_spend: float = 0.0
    max_quarterly_spend: float = 1e9
    min_spend_share: float = 0.0
    avg_inventory_weeks: float = 4.0
    stockout_sensitivity: float = 1.0
    tier: str = "standard"
    attribution_quality: float = 0.8


class ChannelConfigRequest(BaseModel):
    channel: str
    min_spend: float = 0.0
    max_spend: float = 1e9
    cpm: float = 10.0
    prior_elasticity_mean: float = 0.15
    prior_elasticity_std: float = 0.05
    adstock_decay: float = 0.7


class SKUConfigRequest(BaseModel):
    sku_id: str
    sku_name: str
    category: str
    brand: str
    unit_price: float
    unit_cost: float
    weekly_base_demand: float = 100.0
    demand_std: float = 20.0
    lead_time_weeks: int = 2
    media_responsiveness: float = 1.0


class TwinStateRequest(BaseModel):
    retailer_id: str
    sku_id: str
    initial_inventory: float
    base_demand_mean: float
    base_demand_std: float


class ElasticityUpdateRequest(BaseModel):
    retailer_id: str
    channel: str
    category: str
    spend_history: List[float]
    sales_lift_history: List[float]


class AllocationRequest(BaseModel):
    allocation_id: str
    name: str
    total_budget: float
    period_weeks: int
    spend_by_retailer_channel: Dict[str, Dict[str, float]]


class PipelineRequest(BaseModel):
    current_allocation: AllocationRequest
    total_budget: float
    period_weeks: int
    conversion_paths: Optional[List[List[str]]] = None
    spend_history: Optional[Dict[str, float]] = None
    total_incremental_sales: Optional[float] = None


class QuickAnalysisRequest(BaseModel):
    allocation: AllocationRequest
    demand_multiplier: float = 1.0
    supply_disruption: float = 0.0
    elasticity_multiplier: float = 1.0


class PipelineResponse(BaseModel):
    pack_id: str
    status: str
    recommendation: Dict[str, Any]
    executive_summary: str
    confidence: float
    governance_approved: Optional[bool]


class SimulationResponse(BaseModel):
    scenario_id: str
    scenario_name: str
    expected_sales: float
    sales_ci: List[float]
    expected_roas: float
    expected_stockout_rate: float
    binding_constraints: List[str]


# ============================================================================
# Lifecycle Endpoints
# ============================================================================

@app.on_event("startup")
async def startup():
    """Initialize orchestrator on startup"""
    global orchestrator
    orchestrator = RetailMediaOrchestrator(
        config=OrchestratorConfig(),
        bayesian_config=BayesianEngineConfig(),
        twin_config=TwinConfig(),
        agent_config=AgentConfig()
    )
    logger.info("Retail Media Optimization API started")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "orchestrator_initialized": orchestrator is not None,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/status")
async def get_status():
    """Get current system status"""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    
    return orchestrator.get_pipeline_status()


# ============================================================================
# Configuration Endpoints
# ============================================================================

@app.post("/config/retailer")
async def register_retailer(request: RetailerConfigRequest):
    """Register a retailer configuration"""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    
    config = RetailerConfig(
        retailer_id=request.retailer_id,
        retailer_name=request.retailer_name,
        available_channels=[MediaChannel(c) for c in request.available_channels],
        min_quarterly_spend=request.min_quarterly_spend,
        max_quarterly_spend=request.max_quarterly_spend,
        min_spend_share=request.min_spend_share,
        avg_inventory_weeks=request.avg_inventory_weeks,
        stockout_sensitivity=request.stockout_sensitivity,
        tier=request.tier,
        attribution_quality=request.attribution_quality
    )
    
    orchestrator.register_retailer(config)
    
    return {"status": "registered", "retailer_id": request.retailer_id}


@app.post("/config/channel")
async def register_channel(request: ChannelConfigRequest):
    """Register a channel configuration"""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    
    config = ChannelConfig(
        channel=MediaChannel(request.channel),
        min_spend=request.min_spend,
        max_spend=request.max_spend,
        cpm=request.cpm,
        prior_elasticity_mean=request.prior_elasticity_mean,
        prior_elasticity_std=request.prior_elasticity_std,
        adstock_decay=request.adstock_decay
    )
    
    orchestrator.register_channel(config)
    
    return {"status": "registered", "channel": request.channel}


@app.post("/config/sku")
async def register_sku(request: SKUConfigRequest):
    """Register a SKU configuration"""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    
    config = SKUConfig(
        sku_id=request.sku_id,
        sku_name=request.sku_name,
        category=request.category,
        brand=request.brand,
        unit_price=request.unit_price,
        unit_cost=request.unit_cost,
        weekly_base_demand=request.weekly_base_demand,
        demand_std=request.demand_std,
        lead_time_weeks=request.lead_time_weeks,
        media_responsiveness=request.media_responsiveness
    )
    
    orchestrator.register_sku(config)
    
    return {"status": "registered", "sku_id": request.sku_id}


# ============================================================================
# Twin State Endpoints
# ============================================================================

@app.post("/twin/initialize-state")
async def initialize_twin_state(request: TwinStateRequest):
    """Initialize Digital Twin state for a retailer-SKU combination"""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    
    orchestrator.initialize_twin_state(
        retailer_id=request.retailer_id,
        sku_id=request.sku_id,
        initial_inventory=request.initial_inventory,
        base_demand_mean=request.base_demand_mean,
        base_demand_std=request.base_demand_std
    )
    
    return {
        "status": "initialized",
        "retailer_id": request.retailer_id,
        "sku_id": request.sku_id
    }


@app.get("/twin/state-summary")
async def get_twin_state_summary():
    """Get summary of current Twin state"""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    
    return orchestrator.twin.get_state_summary()


# ============================================================================
# Bayesian Analysis Endpoints
# ============================================================================

@app.post("/bayesian/update-elasticity")
async def update_elasticity(request: ElasticityUpdateRequest):
    """
    Update elasticity posterior from retailer data.
    
    This is the federated learning entry point.
    """
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    
    try:
        channel = MediaChannel(request.channel)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid channel: {request.channel}")
    
    posterior = orchestrator.update_elasticity_from_retailer_data(
        retailer_id=request.retailer_id,
        channel=channel,
        category=request.category,
        spend_history=np.array(request.spend_history),
        sales_lift_history=np.array(request.sales_lift_history)
    )
    
    return {
        "status": "updated",
        "posterior": posterior.to_dict()
    }


@app.get("/bayesian/posteriors/{retailer_id}")
async def get_posteriors(retailer_id: str):
    """Get all elasticity posteriors for a retailer"""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    
    posteriors = {}
    for channel in MediaChannel:
        for sku in orchestrator.bayesian_engine.skus.values():
            key = f"{channel.value}:{sku.category}"
            post = orchestrator.bayesian_engine.get_elasticity_posterior(
                retailer_id, channel, sku.category
            )
            posteriors[key] = post.to_dict()
    
    return {"retailer_id": retailer_id, "posteriors": posteriors}


@app.get("/bayesian/federated-posteriors")
async def get_federated_posteriors():
    """Get globally aggregated (federated) posteriors"""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    
    global_posteriors = orchestrator.bayesian_engine.federated_aggregator.get_all_global_posteriors()
    
    return {
        "source": "federated_aggregation",
        "posteriors": {k: v.to_dict() for k, v in global_posteriors.items()}
    }


# ============================================================================
# Pipeline Endpoints
# ============================================================================

@app.post("/pipeline/run", response_model=PipelineResponse)
async def run_pipeline(request: PipelineRequest, background_tasks: BackgroundTasks):
    """
    Run the complete optimization pipeline.
    
    Steps:
    1. Bayesian calibration (posteriors → Twin)
    2. Attribution analysis (optional)
    3. Scenario generation
    4. Twin simulation
    5. Optimization
    6. Governance validation
    7. Rationale generation
    """
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    
    # Convert request to MediaAllocation
    current_allocation = MediaAllocation(
        allocation_id=request.current_allocation.allocation_id,
        name=request.current_allocation.name,
        total_budget=request.current_allocation.total_budget,
        period_weeks=request.current_allocation.period_weeks,
        spend_by_retailer_channel=request.current_allocation.spend_by_retailer_channel
    )
    
    try:
        decision_pack = orchestrator.run_pipeline(
            current_allocation=current_allocation,
            total_budget=request.total_budget,
            period_weeks=request.period_weeks,
            conversion_paths=request.conversion_paths,
            spend_history=request.spend_history,
            total_incremental_sales=request.total_incremental_sales
        )
        
        return PipelineResponse(
            pack_id=decision_pack.pack_id,
            status="completed",
            recommendation={
                "allocation_id": decision_pack.recommended_allocation.allocation_id,
                "total_budget": decision_pack.recommended_allocation.total_budget,
                "spend_by_retailer_channel": decision_pack.recommended_allocation.spend_by_retailer_channel,
            },
            executive_summary=decision_pack.executive_summary,
            confidence=decision_pack.overall_confidence,
            governance_approved=decision_pack.governance_decision.approved if decision_pack.governance_decision else None
        )
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pipeline/quick-analysis", response_model=SimulationResponse)
async def quick_analysis(request: QuickAnalysisRequest):
    """
    Run a quick single-scenario analysis.
    
    Useful for ad-hoc what-if analysis.
    """
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    
    allocation = MediaAllocation(
        allocation_id=request.allocation.allocation_id,
        name=request.allocation.name,
        total_budget=request.allocation.total_budget,
        period_weeks=request.allocation.period_weeks,
        spend_by_retailer_channel=request.allocation.spend_by_retailer_channel
    )
    
    result = orchestrator.run_quick_scenario_analysis(
        allocation=allocation,
        scenario_modifications={
            'demand_multiplier': request.demand_multiplier,
            'supply_disruption': request.supply_disruption,
            'elasticity_multiplier': request.elasticity_multiplier,
        }
    )
    
    return SimulationResponse(
        scenario_id=result.scenario_id,
        scenario_name=result.scenario_name,
        expected_sales=result.expected_incremental_sales,
        sales_ci=[result.sales_ci_lower, result.sales_ci_upper],
        expected_roas=result.expected_roas,
        expected_stockout_rate=result.expected_stockout_rate,
        binding_constraints=result.binding_constraints
    )


# ============================================================================
# Decision Pack Endpoints
# ============================================================================

@app.get("/decision-packs")
async def list_decision_packs():
    """List recent decision packs"""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    
    return {
        "runs": orchestrator.run_history[-10:],  # Last 10 runs
        "total_runs": len(orchestrator.run_history)
    }


@app.get("/decision-packs/{pack_id}")
async def get_decision_pack(pack_id: str):
    """Get a specific decision pack by ID"""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    
    # Look for the pack in history
    for run in orchestrator.run_history:
        if run.get('run_id') == pack_id:
            return run
    
    raise HTTPException(status_code=404, detail=f"Decision pack {pack_id} not found")


# ============================================================================
# Agent Endpoints
# ============================================================================

@app.get("/agents/attribution/history")
async def get_attribution_history():
    """Get attribution analysis history"""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    
    return {
        "history": [
            a.to_dict() for a in orchestrator.attribution_agent.attribution_history[-10:]
        ]
    }


@app.get("/agents/status")
async def get_agent_status():
    """Get status of all agents"""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    
    return {
        "attribution_agent": {
            "history_size": len(orchestrator.attribution_agent.attribution_history)
        },
        "scenario_agent": {
            "max_scenarios": orchestrator.scenario_agent.config.max_scenarios
        },
        "optimization_agent": {
            "risk_aversion": orchestrator.optimization_agent.config.risk_aversion
        },
        "governance_agent": {
            "max_stockout_rate": orchestrator.governance_agent.config.max_stockout_rate,
            "max_allocation_change": orchestrator.governance_agent.config.max_allocation_change
        },
        "rationale_agent": {
            "llm_model": orchestrator.rationale_agent.config.llm_model
        }
    }


# ============================================================================
# Demo Data Endpoint
# ============================================================================

@app.post("/demo/setup")
async def setup_demo_data():
    """
    Setup demo data for testing the pipeline.
    
    Creates sample retailers, channels, SKUs, and initial states.
    """
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    
    # Register channels
    for channel in MediaChannel:
        orchestrator.register_channel(ChannelConfig(channel=channel))
    
    # Register demo retailers
    demo_retailers = [
        RetailerConfig(
            retailer_id="walmart",
            retailer_name="Walmart",
            available_channels=[MediaChannel.SPONSORED_SEARCH, MediaChannel.IN_STORE_DISPLAY, MediaChannel.WEBSITE_BANNER],
            min_spend_share=0.10,
            avg_inventory_weeks=5.0,
            stockout_sensitivity=0.8,
            tier="premium"
        ),
        RetailerConfig(
            retailer_id="kroger",
            retailer_name="Kroger",
            available_channels=[MediaChannel.SPONSORED_SEARCH, MediaChannel.IN_STORE_DISPLAY, MediaChannel.EMAIL],
            min_spend_share=0.08,
            avg_inventory_weeks=4.0,
            stockout_sensitivity=1.0,
            tier="premium"
        ),
        RetailerConfig(
            retailer_id="target",
            retailer_name="Target",
            available_channels=[MediaChannel.SPONSORED_SEARCH, MediaChannel.CONNECTED_TV, MediaChannel.APP_NOTIFICATION],
            min_spend_share=0.07,
            avg_inventory_weeks=4.5,
            stockout_sensitivity=0.9,
            tier="premium"
        ),
        RetailerConfig(
            retailer_id="costco",
            retailer_name="Costco",
            available_channels=[MediaChannel.IN_STORE_DISPLAY, MediaChannel.EMAIL],
            min_spend_share=0.05,
            avg_inventory_weeks=6.0,
            stockout_sensitivity=0.7,
            tier="standard"
        ),
    ]
    
    for retailer in demo_retailers:
        orchestrator.register_retailer(retailer)
    
    # Register demo SKUs
    demo_skus = [
        SKUConfig(sku_id="bev-001", sku_name="Sparkling Water 12pk", category="beverages", brand="DemoBrand", unit_price=6.99, unit_cost=3.50),
        SKUConfig(sku_id="bev-002", sku_name="Energy Drink 4pk", category="beverages", brand="DemoBrand", unit_price=9.99, unit_cost=5.00),
        SKUConfig(sku_id="snk-001", sku_name="Protein Bar 6pk", category="snacks", brand="DemoBrand", unit_price=12.99, unit_cost=6.50),
        SKUConfig(sku_id="snk-002", sku_name="Trail Mix 16oz", category="snacks", brand="DemoBrand", unit_price=7.99, unit_cost=4.00),
    ]
    
    for sku in demo_skus:
        orchestrator.register_sku(sku)
    
    # Initialize Twin states
    for retailer in demo_retailers:
        for sku in demo_skus:
            orchestrator.initialize_twin_state(
                retailer_id=retailer.retailer_id,
                sku_id=sku.sku_id,
                initial_inventory=sku.weekly_base_demand * 4,
                base_demand_mean=sku.weekly_base_demand * (1 + np.random.uniform(-0.2, 0.2)),
                base_demand_std=sku.demand_std
            )
    
    # Add some historical elasticity data
    for retailer in demo_retailers:
        for channel in retailer.available_channels:
            for category in ["beverages", "snacks"]:
                # Generate synthetic spend/lift history
                n_weeks = 26
                spend = np.random.uniform(10000, 100000, n_weeks)
                base_elasticity = 0.15 + np.random.uniform(-0.05, 0.10)
                lift = spend * base_elasticity / 50000 * (1 + np.random.normal(0, 0.1, n_weeks))
                
                orchestrator.update_elasticity_from_retailer_data(
                    retailer_id=retailer.retailer_id,
                    channel=channel,
                    category=category,
                    spend_history=spend,
                    sales_lift_history=np.maximum(0.01, lift)
                )
    
    return {
        "status": "demo_data_created",
        "retailers": len(demo_retailers),
        "skus": len(demo_skus),
        "twin_states": len(demo_retailers) * len(demo_skus)
    }
