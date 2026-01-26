"""
Scenario Generation Agent

Responsibilities:
- Auto-generates plausible reallocations (fixed budget, incremental, pack-level shifts)
- Runs scenario batches through the simulation engine
- Prunes scenarios based on expected value, uncertainty, and feasibility

Business value: expands decision coverage without proportional analyst effort.
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
import logging
import itertools

from .base import (
    BaseIQueueAgent, AgentConfig, AgentType, BeliefState,
    AgentMessage, MessageType, ConfidenceLevel, AgentMessageBus
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ScenarioType(str, Enum):
    """Types of scenarios"""
    FIXED_BUDGET = "fixed_budget"  # Reallocate within fixed budget
    INCREMENTAL = "incremental"    # Add/remove spend
    PACK_SHIFT = "pack_shift"      # Shift between product packs/SKUs
    TIMING_SHIFT = "timing_shift"  # Shift spend timing
    COMPETITIVE = "competitive"    # Response to competitor actions
    STRESS_TEST = "stress_test"    # Extreme scenarios


class PruningCriteria(str, Enum):
    """Criteria for pruning scenarios"""
    EXPECTED_VALUE = "expected_value"
    UNCERTAINTY = "uncertainty"
    FEASIBILITY = "feasibility"
    DOMINANCE = "dominance"
    DIVERSITY = "diversity"


@dataclass
class ScenarioCandidate:
    """A candidate scenario to evaluate"""
    scenario_id: str
    scenario_type: ScenarioType
    name: str
    description: str
    
    # Allocations
    driver_allocations: Dict[str, float]
    baseline_allocations: Dict[str, float]
    delta_allocations: Dict[str, float]
    
    # Expected outcomes
    expected_value: Optional[float] = None
    expected_uncertainty: Optional[float] = None
    probability_of_improvement: Optional[float] = None
    
    # Feasibility
    is_feasible: bool = True
    feasibility_violations: List[str] = field(default_factory=list)
    
    # Metadata
    confidence: float = 0.5
    generation_method: str = "grid"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'scenario_id': self.scenario_id,
            'scenario_type': self.scenario_type.value,
            'name': self.name,
            'description': self.description,
            'driver_allocations': self.driver_allocations,
            'delta_allocations': self.delta_allocations,
            'expected_value': self.expected_value,
            'expected_uncertainty': self.expected_uncertainty,
            'probability_of_improvement': self.probability_of_improvement,
            'is_feasible': self.is_feasible,
            'feasibility_violations': self.feasibility_violations,
            'confidence': self.confidence,
            'generation_method': self.generation_method
        }


@dataclass
class ScenarioBatch:
    """Batch of scenarios for evaluation"""
    batch_id: str
    scenarios: List[ScenarioCandidate]
    total_budget: float
    constraints: Dict[str, Any]
    
    # After evaluation
    evaluated: bool = False
    best_scenario_id: Optional[str] = None
    pareto_frontier: List[str] = field(default_factory=list)
    
    timestamp: datetime = field(default_factory=datetime.utcnow)


class ScenarioGenerationAgent(BaseIQueueAgent):
    """
    Scenario Generation Agent
    
    Auto-generates scenarios for evaluation:
    - Fixed budget reallocations
    - Incremental spend changes
    - Pack/SKU level shifts
    - Timing shifts
    - Competitive responses
    - Stress tests
    
    Prunes scenarios based on expected value, uncertainty, and feasibility.
    """
    
    def __init__(
        self,
        config: AgentConfig,
        message_bus: Optional[AgentMessageBus] = None,
        drivers: Optional[List[str]] = None,
        simulation_fn: Optional[Callable] = None
    ):
        self.drivers = drivers or ['media', 'price', 'trade']
        self.simulation_fn = simulation_fn  # Function to simulate scenario outcomes
        self.generated_scenarios: List[ScenarioCandidate] = []
        self.evaluated_batches: List[ScenarioBatch] = []
        
        super().__init__(config, message_bus)
    
    def _initialize_beliefs(self):
        """Initialize beliefs about scenario effectiveness"""
        # Belief about optimal allocation direction
        for driver in self.drivers:
            self.beliefs[f'{driver}_optimal_direction'] = BeliefState(
                name=f'{driver}_optimal_direction',
                mean=0.0,  # 0 = current is optimal, +/- = should increase/decrease
                variance=0.1,
                confidence=0.3,
                source='prior'
            )
        
        # Belief about scenario diversity value
        self.beliefs['diversity_value'] = BeliefState(
            name='diversity_value',
            mean=0.2,  # How much to value diverse scenarios
            variance=0.01,
            confidence=0.5,
            source='prior'
        )
    
    def _subscribe_to_messages(self):
        """Subscribe to relevant messages"""
        self.message_bus.subscribe(
            MessageType.ATTRIBUTION_UPDATE,
            self._handle_attribution_update
        )
        
        self.message_bus.subscribe(
            MessageType.OPTIMIZATION_RESULT,
            self._handle_optimization_result
        )
    
    def _handle_attribution_update(self, message: AgentMessage):
        """Update beliefs based on attribution"""
        payload = message.payload
        contributions = payload.get('driver_contributions', {})
        
        # Update optimal direction beliefs based on marginal contributions
        # (simplified: higher contribution = explore more)
        for driver, contribution in contributions.items():
            key = f'{driver}_optimal_direction'
            if key in self.beliefs:
                # Positive contribution suggests increase might help
                direction = 0.1 if contribution > 0 else -0.1
                self.update_belief(key, direction, 0.01)
    
    def _handle_optimization_result(self, message: AgentMessage):
        """Learn from optimization results"""
        payload = message.payload
        # Update beliefs about what scenarios work well
        pass
    
    def process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate and evaluate scenario batch.
        
        Args:
            inputs: Dict containing:
                - current_allocations: Current driver allocations
                - total_budget: Total budget constraint
                - scenario_types: Types of scenarios to generate
                - n_scenarios: Number of scenarios per type
                - constraints: Dict of constraints
        """
        current_allocations = inputs.get('current_allocations', {})
        total_budget = inputs.get('total_budget', sum(current_allocations.values()))
        scenario_types = inputs.get('scenario_types', [ScenarioType.FIXED_BUDGET])
        n_scenarios = inputs.get('n_scenarios', 10)
        constraints = inputs.get('constraints', {})
        
        # Generate scenarios
        scenarios = self._generate_scenarios(
            current_allocations, total_budget, scenario_types, n_scenarios, constraints
        )
        
        # Create batch
        batch = ScenarioBatch(
            batch_id=self._generate_id(),
            scenarios=scenarios,
            total_budget=total_budget,
            constraints=constraints
        )
        
        # Evaluate scenarios
        if self.simulation_fn:
            batch = self._evaluate_batch(batch)
        
        # Prune scenarios
        pruned_scenarios = self._prune_scenarios(scenarios)
        
        # Store
        self.generated_scenarios.extend(pruned_scenarios)
        self.evaluated_batches.append(batch)
        
        self.last_update = datetime.utcnow()
        self.update_count += 1
        
        return {
            'batch_id': batch.batch_id,
            'scenarios_generated': len(scenarios),
            'scenarios_after_pruning': len(pruned_scenarios),
            'scenarios': [s.to_dict() for s in pruned_scenarios[:20]],  # Top 20
            'best_scenario': batch.best_scenario_id,
            'pareto_frontier': batch.pareto_frontier
        }
    
    def _generate_scenarios(
        self,
        current: Dict[str, float],
        budget: float,
        types: List[ScenarioType],
        n_per_type: int,
        constraints: Dict[str, Any]
    ) -> List[ScenarioCandidate]:
        """Generate scenarios of specified types"""
        scenarios = []
        
        for scenario_type in types:
            if scenario_type == ScenarioType.FIXED_BUDGET:
                scenarios.extend(
                    self._generate_fixed_budget_scenarios(current, budget, n_per_type)
                )
            elif scenario_type == ScenarioType.INCREMENTAL:
                scenarios.extend(
                    self._generate_incremental_scenarios(current, budget, n_per_type)
                )
            elif scenario_type == ScenarioType.STRESS_TEST:
                scenarios.extend(
                    self._generate_stress_scenarios(current, budget)
                )
        
        # Check feasibility
        for scenario in scenarios:
            self._check_feasibility(scenario, constraints)
        
        return scenarios
    
    def _generate_fixed_budget_scenarios(
        self,
        current: Dict[str, float],
        budget: float,
        n: int
    ) -> List[ScenarioCandidate]:
        """Generate fixed-budget reallocation scenarios"""
        scenarios = []
        drivers = list(current.keys())
        
        if len(drivers) < 2:
            return scenarios
        
        # Grid-based reallocation
        for i in range(n):
            # Random reallocation
            weights = np.random.dirichlet(np.ones(len(drivers)))
            allocations = {d: budget * w for d, w in zip(drivers, weights)}
            
            delta = {d: allocations[d] - current.get(d, 0) for d in drivers}
            
            scenarios.append(ScenarioCandidate(
                scenario_id=f"fixed_{self._generate_id()}",
                scenario_type=ScenarioType.FIXED_BUDGET,
                name=f"Reallocation {i+1}",
                description=f"Fixed budget reallocation: {self._describe_delta(delta)}",
                driver_allocations=allocations,
                baseline_allocations=current.copy(),
                delta_allocations=delta,
                generation_method='dirichlet_sampling'
            ))
        
        # Also generate shift scenarios (move X% from one driver to another)
        for from_driver, to_driver in itertools.permutations(drivers, 2):
            for shift_pct in [0.1, 0.2, 0.3]:
                from_current = current.get(from_driver, 0)
                shift_amount = from_current * shift_pct
                
                allocations = current.copy()
                allocations[from_driver] = from_current - shift_amount
                allocations[to_driver] = current.get(to_driver, 0) + shift_amount
                
                delta = {d: allocations[d] - current.get(d, 0) for d in drivers}
                
                scenarios.append(ScenarioCandidate(
                    scenario_id=f"shift_{self._generate_id()}",
                    scenario_type=ScenarioType.FIXED_BUDGET,
                    name=f"Shift {shift_pct:.0%} {from_driver}→{to_driver}",
                    description=f"Shift {shift_pct:.0%} from {from_driver} to {to_driver}",
                    driver_allocations=allocations,
                    baseline_allocations=current.copy(),
                    delta_allocations=delta,
                    generation_method='pairwise_shift'
                ))
        
        return scenarios
    
    def _generate_incremental_scenarios(
        self,
        current: Dict[str, float],
        budget: float,
        n: int
    ) -> List[ScenarioCandidate]:
        """Generate incremental spend change scenarios"""
        scenarios = []
        drivers = list(current.keys())
        
        # Incremental changes: +/- 10%, 20%, 30%
        for driver in drivers:
            for change_pct in [-0.3, -0.2, -0.1, 0.1, 0.2, 0.3]:
                current_spend = current.get(driver, 0)
                change = current_spend * change_pct
                
                allocations = current.copy()
                allocations[driver] = current_spend + change
                
                delta = {d: 0 for d in drivers}
                delta[driver] = change
                
                new_total = sum(allocations.values())
                
                scenarios.append(ScenarioCandidate(
                    scenario_id=f"incr_{self._generate_id()}",
                    scenario_type=ScenarioType.INCREMENTAL,
                    name=f"{driver} {change_pct:+.0%}",
                    description=f"{'Increase' if change_pct > 0 else 'Decrease'} {driver} by {abs(change_pct):.0%}",
                    driver_allocations=allocations,
                    baseline_allocations=current.copy(),
                    delta_allocations=delta,
                    generation_method='incremental_grid'
                ))
        
        return scenarios
    
    def _generate_stress_scenarios(
        self,
        current: Dict[str, float],
        budget: float
    ) -> List[ScenarioCandidate]:
        """Generate stress test scenarios"""
        scenarios = []
        drivers = list(current.keys())
        
        # All-in scenarios
        for driver in drivers:
            allocations = {d: 0 for d in drivers}
            allocations[driver] = budget
            
            delta = {d: allocations[d] - current.get(d, 0) for d in drivers}
            
            scenarios.append(ScenarioCandidate(
                scenario_id=f"stress_{self._generate_id()}",
                scenario_type=ScenarioType.STRESS_TEST,
                name=f"All-in on {driver}",
                description=f"Allocate 100% of budget to {driver}",
                driver_allocations=allocations,
                baseline_allocations=current.copy(),
                delta_allocations=delta,
                generation_method='extreme'
            ))
        
        # Zero-out scenarios
        for driver in drivers:
            allocations = current.copy()
            removed = allocations[driver]
            allocations[driver] = 0
            
            # Redistribute to others
            others = [d for d in drivers if d != driver]
            if others:
                per_other = removed / len(others)
                for other in others:
                    allocations[other] += per_other
            
            delta = {d: allocations[d] - current.get(d, 0) for d in drivers}
            
            scenarios.append(ScenarioCandidate(
                scenario_id=f"stress_{self._generate_id()}",
                scenario_type=ScenarioType.STRESS_TEST,
                name=f"Zero {driver}",
                description=f"Remove {driver} entirely, redistribute to others",
                driver_allocations=allocations,
                baseline_allocations=current.copy(),
                delta_allocations=delta,
                generation_method='extreme'
            ))
        
        return scenarios
    
    def _describe_delta(self, delta: Dict[str, float]) -> str:
        """Create human-readable description of allocation changes"""
        parts = []
        for driver, change in delta.items():
            if abs(change) > 0.01:
                sign = "+" if change > 0 else ""
                parts.append(f"{driver} {sign}{change:.0f}")
        return ", ".join(parts) if parts else "no change"
    
    def _check_feasibility(
        self,
        scenario: ScenarioCandidate,
        constraints: Dict[str, Any]
    ):
        """Check if scenario meets constraints"""
        violations = []
        
        # Check minimum spend constraints
        min_spends = constraints.get('min_spend', {})
        for driver, min_val in min_spends.items():
            if scenario.driver_allocations.get(driver, 0) < min_val:
                violations.append(f"{driver} below minimum ({min_val})")
        
        # Check maximum spend constraints
        max_spends = constraints.get('max_spend', {})
        for driver, max_val in max_spends.items():
            if scenario.driver_allocations.get(driver, 0) > max_val:
                violations.append(f"{driver} above maximum ({max_val})")
        
        # Check total budget
        budget_limit = constraints.get('total_budget')
        if budget_limit:
            total = sum(scenario.driver_allocations.values())
            if total > budget_limit * 1.01:  # 1% tolerance
                violations.append(f"Total exceeds budget ({total:.0f} > {budget_limit:.0f})")
        
        scenario.is_feasible = len(violations) == 0
        scenario.feasibility_violations = violations
    
    def _evaluate_batch(self, batch: ScenarioBatch) -> ScenarioBatch:
        """Evaluate scenarios using simulation function"""
        if not self.simulation_fn:
            return batch
        
        best_value = float('-inf')
        best_id = None
        
        for scenario in batch.scenarios:
            if not scenario.is_feasible:
                continue
            
            try:
                result = self.simulation_fn(scenario.driver_allocations)
                scenario.expected_value = result.get('expected_value', 0)
                scenario.expected_uncertainty = result.get('uncertainty', 0)
                scenario.probability_of_improvement = result.get('prob_improvement', 0.5)
                scenario.confidence = result.get('confidence', 0.5)
                
                if scenario.expected_value > best_value:
                    best_value = scenario.expected_value
                    best_id = scenario.scenario_id
                    
            except Exception as e:
                logger.error(f"Error evaluating scenario {scenario.scenario_id}: {e}")
        
        batch.evaluated = True
        batch.best_scenario_id = best_id
        batch.pareto_frontier = self._find_pareto_frontier(batch.scenarios)
        
        return batch
    
    def _find_pareto_frontier(
        self,
        scenarios: List[ScenarioCandidate]
    ) -> List[str]:
        """Find Pareto-optimal scenarios (value vs uncertainty tradeoff)"""
        frontier = []
        
        for s in scenarios:
            if s.expected_value is None:
                continue
            
            is_dominated = False
            for other in scenarios:
                if other.expected_value is None or other.scenario_id == s.scenario_id:
                    continue
                
                # Check if 'other' dominates 's'
                # Better value AND lower uncertainty
                if (other.expected_value >= s.expected_value and 
                    (other.expected_uncertainty or 0) <= (s.expected_uncertainty or 0)):
                    if (other.expected_value > s.expected_value or 
                        (other.expected_uncertainty or 0) < (s.expected_uncertainty or 0)):
                        is_dominated = True
                        break
            
            if not is_dominated:
                frontier.append(s.scenario_id)
        
        return frontier
    
    def _prune_scenarios(
        self,
        scenarios: List[ScenarioCandidate],
        max_keep: int = 50
    ) -> List[ScenarioCandidate]:
        """Prune scenarios based on multiple criteria"""
        # Remove infeasible
        feasible = [s for s in scenarios if s.is_feasible]
        
        if not feasible:
            return scenarios[:max_keep]
        
        # Sort by expected value (if available) or confidence
        def score(s):
            if s.expected_value is not None:
                # Higher value, lower uncertainty, higher probability of improvement
                return (
                    s.expected_value - 
                    0.5 * (s.expected_uncertainty or 0) +
                    0.3 * (s.probability_of_improvement or 0.5) * 100
                )
            return s.confidence
        
        sorted_scenarios = sorted(feasible, key=score, reverse=True)
        
        # Keep top scenarios while maintaining diversity
        kept = []
        seen_types = set()
        
        for s in sorted_scenarios:
            if len(kept) >= max_keep:
                break
            
            # Ensure type diversity
            if s.scenario_type not in seen_types or len(kept) < max_keep // 2:
                kept.append(s)
                seen_types.add(s.scenario_type)
        
        return kept
    
    def _get_goal(self) -> str:
        return (
            "Automatically generate plausible marketing investment scenarios. "
            "Create fixed-budget reallocations, incremental changes, and stress tests. "
            "Evaluate and prune scenarios based on expected value, uncertainty, and feasibility."
        )
    
    def _get_backstory(self) -> str:
        return (
            "You are a creative scenario planner with deep marketing optimization expertise. "
            "You explore the space of possible investments systematically. "
            "Your scenarios expand decision coverage without requiring proportional analyst effort."
        )


def create_scenario_agent(
    retailer_id: str,
    drivers: Optional[List[str]] = None,
    simulation_fn: Optional[Callable] = None,
    message_bus: Optional[AgentMessageBus] = None
) -> ScenarioGenerationAgent:
    """Factory function for creating Scenario Generation Agent"""
    config = AgentConfig(
        agent_id=f"scenario_{retailer_id}",
        agent_type=AgentType.SCENARIO_GENERATION,
        retailer_id=retailer_id
    )
    
    return ScenarioGenerationAgent(config, message_bus, drivers, simulation_fn)
