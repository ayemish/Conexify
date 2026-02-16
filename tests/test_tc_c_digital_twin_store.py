"""
TC-C: Digital Twin Store (TC-C01–C04)

Tests twin CRUD, rollups, relationships, idempotency, and revision tracking.
"""

import pytest
from datetime import datetime

from loweconex_platform.digital_twins.models import (
    AssetTwin, AssetType, LocationTwin, EstateTwin,
    KPIRollup, TwinRelationship, RelationshipType, HealthState,
)
from loweconex_platform.digital_twins.store import (
    TwinStore, TimeSeriesPoint, OperationalEvent,
)
from loweconex_platform.digital_twins.relationships import RelationshipGraph


@pytest.fixture
def store():
    return TwinStore()


@pytest.fixture
def sample_asset():
    return AssetTwin(
        asset_id="RTU-001", location_id="LOC-100", company_id="COMP-1",
        asset_type=AssetType.HVAC_RTU, manufacturer="Carrier", model="50XC",
        age_years=8,
    )


@pytest.fixture
def sample_location():
    return LocationTwin(
        location_id="LOC-100", company_id="COMP-1",
        address="123 Main St", sqft=50000, store_format="grocery",
        climate_zone="4A",
    )


@pytest.fixture
def sample_estate():
    return EstateTwin(company_id="COMP-1", name="Test Estate")


# =============================================================================
# TC-C01: Asset Twin CRUD + Time-Series + Events
# =============================================================================

class TestTCC01AssetTwin:
    def test_upsert_and_get_asset(self, store, sample_asset):
        store.upsert_asset(sample_asset)
        retrieved = store.get_asset("RTU-001")
        assert retrieved is not None
        assert retrieved.asset_id == "RTU-001"
        assert retrieved.manufacturer == "Carrier"

    def test_upsert_updates_existing(self, store, sample_asset):
        store.upsert_asset(sample_asset)
        sample_asset.manufacturer = "Trane"
        store.upsert_asset(sample_asset)
        retrieved = store.get_asset("RTU-001")
        assert retrieved.manufacturer == "Trane"

    def test_delete_asset(self, store, sample_asset):
        store.upsert_asset(sample_asset)
        assert store.delete_asset("RTU-001") is True
        assert store.get_asset("RTU-001") is None

    def test_write_and_query_timeseries(self, store):
        points = [
            TimeSeriesPoint(datetime(2025, 1, 15, 10, 0), 72.5, unit="°F"),
            TimeSeriesPoint(datetime(2025, 1, 15, 10, 5), 73.0, unit="°F"),
            TimeSeriesPoint(datetime(2025, 1, 15, 10, 10), 72.8, unit="°F"),
        ]
        store.write_timeseries("RTU-001:supply_air_temp", points)
        result = store.query_timeseries(
            ["RTU-001:supply_air_temp"],
            start_ts=datetime(2025, 1, 15, 10, 0),
            end_ts=datetime(2025, 1, 15, 10, 10),
        )
        assert len(result["RTU-001:supply_air_temp"]) == 3

    def test_store_and_query_events(self, store):
        event = OperationalEvent(
            event_id="EVT-001", event_type="work_order",
            source_system="cmms", start_ts=datetime(2025, 1, 15),
            company_id="COMP-1", asset_id="RTU-001",
        )
        store.store_event(event)
        events = store.query_events(company_id="COMP-1", event_type="work_order")
        assert len(events) == 1
        assert events[0].event_id == "EVT-001"

    def test_patch_asset_health(self, store, sample_asset):
        store.upsert_asset(sample_asset)
        store.patch_twin("asset", "RTU-001", {"health": {"health_score": 65}})
        patched = store.get_asset("RTU-001")
        assert patched.health.health_score == 65

    def test_asset_to_dict_roundtrip(self, sample_asset):
        d = sample_asset.to_dict()
        assert d["asset_id"] == "RTU-001"
        assert d["asset_type"] == "hvac_rtu"
        reconstructed = AssetTwin.from_dict(d)
        assert reconstructed.asset_id == "RTU-001"


# =============================================================================
# TC-C02: Location Twin with KPI Rollups
# =============================================================================

class TestTCC02LocationTwin:
    def test_upsert_and_get_location(self, store, sample_location):
        store.upsert_location(sample_location)
        retrieved = store.get_location("LOC-100")
        assert retrieved is not None
        assert retrieved.sqft == 50000

    def test_patch_location_kpi_rollup(self, store, sample_location):
        store.upsert_location(sample_location)
        store.patch_twin("location", "LOC-100", {
            "kpi_rollups": {
                "energy_reduction": {
                    "kpi_name": "energy_reduction",
                    "savings_low": 10000, "savings_medium": 15000, "savings_high": 20000,
                    "confidence": 0.75,
                }
            }
        })
        loc = store.get_location("LOC-100")
        assert "energy_reduction" in loc.kpi_rollups

    def test_locations_by_company(self, store, sample_location):
        store.upsert_location(sample_location)
        locs = store.get_locations_by_company("COMP-1")
        assert len(locs) == 1
        assert locs[0].location_id == "LOC-100"


# =============================================================================
# TC-C03: Estate Twin with Benchmarks
# =============================================================================

class TestTCC03EstateTwin:
    def test_upsert_and_get_estate(self, store, sample_estate):
        store.upsert_estate(sample_estate)
        retrieved = store.get_estate("COMP-1")
        assert retrieved is not None
        assert retrieved.name == "Test Estate"

    def test_estate_kpi_rollups(self, sample_estate):
        sample_estate.kpi_rollups["energy"] = KPIRollup(
            kpi_name="energy", savings_low=100000, savings_medium=150000,
            savings_high=200000, confidence=0.7,
        )
        assert "energy" in sample_estate.kpi_rollups

    def test_estate_serialization(self, sample_estate):
        d = sample_estate.to_dict()
        assert d["company_id"] == "COMP-1"


# =============================================================================
# TC-C04: Idempotency & Revision Tracking
# =============================================================================

class TestTCC04Idempotency:
    def test_idempotent_ingest_new_run(self, store):
        assert store.idempotent_ingest("run-001") is True

    def test_idempotent_ingest_duplicate_run(self, store):
        store.idempotent_ingest("run-001")
        assert store.idempotent_ingest("run-001") is False

    def test_check_run_id(self, store):
        assert store.check_run_id("run-002") is False
        store.register_run_id("run-002")
        assert store.check_run_id("run-002") is True

    def test_revision_counter_increments(self, store, sample_asset):
        assert store.get_revision("asset", "RTU-001") == 0
        store.upsert_asset(sample_asset)
        assert store.get_revision("asset", "RTU-001") == 1
        store.upsert_asset(sample_asset)
        assert store.get_revision("asset", "RTU-001") == 2

    def test_event_dedup_with_run_id(self, store):
        event = OperationalEvent(
            event_id="EVT-100", event_type="work_order",
            source_system="cmms", start_ts=datetime(2025, 1, 1),
        )
        assert store.store_event(event, run_id="run-001") is True
        assert store.store_event(event, run_id="run-001") is False

    def test_event_without_run_id_allows_overwrite(self, store):
        event = OperationalEvent(
            event_id="EVT-100", event_type="work_order",
            source_system="cmms", start_ts=datetime(2025, 1, 1),
        )
        assert store.store_event(event) is True
        assert store.store_event(event) is True  # No run_id = overwrite allowed

    def test_stats_include_idempotency_data(self, store):
        store.idempotent_ingest("run-001")
        stats = store.stats()
        assert "processed_run_ids" in stats
        assert "revisions_tracked" in stats
        assert stats["processed_run_ids"] >= 1


# =============================================================================
# TC-C: Relationship Graph
# =============================================================================

class TestTCCRelationshipGraph:
    def test_add_and_traverse_edges(self):
        graph = RelationshipGraph()
        graph.add_edge("condenser-1", "rtu-1", "REJECTS_HEAT_TO")
        graph.add_edge("rack-1", "case-1", "SERVES")
        assert len(graph.get_neighbors("condenser-1")) > 0

    def test_thermal_interaction_group(self):
        graph = RelationshipGraph()
        graph.add_edge("condenser-1", "rtu-1", "REJECTS_HEAT_TO")
        graph.add_edge("condenser-1", "rtu-2", "REJECTS_HEAT_TO")
        group = graph.get_thermal_interaction_group("condenser-1")
        assert len(group) >= 2

    def test_cross_asset_kpi_dependencies(self):
        graph = RelationshipGraph()
        graph.add_edge("condenser-1", "rtu-1", "REJECTS_HEAT_TO")
        graph.add_edge("rack-1", "case-1", "SERVES")
        deps = graph.find_cross_asset_kpi_dependencies()
        assert isinstance(deps, dict)
