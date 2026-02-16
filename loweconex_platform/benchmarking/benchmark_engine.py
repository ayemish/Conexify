"""
Benchmarking Governance Engine — Cohort Rules, Normalization, Provenance.

Implements:
- Cohort definition rules (climate zone, store format, equipment model family, runtime profile)
- Normalization methods (weather degree-days, occupancy proxies, operating hours)
- Benchmark provenance (source, vintage, update cadence, methodology)
- Benchmark distribution management (percentiles, z-scores, comparability)
- Comparability enforcement (only compare within valid cohorts)

Ensures that benchmarking claims are defensible, reproducible, and auditable.
"""

from __future__ import annotations

import logging
import math
import statistics
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Cohort dimensions
# =============================================================================

class CohortDimension(str, Enum):
    """Dimensions used to define benchmark cohorts."""
    CLIMATE_ZONE = "climate_zone"
    STORE_FORMAT = "store_format"
    SQUARE_FOOTAGE_BAND = "square_footage_band"
    EQUIPMENT_MODEL_FAMILY = "equipment_model_family"
    EQUIPMENT_AGE_BAND = "equipment_age_band"
    RUNTIME_PROFILE = "runtime_profile"
    REFRIGERANT_TYPE = "refrigerant_type"
    OPERATING_HOURS_BAND = "operating_hours_band"
    REGION = "region"
    VINTAGE_YEAR = "vintage_year"


class NormalizationType(str, Enum):
    """Normalization methods for fair comparison."""
    WEATHER_CDD = "weather_cdd"         # Cooling degree days
    WEATHER_HDD = "weather_hdd"         # Heating degree days
    OCCUPANCY = "occupancy"             # Occupancy-adjusted
    OPERATING_HOURS = "operating_hours"  # Hours-normalized
    FLOOR_AREA = "floor_area"           # Per-sqft normalization
    REVENUE = "revenue"                 # Per-dollar-revenue
    REFRIGERATED_VOLUME = "refrigerated_volume"  # Per-cubic-ft
    NONE = "none"


# =============================================================================
# Cohort definition
# =============================================================================

@dataclass
class CohortRule:
    """A single rule constraining cohort membership."""
    dimension: str
    operator: str = "=="      # ==, in, range, !=
    value: Any = None         # For == and !=
    values: List[Any] = field(default_factory=list)  # For "in"
    range_min: Optional[float] = None  # For "range"
    range_max: Optional[float] = None

    def matches(self, entity_value: Any) -> bool:
        if self.operator == "==":
            return entity_value == self.value
        elif self.operator == "!=":
            return entity_value != self.value
        elif self.operator == "in":
            return entity_value in self.values
        elif self.operator == "range":
            if entity_value is None:
                return False
            return (self.range_min or float("-inf")) <= entity_value <= (self.range_max or float("inf"))
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension": self.dimension,
            "operator": self.operator,
            "value": self.value,
            "values": self.values,
            "range_min": self.range_min,
            "range_max": self.range_max,
        }


@dataclass
class CohortDefinition:
    """
    Defines a benchmark cohort — a group of comparable entities.

    All rules must be satisfied (AND logic) for cohort membership.
    """
    cohort_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    rules: List[CohortRule] = field(default_factory=list)

    # Normalization
    normalization_methods: List[str] = field(default_factory=list)

    # Minimum cohort size for valid comparison
    min_cohort_size: int = 5

    # Metadata
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_by: str = ""

    def matches(self, entity_attributes: Dict[str, Any]) -> bool:
        """Check if an entity belongs to this cohort."""
        for rule in self.rules:
            value = entity_attributes.get(rule.dimension)
            if not rule.matches(value):
                return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cohort_id": self.cohort_id,
            "name": self.name,
            "description": self.description,
            "rules": [r.to_dict() for r in self.rules],
            "normalization_methods": self.normalization_methods,
            "min_cohort_size": self.min_cohort_size,
            "created_ts": self.created_ts,
            "created_by": self.created_by,
        }


# =============================================================================
# Normalization method
# =============================================================================

@dataclass
class NormalizationMethod:
    """Describes how a metric is normalized for fair comparison."""
    method_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    normalization_type: str = NormalizationType.NONE.value
    description: str = ""

    # For degree-day normalization
    base_temperature: Optional[float] = None  # e.g., 65°F for CDD65
    temperature_unit: str = "°F"

    # For area normalization
    area_unit: str = "sqft"

    # Formula description
    formula: str = ""
    # e.g., "kWh_normalized = kWh_raw / CDD_65 * CDD_65_reference"

    def normalize(self, raw_value: float, normalizing_factor: float) -> float:
        """Apply normalization. raw_value / normalizing_factor."""
        if normalizing_factor == 0:
            return raw_value
        return raw_value / normalizing_factor

    def to_dict(self) -> Dict[str, Any]:
        return {
            "method_id": self.method_id,
            "name": self.name,
            "normalization_type": self.normalization_type,
            "description": self.description,
            "base_temperature": self.base_temperature,
            "formula": self.formula,
        }


# =============================================================================
# Benchmark distribution
# =============================================================================

@dataclass
class BenchmarkDistribution:
    """
    A benchmark distribution for a specific KPI/metric within a cohort.

    Stores percentile data for comparisons.
    """
    dist_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    cohort_id: str = ""
    kpi_name: str = ""
    metric_name: str = ""
    unit: str = ""

    # Distribution statistics
    n_samples: int = 0
    mean: float = 0.0
    median: float = 0.0
    std: float = 0.0
    min_val: float = 0.0
    max_val: float = 0.0

    # Percentiles
    p10: float = 0.0
    p25: float = 0.0
    p50: float = 0.0
    p75: float = 0.0
    p90: float = 0.0

    # Normalization applied
    normalization_method: Optional[str] = None

    # Raw values (for recomputing)
    values: List[float] = field(default_factory=list)

    def compute_from_values(self, vals: List[float]):
        """Compute distribution statistics from raw values."""
        if not vals:
            return
        self.values = sorted(vals)
        self.n_samples = len(vals)
        self.mean = statistics.mean(vals)
        self.median = statistics.median(vals)
        self.std = statistics.stdev(vals) if len(vals) > 1 else 0.0
        self.min_val = min(vals)
        self.max_val = max(vals)
        self.p10 = self._percentile(vals, 10)
        self.p25 = self._percentile(vals, 25)
        self.p50 = self._percentile(vals, 50)
        self.p75 = self._percentile(vals, 75)
        self.p90 = self._percentile(vals, 90)

    @staticmethod
    def _percentile(sorted_vals: List[float], pct: int) -> float:
        if not sorted_vals:
            return 0.0
        k = (len(sorted_vals) - 1) * pct / 100
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_vals[int(k)]
        return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)

    def z_score(self, value: float) -> float:
        """Compute z-score of a value against this distribution."""
        if self.std == 0:
            return 0.0
        return (value - self.mean) / self.std

    def percentile_rank(self, value: float) -> float:
        """Compute percentile rank of a value (0–100)."""
        if not self.values:
            return 50.0
        below = sum(1 for v in self.values if v <= value)
        return (below / len(self.values)) * 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dist_id": self.dist_id,
            "cohort_id": self.cohort_id,
            "kpi_name": self.kpi_name,
            "metric_name": self.metric_name,
            "unit": self.unit,
            "n_samples": self.n_samples,
            "mean": round(self.mean, 4),
            "median": round(self.median, 4),
            "std": round(self.std, 4),
            "min": round(self.min_val, 4),
            "max": round(self.max_val, 4),
            "p10": round(self.p10, 4),
            "p25": round(self.p25, 4),
            "p50": round(self.p50, 4),
            "p75": round(self.p75, 4),
            "p90": round(self.p90, 4),
            "normalization_method": self.normalization_method,
        }


# =============================================================================
# Benchmark provenance
# =============================================================================

@dataclass
class BenchmarkProvenance:
    """
    Tracks where benchmark data comes from and when it was updated.

    Ensures benchmarks are defensible and auditable.
    """
    provenance_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    dist_id: str = ""
    cohort_id: str = ""

    # Source
    source_type: str = ""      # internal_portfolio, industry_survey, DOE, ASHRAE, ENERGY_STAR
    source_name: str = ""
    source_url: Optional[str] = None
    source_citation: str = ""

    # Vintage
    data_vintage_start: str = ""  # ISO date
    data_vintage_end: str = ""
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    update_frequency: str = "quarterly"
    next_update_due: Optional[str] = None

    # Methodology
    methodology: str = ""
    normalization_applied: List[str] = field(default_factory=list)
    exclusion_criteria: List[str] = field(default_factory=list)
    sample_size: int = 0

    # Quality
    confidence_level: float = 0.90
    margin_of_error: Optional[float] = None

    # Approval
    approved_by: Optional[str] = None
    approved_ts: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provenance_id": self.provenance_id,
            "dist_id": self.dist_id,
            "cohort_id": self.cohort_id,
            "source_type": self.source_type,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "source_citation": self.source_citation,
            "data_vintage_start": self.data_vintage_start,
            "data_vintage_end": self.data_vintage_end,
            "last_updated": self.last_updated,
            "update_frequency": self.update_frequency,
            "next_update_due": self.next_update_due,
            "methodology": self.methodology,
            "normalization_applied": self.normalization_applied,
            "exclusion_criteria": self.exclusion_criteria,
            "sample_size": self.sample_size,
            "confidence_level": self.confidence_level,
            "margin_of_error": self.margin_of_error,
            "approved_by": self.approved_by,
            "approved_ts": self.approved_ts,
        }

    def is_stale(self) -> bool:
        """Check if benchmark data is overdue for update."""
        if not self.next_update_due:
            return False
        try:
            return datetime.utcnow() > datetime.fromisoformat(self.next_update_due)
        except ValueError:
            return False


# =============================================================================
# Benchmark comparison result
# =============================================================================

@dataclass
class BenchmarkComparison:
    """Result of comparing an entity's metric against its cohort benchmark."""
    entity_id: str = ""
    cohort_id: str = ""
    kpi_name: str = ""
    metric_name: str = ""
    entity_value: float = 0.0
    z_score: float = 0.0
    percentile_rank: float = 50.0
    cohort_mean: float = 0.0
    cohort_median: float = 0.0
    cohort_size: int = 0
    normalization_method: Optional[str] = None
    comparison_valid: bool = True
    validation_issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "cohort_id": self.cohort_id,
            "kpi_name": self.kpi_name,
            "metric_name": self.metric_name,
            "entity_value": round(self.entity_value, 4),
            "z_score": round(self.z_score, 2),
            "percentile_rank": round(self.percentile_rank, 1),
            "cohort_mean": round(self.cohort_mean, 4),
            "cohort_median": round(self.cohort_median, 4),
            "cohort_size": self.cohort_size,
            "normalization_method": self.normalization_method,
            "comparison_valid": self.comparison_valid,
            "validation_issues": self.validation_issues,
        }


# =============================================================================
# Benchmark Engine
# =============================================================================

class BenchmarkEngine:
    """
    Central engine for benchmark governance.

    Manages cohort definitions, benchmark distributions, normalization,
    provenance, and comparability enforcement.
    """

    def __init__(self):
        self._cohorts: Dict[str, CohortDefinition] = {}
        self._distributions: Dict[str, BenchmarkDistribution] = {}
        self._provenance: Dict[str, BenchmarkProvenance] = {}
        self._normalization_methods: Dict[str, NormalizationMethod] = {}

    def register_cohort(self, cohort: CohortDefinition):
        self._cohorts[cohort.cohort_id] = cohort
        logger.info(f"Registered cohort: {cohort.name}")

    def register_distribution(self, dist: BenchmarkDistribution, provenance: BenchmarkProvenance):
        self._distributions[dist.dist_id] = dist
        provenance.dist_id = dist.dist_id
        self._provenance[provenance.provenance_id] = provenance

    def register_normalization(self, method: NormalizationMethod):
        self._normalization_methods[method.method_id] = method

    def find_cohort(self, entity_attributes: Dict[str, Any]) -> Optional[CohortDefinition]:
        """Find the best matching cohort for an entity."""
        matches = [c for c in self._cohorts.values() if c.matches(entity_attributes)]
        if not matches:
            return None
        # Prefer most specific (most rules)
        return max(matches, key=lambda c: len(c.rules))

    def compare(
        self,
        entity_id: str,
        entity_value: float,
        kpi_name: str,
        metric_name: str,
        entity_attributes: Dict[str, Any],
        normalizing_factor: Optional[float] = None,
    ) -> BenchmarkComparison:
        """
        Compare an entity's metric against its cohort benchmark.

        Enforces comparability rules:
        1. Entity must belong to a defined cohort
        2. Cohort must have sufficient sample size
        3. Normalization must be applied if required
        4. Benchmark must not be stale
        """
        result = BenchmarkComparison(
            entity_id=entity_id,
            kpi_name=kpi_name,
            metric_name=metric_name,
            entity_value=entity_value,
        )

        # Find cohort
        cohort = self.find_cohort(entity_attributes)
        if not cohort:
            result.comparison_valid = False
            result.validation_issues.append("No matching cohort found")
            return result

        result.cohort_id = cohort.cohort_id

        # Find distribution
        dist = self._find_distribution(cohort.cohort_id, kpi_name, metric_name)
        if not dist:
            result.comparison_valid = False
            result.validation_issues.append("No benchmark distribution for this cohort/KPI")
            return result

        # Check cohort size
        if dist.n_samples < cohort.min_cohort_size:
            result.comparison_valid = False
            result.validation_issues.append(
                f"Cohort size {dist.n_samples} below minimum {cohort.min_cohort_size}"
            )

        # Check benchmark staleness
        prov = self._find_provenance(dist.dist_id)
        if prov and prov.is_stale():
            result.validation_issues.append("Benchmark data is stale (overdue for update)")

        # Apply normalization if required
        normalized_value = entity_value
        if cohort.normalization_methods and normalizing_factor is not None:
            method_id = cohort.normalization_methods[0]
            method = self._normalization_methods.get(method_id)
            if method:
                normalized_value = method.normalize(entity_value, normalizing_factor)
                result.normalization_method = method.name
            else:
                result.validation_issues.append(f"Normalization method '{method_id}' not found")

        # Compute comparison
        result.entity_value = normalized_value
        result.z_score = dist.z_score(normalized_value)
        result.percentile_rank = dist.percentile_rank(normalized_value)
        result.cohort_mean = dist.mean
        result.cohort_median = dist.median
        result.cohort_size = dist.n_samples

        if not result.validation_issues:
            result.comparison_valid = True

        return result

    def get_stale_benchmarks(self) -> List[BenchmarkProvenance]:
        """Get all benchmark provenance records that are overdue for update."""
        return [p for p in self._provenance.values() if p.is_stale()]

    def _find_distribution(
        self, cohort_id: str, kpi_name: str, metric_name: str
    ) -> Optional[BenchmarkDistribution]:
        for dist in self._distributions.values():
            if (dist.cohort_id == cohort_id
                    and dist.kpi_name == kpi_name
                    and dist.metric_name == metric_name):
                return dist
        return None

    def _find_provenance(self, dist_id: str) -> Optional[BenchmarkProvenance]:
        for prov in self._provenance.values():
            if prov.dist_id == dist_id:
                return prov
        return None

    def stats(self) -> Dict[str, Any]:
        return {
            "cohorts": len(self._cohorts),
            "distributions": len(self._distributions),
            "provenance_records": len(self._provenance),
            "normalization_methods": len(self._normalization_methods),
            "stale_benchmarks": len(self.get_stale_benchmarks()),
        }
