"""
Oil & Gas Telemetry Monitoring Ecosystem

Four-Plane Architecture for industrial operations monitoring:

DATA PLANE:
- Telemetry ingestion, stream processing, evidence store
- Forensic bundles for incident investigation

AGENT PLANE (10 specialized agents):
1. SignalTriageAgent: Deduplicates, filters, classifies alerts
2. CorrelationAgent: Clusters related alerts, detects cascades
3. DiagnosticsAgent: Runs fault trees, matches failure signatures
4. RootCauseAnalystAgent: Proposes hypotheses with confidence
5. RemediationPlannerAgent: Creates ordered action plans
6. ToolExecutorAgent: Executes approved actions with audit
7. VerificationAgent: Confirms remediation effectiveness
8. CustomerCommsAgent: Drafts stakeholder communications
9. GovernancePolicyAgent: Enforces RBAC, approvals, compliance
10. LearningAgent: Extracts lessons, updates runbooks

ORCHESTRATION PLANE:
- 9-state case lifecycle (Intake→Triage→Diagnose→Plan→Authorize→Execute→Verify→Close→Learn)
- Sequential, concurrent, handoff, manager-led patterns
- Human-in-the-loop approval workflow

EXECUTION PLANE:
- Strict tool schemas with validation
- Policy-based autonomy levels
- Full audit logging

Based on NIST AI RMF and OWASP Gen AI Security guidelines.
"""

# Legacy agents (v1)
from .agents import (
    TelemetryIngestionAgent,
    AnomalyDetectionAgent,
    PredictiveMaintenanceAgent,
    ProductionOptimizationAgent,
    SafetyMonitoringAgent,
    ComplianceAgent,
    AlertAgent,
    ReportingAgent,
)

# Legacy orchestrator (v1)
from .orchestrator import OilGasOrchestrator, create_oil_gas_orchestrator

# Legacy schemas
from .schemas import (
    OilGasConfig,
    WellConfig,
    SensorConfig,
    SensorType,
    WellType,
    TelemetryReading,
    AnomalyAlert,
    MaintenancePrediction,
    ProductionMetrics,
    SafetyStatus,
    ComplianceReport,
    OilGasDecisionPack,
)

# Four-Plane Architecture (v2)
from .data_plane import (
    Case,
    CaseState,
    CasePriority,
    Alert,
    AlertClassification,
    Hypothesis,
    RemediationPlan,
    ActionStep,
    ActionRiskLevel,
    AutonomyLevel,
    EvidenceBundle,
    EvidenceStore,
    TelemetryPoint,
    StreamProcessor,
)

from .governance import (
    ToolSchema,
    ToolCategory,
    PolicyEngine,
    AuditLogger,
    SitePolicy,
    Role,
)

from .agent_plane import (
    FourPlaneAgent,
    SignalTriageAgent,
    CorrelationAgent,
    DiagnosticsAgent,
    RootCauseAnalystAgent,
    RemediationPlannerAgent,
)

from .agent_plane_extended import (
    ToolExecutorAgent,
    VerificationAgent,
    CustomerCommsAgent,
    GovernancePolicyAgent,
    LearningAgent,
)

from .orchestrator_v2 import (
    FourPlaneOrchestrator,
    OrchestrationConfig,
    OrchestrationPattern,
    CaseLifecycleManager,
)

__all__ = [
    # Legacy Agents (v1)
    "TelemetryIngestionAgent",
    "AnomalyDetectionAgent",
    "PredictiveMaintenanceAgent",
    "ProductionOptimizationAgent",
    "SafetyMonitoringAgent",
    "ComplianceAgent",
    "AlertAgent",
    "ReportingAgent",
    
    # Legacy Orchestrator (v1)
    "OilGasOrchestrator",
    "create_oil_gas_orchestrator",
    
    # Legacy Schemas
    "OilGasConfig",
    "WellConfig",
    "SensorConfig",
    "SensorType",
    "WellType",
    "TelemetryReading",
    "AnomalyAlert",
    "MaintenancePrediction",
    "ProductionMetrics",
    "SafetyStatus",
    "ComplianceReport",
    "OilGasDecisionPack",
    
    # Four-Plane Architecture (v2) - Data Plane
    "Case",
    "CaseState",
    "CasePriority",
    "Alert",
    "AlertClassification",
    "Hypothesis",
    "RemediationPlan",
    "ActionStep",
    "ActionRiskLevel",
    "AutonomyLevel",
    "EvidenceBundle",
    "EvidenceStore",
    "TelemetryPoint",
    "StreamProcessor",
    
    # Four-Plane Architecture (v2) - Governance
    "ToolSchema",
    "ToolCategory",
    "PolicyEngine",
    "AuditLogger",
    "SitePolicy",
    "Role",
    
    # Four-Plane Architecture (v2) - Agent Plane
    "FourPlaneAgent",
    "SignalTriageAgent",
    "CorrelationAgent",
    "DiagnosticsAgent",
    "RootCauseAnalystAgent",
    "RemediationPlannerAgent",
    "ToolExecutorAgent",
    "VerificationAgent",
    "CustomerCommsAgent",
    "GovernancePolicyAgent",
    "LearningAgent",
    
    # Four-Plane Architecture (v2) - Orchestration
    "FourPlaneOrchestrator",
    "OrchestrationConfig",
    "OrchestrationPattern",
    "CaseLifecycleManager",
]
