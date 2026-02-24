"""
Crew Compositions for the Predictive Maintenance Platform.

Defines pre-built Crew configurations that wire together the CrewAI agents
and their @tool functions for common multi-agent workflows.

Crew definitions:
- DiagnosticCrew: Triage → Evidence → KG lookup → WO composition
- DispatchCrew: WO composition → Parts check → Technician scheduling → Batching
- VerificationCrew: Post-service verification → Sensor recovery → Case close/reopen
- ScenarioCrew: Budget + Risk + Payback scenario analysis
- ModelGovernanceCrew: Experimentation → FL convergence → Model promotion
- CoverageAuditCrew: Ontology lookup → Sensor coverage → Instrumentation recs

Addresses Phase 5 from the FRD implementation plan.
"""

import logging
from typing import Any, Dict, List, Optional

from shared.agents.crewai_base import (
    Agent, Task, Crew, Process, CREWAI_AVAILABLE,
)

logger = logging.getLogger(__name__)


def _safe_crew(agents, tasks, process=None, verbose=True, **kwargs):
    """Create a Crew with graceful fallback when CrewAI is unavailable."""
    proc = process or Process.sequential
    try:
        return Crew(agents=agents, tasks=tasks, process=proc, verbose=verbose, **kwargs)
    except Exception as e:
        logger.warning("Could not create Crew: %s", e)
        return Crew(agents=agents, tasks=tasks, process=proc, verbose=verbose)


# =============================================================================
# 1. Diagnostic Crew: Alert → Triage → Evidence → KG → WO Draft
# =============================================================================

def build_diagnostic_crew(
    case_id: str,
    fault_type: str,
    asset_id: str,
    asset_type: str = "RTU",
    confidence: float = 0.8,
) -> Crew:
    """Build a Diagnostic Crew for end-to-end fault diagnosis and WO creation."""
    from .workflow_agents import (
        CaseTriageAgent, EvidenceToActionAgent, WorkOrderComposerAgent,
        evaluate_case_severity, build_evidence_bundle, compose_work_order,
    )
    from .knowledge_graph_agent import KnowledgeGraphAgent, query_kg_related
    from .ontology_agent import OntologyAgent, get_fault_info, get_required_sensors

    # Agent instances
    triage = Agent(
        role="Case Triage Specialist",
        goal=f"Evaluate severity and triage decision for case {case_id}.",
        backstory="You triage maintenance cases based on fault type, confidence, and asset criticality.",
        tools=[evaluate_case_severity],
        verbose=True,
    )
    evidence = Agent(
        role="Evidence Analyst",
        goal=f"Build evidence bundle for case {case_id} fault {fault_type}.",
        backstory="You assemble diagnostic evidence from sensor data, model outputs, and knowledge graph.",
        tools=[build_evidence_bundle, query_kg_related, get_fault_info],
        verbose=True,
    )
    composer = Agent(
        role="Work Order Composer",
        goal=f"Draft a CMMS-ready work order for case {case_id}.",
        backstory="You create complete, actionable work orders from diagnostic evidence.",
        tools=[compose_work_order, get_required_sensors],
        verbose=True,
    )

    # Tasks
    t1 = Task(
        description=f"Evaluate case {case_id}: fault_type={fault_type}, confidence={confidence}, asset={asset_id}. Determine triage decision.",
        agent=triage,
        expected_output="Triage decision (monitor/triage/dispatch) with rationale and priority score.",
    )
    t2 = Task(
        description=f"Build evidence bundle for case {case_id}. Query knowledge graph for related faults and get fault taxonomy details for {fault_type}.",
        agent=evidence,
        expected_output="Evidence bundle with anomaly traces, risk assessment, and contributing factors.",
    )
    t3 = Task(
        description=f"Compose work order for case {case_id} on asset {asset_id} ({asset_type}). Include required parts and SLA based on priority.",
        agent=composer,
        expected_output="Complete work order draft with title, description, priority, SLA, and parts list.",
    )

    return _safe_crew([triage, evidence, composer], [t1, t2, t3])


# =============================================================================
# 2. Dispatch Crew: WO → Parts → Technician → Batching
# =============================================================================

def build_dispatch_crew(
    work_order_ids: List[str],
    site_id: str,
) -> Crew:
    """Build a Dispatch Crew for parts verification, technician assignment, and batching."""
    from .parts_inventory_agent import (
        check_parts_availability, identify_shortage_risks,
    )
    from .technician_scheduling_agent import (
        match_technician_skills, optimize_schedule,
    )
    from .workflow_agents import batch_compatible_orders, optimize_dispatch_schedule

    parts_agent = Agent(
        role="Parts Coordinator",
        goal=f"Verify parts availability for WOs at site {site_id}.",
        backstory="You ensure all required parts are in stock before dispatching technicians.",
        tools=[check_parts_availability, identify_shortage_risks],
        verbose=True,
    )
    scheduler = Agent(
        role="Scheduling Optimizer",
        goal=f"Assign technicians and optimize dispatch for site {site_id}.",
        backstory="You match technician skills to WOs and optimize scheduling for efficiency.",
        tools=[match_technician_skills, optimize_schedule],
        verbose=True,
    )
    batcher = Agent(
        role="Dispatch Batcher",
        goal=f"Evaluate batching opportunities for {len(work_order_ids)} WOs at site {site_id}.",
        backstory="You combine compatible work orders to minimize truck rolls and travel costs.",
        tools=[batch_compatible_orders, optimize_dispatch_schedule],
        verbose=True,
    )

    wo_list = ", ".join(work_order_ids)
    t1 = Task(
        description=f"Check parts availability for work orders [{wo_list}] at site {site_id}. Flag any shortage risks.",
        agent=parts_agent,
        expected_output="Parts availability report with shortage alerts.",
    )
    t2 = Task(
        description=f"Assign technicians to work orders [{wo_list}] based on skills and availability.",
        agent=scheduler,
        expected_output="Optimized technician assignments with utilization report.",
    )
    t3 = Task(
        description=f"Evaluate batching opportunities for WOs [{wo_list}] at site {site_id}. Recommend dispatch timing.",
        agent=batcher,
        expected_output="Batch recommendations with estimated savings and dispatch schedule.",
    )

    return _safe_crew([parts_agent, scheduler, batcher], [t1, t2, t3])


# =============================================================================
# 3. Verification Crew: Post-service check → Sensor recovery → Close/Reopen
# =============================================================================

def build_verification_crew(
    case_id: str,
    asset_id: str,
    work_order_id: str,
) -> Crew:
    """Build a Verification Crew for post-service outcome verification."""
    from .workflow_agents import verify_repair_outcome, check_sensor_recovery
    from predictive_maintenance.services.workorder.tools import verify_repair_completion

    verifier = Agent(
        role="Repair Verification Specialist",
        goal=f"Verify repair outcome for case {case_id} / WO {work_order_id}.",
        backstory="You use telemetry data to independently verify that maintenance resolved the issue.",
        tools=[verify_repair_outcome, verify_repair_completion, check_sensor_recovery],
        verbose=True,
    )

    t1 = Task(
        description=(
            f"Verify repair for case {case_id} on asset {asset_id}. "
            f"Compare pre/post anomaly scores and check sensor recovery. "
            f"Recommend close or reopen."
        ),
        agent=verifier,
        expected_output="Verification result: passed/failed with evidence and recommendation.",
    )

    return _safe_crew([verifier], [t1])


# =============================================================================
# 4. Scenario Crew: Budget + Risk + Payback analysis
# =============================================================================

def build_scenario_crew(
    scope: str = "site",
    risk_level: str = "medium",
) -> Crew:
    """Build a Scenario Crew for multi-perspective maintenance scenario analysis."""
    from .scenario_agents import (
        get_budget_scenario_agent, get_risk_scenario_agent, get_payback_scenario_agent,
        analyze_budget_impact, analyze_risk_exposure, analyze_payback_period,
    )

    budget_agent = get_budget_scenario_agent()
    risk_agent = get_risk_scenario_agent()
    payback_agent = get_payback_scenario_agent()

    t1 = Task(
        description=f"Analyze the {scope}-level maintenance scenario from a budget/cost perspective. Risk level: {risk_level}.",
        agent=budget_agent,
        expected_output="Budget impact assessment with urgency level and cost analysis.",
    )
    t2 = Task(
        description=f"Analyze the {scope}-level maintenance scenario from a failure risk perspective. Risk level: {risk_level}.",
        agent=risk_agent,
        expected_output="Risk exposure assessment with fault probability and severity analysis.",
    )
    t3 = Task(
        description=f"Analyze the {scope}-level maintenance scenario from an ROI/payback perspective. Risk level: {risk_level}.",
        agent=payback_agent,
        expected_output="Payback assessment with break-even timeline and cumulative savings.",
    )

    return _safe_crew(
        [budget_agent, risk_agent, payback_agent],
        [t1, t2, t3],
    )


# =============================================================================
# 5. Model Governance Crew: Experiment → FL → Promotion
# =============================================================================

def build_model_governance_crew(
    experiment_id: str,
    model_id: str,
) -> Crew:
    """Build a Model Governance Crew for experiment evaluation and model promotion."""
    from .workflow_agents import evaluate_ab_test, promote_model_candidate
    from .federated_learning_agent import (
        FederatedLearningAgent, check_fl_convergence, evaluate_site_contribution,
    )

    experimenter = Agent(
        role="Experiment Evaluator",
        goal=f"Evaluate A/B test results for experiment {experiment_id}.",
        backstory="You analyze experiment metrics to make data-driven promote/rollback decisions.",
        tools=[evaluate_ab_test],
        verbose=True,
    )
    fl_monitor = Agent(
        role="Federated Learning Monitor",
        goal=f"Check FL convergence and site contribution quality for model {model_id}.",
        backstory="You monitor distributed model training quality and recommend when models are ready.",
        tools=[check_fl_convergence, evaluate_site_contribution],
        verbose=True,
    )
    promoter = Agent(
        role="Model Promotion Coordinator",
        goal=f"Coordinate model promotion request for {model_id} if experiment passes.",
        backstory="You create governance-compliant model promotion requests with full justification.",
        tools=[promote_model_candidate],
        verbose=True,
    )

    t1 = Task(
        description=f"Evaluate experiment {experiment_id} results. Determine promote/rollback/hold recommendation.",
        agent=experimenter,
        expected_output="Experiment evaluation with decision and justification.",
    )
    t2 = Task(
        description=f"Check FL convergence for model {model_id}. Evaluate per-site contribution quality.",
        agent=fl_monitor,
        expected_output="Convergence status and site contribution quality report.",
    )
    t3 = Task(
        description=f"If experiment passes and FL converged, create promotion request for model {model_id}.",
        agent=promoter,
        expected_output="Model promotion request or hold recommendation.",
    )

    return _safe_crew([experimenter, fl_monitor, promoter], [t1, t2, t3])


# =============================================================================
# 6. Coverage Audit Crew: Ontology → Sensor Coverage → Instrumentation Recs
# =============================================================================

def build_coverage_audit_crew(
    site_id: str,
    asset_type: str = "RTU",
) -> Crew:
    """Build a Coverage Audit Crew for sensor instrumentation assessment."""
    from .ontology_agent import OntologyAgent, get_required_sensors, get_asset_type_info
    from .sensor_coverage_agent import (
        SensorCoverageAgent, assess_sensor_coverage,
        identify_site_coverage_gaps, recommend_instrumentation,
    )

    ontology = Agent(
        role="Ontology Specialist",
        goal=f"Look up required sensors for {asset_type} assets at site {site_id}.",
        backstory="You are the HVAC/R domain expert who knows what sensors each asset type requires.",
        tools=[get_required_sensors, get_asset_type_info],
        verbose=True,
    )
    coverage = Agent(
        role="Coverage Analyst",
        goal=f"Assess sensor coverage gaps across assets at site {site_id}.",
        backstory="You compare installed sensors against requirements and quantify coverage gaps.",
        tools=[assess_sensor_coverage, identify_site_coverage_gaps, recommend_instrumentation],
        verbose=True,
    )

    t1 = Task(
        description=f"Look up the required and optional sensor sets for {asset_type} assets from the ontology.",
        agent=ontology,
        expected_output="Required and optional sensor lists for the asset type.",
    )
    t2 = Task(
        description=f"Assess sensor coverage for all {asset_type} assets at site {site_id}. Identify gaps and recommend instrumentation improvements.",
        agent=coverage,
        expected_output="Coverage report with gap analysis and prioritized instrumentation recommendations.",
    )

    return _safe_crew([ontology, coverage], [t1, t2])


# =============================================================================
# Registry of all available crews
# =============================================================================

CREW_REGISTRY = {
    "diagnostic": build_diagnostic_crew,
    "dispatch": build_dispatch_crew,
    "verification": build_verification_crew,
    "scenario": build_scenario_crew,
    "model_governance": build_model_governance_crew,
    "coverage_audit": build_coverage_audit_crew,
}
