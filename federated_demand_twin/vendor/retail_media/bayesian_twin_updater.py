"""
Bayesian-to-Digital-Twin Updater

This module connects Bayesian analysis outputs to digital twin entity updates,
ensuring that posterior distributions flow into twin state management.

The updater:
1. Receives Bayesian posterior outputs from the analysis engine
2. Maps posteriors to the appropriate digital twin entities
3. Updates twin state with new posterior values
4. Maintains audit trail of updates
5. Triggers downstream state propagation

Entity update flow:
- Company → aggregate all brand posteriors
- Brand → aggregate RMN-specific posteriors  
- RMN → aggregate channel posteriors
- Channel → direct elasticity/contribution updates
- Driver → direct attribution updates
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4
import numpy as np

from .bayesian_outputs import (
    PosteriorDistribution,
    LiftDecomposition,
    DriverAttributionPosterior,
    RankingPosterior,
    BrandBayesianOutputs,
    RMNBayesianOutputs,
    ChannelBayesianOutputs,
    DriverBayesianOutputs,
    ScenarioPosterior,
    ScenarioComparison,
    EntityBayesianState,
)
from .rmn_schemas import (
    BrandTwin,
    RetailMediaNetworkTwin,
    ChannelTwin,
    CompanyTwin,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class BayesianUpdateConfig:
    """Configuration for Bayesian twin updates."""
    # Update thresholds
    min_observations_for_update: int = 10
    min_evidence_strength: float = 0.3
    
    # Credible interval level
    ci_level: float = 0.90
    
    # Update frequency
    update_on_every_posterior: bool = True
    batch_updates: bool = False
    
    # Audit settings
    enable_audit_trail: bool = True
    max_audit_history: int = 100


@dataclass 
class BayesianUpdateAudit:
    """Audit record for a Bayesian twin update."""
    audit_id: str = field(default_factory=lambda: str(uuid4()))
    entity_type: str = ""
    entity_id: str = ""
    update_type: str = ""  # posterior|lift|attribution|ranking|scenario
    field_name: str = ""
    old_value: Optional[float] = None
    new_value: Optional[float] = None
    posterior_mean: Optional[float] = None
    posterior_std: Optional[float] = None
    evidence_strength: Optional[float] = None
    n_observations: Optional[int] = None
    updated_at: datetime = field(default_factory=datetime.utcnow)
    model_version: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "update_type": self.update_type,
            "field_name": self.field_name,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "posterior_mean": self.posterior_mean,
            "posterior_std": self.posterior_std,
            "evidence_strength": self.evidence_strength,
            "n_observations": self.n_observations,
            "updated_at": self.updated_at.isoformat(),
            "model_version": self.model_version,
        }


class BayesianTwinUpdater:
    """
    Updates digital twin entities with Bayesian posterior outputs.
    
    This class is the bridge between the Bayesian analysis engine and
    the digital twin state management system.
    """
    
    def __init__(self, config: Optional[BayesianUpdateConfig] = None):
        self.config = config or BayesianUpdateConfig()
        self.audit_history: List[BayesianUpdateAudit] = []
        
        # Entity caches for batch updates
        self._brand_cache: Dict[str, BrandTwin] = {}
        self._rmn_cache: Dict[str, RetailMediaNetworkTwin] = {}
        self._channel_cache: Dict[str, ChannelTwin] = {}
        
        # Bayesian state cache
        self._bayesian_states: Dict[str, EntityBayesianState] = {}
    
    def update_brand_twin(
        self,
        brand: BrandTwin,
        bayesian_outputs: BrandBayesianOutputs,
    ) -> BrandTwin:
        """
        Update a BrandTwin with Bayesian posterior outputs.
        
        Args:
            brand: The brand twin to update
            bayesian_outputs: Bayesian outputs for this brand
            
        Returns:
            Updated BrandTwin with posterior fields populated
        """
        # Check evidence strength
        if bayesian_outputs.incremental_sales_posterior:
            posterior = bayesian_outputs.incremental_sales_posterior
            if posterior.evidence_strength < self.config.min_evidence_strength:
                logger.warning(
                    f"Low evidence strength ({posterior.evidence_strength:.2f}) for brand {brand.brand_id}, "
                    "skipping incremental_sales update"
                )
            else:
                # Update incremental sales posterior
                self._create_audit(
                    entity_type="brand",
                    entity_id=brand.brand_id,
                    update_type="posterior",
                    field_name="incremental_sales_posterior_mean",
                    old_value=brand.incremental_sales_posterior_mean,
                    new_value=posterior.posterior_mean,
                    posterior=posterior,
                )
                brand.incremental_sales_posterior_mean = posterior.posterior_mean
                brand.incremental_sales_posterior_std = posterior.posterior_std
                brand.incremental_sales_ci_lower = posterior.ci_90_lower
                brand.incremental_sales_ci_upper = posterior.ci_90_upper
        
        # Update efficiency posterior
        if bayesian_outputs.efficiency_posterior:
            posterior = bayesian_outputs.efficiency_posterior
            if posterior.evidence_strength >= self.config.min_evidence_strength:
                self._create_audit(
                    entity_type="brand",
                    entity_id=brand.brand_id,
                    update_type="posterior",
                    field_name="efficiency_posterior_mean",
                    old_value=brand.efficiency_posterior_mean,
                    new_value=posterior.posterior_mean,
                    posterior=posterior,
                )
                brand.efficiency_posterior_mean = posterior.posterior_mean
                brand.efficiency_posterior_std = posterior.posterior_std
        
        # Update index posterior
        if bayesian_outputs.index_posterior:
            posterior = bayesian_outputs.index_posterior
            if posterior.evidence_strength >= self.config.min_evidence_strength:
                brand.index_posterior_mean = posterior.posterior_mean
        
        # Update lift posteriors
        if bayesian_outputs.sales_lift_posterior:
            lift = bayesian_outputs.sales_lift_posterior
            brand.lift_vs_prior_period_mean = lift.lift_posterior_mean
            brand.prob_positive_lift = lift.prob_positive_lift
        
        # Update timestamps
        brand.bayesian_last_updated = datetime.utcnow()
        brand.updated_at = datetime.utcnow()
        
        # Store/update Bayesian state
        state = self._get_or_create_bayesian_state("brand", brand.brand_id, brand.brand_name)
        state.primary_kpi_posteriors["incremental_sales"] = bayesian_outputs.incremental_sales_posterior
        state.primary_kpi_posteriors["efficiency"] = bayesian_outputs.efficiency_posterior
        if bayesian_outputs.sales_lift_posterior:
            state.lift_decompositions["prior_period"] = bayesian_outputs.sales_lift_posterior
        state.driver_attributions = bayesian_outputs.driver_attributions
        state.last_updated = datetime.utcnow()
        brand.bayesian_state_id = state.state_id
        
        logger.info(f"Updated BrandTwin {brand.brand_id} with Bayesian posteriors")
        return brand
    
    def update_rmn_twin(
        self,
        rmn: RetailMediaNetworkTwin,
        bayesian_outputs: RMNBayesianOutputs,
    ) -> RetailMediaNetworkTwin:
        """
        Update a RetailMediaNetworkTwin with Bayesian posterior outputs.
        """
        # Update incremental sales posterior
        if bayesian_outputs.incremental_sales_posterior:
            posterior = bayesian_outputs.incremental_sales_posterior
            if posterior.evidence_strength >= self.config.min_evidence_strength:
                self._create_audit(
                    entity_type="rmn",
                    entity_id=rmn.rmn_id,
                    update_type="posterior",
                    field_name="incremental_sales_posterior_mean",
                    old_value=rmn.incremental_sales_posterior_mean,
                    new_value=posterior.posterior_mean,
                    posterior=posterior,
                )
                rmn.incremental_sales_posterior_mean = posterior.posterior_mean
                rmn.incremental_sales_posterior_std = posterior.posterior_std
                rmn.incremental_sales_ci_lower = posterior.ci_90_lower
                rmn.incremental_sales_ci_upper = posterior.ci_90_upper
        
        # Update efficiency posterior
        if bayesian_outputs.efficiency_posterior:
            posterior = bayesian_outputs.efficiency_posterior
            if posterior.evidence_strength >= self.config.min_evidence_strength:
                rmn.efficiency_posterior_mean = posterior.posterior_mean
                rmn.efficiency_posterior_std = posterior.posterior_std
        
        # Update index posterior
        if bayesian_outputs.index_posterior:
            rmn.index_posterior_mean = bayesian_outputs.index_posterior.posterior_mean
        
        # Update ranking outputs
        rmn.prob_best_overall = bayesian_outputs.prob_best_overall
        
        # Update timestamps
        rmn.bayesian_last_updated = datetime.utcnow()
        rmn.updated_at = datetime.utcnow()
        
        # Store/update Bayesian state
        state = self._get_or_create_bayesian_state("rmn", rmn.rmn_id, rmn.rmn_name)
        state.primary_kpi_posteriors["incremental_sales"] = bayesian_outputs.incremental_sales_posterior
        state.primary_kpi_posteriors["efficiency"] = bayesian_outputs.efficiency_posterior
        state.driver_attributions = bayesian_outputs.driver_attributions
        state.last_updated = datetime.utcnow()
        rmn.bayesian_state_id = state.state_id
        
        logger.info(f"Updated RetailMediaNetworkTwin {rmn.rmn_id} with Bayesian posteriors")
        return rmn
    
    def update_channel_twin(
        self,
        channel: ChannelTwin,
        bayesian_outputs: ChannelBayesianOutputs,
    ) -> ChannelTwin:
        """
        Update a ChannelTwin with Bayesian posterior outputs.
        """
        # Update incremental sales posterior
        if bayesian_outputs.incremental_sales_posterior:
            posterior = bayesian_outputs.incremental_sales_posterior
            if posterior.evidence_strength >= self.config.min_evidence_strength:
                self._create_audit(
                    entity_type="channel",
                    entity_id=channel.channel_id,
                    update_type="posterior",
                    field_name="incremental_sales_posterior_mean",
                    old_value=channel.incremental_sales_posterior_mean,
                    new_value=posterior.posterior_mean,
                    posterior=posterior,
                )
                channel.incremental_sales_posterior_mean = posterior.posterior_mean
                channel.incremental_sales_posterior_std = posterior.posterior_std
                channel.incremental_sales_ci_lower = posterior.ci_90_lower
                channel.incremental_sales_ci_upper = posterior.ci_90_upper
        
        # Update efficiency posterior
        if bayesian_outputs.efficiency_posterior:
            posterior = bayesian_outputs.efficiency_posterior
            if posterior.evidence_strength >= self.config.min_evidence_strength:
                channel.efficiency_posterior_mean = posterior.posterior_mean
                channel.efficiency_posterior_std = posterior.posterior_std
        
        # Update index posterior
        if bayesian_outputs.index_posterior:
            channel.index_posterior_mean = bayesian_outputs.index_posterior.posterior_mean
        
        # Update elasticity posterior
        if bayesian_outputs.elasticity_posterior:
            posterior = bayesian_outputs.elasticity_posterior
            self._create_audit(
                entity_type="channel",
                entity_id=channel.channel_id,
                update_type="posterior",
                field_name="elasticity_posterior_mean",
                old_value=channel.elasticity_posterior_mean,
                new_value=posterior.posterior_mean,
                posterior=posterior,
            )
            channel.elasticity_posterior_mean = posterior.posterior_mean
            channel.elasticity_posterior_std = posterior.posterior_std
            channel.elasticity_ci_lower = posterior.ci_90_lower
            channel.elasticity_ci_upper = posterior.ci_90_upper
        
        # Update contribution posteriors
        if bayesian_outputs.contribution_posterior:
            channel.contribution_posterior_mean = bayesian_outputs.contribution_posterior.posterior_mean
        if bayesian_outputs.contribution_pct_posterior:
            channel.contribution_pct_posterior_mean = bayesian_outputs.contribution_pct_posterior.posterior_mean
        
        # Update ranking outputs
        if bayesian_outputs.ranking_within_rmn:
            channel.prob_rank_1_within_rmn = bayesian_outputs.ranking_within_rmn.prob_rank_1
            channel.expected_rank_within_rmn = bayesian_outputs.ranking_within_rmn.expected_rank
        
        # Update probability outputs
        channel.prob_efficiency_above_target = bayesian_outputs.prob_efficiency_above_target
        channel.efficiency_target = bayesian_outputs.efficiency_target
        
        # Update timestamps
        channel.bayesian_last_updated = datetime.utcnow()
        channel.updated_at = datetime.utcnow()
        
        # Store/update Bayesian state
        state = self._get_or_create_bayesian_state("channel", channel.channel_id, channel.channel_name)
        state.primary_kpi_posteriors["incremental_sales"] = bayesian_outputs.incremental_sales_posterior
        state.primary_kpi_posteriors["efficiency"] = bayesian_outputs.efficiency_posterior
        state.primary_kpi_posteriors["elasticity"] = bayesian_outputs.elasticity_posterior
        if bayesian_outputs.ranking_within_rmn:
            state.rankings.append(bayesian_outputs.ranking_within_rmn)
        state.driver_attributions = bayesian_outputs.driver_attributions
        state.last_updated = datetime.utcnow()
        channel.bayesian_state_id = state.state_id
        
        logger.info(f"Updated ChannelTwin {channel.channel_id} with Bayesian posteriors")
        return channel
    
    def update_from_elasticity_posterior(
        self,
        channel: ChannelTwin,
        elasticity_mean: float,
        elasticity_std: float,
        ci_lower: float,
        ci_upper: float,
        n_observations: int,
        evidence_strength: float,
        model_version: str = "v1.0.0",
    ) -> ChannelTwin:
        """
        Direct update of channel elasticity from Bayesian engine output.
        
        This is called by the Bayesian engine after computing elasticity posteriors.
        """
        # Create posterior distribution
        posterior = PosteriorDistribution(
            entity_type="channel",
            entity_id=channel.channel_id,
            kpi_name="elasticity",
            posterior_mean=elasticity_mean,
            posterior_std=elasticity_std,
            ci_90_lower=ci_lower,
            ci_90_upper=ci_upper,
            n_observations=n_observations,
            evidence_strength=evidence_strength,
            model_version=model_version,
        )
        
        # Create channel outputs wrapper
        outputs = ChannelBayesianOutputs(
            channel_id=channel.channel_id,
            channel_name=channel.channel_name,
            rmn_id=channel.rmn_id,
            elasticity_posterior=posterior,
        )
        
        return self.update_channel_twin(channel, outputs)
    
    def update_from_attribution_result(
        self,
        channel: ChannelTwin,
        contribution_mean: float,
        contribution_pct_mean: float,
        incremental_sales_mean: float,
        incremental_sales_std: float,
        efficiency_mean: float,
        n_observations: int,
        model_version: str = "v1.0.0",
    ) -> ChannelTwin:
        """
        Update channel from attribution analysis results.
        """
        # Create posteriors
        incr_posterior = PosteriorDistribution(
            entity_type="channel",
            entity_id=channel.channel_id,
            kpi_name="incremental_sales",
            posterior_mean=incremental_sales_mean,
            posterior_std=incremental_sales_std,
            ci_90_lower=incremental_sales_mean - 1.645 * incremental_sales_std,
            ci_90_upper=incremental_sales_mean + 1.645 * incremental_sales_std,
            n_observations=n_observations,
            evidence_strength=min(1.0, n_observations / 100),
            model_version=model_version,
        )
        
        contribution_posterior = PosteriorDistribution(
            entity_type="channel",
            entity_id=channel.channel_id,
            kpi_name="contribution",
            posterior_mean=contribution_mean,
            posterior_std=0.0,  # From attribution, not uncertain
            n_observations=n_observations,
            evidence_strength=min(1.0, n_observations / 100),
            model_version=model_version,
        )
        
        contribution_pct_posterior = PosteriorDistribution(
            entity_type="channel",
            entity_id=channel.channel_id,
            kpi_name="contribution_pct",
            posterior_mean=contribution_pct_mean,
            posterior_std=0.0,
            n_observations=n_observations,
            evidence_strength=min(1.0, n_observations / 100),
            model_version=model_version,
        )
        
        efficiency_posterior = PosteriorDistribution(
            entity_type="channel",
            entity_id=channel.channel_id,
            kpi_name="efficiency",
            posterior_mean=efficiency_mean,
            posterior_std=0.0,
            n_observations=n_observations,
            evidence_strength=min(1.0, n_observations / 100),
            model_version=model_version,
        )
        
        outputs = ChannelBayesianOutputs(
            channel_id=channel.channel_id,
            channel_name=channel.channel_name,
            rmn_id=channel.rmn_id,
            incremental_sales_posterior=incr_posterior,
            efficiency_posterior=efficiency_posterior,
            contribution_posterior=contribution_posterior,
            contribution_pct_posterior=contribution_pct_posterior,
        )
        
        return self.update_channel_twin(channel, outputs)
    
    def update_scenario_comparison(
        self,
        entity_type: str,
        entity_id: str,
        current_scenario: ScenarioPosterior,
        optimized_scenario: ScenarioPosterior,
        prob_optimized_beats_current: float,
        recommended_allocation: Dict[str, float],
    ) -> ScenarioComparison:
        """
        Create and store a scenario comparison for an entity.
        """
        # Compute expected delta
        current_incr = current_scenario.incremental_sales_posterior.posterior_mean if current_scenario.incremental_sales_posterior else 0.0
        optimized_incr = optimized_scenario.incremental_sales_posterior.posterior_mean if optimized_scenario.incremental_sales_posterior else 0.0
        
        current_std = current_scenario.incremental_sales_posterior.posterior_std if current_scenario.incremental_sales_posterior else 0.0
        optimized_std = optimized_scenario.incremental_sales_posterior.posterior_std if optimized_scenario.incremental_sales_posterior else 0.0
        
        delta_mean = optimized_incr - current_incr
        delta_std = np.sqrt(current_std**2 + optimized_std**2)
        
        comparison = ScenarioComparison(
            entity_type=entity_type,
            entity_id=entity_id,
            current_scenario=current_scenario,
            optimized_scenario=optimized_scenario,
            expected_incremental_sales_delta=delta_mean,
            expected_delta_ci_lower=delta_mean - 1.645 * delta_std,
            expected_delta_ci_upper=delta_mean + 1.645 * delta_std,
            prob_optimized_beats_current=prob_optimized_beats_current,
            recommended_allocation=recommended_allocation,
        )
        
        # Update Bayesian state
        state = self._get_or_create_bayesian_state(entity_type, entity_id, "")
        state.scenario_posteriors["current"] = current_scenario
        state.scenario_posteriors["optimized"] = optimized_scenario
        state.scenario_comparison = comparison
        state.last_updated = datetime.utcnow()
        
        logger.info(
            f"Created scenario comparison for {entity_type} {entity_id}: "
            f"P(optimized > current) = {prob_optimized_beats_current:.1%}"
        )
        
        return comparison
    
    def propagate_bayesian_updates(
        self,
        brands: List[BrandTwin],
        rmns: List[RetailMediaNetworkTwin],
        channels: List[ChannelTwin],
    ) -> Dict[str, Any]:
        """
        Propagate Bayesian updates through the entity hierarchy.
        
        Aggregates channel → RMN → brand → company posteriors.
        """
        results = {
            "brands_updated": 0,
            "rmns_updated": 0,
            "channels_updated": 0,
            "aggregations_computed": 0,
        }
        
        # Group channels by RMN
        channels_by_rmn: Dict[str, List[ChannelTwin]] = {}
        for channel in channels:
            if channel.rmn_id not in channels_by_rmn:
                channels_by_rmn[channel.rmn_id] = []
            channels_by_rmn[channel.rmn_id].append(channel)
        
        # Aggregate channel posteriors to RMN level
        for rmn in rmns:
            rmn_channels = channels_by_rmn.get(rmn.rmn_id, [])
            if rmn_channels:
                # Aggregate incremental sales
                incr_means = [c.incremental_sales_posterior_mean for c in rmn_channels 
                              if c.incremental_sales_posterior_mean is not None]
                if incr_means:
                    rmn.incremental_sales_posterior_mean = sum(incr_means)
                    results["aggregations_computed"] += 1
                
                # Compute RMN efficiency as weighted average
                efficiencies = [(c.efficiency_posterior_mean, c.incremental_sales_posterior_mean or 0.0) 
                               for c in rmn_channels 
                               if c.efficiency_posterior_mean is not None]
                if efficiencies:
                    total_weight = sum(w for _, w in efficiencies)
                    if total_weight > 0:
                        rmn.efficiency_posterior_mean = sum(e * w for e, w in efficiencies) / total_weight
                
                rmn.bayesian_last_updated = datetime.utcnow()
                results["rmns_updated"] += 1
        
        # Group RMNs by brand (through programs - simplified here)
        # In full implementation, would traverse BrandRMNProgramTwin
        
        logger.info(f"Propagated Bayesian updates: {results}")
        return results
    
    def get_bayesian_state(self, entity_type: str, entity_id: str) -> Optional[EntityBayesianState]:
        """Get the full Bayesian state for an entity."""
        key = f"{entity_type}:{entity_id}"
        return self._bayesian_states.get(key)
    
    def get_audit_history(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[BayesianUpdateAudit]:
        """Get audit history, optionally filtered by entity."""
        history = self.audit_history
        
        if entity_type:
            history = [a for a in history if a.entity_type == entity_type]
        if entity_id:
            history = [a for a in history if a.entity_id == entity_id]
        
        return history[-limit:]
    
    def _get_or_create_bayesian_state(
        self,
        entity_type: str,
        entity_id: str,
        entity_name: str,
    ) -> EntityBayesianState:
        """Get existing or create new Bayesian state for entity."""
        key = f"{entity_type}:{entity_id}"
        if key not in self._bayesian_states:
            self._bayesian_states[key] = EntityBayesianState(
                entity_type=entity_type,
                entity_id=entity_id,
                entity_name=entity_name,
            )
        return self._bayesian_states[key]
    
    def _create_audit(
        self,
        entity_type: str,
        entity_id: str,
        update_type: str,
        field_name: str,
        old_value: Optional[float],
        new_value: Optional[float],
        posterior: Optional[PosteriorDistribution] = None,
    ) -> None:
        """Create an audit record for a Bayesian update."""
        if not self.config.enable_audit_trail:
            return
        
        audit = BayesianUpdateAudit(
            entity_type=entity_type,
            entity_id=entity_id,
            update_type=update_type,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            posterior_mean=posterior.posterior_mean if posterior else None,
            posterior_std=posterior.posterior_std if posterior else None,
            evidence_strength=posterior.evidence_strength if posterior else None,
            n_observations=posterior.n_observations if posterior else None,
            model_version=posterior.model_version if posterior else "",
        )
        
        self.audit_history.append(audit)
        
        # Trim history if needed
        if len(self.audit_history) > self.config.max_audit_history:
            self.audit_history = self.audit_history[-self.config.max_audit_history:]


# =============================================================================
# Integration with Bayesian Engine
# =============================================================================

class BayesianEngineIntegration:
    """
    Integration layer between the Bayesian analysis engine and digital twins.
    
    This class orchestrates the flow of Bayesian outputs to twin updates.
    """
    
    def __init__(self, updater: Optional[BayesianTwinUpdater] = None):
        self.updater = updater or BayesianTwinUpdater()
        self._pending_updates: List[Dict[str, Any]] = []
    
    def on_elasticity_computed(
        self,
        channel_id: str,
        retailer_id: str,
        elasticity_mean: float,
        elasticity_std: float,
        ci_lower: float,
        ci_upper: float,
        n_observations: int,
        evidence_strength: float,
        model_version: str,
        channel_twin: Optional[ChannelTwin] = None,
    ) -> Optional[ChannelTwin]:
        """
        Callback when elasticity posterior is computed.
        
        Called by BayesianEngine.update_posterior()
        """
        if channel_twin is None:
            logger.warning(f"No channel twin provided for {channel_id}, update skipped")
            return None
        
        return self.updater.update_from_elasticity_posterior(
            channel=channel_twin,
            elasticity_mean=elasticity_mean,
            elasticity_std=elasticity_std,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
            n_observations=n_observations,
            evidence_strength=evidence_strength,
            model_version=model_version,
        )
    
    def on_attribution_computed(
        self,
        channel_shares: Dict[str, float],
        total_incremental_sales: float,
        total_spend: float,
        channel_twins: Dict[str, ChannelTwin],
        n_paths: int,
        model_version: str,
    ) -> Dict[str, ChannelTwin]:
        """
        Callback when attribution is computed.
        
        Called by BayesianAttributionModel.compute_attribution()
        """
        updated_channels = {}
        
        for channel_id, share in channel_shares.items():
            if channel_id not in channel_twins:
                continue
            
            channel = channel_twins[channel_id]
            channel_spend = total_spend * share  # Approximate
            channel_incr = total_incremental_sales * share
            efficiency = channel_incr / channel_spend if channel_spend > 0 else 0.0
            
            updated = self.updater.update_from_attribution_result(
                channel=channel,
                contribution_mean=channel_incr,
                contribution_pct_mean=share,
                incremental_sales_mean=channel_incr,
                incremental_sales_std=channel_incr * 0.1,  # 10% uncertainty estimate
                efficiency_mean=efficiency,
                n_observations=n_paths,
                model_version=model_version,
            )
            updated_channels[channel_id] = updated
        
        return updated_channels
    
    def on_simulation_completed(
        self,
        scenario_name: str,
        entity_type: str,
        entity_id: str,
        incremental_sales_samples: List[float],
        roas_samples: List[float],
        model_version: str,
    ) -> ScenarioPosterior:
        """
        Callback when simulation completes.
        
        Creates scenario posterior from Monte Carlo samples.
        """
        incr_mean = np.mean(incremental_sales_samples)
        incr_std = np.std(incremental_sales_samples)
        roas_mean = np.mean(roas_samples)
        roas_std = np.std(roas_samples)
        
        incr_posterior = PosteriorDistribution(
            entity_type=entity_type,
            entity_id=entity_id,
            kpi_name="incremental_sales",
            posterior_mean=incr_mean,
            posterior_std=incr_std,
            ci_90_lower=np.percentile(incremental_sales_samples, 5),
            ci_90_upper=np.percentile(incremental_sales_samples, 95),
            n_observations=len(incremental_sales_samples),
            evidence_strength=0.9,  # Simulation-based
            model_version=model_version,
        )
        
        roas_posterior = PosteriorDistribution(
            entity_type=entity_type,
            entity_id=entity_id,
            kpi_name="roas",
            posterior_mean=roas_mean,
            posterior_std=roas_std,
            ci_90_lower=np.percentile(roas_samples, 5),
            ci_90_upper=np.percentile(roas_samples, 95),
            n_observations=len(roas_samples),
            evidence_strength=0.9,
            model_version=model_version,
        )
        
        scenario = ScenarioPosterior(
            scenario_name=scenario_name,
            entity_type=entity_type,
            entity_id=entity_id,
            incremental_sales_posterior=incr_posterior,
            roas_posterior=roas_posterior,
            downside_risk_5pct=np.percentile(incremental_sales_samples, 5),
            downside_risk_10pct=np.percentile(incremental_sales_samples, 10),
            upside_potential_90pct=np.percentile(incremental_sales_samples, 90),
            upside_potential_95pct=np.percentile(incremental_sales_samples, 95),
            prob_revenue_increase=np.mean(np.array(incremental_sales_samples) > 0),
            model_version=model_version,
        )
        
        # Store in Bayesian state
        state = self.updater._get_or_create_bayesian_state(entity_type, entity_id, "")
        state.scenario_posteriors[scenario_name] = scenario
        state.last_updated = datetime.utcnow()
        
        return scenario
