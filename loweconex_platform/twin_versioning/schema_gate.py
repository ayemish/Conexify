"""
Schema Registry Enforcement Gate — validates twin model changes.

Gates digital_twins/ model changes through SchemaRegistry.check_compatibility()
before applying. Can be wired as a pre-write hook on TwinStore.

Phase 3.2 integration.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from loweconex_platform.twin_versioning.schema_registry import (
        SchemaRegistry, CompatibilityChecker, CompatibilityMode, SchemaVersion,
    )
    SCHEMA_REGISTRY_AVAILABLE = True
except ImportError:
    SCHEMA_REGISTRY_AVAILABLE = False


class SchemaEnforcementGate:
    """
    Pre-write validation hook for TwinStore.

    Before a twin write (asset, location, or KPI patch), the gate checks:
    1. Is there a registered schema for this model type?
    2. Does the proposed data conform to the latest schema?
    3. If the schema has changed, is it backward-compatible?

    Usage:
        gate = SchemaEnforcementGate(registry)
        result = gate.validate_write("AssetTwin", data_dict)
        if not result["allowed"]:
            raise ValueError(result["reason"])
    """

    def __init__(self, registry: Optional[Any] = None):
        if registry is not None:
            self._registry = registry
        elif SCHEMA_REGISTRY_AVAILABLE:
            self._registry = SchemaRegistry()
        else:
            self._registry = None

    def validate_write(
        self,
        model_name: str,
        data: Dict[str, Any],
        declared_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Validate a proposed twin write against the schema registry.

        Returns:
            {"allowed": bool, "reason": str, "warnings": [...]}
        """
        if not self._registry:
            return {"allowed": True, "reason": "No schema registry configured", "warnings": []}

        latest = self._registry.get_latest(model_name)
        if not latest:
            return {"allowed": True, "reason": f"No schema registered for '{model_name}'", "warnings": []}

        # Check deprecation
        if hasattr(latest, 'deprecation_stage'):
            if latest.deprecation_stage == "blocked":
                return {
                    "allowed": False,
                    "reason": f"Schema '{model_name}' v{latest.version} is BLOCKED (retired)",
                    "warnings": [],
                }
            elif latest.deprecation_stage == "deprecated":
                logger.warning(f"Schema '{model_name}' v{latest.version} is DEPRECATED")

        # Validate required fields
        warnings = []
        missing_required = []
        for field_def in latest.fields:
            if field_def.required and field_def.name not in data:
                if field_def.default is not None:
                    warnings.append(f"Missing field '{field_def.name}' will use default: {field_def.default}")
                else:
                    missing_required.append(field_def.name)

        if missing_required:
            return {
                "allowed": False,
                "reason": f"Missing required fields: {', '.join(missing_required)}",
                "warnings": warnings,
            }

        # Type checking
        type_map = {"string": str, "float": (int, float), "int": int, "bool": bool}
        for field_def in latest.fields:
            if field_def.name in data and data[field_def.name] is not None:
                expected = type_map.get(field_def.field_type)
                if expected and not isinstance(data[field_def.name], expected):
                    warnings.append(
                        f"Field '{field_def.name}': expected {field_def.field_type}, "
                        f"got {type(data[field_def.name]).__name__}"
                    )

        # If caller declared a version, check compatibility with latest
        if declared_version and declared_version != latest.version:
            old_schema = self._registry.get_version(model_name, declared_version)
            if old_schema and SCHEMA_REGISTRY_AVAILABLE:
                compat = CompatibilityChecker.check(
                    old_schema, latest, CompatibilityMode.BACKWARD
                )
                if not compat["compatible"]:
                    return {
                        "allowed": False,
                        "reason": (
                            f"Schema version {declared_version} → {latest.version} "
                            f"has breaking changes: "
                            + "; ".join(c["message"] for c in compat["breaking_changes"][:3])
                        ),
                        "warnings": warnings,
                    }

        return {"allowed": True, "reason": "Schema validation passed", "warnings": warnings}

    def validate_patch(
        self,
        model_name: str,
        patch: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Lighter validation for twin patches (partial updates).
        Only checks that patched fields match expected types.
        """
        if not self._registry:
            return {"allowed": True, "reason": "No registry", "warnings": []}

        latest = self._registry.get_latest(model_name)
        if not latest:
            return {"allowed": True, "reason": "No schema", "warnings": []}

        warnings = []
        type_map = {"string": str, "float": (int, float), "int": int, "bool": bool}
        known_fields = {f.name for f in latest.fields}

        for key, value in patch.items():
            if key not in known_fields:
                warnings.append(f"Field '{key}' not in schema (may be extension)")
                continue
            field_def = next(f for f in latest.fields if f.name == key)
            expected = type_map.get(field_def.field_type)
            if expected and value is not None and not isinstance(value, expected):
                warnings.append(
                    f"Patch field '{key}': expected {field_def.field_type}, "
                    f"got {type(value).__name__}"
                )

        return {"allowed": True, "reason": "Patch validation passed", "warnings": warnings}
