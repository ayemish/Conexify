"""
Data Quality SLAs — ISO/IEC 25012 dimensions, expectation suites, hard gates.

Provides:
- Quality dimensions (completeness, accuracy, consistency, timeliness, etc.)
- Per-dataset expectation suites (Great Expectations-style)
- Acceptance thresholds and automated validation gates
- KPI publication blocking when gates fail
"""

from loweconex_platform.data_quality.quality_engine import (
    DataQualityEngine,
    QualityDimension,
    Expectation,
    ExpectationSuite,
    QualityReport,
    QualityGate,
)

__all__ = [
    "DataQualityEngine",
    "QualityDimension",
    "Expectation",
    "ExpectationSuite",
    "QualityReport",
    "QualityGate",
]
