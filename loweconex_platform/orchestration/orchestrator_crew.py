"""
Orchestrator Crew — top-level crew that coordinates all KPI crews,
runs scenarios, resolves double-counting, and produces the composite report.

Responsibilities:
1. Build run plan and trigger KPI crews
2. Gather outputs into Decision Ledger
3. Resolve overlaps/double-counting
4. Run scenario simulations
5. Produce ranked recommendations
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from loweconex_platform.config import PlatformConfig
from loweconex_platform.digital_twins.store import TwinStore
from loweconex_platform.event_bus.events import EventType, create_envelope
from loweconex_platform.event_bus.redis_streams import LoweconexEventBus
from loweconex_platform.kpi_crews.base_crew import KPICrewFactory, KPICrewResult
from loweconex_platform.kpi_crews.registry import KPI_REGISTRY
from loweconex_platform.kpi_crews.tools import LoweconexTools
from loweconex_platform.orchestration.decision_ledger import DecisionLedger, Recommendation
from loweconex_platform.orchestration.portfolio_optimizer import (
    OptimizationConstraints,
    PortfolioOptimizer,
)
from loweconex_platform.orchestration.scenario_agent import (
    ScenarioAgent,
    ScenarioParameters,
)
from loweconex_platform.digital_twins.relationships import RelationshipGraph
from loweconex_platform.orchestration.decision_advisory_agent import (
    DecisionAdvisoryAgent,
    AdvisoryOutput,
)
from loweconex_platform.pdm_bridge import PdMBridge

# --- Enterprise module imports (graceful degradation) ---
try:
    from loweconex_platform.lineage.lineage_tracker import LineageTracker, DatasetFacet, DatasetType, JobType
    LINEAGE_AVAILABLE = True
except ImportError:
    LINEAGE_AVAILABLE = False

try:
    from loweconex_platform.data_quality.quality_engine import DataQualityEngine, GateDecision
    DQ_AVAILABLE = True
except ImportError:
    DQ_AVAILABLE = False

try:
    from loweconex_platform.benchmarking.benchmark_engine import BenchmarkEngine
    BENCHMARK_AVAILABLE = True
except ImportError:
    BENCHMARK_AVAILABLE = False

try:
    from loweconex_platform.mlops.model_registry import ModelRegistry, ModelVersion, ModelStage, ModelType
    MLOPS_AVAILABLE = True
except ImportError:
    MLOPS_AVAILABLE = False

try:
    from loweconex_platform.agent_ops.agent_ops_engine import AgentHealthMonitor
    AGENT_OPS_AVAILABLE = True
except ImportError:
    AGENT_OPS_AVAILABLE = False

try:
    from loweconex_platform.operating_model.operating_model import (
        ExceptionManager, ExceptionRecord, ExceptionType, ExceptionPriority,
    )
    OPERATING_MODEL_AVAILABLE = True
except ImportError:
    OPERATING_MODEL_AVAILABLE = False

try:
    from loweconex_platform.capex.engine import CapExEngine
    CAPEX_AVAILABLE = True
except ImportError:
    CAPEX_AVAILABLE = False

try:
    from loweconex_platform.execution.execution_engine import (
        ExecutionEngine, RecommendationRecord, RecommendationTracker,
    )
    EXECUTION_AVAILABLE = True
except ImportError:
    EXECUTION_AVAILABLE = False

try:
    from loweconex_platform.ownership.crew.decision_crew import OwnershipDecisionCrew
    OWNERSHIP_CREW_AVAILABLE = True
except ImportError:
    OWNERSHIP_CREW_AVAILABLE = False

logger = logging.getLogger(__name__)

from shared.agents.crewai_base import (
    Agent, Crew, Process, Task, CREWAI_AVAILABLE,
)


class OrchestratorCrew:
    """
    Top-level orchestrator that runs the full analytics pipeline:
    
    1. Trigger KPI crews (parallel or sequential)
    2. Collect results into Decision Ledger
    3. Run 3 scenarios (conservative, expected, aggressive)
    4. Optimize portfolio under constraints
    5. Generate ranked recommendations
    6. Produce composite report artifacts
    """

    def __init__(
        self,
        config: PlatformConfig,
        twin_store: TwinStore,
        event_bus: LoweconexEventBus,
        tools: Optional[LoweconexTools] = None,
        pdm_bridge: Optional[PdMBridge] = None,
        # Enterprise module overrides (auto-created if None)
        lineage_tracker: Optional[Any] = None,
        dq_engine: Optional[Any] = None,
        benchmark_engine: Optional[Any] = None,
        model_registry: Optional[Any] = None,
        health_monitor: Optional[Any] = None,
        exception_manager: Optional[Any] = None,
        execution_engine: Optional[Any] = None,
    ):
        self.config = config
        self.twin_store = twin_store
        self.event_bus = event_bus
        self.tools = tools or LoweconexTools(twin_store, event_bus)
        self.kpi_factory = KPICrewFactory(self.tools, event_bus)
        self.scenario_agent = ScenarioAgent()
        self.portfolio_optimizer = PortfolioOptimizer()
        self.pdm_bridge = pdm_bridge

        # --- Enterprise governance modules ---
        self.lineage = lineage_tracker or (LineageTracker() if LINEAGE_AVAILABLE else None)
        self.dq_engine = dq_engine or (DataQualityEngine() if DQ_AVAILABLE else None)
        self.benchmark_engine = benchmark_engine or (BenchmarkEngine() if BENCHMARK_AVAILABLE else None)
        self.model_registry = model_registry or (ModelRegistry() if MLOPS_AVAILABLE else None)
        self.health_monitor = health_monitor or (AgentHealthMonitor() if AGENT_OPS_AVAILABLE else None)
        self.exception_manager = exception_manager or (ExceptionManager() if OPERATING_MODEL_AVAILABLE else None)
        self.execution_engine = execution_engine or (ExecutionEngine() if EXECUTION_AVAILABLE else None)

        # Results storage
        self._kpi_results: Dict[str, KPICrewResult] = {}
        self._scenario_results: Dict[str, Dict[str, Any]] = {}
        self._run_id: Optional[str] = None

    def run_full_pipeline(
        self,
        company_id: str,
        location_id: Optional[str] = None,
        kpi_names: Optional[List[str]] = None,
        run_scenarios: bool = True,
        custom_scenario_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute the full orchestration pipeline.
        
        Returns composite result with KPI outputs, scenarios, ROI, and recommendations.
        """
        self._run_id = str(uuid.uuid4())
        started_ts = datetime.utcnow().isoformat()
        kpis_to_run = kpi_names or self.config.enabled_kpis

        logger.info(f"=== Orchestrator Pipeline Started (run_id={self._run_id}) ===")
        logger.info(f"Company: {company_id}, Location: {location_id or 'ALL'}")
        logger.info(f"KPIs to run: {kpis_to_run}")

        self.event_bus.emit_crew_started("orchestrator", company_id, self._run_id)

        # --- Lineage: start top-level orchestration job ---
        lineage_run_id = None
        if self.lineage:
            try:
                lineage_run_id = self.lineage.start_job(
                    job_type="orchestration",
                    job_name=f"pipeline_{company_id}",
                    company_id=company_id,
                    correlation_id=self._run_id,
                    config={"kpis": kpis_to_run, "location_id": location_id},
                    code_version=__import__('loweconex_platform').__version__,
                )
            except Exception as e:
                logger.warning(f"Lineage start failed: {e}")

        # =====================================================================
        # Phase 0: PdM Bridge Enrichment
        # =====================================================================
        pdm_enrichment: Dict[str, Any] = {}
        if self.pdm_bridge:
            logger.info("--- Phase 0: PdM Bridge Enrichment ---")
            try:
                assets = self.tools.get_assets_for_scope(company_id, location_id)
                asset_dicts = [
                    a.to_dict() if hasattr(a, 'to_dict') else a
                    for a in (assets or [])
                ]
                pdm_enrichment = self.pdm_bridge.enrich_kpi_inputs(
                    company_id, asset_dicts
                )
                # Also enrich asset dicts in-place for twin patches
                self.pdm_bridge.enrich_asset_dicts(asset_dicts)
                logger.info(
                    f"PdM enrichment: {len(pdm_enrichment.get('pdm_asset_details', []))} assets, "
                    f"avg_health={pdm_enrichment.get('pdm_avg_health_score', 'N/A')}"
                )
            except Exception as e:
                logger.warning(f"PdM bridge enrichment failed: {e}")

        # Merge PdM enrichment into custom_scenario_params
        if pdm_enrichment:
            if custom_scenario_params is None:
                custom_scenario_params = {}
            custom_scenario_params.update(pdm_enrichment)

        # =====================================================================
        # Phase 1: Run KPI Crews
        # =====================================================================
        logger.info("--- Phase 1: Running KPI Crews ---")
        kpi_results = self._run_kpi_crews(company_id, location_id, kpis_to_run)

        # =====================================================================
        # Phase 2: Scenario Simulation
        # =====================================================================
        scenario_comparison = {}
        if run_scenarios:
            logger.info("--- Phase 2: Running Scenario Simulations ---")
            scenario_comparison = self._run_scenarios(
                company_id, location_id, kpis_to_run, custom_scenario_params
            )

        # =====================================================================
        # Phase 2.5: Cross-Asset Optimization
        # =====================================================================
        logger.info("--- Phase 2.5: Cross-Asset Optimization ---")
        cross_asset_result = self._run_cross_asset_optimization(
            company_id, kpi_results
        )

        # =====================================================================
        # Phase 2.7: CapEx Planning (full lifecycle analysis)
        # =====================================================================
        capex_result: Dict[str, Any] = {}
        if CAPEX_AVAILABLE:
            logger.info("--- Phase 2.7: CapEx Planning ---")
            capex_result = self._run_capex_planning(
                company_id, location_id, kpi_results, pdm_enrichment
            )

        # =====================================================================
        # Phase 3: Portfolio Optimization
        # =====================================================================
        logger.info("--- Phase 3: Portfolio Optimization ---")
        optimization_result = self._run_optimization(kpi_results)

        # =====================================================================
        # Phase 4: Build Composite Result
        # =====================================================================
        logger.info("--- Phase 4: Building Composite Result ---")
        composite = self._build_composite_result(
            company_id=company_id,
            location_id=location_id,
            kpi_results=kpi_results,
            scenario_comparison=scenario_comparison,
            optimization_result=optimization_result,
            cross_asset_result=cross_asset_result,
            capex_result=capex_result,
            started_ts=started_ts,
        )

        # =====================================================================
        # Phase 4.5: Ownership Decision Crew (multi-agent cost optimization)
        # =====================================================================
        if OWNERSHIP_CREW_AVAILABLE:
            logger.info("--- Phase 4.5: Ownership Decision Crew ---")
            try:
                ownership_crew_result = self._run_ownership_decision_crew(
                    composite, kpi_results, custom_scenario_params
                )
                composite["ownership_decision"] = ownership_crew_result
            except Exception as e:
                logger.warning(f"Ownership Decision Crew failed: {e}")

        # =====================================================================
        # Phase 5: Decision Advisory (LLM-powered post-composition reasoning)
        # =====================================================================
        logger.info("--- Phase 5: Decision Advisory Agent ---")
        advisory_result = self._run_decision_advisory(composite)
        composite["decision_advisory"] = advisory_result.to_dict()

        # =====================================================================
        # Phase 6: Execution Engine — register recommendations for CMMS
        # =====================================================================
        if self.execution_engine and EXECUTION_AVAILABLE:
            logger.info("--- Phase 6: Registering Recommendations in Execution Engine ---")
            try:
                self._register_recommendations(
                    composite, company_id, location_id
                )
            except Exception as e:
                logger.warning(f"Execution engine recommendation registration failed: {e}")

        # --- Governance summary ---
        composite["governance"] = self._build_governance_summary(company_id)

        # Store as artifact
        artifact_id = self.tools.store_artifact(
            "composite_result", composite, "orchestrator"
        )

        # --- Lineage: complete top-level job ---
        if self.lineage and lineage_run_id:
            try:
                output_ds = self.lineage.create_dataset(
                    name=f"composite_result_{self._run_id}",
                    dataset_type="roi_rollup",
                    company_id=company_id,
                )
                self.lineage.add_output(lineage_run_id, output_ds)
                self.lineage.complete_job(lineage_run_id)
            except Exception as e:
                logger.warning(f"Lineage complete failed: {e}")

        self.event_bus.emit_crew_completed(
            "orchestrator", company_id, self._run_id, [artifact_id]
        )

        logger.info(f"=== Orchestrator Pipeline Completed (run_id={self._run_id}) ===")
        return composite

    def _run_kpi_crews(
        self,
        company_id: str,
        location_id: Optional[str],
        kpi_names: List[str],
    ) -> Dict[str, KPICrewResult]:
        """Run all requested KPI crews and collect results."""
        results: Dict[str, KPICrewResult] = {}

        # Determine execution order (respect dependencies)
        ordered = self._topological_sort(kpi_names)

        for kpi_name in ordered:
            spec = KPI_REGISTRY.get(kpi_name)
            if not spec:
                logger.warning(f"KPI spec not found: {kpi_name}")
                continue

            logger.info(f"Running KPI crew: {kpi_name}")
            crew_start = datetime.utcnow()
            success = False
            try:
                result = self.kpi_factory.run_crew(
                    spec=spec,
                    company_id=company_id,
                    location_id=location_id,
                )
                results[kpi_name] = result
                self._kpi_results[kpi_name] = result
                success = result.status != "error"

                status = result.status
                savings = result.savings_medium
                logger.info(f"  {kpi_name}: status={status}, savings_med=${savings:,.0f}")

                # --- P1.2: MLOps — register model version + log metrics ---
                if self.model_registry and MLOPS_AVAILABLE:
                    try:
                        mv = ModelVersion(
                            model_name=f"kpi_{kpi_name}",
                            version=f"{self._run_id[:8]}",
                            model_type=ModelType.KPI_CALCULATION.value,
                            stage=ModelStage.PRODUCTION.value,
                            training_run_id=self._run_id,
                            metrics={
                                "savings_medium": result.savings_medium,
                                "confidence": result.confidence,
                                "pass_rate": 1.0 if result.qa_status == "approved" else 0.0,
                            },
                            tags={"company_id": company_id, "run_id": self._run_id},
                        )
                        self.model_registry.register_version(mv)
                    except Exception as e:
                        logger.warning(f"MLOps registration failed for {kpi_name}: {e}")

                # --- P1.4: Exception auto-creation on QA rejection ---
                if result.qa_status == "rejected" and self.exception_manager and OPERATING_MODEL_AVAILABLE:
                    try:
                        blocker_issues = [
                            i for i in result.qa_issues if i.get("severity") == "blocker"
                        ]
                        exc = ExceptionRecord(
                            exception_type=ExceptionType.CALCULATION_ERROR.value,
                            priority=ExceptionPriority.HIGH.value,
                            title=f"KPI {kpi_name} QA rejected",
                            description=(
                                f"QA rejected KPI '{kpi_name}' with "
                                f"{len(blocker_issues)} blocker issue(s): "
                                + "; ".join(i.get("message", "") for i in blocker_issues[:3])
                            ),
                            company_id=company_id,
                            location_id=location_id,
                            kpi_name=kpi_name,
                            blocked_kpis=[kpi_name],
                        )
                        self.exception_manager.create(exc)
                        logger.info(f"  Auto-created exception for rejected KPI: {kpi_name}")
                    except Exception as e:
                        logger.warning(f"Exception auto-creation failed: {e}")

            except Exception as e:
                logger.error(f"  {kpi_name} FAILED: {e}", exc_info=True)
                results[kpi_name] = KPICrewResult(
                    kpi_name=kpi_name, status="error",
                    qa_issues=[{"type": "crew_error", "message": str(e)}],
                )

            # --- P1.3: Agent health — record crew execution ---
            if self.health_monitor and AGENT_OPS_AVAILABLE:
                try:
                    duration_ms = int((datetime.utcnow() - crew_start).total_seconds() * 1000)
                    quality = results.get(kpi_name, KPICrewResult(kpi_name=kpi_name)).confidence
                    self.health_monitor.record_execution(
                        agent_id=f"kpi_crew_{kpi_name}",
                        success=success,
                        duration_ms=duration_ms,
                        quality_score=quality,
                    )
                except Exception as e:
                    logger.warning(f"Health monitor record failed: {e}")

        return results

    def _run_scenarios(
        self,
        company_id: str,
        location_id: Optional[str],
        kpi_names: List[str],
        custom_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run 3 standard scenarios + optional custom scenario."""
        scenarios = self.scenario_agent.get_standard_scenarios()

        if custom_params:
            custom = self.scenario_agent.create_custom_scenario(
                name="custom",
                description="Custom scenario with user-specified parameters",
                overrides=custom_params,
            )
            scenarios.append(custom)

        scenario_ledgers: Dict[str, Dict[str, Any]] = {}

        for scenario in scenarios:
            logger.info(f"Running scenario: {scenario.scenario_name}")
            ledger = DecisionLedger(self.config.roi_engine.double_counting_policy)
            ledger.set_scenario(scenario.scenario_id)

            # Determine which KPIs need re-run for this scenario
            baseline_params = ScenarioParameters().to_kpi_params()
            scenario_kpi_params = scenario.to_kpi_params()
            affected_kpis = self.scenario_agent.get_affected_kpis(
                baseline_params, scenario_kpi_params
            )

            for kpi_name in kpi_names:
                spec = KPI_REGISTRY.get(kpi_name)
                if not spec:
                    continue

                if kpi_name in affected_kpis or scenario.scenario_name != "expected":
                    # Re-run with scenario params
                    result = self.kpi_factory.run_crew(
                        spec=spec,
                        company_id=company_id,
                        location_id=location_id,
                        scenario_params=scenario_kpi_params,
                    )
                else:
                    # Reuse baseline result
                    result = self._kpi_results.get(kpi_name, KPICrewResult(kpi_name=kpi_name))

                ledger.register_kpi_result(kpi_name, result.to_dict())

            ledger.build_attributions_from_kpi_results()
            reconciled = ledger.get_reconciled_totals()

            scenario_ledgers[scenario.scenario_name] = {
                "scenario_id": scenario.scenario_id,
                "scenario_name": scenario.scenario_name,
                "parameters": scenario.to_dict(),
                "reconciled_totals": reconciled,
                "reconciliation_plan": self.scenario_agent.generate_reconciliation_plan(scenario),
            }

            self.scenario_agent.store_scenario_result(scenario.scenario_id, reconciled)
            logger.info(f"  {scenario.scenario_name}: total_med=${reconciled.get('total_savings_medium', 0):,.0f}")

        comparison = self.scenario_agent.compare_scenarios(
            {name: data for name, data in scenario_ledgers.items()}
        )

        self._scenario_results = scenario_ledgers
        return {
            "scenarios": scenario_ledgers,
            "comparison": comparison,
        }

    def _run_decision_advisory(
        self, composite: Dict[str, Any]
    ) -> AdvisoryOutput:
        """Run LLM-powered decision advisory on the composite result."""
        advisory_agent = DecisionAdvisoryAgent(
            config={
                "temperature": self.config.crewai.temperature,
                "model": self.config.crewai.llm_model,
            },
            tools=self.tools,
        )
        try:
            result = advisory_agent.advise(composite)
            logger.info(
                f"Advisory: {len(result.strategic_recommendations)} recommendations, "
                f"narrative={len(result.executive_narrative)} chars"
            )
            return result
        except Exception as e:
            logger.error(f"Decision advisory failed: {e}", exc_info=True)
            return AdvisoryOutput()

    def _run_cross_asset_optimization(
        self,
        company_id: str,
        kpi_results: Dict[str, KPICrewResult],
    ) -> Dict[str, Any]:
        """Run cross-asset interaction analysis and build Pareto frontier."""
        rel_graph = getattr(self.twin_store, '_relationship_graph', None)
        if rel_graph is None:
            rel_graph = RelationshipGraph()

        # Discover thermal interaction groups
        assets = self.tools.get_assets_for_scope(company_id)
        thermal_groups = []
        seen = set()
        for asset in assets:
            aid = asset.get("asset_id", "") if isinstance(asset, dict) else getattr(asset, 'asset_id', '')
            if aid in seen:
                continue
            group = rel_graph.get_thermal_interaction_group(aid)
            if len(group) > 1:
                thermal_groups.append(list(group))
                seen.update(group)

        # Cross-asset KPI dependency analysis (aggregate dependencies across assets)
        cross_deps_by_asset = {}
        cross_deps_aggregate = {
            "energy": set(),
            "refrigerant": set(),
            "food_safety": set(),
            "maintenance": set(),
        }
        for asset in assets:
            aid = asset.get("asset_id", "") if isinstance(asset, dict) else getattr(asset, "asset_id", "")
            if not aid:
                continue
            deps = rel_graph.find_cross_asset_kpi_dependencies(aid)
            cross_deps_by_asset[aid] = deps
            for kpi_key, dep_ids in deps.items():
                if kpi_key in cross_deps_aggregate:
                    cross_deps_aggregate[kpi_key].update(dep_ids)
        cross_deps = {k: sorted(v) for k, v in cross_deps_aggregate.items()}

        # Build Pareto frontier from KPI results (savings vs confidence)
        pareto_points = []
        for kpi_name, result in kpi_results.items():
            pareto_points.append({
                "kpi_name": kpi_name,
                "savings_medium": result.savings_medium,
                "confidence": result.confidence,
                "status": result.status,
            })
        pareto_points.sort(key=lambda p: (-p["savings_medium"], -p["confidence"]))

        # Identify Pareto-dominant set (not dominated on both axes)
        pareto_frontier = []
        max_conf = -1
        for pt in pareto_points:
            if pt["confidence"] > max_conf:
                pareto_frontier.append(pt)
                max_conf = pt["confidence"]

        # Marginal impact matrix: for each thermal group, sum savings of member KPIs
        group_impacts = []
        for i, group in enumerate(thermal_groups):
            group_savings = 0.0
            group_kpis = set()
            for kpi_name, result in kpi_results.items():
                for patch in result.twin_patches:
                    if patch.get("entity_id") in group:
                        group_savings += result.savings_medium
                        group_kpis.add(kpi_name)
                        break
            group_impacts.append({
                "group_id": i,
                "asset_ids": group,
                "total_savings_medium": group_savings,
                "contributing_kpis": list(group_kpis),
            })

        logger.info(
            f"Cross-asset: {len(thermal_groups)} thermal groups, "
            f"{len(pareto_frontier)} points on Pareto frontier, "
            f"{len(cross_deps)} cross-KPI dependency sets"
        )

        return {
            "thermal_interaction_groups": thermal_groups,
            "cross_kpi_dependencies": cross_deps,
            "cross_kpi_dependencies_by_asset": cross_deps_by_asset,
            "pareto_frontier": pareto_frontier,
            "all_points": pareto_points,
            "group_marginal_impacts": group_impacts,
        }

    def _run_capex_planning(
        self,
        company_id: str,
        location_id: Optional[str],
        kpi_results: Dict[str, KPICrewResult],
        pdm_enrichment: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run full CapEx lifecycle analysis using the CapEx Generator engine.

        Pulls asset data from twin store, enriches with PdM health/fault data,
        runs survival + LCC + knapsack optimization, and returns the plan.
        """
        if not CAPEX_AVAILABLE:
            return {}

        try:
            engine = CapExEngine()

            # Gather assets from twin store
            assets_raw = self.tools.get_assets_for_scope(company_id, location_id)
            assets = [
                a.to_dict() if hasattr(a, "to_dict") else a
                for a in (assets_raw or [])
            ]
            if not assets:
                logger.info("CapEx planning: no assets found, skipping")
                return {}

            # Build health / fault / energy-waste maps from PdM enrichment
            health_map: Dict[str, Dict[str, Any]] = {}
            fault_map: Dict[str, Dict[str, Any]] = {}
            waste_map: Dict[str, Dict[str, Any]] = {}
            peer_map: Dict[str, int] = {}

            for detail in pdm_enrichment.get("pdm_asset_details", []):
                aid = detail.get("asset_id", "")
                health_map[aid] = {
                    "health_score": detail.get("health_score", 80),
                    "degradation_score": detail.get("degradation_index", 10) * 100,
                    "rul_hours": detail.get("rul_hours", 5000),
                    "annual_maintenance_cost": detail.get("annual_maintenance_cost", 2000),
                    "kwh_day": detail.get("kwh_day", 100),
                    "maintenance_trend": detail.get("maintenance_trend", 0),
                }
                fault_map[aid] = {
                    "fault_burden_score": detail.get("fault_burden_score", 0),
                    "total_faults": detail.get("total_faults", 0),
                }
                waste_map[aid] = {
                    "waste_percentile": detail.get("energy_waste_percentile", 50),
                }
                peer_map[aid] = detail.get("peer_percentile", 50)

            # Also pull health from KPI results (capex_lifecycle_optimization)
            capex_kpi = kpi_results.get("capex_lifecycle_optimization")
            if capex_kpi and capex_kpi.metrics:
                for repl in capex_kpi.metrics.get("replacements", []):
                    aid = repl.get("asset_id", "")
                    if aid and aid not in health_map:
                        health_map[aid] = {
                            "health_score": repl.get("health_score", 80),
                            "annual_maintenance_cost": repl.get("opex_monthly", 500) * 12,
                        }

            # Build replacement options: one standard option per asset
            replacement_options: Dict[str, list] = {}
            for asset in assets:
                aid = asset.get("asset_id", "")
                atype = asset.get("asset_type", "RTU")
                replace_cost = asset.get("capex_replace_cost", asset.get("replacement_cost", 15_000))
                replacement_options[aid] = [{
                    "option_id": f"opt-std-{aid}",
                    "option_name": f"Standard {atype} replacement",
                    "capex_installed_cost": replace_cost,
                    "efficiency_delta": 0.18,
                    "maintenance_delta_per_year": -800,
                    "expected_life_years": 15,
                    "warranty_years": 1,
                }]

            # Economic assumptions from platform config
            discount_rate = self.config.roi_engine.discount_rate
            horizon = self.config.roi_engine.analysis_horizon_years
            economic_assumption = {
                "discount_rate": discount_rate,
                "analysis_horizon_years": horizon,
                "failure_event_cost_by_type": {
                    "RTU": 15_000, "AHU": 20_000,
                    "COMPRESSOR_RACK": 25_000, "CONDENSING_UNIT": 12_000,
                    "WALK_IN_COOLER": 10_000, "WALK_IN_FREEZER": 12_000,
                    "REACH_IN_CASE": 8_000, "CHILLER": 30_000,
                },
            }
            utility_rate = {
                "energy_rate": 0.12,
                "escalation_rate": 0.03,
            }

            # Budget: use platform capex_budget or fallback
            budget = getattr(self.config, "capex_budget", 1_000_000)

            result = engine.analyze(
                store={"name": company_id, "store_id": company_id, "location_id": location_id or ""},
                assets=assets,
                replacement_options=replacement_options,
                economic_assumption=economic_assumption,
                utility_rate=utility_rate,
                budget=budget,
                objective="max_expected_npv",
                health_data=health_map,
                fault_data=fault_map,
                energy_waste_data=waste_map,
                peer_data=peer_map,
            )

            logger.info(
                f"CapEx planning complete: {result.summary.get('assets_selected_for_replacement', 0)} "
                f"replacements, NPV=${result.summary.get('total_expected_npv', 0):,.0f}"
            )

            return result.to_dict()

        except Exception as e:
            logger.error(f"CapEx planning failed: {e}", exc_info=True)
            return {"error": str(e)}

    def _run_optimization(
        self, kpi_results: Dict[str, KPICrewResult]
    ) -> Dict[str, Any]:
        """Run portfolio optimization on KPI results."""
        result_dicts = {k: v.to_dict() for k, v in kpi_results.items()}
        actions = self.portfolio_optimizer.generate_actions_from_kpi_results(result_dicts)

        if not actions:
            return {"message": "No actions to optimize", "selected_actions": []}

        constraints = OptimizationConstraints(
            total_budget=self.config.roi_engine.discount_rate * 10_000_000,
            capex_budget=1_000_000,
            min_confidence=0.3,
        )

        greedy_result = self.portfolio_optimizer.optimize_greedy(actions, constraints)
        categorized = self.portfolio_optimizer.categorize_actions(greedy_result.selected_actions)

        return {
            "optimization": greedy_result.to_dict(),
            "categorized_actions": {
                cat: [a.to_dict() for a in acts]
                for cat, acts in categorized.items()
            },
        }

    def _build_composite_result(
        self,
        company_id: str,
        location_id: Optional[str],
        kpi_results: Dict[str, KPICrewResult],
        scenario_comparison: Dict[str, Any],
        optimization_result: Dict[str, Any],
        started_ts: str,
        cross_asset_result: Optional[Dict[str, Any]] = None,
        capex_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Assemble the final composite result."""
        # Build decision ledger for baseline
        ledger = DecisionLedger(self.config.roi_engine.double_counting_policy)
        for kpi_name, result in kpi_results.items():
            ledger.register_kpi_result(kpi_name, result.to_dict())
        ledger.build_attributions_from_kpi_results()

        reconciled = ledger.get_reconciled_totals()
        naive = ledger.get_naive_totals()
        reconciliation_note = ledger.get_reconciliation_explanation()

        # KPI scorecards
        scorecards = {}
        for kpi_name, result in kpi_results.items():
            scorecards[kpi_name] = {
                "status": result.status,
                "savings_low": result.savings_low,
                "savings_medium": result.savings_medium,
                "savings_high": result.savings_high,
                "confidence": result.confidence,
                "assumptions_count": len(result.assumptions),
                "gaps_count": len(result.gaps),
                "qa_status": result.qa_status,
            }

        return {
            "run_id": self._run_id,
            "company_id": company_id,
            "location_id": location_id,
            "started_ts": started_ts,
            "completed_ts": datetime.utcnow().isoformat(),

            # Executive summary
            "executive_summary": {
                "total_savings_low": reconciled.get("total_savings_low", 0),
                "total_savings_medium": reconciled.get("total_savings_medium", 0),
                "total_savings_high": reconciled.get("total_savings_high", 0),
                "kpi_count": len(kpi_results),
                "approved_kpis": sum(1 for r in kpi_results.values() if r.status == "approved"),
                "key_risks": self._identify_key_risks(kpi_results),
            },

            # KPI scorecards
            "kpi_scorecards": scorecards,

            # Detailed KPI results
            "kpi_results": {k: v.to_dict() for k, v in kpi_results.items()},

            # Savings reconciliation
            "savings_reconciliation": {
                "reconciled_totals": reconciled,
                "naive_totals": naive,
                "reconciliation_note": reconciliation_note,
                "by_category": reconciled.get("by_category", {}),
            },

            # ROI metrics
            "roi_metrics": self._compute_roi_metrics(reconciled, optimization_result),

            # Scenarios
            "scenario_analysis": scenario_comparison,

            # Optimization
            "portfolio_optimization": optimization_result,

            # Cross-asset optimization
            "cross_asset_optimization": cross_asset_result or {},

            # CapEx planning (lifecycle analysis, knapsack optimization)
            "capex_planning": capex_result or {},

            # Metadata
            "metadata": {
                "platform_version": "1.0.0",
                "crewai_available": CREWAI_AVAILABLE,
                "double_counting_policy": self.config.roi_engine.double_counting_policy,
            },
        }

    def _compute_roi_metrics(
        self,
        reconciled: Dict[str, Any],
        optimization_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Compute ROI metrics: payback_months, savings_to_cost_multiple, IRR estimate."""
        total_savings_medium = reconciled.get("total_savings_medium", 0)
        total_savings_low = reconciled.get("total_savings_low", 0)
        total_savings_high = reconciled.get("total_savings_high", 0)

        opt = optimization_result.get("optimization", {})
        total_cost = opt.get("total_cost", 0)
        total_npv = opt.get("total_npv", 0)

        # Payback months: how many months of savings to cover implementation cost
        monthly_savings = total_savings_medium / 12 if total_savings_medium > 0 else 0
        payback_months = (
            round(total_cost / monthly_savings, 1)
            if monthly_savings > 0 and total_cost > 0
            else None
        )

        # Savings-to-cost multiple
        savings_to_cost_multiple = round(
            total_savings_medium / total_cost, 2
        ) if total_cost > 0 else None

        # Simple IRR approximation (annual savings / cost - 1)
        discount_rate = self.config.roi_engine.discount_rate
        horizon = self.config.roi_engine.analysis_horizon_years
        annuity_factor = sum(1 / (1 + discount_rate) ** y for y in range(1, horizon + 1))
        npv_savings = total_savings_medium * annuity_factor
        net_npv = npv_savings - total_cost

        return {
            "total_implementation_cost": total_cost,
            "total_savings_annual_medium": total_savings_medium,
            "total_savings_annual_low": total_savings_low,
            "total_savings_annual_high": total_savings_high,
            "payback_months": payback_months,
            "savings_to_cost_multiple": savings_to_cost_multiple,
            "npv_savings": round(npv_savings, 2),
            "net_npv": round(net_npv, 2),
            "discount_rate": discount_rate,
            "analysis_horizon_years": horizon,
        }

    # ------------------------------------------------------------------
    # Backward-compatible helper methods (legacy callers/tests)
    # ------------------------------------------------------------------

    def _reconcile_savings(
        self,
        kpi_results: Dict[str, KPICrewResult],
    ) -> tuple[Dict[str, Any], Dict[str, float], str]:
        """Reconcile KPI savings and return (reconciled, naive, explanation)."""
        ledger = DecisionLedger(self.config.roi_engine.double_counting_policy)
        for kpi_name, result in kpi_results.items():
            savings_category = getattr(result, "savings_category", "") or kpi_name
            ledger.register_kpi_result(
                kpi_name,
                {
                    "kpi_name": kpi_name,
                    "savings_low": result.savings_low,
                    "savings_medium": result.savings_medium,
                    "savings_high": result.savings_high,
                    "confidence": result.confidence,
                    "savings_category": savings_category,
                    "evidence_refs": result.evidence_refs,
                },
            )
        ledger.build_attributions_from_kpi_results()
        reconciled = ledger.get_reconciled_totals()
        naive_raw = ledger.get_naive_totals()
        naive = {
            "total_savings_low": naive_raw.get("naive_low", 0.0),
            "total_savings_medium": naive_raw.get("naive_medium", 0.0),
            "total_savings_high": naive_raw.get("naive_high", 0.0),
        }
        return reconciled, naive, ledger.get_reconciliation_explanation()

    def _generate_scenario_comparison(
        self,
        kpi_results: Dict[str, KPICrewResult],
    ) -> Dict[str, Any]:
        """Generate a lightweight scenario comparison from baseline KPI outputs."""
        reconciled, _, _ = self._reconcile_savings(kpi_results)
        baseline_med = float(reconciled.get("total_savings_medium", 0.0))
        scenarios = {
            "conservative": {"total_savings_medium": round(baseline_med * 0.8, 2)},
            "expected": {"total_savings_medium": round(baseline_med, 2)},
            "aggressive": {"total_savings_medium": round(baseline_med * 1.2, 2)},
        }
        ranking = sorted(
            [
                {"scenario": name, "savings_medium": vals["total_savings_medium"]}
                for name, vals in scenarios.items()
            ],
            key=lambda x: x["savings_medium"],
            reverse=True,
        )
        return {
            "scenarios": scenarios,
            "comparison": {"ranking_by_total_savings": ranking},
        }

    def _identify_key_risks(self, kpi_results: Dict[str, KPICrewResult]) -> List[str]:
        """Identify key risks from KPI results."""
        risks = []
        low_confidence_kpis = [k for k, v in kpi_results.items() if v.confidence < 0.5]
        if low_confidence_kpis:
            risks.append(f"Low confidence in {len(low_confidence_kpis)} KPIs: {', '.join(low_confidence_kpis)}")

        rejected_kpis = [k for k, v in kpi_results.items() if v.status == "rejected"]
        if rejected_kpis:
            risks.append(f"QA rejected {len(rejected_kpis)} KPIs: {', '.join(rejected_kpis)}")

        high_gap_kpis = [k for k, v in kpi_results.items() if len(v.gaps) > 2]
        if high_gap_kpis:
            risks.append(f"Significant data gaps in {len(high_gap_kpis)} KPIs")

        if not risks:
            risks.append("No major risks identified")

        return risks

    def _topological_sort(self, kpi_names: List[str]) -> List[str]:
        """Sort KPIs respecting dependencies (dependent KPIs run after their inputs)."""
        # Build dependency graph
        deps: Dict[str, List[str]] = {}
        for name in kpi_names:
            spec = KPI_REGISTRY.get(name)
            if spec:
                deps[name] = [d for d in spec.depends_on_kpis if d in kpi_names]
            else:
                deps[name] = []

        # Kahn's algorithm
        in_degree = {n: 0 for n in kpi_names}
        for n, dep_list in deps.items():
            for d in dep_list:
                in_degree[n] = in_degree.get(n, 0) + 1

        queue = [n for n in kpi_names if in_degree.get(n, 0) == 0]
        ordered = []

        while queue:
            node = queue.pop(0)
            ordered.append(node)
            for n, dep_list in deps.items():
                if node in dep_list:
                    in_degree[n] -= 1
                    if in_degree[n] == 0 and n not in ordered:
                        queue.append(n)

        # Add any remaining (cycles or missing)
        for n in kpi_names:
            if n not in ordered:
                ordered.append(n)

        return ordered

    def _register_recommendations(
        self,
        composite: Dict[str, Any],
        company_id: str,
        location_id: Optional[str],
    ):
        """Register advisory recommendations into the ExecutionEngine's tracker.

        This bridges the gap between analytics output and operational execution:
        each strategic recommendation becomes a trackable RecommendationRecord
        that can later be accepted, converted to a CMMS work order, and have
        its outcome measured.
        """
        advisory = composite.get("decision_advisory", {})
        recs = advisory.get("strategic_recommendations", [])
        if not recs:
            return

        tracker = self.execution_engine.recommendation_tracker
        registered_ids = []

        for rec in recs:
            record = RecommendationRecord(
                title=rec.get("title", ""),
                description=rec.get("rationale", ""),
                kpi_name=rec.get("kpi_name"),
                company_id=company_id,
                location_id=location_id,
                recommended_action=rec.get("title", ""),
                estimated_savings_usd=float(rec.get("savings_impact", 0.0)),
                confidence=float(rec.get("confidence", 0.0)),
                correlation_id=self._run_id,
            )
            rec_id = tracker.create(record)
            registered_ids.append(rec_id)

        composite["execution"] = {
            "recommendations_registered": len(registered_ids),
            "recommendation_ids": registered_ids,
            "execution_engine_stats": self.execution_engine.stats(),
        }
        logger.info(
            f"Registered {len(registered_ids)} recommendations in ExecutionEngine"
        )

    def _build_governance_summary(self, company_id: str) -> Dict[str, Any]:
        """Collect governance stats from all wired enterprise modules."""
        summary: Dict[str, Any] = {"modules_active": []}

        if self.lineage:
            try:
                summary["lineage"] = self.lineage.graph.stats()
                summary["modules_active"].append("lineage")
            except Exception:
                pass

        if self.dq_engine:
            try:
                summary["data_quality"] = self.dq_engine.stats()
                summary["modules_active"].append("data_quality")
            except Exception:
                pass

        if self.benchmark_engine:
            try:
                summary["benchmarking"] = self.benchmark_engine.stats()
                summary["modules_active"].append("benchmarking")
            except Exception:
                pass

        if self.model_registry:
            try:
                summary["mlops"] = self.model_registry.stats()
                summary["modules_active"].append("mlops")
            except Exception:
                pass

        if self.health_monitor:
            try:
                summary["agent_health"] = self.health_monitor.stats()
                summary["modules_active"].append("agent_ops")
            except Exception:
                pass

        if self.exception_manager:
            try:
                summary["exceptions"] = self.exception_manager.pattern_analysis()
                summary["modules_active"].append("operating_model")
            except Exception:
                pass

        if self.execution_engine:
            try:
                summary["execution"] = self.execution_engine.stats()
                summary["modules_active"].append("execution")
            except Exception:
                pass

        return summary

    def _run_ownership_decision_crew(
        self,
        composite: Dict[str, Any],
        kpi_results: Dict[str, Any],
        custom_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Run the Ownership Decision Crew (12-agent multi-agent pipeline).

        Extracts metric inputs from KPI crew results and feeds them into
        the ownership cost optimization pipeline.
        """
        # Build metric_inputs from KPI crew results
        metric_inputs = self._extract_metric_inputs_from_kpi(kpi_results)

        # Merge custom params as constraints
        constraints = {}
        if custom_params:
            constraints = {
                k: v for k, v in custom_params.items()
                if k in ("capex_budget", "total_budget", "opex_budget",
                         "owner_budgets", "min_confidence")
            }

        crew = OwnershipDecisionCrew()
        result = crew.run(
            metric_inputs=metric_inputs,
            constraints=constraints,
        )

        logger.info(
            f"Ownership Decision Crew: {len(result.pareto_options)} Pareto options, "
            f"NPV=${result.consolidated_roi.get('npv', 0):,.0f}, "
            f"{result.negotiation_log.conflicts_resolved} conflicts resolved"
        )

        return result.to_dict()

    @staticmethod
    def _extract_metric_inputs_from_kpi(
        kpi_results: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Map KPI crew outputs to ownership metric inputs.

        Maps KPI result metrics into the format expected by the ownership
        module's metric catalog (metric_id → input dict).
        """
        metric_inputs: Dict[str, Dict[str, Any]] = {}

        # KPI name → metric_id mapping
        kpi_to_metric = {
            "work_order_reduction": "m_reactive_jobs",
            "ppm_maximization": "m_ppm_frequency",
            "call_center_volume_reduction": "m_service_bureau",
            "capex_lifecycle_optimization": "m_replacement_cycle",
            "food_temp_diagnostics_improvement": "m_temp_breaches",
            "food_waste_reduction": "m_product_discard",
            "refrigerant_leak_reduction": "m_refrigerant_leakage",
            "energy_reduction": "m_energy_reduction",
            "esg_compliance": "m_emissions_reduction",
            "uptime_improvement": "m_uptime_improvement",
            "preventive_maintenance_optimization": "m_pm_optimization",
        }

        for kpi_name, result in kpi_results.items():
            metric_id = kpi_to_metric.get(kpi_name)
            if not metric_id:
                continue

            # Extract metrics dict from KPI result
            result_dict = result.to_dict() if hasattr(result, "to_dict") else result
            metrics = result_dict.get("metrics", {})

            if metrics:
                metric_inputs[metric_id] = metrics

        return metric_inputs
