"""
Decision Advisory Agent — LLM-powered post-composition reasoning.

Consumes the composite result produced by the Orchestrator pipeline and uses
CrewAI agents to generate:

1. **Strategic Recommendations** — prioritized, justified, actionable advice
2. **Executive Narrative** — board-ready summary with trade-off explanations
3. **Pareto Trade-off Analysis** — explains which KPIs compete and why
4. **Cross-KPI Insight Synthesis** — patterns a human wouldn't spot
5. **Location-level Prioritization Rationale** — why top/bottom locations rank as they do

The agent receives the full composite dict as context and is backed by
LoweconexTools for evidence retrieval.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loweconex_platform.config import SYSTEM_PROMPT, EVIDENCE_GROUNDING_SUFFIX
from loweconex_platform.execution.execution_engine import (
    RecommendationTracker,
    RecommendationRecord,
)

logger = logging.getLogger(__name__)

from shared.agents.crewai_base import (
    Agent, Crew, Process, Task, BaseTool, CREWAI_AVAILABLE,
)


# =============================================================================
# Tool: Composite Result Reader
# =============================================================================

class ReadCompositeResultTool(BaseTool):
    """Provides the full composite result JSON to the advisory agent."""

    name: str = "read_composite_result"
    description: str = (
        "Returns the full composite result JSON from the orchestration pipeline. "
        "Contains: executive_summary, kpi_scorecards, kpi_results, "
        "savings_reconciliation, roi_metrics, scenario_analysis, "
        "portfolio_optimization, cross_asset_optimization."
    )

    def __init__(self, composite: Dict[str, Any]):
        super().__init__()
        self._composite = composite

    def _run(self, section: str = "") -> str:
        if section and section in self._composite:
            return json.dumps(self._composite[section], indent=2, default=str)
        return json.dumps(self._composite, indent=2, default=str)


class ReadParetoFrontierTool(BaseTool):
    """Provides the Pareto frontier data for trade-off analysis."""

    name: str = "read_pareto_frontier"
    description: str = (
        "Returns the Pareto frontier (savings vs confidence) and thermal "
        "interaction group data from cross-asset optimization."
    )

    def __init__(self, composite: Dict[str, Any]):
        super().__init__()
        self._cross = composite.get("cross_asset_optimization", {})

    def _run(self) -> str:
        return json.dumps(self._cross, indent=2, default=str)


class ReadLocationRankingTool(BaseTool):
    """Provides location ranking data for prioritization rationale."""

    name: str = "read_location_ranking"
    description: str = (
        "Returns ranked locations with composite scores, savings, and "
        "top/bottom decile data."
    )

    def __init__(self, report_sections: Dict[str, Any]):
        super().__init__()
        self._ranking = report_sections.get("location_ranking", {})

    def _run(self) -> str:
        return json.dumps(self._ranking, indent=2, default=str)


class ReadScenarioComparisonTool(BaseTool):
    """Provides scenario comparison data."""

    name: str = "read_scenario_comparison"
    description: str = (
        "Returns side-by-side scenario comparison (conservative, expected, "
        "aggressive) with reconciled totals."
    )

    def __init__(self, composite: Dict[str, Any]):
        super().__init__()
        self._scenarios = composite.get("scenario_analysis", {})

    def _run(self) -> str:
        return json.dumps(self._scenarios, indent=2, default=str)


class ReadOwnershipDecisionTool(BaseTool):
    """Provides ownership decision crew output to advisory agents."""

    name: str = "read_ownership_decision"
    description: str = (
        "Returns the Ownership Decision Crew output JSON: Pareto-optimal options, "
        "stakeholder negotiation log, cost stack by quadrant, consolidated ROI, "
        "board narrative, assumption register, and lineage summary. "
        "Use section param to filter: 'pareto', 'negotiation', 'positions', "
        "'cost_stack', 'roi', 'narrative', 'assumptions', 'lineage'."
    )

    def __init__(self, composite: Dict[str, Any]):
        super().__init__()
        self._ownership = composite.get("ownership_decision", {})

    def _run(self, section: str = "") -> str:
        section_map = {
            "pareto": "pareto_options",
            "negotiation": "negotiation_log",
            "positions": "stakeholder_positions",
            "cost_stack": "unified_cost_stack",
            "roi": "consolidated_roi",
            "narrative": "board_narrative",
            "assumptions": "assumption_register",
            "lineage": "lineage_summary",
        }
        if section and section in section_map:
            key = section_map[section]
            return json.dumps(self._ownership.get(key, {}), indent=2, default=str)
        return json.dumps(self._ownership, indent=2, default=str)


class ReadFeedbackHistoryTool(BaseTool):
    """Provides historical recommendation feedback for learning."""

    name: str = "read_feedback_history"
    description: str = (
        "Returns historical recommendation acceptance rates, realization rates, "
        "and per-recommendation outcomes from prior advisory runs. Use this to "
        "calibrate confidence and avoid repeating rejected recommendation types."
    )

    def __init__(self, tracker: RecommendationTracker, company_id: str):
        super().__init__()
        self._tracker = tracker
        self._company_id = company_id

    def _run(self) -> str:
        stats = self._tracker.acceptance_rate()
        company_recs = self._tracker.get_by_company(self._company_id)

        # Build per-recommendation outcome summary
        outcome_summary = []
        for rec in company_recs[-20:]:  # Last 20 recommendations
            outcome_summary.append({
                "title": rec.title,
                "kpi_name": rec.kpi_name,
                "status": rec.acceptance_status,
                "estimated_savings": rec.estimated_savings_usd,
                "actual_savings": rec.actual_savings_usd,
                "implemented": rec.implemented,
                "rejection_reason": rec.rejection_reason,
                "modifications": rec.modifications,
            })

        # Compute rejection patterns
        rejected = [r for r in company_recs if r.acceptance_status == "rejected"]
        rejection_reasons = {}
        for r in rejected:
            reason = r.rejection_reason or "unspecified"
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1

        # Compute realization accuracy for implemented recs
        assessed = [r for r in company_recs
                    if r.actual_savings_usd is not None and r.estimated_savings_usd > 0]
        realization_ratios = [
            r.actual_savings_usd / r.estimated_savings_usd for r in assessed
        ] if assessed else []
        avg_realization = (
            sum(realization_ratios) / len(realization_ratios)
            if realization_ratios else None
        )

        return json.dumps({
            "aggregate_stats": stats,
            "company_recommendation_count": len(company_recs),
            "recent_outcomes": outcome_summary,
            "rejection_patterns": rejection_reasons,
            "avg_realization_ratio": avg_realization,
            "calibration_note": (
                f"Historical realization is {avg_realization:.0%} of estimates — "
                f"adjust savings projections accordingly."
                if avg_realization else
                "No outcome data yet — use conservative estimates."
            ),
        }, indent=2, default=str)


# =============================================================================
# Advisory Output
# =============================================================================

@dataclass
class AdvisoryOutput:
    """Structured output from the Decision Advisory Agent."""
    strategic_recommendations: List[Dict[str, Any]] = field(default_factory=list)
    executive_narrative: str = ""
    trade_off_analysis: str = ""
    cross_kpi_insights: List[str] = field(default_factory=list)
    location_prioritization_rationale: str = ""
    risk_mitigation_plan: str = ""
    quick_wins: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategic_recommendations": self.strategic_recommendations,
            "executive_narrative": self.executive_narrative,
            "trade_off_analysis": self.trade_off_analysis,
            "cross_kpi_insights": self.cross_kpi_insights,
            "location_prioritization_rationale": self.location_prioritization_rationale,
            "risk_mitigation_plan": self.risk_mitigation_plan,
            "quick_wins": self.quick_wins,
            "confidence": self.confidence,
        }


# =============================================================================
# Decision Advisory Agent
# =============================================================================

class DecisionAdvisoryAgent:
    """
    CrewAI-powered agent that reasons over the composite orchestration output
    to produce strategic recommendations, executive narratives, and trade-off
    explanations.

    Uses a 3-agent crew:
    - **Strategist**: Produces ranked recommendations with justifications
    - **Narrator**: Writes board-ready executive narrative
    - **Analyst**: Explains Pareto trade-offs and cross-KPI interactions
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        tools: Optional[Any] = None,
        recommendation_tracker: Optional[RecommendationTracker] = None,
    ):
        self.config = config or {}
        self.tools = tools  # LoweconexTools instance (optional, for evidence lookup)
        self.recommendation_tracker = recommendation_tracker or RecommendationTracker()

    def advise(
        self,
        composite_result: Dict[str, Any],
        report_sections: Optional[Dict[str, Any]] = None,
    ) -> AdvisoryOutput:
        """
        Run the advisory crew on a composite result.

        Args:
            composite_result: Full composite dict from OrchestratorCrew.
            report_sections: Optional pre-built report sections (for location ranking).

        Returns:
            AdvisoryOutput with recommendations, narrative, and analysis.
        """
        company_id = composite_result.get("company_id", "")

        if not CREWAI_AVAILABLE:
            logger.warning("CrewAI not available — running deterministic advisory fallback")
            output = self._deterministic_fallback(composite_result, report_sections)
        else:
            output = self._run_advisory_crew(composite_result, report_sections or {})

        # Register recommendations with the tracker for feedback loop
        self._register_recommendations(output, company_id, composite_result)
        return output

    def _register_recommendations(
        self,
        output: AdvisoryOutput,
        company_id: str,
        composite: Dict[str, Any],
    ):
        """Register each recommendation with the tracker for lifecycle management."""
        run_id = composite.get("run_id", "")
        for rec in output.strategic_recommendations:
            record = RecommendationRecord(
                title=rec.get("title", ""),
                description=rec.get("justification", ""),
                kpi_name=rec.get("kpi_name", rec.get("title", "").lower().replace(" ", "_")),
                company_id=company_id,
                recommended_action=rec.get("title", ""),
                estimated_savings_usd=rec.get("savings_medium", 0),
                confidence=rec.get("confidence", 0),
                correlation_id=run_id,
            )
            rec_id = self.recommendation_tracker.create(record)
            rec["rec_id"] = rec_id  # Attach ID back to the recommendation
            logger.info(f"Registered recommendation: {record.title} (rec_id={rec_id})")

    # -------------------------------------------------------------------------
    # CrewAI path
    # -------------------------------------------------------------------------

    def _run_advisory_crew(
        self,
        composite: Dict[str, Any],
        report_sections: Dict[str, Any],
    ) -> AdvisoryOutput:
        system = SYSTEM_PROMPT + "\n" + EVIDENCE_GROUNDING_SUFFIX

        company_id = composite.get("company_id", "")

        # Build tools
        composite_tool = ReadCompositeResultTool(composite)
        pareto_tool = ReadParetoFrontierTool(composite)
        location_tool = ReadLocationRankingTool(report_sections)
        scenario_tool = ReadScenarioComparisonTool(composite)
        feedback_tool = ReadFeedbackHistoryTool(self.recommendation_tracker, company_id)
        ownership_tool = ReadOwnershipDecisionTool(composite)
        all_tools = [composite_tool, pareto_tool, location_tool, scenario_tool, feedback_tool, ownership_tool]

        # ---- Build feedback context for agent prompts ----
        feedback_stats = self.recommendation_tracker.acceptance_rate()
        company_recs = self.recommendation_tracker.get_by_company(company_id)
        feedback_context = ""
        if feedback_stats.get("total", 0) > 0:
            acc_rate = feedback_stats.get("acceptance_rate", 0)
            impl_rate = feedback_stats.get("implementation_rate", 0)
            realization = feedback_stats.get("realization_rate")
            feedback_context = (
                f"\n\nHISTORICAL FEEDBACK ({feedback_stats['total']} prior recommendations):\n"
                f"- Acceptance rate: {acc_rate:.0%}\n"
                f"- Implementation rate: {impl_rate:.0%}\n"
            )
            if realization is not None:
                feedback_context += f"- Savings realization: {realization:.0%} of estimates\n"

            # Add rejection patterns
            rejected = [r for r in company_recs if r.acceptance_status == "rejected"]
            if rejected:
                reasons = {}
                for r in rejected:
                    reason = r.rejection_reason or "unspecified"
                    reasons[reason] = reasons.get(reason, 0) + 1
                top_reasons = sorted(reasons.items(), key=lambda x: x[1], reverse=True)[:3]
                feedback_context += "- Top rejection reasons: " + "; ".join(
                    f"{reason} ({count}x)" for reason, count in top_reasons
                ) + "\n"
                feedback_context += (
                    "IMPORTANT: Avoid recommending actions similar to previously rejected ones "
                    "unless the underlying conditions have materially changed.\n"
                )

            if realization is not None and realization < 0.7:
                feedback_context += (
                    f"WARNING: Historical realization ({realization:.0%}) is below 70%. "
                    "Apply a conservative bias — reduce savings estimates by "
                    f"{(1 - realization) * 100:.0f}% as a calibration adjustment.\n"
                )

        # --- Agent 1: Strategic Advisor ---
        strategist = Agent(
            role="Strategic Investment Advisor",
            goal=(
                "Analyze the composite KPI results, portfolio optimization output, "
                "scenario comparison, AND the ownership decision crew output to produce "
                "a ranked list of strategic recommendations. Use read_ownership_decision "
                "to access Pareto-optimal investment options, stakeholder constraints, "
                "and the ownership-aware cost stack with quadrant attribution. "
                "Each recommendation must include: title, justification, expected savings, "
                "confidence, implementation priority (1-5), and dependencies. "
                "FIRST use read_feedback_history to review prior recommendation outcomes "
                "and calibrate your estimates accordingly."
            ),
            backstory=(
                system + "\n"
                "You are a senior advisor to the C-suite at a multi-site grocery/retail operator. "
                "You specialize in translating analytics into capital allocation decisions. "
                "You never recommend actions without quantified evidence. "
                "You identify quick wins (< 3 month payback) separately from structural investments. "
                "You LEARN from past recommendations: check which were accepted, rejected, and "
                "implemented, and what the actual savings realization was. Use this to calibrate "
                "your confidence levels and avoid repeating recommendations that were rejected."
                + feedback_context
            ),
            tools=all_tools,
            allow_delegation=False,
            verbose=True,
        )

        # --- Agent 2: Executive Narrator ---
        narrator = Agent(
            role="Executive Communication Specialist",
            goal=(
                "Write a 500-word executive narrative suitable for a board presentation. "
                "Cover: total savings opportunity, key risks, scenario sensitivity, "
                "top 3 recommendations, and what happens if the company does nothing."
            ),
            backstory=(
                system + "\n"
                "You write concise, fact-dense executive summaries for board decks. "
                "Every number you cite must come from the composite result data. "
                "Use plain language, avoid jargon, and structure with clear sections."
            ),
            tools=[composite_tool, scenario_tool],
            allow_delegation=False,
            verbose=True,
        )

        # --- Agent 3: Trade-off Analyst ---
        analyst = Agent(
            role="Portfolio Trade-off Analyst",
            goal=(
                "Analyze the Pareto frontier, cross-asset thermal interaction groups, "
                "scenario comparison, AND ownership decision Pareto options to explain: "
                "(1) which KPIs compete for the same savings, "
                "(2) which asset groups have the highest marginal impact, "
                "(3) how the conservative vs aggressive scenarios affect the recommendation set, "
                "(4) location-level prioritization rationale, "
                "(5) stakeholder trade-offs from the negotiation log "
                "(e.g., Finance vs FM on capex, Compliance constraints)."
            ),
            backstory=(
                system + "\n"
                "You are a quantitative analyst who specializes in portfolio optimization "
                "and multi-criteria decision making. You explain trade-offs clearly, "
                "referencing specific KPI pairs, thermal groups, confidence bounds, "
                "and stakeholder negotiation outcomes."
            ),
            tools=[composite_tool, pareto_tool, location_tool, scenario_tool, ownership_tool],
            allow_delegation=False,
            verbose=True,
        )

        # --- Tasks ---
        task_strategy = Task(
            description=(
                "Use read_composite_result to examine all KPI results, portfolio optimization, "
                "and ROI metrics. Then produce a JSON array of strategic recommendations, each with: "
                "title, justification, savings_medium, confidence, priority (1-5), category "
                "(quick_win | structural | capex | policy), dependencies, and risk_if_deferred."
            ),
            agent=strategist,
            expected_output=(
                '{"recommendations": [{"title": "...", "justification": "...", '
                '"savings_medium": 0, "confidence": 0.0, "priority": 1, '
                '"category": "quick_win", "dependencies": [], "risk_if_deferred": "..."}]}'
            ),
        )

        task_narrative = Task(
            description=(
                "Read the composite result and scenario comparison. Write a board-ready "
                "executive narrative (plain text, 400-600 words) covering: "
                "(1) headline savings figure with confidence range, "
                "(2) top 3 actions and their payback, "
                "(3) key risks and data gaps, "
                "(4) scenario sensitivity (how much does the answer change?), "
                "(5) cost of inaction."
            ),
            agent=narrator,
            expected_output="A 400-600 word executive narrative in plain text.",
        )

        task_tradeoffs = Task(
            description=(
                "Use read_pareto_frontier, read_scenario_comparison, and read_location_ranking "
                "to produce a JSON object with: "
                "(1) trade_off_analysis: text explaining competing KPIs, "
                "(2) cross_kpi_insights: array of insight strings, "
                "(3) location_prioritization_rationale: text explaining top/bottom locations, "
                "(4) risk_mitigation_plan: text with specific actions to de-risk low-confidence KPIs."
            ),
            agent=analyst,
            expected_output=(
                '{"trade_off_analysis": "...", "cross_kpi_insights": ["..."], '
                '"location_prioritization_rationale": "...", "risk_mitigation_plan": "..."}'
            ),
        )

        # --- Crew ---
        crew = Crew(
            agents=[strategist, narrator, analyst],
            tasks=[task_strategy, task_narrative, task_tradeoffs],
            process=Process.sequential,
            verbose=True,
        )

        try:
            crew_output = crew.kickoff(inputs={
                "company_id": composite.get("company_id", ""),
                "run_id": composite.get("run_id", ""),
            })
            return self._parse_crew_output(crew_output, composite)
        except Exception as e:
            logger.error(f"Advisory crew failed: {e}", exc_info=True)
            return self._deterministic_fallback(composite, report_sections)

    def _parse_crew_output(
        self, crew_output: Any, composite: Dict[str, Any]
    ) -> AdvisoryOutput:
        """Parse structured output from advisory crew tasks."""
        output = AdvisoryOutput()

        raw = str(crew_output) if crew_output else ""

        # Attempt to extract JSON blocks from crew output
        try:
            # Strategy task output
            if '"recommendations"' in raw:
                start = raw.index('{"recommendations"')
                depth = 0
                end = start
                for i, c in enumerate(raw[start:], start):
                    if c == '{': depth += 1
                    elif c == '}': depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
                strategy_json = json.loads(raw[start:end])
                recs = strategy_json.get("recommendations", [])
                output.strategic_recommendations = recs
                output.quick_wins = [r for r in recs if r.get("category") == "quick_win"]
        except (json.JSONDecodeError, ValueError):
            logger.debug("Could not parse strategy JSON from crew output")

        # Trade-off analysis JSON
        try:
            if '"trade_off_analysis"' in raw:
                start = raw.index('{"trade_off_analysis"')
                depth = 0
                end = start
                for i, c in enumerate(raw[start:], start):
                    if c == '{': depth += 1
                    elif c == '}': depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
                analysis = json.loads(raw[start:end])
                output.trade_off_analysis = analysis.get("trade_off_analysis", "")
                output.cross_kpi_insights = analysis.get("cross_kpi_insights", [])
                output.location_prioritization_rationale = analysis.get(
                    "location_prioritization_rationale", ""
                )
                output.risk_mitigation_plan = analysis.get("risk_mitigation_plan", "")
        except (json.JSONDecodeError, ValueError):
            logger.debug("Could not parse trade-off JSON from crew output")

        # Narrative is plain text — extract from between the JSON blocks
        if not output.executive_narrative:
            output.executive_narrative = self._extract_narrative_fallback(composite)

        output.confidence = 0.8 if output.strategic_recommendations else 0.4
        return output

    # -------------------------------------------------------------------------
    # Deterministic fallback
    # -------------------------------------------------------------------------

    def _deterministic_fallback(
        self,
        composite: Dict[str, Any],
        report_sections: Optional[Dict[str, Any]] = None,
    ) -> AdvisoryOutput:
        """Rule-based fallback when CrewAI is not available."""
        output = AdvisoryOutput()

        exec_summary = composite.get("executive_summary", {})
        kpi_results = composite.get("kpi_results", {})
        roi = composite.get("roi_metrics", {})
        optimization = composite.get("portfolio_optimization", {})
        cross_asset = composite.get("cross_asset_optimization", {})
        scenarios = composite.get("scenario_analysis", {})

        total_med = exec_summary.get("total_savings_medium", 0)
        total_low = exec_summary.get("total_savings_low", 0)
        total_high = exec_summary.get("total_savings_high", 0)
        payback = roi.get("payback_months")

        # --- Strategic Recommendations ---
        ranked_kpis = sorted(
            kpi_results.items(),
            key=lambda kv: kv[1].get("savings_medium", 0),
            reverse=True,
        )

        priority = 1
        for kpi_name, result in ranked_kpis:
            savings = result.get("savings_medium", 0)
            confidence = result.get("confidence", 0)
            if savings <= 0:
                continue

            category = "quick_win"
            if kpi_name == "capex_lifecycle_optimization":
                category = "capex"
            elif confidence < 0.5:
                category = "structural"
            elif savings > total_med * 0.15:
                category = "structural"

            rec = {
                "title": f"Implement {kpi_name.replace('_', ' ').title()}",
                "justification": result.get("narrative", ""),
                "savings_medium": savings,
                "confidence": confidence,
                "priority": priority,
                "category": category,
                "dependencies": result.get("depends_on_kpis", []),
                "risk_if_deferred": (
                    f"${savings:,.0f}/year in unrealized savings"
                    if savings > 0 else "Minimal"
                ),
            }
            output.strategic_recommendations.append(rec)
            if category == "quick_win":
                output.quick_wins.append(rec)
            priority += 1

        # --- Executive Narrative ---
        output.executive_narrative = self._extract_narrative_fallback(composite)

        # --- Trade-off Analysis ---
        pareto = cross_asset.get("pareto_frontier", [])
        if pareto:
            frontier_names = [p["kpi_name"] for p in pareto]
            output.trade_off_analysis = (
                f"The Pareto frontier includes {len(pareto)} KPIs that are not dominated "
                f"on both savings and confidence axes: {', '.join(frontier_names)}. "
                f"KPIs outside the frontier offer lower returns per unit of confidence risk."
            )

        # --- Cross-KPI Insights ---
        thermal_groups = cross_asset.get("thermal_interaction_groups", [])
        if thermal_groups:
            output.cross_kpi_insights.append(
                f"{len(thermal_groups)} thermal interaction groups detected — "
                f"optimizing one asset in a group affects adjacent assets."
            )

        group_impacts = cross_asset.get("group_marginal_impacts", [])
        for gi in group_impacts[:3]:
            if gi.get("total_savings_medium", 0) > 0:
                output.cross_kpi_insights.append(
                    f"Asset group {gi['asset_ids'][:3]}... contributes "
                    f"${gi['total_savings_medium']:,.0f} via {gi['contributing_kpis']}."
                )

        # --- Location Prioritization ---
        if report_sections:
            loc_ranking = report_sections.get("location_ranking", {})
            top = loc_ranking.get("top_decile", [])
            bottom = loc_ranking.get("bottom_decile", [])
            if top:
                output.location_prioritization_rationale = (
                    f"Top-priority location: {top[0].get('location_id', 'N/A')} "
                    f"(score={top[0].get('composite_score', 0):.3f}, "
                    f"savings=${top[0].get('savings_medium', 0):,.0f}). "
                )
                if bottom:
                    output.location_prioritization_rationale += (
                        f"Lowest: {bottom[-1].get('location_id', 'N/A')} "
                        f"(score={bottom[-1].get('composite_score', 0):.3f})."
                    )

        # --- Risk Mitigation ---
        low_conf = [k for k, v in kpi_results.items() if v.get("confidence", 1) < 0.5]
        if low_conf:
            output.risk_mitigation_plan = (
                f"{len(low_conf)} KPIs have confidence < 50%: {', '.join(low_conf)}. "
                f"Prioritize data collection for these KPIs to improve confidence before "
                f"committing capital. Consider pilot programs at 2-3 locations."
            )

        output.confidence = 0.6

        # --- Enrich with Ownership Decision Crew output ---
        ownership = composite.get("ownership_decision", {})
        if ownership:
            output = self._enrich_with_ownership(output, ownership)

        return output

    def _enrich_with_ownership(
        self,
        output: AdvisoryOutput,
        ownership: Dict[str, Any],
    ) -> AdvisoryOutput:
        """Enrich advisory output with ownership decision crew data."""
        pareto_options = ownership.get("pareto_options", [])
        neg_log = ownership.get("negotiation_log", {})
        positions = ownership.get("stakeholder_positions", [])
        board_narrative = ownership.get("board_narrative", "")
        roi = ownership.get("consolidated_roi", {})

        # Merge Pareto options into trade-off analysis
        if pareto_options:
            pareto_lines = []
            for opt in pareto_options:
                label = opt.get("label", "")
                npv = opt.get("npv", 0)
                risk = opt.get("risk_score", 0)
                pareto_lines.append(f"{label}: NPV ${npv:,.0f}, risk {risk:.2f}")

            ownership_tradeoff = (
                f"\n\nOwnership-Aware Analysis: {len(pareto_options)} Pareto-optimal "
                f"investment options identified by the 12-agent decision crew:\n"
                + "\n".join(f"  • {l}" for l in pareto_lines)
            )
            recommended = ownership.get("recommended_option_id", "")
            rec_opt = next((o for o in pareto_options if o.get("option_id") == recommended), None)
            if rec_opt:
                ownership_tradeoff += (
                    f"\nRecommended: {rec_opt.get('label', '')} — maximizes "
                    f"consolidated NPV while respecting all stakeholder constraints."
                )
            output.trade_off_analysis = (output.trade_off_analysis or "") + ownership_tradeoff

        # Merge negotiation conflicts into cross-KPI insights
        conflicts = neg_log.get("conflicts_detected", [])
        for conflict in conflicts[:5]:
            agents = ", ".join(conflict.get("agents_involved", []))
            desc = conflict.get("description", "")
            resolution = conflict.get("resolution", "Unresolved")
            output.cross_kpi_insights.append(
                f"Stakeholder conflict ({agents}): {desc} → {resolution}"
            )

        # Merge ownership ROI into narrative if available
        if board_narrative and not output.executive_narrative:
            output.executive_narrative = board_narrative
        elif board_narrative:
            output.executive_narrative += (
                "\n\n--- Ownership-Aware Cost Analysis ---\n" + board_narrative
            )

        # Enrich recommendations with ownership quadrant data
        cost_by_dim = ownership.get("cost_lines_by_dimension", {})
        if cost_by_dim:
            dim_totals = {}
            for dim, lines in cost_by_dim.items():
                dim_totals[dim] = sum(abs(l.get("amount", 0)) for l in lines)
            if dim_totals:
                output.cross_kpi_insights.append(
                    f"Cost distribution by dimension: "
                    + ", ".join(f"{d}=${v:,.0f}" for d, v in dim_totals.items() if v > 0)
                )

        # Boost confidence if we have ownership crew data
        if pareto_options and roi.get("npv", 0) > 0:
            output.confidence = min(output.confidence + 0.15, 0.95)

        return output

    def _extract_narrative_fallback(self, composite: Dict[str, Any]) -> str:
        """Generate a deterministic executive narrative from composite data."""
        exec_summary = composite.get("executive_summary", {})
        roi = composite.get("roi_metrics", {})
        risks = exec_summary.get("key_risks", [])

        total_med = exec_summary.get("total_savings_medium", 0)
        total_low = exec_summary.get("total_savings_low", 0)
        total_high = exec_summary.get("total_savings_high", 0)
        kpi_count = exec_summary.get("kpi_count", 0)
        approved = exec_summary.get("approved_kpis", 0)
        payback = roi.get("payback_months")
        net_npv = roi.get("net_npv", 0)

        lines = [
            f"The platform analysis identified ${total_med:,.0f}/year in savings "
            f"across {kpi_count} KPI dimensions (range: ${total_low:,.0f} – ${total_high:,.0f}). "
            f"{approved} of {kpi_count} KPIs passed QA validation.",
            "",
        ]

        if payback:
            lines.append(
                f"Estimated payback period: {payback:.1f} months. "
                f"Net present value over the analysis horizon: ${net_npv:,.0f}."
            )

        # Top 3 KPIs
        kpi_results = composite.get("kpi_results", {})
        top3 = sorted(
            kpi_results.items(),
            key=lambda kv: kv[1].get("savings_medium", 0),
            reverse=True,
        )[:3]
        if top3:
            lines.append("")
            lines.append("Top opportunities:")
            for kpi_name, result in top3:
                s = result.get("savings_medium", 0)
                c = result.get("confidence", 0)
                lines.append(
                    f"  • {kpi_name.replace('_', ' ').title()}: "
                    f"${s:,.0f}/year (confidence: {c:.0%})"
                )

        if risks:
            lines.append("")
            lines.append(f"Key risks: {'; '.join(risks[:3])}")

        # Cost of inaction
        lines.append("")
        lines.append(
            f"Cost of inaction: delaying 12 months foregoes an estimated "
            f"${total_med:,.0f} in annual savings, with compounding effects "
            f"from deferred maintenance and continued energy waste."
        )

        return "\n".join(lines)
