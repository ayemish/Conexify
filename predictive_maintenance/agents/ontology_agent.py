"""
Ontology Agent (N3)

CrewAI agent that manages the HVAC/R equipment ontology — asset types,
required sensor sets, fault taxonomies, and maintenance action catalogs.
Replaces the TypeScript ontology service from quest-agent-forge-main.

Responsibilities:
- Define and query asset type hierarchies (RTU, AHU, Chiller, etc.)
- Map required sensors per asset type for coverage analysis
- Maintain fault taxonomy with severity and recommended actions
- Provide structured lookups for other agents (SensorCoverage, KG, Triage)

Addresses N3 from the FRD implementation plan.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from shared.agents.crewai_base import (
    Agent, Task, Crew, Process, CREWAI_AVAILABLE,
    BaseCrewAgent, CrewAIAgentConfig, AgentCategory, AgentRole,
)

logger = logging.getLogger(__name__)

# CrewAI @tool decorator with fallback
try:
    from crewai.tools import tool as crewai_tool
except ImportError:
    def crewai_tool(name_or_func=None):
        def decorator(func):
            func.tool_name = name_or_func if isinstance(name_or_func, str) else func.__name__
            return func
        if callable(name_or_func):
            return decorator(name_or_func)
        return decorator


# =============================================================================
# Ontology Data Store
# =============================================================================

# Asset type definitions with required sensors
ASSET_TYPES: Dict[str, Dict[str, Any]] = {
    "RTU": {
        "full_name": "Rooftop Unit",
        "category": "HVAC",
        "required_sensors": [
            "supply_air_temp", "return_air_temp", "outside_air_temp",
            "discharge_pressure", "suction_pressure", "compressor_current",
            "supply_fan_status", "filter_dp", "refrigerant_level",
        ],
        "optional_sensors": [
            "humidity", "co2", "vibration", "power_meter", "economizer_position",
        ],
        "typical_faults": ["compressor_failure", "refrigerant_leak", "fan_belt_wear",
                           "filter_clog", "economizer_stuck", "thermostat_drift"],
    },
    "AHU": {
        "full_name": "Air Handling Unit",
        "category": "HVAC",
        "required_sensors": [
            "supply_air_temp", "return_air_temp", "mixed_air_temp",
            "supply_fan_speed", "supply_fan_current", "filter_dp",
            "cooling_valve_position", "heating_valve_position",
        ],
        "optional_sensors": [
            "humidity", "co2", "vfd_frequency", "duct_static_pressure",
        ],
        "typical_faults": ["fan_bearing_wear", "coil_fouling", "damper_stuck",
                           "vfd_fault", "filter_clog", "valve_leak"],
    },
    "CHILLER": {
        "full_name": "Chiller",
        "category": "HVAC",
        "required_sensors": [
            "chilled_water_supply_temp", "chilled_water_return_temp",
            "condenser_water_supply_temp", "condenser_water_return_temp",
            "compressor_current", "oil_pressure", "refrigerant_pressure_high",
            "refrigerant_pressure_low", "evaporator_approach",
        ],
        "optional_sensors": [
            "vibration", "oil_temp", "bearing_temp", "power_meter",
            "condenser_approach", "subcooling", "superheat",
        ],
        "typical_faults": ["tube_fouling", "refrigerant_leak", "compressor_surge",
                           "oil_contamination", "low_charge", "sensor_drift"],
    },
    "WALKIN_COOLER": {
        "full_name": "Walk-In Cooler/Freezer",
        "category": "Refrigeration",
        "required_sensors": [
            "box_temp", "discharge_pressure", "suction_pressure",
            "defrost_status", "door_status", "compressor_current",
        ],
        "optional_sensors": [
            "evaporator_temp", "condenser_temp", "superheat", "subcooling",
        ],
        "typical_faults": ["door_seal_failure", "defrost_heater_fail",
                           "refrigerant_leak", "compressor_failure",
                           "evaporator_ice_buildup", "condenser_dirty"],
    },
    "DISPLAY_CASE": {
        "full_name": "Refrigerated Display Case",
        "category": "Refrigeration",
        "required_sensors": [
            "case_temp", "discharge_air_temp", "suction_pressure",
            "defrost_status",
        ],
        "optional_sensors": [
            "door_status", "lighting_status", "fan_status",
        ],
        "typical_faults": ["temp_excursion", "defrost_failure", "fan_failure",
                           "door_heater_fail", "refrigerant_restriction"],
    },
}

# Fault taxonomy with severity and recommended actions
FAULT_TAXONOMY: Dict[str, Dict[str, Any]] = {
    "compressor_failure": {
        "severity": "critical",
        "category": "mechanical",
        "indicators": ["compressor_current_spike", "pressure_imbalance", "vibration_anomaly"],
        "recommended_actions": ["emergency_shutdown", "technician_dispatch", "replacement_assessment"],
        "typical_mttr_hours": 8,
    },
    "refrigerant_leak": {
        "severity": "high",
        "category": "refrigerant",
        "indicators": ["pressure_drop", "superheat_high", "capacity_loss"],
        "recommended_actions": ["leak_detection_survey", "repair_and_recharge", "epa_reporting"],
        "typical_mttr_hours": 4,
    },
    "filter_clog": {
        "severity": "medium",
        "category": "airflow",
        "indicators": ["filter_dp_high", "airflow_reduced", "supply_temp_drift"],
        "recommended_actions": ["filter_replacement", "schedule_pm"],
        "typical_mttr_hours": 1,
    },
    "fan_belt_wear": {
        "severity": "medium",
        "category": "mechanical",
        "indicators": ["vibration_anomaly", "noise_increase", "fan_speed_fluctuation"],
        "recommended_actions": ["belt_inspection", "belt_replacement"],
        "typical_mttr_hours": 2,
    },
    "economizer_stuck": {
        "severity": "medium",
        "category": "controls",
        "indicators": ["mixed_air_temp_anomaly", "energy_waste", "damper_position_static"],
        "recommended_actions": ["actuator_inspection", "damper_linkage_repair"],
        "typical_mttr_hours": 3,
    },
    "thermostat_drift": {
        "severity": "low",
        "category": "controls",
        "indicators": ["setpoint_deviation", "short_cycling", "occupant_complaints"],
        "recommended_actions": ["recalibration", "thermostat_replacement"],
        "typical_mttr_hours": 1,
    },
    "tube_fouling": {
        "severity": "medium",
        "category": "efficiency",
        "indicators": ["approach_temp_high", "capacity_loss", "energy_increase"],
        "recommended_actions": ["chemical_cleaning", "mechanical_cleaning"],
        "typical_mttr_hours": 6,
    },
    "coil_fouling": {
        "severity": "medium",
        "category": "efficiency",
        "indicators": ["coil_dp_high", "capacity_loss", "discharge_temp_high"],
        "recommended_actions": ["coil_cleaning", "schedule_pm"],
        "typical_mttr_hours": 2,
    },
    "sensor_drift": {
        "severity": "low",
        "category": "instrumentation",
        "indicators": ["reading_inconsistency", "calibration_out_of_range"],
        "recommended_actions": ["recalibration", "sensor_replacement"],
        "typical_mttr_hours": 1,
    },
    "door_seal_failure": {
        "severity": "high",
        "category": "refrigeration",
        "indicators": ["temp_excursion", "compressor_runtime_high", "energy_increase"],
        "recommended_actions": ["gasket_replacement", "door_adjustment"],
        "typical_mttr_hours": 2,
    },
    "temp_excursion": {
        "severity": "critical",
        "category": "food_safety",
        "indicators": ["case_temp_above_threshold", "product_at_risk"],
        "recommended_actions": ["emergency_response", "product_inspection", "root_cause_analysis"],
        "typical_mttr_hours": 1,
    },
}


# =============================================================================
# @tool Functions
# =============================================================================

@crewai_tool("get_asset_type_info")
def get_asset_type_info(asset_type: str) -> dict:
    """Get ontology definition for an asset type — required sensors, typical faults, category.
    asset_type examples: RTU, AHU, CHILLER, WALKIN_COOLER, DISPLAY_CASE."""
    key = asset_type.upper().replace(" ", "_").replace("-", "_")
    info = ASSET_TYPES.get(key)
    if not info:
        return {
            "error": f"Unknown asset type: {asset_type}",
            "known_types": sorted(ASSET_TYPES.keys()),
        }
    return {"asset_type": key, **info}


@crewai_tool("get_required_sensors")
def get_required_sensors(asset_type: str) -> dict:
    """Get the required sensor list for an asset type.
    Returns required and optional sensors separately."""
    key = asset_type.upper().replace(" ", "_").replace("-", "_")
    info = ASSET_TYPES.get(key)
    if not info:
        return {"error": f"Unknown asset type: {asset_type}"}
    return {
        "asset_type": key,
        "required": info.get("required_sensors", []),
        "optional": info.get("optional_sensors", []),
        "total_required": len(info.get("required_sensors", [])),
    }


@crewai_tool("get_fault_info")
def get_fault_info(fault_type: str) -> dict:
    """Get ontology definition for a fault type — severity, indicators, recommended actions.
    fault_type examples: compressor_failure, refrigerant_leak, filter_clog."""
    key = fault_type.lower().replace(" ", "_").replace("-", "_")
    info = FAULT_TAXONOMY.get(key)
    if not info:
        return {
            "error": f"Unknown fault type: {fault_type}",
            "known_faults": sorted(FAULT_TAXONOMY.keys()),
        }
    return {"fault_type": key, **info}


@crewai_tool("find_faults_by_indicator")
def find_faults_by_indicator(indicator: str) -> dict:
    """Find all fault types that list a given indicator/symptom.
    Useful for differential diagnosis from observed symptoms."""
    indicator_lower = indicator.lower()
    matches = []
    for fault_type, info in FAULT_TAXONOMY.items():
        for ind in info.get("indicators", []):
            if indicator_lower in ind.lower():
                matches.append({
                    "fault_type": fault_type,
                    "severity": info["severity"],
                    "matched_indicator": ind,
                })
                break
    return {
        "indicator": indicator,
        "matching_faults": matches,
        "count": len(matches),
    }


@crewai_tool("get_faults_for_asset_type")
def get_faults_for_asset_type(asset_type: str) -> dict:
    """Get all fault types that are typical for a given asset type,
    enriched with severity and recommended actions from the taxonomy."""
    key = asset_type.upper().replace(" ", "_").replace("-", "_")
    info = ASSET_TYPES.get(key)
    if not info:
        return {"error": f"Unknown asset type: {asset_type}"}

    faults = []
    for ft in info.get("typical_faults", []):
        fault_info = FAULT_TAXONOMY.get(ft, {})
        faults.append({
            "fault_type": ft,
            "severity": fault_info.get("severity", "unknown"),
            "category": fault_info.get("category", "unknown"),
            "typical_mttr_hours": fault_info.get("typical_mttr_hours"),
            "recommended_actions": fault_info.get("recommended_actions", []),
        })
    return {
        "asset_type": key,
        "fault_count": len(faults),
        "faults": faults,
    }


@crewai_tool("list_all_asset_types")
def list_all_asset_types() -> dict:
    """List all known asset types in the ontology with their categories."""
    return {
        "asset_types": [
            {"type": k, "full_name": v["full_name"], "category": v["category"]}
            for k, v in ASSET_TYPES.items()
        ],
        "count": len(ASSET_TYPES),
    }


# =============================================================================
# Ontology CrewAI Agent
# =============================================================================

class OntologyAgent(BaseCrewAgent):
    """
    CrewAI agent that manages the HVAC/R equipment ontology.

    Provides structured lookups for asset types, required sensors,
    fault taxonomies, and maintenance action catalogs.
    """

    def __init__(self, **kwargs):
        config = CrewAIAgentConfig(
            agent_id="ontology",
            role=AgentRole.DATA_STEWARD,
            category=AgentCategory.DATA,
            name="HVAC/R Ontology Specialist",
            goal=(
                "Maintain and query the HVAC/R equipment ontology. Provide "
                "structured information about asset types, required sensors, "
                "fault taxonomies, and maintenance actions to support diagnostic "
                "and planning workflows."
            ),
            backstory=(
                "You are an HVAC/R domain expert who has cataloged every major "
                "equipment type, failure mode, sensor requirement, and maintenance "
                "procedure. Your ontology is the authoritative reference for the "
                "entire predictive maintenance platform."
            ),
        )
        super().__init__(config, **kwargs)

    @property
    def tools(self) -> list:
        return [
            get_asset_type_info,
            get_required_sensors,
            get_fault_info,
            find_faults_by_indicator,
            get_faults_for_asset_type,
            list_all_asset_types,
        ]
