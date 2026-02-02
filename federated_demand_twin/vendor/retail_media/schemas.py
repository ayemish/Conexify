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
    # Search & Discovery
    SPONSORED_SEARCH = "sponsored_search"
    SPONSORED_PRODUCTS = "sponsored_products"
    SPONSORED_BRANDS = "sponsored_brands"
    
    # Display Advertising
    DISPLAY_AD = "display_ad"
    WEBSITE_BANNER = "website_banner"
    DIGITAL_ENDCAP = "digital_endcap"
    IN_STORE_DISPLAY = "in_store_display"
    
    # Brand Destinations
    BRAND_STORE = "brand_store"
    BRAND_LANDING_PAGE = "brand_landing_page"
    
    # Direct Marketing
    EMAIL = "email"
    APP_NOTIFICATION = "app_notification"
    SMS = "sms"
    
    # Video & Connected
    CONNECTED_TV = "connected_tv"
    VIDEO_AD = "video_ad"
    STREAMING_AUDIO = "streaming_audio"
    
    # Social & Influencer
    SOCIAL_MEDIA = "social_media"
    INFLUENCER = "influencer"
    
    # Programmatic
    DSP = "dsp"  # Demand-side platform
    OFFSITE_DISPLAY = "offsite_display"


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
class ChannelDigitalTwinState:
    """State vector for a media channel in the Digital Twin"""
    channel: MediaChannel
    retailer_id: str
    week: int
    
    # Channel performance state
    impressions: float = 0.0
    clicks: float = 0.0
    conversions: float = 0.0
    spend: float = 0.0
    
    # Engagement metrics
    click_through_rate: float = 0.0  # CTR
    conversion_rate: float = 0.0
    cost_per_click: float = 0.0  # CPC
    cost_per_acquisition: float = 0.0  # CPA
    
    # Attribution state
    attributed_revenue: float = 0.0
    attributed_units: float = 0.0
    roas: float = 0.0
    
    # Adstock/carryover effects
    cumulative_adstock: float = 0.0
    adstock_decay_rate: float = 0.7
    
    # Channel-specific state
    audience_reach: float = 0.0
    frequency: float = 0.0  # Avg impressions per user
    viewability_rate: float = 0.0
    
    # Elasticity beliefs (from Bayesian posteriors)
    elasticity_mean: float = 0.15
    elasticity_std: float = 0.05
    
    # Budget state
    budget_utilization: float = 0.0  # % of allocated budget spent
    pacing_status: str = "on_track"  # on_track, under_pacing, over_pacing
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'channel': self.channel.value,
            'retailer_id': self.retailer_id,
            'week': self.week,
            'impressions': self.impressions,
            'clicks': self.clicks,
            'conversions': self.conversions,
            'spend': self.spend,
            'click_through_rate': self.click_through_rate,
            'conversion_rate': self.conversion_rate,
            'cost_per_click': self.cost_per_click,
            'cost_per_acquisition': self.cost_per_acquisition,
            'attributed_revenue': self.attributed_revenue,
            'attributed_units': self.attributed_units,
            'roas': self.roas,
            'cumulative_adstock': self.cumulative_adstock,
            'adstock_decay_rate': self.adstock_decay_rate,
            'audience_reach': self.audience_reach,
            'frequency': self.frequency,
            'viewability_rate': self.viewability_rate,
            'elasticity_mean': self.elasticity_mean,
            'elasticity_std': self.elasticity_std,
            'budget_utilization': self.budget_utilization,
            'pacing_status': self.pacing_status,
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
    
    # Media state by channel
    media_spend_by_channel: Dict[str, float] = field(default_factory=dict)
    cumulative_media_effect: float = 0.0  # Adstock carryover
    
    # Channel performance state (replaces inventory focus)
    channel_states: Dict[str, ChannelDigitalTwinState] = field(default_factory=dict)
    
    # Elasticity beliefs (posterior means)
    elasticity_by_channel: Dict[str, float] = field(default_factory=dict)
    elasticity_uncertainty: Dict[str, float] = field(default_factory=dict)
    
    # Cross-retailer effects
    cannibalization_factor: float = 0.0
    halo_factor: float = 0.0
    
    # Computed metrics (updated during simulation)
    total_impressions: float = 0.0
    total_conversions: float = 0.0
    revenue: float = 0.0
    incremental_revenue: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'retailer_id': self.retailer_id,
            'sku_id': self.sku_id,
            'week': self.week,
            'base_demand_mean': self.base_demand_mean,
            'base_demand_std': self.base_demand_std,
            'media_spend_by_channel': self.media_spend_by_channel,
            'cumulative_media_effect': self.cumulative_media_effect,
            'channel_states': {k: v.to_dict() for k, v in self.channel_states.items()},
            'elasticity_by_channel': self.elasticity_by_channel,
            'elasticity_uncertainty': self.elasticity_uncertainty,
            'cannibalization_factor': self.cannibalization_factor,
            'halo_factor': self.halo_factor,
            'total_impressions': self.total_impressions,
            'total_conversions': self.total_conversions,
            'revenue': self.revenue,
            'incremental_revenue': self.incremental_revenue,
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


class CollaborationType(Enum):
    """Types of agent collaboration"""
    DELEGATION = "delegation"
    INFORMATION_SHARING = "information_sharing"
    CONSENSUS_REQUEST = "consensus_request"
    VALIDATION_REQUEST = "validation_request"
    FEEDBACK_LOOP = "feedback_loop"
    NEGOTIATION = "negotiation"


@dataclass
class AgentCollaboration:
    """Record of an agent collaboration event during pipeline execution"""
    collaboration_id: str
    timestamp: datetime
    collaboration_type: CollaborationType
    initiator_agent: str
    target_agents: List[str]
    topic: str
    context: Dict[str, Any] = field(default_factory=dict)
    outcome: str = ""
    duration_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'collaboration_id': self.collaboration_id,
            'timestamp': self.timestamp.isoformat(),
            'type': self.collaboration_type.value,
            'initiator': self.initiator_agent,
            'targets': self.target_agents,
            'topic': self.topic,
            'context': self.context,
            'outcome': self.outcome,
            'duration_ms': self.duration_ms,
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
    
    # Agent collaboration events
    collaboration_events: List[AgentCollaboration] = field(default_factory=list)
    
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
            'collaboration_events': [e.to_dict() for e in self.collaboration_events],
            'bayesian_model_version': self.bayesian_model_version,
            'twin_model_version': self.twin_model_version,
            'agent_versions': self.agent_versions,
        }


# =============================================================================
# Manufacturer Product Digital Twin
# =============================================================================

@dataclass
class ManufacturerProductConfig:
    """Configuration for a manufacturer's product in the digital twin"""
    manufacturer_id: str
    manufacturer_name: str
    product_id: str
    product_name: str
    brand: str
    category: str
    
    # Product economics
    msrp: float
    wholesale_price: float
    margin_to_retailer: float = 0.0
    
    # Media investment parameters
    total_media_budget: float = 0.0
    preferred_channels: List[MediaChannel] = field(default_factory=list)
    
    # Target retailers
    target_retailers: List[str] = field(default_factory=list)
    retailer_priority: Dict[str, int] = field(default_factory=dict)  # retailer_id -> priority (1=highest)
    
    # Product characteristics
    seasonality_pattern: str = "stable"  # stable, seasonal, promotional
    launch_date: Optional[date] = None
    lifecycle_stage: str = "growth"  # launch, growth, mature, decline
    
    def __post_init__(self):
        if self.margin_to_retailer == 0.0:
            self.margin_to_retailer = self.msrp - self.wholesale_price
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'manufacturer_id': self.manufacturer_id,
            'manufacturer_name': self.manufacturer_name,
            'product_id': self.product_id,
            'product_name': self.product_name,
            'brand': self.brand,
            'category': self.category,
            'msrp': self.msrp,
            'wholesale_price': self.wholesale_price,
            'margin_to_retailer': self.margin_to_retailer,
            'total_media_budget': self.total_media_budget,
            'preferred_channels': [c.value for c in self.preferred_channels],
            'target_retailers': self.target_retailers,
            'retailer_priority': self.retailer_priority,
            'seasonality_pattern': self.seasonality_pattern,
            'launch_date': self.launch_date.isoformat() if self.launch_date else None,
            'lifecycle_stage': self.lifecycle_stage,
        }


@dataclass
class ManufacturerChannelState:
    """State for a manufacturer's product performance in a specific channel"""
    channel: MediaChannel
    week: int
    
    # Spend and reach
    spend: float = 0.0
    impressions: float = 0.0
    reach: float = 0.0
    frequency: float = 0.0
    
    # Engagement metrics
    clicks: float = 0.0
    click_through_rate: float = 0.0
    video_views: float = 0.0
    video_completion_rate: float = 0.0
    
    # Conversion metrics
    add_to_carts: float = 0.0
    purchases: float = 0.0
    conversion_rate: float = 0.0
    
    # Revenue attribution
    attributed_sales: float = 0.0
    attributed_units: float = 0.0
    roas: float = 0.0
    
    # Brand metrics
    brand_search_lift: float = 0.0
    new_to_brand_percentage: float = 0.0
    
    # Efficiency metrics
    cost_per_click: float = 0.0
    cost_per_acquisition: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'channel': self.channel.value,
            'week': self.week,
            'spend': self.spend,
            'impressions': self.impressions,
            'reach': self.reach,
            'frequency': self.frequency,
            'clicks': self.clicks,
            'click_through_rate': self.click_through_rate,
            'video_views': self.video_views,
            'video_completion_rate': self.video_completion_rate,
            'add_to_carts': self.add_to_carts,
            'purchases': self.purchases,
            'conversion_rate': self.conversion_rate,
            'attributed_sales': self.attributed_sales,
            'attributed_units': self.attributed_units,
            'roas': self.roas,
            'brand_search_lift': self.brand_search_lift,
            'new_to_brand_percentage': self.new_to_brand_percentage,
            'cost_per_click': self.cost_per_click,
            'cost_per_acquisition': self.cost_per_acquisition,
        }


@dataclass
class ManufacturerRetailerState:
    """State for a manufacturer's product at a specific retailer"""
    retailer_id: str
    week: int
    
    # Channel states at this retailer
    channel_states: Dict[str, ManufacturerChannelState] = field(default_factory=dict)
    
    # Aggregate retailer metrics
    total_spend: float = 0.0
    total_impressions: float = 0.0
    total_conversions: float = 0.0
    total_revenue: float = 0.0
    
    # Share metrics
    share_of_voice: float = 0.0  # % of category impressions
    share_of_shelf: float = 0.0  # Digital shelf presence
    share_of_search: float = 0.0  # % of search impressions
    
    # Competitive position
    category_rank: int = 0
    price_index: float = 1.0  # vs category average
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'retailer_id': self.retailer_id,
            'week': self.week,
            'channel_states': {k: v.to_dict() for k, v in self.channel_states.items()},
            'total_spend': self.total_spend,
            'total_impressions': self.total_impressions,
            'total_conversions': self.total_conversions,
            'total_revenue': self.total_revenue,
            'share_of_voice': self.share_of_voice,
            'share_of_shelf': self.share_of_shelf,
            'share_of_search': self.share_of_search,
            'category_rank': self.category_rank,
            'price_index': self.price_index,
        }


@dataclass
class ManufacturerProductState:
    """
    Digital Twin state for a manufacturer's product across all retailers and channels.
    
    This represents the manufacturer's view of their product performance,
    aggregating data across all retail media networks.
    """
    manufacturer_id: str
    product_id: str
    week: int
    
    # Configuration
    config: Optional[ManufacturerProductConfig] = None
    
    # State by retailer
    retailer_states: Dict[str, ManufacturerRetailerState] = field(default_factory=dict)
    
    # Aggregate metrics across all retailers
    total_media_spend: float = 0.0
    total_impressions: float = 0.0
    total_conversions: float = 0.0
    total_revenue: float = 0.0
    overall_roas: float = 0.0
    
    # Channel mix (% of spend by channel)
    channel_mix: Dict[str, float] = field(default_factory=dict)
    
    # Retailer mix (% of spend by retailer)
    retailer_mix: Dict[str, float] = field(default_factory=dict)
    
    # Elasticity beliefs by channel (from Bayesian posteriors)
    channel_elasticities: Dict[str, float] = field(default_factory=dict)
    channel_elasticity_uncertainty: Dict[str, float] = field(default_factory=dict)
    
    # Cross-retailer effects
    retailer_synergy_factor: float = 0.0  # Positive = synergy, Negative = cannibalization
    
    # Brand health metrics
    brand_awareness_index: float = 0.0
    brand_consideration_index: float = 0.0
    brand_loyalty_index: float = 0.0
    
    # Simulation state
    cumulative_adstock: Dict[str, float] = field(default_factory=dict)  # channel -> adstock
    
    def aggregate_from_retailers(self):
        """Compute aggregate metrics from retailer states"""
        self.total_media_spend = 0.0
        self.total_impressions = 0.0
        self.total_conversions = 0.0
        self.total_revenue = 0.0
        
        channel_spend = {}
        retailer_spend = {}
        
        for retailer_id, state in self.retailer_states.items():
            self.total_media_spend += state.total_spend
            self.total_impressions += state.total_impressions
            self.total_conversions += state.total_conversions
            self.total_revenue += state.total_revenue
            
            retailer_spend[retailer_id] = state.total_spend
            
            for channel, ch_state in state.channel_states.items():
                channel_spend[channel] = channel_spend.get(channel, 0.0) + ch_state.spend
        
        # Compute mixes
        if self.total_media_spend > 0:
            self.channel_mix = {k: v / self.total_media_spend for k, v in channel_spend.items()}
            self.retailer_mix = {k: v / self.total_media_spend for k, v in retailer_spend.items()}
            self.overall_roas = self.total_revenue / self.total_media_spend
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'manufacturer_id': self.manufacturer_id,
            'product_id': self.product_id,
            'week': self.week,
            'config': self.config.to_dict() if self.config else None,
            'retailer_states': {k: v.to_dict() for k, v in self.retailer_states.items()},
            'total_media_spend': self.total_media_spend,
            'total_impressions': self.total_impressions,
            'total_conversions': self.total_conversions,
            'total_revenue': self.total_revenue,
            'overall_roas': self.overall_roas,
            'channel_mix': self.channel_mix,
            'retailer_mix': self.retailer_mix,
            'channel_elasticities': self.channel_elasticities,
            'channel_elasticity_uncertainty': self.channel_elasticity_uncertainty,
            'retailer_synergy_factor': self.retailer_synergy_factor,
            'brand_awareness_index': self.brand_awareness_index,
            'brand_consideration_index': self.brand_consideration_index,
            'brand_loyalty_index': self.brand_loyalty_index,
            'cumulative_adstock': self.cumulative_adstock,
        }


@dataclass
class ManufacturerSimulationResult:
    """Result of Digital Twin simulation for a manufacturer's product"""
    manufacturer_id: str
    product_id: str
    scenario_name: str
    
    # Simulation parameters
    n_simulations: int
    simulation_weeks: int
    
    # KPI distributions
    total_revenue_dist: List[float] = field(default_factory=list)
    roas_dist: List[float] = field(default_factory=list)
    market_share_dist: List[float] = field(default_factory=list)
    
    # Summary statistics
    expected_revenue: float = 0.0
    revenue_ci_lower: float = 0.0
    revenue_ci_upper: float = 0.0
    
    expected_roas: float = 0.0
    roas_ci_lower: float = 0.0
    roas_ci_upper: float = 0.0
    
    # Per-retailer breakdown
    retailer_results: Dict[str, Dict[str, float]] = field(default_factory=dict)
    
    # Per-channel breakdown
    channel_results: Dict[str, Dict[str, float]] = field(default_factory=dict)
    
    # Optimization recommendations
    recommended_channel_mix: Dict[str, float] = field(default_factory=dict)
    recommended_retailer_mix: Dict[str, float] = field(default_factory=dict)
    
    def compute_summary_stats(self):
        """Compute summary statistics from distributions"""
        if self.total_revenue_dist:
            self.expected_revenue = float(np.mean(self.total_revenue_dist))
            self.revenue_ci_lower = float(np.percentile(self.total_revenue_dist, 5))
            self.revenue_ci_upper = float(np.percentile(self.total_revenue_dist, 95))
        
        if self.roas_dist:
            self.expected_roas = float(np.mean(self.roas_dist))
            self.roas_ci_lower = float(np.percentile(self.roas_dist, 5))
            self.roas_ci_upper = float(np.percentile(self.roas_dist, 95))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'manufacturer_id': self.manufacturer_id,
            'product_id': self.product_id,
            'scenario_name': self.scenario_name,
            'n_simulations': self.n_simulations,
            'simulation_weeks': self.simulation_weeks,
            'expected_revenue': self.expected_revenue,
            'revenue_ci_lower': self.revenue_ci_lower,
            'revenue_ci_upper': self.revenue_ci_upper,
            'expected_roas': self.expected_roas,
            'roas_ci_lower': self.roas_ci_lower,
            'roas_ci_upper': self.roas_ci_upper,
            'retailer_results': self.retailer_results,
            'channel_results': self.channel_results,
            'recommended_channel_mix': self.recommended_channel_mix,
            'recommended_retailer_mix': self.recommended_retailer_mix,
        }
