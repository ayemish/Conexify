"""
Task Pipeline — 13 tasks in 5 stages for the Ownership Decision Crew.

Stage 0: Ingest & normalize (orchestrator)
Stage 1: Ownership & metric validation (parallel — 5 stakeholder agents)
Stage 2: Cost translation (parallel — 4 dimension agents)
Stage 3: Reconciliation (sequential)
Stage 4: Optimization + Governance (sequential)

Task context chaining: T6-T9 depend on T1-T5; T10 depends on T6-T9;
T11 depends on T10; T12 depends on T11.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from shared.agents.crewai_base import Agent, Task, _MockTask

logger = logging.getLogger(__name__)


def _make_task(**kwargs) -> Task:
    """Create a CrewAI Task, falling back to mock if agent is a mock."""
    try:
        return Task(**kwargs)
    except Exception:
        return _MockTask(**kwargs)


# ═══════════════════════════════════════════════════════════════════
# Stage 0: Ingest & Normalize
# ═══════════════════════════════════════════════════════════════════

def create_ingest_task(orchestrator: Agent, context: List[Task] = None) -> Task:
    """T0: Build ParameterSet and baseline scenario."""
    return _make_task(
        description=(
            "Build the ParameterSet by reading all resolved parameters for the current scope. "
            "Identify the baseline scenario and candidate interventions. "
            "Use read_parameter_set and read_scenario tools. "
            "Output a JSON object with: parameter_set (all resolved values), "
            "baseline_scenario_id, intervention_candidates (list of metric_ids with inputs), "
            "scope (store/banner/region)."
        ),
        agent=orchestrator,
        expected_output=(
            '{"parameter_set": {...}, "baseline_scenario_id": "...", '
            '"intervention_candidates": [...], "scope": {...}}'
        ),
        context=context or [],
    )


# ═══════════════════════════════════════════════════════════════════
# Stage 1: Ownership & Metric Validation (parallel)
# ═══════════════════════════════════════════════════════════════════

def create_fm_validation_task(fm_agent: Agent, context: List[Task] = None) -> Task:
    """T1: FM Agent validates Q1 metrics, owners, and constraints."""
    return _make_task(
        description=(
            "Validate Q1 (FM-Controlled Opex) metric definitions and ownership assignments. "
            "Use read_metric_evidence(quadrant='Q1') and read_ownership_map to verify: "
            "(1) reactive jobs, PPM frequency, WO volume, tech utilization, repeat failures, "
            "call center, vendor cost metrics are correctly defined, "
            "(2) FM is accountable for each Q1 metric, "
            "(3) input values are operationally feasible. "
            "Then submit your StakeholderPosition with: "
            "- non-negotiables: P1 response time ≤ 4hrs, minimum tech coverage "
            "- preferences: reduction targets with weights "
            "- trade_bands: acceptable WO reduction range "
            "Use submit_stakeholder_position tool."
        ),
        agent=fm_agent,
        expected_output='{"status": "position_recorded", "agent_id": "fm"}',
        context=context or [],
    )


def create_finance_validation_task(finance_agent: Agent, context: List[Task] = None) -> Task:
    """T2: Finance Agent validates Q2 assumptions and emits capex ceiling."""
    return _make_task(
        description=(
            "Validate Q2 (Finance-Controlled Capex) metric definitions and assumptions. "
            "Use read_metric_evidence(quadrant='Q2') and read_parameter_set to verify: "
            "(1) replacement cycle, lifecycle model, capital efficiency, asset condition, "
            "(2) discount rate, hurdle rate, and depreciation policy are correct, "
            "(3) capex budget constraints are realistic. "
            "Submit StakeholderPosition with: "
            "- non-negotiables: capex budget ceiling, minimum hurdle rate "
            "- preferences: preferred discount rate range "
            "- trade_bands: acceptable capex range "
            "Use submit_stakeholder_position tool."
        ),
        agent=finance_agent,
        expected_output='{"status": "position_recorded", "agent_id": "finance"}',
        context=context or [],
    )


def create_compliance_validation_task(compliance_agent: Agent, context: List[Task] = None) -> Task:
    """T3: Compliance Agent validates Q3 thresholds and emits non-negotiables."""
    return _make_task(
        description=(
            "Validate Q3 (Compliance-Driven Risk) metric thresholds and penalty schedules. "
            "Use read_metric_evidence(quadrant='Q3') to verify: "
            "(1) temperature breach definitions match regulatory requirements, "
            "(2) penalty schedules are current for the jurisdiction, "
            "(3) brand exposure risk proxy is reasonable. "
            "Submit StakeholderPosition with: "
            "- non-negotiables: ALL Q3 constraints are HARD (regulatory), "
            "  including max breach count, min monitoring frequency "
            "- preferences: none (compliance is binary) "
            "Use submit_stakeholder_position tool."
        ),
        agent=compliance_agent,
        expected_output='{"status": "position_recorded", "agent_id": "compliance"}',
        context=context or [],
    )


def create_ops_validation_task(ops_agent: Agent, context: List[Task] = None) -> Task:
    """T4: Operations Agent validates disruption costs and uptime constraints."""
    return _make_task(
        description=(
            "Validate operational disruption costs and constraints. "
            "Use read_metric_evidence to check uptime, shrinkage, and disruption metrics. "
            "Submit StakeholderPosition with: "
            "- non-negotiables: minimum uptime floor (e.g., 95%), "
            "  maintenance window constraints "
            "- preferences: preferred maintenance scheduling windows with weights "
            "Use submit_stakeholder_position tool."
        ),
        agent=ops_agent,
        expected_output='{"status": "position_recorded", "agent_id": "ops"}',
        context=context or [],
    )


def create_esg_validation_task(esg_agent: Agent, context: List[Task] = None) -> Task:
    """T5: ESG Agent validates energy/emissions valuation assumptions."""
    return _make_task(
        description=(
            "Validate energy and emissions valuation assumptions. "
            "Use read_metric_evidence(quadrant='Q4') and read_parameter_set to verify: "
            "(1) electricity rate matches current tariff, "
            "(2) carbon factor and carbon price are current, "
            "(3) Scope 1/2 boundary definitions are correct. "
            "Submit StakeholderPosition with: "
            "- preferences: energy reduction valuation range, carbon price range "
            "- trade_bands: acceptable energy efficiency target range "
            "Flag if energy efficiency targets conflict with compliance buffers. "
            "Use submit_stakeholder_position tool."
        ),
        agent=esg_agent,
        expected_output='{"status": "position_recorded", "agent_id": "esg"}',
        context=context or [],
    )


# ═══════════════════════════════════════════════════════════════════
# Stage 2: Cost Translation (parallel)
# ═══════════════════════════════════════════════════════════════════

def create_opex_translation_task(opex_modeler: Agent, context: List[Task] = None) -> Task:
    """T6: Opex Modeler computes Opex cost lines for Q1 metrics."""
    return _make_task(
        description=(
            "Compute all Opex cost lines for Q1 metrics. "
            "For each Q1 metric, use run_translation to evaluate translation rules "
            "with current inputs. Apply service geography effects. "
            "Record assumptions using write_assumption. "
            "Output: JSON array of CostLine objects with low/base/high bands, "
            "owner attribution, and confidence scores."
        ),
        agent=opex_modeler,
        expected_output=(
            '{"dimension": "opex", "cost_lines": [{"name": "...", "amount": 0, '
            '"amount_low": 0, "amount_high": 0, "confidence": 0.0, ...}], "count": 0}'
        ),
        context=context or [],
    )


def create_capex_translation_task(capex_modeler: Agent, context: List[Task] = None) -> Task:
    """T7: Capex Modeler computes Capex/lifecycle cost lines for Q2 metrics."""
    return _make_task(
        description=(
            "Compute all Capex cost lines for Q2 metrics. "
            "For each Q2 metric, use run_translation to evaluate translation rules. "
            "Apply discount rate and depreciation from Finance's validated parameters. "
            "Record assumptions using write_assumption. "
            "Output: JSON array of CostLine objects."
        ),
        agent=capex_modeler,
        expected_output=(
            '{"dimension": "capex", "cost_lines": [...], "count": 0}'
        ),
        context=context or [],
    )


def create_risk_translation_task(risk_modeler: Agent, context: List[Task] = None) -> Task:
    """T8: Risk Modeler computes Risk cost lines for Q3 metrics."""
    return _make_task(
        description=(
            "Compute all Risk cost lines for Q3 metrics. "
            "For each Q3 metric, use run_translation to evaluate translation rules. "
            "Apply probability-weighted damage models. "
            "Respect all Compliance non-negotiable constraints. "
            "Record assumptions using write_assumption. "
            "Output: JSON array of CostLine objects."
        ),
        agent=risk_modeler,
        expected_output=(
            '{"dimension": "risk", "cost_lines": [...], "count": 0}'
        ),
        context=context or [],
    )


def create_strategic_translation_task(strategic_modeler: Agent, context: List[Task] = None) -> Task:
    """T9: Strategic Modeler computes Q4 cross-silo value lines."""
    return _make_task(
        description=(
            "Compute Q4 strategic cost lines: energy reduction, emissions, "
            "cross-silo bundled initiative ROI. "
            "FIRST use read_dependency_graph to check for upstream overlaps "
            "and avoid double-counting benefits already captured in Q1-Q3. "
            "Then use run_translation for Q4 metrics. "
            "Record assumptions using write_assumption. "
            "Output: JSON array of CostLine objects."
        ),
        agent=strategic_modeler,
        expected_output=(
            '{"dimension": "strategic", "cost_lines": [...], "count": 0}'
        ),
        context=context or [],
    )


# ═══════════════════════════════════════════════════════════════════
# Stage 3: Reconciliation
# ═══════════════════════════════════════════════════════════════════

def create_reconciliation_task(reconciler: Agent, context: List[Task] = None) -> Task:
    """T10: Reconciliation Agent merges and de-duplicates the cost stack."""
    return _make_task(
        description=(
            "Merge cost lines from all four dimension agents (opex, capex, risk, strategic) "
            "into a unified cost stack. "
            "Use read_dependency_graph to identify overlaps, then apply anti-double-counting "
            "adjustments. Allocate shared benefits across owners using ownership weights. "
            "Report all adjustments made with source/target metric IDs and overlap fractions. "
            "Output: JSON with unified_cost_stack (all lines) and adjustments_applied list."
        ),
        agent=reconciler,
        expected_output=(
            '{"unified_cost_stack": {"line_count": 0, "total": {...}, ...}, '
            '"adjustments_applied": [{"source_metric": "...", "target_metric": "...", '
            '"overlap_fraction": 0.0, ...}]}'
        ),
        context=context or [],
    )


# ═══════════════════════════════════════════════════════════════════
# Stage 4: Optimization + Governance
# ═══════════════════════════════════════════════════════════════════

def create_optimization_task(optimizer: Agent, context: List[Task] = None) -> Task:
    """T11: Optimizer Agent selects portfolio under constraints, returns Pareto options."""
    return _make_task(
        description=(
            "Select the optimal action portfolio from the reconciled cost stack. "
            "Use run_optimization with constraints derived from stakeholder positions: "
            "- Hard constraints from Compliance and Finance (non-negotiable) "
            "- Soft constraints weighted by preference scores "
            "Run with multiple objective functions: "
            "(1) Max consolidated NPV "
            "(2) Max risk-adjusted ROI (penalize low confidence) "
            "(3) Min compliance risk subject to budget "
            "Return 3-5 Pareto-optimal options with stakeholder utility scores. "
            "Recommend the option that maximizes consolidated NPV while respecting "
            "all hard constraints. "
            "Output: JSON with pareto_options array and recommended_option_id."
        ),
        agent=optimizer,
        expected_output=(
            '{"pareto_options": [{"option_id": "...", "label": "...", "npv": 0, ...}], '
            '"recommended_option_id": "..."}'
        ),
        context=context or [],
    )


def create_audit_task(auditor: Agent, context: List[Task] = None) -> Task:
    """T12: Audit Narrator produces ROI report, assumptions, and narrative."""
    return _make_task(
        description=(
            "Produce the final consolidated ROI report. "
            "Use read_roi to get the full ROI breakdown. "
            "Use read_cost_lines to trace each number to its source metric. "
            "Use read_ownership_map to attribute benefits per owner. "
            "Generate: "
            "(1) consolidated_roi JSON with per-owner/per-quadrant/per-cost_type breakdowns "
            "(2) board_narrative: 400-600 word executive summary covering: "
            "    headline savings figure with confidence range, "
            "    top 3 recommended actions and their payback, "
            "    key risks and data gaps, "
            "    scenario sensitivity, "
            "    cost of inaction "
            "(3) assumption_register: all assumptions with status and lineage "
            "(4) lineage_summary: tracing path from metric → rule → cost line → ROI "
            "Output: JSON with all four sections."
        ),
        agent=auditor,
        expected_output=(
            '{"consolidated_roi": {...}, "board_narrative": "...", '
            '"assumption_register": [...], "lineage_summary": {...}}'
        ),
        context=context or [],
    )


# ═══════════════════════════════════════════════════════════════════
# Task Pipeline Assembly
# ═══════════════════════════════════════════════════════════════════

def assemble_task_pipeline(agents: Dict[str, Agent]) -> List[Task]:
    """
    Assemble the full 13-task pipeline with context chaining.

    Args:
        agents: Dict mapping agent keys to Agent instances.
                Keys: orchestrator, fm, finance, compliance, ops, esg,
                      opex_modeler, capex_modeler, risk_modeler, strategic_modeler,
                      reconciler, optimizer, auditor

    Returns:
        Ordered list of Tasks for the crew.
    """
    # Stage 0
    t0 = create_ingest_task(agents["orchestrator"])

    # Stage 1 (all depend on t0 for parameter context)
    t1 = create_fm_validation_task(agents["fm"], context=[t0])
    t2 = create_finance_validation_task(agents["finance"], context=[t0])
    t3 = create_compliance_validation_task(agents["compliance"], context=[t0])
    t4 = create_ops_validation_task(agents["ops"], context=[t0])
    t5 = create_esg_validation_task(agents["esg"], context=[t0])

    # Stage 2 (depend on Stage 1 outputs for validated constraints)
    stage1 = [t1, t2, t3, t4, t5]
    t6 = create_opex_translation_task(agents["opex_modeler"], context=stage1)
    t7 = create_capex_translation_task(agents["capex_modeler"], context=stage1)
    t8 = create_risk_translation_task(agents["risk_modeler"], context=stage1)
    t9 = create_strategic_translation_task(agents["strategic_modeler"], context=stage1)

    # Stage 3
    stage2 = [t6, t7, t8, t9]
    t10 = create_reconciliation_task(agents["reconciler"], context=stage2)

    # Stage 4
    t11 = create_optimization_task(agents["optimizer"], context=[t10])
    t12 = create_audit_task(agents["auditor"], context=[t10, t11])

    return [t0, t1, t2, t3, t4, t5, t6, t7, t8, t9, t10, t11, t12]
