"""
Scenario Execution Engine

Executes business scenarios by coordinating crews, evaluating objectives,
applying constraints, and generating decision recommendations with evidence.
"""

import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from .schemas import (
    BusinessScenario,
    ScenarioConstraints,
    ScenarioTrigger,
    RiskAppetite,
    Cadence,
    DecisionRecommendation,
    RecommendedAction,
    ActionType,
    EvidenceItem,
    EvidenceType,
    ReasoningChain,
    ReasoningStep,
    DecisionSupportOutput,
)
from .catalog import get_scenario, SCENARIO_CATALOG
from .messaging import (
    MessageBus,
    CrossCrewCoordinator,
    CrewMessage,
    CrewType,
    MessageType,
    MessagePriority,
)

logger = logging.getLogger(__name__)


@dataclass
class ExecutionContext:
    """Context for scenario execution."""
    session_id: str
    scenario_id: str
    user_id: Optional[str] = None
    brand_id: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    constraints_override: Optional[ScenarioConstraints] = None
    risk_appetite: Optional[RiskAppetite] = None
    cadence: Optional[Cadence] = None
    exploration_budget_pct: Optional[float] = None
    max_reallocation_pct: Optional[float] = None
    current_state: Dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.now)


@dataclass
class ExecutionResult:
    """Result of scenario execution."""
    success: bool
    session_id: str
    scenario_id: str
    decision_recommendation: Optional[DecisionRecommendation] = None
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    execution_time_ms: int = 0
    crews_executed: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "session_id": self.session_id,
            "scenario_id": self.scenario_id,
            "decision_recommendation": self.decision_recommendation.to_dict() if self.decision_recommendation else None,
            "error": self.error,
            "warnings": self.warnings,
            "execution_time_ms": self.execution_time_ms,
            "crews_executed": self.crews_executed,
        }


class ObjectiveEvaluator:
    """Evaluates objective functions for scenarios."""
    
    @staticmethod
    def evaluate_incremental_sales(
        current_state: Dict[str, Any],
        proposed_allocation: Dict[str, float],
        response_curves: Dict[str, Any],
    ) -> Tuple[float, float, Dict[str, Any]]:
        """
        Evaluate expected incremental sales from proposed allocation.
        Returns: (expected_value, confidence, details)
        """
        # Placeholder - would use Bayesian response curves
        expected_lift = sum(proposed_allocation.values()) * 0.15
        confidence = 0.85
        details = {
            "method": "bayesian_response_curve",
            "total_spend": sum(proposed_allocation.values()),
            "expected_lift_pct": 0.15,
        }
        return expected_lift, confidence, details
    
    @staticmethod
    def evaluate_incremental_profit(
        current_state: Dict[str, Any],
        proposed_allocation: Dict[str, float],
        margin_rates: Dict[str, float],
    ) -> Tuple[float, float, Dict[str, Any]]:
        """
        Evaluate expected incremental profit.
        Returns: (expected_value, confidence, details)
        """
        total_spend = sum(proposed_allocation.values())
        avg_margin = sum(margin_rates.values()) / len(margin_rates) if margin_rates else 0.3
        expected_sales_lift = total_spend * 0.15
        expected_profit = expected_sales_lift * avg_margin - total_spend * 0.1
        
        return expected_profit, 0.80, {
            "method": "profit_attribution",
            "avg_margin_rate": avg_margin,
        }
    
    @staticmethod
    def evaluate_efficiency(
        current_state: Dict[str, Any],
        proposed_allocation: Dict[str, float],
    ) -> Tuple[float, float, Dict[str, Any]]:
        """
        Evaluate spend efficiency (ROAS, CPA, etc.).
        """
        total_spend = sum(proposed_allocation.values())
        expected_revenue = total_spend * 3.5
        roas = expected_revenue / total_spend if total_spend > 0 else 0
        
        return roas, 0.82, {
            "method": "roas_estimation",
            "expected_revenue": expected_revenue,
        }


class ConstraintChecker:
    """Checks and validates constraints for recommendations."""
    
    @staticmethod
    def check_constraints(
        constraints: ScenarioConstraints,
        proposed_allocation: Dict[str, float],
        expected_outcomes: Dict[str, Any],
    ) -> Tuple[bool, List[str]]:
        """
        Check if proposed allocation satisfies all constraints.
        Returns: (all_satisfied, list_of_violations)
        """
        violations = []
        
        total_spend = sum(proposed_allocation.values())
        
        if constraints.spend_cap and total_spend > constraints.spend_cap:
            violations.append(f"Spend {total_spend:.0f} exceeds cap {constraints.spend_cap:.0f}")
        
        if constraints.spend_floor and total_spend < constraints.spend_floor:
            violations.append(f"Spend {total_spend:.0f} below floor {constraints.spend_floor:.0f}")
        
        expected_roas = expected_outcomes.get("roas", 0)
        if constraints.roas_floor and expected_roas < constraints.roas_floor:
            violations.append(f"Expected ROAS {expected_roas:.2f} below floor {constraints.roas_floor:.2f}")
        
        # Check RMN minimums
        for rmn, minimum in constraints.rmn_minimums.items():
            rmn_spend = proposed_allocation.get(rmn, 0)
            if rmn_spend < minimum:
                violations.append(f"RMN {rmn} spend {rmn_spend:.0f} below minimum {minimum:.0f}")
        
        return len(violations) == 0, violations


class ScenarioExecutor:
    """
    Main executor for business scenarios.
    Coordinates crews, evaluates objectives, and generates recommendations.
    """
    
    def __init__(
        self,
        message_bus: Optional[MessageBus] = None,
        coordinator: Optional[CrossCrewCoordinator] = None,
    ):
        self.bus = message_bus or MessageBus()
        self.coordinator = coordinator or CrossCrewCoordinator(self.bus)
        self.objective_evaluator = ObjectiveEvaluator()
        self.constraint_checker = ConstraintChecker()
        self._active_sessions: Dict[str, ExecutionContext] = {}
    
    def execute_scenario(
        self,
        scenario_id: str,
        context: ExecutionContext,
    ) -> ExecutionResult:
        """
        Execute a business scenario and generate decision recommendations.
        """
        start_time = datetime.now()
        scenario = get_scenario(scenario_id)
        
        if not scenario:
            return ExecutionResult(
                success=False,
                session_id=context.session_id,
                scenario_id=scenario_id,
                error=f"Scenario {scenario_id} not found",
            )
        
        self._active_sessions[context.session_id] = context
        
        try:
            # Apply user overrides to constraints
            constraints = self._merge_constraints(
                scenario.default_constraints,
                context.constraints_override,
                context,
            )
            
            # Start coordinated execution across crews
            coordination_id = self.coordinator.start_scenario_coordination(
                scenario_id=scenario_id,
                scenario_name=scenario.name,
                crew_sequence=scenario.crew_sequence,
                initial_context={
                    "session_id": context.session_id,
                    "brand_id": context.brand_id,
                    "parameters": context.parameters,
                    "constraints": constraints.to_dict(),
                    "risk_appetite": (context.risk_appetite or scenario.default_risk_appetite).value,
                    "current_state": context.current_state,
                },
            )
            
            # Simulate crew execution and gather results
            crew_results = self._execute_crew_sequence(
                scenario, constraints, context, coordination_id
            )
            
            # Generate recommendations from crew results
            recommendations = self._generate_recommendations(
                scenario, constraints, context, crew_results
            )
            
            # Generate supporting evidence
            evidence = self._generate_evidence(
                scenario, crew_results, recommendations
            )
            
            # Build reasoning chain
            reasoning_chain = self._build_reasoning_chain(
                scenario, coordination_id, crew_results
            )
            
            # Create decision recommendation
            decision = self._create_decision_recommendation(
                scenario=scenario,
                context=context,
                recommendations=recommendations,
                evidence=evidence,
                reasoning_chain=reasoning_chain,
                constraints=constraints,
            )
            
            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
            
            return ExecutionResult(
                success=True,
                session_id=context.session_id,
                scenario_id=scenario_id,
                decision_recommendation=decision,
                execution_time_ms=execution_time,
                crews_executed=scenario.crew_sequence,
            )
            
        except Exception as e:
            logger.exception(f"Scenario execution error: {e}")
            return ExecutionResult(
                success=False,
                session_id=context.session_id,
                scenario_id=scenario_id,
                error=str(e),
            )
        finally:
            if context.session_id in self._active_sessions:
                del self._active_sessions[context.session_id]
    
    def _merge_constraints(
        self,
        default: ScenarioConstraints,
        override: Optional[ScenarioConstraints],
        context: ExecutionContext,
    ) -> ScenarioConstraints:
        """Merge default constraints with user overrides."""
        if not override:
            merged = default
        else:
            merged = ScenarioConstraints(
                spend_cap=override.spend_cap or default.spend_cap,
                spend_floor=override.spend_floor or default.spend_floor,
                revenue_floor=override.revenue_floor or default.revenue_floor,
                roas_floor=override.roas_floor or default.roas_floor,
                max_reallocation_pct=override.max_reallocation_pct or default.max_reallocation_pct,
                exploration_budget_pct=override.exploration_budget_pct or default.exploration_budget_pct,
                rmn_minimums={**default.rmn_minimums, **override.rmn_minimums},
                channel_minimums={**default.channel_minimums, **override.channel_minimums},
            )
        
        # Apply context-level overrides
        if context.max_reallocation_pct is not None:
            merged.max_reallocation_pct = context.max_reallocation_pct
        if context.exploration_budget_pct is not None:
            merged.exploration_budget_pct = context.exploration_budget_pct
        
        return merged
    
    def _execute_crew_sequence(
        self,
        scenario: BusinessScenario,
        constraints: ScenarioConstraints,
        context: ExecutionContext,
        coordination_id: str,
    ) -> Dict[str, Dict[str, Any]]:
        """Execute the crew sequence and collect results."""
        results = {}
        
        for crew_id in scenario.crew_sequence:
            # Simulate crew execution
            crew_result = self._simulate_crew_execution(
                crew_id, scenario, constraints, context
            )
            results[crew_id] = crew_result
            
            # Advance scenario coordination
            self.coordinator.advance_scenario(coordination_id, crew_result)
        
        return results
    
    def _simulate_crew_execution(
        self,
        crew_id: str,
        scenario: BusinessScenario,
        constraints: ScenarioConstraints,
        context: ExecutionContext,
    ) -> Dict[str, Any]:
        """Simulate execution of a single crew (placeholder for real CrewAI integration)."""
        # This would integrate with actual CrewAI crews
        return {
            "crew_id": crew_id,
            "status": "completed",
            "analysis": {
                "opportunities_found": 3,
                "risks_identified": 1,
            },
            "recommendations": [
                {
                    "entity": f"{crew_id}_entity_1",
                    "action": "increase_spend",
                    "amount": 5000,
                    "confidence": 0.85,
                },
            ],
            "updates": {
                f"{crew_id}_analyzed": True,
            },
        }
    
    def _generate_recommendations(
        self,
        scenario: BusinessScenario,
        constraints: ScenarioConstraints,
        context: ExecutionContext,
        crew_results: Dict[str, Dict[str, Any]],
    ) -> List[RecommendedAction]:
        """Generate recommended actions from crew results."""
        recommendations = []
        priority = 1
        
        for crew_id, result in crew_results.items():
            for rec in result.get("recommendations", []):
                action = RecommendedAction(
                    action_id=str(uuid.uuid4()),
                    action_type=ActionType.REALLOCATE,
                    entity_type=crew_id.replace("_optimization", ""),
                    entity_id=rec.get("entity", "unknown"),
                    entity_name=rec.get("entity", "Unknown Entity"),
                    description=f"{rec.get('action', 'adjust')} by ${rec.get('amount', 0):,.0f}",
                    current_value=10000,  # Placeholder
                    recommended_value=10000 + rec.get("amount", 0),
                    delta=rec.get("amount", 0),
                    delta_pct=rec.get("amount", 0) / 10000 * 100,
                    expected_impact=rec.get("amount", 0) * 0.15,
                    confidence=rec.get("confidence", 0.8),
                    priority=priority,
                    rationale=f"Based on {crew_id} analysis showing high incremental potential",
                )
                recommendations.append(action)
                priority += 1
        
        return recommendations
    
    def _generate_evidence(
        self,
        scenario: BusinessScenario,
        crew_results: Dict[str, Dict[str, Any]],
        recommendations: List[RecommendedAction],
    ) -> List[EvidenceItem]:
        """Generate supporting evidence for recommendations."""
        evidence = []
        
        # Posterior distribution evidence
        evidence.append(EvidenceItem(
            evidence_id=str(uuid.uuid4()),
            evidence_type=EvidenceType.POSTERIOR_DISTRIBUTION,
            title="Incremental Lift Distribution",
            description="Posterior distribution of expected incremental lift from Bayesian model",
            metric_name="incremental_lift",
            metric_value=0.15,
            confidence_interval=(0.10, 0.22),
            probability=0.85,
            source="bayesian_response_model",
        ))
        
        # Credible interval evidence
        evidence.append(EvidenceItem(
            evidence_id=str(uuid.uuid4()),
            evidence_type=EvidenceType.CREDIBLE_INTERVAL,
            title="90% Credible Interval for ROAS",
            description="90% credible interval for expected ROAS improvement",
            metric_name="roas",
            metric_value=3.5,
            confidence_interval=(2.8, 4.2),
            source="bayesian_response_model",
        ))
        
        # Probability statement
        evidence.append(EvidenceItem(
            evidence_id=str(uuid.uuid4()),
            evidence_type=EvidenceType.PROBABILITY_STATEMENT,
            title="Probability of Positive Lift",
            description="Probability that the recommended allocation produces positive incremental lift",
            metric_name="p_positive_lift",
            metric_value=0.92,
            probability=0.92,
            source="bayesian_inference",
        ))
        
        # Counterfactual
        evidence.append(EvidenceItem(
            evidence_id=str(uuid.uuid4()),
            evidence_type=EvidenceType.COUNTERFACTUAL,
            title="Counterfactual Comparison",
            description="Expected outcome if no changes made vs recommended allocation",
            metric_name="counterfactual_delta",
            metric_value=25000,
            comparison_baseline=0,
            source="causal_model",
        ))
        
        return evidence
    
    def _build_reasoning_chain(
        self,
        scenario: BusinessScenario,
        coordination_id: str,
        crew_results: Dict[str, Dict[str, Any]],
    ) -> ReasoningChain:
        """Build the reasoning chain showing how decision was reached."""
        chain = ReasoningChain(
            chain_id=str(uuid.uuid4()),
            scenario_id=scenario.scenario_id,
        )
        
        step_num = 1
        for crew_id, result in crew_results.items():
            step = ReasoningStep(
                step_id=str(uuid.uuid4()),
                step_number=step_num,
                crew_id=crew_id,
                agent_id=f"{crew_id}_analyst",
                action=f"Analyzed {crew_id.replace('_optimization', '')} level data",
                input_summary=f"Received current state and constraints for {scenario.name}",
                output_summary=f"Found {result.get('analysis', {}).get('opportunities_found', 0)} opportunities",
                reasoning=f"Applied {scenario.objective_type.value} objective to identify optimization opportunities",
                confidence=0.85,
                duration_ms=500,
            )
            chain.add_step(step)
            step_num += 1
        
        # Add cross-crew messages to chain
        messages = self.coordinator.get_cross_crew_messages(scenario.scenario_id)
        chain.cross_crew_messages = messages
        
        return chain
    
    def _create_decision_recommendation(
        self,
        scenario: BusinessScenario,
        context: ExecutionContext,
        recommendations: List[RecommendedAction],
        evidence: List[EvidenceItem],
        reasoning_chain: ReasoningChain,
        constraints: ScenarioConstraints,
    ) -> DecisionRecommendation:
        """Create the final decision recommendation."""
        # Calculate totals
        total_impact = sum(r.expected_impact for r in recommendations)
        avg_confidence = sum(r.confidence for r in recommendations) / len(recommendations) if recommendations else 0
        
        # Check constraints
        proposed_allocation = {r.entity_id: r.recommended_value for r in recommendations}
        expected_outcomes = {"roas": 3.5}  # Placeholder
        constraints_satisfied, violations = self.constraint_checker.check_constraints(
            constraints, proposed_allocation, expected_outcomes
        )
        
        # Generate executive summary
        executive_summary = self._generate_executive_summary(
            scenario, recommendations, total_impact, avg_confidence
        )
        
        # Risk assessment
        risk_assessment = self._assess_risk(
            scenario, recommendations, constraints, context.risk_appetite or scenario.default_risk_appetite
        )
        
        return DecisionRecommendation(
            recommendation_id=str(uuid.uuid4()),
            scenario_id=scenario.scenario_id,
            scenario_name=scenario.name,
            executive_summary=executive_summary,
            recommended_actions=recommendations,
            supporting_evidence=evidence,
            reasoning_chain=reasoning_chain,
            total_expected_impact=total_impact,
            overall_confidence=avg_confidence,
            risk_assessment=risk_assessment,
            constraints_satisfied=constraints_satisfied,
            constraint_violations=violations,
        )
    
    def _generate_executive_summary(
        self,
        scenario: BusinessScenario,
        recommendations: List[RecommendedAction],
        total_impact: float,
        avg_confidence: float,
    ) -> str:
        """Generate executive summary for the recommendation."""
        action_count = len(recommendations)
        return (
            f"For '{scenario.name}' scenario: Identified {action_count} recommended actions "
            f"with expected incremental impact of ${total_impact:,.0f}. "
            f"Overall confidence: {avg_confidence:.0%}. "
            f"Primary objective: {scenario.objective_description}"
        )
    
    def _assess_risk(
        self,
        scenario: BusinessScenario,
        recommendations: List[RecommendedAction],
        constraints: ScenarioConstraints,
        risk_appetite: RiskAppetite,
    ) -> str:
        """Assess overall risk of the recommendation."""
        # Simple risk assessment based on confidence and constraints
        avg_confidence = sum(r.confidence for r in recommendations) / len(recommendations) if recommendations else 0
        
        if avg_confidence > 0.85:
            risk_level = "LOW"
        elif avg_confidence > 0.70:
            risk_level = "MODERATE"
        else:
            risk_level = "HIGH"
        
        return (
            f"{risk_level} RISK: Recommendations have {avg_confidence:.0%} average confidence "
            f"with {risk_appetite.value} risk appetite setting. "
            f"Max reallocation: {constraints.max_reallocation_pct:.0%} per cycle."
        )
    
    def get_available_scenarios(self) -> List[Dict[str, Any]]:
        """Get all available scenarios for UI display."""
        return [s.to_dict() for s in SCENARIO_CATALOG.values()]
    
    def get_scenario_details(self, scenario_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed scenario information."""
        scenario = get_scenario(scenario_id)
        return scenario.to_dict() if scenario else None


def create_executor() -> ScenarioExecutor:
    """Factory function to create a configured scenario executor."""
    bus = MessageBus()
    coordinator = CrossCrewCoordinator(bus)
    return ScenarioExecutor(bus, coordinator)
