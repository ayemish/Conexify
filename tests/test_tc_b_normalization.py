"""
TC-B: Normalization, Identity Resolution & Semantic Layer (TC-B01–B03)
"""

import pytest
from loweconex_platform.ingestion.normalizer import (
    IdentityResolver, Normalizer, SchemaMapping, convert_unit,
)
from loweconex_platform.digital_twins.store import TwinStore
from loweconex_platform.semantic.ontology import (
    SemanticModel, SemanticEntity, SemanticRelationship, SemanticTag,
    SemanticValidator, STANDARD_RULES, OntologyFormat,
)


@pytest.fixture
def twin_store():
    return TwinStore()


@pytest.fixture
def identity_resolver():
    return IdentityResolver()


# =============================================================================
# TC-B01: Identity Resolution
# =============================================================================

class TestTCB01IdentityResolution:
    def test_resolve_or_create_asset_new(self, identity_resolver):
        canonical = identity_resolver.resolve_or_create_asset("bms", "EQ-001", "COMP-1", "LOC-1")
        assert canonical == "asset_COMP-1_EQ-001"

    def test_resolve_or_create_asset_existing(self, identity_resolver):
        identity_resolver.register_asset_mapping("bms", "EQ-001", "canonical_asset_1")
        resolved = identity_resolver.resolve_asset("bms", "EQ-001")
        assert resolved == "canonical_asset_1"

    def test_cross_source_convergence(self, identity_resolver):
        identity_resolver.register_asset_mapping("bms", "EQ-001", "canonical_1")
        identity_resolver.register_asset_mapping("cmms", "WO-EQUIP-001", "canonical_1")
        assert identity_resolver.resolve_asset("bms", "EQ-001") == "canonical_1"
        assert identity_resolver.resolve_asset("cmms", "WO-EQUIP-001") == "canonical_1"

    def test_resolve_or_create_location(self, identity_resolver):
        canonical = identity_resolver.resolve_or_create_location("erp", "STORE-100", "COMP-1")
        assert canonical == "loc_COMP-1_STORE-100"

    def test_resolver_stats(self, identity_resolver):
        identity_resolver.register_asset_mapping("bms", "A1", "C1")
        identity_resolver.register_asset_mapping("bms", "A2", "C2")
        identity_resolver.register_location_mapping("erp", "L1", "CL1")
        stats = identity_resolver.stats()
        assert stats["asset_mappings"] == 2
        assert stats["location_mappings"] == 1
        assert "bms" in stats["source_systems"]


# =============================================================================
# TC-B02: Unit Conversion & Mismatch Detection
# =============================================================================

class TestTCB02UnitConversion:
    def test_fahrenheit_to_celsius(self):
        assert abs(convert_unit(72.0, "fahrenheit", "celsius") - 22.22) < 0.1

    def test_psi_to_bar(self):
        assert abs(convert_unit(100.0, "psi", "bar") - 6.895) < 0.01

    def test_kwh_to_mwh(self):
        assert abs(convert_unit(1500.0, "kwh", "mwh") - 1.5) < 0.001

    def test_lbs_to_kg(self):
        assert abs(convert_unit(100.0, "lbs", "kg") - 45.36) < 0.1

    def test_same_unit_returns_same_value(self):
        assert convert_unit(42.0, "celsius", "celsius") == 42.0

    def test_unknown_conversion_returns_original(self):
        result = convert_unit(42.0, "furlongs", "parsecs")
        assert result == 42.0


# =============================================================================
# TC-B03: Semantic Validation
# =============================================================================

class TestTCB03SemanticValidation:
    def test_standard_rules_exist(self):
        assert len(STANDARD_RULES) >= 6
        rule_ids = [r.rule_id for r in STANDARD_RULES]
        assert "rack_serves_cases" in rule_ids
        assert "hvac_serves_zone" in rule_ids
        assert "temp_point_unit" in rule_ids

    def test_semantic_model_add_and_query(self):
        model = SemanticModel()
        entity = SemanticEntity(entity_id="rack-1", entity_type="refrigeration_rack", name="Rack 1")
        model.add_entity(entity)
        assert model.get_entity("rack-1") is not None
        assert model.get_entity("nonexistent") is None

    def test_rack_must_serve_cases_fails_when_missing(self):
        model = SemanticModel()
        rack = SemanticEntity(entity_id="rack-1", entity_type="refrigeration_rack")
        model.add_entity(rack)
        validator = SemanticValidator(model)
        report = validator.validate_all()
        errors = [e for e in report["error_details"] if e["rule_id"] == "rack_serves_cases"]
        assert len(errors) > 0

    def test_rack_serves_cases_passes_with_relationship(self):
        model = SemanticModel()
        rack = SemanticEntity(entity_id="rack-1", entity_type="refrigeration_rack")
        case1 = SemanticEntity(entity_id="case-1", entity_type="refrigeration_case")
        model.add_entity(rack)
        model.add_entity(case1)
        model.add_relationship(SemanticRelationship(
            rel_id="r1", source_id="rack-1", target_id="case-1", rel_type="serves",
        ))
        validator = SemanticValidator(model)
        report = validator.validate_all()
        rack_errors = [e for e in report["error_details"] if e["rule_id"] == "rack_serves_cases"]
        assert len(rack_errors) == 0

    def test_temperature_point_unit_validation(self):
        model = SemanticModel()
        point = SemanticEntity(
            entity_id="pt-1", entity_type="point",
            unit="furlongs", quantity_type="temperature",
        )
        model.add_entity(point)
        validator = SemanticValidator(model)
        report = validator.validate_all()
        unit_errors = [e for e in report["error_details"] if e["rule_id"] == "temp_point_unit"]
        assert len(unit_errors) > 0

    def test_valid_temperature_point_passes(self):
        model = SemanticModel()
        point = SemanticEntity(
            entity_id="pt-1", entity_type="point",
            unit="°F", quantity_type="temperature",
        )
        model.add_entity(point)
        validator = SemanticValidator(model)
        report = validator.validate_all()
        unit_errors = [e for e in report["error_details"] if e["rule_id"] == "temp_point_unit"]
        assert len(unit_errors) == 0

    def test_ontology_format_enum(self):
        assert OntologyFormat.BRICK.value == "brick"
        assert OntologyFormat.HAYSTACK.value == "haystack"
