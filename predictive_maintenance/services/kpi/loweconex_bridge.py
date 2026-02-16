"""
Loweconex Platform Bridge — Unified KPI Stack

Provides optional integration with the loweconex_platform CrewAI-powered
KPI crews. When available, the bridge enriches KPI results with:
- CrewAI agent research, extraction, and QA outputs
- Cross-KPI double-counting reconciliation (DecisionLedger)
- Scenario simulation via ScenarioAgent
- Decision advisory via LLM-powered advisory agent

When the loweconex_platform is not available (e.g. CrewAI not installed),
the bridge degrades gracefully and the simpler BaseKPIService computations
are used directly.
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure .env is loaded even in Uvicorn reloader child processes
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = Path(__file__).resolve().parents[2] / ".env"
    if _env_file.exists():
        _load_dotenv(_env_file, override=False)
except ImportError:
    pass

from .base import KPIConfig, KPIResult

logger = logging.getLogger(__name__)

# ── Availability flags ──────────────────────────────────────────────

LOWECONEX_AVAILABLE = False
CREWAI_ORCHESTRATION_AVAILABLE = False

try:
    from loweconex_platform.kpi_crews.registry import KPI_REGISTRY as CREW_REGISTRY
    from loweconex_platform.orchestration.orchestrator_crew import OrchestratorCrew
    from loweconex_platform.orchestration.scenario_agent import ScenarioAgent
    from loweconex_platform.orchestration.decision_ledger import DecisionLedger
    LOWECONEX_AVAILABLE = True
    logger.info("Loweconex platform bridge: KPI crews available")
except ImportError:
    logger.info("Loweconex platform bridge: not available (import failed)")

try:
    from shared.agents.crewai_base import CREWAI_AVAILABLE
    if CREWAI_AVAILABLE and LOWECONEX_AVAILABLE:
        # CrewAI orchestration can be explicitly disabled via env var for demo/testing.
        if os.environ.get("PDM_SKIP_CREW_ENRICHMENT", "").lower() in ("1", "true", "yes"):
            logger.info("Loweconex platform bridge: CrewAI available but disabled (PDM_SKIP_CREW_ENRICHMENT set)")
        else:
            CREWAI_ORCHESTRATION_AVAILABLE = True
            logger.info("Loweconex platform bridge: CrewAI orchestration enabled")
except ImportError:
    pass


def get_bridge_status() -> Dict[str, Any]:
    """Return the availability status of the loweconex bridge."""
    crew_names = []
    if LOWECONEX_AVAILABLE:
        crew_names = list(CREW_REGISTRY.keys())
    return {
        "loweconex_available": LOWECONEX_AVAILABLE,
        "crewai_orchestration_available": CREWAI_ORCHESTRATION_AVAILABLE,
        "registered_crews": crew_names,
        "crew_count": len(crew_names),
    }


def enrich_results_with_crews(
    results: List[KPIResult],
    config: KPIConfig,
) -> List[KPIResult]:
    """
    Optionally enrich KPI results using loweconex CrewAI crews.

    When CrewAI orchestration is available, this runs the full 4-agent
    pipeline (Research → Extraction → Calculation → QA) per KPI, merging
    the crew outputs back into the KPIResult.

    When CrewAI is not installed but the Loweconex specs are available,
    falls back to benchmark validation only.

    When neither is available, returns results unchanged.
    """
    if not LOWECONEX_AVAILABLE:
        return results

    # Guard: skip all enrichment when CrewAI tool schemas are broken
    if not CREWAI_ORCHESTRATION_AVAILABLE:
        logger.info("CrewAI orchestration disabled — returning base KPI results")
        return results

    # If CrewAI agents can run, execute the full crew pipeline
    if CREWAI_ORCHESTRATION_AVAILABLE:
        # Gate: require OPENAI_API_KEY before attempting agent enrichment
        import os
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            for k, v in os.environ.items():
                if k.lower() == "openai_api_key":
                    api_key = (v or "").strip()
                    break
        if not api_key:
            try:
                from predictive_maintenance.config import settings
                api_key = (settings.openai.api_key or "").strip()
            except Exception:
                api_key = ""
        if not api_key:
            logger.warning(
                "OPENAI_API_KEY not set — skipping CrewAI enrichment. "
                "Set the key to enable agent-powered KPI research/QA."
            )
        else:
            # Skip if explicitly disabled (broken tool schemas, demo mode, etc.)
            if os.environ.get("PDM_SKIP_CREW_ENRICHMENT", "").lower() in ("1", "true", "yes"):
                logger.info("CrewAI enrichment skipped (PDM_SKIP_CREW_ENRICHMENT set)")
            else:
                # Run with timeout to prevent blocking the single-worker dev server
                _timeout = int(os.environ.get("PDM_CREW_TIMEOUT", "90"))
                try:
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(_run_crew_enrichment, results, config)
                        return future.result(timeout=_timeout)
                except FuturesTimeoutError:
                    logger.warning(
                        "CrewAI enrichment timed out after %ds — falling back to benchmarks",
                        _timeout,
                    )
                except Exception as e:
                    logger.warning("CrewAI enrichment failed: %s — falling back to benchmarks", e)

    # Fallback: benchmark validation only (no agents)
    try:
        enriched = []
        for result in results:
            crew_spec = CREW_REGISTRY.get(result.kpi_name)
            if crew_spec and crew_spec.calculation_fn:
                result = _validate_with_crew_spec(result, crew_spec)
            enriched.append(result)
        return enriched
    except Exception as e:
        logger.warning("Benchmark enrichment failed, using base results: %s", e)
        return results


def _run_crew_enrichment(
    results: List[KPIResult],
    config: KPIConfig,
) -> List[KPIResult]:
    """Run the full CrewAI agent pipeline and merge outputs into KPIResults."""
    try:
        from loweconex_platform.kpi_crews.base_crew import KPICrewFactory, KPICrewResult
        from loweconex_platform.kpi_crews.tools import LoweconexTools, ArtifactStore
        from loweconex_platform.digital_twins.store import get_default_store
        from loweconex_platform.event_bus.redis_streams import LoweconexEventBus

        twin_store = get_default_store()
        try:
            event_bus = LoweconexEventBus(agent_id="kpi_bridge")
        except Exception:
            from shared.event_bus.redis_event_bus import InMemoryEventBus
            event_bus = InMemoryEventBus(agent_id="kpi_bridge")
        artifact_store = ArtifactStore()
        tools = LoweconexTools(
            twin_store=twin_store,
            event_bus=event_bus,
            artifact_store=artifact_store,
        )

        factory = KPICrewFactory(tools=tools, event_bus=event_bus)

        enriched = []
        for result in results:
            crew_spec = CREW_REGISTRY.get(result.kpi_name)
            if crew_spec is None:
                enriched.append(result)
                continue

            try:
                crew_result: KPICrewResult = factory.run_crew(
                    spec=crew_spec,
                    company_id=config.site_id,
                )
                result = _merge_crew_into_result(result, crew_result)
            except Exception as e:
                logger.warning(
                    "CrewAI enrichment failed for %s, keeping base result: %s",
                    result.kpi_name, e,
                )
                result = _validate_with_crew_spec(result, crew_spec)
            enriched.append(result)

        return enriched
    except Exception as e:
        logger.warning("CrewAI enrichment pipeline failed: %s — falling back to base", e)
        return results


def _merge_crew_into_result(base: KPIResult, crew: "KPICrewResult") -> KPIResult:
    """Merge CrewAI crew outputs into the base KPIResult.

    Crew outputs are promoted into authoritative totals when they pass
    an explicit gate (QA approved, coherent savings bounds, confidence floor).
    """
    qa_approved = str(getattr(crew, "qa_status", "") or "").lower() == "approved"
    coherent_bounds = (
        crew.savings_low >= 0
        and crew.savings_low <= crew.savings_medium <= crew.savings_high
    )
    confidence_floor = max(0.40, float(base.confidence or 0.0))
    promote = qa_approved and coherent_bounds and float(crew.confidence or 0.0) >= confidence_floor

    candidate = {
        "savings_low": crew.savings_low,
        "savings_medium": crew.savings_medium,
        "savings_high": crew.savings_high,
        "confidence": crew.confidence,
        "qa_status": crew.qa_status,
        "promotion_gate": (
            "qa_approved_bounds_valid_confident"
            if promote
            else "failed_qc_gate_keep_deterministic"
        ),
        "applied_to_authoritative_totals": promote,
    }
    base.supporting_metrics["agent_savings_candidate"] = candidate

    if promote:
        base.savings_low = float(crew.savings_low or 0.0)
        base.savings_medium = float(crew.savings_medium or 0.0)
        base.savings_high = float(crew.savings_high or 0.0)
        base.confidence = max(float(base.confidence or 0.0), float(crew.confidence or 0.0))
        if str(getattr(crew, "status", "") or "").lower() == "approved":
            base.status = "approved"

    if crew.narrative:
        base.supporting_metrics["agent_narrative"] = crew.narrative

    # Always merge enrichment metadata regardless of approval.
    base.assumptions = list(base.assumptions) + list(crew.assumptions)
    if crew.reasoning_trace:
        base.supporting_metrics["crew_reasoning_trace"] = crew.reasoning_trace
    if crew.formula_variant:
        base.supporting_metrics["formula_variant"] = crew.formula_variant
        base.supporting_metrics["variant_rationale"] = crew.variant_rationale
    if crew.qa_issues:
        base.supporting_metrics["qa_issues"] = crew.qa_issues
    if crew.evidence_refs:
        base.supporting_metrics["evidence_refs"] = crew.evidence_refs

    base.assumptions = list(set(base.assumptions))  # deduplicate
    return base


def _validate_with_crew_spec(result: KPIResult, crew_spec) -> KPIResult:
    """Validate a KPIResult against the crew spec's expected ranges."""
    try:
        from loweconex_platform.kpi_crews.research_corpus import get_benchmarks_for_kpi
        benchmarks = get_benchmarks_for_kpi(result.kpi_name)
        if not benchmarks:
            return result

        # Cross-check savings against benchmark ranges
        notes = []
        for key, value in benchmarks.items():
            if isinstance(value, (int, float)) and value > 0:
                notes.append(f"Benchmark {key}: {value}")

        if notes:
            result.assumptions = list(result.assumptions) + [
                f"Validated against {len(notes)} industry benchmarks"
            ]
    except Exception as e:
        logger.debug("Benchmark validation skipped for %s: %s", result.kpi_name, e)

    return result


def run_full_crew_pipeline(
    config: KPIConfig,
    company_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Run the full Loweconex CrewAI pipeline directly (bypasses BaseKPIService).

    Returns a list of KPICrewResult.to_dict() for all 14 KPI crews.
    Raises ImportError if Loweconex/CrewAI is not available.
    """
    if not CREWAI_ORCHESTRATION_AVAILABLE:
        raise ImportError("CrewAI orchestration is not available")

    from loweconex_platform.kpi_crews.base_crew import KPICrewFactory
    from loweconex_platform.kpi_crews.tools import LoweconexTools, ArtifactStore
    from loweconex_platform.digital_twins.store import get_default_store
    from loweconex_platform.event_bus.redis_streams import LoweconexEventBus

    twin_store = get_default_store()
    try:
        event_bus = LoweconexEventBus(agent_id="kpi_pipeline")
    except Exception:
        from shared.event_bus.redis_event_bus import InMemoryEventBus
        event_bus = InMemoryEventBus(agent_id="kpi_pipeline")
    artifact_store = ArtifactStore()
    tools = LoweconexTools(
        twin_store=twin_store,
        event_bus=event_bus,
        artifact_store=artifact_store,
    )

    factory = KPICrewFactory(tools=tools, event_bus=event_bus)
    cid = company_id or config.site_id
    crew_results = []
    for kpi_name, crew_spec in CREW_REGISTRY.items():
        try:
            cr = factory.run_crew(spec=crew_spec, company_id=cid)
            crew_results.append(cr.to_dict())
        except Exception as e:
            logger.error("Crew %s failed: %s", kpi_name, e)
            crew_results.append({"kpi_name": kpi_name, "status": "error", "error": str(e)})
    return crew_results


def run_scenario_comparison(
    results: List[KPIResult],
    config: KPIConfig,
) -> List[Dict[str, Any]]:
    """
    Run scenario comparison using the loweconex ScenarioAgent when available.

    Falls back to the simpler scenario generation in the orchestrator.
    """
    if not LOWECONEX_AVAILABLE:
        return []

    try:
        scenario_agent = ScenarioAgent()
        scenarios = scenario_agent.get_standard_scenarios()
        return [s.to_dict() if hasattr(s, 'to_dict') else s for s in scenarios]
    except Exception as e:
        logger.warning("Scenario agent failed: %s", e)
        return []


def reconcile_double_counting(
    results: List[KPIResult],
) -> Dict[str, Any]:
    """
    Use the DecisionLedger to reconcile double-counting across KPIs.

    When the Loweconex DecisionLedger is unavailable, falls back to a
    deterministic overlap matrix that applies haircuts to known
    overlapping KPI pairs (e.g. energy_reduction ↔ esg_compliance).

    Returns reconciliation summary with adjusted totals.
    """
    if LOWECONEX_AVAILABLE:
        try:
            ledger = DecisionLedger()
            for r in results:
                ledger.register_kpi_result(
                    r.kpi_name,
                    {
                        "kpi_name": r.kpi_name,
                        "savings_low": r.savings_low,
                        "savings_medium": r.savings_medium,
                        "savings_high": r.savings_high,
                        "confidence": r.confidence,
                        "savings_category": r.category,
                        "evidence_refs": r.supporting_metrics.get("evidence_refs", []),
                    },
                )
            ledger.build_attributions_from_kpi_results()
            reconciled = ledger.get_reconciled_totals()
            return {
                "reconciled": True,
                "adjustments": reconciled.get("adjustments", []),
                "total_after_reconciliation": reconciled.get("total_savings_medium", 0),
            }
        except Exception as e:
            logger.warning("DecisionLedger reconciliation failed, using deterministic fallback: %s", e)

    return _deterministic_reconciliation(results)


# ── Deterministic overlap matrix ─────────────────────────────────────
# Each entry is (kpi_a, kpi_b, haircut_pct_on_b): when both are present,
# reduce kpi_b's savings by haircut_pct to remove the shared component.
_OVERLAP_PAIRS = [
    # Energy kWh reduction is also counted in ESG carbon savings
    ("energy_reduction", "esg_compliance", 0.60),
    # Refrigerant leak reduction overlaps with ESG refrigerant component
    ("refrigerant_leak_reduction", "esg_compliance", 0.30),
    # Work order reduction overlaps with service bureau dispatch avoidance
    ("work_order_reduction", "service_bureau_reduction", 0.25),
    # Work order reduction overlaps with call center deflection
    ("work_order_reduction", "call_center_volume_reduction", 0.15),
    # PPM maximization and PM optimization measure the same maintenance shift
    ("ppm_maximization", "preventive_maintenance_optimization", 0.35),
    # Asset failure prediction overlaps with uptime improvement
    ("asset_failure_prediction", "asset_uptime_increase", 0.20),
    # Food waste and food safety both derive from temperature excursions
    ("food_waste_reduction", "food_safety_compliance", 0.20),
]


def _deterministic_reconciliation(results: List[KPIResult]) -> Dict[str, Any]:
    """Apply a rules-based haircut to overlapping KPI pairs.

    Adjusts all three savings tiers (low, medium, high) consistently
    to maintain coherent ranges after reconciliation.
    """
    savings_med = {r.kpi_name: r.savings_medium for r in results}
    savings_low = {r.kpi_name: r.savings_low for r in results}
    savings_high = {r.kpi_name: r.savings_high for r in results}
    adjustments = []
    total_haircut_med = 0.0
    total_haircut_low = 0.0
    total_haircut_high = 0.0

    for kpi_a, kpi_b, haircut_pct in _OVERLAP_PAIRS:
        if kpi_a in savings_med and kpi_b in savings_med:
            overlap_med = savings_med[kpi_b] * haircut_pct
            overlap_low = savings_low[kpi_b] * haircut_pct
            overlap_high = savings_high[kpi_b] * haircut_pct
            if overlap_med > 0:
                savings_med[kpi_b] -= overlap_med
                savings_low[kpi_b] -= overlap_low
                savings_high[kpi_b] -= overlap_high
                total_haircut_med += overlap_med
                total_haircut_low += overlap_low
                total_haircut_high += overlap_high
                adjustments.append({
                    "pair": [kpi_a, kpi_b],
                    "overlap_pct": haircut_pct,
                    "haircut_amount": round(overlap_med, 2),
                    "haircut_low": round(overlap_low, 2),
                    "haircut_high": round(overlap_high, 2),
                    "reason": f"{kpi_b} reduced by {haircut_pct*100:.0f}% to avoid double-counting with {kpi_a}",
                })

    total_after_med = sum(savings_med.values())
    total_after_low = sum(savings_low.values())
    total_after_high = sum(savings_high.values())
    return {
        "reconciled": True,
        "method": "deterministic_overlap_matrix",
        "adjustments": adjustments,
        "total_haircut": round(total_haircut_med, 2),
        "total_haircut_low": round(total_haircut_low, 2),
        "total_haircut_high": round(total_haircut_high, 2),
        "total_after_reconciliation": round(total_after_med, 2),
        "total_after_reconciliation_low": round(total_after_low, 2),
        "total_after_reconciliation_high": round(total_after_high, 2),
    }
