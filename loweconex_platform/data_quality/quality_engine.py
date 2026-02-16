"""
Data Quality Engine — ISO/IEC 25012 dimensions + expectation suites.

Implements:
- 15 ISO/IEC 25012 data quality dimensions with scoring
- Great Expectations-style expectation suites per dataset
- Automated validation gates that block KPI publication on failure
- Quality SLA definitions with threshold enforcement

References:
- ISO/IEC 25012:2008 Data Quality Model
- Great Expectations (greatexpectations.io) validation patterns
- DAMA DMBOK data quality management
"""

from __future__ import annotations

import logging
import statistics
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# =============================================================================
# ISO/IEC 25012 quality dimensions
# =============================================================================

class QualityDimension(str, Enum):
    """ISO/IEC 25012 data quality characteristics."""
    # Inherent
    ACCURACY = "accuracy"
    COMPLETENESS = "completeness"
    CONSISTENCY = "consistency"
    CREDIBILITY = "credibility"
    CURRENTNESS = "currentness"
    # System-dependent
    ACCESSIBILITY = "accessibility"
    COMPLIANCE = "compliance"
    CONFIDENTIALITY = "confidentiality"
    EFFICIENCY = "efficiency"
    PRECISION = "precision"
    TRACEABILITY = "traceability"
    UNDERSTANDABILITY = "understandability"
    AVAILABILITY = "availability"
    PORTABILITY = "portability"
    RECOVERABILITY = "recoverability"
    # Additional common dimensions
    TIMELINESS = "timeliness"
    UNIQUENESS = "uniqueness"
    VALIDITY = "validity"


class ExpectationType(str, Enum):
    """Types of data expectations (Great Expectations-inspired)."""
    NOT_NULL = "not_null"
    UNIQUE = "unique"
    IN_SET = "in_set"
    IN_RANGE = "in_range"
    REGEX_MATCH = "regex_match"
    TYPE_CHECK = "type_check"
    ROW_COUNT_RANGE = "row_count_range"
    COLUMN_EXISTS = "column_exists"
    MEAN_IN_RANGE = "mean_in_range"
    STD_IN_RANGE = "std_in_range"
    MAX_NULL_FRACTION = "max_null_fraction"
    FRESHNESS = "freshness"
    REFERENTIAL_INTEGRITY = "referential_integrity"
    CUSTOM = "custom"


class GateDecision(str, Enum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


# =============================================================================
# Expectation model
# =============================================================================

@dataclass
class Expectation:
    """
    A single data quality expectation (Great Expectations-style).

    Defines a testable assertion about a dataset or column.
    """
    expectation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    expectation_type: str = ExpectationType.NOT_NULL.value
    dimension: str = QualityDimension.COMPLETENESS.value

    # Target
    column: Optional[str] = None  # None = table-level expectation
    dataset: str = ""

    # Parameters (depend on expectation_type)
    params: Dict[str, Any] = field(default_factory=dict)
    # e.g., {"min": 0, "max": 100} for IN_RANGE
    # e.g., {"values": ["A", "B", "C"]} for IN_SET
    # e.g., {"pattern": r"^\d{5}$"} for REGEX_MATCH
    # e.g., {"max_fraction": 0.05} for MAX_NULL_FRACTION
    # e.g., {"max_age_hours": 24} for FRESHNESS

    # Severity
    severity: str = "error"  # error (blocks), warning (logs)
    description: str = ""

    # Custom validation function
    custom_fn: Optional[Callable[[Any], bool]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "expectation_id": self.expectation_id,
            "name": self.name,
            "expectation_type": self.expectation_type,
            "dimension": self.dimension,
            "column": self.column,
            "dataset": self.dataset,
            "params": self.params,
            "severity": self.severity,
            "description": self.description,
        }


@dataclass
class ExpectationResult:
    """Result of evaluating a single expectation."""
    expectation_id: str
    passed: bool
    severity: str = "error"
    observed_value: Any = None
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "expectation_id": self.expectation_id,
            "passed": self.passed,
            "severity": self.severity,
            "observed_value": self.observed_value,
            "details": self.details,
        }


# =============================================================================
# Expectation suite
# =============================================================================

@dataclass
class ExpectationSuite:
    """
    A collection of expectations for a specific dataset.

    Each dataset has exactly one suite. Suites are versioned.
    """
    suite_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    dataset_name: str = ""
    version: str = "1.0.0"
    description: str = ""
    expectations: List[Expectation] = field(default_factory=list)

    # Gate configuration
    block_on_error: bool = True
    min_pass_rate: float = 1.0  # 1.0 = all must pass to proceed

    # Metadata
    owner: str = ""
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_run_ts: Optional[str] = None

    def add_expectation(self, exp: Expectation):
        exp.dataset = self.dataset_name
        self.expectations.append(exp)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suite_id": self.suite_id,
            "dataset_name": self.dataset_name,
            "version": self.version,
            "description": self.description,
            "expectations": [e.to_dict() for e in self.expectations],
            "block_on_error": self.block_on_error,
            "min_pass_rate": self.min_pass_rate,
            "owner": self.owner,
            "created_ts": self.created_ts,
            "last_run_ts": self.last_run_ts,
            "expectation_count": len(self.expectations),
        }


# =============================================================================
# Quality report
# =============================================================================

@dataclass
class QualityReport:
    """Full quality report from running a suite against data."""
    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    suite_id: str = ""
    dataset_name: str = ""

    # Results
    results: List[ExpectationResult] = field(default_factory=list)
    total: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    pass_rate: float = 0.0

    # Dimension scores (0–1 per ISO 25012 dimension)
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    overall_score: float = 0.0

    # Gate decision
    gate_decision: str = GateDecision.PASS.value
    gate_reason: str = ""

    # Metadata
    generated_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    duration_ms: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "suite_id": self.suite_id,
            "dataset_name": self.dataset_name,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "warnings": self.warnings,
            "pass_rate": self.pass_rate,
            "dimension_scores": self.dimension_scores,
            "overall_score": self.overall_score,
            "gate_decision": self.gate_decision,
            "gate_reason": self.gate_reason,
            "generated_ts": self.generated_ts,
            "duration_ms": self.duration_ms,
            "results": [r.to_dict() for r in self.results],
        }


# =============================================================================
# Quality gate
# =============================================================================

@dataclass
class QualityGate:
    """
    A gate controlling whether data proceeds to the next pipeline stage.

    Gates are tied to expectation suites and enforce hard-stop behavior.
    """
    gate_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    suite_id: str = ""
    pipeline_stage: str = ""  # e.g., "kpi_extraction", "kpi_publication"

    # Thresholds
    min_overall_score: float = 0.8
    required_dimensions: Dict[str, float] = field(default_factory=dict)
    # e.g., {"completeness": 0.95, "accuracy": 0.90}

    # Behavior
    block_on_fail: bool = True
    notify_on_warn: bool = True

    def evaluate(self, report: QualityReport) -> Dict[str, Any]:
        """Evaluate whether a quality report passes this gate."""
        issues = []

        if report.overall_score < self.min_overall_score:
            issues.append(
                f"Overall score {report.overall_score:.2f} below "
                f"minimum {self.min_overall_score:.2f}"
            )

        for dim, threshold in self.required_dimensions.items():
            score = report.dimension_scores.get(dim, 0.0)
            if score < threshold:
                issues.append(
                    f"Dimension '{dim}' score {score:.2f} below "
                    f"threshold {threshold:.2f}"
                )

        if issues and self.block_on_fail:
            decision = GateDecision.BLOCK.value
        elif issues:
            decision = GateDecision.WARN.value
        else:
            decision = GateDecision.PASS.value

        return {
            "gate_id": self.gate_id,
            "decision": decision,
            "issues": issues,
            "report_id": report.report_id,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "name": self.name,
            "suite_id": self.suite_id,
            "pipeline_stage": self.pipeline_stage,
            "min_overall_score": self.min_overall_score,
            "required_dimensions": self.required_dimensions,
            "block_on_fail": self.block_on_fail,
        }


# =============================================================================
# Data Quality Engine
# =============================================================================

class DataQualityEngine:
    """
    Central engine for data quality management.

    Manages expectation suites, runs validations against data,
    computes ISO 25012 dimension scores, and enforces quality gates.
    """

    def __init__(self):
        self._suites: Dict[str, ExpectationSuite] = {}
        self._gates: Dict[str, QualityGate] = {}
        self._reports: List[QualityReport] = []

    def register_suite(self, suite: ExpectationSuite):
        self._suites[suite.suite_id] = suite
        logger.info(f"Registered quality suite: {suite.dataset_name} ({len(suite.expectations)} expectations)")

    def register_gate(self, gate: QualityGate):
        self._gates[gate.gate_id] = gate

    def get_suite(self, suite_id: str) -> Optional[ExpectationSuite]:
        return self._suites.get(suite_id)

    def get_suite_for_dataset(self, dataset_name: str) -> Optional[ExpectationSuite]:
        for suite in self._suites.values():
            if suite.dataset_name == dataset_name:
                return suite
        return None

    def validate(
        self,
        suite_id: str,
        data: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> QualityReport:
        """
        Run an expectation suite against a dataset.

        Args:
            suite_id: The expectation suite to run
            data: List of records (dicts) to validate
            metadata: Optional metadata (e.g., last_updated timestamp)

        Returns:
            QualityReport with per-expectation results and dimension scores
        """
        suite = self._suites.get(suite_id)
        if not suite:
            raise ValueError(f"Suite {suite_id} not found")

        start = datetime.utcnow()
        results = []

        for exp in suite.expectations:
            result = self._evaluate_expectation(exp, data, metadata or {})
            results.append(result)

        end = datetime.utcnow()
        duration_ms = int((end - start).total_seconds() * 1000)

        # Compute dimension scores
        dimension_results: Dict[str, List[bool]] = defaultdict(list)
        for exp, result in zip(suite.expectations, results):
            dimension_results[exp.dimension].append(result.passed)

        dimension_scores = {}
        for dim, outcomes in dimension_results.items():
            dimension_scores[dim] = sum(outcomes) / len(outcomes) if outcomes else 1.0

        overall = sum(dimension_scores.values()) / len(dimension_scores) if dimension_scores else 0.0

        passed_count = sum(1 for r in results if r.passed)
        error_failures = sum(1 for r in results if not r.passed and r.severity == "error")
        warning_count = sum(1 for r in results if not r.passed and r.severity == "warning")
        pass_rate = passed_count / len(results) if results else 1.0

        # Gate decision
        if error_failures > 0 and suite.block_on_error:
            gate_decision = GateDecision.BLOCK.value
            gate_reason = f"{error_failures} error-severity expectations failed"
        elif pass_rate < suite.min_pass_rate:
            gate_decision = GateDecision.BLOCK.value
            gate_reason = f"Pass rate {pass_rate:.1%} below minimum {suite.min_pass_rate:.0%}"
        elif warning_count > 0:
            gate_decision = GateDecision.WARN.value
            gate_reason = f"{warning_count} warning-severity expectations failed"
        else:
            gate_decision = GateDecision.PASS.value
            gate_reason = "All expectations passed"

        report = QualityReport(
            suite_id=suite_id,
            dataset_name=suite.dataset_name,
            results=results,
            total=len(results),
            passed=passed_count,
            failed=len(results) - passed_count,
            warnings=warning_count,
            pass_rate=pass_rate,
            dimension_scores=dimension_scores,
            overall_score=round(overall, 4),
            gate_decision=gate_decision,
            gate_reason=gate_reason,
            duration_ms=duration_ms,
        )

        suite.last_run_ts = datetime.utcnow().isoformat()
        self._reports.append(report)

        logger.info(
            f"Quality validation for {suite.dataset_name}: "
            f"{passed_count}/{len(results)} passed, "
            f"score={overall:.2f}, gate={gate_decision}"
        )
        return report

    def check_gate(self, gate_id: str, report: QualityReport) -> Dict[str, Any]:
        """Evaluate a quality gate against a report."""
        gate = self._gates.get(gate_id)
        if not gate:
            return {"error": f"Gate {gate_id} not found"}
        return gate.evaluate(report)

    def _evaluate_expectation(
        self,
        exp: Expectation,
        data: List[Dict[str, Any]],
        metadata: Dict[str, Any],
    ) -> ExpectationResult:
        """Evaluate a single expectation against data."""
        try:
            if exp.expectation_type == ExpectationType.NOT_NULL.value:
                return self._check_not_null(exp, data)
            elif exp.expectation_type == ExpectationType.UNIQUE.value:
                return self._check_unique(exp, data)
            elif exp.expectation_type == ExpectationType.IN_SET.value:
                return self._check_in_set(exp, data)
            elif exp.expectation_type == ExpectationType.IN_RANGE.value:
                return self._check_in_range(exp, data)
            elif exp.expectation_type == ExpectationType.TYPE_CHECK.value:
                return self._check_type(exp, data)
            elif exp.expectation_type == ExpectationType.ROW_COUNT_RANGE.value:
                return self._check_row_count(exp, data)
            elif exp.expectation_type == ExpectationType.COLUMN_EXISTS.value:
                return self._check_column_exists(exp, data)
            elif exp.expectation_type == ExpectationType.MAX_NULL_FRACTION.value:
                return self._check_null_fraction(exp, data)
            elif exp.expectation_type == ExpectationType.MEAN_IN_RANGE.value:
                return self._check_mean_range(exp, data)
            elif exp.expectation_type == ExpectationType.FRESHNESS.value:
                return self._check_freshness(exp, metadata)
            elif exp.expectation_type == ExpectationType.CUSTOM.value:
                return self._check_custom(exp, data)
            else:
                return ExpectationResult(
                    expectation_id=exp.expectation_id, passed=True,
                    details=f"Unknown expectation type: {exp.expectation_type}"
                )
        except Exception as e:
            return ExpectationResult(
                expectation_id=exp.expectation_id, passed=False,
                severity=exp.severity, details=f"Evaluation error: {e}"
            )

    def _check_not_null(self, exp: Expectation, data: List[Dict]) -> ExpectationResult:
        col = exp.column
        nulls = sum(1 for row in data if row.get(col) is None)
        passed = nulls == 0
        return ExpectationResult(
            expectation_id=exp.expectation_id, passed=passed,
            severity=exp.severity, observed_value=nulls,
            details=f"{nulls}/{len(data)} null values in '{col}'"
        )

    def _check_unique(self, exp: Expectation, data: List[Dict]) -> ExpectationResult:
        col = exp.column
        values = [row.get(col) for row in data if row.get(col) is not None]
        dupes = len(values) - len(set(values))
        passed = dupes == 0
        return ExpectationResult(
            expectation_id=exp.expectation_id, passed=passed,
            severity=exp.severity, observed_value=dupes,
            details=f"{dupes} duplicate values in '{col}'"
        )

    def _check_in_set(self, exp: Expectation, data: List[Dict]) -> ExpectationResult:
        col = exp.column
        allowed = set(exp.params.get("values", []))
        violations = [row.get(col) for row in data if row.get(col) not in allowed]
        passed = len(violations) == 0
        return ExpectationResult(
            expectation_id=exp.expectation_id, passed=passed,
            severity=exp.severity, observed_value=len(violations),
            details=f"{len(violations)} values not in allowed set for '{col}'"
        )

    def _check_in_range(self, exp: Expectation, data: List[Dict]) -> ExpectationResult:
        col = exp.column
        min_val = exp.params.get("min", float("-inf"))
        max_val = exp.params.get("max", float("inf"))
        violations = 0
        for row in data:
            val = row.get(col)
            if val is not None and (val < min_val or val > max_val):
                violations += 1
        passed = violations == 0
        return ExpectationResult(
            expectation_id=exp.expectation_id, passed=passed,
            severity=exp.severity, observed_value=violations,
            details=f"{violations} values outside [{min_val}, {max_val}] in '{col}'"
        )

    def _check_type(self, exp: Expectation, data: List[Dict]) -> ExpectationResult:
        col = exp.column
        expected_type = exp.params.get("type", "str")
        type_map = {"str": str, "int": int, "float": (int, float), "bool": bool}
        target = type_map.get(expected_type, str)
        violations = sum(1 for row in data if row.get(col) is not None and not isinstance(row[col], target))
        passed = violations == 0
        return ExpectationResult(
            expectation_id=exp.expectation_id, passed=passed,
            severity=exp.severity, observed_value=violations,
            details=f"{violations} type mismatches in '{col}' (expected {expected_type})"
        )

    def _check_row_count(self, exp: Expectation, data: List[Dict]) -> ExpectationResult:
        min_rows = exp.params.get("min", 0)
        max_rows = exp.params.get("max", float("inf"))
        count = len(data)
        passed = min_rows <= count <= max_rows
        return ExpectationResult(
            expectation_id=exp.expectation_id, passed=passed,
            severity=exp.severity, observed_value=count,
            details=f"Row count {count} (expected [{min_rows}, {max_rows}])"
        )

    def _check_column_exists(self, exp: Expectation, data: List[Dict]) -> ExpectationResult:
        col = exp.column
        if not data:
            return ExpectationResult(
                expectation_id=exp.expectation_id, passed=False,
                severity=exp.severity, details="No data to check"
            )
        exists = col in data[0]
        return ExpectationResult(
            expectation_id=exp.expectation_id, passed=exists,
            severity=exp.severity,
            details=f"Column '{col}' {'exists' if exists else 'missing'}"
        )

    def _check_null_fraction(self, exp: Expectation, data: List[Dict]) -> ExpectationResult:
        col = exp.column
        max_frac = exp.params.get("max_fraction", 0.05)
        nulls = sum(1 for row in data if row.get(col) is None)
        frac = nulls / len(data) if data else 0
        passed = frac <= max_frac
        return ExpectationResult(
            expectation_id=exp.expectation_id, passed=passed,
            severity=exp.severity, observed_value=round(frac, 4),
            details=f"Null fraction {frac:.1%} in '{col}' (max {max_frac:.0%})"
        )

    def _check_mean_range(self, exp: Expectation, data: List[Dict]) -> ExpectationResult:
        col = exp.column
        min_val = exp.params.get("min", float("-inf"))
        max_val = exp.params.get("max", float("inf"))
        values = [row[col] for row in data if row.get(col) is not None and isinstance(row[col], (int, float))]
        if not values:
            return ExpectationResult(
                expectation_id=exp.expectation_id, passed=False,
                severity=exp.severity, details=f"No numeric values in '{col}'"
            )
        mean = statistics.mean(values)
        passed = min_val <= mean <= max_val
        return ExpectationResult(
            expectation_id=exp.expectation_id, passed=passed,
            severity=exp.severity, observed_value=round(mean, 4),
            details=f"Mean of '{col}' is {mean:.2f} (expected [{min_val}, {max_val}])"
        )

    def _check_freshness(self, exp: Expectation, metadata: Dict[str, Any]) -> ExpectationResult:
        max_age_hours = exp.params.get("max_age_hours", 24)
        last_updated = metadata.get("last_updated")
        if not last_updated:
            return ExpectationResult(
                expectation_id=exp.expectation_id, passed=False,
                severity=exp.severity, details="No last_updated timestamp in metadata"
            )
        try:
            last = datetime.fromisoformat(last_updated)
            age_hours = (datetime.utcnow() - last).total_seconds() / 3600
            passed = age_hours <= max_age_hours
            return ExpectationResult(
                expectation_id=exp.expectation_id, passed=passed,
                severity=exp.severity, observed_value=round(age_hours, 1),
                details=f"Data age {age_hours:.1f}h (max {max_age_hours}h)"
            )
        except Exception as e:
            return ExpectationResult(
                expectation_id=exp.expectation_id, passed=False,
                severity=exp.severity, details=f"Freshness check error: {e}"
            )

    def _check_custom(self, exp: Expectation, data: List[Dict]) -> ExpectationResult:
        if not exp.custom_fn:
            return ExpectationResult(
                expectation_id=exp.expectation_id, passed=True,
                details="No custom function provided"
            )
        try:
            passed = exp.custom_fn(data)
            return ExpectationResult(
                expectation_id=exp.expectation_id, passed=passed,
                severity=exp.severity, details="Custom validation"
            )
        except Exception as e:
            return ExpectationResult(
                expectation_id=exp.expectation_id, passed=False,
                severity=exp.severity, details=f"Custom validation error: {e}"
            )

    def get_reports(self, dataset_name: Optional[str] = None, limit: int = 50) -> List[QualityReport]:
        reports = self._reports
        if dataset_name:
            reports = [r for r in reports if r.dataset_name == dataset_name]
        return reports[-limit:]

    def quality_trend(self, dataset_name: str) -> List[Dict[str, Any]]:
        """Get quality score trend over time for a dataset."""
        reports = [r for r in self._reports if r.dataset_name == dataset_name]
        return [
            {
                "ts": r.generated_ts,
                "overall_score": r.overall_score,
                "pass_rate": r.pass_rate,
                "gate_decision": r.gate_decision,
            }
            for r in reports
        ]

    def stats(self) -> Dict[str, Any]:
        return {
            "suites": len(self._suites),
            "gates": len(self._gates),
            "total_reports": len(self._reports),
            "blocked_count": sum(
                1 for r in self._reports if r.gate_decision == GateDecision.BLOCK.value
            ),
        }
