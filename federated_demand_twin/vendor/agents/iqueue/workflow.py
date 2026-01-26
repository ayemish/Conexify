"""
iQueue Operational Workflow

Implements the "Sense → Update → Simulate → Optimize → Explain → Learn" loop.

1. Data steward agents validate and score new signals
2. Outcome and driver agents update local and global beliefs
3. Attribution agent refreshes decompositions (direct/indirect/carryover)
4. Scenario agent generates and tests reallocations
5. Optimization agent selects candidates under constraints and risk tolerances
6. Governance agent validates and packages recommendations for human approval
7. Outcomes are observed; the system recalibrates and detects drift

Result: MMM becomes a continuous decision loop rather than an episodic report.
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum
import logging
import json
from pathlib import Path

from .base import AgentConfig, AgentType, AgentMessageBus, BeliefState
from .data_steward import DataStewardAgent, create_data_steward_agent
from .endogenous_state import (
    EndogenousStateAgent, create_state_agent_ensemble, StateMetric
)
from .driver_agents import (
    DriverAgent, create_driver_agent_ensemble, DriverType
)
from .attribution import AttributionAgent, create_attribution_agent
from .scenario_generation import ScenarioGenerationAgent, create_scenario_agent
from .optimization import OptimizationAgent, create_optimization_agent
from .governance import GovernanceAgent, create_governance_agent, GovernancePolicy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WorkflowStage(str, Enum):
    """Stages of the operational workflow"""
    SENSE = "sense"           # Data validation
    UPDATE = "update"         # Belief updates
    SIMULATE = "simulate"     # Scenario generation
    OPTIMIZE = "optimize"     # Optimization
    EXPLAIN = "explain"       # Governance & explanation
    LEARN = "learn"           # Recalibration


class WorkflowStatus(str, Enum):
    """Status of workflow execution"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class WorkflowConfig:
    """Configuration for iQueue workflow"""
    retailer_id: str
    segment_id: Optional[str] = None
    
    # Agent configuration
    drivers: List[str] = field(default_factory=lambda: ['media', 'price', 'trade'])
    data_streams: List[str] = field(default_factory=lambda: ['spend', 'price', 'promo', 'distribution'])
    
    # Workflow settings
    run_frequency: str = "daily"  # daily, weekly, on_demand
    auto_approve_threshold: float = 0.9  # Confidence for auto-approval
    max_scenarios: int = 50
    
    # Thresholds
    data_quality_threshold: float = 0.7
    confidence_threshold: float = 0.7
    risk_threshold: float = 0.2
    
    # Persistence
    state_path: Optional[str] = None
    log_path: Optional[str] = None


@dataclass
class StageResult:
    """Result from a workflow stage"""
    stage: WorkflowStage
    status: WorkflowStatus
    started_at: datetime
    completed_at: Optional[datetime]
    duration_ms: Optional[float]
    outputs: Dict[str, Any]
    errors: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'stage': self.stage.value,
            'status': self.status.value,
            'started_at': self.started_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'duration_ms': self.duration_ms,
            'outputs': self.outputs,
            'errors': self.errors
        }


@dataclass
class WorkflowRun:
    """Record of a complete workflow run"""
    run_id: str
    config: WorkflowConfig
    started_at: datetime
    completed_at: Optional[datetime]
    
    # Stage results
    stage_results: Dict[str, StageResult]
    
    # Overall outputs
    final_recommendation: Optional[Dict[str, Any]]
    decision_package: Optional[Dict[str, Any]]
    
    # Status
    status: WorkflowStatus
    blocked_at_stage: Optional[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'run_id': self.run_id,
            'retailer_id': self.config.retailer_id,
            'started_at': self.started_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'stages': {k: v.to_dict() for k, v in self.stage_results.items()},
            'final_recommendation': self.final_recommendation,
            'decision_package': self.decision_package,
            'status': self.status.value,
            'blocked_at_stage': self.blocked_at_stage
        }


class IQueueWorkflow:
    """
    Orchestrates the iQueue agent workflow.
    
    Implements: Sense → Update → Simulate → Optimize → Explain → Learn
    """
    
    def __init__(self, config: WorkflowConfig):
        self.config = config
        self.message_bus = AgentMessageBus()
        
        # Initialize agents
        self._initialize_agents()
        
        # Run history
        self.run_history: List[WorkflowRun] = []
        
        logger.info(f"IQueueWorkflow initialized for {config.retailer_id}")
    
    def _initialize_agents(self):
        """Initialize all agents in the workflow"""
        # Data Steward
        self.data_steward = create_data_steward_agent(
            retailer_id=self.config.retailer_id,
            segment_id=self.config.segment_id,
            stream_ids=self.config.data_streams,
            message_bus=self.message_bus
        )
        
        # Endogenous State Agents
        self.state_agents = create_state_agent_ensemble(
            retailer_id=self.config.retailer_id,
            segment_id=self.config.segment_id,
            message_bus=self.message_bus
        )
        
        # Driver Agents
        self.driver_agents = create_driver_agent_ensemble(
            retailer_id=self.config.retailer_id,
            message_bus=self.message_bus
        )
        
        # Attribution Agent
        self.attribution_agent = create_attribution_agent(
            retailer_id=self.config.retailer_id,
            drivers=self.config.drivers,
            message_bus=self.message_bus
        )
        
        # Scenario Generation Agent
        self.scenario_agent = create_scenario_agent(
            retailer_id=self.config.retailer_id,
            drivers=self.config.drivers,
            simulation_fn=self._simulate_scenario,
            message_bus=self.message_bus
        )
        
        # Optimization Agent
        self.optimization_agent = create_optimization_agent(
            retailer_id=self.config.retailer_id,
            drivers=self.config.drivers,
            response_fn=self._get_response,
            message_bus=self.message_bus
        )
        
        # Governance Agent
        self.governance_agent = create_governance_agent(
            retailer_id=self.config.retailer_id,
            message_bus=self.message_bus
        )
    
    def run(
        self,
        data_inputs: Dict[str, Any],
        current_allocations: Dict[str, float],
        total_budget: float,
        context: Optional[Dict[str, Any]] = None
    ) -> WorkflowRun:
        """
        Execute the complete workflow.
        
        Args:
            data_inputs: Dict of stream_id -> data for validation
            current_allocations: Current driver allocations
            total_budget: Total budget constraint
            context: Additional context for the run
            
        Returns:
            WorkflowRun with all stage results
        """
        import hashlib
        
        run_id = hashlib.md5(
            f"{datetime.utcnow().isoformat()}_{self.config.retailer_id}".encode()
        ).hexdigest()[:12]
        
        workflow_run = WorkflowRun(
            run_id=run_id,
            config=self.config,
            started_at=datetime.utcnow(),
            completed_at=None,
            stage_results={},
            final_recommendation=None,
            decision_package=None,
            status=WorkflowStatus.RUNNING,
            blocked_at_stage=None
        )
        
        try:
            # Stage 1: SENSE - Data validation
            sense_result = self._run_sense_stage(data_inputs)
            workflow_run.stage_results['sense'] = sense_result
            
            if sense_result.status == WorkflowStatus.BLOCKED:
                workflow_run.status = WorkflowStatus.BLOCKED
                workflow_run.blocked_at_stage = 'sense'
                workflow_run.completed_at = datetime.utcnow()
                return workflow_run
            
            # Stage 2: UPDATE - Belief updates
            update_result = self._run_update_stage(
                data_inputs, current_allocations
            )
            workflow_run.stage_results['update'] = update_result
            
            # Stage 3: SIMULATE - Scenario generation
            simulate_result = self._run_simulate_stage(
                current_allocations, total_budget
            )
            workflow_run.stage_results['simulate'] = simulate_result
            
            # Stage 4: OPTIMIZE - Find best allocation
            optimize_result = self._run_optimize_stage(
                current_allocations, total_budget
            )
            workflow_run.stage_results['optimize'] = optimize_result
            
            if optimize_result.status == WorkflowStatus.FAILED:
                workflow_run.status = WorkflowStatus.FAILED
                workflow_run.completed_at = datetime.utcnow()
                return workflow_run
            
            workflow_run.final_recommendation = optimize_result.outputs.get('plan')
            
            # Stage 5: EXPLAIN - Governance validation
            explain_result = self._run_explain_stage(
                optimize_result.outputs.get('plan', {}),
                context or {}
            )
            workflow_run.stage_results['explain'] = explain_result
            workflow_run.decision_package = explain_result.outputs.get('decision_package')
            
            if explain_result.outputs.get('decision_package', {}).get('decision_status') == 'blocked':
                workflow_run.status = WorkflowStatus.BLOCKED
                workflow_run.blocked_at_stage = 'explain'
            else:
                workflow_run.status = WorkflowStatus.COMPLETED
            
            # Stage 6: LEARN - Record for future learning
            learn_result = self._run_learn_stage(workflow_run)
            workflow_run.stage_results['learn'] = learn_result
            
            workflow_run.completed_at = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"Workflow failed: {e}")
            workflow_run.status = WorkflowStatus.FAILED
            workflow_run.completed_at = datetime.utcnow()
        
        # Store history
        self.run_history.append(workflow_run)
        
        return workflow_run
    
    def _run_sense_stage(self, data_inputs: Dict[str, Any]) -> StageResult:
        """Stage 1: SENSE - Validate and score incoming data"""
        started_at = datetime.utcnow()
        outputs = {}
        errors = []
        
        try:
            quality_scores = {}
            all_usable = True
            
            for stream_id, data in data_inputs.items():
                result = self.data_steward.process({
                    'stream_id': stream_id,
                    'data': data
                })
                
                quality_scores[stream_id] = result.get('confidence', 0)
                
                if not result.get('is_usable', True):
                    all_usable = False
                    errors.append(f"Stream {stream_id} failed quality check")
            
            outputs = {
                'quality_scores': quality_scores,
                'overall_quality': np.mean(list(quality_scores.values())),
                'all_usable': all_usable
            }
            
            status = WorkflowStatus.COMPLETED if all_usable else WorkflowStatus.BLOCKED
            
        except Exception as e:
            errors.append(str(e))
            status = WorkflowStatus.FAILED
        
        return StageResult(
            stage=WorkflowStage.SENSE,
            status=status,
            started_at=started_at,
            completed_at=datetime.utcnow(),
            duration_ms=(datetime.utcnow() - started_at).total_seconds() * 1000,
            outputs=outputs,
            errors=errors
        )
    
    def _run_update_stage(
        self,
        data_inputs: Dict[str, Any],
        current_allocations: Dict[str, float]
    ) -> StageResult:
        """Stage 2: UPDATE - Update agent beliefs"""
        started_at = datetime.utcnow()
        outputs = {}
        errors = []
        
        try:
            # Update state agents with observations
            state_updates = {}
            for metric, agent in self.state_agents.items():
                # Extract relevant observation from data
                observation = self._extract_observation(metric, data_inputs)
                if observation is not None:
                    result = agent.process({
                        'observation': observation,
                        'observation_variance': observation * 0.1,
                        'source': 'data_input'
                    })
                    state_updates[metric] = result
            
            # Update driver agents with spend data
            driver_updates = {}
            for driver, spend in current_allocations.items():
                if driver in self.driver_agents:
                    result = self.driver_agents[driver].process({
                        'spend': spend
                    })
                    driver_updates[driver] = result
            
            # Refresh attribution
            total_outcome = self._estimate_total_outcome(data_inputs)
            attribution_result = self.attribution_agent.process({
                'period': date.today(),
                'total_outcome': total_outcome,
                'driver_spends': current_allocations
            })
            
            outputs = {
                'state_updates': state_updates,
                'driver_updates': driver_updates,
                'attribution': attribution_result
            }
            
            status = WorkflowStatus.COMPLETED
            
        except Exception as e:
            errors.append(str(e))
            status = WorkflowStatus.FAILED
        
        return StageResult(
            stage=WorkflowStage.UPDATE,
            status=status,
            started_at=started_at,
            completed_at=datetime.utcnow(),
            duration_ms=(datetime.utcnow() - started_at).total_seconds() * 1000,
            outputs=outputs,
            errors=errors
        )
    
    def _run_simulate_stage(
        self,
        current_allocations: Dict[str, float],
        total_budget: float
    ) -> StageResult:
        """Stage 3: SIMULATE - Generate and test scenarios"""
        started_at = datetime.utcnow()
        outputs = {}
        errors = []
        
        try:
            from .scenario_generation import ScenarioType
            
            result = self.scenario_agent.process({
                'current_allocations': current_allocations,
                'total_budget': total_budget,
                'scenario_types': [
                    ScenarioType.FIXED_BUDGET,
                    ScenarioType.INCREMENTAL
                ],
                'n_scenarios': self.config.max_scenarios // 2,
                'constraints': {
                    'total_budget': total_budget
                }
            })
            
            outputs = {
                'scenarios_generated': result.get('scenarios_generated', 0),
                'scenarios_after_pruning': result.get('scenarios_after_pruning', 0),
                'best_scenario': result.get('best_scenario'),
                'pareto_frontier': result.get('pareto_frontier', [])
            }
            
            status = WorkflowStatus.COMPLETED
            
        except Exception as e:
            errors.append(str(e))
            status = WorkflowStatus.FAILED
        
        return StageResult(
            stage=WorkflowStage.SIMULATE,
            status=status,
            started_at=started_at,
            completed_at=datetime.utcnow(),
            duration_ms=(datetime.utcnow() - started_at).total_seconds() * 1000,
            outputs=outputs,
            errors=errors
        )
    
    def _run_optimize_stage(
        self,
        current_allocations: Dict[str, float],
        total_budget: float
    ) -> StageResult:
        """Stage 4: OPTIMIZE - Find optimal allocation"""
        started_at = datetime.utcnow()
        outputs = {}
        errors = []
        
        try:
            from .optimization import ObjectiveType, RiskMeasure
            
            result = self.optimization_agent.process({
                'current_allocations': current_allocations,
                'total_budget': total_budget,
                'objective': ObjectiveType.REVENUE,
                'risk_measure': RiskMeasure.CVAR,
                'risk_threshold': self.config.risk_threshold,
                'constraints': []
            })
            
            outputs = {
                'plan': result,
                'allocations': result.get('allocations', {}),
                'expected_value': result.get('expected_value', 0),
                'expected_roi': result.get('expected_roi', 0),
                'confidence': result.get('confidence', 0)
            }
            
            status = WorkflowStatus.COMPLETED
            
        except Exception as e:
            errors.append(str(e))
            status = WorkflowStatus.FAILED
        
        return StageResult(
            stage=WorkflowStage.OPTIMIZE,
            status=status,
            started_at=started_at,
            completed_at=datetime.utcnow(),
            duration_ms=(datetime.utcnow() - started_at).total_seconds() * 1000,
            outputs=outputs,
            errors=errors
        )
    
    def _run_explain_stage(
        self,
        recommendation: Dict[str, Any],
        context: Dict[str, Any]
    ) -> StageResult:
        """Stage 5: EXPLAIN - Governance validation and explanation"""
        started_at = datetime.utcnow()
        outputs = {}
        errors = []
        
        try:
            result = self.governance_agent.process({
                'recommendation': recommendation,
                'confidence_sources': {
                    'optimization': recommendation.get('confidence', 0.5),
                    'data_quality': 0.8
                },
                'evidence': {},
                'context': context
            })
            
            outputs = {
                'decision_package': result,
                'decision_status': result.get('decision_status'),
                'requires_approval': result.get('requires_human_approval', False),
                'rationale': result.get('rationale', [])
            }
            
            status = WorkflowStatus.COMPLETED
            
        except Exception as e:
            errors.append(str(e))
            status = WorkflowStatus.FAILED
        
        return StageResult(
            stage=WorkflowStage.EXPLAIN,
            status=status,
            started_at=started_at,
            completed_at=datetime.utcnow(),
            duration_ms=(datetime.utcnow() - started_at).total_seconds() * 1000,
            outputs=outputs,
            errors=errors
        )
    
    def _run_learn_stage(self, workflow_run: WorkflowRun) -> StageResult:
        """Stage 6: LEARN - Record outcomes for future learning"""
        started_at = datetime.utcnow()
        outputs = {}
        errors = []
        
        try:
            # Record run for future analysis
            outputs = {
                'run_id': workflow_run.run_id,
                'recorded': True,
                'metrics': {
                    'total_duration_ms': (
                        datetime.utcnow() - workflow_run.started_at
                    ).total_seconds() * 1000,
                    'stages_completed': len(workflow_run.stage_results),
                    'status': workflow_run.status.value
                }
            }
            
            # Save state if configured
            if self.config.state_path:
                self._save_state()
            
            status = WorkflowStatus.COMPLETED
            
        except Exception as e:
            errors.append(str(e))
            status = WorkflowStatus.FAILED
        
        return StageResult(
            stage=WorkflowStage.LEARN,
            status=status,
            started_at=started_at,
            completed_at=datetime.utcnow(),
            duration_ms=(datetime.utcnow() - started_at).total_seconds() * 1000,
            outputs=outputs,
            errors=errors
        )
    
    def _simulate_scenario(self, allocations: Dict[str, float]) -> Dict[str, Any]:
        """Simulate outcome for a scenario (used by scenario agent)"""
        # Use driver agents to compute expected response
        total_response = 0
        samples = []
        
        for _ in range(100):
            response = 0
            for driver, spend in allocations.items():
                if driver in self.driver_agents:
                    agent = self.driver_agents[driver]
                    elasticity = agent.beliefs.get('elasticity')
                    if elasticity:
                        marginal = np.random.normal(elasticity.mean, elasticity.std)
                    else:
                        marginal = 1.0
                    response += spend * marginal
            samples.append(response)
        
        return {
            'expected_value': np.mean(samples),
            'uncertainty': np.std(samples),
            'prob_improvement': 0.5,  # Simplified
            'confidence': 0.7,
            'samples': samples
        }
    
    def _get_response(self, allocations: Dict[str, float]) -> Dict[str, Any]:
        """Get expected response for allocations (used by optimization agent)"""
        return self._simulate_scenario(allocations)
    
    def _extract_observation(
        self,
        metric: str,
        data_inputs: Dict[str, Any]
    ) -> Optional[float]:
        """Extract observation for a state metric from data inputs"""
        # Simplified: would map from actual data structure
        mapping = {
            'total_baskets': 'spend',
            'basket_penetration': 'distribution',
            'items_per_basket': 'promo',
            'size_per_item': 'price'
        }
        
        source = mapping.get(metric)
        if source and source in data_inputs:
            data = data_inputs[source]
            if isinstance(data, list) and data:
                return float(len(data))
            elif isinstance(data, dict):
                return float(len(data))
        
        return None
    
    def _estimate_total_outcome(self, data_inputs: Dict[str, Any]) -> float:
        """Estimate total outcome from data inputs"""
        # Simplified: sum of all numeric values
        total = 0
        for stream_id, data in data_inputs.items():
            if isinstance(data, list):
                for record in data:
                    if isinstance(record, dict):
                        for v in record.values():
                            if isinstance(v, (int, float)):
                                total += v
        return max(total, 1000)  # Minimum baseline
    
    def _save_state(self):
        """Save workflow state"""
        if not self.config.state_path:
            return
        
        state = {
            'config': {
                'retailer_id': self.config.retailer_id,
                'segment_id': self.config.segment_id
            },
            'run_count': len(self.run_history),
            'last_run': self.run_history[-1].to_dict() if self.run_history else None
        }
        
        Path(self.config.state_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.config.state_path, 'w') as f:
            json.dump(state, f, indent=2, default=str)
    
    def get_agent_states(self) -> Dict[str, Any]:
        """Get current state of all agents"""
        return {
            'data_steward': self.data_steward.get_state(),
            'state_agents': {k: v.get_state() for k, v in self.state_agents.items()},
            'driver_agents': {k: v.get_state() for k, v in self.driver_agents.items()},
            'attribution': self.attribution_agent.get_state(),
            'scenario': self.scenario_agent.get_state(),
            'optimization': self.optimization_agent.get_state(),
            'governance': self.governance_agent.get_state()
        }
    
    def get_run_summary(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        """Get summary of a workflow run"""
        if run_id:
            run = next((r for r in self.run_history if r.run_id == run_id), None)
        else:
            run = self.run_history[-1] if self.run_history else None
        
        if not run:
            return {'error': 'No run found'}
        
        return {
            'run_id': run.run_id,
            'status': run.status.value,
            'duration_ms': (
                (run.completed_at - run.started_at).total_seconds() * 1000
                if run.completed_at else None
            ),
            'stages': {k: v.status.value for k, v in run.stage_results.items()},
            'recommendation': run.final_recommendation,
            'decision': run.decision_package.get('decision_status') if run.decision_package else None,
            'requires_approval': run.decision_package.get('requires_human_approval') if run.decision_package else None
        }


def create_iqueue_workflow(
    retailer_id: str,
    segment_id: Optional[str] = None,
    drivers: Optional[List[str]] = None,
    **kwargs
) -> IQueueWorkflow:
    """Factory function for creating iQueue Workflow"""
    config = WorkflowConfig(
        retailer_id=retailer_id,
        segment_id=segment_id,
        drivers=drivers or ['media', 'price', 'trade'],
        **kwargs
    )
    
    return IQueueWorkflow(config)
