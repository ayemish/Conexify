"""
RMN (Retail Media Network) Optimization - Data Contracts

Defines all data structures for the RMN optimization ecosystem.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import json


class ChannelType(str, Enum):
    """Types of retail media channels"""
    SPONSORED_SEARCH = "sponsored_search"
    SPONSORED_PRODUCT = "sponsored_product"
    DISPLAY = "display"
    VIDEO = "video"
    EMAIL = "email"
    IN_STORE = "in_store"
    OFFSITE = "offsite"
    SOCIAL = "social"


class OptimizationObjective(str, Enum):
    """Optimization objectives"""
    MAXIMIZE_ROAS = "maximize_roas"
    MAXIMIZE_REVENUE = "maximize_revenue"
    MAXIMIZE_REACH = "maximize_reach"
    MINIMIZE_CPA = "minimize_cpa"
    BALANCED = "balanced"


@dataclass
class ChannelConfig:
    """Configuration for a media channel"""
    channel_id: str
    channel_type: ChannelType
    name: str
    
    # Spend constraints
    min_spend: float = 0.0
    max_spend: float = float('inf')
    min_share: float = 0.0
    max_share: float = 1.0
    
    # Prior beliefs
    prior_elasticity_mean: float = 0.15
    prior_elasticity_std: float = 0.05
    
    # Channel characteristics
    lag_days: int = 0
    carryover_rate: float = 0.0
    saturation_point: Optional[float] = None


@dataclass
class RMNConfig:
    """Configuration for RMN optimization"""
    retailer_id: str
    retailer_name: str
    
    # Channels
    channels: List[ChannelConfig] = field(default_factory=list)
    
    # Budget
    total_budget: float = 1000000.0
    budget_period_days: int = 30
    
    # Optimization settings
    objective: OptimizationObjective = OptimizationObjective.MAXIMIZE_ROAS
    risk_aversion: float = 0.3
    
    # Simulation settings
    n_simulations: int = 2000
    n_scenarios: int = 5
    
    # Governance thresholds
    max_budget_change_pct: float = 0.25
    min_confidence: float = 0.5
    
    # Output
    credible_interval: float = 0.90


@dataclass
class MediaSpendData:
    """Media spend and performance data"""
    channel_id: str
    date: date
    
    # Spend
    spend: float
    impressions: int = 0
    clicks: int = 0
    
    # Outcomes
    conversions: int = 0
    revenue: float = 0.0
    
    # Quality metrics
    ctr: float = 0.0
    cvr: float = 0.0
    cpc: float = 0.0
    cpa: float = 0.0
    roas: float = 0.0
    
    def compute_metrics(self):
        """Compute derived metrics"""
        if self.impressions > 0:
            self.ctr = self.clicks / self.impressions
        if self.clicks > 0:
            self.cvr = self.conversions / self.clicks
            self.cpc = self.spend / self.clicks
        if self.conversions > 0:
            self.cpa = self.spend / self.conversions
        if self.spend > 0:
            self.roas = self.revenue / self.spend


@dataclass
class ElasticityPosterior:
    """Bayesian posterior for channel elasticity"""
    channel_id: str
    
    # Posterior parameters
    mean: float
    std: float
    ci_lower: float
    ci_upper: float
    
    # Evidence
    n_observations: int = 0
    evidence_strength: float = 0.5
    
    # Prior
    prior_mean: float = 0.15
    prior_std: float = 0.05
    
    # Metadata
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "mean": self.mean,
            "std": self.std,
            "ci_lower": self.ci_lower,
            "ci_upper": self.ci_upper,
            "n_observations": self.n_observations,
            "evidence_strength": self.evidence_strength,
        }


@dataclass
class AttributionResult:
    """Multi-touch attribution results"""
    # Attribution shares
    channel_shares: Dict[str, float]  # channel_id -> share
    
    # Attributed values
    attributed_revenue: Dict[str, float]  # channel_id -> revenue
    attributed_conversions: Dict[str, float]  # channel_id -> conversions
    
    # Uncertainty (Dirichlet posterior)
    dirichlet_alpha: Dict[str, float]
    
    # Metadata
    total_revenue: float = 0.0
    total_conversions: int = 0
    n_paths: int = 0
    model_version: str = "dirichlet_v1"
    computed_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel_shares": self.channel_shares,
            "attributed_revenue": self.attributed_revenue,
            "total_revenue": self.total_revenue,
            "n_paths": self.n_paths,
        }


@dataclass
class AllocationScenario:
    """A budget allocation scenario"""
    scenario_id: str
    name: str
    description: str
    
    # Allocation
    allocation: Dict[str, float]  # channel_id -> spend
    total_spend: float
    
    # Scenario modifiers
    demand_multiplier: float = 1.0
    elasticity_adjustment: float = 0.0
    
    # Tags
    scenario_type: str = "baseline"  # baseline, optimistic, conservative, stress_test
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "description": self.description,
            "allocation": self.allocation,
            "total_spend": self.total_spend,
            "scenario_type": self.scenario_type,
        }


@dataclass
class SimulationResult:
    """Results from Digital Twin simulation"""
    scenario_id: str
    scenario_name: str
    
    # KPI distributions
    expected_revenue: float
    revenue_std: float
    revenue_ci: Tuple[float, float]
    
    expected_roas: float
    roas_std: float
    roas_ci: Tuple[float, float]
    
    expected_conversions: float
    conversion_ci: Tuple[float, float]
    
    # Breakdown by channel
    channel_contributions: Dict[str, float]
    
    # Simulation metadata
    n_simulations: int
    total_spend: float
    simulated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "expected_revenue": self.expected_revenue,
            "revenue_ci": self.revenue_ci,
            "expected_roas": self.expected_roas,
            "total_spend": self.total_spend,
            "n_simulations": self.n_simulations,
        }


@dataclass
class OptimizationResult:
    """Results from budget optimization"""
    selected_scenario_id: str
    
    # Optimal allocation
    optimal_allocation: Dict[str, float]
    total_budget: float
    
    # Expected outcomes
    expected_revenue: float
    expected_roas: float
    expected_conversions: float
    
    # Optimization details
    objective_value: float
    risk_adjusted_score: float
    
    # All scenarios ranked
    scenario_rankings: List[Dict[str, Any]]
    
    # Metadata
    solver_status: str = "optimal"
    optimized_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_scenario_id": self.selected_scenario_id,
            "optimal_allocation": self.optimal_allocation,
            "total_budget": self.total_budget,
            "expected_revenue": self.expected_revenue,
            "expected_roas": self.expected_roas,
            "solver_status": self.solver_status,
        }


@dataclass
class GovernanceDecision:
    """Governance validation decision"""
    approved: bool
    requires_review: bool
    
    # Policy checks
    checks: List[Dict[str, Any]]
    violations: List[str]
    
    # Risk assessment
    risk_score: float = 0.0
    risk_factors: List[str] = field(default_factory=list)
    
    # Reviewer info
    auto_approved: bool = False
    reviewer_notes: str = ""
    
    validated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "requires_review": self.requires_review,
            "violations": self.violations,
            "risk_score": self.risk_score,
            "auto_approved": self.auto_approved,
        }


@dataclass
class RMNDecisionPack:
    """Complete RMN optimization decision package"""
    pack_id: str
    retailer_id: str
    created_at: datetime
    
    # Results
    attribution: AttributionResult
    elasticities: Dict[str, ElasticityPosterior]
    scenarios: List[AllocationScenario]
    simulations: Dict[str, SimulationResult]
    optimization: OptimizationResult
    governance: GovernanceDecision
    
    # Rationale
    executive_summary: str
    detailed_rationale: str
    uncertainty_acknowledgment: str
    
    # Status
    status: str = "completed"  # completed, pending_review, rejected
    confidence_score: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "retailer_id": self.retailer_id,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "confidence_score": self.confidence_score,
            "optimization": self.optimization.to_dict(),
            "governance": self.governance.to_dict(),
            "executive_summary": self.executive_summary[:500],
        }
    
    def save(self, path: str):
        """Save decision pack to JSON"""
        from pathlib import Path as PathLib
        PathLib(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
