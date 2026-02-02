"""
Retail Media Network (RMN) Level Optimization Crew

Optimizes performance within and across RMNs (retailers) and translates
recommendations into retailer-specific action plans.

Each RMN gets its own crew instance for retailer-specific optimization.

Core Agents:
- RMN Account Lead (manager)
- RMN Performance Analyst
- Auction Dynamics Specialist
- Incrementality Analyst
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


class RMNOptimizationCrew(BaseOptimizationCrew):
    """
    RMN-level optimization crew.
    
    Purpose: Optimize performance within and across RMNs and translate
    recommendations into retailer-specific action plans.
    
    Inputs:
    - RMN performance table (spend, incremental sales, efficiency, share of wallet)
    - Within-RMN breakdown by channel and placement
    - Retailer constraints (minimum spend, co-op rules, inventory)
    
    Outputs:
    - RMN POV: current efficiency, saturation signals, cross-RMN recommendations
    - Within-RMN action plan: channel mix, bidding/pacing, placement priorities
    - Risk memo: retailer constraints, measurement confidence, caveats
    """
    
    def __init__(
        self,
        config: CrewConfig,
        performance_data: Optional[Dict[str, Any]] = None,
        rmn_id: Optional[str] = None,
        rmn_name: Optional[str] = None,
    ):
        self.rmn_id = rmn_id or config.rmn_ids[0] if config.rmn_ids else "default"
        self.rmn_name = rmn_name or self.rmn_id
        super().__init__(config, performance_data)
    
    @property
    def crew_type(self) -> str:
        return f"rmn_optimization_{self.rmn_id}"
    
    def _setup_agents(self) -> None:
        """Define RMN-level optimization agents."""
        
        self.agents["rmn_account_lead"] = AgentDefinition(
            agent_id="rmn_account_lead",
            role="RMN Account Lead",
            name=f"{self.rmn_name} Account Lead",
            goal="Align recommendations with retailer realities and commercial terms",
            backstory=f"""You are the dedicated account lead for {self.rmn_name}. 
            You understand the retailer's unique media capabilities, audience segments, 
            commercial terms, and minimum spend requirements. You ensure recommendations 
            are implementable within the retailer's platform and constraints.""",
            tools=["retailer_playbook_tool", "commitment_tracker_tool"],
            allow_delegation=True,
            verbose=True,
        )
        
        self.agents["rmn_performance_analyst"] = AgentDefinition(
            agent_id="rmn_performance_analyst",
            role="RMN Performance Analyst",
            name=f"{self.rmn_name} Performance Analyst",
            goal="Compute network-level trends and decompose by brand/channel",
            backstory=f"""You are an expert at analyzing {self.rmn_name}'s 
            retail media performance. You track spend efficiency, incremental 
            sales, share of voice, and channel-level metrics. You identify 
            trends and isolate performance drivers.""",
            tools=["rmn_kpi_tool", "trend_analyzer_tool", "decomposition_tool"],
        )
        
        self.agents["auction_dynamics_specialist"] = AgentDefinition(
            agent_id="auction_dynamics_specialist",
            role="Auction Dynamics Specialist",
            name="Auction Dynamics Specialist",
            goal="Interpret CPC/CPM dynamics, competition, and share-of-voice signals",
            backstory="""You understand the auction mechanics of retail media 
            platforms. You analyze bid landscapes, competitive intensity, and 
            share of voice trends. You identify opportunities to win more 
            efficiently or scale with acceptable cost increases.""",
            tools=["auction_analyzer_tool", "bid_landscape_tool", "sov_tracker_tool"],
        )
        
        self.agents["incrementality_analyst"] = AgentDefinition(
            agent_id="incrementality_analyst",
            role="Incrementality Analyst",
            name="Incrementality Analyst",
            goal="Validate that lift and incrementality are comparable across RMNs",
            backstory="""You ensure measurement methodology is consistent and 
            reliable across retailers. You compare lift study results, identify 
            methodology differences, and normalize for fair cross-RMN comparison. 
            You flag any measurement concerns.""",
            tools=["lift_validation_tool", "methodology_comparator_tool"],
        )
        
        self.agents["budget_allocation_optimizer"] = AgentDefinition(
            agent_id="budget_allocation_optimizer",
            role="Budget Allocation Optimizer",
            name="Budget Allocation Optimizer",
            goal="Allocate spend across RMNs and within RMN channels optimally",
            backstory="""You optimize budget allocation using marginal return 
            curves. You find the allocation that maximizes the objective while 
            respecting retailer commitments and channel constraints. You use 
            RMN-specific response curves when available.""",
            tools=["optimizer_tool", "response_curve_tool", "constraint_solver_tool"],
        )
        
        self.agents["constraints_risk_manager"] = AgentDefinition(
            agent_id="constraints_risk_manager",
            role="Constraints & Risk Manager",
            name="Constraints & Risk Manager",
            goal="Enforce retailer obligations and caps, flag compliance issues",
            backstory="""You track all retailer commitments including minimum 
            spend agreements, co-op funding rules, inventory constraints, and 
            platform policies. You ensure recommendations comply and flag any 
            risks or compliance gaps.""",
            tools=["commitment_validator_tool", "compliance_checker_tool", "risk_scorer_tool"],
        )
        
        self.agents["recommendation_narrator"] = AgentDefinition(
            agent_id="recommendation_narrator",
            role="Recommendation Narrator",
            name="Recommendation Narrator",
            goal="Package retailer-specific action plans and risk memos",
            backstory="""You create clear, actionable recommendations tailored 
            to each retailer's context. You write action plans that platform 
            teams can execute directly, with specific channel, audience, and 
            budget guidance.""",
            tools=["narrative_generator_tool", "playbook_formatter_tool"],
        )
        
        self.agents["qa_auditor"] = AgentDefinition(
            agent_id="qa_auditor",
            role="QA Auditor",
            name="QA Auditor",
            goal="Verify data accuracy, calculation correctness, and completeness",
            backstory="""You ensure all RMN-level analysis is accurate and 
            complete. You verify that retailer-specific metrics match source 
            data, calculations are correct, and all required outputs are present.""",
            tools=["data_validator_tool", "math_checker_tool"],
        )
    
    def _setup_tasks(self) -> None:
        """Define RMN-level optimization tasks."""
        
        self.tasks["ingest_rmn_data"] = TaskDefinition(
            task_id="ingest_rmn_data",
            description=f"""Ingest and validate {self.rmn_name} performance data:
            - Spend by channel and placement
            - Incremental sales and attributed revenue
            - Share of voice and competitive metrics
            - Auction dynamics (CPCs, CPMs, win rates)
            Confirm data quality and retailer-specific adjustments.""",
            expected_output="RMN data validation report with quality scores",
            agent_id="rmn_performance_analyst",
        )
        
        self.tasks["analyze_channel_performance"] = TaskDefinition(
            task_id="analyze_channel_performance",
            description=f"""Analyze {self.rmn_name} channel performance:
            - Search, Display, Video, Email channel KPIs
            - Efficiency and scale by channel
            - Saturation signals and headroom
            - Channel-specific trends""",
            expected_output="Channel performance scorecard with rankings",
            agent_id="rmn_performance_analyst",
            context_tasks=["ingest_rmn_data"],
        )
        
        self.tasks["analyze_auction_dynamics"] = TaskDefinition(
            task_id="analyze_auction_dynamics",
            description=f"""Analyze {self.rmn_name} auction dynamics:
            - CPC/CPM trends and cost inflation
            - Competitive intensity by category
            - Share of voice trends
            - Bid efficiency opportunities""",
            expected_output="Auction dynamics report with bidding recommendations",
            agent_id="auction_dynamics_specialist",
            context_tasks=["ingest_rmn_data"],
        )
        
        self.tasks["validate_incrementality"] = TaskDefinition(
            task_id="validate_incrementality",
            description=f"""Validate {self.rmn_name} incrementality:
            - Review lift study methodology
            - Assess confidence and sample size
            - Compare to other RMN methodologies
            - Flag measurement concerns""",
            expected_output="Incrementality validation with confidence levels",
            agent_id="incrementality_analyst",
            context_tasks=["analyze_channel_performance"],
        )
        
        self.tasks["optimize_within_rmn"] = TaskDefinition(
            task_id="optimize_within_rmn",
            description=f"""Optimize allocation within {self.rmn_name}:
            - Set objective based on desired outcome
            - Apply channel-specific response curves
            - Solve for optimal channel mix
            - Recommend bidding/pacing posture""",
            expected_output="Optimized within-RMN allocation",
            agent_id="budget_allocation_optimizer",
            context_tasks=["validate_incrementality", "analyze_auction_dynamics"],
        )
        
        self.tasks["validate_retailer_constraints"] = TaskDefinition(
            task_id="validate_retailer_constraints",
            description=f"""Validate {self.rmn_name} constraints:
            - Minimum spend commitments
            - Co-op funding rules
            - Inventory/availability constraints
            - Platform policy compliance""",
            expected_output="Constraint validation with compliance status",
            agent_id="constraints_risk_manager",
            context_tasks=["optimize_within_rmn"],
        )
        
        self.tasks["generate_rmn_playbook"] = TaskDefinition(
            task_id="generate_rmn_playbook",
            description=f"""Generate {self.rmn_name} action playbook:
            - Channel mix recommendations
            - Bidding and pacing guidance
            - Placement priorities
            - Test and learn opportunities
            - Risk mitigations""",
            expected_output="Retailer-specific action playbook",
            agent_id="recommendation_narrator",
            context_tasks=["validate_retailer_constraints"],
        )
        
        self.tasks["qa_rmn_output"] = TaskDefinition(
            task_id="qa_rmn_output",
            description="""QA the RMN output:
            - Verify data accuracy
            - Check calculation correctness
            - Validate constraint compliance
            - Ensure completeness""",
            expected_output="QA sign-off",
            agent_id="qa_auditor",
            context_tasks=["generate_rmn_playbook"],
        )
    
    def ingest_and_validate(self) -> Dict[str, Any]:
        """Validate RMN performance data."""
        issues = []
        
        # Check for RMN-specific data
        rmn_data = self.performance_data.get("rmn_data", {}).get(self.rmn_id, {})
        
        if not rmn_data:
            issues.append(f"No data available for RMN: {self.rmn_id}")
        
        # Check required channel data
        channel_data = rmn_data.get("channel_data", {})
        if len(channel_data) < 1:
            issues.append("No channel data available")
        
        # Check for spend data
        if "total_spend" not in rmn_data and "spend" not in rmn_data:
            issues.append("Missing spend data")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "rmn_id": self.rmn_id,
            "rmn_name": self.rmn_name,
            "n_channels": len(channel_data),
            "validated_at": datetime.utcnow().isoformat(),
        }
    
    def diagnose(self) -> Dict[str, Any]:
        """Compute KPIs and identify opportunities/risks for this RMN."""
        diagnosis = {
            "kpis": {},
            "channel_performance": {},
            "auction_dynamics": {},
            "opportunities": [],
            "risks": [],
        }
        
        rmn_data = self.performance_data.get("rmn_data", {}).get(self.rmn_id, {})
        channel_data = rmn_data.get("channel_data", {})
        
        # RMN-level KPIs
        total_spend = rmn_data.get("total_spend", rmn_data.get("spend", 0))
        total_sales = rmn_data.get("incremental_sales", 0)
        
        diagnosis["kpis"]["total_spend"] = total_spend
        diagnosis["kpis"]["incremental_sales"] = total_sales
        diagnosis["kpis"]["efficiency"] = total_sales / total_spend if total_spend > 0 else 0
        
        # Channel-level analysis
        for channel_id, ch_data in channel_data.items():
            ch_spend = ch_data.get("spend", 0)
            ch_sales = ch_data.get("incremental_sales", 0)
            ch_efficiency = ch_sales / ch_spend if ch_spend > 0 else 0
            
            diagnosis["channel_performance"][channel_id] = {
                "spend": ch_spend,
                "incremental_sales": ch_sales,
                "efficiency": ch_efficiency,
                "spend_share": ch_spend / total_spend if total_spend > 0 else 0,
            }
        
        # Identify opportunities and risks
        avg_efficiency = diagnosis["kpis"]["efficiency"]
        for channel_id, perf in diagnosis["channel_performance"].items():
            if perf["efficiency"] > avg_efficiency * 1.3:
                diagnosis["opportunities"].append({
                    "entity": channel_id,
                    "type": "scale_channel",
                    "rationale": f"{channel_id} efficiency {perf['efficiency']:.2f} vs RMN avg {avg_efficiency:.2f}",
                })
            elif perf["efficiency"] < avg_efficiency * 0.7:
                diagnosis["risks"].append({
                    "entity": channel_id,
                    "type": "underperforming_channel",
                    "rationale": f"{channel_id} efficiency {perf['efficiency']:.2f} below RMN avg {avg_efficiency:.2f}",
                })
        
        return diagnosis
    
    def optimize(self, diagnosis: Dict[str, Any]) -> OptimizationResult:
        """Optimize channel allocation within this RMN."""
        obj_params = self.get_objective_function_params()
        constraints = self.config.constraints
        
        channel_perf = diagnosis["channel_performance"]
        
        if not channel_perf:
            return OptimizationResult(
                success=False,
                solver_message="No channel performance data"
            )
        
        total_budget = constraints.budget or diagnosis["kpis"]["total_spend"]
        
        # Optimize based on marginal efficiency
        efficiency_sum = sum(p["efficiency"] for p in channel_perf.values()) or 1
        
        optimized_allocation = {}
        for channel_id, perf in channel_perf.items():
            raw_allocation = total_budget * (perf["efficiency"] / efficiency_sum)
            
            min_spend = constraints.channel_floors.get(channel_id, constraints.min_channel_spend)
            max_spend = constraints.channel_ceilings.get(channel_id, total_budget * 0.6)
            
            optimized_allocation[channel_id] = np.clip(raw_allocation, min_spend, max_spend)
        
        # Normalize to budget
        alloc_total = sum(optimized_allocation.values())
        if alloc_total > 0:
            scale_factor = total_budget / alloc_total
            optimized_allocation = {k: v * scale_factor for k, v in optimized_allocation.items()}
        
        expected_sales = sum(
            optimized_allocation[ch] * channel_perf[ch]["efficiency"]
            for ch in optimized_allocation
        )
        
        return OptimizationResult(
            success=True,
            objective_value=expected_sales,
            allocation=optimized_allocation,
            iterations=1,
            convergence_achieved=True,
            solver_status="optimal",
            solver_message=f"RMN {self.rmn_name} channel optimization completed",
        )
    
    def explain(
        self,
        diagnosis: Dict[str, Any],
        optimization_result: OptimizationResult
    ) -> CrewOutput:
        """Generate RMN-specific recommendation narrative."""
        channel_perf = diagnosis["channel_performance"]
        
        allocations = []
        for channel_id, recommended_spend in optimization_result.allocation.items():
            current = channel_perf.get(channel_id, {})
            current_spend = current.get("spend", 0)
            delta = recommended_spend - current_spend
            delta_pct = delta / current_spend if current_spend > 0 else 0
            efficiency = current.get("efficiency", 0)
            
            allocations.append(AllocationRecommendation(
                entity_type="channel",
                entity_id=channel_id,
                entity_name=channel_id,
                current_spend=current_spend,
                recommended_spend=recommended_spend,
                spend_delta=delta,
                spend_delta_pct=delta_pct,
                expected_incremental_sales=recommended_spend * efficiency,
                expected_efficiency=efficiency,
                confidence_level=0.75,
                rationale=f"{'Increase' if delta > 0 else 'Decrease'} based on efficiency {efficiency:.2f}",
                actions=self._get_channel_actions(channel_id, delta_pct),
            ))
        
        return CrewOutput(
            executive_summary=f"{self.rmn_name} Optimization: Reallocation across {len(allocations)} channels "
                            f"to achieve ${optimization_result.objective_value:,.0f} incremental sales",
            key_findings=[
                f"RMN efficiency: {diagnosis['kpis']['efficiency']:.2f} iROAS",
                f"Top channel: {max(channel_perf, key=lambda x: channel_perf[x]['efficiency'])}",
                f"Identified {len(diagnosis['opportunities'])} scale opportunities",
            ],
            opportunities=[o["rationale"] for o in diagnosis["opportunities"]],
            risks=[r["rationale"] for r in diagnosis["risks"]],
            allocations=allocations,
            total_recommended_spend=sum(optimization_result.allocation.values()),
            expected_incremental_sales=optimization_result.objective_value,
            expected_efficiency=optimization_result.objective_value / sum(optimization_result.allocation.values())
                                if optimization_result.allocation else 0,
        )
    
    def _get_channel_actions(self, channel_id: str, delta_pct: float) -> List[str]:
        """Get action items for channel allocation change."""
        actions = []
        channel_lower = channel_id.lower()
        
        if delta_pct > 0.1:
            actions.append(f"Increase {channel_id} budget by {delta_pct:.0%}")
            if "search" in channel_lower:
                actions.append("Expand keyword coverage")
                actions.append("Increase bid caps on top performers")
            elif "display" in channel_lower:
                actions.append("Expand audience targeting")
                actions.append("Add high-value placements")
            elif "video" in channel_lower:
                actions.append("Increase frequency caps")
                actions.append("Test additional creative formats")
        elif delta_pct < -0.1:
            actions.append(f"Reduce {channel_id} budget by {abs(delta_pct):.0%}")
            actions.append("Pause lowest-performing tactics")
            actions.append("Tighten targeting to core audiences")
        else:
            actions.append("Maintain current allocation")
            actions.append("Optimize within existing budget")
        
        return actions
