"""
RMN (Retail Media Network) Optimization - Agents

CrewAI-compliant agents for retail media spend optimization.
"""

import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, date
import logging

from ...crewai_base import (
    DemandTwinAgent,
    CrewAIAgentConfig,
    AgentCategory,
    AgentRole,
    AgentMessageBus,
    MessageType,
    AgentMessage,
)

from .schemas import (
    RMNConfig,
    ChannelConfig,
    MediaSpendData,
    AttributionResult,
    ElasticityPosterior,
    AllocationScenario,
    SimulationResult,
    OptimizationResult,
    GovernanceDecision,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RMNDataIngestionAgent(DemandTwinAgent):
    """
    Validates and preprocesses media spend and performance data.
    """
    
    def __init__(
        self,
        retailer_id: str,
        channels: List[ChannelConfig],
        message_bus: Optional[AgentMessageBus] = None,
    ):
        config = CrewAIAgentConfig(
            agent_id=f"rmn-{retailer_id}-data",
            role=AgentRole.DATA_STEWARD,
            category=AgentCategory.DATA,
            name="RMN Data Steward",
            goal="Validate and preprocess media spend data for optimization",
            backstory="""You are responsible for ensuring data quality in the 
            retail media optimization pipeline. You validate spend data, 
            detect anomalies, and ensure all channels have complete data.""",
            retailer_id=retailer_id,
        )
        super().__init__(config, message_bus)
        
        self.channels = {c.channel_id: c for c in channels}
        self.quality_scores: Dict[str, float] = {}
    
    def validate_data(
        self,
        spend_data: List[MediaSpendData]
    ) -> Dict[str, Any]:
        """Validate media spend data"""
        issues = []
        channel_data: Dict[str, List[MediaSpendData]] = {}
        
        # Group by channel
        for record in spend_data:
            if record.channel_id not in channel_data:
                channel_data[record.channel_id] = []
            channel_data[record.channel_id].append(record)
            record.compute_metrics()
        
        # Validate each channel
        for channel_id, records in channel_data.items():
            if channel_id not in self.channels:
                issues.append(f"Unknown channel: {channel_id}")
                continue
            
            spends = [r.spend for r in records]
            
            # Check for missing data
            if len(records) < 7:
                issues.append(f"{channel_id}: Insufficient data ({len(records)} records)")
            
            # Check for negative spends
            if any(s < 0 for s in spends):
                issues.append(f"{channel_id}: Negative spend values detected")
            
            # Check for outliers
            if len(spends) > 10:
                q1, q3 = np.percentile(spends, [25, 75])
                iqr = q3 - q1
                outliers = sum(1 for s in spends if s < q1 - 1.5*iqr or s > q3 + 1.5*iqr)
                if outliers > len(spends) * 0.1:
                    issues.append(f"{channel_id}: High outlier rate ({outliers/len(spends):.1%})")
            
            # Compute quality score
            quality = 1.0 - len([i for i in issues if channel_id in i]) * 0.1
            self.quality_scores[channel_id] = max(0.5, quality)
        
        overall_quality = np.mean(list(self.quality_scores.values())) if self.quality_scores else 0.5
        
        result = {
            "valid": len(issues) == 0,
            "overall_quality": overall_quality,
            "channel_quality": self.quality_scores,
            "issues": issues,
            "n_records": len(spend_data),
            "n_channels": len(channel_data),
            "validated_at": datetime.utcnow().isoformat(),
        }
        
        self.log_action("validate_data", {"n_records": len(spend_data)}, result)
        return result


class RMNAttributionAgent(DemandTwinAgent):
    """
    Performs Bayesian multi-touch attribution across channels.
    """
    
    def __init__(
        self,
        retailer_id: str,
        channels: List[ChannelConfig],
        message_bus: Optional[AgentMessageBus] = None,
    ):
        config = CrewAIAgentConfig(
            agent_id=f"rmn-{retailer_id}-attribution",
            role=AgentRole.ATTRIBUTION,
            category=AgentCategory.ANALYTICS,
            name="RMN Attribution Analyst",
            goal="Fairly attribute conversions and revenue to media channels",
            backstory="""You are an expert in multi-touch attribution using 
            Bayesian methods. You use Shapley values and Dirichlet posteriors 
            to fairly distribute credit across touchpoints.""",
            retailer_id=retailer_id,
        )
        super().__init__(config, message_bus)
        
        self.channels = [c.channel_id for c in channels]
        self.dirichlet_alpha = {c: 1.0 for c in self.channels}
    
    def compute_attribution(
        self,
        conversion_paths: List[List[str]],
        total_revenue: float,
        total_conversions: int = 0
    ) -> AttributionResult:
        """Compute attribution shares using position-based + Bayesian"""
        counts = {c: 0.0 for c in self.channels}
        
        for path in conversion_paths:
            if not path:
                continue
            
            n_touches = len(path)
            for i, touch in enumerate(path):
                if touch in counts:
                    # Position-based weighting
                    if i == 0:
                        weight = 0.4
                    elif i == n_touches - 1:
                        weight = 0.4
                    else:
                        weight = 0.2 / max(n_touches - 2, 1)
                    counts[touch] += weight
        
        # Update Dirichlet posterior
        for channel, count in counts.items():
            self.dirichlet_alpha[channel] += count
        
        # Posterior mean
        total_alpha = sum(self.dirichlet_alpha.values())
        shares = {c: alpha / total_alpha for c, alpha in self.dirichlet_alpha.items()}
        
        # Attributed values
        attributed_revenue = {c: share * total_revenue for c, share in shares.items()}
        attributed_conversions = {c: share * total_conversions for c, share in shares.items()}
        
        result = AttributionResult(
            channel_shares=shares,
            attributed_revenue=attributed_revenue,
            attributed_conversions=attributed_conversions,
            dirichlet_alpha=dict(self.dirichlet_alpha),
            total_revenue=total_revenue,
            total_conversions=total_conversions,
            n_paths=len(conversion_paths),
        )
        
        self.log_action("compute_attribution", {"n_paths": len(conversion_paths)}, result.to_dict())
        return result


class RMNElasticityAgent(DemandTwinAgent):
    """
    Estimates channel-level media elasticities with Bayesian uncertainty.
    """
    
    def __init__(
        self,
        retailer_id: str,
        channels: List[ChannelConfig],
        message_bus: Optional[AgentMessageBus] = None,
    ):
        config = CrewAIAgentConfig(
            agent_id=f"rmn-{retailer_id}-elasticity",
            role=AgentRole.ELASTICITY,
            category=AgentCategory.ANALYTICS,
            name="RMN Elasticity Analyst",
            goal="Estimate channel elasticities with uncertainty quantification",
            backstory="""You are an econometrician specializing in media 
            elasticity estimation. You use Bayesian regression to estimate 
            how revenue responds to spend changes across channels.""",
            retailer_id=retailer_id,
        )
        super().__init__(config, message_bus)
        
        self.channels = channels
        self.posteriors: Dict[str, ElasticityPosterior] = {}
        
        # Initialize priors
        for channel in channels:
            self.posteriors[channel.channel_id] = ElasticityPosterior(
                channel_id=channel.channel_id,
                mean=channel.prior_elasticity_mean,
                std=channel.prior_elasticity_std,
                ci_lower=channel.prior_elasticity_mean - 1.645 * channel.prior_elasticity_std,
                ci_upper=channel.prior_elasticity_mean + 1.645 * channel.prior_elasticity_std,
                prior_mean=channel.prior_elasticity_mean,
                prior_std=channel.prior_elasticity_std,
            )
    
    def estimate_elasticity(
        self,
        channel_id: str,
        spend: np.ndarray,
        revenue: np.ndarray
    ) -> ElasticityPosterior:
        """Estimate elasticity for a channel from spend-revenue data"""
        if channel_id not in self.posteriors:
            raise ValueError(f"Unknown channel: {channel_id}")
        
        prior = self.posteriors[channel_id]
        
        # Log-log regression
        eps = 1e-6
        log_spend = np.log(np.maximum(spend, eps))
        log_revenue = np.log(np.maximum(revenue, eps))
        
        n = len(spend)
        if n < 10:
            return prior
        
        # OLS
        X = np.column_stack([np.ones(n), log_spend])
        try:
            beta = np.linalg.lstsq(X, log_revenue, rcond=None)[0]
            elasticity = np.clip(beta[1], -0.5, 1.0)
            
            residuals = log_revenue - X @ beta
            sigma = np.std(residuals)
            XtX_inv = np.linalg.inv(X.T @ X)
            se = np.sqrt(max(sigma**2 * XtX_inv[1, 1], 1e-6))
        except:
            return prior
        
        # Bayesian update
        prior_precision = 1.0 / max(prior.std**2, 1e-6)
        obs_precision = 1.0 / max(se**2, 1e-6)
        
        posterior_precision = prior_precision + obs_precision
        posterior_mean = (prior_precision * prior.mean + obs_precision * elasticity) / posterior_precision
        posterior_std = 1.0 / np.sqrt(posterior_precision)
        
        updated = ElasticityPosterior(
            channel_id=channel_id,
            mean=posterior_mean,
            std=posterior_std,
            ci_lower=posterior_mean - 1.645 * posterior_std,
            ci_upper=posterior_mean + 1.645 * posterior_std,
            n_observations=n,
            evidence_strength=min(1.0, n / 100),
            prior_mean=prior.prior_mean,
            prior_std=prior.prior_std,
        )
        
        self.posteriors[channel_id] = updated
        self.log_action("estimate_elasticity", {"channel_id": channel_id, "n": n}, updated.to_dict())
        
        return updated
    
    def get_all_posteriors(self) -> Dict[str, ElasticityPosterior]:
        """Get all channel elasticity posteriors"""
        return dict(self.posteriors)


class RMNScenarioAgent(DemandTwinAgent):
    """
    Generates allocation scenarios for optimization.
    """
    
    def __init__(
        self,
        retailer_id: str,
        channels: List[ChannelConfig],
        message_bus: Optional[AgentMessageBus] = None,
    ):
        config = CrewAIAgentConfig(
            agent_id=f"rmn-{retailer_id}-scenario",
            role=AgentRole.SCENARIO_GENERATOR,
            category=AgentCategory.SIMULATION,
            name="RMN Scenario Planner",
            goal="Generate diverse allocation scenarios for evaluation",
            backstory="""You create comprehensive scenarios for media budget 
            planning. You consider baseline, optimistic, conservative, and 
            stress test scenarios.""",
            retailer_id=retailer_id,
        )
        super().__init__(config, message_bus)
        
        self.channels = channels
    
    def generate_scenarios(
        self,
        current_allocation: Dict[str, float],
        total_budget: float,
        elasticities: Optional[Dict[str, ElasticityPosterior]] = None,
        n_scenarios: int = 5
    ) -> List[AllocationScenario]:
        """Generate allocation scenarios"""
        scenarios = []
        
        # 1. Baseline
        scenarios.append(AllocationScenario(
            scenario_id="baseline",
            name="Baseline",
            description="Maintain current allocation",
            allocation=current_allocation.copy(),
            total_spend=sum(current_allocation.values()),
            scenario_type="baseline",
        ))
        
        # 2. High Growth
        high_growth = {k: v * 1.2 for k, v in current_allocation.items()}
        scenarios.append(AllocationScenario(
            scenario_id="high_growth",
            name="High Growth",
            description="20% budget increase across all channels",
            allocation=high_growth,
            total_spend=sum(high_growth.values()),
            demand_multiplier=1.1,
            scenario_type="optimistic",
        ))
        
        # 3. Conservative
        conservative = {k: v * 0.85 for k, v in current_allocation.items()}
        scenarios.append(AllocationScenario(
            scenario_id="conservative",
            name="Conservative",
            description="15% budget reduction",
            allocation=conservative,
            total_spend=sum(conservative.values()),
            demand_multiplier=0.95,
            scenario_type="conservative",
        ))
        
        # 4. Elasticity Optimized
        if elasticities and len(current_allocation) > 1:
            optimized = current_allocation.copy()
            
            # Sort channels by elasticity
            sorted_channels = sorted(
                elasticities.items(),
                key=lambda x: x[1].mean,
                reverse=True
            )
            
            # Shift 15% from lowest to highest elasticity
            if len(sorted_channels) >= 2:
                highest = sorted_channels[0][0]
                lowest = sorted_channels[-1][0]
                if highest in optimized and lowest in optimized:
                    shift = optimized[lowest] * 0.15
                    optimized[lowest] -= shift
                    optimized[highest] += shift
            
            scenarios.append(AllocationScenario(
                scenario_id="elasticity_optimized",
                name="Elasticity Optimized",
                description="Reallocate to high-elasticity channels",
                allocation=optimized,
                total_spend=sum(optimized.values()),
                scenario_type="optimistic",
            ))
        
        # 5. Stress Test
        scenarios.append(AllocationScenario(
            scenario_id="stress_test",
            name="Stress Test",
            description="30% demand shock scenario",
            allocation=current_allocation.copy(),
            total_spend=sum(current_allocation.values()),
            demand_multiplier=0.7,
            scenario_type="stress_test",
        ))
        
        self.log_action("generate_scenarios", {"n": len(scenarios)}, 
                       {"scenario_ids": [s.scenario_id for s in scenarios]})
        
        return scenarios[:n_scenarios]


class RMNTwinAgent(DemandTwinAgent):
    """
    Digital Twin for simulating media outcomes.
    """
    
    def __init__(
        self,
        retailer_id: str,
        message_bus: Optional[AgentMessageBus] = None,
    ):
        config = CrewAIAgentConfig(
            agent_id=f"rmn-{retailer_id}-twin",
            role=AgentRole.DIGITAL_TWIN,
            category=AgentCategory.SIMULATION,
            name="RMN Digital Twin",
            goal="Simulate media outcomes with Monte Carlo methods",
            backstory="""You are the Digital Twin - a sophisticated simulation 
            engine that models how media spend translates to revenue. You run 
            Monte Carlo simulations with full uncertainty quantification.""",
            retailer_id=retailer_id,
        )
        super().__init__(config, message_bus)
    
    def simulate(
        self,
        scenario: AllocationScenario,
        elasticities: Dict[str, ElasticityPosterior],
        base_revenue: float = 1000000,
        n_simulations: int = 2000
    ) -> SimulationResult:
        """Run Monte Carlo simulation for a scenario"""
        allocation = scenario.allocation
        demand_mult = scenario.demand_multiplier
        
        revenue_samples = []
        channel_contributions: Dict[str, List[float]] = {c: [] for c in allocation}
        
        total_spend = sum(allocation.values())
        
        for _ in range(n_simulations):
            sim_revenue = base_revenue * demand_mult
            
            for channel_id, spend in allocation.items():
                if channel_id in elasticities:
                    el = elasticities[channel_id]
                    sampled_elasticity = np.random.normal(el.mean, el.std)
                else:
                    sampled_elasticity = 0.15
                
                # Revenue lift from spend
                spend_ratio = spend / max(total_spend / len(allocation), 1)
                lift = (spend_ratio ** sampled_elasticity) * np.random.normal(1, 0.05)
                contribution = sim_revenue * lift / len(allocation)
                
                channel_contributions[channel_id].append(contribution)
            
            total_sim_revenue = sum(
                np.mean(channel_contributions[c][-1:]) 
                for c in allocation
            )
            revenue_samples.append(total_sim_revenue * np.random.normal(1, 0.1))
        
        revenue_array = np.array(revenue_samples)
        roas_array = revenue_array / max(total_spend, 1)
        
        result = SimulationResult(
            scenario_id=scenario.scenario_id,
            scenario_name=scenario.name,
            expected_revenue=float(np.mean(revenue_array)),
            revenue_std=float(np.std(revenue_array)),
            revenue_ci=(float(np.percentile(revenue_array, 5)), float(np.percentile(revenue_array, 95))),
            expected_roas=float(np.mean(roas_array)),
            roas_std=float(np.std(roas_array)),
            roas_ci=(float(np.percentile(roas_array, 5)), float(np.percentile(roas_array, 95))),
            expected_conversions=float(np.mean(revenue_array) / 50),  # Assume $50 AOV
            conversion_ci=(float(np.percentile(revenue_array, 5) / 50), float(np.percentile(revenue_array, 95) / 50)),
            channel_contributions={c: float(np.mean(v)) for c, v in channel_contributions.items()},
            n_simulations=n_simulations,
            total_spend=total_spend,
        )
        
        self.log_action("simulate", {"scenario_id": scenario.scenario_id}, result.to_dict())
        return result


class RMNOptimizerAgent(DemandTwinAgent):
    """
    Selects optimal allocation from simulated scenarios.
    """
    
    def __init__(
        self,
        retailer_id: str,
        message_bus: Optional[AgentMessageBus] = None,
    ):
        config = CrewAIAgentConfig(
            agent_id=f"rmn-{retailer_id}-optimizer",
            role=AgentRole.BUDGET_OPTIMIZER,
            category=AgentCategory.OPTIMIZATION,
            name="RMN Budget Optimizer",
            goal="Find optimal budget allocation under constraints",
            backstory="""You optimize media budget allocation across channels. 
            You balance expected returns with risk and business constraints.""",
            retailer_id=retailer_id,
        )
        super().__init__(config, message_bus)
    
    def optimize(
        self,
        simulations: Dict[str, SimulationResult],
        risk_aversion: float = 0.3
    ) -> OptimizationResult:
        """Select optimal allocation from simulations"""
        if not simulations:
            raise ValueError("No simulations provided")
        
        # Score each scenario
        rankings = []
        for scenario_id, sim in simulations.items():
            # Risk-adjusted score
            score = sim.expected_revenue - risk_aversion * sim.revenue_std
            rankings.append({
                "scenario_id": scenario_id,
                "score": score,
                "expected_revenue": sim.expected_revenue,
                "expected_roas": sim.expected_roas,
                "risk": sim.revenue_std,
            })
        
        rankings.sort(key=lambda x: x["score"], reverse=True)
        best = rankings[0]
        best_sim = simulations[best["scenario_id"]]
        
        result = OptimizationResult(
            selected_scenario_id=best["scenario_id"],
            optimal_allocation=dict(best_sim.channel_contributions),
            total_budget=best_sim.total_spend,
            expected_revenue=best_sim.expected_revenue,
            expected_roas=best_sim.expected_roas,
            expected_conversions=best_sim.expected_conversions,
            objective_value=best["score"],
            risk_adjusted_score=best["score"],
            scenario_rankings=rankings,
        )
        
        self.log_action("optimize", {"n_scenarios": len(simulations)}, result.to_dict())
        return result


class RMNGovernanceAgent(DemandTwinAgent):
    """
    Validates recommendations against business policies.
    """
    
    def __init__(
        self,
        retailer_id: str,
        config: RMNConfig,
        message_bus: Optional[AgentMessageBus] = None,
    ):
        agent_config = CrewAIAgentConfig(
            agent_id=f"rmn-{retailer_id}-governance",
            role=AgentRole.POLICY_VALIDATOR,
            category=AgentCategory.GOVERNANCE,
            name="RMN Governance Validator",
            goal="Ensure recommendations comply with business policies",
            backstory="""You validate media recommendations against governance 
            policies, regulatory requirements, and risk thresholds.""",
            retailer_id=retailer_id,
        )
        super().__init__(agent_config, message_bus)
        
        self.rmn_config = config
    
    def validate(
        self,
        optimization: OptimizationResult,
        current_allocation: Dict[str, float]
    ) -> GovernanceDecision:
        """Validate optimization result against policies"""
        checks = []
        violations = []
        risk_factors = []
        
        # Check budget change limit
        current_total = sum(current_allocation.values())
        new_total = optimization.total_budget
        change_pct = abs(new_total - current_total) / max(current_total, 1)
        
        budget_check_passed = change_pct <= self.rmn_config.max_budget_change_pct
        checks.append({
            "policy": "max_budget_change",
            "passed": budget_check_passed,
            "value": change_pct,
            "threshold": self.rmn_config.max_budget_change_pct,
        })
        if not budget_check_passed:
            violations.append(f"Budget change {change_pct:.1%} exceeds limit")
            risk_factors.append("large_budget_change")
        
        # Check channel concentration
        if optimization.optimal_allocation:
            max_share = max(optimization.optimal_allocation.values()) / max(new_total, 1)
            concentration_check = max_share <= 0.6
            checks.append({
                "policy": "channel_concentration",
                "passed": concentration_check,
                "value": max_share,
                "threshold": 0.6,
            })
            if not concentration_check:
                violations.append(f"Channel concentration {max_share:.1%} too high")
                risk_factors.append("high_concentration")
        
        # Compute risk score
        risk_score = len(risk_factors) * 0.3
        
        # Determine approval
        critical_violations = [v for v in violations if "concentration" in v.lower()]
        approved = len(critical_violations) == 0
        requires_review = len(violations) > 0 and approved
        auto_approved = approved and not requires_review
        
        decision = GovernanceDecision(
            approved=approved,
            requires_review=requires_review,
            checks=checks,
            violations=violations,
            risk_score=risk_score,
            risk_factors=risk_factors,
            auto_approved=auto_approved,
        )
        
        self.log_action("validate", {"scenario_id": optimization.selected_scenario_id}, decision.to_dict())
        return decision


class RMNRationaleAgent(DemandTwinAgent):
    """
    Generates human-readable rationales for recommendations.
    """
    
    def __init__(
        self,
        retailer_id: str,
        message_bus: Optional[AgentMessageBus] = None,
    ):
        config = CrewAIAgentConfig(
            agent_id=f"rmn-{retailer_id}-rationale",
            role=AgentRole.RATIONALE_GENERATOR,
            category=AgentCategory.COMMUNICATION,
            name="RMN Business Communicator",
            goal="Generate clear, actionable explanations for recommendations",
            backstory="""You translate complex analytical results into clear 
            business language. You create compelling rationales for stakeholders.""",
            retailer_id=retailer_id,
            temperature=0.7,
        )
        super().__init__(config, message_bus)
    
    def generate_rationale(
        self,
        optimization: OptimizationResult,
        simulations: Dict[str, SimulationResult],
        governance: GovernanceDecision,
        elasticities: Dict[str, ElasticityPosterior]
    ) -> Dict[str, str]:
        """Generate rationale for the recommendation"""
        best_sim = simulations.get(optimization.selected_scenario_id)
        
        # Executive summary
        executive_summary = f"""## Retail Media Optimization Recommendation

Based on Bayesian elasticity analysis and Monte Carlo simulations, we recommend 
the **{optimization.selected_scenario_id.replace('_', ' ').title()}** allocation.

### Expected Outcomes
- **Revenue**: ${optimization.expected_revenue/1e6:.2f}M
- **ROAS**: {optimization.expected_roas:.2f}x
- **Conversions**: {optimization.expected_conversions:,.0f}

### Confidence Level
This recommendation is based on {best_sim.n_simulations if best_sim else 'N/A'} Monte Carlo simulations 
with a 90% credible interval of ${best_sim.revenue_ci[0]/1e6:.2f}M - ${best_sim.revenue_ci[1]/1e6:.2f}M.
"""
        
        # Detailed rationale
        detailed = """### Analysis Details

Our recommendation is grounded in:

1. **Elasticity Analysis**: Bayesian posteriors calibrated from historical spend-revenue data
2. **Multi-Touch Attribution**: Dirichlet-based attribution for fair channel credit
3. **Monte Carlo Simulation**: Probabilistic modeling of revenue outcomes
4. **Risk Assessment**: Risk-adjusted scoring with configurable aversion

### Channel Elasticities
"""
        for channel_id, el in elasticities.items():
            detailed += f"- **{channel_id}**: {el.mean:.3f} ± {el.std:.3f} (n={el.n_observations})\n"
        
        # Uncertainty acknowledgment
        if best_sim:
            uncertainty = f"""### Uncertainty Acknowledgment

The 90% credible interval for revenue is **${best_sim.revenue_ci[0]/1e6:.2f}M to ${best_sim.revenue_ci[1]/1e6:.2f}M**.
This uncertainty reflects:
- Model uncertainty in elasticity estimates
- Natural variability in consumer behavior
- Potential changes in market conditions

We recommend monitoring actual performance and updating elasticity estimates weekly.
"""
        else:
            uncertainty = "Uncertainty data not available."
        
        return {
            "executive_summary": executive_summary,
            "detailed_rationale": detailed,
            "uncertainty_acknowledgment": uncertainty,
        }
