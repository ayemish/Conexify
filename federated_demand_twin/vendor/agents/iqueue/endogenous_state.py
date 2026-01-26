"""
Endogenous-State Agents

Agents own local beliefs for:
- Total shopper baskets
- Basket penetration
- Items per basket
- Size per item

Responsibilities:
- Update local posterior state estimates
- Track lagged relationships and cross-effects
- Produce localized diagnostic alerts (e.g., unexpected penetration shift)

Business value: modularizes the coupled system while preserving interpretability.
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any
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


class StateMetric(str, Enum):
    """Key endogenous state metrics"""
    TOTAL_BASKETS = "total_baskets"
    BASKET_PENETRATION = "basket_penetration"
    ITEMS_PER_BASKET = "items_per_basket"
    SIZE_PER_ITEM = "size_per_item"
    REVENUE_PER_BASKET = "revenue_per_basket"
    UNITS_PER_BASKET = "units_per_basket"


@dataclass
class CrossEffect:
    """Represents a cross-effect between metrics"""
    source_metric: str
    target_metric: str
    lag_periods: int
    coefficient: float
    confidence: float
    last_updated: datetime = field(default_factory=datetime.utcnow)


@dataclass
class StateUpdate:
    """Update to an endogenous state"""
    metric: StateMetric
    observation: float
    observation_variance: float
    timestamp: datetime
    source: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class EndogenousStateAgent(BaseIQueueAgent):
    """
    Base class for endogenous state agents.
    
    These agents maintain beliefs about key business outcomes
    and track relationships between them.
    """
    
    def __init__(
        self,
        config: AgentConfig,
        message_bus: Optional[AgentMessageBus] = None,
        metric: StateMetric = StateMetric.TOTAL_BASKETS
    ):
        self.metric = metric
        self.cross_effects: Dict[str, CrossEffect] = {}
        self.update_history: List[StateUpdate] = []
        self.max_history = 500
        
        super().__init__(config, message_bus)
    
    def _initialize_beliefs(self):
        """Initialize beliefs about this state metric"""
        # Primary belief about the metric value
        self.beliefs['current_value'] = BeliefState(
            name=f'{self.metric.value}_current',
            mean=self._get_initial_mean(),
            variance=self._get_initial_variance(),
            confidence=0.3,
            source='prior'
        )
        
        # Trend belief
        self.beliefs['trend'] = BeliefState(
            name=f'{self.metric.value}_trend',
            mean=0.0,  # No trend initially
            variance=0.01,
            confidence=0.3,
            source='prior'
        )
        
        # Seasonality amplitude
        self.beliefs['seasonality'] = BeliefState(
            name=f'{self.metric.value}_seasonality',
            mean=0.0,
            variance=0.1,
            confidence=0.3,
            source='prior'
        )
    
    @abstractmethod
    def _get_initial_mean(self) -> float:
        """Get initial mean for this metric"""
        pass
    
    @abstractmethod
    def _get_initial_variance(self) -> float:
        """Get initial variance for this metric"""
        pass
    
    def _subscribe_to_messages(self):
        """Subscribe to relevant messages"""
        # Subscribe to belief updates from other state agents
        self.message_bus.subscribe(
            MessageType.BELIEF_UPDATE,
            self._handle_belief_update
        )
        
        # Subscribe to data quality reports
        self.message_bus.subscribe(
            MessageType.DATA_QUALITY,
            self._handle_data_quality
        )
    
    def _handle_belief_update(self, message: AgentMessage):
        """Handle belief updates from other agents"""
        if message.sender_id == self.config.agent_id:
            return  # Ignore own messages
        
        payload = message.payload
        belief_name = payload.get('belief_name', '')
        belief_data = payload.get('belief', {})
        
        # Check if this affects our cross-effects
        source_metric = belief_name.split('_')[0] if '_' in belief_name else belief_name
        effect_key = f"{source_metric}_to_{self.metric.value}"
        
        if effect_key in self.cross_effects:
            self._apply_cross_effect(
                self.cross_effects[effect_key],
                belief_data.get('mean', 0)
            )
    
    def _handle_data_quality(self, message: AgentMessage):
        """Handle data quality updates"""
        payload = message.payload
        confidence = payload.get('overall_confidence', 1.0)
        
        # Adjust our confidence based on data quality
        if confidence < 0.5:
            self._raise_alert(
                f"Low data quality ({confidence:.2f}) may affect {self.metric.value} estimates",
                severity="warning"
            )
    
    def _apply_cross_effect(self, effect: CrossEffect, source_value: float):
        """Apply cross-effect from another metric"""
        if effect.lag_periods > 0:
            # Store for lagged application
            # In production, this would use a proper time-series store
            pass
        else:
            # Immediate effect
            adjustment = effect.coefficient * source_value * effect.confidence
            current = self.beliefs['current_value']
            
            # Small adjustment to mean
            new_mean = current.mean * (1 + adjustment * 0.01)
            self.beliefs['current_value'] = BeliefState(
                name=current.name,
                mean=new_mean,
                variance=current.variance,
                confidence=current.confidence * effect.confidence,
                source='cross_effect',
                history=current.history,
                update_count=current.update_count
            )
    
    def process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process new observations and update state estimates.
        
        Args:
            inputs: Dict containing:
                - observation: New observed value
                - observation_variance: Variance of observation
                - source: Source of the observation
                - metadata: Additional context
        
        Returns:
            Updated state information
        """
        observation = inputs.get('observation')
        observation_variance = inputs.get('observation_variance', 
                                          self._get_initial_variance() * 0.1)
        source = inputs.get('source', 'external')
        metadata = inputs.get('metadata', {})
        
        if observation is None:
            return self.get_state()
        
        # Create state update record
        update = StateUpdate(
            metric=self.metric,
            observation=observation,
            observation_variance=observation_variance,
            timestamp=datetime.utcnow(),
            source=source,
            metadata=metadata
        )
        self.update_history.append(update)
        if len(self.update_history) > self.max_history:
            self.update_history = self.update_history[-self.max_history:]
        
        # Update primary belief
        old_value = self.beliefs['current_value'].mean
        self.update_belief('current_value', observation, observation_variance)
        new_value = self.beliefs['current_value'].mean
        
        # Update trend estimate
        if len(self.update_history) >= 2:
            recent_changes = []
            for i in range(1, min(10, len(self.update_history))):
                change = (self.update_history[-i].observation - 
                         self.update_history[-i-1].observation if i < len(self.update_history) else 0)
                recent_changes.append(change)
            
            if recent_changes:
                trend_estimate = np.mean(recent_changes)
                self.update_belief('trend', trend_estimate, np.var(recent_changes) + 0.001)
        
        # Check for alerts
        self._check_for_alerts(old_value, new_value)
        
        self.last_update = datetime.utcnow()
        self.update_count += 1
        
        return {
            'metric': self.metric.value,
            'current_value': self.beliefs['current_value'].to_dict(),
            'trend': self.beliefs['trend'].to_dict(),
            'confidence': self.beliefs['current_value'].confidence
        }
    
    def _check_for_alerts(self, old_value: float, new_value: float):
        """Check for significant changes that warrant alerts"""
        if old_value == 0:
            return
        
        pct_change = abs(new_value - old_value) / abs(old_value)
        
        if pct_change > 0.2:  # 20% change
            self._raise_alert(
                f"Significant {self.metric.value} shift: {old_value:.2f} → {new_value:.2f} "
                f"({pct_change:.1%} change)",
                severity="warning" if pct_change < 0.5 else "critical"
            )
        
        # Check for drift
        drift = self.beliefs['current_value'].detect_drift()
        if drift:
            self._raise_alert(
                f"{self.metric.value} drift detected: {drift}",
                severity="warning"
            )
    
    def register_cross_effect(
        self,
        source_metric: str,
        lag_periods: int,
        coefficient: float,
        confidence: float = 0.8
    ):
        """Register a cross-effect from another metric"""
        effect = CrossEffect(
            source_metric=source_metric,
            target_metric=self.metric.value,
            lag_periods=lag_periods,
            coefficient=coefficient,
            confidence=confidence
        )
        
        effect_key = f"{source_metric}_to_{self.metric.value}"
        self.cross_effects[effect_key] = effect
        
        logger.info(f"Registered cross-effect: {effect_key} with coef={coefficient}")
    
    def get_forecast(self, periods: int = 4) -> Dict[str, Any]:
        """Generate forecast based on current state and trend"""
        current = self.beliefs['current_value'].mean
        trend = self.beliefs['trend'].mean
        
        forecasts = []
        for t in range(1, periods + 1):
            forecast_value = current + trend * t
            forecast_variance = (
                self.beliefs['current_value'].variance + 
                self.beliefs['trend'].variance * t**2
            )
            forecasts.append({
                'period': t,
                'forecast': forecast_value,
                'lower': forecast_value - 1.96 * np.sqrt(forecast_variance),
                'upper': forecast_value + 1.96 * np.sqrt(forecast_variance)
            })
        
        return {
            'metric': self.metric.value,
            'current': current,
            'trend': trend,
            'forecasts': forecasts
        }
    
    def _get_goal(self) -> str:
        return (
            f"Maintain accurate beliefs about {self.metric.value.replace('_', ' ')}. "
            f"Update posterior estimates with new observations, track trends and cross-effects, "
            f"and alert when unexpected shifts occur."
        )
    
    def _get_backstory(self) -> str:
        return (
            f"You are an expert in tracking {self.metric.value.replace('_', ' ')} for retail analytics. "
            f"You understand the business drivers and can detect anomalies. "
            f"Your beliefs inform downstream scenario and optimization decisions."
        )


class BasketAgent(EndogenousStateAgent):
    """Agent tracking total shopper baskets"""
    
    def __init__(self, config: AgentConfig, message_bus: Optional[AgentMessageBus] = None):
        super().__init__(config, message_bus, StateMetric.TOTAL_BASKETS)
    
    def _get_initial_mean(self) -> float:
        return 10000.0  # Default expected baskets
    
    def _get_initial_variance(self) -> float:
        return 1000000.0  # High initial uncertainty


class PenetrationAgent(EndogenousStateAgent):
    """Agent tracking basket penetration (% of baskets containing category)"""
    
    def __init__(self, config: AgentConfig, message_bus: Optional[AgentMessageBus] = None):
        super().__init__(config, message_bus, StateMetric.BASKET_PENETRATION)
    
    def _get_initial_mean(self) -> float:
        return 0.15  # 15% default penetration
    
    def _get_initial_variance(self) -> float:
        return 0.01  # Penetration variance


class ItemsPerBasketAgent(EndogenousStateAgent):
    """Agent tracking items per basket"""
    
    def __init__(self, config: AgentConfig, message_bus: Optional[AgentMessageBus] = None):
        super().__init__(config, message_bus, StateMetric.ITEMS_PER_BASKET)
    
    def _get_initial_mean(self) -> float:
        return 1.5  # Average items per basket in category
    
    def _get_initial_variance(self) -> float:
        return 0.25


class SizePerItemAgent(EndogenousStateAgent):
    """Agent tracking size/value per item"""
    
    def __init__(self, config: AgentConfig, message_bus: Optional[AgentMessageBus] = None):
        super().__init__(config, message_bus, StateMetric.SIZE_PER_ITEM)
    
    def _get_initial_mean(self) -> float:
        return 5.0  # Average $ per item
    
    def _get_initial_variance(self) -> float:
        return 4.0


def create_state_agent_ensemble(
    retailer_id: str,
    segment_id: Optional[str] = None,
    message_bus: Optional[AgentMessageBus] = None
) -> Dict[str, EndogenousStateAgent]:
    """Create ensemble of endogenous state agents"""
    bus = message_bus or AgentMessageBus()
    
    agents = {}
    
    # Create each state agent
    for metric, agent_class in [
        (StateMetric.TOTAL_BASKETS, BasketAgent),
        (StateMetric.BASKET_PENETRATION, PenetrationAgent),
        (StateMetric.ITEMS_PER_BASKET, ItemsPerBasketAgent),
        (StateMetric.SIZE_PER_ITEM, SizePerItemAgent)
    ]:
        config = AgentConfig(
            agent_id=f"{metric.value}_{retailer_id}_{segment_id or 'all'}",
            agent_type=AgentType.ENDOGENOUS_STATE,
            retailer_id=retailer_id,
            segment_id=segment_id
        )
        agents[metric.value] = agent_class(config, bus)
    
    # Register cross-effects (example relationships)
    # Penetration affects items per basket
    agents[StateMetric.ITEMS_PER_BASKET.value].register_cross_effect(
        source_metric=StateMetric.BASKET_PENETRATION.value,
        lag_periods=0,
        coefficient=0.3,
        confidence=0.7
    )
    
    # Items per basket affects size per item (inverse - more items, smaller size each)
    agents[StateMetric.SIZE_PER_ITEM.value].register_cross_effect(
        source_metric=StateMetric.ITEMS_PER_BASKET.value,
        lag_periods=0,
        coefficient=-0.1,
        confidence=0.6
    )
    
    return agents
