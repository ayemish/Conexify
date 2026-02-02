"""
Base Optimization Crew

Abstract base class for all optimization crews with common patterns:
- Ingest & validate
- Diagnose
- Optimize
- Explain
- QA & governance
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import logging
import numpy as np

from .schemas import (
    DesiredOutcome,
    OptimizationConstraints,
    CrewConfig,
    CrewOutput,
    OptimizationResult,
    AllocationRecommendation,
    ImpactEstimate,
    RiskAssessment,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AgentDefinition:
    """
    CrewAI-compliant agent definition.
    
    Required attributes per CrewAI spec:
    - role: Defines the agent's function and expertise within the crew
    - goal: The individual objective that guides the agent's decision-making
    - backstory: Provides context and personality to the agent
    
    Optional attributes:
    - llm: Language model that powers the agent
    - tools: Capabilities or functions available to the agent
    - function_calling_llm: Language model for tool calling
    - max_iter: Maximum iterations before best answer (default: 20)
    - max_rpm: Maximum requests per minute
    - max_execution_time: Maximum time in seconds for task execution
    - verbose: Enable detailed execution logs (default: False)
    - allow_delegation: Allow delegating tasks (default: False)
    - cache: Enable caching for tool usage (default: True)
    - system_template: Custom system prompt template
    - respect_context_window: Keep messages under context window (default: True)
    - max_retry_limit: Max retries on error (default: 2)
    """
    # Required fields (per CrewAI spec)
    role: str
    goal: str
    backstory: str
    
    # Identity
    agent_id: str = ""
    name: str = ""  # Display name
    
    # LLM configuration
    llm: Optional[str] = None
    function_calling_llm: Optional[str] = None
    
    # Tools
    tools: List[str] = field(default_factory=list)
    
    # Execution settings
    max_iter: int = 20
    max_rpm: Optional[int] = None
    max_execution_time: Optional[int] = None
    max_retry_limit: int = 2
    
    # Behavior settings
    verbose: bool = False
    allow_delegation: bool = False
    cache: bool = True
    respect_context_window: bool = True
    
    # Templates
    system_template: Optional[str] = None
    prompt_template: Optional[str] = None
    response_template: Optional[str] = None
    
    # Advanced
    allow_code_execution: bool = False
    code_execution_mode: str = "safe"  # "safe" or "unsafe"
    multimodal: bool = False
    reasoning: bool = False
    max_reasoning_attempts: Optional[int] = None
    
    def to_crewai_dict(self) -> Dict[str, Any]:
        """Convert to CrewAI-compatible dictionary format."""
        config = {
            "role": self.role,
            "goal": self.goal,
            "backstory": self.backstory,
            "verbose": self.verbose,
            "allow_delegation": self.allow_delegation,
            "cache": self.cache,
            "max_iter": self.max_iter,
            "max_retry_limit": self.max_retry_limit,
            "respect_context_window": self.respect_context_window,
        }
        
        if self.llm:
            config["llm"] = self.llm
        if self.function_calling_llm:
            config["function_calling_llm"] = self.function_calling_llm
        if self.tools:
            config["tools"] = self.tools
        if self.max_rpm:
            config["max_rpm"] = self.max_rpm
        if self.max_execution_time:
            config["max_execution_time"] = self.max_execution_time
        if self.system_template:
            config["system_template"] = self.system_template
        if self.allow_code_execution:
            config["allow_code_execution"] = self.allow_code_execution
            config["code_execution_mode"] = self.code_execution_mode
        if self.multimodal:
            config["multimodal"] = self.multimodal
        if self.reasoning:
            config["reasoning"] = self.reasoning
            if self.max_reasoning_attempts:
                config["max_reasoning_attempts"] = self.max_reasoning_attempts
        
        return config
    
    def to_yaml_dict(self) -> Dict[str, Any]:
        """Convert to YAML-compatible dictionary for agents.yaml."""
        yaml_dict = {
            "role": self.role,
            "goal": self.goal,
            "backstory": self.backstory,
        }
        if self.tools:
            yaml_dict["tools"] = self.tools
        if self.allow_delegation:
            yaml_dict["allow_delegation"] = self.allow_delegation
        if self.verbose:
            yaml_dict["verbose"] = self.verbose
        if self.llm:
            yaml_dict["llm"] = self.llm
        if self.max_iter != 20:
            yaml_dict["max_iter"] = self.max_iter
        if self.cache is False:
            yaml_dict["cache"] = self.cache
        return yaml_dict


@dataclass
class TaskDefinition:
    """
    CrewAI-compliant task definition.
    
    Required attributes:
    - description: Clear statement of what needs to be done
    - expected_output: Description of expected deliverable
    - agent_id: Agent responsible for this task
    
    Optional attributes:
    - context: List of task IDs that provide context
    - async_execution: Whether to run asynchronously
    - output_json: Pydantic model for JSON output
    - output_pydantic: Pydantic model for structured output
    - output_file: File path for output
    - human_input: Whether to require human input
    """
    # Required fields
    description: str
    expected_output: str
    agent_id: str
    
    # Identity
    task_id: str = ""
    
    # Context and dependencies
    context_tasks: List[str] = field(default_factory=list)
    
    # Execution settings
    async_execution: bool = False
    human_input: bool = False
    
    # Output configuration
    output_file: Optional[str] = None
    output_json: Optional[str] = None
    output_pydantic: Optional[str] = None
    
    # Markdown formatting
    markdown: bool = False
    
    def to_crewai_dict(self) -> Dict[str, Any]:
        """Convert to CrewAI-compatible dictionary format."""
        config = {
            "description": self.description,
            "expected_output": self.expected_output,
            "agent": self.agent_id,
            "async_execution": self.async_execution,
        }
        
        if self.context_tasks:
            config["context"] = self.context_tasks
        if self.human_input:
            config["human_input"] = self.human_input
        if self.output_file:
            config["output_file"] = self.output_file
        if self.markdown:
            config["markdown"] = self.markdown
        
        return config
    
    def to_yaml_dict(self) -> Dict[str, Any]:
        """Convert to YAML-compatible dictionary for tasks.yaml."""
        yaml_dict = {
            "description": self.description,
            "expected_output": self.expected_output,
            "agent": self.agent_id,
        }
        if self.context_tasks:
            yaml_dict["context"] = self.context_tasks
        if self.async_execution:
            yaml_dict["async_execution"] = self.async_execution
        if self.human_input:
            yaml_dict["human_input"] = self.human_input
        if self.output_file:
            yaml_dict["output_file"] = self.output_file
        return yaml_dict


class BaseOptimizationCrew(ABC):
    """
    Abstract base class for optimization crews.
    
    Implements the standard crew pattern:
    1. Ingest & validate - confirm metric definitions, joins, data quality
    2. Diagnose - compute KPIs, identify drivers, isolate opportunities/risks
    3. Optimize - apply objective function and solve allocation
    4. Explain - generate recommendation narrative
    5. QA & governance - sanity checks and guardrail enforcement
    
    Supports two execution modes:
    - Standalone: Crew runs independently with its own config
    - Scenario-driven: Crew runs as part of orchestrated scenario execution
    """
    
    def __init__(
        self,
        config: CrewConfig,
        performance_data: Optional[Dict[str, Any]] = None,
        scenario_context: Optional[Dict[str, Any]] = None,
    ):
        self.config = config
        self.performance_data = performance_data or {}
        self.agents: Dict[str, AgentDefinition] = {}
        self.tasks: Dict[str, TaskDefinition] = {}
        self.execution_log: List[Dict[str, Any]] = []
        
        # Scenario-driven execution support
        self.scenario_context = scenario_context
        self.upstream_crew_outputs: Dict[str, Any] = {}
        self._is_scenario_mode = False
        self._scenario_id: Optional[str] = None
        self._message_callback: Optional[callable] = None
        
        self._setup_agents()
        self._setup_tasks()
    
    @property
    @abstractmethod
    def crew_type(self) -> str:
        """Return the crew type identifier."""
        pass
    
    @abstractmethod
    def _setup_agents(self) -> None:
        """Define agents for this crew."""
        pass
    
    @abstractmethod
    def _setup_tasks(self) -> None:
        """Define tasks for this crew."""
        pass
    
    def get_objective_function_params(self) -> Dict[str, Any]:
        """
        Get objective function parameters based on desired outcome.
        
        Returns objective weights, KPI floors, and optimization direction.
        """
        outcome = self.config.desired_outcome
        
        if outcome == DesiredOutcome.INCREASE_REVENUE:
            return {
                "primary_objective": "maximize_incremental_sales",
                "objective_weight": 1.0,
                "efficiency_weight": 0.1,
                "margin_weight": 0.0,
                "kpi_floor": None,
                "spend_ceiling": self.config.constraints.budget,
                "direction": "maximize",
                "tone": "growth",
            }
        elif outcome == DesiredOutcome.INCREASE_MARGIN:
            return {
                "primary_objective": "maximize_incremental_profit",
                "objective_weight": 0.7,
                "efficiency_weight": 0.0,
                "margin_weight": 0.3,
                "kpi_floor": None,
                "spend_ceiling": self.config.constraints.budget,
                "direction": "maximize",
                "tone": "profitability",
            }
        elif outcome == DesiredOutcome.MAINTAIN_REVENUE:
            return {
                "primary_objective": "minimize_spend",
                "objective_weight": 1.0,
                "efficiency_weight": 0.2,
                "margin_weight": 0.0,
                "kpi_floor": self.config.constraints.revenue_floor,
                "spend_ceiling": None,
                "direction": "minimize",
                "tone": "efficiency",
            }
        elif outcome == DesiredOutcome.REDUCE_COST:
            return {
                "primary_objective": "minimize_spend",
                "objective_weight": 1.0,
                "efficiency_weight": 0.1,
                "margin_weight": 0.0,
                "kpi_floor": self.config.constraints.revenue_floor,
                "spend_ceiling": None,
                "direction": "minimize",
                "tone": "cost_reduction",
            }
        else:
            raise ValueError(f"Unknown desired outcome: {outcome}")
    
    def run(self) -> CrewOutput:
        """
        Execute the full crew workflow.
        
        Returns:
            CrewOutput with recommendations, impact estimates, and risk assessments.
        """
        start_time = datetime.utcnow()
        
        try:
            # Step 1: Ingest & Validate
            self._log_step("ingest_validate", "started")
            validation_result = self.ingest_and_validate()
            self._log_step("ingest_validate", "completed", validation_result)
            
            if not validation_result.get("valid", False):
                return self._create_error_output(
                    f"Data validation failed: {validation_result.get('issues', [])}"
                )
            
            # Step 2: Diagnose
            self._log_step("diagnose", "started")
            diagnosis = self.diagnose()
            self._log_step("diagnose", "completed", diagnosis)
            
            # Step 3: Optimize
            self._log_step("optimize", "started")
            optimization_result = self.optimize(diagnosis)
            self._log_step("optimize", "completed", {"success": optimization_result.success})
            
            if not optimization_result.success:
                return self._create_error_output(
                    f"Optimization failed: {optimization_result.solver_message}"
                )
            
            # Step 4: Explain
            self._log_step("explain", "started")
            recommendations = self.explain(diagnosis, optimization_result)
            self._log_step("explain", "completed")
            
            # Step 5: QA & Governance
            self._log_step("qa_governance", "started")
            validated_output = self.qa_and_governance(recommendations)
            self._log_step("qa_governance", "completed")
            
            # Finalize output
            end_time = datetime.utcnow()
            validated_output.execution_time_seconds = (end_time - start_time).total_seconds()
            validated_output.crew_id = self.config.crew_id
            validated_output.crew_type = self.crew_type
            validated_output.desired_outcome = self.config.desired_outcome.value
            
            return validated_output
            
        except Exception as e:
            logger.error(f"Crew execution failed: {e}")
            return self._create_error_output(str(e))
    
    @abstractmethod
    def ingest_and_validate(self) -> Dict[str, Any]:
        """
        Validate input data and confirm metric definitions.
        
        Returns:
            Dict with 'valid' bool and any 'issues' list.
        """
        pass
    
    @abstractmethod
    def diagnose(self) -> Dict[str, Any]:
        """
        Compute KPIs, identify drivers, and isolate opportunities/risks.
        
        Returns:
            Dict with diagnostic results including KPIs, drivers, opportunities, risks.
        """
        pass
    
    @abstractmethod
    def optimize(self, diagnosis: Dict[str, Any]) -> OptimizationResult:
        """
        Apply objective function and solve for optimal allocation.
        
        Args:
            diagnosis: Results from diagnose() step.
            
        Returns:
            OptimizationResult with optimal allocation.
        """
        pass
    
    @abstractmethod
    def explain(
        self,
        diagnosis: Dict[str, Any],
        optimization_result: OptimizationResult
    ) -> CrewOutput:
        """
        Generate recommendation narrative and action list.
        
        Args:
            diagnosis: Results from diagnose() step.
            optimization_result: Results from optimize() step.
            
        Returns:
            CrewOutput with recommendations and explanations.
        """
        pass
    
    def qa_and_governance(self, output: CrewOutput) -> CrewOutput:
        """
        Perform QA checks and enforce governance guardrails.
        
        Args:
            output: CrewOutput from explain() step.
            
        Returns:
            Validated CrewOutput with any governance adjustments.
        """
        violations = []
        constraints = self.config.constraints
        
        # Check total spend against budget
        if constraints.budget > 0:
            if output.total_recommended_spend > constraints.budget * 1.001:  # 0.1% tolerance
                violations.append(
                    f"Total spend ${output.total_recommended_spend:,.0f} exceeds budget ${constraints.budget:,.0f}"
                )
        
        # Check allocation change limits
        for alloc in output.allocations:
            if abs(alloc.spend_delta_pct) > constraints.max_allocation_change_pct:
                violations.append(
                    f"{alloc.entity_name}: {alloc.spend_delta_pct:.1%} change exceeds {constraints.max_allocation_change_pct:.1%} limit"
                )
        
        # Check minimum spend requirements
        for alloc in output.allocations:
            if alloc.recommended_spend > 0 and alloc.recommended_spend < constraints.min_channel_spend:
                violations.append(
                    f"{alloc.entity_name}: ${alloc.recommended_spend:,.0f} below minimum ${constraints.min_channel_spend:,.0f}"
                )
        
        # Check channel floors/ceilings
        for alloc in output.allocations:
            entity_id = alloc.entity_id
            if entity_id in constraints.channel_floors:
                if alloc.recommended_spend < constraints.channel_floors[entity_id]:
                    violations.append(
                        f"{alloc.entity_name}: below floor of ${constraints.channel_floors[entity_id]:,.0f}"
                    )
            if entity_id in constraints.channel_ceilings:
                if alloc.recommended_spend > constraints.channel_ceilings[entity_id]:
                    violations.append(
                        f"{alloc.entity_name}: above ceiling of ${constraints.channel_ceilings[entity_id]:,.0f}"
                    )
        
        output.constraints_satisfied = len(violations) == 0
        output.constraint_violations = violations
        
        if violations:
            output.risks.append(f"Governance check found {len(violations)} constraint violations")
        
        return output
    
    def _log_step(self, step: str, status: str, details: Any = None) -> None:
        """Log a workflow step."""
        self.execution_log.append({
            "step": step,
            "status": status,
            "details": details,
            "timestamp": datetime.utcnow().isoformat(),
        })
        logger.info(f"[{self.crew_type}] {step}: {status}")
    
    def _create_error_output(self, error_message: str) -> CrewOutput:
        """Create an error output."""
        return CrewOutput(
            crew_id=self.config.crew_id,
            crew_type=self.crew_type,
            desired_outcome=self.config.desired_outcome.value,
            executive_summary=f"Optimization failed: {error_message}",
            key_findings=[],
            opportunities=[],
            risks=[error_message],
            constraints_satisfied=False,
            constraint_violations=[error_message],
        )
    
    # =========================================================================
    # Scenario-Driven Execution Support
    # =========================================================================
    
    def enable_scenario_mode(
        self,
        scenario_id: str,
        scenario_context: Dict[str, Any],
        upstream_outputs: Optional[Dict[str, Any]] = None,
        message_callback: Optional[callable] = None,
    ) -> None:
        """
        Enable scenario-driven execution mode.
        
        Args:
            scenario_id: ID of the scenario being executed
            scenario_context: Context from the scenario orchestrator
            upstream_outputs: Outputs from crews that ran before this one
            message_callback: Callback for sending inter-crew messages
        """
        self._is_scenario_mode = True
        self._scenario_id = scenario_id
        self.scenario_context = scenario_context
        self.upstream_crew_outputs = upstream_outputs or {}
        self._message_callback = message_callback
        
        # Update performance data with upstream context
        if upstream_outputs:
            for crew_id, output in upstream_outputs.items():
                self.performance_data[f"upstream_{crew_id}"] = output
        
        logger.info(f"[{self.crew_type}] Scenario mode enabled: {scenario_id}")
    
    def disable_scenario_mode(self) -> None:
        """Disable scenario-driven execution mode."""
        self._is_scenario_mode = False
        self._scenario_id = None
        self.scenario_context = None
        self.upstream_crew_outputs = {}
        self._message_callback = None
    
    def run_for_scenario(
        self,
        scenario_id: str,
        scenario_context: Dict[str, Any],
        upstream_outputs: Optional[Dict[str, Any]] = None,
    ) -> CrewOutput:
        """
        Execute the crew as part of a scenario.
        
        This method enables scenario mode, runs the crew, and returns
        output suitable for aggregation by the orchestrator.
        """
        self.enable_scenario_mode(
            scenario_id=scenario_id,
            scenario_context=scenario_context,
            upstream_outputs=upstream_outputs,
        )
        
        try:
            # Apply scenario-specific objective if provided
            if scenario_context.get("objective_override"):
                self._apply_scenario_objective(scenario_context["objective_override"])
            
            # Run the standard crew workflow
            output = self.run()
            
            # Add scenario metadata to output
            output.scenario_id = scenario_id
            output.is_scenario_output = True
            
            return output
            
        finally:
            self.disable_scenario_mode()
    
    def _apply_scenario_objective(self, objective_config: Dict[str, Any]) -> None:
        """Apply scenario-specific objective configuration."""
        if "desired_outcome" in objective_config:
            outcome_str = objective_config["desired_outcome"]
            try:
                self.config.desired_outcome = DesiredOutcome(outcome_str)
            except ValueError:
                logger.warning(f"Unknown desired outcome: {outcome_str}")
        
        if "constraints" in objective_config:
            for key, value in objective_config["constraints"].items():
                if hasattr(self.config.constraints, key):
                    setattr(self.config.constraints, key, value)
    
    def send_crew_message(
        self,
        target_crew: str,
        message_type: str,
        payload: Dict[str, Any],
    ) -> None:
        """
        Send a message to another crew during scenario execution.
        
        Args:
            target_crew: ID of the target crew
            message_type: Type of message (e.g., "context_update", "recommendation")
            payload: Message payload
        """
        if not self._is_scenario_mode:
            logger.warning("Cannot send crew message outside scenario mode")
            return
        
        if self._message_callback:
            self._message_callback(
                source_crew=self.crew_type,
                target_crew=target_crew,
                message_type=message_type,
                payload=payload,
                scenario_id=self._scenario_id,
            )
        else:
            logger.debug(f"No message callback - message to {target_crew} not sent")
    
    def get_upstream_insight(self, crew_id: str, key: str, default: Any = None) -> Any:
        """
        Get an insight from an upstream crew's output.
        
        Args:
            crew_id: ID of the upstream crew
            key: Key to look up in the crew's output
            default: Default value if not found
        """
        if crew_id not in self.upstream_crew_outputs:
            return default
        
        output = self.upstream_crew_outputs[crew_id]
        
        # Handle both dict and object outputs
        if isinstance(output, dict):
            return output.get(key, default)
        elif hasattr(output, key):
            return getattr(output, key)
        else:
            return default
    
    def get_scenario_parameter(self, key: str, default: Any = None) -> Any:
        """Get a parameter from the scenario context."""
        if not self.scenario_context:
            return default
        return self.scenario_context.get(key, default)
    
    def get_risk_appetite(self) -> str:
        """Get the risk appetite from scenario context."""
        return self.get_scenario_parameter("risk_appetite", "balanced")
    
    def get_max_reallocation_pct(self) -> float:
        """Get the maximum reallocation percentage."""
        return self.get_scenario_parameter("max_reallocation_pct", 0.15)
    
    def should_explore(self) -> bool:
        """Check if exploration is enabled for this scenario."""
        exploration_pct = self.get_scenario_parameter("exploration_budget_pct", 0.10)
        return exploration_pct > 0
    
    def get_agents_yaml(self) -> str:
        """Generate CrewAI-compatible agents YAML."""
        lines = []
        for agent_id, agent in self.agents.items():
            lines.append(f"{agent_id}:")
            lines.append(f"  role: \"{agent.role}\"")
            lines.append(f"  goal: \"{agent.goal}\"")
            lines.append(f"  backstory: \"{agent.backstory}\"")
            if agent.tools:
                lines.append(f"  tools: [{', '.join(agent.tools)}]")
            lines.append(f"  allow_delegation: {str(agent.allow_delegation).lower()}")
            lines.append(f"  verbose: {str(agent.verbose).lower()}")
            lines.append("")
        return "\n".join(lines)
    
    def get_tasks_yaml(self) -> str:
        """Generate CrewAI-compatible tasks YAML."""
        lines = []
        for task_id, task in self.tasks.items():
            lines.append(f"{task_id}:")
            lines.append(f"  description: \"{task.description}\"")
            lines.append(f"  expected_output: \"{task.expected_output}\"")
            lines.append(f"  agent: {task.agent_id}")
            if task.context_tasks:
                lines.append(f"  context: [{', '.join(task.context_tasks)}]")
            lines.append(f"  async_execution: {str(task.async_execution).lower()}")
            lines.append("")
        return "\n".join(lines)
