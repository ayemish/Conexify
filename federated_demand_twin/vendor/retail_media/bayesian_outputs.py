"""
Bayesian Output Schemas for Digital Twin Entities

This module defines comprehensive Bayesian posterior output structures that
connect hierarchical Bayesian analysis to digital twin entities.

The hierarchical Bayesian analysis provides priors for identifying spend
that drives incremental revenue across:
- Brand (product)
- Retail Media Network / Retailer (geography)
- Channel (RMN SEARCH, RMN DISPLAY, RMN VIDEO, RMN EMAIL)
- Marketing Driver (tactic/lever - hierarchy2)
- Marketing Driver Category (hierarchy1)

Outputs include:
- Posterior distributions (mean, std, credible intervals)
- Posterior predictive distributions
- Lift/delta decomposition
- Attribution posteriors
- Scenario comparison posteriors
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Tuple
from uuid import uuid4
from enum import Enum
import numpy as np


def generate_id() -> str:
    """Generate a unique ID."""
    return str(uuid4())


class PosteriorType(Enum):
    """Types of posterior outputs."""
    POINT_ESTIMATE = "point_estimate"
    DISTRIBUTION = "distribution"
    RANKING = "ranking"
    PROBABILITY = "probability"


class MetricType(Enum):
    """Supported metric types."""
    DOLLAR_SALES = "dollar_sales"
    VOLUME_SALES = "volume_sales"
    INCREMENTAL_SALES = "incremental_sales"
    EFFICIENCY = "efficiency"
    ROAS = "roas"
    INDEX = "index"


class BaselineType(Enum):
    """Baseline comparison types."""
    PRIOR_PERIOD = "prior_period"
    SAME_PERIOD_YEAR_AGO = "same_period_year_ago"


# =============================================================================
# Core Posterior Distribution Schema
# =============================================================================

@dataclass
class PosteriorDistribution:
    """
    Universal posterior distribution schema.
    
    Used for any KPI posterior across all entity types.
    """
    posterior_id: str = field(default_factory=generate_id)
    entity_type: str = ""  # brand|rmn|channel|driver|category|company
    entity_id: str = ""
    kpi_name: str = ""  # e.g., 'incremental_sales', 'efficiency', 'elasticity'
    metric_type: str = "dollar_sales"  # dollar_sales|volume_sales
    baseline_type: Optional[str] = None  # prior_period|same_period_year_ago
    
    # Core posterior parameters
    posterior_mean: float = 0.0
    posterior_median: Optional[float] = None
    posterior_std: float = 0.0
    
    # Credible intervals
    ci_50_lower: Optional[float] = None
    ci_50_upper: Optional[float] = None
    ci_80_lower: Optional[float] = None
    ci_80_upper: Optional[float] = None
    ci_90_lower: float = 0.0
    ci_90_upper: float = 0.0
    ci_95_lower: Optional[float] = None
    ci_95_upper: Optional[float] = None
    
    # Probability statements
    prob_positive: Optional[float] = None  # P(effect > 0)
    prob_above_threshold: Optional[float] = None  # P(effect > threshold)
    threshold_value: Optional[float] = None
    
    # Evidence and model info
    n_observations: int = 0
    evidence_strength: float = 0.5  # 0-1
    prior_mean: Optional[float] = None
    prior_std: Optional[float] = None
    model_version: str = "v1.0.0"
    computed_at: datetime = field(default_factory=datetime.utcnow)
    
    # Time context
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    time_grain: str = "week"  # day|week|month|quarter
    
    def sample(self, n_samples: int = 1000) -> np.ndarray:
        """Sample from the posterior distribution."""
        return np.random.normal(self.posterior_mean, self.posterior_std, n_samples)
    
    def compute_probability_above(self, threshold: float) -> float:
        """Compute P(posterior > threshold)."""
        if self.posterior_std > 0:
            from scipy import stats
            return 1 - stats.norm.cdf(threshold, self.posterior_mean, self.posterior_std)
        return 1.0 if self.posterior_mean > threshold else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "posterior_id": self.posterior_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "kpi_name": self.kpi_name,
            "metric_type": self.metric_type,
            "baseline_type": self.baseline_type,
            "posterior_mean": self.posterior_mean,
            "posterior_median": self.posterior_median,
            "posterior_std": self.posterior_std,
            "ci_50": [self.ci_50_lower, self.ci_50_upper] if self.ci_50_lower else None,
            "ci_80": [self.ci_80_lower, self.ci_80_upper] if self.ci_80_lower else None,
            "ci_90": [self.ci_90_lower, self.ci_90_upper],
            "ci_95": [self.ci_95_lower, self.ci_95_upper] if self.ci_95_lower else None,
            "prob_positive": self.prob_positive,
            "prob_above_threshold": self.prob_above_threshold,
            "threshold_value": self.threshold_value,
            "n_observations": self.n_observations,
            "evidence_strength": self.evidence_strength,
            "prior_mean": self.prior_mean,
            "prior_std": self.prior_std,
            "model_version": self.model_version,
            "computed_at": self.computed_at.isoformat(),
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
        }


@dataclass
class RankingPosterior:
    """
    Posterior distribution for entity rankings.
    
    Used for P(entity is #1), P(entity in top N), etc.
    """
    ranking_id: str = field(default_factory=generate_id)
    entity_type: str = ""
    entity_id: str = ""
    ranking_context: str = ""  # e.g., 'brand_rmn_effectiveness', 'channel_efficiency'
    
    # Ranking probabilities
    prob_rank_1: float = 0.0
    prob_rank_2: Optional[float] = None
    prob_top_3: Optional[float] = None
    prob_top_5: Optional[float] = None
    prob_top_decile: Optional[float] = None
    
    # Expected rank
    expected_rank: float = 0.0
    rank_std: float = 0.0
    
    # Context
    total_entities_in_ranking: int = 0
    comparison_group: Optional[str] = None  # e.g., 'all_rmns', 'brand_channels'
    computed_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "ranking_id": self.ranking_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "ranking_context": self.ranking_context,
            "prob_rank_1": self.prob_rank_1,
            "prob_rank_2": self.prob_rank_2,
            "prob_top_3": self.prob_top_3,
            "prob_top_5": self.prob_top_5,
            "prob_top_decile": self.prob_top_decile,
            "expected_rank": self.expected_rank,
            "rank_std": self.rank_std,
            "total_entities_in_ranking": self.total_entities_in_ranking,
            "comparison_group": self.comparison_group,
            "computed_at": self.computed_at.isoformat(),
        }


# =============================================================================
# Lift / Delta Decomposition Outputs
# =============================================================================

@dataclass
class LiftDecomposition:
    """
    Bayesian lift/delta decomposition aligned with workbook data fields.
    
    Maps to: prior, current, dueto, dueto_pct from the normalized fact table.
    """
    decomposition_id: str = field(default_factory=generate_id)
    entity_type: str = ""
    entity_id: str = ""
    metric_type: str = "dollar_sales"
    baseline_type: str = "prior_period"
    
    # Time context
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    
    # Baseline (counterfactual) posterior
    baseline_posterior_mean: float = 0.0
    baseline_posterior_std: float = 0.0
    baseline_ci_lower: float = 0.0
    baseline_ci_upper: float = 0.0
    
    # Actual posterior
    actual_posterior_mean: float = 0.0
    actual_posterior_std: float = 0.0
    actual_ci_lower: float = 0.0
    actual_ci_upper: float = 0.0
    
    # Lift posterior (Δ = actual - baseline)
    lift_posterior_mean: float = 0.0
    lift_posterior_std: float = 0.0
    lift_ci_lower: float = 0.0
    lift_ci_upper: float = 0.0
    lift_pct_mean: Optional[float] = None  # percentage lift
    
    # Probability statements
    prob_positive_lift: float = 0.0  # P(lift > 0)
    prob_significant_lift: Optional[float] = None  # P(lift > threshold)
    
    computed_at: datetime = field(default_factory=datetime.utcnow)
    model_version: str = "v1.0.0"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "decomposition_id": self.decomposition_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "metric_type": self.metric_type,
            "baseline_type": self.baseline_type,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "baseline_posterior": {
                "mean": self.baseline_posterior_mean,
                "std": self.baseline_posterior_std,
                "ci": [self.baseline_ci_lower, self.baseline_ci_upper],
            },
            "actual_posterior": {
                "mean": self.actual_posterior_mean,
                "std": self.actual_posterior_std,
                "ci": [self.actual_ci_lower, self.actual_ci_upper],
            },
            "lift_posterior": {
                "mean": self.lift_posterior_mean,
                "std": self.lift_posterior_std,
                "ci": [self.lift_ci_lower, self.lift_ci_upper],
                "pct_mean": self.lift_pct_mean,
            },
            "prob_positive_lift": self.prob_positive_lift,
            "prob_significant_lift": self.prob_significant_lift,
            "computed_at": self.computed_at.isoformat(),
            "model_version": self.model_version,
        }


@dataclass
class DriverAttributionPosterior:
    """
    Attribution posterior for a specific driver.
    
    Maps to driver_contribution (dueto) and driver_contribution_pct (dueto_pct).
    """
    attribution_id: str = field(default_factory=generate_id)
    parent_entity_type: str = ""  # brand|rmn|channel
    parent_entity_id: str = ""
    driver_id: str = ""
    driver_name: str = ""
    driver_category_id: Optional[str] = None  # hierarchy1
    
    # Time and metric context
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    metric_type: str = "dollar_sales"
    baseline_type: str = "prior_period"
    
    # Contribution posterior (dueto)
    contribution_posterior_mean: float = 0.0
    contribution_posterior_std: float = 0.0
    contribution_ci_lower: float = 0.0
    contribution_ci_upper: float = 0.0
    
    # Contribution percentage posterior (dueto_pct)
    contribution_pct_posterior_mean: float = 0.0
    contribution_pct_posterior_std: float = 0.0
    contribution_pct_ci_lower: float = 0.0
    contribution_pct_ci_upper: float = 0.0
    
    # Driver classification (for incremental vs cannibalization)
    incremental_probability: Optional[float] = None
    cannibalization_probability: Optional[float] = None
    net_incremental_posterior_mean: Optional[float] = None
    
    # Ranking within parent entity
    prob_top_contributor: Optional[float] = None  # P(driver is #1)
    prob_top_10_contributor: Optional[float] = None
    
    computed_at: datetime = field(default_factory=datetime.utcnow)
    model_version: str = "v1.0.0"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "attribution_id": self.attribution_id,
            "parent_entity_type": self.parent_entity_type,
            "parent_entity_id": self.parent_entity_id,
            "driver_id": self.driver_id,
            "driver_name": self.driver_name,
            "driver_category_id": self.driver_category_id,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "metric_type": self.metric_type,
            "baseline_type": self.baseline_type,
            "contribution_posterior": {
                "mean": self.contribution_posterior_mean,
                "std": self.contribution_posterior_std,
                "ci": [self.contribution_ci_lower, self.contribution_ci_upper],
            },
            "contribution_pct_posterior": {
                "mean": self.contribution_pct_posterior_mean,
                "std": self.contribution_pct_posterior_std,
                "ci": [self.contribution_pct_ci_lower, self.contribution_pct_ci_upper],
            },
            "incremental_probability": self.incremental_probability,
            "cannibalization_probability": self.cannibalization_probability,
            "net_incremental_posterior_mean": self.net_incremental_posterior_mean,
            "prob_top_contributor": self.prob_top_contributor,
            "prob_top_10_contributor": self.prob_top_10_contributor,
            "computed_at": self.computed_at.isoformat(),
            "model_version": self.model_version,
        }


# =============================================================================
# Entity-Specific Bayesian Output Classes
# =============================================================================

@dataclass
class CompanyBayesianOutputs:
    """
    Company-level Bayesian outputs (rollup over brands/geographies).
    """
    output_id: str = field(default_factory=generate_id)
    company_id: str = ""
    
    # Total KPI posteriors
    total_dollar_sales_posterior: Optional[PosteriorDistribution] = None
    total_volume_sales_posterior: Optional[PosteriorDistribution] = None
    
    # Lift posteriors by baseline
    lift_vs_prior_period: Optional[LiftDecomposition] = None
    lift_vs_year_ago: Optional[LiftDecomposition] = None
    
    # Category-level attribution (hierarchy1)
    category_attributions: List[DriverAttributionPosterior] = field(default_factory=list)
    
    # Driver-level attribution (hierarchy2)
    driver_attributions: List[DriverAttributionPosterior] = field(default_factory=list)
    
    # Scenario comparison outputs
    scenario_posteriors: Dict[str, PosteriorDistribution] = field(default_factory=dict)
    prob_optimized_beats_current: Optional[float] = None
    expected_optimization_lift: Optional[float] = None
    
    computed_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "output_id": self.output_id,
            "company_id": self.company_id,
            "total_dollar_sales_posterior": self.total_dollar_sales_posterior.to_dict() if self.total_dollar_sales_posterior else None,
            "total_volume_sales_posterior": self.total_volume_sales_posterior.to_dict() if self.total_volume_sales_posterior else None,
            "lift_vs_prior_period": self.lift_vs_prior_period.to_dict() if self.lift_vs_prior_period else None,
            "lift_vs_year_ago": self.lift_vs_year_ago.to_dict() if self.lift_vs_year_ago else None,
            "category_attributions": [a.to_dict() for a in self.category_attributions],
            "driver_attributions": [a.to_dict() for a in self.driver_attributions],
            "scenario_posteriors": {k: v.to_dict() for k, v in self.scenario_posteriors.items()},
            "prob_optimized_beats_current": self.prob_optimized_beats_current,
            "expected_optimization_lift": self.expected_optimization_lift,
            "computed_at": self.computed_at.isoformat(),
        }


@dataclass
class BrandBayesianOutputs:
    """
    Brand-level Bayesian outputs.
    
    Supports all outputs at Brand×RMN×Time×Metric×Measurement×Driver grain.
    """
    output_id: str = field(default_factory=generate_id)
    brand_id: str = ""
    brand_name: str = ""
    
    # Brand KPI posteriors by metric and baseline
    sales_baseline_posterior: Optional[PosteriorDistribution] = None  # counterfactual
    sales_actual_posterior: Optional[PosteriorDistribution] = None
    sales_lift_posterior: Optional[LiftDecomposition] = None
    
    # Brand driver attribution posteriors
    category_attributions: List[DriverAttributionPosterior] = field(default_factory=list)  # by hierarchy1
    driver_attributions: List[DriverAttributionPosterior] = field(default_factory=list)  # by hierarchy2
    rmn_channel_attributions: List[DriverAttributionPosterior] = field(default_factory=list)  # RMN channels
    
    # Brand effectiveness posteriors (matches Drivers tab)
    driver_effectiveness_posteriors: Dict[str, PosteriorDistribution] = field(default_factory=dict)
    driver_rankings: List[RankingPosterior] = field(default_factory=list)
    
    # With spend data attached
    incremental_sales_posterior: Optional[PosteriorDistribution] = None
    efficiency_posterior: Optional[PosteriorDistribution] = None  # incr $ / spend
    index_posterior: Optional[PosteriorDistribution] = None
    
    # Per-RMN posteriors
    rmn_posteriors: Dict[str, Dict[str, PosteriorDistribution]] = field(default_factory=dict)
    
    # Elasticity posteriors per channel
    elasticity_posteriors: Dict[str, PosteriorDistribution] = field(default_factory=dict)
    
    # Time context
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    metric_type: str = "dollar_sales"
    baseline_type: str = "prior_period"
    
    computed_at: datetime = field(default_factory=datetime.utcnow)
    model_version: str = "v1.0.0"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "output_id": self.output_id,
            "brand_id": self.brand_id,
            "brand_name": self.brand_name,
            "sales_baseline_posterior": self.sales_baseline_posterior.to_dict() if self.sales_baseline_posterior else None,
            "sales_actual_posterior": self.sales_actual_posterior.to_dict() if self.sales_actual_posterior else None,
            "sales_lift_posterior": self.sales_lift_posterior.to_dict() if self.sales_lift_posterior else None,
            "category_attributions": [a.to_dict() for a in self.category_attributions],
            "driver_attributions": [a.to_dict() for a in self.driver_attributions],
            "rmn_channel_attributions": [a.to_dict() for a in self.rmn_channel_attributions],
            "driver_effectiveness_posteriors": {k: v.to_dict() for k, v in self.driver_effectiveness_posteriors.items()},
            "driver_rankings": [r.to_dict() for r in self.driver_rankings],
            "incremental_sales_posterior": self.incremental_sales_posterior.to_dict() if self.incremental_sales_posterior else None,
            "efficiency_posterior": self.efficiency_posterior.to_dict() if self.efficiency_posterior else None,
            "index_posterior": self.index_posterior.to_dict() if self.index_posterior else None,
            "rmn_posteriors": {k: {kk: vv.to_dict() for kk, vv in v.items()} for k, v in self.rmn_posteriors.items()},
            "elasticity_posteriors": {k: v.to_dict() for k, v in self.elasticity_posteriors.items()},
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "metric_type": self.metric_type,
            "baseline_type": self.baseline_type,
            "computed_at": self.computed_at.isoformat(),
            "model_version": self.model_version,
        }


@dataclass
class RMNBayesianOutputs:
    """
    Retail Media Network level Bayesian outputs.
    """
    output_id: str = field(default_factory=generate_id)
    rmn_id: str = ""
    rmn_name: str = ""
    
    # RMN-level KPI posteriors
    incremental_sales_posterior: Optional[PosteriorDistribution] = None
    efficiency_posterior: Optional[PosteriorDistribution] = None
    index_posterior: Optional[PosteriorDistribution] = None
    
    # RMN contribution decomposition
    brand_mix_posteriors: Dict[str, PosteriorDistribution] = field(default_factory=dict)  # by brand
    channel_mix_posteriors: Dict[str, PosteriorDistribution] = field(default_factory=dict)  # by channel
    time_decomposition: Dict[str, PosteriorDistribution] = field(default_factory=dict)  # by period
    
    # Top performer probability outputs
    prob_best_overall: float = 0.0  # P(RMN is best overall)
    prob_best_for_brand: Dict[str, float] = field(default_factory=dict)  # P(RMN is best for brand b)
    channel_ranking_within_rmn: Dict[str, RankingPosterior] = field(default_factory=dict)
    
    # Driver attributions
    driver_attributions: List[DriverAttributionPosterior] = field(default_factory=list)
    
    # Per-brand posteriors at this RMN
    brand_posteriors: Dict[str, Dict[str, PosteriorDistribution]] = field(default_factory=dict)
    
    computed_at: datetime = field(default_factory=datetime.utcnow)
    model_version: str = "v1.0.0"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "output_id": self.output_id,
            "rmn_id": self.rmn_id,
            "rmn_name": self.rmn_name,
            "incremental_sales_posterior": self.incremental_sales_posterior.to_dict() if self.incremental_sales_posterior else None,
            "efficiency_posterior": self.efficiency_posterior.to_dict() if self.efficiency_posterior else None,
            "index_posterior": self.index_posterior.to_dict() if self.index_posterior else None,
            "brand_mix_posteriors": {k: v.to_dict() for k, v in self.brand_mix_posteriors.items()},
            "channel_mix_posteriors": {k: v.to_dict() for k, v in self.channel_mix_posteriors.items()},
            "time_decomposition": {k: v.to_dict() for k, v in self.time_decomposition.items()},
            "prob_best_overall": self.prob_best_overall,
            "prob_best_for_brand": self.prob_best_for_brand,
            "channel_ranking_within_rmn": {k: v.to_dict() for k, v in self.channel_ranking_within_rmn.items()},
            "driver_attributions": [a.to_dict() for a in self.driver_attributions],
            "brand_posteriors": {k: {kk: vv.to_dict() for kk, vv in v.items()} for k, v in self.brand_posteriors.items()},
            "computed_at": self.computed_at.isoformat(),
            "model_version": self.model_version,
        }


@dataclass
class ChannelBayesianOutputs:
    """
    Channel-level Bayesian outputs (RMN channels via hierarchy1='RETAIL MEDIA').
    """
    output_id: str = field(default_factory=generate_id)
    channel_id: str = ""
    channel_name: str = ""  # RMN SEARCH, RMN DISPLAY, RMN VIDEO, RMN EMAIL
    rmn_id: Optional[str] = None
    brand_id: Optional[str] = None
    
    # Channel performance posteriors
    incremental_sales_posterior: Optional[PosteriorDistribution] = None
    efficiency_posterior: Optional[PosteriorDistribution] = None
    index_posterior: Optional[PosteriorDistribution] = None
    
    # Elasticity posterior
    elasticity_posterior: Optional[PosteriorDistribution] = None
    
    # Channel response and stability
    variance_over_time_posterior: Optional[PosteriorDistribution] = None
    prob_efficiency_above_target: Optional[float] = None
    efficiency_target: Optional[float] = None
    
    # Channel contribution posteriors
    contribution_posterior: Optional[PosteriorDistribution] = None
    contribution_pct_posterior: Optional[PosteriorDistribution] = None
    
    # Rankings
    ranking_within_rmn: Optional[RankingPosterior] = None
    ranking_overall: Optional[RankingPosterior] = None
    
    # Driver attributions within this channel
    driver_attributions: List[DriverAttributionPosterior] = field(default_factory=list)
    
    computed_at: datetime = field(default_factory=datetime.utcnow)
    model_version: str = "v1.0.0"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "output_id": self.output_id,
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "rmn_id": self.rmn_id,
            "brand_id": self.brand_id,
            "incremental_sales_posterior": self.incremental_sales_posterior.to_dict() if self.incremental_sales_posterior else None,
            "efficiency_posterior": self.efficiency_posterior.to_dict() if self.efficiency_posterior else None,
            "index_posterior": self.index_posterior.to_dict() if self.index_posterior else None,
            "elasticity_posterior": self.elasticity_posterior.to_dict() if self.elasticity_posterior else None,
            "variance_over_time_posterior": self.variance_over_time_posterior.to_dict() if self.variance_over_time_posterior else None,
            "prob_efficiency_above_target": self.prob_efficiency_above_target,
            "efficiency_target": self.efficiency_target,
            "contribution_posterior": self.contribution_posterior.to_dict() if self.contribution_posterior else None,
            "contribution_pct_posterior": self.contribution_pct_posterior.to_dict() if self.contribution_pct_posterior else None,
            "ranking_within_rmn": self.ranking_within_rmn.to_dict() if self.ranking_within_rmn else None,
            "ranking_overall": self.ranking_overall.to_dict() if self.ranking_overall else None,
            "driver_attributions": [a.to_dict() for a in self.driver_attributions],
            "computed_at": self.computed_at.isoformat(),
            "model_version": self.model_version,
        }


@dataclass
class DriverBayesianOutputs:
    """
    Marketing Driver level Bayesian outputs (all hierarchy2 values).
    """
    output_id: str = field(default_factory=generate_id)
    driver_id: str = ""
    driver_name: str = ""
    driver_category_id: Optional[str] = None  # hierarchy1
    driver_category_name: Optional[str] = None
    
    # Driver contribution posteriors (by Brand, RMN, Time, Metric, Measurement)
    contribution_posteriors: Dict[str, DriverAttributionPosterior] = field(default_factory=dict)
    
    # Driver ranking outputs
    prob_rank_1_contributor: float = 0.0
    prob_top_10_contributor: float = 0.0
    ranking_posterior: Optional[RankingPosterior] = None
    
    # Driver classification outputs
    incremental_probability: float = 0.0  # probability this is true incremental
    cannibalization_probability: float = 0.0
    synergy_probability: Optional[float] = None  # for interaction drivers
    net_incremental_posterior: Optional[PosteriorDistribution] = None
    
    # Effectiveness by entity
    brand_effectiveness: Dict[str, PosteriorDistribution] = field(default_factory=dict)
    rmn_effectiveness: Dict[str, PosteriorDistribution] = field(default_factory=dict)
    
    computed_at: datetime = field(default_factory=datetime.utcnow)
    model_version: str = "v1.0.0"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "output_id": self.output_id,
            "driver_id": self.driver_id,
            "driver_name": self.driver_name,
            "driver_category_id": self.driver_category_id,
            "driver_category_name": self.driver_category_name,
            "contribution_posteriors": {k: v.to_dict() for k, v in self.contribution_posteriors.items()},
            "prob_rank_1_contributor": self.prob_rank_1_contributor,
            "prob_top_10_contributor": self.prob_top_10_contributor,
            "ranking_posterior": self.ranking_posterior.to_dict() if self.ranking_posterior else None,
            "incremental_probability": self.incremental_probability,
            "cannibalization_probability": self.cannibalization_probability,
            "synergy_probability": self.synergy_probability,
            "net_incremental_posterior": self.net_incremental_posterior.to_dict() if self.net_incremental_posterior else None,
            "brand_effectiveness": {k: v.to_dict() for k, v in self.brand_effectiveness.items()},
            "rmn_effectiveness": {k: v.to_dict() for k, v in self.rmn_effectiveness.items()},
            "computed_at": self.computed_at.isoformat(),
            "model_version": self.model_version,
        }


@dataclass
class DriverCategoryBayesianOutputs:
    """
    Marketing Driver Category level Bayesian outputs (all hierarchy1 values).
    """
    output_id: str = field(default_factory=generate_id)
    category_id: str = ""
    category_name: str = ""  # RETAIL MEDIA, PAID MEDIA, etc.
    
    # Category contribution posteriors
    contribution_posterior: Optional[PosteriorDistribution] = None
    contribution_pct_posterior: Optional[PosteriorDistribution] = None
    
    # Category effectiveness/ranking
    prob_top_category_overall: float = 0.0
    prob_top_category_for_brand: Dict[str, float] = field(default_factory=dict)
    ranking_posterior: Optional[RankingPosterior] = None
    
    # Drivers within this category
    driver_breakdown: Dict[str, DriverBayesianOutputs] = field(default_factory=dict)
    
    computed_at: datetime = field(default_factory=datetime.utcnow)
    model_version: str = "v1.0.0"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "output_id": self.output_id,
            "category_id": self.category_id,
            "category_name": self.category_name,
            "contribution_posterior": self.contribution_posterior.to_dict() if self.contribution_posterior else None,
            "contribution_pct_posterior": self.contribution_pct_posterior.to_dict() if self.contribution_pct_posterior else None,
            "prob_top_category_overall": self.prob_top_category_overall,
            "prob_top_category_for_brand": self.prob_top_category_for_brand,
            "ranking_posterior": self.ranking_posterior.to_dict() if self.ranking_posterior else None,
            "driver_breakdown": {k: v.to_dict() for k, v in self.driver_breakdown.items()},
            "computed_at": self.computed_at.isoformat(),
            "model_version": self.model_version,
        }


# =============================================================================
# Scenario/Optimization Bayesian Outputs
# =============================================================================

@dataclass
class ScenarioPosterior:
    """
    Bayesian posterior for a specific optimization scenario.
    """
    scenario_id: str = field(default_factory=generate_id)
    scenario_name: str = ""  # current|optimized|what_if
    scenario_type: str = ""  # baseline|optimized|stress_test
    
    # Entity context
    entity_type: str = ""
    entity_id: str = ""
    
    # Posterior distribution of outcomes
    incremental_sales_posterior: Optional[PosteriorDistribution] = None
    efficiency_posterior: Optional[PosteriorDistribution] = None
    roas_posterior: Optional[PosteriorDistribution] = None
    
    # Risk measures
    downside_risk_5pct: Optional[float] = None  # 5th percentile outcome
    downside_risk_10pct: Optional[float] = None  # 10th percentile outcome
    upside_potential_90pct: Optional[float] = None
    upside_potential_95pct: Optional[float] = None
    
    # Probability of hitting goals
    prob_revenue_increase: Optional[float] = None
    prob_margin_increase: Optional[float] = None
    prob_maintain_revenue: Optional[float] = None
    prob_reduce_cost: Optional[float] = None
    
    computed_at: datetime = field(default_factory=datetime.utcnow)
    model_version: str = "v1.0.0"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "scenario_type": self.scenario_type,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "incremental_sales_posterior": self.incremental_sales_posterior.to_dict() if self.incremental_sales_posterior else None,
            "efficiency_posterior": self.efficiency_posterior.to_dict() if self.efficiency_posterior else None,
            "roas_posterior": self.roas_posterior.to_dict() if self.roas_posterior else None,
            "downside_risk_5pct": self.downside_risk_5pct,
            "downside_risk_10pct": self.downside_risk_10pct,
            "upside_potential_90pct": self.upside_potential_90pct,
            "upside_potential_95pct": self.upside_potential_95pct,
            "prob_revenue_increase": self.prob_revenue_increase,
            "prob_margin_increase": self.prob_margin_increase,
            "prob_maintain_revenue": self.prob_maintain_revenue,
            "prob_reduce_cost": self.prob_reduce_cost,
            "computed_at": self.computed_at.isoformat(),
            "model_version": self.model_version,
        }


@dataclass
class ScenarioComparison:
    """
    Comparison between current and optimized scenarios.
    """
    comparison_id: str = field(default_factory=generate_id)
    entity_type: str = ""
    entity_id: str = ""
    
    # Scenario references
    current_scenario: Optional[ScenarioPosterior] = None
    optimized_scenario: Optional[ScenarioPosterior] = None
    
    # Expected value of the decision
    expected_incremental_sales_delta: float = 0.0
    expected_delta_ci_lower: float = 0.0
    expected_delta_ci_upper: float = 0.0
    
    expected_efficiency_delta: float = 0.0
    
    # Probability comparisons
    prob_optimized_beats_current: float = 0.0
    prob_optimized_beats_current_by_5pct: Optional[float] = None
    prob_optimized_beats_current_by_10pct: Optional[float] = None
    
    # Risk measures
    prob_underperforming_constraint: Optional[float] = None
    constraint_description: Optional[str] = None
    
    # Allocation recommendations (Bayesian decisioning)
    recommended_allocation: Dict[str, float] = field(default_factory=dict)  # by RMN/Channel/Brand
    allocation_posterior_samples: Optional[List[Dict[str, float]]] = None  # samples from posterior of optimal allocation
    
    computed_at: datetime = field(default_factory=datetime.utcnow)
    model_version: str = "v1.0.0"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "comparison_id": self.comparison_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "current_scenario": self.current_scenario.to_dict() if self.current_scenario else None,
            "optimized_scenario": self.optimized_scenario.to_dict() if self.optimized_scenario else None,
            "expected_incremental_sales_delta": self.expected_incremental_sales_delta,
            "expected_delta_ci": [self.expected_delta_ci_lower, self.expected_delta_ci_upper],
            "expected_efficiency_delta": self.expected_efficiency_delta,
            "prob_optimized_beats_current": self.prob_optimized_beats_current,
            "prob_optimized_beats_current_by_5pct": self.prob_optimized_beats_current_by_5pct,
            "prob_optimized_beats_current_by_10pct": self.prob_optimized_beats_current_by_10pct,
            "prob_underperforming_constraint": self.prob_underperforming_constraint,
            "constraint_description": self.constraint_description,
            "recommended_allocation": self.recommended_allocation,
            "allocation_posterior_samples": self.allocation_posterior_samples,
            "computed_at": self.computed_at.isoformat(),
            "model_version": self.model_version,
        }


# =============================================================================
# Time-Period Bayesian Outputs
# =============================================================================

@dataclass
class TimePeriodBayesianOutputs:
    """
    Time-period level Bayesian outputs for seasonality and trend.
    """
    output_id: str = field(default_factory=generate_id)
    entity_type: str = ""
    entity_id: str = ""
    period_start: date = field(default_factory=date.today)
    period_end: Optional[date] = None
    time_grain: str = "week"
    
    # Seasonality posterior
    seasonality_posterior_mean: float = 0.0
    seasonality_posterior_std: float = 0.0
    seasonality_ci_lower: float = 0.0
    seasonality_ci_upper: float = 0.0
    
    # Trend posterior
    trend_posterior_mean: float = 0.0
    trend_posterior_std: float = 0.0
    trend_ci_lower: float = 0.0
    trend_ci_upper: float = 0.0
    
    # Shock/anomaly posterior
    anomaly_probability: float = 0.0
    anomaly_magnitude_posterior_mean: Optional[float] = None
    
    # Time-varying driver effects
    time_varying_effects: Dict[str, PosteriorDistribution] = field(default_factory=dict)
    
    computed_at: datetime = field(default_factory=datetime.utcnow)
    model_version: str = "v1.0.0"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "output_id": self.output_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "time_grain": self.time_grain,
            "seasonality_posterior": {
                "mean": self.seasonality_posterior_mean,
                "std": self.seasonality_posterior_std,
                "ci": [self.seasonality_ci_lower, self.seasonality_ci_upper],
            },
            "trend_posterior": {
                "mean": self.trend_posterior_mean,
                "std": self.trend_posterior_std,
                "ci": [self.trend_ci_lower, self.trend_ci_upper],
            },
            "anomaly_probability": self.anomaly_probability,
            "anomaly_magnitude_posterior_mean": self.anomaly_magnitude_posterior_mean,
            "time_varying_effects": {k: v.to_dict() for k, v in self.time_varying_effects.items()},
            "computed_at": self.computed_at.isoformat(),
            "model_version": self.model_version,
        }


# =============================================================================
# Posterior Predictive Outputs
# =============================================================================

@dataclass
class PosteriorPredictive:
    """
    Posterior predictive distribution for forecasting.
    """
    predictive_id: str = field(default_factory=generate_id)
    entity_type: str = ""
    entity_id: str = ""
    kpi_name: str = ""
    
    # Forecast horizon
    forecast_start: date = field(default_factory=date.today)
    forecast_end: Optional[date] = None
    n_periods: int = 0
    time_grain: str = "week"
    
    # Posterior predictive distribution
    predictive_mean: float = 0.0
    predictive_std: float = 0.0
    prediction_interval_lower: float = 0.0  # e.g., 5th percentile
    prediction_interval_upper: float = 0.0  # e.g., 95th percentile
    
    # Period-by-period forecasts
    period_forecasts: List[Dict[str, Any]] = field(default_factory=list)
    
    # Probability of hitting goals
    prob_hitting_target: Optional[float] = None
    target_value: Optional[float] = None
    
    # Model uncertainty contribution
    parameter_uncertainty: float = 0.0
    observation_uncertainty: float = 0.0
    
    computed_at: datetime = field(default_factory=datetime.utcnow)
    model_version: str = "v1.0.0"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "predictive_id": self.predictive_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "kpi_name": self.kpi_name,
            "forecast_start": self.forecast_start.isoformat(),
            "forecast_end": self.forecast_end.isoformat() if self.forecast_end else None,
            "n_periods": self.n_periods,
            "time_grain": self.time_grain,
            "predictive_mean": self.predictive_mean,
            "predictive_std": self.predictive_std,
            "prediction_interval": [self.prediction_interval_lower, self.prediction_interval_upper],
            "period_forecasts": self.period_forecasts,
            "prob_hitting_target": self.prob_hitting_target,
            "target_value": self.target_value,
            "parameter_uncertainty": self.parameter_uncertainty,
            "observation_uncertainty": self.observation_uncertainty,
            "computed_at": self.computed_at.isoformat(),
            "model_version": self.model_version,
        }


# =============================================================================
# Master Bayesian State Container
# =============================================================================

@dataclass
class EntityBayesianState:
    """
    Master container for all Bayesian outputs for a digital twin entity.
    
    This class aggregates all Bayesian posteriors and connects them to the
    digital twin for real-time state updates.
    """
    state_id: str = field(default_factory=generate_id)
    entity_type: str = ""  # company|brand|rmn|channel|driver|category
    entity_id: str = ""
    entity_name: str = ""
    
    # Core posteriors
    primary_kpi_posteriors: Dict[str, PosteriorDistribution] = field(default_factory=dict)
    lift_decompositions: Dict[str, LiftDecomposition] = field(default_factory=dict)
    driver_attributions: List[DriverAttributionPosterior] = field(default_factory=list)
    
    # Rankings
    rankings: List[RankingPosterior] = field(default_factory=list)
    
    # Scenarios
    scenario_posteriors: Dict[str, ScenarioPosterior] = field(default_factory=dict)
    scenario_comparison: Optional[ScenarioComparison] = None
    
    # Time series
    time_period_outputs: List[TimePeriodBayesianOutputs] = field(default_factory=list)
    
    # Forecasts
    predictive_distributions: Dict[str, PosteriorPredictive] = field(default_factory=dict)
    
    # Metadata
    last_updated: datetime = field(default_factory=datetime.utcnow)
    model_version: str = "v1.0.0"
    data_version: Optional[str] = None
    n_observations: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "state_id": self.state_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "primary_kpi_posteriors": {k: v.to_dict() for k, v in self.primary_kpi_posteriors.items()},
            "lift_decompositions": {k: v.to_dict() for k, v in self.lift_decompositions.items()},
            "driver_attributions": [a.to_dict() for a in self.driver_attributions],
            "rankings": [r.to_dict() for r in self.rankings],
            "scenario_posteriors": {k: v.to_dict() for k, v in self.scenario_posteriors.items()},
            "scenario_comparison": self.scenario_comparison.to_dict() if self.scenario_comparison else None,
            "time_period_outputs": [t.to_dict() for t in self.time_period_outputs],
            "predictive_distributions": {k: v.to_dict() for k, v in self.predictive_distributions.items()},
            "last_updated": self.last_updated.isoformat(),
            "model_version": self.model_version,
            "data_version": self.data_version,
            "n_observations": self.n_observations,
        }
