"""
Campaign and Message Level Optimization Crew

Optimizes campaign structure, targeting, and message/creative strategy
to improve efficiency and outcomes, while feeding learnings back into
budget allocation.

Core Agents:
- Campaign Ops Lead (manager)
- Campaign Performance Analyst
- Audience/Keyword Analyst
- Creative/Message Analyst
- Experimentation Designer
- Bidding/Pacing Specialist
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


class CampaignMessageOptimizationCrew(BaseOptimizationCrew):
    """
    Campaign and Message level optimization crew.
    
    Purpose: Optimize campaign structure, targeting, and message/creative
    strategy to improve efficiency and outcomes.
    
    Inputs:
    - Campaign table (spend, impressions, clicks, conversions, incremental sales)
    - Message/creative metadata (creative ID, theme, CTA, asset type)
    - Audience/keyword/product targeting data
    - Frequency and saturation signals
    
    Outputs:
    - Campaign POV: which campaigns/messages are scaling vs saturated
    - Actions: pause/scale/refresh creatives; audience expansions
    - Test plan: experiments and measurement plan
    """
    
    @property
    def crew_type(self) -> str:
        return "campaign_message_optimization"
    
    def _setup_agents(self) -> None:
        """Define campaign-level optimization agents."""
        
        self.agents["campaign_ops_lead"] = AgentDefinition(
            agent_id="campaign_ops_lead",
            role="Campaign Ops Lead",
            name="Campaign Ops Lead",
            goal="Ensure changes are implementable and aligned to outcome and pacing",
            backstory="""You lead campaign operations and ensure all recommendations 
            can be executed within platform constraints and timelines. You coordinate 
            between strategy and execution, ensuring pacing goals are met and changes 
            are properly sequenced.""",
            tools=["campaign_manager_tool", "pacing_tracker_tool"],
            allow_delegation=True,
            verbose=True,
        )
        
        self.agents["campaign_performance_analyst"] = AgentDefinition(
            agent_id="campaign_performance_analyst",
            role="Campaign Performance Analyst",
            name="Campaign Performance Analyst",
            goal="Compute campaign and message KPIs and rank opportunities",
            backstory="""You analyze campaign performance at granular levels. 
            You compute efficiency metrics, identify top and bottom performers, 
            track saturation signals, and surface actionable insights for 
            campaign optimization.""",
            tools=["campaign_kpi_tool", "performance_ranker_tool", "saturation_detector_tool"],
        )
        
        self.agents["audience_keyword_analyst"] = AgentDefinition(
            agent_id="audience_keyword_analyst",
            role="Audience/Keyword Analyst",
            name="Audience/Keyword Analyst",
            goal="Diagnose targeting quality and demand capture vs demand creation",
            backstory="""You are an expert in audience segmentation and keyword 
            strategy. You analyze targeting effectiveness, identify expansion 
            opportunities, and distinguish between demand capture (branded, 
            high-intent) and demand creation (prospecting, awareness).""",
            tools=["audience_analyzer_tool", "keyword_tool", "intent_classifier_tool"],
        )
        
        self.agents["creative_message_analyst"] = AgentDefinition(
            agent_id="creative_message_analyst",
            role="Creative/Message Analyst",
            name="Creative/Message Analyst",
            goal="Evaluate message themes and formats; flag fatigue and misalignment",
            backstory="""You analyze creative performance and message effectiveness. 
            You identify creative fatigue, test winning elements, and ensure 
            message-market fit. You recommend refresh cycles and new creative 
            directions based on performance data.""",
            tools=["creative_analyzer_tool", "fatigue_detector_tool", "message_scorer_tool"],
        )
        
        self.agents["experimentation_designer"] = AgentDefinition(
            agent_id="experimentation_designer",
            role="Experimentation Designer",
            name="Experimentation Designer",
            goal="Define A/B and multivariate tests with required sample sizes",
            backstory="""You design statistically rigorous experiments to improve 
            campaign performance. You calculate sample sizes, define test/control 
            structures, and create learning agendas that systematically improve 
            response curves over time.""",
            tools=["experiment_designer_tool", "sample_size_calculator_tool"],
        )
        
        self.agents["bidding_pacing_specialist"] = AgentDefinition(
            agent_id="bidding_pacing_specialist",
            role="Bidding/Pacing Specialist",
            name="Bidding/Pacing Specialist",
            goal="Define bid/budget rules and pacing guardrails",
            backstory="""You optimize bidding strategies and budget pacing. 
            You set bid caps, dayparting rules, and pacing curves that maximize 
            efficiency while ensuring spend goals are met. You monitor for 
            bid inflation and competitive dynamics.""",
            tools=["bid_optimizer_tool", "pacing_tool", "daypart_analyzer_tool"],
        )
        
        self.agents["constraints_risk_manager"] = AgentDefinition(
            agent_id="constraints_risk_manager",
            role="Constraints & Risk Manager",
            name="Constraints & Risk Manager",
            goal="Enforce brand safety and package output appropriately",
            backstory="""You ensure all campaign recommendations comply with 
            brand safety policies, platform rules, and legal requirements. 
            You flag risky placements, audit targeting for compliance, and 
            protect brand reputation.""",
            tools=["brand_safety_tool", "compliance_checker_tool"],
        )
        
        self.agents["recommendation_narrator"] = AgentDefinition(
            agent_id="recommendation_narrator",
            role="Recommendation Narrator",
            name="Recommendation Narrator",
            goal="Create actionable campaign playbooks and test plans",
            backstory="""You translate analytical insights into clear campaign 
            action plans. You write specific instructions for pause/scale decisions, 
            creative refreshes, targeting changes, and experimentation priorities.""",
            tools=["playbook_generator_tool", "action_formatter_tool"],
        )
        
        self.agents["qa_auditor"] = AgentDefinition(
            agent_id="qa_auditor",
            role="QA Auditor",
            name="QA Auditor",
            goal="Verify analysis accuracy and recommendation completeness",
            backstory="""You ensure all campaign analysis is accurate and 
            recommendations are complete. You verify metrics match source data, 
            catch calculation errors, and ensure no campaigns are missed.""",
            tools=["data_validator_tool", "completeness_checker_tool"],
        )
    
    def _setup_tasks(self) -> None:
        """Define campaign-level optimization tasks."""
        
        self.tasks["ingest_campaign_data"] = TaskDefinition(
            task_id="ingest_campaign_data",
            description="""Ingest and validate campaign performance data:
            - Spend, impressions, clicks, conversions by campaign
            - Incremental sales/profit if modeled
            - Creative/message metadata
            - Targeting parameters (audiences, keywords, products)
            Confirm data completeness and quality.""",
            expected_output="Campaign data validation report",
            agent_id="campaign_performance_analyst",
        )
        
        self.tasks["analyze_campaign_performance"] = TaskDefinition(
            task_id="analyze_campaign_performance",
            description="""Analyze campaign performance:
            - Rank campaigns by efficiency and scale
            - Identify top performers for scale
            - Flag saturated or declining campaigns
            - Compute contribution to total""",
            expected_output="Campaign performance scorecard with rankings",
            agent_id="campaign_performance_analyst",
            context_tasks=["ingest_campaign_data"],
        )
        
        self.tasks["analyze_targeting"] = TaskDefinition(
            task_id="analyze_targeting",
            description="""Analyze targeting effectiveness:
            - Audience segment performance
            - Keyword/product targeting efficiency
            - Demand capture vs demand creation mix
            - Expansion opportunities""",
            expected_output="Targeting analysis with expansion recommendations",
            agent_id="audience_keyword_analyst",
            context_tasks=["analyze_campaign_performance"],
        )
        
        self.tasks["analyze_creative"] = TaskDefinition(
            task_id="analyze_creative",
            description="""Analyze creative/message performance:
            - Creative fatigue signals
            - Message theme effectiveness
            - Format performance (static, video, carousel)
            - Refresh recommendations""",
            expected_output="Creative analysis with refresh plan",
            agent_id="creative_message_analyst",
            context_tasks=["analyze_campaign_performance"],
        )
        
        self.tasks["design_experiments"] = TaskDefinition(
            task_id="design_experiments",
            description="""Design test plan:
            - A/B tests for underperforming elements
            - Multivariate tests for creative optimization
            - Sample size and duration requirements
            - Learning agenda priorities""",
            expected_output="Experimentation plan with test definitions",
            agent_id="experimentation_designer",
            context_tasks=["analyze_targeting", "analyze_creative"],
        )
        
        self.tasks["optimize_bidding_pacing"] = TaskDefinition(
            task_id="optimize_bidding_pacing",
            description="""Optimize bidding and pacing:
            - Bid adjustment recommendations
            - Pacing curve optimization
            - Dayparting opportunities
            - Budget reallocation within campaigns""",
            expected_output="Bidding/pacing optimization plan",
            agent_id="bidding_pacing_specialist",
            context_tasks=["analyze_campaign_performance"],
        )
        
        self.tasks["validate_brand_safety"] = TaskDefinition(
            task_id="validate_brand_safety",
            description="""Validate brand safety compliance:
            - Review placement lists
            - Audit targeting for sensitive categories
            - Check creative compliance
            - Flag any policy violations""",
            expected_output="Brand safety validation report",
            agent_id="constraints_risk_manager",
            context_tasks=["analyze_targeting", "analyze_creative"],
        )
        
        self.tasks["generate_campaign_playbook"] = TaskDefinition(
            task_id="generate_campaign_playbook",
            description="""Generate campaign action playbook:
            - Scale/pause/refresh decisions
            - Targeting changes
            - Creative updates
            - Bid/pacing adjustments
            - Test priorities""",
            expected_output="Campaign optimization playbook",
            agent_id="recommendation_narrator",
            context_tasks=["design_experiments", "optimize_bidding_pacing", "validate_brand_safety"],
        )
        
        self.tasks["qa_campaign_output"] = TaskDefinition(
            task_id="qa_campaign_output",
            description="""QA the campaign output:
            - Verify performance calculations
            - Check completeness of recommendations
            - Validate test designs
            - Ensure actionability""",
            expected_output="QA sign-off",
            agent_id="qa_auditor",
            context_tasks=["generate_campaign_playbook"],
        )
    
    def ingest_and_validate(self) -> Dict[str, Any]:
        """Validate campaign performance data."""
        issues = []
        
        campaign_data = self.performance_data.get("campaigns", {})
        
        if not campaign_data:
            issues.append("No campaign data available")
        
        # Check for required metrics
        for campaign_id, data in campaign_data.items():
            if "spend" not in data:
                issues.append(f"Missing spend for campaign {campaign_id}")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "n_campaigns": len(campaign_data),
            "validated_at": datetime.utcnow().isoformat(),
        }
    
    def diagnose(self) -> Dict[str, Any]:
        """Analyze campaign performance and identify opportunities."""
        diagnosis = {
            "kpis": {},
            "campaign_performance": {},
            "creative_analysis": {},
            "targeting_analysis": {},
            "opportunities": [],
            "risks": [],
        }
        
        campaign_data = self.performance_data.get("campaigns", {})
        
        # Aggregate KPIs
        total_spend = sum(c.get("spend", 0) for c in campaign_data.values())
        total_sales = sum(c.get("incremental_sales", 0) for c in campaign_data.values())
        
        diagnosis["kpis"]["total_spend"] = total_spend
        diagnosis["kpis"]["total_incremental_sales"] = total_sales
        diagnosis["kpis"]["overall_efficiency"] = total_sales / total_spend if total_spend > 0 else 0
        
        # Campaign-level analysis
        for campaign_id, data in campaign_data.items():
            spend = data.get("spend", 0)
            sales = data.get("incremental_sales", 0)
            efficiency = sales / spend if spend > 0 else 0
            
            diagnosis["campaign_performance"][campaign_id] = {
                "spend": spend,
                "incremental_sales": sales,
                "efficiency": efficiency,
                "status": data.get("status", "active"),
            }
            
            # Identify opportunities/risks
            avg_eff = diagnosis["kpis"]["overall_efficiency"]
            if efficiency > avg_eff * 1.5:
                diagnosis["opportunities"].append({
                    "entity": campaign_id,
                    "type": "scale_campaign",
                    "rationale": f"Campaign efficiency {efficiency:.2f} is 50%+ above average",
                })
            elif efficiency < avg_eff * 0.5 and spend > total_spend * 0.05:
                diagnosis["risks"].append({
                    "entity": campaign_id,
                    "type": "underperforming_campaign",
                    "rationale": f"Campaign efficiency {efficiency:.2f} is 50%+ below average with significant spend",
                })
        
        return diagnosis
    
    def optimize(self, diagnosis: Dict[str, Any]) -> OptimizationResult:
        """Optimize campaign allocation."""
        constraints = self.config.constraints
        campaign_perf = diagnosis["campaign_performance"]
        
        if not campaign_perf:
            return OptimizationResult(
                success=False,
                solver_message="No campaign data"
            )
        
        total_budget = constraints.budget or diagnosis["kpis"]["total_spend"]
        
        # Reallocate based on efficiency
        active_campaigns = {k: v for k, v in campaign_perf.items() if v["status"] == "active"}
        efficiency_sum = sum(c["efficiency"] for c in active_campaigns.values()) or 1
        
        optimized_allocation = {}
        for campaign_id, perf in active_campaigns.items():
            raw_allocation = total_budget * (perf["efficiency"] / efficiency_sum)
            optimized_allocation[campaign_id] = max(raw_allocation, constraints.min_channel_spend)
        
        # Normalize
        alloc_total = sum(optimized_allocation.values())
        if alloc_total > 0:
            scale = total_budget / alloc_total
            optimized_allocation = {k: v * scale for k, v in optimized_allocation.items()}
        
        expected_sales = sum(
            optimized_allocation[c] * campaign_perf[c]["efficiency"]
            for c in optimized_allocation
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
        """Generate campaign optimization narrative."""
        campaign_perf = diagnosis["campaign_performance"]
        
        allocations = []
        for campaign_id, recommended in optimization_result.allocation.items():
            current = campaign_perf.get(campaign_id, {}).get("spend", 0)
            delta = recommended - current
            delta_pct = delta / current if current > 0 else 0
            efficiency = campaign_perf.get(campaign_id, {}).get("efficiency", 0)
            
            action = "SCALE" if delta_pct > 0.2 else "PAUSE" if delta_pct < -0.3 else "MAINTAIN"
            
            allocations.append(AllocationRecommendation(
                entity_type="campaign",
                entity_id=campaign_id,
                entity_name=campaign_id,
                current_spend=current,
                recommended_spend=recommended,
                spend_delta=delta,
                spend_delta_pct=delta_pct,
                expected_incremental_sales=recommended * efficiency,
                expected_efficiency=efficiency,
                rationale=f"{action}: Efficiency {efficiency:.2f}",
                actions=[f"{action} campaign", "Monitor performance", "Test new creatives" if action == "SCALE" else ""],
            ))
        
        return CrewOutput(
            executive_summary=f"Campaign Optimization: {len(allocations)} campaigns analyzed, "
                            f"${optimization_result.objective_value:,.0f} projected sales",
            key_findings=[
                f"Overall campaign efficiency: {diagnosis['kpis']['overall_efficiency']:.2f}",
                f"{len(diagnosis['opportunities'])} scale opportunities",
                f"{len(diagnosis['risks'])} underperformers to address",
            ],
            opportunities=[o["rationale"] for o in diagnosis["opportunities"]],
            risks=[r["rationale"] for r in diagnosis["risks"]],
            allocations=allocations,
            total_recommended_spend=sum(optimization_result.allocation.values()),
            expected_incremental_sales=optimization_result.objective_value,
        )
