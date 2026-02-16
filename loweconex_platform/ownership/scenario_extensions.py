"""
Scenario Extensions — owner-scoped scenarios with parameter hierarchy
integration for the ownership-aware decision support module.

Extends the existing ScenarioAgent with owner-specific overrides,
geography comparison, and compliance strictness toggles.
"""

from __future__ import annotations

import copy
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from loweconex_platform.ownership.parameter_hierarchy import ParameterHierarchy

logger = logging.getLogger(__name__)


@dataclass
class OwnershipScenario:
    """
    A scenario with ownership-aware parameter overrides.

    Supports per-owner budget constraints, geography-specific
    parameters, and compliance strictness toggles.
    """
    scenario_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "baseline"
    description: str = ""
    status: str = "draft"  # draft, review, approved, archived

    # Scope
    region: str = ""
    banner: str = ""
    store: str = ""

    # Parameter overrides (param_id → value)
    parameter_overrides: Dict[str, float] = field(default_factory=dict)

    # Owner-specific budget overrides (owner_role → budget)
    owner_budget_overrides: Dict[str, float] = field(default_factory=dict)

    # Metadata
    created_by: str = ""
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    approved_by: Optional[str] = None
    approved_ts: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "region": self.region,
            "banner": self.banner,
            "store": self.store,
            "parameter_overrides": self.parameter_overrides,
            "owner_budget_overrides": self.owner_budget_overrides,
            "created_by": self.created_by,
            "created_ts": self.created_ts,
            "approved_by": self.approved_by,
            "approved_ts": self.approved_ts,
        }


class ScenarioManager:
    """
    Manages ownership-aware scenarios with parameter hierarchy integration.
    """

    def __init__(self, parameter_hierarchy: ParameterHierarchy):
        self._hierarchy = parameter_hierarchy
        self._scenarios: Dict[str, OwnershipScenario] = {}
        self._create_default_scenarios()

    # ── CRUD ────────────────────────────────────────────────────────

    def create(
        self,
        name: str,
        description: str = "",
        region: str = "",
        banner: str = "",
        store: str = "",
        parameter_overrides: Optional[Dict[str, float]] = None,
        owner_budget_overrides: Optional[Dict[str, float]] = None,
        created_by: str = "user",
    ) -> OwnershipScenario:
        scenario = OwnershipScenario(
            name=name,
            description=description,
            region=region,
            banner=banner,
            store=store,
            parameter_overrides=parameter_overrides or {},
            owner_budget_overrides=owner_budget_overrides or {},
            created_by=created_by,
        )
        self._scenarios[scenario.scenario_id] = scenario
        logger.info(f"Created scenario: {name} ({scenario.scenario_id})")
        return scenario

    def get(self, scenario_id: str) -> Optional[OwnershipScenario]:
        return self._scenarios.get(scenario_id)

    def list_all(self) -> List[OwnershipScenario]:
        return list(self._scenarios.values())

    def update_status(self, scenario_id: str, status: str, by: str = "user") -> bool:
        scenario = self._scenarios.get(scenario_id)
        if not scenario:
            return False
        valid_transitions = {
            "draft": ["review"],
            "review": ["approved", "draft"],
            "approved": ["archived"],
            "archived": [],
        }
        if status not in valid_transitions.get(scenario.status, []):
            logger.warning(f"Invalid status transition: {scenario.status} → {status}")
            return False
        scenario.status = status
        if status == "approved":
            scenario.approved_by = by
            scenario.approved_ts = datetime.utcnow().isoformat()
        return True

    def delete(self, scenario_id: str) -> bool:
        scenario = self._scenarios.get(scenario_id)
        if scenario and scenario.status == "draft":
            del self._scenarios[scenario_id]
            return True
        return False

    # ── Resolution ──────────────────────────────────────────────────

    def resolve_parameters(self, scenario_id: str) -> Dict[str, float]:
        """
        Resolve all parameters for a scenario, applying hierarchy
        inheritance plus scenario-specific overrides.
        """
        scenario = self._scenarios.get(scenario_id)
        if not scenario:
            return {}

        # Start with hierarchy-resolved values
        resolved = self._hierarchy.resolve_flat(
            store=scenario.store,
            banner=scenario.banner,
            region=scenario.region,
        )

        # Apply scenario-specific overrides
        for param_id, value in scenario.parameter_overrides.items():
            resolved[param_id] = value

        return resolved

    def resolve_metric_inputs(
        self,
        scenario_id: str,
        base_metric_inputs: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Resolve metric inputs for a scenario by applying parameter
        overrides to base metric inputs.
        """
        params = self.resolve_parameters(scenario_id)
        resolved = copy.deepcopy(base_metric_inputs)

        # Map parameter IDs to metric input keys
        param_to_input = {
            "p_response_time_mean": "response_time_hours",
            "p_internal_labor_rate": "internal_labor_rate",
            "p_vendor_labor_rate": "vendor_labor_rate",
            "p_electricity_rate": "electricity_rate",
            "p_carbon_price": "carbon_price",
            "p_discount_rate": "discount_rate",
            "p_downtime_cost_per_hour": "downtime_cost_per_hour",
            "p_regulatory_strictness": "regulatory_strictness",
            "p_penalty_per_incident": "avg_penalty",
            "p_refrigerant_cost_per_lb": "refrigerant_cost_per_lb",
            "p_capex_budget": "capex_budget",
            "p_opex_budget": "opex_budget",
            "p_sensor_coverage": "sensor_coverage",
            "p_avg_asset_age": "avg_asset_age",
        }

        for param_id, value in params.items():
            input_key = param_to_input.get(param_id)
            if input_key:
                for metric_id in resolved:
                    if input_key in resolved[metric_id]:
                        resolved[metric_id][input_key] = value

        return resolved

    # ── Presets ──────────────────────────────────────────────────────

    def _create_default_scenarios(self):
        """Create baseline, conservative, and aggressive scenarios."""
        self.create(
            name="Baseline",
            description="Current state with default parameters — no interventions.",
            created_by="system",
        )
        self.create(
            name="Conservative",
            description="Conservative assumptions: lower adoption speed, higher costs, lower savings rates.",
            parameter_overrides={
                "p_response_time_mean": 6.0,
                "p_electricity_rate": 0.10,
                "p_downtime_cost_per_hour": 300.0,
                "p_regulatory_strictness": 1.0,
                "p_capex_budget": 500000.0,
                "p_carbon_price": 25.0,
            },
            created_by="system",
        )
        self.create(
            name="Aggressive",
            description="Aggressive assumptions: fast rollout, maximum savings targets, full budget.",
            parameter_overrides={
                "p_response_time_mean": 2.0,
                "p_electricity_rate": 0.15,
                "p_downtime_cost_per_hour": 800.0,
                "p_regulatory_strictness": 3.0,
                "p_capex_budget": 2000000.0,
                "p_carbon_price": 100.0,
            },
            created_by="system",
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenarios": {sid: s.to_dict() for sid, s in self._scenarios.items()},
            "count": len(self._scenarios),
        }
