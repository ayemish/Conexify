"""
PDM Refrigerant Properties

Thermodynamic properties and calculations for common refrigerants.
Uses simplified correlations suitable for predictive maintenance.
"""

import math
from dataclasses import dataclass
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)


@dataclass
class RefrigerantProperties:
    """
    Refrigerant thermodynamic properties.
    
    Pressure-temperature relationships use Antoine equation approximations:
    log10(P) = A - B / (C + T)
    
    Where P is in psia and T is in °F.
    """
    name: str
    formula: str
    
    # Antoine equation coefficients for saturation curve
    antoine_A: float
    antoine_B: float
    antoine_C: float
    
    # Temperature limits (°F)
    t_min: float
    t_max: float
    
    # Critical point
    t_critical: float  # °F
    p_critical: float  # psia
    
    # Normal boiling point
    t_boiling: float  # °F at 14.7 psia
    
    # Typical operating range
    typical_suction_temp_range: tuple = (-20, 60)  # °F
    typical_discharge_temp_range: tuple = (100, 250)  # °F
    
    # Charge density (lb/ton nominal)
    charge_density_lb_per_ton: float = 3.0
    
    def saturation_pressure(self, temperature_f: float) -> float:
        """
        Calculate saturation pressure at given temperature.
        
        Args:
            temperature_f: Temperature in Fahrenheit
            
        Returns:
            Pressure in PSIG
        """
        if temperature_f < self.t_min or temperature_f > self.t_max:
            logger.warning(f"Temperature {temperature_f}°F outside valid range [{self.t_min}, {self.t_max}]")
        
        # Antoine equation
        log_p = self.antoine_A - self.antoine_B / (self.antoine_C + temperature_f)
        p_psia = 10 ** log_p
        
        # Convert to PSIG (gauge)
        return p_psia - 14.7
    
    def saturation_temperature(self, pressure_psig: float) -> float:
        """
        Calculate saturation temperature at given pressure.
        
        Args:
            pressure_psig: Pressure in PSIG
            
        Returns:
            Temperature in Fahrenheit
        """
        # Convert to absolute
        p_psia = pressure_psig + 14.7
        
        if p_psia <= 0:
            raise ValueError(f"Invalid pressure: {pressure_psig} PSIG")
        
        # Inverse Antoine equation
        log_p = math.log10(p_psia)
        temperature_f = self.antoine_B / (self.antoine_A - log_p) - self.antoine_C
        
        return temperature_f
    
    def superheat(self, suction_pressure_psig: float, suction_temp_f: float) -> float:
        """
        Calculate superheat.
        
        Args:
            suction_pressure_psig: Suction pressure in PSIG
            suction_temp_f: Suction line temperature in °F
            
        Returns:
            Superheat in °F
        """
        sat_temp = self.saturation_temperature(suction_pressure_psig)
        return suction_temp_f - sat_temp
    
    def subcool(self, discharge_pressure_psig: float, liquid_temp_f: float) -> float:
        """
        Calculate subcooling.
        
        Args:
            discharge_pressure_psig: Discharge/liquid pressure in PSIG
            liquid_temp_f: Liquid line temperature in °F
            
        Returns:
            Subcooling in °F
        """
        sat_temp = self.saturation_temperature(discharge_pressure_psig)
        return sat_temp - liquid_temp_f
    
    def is_superheat_normal(self, superheat: float, system_type: str = "dx") -> tuple:
        """
        Check if superheat is in normal range.
        
        Returns:
            (is_normal, diagnosis)
        """
        if system_type == "dx":
            # Direct expansion systems
            if superheat < 5:
                return False, "low_superheat_flood_risk"
            elif superheat > 20:
                return False, "high_superheat_starving"
            elif 8 <= superheat <= 14:
                return True, "optimal"
            else:
                return True, "acceptable"
        else:
            # Flooded systems
            if superheat < 0:
                return False, "flooded_normal"  # Expected for flooded
            elif superheat > 10:
                return False, "high_superheat"
            return True, "normal"
    
    def is_subcool_normal(self, subcool: float) -> tuple:
        """
        Check if subcooling is in normal range.
        
        Returns:
            (is_normal, diagnosis)
        """
        if subcool < 2:
            return False, "low_subcool_flash_risk"
        elif subcool > 20:
            return False, "high_subcool_overcharge"
        elif 8 <= subcool <= 14:
            return True, "optimal"
        else:
            return True, "acceptable"


# =============================================================================
# Common Refrigerant Definitions
# =============================================================================

R410A = RefrigerantProperties(
    name="R-410A",
    formula="CH2F2/CHF2CF3",
    # Fitted Antoine coefficients for R-410A (P in psia, T in °F)
    # Calibrated to typical PT chart points: 40°F≈118 psig, 80°F≈250 psig, 120°F≈400 psig.
    antoine_A=3.536288280836719,
    antoine_B=209.89454876319058,
    antoine_C=108.5,
    t_min=-60,
    t_max=150,
    t_critical=162.0,
    p_critical=711.0,
    t_boiling=-61.1,
    typical_suction_temp_range=(30, 65),
    typical_discharge_temp_range=(140, 220),
    charge_density_lb_per_ton=3.5,
)

R22 = RefrigerantProperties(
    name="R-22",
    formula="CHClF2",
    # Fitted Antoine coefficients for R-22
    antoine_A=6.9624,
    antoine_B=1067.5,
    antoine_C=395.0,
    t_min=-60,
    t_max=200,
    t_critical=204.8,
    p_critical=721.9,
    t_boiling=-41.4,
    typical_suction_temp_range=(20, 60),
    typical_discharge_temp_range=(130, 200),
    charge_density_lb_per_ton=2.8,
)

R134A = RefrigerantProperties(
    name="R-134a",
    formula="CH2FCF3",
    # Fitted Antoine coefficients for R-134a
    antoine_A=6.8898,
    antoine_B=1018.6,
    antoine_C=378.2,
    t_min=-40,
    t_max=200,
    t_critical=213.9,
    p_critical=588.9,
    t_boiling=-15.1,
    typical_suction_temp_range=(20, 55),
    typical_discharge_temp_range=(120, 180),
    charge_density_lb_per_ton=2.5,
)

R404A = RefrigerantProperties(
    name="R-404A",
    formula="R125/R143a/R134a",
    # Fitted Antoine coefficients for R-404A
    antoine_A=7.0234,
    antoine_B=1089.2,
    antoine_C=382.8,
    t_min=-80,
    t_max=150,
    t_critical=162.5,
    p_critical=541.1,
    t_boiling=-51.4,
    typical_suction_temp_range=(-30, 30),
    typical_discharge_temp_range=(100, 180),
    charge_density_lb_per_ton=4.0,
)

# Refrigerant lookup
REFRIGERANTS: Dict[str, RefrigerantProperties] = {
    "R410A": R410A,
    "R-410A": R410A,
    "r410a": R410A,
    "R22": R22,
    "R-22": R22,
    "r22": R22,
    "R134A": R134A,
    "R-134a": R134A,
    "r134a": R134A,
    "R404A": R404A,
    "R-404A": R404A,
    "r404a": R404A,
}


def get_refrigerant(name: str) -> Optional[RefrigerantProperties]:
    """Get refrigerant properties by name"""
    return REFRIGERANTS.get(name)


def calculate_superheat(
    refrigerant: str,
    suction_pressure_psig: float,
    suction_temp_f: float
) -> Optional[float]:
    """
    Calculate superheat for a given refrigerant.
    
    Args:
        refrigerant: Refrigerant name (e.g., "R410A")
        suction_pressure_psig: Suction pressure in PSIG
        suction_temp_f: Suction line temperature in °F
    
    Returns:
        Superheat in °F, or None if refrigerant unknown
    """
    ref = get_refrigerant(refrigerant)
    if ref is None:
        return None
    return ref.superheat(suction_pressure_psig, suction_temp_f)


def calculate_subcool(
    refrigerant: str,
    discharge_pressure_psig: float,
    liquid_temp_f: float
) -> Optional[float]:
    """
    Calculate subcooling for a given refrigerant.
    
    Args:
        refrigerant: Refrigerant name
        discharge_pressure_psig: Discharge/liquid pressure in PSIG
        liquid_temp_f: Liquid line temperature in °F
    
    Returns:
        Subcooling in °F, or None if refrigerant unknown
    """
    ref = get_refrigerant(refrigerant)
    if ref is None:
        return None
    return ref.subcool(discharge_pressure_psig, liquid_temp_f)


def saturation_temperature(refrigerant: str, pressure_psig: float) -> Optional[float]:
    """Get saturation temperature for refrigerant at given pressure"""
    ref = get_refrigerant(refrigerant)
    if ref is None:
        return None
    return ref.saturation_temperature(pressure_psig)


def saturation_pressure(refrigerant: str, temperature_f: float) -> Optional[float]:
    """Get saturation pressure for refrigerant at given temperature"""
    ref = get_refrigerant(refrigerant)
    if ref is None:
        return None
    return ref.saturation_pressure(temperature_f)
