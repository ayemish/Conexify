"""
Digital Twin Model Versioning, Migration & Compatibility.

Ensures twin schema evolves without breaking analytics:
- Twin model version registry (DTDL-inspired)
- Schema contracts per KPI input/output
- Backward compatibility checks
- Migration engine with up/down transforms
- Deprecation policy enforcement
"""

from loweconex_platform.twin_versioning.schema_registry import (
    SchemaRegistry,
    SchemaVersion,
    SchemaContract,
    MigrationStep,
    MigrationEngine,
    CompatibilityChecker,
)

__all__ = [
    "SchemaRegistry",
    "SchemaVersion",
    "SchemaContract",
    "MigrationStep",
    "MigrationEngine",
    "CompatibilityChecker",
]
