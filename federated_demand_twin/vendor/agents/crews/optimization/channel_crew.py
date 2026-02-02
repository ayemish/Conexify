"""
Channel Level Optimization Crew

Optimizes within-channel levers and cross-channel mix, translating
the optimized plan into channel playbooks.

Core Agents:
- Channel Strategy Lead (manager)
- Search Specialist
- Display Specialist
- Video Specialist
- Email Specialist
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


class ChannelOptimizationCrew(BaseOptimizationCrew):
    """
    Channel-level optimization crew.
    
    Purpose: Optimize within-channel levers and cross-channel mix,
    translating the optimized plan into channel playbooks.
    
    Inputs:
    - Channel performance table (spend, incremental sales, efficiency)
    - Response curve parameters (if available)
    - Channel-specific levers (keywords, audiences, frequency, segments)
    - Channel policy constraints
    
    Outputs:
    - Channel POV: what each channel contributes and marginal limits
    - Optimized channel mix (spend and expected impact)
    - Channel playbooks: levers, monitoring metrics, stop-loss triggers
    """
    
    @property
    def crew_type(self) -> str:
        return "channel_optimization"
    
    def _setup_agents(self) -> None:
        """Define channel-level optimization agents."""
        
        self.agents["channel_strategy_lead"] = AgentDefinition(
            agent_id="channel_strategy_lead",
            role="Channel Strategy Lead",
            name="Channel Strategy Lead",
            goal="Align cross-channel tradeoffs to outcome and time window",
            backstory="""You lead the cross-channel media strategy. You balance 
            investment across Search, Display, Video, and Email to maximize 
            the objective while respecting channel constraints and capabilities. 
            You ensure the channel mix is optimized for the planning window.""",
            tools=["channel_planner_tool", "tradeoff_analyzer_tool"],
            allow_delegation=True,
            verbose=True,
        )
        
        self.agents["search_specialist"] = AgentDefinition(
            agent_id="search_specialist",
            role="Search Specialist",
            name="Search Specialist",
            goal="Optimize search channel performance through keywords and bids",
            backstory="""You are an expert in retail media search advertising. 
            You optimize keyword portfolios, bid strategies, and match types 
            to maximize efficiency and capture demand. You understand search 
            intent signals and competitive dynamics.""",
            tools=["keyword_tool", "bid_optimizer_tool", "search_term_analyzer_tool"],
        )
        
        self.agents["display_specialist"] = AgentDefinition(
            agent_id="display_specialist",
            role="Display Specialist",
            name="Display Specialist",
            goal="Optimize display channel through audiences and placements",
            backstory="""You specialize in display advertising on retail media 
            networks. You optimize audience targeting, placement selection, 
            and creative formats to drive efficient conversions. You balance 
            reach and frequency for optimal impact.""",
            tools=["audience_tool", "placement_analyzer_tool", "frequency_tool"],
        )
        
        self.agents["video_specialist"] = AgentDefinition(
            agent_id="video_specialist",
            role="Video Specialist",
            name="Video Specialist",
            goal="Optimize video channel through creative and targeting",
            backstory="""You are an expert in video advertising including CTV 
            and online video. You optimize creative length, targeting, and 
            frequency to maximize brand impact and conversions. You understand 
            viewability and completion metrics.""",
            tools=["video_analyzer_tool", "ctv_planner_tool", "creative_tool"],
        )
        
        self.agents["email_specialist"] = AgentDefinition(
            agent_id="email_specialist",
            role="Email Specialist",
            name="Email Specialist",
            goal="Optimize email channel through segmentation and messaging",
            backstory="""You specialize in email marketing within retail media. 
            You optimize segmentation, send timing, subject lines, and content 
            to maximize open rates, clicks, and conversions. You balance 
            frequency to avoid fatigue.""",
            tools=["email_segmentation_tool", "send_time_optimizer_tool", "content_analyzer_tool"],
        )
        
        self.agents["incrementality_analyst"] = AgentDefinition(
            agent_id="incrementality_analyst",
            role="Incrementality Analyst",
            name="Incrementality Analyst",
            goal="Analyze response curves and marginal returns by channel",
            backstory="""You estimate channel-specific response curves and 
            identify saturation points. You distinguish between incremental 
            and cannibalized sales, and you identify the marginal return 
            at different spend levels for each channel.""",
            tools=["response_curve_tool", "saturation_analyzer_tool", "marginal_return_tool"],
        )
        
        self.agents["budget_allocation_optimizer"] = AgentDefinition(
            agent_id="budget_allocation_optimizer",
            role="Budget Allocation Optimizer",
            name="Budget Allocation Optimizer",
            goal="Solve optimal channel mix using response curves",
            backstory="""You optimize the allocation of budget across channels 
            using response curves and marginal returns. You find the allocation 
            that maximizes the objective while respecting channel constraints 
            and diminishing returns.""",
            tools=["optimizer_tool", "constraint_solver_tool"],
        )
        
        self.agents["constraints_risk_manager"] = AgentDefinition(
            agent_id="constraints_risk_manager",
            role="Constraints & Risk Manager",
            name="Constraints & Risk Manager",
            goal="Enforce channel policies and manage execution risk",
            backstory="""You ensure all channel recommendations comply with 
            platform policies, operational capacity, and brand guidelines. 
            You identify execution risks and define stop-loss triggers.""",
            tools=["policy_checker_tool", "risk_scorer_tool"],
        )
        
        self.agents["recommendation_narrator"] = AgentDefinition(
            agent_id="recommendation_narrator",
            role="Recommendation Narrator",
            name="Recommendation Narrator",
            goal="Create channel-specific playbooks with tactical guidance",
            backstory="""You create detailed channel playbooks that translate 
            optimization outputs into actionable tactics. You specify the 
            levers to pull, metrics to monitor, and triggers for adjustment.""",
            tools=["playbook_generator_tool"],
        )
        
        self.agents["qa_auditor"] = AgentDefinition(
            agent_id="qa_auditor",
            role="QA Auditor",
            name="QA Auditor",
            goal="Verify analysis and playbook accuracy",
            backstory="""You ensure all channel analysis is accurate and 
            playbooks are complete and actionable. You verify calculations 
            and catch errors before execution.""",
            tools=["data_validator_tool"],
        )
    
    def _setup_tasks(self) -> None:
        """Define channel-level optimization tasks."""
        
        self.tasks["ingest_channel_data"] = TaskDefinition(
            task_id="ingest_channel_data",
            description="""Ingest and validate channel performance data:
            - Spend, incremental sales, efficiency by channel
            - Response curve parameters if available
            - Channel-specific metrics (CTR, CVR, CPM, CPC)
            - Historical trends and seasonality""",
            expected_output="Channel data validation report",
            agent_id="channel_strategy_lead",
        )
        
        self.tasks["analyze_search"] = TaskDefinition(
            task_id="analyze_search",
            description="""Analyze Search channel performance:
            - Keyword portfolio performance
            - Bid efficiency and auction dynamics
            - Search term coverage and gaps
            - Scale opportunities and saturation""",
            expected_output="Search channel analysis",
            agent_id="search_specialist",
            context_tasks=["ingest_channel_data"],
        )
        
        self.tasks["analyze_display"] = TaskDefinition(
            task_id="analyze_display",
            description="""Analyze Display channel performance:
            - Audience segment performance
            - Placement efficiency
            - Frequency and reach optimization
            - Creative format performance""",
            expected_output="Display channel analysis",
            agent_id="display_specialist",
            context_tasks=["ingest_channel_data"],
        )
        
        self.tasks["analyze_video"] = TaskDefinition(
            task_id="analyze_video",
            description="""Analyze Video channel performance:
            - CTV vs online video performance
            - Completion rates and viewability
            - Frequency optimization
            - Creative performance by length/format""",
            expected_output="Video channel analysis",
            agent_id="video_specialist",
            context_tasks=["ingest_channel_data"],
        )
        
        self.tasks["analyze_email"] = TaskDefinition(
            task_id="analyze_email",
            description="""Analyze Email channel performance:
            - Open rates and click rates by segment
            - Send frequency optimization
            - Content and subject line performance
            - List health and deliverability""",
            expected_output="Email channel analysis",
            agent_id="email_specialist",
            context_tasks=["ingest_channel_data"],
        )
        
        self.tasks["estimate_response_curves"] = TaskDefinition(
            task_id="estimate_response_curves",
            description="""Estimate channel response curves:
            - Fit saturation curves to historical data
            - Identify marginal return at current spend
            - Estimate scale headroom per channel
            - Flag uncertainty in curve estimates""",
            expected_output="Response curve estimates with confidence",
            agent_id="incrementality_analyst",
            context_tasks=["analyze_search", "analyze_display", "analyze_video", "analyze_email"],
        )
        
        self.tasks["optimize_channel_mix"] = TaskDefinition(
            task_id="optimize_channel_mix",
            description="""Optimize cross-channel mix:
            - Set objective function for desired outcome
            - Apply response curves
            - Solve for optimal allocation
            - Report marginal returns at solution""",
            expected_output="Optimized channel allocation",
            agent_id="budget_allocation_optimizer",
            context_tasks=["estimate_response_curves"],
        )
        
        self.tasks["validate_channel_constraints"] = TaskDefinition(
            task_id="validate_channel_constraints",
            description="""Validate channel constraints:
            - Minimum/maximum spend by channel
            - Operational capacity limits
            - Platform policy compliance
            - Define stop-loss triggers""",
            expected_output="Constraint validation with stop-loss triggers",
            agent_id="constraints_risk_manager",
            context_tasks=["optimize_channel_mix"],
        )
        
        self.tasks["generate_channel_playbooks"] = TaskDefinition(
            task_id="generate_channel_playbooks",
            description="""Generate channel playbooks:
            - Tactical recommendations per channel
            - Levers to pull and in what order
            - Monitoring metrics and thresholds
            - Adjustment triggers and escalation""",
            expected_output="Channel-specific playbooks",
            agent_id="recommendation_narrator",
            context_tasks=["validate_channel_constraints"],
        )
        
        self.tasks["qa_channel_output"] = TaskDefinition(
            task_id="qa_channel_output",
            description="""QA channel outputs:
            - Verify calculations
            - Check playbook completeness
            - Validate constraints
            - Ensure executability""",
            expected_output="QA sign-off",
            agent_id="qa_auditor",
            context_tasks=["generate_channel_playbooks"],
        )
    
    def ingest_and_validate(self) -> Dict[str, Any]:
        """Validate channel performance data."""
        issues = []
        
        channel_data = self.performance_data.get("channels", {})
        
        if not channel_data:
            issues.append("No channel data available")
        
        expected_channels = ["search", "display", "video", "email"]
        for channel in expected_channels:
            if channel not in channel_data:
                issues.append(f"Missing data for {channel} channel")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "n_channels": len(channel_data),
            "channels": list(channel_data.keys()),
            "validated_at": datetime.utcnow().isoformat(),
        }
    
    def diagnose(self) -> Dict[str, Any]:
        """Analyze channel performance and response curves."""
        diagnosis = {
            "kpis": {},
            "channel_performance": {},
            "response_curves": {},
            "opportunities": [],
            "risks": [],
        }
        
        channel_data = self.performance_data.get("channels", {})
        
        total_spend = sum(c.get("spend", 0) for c in channel_data.values())
        total_sales = sum(c.get("incremental_sales", 0) for c in channel_data.values())
        
        diagnosis["kpis"]["total_spend"] = total_spend
        diagnosis["kpis"]["total_incremental_sales"] = total_sales
        diagnosis["kpis"]["overall_efficiency"] = total_sales / total_spend if total_spend > 0 else 0
        
        for channel_id, data in channel_data.items():
            spend = data.get("spend", 0)
            sales = data.get("incremental_sales", 0)
            efficiency = sales / spend if spend > 0 else 0
            
            # Estimate simple response curve parameters
            elasticity = data.get("elasticity", 0.15)
            saturation_pct = data.get("saturation_pct", spend / (spend + 100000))
            
            diagnosis["channel_performance"][channel_id] = {
                "spend": spend,
                "incremental_sales": sales,
                "efficiency": efficiency,
                "spend_share": spend / total_spend if total_spend > 0 else 0,
                "elasticity": elasticity,
                "saturation_pct": saturation_pct,
            }
            
            diagnosis["response_curves"][channel_id] = {
                "elasticity": elasticity,
                "saturation_point": spend / (1 - saturation_pct) if saturation_pct < 1 else spend * 2,
                "marginal_return": efficiency * (1 - saturation_pct),
            }
            
            # Opportunities and risks
            if saturation_pct < 0.5 and efficiency > diagnosis["kpis"]["overall_efficiency"]:
                diagnosis["opportunities"].append({
                    "entity": channel_id,
                    "type": "scale_channel",
                    "rationale": f"{channel_id} has headroom (saturation {saturation_pct:.0%}) and high efficiency",
                })
            elif saturation_pct > 0.8:
                diagnosis["risks"].append({
                    "entity": channel_id,
                    "type": "saturated_channel",
                    "rationale": f"{channel_id} is {saturation_pct:.0%} saturated - diminishing returns",
                })
        
        return diagnosis
    
    def optimize(self, diagnosis: Dict[str, Any]) -> OptimizationResult:
        """Optimize channel mix using response curves."""
        constraints = self.config.constraints
        channel_perf = diagnosis["channel_performance"]
        response_curves = diagnosis["response_curves"]
        
        if not channel_perf:
            return OptimizationResult(
                success=False,
                solver_message="No channel data"
            )
        
        total_budget = constraints.budget or diagnosis["kpis"]["total_spend"]
        
        # Optimize using marginal returns
        marginal_returns = {
            ch: response_curves[ch]["marginal_return"]
            for ch in channel_perf
        }
        mr_sum = sum(marginal_returns.values()) or 1
        
        optimized_allocation = {}
        for channel_id in channel_perf:
            raw_allocation = total_budget * (marginal_returns[channel_id] / mr_sum)
            
            min_spend = constraints.channel_floors.get(channel_id, constraints.min_channel_spend)
            max_spend = constraints.channel_ceilings.get(channel_id, total_budget * 0.5)
            
            optimized_allocation[channel_id] = np.clip(raw_allocation, min_spend, max_spend)
        
        # Normalize
        alloc_total = sum(optimized_allocation.values())
        if alloc_total > 0:
            scale = total_budget / alloc_total
            optimized_allocation = {k: v * scale for k, v in optimized_allocation.items()}
        
        # Calculate expected sales using diminishing returns
        expected_sales = 0
        for ch in optimized_allocation:
            perf = channel_perf[ch]
            # Apply diminishing returns based on saturation
            new_saturation = optimized_allocation[ch] / response_curves[ch]["saturation_point"]
            adjusted_efficiency = perf["efficiency"] * (1 - new_saturation * 0.5)
            expected_sales += optimized_allocation[ch] * adjusted_efficiency
        
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
        """Generate channel optimization narrative and playbooks."""
        channel_perf = diagnosis["channel_performance"]
        response_curves = diagnosis["response_curves"]
        
        allocations = []
        for channel_id, recommended in optimization_result.allocation.items():
            current = channel_perf.get(channel_id, {}).get("spend", 0)
            delta = recommended - current
            delta_pct = delta / current if current > 0 else 0
            efficiency = channel_perf.get(channel_id, {}).get("efficiency", 0)
            saturation = channel_perf.get(channel_id, {}).get("saturation_pct", 0)
            
            allocations.append(AllocationRecommendation(
                entity_type="channel",
                entity_id=channel_id,
                entity_name=channel_id.title(),
                current_spend=current,
                recommended_spend=recommended,
                spend_delta=delta,
                spend_delta_pct=delta_pct,
                expected_incremental_sales=recommended * efficiency * (1 - saturation * 0.5),
                expected_efficiency=efficiency,
                rationale=self._get_channel_rationale(channel_id, delta_pct, saturation),
                actions=self._get_channel_playbook(channel_id, delta_pct),
            ))
        
        return CrewOutput(
            executive_summary=f"Channel Mix Optimization: Reallocating ${sum(optimization_result.allocation.values()):,.0f} "
                            f"across {len(allocations)} channels for ${optimization_result.objective_value:,.0f} projected sales",
            key_findings=[
                f"Overall efficiency: {diagnosis['kpis']['overall_efficiency']:.2f}",
                f"Channels with headroom: {len(diagnosis['opportunities'])}",
                f"Saturated channels: {len(diagnosis['risks'])}",
            ],
            opportunities=[o["rationale"] for o in diagnosis["opportunities"]],
            risks=[r["rationale"] for r in diagnosis["risks"]],
            allocations=allocations,
            total_recommended_spend=sum(optimization_result.allocation.values()),
            expected_incremental_sales=optimization_result.objective_value,
        )
    
    def _get_channel_rationale(self, channel_id: str, delta_pct: float, saturation: float) -> str:
        """Get rationale for channel allocation."""
        if delta_pct > 0.2:
            return f"Increase {channel_id}: headroom available (saturation {saturation:.0%})"
        elif delta_pct < -0.2:
            return f"Reduce {channel_id}: high saturation ({saturation:.0%}) limiting returns"
        else:
            return f"Maintain {channel_id}: near optimal efficiency"
    
    def _get_channel_playbook(self, channel_id: str, delta_pct: float) -> List[str]:
        """Get tactical playbook for channel."""
        channel_lower = channel_id.lower()
        actions = []
        
        if delta_pct > 0.1:
            if "search" in channel_lower:
                actions = [
                    f"Increase {channel_id} budget by {delta_pct:.0%}",
                    "Expand keyword portfolio into long-tail terms",
                    "Test broader match types on high performers",
                    "Increase bids on top converting keywords",
                ]
            elif "display" in channel_lower:
                actions = [
                    f"Increase {channel_id} budget by {delta_pct:.0%}",
                    "Expand audience targeting to lookalikes",
                    "Add high-value placement categories",
                    "Test additional creative formats",
                ]
            elif "video" in channel_lower:
                actions = [
                    f"Increase {channel_id} budget by {delta_pct:.0%}",
                    "Extend frequency cap for engaged audiences",
                    "Add CTV inventory if available",
                    "Test 15s and 6s creative cuts",
                ]
            elif "email" in channel_lower:
                actions = [
                    f"Increase {channel_id} budget by {delta_pct:.0%}",
                    "Expand to additional segments",
                    "Increase send frequency for engaged users",
                    "Test new subject line variations",
                ]
        elif delta_pct < -0.1:
            actions = [
                f"Reduce {channel_id} budget by {abs(delta_pct):.0%}",
                "Pause lowest-performing tactics first",
                "Tighten targeting to core segments",
                f"Set stop-loss at -15% efficiency decline",
            ]
        else:
            actions = [
                f"Maintain {channel_id} at current level",
                "Continue optimization within budget",
                "Monitor for saturation signals",
            ]
        
        return actions
