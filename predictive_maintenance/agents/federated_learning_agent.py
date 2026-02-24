"""
Federated Learning Agent (N4)

CrewAI agent that manages federated learning workflows using FlowerAI.
Replaces conceptual TypeScript FL integration from quest-agent-forge-main
with a Python CrewAI implementation.

Responsibilities:
- Coordinate federated training rounds across site-local models
- Aggregate model updates (FedAvg / FedProx strategies)
- Monitor convergence and recommend early stopping
- Track per-site contribution quality and detect poisoning
- Integrate with ExperimentationAgent for model promotion

Addresses N4 from the FRD implementation plan.
"""

import json
import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from shared.agents.crewai_base import (
    Agent, Task, Crew, Process, CREWAI_AVAILABLE,
    BaseCrewAgent, CrewAIAgentConfig, AgentCategory, AgentRole,
)

logger = logging.getLogger(__name__)

# CrewAI @tool decorator with fallback
try:
    from crewai.tools import tool as crewai_tool
except ImportError:
    def crewai_tool(name_or_func=None):
        def decorator(func):
            func.tool_name = name_or_func if isinstance(name_or_func, str) else func.__name__
            return func
        if callable(name_or_func):
            return decorator(name_or_func)
        return decorator

# FlowerAI availability check
FLWR_AVAILABLE = False
try:
    import flwr
    FLWR_AVAILABLE = True
except ImportError:
    logger.info("FlowerAI (flwr) not installed. FL agent runs in simulation mode.")


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class FLRoundResult:
    """Result of a single federated learning round."""
    round_id: int
    participating_sites: List[str]
    aggregated_loss: float
    aggregated_accuracy: float
    per_site_metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)
    strategy: str = "fedavg"
    completed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_id": self.round_id,
            "participating_sites": self.participating_sites,
            "aggregated_loss": self.aggregated_loss,
            "aggregated_accuracy": self.aggregated_accuracy,
            "per_site_metrics": self.per_site_metrics,
            "strategy": self.strategy,
            "completed_at": self.completed_at,
        }


@dataclass
class FLSession:
    """Tracks an entire federated learning session."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    model_id: str = ""
    strategy: str = "fedavg"
    target_rounds: int = 10
    min_sites: int = 2
    rounds: List[FLRoundResult] = field(default_factory=list)
    status: str = "initialized"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "model_id": self.model_id,
            "strategy": self.strategy,
            "target_rounds": self.target_rounds,
            "completed_rounds": len(self.rounds),
            "status": self.status,
            "latest_accuracy": self.rounds[-1].aggregated_accuracy if self.rounds else None,
            "created_at": self.created_at,
        }


# =============================================================================
# FL Engine (deterministic computations)
# =============================================================================

class FLEngine:
    """Core federated learning computations — aggregation, convergence, quality."""

    @staticmethod
    def federated_average(
        site_metrics: Dict[str, Dict[str, float]],
        weights: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """Compute weighted average of site metrics (FedAvg)."""
        if not site_metrics:
            return {"loss": 0.0, "accuracy": 0.0}

        if weights is None:
            # Equal weighting
            weights = {site: 1.0 / len(site_metrics) for site in site_metrics}

        total_weight = sum(weights.get(s, 0) for s in site_metrics)
        if total_weight == 0:
            total_weight = 1.0

        agg = {}
        for site, metrics in site_metrics.items():
            w = weights.get(site, 1.0 / len(site_metrics)) / total_weight
            for key, val in metrics.items():
                agg[key] = agg.get(key, 0.0) + val * w

        return {k: round(v, 6) for k, v in agg.items()}

    @staticmethod
    def check_convergence(
        rounds: List[FLRoundResult],
        patience: int = 3,
        min_improvement: float = 0.001,
    ) -> Dict[str, Any]:
        """Check if training has converged based on accuracy plateau."""
        if len(rounds) < patience + 1:
            return {"converged": False, "reason": "Not enough rounds yet"}

        recent = rounds[-patience:]
        accuracies = [r.aggregated_accuracy for r in recent]

        # Check if improvement is below threshold
        max_delta = max(
            abs(accuracies[i] - accuracies[i - 1])
            for i in range(1, len(accuracies))
        )

        converged = max_delta < min_improvement
        return {
            "converged": converged,
            "max_recent_delta": round(max_delta, 6),
            "threshold": min_improvement,
            "patience_rounds": patience,
            "reason": "Accuracy plateau detected" if converged else "Still improving",
        }

    @staticmethod
    def detect_poisoning(
        site_metrics: Dict[str, Dict[str, float]],
        z_threshold: float = 2.5,
    ) -> Dict[str, Any]:
        """Detect potential model poisoning via statistical outlier detection."""
        if len(site_metrics) < 3:
            return {"suspicious_sites": [], "note": "Need at least 3 sites for outlier detection"}

        losses = {s: m.get("loss", 0) for s, m in site_metrics.items()}
        vals = list(losses.values())
        mean_loss = sum(vals) / len(vals)
        std_loss = math.sqrt(sum((v - mean_loss) ** 2 for v in vals) / len(vals))

        suspicious = []
        if std_loss > 0:
            for site, loss in losses.items():
                z = abs(loss - mean_loss) / std_loss
                if z > z_threshold:
                    suspicious.append({
                        "site_id": site,
                        "loss": loss,
                        "z_score": round(z, 2),
                    })

        return {
            "suspicious_sites": suspicious,
            "mean_loss": round(mean_loss, 6),
            "std_loss": round(std_loss, 6),
            "z_threshold": z_threshold,
        }


# =============================================================================
# @tool Functions
# =============================================================================

@crewai_tool("start_fl_session")
def start_fl_session(
    model_id: str,
    strategy: str = "fedavg",
    target_rounds: int = 10,
    min_sites: int = 2,
) -> dict:
    """Start a new federated learning session. Returns session configuration."""
    session = FLSession(
        model_id=model_id,
        strategy=strategy,
        target_rounds=target_rounds,
        min_sites=min_sites,
        status="active",
    )
    return session.to_dict()


@crewai_tool("aggregate_round_metrics")
def aggregate_round_metrics(
    round_id: int,
    site_metrics_json: str,
    strategy: str = "fedavg",
    weights_json: str = "{}",
) -> dict:
    """Aggregate per-site model metrics for a federated learning round.
    site_metrics_json maps site_id to {"loss": float, "accuracy": float, ...}.
    weights_json optionally maps site_id to sample-count weight."""
    try:
        site_metrics = json.loads(site_metrics_json)
        weights = json.loads(weights_json) if weights_json != "{}" else None
    except json.JSONDecodeError:
        return {"error": "Invalid JSON"}

    aggregated = FLEngine.federated_average(site_metrics, weights)
    poisoning = FLEngine.detect_poisoning(site_metrics)

    return {
        "round_id": round_id,
        "strategy": strategy,
        "participating_sites": list(site_metrics.keys()),
        "aggregated_metrics": aggregated,
        "aggregated_loss": aggregated.get("loss", 0),
        "aggregated_accuracy": aggregated.get("accuracy", 0),
        "poisoning_check": poisoning,
    }


@crewai_tool("check_fl_convergence")
def check_fl_convergence(
    round_accuracies_json: str,
    patience: int = 3,
    min_improvement: float = 0.001,
) -> dict:
    """Check if federated learning has converged.
    round_accuracies_json is a JSON array of per-round accuracy floats."""
    try:
        accuracies = json.loads(round_accuracies_json)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON"}

    if len(accuracies) < patience + 1:
        return {"converged": False, "reason": "Not enough rounds yet"}

    recent = accuracies[-patience:]
    max_delta = max(abs(recent[i] - recent[i - 1]) for i in range(1, len(recent)))

    converged = max_delta < min_improvement
    return {
        "converged": converged,
        "max_recent_delta": round(max_delta, 6),
        "threshold": min_improvement,
        "total_rounds": len(accuracies),
        "latest_accuracy": accuracies[-1] if accuracies else None,
        "reason": "Accuracy plateau detected" if converged else "Still improving",
    }


@crewai_tool("evaluate_site_contribution")
def evaluate_site_contribution(
    site_id: str,
    site_metrics_json: str,
    global_metrics_json: str,
) -> dict:
    """Evaluate a single site's contribution to the federated model.
    Compares site metrics to global aggregated metrics to assess quality."""
    try:
        site = json.loads(site_metrics_json)
        glob = json.loads(global_metrics_json)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON"}

    loss_delta = site.get("loss", 0) - glob.get("loss", 0)
    acc_delta = site.get("accuracy", 0) - glob.get("accuracy", 0)

    quality = "good"
    if loss_delta > 0.1:
        quality = "poor"
    elif loss_delta > 0.05:
        quality = "marginal"

    return {
        "site_id": site_id,
        "quality": quality,
        "loss_delta": round(loss_delta, 4),
        "accuracy_delta": round(acc_delta, 4),
        "recommendation": (
            "Include in aggregation" if quality == "good"
            else "Monitor closely" if quality == "marginal"
            else "Consider excluding from next round"
        ),
    }


# =============================================================================
# Federated Learning CrewAI Agent
# =============================================================================

class FederatedLearningAgent(BaseCrewAgent):
    """
    CrewAI agent that coordinates federated learning across sites.

    Manages FL sessions, aggregates round results, monitors convergence,
    and integrates with the ExperimentationAgent for model promotion.
    """

    def __init__(self, **kwargs):
        config = CrewAIAgentConfig(
            agent_id="federated_learning",
            role=AgentRole.RESOURCE_ALLOCATOR,
            category=AgentCategory.ANALYTICS,
            name="Federated Learning Coordinator",
            goal=(
                "Coordinate federated model training across distributed sites. "
                "Aggregate updates, monitor convergence, detect poisoning, "
                "and recommend when models are ready for promotion."
            ),
            backstory=(
                "You are a distributed ML specialist who manages privacy-preserving "
                "model training across multiple sites. You ensure that federated "
                "training converges efficiently while protecting site data locality "
                "and detecting adversarial contributions."
            ),
        )
        super().__init__(config, **kwargs)
        self._sessions: Dict[str, FLSession] = {}
        self._flwr_available = FLWR_AVAILABLE

    @property
    def tools(self) -> list:
        return [
            start_fl_session,
            aggregate_round_metrics,
            check_fl_convergence,
            evaluate_site_contribution,
        ]

    def create_session(self, model_id: str, **kwargs) -> FLSession:
        """Create and register a new FL session."""
        session = FLSession(model_id=model_id, status="active", **kwargs)
        self._sessions[session.session_id] = session
        return session

    def record_round(
        self,
        session_id: str,
        site_metrics: Dict[str, Dict[str, float]],
        weights: Optional[Dict[str, float]] = None,
    ) -> Optional[FLRoundResult]:
        """Record a completed FL round in a session."""
        session = self._sessions.get(session_id)
        if not session:
            return None

        round_id = len(session.rounds) + 1
        aggregated = FLEngine.federated_average(site_metrics, weights)

        result = FLRoundResult(
            round_id=round_id,
            participating_sites=list(site_metrics.keys()),
            aggregated_loss=aggregated.get("loss", 0),
            aggregated_accuracy=aggregated.get("accuracy", 0),
            per_site_metrics=site_metrics,
            strategy=session.strategy,
        )
        session.rounds.append(result)

        # Check convergence
        convergence = FLEngine.check_convergence(session.rounds)
        if convergence["converged"]:
            session.status = "converged"

        # Check if target rounds reached
        if round_id >= session.target_rounds:
            session.status = "completed"

        return result

    def get_session(self, session_id: str) -> Optional[FLSession]:
        return self._sessions.get(session_id)
