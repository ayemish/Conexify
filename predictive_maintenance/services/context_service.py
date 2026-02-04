"""Context Service

Provides weather, occupancy, and tariff context features for modeling.
This is intentionally lightweight and supports both direct telemetry-provided
context and optional external feeds.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Any

import math

logger = logging.getLogger(__name__)


@dataclass
class ContextSnapshot:
    asset_id: str
    timestamp: datetime
    ambient_temp: Optional[float] = None
    ambient_humidity: Optional[float] = None
    ambient_pressure: Optional[float] = None
    occupancy_fraction: Optional[float] = None
    energy_price: Optional[float] = None
    dew_point: Optional[float] = None
    wbgt: Optional[float] = None


class ContextService:
    """Manage external context inputs and derived features."""

    def __init__(self):
        self._latest: Dict[str, ContextSnapshot] = {}

    def ingest_weather(
        self,
        asset_id: str,
        timestamp: datetime,
        ambient_temp: Optional[float] = None,
        ambient_humidity: Optional[float] = None,
        ambient_pressure: Optional[float] = None,
    ):
        snapshot = self._latest.get(asset_id) or ContextSnapshot(asset_id=asset_id, timestamp=timestamp)
        snapshot.timestamp = timestamp
        if ambient_temp is not None:
            snapshot.ambient_temp = ambient_temp
        if ambient_humidity is not None:
            snapshot.ambient_humidity = ambient_humidity
        if ambient_pressure is not None:
            snapshot.ambient_pressure = ambient_pressure
        self._derive_features(snapshot)
        self._latest[asset_id] = snapshot

    def ingest_occupancy(self, asset_id: str, timestamp: datetime, occupancy_fraction: float):
        snapshot = self._latest.get(asset_id) or ContextSnapshot(asset_id=asset_id, timestamp=timestamp)
        snapshot.timestamp = timestamp
        snapshot.occupancy_fraction = float(max(0.0, min(1.0, occupancy_fraction)))
        self._latest[asset_id] = snapshot

    def ingest_tariff(self, asset_id: str, timestamp: datetime, energy_price: float):
        snapshot = self._latest.get(asset_id) or ContextSnapshot(asset_id=asset_id, timestamp=timestamp)
        snapshot.timestamp = timestamp
        snapshot.energy_price = float(max(0.0, energy_price))
        self._latest[asset_id] = snapshot

    def build_context(self, asset_id: str, telemetry: Dict[str, Any], timestamp: datetime) -> Dict[str, float]:
        """Build modeling context from telemetry + latest external context."""
        context: Dict[str, float] = {}
        snapshot = self._latest.get(asset_id)

        # Prefer telemetry-provided context
        if telemetry.get("ambient_temp") is not None:
            context["ambient_temp"] = float(telemetry["ambient_temp"])
        elif snapshot and snapshot.ambient_temp is not None:
            context["ambient_temp"] = snapshot.ambient_temp

        if telemetry.get("ambient_humidity") is not None:
            context["ambient_humidity"] = float(telemetry["ambient_humidity"])
        elif snapshot and snapshot.ambient_humidity is not None:
            context["ambient_humidity"] = snapshot.ambient_humidity

        if snapshot and snapshot.dew_point is not None:
            context["dew_point"] = snapshot.dew_point
        if snapshot and snapshot.wbgt is not None:
            context["wbgt"] = snapshot.wbgt

        # Occupancy proxy
        if telemetry.get("occupancy_fraction") is not None:
            context["occupancy_fraction"] = float(telemetry["occupancy_fraction"])
        elif snapshot and snapshot.occupancy_fraction is not None:
            context["occupancy_fraction"] = snapshot.occupancy_fraction
        else:
            # Simple heuristic: 0.8 in business hours, 0.2 otherwise
            hour = timestamp.hour
            context["occupancy_fraction"] = 0.8 if 7 <= hour <= 18 else 0.2

        # Tariff / energy price
        if telemetry.get("energy_price") is not None:
            context["energy_price"] = float(telemetry["energy_price"])
        elif snapshot and snapshot.energy_price is not None:
            context["energy_price"] = snapshot.energy_price
        else:
            # Simple TOU proxy: higher price 3-7pm
            hour = timestamp.hour
            context["energy_price"] = 0.22 if 15 <= hour <= 19 else 0.12

        return context

    def _derive_features(self, snapshot: ContextSnapshot):
        """Derive dew point and WBGT from ambient temp/humidity."""
        if snapshot.ambient_temp is None or snapshot.ambient_humidity is None:
            return
        temp_c = (snapshot.ambient_temp - 32) * 5.0 / 9.0
        rh = max(1.0, min(100.0, snapshot.ambient_humidity))
        # Magnus formula
        a, b = 17.27, 237.7
        alpha = (a * temp_c) / (b + temp_c) + math.log(rh / 100.0)
        dew_c = (b * alpha) / (a - alpha)
        snapshot.dew_point = dew_c * 9.0 / 5.0 + 32
        # Simplified WBGT (indoor) approximation
        snapshot.wbgt = 0.7 * snapshot.dew_point + 0.3 * snapshot.ambient_temp
