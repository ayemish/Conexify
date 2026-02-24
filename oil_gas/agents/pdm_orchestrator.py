"""
PdM Agent Orchestrator

Supervises and coordinates the 7 PdM agents, managing:
- Agent lifecycle and health
- Workflow orchestration
- Action approval routing
- Cross-agent communication
- API endpoints for UI integration
"""

import logging
import uuid
import asyncio
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import threading
import json

from shared.utils import optional_import

from shared.agents.crewai_base import (
    DemandTwinAgent, CrewAIAgentConfig, AgentCategory, AgentRole,
    AgentRegistry, Crew, Task, Process, CREWAI_AVAILABLE
)
from .redis_event_bus import (
    RedisEventBus, PdMEvent, PdMEventType, PdMEventFactory,
    InMemoryEventBus
)
from .pdm_agents import (
    PdMAgent, PdMAgentFactory,
    CaseTriageAgent, EvidenceToActionAgent, WorkOrderComposerAgent,
    DispatchBatchingAgent, VerificationAgent, ExperimentationAgent,
    DataStewardAgent
)

logger = logging.getLogger(__name__)


# =============================================================================
# Workflow Definitions
# =============================================================================

class WorkflowType(str, Enum):
    """Pre-defined agent workflows"""
    ALERT_TO_DISPATCH = "alert_to_dispatch"
    CASE_TRIAGE = "case_triage"
    WORK_ORDER_CREATION = "work_order_creation"
    VERIFICATION_LOOP = "verification_loop"
    MODEL_GOVERNANCE = "model_governance"
    DATA_QUALITY_RESPONSE = "data_quality_response"


@dataclass
class WorkflowStep:
    """Single step in a workflow"""
    step_id: str
    agent_name: str
    action: str
    inputs: Dict[str, Any]
    outputs: Optional[Dict[str, Any]] = None
    status: str = "pending"  # pending | running | completed | failed
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


@dataclass
class WorkflowExecution:
    """Execution of a workflow"""
    execution_id: str
    workflow_type: WorkflowType
    triggered_by: str
    trigger_event_id: Optional[str]
    steps: List[WorkflowStep]
    status: str = "running"  # running | completed | failed | paused
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None


# =============================================================================
# Action Approval System
# =============================================================================

@dataclass
class PendingApproval:
    """Action pending human approval"""
    approval_id: str
    action_id: str
    agent_id: str
    action_type: str
    description: str
    payload: Dict[str, Any]
    priority: str
    created_at: datetime
    expires_at: Optional[datetime]
    status: str = "pending"  # pending | approved | rejected | expired
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None


class ApprovalRouter:
    """Routes actions to appropriate approvers"""
    
    def __init__(self):
        self.pending_approvals: Dict[str, PendingApproval] = {}
        self.approval_callbacks: Dict[str, Callable] = {}
    
    def submit_for_approval(
        self,
        action: Dict[str, Any],
        expiry_hours: float = 24.0
    ) -> PendingApproval:
        """Submit an action for approval"""
        approval = PendingApproval(
            approval_id=str(uuid.uuid4()),
            action_id=action["action_id"],
            agent_id=action["agent_id"],
            action_type=action["action_type"],
            description=action["description"],
            payload=action["payload"],
            priority=action.get("priority", "medium"),
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=expiry_hours),
        )
        self.pending_approvals[approval.approval_id] = approval
        return approval
    
    def approve(
        self,
        approval_id: str,
        approved_by: str,
        notes: Optional[str] = None
    ) -> Optional[PendingApproval]:
        """Approve a pending action"""
        approval = self.pending_approvals.get(approval_id)
        if not approval or approval.status != "pending":
            return None
        
        approval.status = "approved"
        approval.approved_by = approved_by
        approval.approved_at = datetime.utcnow()
        
        # Execute callback if registered
        if approval_id in self.approval_callbacks:
            self.approval_callbacks[approval_id](approval)
        
        return approval
    
    def reject(
        self,
        approval_id: str,
        rejected_by: str,
        reason: str
    ) -> Optional[PendingApproval]:
        """Reject a pending action"""
        approval = self.pending_approvals.get(approval_id)
        if not approval or approval.status != "pending":
            return None
        
        approval.status = "rejected"
        approval.approved_by = rejected_by
        approval.approved_at = datetime.utcnow()
        approval.rejection_reason = reason
        
        return approval
    
    def get_pending(self, priority: Optional[str] = None) -> List[PendingApproval]:
        """Get pending approvals"""
        pending = [a for a in self.pending_approvals.values() if a.status == "pending"]
        if priority:
            pending = [a for a in pending if a.priority == priority]
        return sorted(pending, key=lambda x: x.created_at, reverse=True)
    
    def register_callback(self, approval_id: str, callback: Callable):
        """Register callback for when approval is granted"""
        self.approval_callbacks[approval_id] = callback


# =============================================================================
# PdM Orchestrator
# =============================================================================

class PdMOrchestrator:
    """
    Central orchestrator for PdM agents.
    
    Responsibilities:
    - Initialize and manage agent lifecycle
    - Coordinate multi-agent workflows
    - Route actions through approval system
    - Provide API for UI integration
    - Monitor agent health and performance
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        use_redis: bool = True,
    ):
        # Event bus
        if use_redis:
            self.event_bus = RedisEventBus(
                redis_url=redis_url,
                agent_id="orchestrator"
            )
        else:
            self.event_bus = InMemoryEventBus("orchestrator")
        
        self.event_factory = PdMEventFactory("orchestrator")
        
        # Agent factory and agents
        self.agent_factory = PdMAgentFactory(self.event_bus)
        self.agents: Dict[str, PdMAgent] = {}
        
        # Approval system
        self.approval_router = ApprovalRouter()
        
        # Workflow tracking
        self.workflows: Dict[str, WorkflowExecution] = {}
        
        # Conversation history for chat interface
        self.conversations: Dict[str, List[Dict[str, Any]]] = {}
        
        # Running state
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        
        logger.info("PdM Orchestrator initialized")
    
    def start(self):
        """Start the orchestrator and all agents"""
        # Create all agents
        self.agents = self.agent_factory.create_all_agents()
        
        # Register agents with event bus
        for name, agent in self.agents.items():
            self.event_bus.register_agent(agent.config.agent_id, {
                "name": name,
                "role": agent.config.role.value if hasattr(agent.config.role, 'value') else str(agent.config.role),
                "category": agent.config.category.value,
            })
        
        # Start event bus listener
        self.event_bus.start_listening()
        
        # Start health monitor
        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._health_monitor_loop,
            daemon=True
        )
        self._monitor_thread.start()
        
        logger.info(f"Orchestrator started with {len(self.agents)} agents")
    
    def stop(self):
        """Stop the orchestrator and all agents"""
        self._running = False
        self.event_bus.stop_listening()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        logger.info("Orchestrator stopped")
    
    def _health_monitor_loop(self):
        """Monitor agent health periodically"""
        while self._running:
            try:
                # Send heartbeats
                self.event_bus.send_heartbeat()
                
                # Check for stale approvals
                self._expire_stale_approvals()
                
                threading.Event().wait(30)  # Check every 30 seconds
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
    
    def _expire_stale_approvals(self):
        """Expire approvals that have passed their deadline"""
        now = datetime.utcnow()
        for approval in list(self.approval_router.pending_approvals.values()):
            if approval.status == "pending" and approval.expires_at and approval.expires_at < now:
                approval.status = "expired"
    
    # =========================================================================
    # Workflow Orchestration
    # =========================================================================
    
    def execute_workflow(
        self,
        workflow_type: WorkflowType,
        trigger_event: Optional[PdMEvent] = None,
        inputs: Optional[Dict[str, Any]] = None
    ) -> WorkflowExecution:
        """Execute a pre-defined workflow"""
        execution = WorkflowExecution(
            execution_id=str(uuid.uuid4()),
            workflow_type=workflow_type,
            triggered_by="orchestrator",
            trigger_event_id=trigger_event.event_id if trigger_event else None,
            steps=self._get_workflow_steps(workflow_type, inputs or {}),
        )
        
        self.workflows[execution.execution_id] = execution
        
        # Execute steps
        self._run_workflow(execution)
        
        return execution
    
    def _get_workflow_steps(
        self,
        workflow_type: WorkflowType,
        inputs: Dict[str, Any]
    ) -> List[WorkflowStep]:
        """Get steps for a workflow type"""
        if workflow_type == WorkflowType.ALERT_TO_DISPATCH:
            return [
                WorkflowStep(str(uuid.uuid4()), "triage", "triage_alert", inputs),
                WorkflowStep(str(uuid.uuid4()), "evidence", "generate_packet", {}),
                WorkflowStep(str(uuid.uuid4()), "work_order", "compose_work_order", {}),
                WorkflowStep(str(uuid.uuid4()), "dispatch", "evaluate_batching", {}),
            ]
        elif workflow_type == WorkflowType.CASE_TRIAGE:
            return [
                WorkflowStep(str(uuid.uuid4()), "triage", "cluster_and_triage", inputs),
            ]
        elif workflow_type == WorkflowType.VERIFICATION_LOOP:
            return [
                WorkflowStep(str(uuid.uuid4()), "verification", "start_verification", inputs),
                WorkflowStep(str(uuid.uuid4()), "verification", "run_verification_check", {}),
            ]
        elif workflow_type == WorkflowType.MODEL_GOVERNANCE:
            return [
                WorkflowStep(str(uuid.uuid4()), "experimentation", "analyze_experiment", inputs),
            ]
        elif workflow_type == WorkflowType.DATA_QUALITY_RESPONSE:
            return [
                WorkflowStep(str(uuid.uuid4()), "data_steward", "diagnose_and_remediate", inputs),
            ]
        else:
            return []
    
    def _run_workflow(self, execution: WorkflowExecution):
        """Run workflow steps"""
        for step in execution.steps:
            try:
                step.status = "running"
                step.started_at = datetime.utcnow()
                
                agent = self.agents.get(step.agent_name)
                if not agent:
                    step.status = "failed"
                    step.error = f"Agent {step.agent_name} not found"
                    continue
                
                # Execute step (simplified - in production would use CrewAI tasks)
                step.outputs = {"status": "executed"}
                step.status = "completed"
                step.completed_at = datetime.utcnow()
                
            except Exception as e:
                step.status = "failed"
                step.error = str(e)
                execution.status = "failed"
                return
        
        execution.status = "completed"
        execution.completed_at = datetime.utcnow()
    
    # =========================================================================
    # API Methods for UI Integration
    # =========================================================================
    
    def get_agent_statuses(self) -> List[Dict[str, Any]]:
        """Get status of all agents for UI display"""
        return [agent.get_agent_status() for agent in self.agents.values()]
    
    def get_pending_approvals(self, priority: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get pending approvals for UI"""
        approvals = self.approval_router.get_pending(priority)
        return [
            {
                "approval_id": a.approval_id,
                "action_type": a.action_type,
                "agent_id": a.agent_id,
                "description": a.description,
                "priority": a.priority,
                "created_at": a.created_at.isoformat(),
                "expires_at": a.expires_at.isoformat() if a.expires_at else None,
                "payload": a.payload,
            }
            for a in approvals
        ]
    
    def approve_action(self, approval_id: str, user_id: str) -> Dict[str, Any]:
        """Approve an action"""
        approval = self.approval_router.approve(approval_id, user_id)
        if not approval:
            return {"error": "Approval not found or already processed"}
        
        # Find and execute the agent action
        for agent in self.agents.values():
            if agent.config.agent_id == approval.agent_id:
                result = agent.execute_action(approval.action_id)
                return {"status": "approved", "result": result}
        
        return {"status": "approved", "result": None}
    
    def reject_action(self, approval_id: str, user_id: str, reason: str) -> Dict[str, Any]:
        """Reject an action"""
        approval = self.approval_router.reject(approval_id, user_id, reason)
        if not approval:
            return {"error": "Approval not found or already processed"}
        return {"status": "rejected", "reason": reason}
    
    def get_recent_events(
        self,
        event_types: Optional[List[str]] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get recent events for activity feed"""
        types = [PdMEventType(t) for t in event_types] if event_types else None
        events = self.event_bus.get_events(event_types=types, limit=limit)
        return [e.to_dict() for e in events]
    
    def get_workflow_status(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get workflow execution status"""
        execution = self.workflows.get(execution_id)
        if not execution:
            return None
        
        return {
            "execution_id": execution.execution_id,
            "workflow_type": execution.workflow_type.value,
            "status": execution.status,
            "created_at": execution.created_at.isoformat(),
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            "steps": [
                {
                    "step_id": s.step_id,
                    "agent": s.agent_name,
                    "action": s.action,
                    "status": s.status,
                    "error": s.error,
                }
                for s in execution.steps
            ],
        }
    
    def get_agent_actions(self, agent_name: str) -> Dict[str, Any]:
        """Get actions for a specific agent"""
        agent = self.agents.get(agent_name)
        if not agent:
            return {"error": "Agent not found"}
        
        return {
            "agent_id": agent.config.agent_id,
            "pending_actions": agent.pending_actions,
            "completed_actions": agent.completed_actions[-20:],
            "action_history": agent.action_history[-20:],
        }
    
    # =========================================================================
    # Chat Interface
    # =========================================================================
    
    def create_conversation(self, user_id: str) -> str:
        """Create a new conversation"""
        conversation_id = str(uuid.uuid4())
        self.conversations[conversation_id] = [{
            "role": "system",
            "content": "You are a PdM assistant that helps operators understand and manage predictive maintenance cases, alerts, and work orders.",
            "timestamp": datetime.utcnow().isoformat(),
        }]
        return conversation_id
    
    def send_message(
        self,
        conversation_id: str,
        message: str,
        user_id: str
    ) -> Dict[str, Any]:
        """Send a message to the chat interface"""
        if conversation_id not in self.conversations:
            return {"error": "Conversation not found"}
        
        # Add user message
        self.conversations[conversation_id].append({
            "role": "user",
            "content": message,
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
        })
        
        # Generate response (in production, this would use LLM)
        response = self._generate_chat_response(conversation_id, message)
        
        # Add assistant response
        self.conversations[conversation_id].append({
            "role": "assistant",
            "content": response["message"],
            "timestamp": datetime.utcnow().isoformat(),
            "actions": response.get("actions", []),
            "data": response.get("data"),
        })
        
        return response
    
    def _generate_chat_response(
        self,
        conversation_id: str,
        message: str
    ) -> Dict[str, Any]:
        """Generate chat response based on message intent"""
        message_lower = message.lower()
        
        # Intent detection and response generation
        if "pending" in message_lower and "approval" in message_lower:
            approvals = self.get_pending_approvals()
            if approvals:
                return {
                    "message": f"There are {len(approvals)} pending approvals. Here are the most recent:",
                    "data": {"approvals": approvals[:5]},
                    "actions": [
                        {"type": "view_approvals", "label": "View All Approvals"},
                    ],
                }
            else:
                return {"message": "There are no pending approvals at this time."}
        
        elif "agent" in message_lower and ("status" in message_lower or "health" in message_lower):
            statuses = self.get_agent_statuses()
            return {
                "message": f"All {len(statuses)} agents are operational:",
                "data": {"agents": statuses},
            }
        
        elif "case" in message_lower and ("triage" in message_lower or "cluster" in message_lower):
            triage_agent = self.agents.get("triage")
            if triage_agent:
                clusters = list(triage_agent.clusters.values())[-5:]
                return {
                    "message": f"The triage agent has {len(triage_agent.clusters)} active clusters.",
                    "data": {"clusters": [
                        {
                            "cluster_id": c.cluster_id,
                            "alert_count": len(c.alert_ids),
                            "severity": c.severity,
                            "decision": c.triage_decision,
                        }
                        for c in clusters
                    ]},
                }
        
        elif "dispatch" in message_lower and "batch" in message_lower:
            dispatch_agent = self.agents.get("dispatch")
            if dispatch_agent:
                batches = list(dispatch_agent.batches.values())[-5:]
                return {
                    "message": f"There are {len(dispatch_agent.batches)} dispatch batches.",
                    "data": {"batches": [
                        {
                            "batch_id": b.batch_id,
                            "site_id": b.site_id,
                            "work_orders": len(b.work_order_ids),
                            "estimated_savings": b.estimated_savings,
                            "status": b.status,
                        }
                        for b in batches
                    ]},
                }
        
        elif "data" in message_lower and "quality" in message_lower:
            steward = self.agents.get("data_steward")
            if steward:
                issues = list(steward.known_issues.values())[-5:]
                return {
                    "message": f"The data steward is tracking {len(steward.known_issues)} data quality issues.",
                    "data": {"issues": issues},
                }
        
        else:
            return {
                "message": "I can help you with:\n- Checking pending approvals\n- Viewing agent status\n- Case triage and clustering\n- Dispatch batches\n- Data quality issues\n\nWhat would you like to know?",
            }
    
    def get_conversation(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Get conversation history"""
        return self.conversations.get(conversation_id, [])


# =============================================================================
# API Endpoints (for FastAPI integration)
# =============================================================================

def create_api_routes(orchestrator: PdMOrchestrator):
    """Create FastAPI routes for the orchestrator"""
    fastapi_mod = optional_import("fastapi", feature_name="oil_gas_agent_routes", logger=logger)
    pydantic_mod = optional_import("pydantic", feature_name="oil_gas_agent_routes", logger=logger)
    if fastapi_mod is None or pydantic_mod is None:
        logger.warning("FastAPI not installed, API routes not available")
        return None
    APIRouter = fastapi_mod.APIRouter
    HTTPException = fastapi_mod.HTTPException
    BaseModel = pydantic_mod.BaseModel
    
    router = APIRouter(prefix="/api/agents", tags=["agents"])
    
    class ApprovalRequest(BaseModel):
        user_id: str
        reason: Optional[str] = None
    
    class ChatMessage(BaseModel):
        message: str
        user_id: str
    
    @router.get("/status")
    def get_agents_status():
        return orchestrator.get_agent_statuses()
    
    @router.get("/approvals")
    def get_pending_approvals(priority: Optional[str] = None):
        return orchestrator.get_pending_approvals(priority)
    
    @router.post("/approvals/{approval_id}/approve")
    def approve_action(approval_id: str, request: ApprovalRequest):
        result = orchestrator.approve_action(approval_id, request.user_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    
    @router.post("/approvals/{approval_id}/reject")
    def reject_action(approval_id: str, request: ApprovalRequest):
        if not request.reason:
            raise HTTPException(status_code=400, detail="Reason required for rejection")
        result = orchestrator.reject_action(approval_id, request.user_id, request.reason)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    
    @router.get("/events")
    def get_recent_events(limit: int = 50):
        return orchestrator.get_recent_events(limit=limit)
    
    @router.get("/{agent_name}/actions")
    def get_agent_actions(agent_name: str):
        result = orchestrator.get_agent_actions(agent_name)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    
    @router.post("/chat")
    def create_chat(user_id: str):
        conversation_id = orchestrator.create_conversation(user_id)
        return {"conversation_id": conversation_id}
    
    @router.post("/chat/{conversation_id}")
    def send_chat_message(conversation_id: str, request: ChatMessage):
        result = orchestrator.send_message(
            conversation_id, request.message, request.user_id
        )
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    
    @router.get("/chat/{conversation_id}")
    def get_chat_history(conversation_id: str):
        history = orchestrator.get_conversation(conversation_id)
        if not history:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return history
    
    return router


# =============================================================================
# Singleton Orchestrator Instance
# =============================================================================

_orchestrator_instance: Optional[PdMOrchestrator] = None


def get_orchestrator(
    redis_url: str = "redis://localhost:6379",
    use_redis: bool = False  # Default to in-memory for development
) -> PdMOrchestrator:
    """Get or create the singleton orchestrator instance"""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = PdMOrchestrator(
            redis_url=redis_url,
            use_redis=use_redis
        )
    return _orchestrator_instance
