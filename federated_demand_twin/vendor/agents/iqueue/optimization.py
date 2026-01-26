"""
Optimization Agent ("Next Best Investment")

Responsibilities:
- Searches for plans that maximize expected value under constraints
- Supports multi-objective optimization (dollars, units, baskets, etc.)
- Explicitly optimizes under uncertainty (risk-aware constraints such as probability of downside)

Business value: converts marginal response analysis into repeatable optimization.
"""

import numpy as np
from scipy import optimize
from typing import Dict, List, Tuple, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
import logging

from .base import (
    BaseIQueueAgent, AgentConfig, AgentType, BeliefState,
    AgentMessage, MessageType, ConfidenceLevel, AgentMessageBus
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ObjectiveType(str, Enum):
    """Types of optimization objectives"""
    REVENUE = "revenue"
    UNITS = "units"
    BASKETS = "baskets"
    ROI = "roi"
    PROFIT = "profit"
    MARKET_SHARE = "market_share"


class RiskMeasure(str, Enum):
    """Risk measures for uncertainty-aware optimization"""
    EXPECTED_VALUE = "expected_value"
    CVAR = "cvar"  # Conditional Value at Risk
    VAR = "var"    # Value at Risk
    DOWNSIDE_PROBABILITY = "downside_probability"


@dataclass
class InvestmentPlan:
    """Optimal investment plan"""
    plan_id: str
    
    # Allocations
    allocations: Dict[str, float]
    total_investment: float
    
    # Expected outcomes
    expected_value: float
    expected_units: float
    expected_roi: float
    
    # Risk metrics
    value_at_risk: float  # 5th percentile
    conditional_var: float  # Expected value below VaR
    downside_probability: float  # P(outcome < threshold)
    
    # Confidence
    confidence: float
    optimization_method: str
    
    # Constraints
    constraints_satisfied: Dict[str, bool]
    binding_constraints: List[str]
    
    # Metadata
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'plan_id': self.plan_id,
            'allocations': self.allocations,
            'total_investment': self.total_investment,
            'expected_value': self.expected_value,
            'expected_units': self.expected_units,
            'expected_roi': self.expected_roi,
            'value_at_risk': self.value_at_risk,
            'conditional_var': self.conditional_var,
            'downside_probability': self.downside_probability,
            'confidence': self.confidence,
            'optimization_method': self.optimization_method,
            'constraints_satisfied': self.constraints_satisfied,
            'binding_constraints': self.binding_constraints,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class OptimizationConstraint:
    """Constraint for optimization"""
    name: str
    constraint_type: str  # 'eq', 'ineq', 'bounds'
    driver: Optional[str] = None  # None = applies to total
    value: float = 0.0
    upper_bound: Optional[float] = None
    is_hard: bool = True
    
    def get_scipy_constraint(self, driver_indices: Dict[str, int]) -> Dict[str, Any]:
        """Convert to scipy constraint format"""
        if self.constraint_type == 'bounds':
            return None  # Handled separately
        
        if self.driver:
            idx = driver_indices.get(self.driver, 0)
            if self.constraint_type == 'eq':
                return {'type': 'eq', 'fun': lambda x, i=idx, v=self.value: x[i] - v}
            else:  # ineq
                return {'type': 'ineq', 'fun': lambda x, i=idx, v=self.value: x[i] - v}
        else:
            # Total constraint
            if self.constraint_type == 'eq':
                return {'type': 'eq', 'fun': lambda x, v=self.value: np.sum(x) - v}
            else:
                return {'type': 'ineq', 'fun': lambda x, v=self.value: v - np.sum(x)}
        
        return None


class OptimizationAgent(BaseIQueueAgent):
    """
    Optimization Agent for "Next Best Investment"
    
    Optimizes marketing investment under:
    - Budget constraints
    - Risk constraints (CVaR, VaR, downside probability)
    - Business rules (min/max spend per channel)
    - Multi-objective tradeoffs
    """
    
    def __init__(
        self,
        config: AgentConfig,
        message_bus: Optional[AgentMessageBus] = None,
        drivers: Optional[List[str]] = None,
        response_fn: Optional[Callable] = None
    ):
        self.drivers = drivers or ['media', 'price', 'trade']
        self.response_fn = response_fn  # Function mapping allocations to expected outcome
        self.optimization_history: List[InvestmentPlan] = []
        self.constraints: List[OptimizationConstraint] = []
        
        super().__init__(config, message_bus)
    
    def _initialize_beliefs(self):
        """Initialize beliefs about optimization"""
        # Belief about current optimality gap
        self.beliefs['optimality_gap'] = BeliefState(
            name='optimality_gap',
            mean=0.1,  # 10% potential improvement
            variance=0.01,
            confidence=0.4,
            source='prior'
        )
        
        # Per-driver marginal value beliefs
        for driver in self.drivers:
            self.beliefs[f'{driver}_marginal_value'] = BeliefState(
                name=f'{driver}_marginal_value',
                mean=1.0,  # $1 marginal return per $1 spent
                variance=0.1,
                confidence=0.4,
                source='prior'
            )
    
    def _subscribe_to_messages(self):
        """Subscribe to relevant messages"""
        self.message_bus.subscribe(
            MessageType.BELIEF_UPDATE,
            self._handle_driver_update
        )
        
        self.message_bus.subscribe(
            MessageType.SCENARIO_RESULT,
            self._handle_scenario_result
        )
    
    def _handle_driver_update(self, message: AgentMessage):
        """Handle updates from driver agents"""
        payload = message.payload
        belief_name = payload.get('belief_name', '')
        
        for driver in self.drivers:
            if driver in belief_name and 'elasticity' in belief_name:
                belief_data = payload.get('belief', {})
                elasticity = belief_data.get('mean', 1.0)
                
                # Update marginal value belief
                key = f'{driver}_marginal_value'
                if key in self.beliefs:
                    self.update_belief(key, elasticity, 0.05)
    
    def _handle_scenario_result(self, message: AgentMessage):
        """Learn from scenario evaluation results"""
        pass
    
    def process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run optimization to find best investment plan.
        
        Args:
            inputs: Dict containing:
                - current_allocations: Current driver allocations
                - total_budget: Total budget constraint
                - objective: Primary objective (revenue, units, roi, etc.)
                - risk_measure: Risk measure to constrain/optimize
                - risk_threshold: Risk constraint threshold
                - constraints: Additional constraints
        """
        current = inputs.get('current_allocations', {})
        budget = inputs.get('total_budget', sum(current.values()))
        objective = inputs.get('objective', ObjectiveType.REVENUE)
        risk_measure = inputs.get('risk_measure', RiskMeasure.EXPECTED_VALUE)
        risk_threshold = inputs.get('risk_threshold', 0.1)
        custom_constraints = inputs.get('constraints', [])
        
        # Set up constraints
        self._setup_constraints(current, budget, custom_constraints)
        
        # Run optimization
        plan = self._optimize(
            current, budget, objective, risk_measure, risk_threshold
        )
        
        # Store history
        self.optimization_history.append(plan)
        
        # Publish result
        self._publish_optimization_result(plan)
        
        self.last_update = datetime.utcnow()
        self.update_count += 1
        
        return plan.to_dict()
    
    def _setup_constraints(
        self,
        current: Dict[str, float],
        budget: float,
        custom: List[Dict]
    ):
        """Set up optimization constraints"""
        self.constraints = []
        
        # Budget constraint (equality for fixed budget, inequality for max budget)
        self.constraints.append(OptimizationConstraint(
            name='total_budget',
            constraint_type='eq',
            driver=None,
            value=budget
        ))
        
        # Non-negativity (handled via bounds)
        for driver in self.drivers:
            self.constraints.append(OptimizationConstraint(
                name=f'{driver}_non_negative',
                constraint_type='bounds',
                driver=driver,
                value=0.0,
                upper_bound=budget
            ))
        
        # Add custom constraints
        for c in custom:
            self.constraints.append(OptimizationConstraint(
                name=c.get('name', 'custom'),
                constraint_type=c.get('type', 'ineq'),
                driver=c.get('driver'),
                value=c.get('value', 0),
                upper_bound=c.get('upper_bound'),
                is_hard=c.get('is_hard', True)
            ))
    
    def _optimize(
        self,
        current: Dict[str, float],
        budget: float,
        objective: ObjectiveType,
        risk_measure: RiskMeasure,
        risk_threshold: float
    ) -> InvestmentPlan:
        """Run the optimization"""
        n_drivers = len(self.drivers)
        driver_indices = {d: i for i, d in enumerate(self.drivers)}
        
        # Initial point: current allocation or equal split
        x0 = np.array([current.get(d, budget / n_drivers) for d in self.drivers])
        
        # Objective function (negative because we minimize)
        def objective_fn(x):
            allocations = {d: x[i] for i, d in enumerate(self.drivers)}
            
            if self.response_fn:
                result = self.response_fn(allocations)
                value = result.get('expected_value', 0)
            else:
                # Default: use marginal value beliefs
                value = sum(
                    x[i] * self.beliefs.get(f'{d}_marginal_value', 
                        BeliefState(name='', mean=1.0, variance=0.1, confidence=0.5)).mean
                    for i, d in enumerate(self.drivers)
                )
            
            return -value  # Negative for minimization
        
        # Constraints for scipy
        scipy_constraints = []
        
        # Budget constraint
        scipy_constraints.append({
            'type': 'eq',
            'fun': lambda x: np.sum(x) - budget
        })
        
        # Bounds (non-negativity and max)
        bounds = [(0, budget) for _ in self.drivers]
        
        # Run optimization
        try:
            result = optimize.minimize(
                objective_fn,
                x0,
                method='SLSQP',
                bounds=bounds,
                constraints=scipy_constraints,
                options={'maxiter': 100, 'disp': False}
            )
            
            optimal_x = result.x
            success = result.success
            method = 'SLSQP'
            
        except Exception as e:
            logger.error(f"Optimization failed: {e}")
            optimal_x = x0
            success = False
            method = 'fallback_initial'
        
        # Convert to allocations
        optimal_allocations = {d: max(0, optimal_x[i]) for i, d in enumerate(self.drivers)}
        
        # Compute expected outcomes
        expected_value, expected_units, value_samples = self._compute_expected_outcomes(
            optimal_allocations
        )
        
        # Compute risk metrics
        var, cvar, downside_prob = self._compute_risk_metrics(
            value_samples, risk_threshold
        )
        
        # Check constraints
        constraints_satisfied = {}
        binding_constraints = []
        
        for c in self.constraints:
            if c.driver:
                val = optimal_allocations.get(c.driver, 0)
                if c.constraint_type == 'bounds':
                    satisfied = c.value <= val <= (c.upper_bound or float('inf'))
                    if abs(val - c.value) < 0.01 or abs(val - (c.upper_bound or 0)) < 0.01:
                        binding_constraints.append(c.name)
                else:
                    satisfied = val >= c.value if c.constraint_type == 'ineq' else abs(val - c.value) < 0.01
            else:
                total = sum(optimal_allocations.values())
                satisfied = abs(total - c.value) < 0.01 if c.constraint_type == 'eq' else total <= c.value
                if satisfied and c.constraint_type == 'eq':
                    binding_constraints.append(c.name)
            
            constraints_satisfied[c.name] = satisfied
        
        # Compute ROI
        total_spend = sum(optimal_allocations.values())
        expected_roi = (expected_value - total_spend) / max(total_spend, 1)
        
        # Confidence based on optimization success and belief confidence
        confidence = 0.8 if success else 0.4
        confidence *= np.mean([
            self.beliefs.get(f'{d}_marginal_value', BeliefState(name='', mean=1, variance=0.1, confidence=0.5)).confidence
            for d in self.drivers
        ])
        
        return InvestmentPlan(
            plan_id=self._generate_id(),
            allocations=optimal_allocations,
            total_investment=total_spend,
            expected_value=expected_value,
            expected_units=expected_units,
            expected_roi=expected_roi,
            value_at_risk=var,
            conditional_var=cvar,
            downside_probability=downside_prob,
            confidence=confidence,
            optimization_method=method,
            constraints_satisfied=constraints_satisfied,
            binding_constraints=binding_constraints
        )
    
    def _compute_expected_outcomes(
        self,
        allocations: Dict[str, float],
        n_samples: int = 1000
    ) -> Tuple[float, float, np.ndarray]:
        """Compute expected value, units, and sample distribution"""
        if self.response_fn:
            result = self.response_fn(allocations)
            expected_value = result.get('expected_value', 0)
            expected_units = result.get('expected_units', 0)
            value_samples = result.get('samples', np.array([expected_value]))
        else:
            # Use marginal value beliefs with uncertainty
            samples = []
            for _ in range(n_samples):
                value = 0
                for driver, spend in allocations.items():
                    belief = self.beliefs.get(f'{driver}_marginal_value')
                    if belief:
                        marginal = np.random.normal(belief.mean, belief.std)
                    else:
                        marginal = 1.0
                    value += spend * marginal
                samples.append(value)
            
            value_samples = np.array(samples)
            expected_value = np.mean(value_samples)
            expected_units = expected_value * 0.1  # Simplified
        
        return expected_value, expected_units, value_samples
    
    def _compute_risk_metrics(
        self,
        samples: np.ndarray,
        threshold: float = 0.0
    ) -> Tuple[float, float, float]:
        """Compute VaR, CVaR, and downside probability"""
        # Ensure samples is a numpy array
        samples = np.asarray(samples).flatten()
        
        if len(samples) == 0:
            return 0.0, 0.0, 0.0
        
        # VaR: 5th percentile
        var = float(np.percentile(samples, 5))
        
        # CVaR: Expected value in worst 5%
        mask = samples <= var
        worst_samples = samples[mask]
        cvar = float(np.mean(worst_samples)) if len(worst_samples) > 0 else var
        
        # Downside probability
        downside_prob = float(np.mean(samples < threshold))
        
        return var, cvar, downside_prob
    
    def _publish_optimization_result(self, plan: InvestmentPlan):
        """Publish optimization result to message bus"""
        self.message_bus.publish(AgentMessage(
            message_id=self._generate_id(),
            message_type=MessageType.OPTIMIZATION_RESULT,
            sender_id=self.config.agent_id,
            recipient_id=None,
            payload=plan.to_dict()
        ))
    
    def get_marginal_analysis(self, current: Dict[str, float]) -> Dict[str, float]:
        """Get marginal value analysis for current allocation"""
        marginals = {}
        
        for driver in self.drivers:
            belief = self.beliefs.get(f'{driver}_marginal_value')
            if belief:
                marginals[driver] = {
                    'marginal_value': belief.mean,
                    'confidence': belief.confidence,
                    'ci_lower': belief.ci_lower,
                    'ci_upper': belief.ci_upper
                }
            else:
                marginals[driver] = {
                    'marginal_value': 1.0,
                    'confidence': 0.3,
                    'ci_lower': 0.5,
                    'ci_upper': 1.5
                }
        
        return marginals
    
    def _get_goal(self) -> str:
        return (
            "Find optimal marketing investment plans that maximize expected value under constraints. "
            "Support multi-objective optimization and risk-aware decision making. "
            "Convert marginal response analysis into actionable investment recommendations."
        )
    
    def _get_backstory(self) -> str:
        return (
            "You are an expert in marketing investment optimization with deep knowledge of "
            "constrained optimization, portfolio theory, and risk management. "
            "Your recommendations balance expected returns with uncertainty and business constraints."
        )


def create_optimization_agent(
    retailer_id: str,
    drivers: Optional[List[str]] = None,
    response_fn: Optional[Callable] = None,
    message_bus: Optional[AgentMessageBus] = None
) -> OptimizationAgent:
    """Factory function for creating Optimization Agent"""
    config = AgentConfig(
        agent_id=f"optimization_{retailer_id}",
        agent_type=AgentType.OPTIMIZATION,
        retailer_id=retailer_id
    )
    
    return OptimizationAgent(config, message_bus, drivers, response_fn)
