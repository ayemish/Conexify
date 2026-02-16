"""
Populate Persistence Layer — Load real HVAC BMS data into PostgreSQL.

Uses the AD2 HVAC dataset + demo_data_generator synthesis to populate:
- Assets (33 sites × 1 AC unit each)
- Telemetry (interpolated + synthesized refrigeration-circuit sensors)
- Alerts (generated from fault-injected scenarios on select assets)
- Fingerprints (learned baselines per asset)
- Regime segments (operating mode history)
- Audit log entries
- KPI pipeline run + results (from KPIOrchestrator)

Usage:
    python -m predictive_maintenance.demo.populate_persistence \
        --csv AD2_HVAC_Data_set_1.csv
"""

from __future__ import annotations

import argparse
import logging
import math
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Fault scenarios to inject on select sites for realistic alert data
FAULT_ASSIGNMENTS = {
    "test site 3": "refrigerant_leak",
    "test site 7": "condenser_fouling",
    "test site 12": "sensor_drift",
    "test site 19": "compressor_degradation",
    "test site 25": "refrigerant_leak",
    "test site 30": "condenser_fouling",
}

# Site metadata for location enrichment
SITE_ADDRESSES = {
    "test site 1": "101 Main St, Springfield, IL",
    "test site 2": "202 Oak Ave, Decatur, IL",
    "test site 3": "303 Pine Rd, Champaign, IL",
    "test site 4": "404 Elm Blvd, Peoria, IL",
    "test site 5": "505 Cedar Ln, Bloomington, IL",
    "test site 6": "606 Maple Dr, Normal, IL",
    "test site 7": "707 Birch St, Urbana, IL",
    "test site 8": "808 Ash Ave, Danville, IL",
    "test site 9": "909 Walnut Rd, Mattoon, IL",
    "test site 10": "1010 Cherry Ct, Effingham, IL",
    "test site 11": "1111 Hickory Ln, Centralia, IL",
    "test site 12": "1212 Poplar Way, Marion, IL",
    "test site 13": "1313 Willow Dr, Carbondale, IL",
    "test site 14": "1414 Sycamore St, Quincy, IL",
    "test site 15": "1515 Magnolia Ave, Jacksonville, IL",
    "test site 16": "1616 Dogwood Rd, Galesburg, IL",
    "test site 17": "1717 Redwood Blvd, Macomb, IL",
    "test site 18": "1818 Cypress Ct, Rantoul, IL",
    "test site 19": "1919 Juniper Ln, Charleston, IL",
    "test site 20": "2020 Spruce Dr, Taylorville, IL",
    "test site 21": "2121 Fir St, Lincoln, IL",
    "test site 22": "2222 Palm Ave, Litchfield, IL",
    "test site 23": "2323 Olive Rd, Vandalia, IL",
    "test site 24": "2424 Aspen Way, Salem, IL",
    "test site 25": "2525 Beech Ct, Mt Vernon, IL",
    "test site 26": "2626 Linden Ln, Olney, IL",
    "test site 27": "2727 Hazel Dr, Robinson, IL",
    "test site 28": "2828 Alder St, Paris, IL",
    "test site 29": "2929 Ivy Blvd, Tuscola, IL",
    "test site 30": "3030 Holly Ave, Shelbyville, IL",
    "test site 31": "3131 Laurel Rd, Sullivan, IL",
    "test site 32": "3232 Sage Ct, Arcola, IL",
    "test site 33": "3333 Thyme Ln, Arthur, IL",
}


def populate_all(
    csv_path: str,
    db_url: Optional[str] = None,
    max_sites: int = 33,
    interpolate: bool = True,
    interval_minutes: int = 15,
    run_kpi: bool = True,
):
    """
    Main entry point: parse CSV, synthesize telemetry, persist everything.
    """
    from predictive_maintenance.demo.demo_data_generator import (
        parse_csv,
        interpolate_snapshots,
        SynthesizedTelemetry,
        SCENARIOS,
    )
    from predictive_maintenance.persistence.database import get_engine, Base, get_session
    from predictive_maintenance.persistence.models import (
        AssetModel,
        TelemetryModel,
        AlertModel,
        FingerprintModel,
        RegimeSegmentModel,
        AuditLogModel,
    )

    # ── 1. Initialize database ─────────────────────────────────────
    print("=" * 80)
    print("PERSISTENCE LAYER POPULATION")
    print("=" * 80)

    engine = get_engine()
    print(f"  Database: {engine.url}")
    print(f"  CSV:      {csv_path}")

    # Create tables if they don't exist
    Base.metadata.create_all(engine)
    print("  Tables:   created/verified")

    # ── 2. Parse CSV ───────────────────────────────────────────────
    print("\n[1/6] Parsing CSV...")
    all_sites = parse_csv(csv_path)
    site_ids = sorted(all_sites.keys())[:max_sites]
    print(f"  Found {len(all_sites)} sites, processing {len(site_ids)}")

    # ── 3. Process each site ───────────────────────────────────────
    total_assets = 0
    total_telemetry = 0
    total_alerts = 0
    total_fingerprints = 0
    total_segments = 0

    for site_idx, site_id in enumerate(site_ids):
        snapshots = all_sites[site_id]
        if len(snapshots) < 3:
            print(f"  Skipping {site_id} (only {len(snapshots)} snapshots)")
            continue

        scenario_name = FAULT_ASSIGNMENTS.get(site_id)
        fault = SCENARIOS.get(scenario_name) if scenario_name else None

        # Interpolate to higher frequency
        if interpolate and len(snapshots) >= 2:
            snapshots = interpolate_snapshots(snapshots, interval_minutes)

        # Synthesize telemetry
        stream_rng = np.random.default_rng(hash(site_id) % 2**31)
        n = len(snapshots)
        telemetry_dicts = []
        for i, snap in enumerate(snapshots):
            t = SynthesizedTelemetry.from_bms(snap, rng=stream_rng)
            if fault and i >= int(fault.onset_fraction * n):
                onset_idx = int(fault.onset_fraction * n)
                ramp_len = max(1, int(fault.ramp_duration_fraction * n))
                progress = min(1.0, (i - onset_idx) / ramp_len)
                t = fault.apply(t, progress)
            telemetry_dicts.append(t)

        if not telemetry_dicts:
            continue

        asset_id = telemetry_dicts[0]["asset_id"]

        # ── Persist to database ────────────────────────────────────
        with get_session() as session:
            # Check if asset already exists
            existing = session.query(AssetModel).filter(
                AssetModel.asset_id == asset_id
            ).first()

            if not existing:
                # Create asset
                asset = AssetModel(
                    asset_id=asset_id,
                    site_id=site_id,
                    asset_type="hvac_split_system",
                    manufacturer="Toshiba",
                    model_number=f"RAV-SM{random.choice([804, 1104, 1404])}AT-E",
                    serial_number=f"TSB{random.randint(100000, 999999)}",
                    install_date=datetime(2023, random.randint(1, 12), random.randint(1, 28)),
                    refrigerant_type="R-410A",
                    nominal_capacity_tons=random.choice([2.0, 3.0, 4.0, 5.0]),
                    nominal_voltage=230.0,
                    is_active=True,
                    last_telemetry_at=telemetry_dicts[-1]["timestamp"],
                )
                session.add(asset)
                session.flush()
                total_assets += 1
            else:
                # Update last_telemetry_at
                existing.last_telemetry_at = telemetry_dicts[-1]["timestamp"]

            # Bulk insert telemetry
            telem_records = []
            regime_segments = []
            current_regime = None
            regime_start = None

            for t in telemetry_dicts:
                # Determine regime
                regime = _classify_regime(t)

                # Track regime segments
                if regime != current_regime:
                    if current_regime is not None and regime_start is not None:
                        regime_segments.append({
                            "asset_id": asset_id,
                            "regime": current_regime,
                            "start_time": regime_start,
                            "end_time": t["timestamp"],
                            "duration_minutes": (t["timestamp"] - regime_start).total_seconds() / 60,
                            "n_readings": sum(1 for r in telem_records if r.get("regime") == current_regime),
                        })
                    current_regime = regime
                    regime_start = t["timestamp"]

                telem_records.append({
                    "asset_id": asset_id,
                    "timestamp": t["timestamp"],
                    "compressor_on": t.get("compressor_on"),
                    "compressor_current": _round_or_none(t.get("compressor_current"), 2),
                    "compressor_power": _round_or_none(t.get("compressor_power"), 3),
                    "evap_fan_on": t.get("evap_fan_on"),
                    "condenser_fan_on": t.get("condenser_fan_on"),
                    "supply_fan_speed": _round_or_none(t.get("supply_fan_speed"), 1),
                    "suction_temp": _round_or_none(t.get("suction_line_temp"), 1),
                    "discharge_temp": _round_or_none(t.get("discharge_temp"), 1),
                    "supply_air_temp": _round_or_none(t.get("supply_air_temp"), 1),
                    "return_air_temp": _round_or_none(t.get("return_air_temp"), 1),
                    "ambient_temp": _round_or_none(t.get("ambient_temp"), 1),
                    "zone_temp": _round_or_none(t.get("zone_temp"), 1),
                    "suction_pressure": _round_or_none(t.get("suction_pressure"), 1),
                    "discharge_pressure": _round_or_none(t.get("discharge_pressure"), 1),
                    "superheat": _round_or_none(t.get("superheat"), 1),
                    "subcool": _round_or_none(t.get("subcool"), 1),
                    "setpoint": _round_or_none(t.get("setpoint"), 1),
                    "regime": regime,
                    "regime_confidence": 0.9 + random.uniform(0, 0.1),
                    "data_quality_score": 0.95 + random.uniform(0, 0.05),
                    "extra_data": {
                        "ac_mode": t.get("ac_mode"),
                        "ac_alarm_status": t.get("ac_alarm_status"),
                        "ac_error_code": t.get("ac_error_code"),
                        "store_temps": {k: round(v, 1) for k, v in (t.get("store_temps") or {}).items()},
                    },
                })

            # Close last regime segment
            if current_regime and regime_start and telem_records:
                regime_segments.append({
                    "asset_id": asset_id,
                    "regime": current_regime,
                    "start_time": regime_start,
                    "end_time": telem_records[-1]["timestamp"],
                    "duration_minutes": (telem_records[-1]["timestamp"] - regime_start).total_seconds() / 60,
                    "n_readings": 1,
                })

            # Bulk insert telemetry
            session.bulk_insert_mappings(TelemetryModel, telem_records)
            total_telemetry += len(telem_records)

            # Insert regime segments
            for seg in regime_segments:
                session.add(RegimeSegmentModel(
                    asset_id=seg["asset_id"],
                    regime=seg["regime"],
                    start_time=seg["start_time"],
                    end_time=seg["end_time"],
                    n_samples=seg["n_readings"],
                    confidence=0.92,
                ))
            total_segments += len(regime_segments)

            # Generate alerts for fault-injected assets
            if fault and scenario_name:
                alerts = _generate_alerts(asset_id, site_id, scenario_name, telemetry_dicts, fault)
                for a in alerts:
                    session.add(AlertModel(**a))
                total_alerts += len(alerts)

            # Generate fingerprint
            fp = _generate_fingerprint(asset_id, telemetry_dicts)
            existing_fp = session.query(FingerprintModel).filter(
                FingerprintModel.asset_id == asset_id
            ).first()
            if not existing_fp:
                session.add(FingerprintModel(**fp))
                total_fingerprints += 1

            # Audit log entry
            session.add(AuditLogModel(
                event_id=f"EVT-{uuid.uuid4().hex[:8].upper()}",
                action="data_population",
                actor="demo_populate",
                target_type="asset",
                target_id=asset_id,
                details={
                    "source": "AD2_HVAC_Data_set_1.csv",
                    "site_id": site_id,
                    "telemetry_count": len(telem_records),
                    "scenario": scenario_name,
                    "interpolated": interpolate,
                },
            ))

            session.commit()

        tag = f" [FAULT: {scenario_name}]" if scenario_name else ""
        print(f"  [{site_idx + 1:2d}/{len(site_ids)}] {site_id}: {asset_id} — "
              f"{len(telem_records)} telemetry, {len(regime_segments)} regimes"
              f"{tag}")

    print(f"\n[2/6] Assets:       {total_assets} created")
    print(f"[3/6] Telemetry:    {total_telemetry} records")
    print(f"[4/6] Alerts:       {total_alerts} generated")
    print(f"[5/6] Fingerprints: {total_fingerprints} created")
    print(f"[5/6] Segments:     {total_segments} regime segments")

    # ── 4. Run KPI pipeline and persist results ────────────────────
    if run_kpi:
        print("\n[6/6] Running KPI orchestrator...")
        _run_and_persist_kpi(site_ids)

    print("\n" + "=" * 80)
    print("POPULATION COMPLETE")
    print("=" * 80)


def _classify_regime(t: Dict[str, Any]) -> str:
    """Classify operating regime from telemetry."""
    if not t.get("compressor_on"):
        if t.get("evap_fan_on"):
            return "fan_only"
        return "off"
    mode = t.get("ac_mode", 0)
    if mode == 3:  # COOL
        return "cooling_steady"
    elif mode == 1:  # HEAT
        return "heating_steady"
    elif mode == 2:  # DRY
        return "dehumidify"
    # Infer from temps
    zone = t.get("zone_temp") or 70
    setpoint = t.get("setpoint") or 70
    if zone > setpoint + 2:
        return "cooling_steady"
    elif zone < setpoint - 2:
        return "heating_steady"
    return "cooling_steady"


def _round_or_none(val, decimals=1):
    if val is None:
        return None
    return round(float(val), decimals)


def _generate_alerts(
    asset_id: str,
    site_id: str,
    scenario_name: str,
    telemetry: List[Dict],
    fault,
) -> List[Dict[str, Any]]:
    """Generate realistic alerts from fault-injected telemetry."""
    alerts = []
    n = len(telemetry)
    onset_idx = int(fault.onset_fraction * n)
    ramp_len = max(1, int(fault.ramp_duration_fraction * n))

    fault_labels = {
        "refrigerant_leak": ("refrigerant_leak", "Low refrigerant charge detected — superheat elevated, suction pressure dropping"),
        "condenser_fouling": ("condenser_fouling", "Condenser coil fouling — discharge pressure elevated, efficiency degraded"),
        "sensor_drift": ("sensor_calibration_drift", "Return-air temperature sensor drifting — readings inconsistent with zone conditions"),
        "compressor_degradation": ("compressor_wear", "Compressor valve wear — reduced pressure differential, elevated current draw"),
    }
    primary_fault, description = fault_labels.get(scenario_name, ("unknown", "Unknown fault"))

    # Generate watch alert at ~50% through fault ramp
    watch_idx = onset_idx + ramp_len // 2
    if watch_idx < n:
        t = telemetry[watch_idx]
        alerts.append({
            "alert_id": f"ALT-{uuid.uuid4().hex[:8].upper()}",
            "asset_id": asset_id,
            "alert_type": "watch",
            "severity": "low",
            "false_alarm_probability": 0.35,
            "confidence": 0.55,
            "primary_fault": primary_fault,
            "fault_beliefs": {primary_fault: 0.55, "normal_wear": 0.30, "other": 0.15},
            "evidence_summary": [
                f"Anomaly detected in {scenario_name.replace('_', ' ')} pattern",
                f"Regime: {_classify_regime(t)}",
            ],
            "recommended_action": "Monitor closely — trend developing",
            "action_urgency": "monitor",
            "regime_at_detection": _classify_regime(t),
            "ambient_temp_at_detection": _round_or_none(t.get("ambient_temp")),
            "status": "acknowledged",
            "created_at": t["timestamp"],
            "acknowledged_at": t["timestamp"] + timedelta(hours=2),
            "acknowledged_by": "operator_demo",
        })

    # Generate actionable alert at ~85% through fault ramp
    action_idx = onset_idx + int(ramp_len * 0.85)
    if action_idx < n:
        t = telemetry[action_idx]
        alerts.append({
            "alert_id": f"ALT-{uuid.uuid4().hex[:8].upper()}",
            "asset_id": asset_id,
            "alert_type": "actionable",
            "severity": "high",
            "false_alarm_probability": 0.12,
            "confidence": 0.82,
            "primary_fault": primary_fault,
            "fault_beliefs": {primary_fault: 0.82, "normal_wear": 0.12, "other": 0.06},
            "evidence_summary": [
                description,
                f"Confidence: 82% | False alarm probability: 12%",
                f"Duration: {(t['timestamp'] - telemetry[watch_idx]['timestamp']).total_seconds() / 3600:.1f}h since first watch",
            ],
            "recommended_action": f"Schedule {scenario_name.replace('_', ' ')} inspection within 48 hours",
            "action_urgency": "schedule",
            "energy_penalty_estimate_pct": random.uniform(5, 20),
            "downtime_risk_score": random.uniform(0.3, 0.7),
            "comfort_risk_score": random.uniform(0.2, 0.5),
            "estimated_cost_if_ignored": random.uniform(2000, 15000),
            "regime_at_detection": _classify_regime(t),
            "ambient_temp_at_detection": _round_or_none(t.get("ambient_temp")),
            "status": "active",
            "created_at": t["timestamp"],
        })

    # Generate a post-fault critical alert at end of ramp
    end_idx = min(onset_idx + ramp_len + 5, n - 1)
    if end_idx < n and end_idx > action_idx:
        t = telemetry[end_idx]
        alerts.append({
            "alert_id": f"ALT-{uuid.uuid4().hex[:8].upper()}",
            "asset_id": asset_id,
            "alert_type": "actionable",
            "severity": "critical",
            "false_alarm_probability": 0.05,
            "confidence": 0.93,
            "primary_fault": primary_fault,
            "fault_beliefs": {primary_fault: 0.93, "normal_wear": 0.05, "other": 0.02},
            "evidence_summary": [
                f"CRITICAL: {description}",
                "Fault fully developed — immediate action required",
                f"Multi-agent consensus: 93% confidence",
            ],
            "recommended_action": f"Dispatch technician immediately for {scenario_name.replace('_', ' ')} repair",
            "action_urgency": "urgent",
            "energy_penalty_estimate_pct": random.uniform(15, 35),
            "downtime_risk_score": random.uniform(0.7, 0.95),
            "comfort_risk_score": random.uniform(0.5, 0.8),
            "estimated_cost_if_ignored": random.uniform(8000, 30000),
            "regime_at_detection": _classify_regime(t),
            "ambient_temp_at_detection": _round_or_none(t.get("ambient_temp")),
            "status": "active",
            "created_at": t["timestamp"],
        })

    return alerts


def _generate_fingerprint(asset_id: str, telemetry: List[Dict]) -> Dict[str, Any]:
    """Generate a fingerprint from telemetry stream."""
    from collections import defaultdict

    regime_counts = defaultdict(int)
    regime_baselines = defaultdict(lambda: defaultdict(list))

    for t in telemetry:
        regime = _classify_regime(t)
        regime_counts[regime] += 1
        for key in ["suction_pressure", "discharge_pressure", "suction_line_temp",
                     "discharge_temp", "supply_air_temp", "return_air_temp",
                     "compressor_current", "superheat", "subcool"]:
            val = t.get(key)
            if val is not None:
                regime_baselines[regime][key].append(float(val))

    # Compute mu/sigma per regime per sensor
    baselines = {}
    for regime, sensors in regime_baselines.items():
        baselines[regime] = {}
        for sensor, vals in sensors.items():
            if vals:
                baselines[regime][sensor] = {
                    "mu": round(float(np.mean(vals)), 2),
                    "sigma": round(float(np.std(vals)), 3),
                }

    hours = 0
    if telemetry:
        t0 = telemetry[0]["timestamp"]
        t1 = telemetry[-1]["timestamp"]
        hours = (t1 - t0).total_seconds() / 3600

    return {
        "fingerprint_id": f"FP-{uuid.uuid4().hex[:8].upper()}",
        "asset_id": asset_id,
        "sensor_offsets": {},
        "regime_baselines": baselines,
        "hours_of_data": round(hours, 1),
        "adaptation_confidence": min(0.95, hours / 200),
        "n_regimes_observed": dict(regime_counts),
        "last_fitted_at": telemetry[-1]["timestamp"] if telemetry else None,
    }


def _run_and_persist_kpi(site_ids: List[str]):
    """Run the KPI orchestrator and persist results."""
    try:
        from predictive_maintenance.persistence.database import get_session
        from predictive_maintenance.persistence.models import AssetModel, TelemetryModel, AlertModel
        from predictive_maintenance.persistence.kpi_repository import (
            KPIPipelineRepository, KPIResultRepository, get_dashboard_cache,
        )
        from predictive_maintenance.services.kpi import KPIOrchestrator, KPIConfig

        with get_session() as session:
            # Collect data across all sites
            assets = session.query(AssetModel).filter(AssetModel.is_active == True).all()
            asset_data = []
            for a in assets:
                asset_data.append({
                    "asset_id": a.asset_id,
                    "site_id": a.site_id,
                    "asset_type": a.asset_type,
                    "manufacturer": a.manufacturer,
                    "install_date": a.install_date.isoformat() if a.install_date else None,
                    "refrigerant_type": a.refrigerant_type,
                    "nominal_capacity_tons": a.nominal_capacity_tons,
                    "is_active": a.is_active,
                })

            alerts = session.query(AlertModel).all()
            alert_data = []
            for al in alerts:
                alert_data.append({
                    "alert_id": al.alert_id,
                    "asset_id": al.asset_id,
                    "alert_type": al.alert_type,
                    "severity": al.severity,
                    "primary_fault": al.primary_fault,
                    "confidence": al.confidence,
                    "false_alarm_probability": al.false_alarm_probability,
                    "status": al.status,
                    "created_at": al.created_at.isoformat() if al.created_at else None,
                    "feedback_outcome": al.feedback_outcome,
                    "estimated_cost_if_ignored": al.estimated_cost_if_ignored,
                })

            # Telemetry summary
            from sqlalchemy import func
            telem_count = session.query(func.count(TelemetryModel.id)).scalar() or 0
            avg_quality = session.query(func.avg(TelemetryModel.data_quality_score)).scalar() or 0.95

            telemetry_summary = {
                "total_readings": telem_count,
                "avg_data_quality": round(float(avg_quality), 3),
                "sensors_monitored": 16,
                "collection_period_days": 7,
            }

            # Health data (simulated from asset data)
            health_data = []
            rng = random.Random(42)
            for a in asset_data:
                has_fault = any(
                    al["asset_id"] == a["asset_id"] and al["alert_type"] == "actionable"
                    for al in alert_data
                )
                base_health = rng.uniform(0.4, 0.7) if has_fault else rng.uniform(0.75, 0.98)
                rul = rng.uniform(200, 1500) if has_fault else rng.uniform(3000, 15000)
                health_data.append({
                    "asset_id": a["asset_id"],
                    "health_score": round(base_health, 3),
                    "rul_hours": round(rul, 1),
                    "degradation_rate": round(rng.uniform(0.001, 0.01), 4),
                    "maintenance_priority": "high" if has_fault else "normal",
                })

            print(f"  Data collected: {len(asset_data)} assets, {len(alert_data)} alerts, "
                  f"{telem_count} telemetry records")

            # Run KPI orchestrator
            config = KPIConfig(
                site_id="default",
                total_assets=max(len(asset_data), 1),
            )
            orchestrator = KPIOrchestrator(config)
            result = orchestrator.compute_all(
                asset_data=asset_data,
                alert_data=alert_data,
                telemetry_summary=telemetry_summary,
                health_data=health_data,
            )
            result_dict = result.to_dict()

            # Persist KPI pipeline run
            pipeline_repo = KPIPipelineRepository(session)
            result_repo = KPIResultRepository(session)

            run = pipeline_repo.create_run("default")
            pipeline_repo.complete_run(run.run_id, result_dict)
            result_repo.store_results(run.run_id, "default", result_dict.get("scorecards", []))

            # Cache results
            cache = get_dashboard_cache()
            cache.set("default", result_dict)

            session.commit()

            total_savings = result_dict.get("executive_summary", {}).get("total_savings_medium", 0)
            kpi_count = result_dict.get("executive_summary", {}).get("kpi_count", 0)
            print(f"  KPI pipeline run {run.run_id}: {kpi_count} KPIs, "
                  f"${total_savings:,.0f} total savings (medium)")
            print(f"  Results cached and persisted to PostgreSQL")

    except Exception as e:
        logger.error("KPI pipeline failed: %s", e, exc_info=True)
        print(f"  KPI pipeline error: {e}")


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Populate persistence layer with real HVAC BMS data",
    )
    parser.add_argument("--csv", required=True, help="Path to AD2_HVAC_Data_set_1.csv")
    parser.add_argument("--max-sites", type=int, default=33, help="Max sites to process")
    parser.add_argument("--no-interpolate", action="store_true", help="Skip interpolation")
    parser.add_argument("--interval", type=int, default=15, help="Interpolation interval (minutes)")
    parser.add_argument("--no-kpi", action="store_true", help="Skip KPI pipeline run")
    parser.add_argument("--log-level", default="WARNING", help="Logging level")

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(levelname)-8s %(name)s: %(message)s",
    )

    populate_all(
        csv_path=args.csv,
        max_sites=args.max_sites,
        interpolate=not args.no_interpolate,
        interval_minutes=args.interval,
        run_kpi=not args.no_kpi,
    )


if __name__ == "__main__":
    main()
