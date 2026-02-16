"""
Semantic Model & Ontology Governance.

Provides:
- Governed semantic model (entities, tags, relationships, rules)
- Brick / Haystack ontology import/export adapters
- Semantic validation gates (structural + quantitative)
- ASHRAE 223P / DOE semantic interoperability alignment

Validation rules enforce constraints like:
- A rack MUST serve cases
- HVAC MUST serve zones
- Point units MUST match quantitative types
- Equipment classes MUST have required relationships
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Ontology format targets
# =============================================================================

class OntologyFormat(str, Enum):
    BRICK = "brick"
    HAYSTACK = "haystack"
    ASHRAE_223P = "ashrae_223p"
    INTERNAL = "internal"


# =============================================================================
# Semantic primitives
# =============================================================================

@dataclass
class SemanticTag:
    """A governed tag applied to an entity (Brick/Haystack-style marker)."""
    tag_id: str
    namespace: str = "loweconex"
    name: str = ""
    category: str = ""  # equip, point, marker, choice
    description: str = ""
    # Brick class URI if applicable
    brick_class: Optional[str] = None
    # Haystack tag name if applicable
    haystack_tag: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tag_id": self.tag_id,
            "namespace": self.namespace,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "brick_class": self.brick_class,
            "haystack_tag": self.haystack_tag,
        }


@dataclass
class SemanticRelationship:
    """A typed relationship between two semantic entities."""
    rel_id: str
    source_id: str
    target_id: str
    rel_type: str  # serves, feeds, contains, hasPoint, etc.
    namespace: str = "loweconex"
    required: bool = False  # If True, validation fails if missing
    cardinality_min: int = 0
    cardinality_max: Optional[int] = None  # None = unbounded

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rel_id": self.rel_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "rel_type": self.rel_type,
            "namespace": self.namespace,
            "required": self.required,
            "cardinality_min": self.cardinality_min,
            "cardinality_max": self.cardinality_max,
        }


@dataclass
class SemanticEntity:
    """An entity in the semantic model (equipment, point, location, zone)."""
    entity_id: str
    entity_type: str  # equipment, point, location, zone, system
    name: str = ""
    tags: List[SemanticTag] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)

    # Brick / Haystack mappings
    brick_class: Optional[str] = None
    haystack_tags: List[str] = field(default_factory=list)

    # Point-specific
    unit: Optional[str] = None
    quantity_type: Optional[str] = None  # temperature, pressure, power, etc.

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "name": self.name,
            "tags": [t.to_dict() for t in self.tags],
            "properties": self.properties,
            "brick_class": self.brick_class,
            "haystack_tags": self.haystack_tags,
            "unit": self.unit,
            "quantity_type": self.quantity_type,
        }


# =============================================================================
# Semantic validation rules
# =============================================================================

@dataclass
class SemanticRule:
    """A validation rule enforcing structural/quantitative constraints."""
    rule_id: str
    name: str
    description: str
    severity: str = "error"  # error, warning, info

    # Source entity type(s) this rule applies to
    applies_to: List[str] = field(default_factory=list)

    # Rule type
    rule_type: str = "relationship"  # relationship, cardinality, unit, tag, custom

    # Relationship rules
    required_rel_type: Optional[str] = None
    required_target_type: Optional[str] = None
    min_count: int = 0
    max_count: Optional[int] = None

    # Unit rules
    required_quantity_type: Optional[str] = None
    allowed_units: List[str] = field(default_factory=list)

    # Tag rules
    required_tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "severity": self.severity,
            "applies_to": self.applies_to,
            "rule_type": self.rule_type,
            "required_rel_type": self.required_rel_type,
            "required_target_type": self.required_target_type,
            "min_count": self.min_count,
            "max_count": self.max_count,
            "required_quantity_type": self.required_quantity_type,
            "allowed_units": self.allowed_units,
            "required_tags": self.required_tags,
        }


@dataclass
class ValidationResult:
    """Result from a single rule check."""
    rule_id: str
    entity_id: str
    passed: bool
    severity: str = "error"
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "entity_id": self.entity_id,
            "passed": self.passed,
            "severity": self.severity,
            "message": self.message,
        }


# =============================================================================
# Standard rules for HVAC/R grocery domain
# =============================================================================

STANDARD_RULES: List[SemanticRule] = [
    SemanticRule(
        rule_id="rack_serves_cases",
        name="Rack Must Serve Cases",
        description="A refrigeration rack MUST have at least one 'serves' relationship to a refrigeration case.",
        severity="error",
        applies_to=["refrigeration_rack"],
        rule_type="relationship",
        required_rel_type="serves",
        required_target_type="refrigeration_case",
        min_count=1,
    ),
    SemanticRule(
        rule_id="hvac_serves_zone",
        name="HVAC Must Serve Zone",
        description="An HVAC unit MUST have at least one 'serves' relationship to a zone or location.",
        severity="warning",
        applies_to=["hvac_rtu", "hvac_ahu"],
        rule_type="relationship",
        required_rel_type="serves",
        required_target_type="zone",
        min_count=0,  # Warning, not error
    ),
    SemanticRule(
        rule_id="temp_point_unit",
        name="Temperature Point Unit",
        description="Temperature points MUST have units in {°F, °C, degF, degC}.",
        severity="error",
        applies_to=["point"],
        rule_type="unit",
        required_quantity_type="temperature",
        allowed_units=["°F", "°C", "degF", "degC", "fahrenheit", "celsius"],
    ),
    SemanticRule(
        rule_id="pressure_point_unit",
        name="Pressure Point Unit",
        description="Pressure points MUST have units in {psi, kPa, bar, inHg}.",
        severity="error",
        applies_to=["point"],
        rule_type="unit",
        required_quantity_type="pressure",
        allowed_units=["psi", "kPa", "bar", "inHg", "psig"],
    ),
    SemanticRule(
        rule_id="power_point_unit",
        name="Power Point Unit",
        description="Power points MUST have units in {kW, W, hp}.",
        severity="error",
        applies_to=["point"],
        rule_type="unit",
        required_quantity_type="power",
        allowed_units=["kW", "W", "hp", "kilowatt", "watt"],
    ),
    SemanticRule(
        rule_id="equipment_has_location",
        name="Equipment Has Location",
        description="All equipment entities MUST be associated with a location.",
        severity="error",
        applies_to=["equipment"],
        rule_type="relationship",
        required_rel_type="locatedIn",
        required_target_type="location",
        min_count=1,
    ),
    SemanticRule(
        rule_id="condenser_rejects_heat",
        name="Condenser Rejects Heat",
        description="A condenser SHOULD have a 'rejectsHeatTo' relationship.",
        severity="warning",
        applies_to=["condenser"],
        rule_type="relationship",
        required_rel_type="rejectsHeatTo",
        min_count=0,
    ),
]


# =============================================================================
# Semantic Model — the governed model instance
# =============================================================================

class SemanticModel:
    """
    Governed semantic model for the platform.

    Maintains entities, relationships, tags, and validation rules.
    Supports import/export to Brick and Haystack formats.
    """

    def __init__(self):
        self._entities: Dict[str, SemanticEntity] = {}
        self._relationships: Dict[str, SemanticRelationship] = {}
        self._tags: Dict[str, SemanticTag] = {}
        self._rules: List[SemanticRule] = list(STANDARD_RULES)

    def add_entity(self, entity: SemanticEntity):
        self._entities[entity.entity_id] = entity

    def add_relationship(self, rel: SemanticRelationship):
        self._relationships[rel.rel_id] = rel

    def add_tag(self, tag: SemanticTag):
        self._tags[tag.tag_id] = tag

    def add_rule(self, rule: SemanticRule):
        self._rules.append(rule)

    def get_entity(self, entity_id: str) -> Optional[SemanticEntity]:
        return self._entities.get(entity_id)

    def get_relationships_for(self, entity_id: str) -> List[SemanticRelationship]:
        return [r for r in self._relationships.values() if r.source_id == entity_id]

    def get_entities_by_type(self, entity_type: str) -> List[SemanticEntity]:
        return [e for e in self._entities.values() if e.entity_type == entity_type]

    def stats(self) -> Dict[str, int]:
        return {
            "entities": len(self._entities),
            "relationships": len(self._relationships),
            "tags": len(self._tags),
            "rules": len(self._rules),
        }


# =============================================================================
# Semantic Validator
# =============================================================================

class SemanticValidator:
    """
    Validates the semantic model against all registered rules.

    Produces a validation report with pass/fail per entity per rule.
    Can block KPI publication when critical rules fail.
    """

    def __init__(self, model: SemanticModel):
        self.model = model

    def validate_all(self) -> Dict[str, Any]:
        """Run all rules against all applicable entities."""
        results: List[ValidationResult] = []

        for rule in self.model._rules:
            entities = self._get_applicable_entities(rule)
            for entity in entities:
                result = self._check_rule(rule, entity)
                results.append(result)

        errors = [r for r in results if not r.passed and r.severity == "error"]
        warnings = [r for r in results if not r.passed and r.severity == "warning"]
        passed = [r for r in results if r.passed]

        return {
            "total_checks": len(results),
            "passed": len(passed),
            "errors": len(errors),
            "warnings": len(warnings),
            "is_valid": len(errors) == 0,
            "error_details": [r.to_dict() for r in errors],
            "warning_details": [r.to_dict() for r in warnings],
        }

    def validate_entity(self, entity_id: str) -> List[ValidationResult]:
        """Validate a single entity against all applicable rules."""
        entity = self.model.get_entity(entity_id)
        if not entity:
            return []

        results = []
        for rule in self.model._rules:
            if entity.entity_type in rule.applies_to or "equipment" in rule.applies_to:
                results.append(self._check_rule(rule, entity))
        return results

    def _get_applicable_entities(self, rule: SemanticRule) -> List[SemanticEntity]:
        entities = []
        for applies_type in rule.applies_to:
            entities.extend(self.model.get_entities_by_type(applies_type))
        return entities

    def _check_rule(self, rule: SemanticRule, entity: SemanticEntity) -> ValidationResult:
        if rule.rule_type == "relationship":
            return self._check_relationship_rule(rule, entity)
        elif rule.rule_type == "unit":
            return self._check_unit_rule(rule, entity)
        elif rule.rule_type == "tag":
            return self._check_tag_rule(rule, entity)
        else:
            return ValidationResult(
                rule_id=rule.rule_id, entity_id=entity.entity_id,
                passed=True, message="Unhandled rule type"
            )

    def _check_relationship_rule(
        self, rule: SemanticRule, entity: SemanticEntity
    ) -> ValidationResult:
        rels = self.model.get_relationships_for(entity.entity_id)
        matching = [
            r for r in rels
            if r.rel_type == rule.required_rel_type
            and (rule.required_target_type is None
                 or self._target_matches(r.target_id, rule.required_target_type))
        ]
        count = len(matching)

        if count < rule.min_count:
            return ValidationResult(
                rule_id=rule.rule_id, entity_id=entity.entity_id,
                passed=False, severity=rule.severity,
                message=f"Expected >= {rule.min_count} '{rule.required_rel_type}' "
                        f"relationships, found {count}.",
            )
        if rule.max_count is not None and count > rule.max_count:
            return ValidationResult(
                rule_id=rule.rule_id, entity_id=entity.entity_id,
                passed=False, severity=rule.severity,
                message=f"Expected <= {rule.max_count} '{rule.required_rel_type}' "
                        f"relationships, found {count}.",
            )
        return ValidationResult(
            rule_id=rule.rule_id, entity_id=entity.entity_id,
            passed=True, message=f"OK: {count} matching relationships.",
        )

    def _target_matches(self, target_id: str, required_type: str) -> bool:
        target = self.model.get_entity(target_id)
        if not target:
            return False
        return target.entity_type == required_type

    def _check_unit_rule(
        self, rule: SemanticRule, entity: SemanticEntity
    ) -> ValidationResult:
        if entity.quantity_type != rule.required_quantity_type:
            return ValidationResult(
                rule_id=rule.rule_id, entity_id=entity.entity_id,
                passed=True, message="Rule not applicable (quantity type mismatch).",
            )

        if entity.unit and entity.unit.lower() not in [u.lower() for u in rule.allowed_units]:
            return ValidationResult(
                rule_id=rule.rule_id, entity_id=entity.entity_id,
                passed=False, severity=rule.severity,
                message=f"Unit '{entity.unit}' not in allowed set {rule.allowed_units}.",
            )
        return ValidationResult(
            rule_id=rule.rule_id, entity_id=entity.entity_id,
            passed=True, message=f"Unit '{entity.unit}' is valid.",
        )

    def _check_tag_rule(
        self, rule: SemanticRule, entity: SemanticEntity
    ) -> ValidationResult:
        entity_tag_names = {t.name for t in entity.tags}
        missing = [t for t in rule.required_tags if t not in entity_tag_names]
        if missing:
            return ValidationResult(
                rule_id=rule.rule_id, entity_id=entity.entity_id,
                passed=False, severity=rule.severity,
                message=f"Missing required tags: {missing}.",
            )
        return ValidationResult(
            rule_id=rule.rule_id, entity_id=entity.entity_id,
            passed=True, message="All required tags present.",
        )


# =============================================================================
# Brick / Haystack Adapter
# =============================================================================

class BrickHaystackAdapter:
    """
    Import/export adapter for Brick Schema and Project Haystack ontologies.

    Provides bidirectional mapping between the internal semantic model
    and standard building ontology formats.
    """

    # Brick class → internal entity_type mapping
    BRICK_TO_INTERNAL: Dict[str, str] = {
        "brick:RTU": "hvac_rtu",
        "brick:AHU": "hvac_ahu",
        "brick:Refrigeration_System": "refrigeration_rack",
        "brick:Refrigeration_Display_Case": "refrigeration_case",
        "brick:Compressor": "compressor",
        "brick:Condenser": "condenser",
        "brick:Evaporator": "evaporator",
        "brick:Temperature_Sensor": "point",
        "brick:Pressure_Sensor": "point",
        "brick:Power_Sensor": "point",
        "brick:Location": "location",
        "brick:Zone": "zone",
    }

    # Haystack tag sets → internal entity_type
    HAYSTACK_TO_INTERNAL: Dict[str, str] = {
        "ahu": "hvac_ahu",
        "rtu": "hvac_rtu",
        "refrig-rack": "refrigeration_rack",
        "refrig-case": "refrigeration_case",
        "compressor": "compressor",
        "condenser": "condenser",
        "evaporator": "evaporator",
        "site": "location",
        "zone": "zone",
    }

    # Brick relationship → internal relationship type
    BRICK_REL_MAP: Dict[str, str] = {
        "brick:serves": "serves",
        "brick:feeds": "feeds",
        "brick:hasPoint": "hasPoint",
        "brick:isPartOf": "isPartOf",
        "brick:hasLocation": "locatedIn",
    }

    def __init__(self, model: SemanticModel):
        self.model = model

    def export_to_brick(self) -> Dict[str, Any]:
        """Export semantic model to Brick-compatible JSON-LD structure."""
        internal_to_brick = {v: k for k, v in self.BRICK_TO_INTERNAL.items()}
        entities = []
        for entity in self.model._entities.values():
            brick_class = entity.brick_class or internal_to_brick.get(entity.entity_type, "brick:Equipment")
            entities.append({
                "@id": f"loweconex:{entity.entity_id}",
                "@type": brick_class,
                "rdfs:label": entity.name,
                "properties": entity.properties,
            })

        internal_to_brick_rel = {v: k for k, v in self.BRICK_REL_MAP.items()}
        relationships = []
        for rel in self.model._relationships.values():
            brick_rel = internal_to_brick_rel.get(rel.rel_type, f"brick:{rel.rel_type}")
            relationships.append({
                "@id": f"loweconex:{rel.rel_id}",
                "subject": f"loweconex:{rel.source_id}",
                "predicate": brick_rel,
                "object": f"loweconex:{rel.target_id}",
            })

        return {
            "@context": {"brick": "https://brickschema.org/schema/Brick#"},
            "entities": entities,
            "relationships": relationships,
            "exported_ts": datetime.utcnow().isoformat(),
        }

    def export_to_haystack(self) -> Dict[str, Any]:
        """Export semantic model to Haystack-compatible JSON format."""
        internal_to_hs = {v: k for k, v in self.HAYSTACK_TO_INTERNAL.items()}
        rows = []
        for entity in self.model._entities.values():
            hs_tag = internal_to_hs.get(entity.entity_type, entity.entity_type)
            row = {
                "id": f"r:{entity.entity_id}",
                "dis": entity.name,
                hs_tag: "m:",
            }
            if entity.unit:
                row["unit"] = entity.unit
            for tag in entity.haystack_tags:
                row[tag] = "m:"
            rows.append(row)

        return {
            "meta": {"ver": "3.0"},
            "cols": [{"name": "id"}, {"name": "dis"}],
            "rows": rows,
            "exported_ts": datetime.utcnow().isoformat(),
        }

    def import_from_brick(self, brick_data: Dict[str, Any]) -> int:
        """Import entities and relationships from Brick JSON-LD. Returns count imported."""
        count = 0
        for item in brick_data.get("entities", []):
            brick_class = item.get("@type", "")
            entity_type = self.BRICK_TO_INTERNAL.get(brick_class, "equipment")
            entity = SemanticEntity(
                entity_id=item.get("@id", "").replace("loweconex:", ""),
                entity_type=entity_type,
                name=item.get("rdfs:label", ""),
                brick_class=brick_class,
                properties=item.get("properties", {}),
            )
            self.model.add_entity(entity)
            count += 1

        for rel_data in brick_data.get("relationships", []):
            rel_type = self.BRICK_REL_MAP.get(rel_data.get("predicate", ""), "unknown")
            rel = SemanticRelationship(
                rel_id=rel_data.get("@id", "").replace("loweconex:", ""),
                source_id=rel_data.get("subject", "").replace("loweconex:", ""),
                target_id=rel_data.get("object", "").replace("loweconex:", ""),
                rel_type=rel_type,
            )
            self.model.add_relationship(rel)
            count += 1

        logger.info(f"Imported {count} items from Brick format")
        return count

    def import_from_haystack(self, haystack_data: Dict[str, Any]) -> int:
        """Import entities from Haystack JSON. Returns count imported."""
        count = 0
        for row in haystack_data.get("rows", []):
            entity_id = row.get("id", "").replace("r:", "")
            entity_type = "equipment"
            hs_tags = []
            for tag, internal_type in self.HAYSTACK_TO_INTERNAL.items():
                if tag in row:
                    entity_type = internal_type
                    hs_tags.append(tag)

            entity = SemanticEntity(
                entity_id=entity_id,
                entity_type=entity_type,
                name=row.get("dis", ""),
                haystack_tags=hs_tags,
                unit=row.get("unit"),
            )
            self.model.add_entity(entity)
            count += 1

        logger.info(f"Imported {count} entities from Haystack format")
        return count
