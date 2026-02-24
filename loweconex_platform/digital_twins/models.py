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


class ControllerType(Enum):
    BMS = "bms"
    PLC = "plc"
    IOT_GATEWAY = "iot_gateway"
    RTU_CONTROLLER = "rtu_controller"
    RACK_CONTROLLER = "rack_controller"
    SUPERVISORY = "supervisory"
    OTHER = "other"


class ComponentType(Enum):
    COMPRESSOR = "compressor"
    CONDENSER = "condenser"
    CONDENSER_FAN = "condenser_fan"
    EVAPORATOR = "evaporator"
    EVAPORATOR_FAN = "evaporator_fan"
    EXPANSION_VALVE = "expansion_valve"
    FILTER_DRIER = "filter_drier"
    MOTOR = "motor"
    DRIVE = "drive"
    HEAT_EXCHANGER = "heat_exchanger"
    PUMP = "pump"
    VALVE = "valve"
    SENSOR_ARRAY = "sensor_array"
    BELT = "belt"
    CAPACITOR = "capacitor"
    CONTACTOR = "contactor"
    OTHER = "other"


class DataSourceType(Enum):
    BMS = "bms"
    ENERGY_MONITOR = "energy_monitor"
    IOT_PLATFORM = "iot_platform"
    CMMS = "cmms"
    ERP = "erp"
    MANUAL_UPLOAD = "manual_upload"
    API = "api"
    SCADA = "scada"
    OTHER = "other"


class WOType(Enum):
    REACTIVE = "reactive"
    PLANNED_PM = "planned_pm"
    CONDITION_BASED = "condition_based"
    EMERGENCY = "emergency"
    INSPECTION = "inspection"
    WARRANTY = "warranty"


class WOPriority(Enum):
    P1_CRITICAL = "p1_critical"
    P2_HIGH = "p2_high"
    P3_NORMAL = "p3_normal"
    P4_LOW = "p4_low"


class WOStatus(Enum):
    DRAFT = "draft"
    OPEN = "open"
    DISPATCHED = "dispatched"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    VERIFIED = "verified"
    CANCELLED = "cancelled"


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
    # Controller hierarchy
    CONTROLLED_BY = "CONTROLLED_BY"
    MONITORS = "MONITORS"
    # Work order linkage
    HAS_OPEN_WO = "HAS_OPEN_WO"
    ASSIGNED_TO = "ASSIGNED_TO"
    # Component hierarchy
    CONTAINS_COMPONENT = "CONTAINS_COMPONENT"
    # Spatial
    LOCATED_IN_ZONE = "LOCATED_IN_ZONE"
    # Data flow
    DATA_SOURCE_FOR = "DATA_SOURCE_FOR"


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
# Intelligence Layer Value Objects
# =============================================================================

@dataclass
class AssetIntelligence:
    """AI/ML intelligence layer outputs for an asset."""
    active_model_ids: List[str] = field(default_factory=list)
    last_inference_ts: Optional[datetime] = None

    # Predictive signals
    predicted_failure_mode: Optional[str] = None
    predicted_failure_confidence: float = 0.0
    ensemble_predictions: List[Dict[str, Any]] = field(default_factory=list)

    # Prescriptive
    recommended_actions: List[Dict[str, Any]] = field(default_factory=list)

    # Anomaly summary
    active_anomaly_count: int = 0
    anomaly_trend: str = "stable"  # improving, stable, degrading

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active_model_ids": self.active_model_ids,
            "last_inference_ts": self.last_inference_ts.isoformat() if self.last_inference_ts else None,
            "predicted_failure_mode": self.predicted_failure_mode,
            "predicted_failure_confidence": self.predicted_failure_confidence,
            "ensemble_predictions": self.ensemble_predictions,
            "recommended_actions": self.recommended_actions,
            "active_anomaly_count": self.active_anomaly_count,
            "anomaly_trend": self.anomaly_trend,
        }


# =============================================================================
# Rules Engine Value Objects
# =============================================================================

@dataclass
class AlarmThreshold:
    """Alarm limits for a sensor point."""
    point_id: str = ""
    low_limit: Optional[float] = None
    high_limit: Optional[float] = None
    low_low_limit: Optional[float] = None
    high_high_limit: Optional[float] = None
    deadband: float = 0.0
    delay_seconds: int = 0
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "point_id": self.point_id,
            "low_limit": self.low_limit,
            "high_limit": self.high_limit,
            "low_low_limit": self.low_low_limit,
            "high_high_limit": self.high_high_limit,
            "deadband": self.deadband,
            "delay_seconds": self.delay_seconds,
            "is_active": self.is_active,
        }


@dataclass
class ControlRule:
    """A rule in the rules engine (Lowe's Connect rules layer)."""
    rule_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    rule_name: str = ""
    rule_type: str = "alarm"  # alarm, setpoint_limit, scheduling, interlock, custom
    target_entity_type: str = "asset"  # asset, controller, location
    target_entity_id: str = ""

    # Condition
    condition_expression: str = ""
    condition_points: List[str] = field(default_factory=list)

    # Action
    action_type: str = "alarm"  # alarm, notification, setpoint_override, wo_create, log
    action_config: Dict[str, Any] = field(default_factory=dict)

    # State
    is_active: bool = True
    last_evaluated_ts: Optional[datetime] = None
    last_triggered_ts: Optional[datetime] = None
    trigger_count_30d: int = 0

    # Source
    source_system: str = "platform"  # lowes_connect, bms_native, platform_ai

    created_ts: datetime = field(default_factory=datetime.utcnow)
    updated_ts: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "rule_type": self.rule_type,
            "target_entity_type": self.target_entity_type,
            "target_entity_id": self.target_entity_id,
            "condition_expression": self.condition_expression,
            "condition_points": self.condition_points,
            "action_type": self.action_type,
            "action_config": self.action_config,
            "is_active": self.is_active,
            "last_evaluated_ts": self.last_evaluated_ts.isoformat() if self.last_evaluated_ts else None,
            "last_triggered_ts": self.last_triggered_ts.isoformat() if self.last_triggered_ts else None,
            "trigger_count_30d": self.trigger_count_30d,
            "source_system": self.source_system,
            "created_ts": self.created_ts.isoformat(),
            "updated_ts": self.updated_ts.isoformat(),
        }


@dataclass
class ScheduleOverride:
    """Schedule override for occupied/unoccupied, holiday, demand response."""
    schedule_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    target_entity_id: str = ""
    override_type: str = "occupied_unoccupied"  # occupied_unoccupied, holiday, demand_response, night_setback
    schedule: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    effective_from: Optional[datetime] = None
    effective_until: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schedule_id": self.schedule_id,
            "target_entity_id": self.target_entity_id,
            "override_type": self.override_type,
            "schedule": self.schedule,
            "is_active": self.is_active,
            "effective_from": self.effective_from.isoformat() if self.effective_from else None,
            "effective_until": self.effective_until.isoformat() if self.effective_until else None,
        }


# =============================================================================
# Parts & Service Value Objects
# =============================================================================

@dataclass
class PartRequirement:
    """A part needed for a work order."""
    part_id: str = ""
    part_number: str = ""
    description: str = ""
    quantity: int = 1
    status: str = "needed"  # needed, ordered, received, installed
    order_reference: Optional[str] = None
    unit_cost: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "part_id": self.part_id,
            "part_number": self.part_number,
            "description": self.description,
            "quantity": self.quantity,
            "status": self.status,
            "order_reference": self.order_reference,
            "unit_cost": self.unit_cost,
        }


@dataclass
class PartsCatalogEntry:
    """Master catalog entry for a spare part."""
    part_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    part_number: str = ""
    description: str = ""
    category: str = ""  # compressor, filter, belt, capacitor, contactor, valve, sensor, refrigerant
    compatible_asset_types: List[str] = field(default_factory=list)
    compatible_models: List[str] = field(default_factory=list)
    unit_cost: float = 0.0
    lead_time_days: int = 0
    preferred_supplier: Optional[str] = None
    min_stock_qty: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "part_id": self.part_id,
            "part_number": self.part_number,
            "description": self.description,
            "category": self.category,
            "compatible_asset_types": self.compatible_asset_types,
            "compatible_models": self.compatible_models,
            "unit_cost": self.unit_cost,
            "lead_time_days": self.lead_time_days,
            "preferred_supplier": self.preferred_supplier,
            "min_stock_qty": self.min_stock_qty,
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
# ControllerTwin
# =============================================================================

@dataclass
class ControllerTwin:
    """
    Digital twin for a BMS controller, IoT gateway, PLC, or supervisory device.

    Sits between LocationTwin and AssetTwin in the hierarchy.
    Represents any device that aggregates sensor data and executes control logic.
    """
    controller_id: str
    location_id: str
    company_id: str
    controller_type: ControllerType = ControllerType.OTHER

    # Identity
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    firmware_version: Optional[str] = None
    ip_address: Optional[str] = None
    protocol: Optional[str] = None  # bacnet, modbus, mqtt, lora, proprietary

    # Hierarchy
    managed_asset_ids: List[str] = field(default_factory=list)
    parent_controller_id: Optional[str] = None

    # Connectivity
    connection_status: str = "unknown"  # online, offline, degraded, unknown
    last_heartbeat_ts: Optional[datetime] = None
    uptime_pct_30d: float = 0.0

    # Control capabilities
    supports_read: bool = True
    supports_write: bool = False
    supports_scheduling: bool = False

    # Rules engine state (Lowe's Connect rules)
    active_rules: List[ControlRule] = field(default_factory=list)
    alarm_thresholds: Dict[str, AlarmThreshold] = field(default_factory=dict)
    override_schedules: List[ScheduleOverride] = field(default_factory=list)

    # Metadata
    tags: Dict[str, str] = field(default_factory=dict)
    created_ts: datetime = field(default_factory=datetime.utcnow)
    updated_ts: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "controller_id": self.controller_id,
            "location_id": self.location_id,
            "company_id": self.company_id,
            "controller_type": self.controller_type.value,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "firmware_version": self.firmware_version,
            "ip_address": self.ip_address,
            "protocol": self.protocol,
            "managed_asset_ids": self.managed_asset_ids,
            "parent_controller_id": self.parent_controller_id,
            "connection_status": self.connection_status,
            "last_heartbeat_ts": self.last_heartbeat_ts.isoformat() if self.last_heartbeat_ts else None,
            "uptime_pct_30d": self.uptime_pct_30d,
            "supports_read": self.supports_read,
            "supports_write": self.supports_write,
            "supports_scheduling": self.supports_scheduling,
            "active_rules": [r.to_dict() for r in self.active_rules],
            "alarm_thresholds": {k: v.to_dict() for k, v in self.alarm_thresholds.items()},
            "override_schedules": [s.to_dict() for s in self.override_schedules],
            "tags": self.tags,
            "created_ts": self.created_ts.isoformat(),
            "updated_ts": self.updated_ts.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ControllerTwin:
        rules = [ControlRule(**r) if isinstance(r, dict) else r for r in data.get("active_rules", [])]
        thresholds = {
            k: AlarmThreshold(**v) if isinstance(v, dict) else v
            for k, v in data.get("alarm_thresholds", {}).items()
        }
        schedules = [ScheduleOverride(**s) if isinstance(s, dict) else s for s in data.get("override_schedules", [])]
        return cls(
            controller_id=data["controller_id"],
            location_id=data["location_id"],
            company_id=data["company_id"],
            controller_type=ControllerType(data.get("controller_type", "other")),
            manufacturer=data.get("manufacturer"),
            model=data.get("model"),
            firmware_version=data.get("firmware_version"),
            ip_address=data.get("ip_address"),
            protocol=data.get("protocol"),
            managed_asset_ids=data.get("managed_asset_ids", []),
            parent_controller_id=data.get("parent_controller_id"),
            connection_status=data.get("connection_status", "unknown"),
            supports_read=data.get("supports_read", True),
            supports_write=data.get("supports_write", False),
            supports_scheduling=data.get("supports_scheduling", False),
            active_rules=rules,
            alarm_thresholds=thresholds,
            override_schedules=schedules,
            tags=data.get("tags", {}),
        )


# =============================================================================
# SensorPointTwin
# =============================================================================

@dataclass
class SensorPointTwin:
    """
    First-class entity for an individual sensor / BACnet point.

    Replaces flat point_map references with a rich model including
    Brick/Haystack semantic tags, trust scoring, and calibration state.
    """
    point_id: str
    asset_id: str
    controller_id: Optional[str] = None

    # Semantics (Brick/Haystack aligned)
    point_type: str = ""  # supply_air_temp, discharge_pressure, compressor_current, etc.
    brick_class: Optional[str] = None  # e.g., "brick:Supply_Air_Temperature_Sensor"
    haystack_tags: List[str] = field(default_factory=list)

    # Engineering units
    unit: str = ""  # °F, psig, A, kW, %, etc.

    # Trust & quality
    trust_score: float = 1.0  # 0-1, from sensor integrity assessment
    last_value: Optional[float] = None
    last_value_ts: Optional[datetime] = None
    is_stale: bool = False
    expected_interval_seconds: int = 300

    # Calibration
    calibration_offset: float = 0.0
    calibration_date: Optional[datetime] = None
    drift_detected: bool = False

    # BACnet / protocol address
    protocol_address: Optional[str] = None  # e.g., "AI:3" for BACnet analog input 3

    tags: Dict[str, str] = field(default_factory=dict)
    created_ts: datetime = field(default_factory=datetime.utcnow)
    updated_ts: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "point_id": self.point_id,
            "asset_id": self.asset_id,
            "controller_id": self.controller_id,
            "point_type": self.point_type,
            "brick_class": self.brick_class,
            "haystack_tags": self.haystack_tags,
            "unit": self.unit,
            "trust_score": self.trust_score,
            "last_value": self.last_value,
            "last_value_ts": self.last_value_ts.isoformat() if self.last_value_ts else None,
            "is_stale": self.is_stale,
            "expected_interval_seconds": self.expected_interval_seconds,
            "calibration_offset": self.calibration_offset,
            "calibration_date": self.calibration_date.isoformat() if self.calibration_date else None,
            "drift_detected": self.drift_detected,
            "protocol_address": self.protocol_address,
            "tags": self.tags,
            "created_ts": self.created_ts.isoformat(),
            "updated_ts": self.updated_ts.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SensorPointTwin:
        return cls(
            point_id=data["point_id"],
            asset_id=data["asset_id"],
            controller_id=data.get("controller_id"),
            point_type=data.get("point_type", ""),
            brick_class=data.get("brick_class"),
            haystack_tags=data.get("haystack_tags", []),
            unit=data.get("unit", ""),
            trust_score=data.get("trust_score", 1.0),
            last_value=data.get("last_value"),
            is_stale=data.get("is_stale", False),
            expected_interval_seconds=data.get("expected_interval_seconds", 300),
            calibration_offset=data.get("calibration_offset", 0.0),
            drift_detected=data.get("drift_detected", False),
            protocol_address=data.get("protocol_address"),
            tags=data.get("tags", {}),
        )


# =============================================================================
# ComponentTwin
# =============================================================================

@dataclass
class ComponentTwin:
    """
    Digital twin for a sub-assembly within an asset.

    Gives first-class identity to compressors, condensers, evaporators, fans,
    valves, etc. Each component has independent health and linked sensor points.
    """
    component_id: str
    parent_asset_id: str
    component_type: ComponentType = ComponentType.OTHER

    # Nameplate
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial: Optional[str] = None

    # Health (independent of parent asset health)
    health_score: float = 100.0  # 0-100
    anomaly_flags: List[str] = field(default_factory=list)

    # Linked sensor points
    sensor_point_ids: List[str] = field(default_factory=list)

    # Maintenance
    last_service_date: Optional[datetime] = None
    service_interval_hours: Optional[int] = None
    total_runtime_hours: Optional[float] = None

    tags: Dict[str, str] = field(default_factory=dict)
    created_ts: datetime = field(default_factory=datetime.utcnow)
    updated_ts: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "component_id": self.component_id,
            "parent_asset_id": self.parent_asset_id,
            "component_type": self.component_type.value,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "serial": self.serial,
            "health_score": self.health_score,
            "anomaly_flags": self.anomaly_flags,
            "sensor_point_ids": self.sensor_point_ids,
            "last_service_date": self.last_service_date.isoformat() if self.last_service_date else None,
            "service_interval_hours": self.service_interval_hours,
            "total_runtime_hours": self.total_runtime_hours,
            "tags": self.tags,
            "created_ts": self.created_ts.isoformat(),
            "updated_ts": self.updated_ts.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ComponentTwin:
        return cls(
            component_id=data["component_id"],
            parent_asset_id=data["parent_asset_id"],
            component_type=ComponentType(data.get("component_type", "other")),
            manufacturer=data.get("manufacturer"),
            model=data.get("model"),
            serial=data.get("serial"),
            health_score=data.get("health_score", 100.0),
            anomaly_flags=data.get("anomaly_flags", []),
            sensor_point_ids=data.get("sensor_point_ids", []),
            total_runtime_hours=data.get("total_runtime_hours"),
            tags=data.get("tags", {}),
        )


# =============================================================================
# DataSourceRegistration
# =============================================================================

@dataclass
class DataSourceRegistration:
    """
    Registry entry for a heterogeneous data source feeding the platform.

    Tracks BMS, energy monitors, IoT platforms, CMMS, ERP, and manual uploads
    with connection health, schema mapping references, and data quality metrics.
    """
    source_id: str
    company_id: str
    location_id: Optional[str] = None
    source_type: DataSourceType = DataSourceType.OTHER
    source_name: str = ""
    vendor: Optional[str] = None

    # Connection
    connection_method: str = "api"  # bacnet_ip, modbus_tcp, mqtt, rest_api, sftp, s3, manual
    connection_config: Dict[str, Any] = field(default_factory=dict)

    # Schema mapping reference
    schema_mapping_id: Optional[str] = None

    # Health
    status: str = "pending_setup"  # connected, disconnected, error, pending_setup
    last_successful_sync: Optional[datetime] = None
    sync_frequency_seconds: Optional[int] = None
    error_count_24h: int = 0

    # Data quality
    completeness_pct_30d: float = 0.0
    data_quality_score: float = 0.0  # ISO 25012 composite

    tags: Dict[str, str] = field(default_factory=dict)
    created_ts: datetime = field(default_factory=datetime.utcnow)
    updated_ts: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "company_id": self.company_id,
            "location_id": self.location_id,
            "source_type": self.source_type.value,
            "source_name": self.source_name,
            "vendor": self.vendor,
            "connection_method": self.connection_method,
            "connection_config": self.connection_config,
            "schema_mapping_id": self.schema_mapping_id,
            "status": self.status,
            "last_successful_sync": self.last_successful_sync.isoformat() if self.last_successful_sync else None,
            "sync_frequency_seconds": self.sync_frequency_seconds,
            "error_count_24h": self.error_count_24h,
            "completeness_pct_30d": self.completeness_pct_30d,
            "data_quality_score": self.data_quality_score,
            "tags": self.tags,
            "created_ts": self.created_ts.isoformat(),
            "updated_ts": self.updated_ts.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DataSourceRegistration:
        return cls(
            source_id=data["source_id"],
            company_id=data["company_id"],
            location_id=data.get("location_id"),
            source_type=DataSourceType(data.get("source_type", "other")),
            source_name=data.get("source_name", ""),
            vendor=data.get("vendor"),
            connection_method=data.get("connection_method", "api"),
            schema_mapping_id=data.get("schema_mapping_id"),
            status=data.get("status", "pending_setup"),
            error_count_24h=data.get("error_count_24h", 0),
            completeness_pct_30d=data.get("completeness_pct_30d", 0.0),
            data_quality_score=data.get("data_quality_score", 0.0),
            tags=data.get("tags", {}),
        )


# =============================================================================
# WorkOrderTwin
# =============================================================================

@dataclass
class WorkOrderTwin:
    """
    Work order as a graph-connected twin with full lifecycle tracking.

    Elevates work orders from flat persistence into the twin graph with
    parts requirements, SLA tracking, and CMMS sync state.
    """
    wo_id: str
    asset_id: str
    location_id: str
    company_id: str

    # Classification
    wo_type: WOType = WOType.REACTIVE
    priority: WOPriority = WOPriority.P3_NORMAL
    trade: str = "hvac"  # hvac, refrigeration, electrical, plumbing, controls, general

    # Source / trigger
    trigger_source: str = "manual"  # ai_agent, rules_engine, manual, cmms_scheduled, call_center
    source_alert_id: Optional[str] = None
    source_agent_action_id: Optional[str] = None

    # Description
    problem_description: str = ""
    ai_diagnosis: Optional[str] = None
    fault_code: Optional[str] = None

    # Service provider
    assigned_provider_id: Optional[str] = None
    assigned_technician_id: Optional[str] = None

    # Parts
    required_parts: List[PartRequirement] = field(default_factory=list)

    # SLA
    sla_response_hours: Optional[float] = None
    sla_resolution_hours: Optional[float] = None
    sla_met: Optional[bool] = None

    # Lifecycle
    status: WOStatus = WOStatus.DRAFT
    created_at: datetime = field(default_factory=datetime.utcnow)
    dispatched_at: Optional[datetime] = None
    arrived_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None

    # Cost
    estimated_cost: float = 0.0
    actual_cost: Optional[float] = None
    labor_hours: Optional[float] = None

    # Resolution
    resolution_description: Optional[str] = None
    root_cause_confirmed: Optional[str] = None
    follow_up_needed: bool = False

    # External system sync
    external_cmms_id: Optional[str] = None
    external_cmms_system: Optional[str] = None
    last_synced_at: Optional[datetime] = None

    tags: Dict[str, str] = field(default_factory=dict)
    created_ts: datetime = field(default_factory=datetime.utcnow)
    updated_ts: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "wo_id": self.wo_id,
            "asset_id": self.asset_id,
            "location_id": self.location_id,
            "company_id": self.company_id,
            "wo_type": self.wo_type.value,
            "priority": self.priority.value,
            "trade": self.trade,
            "trigger_source": self.trigger_source,
            "source_alert_id": self.source_alert_id,
            "source_agent_action_id": self.source_agent_action_id,
            "problem_description": self.problem_description,
            "ai_diagnosis": self.ai_diagnosis,
            "fault_code": self.fault_code,
            "assigned_provider_id": self.assigned_provider_id,
            "assigned_technician_id": self.assigned_technician_id,
            "required_parts": [p.to_dict() for p in self.required_parts],
            "sla_response_hours": self.sla_response_hours,
            "sla_resolution_hours": self.sla_resolution_hours,
            "sla_met": self.sla_met,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "dispatched_at": self.dispatched_at.isoformat() if self.dispatched_at else None,
            "arrived_at": self.arrived_at.isoformat() if self.arrived_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "estimated_cost": self.estimated_cost,
            "actual_cost": self.actual_cost,
            "labor_hours": self.labor_hours,
            "resolution_description": self.resolution_description,
            "root_cause_confirmed": self.root_cause_confirmed,
            "follow_up_needed": self.follow_up_needed,
            "external_cmms_id": self.external_cmms_id,
            "external_cmms_system": self.external_cmms_system,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
            "tags": self.tags,
            "created_ts": self.created_ts.isoformat(),
            "updated_ts": self.updated_ts.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkOrderTwin:
        parts = [
            PartRequirement(**p) if isinstance(p, dict) else p
            for p in data.get("required_parts", [])
        ]
        return cls(
            wo_id=data["wo_id"],
            asset_id=data["asset_id"],
            location_id=data["location_id"],
            company_id=data["company_id"],
            wo_type=WOType(data.get("wo_type", "reactive")),
            priority=WOPriority(data.get("priority", "p3_normal")),
            trade=data.get("trade", "hvac"),
            trigger_source=data.get("trigger_source", "manual"),
            source_alert_id=data.get("source_alert_id"),
            source_agent_action_id=data.get("source_agent_action_id"),
            problem_description=data.get("problem_description", ""),
            ai_diagnosis=data.get("ai_diagnosis"),
            fault_code=data.get("fault_code"),
            assigned_provider_id=data.get("assigned_provider_id"),
            assigned_technician_id=data.get("assigned_technician_id"),
            required_parts=parts,
            sla_response_hours=data.get("sla_response_hours"),
            sla_resolution_hours=data.get("sla_resolution_hours"),
            sla_met=data.get("sla_met"),
            status=WOStatus(data.get("status", "draft")),
            estimated_cost=data.get("estimated_cost", 0.0),
            actual_cost=data.get("actual_cost"),
            labor_hours=data.get("labor_hours"),
            resolution_description=data.get("resolution_description"),
            root_cause_confirmed=data.get("root_cause_confirmed"),
            follow_up_needed=data.get("follow_up_needed", False),
            external_cmms_id=data.get("external_cmms_id"),
            external_cmms_system=data.get("external_cmms_system"),
            tags=data.get("tags", {}),
        )


# =============================================================================
# ServiceProviderTwin / TechnicianProfile
# =============================================================================

@dataclass
class ServiceProviderTwin:
    """
    Digital twin for a maintenance service provider (in-house team or vendor).

    Tracks capabilities, performance metrics, contract terms, and availability.
    """
    provider_id: str
    company_id: str
    name: str = ""
    provider_type: str = "in_house"  # in_house, third_party, oem

    # Capabilities
    trades: List[str] = field(default_factory=list)  # hvac, refrigeration, electrical, controls
    certifications: List[str] = field(default_factory=list)  # EPA_608, NATE, journeyman_hvac
    service_regions: List[str] = field(default_factory=list)  # geographic / location group IDs

    # Performance
    avg_response_time_hours: float = 0.0
    avg_resolution_time_hours: float = 0.0
    first_time_fix_rate: float = 0.0  # 0-1
    customer_satisfaction_score: float = 0.0
    wo_completed_30d: int = 0
    callback_rate: float = 0.0  # 0-1

    # Contract
    contract_type: str = "t_and_m"  # t_and_m, fixed_price, managed_service
    hourly_rate: Optional[float] = None

    # Availability
    availability_schedule: Optional[Dict[str, str]] = None  # {"mon": "07:00-18:00", ...}
    is_active: bool = True

    tags: Dict[str, str] = field(default_factory=dict)
    created_ts: datetime = field(default_factory=datetime.utcnow)
    updated_ts: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "company_id": self.company_id,
            "name": self.name,
            "provider_type": self.provider_type,
            "trades": self.trades,
            "certifications": self.certifications,
            "service_regions": self.service_regions,
            "avg_response_time_hours": self.avg_response_time_hours,
            "avg_resolution_time_hours": self.avg_resolution_time_hours,
            "first_time_fix_rate": self.first_time_fix_rate,
            "customer_satisfaction_score": self.customer_satisfaction_score,
            "wo_completed_30d": self.wo_completed_30d,
            "callback_rate": self.callback_rate,
            "contract_type": self.contract_type,
            "hourly_rate": self.hourly_rate,
            "availability_schedule": self.availability_schedule,
            "is_active": self.is_active,
            "tags": self.tags,
            "created_ts": self.created_ts.isoformat(),
            "updated_ts": self.updated_ts.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ServiceProviderTwin:
        return cls(
            provider_id=data["provider_id"],
            company_id=data["company_id"],
            name=data.get("name", ""),
            provider_type=data.get("provider_type", "in_house"),
            trades=data.get("trades", []),
            certifications=data.get("certifications", []),
            service_regions=data.get("service_regions", []),
            avg_response_time_hours=data.get("avg_response_time_hours", 0.0),
            avg_resolution_time_hours=data.get("avg_resolution_time_hours", 0.0),
            first_time_fix_rate=data.get("first_time_fix_rate", 0.0),
            customer_satisfaction_score=data.get("customer_satisfaction_score", 0.0),
            wo_completed_30d=data.get("wo_completed_30d", 0),
            callback_rate=data.get("callback_rate", 0.0),
            contract_type=data.get("contract_type", "t_and_m"),
            hourly_rate=data.get("hourly_rate"),
            availability_schedule=data.get("availability_schedule"),
            is_active=data.get("is_active", True),
            tags=data.get("tags", {}),
        )


@dataclass
class TechnicianProfile:
    """Profile for an individual technician within a service provider."""
    technician_id: str
    provider_id: str
    name: str = ""
    trades: List[str] = field(default_factory=list)
    certifications: List[str] = field(default_factory=list)
    assigned_locations: List[str] = field(default_factory=list)
    is_available: bool = True
    current_location: Optional[Dict[str, float]] = None  # {"lat": ..., "lon": ...}

    tags: Dict[str, str] = field(default_factory=dict)
    created_ts: datetime = field(default_factory=datetime.utcnow)
    updated_ts: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "technician_id": self.technician_id,
            "provider_id": self.provider_id,
            "name": self.name,
            "trades": self.trades,
            "certifications": self.certifications,
            "assigned_locations": self.assigned_locations,
            "is_available": self.is_available,
            "current_location": self.current_location,
            "tags": self.tags,
            "created_ts": self.created_ts.isoformat(),
            "updated_ts": self.updated_ts.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TechnicianProfile:
        return cls(
            technician_id=data["technician_id"],
            provider_id=data["provider_id"],
            name=data.get("name", ""),
            trades=data.get("trades", []),
            certifications=data.get("certifications", []),
            assigned_locations=data.get("assigned_locations", []),
            is_available=data.get("is_available", True),
            current_location=data.get("current_location"),
            tags=data.get("tags", {}),
        )


# =============================================================================
# AgentAction — Agentic Workflow Ledger
# =============================================================================

@dataclass
class AgentAction:
    """
    Tracks an action initiated by an AI agent in the agentic workflow layer.

    Links agent decisions to resulting work orders, parts orders, setpoint
    changes, and other automated actions with full audit trail.
    """
    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str = ""
    location_id: Optional[str] = None
    asset_id: Optional[str] = None

    # Agent identity
    agent_type: str = ""  # anomaly_detector, work_order_creator, dispatch_optimizer,
                          # parts_orderer, setpoint_tuner, compliance_checker
    agent_run_id: str = ""

    # Action
    action_type: str = ""  # create_wo, dispatch_tech, order_parts, adjust_setpoint,
                           # generate_alert, escalate, suppress_alarm, schedule_pm
    action_payload: Dict[str, Any] = field(default_factory=dict)

    # Decision context
    triggering_signal: str = ""
    confidence: float = 0.0
    supporting_evidence: List[str] = field(default_factory=list)

    # Approval
    requires_approval: bool = True
    approval_status: str = "pending"  # auto_approved, pending, approved, rejected
    approved_by: Optional[str] = None

    # Outcome
    outcome_status: str = "pending"  # pending, executed, failed, rolled_back
    outcome_details: Dict[str, Any] = field(default_factory=dict)
    resulting_wo_id: Optional[str] = None

    created_ts: datetime = field(default_factory=datetime.utcnow)
    executed_ts: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "company_id": self.company_id,
            "location_id": self.location_id,
            "asset_id": self.asset_id,
            "agent_type": self.agent_type,
            "agent_run_id": self.agent_run_id,
            "action_type": self.action_type,
            "action_payload": self.action_payload,
            "triggering_signal": self.triggering_signal,
            "confidence": self.confidence,
            "supporting_evidence": self.supporting_evidence,
            "requires_approval": self.requires_approval,
            "approval_status": self.approval_status,
            "approved_by": self.approved_by,
            "outcome_status": self.outcome_status,
            "outcome_details": self.outcome_details,
            "resulting_wo_id": self.resulting_wo_id,
            "created_ts": self.created_ts.isoformat(),
            "executed_ts": self.executed_ts.isoformat() if self.executed_ts else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AgentAction:
        return cls(
            action_id=data.get("action_id", str(uuid.uuid4())),
            company_id=data.get("company_id", ""),
            location_id=data.get("location_id"),
            asset_id=data.get("asset_id"),
            agent_type=data.get("agent_type", ""),
            agent_run_id=data.get("agent_run_id", ""),
            action_type=data.get("action_type", ""),
            action_payload=data.get("action_payload", {}),
            triggering_signal=data.get("triggering_signal", ""),
            confidence=data.get("confidence", 0.0),
            supporting_evidence=data.get("supporting_evidence", []),
            requires_approval=data.get("requires_approval", True),
            approval_status=data.get("approval_status", "pending"),
            approved_by=data.get("approved_by"),
            outcome_status=data.get("outcome_status", "pending"),
            outcome_details=data.get("outcome_details", {}),
            resulting_wo_id=data.get("resulting_wo_id"),
        )


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

    # Nameplate / commissioning
    rated_capacity_kw: Optional[float] = None
    rated_efficiency_eer: Optional[float] = None
    refrigerant_charge_lbs: Optional[float] = None
    electrical_specs: Optional[Dict[str, Any]] = None  # {"voltage": 480, "phase": 3, "fla": 45.2}
    warranty_expiry: Optional[datetime] = None
    commissioning_date: Optional[datetime] = None
    expected_useful_life_years: Optional[float] = None

    # Controller linkage
    controller_id: Optional[str] = None

    # Zone/case relationships
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    floor: Optional[str] = None
    coordinates: Optional[Dict[str, float]] = None  # {"x": ..., "y": ...} within floor plan
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
    intelligence: AssetIntelligence = field(default_factory=AssetIntelligence)

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
            "rated_capacity_kw": self.rated_capacity_kw,
            "rated_efficiency_eer": self.rated_efficiency_eer,
            "refrigerant_charge_lbs": self.refrigerant_charge_lbs,
            "electrical_specs": self.electrical_specs,
            "warranty_expiry": self.warranty_expiry.isoformat() if self.warranty_expiry else None,
            "commissioning_date": self.commissioning_date.isoformat() if self.commissioning_date else None,
            "expected_useful_life_years": self.expected_useful_life_years,
            "controller_id": self.controller_id,
            "zone_name": self.zone_name,
            "floor": self.floor,
            "coordinates": self.coordinates,
            "health": self.health.to_dict(),
            "economics": self.economics.to_dict(),
            "intelligence": self.intelligence.to_dict(),
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
            rated_capacity_kw=data.get("rated_capacity_kw"),
            rated_efficiency_eer=data.get("rated_efficiency_eer"),
            refrigerant_charge_lbs=data.get("refrigerant_charge_lbs"),
            electrical_specs=data.get("electrical_specs"),
            warranty_expiry=datetime.fromisoformat(data["warranty_expiry"]) if data.get("warranty_expiry") else None,
            commissioning_date=datetime.fromisoformat(data["commissioning_date"]) if data.get("commissioning_date") else None,
            expected_useful_life_years=data.get("expected_useful_life_years"),
            controller_id=data.get("controller_id"),
            zone_name=data.get("zone_name"),
            floor=data.get("floor"),
            coordinates=data.get("coordinates"),
            intelligence=AssetIntelligence(**data.get("intelligence", {})) if isinstance(data.get("intelligence"), dict) else AssetIntelligence(),
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

    # Controller hierarchy
    controller_ids: List[str] = field(default_factory=list)

    # Data sources
    data_source_ids: List[str] = field(default_factory=list)

    # Spatial model
    floor_plans: List[Dict[str, Any]] = field(default_factory=list)  # [{floor_id, name, image_url, svg_url}]
    zones: List[Dict[str, Any]] = field(default_factory=list)  # [{zone_id, name, type, area_sqft, asset_ids}]

    # Parts inventory
    parts_inventory: List[Dict[str, Any]] = field(default_factory=list)  # [{part_id, qty_on_hand, reorder_point}]

    # Service providers
    assigned_provider_ids: List[str] = field(default_factory=list)

    # Work order summary
    open_wo_count: int = 0
    critical_wo_count: int = 0
    avg_time_to_resolve_hours: Optional[float] = None

    # Rules engine summary
    active_rules_count: int = 0
    active_alarms_count: int = 0

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
            "controller_ids": self.controller_ids,
            "data_source_ids": self.data_source_ids,
            "floor_plans": self.floor_plans,
            "zones": self.zones,
            "parts_inventory": self.parts_inventory,
            "assigned_provider_ids": self.assigned_provider_ids,
            "open_wo_count": self.open_wo_count,
            "critical_wo_count": self.critical_wo_count,
            "avg_time_to_resolve_hours": self.avg_time_to_resolve_hours,
            "active_rules_count": self.active_rules_count,
            "active_alarms_count": self.active_alarms_count,
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
            controller_ids=data.get("controller_ids", []),
            data_source_ids=data.get("data_source_ids", []),
            floor_plans=data.get("floor_plans", []),
            zones=data.get("zones", []),
            parts_inventory=data.get("parts_inventory", []),
            assigned_provider_ids=data.get("assigned_provider_ids", []),
            open_wo_count=data.get("open_wo_count", 0),
            critical_wo_count=data.get("critical_wo_count", 0),
            avg_time_to_resolve_hours=data.get("avg_time_to_resolve_hours"),
            active_rules_count=data.get("active_rules_count", 0),
            active_alarms_count=data.get("active_alarms_count", 0),
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
