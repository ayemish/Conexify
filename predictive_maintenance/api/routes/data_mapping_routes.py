"""
Data Mapping API Routes — /api/v1/mappings/*

CRUD for schema mapping configurations used by the data normalizer.
Allows users to configure how source CSV/API columns map to canonical fields.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

mapping_router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────

class FieldMappingItem(BaseModel):
    source_field: str
    target_field: str
    transform: str = ""
    default_value: str = ""


class SchemaMappingCreate(BaseModel):
    site_id: str = "default"
    name: str
    description: str = ""
    source_type: str = "csv"
    source_columns: List[str] = Field(default_factory=list)
    field_mappings: List[FieldMappingItem] = Field(default_factory=list)
    validation_rules: List[Dict[str, Any]] = Field(default_factory=list)


class SchemaMappingResponse(BaseModel):
    mapping_id: str
    site_id: str
    name: str
    description: str = ""
    source_type: str = "csv"
    source_columns: List[str] = Field(default_factory=list)
    field_mappings: List[Dict[str, Any]] = Field(default_factory=list)
    validation_rules: List[Dict[str, Any]] = Field(default_factory=list)
    is_active: bool = True
    records_processed: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CanonicalFieldsResponse(BaseModel):
    """Available target fields for mapping."""
    fields: List[Dict[str, str]]


# ── Canonical fields (target schema) ─────────────────────────────────

CANONICAL_FIELDS = [
    {"name": "timestamp", "type": "datetime", "required": True, "description": "Observation timestamp"},
    {"name": "asset_id", "type": "string", "required": True, "description": "Unique asset identifier"},
    {"name": "site_id", "type": "string", "required": False, "description": "Site/location identifier"},
    {"name": "suction_pressure", "type": "float", "required": False, "description": "Suction pressure (psig)"},
    {"name": "discharge_pressure", "type": "float", "required": False, "description": "Discharge pressure (psig)"},
    {"name": "suction_line_temp", "type": "float", "required": False, "description": "Suction line temperature (°F)"},
    {"name": "discharge_temp", "type": "float", "required": False, "description": "Discharge temperature (°F)"},
    {"name": "supply_air_temp", "type": "float", "required": False, "description": "Supply air temperature (°F)"},
    {"name": "return_air_temp", "type": "float", "required": False, "description": "Return air temperature (°F)"},
    {"name": "ambient_temp", "type": "float", "required": False, "description": "Outdoor ambient temperature (°F)"},
    {"name": "zone_temp", "type": "float", "required": False, "description": "Zone/space temperature (°F)"},
    {"name": "compressor_current", "type": "float", "required": False, "description": "Compressor current (amps)"},
    {"name": "compressor_power", "type": "float", "required": False, "description": "Compressor power (kW)"},
    {"name": "superheat", "type": "float", "required": False, "description": "Superheat (°F)"},
    {"name": "subcool", "type": "float", "required": False, "description": "Subcooling (°F)"},
    {"name": "compressor_on", "type": "boolean", "required": False, "description": "Compressor running status"},
    {"name": "setpoint", "type": "float", "required": False, "description": "Temperature setpoint (°F)"},
]


# ── Routes ───────────────────────────────────────────────────────────

@mapping_router.get("/canonical-fields", response_model=CanonicalFieldsResponse)
async def get_canonical_fields():
    """Get the list of canonical target fields available for mapping."""
    return CanonicalFieldsResponse(fields=CANONICAL_FIELDS)


@mapping_router.get("/", response_model=List[SchemaMappingResponse])
async def list_mappings(site_id: str = Query(default="default")):
    """List all schema mappings for a site."""
    try:
        from ...persistence.database import get_session
        from ...persistence.kpi_repository import SchemaMappingRepository

        with get_session() as session:
            repo = SchemaMappingRepository(session)
            mappings = repo.get_for_site(site_id)
            return [
                SchemaMappingResponse(
                    mapping_id=m.mapping_id,
                    site_id=m.site_id,
                    name=m.name,
                    description=m.description or "",
                    source_type=m.source_type or "csv",
                    source_columns=m.source_columns or [],
                    field_mappings=m.field_mappings or [],
                    validation_rules=m.validation_rules or [],
                    is_active=m.is_active,
                    records_processed=m.records_processed or 0,
                    created_at=m.created_at,
                    updated_at=m.updated_at,
                )
                for m in mappings
            ]
    except Exception as e:
        logger.warning("Schema mapping list failed: %s", e)
        return []


@mapping_router.post("/", response_model=SchemaMappingResponse)
async def create_mapping(req: SchemaMappingCreate):
    """Create a new schema mapping configuration."""
    try:
        from ...persistence.database import get_session
        from ...persistence.kpi_repository import SchemaMappingRepository

        with get_session() as session:
            repo = SchemaMappingRepository(session)
            mapping = repo.create(
                site_id=req.site_id,
                name=req.name,
                description=req.description,
                source_type=req.source_type,
                source_columns=req.source_columns,
                field_mappings=[fm.dict() for fm in req.field_mappings],
                validation_rules=req.validation_rules,
            )
            session.commit()
            return SchemaMappingResponse(
                mapping_id=mapping.mapping_id,
                site_id=mapping.site_id,
                name=mapping.name,
                description=mapping.description or "",
                source_type=mapping.source_type or "csv",
                source_columns=mapping.source_columns or [],
                field_mappings=mapping.field_mappings or [],
                validation_rules=mapping.validation_rules or [],
                is_active=mapping.is_active,
                records_processed=0,
                created_at=mapping.created_at,
                updated_at=mapping.updated_at,
            )
    except Exception as e:
        logger.error("Schema mapping creation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@mapping_router.put("/{mapping_id}", response_model=SchemaMappingResponse)
async def update_mapping(mapping_id: str, req: SchemaMappingCreate):
    """Update an existing schema mapping."""
    try:
        from ...persistence.database import get_session
        from ...persistence.kpi_repository import SchemaMappingRepository

        with get_session() as session:
            repo = SchemaMappingRepository(session)
            mapping = repo.update(
                mapping_id,
                name=req.name,
                description=req.description,
                source_type=req.source_type,
                source_columns=req.source_columns,
                field_mappings=[fm.dict() for fm in req.field_mappings],
                validation_rules=req.validation_rules,
            )
            if not mapping:
                raise HTTPException(status_code=404, detail="Mapping not found")
            session.commit()
            return SchemaMappingResponse(
                mapping_id=mapping.mapping_id,
                site_id=mapping.site_id,
                name=mapping.name,
                description=mapping.description or "",
                source_type=mapping.source_type or "csv",
                source_columns=mapping.source_columns or [],
                field_mappings=mapping.field_mappings or [],
                validation_rules=mapping.validation_rules or [],
                is_active=mapping.is_active,
                records_processed=mapping.records_processed or 0,
                created_at=mapping.created_at,
                updated_at=mapping.updated_at,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Schema mapping update failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@mapping_router.delete("/{mapping_id}")
async def delete_mapping(mapping_id: str):
    """Deactivate a schema mapping."""
    try:
        from ...persistence.database import get_session
        from ...persistence.kpi_repository import SchemaMappingRepository

        with get_session() as session:
            repo = SchemaMappingRepository(session)
            repo.delete(mapping_id)
            session.commit()
            return {"status": "deleted", "mapping_id": mapping_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@mapping_router.post("/auto-detect")
async def auto_detect_mappings(columns: List[str]):
    """Auto-detect field mappings from source column names."""
    ALIAS_MAP = {
        "timestamp": ["timestamp", "time", "datetime", "ts", "date_time"],
        "asset_id": ["asset_id", "assetid", "asset", "unit_id", "equipment_id", "device_id"],
        "site_id": ["site_id", "siteid", "site", "location", "store_id"],
        "suction_pressure": ["suction_pressure", "suctionpressure", "sp"],
        "discharge_pressure": ["discharge_pressure", "dischargepressure", "dp"],
        "suction_line_temp": ["suction_line_temp", "suction_temp", "suctiontemp"],
        "discharge_temp": ["discharge_temp", "dischargetemp"],
        "supply_air_temp": ["supply_air_temp", "supplyairtemp", "sat"],
        "return_air_temp": ["return_air_temp", "returnairtemp", "rat"],
        "ambient_temp": ["ambient_temp", "ambienttemp", "oat", "outdoor_temp"],
        "zone_temp": ["zone_temp", "zonetemp", "space_temp", "spacetemp"],
        "compressor_current": ["compressor_current", "compressorcurrent"],
        "compressor_power": ["compressor_power", "compressorpower"],
        "superheat": ["superheat", "sh"],
        "subcool": ["subcool", "sc", "subcooling"],
        "compressor_on": ["compressor_on", "compressoron", "compressor_status"],
        "setpoint": ["setpoint", "set_point", "temperature_setpoint"],
    }

    suggestions = []
    for col in columns:
        col_lower = col.strip().lower().replace(" ", "_")
        matched = False
        for target, aliases in ALIAS_MAP.items():
            if col_lower in aliases:
                suggestions.append({
                    "source_field": col,
                    "target_field": target,
                    "confidence": 1.0,
                    "transform": "",
                })
                matched = True
                break
        if not matched:
            suggestions.append({
                "source_field": col,
                "target_field": "",
                "confidence": 0.0,
                "transform": "",
            })

    return {"suggestions": suggestions}
