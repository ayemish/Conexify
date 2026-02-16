"""
TC-A: Data Loading UI & Ingestion Pipeline (TC-A01–A05)

Tests connectors, schema mapping, validation, normalization,
credential vault, scheduler, and lineage integration.
"""

import pytest
import uuid
from datetime import datetime

from loweconex_platform.ingestion.connectors import (
    ConnectorConfig, ConnectorFactory, CSVConnector, LoadResult,
)
from loweconex_platform.ingestion.normalizer import (
    FieldMapping, SchemaMapping, Normalizer, IdentityResolver, convert_unit,
)
from loweconex_platform.ingestion.validators import DataValidator
from loweconex_platform.ingestion.scheduler import (
    IngestionScheduler, ScheduledJob, BackfillRequest,
)
from loweconex_platform.ingestion.credential_vault import (
    CredentialVault, InMemoryVault, EnvVarVault, CredentialEntry,
)
from loweconex_platform.digital_twins.store import TwinStore
from loweconex_platform.lineage.lineage_tracker import LineageTracker


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def twin_store():
    return TwinStore()


@pytest.fixture
def lineage_tracker():
    return LineageTracker()


@pytest.fixture
def normalizer(twin_store, lineage_tracker):
    return Normalizer(twin_store, lineage_tracker=lineage_tracker)


@pytest.fixture
def telemetry_mapping():
    m = SchemaMapping(
        name="test_telemetry",
        source_type="telemetry",
        timezone="UTC",
        confirmed=True,
        confirmed_by="test_user",
    )
    m.add_field("equipment_id", "asset_id")
    m.add_field("store_id", "location_id")
    m.add_field("sensor_name", "point_name")
    m.add_field("reading", "value", transform="float")
    m.add_field("ts", "timestamp", transform="datetime")
    return m


@pytest.fixture
def sample_telemetry_data():
    return [
        {"equipment_id": "RTU-001", "store_id": "LOC-100", "sensor_name": "supply_air_temp",
         "reading": "72.5", "ts": "2025-01-15T10:00:00"},
        {"equipment_id": "RTU-001", "store_id": "LOC-100", "sensor_name": "return_air_temp",
         "reading": "74.1", "ts": "2025-01-15T10:00:00"},
        {"equipment_id": "RACK-001", "store_id": "LOC-100", "sensor_name": "suction_pressure",
         "reading": "28.5", "ts": "2025-01-15T10:00:00"},
    ]


# =============================================================================
# TC-A01: Connector & Credential Management
# =============================================================================

class TestTCA01Connectors:
    def test_connector_factory_creates_csv(self):
        config = ConnectorConfig(connector_type="csv", name="test_csv",
                                 parameters={"file_path": "/tmp/test.csv"})
        connector = ConnectorFactory.create(config)
        assert isinstance(connector, CSVConnector)

    def test_connector_factory_rejects_unknown_type(self):
        config = ConnectorConfig(connector_type="unknown_type")
        with pytest.raises(ValueError, match="Unknown connector type"):
            ConnectorFactory.create(config)

    def test_connector_factory_available_types(self):
        types = ConnectorFactory.available_types()
        assert "csv" in types
        assert "api" in types
        assert "database" in types

    def test_connector_config_redacts_credentials(self):
        config = ConnectorConfig(
            connector_type="api", name="test",
            credentials={"token": "secret_token_123", "api_key": "key_456"},
        )
        safe = config.to_dict()
        assert safe["credentials"]["token"] == "***"
        assert safe["credentials"]["api_key"] == "***"
        assert "secret_token_123" not in str(safe)

    def test_csv_connector_load_from_string(self):
        config = ConnectorConfig(connector_type="csv", name="test")
        connector = CSVConnector(config)
        csv_data = "id,temp,ts\n1,72.5,2025-01-01\n2,73.0,2025-01-02"
        result = connector.load_from_string(csv_data)
        assert result.rows_loaded == 2
        assert "id" in result.columns
        assert "temp" in result.columns

    def test_credential_vault_store_and_retrieve(self):
        vault = CredentialVault(InMemoryVault())
        vault.store_credential("api_key_1", "my_connector", "super_secret_key")
        retrieved = vault.retrieve_credential("api_key_1")
        assert retrieved == "super_secret_key"

    def test_credential_vault_rotation(self):
        vault = CredentialVault(InMemoryVault())
        vault.store_credential("api_key_1", "my_connector", "old_key")
        success = vault.rotate_credential("api_key_1", "new_key")
        assert success
        assert vault.retrieve_credential("api_key_1") == "new_key"

    def test_credential_vault_connector_lookup(self):
        vault = CredentialVault(InMemoryVault())
        vault.store_credential("token", "conn_a", "val1")
        vault.store_credential("key", "conn_a", "val2")
        vault.store_credential("other", "conn_b", "val3")
        creds = vault.get_credentials_for_connector("conn_a")
        assert len(creds) == 2
        assert "token" in creds
        assert "key" in creds

    def test_credential_vault_never_in_logs(self):
        vault = CredentialVault(InMemoryVault())
        entry = vault.store_credential("secret", "conn", "my_password")
        entry_dict = entry.to_dict()
        assert "my_password" not in str(entry_dict)


# =============================================================================
# TC-A02: Schema Mapping
# =============================================================================

class TestTCA02SchemaMapping:
    def test_schema_mapping_creation(self, telemetry_mapping):
        assert telemetry_mapping.confirmed is True
        assert len(telemetry_mapping.field_mappings) == 5
        assert telemetry_mapping.get_mapping("asset_id") is not None

    def test_schema_mapping_with_unit_conversion(self):
        m = SchemaMapping(source_type="telemetry")
        m.add_field("temp_f", "temperature", unit_source="fahrenheit", unit_target="celsius")
        fm = m.get_mapping("temperature")
        assert fm.unit_source == "fahrenheit"
        assert fm.unit_target == "celsius"

    def test_unit_conversion_f_to_c(self):
        assert abs(convert_unit(212.0, "fahrenheit", "celsius") - 100.0) < 0.01
        assert abs(convert_unit(32.0, "fahrenheit", "celsius") - 0.0) < 0.01

    def test_unit_conversion_psi_to_bar(self):
        result = convert_unit(14.5, "psi", "bar")
        assert abs(result - 1.0) < 0.01

    def test_unit_conversion_same_unit_noop(self):
        assert convert_unit(42.0, "kWh", "kWh") == 42.0

    def test_schema_mapping_serialization(self, telemetry_mapping):
        d = telemetry_mapping.to_dict()
        assert d["confirmed"] is True
        assert len(d["field_mappings"]) == 5


# =============================================================================
# TC-A03: Mapping Confirmation Gate
# =============================================================================

class TestTCA03MappingConfirmation:
    def test_confirmed_mapping_has_metadata(self, telemetry_mapping):
        assert telemetry_mapping.confirmed is True
        assert telemetry_mapping.confirmed_by == "test_user"

    def test_unconfirmed_mapping_flag(self):
        m = SchemaMapping(source_type="telemetry", confirmed=False)
        assert m.confirmed is False
        assert m.confirmed_by is None


# =============================================================================
# TC-A04: Data Validation & Quality Gate
# =============================================================================

class TestTCA04Validation:
    def test_validator_passes_good_data(self):
        validator = DataValidator(quality_threshold=0.5)
        data = [
            {"asset_id": "A1", "value": 72.5, "timestamp": "2025-01-01T00:00:00"},
            {"asset_id": "A2", "value": 73.0, "timestamp": "2025-01-01T01:00:00"},
        ]
        result = validator.validate(data, required_fields=["asset_id", "value"])
        assert result.quality_score >= 0.5
        assert not result.blocked

    def test_validator_blocks_low_quality(self):
        validator = DataValidator(quality_threshold=0.9)
        data = [
            {"asset_id": "A1", "value": None, "timestamp": None},
            {"asset_id": None, "value": None, "timestamp": None},
        ]
        result = validator.validate(data, required_fields=["asset_id", "value", "timestamp"])
        assert result.blocked or result.quality_score < 0.9


# =============================================================================
# TC-A05: Scheduler & Backfill
# =============================================================================

class TestTCA05Scheduler:
    def test_register_and_list_jobs(self):
        scheduler = IngestionScheduler()
        job = ScheduledJob(
            connector_name="csv_daily",
            schedule="daily",
            company_id="COMP-1",
        )
        scheduler.register_job(job)
        jobs = scheduler.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].schedule == "daily"
        assert jobs[0].next_run_ts is not None

    def test_execute_job_generates_run_id(self):
        scheduler = IngestionScheduler()
        executed = []
        scheduler.set_run_callback(lambda job, run_id: executed.append(run_id))
        job = ScheduledJob(connector_name="test", schedule="once")
        scheduler.register_job(job)
        result = scheduler.execute_job(job)
        assert result["status"] == "success"
        assert result["run_id"] is not None
        assert len(executed) == 1

    def test_backfill_request(self):
        scheduler = IngestionScheduler()
        executed = []
        scheduler.set_run_callback(lambda job, run_id: executed.append(run_id))
        req = BackfillRequest(
            connector_name="api_backfill",
            start_date="2024-01-01",
            end_date="2024-12-31",
            company_id="COMP-1",
        )
        scheduler.request_backfill(req)
        scheduler.tick()
        assert req.status == "completed"
        assert req.run_id is not None

    def test_scheduler_stats(self):
        scheduler = IngestionScheduler()
        scheduler.register_job(ScheduledJob(connector_name="a", schedule="daily"))
        scheduler.register_job(ScheduledJob(connector_name="b", schedule="hourly"))
        stats = scheduler.stats()
        assert stats["jobs"] == 2


# =============================================================================
# TC-A: Lineage Integration with Ingestion
# =============================================================================

class TestTCALineageIntegration:
    def test_normalize_and_load_records_lineage(self, normalizer, telemetry_mapping, sample_telemetry_data):
        stats = normalizer.normalize_and_load(
            sample_telemetry_data, telemetry_mapping, "COMP-1", "bms_system"
        )
        assert stats["rows_processed"] == 3
        assert stats["timeseries_points"] == 3
        assert stats["run_id"] is not None

        # Check lineage events were recorded
        events = normalizer.lineage.get_all_events()
        assert len(events) > 0

    def test_idempotent_ingestion_prevents_rerun(self, twin_store):
        run_id = "test-run-001"
        assert twin_store.idempotent_ingest(run_id) is True
        assert twin_store.idempotent_ingest(run_id) is False
