"""
Digital Twin Simulation Service

FR-8.1: Maintain a living state representation of demand + inventory + constraints + policies
(weekly updates).

FR-8.2: Provide scenario simulation endpoints (e.g., "lead time +2 weeks", "promo on/off")
returning KPI distributions and recommended actions.

Implements a stateful simulation service for inventory/demand scenarios.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
import json
import hashlib
import logging
from pathlib import Path
import copy

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.schemas.data_contracts import (
    TwinState, ScenarioRequest, ScenarioResult,
    DemandForecastSummary, PosteriorOutcome, OptimizationResult,
    HierarchyLevel
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TwinConfig:
    """Configuration for digital twin service"""
    # State management
    state_store_path: str = "./data/twin_states"
    max_state_history: int = 52  # Keep 1 year of weekly states
    
    # Simulation settings
    default_simulation_weeks: int = 13
    default_num_simulations: int = 1000
    
    # Update frequency
    auto_update_on_forecast: bool = True
    
    # Persistence
    persist_states: bool = True


@dataclass
class EntityState:
    """State of a single entity (SKU/store combination)"""
    entity_id: str
    
    # Inventory state
    on_hand: float
    on_order: float
    backorders: float
    
    # Demand model
    expected_weekly_demand: float
    demand_std: float
    
    # Supply parameters
    lead_time_weeks: int
    moq: int
    case_pack: int
    
    # Current policy
    reorder_point: float
    order_quantity: float
    
    # Costs
    unit_cost: float
    holding_cost_rate: float
    stockout_cost: float
    
    # Metadata
    last_updated: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'entity_id': self.entity_id,
            'on_hand': self.on_hand,
            'on_order': self.on_order,
            'backorders': self.backorders,
            'expected_weekly_demand': self.expected_weekly_demand,
            'demand_std': self.demand_std,
            'lead_time_weeks': self.lead_time_weeks,
            'moq': self.moq,
            'case_pack': self.case_pack,
            'reorder_point': self.reorder_point,
            'order_quantity': self.order_quantity,
            'unit_cost': self.unit_cost,
            'holding_cost_rate': self.holding_cost_rate,
            'stockout_cost': self.stockout_cost,
            'last_updated': self.last_updated.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EntityState':
        data = data.copy()
        if isinstance(data.get('last_updated'), str):
            data['last_updated'] = datetime.fromisoformat(data['last_updated'])
        return cls(**data)


class InventorySimulationEngine:
    """
    Monte Carlo simulation engine for inventory dynamics.
    
    Simulates inventory levels, orders, stockouts over a planning horizon.
    """
    
    def __init__(self, num_simulations: int = 1000):
        self.num_simulations = num_simulations
    
    def simulate_entity(
        self,
        entity_state: EntityState,
        horizon_weeks: int,
        demand_samples: Optional[np.ndarray] = None,
        policy_override: Optional[Dict[str, Any]] = None
    ) -> Dict[str, np.ndarray]:
        """
        Simulate inventory dynamics for a single entity.
        
        Args:
            entity_state: Current state of the entity
            horizon_weeks: Number of weeks to simulate
            demand_samples: Optional pre-generated demand samples (n_sims x horizon)
            policy_override: Optional policy changes (reorder_point, order_quantity)
        
        Returns:
            Dict of KPI arrays (n_simulations,)
        """
        n_sims = self.num_simulations
        
        # Generate demand samples if not provided
        if demand_samples is None:
            demand_samples = np.maximum(
                0,
                np.random.normal(
                    entity_state.expected_weekly_demand,
                    entity_state.demand_std,
                    (n_sims, horizon_weeks)
                )
            )
        
        # Get policy parameters
        rop = policy_override.get('reorder_point', entity_state.reorder_point) if policy_override else entity_state.reorder_point
        order_qty = policy_override.get('order_quantity', entity_state.order_quantity) if policy_override else entity_state.order_quantity
        lead_time = policy_override.get('lead_time_weeks', entity_state.lead_time_weeks) if policy_override else entity_state.lead_time_weeks
        
        # Initialize tracking arrays
        total_demand = np.zeros(n_sims)
        total_fulfilled = np.zeros(n_sims)
        stockout_weeks = np.zeros(n_sims)
        ending_inventory = np.zeros(n_sims)
        total_orders_placed = np.zeros(n_sims)
        total_holding_cost = np.zeros(n_sims)
        
        weekly_holding_rate = entity_state.holding_cost_rate / 52
        
        for sim in range(n_sims):
            # Initialize state
            inventory = entity_state.on_hand
            pipeline = [0] * max(1, lead_time)
            pipeline[0] = entity_state.on_order
            
            for week in range(horizon_weeks):
                # Receive incoming orders
                if lead_time > 0:
                    incoming = pipeline.pop(0)
                    inventory += incoming
                    pipeline.append(0)
                
                # Fulfill demand
                demand = demand_samples[sim, week]
                fulfilled = min(inventory, demand)
                inventory -= fulfilled
                
                total_demand[sim] += demand
                total_fulfilled[sim] += fulfilled
                
                if fulfilled < demand:
                    stockout_weeks[sim] += 1
                
                # Calculate holding cost
                total_holding_cost[sim] += inventory * entity_state.unit_cost * weekly_holding_rate
                
                # Check reorder point and place order
                inventory_position = inventory + sum(pipeline)
                if inventory_position <= rop:
                    order = max(order_qty, entity_state.moq)
                    order = int(np.ceil(order / entity_state.case_pack) * entity_state.case_pack)
                    
                    if lead_time > 0:
                        pipeline[-1] += order
                    else:
                        inventory += order
                    
                    total_orders_placed[sim] += order
            
            ending_inventory[sim] = inventory
        
        # Calculate derived metrics
        service_level = total_fulfilled / np.maximum(total_demand, 1)
        stockout_rate = stockout_weeks / horizon_weeks
        fill_rate = total_fulfilled / np.maximum(total_demand, 1)
        inventory_turns = total_demand / np.maximum(
            (entity_state.on_hand + ending_inventory) / 2, 1
        )
        
        # Stockout cost
        stockout_units = total_demand - total_fulfilled
        stockout_cost = stockout_units * entity_state.stockout_cost
        
        # Total cost
        total_cost = total_holding_cost + stockout_cost
        
        return {
            'service_level': service_level,
            'stockout_rate': stockout_rate,
            'fill_rate': fill_rate,
            'ending_inventory': ending_inventory,
            'total_demand': total_demand,
            'total_fulfilled': total_fulfilled,
            'total_orders': total_orders_placed,
            'inventory_turns': inventory_turns,
            'holding_cost': total_holding_cost,
            'stockout_cost': stockout_cost,
            'total_cost': total_cost,
        }


class DigitalTwinService:
    """
    Main Digital Twin service.
    
    FR-8.1: Maintains living state representation
    FR-8.2: Provides scenario simulation endpoints
    """
    
    def __init__(self, config: Optional[TwinConfig] = None):
        self.config = config or TwinConfig()
        self.simulation_engine = InventorySimulationEngine(
            self.config.default_num_simulations
        )
        
        # State management
        self.current_state: Optional[TwinState] = None
        self.entity_states: Dict[str, EntityState] = {}
        self.state_history: List[TwinState] = []
        
        # Setup persistence
        if self.config.persist_states:
            state_path = Path(self.config.state_store_path)
            state_path.mkdir(parents=True, exist_ok=True)
        
        self.run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    
    def initialize_state(
        self,
        inventory_data: pd.DataFrame,
        supply_params: pd.DataFrame,
        forecast_summaries: List[DemandForecastSummary],
        week_start: date,
        policy_version: str = "default"
    ) -> str:
        """
        Initialize digital twin state from data.
        
        Args:
            inventory_data: DataFrame with on_hand, on_order, backorders by entity
            supply_params: DataFrame with lead_time, moq, case_pack by entity
            forecast_summaries: List of forecast summaries for demand estimates
            week_start: Current week start date
            policy_version: Version identifier for current policies
        
        Returns:
            state_id for the created state
        """
        # Build entity states
        entity_states = {}
        
        # Process inventory data
        for _, row in inventory_data.iterrows():
            entity_id = row.get('sku_id') or row.get('entity_id')
            
            # Get supply params
            supply_row = supply_params[supply_params['sku_id'] == entity_id]
            if len(supply_row) == 0:
                continue
            supply_row = supply_row.iloc[0]
            
            # Get demand estimates from forecasts
            entity_forecasts = [f for f in forecast_summaries if f.entity_id == entity_id]
            if entity_forecasts:
                avg_demand = np.mean([f.q50 for f in entity_forecasts])
                demand_std = np.mean([(f.q90 - f.q10) / 2.56 for f in entity_forecasts])
            else:
                avg_demand = 100  # Default
                demand_std = 25
            
            # Create entity state
            entity_state = EntityState(
                entity_id=entity_id,
                on_hand=float(row.get('on_hand', 0)),
                on_order=float(row.get('on_order', 0)),
                backorders=float(row.get('backorders', 0)),
                expected_weekly_demand=avg_demand,
                demand_std=demand_std,
                lead_time_weeks=int(supply_row.get('lead_time_weeks', 2)),
                moq=int(supply_row.get('moq', 12)),
                case_pack=int(supply_row.get('case_pack', 6)),
                reorder_point=avg_demand * 3,  # Default: 3 weeks
                order_quantity=avg_demand * 4,  # Default: 4 weeks
                unit_cost=float(supply_row.get('unit_cost', 10.0)),
                holding_cost_rate=0.25,
                stockout_cost=5.0
            )
            
            entity_states[entity_id] = entity_state
        
        self.entity_states = entity_states
        
        # Create twin state
        state_id = f"state_{week_start.isoformat()}_{self.run_id}"
        model_version = forecast_summaries[0].model_version if forecast_summaries else "unknown"
        
        self.current_state = TwinState(
            state_id=state_id,
            week_start=week_start,
            entity_states={eid: es.to_dict() for eid, es in entity_states.items()},
            demand_model_version=model_version,
            policy_version=policy_version
        )
        
        # Save state
        if self.config.persist_states:
            self._save_state(self.current_state)
        
        logger.info(f"Initialized twin state {state_id} with {len(entity_states)} entities")
        return state_id
    
    def update_state(
        self,
        updates: Dict[str, Dict[str, Any]],
        week_start: Optional[date] = None
    ) -> str:
        """
        Update current state with new data.
        
        FR-8.1: Weekly updates to living state
        """
        if self.current_state is None:
            raise ValueError("No current state to update. Call initialize_state first.")
        
        # Apply updates to entity states
        for entity_id, entity_updates in updates.items():
            if entity_id in self.entity_states:
                state = self.entity_states[entity_id]
                for key, value in entity_updates.items():
                    if hasattr(state, key):
                        setattr(state, key, value)
                state.last_updated = datetime.utcnow()
        
        # Create new state version
        new_week = week_start or (self.current_state.week_start + timedelta(weeks=1))
        new_state_id = f"state_{new_week.isoformat()}_{self.run_id}"
        
        # Archive current state
        self.state_history.append(self.current_state)
        if len(self.state_history) > self.config.max_state_history:
            self.state_history.pop(0)
        
        # Create updated state
        self.current_state = TwinState(
            state_id=new_state_id,
            week_start=new_week,
            entity_states={eid: es.to_dict() for eid, es in self.entity_states.items()},
            demand_model_version=self.current_state.demand_model_version,
            policy_version=self.current_state.policy_version
        )
        
        if self.config.persist_states:
            self._save_state(self.current_state)
        
        logger.info(f"Updated twin state to {new_state_id}")
        return new_state_id
    
    def simulate_scenario(
        self,
        request: ScenarioRequest
    ) -> ScenarioResult:
        """
        Run scenario simulation.
        
        FR-8.2: Scenario simulation endpoints
        
        Supported modifications:
        - lead_time_delta: Change in lead time (weeks)
        - demand_multiplier: Scale demand by factor
        - reorder_point_delta: Change in reorder point
        - order_quantity_delta: Change in order quantity
        - promo_effect: Promotional demand lift
        """
        if self.current_state is None:
            raise ValueError("No current state. Call initialize_state first.")
        
        logger.info(f"Running scenario: {request.scenario_name}")
        
        # Parse modifications
        mods = request.modifications
        lead_time_delta = mods.get('lead_time_delta', 0)
        demand_multiplier = mods.get('demand_multiplier', 1.0)
        rop_delta = mods.get('reorder_point_delta', 0)
        qty_delta = mods.get('order_quantity_delta', 0)
        promo_effect = mods.get('promo_effect', 0)
        
        # Effective demand multiplier with promo
        effective_demand_mult = demand_multiplier * (1 + promo_effect)
        
        # Run simulations for each entity
        kpi_aggregates = {
            'service_level': [],
            'stockout_rate': [],
            'total_cost': [],
            'ending_inventory': [],
            'inventory_turns': []
        }
        
        entity_results = {}
        
        for entity_id, entity_state in self.entity_states.items():
            # Apply scenario modifications
            scenario_policy = {
                'lead_time_weeks': max(0, entity_state.lead_time_weeks + lead_time_delta),
                'reorder_point': max(0, entity_state.reorder_point + rop_delta),
                'order_quantity': max(entity_state.moq, entity_state.order_quantity + qty_delta),
            }
            
            # Generate demand samples with modification
            demand_samples = np.maximum(
                0,
                np.random.normal(
                    entity_state.expected_weekly_demand * effective_demand_mult,
                    entity_state.demand_std * np.sqrt(effective_demand_mult),
                    (request.num_simulations, request.simulation_weeks)
                )
            )
            
            # Run simulation
            results = self.simulation_engine.simulate_entity(
                entity_state,
                request.simulation_weeks,
                demand_samples=demand_samples,
                policy_override=scenario_policy
            )
            
            entity_results[entity_id] = results
            
            # Aggregate KPIs
            for kpi in kpi_aggregates:
                if kpi in results:
                    kpi_aggregates[kpi].extend(results[kpi].tolist())
        
        # Compute KPI distributions
        kpi_distributions = {}
        for kpi_name, values in kpi_aggregates.items():
            if values:
                arr = np.array(values)
                kpi_distributions[kpi_name] = {
                    'mean': float(np.mean(arr)),
                    'std': float(np.std(arr)),
                    'q10': float(np.percentile(arr, 10)),
                    'q50': float(np.percentile(arr, 50)),
                    'q90': float(np.percentile(arr, 90)),
                }
        
        # Generate recommended actions (placeholder - would call optimizer)
        recommended_actions = []
        
        return ScenarioResult(
            scenario_name=request.scenario_name,
            base_state_id=request.base_state_id,
            kpi_distributions=kpi_distributions,
            recommended_actions=recommended_actions,
            simulation_metadata={
                'num_simulations': request.num_simulations,
                'simulation_weeks': request.simulation_weeks,
                'num_entities': len(self.entity_states),
                'modifications': request.modifications,
            },
            run_id=self.run_id
        )
    
    def compare_scenarios(
        self,
        scenarios: List[ScenarioRequest]
    ) -> Dict[str, ScenarioResult]:
        """
        Compare multiple scenarios.
        
        FR-8.2: Scenario comparison
        """
        results = {}
        
        # Always include baseline
        baseline_request = ScenarioRequest(
            scenario_name="baseline",
            base_state_id=self.current_state.state_id if self.current_state else "",
            modifications={},
            simulation_weeks=self.config.default_simulation_weeks,
            num_simulations=self.config.default_num_simulations
        )
        results["baseline"] = self.simulate_scenario(baseline_request)
        
        # Run each scenario
        for request in scenarios:
            results[request.scenario_name] = self.simulate_scenario(request)
        
        return results
    
    def _save_state(self, state: TwinState):
        """Persist state to disk"""
        state_path = Path(self.config.state_store_path) / f"{state.state_id}.json"
        with open(state_path, 'w') as f:
            json.dump({
                'state_id': state.state_id,
                'week_start': str(state.week_start),
                'entity_states': state.entity_states,
                'demand_model_version': state.demand_model_version,
                'policy_version': state.policy_version,
                'last_updated': state.last_updated.isoformat()
            }, f, indent=2)
    
    def load_state(self, state_id: str) -> Optional[TwinState]:
        """Load state from disk"""
        state_path = Path(self.config.state_store_path) / f"{state_id}.json"
        if not state_path.exists():
            return None
        
        with open(state_path) as f:
            data = json.load(f)
        
        return TwinState(
            state_id=data['state_id'],
            week_start=date.fromisoformat(data['week_start']),
            entity_states=data['entity_states'],
            demand_model_version=data['demand_model_version'],
            policy_version=data['policy_version']
        )


def create_digital_twin(config: Optional[TwinConfig] = None) -> DigitalTwinService:
    """Factory function for digital twin service"""
    return DigitalTwinService(config)


if __name__ == "__main__":
    # Test digital twin service
    twin = create_digital_twin()
    
    # Create sample data
    inventory_data = pd.DataFrame([
        {'sku_id': 'SKU-0001', 'on_hand': 500, 'on_order': 200, 'backorders': 0},
        {'sku_id': 'SKU-0002', 'on_hand': 300, 'on_order': 100, 'backorders': 10},
        {'sku_id': 'SKU-0003', 'on_hand': 800, 'on_order': 0, 'backorders': 0},
    ])
    
    supply_params = pd.DataFrame([
        {'sku_id': 'SKU-0001', 'lead_time_weeks': 2, 'moq': 24, 'case_pack': 12, 'unit_cost': 10.0},
        {'sku_id': 'SKU-0002', 'lead_time_weeks': 3, 'moq': 48, 'case_pack': 24, 'unit_cost': 15.0},
        {'sku_id': 'SKU-0003', 'lead_time_weeks': 1, 'moq': 12, 'case_pack': 6, 'unit_cost': 8.0},
    ])
    
    # Create forecast summaries
    forecast_summaries = []
    for sku in ['SKU-0001', 'SKU-0002', 'SKU-0003']:
        for week in range(13):
            forecast_summaries.append(DemandForecastSummary(
                entity_id=sku,
                entity_level=HierarchyLevel.SKU,
                week_start=date(2024, 1, 1) + timedelta(weeks=week),
                q10=80, q50=100, q90=130,
                model_version="test-v1",
                run_id="test-run"
            ))
    
    # Initialize state
    state_id = twin.initialize_state(
        inventory_data,
        supply_params,
        forecast_summaries,
        week_start=date(2024, 1, 1)
    )
    
    print(f"\n=== Digital Twin Initialized ===")
    print(f"State ID: {state_id}")
    print(f"Entities: {len(twin.entity_states)}")
    
    # Run scenario comparison
    scenarios = [
        ScenarioRequest(
            scenario_name="lead_time_shock",
            base_state_id=state_id,
            modifications={'lead_time_delta': 2},
            simulation_weeks=13,
            num_simulations=500
        ),
        ScenarioRequest(
            scenario_name="demand_surge",
            base_state_id=state_id,
            modifications={'demand_multiplier': 1.3},
            simulation_weeks=13,
            num_simulations=500
        ),
        ScenarioRequest(
            scenario_name="promo_campaign",
            base_state_id=state_id,
            modifications={'promo_effect': 0.25},
            simulation_weeks=13,
            num_simulations=500
        ),
    ]
    
    results = twin.compare_scenarios(scenarios)
    
    print("\n=== Scenario Comparison Results ===")
    for name, result in results.items():
        print(f"\n{name}:")
        for kpi, dist in result.kpi_distributions.items():
            print(f"  {kpi}: mean={dist['mean']:.3f}, q10={dist['q10']:.3f}, q90={dist['q90']:.3f}")
