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
    AgentAction,
    AssetTwin,
    ComponentTwin,
    ControllerTwin,
    DataSourceRegistration,
    EstateTwin,
    KPIRollup,
    LocationTwin,
    SensorPointTwin,
    ServiceProviderTwin,
    TechnicianProfile,
    TwinRelationship,
    WorkOrderTwin,
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
        self._controllers: Dict[str, ControllerTwin] = {}
        self._sensor_points: Dict[str, SensorPointTwin] = {}
        self._components: Dict[str, ComponentTwin] = {}
        self._data_sources: Dict[str, DataSourceRegistration] = {}
        self._work_orders: Dict[str, WorkOrderTwin] = {}
        self._service_providers: Dict[str, ServiceProviderTwin] = {}
        self._technicians: Dict[str, TechnicianProfile] = {}
        self._agent_actions: Dict[str, AgentAction] = {}
        # Relationships
        self._relationships: List[TwinRelationship] = []
        # Time-series: {point_id: [TimeSeriesPoint]}
        self._timeseries: Dict[str, List[TimeSeriesPoint]] = defaultdict(list)
        # Events: {event_id: OperationalEvent}
        self._events: Dict[str, OperationalEvent] = {}
        # Index: company -> location -> asset
        self._company_locations: Dict[str, List[str]] = defaultdict(list)
        self._location_assets: Dict[str, List[str]] = defaultdict(list)
        # Index: new entity cross-references
        self._location_controllers: Dict[str, List[str]] = defaultdict(list)
        self._controller_assets: Dict[str, List[str]] = defaultdict(list)
        self._asset_components: Dict[str, List[str]] = defaultdict(list)
        self._asset_sensor_points: Dict[str, List[str]] = defaultdict(list)
        self._asset_work_orders: Dict[str, List[str]] = defaultdict(list)
        self._location_work_orders: Dict[str, List[str]] = defaultdict(list)
        self._asset_agent_actions: Dict[str, List[str]] = defaultdict(list)
        self._location_data_sources: Dict[str, List[str]] = defaultdict(list)
        self._provider_technicians: Dict[str, List[str]] = defaultdict(list)

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
    # Controller CRUD
    # -------------------------------------------------------------------------

    def upsert_controller(self, controller: ControllerTwin) -> ControllerTwin:
        with self._lock:
            controller.updated_ts = datetime.utcnow()
            self._controllers[controller.controller_id] = controller
            if controller.controller_id not in self._location_controllers[controller.location_id]:
                self._location_controllers[controller.location_id].append(controller.controller_id)
            for aid in controller.managed_asset_ids:
                if aid not in self._controller_assets[controller.controller_id]:
                    self._controller_assets[controller.controller_id].append(aid)
            rev = self._bump_revision("controller", controller.controller_id)
            logger.debug(f"Controller {controller.controller_id} upserted (rev={rev})")
            return controller

    def get_controller(self, controller_id: str) -> Optional[ControllerTwin]:
        return self._controllers.get(controller_id)

    def get_controllers_by_location(self, location_id: str) -> List[ControllerTwin]:
        ids = self._location_controllers.get(location_id, [])
        return [self._controllers[c] for c in ids if c in self._controllers]

    def get_controller_assets(self, controller_id: str) -> List[AssetTwin]:
        ids = self._controller_assets.get(controller_id, [])
        return [self._assets[a] for a in ids if a in self._assets]

    def delete_controller(self, controller_id: str) -> bool:
        with self._lock:
            ctrl = self._controllers.pop(controller_id, None)
            if ctrl:
                loc_list = self._location_controllers.get(ctrl.location_id, [])
                if controller_id in loc_list:
                    loc_list.remove(controller_id)
                self._controller_assets.pop(controller_id, None)
                return True
            return False

    # -------------------------------------------------------------------------
    # SensorPoint CRUD
    # -------------------------------------------------------------------------

    def upsert_sensor_point(self, point: SensorPointTwin) -> SensorPointTwin:
        with self._lock:
            point.updated_ts = datetime.utcnow()
            self._sensor_points[point.point_id] = point
            if point.point_id not in self._asset_sensor_points[point.asset_id]:
                self._asset_sensor_points[point.asset_id].append(point.point_id)
            self._bump_revision("sensor_point", point.point_id)
            return point

    def get_sensor_point(self, point_id: str) -> Optional[SensorPointTwin]:
        return self._sensor_points.get(point_id)

    def get_sensor_points_by_asset(self, asset_id: str) -> List[SensorPointTwin]:
        ids = self._asset_sensor_points.get(asset_id, [])
        return [self._sensor_points[p] for p in ids if p in self._sensor_points]

    def delete_sensor_point(self, point_id: str) -> bool:
        with self._lock:
            pt = self._sensor_points.pop(point_id, None)
            if pt:
                lst = self._asset_sensor_points.get(pt.asset_id, [])
                if point_id in lst:
                    lst.remove(point_id)
                return True
            return False

    # -------------------------------------------------------------------------
    # Component CRUD
    # -------------------------------------------------------------------------

    def upsert_component(self, component: ComponentTwin) -> ComponentTwin:
        with self._lock:
            component.updated_ts = datetime.utcnow()
            self._components[component.component_id] = component
            if component.component_id not in self._asset_components[component.parent_asset_id]:
                self._asset_components[component.parent_asset_id].append(component.component_id)
            self._bump_revision("component", component.component_id)
            return component

    def get_component(self, component_id: str) -> Optional[ComponentTwin]:
        return self._components.get(component_id)

    def get_components_by_asset(self, asset_id: str) -> List[ComponentTwin]:
        ids = self._asset_components.get(asset_id, [])
        return [self._components[c] for c in ids if c in self._components]

    def delete_component(self, component_id: str) -> bool:
        with self._lock:
            comp = self._components.pop(component_id, None)
            if comp:
                lst = self._asset_components.get(comp.parent_asset_id, [])
                if component_id in lst:
                    lst.remove(component_id)
                return True
            return False

    # -------------------------------------------------------------------------
    # DataSource CRUD
    # -------------------------------------------------------------------------

    def upsert_data_source(self, source: DataSourceRegistration) -> DataSourceRegistration:
        with self._lock:
            source.updated_ts = datetime.utcnow()
            self._data_sources[source.source_id] = source
            if source.location_id:
                if source.source_id not in self._location_data_sources[source.location_id]:
                    self._location_data_sources[source.location_id].append(source.source_id)
            self._bump_revision("data_source", source.source_id)
            return source

    def get_data_source(self, source_id: str) -> Optional[DataSourceRegistration]:
        return self._data_sources.get(source_id)

    def get_data_sources_by_location(self, location_id: str) -> List[DataSourceRegistration]:
        ids = self._location_data_sources.get(location_id, [])
        return [self._data_sources[s] for s in ids if s in self._data_sources]

    def delete_data_source(self, source_id: str) -> bool:
        with self._lock:
            src = self._data_sources.pop(source_id, None)
            if src and src.location_id:
                lst = self._location_data_sources.get(src.location_id, [])
                if source_id in lst:
                    lst.remove(source_id)
                return True
            return src is not None

    # -------------------------------------------------------------------------
    # WorkOrder CRUD
    # -------------------------------------------------------------------------

    def upsert_work_order(self, wo: WorkOrderTwin) -> WorkOrderTwin:
        with self._lock:
            wo.updated_ts = datetime.utcnow()
            self._work_orders[wo.wo_id] = wo
            if wo.wo_id not in self._asset_work_orders[wo.asset_id]:
                self._asset_work_orders[wo.asset_id].append(wo.wo_id)
            if wo.wo_id not in self._location_work_orders[wo.location_id]:
                self._location_work_orders[wo.location_id].append(wo.wo_id)
            self._bump_revision("work_order", wo.wo_id)
            return wo

    def get_work_order(self, wo_id: str) -> Optional[WorkOrderTwin]:
        return self._work_orders.get(wo_id)

    def get_work_orders_by_asset(self, asset_id: str) -> List[WorkOrderTwin]:
        ids = self._asset_work_orders.get(asset_id, [])
        return [self._work_orders[w] for w in ids if w in self._work_orders]

    def get_work_orders_by_location(self, location_id: str) -> List[WorkOrderTwin]:
        ids = self._location_work_orders.get(location_id, [])
        return [self._work_orders[w] for w in ids if w in self._work_orders]

    def get_open_work_orders_by_location(self, location_id: str) -> List[WorkOrderTwin]:
        return [
            wo for wo in self.get_work_orders_by_location(location_id)
            if wo.status.value in ("draft", "open", "dispatched", "in_progress", "on_hold")
        ]

    def delete_work_order(self, wo_id: str) -> bool:
        with self._lock:
            wo = self._work_orders.pop(wo_id, None)
            if wo:
                for lst in (self._asset_work_orders.get(wo.asset_id, []),
                            self._location_work_orders.get(wo.location_id, [])):
                    if wo_id in lst:
                        lst.remove(wo_id)
                return True
            return False

    # -------------------------------------------------------------------------
    # ServiceProvider CRUD
    # -------------------------------------------------------------------------

    def upsert_service_provider(self, provider: ServiceProviderTwin) -> ServiceProviderTwin:
        with self._lock:
            provider.updated_ts = datetime.utcnow()
            self._service_providers[provider.provider_id] = provider
            self._bump_revision("service_provider", provider.provider_id)
            return provider

    def get_service_provider(self, provider_id: str) -> Optional[ServiceProviderTwin]:
        return self._service_providers.get(provider_id)

    def get_providers_by_company(self, company_id: str) -> List[ServiceProviderTwin]:
        return [p for p in self._service_providers.values() if p.company_id == company_id]

    def get_providers_by_location(self, location_id: str) -> List[ServiceProviderTwin]:
        return [
            p for p in self._service_providers.values()
            if location_id in p.service_regions
        ]

    # -------------------------------------------------------------------------
    # Technician CRUD
    # -------------------------------------------------------------------------

    def upsert_technician(self, tech: TechnicianProfile) -> TechnicianProfile:
        with self._lock:
            tech.updated_ts = datetime.utcnow()
            self._technicians[tech.technician_id] = tech
            if tech.technician_id not in self._provider_technicians[tech.provider_id]:
                self._provider_technicians[tech.provider_id].append(tech.technician_id)
            self._bump_revision("technician", tech.technician_id)
            return tech

    def get_technician(self, technician_id: str) -> Optional[TechnicianProfile]:
        return self._technicians.get(technician_id)

    def get_technicians_by_provider(self, provider_id: str) -> List[TechnicianProfile]:
        ids = self._provider_technicians.get(provider_id, [])
        return [self._technicians[t] for t in ids if t in self._technicians]

    def get_available_technicians(self, location_id: str, trade: Optional[str] = None) -> List[TechnicianProfile]:
        results = [
            t for t in self._technicians.values()
            if t.is_available and location_id in t.assigned_locations
        ]
        if trade:
            results = [t for t in results if trade in t.trades]
        return results

    # -------------------------------------------------------------------------
    # AgentAction CRUD
    # -------------------------------------------------------------------------

    def store_agent_action(self, action: AgentAction) -> AgentAction:
        with self._lock:
            self._agent_actions[action.action_id] = action
            if action.asset_id:
                if action.action_id not in self._asset_agent_actions[action.asset_id]:
                    self._asset_agent_actions[action.asset_id].append(action.action_id)
            self._bump_revision("agent_action", action.action_id)
            return action

    def get_agent_action(self, action_id: str) -> Optional[AgentAction]:
        return self._agent_actions.get(action_id)

    def get_agent_actions_by_asset(self, asset_id: str) -> List[AgentAction]:
        ids = self._asset_agent_actions.get(asset_id, [])
        return [self._agent_actions[a] for a in ids if a in self._agent_actions]

    def get_pending_agent_actions(self, company_id: Optional[str] = None) -> List[AgentAction]:
        actions = [
            a for a in self._agent_actions.values()
            if a.approval_status == "pending"
        ]
        if company_id:
            actions = [a for a in actions if a.company_id == company_id]
        return actions

    # -------------------------------------------------------------------------
    # Stats
    # -------------------------------------------------------------------------

    def stats(self) -> Dict[str, int]:
        return {
            "assets": len(self._assets),
            "locations": len(self._locations),
            "estates": len(self._estates),
            "controllers": len(self._controllers),
            "sensor_points": len(self._sensor_points),
            "components": len(self._components),
            "data_sources": len(self._data_sources),
            "work_orders": len(self._work_orders),
            "service_providers": len(self._service_providers),
            "technicians": len(self._technicians),
            "agent_actions": len(self._agent_actions),
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
