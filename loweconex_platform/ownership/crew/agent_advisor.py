"""
Agent Advisor — asset/location-scoped reasoning engine.

Accepts an asset ID or location ID, resolves all relevant metrics and
KPI context for that scope, runs the 12-agent decision crew pipeline,
and returns structured per-agent reasoning traces alongside cross-silo
consolidated recommendations.

Integration points:
- KPIConfig / KPIOrchestrator (predictive_maintenance.services.kpi)
- OwnershipDecisionCrew (12-agent crew pipeline)
- DecisionAdvisoryAgent (LLM-powered advisory)
- QuadrantValidator (Q1-Q4 flow integrity)
- GovernanceEngine (RACI + approval gates)
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loweconex_platform.ownership.api_routes import OwnershipDecisionService, get_service
from loweconex_platform.ownership.crew.decision_crew import OwnershipDecisionCrew
from loweconex_platform.ownership.crew.schemas import (
    DecisionCrewOutput, StakeholderPosition, ParetoOption,
)
from loweconex_platform.ownership.crew.agents import AGENT_ROSTER
from loweconex_platform.ownership.quadrant_validator import (
    QuadrantValidator, QUADRANT_COST_TYPE,
)
from loweconex_platform.ownership.governance_engine import GovernanceEngine

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Agent Reasoning Trace
# ═══════════════════════════════════════════════════════════════════

@dataclass
class AgentReasoningStep:
    """A single reasoning step within an agent's trace."""
    step_id: int = 0
    action: str = ""           # "validate", "compute", "negotiate", "optimize", "narrate"
    description: str = ""
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0
    confidence: float = 0
    status: str = "completed"  # "completed", "warning", "error"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "action": self.action,
            "description": self.description,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "duration_ms": round(self.duration_ms, 1),
            "confidence": round(self.confidence, 3),
            "status": self.status,
        }


@dataclass
class AgentTrace:
    """Complete reasoning trace for a single agent."""
    agent_id: str = ""
    agent_role: str = ""
    group: str = ""            # "stakeholder", "dimension", "governance"
    quadrant: str = ""
    stage: int = 0             # Pipeline stage (0-4)
    reasoning_steps: List[AgentReasoningStep] = field(default_factory=list)
    conclusion: str = ""
    key_findings: List[str] = field(default_factory=list)
    constraints_emitted: List[Dict[str, Any]] = field(default_factory=list)
    cost_lines_produced: int = 0
    sign_off: bool = True
    duration_ms: float = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_role": self.agent_role,
            "group": self.group,
            "quadrant": self.quadrant,
            "stage": self.stage,
            "reasoning_steps": [s.to_dict() for s in self.reasoning_steps],
            "conclusion": self.conclusion,
            "key_findings": self.key_findings,
            "constraints_emitted": self.constraints_emitted,
            "cost_lines_produced": self.cost_lines_produced,
            "sign_off": self.sign_off,
            "duration_ms": round(self.duration_ms, 1),
        }


@dataclass
class CrossSiloConsolidation:
    """Shows how different stakeholder views merge into unified output."""
    quadrant_contributions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    overlap_adjustments: List[Dict[str, Any]] = field(default_factory=list)
    negotiation_summary: Dict[str, Any] = field(default_factory=dict)
    unified_npv: float = 0
    unified_savings: float = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quadrant_contributions": self.quadrant_contributions,
            "overlap_adjustments": self.overlap_adjustments,
            "negotiation_summary": self.negotiation_summary,
            "unified_npv": round(self.unified_npv, 2),
            "unified_savings": round(self.unified_savings, 2),
        }


@dataclass
class Recommendation:
    """A single actionable recommendation."""
    rec_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str = ""
    quadrant: str = ""
    owner: str = ""
    savings_annual: float = 0
    confidence: float = 0
    priority: int = 1
    category: str = ""         # "quick_win", "structural", "capex", "compliance"
    rationale: str = ""
    supporting_agents: List[str] = field(default_factory=list)
    risk_if_deferred: str = ""
    implementation_horizon: str = ""  # "0-3 months", "3-6 months", "6-12 months"
    cross_silo_impact: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rec_id": self.rec_id,
            "title": self.title,
            "quadrant": self.quadrant,
            "owner": self.owner,
            "savings_annual": round(self.savings_annual, 2),
            "confidence": round(self.confidence, 3),
            "priority": self.priority,
            "category": self.category,
            "rationale": self.rationale,
            "supporting_agents": self.supporting_agents,
            "risk_if_deferred": self.risk_if_deferred,
            "implementation_horizon": self.implementation_horizon,
            "cross_silo_impact": self.cross_silo_impact,
        }


@dataclass
class AgentAdvisorResult:
    """Complete result from the Agent Advisor."""
    run_id: str = ""
    scope_type: str = ""       # "asset" or "location"
    scope_id: str = ""
    agent_traces: List[AgentTrace] = field(default_factory=list)
    cross_silo: CrossSiloConsolidation = field(default_factory=CrossSiloConsolidation)
    recommendations: List[Recommendation] = field(default_factory=list)
    pareto_options: List[Dict[str, Any]] = field(default_factory=list)
    board_narrative: str = ""
    quadrant_validation: Dict[str, Any] = field(default_factory=dict)
    governance_status: Dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0
    crew_output: Dict[str, Any] = field(default_factory=dict)
    agent_messages: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "scope_type": self.scope_type,
            "scope_id": self.scope_id,
            "agent_traces": [t.to_dict() for t in self.agent_traces],
            "cross_silo": self.cross_silo.to_dict(),
            "recommendations": [r.to_dict() for r in self.recommendations],
            "pareto_options": self.pareto_options,
            "board_narrative": self.board_narrative,
            "quadrant_validation": self.quadrant_validation,
            "governance_status": self.governance_status,
            "execution_time_ms": round(self.execution_time_ms, 1),
            "crew_output": self.crew_output,
            "agent_messages": self.agent_messages,
        }


# ═══════════════════════════════════════════════════════════════════
# Scope → Metric Resolution
# ═══════════════════════════════════════════════════════════════════

# Baseline metric inputs for demo — in production these would come
# from the data stores filtered by asset/location.
ASSET_TYPE_PROFILES: Dict[str, Dict[str, Dict[str, Any]]] = {
    "RTU": {
        "m_reactive_jobs": {"wo_count": 80, "cost_per_wo": 420, "reduction_pct": 0.30},
        "m_ppm_frequency": {"baseline_pm_tasks": 200, "optimized_pm_tasks": 150, "pm_cost_per_task": 150, "avoided_reactive_savings": 8000},
        "m_energy_reduction": {"kwh_reduction": 35000, "electricity_rate": 0.12, "carbon_factor": 0.0004, "carbon_price": 50},
        "m_replacement_cycle": {"replacement_count": 2, "avg_replacement_cost": 22000, "avoided_failure_cost": 8000},
    },
    "WALK_IN": {
        "m_reactive_jobs": {"wo_count": 40, "cost_per_wo": 350, "reduction_pct": 0.25},
        "m_temp_breaches": {"breach_count": 12, "avg_spoilage_per_breach": 3200, "penalty_probability": 0.20, "avg_penalty": 12000, "audit_risk_cost": 6000},
        "m_product_discard": {"discard_volume": 300, "avg_cogs_per_unit": 10, "discard_events": 20, "labor_per_event": 100, "disposal_cost_per_unit": 1.5},
        "m_energy_reduction": {"kwh_reduction": 50000, "electricity_rate": 0.12, "carbon_factor": 0.0004, "carbon_price": 50},
    },
    "RACK": {
        "m_reactive_jobs": {"wo_count": 120, "cost_per_wo": 500, "reduction_pct": 0.35},
        "m_temp_breaches": {"breach_count": 6, "avg_spoilage_per_breach": 4500, "penalty_probability": 0.10, "avg_penalty": 15000, "audit_risk_cost": 8000},
        "m_energy_reduction": {"kwh_reduction": 120000, "electricity_rate": 0.12, "carbon_factor": 0.0004, "carbon_price": 50},
        "m_replacement_cycle": {"replacement_count": 1, "avg_replacement_cost": 45000, "avoided_failure_cost": 15000},
        "m_emissions_reduction": {"emissions_reduced_tco2e": 50, "carbon_price": 50, "compliance_reporting_value": 5000},
    },
}

LOCATION_PROFILES: Dict[str, Dict[str, Dict[str, Any]]] = {
    "default": {
        "m_reactive_jobs": {"wo_count": 200, "cost_per_wo": 400, "reduction_pct": 0.28},
        "m_ppm_frequency": {"baseline_pm_tasks": 500, "optimized_pm_tasks": 380, "pm_cost_per_task": 150, "avoided_reactive_savings": 12000},
        "m_wo_volume": {"wo_volume": 350, "avg_vendor_rate": 250, "vendor_reduction_pct": 0.15, "admin_overhead_per_wo": 45, "admin_reduction_pct": 0.20},
        "m_service_bureau": {"call_volume": 600, "cost_per_call": 25, "deflection_rate": 0.30},
        "m_replacement_cycle": {"replacement_count": 4, "avg_replacement_cost": 20000, "avoided_failure_cost": 8000},
        "m_lifecycle_model": {"keep_lcc_npv": 300000, "replace_lcc_npv": 220000},
        "m_temp_breaches": {"breach_count": 15, "avg_spoilage_per_breach": 2800, "penalty_probability": 0.15, "avg_penalty": 10000, "audit_risk_cost": 5000},
        "m_product_discard": {"discard_volume": 400, "avg_cogs_per_unit": 9, "discard_events": 25, "labor_per_event": 120, "disposal_cost_per_unit": 1.5},
        "m_regulatory_penalties": {"penalty_events": 2, "avg_fine": 12000, "remediation_cost": 6000},
        "m_energy_reduction": {"kwh_reduction": 250000, "electricity_rate": 0.12, "carbon_factor": 0.0004, "carbon_price": 50},
        "m_emissions_reduction": {"emissions_reduced_tco2e": 120, "carbon_price": 50, "compliance_reporting_value": 8000},
    },
}


def resolve_metric_inputs(
    scope_type: str,
    scope_id: str,
    overrides: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Resolve metric inputs for a given asset or location scope."""
    if scope_type == "asset":
        # Infer asset type from ID prefix
        asset_type = "RTU"
        sid = scope_id.upper()
        if "WALK" in sid or "WI" in sid:
            asset_type = "WALK_IN"
        elif "RACK" in sid or "RK" in sid:
            asset_type = "RACK"
        base = dict(ASSET_TYPE_PROFILES.get(asset_type, ASSET_TYPE_PROFILES["RTU"]))
    else:
        base = dict(LOCATION_PROFILES.get("default", {}))

    if overrides:
        for metric_id, inputs in overrides.items():
            if metric_id in base:
                base[metric_id].update(inputs)
            else:
                base[metric_id] = inputs

    return base


# ═══════════════════════════════════════════════════════════════════
# Agent Advisor Engine
# ═══════════════════════════════════════════════════════════════════

class AgentAdvisor:
    """
    Runs the 12-agent decision crew scoped to an asset or location,
    producing structured per-agent reasoning traces and cross-silo
    consolidated recommendations.
    """

    def __init__(self, service: Optional[OwnershipDecisionService] = None):
        self.svc = service or get_service()
        self.crew = OwnershipDecisionCrew()
        self.validator = QuadrantValidator(
            self.svc.catalog, self.svc.ownership, self.svc.rules, self.svc.aggregation,
        )
        self.governance = GovernanceEngine(self.svc.catalog, self.svc.ownership)

    def advise(
        self,
        scope_type: str,
        scope_id: str,
        constraints: Optional[Dict[str, Any]] = None,
        metric_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> AgentAdvisorResult:
        """
        Run the full agent advisory pipeline for an asset or location.

        Args:
            scope_type: "asset" or "location"
            scope_id: Asset ID (e.g., "RTU-001") or location ID (e.g., "store-42")
            constraints: Budget/priority constraints
            metric_overrides: Override specific metric inputs

        Returns:
            AgentAdvisorResult with per-agent traces, cross-silo view, and recommendations.
        """
        t0 = time.monotonic()
        run_id = str(uuid.uuid4())

        logger.info(f"=== Agent Advisor: {scope_type}={scope_id} (run_id={run_id}) ===")

        # 1. Resolve metric inputs for this scope
        metric_inputs = resolve_metric_inputs(scope_type, scope_id, metric_overrides)

        # 2. Run the 12-agent decision crew
        crew_result = self.crew.run(
            metric_inputs=metric_inputs,
            constraints=constraints or {},
        )
        crew_dict = crew_result.to_dict()

        # 3. Build per-agent reasoning traces
        agent_traces = self._build_agent_traces(
            metric_inputs, crew_result, scope_type, scope_id,
        )

        # 4. Build cross-silo consolidation view
        cross_silo = self._build_cross_silo(crew_result, metric_inputs)

        # 5. Generate recommendations
        recommendations = self._build_recommendations(
            crew_result, metric_inputs, scope_type, scope_id,
        )

        # 6. Run quadrant validation
        quad_report = self.validator.validate_setup()

        # 7. Governance summary
        gov_summary = self.governance.get_governance_summary()

        elapsed_ms = (time.monotonic() - t0) * 1000

        return AgentAdvisorResult(
            run_id=run_id,
            scope_type=scope_type,
            scope_id=scope_id,
            agent_traces=agent_traces,
            cross_silo=cross_silo,
            recommendations=recommendations,
            pareto_options=[
                o if isinstance(o, dict) else o.to_dict()
                for o in crew_result.pareto_options
            ],
            board_narrative=crew_result.board_narrative,
            quadrant_validation=quad_report.to_dict(),
            governance_status=gov_summary,
            execution_time_ms=elapsed_ms,
            crew_output=crew_dict,
            agent_messages=crew_dict.get("agent_messages", []),
        )

    # ── Agent Trace Builder ───────────────────────────────────────

    def _build_agent_traces(
        self,
        metric_inputs: Dict[str, Dict[str, Any]],
        crew_result: DecisionCrewOutput,
        scope_type: str,
        scope_id: str,
    ) -> List[AgentTrace]:
        """Build detailed reasoning traces for each agent."""
        traces = []
        positions = crew_result.stakeholder_positions
        cost_lines = crew_result.cost_lines_by_dimension
        roi = crew_result.consolidated_roi

        # STAGE 1: Stakeholder agents
        stakeholder_agents = [
            ("fm", "FM Operations Agent", "Q1", 1),
            ("finance", "Finance Agent", "Q2", 1),
            ("compliance", "Compliance/Food Safety Agent", "Q3", 1),
            ("ops", "Operations Agent", "cross", 1),
            ("esg", "ESG/Sustainability Agent", "Q4", 1),
        ]

        for agent_id, role, quad, stage in stakeholder_agents:
            pos = next((p for p in positions if p.agent_id == agent_id), None)
            trace = AgentTrace(
                agent_id=agent_id, agent_role=role, group="stakeholder",
                quadrant=quad, stage=stage,
            )

            # Step 1: Scope assessment
            scope_metrics = self._get_metrics_for_quadrant(quad, metric_inputs)
            trace.reasoning_steps.append(AgentReasoningStep(
                step_id=1, action="assess_scope",
                description=f"Assessing {scope_type} '{scope_id}' for {quad} metrics",
                input_data={"scope": scope_id, "metrics_in_scope": list(scope_metrics.keys())},
                output_data={"metric_count": len(scope_metrics)},
                confidence=0.9 if scope_metrics else 0.3,
                status="completed" if scope_metrics else "warning",
            ))

            # Step 2: Validate evidence
            trace.reasoning_steps.append(AgentReasoningStep(
                step_id=2, action="validate",
                description=f"Validating metric evidence and data quality",
                input_data={"metrics": list(scope_metrics.keys())},
                output_data={
                    "validated": len(scope_metrics),
                    "data_quality": "sufficient" if scope_metrics else "insufficient",
                },
                confidence=0.85 if scope_metrics else 0.4,
            ))

            # Step 3: Emit constraints
            if pos:
                constraints_data = []
                for c in (pos.non_negotiables or []):
                    constraints_data.append({
                        "type": "non_negotiable",
                        "description": c.description,
                        "justification": c.justification,
                    })
                for c in (pos.preferences or []):
                    constraints_data.append({
                        "type": "preference",
                        "description": c.description,
                        "weight": c.weight,
                    })
                trace.reasoning_steps.append(AgentReasoningStep(
                    step_id=3, action="emit_constraints",
                    description=f"Emitting {len(constraints_data)} constraints for negotiation",
                    output_data={"constraints": constraints_data},
                    confidence=0.9,
                ))
                trace.constraints_emitted = constraints_data
                trace.sign_off = pos.sign_off
                trace.conclusion = (
                    f"{'Signed off' if pos.sign_off else 'Objections raised'}: "
                    f"{len(pos.validated_metric_ids)} metrics validated, "
                    f"{len(pos.non_negotiables or [])} hard constraints, "
                    f"{len(pos.preferences or [])} preferences."
                )
                trace.key_findings = [c.description for c in (pos.non_negotiables or [])]
            else:
                trace.conclusion = f"No position data available for {agent_id}."

            trace.duration_ms = 2.0  # Deterministic execution
            traces.append(trace)

        # STAGE 2: Dimension agents
        dim_agents = [
            ("opex_modeler", "Opex Cost Modeler", "Q1", "opex", 2),
            ("capex_modeler", "Capex/Lifecycle Modeler", "Q2", "capex", 2),
            ("risk_modeler", "Risk/Compliance EV Modeler", "Q3", "risk", 2),
            ("strategic_modeler", "Cross-Silo Value Modeler", "Q4", "strategic", 2),
        ]

        for agent_id, role, quad, cost_type, stage in dim_agents:
            lines = cost_lines.get(cost_type, [])
            total = sum(abs(l.get("amount", 0)) for l in lines)
            trace = AgentTrace(
                agent_id=agent_id, agent_role=role, group="dimension",
                quadrant=quad, stage=stage, cost_lines_produced=len(lines),
            )

            trace.reasoning_steps.append(AgentReasoningStep(
                step_id=1, action="translate",
                description=f"Running translation rules for {cost_type} metrics",
                input_data={"cost_type": cost_type, "quadrant": quad},
                output_data={"lines_produced": len(lines), "total_amount": round(total, 2)},
                confidence=0.85 if lines else 0.3,
            ))

            if lines:
                trace.reasoning_steps.append(AgentReasoningStep(
                    step_id=2, action="compute_cost_lines",
                    description=f"Computed {len(lines)} cost lines totaling ${total:,.0f}",
                    output_data={
                        "line_count": len(lines),
                        "total": round(total, 2),
                        "top_line": lines[0] if lines else {},
                    },
                    confidence=0.8,
                ))

            trace.conclusion = (
                f"Produced {len(lines)} {cost_type} cost lines "
                f"(${total:,.0f}) for {quad}."
            )
            trace.key_findings = [
                f"${total:,.0f} in {cost_type} impact identified"
            ] if total > 0 else ["No cost lines produced — missing metric inputs"]
            trace.duration_ms = 3.0
            traces.append(trace)

        # STAGE 3: Reconciliation agent
        adjustments = crew_result.adjustments_applied
        trace = AgentTrace(
            agent_id="reconciler", agent_role="Reconciliation Agent",
            group="governance", quadrant="all", stage=3,
        )
        trace.reasoning_steps.append(AgentReasoningStep(
            step_id=1, action="reconcile",
            description="Merging cost lines and removing double-counting",
            input_data={"total_lines": sum(len(v) for v in cost_lines.values())},
            output_data={
                "adjustments_applied": len(adjustments),
                "dependency_edges": crew_result.lineage_summary.get("dependency_edges", 0),
            },
            confidence=0.9,
        ))
        trace.conclusion = f"Reconciled cost stack with {len(adjustments)} anti-double-counting adjustments."
        trace.key_findings = [f"{len(adjustments)} overlap adjustments applied"]
        trace.duration_ms = 1.5
        traces.append(trace)

        # STAGE 4: Optimizer agent
        pareto = crew_result.pareto_options
        trace = AgentTrace(
            agent_id="optimizer", agent_role="Optimization Agent",
            group="governance", quadrant="all", stage=4,
        )
        pareto_list = [
            o if isinstance(o, dict) else o.to_dict() for o in pareto
        ]
        trace.reasoning_steps.append(AgentReasoningStep(
            step_id=1, action="optimize",
            description=f"Generating Pareto frontier with {len(pareto_list)} options",
            output_data={
                "options": len(pareto_list),
                "recommended": crew_result.recommended_option_id,
            },
            confidence=0.85,
        ))
        trace.conclusion = f"Generated {len(pareto_list)} Pareto-optimal options."
        trace.key_findings = [
            f"{o.get('label', '')}: NPV ${o.get('npv', 0):,.0f}"
            for o in pareto_list[:3]
        ]
        trace.duration_ms = 2.0
        traces.append(trace)

        # STAGE 4: Audit narrator
        trace = AgentTrace(
            agent_id="auditor", agent_role="Audit Narrator",
            group="governance", quadrant="all", stage=4,
        )
        trace.reasoning_steps.append(AgentReasoningStep(
            step_id=1, action="narrate",
            description="Generating board-ready narrative and assumption register",
            output_data={
                "narrative_length": len(crew_result.board_narrative),
                "assumptions": len(crew_result.assumption_register),
            },
            confidence=0.9,
        ))
        trace.conclusion = "Board narrative and assumption register generated."
        trace.key_findings = [
            f"{len(crew_result.assumption_register)} assumptions registered",
            f"Narrative: {len(crew_result.board_narrative)} chars",
        ]
        trace.duration_ms = 1.0
        traces.append(trace)

        return traces

    # ── Cross-Silo Builder ────────────────────────────────────────

    def _build_cross_silo(
        self,
        crew_result: DecisionCrewOutput,
        metric_inputs: Dict[str, Dict[str, Any]],
    ) -> CrossSiloConsolidation:
        """Build the cross-silo consolidation view."""
        dim_lines = crew_result.cost_lines_by_dimension
        roi = crew_result.consolidated_roi

        quad_contributions = {}
        for cost_type, lines in dim_lines.items():
            quad = next(
                (q for q, ct in QUADRANT_COST_TYPE.items() if ct == cost_type), "?"
            )
            total_savings = sum(abs(l.get("amount", 0)) for l in lines)
            total_npv = sum(l.get("npv", 0) for l in lines)
            owners = list({l.get("owner", "") for l in lines if l.get("owner")})

            quad_contributions[quad] = {
                "cost_type": cost_type,
                "line_count": len(lines),
                "total_savings": round(total_savings, 2),
                "total_npv": round(total_npv, 2),
                "owners": owners,
                "pct_of_total": 0,  # Computed below
            }

        # Compute percentage of total
        total = sum(q["total_savings"] for q in quad_contributions.values())
        for q in quad_contributions.values():
            q["pct_of_total"] = round(
                (q["total_savings"] / total * 100) if total > 0 else 0, 1
            )

        # Overlap adjustments
        adjustments = crew_result.adjustments_applied

        # Negotiation summary
        neg = crew_result.negotiation_log
        neg_dict = neg.to_dict() if hasattr(neg, 'to_dict') else (
            neg if isinstance(neg, dict) else {}
        )

        return CrossSiloConsolidation(
            quadrant_contributions=quad_contributions,
            overlap_adjustments=adjustments,
            negotiation_summary=neg_dict,
            unified_npv=roi.get("npv", 0) if isinstance(roi, dict) else 0,
            unified_savings=roi.get("total_savings", 0) if isinstance(roi, dict) else 0,
        )

    # ── Recommendation Builder ────────────────────────────────────

    def _build_recommendations(
        self,
        crew_result: DecisionCrewOutput,
        metric_inputs: Dict[str, Dict[str, Any]],
        scope_type: str,
        scope_id: str,
    ) -> List[Recommendation]:
        """Build actionable recommendations from crew output."""
        recs = []
        dim_lines = crew_result.cost_lines_by_dimension

        # Generate per-quadrant recommendations
        priority = 1
        for cost_type in ["risk", "opex", "capex", "strategic"]:
            lines = dim_lines.get(cost_type, [])
            if not lines:
                continue

            total_savings = sum(abs(l.get("amount", 0)) for l in lines)
            if total_savings <= 0:
                continue

            quad = next(
                (q for q, ct in QUADRANT_COST_TYPE.items() if ct == cost_type), "?"
            )
            owner = lines[0].get("owner", "") if lines else ""

            # Categorize
            if cost_type == "risk":
                category = "compliance"
                horizon = "0-3 months"
                risk_deferred = f"${total_savings:,.0f}/year in unmitigated compliance exposure"
            elif cost_type == "opex" and total_savings < 50000:
                category = "quick_win"
                horizon = "0-3 months"
                risk_deferred = f"${total_savings:,.0f}/year in continued reactive spend"
            elif cost_type == "capex":
                category = "capex"
                horizon = "6-12 months"
                risk_deferred = f"${total_savings:,.0f}/year in deferred replacement value"
            else:
                category = "structural"
                horizon = "3-6 months"
                risk_deferred = f"${total_savings:,.0f}/year in unrealized savings"

            # Determine cross-silo impact
            cross_silo = []
            if cost_type == "risk":
                cross_silo = ["Compliance reduces FM reactive workload", "Reduces ESG audit risk"]
            elif cost_type == "opex":
                cross_silo = ["FM savings free budget for capex investment"]
            elif cost_type == "strategic":
                cross_silo = ["Benefits span FM, Finance, and ESG stakeholders"]

            # Top metric for this dimension
            metric_ids = list({
                mid for l in lines
                for mid in (l.get("input_metric_ids", []) or [])
            })

            recs.append(Recommendation(
                title=f"{'Implement' if category != 'compliance' else 'Address'} "
                      f"{cost_type.title()} savings for {scope_type} {scope_id}",
                quadrant=quad,
                owner=owner,
                savings_annual=total_savings,
                confidence=0.7 if cost_type != "strategic" else 0.55,
                priority=priority,
                category=category,
                rationale=(
                    f"{len(lines)} {cost_type} cost line(s) totaling "
                    f"${total_savings:,.0f}/year identified by {quad} agents. "
                    f"Metrics: {', '.join(metric_ids[:3]) or 'system defaults'}."
                ),
                supporting_agents=self._agents_for_quadrant(quad),
                risk_if_deferred=risk_deferred,
                implementation_horizon=horizon,
                cross_silo_impact=cross_silo,
            ))
            priority += 1

        # Sort by priority (compliance first, then by savings)
        recs.sort(key=lambda r: (
            0 if r.category == "compliance" else 1,
            -r.savings_annual,
        ))
        for i, r in enumerate(recs):
            r.priority = i + 1

        return recs

    # ── Helpers ────────────────────────────────────────────────────

    def _get_metrics_for_quadrant(
        self, quadrant: str, metric_inputs: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """Get metric inputs relevant to a quadrant."""
        if quadrant == "cross":
            return metric_inputs  # Ops sees all
        metrics = self.svc.catalog.list_by_quadrant(quadrant)
        metric_ids = {m.metric_id for m in metrics}
        return {k: v for k, v in metric_inputs.items() if k in metric_ids}

    def _agents_for_quadrant(self, quadrant: str) -> List[str]:
        """Get agent IDs that contribute to a quadrant."""
        agents = []
        for key, info in AGENT_ROSTER.items():
            if info["quadrant"] == quadrant or info["group"] == "governance":
                agents.append(key)
        return agents[:4]
