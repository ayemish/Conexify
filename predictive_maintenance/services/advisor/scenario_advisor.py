"""Unified Scenario Advisor — conversational interface for multi-agent scenario optimization.

Provides natural-language interaction with:
- Session management (in-memory)
- 11 registered tool functions (6 RMN + 5 D&P)
- Intent inference engine for offline fallback
- RAG-augmented context building
- Dual online/offline message pipeline
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from .openai_client import OpenAIClient, ToolDefinition, ChatResponse
from .rag_store import RagStore, RagSearchResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & Data Classes
# ---------------------------------------------------------------------------

class Ecosystem(str, Enum):
    RMN = "rmn"
    DEMAND_PROCUREMENT = "demand_procurement"
    AUTO = "auto"


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"
    TOOL = "tool"


@dataclass
class ChatMessage:
    role: MessageRole
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Any]] = None
    tool_call_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"role": self.role.value, "content": self.content}
        if self.name:
            d["name"] = self.name
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        d["timestamp"] = self.timestamp.isoformat()
        return d

    def to_openai_dict(self) -> Dict[str, Any]:
        """Convert to OpenAI message format (no timestamp)."""
        d: Dict[str, Any] = {"role": self.role.value, "content": self.content or ""}
        if self.name:
            d["name"] = self.name
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        return d


@dataclass
class AdvisorSession:
    session_id: str
    created_at: datetime
    messages: List[ChatMessage] = field(default_factory=list)
    ecosystem: Ecosystem = Ecosystem.AUTO
    context: Dict[str, Any] = field(default_factory=dict)

    def add_message(self, role: MessageRole, content: str, **kwargs) -> ChatMessage:
        msg = ChatMessage(role=role, content=content, **kwargs)
        self.messages.append(msg)
        return msg

    def get_history(self) -> List[Dict[str, Any]]:
        return [m.to_dict() for m in self.messages]


@dataclass
class AdvisorResponse:
    message: str
    ecosystem: Optional[Ecosystem] = None
    scenario_ids: List[str] = field(default_factory=list)
    data: Optional[Dict[str, Any]] = None
    actions: List[Dict[str, Any]] = field(default_factory=list)
    agent_source: Optional[str] = None
    confidence: float = 0.5
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": self.message,
            "ecosystem": self.ecosystem.value if self.ecosystem else None,
            "scenario_ids": self.scenario_ids,
            "data": self.data,
            "actions": self.actions,
            "agent_source": self.agent_source,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
        }


# ---------------------------------------------------------------------------
# Scenario Catalog — HVAC/R Predictive Maintenance Scenarios
# ---------------------------------------------------------------------------

_SCENARIO_CATALOG: List[Dict[str, Any]] = [
    # A. Energy & Efficiency
    {"scenario_id": "energy_reduction", "name": "Energy Reduction Analysis", "category": "energy_efficiency",
     "description": "Analyze energy savings from PdM-driven HVAC/R optimization across the fleet.",
     "objective": "reduce_energy", "tags": ["energy", "hvac", "savings", "pdm", "kwh"],
     "required_crews": ["energy_reduction"], "triggers": ["high_energy_usage", "utility_rate_change"]},
    {"scenario_id": "energy_cost_sensitivity", "name": "Energy Cost Sensitivity", "category": "energy_efficiency",
     "description": "What-if analysis on energy savings under different utility rate scenarios.",
     "objective": "assess_energy_risk", "tags": ["energy", "cost", "sensitivity", "utility"],
     "required_crews": ["energy_reduction"], "triggers": ["rate_increase", "budget_planning"]},
    {"scenario_id": "condenser_fouling_impact", "name": "Condenser Fouling Impact", "category": "energy_efficiency",
     "description": "Estimate energy penalty and savings from addressing condenser fouling across the fleet.",
     "objective": "reduce_fouling", "tags": ["condenser", "fouling", "energy", "cleaning"],
     "required_crews": ["energy_reduction"], "triggers": ["fouling_detected", "efficiency_drop"]},
    # B. Refrigerant Management
    {"scenario_id": "refrigerant_leak_prevention", "name": "Refrigerant Leak Prevention", "category": "refrigerant_management",
     "description": "Estimate savings from early refrigerant leak detection and prevention.",
     "objective": "reduce_leaks", "tags": ["refrigerant", "leak", "epa", "compliance", "charge"],
     "required_crews": ["refrigerant_leak_reduction"], "triggers": ["leak_detected", "charge_low"]},
    {"scenario_id": "refrigerant_transition", "name": "Refrigerant Transition Planning", "category": "refrigerant_management",
     "description": "Plan transition from high-GWP refrigerants (R-410A) to low-GWP alternatives.",
     "objective": "reduce_gwp", "tags": ["refrigerant", "gwp", "transition", "r410a", "epa"],
     "required_crews": ["refrigerant_leak_reduction", "esg_carbon_reduction"], "triggers": ["regulation_change", "epa_phase_down"]},
    # C. Work Order & Maintenance
    {"scenario_id": "work_order_optimization", "name": "Work Order Optimization", "category": "maintenance_ops",
     "description": "Convert reactive work orders to planned maintenance via predictive insights.",
     "objective": "reduce_reactive_wo", "tags": ["work_order", "maintenance", "reactive", "planned"],
     "required_crews": ["work_order_reduction"], "triggers": ["wo_backlog_high", "repeat_failure"]},
    {"scenario_id": "pm_interval_optimization", "name": "PM Interval Optimization", "category": "maintenance_ops",
     "description": "Optimize preventive maintenance intervals using condition-based monitoring data.",
     "objective": "optimize_pm_schedule", "tags": ["pm", "interval", "schedule", "condition_based"],
     "required_crews": ["work_order_reduction", "ppm_maximization"], "triggers": ["over_maintenance", "pm_review"]},
    {"scenario_id": "service_bureau_reduction", "name": "Service Bureau Reduction", "category": "maintenance_ops",
     "description": "Reduce third-party service dispatches by handling more maintenance in-house with PdM insights.",
     "objective": "reduce_dispatches", "tags": ["service_bureau", "dispatch", "contractor", "cost"],
     "required_crews": ["service_bureau_reduction"], "triggers": ["dispatch_cost_high", "contractor_review"]},
    {"scenario_id": "defer_maintenance_risk", "name": "Defer Maintenance Risk", "category": "maintenance_ops",
     "description": "Assess the risk and cost implications of deferring maintenance on specific assets or fleets.",
     "objective": "assess_deferral_risk", "tags": ["defer", "risk", "rul", "failure_probability"],
     "required_crews": ["asset_failure_prediction"], "triggers": ["budget_constraint", "deferral_request"]},
    # D. CapEx & Lifecycle
    {"scenario_id": "capex_planning", "name": "CapEx Planning", "category": "capex_lifecycle",
     "description": "Optimize capital expenditure timing using asset health and remaining useful life data.",
     "objective": "optimize_capex", "tags": ["capex", "replacement", "lifecycle", "budget", "npv"],
     "required_crews": ["capex_lifecycle_optimization"], "triggers": ["asset_aging", "budget_cycle"]},
    {"scenario_id": "replace_vs_repair", "name": "Replace vs Repair Analysis", "category": "capex_lifecycle",
     "description": "NPV-based comparison of repairing vs replacing aging assets using health and cost data.",
     "objective": "compare_repair_replace", "tags": ["replace", "repair", "npv", "payback", "lifecycle"],
     "required_crews": ["capex_lifecycle_optimization"], "triggers": ["asset_failure", "repair_cost_high"]},
    {"scenario_id": "budget_sensitivity", "name": "CapEx Budget Sensitivity", "category": "capex_lifecycle",
     "description": "Analyze how different CapEx budget levels impact fleet NPV and asset replacement count.",
     "objective": "assess_budget_impact", "tags": ["budget", "sensitivity", "npv", "capex"],
     "required_crews": ["capex_lifecycle_optimization"], "triggers": ["budget_review", "fiscal_year"]},
    # E. Asset Health & Reliability
    {"scenario_id": "fleet_health_assessment", "name": "Fleet Health Assessment", "category": "asset_reliability",
     "description": "Comprehensive health assessment across all HVAC/R assets in the fleet.",
     "objective": "assess_fleet", "tags": ["fleet", "health", "assessment", "overview", "rul"],
     "required_crews": ["asset_failure_prediction"], "triggers": ["quarterly_review", "new_onboarding"]},
    {"scenario_id": "uptime_maximization", "name": "Uptime Maximization", "category": "asset_reliability",
     "description": "Maximize equipment uptime through predictive failure prevention.",
     "objective": "maximize_uptime", "tags": ["uptime", "availability", "reliability", "downtime"],
     "required_crews": ["asset_uptime_increase"], "triggers": ["downtime_event", "rul_low"]},
    {"scenario_id": "critical_asset_triage", "name": "Critical Asset Triage", "category": "asset_reliability",
     "description": "Identify and prioritize the most at-risk assets requiring immediate attention.",
     "objective": "triage_critical", "tags": ["triage", "critical", "risk", "priority", "failure"],
     "required_crews": ["asset_failure_prediction"], "triggers": ["health_score_low", "multiple_faults"]},
    {"scenario_id": "failure_mode_analysis", "name": "Failure Mode Analysis", "category": "asset_reliability",
     "description": "Analyze common failure modes across the fleet and recommend targeted interventions.",
     "objective": "analyze_failures", "tags": ["failure_mode", "fault", "pattern", "root_cause"],
     "required_crews": ["asset_failure_prediction", "work_order_reduction"], "triggers": ["repeat_failure", "fault_cluster"]},
    # F. Food Safety & Compliance
    {"scenario_id": "food_safety_protection", "name": "Food Safety Protection", "category": "food_safety",
     "description": "Prevent temperature excursions and food safety violations through proactive monitoring.",
     "objective": "prevent_excursions", "tags": ["food_safety", "temperature", "compliance", "excursion"],
     "required_crews": ["food_waste_reduction", "food_safety_compliance"], "triggers": ["temp_excursion", "violation_risk"]},
    {"scenario_id": "cold_chain_integrity", "name": "Cold Chain Integrity", "category": "food_safety",
     "description": "Assess cold chain integrity across refrigeration assets and identify gaps.",
     "objective": "protect_cold_chain", "tags": ["cold_chain", "refrigeration", "temperature", "shrink"],
     "required_crews": ["food_waste_reduction"], "triggers": ["shrink_increase", "temp_drift"]},
    # G. ESG & Sustainability
    {"scenario_id": "esg_compliance", "name": "ESG Compliance Report", "category": "esg_sustainability",
     "description": "Generate ESG metrics including carbon reduction from PdM and refrigerant GWP management.",
     "objective": "esg_reporting", "tags": ["esg", "carbon", "sustainability", "gwp", "emissions"],
     "required_crews": ["esg_carbon_reduction"], "triggers": ["reporting_period", "esg_audit"]},
    {"scenario_id": "carbon_reduction_plan", "name": "Carbon Reduction Plan", "category": "esg_sustainability",
     "description": "Model carbon reduction scenarios from energy efficiency, refrigerant management, and fleet optimization.",
     "objective": "reduce_carbon", "tags": ["carbon", "reduction", "energy", "refrigerant", "sustainability"],
     "required_crews": ["esg_carbon_reduction", "energy_reduction"], "triggers": ["esg_target", "carbon_goal"]},
    # H. Call Center & Operations
    {"scenario_id": "call_center_reduction", "name": "Call Center Volume Reduction", "category": "operations",
     "description": "Reduce inbound maintenance calls through proactive alerting and self-service diagnostics.",
     "objective": "reduce_calls", "tags": ["call_center", "volume", "proactive", "alerting"],
     "required_crews": ["call_center_reduction"], "triggers": ["call_volume_high", "repeat_calls"]},
    {"scenario_id": "alert_threshold_tuning", "name": "Alert Threshold Tuning", "category": "operations",
     "description": "Tune alert thresholds and routing to reduce noisy alarms while maintaining detection coverage.",
     "objective": "reduce_alert_noise", "tags": ["alerts", "threshold", "alarm_fatigue", "false_alarms"],
     "required_crews": ["asset_failure_prediction", "work_order_reduction"], "triggers": ["alert_noise_high", "false_alarm_rate_high"]},
    {"scenario_id": "emergency_response", "name": "Emergency Response Planning", "category": "operations",
     "description": "Plan rapid response protocols for critical equipment failures and safety events.",
     "objective": "crisis_management", "tags": ["emergency", "rapid", "crisis", "safety", "response"],
     "required_crews": ["asset_failure_prediction", "asset_uptime_increase"], "triggers": ["critical_failure", "safety_event"]},
]

# Build lookup indexes
_CATALOG_BY_ID = {s["scenario_id"]: s for s in _SCENARIO_CATALOG}
_CATALOG_BY_NAME = {s["name"].lower(): s for s in _SCENARIO_CATALOG}

# Scenario catalog crew aliases -> canonical KPI IDs used by orchestrators.
_CREW_TO_KPI_ALIASES: Dict[str, str] = {
    "esg_carbon_reduction": "esg_compliance",
    "call_center_reduction": "call_center_volume_reduction",
}


# ---------------------------------------------------------------------------
# Default fleet state
# ---------------------------------------------------------------------------

_DEFAULT_FLEET_STATE = {
    "fleet_summary": {
        "total_assets": 50,
        "total_locations": 3,
        "avg_health_score": 72.5,
        "degraded_count": 12,
        "critical_count": 3,
        "avg_rul_hours": 4200,
        "open_work_orders": 18,
        "reactive_wo_pct": 0.45,
    },
    "kpi_summary": {
        "total_annual_savings_medium": 0,
        "approved_kpis": 0,
        "top_kpi": "energy_reduction",
        "avg_confidence": 0.0,
    },
    "maintenance_budget": {
        "annual_budget": 500_000,
        "ytd_spend": 0,
        "capex_budget": 250_000,
        "capex_ytd": 0,
    },
    "last_updated": datetime.utcnow().isoformat(),
}


# ---------------------------------------------------------------------------
# Intent → Scenario mapping (offline)
# ---------------------------------------------------------------------------

_INTENT_MAP: List[Tuple[List[str], str]] = [
    (["repair vs replace", "replace vs repair", "replace or repair"], "replace_vs_repair"),
    (["change alerts", "alert threshold", "alerts threshold", "noisy alerts", "alarm fatigue", "false alarms"], "alert_threshold_tuning"),
    (["energy", "kwh", "power", "electricity", "utility"], "energy_reduction"),
    (["refrigerant", "leak", "charge", "r-410a", "r410a", "freon"], "refrigerant_leak_prevention"),
    (["work order", "reactive", "planned maintenance", "wo "], "work_order_optimization"),
    (["capex", "capital", "replacement", "lifecycle"], "capex_planning"),
    (["fleet health", "health assessment", "fleet overview"], "fleet_health_assessment"),
    (["uptime", "downtime", "availability", "reliability"], "uptime_maximization"),
    (["food safety", "temperature", "excursion", "violation"], "food_safety_protection"),
    (["esg", "carbon", "sustainability", "emissions", "gwp"], "esg_compliance"),
    (["defer", "deferral", "postpone", "delay maintenance"], "defer_maintenance_risk"),
    (["triage", "critical", "at-risk", "at risk", "urgent"], "critical_asset_triage"),
    (["failure mode", "fault pattern", "root cause", "repeat failure"], "failure_mode_analysis"),
    (["call center", "calls", "call volume"], "call_center_reduction"),
    (["service bureau", "dispatch", "contractor"], "service_bureau_reduction"),
    (["pm interval", "pm schedule", "preventive maintenance"], "pm_interval_optimization"),
    (["cold chain", "shrink", "food waste"], "cold_chain_integrity"),
    (["budget sensitivity", "budget impact"], "budget_sensitivity"),
    (["emergency", "crisis", "critical failure"], "emergency_response"),
    (["condenser", "fouling", "coil cleaning"], "condenser_fouling_impact"),
    (["transition", "phase down", "low gwp"], "refrigerant_transition"),
]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the PdM Scenario Advisor — a knowledgeable, conversational assistant for HVAC/R predictive maintenance.

Your role is to help facility managers and maintenance teams **understand, prioritize, and act** on their equipment data. You explain complex maintenance concepts in plain language, interpret data in context, and recommend next steps.

## How to respond
- **Be conversational.** Write in natural language, not bullet-point data dumps. Explain what numbers mean and why they matter.
- **Interpret, don't just report.** Instead of listing raw data, explain: "Your fleet health score of 72 means roughly 1 in 4 assets is degraded — that's typical for a fleet this age, but the 3 critical assets need immediate attention."
- **Prioritize for the user.** When presenting options, lead with what matters most and explain trade-offs.
- **Use plain language first, then specifics.** Start with the headline insight, then support with numbers, asset IDs, and confidence levels.
- **Ask clarifying questions** when the user's intent is ambiguous — about their site, budget, timeline, or risk tolerance.
- **Recommend concrete next steps.** End responses with 1-3 actionable recommendations when appropriate.

## What you know about
- 21 pre-built optimization scenarios across energy, refrigerant, maintenance, CapEx, reliability, food safety, ESG, and operations
- 14 KPI dimensions with savings estimates, confidence scores, and approval status
- Fleet health metrics: asset health scores, remaining useful life (RUL), fault probabilities
- CapEx planning with NPV analysis and budget optimization
- What-if scenario modeling with custom parameters

## Response style
- Keep responses focused and concise (2-4 paragraphs typical)
- Use bold for key numbers and recommendations
- When referencing savings, always mention the confidence level so the user knows how trustworthy the estimate is
- If data is limited, be transparent: explain what's missing and how uploading more data would improve the analysis"""


# ---------------------------------------------------------------------------
# UnifiedScenarioAdvisor
# ---------------------------------------------------------------------------

class UnifiedScenarioAdvisor:
    """Conversational interface for multi-agent scenario optimization.

    Parameters
    ----------
    rag : RagStore, optional
        RAG store instance. Created internally if not provided.
    client : OpenAIClient, optional
        OpenAI client. Created internally if not provided.
    twin_manager : object, optional
        Digital twin manager for live state. Falls back to defaults.
    """

    def __init__(
        self,
        rag: Optional[RagStore] = None,
        client: Optional[OpenAIClient] = None,
        twin_manager: Optional[Any] = None,
    ):
        self.rag = rag or RagStore()
        self.client = client or OpenAIClient()
        self.twin_manager = twin_manager
        self.sessions: Dict[str, AdvisorSession] = {}
        self.catalog = list(_SCENARIO_CATALOG)
        self._register_tools()
        self._index_scenario_catalog()
        self._hydrate_sessions_from_db()

    # ------------------------------------------------------------------
    # Session Management
    # ------------------------------------------------------------------

    def create_session(self, ecosystem: str = "auto") -> AdvisorSession:
        session_id = str(uuid.uuid4())
        eco = Ecosystem(ecosystem) if ecosystem in [e.value for e in Ecosystem] else Ecosystem.AUTO
        session = AdvisorSession(
            session_id=session_id,
            created_at=datetime.utcnow(),
            ecosystem=eco,
        )
        session.add_message(MessageRole.SYSTEM, SYSTEM_PROMPT)
        self.sessions[session_id] = session
        self._db_create_session(session_id, eco.value)
        return session

    def get_session(self, session_id: str) -> Optional[AdvisorSession]:
        return self.sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        removed = self.sessions.pop(session_id, None) is not None
        if removed:
            self._db_delete_session(session_id)
        return removed

    def get_history(self, session_id: str) -> Optional[List[Dict[str, Any]]]:
        session = self.get_session(session_id)
        if session is None:
            return None
        return session.get_history()

    # ------------------------------------------------------------------
    # Tool Registration
    # ------------------------------------------------------------------

    def _register_tools(self):
        """Register PdM scenario advisor tools."""
        self.client.register_tool(ToolDefinition(
            name="list_maintenance_scenarios",
            description="List all available HVAC/R predictive maintenance scenarios, optionally filtered by category.",
            parameters={"type": "object", "properties": {
                "category": {"type": "string", "description": "Filter by category (energy_efficiency, refrigerant_management, maintenance_ops, capex_lifecycle, asset_reliability, food_safety, esg_sustainability, operations)"}
            }},
            handler=self._tool_list_scenarios,
        ))
        self.client.register_tool(ToolDefinition(
            name="get_scenario_details",
            description="Get the full definition of a specific maintenance scenario by its ID.",
            parameters={"type": "object", "properties": {
                "scenario_id": {"type": "string", "description": "The scenario ID to look up"}
            }, "required": ["scenario_id"]},
            handler=self._tool_get_scenario_details,
        ))
        self.client.register_tool(ToolDefinition(
            name="recommend_scenario",
            description="Recommend the best maintenance scenario based on a stated objective (e.g. reduce energy, optimize capex, improve uptime).",
            parameters={"type": "object", "properties": {
                "objective": {"type": "string", "description": "The maintenance objective to optimize for"}
            }, "required": ["objective"]},
            handler=self._tool_recommend_scenario,
        ))
        self.client.register_tool(ToolDefinition(
            name="search_knowledge",
            description="Semantic search over the RAG knowledge base for maintenance scenarios, KPI results, and documentation.",
            parameters={"type": "object", "properties": {
                "query": {"type": "string", "description": "Search query"}
            }, "required": ["query"]},
            handler=self._tool_search_knowledge,
        ))
        self.client.register_tool(ToolDefinition(
            name="execute_scenario",
            description="Execute a maintenance scenario with optional parameter overrides against real fleet data.",
            parameters={"type": "object", "properties": {
                "scenario_id": {"type": "string", "description": "Scenario to execute"},
                "site_id": {"type": "string", "description": "Site ID to run against", "default": "default"},
                "parameters": {"type": "object", "description": "KPIConfig parameter overrides (e.g. energy_cost_per_kwh, baseline_reactive_wo_per_month)"},
                "risk_appetite": {"type": "string", "enum": ["conservative", "balanced", "aggressive"]},
            }, "required": ["scenario_id"]},
            handler=self._tool_execute_scenario,
        ))
        self.client.register_tool(ToolDefinition(
            name="get_fleet_state",
            description="Retrieve the current fleet health state, KPI summaries, and maintenance budget overview.",
            parameters={"type": "object", "properties": {
                "site_id": {"type": "string", "description": "Optional: specific site to query"}
            }},
            handler=self._tool_get_fleet_state,
        ))
        self.client.register_tool(ToolDefinition(
            name="get_asset_health",
            description="Get health details for a specific asset including health score, RUL, fault probability, and sensor trust.",
            parameters={"type": "object", "properties": {
                "asset_id": {"type": "string", "description": "Asset ID to query"}
            }, "required": ["asset_id"]},
            handler=self._tool_get_asset_health,
        ))
        self.client.register_tool(ToolDefinition(
            name="run_kpi_dashboard",
            description="Run the full 14-KPI dashboard computation for a site and return savings estimates.",
            parameters={"type": "object", "properties": {
                "site_id": {"type": "string", "description": "Site ID to compute KPIs for", "default": "default"}
            }},
            handler=self._tool_run_kpi_dashboard,
        ))
        self.client.register_tool(ToolDefinition(
            name="compare_scenarios",
            description="Compare two maintenance scenarios side by side showing savings delta.",
            parameters={"type": "object", "properties": {
                "scenario_a": {"type": "string", "description": "First scenario ID"},
                "scenario_b": {"type": "string", "description": "Second scenario ID"},
            }, "required": ["scenario_a", "scenario_b"]},
            handler=self._tool_compare_scenarios,
        ))

    # ------------------------------------------------------------------
    # PdM Tool Handlers
    # ------------------------------------------------------------------

    def _tool_list_scenarios(self, category: Optional[str] = None) -> Dict[str, Any]:
        scenarios = self.catalog
        if category:
            scenarios = [s for s in scenarios if s.get("category") == category]
        return {
            "scenarios": [
                {"scenario_id": s["scenario_id"], "name": s["name"], "category": s["category"],
                 "description": s["description"]}
                for s in scenarios
            ],
            "count": len(scenarios),
        }

    def _tool_get_scenario_details(self, scenario_id: str) -> Dict[str, Any]:
        scenario = _CATALOG_BY_ID.get(scenario_id)
        if not scenario:
            return {"error": f"Scenario '{scenario_id}' not found", "available_ids": list(_CATALOG_BY_ID.keys())}
        return dict(scenario)

    def _tool_recommend_scenario(self, objective: str) -> Dict[str, Any]:
        results = self.rag.search(objective, top_k=3, doc_type="scenario_catalog")
        if results:
            best = results[0]
            scenario_id = best.metadata.get("scenario_id", "")
            scenario = _CATALOG_BY_ID.get(scenario_id, {})
            return {
                "recommended_scenario_id": scenario_id,
                "name": scenario.get("name", ""),
                "description": scenario.get("description", ""),
                "match_score": round(best.score, 3),
                "alternatives": [
                    {"scenario_id": r.metadata.get("scenario_id", ""), "score": round(r.score, 3)}
                    for r in results[1:]
                ],
            }
        return {"error": "No matching scenarios found", "objective": objective}

    def _tool_search_knowledge(self, query: str) -> Dict[str, Any]:
        results = self.rag.search(query, top_k=5)
        return {
            "results": [
                {"doc_id": r.doc_id, "doc_type": r.doc_type, "content": r.content[:200],
                 "score": round(r.score, 3), "metadata": r.metadata}
                for r in results
            ],
            "count": len(results),
        }

    def _tool_execute_scenario(
        self,
        scenario_id: str,
        site_id: str = "default",
        parameters: Optional[Dict[str, Any]] = None,
        risk_appetite: str = "balanced",
    ) -> Dict[str, Any]:
        return self._execute_scenario(
            scenario_id, site_id, parameters, risk_appetite
        )

    def _tool_get_fleet_state(self, site_id: Optional[str] = None) -> Dict[str, Any]:
        return self._get_current_state(site_id)

    def _tool_get_asset_health(self, asset_id: str) -> Dict[str, Any]:
        """Get health details for a specific asset from the PdM kernel."""
        try:
            from predictive_maintenance.api.routes._routes_legacy import get_pdm_system
            system = get_pdm_system(asset_id)
            if system and hasattr(system, "health_index"):
                hi = system.health_index
                return {
                    "asset_id": asset_id,
                    "health_score": getattr(hi, "health_score", None),
                    "health_band": getattr(hi, "health_band", "unknown"),
                    "rul_hours": getattr(hi, "rul_hours", None),
                    "sensor_trust_score": getattr(hi, "sensor_trust_score", None),
                    "fault_probability_score": getattr(hi, "fault_probability_score", None),
                    "degradation_score": getattr(hi, "degradation_score", None),
                    "primary_fault": getattr(hi, "primary_fault", None),
                }
        except Exception as e:
            logger.debug("Asset health lookup failed for %s: %s", asset_id, e)
        return {"asset_id": asset_id, "error": "Asset not found or no health data available"}

    def _tool_run_kpi_dashboard(self, site_id: str = "default") -> Dict[str, Any]:
        """Run the full KPI dashboard computation for a site."""
        try:
            from predictive_maintenance.api.routes.kpi_fleet_routes import compute_dashboard_data

            dashboard = compute_dashboard_data(site_id=site_id, run_scenarios=True)
            self._index_kpi_dashboard(site_id=site_id, dashboard=dashboard)
            return dashboard
        except Exception as e:
            logger.warning("KPI dashboard computation failed: %s", e)
            return {"error": f"KPI computation failed: {e}"}

    def _tool_compare_scenarios(self, scenario_a: str, scenario_b: str) -> Dict[str, Any]:
        """Compare two scenarios by executing both and showing the delta."""
        result_a = self._execute_scenario(scenario_a)
        result_b = self._execute_scenario(scenario_b)

        savings_a = result_a.get("decision_recommendation", {}).get("total_expected_impact", 0)
        savings_b = result_b.get("decision_recommendation", {}).get("total_expected_impact", 0)

        return {
            "comparison": {
                "scenario_a": {
                    "id": scenario_a,
                    "name": _CATALOG_BY_ID.get(scenario_a, {}).get("name", scenario_a),
                    "total_savings": savings_a,
                    "confidence": result_a.get("decision_recommendation", {}).get("overall_confidence", 0),
                },
                "scenario_b": {
                    "id": scenario_b,
                    "name": _CATALOG_BY_ID.get(scenario_b, {}).get("name", scenario_b),
                    "total_savings": savings_b,
                    "confidence": result_b.get("decision_recommendation", {}).get("overall_confidence", 0),
                },
                "delta": round(savings_a - savings_b, 2),
                "recommendation": scenario_a if savings_a >= savings_b else scenario_b,
                "rationale": (
                    f"{'Scenario A' if savings_a >= savings_b else 'Scenario B'} yields "
                    f"${abs(savings_a - savings_b):,.0f} more in estimated savings."
                ),
            },
        }

    # ------------------------------------------------------------------
    # Scenario Execution
    # ------------------------------------------------------------------

    def _execute_scenario(
        self,
        scenario_id: str,
        site_id: str = "default",
        parameters: Optional[Dict[str, Any]] = None,
        risk_appetite: str = "balanced",
    ) -> Dict[str, Any]:
        """Execute a PdM scenario against real fleet data via the KPI orchestrator."""
        scenario = _CATALOG_BY_ID.get(scenario_id)
        if not scenario:
            return {"success": False, "error": f"Unknown scenario: {scenario_id}"}

        parameters = parameters or {}
        import time
        start = time.time()

        # Attempt real KPI computation, scoped to required KPI crews when possible.
        dashboard_result: Dict[str, Any] = {}
        total_savings = 0.0
        avg_confidence = 0.0
        kpi_count = 0
        normalized_required_kpis: List[str] = []
        try:
            from predictive_maintenance.api.routes.kpi_fleet_routes import compute_dashboard_data

            required_crews = list(scenario.get("required_crews", []) or [])
            normalized_required_kpis = [
                _CREW_TO_KPI_ALIASES.get(name, name) for name in required_crews
            ]

            # Build scenario parameter overrides used by OrchestratorCrew.
            scenario_params = dict(parameters)
            if risk_appetite == "conservative":
                scenario_params.setdefault("risk_multiplier", 0.90)
                scenario_params.setdefault("cost_multiplier", 0.85)
            elif risk_appetite == "aggressive":
                scenario_params.setdefault("risk_multiplier", 1.20)
                scenario_params.setdefault("cost_multiplier", 1.15)

            dashboard_result = compute_dashboard_data(
                site_id=site_id,
                required_kpis=normalized_required_kpis or None,
                run_scenarios=True,
                custom_scenario_params=scenario_params or None,
            )
            executive_summary = dashboard_result.get("executive_summary", {}) or {}
            total_savings = float(executive_summary.get("total_savings_medium", 0.0) or 0.0)
            avg_confidence = float(executive_summary.get("avg_confidence", 0.0) or 0.0)
            kpi_count = int(executive_summary.get("kpi_count", 0) or 0)
            self._index_kpi_dashboard(site_id=site_id, dashboard=dashboard_result)
        except Exception as e:
            logger.warning("Scenario KPI computation failed, using defaults: %s", e)

        crews_executed = normalized_required_kpis or list(scenario.get("required_crews", []) or [])
        result = {
            "success": True,
            "scenario_id": scenario_id,
            "site_id": site_id,
            "session_id": str(uuid.uuid4())[:8],
            "decision_recommendation": {
                "recommendation_id": str(uuid.uuid4()),
                "scenario_id": scenario_id,
                "executive_summary": (
                    f"Scenario '{scenario['name']}' executed with {risk_appetite} risk appetite. "
                    f"Analyzed {kpi_count} KPI dimensions across fleet. "
                    f"Estimated annual savings: ${total_savings:,.0f}."
                ),
                "recommended_actions": [
                    {"action": "implement_pdm", "priority": 1, "impact": "high",
                     "description": f"Execute {scenario['name']} program"},
                    {"action": "monitor_kpis", "priority": 2, "impact": "medium",
                     "description": "Track KPI trends over next 30 days"},
                ],
                "total_expected_impact": round(total_savings, 2),
                "overall_confidence": round(avg_confidence, 3),
                "risk_assessment": f"{risk_appetite.upper()} — {'Within acceptable bounds' if avg_confidence >= 0.5 else 'Low confidence — more data needed'}",
                "kpi_count": kpi_count,
            },
            "crews_executed": crews_executed,
            "execution_time_ms": int((time.time() - start) * 1000),
            "parameters": parameters,
            "risk_appetite": risk_appetite,
            "warnings": [] if avg_confidence >= 0.5 else ["Low confidence — results may improve with more telemetry data"],
        }

        if dashboard_result:
            result["scorecards"] = (dashboard_result.get("scorecards", []) or [])[:5]
            if dashboard_result.get("scenario_comparison"):
                result["scenario_comparison"] = dashboard_result.get("scenario_comparison")

        # Index result into RAG
        self._index_scenario_result(result)
        return result

    def _index_scenario_result(self, result: Dict[str, Any]):
        """Index a scenario execution result into the RAG store."""
        scenario_id = result.get("scenario_id", "unknown")
        content_parts = [
            f"Scenario {scenario_id} executed.",
            f"Success: {result.get('success', False)}",
        ]
        dr = result.get("decision_recommendation", {})
        if dr:
            content_parts.append(f"Summary: {dr.get('executive_summary', '')}")
            content_parts.append(f"Impact: ${dr.get('total_expected_impact', 0):,.0f}")
            content_parts.append(f"Confidence: {dr.get('overall_confidence', 0):.0%}")
        content_parts.append(f"Crews: {', '.join(result.get('crews_executed', []))}")
        if result.get("warnings"):
            content_parts.append(f"Warnings: {'; '.join(result['warnings'])}")

        self.rag.index_document(
            doc_type="scenario_result",
            content="\n".join(content_parts),
            metadata={
                "scenario_id": scenario_id,
                "success": result.get("success", False),
                "session_id": result.get("session_id", ""),
                "execution_time_ms": result.get("execution_time_ms", 0),
            },
        )

    def _index_kpi_dashboard(self, site_id: str, dashboard: Dict[str, Any]):
        """Index KPI dashboard summary + scorecards into the advisor RAG store."""
        if not isinstance(dashboard, dict):
            return

        executive = dashboard.get("executive_summary", {}) or {}
        summary_parts = [
            f"Site: {site_id}",
            f"Total savings (medium): ${float(executive.get('total_savings_medium', 0) or 0):,.0f}",
            f"Total savings (low): ${float(executive.get('total_savings_low', 0) or 0):,.0f}",
            f"Total savings (high): ${float(executive.get('total_savings_high', 0) or 0):,.0f}",
            f"KPI count: {int(executive.get('kpi_count', 0) or 0)}",
            f"Approved KPIs: {int(executive.get('approved_kpis', 0) or 0)}",
            f"Average confidence: {float(executive.get('avg_confidence', 0) or 0):.0%}",
        ]
        self.rag.index_document(
            doc_type="kpi_result",
            content="\n".join(summary_parts),
            metadata={
                "site_id": site_id,
                "source": "kpi_dashboard",
                "computed_at": dashboard.get("computed_at"),
            },
        )

        for card in (dashboard.get("scorecards", []) or [])[:20]:
            if not isinstance(card, dict):
                continue
            kpi_name = str(card.get("kpi_name", "") or "")
            if not kpi_name:
                continue
            content = "\n".join([
                f"Site: {site_id}",
                f"KPI: {kpi_name}",
                f"Display Name: {card.get('display_name', kpi_name)}",
                f"Savings Medium: ${float(card.get('savings_medium', 0) or 0):,.0f}",
                f"Savings Range: ${float(card.get('savings_low', 0) or 0):,.0f} - ${float(card.get('savings_high', 0) or 0):,.0f}",
                f"Confidence: {float(card.get('confidence', 0) or 0):.0%}",
                f"Status: {card.get('status', 'pending')}",
                f"Narrative: {card.get('narrative', '')}",
            ])
            self.rag.index_document(
                doc_type="kpi_data",
                content=content,
                metadata={
                    "site_id": site_id,
                    "kpi_name": kpi_name,
                    "source": "kpi_dashboard",
                    "computed_at": dashboard.get("computed_at"),
                },
            )

    # ------------------------------------------------------------------
    # Current State
    # ------------------------------------------------------------------

    def _get_current_state(self, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Retrieve current fleet health state from the PdM system."""
        import copy
        state = copy.deepcopy(_DEFAULT_FLEET_STATE)
        state["last_updated"] = datetime.utcnow().isoformat()

        # Try to get real fleet data
        try:
            from predictive_maintenance.api.routes.kpi_fleet_routes import (
                _collect_data_from_db, _collect_health_data,
            )
            sid = site_id or "default"
            asset_data, alert_data, telemetry_summary, _ = _collect_data_from_db(sid)
            health_data = _collect_health_data(sid, asset_data)

            if asset_data or health_data:
                known_health = [h for h in health_data if h.get("health_score") is not None]
                n_known = len(known_health) or 1
                state["fleet_summary"] = {
                    "total_assets": len(asset_data),
                    "total_locations": len(set(a.get("site_id", "default") for a in asset_data)),
                    "avg_health_score": round(sum(h.get("health_score", 0) for h in known_health) / n_known, 1),
                    "degraded_count": sum(1 for h in known_health if (h.get("health_score") or 0) < 60),
                    "critical_count": sum(1 for h in known_health if (h.get("health_score") or 0) < 30),
                    "avg_rul_hours": round(sum(h.get("rul_hours", 0) for h in known_health) / n_known),
                    "open_work_orders": sum(1 for a in alert_data if a.get("status") == "active"),
                    "reactive_wo_pct": round(
                        sum(1 for a in alert_data if a.get("alert_type") in ("actionable", "dispatch"))
                        / max(len(alert_data), 1), 2
                    ),
                }
                state["telemetry_summary"] = telemetry_summary
        except Exception as e:
            logger.debug("Fleet state lookup failed, using defaults: %s", e)

        if self.twin_manager is not None:
            try:
                twin_state = self.twin_manager.get_fleet_state(site_id)
                if twin_state:
                    state.update(twin_state)
            except Exception as exc:
                logger.debug("Twin manager fleet state lookup failed: %s", exc)

        return state

    # ------------------------------------------------------------------
    # RAG Catalog Indexing
    # ------------------------------------------------------------------

    def _index_scenario_catalog(self):
        """Index all scenarios from catalog into RAG store."""
        for scenario in self.catalog:
            content_parts = [
                f"Scenario ID: {scenario['scenario_id']}",
                f"Name: {scenario['name']}",
                f"Category: {scenario['category']}",
                f"Description: {scenario['description']}",
                f"Objective: {scenario.get('objective', '')}",
                f"Tags: {', '.join(scenario.get('tags', []))}",
                f"Required Crews: {', '.join(scenario.get('required_crews', []))}",
                f"Triggers: {', '.join(scenario.get('triggers', []))}",
            ]
            self.rag.index_document(
                doc_type="scenario_catalog",
                content="\n".join(content_parts),
                metadata={"scenario_id": scenario["scenario_id"], "category": scenario["category"]},
                persist=False,
            )

    # ------------------------------------------------------------------
    # Ecosystem Detection
    # ------------------------------------------------------------------

    MAINTENANCE_KEYWORDS = ["energy", "hvac", "refrigerant", "work order", "capex", "uptime", "health", "rul", "fault", "maintenance", "pdm"]
    COMPLIANCE_KEYWORDS = ["food safety", "esg", "carbon", "compliance", "temperature", "excursion", "violation", "epa"]

    def _detect_ecosystem(self, text: str) -> Optional[Ecosystem]:
        lower = text.lower()
        maint_score = sum(1 for kw in self.MAINTENANCE_KEYWORDS if kw in lower)
        comp_score = sum(1 for kw in self.COMPLIANCE_KEYWORDS if kw in lower)
        if maint_score > 0 or comp_score > 0:
            return Ecosystem.AUTO
        return None

    # ------------------------------------------------------------------
    # Scenario Matching (offline)
    # ------------------------------------------------------------------

    def _match_scenario_id(self, message: str) -> Optional[str]:
        """Scan message for known scenario_id or scenario name."""
        lower = message.lower()
        for sid in _CATALOG_BY_ID:
            sid_tokens = {sid, sid.replace("_", " "), sid.replace("_", "-")}
            if any(tok in lower for tok in sid_tokens):
                return sid
        for name, scenario in _CATALOG_BY_NAME.items():
            if name in lower:
                return scenario["scenario_id"]
        return None

    def _infer_scenario_from_intent(self, message: str) -> Optional[str]:
        """Intent-based scenario inference using keyword matching."""
        lower = message.lower()
        for keywords, scenario_id in _INTENT_MAP:
            if any(kw in lower for kw in keywords):
                return scenario_id
        return None

    # ------------------------------------------------------------------
    # Offline Parameter Extraction
    # ------------------------------------------------------------------

    _KNOWN_ASSET_TYPES = ["rtu", "ahu", "chiller", "compressor", "condensing unit", "walk-in", "reach-in", "freezer", "cooler"]

    def _extract_offline_params(self, message: str) -> Dict[str, Any]:
        """Regex-based parameter extraction from natural language."""
        lower = message.lower()
        params: Dict[str, Any] = {}

        # Asset types
        found_types = [t for t in self._KNOWN_ASSET_TYPES if t in lower]
        if found_types:
            params["asset_types"] = found_types

        # Budget / cost extraction
        budget_match = re.search(r"\$?([\d,.]+)\s*(m|k|million|thousand)?", lower)
        if budget_match:
            value = float(budget_match.group(1).replace(",", ""))
            multiplier = budget_match.group(2)
            if multiplier in ("m", "million"):
                value *= 1_000_000
            elif multiplier in ("k", "thousand"):
                value *= 1_000
            if value > 100:
                params["budget_total"] = value

        # Energy cost per kWh
        energy_match = re.search(r"(\d+\.?\d*)\s*(?:cents?|¢)\s*(?:per\s*)?kwh", lower)
        if energy_match:
            params["energy_cost_per_kwh"] = float(energy_match.group(1)) / 100.0

        # Deferral days
        defer_match = re.search(r"defer(?:ral)?\s*(?:for)?\s*(\d+)\s*days?", lower)
        if defer_match:
            params["defer_days"] = int(defer_match.group(1))

        # Asset ID
        asset_match = re.search(r"asset[_\s-]?(\w+[-_]\w+)", lower)
        if asset_match:
            params["asset_id"] = asset_match.group(1)

        # Site ID
        site_match = re.search(r"site(?:[_\s-]?id)?\s*[:=]?\s*([a-z0-9_-]+)", lower)
        if site_match:
            params["site_id"] = site_match.group(1)

        # Percentage
        pct_match = re.search(r"(\d{1,3})%", message)
        if pct_match:
            params["reduction_pct"] = int(pct_match.group(1)) / 100.0

        return params

    # ------------------------------------------------------------------
    # RAG Context Building
    # ------------------------------------------------------------------

    def _build_rag_context(self, query: str) -> Tuple[str, List[RagSearchResult]]:
        """Build RAG context for the query."""
        results = self.rag.search(query, top_k=4)
        if not results:
            return "", []

        lines = ["Retrieved context (use to answer the question):"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. [{r.doc_type}] {r.content[:300]}")

        return "\n".join(lines), results

    # ------------------------------------------------------------------
    # Send Message — Main Pipeline
    # ------------------------------------------------------------------

    def send_message(
        self,
        session_id: str,
        message: str,
        stream: bool = False,
    ) -> AdvisorResponse:
        """Single entry point for all user inputs.

        Pipeline:
        1. Session lookup
        2. Append user message
        3. Pre-execution scenario check
        4. RAG context building
        5. Online/offline branch
        """
        # 1. Session lookup
        session = self.get_session(session_id)
        if session is None:
            return AdvisorResponse(
                message="Session not found. Please create a new session.",
                confidence=0.0,
                agent_source="error",
            )

        # 2. Append user message
        session.add_message(MessageRole.USER, message)
        self._db_append_message(session_id, "user", message)

        # 3. Pre-execution scenario check
        pre_exec_result = None
        scenario_id = self._match_scenario_id(message)
        if scenario_id:
            exec_keywords = ["run", "execute", "simulate", "launch", "start"]
            if any(kw in message.lower() for kw in exec_keywords):
                params = self._extract_offline_params(message)
                pre_exec_result = self._execute_scenario(scenario_id, parameters=params)

        # 4. RAG context building
        rag_context, rag_results = self._build_rag_context(message)
        if pre_exec_result and pre_exec_result.get("success"):
            dr = pre_exec_result.get("decision_recommendation", {})
            rag_context += f"\n\nScenario execution result: {dr.get('executive_summary', '')}"

        # 5. Online/offline branch
        if not self.client.is_available:
            return self._handle_offline_message(session, message, rag_context, rag_results, pre_exec_result)

        return self._handle_online_message(session, message, rag_context, rag_results, pre_exec_result)

    # ------------------------------------------------------------------
    # Online Message Handling
    # ------------------------------------------------------------------

    # ── Context window management ─────────────────────────────────
    # Rough token budget: keep well under the 128k context limit.
    # We reserve ~4k for the response and ~2k for tool definitions.
    _MAX_CONTEXT_TOKENS = 100_000
    _CHARS_PER_TOKEN = 4  # conservative estimate

    @staticmethod
    def _estimate_tokens(messages: List[Dict[str, Any]]) -> int:
        """Rough token estimate: ~4 chars per token."""
        total_chars = sum(len(m.get("content", "") or "") for m in messages)
        return total_chars // 4

    @classmethod
    def _trim_messages_to_window(
        cls, messages: List[Dict[str, Any]], max_tokens: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Trim message history to fit within the token budget.

        Strategy:
        1. Always keep the first system message (prompt).
        2. Always keep the last user message + any trailing tool/assistant.
        3. Drop oldest non-system messages until under budget.
        """
        budget = max_tokens or cls._MAX_CONTEXT_TOKENS
        if cls._estimate_tokens(messages) <= budget:
            return messages

        # Separate system messages (keep all) from conversation messages
        system_msgs = [m for m in messages if m.get("role") == "system"]
        convo_msgs = [m for m in messages if m.get("role") != "system"]

        # Always keep at least the last 4 conversation messages
        min_tail = min(4, len(convo_msgs))
        tail = convo_msgs[-min_tail:] if min_tail else []
        middle = convo_msgs[:-min_tail] if min_tail else convo_msgs

        # Drop from the front of middle until under budget
        while middle and cls._estimate_tokens(system_msgs + middle + tail) > budget:
            middle.pop(0)

        trimmed = system_msgs + middle + tail
        if len(trimmed) < len(messages):
            logger.debug(
                "Context window trimmed: %d → %d messages (~%d tokens)",
                len(messages), len(trimmed), cls._estimate_tokens(trimmed),
            )
        return trimmed

    def _handle_online_message(
        self,
        session: AdvisorSession,
        message: str,
        rag_context: str,
        rag_results: List[RagSearchResult],
        pre_exec_result: Optional[Dict[str, Any]],
    ) -> AdvisorResponse:
        """Handle message via OpenAI chat completion with tool calling."""
        # Build message payload with context window management
        messages = [m.to_openai_dict() for m in session.messages]
        if rag_context:
            messages.append({"role": "system", "content": rag_context})
        messages = self._trim_messages_to_window(messages)

        # Call OpenAI
        response = self.client.chat(messages, use_tools=True)

        if response.finish_reason in ("unavailable", "error"):
            return self._handle_offline_message(session, message, rag_context, rag_results, pre_exec_result)

        # Handle tool calls
        if response.tool_calls:
            return self._handle_tool_calls(session, response, message)

        # Direct response
        content = response.content or "I couldn't generate a response. Please try rephrasing your question."
        session.add_message(MessageRole.ASSISTANT, content)
        self._db_append_message(session.session_id, "assistant", content)

        ecosystem = self._detect_ecosystem(message)
        scenario_ids = []
        if pre_exec_result and pre_exec_result.get("scenario_id"):
            scenario_ids.append(pre_exec_result["scenario_id"])

        return AdvisorResponse(
            message=content,
            ecosystem=ecosystem,
            scenario_ids=scenario_ids,
            data=pre_exec_result,
            confidence=0.85,
            agent_source="openai",
        )

    def _handle_tool_calls(
        self,
        session: AdvisorSession,
        response: ChatResponse,
        original_message: str,
    ) -> AdvisorResponse:
        """Execute tool calls and get follow-up synthesis."""
        data: Dict[str, Any] = {}
        scenario_ids: List[str] = []
        detected_ecosystem = None

        # Record assistant message with tool_calls
        session.add_message(
            MessageRole.ASSISTANT, response.content or "",
            tool_calls=response.tool_calls,
        )

        for tc in response.tool_calls:
            func_name = tc["function"]["name"]
            result = self.client.execute_tool_call(tc)

            # Serialize result
            result_str = json.dumps(result) if not isinstance(result, str) else result

            session.add_message(
                MessageRole.TOOL, result_str,
                name=func_name,
                tool_call_id=tc["id"],
            )

            data[func_name] = result

            # Detect ecosystem from tool name
            if func_name.startswith("dp_"):
                detected_ecosystem = Ecosystem.DEMAND_PROCUREMENT
            elif func_name.startswith(("get_rmn", "execute_rmn", "search_knowledge", "recommend_scenario")):
                detected_ecosystem = Ecosystem.RMN

            # Collect scenario IDs
            if isinstance(result, dict):
                for key in ("scenario_id", "recommended_scenario_id"):
                    if key in result:
                        scenario_ids.append(result[key])

        # Follow-up completion to synthesize results (with context window management)
        follow_up_messages = self._trim_messages_to_window(
            [m.to_openai_dict() for m in session.messages]
        )
        final_response = self.client.chat(follow_up_messages, use_tools=False)

        content = final_response.content or "Tool execution completed. Please see the structured data."
        session.add_message(MessageRole.ASSISTANT, content)
        self._db_append_message(session.session_id, "assistant", content)

        return AdvisorResponse(
            message=content,
            ecosystem=detected_ecosystem or self._detect_ecosystem(original_message),
            scenario_ids=scenario_ids,
            data=data,
            confidence=0.9,
            agent_source="tool_chain",
        )

    # ------------------------------------------------------------------
    # Offline Message Handling
    # ------------------------------------------------------------------

    def _handle_offline_message(
        self,
        session: AdvisorSession,
        message: str,
        rag_context: str,
        rag_results: List[RagSearchResult],
        pre_exec_result: Optional[Dict[str, Any]],
    ) -> AdvisorResponse:
        """Conversational offline pipeline — synthesizes data into helpful explanations."""
        lower = message.lower()

        # If pre-execution already ran (from step 3 of pipeline), explain the results
        if pre_exec_result and pre_exec_result.get("success"):
            content = self._synthesize_scenario_result(pre_exec_result)
            session.add_message(MessageRole.ASSISTANT, content)
            self._db_append_message(session.session_id, "assistant", content)
            return AdvisorResponse(
                message=content,
                ecosystem=Ecosystem.AUTO,
                scenario_ids=[pre_exec_result.get("scenario_id", "")],
                data=pre_exec_result,
                confidence=0.7,
                agent_source="scenario_executor",
            )

        # Step 1 & 2: Scenario ID or intent match
        scenario_id = self._match_scenario_id(message) or self._infer_scenario_from_intent(message)
        if scenario_id:
            params = self._extract_offline_params(message)
            result = self._execute_scenario(scenario_id, parameters=params)
            content = self._synthesize_scenario_result(result, scenario_id)
            session.add_message(MessageRole.ASSISTANT, content)
            self._db_append_message(session.session_id, "assistant", content)
            return AdvisorResponse(
                message=content,
                ecosystem=Ecosystem.AUTO,
                scenario_ids=[scenario_id],
                data=result,
                confidence=0.7,
                agent_source="scenario_executor",
            )

        # Step 3: Current-state query detection
        state_keywords = ["current", "fleet", "state", "health", "overview", "how many", "status", "summary"]
        if any(kw in lower for kw in state_keywords):
            state = self._get_current_state()
            content = self._synthesize_fleet_state(state, message)
            session.add_message(MessageRole.ASSISTANT, content)
            self._db_append_message(session.session_id, "assistant", content)
            return AdvisorResponse(
                message=content,
                ecosystem=self._detect_ecosystem(message),
                data=state,
                confidence=0.8,
                agent_source="state_lookup",
            )

        # Step 4: RAG-informed conversational response
        if rag_results:
            content = self._synthesize_rag_response(message, rag_results)
            session.add_message(MessageRole.ASSISTANT, content)
            self._db_append_message(session.session_id, "assistant", content)
            return AdvisorResponse(
                message=content,
                ecosystem=self._detect_ecosystem(message),
                confidence=0.6,
                agent_source="rag_synthesis",
            )

        # Step 5: Conversational guidance fallback
        content = self._build_conversational_guidance(message)
        session.add_message(MessageRole.ASSISTANT, content)
        self._db_append_message(session.session_id, "assistant", content)
        return AdvisorResponse(
            message=content,
            ecosystem=self._detect_ecosystem(message),
            confidence=0.4,
            agent_source="offline",
        )

    # ------------------------------------------------------------------
    # Offline Response Synthesis Helpers
    # ------------------------------------------------------------------

    def _synthesize_scenario_result(
        self, result: Dict[str, Any], scenario_id: str = None,
    ) -> str:
        """Turn a scenario execution result into a conversational explanation."""
        sid = scenario_id or result.get("scenario_id", "unknown")
        scenario = _CATALOG_BY_ID.get(sid, {})
        name = scenario.get("name", sid.replace("_", " ").title())
        dr = result.get("decision_recommendation", {})
        summary = dr.get("executive_summary", "")
        savings = dr.get("total_expected_impact", 0)
        confidence = dr.get("overall_confidence", 0)
        crews = result.get("crews_executed", [])

        parts = [f"I ran the **{name}** analysis for you. Here's what I found:\n"]

        if summary:
            parts.append(f"{summary}\n")

        if savings > 0:
            conf_label = "high" if confidence >= 0.7 else "moderate" if confidence >= 0.4 else "low"
            parts.append(
                f"The estimated annual savings are **${savings:,.0f}** "
                f"with **{conf_label} confidence** ({confidence:.0%}). "
            )
            if confidence < 0.5:
                parts.append(
                    "The confidence is on the lower side — uploading more operational data "
                    "(telemetry, work orders, energy bills) would help sharpen this estimate."
                )
        elif not summary:
            parts.append("The analysis completed but didn't find significant savings opportunity with the current data.")

        # Add contextual next steps
        parts.append("\n**What you can do next:**")
        if sid in ("energy_reduction", "condenser_fouling_impact"):
            parts.append("- Review the energy baseline assumptions on the KPI Dashboard")
            parts.append("- Upload recent utility bills via Data Upload to improve accuracy")
        elif sid in ("capex_planning", "replace_vs_repair", "budget_sensitivity"):
            parts.append("- Check the CapEx Planning tab for the full asset replacement schedule")
            parts.append("- Try adjusting the budget to see how it affects the plan")
        elif sid in ("work_order_optimization", "pm_interval_optimization"):
            parts.append("- Upload work order history to improve the reactive-to-planned ratio calculation")
            parts.append("- Review the Work Order Reduction KPI on the dashboard")
        elif sid in ("critical_asset_triage", "fleet_health_assessment"):
            parts.append("- Focus on the critical assets first — ask me about a specific asset ID for details")
            parts.append("- Consider running the CapEx planning scenario for replacement prioritization")
        else:
            parts.append("- Ask me to dive deeper into any specific finding")
            parts.append("- Try running a related scenario for comparison")

        return "\n".join(parts)

    def _synthesize_fleet_state(self, state: Dict[str, Any], question: str) -> str:
        """Turn fleet state data into a conversational health briefing."""
        fs = state.get("fleet_summary", {})
        total = fs.get("total_assets", 0)
        health = fs.get("avg_health_score", 0)
        degraded = fs.get("degraded_count", 0)
        critical = fs.get("critical_count", 0)
        rul = fs.get("avg_rul_hours", 0)
        open_wo = fs.get("open_work_orders", 0)
        reactive_pct = fs.get("reactive_wo_pct", 0)

        parts = ["Here's a snapshot of your fleet's current health:\n"]

        # Health assessment
        if health >= 80:
            parts.append(f"Overall your fleet is in **good shape** with an average health score of **{health:.0f}/100** across {total} assets.")
        elif health >= 60:
            parts.append(f"Your fleet health is **fair** at **{health:.0f}/100** across {total} assets — there's room for improvement.")
        else:
            parts.append(f"Your fleet health needs attention — the average score is **{health:.0f}/100** across {total} assets, which is below the typical target of 70+.")

        # Critical assets
        if critical > 0:
            parts.append(f"\n**{critical} asset(s) are in critical condition** and should be prioritized for inspection or replacement. ")
            if degraded > critical:
                parts.append(f"An additional {degraded - critical} assets are degraded but not yet critical.")
        elif degraded > 0:
            parts.append(f"\nNo assets are critical right now, but **{degraded} are degraded** and worth monitoring closely.")
        else:
            parts.append("\nNo assets are currently in critical or degraded condition — that's great.")

        # RUL
        if rul > 0:
            rul_months = rul / (24 * 30)  # rough conversion
            parts.append(f"\nAverage remaining useful life is about **{rul_months:.0f} months** ({rul:,.0f} hours).")

        # Work orders
        if open_wo > 0 or reactive_pct > 0:
            parts.append(f"\nYou have **{open_wo} open work orders**, with **{reactive_pct:.0%} being reactive** (unplanned). ")
            if reactive_pct > 0.4:
                parts.append("That reactive rate is high — predictive maintenance could help shift more work orders to planned.")
            elif reactive_pct > 0.2:
                parts.append("That's a moderate reactive rate. There's opportunity to improve with better predictive coverage.")
            else:
                parts.append("That's a healthy ratio — your preventive maintenance program is working well.")

        parts.append("\nWould you like me to dig into any specific area — energy, CapEx planning, critical assets, or maintenance optimization?")
        return "\n".join(parts)

    def _synthesize_rag_response(self, question: str, results: List[RagSearchResult]) -> str:
        """Synthesize RAG results into a conversational response."""
        # Group results by type for organized response
        scenarios = [r for r in results if r.doc_type == "scenario_catalog"]
        kpi_results = [r for r in results if r.doc_type in ("kpi_result", "kpi_data")]
        docs = [r for r in results if r.doc_type not in ("scenario_catalog", "kpi_result", "kpi_data")]

        parts = []

        if scenarios:
            # Extract scenario names and descriptions
            relevant = []
            for r in scenarios:
                # Parse out the scenario name from content
                content = r.content
                name_match = re.search(r"Name:\s*(.+?)(?:\n|$)", content)
                desc_match = re.search(r"Description:\s*(.+?)(?:\n|$)", content)
                name = name_match.group(1).strip() if name_match else ""
                desc = desc_match.group(1).strip() if desc_match else content[:150]
                if name:
                    relevant.append((name, desc))

            if relevant:
                parts.append("Based on your question, here are the most relevant capabilities I can help with:\n")
                for name, desc in relevant[:3]:
                    parts.append(f"- **{name}** — {desc}")
                parts.append("\nWould you like me to run any of these analyses? Just tell me which one interests you, "
                           "or describe what you're trying to accomplish and I'll recommend the best approach.")

        if kpi_results:
            parts.append("\nI also found some relevant KPI data that may help answer your question. "
                        "You can view the full KPI Dashboard for detailed savings estimates and confidence levels.")

        if docs and not scenarios and not kpi_results:
            # General knowledge results — summarize conversationally
            parts.append("Here's what I found that's relevant to your question:\n")
            for r in docs[:3]:
                # Clean up the content for readability
                summary = r.content[:250].strip()
                if summary:
                    parts.append(f"{summary}")

        if not parts:
            return self._build_conversational_guidance(question)

        return "\n".join(parts)

    def _build_conversational_guidance(self, question: str) -> str:
        """Generate a helpful conversational response when no specific data matches."""
        lower = question.lower()

        # Try to understand what the user is asking about and guide them
        if any(w in lower for w in ["help", "what can", "how do", "getting started"]):
            return (
                "I'm here to help you understand and optimize your HVAC/R maintenance operations. "
                "Here are some things you can ask me about:\n\n"
                "- **\"How is my fleet doing?\"** — I'll give you a health overview with key metrics\n"
                "- **\"Where can I save the most money?\"** — I'll analyze your top savings opportunities\n"
                "- **\"Which assets need attention?\"** — I'll identify your most at-risk equipment\n"
                "- **\"Should I replace or repair asset X?\"** — I'll run an NPV analysis\n"
                "- **\"What's my energy savings potential?\"** — I'll estimate energy optimization impact\n"
                "- **\"Plan my CapEx budget\"** — I'll prioritize replacements within your budget\n\n"
                "What would you like to explore?"
            )

        if any(w in lower for w in ["save", "saving", "cost", "reduce", "cut", "budget", "roi"]):
            return (
                "To help you find savings opportunities, I can analyze several areas:\n\n"
                "- **Energy optimization** — reducing energy waste through PdM-driven HVAC/R tuning\n"
                "- **Work order reduction** — shifting reactive maintenance to planned\n"
                "- **CapEx planning** — timing replacements for maximum NPV\n"
                "- **Refrigerant management** — catching leaks early to avoid costly charges\n"
                "- **Service bureau reduction** — handling more maintenance in-house\n\n"
                "Which area is most important to you right now? Or I can run a full analysis across all of them."
            )

        if any(w in lower for w in ["asset", "equipment", "unit", "rtu", "ahu", "chiller"]):
            return (
                "I can help with specific asset analysis. Here's what I can tell you about your equipment:\n\n"
                "- **Health score and remaining useful life** for any specific asset\n"
                "- **Critical asset triage** — which units need immediate attention\n"
                "- **Replace vs repair analysis** — NPV comparison for aging equipment\n"
                "- **Failure mode analysis** — common failure patterns across your fleet\n\n"
                "If you have a specific asset ID, share it and I'll pull up the details. "
                "Otherwise, I can run a fleet-wide assessment."
            )

        # Generic conversational fallback
        return (
            "I'd like to help with that. Could you tell me a bit more about what you're looking for? "
            "For example:\n\n"
            "- Are you trying to **understand your fleet's current condition**?\n"
            "- Looking for **savings opportunities** in energy, maintenance, or CapEx?\n"
            "- Need to **prioritize which assets** to repair or replace?\n"
            "- Want to **run a what-if scenario** (e.g., \"what if we defer maintenance for 60 days\")?\n\n"
            "Just describe what you're trying to accomplish and I'll point you in the right direction."
        )

    # ------------------------------------------------------------------
    # DB Persistence Helpers (write-through)
    # ------------------------------------------------------------------

    def _hydrate_sessions_from_db(self):
        """Restore active sessions from PostgreSQL on startup."""
        try:
            from ...persistence.advisor_repository import AdvisorRepository
            if not AdvisorRepository.is_available():
                return
            rows = AdvisorRepository.load_all_active_sessions()
            for row in rows:
                eco = Ecosystem(row["ecosystem"]) if row["ecosystem"] in [e.value for e in Ecosystem] else Ecosystem.AUTO
                session = AdvisorSession(
                    session_id=row["session_id"],
                    created_at=row.get("created_at", datetime.utcnow()),
                    ecosystem=eco,
                    context=row.get("context", {}),
                )
                for m in row.get("messages", []):
                    role = MessageRole(m["role"]) if m["role"] in [r.value for r in MessageRole] else MessageRole.USER
                    session.messages.append(ChatMessage(role=role, content=m["content"]))
                self.sessions[row["session_id"]] = session
            if rows:
                logger.info("Hydrated %d advisor sessions from DB", len(rows))
        except Exception as e:
            logger.debug("Session hydration skipped: %s", e)

    def _db_create_session(self, session_id: str, ecosystem: str):
        try:
            from ...persistence.advisor_repository import AdvisorRepository
            AdvisorRepository.create_session(session_id=session_id, ecosystem=ecosystem)
        except Exception as e:
            logger.debug("DB create_session failed: %s", e)

    def _db_delete_session(self, session_id: str):
        try:
            from ...persistence.advisor_repository import AdvisorRepository
            AdvisorRepository.delete_session(session_id)
        except Exception as e:
            logger.debug("DB delete_session failed: %s", e)

    def _db_append_message(self, session_id: str, role: str, content: str, metadata: dict = None):
        try:
            from ...persistence.advisor_repository import AdvisorRepository
            AdvisorRepository.append_message(session_id=session_id, role=role, content=content, metadata=metadata)
        except Exception as e:
            logger.debug("DB append_message failed: %s", e)

    def _record_assistant_response(self, session_id: str, content: str):
        """Record an assistant response in both session history and DB."""
        session = self.get_session(session_id)
        if session:
            session.add_message(MessageRole.ASSISTANT, content)
        self._db_append_message(session_id, "assistant", content)

    def _build_messages(self, session_id: str, user_message: str) -> List[Dict[str, Any]]:
        """Build OpenAI-format messages for streaming. Used by SSE endpoint."""
        session = self.get_session(session_id)
        if session is None:
            return [{"role": "user", "content": user_message}]
        messages = [m.to_openai_dict() for m in session.messages]
        # Append the new user message (not yet in history for streaming)
        messages.append({"role": "user", "content": user_message})
        return messages

    def _build_guidance_message(self) -> str:
        """Build a help menu listing available scenarios and example prompts."""
        lines = [
            "I'm currently operating in offline mode. Here's what I can help with:\n",
            "**Available Scenarios:**",
        ]
        categories = {}
        for s in self.catalog:
            cat = s["category"]
            categories.setdefault(cat, []).append(s)

        for cat, scenarios in categories.items():
            lines.append(f"\n**{cat.replace('_', ' ').title()}:**")
            for s in scenarios:
                lines.append(f"  - {s['name']} (`{s['scenario_id']}`)")

        lines.extend([
            "\n**Example prompts:**",
            '- "Show fleet health summary"',
            '- "Run energy reduction analysis"',
            '- "What if we defer maintenance for 60 days?"',
            '- "Compare capex_planning vs replace_vs_repair"',
            '- "Which assets are critical and need immediate attention?"',
            '- "Run the CapEx planning scenario with a $1M budget"',
        ])
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_advisor(
    rag: Optional[RagStore] = None,
    client: Optional[OpenAIClient] = None,
    twin_manager: Optional[Any] = None,
) -> UnifiedScenarioAdvisor:
    """Factory function to create a configured UnifiedScenarioAdvisor."""
    return UnifiedScenarioAdvisor(rag=rag, client=client, twin_manager=twin_manager)


_shared_advisor: Optional[UnifiedScenarioAdvisor] = None


def get_shared_advisor() -> UnifiedScenarioAdvisor:
    """Return a process-level shared advisor instance."""
    global _shared_advisor
    if _shared_advisor is None:
        _shared_advisor = create_advisor()
    return _shared_advisor
