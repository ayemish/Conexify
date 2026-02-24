"""
Workflow-oriented PdM agents (case triage, evidence packaging, work orders).

Re-exports from the canonical implementations in oil_gas/agents/pdm_agents.py.
The previous stubs have been replaced — all workflow agents are now full
CrewAI-compliant implementations with @tool functions and ProtocolEnabledAgent
mixin support.
"""

from oil_gas.agents.pdm_agents import (
    # Base class
    PdMAgent,
    PdMAgentRole,
    # All 7 workflow agents
    CaseTriageAgent,
    EvidenceToActionAgent,
    WorkOrderComposerAgent,
    DispatchBatchingAgent,
    VerificationAgent,
    ExperimentationAgent,
    DataStewardAgent,
    # Agent factory
    PdMAgentFactory,
    # @tool functions (re-export for convenience)
    evaluate_case_severity,
    check_deduplication,
    build_evidence_bundle,
    assess_evidence_confidence,
    compose_work_order,
    validate_wo_completeness,
    batch_compatible_orders,
    optimize_dispatch_schedule,
    verify_repair_outcome,
    check_sensor_recovery,
    evaluate_ab_test,
    promote_model_candidate,
    validate_data_quality,
    reconcile_schema_drift,
)

__all__ = [
    "PdMAgent",
    "PdMAgentRole",
    "CaseTriageAgent",
    "EvidenceToActionAgent",
    "WorkOrderComposerAgent",
    "DispatchBatchingAgent",
    "VerificationAgent",
    "ExperimentationAgent",
    "DataStewardAgent",
    "PdMAgentFactory",
    "evaluate_case_severity",
    "check_deduplication",
    "build_evidence_bundle",
    "assess_evidence_confidence",
    "compose_work_order",
    "validate_wo_completeness",
    "batch_compatible_orders",
    "optimize_dispatch_schedule",
    "verify_repair_outcome",
    "check_sensor_recovery",
    "evaluate_ab_test",
    "promote_model_candidate",
    "validate_data_quality",
    "reconcile_schema_drift",
]
