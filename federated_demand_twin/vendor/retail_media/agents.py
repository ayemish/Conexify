"""
Retail Media Optimization Agents

Implements the agent layer for retail media spend optimization:
- AttributionAgent: Decomposes lift sources with Bayesian attribution
- ScenarioGenerationAgent: Generates what-if media plans
- OptimizationAgent: Solves budget allocation problem
- GovernanceAgent: Validates recommendations against business rules
- RationaleAgent: Generates human-readable explanations (LLM-powered)
"""

import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, date
import logging
import uuid
from scipy.optimize import minimize, LinearConstraint

from .schemas import (
    MediaChannel,
    RetailerConfig,
    ChannelConfig,
    SKUConfig,
    ElasticityPosterior,
    AttributionResult,
    MediaAllocation,
    MediaScenario,
    MediaSimulationResult,
    AllocationStatus,
    ValidationCheck,
    GovernanceDecision,
    GovernanceStatus,
    MediaDecisionPack,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for retail media agents"""
    # Attribution agent
    attribution_min_paths: int = 100
    attribution_lookback_days: int = 90
    
    # Scenario agent
    max_scenarios: int = 10
    include_stress_tests: bool = True
    
    # Optimization agent
    risk_aversion: float = 0.3
    stockout_penalty_weight: float = 0.5
    min_retailer_spend_share: float = 0.05
    max_channel_concentration: float = 0.4
    
    # Governance agent
    max_stockout_rate: float = 0.10
    max_allocation_change: float = 0.25
    require_human_approval_threshold: float = 0.15
    
    # Rationale agent
    llm_model: str = "proprietary-retail-media-v1"
    max_rationale_tokens: int = 500


class AttributionAgent:
    """
    Attribution Agent - Decomposes historical sales lift into channel contributions.
    
    Consumes: Historical spend + sales data, Bayesian priors
    Produces: Channel attribution posteriors with uncertainty
    Feeds: Bayesian layer with evidence for elasticity updates
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
        self.attribution_history: List[AttributionResult] = []
    
    def process(
        self,
        conversion_paths: List[List[str]],
        spend_by_channel: Dict[str, float],
        total_incremental_sales: float,
        prior_shares: Optional[Dict[str, float]] = None
    ) -> AttributionResult:
        """
        Compute multi-touch attribution for a period.
        
        Args:
            conversion_paths: List of customer journey paths
            spend_by_channel: Spend per channel
            total_incremental_sales: Total lift to attribute
            prior_shares: Optional prior belief about channel shares
        
        Returns:
            AttributionResult with channel contributions and uncertainty
        """
        n_paths = len(conversion_paths)
        channels = list(MediaChannel)
        n_channels = len(channels)
        
        if n_paths < self.config.attribution_min_paths:
            logger.warning(
                f"Low path count ({n_paths}) may result in high attribution uncertainty"
            )
        
        # Count weighted touches per channel
        touch_weights = {c.value: 0.0 for c in channels}
        
        for path in conversion_paths:
            path_len = len(path)
            if path_len == 0:
                continue
            
            for i, channel in enumerate(path):
                if channel not in touch_weights:
                    continue
                
                # Position-based weighting
                if path_len == 1:
                    weight = 1.0
                elif i == path_len - 1:
                    weight = 0.4  # Last touch
                elif i == 0:
                    weight = 0.2  # First touch
                else:
                    weight = 0.4 / max(1, path_len - 2)  # Middle touches
                
                touch_weights[channel] += weight
        
        # Compute Dirichlet posterior
        alpha_prior = 1.0
        if prior_shares:
            alpha = {c: prior_shares.get(c, alpha_prior) * 10 + touch_weights.get(c, 0)
                     for c in touch_weights}
        else:
            alpha = {c: alpha_prior + touch_weights.get(c, 0) for c in touch_weights}
        
        alpha_array = np.array(list(alpha.values()))
        posterior_mean = alpha_array / alpha_array.sum()
        
        # Sample for credible intervals
        samples = np.random.dirichlet(alpha_array, size=5000)
        ci_lower = np.percentile(samples, 5, axis=0)
        ci_upper = np.percentile(samples, 95, axis=0)
        
        channel_names = list(alpha.keys())
        channel_shares = {channel_names[i]: float(posterior_mean[i]) for i in range(n_channels)}
        channel_share_ci = {
            channel_names[i]: (float(ci_lower[i]), float(ci_upper[i]))
            for i in range(n_channels)
        }
        
        # Compute ROAS
        total_spend = sum(spend_by_channel.values())
        overall_roas = total_incremental_sales / total_spend if total_spend > 0 else 0.0
        
        # Confidence based on sample size
        attribution_confidence = min(1.0, n_paths / 1000)
        
        # Detect anomalies
        anomalies = self._detect_anomalies(
            channel_shares, channel_share_ci, spend_by_channel
        )
        
        result = AttributionResult(
            period_start=date.today(),
            period_end=date.today(),
            channel_shares=channel_shares,
            channel_share_ci=channel_share_ci,
            total_incremental_sales=total_incremental_sales,
            total_spend=total_spend,
            overall_roas=overall_roas,
            attribution_confidence=attribution_confidence,
            anomalies=anomalies,
            model_version="attribution-agent-v1.0.0"
        )
        
        self.attribution_history.append(result)
        logger.info(f"Attribution computed: {len(anomalies)} anomalies detected")
        
        return result
    
    def _detect_anomalies(
        self,
        shares: Dict[str, float],
        share_ci: Dict[str, Tuple[float, float]],
        spend: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        """Detect attribution anomalies"""
        anomalies = []
        total_spend = sum(spend.values())
        
        for channel, share in shares.items():
            ci = share_ci.get(channel, (0, 1))
            ci_width = ci[1] - ci[0]
            
            # High variance
            if ci_width > 0.25:
                anomalies.append({
                    'type': 'high_variance',
                    'channel': channel,
                    'message': f'{channel} has high uncertainty (CI: {ci_width:.1%})',
                    'severity': 'warning'
                })
            
            # Spend-attribution mismatch
            channel_spend = spend.get(channel, 0)
            spend_share = channel_spend / total_spend if total_spend > 0 else 0
            
            if spend_share > 0.15 and share < spend_share * 0.3:
                anomalies.append({
                    'type': 'low_efficiency',
                    'channel': channel,
                    'message': f'{channel}: {spend_share:.0%} spend → {share:.0%} attribution',
                    'severity': 'warning'
                })
        
        return anomalies


class ScenarioGenerationAgent:
    """
    Scenario Generation Agent - Creates candidate media plans for Twin evaluation.
    
    Consumes: Current allocation, Bayesian elasticity posteriors
    Produces: List of candidate MediaScenarios
    Feeds: Digital Twin with scenarios to simulate
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
    
    def generate_scenarios(
        self,
        current_allocation: MediaAllocation,
        elasticity_posteriors: Dict[str, Dict[str, ElasticityPosterior]],
        retailers: Dict[str, RetailerConfig],
        constraints: Optional[Dict[str, Any]] = None
    ) -> List[MediaScenario]:
        """
        Generate candidate scenarios for simulation.
        
        Args:
            current_allocation: Current media spend allocation
            elasticity_posteriors: Bayesian posteriors by retailer/channel
            retailers: Retailer configurations
            constraints: Optional spend constraints
        
        Returns:
            List of MediaScenarios for Twin simulation
        """
        scenarios = []
        
        # 1. Baseline scenario (current allocation)
        scenarios.append(self._create_baseline_scenario(current_allocation))
        
        # 2. Elasticity-maximizing scenario
        high_elasticity = self._optimize_for_elasticity(
            current_allocation, elasticity_posteriors, retailers
        )
        scenarios.append(high_elasticity)
        
        # 3. Risk-minimizing scenario (avoid high-stockout retailers)
        low_risk = self._optimize_for_risk(
            current_allocation, elasticity_posteriors, retailers
        )
        scenarios.append(low_risk)
        
        # 4. Exploration scenario (test uncertain channels)
        exploration = self._optimize_for_learning(
            current_allocation, elasticity_posteriors, retailers
        )
        scenarios.append(exploration)
        
        # 5. Stress tests
        if self.config.include_stress_tests:
            scenarios.extend(self._generate_stress_tests(current_allocation))
        
        logger.info(f"Generated {len(scenarios)} scenarios for simulation")
        return scenarios[:self.config.max_scenarios]
    
    def _create_baseline_scenario(self, allocation: MediaAllocation) -> MediaScenario:
        """Create baseline scenario from current allocation"""
        return MediaScenario(
            scenario_id=f"baseline-{uuid.uuid4().hex[:8]}",
            scenario_name="Baseline",
            description="Current allocation with no changes",
            allocation=allocation
        )
    
    def _optimize_for_elasticity(
        self,
        allocation: MediaAllocation,
        posteriors: Dict[str, Dict[str, ElasticityPosterior]],
        retailers: Dict[str, RetailerConfig]
    ) -> MediaScenario:
        """Shift budget to highest-elasticity channels"""
        new_spend = {}
        
        for retailer_id in allocation.spend_by_retailer_channel:
            retailer_posteriors = posteriors.get(retailer_id, {})
            current_spend = allocation.spend_by_retailer_channel[retailer_id]
            
            # Rank channels by elasticity
            channel_elasticities = []
            for channel, spend in current_spend.items():
                # Find matching posterior
                for key, post in retailer_posteriors.items():
                    if channel in key:
                        channel_elasticities.append((channel, post.mean, spend))
                        break
                else:
                    channel_elasticities.append((channel, 0.15, spend))
            
            # Sort by elasticity (descending)
            channel_elasticities.sort(key=lambda x: x[1], reverse=True)
            
            # Reallocate: top channels get more
            total_retailer_spend = sum(current_spend.values())
            new_retailer_spend = {}
            
            for i, (channel, elasticity, orig_spend) in enumerate(channel_elasticities):
                if i < len(channel_elasticities) // 3:
                    # Top third: +30%
                    new_retailer_spend[channel] = orig_spend * 1.3
                elif i < 2 * len(channel_elasticities) // 3:
                    # Middle third: no change
                    new_retailer_spend[channel] = orig_spend
                else:
                    # Bottom third: -30%
                    new_retailer_spend[channel] = orig_spend * 0.7
            
            # Normalize to maintain total budget
            total_new = sum(new_retailer_spend.values())
            if total_new > 0:
                scale = total_retailer_spend / total_new
                new_retailer_spend = {k: v * scale for k, v in new_retailer_spend.items()}
            
            new_spend[retailer_id] = new_retailer_spend
        
        new_allocation = MediaAllocation(
            allocation_id=f"high-elasticity-{uuid.uuid4().hex[:8]}",
            name="High Elasticity",
            total_budget=allocation.total_budget,
            period_weeks=allocation.period_weeks,
            spend_by_retailer_channel=new_spend
        )
        
        return MediaScenario(
            scenario_id=f"high-elasticity-{uuid.uuid4().hex[:8]}",
            scenario_name="High Elasticity",
            description="Shift budget to channels with highest estimated elasticity",
            allocation=new_allocation
        )
    
    def _optimize_for_risk(
        self,
        allocation: MediaAllocation,
        posteriors: Dict[str, Dict[str, ElasticityPosterior]],
        retailers: Dict[str, RetailerConfig]
    ) -> MediaScenario:
        """Reduce spend on high-stockout-risk retailers"""
        new_spend = {}
        
        for retailer_id, channels in allocation.spend_by_retailer_channel.items():
            retailer = retailers.get(retailer_id)
            
            if retailer and retailer.stockout_sensitivity > 1.2:
                # High stockout risk: reduce spend by 20%
                new_spend[retailer_id] = {c: s * 0.8 for c, s in channels.items()}
            elif retailer and retailer.avg_inventory_weeks < 3:
                # Low inventory: reduce spend by 15%
                new_spend[retailer_id] = {c: s * 0.85 for c, s in channels.items()}
            else:
                new_spend[retailer_id] = channels.copy()
        
        # Redistribute reduced spend to low-risk retailers
        original_total = sum(sum(c.values()) for c in allocation.spend_by_retailer_channel.values())
        new_total = sum(sum(c.values()) for c in new_spend.values())
        surplus = original_total - new_total
        
        if surplus > 0:
            # Find low-risk retailers
            low_risk_retailers = [
                r for r in retailers.values()
                if r.stockout_sensitivity <= 1.0 and r.avg_inventory_weeks >= 4
            ]
            if low_risk_retailers:
                bonus_per_retailer = surplus / len(low_risk_retailers)
                for retailer in low_risk_retailers:
                    if retailer.retailer_id in new_spend:
                        for channel in new_spend[retailer.retailer_id]:
                            new_spend[retailer.retailer_id][channel] += bonus_per_retailer / len(new_spend[retailer.retailer_id])
        
        new_allocation = MediaAllocation(
            allocation_id=f"low-risk-{uuid.uuid4().hex[:8]}",
            name="Inventory Safe",
            total_budget=allocation.total_budget,
            period_weeks=allocation.period_weeks,
            spend_by_retailer_channel=new_spend
        )
        
        return MediaScenario(
            scenario_id=f"low-risk-{uuid.uuid4().hex[:8]}",
            scenario_name="Inventory Safe",
            description="Reduce spend on retailers with high stockout risk",
            allocation=new_allocation
        )
    
    def _optimize_for_learning(
        self,
        allocation: MediaAllocation,
        posteriors: Dict[str, Dict[str, ElasticityPosterior]],
        retailers: Dict[str, RetailerConfig]
    ) -> MediaScenario:
        """Allocate budget to uncertain channels to reduce posterior variance"""
        new_spend = {}
        
        for retailer_id, channels in allocation.spend_by_retailer_channel.items():
            retailer_posteriors = posteriors.get(retailer_id, {})
            new_retailer_spend = channels.copy()
            
            # Find high-uncertainty channels
            for key, post in retailer_posteriors.items():
                channel = key.split(":")[0]
                if channel in new_retailer_spend and post.evidence_strength < 0.5:
                    # Low evidence: boost spend by 20% for learning
                    new_retailer_spend[channel] = new_retailer_spend.get(channel, 0) * 1.2
            
            new_spend[retailer_id] = new_retailer_spend
        
        # Normalize to budget
        total = sum(sum(c.values()) for c in new_spend.values())
        if total > allocation.total_budget:
            scale = allocation.total_budget / total
            new_spend = {
                r: {c: s * scale for c, s in channels.items()}
                for r, channels in new_spend.items()
            }
        
        new_allocation = MediaAllocation(
            allocation_id=f"explore-{uuid.uuid4().hex[:8]}",
            name="Explore Uncertain",
            total_budget=allocation.total_budget,
            period_weeks=allocation.period_weeks,
            spend_by_retailer_channel=new_spend
        )
        
        return MediaScenario(
            scenario_id=f"explore-{uuid.uuid4().hex[:8]}",
            scenario_name="Explore Uncertain",
            description="Boost spend on uncertain channels to improve measurement",
            allocation=new_allocation
        )
    
    def _generate_stress_tests(
        self,
        allocation: MediaAllocation
    ) -> List[MediaScenario]:
        """Generate stress test scenarios"""
        stress_tests = []
        
        # Demand surge
        stress_tests.append(MediaScenario(
            scenario_id=f"demand-surge-{uuid.uuid4().hex[:8]}",
            scenario_name="Demand Surge",
            description="What if demand increases 30%?",
            allocation=allocation,
            demand_multiplier=1.3
        ))
        
        # Supply disruption
        stress_tests.append(MediaScenario(
            scenario_id=f"supply-disruption-{uuid.uuid4().hex[:8]}",
            scenario_name="Supply Disruption",
            description="What if 20% of supply is lost?",
            allocation=allocation,
            supply_disruption=0.2
        ))
        
        # Reduced effectiveness
        stress_tests.append(MediaScenario(
            scenario_id=f"low-effectiveness-{uuid.uuid4().hex[:8]}",
            scenario_name="Low Effectiveness",
            description="What if elasticities are 30% lower than expected?",
            allocation=allocation,
            elasticity_multiplier=0.7
        ))
        
        return stress_tests


class OptimizationAgent:
    """
    Optimization Agent - Solves the constrained budget allocation problem.
    
    Consumes: Twin simulation results, constraints
    Produces: Optimal MediaAllocation
    Feeds: Governance Agent for approval
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
    
    def optimize(
        self,
        simulation_results: Dict[str, MediaSimulationResult],
        retailers: Dict[str, RetailerConfig],
        total_budget: float,
        period_weeks: int,
        constraints: Optional[Dict[str, Any]] = None
    ) -> MediaAllocation:
        """
        Solve for optimal allocation given simulation results.
        
        Uses expected value with risk penalty:
            maximize E[sales] - λ × (E[sales] - CVaR_5%)
                             - μ × E[stockout_rate]
        
        Subject to:
            - Budget constraint
            - Minimum retailer spend shares
            - Maximum channel concentration
        """
        # Find best performing scenario as starting point
        best_scenario_id = None
        best_score = float('-inf')
        
        for scenario_id, result in simulation_results.items():
            score = self._compute_score(result)
            if score > best_score:
                best_score = score
                best_scenario_id = scenario_id
        
        if best_scenario_id is None:
            raise ValueError("No valid simulation results")
        
        best_result = simulation_results[best_scenario_id]
        
        # For MVP: return the best scenario's allocation with minor adjustments
        # In production: would use scipy.optimize or cvxpy for proper optimization
        
        # Extract allocation from the winning scenario
        # (In practice, the scenario would carry its allocation)
        
        # Create optimized allocation
        # Start with equal distribution and adjust based on results
        n_retailers = len(retailers)
        per_retailer = total_budget / max(1, n_retailers)
        
        # Adjust based on retailer results
        spend = {}
        for retailer_id, retailer in retailers.items():
            retailer_results = best_result.retailer_results.get(retailer_id, {})
            
            # Base allocation
            retailer_spend = per_retailer
            
            # Adjust based on performance
            if 'expected_sales' in retailer_results:
                performance_factor = min(1.5, max(0.5, 
                    retailer_results['expected_sales'] / (per_retailer * 5) if per_retailer > 0 else 1.0
                ))
                retailer_spend *= performance_factor
            
            # Respect min/max constraints
            retailer_spend = max(retailer.min_quarterly_spend, retailer_spend)
            retailer_spend = min(retailer.max_quarterly_spend, retailer_spend)
            
            # Distribute across channels
            n_channels = len(retailer.available_channels)
            if n_channels > 0:
                per_channel = retailer_spend / n_channels
                spend[retailer_id] = {
                    c.value: per_channel for c in retailer.available_channels
                }
            else:
                spend[retailer_id] = {MediaChannel.SPONSORED_SEARCH.value: retailer_spend}
        
        # Normalize to budget
        current_total = sum(sum(c.values()) for c in spend.values())
        if current_total > 0:
            scale = total_budget / current_total
            spend = {
                r: {c: s * scale for c, s in channels.items()}
                for r, channels in spend.items()
            }
        
        allocation = MediaAllocation(
            allocation_id=f"optimized-{uuid.uuid4().hex[:8]}",
            name=f"Optimized (based on {best_result.scenario_name})",
            total_budget=total_budget,
            period_weeks=period_weeks,
            spend_by_retailer_channel=spend,
            status=AllocationStatus.PENDING_APPROVAL
        )
        
        logger.info(
            f"Optimization complete: selected {best_result.scenario_name} "
            f"with score {best_score:.2f}"
        )
        
        return allocation
    
    def _compute_score(self, result: MediaSimulationResult) -> float:
        """Compute objective score for a simulation result"""
        expected_sales = result.expected_incremental_sales
        downside_risk = expected_sales - result.sales_ci_lower
        stockout_penalty = result.expected_stockout_rate * expected_sales
        
        score = (
            expected_sales
            - self.config.risk_aversion * downside_risk
            - self.config.stockout_penalty_weight * stockout_penalty
        )
        
        return score


class GovernanceAgent:
    """
    Governance Agent - Validates recommendations against business rules.
    
    Consumes: Optimization recommendation, business rules
    Produces: Approval/rejection with explanation
    Feeds: Rationale Agent if approved, escalates if rejected
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
    
    def validate(
        self,
        recommendation: MediaAllocation,
        simulation_result: MediaSimulationResult,
        prior_allocation: Optional[MediaAllocation] = None,
        retailers: Optional[Dict[str, RetailerConfig]] = None
    ) -> GovernanceDecision:
        """
        Validate a recommendation against governance rules.
        
        Checks:
        1. Minimum retailer spend shares
        2. Stockout risk thresholds
        3. Allocation stability (week-over-week change)
        4. Channel concentration limits
        """
        checks = []
        
        # Check 1: Minimum retailer spend
        if retailers:
            for retailer_id, retailer in retailers.items():
                retailer_spend = recommendation.get_retailer_total(retailer_id)
                spend_share = retailer_spend / recommendation.total_budget if recommendation.total_budget > 0 else 0
                
                if spend_share < retailer.min_spend_share:
                    checks.append(ValidationCheck(
                        rule_name="MinRetailerSpend",
                        passed=False,
                        message=f"{retailer.retailer_name}: {spend_share:.1%} < {retailer.min_spend_share:.1%} minimum",
                        severity="error"
                    ))
                else:
                    checks.append(ValidationCheck(
                        rule_name="MinRetailerSpend",
                        passed=True,
                        message=f"{retailer.retailer_name}: {spend_share:.1%} meets minimum"
                    ))
        
        # Check 2: Stockout risk
        if simulation_result.expected_stockout_rate > self.config.max_stockout_rate:
            checks.append(ValidationCheck(
                rule_name="StockoutRiskCap",
                passed=False,
                message=f"Expected stockout rate {simulation_result.expected_stockout_rate:.1%} > {self.config.max_stockout_rate:.1%} cap",
                severity="error"
            ))
        else:
            checks.append(ValidationCheck(
                rule_name="StockoutRiskCap",
                passed=True,
                message=f"Stockout rate {simulation_result.expected_stockout_rate:.1%} within limits"
            ))
        
        # Check 3: Allocation stability
        if prior_allocation:
            max_change = 0.0
            for retailer_id in recommendation.spend_by_retailer_channel:
                new_spend = recommendation.get_retailer_total(retailer_id)
                old_spend = prior_allocation.get_retailer_total(retailer_id)
                
                if old_spend > 0:
                    change = abs(new_spend - old_spend) / old_spend
                    max_change = max(max_change, change)
            
            if max_change > self.config.max_allocation_change:
                checks.append(ValidationCheck(
                    rule_name="AllocationStability",
                    passed=False,
                    message=f"Max retailer change {max_change:.1%} > {self.config.max_allocation_change:.1%} limit",
                    severity="warning"
                ))
            else:
                checks.append(ValidationCheck(
                    rule_name="AllocationStability",
                    passed=True,
                    message=f"Allocation changes within stability bounds"
                ))
        
        # Check 4: Channel concentration
        for channel in MediaChannel:
            channel_spend = recommendation.get_channel_total(channel.value)
            channel_share = channel_spend / recommendation.total_budget if recommendation.total_budget > 0 else 0
            
            if channel_share > self.config.max_channel_concentration:
                checks.append(ValidationCheck(
                    rule_name="ChannelConcentration",
                    passed=False,
                    message=f"{channel.value}: {channel_share:.1%} > {self.config.max_channel_concentration:.1%} max",
                    severity="warning"
                ))
        
        # Determine overall decision
        errors = [c for c in checks if not c.passed and c.severity == "error"]
        warnings = [c for c in checks if not c.passed and c.severity == "warning"]
        
        if errors:
            status = GovernanceStatus.FAILED
            approved = False
            requires_human = True
            escalation = f"{len(errors)} rule violations require review"
        elif warnings:
            status = GovernanceStatus.REQUIRES_REVIEW
            approved = False
            requires_human = True
            escalation = f"{len(warnings)} warnings flagged for review"
        else:
            status = GovernanceStatus.PASSED
            approved = True
            requires_human = False
            escalation = None
        
        decision = GovernanceDecision(
            approved=approved,
            status=status,
            checks=checks,
            requires_human_approval=requires_human,
            escalation_reason=escalation
        )
        
        logger.info(f"Governance decision: {status.value}, {len(checks)} checks performed")
        return decision


class RationaleAgent:
    """
    Rationale Agent - Generates human-readable explanations.
    
    This agent would be powered by a proprietary LLM fine-tuned on:
    - Historical decision packs
    - Bayesian posterior descriptions
    - Twin simulation narratives
    
    For MVP: Uses template-based generation.
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
    
    def generate_rationale(
        self,
        recommendation: MediaAllocation,
        simulation_results: Dict[str, MediaSimulationResult],
        elasticity_posteriors: Dict[str, Dict[str, ElasticityPosterior]],
        governance_decision: GovernanceDecision,
        prior_allocation: Optional[MediaAllocation] = None
    ) -> Dict[str, str]:
        """
        Generate human-readable rationale for the recommendation.
        
        Returns:
            Dict with 'executive_summary', 'detailed_rationale', 'uncertainty_acknowledgment'
        """
        # Find best simulation result
        best_result = None
        for result in simulation_results.values():
            if best_result is None or result.expected_incremental_sales > best_result.expected_incremental_sales:
                best_result = result
        
        if best_result is None:
            return {
                'executive_summary': "Insufficient data for recommendation.",
                'detailed_rationale': "",
                'uncertainty_acknowledgment': ""
            }
        
        # Generate executive summary
        executive_summary = self._generate_executive_summary(
            recommendation, best_result, elasticity_posteriors
        )
        
        # Generate detailed rationale
        detailed_rationale = self._generate_detailed_rationale(
            recommendation, simulation_results, elasticity_posteriors
        )
        
        # Generate uncertainty acknowledgment
        uncertainty = self._generate_uncertainty_acknowledgment(
            elasticity_posteriors, best_result
        )
        
        return {
            'executive_summary': executive_summary,
            'detailed_rationale': detailed_rationale,
            'uncertainty_acknowledgment': uncertainty
        }
    
    def _generate_executive_summary(
        self,
        allocation: MediaAllocation,
        result: MediaSimulationResult,
        posteriors: Dict[str, Dict[str, ElasticityPosterior]]
    ) -> str:
        """Generate executive summary"""
        # Find top elasticity channels
        top_channels = []
        for retailer_posts in posteriors.values():
            for key, post in retailer_posts.items():
                channel = key.split(":")[0]
                top_channels.append((channel, post.mean, post.ci_lower, post.ci_upper))
        
        top_channels.sort(key=lambda x: x[1], reverse=True)
        top_channel = top_channels[0] if top_channels else ("sponsored_search", 0.15, 0.10, 0.20)
        
        summary = f"""## Q{(datetime.now().month - 1) // 3 + 1} Retail Media Recommendation

We recommend an allocation of ${allocation.total_budget/1e6:.1f}M across {len(allocation.spend_by_retailer_channel)} retailers. This reallocation is grounded in our Bayesian elasticity analysis: {top_channel[0].replace('_', ' ').title()} shows the highest elasticity of {top_channel[1]:.2f} (90% CI: {top_channel[2]:.2f}-{top_channel[3]:.2f}).

**Expected Outcomes:**
- Incremental Sales: ${result.expected_incremental_sales/1e6:.1f}M (90% CI: ${result.sales_ci_lower/1e6:.1f}M - ${result.sales_ci_upper/1e6:.1f}M)
- ROAS: {result.expected_roas:.1f}x
- Stockout Risk: {result.expected_stockout_rate:.1%}
"""
        return summary
    
    def _generate_detailed_rationale(
        self,
        allocation: MediaAllocation,
        results: Dict[str, MediaSimulationResult],
        posteriors: Dict[str, Dict[str, ElasticityPosterior]]
    ) -> str:
        """Generate detailed rationale"""
        rationale = "### Scenario Analysis\n\n"
        
        for scenario_id, result in results.items():
            rationale += f"**{result.scenario_name}**: "
            rationale += f"${result.expected_incremental_sales/1e6:.1f}M expected sales, "
            rationale += f"{result.expected_roas:.1f}x ROAS, "
            rationale += f"{result.expected_stockout_rate:.1%} stockout risk\n"
        
        rationale += "\n### Retailer Allocation\n\n"
        for retailer_id, channels in allocation.spend_by_retailer_channel.items():
            total = sum(channels.values())
            rationale += f"- **{retailer_id}**: ${total/1e6:.2f}M "
            rationale += f"({total/allocation.total_budget*100:.0f}% of budget)\n"
        
        return rationale
    
    def _generate_uncertainty_acknowledgment(
        self,
        posteriors: Dict[str, Dict[str, ElasticityPosterior]],
        result: MediaSimulationResult
    ) -> str:
        """Generate uncertainty acknowledgment"""
        # Find high-uncertainty estimates
        high_uncertainty = []
        for retailer_id, retailer_posts in posteriors.items():
            for key, post in retailer_posts.items():
                if post.evidence_strength < 0.5:
                    channel = key.split(":")[0]
                    high_uncertainty.append((retailer_id, channel, post.std / post.mean))
        
        high_uncertainty.sort(key=lambda x: x[2], reverse=True)
        
        ack = "### Key Uncertainties\n\n"
        
        if high_uncertainty:
            top_uncertain = high_uncertainty[0]
            ack += f"Our {top_uncertain[1].replace('_', ' ')} elasticity estimate for {top_uncertain[0]} has high variance "
            ack += f"(coefficient of variation: {top_uncertain[2]:.0%}) due to limited measurement data. "
        
        ack += f"\n\nThe 90% credible interval on expected sales spans "
        ack += f"${result.sales_ci_lower/1e6:.1f}M to ${result.sales_ci_upper/1e6:.1f}M, "
        ack += f"reflecting simulation uncertainty across {result.n_simulations} Monte Carlo paths."
        
        if result.binding_constraints:
            ack += f"\n\n**Binding Constraints**: {', '.join(result.binding_constraints)}"
        
        return ack
