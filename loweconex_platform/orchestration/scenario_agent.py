"""
Scenario Agent — manipulates assumptions and requests KPI re-runs
to produce what-if scenario comparisons.

Supports Conservative, Expected, and Aggressive scenario profiles
plus custom parameter overrides.
"""

from __future__ import annotations

import copy
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Scenario Definitions
# =============================================================================

@dataclass
class ScenarioParameters:
    """A set of manipulable parameters for a scenario run."""
    scenario_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    scenario_name: str = "baseline"
    description: str = ""

    # Adoption / rollout
    rollout_stores_per_month: int = 50
    rollout_start_month: int = 1

    # Alert and classification thresholds
    alert_confidence_threshold: float = 0.7
    classification_confidence_threshold: float = 0.8

    # Cost rates
    internal_labor_rate: float = 65.0
    overtime_premium: float = 1.5
    vendor_rate_multiplier: float = 1.0

    # Energy
    electricity_rate: float = 0.12
    gas_rate: float = 1.20
    energy_reduction_pct: float = 0.12

    # Refrigerant
    refrigerant_cost_per_lb: float = 15.0
    baseline_leak_rate: float = 0.20
    target_leak_rate: float = 0.10
    leak_detection_coverage: str = "periodic"  # "periodic" | "continuous"

    # PM
    pm_interval_adjustment: float = 1.0  # 1.0 = no change; 0.8 = 20% fewer tasks
    pm_cost_per_task: float = 150.0

    # CapEx
    capex_budget: float = 1_000_000.0
    hurdle_rate: float = 0.08

    # Work orders
    cost_per_wo: float = 350.0
    wo_reduction_pct: float = 0.25

    # Food
    shrink_reduction_pct: float = 0.30

    # Call center
    deflection_rate: float = 0.30
    cost_per_call: float = 25.0

    # Emissions
    carbon_credit_value: float = 50.0

    def to_kpi_params(self) -> Dict[str, Any]:
        """Convert to flat dict for KPI crew scenario_params."""
        return {
            "rollout_stores_per_month": self.rollout_stores_per_month,
            "alert_confidence_threshold": self.alert_confidence_threshold,
            "electricity_rate": self.electricity_rate,
            "energy_reduction_pct": self.energy_reduction_pct,
            "refrigerant_cost_per_lb": self.refrigerant_cost_per_lb,
            "baseline_leak_rate": self.baseline_leak_rate,
            "target_leak_rate": self.target_leak_rate,
            "pm_cost_per_task": self.pm_cost_per_task,
            "annual_capex_budget": self.capex_budget,
            "discount_rate": self.hurdle_rate,
            "cost_per_wo": self.cost_per_wo,
            "wo_reduction_pct": self.wo_reduction_pct,
            "shrink_reduction_pct": self.shrink_reduction_pct,
            "deflection_rate": self.deflection_rate,
            "cost_per_call": self.cost_per_call,
            "carbon_credit_value": self.carbon_credit_value,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "description": self.description,
            **self.to_kpi_params(),
            "leak_detection_coverage": self.leak_detection_coverage,
            "internal_labor_rate": self.internal_labor_rate,
            "overtime_premium": self.overtime_premium,
            "vendor_rate_multiplier": self.vendor_rate_multiplier,
        }


# =============================================================================
# Pre-built Scenario Profiles
# =============================================================================

CONSERVATIVE_SCENARIO = ScenarioParameters(
    scenario_name="conservative",
    description="Conservative assumptions: lower adoption speed, higher costs, lower savings rates.",
    rollout_stores_per_month=25,
    energy_reduction_pct=0.08,
    wo_reduction_pct=0.15,
    target_leak_rate=0.14,
    shrink_reduction_pct=0.15,
    deflection_rate=0.15,
    capex_budget=500_000,
)

EXPECTED_SCENARIO = ScenarioParameters(
    scenario_name="expected",
    description="Expected case: moderate adoption, standard cost assumptions, achievable savings.",
    rollout_stores_per_month=50,
    energy_reduction_pct=0.12,
    wo_reduction_pct=0.25,
    target_leak_rate=0.10,
    shrink_reduction_pct=0.30,
    deflection_rate=0.30,
    capex_budget=1_000_000,
)

AGGRESSIVE_SCENARIO = ScenarioParameters(
    scenario_name="aggressive",
    description="Aggressive assumptions: fast rollout, maximum savings targets, full budget.",
    rollout_stores_per_month=100,
    energy_reduction_pct=0.18,
    wo_reduction_pct=0.40,
    target_leak_rate=0.06,
    leak_detection_coverage="continuous",
    shrink_reduction_pct=0.50,
    deflection_rate=0.50,
    capex_budget=2_000_000,
)


# =============================================================================
# Scenario Agent
# =============================================================================

class ScenarioAgent:
    """
    Manages scenario creation, parameter manipulation, and comparison.
    
    Produces 3 standard scenarios (Conservative, Expected, Aggressive)
    plus supports custom parameter overrides. Determines which KPI crews
    need re-computation when parameters change.
    """

    # Map parameters to affected KPIs
    PARAMETER_KPI_MAP = {
        "electricity_rate": ["energy_reduction", "esg_compliance"],
        "energy_reduction_pct": ["energy_reduction", "esg_compliance"],
        "baseline_leak_rate": ["refrigerant_leak_reduction", "esg_compliance"],
        "target_leak_rate": ["refrigerant_leak_reduction", "esg_compliance"],
        "refrigerant_cost_per_lb": ["refrigerant_leak_reduction"],
        "cost_per_wo": ["work_order_reduction"],
        "wo_reduction_pct": ["work_order_reduction"],
        "pm_cost_per_task": ["preventive_maintenance_optimization", "ppm_maximization"],
        "shrink_reduction_pct": ["food_waste_reduction"],
        "deflection_rate": ["call_center_volume_reduction"],
        "cost_per_call": ["call_center_volume_reduction"],
        "capex_budget": ["capex_lifecycle_optimization"],
        "hurdle_rate": ["capex_lifecycle_optimization"],
        "carbon_credit_value": ["esg_compliance"],
    }

    def __init__(self):
        self._scenarios: Dict[str, ScenarioParameters] = {}
        self._results: Dict[str, Dict[str, Any]] = {}

    def get_standard_scenarios(self) -> List[ScenarioParameters]:
        """Get the three standard scenario profiles."""
        return [
            copy.deepcopy(CONSERVATIVE_SCENARIO),
            copy.deepcopy(EXPECTED_SCENARIO),
            copy.deepcopy(AGGRESSIVE_SCENARIO),
        ]

    def create_custom_scenario(
        self,
        name: str,
        description: str = "",
        base: str = "expected",
        overrides: Optional[Dict[str, Any]] = None,
    ) -> ScenarioParameters:
        """Create a custom scenario from a base profile with overrides."""
        bases = {
            "conservative": CONSERVATIVE_SCENARIO,
            "expected": EXPECTED_SCENARIO,
            "aggressive": AGGRESSIVE_SCENARIO,
        }
        scenario = copy.deepcopy(bases.get(base, EXPECTED_SCENARIO))
        scenario.scenario_id = str(uuid.uuid4())
        scenario.scenario_name = name
        scenario.description = description

        if overrides:
            for key, value in overrides.items():
                if hasattr(scenario, key):
                    setattr(scenario, key, value)

        self._scenarios[scenario.scenario_id] = scenario
        return scenario

    def get_affected_kpis(
        self, base_params: Dict[str, Any], new_params: Dict[str, Any]
    ) -> List[str]:
        """
        Determine which KPIs need re-computation based on parameter changes.
        Only requests re-run when a parameter change affects inputs materially.
        """
        affected = set()
        for param_name, new_value in new_params.items():
            old_value = base_params.get(param_name)
            if old_value != new_value:
                kpis = self.PARAMETER_KPI_MAP.get(param_name, [])
                affected.update(kpis)
        return sorted(affected)

    def store_scenario_result(self, scenario_id: str, result: Dict[str, Any]):
        """Store the result of a scenario run."""
        self._results[scenario_id] = {
            "scenario_id": scenario_id,
            "result": result,
            "completed_ts": datetime.utcnow().isoformat(),
        }

    def compare_scenarios(
        self, scenario_results: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Compare multiple scenario results side by side.
        
        Returns comparison matrix with deltas and rankings.
        """
        if not scenario_results:
            return {"error": "No scenarios to compare"}

        comparison = {
            "scenarios": {},
            "ranking_by_total_savings": [],
            "ranking_by_payback": [],
        }

        scenarios_with_totals = []

        for scenario_name, result in scenario_results.items():
            totals = result.get("reconciled_totals", {})
            savings_med = totals.get("total_savings_medium", 0)
            scenarios_with_totals.append((scenario_name, savings_med))

            comparison["scenarios"][scenario_name] = {
                "total_savings_low": totals.get("total_savings_low", 0),
                "total_savings_medium": savings_med,
                "total_savings_high": totals.get("total_savings_high", 0),
                "by_category": totals.get("by_category", {}),
            }

        # Rank by total savings
        scenarios_with_totals.sort(key=lambda x: x[1], reverse=True)
        comparison["ranking_by_total_savings"] = [
            {"rank": i + 1, "scenario": name, "savings_medium": val}
            for i, (name, val) in enumerate(scenarios_with_totals)
        ]

        # Compute deltas between scenarios
        if len(scenario_results) >= 2:
            names = list(scenario_results.keys())
            baseline = comparison["scenarios"].get(names[0], {})
            for other_name in names[1:]:
                other = comparison["scenarios"].get(other_name, {})
                comparison[f"delta_{names[0]}_vs_{other_name}"] = {
                    "savings_medium_delta": other.get("total_savings_medium", 0) - baseline.get("total_savings_medium", 0),
                }

        return comparison

    def generate_reconciliation_plan(self, scenario_params: ScenarioParameters) -> Dict[str, Any]:
        """
        Generate a reconciliation plan to avoid double-counting
        for a given scenario.
        """
        return {
            "scenario_id": scenario_params.scenario_id,
            "scenario_name": scenario_params.scenario_name,
            "reconciliation_rules": [
                {
                    "rule": "energy_from_leak_repair",
                    "description": "Energy savings from restored refrigerant efficiency counted in Energy KPI, not Leak KPI",
                    "winner_kpi": "energy_reduction",
                    "loser_kpi": "refrigerant_leak_reduction",
                    "savings_type": "energy",
                },
                {
                    "rule": "labor_wo_vs_pm",
                    "description": "Labor savings from WO reduction take precedence over PM labor savings",
                    "winner_kpi": "work_order_reduction",
                    "loser_kpi": "ppm_maximization",
                    "savings_type": "labor",
                },
                {
                    "rule": "emissions_scope_assignment",
                    "description": "ESG KPI owns all emissions reporting; other KPIs provide input quantities only",
                    "winner_kpi": "esg_compliance",
                    "loser_kpi": "*",
                    "savings_type": "emissions",
                },
            ],
            "manipulated_parameters": {
                k: v for k, v in scenario_params.to_kpi_params().items()
                if v != getattr(EXPECTED_SCENARIO, k, None)
            },
        }
