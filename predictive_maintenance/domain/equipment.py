"""
PDM Equipment Specifications and Degradation Models

Equipment catalog with nominal specifications and degradation curves.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from enum import Enum


class EquipmentType(str, Enum):
    """Equipment types"""
    RTU = "rtu"  # Rooftop Unit
    SPLIT = "split"  # Split System
    CHILLER = "chiller"
    REFRIGERATION = "refrigeration"
    HEAT_PUMP = "heat_pump"
    VRF = "vrf"  # Variable Refrigerant Flow


@dataclass
class EquipmentSpecs:
    """Base equipment specifications"""
    equipment_type: EquipmentType
    manufacturer: str
    model_number: str
    
    # Capacity
    nominal_capacity_tons: float
    nominal_capacity_btuh: float = 0.0
    
    # Electrical
    nominal_voltage: float = 208.0
    nominal_phases: int = 3
    full_load_amps: float = 0.0
    locked_rotor_amps: float = 0.0
    
    # Refrigerant
    refrigerant_type: str = "R410A"
    factory_charge_lb: float = 0.0
    
    # Efficiency ratings
    seer: Optional[float] = None  # Seasonal Energy Efficiency Ratio
    eer: Optional[float] = None   # Energy Efficiency Ratio
    cop: Optional[float] = None   # Coefficient of Performance
    
    # Physical
    weight_lb: float = 0.0
    
    # Dates
    manufacture_date: Optional[datetime] = None
    install_date: Optional[datetime] = None
    warranty_years: int = 5
    
    # Expected component lifespans (years)
    compressor_lifespan: float = 15.0
    fan_motor_lifespan: float = 12.0
    contactor_lifespan: float = 8.0
    capacitor_lifespan: float = 6.0
    
    def __post_init__(self):
        if self.nominal_capacity_btuh == 0.0:
            self.nominal_capacity_btuh = self.nominal_capacity_tons * 12000
    
    def age_years(self, reference_date: datetime = None) -> float:
        """Calculate equipment age in years"""
        if self.install_date is None:
            return 0.0
        ref = reference_date or datetime.utcnow()
        delta = ref - self.install_date
        return delta.days / 365.25
    
    def expected_efficiency_degradation(self, age_years: float = None) -> float:
        """
        Estimate efficiency degradation based on age.
        
        Returns:
            Efficiency multiplier (1.0 = new, 0.8 = 20% degraded)
        """
        age = age_years if age_years is not None else self.age_years()
        return efficiency_degradation_curve(age)
    
    def component_failure_probability(self, component: str, age_years: float = None) -> float:
        """
        Estimate component failure probability.
        
        Uses Weibull distribution model.
        """
        age = age_years if age_years is not None else self.age_years()
        
        lifespans = {
            "compressor": self.compressor_lifespan,
            "fan_motor": self.fan_motor_lifespan,
            "contactor": self.contactor_lifespan,
            "capacitor": self.capacitor_lifespan,
        }
        
        lifespan = lifespans.get(component, 10.0)
        
        # Weibull CDF: F(t) = 1 - exp(-(t/λ)^k)
        # k = 2.0 (typical for mechanical wear)
        k = 2.0
        lambda_param = lifespan / (math.gamma(1 + 1/k))
        
        return 1 - math.exp(-((age / lambda_param) ** k))


@dataclass
class RTUSpecs(EquipmentSpecs):
    """Rooftop Unit specifications"""
    equipment_type: EquipmentType = EquipmentType.RTU
    
    # Airflow
    nominal_cfm: float = 0.0
    cfm_per_ton: float = 400.0
    
    # Fan
    supply_fan_hp: float = 0.0
    condenser_fan_hp: float = 0.0
    
    # Heating
    has_gas_heat: bool = False
    gas_heat_btuh: float = 0.0
    has_electric_heat: bool = False
    electric_heat_kw: float = 0.0
    
    # Economizer
    has_economizer: bool = False
    economizer_type: str = "dry_bulb"  # dry_bulb, enthalpy, differential
    
    # Compressor
    n_compressors: int = 1
    compressor_type: str = "scroll"  # scroll, reciprocating, screw
    
    def __post_init__(self):
        super().__post_init__()
        if self.nominal_cfm == 0.0:
            self.nominal_cfm = self.nominal_capacity_tons * self.cfm_per_ton


@dataclass
class ChillerSpecs(EquipmentSpecs):
    """Chiller specifications"""
    equipment_type: EquipmentType = EquipmentType.CHILLER
    
    # Chiller specific
    chiller_type: str = "air_cooled"  # air_cooled, water_cooled
    compressor_type: str = "screw"  # screw, centrifugal, scroll
    
    # Water side
    chilled_water_flow_gpm: float = 0.0
    entering_water_temp: float = 54.0
    leaving_water_temp: float = 44.0
    
    # Condenser
    condenser_water_flow_gpm: float = 0.0
    
    # Full load kW/ton
    full_load_kw_per_ton: float = 0.6
    
    # Part load efficiency
    iplv: Optional[float] = None  # Integrated Part Load Value


@dataclass
class RefrigerationSpecs(EquipmentSpecs):
    """Refrigeration system specifications"""
    equipment_type: EquipmentType = EquipmentType.REFRIGERATION
    
    # Application
    application: str = "medium_temp"  # low_temp, medium_temp, high_temp
    
    # Temperature ranges
    target_box_temp: float = 35.0  # °F
    
    # Evaporator
    evaporator_type: str = "unit_cooler"
    evaporator_td: float = 10.0  # Temperature difference
    
    # Defrost
    defrost_type: str = "electric"  # electric, hot_gas, off_cycle
    defrost_frequency_hours: float = 6.0


# =============================================================================
# Degradation Models
# =============================================================================

@dataclass
class DegradationModel:
    """Equipment degradation tracking"""
    asset_id: str
    equipment_specs: EquipmentSpecs
    
    # Observed degradation factors
    efficiency_factor: float = 1.0  # Current efficiency vs nominal
    capacity_factor: float = 1.0   # Current capacity vs nominal
    
    # Component health (0-1, 1=healthy)
    compressor_health: float = 1.0
    condenser_health: float = 1.0
    evaporator_health: float = 1.0
    fan_health: float = 1.0
    controls_health: float = 1.0
    
    # Fault history
    fault_count: int = 0
    last_fault_date: Optional[datetime] = None
    
    # Maintenance
    last_maintenance_date: Optional[datetime] = None
    maintenance_score: float = 1.0  # Well-maintained = 1.0
    
    def overall_health_score(self) -> float:
        """Calculate overall equipment health score"""
        weights = {
            "compressor": 0.35,
            "condenser": 0.20,
            "evaporator": 0.20,
            "fan": 0.15,
            "controls": 0.10,
        }
        
        score = (
            weights["compressor"] * self.compressor_health +
            weights["condenser"] * self.condenser_health +
            weights["evaporator"] * self.evaporator_health +
            weights["fan"] * self.fan_health +
            weights["controls"] * self.controls_health
        )
        
        # Adjust for maintenance
        score *= (0.8 + 0.2 * self.maintenance_score)
        
        return min(1.0, max(0.0, score))
    
    def remaining_useful_life_estimate(self) -> Tuple[float, float]:
        """
        Estimate remaining useful life.
        
        Returns:
            (min_years, max_years) estimate
        """
        age = self.equipment_specs.age_years()
        health = self.overall_health_score()
        
        # Base expected life
        base_life = self.equipment_specs.compressor_lifespan
        
        # Adjust for current health
        remaining = base_life - age
        
        # Health-adjusted estimate
        adjusted_remaining = remaining * health
        
        # Return range
        return (
            max(0, adjusted_remaining * 0.7),
            max(0, adjusted_remaining * 1.3)
        )
    
    def update_from_telemetry(
        self,
        actual_capacity_ratio: float,
        actual_efficiency_ratio: float,
        sensor_anomalies: Dict[str, float],
    ):
        """Update degradation model from telemetry analysis"""
        # Update efficiency and capacity factors
        self.efficiency_factor = 0.9 * self.efficiency_factor + 0.1 * actual_efficiency_ratio
        self.capacity_factor = 0.9 * self.capacity_factor + 0.1 * actual_capacity_ratio
        
        # Update component health from sensor patterns
        if "discharge_pressure" in sensor_anomalies:
            self.condenser_health *= (1 - 0.1 * sensor_anomalies["discharge_pressure"])
        
        if "suction_pressure" in sensor_anomalies:
            self.evaporator_health *= (1 - 0.1 * sensor_anomalies["suction_pressure"])
        
        if "compressor_current" in sensor_anomalies:
            self.compressor_health *= (1 - 0.1 * sensor_anomalies["compressor_current"])
        
        # Clamp values
        self.compressor_health = max(0.0, min(1.0, self.compressor_health))
        self.condenser_health = max(0.0, min(1.0, self.condenser_health))
        self.evaporator_health = max(0.0, min(1.0, self.evaporator_health))


def efficiency_degradation_curve(age_years: float, maintenance_factor: float = 1.0) -> float:
    """
    Model efficiency degradation over time.
    
    Based on DOE studies showing ~2-5% degradation per year for unmaintained equipment,
    reduced to ~0.5-1% per year with proper maintenance.
    
    Args:
        age_years: Equipment age in years
        maintenance_factor: 1.0 = well maintained, 0.0 = neglected
    
    Returns:
        Efficiency multiplier (1.0 = new, lower = degraded)
    """
    # Base degradation rate (unmaintained)
    base_rate = 0.03  # 3% per year
    
    # Maintenance reduces degradation
    effective_rate = base_rate * (1 - 0.7 * maintenance_factor)
    
    # Exponential decay with floor
    efficiency = math.exp(-effective_rate * age_years)
    
    # Floor at 60% (equipment still runs but poorly)
    return max(0.60, efficiency)


def capacity_degradation_curve(
    age_years: float,
    fouling_factor: float = 0.0,
    refrigerant_loss_pct: float = 0.0,
) -> float:
    """
    Model capacity degradation.
    
    Args:
        age_years: Equipment age
        fouling_factor: Coil fouling (0-1, 0=clean)
        refrigerant_loss_pct: Refrigerant loss percentage
    
    Returns:
        Capacity multiplier
    """
    # Age-based degradation (slower than efficiency)
    age_factor = math.exp(-0.01 * age_years)
    
    # Fouling impact (can reduce capacity significantly)
    fouling_impact = 1 - 0.3 * fouling_factor
    
    # Refrigerant loss impact (roughly proportional)
    refrigerant_impact = 1 - 0.8 * (refrigerant_loss_pct / 100)
    
    return max(0.3, age_factor * fouling_impact * refrigerant_impact)
