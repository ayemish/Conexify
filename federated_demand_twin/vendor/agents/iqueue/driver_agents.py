"""
Driver Agents (Controllable vs Non-Controllable)

Controllable driver agents: Media, Price, Trade
- Maintain response curves, saturation/adstock, elasticity priors, constraints.

Non-controllable driver agents: Time series effects, Holidays/Events, Competition
- Maintain event libraries, competitor watch indices, stress tests.

Business value: separates what can be optimized from what must be managed.
"""

import numpy as np
from scipy import stats
from typing import Dict, List, Tuple, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum
from abc import abstractmethod
import logging

from .base import (
    BaseIQueueAgent, AgentConfig, AgentType, BeliefState,
    AgentMessage, MessageType, ConfidenceLevel, AgentMessageBus
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DriverCategory(str, Enum):
    """Categories of drivers"""
    CONTROLLABLE = "controllable"
    NON_CONTROLLABLE = "non_controllable"


class DriverType(str, Enum):
    """Specific driver types"""
    # Controllable
    MEDIA = "media"
    PRICE = "price"
    TRADE = "trade"
    # Non-controllable
    TIME_SERIES = "time_series"
    EVENTS = "events"
    COMPETITION = "competition"


@dataclass
class ResponseCurve:
    """Response curve for a driver"""
    driver_type: DriverType
    curve_type: str  # 'linear', 'diminishing', 's_curve', 'threshold'
    parameters: Dict[str, float]
    saturation_point: Optional[float] = None
    confidence: float = 0.7
    last_updated: datetime = field(default_factory=datetime.utcnow)
    
    def evaluate(self, x: float) -> float:
        """Evaluate response at input level x"""
        if self.curve_type == 'linear':
            return self.parameters.get('slope', 1.0) * x + self.parameters.get('intercept', 0.0)
        
        elif self.curve_type == 'diminishing':
            # y = a * (1 - exp(-b * x))
            a = self.parameters.get('max_response', 1.0)
            b = self.parameters.get('decay_rate', 0.1)
            return a * (1 - np.exp(-b * x))
        
        elif self.curve_type == 's_curve':
            # y = L / (1 + exp(-k * (x - x0)))
            L = self.parameters.get('L', 1.0)
            k = self.parameters.get('k', 0.1)
            x0 = self.parameters.get('x0', 50.0)
            return L / (1 + np.exp(-k * (x - x0)))
        
        elif self.curve_type == 'threshold':
            threshold = self.parameters.get('threshold', 0.0)
            slope = self.parameters.get('slope', 1.0)
            return slope * max(0, x - threshold)
        
        return x
    
    def get_marginal_response(self, x: float, delta: float = 0.01) -> float:
        """Get marginal response at point x"""
        return (self.evaluate(x + delta) - self.evaluate(x)) / delta


@dataclass
class AdstockModel:
    """Adstock/carryover model for media effects"""
    decay_rate: float  # Decay per period (0-1)
    peak_lag: int  # Periods until peak effect
    max_carryover_periods: int = 8
    
    def apply(self, spend_history: List[float]) -> float:
        """Apply adstock transformation"""
        if not spend_history:
            return 0.0
        
        effective_spend = 0.0
        for i, spend in enumerate(reversed(spend_history[-self.max_carryover_periods:])):
            lag = i
            # Decay with lag
            weight = (self.decay_rate ** lag) * self._lag_adjustment(lag)
            effective_spend += spend * weight
        
        return effective_spend
    
    def _lag_adjustment(self, lag: int) -> float:
        """Adjust weight based on peak lag"""
        if lag < self.peak_lag:
            return lag / self.peak_lag if self.peak_lag > 0 else 1.0
        return 1.0


@dataclass
class DriverConstraint:
    """Constraint on a driver"""
    constraint_type: str  # 'min', 'max', 'range', 'budget'
    value: float
    secondary_value: Optional[float] = None  # For range constraints
    is_hard: bool = True  # Hard vs soft constraint
    penalty: float = 0.0  # Penalty for violating soft constraint
    
    def is_satisfied(self, actual: float) -> bool:
        """Check if constraint is satisfied"""
        if self.constraint_type == 'min':
            return actual >= self.value
        elif self.constraint_type == 'max':
            return actual <= self.value
        elif self.constraint_type == 'range':
            return self.value <= actual <= (self.secondary_value or float('inf'))
        elif self.constraint_type == 'budget':
            return actual <= self.value
        return True


class DriverAgent(BaseIQueueAgent):
    """Base class for driver agents"""
    
    def __init__(
        self,
        config: AgentConfig,
        message_bus: Optional[AgentMessageBus] = None,
        driver_type: DriverType = DriverType.MEDIA,
        category: DriverCategory = DriverCategory.CONTROLLABLE
    ):
        self.driver_type = driver_type
        self.category = category
        self.response_curves: Dict[str, ResponseCurve] = {}
        self.constraints: Dict[str, DriverConstraint] = {}
        self.spend_history: List[Tuple[datetime, float]] = []
        
        super().__init__(config, message_bus)
    
    def _initialize_beliefs(self):
        """Initialize beliefs about driver effectiveness"""
        # Elasticity belief
        self.beliefs['elasticity'] = BeliefState(
            name=f'{self.driver_type.value}_elasticity',
            mean=self._get_default_elasticity(),
            variance=0.1,
            confidence=0.4,
            source='prior'
        )
        
        # ROI belief
        self.beliefs['roi'] = BeliefState(
            name=f'{self.driver_type.value}_roi',
            mean=1.5,  # Default ROI
            variance=0.5,
            confidence=0.3,
            source='prior'
        )
        
        # Current spend level
        self.beliefs['current_spend'] = BeliefState(
            name=f'{self.driver_type.value}_spend',
            mean=0.0,
            variance=1.0,
            confidence=0.9,
            source='observation'
        )
    
    @abstractmethod
    def _get_default_elasticity(self) -> float:
        """Get default elasticity for this driver type"""
        pass
    
    def _subscribe_to_messages(self):
        """Subscribe to relevant messages"""
        self.message_bus.subscribe(
            MessageType.ATTRIBUTION_UPDATE,
            self._handle_attribution_update
        )
    
    def _handle_attribution_update(self, message: AgentMessage):
        """Handle attribution updates that inform our effectiveness"""
        payload = message.payload
        
        # Update elasticity based on attribution
        if self.driver_type.value in str(payload.get('driver', '')):
            contribution = payload.get('contribution', 0)
            spend = payload.get('spend', 1)
            
            if spend > 0:
                implied_elasticity = contribution / spend
                self.update_belief('elasticity', implied_elasticity, 0.05)
    
    def process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process driver inputs and compute expected response.
        
        Args:
            inputs: Dict containing:
                - spend: Current/proposed spend level
                - target_outcome: Target outcome to optimize for
                - constraints: Any constraints to apply
        """
        spend = inputs.get('spend', 0.0)
        target = inputs.get('target_outcome')
        
        # Record spend
        self.spend_history.append((datetime.utcnow(), spend))
        self.update_belief('current_spend', spend, 1.0)
        
        # Compute response
        response = self._compute_response(spend)
        
        # Check constraints
        constraint_status = self._check_constraints(spend)
        
        # Compute marginal response
        marginal = self._compute_marginal_response(spend)
        
        self.last_update = datetime.utcnow()
        self.update_count += 1
        
        return {
            'driver': self.driver_type.value,
            'category': self.category.value,
            'spend': spend,
            'expected_response': response,
            'marginal_response': marginal,
            'elasticity': self.beliefs['elasticity'].mean,
            'roi': self.beliefs['roi'].mean,
            'constraints_satisfied': constraint_status,
            'confidence': self.beliefs['elasticity'].confidence
        }
    
    def _compute_response(self, spend: float) -> float:
        """Compute expected response for given spend"""
        # Use primary response curve if available
        if 'primary' in self.response_curves:
            return self.response_curves['primary'].evaluate(spend)
        
        # Fall back to elasticity-based response
        elasticity = self.beliefs['elasticity'].mean
        return spend * elasticity
    
    def _compute_marginal_response(self, spend: float) -> float:
        """Compute marginal response at current spend"""
        if 'primary' in self.response_curves:
            return self.response_curves['primary'].get_marginal_response(spend)
        
        # For linear, marginal = elasticity
        return self.beliefs['elasticity'].mean
    
    def _check_constraints(self, spend: float) -> Dict[str, bool]:
        """Check all constraints"""
        return {
            name: constraint.is_satisfied(spend)
            for name, constraint in self.constraints.items()
        }
    
    def set_response_curve(
        self,
        curve_type: str,
        parameters: Dict[str, float],
        saturation_point: Optional[float] = None,
        name: str = 'primary'
    ):
        """Set response curve for this driver"""
        self.response_curves[name] = ResponseCurve(
            driver_type=self.driver_type,
            curve_type=curve_type,
            parameters=parameters,
            saturation_point=saturation_point
        )
    
    def add_constraint(
        self,
        name: str,
        constraint_type: str,
        value: float,
        secondary_value: Optional[float] = None,
        is_hard: bool = True
    ):
        """Add constraint to this driver"""
        self.constraints[name] = DriverConstraint(
            constraint_type=constraint_type,
            value=value,
            secondary_value=secondary_value,
            is_hard=is_hard
        )
    
    def get_optimal_spend(
        self,
        budget: float,
        target_marginal: float = 0.0
    ) -> float:
        """Find optimal spend level given budget and target marginal response"""
        if 'primary' not in self.response_curves:
            return min(budget, budget * 0.5)  # Simple heuristic
        
        curve = self.response_curves['primary']
        
        # Binary search for spend where marginal = target
        low, high = 0.0, budget
        for _ in range(50):
            mid = (low + high) / 2
            marginal = curve.get_marginal_response(mid)
            
            if marginal > target_marginal:
                low = mid
            else:
                high = mid
        
        return mid
    
    def _get_goal(self) -> str:
        return (
            f"Manage {self.driver_type.value} driver effectiveness. "
            f"Maintain response curves, track elasticity and ROI, "
            f"and provide marginal response estimates for optimization."
        )
    
    def _get_backstory(self) -> str:
        return (
            f"You are an expert in {self.driver_type.value} marketing response modeling. "
            f"You understand diminishing returns, saturation effects, and budget constraints. "
            f"Your response curves inform optimal resource allocation decisions."
        )


class ControllableDriverAgent(DriverAgent):
    """Base for controllable drivers (Media, Price, Trade)"""
    
    def __init__(
        self,
        config: AgentConfig,
        message_bus: Optional[AgentMessageBus] = None,
        driver_type: DriverType = DriverType.MEDIA
    ):
        super().__init__(config, message_bus, driver_type, DriverCategory.CONTROLLABLE)


class NonControllableDriverAgent(DriverAgent):
    """Base for non-controllable drivers"""
    
    def __init__(
        self,
        config: AgentConfig,
        message_bus: Optional[AgentMessageBus] = None,
        driver_type: DriverType = DriverType.TIME_SERIES
    ):
        super().__init__(config, message_bus, driver_type, DriverCategory.NON_CONTROLLABLE)


class MediaDriverAgent(ControllableDriverAgent):
    """Agent for media/advertising driver"""
    
    def __init__(self, config: AgentConfig, message_bus: Optional[AgentMessageBus] = None):
        super().__init__(config, message_bus, DriverType.MEDIA)
        
        # Media-specific: adstock model
        self.adstock = AdstockModel(decay_rate=0.7, peak_lag=1)
        
        # Set default diminishing returns curve
        self.set_response_curve(
            curve_type='diminishing',
            parameters={'max_response': 1000.0, 'decay_rate': 0.001},
            saturation_point=5000.0
        )
    
    def _get_default_elasticity(self) -> float:
        return 0.15  # Media typically has lower elasticity
    
    def _initialize_beliefs(self):
        super()._initialize_beliefs()
        
        # Media-specific beliefs
        self.beliefs['adstock_decay'] = BeliefState(
            name='media_adstock_decay',
            mean=0.7,
            variance=0.02,
            confidence=0.5,
            source='prior'
        )
    
    def _compute_response(self, spend: float) -> float:
        """Compute response with adstock"""
        # Get effective spend with carryover
        spend_history = [s for _, s in self.spend_history[-8:]]
        spend_history.append(spend)
        effective_spend = self.adstock.apply(spend_history)
        
        # Apply response curve to effective spend
        return super()._compute_response(effective_spend)


class PriceDriverAgent(ControllableDriverAgent):
    """Agent for price driver"""
    
    def __init__(self, config: AgentConfig, message_bus: Optional[AgentMessageBus] = None):
        super().__init__(config, message_bus, DriverType.PRICE)
        
        # Set linear price response (negative elasticity)
        self.set_response_curve(
            curve_type='linear',
            parameters={'slope': -1.5, 'intercept': 100.0}
        )
    
    def _get_default_elasticity(self) -> float:
        return -1.5  # Price elasticity typically negative
    
    def _initialize_beliefs(self):
        super()._initialize_beliefs()
        
        # Price-specific beliefs
        self.beliefs['price_threshold'] = BeliefState(
            name='price_threshold',
            mean=10.0,
            variance=4.0,
            confidence=0.4,
            source='prior'
        )


class TradeDriverAgent(ControllableDriverAgent):
    """Agent for trade/promotion driver"""
    
    def __init__(self, config: AgentConfig, message_bus: Optional[AgentMessageBus] = None):
        super().__init__(config, message_bus, DriverType.TRADE)
        
        # Set S-curve for trade (threshold effect then saturation)
        self.set_response_curve(
            curve_type='s_curve',
            parameters={'L': 500.0, 'k': 0.05, 'x0': 50.0}
        )
    
    def _get_default_elasticity(self) -> float:
        return 0.8  # Trade typically has higher short-term elasticity


class TimeSeriesDriverAgent(NonControllableDriverAgent):
    """Agent for time series effects (trend, seasonality)"""
    
    def __init__(self, config: AgentConfig, message_bus: Optional[AgentMessageBus] = None):
        super().__init__(config, message_bus, DriverType.TIME_SERIES)
        
        # Seasonal patterns
        self.seasonal_indices: Dict[int, float] = {}  # month -> index
        self.trend: float = 0.0
    
    def _get_default_elasticity(self) -> float:
        return 1.0  # Time effects are multiplicative
    
    def _initialize_beliefs(self):
        super()._initialize_beliefs()
        
        # Time-specific beliefs
        self.beliefs['trend'] = BeliefState(
            name='time_trend',
            mean=0.02,  # 2% annual growth
            variance=0.001,
            confidence=0.6,
            source='prior'
        )
        
        self.beliefs['seasonality_amplitude'] = BeliefState(
            name='seasonality_amplitude',
            mean=0.15,  # 15% seasonal swing
            variance=0.01,
            confidence=0.5,
            source='prior'
        )
    
    def get_time_effect(self, period: date) -> float:
        """Get combined time effect for a period"""
        month = period.month
        seasonal = self.seasonal_indices.get(month, 1.0)
        
        # Apply trend
        trend_effect = 1.0 + self.beliefs['trend'].mean
        
        return seasonal * trend_effect


class EventsDriverAgent(NonControllableDriverAgent):
    """Agent for holidays and events"""
    
    def __init__(self, config: AgentConfig, message_bus: Optional[AgentMessageBus] = None):
        super().__init__(config, message_bus, DriverType.EVENTS)
        
        # Event library
        self.event_library: Dict[str, Dict[str, Any]] = {}
        self._initialize_event_library()
    
    def _get_default_elasticity(self) -> float:
        return 1.0
    
    def _initialize_event_library(self):
        """Initialize common events"""
        self.event_library = {
            'thanksgiving': {'month': 11, 'effect': 1.3, 'duration': 1},
            'christmas': {'month': 12, 'effect': 1.5, 'duration': 2},
            'super_bowl': {'month': 2, 'effect': 1.15, 'duration': 1},
            'memorial_day': {'month': 5, 'effect': 1.1, 'duration': 1},
            'labor_day': {'month': 9, 'effect': 1.1, 'duration': 1},
            'back_to_school': {'month': 8, 'effect': 1.2, 'duration': 3}
        }
    
    def get_event_effect(self, period: date) -> Tuple[float, List[str]]:
        """Get event effects for a period"""
        effects = 1.0
        active_events = []
        
        for event_name, event_info in self.event_library.items():
            if period.month == event_info['month']:
                effects *= event_info['effect']
                active_events.append(event_name)
        
        return effects, active_events


class CompetitionDriverAgent(NonControllableDriverAgent):
    """Agent for competitive effects"""
    
    def __init__(self, config: AgentConfig, message_bus: Optional[AgentMessageBus] = None):
        super().__init__(config, message_bus, DriverType.COMPETITION)
        
        # Competitor watch
        self.competitor_indices: Dict[str, float] = {}
    
    def _get_default_elasticity(self) -> float:
        return -0.3  # Competition typically has negative cross-elasticity
    
    def _initialize_beliefs(self):
        super()._initialize_beliefs()
        
        # Competition-specific beliefs
        self.beliefs['competitive_intensity'] = BeliefState(
            name='competitive_intensity',
            mean=0.5,  # Medium competition
            variance=0.04,
            confidence=0.4,
            source='prior'
        )
    
    def update_competitor_index(self, competitor: str, index: float):
        """Update competitor activity index"""
        self.competitor_indices[competitor] = index
        
        # Update competitive intensity belief
        avg_intensity = np.mean(list(self.competitor_indices.values())) if self.competitor_indices else 0.5
        self.update_belief('competitive_intensity', avg_intensity, 0.01)


def create_driver_agent_ensemble(
    retailer_id: str,
    message_bus: Optional[AgentMessageBus] = None
) -> Dict[str, DriverAgent]:
    """Create ensemble of all driver agents"""
    bus = message_bus or AgentMessageBus()
    
    agents = {}
    
    # Controllable drivers
    for driver_type, agent_class in [
        (DriverType.MEDIA, MediaDriverAgent),
        (DriverType.PRICE, PriceDriverAgent),
        (DriverType.TRADE, TradeDriverAgent)
    ]:
        config = AgentConfig(
            agent_id=f"{driver_type.value}_driver_{retailer_id}",
            agent_type=AgentType.DRIVER_CONTROLLABLE,
            retailer_id=retailer_id
        )
        agents[driver_type.value] = agent_class(config, bus)
    
    # Non-controllable drivers
    for driver_type, agent_class in [
        (DriverType.TIME_SERIES, TimeSeriesDriverAgent),
        (DriverType.EVENTS, EventsDriverAgent),
        (DriverType.COMPETITION, CompetitionDriverAgent)
    ]:
        config = AgentConfig(
            agent_id=f"{driver_type.value}_driver_{retailer_id}",
            agent_type=AgentType.DRIVER_NON_CONTROLLABLE,
            retailer_id=retailer_id
        )
        agents[driver_type.value] = agent_class(config, bus)
    
    return agents
