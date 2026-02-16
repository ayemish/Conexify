"""Scenario orchestration for persona-driven conversational analysis."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore

from shared.agents.crewai_base import Agent, Task, Crew, Process, CREWAI_AVAILABLE  # type: ignore

from ..config import settings
from ..agents.scenario_agents import (
    ScenarioContext,
    BudgetScenarioAgent,
    RiskScenarioAgent,
    PaybackScenarioAgent,
)

logger = logging.getLogger(__name__)


@dataclass
class ScenarioAgentInstruction:
    agent_id: str
    title: str
    instruction: str


@dataclass
class ScenarioResponse:
    persona_id: str
    persona_prompt: str
    instructions: List[ScenarioAgentInstruction]
    outputs: List[Dict[str, Any]]
    created_at: datetime


class ScenarioService:
    """Generates scenario agent instructions and simulates agent outputs."""

    def __init__(self):
        self._client = None
        self.personas = [
            {
                "id": "company",
                "name": "Company Persona",
                "tagline": "Enterprise strategy, portfolio tradeoffs, long-term value.",
                "prompt": (
                    "You are the company-level strategy persona. Prioritize enterprise growth, "
                    "risk controls, and cross-brand coherence. Evaluate marketing investments across "
                    "the entire portfolio, balancing near-term performance with long-term brand equity."
                ),
            },
            {
                "id": "brand_manager",
                "name": "Brand Manager Persona",
                "tagline": "Brand-level outcomes, tactical activation, speed.",
                "prompt": (
                    "You are the brand manager persona. Focus on brand P&L, channel mix, "
                    "and competitive pressure. Prefer actionable, fast feedback loops and clear "
                    "brand-level tradeoffs."
                ),
            },
            {
                "id": "finance",
                "name": "Finance Persona",
                "tagline": "Capital efficiency, risk-adjusted returns, payback discipline.",
                "prompt": (
                    "You are the finance persona. Prioritize capital efficiency, risk-adjusted ROI, "
                    "and payback timelines. Challenge assumptions and enforce budget constraints."
                ),
            },
        ]

    def _client_or_raise(self):
        if OpenAI is None:
            raise RuntimeError("OpenAI client not available. Install openai>=1.30.0")
        if self._client is None:
            self._client = OpenAI(api_key=settings.openai.api_key)
        return self._client

    def generate_instructions(
        self,
        persona_prompt: str,
        user_message: str,
        budget: str,
        risk: str,
        payback: str,
        scope: str,
        twin_state: Optional[Dict[str, Any]] = None,
    ) -> List[ScenarioAgentInstruction]:
        """Use OpenAI to generate scenario agent instructions, fallback to templates."""
        base_questions = (
            "What is the marketing budget? "
            "What is your level of risk? "
            "What is your timeline for payback?"
        )
        if settings.openai.api_key:
            try:
                client = self._client_or_raise()
                twin_note = f"\nTwin State: {twin_state}" if twin_state else ""
                prompt = (
                    "You are to design scenario agent instructions for a marketing planning system. "
                    "Given a persona prompt and the user question, produce 2-4 concise scenario agent instructions. "
                    "Each instruction should incorporate the questions: budget, risk, and payback timeline, "
                    "and adapt to the specified scope. Return as JSON list of objects with fields: agent_id, title, instruction.\n\n"
                    f"Persona Prompt: {persona_prompt}\n"
                    f"User Message: {user_message}\n"
                    f"Scope: {scope}\n"
                    f"Budget: {budget}\nRisk: {risk}\nPayback: {payback}\n"
                    f"Questions: {base_questions}"
                    f"{twin_note}"
                )
                response = client.responses.create(
                    model=settings.openai.chat_model,
                    input=prompt,
                )
                text = response.output_text
                # naive parse: expect JSON list; fallback on templates if parsing fails
                import json
                data = json.loads(text)
                return [
                    ScenarioAgentInstruction(
                        agent_id=item.get("agent_id", f"agent_{i}"),
                        title=item.get("title", "Scenario Agent"),
                        instruction=item.get("instruction", ""),
                    )
                    for i, item in enumerate(data)
                ]
            except Exception as exc:
                logger.warning(f"OpenAI instruction generation failed, using templates: {exc}")

        return self._template_instructions(persona_prompt, budget, risk, payback, scope)

    def _template_instructions(
        self,
        persona_prompt: str,
        budget: str,
        risk: str,
        payback: str,
        scope: str,
    ) -> List[ScenarioAgentInstruction]:
        return [
            ScenarioAgentInstruction(
                agent_id="scenario_budget",
                title="Budget Framing",
                instruction=(
                    f"Interpret budget at the {scope} level. "
                    f"Budget: {budget}. Provide constraints and allocation guidance."
                ),
            ),
            ScenarioAgentInstruction(
                agent_id="scenario_risk",
                title="Risk Appetite",
                instruction=(
                    f"Assess risk tolerance at the {scope} level. "
                    f"Risk: {risk}. Recommend safe vs aggressive levers."
                ),
            ),
            ScenarioAgentInstruction(
                agent_id="scenario_payback",
                title="Payback Timeline",
                instruction=(
                    f"Evaluate payback timeline at the {scope} level. "
                    f"Payback: {payback}. Propose near-term vs long-term plan."
                ),
            ),
        ]

    def simulate_agents(
        self,
        context: ScenarioContext,
        instructions: List[ScenarioAgentInstruction],
    ) -> List[Dict[str, Any]]:
        """Activate scenario agents (CrewAI if available, else lightweight)."""
        crew_outputs = self._run_crewai(context, instructions)
        if crew_outputs:
            return crew_outputs
        agents = {
            "scenario_budget": BudgetScenarioAgent("scenario_budget", "Budget Framing"),
            "scenario_risk": RiskScenarioAgent("scenario_risk", "Risk Appetite"),
            "scenario_payback": PaybackScenarioAgent("scenario_payback", "Payback Timeline"),
        }
        outputs = []
        for inst in instructions:
            agent = agents.get(inst.agent_id)
            if agent is None:
                outputs.append({
                    "agent_id": inst.agent_id,
                    "title": inst.title,
                    "summary": f"Scenario agent not found; instruction: {inst.instruction}",
                })
                continue
            result = agent.analyze(context, inst.instruction)
            outputs.append({
                "agent_id": result.agent_id,
                "title": result.title,
                "summary": result.summary,
            })
        return outputs

    def _run_crewai(
        self,
        context: ScenarioContext,
        instructions: List[ScenarioAgentInstruction],
    ) -> List[Dict[str, Any]]:
        """Run instructions through CrewAI runtime if available."""
        if not settings.openai.scenario_crewai_enabled:
            return []
        if Agent is None or Task is None or Crew is None or Process is None:
            return []
        if not settings.openai.api_key:
            return []

        crew_agents = []
        tasks = []
        for inst in instructions:
            agent = Agent(
                role=inst.title,
                goal=inst.instruction,
                backstory=context.persona_prompt,
                verbose=False,
            )
            task = Task(
                description=(
                    f"{inst.instruction}\n"
                    f"Context: scope={context.scope}, budget={context.marketing_budget}, "
                    f"risk={context.risk_level}, payback={context.payback_timeline}. "
                    f"User message: {context.user_message}"
                ),
                expected_output="Concise recommendation and key considerations.",
                agent=agent,
            )
            crew_agents.append(agent)
            tasks.append(task)

        crew = Crew(
            agents=crew_agents,
            tasks=tasks,
            process=Process.sequential,
            verbose=False,
        )
        try:
            results = crew.kickoff()
            # CrewAI returns a combined output; map each task output if available
            outputs = []
            if isinstance(results, list):
                for inst, result in zip(instructions, results):
                    outputs.append({
                        "agent_id": inst.agent_id,
                        "title": inst.title,
                        "summary": str(result),
                    })
            else:
                for inst in instructions:
                    outputs.append({
                        "agent_id": inst.agent_id,
                        "title": inst.title,
                        "summary": str(results),
                    })
            return outputs
        except Exception as exc:
            logger.warning(f"CrewAI execution failed, falling back to local agents: {exc}")
            return []

    def get_personas(self) -> List[Dict[str, Any]]:
        return list(self.personas)

    def run_scenario(
        self,
        persona_id: str,
        persona_prompt: str,
        user_message: str,
        budget: str,
        risk: str,
        payback: str,
        scope: str,
        twin_state: Optional[Dict[str, Any]] = None,
    ) -> ScenarioResponse:
        context = ScenarioContext(
            persona_id=persona_id,
            persona_prompt=persona_prompt,
            user_message=user_message,
            scope=scope,
            marketing_budget=budget,
            risk_level=risk,
            payback_timeline=payback,
            twin_state=twin_state or {},
        )
        instructions = self.generate_instructions(
            persona_prompt, user_message, budget, risk, payback, scope, twin_state=twin_state
        )
        outputs = self.simulate_agents(context, instructions)
        return ScenarioResponse(
            persona_id=persona_id,
            persona_prompt=persona_prompt,
            instructions=instructions,
            outputs=outputs,
            created_at=datetime.utcnow(),
        )


_scenario_service: Optional[ScenarioService] = None


def get_scenario_service() -> ScenarioService:
    global _scenario_service
    if _scenario_service is None:
        _scenario_service = ScenarioService()
    return _scenario_service
