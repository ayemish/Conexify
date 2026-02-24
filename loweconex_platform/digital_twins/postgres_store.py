"""
PostgreSQL-backed TwinStore — write-through persistence layer.

Extends the in-memory TwinStore with automatic write-through to PostgreSQL
using the PdM persistence layer. On startup, hydrates the in-memory cache
from the database so callers get the same fast in-memory reads while
guaranteeing durability across restarts.

Persisted entity types:
- Assets (via pdm_assets + pdm_twin_assets JSON sidecar)
- Locations (via pdm_twin_locations)
- Estates (via pdm_twin_estates)
- Events (via pdm_alerts)
- Time-series (via pdm_twin_timeseries)
- Relationships (via pdm_twin_relationships)

Usage:
    from loweconex_platform.digital_twins.postgres_store import get_persistent_store
    store = get_persistent_store()
"""

from __future__ import annotations

from collections import defaultdict
import json
import logging
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from loweconex_platform.digital_twins.models import (
    AgentAction,
    AssetTwin,
    AssetType,
    ComponentTwin,
    ControllerTwin,
    DataSourceRegistration,
    EstateTwin,
    LocationTwin,
    SensorPointTwin,
    ServiceProviderTwin,
    TechnicianProfile,
    TwinRelationship,
    RelationshipType,
    WorkOrderTwin,
)
from loweconex_platform.digital_twins.store import (
    OperationalEvent,
    TimeSeriesPoint,
    TwinStore,
)

logger = logging.getLogger(__name__)

# ── Availability ────────────────────────────────────────────────────

_DB_AVAILABLE = False
_ORM_MODELS = {}
try:
    from predictive_maintenance.persistence.database import get_session, Base
    from predictive_maintenance.persistence.models import AssetModel
    from sqlalchemy import (
        Column, String, Float, Boolean, DateTime, Integer, Text, Index,
    )

    # Use JSONB when available (PostgreSQL), fall back to Text for SQLite
    try:
        from sqlalchemy.dialects.postgresql import JSONB
    except ImportError:
        from sqlalchemy import Text as JSONB

    _DB_AVAILABLE = True
except ImportError:
    logger.info("PdM persistence not available — PostgresTwinStore disabled")

# ── Sidecar ORM tables for full twin persistence ───────────────────

if _DB_AVAILABLE:
    from predictive_maintenance.persistence.database import Base as _Base

    class TwinAssetSidecarModel(_Base):
        """JSON sidecar for full AssetTwin state beyond what pdm_assets stores."""
        __tablename__ = "pdm_twin_assets"
        __table_args__ = {"extend_existing": True}
        asset_id = Column(String(100), primary_key=True)
        twin_json = Column(JSONB, nullable=False)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class TwinLocationModel(_Base):
        """Persisted LocationTwin."""
        __tablename__ = "pdm_twin_locations"
        __table_args__ = {"extend_existing": True}
        location_id = Column(String(100), primary_key=True)
        company_id = Column(String(100), nullable=False, index=True)
        twin_json = Column(JSONB, nullable=False)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class TwinEstateModel(_Base):
        """Persisted EstateTwin."""
        __tablename__ = "pdm_twin_estates"
        __table_args__ = {"extend_existing": True}
        company_id = Column(String(100), primary_key=True)
        twin_json = Column(JSONB, nullable=False)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class TwinRelationshipModel(_Base):
        """Persisted TwinRelationship edge."""
        __tablename__ = "pdm_twin_relationships"
        __table_args__ = (
            Index("ix_twin_rel_source", "source_id"),
            Index("ix_twin_rel_target", "target_id"),
            {"extend_existing": True},
        )
        id = Column(Integer, primary_key=True, autoincrement=True)
        source_id = Column(String(100), nullable=False)
        target_id = Column(String(100), nullable=False)
        relationship_type = Column(String(50), nullable=False)
        properties_json = Column(JSONB, default=dict)
        created_at = Column(DateTime, default=datetime.utcnow)

    class TwinTimeseriesModel(_Base):
        """Persisted time-series points (batch-flushed)."""
        __tablename__ = "pdm_twin_timeseries"
        __table_args__ = (
            Index("ix_twin_ts_point_ts", "point_id", "timestamp"),
            {"extend_existing": True},
        )
        id = Column(Integer, primary_key=True, autoincrement=True)
        point_id = Column(String(200), nullable=False)
        timestamp = Column(DateTime, nullable=False)
        value = Column(Float, nullable=False)
        quality = Column(Float, default=1.0)
        unit = Column(String(30), default="")

    class TwinControllerModel(_Base):
        """Persisted ControllerTwin."""
        __tablename__ = "pdm_twin_controllers"
        __table_args__ = {"extend_existing": True}
        controller_id = Column(String(100), primary_key=True)
        location_id = Column(String(100), nullable=False, index=True)
        company_id = Column(String(100), nullable=False, index=True)
        twin_json = Column(JSONB, nullable=False)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class TwinSensorPointModel(_Base):
        """Persisted SensorPointTwin."""
        __tablename__ = "pdm_twin_sensor_points"
        __table_args__ = {"extend_existing": True}
        point_id = Column(String(200), primary_key=True)
        asset_id = Column(String(100), nullable=False, index=True)
        twin_json = Column(JSONB, nullable=False)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class TwinComponentModel(_Base):
        """Persisted ComponentTwin."""
        __tablename__ = "pdm_twin_components"
        __table_args__ = {"extend_existing": True}
        component_id = Column(String(100), primary_key=True)
        parent_asset_id = Column(String(100), nullable=False, index=True)
        twin_json = Column(JSONB, nullable=False)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class TwinDataSourceModel(_Base):
        """Persisted DataSourceRegistration."""
        __tablename__ = "pdm_twin_data_sources"
        __table_args__ = {"extend_existing": True}
        source_id = Column(String(100), primary_key=True)
        company_id = Column(String(100), nullable=False, index=True)
        location_id = Column(String(100), nullable=True, index=True)
        twin_json = Column(JSONB, nullable=False)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class TwinWorkOrderModel(_Base):
        """Persisted WorkOrderTwin."""
        __tablename__ = "pdm_twin_work_orders"
        __table_args__ = {"extend_existing": True}
        wo_id = Column(String(100), primary_key=True)
        asset_id = Column(String(100), nullable=False, index=True)
        location_id = Column(String(100), nullable=False, index=True)
        company_id = Column(String(100), nullable=False, index=True)
        twin_json = Column(JSONB, nullable=False)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class TwinServiceProviderModel(_Base):
        """Persisted ServiceProviderTwin."""
        __tablename__ = "pdm_twin_service_providers"
        __table_args__ = {"extend_existing": True}
        provider_id = Column(String(100), primary_key=True)
        company_id = Column(String(100), nullable=False, index=True)
        twin_json = Column(JSONB, nullable=False)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class TwinTechnicianModel(_Base):
        """Persisted TechnicianProfile."""
        __tablename__ = "pdm_twin_technicians"
        __table_args__ = {"extend_existing": True}
        technician_id = Column(String(100), primary_key=True)
        provider_id = Column(String(100), nullable=False, index=True)
        twin_json = Column(JSONB, nullable=False)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class TwinAgentActionModel(_Base):
        """Persisted AgentAction."""
        __tablename__ = "pdm_twin_agent_actions"
        __table_args__ = {"extend_existing": True}
        action_id = Column(String(100), primary_key=True)
        company_id = Column(String(100), nullable=False, index=True)
        asset_id = Column(String(100), nullable=True, index=True)
        twin_json = Column(JSONB, nullable=False)
        created_at = Column(DateTime, default=datetime.utcnow)

    _ORM_MODELS = {
        "asset_sidecar": TwinAssetSidecarModel,
        "location": TwinLocationModel,
        "estate": TwinEstateModel,
        "relationship": TwinRelationshipModel,
        "timeseries": TwinTimeseriesModel,
        "controller": TwinControllerModel,
        "sensor_point": TwinSensorPointModel,
        "component": TwinComponentModel,
        "data_source": TwinDataSourceModel,
        "work_order": TwinWorkOrderModel,
        "service_provider": TwinServiceProviderModel,
        "technician": TwinTechnicianModel,
        "agent_action": TwinAgentActionModel,
    }


class PostgresTwinStore(TwinStore):
    """TwinStore with write-through to PostgreSQL.

    - **Reads** are served from the in-memory parent class (fast).
    - **Writes** (upsert_asset, upsert_location, store_event, etc.)
      are forwarded to the parent AND persisted to PostgreSQL.
    - **Startup** hydrates the in-memory cache from the database.
    """

    def __init__(self, hydrate: bool = True):
        super().__init__()
        self._db_available = _DB_AVAILABLE
        self.degraded_mode: bool = False
        self.hydration_warnings: List[Dict[str, Any]] = []
        self._ensure_tables()
        if hydrate and self._db_available:
            self._hydrate_from_db()

    def _record_nonfatal_hydration_error(
        self,
        code: str,
        message: str,
        context: Dict[str, Any],
        error: Optional[Exception] = None,
    ) -> None:
        warning = {
            "code": code,
            "message": message,
            "context": context,
            "error": str(error) if error else None,
        }
        self.hydration_warnings.append(warning)
        self.degraded_mode = True
        logger.warning("%s | context=%s | error=%s", message, context, error)

    # ── Schema bootstrap ────────────────────────────────────────────

    def _ensure_tables(self):
        """Create sidecar tables if they don't exist yet."""
        if not self._db_available:
            return
        try:
            from predictive_maintenance.persistence.database import get_engine
            engine = get_engine()
            for model in _ORM_MODELS.values():
                model.__table__.create(bind=engine, checkfirst=True)
        except Exception as e:
            logger.debug("Twin table bootstrap (non-fatal): %s", e)

    # ── Hydration ───────────────────────────────────────────────────

    def _hydrate_from_db(self):
        """Load existing twins from PostgreSQL into the in-memory cache."""
        a_count = self._hydrate_assets()
        l_count = self._hydrate_locations()
        e_count = self._hydrate_estates()
        r_count = self._hydrate_relationships()
        ts_count = self._hydrate_timeseries()
        ev_count = self._hydrate_events()
        c_count = self._hydrate_controllers()
        sp_count = self._hydrate_sensor_points()
        comp_count = self._hydrate_components()
        ds_count = self._hydrate_data_sources()
        wo_count = self._hydrate_work_orders()
        prov_count = self._hydrate_service_providers()
        tech_count = self._hydrate_technicians()
        aa_count = self._hydrate_agent_actions()
        logger.info(
            "PostgresTwinStore hydrated: %d assets, %d locations, %d estates, "
            "%d relationships, %d ts points, %d events, %d controllers, "
            "%d sensor_points, %d components, %d data_sources, %d work_orders, "
            "%d providers, %d technicians, %d agent_actions",
            a_count, l_count, e_count, r_count, ts_count, ev_count,
            c_count, sp_count, comp_count, ds_count, wo_count,
            prov_count, tech_count, aa_count,
        )

    def _hydrate_assets(self) -> int:
        count = 0
        try:
            with get_session() as session:
                rows = session.query(_ORM_MODELS["asset_sidecar"]).all()
                for row in rows:
                    try:
                        data = row.twin_json if isinstance(row.twin_json, dict) else json.loads(row.twin_json)
                        twin = AssetTwin.from_dict(data)
                        super().upsert_asset(twin)
                        count += 1
                    except Exception as exc:
                        self._record_nonfatal_hydration_error(
                            "ASSET_HYDRATE_ROW_FAILED",
                            "Failed hydrating asset sidecar row; row skipped.",
                            {"asset_id": getattr(row, "asset_id", "")},
                            exc,
                        )
        except Exception as e:
            logger.debug("Asset hydration: %s", e)
            # Fallback: hydrate from pdm_assets table
            try:
                with get_session() as session:
                    all_assets = session.query(AssetModel).filter(
                        AssetModel.is_active == True
                    ).all()
                    for row in all_assets:
                        try:
                            twin = AssetTwin(
                                asset_id=row.asset_id,
                                location_id=row.site_id,
                                company_id=row.site_id,
                                asset_type=AssetType(row.asset_type or "other"),
                            )
                            super().upsert_asset(twin)
                            count += 1
                        except Exception as exc:
                            self._record_nonfatal_hydration_error(
                                "ASSET_FALLBACK_ROW_FAILED",
                                "Failed hydrating fallback asset row; row skipped.",
                                {"asset_id": getattr(row, "asset_id", "")},
                                exc,
                            )
            except Exception as exc:
                self._record_nonfatal_hydration_error(
                    "ASSET_FALLBACK_QUERY_FAILED",
                    "Fallback asset hydration query failed.",
                    {"asset_id": ""},
                    exc,
                )
        return count

    def _hydrate_locations(self) -> int:
        count = 0
        try:
            with get_session() as session:
                rows = session.query(_ORM_MODELS["location"]).all()
                for row in rows:
                    try:
                        data = row.twin_json if isinstance(row.twin_json, dict) else json.loads(row.twin_json)
                        twin = LocationTwin.from_dict(data)
                        super().upsert_location(twin)
                        count += 1
                    except Exception as exc:
                        self._record_nonfatal_hydration_error(
                            "LOCATION_HYDRATE_ROW_FAILED",
                            "Failed hydrating location row; row skipped.",
                            {"location_id": getattr(row, "location_id", "")},
                            exc,
                        )
        except Exception as e:
            logger.debug("Location hydration: %s", e)
        return count

    def _hydrate_estates(self) -> int:
        count = 0
        try:
            with get_session() as session:
                rows = session.query(_ORM_MODELS["estate"]).all()
                for row in rows:
                    try:
                        data = row.twin_json if isinstance(row.twin_json, dict) else json.loads(row.twin_json)
                        twin = EstateTwin.from_dict(data)
                        super().upsert_estate(twin)
                        count += 1
                    except Exception as exc:
                        self._record_nonfatal_hydration_error(
                            "ESTATE_HYDRATE_ROW_FAILED",
                            "Failed hydrating estate row; row skipped.",
                            {"company_id": getattr(row, "company_id", "")},
                            exc,
                        )
        except Exception as e:
            logger.debug("Estate hydration: %s", e)
        return count

    def _hydrate_relationships(self) -> int:
        count = 0
        try:
            with get_session() as session:
                rows = session.query(_ORM_MODELS["relationship"]).all()
                for row in rows:
                    try:
                        rel = TwinRelationship(
                            source_id=row.source_id,
                            target_id=row.target_id,
                            relationship_type=RelationshipType(row.relationship_type),
                            properties=row.properties_json if isinstance(row.properties_json, dict) else json.loads(row.properties_json or "{}"),
                        )
                        super().add_relationship(rel)
                        count += 1
                    except Exception as exc:
                        self._record_nonfatal_hydration_error(
                            "RELATIONSHIP_HYDRATE_ROW_FAILED",
                            "Failed hydrating relationship row; row skipped.",
                            {
                                "source_id": getattr(row, "source_id", ""),
                                "target_id": getattr(row, "target_id", ""),
                            },
                            exc,
                        )
        except Exception as e:
            logger.debug("Relationship hydration: %s", e)
        return count

    def _hydrate_timeseries(self) -> int:
        """Hydrate persisted time-series rows into the in-memory cache."""
        count = 0
        try:
            with get_session() as session:
                Model = _ORM_MODELS["timeseries"]
                rows = (
                    session.query(Model)
                    .order_by(Model.timestamp.asc())
                    .limit(50000)
                    .all()
                )
                grouped: Dict[str, List[TimeSeriesPoint]] = defaultdict(list)
                for row in rows:
                    grouped[row.point_id].append(
                        TimeSeriesPoint(
                            timestamp=row.timestamp,
                            value=float(row.value or 0.0),
                            quality=float(row.quality or 1.0),
                            unit=row.unit or "",
                        )
                    )
                for point_id, points in grouped.items():
                    super().write_timeseries(point_id, points)
                    count += len(points)
        except Exception as e:
            logger.debug("Timeseries hydration: %s", e)
        return count

    def _hydrate_events(self) -> int:
        """Hydrate operational events from persisted alerts."""
        count = 0
        try:
            from predictive_maintenance.persistence.models import AlertModel
            with get_session() as session:
                rows = (
                    session.query(AlertModel)
                    .order_by(AlertModel.created_at.desc())
                    .limit(5000)
                    .all()
                )
                for row in rows:
                    event = OperationalEvent(
                        event_id=f"alert_{row.alert_id}",
                        event_type=row.alert_type or "alert",
                        source_system="pdm_alerts",
                        start_ts=row.created_at or datetime.utcnow(),
                        asset_id=row.asset_id,
                        severity=row.severity or "info",
                        confidence=float(row.confidence or 1.0),
                        code=row.primary_fault,
                        ack_status=(
                            "acked"
                            if str(row.status or "").lower() in {"resolved", "closed", "acknowledged"}
                            else "unacked"
                        ),
                    )
                    super().store_event(event)
                    count += 1
        except Exception as e:
            logger.debug("Event hydration: %s", e)
        return count

    def _hydrate_controllers(self) -> int:
        count = 0
        try:
            with get_session() as session:
                rows = session.query(_ORM_MODELS["controller"]).all()
                for row in rows:
                    try:
                        data = row.twin_json if isinstance(row.twin_json, dict) else json.loads(row.twin_json)
                        twin = ControllerTwin.from_dict(data)
                        super().upsert_controller(twin)
                        count += 1
                    except Exception as exc:
                        self._record_nonfatal_hydration_error(
                            "CONTROLLER_HYDRATE_ROW_FAILED",
                            "Failed hydrating controller row; row skipped.",
                            {"controller_id": getattr(row, "controller_id", "")},
                            exc,
                        )
        except Exception as e:
            logger.debug("Controller hydration: %s", e)
        return count

    def _hydrate_sensor_points(self) -> int:
        count = 0
        try:
            with get_session() as session:
                rows = session.query(_ORM_MODELS["sensor_point"]).all()
                for row in rows:
                    try:
                        data = row.twin_json if isinstance(row.twin_json, dict) else json.loads(row.twin_json)
                        twin = SensorPointTwin.from_dict(data)
                        super().upsert_sensor_point(twin)
                        count += 1
                    except Exception as exc:
                        self._record_nonfatal_hydration_error(
                            "SENSOR_POINT_HYDRATE_ROW_FAILED",
                            "Failed hydrating sensor point row; row skipped.",
                            {"asset_id": getattr(row, "asset_id", "")},
                            exc,
                        )
        except Exception as e:
            logger.debug("SensorPoint hydration: %s", e)
        return count

    def _hydrate_components(self) -> int:
        count = 0
        try:
            with get_session() as session:
                rows = session.query(_ORM_MODELS["component"]).all()
                for row in rows:
                    try:
                        data = row.twin_json if isinstance(row.twin_json, dict) else json.loads(row.twin_json)
                        twin = ComponentTwin.from_dict(data)
                        super().upsert_component(twin)
                        count += 1
                    except Exception as exc:
                        self._record_nonfatal_hydration_error(
                            "COMPONENT_HYDRATE_ROW_FAILED",
                            "Failed hydrating component row; row skipped.",
                            {"parent_asset_id": getattr(row, "parent_asset_id", "")},
                            exc,
                        )
        except Exception as e:
            logger.debug("Component hydration: %s", e)
        return count

    def _hydrate_data_sources(self) -> int:
        count = 0
        try:
            with get_session() as session:
                rows = session.query(_ORM_MODELS["data_source"]).all()
                for row in rows:
                    try:
                        data = row.twin_json if isinstance(row.twin_json, dict) else json.loads(row.twin_json)
                        twin = DataSourceRegistration.from_dict(data)
                        super().upsert_data_source(twin)
                        count += 1
                    except Exception as exc:
                        self._record_nonfatal_hydration_error(
                            "DATA_SOURCE_HYDRATE_ROW_FAILED",
                            "Failed hydrating data source row; row skipped.",
                            {"source_id": getattr(row, "source_id", "")},
                            exc,
                        )
        except Exception as e:
            logger.debug("DataSource hydration: %s", e)
        return count

    def _hydrate_work_orders(self) -> int:
        count = 0
        try:
            with get_session() as session:
                rows = session.query(_ORM_MODELS["work_order"]).all()
                for row in rows:
                    try:
                        data = row.twin_json if isinstance(row.twin_json, dict) else json.loads(row.twin_json)
                        twin = WorkOrderTwin.from_dict(data)
                        super().upsert_work_order(twin)
                        count += 1
                    except Exception as exc:
                        self._record_nonfatal_hydration_error(
                            "WORK_ORDER_HYDRATE_ROW_FAILED",
                            "Failed hydrating work order row; row skipped.",
                            {"asset_id": getattr(row, "asset_id", "")},
                            exc,
                        )
        except Exception as e:
            logger.debug("WorkOrder hydration: %s", e)
        return count

    def _hydrate_service_providers(self) -> int:
        count = 0
        try:
            with get_session() as session:
                rows = session.query(_ORM_MODELS["service_provider"]).all()
                for row in rows:
                    try:
                        data = row.twin_json if isinstance(row.twin_json, dict) else json.loads(row.twin_json)
                        twin = ServiceProviderTwin.from_dict(data)
                        super().upsert_service_provider(twin)
                        count += 1
                    except Exception as exc:
                        self._record_nonfatal_hydration_error(
                            "PROVIDER_HYDRATE_ROW_FAILED",
                            "Failed hydrating service provider row; row skipped.",
                            {"provider_id": getattr(row, "provider_id", "")},
                            exc,
                        )
        except Exception as e:
            logger.debug("ServiceProvider hydration: %s", e)
        return count

    def _hydrate_technicians(self) -> int:
        count = 0
        try:
            with get_session() as session:
                rows = session.query(_ORM_MODELS["technician"]).all()
                for row in rows:
                    try:
                        data = row.twin_json if isinstance(row.twin_json, dict) else json.loads(row.twin_json)
                        twin = TechnicianProfile.from_dict(data)
                        super().upsert_technician(twin)
                        count += 1
                    except Exception as exc:
                        self._record_nonfatal_hydration_error(
                            "TECHNICIAN_HYDRATE_ROW_FAILED",
                            "Failed hydrating technician row; row skipped.",
                            {"technician_id": getattr(row, "technician_id", "")},
                            exc,
                        )
        except Exception as e:
            logger.debug("Technician hydration: %s", e)
        return count

    def _hydrate_agent_actions(self) -> int:
        count = 0
        try:
            with get_session() as session:
                rows = session.query(_ORM_MODELS["agent_action"]).all()
                for row in rows:
                    try:
                        data = row.twin_json if isinstance(row.twin_json, dict) else json.loads(row.twin_json)
                        action = AgentAction.from_dict(data)
                        super().store_agent_action(action)
                        count += 1
                    except Exception as exc:
                        self._record_nonfatal_hydration_error(
                            "AGENT_ACTION_HYDRATE_ROW_FAILED",
                            "Failed hydrating agent action row; row skipped.",
                            {"asset_id": getattr(row, "asset_id", "")},
                            exc,
                        )
        except Exception as e:
            logger.debug("AgentAction hydration: %s", e)
        return count

    # ── Write-through overrides ─────────────────────────────────────

    def upsert_asset(self, asset: AssetTwin) -> AssetTwin:
        result = super().upsert_asset(asset)
        if self._db_available:
            self._persist_asset(asset)
        return result

    def upsert_location(self, location: LocationTwin) -> LocationTwin:
        result = super().upsert_location(location)
        if self._db_available:
            self._persist_location(location)
        return result

    def upsert_estate(self, estate: EstateTwin) -> EstateTwin:
        result = super().upsert_estate(estate)
        if self._db_available:
            self._persist_estate(estate)
        return result

    def delete_asset(self, asset_id: str) -> bool:
        deleted = super().delete_asset(asset_id)
        if deleted and self._db_available:
            self._deactivate_asset_db(asset_id)
        return deleted

    def store_event(self, event: OperationalEvent, run_id: Optional[str] = None) -> bool:
        stored = super().store_event(event, run_id)
        if stored and self._db_available:
            self._persist_event(event)
        return stored

    def add_relationship(self, rel: TwinRelationship):
        super().add_relationship(rel)
        if self._db_available:
            self._persist_relationship(rel)

    def write_timeseries(self, point_id: str, points: List[TimeSeriesPoint]):
        super().write_timeseries(point_id, points)
        if self._db_available:
            self._persist_timeseries(point_id, points)

    def patch_twin(self, entity_type: str, entity_id: str, patch: Dict[str, Any]) -> bool:
        patched = super().patch_twin(entity_type, entity_id, patch)
        if patched and self._db_available:
            if entity_type == "asset":
                asset = self.get_asset(entity_id)
                if asset:
                    self._persist_asset(asset)
            elif entity_type == "location":
                loc = self.get_location(entity_id)
                if loc:
                    self._persist_location(loc)
            elif entity_type == "estate":
                est = self.get_estate(entity_id)
                if est:
                    self._persist_estate(est)
        return patched

    # ── DB write helpers ────────────────────────────────────────────

    def _persist_asset(self, asset: AssetTwin):
        try:
            with get_session() as session:
                Model = _ORM_MODELS["asset_sidecar"]
                twin_data = asset.to_dict()
                existing = session.query(Model).filter(Model.asset_id == asset.asset_id).first()
                if existing:
                    existing.twin_json = twin_data
                    existing.updated_at = datetime.utcnow()
                else:
                    session.add(Model(asset_id=asset.asset_id, twin_json=twin_data))
                session.commit()
        except Exception as e:
            logger.debug("Asset persist failed for %s: %s", asset.asset_id, e)

        # Also keep pdm_assets in sync
        try:
            from predictive_maintenance.persistence.repositories import AssetRepository
            with get_session() as session:
                repo = AssetRepository(session)
                existing = repo.get_by_id(asset.asset_id)
                if existing:
                    existing.site_id = asset.location_id
                    existing.asset_type = (
                        asset.asset_type.value
                        if hasattr(asset.asset_type, "value")
                        else str(asset.asset_type)
                    )
                    existing.is_active = True
                else:
                    repo.create(
                        asset_id=asset.asset_id,
                        site_id=asset.location_id,
                        asset_type=(
                            asset.asset_type.value
                            if hasattr(asset.asset_type, "value")
                            else str(asset.asset_type)
                        ),
                    )
                session.commit()
        except Exception as e:
            logger.debug("Asset pdm_assets sync failed for %s: %s", asset.asset_id, e)

    def _persist_location(self, location: LocationTwin):
        try:
            with get_session() as session:
                Model = _ORM_MODELS["location"]
                twin_data = location.to_dict()
                existing = session.query(Model).filter(Model.location_id == location.location_id).first()
                if existing:
                    existing.company_id = location.company_id
                    existing.twin_json = twin_data
                    existing.updated_at = datetime.utcnow()
                else:
                    session.add(Model(
                        location_id=location.location_id,
                        company_id=location.company_id,
                        twin_json=twin_data,
                    ))
                session.commit()
        except Exception as e:
            logger.debug("Location persist failed for %s: %s", location.location_id, e)

    def _persist_estate(self, estate: EstateTwin):
        try:
            with get_session() as session:
                Model = _ORM_MODELS["estate"]
                twin_data = estate.to_dict()
                existing = session.query(Model).filter(Model.company_id == estate.company_id).first()
                if existing:
                    existing.twin_json = twin_data
                    existing.updated_at = datetime.utcnow()
                else:
                    session.add(Model(company_id=estate.company_id, twin_json=twin_data))
                session.commit()
        except Exception as e:
            logger.debug("Estate persist failed for %s: %s", estate.company_id, e)

    def _persist_relationship(self, rel: TwinRelationship):
        try:
            with get_session() as session:
                Model = _ORM_MODELS["relationship"]
                session.add(Model(
                    source_id=rel.source_id,
                    target_id=rel.target_id,
                    relationship_type=rel.relationship_type.value,
                    properties_json=rel.properties,
                ))
                session.commit()
        except Exception as e:
            logger.debug("Relationship persist failed: %s", e)

    def _persist_timeseries(self, point_id: str, points: List[TimeSeriesPoint]):
        try:
            with get_session() as session:
                Model = _ORM_MODELS["timeseries"]
                for pt in points:
                    session.add(Model(
                        point_id=point_id,
                        timestamp=pt.timestamp,
                        value=pt.value,
                        quality=pt.quality,
                        unit=pt.unit,
                    ))
                session.commit()
        except Exception as e:
            logger.debug("Timeseries persist failed for %s: %s", point_id, e)

    def upsert_controller(self, controller: ControllerTwin) -> ControllerTwin:
        result = super().upsert_controller(controller)
        if self._db_available:
            self._persist_json_twin("controller", "controller_id", controller.controller_id, controller.to_dict(),
                                   extra={"location_id": controller.location_id, "company_id": controller.company_id})
        return result

    def upsert_sensor_point(self, point: SensorPointTwin) -> SensorPointTwin:
        result = super().upsert_sensor_point(point)
        if self._db_available:
            self._persist_json_twin("sensor_point", "point_id", point.point_id, point.to_dict(),
                                   extra={"asset_id": point.asset_id})
        return result

    def upsert_component(self, component: ComponentTwin) -> ComponentTwin:
        result = super().upsert_component(component)
        if self._db_available:
            self._persist_json_twin("component", "component_id", component.component_id, component.to_dict(),
                                   extra={"parent_asset_id": component.parent_asset_id})
        return result

    def upsert_data_source(self, source: DataSourceRegistration) -> DataSourceRegistration:
        result = super().upsert_data_source(source)
        if self._db_available:
            self._persist_json_twin("data_source", "source_id", source.source_id, source.to_dict(),
                                   extra={"company_id": source.company_id, "location_id": source.location_id})
        return result

    def upsert_work_order(self, wo: WorkOrderTwin) -> WorkOrderTwin:
        result = super().upsert_work_order(wo)
        if self._db_available:
            self._persist_json_twin("work_order", "wo_id", wo.wo_id, wo.to_dict(),
                                   extra={"asset_id": wo.asset_id, "location_id": wo.location_id, "company_id": wo.company_id})
        return result

    def upsert_service_provider(self, provider: ServiceProviderTwin) -> ServiceProviderTwin:
        result = super().upsert_service_provider(provider)
        if self._db_available:
            self._persist_json_twin("service_provider", "provider_id", provider.provider_id, provider.to_dict(),
                                   extra={"company_id": provider.company_id})
        return result

    def upsert_technician(self, tech: TechnicianProfile) -> TechnicianProfile:
        result = super().upsert_technician(tech)
        if self._db_available:
            self._persist_json_twin("technician", "technician_id", tech.technician_id, tech.to_dict(),
                                   extra={"provider_id": tech.provider_id})
        return result

    def store_agent_action(self, action: AgentAction) -> AgentAction:
        result = super().store_agent_action(action)
        if self._db_available:
            self._persist_json_twin("agent_action", "action_id", action.action_id, action.to_dict(),
                                   extra={"company_id": action.company_id, "asset_id": action.asset_id})
        return result

    def _deactivate_asset_db(self, asset_id: str):
        try:
            with get_session() as session:
                Model = _ORM_MODELS["asset_sidecar"]
                session.query(Model).filter(Model.asset_id == asset_id).delete()
                session.commit()
        except Exception as e:
            logger.debug("Asset sidecar delete failed for %s: %s", asset_id, e)
        try:
            from predictive_maintenance.persistence.repositories import AssetRepository
            with get_session() as session:
                repo = AssetRepository(session)
                repo.deactivate(asset_id)
                session.commit()
        except Exception as e:
            logger.debug("Asset deactivate failed for %s: %s", asset_id, e)

    def _persist_json_twin(self, model_key: str, pk_field: str, pk_value: str,
                           twin_data: Dict[str, Any], extra: Optional[Dict[str, Any]] = None):
        """Generic JSON sidecar persist for new twin entity types."""
        try:
            with get_session() as session:
                Model = _ORM_MODELS[model_key]
                existing = session.query(Model).filter(getattr(Model, pk_field) == pk_value).first()
                if existing:
                    existing.twin_json = twin_data
                    if hasattr(existing, "updated_at"):
                        existing.updated_at = datetime.utcnow()
                    if extra:
                        for k, v in extra.items():
                            if hasattr(existing, k):
                                setattr(existing, k, v)
                else:
                    kwargs = {pk_field: pk_value, "twin_json": twin_data}
                    if extra:
                        kwargs.update(extra)
                    session.add(Model(**kwargs))
                session.commit()
        except Exception as e:
            logger.debug("%s persist failed for %s: %s", model_key, pk_value, e)

    def _persist_event(self, event: OperationalEvent):
        """Persist an operational event as an alert in the PdM persistence layer."""
        try:
            from predictive_maintenance.persistence.models import AlertModel
            with get_session() as session:
                alert = AlertModel(
                    asset_id=event.asset_id or "",
                    alert_type=event.event_type,
                    severity=event.severity,
                    primary_fault=event.code,
                    confidence=event.confidence,
                    status="active" if event.ack_status == "unacked" else "resolved",
                )
                session.add(alert)
                session.commit()
        except Exception as e:
            logger.debug("Event persist failed for %s: %s", event.event_id, e)


# ── Module-level singleton ──────────────────────────────────────────

_persistent_store: Optional[PostgresTwinStore] = None
_persistent_lock = threading.Lock()


def get_persistent_store() -> TwinStore:
    """Return a PostgreSQL-backed TwinStore singleton.

    Falls back to the plain in-memory TwinStore if PostgreSQL is not
    available, ensuring the system always starts.
    """
    global _persistent_store
    if _persistent_store is None:
        with _persistent_lock:
            if _persistent_store is None:
                if _DB_AVAILABLE:
                    _persistent_store = PostgresTwinStore(hydrate=True)
                    logger.info("PostgresTwinStore singleton created (DB-backed)")
                else:
                    from loweconex_platform.digital_twins.store import get_default_store
                    return get_default_store()
    return _persistent_store
