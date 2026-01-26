"""
Twin-Bayesian Integration Service

Connects Digital Twin simulation results to the Bayesian Decision Engine
for scenario-informed posterior computation.

This module bridges the gap between:
- Digital Twin: Monte Carlo simulations of inventory dynamics
- Bayesian Engine: Uncertainty quantification and decision support

The integration enables:
1. Twin scenarios to inform Bayesian priors
2. Scenario KPI distributions to become posterior inputs
3. Closed-loop feedback for policy evaluation
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, date
import logging
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.schemas.data_contracts import (
    DemandForecastSummary, PosteriorOutcome, ScenarioResult,
    OptimizationResult, HierarchyLevel
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class IntegrationConfig:
    """Configuration for Twin-Bayesian integration"""
    # Prior update settings
    prior_weight: float = 0.3  # Weight for historical prior vs. twin evidence
    min_samples_for_update: int = 100
    
    # Scenario mapping
    baseline_scenario_name: str = "baseline"
    
    # Credible interval
    ci_level: float = 0.90
    
    # Caching
    cache_integrated_posteriors: bool = True


class TwinBayesianConnector:
    """
    Integrates Digital Twin simulation results with Bayesian inference.
    
    The connector:
    1. Transforms Twin KPI distributions into Bayesian likelihood inputs
    2. Updates priors based on scenario evidence
    3. Produces scenario-informed posteriors for decision support
    """
    
    def __init__(self, config: Optional[IntegrationConfig] = None):
        self.config = config or IntegrationConfig()
        self.integrated_posteriors: Dict[str, Dict[str, PosteriorOutcome]] = {}
        
        logger.info("TwinBayesianConnector initialized")
    
    def integrate_twin_scenarios(
        self,
        entity_id: str,
        twin_results: Dict[str, ScenarioResult],
        prior_beliefs: Optional[Dict[str, Any]] = None,
        model_version: str = "integrated-v1.0.0"
    ) -> Dict[str, PosteriorOutcome]:
        """
        Integrate Twin scenario results into Bayesian posteriors.
        
        Args:
            entity_id: Entity identifier
            twin_results: Scenario name -> ScenarioResult from Digital Twin
            prior_beliefs: Optional prior beliefs to incorporate
            model_version: Version string for tracking
            
        Returns:
            Dict of scenario name -> PosteriorOutcome with integrated posteriors
        """
        posteriors = {}
        
        for scenario_name, scenario_result in twin_results.items():
            # Extract KPI distributions from Twin
            kpi_dists = scenario_result.kpi_distributions
            
            # Compute posteriors from Twin Monte Carlo samples
            posterior = self._compute_posterior_from_twin(
                entity_id=entity_id,
                scenario_name=scenario_name,
                kpi_distributions=kpi_dists,
                prior_beliefs=prior_beliefs,
                model_version=model_version
            )
            
            posteriors[scenario_name] = posterior
        
        # Cache for later retrieval
        if self.config.cache_integrated_posteriors:
            self.integrated_posteriors[entity_id] = posteriors
        
        return posteriors
    
    def _compute_posterior_from_twin(
        self,
        entity_id: str,
        scenario_name: str,
        kpi_distributions: Dict[str, List[float]],
        prior_beliefs: Optional[Dict[str, Any]],
        model_version: str
    ) -> PosteriorOutcome:
        """
        Compute Bayesian posterior from Twin KPI distributions.
        
        Uses Monte Carlo samples from Twin as likelihood evidence.
        """
        ci_lower = (1 - self.config.ci_level) / 2 * 100
        ci_upper = (1 + self.config.ci_level) / 2 * 100
        
        # Extract stockout distribution
        stockout_samples = np.array(
            kpi_distributions.get('stockout_rate', 
            kpi_distributions.get('stockout_probability', [0.05]))
        )
        
        # Extract service level distribution
        service_samples = np.array(
            kpi_distributions.get('service_level', [0.95])
        )
        
        # Extract margin/cost impact if available
        margin_samples = np.array(
            kpi_distributions.get('margin_impact',
            kpi_distributions.get('total_cost', [0.0]))
        )
        
        # Extract weeks of supply
        wos_samples = np.array(
            kpi_distributions.get('weeks_of_supply', [4.0])
        )
        
        # Apply Bayesian update if prior beliefs provided
        if prior_beliefs:
            stockout_samples = self._bayesian_update(
                stockout_samples, 
                prior_beliefs.get('stockout_prior', 0.05),
                prior_beliefs.get('stockout_prior_strength', 10)
            )
            
            margin_samples = self._bayesian_update(
                margin_samples,
                prior_beliefs.get('margin_prior', 0.0),
                prior_beliefs.get('margin_prior_strength', 10)
            )
        
        # Compute summary statistics
        posterior = PosteriorOutcome(
            entity_id=entity_id,
            scenario_name=scenario_name,
            stockout_probability=float(np.mean(stockout_samples)),
            stockout_ci_lower=float(np.percentile(stockout_samples, ci_lower)),
            stockout_ci_upper=float(np.percentile(stockout_samples, ci_upper)),
            expected_margin_impact=float(np.mean(margin_samples)),
            margin_ci_lower=float(np.percentile(margin_samples, ci_lower)),
            margin_ci_upper=float(np.percentile(margin_samples, ci_upper)),
            service_level_estimate=float(np.mean(service_samples)),
            weeks_of_supply=float(np.mean(wos_samples)),
            computed_at=datetime.utcnow(),
            model_version=model_version
        )
        
        return posterior
    
    def _bayesian_update(
        self,
        likelihood_samples: np.ndarray,
        prior_mean: float,
        prior_strength: float
    ) -> np.ndarray:
        """
        Apply Bayesian update combining prior with likelihood samples.
        
        Uses conjugate normal-normal update approximation.
        """
        n_samples = len(likelihood_samples)
        likelihood_mean = np.mean(likelihood_samples)
        likelihood_var = np.var(likelihood_samples) + 1e-8
        
        # Posterior precision = prior precision + likelihood precision
        prior_precision = prior_strength
        likelihood_precision = n_samples / likelihood_var
        posterior_precision = prior_precision + likelihood_precision
        
        # Posterior mean is precision-weighted average
        posterior_mean = (
            prior_precision * prior_mean + likelihood_precision * likelihood_mean
        ) / posterior_precision
        
        # Posterior variance
        posterior_var = 1 / posterior_precision
        
        # Generate posterior samples
        posterior_samples = np.random.normal(
            posterior_mean, 
            np.sqrt(posterior_var), 
            n_samples
        )
        
        return posterior_samples
    
    def compare_scenario_posteriors(
        self,
        entity_id: str,
        baseline_name: str = "baseline"
    ) -> Dict[str, Dict[str, float]]:
        """
        Compare posteriors across scenarios for decision support.
        
        Returns delta from baseline for each scenario and KPI.
        """
        if entity_id not in self.integrated_posteriors:
            raise ValueError(f"No integrated posteriors for entity {entity_id}")
        
        posteriors = self.integrated_posteriors[entity_id]
        
        if baseline_name not in posteriors:
            raise ValueError(f"Baseline scenario '{baseline_name}' not found")
        
        baseline = posteriors[baseline_name]
        comparisons = {}
        
        for scenario_name, posterior in posteriors.items():
            if scenario_name == baseline_name:
                continue
            
            comparisons[scenario_name] = {
                'stockout_delta': posterior.stockout_probability - baseline.stockout_probability,
                'stockout_delta_pct': (
                    (posterior.stockout_probability - baseline.stockout_probability) 
                    / max(baseline.stockout_probability, 0.01) * 100
                ),
                'margin_delta': posterior.expected_margin_impact - baseline.expected_margin_impact,
                'service_level_delta': posterior.service_level_estimate - baseline.service_level_estimate,
                'wos_delta': posterior.weeks_of_supply - baseline.weeks_of_supply,
                'risk_assessment': self._assess_scenario_risk(baseline, posterior)
            }
        
        return comparisons
    
    def _assess_scenario_risk(
        self,
        baseline: PosteriorOutcome,
        alternative: PosteriorOutcome
    ) -> str:
        """Assess risk level of scenario vs baseline"""
        stockout_increase = alternative.stockout_probability - baseline.stockout_probability
        service_decrease = baseline.service_level_estimate - alternative.service_level_estimate
        
        if stockout_increase > 0.10 or service_decrease > 0.05:
            return "HIGH_RISK"
        elif stockout_increase > 0.05 or service_decrease > 0.02:
            return "MODERATE_RISK"
        elif stockout_increase < -0.02:
            return "OPPORTUNITY"
        else:
            return "LOW_RISK"
    
    def get_decision_recommendation(
        self,
        entity_id: str,
        risk_tolerance: str = "moderate"
    ) -> Dict[str, Any]:
        """
        Generate decision recommendation based on integrated posteriors.
        
        Args:
            entity_id: Entity to generate recommendation for
            risk_tolerance: "conservative", "moderate", or "aggressive"
            
        Returns:
            Recommendation with rationale
        """
        if entity_id not in self.integrated_posteriors:
            return {"error": f"No posteriors for {entity_id}"}
        
        posteriors = self.integrated_posteriors[entity_id]
        baseline = posteriors.get(self.config.baseline_scenario_name)
        
        if not baseline:
            return {"error": "No baseline scenario"}
        
        # Risk thresholds based on tolerance
        thresholds = {
            "conservative": {"stockout_max": 0.05, "service_min": 0.98},
            "moderate": {"stockout_max": 0.10, "service_min": 0.95},
            "aggressive": {"stockout_max": 0.15, "service_min": 0.90}
        }
        
        threshold = thresholds.get(risk_tolerance, thresholds["moderate"])
        
        # Evaluate baseline
        baseline_acceptable = (
            baseline.stockout_probability <= threshold["stockout_max"] and
            baseline.service_level_estimate >= threshold["service_min"]
        )
        
        recommendation = {
            "entity_id": entity_id,
            "risk_tolerance": risk_tolerance,
            "baseline_acceptable": baseline_acceptable,
            "baseline_stockout": baseline.stockout_probability,
            "baseline_service_level": baseline.service_level_estimate,
            "action": "MAINTAIN" if baseline_acceptable else "ADJUST",
            "rationale": []
        }
        
        if not baseline_acceptable:
            if baseline.stockout_probability > threshold["stockout_max"]:
                recommendation["rationale"].append(
                    f"Stockout risk ({baseline.stockout_probability:.1%}) exceeds "
                    f"threshold ({threshold['stockout_max']:.1%})"
                )
            if baseline.service_level_estimate < threshold["service_min"]:
                recommendation["rationale"].append(
                    f"Service level ({baseline.service_level_estimate:.1%}) below "
                    f"target ({threshold['service_min']:.1%})"
                )
            recommendation["suggested_actions"] = [
                "Increase safety stock",
                "Reduce lead time variability",
                "Review demand forecast accuracy"
            ]
        else:
            recommendation["rationale"].append(
                "Current policy meets risk tolerance thresholds"
            )
        
        # Add scenario insights
        comparisons = self.compare_scenario_posteriors(entity_id)
        high_risk_scenarios = [
            name for name, comp in comparisons.items()
            if comp["risk_assessment"] == "HIGH_RISK"
        ]
        
        if high_risk_scenarios:
            recommendation["vulnerability_warnings"] = high_risk_scenarios
            recommendation["rationale"].append(
                f"High risk exposure in scenarios: {', '.join(high_risk_scenarios)}"
            )
        
        return recommendation


class ScenarioInformedBayesianEngine:
    """
    Extended Bayesian engine that incorporates Digital Twin scenarios.
    
    This class wraps the standard BayesianDecisionEngine and adds
    Twin-informed posterior computation.
    """
    
    def __init__(
        self,
        bayesian_engine,  # BayesianDecisionEngine instance
        connector: Optional[TwinBayesianConnector] = None
    ):
        self.bayesian_engine = bayesian_engine
        self.connector = connector or TwinBayesianConnector()
        
        logger.info("ScenarioInformedBayesianEngine initialized")
    
    def analyze_with_twin_scenarios(
        self,
        entity_id: str,
        forecast_summaries: List[DemandForecastSummary],
        inventory_state: Dict[str, float],
        supply_params: Dict[str, Any],
        twin_scenario_results: Dict[str, Any],
        model_version: str = "integrated-v1.0.0"
    ) -> Dict[str, PosteriorOutcome]:
        """
        Run Bayesian analysis informed by Twin scenario simulations.
        
        Combines:
        1. Standard Bayesian inference from forecasts
        2. Twin scenario evidence for prior updates
        
        Returns:
            Scenario-informed posteriors
        """
        # First, run standard Bayesian analysis as prior
        standard_result = self.bayesian_engine.analyze_entity(
            entity_id=entity_id,
            forecast_summaries=forecast_summaries,
            inventory_state=inventory_state,
            supply_params=supply_params,
            model_version=model_version
        )
        
        # Extract prior beliefs from standard analysis
        standard_baseline = standard_result.get('outcomes', {}).get('baseline', {})
        prior_beliefs = {
            'stockout_prior': standard_baseline.get('stockout_probability', 0.05),
            'stockout_prior_strength': 10,
            'margin_prior': standard_baseline.get('expected_margin_impact', 0.0),
            'margin_prior_strength': 5
        }
        
        # Convert twin results to ScenarioResult objects if needed
        scenario_results = {}
        for scenario_name, scenario_data in twin_scenario_results.items():
            if isinstance(scenario_data, dict):
                # Create mock ScenarioResult
                scenario_results[scenario_name] = type('ScenarioResult', (), {
                    'scenario_name': scenario_name,
                    'kpi_distributions': scenario_data.get('kpi_distributions', {}),
                    'recommended_actions': scenario_data.get('recommended_actions', [])
                })()
            else:
                scenario_results[scenario_name] = scenario_data
        
        # Integrate Twin scenarios with Bayesian priors
        integrated_posteriors = self.connector.integrate_twin_scenarios(
            entity_id=entity_id,
            twin_results=scenario_results,
            prior_beliefs=prior_beliefs,
            model_version=model_version
        )
        
        return integrated_posteriors
    
    def get_scenario_comparison(self, entity_id: str) -> Dict[str, Dict[str, float]]:
        """Get comparison of scenarios for decision support"""
        return self.connector.compare_scenario_posteriors(entity_id)
    
    def get_recommendation(
        self,
        entity_id: str,
        risk_tolerance: str = "moderate"
    ) -> Dict[str, Any]:
        """Get decision recommendation based on integrated analysis"""
        return self.connector.get_decision_recommendation(entity_id, risk_tolerance)


def create_twin_bayesian_connector(
    config: Optional[IntegrationConfig] = None
) -> TwinBayesianConnector:
    """Factory function for creating TwinBayesianConnector"""
    return TwinBayesianConnector(config)


def create_scenario_informed_engine(
    bayesian_engine,
    connector_config: Optional[IntegrationConfig] = None
) -> ScenarioInformedBayesianEngine:
    """Factory function for creating ScenarioInformedBayesianEngine"""
    connector = TwinBayesianConnector(connector_config)
    return ScenarioInformedBayesianEngine(bayesian_engine, connector)
