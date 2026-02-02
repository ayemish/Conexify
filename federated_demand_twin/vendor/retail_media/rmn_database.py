"""
RMN Digital Twin Database Models and Setup

SQLAlchemy ORM models for the RMN Digital Twin schema.
Supports SQLite for development and PostgreSQL for production.
"""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import (
    create_engine, Column, String, Float, Boolean, Date, DateTime, 
    Text, Integer, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker, Session
from uuid import uuid4

Base = declarative_base()


def generate_uuid() -> str:
    return str(uuid4())


# =============================================================================
# Core Twin Entities
# =============================================================================

class CompanyModel(Base):
    """Company entity (top-level organization)."""
    __tablename__ = 'companies'
    
    company_id = Column(String(36), primary_key=True, default=generate_uuid)
    company_name = Column(String(255), nullable=False)
    company_code = Column(String(50), nullable=True, unique=True)
    industry = Column(String(100), nullable=True)
    country = Column(String(50), default='US')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    brands = relationship("BrandModel", back_populates="company")
    
    __table_args__ = (
        Index('idx_company_name', 'company_name'),
    )


class BrandModel(Base):
    """Brand entity representing a product brand within a company."""
    __tablename__ = 'brands'
    
    brand_id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey('companies.company_id'), nullable=False)
    brand_name = Column(String(255), nullable=False)
    brand_code = Column(String(50), nullable=True)
    category = Column(String(100), nullable=True)
    default_margin_rate = Column(Float, nullable=True)
    lifecycle_stage = Column(String(50), nullable=True)  # growth|mature|decline
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Bayesian posterior outputs
    bayesian_state_id = Column(String(36), nullable=True)
    incremental_sales_posterior_mean = Column(Float, nullable=True)
    incremental_sales_posterior_std = Column(Float, nullable=True)
    incremental_sales_ci_lower = Column(Float, nullable=True)
    incremental_sales_ci_upper = Column(Float, nullable=True)
    efficiency_posterior_mean = Column(Float, nullable=True)
    efficiency_posterior_std = Column(Float, nullable=True)
    index_posterior_mean = Column(Float, nullable=True)
    lift_vs_prior_period_mean = Column(Float, nullable=True)
    lift_vs_year_ago_mean = Column(Float, nullable=True)
    prob_positive_lift = Column(Float, nullable=True)
    bayesian_last_updated = Column(DateTime, nullable=True)
    
    # Relationships
    company = relationship("CompanyModel", back_populates="brands")
    rmn_programs = relationship("BrandRMNProgramModel", back_populates="brand")
    
    __table_args__ = (
        Index('idx_brand_company', 'company_id'),
        Index('idx_brand_name', 'brand_name'),
        UniqueConstraint('company_id', 'brand_code', name='uq_brand_code'),
    )


class RetailMediaNetworkModel(Base):
    """Retail Media Network entity (e.g., Walmart Connect, Target Roundel)."""
    __tablename__ = 'retail_media_networks'
    
    rmn_id = Column(String(36), primary_key=True, default=generate_uuid)
    rmn_name = Column(String(255), nullable=False)
    rmn_code = Column(String(50), nullable=True, unique=True)
    rmn_type = Column(String(50), default='retailer')  # retailer|marketplace|rollup
    is_rollup_node = Column(Boolean, default=False)
    country = Column(String(50), default='US')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Bayesian posterior outputs
    bayesian_state_id = Column(String(36), nullable=True)
    incremental_sales_posterior_mean = Column(Float, nullable=True)
    incremental_sales_posterior_std = Column(Float, nullable=True)
    incremental_sales_ci_lower = Column(Float, nullable=True)
    incremental_sales_ci_upper = Column(Float, nullable=True)
    efficiency_posterior_mean = Column(Float, nullable=True)
    efficiency_posterior_std = Column(Float, nullable=True)
    index_posterior_mean = Column(Float, nullable=True)
    prob_best_overall = Column(Float, nullable=True)
    expected_rank = Column(Float, nullable=True)
    bayesian_last_updated = Column(DateTime, nullable=True)
    
    # Relationships
    programs = relationship("BrandRMNProgramModel", back_populates="rmn")
    channels = relationship("ChannelModel", back_populates="rmn")
    
    __table_args__ = (
        Index('idx_rmn_name', 'rmn_name'),
        Index('idx_rmn_type', 'rmn_type'),
    )


class BrandRMNProgramModel(Base):
    """Bridge entity linking a Brand to an RMN with program details."""
    __tablename__ = 'brand_rmn_programs'
    
    brand_rmn_program_id = Column(String(36), primary_key=True, default=generate_uuid)
    brand_id = Column(String(36), ForeignKey('brands.brand_id'), nullable=False)
    rmn_id = Column(String(36), ForeignKey('retail_media_networks.rmn_id'), nullable=False)
    program_name = Column(String(255), nullable=True)
    contract_start = Column(Date, nullable=True)
    contract_end = Column(Date, nullable=True)
    billing_model = Column(String(50), nullable=True)  # CPC|CPM|CPA|flat
    attribution_window_days = Column(Integer, nullable=True)
    budget_owner = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    brand = relationship("BrandModel", back_populates="rmn_programs")
    rmn = relationship("RetailMediaNetworkModel", back_populates="programs")
    channels = relationship("ChannelModel", back_populates="program")
    campaigns = relationship("CampaignModel", back_populates="program")
    
    __table_args__ = (
        Index('idx_program_brand', 'brand_id'),
        Index('idx_program_rmn', 'rmn_id'),
        UniqueConstraint('brand_id', 'rmn_id', name='uq_brand_rmn'),
    )


class ChannelModel(Base):
    """Channel entity representing an RMN channel (search, display, video, email)."""
    __tablename__ = 'channels'
    
    channel_id = Column(String(36), primary_key=True, default=generate_uuid)
    rmn_id = Column(String(36), ForeignKey('retail_media_networks.rmn_id'), nullable=False)
    brand_rmn_program_id = Column(String(36), ForeignKey('brand_rmn_programs.brand_rmn_program_id'), nullable=False)
    channel_name = Column(String(255), nullable=False)
    channel_type = Column(String(50), nullable=False)  # search|display|video|email|other
    objective_default = Column(String(255), nullable=True)
    bidding_strategy_default = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Bayesian posterior outputs
    bayesian_state_id = Column(String(36), nullable=True)
    incremental_sales_posterior_mean = Column(Float, nullable=True)
    incremental_sales_posterior_std = Column(Float, nullable=True)
    incremental_sales_ci_lower = Column(Float, nullable=True)
    incremental_sales_ci_upper = Column(Float, nullable=True)
    efficiency_posterior_mean = Column(Float, nullable=True)
    efficiency_posterior_std = Column(Float, nullable=True)
    index_posterior_mean = Column(Float, nullable=True)
    elasticity_posterior_mean = Column(Float, nullable=True)
    elasticity_posterior_std = Column(Float, nullable=True)
    elasticity_ci_lower = Column(Float, nullable=True)
    elasticity_ci_upper = Column(Float, nullable=True)
    contribution_posterior_mean = Column(Float, nullable=True)
    contribution_pct_posterior_mean = Column(Float, nullable=True)
    prob_efficiency_above_target = Column(Float, nullable=True)
    efficiency_target = Column(Float, nullable=True)
    prob_rank_1_within_rmn = Column(Float, nullable=True)
    expected_rank_within_rmn = Column(Float, nullable=True)
    bayesian_last_updated = Column(DateTime, nullable=True)
    
    # Relationships
    rmn = relationship("RetailMediaNetworkModel", back_populates="channels")
    program = relationship("BrandRMNProgramModel", back_populates="channels")
    campaigns = relationship("CampaignModel", back_populates="channel")
    
    __table_args__ = (
        Index('idx_channel_rmn', 'rmn_id'),
        Index('idx_channel_program', 'brand_rmn_program_id'),
        Index('idx_channel_type', 'channel_type'),
    )


class CampaignModel(Base):
    """Campaign entity representing an advertising campaign."""
    __tablename__ = 'campaigns'
    
    campaign_id = Column(String(36), primary_key=True, default=generate_uuid)
    brand_rmn_program_id = Column(String(36), ForeignKey('brand_rmn_programs.brand_rmn_program_id'), nullable=False)
    channel_id = Column(String(36), ForeignKey('channels.channel_id'), nullable=False)
    campaign_name = Column(String(255), nullable=False)
    campaign_objective = Column(String(255), nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    budget_planned = Column(Float, nullable=True)
    pacing_mode = Column(String(50), nullable=True)  # even|frontload|backload
    targeting_summary = Column(Text, nullable=True)
    status = Column(String(50), default='draft')  # draft|live|paused|ended
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    program = relationship("BrandRMNProgramModel", back_populates="campaigns")
    channel = relationship("ChannelModel", back_populates="campaigns")
    messages = relationship("MessageModel", back_populates="campaign")
    
    __table_args__ = (
        Index('idx_campaign_program', 'brand_rmn_program_id'),
        Index('idx_campaign_channel', 'channel_id'),
        Index('idx_campaign_status', 'status'),
        Index('idx_campaign_dates', 'start_date', 'end_date'),
    )


class MessageModel(Base):
    """Message/Creative entity representing ad creative content."""
    __tablename__ = 'messages'
    
    message_id = Column(String(36), primary_key=True, default=generate_uuid)
    campaign_id = Column(String(36), ForeignKey('campaigns.campaign_id'), nullable=False)
    message_name = Column(String(255), nullable=False)
    creative_type = Column(String(50), nullable=True)  # static|video|html|email
    offer_type = Column(String(100), nullable=True)
    headline = Column(String(500), nullable=True)
    cta = Column(String(100), nullable=True)
    landing_url = Column(String(1000), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    campaign = relationship("CampaignModel", back_populates="messages")
    
    __table_args__ = (
        Index('idx_message_campaign', 'campaign_id'),
    )


# =============================================================================
# Dimension Tables
# =============================================================================

class TimePeriodDimModel(Base):
    """Time period dimension for temporal analysis."""
    __tablename__ = 'dim_time_periods'
    
    time_period_id = Column(String(36), primary_key=True, default=generate_uuid)
    date = Column(Date, nullable=False)
    period = Column(String(20), nullable=True)  # e.g., 2024-P07
    quarter = Column(String(10), nullable=True)
    half = Column(String(10), nullable=True)
    calendar = Column(String(20), nullable=True)  # e.g., 2024-CY
    grain = Column(String(20), default='week')  # day|week|month|quarter|year
    
    __table_args__ = (
        Index('idx_time_date', 'date'),
        Index('idx_time_period', 'period'),
        Index('idx_time_grain', 'grain'),
    )


class MetricDimModel(Base):
    """Metric dimension defining measurement types."""
    __tablename__ = 'dim_metrics'
    
    metric_id = Column(String(36), primary_key=True, default=generate_uuid)
    metric_name = Column(String(255), nullable=False, unique=True)
    unit = Column(String(50), nullable=True)  # USD|units
    is_primary = Column(Boolean, default=False)
    
    __table_args__ = (
        Index('idx_metric_name', 'metric_name'),
    )


class BaselineDimModel(Base):
    """Baseline dimension for measurement context."""
    __tablename__ = 'dim_baselines'
    
    baseline_id = Column(String(36), primary_key=True, default=generate_uuid)
    measurement_name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)


class SpendCategoryDimModel(Base):
    """Spend category dimension (hierarchy1)."""
    __tablename__ = 'dim_spend_categories'
    
    spend_category_id = Column(String(36), primary_key=True, default=generate_uuid)
    spend_category_name = Column(String(255), nullable=False, unique=True)
    spend_category_type = Column(String(50), nullable=True)  # paid_media|promo|rmn|trade|env
    
    # Relationships
    tactic_drivers = relationship("TacticDriverDimModel", back_populates="spend_category")


class TacticDriverDimModel(Base):
    """Tactic/Driver dimension (hierarchy2)."""
    __tablename__ = 'dim_tactic_drivers'
    
    tactic_driver_id = Column(String(36), primary_key=True, default=generate_uuid)
    spend_category_id = Column(String(36), ForeignKey('dim_spend_categories.spend_category_id'), nullable=False)
    tactic_driver_name = Column(String(255), nullable=False)
    is_rmn_channel = Column(Boolean, default=False)
    
    # Relationships
    spend_category = relationship("SpendCategoryDimModel", back_populates="tactic_drivers")
    
    __table_args__ = (
        Index('idx_tactic_category', 'spend_category_id'),
        UniqueConstraint('spend_category_id', 'tactic_driver_name', name='uq_tactic_driver'),
    )


class OptimizationScenarioDimModel(Base):
    """Optimization scenario dimension for what-if analysis."""
    __tablename__ = 'dim_optimization_scenarios'
    
    scenario_id = Column(String(36), primary_key=True, default=generate_uuid)
    scenario_name = Column(String(255), nullable=False)
    objective = Column(String(100), nullable=True)
    constraints_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_scenario_name', 'scenario_name'),
    )


# =============================================================================
# Bayesian Output Tables
# =============================================================================

class PosteriorDistributionModel(Base):
    """Store posterior distributions for any entity KPI."""
    __tablename__ = 'bayesian_posteriors'
    
    posterior_id = Column(String(36), primary_key=True, default=generate_uuid)
    entity_type = Column(String(50), nullable=False)  # brand|rmn|channel|driver|category
    entity_id = Column(String(36), nullable=False)
    kpi_name = Column(String(100), nullable=False)  # incremental_sales|efficiency|elasticity|etc
    metric_type = Column(String(50), default='dollar_sales')
    baseline_type = Column(String(50), nullable=True)  # prior_period|same_period_year_ago
    
    # Posterior parameters
    posterior_mean = Column(Float, nullable=False)
    posterior_median = Column(Float, nullable=True)
    posterior_std = Column(Float, nullable=False)
    
    # Credible intervals
    ci_50_lower = Column(Float, nullable=True)
    ci_50_upper = Column(Float, nullable=True)
    ci_80_lower = Column(Float, nullable=True)
    ci_80_upper = Column(Float, nullable=True)
    ci_90_lower = Column(Float, nullable=True)
    ci_90_upper = Column(Float, nullable=True)
    ci_95_lower = Column(Float, nullable=True)
    ci_95_upper = Column(Float, nullable=True)
    
    # Probability statements
    prob_positive = Column(Float, nullable=True)  # P(effect > 0)
    prob_above_threshold = Column(Float, nullable=True)
    threshold_value = Column(Float, nullable=True)
    
    # Evidence and model info
    n_observations = Column(Integer, default=0)
    evidence_strength = Column(Float, default=0.5)
    prior_mean = Column(Float, nullable=True)
    prior_std = Column(Float, nullable=True)
    model_version = Column(String(50), default='v1.0.0')
    computed_at = Column(DateTime, default=datetime.utcnow)
    
    # Time context
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    time_grain = Column(String(20), default='week')
    
    __table_args__ = (
        Index('idx_posterior_entity', 'entity_type', 'entity_id'),
        Index('idx_posterior_kpi', 'kpi_name'),
        Index('idx_posterior_time', 'period_start', 'period_end'),
    )


class LiftDecompositionModel(Base):
    """Store lift/delta decomposition outputs."""
    __tablename__ = 'bayesian_lift_decompositions'
    
    decomposition_id = Column(String(36), primary_key=True, default=generate_uuid)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(36), nullable=False)
    metric_type = Column(String(50), default='dollar_sales')
    baseline_type = Column(String(50), default='prior_period')
    
    # Time context
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    
    # Baseline (counterfactual) posterior
    baseline_posterior_mean = Column(Float, nullable=True)
    baseline_posterior_std = Column(Float, nullable=True)
    baseline_ci_lower = Column(Float, nullable=True)
    baseline_ci_upper = Column(Float, nullable=True)
    
    # Actual posterior
    actual_posterior_mean = Column(Float, nullable=True)
    actual_posterior_std = Column(Float, nullable=True)
    actual_ci_lower = Column(Float, nullable=True)
    actual_ci_upper = Column(Float, nullable=True)
    
    # Lift posterior
    lift_posterior_mean = Column(Float, nullable=True)
    lift_posterior_std = Column(Float, nullable=True)
    lift_ci_lower = Column(Float, nullable=True)
    lift_ci_upper = Column(Float, nullable=True)
    lift_pct_mean = Column(Float, nullable=True)
    
    # Probability statements
    prob_positive_lift = Column(Float, nullable=True)
    prob_significant_lift = Column(Float, nullable=True)
    
    computed_at = Column(DateTime, default=datetime.utcnow)
    model_version = Column(String(50), default='v1.0.0')
    
    __table_args__ = (
        Index('idx_lift_entity', 'entity_type', 'entity_id'),
        Index('idx_lift_baseline', 'baseline_type'),
    )


class DriverAttributionModel(Base):
    """Store driver attribution posteriors."""
    __tablename__ = 'bayesian_driver_attributions'
    
    attribution_id = Column(String(36), primary_key=True, default=generate_uuid)
    parent_entity_type = Column(String(50), nullable=False)  # brand|rmn|channel
    parent_entity_id = Column(String(36), nullable=False)
    driver_id = Column(String(36), nullable=False)
    driver_name = Column(String(255), nullable=False)
    driver_category_id = Column(String(36), nullable=True)  # hierarchy1
    
    # Time and metric context
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    metric_type = Column(String(50), default='dollar_sales')
    baseline_type = Column(String(50), default='prior_period')
    
    # Contribution posterior (dueto)
    contribution_posterior_mean = Column(Float, nullable=True)
    contribution_posterior_std = Column(Float, nullable=True)
    contribution_ci_lower = Column(Float, nullable=True)
    contribution_ci_upper = Column(Float, nullable=True)
    
    # Contribution percentage posterior (dueto_pct)
    contribution_pct_posterior_mean = Column(Float, nullable=True)
    contribution_pct_posterior_std = Column(Float, nullable=True)
    contribution_pct_ci_lower = Column(Float, nullable=True)
    contribution_pct_ci_upper = Column(Float, nullable=True)
    
    # Driver classification
    incremental_probability = Column(Float, nullable=True)
    cannibalization_probability = Column(Float, nullable=True)
    net_incremental_posterior_mean = Column(Float, nullable=True)
    
    # Ranking
    prob_top_contributor = Column(Float, nullable=True)
    prob_top_10_contributor = Column(Float, nullable=True)
    
    computed_at = Column(DateTime, default=datetime.utcnow)
    model_version = Column(String(50), default='v1.0.0')
    
    __table_args__ = (
        Index('idx_attribution_parent', 'parent_entity_type', 'parent_entity_id'),
        Index('idx_attribution_driver', 'driver_id'),
    )


class ScenarioComparisonModel(Base):
    """Store scenario comparison outputs."""
    __tablename__ = 'bayesian_scenario_comparisons'
    
    comparison_id = Column(String(36), primary_key=True, default=generate_uuid)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(36), nullable=False)
    
    # Scenario references
    current_scenario_id = Column(String(36), nullable=True)
    optimized_scenario_id = Column(String(36), nullable=True)
    
    # Expected value of the decision
    expected_incremental_sales_delta = Column(Float, nullable=True)
    expected_delta_ci_lower = Column(Float, nullable=True)
    expected_delta_ci_upper = Column(Float, nullable=True)
    expected_efficiency_delta = Column(Float, nullable=True)
    
    # Probability comparisons
    prob_optimized_beats_current = Column(Float, nullable=True)
    prob_optimized_beats_current_by_5pct = Column(Float, nullable=True)
    prob_optimized_beats_current_by_10pct = Column(Float, nullable=True)
    
    # Risk measures
    prob_underperforming_constraint = Column(Float, nullable=True)
    constraint_description = Column(Text, nullable=True)
    
    # Allocation recommendations (JSON)
    recommended_allocation_json = Column(Text, nullable=True)
    
    computed_at = Column(DateTime, default=datetime.utcnow)
    model_version = Column(String(50), default='v1.0.0')
    
    __table_args__ = (
        Index('idx_comparison_entity', 'entity_type', 'entity_id'),
    )


class RankingPosteriorModel(Base):
    """Store ranking posterior outputs."""
    __tablename__ = 'bayesian_rankings'
    
    ranking_id = Column(String(36), primary_key=True, default=generate_uuid)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(36), nullable=False)
    ranking_context = Column(String(100), nullable=False)  # e.g., 'brand_rmn_effectiveness'
    
    # Ranking probabilities
    prob_rank_1 = Column(Float, nullable=True)
    prob_rank_2 = Column(Float, nullable=True)
    prob_top_3 = Column(Float, nullable=True)
    prob_top_5 = Column(Float, nullable=True)
    prob_top_decile = Column(Float, nullable=True)
    
    # Expected rank
    expected_rank = Column(Float, nullable=True)
    rank_std = Column(Float, nullable=True)
    
    # Context
    total_entities_in_ranking = Column(Integer, default=0)
    comparison_group = Column(String(100), nullable=True)
    computed_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_ranking_entity', 'entity_type', 'entity_id'),
        Index('idx_ranking_context', 'ranking_context'),
    )


class BayesianUpdateAuditModel(Base):
    """Audit trail for Bayesian twin updates."""
    __tablename__ = 'bayesian_update_audit'
    
    audit_id = Column(String(36), primary_key=True, default=generate_uuid)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(36), nullable=False)
    update_type = Column(String(50), nullable=False)  # posterior|lift|attribution|ranking
    field_name = Column(String(100), nullable=False)
    old_value = Column(Float, nullable=True)
    new_value = Column(Float, nullable=True)
    posterior_mean = Column(Float, nullable=True)
    posterior_std = Column(Float, nullable=True)
    evidence_strength = Column(Float, nullable=True)
    n_observations = Column(Integer, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)
    model_version = Column(String(50), default='v1.0.0')
    
    __table_args__ = (
        Index('idx_audit_entity', 'entity_type', 'entity_id'),
        Index('idx_audit_time', 'updated_at'),
    )


# =============================================================================
# Fact Tables
# =============================================================================

class PerformanceObservationFactModel(Base):
    """Raw performance observation fact table."""
    __tablename__ = 'fact_performance_observations'
    
    observation_id = Column(String(36), primary_key=True, default=generate_uuid)
    brand_id = Column(String(36), ForeignKey('brands.brand_id'), nullable=False)
    rmn_id = Column(String(36), ForeignKey('retail_media_networks.rmn_id'), nullable=False)
    time_period_id = Column(String(36), ForeignKey('dim_time_periods.time_period_id'), nullable=False)
    metric_id = Column(String(36), ForeignKey('dim_metrics.metric_id'), nullable=False)
    baseline_id = Column(String(36), ForeignKey('dim_baselines.baseline_id'), nullable=False)
    spend_category_id = Column(String(36), ForeignKey('dim_spend_categories.spend_category_id'), nullable=False)
    tactic_driver_id = Column(String(36), ForeignKey('dim_tactic_drivers.tactic_driver_id'), nullable=False)
    prior = Column(Float, nullable=True)
    current = Column(Float, nullable=True)
    dueto = Column(Float, nullable=True)
    dueto_pct = Column(Float, nullable=True)
    
    __table_args__ = (
        Index('idx_obs_brand', 'brand_id'),
        Index('idx_obs_rmn', 'rmn_id'),
        Index('idx_obs_time', 'time_period_id'),
        Index('idx_obs_metric', 'metric_id'),
        Index('idx_obs_composite', 'brand_id', 'rmn_id', 'time_period_id'),
    )


class RMNPerformanceFactModel(Base):
    """Aggregated RMN performance fact table for optimization scenarios."""
    __tablename__ = 'fact_rmn_performance'
    
    rmn_perf_id = Column(String(36), primary_key=True, default=generate_uuid)
    brand_id = Column(String(36), ForeignKey('brands.brand_id'), nullable=False)
    rmn_id = Column(String(36), ForeignKey('retail_media_networks.rmn_id'), nullable=False)
    channel_id = Column(String(36), ForeignKey('channels.channel_id'), nullable=True)
    scenario_id = Column(String(36), ForeignKey('dim_optimization_scenarios.scenario_id'), nullable=False)
    time_period_id = Column(String(36), ForeignKey('dim_time_periods.time_period_id'), nullable=True)
    spend = Column(Float, nullable=True)
    incremental_sales = Column(Float, nullable=True)
    efficiency = Column(Float, nullable=True)
    index = Column(Float, nullable=True)
    
    __table_args__ = (
        Index('idx_rmn_perf_brand', 'brand_id'),
        Index('idx_rmn_perf_rmn', 'rmn_id'),
        Index('idx_rmn_perf_scenario', 'scenario_id'),
        Index('idx_rmn_perf_composite', 'brand_id', 'rmn_id', 'scenario_id'),
    )


# =============================================================================
# Database Setup and Utilities
# =============================================================================

class RMNDatabase:
    """Database manager for RMN Digital Twin."""
    
    def __init__(self, database_url: str = "sqlite:///rmn_digital_twin.db"):
        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def create_tables(self):
        """Create all tables."""
        Base.metadata.create_all(self.engine)
    
    def drop_tables(self):
        """Drop all tables."""
        Base.metadata.drop_all(self.engine)
    
    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()
    
    def seed_sample_data(self):
        """Seed the database with sample data for Kellogg's."""
        session = self.get_session()
        try:
            # Create Kellogg's company
            kelloggs = CompanyModel(
                company_id="kelloggs-001",
                company_name="Kellogg's",
                company_code="KEL",
                industry="Consumer Packaged Goods",
                country="US"
            )
            session.add(kelloggs)
            
            # Create brands
            brands = [
                BrandModel(brand_id="brand-001", company_id="kelloggs-001", brand_name="Frosted Flakes", brand_code="FF", category="Cereal", lifecycle_stage="mature"),
                BrandModel(brand_id="brand-002", company_id="kelloggs-001", brand_name="Pop-Tarts", brand_code="PT", category="Toaster Pastries", lifecycle_stage="mature"),
                BrandModel(brand_id="brand-003", company_id="kelloggs-001", brand_name="Cheez-It", brand_code="CI", category="Crackers", lifecycle_stage="growth"),
                BrandModel(brand_id="brand-004", company_id="kelloggs-001", brand_name="Pringles", brand_code="PR", category="Snacks", lifecycle_stage="mature"),
                BrandModel(brand_id="brand-005", company_id="kelloggs-001", brand_name="Eggo", brand_code="EG", category="Frozen Breakfast", lifecycle_stage="mature"),
                BrandModel(brand_id="brand-006", company_id="kelloggs-001", brand_name="Special K", brand_code="SK", category="Cereal", lifecycle_stage="decline"),
            ]
            session.add_all(brands)
            
            # Create RMNs
            rmns = [
                RetailMediaNetworkModel(rmn_id="rmn-walmart", rmn_name="Walmart Connect", rmn_code="WMT", rmn_type="retailer"),
                RetailMediaNetworkModel(rmn_id="rmn-target", rmn_name="Target Roundel", rmn_code="TGT", rmn_type="retailer"),
                RetailMediaNetworkModel(rmn_id="rmn-amazon", rmn_name="Amazon Advertising", rmn_code="AMZN", rmn_type="marketplace"),
                RetailMediaNetworkModel(rmn_id="rmn-instacart", rmn_name="Instacart Ads", rmn_code="IC", rmn_type="marketplace"),
                RetailMediaNetworkModel(rmn_id="rmn-albertsons", rmn_name="Albertsons Media Collective", rmn_code="ABS", rmn_type="retailer"),
                RetailMediaNetworkModel(rmn_id="rmn-total-us", rmn_name="Total US - MultiOutletC", rmn_code="TOTAL", rmn_type="rollup", is_rollup_node=True),
            ]
            session.add_all(rmns)
            
            # Create Brand-RMN Programs (for first brand across all RMNs as example)
            programs = []
            channel_types = ["search", "display", "video", "email"]
            for brand in brands[:3]:  # First 3 brands
                for rmn in rmns[:5]:  # First 5 RMNs (not rollup)
                    program = BrandRMNProgramModel(
                        brand_rmn_program_id=f"prog-{brand.brand_id}-{rmn.rmn_id}",
                        brand_id=brand.brand_id,
                        rmn_id=rmn.rmn_id,
                        program_name=f"{brand.brand_name} on {rmn.rmn_name}",
                        billing_model="CPC",
                        attribution_window_days=14
                    )
                    programs.append(program)
                    session.add(program)
                    
                    # Create channels for each program
                    for ch_type in channel_types:
                        channel = ChannelModel(
                            channel_id=f"ch-{brand.brand_id}-{rmn.rmn_id}-{ch_type}",
                            rmn_id=rmn.rmn_id,
                            brand_rmn_program_id=program.brand_rmn_program_id,
                            channel_name=f"RMN {ch_type.upper()}",
                            channel_type=ch_type
                        )
                        session.add(channel)
            
            # Create spend categories
            spend_categories = [
                SpendCategoryDimModel(spend_category_id="cat-retail-media", spend_category_name="RETAIL MEDIA", spend_category_type="rmn"),
                SpendCategoryDimModel(spend_category_id="cat-paid-media", spend_category_name="PAID MEDIA", spend_category_type="paid_media"),
                SpendCategoryDimModel(spend_category_id="cat-trade", spend_category_name="TRADE SUPPORT", spend_category_type="trade"),
                SpendCategoryDimModel(spend_category_id="cat-promo", spend_category_name="CONSUMER PROMOTIONS", spend_category_type="promo"),
            ]
            session.add_all(spend_categories)
            
            # Create tactic drivers
            tactic_drivers = [
                TacticDriverDimModel(tactic_driver_id="tactic-rmn-search", spend_category_id="cat-retail-media", tactic_driver_name="RMN SEARCH", is_rmn_channel=True),
                TacticDriverDimModel(tactic_driver_id="tactic-rmn-display", spend_category_id="cat-retail-media", tactic_driver_name="RMN DISPLAY", is_rmn_channel=True),
                TacticDriverDimModel(tactic_driver_id="tactic-rmn-video", spend_category_id="cat-retail-media", tactic_driver_name="RMN VIDEO", is_rmn_channel=True),
                TacticDriverDimModel(tactic_driver_id="tactic-rmn-email", spend_category_id="cat-retail-media", tactic_driver_name="RMN EMAIL", is_rmn_channel=True),
                TacticDriverDimModel(tactic_driver_id="tactic-tv", spend_category_id="cat-paid-media", tactic_driver_name="TV", is_rmn_channel=False),
                TacticDriverDimModel(tactic_driver_id="tactic-digital", spend_category_id="cat-paid-media", tactic_driver_name="DIGITAL", is_rmn_channel=False),
            ]
            session.add_all(tactic_drivers)
            
            # Create optimization scenarios
            scenarios = [
                OptimizationScenarioDimModel(scenario_id="scenario-current", scenario_name="current", objective="maintain_revenue"),
                OptimizationScenarioDimModel(scenario_id="scenario-optimized", scenario_name="optimized", objective="increase_revenue"),
            ]
            session.add_all(scenarios)
            
            # Create metrics
            metrics = [
                MetricDimModel(metric_id="metric-revenue", metric_name="Revenue", unit="USD", is_primary=True),
                MetricDimModel(metric_id="metric-units", metric_name="Units Sold", unit="units", is_primary=True),
                MetricDimModel(metric_id="metric-roas", metric_name="ROAS", unit="ratio", is_primary=False),
            ]
            session.add_all(metrics)
            
            # Create baselines
            baselines = [
                BaselineDimModel(baseline_id="baseline-yago", measurement_name="Year Ago", description="Prior year comparison"),
                BaselineDimModel(baseline_id="baseline-budget", measurement_name="Budget", description="Budget comparison"),
            ]
            session.add_all(baselines)
            
            session.commit()
            print("Sample data seeded successfully.")
            
        except Exception as e:
            session.rollback()
            print(f"Error seeding data: {e}")
            raise
        finally:
            session.close()


# Convenience function to initialize database
def init_rmn_database(database_url: str = "sqlite:///rmn_digital_twin.db", seed: bool = True) -> RMNDatabase:
    """Initialize the RMN database with optional sample data."""
    db = RMNDatabase(database_url)
    db.create_tables()
    if seed:
        db.seed_sample_data()
    return db
