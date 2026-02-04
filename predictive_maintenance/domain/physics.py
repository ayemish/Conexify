"""
PDM Physics Models

Thermodynamic calculations for HVAC/R performance analysis.
"""

import math
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Air properties at standard conditions
AIR_DENSITY_LB_PER_CF = 0.075  # lb/ft³ at 70°F
AIR_SPECIFIC_HEAT = 0.24  # BTU/(lb·°F)
WATER_SPECIFIC_HEAT = 1.0  # BTU/(lb·°F)
WATER_DENSITY_LB_PER_GAL = 8.33  # lb/gal

# Conversion factors
BTU_PER_KWH = 3412.14
BTU_PER_TON_HR = 12000
WATTS_PER_HP = 746


# =============================================================================
# Efficiency Calculations
# =============================================================================

def calculate_cop(
    capacity_btuh: float,
    power_watts: float,
) -> float:
    """
    Calculate Coefficient of Performance.
    
    COP = Useful heating or cooling / Work input
    
    Args:
        capacity_btuh: Cooling/heating capacity in BTU/hr
        power_watts: Electrical power input in watts
    
    Returns:
        COP (dimensionless)
    """
    if power_watts <= 0:
        return 0.0
    
    power_btuh = power_watts * BTU_PER_KWH / 1000
    return capacity_btuh / power_btuh


def calculate_eer(
    capacity_btuh: float,
    power_watts: float,
) -> float:
    """
    Calculate Energy Efficiency Ratio.
    
    EER = Cooling capacity (BTU/hr) / Power input (watts)
    
    Args:
        capacity_btuh: Cooling capacity in BTU/hr
        power_watts: Power input in watts
    
    Returns:
        EER (BTU/hr per watt)
    """
    if power_watts <= 0:
        return 0.0
    
    return capacity_btuh / power_watts


def cop_to_eer(cop: float) -> float:
    """Convert COP to EER"""
    return cop * BTU_PER_KWH / 1000


def eer_to_cop(eer: float) -> float:
    """Convert EER to COP"""
    return eer * 1000 / BTU_PER_KWH


# =============================================================================
# Capacity Calculations
# =============================================================================

def calculate_capacity(
    cfm: float,
    delta_t: float,
    air_density: float = AIR_DENSITY_LB_PER_CF,
) -> float:
    """
    Calculate sensible cooling/heating capacity from airflow.
    
    Q = m_dot * Cp * ΔT
    Q = (CFM * ρ * 60) * Cp * ΔT
    
    Args:
        cfm: Airflow in cubic feet per minute
        delta_t: Temperature difference (supply - return for cooling)
        air_density: Air density in lb/ft³
    
    Returns:
        Capacity in BTU/hr
    """
    mass_flow_lb_hr = cfm * air_density * 60  # lb/hr
    capacity = mass_flow_lb_hr * AIR_SPECIFIC_HEAT * abs(delta_t)
    return capacity


def calculate_capacity_from_temps(
    supply_temp_f: float,
    return_temp_f: float,
    cfm: float,
) -> float:
    """
    Calculate sensible capacity from supply/return temps.
    
    Args:
        supply_temp_f: Supply air temperature °F
        return_temp_f: Return air temperature °F
        cfm: Airflow in CFM
    
    Returns:
        Sensible capacity in BTU/hr (positive = cooling)
    """
    delta_t = return_temp_f - supply_temp_f
    return calculate_capacity(cfm, delta_t)


def calculate_tons(capacity_btuh: float) -> float:
    """Convert BTU/hr to tons"""
    return capacity_btuh / BTU_PER_TON_HR


def calculate_btuh(tons: float) -> float:
    """Convert tons to BTU/hr"""
    return tons * BTU_PER_TON_HR


# =============================================================================
# Airflow Calculations
# =============================================================================

def estimate_airflow(
    supply_temp_f: float,
    return_temp_f: float,
    capacity_btuh: float,
) -> float:
    """
    Estimate airflow from capacity and temperatures.
    
    CFM = Q / (1.08 * ΔT)
    
    Args:
        supply_temp_f: Supply air temperature °F
        return_temp_f: Return air temperature °F
        capacity_btuh: Capacity in BTU/hr
    
    Returns:
        Estimated CFM
    """
    delta_t = abs(return_temp_f - supply_temp_f)
    if delta_t < 1:
        return 0.0
    
    # 1.08 = 60 min/hr * 0.075 lb/cf * 0.24 BTU/(lb·°F)
    cfm = capacity_btuh / (1.08 * delta_t)
    return cfm


def cfm_per_ton(cfm: float, tons: float) -> float:
    """Calculate CFM per ton ratio"""
    if tons <= 0:
        return 0.0
    return cfm / tons


def is_airflow_normal(cfm_per_ton_ratio: float) -> Tuple[bool, str]:
    """
    Check if airflow is in normal range.
    
    Normal range: 350-450 CFM/ton
    
    Returns:
        (is_normal, diagnosis)
    """
    if cfm_per_ton_ratio < 300:
        return False, "low_airflow"
    elif cfm_per_ton_ratio < 350:
        return True, "slightly_low"
    elif cfm_per_ton_ratio <= 450:
        return True, "normal"
    elif cfm_per_ton_ratio <= 500:
        return True, "slightly_high"
    else:
        return False, "high_airflow"


# =============================================================================
# Refrigerant Charge Estimation
# =============================================================================

def estimate_refrigerant_charge(
    superheat: float,
    subcool: float,
    ambient_temp_f: float,
    system_type: str = "txv",
) -> Tuple[str, float]:
    """
    Estimate refrigerant charge status from superheat/subcool.
    
    Args:
        superheat: Measured superheat °F
        subcool: Measured subcooling °F
        ambient_temp_f: Ambient temperature °F
        system_type: "txv" or "piston"
    
    Returns:
        (status, confidence)
        status: "undercharged", "normal", "overcharged"
    """
    if system_type == "txv":
        # TXV systems: subcooling is primary indicator
        if subcool < 5:
            return "undercharged", 0.8
        elif subcool > 18:
            return "overcharged", 0.8
        elif 8 <= subcool <= 14:
            return "normal", 0.9
        else:
            return "normal", 0.6
    else:
        # Fixed orifice: superheat is primary indicator
        # Adjust target based on ambient
        target_superheat = 10 + (ambient_temp_f - 80) * 0.2
        
        if superheat < target_superheat - 5:
            return "overcharged", 0.7
        elif superheat > target_superheat + 8:
            return "undercharged", 0.7
        else:
            return "normal", 0.8


def charge_loss_rate(
    current_subcool: float,
    baseline_subcool: float,
    time_hours: float,
) -> float:
    """
    Estimate refrigerant loss rate.
    
    Args:
        current_subcool: Current subcooling °F
        baseline_subcool: Baseline subcooling °F
        time_hours: Time since baseline
    
    Returns:
        Estimated charge loss rate (%/month)
    """
    if time_hours <= 0:
        return 0.0
    
    subcool_drop = baseline_subcool - current_subcool
    if subcool_drop <= 0:
        return 0.0
    
    # Rough correlation: 1°F subcool ≈ 5% charge
    charge_loss_pct = subcool_drop * 5
    
    # Convert to per-month rate
    hours_per_month = 730
    loss_rate_per_month = charge_loss_pct * (hours_per_month / time_hours)
    
    return loss_rate_per_month


# =============================================================================
# Sensible Heat Ratio
# =============================================================================

def calculate_sensible_heat_ratio(
    sensible_capacity: float,
    total_capacity: float,
) -> float:
    """
    Calculate Sensible Heat Ratio.
    
    SHR = Sensible capacity / Total capacity
    
    Args:
        sensible_capacity: Sensible cooling capacity BTU/hr
        total_capacity: Total cooling capacity BTU/hr
    
    Returns:
        SHR (0-1)
    """
    if total_capacity <= 0:
        return 0.0
    
    shr = sensible_capacity / total_capacity
    return min(1.0, max(0.0, shr))


def is_shr_normal(shr: float, space_type: str = "office") -> Tuple[bool, str]:
    """
    Check if SHR is appropriate for space type.
    
    Args:
        shr: Sensible Heat Ratio
        space_type: "office", "retail", "warehouse", "kitchen"
    
    Returns:
        (is_normal, diagnosis)
    """
    typical_shr = {
        "office": (0.70, 0.85),
        "retail": (0.75, 0.90),
        "warehouse": (0.85, 0.95),
        "kitchen": (0.50, 0.70),
        "data_center": (0.90, 1.00),
    }
    
    range_low, range_high = typical_shr.get(space_type, (0.70, 0.85))
    
    if shr < range_low:
        return False, "high_latent_load"
    elif shr > range_high:
        return False, "low_latent_load"
    else:
        return True, "normal"


# =============================================================================
# Performance Diagnostics
# =============================================================================

def diagnose_refrigerant_system(
    suction_pressure: float,
    discharge_pressure: float,
    suction_temp: float,
    liquid_temp: float,
    ambient_temp: float,
    refrigerant: str = "R410A",
) -> Dict[str, any]:
    """
    Comprehensive refrigerant system diagnosis.
    
    Returns diagnostic summary with fault indicators.
    """
    from .refrigerant import get_refrigerant
    
    ref = get_refrigerant(refrigerant)
    if ref is None:
        return {"error": f"Unknown refrigerant: {refrigerant}"}
    
    # Calculate key parameters
    superheat = ref.superheat(suction_pressure, suction_temp)
    subcool = ref.subcool(discharge_pressure, liquid_temp)
    
    # Saturation temperatures
    evap_sat_temp = ref.saturation_temperature(suction_pressure)
    cond_sat_temp = ref.saturation_temperature(discharge_pressure)
    
    # Temperature splits
    condenser_split = cond_sat_temp - ambient_temp
    
    # Diagnosis
    diagnosis = {
        "superheat": round(superheat, 1),
        "subcool": round(subcool, 1),
        "evap_sat_temp": round(evap_sat_temp, 1),
        "cond_sat_temp": round(cond_sat_temp, 1),
        "condenser_split": round(condenser_split, 1),
        "issues": [],
        "probable_faults": [],
    }
    
    # Check superheat
    sh_ok, sh_diag = ref.is_superheat_normal(superheat)
    if not sh_ok:
        diagnosis["issues"].append(f"Abnormal superheat: {sh_diag}")
        if sh_diag == "high_superheat_starving":
            diagnosis["probable_faults"].extend([
                "refrigerant_undercharge",
                "txv_restriction",
                "low_airflow",
            ])
        elif sh_diag == "low_superheat_flood_risk":
            diagnosis["probable_faults"].extend([
                "refrigerant_overcharge",
                "txv_overfeeding",
            ])
    
    # Check subcool
    sc_ok, sc_diag = ref.is_subcool_normal(subcool)
    if not sc_ok:
        diagnosis["issues"].append(f"Abnormal subcool: {sc_diag}")
        if sc_diag == "low_subcool_flash_risk":
            diagnosis["probable_faults"].extend([
                "refrigerant_undercharge",
                "condenser_restriction",
            ])
        elif sc_diag == "high_subcool_overcharge":
            diagnosis["probable_faults"].extend([
                "refrigerant_overcharge",
                "liquid_line_restriction",
            ])
    
    # Check condenser performance
    if condenser_split > 30:
        diagnosis["issues"].append(f"High condenser split: {condenser_split:.1f}°F")
        diagnosis["probable_faults"].extend([
            "condenser_fouling",
            "condenser_fan_issue",
            "non_condensables",
        ])
    elif condenser_split < 10:
        diagnosis["issues"].append(f"Low condenser split: {condenser_split:.1f}°F")
        # Could indicate low load or sensor issue
    
    # Deduplicate faults
    diagnosis["probable_faults"] = list(set(diagnosis["probable_faults"]))
    
    # Overall status
    if not diagnosis["issues"]:
        diagnosis["status"] = "normal"
    elif len(diagnosis["issues"]) == 1:
        diagnosis["status"] = "minor_issue"
    else:
        diagnosis["status"] = "multiple_issues"
    
    return diagnosis
