"""
Retail Media Optimization Data Schemas

Defines data contracts for the retail media spend optimization system.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, date
from enum import Enum
import numpy as np


class MediaChannel(Enum):
    """Supported retail media channels"""
    SPONSORED_SEARCH = "sponsored_search"
    IN_STORE_DISPLAY = "in_store_display"
    CONNECTED_TV = "connected_tv"
    EMAIL = "email"
    APP_NOTIFICATION = "app_notification"
    WEBSITE_BANNER = "website_banner"
    SOCIAL_MEDIA = "social_media"
    DIGITAL_ENDCAP = "digital_endcap"


class AllocationStatus(Enum):
    """Status of media allocation"""
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    ACTIVE = "active"
    COMPLETED = "completed"


class GovernanceStatus(Enum):
    """Governance check status"""
    PASSED = "passed"
    FAILED = "failed"
    REQUIRES_REVIEW = "requires_review"


@dataclass
class RetailerConfig:
    """Configuration for a retail media network partner"""
    retailer_id: str
    retailer_name: str
    
    # Channel availability
    available_channels: List[MediaChannel] = field(default_factory=list)
    
    # Spend constraints
    min_quarterly_spend: float = 0.0
    max_quarterly_spend: float = float('inf')
    min_spend_share: float = 0.0  # Minimum share of total budget
    
    # Inventory characteristics
    avg_inventory_weeks: float = 4.0
    stockout_sensitivity: float = 1.0  # Multiplier for stockout cost
    
    # Relationship tier
    tier: str = "standard"  # premium, standard, emerging
    
    # Measurement quality
    attribution_quality: float = 0.8  # 0-1 scale of data quality
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'retailer_id': self.retailer_id,
            'retailer_name': self.retailer_name,
            'available_channels': [c.value for c in self.available_channels],
            'min_quarterly_spend': self.min_quarterly_spend,
            'max_quarterly_spend': self.max_quarterly_spend,
            'min_spend_share': self.min_spend_share,
            'avg_inventory_weeks': self.avg_inventory_weeks,
            'stockout_sensitivity': self.stockout_sensitivity,
            'tier': self.tier,
            'attribution_quality': self.attribution_quality,
        }


@dataclass
class ChannelConfig:
    """Configuration for a media channel"""
    channel: MediaChannel
    
    # Cost parameters
    min_spend: float = 0.0
    max_spend: float = float('inf')
    cpm: float = 10.0  # Cost per thousand impressions
    
    # Effectiveness priors
    prior_elasticity_mean: float = 0.15
    prior_elasticity_std: float = 0.05
    
    # Adstock parameters (carryover effects)
    adstock_decay: float = 0.7  # Weekly decay rate
    adstock_max_weeks: int = 4
    
    # Measurement
    has_incrementality_test: bool = False
    measurement_lag_days: int = 14
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'channel': self.channel.value,
            'min_spend': self.min_spend,
            'max_spend': self.max_spend,
            'cpm': self.cpm,
            'prior_elasticity_mean': self.prior_elasticity_mean,
            'prior_elasticity_std': self.prior_elasticity_std,
            'adstock_decay': self.adstock_decay,
            'adstock_max_weeks': self.adstock_max_weeks,
            'has_incrementality_test': self.has_incrementality_test,
            'measurement_lag_days': self.measurement_lag_days,
        }


@dataclass
class SKUConfig:
    """Configuration for a SKU/product"""
    sku_id: str
    sku_name: str
    category: str
    brand: str
    
    # Economics
    unit_price: float
    unit_cost: float
    margin: float = 0.0  # Computed from price - cost
    
    # Inventory parameters
    weekly_base_demand: float = 100.0
    demand_std: float = 20.0
    lead_time_weeks: int = 2
    
    # Media responsiveness
    media_responsiveness: float = 1.0  # Multiplier on category elasticity
    
    def __post_init__(self):
        if self.margin == 0.0:
            self.margin = self.unit_price - self.unit_cost
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'sku_id': self.sku_id,
            'sku_name': self.sku_name,
            'category': self.category,
            'brand': self.brand,
            'unit_price': self.unit_price,
            'unit_cost': self.unit_cost,
            'margin': self.margin,
            'weekly_base_demand': self.weekly_base_demand,
            'demand_std': self.demand_std,
            'lead_time_weeks': self.lead_time_weeks,
            'media_responsiveness': self.media_responsiveness,
        }


@dataclass
class ElasticityPosterior:
    """Posterior distribution for channel elasticity"""
    retailer_id: str
    channel: MediaChannel
    category: str
    
    # Posterior parameters (LogNormal)
    mean: float
    std: float
    ci_lower: float  # 5th percentile
    ci_upper: float  # 95th percentile
    
    # Evidence strength
    n_observations: int = 0
    evidence_strength: float = 0.5  # 0-1, higher = more confident
    
    # Model version
    model_version: str = "v1.0.0"
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def sample(self, n_samples: int) -> np.ndarray:
        """Sample from the posterior distribution"""
        # Use LogNormal for elasticity (always positive)
        mu = np.log(self.mean) - 0.5 * (self.std / self.mean) ** 2
        sigma = np.sqrt(np.log(1 + (self.std / self.mean) ** 2))
        return np.random.lognormal(mu, sigma, n_samples)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'retailer_id': self.retailer_id,
            'channel': self.channel.value,
            'category': self.category,
            'mean': self.mean,
            'std': self.std,
            'ci_lower': self.ci_lower,
            'ci_upper': self.ci_upper,
            'n_observations': self.n_observations,
            'evidence_strength': self.evidence_strength,
            'model_version': self.model_version,
            'updated_at': self.updated_at.isoformat(),
        }


@dataclass
class AttributionResult:
    """Result of multi-touch attribution analysis"""
    period_start: date
    period_end: date
    
    # Channel contributions (Dirichlet posterior)
    channel_shares: Dict[str, float]  # channel -> share of lift
    channel_share_ci: Dict[str, Tuple[float, float]]  # channel -> (lower, upper)
    
    # Total metrics
    total_incremental_sales: float
    total_spend: float
    overall_roas: float
    
    # Confidence
    attribution_confidence: float  # 0-1
    
    # Anomalies detected
    anomalies: List[Dict[str, Any]] = field(default_factory=list)
    
    model_version: str = "v1.0.0"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'period_start': self.period_start.isoformat(),
            'period_end': self.period_end.isoformat(),
            'channel_shares': self.channel_shares,
            'channel_share_ci': {k: list(v) for k, v in self.channel_share_ci.items()},
            'total_incremental_sales': self.total_incremental_sales,
            'total_spend': self.total_spend,
            'overall_roas': self.overall_roas,
            'attribution_confidence': self.attribution_confidence,
            'anomalies': self.anomalies,
            'model_version': self.model_version,
        }


@dataclass
class RetailerSKUState:
    """State vector for a retailer-SKU combination in the Digital Twin"""
    retailer_id: str
    sku_id: str
    week: int
    
    # Demand state (from Bayesian posteriors)
    base_demand_mean: float
    base_demand_std: float
    
    # Media state
    media_spend_by_channel: Dict[str, float] = field(default_factory=dict)
    cumulative_media_effect: float = 0.0  # Adstock carryover
    
    # Inventory state
    on_hand_inventory: float = 0.0
    on_order: float = 0.0
    lead_time_weeks: int = 2
    reorder_point: float = 0.0
    
    # Elasticity beliefs (posterior means)
    elasticity_by_channel: Dict[str, float] = field(default_factory=dict)
    elasticity_uncertainty: Dict[str, float] = field(default_factory=dict)
    
    # Cross-retailer effects
    cannibalization_factor: float = 0.0
    halo_factor: float = 0.0
    
    # Computed metrics (updated during simulation)
    fulfilled_demand: float = 0.0
    stockout_units: float = 0.0
    revenue: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'retailer_id': self.retailer_id,
            'sku_id': self.sku_id,
            'week': self.week,
            'base_demand_mean': self.base_demand_mean,
            'base_demand_std': self.base_demand_std,
            'media_spend_by_channel': self.media_spend_by_channel,
            'cumulative_media_effect': self.cumulative_media_effect,
            'on_hand_inventory': self.on_hand_inventory,
            'on_order': self.on_order,
            'lead_time_weeks': self.lead_time_weeks,
            'reorder_point': self.reorder_point,
            'elasticity_by_channel': self.elasticity_by_channel,
            'elasticity_uncertainty': self.elasticity_uncertainty,
            'cannibalization_factor': self.cannibalization_factor,
            'halo_factor': self.halo_factor,
            'fulfilled_demand': self.fulfilled_demand,
            'stockout_units': self.stockout_units,
            'revenue': self.revenue,
        }


@dataclass
class MediaAllocation:
    """A media spend allocation plan"""
    allocation_id: str
    name: str
    
    # Budget
    total_budget: float
    period_weeks: int
    
    # Allocation by retailer and channel
    spend_by_retailer_channel: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # Format: {retailer_id: {channel: spend}}
    
    # Weekly breakdown (optional)
    weekly_spend: Optional[Dict[int, Dict[str, Dict[str, float]]]] = None
    # Format: {week: {retailer_id: {channel: spend}}}
    
    # Status
    status: AllocationStatus = AllocationStatus.DRAFT
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: str = "system"
    
    def get_retailer_total(self, retailer_id: str) -> float:
        """Get total spend for a retailer"""
        if retailer_id in self.spend_by_retailer_channel:
            return sum(self.spend_by_retailer_channel[retailer_id].values())
        return 0.0
    
    def get_channel_total(self, channel: str) -> float:
        """Get total spend for a channel across all retailers"""
        total = 0.0
        for retailer_spend in self.spend_by_retailer_channel.values():
            total += retailer_spend.get(channel, 0.0)
        return total
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'allocation_id': self.allocation_id,
            'name': self.name,
            'total_budget': self.total_budget,
            'period_weeks': self.period_weeks,
            'spend_by_retailer_channel': self.spend_by_retailer_channel,
            'weekly_spend': self.weekly_spend,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'created_by': self.created_by,
        }


@dataclass
class MediaScenario:
    """A scenario for Digital Twin simulation"""
    scenario_id: str
    scenario_name: str
    description: str
    
    # Base allocation
    allocation: MediaAllocation
    
    # Scenario modifications
    demand_multiplier: float = 1.0
    supply_disruption: float = 0.0  # 0-1, fraction of supply lost
    elasticity_multiplier: float = 1.0
    
    # Competitor effects
    competitor_spend_change: float = 0.0  # -1 to +1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'scenario_id': self.scenario_id,
            'scenario_name': self.scenario_name,
            'description': self.description,
            'allocation': self.allocation.to_dict(),
            'demand_multiplier': self.demand_multiplier,
            'supply_disruption': self.supply_disruption,
            'elasticity_multiplier': self.elasticity_multiplier,
            'competitor_spend_change': self.competitor_spend_change,
        }


@dataclass
class MediaSimulationResult:
    """Result of Digital Twin simulation for a media scenario"""
    scenario_id: str
    scenario_name: str
    
    # Simulation parameters
    n_simulations: int
    simulation_weeks: int
    
    # KPI distributions (arrays of simulation results)
    incremental_sales_dist: List[float] = field(default_factory=list)
    stockout_rate_dist: List[float] = field(default_factory=list)
    roas_dist: List[float] = field(default_factory=list)
    inventory_cost_dist: List[float] = field(default_factory=list)
    
    # Summary statistics
    expected_incremental_sales: float = 0.0
    sales_ci_lower: float = 0.0
    sales_ci_upper: float = 0.0
    
    expected_stockout_rate: float = 0.0
    stockout_ci_lower: float = 0.0
    stockout_ci_upper: float = 0.0
    
    expected_roas: float = 0.0
    roas_ci_lower: float = 0.0
    roas_ci_upper: float = 0.0
    
    # Binding constraints
    binding_constraints: List[str] = field(default_factory=list)
    
    # Per-retailer breakdown
    retailer_results: Dict[str, Dict[str, float]] = field(default_factory=dict)
    
    def compute_summary_stats(self):
        """Compute summary statistics from distributions"""
        if self.incremental_sales_dist:
            self.expected_incremental_sales = float(np.mean(self.incremental_sales_dist))
            self.sales_ci_lower = float(np.percentile(self.incremental_sales_dist, 5))
            self.sales_ci_upper = float(np.percentile(self.incremental_sales_dist, 95))
        
        if self.stockout_rate_dist:
            self.expected_stockout_rate = float(np.mean(self.stockout_rate_dist))
            self.stockout_ci_lower = float(np.percentile(self.stockout_rate_dist, 5))
            self.stockout_ci_upper = float(np.percentile(self.stockout_rate_dist, 95))
        
        if self.roas_dist:
            self.expected_roas = float(np.mean(self.roas_dist))
            self.roas_ci_lower = float(np.percentile(self.roas_dist, 5))
            self.roas_ci_upper = float(np.percentile(self.roas_dist, 95))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'scenario_id': self.scenario_id,
            'scenario_name': self.scenario_name,
            'n_simulations': self.n_simulations,
            'simulation_weeks': self.simulation_weeks,
            'expected_incremental_sales': self.expected_incremental_sales,
            'sales_ci_lower': self.sales_ci_lower,
            'sales_ci_upper': self.sales_ci_upper,
            'expected_stockout_rate': self.expected_stockout_rate,
            'stockout_ci_lower': self.stockout_ci_lower,
            'stockout_ci_upper': self.stockout_ci_upper,
            'expected_roas': self.expected_roas,
            'roas_ci_lower': self.roas_ci_lower,
            'roas_ci_upper': self.roas_ci_upper,
            'binding_constraints': self.binding_constraints,
            'retailer_results': self.retailer_results,
        }


@dataclass
class ValidationCheck:
    """Result of a governance validation check"""
    rule_name: str
    passed: bool
    message: str
    severity: str = "warning"  # info, warning, error
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'rule_name': self.rule_name,
            'passed': self.passed,
            'message': self.message,
            'severity': self.severity,
        }


@dataclass
class GovernanceDecision:
    """Result of governance agent validation"""
    approved: bool
    status: GovernanceStatus
    checks: List[ValidationCheck] = field(default_factory=list)
    requires_human_approval: bool = False
    escalation_reason: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'approved': self.approved,
            'status': self.status.value,
            'checks': [c.to_dict() for c in self.checks],
            'requires_human_approval': self.requires_human_approval,
            'escalation_reason': self.escalation_reason,
            'reviewed_by': self.reviewed_by,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
        }


@dataclass
class MediaDecisionPack:
    """Complete decision pack output from the retail media optimization system"""
    pack_id: str
    created_at: datetime
    
    # Recommendation
    recommended_allocation: MediaAllocation
    
    # Bayesian analysis summary
    elasticity_posteriors: Dict[str, ElasticityPosterior] = field(default_factory=dict)
    attribution_result: Optional[AttributionResult] = None
    
    # Twin simulation results
    simulation_results: Dict[str, MediaSimulationResult] = field(default_factory=dict)
    scenario_comparison: Dict[str, Dict[str, float]] = field(default_factory=dict)
    
    # Governance
    governance_decision: Optional[GovernanceDecision] = None
    
    # Rationale (LLM-generated)
    executive_summary: str = ""
    detailed_rationale: str = ""
    uncertainty_acknowledgment: str = ""
    
    # Confidence metrics
    overall_confidence: float = 0.0
    data_quality_score: float = 0.0
    
    # Model versions
    bayesian_model_version: str = "v1.0.0"
    twin_model_version: str = "v1.0.0"
    agent_versions: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'pack_id': self.pack_id,
            'created_at': self.created_at.isoformat(),
            'recommended_allocation': self.recommended_allocation.to_dict(),
            'elasticity_posteriors': {k: v.to_dict() for k, v in self.elasticity_posteriors.items()},
            'attribution_result': self.attribution_result.to_dict() if self.attribution_result else None,
            'simulation_results': {k: v.to_dict() for k, v in self.simulation_results.items()},
            'scenario_comparison': self.scenario_comparison,
            'governance_decision': self.governance_decision.to_dict() if self.governance_decision else None,
            'executive_summary': self.executive_summary,
            'detailed_rationale': self.detailed_rationale,
            'uncertainty_acknowledgment': self.uncertainty_acknowledgment,
            'overall_confidence': self.overall_confidence,
            'data_quality_score': self.data_quality_score,
            'bayesian_model_version': self.bayesian_model_version,
            'twin_model_version': self.twin_model_version,
            'agent_versions': self.agent_versions,
        }
