"""
KPI Crew Base Template — mandatory structure for all 14 KPI crews.

Each crew follows: Research Agent → Extraction Agent → Calculation Agent → QA Agent
Sequential workflow with bounded retries and artifact persistence.

All agents are CrewAI-powered with domain-specific tool bindings.
The deterministic calculation function from KPICrewSpec is exposed as a
CrewAI tool so the Calculation agent can invoke it with structured inputs.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from loweconex_platform.config import EVIDENCE_GROUNDING_SUFFIX, SYSTEM_PROMPT
from loweconex_platform.event_bus.events import EventType, create_envelope
from loweconex_platform.event_bus.redis_streams import LoweconexEventBus
from loweconex_platform.kpi_crews.tools import ArtifactStore, LoweconexTools
from loweconex_platform.kpi_crews.crewai_tools import (
    build_research_tools,
    build_extraction_tools,
    build_calculation_tools,
    build_qa_tools,
)
from loweconex_platform.kpi_crews.research_corpus import get_research_snippets, get_benchmarks_for_kpi


# =============================================================================
# Historical Result Store (for QA anomaly detection across runs)
# =============================================================================

class KPIHistoryStore:
    """
    Store of past KPI run results for drift detection.
    Writes through to PostgreSQL via KPIResultModel when available,
    keeps an in-memory cache for fast access.
    """
    _history: Dict[str, List[Dict[str, Any]]] = {}
    _hydrated: bool = False

    @classmethod
    def _hydrate_once(cls):
        """Load recent KPI results from PostgreSQL into the in-memory cache."""
        if cls._hydrated:
            return
        cls._hydrated = True
        try:
            from predictive_maintenance.persistence.database import get_session
            from predictive_maintenance.persistence.models import KPIResultModel
            with get_session() as session:
                rows = (
                    session.query(KPIResultModel)
                    .order_by(KPIResultModel.computed_at.desc())
                    .limit(500)
                    .all()
                )
                for row in reversed(rows):  # oldest first
                    entry = {
                        "savings_medium": row.savings_medium,
                        "confidence": row.confidence,
                        "computed_at": row.computed_at.isoformat() if row.computed_at else None,
                    }
                    cls._history.setdefault(row.kpi_name, []).append(entry)
                # Trim each KPI to last 50
                for k in cls._history:
                    cls._history[k] = cls._history[k][-50:]
                if rows:
                    logger.info("KPIHistoryStore: hydrated %d results from DB", len(rows))
        except Exception as e:
            logger.debug("KPIHistoryStore hydration skipped: %s", e)

    @classmethod
    def record(cls, kpi_name: str, result_summary: Dict[str, Any]):
        cls._hydrate_once()
        cls._history.setdefault(kpi_name, []).append(result_summary)
        # Keep last 50 runs
        if len(cls._history[kpi_name]) > 50:
            cls._history[kpi_name] = cls._history[kpi_name][-50:]
        # Write-through to PostgreSQL
        cls._persist_to_db(kpi_name, result_summary)

    @classmethod
    def _persist_to_db(cls, kpi_name: str, result_summary: Dict[str, Any]):
        """Write a single KPI result record to PostgreSQL for durability."""
        try:
            from predictive_maintenance.persistence.database import get_session
            from predictive_maintenance.persistence.models import KPIResultModel
            with get_session() as session:
                model = KPIResultModel(
                    run_id=result_summary.get("run_id", f"crew-{kpi_name}"),
                    site_id=result_summary.get("site_id", "default"),
                    kpi_name=kpi_name,
                    display_name=result_summary.get("display_name", kpi_name),
                    category=result_summary.get("category", ""),
                    savings_low=result_summary.get("savings_low", 0),
                    savings_medium=result_summary.get("savings_medium", 0),
                    savings_high=result_summary.get("savings_high", 0),
                    confidence=result_summary.get("confidence", 0),
                    status=result_summary.get("status", "completed"),
                    narrative=result_summary.get("narrative", ""),
                )
                session.add(model)
                session.commit()
        except Exception as e:
            logger.debug("KPIHistoryStore DB write-through failed: %s", e)

    @classmethod
    def get_history(cls, kpi_name: str) -> List[Dict[str, Any]]:
        cls._hydrate_once()
        return cls._history.get(kpi_name, [])

    @classmethod
    def get_stats(cls, kpi_name: str) -> Dict[str, Any]:
        """Compute mean/std of savings_medium and confidence from history."""
        hist = cls.get_history(kpi_name)
        if len(hist) < 2:
            return {"runs": len(hist), "sufficient_history": False}
        savings = [h.get("savings_medium", 0) for h in hist]
        confs = [h.get("confidence", 0) for h in hist]
        import statistics
        return {
            "runs": len(hist),
            "sufficient_history": True,
            "savings_mean": statistics.mean(savings),
            "savings_stdev": statistics.stdev(savings) if len(savings) > 1 else 0,
            "confidence_mean": statistics.mean(confs),
            "confidence_stdev": statistics.stdev(confs) if len(confs) > 1 else 0,
        }

logger = logging.getLogger(__name__)

from shared.agents.crewai_base import (
    Agent, BaseTool, Crew, Process, Task, CREWAI_AVAILABLE,
)


# =============================================================================
# KPI Crew Result
# =============================================================================

@dataclass
class KPICrewResult:
    """Output from a completed KPI crew run."""
    kpi_name: str
    status: str = "pending"  # pending | running | approved | rejected | error
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Research output
    research: Dict[str, Any] = field(default_factory=dict)

    # Extraction output
    extraction: Dict[str, Any] = field(default_factory=dict)
    data_quality: Dict[str, Any] = field(default_factory=dict)
    gaps: List[Dict[str, Any]] = field(default_factory=list)

    # Calculation output
    metrics: Dict[str, Any] = field(default_factory=dict)
    savings_low: float = 0.0
    savings_medium: float = 0.0
    savings_high: float = 0.0
    confidence: float = 0.0
    assumptions: List[str] = field(default_factory=list)
    twin_patches: List[Dict[str, Any]] = field(default_factory=list)
    narrative: str = ""

    # QA output
    qa_status: str = "pending"  # pending | approved | rejected
    qa_issues: List[Dict[str, Any]] = field(default_factory=list)
    qa_required_fixes: List[str] = field(default_factory=list)

    # Reasoning trace — per-agent chain-of-thought preserved for lineage
    reasoning_trace: List[Dict[str, Any]] = field(default_factory=list)
    formula_variant: str = ""  # data_driven | benchmark_driven | pdm_grounded
    variant_rationale: str = ""

    # Provenance
    artifact_ids: List[str] = field(default_factory=list)
    evidence_refs: List[Dict[str, Any]] = field(default_factory=list)
    lineage_ids: List[str] = field(default_factory=list)
    started_ts: Optional[str] = None
    completed_ts: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kpi_name": self.kpi_name,
            "status": self.status,
            "correlation_id": self.correlation_id,
            "research": self.research,
            "extraction": self.extraction,
            "data_quality": self.data_quality,
            "gaps": self.gaps,
            "metrics": self.metrics,
            "savings_low": self.savings_low,
            "savings_medium": self.savings_medium,
            "savings_high": self.savings_high,
            "confidence": self.confidence,
            "assumptions": self.assumptions,
            "twin_patches": self.twin_patches,
            "narrative": self.narrative,
            "qa_status": self.qa_status,
            "qa_issues": self.qa_issues,
            "qa_required_fixes": self.qa_required_fixes,
            "reasoning_trace": self.reasoning_trace,
            "formula_variant": self.formula_variant,
            "variant_rationale": self.variant_rationale,
            "artifact_ids": self.artifact_ids,
            "evidence_refs": self.evidence_refs,
            "lineage_ids": self.lineage_ids,
            "started_ts": self.started_ts,
            "completed_ts": self.completed_ts,
        }


# =============================================================================
# KPI Crew Specification
# =============================================================================

@dataclass
class SpecialistAgentDef:
    """Definition for a KPI-specific specialist agent injected between Extraction and Calculation."""
    role: str
    goal: str
    backstory: str
    task_description: str
    expected_output: str
    # Callable(tools_provider) -> List[BaseTool]; if None, gets extraction tools
    tool_builder: Optional[Callable] = None
    # Insert position: "pre_calc" (after extraction, before calc) or "post_calc" (after calc, before QA)
    position: str = "pre_calc"


@dataclass
class KPICrewSpec:
    """
    Specification for a KPI crew — defines the domain-specific prompts,
    required inputs, calculation formulas, and output schema.

    Each KPI MUST populate research_goal, extraction_goal, calculation_goal,
    and qa_goal with domain-specific prompts referencing the analytical
    dimensions unique to that KPI.  Generic/empty goals are a code smell.
    """
    kpi_name: str
    display_name: str
    objective: str

    # Agent role descriptions — MUST be KPI-specific, not generic
    research_goal: str = ""
    extraction_goal: str = ""
    calculation_goal: str = ""
    qa_goal: str = ""

    # Agent backstory supplements (appended to system prompt)
    research_backstory: str = ""
    extraction_backstory: str = ""
    calculation_backstory: str = ""
    qa_backstory: str = ""

    # Required data inputs
    required_inputs: List[str] = field(default_factory=list)

    # Calculation formulas (human-readable)
    formulas: List[str] = field(default_factory=list)

    # Output metrics keys
    output_metrics: List[str] = field(default_factory=list)

    # Savings category mapping (for ROI engine)
    savings_category: str = ""

    # Domain-specific research topics
    research_topics: List[str] = field(default_factory=list)

    # Custom calculation function (deterministic kernel)
    calculation_fn: Optional[Callable] = None

    # Cross-KPI dependencies
    depends_on_kpis: List[str] = field(default_factory=list)

    # --- Extended architecture fields ---

    # Per-role tool builder overrides: Callable(tools_provider) -> List[BaseTool]
    # When set, REPLACES the default tool set for that role.
    research_tool_builder: Optional[Callable] = None
    extraction_tool_builder: Optional[Callable] = None
    calculation_tool_builder: Optional[Callable] = None
    qa_tool_builder: Optional[Callable] = None

    # Specialist agents injected into the crew beyond the standard 4
    specialist_agents: List[SpecialistAgentDef] = field(default_factory=list)


# =============================================================================
# KPI Crew Factory
# =============================================================================

class KPICrewFactory:
    """
    Factory for building and running KPI crews.
    
    All crews run via CrewAI agents with bound tools.
    The KPICrewSpec.calculation_fn is surfaced as an agent tool so the
    Calculation agent can invoke the domain formula with structured inputs.
    """

    def __init__(self, tools: LoweconexTools, event_bus: LoweconexEventBus):
        self.tools = tools
        self.event_bus = event_bus

    def build_crew(self, spec: KPICrewSpec) -> KPICrew:
        """Build a KPI crew from a specification."""
        return KPICrew(spec=spec, tools=self.tools, event_bus=self.event_bus)

    def run_crew(
        self,
        spec: KPICrewSpec,
        company_id: str,
        location_id: Optional[str] = None,
        scenario_params: Optional[Dict[str, Any]] = None,
    ) -> KPICrewResult:
        """Build and run a KPI crew, returning the result."""
        crew = self.build_crew(spec)
        return crew.run(company_id, location_id, scenario_params)


class KPICrew:
    """
    A single KPI crew instance following the mandatory structure:
    Research → Extraction → Calculation → QA (sequential).
    """

    def __init__(
        self,
        spec: KPICrewSpec,
        tools: LoweconexTools,
        event_bus: LoweconexEventBus,
    ):
        self.spec = spec
        self.tools = tools
        self.event_bus = event_bus
        self.result = KPICrewResult(kpi_name=spec.kpi_name)

    def run(
        self,
        company_id: str,
        location_id: Optional[str] = None,
        scenario_params: Optional[Dict[str, Any]] = None,
    ) -> KPICrewResult:
        """Execute the full crew pipeline via CrewAI agents."""
        self.result.started_ts = datetime.utcnow().isoformat()
        self.result.status = "running"
        correlation_id = self.result.correlation_id

        # Emit crew started
        self.event_bus.emit_crew_started(
            f"kpi_{self.spec.kpi_name}", company_id, correlation_id
        )

        try:
            return self._run_crewai(company_id, location_id, scenario_params)
        except Exception as e:
            logger.error(f"KPI crew {self.spec.kpi_name} failed: {e}", exc_info=True)
            self.result.status = "error"
            self.result.qa_issues.append({"type": "crew_error", "message": str(e)})
            self.result.completed_ts = datetime.utcnow().isoformat()
            return self.result

    # ------------------------------------------------------------------
    # Build a one-shot tool that wraps the deterministic calc function
    # so the Calculation agent can call it.
    # ------------------------------------------------------------------

    def _build_calc_fn_tool(self, company_id, location_id, scenario_params):
        """Return a BaseTool that invokes the KPICrewSpec.calculation_fn."""
        spec = self.spec
        tools_ref = self.tools

        class RunKPICalculationTool(BaseTool):
            name: str = f"run_{spec.kpi_name}_calculation"
            description: str = (
                f"Execute the {spec.display_name} domain formula. "
                "No input required — scope and parameters are pre-bound. "
                "Returns JSON with metrics, savings_low/medium/high, confidence, "
                "assumptions, narrative, twin_patches, and evidence_refs."
            )

            def _run(self, **kwargs) -> str:
                assets = tools_ref.get_assets_for_scope(company_id, location_id)
                locations = tools_ref.get_locations_for_company(company_id)
                from loweconex_platform.digital_twins.relationships import RelationshipGraph
                rel_graph = getattr(tools_ref.twin_store, '_relationship_graph', None)
                if rel_graph is None:
                    rel_graph = RelationshipGraph()
                result = spec.calculation_fn(
                    tools=tools_ref,
                    company_id=company_id,
                    location_id=location_id,
                    assets=assets,
                    locations=locations,
                    scenario_params=scenario_params or {},
                    research={},
                    relationship_graph=rel_graph,
                )
                import json as _json
                return _json.dumps(result, indent=2, default=str)

        return RunKPICalculationTool()

    def _run_crewai(
        self,
        company_id: str,
        location_id: Optional[str],
        scenario_params: Optional[Dict[str, Any]],
    ) -> KPICrewResult:
        """Run using CrewAI agents with bound tools.

        Supports KPI-specific:
        - research_goal / extraction_goal / calculation_goal / qa_goal
        - research_backstory / extraction_backstory / calculation_backstory / qa_backstory
        - Per-role tool builder overrides via {role}_tool_builder callables
        - Specialist agents injected at pre_calc or post_calc positions
        """
        kpi = self.spec.kpi_name
        system = SYSTEM_PROMPT + EVIDENCE_GROUNDING_SUFFIX

        # ---- Build per-role tool sets (KPI-specific overrides win) ----
        if self.spec.research_tool_builder:
            research_tools = self.spec.research_tool_builder(self.tools)
        else:
            research_tools = build_research_tools(self.tools)

        if self.spec.extraction_tool_builder:
            extraction_tools = self.spec.extraction_tool_builder(self.tools)
        else:
            extraction_tools = build_extraction_tools(self.tools)

        if self.spec.calculation_tool_builder:
            calc_tools = self.spec.calculation_tool_builder(self.tools)
        else:
            calc_tools = build_calculation_tools(self.tools)
        if self.spec.calculation_fn:
            calc_tools.append(
                self._build_calc_fn_tool(company_id, location_id, scenario_params)
            )

        if self.spec.qa_tool_builder:
            qa_tools = self.spec.qa_tool_builder(self.tools)
        else:
            qa_tools = build_qa_tools(self.tools)

        # ---- Pre-fetch KPI-specific research context for agent prompts ----
        corpus_snippets = get_research_snippets(kpi)
        benchmarks = get_benchmarks_for_kpi(kpi)
        corpus_summary = "\n".join(
            f"- {s['title']} ({s['citation']}): {s['summary']}"
            for s in corpus_snippets[:6]
        ) or "No curated research available for this KPI."
        benchmark_summary = ", ".join(
            f"{k}={v}" for k, v in list(benchmarks.items())[:10]
        ) or "No benchmarks loaded."
        history_stats = KPIHistoryStore.get_stats(kpi)

        # ---- Build backstory strings (KPI-specific supplements appended) ----
        research_backstory_base = (
            system + "\nYou curate and summarize standards and peer-reviewed guidance into calculation notes. "
            f"You have access to {len(corpus_snippets)} curated research snippets for this KPI. "
            f"Key benchmarks: {benchmark_summary}. "
            "Use the load_research_snippets tool to retrieve full citation details. "
            "Your output must include specific numeric ranges WITH citations for every default used."
        )
        if self.spec.research_backstory:
            research_backstory_base += "\n" + self.spec.research_backstory

        extraction_backstory_base = (
            system + "\nYou produce a validated KPI input contract from raw sources and twins. "
            "Flag data quality issues: missing fields, stale timestamps (>90 days old), "
            "sparse coverage (<50% of assets), and unit mismatches. "
            "Your gaps report directly affects calculation confidence."
        )
        if self.spec.extraction_backstory:
            extraction_backstory_base += "\n" + self.spec.extraction_backstory

        calc_backstory_base = (
            system + "\nYou are rigorous about units, baselines, and reconciliation. "
            f"Available benchmarks from research corpus: {benchmark_summary}. "
            "IMPORTANT: After invoking the calculation tool, review the result and "
            "adjust confidence DOWN if the calculation fell back to default assumptions "
            "(no real event data), and UP if grounded in actual operational data or PdM models. "
            "Document which formula variant was selected and why."
        )
        if self.spec.calculation_backstory:
            calc_backstory_base += "\n" + self.spec.calculation_backstory

        qa_history_context = ""
        if history_stats.get("sufficient_history"):
            qa_history_context = (
                f"\nHistorical baseline ({history_stats['runs']} prior runs): "
                f"savings_medium mean=${history_stats['savings_mean']:,.0f} "
                f"(±${history_stats['savings_stdev']:,.0f}), "
                f"confidence mean={history_stats['confidence_mean']:.2f} "
                f"(±{history_stats['confidence_stdev']:.2f}). "
                "Flag results that deviate >2σ from historical mean as DRIFT anomalies."
            )
        qa_backstory_base = (
            system + "\nYou block publication if results fail sanity checks. "
            "Your checks include: (1) savings ordering (low ≤ med ≤ high), "
            "(2) confidence in [0,1], (3) assumptions documented with citations, "
            "(4) benchmark range validation — savings should be plausible given "
            f"industry benchmarks: {benchmark_summary}, "
            "(5) historical drift detection — flag if savings_medium is >2σ from prior runs."
            f"{qa_history_context}"
        )
        if self.spec.qa_backstory:
            qa_backstory_base += "\n" + self.spec.qa_backstory

        # ---- Build the 4 core agents ----
        research_agent = Agent(
            role=f"{self.spec.display_name} Research Analyst",
            goal=self.spec.research_goal or (
                f"Curate benchmark ranges, formulas, and standards references for {kpi}. "
                f"Validate that calculation defaults align with the following literature:\n{corpus_summary}"
            ),
            backstory=research_backstory_base,
            tools=research_tools,
            allow_delegation=False,
            verbose=True,
        )

        extraction_agent = Agent(
            role=f"{self.spec.display_name} Data Extraction Lead",
            goal=self.spec.extraction_goal or f"Extract, clean, and feature-engineer all required inputs for {kpi}.",
            backstory=extraction_backstory_base,
            tools=extraction_tools,
            allow_delegation=False,
            verbose=True,
        )

        calculation_agent = Agent(
            role=f"{self.spec.display_name} Calculation Lead",
            goal=self.spec.calculation_goal or (
                f"Compute KPI metrics, savings ranges, confidence bounds for {kpi}. "
                "Select the appropriate formula variant based on data availability."
            ),
            backstory=calc_backstory_base,
            tools=calc_tools,
            allow_delegation=False,
            verbose=True,
        )

        qa_agent = Agent(
            role=f"{self.spec.display_name} QA & Reconciliation",
            goal=self.spec.qa_goal or (
                f"Detect outliers, unit errors, leakage/double counting, and reconciliation gaps for {kpi}. "
                "Perform anomaly detection: compare current results against historical runs and flag drift."
            ),
            backstory=qa_backstory_base,
            tools=qa_tools,
            allow_delegation=False,
            verbose=True,
        )

        # ---- Build specialist agents (KPI-specific) ----
        specialist_pre_calc = []
        specialist_post_calc = []
        for sa_def in self.spec.specialist_agents:
            sa_tools = extraction_tools  # default
            if sa_def.tool_builder:
                sa_tools = sa_def.tool_builder(self.tools)
            sa = Agent(
                role=sa_def.role,
                goal=sa_def.goal,
                backstory=system + "\n" + sa_def.backstory,
                tools=sa_tools,
                allow_delegation=False,
                verbose=True,
            )
            sa_task = Task(
                description=sa_def.task_description,
                expected_output=sa_def.expected_output,
                agent=sa,
            )
            if sa_def.position == "post_calc":
                specialist_post_calc.append((sa, sa_task))
            else:
                specialist_pre_calc.append((sa, sa_task))

        # ---- Build scope description ----
        scope_desc = f"company={company_id}"
        if location_id:
            scope_desc += f", location={location_id}"
        if scenario_params:
            scope_desc += f", scenario_params={json.dumps(scenario_params)}"

        # ---- Build tasks for core 4 ----
        t1 = Task(
            description=(
                f"Use the load_research_snippets tool to pull calculation standards and benchmarks for '{kpi}'. "
                f"For each research topic in {self.spec.research_topics}, retrieve and summarize the snippets. "
                f"Cross-reference the formulas: {self.spec.formulas}. "
                f"Identify the literature-grounded default values for each calculation parameter. "
                f"Flag any parameters where no authoritative source is available. "
                f"Scope: {scope_desc}"
            ),
            expected_output=(
                'JSON: {"kpi_name", "formulas[]", "benchmarks": {param: {value, source, citation}}, '
                '"required_inputs[]", "citations[]", "ungrounded_params[]"}'
            ),
            agent=research_agent,
        )
        t2 = Task(
            description=(
                f"Build a KPI input contract for '{kpi}' at scope: {scope_desc}. "
                f"Use get_assets_for_scope and get_locations_for_company to enumerate twins. "
                f"Use query_events to check data availability for: {self.spec.required_inputs}. "
                f"For each required input, report: available (bool), record_count, freshness (days since newest), "
                f"coverage_pct (assets with data / total assets). "
                f"Classify gaps as low/medium/high severity based on impact on calculation confidence."
            ),
            expected_output=(
                'JSON: {"kpi_name", "scope", "inputs": {name: {available, count, freshness_days, coverage_pct}}, '
                '"data_quality_score": 0-1, "gaps[]": [{input, severity, impact}]}'
            ),
            agent=extraction_agent,
        )
        t3 = Task(
            description=(
                f"Compute KPI metrics for '{kpi}' by invoking the run_{kpi}_calculation tool. "
                f"BEFORE invoking, review the extraction results to determine formula variant: "
                f"(a) DATA-DRIVEN: if real event/timeseries data has coverage >50%, use data-driven baselines; "
                f"(b) BENCHMARK-DRIVEN: if data is sparse, rely on research corpus defaults; "
                f"(c) PDM-GROUNDED: if pdm_asset_details exist in scenario_params, prefer PdM model outputs. "
                f"AFTER invoking, review the result and: "
                f"1. Adjust confidence based on which variant was used (data-driven=+0.1, benchmark=-0.1, pdm=+0.15). "
                f"2. Apply twin_patches via write_twin. "
                f"3. Persist output via store_artifact. "
                f"4. Document which variant was selected and why. "
                f"Formulas: {self.spec.formulas}"
            ),
            expected_output=(
                'JSON: {"kpi_name", "formula_variant": "data_driven|benchmark_driven|pdm_grounded", '
                '"metrics", "savings_low", "savings_medium", "savings_high", "confidence", '
                '"assumptions", "twin_patches[]", "variant_rationale"}'
            ),
            agent=calculation_agent,
        )
        t4 = Task(
            description=(
                f"Run comprehensive QA for '{kpi}': "
                f"1. STRUCTURAL: verify savings_low ≤ savings_medium ≤ savings_high, confidence ∈ [0,1], no negative savings. "
                f"2. ASSUMPTIONS: verify every assumption cites a source (standard, benchmark, or data). "
                f"3. BENCHMARK PLAUSIBILITY: compare savings_medium against industry benchmarks — "
                f"   flag if outside ±2× the expected range for this KPI type. "
                f"4. HISTORICAL DRIFT: compare against prior runs (if available) — "
                f"   flag if savings_medium deviates >2σ from historical mean. "
                f"5. CROSS-CHECK: use read_twin and query_events to spot-check 2-3 source data points. "
                f"Approve only if all structural checks pass AND no blocker-severity issues remain."
            ),
            expected_output=(
                'JSON: {"kpi_name", "status": "APPROVED|REJECTED", '
                '"issues[]": [{type, message, severity}], "required_fixes[]", '
                '"drift_analysis": {current_vs_mean, sigma_deviation}, '
                '"benchmark_check": {within_range: bool, expected_range}}'
            ),
            agent=qa_agent,
        )

        # ---- Assemble agent + task lists with specialists inserted ----
        agents = [research_agent, extraction_agent]
        tasks = [t1, t2]

        for sa, sa_task in specialist_pre_calc:
            agents.append(sa)
            tasks.append(sa_task)

        agents.append(calculation_agent)
        tasks.append(t3)

        for sa, sa_task in specialist_post_calc:
            agents.append(sa)
            tasks.append(sa_task)

        agents.append(qa_agent)
        tasks.append(t4)

        crew = Crew(
            agents=agents,
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
        )

        crew_output = crew.kickoff(inputs={
            "company_id": company_id,
            "location_id": location_id or "",
            "kpi_name": kpi,
        })

        # ---- Capture per-task reasoning trace ----
        task_labels = ["research", "extraction"]
        for _ in specialist_pre_calc:
            task_labels.append("specialist_pre_calc")
        task_labels.append("calculation")
        for _ in specialist_post_calc:
            task_labels.append("specialist_post_calc")
        task_labels.append("qa")

        self._extract_reasoning_trace(crew_output, tasks, task_labels)
        self._parse_crew_output(crew_output, company_id, location_id)
        return self.result

    def _run_qa_checks(self) -> List[Dict[str, Any]]:
        """Run standard QA checks on the calculation result."""
        issues = []

        # Check savings consistency
        if self.result.savings_low > self.result.savings_medium:
            issues.append({
                "type": "savings_ordering",
                "message": "Low savings exceeds medium savings",
                "severity": "blocker",
            })
        if self.result.savings_medium > self.result.savings_high:
            issues.append({
                "type": "savings_ordering",
                "message": "Medium savings exceeds high savings",
                "severity": "blocker",
            })

        # Check for negative savings
        if self.result.savings_low < 0:
            issues.append({
                "type": "negative_savings",
                "message": "Negative low savings estimate",
                "severity": "warning",
            })

        # Check confidence bounds
        if self.result.confidence < 0 or self.result.confidence > 1:
            issues.append({
                "type": "confidence_range",
                "message": f"Confidence {self.result.confidence} out of [0,1] range",
                "severity": "blocker",
            })

        # Check data gaps
        high_gaps = [g for g in self.result.gaps if g.get("severity") == "high"]
        if high_gaps:
            issues.append({
                "type": "data_gaps",
                "message": f"{len(high_gaps)} high-severity data gaps detected",
                "severity": "warning",
            })

        # Check assumptions exist
        if not self.result.assumptions:
            issues.append({
                "type": "missing_assumptions",
                "message": "No assumptions documented",
                "severity": "warning",
            })

        return issues

    def _extract_reasoning_trace(
        self,
        crew_output: Any,
        tasks: List[Any],
        task_labels: List[str],
    ):
        """
        Extract per-task reasoning from CrewAI output.

        CrewAI stores per-task outputs on task.output (TaskOutput) objects.
        We capture both the raw text (chain-of-thought) and any structured
        JSON the agent produced. This preserves the LLM's reasoning for
        lineage and auditability.
        """
        trace = []
        for i, task in enumerate(tasks):
            label = task_labels[i] if i < len(task_labels) else f"task_{i}"
            entry = {
                "step": i,
                "role": label,
                "agent_role": getattr(task, 'agent', None) and getattr(task.agent, 'role', label),
                "raw_output": "",
                "structured_output": None,
                "reasoning_excerpt": "",
            }

            # CrewAI >=0.28 stores TaskOutput on task.output after kickoff
            task_output = getattr(task, 'output', None)
            if task_output is not None:
                raw_text = ""
                if hasattr(task_output, 'raw'):
                    raw_text = str(task_output.raw)
                elif hasattr(task_output, 'result'):
                    raw_text = str(task_output.result)
                else:
                    raw_text = str(task_output)

                entry["raw_output"] = raw_text

                # Try to extract structured JSON from the raw output
                try:
                    structured = json.loads(raw_text)
                    entry["structured_output"] = structured
                except (json.JSONDecodeError, TypeError):
                    # Fallback: extract JSON substring between first '{' and last '}'
                    first = raw_text.find('{')
                    last = raw_text.rfind('}')
                    if first >= 0 and last > first:
                        try:
                            structured = json.loads(raw_text[first:last + 1])
                            entry["structured_output"] = structured
                        except (json.JSONDecodeError, TypeError):
                            pass

                # Extract reasoning excerpt: text before the first '{' (the thinking)
                brace_idx = raw_text.find('{')
                if brace_idx > 20:
                    entry["reasoning_excerpt"] = raw_text[:brace_idx].strip()[:500]
                elif not entry["structured_output"]:
                    entry["reasoning_excerpt"] = raw_text[:500]

                # Capture formula_variant and variant_rationale from calc task
                if label == "calculation" and entry["structured_output"]:
                    self.result.formula_variant = entry["structured_output"].get(
                        "formula_variant", ""
                    )
                    self.result.variant_rationale = entry["structured_output"].get(
                        "variant_rationale", ""
                    )

            trace.append(entry)

        self.result.reasoning_trace = trace
        logger.debug(f"[{self.spec.kpi_name}] Captured reasoning trace: {len(trace)} steps")

    def _parse_crew_output(self, crew_output, company_id: str = "", location_id: Optional[str] = None):
        """Parse CrewAI crew output into KPICrewResult and emit events."""
        kpi = self.spec.kpi_name
        correlation_id = self.result.correlation_id

        try:
            if hasattr(crew_output, 'raw'):
                raw = crew_output.raw
            elif hasattr(crew_output, 'result'):
                raw = str(crew_output.result)
            else:
                raw = str(crew_output)

            # Try to parse as JSON
            try:
                data = json.loads(raw)
                self.result.metrics = data.get("metrics", {})
                self.result.savings_low = float(data.get("savings_low", 0))
                self.result.savings_medium = float(data.get("savings_medium", 0))
                self.result.savings_high = float(data.get("savings_high", 0))
                self.result.confidence = float(data.get("confidence", 0))
                self.result.assumptions = data.get("assumptions", [])
                self.result.narrative = data.get("narrative", "")
                self.result.twin_patches = data.get("twin_patches", [])
                self.result.evidence_refs = data.get("evidence_refs", [])
                # Capture variant fields from final output if not already set from trace
                if not self.result.formula_variant:
                    self.result.formula_variant = data.get("formula_variant", "")
                if not self.result.variant_rationale:
                    self.result.variant_rationale = data.get("variant_rationale", "")
                qa_status = data.get("status", "approved")
                if isinstance(qa_status, str):
                    qa_status = qa_status.lower()
                self.result.qa_status = qa_status
            except json.JSONDecodeError:
                self.result.narrative = raw
                self.result.qa_status = "approved"

        except Exception as e:
            logger.error(f"Failed to parse crew output: {e}")
            self.result.status = "error"
            self.result.completed_ts = datetime.utcnow().isoformat()
            return

        # Run local QA checks as a safety net
        qa_issues = self._run_qa_checks()
        self.result.qa_issues.extend(qa_issues)
        has_blockers = any(i.get("severity") == "blocker" for i in self.result.qa_issues)
        if has_blockers:
            self.result.qa_status = "rejected"
        self.result.status = "approved" if self.result.qa_status == "approved" else "rejected"

        # Emit KPI computed event
        self.event_bus.emit_kpi_computed(
            kpi_name=kpi,
            company_id=company_id,
            correlation_id=correlation_id,
            payload=self.result.to_dict(),
            location_id=location_id,
        )

        # Store final artifact
        art_id = self.tools.store_artifact("kpi_result", self.result.to_dict(), f"kpi_{kpi}")
        self.result.artifact_ids.append(art_id)

        # Store reasoning trace as a separate lineage artifact for auditability
        if self.result.reasoning_trace:
            trace_artifact = {
                "kpi_name": kpi,
                "correlation_id": correlation_id,
                "formula_variant": self.result.formula_variant,
                "variant_rationale": self.result.variant_rationale,
                "steps": self.result.reasoning_trace,
                "ts": datetime.utcnow().isoformat(),
            }
            trace_id = self.tools.store_artifact(
                "reasoning_trace", trace_artifact, f"trace_{kpi}"
            )
            self.result.artifact_ids.append(trace_id)
            self.result.lineage_ids.append(trace_id)
            logger.info(f"[{kpi}] Stored reasoning trace artifact: {trace_id}")

        # Emit crew completed
        self.event_bus.emit_crew_completed(
            f"kpi_{kpi}", company_id, correlation_id, self.result.artifact_ids
        )

        self.result.completed_ts = datetime.utcnow().isoformat()

        # Record for historical drift detection
        KPIHistoryStore.record(kpi, {
            "savings_medium": self.result.savings_medium,
            "confidence": self.result.confidence,
            "status": self.result.status,
            "ts": self.result.completed_ts,
        })

        logger.info(f"[{kpi}] Completed: status={self.result.status}, savings_med=${self.result.savings_medium:,.0f}")
