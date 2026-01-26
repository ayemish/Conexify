"""
Retail Media Bayesian Analysis Layer

Implements Bayesian inference for:
- Channel elasticity estimation with uncertainty
- Multi-touch attribution with Dirichlet posteriors
- Federated aggregation of retailer-specific posteriors
- Inventory-adjusted priors for achievable lift
"""

import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, date
import logging
from scipy import stats
from scipy.special import digamma, gammaln

from .schemas import (
    MediaChannel,
    RetailerConfig,
    ChannelConfig,
    SKUConfig,
    ElasticityPosterior,
    AttributionResult,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class BayesianEngineConfig:
    """Configuration for retail media Bayesian engine"""
    # Sampling settings
    num_samples: int = 5000
    burn_in: int = 1000
    
    # Prior settings
    elasticity_prior_mean: float = 0.15
    elasticity_prior_std: float = 0.05
    
    # Attribution prior (Dirichlet concentration)
    attribution_prior_alpha: float = 1.0  # Uniform prior
    
    # Federated learning settings
    aggregation_method: str = "precision_weighted"  # precision_weighted, simple_average
    min_observations_for_update: int = 10
    
    # Credible interval
    credible_interval: float = 0.90


class ChannelElasticityModel:
    """
    Bayesian model for channel elasticity estimation.
    
    Models the relationship: 
        log(sales_lift) ~ Normal(η * log(spend), σ²)
    
    Where η is the elasticity parameter with a LogNormal prior.
    """
    
    def __init__(self, config: Optional[BayesianEngineConfig] = None):
        self.config = config or BayesianEngineConfig()
        self.posteriors: Dict[str, ElasticityPosterior] = {}
        
    def update_posterior(
        self,
        retailer_id: str,
        channel: MediaChannel,
        category: str,
        spend_history: np.ndarray,
        sales_lift_history: np.ndarray,
        prior: Optional[ElasticityPosterior] = None
    ) -> ElasticityPosterior:
        """
        Update elasticity posterior given new spend/lift observations.
        
        Uses conjugate Normal-Normal update for log-transformed data.
        """
        n_obs = len(spend_history)
        
        if n_obs < self.config.min_observations_for_update:
            # Return prior if insufficient data
            if prior:
                return prior
            return self._get_default_prior(retailer_id, channel, category)
        
        # Log-transform for elasticity estimation (use small epsilon to avoid log(0))
        eps = 1e-6
        log_spend = np.log(np.maximum(spend_history, eps))
        log_lift = np.log(np.maximum(sales_lift_history, eps))
        
        # Simple linear regression for elasticity
        # log(lift) = η * log(spend) + ε
        X = log_spend.reshape(-1, 1)
        y = log_lift
        
        # OLS estimate
        X_with_intercept = np.column_stack([np.ones(n_obs), X])
        try:
            # Check for sufficient variance in X
            if np.var(log_spend) < 1e-10:
                raise np.linalg.LinAlgError("Insufficient variance in spend data")
            
            beta = np.linalg.lstsq(X_with_intercept, y, rcond=None)[0]
            elasticity_ols = beta[1]
            
            # Ensure elasticity is reasonable
            if np.isnan(elasticity_ols) or np.isinf(elasticity_ols):
                raise np.linalg.LinAlgError("Invalid elasticity estimate")
            
            # Clamp elasticity to reasonable range
            elasticity_ols = np.clip(elasticity_ols, -1.0, 2.0)
            
            # Residual variance
            residuals = y - X_with_intercept @ beta
            sigma_sq = max(np.var(residuals), 1e-6)
            
            # Standard error of elasticity estimate
            XtX_inv = np.linalg.inv(X_with_intercept.T @ X_with_intercept)
            se_elasticity = np.sqrt(max(sigma_sq * XtX_inv[1, 1], 1e-6))
        except (np.linalg.LinAlgError, ValueError):
            # Fallback to simple ratio estimate
            mean_log_spend = np.mean(log_spend)
            mean_log_lift = np.mean(log_lift)
            if abs(mean_log_spend) > 1e-6:
                elasticity_ols = mean_log_lift / mean_log_spend
                elasticity_ols = np.clip(elasticity_ols, 0.01, 1.0)
            else:
                elasticity_ols = self.config.elasticity_prior_mean
            se_elasticity = self.config.elasticity_prior_std
        
        # Bayesian update: combine prior with likelihood
        if prior:
            prior_mean = prior.mean
            prior_var = prior.std ** 2
        else:
            prior_mean = self.config.elasticity_prior_mean
            prior_var = self.config.elasticity_prior_std ** 2
        
        likelihood_var = se_elasticity ** 2
        
        # Precision-weighted combination
        prior_precision = 1.0 / prior_var
        likelihood_precision = 1.0 / likelihood_var
        
        posterior_precision = prior_precision + likelihood_precision
        posterior_mean = (prior_precision * prior_mean + likelihood_precision * elasticity_ols) / posterior_precision
        posterior_var = 1.0 / posterior_precision
        posterior_std = np.sqrt(posterior_var)
        
        # Compute credible interval
        z = stats.norm.ppf(1 - (1 - self.config.credible_interval) / 2)
        ci_lower = max(0.01, posterior_mean - z * posterior_std)
        ci_upper = posterior_mean + z * posterior_std
        
        # Evidence strength based on sample size and prior-likelihood agreement
        evidence_strength = min(1.0, n_obs / 100) * (1 - abs(prior_mean - elasticity_ols) / prior_mean)
        evidence_strength = max(0.1, min(1.0, evidence_strength))
        
        posterior = ElasticityPosterior(
            retailer_id=retailer_id,
            channel=channel,
            category=category,
            mean=float(posterior_mean),
            std=float(posterior_std),
            ci_lower=float(ci_lower),
            ci_upper=float(ci_upper),
            n_observations=n_obs,
            evidence_strength=float(evidence_strength),
            model_version="elasticity-v1.0.0",
            updated_at=datetime.utcnow()
        )
        
        # Cache the posterior
        key = f"{retailer_id}:{channel.value}:{category}"
        self.posteriors[key] = posterior
        
        logger.info(f"Updated elasticity posterior for {key}: mean={posterior_mean:.3f}, std={posterior_std:.3f}")
        
        return posterior
    
    def _get_default_prior(
        self,
        retailer_id: str,
        channel: MediaChannel,
        category: str
    ) -> ElasticityPosterior:
        """Get default prior for a channel-category combination"""
        # Channel-specific priors based on industry benchmarks
        channel_priors = {
            MediaChannel.SPONSORED_SEARCH: (0.18, 0.04),
            MediaChannel.IN_STORE_DISPLAY: (0.22, 0.06),
            MediaChannel.CONNECTED_TV: (0.10, 0.05),
            MediaChannel.EMAIL: (0.12, 0.03),
            MediaChannel.APP_NOTIFICATION: (0.08, 0.03),
            MediaChannel.WEBSITE_BANNER: (0.06, 0.03),
            MediaChannel.SOCIAL_MEDIA: (0.14, 0.05),
            MediaChannel.DIGITAL_ENDCAP: (0.16, 0.05),
        }
        
        mean, std = channel_priors.get(channel, (0.15, 0.05))
        
        z = stats.norm.ppf(1 - (1 - self.config.credible_interval) / 2)
        
        return ElasticityPosterior(
            retailer_id=retailer_id,
            channel=channel,
            category=category,
            mean=mean,
            std=std,
            ci_lower=max(0.01, mean - z * std),
            ci_upper=mean + z * std,
            n_observations=0,
            evidence_strength=0.3,  # Low confidence for prior
            model_version="elasticity-prior-v1.0.0",
            updated_at=datetime.utcnow()
        )
    
    def get_posterior(
        self,
        retailer_id: str,
        channel: MediaChannel,
        category: str
    ) -> Optional[ElasticityPosterior]:
        """Get cached posterior for a retailer-channel-category"""
        key = f"{retailer_id}:{channel.value}:{category}"
        return self.posteriors.get(key)


class BayesianAttributionModel:
    """
    Bayesian multi-touch attribution using Dirichlet-Multinomial model.
    
    Models channel contribution shares with uncertainty:
        α ~ Dirichlet(α_prior)
        conversions ~ Multinomial(n, α)
    """
    
    def __init__(self, config: Optional[BayesianEngineConfig] = None):
        self.config = config or BayesianEngineConfig()
        self.channel_order: List[MediaChannel] = list(MediaChannel)
    
    def compute_attribution(
        self,
        conversion_paths: List[List[str]],
        spend_by_channel: Dict[str, float],
        total_sales: float,
        prior_alpha: Optional[Dict[str, float]] = None
    ) -> AttributionResult:
        """
        Compute Bayesian attribution from conversion paths.
        
        Args:
            conversion_paths: List of paths, each path is list of channel touches
            spend_by_channel: Spend per channel
            total_sales: Total incremental sales to attribute
            prior_alpha: Optional Dirichlet prior concentrations
        
        Returns:
            AttributionResult with posterior channel shares
        """
        n_channels = len(self.channel_order)
        channels = [c.value for c in self.channel_order]
        
        # Initialize prior
        if prior_alpha:
            alpha_prior = np.array([prior_alpha.get(c, self.config.attribution_prior_alpha) for c in channels])
        else:
            alpha_prior = np.ones(n_channels) * self.config.attribution_prior_alpha
        
        # Count channel touches (simple position-based weighting)
        touch_counts = np.zeros(n_channels)
        
        for path in conversion_paths:
            path_length = len(path)
            if path_length == 0:
                continue
            
            # Position-based weights: last touch gets 40%, first gets 20%, middle splits 40%
            for i, channel in enumerate(path):
                try:
                    channel_idx = channels.index(channel)
                except ValueError:
                    continue
                
                if path_length == 1:
                    weight = 1.0
                elif i == path_length - 1:  # Last touch
                    weight = 0.4
                elif i == 0:  # First touch
                    weight = 0.2
                else:  # Middle touches
                    weight = 0.4 / (path_length - 2) if path_length > 2 else 0.2
                
                touch_counts[channel_idx] += weight
        
        # Posterior is Dirichlet with updated concentrations
        alpha_posterior = alpha_prior + touch_counts
        
        # Compute posterior means (expected shares)
        posterior_mean = alpha_posterior / alpha_posterior.sum()
        
        # Compute credible intervals via sampling
        samples = np.random.dirichlet(alpha_posterior, size=self.config.num_samples)
        ci_lower = np.percentile(samples, 5, axis=0)
        ci_upper = np.percentile(samples, 95, axis=0)
        
        # Build result
        channel_shares = {channels[i]: float(posterior_mean[i]) for i in range(n_channels)}
        channel_share_ci = {
            channels[i]: (float(ci_lower[i]), float(ci_upper[i]))
            for i in range(n_channels)
        }
        
        # Compute ROAS
        total_spend = sum(spend_by_channel.values())
        overall_roas = total_sales / total_spend if total_spend > 0 else 0.0
        
        # Attribution confidence based on evidence (number of paths)
        n_paths = len(conversion_paths)
        attribution_confidence = min(1.0, n_paths / 1000)
        
        # Detect anomalies
        anomalies = self._detect_anomalies(
            channel_shares, channel_share_ci, spend_by_channel, total_sales
        )
        
        return AttributionResult(
            period_start=date.today(),
            period_end=date.today(),
            channel_shares=channel_shares,
            channel_share_ci=channel_share_ci,
            total_incremental_sales=total_sales,
            total_spend=total_spend,
            overall_roas=overall_roas,
            attribution_confidence=attribution_confidence,
            anomalies=anomalies,
            model_version="attribution-v1.0.0"
        )
    
    def _detect_anomalies(
        self,
        shares: Dict[str, float],
        share_ci: Dict[str, Tuple[float, float]],
        spend: Dict[str, float],
        total_sales: float
    ) -> List[Dict[str, Any]]:
        """Detect anomalies in attribution results"""
        anomalies = []
        total_spend = sum(spend.values())
        
        for channel, share in shares.items():
            channel_spend = spend.get(channel, 0.0)
            spend_share = channel_spend / total_spend if total_spend > 0 else 0.0
            
            # Check for high variance
            ci = share_ci.get(channel, (0, 1))
            ci_width = ci[1] - ci[0]
            if ci_width > 0.3:
                anomalies.append({
                    'type': 'high_variance',
                    'channel': channel,
                    'message': f'{channel} attribution has high uncertainty (CI width: {ci_width:.1%})',
                    'severity': 'warning'
                })
            
            # Check for attribution-spend mismatch
            if spend_share > 0.1 and share < spend_share * 0.3:
                anomalies.append({
                    'type': 'low_efficiency',
                    'channel': channel,
                    'message': f'{channel} receives {spend_share:.1%} of spend but only {share:.1%} attribution',
                    'severity': 'warning'
                })
        
        return anomalies


class FederatedElasticityAggregator:
    """
    Aggregates elasticity posteriors across multiple retailers
    without sharing raw data.
    
    Implements federated Bayesian aggregation:
    - Each retailer computes local posterior
    - Central aggregator combines posteriors using precision weighting
    - Returns global posterior that benefits from all retailers' data
    """
    
    def __init__(self, config: Optional[BayesianEngineConfig] = None):
        self.config = config or BayesianEngineConfig()
        self.retailer_posteriors: Dict[str, Dict[str, ElasticityPosterior]] = {}
    
    def register_retailer_posterior(
        self,
        retailer_id: str,
        posterior: ElasticityPosterior
    ):
        """Register a retailer's local posterior for aggregation"""
        key = f"{posterior.channel.value}:{posterior.category}"
        
        if retailer_id not in self.retailer_posteriors:
            self.retailer_posteriors[retailer_id] = {}
        
        self.retailer_posteriors[retailer_id][key] = posterior
        logger.info(f"Registered posterior from {retailer_id} for {key}")
    
    def aggregate_posteriors(
        self,
        channel: MediaChannel,
        category: str,
        retailer_weights: Optional[Dict[str, float]] = None
    ) -> ElasticityPosterior:
        """
        Aggregate retailer posteriors into a global posterior.
        
        Uses precision-weighted combination for Normal approximations.
        """
        key = f"{channel.value}:{category}"
        
        # Collect posteriors for this channel-category
        posteriors = []
        weights = []
        
        for retailer_id, retailer_posts in self.retailer_posteriors.items():
            if key in retailer_posts:
                post = retailer_posts[key]
                posteriors.append(post)
                
                # Weight by sample size and data quality
                base_weight = retailer_weights.get(retailer_id, 1.0) if retailer_weights else 1.0
                weight = base_weight * post.evidence_strength * np.sqrt(post.n_observations + 1)
                weights.append(weight)
        
        if not posteriors:
            # Return uninformative prior
            return ElasticityPosterior(
                retailer_id="global",
                channel=channel,
                category=category,
                mean=self.config.elasticity_prior_mean,
                std=self.config.elasticity_prior_std,
                ci_lower=0.05,
                ci_upper=0.25,
                n_observations=0,
                evidence_strength=0.1,
                model_version="federated-prior-v1.0.0"
            )
        
        weights = np.array(weights)
        weights = weights / weights.sum()
        
        if self.config.aggregation_method == "precision_weighted":
            # Precision-weighted aggregation (with floor on std to avoid div by zero)
            min_std = 1e-4
            precisions = np.array([1.0 / max(p.std, min_std) ** 2 for p in posteriors])
            weighted_precisions = precisions * weights
            
            global_precision = np.sum(weighted_precisions)
            if global_precision < 1e-10:
                global_precision = 1.0 / (self.config.elasticity_prior_std ** 2)
            
            global_var = 1.0 / global_precision
            global_std = np.sqrt(global_var)
            
            weighted_means = np.array([p.mean * weighted_precisions[i] for i, p in enumerate(posteriors)])
            global_mean = np.sum(weighted_means) / global_precision
            
            # Ensure valid values
            if np.isnan(global_mean) or np.isinf(global_mean):
                global_mean = np.mean([p.mean for p in posteriors])
            if np.isnan(global_std) or np.isinf(global_std) or global_std < min_std:
                global_std = self.config.elasticity_prior_std
            
        else:
            # Simple weighted average
            global_mean = sum(w * p.mean for w, p in zip(weights, posteriors))
            global_var = sum(w * p.std ** 2 for w, p in zip(weights, posteriors))
            global_std = np.sqrt(global_var)
        
        # Credible interval
        z = stats.norm.ppf(1 - (1 - self.config.credible_interval) / 2)
        ci_lower = max(0.01, global_mean - z * global_std)
        ci_upper = global_mean + z * global_std
        
        # Total observations and evidence
        total_obs = sum(p.n_observations for p in posteriors)
        avg_evidence = np.mean([p.evidence_strength for p in posteriors])
        
        return ElasticityPosterior(
            retailer_id="global",
            channel=channel,
            category=category,
            mean=float(global_mean),
            std=float(global_std),
            ci_lower=float(ci_lower),
            ci_upper=float(ci_upper),
            n_observations=total_obs,
            evidence_strength=float(avg_evidence),
            model_version="federated-v1.0.0",
            updated_at=datetime.utcnow()
        )
    
    def get_all_global_posteriors(
        self,
        retailer_weights: Optional[Dict[str, float]] = None
    ) -> Dict[str, ElasticityPosterior]:
        """Aggregate all channel-category combinations"""
        # Collect all unique channel-category keys
        all_keys = set()
        for retailer_posts in self.retailer_posteriors.values():
            all_keys.update(retailer_posts.keys())
        
        global_posteriors = {}
        for key in all_keys:
            channel_str, category = key.split(":", 1)
            channel = MediaChannel(channel_str)
            global_posteriors[key] = self.aggregate_posteriors(
                channel, category, retailer_weights
            )
        
        return global_posteriors


class RetailMediaBayesianEngine:
    """
    Main Bayesian engine for retail media optimization.
    
    Coordinates:
    - Channel elasticity estimation
    - Multi-touch attribution
    - Federated aggregation
    - Inventory-adjusted priors
    """
    
    def __init__(self, config: Optional[BayesianEngineConfig] = None):
        self.config = config or BayesianEngineConfig()
        
        self.elasticity_model = ChannelElasticityModel(config)
        self.attribution_model = BayesianAttributionModel(config)
        self.federated_aggregator = FederatedElasticityAggregator(config)
        
        # Retailer and channel configs
        self.retailers: Dict[str, RetailerConfig] = {}
        self.channels: Dict[MediaChannel, ChannelConfig] = {}
        self.skus: Dict[str, SKUConfig] = {}
        
        logger.info("RetailMediaBayesianEngine initialized")
    
    def register_retailer(self, config: RetailerConfig):
        """Register a retailer configuration"""
        self.retailers[config.retailer_id] = config
        logger.info(f"Registered retailer: {config.retailer_id}")
    
    def register_channel(self, config: ChannelConfig):
        """Register a channel configuration"""
        self.channels[config.channel] = config
        logger.info(f"Registered channel: {config.channel.value}")
    
    def register_sku(self, config: SKUConfig):
        """Register a SKU configuration"""
        self.skus[config.sku_id] = config
        logger.info(f"Registered SKU: {config.sku_id}")
    
    def update_elasticity_from_data(
        self,
        retailer_id: str,
        channel: MediaChannel,
        category: str,
        spend_history: np.ndarray,
        sales_lift_history: np.ndarray
    ) -> ElasticityPosterior:
        """
        Update elasticity posterior from new spend/sales data.
        
        This is called by each retailer with their local data.
        """
        posterior = self.elasticity_model.update_posterior(
            retailer_id=retailer_id,
            channel=channel,
            category=category,
            spend_history=spend_history,
            sales_lift_history=sales_lift_history
        )
        
        # Register for federated aggregation
        self.federated_aggregator.register_retailer_posterior(retailer_id, posterior)
        
        return posterior
    
    def get_elasticity_posterior(
        self,
        retailer_id: str,
        channel: MediaChannel,
        category: str,
        use_federated: bool = True
    ) -> ElasticityPosterior:
        """
        Get elasticity posterior for a retailer-channel-category.
        
        If use_federated=True and no retailer-specific posterior exists,
        returns the federated global posterior.
        """
        # Try retailer-specific first
        posterior = self.elasticity_model.get_posterior(retailer_id, channel, category)
        
        if posterior is not None:
            return posterior
        
        # Fall back to federated global
        if use_federated:
            return self.federated_aggregator.aggregate_posteriors(channel, category)
        
        # Return prior
        return self.elasticity_model._get_default_prior(retailer_id, channel, category)
    
    def compute_attribution(
        self,
        conversion_paths: List[List[str]],
        spend_by_channel: Dict[str, float],
        total_incremental_sales: float
    ) -> AttributionResult:
        """Compute multi-touch attribution"""
        return self.attribution_model.compute_attribution(
            conversion_paths=conversion_paths,
            spend_by_channel=spend_by_channel,
            total_sales=total_incremental_sales
        )
    
    def get_inventory_adjusted_elasticity(
        self,
        retailer_id: str,
        channel: MediaChannel,
        category: str,
        current_inventory_weeks: float,
        stockout_probability: float
    ) -> ElasticityPosterior:
        """
        Adjust elasticity posterior for inventory constraints.
        
        If stockout risk is high, effective elasticity is reduced
        because we can't fulfill the demand we'd generate.
        """
        base_posterior = self.get_elasticity_posterior(retailer_id, channel, category)
        
        # Adjustment factor based on stockout risk
        # If 20% stockout probability, we can only realize 80% of the lift
        fulfillment_rate = 1.0 - stockout_probability
        
        # Also adjust for low inventory
        if current_inventory_weeks < 2:
            inventory_penalty = current_inventory_weeks / 2
        else:
            inventory_penalty = 1.0
        
        adjustment_factor = fulfillment_rate * inventory_penalty
        
        adjusted_mean = base_posterior.mean * adjustment_factor
        adjusted_std = base_posterior.std * adjustment_factor
        
        return ElasticityPosterior(
            retailer_id=retailer_id,
            channel=channel,
            category=category,
            mean=adjusted_mean,
            std=adjusted_std,
            ci_lower=base_posterior.ci_lower * adjustment_factor,
            ci_upper=base_posterior.ci_upper * adjustment_factor,
            n_observations=base_posterior.n_observations,
            evidence_strength=base_posterior.evidence_strength * 0.9,  # Slight reduction due to adjustment
            model_version=f"{base_posterior.model_version}-inventory-adjusted",
            updated_at=datetime.utcnow()
        )
    
    def get_all_posteriors_for_twin(
        self,
        retailer_ids: Optional[List[str]] = None,
        categories: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, ElasticityPosterior]]:
        """
        Get all posteriors formatted for Digital Twin consumption.
        
        Returns: {retailer_id: {channel:category: ElasticityPosterior}}
        """
        retailers = retailer_ids or list(self.retailers.keys())
        cats = categories or list(set(s.category for s in self.skus.values()))
        
        result = {}
        
        for retailer_id in retailers:
            result[retailer_id] = {}
            
            retailer = self.retailers.get(retailer_id)
            channels = retailer.available_channels if retailer else list(MediaChannel)
            
            for channel in channels:
                for category in cats:
                    key = f"{channel.value}:{category}"
                    result[retailer_id][key] = self.get_elasticity_posterior(
                        retailer_id, channel, category
                    )
        
        return result
    
    def compute_scenario_prior_weights(
        self,
        scenarios: List[str],
        recent_signals: Optional[Dict[str, float]] = None
    ) -> Dict[str, float]:
        """
        Compute Bayesian-informed weights for which scenarios to simulate.
        
        Higher weight = more posterior probability mass = more simulation budget.
        """
        # Default uniform weights
        weights = {s: 1.0 / len(scenarios) for s in scenarios}
        
        if recent_signals:
            # Adjust based on signals
            if recent_signals.get('demand_volatility', 0) > 0.2:
                weights['demand_surge'] = weights.get('demand_surge', 0) + 0.2
            
            if recent_signals.get('supply_chain_stress', 0) > 0.3:
                weights['supply_disruption'] = weights.get('supply_disruption', 0) + 0.2
            
            # Renormalize
            total = sum(weights.values())
            weights = {k: v / total for k, v in weights.items()}
        
        return weights
