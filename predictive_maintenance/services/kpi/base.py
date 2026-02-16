"""
Base KPI Service Framework

Provides the abstract base class and shared data structures for all
14 KPI computation services. Each concrete KPI service computes savings
estimates from real telemetry, alert, and asset data.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class KPIConfig:
    """Site-level configuration for KPI calculations.

    These parameters are loaded from the database or environment and
    represent real operational baselines for a specific site/customer.
    """

    site_id: str = "default"
    customer_name: str = "Customer"

    # Fleet parameters
    total_assets: int = 50
    total_locations: int = 3

    # Energy baseline
    baseline_annual_kwh: float = 7_087_500.0
    energy_cost_per_kwh: float = 0.12

    # Refrigerant baseline
    baseline_leak_rate_pct: float = 25.0  # % of charge lost per year
    refrigerant_cost_per_lb: float = 15.0
    avg_charge_lbs: float = 12.0

    # Work order baseline
    baseline_reactive_wo_per_month: int = 40
    avg_wo_cost: float = 350.0

    # Food safety
    avg_temp_excursion_events_per_month: int = 12
    food_waste_cost_per_event: float = 800.0
    food_safety_violation_cost: float = 5_250.0
    baseline_violations_per_year: int = 18

    # Maintenance
    avg_dispatch_cost: float = 450.0
    baseline_dispatches_per_month: int = 22
    baseline_pm_cost_annual: float = 180_000.0

    # Uptime
    baseline_uptime_pct: float = 90.0
    hourly_downtime_cost: float = 150.0
    operating_hours_per_year: float = 8_760.0

    # Call center — ICMI 2022: $8-15 for HVAC/R facility-specific calls
    baseline_calls_per_month: int = 80
    cost_per_call: float = 12.0

    # CapEx
    avg_asset_replacement_cost: float = 18_000.0
    discount_rate: float = 0.08

    # ESG — EPA eGRID2022 US national avg; R-404A default for commercial refrigeration
    grid_emission_factor_tco2_per_kwh: float = 0.000386  # EPA eGRID2022 US avg
    refrigerant_gwp: float = 3_922.0  # R-404A GWP (dominant in commercial refrigeration)
    carbon_price_per_tco2: float = 51.0  # EPA IWG 2024 social cost of carbon

    # Demand charges (Gap 7: separate kW from kWh savings)
    demand_charge_per_kw_month: float = 12.0  # typical commercial demand charge
    baseline_peak_demand_kw: float = 200.0  # baseline peak demand

    # Configurable reduction targets (previously hardcoded in KPI services)
    energy_penalty_pct_degraded: float = 0.15  # avg energy penalty per degraded unit
    energy_penalty_pct_normal: float = 0.10    # baseline energy penalty
    food_waste_reduction_pct: float = 0.30     # baseline excursion reduction
    wo_reduction_pct: float = 0.25             # reactive WO reduction target
    refrigerant_reduction_factor: float = 0.50 # leak rate reduction via PdM
    food_safety_reduction_pct: float = 0.55    # violation reduction
    call_center_deflection_pct: float = 0.30   # call deflection rate
    service_bureau_avoidance_pct: float = 0.35 # dispatch avoidance rate
    pm_skip_pct_factor: float = 0.30           # PM deferral rate for healthy assets
    ppm_shift_pct: float = 0.30               # reactive-to-planned shift target
    uptime_target_pct: float = 99.0            # target uptime percentage
    mttr_reduction_hours: float = 2.0          # hours saved per food temp incident

    def validate(self) -> List[str]:
        """Validate baselines and return a list of error messages.

        Rejects nonsensical values that would produce meaningless KPI outputs.
        Returns an empty list when all baselines are valid.
        """
        errors: List[str] = []

        # Fleet
        if self.total_assets <= 0:
            errors.append("total_assets must be > 0")
        if self.total_locations <= 0:
            errors.append("total_locations must be > 0")

        # Energy
        if self.baseline_annual_kwh < 0:
            errors.append("baseline_annual_kwh cannot be negative")
        if self.energy_cost_per_kwh <= 0:
            errors.append("energy_cost_per_kwh must be > 0")

        # Refrigerant
        if not (0 <= self.baseline_leak_rate_pct <= 100):
            errors.append("baseline_leak_rate_pct must be 0–100")
        if self.refrigerant_cost_per_lb < 0:
            errors.append("refrigerant_cost_per_lb cannot be negative")
        if self.avg_charge_lbs < 0:
            errors.append("avg_charge_lbs cannot be negative")

        # Work orders
        if self.baseline_reactive_wo_per_month < 0:
            errors.append("baseline_reactive_wo_per_month cannot be negative")
        if self.avg_wo_cost < 0:
            errors.append("avg_wo_cost cannot be negative")

        # Food safety
        if self.food_waste_cost_per_event < 0:
            errors.append("food_waste_cost_per_event cannot be negative")
        if self.food_safety_violation_cost < 0:
            errors.append("food_safety_violation_cost cannot be negative")

        # Uptime
        if not (0 <= self.baseline_uptime_pct <= 100):
            errors.append("baseline_uptime_pct must be 0–100")
        if self.hourly_downtime_cost < 0:
            errors.append("hourly_downtime_cost cannot be negative")
        if self.operating_hours_per_year <= 0 or self.operating_hours_per_year > 8_784:
            errors.append("operating_hours_per_year must be 1–8784")

        # CapEx
        if self.avg_asset_replacement_cost < 0:
            errors.append("avg_asset_replacement_cost cannot be negative")
        if not (0 < self.discount_rate < 1):
            errors.append("discount_rate must be between 0 and 1 (e.g. 0.08)")

        # ESG
        if self.grid_emission_factor_tco2_per_kwh < 0:
            errors.append("grid_emission_factor_tco2_per_kwh cannot be negative")
        if self.refrigerant_gwp < 0:
            errors.append("refrigerant_gwp cannot be negative")

        # Demand charges
        if self.demand_charge_per_kw_month < 0:
            errors.append("demand_charge_per_kw_month cannot be negative")

        return errors

    @classmethod
    def load_from_db(cls, site_id: str) -> "KPIConfig":
        """Load site-specific KPI baselines from the database.

        Falls back to dataclass defaults when no row exists or the DB
        is unreachable, so callers never need to handle errors.
        """
        try:
            from predictive_maintenance.persistence.database import get_session
            from predictive_maintenance.persistence.models import SiteConfigModel

            with get_session() as session:
                row = session.query(SiteConfigModel).filter(
                    SiteConfigModel.site_id == site_id
                ).first()
                if row is None:
                    logger.info("No SiteConfig for %s — using defaults", site_id)
                    return cls(site_id=site_id)

                # Map every column that exists on both the ORM row and this dataclass
                kwargs: dict = {"site_id": site_id}
                for f in cls.__dataclass_fields__:
                    if f == "site_id":
                        continue
                    db_val = getattr(row, f, None)
                    if db_val is not None:
                        kwargs[f] = db_val
                logger.info("Loaded SiteConfig for %s from database", site_id)
                return cls(**kwargs)
        except Exception as exc:
            logger.warning("SiteConfig load failed for %s: %s — using defaults", site_id, exc)
            return cls(site_id=site_id)


@dataclass
class KPIResult:
    """Standardized output from a KPI computation service."""

    kpi_name: str
    display_name: str
    category: str

    # Savings estimates (annual $)
    savings_low: float = 0.0
    savings_medium: float = 0.0
    savings_high: float = 0.0

    # Confidence 0-1 based on data availability and model maturity
    confidence: float = 0.0

    # Approval status
    status: str = "pending"  # pending, approved, rejected

    # Human-readable narrative
    narrative: str = ""

    # Assumptions underpinning the estimate
    assumptions: List[str] = field(default_factory=list)

    # Supporting metrics used in the calculation
    supporting_metrics: Dict[str, Any] = field(default_factory=dict)

    # Research basis: citations, methodology, and baseline data
    research_basis: Dict[str, Any] = field(default_factory=dict)

    # Data quality indicators
    data_points_used: int = 0
    data_coverage_pct: float = 0.0

    # True when result is backed by real telemetry/alert data rather than
    # assumptions only.  Auto-computed from data_points_used & coverage.
    data_grounded: bool = False

    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        # Auto-set data_grounded based on actual data backing
        if not self.data_grounded:
            self.data_grounded = (
                self.data_points_used > 0 and self.data_coverage_pct >= 0.05
            )

    def approve(self) -> "KPIResult":
        self.status = "approved"
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kpi_name": self.kpi_name,
            "display_name": self.display_name,
            "category": self.category,
            "savings_low": round(self.savings_low, 2),
            "savings_medium": round(self.savings_medium, 2),
            "savings_high": round(self.savings_high, 2),
            "confidence": round(self.confidence, 3),
            "status": self.status,
            "narrative": self.narrative,
            "assumptions": self.assumptions,
            "supporting_metrics": self.supporting_metrics,
            "data_points_used": self.data_points_used,
            "data_coverage_pct": round(self.data_coverage_pct, 2),
            "data_grounded": self.data_grounded,
            "research_basis": self.research_basis,
            "computed_at": self.computed_at.isoformat(),
        }


class BaseKPIService(ABC):
    """Abstract base class for KPI computation services.

    Each concrete subclass must implement ``compute()`` which queries
    real data and returns a ``KPIResult``.
    """

    kpi_name: str = ""
    display_name: str = ""
    category: str = ""

    def __init__(self, config: KPIConfig):
        self.config = config

    @abstractmethod
    def compute(
        self,
        asset_data: List[Dict[str, Any]],
        alert_data: List[Dict[str, Any]],
        telemetry_summary: Dict[str, Any],
        health_data: List[Dict[str, Any]],
    ) -> KPIResult:
        """Compute the KPI from real data.

        Parameters
        ----------
        asset_data : list
            List of asset records with health scores, RUL, etc.
        alert_data : list
            List of alert records with types, outcomes, timestamps.
        telemetry_summary : dict
            Aggregated telemetry statistics (avg power, runtime hours, etc.).
        health_data : list
            Per-asset health index results.

        Returns
        -------
        KPIResult
        """

    def _make_result(self, **kwargs) -> KPIResult:
        """Helper to create a KPIResult pre-filled with service metadata."""
        # Auto-inject research citations if not explicitly provided
        if "research_basis" not in kwargs:
            try:
                from .research_citations import get_research_basis
                kwargs["research_basis"] = get_research_basis(self.kpi_name)
            except Exception:
                pass
        return KPIResult(
            kpi_name=self.kpi_name,
            display_name=self.display_name,
            category=self.category,
            **kwargs,
        )

    def _confidence_from_coverage(
        self,
        data_points: int,
        min_for_full: int = 500,
        base_confidence: float = 0.5,
    ) -> float:
        """Scale confidence based on available data volume."""
        if data_points <= 0:
            return 0.1
        coverage = min(1.0, data_points / min_for_full)
        return base_confidence + (1.0 - base_confidence) * coverage

    def _tri_estimate(
        self, medium: float, low_factor: float = 0.6, high_factor: float = 1.4
    ) -> tuple:
        """Generate (low, medium, high) savings from a medium estimate."""
        return (medium * low_factor, medium, medium * high_factor)
