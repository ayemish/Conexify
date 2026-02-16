"""
Data Validation — checks data quality before production import.

Validates: required fields, value ranges, referential integrity,
data types, and generates a Data Quality Score.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

from loweconex_platform.digital_twins.store import TwinStore

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    """A single validation issue."""
    severity: str  # "error", "warning", "info"
    field: str
    row_index: Optional[int] = None
    message: str = ""
    value: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "field": self.field,
            "row_index": self.row_index,
            "message": self.message,
            "value": str(self.value)[:100] if self.value is not None else None,
        }


@dataclass
class ValidationResult:
    """Aggregated validation result."""
    is_valid: bool = True
    data_quality_score: float = 1.0  # 0.0 to 1.0
    total_rows: int = 0
    valid_rows: int = 0
    issues: List[ValidationIssue] = field(default_factory=list)
    field_completeness: Dict[str, float] = field(default_factory=dict)
    blocked: bool = False  # True if quality below threshold

    @property
    def quality_score(self) -> float:
        """Backward-compatible alias for data_quality_score."""
        return self.data_quality_score

    @quality_score.setter
    def quality_score(self, value: float):
        self.data_quality_score = value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "data_quality_score": round(self.data_quality_score, 3),
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "error_count": sum(1 for i in self.issues if i.severity == "error"),
            "warning_count": sum(1 for i in self.issues if i.severity == "warning"),
            "field_completeness": self.field_completeness,
            "blocked": self.blocked,
            "issues": [i.to_dict() for i in self.issues[:100]],  # Cap at 100
        }


# Standard range checks per canonical field
RANGE_CHECKS: Dict[str, Dict[str, float]] = {
    "temperature_f": {"min": -40, "max": 200},
    "temperature_c": {"min": -40, "max": 93},
    "pressure_psi": {"min": 0, "max": 1000},
    "humidity_pct": {"min": 0, "max": 100},
    "energy_kwh": {"min": 0, "max": 1_000_000},
    "power_kw": {"min": 0, "max": 10_000},
    "health_score": {"min": 0, "max": 100},
    "failure_risk": {"min": 0, "max": 1},
    "leak_rate": {"min": 0, "max": 1},
    "cost": {"min": 0, "max": 10_000_000},
    "age_years": {"min": 0, "max": 100},
    "sqft": {"min": 100, "max": 1_000_000},
}


class DataValidator:
    """
    Validates data quality before production import.
    
    Checks:
    - Required fields present
    - Value ranges (out-of-range flagged)
    - Referential integrity (asset_id, location_id exist)
    - Data type conformance
    - Duplicate detection
    - Generates Data Quality Score
    
    Blocks import if score below configurable threshold.
    """

    def __init__(
        self,
        twin_store: Optional[TwinStore] = None,
        quality_threshold: float = 0.6,
    ):
        self.twin_store = twin_store
        self.quality_threshold = quality_threshold

    def validate(
        self,
        data: List[Dict[str, Any]],
        required_fields: Optional[List[str]] = None,
        unique_fields: Optional[List[str]] = None,
        range_checks: Optional[Dict[str, Dict[str, float]]] = None,
        check_referential_integrity: bool = True,
    ) -> ValidationResult:
        """
        Run all validation checks on the data.
        
        Returns ValidationResult with quality score and issue list.
        """
        result = ValidationResult(total_rows=len(data))
        required = required_fields or []
        uniques = unique_fields or []
        ranges = range_checks or RANGE_CHECKS

        seen_values: Dict[str, Set[str]] = {f: set() for f in uniques}
        field_present_count: Dict[str, int] = {}
        all_fields: Set[str] = set()

        for i, row in enumerate(data):
            row_valid = True
            all_fields.update(row.keys())

            # Required field checks
            for req_field in required:
                value = row.get(req_field)
                if value is None or (isinstance(value, str) and not value.strip()):
                    result.issues.append(ValidationIssue(
                        severity="error",
                        field=req_field,
                        row_index=i,
                        message=f"Required field '{req_field}' missing or empty",
                    ))
                    row_valid = False

            # Field completeness tracking
            for fld in row:
                val = row[fld]
                if val is not None and (not isinstance(val, str) or val.strip()):
                    field_present_count[fld] = field_present_count.get(fld, 0) + 1

            # Range checks
            for field_name, bounds in ranges.items():
                if field_name in row and row[field_name] is not None:
                    try:
                        val = float(row[field_name])
                        if val < bounds.get("min", float("-inf")):
                            result.issues.append(ValidationIssue(
                                severity="warning",
                                field=field_name,
                                row_index=i,
                                message=f"Value {val} below minimum {bounds['min']}",
                                value=val,
                            ))
                        if val > bounds.get("max", float("inf")):
                            result.issues.append(ValidationIssue(
                                severity="warning",
                                field=field_name,
                                row_index=i,
                                message=f"Value {val} above maximum {bounds['max']}",
                                value=val,
                            ))
                    except (ValueError, TypeError):
                        result.issues.append(ValidationIssue(
                            severity="warning",
                            field=field_name,
                            row_index=i,
                            message=f"Non-numeric value for range-checked field",
                            value=row[field_name],
                        ))

            # Uniqueness checks
            for uniq_field in uniques:
                val = str(row.get(uniq_field, ""))
                if val and val in seen_values[uniq_field]:
                    result.issues.append(ValidationIssue(
                        severity="warning",
                        field=uniq_field,
                        row_index=i,
                        message=f"Duplicate value '{val}' for unique field '{uniq_field}'",
                        value=val,
                    ))
                seen_values[uniq_field].add(val)

            # Referential integrity
            if check_referential_integrity and self.twin_store:
                asset_id = row.get("asset_id")
                if asset_id and not self.twin_store.get_asset(str(asset_id)):
                    result.issues.append(ValidationIssue(
                        severity="info",
                        field="asset_id",
                        row_index=i,
                        message=f"Asset '{asset_id}' not found in twin store (will be created)",
                        value=asset_id,
                    ))

                location_id = row.get("location_id")
                if location_id and not self.twin_store.get_location(str(location_id)):
                    result.issues.append(ValidationIssue(
                        severity="info",
                        field="location_id",
                        row_index=i,
                        message=f"Location '{location_id}' not found (will be created)",
                        value=location_id,
                    ))

            if row_valid:
                result.valid_rows += 1

        # Compute field completeness
        for fld in all_fields:
            count = field_present_count.get(fld, 0)
            result.field_completeness[fld] = count / max(len(data), 1)

        # Compute data quality score
        error_count = sum(1 for i in result.issues if i.severity == "error")
        warning_count = sum(1 for i in result.issues if i.severity == "warning")

        if len(data) > 0:
            error_rate = error_count / len(data)
            warning_rate = warning_count / len(data)
            result.data_quality_score = max(0.0, 1.0 - error_rate - warning_rate * 0.3)
        else:
            result.data_quality_score = 0.0

        result.is_valid = result.data_quality_score >= self.quality_threshold
        result.blocked = not result.is_valid

        if result.blocked:
            logger.warning(
                f"Data validation BLOCKED: score {result.data_quality_score:.2f} "
                f"< threshold {self.quality_threshold}"
            )
        else:
            logger.info(
                f"Data validation passed: score {result.data_quality_score:.2f}, "
                f"{result.valid_rows}/{result.total_rows} valid rows"
            )

        return result
