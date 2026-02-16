"""
Shared JSON-schema contract types for inter-agent communication.

All agents in the Ownership Decision Crew read/write these artifacts.
Structured data only — narrative text comes exclusively from the AuditNarrator.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════
# 1. Stakeholder Position (emitted by each stakeholder agent)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Constraint:
    """A single constraint emitted by a stakeholder agent."""
    constraint_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    constraint_type: str = "hard"          # "hard" or "soft"
    description: str = ""
    parameter_id: Optional[str] = None     # linked parameter (if any)
    metric_id: Optional[str] = None        # linked metric (if any)
    operator: str = "lte"                  # "lte", "gte", "eq", "between"
    value: float = 0.0
    value_upper: Optional[float] = None    # for "between"
    weight: float = 1.0                    # importance for soft constraints (0-1)
    justification: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "constraint_id": self.constraint_id,
            "agent_id": self.agent_id,
            "constraint_type": self.constraint_type,
            "description": self.description,
            "parameter_id": self.parameter_id,
            "metric_id": self.metric_id,
            "operator": self.operator,
            "value": self.value,
            "value_upper": self.value_upper,
            "weight": self.weight,
            "justification": self.justification,
        }


@dataclass
class TradeBand:
    """Acceptable trade range for a parameter."""
    parameter_id: str = ""
    min_acceptable: float = 0.0
    max_acceptable: float = 0.0
    preferred: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameter_id": self.parameter_id,
            "min_acceptable": self.min_acceptable,
            "max_acceptable": self.max_acceptable,
            "preferred": self.preferred,
        }


@dataclass
class StakeholderPosition:
    """
    Complete negotiation position emitted by a stakeholder agent.

    Contains non-negotiables (hard constraints), preferences (soft constraints
    with weights), and acceptable trade bands for key parameters.
    """
    agent_id: str = ""
    agent_role: str = ""
    quadrant_authority: str = ""           # Q1, Q2, Q3, Q4, or "cross"

    non_negotiables: List[Constraint] = field(default_factory=list)
    preferences: List[Constraint] = field(default_factory=list)
    trade_bands: List[TradeBand] = field(default_factory=list)

    validated_metric_ids: List[str] = field(default_factory=list)
    objections: List[str] = field(default_factory=list)
    sign_off: bool = False

    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_role": self.agent_role,
            "quadrant_authority": self.quadrant_authority,
            "non_negotiables": [c.to_dict() for c in self.non_negotiables],
            "preferences": [c.to_dict() for c in self.preferences],
            "trade_bands": [tb.to_dict() for tb in self.trade_bands],
            "validated_metric_ids": self.validated_metric_ids,
            "objections": self.objections,
            "sign_off": self.sign_off,
            "timestamp": self.timestamp,
        }


# ═══════════════════════════════════════════════════════════════════
# 2. Assumption Register
# ═══════════════════════════════════════════════════════════════════

@dataclass
class AssumptionRecord:
    """A single assumption recorded by any agent."""
    assumption_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    owner_agent: str = ""
    justification: str = ""
    impact_rank: int = 0                   # 1 = highest impact
    status: str = "proposed"               # proposed | accepted | challenged | rejected
    parameter_id: Optional[str] = None
    metric_id: Optional[str] = None
    value: Optional[float] = None
    source: str = ""                       # "benchmark", "user_input", "model", "default"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assumption_id": self.assumption_id,
            "description": self.description,
            "owner_agent": self.owner_agent,
            "justification": self.justification,
            "impact_rank": self.impact_rank,
            "status": self.status,
            "parameter_id": self.parameter_id,
            "metric_id": self.metric_id,
            "value": self.value,
            "source": self.source,
        }


# ═══════════════════════════════════════════════════════════════════
# 3. Negotiation Log
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ConflictRecord:
    """A detected conflict between stakeholder positions."""
    conflict_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agents_involved: List[str] = field(default_factory=list)
    description: str = ""
    conflict_type: str = ""                # "budget", "threshold", "priority", "valuation"
    resolution: str = ""
    resolution_method: str = ""            # "constraint_satisfaction", "weight_compromise", "manager_override"
    compromise_value: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "agents_involved": self.agents_involved,
            "description": self.description,
            "conflict_type": self.conflict_type,
            "resolution": self.resolution,
            "resolution_method": self.resolution_method,
            "compromise_value": self.compromise_value,
        }


@dataclass
class NegotiationLog:
    """Full log of the negotiation process."""
    positions: List[StakeholderPosition] = field(default_factory=list)
    conflicts_detected: List[ConflictRecord] = field(default_factory=list)
    conflicts_resolved: int = 0
    rounds: int = 0
    final_sign_offs: Dict[str, bool] = field(default_factory=dict)
    unresolved_objections: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "positions": [p.to_dict() for p in self.positions],
            "conflicts_detected": [c.to_dict() for c in self.conflicts_detected],
            "conflicts_resolved": self.conflicts_resolved,
            "rounds": self.rounds,
            "final_sign_offs": self.final_sign_offs,
            "unresolved_objections": self.unresolved_objections,
        }


# ═══════════════════════════════════════════════════════════════════
# 4. Pareto Option (from multi-objective optimizer)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ParetoOption:
    """A single non-dominated solution on the Pareto frontier."""
    option_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    label: str = ""                        # "Max NPV", "Min Risk", etc.
    objective_function: str = ""           # which objective was optimized
    npv: float = 0.0
    roi_pct: float = 0.0
    risk_score: float = 0.0
    compliance_gap: float = 0.0            # 0 = fully compliant
    total_cost: float = 0.0
    total_savings: float = 0.0
    selected_line_ids: List[str] = field(default_factory=list)
    budget_utilization: Dict[str, float] = field(default_factory=dict)
    stakeholder_utility_scores: Dict[str, float] = field(default_factory=dict)

    @staticmethod
    def _safe_float(v: float) -> float:
        """Replace inf/nan with JSON-safe values."""
        import math
        if math.isinf(v) or math.isnan(v):
            return 0.0
        return v

    def to_dict(self) -> Dict[str, Any]:
        return {
            "option_id": self.option_id,
            "label": self.label,
            "objective_function": self.objective_function,
            "npv": round(self._safe_float(self.npv), 2),
            "roi_pct": round(self._safe_float(self.roi_pct), 1),
            "risk_score": round(self._safe_float(self.risk_score), 3),
            "compliance_gap": round(self._safe_float(self.compliance_gap), 2),
            "total_cost": round(self._safe_float(self.total_cost), 2),
            "total_savings": round(self._safe_float(self.total_savings), 2),
            "selected_line_count": len(self.selected_line_ids),
            "budget_utilization": {
                k: round(self._safe_float(v), 3) for k, v in self.budget_utilization.items()
            },
            "stakeholder_utility_scores": {
                k: round(self._safe_float(v), 3) for k, v in self.stakeholder_utility_scores.items()
            },
        }


# ═══════════════════════════════════════════════════════════════════
# 5. Agent Message (inter-agent communication)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class AgentMessage:
    """A single message exchanged between agents during the pipeline."""
    message_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    sender: str = ""            # agent_id of sender
    receiver: str = ""          # agent_id of receiver (or "all" for broadcasts)
    message_type: str = ""      # context_handoff | tool_call | negotiation | delegation | sign_off | stage_transition
    stage: int = 0              # pipeline stage (0-4)
    content: str = ""           # human-readable summary
    data_summary: Dict[str, Any] = field(default_factory=dict)  # structured payload preview
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "sender": self.sender,
            "receiver": self.receiver,
            "message_type": self.message_type,
            "stage": self.stage,
            "content": self.content,
            "data_summary": self.data_summary,
            "timestamp": self.timestamp,
        }


# ═══════════════════════════════════════════════════════════════════
# 6. Decision Crew Output (final composite)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class DecisionCrewOutput:
    """
    Complete output from the OwnershipDecisionCrew.

    Contains all artifacts produced by the 12-agent pipeline:
    cost stack, ROI, Pareto options, negotiation log, assumptions,
    and board-ready narrative.
    """
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Stage 1 outputs
    stakeholder_positions: List[StakeholderPosition] = field(default_factory=list)

    # Stage 2 outputs (cost lines per dimension)
    cost_lines_by_dimension: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    # Stage 3 outputs
    unified_cost_stack: Dict[str, Any] = field(default_factory=dict)
    adjustments_applied: List[Dict[str, Any]] = field(default_factory=list)

    # Stage 4 outputs
    consolidated_roi: Dict[str, Any] = field(default_factory=dict)
    pareto_options: List[ParetoOption] = field(default_factory=list)
    recommended_option_id: str = ""

    # Governance
    negotiation_log: NegotiationLog = field(default_factory=NegotiationLog)
    assumption_register: List[AssumptionRecord] = field(default_factory=list)

    # Narrative (from AuditNarrator)
    board_narrative: str = ""
    lineage_summary: Dict[str, Any] = field(default_factory=dict)

    # Inter-agent communication log
    agent_messages: List["AgentMessage"] = field(default_factory=list)

    # Metadata
    agent_count: int = 0
    task_count: int = 0
    execution_time_ms: int = 0
    crewai_used: bool = False
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "stakeholder_positions": [p.to_dict() for p in self.stakeholder_positions],
            "cost_lines_by_dimension": self.cost_lines_by_dimension,
            "unified_cost_stack": self.unified_cost_stack,
            "adjustments_applied": self.adjustments_applied,
            "consolidated_roi": self.consolidated_roi,
            "pareto_options": [p.to_dict() for p in self.pareto_options],
            "recommended_option_id": self.recommended_option_id,
            "negotiation_log": self.negotiation_log.to_dict(),
            "assumption_register": [a.to_dict() for a in self.assumption_register],
            "board_narrative": self.board_narrative,
            "lineage_summary": self.lineage_summary,
            "agent_messages": [m.to_dict() for m in self.agent_messages],
            "agent_count": self.agent_count,
            "task_count": self.task_count,
            "execution_time_ms": self.execution_time_ms,
            "crewai_used": self.crewai_used,
            "timestamp": self.timestamp,
        }
