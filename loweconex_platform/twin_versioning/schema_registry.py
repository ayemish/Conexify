"""
Twin Model Versioning — Schema Registry, Migrations & Compatibility.

DTDL-inspired approach for managing twin schema evolution:
- Versioned schema definitions for Asset, Location, Estate twins
- KPI input/output schema contracts with backward-compatibility enforcement
- Migration engine with ordered up/down transforms
- Deprecation policy (warn → block lifecycle)

References:
- Azure DTDL (Digital Twin Definition Language) for model versioning
- Avro schema evolution rules for compatibility semantics
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Schema version model
# =============================================================================

class CompatibilityMode(str, Enum):
    """Compatibility enforcement modes (Avro-style semantics)."""
    NONE = "none"                  # No checks
    BACKWARD = "backward"          # New schema can read old data
    FORWARD = "forward"            # Old schema can read new data
    FULL = "full"                  # Both directions
    BACKWARD_TRANSITIVE = "backward_transitive"
    FULL_TRANSITIVE = "full_transitive"


class DeprecationStage(str, Enum):
    """Lifecycle stages for deprecated schema versions."""
    ACTIVE = "active"
    DEPRECATED = "deprecated"       # Warn on use
    BLOCKED = "blocked"             # Reject on use
    RETIRED = "retired"             # Removed from registry


@dataclass
class SchemaField:
    """A single field in a schema definition."""
    name: str
    field_type: str              # string, float, int, bool, datetime, dict, list
    required: bool = False
    default: Any = None
    description: str = ""
    unit: Optional[str] = None
    constraints: Dict[str, Any] = field(default_factory=dict)  # min, max, enum, pattern

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "field_type": self.field_type,
            "required": self.required,
            "default": self.default,
            "description": self.description,
            "unit": self.unit,
            "constraints": self.constraints,
        }


@dataclass
class SchemaVersion:
    """
    A versioned schema definition (DTDL-inspired model).

    Tracks fields, compatibility, and deprecation lifecycle.
    """
    schema_id: str
    model_name: str             # e.g., "AssetTwin", "LocationTwin", "KPI_energy_waste"
    version: str                # semver: "1.0.0", "1.1.0", "2.0.0"
    fields: List[SchemaField] = field(default_factory=list)

    # Metadata
    description: str = ""
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_by: str = ""
    changelog: str = ""

    # Lifecycle
    stage: str = DeprecationStage.ACTIVE.value
    deprecated_ts: Optional[str] = None
    blocked_ts: Optional[str] = None
    sunset_date: Optional[str] = None    # Date after which BLOCKED

    # Compatibility
    compatibility_mode: str = CompatibilityMode.BACKWARD.value
    previous_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "model_name": self.model_name,
            "version": self.version,
            "fields": [f.to_dict() for f in self.fields],
            "description": self.description,
            "created_ts": self.created_ts,
            "created_by": self.created_by,
            "changelog": self.changelog,
            "stage": self.stage,
            "deprecated_ts": self.deprecated_ts,
            "blocked_ts": self.blocked_ts,
            "sunset_date": self.sunset_date,
            "compatibility_mode": self.compatibility_mode,
            "previous_version": self.previous_version,
        }

    @property
    def field_names(self) -> Set[str]:
        return {f.name for f in self.fields}

    @property
    def required_fields(self) -> Set[str]:
        return {f.name for f in self.fields if f.required}


# =============================================================================
# Schema contracts for KPI inputs/outputs
# =============================================================================

@dataclass
class SchemaContract:
    """
    A contract binding a KPI to specific input/output schemas.

    Enforces that KPI calculations always receive and produce data
    conforming to declared schemas with backward compatibility.
    """
    contract_id: str
    kpi_name: str
    input_schema_id: str          # SchemaVersion.schema_id for inputs
    output_schema_id: str         # SchemaVersion.schema_id for outputs
    min_input_version: str = "1.0.0"
    max_input_version: Optional[str] = None
    enforced: bool = True
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "kpi_name": self.kpi_name,
            "input_schema_id": self.input_schema_id,
            "output_schema_id": self.output_schema_id,
            "min_input_version": self.min_input_version,
            "max_input_version": self.max_input_version,
            "enforced": self.enforced,
            "created_ts": self.created_ts,
        }


# =============================================================================
# Migration engine
# =============================================================================

@dataclass
class MigrationStep:
    """
    A single migration transform between two schema versions.
    """
    migration_id: str
    model_name: str
    from_version: str
    to_version: str
    description: str = ""

    # Transform functions (operate on a dict representing one record)
    up_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
    down_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None

    # If True, migration is reversible
    reversible: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "migration_id": self.migration_id,
            "model_name": self.model_name,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "description": self.description,
            "reversible": self.reversible,
        }


class MigrationEngine:
    """
    Executes ordered schema migrations on twin data.

    Given a record at version A, finds the migration path to version B
    and applies each step sequentially.
    """

    def __init__(self):
        self._steps: Dict[str, List[MigrationStep]] = {}  # model_name → steps

    def register_step(self, step: MigrationStep):
        if step.model_name not in self._steps:
            self._steps[step.model_name] = []
        self._steps[step.model_name].append(step)
        logger.debug(
            f"Registered migration: {step.model_name} "
            f"{step.from_version} → {step.to_version}"
        )

    def migrate(
        self,
        model_name: str,
        record: Dict[str, Any],
        from_version: str,
        to_version: str,
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Migrate a record from from_version to to_version.

        Returns (migrated_record, list_of_applied_migration_ids).
        """
        path = self._find_path(model_name, from_version, to_version)
        if path is None:
            raise ValueError(
                f"No migration path found: {model_name} {from_version} → {to_version}"
            )

        result = copy.deepcopy(record)
        applied = []

        for step in path:
            if step.up_fn:
                result = step.up_fn(result)
                applied.append(step.migration_id)
                logger.debug(f"Applied migration {step.migration_id}")

        return result, applied

    def rollback(
        self,
        model_name: str,
        record: Dict[str, Any],
        from_version: str,
        to_version: str,
    ) -> Tuple[Dict[str, Any], List[str]]:
        """Reverse-migrate a record (requires reversible steps)."""
        path = self._find_path(model_name, from_version, to_version)
        if path is None:
            # Try reverse direction
            path = self._find_path(model_name, to_version, from_version)
            if path is None:
                raise ValueError(f"No rollback path found")
            path = list(reversed(path))

        result = copy.deepcopy(record)
        applied = []

        for step in path:
            if not step.reversible or not step.down_fn:
                raise ValueError(
                    f"Migration {step.migration_id} is not reversible"
                )
            result = step.down_fn(result)
            applied.append(step.migration_id)

        return result, applied

    def _find_path(
        self, model_name: str, from_v: str, to_v: str
    ) -> Optional[List[MigrationStep]]:
        """Find ordered migration path using BFS."""
        steps = self._steps.get(model_name, [])
        if not steps:
            return None

        # Build adjacency: version → [(next_version, step)]
        adj: Dict[str, List[Tuple[str, MigrationStep]]] = {}
        for s in steps:
            if s.from_version not in adj:
                adj[s.from_version] = []
            adj[s.from_version].append((s.to_version, s))

        # BFS
        from collections import deque
        queue = deque([(from_v, [])])
        visited = {from_v}

        while queue:
            current, path = queue.popleft()
            if current == to_v:
                return path

            for next_v, step in adj.get(current, []):
                if next_v not in visited:
                    visited.add(next_v)
                    queue.append((next_v, path + [step]))

        return None

    def get_all_steps(self, model_name: str) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self._steps.get(model_name, [])]


# =============================================================================
# Compatibility checker
# =============================================================================

class CompatibilityChecker:
    """
    Checks whether a new schema version is compatible with the previous
    version according to the declared compatibility mode.

    Rules (backward compatibility):
    - New required fields without defaults → BREAKING
    - Removing a field → BREAKING
    - Changing a field type → BREAKING
    - Adding optional fields → OK
    - Widening constraints → OK
    """

    @staticmethod
    def check(
        old: SchemaVersion,
        new: SchemaVersion,
        mode: CompatibilityMode = CompatibilityMode.BACKWARD,
    ) -> Dict[str, Any]:
        issues = []

        if mode in (CompatibilityMode.BACKWARD, CompatibilityMode.FULL,
                     CompatibilityMode.BACKWARD_TRANSITIVE, CompatibilityMode.FULL_TRANSITIVE):
            issues.extend(CompatibilityChecker._check_backward(old, new))

        if mode in (CompatibilityMode.FORWARD, CompatibilityMode.FULL,
                     CompatibilityMode.FULL_TRANSITIVE):
            issues.extend(CompatibilityChecker._check_forward(old, new))

        breaking = [i for i in issues if i["severity"] == "breaking"]
        warnings = [i for i in issues if i["severity"] == "warning"]

        return {
            "compatible": len(breaking) == 0,
            "breaking_changes": breaking,
            "warnings": warnings,
            "old_version": old.version,
            "new_version": new.version,
            "mode": mode.value,
        }

    @staticmethod
    def _check_backward(old: SchemaVersion, new: SchemaVersion) -> List[Dict[str, Any]]:
        """New schema must be able to read old data."""
        issues = []
        old_map = {f.name: f for f in old.fields}
        new_map = {f.name: f for f in new.fields}

        # New required fields without defaults
        for name, nf in new_map.items():
            if name not in old_map and nf.required and nf.default is None:
                issues.append({
                    "severity": "breaking",
                    "field": name,
                    "message": f"New required field '{name}' has no default; "
                               f"old data cannot satisfy this.",
                })

        # Removed fields
        for name in old_map:
            if name not in new_map:
                issues.append({
                    "severity": "breaking",
                    "field": name,
                    "message": f"Field '{name}' removed in new version.",
                })

        # Type changes
        for name in old_map:
            if name in new_map:
                if old_map[name].field_type != new_map[name].field_type:
                    issues.append({
                        "severity": "breaking",
                        "field": name,
                        "message": f"Field '{name}' type changed from "
                                   f"'{old_map[name].field_type}' to "
                                   f"'{new_map[name].field_type}'.",
                    })

        return issues

    @staticmethod
    def _check_forward(old: SchemaVersion, new: SchemaVersion) -> List[Dict[str, Any]]:
        """Old schema must be able to read new data."""
        issues = []
        old_map = {f.name: f for f in old.fields}
        new_map = {f.name: f for f in new.fields}

        # Fields in new but not in old (old readers won't know about them)
        for name in new_map:
            if name not in old_map:
                issues.append({
                    "severity": "warning",
                    "field": name,
                    "message": f"New field '{name}' unknown to old readers.",
                })

        return issues


# =============================================================================
# Schema registry
# =============================================================================

class SchemaRegistry:
    """
    Central registry for all twin model schemas, contracts, and migrations.

    Enforces:
    - Version ordering
    - Compatibility checks on registration
    - Deprecation lifecycle
    - Contract binding for KPI I/O
    """

    def __init__(self, default_mode: CompatibilityMode = CompatibilityMode.BACKWARD):
        self._schemas: Dict[str, SchemaVersion] = {}  # schema_id → version
        self._by_model: Dict[str, List[str]] = {}     # model_name → [schema_ids]
        self._contracts: Dict[str, SchemaContract] = {}
        self._migration_engine = MigrationEngine()
        self._default_mode = default_mode

    def register_schema(
        self, schema: SchemaVersion, check_compat: bool = True
    ) -> Dict[str, Any]:
        """
        Register a new schema version.

        Optionally checks compatibility against the previous version.
        """
        if schema.schema_id in self._schemas:
            return {"status": "already_exists", "schema_id": schema.schema_id}

        # Compatibility check
        compat_result = None
        if check_compat and schema.previous_version:
            prev = self._schemas.get(schema.previous_version)
            if prev:
                mode = CompatibilityMode(schema.compatibility_mode)
                compat_result = CompatibilityChecker.check(prev, schema, mode)
                if not compat_result["compatible"]:
                    logger.warning(
                        f"Schema {schema.schema_id} has breaking changes "
                        f"vs {schema.previous_version}"
                    )
                    return {
                        "status": "incompatible",
                        "schema_id": schema.schema_id,
                        "compatibility": compat_result,
                    }

        self._schemas[schema.schema_id] = schema
        if schema.model_name not in self._by_model:
            self._by_model[schema.model_name] = []
        self._by_model[schema.model_name].append(schema.schema_id)

        logger.info(f"Registered schema: {schema.model_name} v{schema.version}")
        return {
            "status": "registered",
            "schema_id": schema.schema_id,
            "compatibility": compat_result,
        }

    def get_schema(self, schema_id: str) -> Optional[SchemaVersion]:
        return self._schemas.get(schema_id)

    def get_latest(self, model_name: str) -> Optional[SchemaVersion]:
        """Get the latest ACTIVE schema for a model."""
        ids = self._by_model.get(model_name, [])
        active = [
            self._schemas[sid] for sid in ids
            if self._schemas[sid].stage == DeprecationStage.ACTIVE.value
        ]
        if not active:
            return None
        return max(active, key=lambda s: s.version)

    def deprecate(self, schema_id: str, sunset_date: Optional[str] = None):
        """Mark a schema as deprecated (warn on use)."""
        schema = self._schemas.get(schema_id)
        if schema:
            schema.stage = DeprecationStage.DEPRECATED.value
            schema.deprecated_ts = datetime.utcnow().isoformat()
            schema.sunset_date = sunset_date
            logger.info(f"Deprecated schema: {schema_id}")

    def block(self, schema_id: str):
        """Block a schema (reject on use)."""
        schema = self._schemas.get(schema_id)
        if schema:
            schema.stage = DeprecationStage.BLOCKED.value
            schema.blocked_ts = datetime.utcnow().isoformat()
            logger.info(f"Blocked schema: {schema_id}")

    def register_contract(self, contract: SchemaContract):
        self._contracts[contract.contract_id] = contract

    def validate_contract(
        self, kpi_name: str, input_version: str, output_version: str
    ) -> Dict[str, Any]:
        """Check if KPI I/O versions satisfy the contract."""
        contracts = [
            c for c in self._contracts.values() if c.kpi_name == kpi_name
        ]
        if not contracts:
            return {"status": "no_contract", "kpi_name": kpi_name}

        contract = contracts[0]
        issues = []

        if input_version < contract.min_input_version:
            issues.append(
                f"Input version {input_version} below minimum {contract.min_input_version}"
            )
        if contract.max_input_version and input_version > contract.max_input_version:
            issues.append(
                f"Input version {input_version} above maximum {contract.max_input_version}"
            )

        input_schema = self._schemas.get(contract.input_schema_id)
        if input_schema and input_schema.stage == DeprecationStage.BLOCKED.value:
            issues.append(f"Input schema {contract.input_schema_id} is BLOCKED")

        return {
            "status": "valid" if not issues else "invalid",
            "kpi_name": kpi_name,
            "issues": issues,
            "contract": contract.to_dict(),
        }

    @property
    def migration_engine(self) -> MigrationEngine:
        return self._migration_engine

    def stats(self) -> Dict[str, Any]:
        return {
            "schemas": len(self._schemas),
            "models": len(self._by_model),
            "contracts": len(self._contracts),
            "active": sum(
                1 for s in self._schemas.values()
                if s.stage == DeprecationStage.ACTIVE.value
            ),
            "deprecated": sum(
                1 for s in self._schemas.values()
                if s.stage == DeprecationStage.DEPRECATED.value
            ),
        }
