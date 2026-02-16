"""
Canonical Digital Twin models: AssetTwin, LocationTwin, EstateTwin.

All analytics read/write to twins; all reporting is a view over twins.
Aligned with ISO 23247 digital twin framework concepts.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# =============================================================================
# Enums
# =============================================================================

class AssetType(Enum):
    HVAC_RTU = "hvac_rtu"
    HVAC_AHU = "hvac_ahu"
    REFRIGERATION_RACK = "refrigeration_rack"
    REFRIGERATION_CASE = "refrigeration_case"
    COMPRESSOR = "compressor"
    CONDENSER = "condenser"
    EVAPORATOR = "evaporator"
    BOILER = "boiler"
    CHILLER = "chiller"
    VFD = "vfd"
    LIGHTING = "lighting"
    POWER_METER = "power_meter"
    TEMP_SENSOR = "temp_sensor"
    LEAK_DETECTOR = "leak_detector"
    OTHER = "other"


class RelationshipType(Enum):
    SERVES = "SERVES"
    REJECTS_HEAT_TO = "REJECTS_HEAT_TO"
    AFFECTS_LOAD_OF = "AFFECTS_LOAD_OF"
    SHARES_CIRCUIT_WITH = "SHARES_CIRCUIT_WITH"
    CO_LOCATED_WITH = "CO_LOCATED_WITH"
    PARENT_OF = "PARENT_OF"
    CHILD_OF = "CHILD_OF"
    FED_BY = "FED_BY"
    METERS = "METERS"


class AnomalyFlag(Enum):
    HIGH_ENERGY = "high_energy"
    SENSOR_DRIFT = "sensor_drift"
    SHORT_CYCLING = "short_cycling"
    COIL_ICING = "coil_icing"
    FAN_DEGRADATION = "fan_degradation"
    REFRIGERANT_UNDERCHARGE = "refrigerant_undercharge"
    HIGH_HEAD_PRESSURE = "high_head_pressure"
    TEMP_EXCURSION = "temp_excursion"
    VIBRATION_ANOMALY = "vibration_anomaly"
    PERFORMANCE_DEGRADATION = "performance_degradation"


# =============================================================================
# Embedded Value Objects
# =============================================================================

@dataclass
class HealthState:
    """Asset health state with risk projections."""
    health_score: float = 100.0  # 0–100
    failure_risk_30d: float = 0.0
    failure_risk_90d: float = 0.0
    anomaly_flags: List[AnomalyFlag] = field(default_factory=list)
    last_assessment_ts: Optional[datetime] = None
    assessment_source: str = "initial"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "health_score": self.health_score,
            "failure_risk_30d": self.failure_risk_30d,
            "failure_risk_90d": self.failure_risk_90d,
            "anomaly_flags": [f.value for f in self.anomaly_flags],
            "last_assessment_ts": self.last_assessment_ts.isoformat() if self.last_assessment_ts else None,
            "assessment_source": self.assessment_source,
        }


@dataclass
class AssetEconomics:
    """Economic profile for an asset."""
    opex_baseline_monthly: float = 0.0
    capex_replace_cost: float = 0.0
    remaining_useful_life_months: Optional[float] = None
    expected_life_years: Optional[float] = None
    predicted_future_cost_curve: List[Dict[str, float]] = field(default_factory=list)
    currency: str = "USD"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opex_baseline_monthly": self.opex_baseline_monthly,
            "capex_replace_cost": self.capex_replace_cost,
            "remaining_useful_life_months": self.remaining_useful_life_months,
            "expected_life_years": self.expected_life_years,
            "predicted_future_cost_curve": self.predicted_future_cost_curve,
            "currency": self.currency,
        }


@dataclass
class ComplianceState:
    """Compliance tracking per domain."""
    food_safety: Dict[str, Any] = field(default_factory=dict)
    refrigerant: Dict[str, Any] = field(default_factory=dict)
    esg: Dict[str, Any] = field(default_factory=dict)
    last_audit_ts: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "food_safety": self.food_safety,
            "refrigerant": self.refrigerant,
            "esg": self.esg,
            "last_audit_ts": self.last_audit_ts.isoformat() if self.last_audit_ts else None,
        }


@dataclass
class KPIRollup:
    """Summary of a KPI computation for a location or estate."""
    kpi_name: str
    value: float = 0.0
    unit: str = ""
    savings_low: float = 0.0
    savings_medium: float = 0.0
    savings_high: float = 0.0
    confidence: float = 0.0
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    assumptions: List[str] = field(default_factory=list)
    computed_ts: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kpi_name": self.kpi_name,
            "value": self.value,
            "unit": self.unit,
            "savings_low": self.savings_low,
            "savings_medium": self.savings_medium,
            "savings_high": self.savings_high,
            "confidence": self.confidence,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "assumptions": self.assumptions,
            "computed_ts": self.computed_ts.isoformat() if self.computed_ts else None,
        }


# =============================================================================
# Relationship Edge
# =============================================================================

@dataclass
class TwinRelationship:
    """Typed edge in the twin graph."""
    source_id: str
    target_id: str
    relationship_type: RelationshipType
    properties: Dict[str, Any] = field(default_factory=dict)
    created_ts: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relationship_type": self.relationship_type.value,
            "properties": self.properties,
            "created_ts": self.created_ts.isoformat(),
        }


# =============================================================================
# AssetTwin
# =============================================================================

@dataclass
class AssetTwin:
    """
    Digital twin for a single physical asset.
    
    Represents HVAC RTU, AHU, refrigeration rack, case, compressor,
    condenser, boiler, etc. with full telemetry, health, and economics.
    """
    asset_id: str
    location_id: str
    company_id: str
    asset_type: AssetType = AssetType.OTHER

    # Identity
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial: Optional[str] = None
    install_date: Optional[datetime] = None
    age_years: Optional[float] = None

    # Zone/case relationships
    zone_id: Optional[str] = None
    served_zone_ids: List[str] = field(default_factory=list)
    served_case_ids: List[str] = field(default_factory=list)
    served_product_zones: List[str] = field(default_factory=list)

    # Meter / component hierarchy
    fed_by_meter_id: Optional[str] = None
    contains_component_ids: List[str] = field(default_factory=list)

    # Telemetry mapping
    point_map: Dict[str, str] = field(default_factory=dict)
    units_map: Dict[str, str] = field(default_factory=dict)

    # State
    health: HealthState = field(default_factory=HealthState)
    economics: AssetEconomics = field(default_factory=AssetEconomics)

    # Metadata
    tags: Dict[str, str] = field(default_factory=dict)
    created_ts: datetime = field(default_factory=datetime.utcnow)
    updated_ts: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "location_id": self.location_id,
            "company_id": self.company_id,
            "asset_type": self.asset_type.value,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "serial": self.serial,
            "install_date": self.install_date.isoformat() if self.install_date else None,
            "age_years": self.age_years,
            "zone_id": self.zone_id,
            "served_zone_ids": self.served_zone_ids,
            "served_case_ids": self.served_case_ids,
            "served_product_zones": self.served_product_zones,
            "fed_by_meter_id": self.fed_by_meter_id,
            "contains_component_ids": self.contains_component_ids,
            "point_map": self.point_map,
            "units_map": self.units_map,
            "health": self.health.to_dict(),
            "economics": self.economics.to_dict(),
            "tags": self.tags,
            "created_ts": self.created_ts.isoformat(),
            "updated_ts": self.updated_ts.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AssetTwin:
        health_data = data.get("health", {})
        econ_data = data.get("economics", {})
        return cls(
            asset_id=data["asset_id"],
            location_id=data["location_id"],
            company_id=data["company_id"],
            asset_type=AssetType(data.get("asset_type", "other")),
            manufacturer=data.get("manufacturer"),
            model=data.get("model"),
            serial=data.get("serial"),
            install_date=datetime.fromisoformat(data["install_date"]) if data.get("install_date") else None,
            age_years=data.get("age_years"),
            zone_id=data.get("zone_id"),
            served_zone_ids=data.get("served_zone_ids", []),
            served_case_ids=data.get("served_case_ids", []),
            served_product_zones=data.get("served_product_zones", []),
            fed_by_meter_id=data.get("fed_by_meter_id"),
            contains_component_ids=data.get("contains_component_ids", []),
            point_map=data.get("point_map", {}),
            units_map=data.get("units_map", {}),
            health=HealthState(
                health_score=health_data.get("health_score", 100.0),
                failure_risk_30d=health_data.get("failure_risk_30d", 0.0),
                failure_risk_90d=health_data.get("failure_risk_90d", 0.0),
                anomaly_flags=[AnomalyFlag(f) for f in health_data.get("anomaly_flags", [])],
            ),
            economics=AssetEconomics(
                opex_baseline_monthly=econ_data.get("opex_baseline_monthly", 0.0),
                capex_replace_cost=econ_data.get("capex_replace_cost", 0.0),
                remaining_useful_life_months=econ_data.get("remaining_useful_life_months"),
                expected_life_years=econ_data.get("expected_life_years"),
                predicted_future_cost_curve=econ_data.get("predicted_future_cost_curve", []),
            ),
            tags=data.get("tags", {}),
        )


# =============================================================================
# LocationTwin
# =============================================================================

@dataclass
class LocationTwin:
    """
    Digital twin for a store/site/location.
    
    Aggregates assets and their KPIs. Contains utility tariffs,
    compliance state, and location-level rollups.
    """
    location_id: str
    company_id: str
    estate_id: Optional[str] = None

    # Geography
    geo: Optional[Dict[str, float]] = None  # {"lat": ..., "lon": ...}
    climate_zone: Optional[str] = None
    region: Optional[str] = None
    address: Optional[str] = None

    # Store attributes
    store_format: Optional[str] = None
    sqft: Optional[float] = None
    operating_hours: Optional[Dict[str, str]] = None  # {"mon": "06:00-22:00", ...}

    # Assets
    asset_ids: List[str] = field(default_factory=list)
    has_meter_ids: List[str] = field(default_factory=list)
    adjacent_system_ids: List[str] = field(default_factory=list)

    # Economics
    utility_tariffs: Dict[str, Any] = field(default_factory=dict)  # {"electricity": {...}, "gas": {...}}

    # KPI rollups
    kpi_rollups: Dict[str, KPIRollup] = field(default_factory=dict)

    # Compliance
    compliance: ComplianceState = field(default_factory=ComplianceState)

    # Metadata
    tags: Dict[str, str] = field(default_factory=dict)
    created_ts: datetime = field(default_factory=datetime.utcnow)
    updated_ts: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "location_id": self.location_id,
            "company_id": self.company_id,
            "estate_id": self.estate_id,
            "geo": self.geo,
            "climate_zone": self.climate_zone,
            "region": self.region,
            "address": self.address,
            "store_format": self.store_format,
            "sqft": self.sqft,
            "operating_hours": self.operating_hours,
            "asset_ids": self.asset_ids,
            "has_meter_ids": self.has_meter_ids,
            "adjacent_system_ids": self.adjacent_system_ids,
            "utility_tariffs": self.utility_tariffs,
            "kpi_rollups": {k: v.to_dict() for k, v in self.kpi_rollups.items()},
            "compliance": self.compliance.to_dict(),
            "tags": self.tags,
            "created_ts": self.created_ts.isoformat(),
            "updated_ts": self.updated_ts.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LocationTwin:
        return cls(
            location_id=data["location_id"],
            company_id=data["company_id"],
            estate_id=data.get("estate_id"),
            geo=data.get("geo"),
            climate_zone=data.get("climate_zone"),
            region=data.get("region"),
            address=data.get("address"),
            store_format=data.get("store_format"),
            sqft=data.get("sqft"),
            operating_hours=data.get("operating_hours"),
            asset_ids=data.get("asset_ids", []),
            has_meter_ids=data.get("has_meter_ids", []),
            adjacent_system_ids=data.get("adjacent_system_ids", []),
            utility_tariffs=data.get("utility_tariffs", {}),
            compliance=ComplianceState(**data.get("compliance", {})) if isinstance(data.get("compliance"), dict) else ComplianceState(),
            tags=data.get("tags", {}),
        )


# =============================================================================
# EstateTwin
# =============================================================================

@dataclass
class ScenarioEntry:
    """A scenario in the estate's scenario ledger."""
    scenario_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    roi_summary: Dict[str, Any] = field(default_factory=dict)
    status: str = "draft"  # draft | running | completed | archived
    created_ts: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "roi_summary": self.roi_summary,
            "status": self.status,
            "created_ts": self.created_ts.isoformat(),
        }


@dataclass
class EstateTwin:
    """
    Digital twin for a company/portfolio.
    
    Aggregates locations, holds estate-level KPI rollups,
    benchmarking distributions, and scenario ledger.
    """
    company_id: str
    # Backward-compatible alias retained for older callers/tests.
    name: Optional[str] = None
    company_name: Optional[str] = None

    # Locations
    location_ids: List[str] = field(default_factory=list)

    # KPI rollups (estate-wide)
    kpi_rollups: Dict[str, KPIRollup] = field(default_factory=dict)

    # Benchmarking
    benchmarks: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # Scenario ledger
    scenarios: List[ScenarioEntry] = field(default_factory=list)

    # ROI summaries
    roi_summaries: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    tags: Dict[str, str] = field(default_factory=dict)
    created_ts: datetime = field(default_factory=datetime.utcnow)
    updated_ts: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        # Keep company_name and name synchronized for compatibility.
        if self.company_name is None and self.name is not None:
            self.company_name = self.name
        elif self.name is None and self.company_name is not None:
            self.name = self.company_name

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company_id": self.company_id,
            "name": self.name,
            "company_name": self.company_name,
            "location_ids": self.location_ids,
            "kpi_rollups": {k: v.to_dict() for k, v in self.kpi_rollups.items()},
            "benchmarks": self.benchmarks,
            "scenarios": [s.to_dict() for s in self.scenarios],
            "roi_summaries": self.roi_summaries,
            "tags": self.tags,
            "created_ts": self.created_ts.isoformat(),
            "updated_ts": self.updated_ts.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EstateTwin:
        return cls(
            company_id=data["company_id"],
            company_name=data.get("company_name"),
            location_ids=data.get("location_ids", []),
            benchmarks=data.get("benchmarks", {}),
            scenarios=[ScenarioEntry(**s) for s in data.get("scenarios", [])],
            roi_summaries=data.get("roi_summaries", {}),
            tags=data.get("tags", {}),
        )
