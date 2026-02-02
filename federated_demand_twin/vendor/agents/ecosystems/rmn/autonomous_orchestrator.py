"""
RMN Autonomous Multi-Agent Orchestrator

Implements an autonomous multi-agent system with:
- Parallel work tracks
- Agent collaboration and delegation
- Dynamic task routing
- Inter-agent messaging for coordination
"""

import asyncio
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
import threading
import numpy as np

from .agents import (
    RMNDataIngestionAgent,
    RMNAttributionAgent,
    RMNElasticityAgent,
    RMNScenarioAgent,
    RMNTwinAgent,
    RMNOptimizerAgent,
    RMNGovernanceAgent,
    RMNRationaleAgent,
)
from .schemas import (
    RMNConfig,
    ChannelConfig,
    ChannelType,
    MediaSpendData,
    RMNDecisionPack,
)
from ...crewai_base import AgentMessageBus, MessageType, AgentMessage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CollaborationType(str, Enum):
    """Types of agent collaboration"""
    DELEGATION = "delegation"
    INFORMATION_SHARING = "information_sharing"
    CONSENSUS_REQUEST = "consensus_request"
    PARALLEL_EXECUTION = "parallel_execution"
    FEEDBACK_LOOP = "feedback_loop"
    NEGOTIATION = "negotiation"


class TaskStatus(str, Enum):
    """Status of autonomous tasks"""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_COLLABORATION = "waiting_collaboration"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkTrackType(str, Enum):
    """Types of parallel work tracks"""
    DATA_QUALITY = "data_quality"
    ANALYTICS = "analytics"
    SIMULATION = "simulation"
    OPTIMIZATION = "optimization"
    GOVERNANCE = "governance"
    COMMUNICATION = "communication"


@dataclass
class CollaborationEvent:
    """Records an agent collaboration event"""
    event_id: str
    timestamp: datetime
    collaboration_type: CollaborationType
    initiator_agent: str
    target_agents: List[str]
    topic: str
    payload: Dict[str, Any]
    status: str = "active"
    response: Optional[Dict[str, Any]] = None
    duration_ms: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "collaboration_type": self.collaboration_type.value,
            "initiator_agent": self.initiator_agent,
            "target_agents": self.target_agents,
            "topic": self.topic,
            "payload": self.payload,
            "status": self.status,
            "response": self.response,
            "duration_ms": self.duration_ms,
        }


@dataclass
class AutonomousTask:
    """Represents an autonomous task in the system"""
    task_id: str
    name: str
    description: str
    assigned_agents: List[str]
    work_track: WorkTrackType
    dependencies: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 5
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    collaborations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "assigned_agents": self.assigned_agents,
            "work_track": self.work_track.value,
            "dependencies": self.dependencies,
            "status": self.status.value,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "collaborations": self.collaborations,
        }


@dataclass
class ParallelWorkTrack:
    """Represents a parallel work track"""
    track_id: str
    track_type: WorkTrackType
    name: str
    agents: List[str]
    tasks: List[str] = field(default_factory=list)
    status: str = "idle"
    progress: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "track_id": self.track_id,
            "track_type": self.track_type.value,
            "name": self.name,
            "agents": self.agents,
            "tasks": self.tasks,
            "status": self.status,
            "progress": self.progress,
        }


class AutonomousRMNOrchestrator:
    """
    Autonomous Multi-Agent Orchestrator for RMN Optimization.
    
    Features:
    - Parallel work tracks for independent analysis
    - Agent collaboration via message passing
    - Dynamic task delegation
    - Consensus building for critical decisions
    - Real-time collaboration event tracking
    """
    
    def __init__(self, config: RMNConfig):
        self.config = config
        self.message_bus = AgentMessageBus()
        
        # Initialize agents
        self._initialize_agents()
        
        # Work tracks
        self.work_tracks: Dict[str, ParallelWorkTrack] = {}
        self._initialize_work_tracks()
        
        # Task management
        self.tasks: Dict[str, AutonomousTask] = {}
        self.task_queue: List[str] = []
        
        # Collaboration tracking
        self.collaboration_events: List[CollaborationEvent] = []
        self.active_collaborations: Dict[str, CollaborationEvent] = {}
        
        # Shared state for agent collaboration
        self.shared_state: Dict[str, Any] = {
            "beliefs": {},
            "decisions": {},
            "consensus": {},
        }
        
        # Thread pool for parallel execution
        self.executor = ThreadPoolExecutor(max_workers=4)
        self._lock = threading.Lock()
        
        # Run history
        self.run_history: List[RMNDecisionPack] = []
        
        logger.info(f"AutonomousRMNOrchestrator initialized for {config.retailer_name}")
    
    def _initialize_agents(self):
        """Initialize all RMN agents with message bus"""
        channels = self.config.channels
        rid = self.config.retailer_id
        
        self.agents: Dict[str, Any] = {}
        
        self.agents["data"] = RMNDataIngestionAgent(rid, channels, self.message_bus)
        self.agents["attribution"] = RMNAttributionAgent(rid, channels, self.message_bus)
        self.agents["elasticity"] = RMNElasticityAgent(rid, channels, self.message_bus)
        self.agents["scenario"] = RMNScenarioAgent(rid, channels, self.message_bus)
        self.agents["twin"] = RMNTwinAgent(rid, self.message_bus)
        self.agents["optimizer"] = RMNOptimizerAgent(rid, self.message_bus)
        self.agents["governance"] = RMNGovernanceAgent(rid, self.config, self.message_bus)
        self.agents["rationale"] = RMNRationaleAgent(rid, self.message_bus)
        
        # Setup message handlers for collaboration
        for agent_name, agent in self.agents.items():
            self.message_bus.subscribe(
                agent.config.agent_id,
                lambda msg, name=agent_name: self._handle_agent_message(name, msg)
            )
        
        logger.info(f"Initialized {len(self.agents)} autonomous agents")
    
    def _initialize_work_tracks(self):
        """Initialize parallel work tracks"""
        tracks = [
            ("data_quality", WorkTrackType.DATA_QUALITY, "Data Quality Track", ["data"]),
            ("analytics", WorkTrackType.ANALYTICS, "Analytics Track", ["attribution", "elasticity"]),
            ("simulation", WorkTrackType.SIMULATION, "Simulation Track", ["scenario", "twin"]),
            ("optimization", WorkTrackType.OPTIMIZATION, "Optimization Track", ["optimizer"]),
            ("governance", WorkTrackType.GOVERNANCE, "Governance Track", ["governance"]),
            ("communication", WorkTrackType.COMMUNICATION, "Communication Track", ["rationale"]),
        ]
        
        for track_id, track_type, name, agents in tracks:
            self.work_tracks[track_id] = ParallelWorkTrack(
                track_id=track_id,
                track_type=track_type,
                name=name,
                agents=agents,
            )
    
    def _handle_agent_message(self, agent_name: str, message: AgentMessage):
        """Handle inter-agent messages for collaboration"""
        if message.message_type == MessageType.TASK_REQUEST:
            self._handle_delegation_request(agent_name, message)
        elif message.message_type == MessageType.BELIEF_UPDATE:
            self._handle_belief_sharing(agent_name, message)
    
    def _handle_delegation_request(self, agent_name: str, message: AgentMessage):
        """Handle task delegation between agents"""
        event = CollaborationEvent(
            event_id=str(uuid.uuid4())[:8],
            timestamp=datetime.utcnow(),
            collaboration_type=CollaborationType.DELEGATION,
            initiator_agent=agent_name,
            target_agents=[message.recipient_id] if message.recipient_id else [],
            topic="task_delegation",
            payload=message.payload,
        )
        self._record_collaboration(event)
    
    def _handle_belief_sharing(self, agent_name: str, message: AgentMessage):
        """Handle belief sharing between agents"""
        event = CollaborationEvent(
            event_id=str(uuid.uuid4())[:8],
            timestamp=datetime.utcnow(),
            collaboration_type=CollaborationType.INFORMATION_SHARING,
            initiator_agent=agent_name,
            target_agents=["all"],
            topic="belief_update",
            payload=message.payload,
        )
        self._record_collaboration(event)
        
        # Update shared state
        with self._lock:
            belief_id = message.payload.get("belief_id")
            if belief_id:
                self.shared_state["beliefs"][belief_id] = {
                    "agent": agent_name,
                    "value": message.payload.get("new_mean"),
                    "std": message.payload.get("new_std"),
                    "timestamp": datetime.utcnow().isoformat(),
                }
    
    def _record_collaboration(self, event: CollaborationEvent):
        """Record a collaboration event"""
        with self._lock:
            self.collaboration_events.append(event)
            if event.status == "active":
                self.active_collaborations[event.event_id] = event
    
    def _create_task(
        self,
        name: str,
        description: str,
        agents: List[str],
        track: WorkTrackType,
        dependencies: List[str] = None,
        priority: int = 5,
    ) -> AutonomousTask:
        """Create a new autonomous task"""
        task = AutonomousTask(
            task_id=str(uuid.uuid4())[:8],
            name=name,
            description=description,
            assigned_agents=agents,
            work_track=track,
            dependencies=dependencies or [],
            priority=priority,
        )
        self.tasks[task.task_id] = task
        return task
    
    def _initiate_collaboration(
        self,
        collab_type: CollaborationType,
        initiator: str,
        targets: List[str],
        topic: str,
        payload: Dict[str, Any],
    ) -> CollaborationEvent:
        """Initiate a collaboration between agents"""
        event = CollaborationEvent(
            event_id=str(uuid.uuid4())[:8],
            timestamp=datetime.utcnow(),
            collaboration_type=collab_type,
            initiator_agent=initiator,
            target_agents=targets,
            topic=topic,
            payload=payload,
        )
        self._record_collaboration(event)
        
        # Broadcast message to targets
        self.message_bus.publish(AgentMessage(
            message_id=event.event_id,
            message_type=MessageType.TASK_REQUEST,
            sender_id=initiator,
            recipient_id=None if targets == ["all"] else targets[0],
            payload=payload,
        ))
        
        return event
    
    def _complete_collaboration(self, event_id: str, response: Dict[str, Any]):
        """Complete a collaboration event"""
        with self._lock:
            if event_id in self.active_collaborations:
                event = self.active_collaborations[event_id]
                event.status = "completed"
                event.response = response
                event.duration_ms = int(
                    (datetime.utcnow() - event.timestamp).total_seconds() * 1000
                )
                del self.active_collaborations[event_id]
    
    def run_autonomous(
        self,
        spend_data: List[MediaSpendData],
        conversion_paths: List[List[str]],
        current_allocation: Dict[str, float],
        base_revenue: float = 1000000,
    ) -> RMNDecisionPack:
        """
        Run the autonomous multi-agent optimization workflow.
        
        Unlike the sequential workflow, this runs parallel work tracks
        with agent collaboration and dynamic task routing.
        """
        import hashlib
        
        run_id = hashlib.md5(
            f"{datetime.utcnow().isoformat()}_{self.config.retailer_id}".encode()
        ).hexdigest()[:12]
        
        logger.info(f"Starting autonomous workflow run {run_id}")
        
        # Reset state for new run
        self.tasks = {}
        self.collaboration_events = []
        self.active_collaborations = {}
        
        # Phase 1: Parallel Data & Analytics Track
        # Data validation and analytics can run in parallel
        logger.info("Phase 1: Parallel Data & Analytics")
        
        # Create parallel tasks
        data_task = self._create_task(
            "data_validation", "Validate media spend data",
            ["data"], WorkTrackType.DATA_QUALITY, priority=10
        )
        
        attribution_task = self._create_task(
            "attribution_analysis", "Compute multi-touch attribution",
            ["attribution"], WorkTrackType.ANALYTICS, priority=9
        )
        
        elasticity_task = self._create_task(
            "elasticity_estimation", "Estimate channel elasticities",
            ["elasticity"], WorkTrackType.ANALYTICS, priority=9
        )
        
        # Update work tracks
        self.work_tracks["data_quality"].status = "running"
        self.work_tracks["analytics"].status = "running"
        
        # Execute parallel tasks
        validation_result = None
        attribution_result = None
        elasticity_result = None
        
        def run_data_validation():
            nonlocal validation_result
            data_task.status = TaskStatus.RUNNING
            data_task.started_at = datetime.utcnow()
            validation_result = self.agents["data"].validate_data(spend_data)
            data_task.status = TaskStatus.COMPLETED
            data_task.completed_at = datetime.utcnow()
            data_task.result = validation_result
            
            # Collaboration: Share data quality with analytics track
            self._initiate_collaboration(
                CollaborationType.INFORMATION_SHARING,
                "data", ["attribution", "elasticity"],
                "data_quality_report",
                {"quality_score": validation_result["overall_quality"]}
            )
        
        def run_attribution():
            nonlocal attribution_result
            attribution_task.status = TaskStatus.RUNNING
            attribution_task.started_at = datetime.utcnow()
            total_revenue = sum(d.revenue for d in spend_data)
            total_conversions = sum(d.conversions for d in spend_data)
            attribution_result = self.agents["attribution"].compute_attribution(
                conversion_paths, total_revenue, total_conversions
            )
            attribution_task.status = TaskStatus.COMPLETED
            attribution_task.completed_at = datetime.utcnow()
            attribution_task.result = attribution_result.to_dict()
            
            # Collaboration: Share attribution insights
            self._initiate_collaboration(
                CollaborationType.INFORMATION_SHARING,
                "attribution", ["scenario", "optimizer"],
                "attribution_shares",
                {"channel_shares": attribution_result.channel_shares}
            )
        
        def run_elasticity():
            nonlocal elasticity_result
            elasticity_task.status = TaskStatus.RUNNING
            elasticity_task.started_at = datetime.utcnow()
            
            # Group spend data by channel
            channel_data: Dict[str, Dict[str, List]] = {}
            for record in spend_data:
                if record.channel_id not in channel_data:
                    channel_data[record.channel_id] = {"spend": [], "revenue": []}
                channel_data[record.channel_id]["spend"].append(record.spend)
                channel_data[record.channel_id]["revenue"].append(record.revenue)
            
            for channel_id, data in channel_data.items():
                if len(data["spend"]) >= 10:
                    self.agents["elasticity"].estimate_elasticity(
                        channel_id,
                        np.array(data["spend"]),
                        np.array(data["revenue"])
                    )
            
            elasticity_result = self.agents["elasticity"].get_all_posteriors()
            elasticity_task.status = TaskStatus.COMPLETED
            elasticity_task.completed_at = datetime.utcnow()
            elasticity_task.result = {k: v.to_dict() for k, v in elasticity_result.items()}
            
            # Collaboration: Share elasticity beliefs
            for channel_id, posterior in elasticity_result.items():
                self._initiate_collaboration(
                    CollaborationType.INFORMATION_SHARING,
                    "elasticity", ["scenario", "twin", "optimizer"],
                    f"elasticity_posterior_{channel_id}",
                    {"channel_id": channel_id, "mean": posterior.mean, "std": posterior.std}
                )
        
        # Run Phase 1 in parallel
        futures = [
            self.executor.submit(run_data_validation),
            self.executor.submit(run_attribution),
            self.executor.submit(run_elasticity),
        ]
        
        # Wait for Phase 1 completion
        for f in futures:
            f.result()
        
        self.work_tracks["data_quality"].progress = 1.0
        self.work_tracks["data_quality"].status = "completed"
        self.work_tracks["analytics"].progress = 1.0
        self.work_tracks["analytics"].status = "completed"
        
        logger.info("Phase 1 complete - Data and Analytics tracks finished")
        
        # Phase 2: Simulation Track (depends on analytics)
        logger.info("Phase 2: Simulation Track")
        self.work_tracks["simulation"].status = "running"
        
        # Scenario agent collaborates with elasticity agent
        scenario_collab = self._initiate_collaboration(
            CollaborationType.CONSENSUS_REQUEST,
            "scenario", ["elasticity"],
            "scenario_design_consensus",
            {"request": "Validate scenario assumptions with elasticity beliefs"}
        )
        
        scenario_task = self._create_task(
            "scenario_generation", "Generate allocation scenarios",
            ["scenario"], WorkTrackType.SIMULATION,
            dependencies=[elasticity_task.task_id], priority=8
        )
        scenario_task.status = TaskStatus.RUNNING
        scenario_task.started_at = datetime.utcnow()
        
        scenarios = self.agents["scenario"].generate_scenarios(
            current_allocation,
            self.config.total_budget,
            elasticity_result,
            n_scenarios=self.config.n_scenarios
        )
        
        scenario_task.status = TaskStatus.COMPLETED
        scenario_task.completed_at = datetime.utcnow()
        scenario_task.result = {"n_scenarios": len(scenarios)}
        
        self._complete_collaboration(scenario_collab.event_id, {"scenarios_generated": len(scenarios)})
        
        # Twin simulates all scenarios - parallel within track
        simulation_task = self._create_task(
            "monte_carlo_simulation", "Run Monte Carlo simulations for all scenarios",
            ["twin"], WorkTrackType.SIMULATION,
            dependencies=[scenario_task.task_id], priority=7
        )
        simulation_task.status = TaskStatus.RUNNING
        simulation_task.started_at = datetime.utcnow()
        
        # Parallel scenario simulation
        simulations = {}
        
        def simulate_scenario(scenario):
            return scenario.scenario_id, self.agents["twin"].simulate(
                scenario, elasticity_result,
                base_revenue=base_revenue,
                n_simulations=self.config.n_simulations
            )
        
        sim_futures = [self.executor.submit(simulate_scenario, s) for s in scenarios]
        for f in sim_futures:
            scenario_id, result = f.result()
            simulations[scenario_id] = result
            
            # Collaboration: Twin shares simulation results
            self._initiate_collaboration(
                CollaborationType.INFORMATION_SHARING,
                "twin", ["optimizer", "governance"],
                f"simulation_result_{scenario_id}",
                {"scenario_id": scenario_id, "expected_revenue": result.expected_revenue}
            )
        
        simulation_task.status = TaskStatus.COMPLETED
        simulation_task.completed_at = datetime.utcnow()
        simulation_task.result = {"n_simulations": len(simulations)}
        
        self.work_tracks["simulation"].progress = 1.0
        self.work_tracks["simulation"].status = "completed"
        
        logger.info("Phase 2 complete - Simulation track finished")
        
        # Phase 3: Optimization & Governance (parallel with collaboration)
        logger.info("Phase 3: Parallel Optimization & Governance")
        self.work_tracks["optimization"].status = "running"
        self.work_tracks["governance"].status = "running"
        
        # Optimizer and Governance work in parallel with negotiation
        optimization_result = None
        governance_result = None
        
        def run_optimization():
            nonlocal optimization_result
            opt_task = self._create_task(
                "budget_optimization", "Select optimal allocation",
                ["optimizer"], WorkTrackType.OPTIMIZATION, priority=6
            )
            opt_task.status = TaskStatus.RUNNING
            opt_task.started_at = datetime.utcnow()
            
            optimization_result = self.agents["optimizer"].optimize(
                simulations, risk_aversion=self.config.risk_aversion
            )
            
            opt_task.status = TaskStatus.COMPLETED
            opt_task.completed_at = datetime.utcnow()
            opt_task.result = optimization_result.to_dict()
            
            # Negotiation with governance
            self._initiate_collaboration(
                CollaborationType.NEGOTIATION,
                "optimizer", ["governance"],
                "allocation_proposal",
                {
                    "proposed_allocation": optimization_result.optimal_allocation,
                    "expected_revenue": optimization_result.expected_revenue,
                }
            )
        
        def run_governance_parallel():
            nonlocal governance_result
            gov_task = self._create_task(
                "governance_validation", "Validate against policies",
                ["governance"], WorkTrackType.GOVERNANCE, priority=6
            )
            gov_task.status = TaskStatus.RUNNING
            gov_task.started_at = datetime.utcnow()
            
            # Wait briefly for optimization to complete
            while optimization_result is None:
                pass
            
            governance_result = self.agents["governance"].validate(
                optimization_result, current_allocation
            )
            
            gov_task.status = TaskStatus.COMPLETED
            gov_task.completed_at = datetime.utcnow()
            gov_task.result = governance_result.to_dict()
            
            # Feedback to optimizer if violations found
            if governance_result.violations:
                self._initiate_collaboration(
                    CollaborationType.FEEDBACK_LOOP,
                    "governance", ["optimizer"],
                    "policy_violations",
                    {"violations": governance_result.violations}
                )
        
        opt_future = self.executor.submit(run_optimization)
        gov_future = self.executor.submit(run_governance_parallel)
        
        opt_future.result()
        gov_future.result()
        
        self.work_tracks["optimization"].progress = 1.0
        self.work_tracks["optimization"].status = "completed"
        self.work_tracks["governance"].progress = 1.0
        self.work_tracks["governance"].status = "completed"
        
        logger.info("Phase 3 complete - Optimization & Governance tracks finished")
        
        # Phase 4: Communication Track
        logger.info("Phase 4: Communication Track")
        self.work_tracks["communication"].status = "running"
        
        rationale_task = self._create_task(
            "rationale_generation", "Generate recommendation rationale",
            ["rationale"], WorkTrackType.COMMUNICATION, priority=5
        )
        rationale_task.status = TaskStatus.RUNNING
        rationale_task.started_at = datetime.utcnow()
        
        # Rationale agent collaborates with all agents for comprehensive explanation
        self._initiate_collaboration(
            CollaborationType.CONSENSUS_REQUEST,
            "rationale", ["attribution", "elasticity", "optimizer", "governance"],
            "rationale_inputs",
            {"request": "Provide key findings for recommendation rationale"}
        )
        
        rationale = self.agents["rationale"].generate_rationale(
            optimization_result, simulations, governance_result, elasticity_result
        )
        
        rationale_task.status = TaskStatus.COMPLETED
        rationale_task.completed_at = datetime.utcnow()
        rationale_task.result = rationale
        
        self.work_tracks["communication"].progress = 1.0
        self.work_tracks["communication"].status = "completed"
        
        logger.info("Phase 4 complete - Communication track finished")
        
        # Build decision pack
        decision_pack = RMNDecisionPack(
            pack_id=run_id,
            retailer_id=self.config.retailer_id,
            created_at=datetime.utcnow(),
            attribution=attribution_result,
            elasticities=elasticity_result,
            scenarios=scenarios,
            simulations=simulations,
            optimization=optimization_result,
            governance=governance_result,
            executive_summary=rationale["executive_summary"],
            detailed_rationale=rationale["detailed_rationale"],
            uncertainty_acknowledgment=rationale["uncertainty_acknowledgment"],
            status="completed" if governance_result.approved else "pending_review",
            confidence_score=0.85 if governance_result.approved else 0.6,
        )
        
        self.run_history.append(decision_pack)
        
        logger.info(f"Autonomous workflow complete: {decision_pack.status}")
        logger.info(f"Total collaborations: {len(self.collaboration_events)}")
        
        return decision_pack
    
    def get_workflow_state(self) -> Dict[str, Any]:
        """Get current workflow state for UI visualization"""
        return {
            "work_tracks": [t.to_dict() for t in self.work_tracks.values()],
            "tasks": [t.to_dict() for t in self.tasks.values()],
            "collaboration_events": [e.to_dict() for e in self.collaboration_events[-50:]],
            "active_collaborations": [e.to_dict() for e in self.active_collaborations.values()],
            "shared_state": self.shared_state,
        }
    
    def get_agent_collaboration_graph(self) -> Dict[str, Any]:
        """Get agent collaboration graph for visualization"""
        edges = []
        edge_counts: Dict[str, int] = {}
        
        for event in self.collaboration_events:
            for target in event.target_agents:
                key = f"{event.initiator_agent}->{target}"
                edge_counts[key] = edge_counts.get(key, 0) + 1
        
        for key, count in edge_counts.items():
            source, target = key.split("->")
            edges.append({
                "source": source,
                "target": target,
                "count": count,
                "weight": min(count / 5, 1.0),
            })
        
        return {
            "nodes": [
                {"id": name, "role": agent.config.role.value}
                for name, agent in self.agents.items()
            ],
            "edges": edges,
        }
    
    def get_parallel_tracks_status(self) -> List[Dict[str, Any]]:
        """Get status of all parallel work tracks"""
        return [track.to_dict() for track in self.work_tracks.values()]


def create_autonomous_rmn_orchestrator(
    retailer_id: str,
    retailer_name: str,
    channels: Optional[List[Dict[str, Any]]] = None,
    **kwargs
) -> AutonomousRMNOrchestrator:
    """Factory function for autonomous RMN orchestrator"""
    
    if channels is None:
        channels = [
            {"channel_id": "sponsored_search", "channel_type": ChannelType.SPONSORED_SEARCH, "name": "Sponsored Search"},
            {"channel_id": "sponsored_product", "channel_type": ChannelType.SPONSORED_PRODUCT, "name": "Sponsored Product"},
            {"channel_id": "display", "channel_type": ChannelType.DISPLAY, "name": "Display Ads"},
            {"channel_id": "video", "channel_type": ChannelType.VIDEO, "name": "Video"},
            {"channel_id": "email", "channel_type": ChannelType.EMAIL, "name": "Email"},
        ]
    
    channel_configs = [
        ChannelConfig(
            channel_id=c.get("channel_id", f"channel_{i}"),
            channel_type=c.get("channel_type", ChannelType.DISPLAY),
            name=c.get("name", f"Channel {i}"),
            min_spend=c.get("min_spend", 0),
            max_spend=c.get("max_spend", float('inf')),
            prior_elasticity_mean=c.get("prior_elasticity_mean", 0.15),
            prior_elasticity_std=c.get("prior_elasticity_std", 0.05),
        )
        for i, c in enumerate(channels)
    ]
    
    config = RMNConfig(
        retailer_id=retailer_id,
        retailer_name=retailer_name,
        channels=channel_configs,
        **kwargs
    )
    
    return AutonomousRMNOrchestrator(config)
