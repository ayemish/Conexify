# Loweconex Data File Normalization & Processing

**Prepared for:** Data Science Team Review  
**Date:** February 20, 2026  
**Version:** 1.0  

---

## Table of Contents

1. [Pipeline Overview](#1-pipeline-overview)
2. [Data Connectors (Ingestion Sources)](#2-data-connectors-ingestion-sources)
3. [Schema Mapping](#3-schema-mapping)
4. [Field-Level Transformations](#4-field-level-transformations)
5. [Unit Conversion](#5-unit-conversion)
6. [Timestamp & Timezone Handling](#6-timestamp--timezone-handling)
7. [Identity Resolution](#7-identity-resolution)
8. [Semantic Point Name Resolution](#8-semantic-point-name-resolution)
9. [Data Quality Validation](#9-data-quality-validation)
10. [ISO 25012 Data Quality Engine](#10-iso-25012-data-quality-engine)
11. [Normalization & Loading](#11-normalization--loading)
12. [Digital Twin Store (Destination)](#12-digital-twin-store-destination)
13. [Streaming Ingest (Real-Time)](#13-streaming-ingest-real-time)
14. [Scheduling & Backfill](#14-scheduling--backfill)
15. [Credential Management](#15-credential-management)
16. [Lineage Tracking](#16-lineage-tracking)
17. [Idempotency & Deduplication](#17-idempotency--deduplication)
18. [End-to-End Flow Diagram](#18-end-to-end-flow-diagram)

---

## 1. Pipeline Overview

The Loweconex data processing pipeline transforms raw data from heterogeneous sources (BMS, CMMS, energy meters, leak detectors, vendor exports) into a canonical digital twin model. The pipeline has two ingestion modes:

- **Batch ingestion** — CSV/XLSX upload, REST API pull, SFTP, S3, database queries → normalize → validate → load into TwinStore
- **Streaming ingestion** — MQTT subscriptions and BACnet/IP polling → normalize → write time-series → forward to PdM kernel for real-time diagnostics

```
┌──────────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                                   │
│  CSV/XLSX │ REST API │ SFTP │ S3 │ Database │ MQTT │ BACnet/IP       │
└─────┬─────┴─────┬────┴──┬───┴──┬─┴────┬─────┴──┬───┴────┬───────────┘
      │           │       │      │      │        │        │
      ▼           ▼       ▼      ▼      ▼        ▼        ▼
┌─────────────────────────────────┐  ┌──────────────────────────┐
│     Batch Connectors            │  │  Streaming Listeners     │
│  (ConnectorFactory.create())    │  │  (MQTT + BACnet Poller)  │
└──────────────┬──────────────────┘  └───────────┬──────────────┘
               │                                  │
               ▼                                  ▼
┌──────────────────────────────┐   ┌────────────────────────────────┐
│   Schema Mapping             │   │   StreamingIngestService        │
│   + Field Transforms         │   │   (backpressure queue +        │
│   + Unit Conversion          │   │    consumer thread)             │
│   + Enum Mapping             │   └──────────────┬─────────────────┘
└──────────────┬───────────────┘                  │
               │                                  │
               ▼                                  │
┌──────────────────────────────┐                  │
│  Identity Resolution         │                  │
│  (source ID → canonical ID)  │                  │
└──────────────┬───────────────┘                  │
               │                                  │
               ▼                                  │
┌──────────────────────────────┐                  │
│  Semantic Point Resolution   │                  │
│  (Brick/Haystack ontology)   │                  │
└──────────────┬───────────────┘                  │
               │                                  │
               ▼                                  │
┌──────────────────────────────┐                  │
│  Data Quality Validation     │                  │
│  (ranges, required fields,   │                  │
│   referential integrity,     │                  │
│   DQ score gating)           │                  │
└──────────────┬───────────────┘                  │
               │                                  │
               ▼                                  ▼
┌──────────────────────────────────────────────────────────────┐
│                      TwinStore                                │
│  (Assets, Locations, Estates, Time-Series, Events)           │
│  + Idempotent ingestion (run_id dedup)                       │
│  + Revision tracking per entity                              │
└──────────────────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│  Downstream Consumers                                         │
│  PdM Kernel │ KPI Crews │ Scenario Agents │ Report Builder   │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Data Connectors (Ingestion Sources)

**File:** `loweconex_platform/ingestion/connectors.py`

All connectors inherit from `BaseConnector` and implement three methods: `test_connection()`, `load()`, and `preview()`. They produce a standardized `LoadResult` containing the raw data as `List[Dict[str, Any]]`.

### 2.1 Connector Types

| Connector | Class | Description | Key Parameters |
|-----------|-------|-------------|----------------|
| **CSV/XLSX** | `CSVConnector` | File upload (CSV or Excel via openpyxl) | `file_path`, `delimiter`, `encoding`, `has_header` |
| **REST API** | `APIConnector` | Pull from REST/GraphQL endpoints | `base_url`, `auth_type` (bearer/api_key), `headers`, `pagination` |
| **Database** | `DatabaseConnector` | Query read replicas via SQLAlchemy | `connection_string`, `query` |
| **SFTP** | `SFTPConnector` | Pull files from SFTP servers (paramiko) | `host`, `port`, `remote_path`, `username`, `password`/`key_path` |
| **S3** | `S3Connector` | Pull from Amazon S3 or compatible stores (boto3) | `bucket`, `key`, `region`, `endpoint_url` |

### 2.2 ConnectorFactory

```python
ConnectorFactory.create(config: ConnectorConfig) -> BaseConnector
```

Factory pattern maps `connector_type` string to class:

| Type String | Class |
|------------|-------|
| `csv` | `CSVConnector` |
| `xlsx` | `CSVConnector` |
| `api` | `APIConnector` |
| `database` | `DatabaseConnector` |
| `sftp` | `SFTPConnector` |
| `s3` | `S3Connector` |

### 2.3 LoadResult

Every connector returns:

| Field | Type | Description |
|-------|------|-------------|
| `rows_loaded` | int | Total rows successfully read |
| `rows_rejected` | int | Rows that failed to parse |
| `columns` | List[str] | Column/field names detected |
| `sample_rows` | List[Dict] | First 5 rows for preview |
| `data` | List[Dict] | Full raw data (source field names, untransformed) |
| `errors` | List[str] | Error messages |
| `warnings` | List[str] | Warning messages |
| `load_ts` | str | ISO timestamp of load |

### 2.4 ConnectorConfig

| Field | Description |
|-------|-------------|
| `connector_type` | One of: csv, xlsx, api, database, sftp, s3 |
| `name` | Human-readable connector name |
| `credentials` | Dict of secret values (never logged in plaintext) |
| `parameters` | Connector-specific config (URLs, paths, queries) |
| `schedule` | `once`, `hourly`, `daily`, `weekly` |
| `last_run_ts` | ISO timestamp of last execution |

---

## 3. Schema Mapping

**File:** `loweconex_platform/ingestion/normalizer.py`

Schema mappings define how source fields map to the canonical schema. Each `SchemaMapping` contains a list of `FieldMapping` entries plus identity and timestamp configuration.

### 3.1 SchemaMapping

| Field | Type | Description |
|-------|------|-------------|
| `mapping_id` | str | UUID, auto-generated |
| `name` | str | Human-readable mapping name |
| `source_type` | str | Data category: `telemetry`, `work_orders`, `energy`, `leak_logs`, `call_center`, `vendor_jobs`, `asset_registry`, `location_registry` |
| `field_mappings` | List[FieldMapping] | Per-field mapping rules |
| `identity_fields` | Dict[str, str] | Maps canonical identity fields to source fields (e.g., `{"asset_id": "src_equipment_id"}`) |
| `timezone` | str | Source timezone (default: `UTC`) |
| `timestamp_format` | str | Optional strptime format for timestamp parsing |
| `confirmed` | bool | Whether mapping has been human-reviewed |
| `confirmed_by` | str | Who confirmed the mapping |

### 3.2 FieldMapping

Each field mapping specifies how a single source column maps to a canonical field:

| Field | Type | Description |
|-------|------|-------------|
| `source_field` | str | Column name in the source data |
| `canonical_field` | str | Target field name in canonical schema |
| `transform` | str | Transform to apply: `lowercase`, `uppercase`, `strip`, `float`, `int`, `datetime` |
| `unit_source` | str | Unit of the source value (e.g., `fahrenheit`) |
| `unit_target` | str | Target unit to convert to (e.g., `celsius`) |
| `enum_map` | Dict[str, str] | Value remapping (e.g., `{"1": "active", "0": "inactive"}`) |
| `default_value` | Any | Default if source field is missing |
| `required` | bool | Raise error if field is missing/null |

### 3.3 Source Type Routing

The normalizer routes each row to a specific loader based on `source_type`:

| Source Type | Loader | Destination |
|------------|--------|-------------|
| `telemetry` | `_load_telemetry()` | TwinStore time-series |
| `energy` | `_load_telemetry()` | TwinStore time-series |
| `work_orders` | `_load_event()` | TwinStore events |
| `leak_logs` | `_load_event()` | TwinStore events |
| `call_center` | `_load_event()` | TwinStore events |
| `vendor_jobs` | `_load_event()` | TwinStore events |
| `asset_registry` | `_load_asset()` | TwinStore assets |
| `location_registry` | `_load_location()` | TwinStore locations |
| *(other)* | `_load_event()` | TwinStore events (fallback) |

---

## 4. Field-Level Transformations

**Method:** `Normalizer._apply_transform()`

Transformations are applied per-field during normalization:

| Transform | Behavior |
|-----------|----------|
| `float` | Cast to float, default 0.0 on empty |
| `int` | Cast to int (via float), default 0 on empty |
| `lowercase` | Convert string to lowercase |
| `uppercase` | Convert string to uppercase |
| `strip` | Strip leading/trailing whitespace |
| `datetime` | Parse to Python datetime (see Section 6) |

After transform, two additional steps run:

1. **Enum mapping** — If `enum_map` is defined, the string value is remapped (e.g., vendor-specific codes → canonical codes)
2. **Unit conversion** — If `unit_source` ≠ `unit_target`, automatic conversion is applied (see Section 5)

---

## 5. Unit Conversion

**Function:** `normalizer.convert_unit()`

Built-in conversion table for HVAC/R-relevant units:

| From | To | Formula |
|------|----|---------|
| Fahrenheit | Celsius | `(v - 32) × 5/9` |
| Celsius | Fahrenheit | `v × 9/5 + 32` |
| PSI | Bar | `v × 0.0689476` |
| Bar | PSI | `v / 0.0689476` |
| lbs | kg | `v × 0.453592` |
| kg | lbs | `v / 0.453592` |
| kWh | MWh | `v / 1000` |
| MWh | kWh | `v × 1000` |
| Therms | kWh | `v × 29.3001` |
| kWh | Therms | `v / 29.3001` |
| CFM | m³/h | `v × 1.69901` |
| m³/h | CFM | `v / 1.69901` |
| inches WC | Pa | `v × 249.089` |
| Pa | inches WC | `v / 249.089` |

- Conversion is **case-insensitive**
- If no conversion is found, the value is returned unchanged with a warning logged
- Identity conversions (`from == to`) are no-ops

---

## 6. Timestamp & Timezone Handling

**Method:** `Normalizer._parse_datetime_tz()`

### 6.1 Parsing Strategy

1. If value is already a `datetime` object → use directly
2. If `timestamp_format` is specified → parse with `strptime`
3. Otherwise → parse with `datetime.fromisoformat()`

### 6.2 Timezone Normalization

All timestamps are normalized to **UTC** (timezone-naive) for storage:

1. If the parsed datetime has no timezone info AND the mapping specifies a non-UTC timezone:
   - Apply the source timezone via `zoneinfo.ZoneInfo` (Python 3.9+) or `backports.zoneinfo`
   - This correctly handles **DST discontinuities** (spring-forward/fall-back)
2. If the datetime has timezone info:
   - Convert to UTC via `astimezone(timezone.utc)`
   - Strip timezone info (store as naive UTC)

### 6.3 Fallback

If `zoneinfo` is unavailable, timezone-unaware datetimes are stored as-is (assumed UTC).

---

## 7. Identity Resolution

**Class:** `IdentityResolver`

### 7.1 Purpose

Different source systems refer to the same physical asset or location by different IDs. The IdentityResolver maintains a cross-reference table that maps source-specific IDs to canonical IDs.

### 7.2 Mapping Structure

```
source_system → source_id → canonical_id
```

Two parallel maps:
- `_asset_map` — for equipment/asset identity
- `_location_map` — for site/location identity

### 7.3 Resolution Flow

For each row:

1. **Exact match** — Look up `(source_system, source_id)` in the mapping table
2. **Create if missing** — If no match found, generate a canonical ID:
   - Assets: `asset_{company_id}_{source_id}`
   - Locations: `loc_{company_id}_{source_id}`
3. **Register** — Store the new mapping for future lookups

### 7.4 Methods

| Method | Description |
|--------|-------------|
| `register_asset_mapping(source_system, source_id, canonical_id)` | Pre-register a known mapping |
| `resolve_asset(source_system, source_id)` | Look up canonical ID (returns None if unknown) |
| `resolve_or_create_asset(source_system, source_id, company_id, location_id)` | Look up or auto-create canonical ID |
| `resolve_or_create_location(source_system, source_id, company_id)` | Same for locations |
| `get_unresolved()` | List of records that failed resolution |
| `stats()` | Summary of mapping counts per source system |

---

## 8. Semantic Point Name Resolution

**Class:** `BrickHaystackAdapter` (from `loweconex_platform/semantic/ontology.py`)

### 8.1 Purpose

Building Management Systems (BMS) use inconsistent point names across vendors and installations. The semantic adapter resolves raw BMS point names (e.g., `AHU-1.SAT`, `RTU_03_DischAirTemp`) to canonical ontology terms using the Brick and Haystack standards.

### 8.2 Integration

During normalization, if the canonical record contains a `point_name` field:

```python
if "point_name" in canonical and canonical["point_name"]:
    canonical["point_name"] = self.resolve_point_name(canonical["point_name"])
```

The `resolve_point_name()` method calls the semantic adapter's `resolve_point()`, falling back to the original name if resolution fails.

### 8.3 Ontology Standards

| Standard | Description |
|----------|-------------|
| **Brick** | RDF-based building metadata schema (brick-class URIs) |
| **Haystack** | Tag-based building data model (marker tags) |
| **ASHRAE 223P** | Semantic interoperability standard for building equipment |

### 8.4 Semantic Validation Rules

The ontology enforces structural constraints on the normalized data:

| Rule | Severity | Description |
|------|----------|-------------|
| `rack_serves_cases` | Error | Refrigeration rack MUST serve ≥1 case |
| `hvac_serves_zone` | Warning | HVAC unit SHOULD serve a zone |
| `temp_point_unit` | Error | Temperature points MUST use °F/°C/degF/degC |
| `pressure_point_unit` | Error | Pressure points MUST use psi/kPa/bar/inHg |
| `power_point_unit` | Error | Power points MUST use kW/W/hp |
| `equipment_has_location` | Error | All equipment MUST have a location |
| `condenser_rejects_heat` | Warning | Condensers SHOULD have a rejectsHeatTo relationship |

---

## 9. Data Quality Validation

**File:** `loweconex_platform/ingestion/validators.py`

### 9.1 DataValidator

Pre-import validation that checks data quality and generates a score. **Blocks import if score falls below configurable threshold** (default: 0.6).

### 9.2 Validation Checks

| Check | Severity | Description |
|-------|----------|-------------|
| **Required fields** | Error | Fields marked required must be present and non-empty |
| **Value ranges** | Warning | Numeric values checked against domain-specific bounds |
| **Uniqueness** | Warning | Duplicate values flagged for fields marked unique |
| **Referential integrity** | Info | Asset/location IDs checked against TwinStore (missing = will be created) |
| **Data type conformance** | Warning | Non-numeric values in range-checked fields |

### 9.3 Standard Range Checks

| Canonical Field | Min | Max |
|-----------------|-----|-----|
| `temperature_f` | -40 | 200 |
| `temperature_c` | -40 | 93 |
| `pressure_psi` | 0 | 1,000 |
| `humidity_pct` | 0 | 100 |
| `energy_kwh` | 0 | 1,000,000 |
| `power_kw` | 0 | 10,000 |
| `health_score` | 0 | 100 |
| `failure_risk` | 0 | 1 |
| `leak_rate` | 0 | 1 |
| `cost` | 0 | 10,000,000 |
| `age_years` | 0 | 100 |
| `sqft` | 100 | 1,000,000 |

### 9.4 Data Quality Score

```
DQ Score = max(0.0, 1.0 - error_rate - warning_rate × 0.3)
```

Where:
- `error_rate = error_count / total_rows`
- `warning_rate = warning_count / total_rows`

If `DQ Score < quality_threshold` (default 0.6), the import is **blocked** and the `ValidationResult.blocked` flag is set to `True`.

### 9.5 ValidationResult

| Field | Type | Description |
|-------|------|-------------|
| `is_valid` | bool | True if DQ score ≥ threshold |
| `data_quality_score` | float | 0.0–1.0 composite score |
| `total_rows` | int | Input row count |
| `valid_rows` | int | Rows with zero errors |
| `issues` | List[ValidationIssue] | Detailed issue list (capped at 100) |
| `field_completeness` | Dict[str, float] | Per-field % of non-null values |
| `blocked` | bool | True if score below threshold (import prevented) |

---

## 10. ISO 25012 Data Quality Engine

**File:** `loweconex_platform/data_quality/quality_engine.py`

An optional, more comprehensive quality layer that integrates with the normalizer.

### 10.1 ISO/IEC 25012 Dimensions

The engine scores data across 18 quality dimensions:

| Category | Dimensions |
|----------|-----------|
| **Inherent** | Accuracy, Completeness, Consistency, Credibility, Currentness |
| **System-dependent** | Accessibility, Compliance, Confidentiality, Efficiency, Precision, Traceability, Understandability, Availability, Portability, Recoverability |
| **Additional** | Timeliness, Uniqueness, Validity |

### 10.2 Expectation Suites (Great Expectations-style)

Individual quality assertions defined per dataset:

| Expectation Type | Description |
|------------------|-------------|
| `not_null` | Column must not contain nulls |
| `unique` | Column values must be unique |
| `in_set` | Values must be within an allowed set |
| `in_range` | Numeric values within min/max bounds |
| `regex_match` | Values must match regex pattern |
| `type_check` | Values must be of expected type |
| `row_count_range` | Dataset must have expected number of rows |
| `column_exists` | Required columns must be present |
| `mean_in_range` | Column mean within expected bounds |
| `std_in_range` | Column standard deviation within bounds |
| `max_null_fraction` | Maximum allowed null percentage |
| `freshness` | Data must be within recency threshold |
| `referential_integrity` | Foreign keys must resolve |
| `custom` | User-defined validation function |

### 10.3 Gate Decisions

Quality gates produce one of three decisions:

| Decision | Effect |
|----------|--------|
| `PASS` | Data proceeds to normalization |
| `WARN` | Data proceeds with logged warnings |
| `BLOCK` | Data rejected, import halted |

### 10.4 Integration with Normalizer

The normalizer calls `run_data_quality_check()` before processing rows. This method:

1. Creates an expectation suite named `ingestion_{source_type}`
2. Runs all expectations against the raw data
3. Returns a quality report included in the normalization stats
4. If blocked, the normalizer skips row processing

---

## 11. Normalization & Loading

**Method:** `Normalizer.normalize_and_load()`

### 11.1 Process (Per Batch)

```
1. Generate unique run_id (UUID)
2. Start lineage job (OpenLineage)
3. Idempotency check — skip if run_id already processed
4. Run data quality checks on raw data
5. For each row:
   a. Apply schema mapping (_apply_mapping)
   b. Resolve semantic point names
   c. Route by source_type to appropriate loader
6. Complete lineage job
7. Return stats summary
```

### 11.2 Telemetry Loading (`_load_telemetry`)

For each telemetry row:

1. Extract `asset_id`, `location_id`, `point_name`, `value`, `timestamp` from canonical record
2. Resolve location identity → canonical `location_id`
3. Resolve asset identity → canonical `asset_id`
4. Construct `point_id` = `{asset_id}:{point_name}` (or `{company_id}:{point_name}` if no asset)
5. Write `TimeSeriesPoint(timestamp, value, unit)` to TwinStore

### 11.3 Event Loading (`_load_event`)

For work orders, leak logs, call center records, and vendor jobs:

1. Extract or generate `event_id`
2. Set `event_type` from canonical record or default to `source_type`
3. Resolve location and asset identities
4. Parse `start_ts` and `end_ts`
5. Build `OperationalEvent` with severity, confidence, code, and payload (all remaining fields)
6. Store in TwinStore event store

### 11.4 Asset Registry Loading (`_load_asset`)

1. Resolve asset identity
2. Map `asset_type` string to `AssetType` enum (fallback: `OTHER`)
3. If asset exists → **update** (manufacturer, model, serial, install_date)
4. If asset is new → **create** `AssetTwin` with full attributes

Supported asset types:

| Type | Value |
|------|-------|
| HVAC RTU | `hvac_rtu` |
| HVAC AHU | `hvac_ahu` |
| Refrigeration Rack | `refrigeration_rack` |
| Refrigeration Case | `refrigeration_case` |
| Compressor | `compressor` |
| Condenser | `condenser` |
| Evaporator | `evaporator` |
| Boiler | `boiler` |
| Chiller | `chiller` |
| VFD | `vfd` |
| Lighting | `lighting` |
| Power Meter | `power_meter` |
| Temp Sensor | `temp_sensor` |
| Leak Detector | `leak_detector` |
| Other | `other` |

### 11.5 Location Registry Loading (`_load_location`)

1. Check if location exists → **update** (address, sqft, store_format, climate_zone)
2. If new → **create** `LocationTwin` with attributes

### 11.6 Normalization Stats

Every `normalize_and_load()` call returns:

| Stat | Description |
|------|-------------|
| `run_id` | Unique ingestion run identifier |
| `rows_processed` | Total rows iterated |
| `assets_created` | New assets created |
| `assets_updated` | Existing assets updated |
| `locations_created` | New locations created |
| `events_created` | Events stored |
| `timeseries_points` | Time-series points written |
| `errors` | List of `{row, error}` for failed rows |
| `data_quality_report` | DQ engine results |

---

## 12. Digital Twin Store (Destination)

**File:** `loweconex_platform/digital_twins/store.py`

### 12.1 TwinStore

Thread-safe in-memory store (production interface compatible with PostgreSQL/TimescaleDB). Stores:

| Collection | Model | Key | Description |
|-----------|-------|-----|-------------|
| Assets | `AssetTwin` | `asset_id` | Equipment twins with health, economics, point maps |
| Locations | `LocationTwin` | `location_id` | Store/site twins with tariffs, KPI rollups, compliance |
| Estates | `EstateTwin` | `company_id` | Portfolio twins with benchmarks, scenarios, ROI |
| Time-Series | `TimeSeriesPoint` | `point_id` | Sorted time-series observations (`{asset_id}:{point_name}`) |
| Events | `OperationalEvent` | `event_id` | Unified events (faults, work orders, leaks, excursions) |
| Relationships | `TwinRelationship` | — | Typed edges (SERVES, REJECTS_HEAT_TO, FED_BY, etc.) |

### 12.2 TimeSeriesPoint

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | datetime | UTC observation time |
| `value` | float | Numeric measurement |
| `quality` | float | Data quality score (0.0–1.0, default 1.0) |
| `unit` | str | Unit of measurement |

### 12.3 OperationalEvent

Unified event model covering faults, excursions, leaks, and work orders:

| Field | Type | Description |
|-------|------|-------------|
| `event_id` | str | Unique event identifier |
| `event_type` | str | Category (work_orders, leak_logs, call_center, etc.) |
| `source_system` | str | Originating system |
| `start_ts` / `end_ts` | datetime | Event timespan |
| `asset_id` | str | Associated asset (optional) |
| `location_id` | str | Associated location (optional) |
| `company_id` | str | Owning company |
| `severity` | str | info / warning / error / critical |
| `confidence` | float | 0.0–1.0 |
| `code` | str | Event/fault code |
| `ack_status` | str | unacked / acked / resolved |
| `payload` | Dict | All additional fields from the source record |

### 12.4 AssetTwin

Full digital twin for a physical asset:

| Category | Fields |
|----------|--------|
| **Identity** | `asset_id`, `location_id`, `company_id`, `asset_type`, `manufacturer`, `model`, `serial`, `install_date`, `age_years` |
| **Relationships** | `zone_id`, `served_zone_ids`, `served_case_ids`, `served_product_zones`, `fed_by_meter_id`, `contains_component_ids` |
| **Telemetry** | `point_map` (point name → point ID), `units_map` (point name → unit) |
| **Health** | `health_score` (0–100), `failure_risk_30d`, `failure_risk_90d`, `anomaly_flags`, `assessment_source` |
| **Economics** | `opex_baseline_monthly`, `capex_replace_cost`, `remaining_useful_life_months`, `expected_life_years`, `predicted_future_cost_curve` |

### 12.5 LocationTwin

| Category | Fields |
|----------|--------|
| **Geography** | `geo` (lat/lon), `climate_zone`, `region`, `address` |
| **Store** | `store_format`, `sqft`, `operating_hours` |
| **Assets** | `asset_ids`, `has_meter_ids`, `adjacent_system_ids` |
| **Economics** | `utility_tariffs` (electricity rate, demand charge, gas rate) |
| **KPIs** | `kpi_rollups` (per-KPI summary with savings bands and confidence) |
| **Compliance** | `food_safety`, `refrigerant`, `esg`, `last_audit_ts` |

### 12.6 Indexes & Queries

| Index | Structure | Enables |
|-------|-----------|---------|
| Company → Locations | `Dict[company_id, List[location_id]]` | Get all sites for a company |
| Location → Assets | `Dict[location_id, List[asset_id]]` | Get all equipment at a site |
| Time-series | `Dict[point_id, List[TimeSeriesPoint]]` | Query by point + time range |
| Events | `Dict[event_id, OperationalEvent]` | Filter by company, location, asset, type, time |

---

## 13. Streaming Ingest (Real-Time)

**File:** `loweconex_platform/ingestion/streaming.py`

### 13.1 StreamingIngestService

Unified service managing real-time protocol listeners with:

- **Backpressure queue** — Bounded `queue.Queue` (configurable `high_water_mark`, default 10,000) between listeners and processing. Drops messages when full.
- **Consumer thread** — Single background thread drains the queue and processes messages
- **Metrics tracking** — Messages received, processed, failed, dropped, queue depth

### 13.2 Protocol Listeners

#### MQTT Listener (`MQTTListener`)

| Setting | Default | Description |
|---------|---------|-------------|
| `mqtt_broker` | localhost | Broker hostname |
| `mqtt_port` | 1883 | Broker port |
| `mqtt_topics` | `pdm/telemetry/#`, `pdm/events/#` | Subscription topics |
| `mqtt_qos` | 1 | Quality of Service level |
| `mqtt_client_id` | `pdm_ingest` | Client identifier |

- Uses `paho-mqtt` library
- Auto-reconnects on disconnect
- Parses JSON payloads from MQTT messages

#### BACnet/IP Poller (`BACnetPoller`)

| Setting | Default | Description |
|---------|---------|-------------|
| `bacnet_ip` | 0.0.0.0 | Network interface |
| `bacnet_port` | 47808 | BACnet port |
| `bacnet_device_ids` | [] | Device IDs to poll |
| `bacnet_poll_interval_seconds` | 30.0 | Polling interval |

- Uses `BAC0` library
- Reads standard HVAC BACnet objects per device:

| Object Type | Instance | Metric Name |
|------------|----------|-------------|
| analogInput 0 | zone_temp | Zone Temperature |
| analogInput 1 | supply_air_temp | Supply Air Temperature |
| analogInput 2 | return_air_temp | Return Air Temperature |
| analogInput 3 | discharge_pressure | Discharge Pressure |
| analogInput 4 | suction_pressure | Suction Pressure |
| analogOutput 0 | compressor_speed | Compressor Speed |
| binaryInput 0 | compressor_status | Compressor On/Off |

### 13.3 Message Processing (`_handle_message`)

For every message from any protocol:

1. **Extract asset ID** — From `asset_id` or `device_id` field
2. **Parse timestamp** — ISO format with `Z` suffix handling; fallback to `now(UTC)`
3. **Normalize timezone** — Ensure UTC
4. **Write to TwinStore** — Construct `point_id = {asset_id}:{metric}`, write `TimeSeriesPoint` with value and quality
5. **Publish to event bus** — `ingest.{protocol}` channel with topic, asset_id, timestamp
6. **Forward to PdM kernel** — `HVACRPdMAdvancedSystem.process_reading(payload)` for real-time health assessment, fault diagnosis, and RUL estimation

### 13.4 PdM Kernel Integration

The streaming service lazily creates a PdM kernel system per asset:

```python
from predictive_maintenance.integration.advanced_system import create_pdm_system
system = create_pdm_system(asset_id=asset_id)
```

Every incoming reading is forwarded to the kernel for real-time diagnostics. If the PdM module is unavailable, streaming data is still stored but no diagnostics are triggered.

### 13.5 IngestMetrics

| Metric | Description |
|--------|-------------|
| `messages_received` | Total messages received across all listeners |
| `messages_processed` | Successfully processed |
| `messages_failed` | Processing errors |
| `backpressure_drops` | Messages dropped due to full queue |
| `queue_depth` | Current queue size |
| `uptime_seconds` | Service uptime |
| `active_protocols` | List of active protocol names |
| `last_message_ts` | Timestamp of most recent message |

---

## 14. Scheduling & Backfill

**File:** `loweconex_platform/ingestion/scheduler.py`

### 14.1 IngestionScheduler

Manages scheduled and backfill ingestion jobs in a background thread.

| Schedule | Interval |
|----------|----------|
| `once` | 0 (manual trigger only) |
| `hourly` | 3,600s |
| `daily` | 86,400s |
| `weekly` | 604,800s |

### 14.2 ScheduledJob

| Field | Description |
|-------|-------------|
| `job_id` | Unique identifier (UUID) |
| `connector_name` | Which connector to use |
| `mapping_id` | Which schema mapping to apply |
| `company_id` | Target company |
| `source_system` | Source system identifier |
| `schedule` | once / hourly / daily / weekly |
| `enabled` | Active flag |
| `last_run_id` | UUID of last execution |
| `last_run_ts` | Timestamp of last execution |
| `last_status` | success / failed |
| `next_run_ts` | Calculated next execution time |

### 14.3 BackfillRequest

For historical data loading:

| Field | Description |
|-------|-------------|
| `request_id` | Unique identifier |
| `connector_name` | Source connector |
| `mapping_id` | Schema mapping |
| `start_date` / `end_date` | Date range to backfill |
| `status` | pending / running / completed / failed |
| `run_id` | Assigned when execution starts |

### 14.4 Execution

- Each run gets a unique `run_id` for idempotent deduplication
- The scheduler calls a user-provided callback with `(job, run_id)` arguments
- Failed jobs are logged; next run is still scheduled
- Background thread calls `tick()` at configurable interval (default 60s)

---

## 15. Credential Management

**File:** `loweconex_platform/ingestion/credential_vault.py`

### 15.1 CredentialVault

Secure credential storage with:

- **Never logged or serialized in plaintext**
- Audit-logged access (store, retrieve, rotate, delete)
- Rotation tracking with `rotated_ts`
- Expiry monitoring with `expires_ts`

### 15.2 Vault Backends

| Backend | Class | Description |
|---------|-------|-------------|
| In-memory | `InMemoryVault` | Dev/testing (default) |
| Environment vars | `EnvVarVault` | Env-based, prefix `LOWECONEX_CRED_` |
| *(Interface)* | `VaultBackend` | Abstract base for HashiCorp Vault / AWS Secrets Manager / Azure Key Vault |

### 15.3 Credential Types

| Type | Description |
|------|-------------|
| `api_key` | API key for REST connectors |
| `bearer_token` | OAuth bearer token |
| `basic_auth` | Username/password pair |
| `connection_string` | Database connection string |

---

## 16. Lineage Tracking

**File:** `loweconex_platform/lineage/lineage_tracker.py`

### 16.1 OpenLineage-Compatible Provenance

Every normalization run creates a complete lineage chain:

```
Raw Input Dataset → Ingestion Job → Normalized Output Dataset
```

### 16.2 Lineage Events

| Event Type | Description |
|------------|-------------|
| `START` | Job begins |
| `RUNNING` | Job in progress |
| `COMPLETE` | Job finished successfully |
| `FAIL` | Job failed |
| `ABORT` | Job aborted |

### 16.3 Dataset Types

| Type | Description |
|------|-------------|
| `raw_telemetry` | Raw BMS/sensor data |
| `raw_work_order` | Raw CMMS records |
| `raw_event` | Raw operational events |
| `normalized` | Post-normalization data |
| `feature_table` | Engineered features |
| `twin_snapshot` | Digital twin state |
| `kpi_artifact` | KPI computation output |
| `scenario_result` | Scenario simulation output |
| `roi_rollup` | ROI computation output |
| `report_section` / `report_export` | Generated reports |

### 16.4 Job Types

| Type | Description |
|------|-------------|
| `ingestion` | Data loading |
| `normalization` | Schema transformation |
| `identity_resolution` | ID cross-referencing |
| `feature_engineering` | Feature computation |
| `kpi_calculation` | KPI computation |
| `model_inference` / `model_training` | ML operations |

### 16.5 Integration with Normalizer

During `normalize_and_load()`:

1. `lineage.start_job()` — Creates ingestion job with config metadata
2. `lineage.add_input()` — Registers the raw input dataset (name, type, row count)
3. *(normalization runs)*
4. `lineage.add_output()` — Registers the normalized output (assets, events, ts points created)
5. `lineage.complete_job()` or `lineage.fail_job()` — Closes the lineage record

Every numbered output in the platform carries a `lineage_id` that traces back through the full provenance chain.

---

## 17. Idempotency & Deduplication

### 17.1 Run-Level Idempotency

Every ingestion run (batch or backfill) receives a unique `run_id` (UUID). Before processing:

```python
if not self.twin_store.idempotent_ingest(run_id):
    # Already processed — skip entire batch
    return stats
```

The TwinStore atomically checks and registers the `run_id` under a lock. If the `run_id` has been seen before, the entire batch is skipped.

### 17.2 Event-Level Deduplication

Events can optionally be deduplicated by `(run_id, event_id)`:

```python
store_event(event, run_id=run_id)  # Returns False if duplicate
```

### 17.3 Revision Tracking

Every entity (asset, location, estate) maintains a monotonically increasing revision number:

```python
self._bump_revision("asset", asset_id)  # Returns new revision number
```

This enables change detection and conflict resolution.

---

## 18. End-to-End Flow Diagram

### Batch Ingestion (CSV upload example)

```
1. User uploads CSV via API
   └─▶ CSVConnector.load(file_path) → LoadResult(data=[...])

2. Schema mapping applied
   └─▶ Normalizer.normalize_and_load(data, mapping, company_id, source_system)
       │
       ├─ 2a. Generate run_id, check idempotency
       ├─ 2b. Start lineage job
       ├─ 2c. Run DQ checks → DQ score, gate decision
       │
       └─ 2d. For each row:
              ├─ Apply field mappings (rename, transform, enum map)
              ├─ Convert units (°F→°C, PSI→bar, etc.)
              ├─ Parse + normalize timestamps to UTC
              ├─ Resolve semantic point names (Brick/Haystack)
              ├─ Resolve asset/location identity
              └─ Route to loader:
                 ├─ telemetry → TimeSeriesPoint → TwinStore.write_timeseries()
                 ├─ work_orders → OperationalEvent → TwinStore.store_event()
                 ├─ asset_registry → AssetTwin → TwinStore.upsert_asset()
                 └─ location_registry → LocationTwin → TwinStore.upsert_location()

3. Complete lineage job
4. Return normalization stats
```

### Streaming Ingestion (MQTT example)

```
1. MQTT message arrives on pdm/telemetry/{asset_id}
   └─▶ MQTTListener._on_message()
       └─▶ Parse JSON payload
           └─▶ _enqueue_message("mqtt", topic, payload)

2. Consumer thread dequeues message
   └─▶ _handle_message("mqtt", topic, payload)
       │
       ├─ 2a. Extract asset_id, parse timestamp → UTC
       ├─ 2b. Construct point_id = {asset_id}:{metric}
       ├─ 2c. Write TimeSeriesPoint to TwinStore
       ├─ 2d. Publish to Redis event bus (ingest.mqtt)
       └─ 2e. Forward to PdM kernel for real-time diagnostics
              └─▶ HVACRPdMAdvancedSystem.process_reading(payload)
                  └─▶ Health assessment, fault diagnosis, RUL estimation
```
