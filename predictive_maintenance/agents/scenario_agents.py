"""Scenario agent interfaces for maintenance-focused planning.

Each agent evaluates a maintenance scenario from a different perspective:
- BudgetScenarioAgent: CapEx/OpEx cost analysis
- RiskScenarioAgent: Failure probability and safety risk
- PaybackScenarioAgent: ROI and payback period analysis

All agents are CrewAI-compliant with @tool functions for LLM reasoning.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional

from shared.agents.crewai_base import (
    Agent, Task, Crew, Process, CREWAI_AVAILABLE,
    CrewAIAgentConfig, AgentCategory, AgentRole,
)

logger = logging.getLogger(__name__)

# CrewAI @tool decorator with fallback
try:
    from crewai.tools import tool as crewai_tool
except ImportError:
    def crewai_tool(name_or_func=None):
        """Fallback @tool decorator when CrewAI is unavailable."""
        def decorator(func):
            func.tool_name = name_or_func if isinstance(name_or_func, str) else func.__name__
            return func
        if callable(name_or_func):
            return decorator(name_or_func)
        return decorator


@dataclass
class ScenarioContext:
    persona_id: str
    persona_prompt: str
    user_message: str
    scope: str  # asset, site, fleet
    risk_level: str  # low, medium, high, critical
    payback_timeline: str  # months
    maintenance_budget: str = ""  # annual maintenance budget
    twin_state: Dict[str, Any] = field(default_factory=dict)
    # Backward compatibility alias
    marketing_budget: str = ""

    def __post_init__(self):
        if not self.maintenance_budget and self.marketing_budget:
            self.maintenance_budget = self.marketing_budget
        elif not self.marketing_budget and self.maintenance_budget:
            self.marketing_budget = self.maintenance_budget


@dataclass
class ScenarioAgentResult:
    agent_id: str
    title: str
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


# =============================================================================
# @tool Functions for Scenario Agents
# =============================================================================

@crewai_tool("analyze_budget_impact")
def analyze_budget_impact(
    scope: str, risk_level: str, maintenance_budget: str,
    health_score: float = -1, rul_hours: float = -1, instruction: str = ""
) -> dict:
    """Analyze maintenance scenario from cost/budget perspective — CapEx, OpEx, NPV.
    Returns budget assessment with health context and cost recommendations."""
    health_note = f" Health score: {health_score:.0f}." if health_score >= 0 else ""
    rul_note = f" RUL: {rul_hours:.0f}h." if rul_hours >= 0 else ""

    # Budget threshold analysis
    urgency = "low"
    if health_score >= 0 and health_score < 40:
        urgency = "high"
    elif health_score >= 0 and health_score < 70:
        urgency = "medium"

    return {
        "perspective": "budget",
        "scope": scope,
        "risk_level": risk_level,
        "maintenance_budget": maintenance_budget,
        "urgency": urgency,
        "summary": (
            f"Budget lens ({scope}): maintenance budget {maintenance_budget}. "
            f"Risk level: {risk_level}.{health_note}{rul_note}"
        ),
        "details": {
            "health_score": health_score if health_score >= 0 else None,
            "rul_hours": rul_hours if rul_hours >= 0 else None,
        },
    }


@crewai_tool("analyze_risk_exposure")
def analyze_risk_exposure(
    scope: str, risk_level: str, persona_id: str = "",
    fault_probability: float = -1, degradation_index: float = -1,
    instruction: str = ""
) -> dict:
    """Analyze failure risk exposure — probability, severity, cascading impact.
    Returns risk assessment with fault probability and degradation context."""
    fault_note = f" Fault probability: {fault_probability:.1%}." if fault_probability >= 0 else ""
    deg_note = f" Degradation: {degradation_index:.1%}." if degradation_index >= 0 else ""

    # Risk categorization
    risk_category = "acceptable"
    if fault_probability >= 0.8:
        risk_category = "critical"
    elif fault_probability >= 0.5:
        risk_category = "elevated"
    elif fault_probability >= 0.2:
        risk_category = "moderate"

    return {
        "perspective": "risk",
        "scope": scope,
        "risk_level": risk_level,
        "risk_category": risk_category,
        "summary": (
            f"Risk lens ({scope}): risk level {risk_level}. "
            f"Persona: {persona_id}.{fault_note}{deg_note}"
        ),
        "details": {
            "fault_probability": fault_probability if fault_probability >= 0 else None,
            "degradation_index": degradation_index if degradation_index >= 0 else None,
        },
    }


@crewai_tool("analyze_payback_period")
def analyze_payback_period(
    scope: str, payback_timeline: str, persona_id: str = "",
    energy_penalty_pct: float = -1, estimated_downtime_cost: float = -1,
    instruction: str = ""
) -> dict:
    """Analyze ROI/payback — break-even timeline, cumulative savings, confidence.
    Returns payback assessment with energy penalty and downtime cost context."""
    energy_note = f" Energy penalty: {energy_penalty_pct:.1f}%." if energy_penalty_pct >= 0 else ""
    cost_note = f" Est. downtime cost: ${estimated_downtime_cost:,.0f}." if estimated_downtime_cost >= 0 else ""

    # Simple payback viability
    viable = "unknown"
    if estimated_downtime_cost > 0 and energy_penalty_pct > 0:
        viable = "likely" if estimated_downtime_cost > 5000 or energy_penalty_pct > 5 else "marginal"

    return {
        "perspective": "payback",
        "scope": scope,
        "payback_timeline": payback_timeline,
        "viability": viable,
        "summary": (
            f"Payback lens ({scope}): target {payback_timeline}. "
            f"Persona: {persona_id}.{energy_note}{cost_note}"
        ),
        "details": {
            "energy_penalty_pct": energy_penalty_pct if energy_penalty_pct >= 0 else None,
            "downtime_cost": estimated_downtime_cost if estimated_downtime_cost >= 0 else None,
        },
    }


# =============================================================================
# CrewAI Agent Factories (lazy instantiation to avoid module-load errors)
# =============================================================================

_BUDGET_AGENT_CONFIG = dict(
    role="Budget Analyst",
    goal="Analyze maintenance scenarios from a cost/budget perspective, evaluating CapEx, OpEx, and NPV impacts.",
    backstory="You are a financial analyst specializing in maintenance budgeting. "
              "You evaluate scenarios through the lens of total cost of ownership, "
              "comparing repair-vs-replace economics and budget utilization rates.",
)

_RISK_AGENT_CONFIG = dict(
    role="Risk Analyst",
    goal="Analyze maintenance scenarios from a failure risk perspective, evaluating probability, severity, and cascading impact.",
    backstory="You are a reliability engineer who assesses failure modes and their consequences. "
              "You quantify risk in terms of safety, operational continuity, and regulatory compliance.",
)

_PAYBACK_AGENT_CONFIG = dict(
    role="ROI Analyst",
    goal="Analyze maintenance scenarios from an ROI/payback perspective, evaluating break-even timelines and cumulative savings.",
    backstory="You are an investment analyst who evaluates maintenance spending as capital allocation. "
              "You model payback periods, IRR, and cumulative savings to guide investment decisions.",
)


def _make_agent(config: dict, tools: list):
    """Create a CrewAI Agent with graceful fallback."""
    try:
        return Agent(**config, tools=tools, verbose=True)
    except Exception:
        try:
            return Agent(**config, tools=tools)
        except Exception:
            return Agent(**config)


def get_budget_scenario_agent():
    """Lazy factory for the budget scenario CrewAI agent."""
    return _make_agent(_BUDGET_AGENT_CONFIG, [analyze_budget_impact])


def get_risk_scenario_agent():
    """Lazy factory for the risk scenario CrewAI agent."""
    return _make_agent(_RISK_AGENT_CONFIG, [analyze_risk_exposure])


def get_payback_scenario_agent():
    """Lazy factory for the payback scenario CrewAI agent."""
    return _make_agent(_PAYBACK_AGENT_CONFIG, [analyze_payback_period])




# =============================================================================
# Backward-Compatible Class Interface
# =============================================================================

class ScenarioAgent:
    """Base interface for scenario agents. Now wraps CrewAI agents."""

    def __init__(self, agent_id: str, title: str):
        self.agent_id = agent_id
        self.title = title

    def analyze(self, context: ScenarioContext, instruction: str) -> ScenarioAgentResult:
        raise NotImplementedError


class BudgetScenarioAgent(ScenarioAgent):
    """Analyzes maintenance scenarios from a cost/budget perspective."""

    crewai_tools = [analyze_budget_impact]

    def get_crewai_agent(self):
        return get_budget_scenario_agent()

    def analyze(self, context: ScenarioContext, instruction: str) -> ScenarioAgentResult:
        health = context.twin_state.get("health", {})
        result = analyze_budget_impact(
            scope=context.scope,
            risk_level=context.risk_level,
            maintenance_budget=context.maintenance_budget,
            health_score=health.get("health_score", -1),
            rul_hours=health.get("rul_hours", -1),
            instruction=instruction,
        )
        return ScenarioAgentResult(
            agent_id=self.agent_id,
            title=self.title,
            summary=result["summary"],
            details=result["details"],
        )


class RiskScenarioAgent(ScenarioAgent):
    """Analyzes maintenance scenarios from a failure risk perspective."""

    crewai_tools = [analyze_risk_exposure]

    def get_crewai_agent(self):
        return get_risk_scenario_agent()

    def analyze(self, context: ScenarioContext, instruction: str) -> ScenarioAgentResult:
        health = context.twin_state.get("health", {})
        result = analyze_risk_exposure(
            scope=context.scope,
            risk_level=context.risk_level,
            persona_id=context.persona_id,
            fault_probability=health.get("fault_probability", -1),
            degradation_index=health.get("degradation_index", -1),
            instruction=instruction,
        )
        return ScenarioAgentResult(
            agent_id=self.agent_id,
            title=self.title,
            summary=result["summary"],
            details=result["details"],
        )


class PaybackScenarioAgent(ScenarioAgent):
    """Analyzes maintenance scenarios from an ROI/payback perspective."""

    crewai_tools = [analyze_payback_period]

    def get_crewai_agent(self):
        return get_payback_scenario_agent()

    def analyze(self, context: ScenarioContext, instruction: str) -> ScenarioAgentResult:
        health = context.twin_state.get("health", {})
        result = analyze_payback_period(
            scope=context.scope,
            payback_timeline=context.payback_timeline,
            persona_id=context.persona_id,
            energy_penalty_pct=health.get("energy_penalty_pct", -1),
            estimated_downtime_cost=health.get("estimated_downtime_cost", -1),
            instruction=instruction,
        )
        return ScenarioAgentResult(
            agent_id=self.agent_id,
            title=self.title,
            summary=result["summary"],
            details=result["details"],
        )
