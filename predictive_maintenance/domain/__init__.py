"""
PDM Domain Models

Physical and thermodynamic models for HVAC/R equipment.
"""

from .refrigerant import (
    RefrigerantProperties,
    R410A,
    R22,
    R134A,
    R404A,
    get_refrigerant,
    calculate_superheat,
    calculate_subcool,
    saturation_temperature,
    saturation_pressure,
)
from .equipment import (
    EquipmentSpecs,
    RTUSpecs,
    ChillerSpecs,
    RefrigerationSpecs,
    DegradationModel,
    efficiency_degradation_curve,
)
from .physics import (
    calculate_cop,
    calculate_eer,
    calculate_capacity,
    estimate_refrigerant_charge,
    estimate_airflow,
    calculate_sensible_heat_ratio,
)

__all__ = [
    # Refrigerant
    "RefrigerantProperties",
    "R410A",
    "R22",
    "R134A",
    "R404A",
    "get_refrigerant",
    "calculate_superheat",
    "calculate_subcool",
    "saturation_temperature",
    "saturation_pressure",
    # Equipment
    "EquipmentSpecs",
    "RTUSpecs",
    "ChillerSpecs",
    "RefrigerationSpecs",
    "DegradationModel",
    "efficiency_degradation_curve",
    # Physics
    "calculate_cop",
    "calculate_eer",
    "calculate_capacity",
    "estimate_refrigerant_charge",
    "estimate_airflow",
    "calculate_sensible_heat_ratio",
]
