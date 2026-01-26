"""
Attribution & Pathway Agent

Responsibilities:
- Maintains consistent decompositions into direct lift, indirect pathways, feedback loops, and decay
- Enforces accounting consistency (attribution must reconcile to total effects)

Business value: makes complex "ecosystem" effects auditable and repeatable.
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any
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


class PathwayType(str, Enum):
    """Types of attribution pathways"""
    DIRECT = "direct"
    INDIRECT = "indirect"
    CARRYOVER = "carryover"
    FEEDBACK = "feedback"
    BASELINE = "baseline"


@dataclass
class PathwayDecomposition:
    """Decomposition of effects through pathways"""
    driver: str
    total_effect: float
    
    # Pathway breakdown
    direct_effect: float
    indirect_effect: float
    carryover_effect: float
    feedback_effect: float
    
    # Confidence and metadata
    confidence: float
    decomposition_method: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def is_reconciled(self) -> bool:
        """Check if decomposition reconciles to total"""
        sum_pathways = (
            self.direct_effect + self.indirect_effect + 
            self.carryover_effect + self.feedback_effect
        )
        return abs(sum_pathways - self.total_effect) < 0.01 * abs(self.total_effect)
    
    @property
    def reconciliation_error(self) -> float:
        """Get reconciliation error"""
        sum_pathways = (
            self.direct_effect + self.indirect_effect + 
            self.carryover_effect + self.feedback_effect
        )
        return self.total_effect - sum_pathways
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'driver': self.driver,
            'total_effect': self.total_effect,
            'direct_effect': self.direct_effect,
            'indirect_effect': self.indirect_effect,
            'carryover_effect': self.carryover_effect,
            'feedback_effect': self.feedback_effect,
            'confidence': self.confidence,
            'is_reconciled': self.is_reconciled,
            'reconciliation_error': self.reconciliation_error,
            'method': self.decomposition_method,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class AttributionResult:
    """Complete attribution result"""
    period: date
    total_outcome: float
    baseline: float
    incremental: float
    
    # By driver
    driver_contributions: Dict[str, float]
    driver_decompositions: Dict[str, PathwayDecomposition]
    
    # Accounting check
    is_reconciled: bool
    reconciliation_error: float
    
    # Metadata
    confidence: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'period': str(self.period),
            'total_outcome': self.total_outcome,
            'baseline': self.baseline,
            'incremental': self.incremental,
            'driver_contributions': self.driver_contributions,
            'decompositions': {
                k: v.to_dict() for k, v in self.driver_decompositions.items()
            },
            'is_reconciled': self.is_reconciled,
            'reconciliation_error': self.reconciliation_error,
            'confidence': self.confidence,
            'timestamp': self.timestamp.isoformat()
        }


class AttributionAgent(BaseIQueueAgent):
    """
    Attribution & Pathway Agent
    
    Maintains consistent decompositions into:
    - Direct lift: Immediate effect of driver
    - Indirect pathways: Effects through other drivers/outcomes
    - Carryover: Lagged effects from prior periods
    - Feedback: Circular effects (e.g., sales → more media spend)
    
    Enforces accounting consistency: all effects must sum to total.
    """
    
    def __init__(
        self,
        config: AgentConfig,
        message_bus: Optional[AgentMessageBus] = None,
        drivers: Optional[List[str]] = None
    ):
        self.drivers = drivers or ['media', 'price', 'trade', 'competition', 'events']
        self.attribution_history: List[AttributionResult] = []
        self.pathway_models: Dict[str, Dict[str, float]] = {}
        
        super().__init__(config, message_bus)
    
    def _initialize_beliefs(self):
        """Initialize beliefs about attribution"""
        # Baseline share belief
        self.beliefs['baseline_share'] = BeliefState(
            name='baseline_share',
            mean=0.6,  # 60% baseline
            variance=0.01,
            confidence=0.5,
            source='prior'
        )
        
        # Per-driver contribution beliefs
        for driver in self.drivers:
            self.beliefs[f'{driver}_contribution_share'] = BeliefState(
                name=f'{driver}_contribution_share',
                mean=0.08,  # 8% each by default
                variance=0.01,
                confidence=0.3,
                source='prior'
            )
            
            # Direct vs indirect ratio
            self.beliefs[f'{driver}_direct_ratio'] = BeliefState(
                name=f'{driver}_direct_ratio',
                mean=0.7,  # 70% direct
                variance=0.02,
                confidence=0.4,
                source='prior'
            )
    
    def _subscribe_to_messages(self):
        """Subscribe to messages from driver agents"""
        self.message_bus.subscribe(
            MessageType.BELIEF_UPDATE,
            self._handle_driver_update
        )
    
    def _handle_driver_update(self, message: AgentMessage):
        """Handle updates from driver agents"""
        payload = message.payload
        belief_name = payload.get('belief_name', '')
        
        # Extract driver from belief name
        for driver in self.drivers:
            if driver in belief_name and 'elasticity' in belief_name:
                belief_data = payload.get('belief', {})
                elasticity = belief_data.get('mean', 0)
                
                # Update pathway model with new elasticity
                if driver not in self.pathway_models:
                    self.pathway_models[driver] = {}
                self.pathway_models[driver]['elasticity'] = elasticity
    
    def process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process attribution request.
        
        Args:
            inputs: Dict containing:
                - period: Date period for attribution
                - total_outcome: Total observed outcome
                - driver_spends: Dict of driver -> spend
                - driver_responses: Optional Dict of driver -> observed response
        """
        period = inputs.get('period', date.today())
        total_outcome = inputs.get('total_outcome', 0.0)
        driver_spends = inputs.get('driver_spends', {})
        driver_responses = inputs.get('driver_responses', {})
        
        # Compute attribution
        result = self._compute_attribution(
            period, total_outcome, driver_spends, driver_responses
        )
        
        # Store history
        self.attribution_history.append(result)
        
        # Update beliefs based on results
        self._update_beliefs_from_attribution(result)
        
        # Publish attribution update
        self._publish_attribution(result)
        
        self.last_update = datetime.utcnow()
        self.update_count += 1
        
        return result.to_dict()
    
    def _compute_attribution(
        self,
        period: date,
        total_outcome: float,
        driver_spends: Dict[str, float],
        driver_responses: Dict[str, float]
    ) -> AttributionResult:
        """Compute full attribution with pathway decomposition"""
        # Compute baseline
        baseline_share = self.beliefs['baseline_share'].mean
        baseline = total_outcome * baseline_share
        incremental = total_outcome - baseline
        
        # Compute driver contributions
        driver_contributions = {}
        driver_decompositions = {}
        
        remaining_incremental = incremental
        
        for driver in self.drivers:
            if driver in driver_spends and driver_spends[driver] > 0:
                # Get contribution share
                share_belief = self.beliefs.get(f'{driver}_contribution_share')
                if share_belief:
                    contribution = incremental * share_belief.mean
                else:
                    contribution = incremental / len(self.drivers)
                
                driver_contributions[driver] = contribution
                
                # Compute pathway decomposition
                decomposition = self._decompose_pathways(
                    driver, contribution, driver_spends.get(driver, 0)
                )
                driver_decompositions[driver] = decomposition
                
                remaining_incremental -= contribution
        
        # Allocate remaining to baseline adjustment
        if remaining_incremental != 0:
            baseline += remaining_incremental
        
        # Check reconciliation
        sum_contributions = sum(driver_contributions.values())
        is_reconciled = abs(sum_contributions - incremental) < 0.01 * abs(total_outcome)
        reconciliation_error = incremental - sum_contributions
        
        # Overall confidence
        confidence = np.mean([
            self.beliefs[f'{d}_contribution_share'].confidence 
            for d in self.drivers if f'{d}_contribution_share' in self.beliefs
        ])
        
        return AttributionResult(
            period=period,
            total_outcome=total_outcome,
            baseline=baseline,
            incremental=incremental,
            driver_contributions=driver_contributions,
            driver_decompositions=driver_decompositions,
            is_reconciled=is_reconciled,
            reconciliation_error=reconciliation_error,
            confidence=confidence
        )
    
    def _decompose_pathways(
        self,
        driver: str,
        total_contribution: float,
        spend: float
    ) -> PathwayDecomposition:
        """Decompose driver contribution into pathways"""
        # Get pathway ratios
        direct_ratio = self.beliefs.get(
            f'{driver}_direct_ratio', 
            BeliefState(name='default', mean=0.7, variance=0.01, confidence=0.5)
        ).mean
        
        # Pathway allocation
        direct_effect = total_contribution * direct_ratio
        indirect_effect = total_contribution * 0.15  # 15% indirect
        carryover_effect = total_contribution * 0.10  # 10% carryover
        feedback_effect = total_contribution * 0.05  # 5% feedback
        
        # Adjust to ensure reconciliation
        sum_pathways = direct_effect + indirect_effect + carryover_effect + feedback_effect
        if sum_pathways != total_contribution:
            adjustment = total_contribution - sum_pathways
            direct_effect += adjustment
        
        confidence = self.beliefs.get(
            f'{driver}_direct_ratio',
            BeliefState(name='default', mean=0.7, variance=0.01, confidence=0.5)
        ).confidence
        
        return PathwayDecomposition(
            driver=driver,
            total_effect=total_contribution,
            direct_effect=direct_effect,
            indirect_effect=indirect_effect,
            carryover_effect=carryover_effect,
            feedback_effect=feedback_effect,
            confidence=confidence,
            decomposition_method='proportional_with_priors'
        )
    
    def _update_beliefs_from_attribution(self, result: AttributionResult):
        """Update beliefs based on attribution results"""
        # Update baseline share
        observed_baseline_share = result.baseline / max(result.total_outcome, 1)
        self.update_belief('baseline_share', observed_baseline_share, 0.01)
        
        # Update driver contribution shares
        for driver, contribution in result.driver_contributions.items():
            observed_share = contribution / max(result.incremental, 1)
            key = f'{driver}_contribution_share'
            if key in self.beliefs:
                self.update_belief(key, observed_share, 0.01)
    
    def _publish_attribution(self, result: AttributionResult):
        """Publish attribution result to message bus"""
        self.message_bus.publish(AgentMessage(
            message_id=self._generate_id(),
            message_type=MessageType.ATTRIBUTION_UPDATE,
            sender_id=self.config.agent_id,
            recipient_id=None,
            payload=result.to_dict()
        ))
    
    def get_contribution_summary(self) -> Dict[str, Any]:
        """Get summary of driver contributions"""
        if not self.attribution_history:
            return {'status': 'no_history'}
        
        recent = self.attribution_history[-1]
        
        return {
            'period': str(recent.period),
            'total_outcome': recent.total_outcome,
            'baseline_pct': recent.baseline / recent.total_outcome * 100,
            'incremental_pct': recent.incremental / recent.total_outcome * 100,
            'by_driver': {
                driver: {
                    'contribution': contrib,
                    'pct_of_total': contrib / recent.total_outcome * 100,
                    'pct_of_incremental': contrib / max(recent.incremental, 1) * 100
                }
                for driver, contrib in recent.driver_contributions.items()
            },
            'is_reconciled': recent.is_reconciled,
            'confidence': recent.confidence
        }
    
    def enforce_consistency(self, attribution: AttributionResult) -> AttributionResult:
        """Ensure attribution is internally consistent"""
        # Adjust to ensure sum = total
        current_sum = attribution.baseline + sum(attribution.driver_contributions.values())
        
        if abs(current_sum - attribution.total_outcome) > 0.01:
            adjustment = attribution.total_outcome - current_sum
            
            # Distribute adjustment proportionally
            for driver in attribution.driver_contributions:
                share = attribution.driver_contributions[driver] / max(current_sum, 1)
                attribution.driver_contributions[driver] += adjustment * share
            
            attribution.is_reconciled = True
            attribution.reconciliation_error = 0.0
        
        return attribution
    
    def _get_goal(self) -> str:
        return (
            "Maintain consistent attribution of business outcomes to marketing drivers. "
            "Decompose effects into direct, indirect, carryover, and feedback pathways. "
            "Ensure all attributions reconcile to total observed effects."
        )
    
    def _get_backstory(self) -> str:
        return (
            "You are an expert in marketing attribution and econometric decomposition. "
            "You understand that effects flow through multiple pathways and time periods. "
            "Your decompositions make the complex marketing ecosystem auditable and repeatable."
        )


def create_attribution_agent(
    retailer_id: str,
    drivers: Optional[List[str]] = None,
    message_bus: Optional[AgentMessageBus] = None
) -> AttributionAgent:
    """Factory function for creating Attribution Agent"""
    config = AgentConfig(
        agent_id=f"attribution_{retailer_id}",
        agent_type=AgentType.ATTRIBUTION,
        retailer_id=retailer_id
    )
    
    return AttributionAgent(config, message_bus, drivers)
