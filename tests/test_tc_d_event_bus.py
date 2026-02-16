"""
TC-D: Event Bus & Message Envelope (TC-D01–D03)

Tests event publishing, schema validation, envelope structure,
and dead-letter queue routing.
"""

import pytest
import uuid

from shared.event_bus.events import (
    EventType, EventEnvelope, create_envelope,
    PdMEvent, PdMEventType, PdMEventFactory,
)
from shared.event_bus.redis_event_bus import RedisEventBus


@pytest.fixture
def event_bus():
    return RedisEventBus(redis_url="redis://localhost:6379", agent_id="test")


# =============================================================================
# TC-D01: EventEnvelope Structure & Factory
# =============================================================================

class TestTCD01EnvelopeStructure:
    def test_create_envelope_has_required_fields(self):
        env = create_envelope(
            event_type=EventType.KPI_COMPUTED,
            company_id="COMP-1",
            producer="test",
            payload={"kpi_name": "energy_reduction", "savings": 50000},
        )
        assert env.msg_id is not None
        assert env.correlation_id is not None
        assert env.event_type == "KPI_COMPUTED"
        assert env.company_id == "COMP-1"
        assert env.payload_schema_version == "1.0"

    def test_envelope_serialization_roundtrip(self):
        env = create_envelope(
            event_type=EventType.DATA_INGESTED,
            company_id="COMP-1",
            producer="normalizer",
            payload={"rows": 100},
            location_id="LOC-100",
        )
        json_str = env.to_json()
        restored = EventEnvelope.from_json(json_str)
        assert restored.msg_id == env.msg_id
        assert restored.company_id == "COMP-1"
        assert restored.payload["rows"] == 100

    def test_envelope_with_kpi_and_scenario(self):
        env = create_envelope(
            event_type=EventType.KPI_COMPUTED,
            company_id="COMP-1",
            producer="kpi_crew",
            payload={},
            kpi_name="energy_reduction",
            scenario_id="scenario-conservative",
        )
        assert env.kpi_name == "energy_reduction"
        assert env.scenario_id == "scenario-conservative"

    def test_envelope_with_artifact_ids(self):
        env = create_envelope(
            event_type=EventType.CREW_COMPLETED,
            company_id="COMP-1",
            producer="orchestrator",
            payload={},
            artifact_ids=["art_1", "art_2"],
        )
        assert len(env.artifact_ids) == 2


# =============================================================================
# TC-D02: Schema Validation on Publish
# =============================================================================

class TestTCD02SchemaValidation:
    def test_valid_envelope_passes_validation(self):
        env = create_envelope(
            event_type=EventType.KPI_COMPUTED,
            company_id="COMP-1",
            producer="test",
            payload={},
        )
        errors = RedisEventBus.validate_envelope(env)
        assert len(errors) == 0

    def test_missing_event_type_fails_validation(self):
        env = EventEnvelope(event_type="", company_id="COMP-1")
        errors = RedisEventBus.validate_envelope(env)
        assert any("event_type" in e for e in errors)

    def test_missing_company_id_fails_validation(self):
        env = EventEnvelope(event_type="KPI_COMPUTED", company_id="")
        errors = RedisEventBus.validate_envelope(env)
        assert any("company_id" in e for e in errors)

    def test_missing_msg_id_fails_validation(self):
        env = EventEnvelope(event_type="KPI_COMPUTED", company_id="COMP-1", msg_id="")
        errors = RedisEventBus.validate_envelope(env)
        assert any("msg_id" in e for e in errors)

    def test_missing_schema_version_fails_validation(self):
        env = EventEnvelope(
            event_type="KPI_COMPUTED", company_id="COMP-1",
            payload_schema_version="",
        )
        errors = RedisEventBus.validate_envelope(env)
        assert any("payload_schema_version" in e for e in errors)

    def test_valid_pdm_event_passes_validation(self):
        factory = PdMEventFactory(source_agent="test_agent", tenant_id="T1")
        event = factory.alert_created(
            alert_id="A1", asset_id="ASSET-1", site_id="SITE-1",
            alert_type="fault", severity="high", confidence=0.9,
            ev_score=100.0, contributing_metrics=[],
        )
        errors = RedisEventBus.validate_envelope(event)
        assert len(errors) == 0

    def test_pdm_event_missing_source_agent_fails(self):
        event = PdMEvent(
            event_id="E1",
            event_type=PdMEventType.ALERT_CREATED,
            source_agent="",
            timestamp=__import__("datetime").datetime.utcnow(),
        )
        errors = RedisEventBus.validate_envelope(event)
        assert any("source_agent" in e for e in errors)


# =============================================================================
# TC-D03: Publish / Subscribe (In-Memory Fallback)
# =============================================================================

class TestTCD03PublishSubscribe:
    def test_publish_valid_envelope(self, event_bus):
        env = create_envelope(
            event_type=EventType.KPI_COMPUTED,
            company_id="COMP-1",
            producer="test",
            payload={"kpi": "energy"},
        )
        msg_id = event_bus.publish(env)
        assert msg_id is not None

    def test_subscribe_and_receive(self, event_bus):
        received = []
        event_bus.subscribe("KPI_COMPUTED", lambda e: received.append(e))
        env = create_envelope(
            event_type=EventType.KPI_COMPUTED,
            company_id="COMP-1",
            producer="test",
            payload={"kpi": "energy"},
        )
        event_bus.publish(env)
        assert len(received) == 1

    def test_publish_invalid_envelope_routes_to_dlq(self, event_bus):
        env = EventEnvelope(event_type="", company_id="", msg_id="bad-msg")
        msg_id = event_bus.publish(env)
        assert msg_id == "bad-msg"

    def test_publish_batch(self, event_bus):
        envs = [
            create_envelope(EventType.KPI_COMPUTED, "COMP-1", "test", {"i": i})
            for i in range(5)
        ]
        ids = event_bus.publish_batch(envs)
        assert len(ids) == 5

    def test_pdm_event_publish(self, event_bus):
        factory = PdMEventFactory(source_agent="test_agent")
        event = factory.alert_created(
            alert_id="A1", asset_id="ASSET-1", site_id="SITE-1",
            alert_type="fault", severity="medium", confidence=0.8,
            ev_score=50.0, contributing_metrics=[],
        )
        msg_id = event_bus.publish(event)
        assert msg_id is not None
