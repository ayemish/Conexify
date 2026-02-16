"""
Digital Twin Store — persistence layer for twin graph, time-series, and events.

Supports in-memory backend (default) with interface for PostgreSQL/TimescaleDB.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from loweconex_platform.digital_twins.models import (
    AssetTwin,
    EstateTwin,
    KPIRollup,
    LocationTwin,
    TwinRelationship,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Time-Series Point
# =============================================================================

class TimeSeriesPoint:
    """A single time-series observation."""
    __slots__ = ("timestamp", "value", "quality", "unit")

    def __init__(self, timestamp: datetime, value: float, quality: float = 1.0, unit: str = ""):
        self.timestamp = timestamp
        self.value = value
        self.quality = quality
        self.unit = unit

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "value": self.value,
            "quality": self.quality,
            "unit": self.unit,
        }


# =============================================================================
# Unified Event
# =============================================================================

class OperationalEvent:
    """
    Unified event model for faults, excursions, leaks, work orders.
    """

    def __init__(
        self,
        event_id: str,
        event_type: str,
        source_system: str,
        start_ts: datetime,
        end_ts: Optional[datetime] = None,
        asset_id: Optional[str] = None,
        location_id: Optional[str] = None,
        company_id: Optional[str] = None,
        severity: str = "info",
        confidence: float = 1.0,
        code: Optional[str] = None,
        ack_status: str = "unacked",
        ack_ts: Optional[datetime] = None,
        ack_user: Optional[str] = None,
        related_event_ids: Optional[List[str]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ):
        self.event_id = event_id
        self.event_type = event_type
        self.source_system = source_system
        self.start_ts = start_ts
        self.end_ts = end_ts
        self.asset_id = asset_id
        self.location_id = location_id
        self.company_id = company_id
        self.severity = severity
        self.confidence = confidence
        self.code = code
        self.ack_status = ack_status
        self.ack_ts = ack_ts
        self.ack_user = ack_user
        self.related_event_ids = related_event_ids or []
        self.payload = payload or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source_system": self.source_system,
            "start_ts": self.start_ts.isoformat(),
            "end_ts": self.end_ts.isoformat() if self.end_ts else None,
            "asset_id": self.asset_id,
            "location_id": self.location_id,
            "company_id": self.company_id,
            "severity": self.severity,
            "confidence": self.confidence,
            "code": self.code,
            "ack_status": self.ack_status,
            "ack_ts": self.ack_ts.isoformat() if self.ack_ts else None,
            "ack_user": self.ack_user,
            "related_event_ids": self.related_event_ids,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> OperationalEvent:
        return cls(
            event_id=data["event_id"],
            event_type=data["event_type"],
            source_system=data["source_system"],
            start_ts=datetime.fromisoformat(data["start_ts"]),
            end_ts=datetime.fromisoformat(data["end_ts"]) if data.get("end_ts") else None,
            asset_id=data.get("asset_id"),
            location_id=data.get("location_id"),
            company_id=data.get("company_id"),
            severity=data.get("severity", "info"),
            confidence=data.get("confidence", 1.0),
            code=data.get("code"),
            ack_status=data.get("ack_status", "unacked"),
            ack_ts=datetime.fromisoformat(data["ack_ts"]) if data.get("ack_ts") else None,
            ack_user=data.get("ack_user"),
            related_event_ids=data.get("related_event_ids", []),
            payload=data.get("payload", {}),
        )


# =============================================================================
# Twin Store (In-Memory)
# =============================================================================

class TwinStore:
    """
    Central store for digital twins, time-series, events, and relationships.
    
    Thread-safe in-memory implementation. Interface is compatible with
    PostgreSQL/TimescaleDB backends for production.
    
    Supports:
    - Idempotent ingestion via run_id dedup
    - Revision tracking per twin entity
    """

    def __init__(self):
        self._lock = threading.RLock()
        # Twin collections
        self._assets: Dict[str, AssetTwin] = {}
        self._locations: Dict[str, LocationTwin] = {}
        self._estates: Dict[str, EstateTwin] = {}
        # Relationships
        self._relationships: List[TwinRelationship] = []
        # Time-series: {point_id: [TimeSeriesPoint]}
        self._timeseries: Dict[str, List[TimeSeriesPoint]] = defaultdict(list)
        # Events: {event_id: OperationalEvent}
        self._events: Dict[str, OperationalEvent] = {}
        # Index: company -> location -> asset
        self._company_locations: Dict[str, List[str]] = defaultdict(list)
        self._location_assets: Dict[str, List[str]] = defaultdict(list)

        # Idempotency: track processed run_ids to prevent duplicate ingestion
        self._processed_run_ids: Dict[str, datetime] = {}
        # Revision ledger: entity_key -> revision_number
        self._revisions: Dict[str, int] = {}

        logger.info("TwinStore initialized (in-memory backend)")

    # -------------------------------------------------------------------------
    # Idempotency & Revision Tracking
    # -------------------------------------------------------------------------

    def check_run_id(self, run_id: str) -> bool:
        """Check if a run_id has already been processed. Returns True if already seen."""
        return run_id in self._processed_run_ids

    def register_run_id(self, run_id: str):
        """Mark a run_id as processed."""
        with self._lock:
            self._processed_run_ids[run_id] = datetime.utcnow()

    def idempotent_ingest(self, run_id: str) -> bool:
        """Returns True if this run_id is new and should be processed. Registers it atomically."""
        with self._lock:
            if run_id in self._processed_run_ids:
                logger.info(f"Run {run_id} already processed — skipping (idempotent)")
                return False
            self._processed_run_ids[run_id] = datetime.utcnow()
            return True

    def get_revision(self, entity_type: str, entity_id: str) -> int:
        """Get the current revision number for an entity."""
        key = f"{entity_type}:{entity_id}"
        return self._revisions.get(key, 0)

    def _bump_revision(self, entity_type: str, entity_id: str) -> int:
        """Increment and return the revision number for an entity."""
        key = f"{entity_type}:{entity_id}"
        rev = self._revisions.get(key, 0) + 1
        self._revisions[key] = rev
        return rev

    # -------------------------------------------------------------------------
    # Asset CRUD
    # -------------------------------------------------------------------------

    def upsert_asset(self, asset: AssetTwin) -> AssetTwin:
        with self._lock:
            asset.updated_ts = datetime.utcnow()
            self._assets[asset.asset_id] = asset
            if asset.asset_id not in self._location_assets[asset.location_id]:
                self._location_assets[asset.location_id].append(asset.asset_id)
            rev = self._bump_revision("asset", asset.asset_id)
            logger.debug(f"Asset {asset.asset_id} upserted (rev={rev})")
            return asset

    def get_asset(self, asset_id: str) -> Optional[AssetTwin]:
        return self._assets.get(asset_id)

    def get_assets_by_location(self, location_id: str) -> List[AssetTwin]:
        ids = self._location_assets.get(location_id, [])
        return [self._assets[a] for a in ids if a in self._assets]

    def get_assets_by_company(self, company_id: str) -> List[AssetTwin]:
        results = []
        for loc_id in self._company_locations.get(company_id, []):
            results.extend(self.get_assets_by_location(loc_id))
        return results

    def get_assets_by_type(self, company_id: str, asset_type: str) -> List[AssetTwin]:
        return [a for a in self.get_assets_by_company(company_id)
                if a.asset_type.value == asset_type]

    def delete_asset(self, asset_id: str) -> bool:
        with self._lock:
            asset = self._assets.pop(asset_id, None)
            if asset:
                loc_list = self._location_assets.get(asset.location_id, [])
                if asset_id in loc_list:
                    loc_list.remove(asset_id)
                return True
            return False

    # -------------------------------------------------------------------------
    # Location CRUD
    # -------------------------------------------------------------------------

    def upsert_location(self, location: LocationTwin) -> LocationTwin:
        with self._lock:
            location.updated_ts = datetime.utcnow()
            self._locations[location.location_id] = location
            if location.location_id not in self._company_locations[location.company_id]:
                self._company_locations[location.company_id].append(location.location_id)
            self._bump_revision("location", location.location_id)
            return location

    def get_location(self, location_id: str) -> Optional[LocationTwin]:
        return self._locations.get(location_id)

    def get_locations_by_company(self, company_id: str) -> List[LocationTwin]:
        ids = self._company_locations.get(company_id, [])
        return [self._locations[l] for l in ids if l in self._locations]

    def delete_location(self, location_id: str) -> bool:
        with self._lock:
            loc = self._locations.pop(location_id, None)
            if loc:
                clist = self._company_locations.get(loc.company_id, [])
                if location_id in clist:
                    clist.remove(location_id)
                return True
            return False

    # -------------------------------------------------------------------------
    # Estate CRUD
    # -------------------------------------------------------------------------

    def upsert_estate(self, estate: EstateTwin) -> EstateTwin:
        with self._lock:
            estate.updated_ts = datetime.utcnow()
            self._estates[estate.company_id] = estate
            self._bump_revision("estate", estate.company_id)
            return estate

    def get_estate(self, company_id: str) -> Optional[EstateTwin]:
        return self._estates.get(company_id)

    def list_estates(self) -> List[EstateTwin]:
        return list(self._estates.values())

    # -------------------------------------------------------------------------
    # Twin Patch (used by agents)
    # -------------------------------------------------------------------------

    def patch_twin(self, entity_type: str, entity_id: str, patch: Dict[str, Any]) -> bool:
        """Apply a partial update to a twin. Returns True if found and updated."""
        with self._lock:
            if entity_type == "asset":
                twin = self._assets.get(entity_id)
                if not twin:
                    return False
                for key, val in patch.items():
                    if key == "health" and isinstance(val, dict):
                        for hk, hv in val.items():
                            setattr(twin.health, hk, hv)
                    elif key == "economics" and isinstance(val, dict):
                        for ek, ev in val.items():
                            setattr(twin.economics, ek, ev)
                    elif hasattr(twin, key):
                        setattr(twin, key, val)
                twin.updated_ts = datetime.utcnow()
                return True
            elif entity_type == "location":
                twin = self._locations.get(entity_id)
                if not twin:
                    return False
                for key, val in patch.items():
                    if key == "kpi_rollups" and isinstance(val, dict):
                        for kpi_name, rollup_data in val.items():
                            twin.kpi_rollups[kpi_name] = KPIRollup(**rollup_data) if isinstance(rollup_data, dict) else rollup_data
                    elif hasattr(twin, key):
                        setattr(twin, key, val)
                twin.updated_ts = datetime.utcnow()
                return True
            elif entity_type == "estate":
                twin = self._estates.get(entity_id)
                if not twin:
                    return False
                for key, val in patch.items():
                    if hasattr(twin, key):
                        setattr(twin, key, val)
                twin.updated_ts = datetime.utcnow()
                return True
            return False

    def read_twin(self, entity_type: str, entity_id: str) -> Optional[Dict[str, Any]]:
        """Read a twin as dict. Convenience for agent tools."""
        if entity_type == "asset":
            t = self.get_asset(entity_id)
        elif entity_type == "location":
            t = self.get_location(entity_id)
        elif entity_type == "estate":
            t = self.get_estate(entity_id)
        else:
            return None
        return t.to_dict() if t else None

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------

    def add_relationship(self, rel: TwinRelationship):
        with self._lock:
            self._relationships.append(rel)

    def get_relationships(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        rel_type: Optional[str] = None,
    ) -> List[TwinRelationship]:
        results = self._relationships
        if source_id:
            results = [r for r in results if r.source_id == source_id]
        if target_id:
            results = [r for r in results if r.target_id == target_id]
        if rel_type:
            results = [r for r in results if r.relationship_type.value == rel_type]
        return results

    def get_connected_assets(self, asset_id: str) -> List[Tuple[str, str]]:
        """Get all assets connected to the given asset. Returns [(asset_id, relationship_type)]."""
        connected = []
        for r in self._relationships:
            if r.source_id == asset_id:
                connected.append((r.target_id, r.relationship_type.value))
            elif r.target_id == asset_id:
                connected.append((r.source_id, r.relationship_type.value))
        return connected

    # -------------------------------------------------------------------------
    # Time-Series
    # -------------------------------------------------------------------------

    def write_timeseries(self, point_id: str, points: List[TimeSeriesPoint]):
        with self._lock:
            self._timeseries[point_id].extend(points)
            self._timeseries[point_id].sort(key=lambda p: p.timestamp)

    def query_timeseries(
        self,
        point_ids: List[str],
        start_ts: Optional[datetime] = None,
        end_ts: Optional[datetime] = None,
    ) -> Dict[str, List[TimeSeriesPoint]]:
        results = {}
        for pid in point_ids:
            pts = self._timeseries.get(pid, [])
            if start_ts:
                pts = [p for p in pts if p.timestamp >= start_ts]
            if end_ts:
                pts = [p for p in pts if p.timestamp <= end_ts]
            results[pid] = pts
        return results

    # -------------------------------------------------------------------------
    # Event Store
    # -------------------------------------------------------------------------

    def store_event(self, event: OperationalEvent, run_id: Optional[str] = None) -> bool:
        """Store an event. If run_id provided, deduplicates by (run_id, event_id)."""
        with self._lock:
            if run_id:
                dedup_key = f"{run_id}:{event.event_id}"
                if dedup_key in self._processed_run_ids:
                    return False
                self._processed_run_ids[dedup_key] = datetime.utcnow()
            self._events[event.event_id] = event
            return True

    def get_event(self, event_id: str) -> Optional[OperationalEvent]:
        return self._events.get(event_id)

    def query_events(
        self,
        company_id: Optional[str] = None,
        location_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        event_type: Optional[str] = None,
        start_ts: Optional[datetime] = None,
        end_ts: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[OperationalEvent]:
        events = list(self._events.values())
        if company_id:
            events = [e for e in events if e.company_id == company_id]
        if location_id:
            events = [e for e in events if e.location_id == location_id]
        if asset_id:
            events = [e for e in events if e.asset_id == asset_id]
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if start_ts:
            events = [e for e in events if e.start_ts >= start_ts]
        if end_ts:
            events = [e for e in events if e.start_ts <= end_ts]
        events.sort(key=lambda e: e.start_ts, reverse=True)
        return events[:limit]

    # -------------------------------------------------------------------------
    # Stats
    # -------------------------------------------------------------------------

    def stats(self) -> Dict[str, int]:
        return {
            "assets": len(self._assets),
            "locations": len(self._locations),
            "estates": len(self._estates),
            "relationships": len(self._relationships),
            "timeseries_points": sum(len(v) for v in self._timeseries.values()),
            "events": len(self._events),
            "processed_run_ids": len(self._processed_run_ids),
            "revisions_tracked": len(self._revisions),
        }


# =============================================================================
# Module-level singleton
# =============================================================================

_default_store: Optional[TwinStore] = None
_store_lock = threading.Lock()


def get_default_store() -> TwinStore:
    """Return the process-wide singleton TwinStore.

    Thread-safe lazy initialization.  Prefers the PostgreSQL-backed
    ``PostgresTwinStore`` when the PdM persistence layer is available;
    falls back to the plain in-memory ``TwinStore`` otherwise.
    """
    global _default_store
    if _default_store is None:
        with _store_lock:
            if _default_store is None:
                try:
                    from loweconex_platform.digital_twins.postgres_store import (
                        get_persistent_store,
                    )
                    _default_store = get_persistent_store()
                except Exception:
                    _default_store = TwinStore()
                    logger.info("Default TwinStore singleton created (in-memory)")
    return _default_store
