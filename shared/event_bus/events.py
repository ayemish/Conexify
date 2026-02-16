"""
Unified Event Types and Envelopes — single source of truth.

Contains BOTH:
- PdM domain events (PdMEventType, PdMEvent, PdMEventFactory)
- Loweconex KPI events (EventType, EventEnvelope, create_envelope)

All domain code imports from here.
"""

import hashlib
import json
import uuid
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


# =============================================================================
# PdM Event Types (used by oil_gas and predictive_maintenance)
# =============================================================================

class PdMEventType(str, Enum):
    """Event types for Predictive Maintenance agent collaboration"""
    # Telemetry
    TELEMETRY_RECEIVED = "telemetry.received"
    ANALYSIS_COMPLETE = "analysis.complete"
    # Alert & Case Events
    ALERT_CREATED = "alert.created"
    ALERT_UPDATED = "alert.updated"
    ALERT_CLUSTERED = "alert.clustered"
    CASE_CREATED = "case.created"
    CASE_UPDATED = "case.updated"
    CASE_TRIAGED = "case.triaged"
    CASE_CLOSED = "case.closed"

    # Work Order Events
    WORK_ORDER_DRAFTED = "work_order.drafted"
    WORK_ORDER_SUBMITTED = "work_order.submitted"
    WORK_ORDER_COMPLETED = "work_order.completed"
    WORK_ORDER_VERIFIED = "work_order.verified"

    # Dispatch Events
    DISPATCH_BATCH_CREATED = "dispatch.batch_created"
    DISPATCH_SCHEDULED = "dispatch.scheduled"
    DISPATCH_COMPLETED = "dispatch.completed"

    # Model & Experimentation Events
    MODEL_DRIFT_DETECTED = "model.drift_detected"
    MODEL_RETRAIN_TRIGGERED = "model.retrain_triggered"
    MODEL_PROMOTION_REQUESTED = "model.promotion_requested"
    EXPERIMENT_COMPLETED = "experiment.completed"

    # Data Quality Events
    DATA_QUALITY_ISSUE = "data.quality_issue"
    DATA_GAP_DETECTED = "data.gap_detected"
    SENSOR_OFFLINE = "sensor.offline"

    # Agent Coordination Events
    AGENT_TASK_REQUEST = "agent.task_request"
    AGENT_TASK_RESULT = "agent.task_result"
    AGENT_HEARTBEAT = "agent.heartbeat"
    AGENT_HANDOFF = "agent.handoff"

    # Verification Events
    VERIFICATION_STARTED = "verification.started"
    VERIFICATION_PASSED = "verification.passed"
    VERIFICATION_FAILED = "verification.failed"

    # Evidence & Explainability Events
    EVIDENCE_PACKAGE_CREATED = "evidence.package_created"
    MAINTENANCE_PACKET_CREATED = "maintenance.packet_created"


# =============================================================================
# PdM Event Envelope
# =============================================================================

@dataclass
class PdMEvent:
    """Base event structure for all PdM events"""
    event_id: str
    event_type: PdMEventType
    source_agent: str
    timestamp: datetime

    # Core identifiers
    tenant_id: Optional[str] = None
    site_id: Optional[str] = None
    asset_id: Optional[str] = None
    case_id: Optional[str] = None

    # Payload
    payload: Dict[str, Any] = field(default_factory=dict)

    # Routing
    target_agents: Optional[List[str]] = None  # None = broadcast
    priority: int = 5  # 1-10, 1 highest

    # Correlation
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None

    # TTL and processing
    ttl_seconds: int = 3600
    retry_count: int = 0
    max_retries: int = 3

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "source_agent": self.source_agent,
            "timestamp": self.timestamp.isoformat(),
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "asset_id": self.asset_id,
            "case_id": self.case_id,
            "payload": self.payload,
            "target_agents": self.target_agents,
            "priority": self.priority,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "ttl_seconds": self.ttl_seconds,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PdMEvent":
        return cls(
            event_id=data["event_id"],
            event_type=PdMEventType(data["event_type"]),
            source_agent=data["source_agent"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            tenant_id=data.get("tenant_id"),
            site_id=data.get("site_id"),
            asset_id=data.get("asset_id"),
            case_id=data.get("case_id"),
            payload=data.get("payload", {}),
            target_agents=data.get("target_agents"),
            priority=data.get("priority", 5),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            ttl_seconds=data.get("ttl_seconds", 3600),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> "PdMEvent":
        return cls.from_dict(json.loads(json_str))


# =============================================================================
# Event Handler Protocol (PdM style)
# =============================================================================

class EventHandler(ABC):
    """Abstract base class for event handlers"""

    @abstractmethod
    def handle(self, event: PdMEvent) -> Optional[PdMEvent]:
        """Handle an event. Returns optional response event."""
        pass

    @property
    @abstractmethod
    def handled_event_types(self) -> List[PdMEventType]:
        """Event types this handler subscribes to"""
        pass


# =============================================================================
# PdM Event Factory
# =============================================================================

class PdMEventFactory:
    """Factory for creating typed PdM events"""

    def __init__(self, source_agent: str, tenant_id: Optional[str] = None):
        self.source_agent = source_agent
        self.tenant_id = tenant_id

    def _create_base(
        self,
        event_type: PdMEventType,
        payload: Dict[str, Any],
        **kwargs
    ) -> PdMEvent:
        return PdMEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            source_agent=self.source_agent,
            timestamp=datetime.utcnow(),
            tenant_id=self.tenant_id,
            payload=payload,
            **kwargs
        )

    def alert_created(
        self, alert_id: str, asset_id: str, site_id: str,
        alert_type: str, severity: str, confidence: float,
        ev_score: float, contributing_metrics: List[Dict[str, Any]],
    ) -> PdMEvent:
        return self._create_base(
            PdMEventType.ALERT_CREATED,
            {"alert_id": alert_id, "alert_type": alert_type,
             "severity": severity, "confidence": confidence,
             "ev_score": ev_score, "contributing_metrics": contributing_metrics},
            asset_id=asset_id, site_id=site_id,
        )

    def case_created(
        self, case_id: str, asset_id: str, site_id: str,
        title: str, severity: str, ev_score: float, alert_ids: List[str],
    ) -> PdMEvent:
        return self._create_base(
            PdMEventType.CASE_CREATED,
            {"title": title, "severity": severity,
             "ev_score": ev_score, "alert_ids": alert_ids},
            case_id=case_id, asset_id=asset_id, site_id=site_id,
        )

    def case_triaged(
        self, case_id: str, triage_decision: str,
        cluster_id: Optional[str], rationale: str, priority_score: float,
    ) -> PdMEvent:
        return self._create_base(
            PdMEventType.CASE_TRIAGED,
            {"triage_decision": triage_decision, "cluster_id": cluster_id,
             "rationale": rationale, "priority_score": priority_score},
            case_id=case_id,
        )

    def work_order_drafted(
        self, case_id: str, work_order_id: str, title: str,
        description: str, priority: str, estimated_parts: List[str],
        estimated_duration_hours: float,
    ) -> PdMEvent:
        return self._create_base(
            PdMEventType.WORK_ORDER_DRAFTED,
            {"work_order_id": work_order_id, "title": title,
             "description": description, "priority": priority,
             "estimated_parts": estimated_parts,
             "estimated_duration_hours": estimated_duration_hours},
            case_id=case_id,
        )

    def maintenance_packet_created(
        self, case_id: str, packet_id: str, problem_statement: str,
        evidence_items: List[Dict[str, Any]], likely_root_causes: List[str],
        recommended_actions: List[Dict[str, Any]], safety_notes: List[str],
    ) -> PdMEvent:
        return self._create_base(
            PdMEventType.MAINTENANCE_PACKET_CREATED,
            {"packet_id": packet_id, "problem_statement": problem_statement,
             "evidence_items": evidence_items,
             "likely_root_causes": likely_root_causes,
             "recommended_actions": recommended_actions,
             "safety_notes": safety_notes},
            case_id=case_id,
        )

    def dispatch_batch_created(
        self, batch_id: str, site_id: str, case_ids: List[str],
        total_ev: float, estimated_savings: float, rationale: str,
    ) -> PdMEvent:
        return self._create_base(
            PdMEventType.DISPATCH_BATCH_CREATED,
            {"batch_id": batch_id, "case_ids": case_ids,
             "total_ev": total_ev, "estimated_savings": estimated_savings,
             "rationale": rationale},
            site_id=site_id,
        )

    def verification_result(
        self, case_id: str, passed: bool, verification_method: str,
        confidence: float, evidence: Dict[str, Any], recommendation: str,
    ) -> PdMEvent:
        event_type = PdMEventType.VERIFICATION_PASSED if passed else PdMEventType.VERIFICATION_FAILED
        return self._create_base(
            event_type,
            {"passed": passed, "verification_method": verification_method,
             "confidence": confidence, "evidence": evidence,
             "recommendation": recommendation},
            case_id=case_id,
        )

    def model_promotion_requested(
        self, model_id: str, current_version: str, proposed_version: str,
        justification: str, metrics_comparison: Dict[str, Any],
    ) -> PdMEvent:
        return self._create_base(
            PdMEventType.MODEL_PROMOTION_REQUESTED,
            {"model_id": model_id, "current_version": current_version,
             "proposed_version": proposed_version,
             "justification": justification,
             "metrics_comparison": metrics_comparison},
        )

    def data_quality_issue(
        self, asset_id: str, site_id: str, issue_type: str,
        affected_sensors: List[str], severity: str,
        diagnosis: str, recommended_action: str,
    ) -> PdMEvent:
        return self._create_base(
            PdMEventType.DATA_QUALITY_ISSUE,
            {"issue_type": issue_type, "affected_sensors": affected_sensors,
             "severity": severity, "diagnosis": diagnosis,
             "recommended_action": recommended_action},
            asset_id=asset_id, site_id=site_id,
        )


# =============================================================================
# Loweconex Event Types (used by loweconex_platform)
# =============================================================================

class EventType(Enum):
    """Canonical event types for Loweconex inter-crew coordination."""
    # Ingestion
    DATA_INGESTED = "DATA_INGESTED"
    TWIN_UPDATED = "TWIN_UPDATED"

    # KPI lifecycle
    KPI_INPUTS_READY = "KPI_INPUTS_READY"
    KPI_COMPUTED = "KPI_COMPUTED"
    KPI_QA_PASSED = "KPI_QA_PASSED"
    KPI_QA_FAILED = "KPI_QA_FAILED"

    # Scenarios
    SCENARIO_RUN_REQUESTED = "SCENARIO_RUN_REQUESTED"
    SCENARIO_RUN_COMPLETED = "SCENARIO_RUN_COMPLETED"
    SCENARIO_PARAMETER_CHANGED = "SCENARIO_PARAMETER_CHANGED"

    # ROI
    ROI_COMPUTED = "ROI_COMPUTED"
    SAVINGS_ATTRIBUTION_UPDATED = "SAVINGS_ATTRIBUTION_UPDATED"

    # Reporting
    REPORT_SECTION_DRAFTED = "REPORT_SECTION_DRAFTED"
    REPORT_COMPILED = "REPORT_COMPILED"
    REPORT_EXPORTED = "REPORT_EXPORTED"

    # Governance
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    HUMAN_REVIEW_COMPLETED = "HUMAN_REVIEW_COMPLETED"
    AUDIT_LOG_ENTRY = "AUDIT_LOG_ENTRY"
    COMPLIANCE_CHECK_COMPLETED = "COMPLIANCE_CHECK_COMPLETED"

    # Data quality
    DATA_QUALITY_REPORT = "DATA_QUALITY_REPORT"
    DATA_GAP_DETECTED = "DATA_GAP_DETECTED"

    # Progress (transient, pub/sub only)
    CREW_STARTED = "CREW_STARTED"
    CREW_PROGRESS = "CREW_PROGRESS"
    CREW_COMPLETED = "CREW_COMPLETED"
    CREW_FAILED = "CREW_FAILED"


# =============================================================================
# Loweconex Event Envelope
# =============================================================================

@dataclass
class EventEnvelope:
    """
    Standard message envelope for Loweconex event bus messages.

    JSON-serializable with tenant isolation, correlation tracking,
    and schema versioning.
    """
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = ""
    company_id: str = ""
    location_id: Optional[str] = None
    asset_id: Optional[str] = None
    producer: str = ""
    consumer_group: Optional[str] = None
    payload_schema_version: str = "1.0"
    payload: Dict[str, Any] = field(default_factory=dict)
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Optional metadata
    kpi_name: Optional[str] = None
    scenario_id: Optional[str] = None
    estate_id: Optional[str] = None
    artifact_ids: List[str] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3

    # Idempotency & integrity
    idempotency_key: Optional[str] = None
    payload_hash: Optional[str] = None

    def __post_init__(self):
        if self.payload and not self.payload_hash:
            raw = json.dumps(self.payload, sort_keys=True, default=str)
            self.payload_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "msg_id": self.msg_id,
            "correlation_id": self.correlation_id,
            "event_type": self.event_type,
            "company_id": self.company_id,
            "location_id": self.location_id,
            "asset_id": self.asset_id,
            "producer": self.producer,
            "consumer_group": self.consumer_group,
            "payload_schema_version": self.payload_schema_version,
            "payload": self.payload,
            "created_ts": self.created_ts,
            "kpi_name": self.kpi_name,
            "scenario_id": self.scenario_id,
            "artifact_ids": self.artifact_ids,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "estate_id": self.estate_id,
            "idempotency_key": self.idempotency_key,
            "payload_hash": self.payload_hash,
        }

    @classmethod
    def from_json(cls, data: str) -> "EventEnvelope":
        return cls.from_dict(json.loads(data))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventEnvelope":
        return cls(
            msg_id=data.get("msg_id", str(uuid.uuid4())),
            correlation_id=data.get("correlation_id", str(uuid.uuid4())),
            event_type=data.get("event_type", ""),
            company_id=data.get("company_id", ""),
            location_id=data.get("location_id"),
            asset_id=data.get("asset_id"),
            producer=data.get("producer", ""),
            consumer_group=data.get("consumer_group"),
            payload_schema_version=data.get("payload_schema_version", "1.0"),
            payload=data.get("payload", {}),
            created_ts=data.get("created_ts", datetime.utcnow().isoformat()),
            kpi_name=data.get("kpi_name"),
            scenario_id=data.get("scenario_id"),
            artifact_ids=data.get("artifact_ids", []),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            estate_id=data.get("estate_id"),
            idempotency_key=data.get("idempotency_key"),
            payload_hash=data.get("payload_hash"),
        )


def create_envelope(
    event_type: EventType,
    company_id: str,
    producer: str,
    payload: Dict[str, Any],
    location_id: Optional[str] = None,
    asset_id: Optional[str] = None,
    kpi_name: Optional[str] = None,
    scenario_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    artifact_ids: Optional[List[str]] = None,
) -> EventEnvelope:
    """Factory for creating properly structured event envelopes."""
    return EventEnvelope(
        event_type=event_type.value,
        company_id=company_id,
        location_id=location_id,
        asset_id=asset_id,
        producer=producer,
        payload=payload,
        kpi_name=kpi_name,
        scenario_id=scenario_id,
        correlation_id=correlation_id or str(uuid.uuid4()),
        artifact_ids=artifact_ids or [],
    )
