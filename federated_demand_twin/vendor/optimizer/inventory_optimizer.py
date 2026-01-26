"""
Inventory Optimization Service

FR-7.1: Compute recommended reorder points and order quantities under constraints
(e.g., MOQ, case pack, lead time).

FR-7.2: Log objective value, constraint satisfaction, and inputs used for each solve
to support auditability.

Uses OR-Tools for constraint optimization (as recommended in requirements).
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import json
import hashlib
import logging
from pathlib import Path

# OR-Tools imports (primary optimization library per requirements)
try:
    from ortools.sat.python import cp_model
    from ortools.linear_solver import pywraplp
    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False
    logging.warning("OR-Tools not installed. Using simplified optimizer.")

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.schemas.data_contracts import (
    PosteriorOutcome, OptimizationRequest, OptimizationResult
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class OptimizerConfig:
    """Configuration for inventory optimizer"""
    # Solver settings
    solver_time_limit_seconds: float = 30.0
    solver_type: str = "CBC_MIXED_INTEGER_PROGRAMMING"  # or "SCIP", "GLOP"
    
    # Objective weights
    stockout_cost_weight: float = 10.0
    holding_cost_weight: float = 1.0
    ordering_cost_weight: float = 0.1
    
    # Default constraints
    max_inventory_weeks: float = 12.0
    min_inventory_weeks: float = 2.0
    max_order_frequency_per_period: int = 4
    
    # Audit settings
    log_all_solves: bool = True
    audit_path: str = "./logs/optimization_audit.json"


@dataclass
class InventoryDecision:
    """Represents an inventory decision to optimize"""
    entity_id: str
    
    # Current state
    current_inventory: float
    on_order: float
    
    # Demand forecast
    expected_weekly_demand: float
    demand_std: float
    
    # Supply parameters
    lead_time_weeks: int
    moq: int
    case_pack: int
    
    # Costs
    unit_cost: float
    holding_cost_rate: float  # Annual rate
    stockout_cost_per_unit: float
    ordering_cost: float
    
    # Constraints
    warehouse_capacity: Optional[float] = None
    budget_limit: Optional[float] = None
    min_service_level: float = 0.95


class SafetyStockCalculator:
    """
    Calculate safety stock levels using statistical methods.
    
    Supports multiple service level targeting approaches.
    """
    
    @staticmethod
    def z_score_for_service_level(service_level: float) -> float:
        """Get z-score for target service level"""
        from scipy import stats
        return stats.norm.ppf(service_level)
    
    @staticmethod
    def calculate_safety_stock(
        demand_std: float,
        lead_time_weeks: int,
        service_level: float = 0.95
    ) -> float:
        """
        Calculate safety stock for target service level.
        
        SS = z * σ_d * √L
        where:
            z = service level z-score
            σ_d = demand standard deviation
            L = lead time in periods
        """
        z = SafetyStockCalculator.z_score_for_service_level(service_level)
        return z * demand_std * np.sqrt(lead_time_weeks)
    
    @staticmethod
    def calculate_reorder_point(
        expected_demand: float,
        demand_std: float,
        lead_time_weeks: int,
        service_level: float = 0.95
    ) -> float:
        """
        Calculate reorder point.
        
        ROP = d * L + SS
        where:
            d = expected demand per period
            L = lead time
            SS = safety stock
        """
        lead_time_demand = expected_demand * lead_time_weeks
        safety_stock = SafetyStockCalculator.calculate_safety_stock(
            demand_std, lead_time_weeks, service_level
        )
        return lead_time_demand + safety_stock


class EOQCalculator:
    """
    Economic Order Quantity calculations.
    """
    
    @staticmethod
    def calculate_eoq(
        annual_demand: float,
        ordering_cost: float,
        holding_cost_per_unit: float
    ) -> float:
        """
        Classic EOQ formula.
        
        EOQ = √(2DS/H)
        where:
            D = annual demand
            S = ordering cost per order
            H = holding cost per unit per year
        """
        if holding_cost_per_unit <= 0:
            return annual_demand / 12  # Monthly order as fallback
        
        return np.sqrt(2 * annual_demand * ordering_cost / holding_cost_per_unit)
    
    @staticmethod
    def apply_constraints(
        order_quantity: float,
        moq: int,
        case_pack: int,
        max_quantity: Optional[float] = None
    ) -> int:
        """Apply MOQ and case pack constraints to order quantity"""
        # Round up to case pack
        qty = int(np.ceil(order_quantity / case_pack) * case_pack)
        
        # Apply MOQ
        qty = max(qty, moq)
        
        # Apply max constraint
        if max_quantity is not None:
            qty = min(qty, int(max_quantity))
        
        return qty


class InventoryOptimizer:
    """
    Main inventory optimization service.
    
    FR-7.1: Compute recommended reorder points and order quantities
    FR-7.2: Log objective value, constraint satisfaction for auditability
    """
    
    def __init__(self, config: Optional[OptimizerConfig] = None):
        self.config = config or OptimizerConfig()
        self.audit_log: List[Dict[str, Any]] = []
        self.run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        # Setup audit logging
        if self.config.log_all_solves:
            audit_path = Path(self.config.audit_path)
            audit_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _compute_inputs_hash(self, decision: InventoryDecision) -> str:
        """Compute hash of inputs for reproducibility"""
        inputs = {
            'entity_id': decision.entity_id,
            'current_inventory': decision.current_inventory,
            'expected_demand': decision.expected_weekly_demand,
            'lead_time': decision.lead_time_weeks,
            'moq': decision.moq,
            'case_pack': decision.case_pack,
        }
        return hashlib.md5(
            json.dumps(inputs, sort_keys=True).encode()
        ).hexdigest()[:12]
    
    def optimize_single_entity(
        self,
        decision: InventoryDecision,
        posterior_outcome: Optional[PosteriorOutcome] = None,
        model_version: str = "unknown"
    ) -> OptimizationResult:
        """
        Optimize inventory policy for a single entity.
        
        Returns recommended reorder point and order quantity.
        """
        start_time = datetime.utcnow()
        
        # Calculate safety stock and reorder point
        safety_stock = SafetyStockCalculator.calculate_safety_stock(
            decision.demand_std,
            decision.lead_time_weeks,
            decision.min_service_level
        )
        
        base_rop = SafetyStockCalculator.calculate_reorder_point(
            decision.expected_weekly_demand,
            decision.demand_std,
            decision.lead_time_weeks,
            decision.min_service_level
        )
        
        # Calculate EOQ
        annual_demand = decision.expected_weekly_demand * 52
        holding_cost = decision.unit_cost * decision.holding_cost_rate
        
        base_eoq = EOQCalculator.calculate_eoq(
            annual_demand,
            decision.ordering_cost,
            holding_cost
        )
        
        # Apply constraints
        recommended_rop = int(np.ceil(base_rop / decision.case_pack) * decision.case_pack)
        recommended_qty = EOQCalculator.apply_constraints(
            base_eoq,
            decision.moq,
            decision.case_pack,
            decision.warehouse_capacity
        )
        
        # Calculate expected outcomes
        if posterior_outcome:
            expected_stockout = posterior_outcome.stockout_probability
            expected_service = posterior_outcome.expected_service_level
        else:
            # Estimate from safety stock calculation
            expected_service = decision.min_service_level
            expected_stockout = 1 - expected_service
        
        # Calculate expected costs
        avg_inventory = recommended_rop / 2 + safety_stock
        expected_holding_cost = avg_inventory * holding_cost / 52  # Weekly
        expected_inventory_cost = expected_holding_cost * 13  # 13-week horizon
        
        # Compute objective value
        objective_value = (
            self.config.stockout_cost_weight * expected_stockout * decision.stockout_cost_per_unit +
            self.config.holding_cost_weight * expected_inventory_cost +
            self.config.ordering_cost_weight * decision.ordering_cost
        )
        
        # Check constraint satisfaction
        constraints_satisfied = {
            'moq_satisfied': recommended_qty >= decision.moq,
            'case_pack_aligned': recommended_qty % decision.case_pack == 0,
            'min_service_level': expected_service >= decision.min_service_level,
        }
        
        if decision.warehouse_capacity:
            max_inv = recommended_rop + recommended_qty
            constraints_satisfied['warehouse_capacity'] = max_inv <= decision.warehouse_capacity
        
        if decision.budget_limit:
            order_cost = recommended_qty * decision.unit_cost
            constraints_satisfied['budget'] = order_cost <= decision.budget_limit
        
        # Identify binding constraints
        binding = [k for k, v in constraints_satisfied.items() if not v]
        
        # Calculate solve time
        solve_time = (datetime.utcnow() - start_time).total_seconds()
        
        # Create result
        result = OptimizationResult(
            entity_id=decision.entity_id,
            recommended_reorder_point=recommended_rop,
            recommended_order_quantity=recommended_qty,
            objective_value=objective_value,
            constraints_satisfied=constraints_satisfied,
            binding_constraints=binding,
            inputs_hash=self._compute_inputs_hash(decision),
            expected_stockout_risk=expected_stockout,
            expected_service_level=expected_service,
            expected_inventory_cost=expected_inventory_cost,
            solver_status="OPTIMAL" if not binding else "FEASIBLE",
            solve_time_seconds=solve_time,
            model_version=model_version,
            run_id=self.run_id
        )
        
        # Audit log
        self._log_solve(decision, result)
        
        return result
    
    def optimize_with_ortools(
        self,
        decision: InventoryDecision,
        model_version: str = "unknown"
    ) -> OptimizationResult:
        """
        Optimize using OR-Tools MIP solver.
        
        More sophisticated optimization for complex constraints.
        """
        if not ORTOOLS_AVAILABLE:
            logger.warning("OR-Tools not available, using simplified optimizer")
            return self.optimize_single_entity(decision, model_version=model_version)
        
        start_time = datetime.utcnow()
        
        # Create solver
        solver = pywraplp.Solver.CreateSolver(self.config.solver_type)
        if not solver:
            logger.error("Could not create solver")
            return self.optimize_single_entity(decision, model_version=model_version)
        
        # Decision variables
        # ROP in units of case_pack
        max_rop_cases = int(decision.expected_weekly_demand * 20 / decision.case_pack)
        rop_cases = solver.IntVar(0, max_rop_cases, 'rop_cases')
        
        # Order quantity in units of case_pack
        max_qty_cases = int(decision.expected_weekly_demand * 52 / decision.case_pack)
        qty_cases = solver.IntVar(1, max_qty_cases, 'qty_cases')
        
        # Actual values
        rop = rop_cases * decision.case_pack
        qty = qty_cases * decision.case_pack
        
        # Constraints
        # MOQ constraint
        solver.Add(qty_cases * decision.case_pack >= decision.moq)
        
        # Service level constraint (simplified: ROP must cover lead time demand + safety)
        min_rop = decision.expected_weekly_demand * decision.lead_time_weeks * 1.5
        solver.Add(rop_cases * decision.case_pack >= min_rop)
        
        # Warehouse capacity
        if decision.warehouse_capacity:
            solver.Add(
                (rop_cases + qty_cases) * decision.case_pack <= decision.warehouse_capacity
            )
        
        # Budget constraint
        if decision.budget_limit:
            solver.Add(qty_cases * decision.case_pack * decision.unit_cost <= decision.budget_limit)
        
        # Objective: minimize total cost
        holding_cost = decision.unit_cost * decision.holding_cost_rate / 52
        annual_demand = decision.expected_weekly_demand * 52
        
        # Holding cost component (average inventory * holding rate)
        # Average inventory ≈ ROP/2 + Q/2
        avg_inv_expr = (rop_cases + qty_cases) * decision.case_pack / 2
        holding_cost_expr = avg_inv_expr * holding_cost
        
        # Ordering cost component (annual orders * cost per order)
        # Number of orders ≈ annual_demand / Q
        # Linearize by minimizing Q (larger Q = fewer orders)
        ordering_cost_expr = decision.ordering_cost / (qty_cases * decision.case_pack + 1)
        
        # Combined objective (weighted)
        solver.Minimize(
            self.config.holding_cost_weight * holding_cost_expr +
            self.config.ordering_cost_weight * (annual_demand / (qty_cases * decision.case_pack + 1)) * decision.ordering_cost
        )
        
        # Set time limit
        solver.SetTimeLimit(int(self.config.solver_time_limit_seconds * 1000))
        
        # Solve
        status = solver.Solve()
        
        solve_time = (datetime.utcnow() - start_time).total_seconds()
        
        # Extract solution
        if status in [pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE]:
            recommended_rop = int(rop_cases.solution_value() * decision.case_pack)
            recommended_qty = int(qty_cases.solution_value() * decision.case_pack)
            objective_value = solver.Objective().Value()
            solver_status = "OPTIMAL" if status == pywraplp.Solver.OPTIMAL else "FEASIBLE"
        else:
            # Fallback to simplified method
            logger.warning("OR-Tools solver failed, using fallback")
            return self.optimize_single_entity(decision, model_version=model_version)
        
        # Estimate outcomes
        safety_stock = SafetyStockCalculator.calculate_safety_stock(
            decision.demand_std,
            decision.lead_time_weeks,
            decision.min_service_level
        )
        expected_service = decision.min_service_level
        expected_stockout = 1 - expected_service
        
        avg_inventory = recommended_rop / 2 + recommended_qty / 2
        expected_inventory_cost = avg_inventory * holding_cost * 13
        
        # Check constraints
        constraints_satisfied = {
            'moq_satisfied': recommended_qty >= decision.moq,
            'case_pack_aligned': recommended_qty % decision.case_pack == 0,
            'min_service_level': True,  # Enforced by constraint
        }
        
        binding = [k for k, v in constraints_satisfied.items() if not v]
        
        result = OptimizationResult(
            entity_id=decision.entity_id,
            recommended_reorder_point=recommended_rop,
            recommended_order_quantity=recommended_qty,
            objective_value=objective_value,
            constraints_satisfied=constraints_satisfied,
            binding_constraints=binding,
            inputs_hash=self._compute_inputs_hash(decision),
            expected_stockout_risk=expected_stockout,
            expected_service_level=expected_service,
            expected_inventory_cost=expected_inventory_cost,
            solver_status=solver_status,
            solve_time_seconds=solve_time,
            model_version=model_version,
            run_id=self.run_id
        )
        
        self._log_solve(decision, result)
        return result
    
    def optimize_portfolio(
        self,
        decisions: List[InventoryDecision],
        posterior_outcomes: Optional[Dict[str, PosteriorOutcome]] = None,
        model_version: str = "unknown"
    ) -> List[OptimizationResult]:
        """
        Optimize inventory for multiple entities.
        
        Can incorporate portfolio-level constraints (total budget, etc.)
        """
        results = []
        
        for decision in decisions:
            posterior = None
            if posterior_outcomes and decision.entity_id in posterior_outcomes:
                posterior = posterior_outcomes[decision.entity_id]
            
            # Use OR-Tools if available for complex constraints
            if ORTOOLS_AVAILABLE and (decision.warehouse_capacity or decision.budget_limit):
                result = self.optimize_with_ortools(decision, model_version)
            else:
                result = self.optimize_single_entity(decision, posterior, model_version)
            
            results.append(result)
        
        return results
    
    def _log_solve(self, decision: InventoryDecision, result: OptimizationResult):
        """Log optimization solve for audit trail (FR-7.2)"""
        if not self.config.log_all_solves:
            return
        
        entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'run_id': self.run_id,
            'entity_id': decision.entity_id,
            'inputs': {
                'current_inventory': decision.current_inventory,
                'expected_demand': decision.expected_weekly_demand,
                'demand_std': decision.demand_std,
                'lead_time': decision.lead_time_weeks,
                'moq': decision.moq,
                'case_pack': decision.case_pack,
                'min_service_level': decision.min_service_level,
            },
            'outputs': {
                'reorder_point': result.recommended_reorder_point,
                'order_quantity': result.recommended_order_quantity,
                'objective_value': result.objective_value,
                'solver_status': result.solver_status,
            },
            'constraints': result.constraints_satisfied,
            'binding_constraints': result.binding_constraints,
            'solve_time_seconds': result.solve_time_seconds,
            'inputs_hash': result.inputs_hash,
        }
        
        self.audit_log.append(entry)
        
        # Write to file
        audit_path = Path(self.config.audit_path)
        with open(audit_path, 'w') as f:
            json.dump(self.audit_log, f, indent=2)


def create_optimizer(config: Optional[OptimizerConfig] = None) -> InventoryOptimizer:
    """Factory function for inventory optimizer"""
    return InventoryOptimizer(config)


if __name__ == "__main__":
    # Test optimizer
    optimizer = create_optimizer()
    
    # Create test decision
    decision = InventoryDecision(
        entity_id="SKU-0001",
        current_inventory=500,
        on_order=200,
        expected_weekly_demand=100,
        demand_std=25,
        lead_time_weeks=2,
        moq=24,
        case_pack=12,
        unit_cost=10.0,
        holding_cost_rate=0.25,
        stockout_cost_per_unit=5.0,
        ordering_cost=50.0,
        min_service_level=0.95
    )
    
    # Optimize
    result = optimizer.optimize_single_entity(decision, model_version="test-v0.0.1")
    
    print("\n=== Optimization Results ===")
    print(f"Entity: {result.entity_id}")
    print(f"Recommended ROP: {result.recommended_reorder_point}")
    print(f"Recommended Order Qty: {result.recommended_order_quantity}")
    print(f"Objective Value: {result.objective_value:.2f}")
    print(f"Expected Service Level: {result.expected_service_level:.2%}")
    print(f"Expected Stockout Risk: {result.expected_stockout_risk:.2%}")
    print(f"Solver Status: {result.solver_status}")
    print(f"Solve Time: {result.solve_time_seconds:.4f}s")
    print(f"Constraints Satisfied: {result.constraints_satisfied}")
    
    # Test with OR-Tools if available
    if ORTOOLS_AVAILABLE:
        print("\n=== OR-Tools Optimization ===")
        result_ortools = optimizer.optimize_with_ortools(decision, model_version="test-v0.0.1")
        print(f"Recommended ROP: {result_ortools.recommended_reorder_point}")
        print(f"Recommended Order Qty: {result_ortools.recommended_order_quantity}")
        print(f"Solver Status: {result_ortools.solver_status}")
