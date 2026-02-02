"""
Optimization Crew Schemas

Defines data structures for crew configuration, constraints, and outputs.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from uuid import uuid4


class DesiredOutcome(Enum):
    """Objective functions for optimization crews."""
    INCREASE_REVENUE = "increase_revenue"
    INCREASE_MARGIN = "increase_margin"
    MAINTAIN_REVENUE = "maintain_revenue"
    REDUCE_COST = "reduce_cost"


class OptimizationLevel(Enum):
    """Analytical levels for optimization."""
    BRAND = "brand"
    RMN = "rmn"
    CAMPAIGN = "campaign"
    MESSAGE = "message"
    CHANNEL = "channel"


class ConstraintType(Enum):
    """Types of optimization constraints."""
    BUDGET_CAP = "budget_cap"
    BUDGET_FLOOR = "budget_floor"
    REVENUE_FLOOR = "revenue_floor"
    CHANNEL_MIN = "channel_min"
    CHANNEL_MAX = "channel_max"
    RMN_MIN = "rmn_min"
    RMN_MAX = "rmn_max"
    PACING = "pacing"
    BRAND_SAFETY = "brand_safety"
    INVENTORY = "inventory"


@dataclass
class Constraint:
    """Individual optimization constraint."""
    constraint_id: str = field(default_factory=lambda: str(uuid4()))
    constraint_type: ConstraintType = ConstraintType.BUDGET_CAP
    entity_type: str = ""  # brand, rmn, channel, campaign
    entity_id: str = ""
    value: float = 0.0
    is_hard: bool = True  # Hard constraint vs soft preference
    priority: int = 1  # Higher = more important
    description: str = ""


@dataclass
class OptimizationConstraints:
    """Collection of constraints for an optimization run."""
    budget: float = 0.0
    budget_delta: Optional[float] = None  # For scenario changes
    revenue_floor: Optional[float] = None
    margin_floor: Optional[float] = None
    
    # Entity-level constraints
    channel_floors: Dict[str, float] = field(default_factory=dict)
    channel_ceilings: Dict[str, float] = field(default_factory=dict)
    rmn_floors: Dict[str, float] = field(default_factory=dict)
    rmn_ceilings: Dict[str, float] = field(default_factory=dict)
    brand_floors: Dict[str, float] = field(default_factory=dict)
    brand_ceilings: Dict[str, float] = field(default_factory=dict)
    
    # Pacing constraints
    pacing_start_date: Optional[datetime] = None
    pacing_end_date: Optional[datetime] = None
    pacing_curve: str = "linear"  # linear, front_loaded, back_loaded
    
    # Additional constraints
    custom_constraints: List[Constraint] = field(default_factory=list)
    
    # Guardrails
    min_channel_spend: float = 1000.0
    max_allocation_change_pct: float = 0.5  # Max 50% change from baseline
    require_test_budget: bool = True
    test_budget_pct: float = 0.10  # 10% for learning


@dataclass
class CrewConfig:
    """Configuration for a crew instance."""
    crew_id: str = field(default_factory=lambda: str(uuid4()))
    crew_type: str = ""  # brand, rmn, campaign, channel, scenario
    desired_outcome: DesiredOutcome = DesiredOutcome.INCREASE_REVENUE
    
    # Filters
    brand_ids: List[str] = field(default_factory=list)
    rmn_ids: List[str] = field(default_factory=list)
    channel_ids: List[str] = field(default_factory=list)
    campaign_ids: List[str] = field(default_factory=list)
    
    # Time window
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    
    # Constraints
    constraints: OptimizationConstraints = field(default_factory=OptimizationConstraints)
    
    # Execution settings
    max_iterations: int = 100
    convergence_threshold: float = 0.001
    include_sub_crews: bool = True
    verbose: bool = False


@dataclass
class ScenarioConfig:
    """Configuration for a scenario optimization run."""
    scenario_id: str = field(default_factory=lambda: str(uuid4()))
    scenario_name: str = ""
    scenario_type: str = "optimization"  # optimization, what_if, stress_test
    
    desired_outcome: DesiredOutcome = DesiredOutcome.INCREASE_REVENUE
    base_crew_config: CrewConfig = field(default_factory=CrewConfig)
    
    # Scenario-specific parameters
    budget_delta_pct: float = 0.0  # % change from current
    target_revenue_delta_pct: float = 0.0
    target_margin_delta_pct: float = 0.0
    
    # What-if parameters
    channel_emphasis: Dict[str, float] = field(default_factory=dict)  # Weight multipliers
    rmn_emphasis: Dict[str, float] = field(default_factory=dict)
    
    # Comparison
    compare_to_baseline: bool = True
    compare_scenarios: List[str] = field(default_factory=list)


@dataclass
class AllocationRecommendation:
    """Recommended spend allocation."""
    entity_type: str = ""  # brand, rmn, channel, campaign, message
    entity_id: str = ""
    entity_name: str = ""
    
    current_spend: float = 0.0
    recommended_spend: float = 0.0
    spend_delta: float = 0.0
    spend_delta_pct: float = 0.0
    
    expected_incremental_sales: float = 0.0
    expected_efficiency: float = 0.0
    expected_margin: Optional[float] = None
    
    confidence_level: float = 0.0
    rationale: str = ""
    actions: List[str] = field(default_factory=list)


@dataclass
class ImpactEstimate:
    """Estimated impact of recommendations."""
    metric_name: str = ""
    baseline_value: float = 0.0
    projected_value: float = 0.0
    delta: float = 0.0
    delta_pct: float = 0.0
    
    ci_lower: float = 0.0
    ci_upper: float = 0.0
    confidence: float = 0.0
    
    assumptions: List[str] = field(default_factory=list)
    sensitivities: Dict[str, float] = field(default_factory=dict)


@dataclass
class RiskAssessment:
    """Risk assessment for recommendations."""
    risk_id: str = field(default_factory=lambda: str(uuid4()))
    risk_type: str = ""  # execution, measurement, market, compliance
    description: str = ""
    probability: float = 0.0  # 0-1
    impact: str = "medium"  # low, medium, high
    mitigation: str = ""
    owner: str = ""


@dataclass 
class CrewOutput:
    """Standard output structure for all crews."""
    crew_id: str = ""
    crew_type: str = ""
    desired_outcome: str = ""
    
    # POV - Point of View
    executive_summary: str = ""
    key_findings: List[str] = field(default_factory=list)
    opportunities: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    
    # Recommendations
    allocations: List[AllocationRecommendation] = field(default_factory=list)
    total_recommended_spend: float = 0.0
    
    # Impact
    impact_estimates: List[ImpactEstimate] = field(default_factory=list)
    expected_incremental_sales: float = 0.0
    expected_efficiency: float = 0.0
    expected_margin: Optional[float] = None
    
    # Risk & Governance
    risk_assessments: List[RiskAssessment] = field(default_factory=list)
    constraints_satisfied: bool = True
    constraint_violations: List[str] = field(default_factory=list)
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    execution_time_seconds: float = 0.0
    model_version: str = "1.0.0"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "crew_id": self.crew_id,
            "crew_type": self.crew_type,
            "desired_outcome": self.desired_outcome,
            "executive_summary": self.executive_summary,
            "key_findings": self.key_findings,
            "opportunities": self.opportunities,
            "risks": self.risks,
            "allocations": [
                {
                    "entity_type": a.entity_type,
                    "entity_id": a.entity_id,
                    "entity_name": a.entity_name,
                    "current_spend": a.current_spend,
                    "recommended_spend": a.recommended_spend,
                    "spend_delta": a.spend_delta,
                    "spend_delta_pct": a.spend_delta_pct,
                    "expected_incremental_sales": a.expected_incremental_sales,
                    "expected_efficiency": a.expected_efficiency,
                    "rationale": a.rationale,
                    "actions": a.actions,
                }
                for a in self.allocations
            ],
            "total_recommended_spend": self.total_recommended_spend,
            "expected_incremental_sales": self.expected_incremental_sales,
            "expected_efficiency": self.expected_efficiency,
            "constraints_satisfied": self.constraints_satisfied,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class OptimizationResult:
    """Result of optimization solve."""
    success: bool = False
    objective_value: float = 0.0
    allocation: Dict[str, float] = field(default_factory=dict)
    
    iterations: int = 0
    convergence_achieved: bool = False
    
    shadow_prices: Dict[str, float] = field(default_factory=dict)  # Constraint sensitivity
    binding_constraints: List[str] = field(default_factory=list)
    
    solve_time_seconds: float = 0.0
    solver_status: str = ""
    solver_message: str = ""
