"""
Demo Data Generator — Real HVAC BMS Data → PdM Pipeline

Parses the AD2 HVAC dataset (long-format BMS telemetry from 33 retail sites
with Toshiba split-system AC units) and:

1. Pivots point_name/value rows into per-timestamp telemetry dicts
2. Maps BMS signals to PdM TelemetrySnapshot fields
3. Synthesizes missing refrigeration-circuit sensors (pressures, temps,
   compressor current/power) using physics-based correlations
4. Optionally injects fault scenarios (refrigerant leak, condenser fouling,
   sensor drift, compressor degradation) for demo purposes
5. Feeds the stream through HVACRPdMAdvancedSystem and prints results

Usage:
    python -m predictive_maintenance.demo.demo_data_generator \
        --csv AD2_HVAC_Data_set_1.csv \
        --site "test site 1" \
        --scenario refrigerant_leak
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import random
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# BMS → PdM Field Mapping
# =============================================================================

# AC unit Mode values from Toshiba BMS
AC_MODE_OFF = 0
AC_MODE_HEAT = 1
AC_MODE_DRY = 2
AC_MODE_COOL = 3
AC_MODE_FAN = 4


@dataclass
class BMSSnapshot:
    """Raw BMS reading pivoted into a single-timestamp record."""
    site_id: str
    site_name: str
    manufacturer: str
    timestamp: datetime

    # AC unit state
    ac_on_off: int = 0
    ac_mode: int = 0              # 0=off, 1=heat, 2=dry, 3=cool, 4=fan
    ac_fan_speed: int = 0         # 0–5
    ac_setpoint: float = 21.0
    ac_temp_ref: float = 21.0     # actual room temp reported by AC
    ac_vane_position: int = 0
    ac_alarm_status: int = 0
    ac_operation_time: float = 0  # cumulative hours
    ac_device_id: int = 0
    ac_error_code: int = 0

    # Store temperatures (zone sensors at 9 grid positions)
    store_temps: Dict[str, float] = field(default_factory=dict)

    # Controller/AD2 metadata
    controller_status: str = "On-line"
    battery_pct: float = 100.0
    power_status: str = "Mains"


def parse_csv(csv_path: str) -> Dict[str, Dict[str, List[BMSSnapshot]]]:
    """
    Parse the AD2 CSV into {site_id: {timestamp_str: BMSSnapshot}}.
    Returns dict keyed by site_id → list of BMSSnapshot sorted by time.
    """
    # Accumulate raw values: site -> timestamp -> {point_name: value}
    raw: Dict[str, Dict[str, Dict[str, str]]] = defaultdict(lambda: defaultdict(dict))
    site_meta: Dict[str, Tuple[str, str]] = {}  # site_id -> (site_name, manufacturer)

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = row["site_id"]
            ts = row["time"]
            raw[sid][ts][row["point_name"]] = row["value"]
            if sid not in site_meta:
                site_meta[sid] = (row["Site_name"], row["Manufacturer"])

    result: Dict[str, List[BMSSnapshot]] = {}
    for sid, ts_map in raw.items():
        snapshots = []
        site_name, manufacturer = site_meta[sid]
        for ts_str in sorted(ts_map.keys()):
            pts = ts_map[ts_str]
            ts = datetime.strptime(ts_str, "%d/%m/%Y %H:%M")
            snap = BMSSnapshot(
                site_id=sid,
                site_name=site_name,
                manufacturer=manufacturer,
                timestamp=ts,
            )
            # Map point names to fields
            snap.ac_on_off = _int(pts.get("AC unit On-Off", "0"))
            snap.ac_mode = _int(pts.get("AC unit Mode", "0"))
            snap.ac_fan_speed = _int(pts.get("AC Fan Speed", "0"))
            raw_sp = _float(pts.get("AC Real Setpoint", "21"))
            snap.ac_setpoint = raw_sp if raw_sp < 100 else 21.0  # 32768 = unavailable
            raw_ref = _float(pts.get("AC Temp Ref", "21"))
            snap.ac_temp_ref = raw_ref if raw_ref < 100 else 21.0
            snap.ac_vane_position = _int(pts.get("AC Vane Position", "0"))
            snap.ac_alarm_status = _int(pts.get("AC Alarm Status", "0"))
            snap.ac_operation_time = _float(pts.get("AC unit Operation Time", "0"))
            snap.ac_device_id = _int(pts.get("AC Device ID", "0"))

            # Error codes (pick whichever manufacturer code is present)
            for key in ["TOS AC Error Code", "DAI AC Error Code", "FUJ AC Error Code",
                        "HIT AC Error Code", "MHI AC Error Code", "MIT AC Error Code",
                        "PAN AC Error Code", "SAM AC Error Code", "SAN AC Error Code"]:
                if key in pts:
                    snap.ac_error_code = _int(pts[key])
                    break

            # Store temperatures
            for key, val in pts.items():
                if key.startswith("Store Temp"):
                    try:
                        snap.store_temps[key] = float(val)
                    except (ValueError, TypeError):
                        pass

            snap.controller_status = pts.get("Controller Status", "On-line")
            snap.battery_pct = _float(pts.get("AD2 Battery Percentage", "100"))
            snap.power_status = pts.get("AD2 Power Status", "Mains")

            snapshots.append(snap)
        result[sid] = snapshots

    return result


def _int(v: str) -> int:
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


def _float(v: str) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


# =============================================================================
# Physics-Based Sensor Synthesis
# =============================================================================

@dataclass
class SynthesizedTelemetry:
    """Full PdM-compatible telemetry dict synthesized from BMS data."""

    @staticmethod
    def from_bms(
        snap: BMSSnapshot,
        ambient_temp: Optional[float] = None,
        rng: Optional[np.random.Generator] = None,
    ) -> Dict[str, Any]:
        """
        Convert a BMS snapshot to a PdM telemetry dict.

        Synthesizes refrigeration-circuit sensors using thermodynamic
        correlations from the available BMS signals.

        Args:
            snap: Raw BMS snapshot
            ambient_temp: Override ambient temperature
            rng: Persistent numpy RNG for temporally coherent sensor noise.
                 If None, creates one from timestamp (less coherent).
        """
        # AUTO mode (0) engages compressor; FAN mode (4) does not
        compressor_on = snap.ac_on_off == 1 and snap.ac_mode in (AC_MODE_OFF, AC_MODE_COOL, AC_MODE_HEAT, AC_MODE_DRY)
        fan_on = snap.ac_on_off == 1 and snap.ac_fan_speed > 0

        # Determine cooling vs heating (AUTO mode inferred from temps)
        is_cooling = snap.ac_mode == AC_MODE_COOL
        is_heating = snap.ac_mode == AC_MODE_HEAT
        if snap.ac_mode == AC_MODE_OFF and compressor_on:  # AUTO mode
            is_cooling = snap.ac_temp_ref > snap.ac_setpoint
            is_heating = not is_cooling

        # Zone temperature — use average of store temps if available, else AC ref
        zone_temp = snap.ac_temp_ref
        if snap.store_temps:
            zone_temp = np.mean(list(snap.store_temps.values()))

        # Ambient temperature — use store rear-center (closest to outdoor) or estimate
        if ambient_temp is not None:
            amb = ambient_temp
        elif "Store Temp - RC" in snap.store_temps:
            amb = snap.store_temps["Store Temp - RC"] + 3.0  # outdoor is warmer
        else:
            amb = zone_temp + 5.0  # rough outdoor estimate

        setpoint = _c_to_f(snap.ac_setpoint)

        # Convert to Fahrenheit — PdM pipeline expects °F
        zone_temp = _c_to_f(zone_temp)
        amb = _c_to_f(amb)
        delta_t = zone_temp - setpoint  # positive = zone warmer than setpoint

        # --- Synthesize refrigeration-circuit sensors ---
        if rng is None:
            rng = np.random.default_rng(int(snap.timestamp.timestamp()) % 2**31)

        if compressor_on and is_cooling:
            # R410A typical operating conditions for split system cooling
            # Suction pressure ~100-130 psi, Discharge pressure ~350-450 psi
            load_factor = min(1.0, max(0.2, abs(delta_t) / 9.0))  # 9°F ≈ 5°C

            suction_pressure = 115 + load_factor * 10 + rng.normal(0, 1.5)
            discharge_pressure = 370 + (amb - 70) * 1.5 + load_factor * 30 + rng.normal(0, 3)

            # Temperatures derived from pressures (°F saturation curve)
            suction_sat = _r410a_sat_temp(suction_pressure)
            discharge_sat = _r410a_sat_temp(discharge_pressure)
            superheat = 8.0 + rng.normal(0, 0.8)  # ~8°F superheat
            subcool = 8.0 + rng.normal(0, 0.8)    # ~8°F subcool
            suction_temp = suction_sat + superheat
            discharge_temp = discharge_sat + 25.0 + rng.normal(0, 1.5)
            liquid_line_temp = discharge_sat - subcool
            supply_air_temp = zone_temp - (5.0 + load_factor * 12.0) + rng.normal(0, 0.5)
            return_air_temp = zone_temp + rng.normal(0, 0.4)

            # Compressor electrical
            nominal_current = 8.0 + load_factor * 4.0  # 8-12 amps typical
            compressor_current = nominal_current + rng.normal(0, 0.3)
            compressor_power = compressor_current * 230 * 0.85 / 1000  # kW (single-phase)

        elif compressor_on and is_heating:
            load_factor = min(1.0, max(0.2, abs(delta_t) / 9.0))

            suction_pressure = 70 + (amb - 32) * 0.8 + rng.normal(0, 1.5)
            discharge_pressure = 380 + load_factor * 40 + rng.normal(0, 3)

            suction_sat = _r410a_sat_temp(max(30, suction_pressure))
            discharge_sat = _r410a_sat_temp(discharge_pressure)
            superheat = 8.0 + rng.normal(0, 0.8)
            subcool = 8.0 + rng.normal(0, 0.8)
            suction_temp = suction_sat + superheat
            discharge_temp = discharge_sat + 30.0 + rng.normal(0, 1.5)
            liquid_line_temp = discharge_sat - subcool
            supply_air_temp = zone_temp + (9.0 + load_factor * 18.0) + rng.normal(0, 0.5)
            return_air_temp = zone_temp + rng.normal(0, 0.4)

            nominal_current = 9.0 + load_factor * 5.0
            compressor_current = nominal_current + rng.normal(0, 0.3)
            compressor_power = compressor_current * 230 * 0.85 / 1000

        else:
            # Off or fan-only
            suction_pressure = None
            discharge_pressure = None
            suction_temp = amb + rng.normal(0, 0.8) if fan_on else None
            discharge_temp = None
            liquid_line_temp = None
            supply_air_temp = zone_temp + rng.normal(0, 0.5) if fan_on else None
            return_air_temp = zone_temp + rng.normal(0, 0.4) if fan_on else None
            compressor_current = None
            compressor_power = None

        # Fan speed normalization (0-5 → 0-100%)
        fan_speed_pct = (snap.ac_fan_speed / 5.0) * 100.0 if snap.ac_fan_speed > 0 else 0.0

        telemetry = {
            "timestamp": snap.timestamp,
            "asset_id": f"{snap.site_id}_AC{snap.ac_device_id}",
            "site_id": snap.site_id,

            # State
            "compressor_on": compressor_on,
            "evap_fan_on": fan_on,
            "condenser_fan_on": compressor_on,
            "supply_fan_speed": fan_speed_pct,

            # Temperatures (°F)
            "suction_line_temp": suction_temp,
            "discharge_temp": discharge_temp,
            "liquid_line_temp": liquid_line_temp,
            "supply_air_temp": supply_air_temp,
            "return_air_temp": return_air_temp,
            "ambient_temp": amb,
            "zone_temp": zone_temp,
            "setpoint": setpoint,

            # Pressures (psi)
            "suction_pressure": suction_pressure,
            "discharge_pressure": discharge_pressure,

            # Derived
            "superheat": superheat if compressor_on else None,
            "subcool": subcool if compressor_on else None,

            # Electrical
            "compressor_current": compressor_current,
            "compressor_power": compressor_power,

            # Metadata from BMS
            "ac_mode": snap.ac_mode,
            "ac_alarm_status": snap.ac_alarm_status,
            "ac_error_code": snap.ac_error_code,
            "ac_operation_time_hours": snap.ac_operation_time,
            "controller_status": snap.controller_status,
            "battery_pct": snap.battery_pct,
            "power_status": snap.power_status,
            "store_temps": snap.store_temps,
        }
        return telemetry


def _c_to_f(celsius: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return celsius * 9.0 / 5.0 + 32.0


def _r410a_sat_temp(pressure_psi: float) -> float:
    """Simplified R-410A saturation temperature (°F) from pressure (psi).

    Uses a power-law approximation of the saturation curve.
    Accurate to ±3°F across 50-500 psi operating range.
    """
    if pressure_psi <= 0:
        return -4.0  # -20°C in °F
    # Power-law fit to R-410A saturation data
    # T_sat(°F) ≈ 0.588 * P^0.845
    return 0.588 * max(pressure_psi, 10) ** 0.845


# =============================================================================
# Fault Injection Scenarios
# =============================================================================

@dataclass
class FaultScenario:
    """Defines a fault injection scenario for demo purposes."""
    name: str
    description: str
    onset_fraction: float = 0.4   # fraction through data where fault begins
    ramp_duration_fraction: float = 0.3  # how long the ramp takes

    def apply(self, telemetry: Dict[str, Any], progress: float) -> Dict[str, Any]:
        """Apply fault effects. progress=0 at onset, 1.0 at full severity."""
        return telemetry


class RefrigerantLeakScenario(FaultScenario):
    """Gradual refrigerant leak — suction pressure drops, superheat rises,
    discharge temp rises, compressor current increases."""

    def __init__(self):
        super().__init__(
            name="refrigerant_leak",
            description="Gradual R-410A refrigerant leak over ~40% of data window",
            onset_fraction=0.3,
            ramp_duration_fraction=0.4,
        )

    def apply(self, telemetry: Dict[str, Any], progress: float) -> Dict[str, Any]:
        t = telemetry.copy()
        severity = min(1.0, progress)

        if t.get("suction_pressure") is not None:
            t["suction_pressure"] -= severity * 35  # drops up to 35 psi
        if t.get("discharge_temp") is not None:
            t["discharge_temp"] += severity * 25  # rises up to 25°F
        if t.get("suction_line_temp") is not None:
            t["suction_line_temp"] += severity * 15  # superheat increases 15°F
        if t.get("superheat") is not None:
            t["superheat"] += severity * 15  # direct superheat field
        if t.get("subcool") is not None:
            t["subcool"] -= severity * 6  # subcool drops
        if t.get("compressor_current") is not None:
            t["compressor_current"] *= (1 + severity * 0.20)  # current rises ~20%
        if t.get("supply_air_temp") is not None:
            t["supply_air_temp"] += severity * 5  # less cooling capacity
        return t


class CondenserFoulingScenario(FaultScenario):
    """Dirty condenser — discharge pressure and temp rise, efficiency drops."""

    def __init__(self):
        super().__init__(
            name="condenser_fouling",
            description="Progressive condenser fouling (dust/debris buildup)",
        )

    def apply(self, telemetry: Dict[str, Any], progress: float) -> Dict[str, Any]:
        t = telemetry.copy()
        severity = min(1.0, progress)

        if t.get("discharge_pressure") is not None:
            t["discharge_pressure"] += severity * 40  # rises up to 40 psi
        if t.get("discharge_temp") is not None:
            t["discharge_temp"] += severity * 15
        if t.get("compressor_current") is not None:
            t["compressor_current"] *= (1 + severity * 0.2)
        if t.get("compressor_power") is not None:
            t["compressor_power"] *= (1 + severity * 0.2)
        if t.get("liquid_line_temp") is not None:
            t["liquid_line_temp"] += severity * 8  # subcool decreases
        return t


class SensorDriftScenario(FaultScenario):
    """Gradual drift in return-air temperature sensor — reads progressively
    lower, causing overcooling and trust score degradation."""

    def __init__(self):
        super().__init__(
            name="sensor_drift",
            description="Return-air temp sensor drifting low (calibration loss)",
            onset_fraction=0.3,
        )

    def apply(self, telemetry: Dict[str, Any], progress: float) -> Dict[str, Any]:
        t = telemetry.copy()
        severity = min(1.0, progress)

        if t.get("return_air_temp") is not None:
            t["return_air_temp"] -= severity * 7.0  # drifts down 7°F
        return t


class CompressorDegradationScenario(FaultScenario):
    """Compressor valve wear — reduced efficiency, higher current draw,
    lower suction pressure, higher discharge temp."""

    def __init__(self):
        super().__init__(
            name="compressor_degradation",
            description="Compressor valve wear causing efficiency loss",
            onset_fraction=0.35,
            ramp_duration_fraction=0.4,
        )

    def apply(self, telemetry: Dict[str, Any], progress: float) -> Dict[str, Any]:
        t = telemetry.copy()
        severity = min(1.0, progress)

        if t.get("suction_pressure") is not None:
            t["suction_pressure"] -= severity * 15
        if t.get("discharge_pressure") is not None:
            t["discharge_pressure"] -= severity * 20  # can't build pressure
        if t.get("discharge_temp") is not None:
            t["discharge_temp"] += severity * 18  # mechanical heat
        if t.get("compressor_current") is not None:
            t["compressor_current"] *= (1 + severity * 0.25)
        if t.get("compressor_power") is not None:
            t["compressor_power"] *= (1 + severity * 0.25)
        return t


SCENARIOS: Dict[str, FaultScenario] = {
    "refrigerant_leak": RefrigerantLeakScenario(),
    "condenser_fouling": CondenserFoulingScenario(),
    "sensor_drift": SensorDriftScenario(),
    "compressor_degradation": CompressorDegradationScenario(),
}


# =============================================================================
# Interpolation — upsample sparse BMS to high-frequency telemetry
# =============================================================================

def interpolate_snapshots(
    snapshots: List[BMSSnapshot],
    interval_minutes: int = 5,
) -> List[BMSSnapshot]:
    """
    Linearly interpolate between sparse BMS snapshots (~3 hr apart) to
    produce realistic high-frequency data (default: every 5 min).

    Numeric fields are linearly interpolated; categorical/boolean fields
    hold the value of the preceding real snapshot.
    """
    if len(snapshots) < 2:
        return list(snapshots)

    result: List[BMSSnapshot] = []
    interval = timedelta(minutes=interval_minutes)

    for idx in range(len(snapshots) - 1):
        s0 = snapshots[idx]
        s1 = snapshots[idx + 1]
        gap = (s1.timestamp - s0.timestamp).total_seconds()
        n_steps = max(1, int(gap / interval.total_seconds()))

        for step in range(n_steps):
            frac = step / n_steps
            ts = s0.timestamp + timedelta(seconds=gap * frac)

            snap = BMSSnapshot(
                site_id=s0.site_id,
                site_name=s0.site_name,
                manufacturer=s0.manufacturer,
                timestamp=ts,
                # Categorical — hold from s0
                ac_on_off=s0.ac_on_off,
                ac_mode=s0.ac_mode,
                ac_alarm_status=s0.ac_alarm_status,
                ac_device_id=s0.ac_device_id,
                ac_error_code=s0.ac_error_code,
                ac_vane_position=s0.ac_vane_position,
                controller_status=s0.controller_status,
                power_status=s0.power_status,
                # Numeric — lerp
                ac_fan_speed=int(round(s0.ac_fan_speed + frac * (s1.ac_fan_speed - s0.ac_fan_speed))),
                ac_setpoint=s0.ac_setpoint + frac * (s1.ac_setpoint - s0.ac_setpoint),
                ac_temp_ref=s0.ac_temp_ref + frac * (s1.ac_temp_ref - s0.ac_temp_ref),
                ac_operation_time=s0.ac_operation_time + frac * (s1.ac_operation_time - s0.ac_operation_time),
                battery_pct=s0.battery_pct + frac * (s1.battery_pct - s0.battery_pct),
            )
            # Interpolate store temps
            common_keys = set(s0.store_temps.keys()) & set(s1.store_temps.keys())
            for k in common_keys:
                snap.store_temps[k] = s0.store_temps[k] + frac * (s1.store_temps[k] - s0.store_temps[k])
            # Keep keys only in s0
            for k in set(s0.store_temps.keys()) - common_keys:
                snap.store_temps[k] = s0.store_temps[k]

            result.append(snap)

    # Append final snapshot
    result.append(snapshots[-1])
    return result


# =============================================================================
# Demo Runner
# =============================================================================

def build_demo_stream(
    csv_path: str,
    site_id: str = "test site 17",
    scenario: Optional[str] = None,
    max_snapshots: Optional[int] = None,
    interpolate: bool = True,
    interval_minutes: int = 15,
) -> List[Dict[str, Any]]:
    """
    Build a stream of PdM telemetry dicts from the CSV.

    Args:
        csv_path: Path to AD2_HVAC_Data_set_1.csv
        site_id: Which site to extract (default: "test site 17" — 73% explicit COOL mode)
        scenario: Optional fault scenario to inject
        max_snapshots: Limit number of snapshots (None = all)
        interpolate: Upsample sparse BMS data to high-frequency telemetry
        interval_minutes: Interpolation interval in minutes (default: 15)

    Returns:
        List of telemetry dicts ready for HVACRPdMAdvancedSystem.process_telemetry()
    """
    all_sites = parse_csv(csv_path)
    if site_id not in all_sites:
        available = sorted(all_sites.keys())
        raise ValueError(f"Site '{site_id}' not found. Available: {available}")

    snapshots = all_sites[site_id]

    if interpolate and len(snapshots) >= 2:
        snapshots = interpolate_snapshots(snapshots, interval_minutes)
        logger.info(f"Interpolated to {len(snapshots)} snapshots at {interval_minutes}-min intervals")

    if max_snapshots:
        snapshots = snapshots[:max_snapshots]

    fault = SCENARIOS.get(scenario) if scenario else None
    n = len(snapshots)

    # Persistent RNG for temporally coherent sensor noise across the stream
    stream_rng = np.random.default_rng(42)

    stream = []
    for i, snap in enumerate(snapshots):
        telemetry = SynthesizedTelemetry.from_bms(snap, rng=stream_rng)

        # Inject fault if applicable
        if fault and i >= int(fault.onset_fraction * n):
            onset_idx = int(fault.onset_fraction * n)
            ramp_len = max(1, int(fault.ramp_duration_fraction * n))
            progress = min(1.0, (i - onset_idx) / ramp_len)
            telemetry = fault.apply(telemetry, progress)

        stream.append(telemetry)

    logger.info(
        f"Built {len(stream)} telemetry snapshots for site '{site_id}'"
        + (f" with fault scenario '{scenario}'" if scenario else "")
    )
    return stream


def run_demo(
    csv_path: str,
    site_id: str = "test site 17",
    scenario: Optional[str] = None,
    max_snapshots: Optional[int] = None,
    verbose: bool = True,
    interpolate: bool = True,
    interval_minutes: int = 15,
) -> Dict[str, Any]:
    """
    Run the full demo: parse CSV → synthesize → inject faults → run PdM pipeline.

    Returns a summary dict with results.
    """
    from predictive_maintenance.integration.advanced_system import HVACRPdMAdvancedSystem

    stream = build_demo_stream(
        csv_path, site_id, scenario, max_snapshots,
        interpolate=interpolate, interval_minutes=interval_minutes,
    )
    if not stream:
        print("No data found.")
        return {}

    asset_id = stream[0]["asset_id"]
    pdm = HVACRPdMAdvancedSystem(
        asset_id=asset_id,
        site_id=site_id,
    )

    results = {
        "site_id": site_id,
        "asset_id": asset_id,
        "scenario": scenario,
        "n_snapshots": len(stream),
        "alerts": [],
        "regime_history": [],
        "timeline": [],
    }

    for i, telemetry in enumerate(stream):
        alert = pdm.process_telemetry(telemetry)
        ts = telemetry["timestamp"]
        regime = pdm.current_regime

        entry = {
            "step": i,
            "timestamp": ts.isoformat(),
            "regime": regime.value if hasattr(regime, "value") else str(regime),
            "alert_type": alert.alert_type.value if alert and hasattr(alert.alert_type, "value") else None,
            "compressor_on": telemetry.get("compressor_on", False),
            "zone_temp": telemetry.get("zone_temp"),
            "ambient_temp": telemetry.get("ambient_temp"),
            # Key telemetry for fault impact visibility
            "suction_pressure": round(telemetry["suction_pressure"], 1) if telemetry.get("suction_pressure") is not None else None,
            "discharge_pressure": round(telemetry["discharge_pressure"], 1) if telemetry.get("discharge_pressure") is not None else None,
            "suction_line_temp": round(telemetry["suction_line_temp"], 1) if telemetry.get("suction_line_temp") is not None else None,
            "supply_air_temp": round(telemetry["supply_air_temp"], 1) if telemetry.get("supply_air_temp") is not None else None,
            "superheat": round(telemetry["superheat"], 1) if telemetry.get("superheat") is not None else None,
            "subcool": round(telemetry["subcool"], 1) if telemetry.get("subcool") is not None else None,
            "compressor_current": round(telemetry["compressor_current"], 2) if telemetry.get("compressor_current") is not None else None,
        }

        # Include health/RUL if available
        if pdm.current_health:
            entry["health_score"] = round(pdm.current_health.health_score, 3)
        if pdm.current_rul:
            entry["rul_hours"] = round(pdm.current_rul.rul_hours, 1)

        # Sensor trust summary
        if pdm.current_trust_scores:
            min_trust = min(t.trust_score for t in pdm.current_trust_scores.values())
            entry["min_sensor_trust"] = round(min_trust, 3)

        # Change detection summary
        n_changes = sum(
            1 for d in pdm.current_changes.values()
            if getattr(d, "change_detected", False)
        )
        entry["n_active_changes"] = n_changes

        # Fault hypothesis
        if hasattr(pdm, "fault_hypothesis"):
            h = pdm.fault_hypothesis.current_hypothesis
            if h and h.most_likely_fault:
                entry["top_fault"] = h.most_likely_fault.value if hasattr(h.most_likely_fault, "value") else str(h.most_likely_fault)
                entry["top_fault_prob"] = round(h.posteriors.get(h.most_likely_fault, 0.0), 3)

        results["timeline"].append(entry)

        if alert and alert.alert_type.value != "watch":
            results["alerts"].append({
                "step": i,
                "timestamp": ts.isoformat(),
                "alert_type": alert.alert_type.value,
                "severity": getattr(alert, "severity", None),
            })

        # Print every Nth step, scaling with total snapshots
        print_every = max(1, len(stream) // 40)
        if verbose and i % print_every == 0:
            _print_step(entry, scenario)

    # Print summary
    if verbose:
        _print_summary(results, pdm)

    return results


def _print_step(entry: Dict[str, Any], scenario: Optional[str] = None):
    """Print a single pipeline step."""
    ts = entry["timestamp"][:16]
    regime = entry.get("regime", "?")
    alert = entry.get("alert_type", "ok")
    zone = entry.get("zone_temp")
    amb = entry.get("ambient_temp")
    health = entry.get("health_score", "—")
    rul = entry.get("rul_hours", "—")
    trust = entry.get("min_sensor_trust", "—")
    changes = entry.get("n_active_changes", 0)
    comp = "ON " if entry.get("compressor_on") else "OFF"
    fault = entry.get("top_fault", "—")

    zone_str = f"{zone:.1f}°F" if zone else "—"
    amb_str = f"{amb:.1f}°F" if amb else "—"

    print(
        f"  [{entry['step']:3d}] {ts}  {comp}  regime={regime:<14s}  "
        f"zone={zone_str:>7s}  amb={amb_str:>7s}  "
        f"health={health!s:>5s}  rul={rul!s:>6s}h  "
        f"trust={trust!s:>5s}  Δ={changes}  "
        f"fault={fault:<20s}  alert={alert}"
    )


def _print_summary(results: Dict[str, Any], pdm):
    """Print demo summary."""
    print("\n" + "=" * 90)
    print("DEMO SUMMARY")
    print("=" * 90)
    print(f"  Site:      {results['site_id']}")
    print(f"  Asset:     {results['asset_id']}")
    print(f"  Scenario:  {results['scenario'] or 'baseline (no fault injected)'}")
    print(f"  Snapshots: {results['n_snapshots']}")
    print(f"  Duration:  {pdm.hours_of_operation:.1f} hours of operation")
    print(f"  Alerts:    {len(results['alerts'])}")

    if results["alerts"]:
        print("\n  Alert History:")
        for a in results["alerts"]:
            print(f"    [{a['step']:3d}] {a['timestamp'][:16]}  {a['alert_type']}  severity={a.get('severity', '?')}")

    # Regime distribution
    regimes = defaultdict(int)
    for e in results["timeline"]:
        regimes[e.get("regime", "unknown")] += 1
    print("\n  Regime Distribution:")
    for r, count in sorted(regimes.items(), key=lambda x: -x[1]):
        pct = count / len(results["timeline"]) * 100
        print(f"    {r:<18s}  {count:4d} ({pct:5.1f}%)")

    # Final health
    last = results["timeline"][-1] if results["timeline"] else {}
    print(f"\n  Final State:")
    print(f"    Health Score:      {last.get('health_score', '—')}")
    print(f"    RUL:               {last.get('rul_hours', '—')} hours")
    print(f"    Min Sensor Trust:  {last.get('min_sensor_trust', '—')}")
    print(f"    Active Changes:    {last.get('n_active_changes', 0)}")
    print(f"    Top Fault:         {last.get('top_fault', '—')}")
    print(f"    Top Fault Prob:    {last.get('top_fault_prob', '—')}")

    # Telemetry impact analysis (for fault scenarios)
    tl = results["timeline"]
    if results.get("scenario") and len(tl) > 20:
        n = len(tl)
        # Compare first 20% (pre-fault) vs last 20% (full fault)
        early = [e for e in tl[:n // 5] if e.get("compressor_on")]
        late = [e for e in tl[4 * n // 5:] if e.get("compressor_on")]
        if early and late:
            print("\n  Telemetry Impact (compressor-on averages):")
            print(f"    {'Metric':<22s}  {'Pre-fault':>10s}  {'Post-fault':>10s}  {'Change':>10s}")
            print(f"    {'-'*22}  {'-'*10}  {'-'*10}  {'-'*10}")
            for key, unit in [
                ("suction_pressure", "psi"),
                ("suction_line_temp", "°F"),
                ("supply_air_temp", "°F"),
                ("superheat", "°F"),
                ("subcool", "°F"),
                ("compressor_current", "A"),
            ]:
                early_vals = [e[key] for e in early if e.get(key) is not None]
                late_vals = [e[key] for e in late if e.get(key) is not None]
                if early_vals and late_vals:
                    e_avg = sum(early_vals) / len(early_vals)
                    l_avg = sum(late_vals) / len(late_vals)
                    delta = l_avg - e_avg
                    sign = "+" if delta >= 0 else ""
                    print(f"    {key:<22s}  {e_avg:>8.1f}{unit:>2s}  {l_avg:>8.1f}{unit:>2s}  {sign}{delta:>7.1f}{unit:>2s}")

    print("=" * 90)


def export_to_json(results: Dict[str, Any], output_path: str):
    """Export demo results to JSON for frontend consumption."""
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Results exported to {output_path}")


def list_sites(csv_path: str):
    """List available sites in the CSV."""
    sites = set()
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sites.add(row["site_id"])
    for s in sorted(sites):
        print(f"  {s}")


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Demo Data Generator — Real HVAC BMS → PdM Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Fault Scenarios:
  refrigerant_leak        Gradual R-410A leak (↓suction pressure, ↑superheat)
  condenser_fouling       Dirty condenser (↑discharge pressure/temp)
  sensor_drift            Return-air temp sensor drifting low
  compressor_degradation  Compressor valve wear (↑current, ↓efficiency)

Examples:
  # Baseline run (no fault)
  python -m predictive_maintenance.demo.demo_data_generator --csv AD2_HVAC_Data_set_1.csv

  # With fault injection
  python -m predictive_maintenance.demo.demo_data_generator --csv AD2_HVAC_Data_set_1.csv --scenario refrigerant_leak

  # List available sites
  python -m predictive_maintenance.demo.demo_data_generator --csv AD2_HVAC_Data_set_1.csv --list-sites
""",
    )
    parser.add_argument("--csv", required=True, help="Path to AD2_HVAC_Data_set_1.csv")
    parser.add_argument("--site", default="test site 17", help="Site ID to process (default: site 17, 73%% explicit COOL mode)")
    parser.add_argument("--scenario", choices=list(SCENARIOS.keys()), help="Fault scenario to inject")
    parser.add_argument("--max-snapshots", type=int, help="Limit number of snapshots")
    parser.add_argument("--no-interpolate", action="store_true", help="Disable interpolation (use raw BMS timestamps only)")
    parser.add_argument("--interval", type=int, default=15, help="Interpolation interval in minutes (default: 15)")
    parser.add_argument("--output", help="Export results to JSON file")
    parser.add_argument("--list-sites", action="store_true", help="List available sites and exit")
    parser.add_argument("--quiet", action="store_true", help="Suppress step-by-step output")
    parser.add_argument("--log-level", default="WARNING", help="Logging level")

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(levelname)-8s %(name)s: %(message)s",
    )

    if args.list_sites:
        print("Available sites:")
        list_sites(args.csv)
        return

    scenario_desc = SCENARIOS[args.scenario].description if args.scenario else "baseline (no fault)"
    print(f"\n{'=' * 90}")
    print(f"PdM Demo — Real HVAC Data → Predictive Maintenance Pipeline")
    print(f"{'=' * 90}")
    print(f"  CSV:       {args.csv}")
    print(f"  Site:      {args.site}")
    print(f"  Scenario:  {scenario_desc}")
    print(f"{'=' * 90}\n")

    results = run_demo(
        csv_path=args.csv,
        site_id=args.site,
        scenario=args.scenario,
        max_snapshots=args.max_snapshots,
        verbose=not args.quiet,
        interpolate=not args.no_interpolate,
        interval_minutes=args.interval,
    )

    if args.output:
        export_to_json(results, args.output)


if __name__ == "__main__":
    main()
