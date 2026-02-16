"""
Benchmarking Governance — Cohort Rules, Normalization, Provenance.

Provides:
- Cohort definition rules (climate zone, store format, equipment family, runtime)
- Normalization methods (weather, occupancy, hours)
- Benchmark provenance (where distributions come from, when updated)
- Benchmark distribution management and comparability enforcement
"""

from loweconex_platform.benchmarking.benchmark_engine import (
    BenchmarkEngine,
    CohortDefinition,
    CohortRule,
    NormalizationMethod,
    BenchmarkDistribution,
    BenchmarkProvenance,
    BenchmarkComparison,
)

__all__ = [
    "BenchmarkEngine",
    "CohortDefinition",
    "CohortRule",
    "NormalizationMethod",
    "BenchmarkDistribution",
    "BenchmarkProvenance",
    "BenchmarkComparison",
]
