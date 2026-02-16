"""
Adaptive Agent Weights via Thompson Sampling

Implements Bayesian optimization of agent voting weights:
1. Thompson Sampling for exploration-exploitation balance
2. Multi-armed bandit formulation for agent selection
3. Contextual bandits for situation-dependent weighting
4. Online learning from operator feedback

References:
- Thompson, "On the likelihood that one unknown probability exceeds another", 1933
- Russo et al., "A Tutorial on Thompson Sampling", 2018
- Agrawal & Goyal, "Thompson Sampling for Contextual Bandits", ICML 2013
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import uuid

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class AgentBelief:
    """Beta distribution belief about agent's correctness probability"""
    agent_role: str
    
    # Beta distribution parameters (prior + observations)
    alpha: float = 1.0  # Successes + prior
    beta: float = 1.0   # Failures + prior
    
    # Contextual parameters (per-regime, per-fault-type)
    contextual_alpha: Dict[str, float] = field(default_factory=lambda: defaultdict(lambda: 1.0))
    contextual_beta: Dict[str, float] = field(default_factory=lambda: defaultdict(lambda: 1.0))
    
    # Performance tracking
    total_correct: int = 0
    total_incorrect: int = 0
    recent_accuracy: float = 0.5
    
    # Timestamp tracking
    last_update: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def mean(self) -> float:
        """Expected value (mean of Beta distribution)"""
        return self.alpha / (self.alpha + self.beta)
    
    @property
    def variance(self) -> float:
        """Variance of Beta distribution"""
        ab = self.alpha + self.beta
        return (self.alpha * self.beta) / (ab ** 2 * (ab + 1))
    
    @property
    def confidence(self) -> float:
        """Confidence based on number of observations"""
        total = self.alpha + self.beta - 2  # Subtract prior
        return 1.0 - 1.0 / (1.0 + total / 10.0)
    
    def sample(self) -> float:
        """Thompson Sampling: draw from posterior"""
        return np.random.beta(self.alpha, self.beta)
    
    def contextual_sample(self, context_key: str) -> float:
        """Sample from contextual posterior"""
        a = self.contextual_alpha.get(context_key, 1.0)
        b = self.contextual_beta.get(context_key, 1.0)
        return np.random.beta(a, b)
    
    def update(self, was_correct: bool, context_key: str = None):
        """Bayesian update after observing outcome"""
        if was_correct:
            self.alpha += 1.0
            self.total_correct += 1
            if context_key:
                self.contextual_alpha[context_key] = self.contextual_alpha.get(context_key, 1.0) + 1.0
        else:
            self.beta += 1.0
            self.total_incorrect += 1
            if context_key:
                self.contextual_beta[context_key] = self.contextual_beta.get(context_key, 1.0) + 1.0
        
        self.recent_accuracy = self.total_correct / max(1, self.total_correct + self.total_incorrect)
        self.last_update = datetime.utcnow()


@dataclass
class VotingDecision:
    """Record of a voting decision for learning"""
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Context
    asset_id: str = ""
    regime: str = ""
    fault_type: str = ""
    context_key: str = ""
    
    # Agent votes and weights
    agent_votes: Dict[str, bool] = field(default_factory=dict)  # role -> vote
    agent_weights: Dict[str, float] = field(default_factory=dict)
    
    # Final decision
    final_decision: str = ""
    confidence: float = 0.0
    
    # Outcome (filled after feedback)
    outcome: Optional[str] = None
    was_correct: Optional[bool] = None


class AdaptiveAgentWeights:
    """
    Bayesian optimization of agent voting weights via Thompson Sampling.
    
    Each agent role has a Beta distribution belief about its reliability.
    Weights are sampled from these posteriors to balance:
    - Exploitation: Give more weight to historically accurate agents
    - Exploration: Try agents with uncertain performance
    
    Supports contextual bandits: different weights per context (regime, fault type).
    """
    
    def __init__(
        self,
        agent_roles: List[str],
        prior_alpha: float = 2.0,
        prior_beta: float = 2.0,
        decay_rate: float = 0.001,
        min_weight: float = 0.05,
    ):
        """
        Initialize adaptive weight service.
        
        Args:
            agent_roles: List of agent role names
            prior_alpha: Prior successes (higher = more optimistic)
            prior_beta: Prior failures (higher = more pessimistic)
            decay_rate: Rate at which old observations decay
            min_weight: Minimum weight for any agent
        """
        self.agent_roles = agent_roles
        self.prior_alpha = prior_alpha
        self.prior_beta = prior_beta
        self.decay_rate = decay_rate
        self.min_weight = min_weight
        
        # Initialize beliefs for each agent
        self.beliefs: Dict[str, AgentBelief] = {
            role: AgentBelief(
                agent_role=role,
                alpha=prior_alpha,
                beta=prior_beta,
            )
            for role in agent_roles
        }
        
        # Decision history for learning
        self.decision_history: List[VotingDecision] = []
        
        # Performance tracking
        self._correct_decisions = 0
        self._total_decisions = 0
        
        logger.info(f"AdaptiveAgentWeights initialized for {len(agent_roles)} agents")
    
    def sample_weights(self, context: Dict[str, Any] = None) -> Dict[str, float]:
        """
        Sample agent weights using Thompson Sampling.
        
        Args:
            context: Optional context for contextual bandits
                     (e.g., {"regime": "cooling", "fault_type": "refrigerant_leak"})
        
        Returns:
            Dict mapping agent_role -> weight (normalized to sum to 1)
        """
        context_key = self._build_context_key(context) if context else None
        
        # Sample from posterior for each agent
        samples = {}
        for role, belief in self.beliefs.items():
            if context_key:
                samples[role] = belief.contextual_sample(context_key)
            else:
                samples[role] = belief.sample()
        
        # Ensure minimum weight
        for role in samples:
            samples[role] = max(samples[role], self.min_weight)
        
        # Normalize to sum to 1
        total = sum(samples.values())
        return {role: w / total for role, w in samples.items()}
    
    def get_mean_weights(self, context: Dict[str, Any] = None) -> Dict[str, float]:
        """
        Get mean weights (exploitation only, no exploration).
        
        Useful for final production use after sufficient learning.
        """
        context_key = self._build_context_key(context) if context else None
        
        weights = {}
        for role, belief in self.beliefs.items():
            if context_key:
                a = belief.contextual_alpha.get(context_key, 1.0)
                b = belief.contextual_beta.get(context_key, 1.0)
                weights[role] = a / (a + b)
            else:
                weights[role] = belief.mean
        
        # Normalize
        total = sum(weights.values())
        return {role: max(w / total, self.min_weight) for role, w in weights.items()}
    
    def record_decision(
        self,
        asset_id: str,
        agent_votes: Dict[str, bool],
        agent_weights: Dict[str, float],
        final_decision: str,
        confidence: float,
        regime: str = "",
        fault_type: str = "",
    ) -> str:
        """
        Record a voting decision for later learning.
        
        Returns:
            decision_id for linking with outcome
        """
        context_key = self._build_context_key({
            "regime": regime,
            "fault_type": fault_type,
        })
        
        decision = VotingDecision(
            asset_id=asset_id,
            regime=regime,
            fault_type=fault_type,
            context_key=context_key,
            agent_votes=agent_votes,
            agent_weights=agent_weights,
            final_decision=final_decision,
            confidence=confidence,
        )
        
        self.decision_history.append(decision)
        
        # Trim old history
        if len(self.decision_history) > 10000:
            self.decision_history = self.decision_history[-5000:]
        
        return decision.decision_id
    
    def update_from_feedback(
        self,
        decision_id: str,
        outcome: str,
        was_correct: bool,
    ):
        """
        Update agent beliefs based on decision outcome.
        
        Args:
            decision_id: ID from record_decision
            outcome: What actually happened
            was_correct: Whether the decision was correct
        """
        # Find the decision
        decision = None
        for d in self.decision_history:
            if d.decision_id == decision_id:
                decision = d
                break
        
        if not decision:
            logger.warning(f"Decision not found: {decision_id}")
            return
        
        decision.outcome = outcome
        decision.was_correct = was_correct
        
        # Update beliefs for each agent based on their vote
        for role, vote in decision.agent_votes.items():
            if role not in self.beliefs:
                continue
            
            belief = self.beliefs[role]
            
            # Agent was correct if their vote matched the actual outcome
            agent_correct = (vote == was_correct)
            
            belief.update(
                was_correct=agent_correct,
                context_key=decision.context_key,
            )
        
        # Update global tracking
        self._total_decisions += 1
        if was_correct:
            self._correct_decisions += 1
        
        # Apply decay to old observations
        self._apply_decay()
        
        logger.debug(
            f"Updated beliefs from decision {decision_id}: "
            f"correct={was_correct}, agents updated={list(decision.agent_votes.keys())}"
        )
    
    def update_agent_directly(
        self,
        agent_role: str,
        was_correct: bool,
        context: Dict[str, Any] = None,
    ):
        """Directly update an agent's belief without a full decision record"""
        if agent_role not in self.beliefs:
            logger.warning(f"Unknown agent role: {agent_role}")
            return
        
        context_key = self._build_context_key(context) if context else None
        self.beliefs[agent_role].update(was_correct, context_key)
    
    def _build_context_key(self, context: Dict[str, Any]) -> str:
        """Build context key for contextual bandits"""
        if not context:
            return "default"
        
        parts = []
        if context.get("regime"):
            parts.append(f"regime:{context['regime']}")
        if context.get("fault_type"):
            parts.append(f"fault:{context['fault_type']}")
        
        return "|".join(parts) if parts else "default"
    
    def _apply_decay(self):
        """Apply decay to old observations (moves towards prior)"""
        for belief in self.beliefs.values():
            # Decay towards prior
            belief.alpha = self.prior_alpha + (belief.alpha - self.prior_alpha) * (1 - self.decay_rate)
            belief.beta = self.prior_beta + (belief.beta - self.prior_beta) * (1 - self.decay_rate)
            
            # Also decay contextual beliefs
            for key in list(belief.contextual_alpha.keys()):
                belief.contextual_alpha[key] = 1.0 + (belief.contextual_alpha[key] - 1.0) * (1 - self.decay_rate)
            for key in list(belief.contextual_beta.keys()):
                belief.contextual_beta[key] = 1.0 + (belief.contextual_beta[key] - 1.0) * (1 - self.decay_rate)
    
    def get_agent_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get current statistics for all agents"""
        return {
            role: {
                "mean_reliability": belief.mean,
                "variance": belief.variance,
                "confidence": belief.confidence,
                "total_correct": belief.total_correct,
                "total_incorrect": belief.total_incorrect,
                "recent_accuracy": belief.recent_accuracy,
                "alpha": belief.alpha,
                "beta": belief.beta,
            }
            for role, belief in self.beliefs.items()
        }
    
    def get_ranking(self) -> List[Tuple[str, float, float]]:
        """Get agents ranked by mean reliability (role, mean, confidence)"""
        ranking = [
            (role, belief.mean, belief.confidence)
            for role, belief in self.beliefs.items()
        ]
        return sorted(ranking, key=lambda x: -x[1])
    
    def get_contextual_stats(self, context_key: str) -> Dict[str, Dict[str, Any]]:
        """Get statistics for a specific context"""
        stats = {}
        for role, belief in self.beliefs.items():
            a = belief.contextual_alpha.get(context_key, 1.0)
            b = belief.contextual_beta.get(context_key, 1.0)
            stats[role] = {
                "contextual_mean": a / (a + b),
                "alpha": a,
                "beta": b,
                "observations": a + b - 2,
            }
        return stats
    
    @property
    def overall_accuracy(self) -> float:
        """Overall decision accuracy"""
        if self._total_decisions == 0:
            return 0.5
        return self._correct_decisions / self._total_decisions
    
    def export_state(self) -> Dict[str, Any]:
        """Export current state for persistence"""
        return {
            "agent_roles": self.agent_roles,
            "prior_alpha": self.prior_alpha,
            "prior_beta": self.prior_beta,
            "beliefs": {
                role: {
                    "alpha": b.alpha,
                    "beta": b.beta,
                    "total_correct": b.total_correct,
                    "total_incorrect": b.total_incorrect,
                    "contextual_alpha": dict(b.contextual_alpha),
                    "contextual_beta": dict(b.contextual_beta),
                }
                for role, b in self.beliefs.items()
            },
            "correct_decisions": self._correct_decisions,
            "total_decisions": self._total_decisions,
        }
    
    def import_state(self, state: Dict[str, Any]):
        """Import persisted state"""
        for role, belief_state in state.get("beliefs", {}).items():
            if role in self.beliefs:
                b = self.beliefs[role]
                b.alpha = belief_state.get("alpha", self.prior_alpha)
                b.beta = belief_state.get("beta", self.prior_beta)
                b.total_correct = belief_state.get("total_correct", 0)
                b.total_incorrect = belief_state.get("total_incorrect", 0)
                b.contextual_alpha = defaultdict(
                    lambda: 1.0,
                    belief_state.get("contextual_alpha", {}),
                )
                b.contextual_beta = defaultdict(
                    lambda: 1.0,
                    belief_state.get("contextual_beta", {}),
                )
        
        self._correct_decisions = state.get("correct_decisions", 0)
        self._total_decisions = state.get("total_decisions", 0)
