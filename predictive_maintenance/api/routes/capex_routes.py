"""
CapEx Platform Data API

Endpoint that collects asset, telemetry, work-order, energy, and economic
data from the platform's persistence layer and transforms it into the exact
JSON shape the frontend CapEx engine expects — eliminating the need for
spreadsheet upload.
"""

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

capex_data_router = APIRouter()

# ═══════════════════════════════════════════════════════════════════════
# Asset-type mapping: platform DB values → CapEx engine constants
# ═══════════════════════════════════════════════════════════════════════

_ASSET_TYPE_MAP = {
    "hvac_rtu": "RTU",
    "rtu": "RTU",
    "ahu": "AHU",
    "chiller": "Chiller",
    "boiler": "Boiler",
    "condensing_unit": "Condensing Unit",
    "compressor_rack": "Compressor Rack",
    "walk_in_cooler": "Walk-in Cooler",
    "walk_in_freezer": "Walk-in Freezer",
    "reach_in_case": "Reach-in Case",
    "vfd": "VFD",
    "pump": "Pump",
    "exhaust_fan": "Exhaust Fan",
    "lighting": "Lighting System",
    "bms": "Building Management System",
    # Also handle the CapEx engine names as pass-through
    "RTU": "RTU",
    "AHU": "AHU",
    "Chiller": "Chiller",
    "Compressor Rack": "Compressor Rack",
    "Walk-in Cooler": "Walk-in Cooler",
    "Walk-in Freezer": "Walk-in Freezer",
    "Reach-in Case": "Reach-in Case",
    "Condensing Unit": "Condensing Unit",
}

_CRITICALITY_MAP = {
    "RTU": "Comfort",
    "AHU": "Comfort",
    "Chiller": "Comfort",
    "Boiler": "Comfort",
    "Compressor Rack": "Food Safety",
    "Condensing Unit": "Food Safety",
    "Walk-in Cooler": "Food Safety",
    "Walk-in Freezer": "Food Safety",
    "Reach-in Case": "Food Safety",
    "VFD": "Operational",
    "Pump": "Operational",
    "Exhaust Fan": "Operational",
    "Lighting System": "Operational",
    "Building Management System": "Mission Critical",
}

# Replacement option cost tables (matching sampleData.js generateReplacementOptions)
_REPLACEMENT_COST_BASE = {
    "RTU": {"cost": 8000, "life": 15},
    "AHU": {"cost": 25000, "life": 20},
    "Compressor Rack": {"cost": 75000, "life": 15},
    "Walk-in Cooler": {"cost": 15000, "life": 20},
    "Walk-in Freezer": {"cost": 25000, "life": 20},
    "Reach-in Case": {"cost": 5000, "life": 12},
    "Condensing Unit": {"cost": 8000, "life": 15},
    "Chiller": {"cost": 50000, "life": 25},
    "Boiler": {"cost": 30000, "life": 20},
}

_DEFAULT_COST_BASE = {"cost": 10000, "life": 15}

# Failure event costs by asset type (matching sampleData.js)
_FAILURE_EVENT_COSTS = {
    "RTU": 15000,
    "AHU": 20000,
    "Compressor Rack": 75000,
    "Walk-in Cooler": 25000,
    "Walk-in Freezer": 50000,
    "Reach-in Case": 8000,
    "Condensing Unit": 12000,
    "Chiller": 80000,
    "Boiler": 40000,
}

# Telemetry column → CapEx canonical metric mapping
_TELEMETRY_METRIC_MAP = {
    "compressor_power": "power_kw",
    "supply_air_temp": "supply_temp_c",
    "return_air_temp": "return_temp_c",
    "discharge_temp": "discharge_temp_c",
    "suction_pressure": "suction_pressure_psi",
    "discharge_pressure": "discharge_pressure_psi",
    "superheat": "superheat_k",
    "zone_temp": "zone_temp_c",
    "ambient_temp": "outdoor_air_temp_c",
    "setpoint": "setpoint_temp_c",
}


# ═══════════════════════════════════════════════════════════════════════
# Response models
# ═══════════════════════════════════════════════════════════════════════

class PlatformDataResponse(BaseModel):
    stores: List[Dict[str, Any]]
    assets: List[Dict[str, Any]]
    replacementOptions: List[Dict[str, Any]] = Field(default_factory=list)
    utilityRates: List[Dict[str, Any]] = Field(default_factory=list)
    economicAssumptions: List[Dict[str, Any]] = Field(default_factory=list)
    telemetry: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)
    maintenanceHistory: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)
    budget: Dict[str, Any] = Field(default_factory=dict)
    dataSource: Dict[str, str] = Field(default_factory=dict)
    meta: Dict[str, Any] = Field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════════════

def _map_asset_type(raw_type: str) -> str:
    """Map platform asset type to CapEx engine constant."""
    return _ASSET_TYPE_MAP.get(raw_type, _ASSET_TYPE_MAP.get(raw_type.lower().replace(" ", "_"), "RTU"))


def _compute_age_years(install_date) -> int:
    """Compute integer age in years from install date."""
    if install_date is None:
        return 5  # sensible default
    try:
        if isinstance(install_date, str):
            install_date = datetime.fromisoformat(install_date.replace("Z", "+00:00"))
        if install_date.tzinfo is None:
            install_date = install_date.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return max(0, int((now - install_date).days / 365.25))
    except Exception:
        return 5


def _generate_replacement_options(asset_id: str, asset_type: str, capacity: float, option_set_id: str) -> List[Dict]:
    """Generate 3-tier replacement options matching sampleData.js logic."""
    base = _REPLACEMENT_COST_BASE.get(asset_type, _DEFAULT_COST_BASE)
    capacity_factor = max(1.0, capacity / 10.0) if capacity else 1.0

    return [
        {
            "optionId": f"{asset_id}-opt-standard",
            "replacementOptionSetId": option_set_id,
            "optionName": "Standard Replacement",
            "capexInstalledCost": round(base["cost"] * capacity_factor),
            "expectedLifeYears": base["life"],
            "expectedEfficiencyDelta": 0.10,
            "expectedMaintenanceDeltaPerYear": -500,
            "leadTimeDays": 21,
            "warrantyYears": 1,
        },
        {
            "optionId": f"{asset_id}-opt-higheff",
            "replacementOptionSetId": option_set_id,
            "optionName": "High Efficiency",
            "capexInstalledCost": round(base["cost"] * capacity_factor * 1.35),
            "expectedLifeYears": base["life"] + 3,
            "expectedEfficiencyDelta": 0.25,
            "expectedMaintenanceDeltaPerYear": -800,
            "leadTimeDays": 35,
            "warrantyYears": 3,
        },
        {
            "optionId": f"{asset_id}-opt-premium",
            "replacementOptionSetId": option_set_id,
            "optionName": "Premium / VRF",
            "capexInstalledCost": round(base["cost"] * capacity_factor * 1.8),
            "expectedLifeYears": base["life"] + 5,
            "expectedEfficiencyDelta": 0.35,
            "expectedMaintenanceDeltaPerYear": -1200,
            "leadTimeDays": 60,
            "warrantyYears": 5,
        },
    ]


def _derive_store_from_site(site_id: str, asset_data: List[Dict], kpi_cfg) -> Dict:
    """Build a CapEx 'store' object from site info."""
    # Attempt estate / location derivation
    estate = site_id.replace("_", " ").title() if site_id != "default" else "Main Campus"
    return {
        "storeId": site_id,
        "name": estate,
        "address": "",
        "lat": 41.88,   # default Chicago
        "lon": -87.63,
        "region": "Midwest",
        "climateZone": "5A",
        "areaSqft": 50000,
        "storeType": "Grocery",
        "utilityRateId": f"rate-{site_id}",
    }


# ═══════════════════════════════════════════════════════════════════════
# Main endpoint
# ═══════════════════════════════════════════════════════════════════════

@capex_data_router.get("/platform-data", response_model=PlatformDataResponse)
async def get_platform_data_for_capex(
    site_id: str = Query(default="default", description="Site ID"),
    telemetry_days: int = Query(default=90, ge=7, le=365, description="Days of telemetry to load"),
    wo_days: int = Query(default=365, ge=30, le=730, description="Days of work-order history"),
):
    """
    Collect all platform data and transform into the CapEx engine's expected
    JSON shape — same format as manual JSON upload.
    """
    now = datetime.now(timezone.utc)
    telemetry_start = now - timedelta(days=telemetry_days)
    wo_start = now - timedelta(days=wo_days)

    # ── 1. Load KPI Config (economic parameters) ───────────────────
    try:
        from ...services.kpi.base import KPIConfig
        kpi_cfg = KPIConfig.load_from_db(site_id)
    except Exception as e:
        logger.warning("KPIConfig load failed: %s — using defaults", e)
        from ...services.kpi.base import KPIConfig
        kpi_cfg = KPIConfig(site_id=site_id)

    # ── 2. Load assets from DB ─────────────────────────────────────
    asset_data = []
    asset_ids = []
    try:
        from ...persistence.database import get_session
        from ...persistence.models import (
            AssetModel, TelemetryModel, WorkOrderModel,
            EnergyDataModel, MaintenanceHistoryModel,
        )
        from ...persistence.repositories import TelemetryRepository

        with get_session() as session:
            # Assets
            if site_id == "default":
                db_assets = session.query(AssetModel).filter(AssetModel.is_active == True).all()
            else:
                db_assets = session.query(AssetModel).filter(
                    AssetModel.site_id == site_id,
                    AssetModel.is_active == True,
                ).all()

            for a in db_assets:
                asset_ids.append(a.asset_id)
                asset_data.append({
                    "asset_id": a.asset_id,
                    "site_id": a.site_id,
                    "asset_type_raw": a.asset_type or "hvac_rtu",
                    "manufacturer": a.manufacturer or "",
                    "model_number": a.model_number or "",
                    "install_date": a.install_date,
                    "capacity": a.nominal_capacity_tons or 0,
                    "refrigerant_type": a.refrigerant_type,
                })

            # ── 3. Load telemetry per asset ─────────────────────────
            telemetry_repo = TelemetryRepository(session)
            telemetry_by_asset: Dict[str, List[Dict]] = {}
            min_telemetry_threshold = 7  # days

            for aid in asset_ids:
                readings = telemetry_repo.get_range(aid, telemetry_start, now, limit=50000)
                if len(readings) < min_telemetry_threshold:
                    # Not enough real data — engine will generate synthetic
                    continue

                transformed = []
                for r in readings:
                    ts = r.timestamp.isoformat() if r.timestamp else now.isoformat()
                    # Emit one row per metric that has a value
                    for db_col, capex_metric in _TELEMETRY_METRIC_MAP.items():
                        val = getattr(r, db_col, None)
                        if val is not None and not (isinstance(val, float) and math.isnan(val)):
                            transformed.append({
                                "ts": ts,
                                "assetId": aid,
                                "metric": capex_metric,
                                "value": round(float(val), 2),
                                "qualityFlag": "good" if (r.data_quality_score or 1.0) >= 0.8 else "imputed",
                            })

                if transformed:
                    telemetry_by_asset[aid] = transformed

            # ── 4. Load work orders per asset ───────────────────────
            wo_by_asset: Dict[str, List[Dict]] = {}
            wo_rows = session.query(WorkOrderModel).filter(
                WorkOrderModel.opened_at >= wo_start,
            )
            if site_id != "default":
                wo_rows = wo_rows.filter(WorkOrderModel.site_id == site_id)
            for wo in wo_rows.all():
                aid = wo.asset_id
                if aid not in wo_by_asset:
                    wo_by_asset[aid] = []
                close_ts = wo.closed_at.isoformat() if wo.closed_at else None
                open_ts = wo.opened_at.isoformat() if wo.opened_at else now.isoformat()
                downtime_hours = 0
                if wo.closed_at and wo.opened_at:
                    downtime_hours = round((wo.closed_at - wo.opened_at).total_seconds() / 3600, 1)
                wo_by_asset[aid].append({
                    "workOrderId": wo.wo_id,
                    "assetId": aid,
                    "openTs": open_ts,
                    "closeTs": close_ts,
                    "category": "repair" if (wo.wo_type or "").lower() in ("reactive", "emergency", "repair") else "PM",
                    "costTotal": round(float(wo.cost or 0), 2),
                    "downtimeHours": downtime_hours,
                    "failureCode": wo.description[:50] if wo.description else "",
                })

            # ── 5. Load energy data for utility rate ────────────────
            energy_rows = session.query(EnergyDataModel).filter(
                EnergyDataModel.period_start >= (now - timedelta(days=365)),
            )
            if site_id != "default":
                energy_rows = energy_rows.filter(EnergyDataModel.site_id == site_id)
            energy_list = energy_rows.all()

            annual_kwh = sum(float(r.kwh_consumed or 0) for r in energy_list)
            annual_cost = sum(float(r.cost or 0) for r in energy_list)
            effective_rate = (annual_cost / annual_kwh) if annual_kwh > 0 else kpi_cfg.energy_cost_per_kwh

    except Exception as e:
        logger.warning("Database query failed: %s — returning empty dataset", e)
        telemetry_by_asset = {}
        wo_by_asset = {}
        effective_rate = kpi_cfg.energy_cost_per_kwh
        annual_kwh = 0

    # ── 6. Build budget info ────────────────────────────────────────
    budget_info = {"annualCapexBudget": 200000}
    try:
        from .budget_routes import _budget_path
        import json as _json
        bp = _budget_path(site_id)
        if not bp.exists() and site_id != "default":
            bp = _budget_path("default")
        if bp.exists():
            bdata = _json.loads(bp.read_text())
            capex = float(bdata.get("overall_capex", 0) or 0)
            if capex > 0:
                budget_info["annualCapexBudget"] = capex
    except Exception as e:
        logger.debug("Budget load skipped: %s", e)

    # ═══════════════════════════════════════════════════════════════
    # Transform into CapEx engine shapes
    # ═══════════════════════════════════════════════════════════════

    store = _derive_store_from_site(site_id, asset_data, kpi_cfg)

    # Transform assets
    capex_assets = []
    all_replacement_options = []
    option_set_id = f"opt-set-{site_id}"

    for ad in asset_data:
        capex_type = _map_asset_type(ad["asset_type_raw"])
        age_years = _compute_age_years(ad["install_date"])
        install_iso = ad["install_date"].isoformat() if ad["install_date"] else datetime(
            datetime.now().year - age_years, 6, 1
        ).isoformat()

        capex_asset = {
            "assetId": ad["asset_id"],
            "storeId": site_id,
            "assetType": capex_type,
            "manufacturer": ad["manufacturer"],
            "model": ad["model_number"],
            "capacityNominal": ad["capacity"] or 10,
            "capacityUnit": "tons",
            "installDate": install_iso,
            "ageYears": age_years,
            "criticalityClass": _CRITICALITY_MAP.get(capex_type, "Comfort"),
            "replacementOptionSetId": option_set_id,
        }
        capex_assets.append(capex_asset)

        # Generate replacement options for this asset
        options = _generate_replacement_options(
            ad["asset_id"], capex_type, ad["capacity"] or 10, option_set_id
        )
        all_replacement_options.extend(options)

    # Utility rate
    utility_rate = {
        "utilityRateId": f"rate-{site_id}",
        "currency": "USD",
        "rateType": "flat",
        "energyRateSchedule": {
            "default": round(effective_rate, 4),
            "offPeak": round(effective_rate * 0.7, 4),
            "midPeak": round(effective_rate, 4),
            "onPeak": round(effective_rate * 1.5, 4),
        },
        "demandChargeSchedule": {
            "summer": kpi_cfg.demand_charge_per_kw_month,
            "winter": round(kpi_cfg.demand_charge_per_kw_month * 0.67, 2),
        },
        "escalationRateAssumption": 0.03,
    }

    # Economic assumptions
    # Build failure costs dict using CapEx engine asset type names
    failure_costs = {}
    for capex_type_name, cost in _FAILURE_EVENT_COSTS.items():
        failure_costs[capex_type_name] = cost

    economic_assumption = {
        "storeId": site_id,
        "discountRate": kpi_cfg.discount_rate,
        "analysisHorizonYears": 10,
        "inflationAssumption": 0.025,
        "failureEventCostByAssetType": failure_costs,
        "truckRollCost": round(kpi_cfg.avg_dispatch_cost * 0.55, 0),  # dispatch cost ≈ truck roll + overhead
        "laborRate": 95,
    }

    # Data source tracking
    data_source = {
        "weather": "none",
        "telemetry": "platform_db" if telemetry_by_asset else "will_generate",
        "workOrders": "platform_db" if wo_by_asset else "will_generate",
    }

    return PlatformDataResponse(
        stores=[store],
        assets=capex_assets,
        replacementOptions=all_replacement_options,
        utilityRates=[utility_rate],
        economicAssumptions=[economic_assumption],
        telemetry=telemetry_by_asset,
        maintenanceHistory=wo_by_asset,
        budget=budget_info,
        dataSource=data_source,
        meta={
            "generated_at": now.isoformat(),
            "site_id": site_id,
            "asset_count": len(capex_assets),
            "telemetry_assets_with_data": len(telemetry_by_asset),
            "work_order_assets_with_data": len(wo_by_asset),
            "energy_rate_source": "measured" if annual_kwh > 0 else "kpi_config_default",
        },
    )
