"""
Crew Integration Module

Bridges the scenario execution system with the existing CrewAI-based
optimization crews (Brand, RMN, Channel, Campaign).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Type

from .schemas import (
    BusinessScenario,
    ScenarioConstraints,
    RiskAppetite,
    DecisionRecommendation,
    RecommendedAction,
    EvidenceItem,
    ReasoningChain,
    ReasoningStep,
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
class CrewExecutionRequest:
    """Request to execute a crew as part of a scenario."""
    crew_id: str
    scenario_id: str
    context: Dict[str, Any]
    constraints: ScenarioConstraints
    risk_appetite: RiskAppetite
    upstream_results: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CrewExecutionResult:
    """Result from a crew execution."""
    crew_id: str
    success: bool
    analysis: Dict[str, Any]
    recommendations: List[Dict[str, Any]]
    evidence: List[Dict[str, Any]]
    reasoning: str
    confidence: float
    duration_ms: int
    error: Optional[str] = None


class CrewAdapter:
    """
    Adapter that wraps existing crew classes to work with the scenario system.
    Provides a unified interface for scenario execution.
    """
    
    def __init__(self, crew_id: str, crew_class: Optional[Type] = None):
        self.crew_id = crew_id
        self.crew_class = crew_class
        self._instance = None
    
    def initialize(self, config: Dict[str, Any]) -> None:
        """Initialize the crew with configuration."""
        if self.crew_class:
            self._instance = self.crew_class(config=config)
    
    def execute(self, request: CrewExecutionRequest) -> CrewExecutionResult:
        """Execute the crew for a scenario."""
        start_time = datetime.now()
        
        try:
            # If we have a real crew instance, use it
            if self._instance:
                result = self._instance.run(
                    context=request.context,
                    constraints=request.constraints,
                )
                return CrewExecutionResult(
                    crew_id=self.crew_id,
                    success=True,
                    analysis=result.get("analysis", {}),
                    recommendations=result.get("recommendations", []),
                    evidence=result.get("evidence", []),
                    reasoning=result.get("reasoning", ""),
                    confidence=result.get("confidence", 0.8),
                    duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                )
            
            # Otherwise, simulate crew execution
            return self._simulate_execution(request, start_time)
            
        except Exception as e:
            logger.exception(f"Crew execution error: {e}")
            return CrewExecutionResult(
                crew_id=self.crew_id,
                success=False,
                analysis={},
                recommendations=[],
                evidence=[],
                reasoning="",
                confidence=0.0,
                duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                error=str(e),
            )
    
    def _simulate_execution(
        self,
        request: CrewExecutionRequest,
        start_time: datetime,
    ) -> CrewExecutionResult:
        """Simulate crew execution for demo purposes."""
        import random
        import time
        
        # Simulate processing time
        time.sleep(0.1)
        
        # Generate simulated results based on crew type
        crew_type = self.crew_id.replace("_optimization", "")
        
        analysis = {
            "opportunities_found": random.randint(2, 5),
            "risks_identified": random.randint(1, 3),
            "top_performers": [f"{crew_type}_entity_{i}" for i in range(1, 4)],
            "underperformers": [f"{crew_type}_entity_{i}" for i in range(4, 6)],
        }
        
        recommendations = []
        for i in range(random.randint(2, 4)):
            current = random.uniform(100000, 500000)
            delta = current * random.uniform(-0.15, 0.25)
            recommendations.append({
                "entity": f"{crew_type}_entity_{i+1}",
                "action": "increase_spend" if delta > 0 else "decrease_spend",
                "amount": abs(delta),
                "confidence": random.uniform(0.75, 0.95),
                "rationale": f"Based on {crew_type} level analysis",
            })
        
        evidence = [
            {
                "type": "posterior_estimate",
                "metric": f"{crew_type}_elasticity",
                "value": random.uniform(0.10, 0.25),
                "ci_lower": 0.08,
                "ci_upper": 0.28,
            },
            {
                "type": "probability",
                "metric": "p_positive_lift",
                "value": random.uniform(0.80, 0.95),
            },
        ]
        
        reasoning = (
            f"Analyzed {crew_type} level data for scenario {request.scenario_id}. "
            f"Applied {request.risk_appetite.value} risk appetite constraints. "
            f"Found {analysis['opportunities_found']} scale opportunities and "
            f"{analysis['risks_identified']} areas of concern."
        )
        
        return CrewExecutionResult(
            crew_id=self.crew_id,
            success=True,
            analysis=analysis,
            recommendations=recommendations,
            evidence=evidence,
            reasoning=reasoning,
            confidence=random.uniform(0.80, 0.95),
            duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
        )


class ScenarioCrewOrchestrator:
    """
    Orchestrates crew execution for business scenarios.
    Manages the flow of information between crews and aggregates results.
    """
    
    def __init__(
        self,
        message_bus: Optional[MessageBus] = None,
        coordinator: Optional[CrossCrewCoordinator] = None,
    ):
        self.bus = message_bus or MessageBus()
        self.coordinator = coordinator or CrossCrewCoordinator(self.bus)
        self._crew_adapters: Dict[str, CrewAdapter] = {}
        self._register_default_crews()
    
    def _register_default_crews(self) -> None:
        """Register default crew adapters."""
        default_crews = [
            "brand_optimization",
            "rmn_optimization",
            "channel_optimization",
            "campaign_optimization",
        ]
        for crew_id in default_crews:
            self._crew_adapters[crew_id] = CrewAdapter(crew_id)
    
    def register_crew(
        self,
        crew_id: str,
        crew_class: Optional[Type] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register a crew adapter."""
        adapter = CrewAdapter(crew_id, crew_class)
        if config:
            adapter.initialize(config)
        self._crew_adapters[crew_id] = adapter
    
    def execute_scenario_with_crews(
        self,
        scenario: BusinessScenario,
        context: Dict[str, Any],
        constraints: Optional[ScenarioConstraints] = None,
        risk_appetite: Optional[RiskAppetite] = None,
    ) -> Dict[str, Any]:
        """
        Execute a scenario by running the required crews in sequence.
        """
        effective_constraints = constraints or scenario.default_constraints
        effective_risk = risk_appetite or scenario.default_risk_appetite
        
        # Start coordination
        coordination_id = self.coordinator.start_scenario_coordination(
            scenario_id=scenario.scenario_id,
            scenario_name=scenario.name,
            crew_sequence=scenario.crew_sequence,
            initial_context=context,
        )
        
        # Execute crews in sequence
        crew_results: Dict[str, CrewExecutionResult] = {}
        aggregated_context = dict(context)
        
        for crew_id in scenario.crew_sequence:
            adapter = self._crew_adapters.get(crew_id)
            if not adapter:
                logger.warning(f"No adapter for crew {crew_id}, skipping")
                continue
            
            # Build request with upstream results
            request = CrewExecutionRequest(
                crew_id=crew_id,
                scenario_id=scenario.scenario_id,
                context=aggregated_context,
                constraints=effective_constraints,
                risk_appetite=effective_risk,
                upstream_results={k: v.analysis for k, v in crew_results.items()},
            )
            
            # Execute crew
            result = adapter.execute(request)
            crew_results[crew_id] = result
            
            # Advance coordination
            self.coordinator.advance_scenario(
                coordination_id,
                {
                    "crew_id": crew_id,
                    "success": result.success,
                    "analysis": result.analysis,
                    "updates": {f"{crew_id}_completed": True},
                },
            )
            
            # Update context with results
            aggregated_context[f"{crew_id}_result"] = result.analysis
            aggregated_context.update({f"{crew_id}_analyzed": True})
        
        # Aggregate results into decision recommendation
        return self._aggregate_results(scenario, crew_results, coordination_id)
    
    def _aggregate_results(
        self,
        scenario: BusinessScenario,
        crew_results: Dict[str, CrewExecutionResult],
        coordination_id: str,
    ) -> Dict[str, Any]:
        """Aggregate crew results into a unified output."""
        import uuid
        
        # Collect all recommendations
        all_recommendations = []
        priority = 1
        for crew_id, result in crew_results.items():
            for rec in result.recommendations:
                all_recommendations.append({
                    **rec,
                    "source_crew": crew_id,
                    "priority": priority,
                })
                priority += 1
        
        # Collect all evidence
        all_evidence = []
        for crew_id, result in crew_results.items():
            for ev in result.evidence:
                all_evidence.append({
                    **ev,
                    "source_crew": crew_id,
                })
        
        # Build reasoning chain
        reasoning_steps = []
        step_num = 1
        for crew_id, result in crew_results.items():
            reasoning_steps.append({
                "step_number": step_num,
                "crew_id": crew_id,
                "action": f"Analyzed {crew_id.replace('_optimization', '')} level",
                "reasoning": result.reasoning,
                "confidence": result.confidence,
                "duration_ms": result.duration_ms,
            })
            step_num += 1
        
        # Calculate overall metrics
        total_confidence = sum(r.confidence for r in crew_results.values())
        avg_confidence = total_confidence / len(crew_results) if crew_results else 0
        
        total_duration = sum(r.duration_ms for r in crew_results.values())
        
        return {
            "coordination_id": coordination_id,
            "scenario_id": scenario.scenario_id,
            "scenario_name": scenario.name,
            "crews_executed": list(crew_results.keys()),
            "recommendations": all_recommendations,
            "evidence": all_evidence,
            "reasoning_chain": {
                "steps": reasoning_steps,
                "crews_involved": list(crew_results.keys()),
            },
            "overall_confidence": avg_confidence,
            "total_duration_ms": total_duration,
            "success": all(r.success for r in crew_results.values()),
        }
    
    def get_crew_status(self) -> Dict[str, str]:
        """Get status of all registered crews."""
        return {
            crew_id: "registered"
            for crew_id in self._crew_adapters.keys()
        }


def create_integrated_executor():
    """
    Factory function to create a fully integrated scenario executor
    with crew orchestration and messaging.
    """
    from .executor import ScenarioExecutor
    
    bus = MessageBus()
    coordinator = CrossCrewCoordinator(bus)
    orchestrator = ScenarioCrewOrchestrator(bus, coordinator)
    executor = ScenarioExecutor(bus, coordinator)
    
    return {
        "executor": executor,
        "orchestrator": orchestrator,
        "message_bus": bus,
        "coordinator": coordinator,
    }
