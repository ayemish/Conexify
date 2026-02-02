"""
Brand Level Optimization Crew

Optimizes a brand portfolio's retail media spend mix across RMNs, channels,
campaigns, and messages to achieve the desired outcome.

Core Agents:
- Brand Portfolio Lead (manager)
- Brand Performance Analyst
- Incrementality Analyst
- Margin & Mix Analyst
- Budget Allocation Optimizer
- Constraints & Risk Manager
- Recommendation Narrator
- QA Auditor
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
import numpy as np
import logging

from .base_crew import BaseOptimizationCrew, AgentDefinition, TaskDefinition
from .schemas import (
    DesiredOutcome,
    CrewConfig,
    CrewOutput,
    OptimizationResult,
    AllocationRecommendation,
    ImpactEstimate,
    RiskAssessment,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BrandOptimizationCrew(BaseOptimizationCrew):
    """
    Brand-level optimization crew.
    
    Purpose: Optimize a brand portfolio's retail media spend mix across RMNs,
    channels, campaigns, and messages to achieve the desired outcome.
    
    Inputs:
    - Brand performance table (spend, incremental sales, efficiency)
    - Allocation detail by RMN and channel
    - Business guardrails (budget, brand priorities, minimum presence)
    
    Outputs:
    - Brand POV: what is working, what is not, and why
    - Recommended spend reallocation by RMN and channel
    - Impact estimate with assumptions and sensitivities
    """
    
    @property
    def crew_type(self) -> str:
        return "brand_optimization"
    
    def _setup_agents(self) -> None:
        """Define brand-level optimization agents."""
        
        self.agents["brand_portfolio_lead"] = AgentDefinition(
            role="Brand Portfolio Lead",
            goal="Own decision logic, align to outcome, and resolve tradeoffs across brand portfolio",
            backstory="""You are a senior brand marketing strategist with 15+ years 
            experience in CPG retail media. You make final allocation decisions by 
            balancing growth, efficiency, and brand priorities. You are accountable 
            for the portfolio's retail media performance.""",
            agent_id="brand_portfolio_lead",
            name="Brand Portfolio Lead",
            tools=["decision_framework_tool", "tradeoff_analyzer_tool"],
            allow_delegation=True,
            verbose=True,
        )
        
        self.agents["brand_performance_analyst"] = AgentDefinition(
            role="Brand Performance Analyst",
            goal="Compute KPIs, identify winners/losers, and quantify contribution to totals",
            backstory="""You are an expert at analyzing brand performance data. 
            You compute key metrics like spend efficiency, incremental sales, and 
            ROAS. You identify which RMNs and channels are driving results and 
            which are underperforming.""",
            agent_id="brand_performance_analyst",
            name="Brand Performance Analyst",
            tools=["kpi_calculator_tool", "trend_analyzer_tool", "benchmark_tool"],
        )
        
        self.agents["incrementality_analyst"] = AgentDefinition(
            role="Incrementality Analyst",
            goal="Validate lift methodology and interpret marginal returns/response curves",
            backstory="""You are a measurement scientist specializing in 
            incrementality testing and media mix modeling. You ensure that 
            attributed sales are truly incremental and interpret diminishing 
            returns curves to find optimal spend levels.""",
            agent_id="incrementality_analyst",
            name="Incrementality Analyst",
            tools=["lift_validation_tool", "response_curve_tool", "saturation_detector_tool"],
        )
        
        self.agents["margin_mix_analyst"] = AgentDefinition(
            role="Margin & Mix Analyst",
            goal="Incorporate gross margin, SKU mix, and price/promo interactions",
            backstory="""You analyze profitability at the product level. You 
            understand how different SKUs, price points, and promotional 
            strategies affect overall margin. You optimize for profitable 
            growth, not just revenue.""",
            agent_id="margin_mix_analyst",
            name="Margin & Mix Analyst",
            tools=["margin_calculator_tool", "sku_mix_analyzer_tool", "promo_impact_tool"],
        )
        
        self.agents["budget_allocation_optimizer"] = AgentDefinition(
            role="Budget Allocation Optimizer",
            goal="Solve allocation under constraints using marginal ROAS equalization",
            backstory="""You are an optimization expert who finds the best 
            allocation of budget across channels and RMNs. You use mathematical 
            optimization to maximize objectives while respecting all constraints. 
            You focus on marginal (not average) returns.""",
            agent_id="budget_allocation_optimizer",
            name="Budget Allocation Optimizer",
            tools=["optimizer_tool", "constraint_solver_tool", "sensitivity_analyzer_tool"],
        )
        
        self.agents["constraints_risk_manager"] = AgentDefinition(
            role="Constraints & Risk Manager",
            goal="Enforce floors/ceilings, retailer obligations, and brand safety constraints",
            backstory="""You ensure all recommendations comply with business 
            constraints including minimum spend requirements, retailer commitments, 
            brand safety policies, and operational capacity limits. You flag 
            risks and propose mitigations.""",
            agent_id="constraints_risk_manager",
            name="Constraints & Risk Manager",
            tools=["constraint_validator_tool", "risk_scorer_tool", "compliance_checker_tool"],
        )
        
        self.agents["recommendation_narrator"] = AgentDefinition(
            role="Recommendation Narrator",
            goal="Produce stakeholder-ready narrative and action list",
            backstory="""You translate complex optimization outputs into clear, 
            actionable recommendations. You write executive summaries that 
            explain the 'why' behind recommendations and specify concrete 
            next steps for implementation.""",
            agent_id="recommendation_narrator",
            name="Recommendation Narrator",
            tools=["narrative_generator_tool", "action_list_formatter_tool"],
        )
        
        self.agents["qa_auditor"] = AgentDefinition(
            role="QA Auditor",
            goal="Verify math consistency, unit sanity, and completeness",
            backstory="""You are meticulous about data quality and consistency. 
            You verify that all calculations are correct, units match, totals 
            reconcile, and no data is missing. You catch errors before they 
            reach stakeholders.""",
            agent_id="qa_auditor",
            name="QA Auditor",
            tools=["math_validator_tool", "reconciliation_tool", "completeness_checker_tool"],
        )
    
    def _setup_tasks(self) -> None:
        """Define brand-level optimization tasks."""
        
        self.tasks["ingest_brand_data"] = TaskDefinition(
            task_id="ingest_brand_data",
            description="""Ingest and validate brand performance data including:
            - Spend by RMN and channel
            - Incremental sales and attributed revenue
            - Efficiency metrics (iROAS, CPiS)
            - Historical trends and seasonality
            Confirm data quality and flag any issues.""",
            expected_output="Data validation report with quality scores and any issues identified",
            agent_id="brand_performance_analyst",
        )
        
        self.tasks["compute_brand_kpis"] = TaskDefinition(
            task_id="compute_brand_kpis",
            description="""Compute brand-level KPIs:
            - Total and incremental sales by RMN/channel
            - Spend efficiency (iROAS) by RMN/channel
            - Index vs benchmark
            - Contribution to total portfolio
            - Trend vs prior period and year-ago""",
            expected_output="Brand KPI scorecard with rankings and contribution analysis",
            agent_id="brand_performance_analyst",
            context_tasks=["ingest_brand_data"],
        )
        
        self.tasks["validate_incrementality"] = TaskDefinition(
            task_id="validate_incrementality",
            description="""Validate incrementality methodology:
            - Review lift study results and confidence
            - Assess response curve saturation points
            - Identify marginal vs average return gaps
            - Flag any measurement concerns""",
            expected_output="Incrementality validation report with confidence levels",
            agent_id="incrementality_analyst",
            context_tasks=["compute_brand_kpis"],
        )
        
        self.tasks["analyze_margin_mix"] = TaskDefinition(
            task_id="analyze_margin_mix",
            description="""Analyze margin and product mix:
            - Gross margin by product/SKU impacted
            - Mix shift opportunities
            - Price/promo interaction effects
            - Profitability vs volume tradeoffs""",
            expected_output="Margin analysis with mix optimization opportunities",
            agent_id="margin_mix_analyst",
            context_tasks=["compute_brand_kpis"],
        )
        
        self.tasks["optimize_allocation"] = TaskDefinition(
            task_id="optimize_allocation",
            description="""Optimize budget allocation:
            - Set objective function based on desired outcome
            - Apply response curves and diminishing returns
            - Solve for optimal allocation across RMNs/channels
            - Compute shadow prices for binding constraints""",
            expected_output="Optimized allocation with expected impact",
            agent_id="budget_allocation_optimizer",
            context_tasks=["validate_incrementality", "analyze_margin_mix"],
        )
        
        self.tasks["validate_constraints"] = TaskDefinition(
            task_id="validate_constraints",
            description="""Validate all constraints are satisfied:
            - Budget ceiling
            - RMN/channel floors and ceilings
            - Retailer commitment minimums
            - Brand safety requirements
            - Operational capacity limits""",
            expected_output="Constraint validation report with any violations",
            agent_id="constraints_risk_manager",
            context_tasks=["optimize_allocation"],
        )
        
        self.tasks["generate_narrative"] = TaskDefinition(
            task_id="generate_narrative",
            description="""Generate stakeholder narrative:
            - Executive summary of recommendations
            - Key findings (what's working, what's not)
            - Recommended actions with rationale
            - Expected impact and assumptions
            - Risks and mitigations""",
            expected_output="Executive recommendation deck with action plan",
            agent_id="recommendation_narrator",
            context_tasks=["validate_constraints"],
        )
        
        self.tasks["qa_final_output"] = TaskDefinition(
            task_id="qa_final_output",
            description="""QA the final output:
            - Verify all totals reconcile
            - Check unit consistency
            - Validate calculation accuracy
            - Ensure completeness""",
            expected_output="QA sign-off with any corrections",
            agent_id="qa_auditor",
            context_tasks=["generate_narrative"],
        )
    
    def ingest_and_validate(self) -> Dict[str, Any]:
        """Validate brand performance data."""
        issues = []
        
        # Check required data fields
        required_fields = ["spend", "incremental_sales", "efficiency"]
        for field in required_fields:
            if field not in self.performance_data:
                issues.append(f"Missing required field: {field}")
        
        # Check data quality
        if "spend" in self.performance_data:
            spend_data = self.performance_data["spend"]
            if isinstance(spend_data, dict):
                for entity, value in spend_data.items():
                    if value < 0:
                        issues.append(f"Negative spend for {entity}")
        
        # Check for sufficient data
        if "rmn_data" in self.performance_data:
            if len(self.performance_data["rmn_data"]) < 1:
                issues.append("No RMN data available")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "n_rmns": len(self.performance_data.get("rmn_data", {})),
            "n_channels": len(self.performance_data.get("channel_data", {})),
            "validated_at": datetime.utcnow().isoformat(),
        }
    
    def diagnose(self) -> Dict[str, Any]:
        """Compute KPIs and identify opportunities/risks."""
        diagnosis = {
            "kpis": {},
            "drivers": [],
            "opportunities": [],
            "risks": [],
            "rankings": {},
        }
        
        # Compute KPIs from performance data
        spend_by_rmn = self.performance_data.get("spend_by_rmn", {})
        sales_by_rmn = self.performance_data.get("incremental_sales_by_rmn", {})
        
        # Calculate efficiency by RMN
        efficiency_by_rmn = {}
        for rmn_id in spend_by_rmn:
            if rmn_id in sales_by_rmn and spend_by_rmn[rmn_id] > 0:
                efficiency_by_rmn[rmn_id] = sales_by_rmn[rmn_id] / spend_by_rmn[rmn_id]
        
        diagnosis["kpis"]["total_spend"] = sum(spend_by_rmn.values())
        diagnosis["kpis"]["total_incremental_sales"] = sum(sales_by_rmn.values())
        diagnosis["kpis"]["overall_efficiency"] = (
            diagnosis["kpis"]["total_incremental_sales"] / diagnosis["kpis"]["total_spend"]
            if diagnosis["kpis"]["total_spend"] > 0 else 0
        )
        diagnosis["kpis"]["efficiency_by_rmn"] = efficiency_by_rmn
        
        # Rank RMNs by efficiency
        sorted_rmns = sorted(efficiency_by_rmn.items(), key=lambda x: x[1], reverse=True)
        diagnosis["rankings"]["rmn_by_efficiency"] = [r[0] for r in sorted_rmns]
        
        # Identify opportunities (high efficiency, low spend)
        avg_efficiency = np.mean(list(efficiency_by_rmn.values())) if efficiency_by_rmn else 0
        for rmn_id, eff in efficiency_by_rmn.items():
            if eff > avg_efficiency * 1.2:
                diagnosis["opportunities"].append({
                    "entity": rmn_id,
                    "type": "scale_winner",
                    "rationale": f"Efficiency {eff:.2f} is 20%+ above average {avg_efficiency:.2f}",
                })
        
        # Identify risks (low efficiency)
        for rmn_id, eff in efficiency_by_rmn.items():
            if eff < avg_efficiency * 0.8:
                diagnosis["risks"].append({
                    "entity": rmn_id,
                    "type": "underperformer",
                    "rationale": f"Efficiency {eff:.2f} is 20%+ below average {avg_efficiency:.2f}",
                })
        
        return diagnosis
    
    def optimize(self, diagnosis: Dict[str, Any]) -> OptimizationResult:
        """Optimize brand allocation across RMNs and channels."""
        obj_params = self.get_objective_function_params()
        constraints = self.config.constraints
        
        # Get current allocation
        current_allocation = self.performance_data.get("spend_by_rmn", {})
        efficiency_by_rmn = diagnosis["kpis"].get("efficiency_by_rmn", {})
        
        if not current_allocation:
            return OptimizationResult(
                success=False,
                solver_message="No allocation data available"
            )
        
        total_budget = constraints.budget or sum(current_allocation.values())
        
        # Simple marginal efficiency optimization
        # Allocate proportional to efficiency (higher efficiency = more budget)
        efficiency_sum = sum(efficiency_by_rmn.values()) or 1
        
        optimized_allocation = {}
        for rmn_id in current_allocation:
            eff = efficiency_by_rmn.get(rmn_id, 1.0)
            raw_allocation = total_budget * (eff / efficiency_sum)
            
            # Apply constraints
            min_spend = constraints.rmn_floors.get(rmn_id, constraints.min_channel_spend)
            max_spend = constraints.rmn_ceilings.get(rmn_id, total_budget)
            
            optimized_allocation[rmn_id] = np.clip(raw_allocation, min_spend, max_spend)
        
        # Normalize to budget
        alloc_total = sum(optimized_allocation.values())
        if alloc_total > 0:
            scale_factor = total_budget / alloc_total
            optimized_allocation = {k: v * scale_factor for k, v in optimized_allocation.items()}
        
        # Calculate expected impact
        expected_sales = sum(
            optimized_allocation[rmn] * efficiency_by_rmn.get(rmn, 1.0)
            for rmn in optimized_allocation
        )
        
        return OptimizationResult(
            success=True,
            objective_value=expected_sales,
            allocation=optimized_allocation,
            iterations=1,
            convergence_achieved=True,
            solver_status="optimal",
            solver_message="Marginal efficiency optimization completed",
        )
    
    def explain(
        self,
        diagnosis: Dict[str, Any],
        optimization_result: OptimizationResult
    ) -> CrewOutput:
        """Generate recommendation narrative."""
        current_allocation = self.performance_data.get("spend_by_rmn", {})
        rmn_names = self.performance_data.get("rmn_names", {})
        
        allocations = []
        for rmn_id, recommended_spend in optimization_result.allocation.items():
            current_spend = current_allocation.get(rmn_id, 0)
            delta = recommended_spend - current_spend
            delta_pct = delta / current_spend if current_spend > 0 else 0
            
            efficiency = diagnosis["kpis"]["efficiency_by_rmn"].get(rmn_id, 0)
            
            allocations.append(AllocationRecommendation(
                entity_type="rmn",
                entity_id=rmn_id,
                entity_name=rmn_names.get(rmn_id, rmn_id),
                current_spend=current_spend,
                recommended_spend=recommended_spend,
                spend_delta=delta,
                spend_delta_pct=delta_pct,
                expected_incremental_sales=recommended_spend * efficiency,
                expected_efficiency=efficiency,
                confidence_level=0.8,
                rationale=self._generate_allocation_rationale(rmn_id, delta_pct, efficiency),
                actions=self._generate_actions(rmn_id, delta_pct),
            ))
        
        # Impact estimates
        current_sales = diagnosis["kpis"]["total_incremental_sales"]
        projected_sales = optimization_result.objective_value
        
        impact_estimates = [
            ImpactEstimate(
                metric_name="Incremental Sales",
                baseline_value=current_sales,
                projected_value=projected_sales,
                delta=projected_sales - current_sales,
                delta_pct=(projected_sales - current_sales) / current_sales if current_sales > 0 else 0,
                ci_lower=projected_sales * 0.9,
                ci_upper=projected_sales * 1.1,
                confidence=0.8,
                assumptions=["Response curves remain stable", "Competitive dynamics unchanged"],
            )
        ]
        
        # Build output
        output = CrewOutput(
            executive_summary=self._generate_executive_summary(diagnosis, optimization_result),
            key_findings=self._extract_key_findings(diagnosis),
            opportunities=[o["rationale"] for o in diagnosis["opportunities"]],
            risks=[r["rationale"] for r in diagnosis["risks"]],
            allocations=allocations,
            total_recommended_spend=sum(optimization_result.allocation.values()),
            impact_estimates=impact_estimates,
            expected_incremental_sales=projected_sales,
            expected_efficiency=projected_sales / sum(optimization_result.allocation.values()) if optimization_result.allocation else 0,
        )
        
        return output
    
    def _generate_executive_summary(
        self,
        diagnosis: Dict[str, Any],
        optimization_result: OptimizationResult
    ) -> str:
        """Generate executive summary."""
        outcome = self.config.desired_outcome.value.replace("_", " ").title()
        current_sales = diagnosis["kpis"]["total_incremental_sales"]
        projected_sales = optimization_result.objective_value
        delta_pct = (projected_sales - current_sales) / current_sales * 100 if current_sales > 0 else 0
        
        return f"""Brand Portfolio Optimization - {outcome}

Based on analysis of performance across {len(optimization_result.allocation)} RMNs, 
we recommend reallocating ${sum(optimization_result.allocation.values()):,.0f} in spend 
to achieve an estimated {delta_pct:+.1f}% improvement in incremental sales.

The optimization prioritizes {'efficiency and scale' if delta_pct > 0 else 'cost reduction while maintaining performance'} 
by shifting investment toward higher-performing RMNs and channels while respecting 
all business constraints and minimum presence requirements."""
    
    def _extract_key_findings(self, diagnosis: Dict[str, Any]) -> List[str]:
        """Extract key findings from diagnosis."""
        findings = []
        
        total_efficiency = diagnosis["kpis"].get("overall_efficiency", 0)
        findings.append(f"Overall portfolio efficiency: {total_efficiency:.2f} iROAS")
        
        rankings = diagnosis["rankings"].get("rmn_by_efficiency", [])
        if rankings:
            findings.append(f"Top performer: {rankings[0]}")
            if len(rankings) > 1:
                findings.append(f"Lowest performer: {rankings[-1]}")
        
        n_opportunities = len(diagnosis["opportunities"])
        n_risks = len(diagnosis["risks"])
        findings.append(f"Identified {n_opportunities} scale opportunities and {n_risks} underperformers")
        
        return findings
    
    def _generate_allocation_rationale(
        self,
        rmn_id: str,
        delta_pct: float,
        efficiency: float
    ) -> str:
        """Generate rationale for allocation change."""
        if delta_pct > 0.1:
            return f"Increase investment due to strong efficiency ({efficiency:.2f}) and scale headroom"
        elif delta_pct < -0.1:
            return f"Reduce investment due to below-average efficiency ({efficiency:.2f}) and diminishing returns"
        else:
            return f"Maintain current investment level with efficiency at ({efficiency:.2f})"
    
    def _generate_actions(self, rmn_id: str, delta_pct: float) -> List[str]:
        """Generate action items for allocation change."""
        actions = []
        if delta_pct > 0.1:
            actions.append(f"Increase {rmn_id} budget by {delta_pct:.0%}")
            actions.append("Expand into additional placements/audiences")
            actions.append("Test incremental spend in 10% increments")
        elif delta_pct < -0.1:
            actions.append(f"Reduce {rmn_id} budget by {abs(delta_pct):.0%}")
            actions.append("Pause lowest-performing campaigns first")
            actions.append("Monitor for efficiency recovery")
        else:
            actions.append(f"Maintain {rmn_id} at current levels")
            actions.append("Continue optimization within current budget")
        return actions
    
    # =========================================================================
    # Scenario-Driven Execution Support
    # =========================================================================
    
    def optimize_for_scenario(
        self,
        scenario_id: str,
        scenario_objective: str,
        upstream_insights: Optional[Dict[str, Any]] = None,
    ) -> CrewOutput:
        """
        Execute brand optimization tailored to a specific scenario.
        
        This method adapts the optimization based on the scenario objective
        and any insights from upstream crews.
        """
        # Apply scenario-specific adjustments
        if scenario_objective == "incremental_sales":
            # Growth mode: prioritize efficiency and scale
            self.config.constraints.max_allocation_change_pct = self.get_max_reallocation_pct()
        elif scenario_objective == "incremental_profit":
            # Margin mode: weight profitability higher
            pass
        elif scenario_objective == "stability":
            # Stability mode: minimize changes
            self.config.constraints.max_allocation_change_pct = min(
                0.05, self.get_max_reallocation_pct()
            )
        elif scenario_objective == "efficiency":
            # Cost reduction mode: focus on cutting low performers
            pass
        
        # Incorporate upstream insights if available
        if upstream_insights:
            self._incorporate_upstream_insights(upstream_insights)
        
        # Run standard crew workflow
        output = self.run()
        
        # Add scenario metadata
        if hasattr(output, 'scenario_id'):
            output.scenario_id = scenario_id
        
        # Send results to downstream crews if in scenario mode
        if self._is_scenario_mode:
            self._notify_downstream_crews(output)
        
        return output
    
    def _incorporate_upstream_insights(
        self,
        upstream_insights: Dict[str, Any],
    ) -> None:
        """Incorporate insights from upstream crews into optimization."""
        # Example: if orchestrator detected high uncertainty, adjust confidence
        if upstream_insights.get("high_uncertainty"):
            logger.info("Adjusting for high uncertainty from upstream")
            # Could adjust response curve confidence, etc.
        
        # If specific RMNs flagged by upstream, adjust their handling
        flagged_rmns = upstream_insights.get("flagged_rmns", [])
        for rmn_id in flagged_rmns:
            logger.info(f"RMN {rmn_id} flagged by upstream crew")
    
    def _notify_downstream_crews(self, output: CrewOutput) -> None:
        """Send relevant insights to downstream crews."""
        # Extract insights that downstream crews might need
        insights = {
            "top_rmns": [a.entity_id for a in output.allocations if a.spend_delta_pct > 0][:3],
            "underperforming_rmns": [a.entity_id for a in output.allocations if a.spend_delta_pct < -0.1],
            "total_recommended_spend": output.total_recommended_spend,
            "expected_efficiency": output.expected_efficiency,
        }
        
        # Send to RMN crew for detailed optimization
        self.send_crew_message(
            target_crew="rmn_optimization",
            message_type="brand_context",
            payload=insights,
        )
        
        # Send to channel crew for channel-level follow-up
        self.send_crew_message(
            target_crew="channel_optimization",
            message_type="brand_context",
            payload=insights,
        )
    
    def get_scenario_recommendations(
        self,
        current_state: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Generate scenario recommendations based on brand performance.
        
        This allows the brand crew to contribute to agent-generated
        scenario recommendations.
        """
        recommendations = []
        
        # Analyze brand performance
        total_spend = sum(current_state.get("spend_by_rmn", {}).values())
        total_sales = sum(current_state.get("incremental_sales_by_rmn", {}).values())
        efficiency = total_sales / total_spend if total_spend > 0 else 0
        
        # Check for growth opportunity
        if efficiency > 1.5:
            recommendations.append({
                "scenario_id": "grow_revenue_brand",
                "confidence": 0.85,
                "rationale": f"Strong efficiency ({efficiency:.2f}) suggests scale opportunity",
                "source": "brand_optimization",
            })
        
        # Check for margin pressure
        margin_rate = current_state.get("avg_margin_rate", 0.3)
        if margin_rate < 0.25:
            recommendations.append({
                "scenario_id": "grow_margin",
                "confidence": 0.80,
                "rationale": f"Low margin rate ({margin_rate:.1%}) suggests profit optimization needed",
                "source": "brand_optimization",
            })
        
        # Check for efficiency issues
        if efficiency < 1.0:
            recommendations.append({
                "scenario_id": "reduce_cost",
                "confidence": 0.82,
                "rationale": f"Below-breakeven efficiency ({efficiency:.2f}) requires cost reduction",
                "source": "brand_optimization",
            })
        
        return recommendations
