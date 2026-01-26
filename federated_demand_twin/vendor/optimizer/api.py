"""
Inventory Optimization API

FastAPI service for inventory optimization.
Provides endpoints for computing optimal reorder points and quantities.

FR-7.1: Compute recommended reorder points and order quantities
FR-7.2: Log objective values and constraint satisfaction for auditability
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

from vendor.optimizer.inventory_optimizer import (
    InventoryOptimizer, OptimizerConfig, InventoryDecision,
    create_optimizer
)
from shared.schemas.data_contracts import (
    OptimizationRequest, OptimizationResult, PosteriorOutcome
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# App Configuration
# =============================================================================

app = FastAPI(
    title="Inventory Optimization API",
    description="Constrained inventory optimization service",
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

optimizer: Optional[InventoryOptimizer] = None


# =============================================================================
# Request/Response Models
# =============================================================================

class OptimizeEntityRequest(BaseModel):
    """Request to optimize a single entity"""
    entity_id: str
    current_inventory: float
    on_order: float = 0.0
    expected_weekly_demand: float
    demand_std: float
    lead_time_weeks: int
    moq: int = 1
    case_pack: int = 1
    unit_cost: float = 10.0
    holding_cost_rate: float = 0.25
    stockout_cost_per_unit: float = 5.0
    ordering_cost: float = 50.0
    min_service_level: float = 0.95
    max_inventory: Optional[float] = None
    budget_constraint: Optional[float] = None
    
    # Posterior from Bayesian engine (optional)
    posterior: Optional[Dict[str, float]] = None


class BatchOptimizeRequest(BaseModel):
    """Request to optimize multiple entities"""
    entities: List[OptimizeEntityRequest]
    global_budget: Optional[float] = None
    warehouse_capacity: Optional[float] = None


class OptimizeResponse(BaseModel):
    """Optimization result response"""
    entity_id: str
    recommended_reorder_point: float
    recommended_order_quantity: int
    expected_service_level: float
    expected_stockout_risk: float
    expected_holding_cost: float
    expected_ordering_cost: float
    total_expected_cost: float
    solver_status: str
    solve_time_ms: float
    constraints_satisfied: Dict[str, bool]


class BatchOptimizeResponse(BaseModel):
    """Batch optimization response"""
    results: List[OptimizeResponse]
    total_investment: float
    total_expected_cost: float
    global_constraints_satisfied: Dict[str, bool]
    solve_time_ms: float


class AuditLogEntry(BaseModel):
    """Audit log entry"""
    timestamp: str
    entity_id: str
    objective_value: float
    solver_status: str
    constraints: Dict[str, Any]


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    optimizer_initialized: bool
    solver_available: bool
    timestamp: str


# =============================================================================
# Lifecycle Events
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize optimizer on startup"""
    global optimizer
    
    config = OptimizerConfig(
        solver_time_limit_seconds=int(os.getenv("SOLVER_TIME_LIMIT", "30")),
        audit_path=os.getenv("AUDIT_PATH", "/app/logs/optimization_audit.json")
    )
    
    optimizer = create_optimizer(config)
    logger.info("Inventory Optimizer initialized")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Inventory Optimizer shutting down")


# =============================================================================
# API Endpoints
# =============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy" if optimizer else "initializing",
        optimizer_initialized=optimizer is not None,
        solver_available=True,
        timestamp=datetime.utcnow().isoformat()
    )


@app.post("/optimize", response_model=OptimizeResponse)
async def optimize_entity(request: OptimizeEntityRequest):
    """
    Optimize inventory policy for a single entity.
    
    Computes recommended reorder point and order quantity under constraints.
    """
    if not optimizer:
        raise HTTPException(status_code=503, detail="Optimizer not initialized")
    
    try:
        import time
        start = time.time()
        
        # Create decision object
        decision = InventoryDecision(
            entity_id=request.entity_id,
            current_inventory=request.current_inventory,
            on_order=request.on_order,
            expected_weekly_demand=request.expected_weekly_demand,
            demand_std=request.demand_std,
            lead_time_weeks=request.lead_time_weeks,
            moq=request.moq,
            case_pack=request.case_pack,
            unit_cost=request.unit_cost,
            holding_cost_rate=request.holding_cost_rate,
            stockout_cost_per_unit=request.stockout_cost_per_unit,
            ordering_cost=request.ordering_cost,
            min_service_level=request.min_service_level,
            max_inventory=request.max_inventory,
            budget_constraint=request.budget_constraint
        )
        
        # Convert posterior if provided
        posterior = None
        if request.posterior:
            posterior = PosteriorOutcome(
                entity_id=request.entity_id,
                scenario_name="api-request",
                stockout_probability=request.posterior.get('stockout_probability', 0.05),
                stockout_ci_lower=request.posterior.get('stockout_ci_lower', 0.01),
                stockout_ci_upper=request.posterior.get('stockout_ci_upper', 0.10),
                expected_margin_impact=request.posterior.get('expected_margin_impact', 0.0),
                margin_ci_lower=request.posterior.get('margin_ci_lower', -100),
                margin_ci_upper=request.posterior.get('margin_ci_upper', 100),
                service_level_estimate=request.posterior.get('service_level_estimate', 0.95),
                computed_at=datetime.utcnow(),
                model_version="api"
            )
        
        # Run optimization
        result = optimizer.optimize_single_entity(
            decision=decision,
            posterior=posterior,
            model_version="api-v1.0.0"
        )
        
        elapsed_ms = (time.time() - start) * 1000
        
        return OptimizeResponse(
            entity_id=result.entity_id,
            recommended_reorder_point=result.recommended_reorder_point,
            recommended_order_quantity=result.recommended_order_quantity,
            expected_service_level=result.expected_service_level,
            expected_stockout_risk=result.expected_stockout_risk,
            expected_holding_cost=result.expected_holding_cost,
            expected_ordering_cost=result.expected_ordering_cost,
            total_expected_cost=result.total_expected_cost,
            solver_status=result.solver_status,
            solve_time_ms=elapsed_ms,
            constraints_satisfied=result.constraints_satisfied
        )
        
    except Exception as e:
        logger.error(f"Optimization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/optimize-batch", response_model=BatchOptimizeResponse)
async def optimize_batch(request: BatchOptimizeRequest):
    """
    Optimize inventory policies for multiple entities with global constraints.
    
    Supports global budget and warehouse capacity constraints.
    """
    if not optimizer:
        raise HTTPException(status_code=503, detail="Optimizer not initialized")
    
    try:
        import time
        start = time.time()
        
        results = []
        total_investment = 0.0
        total_cost = 0.0
        
        for entity_req in request.entities:
            decision = InventoryDecision(
                entity_id=entity_req.entity_id,
                current_inventory=entity_req.current_inventory,
                on_order=entity_req.on_order,
                expected_weekly_demand=entity_req.expected_weekly_demand,
                demand_std=entity_req.demand_std,
                lead_time_weeks=entity_req.lead_time_weeks,
                moq=entity_req.moq,
                case_pack=entity_req.case_pack,
                unit_cost=entity_req.unit_cost,
                holding_cost_rate=entity_req.holding_cost_rate,
                stockout_cost_per_unit=entity_req.stockout_cost_per_unit,
                ordering_cost=entity_req.ordering_cost,
                min_service_level=entity_req.min_service_level
            )
            
            result = optimizer.optimize_single_entity(
                decision=decision,
                posterior=None,
                model_version="api-batch-v1.0.0"
            )
            
            results.append(OptimizeResponse(
                entity_id=result.entity_id,
                recommended_reorder_point=result.recommended_reorder_point,
                recommended_order_quantity=result.recommended_order_quantity,
                expected_service_level=result.expected_service_level,
                expected_stockout_risk=result.expected_stockout_risk,
                expected_holding_cost=result.expected_holding_cost,
                expected_ordering_cost=result.expected_ordering_cost,
                total_expected_cost=result.total_expected_cost,
                solver_status=result.solver_status,
                solve_time_ms=0,
                constraints_satisfied=result.constraints_satisfied
            ))
            
            total_investment += result.recommended_order_quantity * entity_req.unit_cost
            total_cost += result.total_expected_cost
        
        elapsed_ms = (time.time() - start) * 1000
        
        # Check global constraints
        global_satisfied = {}
        if request.global_budget:
            global_satisfied['budget'] = total_investment <= request.global_budget
        if request.warehouse_capacity:
            total_units = sum(r.recommended_order_quantity for r in results)
            global_satisfied['capacity'] = total_units <= request.warehouse_capacity
        
        return BatchOptimizeResponse(
            results=results,
            total_investment=total_investment,
            total_expected_cost=total_cost,
            global_constraints_satisfied=global_satisfied,
            solve_time_ms=elapsed_ms
        )
        
    except Exception as e:
        logger.error(f"Batch optimization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/audit-log", response_model=List[AuditLogEntry])
async def get_audit_log(limit: int = 100):
    """
    Retrieve optimization audit log.
    
    FR-7.2: Provides audit trail for all optimization decisions.
    """
    if not optimizer:
        raise HTTPException(status_code=503, detail="Optimizer not initialized")
    
    try:
        import json
        audit_path = Path(optimizer.config.audit_path)
        
        if not audit_path.exists():
            return []
        
        with open(audit_path, 'r') as f:
            entries = json.load(f)
        
        # Return most recent entries
        return entries[-limit:]
        
    except Exception as e:
        logger.error(f"Failed to retrieve audit log: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8082"))
    
    uvicorn.run(app, host=host, port=port)
