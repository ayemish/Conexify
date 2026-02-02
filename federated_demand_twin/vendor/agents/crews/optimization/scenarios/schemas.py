"""
Scenario Schema Definitions for Decision Support System

Defines the data structures for business scenarios, constraints, triggers,
recommendations, evidence, and reasoning chains.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple


class ScenarioCategory(Enum):
    """Categories of business scenarios."""
    CORE_OUTCOME = "core_outcome"
    INCREMENTALITY = "incrementality"
    RISK_GOVERNANCE = "risk_governance"
    PORTFOLIO = "portfolio"
    OPERATIONAL = "operational"


class ObjectiveType(Enum):
    """Types of optimization objectives."""
    INCREMENTAL_SALES = "incremental_sales"
    INCREMENTAL_PROFIT = "incremental_profit"
    EFFICIENCY = "efficiency"
    STABILITY = "stability"
    DECLINE_RISK_MIN = "decline_risk_min"
    NEW_TO_BRAND = "new_to_brand"
    SHARE_DEFENSE = "share_defense"
    CATEGORY_PROTECTION = "category_protection"
    LEARNING = "learning"


class RiskAppetite(Enum):
    """Risk appetite levels mapped to credible interval thresholds."""
    CONSERVATIVE = "conservative"  # 90% CI, max 5% reallocation
    BALANCED = "balanced"          # 80% CI, max 15% reallocation
    AGGRESSIVE = "aggressive"      # 70% CI, max 30% reallocation


class Cadence(Enum):
    """Optimization cadence options."""
    DAILY = "daily"
    WEEKLY = "weekly"
    EVENT_DRIVEN = "event_driven"
    CONTINUOUS = "continuous"


class TriggerType(Enum):
    """Types of scenario triggers."""
    THRESHOLD_BREACH = "threshold_breach"
    TREND_DETECTION = "trend_detection"
    EXTERNAL_EVENT = "external_event"
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class EvidenceType(Enum):
    """Types of supporting evidence."""
    POSTERIOR_DISTRIBUTION = "posterior_distribution"
    CREDIBLE_INTERVAL = "credible_interval"
    PROBABILITY_STATEMENT = "probability_statement"
    COUNTERFACTUAL = "counterfactual"
    HISTORICAL_COMPARISON = "historical_comparison"
    BENCHMARK = "benchmark"
    SENSITIVITY_ANALYSIS = "sensitivity_analysis"
    CAUSAL_ATTRIBUTION = "causal_attribution"


class ActionType(Enum):
    """Types of recommended actions."""
    REALLOCATE = "reallocate"
    SCALE = "scale"
    PAUSE = "pause"
    EXPLORE = "explore"
    MAINTAIN = "maintain"
    TAPER = "taper"
    CONCENTRATE = "concentrate"
    DIVERSIFY = "diversify"


@dataclass
class ScenarioConstraints:
    """Constraints for a business scenario."""
    spend_cap: Optional[float] = None
    spend_floor: Optional[float] = None
    revenue_floor: Optional[float] = None
    revenue_ceiling: Optional[float] = None
    profit_floor: Optional[float] = None
    roas_floor: Optional[float] = None
    roas_ceiling: Optional[float] = None
    efficiency_floor: Optional[float] = None
    variance_cap: Optional[float] = None
    risk_cap: Optional[float] = None
    share_floor: Optional[float] = None
    
    # RMN/Channel constraints
    rmn_minimums: Dict[str, float] = field(default_factory=dict)
    rmn_maximums: Dict[str, float] = field(default_factory=dict)
    channel_minimums: Dict[str, float] = field(default_factory=dict)
    channel_maximums: Dict[str, float] = field(default_factory=dict)
    
    # Operational constraints
    max_reallocation_pct: float = 0.15  # Max % budget moved per cycle
    exploration_budget_pct: float = 0.10  # % reserved for learning
    min_presence_by_rmn: bool = True
    inventory_aware: bool = True
    
    # Risk constraints
    cannibalization_tolerance: float = 0.05  # Max acceptable cannibalization rate
    prob_underperform_max: float = 0.10  # Max P(underperform)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "spend_cap": self.spend_cap,
            "spend_floor": self.spend_floor,
            "revenue_floor": self.revenue_floor,
            "roas_floor": self.roas_floor,
            "efficiency_floor": self.efficiency_floor,
            "variance_cap": self.variance_cap,
            "max_reallocation_pct": self.max_reallocation_pct,
            "exploration_budget_pct": self.exploration_budget_pct,
            "rmn_minimums": self.rmn_minimums,
            "channel_minimums": self.channel_minimums,
        }


@dataclass
class ScenarioTrigger:
    """Trigger conditions for a scenario."""
    trigger_type: TriggerType
    description: str
    conditions: Dict[str, Any] = field(default_factory=dict)
    threshold: Optional[float] = None
    lookback_days: int = 30
    severity: str = "medium"  # low, medium, high, critical
    
    def is_triggered(self, current_state: Dict[str, Any]) -> Tuple[bool, str]:
        """Check if trigger conditions are met."""
        # Placeholder for trigger evaluation logic
        return False, "Trigger not evaluated"


@dataclass
class RecommendedAction:
    """A recommended action from the optimization."""
    action_id: str
    action_type: ActionType
    entity_type: str  # brand, rmn, channel, campaign
    entity_id: str
    entity_name: str
    description: str
    current_value: float
    recommended_value: float
    delta: float
    delta_pct: float
    expected_impact: float
    confidence: float  # 0-1
    priority: int  # 1 = highest
    rationale: str
    risks: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type.value,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "description": self.description,
            "current_value": self.current_value,
            "recommended_value": self.recommended_value,
            "delta": self.delta,
            "delta_pct": self.delta_pct,
            "expected_impact": self.expected_impact,
            "confidence": self.confidence,
            "priority": self.priority,
            "rationale": self.rationale,
            "risks": self.risks,
        }


@dataclass
class EvidenceItem:
    """A piece of evidence supporting a recommendation."""
    evidence_id: str
    evidence_type: EvidenceType
    title: str
    description: str
    metric_name: str
    metric_value: float
    confidence_interval: Optional[Tuple[float, float]] = None
    probability: Optional[float] = None
    comparison_baseline: Optional[float] = None
    source: str = "bayesian_model"
    timestamp: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "evidence_type": self.evidence_type.value,
            "title": self.title,
            "description": self.description,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "confidence_interval": list(self.confidence_interval) if self.confidence_interval else None,
            "probability": self.probability,
            "comparison_baseline": self.comparison_baseline,
            "source": self.source,
        }


@dataclass
class ReasoningStep:
    """A step in the reasoning chain."""
    step_id: str
    step_number: int
    crew_id: str
    agent_id: str
    action: str
    input_summary: str
    output_summary: str
    reasoning: str
    confidence: float
    duration_ms: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_number": self.step_number,
            "crew_id": self.crew_id,
            "agent_id": self.agent_id,
            "action": self.action,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "duration_ms": self.duration_ms,
        }


@dataclass
class ReasoningChain:
    """Complete reasoning chain showing how decision was reached."""
    chain_id: str
    scenario_id: str
    steps: List[ReasoningStep] = field(default_factory=list)
    crews_involved: List[str] = field(default_factory=list)
    cross_crew_messages: List[Dict[str, Any]] = field(default_factory=list)
    total_duration_ms: int = 0
    
    def add_step(self, step: ReasoningStep) -> None:
        self.steps.append(step)
        if step.crew_id not in self.crews_involved:
            self.crews_involved.append(step.crew_id)
        self.total_duration_ms += step.duration_ms
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "scenario_id": self.scenario_id,
            "steps": [s.to_dict() for s in self.steps],
            "crews_involved": self.crews_involved,
            "cross_crew_messages": self.cross_crew_messages,
            "total_duration_ms": self.total_duration_ms,
        }


@dataclass
class DecisionRecommendation:
    """A complete decision recommendation with evidence and reasoning."""
    recommendation_id: str
    scenario_id: str
    scenario_name: str
    executive_summary: str
    recommended_actions: List[RecommendedAction]
    supporting_evidence: List[EvidenceItem]
    reasoning_chain: ReasoningChain
    total_expected_impact: float
    overall_confidence: float
    risk_assessment: str
    constraints_satisfied: bool
    constraint_violations: List[str] = field(default_factory=list)
    alternative_options: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "executive_summary": self.executive_summary,
            "recommended_actions": [a.to_dict() for a in self.recommended_actions],
            "supporting_evidence": [e.to_dict() for e in self.supporting_evidence],
            "reasoning_chain": self.reasoning_chain.to_dict(),
            "total_expected_impact": self.total_expected_impact,
            "overall_confidence": self.overall_confidence,
            "risk_assessment": self.risk_assessment,
            "constraints_satisfied": self.constraints_satisfied,
            "constraint_violations": self.constraint_violations,
            "alternative_options": self.alternative_options,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class BusinessScenario:
    """Complete definition of a business scenario."""
    scenario_id: str
    name: str
    description: str
    category: ScenarioCategory
    objective_type: ObjectiveType
    objective_description: str
    
    # Configuration
    default_constraints: ScenarioConstraints
    triggers: List[ScenarioTrigger]
    default_risk_appetite: RiskAppetite = RiskAppetite.BALANCED
    default_cadence: Cadence = Cadence.WEEKLY
    
    # Crew orchestration
    primary_crew: str = "scenario_orchestrator"
    required_crews: List[str] = field(default_factory=list)
    crew_sequence: List[str] = field(default_factory=list)
    
    # Action templates
    action_templates: List[Dict[str, Any]] = field(default_factory=list)
    
    # UI/UX
    icon: str = "trending_up"
    color: str = "#2196F3"
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "objective_type": self.objective_type.value,
            "objective_description": self.objective_description,
            "default_constraints": self.default_constraints.to_dict(),
            "triggers": [{"type": t.trigger_type.value, "description": t.description} for t in self.triggers],
            "default_risk_appetite": self.default_risk_appetite.value,
            "default_cadence": self.default_cadence.value,
            "primary_crew": self.primary_crew,
            "required_crews": self.required_crews,
            "crew_sequence": self.crew_sequence,
            "icon": self.icon,
            "color": self.color,
            "tags": self.tags,
        }


@dataclass
class DecisionSupportOutput:
    """Complete output from the decision support system."""
    session_id: str
    scenario: BusinessScenario
    recommendation: DecisionRecommendation
    current_state: Dict[str, Any]
    projected_state: Dict[str, Any]
    comparison: Dict[str, Any]
    user_controls: Dict[str, Any]
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "scenario": self.scenario.to_dict(),
            "recommendation": self.recommendation.to_dict(),
            "current_state": self.current_state,
            "projected_state": self.projected_state,
            "comparison": self.comparison,
            "user_controls": self.user_controls,
            "audit_trail": self.audit_trail,
        }
