"""
Ingestion Connector API Routes

Exposes the Loweconex ingestion connectors via REST endpoints:
- GET  /api/v1/ingestion/connectors — List available connector types
- POST /api/v1/ingestion/connectors/test — Test a connector config
- POST /api/v1/ingestion/connectors/preview — Preview data from a connector
- POST /api/v1/ingestion/connectors/load — Load data through a connector
- GET  /api/v1/ingestion/streaming/status — Streaming ingest status
- POST /api/v1/ingestion/streaming/start — Start streaming listeners
- POST /api/v1/ingestion/streaming/stop — Stop streaming listeners
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

ingestion_router = APIRouter()


# ── Request / Response Models ───────────────────────────────────────

class ConnectorConfigRequest(BaseModel):
    connector_type: str = Field(..., description="csv, api, sftp, s3, database")
    name: str = Field(default="", description="Connector display name")
    credentials: Dict[str, str] = Field(default_factory=dict)
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ConnectorTestResponse(BaseModel):
    success: bool
    message: str
    connector_type: str


class ConnectorPreviewResponse(BaseModel):
    connector_name: str
    columns: List[str]
    sample_rows: List[Dict[str, Any]]
    row_count: int
    errors: List[str]


class ConnectorLoadResponse(BaseModel):
    connector_name: str
    rows_loaded: int
    rows_rejected: int
    columns: List[str]
    errors: List[str]
    warnings: List[str]
    load_ts: str


class StreamingConfigRequest(BaseModel):
    protocol: str = Field(..., description="mqtt or bacnet")
    mqtt_broker: str = Field(default="localhost")
    mqtt_port: int = Field(default=1883)
    mqtt_topics: List[str] = Field(default_factory=lambda: ["pdm/telemetry/#"])
    bacnet_device_ids: List[int] = Field(default_factory=list)
    bacnet_poll_interval_seconds: float = Field(default=30.0)


# ── Endpoints ───────────────────────────────────────────────────────

@ingestion_router.get("/connectors")
async def list_connector_types():
    """List available connector types."""
    try:
        from loweconex_platform.ingestion.connectors import ConnectorFactory
        return {
            "connector_types": ConnectorFactory.available_types(),
            "count": len(ConnectorFactory.available_types()),
        }
    except ImportError:
        raise HTTPException(status_code=501, detail="Ingestion connectors not available")


@ingestion_router.post("/connectors/test", response_model=ConnectorTestResponse)
async def test_connector(req: ConnectorConfigRequest):
    """Test a connector configuration without loading data."""
    try:
        from loweconex_platform.ingestion.connectors import ConnectorConfig, ConnectorFactory

        config = ConnectorConfig(
            connector_type=req.connector_type,
            name=req.name,
            credentials=req.credentials,
            parameters=req.parameters,
        )
        connector = ConnectorFactory.create(config)
        success, message = connector.test_connection()
        return ConnectorTestResponse(
            success=success,
            message=message,
            connector_type=req.connector_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImportError:
        raise HTTPException(status_code=501, detail="Ingestion connectors not available")


@ingestion_router.post("/connectors/preview", response_model=ConnectorPreviewResponse)
async def preview_connector(req: ConnectorConfigRequest):
    """Preview sample data from a connector without full load."""
    try:
        from loweconex_platform.ingestion.connectors import ConnectorConfig, ConnectorFactory

        config = ConnectorConfig(
            connector_type=req.connector_type,
            name=req.name,
            credentials=req.credentials,
            parameters=req.parameters,
        )
        connector = ConnectorFactory.create(config)
        result = connector.preview(rows=5)
        return ConnectorPreviewResponse(
            connector_name=result.connector_name,
            columns=result.columns,
            sample_rows=result.sample_rows,
            row_count=result.rows_loaded,
            errors=result.errors,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImportError:
        raise HTTPException(status_code=501, detail="Ingestion connectors not available")


@ingestion_router.post("/connectors/load", response_model=ConnectorLoadResponse)
async def load_from_connector(req: ConnectorConfigRequest):
    """Load data from a connector into the TwinStore and normalizer."""
    try:
        from loweconex_platform.ingestion.connectors import ConnectorConfig, ConnectorFactory
        from loweconex_platform.ingestion.normalizer import Normalizer, SchemaMapping
        from loweconex_platform.digital_twins.store import get_default_store

        config = ConnectorConfig(
            connector_type=req.connector_type,
            name=req.name,
            credentials=req.credentials,
            parameters=req.parameters,
        )
        connector = ConnectorFactory.create(config)
        result = connector.load()

        if result.errors:
            return ConnectorLoadResponse(
                connector_name=result.connector_name,
                rows_loaded=0,
                rows_rejected=0,
                columns=result.columns,
                errors=result.errors,
                warnings=result.warnings,
                load_ts=result.load_ts,
            )

        # Normalize and ingest into TwinStore
        twin_store = get_default_store()
        normalizer = Normalizer(twin_store)

        if result.data:
            try:
                # Build a permissive auto-mapping for connector-driven ingest.
                source_columns = list(result.data[0].keys()) if result.data else []
                col_lookup = {c.lower().strip(): c for c in source_columns}
                all_cols = set(col_lookup.keys())

                if {"event_type", "work_order_id"} & all_cols:
                    source_type = "work_orders"
                elif {"asset_type", "manufacturer", "serial"} & all_cols:
                    source_type = "asset_registry"
                elif {"address", "sqft", "climate_zone"} & all_cols:
                    source_type = "location_registry"
                elif {"energy_kwh", "kwh"} & all_cols:
                    source_type = "energy"
                else:
                    source_type = "telemetry"

                alias_map = {
                    "timestamp": ["timestamp", "time", "datetime", "ts"],
                    "asset_id": ["asset_id", "asset", "equipment_id", "device_id", "unit_id"],
                    "location_id": ["location_id", "site_id", "site", "store_id", "location"],
                    "point_name": ["point_name", "metric", "sensor", "point", "tag"],
                    "value": ["value", "reading", "measurement", "val"],
                    "unit": ["unit", "uom"],
                    "event_type": ["event_type", "type"],
                    "severity": ["severity", "priority"],
                    "confidence": ["confidence", "score"],
                    "asset_type": ["asset_type", "equipment_type", "type"],
                    "manufacturer": ["manufacturer", "make", "vendor"],
                    "model": ["model", "model_number"],
                    "serial": ["serial", "serial_number"],
                    "address": ["address", "site_address"],
                    "sqft": ["sqft", "square_feet", "area_sqft"],
                    "store_format": ["store_format", "format"],
                    "climate_zone": ["climate_zone", "climate"],
                }

                mapping = SchemaMapping(
                    name=f"auto_{req.name or req.connector_type}",
                    source_type=source_type,
                    timezone="UTC",
                )
                for canonical_field, aliases in alias_map.items():
                    source_field = None
                    for alias in aliases:
                        if alias in col_lookup:
                            source_field = col_lookup[alias]
                            break
                    if source_field:
                        transform = None
                        if canonical_field == "timestamp":
                            transform = "datetime"
                        elif canonical_field in {
                            "value",
                            "confidence",
                            "sqft",
                        } or canonical_field.endswith(("_temp", "_pressure")):
                            transform = "float"
                        mapping.add_field(
                            source=source_field,
                            canonical=canonical_field,
                            transform=transform,
                        )

                # Identity fallback mapping hints
                if mapping.get_mapping("asset_id"):
                    mapping.identity_fields["asset_id"] = mapping.get_mapping("asset_id").source_field
                if mapping.get_mapping("location_id"):
                    mapping.identity_fields["location_id"] = mapping.get_mapping("location_id").source_field

                company_id = (
                    req.parameters.get("company_id")
                    or req.parameters.get("site_id")
                    or "default"
                )
                ingest_stats = normalizer.normalize_and_load(
                    data=result.data,
                    mapping=mapping,
                    company_id=str(company_id),
                    source_system=req.name or req.connector_type or "connector",
                )
                if ingest_stats.get("errors"):
                    result.warnings.extend(
                        [f"Normalization issue: {err}" for err in ingest_stats["errors"][:5]]
                    )
            except Exception as e:
                result.warnings.append(f"Normalization partial failure: {e}")

        return ConnectorLoadResponse(
            connector_name=result.connector_name,
            rows_loaded=result.rows_loaded,
            rows_rejected=result.rows_rejected,
            columns=result.columns,
            errors=result.errors,
            warnings=result.warnings,
            load_ts=result.load_ts,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImportError:
        raise HTTPException(status_code=501, detail="Ingestion connectors not available")


# ── Streaming Ingest Endpoints ──────────────────────────────────────

@ingestion_router.get("/streaming/status")
async def streaming_status():
    """Get the status of the streaming ingest service."""
    try:
        from loweconex_platform.ingestion.streaming import get_ingest_service
        svc = get_ingest_service()
        return svc.get_status()
    except ImportError:
        return {"active_protocols": [], "messages_received": 0, "status": "not_available"}


@ingestion_router.post("/streaming/start")
async def start_streaming(req: StreamingConfigRequest):
    """Start a streaming listener (MQTT or BACnet)."""
    try:
        from loweconex_platform.ingestion.streaming import (
            StreamConfig,
            get_ingest_service,
        )

        config = StreamConfig(
            protocol=req.protocol,
            mqtt_broker=req.mqtt_broker,
            mqtt_port=req.mqtt_port,
            mqtt_topics=req.mqtt_topics,
            bacnet_device_ids=req.bacnet_device_ids,
            bacnet_poll_interval_seconds=req.bacnet_poll_interval_seconds,
        )
        svc = get_ingest_service()
        svc.configs.append(config)
        svc.start()
        return {"status": "started", "protocol": req.protocol}
    except ImportError:
        raise HTTPException(status_code=501, detail="Streaming ingest not available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@ingestion_router.post("/streaming/stop")
async def stop_streaming():
    """Stop all streaming listeners."""
    try:
        from loweconex_platform.ingestion.streaming import get_ingest_service
        svc = get_ingest_service()
        svc.stop()
        return {"status": "stopped"}
    except ImportError:
        raise HTTPException(status_code=501, detail="Streaming ingest not available")
