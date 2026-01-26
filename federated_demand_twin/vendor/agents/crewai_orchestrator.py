"""
Unified CrewAI Orchestrator

Orchestrates multi-agent workflows using CrewAI Crew.
Implements the complete decision pipeline:
    Sense → Update → Simulate → Optimize → Explain → Learn
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
from pathlib import Path
import numpy as np

from .crewai_base import (
    DemandTwinAgent,
    AgentRegistry,
    AgentMessageBus,
    AgentCategory,
    AgentRole,
    create_task,
    create_crew,
    CREWAI_AVAILABLE,
)

if CREWAI_AVAILABLE:
    from crewai import Task, Crew, Process
else:
    from .crewai_base import Task, Crew, Process

from .crewai_agents import (
    DataStewardAgent,
    AttributionAgent,
    ElasticityAgent,
    ForecastAgent,
    ScenarioGeneratorAgent,
    DigitalTwinAgent,
    BudgetOptimizerAgent,
    GovernanceAgent,
    RationaleAgent,
    ReportWriterAgent,
    create_agent,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WorkflowStage(str, Enum):
    """Stages of the decision workflow"""
    SENSE = "sense"
    UPDATE = "update"
    SIMULATE = "simulate"
    OPTIMIZE = "optimize"
    EXPLAIN = "explain"
    LEARN = "learn"


class WorkflowStatus(str, Enum):
    """Workflow execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REQUIRES_REVIEW = "requires_review"


@dataclass
class StageResult:
    """Result from a workflow stage"""
    stage: WorkflowStage
    status: WorkflowStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    outputs: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    
    @property
    def duration_seconds(self) -> float:
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage.value,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "outputs": self.outputs,
            "errors": self.errors,
        }


@dataclass
class DecisionPack:
    """Complete decision package from workflow"""
    pack_id: str
    retailer_id: str
    created_at: datetime
    
    # Results
    recommendation: Dict[str, Any]
    simulation_results: Dict[str, Dict[str, Any]]
    governance_decision: Dict[str, Any]
    rationale: Dict[str, str]
    report: str
    
    # Metadata
    stage_results: Dict[str, StageResult]
    overall_status: WorkflowStatus
    confidence_score: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "retailer_id": self.retailer_id,
            "created_at": self.created_at.isoformat(),
            "recommendation": self.recommendation,
            "simulation_results": self.simulation_results,
            "governance_decision": self.governance_decision,
            "rationale": self.rationale,
            "report": self.report,
            "stage_results": {k: v.to_dict() for k, v in self.stage_results.items()},
            "overall_status": self.overall_status.value,
            "confidence_score": self.confidence_score,
        }
    
    def save(self, path: str):
        """Save decision pack to file"""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)


@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator"""
    retailer_id: str
    segment_id: Optional[str] = None
    
    # Agent settings
    drivers: List[str] = field(default_factory=lambda: ["media", "price", "trade"])
    data_streams: List[str] = field(default_factory=lambda: ["spend", "price", "promo"])
    
    # Workflow settings
    n_simulations: int = 1000
    n_scenarios: int = 5
    risk_aversion: float = 0.3
    
    # Governance
    auto_approve_threshold: float = 0.9
    max_budget_change: float = 0.25
    
    # Output
    output_path: str = "./reports"
    save_packs: bool = True


class CrewAIOrchestrator:
    """
    Unified orchestrator for CrewAI-based agent workflows.
    
    Implements the decision loop:
    1. SENSE: Validate data quality
    2. UPDATE: Update Bayesian beliefs (elasticity, attribution)
    3. SIMULATE: Generate scenarios and run Digital Twin
    4. OPTIMIZE: Select optimal allocation
    5. EXPLAIN: Generate rationale and governance review
    6. LEARN: Log outcomes for future learning
    """
    
    def __init__(self, config: OrchestratorConfig):
        self.config = config
        self.registry = AgentRegistry.get_instance()
        self.message_bus = self.registry.message_bus
        
        # Initialize agents
        self._initialize_agents()
        
        # Workflow state
        self.current_run_id: Optional[str] = None
        self.stage_results: Dict[str, StageResult] = {}
        self.run_history: List[DecisionPack] = []
        
        logger.info(f"CrewAIOrchestrator initialized for {config.retailer_id}")
    
    def _initialize_agents(self):
        """Initialize all agents for the workflow"""
        rid = self.config.retailer_id
        
        # Data Agents
        self.data_steward = DataStewardAgent(
            agent_id=f"{rid}-data-steward",
            retailer_id=rid,
            stream_ids=self.config.data_streams,
            message_bus=self.message_bus,
        )
        self.registry.register(self.data_steward)
        
        # Analytics Agents
        self.attribution_agent = AttributionAgent(
            agent_id=f"{rid}-attribution",
            retailer_id=rid,
            drivers=self.config.drivers,
            message_bus=self.message_bus,
        )
        self.registry.register(self.attribution_agent)
        
        self.elasticity_agent = ElasticityAgent(
            agent_id=f"{rid}-elasticity",
            retailer_id=rid,
            message_bus=self.message_bus,
        )
        self.registry.register(self.elasticity_agent)
        
        self.forecast_agent = ForecastAgent(
            agent_id=f"{rid}-forecast",
            retailer_id=rid,
            message_bus=self.message_bus,
        )
        self.registry.register(self.forecast_agent)
        
        # Simulation Agents
        self.scenario_agent = ScenarioGeneratorAgent(
            agent_id=f"{rid}-scenario",
            retailer_id=rid,
            drivers=self.config.drivers,
            message_bus=self.message_bus,
        )
        self.registry.register(self.scenario_agent)
        
        self.twin_agent = DigitalTwinAgent(
            agent_id=f"{rid}-twin",
            retailer_id=rid,
            message_bus=self.message_bus,
        )
        self.registry.register(self.twin_agent)
        
        # Optimization Agents
        self.optimizer_agent = BudgetOptimizerAgent(
            agent_id=f"{rid}-optimizer",
            retailer_id=rid,
            drivers=self.config.drivers,
            message_bus=self.message_bus,
        )
        self.registry.register(self.optimizer_agent)
        
        # Governance Agents
        self.governance_agent = GovernanceAgent(
            agent_id=f"{rid}-governance",
            retailer_id=rid,
            message_bus=self.message_bus,
        )
        self._setup_governance_policies()
        self.registry.register(self.governance_agent)
        
        # Communication Agents
        self.rationale_agent = RationaleAgent(
            agent_id=f"{rid}-rationale",
            retailer_id=rid,
            message_bus=self.message_bus,
        )
        self.registry.register(self.rationale_agent)
        
        self.report_agent = ReportWriterAgent(
            agent_id=f"{rid}-report",
            retailer_id=rid,
            message_bus=self.message_bus,
        )
        self.registry.register(self.report_agent)
        
        logger.info(f"Initialized {len(self.registry.get_all())} agents")
    
    def _setup_governance_policies(self):
        """Setup governance validation policies"""
        # Budget change limit
        def check_budget_change(rec: Dict[str, Any]) -> bool:
            change = rec.get("budget_change_pct", 0)
            return abs(change) <= self.config.max_budget_change
        
        self.governance_agent.add_policy(
            "max_budget_change",
            check_budget_change,
            severity="warning"
        )
        
        # Minimum confidence
        def check_confidence(rec: Dict[str, Any]) -> bool:
            return rec.get("confidence", 0) >= 0.5
        
        self.governance_agent.add_policy(
            "min_confidence",
            check_confidence,
            severity="critical"
        )
    
    def _start_stage(self, stage: WorkflowStage) -> StageResult:
        """Start a workflow stage"""
        result = StageResult(
            stage=stage,
            status=WorkflowStatus.RUNNING,
            started_at=datetime.utcnow(),
        )
        self.stage_results[stage.value] = result
        logger.info(f"Starting stage: {stage.value}")
        return result
    
    def _complete_stage(
        self,
        result: StageResult,
        outputs: Dict[str, Any],
        status: WorkflowStatus = WorkflowStatus.COMPLETED
    ):
        """Complete a workflow stage"""
        result.completed_at = datetime.utcnow()
        result.status = status
        result.outputs = outputs
        logger.info(f"Completed stage: {result.stage.value} ({result.duration_seconds:.1f}s)")
    
    def run(
        self,
        data_inputs: Dict[str, np.ndarray],
        current_allocation: Dict[str, float],
        total_budget: float,
        conversion_paths: Optional[List[List[str]]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> DecisionPack:
        """
        Run the complete decision workflow.
        
        Args:
            data_inputs: Dict of stream_id -> data arrays
            current_allocation: Current driver allocations
            total_budget: Total budget constraint
            conversion_paths: Optional conversion paths for attribution
            context: Additional context
        
        Returns:
            DecisionPack with recommendations
        """
        import hashlib
        
        self.current_run_id = hashlib.md5(
            f"{datetime.utcnow().isoformat()}_{self.config.retailer_id}".encode()
        ).hexdigest()[:12]
        
        self.stage_results = {}
        
        logger.info(f"Starting workflow run {self.current_run_id}")
        
        # Stage 1: SENSE - Data validation
        stage_result = self._start_stage(WorkflowStage.SENSE)
        try:
            data_quality = {}
            for stream_id, data in data_inputs.items():
                quality = self.data_steward.validate_stream(stream_id, data)
                data_quality[stream_id] = quality
            
            overall_quality = np.mean([q["quality_score"] for q in data_quality.values()])
            self._complete_stage(stage_result, {
                "data_quality": data_quality,
                "overall_quality": overall_quality,
            })
        except Exception as e:
            stage_result.errors.append(str(e))
            stage_result.status = WorkflowStatus.FAILED
            logger.error(f"SENSE stage failed: {e}")
        
        # Stage 2: UPDATE - Bayesian belief updates
        stage_result = self._start_stage(WorkflowStage.UPDATE)
        try:
            # Attribution update
            attribution = None
            if conversion_paths:
                attribution = self.attribution_agent.compute_attribution(
                    conversion_paths, total_budget
                )
            
            # Elasticity update (if spend/response data available)
            elasticity = None
            if "spend" in data_inputs and "response" in data_inputs:
                elasticity = self.elasticity_agent.estimate_elasticity(
                    data_inputs["spend"],
                    data_inputs["response"],
                    elasticity_type="media"
                )
            
            # Forecast update
            forecast = None
            if "demand" in data_inputs:
                forecast = self.forecast_agent.forecast(data_inputs["demand"])
            
            self._complete_stage(stage_result, {
                "attribution": attribution,
                "elasticity": elasticity,
                "forecast": forecast,
            })
        except Exception as e:
            stage_result.errors.append(str(e))
            stage_result.status = WorkflowStatus.FAILED
            logger.error(f"UPDATE stage failed: {e}")
        
        # Stage 3: SIMULATE - Scenario generation and simulation
        stage_result = self._start_stage(WorkflowStage.SIMULATE)
        try:
            # Generate scenarios
            scenarios = self.scenario_agent.generate_scenarios(
                current_allocation,
                total_budget,
                n_scenarios=self.config.n_scenarios
            )
            
            # Run simulations
            simulation_results = {}
            for scenario in scenarios:
                result = self.twin_agent.simulate(
                    scenario,
                    n_simulations=self.config.n_simulations
                )
                simulation_results[scenario["scenario_id"]] = result
            
            self._complete_stage(stage_result, {
                "scenarios": scenarios,
                "simulation_results": simulation_results,
            })
        except Exception as e:
            stage_result.errors.append(str(e))
            stage_result.status = WorkflowStatus.FAILED
            logger.error(f"SIMULATE stage failed: {e}")
            simulation_results = {}
        
        # Stage 4: OPTIMIZE - Select optimal allocation
        stage_result = self._start_stage(WorkflowStage.OPTIMIZE)
        try:
            optimization = self.optimizer_agent.optimize(
                simulation_results,
                total_budget,
                risk_aversion=self.config.risk_aversion
            )
            
            # Get the selected scenario
            selected_id = optimization.get("selected_scenario")
            selected_scenario = next(
                (s for s in scenarios if s["scenario_id"] == selected_id),
                scenarios[0] if scenarios else {}
            )
            
            recommendation = {
                "scenario_id": selected_id,
                "name": selected_scenario.get("name", "Unknown"),
                "allocation": selected_scenario.get("allocation", current_allocation),
                "total_budget": total_budget,
                "expected_sales": optimization.get("expected_sales", 0),
                "expected_roas": optimization.get("expected_roas", 0),
                "confidence": 0.8,  # Simplified
                "budget_change_pct": 0,  # Would compute from current
            }
            
            self._complete_stage(stage_result, {
                "optimization": optimization,
                "recommendation": recommendation,
            })
        except Exception as e:
            stage_result.errors.append(str(e))
            stage_result.status = WorkflowStatus.FAILED
            logger.error(f"OPTIMIZE stage failed: {e}")
            recommendation = {"allocation": current_allocation}
        
        # Stage 5: EXPLAIN - Governance and rationale
        stage_result = self._start_stage(WorkflowStage.EXPLAIN)
        try:
            # Governance validation
            governance_decision = self.governance_agent.validate(recommendation)
            
            # Generate rationale
            best_sim = simulation_results.get(recommendation.get("scenario_id"), {})
            rationale = self.rationale_agent.generate_rationale(
                recommendation,
                best_sim,
                governance_decision
            )
            
            # Compile report
            report = self.report_agent.compile_report(
                recommendation,
                simulation_results,
                governance_decision,
                rationale
            )
            
            self._complete_stage(stage_result, {
                "governance_decision": governance_decision,
                "rationale": rationale,
                "report": report,
            })
        except Exception as e:
            stage_result.errors.append(str(e))
            stage_result.status = WorkflowStatus.FAILED
            logger.error(f"EXPLAIN stage failed: {e}")
            governance_decision = {"approved": False, "errors": [str(e)]}
            rationale = {}
            report = ""
        
        # Stage 6: LEARN - Log for future learning
        stage_result = self._start_stage(WorkflowStage.LEARN)
        try:
            # Would log to database for future recalibration
            learning_log = {
                "run_id": self.current_run_id,
                "recommendation": recommendation,
                "governance_approved": governance_decision.get("approved", False),
                "logged_at": datetime.utcnow().isoformat(),
            }
            self._complete_stage(stage_result, {"learning_log": learning_log})
        except Exception as e:
            stage_result.errors.append(str(e))
            logger.warning(f"LEARN stage failed: {e}")
        
        # Determine overall status
        failed_stages = [s for s in self.stage_results.values() if s.status == WorkflowStatus.FAILED]
        if failed_stages:
            overall_status = WorkflowStatus.FAILED
        elif not governance_decision.get("approved", False):
            overall_status = WorkflowStatus.REQUIRES_REVIEW
        else:
            overall_status = WorkflowStatus.COMPLETED
        
        # Build decision pack
        decision_pack = DecisionPack(
            pack_id=self.current_run_id,
            retailer_id=self.config.retailer_id,
            created_at=datetime.utcnow(),
            recommendation=recommendation,
            simulation_results=simulation_results,
            governance_decision=governance_decision,
            rationale=rationale,
            report=report,
            stage_results=dict(self.stage_results),
            overall_status=overall_status,
            confidence_score=recommendation.get("confidence", 0),
        )
        
        # Save if configured
        if self.config.save_packs:
            pack_path = f"{self.config.output_path}/decision_pack_{self.current_run_id}.json"
            decision_pack.save(pack_path)
            logger.info(f"Saved decision pack to {pack_path}")
        
        self.run_history.append(decision_pack)
        
        logger.info(f"Workflow completed: {overall_status.value}")
        
        return decision_pack
    
    def run_with_crew(
        self,
        data_inputs: Dict[str, np.ndarray],
        current_allocation: Dict[str, float],
        total_budget: float,
    ) -> Any:
        """
        Run workflow using CrewAI Crew orchestration.
        
        This method uses CrewAI's native Task and Crew abstractions
        for agent coordination.
        """
        if not CREWAI_AVAILABLE:
            logger.warning("CrewAI not available, falling back to sequential execution")
            return self.run(data_inputs, current_allocation, total_budget)
        
        # Define tasks
        tasks = [
            Task(
                description=f"Validate data quality for streams: {list(data_inputs.keys())}",
                agent=self.data_steward,
                expected_output="Data quality report with scores and issues",
            ),
            Task(
                description="Update elasticity beliefs from recent data",
                agent=self.elasticity_agent,
                expected_output="Updated elasticity posteriors",
            ),
            Task(
                description=f"Generate {self.config.n_scenarios} scenarios for budget ${total_budget/1e6:.1f}M",
                agent=self.scenario_agent,
                expected_output="List of candidate scenarios with allocations",
            ),
            Task(
                description="Simulate all scenarios using Digital Twin",
                agent=self.twin_agent,
                expected_output="Simulation results with KPI distributions",
            ),
            Task(
                description="Select optimal allocation under risk constraints",
                agent=self.optimizer_agent,
                expected_output="Selected scenario with justification",
            ),
            Task(
                description="Validate recommendation against governance policies",
                agent=self.governance_agent,
                expected_output="Governance decision with any violations",
            ),
            Task(
                description="Generate human-readable rationale for recommendation",
                agent=self.rationale_agent,
                expected_output="Executive summary and detailed rationale",
            ),
        ]
        
        # Create and run crew
        crew = Crew(
            agents=[
                self.data_steward,
                self.elasticity_agent,
                self.scenario_agent,
                self.twin_agent,
                self.optimizer_agent,
                self.governance_agent,
                self.rationale_agent,
            ],
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
        )
        
        result = crew.kickoff(inputs={
            "data_inputs": data_inputs,
            "current_allocation": current_allocation,
            "total_budget": total_budget,
        })
        
        return result
    
    def get_agent_summary(self) -> Dict[str, Any]:
        """Get summary of all agents"""
        agents = self.registry.get_all()
        
        by_category = {}
        for agent in agents:
            cat = agent.config.category.value
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append({
                "id": agent.config.agent_id,
                "role": agent.config.role.value,
                "beliefs": len(agent.beliefs),
            })
        
        return {
            "total_agents": len(agents),
            "by_category": by_category,
            "retailer_id": self.config.retailer_id,
        }


# =============================================================================
# Factory Functions
# =============================================================================

def create_orchestrator(
    retailer_id: str,
    drivers: Optional[List[str]] = None,
    **kwargs
) -> CrewAIOrchestrator:
    """Factory function for orchestrator"""
    config = OrchestratorConfig(
        retailer_id=retailer_id,
        drivers=drivers or ["media", "price", "trade"],
        **kwargs
    )
    return CrewAIOrchestrator(config)


def create_retail_media_orchestrator(
    retailer_id: str,
    channels: Optional[List[str]] = None,
    **kwargs
) -> CrewAIOrchestrator:
    """Factory function for retail media optimization"""
    config = OrchestratorConfig(
        retailer_id=retailer_id,
        drivers=channels or ["sponsored_search", "display", "email", "in_store"],
        data_streams=["spend", "impressions", "clicks", "conversions"],
        **kwargs
    )
    return CrewAIOrchestrator(config)
