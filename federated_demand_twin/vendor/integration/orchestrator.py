"""
Integration Orchestrator

Wires together all components of the Federated Demand Twin:
1. iQueue Agents (endogenous state tracking)
2. FL Server (cross-retailer aggregation)  
3. Extended NBEATS (demand forecasting)
4. Bayesian Engine (inventory/procurement probabilities)

This is the main entry point for running the integrated system.
"""

import numpy as np
import torch
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
import logging
from pathlib import Path
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import all components
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from customer.fl_client.extended_demand_model import (
    ExtendedModelConfig,
    IntegratedDemandForecaster,
    create_extended_config,
    create_integrated_forecaster
)

from vendor.agents.iqueue import (
    AgentConfig,
    BeliefState,
    BasketAgent,
    PenetrationAgent,
    ItemsPerBasketAgent,
    SizePerItemAgent,
    MediaDriverAgent,
    PriceDriverAgent,
    TradeDriverAgent,
    AttributionAgent,
    ScenarioGenerationAgent,
    OptimizationAgent,
    GovernanceAgent,
    IQueueWorkflow,
    WorkflowConfig
)

from vendor.agents.iqueue.base import AgentType, AgentMessageBus

from vendor.integration.unified_pipeline import (
    UnifiedPipeline,
    EndogenousBridge,
    EndogenousState,
    ProductBayesianEngine,
    ProcurementProbabilityEngine,
    ProductConfig,
    SupplierConfig,
    ProcurementScenario,
    create_unified_pipeline,
    create_product_config,
    create_supplier_config
)


@dataclass
class OrchestratorConfig:
    """Configuration for the integration orchestrator"""
    # Identifiers
    retailer_id: str
    segment_id: Optional[str] = None
    
    # Model configuration
    lookback_weeks: int = 26
    forecast_horizon: int = 13
    hidden_dim: int = 128
    num_blocks: int = 3
    use_bayesian: bool = True
    
    # FL configuration
    fl_enabled: bool = True
    fl_aggregation_weight: float = 0.7
    
    # Simulation settings
    n_simulations: int = 5000
    
    # Drivers
    drivers: List[str] = field(default_factory=lambda: ['media', 'price', 'trade'])
    
    # Persistence
    state_path: Optional[str] = None


class IntegrationOrchestrator:
    """
    Main orchestrator for the integrated Federated Demand Twin system.
    
    Manages:
    - iQueue agent lifecycle and state updates
    - Federated learning model aggregation
    - Demand forecasting with endogenous variables
    - Bayesian inventory/procurement analysis
    - End-to-end workflow execution
    """
    
    def __init__(self, config: OrchestratorConfig):
        self.config = config
        self.message_bus = AgentMessageBus()
        
        # Initialize components
        self._init_agents()
        self._init_forecaster()
        self._init_bayesian_engine()
        self._init_endogenous_bridge()
        
        # State tracking
        self.run_history: List[Dict[str, Any]] = []
        self.last_update = datetime.utcnow()
        
        logger.info(f"IntegrationOrchestrator initialized for {config.retailer_id}")
    
    def _init_agents(self):
        """Initialize iQueue agents"""
        # State agents - one for each endogenous metric
        self.state_agents = {}
        
        basket_config = AgentConfig(
            agent_id=f"{self.config.retailer_id}_baskets",
            agent_type=AgentType.ENDOGENOUS_STATE,
            retailer_id=self.config.retailer_id,
            segment_id=self.config.segment_id
        )
        self.state_agents['total_baskets'] = BasketAgent(basket_config, self.message_bus)
        
        penetration_config = AgentConfig(
            agent_id=f"{self.config.retailer_id}_penetration",
            agent_type=AgentType.ENDOGENOUS_STATE,
            retailer_id=self.config.retailer_id,
            segment_id=self.config.segment_id
        )
        self.state_agents['basket_penetration'] = PenetrationAgent(penetration_config, self.message_bus)
        
        items_config = AgentConfig(
            agent_id=f"{self.config.retailer_id}_items",
            agent_type=AgentType.ENDOGENOUS_STATE,
            retailer_id=self.config.retailer_id,
            segment_id=self.config.segment_id
        )
        self.state_agents['items_per_basket'] = ItemsPerBasketAgent(items_config, self.message_bus)
        
        size_config = AgentConfig(
            agent_id=f"{self.config.retailer_id}_size",
            agent_type=AgentType.ENDOGENOUS_STATE,
            retailer_id=self.config.retailer_id,
            segment_id=self.config.segment_id
        )
        self.state_agents['size_per_item'] = SizePerItemAgent(size_config, self.message_bus)
        
        # Driver agents
        self.driver_agents = {}
        
        media_config = AgentConfig(
            agent_id=f"{self.config.retailer_id}_media",
            agent_type=AgentType.DRIVER_CONTROLLABLE,
            retailer_id=self.config.retailer_id
        )
        self.driver_agents['media'] = MediaDriverAgent(media_config, self.message_bus)
        
        price_config = AgentConfig(
            agent_id=f"{self.config.retailer_id}_price",
            agent_type=AgentType.DRIVER_CONTROLLABLE,
            retailer_id=self.config.retailer_id
        )
        self.driver_agents['price'] = PriceDriverAgent(price_config, self.message_bus)
        
        trade_config = AgentConfig(
            agent_id=f"{self.config.retailer_id}_trade",
            agent_type=AgentType.DRIVER_CONTROLLABLE,
            retailer_id=self.config.retailer_id
        )
        self.driver_agents['trade'] = TradeDriverAgent(trade_config, self.message_bus)
        
        # Attribution agent
        attribution_config = AgentConfig(
            agent_id=f"{self.config.retailer_id}_attribution",
            agent_type=AgentType.ATTRIBUTION,
            retailer_id=self.config.retailer_id
        )
        self.attribution_agent = AttributionAgent(
            attribution_config, 
            self.message_bus,
            drivers=self.config.drivers
        )
        
        # Scenario agent
        scenario_config = AgentConfig(
            agent_id=f"{self.config.retailer_id}_scenario",
            agent_type=AgentType.SCENARIO_GENERATION,
            retailer_id=self.config.retailer_id
        )
        self.scenario_agent = ScenarioGenerationAgent(
            scenario_config,
            self.message_bus,
            drivers=self.config.drivers,
            simulation_fn=self._simulate_scenario
        )
        
        # Optimization agent
        optimization_config = AgentConfig(
            agent_id=f"{self.config.retailer_id}_optimization",
            agent_type=AgentType.OPTIMIZATION,
            retailer_id=self.config.retailer_id
        )
        self.optimization_agent = OptimizationAgent(
            optimization_config,
            self.message_bus,
            drivers=self.config.drivers,
            response_fn=self._get_driver_response
        )
        
        # Governance agent
        governance_config = AgentConfig(
            agent_id=f"{self.config.retailer_id}_governance",
            agent_type=AgentType.GOVERNANCE,
            retailer_id=self.config.retailer_id
        )
        self.governance_agent = GovernanceAgent(governance_config, self.message_bus)
        
        logger.info(f"Initialized {len(self.state_agents)} state agents, "
                   f"{len(self.driver_agents)} driver agents")
    
    def _init_forecaster(self):
        """Initialize demand forecaster"""
        model_config = create_extended_config(
            lookback_weeks=self.config.lookback_weeks,
            forecast_horizon=self.config.forecast_horizon,
            hidden_dim=self.config.hidden_dim,
            num_blocks=self.config.num_blocks,
            use_bayesian=self.config.use_bayesian
        )
        
        self.forecaster = create_integrated_forecaster(model_config)
        logger.info("Initialized demand forecaster")
    
    def _init_bayesian_engine(self):
        """Initialize Bayesian engine"""
        self.bayesian_engine = ProductBayesianEngine(
            n_simulations=self.config.n_simulations
        )
        
        self.procurement_engine = ProcurementProbabilityEngine(
            n_simulations=self.config.n_simulations
        )
        
        logger.info("Initialized Bayesian and procurement engines")
    
    def _init_endogenous_bridge(self):
        """Initialize endogenous variable bridge"""
        self.endogenous_bridge = EndogenousBridge(
            lookback_weeks=self.config.lookback_weeks
        )
        logger.info("Initialized endogenous bridge")
    
    def update_state_agents(
        self,
        observations: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Update state agents with new observations.
        
        Args:
            observations: Dict of metric -> observed value
                e.g., {'total_baskets': 1000, 'basket_penetration': 0.12, ...}
        
        Returns:
            Updated belief states
        """
        results = {}
        
        for metric, agent in self.state_agents.items():
            if metric in observations:
                result = agent.process({
                    'observation': observations[metric],
                    'observation_variance': abs(observations[metric] * 0.1),
                    'source': 'orchestrator'
                })
                results[metric] = result
        
        # Update endogenous bridge
        if all(m in self.state_agents for m in ['total_baskets', 'basket_penetration', 
                                                   'items_per_basket', 'size_per_item']):
            self.endogenous_bridge.update_from_agents(
                basket_agent=self.state_agents['total_baskets'],
                penetration_agent=self.state_agents['basket_penetration'],
                items_agent=self.state_agents['items_per_basket'],
                size_agent=self.state_agents['size_per_item']
            )
        
        return results
    
    def update_driver_agents(
        self,
        driver_data: Dict[str, Dict[str, float]]
    ) -> Dict[str, Any]:
        """
        Update driver agents with spend/response data.
        
        Args:
            driver_data: Dict of driver -> {spend, response, ...}
        
        Returns:
            Updated driver states
        """
        results = {}
        
        for driver, data in driver_data.items():
            if driver in self.driver_agents:
                result = self.driver_agents[driver].process(data)
                results[driver] = result
        
        return results
    
    def generate_forecast(
        self,
        demand_history: np.ndarray,
        base_covariates: Optional[np.ndarray] = None,
        include_endogenous: bool = True
    ) -> Dict[str, np.ndarray]:
        """
        Generate demand forecast with optional endogenous variables.
        
        Args:
            demand_history: (lookback_weeks,) array of historical demand
            base_covariates: (lookback_weeks, n_base_covariates) optional
            include_endogenous: Whether to include iQueue agent states
        
        Returns:
            Dict with q10, q50, q90 forecasts and uncertainty
        """
        endogenous = None
        
        if include_endogenous and self.endogenous_bridge.state_history:
            endogenous = self.endogenous_bridge.get_covariate_matrix()
        
        predictions = self.forecaster.predict(
            demand_history=demand_history,
            base_covariates=base_covariates,
            endogenous_covariates=endogenous
        )
        
        return predictions
    
    def run_inventory_analysis(
        self,
        product_id: str,
        demand_history: np.ndarray,
        current_inventory: float,
        on_order: float,
        product_config: Optional[ProductConfig] = None,
        suppliers: Optional[List[SupplierConfig]] = None,
        sourcing_strategies: Optional[Dict[str, Dict[str, float]]] = None
    ) -> Dict[str, Any]:
        """
        Run complete inventory probability analysis.
        
        Integrates:
        - Demand forecasting (with endogenous variables)
        - Bayesian inventory probabilities
        - Procurement scenario analysis
        """
        # Register product if provided
        if product_config:
            self.bayesian_engine.register_product(product_config)
        
        # Register suppliers if provided
        if suppliers:
            for supplier in suppliers:
                self.procurement_engine.register_supplier(supplier)
        
        # Generate forecasts
        forecast_result = self.generate_forecast(demand_history)
        
        # Convert to list of dicts for Bayesian engine
        demand_forecasts = []
        for t in range(self.config.forecast_horizon):
            demand_forecasts.append({
                'q10': float(forecast_result['q10'][t]),
                'q50': float(forecast_result['q50'][t]),
                'q90': float(forecast_result['q90'][t])
            })
        
        # Run procurement scenarios if applicable
        procurement_scenarios = None
        if suppliers and sourcing_strategies:
            target_date = date.today() + timedelta(weeks=2)
            order_qty = int(sum(f['q50'] for f in demand_forecasts[:4]))
            
            procurement_scenarios = self.procurement_engine.compare_sourcing_strategies(
                order_quantity=order_qty,
                target_date=target_date,
                strategies=sourcing_strategies
            )
        
        # Get endogenous state
        endogenous_state = None
        if self.endogenous_bridge.state_history:
            endogenous_state = self.endogenous_bridge.state_history[-1]
        
        # Run Bayesian analysis
        posteriors = self.bayesian_engine.run_product_scenarios(
            product_id=product_id,
            demand_forecasts=demand_forecasts,
            current_inventory=current_inventory,
            on_order=on_order,
            endogenous_state=endogenous_state,
            procurement_scenarios=procurement_scenarios
        )
        
        # Generate recommendation
        recommendation = self._generate_recommendation(posteriors)
        
        result = {
            'product_id': product_id,
            'timestamp': datetime.utcnow().isoformat(),
            'demand_forecasts': demand_forecasts,
            'forecast_uncertainty': float(forecast_result.get('uncertainty', 0)),
            'posteriors': {k: v.to_dict() for k, v in posteriors.items()},
            'procurement_scenarios': (
                {k: {'otif': v.otif_probability, 'cost': v.expected_total_cost} 
                 for k, v in procurement_scenarios.items()}
                if procurement_scenarios else None
            ),
            'recommendation': recommendation
        }
        
        # Store in history
        self.run_history.append(result)
        self.last_update = datetime.utcnow()
        
        return result
    
    def run_optimization(
        self,
        current_allocations: Dict[str, float],
        total_budget: float
    ) -> Dict[str, Any]:
        """
        Run marketing investment optimization.
        
        Uses iQueue optimization agent with driver response functions.
        """
        from vendor.agents.iqueue.optimization import ObjectiveType, RiskMeasure
        
        result = self.optimization_agent.process({
            'current_allocations': current_allocations,
            'total_budget': total_budget,
            'objective': ObjectiveType.REVENUE,
            'risk_measure': RiskMeasure.CVAR,
            'risk_threshold': 0.2
        })
        
        # Validate through governance
        governance_result = self.governance_agent.process({
            'recommendation': result,
            'confidence_sources': {
                'optimization': result.get('confidence', 0.5)
            }
        })
        
        return {
            'optimization': result,
            'governance': governance_result
        }
    
    def run_complete_workflow(
        self,
        observations: Dict[str, float],
        driver_data: Dict[str, Dict[str, float]],
        demand_history: np.ndarray,
        current_inventory: float,
        on_order: float,
        product_id: str,
        current_allocations: Dict[str, float],
        total_budget: float
    ) -> Dict[str, Any]:
        """
        Run the complete Sense → Update → Simulate → Optimize → Explain → Learn workflow.
        """
        results = {
            'workflow_id': f"wf_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            'retailer_id': self.config.retailer_id,
            'stages': {}
        }
        
        # Stage 1: SENSE - Update state agents
        state_updates = self.update_state_agents(observations)
        results['stages']['sense'] = {
            'status': 'completed',
            'updates': len(state_updates)
        }
        
        # Stage 2: UPDATE - Update driver agents
        driver_updates = self.update_driver_agents(driver_data)
        results['stages']['update'] = {
            'status': 'completed',
            'driver_updates': len(driver_updates)
        }
        
        # Stage 3: SIMULATE - Inventory analysis
        inventory_result = self.run_inventory_analysis(
            product_id=product_id,
            demand_history=demand_history,
            current_inventory=current_inventory,
            on_order=on_order
        )
        results['stages']['simulate'] = {
            'status': 'completed',
            'baseline_stockout': inventory_result['posteriors']['baseline']['stockout_probability']
        }
        
        # Stage 4: OPTIMIZE - Marketing optimization
        optimization_result = self.run_optimization(current_allocations, total_budget)
        results['stages']['optimize'] = {
            'status': 'completed',
            'recommendation': optimization_result['optimization'].get('allocations')
        }
        
        # Stage 5: EXPLAIN - Governance check
        results['stages']['explain'] = {
            'status': 'completed',
            'decision': optimization_result['governance'].get('decision_status'),
            'requires_approval': optimization_result['governance'].get('requires_human_approval')
        }
        
        # Stage 6: LEARN - Store results
        results['stages']['learn'] = {
            'status': 'completed',
            'run_stored': True
        }
        
        results['inventory_analysis'] = inventory_result
        results['optimization'] = optimization_result
        results['completed_at'] = datetime.utcnow().isoformat()
        
        return results
    
    def _simulate_scenario(self, allocations: Dict[str, float]) -> Dict[str, Any]:
        """Simulation function for scenario agent"""
        total_response = 0
        samples = []
        
        for _ in range(100):
            response = 0
            for driver, spend in allocations.items():
                if driver in self.driver_agents:
                    agent = self.driver_agents[driver]
                    elasticity = agent.beliefs.get('elasticity')
                    if elasticity:
                        marginal = np.random.normal(elasticity.mean, elasticity.std)
                    else:
                        marginal = 1.0
                    response += spend * max(0, marginal)
            samples.append(response)
        
        return {
            'expected_value': np.mean(samples),
            'uncertainty': np.std(samples),
            'prob_improvement': 0.5,
            'confidence': 0.7,
            'samples': samples
        }
    
    def _get_driver_response(self, allocations: Dict[str, float]) -> Dict[str, Any]:
        """Response function for optimization agent"""
        return self._simulate_scenario(allocations)
    
    def _generate_recommendation(
        self,
        posteriors: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate recommendation from posteriors"""
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
        
        return recommendation
    
    def get_state_summary(self) -> Dict[str, Any]:
        """Get summary of current system state"""
        return {
            'retailer_id': self.config.retailer_id,
            'last_update': self.last_update.isoformat(),
            'num_runs': len(self.run_history),
            'state_agents': {
                metric: {
                    'mean': agent.beliefs.get(metric, 
                        type('', (), {'mean': 0, 'confidence': 0})()).mean,
                    'confidence': agent.beliefs.get(metric,
                        type('', (), {'mean': 0, 'confidence': 0})()).confidence
                }
                for metric, agent in self.state_agents.items()
            },
            'endogenous_history_length': len(self.endogenous_bridge.state_history)
        }
    
    def set_fl_parameters(self, global_params: Dict[str, np.ndarray]):
        """Update forecaster with FL-aggregated parameters"""
        if self.config.fl_enabled:
            self.forecaster.interpolate_fl_parameters(
                global_params,
                local_weight=1 - self.config.fl_aggregation_weight
            )


def create_orchestrator(
    retailer_id: str,
    segment_id: Optional[str] = None,
    **kwargs
) -> IntegrationOrchestrator:
    """Factory function for creating an integration orchestrator"""
    config = OrchestratorConfig(
        retailer_id=retailer_id,
        segment_id=segment_id,
        **kwargs
    )
    return IntegrationOrchestrator(config)
