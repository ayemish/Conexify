"""Scenario agent interfaces for maintenance-focused planning.

Each agent evaluates a maintenance scenario from a different perspective:
- BudgetScenarioAgent: CapEx/OpEx cost analysis
- RiskScenarioAgent: Failure probability and safety risk
- PaybackScenarioAgent: ROI and payback period analysis
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List


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


class ScenarioAgent:
    """Base interface for scenario agents."""

    def __init__(self, agent_id: str, title: str):
        self.agent_id = agent_id
        self.title = title

    def analyze(self, context: ScenarioContext, instruction: str) -> ScenarioAgentResult:
        raise NotImplementedError


class BudgetScenarioAgent(ScenarioAgent):
    """Analyzes maintenance scenarios from a cost/budget perspective."""

    def analyze(self, context: ScenarioContext, instruction: str) -> ScenarioAgentResult:
        health = context.twin_state.get("health", {})
        health_score = health.get("health_score")
        rul_hours = health.get("rul_hours")

        health_note = f" Health score: {health_score:.0f}." if isinstance(health_score, (int, float)) else ""
        rul_note = f" RUL: {rul_hours:.0f}h." if isinstance(rul_hours, (int, float)) else ""

        return ScenarioAgentResult(
            agent_id=self.agent_id,
            title=self.title,
            summary=(
                f"Budget lens ({context.scope}): maintenance budget {context.maintenance_budget}. "
                f"Risk level: {context.risk_level}."
                f"{health_note}{rul_note} Instruction: {instruction}"
            ),
            details={"health_score": health_score, "rul_hours": rul_hours},
        )


class RiskScenarioAgent(ScenarioAgent):
    """Analyzes maintenance scenarios from a failure risk perspective."""

    def analyze(self, context: ScenarioContext, instruction: str) -> ScenarioAgentResult:
        health = context.twin_state.get("health", {})
        fault_prob = health.get("fault_probability")
        degradation = health.get("degradation_index")

        fault_note = f" Fault probability: {fault_prob:.1%}." if isinstance(fault_prob, (int, float)) else ""
        deg_note = f" Degradation: {degradation:.1%}." if isinstance(degradation, (int, float)) else ""

        return ScenarioAgentResult(
            agent_id=self.agent_id,
            title=self.title,
            summary=(
                f"Risk lens ({context.scope}): risk level {context.risk_level}. "
                f"Persona: {context.persona_id}."
                f"{fault_note}{deg_note} Instruction: {instruction}"
            ),
            details={"fault_probability": fault_prob, "degradation_index": degradation},
        )


class PaybackScenarioAgent(ScenarioAgent):
    """Analyzes maintenance scenarios from an ROI/payback perspective."""

    def analyze(self, context: ScenarioContext, instruction: str) -> ScenarioAgentResult:
        health = context.twin_state.get("health", {})
        energy_penalty = health.get("energy_penalty_pct")
        downtime_cost = health.get("estimated_downtime_cost")

        energy_note = f" Energy penalty: {energy_penalty:.1f}%." if isinstance(energy_penalty, (int, float)) else ""
        cost_note = f" Est. downtime cost: ${downtime_cost:,.0f}." if isinstance(downtime_cost, (int, float)) else ""

        return ScenarioAgentResult(
            agent_id=self.agent_id,
            title=self.title,
            summary=(
                f"Payback lens ({context.scope}): target {context.payback_timeline}. "
                f"Persona: {context.persona_id}."
                f"{energy_note}{cost_note} Instruction: {instruction}"
            ),
            details={"energy_penalty_pct": energy_penalty, "downtime_cost": downtime_cost},
        )
