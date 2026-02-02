"""
Scenario Optimization Crews

Orchestration crews that run parameterized "what-if" optimizations for
four desired outcomes:
- INCREASE_REVENUE: Maximize incremental dollar sales
- INCREASE_MARGIN: Maximize incremental gross profit
- MAINTAIN_REVENUE: Minimize spend subject to revenue floor
- REDUCE_COST: Minimize spend while protecting priority KPIs

Core Agents (Scenario Orchestrator):
- Scenario Director (manager)
- Scenario Intake Analyst
- Objective Router
- Data Context Builder
- Response Curve Modeler
- Constraint Builder
- Optimization Solver
- Sensitivity & Robustness Analyst
- Scenario Comparator
- Narrator + QA Auditor
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Type
import numpy as np
import logging

from .base_crew import BaseOptimizationCrew, AgentDefinition, TaskDefinition
from .schemas import (
    DesiredOutcome,
    CrewConfig,
    ScenarioConfig,
    CrewOutput,
    OptimizationResult,
    AllocationRecommendation,
    ImpactEstimate,
    RiskAssessment,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ScenarioOrchestratorCrew(BaseOptimizationCrew):
    """
    Scenario Orchestrator Crew - Generic.
    
    Purpose: Run parameterized optimization scenarios end-to-end and
    produce comparable scenario outputs.
    
    Inputs:
    - Scenario brief: desired_outcome, budget, constraints
    - Baseline performance and allocation data
    - Response curves or historical performance
    
    Outputs:
    - Scenario plan: optimized allocation and tactical actions
    - Scenario comparison: baseline vs scenario deltas
    - Governance pack: assumptions, confidence, risks, measurement plan
    """
    
    def __init__(
        self,
        config: CrewConfig,
        scenario_config: Optional[ScenarioConfig] = None,
        performance_data: Optional[Dict[str, Any]] = None,
        sub_crews: Optional[Dict[str, BaseOptimizationCrew]] = None,
    ):
        self.scenario_config = scenario_config or ScenarioConfig()
        self.sub_crews = sub_crews or {}
        self.scenario_results: Dict[str, CrewOutput] = {}
        super().__init__(config, performance_data)
    
    @property
    def crew_type(self) -> str:
        return "scenario_orchestrator"
    
    def _setup_agents(self) -> None:
        """Define scenario orchestrator agents."""
        
        self.agents["scenario_director"] = AgentDefinition(
            agent_id="scenario_director",
            role="Scenario Director",
            name="Scenario Director",
            goal="Final decision-maker; select which sub-crews to invoke",
            backstory="""You are the chief strategist who orchestrates complex 
            optimization scenarios. You decide which level crews to invoke 
            (Brand, RMN, Campaign, Channel), sequence their execution, and 
            synthesize their outputs into a coherent recommendation.""",
            tools=["crew_invoker_tool", "decision_framework_tool"],
            allow_delegation=True,
            verbose=True,
        )
        
        self.agents["scenario_intake_analyst"] = AgentDefinition(
            agent_id="scenario_intake_analyst",
            role="Scenario Intake Analyst",
            name="Scenario Intake Analyst",
            goal="Normalize scenario inputs and resolve missing parameters",
            backstory="""You process scenario requests and ensure all required 
            parameters are present and valid. You fill in defaults for missing 
            values, validate constraints, and prepare the scenario for execution.""",
            tools=["parameter_validator_tool", "default_resolver_tool"],
        )
        
        self.agents["objective_router"] = AgentDefinition(
            agent_id="objective_router",
            role="Objective Router",
            name="Objective Router",
            goal="Set objective weights and KPI floors based on desired outcome",
            backstory="""You translate business objectives into mathematical 
            optimization parameters. You set the right objective function 
            weights, constraints, and KPI floors for each desired outcome 
            (revenue, margin, maintain, cost reduction).""",
            tools=["objective_configurator_tool"],
        )
        
        self.agents["data_context_builder"] = AgentDefinition(
            agent_id="data_context_builder",
            role="Data Context Builder",
            name="Data Context Builder",
            goal="Subset and aggregate data to the optimization grain",
            backstory="""You prepare the data context for optimization. You 
            filter data by brand, RMN, channel, and time window. You aggregate 
            to the right grain and ensure all required metrics are present.""",
            tools=["data_filter_tool", "aggregator_tool"],
        )
        
        self.agents["response_curve_modeler"] = AgentDefinition(
            agent_id="response_curve_modeler",
            role="Response Curve Modeler",
            name="Response Curve Modeler",
            goal="Estimate marginal return curves and uncertainty bands",
            backstory="""You estimate response curves from historical data. 
            You fit saturation curves, estimate marginal returns at different 
            spend levels, and quantify uncertainty in the estimates. You use 
            Bayesian priors when data is sparse.""",
            tools=["curve_fitter_tool", "uncertainty_estimator_tool"],
        )
        
        self.agents["constraint_builder"] = AgentDefinition(
            agent_id="constraint_builder",
            role="Constraint Builder",
            name="Constraint Builder",
            goal="Encode business rules into solver-friendly format",
            backstory="""You translate business constraints into mathematical 
            constraints for the optimizer. You handle budget caps, floors, 
            ceilings, pacing requirements, and retailer commitments.""",
            tools=["constraint_encoder_tool"],
        )
        
        self.agents["optimization_solver"] = AgentDefinition(
            agent_id="optimization_solver",
            role="Optimization Solver",
            name="Optimization Solver",
            goal="Produce optimal allocation and optional discrete actions",
            backstory="""You are the mathematical optimizer. You solve for the 
            allocation that maximizes (or minimizes) the objective while 
            satisfying all constraints. You report shadow prices and identify 
            binding constraints.""",
            tools=["solver_tool", "shadow_price_calculator_tool"],
        )
        
        self.agents["sensitivity_robustness_analyst"] = AgentDefinition(
            agent_id="sensitivity_robustness_analyst",
            role="Sensitivity & Robustness Analyst",
            name="Sensitivity & Robustness Analyst",
            goal="Stress-test plans and identify fragile recommendations",
            backstory="""You test the robustness of optimization solutions. 
            You run sensitivity analyses, stress tests, and Monte Carlo 
            simulations to identify fragile recommendations that depend 
            heavily on uncertain inputs.""",
            tools=["sensitivity_tool", "stress_test_tool", "monte_carlo_tool"],
        )
        
        self.agents["scenario_comparator"] = AgentDefinition(
            agent_id="scenario_comparator",
            role="Scenario Comparator",
            name="Scenario Comparator",
            goal="Generate multi-scenario tables and narratives",
            backstory="""You compare multiple scenarios and create clear 
            comparisons for decision-makers. You generate tables showing 
            baseline vs optimized, scenario vs scenario, and tradeoffs 
            between objectives.""",
            tools=["comparison_generator_tool", "tradeoff_visualizer_tool"],
        )
        
        self.agents["narrator_qa"] = AgentDefinition(
            agent_id="narrator_qa",
            role="Narrator & QA Auditor",
            name="Narrator & QA Auditor",
            goal="Package and validate scenario outputs",
            backstory="""You create the final scenario narrative and perform 
            quality assurance. You write executive summaries, validate all 
            calculations, and ensure the governance pack is complete.""",
            tools=["narrative_generator_tool", "qa_validator_tool"],
        )
    
    def _setup_tasks(self) -> None:
        """Define scenario orchestrator tasks."""
        
        self.tasks["intake_scenario"] = TaskDefinition(
            task_id="intake_scenario",
            description="""Process scenario request:
            - Validate all required parameters
            - Resolve missing values with defaults
            - Confirm desired outcome and constraints
            - Identify scope (brands, RMNs, channels, time window)""",
            expected_output="Validated scenario brief",
            agent_id="scenario_intake_analyst",
        )
        
        self.tasks["route_objective"] = TaskDefinition(
            task_id="route_objective",
            description="""Configure objective function:
            - Set primary objective based on desired outcome
            - Configure objective weights
            - Set KPI floors and ceilings
            - Define success metrics""",
            expected_output="Objective function configuration",
            agent_id="objective_router",
            context_tasks=["intake_scenario"],
        )
        
        self.tasks["build_data_context"] = TaskDefinition(
            task_id="build_data_context",
            description="""Prepare data context:
            - Filter to scenario scope
            - Aggregate to optimization grain
            - Compute baseline metrics
            - Identify data gaps""",
            expected_output="Data context for optimization",
            agent_id="data_context_builder",
            context_tasks=["intake_scenario"],
        )
        
        self.tasks["model_response_curves"] = TaskDefinition(
            task_id="model_response_curves",
            description="""Estimate response curves:
            - Fit saturation curves to history
            - Estimate marginal returns
            - Quantify uncertainty bands
            - Flag low-confidence estimates""",
            expected_output="Response curve estimates",
            agent_id="response_curve_modeler",
            context_tasks=["build_data_context"],
        )
        
        self.tasks["build_constraints"] = TaskDefinition(
            task_id="build_constraints",
            description="""Encode constraints:
            - Budget ceiling or floor
            - Entity-level floors and ceilings
            - Pacing requirements
            - Custom business rules""",
            expected_output="Encoded constraint set",
            agent_id="constraint_builder",
            context_tasks=["route_objective"],
        )
        
        self.tasks["solve_optimization"] = TaskDefinition(
            task_id="solve_optimization",
            description="""Solve for optimal allocation:
            - Run optimizer with objective and constraints
            - Report optimal allocation
            - Compute shadow prices
            - Identify binding constraints""",
            expected_output="Optimization solution",
            agent_id="optimization_solver",
            context_tasks=["model_response_curves", "build_constraints"],
        )
        
        self.tasks["analyze_sensitivity"] = TaskDefinition(
            task_id="analyze_sensitivity",
            description="""Analyze solution robustness:
            - Sensitivity to input assumptions
            - Stress test key parameters
            - Monte Carlo on uncertain inputs
            - Flag fragile recommendations""",
            expected_output="Sensitivity analysis",
            agent_id="sensitivity_robustness_analyst",
            context_tasks=["solve_optimization"],
        )
        
        self.tasks["compare_scenarios"] = TaskDefinition(
            task_id="compare_scenarios",
            description="""Compare baseline and optimized:
            - Compute deltas for all KPIs
            - Generate comparison tables
            - Identify key tradeoffs
            - Rank scenarios if multiple""",
            expected_output="Scenario comparison",
            agent_id="scenario_comparator",
            context_tasks=["analyze_sensitivity"],
        )
        
        self.tasks["package_output"] = TaskDefinition(
            task_id="package_output",
            description="""Create final output:
            - Executive summary
            - Scenario plan with allocation
            - Comparison tables
            - Governance pack
            - QA validation""",
            expected_output="Complete scenario output",
            agent_id="narrator_qa",
            context_tasks=["compare_scenarios"],
        )
    
    def invoke_sub_crew(
        self,
        crew_type: str,
        config: CrewConfig,
        performance_data: Dict[str, Any]
    ) -> CrewOutput:
        """Invoke a sub-crew for detailed analysis."""
        from .brand_crew import BrandOptimizationCrew
        from .rmn_crew import RMNOptimizationCrew
        from .campaign_crew import CampaignMessageOptimizationCrew
        from .channel_crew import ChannelOptimizationCrew
        
        crew_classes = {
            "brand": BrandOptimizationCrew,
            "rmn": RMNOptimizationCrew,
            "campaign": CampaignMessageOptimizationCrew,
            "channel": ChannelOptimizationCrew,
        }
        
        crew_class = crew_classes.get(crew_type)
        if not crew_class:
            raise ValueError(f"Unknown crew type: {crew_type}")
        
        crew = crew_class(config, performance_data)
        return crew.run()
    
    def ingest_and_validate(self) -> Dict[str, Any]:
        """Validate scenario inputs."""
        issues = []
        
        # Check scenario config
        if not self.scenario_config.scenario_name:
            self.scenario_config.scenario_name = f"Scenario_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        # Check performance data
        if not self.performance_data:
            issues.append("No performance data provided")
        
        # Check constraints
        if self.config.constraints.budget <= 0:
            # Try to infer from data
            total_spend = 0
            for key in ["spend_by_rmn", "spend_by_channel", "total_spend"]:
                if key in self.performance_data:
                    data = self.performance_data[key]
                    if isinstance(data, dict):
                        total_spend = sum(data.values())
                    else:
                        total_spend = data
                    break
            
            if total_spend > 0:
                self.config.constraints.budget = total_spend
            else:
                issues.append("No budget specified and cannot infer from data")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "scenario_name": self.scenario_config.scenario_name,
            "desired_outcome": self.config.desired_outcome.value,
            "budget": self.config.constraints.budget,
            "validated_at": datetime.utcnow().isoformat(),
        }
    
    def diagnose(self) -> Dict[str, Any]:
        """Build data context and estimate response curves."""
        diagnosis = {
            "baseline": {},
            "response_curves": {},
            "opportunities": [],
            "risks": [],
        }
        
        # Aggregate baseline metrics
        spend_data = self.performance_data.get("spend_by_rmn", {})
        sales_data = self.performance_data.get("incremental_sales_by_rmn", {})
        
        total_spend = sum(spend_data.values())
        total_sales = sum(sales_data.values())
        
        diagnosis["baseline"]["total_spend"] = total_spend
        diagnosis["baseline"]["total_incremental_sales"] = total_sales
        diagnosis["baseline"]["overall_efficiency"] = total_sales / total_spend if total_spend > 0 else 0
        
        # Entity-level baseline
        diagnosis["baseline"]["by_entity"] = {}
        for entity_id in spend_data:
            spend = spend_data.get(entity_id, 0)
            sales = sales_data.get(entity_id, 0)
            efficiency = sales / spend if spend > 0 else 0
            
            diagnosis["baseline"]["by_entity"][entity_id] = {
                "spend": spend,
                "incremental_sales": sales,
                "efficiency": efficiency,
            }
            
            # Estimate response curve
            elasticity = self.performance_data.get("elasticity", {}).get(entity_id, 0.15)
            saturation_point = spend * 2  # Assume we're at 50% saturation
            
            diagnosis["response_curves"][entity_id] = {
                "elasticity": elasticity,
                "saturation_point": saturation_point,
                "marginal_return": efficiency * (1 - spend / saturation_point),
            }
        
        return diagnosis
    
    def optimize(self, diagnosis: Dict[str, Any]) -> OptimizationResult:
        """Run optimization based on desired outcome."""
        obj_params = self.get_objective_function_params()
        constraints = self.config.constraints
        
        baseline = diagnosis["baseline"]["by_entity"]
        curves = diagnosis["response_curves"]
        
        if not baseline:
            return OptimizationResult(
                success=False,
                solver_message="No baseline data"
            )
        
        # Determine budget based on objective
        if obj_params["direction"] == "maximize":
            total_budget = constraints.budget
        else:  # minimize spend
            total_budget = constraints.budget * 0.9  # Target 10% reduction
        
        # Optimize using marginal returns
        marginal_returns = {e: curves[e]["marginal_return"] for e in baseline}
        mr_sum = sum(marginal_returns.values()) or 1
        
        optimized_allocation = {}
        for entity_id in baseline:
            raw_allocation = total_budget * (marginal_returns[entity_id] / mr_sum)
            
            min_spend = constraints.rmn_floors.get(entity_id, constraints.min_channel_spend)
            max_spend = constraints.rmn_ceilings.get(entity_id, total_budget * 0.5)
            
            optimized_allocation[entity_id] = np.clip(raw_allocation, min_spend, max_spend)
        
        # Normalize
        alloc_total = sum(optimized_allocation.values())
        if alloc_total > 0:
            scale = total_budget / alloc_total
            optimized_allocation = {k: v * scale for k, v in optimized_allocation.items()}
        
        # Calculate expected outcome
        expected_sales = sum(
            optimized_allocation[e] * baseline[e]["efficiency"] * 
            (1 - optimized_allocation[e] / curves[e]["saturation_point"] * 0.5)
            for e in optimized_allocation
        )
        
        return OptimizationResult(
            success=True,
            objective_value=expected_sales,
            allocation=optimized_allocation,
            iterations=1,
            convergence_achieved=True,
            solver_status="optimal",
        )
    
    def explain(
        self,
        diagnosis: Dict[str, Any],
        optimization_result: OptimizationResult
    ) -> CrewOutput:
        """Generate scenario comparison and narrative."""
        baseline = diagnosis["baseline"]
        entity_baseline = baseline["by_entity"]
        
        # Build allocations
        allocations = []
        for entity_id, recommended in optimization_result.allocation.items():
            current = entity_baseline.get(entity_id, {})
            current_spend = current.get("spend", 0)
            delta = recommended - current_spend
            delta_pct = delta / current_spend if current_spend > 0 else 0
            efficiency = current.get("efficiency", 0)
            
            allocations.append(AllocationRecommendation(
                entity_type="rmn",
                entity_id=entity_id,
                entity_name=entity_id,
                current_spend=current_spend,
                recommended_spend=recommended,
                spend_delta=delta,
                spend_delta_pct=delta_pct,
                expected_incremental_sales=recommended * efficiency,
                expected_efficiency=efficiency,
                rationale=f"{'Increase' if delta > 0 else 'Decrease'} to optimize for {self.config.desired_outcome.value}",
            ))
        
        # Impact estimates
        current_sales = baseline["total_incremental_sales"]
        projected_sales = optimization_result.objective_value
        current_spend = baseline["total_spend"]
        projected_spend = sum(optimization_result.allocation.values())
        
        impact_estimates = [
            ImpactEstimate(
                metric_name="Incremental Sales",
                baseline_value=current_sales,
                projected_value=projected_sales,
                delta=projected_sales - current_sales,
                delta_pct=(projected_sales - current_sales) / current_sales if current_sales > 0 else 0,
                ci_lower=projected_sales * 0.85,
                ci_upper=projected_sales * 1.15,
                confidence=0.75,
            ),
            ImpactEstimate(
                metric_name="Total Spend",
                baseline_value=current_spend,
                projected_value=projected_spend,
                delta=projected_spend - current_spend,
                delta_pct=(projected_spend - current_spend) / current_spend if current_spend > 0 else 0,
                confidence=0.95,
            ),
            ImpactEstimate(
                metric_name="Efficiency (iROAS)",
                baseline_value=current_sales / current_spend if current_spend > 0 else 0,
                projected_value=projected_sales / projected_spend if projected_spend > 0 else 0,
                delta=(projected_sales / projected_spend) - (current_sales / current_spend) if current_spend > 0 and projected_spend > 0 else 0,
                confidence=0.70,
            ),
        ]
        
        outcome_text = self.config.desired_outcome.value.replace("_", " ").title()
        
        return CrewOutput(
            executive_summary=f"""Scenario: {self.scenario_config.scenario_name} - {outcome_text}

Optimized allocation of ${projected_spend:,.0f} across {len(allocations)} entities 
to achieve ${projected_sales:,.0f} in incremental sales.

Key changes:
- Spend delta: ${projected_spend - current_spend:+,.0f} ({(projected_spend - current_spend) / current_spend * 100 if current_spend > 0 else 0:+.1f}%)
- Sales delta: ${projected_sales - current_sales:+,.0f} ({(projected_sales - current_sales) / current_sales * 100 if current_sales > 0 else 0:+.1f}%)
- Efficiency: {projected_sales / projected_spend:.2f} vs {current_sales / current_spend:.2f} baseline""",
            key_findings=[
                f"Objective: {outcome_text}",
                f"Baseline efficiency: {baseline['overall_efficiency']:.2f} iROAS",
                f"Projected efficiency: {projected_sales / projected_spend:.2f} iROAS" if projected_spend > 0 else "",
            ],
            opportunities=[],
            risks=[],
            allocations=allocations,
            total_recommended_spend=projected_spend,
            impact_estimates=impact_estimates,
            expected_incremental_sales=projected_sales,
            expected_efficiency=projected_sales / projected_spend if projected_spend > 0 else 0,
        )


class IncreaseRevenueCrew(ScenarioOrchestratorCrew):
    """
    Increase Revenue Crew - Maximize incremental dollar sales.
    
    Primary objective: Maximize incremental sales
    Constraints: Spend ≤ budget; optional RMN/channel floors/ceilings
    KPIs: Incremental sales, iROAS, scale headroom, saturation signals
    """
    
    def __init__(
        self,
        config: CrewConfig,
        performance_data: Optional[Dict[str, Any]] = None,
    ):
        config.desired_outcome = DesiredOutcome.INCREASE_REVENUE
        scenario_config = ScenarioConfig(
            scenario_name="Increase Revenue",
            desired_outcome=DesiredOutcome.INCREASE_REVENUE,
        )
        super().__init__(config, scenario_config, performance_data)
    
    @property
    def crew_type(self) -> str:
        return "increase_revenue"


class IncreaseMarginCrew(ScenarioOrchestratorCrew):
    """
    Increase Margin Crew - Maximize incremental gross profit.
    
    Primary objective: Maximize incremental_sales × gross_margin_rate
    Constraints: Spend ≤ budget; optional mix shift constraints
    KPIs: Incremental profit, profit per $ spend, contribution margin
    """
    
    def __init__(
        self,
        config: CrewConfig,
        performance_data: Optional[Dict[str, Any]] = None,
    ):
        config.desired_outcome = DesiredOutcome.INCREASE_MARGIN
        scenario_config = ScenarioConfig(
            scenario_name="Increase Margin",
            desired_outcome=DesiredOutcome.INCREASE_MARGIN,
        )
        super().__init__(config, scenario_config, performance_data)
    
    @property
    def crew_type(self) -> str:
        return "increase_margin"


class MaintainRevenueCrew(ScenarioOrchestratorCrew):
    """
    Maintain Revenue Crew - Minimize spend while maintaining revenue floor.
    
    Primary objective: Minimize spend subject to revenue floor
    Constraints: Incremental sales ≥ target; maintain presence guardrails
    KPIs: Spend savings, efficiency, risk/fragility, forecast error
    """
    
    def __init__(
        self,
        config: CrewConfig,
        performance_data: Optional[Dict[str, Any]] = None,
    ):
        config.desired_outcome = DesiredOutcome.MAINTAIN_REVENUE
        scenario_config = ScenarioConfig(
            scenario_name="Maintain Revenue",
            desired_outcome=DesiredOutcome.MAINTAIN_REVENUE,
        )
        super().__init__(config, scenario_config, performance_data)
    
    @property
    def crew_type(self) -> str:
        return "maintain_revenue"


class ReduceCostCrew(ScenarioOrchestratorCrew):
    """
    Reduce Cost Crew - Minimize spend while protecting priority KPIs.
    
    Primary objective: Minimize spend while protecting revenue floor
    Constraints: Revenue ≥ floor; brand equity constraints; test carveouts
    KPIs: Cost savings, efficiency, coverage proxies, downside risk
    """
    
    def __init__(
        self,
        config: CrewConfig,
        performance_data: Optional[Dict[str, Any]] = None,
    ):
        config.desired_outcome = DesiredOutcome.REDUCE_COST
        scenario_config = ScenarioConfig(
            scenario_name="Reduce Cost",
            desired_outcome=DesiredOutcome.REDUCE_COST,
        )
        super().__init__(config, scenario_config, performance_data)
    
    @property
    def crew_type(self) -> str:
        return "reduce_cost"
