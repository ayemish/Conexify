"""
RMN Digital Twin Schemas for Retail Media Network Spend Optimization

This module defines the core digital twin entities, dimensions, and fact tables
for modeling retail media network performance and optimization.

Hierarchy:
- CompanyTwin (top-level, e.g., Kellogg's)
  └── BrandTwin (e.g., Frosted Flakes, Pop-Tarts)
      └── BrandRMNProgramTwin (bridge: Brand × RetailMediaNetwork)
          └── ChannelTwin (search, display, video, email per RMN)
              └── CampaignTwin
                  └── MessageTwin

- RetailMediaNetworkTwin (Walmart, Target, Amazon, etc.)
  └── ChannelTwin (linked via BrandRMNProgramTwin)

Dimensions:
- TimePeriodDim, MetricDim, BaselineDim, SpendCategoryDim, TacticDriverDim, OptimizationScenarioDim

Facts:
- PerformanceObservationFact (raw observation grain)
- RMNPerformanceFact (aggregated performance by scenario)
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import uuid4


# =============================================================================
# Base Types
# =============================================================================

def generate_id() -> str:
    """Generate a unique ID."""
    return str(uuid4())


class LifecycleStage(Enum):
    """Brand lifecycle stages."""
    LAUNCH = "launch"
    GROWTH = "growth"
    MATURE = "mature"
    DECLINE = "decline"


class RMNType(Enum):
    """Retail Media Network types."""
    RETAILER = "retailer"
    MARKETPLACE = "marketplace"
    ROLLUP = "rollup"


class ChannelType(Enum):
    """RMN Channel types."""
    SEARCH = "search"
    DISPLAY = "display"
    VIDEO = "video"
    EMAIL = "email"
    OTHER = "other"


class BillingModel(Enum):
    """Billing models for RMN programs."""
    CPC = "CPC"
    CPM = "CPM"
    CPA = "CPA"
    FLAT = "flat"


class PacingMode(Enum):
    """Campaign pacing modes."""
    EVEN = "even"
    FRONTLOAD = "frontload"
    BACKLOAD = "backload"


class CampaignStatus(Enum):
    """Campaign status."""
    DRAFT = "draft"
    LIVE = "live"
    PAUSED = "paused"
    ENDED = "ended"


class CreativeType(Enum):
    """Message creative types."""
    STATIC = "static"
    VIDEO = "video"
    HTML = "html"
    EMAIL = "email"


class TimeGrain(Enum):
    """Time period granularity."""
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


class SpendCategoryType(Enum):
    """Spend category types."""
    PAID_MEDIA = "paid_media"
    PROMO = "promo"
    RMN = "rmn"
    TRADE = "trade"
    ENV = "env"


class ScenarioObjective(Enum):
    """Optimization scenario objectives."""
    INCREASE_REVENUE = "increase_revenue"
    INCREASE_MARGIN = "increase_margin"
    MAINTAIN_REVENUE = "maintain_revenue"
    REDUCE_COST = "reduce_cost"


# =============================================================================
# Core Twin Entities
# =============================================================================

@dataclass
class CompanyTwin:
    """Top-level company entity (e.g., Kellogg's)."""
    company_id: str = field(default_factory=generate_id)
    company_name: str = ""
    company_code: Optional[str] = None
    industry: Optional[str] = None
    country: str = "US"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True


@dataclass
class BrandTwin:
    """
    Brand entity representing a product brand within a company.
    
    PK: brand_id
    FK: company_id -> CompanyTwin.company_id
    
    Bayesian outputs supported:
    - sales_baseline_posterior, sales_actual_posterior, sales_lift_posterior
    - driver attribution posteriors (by hierarchy1/hierarchy2)
    - incremental_sales_posterior, efficiency_posterior, index_posterior
    - elasticity_posteriors per channel
    """
    brand_id: str = field(default_factory=generate_id)
    company_id: str = ""
    brand_name: str = ""
    brand_code: Optional[str] = None
    category: Optional[str] = None
    default_margin_rate: Optional[float] = None
    lifecycle_stage: Optional[str] = None  # growth|mature|decline
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True
    
    # Bayesian posterior outputs (populated by Bayesian engine)
    bayesian_state_id: Optional[str] = None  # FK to EntityBayesianState
    incremental_sales_posterior_mean: Optional[float] = None
    incremental_sales_posterior_std: Optional[float] = None
    incremental_sales_ci_lower: Optional[float] = None
    incremental_sales_ci_upper: Optional[float] = None
    efficiency_posterior_mean: Optional[float] = None
    efficiency_posterior_std: Optional[float] = None
    index_posterior_mean: Optional[float] = None
    lift_vs_prior_period_mean: Optional[float] = None
    lift_vs_year_ago_mean: Optional[float] = None
    prob_positive_lift: Optional[float] = None
    bayesian_last_updated: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "brand_id": self.brand_id,
            "company_id": self.company_id,
            "brand_name": self.brand_name,
            "brand_code": self.brand_code,
            "category": self.category,
            "default_margin_rate": self.default_margin_rate,
            "lifecycle_stage": self.lifecycle_stage,
            "is_active": self.is_active,
            "bayesian_outputs": {
                "state_id": self.bayesian_state_id,
                "incremental_sales": {
                    "mean": self.incremental_sales_posterior_mean,
                    "std": self.incremental_sales_posterior_std,
                    "ci": [self.incremental_sales_ci_lower, self.incremental_sales_ci_upper],
                } if self.incremental_sales_posterior_mean else None,
                "efficiency_mean": self.efficiency_posterior_mean,
                "efficiency_std": self.efficiency_posterior_std,
                "index_mean": self.index_posterior_mean,
                "lift_vs_prior_period": self.lift_vs_prior_period_mean,
                "lift_vs_year_ago": self.lift_vs_year_ago_mean,
                "prob_positive_lift": self.prob_positive_lift,
                "last_updated": self.bayesian_last_updated.isoformat() if self.bayesian_last_updated else None,
            },
        }


@dataclass
class RetailMediaNetworkTwin:
    """
    Retail Media Network entity (e.g., Walmart Connect, Target Roundel).
    
    PK: rmn_id
    
    Bayesian outputs supported:
    - incremental_sales_posterior, efficiency_posterior, index_posterior
    - brand_mix_posteriors, channel_mix_posteriors
    - prob_best_overall, prob_best_for_brand
    - driver attribution posteriors
    """
    rmn_id: str = field(default_factory=generate_id)
    rmn_name: str = ""
    rmn_code: Optional[str] = None
    rmn_type: str = "retailer"  # retailer|marketplace|rollup
    is_rollup_node: bool = False  # true for 'Total US - MultiOutletC'
    country: str = "US"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True
    
    # Bayesian posterior outputs (populated by Bayesian engine)
    bayesian_state_id: Optional[str] = None
    incremental_sales_posterior_mean: Optional[float] = None
    incremental_sales_posterior_std: Optional[float] = None
    incremental_sales_ci_lower: Optional[float] = None
    incremental_sales_ci_upper: Optional[float] = None
    efficiency_posterior_mean: Optional[float] = None
    efficiency_posterior_std: Optional[float] = None
    index_posterior_mean: Optional[float] = None
    prob_best_overall: Optional[float] = None  # P(RMN is best overall)
    expected_rank: Optional[float] = None
    bayesian_last_updated: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "rmn_id": self.rmn_id,
            "rmn_name": self.rmn_name,
            "rmn_code": self.rmn_code,
            "rmn_type": self.rmn_type,
            "is_rollup_node": self.is_rollup_node,
            "country": self.country,
            "is_active": self.is_active,
            "bayesian_outputs": {
                "state_id": self.bayesian_state_id,
                "incremental_sales": {
                    "mean": self.incremental_sales_posterior_mean,
                    "std": self.incremental_sales_posterior_std,
                    "ci": [self.incremental_sales_ci_lower, self.incremental_sales_ci_upper],
                } if self.incremental_sales_posterior_mean else None,
                "efficiency_mean": self.efficiency_posterior_mean,
                "efficiency_std": self.efficiency_posterior_std,
                "index_mean": self.index_posterior_mean,
                "prob_best_overall": self.prob_best_overall,
                "expected_rank": self.expected_rank,
                "last_updated": self.bayesian_last_updated.isoformat() if self.bayesian_last_updated else None,
            },
        }


@dataclass
class BrandRMNProgramTwin:
    """
    Bridge entity linking a Brand to an RMN with program details.
    
    PK: brand_rmn_program_id
    FK: brand_id -> BrandTwin.brand_id
    FK: rmn_id -> RetailMediaNetworkTwin.rmn_id
    """
    brand_rmn_program_id: str = field(default_factory=generate_id)
    brand_id: str = ""
    rmn_id: str = ""
    program_name: Optional[str] = None
    contract_start: Optional[date] = None
    contract_end: Optional[date] = None
    billing_model: Optional[str] = None  # CPC|CPM|CPA|flat
    attribution_window_days: Optional[int] = None
    budget_owner: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "brand_rmn_program_id": self.brand_rmn_program_id,
            "brand_id": self.brand_id,
            "rmn_id": self.rmn_id,
            "program_name": self.program_name,
            "contract_start": self.contract_start.isoformat() if self.contract_start else None,
            "contract_end": self.contract_end.isoformat() if self.contract_end else None,
            "billing_model": self.billing_model,
            "attribution_window_days": self.attribution_window_days,
            "budget_owner": self.budget_owner,
            "is_active": self.is_active,
        }


@dataclass
class ChannelTwin:
    """
    Channel entity representing an RMN channel (search, display, video, email).
    
    PK: channel_id
    FK: rmn_id -> RetailMediaNetworkTwin.rmn_id
    FK: brand_rmn_program_id -> BrandRMNProgramTwin.brand_rmn_program_id
    
    Bayesian outputs supported:
    - incremental_sales_posterior, efficiency_posterior, index_posterior
    - elasticity_posterior
    - contribution_posterior, contribution_pct_posterior
    - variance_over_time_posterior
    - ranking within RMN and overall
    """
    channel_id: str = field(default_factory=generate_id)
    rmn_id: str = ""
    brand_rmn_program_id: str = ""
    channel_name: str = ""
    channel_type: str = "search"  # search|display|video|email|other
    objective_default: Optional[str] = None
    bidding_strategy_default: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True
    
    # Bayesian posterior outputs (populated by Bayesian engine)
    bayesian_state_id: Optional[str] = None
    incremental_sales_posterior_mean: Optional[float] = None
    incremental_sales_posterior_std: Optional[float] = None
    incremental_sales_ci_lower: Optional[float] = None
    incremental_sales_ci_upper: Optional[float] = None
    efficiency_posterior_mean: Optional[float] = None
    efficiency_posterior_std: Optional[float] = None
    index_posterior_mean: Optional[float] = None
    elasticity_posterior_mean: Optional[float] = None
    elasticity_posterior_std: Optional[float] = None
    elasticity_ci_lower: Optional[float] = None
    elasticity_ci_upper: Optional[float] = None
    contribution_posterior_mean: Optional[float] = None
    contribution_pct_posterior_mean: Optional[float] = None
    prob_efficiency_above_target: Optional[float] = None
    efficiency_target: Optional[float] = None
    prob_rank_1_within_rmn: Optional[float] = None
    expected_rank_within_rmn: Optional[float] = None
    bayesian_last_updated: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "rmn_id": self.rmn_id,
            "brand_rmn_program_id": self.brand_rmn_program_id,
            "channel_name": self.channel_name,
            "channel_type": self.channel_type,
            "objective_default": self.objective_default,
            "bidding_strategy_default": self.bidding_strategy_default,
            "is_active": self.is_active,
            "bayesian_outputs": {
                "state_id": self.bayesian_state_id,
                "incremental_sales": {
                    "mean": self.incremental_sales_posterior_mean,
                    "std": self.incremental_sales_posterior_std,
                    "ci": [self.incremental_sales_ci_lower, self.incremental_sales_ci_upper],
                } if self.incremental_sales_posterior_mean else None,
                "efficiency_mean": self.efficiency_posterior_mean,
                "efficiency_std": self.efficiency_posterior_std,
                "index_mean": self.index_posterior_mean,
                "elasticity": {
                    "mean": self.elasticity_posterior_mean,
                    "std": self.elasticity_posterior_std,
                    "ci": [self.elasticity_ci_lower, self.elasticity_ci_upper],
                } if self.elasticity_posterior_mean else None,
                "contribution_mean": self.contribution_posterior_mean,
                "contribution_pct_mean": self.contribution_pct_posterior_mean,
                "prob_efficiency_above_target": self.prob_efficiency_above_target,
                "efficiency_target": self.efficiency_target,
                "prob_rank_1_within_rmn": self.prob_rank_1_within_rmn,
                "expected_rank_within_rmn": self.expected_rank_within_rmn,
                "last_updated": self.bayesian_last_updated.isoformat() if self.bayesian_last_updated else None,
            },
        }


@dataclass
class CampaignTwin:
    """
    Campaign entity representing an advertising campaign.
    
    PK: campaign_id
    FK: channel_id -> ChannelTwin.channel_id
    FK: brand_rmn_program_id -> BrandRMNProgramTwin.brand_rmn_program_id
    """
    campaign_id: str = field(default_factory=generate_id)
    brand_rmn_program_id: str = ""
    channel_id: str = ""
    campaign_name: str = ""
    campaign_objective: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    budget_planned: Optional[float] = None
    pacing_mode: Optional[str] = None  # even|frontload|backload
    targeting_summary: Optional[str] = None
    status: str = "draft"  # draft|live|paused|ended
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "brand_rmn_program_id": self.brand_rmn_program_id,
            "channel_id": self.channel_id,
            "campaign_name": self.campaign_name,
            "campaign_objective": self.campaign_objective,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "budget_planned": self.budget_planned,
            "pacing_mode": self.pacing_mode,
            "targeting_summary": self.targeting_summary,
            "status": self.status,
        }


@dataclass
class MessageTwin:
    """
    Message/Creative entity representing ad creative content.
    
    PK: message_id
    FK: campaign_id -> CampaignTwin.campaign_id
    """
    message_id: str = field(default_factory=generate_id)
    campaign_id: str = ""
    message_name: str = ""
    creative_type: Optional[str] = None  # static|video|html|email
    offer_type: Optional[str] = None
    headline: Optional[str] = None
    cta: Optional[str] = None
    landing_url: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "campaign_id": self.campaign_id,
            "message_name": self.message_name,
            "creative_type": self.creative_type,
            "offer_type": self.offer_type,
            "headline": self.headline,
            "cta": self.cta,
            "landing_url": self.landing_url,
        }


# =============================================================================
# Dimension Tables
# =============================================================================

@dataclass
class TimePeriodDim:
    """
    Time period dimension for temporal analysis.
    
    PK: time_period_id
    """
    time_period_id: str = field(default_factory=generate_id)
    date: date = field(default_factory=date.today)
    period: Optional[str] = None  # e.g., 2024-P07
    quarter: Optional[str] = None
    half: Optional[str] = None
    calendar: Optional[str] = None  # e.g., 2024-CY
    grain: str = "week"  # day|week|month|quarter|year
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "time_period_id": self.time_period_id,
            "date": self.date.isoformat(),
            "period": self.period,
            "quarter": self.quarter,
            "half": self.half,
            "calendar": self.calendar,
            "grain": self.grain,
        }


@dataclass
class MetricDim:
    """
    Metric dimension defining measurement types.
    
    PK: metric_id
    """
    metric_id: str = field(default_factory=generate_id)
    metric_name: str = ""
    unit: Optional[str] = None  # USD|units
    is_primary: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "metric_name": self.metric_name,
            "unit": self.unit,
            "is_primary": self.is_primary,
        }


@dataclass
class BaselineDim:
    """
    Baseline dimension for measurement context.
    
    PK: baseline_id
    """
    baseline_id: str = field(default_factory=generate_id)
    measurement_name: str = ""
    description: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "baseline_id": self.baseline_id,
            "measurement_name": self.measurement_name,
            "description": self.description,
        }


@dataclass
class SpendCategoryDim:
    """
    Spend category dimension (hierarchy1).
    
    PK: spend_category_id
    """
    spend_category_id: str = field(default_factory=generate_id)
    spend_category_name: str = ""
    spend_category_type: Optional[str] = None  # paid_media|promo|rmn|trade|env
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "spend_category_id": self.spend_category_id,
            "spend_category_name": self.spend_category_name,
            "spend_category_type": self.spend_category_type,
        }


@dataclass
class TacticDriverDim:
    """
    Tactic/Driver dimension (hierarchy2).
    
    PK: tactic_driver_id
    FK: spend_category_id -> SpendCategoryDim.spend_category_id
    """
    tactic_driver_id: str = field(default_factory=generate_id)
    spend_category_id: str = ""
    tactic_driver_name: str = ""
    is_rmn_channel: bool = False  # true when spend_category == 'RETAIL MEDIA' and starts with 'RMN '
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "tactic_driver_id": self.tactic_driver_id,
            "spend_category_id": self.spend_category_id,
            "tactic_driver_name": self.tactic_driver_name,
            "is_rmn_channel": self.is_rmn_channel,
        }


@dataclass
class OptimizationScenarioDim:
    """
    Optimization scenario dimension for what-if analysis.
    
    PK: scenario_id
    """
    scenario_id: str = field(default_factory=generate_id)
    scenario_name: str = ""  # current|optimized|what_if
    objective: Optional[str] = None  # increase_revenue|increase_margin|maintain_revenue|reduce_cost
    constraints_json: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "objective": self.objective,
            "constraints_json": self.constraints_json,
        }


# =============================================================================
# Fact Tables
# =============================================================================

@dataclass
class PerformanceObservationFact:
    """
    Raw performance observation fact table.
    
    Grain: Brand x RMN(geography) x Time x Metric x Baseline x SpendCategory x TacticDriver
    
    PK: observation_id
    FKs: brand_id, rmn_id, time_period_id, metric_id, baseline_id, spend_category_id, tactic_driver_id
    """
    observation_id: str = field(default_factory=generate_id)
    brand_id: str = ""
    rmn_id: str = ""
    time_period_id: str = ""
    metric_id: str = ""
    baseline_id: str = ""
    spend_category_id: str = ""
    tactic_driver_id: str = ""
    prior: Optional[float] = None
    current: Optional[float] = None
    dueto: Optional[float] = None  # driver contribution
    dueto_pct: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "brand_id": self.brand_id,
            "rmn_id": self.rmn_id,
            "time_period_id": self.time_period_id,
            "metric_id": self.metric_id,
            "baseline_id": self.baseline_id,
            "spend_category_id": self.spend_category_id,
            "tactic_driver_id": self.tactic_driver_id,
            "prior": self.prior,
            "current": self.current,
            "dueto": self.dueto,
            "dueto_pct": self.dueto_pct,
        }


@dataclass
class RMNPerformanceFact:
    """
    Aggregated RMN performance fact table for optimization scenarios.
    
    Grain: Brand x RMN x Channel x Scenario x Time
    
    PK: rmn_perf_id
    FKs: brand_id, rmn_id, channel_id, scenario_id, time_period_id
    """
    rmn_perf_id: str = field(default_factory=generate_id)
    brand_id: str = ""
    rmn_id: str = ""
    channel_id: Optional[str] = None
    scenario_id: str = ""
    time_period_id: Optional[str] = None
    spend: Optional[float] = None
    incremental_sales: Optional[float] = None
    efficiency: Optional[float] = None  # incremental_sales / spend
    index: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "rmn_perf_id": self.rmn_perf_id,
            "brand_id": self.brand_id,
            "rmn_id": self.rmn_id,
            "channel_id": self.channel_id,
            "scenario_id": self.scenario_id,
            "time_period_id": self.time_period_id,
            "spend": self.spend,
            "incremental_sales": self.incremental_sales,
            "efficiency": self.efficiency,
            "index": self.index,
        }


# =============================================================================
# Aggregated State Classes for Digital Twin Runtime
# =============================================================================

@dataclass
class BrandRMNState:
    """
    Runtime state for a Brand's RMN program, aggregating performance data.
    """
    brand: BrandTwin
    rmn: RetailMediaNetworkTwin
    program: BrandRMNProgramTwin
    channels: List[ChannelTwin] = field(default_factory=list)
    campaigns: List[CampaignTwin] = field(default_factory=list)
    
    # Aggregated metrics
    total_spend: float = 0.0
    total_incremental_sales: float = 0.0
    efficiency: float = 0.0
    
    # Channel-level metrics
    channel_metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)
    
    def compute_efficiency(self) -> float:
        """Compute efficiency as incremental_sales / spend."""
        if self.total_spend > 0:
            self.efficiency = self.total_incremental_sales / self.total_spend
        return self.efficiency
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "brand": self.brand.to_dict(),
            "rmn": self.rmn.to_dict(),
            "program": self.program.to_dict(),
            "channels": [c.to_dict() for c in self.channels],
            "campaigns": [c.to_dict() for c in self.campaigns],
            "total_spend": self.total_spend,
            "total_incremental_sales": self.total_incremental_sales,
            "efficiency": self.efficiency,
            "channel_metrics": self.channel_metrics,
        }


@dataclass
class RMNOptimizationState:
    """
    Optimization state for comparing scenarios across an RMN.
    """
    rmn: RetailMediaNetworkTwin
    current_scenario: OptimizationScenarioDim
    optimized_scenario: Optional[OptimizationScenarioDim] = None
    
    # Current vs Optimized metrics
    current_spend: float = 0.0
    current_incremental_sales: float = 0.0
    optimized_spend: float = 0.0
    optimized_incremental_sales: float = 0.0
    
    # Channel-level optimization recommendations
    channel_recommendations: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    def compute_lift(self) -> float:
        """Compute incremental sales lift from optimization."""
        if self.current_incremental_sales > 0:
            return (self.optimized_incremental_sales - self.current_incremental_sales) / self.current_incremental_sales
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "rmn": self.rmn.to_dict(),
            "current_scenario": self.current_scenario.to_dict(),
            "optimized_scenario": self.optimized_scenario.to_dict() if self.optimized_scenario else None,
            "current_spend": self.current_spend,
            "current_incremental_sales": self.current_incremental_sales,
            "optimized_spend": self.optimized_spend,
            "optimized_incremental_sales": self.optimized_incremental_sales,
            "lift": self.compute_lift(),
            "channel_recommendations": self.channel_recommendations,
        }
