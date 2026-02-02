"""
Retail Media Digital Twin

Simulates retail media spend outcomes across retailers, channels, and SKUs.

The Twin:
1. Maintains state for each retailer-SKU combination
2. Runs Monte Carlo simulation for media scenarios
3. Produces KPI distributions (sales, stockout, ROAS)
4. Uses Bayesian posteriors to calibrate simulations
"""

import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import logging
import copy
from collections import defaultdict

from .schemas import (
    MediaChannel,
    RetailerConfig,
    ChannelConfig,
    SKUConfig,
    ElasticityPosterior,
    RetailerSKUState,
    MediaAllocation,
    MediaScenario,
    MediaSimulationResult,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TwinConfig:
    """Configuration for retail media digital twin"""
    # Simulation settings
    default_simulation_weeks: int = 13
    default_num_simulations: int = 5000
    
    # Adstock settings
    default_adstock_decay: float = 0.7
    adstock_max_weeks: int = 4
    
    # Cross-retailer effects
    enable_cannibalization: bool = True
    default_cannibalization_rate: float = 0.05
    enable_halo_effect: bool = True
    default_halo_rate: float = 0.02
    
    # Inventory dynamics
    enable_inventory_simulation: bool = True
    default_service_level_target: float = 0.95
    
    # State persistence
    persist_states: bool = True
    state_store_path: str = "./data/media_twin_states"


class MediaSimulationEngine:
    """
    Monte Carlo simulation engine for retail media scenarios.
    
    Simulates:
    - Media-driven demand lift (using Bayesian elasticities)
    - Inventory dynamics and stockouts
    - Cross-retailer cannibalization and halo effects
    - Adstock (carryover) effects from prior spend
    """
    
    def __init__(self, config: Optional[TwinConfig] = None):
        self.config = config or TwinConfig()
    
    def simulate_scenario(
        self,
        scenario: MediaScenario,
        initial_states: Dict[str, Dict[str, RetailerSKUState]],
        elasticity_posteriors: Dict[str, Dict[str, ElasticityPosterior]],
        sku_configs: Dict[str, SKUConfig],
        n_simulations: Optional[int] = None,
        simulation_weeks: Optional[int] = None
    ) -> MediaSimulationResult:
        """
        Run Monte Carlo simulation for a media scenario.
        
        Args:
            scenario: The media scenario to simulate
            initial_states: {retailer_id: {sku_id: RetailerSKUState}}
            elasticity_posteriors: {retailer_id: {channel:category: ElasticityPosterior}}
            sku_configs: {sku_id: SKUConfig}
            n_simulations: Number of Monte Carlo paths
            simulation_weeks: Simulation horizon
        
        Returns:
            MediaSimulationResult with KPI distributions
        """
        n_sims = n_simulations or self.config.default_num_simulations
        weeks = simulation_weeks or self.config.default_simulation_weeks
        
        allocation = scenario.allocation
        
        # Initialize result arrays
        total_incremental_sales = np.zeros(n_sims)
        total_stockout_events = np.zeros(n_sims)
        total_demand = np.zeros(n_sims)
        total_spend = allocation.total_budget
        
        # Per-retailer tracking
        retailer_sales = defaultdict(lambda: np.zeros(n_sims))
        retailer_stockouts = defaultdict(lambda: np.zeros(n_sims))
        
        # Run simulations
        for sim in range(n_sims):
            # Sample elasticities from posteriors for this simulation
            sampled_elasticities = self._sample_elasticities(elasticity_posteriors)
            
            # Deep copy states for this simulation path
            sim_states = copy.deepcopy(initial_states)
            
            # Track weekly results
            cumulative_adstock = defaultdict(lambda: defaultdict(float))
            
            for week in range(weeks):
                # Get weekly spend allocation
                weekly_spend = self._get_weekly_spend(allocation, week, weeks)
                
                for retailer_id, retailer_spend in weekly_spend.items():
                    if retailer_id not in sim_states:
                        continue
                    
                    for sku_id, state in sim_states[retailer_id].items():
                        sku_config = sku_configs.get(sku_id)
                        if not sku_config:
                            continue
                        
                        # Compute media-driven lift
                        lift = self._compute_media_lift(
                            retailer_id=retailer_id,
                            sku_config=sku_config,
                            channel_spend=retailer_spend,
                            elasticities=sampled_elasticities.get(retailer_id, {}),
                            adstock=cumulative_adstock[retailer_id][sku_id],
                            scenario=scenario
                        )
                        
                        # Update adstock for next week
                        cumulative_adstock[retailer_id][sku_id] = (
                            cumulative_adstock[retailer_id][sku_id] * self.config.default_adstock_decay
                            + sum(retailer_spend.values())
                        )
                        
                        # Compute demand with scenario adjustments
                        base_demand = state.base_demand_mean * scenario.demand_multiplier
                        demand_noise = np.random.normal(0, state.base_demand_std)
                        total_demand_units = max(0, base_demand * (1 + lift) + demand_noise)
                        
                        # Apply cross-retailer effects
                        if self.config.enable_cannibalization:
                            cannibalization = self._compute_cannibalization(
                                retailer_id, sku_id, sim_states, weekly_spend
                            )
                            total_demand_units *= (1 - cannibalization)
                        
                        # Channel-focused simulation (no inventory constraints)
                        fulfilled = total_demand_units
                        stockout_units = 0
                        
                        # Update channel state metrics
                        state.total_impressions += weekly_spend.get(retailer_id, 0) * 100  # Approximate impressions
                        state.total_conversions += fulfilled * 0.02  # Approximate conversion rate
                        
                        # Compute revenue
                        incremental_sales = fulfilled * lift * sku_config.unit_price
                        state.revenue += incremental_sales
                        
                        # Accumulate results
                        total_incremental_sales[sim] += incremental_sales
                        total_demand[sim] += total_demand_units
                        if stockout_units > 0:
                            total_stockout_events[sim] += 1
                        
                        retailer_sales[retailer_id][sim] += incremental_sales
                        if stockout_units > 0:
                            retailer_stockouts[retailer_id][sim] += 1
        
        # Compute stockout rate
        total_sku_weeks = len(initial_states) * sum(len(skus) for skus in initial_states.values()) * weeks
        stockout_rate = total_stockout_events / max(1, total_sku_weeks)
        
        # Compute ROAS
        roas = total_incremental_sales / total_spend if total_spend > 0 else np.zeros(n_sims)
        
        # Identify binding constraints
        binding_constraints = self._identify_binding_constraints(
            retailer_stockouts, total_stockout_events, scenario
        )
        
        # Build result
        result = MediaSimulationResult(
            scenario_id=scenario.scenario_id,
            scenario_name=scenario.scenario_name,
            n_simulations=n_sims,
            simulation_weeks=weeks,
            incremental_sales_dist=total_incremental_sales.tolist(),
            stockout_rate_dist=stockout_rate.tolist(),
            roas_dist=roas.tolist(),
            binding_constraints=binding_constraints,
            retailer_results={
                r: {
                    'expected_sales': float(np.mean(sales)),
                    'expected_stockouts': float(np.mean(retailer_stockouts[r]))
                }
                for r, sales in retailer_sales.items()
            }
        )
        
        # Compute summary statistics
        result.compute_summary_stats()
        
        logger.info(
            f"Simulated scenario '{scenario.scenario_name}': "
            f"E[sales]=${result.expected_incremental_sales/1e6:.2f}M, "
            f"E[stockout]={result.expected_stockout_rate:.1%}, "
            f"E[ROAS]={result.expected_roas:.1f}x"
        )
        
        return result
    
    def _sample_elasticities(
        self,
        posteriors: Dict[str, Dict[str, ElasticityPosterior]]
    ) -> Dict[str, Dict[str, float]]:
        """Sample elasticity values from posteriors for one simulation"""
        sampled = {}
        for retailer_id, retailer_posteriors in posteriors.items():
            sampled[retailer_id] = {}
            for key, posterior in retailer_posteriors.items():
                # Sample one value from the posterior
                sampled[retailer_id][key] = float(posterior.sample(1)[0])
        return sampled
    
    def _get_weekly_spend(
        self,
        allocation: MediaAllocation,
        week: int,
        total_weeks: int
    ) -> Dict[str, Dict[str, float]]:
        """Get spend allocation for a specific week"""
        if allocation.weekly_spend and week in allocation.weekly_spend:
            return allocation.weekly_spend[week]
        
        # Uniform distribution across weeks
        weekly_factor = 1.0 / total_weeks
        return {
            retailer: {
                channel: spend * weekly_factor
                for channel, spend in channels.items()
            }
            for retailer, channels in allocation.spend_by_retailer_channel.items()
        }
    
    def _compute_media_lift(
        self,
        retailer_id: str,
        sku_config: SKUConfig,
        channel_spend: Dict[str, float],
        elasticities: Dict[str, float],
        adstock: float,
        scenario: MediaScenario
    ) -> float:
        """Compute total media-driven demand lift"""
        total_lift = 0.0
        
        for channel, spend in channel_spend.items():
            key = f"{channel}:{sku_config.category}"
            elasticity = elasticities.get(key, 0.15)
            
            # Apply scenario elasticity multiplier
            elasticity *= scenario.elasticity_multiplier
            
            # Apply SKU responsiveness
            elasticity *= sku_config.media_responsiveness
            
            # Diminishing returns (log transform)
            if spend > 0:
                log_spend = np.log(spend / 1000 + 1)  # Normalize to thousands
                channel_lift = elasticity * log_spend
                total_lift += channel_lift
        
        # Add adstock contribution (decayed prior spend effect)
        if adstock > 0:
            adstock_lift = 0.05 * np.log(adstock / 1000 + 1)
            total_lift += adstock_lift
        
        return total_lift
    
    def _compute_cannibalization(
        self,
        retailer_id: str,
        sku_id: str,
        states: Dict[str, Dict[str, RetailerSKUState]],
        weekly_spend: Dict[str, Dict[str, float]]
    ) -> float:
        """Compute demand cannibalized by other retailers"""
        if not self.config.enable_cannibalization:
            return 0.0
        
        own_spend = sum(weekly_spend.get(retailer_id, {}).values())
        total_other_spend = sum(
            sum(channels.values())
            for r, channels in weekly_spend.items()
            if r != retailer_id
        )
        
        if own_spend + total_other_spend == 0:
            return 0.0
        
        # Cannibalization proportional to competitor spend share
        competitor_share = total_other_spend / (own_spend + total_other_spend)
        cannibalization = self.config.default_cannibalization_rate * competitor_share
        
        return min(0.2, cannibalization)  # Cap at 20%
    
    def _identify_binding_constraints(
        self,
        retailer_stockouts: Dict[str, np.ndarray],
        total_stockouts: np.ndarray,
        scenario: MediaScenario
    ) -> List[str]:
        """Identify which constraints are binding"""
        constraints = []
        
        # High overall stockout rate
        if np.mean(total_stockouts) > 0.1 * len(retailer_stockouts):
            constraints.append("inventory_capacity")
        
        # Per-retailer constraints
        for retailer_id, stockouts in retailer_stockouts.items():
            if np.mean(stockouts) > 0.15:
                constraints.append(f"inventory:{retailer_id}")
        
        # Supply disruption
        if scenario.supply_disruption > 0.1:
            constraints.append("supply_disruption")
        
        return constraints


class RetailMediaTwin:
    """
    Digital Twin for retail media network simulation.
    
    Maintains state for retailer-SKU combinations and runs scenario simulations
    using Bayesian posteriors from the analysis layer.
    """
    
    def __init__(self, config: Optional[TwinConfig] = None):
        self.config = config or TwinConfig()
        self.simulation_engine = MediaSimulationEngine(config)
        
        # Configuration registries
        self.retailers: Dict[str, RetailerConfig] = {}
        self.channels: Dict[MediaChannel, ChannelConfig] = {}
        self.skus: Dict[str, SKUConfig] = {}
        
        # State management
        self.states: Dict[str, Dict[str, RetailerSKUState]] = {}
        # Format: {retailer_id: {sku_id: RetailerSKUState}}
        
        # Bayesian posteriors (fed from analysis layer)
        self.elasticity_posteriors: Dict[str, Dict[str, ElasticityPosterior]] = {}
        
        # Simulation history
        self.simulation_history: List[MediaSimulationResult] = []
        
        logger.info("RetailMediaTwin initialized")
    
    def register_retailer(self, config: RetailerConfig):
        """Register a retailer"""
        self.retailers[config.retailer_id] = config
        if config.retailer_id not in self.states:
            self.states[config.retailer_id] = {}
        logger.info(f"Registered retailer: {config.retailer_id}")
    
    def register_channel(self, config: ChannelConfig):
        """Register a channel"""
        self.channels[config.channel] = config
        logger.info(f"Registered channel: {config.channel.value}")
    
    def register_sku(self, config: SKUConfig):
        """Register a SKU"""
        self.skus[config.sku_id] = config
        logger.info(f"Registered SKU: {config.sku_id}")
    
    def initialize_state(
        self,
        retailer_id: str,
        sku_id: str,
        initial_inventory: float,
        base_demand_mean: float,
        base_demand_std: float,
        elasticity_posteriors: Optional[Dict[str, ElasticityPosterior]] = None
    ) -> RetailerSKUState:
        """Initialize state for a retailer-SKU combination"""
        sku_config = self.skus.get(sku_id)
        
        state = RetailerSKUState(
            retailer_id=retailer_id,
            sku_id=sku_id,
            week=0,
            base_demand_mean=base_demand_mean,
            base_demand_std=base_demand_std,
        )
        
        # Set elasticity beliefs from posteriors
        if elasticity_posteriors:
            state.elasticity_by_channel = {
                k: p.mean for k, p in elasticity_posteriors.items()
            }
            state.elasticity_uncertainty = {
                k: p.std for k, p in elasticity_posteriors.items()
            }
        
        if retailer_id not in self.states:
            self.states[retailer_id] = {}
        self.states[retailer_id][sku_id] = state
        
        logger.info(f"Initialized state for {retailer_id}:{sku_id}")
        return state
    
    def initialize_from_bayesian_posteriors(
        self,
        posteriors: Dict[str, Dict[str, ElasticityPosterior]]
    ):
        """
        Initialize Twin with Bayesian posteriors.
        
        This is the key "Bayesian → Twin" integration point.
        """
        self.elasticity_posteriors = posteriors
        
        # Update all states with posterior information
        for retailer_id, retailer_posteriors in posteriors.items():
            if retailer_id in self.states:
                for sku_id, state in self.states[retailer_id].items():
                    state.elasticity_by_channel = {
                        k: p.mean for k, p in retailer_posteriors.items()
                    }
                    state.elasticity_uncertainty = {
                        k: p.std for k, p in retailer_posteriors.items()
                    }
        
        logger.info(f"Initialized Twin with Bayesian posteriors for {len(posteriors)} retailers")
    
    def simulate_scenario(
        self,
        scenario: MediaScenario,
        n_simulations: Optional[int] = None,
        simulation_weeks: Optional[int] = None
    ) -> MediaSimulationResult:
        """Run simulation for a single scenario"""
        result = self.simulation_engine.simulate_scenario(
            scenario=scenario,
            initial_states=self.states,
            elasticity_posteriors=self.elasticity_posteriors,
            sku_configs=self.skus,
            n_simulations=n_simulations,
            simulation_weeks=simulation_weeks
        )
        
        self.simulation_history.append(result)
        return result
    
    def compare_scenarios(
        self,
        scenarios: List[MediaScenario],
        n_simulations: Optional[int] = None,
        simulation_weeks: Optional[int] = None
    ) -> Dict[str, MediaSimulationResult]:
        """
        Compare multiple scenarios.
        
        Returns simulation results for each scenario, enabling comparison.
        """
        results = {}
        
        for scenario in scenarios:
            result = self.simulate_scenario(
                scenario, n_simulations, simulation_weeks
            )
            results[scenario.scenario_id] = result
        
        # Log comparison summary
        logger.info("Scenario Comparison:")
        for scenario_id, result in results.items():
            logger.info(
                f"  {result.scenario_name}: "
                f"Sales=${result.expected_incremental_sales/1e6:.2f}M "
                f"[${result.sales_ci_lower/1e6:.2f}M, ${result.sales_ci_upper/1e6:.2f}M], "
                f"ROAS={result.expected_roas:.1f}x"
            )
        
        return results
    
    def get_scenario_ranking(
        self,
        results: Dict[str, MediaSimulationResult],
        objective: str = "sales",
        risk_aversion: float = 0.0
    ) -> List[Tuple[str, float]]:
        """
        Rank scenarios by objective, optionally with risk adjustment.
        
        Args:
            results: Simulation results by scenario
            objective: 'sales', 'roas', or 'risk_adjusted'
            risk_aversion: Weight on downside risk (0 = neutral, 1 = very risk averse)
        
        Returns:
            List of (scenario_id, score) tuples, sorted descending
        """
        scores = []
        
        for scenario_id, result in results.items():
            if objective == "sales":
                score = result.expected_incremental_sales
            elif objective == "roas":
                score = result.expected_roas
            elif objective == "risk_adjusted":
                # Score = E[sales] - risk_aversion * (E[sales] - CI_lower)
                downside = result.expected_incremental_sales - result.sales_ci_lower
                score = result.expected_incremental_sales - risk_aversion * downside
            else:
                score = result.expected_incremental_sales
            
            # Penalize high stockout rate
            stockout_penalty = result.expected_stockout_rate * result.expected_incremental_sales * 0.5
            score -= stockout_penalty
            
            scores.append((scenario_id, score))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores
    
    def get_state_summary(self) -> Dict[str, Any]:
        """Get summary of current Twin state"""
        total_revenue = 0
        total_demand = 0
        total_impressions = 0
        n_states = 0
        
        for retailer_states in self.states.values():
            for state in retailer_states.values():
                total_revenue += state.revenue
                total_demand += state.base_demand_mean
                total_impressions += state.total_impressions
                n_states += 1
        
        return {
            'n_retailers': len(self.states),
            'n_states': n_states,
            'total_revenue': total_revenue,
            'total_weekly_demand': total_demand,
            'total_impressions': total_impressions,
            'n_posteriors': sum(len(p) for p in self.elasticity_posteriors.values()),
        }
    
    def feed_to_agents(
        self,
        scenario_results: Dict[str, MediaSimulationResult]
    ) -> Dict[str, Any]:
        """
        Format simulation results for agent consumption.
        
        This is the "Twin → Agents" data flow.
        """
        agent_context = {
            'twin_results': {
                scenario_id: result.to_dict()
                for scenario_id, result in scenario_results.items()
            },
            'scenario_ranking': self.get_scenario_ranking(scenario_results, 'risk_adjusted', 0.3),
            'elasticity_posteriors': {
                retailer_id: {
                    key: posterior.to_dict()
                    for key, posterior in posteriors.items()
                }
                for retailer_id, posteriors in self.elasticity_posteriors.items()
            },
            'state_summary': self.get_state_summary(),
            'binding_constraints': list(set(
                constraint
                for result in scenario_results.values()
                for constraint in result.binding_constraints
            )),
        }
        
        return agent_context
