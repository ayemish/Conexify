"""
Scenario Orchestrator Crew

Master orchestrator that coordinates all optimization crews to execute
user-selected or agent-generated business scenarios. Implements the
decision-support workflow with collaborative multi-agent reasoning.

Key Responsibilities:
1. Analyze current state and generate scenario recommendations
2. Execute user-selected scenarios across relevant crews
3. Coordinate inter-crew messaging and information flow
4. Aggregate results into unified decision recommendations
5. Provide evidence-based reasoning and confidence metrics
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Type
from enum import Enum
import logging
import uuid

from .base_crew import BaseOptimizationCrew, AgentDefinition, TaskDefinition
from .schemas import (
    DesiredOutcome,
    CrewConfig,
    CrewOutput,
    OptimizationResult,
    AllocationRecommendation,
    ImpactEstimate,
    RiskAssessment,
    OptimizationConstraints,
)
from .scenarios import (
    BusinessScenario,
    ScenarioCategory,
    ScenarioConstraints,
    RiskAppetite,
    Cadence,
    SCENARIO_CATALOG,
    get_scenario,
    list_scenarios_by_category,
    MessageBus,
    CrossCrewCoordinator,
    CrewMessage,
    ScenarioExecutor,
)
from .scenarios.messaging import CrewType, MessageType, MessagePriority

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ScenarioSelectionMode(Enum):
    """How the scenario was selected."""
    USER_SELECTED = "user_selected"
    AGENT_RECOMMENDED = "agent_recommended"
    AUTO_TRIGGERED = "auto_triggered"


@dataclass
class ScenarioExecutionContext:
    """Context for executing a scenario across crews."""
    session_id: str
    scenario: BusinessScenario
    selection_mode: ScenarioSelectionMode
    user_parameters: Dict[str, Any] = field(default_factory=dict)
    risk_appetite: RiskAppetite = RiskAppetite.BALANCED
    cadence: Cadence = Cadence.WEEKLY
    max_reallocation_pct: float = 0.15
    exploration_budget_pct: float = 0.10
    current_state: Dict[str, Any] = field(default_factory=dict)
    brand_id: Optional[str] = None
    priority_entities: List[str] = field(default_factory=list)


@dataclass
class ScenarioRecommendation:
    """Agent-generated scenario recommendation."""
    scenario_id: str
    scenario_name: str
    confidence: float
    rationale: str
    expected_impact: float
    risk_level: str
    triggers_detected: List[str]
    priority: int


@dataclass
class OrchestratorOutput:
    """Output from the scenario orchestrator."""
    session_id: str
    scenario_id: str
    scenario_name: str
    selection_mode: str
    crews_executed: List[str]
    crew_outputs: Dict[str, Any]
    aggregated_recommendations: List[Dict[str, Any]]
    supporting_evidence: List[Dict[str, Any]]
    reasoning_chain: Dict[str, Any]
    executive_summary: str
    total_expected_impact: float
    overall_confidence: float
    risk_assessment: str
    constraints_satisfied: bool
    constraint_violations: List[str]
    execution_time_ms: int
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "selection_mode": self.selection_mode,
            "crews_executed": self.crews_executed,
            "aggregated_recommendations": self.aggregated_recommendations,
            "supporting_evidence": self.supporting_evidence,
            "reasoning_chain": self.reasoning_chain,
            "executive_summary": self.executive_summary,
            "total_expected_impact": self.total_expected_impact,
            "overall_confidence": self.overall_confidence,
            "risk_assessment": self.risk_assessment,
            "constraints_satisfied": self.constraints_satisfied,
            "constraint_violations": self.constraint_violations,
            "execution_time_ms": self.execution_time_ms,
            "created_at": self.created_at.isoformat(),
        }


class ScenarioOrchestratorCrew(BaseOptimizationCrew):
    """
    Master orchestrator crew that coordinates scenario execution across
    all optimization crews (Brand, RMN, Channel, Campaign).
    
    This crew:
    1. Analyzes current performance to recommend scenarios
    2. Executes user-selected scenarios by coordinating sub-crews
    3. Manages inter-crew messaging and information flow
    4. Aggregates outputs into unified recommendations
    """
    
    def __init__(
        self,
        config: CrewConfig,
        performance_data: Optional[Dict[str, Any]] = None,
        sub_crews: Optional[Dict[str, BaseOptimizationCrew]] = None,
    ):
        # Initialize messaging infrastructure
        self.message_bus = MessageBus()
        self.coordinator = CrossCrewCoordinator(self.message_bus)
        self.scenario_executor = ScenarioExecutor(self.message_bus, self.coordinator)
        
        # Sub-crews that this orchestrator coordinates
        self.sub_crews = sub_crews or {}
        
        # Active scenario context
        self._active_context: Optional[ScenarioExecutionContext] = None
        self._scenario_recommendations: List[ScenarioRecommendation] = []
        
        super().__init__(config, performance_data)
    
    @property
    def crew_type(self) -> str:
        return "scenario_orchestrator"
    
    def _setup_agents(self) -> None:
        """Define scenario orchestration agents."""
        
        self.agents["scenario_director"] = AgentDefinition(
            role="Scenario Director",
            goal="Orchestrate scenario execution across crews and make final optimization decisions",
            backstory="""You are the chief strategist responsible for orchestrating complex 
            optimization scenarios. You decide which crews to invoke, in what order, and how 
            to synthesize their outputs into actionable recommendations. You have deep 
            experience in retail media optimization and understand the tradeoffs between 
            growth, efficiency, and risk.""",
            agent_id="scenario_director",
            name="Scenario Director",
            tools=["crew_invoker_tool", "decision_framework_tool", "tradeoff_analyzer_tool"],
            allow_delegation=True,
            verbose=True,
        )
        
        self.agents["scenario_intake_analyst"] = AgentDefinition(
            role="Scenario Intake Analyst",
            goal="Analyze current state and recommend optimal scenarios based on triggers and objectives",
            backstory="""You analyze performance data to identify which business scenarios 
            are most relevant. You detect triggers like revenue decline, competitive threats, 
            or efficiency opportunities. You translate business objectives into scenario 
            recommendations with clear rationale.""",
            agent_id="scenario_intake_analyst",
            name="Scenario Intake Analyst",
            tools=["trigger_detector_tool", "scenario_matcher_tool", "state_analyzer_tool"],
        )
        
        self.agents["objective_router"] = AgentDefinition(
            role="Objective Router",
            goal="Configure objective functions and constraints for each scenario",
            backstory="""You translate business scenarios into mathematical optimization 
            parameters. You set objective weights, KPI floors, and constraint bounds based 
            on the selected scenario and user preferences. You ensure optimization is 
            aligned with business intent.""",
            agent_id="objective_router",
            name="Objective Router",
            tools=["objective_configurator_tool", "constraint_builder_tool"],
        )
        
        self.agents["crew_coordinator"] = AgentDefinition(
            role="Crew Coordinator",
            goal="Manage crew sequencing and inter-crew message passing",
            backstory="""You coordinate the execution of multiple optimization crews. 
            You determine the optimal sequence of crew execution, pass context between 
            crews, and ensure information flows correctly. You handle dependencies and 
            resolve conflicts between crew recommendations.""",
            agent_id="crew_coordinator",
            name="Crew Coordinator",
            tools=["crew_scheduler_tool", "message_router_tool", "dependency_resolver_tool"],
        )
        
        self.agents["response_curve_modeler"] = AgentDefinition(
            role="Response Curve Modeler",
            goal="Estimate marginal return curves and uncertainty bands from Bayesian posteriors",
            backstory="""You model how incremental spend translates to incremental outcomes. 
            You estimate response curves with uncertainty quantification and identify 
            diminishing returns thresholds. Your models inform optimal allocation decisions.""",
            agent_id="response_curve_modeler",
            name="Response Curve Modeler",
            tools=["curve_fitter_tool", "uncertainty_estimator_tool", "saturation_detector_tool"],
        )
        
        self.agents["optimization_solver"] = AgentDefinition(
            role="Optimization Solver",
            goal="Solve for optimal allocation given objectives and constraints",
            backstory="""You are the mathematical optimizer. You solve constrained 
            optimization problems to find allocations that maximize objectives while 
            respecting all constraints. You also compute shadow prices and sensitivity.""",
            agent_id="optimization_solver",
            name="Optimization Solver",
            tools=["solver_tool", "shadow_price_calculator_tool", "sensitivity_analyzer_tool"],
        )
        
        self.agents["sensitivity_robustness_analyst"] = AgentDefinition(
            role="Sensitivity & Robustness Analyst",
            goal="Stress-test recommendations and identify fragile allocations",
            backstory="""You test the robustness of optimization solutions. You run 
            sensitivity analyses to understand which assumptions are critical and 
            how recommendations change under different scenarios.""",
            agent_id="sensitivity_robustness_analyst",
            name="Sensitivity Analyst",
            tools=["sensitivity_tool", "stress_test_tool", "monte_carlo_tool"],
        )
        
        self.agents["scenario_comparator"] = AgentDefinition(
            role="Scenario Comparator",
            goal="Compare scenario outcomes and generate tradeoff narratives",
            backstory="""You compare multiple scenarios and explain tradeoffs. You 
            create clear comparisons showing the implications of different choices 
            and help stakeholders understand what they're optimizing for.""",
            agent_id="scenario_comparator",
            name="Scenario Comparator",
            tools=["comparison_generator_tool", "tradeoff_visualizer_tool"],
        )
        
        self.agents["evidence_synthesizer"] = AgentDefinition(
            role="Evidence Synthesizer",
            goal="Aggregate evidence from all crews into coherent decision support",
            backstory="""You synthesize evidence from multiple crews into a unified 
            narrative. You ensure all recommendations are backed by data and clearly 
            explain the reasoning chain that led to each decision.""",
            agent_id="evidence_synthesizer",
            name="Evidence Synthesizer",
            tools=["evidence_aggregator_tool", "narrative_generator_tool"],
        )
    
    def _setup_tasks(self) -> None:
        """Define scenario orchestration tasks."""
        
        self.tasks["analyze_state_and_triggers"] = TaskDefinition(
            task_id="analyze_state_and_triggers",
            description="""Analyze the current performance state and detect any scenario 
            triggers. Review recent performance trends, competitive signals, and constraint 
            status. Identify which scenarios are most relevant based on detected triggers.""",
            expected_output="""A list of detected triggers and matched scenarios with 
            confidence scores and rationale for each recommendation.""",
            agent_id="scenario_intake_analyst",
        )
        
        self.tasks["configure_scenario_objectives"] = TaskDefinition(
            task_id="configure_scenario_objectives",
            description="""Configure the objective function and constraints for the selected 
            scenario. Set primary and secondary objective weights, KPI floors/ceilings, 
            and risk parameters based on user preferences.""",
            expected_output="""Objective configuration with weights, constraints, and 
            optimization parameters ready for crew execution.""",
            agent_id="objective_router",
            context_tasks=["analyze_state_and_triggers"],
        )
        
        self.tasks["plan_crew_execution"] = TaskDefinition(
            task_id="plan_crew_execution",
            description="""Plan the execution sequence for required crews. Determine 
            which crews to invoke, in what order, and what context to pass between them.""",
            expected_output="""Crew execution plan with sequence, dependencies, and 
            context mapping.""",
            agent_id="crew_coordinator",
            context_tasks=["configure_scenario_objectives"],
        )
        
        self.tasks["execute_crews_and_aggregate"] = TaskDefinition(
            task_id="execute_crews_and_aggregate",
            description="""Execute the planned crews in sequence, passing context and 
            collecting outputs. Aggregate all crew recommendations into a unified view.""",
            expected_output="""Aggregated crew outputs with all recommendations, evidence, 
            and reasoning from each crew.""",
            agent_id="crew_coordinator",
            context_tasks=["plan_crew_execution"],
        )
        
        self.tasks["synthesize_evidence"] = TaskDefinition(
            task_id="synthesize_evidence",
            description="""Synthesize evidence from all crews into coherent decision 
            support. Create the reasoning chain and evidence trail.""",
            expected_output="""Synthesized evidence with reasoning chain and confidence 
            metrics.""",
            agent_id="evidence_synthesizer",
            context_tasks=["execute_crews_and_aggregate"],
        )
        
        self.tasks["stress_test_recommendations"] = TaskDefinition(
            task_id="stress_test_recommendations",
            description="""Stress-test the aggregated recommendations. Identify fragile 
            assumptions and sensitivity to key parameters.""",
            expected_output="""Robustness assessment with sensitivity analysis and risk 
            identification.""",
            agent_id="sensitivity_robustness_analyst",
            context_tasks=["synthesize_evidence"],
        )
        
        self.tasks["finalize_decision_pack"] = TaskDefinition(
            task_id="finalize_decision_pack",
            description="""Finalize the decision pack with executive summary, recommended 
            actions, evidence, and risk assessment. Ensure all recommendations are 
            actionable and clearly explained.""",
            expected_output="""Complete decision pack ready for stakeholder review.""",
            agent_id="scenario_director",
            context_tasks=["stress_test_recommendations"],
        )
    
    def register_sub_crew(
        self,
        crew_id: str,
        crew: BaseOptimizationCrew,
    ) -> None:
        """Register a sub-crew for orchestration."""
        self.sub_crews[crew_id] = crew
        logger.info(f"Registered sub-crew: {crew_id}")
    
    def analyze_and_recommend_scenarios(
        self,
        current_state: Dict[str, Any],
    ) -> List[ScenarioRecommendation]:
        """
        Analyze current state and generate scenario recommendations.
        This is the agent-generated scenario recommendation system.
        """
        recommendations = []
        priority = 1
        
        # Extract key metrics from current state
        revenue_trend = current_state.get("revenue_trend", 0)
        efficiency_trend = current_state.get("efficiency_trend", 0)
        margin_trend = current_state.get("margin_trend", 0)
        competitive_pressure = current_state.get("competitive_pressure", 0)
        uncertainty_level = current_state.get("uncertainty_level", 0.5)
        budget_utilization = current_state.get("budget_utilization", 1.0)
        
        # Detect triggers and recommend scenarios
        
        # Revenue growth opportunity
        if revenue_trend > 0.05:
            scenario = get_scenario("grow_revenue_brand")
            if scenario:
                recommendations.append(ScenarioRecommendation(
                    scenario_id="grow_revenue_brand",
                    scenario_name=scenario.name,
                    confidence=0.85,
                    rationale="Positive revenue trend detected - opportunity to scale winners",
                    expected_impact=current_state.get("total_spend", 1000000) * 0.12,
                    risk_level="LOW",
                    triggers_detected=["positive_revenue_trend"],
                    priority=priority,
                ))
                priority += 1
        
        # Revenue decline risk
        if revenue_trend < -0.05:
            scenario = get_scenario("prevent_decline")
            if scenario:
                recommendations.append(ScenarioRecommendation(
                    scenario_id="prevent_decline",
                    scenario_name=scenario.name,
                    confidence=0.90,
                    rationale="Revenue decline detected - defensive optimization needed",
                    expected_impact=abs(revenue_trend) * current_state.get("total_spend", 1000000),
                    risk_level="HIGH",
                    triggers_detected=["negative_revenue_trend", "decline_risk"],
                    priority=priority,
                ))
                priority += 1
        
        # Efficiency opportunity
        if efficiency_trend < 0:
            scenario = get_scenario("reduce_cost")
            if scenario:
                recommendations.append(ScenarioRecommendation(
                    scenario_id="reduce_cost",
                    scenario_name=scenario.name,
                    confidence=0.80,
                    rationale="Efficiency declining - cost optimization recommended",
                    expected_impact=current_state.get("total_spend", 1000000) * 0.08,
                    risk_level="MODERATE",
                    triggers_detected=["efficiency_decline"],
                    priority=priority,
                ))
                priority += 1
        
        # Margin pressure
        if margin_trend < -0.03:
            scenario = get_scenario("grow_margin")
            if scenario:
                recommendations.append(ScenarioRecommendation(
                    scenario_id="grow_margin",
                    scenario_name=scenario.name,
                    confidence=0.82,
                    rationale="Margin compression detected - profit optimization needed",
                    expected_impact=current_state.get("total_spend", 1000000) * 0.10,
                    risk_level="MODERATE",
                    triggers_detected=["margin_compression"],
                    priority=priority,
                ))
                priority += 1
        
        # Competitive threat
        if competitive_pressure > 0.7:
            scenario = get_scenario("defend_share")
            if scenario:
                recommendations.append(ScenarioRecommendation(
                    scenario_id="defend_share",
                    scenario_name=scenario.name,
                    confidence=0.88,
                    rationale="High competitive pressure - share defense recommended",
                    expected_impact=current_state.get("total_spend", 1000000) * 0.15,
                    risk_level="HIGH",
                    triggers_detected=["competitive_pressure"],
                    priority=priority,
                ))
                priority += 1
        
        # High uncertainty
        if uncertainty_level > 0.7:
            scenario = get_scenario("risk_minimized")
            if scenario:
                recommendations.append(ScenarioRecommendation(
                    scenario_id="risk_minimized",
                    scenario_name=scenario.name,
                    confidence=0.85,
                    rationale="High uncertainty environment - risk-minimized approach recommended",
                    expected_impact=0,
                    risk_level="LOW",
                    triggers_detected=["high_uncertainty"],
                    priority=priority,
                ))
                priority += 1
        
        # Learning opportunity
        if uncertainty_level > 0.5 and budget_utilization < 0.9:
            scenario = get_scenario("explore_exploit")
            if scenario:
                recommendations.append(ScenarioRecommendation(
                    scenario_id="explore_exploit",
                    scenario_name=scenario.name,
                    confidence=0.78,
                    rationale="Opportunity to reduce uncertainty through exploration",
                    expected_impact=current_state.get("total_spend", 1000000) * 0.05,
                    risk_level="MODERATE",
                    triggers_detected=["exploration_opportunity"],
                    priority=priority,
                ))
                priority += 1
        
        # Default: stability
        if not recommendations:
            scenario = get_scenario("maintain_revenue")
            if scenario:
                recommendations.append(ScenarioRecommendation(
                    scenario_id="maintain_revenue",
                    scenario_name=scenario.name,
                    confidence=0.75,
                    rationale="Stable environment - maintenance mode recommended",
                    expected_impact=0,
                    risk_level="LOW",
                    triggers_detected=["stable_state"],
                    priority=priority,
                ))
        
        # Sort by priority (already assigned in order of importance)
        self._scenario_recommendations = sorted(recommendations, key=lambda x: x.priority)
        return self._scenario_recommendations
    
    def execute_scenario(
        self,
        context: ScenarioExecutionContext,
    ) -> OrchestratorOutput:
        """
        Execute a scenario across all required crews.
        
        This is the main entry point for scenario execution, supporting both
        user-selected and agent-recommended scenarios.
        """
        start_time = datetime.now()
        self._active_context = context
        
        logger.info(f"Executing scenario: {context.scenario.name} ({context.selection_mode.value})")
        
        # Configure constraints from scenario and user parameters
        effective_constraints = self._build_effective_constraints(context)
        
        # Start coordination
        coordination_id = self.coordinator.start_scenario_coordination(
            scenario_id=context.scenario.scenario_id,
            scenario_name=context.scenario.name,
            crew_sequence=context.scenario.crew_sequence,
            initial_context={
                "session_id": context.session_id,
                "brand_id": context.brand_id,
                "risk_appetite": context.risk_appetite.value,
                "current_state": context.current_state,
                "constraints": effective_constraints.to_dict(),
                "user_parameters": context.user_parameters,
            },
        )
        
        # Execute crews in sequence
        crew_outputs: Dict[str, CrewOutput] = {}
        aggregated_context = dict(context.current_state)
        
        for crew_id in context.scenario.crew_sequence:
            logger.info(f"Executing crew: {crew_id}")
            
            # Check if we have a registered sub-crew
            if crew_id in self.sub_crews:
                # Execute real crew
                crew = self.sub_crews[crew_id]
                
                # Update crew config with scenario parameters
                crew.config.desired_outcome = self._map_scenario_to_outcome(context.scenario)
                crew.config.constraints = self._map_to_optimization_constraints(effective_constraints)
                crew.performance_data = aggregated_context
                
                crew_output = crew.run()
                crew_outputs[crew_id] = crew_output
                
                # Update context with crew results
                aggregated_context[f"{crew_id}_output"] = {
                    "recommendations": [a.__dict__ for a in crew_output.allocations],
                    "key_findings": crew_output.key_findings,
                    "opportunities": crew_output.opportunities,
                    "risks": crew_output.risks,
                }
            else:
                # Simulate crew execution
                crew_outputs[crew_id] = self._simulate_crew_execution(
                    crew_id, context, effective_constraints, aggregated_context
                )
            
            # Notify coordinator
            self.coordinator.advance_scenario(
                coordination_id,
                {
                    "crew_id": crew_id,
                    "success": True,
                    "updates": {f"{crew_id}_completed": True},
                },
            )
            
            # Send inter-crew message for next crew
            if crew_id != context.scenario.crew_sequence[-1]:
                next_idx = context.scenario.crew_sequence.index(crew_id) + 1
                next_crew = context.scenario.crew_sequence[next_idx]
                
                self._send_inter_crew_message(
                    source_crew=crew_id,
                    target_crew=next_crew,
                    scenario_id=context.scenario.scenario_id,
                    context=aggregated_context,
                )
        
        # Aggregate results
        output = self._aggregate_crew_outputs(
            context=context,
            crew_outputs=crew_outputs,
            coordination_id=coordination_id,
            start_time=start_time,
        )
        
        self._active_context = None
        return output
    
    def _build_effective_constraints(
        self,
        context: ScenarioExecutionContext,
    ) -> ScenarioConstraints:
        """Build effective constraints from scenario defaults and user overrides."""
        base = context.scenario.default_constraints
        
        return ScenarioConstraints(
            spend_cap=context.user_parameters.get("spend_cap", base.spend_cap),
            spend_floor=context.user_parameters.get("spend_floor", base.spend_floor),
            revenue_floor=context.user_parameters.get("revenue_floor", base.revenue_floor),
            roas_floor=context.user_parameters.get("roas_floor", base.roas_floor),
            max_reallocation_pct=context.max_reallocation_pct,
            exploration_budget_pct=context.exploration_budget_pct,
            rmn_minimums=context.user_parameters.get("rmn_minimums", base.rmn_minimums),
            channel_minimums=context.user_parameters.get("channel_minimums", base.channel_minimums),
            min_presence_by_rmn=base.min_presence_by_rmn,
            inventory_aware=base.inventory_aware,
        )
    
    def _map_scenario_to_outcome(
        self,
        scenario: BusinessScenario,
    ) -> DesiredOutcome:
        """Map scenario objective to DesiredOutcome enum."""
        objective = scenario.objective_type.value
        
        if "incremental_sales" in objective or "new_to_brand" in objective:
            return DesiredOutcome.INCREASE_REVENUE
        elif "incremental_profit" in objective:
            return DesiredOutcome.INCREASE_MARGIN
        elif "efficiency" in objective:
            return DesiredOutcome.REDUCE_COST
        elif "stability" in objective or "decline" in objective:
            return DesiredOutcome.MAINTAIN_REVENUE
        else:
            return DesiredOutcome.INCREASE_REVENUE
    
    def _map_to_optimization_constraints(
        self,
        scenario_constraints: ScenarioConstraints,
    ) -> OptimizationConstraints:
        """Map ScenarioConstraints to OptimizationConstraints."""
        return OptimizationConstraints(
            budget=scenario_constraints.spend_cap or 10_000_000,
            revenue_floor=scenario_constraints.revenue_floor or 0,
            max_allocation_change_pct=scenario_constraints.max_reallocation_pct,
            channel_floors=scenario_constraints.channel_minimums,
            channel_ceilings=scenario_constraints.channel_maximums,
        )
    
    def _simulate_crew_execution(
        self,
        crew_id: str,
        context: ScenarioExecutionContext,
        constraints: ScenarioConstraints,
        current_context: Dict[str, Any],
    ) -> CrewOutput:
        """Simulate crew execution when no real crew is available."""
        import random
        
        crew_type = crew_id.replace("_optimization", "")
        
        # Generate simulated allocations
        allocations = []
        entities = [f"{crew_type}_entity_{i}" for i in range(1, 4)]
        
        for i, entity in enumerate(entities):
            current = random.uniform(200000, 800000)
            delta_pct = random.uniform(-constraints.max_reallocation_pct, constraints.max_reallocation_pct)
            recommended = current * (1 + delta_pct)
            
            allocations.append(AllocationRecommendation(
                entity_id=entity,
                entity_type=crew_type,
                entity_name=f"{crew_type.title()} {i+1}",
                current_spend=current,
                recommended_spend=recommended,
                spend_delta=recommended - current,
                spend_delta_pct=delta_pct,
                expected_incremental_sales=abs(recommended - current) * random.uniform(1.2, 2.0),
                expected_efficiency=random.uniform(1.1, 2.2),
                confidence=random.uniform(0.75, 0.95),
                rationale=f"Based on {crew_type} level optimization",
            ))
        
        return CrewOutput(
            crew_id=crew_id,
            crew_type=crew_id,
            desired_outcome=context.scenario.objective_type.value,
            executive_summary=f"{crew_id} optimization completed for {context.scenario.name}",
            key_findings=[
                f"Found {len(allocations)} optimization opportunities at {crew_type} level",
                f"Average confidence: {sum(a.confidence for a in allocations)/len(allocations):.0%}",
            ],
            opportunities=[
                f"Scale high-performers at {crew_type} level",
                f"Reduce underperforming {crew_type} allocations",
            ],
            risks=[
                "Response curve uncertainty",
                "Competitive dynamics may shift",
            ],
            allocations=allocations,
            total_recommended_spend=sum(a.recommended_spend for a in allocations),
            expected_incremental_sales=sum(a.expected_incremental_sales for a in allocations),
            expected_efficiency=sum(a.expected_efficiency * a.recommended_spend for a in allocations) / max(1, sum(a.recommended_spend for a in allocations)),
            constraints_satisfied=True,
            constraint_violations=[],
        )
    
    def _send_inter_crew_message(
        self,
        source_crew: str,
        target_crew: str,
        scenario_id: str,
        context: Dict[str, Any],
    ) -> None:
        """Send a message from one crew to another."""
        try:
            source_type = CrewType(source_crew)
            target_type = CrewType(target_crew)
        except ValueError:
            # If crew types don't match enum, skip messaging
            return
        
        msg = CrewMessage.create_notification(
            source=source_type,
            target=target_type,
            subject=f"Context handoff for scenario {scenario_id}",
            payload={
                "upstream_context": context,
                "scenario_id": scenario_id,
            },
            scenario_id=scenario_id,
        )
        self.message_bus.send(msg)
    
    def _aggregate_crew_outputs(
        self,
        context: ScenarioExecutionContext,
        crew_outputs: Dict[str, CrewOutput],
        coordination_id: str,
        start_time: datetime,
    ) -> OrchestratorOutput:
        """Aggregate outputs from all crews into unified recommendation."""
        
        # Collect all recommendations
        all_recommendations = []
        priority = 1
        for crew_id, output in crew_outputs.items():
            for alloc in output.allocations:
                all_recommendations.append({
                    "priority": priority,
                    "source_crew": crew_id,
                    "entity_id": alloc.entity_id,
                    "entity_type": alloc.entity_type,
                    "entity_name": alloc.entity_name,
                    "action": "increase" if alloc.spend_delta > 0 else "decrease",
                    "current_value": alloc.current_spend,
                    "recommended_value": alloc.recommended_spend,
                    "delta": alloc.spend_delta,
                    "delta_pct": alloc.spend_delta_pct,
                    "expected_impact": alloc.expected_incremental_sales,
                    "confidence": alloc.confidence,
                    "rationale": alloc.rationale,
                })
                priority += 1
        
        # Collect evidence
        evidence = []
        for crew_id, output in crew_outputs.items():
            evidence.append({
                "source": crew_id,
                "type": "crew_analysis",
                "findings": output.key_findings,
                "opportunities": output.opportunities,
                "risks": output.risks,
                "confidence": sum(a.confidence for a in output.allocations) / max(1, len(output.allocations)),
            })
        
        # Build reasoning chain
        reasoning_steps = []
        for i, (crew_id, output) in enumerate(crew_outputs.items()):
            reasoning_steps.append({
                "step_number": i + 1,
                "crew_id": crew_id,
                "action": f"Optimized {crew_id.replace('_optimization', '')} level",
                "output_summary": output.executive_summary,
                "key_findings": output.key_findings,
                "confidence": sum(a.confidence for a in output.allocations) / max(1, len(output.allocations)),
            })
        
        # Calculate aggregates
        total_impact = sum(r["expected_impact"] for r in all_recommendations)
        avg_confidence = sum(r["confidence"] for r in all_recommendations) / max(1, len(all_recommendations))
        
        # Check constraints
        all_satisfied = all(o.constraints_satisfied for o in crew_outputs.values())
        all_violations = []
        for o in crew_outputs.values():
            all_violations.extend(o.constraint_violations)
        
        # Risk assessment
        if avg_confidence > 0.85:
            risk_level = "LOW"
        elif avg_confidence > 0.70:
            risk_level = "MODERATE"
        else:
            risk_level = "HIGH"
        
        execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        # Executive summary
        exec_summary = (
            f"Executed '{context.scenario.name}' scenario across {len(crew_outputs)} crews. "
            f"Generated {len(all_recommendations)} recommendations with expected impact of "
            f"${total_impact:,.0f}. Overall confidence: {avg_confidence:.0%}. "
            f"Risk level: {risk_level}."
        )
        
        return OrchestratorOutput(
            session_id=context.session_id,
            scenario_id=context.scenario.scenario_id,
            scenario_name=context.scenario.name,
            selection_mode=context.selection_mode.value,
            crews_executed=list(crew_outputs.keys()),
            crew_outputs={k: v.__dict__ for k, v in crew_outputs.items()},
            aggregated_recommendations=all_recommendations,
            supporting_evidence=evidence,
            reasoning_chain={
                "steps": reasoning_steps,
                "crews_involved": list(crew_outputs.keys()),
                "cross_crew_messages": self.coordinator.get_cross_crew_messages(context.scenario.scenario_id),
            },
            executive_summary=exec_summary,
            total_expected_impact=total_impact,
            overall_confidence=avg_confidence,
            risk_assessment=f"{risk_level} RISK: {avg_confidence:.0%} confidence with {context.risk_appetite.value} risk appetite",
            constraints_satisfied=all_satisfied,
            constraint_violations=all_violations,
            execution_time_ms=execution_time,
        )
    
    # Required abstract method implementations
    
    def ingest_and_validate(self) -> Dict[str, Any]:
        """Validate scenario execution inputs."""
        if not self._active_context:
            return {"valid": False, "issues": ["No active scenario context"]}
        
        issues = []
        if not self._active_context.scenario:
            issues.append("No scenario selected")
        if not self._active_context.scenario.crew_sequence:
            issues.append("Scenario has no crew sequence defined")
        
        return {"valid": len(issues) == 0, "issues": issues}
    
    def diagnose(self) -> Dict[str, Any]:
        """Analyze current state for scenario execution."""
        if not self._active_context:
            return {}
        
        return {
            "scenario_id": self._active_context.scenario.scenario_id,
            "objective_type": self._active_context.scenario.objective_type.value,
            "required_crews": self._active_context.scenario.crew_sequence,
            "risk_appetite": self._active_context.risk_appetite.value,
            "current_state_summary": {
                k: type(v).__name__ for k, v in self._active_context.current_state.items()
            },
        }
    
    def optimize(self, diagnosis: Dict[str, Any]) -> OptimizationResult:
        """Orchestrator doesn't directly optimize - it coordinates crews."""
        return OptimizationResult(
            success=True,
            solver_status="delegated_to_crews",
            solver_message="Optimization delegated to sub-crews",
            optimal_allocation={},
        )
    
    def explain(
        self,
        diagnosis: Dict[str, Any],
        optimization_result: OptimizationResult
    ) -> CrewOutput:
        """Generate explanation - delegated to sub-crews."""
        return CrewOutput(
            crew_id=self.config.crew_id,
            crew_type=self.crew_type,
            desired_outcome=self._active_context.scenario.objective_type.value if self._active_context else "",
            executive_summary="Scenario execution coordinated across sub-crews",
            key_findings=[],
            opportunities=[],
            risks=[],
            allocations=[],
        )


def create_orchestrator(
    config: Optional[CrewConfig] = None,
) -> ScenarioOrchestratorCrew:
    """Factory function to create a configured scenario orchestrator."""
    if not config:
        config = CrewConfig(
            crew_id="scenario_orchestrator",
            desired_outcome=DesiredOutcome.INCREASE_REVENUE,
            constraints=OptimizationConstraints(),
        )
    return ScenarioOrchestratorCrew(config)
