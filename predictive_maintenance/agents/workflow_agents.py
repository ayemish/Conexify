"""
Workflow-oriented PdM agents (case triage, evidence packaging, work orders).

These are lightweight stubs to keep the orchestration layer functional.
"""

import uuid
from typing import Optional, List

from ..integration.event_bus import (
    RedisEventBus, InMemoryEventBus, PdMEvent, PdMEventType, PdMEventFactory, EventHandler
)


class PdMAgent(EventHandler):
    """Base class for workflow agents."""

    def __init__(self, agent_id: str, event_bus: Optional[RedisEventBus] = None):
        self.agent_id = agent_id
        self.event_bus = event_bus or InMemoryEventBus(agent_id)
        self.event_factory = PdMEventFactory(agent_id)
        self.event_bus.register_handler(self)

    @property
    def handled_event_types(self) -> List[PdMEventType]:
        return []

    def handle(self, event: PdMEvent) -> Optional[PdMEvent]:
        return None


class CaseTriageAgent(PdMAgent):
    """Triages cases into monitor/triage/dispatch buckets."""

    @property
    def handled_event_types(self) -> List[PdMEventType]:
        return [PdMEventType.CASE_CREATED]

    def handle(self, event: PdMEvent) -> Optional[PdMEvent]:
        severity = (event.payload or {}).get("severity", "medium")
        decision = "dispatch" if severity == "high" else "triage"
        return self.event_factory.case_triaged(
            case_id=event.case_id or str(uuid.uuid4())[:12],
            triage_decision=decision,
            cluster_id=None,
            rationale=f"Auto-triage based on severity={severity}",
            priority_score=0.8 if decision == "dispatch" else 0.5,
        )


class EvidenceToActionAgent(PdMAgent):
    """Builds a maintenance packet from triage results."""

    @property
    def handled_event_types(self) -> List[PdMEventType]:
        return [PdMEventType.CASE_TRIAGED]

    def handle(self, event: PdMEvent) -> Optional[PdMEvent]:
        return self.event_factory.maintenance_packet_created(
            case_id=event.case_id or str(uuid.uuid4())[:12],
            packet_id=str(uuid.uuid4())[:12],
            problem_statement="Potential equipment fault detected",
            evidence_items=[],
            likely_root_causes=[],
            recommended_actions=[],
            safety_notes=[],
        )


class WorkOrderComposerAgent(PdMAgent):
    """Drafts a work order for dispatch decisions."""

    @property
    def handled_event_types(self) -> List[PdMEventType]:
        return [PdMEventType.CASE_TRIAGED]

    def handle(self, event: PdMEvent) -> Optional[PdMEvent]:
        decision = (event.payload or {}).get("triage_decision")
        if decision != "dispatch":
            return None
        return self.event_factory.work_order_drafted(
            case_id=event.case_id or str(uuid.uuid4())[:12],
            work_order_id=str(uuid.uuid4())[:12],
            title="Investigate HVAC/R alert",
            description="Dispatch technician to inspect system.",
            priority="high",
            estimated_parts=[],
            estimated_duration_hours=2.0,
        )
