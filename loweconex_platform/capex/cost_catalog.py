"""
Centralized CapEx Cost Catalog — single source of truth for replacement costs.

Reads from digital twin ``AssetEconomics.capex_replace_cost`` first, then
falls back to the type-based default catalog.  All KPI crews, the CapEx
engine, and the portfolio optimizer should use ``get_replacement_cost()``
instead of maintaining their own cost maps.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── Type-based default replacement costs (USD) ─────────────────────
# Used when the digital twin has no economics data for an asset.

DEFAULT_REPLACEMENT_COSTS: Dict[str, float] = {
    "hvac_rtu": 18_000.0,
    "hvac_ahu": 35_000.0,
    "refrigeration_rack": 45_000.0,
    "refrigeration_case": 8_000.0,
    "compressor": 12_000.0,
    "condenser": 9_500.0,
    "evaporator": 7_000.0,
    "boiler": 25_000.0,
    "chiller": 60_000.0,
    "vfd": 4_500.0,
    "lighting": 2_000.0,
    "power_meter": 1_200.0,
    "temp_sensor": 500.0,
    "leak_detector": 800.0,
    "other": 15_000.0,
}

# ── Expected useful life (years) by asset type ─────────────────────

DEFAULT_USEFUL_LIFE_YEARS: Dict[str, float] = {
    "hvac_rtu": 15.0,
    "hvac_ahu": 20.0,
    "refrigeration_rack": 15.0,
    "refrigeration_case": 12.0,
    "compressor": 12.0,
    "condenser": 15.0,
    "evaporator": 15.0,
    "boiler": 20.0,
    "chiller": 20.0,
    "vfd": 10.0,
    "lighting": 8.0,
    "power_meter": 15.0,
    "temp_sensor": 10.0,
    "leak_detector": 10.0,
    "other": 15.0,
}


def get_replacement_cost(
    asset_id: str,
    asset_type: str = "other",
    twin_store: Optional[Any] = None,
) -> float:
    """Return the replacement cost for an asset.

    Lookup order:
    1. Digital twin ``AssetEconomics.capex_replace_cost`` (if twin_store provided)
    2. Type-based default catalog

    Parameters
    ----------
    asset_id : str
        The asset identifier.
    asset_type : str
        Asset type string (e.g. ``"hvac_rtu"``).
    twin_store : TwinStore, optional
        If provided, will attempt to read economics from the digital twin.

    Returns
    -------
    float
        Replacement cost in USD.
    """
    # Try digital twin economics
    if twin_store is not None:
        try:
            twin = twin_store.get_asset(asset_id)
            if twin is not None:
                economics = getattr(twin, "economics", None)
                if economics and getattr(economics, "capex_replace_cost", 0) > 0:
                    return economics.capex_replace_cost
        except Exception:
            pass

    # Fall back to type-based default
    asset_type_lower = asset_type.lower() if asset_type else "other"
    return DEFAULT_REPLACEMENT_COSTS.get(asset_type_lower, DEFAULT_REPLACEMENT_COSTS["other"])


def get_useful_life(asset_type: str = "other") -> float:
    """Return expected useful life in years for an asset type."""
    asset_type_lower = asset_type.lower() if asset_type else "other"
    return DEFAULT_USEFUL_LIFE_YEARS.get(asset_type_lower, DEFAULT_USEFUL_LIFE_YEARS["other"])
