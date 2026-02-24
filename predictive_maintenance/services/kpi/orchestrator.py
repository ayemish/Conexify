"""
Cross-KPI Orchestration Layer

Aggregates all 14 KPI computations, generates cross-KPI recommendations,
scenario comparisons, location rankings, and ROI calculations from real data.
"""

import copy
import hashlib
import json as _json
import logging
import math
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import KPIConfig, KPIResult
from .registry import KPI_REGISTRY, get_kpi_service
from .loweconex_bridge import (
    enrich_results_with_crews,
    get_bridge_status,
    reconcile_double_counting,
    LOWECONEX_AVAILABLE,
)

logger = logging.getLogger(__name__)

# ── Optional EventBus integration ────────────────────────────────────
_event_bus = None


def _get_event_bus():
    """Lazily initialize the shared RedisEventBus singleton."""
    global _event_bus
    if _event_bus is not None:
        return _event_bus
    try:
        from shared.event_bus.redis_event_bus import RedisEventBus
        from predictive_maintenance.config import settings
        redis_url = getattr(getattr(settings, "redis", None), "url", "redis://localhost:6379")
        _event_bus = RedisEventBus(redis_url=redis_url, agent_id="kpi_orchestrator")
        return _event_bus
    except Exception as e:
        logger.debug("EventBus not available: %s", e)
        return None


def _emit_event(event_type: str, company_id: str, correlation_id: str, payload: dict):
    """Emit a Loweconex-style event if the bus is available."""
    bus = _get_event_bus()
    if not bus:
        return
    try:
        from shared.event_bus.events import EventEnvelope
        bus.publish(EventEnvelope(
            event_type=event_type,
            company_id=company_id,
            producer="kpi_orchestrator",
            correlation_id=correlation_id,
            payload=payload,
        ))
    except Exception as e:
        logger.debug("Event emission failed: %s", e)


@dataclass
class LocationSavings:
    """Per-location savings breakdown."""
    location_id: str
    address: str = ""
    total_savings: float = 0.0
    kpi_count: int = 0
    top_kpi: str = ""


@dataclass
class ScenarioEstimate:
    """A named savings scenario."""
    scenario_name: str
    description: str
    total_savings_medium: float = 0.0


@dataclass
class StrategicRecommendation:
    """A prioritized strategic recommendation."""
    priority: int
    title: str
    impact: str  # high, medium, low
    savings_impact: float
    rationale: str


@dataclass
class ROIMetrics:
    """Return-on-investment calculations."""
    payback_months: float = 0.0
    npv: float = 0.0
    irr: float = 0.0
    savings_to_cost_multiple: float = 0.0


@dataclass
class KPIDashboardResult:
    """Complete KPI dashboard output."""
    site_id: str
    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Executive summary
    executive_summary: Dict[str, Any] = field(default_factory=dict)

    # Individual KPI scorecards
    scorecards: List[Dict[str, Any]] = field(default_factory=list)

    # Cross-KPI analysis
    scenario_comparison: List[Dict[str, Any]] = field(default_factory=list)
    decision_advisory: Dict[str, Any] = field(default_factory=dict)
    location_ranking: List[Dict[str, Any]] = field(default_factory=list)

    # Financial
    roi: Dict[str, Any] = field(default_factory=dict)

    # Governance
    governance: Dict[str, Any] = field(default_factory=dict)
    data_source: str = "deterministic_kpi_orchestrator"
    degraded_mode: bool = False
    warnings: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "computed_at": self.computed_at.isoformat(),
            "executive_summary": self.executive_summary,
            "scorecards": self.scorecards,
            "scenario_comparison": self.scenario_comparison,
            "decision_advisory": self.decision_advisory,
            "location_ranking": self.location_ranking,
            "roi": self.roi,
            "governance": self.governance,
            "data_source": self.data_source,
            "degraded_mode": self.degraded_mode,
            "warnings": self.warnings,
        }


    # ── Pipeline Type Definitions ──────────────────────────────────────
    # Each pipeline type focuses on a specific operational goal and
    # runs only the relevant KPI crews.

PIPELINE_TYPES: Dict[str, Dict[str, Any]] = {
    "capex_asset_replacement": {
        "name": "CapEx & Asset Replacement",
        "description": "Optimize capital expenditure timing and asset replacement using health scores, remaining useful life, and NPV analysis.",
        "icon": "building",
        "color": "#8b5cf6",
        "goal": "Minimize lifecycle cost and maximize fleet value through data-driven replacement prioritization.",
        "kpis": [
            "capex_lifecycle_optimization",
            "asset_failure_prediction",
            "asset_uptime_increase",
        ],
        "phases": [
            "Collect Asset Health Data",
            "Compute RUL & Failure Probability",
            "Run Weibull Survival Models",
            "NPV & Payback Analysis",
            "Budget Optimization (Knapsack)",
            "Generate Replacement Schedule",
        ],
    },
    "preventive_maintenance": {
        "name": "Preventive Maintenance",
        "description": "Optimize PM intervals and shift from calendar-based to condition-based maintenance using sensor data.",
        "icon": "wrench",
        "color": "#22c55e",
        "goal": "Reduce over-maintenance costs while maintaining food safety and equipment reliability.",
        "kpis": [
            "preventive_maintenance_optimization",
            "ppm_maximization",
            "food_safety_compliance",
            "food_temp_diagnostics_improvement",
        ],
        "phases": [
            "Collect Maintenance History",
            "Analyze PM Intervals vs Condition",
            "Identify Over/Under-Maintained Assets",
            "Compute Optimal PM Schedules",
            "Validate Food Safety Compliance",
            "Generate PM Recommendations",
        ],
    },
    "work_order_mitigation": {
        "name": "Work Order Mitigation",
        "description": "Reduce reactive work orders, call center volume, and third-party service dispatches through predictive insights.",
        "icon": "clipboard",
        "color": "#f59e0b",
        "goal": "Shift maintenance from reactive to planned, reducing emergency costs and operational disruption.",
        "kpis": [
            "work_order_reduction",
            "call_center_volume_reduction",
            "service_bureau_reduction",
        ],
        "phases": [
            "Collect Work Order History",
            "Classify Reactive vs Planned WOs",
            "Analyze Call Center Patterns",
            "Model Dispatch Avoidance",
            "Compute Savings from PdM Coverage",
            "Generate Mitigation Plan",
        ],
    },
    "energy_management": {
        "name": "Energy Management & Savings",
        "description": "Identify energy waste, refrigerant leak savings, and carbon reduction opportunities across the fleet.",
        "icon": "zap",
        "color": "#3b82f6",
        "goal": "Reduce energy consumption and environmental impact while maintaining operational performance.",
        "kpis": [
            "energy_reduction",
            "refrigerant_leak_reduction",
            "esg_compliance",
            "food_waste_reduction",
        ],
        "phases": [
            "Collect Energy & Refrigerant Data",
            "Baseline Energy Consumption",
            "Detect Efficiency Anomalies",
            "Model Refrigerant Leak Savings",
            "Compute Carbon Reduction",
            "Generate Energy Optimization Plan",
        ],
    },
}


class KPIOrchestrator:
    """Orchestrates all 14 KPI computations and cross-KPI analysis.

    This replaces the hard-coded mock data in the frontend with
    real computations backed by telemetry, alert, and asset data.
    """

    # Max threads for parallel location ranking
    _LOCATION_WORKERS = 4

    def __init__(self, config: KPIConfig):
        self.config = config
        self._services = {
            name: get_kpi_service(name, config)
            for name in KPI_REGISTRY
        }
        # LRU-style cache for scenario comparisons keyed by data fingerprint
        self._scenario_cache: Dict[str, List[Dict[str, Any]]] = {}

    @staticmethod
    def _warning(code: str, message: str, **context: Any) -> Dict[str, Any]:
        return {"code": code, "message": message, "context": context}

    def compute_pipeline(
        self,
        pipeline_type: str,
        asset_data: List[Dict[str, Any]],
        alert_data: List[Dict[str, Any]],
        telemetry_summary: Dict[str, Any],
        health_data: List[Dict[str, Any]],
        implementation_cost: float = 100_000.0,
    ) -> Dict[str, Any]:
        """Run a focused orchestration pipeline for a specific goal.

        Parameters
        ----------
        pipeline_type : str
            One of the keys in PIPELINE_TYPES.
        """
        ptype = PIPELINE_TYPES.get(pipeline_type)
        if not ptype:
            raise ValueError(f"Unknown pipeline type: {pipeline_type}. "
                           f"Available: {list(PIPELINE_TYPES.keys())}")

        correlation_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)
        kpi_names = ptype["kpis"]
        phases = ptype["phases"]

        _emit_event("PIPELINE_STARTED", self.config.site_id, correlation_id, {
            "pipeline_type": pipeline_type,
            "kpi_count": len(kpi_names),
        })

        # Run only the relevant KPI crews
        results: List[KPIResult] = []
        crew_statuses = {}
        for i, name in enumerate(kpi_names):
            service = self._services.get(name)
            if not service:
                logger.warning("KPI service %s not found, skipping", name)
                continue
            try:
                import time
                t0 = time.monotonic()
                result = service.compute(
                    asset_data=asset_data,
                    alert_data=alert_data,
                    telemetry_summary=telemetry_summary,
                    health_data=health_data,
                )
                duration_ms = (time.monotonic() - t0) * 1000
                if result.confidence >= 0.50:
                    result.approve()
                results.append(result)
                crew_statuses[name] = {"status": "completed", "duration_ms": round(duration_ms, 1)}
            except Exception as e:
                logger.error("Pipeline %s KPI %s failed: %s", pipeline_type, name, e)
                crew_statuses[name] = {"status": "failed", "duration_ms": 0}

        # Enrich with CrewAI when available
        results = enrich_results_with_crews(results, self.config)

        # Aggregate
        scorecards = [r.to_dict() for r in results]
        approved = [r for r in results if r.status == "approved"]
        total_med = sum(r.savings_medium for r in results)
        total_low = sum(r.savings_low for r in results)
        total_high = sum(r.savings_high for r in results)
        avg_conf = sum(r.confidence for r in results) / max(len(results), 1)
        duration_seconds = (datetime.now(timezone.utc) - started_at).total_seconds()

        # Build goal-specific recommendations
        recs = self._generate_recommendations(results)

        _emit_event("PIPELINE_COMPLETED", self.config.site_id, correlation_id, {
            "pipeline_type": pipeline_type,
            "total_savings_medium": total_med,
        })

        return {
            "pipeline_type": pipeline_type,
            "pipeline_name": ptype["name"],
            "pipeline_description": ptype["description"],
            "pipeline_goal": ptype["goal"],
            "pipeline_color": ptype["color"],
            "site_id": self.config.site_id,
            "run_id": correlation_id,
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(duration_seconds, 2),
            "status": "completed",
            "phases": phases,
            "phase_index": len(phases) - 1,
            "total_phases": len(phases),
            "scorecards": scorecards,
            "crew_statuses": crew_statuses,
            "executive_summary": {
                "total_savings_medium": round(total_med, 2),
                "total_savings_low": round(total_low, 2),
                "total_savings_high": round(total_high, 2),
                "kpi_count": len(results),
                "approved_kpis": len(approved),
                "avg_confidence": round(avg_conf, 3),
                "narrative": (
                    f"{ptype['name']}: {len(results)} KPI crews analyzed "
                    f"({len(approved)} approved). "
                    f"Estimated annual impact: ${total_med:,.0f} "
                    f"(range: ${total_low:,.0f} – ${total_high:,.0f})."
                ),
            },
            "recommendations": [
                {"priority": r.priority, "title": r.title, "impact": r.impact,
                 "savings_impact": round(r.savings_impact, 2), "rationale": r.rationale}
                for r in recs
            ],
            "roi": self._compute_roi(total_med, implementation_cost),
        }

    def compute_all(
        self,
        asset_data: List[Dict[str, Any]],
        alert_data: List[Dict[str, Any]],
        telemetry_summary: Dict[str, Any],
        health_data: List[Dict[str, Any]],
        location_map: Optional[Dict[str, Dict[str, Any]]] = None,
        implementation_cost: float = 250_000.0,
    ) -> KPIDashboardResult:
        """Run all KPI computations and produce the full dashboard.

        Parameters
        ----------
        asset_data : list of dict
            Asset records with metadata.
        alert_data : list of dict
            Alert records with types, outcomes, timestamps.
        telemetry_summary : dict
            Aggregated telemetry stats.
        health_data : list of dict
            Per-asset health index results.
        location_map : dict, optional
            {location_id: {"address": ..., "asset_ids": [...]}}
        implementation_cost : float
            Estimated cost to deploy the PdM platform.
        """
        warnings_out: List[Dict[str, Any]] = []
        degraded_mode = False

        # Store references for per-location re-computation in _rank_locations
        self._last_alert_data = alert_data
        self._last_telemetry_summary = telemetry_summary

        # ── 1. Compute each KPI ───────────────────────────────────
        correlation_id = str(uuid.uuid4())
        _emit_event("CREW_STARTED", self.config.site_id, correlation_id, {
            "phase": "compute_kpis",
            "kpi_count": len(self._services),
        })

        results: List[KPIResult] = []
        for i, (name, service) in enumerate(self._services.items()):
            try:
                _emit_event("CREW_PROGRESS", self.config.site_id, correlation_id, {
                    "phase": "compute_kpis",
                    "kpi_name": name,
                    "index": i,
                    "total": len(self._services),
                })
                result = service.compute(
                    asset_data=asset_data,
                    alert_data=alert_data,
                    telemetry_summary=telemetry_summary,
                    health_data=health_data,
                )
                # Auto-approve high-confidence KPIs (configurable threshold)
                _approval_threshold = float(
                    getattr(self.config, 'auto_approval_threshold', 0.70)
                )
                if result.confidence >= _approval_threshold:
                    result.approve()
                results.append(result)
                _emit_event("KPI_COMPUTED", self.config.site_id, correlation_id, {
                    "kpi_name": name,
                    "savings_medium": result.savings_medium,
                    "confidence": result.confidence,
                    "status": result.status,
                })
            except Exception as e:
                logger.error("KPI %s computation failed: %s", name, e, exc_info=True)
                degraded_mode = True
                warnings_out.append(
                    self._warning(
                        "KPI_COMPUTATION_FAILED",
                        "KPI computation failed; returning partial scorecard with error status.",
                        site_id=self.config.site_id,
                        kpi_name=name,
                        error=str(e),
                    )
                )
                try:
                    from ...observability.metrics import metrics
                    metrics.record_kpi_computation_skipped(
                        site_id=self.config.site_id,
                        kpi_name=name,
                        reason="compute_exception",
                    )
                except Exception as metrics_err:
                    logger.debug("Metrics emission skipped (kpi compute failed): %s", metrics_err)
                results.append(KPIResult(
                    kpi_name=name,
                    display_name=service.display_name,
                    category=service.category,
                    narrative=f"Computation failed: {e}",
                    status="error",
                ))

        # Enrich with loweconex CrewAI crews when available
        results = enrich_results_with_crews(results, self.config)

        # T2-9 / T3-17: Recalibrate confidence from WO actuals and M&V
        try:
            from .recalibration import recalibrate_from_work_orders, recalibrate_from_mv
            results = recalibrate_from_work_orders(results, self.config)
            results = recalibrate_from_mv(results, self.config)
        except Exception as recal_err:
            logger.debug("Confidence recalibration skipped: %s", recal_err)
            degraded_mode = True
            warnings_out.append(
                self._warning(
                    "KPI_RECALIBRATION_SKIPPED",
                    "Confidence recalibration skipped due to non-fatal error.",
                    site_id=self.config.site_id,
                    error=str(recal_err),
                )
            )

        # Reconcile double-counting across KPIs
        _emit_event("CREW_PROGRESS", self.config.site_id, correlation_id, {
            "phase": "reconcile_double_counting",
        })
        reconciliation = reconcile_double_counting(results)

        # Sort by savings descending
        results.sort(key=lambda r: r.savings_medium, reverse=True)
        scorecards = [r.to_dict() for r in results]

        # ── 2. Executive summary ──────────────────────────────────
        approved = [r for r in results if r.status == "approved"]
        total_med_raw = sum(r.savings_medium for r in results)
        total_low = sum(r.savings_low for r in results)
        total_high = sum(r.savings_high for r in results)
        total_med = total_med_raw
        if reconciliation.get("reconciled"):
            total_med = float(reconciliation.get("total_after_reconciliation", total_med_raw))
            total_low = float(reconciliation.get("total_after_reconciliation_low", total_low))
            total_high = float(reconciliation.get("total_after_reconciliation_high", total_high))

        avg_confidence = (
            sum(r.confidence for r in results) / len(results)
            if results else 0
        )

        executive_summary = {
            "total_savings_medium": round(total_med, 2),
            "total_savings_low": round(total_low, 2),
            "total_savings_high": round(total_high, 2),
            "kpi_count": len(results),
            "approved_kpis": len(approved),
            "avg_confidence": round(avg_confidence, 3),
            "narrative": (
                f"Analysis of {len(results)} KPI dimensions "
                f"({len(approved)} approved) identifies "
                f"${total_med:,.0f} in annual savings (medium estimate). "
                f"Range: ${total_low:,.0f} – ${total_high:,.0f}."
            ),
            "total_savings_medium_raw_pre_reconciliation": round(total_med_raw, 2),
        }

        # ── 3. Scenario comparison (re-run KPIs with varied params) ─
        scenarios = self._compute_scenario_comparison(
            asset_data=asset_data,
            alert_data=alert_data,
            telemetry_summary=telemetry_summary,
            health_data=health_data,
            warnings_out=warnings_out,
        )

        # ── 4. Strategic recommendations ──────────────────────────
        recs = self._generate_recommendations(results)
        decision_advisory = {
            "strategic_recommendations": [
                {
                    "priority": r.priority,
                    "title": r.title,
                    "impact": r.impact,
                    "savings_impact": round(r.savings_impact, 2),
                    "rationale": r.rationale,
                }
                for r in recs
            ],
            "executive_narrative": (
                f"The platform identifies ${total_med:,.0f}+ in annual savings "
                f"across {len(results)} KPI dimensions. "
                f"Priority investments yield the highest risk-adjusted returns."
            ),
        }

        # ── 5. Location ranking ───────────────────────────────────
        location_ranking = self._rank_locations(
            results, asset_data, health_data, location_map, warnings_out=warnings_out
        )

        # ── 6. ROI calculation ────────────────────────────────────
        roi = self._compute_roi(total_med, implementation_cost)

        # ── 7. Governance modules ─────────────────────────────────
        governance = self._check_governance()
        if governance.get("warnings"):
            warnings_out.extend(governance.get("warnings", []))
            degraded_mode = True
        governance["loweconex_bridge"] = get_bridge_status()
        if reconciliation.get("reconciled"):
            governance["savings_reconciliation"] = reconciliation
            governance["savings_reconciliation"]["total_savings_medium_raw_pre_reconciliation"] = round(
                total_med_raw, 2
            )

        dashboard = KPIDashboardResult(
            site_id=self.config.site_id,
            executive_summary=executive_summary,
            scorecards=scorecards,
            scenario_comparison=scenarios,
            decision_advisory=decision_advisory,
            location_ranking=location_ranking,
            roi=roi,
            governance=governance,
            data_source="deterministic_kpi_orchestrator",
            degraded_mode=degraded_mode,
            warnings=warnings_out,
        )

        _emit_event("CREW_COMPLETED", self.config.site_id, correlation_id, {
            "phase": "dashboard_complete",
            "kpi_count": len(results),
            "total_savings_medium": total_med,
            "approved_kpis": len(approved),
        })

        return dashboard

    # ── Scenario parameter profiles ─────────────────────────────────
    # Each profile applies multipliers to relevant KPIConfig fields so
    # the same KPI services re-compute with different assumptions.
    SCENARIO_PROFILES = {
        "conservative": {
            "description": "Low-risk improvements: shorter rollout, higher costs, lower reduction targets",
            "overrides": {
                "baseline_reactive_wo_per_month": 0.90,       # assume 10% fewer WOs in baseline
                "energy_cost_per_kwh": 1.0,                    # no energy cost uplift
                "avg_wo_cost": 0.85,                           # lower WO cost assumption
                "baseline_leak_rate_pct": 0.80,                # less leakage baseline
                "avg_temp_excursion_events_per_month": 0.80,   # fewer excursions
                "hourly_downtime_cost": 0.85,                  # lower downtime cost
                "baseline_dispatches_per_month": 0.90,         # fewer dispatches
                "baseline_calls_per_month": 0.90,
            },
        },
        "moderate": {
            "description": "Balanced scenario: current baselines, medium assumptions",
            "overrides": {},  # use existing config as-is
        },
        "aggressive": {
            "description": "Full optimization: higher baselines, faster rollout, maximum reduction targets",
            "overrides": {
                "baseline_reactive_wo_per_month": 1.20,
                "energy_cost_per_kwh": 1.10,
                "avg_wo_cost": 1.15,
                "baseline_leak_rate_pct": 1.25,
                "avg_temp_excursion_events_per_month": 1.30,
                "hourly_downtime_cost": 1.20,
                "baseline_dispatches_per_month": 1.15,
                "baseline_calls_per_month": 1.20,
            },
        },
    }

    @staticmethod
    def _data_fingerprint(
        asset_data: List[Dict[str, Any]],
        alert_data: List[Dict[str, Any]],
        telemetry_summary: Dict[str, Any],
    ) -> str:
        """Cheap hash of input data for cache invalidation."""
        parts = [
            str(len(asset_data)),
            str(len(alert_data)),
            str(sorted(telemetry_summary.items())),
        ]
        return hashlib.md5("|".join(parts).encode()).hexdigest()

    def _compute_scenario_comparison(
        self,
        asset_data: List[Dict[str, Any]],
        alert_data: List[Dict[str, Any]],
        telemetry_summary: Dict[str, Any],
        health_data: List[Dict[str, Any]],
        warnings_out: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Re-run KPI computations with varied parameter sets per scenario.

        Results are cached by a fingerprint of the input data so repeated
        calls with the same dataset skip re-computation.
        """
        cache_key = self._data_fingerprint(asset_data, alert_data, telemetry_summary)
        if cache_key in self._scenario_cache:
            logger.debug("Scenario comparison cache hit (key=%s)", cache_key[:8])
            return self._scenario_cache[cache_key]

        scenarios = [
            {
                "scenario_name": "baseline",
                "description": "Current operations without optimization",
                "total_savings_medium": 0,
            },
        ]

        for profile_name, profile in self.SCENARIO_PROFILES.items():
            try:
                # Build a modified config for this scenario
                scenario_config = copy.deepcopy(self.config)
                for param, multiplier in profile.get("overrides", {}).items():
                    current = getattr(scenario_config, param, None)
                    if current is not None and isinstance(current, (int, float)):
                        setattr(scenario_config, param, type(current)(current * multiplier))

                # Re-instantiate KPI services with the scenario config
                scenario_services = {
                    name: get_kpi_service(name, scenario_config)
                    for name in KPI_REGISTRY
                }

                # Compute all KPIs under this scenario
                scenario_total = 0.0
                for name, service in scenario_services.items():
                    try:
                        result = service.compute(
                            asset_data=asset_data,
                            alert_data=alert_data,
                            telemetry_summary=telemetry_summary,
                            health_data=health_data,
                        )
                        scenario_total += result.savings_medium
                    except Exception as exc:
                        logger.warning(
                            "Scenario KPI compute skipped: scenario=%s kpi=%s site_id=%s error=%s",
                            profile_name,
                            name,
                            self.config.site_id,
                            exc,
                        )
                        if warnings_out is not None:
                            warnings_out.append(
                                self._warning(
                                    "SCENARIO_KPI_SKIPPED",
                                    "Scenario KPI computation skipped due to non-fatal error.",
                                    site_id=self.config.site_id,
                                    scenario=profile_name,
                                    kpi_name=name,
                                    error=str(exc),
                                )
                            )
                        try:
                            from ...observability.metrics import metrics
                            metrics.record_kpi_computation_skipped(
                                site_id=self.config.site_id,
                                kpi_name=name,
                                reason=f"scenario:{profile_name}",
                            )
                        except Exception as metrics_err:
                            logger.debug("Metrics emission skipped (scenario kpi skipped): %s", metrics_err)

                scenarios.append({
                    "scenario_name": profile_name,
                    "description": profile["description"],
                    "total_savings_medium": round(scenario_total, 2),
                })
            except Exception as e:
                logger.warning("Scenario '%s' computation failed: %s", profile_name, e)
                scenarios.append({
                    "scenario_name": profile_name,
                    "description": profile["description"],
                    "total_savings_medium": 0,
                })

        # Evict oldest entry if cache grows beyond 8 entries
        if len(self._scenario_cache) >= 8:
            oldest_key = next(iter(self._scenario_cache))
            del self._scenario_cache[oldest_key]
        self._scenario_cache[cache_key] = scenarios
        return scenarios

    def _generate_recommendations(
        self, results: List[KPIResult]
    ) -> List[StrategicRecommendation]:
        """Generate prioritized recommendations from KPI results."""
        recs = []
        priority = 1

        # Top KPIs by savings * confidence = risk-adjusted value
        scored = sorted(
            results,
            key=lambda r: r.savings_medium * r.confidence,
            reverse=True,
        )

        titles_map = {
            "asset_failure_prediction": "Deploy PdM models fleet-wide",
            "energy_reduction": "Optimize energy efficiency across degraded assets",
            "refrigerant_leak_reduction": "Accelerate refrigerant leak detection",
            "food_safety_compliance": "Implement food safety monitoring",
            "capex_lifecycle_optimization": "Execute CapEx replacement program",
            "work_order_reduction": "Shift reactive maintenance to planned",
            "asset_uptime_increase": "Maximize asset uptime via predictive alerts",
            "service_bureau_reduction": "Reduce third-party service dispatches",
        }

        for r in scored[:6]:
            if r.savings_medium <= 0:
                continue
            title = titles_map.get(r.kpi_name, f"Optimize {r.display_name}")
            impact = "high" if r.savings_medium * r.confidence > 30_000 else "medium"
            recs.append(StrategicRecommendation(
                priority=priority,
                title=title,
                impact=impact,
                savings_impact=r.savings_medium,
                rationale=r.narrative,
            ))
            priority += 1

        # ── Cross-KPI action-centric recommendations ──────────────────
        # Identify actions that improve multiple KPIs simultaneously.
        cross_kpi_actions = self._generate_cross_kpi_actions(results)
        for action in cross_kpi_actions:
            recs.append(StrategicRecommendation(
                priority=priority,
                title=action["title"],
                impact=action["impact"],
                savings_impact=action["savings_impact"],
                rationale=action["rationale"],
            ))
            priority += 1

        return recs

    @staticmethod
    def _generate_cross_kpi_actions(
        results: List[KPIResult],
    ) -> List[Dict[str, Any]]:
        """Generate action-centric recommendations that span multiple KPIs.

        Instead of one recommendation per KPI, this identifies actions that
        improve several KPIs simultaneously (resource optimization, sequencing).
        """
        actions = []
        kpi_map = {r.kpi_name: r for r in results if r.savings_medium > 0}

        # Action: Refrigerant leak detection improves energy + ESG + food safety
        leak_kpis = ["refrigerant_leak_reduction", "esg_carbon_reduction", "energy_reduction", "food_safety_compliance"]
        leak_hits = [kpi_map[k] for k in leak_kpis if k in kpi_map]
        if len(leak_hits) >= 2:
            total = sum(r.savings_medium for r in leak_hits)
            actions.append({
                "title": f"Invest in refrigerant leak detection (improves {len(leak_hits)} KPIs)",
                "impact": "high" if total > 50_000 else "medium",
                "savings_impact": round(total, 2),
                "rationale": (
                    "Leak detection simultaneously improves "
                    + ", ".join(r.display_name for r in leak_hits)
                    + f", delivering ${total:,.0f} combined savings."
                ),
            })

        # Action: Condition-based PM improves WO reduction + uptime + service bureau
        pm_kpis = ["work_order_reduction", "asset_uptime_increase", "service_bureau_reduction", "preventive_maintenance_optimization"]
        pm_hits = [kpi_map[k] for k in pm_kpis if k in kpi_map]
        if len(pm_hits) >= 2:
            total = sum(r.savings_medium for r in pm_hits)
            actions.append({
                "title": f"Deploy condition-based maintenance (improves {len(pm_hits)} KPIs)",
                "impact": "high" if total > 40_000 else "medium",
                "savings_impact": round(total, 2),
                "rationale": (
                    f"Shifting to condition-based PM simultaneously reduces work orders, "
                    f"increases uptime, and cuts service dispatch costs — ${total:,.0f} combined."
                ),
            })

        # Action: Energy optimization funds PM optimization
        if "energy_reduction" in kpi_map and "capex_lifecycle_optimization" in kpi_map:
            e = kpi_map["energy_reduction"]
            c = kpi_map["capex_lifecycle_optimization"]
            actions.append({
                "title": "Sequence: energy savings fund CapEx program",
                "impact": "medium",
                "savings_impact": round(e.savings_medium + c.savings_medium, 2),
                "rationale": (
                    f"Deploy energy optimization first (${e.savings_medium:,.0f}/yr) "
                    f"to generate cash flow that funds the CapEx replacement program "
                    f"(${c.savings_medium:,.0f}/yr NPV)."
                ),
            })

        return actions[:3]  # Limit to top 3 cross-KPI actions

    def _rank_locations(
        self,
        results: List[KPIResult],
        asset_data: List[Dict[str, Any]],
        health_data: List[Dict[str, Any]],
        location_map: Optional[Dict[str, Dict[str, Any]]],
        warnings_out: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Rank locations by total savings potential.

        Computes KPIs per location by filtering data to each location's
        assets and re-running the KPI services, producing genuine
        per-location savings instead of proportional allocation.
        """
        if not location_map:
            # Build from asset data
            loc_assets: Dict[str, List[str]] = {}
            for a in asset_data:
                sid = a.get("site_id", "unknown")
                loc_assets.setdefault(sid, []).append(a.get("asset_id", ""))
            location_map = {
                sid: {"address": f"Site {sid}", "asset_ids": aids}
                for sid, aids in loc_assets.items()
            }

        if not location_map:
            return []

        # Circuit breaker: limit to top-N locations by asset count to prevent
        # O(N×14) KPI recomputations on large fleets.
        _MAX_RANKED = int(getattr(self.config, 'max_ranked_locations', 10))
        if len(location_map) > _MAX_RANKED:
            sorted_locs = sorted(
                location_map.items(),
                key=lambda x: len(x[1].get('asset_ids', [])),
                reverse=True,
            )
            location_map = dict(sorted_locs[:_MAX_RANKED])
            logger.info("Location ranking limited to top %d locations (of %d)", _MAX_RANKED, len(sorted_locs))

        # ── Parallelised location ranking ────────────────────────────
        def _rank_single_location(loc_id: str, info: dict) -> Dict[str, Any]:
            loc_asset_ids = set(info.get("asset_ids", []))
            n_loc_assets = len(loc_asset_ids)

            loc_asset_data = [
                a for a in asset_data
                if a.get("asset_id") in loc_asset_ids
            ]
            loc_alert_data_raw = [
                a for a in (self._last_alert_data or [])
                if a.get("asset_id") in loc_asset_ids
            ] if hasattr(self, '_last_alert_data') and self._last_alert_data else []
            loc_health_data = [
                h for h in health_data
                if h.get("asset_id") in loc_asset_ids
            ]

            global_count = self._last_telemetry_summary.get("telemetry_count", 0) if hasattr(self, '_last_telemetry_summary') and self._last_telemetry_summary else 0
            global_assets = max(len(asset_data), 1)
            loc_fraction = n_loc_assets / global_assets

            loc_telemetry = {
                "telemetry_count": int(global_count * loc_fraction),
                "avg_compressor_power_kw": (
                    self._last_telemetry_summary.get("avg_compressor_power_kw", 0)
                    if hasattr(self, '_last_telemetry_summary') and self._last_telemetry_summary else 0
                ),
                "total_compressor_hours": (
                    (self._last_telemetry_summary.get("total_compressor_hours", 0) * loc_fraction)
                    if hasattr(self, '_last_telemetry_summary') and self._last_telemetry_summary else 0
                ),
            }

            loc_config = copy.deepcopy(self.config)
            loc_config.total_assets = max(n_loc_assets, 1)
            loc_config.total_locations = 1
            loc_config.baseline_annual_kwh = self.config.baseline_annual_kwh * loc_fraction

            loc_total = 0.0
            loc_kpi_savings: Dict[str, float] = {}
            computed_count = 0

            for name, _cls in KPI_REGISTRY.items():
                try:
                    svc = get_kpi_service(name, loc_config)
                    r = svc.compute(
                        asset_data=loc_asset_data,
                        alert_data=loc_alert_data_raw,
                        telemetry_summary=loc_telemetry,
                        health_data=loc_health_data,
                    )
                    loc_total += r.savings_medium
                    loc_kpi_savings[name] = r.savings_medium
                    computed_count += 1
                except Exception as exc:
                    logger.warning(
                        "Location KPI compute skipped: site_id=%s location_id=%s kpi=%s error=%s",
                        self.config.site_id,
                        loc_id,
                        name,
                        exc,
                    )
                    if warnings_out is not None:
                        warnings_out.append(
                            self._warning(
                                "LOCATION_KPI_SKIPPED",
                                "Location KPI computation skipped due to non-fatal error.",
                                site_id=self.config.site_id,
                                location_id=loc_id,
                                kpi_name=name,
                                error=str(exc),
                            )
                        )
                    try:
                        from ...observability.metrics import metrics
                        metrics.record_kpi_computation_skipped(
                            site_id=self.config.site_id,
                            kpi_name=name,
                            reason=f"location:{loc_id}",
                        )
                    except Exception as metrics_err:
                        logger.debug("Metrics emission skipped (location kpi skipped): %s", metrics_err)

            top_kpi = max(loc_kpi_savings, key=loc_kpi_savings.get) if loc_kpi_savings else ""

            degraded = sum(
                1 for h in loc_health_data
                if h.get("health_score") is not None and h.get("health_score", 100) < 70
            )

            return {
                "location_id": loc_id,
                "address": info.get("address", ""),
                "total_savings": round(loc_total, 2),
                "kpi_count": computed_count,
                "top_kpi": top_kpi,
                "asset_count": n_loc_assets,
                "degraded_count": degraded,
            }

        rankings: List[Dict[str, Any]] = []
        n_locations = len(location_map)
        if n_locations <= 1:
            # Single location — no need for thread pool overhead
            for lid, info in location_map.items():
                rankings.append(_rank_single_location(lid, info))
        else:
            workers = min(self._LOCATION_WORKERS, n_locations)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(_rank_single_location, lid, info): lid
                    for lid, info in location_map.items()
                }
                for future in as_completed(futures):
                    try:
                        rankings.append(future.result())
                    except Exception as e:
                        lid = futures[future]
                        logger.warning("Location ranking failed for %s: %s", lid, e)

        rankings.sort(key=lambda x: x["total_savings"], reverse=True)
        return rankings

    def _compute_roi(
        self, annual_savings: float, implementation_cost: float
    ) -> Dict[str, Any]:
        """Compute ROI metrics."""
        if annual_savings <= 0:
            return {"payback_months": 0, "npv": 0, "irr": 0, "savings_to_cost_multiple": 0}

        payback_months = (implementation_cost / annual_savings) * 12 if annual_savings > 0 else 0
        discount_rate = self.config.discount_rate
        horizon_years = 5

        # NPV
        npv = -implementation_cost
        for yr in range(1, horizon_years + 1):
            npv += annual_savings / ((1 + discount_rate) ** yr)

        # Savings-to-cost multiple
        multiple = (annual_savings * horizon_years) / max(implementation_cost, 1)

        # Simplified IRR approximation
        irr = 0.0
        if implementation_cost > 0:
            irr = (annual_savings / implementation_cost) - discount_rate

        return {
            "payback_months": round(payback_months, 1),
            "npv": round(npv, 0),
            "irr": round(max(0, irr), 3),
            "savings_to_cost_multiple": round(multiple, 1),
            "assumptions": {
                "discount_rate": discount_rate,
                "horizon_years": horizon_years,
                "implementation_cost": implementation_cost,
                "annual_savings_input": round(annual_savings, 2),
                "data_source": "KPI crew pipeline (14 dimensions, fleet-wide)",
            },
        }

    def _check_governance(self) -> Dict[str, Any]:
        """Check which governance modules are active."""
        active_modules = []
        warnings: List[Dict[str, Any]] = []

        def _probe(module_import: str, label: str):
            try:
                __import__(module_import, fromlist=["*"])
                active_modules.append(label)
            except Exception as exc:
                logger.info(
                    "Governance module not active: site_id=%s module=%s error=%s",
                    self.config.site_id,
                    label,
                    exc,
                )
                warnings.append(
                    self._warning(
                        "GOVERNANCE_MODULE_INACTIVE",
                        "Optional governance module unavailable.",
                        site_id=self.config.site_id,
                        module=label,
                        error=str(exc),
                    )
                )

        _probe("loweconex_platform.lineage", "lineage")
        _probe("loweconex_platform.data_quality", "data_quality")
        _probe("loweconex_platform.mlops", "mlops")
        _probe("loweconex_platform.agent_ops", "agent_ops")
        _probe("loweconex_platform.ai_risk", "ai_risk")
        return {"modules_active": active_modules, "warnings": warnings}
