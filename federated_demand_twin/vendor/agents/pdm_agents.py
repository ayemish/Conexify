"""
Predictive Maintenance (PdM) Agents

CrewAI-compliant agents for predictive maintenance workflows.
These agents are additive to the existing platform - they consume
events and outputs, perform multi-step reasoning, and propose/execute
permissioned actions through existing typed interfaces.

Agents:
1. Case Triage & De-duplication Agent - Noise suppression
2. Evidence-to-Action Agent - Technician-ready work packages
3. Work Order Composer Agent - CMMS-ready drafting
4. Dispatch Batching & Scheduling Agent - ROI optimization
5. Verification & Reopen Agent - Telemetry-based verification
6. Experimentation & Model Promotion Agent - Governance automation
7. Data Steward / Integration Agent - Data quality management
"""

import logging
import uuid
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from abc import abstractmethod

from .crewai_base import (
    DemandTwinAgent, CrewAIAgentConfig, AgentCategory, AgentRole,
    BaseTool, AgentRegistry, BeliefState, CREWAI_AVAILABLE,
    Agent, Task, Crew, Process
)
from .redis_event_bus import (
    RedisEventBus, PdMEvent, PdMEventType, PdMEventFactory,
    EventHandler, InMemoryEventBus
)

logger = logging.getLogger(__name__)


# =============================================================================
# Extended Agent Roles for PdM
# =============================================================================

class PdMAgentRole(str, Enum):
    """PdM-specific agent roles"""
    CASE_TRIAGE = "case_triage"
    EVIDENCE_TO_ACTION = "evidence_to_action"
    WORK_ORDER_COMPOSER = "work_order_composer"
    DISPATCH_BATCHER = "dispatch_batcher"
    VERIFICATION = "verification"
    EXPERIMENTATION = "experimentation"
    DATA_STEWARD = "data_steward"


# =============================================================================
# Base PdM Agent
# =============================================================================

class PdMAgent(DemandTwinAgent, EventHandler):
    """
    Base class for all PdM agents.
    
    Extends DemandTwinAgent with:
    - Redis event bus integration
    - Event handling capabilities
    - PdM-specific tools and context
    """
    
    def __init__(
        self,
        config: CrewAIAgentConfig,
        event_bus: Optional[RedisEventBus] = None,
        **kwargs
    ):
        super().__init__(config, **kwargs)
        self.event_bus = event_bus or InMemoryEventBus(config.agent_id)
        self.event_factory = PdMEventFactory(config.agent_id)
        
        # Register as event handler
        self.event_bus.register_handler(self)
        
        # Agent-specific state
        self.pending_actions: List[Dict[str, Any]] = []
        self.completed_actions: List[Dict[str, Any]] = []
    
    @property
    @abstractmethod
    def handled_event_types(self) -> List[PdMEventType]:
        """Event types this agent handles"""
        pass
    
    @abstractmethod
    def handle(self, event: PdMEvent) -> Optional[PdMEvent]:
        """Handle an incoming event"""
        pass
    
    def propose_action(
        self,
        action_type: str,
        description: str,
        payload: Dict[str, Any],
        requires_approval: bool = True,
        priority: str = "medium",
    ) -> Dict[str, Any]:
        """Propose an action for approval or execution"""
        action = {
            "action_id": str(uuid.uuid4()),
            "agent_id": self.config.agent_id,
            "action_type": action_type,
            "description": description,
            "payload": payload,
            "requires_approval": requires_approval,
            "priority": priority,
            "status": "pending_approval" if requires_approval else "ready",
            "proposed_at": datetime.utcnow().isoformat(),
        }
        self.pending_actions.append(action)
        return action
    
    def execute_action(self, action_id: str) -> Dict[str, Any]:
        """Execute an approved action"""
        action = next((a for a in self.pending_actions if a["action_id"] == action_id), None)
        if not action:
            return {"error": "Action not found"}
        
        self.pending_actions.remove(action)
        action["status"] = "executed"
        action["executed_at"] = datetime.utcnow().isoformat()
        self.completed_actions.append(action)
        
        return action
    
    def get_agent_status(self) -> Dict[str, Any]:
        """Get current agent status for UI"""
        return {
            "agent_id": self.config.agent_id,
            "role": self.config.role.value if hasattr(self.config.role, 'value') else str(self.config.role),
            "pending_actions": len(self.pending_actions),
            "completed_actions": len(self.completed_actions),
            "beliefs": len(self.beliefs),
            "last_activity": self.action_history[-1]["timestamp"] if self.action_history else None,
        }


# =============================================================================
# 1. Case Triage & De-duplication Agent
# =============================================================================

@dataclass
class AlertCluster:
    """Cluster of related alerts"""
    cluster_id: str
    alert_ids: List[str]
    asset_id: str
    site_id: str
    signature: str
    first_alert_time: datetime
    last_alert_time: datetime
    total_ev: float
    severity: str
    triage_decision: Optional[str] = None  # monitor | triage | dispatch


class CaseTriageAgent(PdMAgent):
    """
    Case Triage & De-duplication Agent
    
    Reduces decision fatigue by:
    - Auto-grouping alerts into incident clusters
    - Recommending: monitor vs triage vs dispatch
    - Enforcing operational pacing
    """
    
    def __init__(
        self,
        event_bus: Optional[RedisEventBus] = None,
        max_dispatches_per_site_week: int = 5,
        clustering_window_hours: float = 4.0,
        **kwargs
    ):
        config = CrewAIAgentConfig(
            agent_id="case_triage_agent",
            role=AgentRole.DATA_VALIDATOR,
            category=AgentCategory.DATA,
            name="Case Triage Specialist",
            goal="Reduce alert fatigue by intelligently clustering and prioritizing cases, ensuring operators focus only on high-value interventions.",
            backstory="""You are an expert in predictive maintenance operations with deep experience 
            in managing alert queues. You understand that not every alert requires immediate action, 
            and that grouping related issues improves technician efficiency. You apply consistent 
            triage heuristics to cut queue volume while never missing critical failures.""",
        )
        super().__init__(config, event_bus, **kwargs)
        
        self.max_dispatches_per_site_week = max_dispatches_per_site_week
        self.clustering_window_hours = clustering_window_hours
        self.clusters: Dict[str, AlertCluster] = {}
        self.site_dispatch_counts: Dict[str, int] = {}
    
    @property
    def handled_event_types(self) -> List[PdMEventType]:
        return [
            PdMEventType.ALERT_CREATED,
            PdMEventType.ALERT_UPDATED,
            PdMEventType.CASE_CREATED,
        ]
    
    def handle(self, event: PdMEvent) -> Optional[PdMEvent]:
        """Handle incoming alert/case events"""
        if event.event_type == PdMEventType.ALERT_CREATED:
            return self._handle_alert_created(event)
        elif event.event_type == PdMEventType.CASE_CREATED:
            return self._handle_case_created(event)
        return None
    
    def _handle_alert_created(self, event: PdMEvent) -> Optional[PdMEvent]:
        """Process new alert and potentially cluster it"""
        payload = event.payload
        alert_id = payload.get("alert_id")
        asset_id = event.asset_id
        site_id = event.site_id
        alert_type = payload.get("alert_type", "unknown")
        
        # Generate cluster signature
        signature = f"{asset_id}:{alert_type}"
        
        # Check for existing cluster
        existing_cluster = self._find_matching_cluster(
            signature, event.timestamp
        )
        
        if existing_cluster:
            # Add to existing cluster
            existing_cluster.alert_ids.append(alert_id)
            existing_cluster.last_alert_time = event.timestamp
            existing_cluster.total_ev += payload.get("ev_score", 0)
            
            self.log_action("cluster_alert", {
                "alert_id": alert_id,
                "cluster_id": existing_cluster.cluster_id
            }, {"action": "added_to_cluster"})
            
            return self.event_factory._create_base(
                PdMEventType.ALERT_CLUSTERED,
                {
                    "alert_id": alert_id,
                    "cluster_id": existing_cluster.cluster_id,
                    "cluster_size": len(existing_cluster.alert_ids),
                },
                asset_id=asset_id,
                site_id=site_id,
            )
        else:
            # Create new cluster
            cluster = AlertCluster(
                cluster_id=str(uuid.uuid4()),
                alert_ids=[alert_id],
                asset_id=asset_id,
                site_id=site_id,
                signature=signature,
                first_alert_time=event.timestamp,
                last_alert_time=event.timestamp,
                total_ev=payload.get("ev_score", 0),
                severity=payload.get("severity", "medium"),
            )
            self.clusters[cluster.cluster_id] = cluster
            
            self.log_action("create_cluster", {
                "alert_id": alert_id
            }, {"cluster_id": cluster.cluster_id})
        
        return None
    
    def _find_matching_cluster(
        self, signature: str, timestamp: datetime
    ) -> Optional[AlertCluster]:
        """Find a cluster that matches the signature within time window"""
        cutoff = timestamp - timedelta(hours=self.clustering_window_hours)
        
        for cluster in self.clusters.values():
            if cluster.signature == signature and cluster.last_alert_time >= cutoff:
                return cluster
        return None
    
    def _handle_case_created(self, event: PdMEvent) -> Optional[PdMEvent]:
        """Triage a new case"""
        payload = event.payload
        case_id = event.case_id
        site_id = event.site_id
        severity = payload.get("severity", "medium")
        ev_score = payload.get("ev_score", 0)
        
        # Determine triage decision
        triage_decision, rationale, priority_score = self._compute_triage_decision(
            site_id, severity, ev_score
        )
        
        # Propose action
        action = self.propose_action(
            action_type="triage_case",
            description=f"Triage case {case_id}: {triage_decision}",
            payload={
                "case_id": case_id,
                "decision": triage_decision,
                "rationale": rationale,
            },
            requires_approval=(triage_decision == "dispatch"),
            priority=severity,
        )
        
        self.log_action("triage_case", {
            "case_id": case_id,
            "severity": severity,
            "ev_score": ev_score,
        }, {
            "decision": triage_decision,
            "rationale": rationale,
            "priority_score": priority_score,
        })
        
        return self.event_factory.case_triaged(
            case_id=case_id,
            triage_decision=triage_decision,
            cluster_id=None,
            rationale=rationale,
            priority_score=priority_score,
        )
    
    def _compute_triage_decision(
        self,
        site_id: str,
        severity: str,
        ev_score: float
    ) -> Tuple[str, str, float]:
        """Compute triage decision using heuristics"""
        # Check site dispatch limits
        site_dispatches = self.site_dispatch_counts.get(site_id, 0)
        at_limit = site_dispatches >= self.max_dispatches_per_site_week
        
        # Priority score (0-100)
        severity_weights = {"critical": 40, "high": 30, "medium": 20, "low": 10}
        priority_score = severity_weights.get(severity, 20) + min(ev_score * 60, 60)
        
        if severity == "critical" and not at_limit:
            decision = "dispatch"
            rationale = f"Critical severity with EV=${ev_score:.0f}. Immediate dispatch recommended."
        elif priority_score >= 70 and not at_limit:
            decision = "dispatch"
            rationale = f"High priority score ({priority_score:.0f}). Dispatch recommended."
        elif priority_score >= 40:
            decision = "triage"
            rationale = f"Moderate priority ({priority_score:.0f}). Manual triage recommended."
        else:
            decision = "monitor"
            rationale = f"Low priority ({priority_score:.0f}). Continue monitoring."
        
        if at_limit and decision == "dispatch":
            decision = "triage"
            rationale += f" [Site at dispatch limit ({self.max_dispatches_per_site_week}/week)]"
        
        return decision, rationale, priority_score


# =============================================================================
# 2. Evidence-to-Action Agent
# =============================================================================

@dataclass
class MaintenancePacket:
    """Technician-ready maintenance work package"""
    packet_id: str
    case_id: str
    problem_statement: str
    evidence_items: List[Dict[str, Any]]
    likely_root_causes: List[str]
    discriminating_checks: List[str]
    recommended_actions: List[Dict[str, Any]]
    required_parts: List[str]
    required_tools: List[str]
    safety_notes: List[str]
    compliance_notes: List[str]
    estimated_duration_hours: float
    created_at: datetime


class EvidenceToActionAgent(PdMAgent):
    """
    Evidence-to-Action Agent
    
    Turns explainability into technician-ready work packages by:
    - Producing plain-language problem statements
    - Providing evidence with before/after charts
    - Identifying likely root causes with discriminating checks
    - Recommending parts/tools and safety notes
    """
    
    def __init__(self, event_bus: Optional[RedisEventBus] = None, **kwargs):
        config = CrewAIAgentConfig(
            agent_id="evidence_to_action_agent",
            role=AgentRole.RATIONALE_GENERATOR,
            category=AgentCategory.COMMUNICATION,
            name="Evidence-to-Action Specialist",
            goal="Transform model predictions and contributing metrics into actionable, technician-friendly maintenance packages that improve first-time fix rates.",
            backstory="""You are a veteran field service engineer who understands both the technical 
            aspects of HVAC/R systems and the practical realities of field work. You excel at 
            translating complex diagnostic data into clear, actionable guidance that technicians 
            can immediately use. Your packages reduce diagnostic time and increase first-visit 
            resolution rates.""",
        )
        super().__init__(config, event_bus, **kwargs)
        
        self.packets: Dict[str, MaintenancePacket] = {}
    
    @property
    def handled_event_types(self) -> List[PdMEventType]:
        return [
            PdMEventType.CASE_TRIAGED,
            PdMEventType.CASE_CREATED,
        ]
    
    def handle(self, event: PdMEvent) -> Optional[PdMEvent]:
        """Handle case events to generate maintenance packets"""
        if event.event_type == PdMEventType.CASE_TRIAGED:
            payload = event.payload
            if payload.get("triage_decision") in ["triage", "dispatch"]:
                return self._generate_maintenance_packet(event)
        return None
    
    def _generate_maintenance_packet(self, event: PdMEvent) -> Optional[PdMEvent]:
        """Generate a maintenance packet for a case"""
        case_id = event.case_id
        
        # In production, this would call an LLM to generate the packet
        # For now, we create a structured template
        packet = MaintenancePacket(
            packet_id=str(uuid.uuid4()),
            case_id=case_id,
            problem_statement=self._generate_problem_statement(event),
            evidence_items=self._gather_evidence(event),
            likely_root_causes=self._identify_root_causes(event),
            discriminating_checks=self._generate_discriminating_checks(event),
            recommended_actions=self._generate_actions(event),
            required_parts=self._identify_parts(event),
            required_tools=self._identify_tools(event),
            safety_notes=self._generate_safety_notes(event),
            compliance_notes=self._generate_compliance_notes(event),
            estimated_duration_hours=self._estimate_duration(event),
            created_at=datetime.utcnow(),
        )
        
        self.packets[packet.packet_id] = packet
        
        self.log_action("generate_packet", {
            "case_id": case_id
        }, {
            "packet_id": packet.packet_id,
            "n_root_causes": len(packet.likely_root_causes),
            "n_actions": len(packet.recommended_actions),
        })
        
        return self.event_factory.maintenance_packet_created(
            case_id=case_id,
            packet_id=packet.packet_id,
            problem_statement=packet.problem_statement,
            evidence_items=packet.evidence_items,
            likely_root_causes=packet.likely_root_causes,
            recommended_actions=packet.recommended_actions,
            safety_notes=packet.safety_notes,
        )
    
    def _generate_problem_statement(self, event: PdMEvent) -> str:
        """Generate plain-language problem statement"""
        return f"Anomaly detected requiring investigation. Priority: {event.payload.get('priority_score', 'unknown')}"
    
    def _gather_evidence(self, event: PdMEvent) -> List[Dict[str, Any]]:
        """Gather evidence items from contributing metrics"""
        return [{
            "type": "metric_deviation",
            "description": "Contributing metrics exceed baseline thresholds",
            "data_source": "telemetry",
        }]
    
    def _identify_root_causes(self, event: PdMEvent) -> List[str]:
        """Identify likely root causes"""
        return [
            "Refrigerant charge imbalance",
            "Condenser coil fouling",
            "Compressor valve degradation",
        ]
    
    def _generate_discriminating_checks(self, event: PdMEvent) -> List[str]:
        """Generate checks to discriminate between root causes"""
        return [
            "Measure subcooling/superheat to check charge",
            "Inspect condenser coils for debris/fouling",
            "Check compressor amp draw and compare to rated",
        ]
    
    def _generate_actions(self, event: PdMEvent) -> List[Dict[str, Any]]:
        """Generate recommended actions"""
        return [
            {
                "action": "Perform diagnostic checks",
                "priority": 1,
                "estimated_time_mins": 30,
            },
            {
                "action": "Clean condenser coils if fouled",
                "priority": 2,
                "estimated_time_mins": 45,
            },
        ]
    
    def _identify_parts(self, event: PdMEvent) -> List[str]:
        """Identify potentially required parts"""
        return ["Refrigerant (if low)", "Coil cleaner", "Filter drier (if contamination)"]
    
    def _identify_tools(self, event: PdMEvent) -> List[str]:
        """Identify required tools"""
        return ["Manifold gauge set", "Multimeter", "Coil cleaning equipment"]
    
    def _generate_safety_notes(self, event: PdMEvent) -> List[str]:
        """Generate safety notes"""
        return [
            "Ensure power is locked out before accessing electrical components",
            "Use proper PPE when handling refrigerants",
        ]
    
    def _generate_compliance_notes(self, event: PdMEvent) -> List[str]:
        """Generate compliance notes"""
        return ["EPA Section 608 certification required for refrigerant handling"]
    
    def _estimate_duration(self, event: PdMEvent) -> float:
        """Estimate job duration in hours"""
        return 2.0


# =============================================================================
# 3. Work Order Composer Agent
# =============================================================================

class WorkOrderComposerAgent(PdMAgent):
    """
    Work Order Composer Agent
    
    Creates CMMS-ready work orders by:
    - Drafting WO description, steps, and parts list
    - Choosing priority and SLA tags based on EV
    - Routing to appropriate team/vendor
    """
    
    def __init__(self, event_bus: Optional[RedisEventBus] = None, **kwargs):
        config = CrewAIAgentConfig(
            agent_id="work_order_composer_agent",
            role=AgentRole.REPORT_WRITER,
            category=AgentCategory.COMMUNICATION,
            name="Work Order Composer",
            goal="Create complete, CMMS-ready work orders that require minimal manual editing and route to the correct resolution team.",
            backstory="""You are a maintenance planning expert who has worked extensively with 
            CMMS systems across multiple industries. You understand the information technicians 
            need to be effective and how to structure work orders for efficient scheduling and 
            execution. Your work orders are known for their clarity and completeness.""",
        )
        super().__init__(config, event_bus, **kwargs)
        
        self.work_orders: Dict[str, Dict[str, Any]] = {}
    
    @property
    def handled_event_types(self) -> List[PdMEventType]:
        return [
            PdMEventType.MAINTENANCE_PACKET_CREATED,
            PdMEventType.CASE_TRIAGED,
        ]
    
    def handle(self, event: PdMEvent) -> Optional[PdMEvent]:
        """Handle maintenance packet to create work order"""
        if event.event_type == PdMEventType.MAINTENANCE_PACKET_CREATED:
            return self._compose_work_order(event)
        return None
    
    def _compose_work_order(self, event: PdMEvent) -> Optional[PdMEvent]:
        """Compose a work order from maintenance packet"""
        payload = event.payload
        case_id = event.case_id
        packet_id = payload.get("packet_id")
        
        # Determine priority from context
        priority = self._determine_priority(event)
        
        # Create work order structure
        work_order = {
            "work_order_id": str(uuid.uuid4()),
            "case_id": case_id,
            "packet_id": packet_id,
            "title": f"PdM Alert - {payload.get('problem_statement', 'Investigation Required')[:50]}",
            "description": self._format_description(payload),
            "priority": priority,
            "sla_hours": self._get_sla_hours(priority),
            "steps": self._format_steps(payload),
            "parts_list": payload.get("estimated_parts", []),
            "assigned_team": self._determine_team(event),
            "created_at": datetime.utcnow().isoformat(),
            "status": "draft",
        }
        
        self.work_orders[work_order["work_order_id"]] = work_order
        
        # Propose action for approval
        self.propose_action(
            action_type="submit_work_order",
            description=f"Submit work order for case {case_id}",
            payload=work_order,
            requires_approval=True,
            priority=priority,
        )
        
        self.log_action("compose_work_order", {
            "case_id": case_id,
            "packet_id": packet_id,
        }, {
            "work_order_id": work_order["work_order_id"],
            "priority": priority,
        })
        
        return self.event_factory.work_order_drafted(
            case_id=case_id,
            work_order_id=work_order["work_order_id"],
            title=work_order["title"],
            description=work_order["description"],
            priority=priority,
            estimated_parts=work_order["parts_list"],
            estimated_duration_hours=2.0,
        )
    
    def _determine_priority(self, event: PdMEvent) -> str:
        """Determine work order priority"""
        payload = event.payload
        # Use problem statement keywords or other heuristics
        problem = payload.get("problem_statement", "").lower()
        if "critical" in problem or "emergency" in problem:
            return "emergency"
        elif "high" in problem or "urgent" in problem:
            return "urgent"
        return "standard"
    
    def _get_sla_hours(self, priority: str) -> int:
        """Get SLA hours based on priority"""
        sla_map = {
            "emergency": 4,
            "urgent": 24,
            "standard": 72,
            "planned": 168,
        }
        return sla_map.get(priority, 72)
    
    def _format_description(self, payload: Dict[str, Any]) -> str:
        """Format work order description"""
        lines = [
            f"Problem: {payload.get('problem_statement', 'Investigation required')}",
            "",
            "Likely Root Causes:",
        ]
        for cause in payload.get("likely_root_causes", []):
            lines.append(f"  - {cause}")
        
        lines.extend(["", "Safety Notes:"])
        for note in payload.get("safety_notes", []):
            lines.append(f"  - {note}")
        
        return "\n".join(lines)
    
    def _format_steps(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Format work order steps"""
        return [
            {"step_number": i + 1, "description": action.get("action", action) if isinstance(action, dict) else action}
            for i, action in enumerate(payload.get("recommended_actions", []))
        ]
    
    def _determine_team(self, event: PdMEvent) -> str:
        """Determine which team should handle the work order"""
        return "HVAC_TEAM_A"


# =============================================================================
# 4. Dispatch Batching & Scheduling Agent
# =============================================================================

@dataclass
class DispatchBatch:
    """Batch of work orders for a single dispatch"""
    batch_id: str
    site_id: str
    work_order_ids: List[str]
    case_ids: List[str]
    total_ev: float
    estimated_savings: float
    estimated_duration_hours: float
    recommended_date: Optional[datetime]
    rationale: str
    status: str = "proposed"


class DispatchBatchingAgent(PdMAgent):
    """
    Dispatch Batching & Scheduling Agent
    
    Maximizes ROI of field operations by:
    - Recommending bundles for single site visits
    - Suggesting timing based on risk and cost
    - Providing ranked plans with EV delta
    """
    
    def __init__(
        self,
        event_bus: Optional[RedisEventBus] = None,
        truck_roll_cost: float = 150.0,
        min_batch_ev_threshold: float = 500.0,
        **kwargs
    ):
        config = CrewAIAgentConfig(
            agent_id="dispatch_batching_agent",
            role=AgentRole.RESOURCE_ALLOCATOR,
            category=AgentCategory.OPTIMIZATION,
            name="Dispatch Optimization Specialist",
            goal="Maximize the ROI of field operations by intelligently batching and scheduling work orders to minimize truck rolls while addressing critical issues promptly.",
            backstory="""You are a logistics optimization expert specializing in field service 
            operations. You understand that every truck roll has a cost, and that combining 
            work orders at the same site dramatically improves efficiency. You balance urgency 
            with efficiency to create optimal dispatch plans.""",
        )
        super().__init__(config, event_bus, **kwargs)
        
        self.truck_roll_cost = truck_roll_cost
        self.min_batch_ev_threshold = min_batch_ev_threshold
        self.batches: Dict[str, DispatchBatch] = {}
        self.pending_work_orders: Dict[str, Dict[str, Any]] = {}
    
    @property
    def handled_event_types(self) -> List[PdMEventType]:
        return [
            PdMEventType.WORK_ORDER_DRAFTED,
            PdMEventType.WORK_ORDER_SUBMITTED,
        ]
    
    def handle(self, event: PdMEvent) -> Optional[PdMEvent]:
        """Handle work order events for batching"""
        if event.event_type == PdMEventType.WORK_ORDER_DRAFTED:
            return self._evaluate_batching(event)
        return None
    
    def _evaluate_batching(self, event: PdMEvent) -> Optional[PdMEvent]:
        """Evaluate if work order should be batched"""
        payload = event.payload
        work_order_id = payload.get("work_order_id")
        case_id = event.case_id
        site_id = event.site_id
        
        # Store work order
        self.pending_work_orders[work_order_id] = {
            "work_order_id": work_order_id,
            "case_id": case_id,
            "site_id": site_id,
            "priority": payload.get("priority", "standard"),
            "ev": payload.get("ev", 100),  # Estimated value
            "created_at": datetime.utcnow(),
        }
        
        # Check for batching opportunity
        batch = self._find_or_create_batch(site_id, work_order_id)
        
        if batch and len(batch.work_order_ids) > 1:
            self.log_action("create_batch", {
                "work_order_id": work_order_id,
                "site_id": site_id,
            }, {
                "batch_id": batch.batch_id,
                "batch_size": len(batch.work_order_ids),
                "estimated_savings": batch.estimated_savings,
            })
            
            return self.event_factory.dispatch_batch_created(
                batch_id=batch.batch_id,
                site_id=site_id,
                case_ids=batch.case_ids,
                total_ev=batch.total_ev,
                estimated_savings=batch.estimated_savings,
                rationale=batch.rationale,
            )
        
        return None
    
    def _find_or_create_batch(self, site_id: str, work_order_id: str) -> Optional[DispatchBatch]:
        """Find existing batch or create new one"""
        # Find pending work orders for same site
        site_wos = [
            wo for wo in self.pending_work_orders.values()
            if wo["site_id"] == site_id
        ]
        
        if len(site_wos) < 2:
            return None
        
        # Check if all are urgent
        all_urgent = all(wo["priority"] in ["emergency", "urgent"] for wo in site_wos)
        if all_urgent:
            return None  # Don't delay urgent work
        
        # Calculate batch economics
        total_ev = sum(wo["ev"] for wo in site_wos)
        saved_truck_rolls = len(site_wos) - 1
        estimated_savings = saved_truck_rolls * self.truck_roll_cost
        
        batch = DispatchBatch(
            batch_id=str(uuid.uuid4()),
            site_id=site_id,
            work_order_ids=[wo["work_order_id"] for wo in site_wos],
            case_ids=[wo["case_id"] for wo in site_wos],
            total_ev=total_ev,
            estimated_savings=estimated_savings,
            estimated_duration_hours=len(site_wos) * 1.5,
            recommended_date=datetime.utcnow() + timedelta(days=1),
            rationale=f"Combine {len(site_wos)} work orders at site. Saves {saved_truck_rolls} truck rolls (${estimated_savings:.0f}).",
        )
        
        self.batches[batch.batch_id] = batch
        return batch


# =============================================================================
# 5. Verification & Reopen Agent
# =============================================================================

class VerificationAgent(PdMAgent):
    """
    Verification & Reopen Agent
    
    Closes the loop using telemetry by:
    - Running post-fix verification checks
    - Auto-marking resolved or reopening cases
    - Improving precision through telemetry-based validation
    """
    
    def __init__(
        self,
        event_bus: Optional[RedisEventBus] = None,
        verification_window_hours: float = 24.0,
        confidence_threshold: float = 0.8,
        **kwargs
    ):
        config = CrewAIAgentConfig(
            agent_id="verification_agent",
            role=AgentRole.COMPLIANCE_CHECKER,
            category=AgentCategory.GOVERNANCE,
            name="Verification Specialist",
            goal="Ensure that completed work actually resolves the underlying issue by verifying through telemetry data, automatically reopening cases when problems persist.",
            backstory="""You are a quality assurance expert who believes that 'closed' must mean 
            'fixed'. You use telemetry data to independently verify that maintenance work has 
            actually resolved the underlying issue. Your verification catches issues that would 
            otherwise lead to repeat visits and customer dissatisfaction.""",
        )
        super().__init__(config, event_bus, **kwargs)
        
        self.verification_window_hours = verification_window_hours
        self.confidence_threshold = confidence_threshold
        self.pending_verifications: Dict[str, Dict[str, Any]] = {}
    
    @property
    def handled_event_types(self) -> List[PdMEventType]:
        return [
            PdMEventType.WORK_ORDER_COMPLETED,
            PdMEventType.CASE_CLOSED,
        ]
    
    def handle(self, event: PdMEvent) -> Optional[PdMEvent]:
        """Handle work completion events for verification"""
        if event.event_type == PdMEventType.WORK_ORDER_COMPLETED:
            return self._start_verification(event)
        return None
    
    def _start_verification(self, event: PdMEvent) -> Optional[PdMEvent]:
        """Start verification process for completed work"""
        case_id = event.case_id
        
        # Schedule verification
        verification = {
            "verification_id": str(uuid.uuid4()),
            "case_id": case_id,
            "work_order_id": event.payload.get("work_order_id"),
            "started_at": datetime.utcnow(),
            "window_ends_at": datetime.utcnow() + timedelta(hours=self.verification_window_hours),
            "status": "in_progress",
        }
        
        self.pending_verifications[verification["verification_id"]] = verification
        
        self.log_action("start_verification", {
            "case_id": case_id,
        }, {
            "verification_id": verification["verification_id"],
            "window_hours": self.verification_window_hours,
        })
        
        return self.event_factory._create_base(
            PdMEventType.VERIFICATION_STARTED,
            {
                "verification_id": verification["verification_id"],
                "window_hours": self.verification_window_hours,
            },
            case_id=case_id,
        )
    
    def run_verification_check(self, verification_id: str) -> Optional[PdMEvent]:
        """Run verification check (called after window expires)"""
        verification = self.pending_verifications.get(verification_id)
        if not verification:
            return None
        
        # In production, this would analyze post-fix telemetry
        # For now, simulate verification result
        passed, confidence, evidence = self._analyze_telemetry(verification)
        
        verification["status"] = "passed" if passed else "failed"
        verification["completed_at"] = datetime.utcnow().isoformat()
        verification["result"] = {
            "passed": passed,
            "confidence": confidence,
            "evidence": evidence,
        }
        
        recommendation = "Issue resolved. Case can be closed." if passed else "Issue persists. Recommend reopening case for further investigation."
        
        self.log_action("complete_verification", {
            "verification_id": verification_id,
        }, {
            "passed": passed,
            "confidence": confidence,
        })
        
        return self.event_factory.verification_result(
            case_id=verification["case_id"],
            passed=passed,
            verification_method="telemetry_analysis",
            confidence=confidence,
            evidence=evidence,
            recommendation=recommendation,
        )
    
    def _analyze_telemetry(self, verification: Dict[str, Any]) -> Tuple[bool, float, Dict[str, Any]]:
        """Analyze telemetry to determine if issue is resolved"""
        # Simulated analysis
        return True, 0.92, {
            "metrics_normalized": True,
            "anomaly_score_reduction": 0.85,
            "operating_envelope": "normal",
        }


# =============================================================================
# 6. Experimentation & Model Promotion Agent
# =============================================================================

class ExperimentationAgent(PdMAgent):
    """
    Experimentation & Model Promotion Agent
    
    Automates experiment analysis by:
    - Recommending promote/rollback with justification
    - Auto-opening approval requests
    - Triggering retraining when criteria met
    """
    
    def __init__(self, event_bus: Optional[RedisEventBus] = None, **kwargs):
        config = CrewAIAgentConfig(
            agent_id="experimentation_agent",
            role=AgentRole.POLICY_VALIDATOR,
            category=AgentCategory.GOVERNANCE,
            name="Model Governance Specialist",
            goal="Analyze experiment results and make data-driven recommendations for model promotion or rollback, ensuring only well-validated models reach production.",
            backstory="""You are an ML operations expert who understands that model evaluation 
            is nuanced and cannot be reduced to a single metric. You analyze experiment results 
            holistically, considering precision, recall, false positive rates, business costs, 
            and operational impact. Your recommendations are thorough and well-justified.""",
        )
        super().__init__(config, event_bus, **kwargs)
        
        self.pending_recommendations: List[Dict[str, Any]] = []
    
    @property
    def handled_event_types(self) -> List[PdMEventType]:
        return [
            PdMEventType.EXPERIMENT_COMPLETED,
            PdMEventType.MODEL_DRIFT_DETECTED,
        ]
    
    def handle(self, event: PdMEvent) -> Optional[PdMEvent]:
        """Handle experiment and drift events"""
        if event.event_type == PdMEventType.EXPERIMENT_COMPLETED:
            return self._analyze_experiment(event)
        elif event.event_type == PdMEventType.MODEL_DRIFT_DETECTED:
            return self._handle_drift(event)
        return None
    
    def _analyze_experiment(self, event: PdMEvent) -> Optional[PdMEvent]:
        """Analyze completed experiment"""
        payload = event.payload
        experiment_id = payload.get("experiment_id")
        
        # Extract metrics
        control_metrics = payload.get("control_metrics", {})
        treatment_metrics = payload.get("treatment_metrics", {})
        
        # Make recommendation
        recommendation, justification = self._make_recommendation(
            control_metrics, treatment_metrics
        )
        
        # Create promotion request if recommended
        if recommendation == "promote":
            action = self.propose_action(
                action_type="promote_model",
                description=f"Promote treatment model from experiment {experiment_id}",
                payload={
                    "experiment_id": experiment_id,
                    "current_version": payload.get("control_model"),
                    "proposed_version": payload.get("treatment_model"),
                    "justification": justification,
                    "metrics_comparison": {
                        "control": control_metrics,
                        "treatment": treatment_metrics,
                    },
                },
                requires_approval=True,
                priority="high",
            )
            
            self.log_action("recommend_promotion", {
                "experiment_id": experiment_id,
            }, {
                "recommendation": recommendation,
                "justification": justification,
            })
            
            return self.event_factory.model_promotion_requested(
                model_id=payload.get("treatment_model", "unknown"),
                current_version=payload.get("control_model", "current"),
                proposed_version=payload.get("treatment_model", "proposed"),
                justification=justification,
                metrics_comparison={
                    "control": control_metrics,
                    "treatment": treatment_metrics,
                },
            )
        
        return None
    
    def _make_recommendation(
        self,
        control: Dict[str, Any],
        treatment: Dict[str, Any]
    ) -> Tuple[str, str]:
        """Make promote/rollback recommendation"""
        # Compare key metrics
        control_f1 = control.get("f1", 0)
        treatment_f1 = treatment.get("f1", 0)
        control_fpr = control.get("false_positive_rate", 1)
        treatment_fpr = treatment.get("false_positive_rate", 1)
        
        f1_improvement = (treatment_f1 - control_f1) / max(control_f1, 0.01)
        fpr_improvement = (control_fpr - treatment_fpr) / max(control_fpr, 0.01)
        
        if f1_improvement > 0.05 and fpr_improvement >= 0:
            return "promote", f"Treatment model shows {f1_improvement:.1%} F1 improvement with same or better FPR."
        elif f1_improvement > 0.1:
            return "promote", f"Treatment model shows significant {f1_improvement:.1%} F1 improvement."
        elif f1_improvement < -0.05:
            return "rollback", f"Treatment model shows {-f1_improvement:.1%} F1 degradation."
        else:
            return "hold", "No significant difference between models. Continue experiment."
    
    def _handle_drift(self, event: PdMEvent) -> Optional[PdMEvent]:
        """Handle model drift detection"""
        payload = event.payload
        drift_severity = payload.get("severity", "medium")
        
        if drift_severity == "high":
            self.propose_action(
                action_type="trigger_retraining",
                description=f"Trigger retraining due to high drift",
                payload={
                    "model_id": payload.get("model_id"),
                    "drift_type": payload.get("drift_type"),
                    "trigger": "automated_drift_response",
                },
                requires_approval=True,
                priority="high",
            )
        
        return None


# =============================================================================
# 7. Data Steward / Integration Agent
# =============================================================================

class DataStewardAgent(PdMAgent):
    """
    Data Steward / Integration Agent
    
    Reduces data-quality drag by:
    - Diagnosing root causes of data gaps
    - Auto-generating tickets for instrumentation fixes
    - Recommending safe degradation modes
    """
    
    def __init__(self, event_bus: Optional[RedisEventBus] = None, **kwargs):
        config = CrewAIAgentConfig(
            agent_id="data_steward_agent",
            role=AgentRole.DATA_STEWARD,
            category=AgentCategory.DATA,
            name="Data Quality Steward",
            goal="Ensure telemetry data quality remains high by proactively identifying and addressing data gaps, sensor issues, and integration problems.",
            backstory="""You are a data quality expert who understands that predictive maintenance 
            is only as good as its data. You continuously monitor data streams for gaps, anomalies, 
            and quality issues. You proactively address problems before they impact model performance 
            and recommend graceful degradation when data quality is insufficient for reliable predictions.""",
        )
        super().__init__(config, event_bus, **kwargs)
        
        self.known_issues: Dict[str, Dict[str, Any]] = {}
    
    @property
    def handled_event_types(self) -> List[PdMEventType]:
        return [
            PdMEventType.DATA_QUALITY_ISSUE,
            PdMEventType.DATA_GAP_DETECTED,
            PdMEventType.SENSOR_OFFLINE,
        ]
    
    def handle(self, event: PdMEvent) -> Optional[PdMEvent]:
        """Handle data quality events"""
        if event.event_type in [PdMEventType.DATA_QUALITY_ISSUE, PdMEventType.DATA_GAP_DETECTED, PdMEventType.SENSOR_OFFLINE]:
            return self._diagnose_and_remediate(event)
        return None
    
    def _diagnose_and_remediate(self, event: PdMEvent) -> Optional[PdMEvent]:
        """Diagnose data issue and recommend remediation"""
        payload = event.payload
        asset_id = event.asset_id
        site_id = event.site_id
        
        # Diagnose issue
        diagnosis = self._diagnose_issue(event)
        
        # Store issue
        issue_id = str(uuid.uuid4())
        self.known_issues[issue_id] = {
            "issue_id": issue_id,
            "event_type": event.event_type.value,
            "asset_id": asset_id,
            "site_id": site_id,
            "diagnosis": diagnosis,
            "detected_at": datetime.utcnow().isoformat(),
            "status": "open",
        }
        
        # Determine remediation
        remediation = self._recommend_remediation(diagnosis)
        
        # Create work order for instrumentation fix if needed
        if remediation.get("create_work_order"):
            self.propose_action(
                action_type="create_instrumentation_work_order",
                description=f"Fix data issue: {diagnosis['summary']}",
                payload={
                    "issue_id": issue_id,
                    "asset_id": asset_id,
                    "site_id": site_id,
                    "diagnosis": diagnosis,
                    "remediation": remediation,
                },
                requires_approval=True,
                priority=remediation.get("priority", "medium"),
            )
        
        # Check if safe degradation is needed
        if remediation.get("enable_degradation_mode"):
            self.propose_action(
                action_type="enable_degradation_mode",
                description=f"Enable safe degradation mode for asset {asset_id}",
                payload={
                    "asset_id": asset_id,
                    "reason": diagnosis["summary"],
                    "suppressed_actions": remediation.get("suppressed_actions", []),
                },
                requires_approval=False,
                priority="high",
            )
        
        self.log_action("diagnose_data_issue", {
            "event_type": event.event_type.value,
            "asset_id": asset_id,
        }, {
            "issue_id": issue_id,
            "diagnosis": diagnosis["summary"],
            "remediation": remediation["action"],
        })
        
        return self.event_factory.data_quality_issue(
            asset_id=asset_id,
            site_id=site_id,
            issue_type=diagnosis["type"],
            affected_sensors=diagnosis.get("affected_sensors", []),
            severity=diagnosis["severity"],
            diagnosis=diagnosis["summary"],
            recommended_action=remediation["action"],
        )
    
    def _diagnose_issue(self, event: PdMEvent) -> Dict[str, Any]:
        """Diagnose the root cause of a data issue"""
        event_type = event.event_type
        payload = event.payload
        
        if event_type == PdMEventType.SENSOR_OFFLINE:
            return {
                "type": "sensor_offline",
                "severity": "high",
                "summary": f"Sensor offline: {payload.get('sensor_id', 'unknown')}",
                "likely_cause": "Power loss, network issue, or sensor failure",
                "affected_sensors": [payload.get("sensor_id")],
            }
        elif event_type == PdMEventType.DATA_GAP_DETECTED:
            return {
                "type": "data_gap",
                "severity": "medium",
                "summary": f"Data gap detected: {payload.get('gap_duration_hours', 0):.1f} hours",
                "likely_cause": "Gateway connectivity issue or buffering failure",
                "affected_sensors": payload.get("affected_sensors", []),
            }
        else:
            return {
                "type": "quality_degradation",
                "severity": "low",
                "summary": "Data quality below threshold",
                "likely_cause": "Sensor calibration drift or environmental interference",
                "affected_sensors": payload.get("affected_sensors", []),
            }
    
    def _recommend_remediation(self, diagnosis: Dict[str, Any]) -> Dict[str, Any]:
        """Recommend remediation actions"""
        severity = diagnosis["severity"]
        issue_type = diagnosis["type"]
        
        if severity == "high":
            return {
                "action": "Create urgent work order and enable degradation mode",
                "create_work_order": True,
                "enable_degradation_mode": True,
                "suppressed_actions": ["autonomous_control_changes"],
                "priority": "urgent",
            }
        elif severity == "medium":
            return {
                "action": "Create work order for investigation",
                "create_work_order": True,
                "enable_degradation_mode": False,
                "priority": "standard",
            }
        else:
            return {
                "action": "Monitor and log for trending",
                "create_work_order": False,
                "enable_degradation_mode": False,
                "priority": "low",
            }


# =============================================================================
# Agent Factory
# =============================================================================

class PdMAgentFactory:
    """Factory for creating PdM agents with shared event bus"""
    
    def __init__(self, event_bus: Optional[RedisEventBus] = None):
        self.event_bus = event_bus or InMemoryEventBus("factory")
        self.agents: Dict[str, PdMAgent] = {}
    
    def create_all_agents(self) -> Dict[str, PdMAgent]:
        """Create all PdM agents"""
        self.agents = {
            "triage": CaseTriageAgent(self.event_bus),
            "evidence": EvidenceToActionAgent(self.event_bus),
            "work_order": WorkOrderComposerAgent(self.event_bus),
            "dispatch": DispatchBatchingAgent(self.event_bus),
            "verification": VerificationAgent(self.event_bus),
            "experimentation": ExperimentationAgent(self.event_bus),
            "data_steward": DataStewardAgent(self.event_bus),
        }
        return self.agents
    
    def get_agent(self, name: str) -> Optional[PdMAgent]:
        """Get agent by name"""
        return self.agents.get(name)
    
    def get_all_statuses(self) -> List[Dict[str, Any]]:
        """Get status of all agents"""
        return [agent.get_agent_status() for agent in self.agents.values()]
