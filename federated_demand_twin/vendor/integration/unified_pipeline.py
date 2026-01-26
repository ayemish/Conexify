"""
Unified Pipeline: FL → NBEATS → Endogenous → Bayesian

This module closes the integration gaps between:
1. Federated Learning (cross-retailer model aggregation)
2. NBEATS/SLOTH demand forecasting (with exogenous variables)
3. Endogenous state tracking (basket dynamics)
4. Bayesian decision engine (inventory/procurement probabilities)

The pipeline enables:
- Product-specific inventory probability scenarios
- Procurement probability distributions
- Endogenous variable integration into forecasting
- Hierarchical Bayesian inference at product level
"""

import numpy as np
import torch
from typing import Dict, List, Tuple, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum
import logging
from pathlib import Path
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# PRODUCT HIERARCHY & CONFIGURATION
# =============================================================================

class ProductLevel(str, Enum):
    """Hierarchy levels for product-specific analysis"""
    SKU = "sku"
    CATEGORY = "category"
    BRAND = "brand"
    PORTFOLIO = "portfolio"


@dataclass
class ProductConfig:
    """Product-specific configuration for Bayesian analysis"""
    product_id: str
    level: ProductLevel
    parent_id: Optional[str] = None
    
    # Demand characteristics
    demand_volatility: float = 0.2  # CV of demand
    seasonality_strength: float = 0.3  # 0-1 scale
    trend_direction: float = 0.0  # -1 to +1 (declining to growing)
    
    # Inventory parameters
    target_service_level: float = 0.95
    holding_cost_rate: float = 0.25  # Annual as fraction of value
    stockout_cost_multiplier: float = 2.0
    
    # Supply parameters
    lead_time_mean_weeks: float = 2.0
    lead_time_std_weeks: float = 0.5
    moq: int = 12
    case_pack: int = 6
    
    # Procurement parameters
    supplier_reliability: float = 0.95  # On-time in-full rate
    num_suppliers: int = 1
    supplier_diversification_benefit: float = 0.0  # Risk reduction from multi-sourcing


@dataclass
class SupplierConfig:
    """Supplier-specific configuration for procurement scenarios"""
    supplier_id: str
    supplier_name: str
    
    # Reliability metrics
    otif_rate: float = 0.95  # On-Time In-Full
    quality_rate: float = 0.99
    
    # Lead time distribution
    lead_time_mean_days: float = 14.0
    lead_time_std_days: float = 3.0
    lead_time_min_days: float = 7.0
    lead_time_max_days: float = 28.0
    
    # Capacity constraints
    min_order_quantity: int = 100
    max_order_quantity: int = 10000
    capacity_utilization: float = 0.7  # Current utilization
    
    # Cost structure
    unit_cost: float = 10.0
    freight_cost_per_unit: float = 0.5
    volume_discount_threshold: int = 1000
    volume_discount_rate: float = 0.05


# =============================================================================
# ENDOGENOUS VARIABLE BRIDGE
# =============================================================================

@dataclass
class EndogenousState:
    """Current state of endogenous variables for forecasting"""
    timestamp: datetime
    
    # Basket dynamics
    total_baskets: float
    basket_penetration: float
    items_per_basket: float
    size_per_item: float
    
    # Derived metrics
    total_units: float = field(init=False)
    total_volume: float = field(init=False)
    
    # Trends (week-over-week change rates)
    basket_trend: float = 0.0
    penetration_trend: float = 0.0
    items_trend: float = 0.0
    size_trend: float = 0.0
    
    # Confidence in state estimates
    confidence: float = 0.8
    
    def __post_init__(self):
        self.total_units = (
            self.total_baskets * 
            self.basket_penetration * 
            self.items_per_basket
        )
        self.total_volume = self.total_units * self.size_per_item
    
    def to_covariate_vector(self) -> np.ndarray:
        """Convert to covariate vector for NBEATS input"""
        return np.array([
            self.basket_penetration,
            self.items_per_basket,
            self.size_per_item,
            self.basket_trend,
            self.penetration_trend,
            self.items_trend,
            self.size_trend,
            self.confidence
        ])


class EndogenousBridge:
    """
    Bridges iQueue EndogenousStateAgents to NBEATS covariate inputs.
    
    Converts agent belief states into forecasting covariates.
    """
    
    def __init__(self, lookback_weeks: int = 26):
        self.lookback_weeks = lookback_weeks
        self.state_history: List[EndogenousState] = []
    
    def update_from_agents(
        self,
        basket_agent,
        penetration_agent,
        items_agent,
        size_agent
    ) -> EndogenousState:
        """Extract current state from iQueue agents"""
        now = datetime.utcnow()
        
        # Get beliefs from each agent
        basket_belief = basket_agent.beliefs.get('total_baskets')
        pen_belief = penetration_agent.beliefs.get('basket_penetration')
        items_belief = items_agent.beliefs.get('items_per_basket')
        size_belief = size_agent.beliefs.get('size_per_item')
        
        state = EndogenousState(
            timestamp=now,
            total_baskets=basket_belief.mean if basket_belief else 1000,
            basket_penetration=pen_belief.mean if pen_belief else 0.1,
            items_per_basket=items_belief.mean if items_belief else 1.5,
            size_per_item=size_belief.mean if size_belief else 1.0,
            confidence=min(
                basket_belief.confidence if basket_belief else 0.5,
                pen_belief.confidence if pen_belief else 0.5,
                items_belief.confidence if items_belief else 0.5,
                size_belief.confidence if size_belief else 0.5
            )
        )
        
        # Compute trends from history
        if self.state_history:
            prev = self.state_history[-1]
            state.basket_trend = (state.total_baskets - prev.total_baskets) / max(prev.total_baskets, 1)
            state.penetration_trend = state.basket_penetration - prev.basket_penetration
            state.items_trend = state.items_per_basket - prev.items_per_basket
            state.size_trend = state.size_per_item - prev.size_per_item
        
        self.state_history.append(state)
        
        # Keep only lookback period
        if len(self.state_history) > self.lookback_weeks:
            self.state_history = self.state_history[-self.lookback_weeks:]
        
        return state
    
    def get_covariate_matrix(self) -> np.ndarray:
        """Get covariate matrix for NBEATS (lookback_weeks, n_covariates)"""
        if not self.state_history:
            # Return zeros if no history
            return np.zeros((self.lookback_weeks, 8))
        
        # Pad if needed
        n_states = len(self.state_history)
        covariates = np.array([s.to_covariate_vector() for s in self.state_history])
        
        if n_states < self.lookback_weeks:
            # Pad with first state repeated
            padding = np.tile(covariates[0], (self.lookback_weeks - n_states, 1))
            covariates = np.vstack([padding, covariates])
        
        return covariates


# =============================================================================
# PROCUREMENT PROBABILITY ENGINE
# =============================================================================

@dataclass
class ProcurementScenario:
    """A procurement scenario for probability analysis"""
    scenario_id: str
    name: str
    description: str
    
    # Order parameters
    order_quantity: int
    target_receipt_date: date
    
    # Supplier allocation (supplier_id -> fraction)
    supplier_allocation: Dict[str, float]
    
    # Computed probabilities (filled by engine)
    on_time_probability: Optional[float] = None
    in_full_probability: Optional[float] = None
    otif_probability: Optional[float] = None
    expected_receipt_date: Optional[date] = None
    receipt_date_std_days: Optional[float] = None
    
    # Cost estimates
    expected_total_cost: Optional[float] = None
    cost_ci_lower: Optional[float] = None
    cost_ci_upper: Optional[float] = None


class ProcurementProbabilityEngine:
    """
    Computes procurement probabilities for supplier/order scenarios.
    
    Provides:
    - OTIF (On-Time In-Full) probability distributions
    - Lead time uncertainty propagation
    - Multi-supplier risk aggregation
    - Cost uncertainty quantification
    """
    
    def __init__(self, n_simulations: int = 5000):
        self.n_simulations = n_simulations
        self.suppliers: Dict[str, SupplierConfig] = {}
    
    def register_supplier(self, supplier: SupplierConfig):
        """Register a supplier configuration"""
        self.suppliers[supplier.supplier_id] = supplier
    
    def compute_scenario_probabilities(
        self,
        scenario: ProcurementScenario
    ) -> ProcurementScenario:
        """
        Compute probability distributions for a procurement scenario.
        
        Uses Monte Carlo simulation over supplier reliability and lead times.
        """
        # Arrays for simulation
        receipt_dates = []
        quantities_received = []
        total_costs = []
        
        order_date = date.today()
        target_days = (scenario.target_receipt_date - order_date).days
        
        for sim in range(self.n_simulations):
            sim_receipt_day = 0
            sim_quantity = 0
            sim_cost = 0
            
            for supplier_id, allocation in scenario.supplier_allocation.items():
                supplier = self.suppliers.get(supplier_id)
                if not supplier:
                    continue
                
                allocated_qty = int(scenario.order_quantity * allocation)
                
                # Simulate supplier performance
                # 1. Lead time (truncated normal)
                lead_time = np.random.normal(
                    supplier.lead_time_mean_days,
                    supplier.lead_time_std_days
                )
                lead_time = np.clip(
                    lead_time,
                    supplier.lead_time_min_days,
                    supplier.lead_time_max_days
                )
                
                # 2. On-time (based on OTIF rate)
                is_on_time = np.random.random() < supplier.otif_rate
                
                # 3. Quantity delivered (quality rate affects quantity)
                quality_factor = np.random.random() < supplier.quality_rate
                delivered_qty = allocated_qty if quality_factor else int(allocated_qty * 0.95)
                
                # 4. Cost (including volume discounts)
                unit_cost = supplier.unit_cost + supplier.freight_cost_per_unit
                if allocated_qty >= supplier.volume_discount_threshold:
                    unit_cost *= (1 - supplier.volume_discount_rate)
                
                # Aggregate across suppliers (worst case for timing)
                sim_receipt_day = max(sim_receipt_day, lead_time)
                sim_quantity += delivered_qty
                sim_cost += delivered_qty * unit_cost
            
            receipt_dates.append(sim_receipt_day)
            quantities_received.append(sim_quantity)
            total_costs.append(sim_cost)
        
        receipt_dates = np.array(receipt_dates)
        quantities_received = np.array(quantities_received)
        total_costs = np.array(total_costs)
        
        # Compute probabilities
        scenario.on_time_probability = float(np.mean(receipt_dates <= target_days))
        scenario.in_full_probability = float(np.mean(quantities_received >= scenario.order_quantity))
        scenario.otif_probability = float(np.mean(
            (receipt_dates <= target_days) & (quantities_received >= scenario.order_quantity)
        ))
        
        # Receipt date statistics
        mean_receipt_days = np.mean(receipt_dates)
        scenario.expected_receipt_date = order_date + timedelta(days=int(mean_receipt_days))
        scenario.receipt_date_std_days = float(np.std(receipt_dates))
        
        # Cost statistics
        scenario.expected_total_cost = float(np.mean(total_costs))
        scenario.cost_ci_lower = float(np.percentile(total_costs, 5))
        scenario.cost_ci_upper = float(np.percentile(total_costs, 95))
        
        return scenario
    
    def compare_sourcing_strategies(
        self,
        order_quantity: int,
        target_date: date,
        strategies: Dict[str, Dict[str, float]]
    ) -> Dict[str, ProcurementScenario]:
        """
        Compare multiple sourcing strategies.
        
        Args:
            order_quantity: Total quantity to order
            target_date: Target receipt date
            strategies: Dict of strategy_name -> {supplier_id: allocation}
            
        Returns:
            Dict of strategy_name -> evaluated ProcurementScenario
        """
        results = {}
        
        for strategy_name, allocation in strategies.items():
            scenario = ProcurementScenario(
                scenario_id=f"strat_{strategy_name}",
                name=strategy_name,
                description=f"Sourcing strategy: {strategy_name}",
                order_quantity=order_quantity,
                target_receipt_date=target_date,
                supplier_allocation=allocation
            )
            
            results[strategy_name] = self.compute_scenario_probabilities(scenario)
        
        return results


# =============================================================================
# PRODUCT-LEVEL BAYESIAN ENGINE
# =============================================================================

@dataclass
class ProductPosterior:
    """Posterior distributions at product level"""
    product_id: str
    level: ProductLevel
    scenario_name: str
    timestamp: datetime
    
    # Inventory probabilities
    stockout_probability: float
    stockout_ci: Tuple[float, float]
    
    days_of_supply_mean: float
    days_of_supply_ci: Tuple[float, float]
    
    # Service level
    service_level_mean: float
    service_level_ci: Tuple[float, float]
    
    # Financial impact
    expected_margin: float
    margin_ci: Tuple[float, float]
    
    holding_cost: float
    stockout_cost: float
    
    # Procurement probabilities
    procurement_otif: Optional[float] = None
    expected_lead_time_days: Optional[float] = None
    
    # Confidence
    posterior_confidence: float = 0.8
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'product_id': self.product_id,
            'level': self.level.value,
            'scenario_name': self.scenario_name,
            'stockout_probability': self.stockout_probability,
            'stockout_ci': self.stockout_ci,
            'days_of_supply': self.days_of_supply_mean,
            'service_level': self.service_level_mean,
            'expected_margin': self.expected_margin,
            'holding_cost': self.holding_cost,
            'stockout_cost': self.stockout_cost,
            'procurement_otif': self.procurement_otif,
            'confidence': self.posterior_confidence
        }


class ProductBayesianEngine:
    """
    Product-specific Bayesian inference engine.
    
    Extends the base BayesianDecisionEngine with:
    - Product hierarchy support
    - Endogenous variable integration
    - Procurement probability incorporation
    - Hierarchical posterior computation
    """
    
    def __init__(
        self,
        n_simulations: int = 5000,
        ci_level: float = 0.90
    ):
        self.n_simulations = n_simulations
        self.ci_level = ci_level
        self.ci_lower_pct = (1 - ci_level) / 2 * 100
        self.ci_upper_pct = (1 + ci_level) / 2 * 100
        
        self.product_configs: Dict[str, ProductConfig] = {}
        self.posteriors: Dict[str, Dict[str, ProductPosterior]] = {}
    
    def register_product(self, config: ProductConfig):
        """Register a product configuration"""
        self.product_configs[config.product_id] = config
    
    def compute_inventory_probabilities(
        self,
        product_id: str,
        demand_forecasts: List[Dict[str, float]],  # List of {q10, q50, q90}
        current_inventory: float,
        on_order: float,
        endogenous_state: Optional[EndogenousState] = None,
        procurement_scenario: Optional[ProcurementScenario] = None,
        scenario_name: str = "baseline"
    ) -> ProductPosterior:
        """
        Compute inventory probability distributions for a product.
        
        Integrates:
        - Demand uncertainty from forecasts
        - Endogenous variable adjustments
        - Procurement lead time uncertainty
        
        Returns:
            ProductPosterior with all probability distributions
        """
        config = self.product_configs.get(product_id)
        if not config:
            config = ProductConfig(product_id=product_id, level=ProductLevel.SKU)
        
        horizon_weeks = len(demand_forecasts)
        
        # Arrays for simulation
        stockout_weeks = np.zeros(self.n_simulations)
        total_demand = np.zeros(self.n_simulations)
        total_fulfilled = np.zeros(self.n_simulations)
        ending_inventory = np.zeros(self.n_simulations)
        total_margin = np.zeros(self.n_simulations)
        
        for sim in range(self.n_simulations):
            inventory = current_inventory
            pipeline = [on_order] + [0] * int(config.lead_time_mean_weeks)
            
            sim_demand_total = 0
            sim_fulfilled_total = 0
            sim_stockouts = 0
            
            for week, forecast in enumerate(demand_forecasts):
                # Sample demand from forecast distribution
                q10, q50, q90 = forecast['q10'], forecast['q50'], forecast['q90']
                
                # Fit lognormal and sample
                mu = np.log(max(q50, 1))
                sigma = np.log(max(q90 / q50, 1.01)) / 1.28
                demand = np.random.lognormal(mu, sigma)
                
                # Apply endogenous adjustment if available
                if endogenous_state:
                    # Adjust demand based on basket dynamics
                    adjustment = 1.0 + (endogenous_state.basket_trend * 0.5)
                    adjustment *= (1.0 + endogenous_state.penetration_trend * 2.0)
                    demand *= adjustment
                
                # Receive pipeline inventory
                if pipeline:
                    incoming = pipeline.pop(0)
                    
                    # Apply procurement uncertainty
                    if procurement_scenario and procurement_scenario.otif_probability:
                        if np.random.random() > procurement_scenario.otif_probability:
                            # Delayed or short shipment
                            incoming *= 0.85
                    
                    inventory += incoming
                    pipeline.append(0)
                
                # Fulfill demand
                fulfilled = min(inventory, demand)
                inventory -= fulfilled
                
                sim_demand_total += demand
                sim_fulfilled_total += fulfilled
                
                if fulfilled < demand:
                    sim_stockouts += 1
                
                # Reorder logic
                if inventory <= config.target_service_level * q50 * config.lead_time_mean_weeks:
                    reorder_qty = max(q50 * 4, config.moq)  # ~4 weeks supply
                    reorder_qty = int(np.ceil(reorder_qty / config.case_pack) * config.case_pack)
                    
                    if pipeline:
                        pipeline[-1] += reorder_qty
            
            stockout_weeks[sim] = sim_stockouts
            total_demand[sim] = sim_demand_total
            total_fulfilled[sim] = sim_fulfilled_total
            ending_inventory[sim] = inventory
            
            # Compute margin
            unit_margin = 5.0  # Simplified
            margin = sim_fulfilled_total * unit_margin
            holding_cost = (current_inventory + inventory) / 2 * config.holding_cost_rate / 52 * horizon_weeks
            stockout_cost = (sim_demand_total - sim_fulfilled_total) * config.stockout_cost_multiplier * unit_margin
            total_margin[sim] = margin - holding_cost - stockout_cost
        
        # Compute summary statistics
        stockout_rate = stockout_weeks / horizon_weeks
        service_level = total_fulfilled / np.maximum(total_demand, 1)
        
        avg_inv = (current_inventory + ending_inventory) / 2
        weekly_demand = total_demand / horizon_weeks
        days_of_supply = avg_inv / (weekly_demand / 7 + 1e-6)
        
        return ProductPosterior(
            product_id=product_id,
            level=config.level,
            scenario_name=scenario_name,
            timestamp=datetime.utcnow(),
            
            stockout_probability=float(np.mean(stockout_rate > 0)),
            stockout_ci=(
                float(np.percentile(stockout_rate, self.ci_lower_pct)),
                float(np.percentile(stockout_rate, self.ci_upper_pct))
            ),
            
            days_of_supply_mean=float(np.mean(days_of_supply)),
            days_of_supply_ci=(
                float(np.percentile(days_of_supply, self.ci_lower_pct)),
                float(np.percentile(days_of_supply, self.ci_upper_pct))
            ),
            
            service_level_mean=float(np.mean(service_level)),
            service_level_ci=(
                float(np.percentile(service_level, self.ci_lower_pct)),
                float(np.percentile(service_level, self.ci_upper_pct))
            ),
            
            expected_margin=float(np.mean(total_margin)),
            margin_ci=(
                float(np.percentile(total_margin, self.ci_lower_pct)),
                float(np.percentile(total_margin, self.ci_upper_pct))
            ),
            
            holding_cost=float(np.mean(avg_inv * config.holding_cost_rate / 52 * horizon_weeks)),
            stockout_cost=float(np.mean((total_demand - total_fulfilled) * config.stockout_cost_multiplier * 5.0)),
            
            procurement_otif=procurement_scenario.otif_probability if procurement_scenario else None,
            expected_lead_time_days=(
                procurement_scenario.receipt_date_std_days * 7 if procurement_scenario else 
                config.lead_time_mean_weeks * 7
            ),
            
            posterior_confidence=0.85 if endogenous_state else 0.75
        )
    
    def run_product_scenarios(
        self,
        product_id: str,
        demand_forecasts: List[Dict[str, float]],
        current_inventory: float,
        on_order: float,
        endogenous_state: Optional[EndogenousState] = None,
        procurement_scenarios: Optional[Dict[str, ProcurementScenario]] = None
    ) -> Dict[str, ProductPosterior]:
        """
        Run multiple scenarios for a product.
        
        Returns posteriors for:
        - baseline
        - demand_up_20pct
        - demand_down_20pct
        - supply_disruption
        - Each procurement scenario
        """
        results = {}
        
        # Baseline
        results['baseline'] = self.compute_inventory_probabilities(
            product_id, demand_forecasts, current_inventory, on_order,
            endogenous_state, None, 'baseline'
        )
        
        # Demand +20%
        demand_up = [{k: v * 1.2 for k, v in f.items()} for f in demand_forecasts]
        results['demand_up_20pct'] = self.compute_inventory_probabilities(
            product_id, demand_up, current_inventory, on_order,
            endogenous_state, None, 'demand_up_20pct'
        )
        
        # Demand -20%
        demand_down = [{k: v * 0.8 for k, v in f.items()} for f in demand_forecasts]
        results['demand_down_20pct'] = self.compute_inventory_probabilities(
            product_id, demand_down, current_inventory, on_order,
            endogenous_state, None, 'demand_down_20pct'
        )
        
        # Supply disruption (no incoming orders)
        results['supply_disruption'] = self.compute_inventory_probabilities(
            product_id, demand_forecasts, current_inventory, 0,
            endogenous_state, None, 'supply_disruption'
        )
        
        # Procurement scenarios
        if procurement_scenarios:
            for scenario_name, scenario in procurement_scenarios.items():
                results[f'procurement_{scenario_name}'] = self.compute_inventory_probabilities(
                    product_id, demand_forecasts, current_inventory, on_order,
                    endogenous_state, scenario, f'procurement_{scenario_name}'
                )
        
        # Cache
        self.posteriors[product_id] = results
        
        return results


# =============================================================================
# UNIFIED PIPELINE ORCHESTRATOR
# =============================================================================

class UnifiedPipeline:
    """
    Orchestrates the complete FL → NBEATS → Endogenous → Bayesian pipeline.
    
    This is the main integration point that connects:
    1. Federated Learning aggregated model
    2. NBEATS demand forecasting with covariates
    3. Endogenous state tracking from iQueue agents
    4. Bayesian inventory/procurement probability computation
    """
    
    def __init__(
        self,
        fl_model=None,
        demand_model=None,
        endogenous_bridge: Optional[EndogenousBridge] = None,
        procurement_engine: Optional[ProcurementProbabilityEngine] = None,
        bayesian_engine: Optional[ProductBayesianEngine] = None
    ):
        self.fl_model = fl_model
        self.demand_model = demand_model
        self.endogenous_bridge = endogenous_bridge or EndogenousBridge()
        self.procurement_engine = procurement_engine or ProcurementProbabilityEngine()
        self.bayesian_engine = bayesian_engine or ProductBayesianEngine()
        
        logger.info("UnifiedPipeline initialized")
    
    def set_fl_model(self, fl_model):
        """Set the federated learning model (after aggregation)"""
        self.fl_model = fl_model
    
    def set_demand_model(self, demand_model):
        """Set the NBEATS demand forecasting model"""
        self.demand_model = demand_model
    
    def update_endogenous_state(
        self,
        basket_agent,
        penetration_agent,
        items_agent,
        size_agent
    ) -> EndogenousState:
        """Update endogenous state from iQueue agents"""
        return self.endogenous_bridge.update_from_agents(
            basket_agent, penetration_agent, items_agent, size_agent
        )
    
    def generate_forecasts(
        self,
        demand_history: np.ndarray,
        base_covariates: Optional[np.ndarray] = None,
        include_endogenous: bool = True,
        horizon: int = 13
    ) -> List[Dict[str, float]]:
        """
        Generate demand forecasts using NBEATS with full covariate set.
        
        Integrates endogenous variables as additional covariates.
        """
        if self.demand_model is None:
            # Return simple baseline if no model
            mean = np.mean(demand_history[-4:]) if len(demand_history) > 0 else 100
            return [
                {'q10': mean * 0.8, 'q50': mean, 'q90': mean * 1.3}
                for _ in range(horizon)
            ]
        
        # Prepare covariates
        if include_endogenous and self.endogenous_bridge.state_history:
            endogenous_cov = self.endogenous_bridge.get_covariate_matrix()
            
            if base_covariates is not None:
                # Concatenate base covariates with endogenous
                full_covariates = np.concatenate([base_covariates, endogenous_cov], axis=-1)
            else:
                full_covariates = endogenous_cov
        else:
            full_covariates = base_covariates
        
        # Convert to tensors
        demand_tensor = torch.from_numpy(demand_history.astype(np.float32)).unsqueeze(0)
        
        if full_covariates is not None:
            cov_tensor = torch.from_numpy(full_covariates.astype(np.float32)).unsqueeze(0)
        else:
            cov_tensor = None
        
        # Generate forecast
        self.demand_model.model.eval()
        with torch.no_grad():
            predictions = self.demand_model.predict(demand_tensor, cov_tensor)
        
        # Convert to list of dicts
        forecasts = []
        for t in range(horizon):
            forecasts.append({
                'q10': float(predictions['q10'][0, t]),
                'q50': float(predictions['q50'][0, t]),
                'q90': float(predictions['q90'][0, t])
            })
        
        return forecasts
    
    def run_product_analysis(
        self,
        product_id: str,
        demand_history: np.ndarray,
        current_inventory: float,
        on_order: float,
        base_covariates: Optional[np.ndarray] = None,
        suppliers: Optional[List[SupplierConfig]] = None,
        sourcing_strategies: Optional[Dict[str, Dict[str, float]]] = None
    ) -> Dict[str, Any]:
        """
        Run complete analysis for a product.
        
        Steps:
        1. Generate demand forecasts (NBEATS + endogenous)
        2. Compute procurement scenarios (if suppliers provided)
        3. Run Bayesian inventory analysis
        4. Return comprehensive results
        """
        # 1. Generate forecasts
        forecasts = self.generate_forecasts(
            demand_history, base_covariates, include_endogenous=True
        )
        
        # 2. Procurement scenarios
        procurement_scenarios = None
        if suppliers and sourcing_strategies:
            for supplier in suppliers:
                self.procurement_engine.register_supplier(supplier)
            
            target_date = date.today() + timedelta(weeks=2)
            order_qty = int(sum(f['q50'] for f in forecasts[:4]))  # 4 weeks supply
            
            procurement_scenarios = self.procurement_engine.compare_sourcing_strategies(
                order_qty, target_date, sourcing_strategies
            )
        
        # 3. Get endogenous state
        endogenous_state = None
        if self.endogenous_bridge.state_history:
            endogenous_state = self.endogenous_bridge.state_history[-1]
        
        # 4. Run Bayesian analysis
        posteriors = self.bayesian_engine.run_product_scenarios(
            product_id=product_id,
            demand_forecasts=forecasts,
            current_inventory=current_inventory,
            on_order=on_order,
            endogenous_state=endogenous_state,
            procurement_scenarios=procurement_scenarios
        )
        
        return {
            'product_id': product_id,
            'timestamp': datetime.utcnow().isoformat(),
            'demand_forecasts': forecasts,
            'endogenous_state': endogenous_state.to_dict() if endogenous_state else None,
            'procurement_scenarios': {
                k: {
                    'otif_probability': v.otif_probability,
                    'expected_cost': v.expected_total_cost,
                    'expected_receipt_date': v.expected_receipt_date.isoformat() if v.expected_receipt_date else None
                }
                for k, v in (procurement_scenarios or {}).items()
            },
            'posteriors': {k: v.to_dict() for k, v in posteriors.items()},
            'recommendation': self._generate_recommendation(posteriors)
        }
    
    def _generate_recommendation(
        self,
        posteriors: Dict[str, ProductPosterior]
    ) -> Dict[str, Any]:
        """Generate action recommendations from posteriors"""
        baseline = posteriors.get('baseline')
        if not baseline:
            return {'action': 'INSUFFICIENT_DATA'}
        
        recommendation = {
            'action': 'MAINTAIN',
            'rationale': [],
            'urgency': 'low'
        }
        
        if baseline.stockout_probability > 0.10:
            recommendation['action'] = 'INCREASE_STOCK'
            recommendation['rationale'].append(
                f"High stockout risk: {baseline.stockout_probability:.1%}"
            )
            recommendation['urgency'] = 'high' if baseline.stockout_probability > 0.20 else 'medium'
        
        if baseline.days_of_supply_mean < 14:
            recommendation['action'] = 'EXPEDITE_ORDER'
            recommendation['rationale'].append(
                f"Low days of supply: {baseline.days_of_supply_mean:.0f} days"
            )
            recommendation['urgency'] = 'high'
        
        if baseline.service_level_mean < 0.95:
            recommendation['rationale'].append(
                f"Service level below target: {baseline.service_level_mean:.1%}"
            )
        
        # Check procurement scenarios
        procurement_posteriors = {
            k: v for k, v in posteriors.items() 
            if k.startswith('procurement_')
        }
        
        if procurement_posteriors:
            best_procurement = min(
                procurement_posteriors.items(),
                key=lambda x: x[1].stockout_probability
            )
            recommendation['recommended_sourcing'] = best_procurement[0]
        
        return recommendation


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

def create_unified_pipeline(
    demand_model=None,
    lookback_weeks: int = 26,
    n_simulations: int = 5000
) -> UnifiedPipeline:
    """Create a fully configured unified pipeline"""
    return UnifiedPipeline(
        demand_model=demand_model,
        endogenous_bridge=EndogenousBridge(lookback_weeks),
        procurement_engine=ProcurementProbabilityEngine(n_simulations),
        bayesian_engine=ProductBayesianEngine(n_simulations)
    )


def create_product_config(
    product_id: str,
    level: str = "sku",
    **kwargs
) -> ProductConfig:
    """Create a product configuration"""
    return ProductConfig(
        product_id=product_id,
        level=ProductLevel(level),
        **kwargs
    )


def create_supplier_config(
    supplier_id: str,
    supplier_name: str,
    **kwargs
) -> SupplierConfig:
    """Create a supplier configuration"""
    return SupplierConfig(
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        **kwargs
    )
