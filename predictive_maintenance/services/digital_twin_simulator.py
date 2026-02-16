"""
Physics-Informed Digital Twin Simulator

Extends the state-only digital twin with a thermodynamic cycle model
for HVAC/R equipment.  Enables:
1. **What-if simulation** — "if we delay maintenance 2 weeks, what happens?"
2. **Parameter estimation** — real-time calibration of isentropic efficiency,
   UA values, and degradation coefficients
3. **Fault injection** — simulate fault progression for training / validation

The simulator uses the physics models from ``domain.physics`` and wraps
them with degradation overlays and uncertainty quantification.

Error modelling:
- Tracks prediction residuals for each thermodynamic variable
- Maintains running RMSE and bias for simulator vs actual telemetry
- Reports model uncertainty as ±2σ bands on simulated values

References:
- ASHRAE Handbook — Fundamentals (psychrometrics, heat transfer)
- Braun, "Methodologies for the Design and Control of Central Cooling Plants", 1988
"""

import logging
import math
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ── Degradation models ───────────────────────────────────────────────

FAULT_DEGRADATION_MODELS = {
    "refrigerant_leak": {
        "affected_params": ["charge_fraction", "superheat_delta_f"],
        "rate_per_hour": 0.0002,
        "acceleration": 1.0005,
    },
    "condenser_fouling": {
        "affected_params": ["condenser_ua_fraction"],
        "rate_per_hour": 0.00005,
        "acceleration": 1.0001,
    },
    "compressor_degradation": {
        "affected_params": ["isentropic_efficiency", "volumetric_efficiency"],
        "rate_per_hour": 0.00003,
        "acceleration": 1.0002,
    },
    "evaporator_icing": {
        "affected_params": ["evaporator_ua_fraction"],
        "rate_per_hour": 0.001,
        "acceleration": 1.001,
    },
    "fan_degradation": {
        "affected_params": ["fan_efficiency"],
        "rate_per_hour": 0.00002,
        "acceleration": 1.0001,
    },
}


# ── Data classes ─────────────────────────────────────────────────────

@dataclass
class TwinParameters:
    """Calibratable thermodynamic parameters."""
    # Compressor
    isentropic_efficiency: float = 0.72
    volumetric_efficiency: float = 0.85
    compressor_displacement_cfh: float = 50.0

    # Heat exchangers
    condenser_ua_fraction: float = 1.0  # 1.0 = design condition
    evaporator_ua_fraction: float = 1.0

    # Refrigerant
    charge_fraction: float = 1.0  # 1.0 = fully charged
    superheat_delta_f: float = 10.0
    subcooling_delta_f: float = 8.0

    # Fan
    fan_efficiency: float = 0.75

    # External
    ambient_temp_f: float = 95.0
    return_air_temp_f: float = 75.0
    supply_air_setpoint_f: float = 55.0

    def copy(self) -> "TwinParameters":
        return TwinParameters(**self.__dict__)


@dataclass
class SimulationResult:
    """Output of a single simulation step."""
    sim_id: str = field(default_factory=lambda: str(uuid.uuid4())[:10])
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Simulated readings
    discharge_temp_f: float = 0.0
    suction_temp_f: float = 0.0
    supply_air_temp_f: float = 0.0
    condenser_pressure_psig: float = 0.0
    evaporator_pressure_psig: float = 0.0
    compressor_power_w: float = 0.0
    cooling_capacity_btuh: float = 0.0
    cop: float = 0.0

    # Uncertainty (±2σ)
    discharge_temp_uncertainty: float = 0.0
    supply_air_uncertainty: float = 0.0
    power_uncertainty: float = 0.0
    cop_uncertainty: float = 0.0

    # Degradation state
    parameters_used: Dict[str, float] = field(default_factory=dict)
    fault_active: Optional[str] = None
    hours_simulated: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sim_id": self.sim_id,
            "timestamp": self.timestamp.isoformat(),
            "discharge_temp_f": round(self.discharge_temp_f, 1),
            "suction_temp_f": round(self.suction_temp_f, 1),
            "supply_air_temp_f": round(self.supply_air_temp_f, 1),
            "compressor_power_w": round(self.compressor_power_w, 1),
            "cooling_capacity_btuh": round(self.cooling_capacity_btuh, 0),
            "cop": round(self.cop, 2),
            "discharge_temp_uncertainty": round(self.discharge_temp_uncertainty, 1),
            "cop_uncertainty": round(self.cop_uncertainty, 2),
            "fault_active": self.fault_active,
            "hours_simulated": round(self.hours_simulated, 1),
        }


@dataclass
class WhatIfScenario:
    """A what-if simulation request."""
    scenario_id: str = field(default_factory=lambda: f"WIF-{uuid.uuid4().hex[:8].upper()}")
    description: str = ""
    fault_type: Optional[str] = None
    delay_hours: float = 0.0
    ambient_temp_override: Optional[float] = None
    load_fraction_override: Optional[float] = None
    steps: int = 48  # simulation time-steps
    step_hours: float = 1.0


@dataclass
class WhatIfResult:
    """Result of a what-if simulation."""
    scenario_id: str = ""
    description: str = ""
    trajectory: List[SimulationResult] = field(default_factory=list)
    estimated_failure_hour: Optional[float] = None
    final_cop: float = 0.0
    cop_degradation_pct: float = 0.0
    risk_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "description": self.description,
            "n_steps": len(self.trajectory),
            "estimated_failure_hour": self.estimated_failure_hour,
            "final_cop": round(self.final_cop, 2),
            "cop_degradation_pct": round(self.cop_degradation_pct, 1),
            "risk_summary": self.risk_summary,
            "trajectory": [s.to_dict() for s in self.trajectory[-5:]],
        }


# ── Service ──────────────────────────────────────────────────────────

class DigitalTwinSimulator:
    """
    Physics-informed HVAC/R digital twin with degradation overlays.
    """

    def __init__(self, asset_id: str, params: Optional[TwinParameters] = None):
        self.asset_id = asset_id
        self.params = params or TwinParameters()
        self.baseline_params = self.params.copy()

        # Error tracking (simulator residuals)
        self._residuals: Dict[str, deque] = {
            "discharge_temp": deque(maxlen=500),
            "supply_air_temp": deque(maxlen=500),
            "compressor_power": deque(maxlen=500),
            "cop": deque(maxlen=500),
        }

    # ── Real-time simulation ─────────────────────────────────────────

    def simulate_step(
        self,
        params: Optional[TwinParameters] = None,
        fault_type: Optional[str] = None,
        fault_hours: float = 0.0,
        timestamp: Optional[datetime] = None,
    ) -> SimulationResult:
        """
        Run one simulation step using the thermodynamic cycle model.
        """
        p = params or self.params
        now = timestamp or datetime.utcnow()

        # Apply degradation if fault is active
        if fault_type and fault_type in FAULT_DEGRADATION_MODELS:
            p = self._apply_degradation(p.copy(), fault_type, fault_hours)

        # Simplified vapor-compression cycle model
        evap_temp = p.supply_air_setpoint_f - 15.0  # evap coil ΔT
        cond_temp = p.ambient_temp_f + 20.0 * (1.0 / max(p.condenser_ua_fraction, 0.1))

        # Adjust for charge level
        evap_temp -= (1.0 - p.charge_fraction) * 30.0  # low charge → lower evap temp
        cond_temp += (1.0 - p.charge_fraction) * 15.0  # low charge → higher cond temp

        # Compressor model
        suction_temp = evap_temp + p.superheat_delta_f
        pressure_ratio = self._pressure_ratio(evap_temp, cond_temp)
        discharge_temp = self._discharge_temp(
            suction_temp, pressure_ratio, p.isentropic_efficiency,
        )

        # Power and capacity
        capacity = self._cooling_capacity(
            p.return_air_temp_f, p.supply_air_setpoint_f,
            p.evaporator_ua_fraction, p.fan_efficiency,
        )
        power = self._compressor_power(
            capacity, pressure_ratio, p.isentropic_efficiency,
            p.volumetric_efficiency,
        )
        cop = capacity / max(power * 3.412, 1.0)  # BTU/hr per BTU/hr

        # Uncertainty from residual history
        uncertainties = self._compute_uncertainties()

        result = SimulationResult(
            timestamp=now,
            discharge_temp_f=discharge_temp,
            suction_temp_f=suction_temp,
            supply_air_temp_f=p.supply_air_setpoint_f + 2.0 * (1.0 - p.evaporator_ua_fraction),
            condenser_pressure_psig=self._temp_to_pressure(cond_temp),
            evaporator_pressure_psig=self._temp_to_pressure(evap_temp),
            compressor_power_w=power,
            cooling_capacity_btuh=capacity,
            cop=cop,
            discharge_temp_uncertainty=uncertainties.get("discharge_temp", 5.0),
            supply_air_uncertainty=uncertainties.get("supply_air_temp", 2.0),
            power_uncertainty=uncertainties.get("compressor_power", 100.0),
            cop_uncertainty=uncertainties.get("cop", 0.3),
            parameters_used={k: v for k, v in p.__dict__.items()},
            fault_active=fault_type,
            hours_simulated=fault_hours,
        )

        return result

    # ── What-if simulation ───────────────────────────────────────────

    def run_what_if(self, scenario: WhatIfScenario) -> WhatIfResult:
        """
        Run a multi-step what-if scenario.

        Simulates fault progression over time and reports when the system
        would cross critical thresholds.
        """
        trajectory: List[SimulationResult] = []
        params = self.params.copy()

        if scenario.ambient_temp_override is not None:
            params.ambient_temp_f = scenario.ambient_temp_override

        baseline_cop = self.simulate_step(params=params).cop
        failure_hour = None

        for step in range(scenario.steps):
            hours = step * scenario.step_hours

            result = self.simulate_step(
                params=params,
                fault_type=scenario.fault_type,
                fault_hours=hours,
            )
            trajectory.append(result)

            # Check failure threshold: COP < 50% of baseline or discharge > 250°F
            if result.cop < baseline_cop * 0.5 or result.discharge_temp_f > 250:
                if failure_hour is None:
                    failure_hour = hours

        final_cop = trajectory[-1].cop if trajectory else baseline_cop
        degradation_pct = max(0, (1.0 - final_cop / max(baseline_cop, 0.1)) * 100)

        risk = "low"
        if failure_hour is not None:
            if failure_hour < 24:
                risk = "critical"
            elif failure_hour < 72:
                risk = "high"
            elif failure_hour < 168:
                risk = "medium"
        elif degradation_pct > 20:
            risk = "medium"

        return WhatIfResult(
            scenario_id=scenario.scenario_id,
            description=scenario.description or f"What-if: {scenario.fault_type} over {scenario.steps * scenario.step_hours}h",
            trajectory=trajectory,
            estimated_failure_hour=failure_hour,
            final_cop=final_cop,
            cop_degradation_pct=degradation_pct,
            risk_summary=risk,
        )

    # ── Calibration from actual telemetry ────────────────────────────

    def calibrate(
        self,
        actual_discharge_temp: Optional[float] = None,
        actual_supply_air_temp: Optional[float] = None,
        actual_power_w: Optional[float] = None,
        actual_cop: Optional[float] = None,
    ):
        """
        Compare simulation to actual telemetry and update residuals.

        Call this after each telemetry tick to maintain the error model.
        Over time, parameter estimation can use these residuals to
        adjust isentropic efficiency, UA fractions, etc.
        """
        sim = self.simulate_step()

        if actual_discharge_temp is not None:
            self._residuals["discharge_temp"].append(
                actual_discharge_temp - sim.discharge_temp_f
            )
        if actual_supply_air_temp is not None:
            self._residuals["supply_air_temp"].append(
                actual_supply_air_temp - sim.supply_air_temp_f
            )
        if actual_power_w is not None:
            self._residuals["compressor_power"].append(
                actual_power_w - sim.compressor_power_w
            )
        if actual_cop is not None:
            self._residuals["cop"].append(actual_cop - sim.cop)

        # Simple online parameter adjustment (gradient-free)
        self._adjust_parameters()

    def get_error_metrics(self) -> Dict[str, Dict[str, float]]:
        """Return RMSE, bias, and ±2σ for each tracked variable."""
        metrics = {}
        for key, residuals in self._residuals.items():
            if not residuals:
                metrics[key] = {"rmse": 0.0, "bias": 0.0, "sigma_2": 0.0}
                continue
            arr = np.array(residuals)
            metrics[key] = {
                "rmse": float(np.sqrt(np.mean(arr ** 2))),
                "bias": float(np.mean(arr)),
                "sigma_2": float(2.0 * np.std(arr)),
            }
        return metrics

    # ── Internal physics ─────────────────────────────────────────────

    @staticmethod
    def _apply_degradation(
        params: TwinParameters, fault_type: str, hours: float,
    ) -> TwinParameters:
        model = FAULT_DEGRADATION_MODELS.get(fault_type)
        if not model:
            return params

        rate = model["rate_per_hour"]
        accel = model["acceleration"]
        effective_rate = rate * (accel ** hours)
        degradation = min(effective_rate * hours, 0.9)

        for param_name in model["affected_params"]:
            if hasattr(params, param_name):
                current = getattr(params, param_name)
                setattr(params, param_name, current * (1.0 - degradation))

        return params

    @staticmethod
    def _pressure_ratio(evap_temp_f: float, cond_temp_f: float) -> float:
        """Approximate pressure ratio from saturation temperatures (R-410A)."""
        # Simplified Antoine-like approximation for R-410A
        p_evap = 10 ** (3.5 + 0.012 * evap_temp_f)
        p_cond = 10 ** (3.5 + 0.012 * cond_temp_f)
        return max(p_cond / p_evap, 1.0)

    @staticmethod
    def _discharge_temp(
        suction_temp_f: float, pr: float, eta_is: float,
    ) -> float:
        """Estimate discharge temperature from isentropic compression."""
        gamma = 1.15  # effective ratio for R-410A
        t_suction_r = suction_temp_f + 459.67
        t_discharge_r = t_suction_r * (pr ** ((gamma - 1) / gamma))
        t_discharge_ideal = t_discharge_r - 459.67
        return suction_temp_f + (t_discharge_ideal - suction_temp_f) / max(eta_is, 0.1)

    @staticmethod
    def _cooling_capacity(
        return_temp: float, supply_temp: float,
        ua_fraction: float, fan_eff: float,
    ) -> float:
        """Estimate cooling capacity (BTU/hr) from air-side ΔT."""
        dt = max(return_temp - supply_temp, 0) * ua_fraction
        cfm = 400 * fan_eff  # nominal 400 CFM
        return 1.08 * cfm * dt

    @staticmethod
    def _compressor_power(
        capacity_btuh: float, pr: float,
        eta_is: float, eta_vol: float,
    ) -> float:
        """Estimate compressor electrical power (watts)."""
        cop_ideal = 1.0 / (1.0 - 1.0 / max(pr, 1.01))
        cop_actual = cop_ideal * eta_is * eta_vol * 0.9  # motor loss
        return max(capacity_btuh / (cop_actual * 3.412), 50.0)

    @staticmethod
    def _temp_to_pressure(sat_temp_f: float) -> float:
        """Approximate saturation pressure (psig) for R-410A."""
        return max(10 ** (1.8 + 0.013 * sat_temp_f) - 14.7, 0.0)

    def _compute_uncertainties(self) -> Dict[str, float]:
        """Return ±2σ from residual history."""
        result = {}
        for key, residuals in self._residuals.items():
            if len(residuals) > 5:
                result[key] = float(2.0 * np.std(residuals))
            else:
                # Default uncertainties
                defaults = {
                    "discharge_temp": 5.0,
                    "supply_air_temp": 2.0,
                    "compressor_power": 100.0,
                    "cop": 0.3,
                }
                result[key] = defaults.get(key, 1.0)
        return result

    def _adjust_parameters(self):
        """Simple bias-correction of calibratable parameters."""
        # If discharge temp bias is consistently positive, compressor
        # is likely less efficient than modeled → reduce eta
        if len(self._residuals["discharge_temp"]) >= 20:
            bias = float(np.mean(list(self._residuals["discharge_temp"])[-20:]))
            if abs(bias) > 3.0:
                adjustment = 0.001 * np.sign(-bias)
                self.params.isentropic_efficiency = max(
                    0.3,
                    min(0.95, self.params.isentropic_efficiency + adjustment),
                )

        # If COP bias is negative, condenser may be fouled
        if len(self._residuals["cop"]) >= 20:
            cop_bias = float(np.mean(list(self._residuals["cop"])[-20:]))
            if cop_bias < -0.2:
                self.params.condenser_ua_fraction = max(
                    0.1, self.params.condenser_ua_fraction - 0.002,
                )
