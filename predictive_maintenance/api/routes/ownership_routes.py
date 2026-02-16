"""
Ownership Decision Support API Routes.

Exposes the ownership-aware decision support module via REST endpoints
for metric catalog, ownership mapping, cost stack, consolidated ROI,
scenarios, parameters, optimization, and audit.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from loweconex_platform.ownership.api_routes import get_service

ownership_router = APIRouter()


# ═══════════════════════════════════════════════════════════════════
# Request / Response Models
# ═══════════════════════════════════════════════════════════════════

class MetricCreateRequest(BaseModel):
    name: str
    description: str = ""
    quadrant: str = "Q1"
    default_owner_role: str = "fm"
    unit_type: str = "count"
    measurement_frequency: str = "monthly"
    source_type: str = "manual"
    created_by: str = "user"


class OwnershipOverrideRequest(BaseModel):
    org_level: str = "global"
    org_entity: str = ""
    accountable: Optional[str] = None
    responsible: Optional[str] = None
    consulted: Optional[List[str]] = None
    informed: Optional[List[str]] = None
    owner_weights: Optional[List[Dict[str, Any]]] = None
    created_by: str = "user"


class ParameterOverrideRequest(BaseModel):
    level: str = "global"
    entity: str = ""
    value: float
    reason: str = ""
    created_by: str = "user"


class MetricInputs(BaseModel):
    """Metric inputs for cost stack / ROI computation."""
    metric_inputs: Dict[str, Dict[str, Any]]
    scenario_id: Optional[str] = None


class AgentAdvisorRequest(BaseModel):
    """Request body for the agent advisor endpoint."""
    scope_type: str = "asset"       # "asset" or "location"
    scope_id: str = "RTU-001"       # Asset ID or location ID
    constraints: Dict[str, Any] = Field(default_factory=dict)
    metric_overrides: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class ScenarioCreateRequest(BaseModel):
    name: str
    description: str = ""
    region: str = ""
    banner: str = ""
    store: str = ""
    parameter_overrides: Dict[str, float] = Field(default_factory=dict)
    owner_budget_overrides: Dict[str, float] = Field(default_factory=dict)
    created_by: str = "user"


class ScenarioRunRequest(BaseModel):
    base_metric_inputs: Dict[str, Dict[str, Any]]


class ScenarioCompareRequest(BaseModel):
    scenario_ids: List[str]
    base_metric_inputs: Dict[str, Dict[str, Any]]


class OptimizeRequest(BaseModel):
    metric_inputs: Dict[str, Dict[str, Any]]
    constraints: Dict[str, Any] = Field(default_factory=dict)


class BudgetCutRequest(BaseModel):
    metric_inputs: Dict[str, Dict[str, Any]]
    cut_pct: float = 0.50
    cut_type: str = "opex"


# ═══════════════════════════════════════════════════════════════════
# Metric Catalog
# ═══════════════════════════════════════════════════════════════════

@ownership_router.get("/metrics")
async def list_metrics(
    quadrant: Optional[str] = Query(None, description="Filter by quadrant (Q1/Q2/Q3/Q4)"),
    owner: Optional[str] = Query(None, description="Filter by default owner role"),
):
    """List all metrics in the catalog, optionally filtered."""
    svc = get_service()
    return svc.get_metrics(quadrant=quadrant, owner=owner)


@ownership_router.post("/metrics")
async def create_metric(body: MetricCreateRequest):
    """Add a custom metric to the catalog."""
    svc = get_service()
    return svc.add_metric(body.model_dump())


# ═══════════════════════════════════════════════════════════════════
# Ownership
# ═══════════════════════════════════════════════════════════════════

@ownership_router.get("/owners")
async def get_ownership_map():
    """Get the full ownership map for all metrics."""
    svc = get_service()
    return svc.get_ownership_map()


@ownership_router.put("/owners/{metric_id}")
async def override_ownership(metric_id: str, body: OwnershipOverrideRequest):
    """Override ownership for a specific metric."""
    svc = get_service()
    return svc.override_ownership(metric_id, body.model_dump())


@ownership_router.get("/owners/by-role/{owner_role}")
async def get_metrics_for_owner(owner_role: str):
    """Get all metrics where the given role is accountable or responsible."""
    svc = get_service()
    return svc.get_metrics_for_owner(owner_role)


@ownership_router.get("/owners/dependencies/{metric_id}")
async def get_cross_silo_dependencies(metric_id: str):
    """Get cross-silo dependency map for a metric."""
    svc = get_service()
    return svc.get_cross_silo_deps(metric_id)


# ═══════════════════════════════════════════════════════════════════
# Parameters
# ═══════════════════════════════════════════════════════════════════

@ownership_router.get("/parameters")
async def list_parameters(
    category: Optional[str] = Query(None, description="Filter by category"),
):
    """List all parameter definitions."""
    svc = get_service()
    return svc.get_parameters(category=category)


@ownership_router.get("/parameters/sliders")
async def get_slider_params():
    """Get high-impact slider parameters for quick controls."""
    svc = get_service()
    return svc.get_slider_params()


@ownership_router.put("/parameters/{param_id}")
async def set_parameter_override(param_id: str, body: ParameterOverrideRequest):
    """Set a parameter override at a hierarchy level."""
    svc = get_service()
    return svc.set_parameter_override(param_id, body.model_dump())


@ownership_router.get("/parameters/resolve")
async def resolve_parameters(
    store: str = Query("", description="Store ID"),
    banner: str = Query("", description="Banner name"),
    region: str = Query("", description="Region name"),
):
    """Resolve all parameters for a given scope (hierarchy walk)."""
    svc = get_service()
    return svc.resolve_parameters(store=store, banner=banner, region=region)


# ═══════════════════════════════════════════════════════════════════
# Cost Stack & ROI
# ═══════════════════════════════════════════════════════════════════

@ownership_router.post("/cost-stack")
async def build_cost_stack(body: MetricInputs):
    """Build a cost stack from metric inputs."""
    svc = get_service()
    return svc.build_cost_stack(body.metric_inputs, body.scenario_id)


@ownership_router.post("/roi")
async def compute_roi(body: MetricInputs):
    """Compute consolidated ROI from metric inputs."""
    svc = get_service()
    return svc.compute_roi(body.metric_inputs, scenario_id=body.scenario_id or "")


# ═══════════════════════════════════════════════════════════════════
# Scenarios
# ═══════════════════════════════════════════════════════════════════

@ownership_router.get("/scenarios")
async def list_scenarios():
    """List all scenarios."""
    svc = get_service()
    return svc.list_scenarios()


@ownership_router.post("/scenarios")
async def create_scenario(body: ScenarioCreateRequest):
    """Create a new scenario."""
    svc = get_service()
    return svc.create_scenario(body.model_dump())


@ownership_router.post("/scenarios/{scenario_id}/run")
async def run_scenario(scenario_id: str, body: ScenarioRunRequest):
    """Run a scenario: resolve params → translate → aggregate → ROI."""
    svc = get_service()
    result = svc.run_scenario(scenario_id, body.base_metric_inputs)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@ownership_router.post("/scenarios/compare")
async def compare_scenarios(body: ScenarioCompareRequest):
    """Compare multiple scenarios side by side."""
    svc = get_service()
    return svc.compare_scenarios(body.scenario_ids, body.base_metric_inputs)


@ownership_router.put("/scenarios/{scenario_id}/status")
async def update_scenario_status(
    scenario_id: str,
    status: str = Query(..., description="New status: review, approved, archived"),
    by: str = Query("user", description="Who is making the change"),
):
    """Update scenario status (draft → review → approved → archived)."""
    svc = get_service()
    return svc.update_scenario_status(scenario_id, status, by)


# ═══════════════════════════════════════════════════════════════════
# Optimization
# ═══════════════════════════════════════════════════════════════════

@ownership_router.post("/optimize")
async def optimize(body: OptimizeRequest):
    """Run constraint-aware optimization on metric inputs."""
    svc = get_service()
    return svc.optimize(body.metric_inputs, body.constraints)


@ownership_router.post("/optimize/budget-cut")
async def simulate_budget_cut(body: BudgetCutRequest):
    """Simulate a budget cut and get recommended reallocation."""
    svc = get_service()
    return svc.simulate_budget_cut(body.metric_inputs, body.cut_pct, body.cut_type)


# ═══════════════════════════════════════════════════════════════════
# Translation Rules
# ═══════════════════════════════════════════════════════════════════

@ownership_router.get("/translation-rules")
async def get_translation_rules(
    quadrant: Optional[str] = Query(None, description="Filter by quadrant"),
):
    """Get translation rules library."""
    svc = get_service()
    return svc.get_translation_rules(quadrant=quadrant)


# ═══════════════════════════════════════════════════════════════════
# Audit & Export
# ═══════════════════════════════════════════════════════════════════

@ownership_router.get("/audit-log")
async def get_audit_log(
    entity_type: Optional[str] = Query(None, description="ownership or parameter"),
    entity_id: Optional[str] = Query(None, description="Specific entity ID"),
):
    """Get audit log of ownership and parameter changes."""
    svc = get_service()
    return svc.get_audit_log(entity_type, entity_id)


@ownership_router.get("/dependency-graph")
async def get_dependency_graph():
    """Get the benefit dependency graph for anti-double-counting."""
    svc = get_service()
    return svc.get_dependency_graph()


@ownership_router.post("/export")
async def export_pack(body: MetricInputs):
    """Generate a complete export pack for budget discussions."""
    svc = get_service()
    return svc.export_pack(body.metric_inputs, body.scenario_id or "")


# ═══════════════════════════════════════════════════════════════════
# Multi-Agent Decision Crew
# ═══════════════════════════════════════════════════════════════════

class CrewRunRequest(BaseModel):
    metric_inputs: Dict[str, Dict[str, Any]]
    constraints: Dict[str, Any] = Field(default_factory=dict)
    scenario_id: Optional[str] = None


@ownership_router.post("/crew/run")
async def run_decision_crew(body: CrewRunRequest):
    """
    Run the 12-agent Ownership Decision Crew.

    Executes the full multi-agent pipeline:
    Stage 0: Parameter resolution
    Stage 1: Stakeholder validation (5 agents parallel)
    Stage 2: Cost translation (4 dimension agents parallel)
    Stage 3: Reconciliation (anti-double-counting)
    Stage 4: Optimization (Pareto frontier) + Audit narrative

    Returns DecisionCrewOutput with cost stack, ROI, Pareto options,
    negotiation log, assumptions, and board narrative.
    """
    try:
        from loweconex_platform.ownership.crew.decision_crew import OwnershipDecisionCrew
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="Ownership Decision Crew module not available",
        )

    svc = get_service()
    crew = OwnershipDecisionCrew(
        catalog=svc.catalog,
        ownership=svc.ownership,
        rules=svc.rules,
        params=svc.params,
        roi_engine=svc.roi_engine,
        optimizer=svc.optimizer,
        aggregation=svc.aggregation,
        scenarios=svc.scenarios,
    )

    result = crew.run(
        metric_inputs=body.metric_inputs,
        constraints=body.constraints,
        scenario_id=body.scenario_id,
    )
    return result.to_dict()


@ownership_router.get("/crew/agents")
async def list_crew_agents():
    """List all agents in the Ownership Decision Crew roster."""
    try:
        from loweconex_platform.ownership.crew.agents import AGENT_ROSTER, get_agent_count
    except ImportError:
        raise HTTPException(status_code=501, detail="Crew module not available")

    roster = []
    for key, info in AGENT_ROSTER.items():
        roster.append({
            "agent_key": key,
            "group": info["group"],
            "quadrant": info["quadrant"],
        })

    return {
        "agents": roster,
        "total": get_agent_count(),
        "groups": {
            "stakeholder": len([r for r in roster if r["group"] == "stakeholder"]),
            "dimension": len([r for r in roster if r["group"] == "dimension"]),
            "governance": len([r for r in roster if r["group"] == "governance"]),
        },
    }


# ═══════════════════════════════════════════════════════════════════
# Quadrant Validation
# ═══════════════════════════════════════════════════════════════════

def _get_validator():
    from loweconex_platform.ownership.quadrant_validator import QuadrantValidator
    svc = get_service()
    return QuadrantValidator(svc.catalog, svc.ownership, svc.rules, svc.aggregation)


@ownership_router.get("/quadrant/validate")
async def validate_quadrant_wiring():
    """Run full quadrant wiring validation (setup + rules)."""
    validator = _get_validator()
    report = validator.validate_setup()
    return report.to_dict()


@ownership_router.get("/quadrant/summary")
async def quadrant_summary():
    """Get per-quadrant summary of metrics, rules, and owners."""
    validator = _get_validator()
    return validator.get_quadrant_summary()


@ownership_router.post("/quadrant/validate-stack")
async def validate_cost_stack_quadrants(body: MetricInputs):
    """Validate cost stack lines match quadrant expectations."""
    validator = _get_validator()
    svc = get_service()
    stack = svc.aggregation.build_cost_stack(body.metric_inputs)
    report = validator.validate_cost_lines(stack)
    return report.to_dict()


# ═══════════════════════════════════════════════════════════════════
# Governance
# ═══════════════════════════════════════════════════════════════════

_governance_engine = None


def _get_governance():
    global _governance_engine
    if _governance_engine is None:
        from loweconex_platform.ownership.governance_engine import GovernanceEngine
        svc = get_service()
        _governance_engine = GovernanceEngine(svc.catalog, svc.ownership)
    return _governance_engine


class ChangeRequestBody(BaseModel):
    change_type: str
    requestor: str
    description: str
    metric_id: str = ""
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    justification: str = ""


class ApprovalBody(BaseModel):
    approver: str
    note: str = ""


class RejectionBody(BaseModel):
    rejector: str
    reason: str


@ownership_router.post("/governance/changes")
async def submit_change(body: ChangeRequestBody):
    """Submit a governance change request."""
    ge = _get_governance()
    cr = ge.submit_change(
        change_type=body.change_type,
        requestor=body.requestor,
        description=body.description,
        metric_id=body.metric_id,
        old_value=body.old_value,
        new_value=body.new_value,
        justification=body.justification,
    )
    return cr.to_dict()


@ownership_router.post("/governance/changes/{change_id}/approve")
async def approve_change(change_id: str, body: ApprovalBody):
    """Approve a pending change request."""
    ge = _get_governance()
    try:
        cr = ge.approve_change(change_id, body.approver, body.note)
        return cr.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@ownership_router.post("/governance/changes/{change_id}/reject")
async def reject_change(change_id: str, body: RejectionBody):
    """Reject a pending change request."""
    ge = _get_governance()
    try:
        cr = ge.reject_change(change_id, body.rejector, body.reason)
        return cr.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@ownership_router.get("/governance/pending")
async def get_pending_approvals(
    approver: Optional[str] = Query(None, description="Filter by approver role"),
):
    """Get all pending governance change requests."""
    ge = _get_governance()
    pending = ge.get_pending_approvals(approver or "")
    return {"changes": [c.to_dict() for c in pending], "count": len(pending)}


@ownership_router.get("/governance/history")
async def get_change_history(
    metric_id: Optional[str] = Query(None),
    change_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Get governance change request history."""
    ge = _get_governance()
    history = ge.get_change_history(metric_id or "", change_type or "", limit)
    return {"changes": [c.to_dict() for c in history], "count": len(history)}


@ownership_router.get("/governance/audit")
async def get_governance_audit(
    entity_id: Optional[str] = Query(None),
    actor: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """Get governance audit log."""
    ge = _get_governance()
    entries = ge.get_audit_log(entity_id or "", actor or "", limit)
    return {"entries": [e.to_dict() for e in entries], "count": len(entries)}


@ownership_router.get("/governance/summary")
async def get_governance_summary():
    """Get governance summary with approval rates and RACI validation."""
    ge = _get_governance()
    return ge.get_governance_summary()


@ownership_router.get("/governance/check-auth")
async def check_authorization(
    actor: str = Query(..., description="Actor role"),
    action: str = Query(..., description="Action: approve, modify, review, view"),
    metric_id: str = Query(..., description="Metric ID"),
):
    """Check if an actor is authorized for an action on a metric."""
    ge = _get_governance()
    return ge.validate_ownership_action(actor, action, metric_id)


# ═══════════════════════════════════════════════════════════════════
# Agent Advisor
# ═══════════════════════════════════════════════════════════════════

_agent_advisor = None


def _get_advisor():
    global _agent_advisor
    if _agent_advisor is None:
        from loweconex_platform.ownership.crew.agent_advisor import AgentAdvisor
        _agent_advisor = AgentAdvisor()
    return _agent_advisor


@ownership_router.post("/agent-advisor")
async def run_agent_advisor(body: AgentAdvisorRequest):
    """
    Run the 12-agent advisory crew scoped to an asset or location.

    Returns per-agent reasoning traces, cross-silo consolidation,
    and actionable recommendations.
    """
    advisor = _get_advisor()
    result = advisor.advise(
        scope_type=body.scope_type,
        scope_id=body.scope_id,
        constraints=body.constraints or None,
        metric_overrides=body.metric_overrides or None,
    )
    return result.to_dict()


@ownership_router.get("/agent-advisor/profiles")
async def get_advisor_profiles():
    """Get available asset and location profiles from real fleet data."""
    from loweconex_platform.ownership.crew.agent_advisor import (
        ASSET_TYPE_PROFILES, LOCATION_PROFILES,
    )

    sample_assets = []
    sample_locations = []

    try:
        from ...persistence.database import get_session
        from ...persistence.models import AssetModel

        with get_session() as session:
            assets = (
                session.query(AssetModel)
                .filter(AssetModel.is_active == True)
                .order_by(AssetModel.asset_id)
                .all()
            )

            seen_sites = set()
            for a in assets:
                atype = (a.asset_type or "hvac_rtu").upper().replace(" ", "_")
                mfr = a.manufacturer or ""
                model = a.model_number or ""
                label_parts = [atype, mfr, model]
                label = " — ".join(p for p in label_parts if p) or a.asset_id
                sample_assets.append({
                    "id": a.asset_id,
                    "type": atype,
                    "label": label,
                })

                site = a.site_id or "unknown"
                if site not in seen_sites:
                    seen_sites.add(site)
                    sample_locations.append({
                        "id": site,
                        "label": site.replace("_", " ").title(),
                    })
    except Exception:
        pass

    # Fallback if DB returned nothing
    if not sample_assets:
        sample_assets = [
            {"id": "RTU-001", "type": "RTU", "label": "Rooftop Unit #001"},
            {"id": "WI-001", "type": "WALK_IN", "label": "Walk-In Cooler #001"},
            {"id": "RK-001", "type": "RACK", "label": "Rack System #001"},
        ]
    if not sample_locations:
        sample_locations = [
            {"id": "store-001", "label": "Store #001 — Flagship"},
            {"id": "store-042", "label": "Store #042 — Distribution Hub"},
        ]

    return {
        "asset_types": list(ASSET_TYPE_PROFILES.keys()),
        "sample_assets": sample_assets,
        "sample_locations": sample_locations,
    }
