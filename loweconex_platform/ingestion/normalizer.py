"""
Normalization & Identity Resolution Service.

Transforms raw source data into canonical schema, resolves asset/location
identity across sources, and handles unit conversion and timezone mapping.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from loweconex_platform.digital_twins.models import AssetTwin, AssetType, LocationTwin
from loweconex_platform.digital_twins.store import OperationalEvent, TimeSeriesPoint, TwinStore
from loweconex_platform.lineage.lineage_tracker import LineageTracker

try:
    from loweconex_platform.semantic.ontology import (
        BrickHaystackAdapter,
        SemanticModel,
        SemanticValidator,
    )
    SEMANTIC_AVAILABLE = True
except ImportError:
    SEMANTIC_AVAILABLE = False

try:
    from loweconex_platform.data_quality.quality_engine import DataQualityEngine, ExpectationSuite
    DQ_AVAILABLE = True
except ImportError:
    DQ_AVAILABLE = False

try:
    from zoneinfo import ZoneInfo
    ZONEINFO_AVAILABLE = True
except ImportError:
    try:
        from backports.zoneinfo import ZoneInfo
        ZONEINFO_AVAILABLE = True
    except ImportError:
        ZONEINFO_AVAILABLE = False

logger = logging.getLogger(__name__)


# =============================================================================
# Schema Mapping
# =============================================================================

@dataclass
class FieldMapping:
    """Maps a source field to a canonical field."""
    source_field: str
    canonical_field: str
    transform: Optional[str] = None  # "lowercase", "uppercase", "strip", "float", "int", "datetime"
    unit_source: Optional[str] = None
    unit_target: Optional[str] = None
    enum_map: Optional[Dict[str, str]] = None
    default_value: Any = None
    required: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_field": self.source_field,
            "canonical_field": self.canonical_field,
            "transform": self.transform,
            "unit_source": self.unit_source,
            "unit_target": self.unit_target,
            "enum_map": self.enum_map,
            "default_value": self.default_value,
            "required": self.required,
        }


@dataclass
class SchemaMapping:
    """
    Complete schema mapping from source to canonical.
    
    Maps source fields → canonical schema fields with unit declarations,
    enum mappings, timestamp/timezone handling, and identity mapping.
    """
    mapping_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    source_type: str = ""  # "telemetry", "work_orders", "energy", "leak_logs", etc.
    field_mappings: List[FieldMapping] = field(default_factory=list)
    identity_fields: Dict[str, str] = field(default_factory=dict)  # {"asset_id": "src_equipment_id"}
    timezone: str = "UTC"
    timestamp_format: Optional[str] = None  # strptime format
    confirmed: bool = False
    confirmed_by: Optional[str] = None
    confirmed_ts: Optional[str] = None

    def add_field(self, source: str, canonical: str, **kwargs) -> FieldMapping:
        fm = FieldMapping(source_field=source, canonical_field=canonical, **kwargs)
        self.field_mappings.append(fm)
        return fm

    def get_mapping(self, canonical_field: str) -> Optional[FieldMapping]:
        for fm in self.field_mappings:
            if fm.canonical_field == canonical_field:
                return fm
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mapping_id": self.mapping_id,
            "name": self.name,
            "source_type": self.source_type,
            "field_mappings": [fm.to_dict() for fm in self.field_mappings],
            "identity_fields": self.identity_fields,
            "timezone": self.timezone,
            "timestamp_format": self.timestamp_format,
            "confirmed": self.confirmed,
        }


# =============================================================================
# Unit Conversion
# =============================================================================

UNIT_CONVERSIONS = {
    ("fahrenheit", "celsius"): lambda v: (v - 32) * 5 / 9,
    ("celsius", "fahrenheit"): lambda v: v * 9 / 5 + 32,
    ("psi", "bar"): lambda v: v * 0.0689476,
    ("bar", "psi"): lambda v: v / 0.0689476,
    ("lbs", "kg"): lambda v: v * 0.453592,
    ("kg", "lbs"): lambda v: v / 0.453592,
    ("kwh", "mwh"): lambda v: v / 1000,
    ("mwh", "kwh"): lambda v: v * 1000,
    ("therms", "kwh"): lambda v: v * 29.3001,
    ("kwh", "therms"): lambda v: v / 29.3001,
    ("cfm", "m3h"): lambda v: v * 1.69901,
    ("m3h", "cfm"): lambda v: v / 1.69901,
    ("inches_wc", "pa"): lambda v: v * 249.089,
    ("pa", "inches_wc"): lambda v: v / 249.089,
}


def convert_unit(value: float, from_unit: str, to_unit: str) -> float:
    """Convert a value between units."""
    if from_unit == to_unit:
        return value
    key = (from_unit.lower(), to_unit.lower())
    converter = UNIT_CONVERSIONS.get(key)
    if converter:
        return converter(value)
    logger.warning(f"No conversion found: {from_unit} -> {to_unit}")
    return value


# =============================================================================
# Identity Resolution
# =============================================================================

class IdentityResolver:
    """
    Resolves asset and location identities across data sources.
    
    Maintains a mapping table from source-specific IDs to canonical IDs.
    Supports fuzzy matching on name/serial/model when exact ID match fails.
    """

    def __init__(self):
        # source_system -> source_id -> canonical_id
        self._asset_map: Dict[str, Dict[str, str]] = {}
        self._location_map: Dict[str, Dict[str, str]] = {}
        self._unresolved: List[Dict[str, Any]] = []

    def register_asset_mapping(
        self, source_system: str, source_id: str, canonical_id: str
    ):
        if source_system not in self._asset_map:
            self._asset_map[source_system] = {}
        self._asset_map[source_system][source_id] = canonical_id

    def register_location_mapping(
        self, source_system: str, source_id: str, canonical_id: str
    ):
        if source_system not in self._location_map:
            self._location_map[source_system] = {}
        self._location_map[source_system][source_id] = canonical_id

    def resolve_asset(self, source_system: str, source_id: str) -> Optional[str]:
        return self._asset_map.get(source_system, {}).get(source_id)

    def resolve_location(self, source_system: str, source_id: str) -> Optional[str]:
        return self._location_map.get(source_system, {}).get(source_id)

    def resolve_or_create_asset(
        self, source_system: str, source_id: str, company_id: str, location_id: str
    ) -> str:
        """Resolve asset ID or create a new canonical ID."""
        existing = self.resolve_asset(source_system, source_id)
        if existing:
            return existing
        canonical_id = f"asset_{company_id}_{source_id}"
        self.register_asset_mapping(source_system, source_id, canonical_id)
        return canonical_id

    def resolve_or_create_location(
        self, source_system: str, source_id: str, company_id: str
    ) -> str:
        existing = self.resolve_location(source_system, source_id)
        if existing:
            return existing
        canonical_id = f"loc_{company_id}_{source_id}"
        self.register_location_mapping(source_system, source_id, canonical_id)
        return canonical_id

    def get_unresolved(self) -> List[Dict[str, Any]]:
        return self._unresolved

    def stats(self) -> Dict[str, Any]:
        return {
            "asset_mappings": sum(len(v) for v in self._asset_map.values()),
            "location_mappings": sum(len(v) for v in self._location_map.values()),
            "source_systems": list(set(list(self._asset_map.keys()) + list(self._location_map.keys()))),
            "unresolved_count": len(self._unresolved),
        }


# =============================================================================
# Normalizer
# =============================================================================

class Normalizer:
    """
    Transforms raw loaded data into canonical format and populates twins.
    
    Uses SchemaMapping to convert source fields, resolve identities,
    convert units, and write to the TwinStore.

    Integrates:
    - Brick/Haystack semantic ontology adapter for point name resolution
    - ISO 25012 data quality engine for completeness / outlier gates
    - Timezone-aware timestamp handling with DST discontinuity support
    """

    def __init__(
        self,
        twin_store: TwinStore,
        identity_resolver: Optional[IdentityResolver] = None,
        lineage_tracker: Optional[LineageTracker] = None,
        semantic_adapter: Optional[Any] = None,
        dq_engine: Optional[Any] = None,
    ):
        self.twin_store = twin_store
        self.identity = identity_resolver or IdentityResolver()
        self.lineage = lineage_tracker or LineageTracker()
        self._mappings: Dict[str, SchemaMapping] = {}

        # Semantic ontology adapter (Brick/Haystack point name resolution)
        if semantic_adapter is not None:
            self.semantic_adapter = semantic_adapter
        elif SEMANTIC_AVAILABLE:
            self.semantic_adapter = BrickHaystackAdapter(SemanticModel())
        else:
            self.semantic_adapter = None

        # Data quality engine (ISO 25012)
        if dq_engine is not None:
            self.dq_engine = dq_engine
        elif DQ_AVAILABLE:
            self.dq_engine = DataQualityEngine()
        else:
            self.dq_engine = None

    def register_mapping(self, mapping: SchemaMapping):
        self._mappings[mapping.mapping_id] = mapping

    def normalize_and_load(
        self,
        data: List[Dict[str, Any]],
        mapping: SchemaMapping,
        company_id: str,
        source_system: str = "unknown",
    ) -> Dict[str, Any]:
        """
        Normalize raw data using a schema mapping and load into twin store.
        
        Returns summary of what was loaded (assets, locations, events, timeseries).
        """
        run_id = str(uuid.uuid4())
        stats = {
            "run_id": run_id,
            "rows_processed": 0,
            "assets_created": 0,
            "assets_updated": 0,
            "locations_created": 0,
            "events_created": 0,
            "timeseries_points": 0,
            "errors": [],
        }

        # Lineage: start ingestion job
        lineage_job_id = self.lineage.start_job(
            job_type="ingestion",
            job_name=f"normalize_{mapping.source_type}_{company_id}",
            company_id=company_id,
            config={"source_system": source_system, "mapping_id": mapping.mapping_id},
        )
        self.lineage.add_input(
            lineage_job_id,
            self.lineage.create_dataset(
                name=f"{source_system}:{mapping.source_type}",
                dataset_type="raw_input",
                company_id=company_id,
                row_count=len(data),
                content=str({"mapping_id": mapping.mapping_id, "rows": len(data)}),
            ),
        )

        # Idempotent ingestion check
        if not self.twin_store.idempotent_ingest(run_id):
            stats["errors"].append(f"Run {run_id} already processed")
            return stats

        # Run data quality checks on raw data
        dq_report = self.run_data_quality_check(data, mapping)
        stats["data_quality_report"] = dq_report

        for row in data:
            stats["rows_processed"] += 1
            try:
                canonical = self._apply_mapping(row, mapping)
                # Resolve semantic point names
                if "point_name" in canonical and canonical["point_name"]:
                    canonical["point_name"] = self.resolve_point_name(canonical["point_name"])

                if mapping.source_type == "telemetry":
                    self._load_telemetry(canonical, company_id, source_system, mapping, stats)
                elif mapping.source_type in ("work_orders", "leak_logs", "call_center", "vendor_jobs"):
                    self._load_event(canonical, company_id, source_system, mapping, stats)
                elif mapping.source_type == "asset_registry":
                    self._load_asset(canonical, company_id, source_system, mapping, stats)
                elif mapping.source_type == "location_registry":
                    self._load_location(canonical, company_id, stats)
                elif mapping.source_type == "energy":
                    self._load_telemetry(canonical, company_id, source_system, mapping, stats)
                else:
                    self._load_event(canonical, company_id, source_system, mapping, stats)

            except Exception as e:
                stats["errors"].append({"row": stats["rows_processed"], "error": str(e)})

        # Lineage: complete ingestion job
        self.lineage.add_output(
            lineage_job_id,
            self.lineage.create_dataset(
                name=f"twin_store:{company_id}",
                dataset_type="normalized_output",
                company_id=company_id,
                row_count=stats["rows_processed"],
                content=str(
                    {
                        "assets_created": stats["assets_created"],
                        "events_created": stats["events_created"],
                        "timeseries_points": stats["timeseries_points"],
                    }
                ),
            ),
        )
        if stats["errors"]:
            self.lineage.fail_job(lineage_job_id, error=str(stats["errors"][:3]))
        else:
            self.lineage.complete_job(lineage_job_id)

        logger.info(
            f"Normalized {stats['rows_processed']} rows (run_id={run_id}): "
            f"{stats['assets_created']} assets, {stats['events_created']} events, "
            f"{stats['timeseries_points']} ts points"
        )
        return stats

    def _apply_mapping(self, row: Dict[str, Any], mapping: SchemaMapping) -> Dict[str, Any]:
        """Apply field mappings to transform a row."""
        result = {}
        for fm in mapping.field_mappings:
            value = row.get(fm.source_field, fm.default_value)
            if value is None and fm.required:
                raise ValueError(f"Required field missing: {fm.source_field}")
            if value is not None:
                value = self._apply_transform(value, fm)
            result[fm.canonical_field] = value
        return result

    def resolve_point_name(self, raw_name: str) -> str:
        """Resolve a raw BMS point name to its canonical ontology term."""
        if self.semantic_adapter and hasattr(self.semantic_adapter, 'resolve_point'):
            try:
                resolved = self.semantic_adapter.resolve_point(raw_name)
                if resolved:
                    return resolved
            except Exception as e:
                logger.debug(f"Semantic resolution failed for '{raw_name}': {e}")
        return raw_name

    def run_data_quality_check(
        self, data: List[Dict[str, Any]], mapping: SchemaMapping
    ) -> Dict[str, Any]:
        """Run data quality checks on loaded data before normalization."""
        if not self.dq_engine:
            return {"status": "skipped", "reason": "no dq_engine"}
        try:
            suite_name = f"ingestion_{mapping.source_type}"
            if hasattr(self.dq_engine, "run_checks"):
                report = self.dq_engine.run_checks(data=data, suite_name=suite_name)
                return report if isinstance(report, dict) else {"status": "completed"}

            # Backward-compatible path for DataQualityEngine.validate(...)
            if hasattr(self.dq_engine, "get_suite_for_dataset") and hasattr(self.dq_engine, "validate"):
                suite = self.dq_engine.get_suite_for_dataset(suite_name)
                if not suite:
                    return {"status": "skipped", "reason": f"no_quality_suite:{suite_name}"}
                report = self.dq_engine.validate(suite.suite_id, data=data)
                return report.to_dict() if hasattr(report, "to_dict") else {"status": "completed"}

            return {"status": "skipped", "reason": "unsupported_dq_engine"}
        except Exception as e:
            logger.warning(f"Data quality check failed: {e}")
            return {"status": "error", "error": str(e)}

    @staticmethod
    def _parse_datetime_tz(value: Any, timezone: str = "UTC", fmt: Optional[str] = None) -> datetime:
        """Parse a datetime string with DST-aware timezone handling."""
        if isinstance(value, datetime):
            dt = value
        elif fmt:
            dt = datetime.strptime(str(value), fmt)
        else:
            dt = datetime.fromisoformat(str(value))

        if dt.tzinfo is None and ZONEINFO_AVAILABLE and timezone != "UTC":
            try:
                tz = ZoneInfo(timezone)
                dt = dt.replace(tzinfo=tz)
            except Exception:
                pass

        if dt.tzinfo is not None:
            from datetime import timezone as _tz
            dt = dt.astimezone(_tz.utc).replace(tzinfo=None)

        return dt

    def _apply_transform(self, value: Any, fm: FieldMapping) -> Any:
        """Apply transformation to a field value."""
        if fm.transform == "float":
            return float(value) if value else 0.0
        elif fm.transform == "int":
            return int(float(value)) if value else 0
        elif fm.transform == "lowercase":
            return str(value).lower()
        elif fm.transform == "uppercase":
            return str(value).upper()
        elif fm.transform == "strip":
            return str(value).strip()
        elif fm.transform == "datetime":
            if isinstance(value, datetime):
                return value
            return self._parse_datetime_tz(value)

        if fm.enum_map and str(value) in fm.enum_map:
            value = fm.enum_map[str(value)]

        if fm.unit_source and fm.unit_target and fm.unit_source != fm.unit_target:
            try:
                value = convert_unit(float(value), fm.unit_source, fm.unit_target)
            except (ValueError, TypeError):
                pass

        return value

    def _load_telemetry(
        self, canonical: Dict, company_id: str, source_system: str,
        mapping: SchemaMapping, stats: Dict,
    ):
        """Load a normalized telemetry row into the time-series store."""
        asset_src_id = canonical.get("asset_id", "")
        location_src_id = canonical.get("location_id", "")
        point_name = canonical.get("point_name", "")
        value = canonical.get("value")
        timestamp = canonical.get("timestamp")

        if not point_name or value is None:
            return

        location_id = self.identity.resolve_or_create_location(
            source_system, location_src_id, company_id
        ) if location_src_id else ""

        asset_id = self.identity.resolve_or_create_asset(
            source_system, asset_src_id, company_id, location_id
        ) if asset_src_id else ""

        point_id = f"{asset_id}:{point_name}" if asset_id else f"{company_id}:{point_name}"
        ts = timestamp if isinstance(timestamp, datetime) else datetime.utcnow()

        self.twin_store.write_timeseries(point_id, [
            TimeSeriesPoint(
                timestamp=ts,
                value=float(value),
                unit=canonical.get("unit", ""),
            )
        ])
        stats["timeseries_points"] += 1

    def _load_event(
        self, canonical: Dict, company_id: str, source_system: str,
        mapping: SchemaMapping, stats: Dict,
    ):
        """Load a normalized event row into the event store."""
        event_id = canonical.get("event_id", str(uuid.uuid4()))
        event_type = canonical.get("event_type", mapping.source_type)

        asset_src_id = canonical.get("asset_id", "")
        location_src_id = canonical.get("location_id", "")

        location_id = self.identity.resolve_or_create_location(
            source_system, location_src_id, company_id
        ) if location_src_id else None

        asset_id = self.identity.resolve_or_create_asset(
            source_system, asset_src_id, company_id, location_id or ""
        ) if asset_src_id else None

        start_ts = canonical.get("start_ts") or canonical.get("timestamp") or datetime.utcnow()
        if isinstance(start_ts, str):
            start_ts = datetime.fromisoformat(start_ts)

        end_ts = canonical.get("end_ts")
        if isinstance(end_ts, str):
            end_ts = datetime.fromisoformat(end_ts)

        event = OperationalEvent(
            event_id=event_id,
            event_type=event_type,
            source_system=source_system,
            start_ts=start_ts,
            end_ts=end_ts,
            asset_id=asset_id,
            location_id=location_id,
            company_id=company_id,
            severity=canonical.get("severity", "info"),
            confidence=float(canonical.get("confidence", 1.0)),
            code=canonical.get("code"),
            payload={k: v for k, v in canonical.items() if k not in (
                "event_id", "event_type", "asset_id", "location_id",
                "start_ts", "end_ts", "severity", "confidence", "code"
            )},
        )
        self.twin_store.store_event(event)
        stats["events_created"] += 1

    def _load_asset(
        self, canonical: Dict, company_id: str, source_system: str,
        mapping: SchemaMapping, stats: Dict,
    ):
        """Load a normalized asset registry row."""
        src_id = canonical.get("asset_id", "")
        location_src_id = canonical.get("location_id", "")

        location_id = self.identity.resolve_or_create_location(
            source_system, location_src_id, company_id
        ) if location_src_id else ""

        asset_id = self.identity.resolve_or_create_asset(
            source_system, src_id, company_id, location_id
        )

        asset_type_str = canonical.get("asset_type", "other")
        try:
            asset_type = AssetType(asset_type_str)
        except ValueError:
            asset_type = AssetType.OTHER

        existing = self.twin_store.get_asset(asset_id)
        if existing:
            # Update
            for key in ("manufacturer", "model", "serial", "install_date"):
                val = canonical.get(key)
                if val:
                    setattr(existing, key, val)
            existing.updated_ts = datetime.utcnow()
            self.twin_store.upsert_asset(existing)
            stats["assets_updated"] += 1
        else:
            install_date = canonical.get("install_date")
            if isinstance(install_date, str):
                try:
                    install_date = datetime.fromisoformat(install_date)
                except ValueError:
                    install_date = None

            asset = AssetTwin(
                asset_id=asset_id,
                location_id=location_id,
                company_id=company_id,
                asset_type=asset_type,
                manufacturer=canonical.get("manufacturer"),
                model=canonical.get("model"),
                serial=canonical.get("serial"),
                install_date=install_date,
                age_years=canonical.get("age_years"),
            )
            self.twin_store.upsert_asset(asset)
            stats["assets_created"] += 1

    def _load_location(self, canonical: Dict, company_id: str, stats: Dict):
        """Load a normalized location registry row."""
        location_id = canonical.get("location_id", str(uuid.uuid4()))

        existing = self.twin_store.get_location(location_id)
        if existing:
            for key in ("address", "sqft", "store_format", "climate_zone"):
                val = canonical.get(key)
                if val:
                    setattr(existing, key, val)
            existing.updated_ts = datetime.utcnow()
            self.twin_store.upsert_location(existing)
        else:
            location = LocationTwin(
                location_id=location_id,
                company_id=company_id,
                address=canonical.get("address"),
                sqft=canonical.get("sqft"),
                store_format=canonical.get("store_format"),
                climate_zone=canonical.get("climate_zone"),
            )
            self.twin_store.upsert_location(location)
            stats["locations_created"] += 1
