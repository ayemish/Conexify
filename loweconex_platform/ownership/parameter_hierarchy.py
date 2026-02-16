"""
Parameter Hierarchy — 4-level inheritance system for decision parameters.

Supports Global → Region → Banner → Store inheritance with override
resolution, audit trail, and sensitivity ranking.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ParameterCategory(str, Enum):
    GEOGRAPHY = "geography"
    ASSET = "asset"
    STORE = "store"
    COMPLIANCE = "compliance"
    ENERGY = "energy"
    FINANCIAL = "financial"
    DATA_QUALITY = "data_quality"


class HierarchyLevel(str, Enum):
    GLOBAL = "global"
    REGION = "region"
    BANNER = "banner"
    STORE = "store"


@dataclass
class ParameterDefinition:
    """Definition of a single configurable parameter."""
    param_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    category: str = ParameterCategory.FINANCIAL.value
    default_value: float = 0.0
    unit: str = ""
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    step: Optional[float] = None            # slider step size
    sensitivity_rank: int = 0               # 1 = most sensitive
    is_slider: bool = False                 # show as quick slider control
    affects_quadrants: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "param_id": self.param_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "default_value": self.default_value,
            "unit": self.unit,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "step": self.step,
            "sensitivity_rank": self.sensitivity_rank,
            "is_slider": self.is_slider,
            "affects_quadrants": self.affects_quadrants,
        }


@dataclass
class ParameterOverride:
    """An override of a parameter at a specific hierarchy level."""
    override_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    param_id: str = ""
    level: str = HierarchyLevel.GLOBAL.value
    entity: str = ""                # e.g. region name, banner name, store ID
    value: float = 0.0
    reason: str = ""
    created_by: str = "system"
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "override_id": self.override_id,
            "param_id": self.param_id,
            "level": self.level,
            "entity": self.entity,
            "value": self.value,
            "reason": self.reason,
            "created_by": self.created_by,
            "created_ts": self.created_ts,
        }


class ParameterHierarchy:
    """
    Manages parameter definitions and 4-level override hierarchy.

    Resolution: Store > Banner > Region > Global > Default.
    Maintains an audit log of all changes.
    """

    def __init__(self):
        self._definitions: Dict[str, ParameterDefinition] = {}
        self._overrides: List[ParameterOverride] = []
        self._audit_log: List[Dict[str, Any]] = []
        self._seed_parameters()

    # ── Definition CRUD ─────────────────────────────────────────────

    def get_definition(self, param_id: str) -> Optional[ParameterDefinition]:
        return self._definitions.get(param_id)

    def list_definitions(self, category: Optional[str] = None) -> List[ParameterDefinition]:
        defs = list(self._definitions.values())
        if category:
            defs = [d for d in defs if d.category == category]
        return defs

    def list_slider_params(self) -> List[ParameterDefinition]:
        return [d for d in self._definitions.values() if d.is_slider]

    # ── Override management ─────────────────────────────────────────

    def set_override(
        self,
        param_id: str,
        level: str,
        entity: str,
        value: float,
        reason: str = "",
        created_by: str = "user",
    ) -> Optional[ParameterOverride]:
        """Set a parameter override at a given hierarchy level."""
        defn = self._definitions.get(param_id)
        if not defn:
            logger.warning(f"Parameter {param_id} not found")
            return None

        # Validate bounds
        if defn.min_value is not None and value < defn.min_value:
            logger.warning(f"Value {value} below min {defn.min_value} for {param_id}")
            value = defn.min_value
        if defn.max_value is not None and value > defn.max_value:
            logger.warning(f"Value {value} above max {defn.max_value} for {param_id}")
            value = defn.max_value

        override = ParameterOverride(
            param_id=param_id,
            level=level,
            entity=entity,
            value=value,
            reason=reason,
            created_by=created_by,
        )
        self._overrides.append(override)

        self._audit_log.append({
            "action": "set_override",
            "param_id": param_id,
            "param_name": defn.name,
            "level": level,
            "entity": entity,
            "value": value,
            "reason": reason,
            "created_by": created_by,
            "timestamp": datetime.utcnow().isoformat(),
        })

        logger.info(f"Override set: {defn.name} = {value} at {level}/{entity}")
        return override

    def resolve(
        self,
        param_id: str,
        store: str = "",
        banner: str = "",
        region: str = "",
    ) -> Dict[str, Any]:
        """
        Resolve effective parameter value walking up the hierarchy.

        Returns the value plus metadata about which level provided it.
        """
        defn = self._definitions.get(param_id)
        if not defn:
            return {"param_id": param_id, "value": 0.0, "source": "not_found"}

        # Walk hierarchy: Store → Banner → Region → Global
        hierarchy = [
            (HierarchyLevel.STORE.value, store),
            (HierarchyLevel.BANNER.value, banner),
            (HierarchyLevel.REGION.value, region),
            (HierarchyLevel.GLOBAL.value, ""),
        ]

        for level, entity in hierarchy:
            if not entity and level != HierarchyLevel.GLOBAL.value:
                continue
            # Find most recent override at this level
            matches = [
                o for o in self._overrides
                if o.param_id == param_id and o.level == level and o.entity == entity
            ]
            if matches:
                latest = max(matches, key=lambda o: o.created_ts)
                return {
                    "param_id": param_id,
                    "name": defn.name,
                    "value": latest.value,
                    "source": f"{level}/{entity}" if entity else level,
                    "override_id": latest.override_id,
                    "is_default": False,
                }

        # Fall back to definition default
        return {
            "param_id": param_id,
            "name": defn.name,
            "value": defn.default_value,
            "source": "default",
            "is_default": True,
        }

    def resolve_all(
        self,
        store: str = "",
        banner: str = "",
        region: str = "",
    ) -> Dict[str, Dict[str, Any]]:
        """Resolve all parameters for a given scope."""
        return {
            pid: self.resolve(pid, store=store, banner=banner, region=region)
            for pid in self._definitions
        }

    def resolve_flat(
        self,
        store: str = "",
        banner: str = "",
        region: str = "",
    ) -> Dict[str, float]:
        """Resolve all parameters as a flat {param_id: value} dict."""
        return {
            pid: self.resolve(pid, store=store, banner=banner, region=region)["value"]
            for pid in self._definitions
        }

    # ── Audit ───────────────────────────────────────────────────────

    def get_audit_log(self, param_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if param_id:
            return [e for e in self._audit_log if e.get("param_id") == param_id]
        return list(self._audit_log)

    # ── Serialization ───────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "definitions": {pid: d.to_dict() for pid, d in self._definitions.items()},
            "overrides": [o.to_dict() for o in self._overrides],
            "audit_log_count": len(self._audit_log),
        }

    # ── Seed ────────────────────────────────────────────────────────

    def _seed_parameters(self):
        """Seed with all parameter types from requirements §3.1."""
        seeds = [
            # ── Geography & Service Context ─────────────────────────
            ParameterDefinition(
                param_id="p_response_time_mean",
                name="Technician Response Time (mean hours)",
                category=ParameterCategory.GEOGRAPHY.value,
                default_value=4.0, unit="hours", min_value=0.5, max_value=48.0, step=0.5,
                is_slider=True, sensitivity_rank=2,
                affects_quadrants=["Q1"],
            ),
            ParameterDefinition(
                param_id="p_travel_distance",
                name="Average Travel Distance",
                category=ParameterCategory.GEOGRAPHY.value,
                default_value=25.0, unit="miles", min_value=0, max_value=200, step=5,
            ),
            ParameterDefinition(
                param_id="p_internal_labor_rate",
                name="Internal Labor Rate",
                category=ParameterCategory.GEOGRAPHY.value,
                default_value=65.0, unit="$/hr", min_value=20, max_value=200, step=5,
                is_slider=True, sensitivity_rank=5,
                affects_quadrants=["Q1", "Q2"],
            ),
            ParameterDefinition(
                param_id="p_vendor_labor_rate",
                name="Vendor Labor Rate",
                category=ParameterCategory.GEOGRAPHY.value,
                default_value=95.0, unit="$/hr", min_value=30, max_value=300, step=5,
                affects_quadrants=["Q1"],
            ),
            ParameterDefinition(
                param_id="p_parts_lead_time",
                name="Parts Lead Time",
                category=ParameterCategory.GEOGRAPHY.value,
                default_value=3.0, unit="days", min_value=0.5, max_value=30, step=0.5,
            ),

            # ── Asset Context ───────────────────────────────────────
            ParameterDefinition(
                param_id="p_avg_asset_age",
                name="Average Asset Age",
                category=ParameterCategory.ASSET.value,
                default_value=8.0, unit="years", min_value=0, max_value=30, step=1,
                is_slider=True, sensitivity_rank=4,
                affects_quadrants=["Q2"],
            ),
            ParameterDefinition(
                param_id="p_failure_rate_multiplier",
                name="Failure Rate Multiplier",
                category=ParameterCategory.ASSET.value,
                default_value=1.0, unit="x", min_value=0.5, max_value=3.0, step=0.1,
                affects_quadrants=["Q1", "Q2"],
            ),
            ParameterDefinition(
                param_id="p_asset_criticality_tier",
                name="Asset Criticality Tier",
                description="1=Critical, 2=Important, 3=Standard",
                category=ParameterCategory.ASSET.value,
                default_value=2.0, unit="tier", min_value=1, max_value=3, step=1,
            ),

            # ── Store / Operation Context ───────────────────────────
            ParameterDefinition(
                param_id="p_operating_hours",
                name="Daily Operating Hours",
                category=ParameterCategory.STORE.value,
                default_value=16.0, unit="hours/day", min_value=8, max_value=24, step=1,
            ),
            ParameterDefinition(
                param_id="p_revenue_proxy",
                name="Daily Revenue Proxy",
                category=ParameterCategory.STORE.value,
                default_value=50000.0, unit="$/day", min_value=5000, max_value=500000, step=5000,
                affects_quadrants=["Q3"],
            ),
            ParameterDefinition(
                param_id="p_downtime_cost_per_hour",
                name="Downtime Cost per Hour",
                category=ParameterCategory.STORE.value,
                default_value=500.0, unit="$/hr", min_value=50, max_value=10000, step=50,
                is_slider=True, sensitivity_rank=1,
                affects_quadrants=["Q1", "Q3", "Q4"],
            ),

            # ── Compliance Context ──────────────────────────────────
            ParameterDefinition(
                param_id="p_regulatory_strictness",
                name="Regulatory Strictness Level",
                description="1=Relaxed, 2=Standard, 3=Strict",
                category=ParameterCategory.COMPLIANCE.value,
                default_value=2.0, unit="level", min_value=1, max_value=3, step=1,
                is_slider=True, sensitivity_rank=3,
                affects_quadrants=["Q3"],
            ),
            ParameterDefinition(
                param_id="p_breach_threshold_hours",
                name="Compliance Breach Threshold (hours)",
                category=ParameterCategory.COMPLIANCE.value,
                default_value=4.0, unit="hours", min_value=0.25, max_value=24, step=0.25,
                affects_quadrants=["Q3"],
            ),
            ParameterDefinition(
                param_id="p_penalty_per_incident",
                name="Penalty per Compliance Incident",
                category=ParameterCategory.COMPLIANCE.value,
                default_value=10000.0, unit="$", min_value=500, max_value=100000, step=500,
                affects_quadrants=["Q3"],
            ),

            # ── Energy & Emissions ──────────────────────────────────
            ParameterDefinition(
                param_id="p_electricity_rate",
                name="Electricity Rate",
                category=ParameterCategory.ENERGY.value,
                default_value=0.12, unit="$/kWh", min_value=0.04, max_value=0.50, step=0.01,
                is_slider=True, sensitivity_rank=6,
                affects_quadrants=["Q4"],
            ),
            ParameterDefinition(
                param_id="p_refrigerant_cost_per_lb",
                name="Refrigerant Cost per Pound",
                category=ParameterCategory.ENERGY.value,
                default_value=15.0, unit="$/lb", min_value=5, max_value=100, step=1,
                affects_quadrants=["Q3", "Q4"],
            ),
            ParameterDefinition(
                param_id="p_carbon_price",
                name="Carbon Price",
                category=ParameterCategory.ENERGY.value,
                default_value=50.0, unit="$/tCO2e", min_value=0, max_value=200, step=5,
                is_slider=True, sensitivity_rank=8,
                affects_quadrants=["Q4"],
            ),

            # ── Financial ───────────────────────────────────────────
            ParameterDefinition(
                param_id="p_discount_rate",
                name="Discount Rate",
                category=ParameterCategory.FINANCIAL.value,
                default_value=0.08, unit="%", min_value=0.02, max_value=0.20, step=0.01,
                is_slider=True, sensitivity_rank=7,
                affects_quadrants=["Q1", "Q2", "Q3", "Q4"],
            ),
            ParameterDefinition(
                param_id="p_inflation_rate",
                name="Inflation Rate",
                category=ParameterCategory.FINANCIAL.value,
                default_value=0.03, unit="%", min_value=0, max_value=0.15, step=0.005,
                affects_quadrants=["Q1", "Q2"],
            ),
            ParameterDefinition(
                param_id="p_capex_budget",
                name="Annual CapEx Budget",
                category=ParameterCategory.FINANCIAL.value,
                default_value=1000000.0, unit="$", min_value=0, max_value=50000000, step=100000,
                is_slider=True, sensitivity_rank=9,
                affects_quadrants=["Q2"],
            ),
            ParameterDefinition(
                param_id="p_opex_budget",
                name="Annual OpEx Budget",
                category=ParameterCategory.FINANCIAL.value,
                default_value=5000000.0, unit="$", min_value=0, max_value=50000000, step=100000,
                affects_quadrants=["Q1"],
            ),

            # ── Data Quality ────────────────────────────────────────
            ParameterDefinition(
                param_id="p_sensor_coverage",
                name="Sensor Coverage",
                category=ParameterCategory.DATA_QUALITY.value,
                default_value=0.60, unit="%", min_value=0, max_value=1.0, step=0.05,
                affects_quadrants=["Q1", "Q3", "Q4"],
            ),
            ParameterDefinition(
                param_id="p_data_missingness",
                name="Data Missingness Rate",
                category=ParameterCategory.DATA_QUALITY.value,
                default_value=0.15, unit="%", min_value=0, max_value=0.80, step=0.05,
            ),
        ]

        for defn in seeds:
            self._definitions[defn.param_id] = defn

        logger.info(f"Seeded {len(seeds)} parameter definitions across {len(ParameterCategory)} categories")
